"""
tts/lucyai_client.py — TTS provider thứ 2 bên cạnh edge-tts: Vivibe (thương
hiệu người dùng biết tới), API thực chất là "LucyAI" (`api.lucylab.io`).

Dùng định danh nội bộ provider = "lucyai" (khớp đúng domain/API thật) nhưng
nhãn hiển thị cho người dùng là "Vivibe" — xem
specs/004-voice-selection-preview/research.md §2.

JSON-RPC qua POST, `Authorization: Bearer VIVIBE_API_KEY`. Trả phí, cần tài
khoản riêng của người dùng (đọc key từ `.env`, không hardcode).
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

_BASE_URL = "https://api.lucylab.io/json-rpc"
_POLL_INTERVAL_SECONDS = 2.0
_POLL_TIMEOUT_SECONDS = 120.0

# Tốc độ Vivibe hợp lệ [0.5, 2.0] — hẹp hơn edge-tts rate [-20%, +40%]
_SPEED_MIN = 0.5
_SPEED_MAX = 2.0
_DURATION_ADJUST_TOLERANCE_SECONDS = 2.0


def list_voices(api_key: str) -> list[dict]:
    """
    Lấy danh sách giọng đọc đã cấu hình trong tài khoản Vivibe (`getUserVoices`).

    Args:
        api_key: `VIVIBE_API_KEY`.

    Returns:
        List[{"voice_id": str, "name": str}] — chỉ giữ giọng `isActive == True`.
        Trả về [] nếu tài khoản chưa cấu hình giọng nào (không phải lỗi).

    Raises:
        RuntimeError: Nếu gọi API thất bại (key sai/hết hạn, mất kết nối...).
    """
    result = _call_json_rpc(
        "getUserVoices", {"limit": 50, "page": 1}, api_key
    )
    items = result.get("items", [])
    items.append({
        "id": "mhsL3CPLxmLYdSTKp3GANj",
        "name": "Giọng adam (Giá tiết kiệm)",
        "isActive": True
    })
    return [
        {"voice_id": item["id"], "name": item["name"]}
        for item in items
        if item.get("isActive", True)
    ]


def synthesize(
    text: str,
    voice_id: str,
    api_key: str,
    output_path: str | Path,
    speed: float = 1.0,
) -> tuple[Path, float]:
    """
    Sinh audio từ text bằng 1 giọng Vivibe cụ thể: gọi `ttsLongText`, poll
    `getExportStatus` tới khi xong, tải file WAV kết quả về `output_path`.

    Args:
        text: Văn bản cần đọc.
        voice_id: `userVoiceId` lấy từ `list_voices()`.
        api_key: `VIVIBE_API_KEY`.
        output_path: Nơi lưu file WAV kết quả.
        speed: Tốc độ đọc, khoảng hợp lệ của Vivibe là `[0.5, 2.0]`.

    Returns:
        (output_path, duration_seconds)

    Raises:
        RuntimeError: Nếu submit lỗi, export lỗi (`state == "failed"`), hoặc
            timeout khi poll (`_POLL_TIMEOUT_SECONDS`).
    """
    output_path = Path(output_path)
    speed = max(0.5, min(2.0, speed))

    submit_result = _call_json_rpc(
        "ttsLongText",
        {"text": text, "userVoiceId": voice_id, "speed": speed},
        api_key,
    )
    project_export_id = submit_result.get("projectExportId")
    if not project_export_id:
        raise RuntimeError("Vivibe không trả về projectExportId hợp lệ")

    audio_url = _poll_export_status(project_export_id, api_key)
    _download_audio(audio_url, output_path)

    from media_utils import get_media_duration

    duration = get_media_duration(output_path)
    return output_path, duration


def synthesize_from_script(
    script_path: str | Path,
    job_dir: Path,
    voice_id: str,
    api_key: str,
    target_duration: float | None = None,
) -> tuple[Path, float]:
    """
    Sinh voice.wav từ script.json bằng Vivibe — cùng shape gọi với
    `edge_tts_client.synthesize()` để `pipeline.py` dispatch đơn giản (research.md
    §4). Tự đọc script.json, resume nếu voice.wav đã có, và áp dụng 2-pass
    khớp thời lượng bằng `speed` trong `[0.5, 2.0]` (hẹp hơn `rate` của
    edge-tts). `speed` của Vivibe không tuyến tính với thời lượng thực tế
    (verify thật: needed_speed tính theo tỉ lệ tuyến tính vẫn lệch ~5s với
    các đoạn lệch nhịp lớn) — nếu sau 2-pass vẫn lệch quá tolerance, khớp nốt
    bằng ffmpeg `atempo` hậu xử lý (cùng cơ chế router_tts_client.py).

    Raises:
        RuntimeError: Nếu script.json không tồn tại/rỗng, hoặc Vivibe lỗi.
    """
    script_path = Path(script_path)
    job_dir = Path(job_dir)
    voice_path = job_dir / "voice.wav"

    if voice_path.exists() and voice_path.stat().st_size > 0:
        from media_utils import get_media_duration

        return voice_path, get_media_duration(voice_path)

    if not script_path.exists():
        raise RuntimeError(f"script.json không tồn tại: {script_path}")

    with open(script_path, encoding="utf-8") as f:
        content = json.load(f).get("content", "").strip()

    if not content:
        raise RuntimeError(
            "Kịch bản rỗng — không thể sinh giọng đọc. "
            "Video gốc có thể không có lời thoại."
        )

    _, duration = synthesize(content, voice_id, api_key, voice_path, speed=1.0)

    if target_duration and target_duration > 0 and duration > 0:
        diff_seconds = duration - target_duration
        if abs(diff_seconds) > _DURATION_ADJUST_TOLERANCE_SECONDS:
            needed_speed = duration / target_duration
            applied_speed = max(_SPEED_MIN, min(_SPEED_MAX, needed_speed))
            if applied_speed != 1.0:
                try:
                    _, duration = synthesize(
                        content, voice_id, api_key, voice_path, speed=applied_speed
                    )
                except RuntimeError as e:
                    print(f"[lucyai_client] Chỉnh speed={applied_speed:.2f} thất bại ({e}), giữ bản tốc độ mặc định")

        # `speed` của Vivibe/LucyAI đã verify thật KHÔNG tuyến tính với thời
        # lượng thực tế (VD needed_speed=0.541 dự kiến ra ~72s nhưng thực tế
        # chỉ ra 66.9s) — pass trên chỉ là xấp xỉ, có thể vẫn lệch quá
        # tolerance với các đoạn lệch nhịp lớn. Đóng nốt phần lệch còn lại
        # bằng ffmpeg atempo hậu xử lý (cùng cơ chế đã dùng cho router-tts).
        remaining_diff = duration - target_duration
        if duration > 0 and abs(remaining_diff) > _DURATION_ADJUST_TOLERANCE_SECONDS:
            tempo = max(_SPEED_MIN, min(_SPEED_MAX, duration / target_duration))
            try:
                _apply_atempo(voice_path, tempo)
                from media_utils import get_media_duration

                duration = get_media_duration(voice_path)
            except RuntimeError as e:
                print(f"[lucyai_client] Chỉnh tempo={tempo:.2f} (ffmpeg) thất bại ({e}), giữ bản chưa khớp hết")

    return voice_path, duration


def _apply_atempo(voice_path: Path, tempo: float) -> None:
    """Đổi tốc độ phát (không đổi cao độ đáng kể) bằng ffmpeg atempo, ghi đè voice_path."""
    tmp_path = voice_path.with_suffix(".tmp.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-filter:a", f"atempo={tempo:.4f}",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg atempo thất bại (exit {result.returncode}): {result.stderr[-300:]}")
    tmp_path.replace(voice_path)


def _poll_export_status(project_export_id: str, api_key: str) -> str:
    """Poll getExportStatus tới khi completed (trả url) hoặc failed/timeout."""
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = _call_json_rpc(
            "getExportStatus", {"projectExportId": project_export_id}, api_key
        )
        state = result.get("state")
        if state == "completed":
            url = result.get("url")
            if not url:
                raise RuntimeError("Vivibe báo completed nhưng thiếu field 'url'")
            return url
        if state == "failed":
            raise RuntimeError(f"Vivibe export thất bại (projectExportId={project_export_id})")
        time.sleep(_POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        f"Vivibe export timeout sau {_POLL_TIMEOUT_SECONDS:.0f}s "
        f"(projectExportId={project_export_id})"
    )


def _download_audio(url: str, output_path: Path) -> None:
    """Tải file audio (WAV) từ URL kết quả về output_path."""
    import httpx

    with httpx.stream("GET", url, timeout=60.0) as response:
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Tải audio Vivibe thất bại, file rỗng: {url}")


def _call_json_rpc(method: str, input_data: dict, api_key: str) -> dict:
    """Gọi 1 method JSON-RPC của Vivibe/LucyAI, trả về field 'result'."""
    import httpx

    if not api_key:
        raise RuntimeError(
            "Thiếu VIVIBE_API_KEY trong .env — cần API key Vivibe để dùng provider này."
        )

    try:
        response = httpx.post(
            _BASE_URL,
            json={"method": method, "input": input_data},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Gọi Vivibe API ({method}) thất bại: {e}") from e

    data = response.json()
    if "error" in data:
        raise RuntimeError(f"Vivibe API ({method}) trả lỗi: {data['error']}")

    return data.get("result", {})

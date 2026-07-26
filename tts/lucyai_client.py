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

import os
import time
from pathlib import Path

_BASE_URL = "https://api.lucylab.io/json-rpc"
_POLL_INTERVAL_SECONDS = 2.0
_POLL_TIMEOUT_SECONDS = 120.0

# Tốc độ Vivibe hợp lệ [0.5, 2.0] — hẹp hơn edge-tts rate [-20%, +40%]
_SPEED_MIN = 0.5
_SPEED_MAX = 2.0


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
    speed = max(_SPEED_MIN, min(_SPEED_MAX, speed))

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


def synthesize_text(text: str, voice_id: str, output_path: str | Path) -> Path:
    """
    Sinh audio từ 1 đoạn text ở tốc độ mặc định — chữ ký adapter dùng chung
    với `edge_tts_client.synthesize_text()` và `router_tts_client.synthesize_text()`
    để `tts/segment_synthesizer.py` gọi được cả 3 provider như nhau
    (005-natural-pause-dubbing, research.md §7).

    Khác `synthesize()`: tự đọc `VIVIBE_API_KEY` từ env thay vì nhận tham số,
    và luôn dùng `speed=1.0` (khớp thời lượng do segment_synthesizer lo bằng
    ffmpeg `atempo`, research.md §3).

    Raises:
        RuntimeError: Nếu thiếu `VIVIBE_API_KEY` hoặc Vivibe lỗi.
    """
    api_key = os.environ.get("VIVIBE_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Thiếu VIVIBE_API_KEY trong .env — cần để dùng giọng đọc Vivibe."
        )
    output_path = Path(output_path)
    synthesize(text, voice_id, api_key, output_path, speed=1.0)
    return output_path


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

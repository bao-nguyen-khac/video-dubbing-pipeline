"""
tts/router_tts_client.py — TTS provider thứ 3: giọng đọc Gemini qua 9router
(cùng endpoint OpenAI-compatible `{ROUTER_BASE_URL}/audio/speech` đã dùng cho
script_gen — tái dùng ROUTER_BASE_URL/ROUTER_API_KEY có sẵn, KHÔNG cần API
key riêng như LucyAI/Vivibe).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

# 30 giọng Gemini TTS đã biết — API 9router không có endpoint discovery
# (không giống getUserVoices của LucyAI), nên liệt kê cố định theo danh sách
# chính thức của Gemini TTS.
_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]

_MODEL_TEMPLATE = "gemini/gemini-3.1-flash-tts-preview/{voice}"
_DURATION_ADJUST_TOLERANCE_SECONDS = 2.0
# atempo hợp lệ [0.5, 100.0] — giới hạn cùng khoảng với edge-tts/LucyAI để
# tránh nghe bất thường
_TEMPO_MIN = 0.5
_TEMPO_MAX = 2.0


def list_voices() -> list[dict]:
    """Danh sách giọng Gemini TTS cố định (không có endpoint discovery)."""
    return [{"voice_id": v, "name": v} for v in _VOICES]


def synthesize_text(text: str, voice_id: str, output_path: str | Path) -> Path:
    """Sinh audio trực tiếp từ text — dùng cho nghe thử (US2, 004)."""
    output_path = Path(output_path)
    _call_speech_api(text, voice_id, output_path)
    return output_path


def synthesize_from_script(
    script_path: str | Path,
    job_dir: Path,
    voice_id: str,
    target_duration: float | None = None,
) -> tuple[Path, float]:
    """
    Sinh voice.wav từ script.json qua 9router — cùng shape gọi với
    edge_tts_client.synthesize()/lucyai_client.synthesize_from_script() để
    pipeline.py dispatch đơn giản.

    Tham số `speed` của API đã verify thật KHÔNG có tác dụng đáng kể (2.88s
    → 2.76s dù đặt speed=1.5) — khớp thời lượng bằng hậu xử lý ffmpeg
    `atempo` thay vì dựa vào API.

    Raises:
        RuntimeError: Nếu script.json không tồn tại/rỗng, hoặc API lỗi.
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

    _call_speech_api(content, voice_id, voice_path)

    from media_utils import get_media_duration

    duration = get_media_duration(voice_path)

    if target_duration and target_duration > 0 and duration > 0:
        diff_seconds = duration - target_duration
        if abs(diff_seconds) > _DURATION_ADJUST_TOLERANCE_SECONDS:
            tempo = max(_TEMPO_MIN, min(_TEMPO_MAX, duration / target_duration))
            try:
                _apply_atempo(voice_path, tempo)
                duration = get_media_duration(voice_path)
            except RuntimeError as e:
                print(f"[router_tts_client] Chỉnh tempo={tempo:.2f} thất bại ({e}), giữ bản gốc")

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


def _call_speech_api(text: str, voice_id: str, output_path: Path) -> None:
    """Gọi {ROUTER_BASE_URL}/audio/speech (OpenAI-compatible), ghi WAV ra output_path."""
    import httpx

    base_url = os.environ.get("ROUTER_BASE_URL", "http://localhost:20128/v1")
    api_key = os.environ.get("ROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("Thiếu ROUTER_API_KEY trong .env — cần để dùng 9router TTS.")

    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/audio/speech",
            json={
                "model": _MODEL_TEMPLATE.format(voice=voice_id),
                "input": text,
                "language": "Vietnamese",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Gọi 9router TTS thất bại: {e}") from e

    if not response.content:
        raise RuntimeError("9router TTS trả về audio rỗng")

    output_path.write_bytes(response.content)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Ghi file audio 9router TTS thất bại")

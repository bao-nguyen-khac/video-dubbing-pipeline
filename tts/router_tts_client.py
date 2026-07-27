"""
tts/router_tts_client.py — TTS provider thứ 3: giọng đọc Gemini qua 9router
(cùng endpoint OpenAI-compatible `{ROUTER_BASE_URL}/audio/speech` đã dùng cho
script_gen — tái dùng ROUTER_BASE_URL/ROUTER_API_KEY có sẵn, KHÔNG cần API
key riêng như LucyAI/Vivibe).
"""

from __future__ import annotations

import os
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


def list_voices() -> list[dict]:
    """Danh sách giọng Gemini TTS cố định (không có endpoint discovery)."""
    return [{"voice_id": v, "name": v} for v in _VOICES]


def is_available(timeout: float = 3.0) -> bool:
    """
    Kiểm tra nhanh 9router có phản hồi không (T041, 005) — `list_voices()`
    hardcode nên trước đây `GET /api/voices` vẫn liệt kê đủ 30 giọng dù
    9router đã chết, khiến job chỉ báo lỗi ở bước `synthesizing` sau khi đã
    tốn download/ASR/script. Timeout ngắn vì đây chỉ là gợi ý hiển thị, không
    chặn job (job vẫn tự báo lỗi rõ ràng nếu health-check này sai).
    """
    import httpx

    base_url = os.environ.get("ROUTER_BASE_URL", "http://localhost:20128/v1")
    api_key = os.environ.get("ROUTER_API_KEY", "")
    if not api_key:
        return False
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        return response.status_code < 500
    except httpx.HTTPError:
        return False


def synthesize_text(text: str, voice_id: str, output_path: str | Path) -> Path:
    """Sinh audio trực tiếp từ text — dùng cho nghe thử (US2, 004)."""
    output_path = Path(output_path)
    _call_speech_api(text, voice_id, output_path)
    return output_path


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

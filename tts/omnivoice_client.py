"""
tts/omnivoice_client.py — TTS provider thứ 4: OmniVoice (k2-fsa) chạy như một
service riêng (repo omnivoice-service), gọi qua HTTP.

Khác 3 provider kia: OmniVoice không có catalog giọng sẵn — mọi giọng đều phải
nạp trước bằng voice cloning (audio mẫu + transcript) vào service, service cấp
`voice_id` để dùng lại. Client này chỉ đọc/gọi service, không load model.

Đọc `OMNIVOICE_BASE_URL` từ `.env` (mặc định http://localhost:8100), tương tự
cách router_tts_client dùng ROUTER_BASE_URL — KHÔNG cần API key.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_BASE_URL = "http://localhost:8100"


def _base_url() -> str:
    return os.environ.get("OMNIVOICE_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _headers() -> dict:
    """
    X-API-Key khi service chạy public (vd tunnel Colab/Kaggle) và
    OMNIVOICE_API_KEY được set khớp phía service. Service local không set
    OMNIVOICE_API_KEY thì gọi bình thường, không cần header này.
    """
    api_key = os.environ.get("OMNIVOICE_API_KEY")
    return {"X-API-Key": api_key} if api_key else {}


def list_voices() -> list[dict]:
    """
    Danh sách giọng đã nạp vào OmniVoice service (voice-clone profile).

    Trả về [] nếu service chưa nạp giọng nào (không phải lỗi). Ném lỗi nếu
    không gọi được service — nhưng voices_api gọi kèm `is_available()` trước
    nên endpoint /api/voices vẫn "graceful degrade" như router-tts/lucyai.
    """
    import httpx

    response = httpx.get(f"{_base_url()}/voices", headers=_headers(), timeout=10.0)
    response.raise_for_status()
    items = response.json().get("voices", [])
    return [{"voice_id": v["voice_id"], "name": v["name"]} for v in items]


def is_available(timeout: float = 3.0) -> bool:
    """
    Kiểm tra nhanh OmniVoice service có sống không (giống router_tts.is_available).
    Service là local, có thể chưa khởi động → ẩn provider khỏi danh sách thay vì
    để job chết muộn ở bước synthesizing.
    """
    import httpx

    try:
        response = httpx.get(f"{_base_url()}/health", headers=_headers(), timeout=timeout)
        return response.status_code < 500
    except httpx.HTTPError:
        return False


def synthesize_text(text: str, voice_id: str, output_path: str | Path) -> Path:
    """
    Sinh audio từ text bằng 1 giọng đã nạp — chữ ký adapter dùng chung với 3
    provider còn lại để segment_synthesizer gọi được như nhau.

    Service trả WAV 24kHz mono; segment_synthesizer sẽ tự chuẩn hoá về
    44100/stereo qua ffmpeg (`_normalize_wav`), nên ở đây chỉ ghi bytes thô.

    Raises:
        RuntimeError: Nếu gọi service lỗi hoặc trả audio rỗng.
    """
    import httpx

    output_path = Path(output_path)
    try:
        response = httpx.post(
            f"{_base_url()}/synthesize",
            json={"text": text, "voice_id": voice_id},
            headers=_headers(),
            timeout=300.0,  # inference trên M1/MPS chậm (RTF ~8x), cho biên rộng
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Gọi OmniVoice service thất bại: {e}") from e

    if not response.content:
        raise RuntimeError("OmniVoice service trả về audio rỗng")

    output_path.write_bytes(response.content)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Ghi file audio OmniVoice thất bại")
    return output_path

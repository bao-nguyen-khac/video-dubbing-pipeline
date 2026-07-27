"""
web/backend/voices_api.py — Endpoint danh sách giọng đọc + nghe thử
(004-voice-selection-preview).

Chỉ gọi lại tts/edge_tts_client.py, tts/lucyai_client.py, và
tts/router_tts_client.py — không viết lại logic TTS (Constitution Principle I).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

# Câu mẫu cố định cho nghe thử (FR-005) — không cho người dùng tự nhập, tránh
# tốn quota Vivibe ngoài kiểm soát (spec.md → Assumptions)
_PREVIEW_TEXT = "Xin chào, đây là giọng đọc mẫu để bạn tham khảo trước khi chọn."


def _error(status_code: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message, **extra})


@router.get("")
async def list_voices():
    """
    GET /api/voices — danh sách giọng gộp edge-tts + Vivibe (nếu đã cấu hình
    VIVIBE_API_KEY). Vivibe lỗi/chưa cấu hình → chỉ trả edge-tts, không lỗi
    cả endpoint (FR-003, contracts/api.md).

    Cả 2 client (edge_tts_client, lucyai_client) đều đồng bộ (blocking) —
    chạy trong thread pool qua asyncio.to_thread() để không lồng
    asyncio.run() bên trong event loop của FastAPI (bug thật phát hiện lúc
    verify: "asyncio.run() cannot be called from a running event loop").
    """
    from tts.edge_tts_client import list_voices as edge_tts_list_voices

    edge_voices = await asyncio.to_thread(edge_tts_list_voices)
    voices = [
        {"provider": "edge-tts", "voice_id": v["voice_id"], "name": v["name"]}
        for v in edge_voices
    ]

    api_key = os.environ.get("VIVIBE_API_KEY", "")
    if api_key:
        try:
            from tts.lucyai_client import list_voices as lucyai_list_voices

            lucyai_voices = await asyncio.to_thread(lucyai_list_voices, api_key)
            voices += [
                {"provider": "lucyai", "voice_id": v["voice_id"], "name": v["name"]}
                for v in lucyai_voices
            ]
        except RuntimeError as e:
            print(f"[voices_api] Lấy danh sách giọng Vivibe thất bại: {e}")

    # router-tts tái dùng ROUTER_API_KEY đã có (không cần secret riêng). Trước
    # T041 (005), list_voices() hardcode nên vẫn liệt kê đủ 30 giọng dù
    # 9router chết — người dùng chọn xong job mới báo lỗi ở synthesizing, sau
    # khi đã tốn download/ASR/script. Thêm health-check timeout ngắn: 9router
    # không phản hồi → ẩn hẳn router-tts khỏi danh sách thay vì để job chết
    # muộn (cùng cách lucyai đã "graceful degrade" ở khối phía trên).
    if os.environ.get("ROUTER_API_KEY", ""):
        from tts.router_tts_client import is_available as router_tts_is_available
        from tts.router_tts_client import list_voices as router_tts_list_voices

        if await asyncio.to_thread(router_tts_is_available):
            router_voices = await asyncio.to_thread(router_tts_list_voices)
            voices += [
                {"provider": "router-tts", "voice_id": v["voice_id"], "name": v["name"]}
                for v in router_voices
            ]
        else:
            print("[voices_api] 9router không phản hồi, ẩn giọng router-tts khỏi danh sách")

    return {"voices": voices}


class PreviewRequest(BaseModel):
    provider: str
    voice_id: str


@router.post("/preview")
async def preview_voice(body: PreviewRequest):
    """
    POST /api/voices/preview — sinh audio mẫu (FR-004/FR-005), KHÔNG tạo job
    trong jobs/, KHÔNG bị chặn bởi rule "đang có job chạy" (FR-008,
    contracts/api.md).
    """
    if body.provider not in ("edge-tts", "lucyai", "router-tts"):
        return _error(400, "provider phải là 'edge-tts', 'lucyai' hoặc 'router-tts'")
    if not body.voice_id:
        return _error(400, "Thiếu voice_id")

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "preview.wav"
        try:
            if body.provider == "lucyai":
                from tts.lucyai_client import synthesize as lucyai_synthesize_raw

                api_key = os.environ.get("VIVIBE_API_KEY", "")
                await asyncio.to_thread(
                    lucyai_synthesize_raw, _PREVIEW_TEXT, body.voice_id, api_key, output_path
                )
            elif body.provider == "router-tts":
                from tts.router_tts_client import synthesize_text as router_tts_synthesize_text

                await asyncio.to_thread(
                    router_tts_synthesize_text, _PREVIEW_TEXT, body.voice_id, output_path
                )
            else:
                from tts.edge_tts_client import synthesize_text as edge_tts_synthesize_text

                await asyncio.to_thread(
                    edge_tts_synthesize_text, _PREVIEW_TEXT, body.voice_id, output_path
                )
        except RuntimeError as e:
            return JSONResponse(status_code=502, content={"error": f"Sinh audio mẫu thất bại: {e}"})

        audio_bytes = output_path.read_bytes()

    return Response(content=audio_bytes, media_type="audio/wav")

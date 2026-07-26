"""
tts/edge_tts_client.py — Sinh giọng đọc tiếng Việt bằng edge-tts.

Voice mặc định: vi-VN-NamMinhNeural (Nam)
Backup voice:   vi-VN-HoaiMyNeural (Nữ)

Từ 005-natural-pause-dubbing, module này chỉ còn vai trò adapter mức-text:
`synthesize_text()` sinh audio cho 1 nhịp (hoặc 1 đoạn nghe thử), còn việc
khớp nhịp/khớp thời lượng/thu mốc phụ đề do `tts/segment_synthesizer.py` lo
chung cho cả 3 provider (research.md §6/§7).
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────

DEFAULT_VOICE = "vi-VN-NamMinhNeural"
BACKUP_VOICE = "vi-VN-HoaiMyNeural"


def list_voices() -> list[dict]:
    """
    Lấy danh sách giọng đọc tiếng Việt có sẵn trong catalog edge-tts
    (004-voice-selection-preview). Lấy động qua SDK thay vì hardcode, dù thực
    tế hiện chỉ có 2 giọng (đã verify: `vi-VN-HoaiMyNeural`,
    `vi-VN-NamMinhNeural` — research.md §1).

    Returns:
        List[{"voice_id": str, "name": str}]
    """
    voices = asyncio.run(_list_voices_async())
    return [
        {"voice_id": v["ShortName"], "name": v["FriendlyName"]}
        for v in voices
        if v["Locale"].startswith("vi-")
    ]


async def _list_voices_async() -> list[dict]:
    import edge_tts

    return await edge_tts.list_voices()


def synthesize_text(text: str, voice: str, output_path: str | Path) -> Path:
    """
    Sinh audio từ 1 đoạn text ở tốc độ mặc định.

    Dùng cho cả nghe thử (004-voice-selection-preview, US2) và tổng hợp từng
    nhịp trong luồng job (005 — `tts/segment_synthesizer.py` gọi qua adapter
    cùng chữ ký với 2 provider còn lại).
    """
    output_path = Path(output_path)
    _synthesize_with_fallback(text, voice, output_path, rate="+0%")
    return output_path


def _synthesize_with_fallback(content: str, voice: str, voice_path: Path, rate: str) -> None:
    """Sinh voice với voice chính, fallback sang voice phụ nếu lỗi."""
    try:
        asyncio.run(_synthesize_async(content, voice, voice_path, rate))
    except Exception as e_main:
        if voice != BACKUP_VOICE:
            try:
                asyncio.run(_synthesize_async(content, BACKUP_VOICE, voice_path, rate))
            except Exception as e_backup:
                raise RuntimeError(
                    f"TTS thất bại với cả 2 voice:\n"
                    f"  {voice}: {e_main}\n"
                    f"  {BACKUP_VOICE}: {e_backup}"
                ) from e_backup
        else:
            raise RuntimeError(f"TTS thất bại: {e_main}") from e_main

    if not voice_path.exists() or voice_path.stat().st_size == 0:
        raise RuntimeError("edge-tts không tạo được file âm thanh hợp lệ")


async def _synthesize_async(text: str, voice: str, output_path: Path, rate: str = "+0%") -> None:
    """Chạy edge-tts async và lưu ra file WAV."""
    try:
        import edge_tts
    except ImportError as e:
        raise RuntimeError(
            "edge-tts chưa được cài đặt. Chạy: pip install edge-tts"
        ) from e

    # edge-tts xuất ra MP3, sau đó convert sang WAV để ffmpeg dễ xử lý
    mp3_path = output_path.with_suffix(".mp3")

    communicator = edge_tts.Communicate(text, voice, rate=rate)
    await communicator.save(str(mp3_path))

    # Convert MP3 → WAV 44.1kHz stereo
    if not mp3_path.exists() or mp3_path.stat().st_size == 0:
        raise RuntimeError("edge-tts không tạo được file MP3 đầu ra")

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(mp3_path),
            "-ar", "44100",
            "-ac", "2",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Dọn file MP3 tạm
    if mp3_path.exists():
        mp3_path.unlink()

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg convert MP3→WAV thất bại: {result.stderr[-300:]}"
        )

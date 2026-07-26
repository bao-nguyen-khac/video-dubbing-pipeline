"""
tts/edge_tts_client.py — Sinh giọng đọc tiếng Việt bằng edge-tts.

Voice mặc định: vi-VN-NamMinhNeural (Nam)
Backup voice:   vi-VN-HoaiMyNeural (Nữ)
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from media_utils import get_media_duration

# ─── Config ──────────────────────────────────────────────────────────────────

DEFAULT_VOICE = "vi-VN-NamMinhNeural"
BACKUP_VOICE = "vi-VN-HoaiMyNeural"

# FR-010: giới hạn chỉnh tốc độ đọc để khớp video gốc — tránh nghe quá nhanh/chậm
_RATE_MIN_PCT = -20
_RATE_MAX_PCT = 40
# Lệch dưới ngưỡng này (giây) thì không cần sinh lại ở tốc độ khác
_RATE_ADJUST_TOLERANCE_SECONDS = 2.0


# ─── Main Function ───────────────────────────────────────────────────────────


def synthesize(
    script_path: str | Path,
    job_dir: Path,
    voice: str = DEFAULT_VOICE,
    target_duration: float | None = None,
) -> tuple[Path, float]:
    """
    Sinh file âm thanh từ script.json bằng edge-tts.

    Args:
        script_path: Đường dẫn tới script.json.
        job_dir: Thư mục job (jobs/{job_id}/).
        voice: Tên voice edge-tts (mặc định vi-VN-NamMinhNeural).
        target_duration: Thời lượng video gốc (giây) để chỉnh tốc độ đọc cho khớp
            gần đúng (FR-010). None hoặc <=0 → sinh ở tốc độ mặc định, không chỉnh.

    Returns:
        (voice_path, duration_seconds)
        voice_path: Path tới voice.wav vừa tạo.
        duration_seconds: Thời lượng file audio (giây).

    Raises:
        RuntimeError: Nếu TTS thất bại hoặc script rỗng.
    """
    script_path = Path(script_path)
    job_dir = Path(job_dir)
    voice_path = job_dir / "voice.wav"

    # Resume: nếu voice.wav đã tồn tại và hợp lệ, bỏ qua
    if voice_path.exists() and voice_path.stat().st_size > 0:
        duration = get_media_duration(voice_path)
        return voice_path, duration

    # Đọc kịch bản
    if not script_path.exists():
        raise RuntimeError(f"script.json không tồn tại: {script_path}")

    with open(script_path, encoding="utf-8") as f:
        script_data = json.load(f)

    content = script_data.get("content", "").strip()

    # Edge case: kịch bản rỗng (video gốc không có lời thoại)
    if not content:
        raise RuntimeError(
            "Kịch bản rỗng — không thể sinh giọng đọc. "
            "Video gốc có thể không có lời thoại."
        )

    # Lượt 1: sinh ở tốc độ mặc định
    _synthesize_with_fallback(content, voice, voice_path, rate="+0%")
    duration = get_media_duration(voice_path)

    # Lượt 2 (FR-010): nếu lệch đáng kể so với video gốc, chỉnh rate rồi sinh lại.
    # Lỗi ở lượt này KHÔNG chặn pipeline — giữ nguyên bản lượt 1 nếu sinh lại lỗi.
    if target_duration and target_duration > 0 and duration > 0:
        diff_seconds = duration - target_duration
        if abs(diff_seconds) > _RATE_ADJUST_TOLERANCE_SECONDS:
            needed_pct = round((duration / target_duration - 1) * 100)
            applied_pct = max(_RATE_MIN_PCT, min(_RATE_MAX_PCT, needed_pct))
            if applied_pct != 0:
                rate = f"{applied_pct:+d}%"
                try:
                    _synthesize_with_fallback(content, voice, voice_path, rate=rate)
                    duration = get_media_duration(voice_path)
                except RuntimeError as e:
                    print(f"[edge_tts_client] Chỉnh rate={rate} thất bại ({e}), giữ bản tốc độ mặc định")

    return voice_path, duration


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

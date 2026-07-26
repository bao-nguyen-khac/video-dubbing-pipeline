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
    Sinh audio trực tiếp từ 1 đoạn text ngắn (không qua script.json) — dùng
    cho nghe thử (004-voice-selection-preview, US2), không phải luồng job
    chính (xem synthesize()).
    """
    output_path = Path(output_path)
    _synthesize_with_fallback(text, voice, output_path, rate="+0%")
    return output_path


# ─── Main Function ───────────────────────────────────────────────────────────


def synthesize(
    script_path: str | Path,
    job_dir: Path,
    voice: str = DEFAULT_VOICE,
    target_duration: float | None = None,
    collect_captions: bool = False,
) -> tuple[Path, float]:
    """
    Sinh file âm thanh từ script.json bằng edge-tts.

    Args:
        script_path: Đường dẫn tới script.json.
        job_dir: Thư mục job (jobs/{job_id}/).
        voice: Tên voice edge-tts (mặc định vi-VN-NamMinhNeural).
        target_duration: Thời lượng video gốc (giây) để chỉnh tốc độ đọc cho khớp
            gần đúng (FR-010). None hoặc <=0 → sinh ở tốc độ mặc định, không chỉnh.
        collect_captions: Nếu True, thu thêm mốc thời gian theo câu/cụm từ
            `SentenceBoundary` của edge-tts, ghi ra `jobs/{job_id}/captions.json`
            (US4, 003-dubbing-fixes-subtitles, research.md §4).

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
    captions_path = job_dir / "captions.json"

    # Resume: nếu voice.wav đã tồn tại và hợp lệ, bỏ qua sinh lại. Vẫn có thể
    # cần thu captions.json nếu job trước đó không bật dynamic_captions.
    if voice_path.exists() and voice_path.stat().st_size > 0:
        duration = get_media_duration(voice_path)
        if collect_captions and not (captions_path.exists() and captions_path.stat().st_size > 0):
            with open(script_path, encoding="utf-8") as f:
                content = json.load(f).get("content", "").strip()
            if content:
                _collect_captions(content, voice, captions_path, rate="+0%")
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
    final_rate = "+0%"

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
                    final_rate = rate
                except RuntimeError as e:
                    print(f"[edge_tts_client] Chỉnh rate={rate} thất bại ({e}), giữ bản tốc độ mặc định")

    if collect_captions:
        # Thu riêng 1 lượt .stream() CÙNG rate cuối cùng chỉ để lấy
        # SentenceBoundary — không ghi đè voice.wav đã chốt ở trên (US4,
        # research.md §4). Lỗi ở đây KHÔNG chặn job (chỉ mất phụ đề động,
        # dub content vẫn còn giá trị — xử lý khác US3, xem pipeline.py).
        try:
            _collect_captions(content, voice, captions_path, rate=final_rate)
        except RuntimeError as e:
            print(f"[edge_tts_client] Thu captions.json thất bại ({e}), bỏ qua phụ đề động")

    return voice_path, duration


def _collect_captions(content: str, voice: str, captions_path: Path, rate: str) -> None:
    """Chạy edge-tts stream() chỉ để thu SentenceBoundary, ghi ra captions.json."""
    cues = asyncio.run(_stream_sentence_boundaries(content, voice, rate))
    if not cues:
        raise RuntimeError("Không thu được SentenceBoundary nào từ edge-tts")
    with open(captions_path, "w", encoding="utf-8") as f:
        json.dump(cues, f, ensure_ascii=False, indent=2)


async def _stream_sentence_boundaries(text: str, voice: str, rate: str) -> list[dict]:
    """Chạy edge_tts.Communicate.stream(), trả về list cue {start, end, text} (giây)."""
    import edge_tts

    cues = []
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk.get("type") == "SentenceBoundary":
            # offset/duration đơn vị 100-ns (chuẩn edge-tts/Azure Speech SDK)
            start = chunk["offset"] / 1e7
            cues.append(
                {
                    "start": start,
                    "end": start + chunk["duration"] / 1e7,
                    "text": chunk["text"].strip(),
                }
            )
    return cues


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

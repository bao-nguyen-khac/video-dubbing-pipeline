"""
merge/ffmpeg_merge.py — Ghép voice track (+ nhạc nền tách được, nếu có) vào video
gốc bằng ffmpeg.

FR-009: giữ nhạc nền gốc, chỉ loại bỏ giọng nói gốc, khi có background_audio_path
(từ merge/vocal_separator.py). Nếu không có (Demucs lỗi) → fallback mute toàn bộ
audio gốc như hành vi trước đây.
Phát hiện và cảnh báo nếu thời lượng audio/video lệch đáng kể.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from media_utils import get_media_duration

# Ngưỡng lệch thời lượng (giây) — nếu vượt quá → set warnings.duration_mismatch = True
_DURATION_MISMATCH_THRESHOLD_SECONDS = 3.0


def merge_audio(
    source_video_path: str | Path,
    voice_path: str | Path,
    job_dir: Path,
    background_audio_path: str | Path | None = None,
) -> tuple[Path, bool, bool]:
    """
    Ghép voice.wav (+ background_audio_path nếu có) vào source.mp4.

    Args:
        source_video_path: Đường dẫn tới source.mp4.
        voice_path: Đường dẫn tới voice.wav.
        job_dir: Thư mục job (jobs/{job_id}/).
        background_audio_path: Đường dẫn tới nhạc nền tách được (background.wav);
            None nếu tách thất bại → fallback mute toàn bộ audio gốc (FR-009).

    Returns:
        (output_path, duration_mismatch, background_music_kept)
        output_path: Path tới output.mp4 vừa tạo.
        duration_mismatch: True nếu lệch thời lượng đáng kể.
        background_music_kept: True nếu audio output có trộn nhạc nền gốc.

    Raises:
        RuntimeError: Nếu ffmpeg gặp lỗi.
    """
    source_video_path = Path(source_video_path)
    voice_path = Path(voice_path)
    job_dir = Path(job_dir)
    output_path = job_dir / "output.mp4"

    # Validate input files
    if not source_video_path.exists():
        raise RuntimeError(f"source.mp4 không tồn tại: {source_video_path}")
    if not voice_path.exists():
        raise RuntimeError(f"voice.wav không tồn tại: {voice_path}")

    background_path = Path(background_audio_path) if background_audio_path else None
    if background_path is not None and (
        not background_path.exists() or background_path.stat().st_size == 0
    ):
        background_path = None  # coi như tách nhạc nền thất bại, fallback mute
    background_music_kept = background_path is not None

    # Kiểm tra thời lượng để cảnh báo lệch (tính trước để dùng được cả khi resume)
    video_dur = get_media_duration(source_video_path)
    audio_dur = get_media_duration(voice_path)
    duration_mismatch = (
        abs(video_dur - audio_dur) > _DURATION_MISMATCH_THRESHOLD_SECONDS
        if video_dur > 0 and audio_dur > 0
        else False
    )

    # Resume: nếu output.mp4 đã tồn tại và hợp lệ, bỏ qua re-merge nhưng vẫn trả
    # đúng cảnh báo lệch thời lượng thay vì hardcode False
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path, duration_mismatch, background_music_kept

    # Ghép audio vào video bằng ffmpeg
    if background_path is not None:
        _run_ffmpeg_merge_with_background(source_video_path, voice_path, background_path, output_path)
    else:
        _run_ffmpeg_merge(source_video_path, voice_path, output_path)

    return output_path, duration_mismatch, background_music_kept


def _run_ffmpeg_merge(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> None:
    """
    Chạy ffmpeg để ghép audio mới vào video, loại bỏ audio gốc.

    Strategy:
    - `-map 0:v:0`: Lấy video stream từ source (giữ nguyên codec, không re-encode)
    - `-map 1:a:0`: Lấy audio stream từ voice.wav
    - `-c:v copy`: Copy video stream không re-encode (nhanh, giữ chất lượng gốc)
    - `-c:a aac`: Encode audio sang AAC (chuẩn MP4)
    - `-shortest`: Kết thúc khi stream ngắn hơn kết thúc (xử lý lệch thời lượng)
    """
    cmd = [
        "ffmpeg",
        "-y",                           # Ghi đè output nếu đã tồn tại
        "-i", str(video_path),          # Input 0: video gốc
        "-i", str(audio_path),          # Input 1: voice mới
        "-map", "0:v:0",               # Lấy video từ input 0
        "-map", "1:a:0",               # Lấy audio từ input 1
        "-c:v", "copy",                # Copy video không re-encode
        "-c:a", "aac",                 # Encode audio → AAC
        "-b:a", "128k",               # Bitrate audio 128kbps
        "-shortest",                    # Kết thúc theo stream ngắn hơn
        "-movflags", "+faststart",     # Tối ưu streaming (moov atom ở đầu)
        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # Tối đa 5 phút cho video ngắn (SC-002)
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg merge thất bại (exit {result.returncode}):\n"
            f"{result.stderr[-500:]}"
        )

    # Kiểm tra output hợp lệ
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg không tạo được output.mp4 hợp lệ")


def _run_ffmpeg_merge_with_background(
    video_path: Path,
    voice_path: Path,
    background_path: Path,
    output_path: Path,
) -> None:
    """
    Ghép video + voice mới + nhạc nền tách được (FR-009).

    Strategy:
    - Trộn voice (âm lượng gốc) với nhạc nền (giảm còn 50%, tránh át giọng đọc)
      bằng filter `amix`, lấy thời lượng theo voice (`duration=first`).
    - Map video từ source (giữ nguyên codec), audio từ track đã trộn.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),          # Input 0: video gốc
        "-i", str(voice_path),          # Input 1: voice mới
        "-i", str(background_path),     # Input 2: nhạc nền tách được
        "-filter_complex",
        "[1:a]volume=1.0[voice];[2:a]volume=0.5[bg];"
        "[voice][bg]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v:0",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg merge (kèm nhạc nền) thất bại (exit {result.returncode}):\n"
            f"{result.stderr[-500:]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg không tạo được output.mp4 hợp lệ")

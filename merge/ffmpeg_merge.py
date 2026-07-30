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

from media_utils import get_media_duration, has_audio_stream

# Ngưỡng lệch thời lượng (giây) — nếu vượt quá → set warnings.duration_mismatch = True
_DURATION_MISMATCH_THRESHOLD_SECONDS = 3.0


def _parse_one_timestamp(token: str, total_duration: float) -> float | None:
    """'end'/'hết' → hết video; 'M:SS'/'H:MM:SS'/'SS(.ms)' → giây. None nếu sai."""
    token = token.strip().lower()
    if token in ("end", "hết", "het", "cuối", "cuoi"):
        return total_duration
    if not token:
        return None
    try:
        parts = [float(p) for p in token.split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return max(0.0, min(total_duration, seconds))


def parse_time_ranges(text: str, total_duration: float) -> list[list[float]]:
    """
    Chuỗi mốc thời gian người dùng nhập → danh sách [start, end] (giây).

    Chấp nhận nhiều khoảng ngăn bằng dấu phẩy: "0:15-0:30, 1:05-end". Bỏ qua
    phần sai định dạng thay vì báo lỗi. Kết quả đã kẹp trong [0, total] và bỏ
    khoảng rỗng/âm.
    """
    ranges: list[list[float]] = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if "-" not in part:
            continue
        left, right = part.split("-", 1)
        start = _parse_one_timestamp(left, total_duration)
        end = _parse_one_timestamp(right, total_duration)
        if start is None or end is None or end <= start:
            continue
        ranges.append([round(start, 3), round(end, 3)])
    return ranges


def apply_keep_original_ranges(
    output_path: Path,
    source_video_path: Path,
    ranges: list[list[float]],
) -> None:
    """
    Phủ AUDIO GỐC (còn nguyên nhạc + tiếng hát) vào các khoảng `ranges` của
    output đã ghép — dùng khi video có đoạn nhạc muốn giữ nguyên, không lồng
    tiếng đè (case 50% nói / 50% nhạc).

    Chạy 1 pass phụ: video copy (không re-encode), chỉ trộn lại audio. Trong
    khoảng giữ → dùng audio gốc; ngoài khoảng → giữ audio đã lồng tiếng.

    No-op nếu không có khoảng nào hoặc video gốc không có audio.
    """
    output_path = Path(output_path)
    source_video_path = Path(source_video_path)
    if not ranges or not has_audio_stream(source_video_path):
        return

    inside = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in ranges)
    filter_complex = (
        # Tắt tiếng track lồng tiếng TRONG khoảng giữ
        f"[0:a]volume=0:enable='{inside}'[dub];"
        # Tắt tiếng audio gốc NGOÀI khoảng giữ
        f"[1:a]volume=0:enable='not({inside})'[orig];"
        # Cộng lại (loại trừ nhau theo thời gian nên normalize=0 để giữ nguyên mức)
        f"[dub][orig]amix=inputs=2:normalize=0[a]"
    )
    tmp_path = output_path.with_suffix(".keep.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(output_path),         # 0: bản đã lồng tiếng (video + audio dub)
        "-i", str(source_video_path),   # 1: audio gốc
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg phủ audio gốc (giữ nhạc) thất bại (exit {result.returncode}):\n"
            f"{result.stderr[-500:]}"
        )
    if not tmp_path.exists() or tmp_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg không tạo được file khi phủ audio gốc")
    tmp_path.replace(output_path)


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
    - `apad` + `-shortest`: Đệm im lặng vào voice cho đủ dài rồi cắt theo VIDEO.
      Voice thường ngắn hơn video khi cuối clip chỉ có nhạc/không lời — nếu
      dùng `-shortest` trực tiếp trên voice thì video bị cắt cụt mất đoạn cuối
      (bug thật: video 19.9s, lời 3.1s → output chỉ còn ~9.9s). apad đảm bảo
      output luôn bằng đúng độ dài video, phần thừa là im lặng.
    """
    cmd = [
        "ffmpeg",
        "-y",                           # Ghi đè output nếu đã tồn tại
        "-i", str(video_path),          # Input 0: video gốc
        "-i", str(audio_path),          # Input 1: voice mới
        "-filter_complex", "[1:a]apad[a]",  # Đệm im lặng cho voice
        "-map", "0:v:0",               # Lấy video từ input 0
        "-map", "[a]",                 # Audio đã đệm
        "-c:v", "copy",                # Copy video không re-encode
        "-c:a", "aac",                 # Encode audio → AAC
        "-b:a", "128k",               # Bitrate audio 128kbps
        "-shortest",                    # Cắt theo video (audio đã đệm dài hơn)
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
      bằng `amix`, lấy thời lượng theo NHẠC NỀN (`duration=longest`) — nhạc nền
      dài bằng cả video, còn voice thường ngắn hơn (cuối clip chỉ có nhạc).
    - `apad` + `-shortest`: đệm cho đủ rồi cắt theo VIDEO, giữ trọn đoạn nhạc
      cuối. Trước đây `duration=first` + `-shortest` lấy độ dài theo voice nên
      cắt cụt phần cuối chỉ có nhạc (bug thật: 19.9s → 9.9s).
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),          # Input 0: video gốc
        "-i", str(voice_path),          # Input 1: voice mới
        "-i", str(background_path),     # Input 2: nhạc nền tách được
        "-filter_complex",
        "[1:a]volume=1.0[voice];[2:a]volume=0.5[bg];"
        "[voice][bg]amix=inputs=2:duration=longest:dropout_transition=0[mix];"
        "[mix]apad[a]",
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

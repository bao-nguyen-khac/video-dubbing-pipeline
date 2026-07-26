"""
merge/subtitle_burner.py — Sinh file phụ đề (.srt) từ danh sách cue và ghi
cứng (burn-in) vào video bằng ffmpeg (bộ lọc `subtitles`, dùng libass).

Dùng chung cho:
- script_mode = "subtitle" (US3, 003-dubbing-fixes-subtitles): cue lấy từ
  Script.segments (dịch sát nghĩa theo mốc thời gian ASR gốc).
- dynamic_captions = true (US4): cue lấy từ Voice Track.word_boundaries (gom
  theo câu/cụm từ sự kiện WordBoundary của edge-tts).

Burn-in bắt buộc re-encode video (không dùng -c:v copy được nữa khi có filter
video) — xem research.md §7.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _format_srt_timestamp(seconds: float) -> str:
    """Chuyển giây (float) sang định dạng timestamp SRT: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(cues: list[dict], srt_path: str | Path) -> Path:
    """
    Sinh file .srt chuẩn từ danh sách cue {start, end, text} (giây).

    Args:
        cues: List[{"start": float, "end": float, "text": str}], đã sắp xếp
            theo thời gian tăng dần.
        srt_path: Đường dẫn file .srt sẽ ghi ra.

    Returns:
        Path tới file .srt vừa ghi.

    Raises:
        RuntimeError: Nếu cues rỗng — không có gì để burn.
    """
    srt_path = Path(srt_path)

    if not cues:
        raise RuntimeError("Danh sách cue rỗng — không có nội dung để tạo phụ đề")

    lines = []
    for i, cue in enumerate(cues, start=1):
        text = cue["text"].strip()
        if not text:
            continue
        start_ts = _format_srt_timestamp(cue["start"])
        end_ts = _format_srt_timestamp(cue["end"])
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def burn_subtitles(
    video_path: str | Path,
    srt_path: str | Path,
    output_path: str | Path,
    audio_path: str | Path | None = None,
) -> Path:
    """
    Burn-in phụ đề từ file .srt vào video, căn giữa dưới màn hình.

    Args:
        video_path: Video gốc để lấy video stream (và audio stream nếu
            audio_path=None).
        srt_path: File .srt đã sinh bằng write_srt().
        output_path: Đường dẫn output.mp4 sẽ ghi ra.
        audio_path: Nếu khác None, dùng audio từ file này thay vì audio có
            sẵn trong video_path (VD dùng cho US4: video_path là output đã
            ghép voice+nhạc nền, audio đã đúng sẵn nên audio_path=None; US3
            audio_path cũng None vì audio gốc nằm sẵn trong source.mp4).

    Returns:
        Path tới output_path.

    Raises:
        RuntimeError: Nếu ffmpeg lỗi hoặc không tạo được output hợp lệ. Việc
            fail job hay chỉ cảnh báo khi lỗi là quyết định của caller (US3
            fail job, US4 chỉ cảnh báo — xem tasks.md T017/T022).
    """
    video_path = Path(video_path)
    srt_path = Path(srt_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise RuntimeError(f"Video nguồn không tồn tại: {video_path}")
    if not srt_path.exists():
        raise RuntimeError(f"File phụ đề không tồn tại: {srt_path}")

    # force_style: Alignment=2 (căn giữa dưới), cỡ chữ/viền dễ đọc trên nền video
    subtitles_filter = (
        f"subtitles={_ffmpeg_escape_path(srt_path)}:"
        "force_style='Alignment=2,FontSize=16,Outline=1,Shadow=0,"
        "MarginV=40,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000'"
    )

    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    if audio_path is not None:
        cmd += ["-i", str(audio_path)]
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    cmd += [
        "-vf", subtitles_filter,
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        # Ép format MP4 tường minh — không dựa vào đuôi file để đoán, vì
        # output_path có thể là file tạm không có đuôi ".mp4" chuẩn (VD
        # "*.mp4.tmp" ở US4), khiến ffmpeg lỗi "Unable to choose an output
        # format" (bug thật phát hiện lúc verify US4)
        "-f", "mp4",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg burn phụ đề thất bại (exit {result.returncode}):\n"
            f"{result.stderr[-500:]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg không tạo được output hợp lệ sau khi burn phụ đề")

    return output_path


def _ffmpeg_escape_path(path: Path) -> str:
    """Escape đường dẫn cho filter ffmpeg (dấu ':' trên đường dẫn phải escape)."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

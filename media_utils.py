"""media_utils.py — Shared ffmpeg/ffprobe helper dùng chung giữa các module."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_media_duration(media_path: str | Path) -> float:
    """Lấy thời lượng file media (video/audio) bằng ffprobe (giây)."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return 0.0


def get_video_frame_size(media_path: str | Path) -> dict:
    """
    Lấy kích thước khung hình video (width/height) bằng ffprobe — dùng để tính
    cỡ chữ và vị trí từng dòng phụ đề theo pixel thật (009-hardsub-blur-
    reposition, merge/text_renderer.py::render_cue_overlays()).

    Trả {"width": 0, "height": 0} nếu không đọc được (không chặn caller — để
    ffmpeg tự báo lỗi rõ ràng hơn ở bước burn nếu thật sự có vấn đề).
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                return {"width": int(parts[0]), "height": int(parts[1])}
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return {"width": 0, "height": 0}


def has_audio_stream(media_path: str | Path) -> bool:
    """
    True nếu file có ít nhất 1 audio stream, bằng ffprobe.

    Một số bài đăng TikTok dạng ảnh/slideshow được nền tảng tự dựng thành video
    (thường có metadata "Bento4 Video Handler") — phần nhạc nền có thể phát
    riêng ngoài track hình, khiến file tải về chỉ còn video, không có audio.
    Kiểm tra sớm ở đây để báo lỗi rõ ràng thay vì để ffmpeg thất bại với thông
    điệp kỹ thuật khó hiểu ("Output file does not contain any stream").
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=index",
                "-of", "csv=p=0",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, OSError):
        return True  # Không kiểm tra được thì không chặn — để ffmpeg tự quyết định

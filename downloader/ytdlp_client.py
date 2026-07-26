"""
downloader/ytdlp_client.py — Tải video qua yt-dlp (YouTube + fallback).

Constitution Principle II: yt-dlp là fallback khi f2 không hỗ trợ nguồn.
"""

from __future__ import annotations

from pathlib import Path


def download_video_ytdlp(url: str, job_dir: Path) -> Path:
    """
    Tải video qua yt-dlp. Dùng cho YouTube và làm fallback.

    Args:
        url: URL công khai của video.
        job_dir: Thư mục job (jobs/{job_id}/).

    Returns:
        Path tới file source.mp4 đã tải.

    Raises:
        RuntimeError: Nếu tải thất bại.
    """
    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError(
            "yt-dlp chưa được cài đặt. Chạy: pip install yt-dlp"
        ) from e

    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    output_path = job_dir / "source.mp4"

    # Resume: nếu source.mp4 đã tồn tại và hợp lệ, bỏ qua
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    ydl_opts = {
        # Chọn format tốt nhất: video MP4 + audio, tối đa 1080p
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(output_path),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        # Không mở trình duyệt, chạy headless
        "noplaylist": True,
        # Retry settings (Hardness Engineering)
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        # Tắt geo-bypass để tránh lỗi không mong muốn
        "geo_bypass": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"yt-dlp tải thất bại [{url}]: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Lỗi không mong đợi khi dùng yt-dlp: {e}") from e

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(
            f"yt-dlp không tạo được file hợp lệ tại: {output_path}\n"
            f"URL: {url}"
        )

    return output_path

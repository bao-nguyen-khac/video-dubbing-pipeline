"""
downloader/f2_client.py — Tải video TikTok/Douyin watermark-free qua thư viện f2.

Constitution Principle II: f2 là engine chính cho Douyin/TikTok.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

# Cookie thật từ trình duyệt đã đăng nhập TikTok/Douyin — bắt buộc phải có, nếu
# không f2 tự sinh "fake msToken" và bị nền tảng từ chối (lỗi
# "msToken 内容不符合要求"). Đọc từ .env, xem .env.example để biết cách lấy cookie.
TIKTOK_COOKIE = os.environ.get("TIKTOK_COOKIE", "")
DOUYIN_COOKIE = os.environ.get("DOUYIN_COOKIE", "")


def download_video(url: str, job_dir: Path, platform: str) -> Path:
    """
    Tải video từ TikTok hoặc Douyin, lưu vào jobs/{job_id}/source.mp4.

    Args:
        url: URL công khai của video.
        job_dir: Đường dẫn thư mục job (jobs/{job_id}/).
        platform: 'tiktok' hoặc 'douyin'.

    Returns:
        Path tới file source.mp4 đã tải.

    Raises:
        RuntimeError: Nếu tải thất bại hoặc f2 không hỗ trợ URL.
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    output_path = job_dir / "source.mp4"

    # Nếu source.mp4 đã tồn tại (resume), bỏ qua tải lại
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    if platform == "tiktok":
        try:
            return _download_tiktok(url, output_path)
        except Exception as e:
            # f2 dùng API sinh msToken thật của TikTok ngay lúc import module —
            # nếu TikTok chặn theo IP/network hoặc thuật toán ký của f2 lỗi thời,
            # toàn bộ import fail trước khi chạm tới cookie. yt-dlp là fallback
            # độc lập, không phụ thuộc cơ chế msToken của f2 (Constitution Principle II)
            print(f"[f2_client] f2 tải TikTok thất bại ({e}), thử fallback yt-dlp...")
            from downloader.ytdlp_client import download_video_ytdlp
            return download_video_ytdlp(url, output_path.parent)
    elif platform == "douyin":
        return _download_douyin(url, output_path)
    else:
        raise ValueError(f"f2_client không hỗ trợ platform: {platform}")


def _download_tiktok(url: str, output_path: Path) -> Path:
    """Tải video TikTok watermark-free qua f2."""
    if not TIKTOK_COOKIE:
        raise RuntimeError(
            "Thiếu TIKTOK_COOKIE trong .env — f2 cần cookie thật để lấy msToken hợp "
            "lệ (không có cookie, TikTok từ chối token giả f2 tự sinh). "
            "Xem .env.example để biết cách lấy cookie."
        )

    try:
        from f2.apps.tiktok.handler import TiktokHandler
        from f2.apps.tiktok.model import TiktokVideo
    except ImportError as e:
        raise RuntimeError(
            "Thư viện f2 chưa được cài đặt. Chạy: pip install f2"
        ) from e

    try:
        handler = TiktokHandler(
            {
                "headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                "cookie": TIKTOK_COOKIE,
                "proxies": {},
                "timeout": 30,
                "max_retries": 3,
                "max_connections": 1,
                "path": str(output_path.parent),
                "folderize": False,
            }
        )

        async def _fetch():
            video = await handler.fetch_one_video(url)
            if not video or not video.video_play_addr:
                raise RuntimeError("f2 không lấy được play URL của video TikTok")
            await handler.downloader.create_download_task(
                handler.kwargs,
                video,
                str(output_path),
            )

        asyncio.run(_fetch())

    except Exception as e:
        raise RuntimeError(f"Tải TikTok thất bại [{url}]: {e}") from e

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"File download không hợp lệ sau khi tải: {output_path}")

    return output_path


def _download_douyin(url: str, output_path: Path) -> Path:
    """Tải video Douyin watermark-free qua f2."""
    if not DOUYIN_COOKIE:
        raise RuntimeError(
            "Thiếu DOUYIN_COOKIE trong .env — f2 cần cookie thật để lấy msToken hợp "
            "lệ. Xem .env.example để biết cách lấy cookie."
        )

    try:
        from f2.apps.douyin.handler import DouyinHandler
    except ImportError as e:
        raise RuntimeError(
            "Thư viện f2 chưa được cài đặt. Chạy: pip install f2"
        ) from e

    try:
        handler = DouyinHandler(
            {
                "headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Linux; Android 10; K) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Mobile Safari/537.36"
                    )
                },
                "cookie": DOUYIN_COOKIE,
                "proxies": {},
                "timeout": 30,
                "max_retries": 3,
                "max_connections": 1,
                "path": str(output_path.parent),
                "folderize": False,
            }
        )

        async def _fetch():
            video = await handler.fetch_one_video(url)
            if not video or not video.video_play_addr:
                raise RuntimeError("f2 không lấy được play URL của video Douyin")
            await handler.downloader.create_download_task(
                handler.kwargs,
                video,
                str(output_path),
            )

        asyncio.run(_fetch())

    except Exception as e:
        raise RuntimeError(f"Tải Douyin thất bại [{url}]: {e}") from e

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"File download không hợp lệ sau khi tải: {output_path}")

    return output_path

"""
downloader/ytdlp_client.py — Tải video qua yt-dlp (YouTube + fallback).

Constitution Principle II: yt-dlp là fallback khi f2 không hỗ trợ nguồn.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _apply_js_runtime_opts(ydl_opts: dict) -> None:
    """
    YouTube dùng "n-challenge" (chữ ký JS) để chặn tải — không có JS runtime
    giải thì yt-dlp thiếu format và báo "Requested format is not available".

    yt-dlp mặc định chỉ bật Deno; máy này dùng Node (đã cài) nên bật thêm Node
    và trỏ đúng đường dẫn để backend tìm được dù PATH lúc chạy không có nvm.
    Cần kèm package `yt-dlp-ejs` (đã ở requirements) để có sẵn script giải.

    Env:
      - YTDLP_JS_RUNTIME: tên runtime (deno/node/bun/quickjs), mặc định 'node'.
      - YTDLP_JS_RUNTIME_PATH: đường dẫn binary, ghi đè auto-detect nếu cần.
    """
    runtime = os.environ.get("YTDLP_JS_RUNTIME", "node").strip()
    if not runtime:
        return

    path = os.environ.get("YTDLP_JS_RUNTIME_PATH", "").strip()
    if not path:
        path = shutil.which(runtime) or ""
    if not path and runtime == "node":
        # Fallback đường dẫn brew ổn định khi PATH lúc chạy không có node
        for candidate in ("/opt/homebrew/bin/node", "/usr/local/bin/node"):
            if Path(candidate).exists():
                path = candidate
                break

    config = {"path": path} if path else {}
    # Giữ deno bật kèm (ưu tiên cao hơn node) — nếu sau này cài deno sẽ tự dùng,
    # còn hiện tại deno không có nên yt-dlp rơi xuống node.
    ydl_opts["js_runtimes"] = {"deno": {}, runtime: config}


def _apply_cookie_opts(ydl_opts: dict) -> None:
    """
    Thêm cấu hình cookies cho yt-dlp từ env — cần khi YouTube báo "Sign in to
    confirm you're not a bot" (bot-detection theo IP/phiên).

    Ưu tiên file cookies.txt (hợp server/VPS), rồi tới đọc trực tiếp từ trình
    duyệt (tiện khi chạy local). Không cấu hình gì → giữ nguyên hành vi cũ.

    - YTDLP_COOKIES_FILE: đường dẫn cookies.txt (Netscape format).
    - YTDLP_COOKIES_FROM_BROWSER: tên trình duyệt yt-dlp hỗ trợ, có thể kèm
      profile theo cú pháp "chrome:Default" (vd 'chrome', 'safari', 'brave',
      'firefox', 'edge').
    """
    cookies_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
        return

    from_browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if from_browser:
        # yt-dlp nhận tuple (browser, profile, keyring, container). Cho phép
        # "chrome:Default" để chỉ định profile.
        browser, _, profile = from_browser.partition(":")
        ydl_opts["cookiesfrombrowser"] = (browser, profile or None, None, None)


def _has_cookies_configured() -> bool:
    """True nếu có cấu hình cookies (file hoặc trình duyệt) trong env."""
    return bool(
        os.environ.get("YTDLP_COOKIES_FILE", "").strip()
        or os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    )


def _is_bot_check_error(message: str) -> bool:
    """
    Nhận diện lỗi YouTube đòi xác thực (bot-detection) — chỉ khi gặp lỗi này
    mới cần dùng cookies, tránh gắn hoạt động vào tài khoản khi không cần.
    """
    msg = message.lower()
    return any(
        s in msg
        for s in ("confirm you're not a bot", "confirm you’re not a bot", "sign in to confirm")
    )


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

    def _run(use_cookies: bool) -> None:
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
        _apply_js_runtime_opts(ydl_opts)
        if use_cookies:
            _apply_cookie_opts(ydl_opts)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    # Thử KHÔNG cookies trước — hầu hết video tải được mà không cần đăng nhập,
    # tránh gắn hoạt động vào tài khoản Google. Chỉ khi YouTube đòi xác thực
    # (bot-detection) mới thử lại với cookies (nên là tài khoản "nháp" riêng —
    # xem .env). Việc này giảm tối đa rủi ro cho tài khoản chính.
    try:
        _run(use_cookies=False)
    except yt_dlp.utils.DownloadError as e:
        if _is_bot_check_error(str(e)) and _has_cookies_configured():
            print(f"[ytdlp_client] YouTube đòi xác thực, thử lại với cookies: [{url}]")
            try:
                _run(use_cookies=True)
            except yt_dlp.utils.DownloadError as e2:
                raise RuntimeError(f"yt-dlp tải thất bại [{url}]: {e2}") from e2
        else:
            raise RuntimeError(f"yt-dlp tải thất bại [{url}]: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Lỗi không mong đợi khi dùng yt-dlp: {e}") from e

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(
            f"yt-dlp không tạo được file hợp lệ tại: {output_path}\n"
            f"URL: {url}"
        )

    return output_path

"""
download_registry.py — Sổ lưu các video ĐÃ TẢI (link + nguồn) để tái dùng.

Mỗi lần tải xong 1 video, ghi lại (URL đã chuẩn hoá → file source.mp4 của job
đầu tiên). Khi tạo job mới với cùng link, pipeline tra sổ này và CLONE file có
sẵn thay vì tải lại (tiết kiệm thời gian + tránh bot-check YouTube lần nữa).

Lưu ở `download_registry.json` cạnh file này. An toàn thread bằng 1 khoá chung
(job chạy trong daemon thread — xem web/backend/job_runner.py).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_REGISTRY_PATH = Path(__file__).parent / "download_registry.json"
_LOCK = threading.Lock()

# Tham số theo dõi (tracking) không ảnh hưởng nội dung video — bỏ đi để cùng 1
# video dán từ nhiều nguồn vẫn khớp nhau.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "si", "feature", "fbclid", "gclid", "_r", "_t",
    "is_from_webapp", "sender_device", "sender_web_id", "web_id",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str) -> str:
    """Chuẩn hoá URL để so khớp: hạ host về thường, bỏ fragment + tham số tracking + '/' cuối."""
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _TRACKING_PARAMS]
    )
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, "")
    )


def _read() -> dict:
    if not _REGISTRY_PATH.exists():
        return {"videos": {}}
    try:
        with open(_REGISTRY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("videos"), dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"videos": {}}


def _write(data: dict) -> None:
    tmp = _REGISTRY_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(_REGISTRY_PATH)


def lookup(url: str) -> dict | None:
    """
    Trả về entry đã lưu cho `url` nếu có VÀ file source.mp4 vẫn còn trên đĩa;
    ngược lại None (kể cả khi file đã bị xoá — để pipeline tải lại + ghi mới).
    """
    key = normalize_url(url)
    if not key:
        return None
    with _LOCK:
        entry = _read()["videos"].get(key)
    if not entry:
        return None
    src = entry.get("source_video")
    if src and Path(src).exists() and Path(src).stat().st_size > 0:
        return entry
    return None


def register(url: str, platform: str, source_video: str | Path, job_id: str) -> None:
    """Ghi/cập nhật 1 video đã tải vào sổ (giữ nguyên entry cũ nếu file vẫn tốt)."""
    key = normalize_url(url)
    if not key:
        return
    with _LOCK:
        data = _read()
        existing = data["videos"].get(key)
        # Đã có entry với file còn sống → không ghi đè (giữ nguồn gốc đầu tiên)
        if existing:
            src = existing.get("source_video")
            if src and Path(src).exists() and Path(src).stat().st_size > 0:
                return
        data["videos"][key] = {
            "url": url.strip(),
            "platform": platform,
            "source_video": str(source_video),
            "job_id": job_id,
            "created_at": _now_iso(),
        }
        _write(data)


def prune_missing() -> int:
    """Bỏ các entry trỏ tới file source không còn tồn tại. Trả số entry đã xoá."""
    with _LOCK:
        data = _read()
        videos = data["videos"]
        stale = [
            key for key, v in videos.items()
            if not (v.get("source_video") and Path(v["source_video"]).exists())
        ]
        for key in stale:
            del videos[key]
        if stale:
            _write(data)
        return len(stale)


def list_all() -> list[dict]:
    """Danh sách video đã lưu, mới nhất trước — dùng cho GET /api/downloads."""
    with _LOCK:
        videos = list(_read()["videos"].values())
    for v in videos:
        src = v.get("source_video")
        v["available"] = bool(src and Path(src).exists() and Path(src).stat().st_size > 0)
    videos.sort(key=lambda v: v.get("created_at", ""), reverse=True)
    return videos

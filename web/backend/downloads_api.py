"""
web/backend/downloads_api.py — Sổ video đã tải (link + nguồn).

Chỉ đọc lại download_registry.py — nơi pipeline ghi mỗi video đã tải để tái
dùng (clone thay vì tải lại khi tạo job mới cùng link).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_downloads():
    """GET /api/downloads — danh sách video đã tải (mới nhất trước)."""
    import download_registry

    return {"videos": download_registry.list_all()}

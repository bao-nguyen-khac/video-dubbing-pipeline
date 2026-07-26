"""
web/backend/auth.py — Kiểm tra đăng nhập từ .env, ký/verify session cookie.

Chỉ 1 cặp tài khoản duy nhất (WEB_UI_USERNAME/WEB_UI_PASSWORD) — không phải hệ
thống nhiều user (spec 002-web-ui, Clarification 2026-07-26 Q1). Phiên kéo dài
7 ngày (Clarification 2026-07-26 Q2).
"""

from __future__ import annotations

import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # 7 ngày

WEB_UI_USERNAME = os.environ.get("WEB_UI_USERNAME", "")
WEB_UI_PASSWORD = os.environ.get("WEB_UI_PASSWORD", "")
WEB_UI_SECRET_KEY = os.environ.get("WEB_UI_SECRET_KEY", "")


def _serializer() -> URLSafeTimedSerializer:
    if not WEB_UI_SECRET_KEY:
        raise RuntimeError(
            "Thiếu WEB_UI_SECRET_KEY trong .env — cần secret để ký session cookie."
        )
    return URLSafeTimedSerializer(WEB_UI_SECRET_KEY, salt="web-ui-session")


def check_credentials(username: str, password: str) -> bool:
    """So khớp với WEB_UI_USERNAME/WEB_UI_PASSWORD từ .env."""
    if not WEB_UI_USERNAME or not WEB_UI_PASSWORD:
        return False
    return username == WEB_UI_USERNAME and password == WEB_UI_PASSWORD


def create_session_token(username: str) -> str:
    """Ký session token cho username đã xác thực."""
    return _serializer().dumps({"username": username})


def verify_session_token(token: str | None) -> bool:
    """Kiểm tra session token còn hạn (7 ngày) và chữ ký hợp lệ."""
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False

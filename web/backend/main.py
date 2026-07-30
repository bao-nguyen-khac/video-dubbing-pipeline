"""
web/backend/main.py — FastAPI app: auth middleware, mount jobs API, serve React
build. Chạy bằng `uvicorn web.backend.main:app` từ repo root (xem quickstart.md).
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load .env sớm nhất có thể — trước khi auth.py đọc WEB_UI_* qua os.environ
load_dotenv()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from web.backend import auth  # noqa: E402
from web.backend.downloads_api import router as downloads_router  # noqa: E402
from web.backend.jobs_api import router as jobs_router  # noqa: E402
from web.backend.publish_api import router as publish_router  # noqa: E402
from web.backend.voices_api import router as voices_router  # noqa: E402

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Endpoint không yêu cầu session hợp lệ
PUBLIC_API_PATHS = {"/api/login"}

app = FastAPI(title="Video Repurpose Pipeline — Web UI")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Chặn mọi request /api/* (trừ PUBLIC_API_PATHS) thiếu/hết hạn session (FR-010)."""
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        token = request.cookies.get(auth.SESSION_COOKIE_NAME)
        if not auth.verify_session_token(token):
            return JSONResponse(
                status_code=401,
                content={"error": "Chưa đăng nhập hoặc phiên đã hết hạn"},
            )
    return await call_next(request)


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/login")
async def login(body: LoginRequest):
    """Kiểm tra tài khoản/mật khẩu, set session cookie 7 ngày (contracts/api.md)."""
    if not auth.check_credentials(body.username, body.password):
        return JSONResponse(
            status_code=401,
            content={"error": "Sai tài khoản hoặc mật khẩu"},
        )

    token = auth.create_session_token(body.username)
    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        auth.SESSION_COOKIE_NAME,
        token,
        max_age=auth.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/api/logout")
async def logout():
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return response


app.include_router(jobs_router, prefix="/api/jobs")
app.include_router(voices_router, prefix="/api/voices")
app.include_router(publish_router, prefix="/api/publish")
app.include_router(downloads_router, prefix="/api/downloads")

# Serve React build (nếu đã `npm run build`) làm static site tại "/"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

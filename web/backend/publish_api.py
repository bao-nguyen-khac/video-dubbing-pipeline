"""
web/backend/publish_api.py — Endpoint tab "Đăng video" (006-publish-video-tab).

Lớp HTTP mỏng: mọi logic nằm ở module publish/ (Constitution Principle I,
contracts/api.md). Không có ZERNIO_API_KEY thì mọi endpoint ở đây trả 503, phần
còn lại của ứng dụng không bị ảnh hưởng.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from media_utils import get_media_duration
from pipeline import read_job
from publish import limits, reconcile, runner, store, zernio_client
from publish.zernio_client import ZernioError
from web.backend.jobs_api import _get_output_video_path, _iter_all_jobs

router = APIRouter()

SUPPORTED_PLATFORMS = ("tiktok", "youtube")

# Chặng 1 chỉ bàn giao TikTok (plan.md → Thứ tự bàn giao); YouTube bật ở Phase 4
ENABLED_PLATFORMS = ("tiktok",)


def _error(status_code: int, message: str, **extra) -> JSONResponse:
    """Response lỗi đồng nhất `{"error": ...}` — cùng dạng với jobs_api.py."""
    return JSONResponse(status_code=status_code, content={"error": message, **extra})


def _not_configured() -> JSONResponse:
    return _error(503, "Chưa cấu hình ZERNIO_API_KEY — xem .env.example")


def _provider_error(e: ZernioError) -> JSONResponse:
    """Lỗi từ Zernio khi đang phục vụ 1 request đồng bộ."""
    status = 502
    if e.kind == "limit_exceeded":
        status = 402
    elif e.kind == "auth_expired":
        status = 401
    return _error(status, e.message, error_kind=e.kind)


def _attempt_to_public(attempt: dict) -> dict:
    """Hình dạng attempt trả ra frontend (contracts/api.md)."""
    return {
        "attempt_id": attempt["attempt_id"],
        "job_id": attempt["job_id"],
        "platform": attempt["platform"],
        "account_label": attempt.get("account_label", ""),
        "title": attempt.get("title", ""),
        "status": attempt["status"],
        "publish_mode": attempt.get("publish_mode", "now"),
        "scheduled_for": attempt.get("scheduled_for"),
        "error": attempt.get("error"),
        "error_kind": attempt.get("error_kind"),
        "post_url": attempt.get("post_url"),
        "created_at": attempt["created_at"],
        "updated_at": attempt["updated_at"],
    }


# ── Videos ──────────────────────────────────────────────────────────────────


@router.get("/videos")
async def list_publishable_videos():
    """GET /api/publish/videos — job đã xong và còn file output (FR-002)."""
    videos = []
    for job in _iter_all_jobs():
        if job.get("status") != "done":
            continue
        path = _get_output_video_path(job)
        if not path:
            continue
        videos.append(
            {
                "job_id": job["job_id"],
                "source_url": job.get("source_url", ""),
                "created_at": job.get("created_at", ""),
                "duration_seconds": round(get_media_duration(path), 1),
                "already_published_to": store.published_platforms(job["job_id"]),
            }
        )
    videos.sort(key=lambda v: v["created_at"], reverse=True)
    return {"videos": videos}


# ── Connections ─────────────────────────────────────────────────────────────


@router.get("/connections")
async def list_connections():
    """GET /api/publish/connections — kênh đã liên kết + blocklist cục bộ."""
    if not zernio_client.is_configured():
        return _not_configured()

    try:
        accounts = zernio_client.list_accounts()
    except ZernioError as e:
        return _provider_error(e)

    state = store.read_state()
    blocked = set(state.get("disconnected_account_ids", []))

    connections = []
    for account in accounts:
        platform = account.get("platform")
        if platform not in ENABLED_PLATFORMS:
            continue
        account_id = account.get("_id") or account.get("id", "")
        if account_id in blocked:
            status = "disconnected"
        elif account.get("isActive") is False:
            status = "expired"
        else:
            status = "connected"
        connections.append(
            {
                "account_id": account_id,
                "platform": platform,
                "label": account.get("username") or account.get("displayName") or account_id,
                "status": status,
            }
        )

    return {"connections": connections}


class ConnectRequest(BaseModel):
    redirect_url: str | None = None


@router.post("/connections/{platform}")
async def start_connect(platform: str, body: ConnectRequest | None = None):
    """POST /api/publish/connections/{platform} — trả authorize_url (FR-005)."""
    if not zernio_client.is_configured():
        return _not_configured()
    if platform not in ENABLED_PLATFORMS:
        return _error(400, f"Nền tảng '{platform}' chưa được hỗ trợ ở phiên bản này")

    try:
        profile_id = zernio_client.default_profile_id()
        store.set_profile_id(profile_id)
        authorize_url = zernio_client.connect_url(
            platform, profile_id, body.redirect_url if body else None
        )
    except ZernioError as e:
        return _provider_error(e)

    return {"authorize_url": authorize_url}


@router.delete("/connections/{account_id}")
async def disconnect_channel(account_id: str):
    """
    DELETE /api/publish/connections/{account_id} — ngắt kết nối (FR-011).

    Chặn cục bộ TRƯỚC (nguồn sự thật để chặn đăng), rồi mới gọi Zernio xoá liên
    kết thật. Zernio lỗi cũng không sao: kênh đã bị chặn ở phía này rồi.

    007-schedule-publish (FR-015): mọi bài đang chờ đăng của kênh này PHẢI bị
    huỷ theo — Zernio đăng bài mà không hỏi lại hệ thống này, nên chỉ chặn cục
    bộ KHÔNG đủ để ngăn bài đã hẹn lên đúng kênh vừa ngắt (research.md §6).
    """
    if not zernio_client.is_configured():
        return _not_configured()

    store.block_account(account_id)

    cancelled_attempts = []
    warnings = []
    for attempt in store.list_scheduled_by_account(account_id):
        try:
            zernio_client.delete_post(attempt["provider_post_id"])
        except ZernioError as e:
            warnings.append(f"Không huỷ được bài '{attempt['title']}': {e.message}")
            continue
        store.cancel_attempt(attempt["job_id"], attempt["attempt_id"])
        cancelled_attempts.append(
            {
                "attempt_id": attempt["attempt_id"],
                "title": attempt["title"],
                "scheduled_for": attempt["scheduled_for"],
            }
        )

    try:
        zernio_client.delete_account(account_id)
    except ZernioError as e:
        warnings.append(f"Gỡ liên kết ở Zernio thất bại: {e.message}")

    response: dict = {"ok": True, "cancelled_attempts": cancelled_attempts}
    if warnings:
        response["warning"] = "; ".join(warnings)
    return JSONResponse(status_code=200, content=response)


# ── Publish ─────────────────────────────────────────────────────────────────


class CreatePublishRequest(BaseModel):
    job_id: str
    platform: str
    account_id: str
    title: str
    # 007-schedule-publish: "now" (mặc định, tương thích ngược với 006) hoặc
    # "scheduled". scheduled_for là chuỗi ISO 8601 UTC (client tự quy đổi từ
    # giờ Việt Nam trước khi gửi — xem web/frontend/src/lib/labels.ts)
    publish_mode: str = "now"
    scheduled_for: str | None = None


@router.post("", status_code=202)
async def create_publish(body: CreatePublishRequest):
    """POST /api/publish — tạo 1 lượt đăng, xử lý thật chạy nền (FR-007)."""
    if not zernio_client.is_configured():
        return _not_configured()

    title = body.title.strip()
    if not title:
        return _error(400, "Tiêu đề là bắt buộc")

    if body.platform not in ENABLED_PLATFORMS:
        return _error(400, f"Nền tảng '{body.platform}' chưa được hỗ trợ ở phiên bản này")

    if body.publish_mode not in ("now", "scheduled"):
        return _error(400, "publish_mode phải là 'now' hoặc 'scheduled'")

    scheduled_for_dt = None
    if body.publish_mode == "scheduled":
        if not body.scheduled_for:
            return _error(400, "Thiếu thời điểm hẹn giờ")
        try:
            scheduled_for_dt = datetime.fromisoformat(body.scheduled_for.replace("Z", "+00:00"))
        except ValueError:
            return _error(400, "Thời điểm hẹn giờ không đúng định dạng")

        schedule_error = limits.check_schedule_time(scheduled_for_dt)
        if schedule_error:
            return _error(400, schedule_error)

    try:
        job = read_job(body.job_id)
    except FileNotFoundError:
        return _error(400, "Job không tồn tại")

    if job.get("status") != "done":
        return _error(400, "Job chưa xử lý xong, chưa có video để đăng")

    video_path = _get_output_video_path(job)
    if not video_path:
        return _error(400, "Job chưa có video kết quả để đăng")

    if store.is_blocked(body.account_id):
        return _error(403, "Kênh đã bị ngắt kết nối, hãy liên kết lại trước khi đăng")

    active = store.find_active_attempt(body.job_id, body.platform)
    if active:
        message = (
            "Video này đã có bài đang chờ đăng lên nền tảng đã chọn"
            if active.get("status") == "scheduled"
            else "Video này đang được đăng lên nền tảng đã chọn"
        )
        return _error(409, message, attempt_id=active["attempt_id"])

    # Giới hạn nền tảng: chặn TRƯỚC khi upload để không tốn 1 lượt tải lên
    max_duration = None
    if body.platform == "tiktok":
        try:
            info = zernio_client.tiktok_creator_info(body.account_id)
            max_duration = (info.get("postingLimits") or {}).get("maxVideoDurationSec")
        except ZernioError:
            # Không lấy được giới hạn động thì dùng ngưỡng mặc định
            max_duration = None

    limit_error = limits.check_limits(body.platform, video_path, max_duration)
    if limit_error:
        return _error(400, limit_error)

    account_label = body.account_id
    try:
        for account in zernio_client.list_accounts(body.platform):
            if (account.get("_id") or account.get("id")) == body.account_id:
                account_label = (
                    account.get("username") or account.get("displayName") or body.account_id
                )
                break
    except ZernioError:
        # Không lấy được tên kênh thì vẫn đăng được — chỉ mất nhãn đẹp ở lịch sử
        pass

    attempt = store.create_attempt(
        job_id=body.job_id,
        platform=body.platform,
        account_id=body.account_id,
        account_label=account_label,
        title=title,
        publish_mode=body.publish_mode,
        scheduled_for=body.scheduled_for,
    )
    runner.start_publish(attempt, str(video_path))

    return {"attempt_id": attempt["attempt_id"], "status": attempt["status"]}


@router.get("/attempts")
async def list_publish_attempts(job_id: str | None = None, status: str | None = None):
    """
    GET /api/publish/attempts — lịch sử lượt đăng (FR-010).

    Mỗi attempt được đối soát lười (T009/T016) trước khi trả về (FR-009).
    `?status=scheduled` cho giao diện lấy riêng danh sách đang chờ đăng, sắp
    theo `scheduled_for` tăng dần (gần nhất trước) thay vì `created_at` giảm
    dần như lịch sử chung (contracts/api.md).
    """
    attempts = [reconcile.reconcile_if_needed(a) for a in store.list_attempts(job_id)]

    if status:
        attempts = [a for a in attempts if a.get("status") == status]

    if status == "scheduled":
        attempts.sort(key=lambda a: a.get("scheduled_for") or "")

    return {"attempts": [_attempt_to_public(a) for a in attempts]}


@router.get("/attempts/{attempt_id}")
async def get_publish_attempt(attempt_id: str):
    """GET /api/publish/attempts/{attempt_id} — frontend poll khi đang đăng."""
    attempt = store.find_attempt(attempt_id)
    if not attempt:
        return _error(404, "Lượt đăng không tồn tại")
    attempt = reconcile.reconcile_if_needed(attempt)
    return _attempt_to_public(attempt)


@router.delete("/attempts/{attempt_id}")
async def cancel_publish_attempt(attempt_id: str):
    """
    DELETE /api/publish/attempts/{attempt_id} — huỷ 1 bài đang chờ đăng
    (FR-011, FR-012).

    Thứ tự BẮT BUỘC: gọi Zernio huỷ trước, ghi 'cancelled' vào file sau
    (research.md §5) — ghi trước khi huỷ thật xong là nói dối người dùng về
    một hành động không đảo ngược được.
    """
    if not zernio_client.is_configured():
        return _not_configured()

    attempt = store.find_attempt(attempt_id)
    if not attempt:
        return _error(404, "Lượt đăng không tồn tại")

    attempt = reconcile.reconcile_if_needed(attempt)
    status = attempt.get("status")

    if status == "publishing":
        return _error(409, "Bài đang được đăng, không huỷ được nữa")
    if status != "scheduled":
        return _error(
            409, "Bài đã đăng rồi, không huỷ được từ đây — xoá trực tiếp trên nền tảng"
        )

    try:
        zernio_client.delete_post(attempt["provider_post_id"])
    except ZernioError as e:
        if e.kind == "platform_rejected":
            # Zernio xác nhận bài đã đăng rồi (400) — đây là kết quả rõ ràng,
            # không phải sự cố dịch vụ trung gian, nên trả 409 như FR-012 thay
            # vì 502 mặc định của _provider_error() (contracts/api.md)
            return _error(409, e.message)
        return _provider_error(e)

    store.cancel_attempt(attempt["job_id"], attempt_id)
    return {"ok": True}

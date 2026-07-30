"""
publish/reconcile.py — Đối soát lười trạng thái lượt đăng với Zernio
(007-schedule-publish, FR-009, research.md §4).

Không có tiến trình quét nền: đối soát chạy đúng lúc giao diện đọc dữ liệu
(GET /api/publish/attempts[/{id}]). Attempt "scheduled" mà CHƯA tới giờ thì
chắc chắn trạng thái chưa đổi — gọi Zernio lúc đó chỉ tốn quota vô ích. Chỉ 2
điều kiện đáng gọi:

1. status == "scheduled" và đã qua scheduled_for (trừ hao 1 phút)
2. status == "publishing" (trạng thái chuyển tiếp, luôn cần soát)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from publish import store, zernio_client
from publish.zernio_client import ZernioError

# Trừ hao cho lệch đồng hồ giữa hệ thống này và Zernio, và cho việc Zernio có
# thể mất vài chục giây để chuyển "scheduled" -> "publishing" đúng lúc tới giờ.
_DUE_GRACE = timedelta(minutes=1)

_SUCCESS_STATUS = "published"
_FAILED_STATUSES = ("failed", "partial", "cancelled")


def needs_reconcile(attempt: dict, now: datetime | None = None) -> bool:
    """True nếu attempt này đáng gọi Zernio để lấy trạng thái mới nhất."""
    status = attempt.get("status")

    if status == "publishing":
        return True

    if status != "scheduled":
        return False

    scheduled_for = attempt.get("scheduled_for")
    if not scheduled_for:
        return False

    due_at = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00")) - _DUE_GRACE
    reference = now or datetime.now(timezone.utc)
    return reference >= due_at


def reconcile_attempt(attempt: dict) -> dict:
    """
    Gọi Zernio lấy trạng thái thật và cập nhật file nếu có thay đổi
    (data-model.md §2). Lỗi gọi Zernio thì GIỮ NGUYÊN trạng thái cũ — một lượt
    đối soát thất bại không có nghĩa là bài đã hỏng, chỉ là chưa biết được kết
    quả (khác hẳn nhánh "now" của runner, nơi timeout mới coi là thất bại thật
    sự vì đã có giới hạn 10 phút để chờ).
    """
    post_id = attempt.get("provider_post_id")
    if not post_id:
        return attempt

    try:
        post = zernio_client.get_post(post_id)
    except ZernioError:
        return attempt

    return apply_post_to_attempt(attempt, post)


def apply_post_to_attempt(attempt: dict, post: dict) -> dict:
    """
    Cập nhật attempt cục bộ theo trạng thái THẬT của 1 bài Zernio đã lấy sẵn.

    Tách riêng khỏi `reconcile_attempt` để dùng chung cho cả đối soát lười (gọi
    `get_post` từng bài) LẪN sync hàng loạt (lấy 1 lần qua `list_posts` rồi map
    theo id) — cùng logic ánh xạ, không lặp code. Chỉ ghi file khi có thay đổi
    thật (tránh cập nhật updated_at vô ích).
    """
    job_id = attempt["job_id"]
    attempt_id = attempt["attempt_id"]
    status = post.get("status")

    if status == _SUCCESS_STATUS:
        return store.update_attempt(
            job_id,
            attempt_id,
            status="success",
            post_url=zernio_client.post_url_from(post),
            error=None,
            error_kind=None,
        )

    if status in _FAILED_STATUSES:
        reason = zernio_client.platform_failure_reason(post)
        detail = f": {reason}" if reason else ""
        return store.update_attempt(
            job_id,
            attempt_id,
            status="failed",
            error=f"Nền tảng từ chối bài đăng (trạng thái '{status}'){detail}",
            error_kind="platform_rejected",
        )

    if status == "scheduled":
        # Đồng bộ luôn giờ hẹn nếu bị sửa bên Zernio (reschedule) — đây là lý do
        # chính người dùng cần sync về (chỉnh lịch trực tiếp trên Zernio).
        remote_when = post.get("scheduledFor")
        fields: dict = {}
        if attempt.get("status") == "publishing":
            fields["status"] = "scheduled"  # Zernio lùi lại, hiếm
        if remote_when and remote_when != attempt.get("scheduled_for"):
            fields["scheduled_for"] = remote_when
        if fields:
            return store.update_attempt(job_id, attempt_id, **fields)
        return attempt

    if status == "publishing" and attempt.get("status") != "publishing":
        return store.update_attempt(job_id, attempt_id, status="publishing")

    # Không đổi — không ghi lại
    return attempt


def reconcile_if_needed(attempt: dict) -> dict:
    """Tiện ích gộp: đối soát nếu cần, trả về attempt (đã cập nhật hoặc không)."""
    if needs_reconcile(attempt):
        return reconcile_attempt(attempt)
    return attempt

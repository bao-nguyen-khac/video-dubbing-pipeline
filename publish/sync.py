"""
publish/sync.py — Đồng bộ hàng loạt trạng thái lượt đăng với Zernio.

Khác đối soát lười (reconcile.py, gọi GET /posts/{id} từng bài đúng lúc UI đọc):
sync lấy TOÀN BỘ bài qua 1 lần list_posts (phân trang) rồi map theo id — 1 call
thay vì N call. Bắt được cả thay đổi người dùng chỉnh THẲNG trên Zernio: đổi
giờ hẹn (reschedule), bài đã đăng/thất bại, và bài bị xoá bên đó.

Phạm vi: chỉ các attempt do app này tạo (khớp `provider_post_id` = Zernio
post `_id`). Không kéo về bài tạo trực tiếp trên Zernio (không gắn job nào).
"""

from __future__ import annotations

from publish import reconcile, store, zernio_client
from publish.zernio_client import ZernioError

# Chỉ những attempt còn "sống" mới cần soát — bài đã success/failed/cancelled là
# trạng thái cuối, không đổi nữa (trừ khi Zernio báo khác, hiếm).
_SYNCABLE_STATUSES = ("pending", "publishing", "scheduled")


def sync_attempts(job_id: str | None = None) -> dict:
    """
    Đồng bộ trạng thái mọi attempt (hoặc của 1 job) với Zernio.

    Returns:
        {"checked": int, "updated": int, "cancelled": int, "attempts": [...]}
        `attempts` là bản ghi đã đối soát (để UI cập nhật ngay không cần gọi lại).

    Raises:
        ZernioError: nếu list_posts thất bại (mất kết nối/auth) — UI báo lỗi rõ.
    """
    all_attempts = store.list_attempts(job_id)
    syncable = [
        a for a in all_attempts
        if a.get("provider_post_id") and a.get("status") in _SYNCABLE_STATUSES
    ]

    if not syncable:
        return {"checked": 0, "updated": 0, "cancelled": 0, "attempts": all_attempts}

    # 1 lần lấy hết bài "zernio" rồi map theo id (nguồn sự thật cho đối soát)
    posts_by_id = {
        p.get("_id"): p for p in zernio_client.iter_all_posts(source="zernio") if p.get("_id")
    }

    updated = 0
    cancelled = 0
    for attempt in syncable:
        post_id = attempt["provider_post_id"]
        post = posts_by_id.get(post_id)

        if post is not None:
            new_attempt = reconcile.apply_post_to_attempt(attempt, post)
            if new_attempt.get("updated_at") != attempt.get("updated_at"):
                updated += 1
            continue

        # Không có trong danh sách → xác nhận bằng 1 lần get_post (tránh huỷ nhầm
        # do trần phân trang / bài quá cũ). 404 = đã xoá bên Zernio → huỷ cục bộ.
        try:
            confirmed = zernio_client.get_post(post_id)
        except ZernioError as e:
            if e.kind == "not_found" and attempt.get("status") == "scheduled":
                store.cancel_attempt(attempt["job_id"], attempt["attempt_id"])
                cancelled += 1
            continue
        new_attempt = reconcile.apply_post_to_attempt(attempt, confirmed)
        if new_attempt.get("updated_at") != attempt.get("updated_at"):
            updated += 1

    return {
        "checked": len(syncable),
        "updated": updated,
        "cancelled": cancelled,
        "attempts": store.list_attempts(job_id),
    }

"""
publish/runner.py — Chạy 1 lượt đăng trong thread nền.

Cùng mô hình với web/backend/job_runner.py: request HTTP trả về ngay, trạng thái
thật luôn nằm trong file (jobs/{job_id}/publishes/{attempt_id}.json), không phải
trong biến in-memory — backend restart giữa chừng vẫn audit lại được.
"""

from __future__ import annotations

import threading
import time

from publish import store, zernio_client
from publish.zernio_client import ZernioError

POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 600.0  # 10 phút

# Trạng thái post của Zernio (contracts/api.md)
_SUCCESS_STATUS = "published"
_FAILED_STATUSES = ("failed", "partial", "cancelled")


def start_publish(attempt: dict, video_path: str) -> None:
    """Spawn daemon thread chạy 1 lượt đăng. Không trả về gì."""
    thread = threading.Thread(
        target=_run_and_swallow,
        args=(attempt, video_path),
        daemon=True,
    )
    thread.start()


def _run_and_swallow(attempt: dict, video_path: str) -> None:
    """Không để exception nào làm chết thread im lặng (SC-004)."""
    try:
        run_publish(attempt, video_path)
    except Exception as e:  # noqa: BLE001 — chốt chặn cuối
        print(f"[publish.runner] Lỗi không mong đợi khi đăng: {e}")
        _fail(attempt, "unknown", f"Lỗi không mong đợi khi đăng: {e}")


def run_publish(attempt: dict, video_path: str) -> dict:
    """
    Điều phối theo `attempt["publish_mode"]` (007-schedule-publish).

    - "now" (mặc định, 006): pending → publishing → success/failed, poll tới
      khi có kết quả hoặc hết 10 phút.
    - "scheduled": pending → scheduled, rồi DỪNG NGAY — Zernio giữ bài và tự
      đăng khi tới giờ, hệ thống này không cần chạy vào lúc đó. Trạng thái thật
      sau đó được cập nhật qua đối soát lười (publish/reconcile.py), KHÔNG bao
      giờ qua poll ở đây.

    Tách khỏi thread để test gọi trực tiếp được (đồng bộ) với client đã mock.
    """
    job_id = attempt["job_id"]
    attempt_id = attempt["attempt_id"]
    platform = attempt["platform"]
    scheduled_for = attempt.get("scheduled_for")

    try:
        media_url = zernio_client.upload_video(video_path)

        privacy_level = "PUBLIC_TO_EVERYONE"
        if platform == "tiktok":
            privacy_level = _resolve_tiktok_privacy_level(attempt["account_id"])

        post = zernio_client.create_post(
            platform=platform,
            account_id=attempt["account_id"],
            title=attempt["title"],
            media_url=media_url,
            request_id=attempt_id,
            tiktok_privacy_level=privacy_level,
            scheduled_for=scheduled_for,
        )
    except ZernioError as e:
        return _fail(attempt, e.kind, e.message)

    post_id = post.get("_id") or post.get("id")

    if attempt.get("publish_mode") == "scheduled":
        # Zernio đã nhận bài — KHÔNG poll. Bài hẹn 3 ngày sau vẫn ở trạng thái
        # "scheduled" suốt khoảng đó; nếu poll như nhánh "now" thì sau 10 phút
        # sẽ bị _poll_until_done() đánh nhầm thành "failed" dù vẫn đang chờ
        # đăng bình thường (bug đã phát hiện thật, xem research.md §3 — đây
        # chính là lý do 2 nhánh phải tách hẳn, không dùng chung code).
        return store.update_attempt(
            job_id, attempt_id, status="scheduled", provider_post_id=post_id
        )

    store.update_attempt(
        job_id, attempt_id, status="publishing", provider_post_id=post_id
    )

    return _poll_until_done(attempt, post, post_id)


def _resolve_tiktok_privacy_level(account_id: str) -> str:
    """
    Chọn mức riêng tư công khai đúng như TikTok cho phép với chính tài khoản đó.

    Nếu PUBLIC_TO_EVERYONE không nằm trong danh sách trả về, dừng lại báo lỗi —
    thà không đăng còn hơn đăng ngầm thành video riêng tư (SC-005).
    """
    try:
        info = zernio_client.tiktok_creator_info(account_id)
    except ZernioError:
        # Không lấy được creator-info không đáng để chặn lượt đăng: gửi mức công
        # khai mặc định, TikTok sẽ từ chối rõ ràng nếu không hợp lệ
        return "PUBLIC_TO_EVERYONE"

    levels = [lv.get("value") for lv in info.get("privacyLevels", []) or []]
    if levels and "PUBLIC_TO_EVERYONE" not in levels:
        raise ZernioError(
            "platform_rejected",
            "Tài khoản TikTok này hiện không cho phép đăng công khai "
            f"(TikTok chỉ cho: {', '.join(filter(None, levels))}). "
            "Kiểm tra lại cài đặt tài khoản trên TikTok rồi thử lại.",
            info,
        )

    creator = info.get("creator") or {}
    if creator.get("canPostMore") is False:
        raise ZernioError(
            "platform_rejected",
            "Tài khoản TikTok đã chạm giới hạn số bài đăng của hôm nay — thử lại sau",
            info,
        )

    return "PUBLIC_TO_EVERYONE"


def _poll_until_done(attempt: dict, post: dict, post_id: str | None) -> dict:
    job_id = attempt["job_id"]
    attempt_id = attempt["attempt_id"]

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    current = post

    while True:
        status = current.get("status")

        if status == _SUCCESS_STATUS:
            return store.update_attempt(
                job_id,
                attempt_id,
                status="success",
                post_url=zernio_client.post_url_from(current),
                error=None,
                error_kind=None,
            )

        if status in _FAILED_STATUSES:
            reason = zernio_client.platform_failure_reason(current)
            detail = f": {reason}" if reason else ""
            return _fail(
                attempt,
                "platform_rejected",
                f"Nền tảng từ chối bài đăng (trạng thái '{status}'){detail}",
            )

        if time.monotonic() >= deadline or not post_id:
            return _fail(
                attempt,
                "provider_unavailable",
                "Quá thời gian chờ kết quả đăng (10 phút) — kiểm tra lại trên kênh "
                "trước khi đăng lại để tránh đăng trùng",
            )

        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            current = zernio_client.get_post(post_id)
        except ZernioError as e:
            # Lỗi lúc poll chưa chắc là lỗi đăng — chỉ bỏ cuộc khi hết hạn chờ
            if time.monotonic() >= deadline:
                return _fail(attempt, e.kind, e.message)


def _fail(attempt: dict, kind: str, message: str) -> dict:
    return store.update_attempt(
        attempt["job_id"],
        attempt["attempt_id"],
        status="failed",
        error=message,
        error_kind=kind,
    )

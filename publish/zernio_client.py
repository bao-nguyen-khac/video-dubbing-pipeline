"""
publish/zernio_client.py — Adapter DUY NHẤT gọi API Zernio.

Mọi ánh xạ tên trường của provider nằm gọn trong file này (contracts/api.md →
"Schema Zernio đã xác minh"), nên đổi provider/đổi schema chỉ sửa 1 chỗ.

⚠️ Constitution §VI: mọi hàm ở đây gọi thật ra ngoài — tốn chi phí thật và
create_post() tạo bài đăng CÔNG KHAI thật. Test tự động PHẢI mock transport.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://zernio.com/api/v1"

# Gọi API thường nhanh; riêng PUT file video lên object storage cần rộng tay
API_TIMEOUT = 30.0
UPLOAD_TIMEOUT = 900.0


class ZernioError(RuntimeError):
    """
    Lỗi đã phân loại từ Zernio.

    `kind` là giá trị dùng cho attempt.error_kind (data-model.md §1):
    auth_expired | duplicate_content | platform_rejected | provider_unavailable
    | limit_exceeded | network | unknown
    """

    def __init__(self, kind: str, message: str, raw: dict | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.raw = raw or {}


def base_url() -> str:
    return os.environ.get("ZERNIO_BASE_URL") or DEFAULT_BASE_URL


def api_key() -> str:
    return os.environ.get("ZERNIO_API_KEY", "")


def is_configured() -> bool:
    """Chưa có key thì tab Đăng video báo chưa cấu hình, phần còn lại vẫn chạy."""
    return bool(api_key())


def _client(timeout: float = API_TIMEOUT) -> httpx.Client:
    return httpx.Client(
        base_url=base_url(),
        headers={"Authorization": f"Bearer {api_key()}"},
        timeout=timeout,
    )


def _raise_for_response(response: httpx.Response) -> None:
    """Ánh xạ lỗi HTTP của Zernio sang ZernioError (contracts/api.md)."""
    if response.is_success:
        return

    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}

    status = response.status_code
    message = body.get("error") or f"Zernio trả lỗi HTTP {status}"
    code = body.get("code")
    err_type = body.get("type")

    if status == 401:
        raise ZernioError(
            "auth_expired",
            "Zernio từ chối API key (401) — kiểm tra lại ZERNIO_API_KEY trong .env",
            body,
        )

    if status == 403:
        if code == "ACCOUNT_DISCONNECTED":
            raise ZernioError(
                "auth_expired",
                "Kênh đã mất kết nối hoặc quyền truy cập hết hạn — hãy liên kết lại kênh rồi đăng lại",
                body,
            )
        if code == "PROFILE_OVER_LIMIT":
            raise ZernioError(
                "limit_exceeded",
                "Tài khoản Zernio đã vượt hạn mức profile của gói đang dùng",
                body,
            )
        raise ZernioError("unknown", f"Zernio từ chối yêu cầu (403): {message}", body)

    if status == 402:
        raise ZernioError(
            "limit_exceeded",
            f"Tài khoản Zernio cần bổ sung thanh toán/hạn mức trước khi tiếp tục: {message}",
            body,
        )

    if status == 409:
        details = body.get("details") or {}
        raise ZernioError(
            "duplicate_content",
            "Nội dung này đã được đăng lên chính kênh đó trong 24 giờ qua "
            f"(bài cũ: {details.get('existingPostId', 'không rõ id')}). "
            "Đổi tiêu đề nếu bạn thật sự muốn đăng lại.",
            body,
        )

    if status == 429:
        retry_after = response.headers.get("Retry-After")
        suffix = f" Thử lại sau {retry_after}s." if retry_after else ""
        raise ZernioError(
            "provider_unavailable",
            f"Zernio/nền tảng đang giới hạn tần suất đăng: {message}.{suffix}",
            body,
        )

    if status >= 500:
        raise ZernioError(
            "provider_unavailable",
            f"Dịch vụ đăng bài Zernio đang gặp sự cố (HTTP {status}) — "
            "lỗi ở phía dịch vụ trung gian, không phải video hay tài khoản của bạn",
            body,
        )

    if err_type == "platform_error":
        platform = body.get("platform", "nền tảng")
        raise ZernioError("platform_rejected", f"{platform} từ chối bài đăng: {message}", body)

    raise ZernioError("unknown", f"Zernio trả lỗi (HTTP {status}): {message}", body)


def _request(method: str, path: str, **kwargs) -> dict:
    try:
        with _client() as client:
            response = client.request(method, path, **kwargs)
    except httpx.TimeoutException as e:
        raise ZernioError(
            "provider_unavailable",
            "Gọi Zernio quá thời gian chờ — dịch vụ trung gian không phản hồi",
            {"exception": str(e)},
        ) from e
    except httpx.HTTPError as e:
        raise ZernioError(
            "provider_unavailable",
            f"Không kết nối được tới dịch vụ đăng bài Zernio: {e}",
            {"exception": str(e)},
        ) from e

    _raise_for_response(response)
    try:
        return response.json()
    except ValueError:
        return {}


# ── Profiles & accounts ─────────────────────────────────────────────────────


def list_profiles() -> list[dict]:
    return _request("GET", "/profiles").get("profiles", [])


def default_profile_id() -> str:
    """
    Profile dùng cho luồng liên kết kênh (GET /connect/{platform} bắt buộc có).

    Ưu tiên ZERNIO_PROFILE_ID trong .env, sau đó profile isDefault, cuối cùng là
    profile đầu tiên của tài khoản.
    """
    env_profile = os.environ.get("ZERNIO_PROFILE_ID", "").strip()
    if env_profile:
        return env_profile

    profiles = list_profiles()
    if not profiles:
        raise ZernioError(
            "unknown",
            "Tài khoản Zernio chưa có profile nào — tạo 1 profile trên dashboard Zernio trước",
        )
    for profile in profiles:
        if profile.get("isDefault"):
            return profile["_id"]
    return profiles[0]["_id"]


def list_accounts(platform: str | None = None) -> list[dict]:
    """Kênh đã liên kết. Mỗi phần tử: _id, platform, username, displayName, isActive."""
    params = {"platform": platform} if platform else None
    return _request("GET", "/accounts", params=params).get("accounts", [])


def connect_url(platform: str, profile_id: str, redirect_url: str | None = None) -> str:
    """URL OAuth để người dùng cấp quyền trên chính nền tảng đích (FR-005)."""
    params: dict[str, str] = {"profileId": profile_id}
    if redirect_url:
        params["redirect_url"] = redirect_url
    body = _request("GET", f"/connect/{platform}", params=params)
    auth_url = body.get("authUrl")
    if not auth_url:
        raise ZernioError("unknown", "Zernio không trả về authUrl để liên kết kênh", body)
    return auth_url


def delete_account(account_id: str) -> None:
    """Ngắt liên kết kênh phía Zernio (FR-011)."""
    _request("DELETE", f"/accounts/{account_id}")


def tiktok_creator_info(account_id: str) -> dict:
    """
    Thông tin creator TikTok: các privacyLevel hợp lệ + giới hạn thời lượng.

    Cần để đảm bảo đăng CÔNG KHAI đúng cách (SC-005): privacyLevel gửi đi phải
    nằm trong danh sách nền tảng trả về cho chính tài khoản đó.
    """
    return _request("GET", f"/accounts/{account_id}/tiktok/creator-info", params={"mediaType": "video"})


# ── Media ───────────────────────────────────────────────────────────────────


def upload_video(video_path: str | Path) -> str:
    """
    Upload video và trả publicUrl dùng được trong mediaItems.

    2 bước theo đúng thiết kế của Zernio: xin presigned URL rồi PUT thẳng file
    lên object storage (hỗ trợ tới 5GB; endpoint multipart /media/upload-direct
    chỉ tới 25MB nên không dùng cho video).
    """
    path = Path(video_path)
    size = path.stat().st_size

    presign = _request(
        "POST",
        "/media/presign",
        json={"filename": path.name, "contentType": "video/mp4", "size": size},
    )
    upload_url = presign.get("uploadUrl")
    public_url = presign.get("publicUrl")
    if not upload_url or not public_url:
        raise ZernioError("unknown", "Zernio không trả về link upload hợp lệ", presign)

    try:
        with open(path, "rb") as f:
            # PUT thẳng lên object storage — KHÔNG kèm Authorization của Zernio
            response = httpx.put(
                upload_url,
                content=f,
                headers={"Content-Type": "video/mp4"},
                timeout=UPLOAD_TIMEOUT,
            )
    except httpx.HTTPError as e:
        raise ZernioError(
            "network",
            f"Tải video lên kho lưu trữ thất bại: {e}",
            {"exception": str(e)},
        ) from e

    if not response.is_success:
        raise ZernioError(
            "network",
            f"Tải video lên kho lưu trữ thất bại (HTTP {response.status_code})",
            {"status": response.status_code},
        )

    return public_url


# ── Posts ───────────────────────────────────────────────────────────────────


def build_post_payload(
    platform: str,
    account_id: str,
    title: str,
    media_url: str,
    tiktok_privacy_level: str = "PUBLIC_TO_EVERYONE",
) -> dict:
    """
    Body POST /posts cho 1 video, đăng công khai ngay.

    Chế độ hiển thị công khai LUÔN đặt tường minh (research.md §3) — không để
    mặc định của provider quyết định, tránh "thành công giả" (video riêng tư mà
    người dùng tưởng đã công khai).
    """
    media_item = {"type": "video", "url": media_url, "mimeType": "video/mp4"}
    payload: dict = {
        "content": title,
        "mediaItems": [media_item],
        "publishNow": True,
    }

    if platform == "tiktok":
        payload["platforms"] = [{"platform": "tiktok", "accountId": account_id}]
        # draft KHÔNG được set: draft=true đẩy bài vào Creator Inbox thay vì
        # đăng công khai (trái SC-005). allowDuet/allowStitch bắt buộc với video.
        payload["tiktokSettings"] = {
            "privacyLevel": tiktok_privacy_level,
            "allowComment": True,
            "allowDuet": True,
            "allowStitch": True,
            "contentPreviewConfirmed": True,
            "expressConsentGiven": True,
        }
    elif platform == "youtube":
        payload["platforms"] = [
            {
                "platform": "youtube",
                "accountId": account_id,
                "platformSpecificData": {
                    # YouTube giới hạn tiêu đề 100 ký tự
                    "title": title[:100],
                    "privacyStatus": "public",
                    "madeForKids": False,
                },
            }
        ]
    else:
        raise ZernioError("unknown", f"Nền tảng không hỗ trợ: {platform}")

    return payload


def create_post(
    platform: str,
    account_id: str,
    title: str,
    media_url: str,
    request_id: str,
    tiktok_privacy_level: str = "PUBLIC_TO_EVERYONE",
) -> dict:
    """
    Tạo bài đăng công khai ngay. `request_id` đi vào header x-request-id để một
    lần retry mạng không sinh 2 bài (contracts/api.md → Idempotency).

    Trả về post dict (`_id`, `status`, `platforms[]`).
    """
    payload = build_post_payload(platform, account_id, title, media_url, tiktok_privacy_level)
    body = _request("POST", "/posts", json=payload, headers={"x-request-id": request_id})
    # Retry cùng x-request-id trả 200 kèm existingPost thay vì post
    post = body.get("post") or body.get("existingPost")
    if not post:
        raise ZernioError("unknown", "Zernio không trả về thông tin bài đăng", body)
    return post


def get_post(post_id: str) -> dict:
    body = _request("GET", f"/posts/{post_id}")
    post = body.get("post") or body
    if not isinstance(post, dict) or not post.get("status"):
        raise ZernioError("unknown", "Zernio trả về trạng thái bài đăng không hợp lệ", body)
    return post


def post_url_from(post: dict) -> str | None:
    """Link bài đăng trên nền tảng (platformPostUrl của mục platform đầu tiên)."""
    for entry in post.get("platforms", []) or []:
        url = entry.get("platformPostUrl")
        if url:
            return url
    return None


def platform_failure_reason(post: dict) -> str | None:
    """Lý do thất bại do nền tảng trả về, nếu có."""
    for entry in post.get("platforms", []) or []:
        if entry.get("status") in ("failed", "error"):
            return entry.get("error") or entry.get("failureReason") or entry.get("message")
    return None

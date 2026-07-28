"""
tests/unit/test_zernio_client.py — Ánh xạ lỗi + payload gửi Zernio.

⚠️ Constitution §VI: KHÔNG test nào được gọi thật tới zernio.com — mọi request
đi qua httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from publish import zernio_client
from publish.zernio_client import ZernioError


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "sk_test")
    monkeypatch.delenv("ZERNIO_PROFILE_ID", raising=False)


def mock_client(handler):
    """Thay _client() bằng client dùng MockTransport."""

    def factory(timeout: float = zernio_client.API_TIMEOUT):
        return httpx.Client(
            base_url=zernio_client.base_url(),
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    return factory


def respond(monkeypatch, status_code: int, json_body: dict, headers: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body, headers=headers or {})

    monkeypatch.setattr(zernio_client, "_client", mock_client(handler))


# ── Ánh xạ lỗi (contracts/api.md) ───────────────────────────────────────────


def test_401_la_auth_expired(monkeypatch):
    respond(monkeypatch, 401, {"error": "Unauthorized"})

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "auth_expired"


def test_403_account_disconnected_la_auth_expired(monkeypatch):
    respond(monkeypatch, 403, {"error": "disconnected", "code": "ACCOUNT_DISCONNECTED"})

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "auth_expired"
    assert "liên kết lại" in e.value.message


def test_403_profile_over_limit_la_limit_exceeded(monkeypatch):
    respond(monkeypatch, 403, {"error": "over limit", "code": "PROFILE_OVER_LIMIT"})

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "limit_exceeded"


def test_402_la_limit_exceeded(monkeypatch):
    respond(monkeypatch, 402, {"error": "free_tier_exceeded"})

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "limit_exceeded"


def test_409_la_duplicate_content(monkeypatch):
    respond(
        monkeypatch,
        409,
        {"error": "duplicate", "details": {"existingPostId": "post-1"}},
    )

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "duplicate_content"
    assert "post-1" in e.value.message


def test_429_la_provider_unavailable_kem_retry_after(monkeypatch):
    respond(monkeypatch, 429, {"error": "rate limited"}, headers={"Retry-After": "30"})

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "provider_unavailable"
    assert "30" in e.value.message


def test_500_la_provider_unavailable(monkeypatch):
    respond(monkeypatch, 500, {"error": "boom"})

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "provider_unavailable"
    # Thông báo phải nói rõ lỗi ở phía dịch vụ trung gian (Edge Case spec.md)
    assert "trung gian" in e.value.message


def test_platform_error_la_platform_rejected(monkeypatch):
    respond(
        monkeypatch,
        400,
        {"error": "video too long", "type": "platform_error", "platform": "tiktok"},
    )

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "platform_rejected"


def test_timeout_la_provider_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    monkeypatch.setattr(zernio_client, "_client", mock_client(handler))

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "provider_unavailable"


def test_loi_khong_ro_la_unknown(monkeypatch):
    respond(monkeypatch, 418, {"error": "teapot"})

    with pytest.raises(ZernioError) as e:
        zernio_client.list_accounts()
    assert e.value.kind == "unknown"


# ── Payload đăng bài (SC-005: luôn công khai, tường minh) ───────────────────


def test_payload_tiktok_dang_cong_khai_khong_draft():
    payload = zernio_client.build_post_payload(
        "tiktok", "acc-1", "Tiêu đề", "https://media/x.mp4"
    )

    assert payload["publishNow"] is True
    assert payload["content"] == "Tiêu đề"
    assert payload["mediaItems"][0] == {
        "type": "video",
        "url": "https://media/x.mp4",
        "mimeType": "video/mp4",
    }
    settings = payload["tiktokSettings"]
    assert settings["privacyLevel"] == "PUBLIC_TO_EVERYONE"
    # draft=true đẩy bài vào Creator Inbox thay vì đăng công khai — không được set
    assert "draft" not in settings
    # allowDuet/allowStitch bắt buộc với bài video
    assert settings["allowDuet"] is True
    assert settings["allowStitch"] is True


def test_create_post_gui_x_request_id(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request_id"] = request.headers.get("x-request-id")
        return httpx.Response(201, json={"post": {"_id": "p1", "status": "published"}})

    monkeypatch.setattr(zernio_client, "_client", mock_client(handler))

    post = zernio_client.create_post(
        "tiktok", "acc-1", "Tiêu đề", "https://media/x.mp4", request_id="attempt-42"
    )

    assert seen["request_id"] == "attempt-42"
    assert post["_id"] == "p1"


def test_create_post_chap_nhan_existing_post_khi_retry(monkeypatch):
    """Retry cùng x-request-id ⇒ Zernio trả 200 kèm existingPost, không tạo bài mới."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"existingPost": {"_id": "p1", "status": "publishing"}})

    monkeypatch.setattr(zernio_client, "_client", mock_client(handler))

    post = zernio_client.create_post(
        "tiktok", "acc-1", "Tiêu đề", "https://media/x.mp4", request_id="attempt-42"
    )

    assert post["_id"] == "p1"


def test_default_profile_id_uu_tien_env(monkeypatch):
    monkeypatch.setenv("ZERNIO_PROFILE_ID", "profile-env")

    assert zernio_client.default_profile_id() == "profile-env"


def test_default_profile_id_chon_profile_mac_dinh(monkeypatch):
    respond(
        monkeypatch,
        200,
        {"profiles": [{"_id": "p1"}, {"_id": "p2", "isDefault": True}]},
    )

    assert zernio_client.default_profile_id() == "p2"


def test_post_url_from_lay_platform_post_url():
    post = {"platforms": [{"platformPostUrl": "https://tiktok.com/@a/video/1"}]}

    assert zernio_client.post_url_from(post) == "https://tiktok.com/@a/video/1"

"""
tests/unit/test_publish_cancel.py — Huỷ bài đang chờ đăng (007-schedule-publish,
FR-011, FR-012, FR-015).

Trọng tâm: thứ tự BẮT BUỘC là gọi Zernio huỷ trước, ghi 'cancelled' vào file
sau (research.md §5) — Zernio lỗi thì trạng thái phải giữ nguyên 'scheduled',
không được nói dối người dùng về một việc chưa thật sự huỷ được.

⚠️ Constitution §VI: zernio_client được mock hoàn toàn, không gọi thật.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from publish import store
from publish.zernio_client import ZernioError
from web.backend import auth, publish_api


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "sk_test")

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(store, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "publish_data" / "state.json")
    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)

    from web.backend.main import app

    client = TestClient(app)
    client.cookies.set(auth.SESSION_COOKIE_NAME, "fake")

    return {"client": client, "jobs_dir": jobs_dir, "monkeypatch": monkeypatch}


def _iso(minutes_from_now: float) -> str:
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return dt.isoformat().replace("+00:00", "Z")


def make_scheduled_attempt(job_id="job-1", account_id="acc-1", status="scheduled"):
    attempt = store.create_attempt(
        job_id, "tiktok", account_id, "@kenh", "Tiêu đề",
        publish_mode="scheduled", scheduled_for=_iso(60),
    )
    return store.update_attempt(
        job_id, attempt["attempt_id"], status=status, provider_post_id="post-1"
    )


# ── DELETE /api/publish/attempts/{id} ───────────────────────────────────────


def test_huy_bai_scheduled_thanh_cong(env, monkeypatch):
    attempt = make_scheduled_attempt()
    monkeypatch.setattr(publish_api.zernio_client, "delete_post", lambda post_id: None)

    res = env["client"].delete(f"/api/publish/attempts/{attempt['attempt_id']}")

    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert store.read_attempt("job-1", attempt["attempt_id"])["status"] == "cancelled"


def test_zernio_loi_khi_huy_thi_giu_nguyen_scheduled(env, monkeypatch):
    """Bug quan trọng nhất cần chặn: không ghi 'cancelled' khi chưa huỷ được thật."""
    attempt = make_scheduled_attempt()

    def raise_error(post_id):
        raise ZernioError("provider_unavailable", "Dịch vụ trung gian đang gặp sự cố")

    monkeypatch.setattr(publish_api.zernio_client, "delete_post", raise_error)

    res = env["client"].delete(f"/api/publish/attempts/{attempt['attempt_id']}")

    assert res.status_code == 502
    assert store.read_attempt("job-1", attempt["attempt_id"])["status"] == "scheduled"


def test_huy_bai_da_thanh_cong_bi_chan(env):
    attempt = make_scheduled_attempt(status="success")

    res = env["client"].delete(f"/api/publish/attempts/{attempt['attempt_id']}")

    assert res.status_code == 409
    assert "xoá trực tiếp trên nền tảng" in res.json()["error"]


def test_huy_bai_dang_publishing_bi_chan(env):
    attempt = make_scheduled_attempt(status="publishing")

    res = env["client"].delete(f"/api/publish/attempts/{attempt['attempt_id']}")

    assert res.status_code == 409
    assert "không huỷ được nữa" in res.json()["error"]


def test_huy_bai_khong_ton_tai_tra_404(env):
    res = env["client"].delete("/api/publish/attempts/khong-co")

    assert res.status_code == 404


def test_zernio_400_anh_xa_thanh_409(env, monkeypatch):
    """delete_post() ánh xạ HTTP 400 của Zernio (bài đã đăng) -> platform_rejected
    -> endpoint phải trả 409 cho người dùng, không phải 502 mặc định."""
    attempt = make_scheduled_attempt()

    def raise_platform_rejected(post_id):
        raise ZernioError("platform_rejected", "Bài đã đăng rồi, không huỷ được từ đây")

    monkeypatch.setattr(publish_api.zernio_client, "delete_post", raise_platform_rejected)

    res = env["client"].delete(f"/api/publish/attempts/{attempt['attempt_id']}")

    assert res.status_code == 409


# ── DELETE /api/publish/connections/{account_id} huỷ theo (FR-015) ─────────


def test_ngat_ket_noi_huy_ca_2_bai_dang_cho(env, monkeypatch):
    a1 = make_scheduled_attempt(job_id="job-1", account_id="acc-1")
    a2 = make_scheduled_attempt(job_id="job-2", account_id="acc-1")
    # Job khác kênh không bị đụng tới
    other = make_scheduled_attempt(job_id="job-3", account_id="acc-2")

    monkeypatch.setattr(publish_api.zernio_client, "delete_post", lambda post_id: None)
    monkeypatch.setattr(publish_api.zernio_client, "delete_account", lambda account_id: None)

    res = env["client"].delete("/api/publish/connections/acc-1")

    assert res.status_code == 200
    body = res.json()
    assert len(body["cancelled_attempts"]) == 2
    cancelled_ids = {a["attempt_id"] for a in body["cancelled_attempts"]}
    assert cancelled_ids == {a1["attempt_id"], a2["attempt_id"]}

    assert store.read_attempt("job-1", a1["attempt_id"])["status"] == "cancelled"
    assert store.read_attempt("job-2", a2["attempt_id"])["status"] == "cancelled"
    assert store.read_attempt("job-3", other["attempt_id"])["status"] == "scheduled"


def test_ngat_ket_noi_khong_co_bai_cho_thi_cancelled_attempts_rong(env, monkeypatch):
    monkeypatch.setattr(publish_api.zernio_client, "delete_account", lambda account_id: None)

    res = env["client"].delete("/api/publish/connections/acc-no-schedule")

    assert res.status_code == 200
    assert res.json()["cancelled_attempts"] == []


def test_ngat_ket_noi_huy_loi_1_bai_van_bao_warning_khong_chan_response(env, monkeypatch):
    a1 = make_scheduled_attempt(job_id="job-1", account_id="acc-1")
    a2 = make_scheduled_attempt(job_id="job-2", account_id="acc-1")

    calls = {"n": 0}

    def flaky_delete(post_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ZernioError("provider_unavailable", "timeout")
        return None

    monkeypatch.setattr(publish_api.zernio_client, "delete_post", flaky_delete)
    monkeypatch.setattr(publish_api.zernio_client, "delete_account", lambda account_id: None)

    res = env["client"].delete("/api/publish/connections/acc-1")

    assert res.status_code == 200
    assert len(res.json()["cancelled_attempts"]) == 1
    assert "warning" in res.json()

    statuses = {
        store.read_attempt("job-1", a1["attempt_id"])["status"],
        store.read_attempt("job-2", a2["attempt_id"])["status"],
    }
    assert statuses == {"scheduled", "cancelled"}


def test_ngat_ket_noi_van_chan_dang_du_khong_co_bai_cho(env, monkeypatch):
    """Blocklist cục bộ (006) vẫn hoạt động bình thường, không bị phá bởi thay đổi 007."""
    monkeypatch.setattr(publish_api.zernio_client, "delete_account", lambda account_id: None)

    res = env["client"].delete("/api/publish/connections/acc-1")

    assert res.status_code == 200
    assert store.is_blocked("acc-1") is True

"""
tests/unit/test_publish_reconcile.py — Đối soát lười (007-schedule-publish).

Trọng tâm: attempt "scheduled" chưa tới giờ KHÔNG được gọi Zernio (tốn quota vô
ích); attempt đã tới giờ hoặc "publishing" thì phải đối soát; lỗi khi đối soát
không được phá trạng thái hiện có.

⚠️ Constitution §VI: zernio_client được mock hoàn toàn, không gọi thật.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from publish import reconcile, store
from publish.zernio_client import ZernioError


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(store, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "publish_data" / "state.json")
    return jobs_dir


def scheduled_attempt(isolated, minutes_from_now: float, status: str = "scheduled"):
    scheduled_for = (
        datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    ).isoformat().replace("+00:00", "Z")
    attempt = store.create_attempt(
        "job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề",
        publish_mode="scheduled", scheduled_for=scheduled_for,
    )
    return store.update_attempt(
        "job-1", attempt["attempt_id"], status=status, provider_post_id="post-1"
    )


# ── needs_reconcile() ────────────────────────────────────────────────────────


def test_chua_toi_gio_thi_khong_can_doi_soat(isolated):
    attempt = scheduled_attempt(isolated, minutes_from_now=120)

    assert reconcile.needs_reconcile(attempt) is False


def test_da_toi_gio_thi_can_doi_soat(isolated):
    attempt = scheduled_attempt(isolated, minutes_from_now=-5)

    assert reconcile.needs_reconcile(attempt) is True


def test_trong_khoang_tru_hao_1_phut_thi_can_doi_soat(isolated):
    """Trừ hao cho lệch đồng hồ — 30s trước giờ hẹn vẫn coi là 'đến lúc' kiểm tra."""
    attempt = scheduled_attempt(isolated, minutes_from_now=0.5)

    assert reconcile.needs_reconcile(attempt) is True


def test_publishing_luon_can_doi_soat_bat_ke_gio(isolated):
    attempt = scheduled_attempt(isolated, minutes_from_now=999, status="publishing")

    assert reconcile.needs_reconcile(attempt) is True


def test_pending_khong_can_doi_soat(isolated):
    attempt = store.create_attempt("job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề")

    assert reconcile.needs_reconcile(attempt) is False


def test_success_khong_can_doi_soat_nua(isolated):
    attempt = scheduled_attempt(isolated, minutes_from_now=-999, status="success")

    assert reconcile.needs_reconcile(attempt) is False


# ── reconcile_attempt() ──────────────────────────────────────────────────────


def test_published_thi_chuyen_success(isolated, monkeypatch):
    attempt = scheduled_attempt(isolated, minutes_from_now=-5)
    monkeypatch.setattr(
        reconcile.zernio_client,
        "get_post",
        lambda post_id: {
            "status": "published",
            "platforms": [{"platformPostUrl": "https://tiktok.com/@a/video/1"}],
        },
    )

    result = reconcile.reconcile_attempt(attempt)

    assert result["status"] == "success"
    assert result["post_url"] == "https://tiktok.com/@a/video/1"
    assert store.read_attempt("job-1", attempt["attempt_id"])["status"] == "success"


def test_failed_thi_chuyen_failed_kem_ly_do(isolated, monkeypatch):
    attempt = scheduled_attempt(isolated, minutes_from_now=-5)
    monkeypatch.setattr(
        reconcile.zernio_client,
        "get_post",
        lambda post_id: {
            "status": "failed",
            "platforms": [{"status": "failed", "error": "Video quá dài"}],
        },
    )

    result = reconcile.reconcile_attempt(attempt)

    assert result["status"] == "failed"
    assert result["error_kind"] == "platform_rejected"
    assert "Video quá dài" in result["error"]


def test_van_dang_scheduled_thi_giu_nguyen(isolated, monkeypatch):
    attempt = scheduled_attempt(isolated, minutes_from_now=-5)
    monkeypatch.setattr(
        reconcile.zernio_client, "get_post", lambda post_id: {"status": "scheduled"}
    )

    result = reconcile.reconcile_attempt(attempt)

    assert result["status"] == "scheduled"


def test_loi_khi_doi_soat_khong_pha_trang_thai_hien_co(isolated, monkeypatch):
    """Bug quan trọng nhất cần chặn: lỗi gọi Zernio không được biến thành 'failed'."""
    attempt = scheduled_attempt(isolated, minutes_from_now=-5)

    def raise_error(post_id):
        raise ZernioError("provider_unavailable", "timeout")

    monkeypatch.setattr(reconcile.zernio_client, "get_post", raise_error)

    result = reconcile.reconcile_attempt(attempt)

    assert result["status"] == "scheduled"
    assert store.read_attempt("job-1", attempt["attempt_id"])["status"] == "scheduled"


def test_khong_co_provider_post_id_thi_bo_qua(isolated, monkeypatch):
    attempt = store.create_attempt(
        "job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề",
        publish_mode="scheduled", scheduled_for="2020-01-01T00:00:00Z",
    )  # chưa có provider_post_id (chưa tạo được post ở Zernio)

    called = []
    monkeypatch.setattr(
        reconcile.zernio_client, "get_post", lambda post_id: called.append(post_id)
    )

    result = reconcile.reconcile_attempt(attempt)

    assert called == []
    assert result["status"] == "pending"


def test_reconcile_if_needed_bo_qua_khi_chua_toi_gio(isolated, monkeypatch):
    attempt = scheduled_attempt(isolated, minutes_from_now=120)
    called = []
    monkeypatch.setattr(
        reconcile.zernio_client, "get_post", lambda post_id: called.append(post_id)
    )

    result = reconcile.reconcile_if_needed(attempt)

    assert called == []
    assert result["status"] == "scheduled"


def test_reconcile_if_needed_goi_khi_da_toi_gio(isolated, monkeypatch):
    attempt = scheduled_attempt(isolated, minutes_from_now=-5)
    monkeypatch.setattr(
        reconcile.zernio_client,
        "get_post",
        lambda post_id: {"status": "published", "platforms": []},
    )

    result = reconcile.reconcile_if_needed(attempt)

    assert result["status"] == "success"

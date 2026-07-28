"""
tests/unit/test_publish_store.py — Lưu/đọc trạng thái lượt đăng (data-model.md).

Không chạm mạng: chỉ đọc/ghi file trong thư mục tạm.
"""

from __future__ import annotations

import pytest

from publish import store


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """Trỏ JOBS_DIR và state.json vào thư mục tạm, không đụng dữ liệu thật."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(store, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "publish_data" / "state.json")
    return jobs_dir


def _attempt(job_id="job-1", platform="tiktok"):
    return store.create_attempt(
        job_id=job_id,
        platform=platform,
        account_id="acc-1",
        account_label="@kenh",
        title="Tiêu đề",
    )


def test_create_attempt_ghi_file_pending(isolated_store):
    attempt = _attempt()

    assert attempt["status"] == "pending"
    assert attempt["error"] is None
    path = store.attempt_path("job-1", attempt["attempt_id"])
    assert path.exists()
    assert store.read_attempt("job-1", attempt["attempt_id"])["title"] == "Tiêu đề"


def test_update_attempt_giu_nguyen_field_khac(isolated_store):
    attempt = _attempt()

    updated = store.update_attempt(
        "job-1", attempt["attempt_id"], status="success", post_url="https://tiktok/x"
    )

    assert updated["status"] == "success"
    assert updated["post_url"] == "https://tiktok/x"
    assert updated["title"] == "Tiêu đề"
    assert updated["updated_at"] >= attempt["updated_at"]


def test_find_active_attempt_chi_khop_pending_va_publishing(isolated_store):
    attempt = _attempt()
    assert store.find_active_attempt("job-1", "tiktok")["attempt_id"] == attempt["attempt_id"]

    store.update_attempt("job-1", attempt["attempt_id"], status="publishing")
    assert store.find_active_attempt("job-1", "tiktok") is not None

    store.update_attempt("job-1", attempt["attempt_id"], status="success")
    assert store.find_active_attempt("job-1", "tiktok") is None


def test_find_active_attempt_tach_theo_nen_tang(isolated_store):
    _attempt(platform="tiktok")

    assert store.find_active_attempt("job-1", "tiktok") is not None
    assert store.find_active_attempt("job-1", "youtube") is None


def test_published_platforms_chi_tinh_success(isolated_store):
    a1 = _attempt(platform="tiktok")
    a2 = _attempt(platform="youtube")
    store.update_attempt("job-1", a1["attempt_id"], status="success")
    store.update_attempt("job-1", a2["attempt_id"], status="failed")

    assert store.published_platforms("job-1") == ["tiktok"]


def test_list_attempts_moi_nhat_truoc(isolated_store):
    a1 = _attempt()
    store.update_attempt("job-1", a1["attempt_id"], status="success")
    a2 = store.create_attempt("job-2", "tiktok", "acc-1", "@kenh", "Video 2")

    ids = [a["attempt_id"] for a in store.list_attempts()]
    assert set(ids) == {a1["attempt_id"], a2["attempt_id"]}
    assert ids[0] == a2["attempt_id"]  # tạo sau ⇒ đứng trước


def test_blocklist_them_va_go(isolated_store):
    assert store.is_blocked("acc-1") is False

    store.block_account("acc-1")
    assert store.is_blocked("acc-1") is True
    assert store.read_state()["disconnected_account_ids"] == ["acc-1"]

    store.block_account("acc-1")  # idempotent
    assert store.read_state()["disconnected_account_ids"] == ["acc-1"]

    store.unblock_account("acc-1")
    assert store.is_blocked("acc-1") is False


def test_state_hong_khong_lam_chet_ung_dung(isolated_store, tmp_path):
    store.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store.STATE_PATH.write_text("{ khong phai json", encoding="utf-8")

    state = store.read_state()

    assert state["profile_id"] is None
    assert state["disconnected_account_ids"] == []

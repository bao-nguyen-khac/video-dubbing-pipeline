"""
tests/unit/test_publish_runner.py — Chuyển trạng thái lượt đăng
(data-model.md §1.1, SC-004).

⚠️ Constitution §VI: zernio_client bị thay hoàn toàn bằng bản giả — không gọi
thật, không upload gì.
"""

from __future__ import annotations

import pytest

from publish import runner, store
from publish.zernio_client import ZernioError


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(store, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "publish_data" / "state.json")
    # Không chờ thật giữa các lượt poll
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    return jobs_dir


@pytest.fixture()
def attempt(isolated):
    return store.create_attempt("job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề")


def install_client(monkeypatch, *, upload=None, create=None, poll_results=None, creator_info=None):
    """Thay các hàm của zernio_client bằng bản giả."""

    def default_upload(path):
        return "https://media.zernio.com/temp/x.mp4"

    def default_create(**kwargs):
        return {"_id": "post-1", "status": "publishing"}

    def default_creator_info(account_id):
        return {
            "creator": {"canPostMore": True},
            "privacyLevels": [{"value": "PUBLIC_TO_EVERYONE"}],
        }

    monkeypatch.setattr(runner.zernio_client, "upload_video", upload or default_upload)
    monkeypatch.setattr(runner.zernio_client, "create_post", create or default_create)
    monkeypatch.setattr(
        runner.zernio_client, "tiktok_creator_info", creator_info or default_creator_info
    )

    results = list(poll_results or [])

    def fake_get_post(post_id):
        if not results:
            return {"_id": post_id, "status": "publishing"}
        return results.pop(0)

    monkeypatch.setattr(runner.zernio_client, "get_post", fake_get_post)


def test_luong_thanh_cong_ghi_post_url(isolated, attempt, monkeypatch):
    install_client(
        monkeypatch,
        poll_results=[
            {
                "_id": "post-1",
                "status": "published",
                "platforms": [{"platformPostUrl": "https://tiktok.com/@a/video/1"}],
            }
        ],
    )

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "success"
    assert result["post_url"] == "https://tiktok.com/@a/video/1"
    assert result["error"] is None
    # Trạng thái được ghi xuống file, không chỉ nằm trong bộ nhớ
    assert store.read_attempt("job-1", attempt["attempt_id"])["status"] == "success"


def test_dang_thanh_cong_ngay_o_lan_tao_post(isolated, attempt, monkeypatch):
    """publishNow=true có thể trả 'published' ngay — không cần poll thêm."""
    install_client(
        monkeypatch,
        create=lambda **kwargs: {
            "_id": "post-1",
            "status": "published",
            "platforms": [{"platformPostUrl": "https://tiktok.com/@a/video/2"}],
        },
    )

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "success"
    assert result["post_url"] == "https://tiktok.com/@a/video/2"


def test_provider_bao_failed_thi_platform_rejected(isolated, attempt, monkeypatch):
    install_client(
        monkeypatch,
        poll_results=[
            {
                "_id": "post-1",
                "status": "failed",
                "platforms": [{"status": "failed", "error": "Video quá dài"}],
            }
        ],
    )

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert result["error_kind"] == "platform_rejected"
    assert "Video quá dài" in result["error"]


def test_partial_cung_tinh_la_that_bai(isolated, attempt, monkeypatch):
    install_client(monkeypatch, poll_results=[{"_id": "post-1", "status": "partial"}])

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert result["error_kind"] == "platform_rejected"


def test_token_het_han_thi_auth_expired(isolated, attempt, monkeypatch):
    def create_raises(**kwargs):
        raise ZernioError("auth_expired", "Kênh đã mất kết nối — hãy liên kết lại")

    install_client(monkeypatch, create=create_raises)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert result["error_kind"] == "auth_expired"
    assert "liên kết lại" in result["error"]


def test_upload_loi_mang_thi_network(isolated, attempt, monkeypatch):
    def upload_raises(path):
        raise ZernioError("network", "Tải video lên kho lưu trữ thất bại")

    install_client(monkeypatch, upload=upload_raises)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert result["error_kind"] == "network"


def test_provider_chet_thi_provider_unavailable(isolated, attempt, monkeypatch):
    def create_raises(**kwargs):
        raise ZernioError("provider_unavailable", "Dịch vụ trung gian đang gặp sự cố")

    install_client(monkeypatch, create=create_raises)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["error_kind"] == "provider_unavailable"


def test_het_han_cho_thi_that_bai_khong_treo(isolated, attempt, monkeypatch):
    install_client(monkeypatch)  # luôn trả 'publishing'
    monkeypatch.setattr(runner, "POLL_TIMEOUT_SECONDS", 0.0)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert result["error_kind"] == "provider_unavailable"
    assert "Quá thời gian chờ" in result["error"]


def test_tiktok_khong_cho_dang_cong_khai_thi_dung_lai(isolated, attempt, monkeypatch):
    """Thà không đăng còn hơn đăng ngầm thành video riêng tư (SC-005)."""
    install_client(
        monkeypatch,
        creator_info=lambda account_id: {
            "creator": {"canPostMore": True},
            "privacyLevels": [{"value": "SELF_ONLY"}],
        },
        create=lambda **kwargs: pytest.fail("Không được đăng khi không có mức công khai"),
    )

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert result["error_kind"] == "platform_rejected"
    assert "công khai" in result["error"]


def test_cham_gioi_han_dang_trong_ngay_thi_dung_lai(isolated, attempt, monkeypatch):
    install_client(
        monkeypatch,
        creator_info=lambda account_id: {
            "creator": {"canPostMore": False},
            "privacyLevels": [{"value": "PUBLIC_TO_EVERYONE"}],
        },
        create=lambda **kwargs: pytest.fail("Không được đăng khi đã chạm giới hạn"),
    )

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert "giới hạn" in result["error"]


def test_creator_info_loi_van_dang_binh_thuong(isolated, attempt, monkeypatch):
    """Không lấy được creator-info không đáng để chặn lượt đăng."""

    def creator_info_raises(account_id):
        raise ZernioError("provider_unavailable", "timeout")

    install_client(
        monkeypatch,
        creator_info=creator_info_raises,
        create=lambda **kwargs: {
            "_id": "post-1",
            "status": "published",
            "platforms": [{"platformPostUrl": "https://tiktok.com/@a/video/3"}],
        },
    )

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "success"


def test_loi_bat_ngo_van_ghi_that_bai_khong_im_lang(isolated, attempt, monkeypatch):
    def upload_explodes(path):
        raise ValueError("lỗi lạ")

    install_client(monkeypatch, upload=upload_explodes)

    runner._run_and_swallow(attempt, "/tmp/output.mp4")

    saved = store.read_attempt("job-1", attempt["attempt_id"])
    assert saved["status"] == "failed"
    assert saved["error_kind"] == "unknown"

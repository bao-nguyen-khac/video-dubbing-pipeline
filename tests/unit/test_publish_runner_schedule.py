"""
tests/unit/test_publish_runner_schedule.py — Tách nhánh runner theo publish_mode
(007-schedule-publish, research.md §3).

Bug đã phát hiện thật (nếu không tách nhánh): bài hẹn 3 ngày sau vẫn ở trạng
thái "scheduled" khi Zernio kiểm tra — nếu dùng chung _poll_until_done() với
nhánh "now", sau 10 phút nó sẽ bị đánh nhầm thành "failed" dù đang chờ đăng
bình thường. Test này khoá lại: nhánh "scheduled" phải return ngay, không bao
giờ chạm _poll_until_done().

⚠️ Constitution §VI: zernio_client được mock hoàn toàn, không gọi thật.
"""

from __future__ import annotations

import pytest

from publish import runner, store


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(store, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "publish_data" / "state.json")
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    return jobs_dir


def install_client(monkeypatch, post_status="scheduled"):
    monkeypatch.setattr(
        runner.zernio_client, "upload_video", lambda path: "https://media.zernio.com/x.mp4"
    )
    monkeypatch.setattr(
        runner.zernio_client,
        "create_post",
        lambda **kwargs: {"_id": "post-1", "status": post_status},
    )
    monkeypatch.setattr(
        runner.zernio_client,
        "tiktok_creator_info",
        lambda account_id: {
            "creator": {"canPostMore": True},
            "privacyLevels": [{"value": "PUBLIC_TO_EVERYONE"}],
        },
    )


def test_nhanh_scheduled_dung_ngay_khong_poll(isolated, monkeypatch):
    attempt = store.create_attempt(
        "job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề",
        publish_mode="scheduled", scheduled_for="2026-08-01T00:00:00Z",
    )
    install_client(monkeypatch, post_status="scheduled")

    # get_post KHÔNG được gọi ở nhánh này — nếu bị gọi tức là đã lẫn sang poll
    def fail_if_polled(post_id):
        pytest.fail("Nhánh 'scheduled' không được gọi get_post()/poll")

    monkeypatch.setattr(runner.zernio_client, "get_post", fail_if_polled)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "scheduled"
    assert result["provider_post_id"] == "post-1"


def test_nhanh_scheduled_khong_bi_danh_that_bai_du_cho_qua_10_phut(isolated, monkeypatch):
    """
    Tái hiện đúng bug đã phát hiện: dù giả lập "đã chờ quá POLL_TIMEOUT_SECONDS",
    nhánh scheduled vẫn phải là 'scheduled', không bao giờ thành 'failed'.
    """
    attempt = store.create_attempt(
        "job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề",
        publish_mode="scheduled", scheduled_for="2026-08-01T00:00:00Z",
    )
    install_client(monkeypatch, post_status="scheduled")
    # Giả lập mốc timeout đã trôi qua từ lâu TRƯỚC khi gọi run_publish — nếu
    # code lỡ đi vào _poll_until_done(), nó sẽ thấy đã hết hạn ngay lập tức
    monkeypatch.setattr(runner, "POLL_TIMEOUT_SECONDS", -1.0)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "scheduled"
    assert result["error"] is None
    assert result["error_kind"] is None


def test_nhanh_now_khong_doi_hanh_vi(isolated, monkeypatch):
    """Đăng ngay (mặc định, 006) vẫn poll và ra kết quả như cũ."""
    attempt = store.create_attempt("job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề")
    install_client(monkeypatch, post_status="scheduled")

    calls = []

    def fake_get_post(post_id):
        calls.append(post_id)
        return {
            "status": "published",
            "platforms": [{"platformPostUrl": "https://tiktok.com/@a/video/1"}],
        }

    monkeypatch.setattr(runner.zernio_client, "get_post", fake_get_post)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "success"
    assert calls == ["post-1"]  # đã poll — khác hẳn nhánh scheduled


def test_scheduled_for_duoc_truyen_xuong_create_post(isolated, monkeypatch):
    attempt = store.create_attempt(
        "job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề",
        publish_mode="scheduled", scheduled_for="2026-08-01T13:00:00Z",
    )
    seen = {}

    def fake_create_post(**kwargs):
        seen.update(kwargs)
        return {"_id": "post-1", "status": "scheduled"}

    monkeypatch.setattr(runner.zernio_client, "upload_video", lambda path: "https://media/x.mp4")
    monkeypatch.setattr(runner.zernio_client, "create_post", fake_create_post)
    monkeypatch.setattr(
        runner.zernio_client,
        "tiktok_creator_info",
        lambda account_id: {"creator": {"canPostMore": True}, "privacyLevels": [{"value": "PUBLIC_TO_EVERYONE"}]},
    )

    runner.run_publish(attempt, "/tmp/output.mp4")

    assert seen["scheduled_for"] == "2026-08-01T13:00:00Z"


def test_loi_truoc_khi_tao_post_van_fail_binh_thuong(isolated, monkeypatch):
    """Lỗi upload/tạo post xảy ra TRƯỚC khi biết được scheduled hay không — vẫn fail đúng như cũ."""
    from publish.zernio_client import ZernioError

    attempt = store.create_attempt(
        "job-1", "tiktok", "acc-1", "@kenh", "Tiêu đề",
        publish_mode="scheduled", scheduled_for="2026-08-01T00:00:00Z",
    )

    def upload_raises(path):
        raise ZernioError("network", "Tải video lên kho lưu trữ thất bại")

    monkeypatch.setattr(runner.zernio_client, "upload_video", upload_raises)

    result = runner.run_publish(attempt, "/tmp/output.mp4")

    assert result["status"] == "failed"
    assert result["error_kind"] == "network"

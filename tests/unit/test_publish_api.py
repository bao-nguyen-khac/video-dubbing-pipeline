"""
tests/unit/test_publish_api.py — Validate + chống đăng trùng ở endpoint
/api/publish (FR-002/FR-004/FR-009/FR-011, SC-003).

⚠️ Constitution §VI: zernio_client được mock hoàn toàn, không gọi thật.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from publish import limits, store
from publish.zernio_client import ZernioError
from web.backend import auth, publish_api


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """
    Cô lập jobs/ + state.json, bỏ qua đăng nhập, và chặn mọi lời gọi Zernio
    thật (mọi hàm dùng trong luồng đăng đều bị thay bằng bản giả).
    """
    monkeypatch.setenv("ZERNIO_API_KEY", "sk_test")

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(store, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "publish_data" / "state.json")

    # Bỏ qua auth middleware (đã có test riêng cho đăng nhập ở feature 002)
    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)

    calls: list[str] = []

    def fake_list_accounts(platform=None):
        calls.append("list_accounts")
        return [
            {"_id": "acc-1", "platform": "tiktok", "username": "@kenh", "isActive": True},
        ]

    def fake_creator_info(account_id):
        calls.append("creator_info")
        return {
            "creator": {"canPostMore": True},
            "privacyLevels": [{"value": "PUBLIC_TO_EVERYONE"}],
            "postingLimits": {"maxVideoDurationSec": 600},
        }

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Không được gọi Zernio thật trong test")

    monkeypatch.setattr(publish_api.zernio_client, "list_accounts", fake_list_accounts)
    monkeypatch.setattr(publish_api.zernio_client, "tiktok_creator_info", fake_creator_info)
    monkeypatch.setattr(publish_api.zernio_client, "upload_video", fail_if_called)
    monkeypatch.setattr(publish_api.zernio_client, "create_post", fail_if_called)

    # Không cho runner chạy thật — chỉ ghi nhận đã được gọi
    started: list[dict] = []
    monkeypatch.setattr(
        publish_api.runner, "start_publish", lambda attempt, path: started.append(attempt)
    )

    from web.backend.main import app

    client = TestClient(app)
    client.cookies.set(auth.SESSION_COOKIE_NAME, "fake")

    return {
        "client": client,
        "jobs_dir": jobs_dir,
        "calls": calls,
        "started": started,
        "monkeypatch": monkeypatch,
    }


def make_job(env, job_id="job-1", status="done", with_output=True, duration=30.0):
    job_dir = env["jobs_dir"] / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    output_path = job_dir / "output.mp4"
    if with_output:
        output_path.write_bytes(b"\x00" * 1024)
    job = {
        "job_id": job_id,
        "source_url": "https://www.tiktok.com/@a/video/1",
        "platform": "tiktok",
        "script_mode": "rewrite",
        "status": status,
        "error": None,
        "artifacts": {"output_video": str(output_path) if with_output else None},
        "warnings": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")

    # read_job/_iter_all_jobs của jobs_api đọc JOBS_DIR riêng của chúng
    env["monkeypatch"].setattr(publish_api, "read_job", lambda jid: job if jid == job_id else _raise())
    env["monkeypatch"].setattr(publish_api, "_iter_all_jobs", lambda: iter([job]))
    env["monkeypatch"].setattr(publish_api, "get_media_duration", lambda p: duration)
    # limits.py import get_media_duration trực tiếp (không qua publish_api) —
    # phải mock cả ở đó, nếu không ffprobe thật quyết định kết quả test
    env["monkeypatch"].setattr(limits, "get_media_duration", lambda p: duration)
    return job


def _raise():
    raise FileNotFoundError


def publish_body(**overrides):
    body = {
        "job_id": "job-1",
        "platform": "tiktok",
        "account_id": "acc-1",
        "title": "Tiêu đề hợp lệ",
    }
    body.update(overrides)
    return body


# ── Validate ────────────────────────────────────────────────────────────────


def test_tieu_de_rong_bi_chan(env):
    make_job(env)

    res = env["client"].post("/api/publish", json=publish_body(title="   "))

    assert res.status_code == 400
    assert res.json()["error"] == "Tiêu đề là bắt buộc"
    assert env["started"] == []


def test_job_chua_xong_bi_chan(env):
    make_job(env, status="failed")

    res = env["client"].post("/api/publish", json=publish_body())

    assert res.status_code == 400
    assert "chưa xử lý xong" in res.json()["error"]


def test_job_khong_co_output_bi_chan(env):
    make_job(env, with_output=False)

    res = env["client"].post("/api/publish", json=publish_body())

    assert res.status_code == 400
    assert "chưa có video kết quả" in res.json()["error"]


def test_video_vuot_gioi_han_bi_chan_truoc_khi_upload(env):
    make_job(env, duration=1200.0)

    res = env["client"].post("/api/publish", json=publish_body())

    assert res.status_code == 400
    assert "vượt giới hạn" in res.json()["error"]
    # Không lượt đăng nào được tạo và không có upload nào diễn ra
    assert env["started"] == []
    assert list(store.iter_attempts()) == []


def test_kenh_bi_ngat_ket_noi_bi_chan(env):
    make_job(env)
    store.block_account("acc-1")

    res = env["client"].post("/api/publish", json=publish_body())

    assert res.status_code == 403
    assert "liên kết lại" in res.json()["error"]


def test_nen_tang_chua_ho_tro_bi_chan(env):
    make_job(env)

    res = env["client"].post("/api/publish", json=publish_body(platform="youtube"))

    assert res.status_code == 400


def test_thieu_api_key_tra_503(env, monkeypatch):
    monkeypatch.delenv("ZERNIO_API_KEY", raising=False)
    make_job(env)

    res = env["client"].post("/api/publish", json=publish_body())

    assert res.status_code == 503
    assert "ZERNIO_API_KEY" in res.json()["error"]


# ── Chống đăng trùng (FR-009, SC-003) ───────────────────────────────────────


def test_bam_dang_hai_lan_chi_tao_mot_luot(env):
    make_job(env)

    first = env["client"].post("/api/publish", json=publish_body())
    second = env["client"].post("/api/publish", json=publish_body())

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["attempt_id"] == first.json()["attempt_id"]

    attempts = list(store.iter_attempts("job-1"))
    assert len(attempts) == 1
    assert len(env["started"]) == 1


def test_dang_lai_duoc_sau_khi_luot_truoc_that_bai(env):
    make_job(env)
    first = env["client"].post("/api/publish", json=publish_body())
    store.update_attempt("job-1", first.json()["attempt_id"], status="failed")

    second = env["client"].post("/api/publish", json=publish_body())

    assert second.status_code == 202
    assert second.json()["attempt_id"] != first.json()["attempt_id"]
    # Lượt cũ được giữ nguyên trong lịch sử, không bị sửa đè
    assert len(list(store.iter_attempts("job-1"))) == 2


# ── Danh sách & lịch sử ─────────────────────────────────────────────────────


def test_videos_chi_liet_ke_job_done_co_output(env):
    make_job(env, status="done")

    res = env["client"].get("/api/publish/videos")

    assert res.status_code == 200
    videos = res.json()["videos"]
    assert len(videos) == 1
    assert videos[0]["job_id"] == "job-1"
    assert videos[0]["already_published_to"] == []


def test_videos_bo_qua_job_chua_xong(env):
    make_job(env, status="merging")

    res = env["client"].get("/api/publish/videos")

    assert res.json()["videos"] == []


def test_connections_hop_nhat_blocklist(env):
    store.block_account("acc-1")

    res = env["client"].get("/api/publish/connections")

    assert res.status_code == 200
    assert res.json()["connections"][0]["status"] == "disconnected"


def test_connections_bao_loi_ro_khi_zernio_chet(env, monkeypatch):
    def boom(platform=None):
        raise ZernioError("provider_unavailable", "Dịch vụ trung gian đang gặp sự cố")

    monkeypatch.setattr(publish_api.zernio_client, "list_accounts", boom)

    res = env["client"].get("/api/publish/connections")

    assert res.status_code == 502
    assert "trung gian" in res.json()["error"]


def test_attempt_detail_va_lich_su(env):
    make_job(env)
    created = env["client"].post("/api/publish", json=publish_body()).json()

    detail = env["client"].get(f"/api/publish/attempts/{created['attempt_id']}")
    history = env["client"].get("/api/publish/attempts")

    assert detail.status_code == 200
    assert detail.json()["title"] == "Tiêu đề hợp lệ"
    assert detail.json()["status"] == "pending"
    assert len(history.json()["attempts"]) == 1


def test_attempt_khong_ton_tai_tra_404(env):
    res = env["client"].get("/api/publish/attempts/khong-co")

    assert res.status_code == 404

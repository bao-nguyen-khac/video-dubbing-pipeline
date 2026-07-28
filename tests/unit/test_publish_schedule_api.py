"""
tests/unit/test_publish_schedule_api.py — Đặt lịch đăng qua /api/publish
(007-schedule-publish, FR-003/FR-004/FR-009/FR-014).

⚠️ Constitution §VI: zernio_client được mock hoàn toàn, không gọi thật, và
không test nào tạo bài hẹn giờ thật.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from publish import limits, store
from web.backend import auth, publish_api


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Cùng khuôn mẫu với tests/unit/test_publish_api.py::env."""
    monkeypatch.setenv("ZERNIO_API_KEY", "sk_test")

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    monkeypatch.setattr(store, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(store, "STATE_PATH", tmp_path / "publish_data" / "state.json")
    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Không được gọi Zernio thật trong test")

    monkeypatch.setattr(publish_api.zernio_client, "upload_video", fail_if_called)
    monkeypatch.setattr(publish_api.zernio_client, "create_post", fail_if_called)
    monkeypatch.setattr(
        publish_api.zernio_client,
        "list_accounts",
        lambda platform=None: [
            {"_id": "acc-1", "platform": "tiktok", "username": "@kenh", "isActive": True}
        ],
    )
    monkeypatch.setattr(
        publish_api.zernio_client,
        "tiktok_creator_info",
        lambda account_id: {
            "creator": {"canPostMore": True},
            "privacyLevels": [{"value": "PUBLIC_TO_EVERYONE"}],
            "postingLimits": {"maxVideoDurationSec": 600},
        },
    )

    started: list[dict] = []
    monkeypatch.setattr(
        publish_api.runner, "start_publish", lambda attempt, path: started.append(attempt)
    )

    from web.backend.main import app

    client = TestClient(app)
    client.cookies.set(auth.SESSION_COOKIE_NAME, "fake")

    return {"client": client, "jobs_dir": jobs_dir, "started": started, "monkeypatch": monkeypatch}


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

    env["monkeypatch"].setattr(
        publish_api, "read_job", lambda jid: job if jid == job_id else _raise()
    )
    env["monkeypatch"].setattr(publish_api, "_iter_all_jobs", lambda: iter([job]))
    env["monkeypatch"].setattr(publish_api, "get_media_duration", lambda p: duration)
    env["monkeypatch"].setattr(limits, "get_media_duration", lambda p: duration)
    return job


def _raise():
    raise FileNotFoundError


def _iso(minutes_from_now: float) -> str:
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return dt.isoformat().replace("+00:00", "Z")


def schedule_body(scheduled_for: str | None, **overrides):
    body = {
        "job_id": "job-1",
        "platform": "tiktok",
        "account_id": "acc-1",
        "title": "Tiêu đề hợp lệ",
        "publish_mode": "scheduled",
        "scheduled_for": scheduled_for,
    }
    body.update(overrides)
    return body


# ── Biên thời gian (FR-003, FR-004) ──────────────────────────────────────────


def test_thieu_scheduled_for_bi_chan(env):
    make_job(env)

    res = env["client"].post("/api/publish", json=schedule_body(None))

    assert res.status_code == 400
    assert "Thiếu thời điểm" in res.json()["error"]
    assert env["started"] == []


def test_hen_qua_khu_bi_chan(env):
    make_job(env)

    res = env["client"].post("/api/publish", json=schedule_body(_iso(-10)))

    assert res.status_code == 400
    assert "15 phút" in res.json()["error"]


def test_hen_qua_sat_duoi_15_phut_bi_chan(env):
    make_job(env)

    res = env["client"].post("/api/publish", json=schedule_body(_iso(5)))

    assert res.status_code == 400
    assert "15 phút" in res.json()["error"]


def test_hen_qua_xa_qua_3_ngay_bi_chan(env):
    make_job(env)

    res = env["client"].post("/api/publish", json=schedule_body(_iso(4 * 24 * 60)))

    assert res.status_code == 400
    assert "3 ngày" in res.json()["error"]


def test_hen_hop_le_duoc_chap_nhan(env):
    make_job(env)

    res = env["client"].post("/api/publish", json=schedule_body(_iso(60)))

    assert res.status_code == 202
    attempt_id = res.json()["attempt_id"]
    assert res.json()["status"] == "pending"

    saved = store.read_attempt("job-1", attempt_id)
    assert saved["publish_mode"] == "scheduled"
    assert saved["scheduled_for"] is not None
    assert len(env["started"]) == 1


def test_publish_mode_khong_hop_le_bi_chan(env):
    make_job(env)

    res = env["client"].post(
        "/api/publish", json=schedule_body(_iso(60), publish_mode="later")
    )

    assert res.status_code == 400


def test_bien_thoi_gian_khong_tao_luot_dang_nao(env):
    """Ca 400 tuyệt đối không được tạo file attempt (không tốn 1 lượt upload)."""
    make_job(env)

    env["client"].post("/api/publish", json=schedule_body(_iso(-10)))
    env["client"].post("/api/publish", json=schedule_body(_iso(4 * 24 * 60)))

    assert list(store.iter_attempts("job-1")) == []
    assert env["started"] == []


# ── Ràng buộc của đăng ngay vẫn áp dụng khi hẹn giờ (FR-014) ────────────────


def test_tieu_de_rong_van_bi_chan_khi_hen_gio(env):
    make_job(env)

    res = env["client"].post(
        "/api/publish", json=schedule_body(_iso(60), title="   ")
    )

    assert res.status_code == 400
    assert "Tiêu đề" in res.json()["error"]


def test_job_chua_xong_van_bi_chan_khi_hen_gio(env):
    make_job(env, status="merging")

    res = env["client"].post("/api/publish", json=schedule_body(_iso(60)))

    assert res.status_code == 400
    assert "chưa xử lý xong" in res.json()["error"]


def test_video_vuot_gioi_han_van_bi_chan_truoc_khi_upload(env):
    make_job(env, duration=1200.0)

    res = env["client"].post("/api/publish", json=schedule_body(_iso(60)))

    assert res.status_code == 400
    assert "vượt giới hạn" in res.json()["error"]
    assert env["started"] == []


def test_kenh_bi_ngat_ket_noi_van_bi_chan(env):
    make_job(env)
    store.block_account("acc-1")

    res = env["client"].post("/api/publish", json=schedule_body(_iso(60)))

    assert res.status_code == 403


# ── Chống trùng: scheduled tính là đang hoạt động (research.md §8) ──────────


def test_dat_lich_trung_job_platform_bi_chan(env):
    make_job(env)
    first = env["client"].post("/api/publish", json=schedule_body(_iso(60)))
    assert first.status_code == 202
    # Runner bị mock nên không tự chuyển "pending" -> "scheduled" — giả lập
    # đúng trạng thái thật sự có sau khi Zernio đã nhận bài
    store.update_attempt(
        "job-1", first.json()["attempt_id"], status="scheduled", provider_post_id="post-1"
    )

    second = env["client"].post("/api/publish", json=schedule_body(_iso(90)))

    assert second.status_code == 409
    assert second.json()["attempt_id"] == first.json()["attempt_id"]
    assert "đang chờ đăng" in second.json()["error"]


def test_dang_ngay_bi_chan_boi_bai_da_hen_gio(env):
    """Trộn 'now' và 'scheduled' cùng job+platform vẫn phải chống trùng."""
    make_job(env)
    scheduled = env["client"].post("/api/publish", json=schedule_body(_iso(60)))
    assert scheduled.status_code == 202

    now_body = {
        "job_id": "job-1",
        "platform": "tiktok",
        "account_id": "acc-1",
        "title": "Đăng ngay luôn",
    }
    res = env["client"].post("/api/publish", json=now_body)

    assert res.status_code == 409


def test_dat_lich_lai_duoc_sau_khi_huy_bai_truoc(env):
    make_job(env)
    first = env["client"].post("/api/publish", json=schedule_body(_iso(60)))
    store.cancel_attempt("job-1", first.json()["attempt_id"])

    second = env["client"].post("/api/publish", json=schedule_body(_iso(90)))

    assert second.status_code == 202
    assert second.json()["attempt_id"] != first.json()["attempt_id"]


# ── Response format ──────────────────────────────────────────────────────────


def test_attempt_detail_co_publish_mode_va_scheduled_for(env):
    make_job(env)
    created = env["client"].post("/api/publish", json=schedule_body(_iso(60))).json()

    detail = env["client"].get(f"/api/publish/attempts/{created['attempt_id']}")

    body = detail.json()
    assert body["publish_mode"] == "scheduled"
    assert body["scheduled_for"] is not None
    assert body["status"] == "scheduled" or body["status"] == "pending"


def test_loc_theo_status_scheduled(env):
    make_job(env)
    env["client"].post("/api/publish", json=schedule_body(_iso(60)))
    # Đưa attempt về đúng "scheduled" (runner bị mock nên không tự chuyển)
    attempt_id = list(store.iter_attempts("job-1"))[0]["attempt_id"]
    store.update_attempt("job-1", attempt_id, status="scheduled", provider_post_id="post-1")

    res = env["client"].get("/api/publish/attempts?status=scheduled")

    assert res.status_code == 200
    assert len(res.json()["attempts"]) == 1
    assert res.json()["attempts"][0]["status"] == "scheduled"

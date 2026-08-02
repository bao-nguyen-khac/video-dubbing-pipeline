"""
tests/unit/test_generate_jobs_api.py — Contract test cho 4 endpoint
web/backend/generate_jobs_api.py (contracts/api.md §1-4, 010-topic-video-
generation).

⚠️ Constitution §VI: `start_generate_job` bị mock hoàn toàn (giống
test_review_api.py mock `start_job`) — không test nào ở đây chạy
run_generate_pipeline() thật hay gọi 9router/Pexels/TTS/hyperframes. End-to-end
mock đầy đủ nằm ở test_generate_pipeline_e2e.py (T031).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline import _write_job as write_job
from pipeline import read_job
from web.backend import auth, generate_jobs_api


@pytest.fixture()
def client(tmp_jobs_dir, monkeypatch):
    from web.backend.main import app

    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)

    started: list[str] = []
    monkeypatch.setattr(generate_jobs_api, "start_generate_job", lambda job_id: started.append(job_id))

    c = TestClient(app)
    c.started = started  # type: ignore[attr-defined]
    return c


# ─── POST /api/generate-jobs ──────────────────────────────────────────────────


def test_submit_generate_job_creates_job(client):
    res = client.post("/api/generate-jobs", json={"topic": "tổng quan về tiền tệ"})

    assert res.status_code == 201
    job_id = res.json()["job_id"]
    assert job_id

    detail = client.get(f"/api/generate-jobs/{job_id}").json()
    assert detail["job_type"] == "generate"
    assert detail["topic"] == "tổng quan về tiền tệ"
    assert detail["status"] == "pending"
    assert client.started == [job_id]


def test_submit_generate_job_rejects_blank_topic(client):
    res = client.post("/api/generate-jobs", json={"topic": "   "})
    assert res.status_code == 400
    assert "error" in res.json()


def test_submit_generate_job_conflict_when_dub_job_running(client, make_job):
    make_job(status="downloading")  # job dub đang xử lý — CÙNG hàng đợi (research.md §1)

    res = client.post("/api/generate-jobs", json={"topic": "chủ đề khác"})

    assert res.status_code == 409
    assert "running_job_id" in res.json()


def test_submit_generate_job_conflict_when_generate_job_running(client, make_generate_job):
    make_generate_job(job_id="job-gen-running", status="outlining")

    res = client.post("/api/generate-jobs", json={"topic": "chủ đề khác"})

    assert res.status_code == 409


# ─── GET /api/generate-jobs ───────────────────────────────────────────────────


def test_list_generate_jobs_only_includes_generate_type(client, make_generate_job, make_job):
    make_generate_job(job_id="job-gen-1")
    make_job(job_id="job-dub-1")  # luồng dub — MUST không lẫn vào danh sách này

    res = client.get("/api/generate-jobs")

    assert res.status_code == 200
    job_ids = [j["job_id"] for j in res.json()["jobs"]]
    assert job_ids == ["job-gen-1"]


def test_list_generate_jobs_newest_first(client, make_generate_job):
    make_generate_job(job_id="job-gen-a", extra={"created_at": "2026-08-01T00:00:00+00:00"})
    make_generate_job(job_id="job-gen-b", extra={"created_at": "2026-08-01T01:00:00+00:00"})

    jobs = client.get("/api/generate-jobs").json()["jobs"]

    assert [j["job_id"] for j in jobs] == ["job-gen-b", "job-gen-a"]


# ─── GET /api/generate-jobs/{job_id} ──────────────────────────────────────────


def test_get_generate_job_detail_includes_scenes_brief(client, make_generate_job):
    job = make_generate_job(
        job_id="job-gen-detail",
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=[
            {"index": 0, "narration_text": "câu 1", "image_query": "q1", "image_path": None, "voice_path": None, "duration": None},
            {"index": 1, "narration_text": "câu 2", "image_query": "q2", "image_path": None, "voice_path": None, "duration": None},
        ],
    )

    detail = client.get(f"/api/generate-jobs/{job['job_id']}").json()

    assert detail["scenes"] == [
        {"index": 0, "narration_text": "câu 1"},
        {"index": 1, "narration_text": "câu 2"},
    ]
    # KHÔNG lộ image_path/voice_path tuyệt đối (contracts/api.md §3)
    assert "image_path" not in str(detail["scenes"])
    assert detail["review_url"] == f"/api/jobs/{job['job_id']}/review"


def test_get_generate_job_404_for_missing_job(client):
    res = client.get("/api/generate-jobs/does-not-exist")
    assert res.status_code == 404


def test_get_generate_job_404_for_dub_job(client, make_job):
    """Job dub KHÔNG lộ qua router generate-jobs dù job_id đúng tồn tại."""
    job = make_job(job_id="job-dub-only")

    res = client.get(f"/api/generate-jobs/{job['job_id']}")

    assert res.status_code == 404


# ─── GET /api/generate-jobs/{job_id}/output ───────────────────────────────────


def test_get_generate_job_output_404_when_not_done(client, make_generate_job):
    job = make_generate_job(job_id="job-gen-nodone", status="rendering")

    res = client.get(f"/api/generate-jobs/{job['job_id']}/output")

    assert res.status_code == 404


def test_get_generate_job_output_streams_file_when_done(client, make_generate_job, tmp_jobs_dir):
    job_id = "job-gen-done"
    make_generate_job(job_id=job_id, status="done")
    output_path = tmp_jobs_dir / job_id / "output.mp4"
    output_path.write_bytes(b"fake-mp4-bytes")
    job = read_job(job_id)
    job["artifacts"]["output_video"] = str(output_path)
    write_job(job_id, job)

    res = client.get(f"/api/generate-jobs/{job_id}/output")

    assert res.status_code == 200
    assert res.content == b"fake-mp4-bytes"


# ─── Regression: jobs/ dùng CHUNG giữa dub và generate — GET /api/jobs (dub)
# KHÔNG được crash khi thư mục có lẫn job "generate" (bug thật: _job_to_
# summary() của jobs_api.py giả định mọi job có source_url/platform, KeyError
# ngay khi có 1 job generate trong jobs/, sập luôn trang "Lịch sử" của dub).


def test_dub_job_list_ignores_generate_jobs_without_crashing(
    client, make_job, make_generate_job
):
    make_job(job_id="job-dub-1")
    make_generate_job(job_id="job-gen-1")

    res = client.get("/api/jobs")

    assert res.status_code == 200
    job_ids = [j["job_id"] for j in res.json()["jobs"]]
    assert job_ids == ["job-dub-1"]


def test_dub_job_detail_404_for_generate_job_id(client, make_generate_job):
    job = make_generate_job(job_id="job-gen-detail-via-dub")

    res = client.get(f"/api/jobs/{job['job_id']}")

    assert res.status_code == 404


def test_dub_retry_404_for_generate_job_id(client, make_generate_job):
    job = make_generate_job(job_id="job-gen-retry-via-dub", status="failed")

    res = client.post(f"/api/jobs/{job['job_id']}/retry")

    assert res.status_code == 404

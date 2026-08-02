"""
tests/unit/test_review_api.py — Endpoint chốt kiểm duyệt (008-supervised-pipeline).

Bao phủ contracts/api.md §2–§5: GET/PUT review, approve, regenerate — gồm cả các
nhánh 400/409 mà spec nói rõ phải giữ nguyên trạng thái job (FR-018/FR-019).

⚠️ Constitution §VI: `start_job` bị mock hoàn toàn — không test nào chạy pipeline
thật hay gọi 9router/Vivibe/Zernio.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.unit.conftest import REVIEWED_SEGMENTS, SCRIPT_SEGMENTS
from web.backend import auth, review_api


@pytest.fixture()
def client(tmp_jobs_dir, monkeypatch):
    """TestClient với auth bỏ qua và start_job bị chặn (ghi lại lượt gọi)."""
    from web.backend.main import app

    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)

    started: list[dict] = []

    def fake_start_job(url, script_mode, job_id=None, **kwargs):
        started.append({"url": url, "script_mode": script_mode, "job_id": job_id, **kwargs})

    monkeypatch.setattr(review_api, "start_job", fake_start_job)

    c = TestClient(app)
    c.started = started  # type: ignore[attr-defined]
    return c


def _load(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─── GET /review ─────────────────────────────────────────────────────────────


def test_get_review_transcript_gate(client, make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
        review_gates={"transcript": {"reached_at": "2026-07-30T00:00:00+00:00"}},
    )

    res = client.get(f"/api/jobs/{job['job_id']}/review")

    assert res.status_code == 200
    body = res.json()
    assert body["gate"] == "transcript"
    assert body["editable_field"] == "text"
    assert body["can_regenerate"] is False
    assert all(s["source_text"] is None for s in body["segments"])
    assert body["segments"][0]["start"] == 0.0


def test_get_review_empty_segments_is_200(client, make_job):
    """Video không có lời thoại: 0 câu là thành công, không phải lỗi."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=[],
    )

    res = client.get(f"/api/jobs/{job['job_id']}/review")

    assert res.status_code == 200
    assert res.json()["segments"] == []


def test_get_review_404_when_job_missing(client):
    res = client.get("/api/jobs/khong-ton-tai/review")

    assert res.status_code == 404
    assert res.json()["error"] == "Job không tồn tại"


def test_get_review_409_when_not_awaiting(client, make_job):
    job = make_job(status="merging")

    res = client.get(f"/api/jobs/{job['job_id']}/review")

    assert res.status_code == 409
    assert res.json()["status"] == "merging"


# ─── PUT /review ─────────────────────────────────────────────────────────────


def test_put_review_saves_without_changing_status(client, make_job):
    """FR-011: lưu nháp — không phê duyệt, status giữ nguyên."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    res = client.put(
        f"/api/jobs/{job['job_id']}/review",
        json={"gate": "transcript", "segments": [{"index": 0, "text": "Này MrBeast,"}]},
    )

    assert res.status_code == 200
    assert res.json()["saved_count"] == 2
    assert res.json()["dropped_count"] == 0

    import pipeline

    saved = pipeline.read_job(job["job_id"])
    assert saved["status"] == "awaiting_review"
    assert saved["review_gate"] == "transcript"
    assert saved["review_gates"]["transcript"]["edited"] is True
    assert _load(saved["artifacts"]["transcript_reviewed"])["segments"][0]["text"] == (
        "Này MrBeast,"
    )


def test_put_review_drops_blank_segment(client, make_job):
    """FR-013: xoá trắng = bỏ câu."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    res = client.put(
        f"/api/jobs/{job['job_id']}/review",
        json={"gate": "transcript", "segments": [{"index": 0, "text": "  "}]},
    )

    assert res.status_code == 200
    assert (res.json()["saved_count"], res.json()["dropped_count"]) == (1, 1)


def test_put_review_all_blank_returns_400_and_keeps_file(client, make_job):
    """FR-014: rỗng toàn bộ → 400, file trên đĩa không đổi."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )
    path = job["artifacts"]["transcript_reviewed"]
    before = _load(path)

    res = client.put(
        f"/api/jobs/{job['job_id']}/review",
        json={
            "gate": "transcript",
            "segments": [{"index": 0, "text": ""}, {"index": 1, "text": " "}],
        },
    )

    assert res.status_code == 400
    assert "rỗng" in res.json()["error"]
    assert _load(path) == before


def test_put_review_unknown_index_returns_400(client, make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    res = client.put(
        f"/api/jobs/{job['job_id']}/review",
        json={"gate": "transcript", "segments": [{"index": 99, "text": "x"}]},
    )

    assert res.status_code == 400
    assert "99" in res.json()["error"]


def test_put_review_gate_mismatch_returns_409(client, make_job):
    """Tab cũ lưu sai chốt phải bị từ chối."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
        script_segments=SCRIPT_SEGMENTS,
    )

    res = client.put(
        f"/api/jobs/{job['job_id']}/review",
        json={"gate": "script", "segments": [{"index": 0, "text": "x"}]},
    )

    assert res.status_code == 409
    assert "transcript" in res.json()["error"]


# ─── POST /review/approve ────────────────────────────────────────────────────


def test_approve_transcript_gate_resumes_scripting(client, make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
        review_gates={"transcript": {"reached_at": "2026-07-30T00:00:00+00:00"}},
    )

    res = client.post(
        f"/api/jobs/{job['job_id']}/review/approve", json={"gate": "transcript"}
    )

    assert res.status_code == 202
    assert res.json()["resumed_status"] == "scripting"

    import pipeline

    saved = pipeline.read_job(job["job_id"])
    assert saved["status"] == "scripting"
    assert saved["review_gate"] is None
    assert saved["review_gates"]["transcript"]["approved_at"] is not None
    # Pipeline được khởi động lại đúng một lần, với đúng job_id
    assert len(client.started) == 1  # type: ignore[attr-defined]
    assert client.started[0]["job_id"] == job["job_id"]  # type: ignore[attr-defined]
    assert client.started[0]["supervised"] is True  # type: ignore[attr-defined]


def test_approve_twice_only_runs_once(client, make_job):
    """FR-019: nhấn đúp / 2 tab — lượt sau bị từ chối vô hại."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )
    url = f"/api/jobs/{job['job_id']}/review/approve"

    first = client.post(url, json={"gate": "transcript"})
    second = client.post(url, json={"gate": "transcript"})

    assert first.status_code == 202
    assert second.status_code == 409
    assert len(client.started) == 1  # type: ignore[attr-defined]


def test_approve_gate_mismatch_returns_409(client, make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    res = client.post(
        f"/api/jobs/{job['job_id']}/review/approve", json={"gate": "script"}
    )

    assert res.status_code == 409
    assert len(client.started) == 0  # type: ignore[attr-defined]


def test_approve_404_when_job_missing(client):
    res = client.post("/api/jobs/khong-ton-tai/review/approve", json={"gate": "transcript"})

    assert res.status_code == 404


def test_approve_409_when_another_job_processing(client, make_job):
    """
    FR-018: có job khác THỰC SỰ xử lý → từ chối, và job chờ duyệt giữ nguyên
    trạng thái + nội dung đã sửa (không mất, không bị đánh dấu lỗi).
    """
    waiting = make_job(
        job_id="job-waiting",
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )
    make_job(job_id="job-busy", status="synthesizing")

    res = client.post(
        f"/api/jobs/{waiting['job_id']}/review/approve", json={"gate": "transcript"}
    )

    assert res.status_code == 409
    assert res.json()["running_job_id"] == "job-busy"

    import pipeline

    after = pipeline.read_job("job-waiting")
    assert after["status"] == "awaiting_review"
    assert after["review_gate"] == "transcript"
    assert len(_load(after["artifacts"]["transcript_reviewed"])["segments"]) == 2
    assert len(client.started) == 0  # type: ignore[attr-defined]


def test_awaiting_review_job_does_not_occupy_slot(client, make_job):
    """FR-021/SC-005: job chờ duyệt không tính là đang xử lý."""
    from web.backend.jobs_api import find_running_job_id

    make_job(status="awaiting_review", supervised=True, review_gate="transcript")

    assert find_running_job_id() is None


def test_delete_awaiting_review_job_is_allowed(client, make_job):
    """FR-022: job chờ duyệt xoá được như job chờ/xong/lỗi."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    res = client.delete(f"/api/jobs/{job['job_id']}")

    assert res.status_code == 200
    assert res.json()["ok"] is True


# ─── Chốt kịch bản (US2) ─────────────────────────────────────────────────────


@pytest.fixture()
def script_gate_job(make_job):
    return make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="script",
        reviewed_segments=REVIEWED_SEGMENTS,
        script_segments=SCRIPT_SEGMENTS,
        review_gates={
            "transcript": {"reached_at": "2026-07-30T00:00:00+00:00", "approved_at": "2026-07-30T00:05:00+00:00"},
            "script": {"reached_at": "2026-07-30T00:06:00+00:00", "approved_at": None},
        },
    )


def test_get_review_script_gate(client, script_gate_job):
    res = client.get(f"/api/jobs/{script_gate_job['job_id']}/review")

    assert res.status_code == 200
    body = res.json()
    assert body["gate"] == "script"
    assert body["editable_field"] == "translated_text"
    assert body["can_regenerate"] is True
    assert body["segments"][0]["source_text"] == "Hey Mr. Beast,"
    assert body["segments"][0]["text"] == "Này MrBeast,"


def test_put_review_script_gate_writes_translation_and_backup(client, script_gate_job):
    jid = script_gate_job["job_id"]
    script_path = script_gate_job["artifacts"]["script"]
    backup = script_path.replace("script.json", "script_original.json")

    res = client.put(
        f"/api/jobs/{jid}/review",
        json={"gate": "script", "segments": [{"index": 0, "text": "Này Mít Bít,"}]},
    )

    assert res.status_code == 200
    data = _load(script_path)
    assert data["segments"][0]["translated_text"] == "Này Mít Bít,"
    assert data["content"] == "Này Mít Bít, nếu tôi đưa anh máy ảnh này,"
    # Bản lưu giữ đúng nội dung LLM sinh ra trước khi sửa tay
    assert _load(backup)["segments"][0]["translated_text"] == "Này MrBeast,"


def test_approve_script_gate_resumes_synthesizing(client, script_gate_job):
    jid = script_gate_job["job_id"]

    res = client.post(f"/api/jobs/{jid}/review/approve", json={"gate": "script"})

    assert res.status_code == 202
    assert res.json()["resumed_status"] == "synthesizing"

    import pipeline

    after = pipeline.read_job(jid)
    assert after["status"] == "synthesizing"
    assert after["review_gate"] is None
    assert after["review_gates"]["script"]["approved_at"] is not None
    # Bất biến: duyệt chốt 2 ⟹ chốt 1 đã duyệt trước đó
    assert after["review_gates"]["transcript"]["approved_at"] is not None


# ─── Sinh lại kịch bản (US4) ─────────────────────────────────────────────────


def test_regenerate_resets_script_and_resumes_scripting(client, script_gate_job):
    """
    FR-020: xoá kịch bản cũ, quay về bước scripting để sinh lại từ lời thoại đã
    duyệt, và lời thoại đã duyệt KHÔNG bị thay đổi.
    """
    jid = script_gate_job["job_id"]
    script_path = Path(script_gate_job["artifacts"]["script"])
    reviewed_path = script_gate_job["artifacts"]["transcript_reviewed"]
    reviewed_before = _load(reviewed_path)

    # Có sửa tay trước đó (tạo cả script_original.json)
    client.put(
        f"/api/jobs/{jid}/review",
        json={"gate": "script", "segments": [{"index": 0, "text": "Bản sửa tay"}]},
    )

    res = client.post(f"/api/jobs/{jid}/review/regenerate")

    assert res.status_code == 202
    assert res.json()["regenerated_count"] == 1

    import pipeline

    after = pipeline.read_job(jid)
    assert after["status"] == "scripting"
    assert after["review_gate"] is None
    assert after["review_gates"]["script"]["approved_at"] is None
    assert after["review_gates"]["script"]["edited"] is False
    # script.json + bản lưu bị xoá để generate_script() thực sự sinh lại
    assert not script_path.exists()
    assert not (script_path.parent / "script_original.json").exists()
    # Lời thoại đã duyệt KHÔNG bị chạm tới
    assert _load(reviewed_path) == reviewed_before
    # Pipeline được khởi động lại đúng một lần
    assert len(client.started) == 1  # type: ignore[attr-defined]
    assert client.started[0]["job_id"] == jid  # type: ignore[attr-defined]


def test_regenerate_rejected_at_transcript_gate(client, make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    res = client.post(f"/api/jobs/{job['job_id']}/review/regenerate")

    assert res.status_code == 409
    assert "chốt kịch bản" in res.json()["error"]
    assert len(client.started) == 0  # type: ignore[attr-defined]


def test_regenerate_409_when_not_awaiting(client, make_job):
    job = make_job(status="merging")

    res = client.post(f"/api/jobs/{job['job_id']}/review/regenerate")

    assert res.status_code == 409


def test_regenerate_409_when_another_job_processing(client, script_gate_job, make_job):
    make_job(job_id="job-busy-2", status="merging")

    res = client.post(f"/api/jobs/{script_gate_job['job_id']}/review/regenerate")

    assert res.status_code == 409
    assert res.json()["running_job_id"] == "job-busy-2"


# ─── vùng phụ đề gốc do người dùng tự khoanh tại chốt lời thoại (009) ───────


def test_put_review_saves_hardsub_box(client, make_job, tmp_jobs_dir):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
        extra={"hardsub_blur_enabled": True},
    )

    res = client.put(
        f"/api/jobs/{job['job_id']}/review",
        json={
            "gate": "transcript",
            "segments": [],
            "hardsub_box": {"x": 10, "y": 700, "w": 200, "h": 40},
            "hardsub_no_ranges": "0:00-0:05",
        },
    )

    assert res.status_code == 200
    import pipeline

    updated = pipeline.read_job(job["job_id"])
    assert updated["hardsub_box"] == {"x": 10, "y": 700, "w": 200, "h": 40}
    assert updated["hardsub_no_ranges"] == "0:00-0:05"


def test_put_review_hardsub_box_400_when_feature_disabled(client, make_job):
    """FR-013: job không bật hardsub_blur_enabled nhưng vẫn gửi hardsub_box → 400."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
        extra={"hardsub_blur_enabled": False},
    )

    res = client.put(
        f"/api/jobs/{job['job_id']}/review",
        json={
            "gate": "transcript",
            "segments": [],
            "hardsub_box": {"x": 10, "y": 700, "w": 200, "h": 40},
        },
    )

    assert res.status_code == 400


def test_approve_transcript_gate_400_when_hardsub_box_missing(client, make_job, tmp_jobs_dir):
    """Job bật hardsub_blur_enabled, khung hình đại diện đã trích, nhưng người
    dùng chưa khoanh vùng nào → chặn phê duyệt (khác US3: chỉ bỏ qua khi
    KHÔNG trích được khung hình, không phải khi có khung hình mà chưa khoanh)."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
        extra={"hardsub_blur_enabled": True},
    )
    job_dir = tmp_jobs_dir / job["job_id"]
    (job_dir / "hardsub_frame.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    job["artifacts"]["hardsub_frame"] = str(job_dir / "hardsub_frame.png")
    import pipeline

    pipeline._write_job(job["job_id"], job)

    res = client.post(
        f"/api/jobs/{job['job_id']}/review/approve", json={"gate": "transcript"}
    )

    assert res.status_code == 400


# ─── 010-topic-video-generation: chốt outline (job_type="generate") ─────────
#
# T040: route /review/approve dùng CHUNG cho cả 2 job_type — job "generate"
# KHÔNG được đi qua update_job_status()/start_job() của luồng dub (VALID_
# TRANSITIONS không có "sourcing_assets", source_url/script_mode không tồn
# tại trên job này → sẽ lỗi nếu code vẫn giả định luồng dub).


def test_approve_outline_gate_resumes_generate_job(client, make_generate_job, monkeypatch):
    from web.backend import generate_jobs_api

    started_generate: list[str] = []
    monkeypatch.setattr(
        generate_jobs_api, "start_generate_job", lambda job_id: started_generate.append(job_id)
    )

    job = make_generate_job(
        job_id="job-gen-review-approve",
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=[
            {"index": 0, "narration_text": "Câu 1", "image_query": "q1", "image_path": None, "voice_path": None, "duration": None},
        ],
        review_gates={"outline": {"reached_at": "2026-08-01T00:00:00+00:00"}},
    )

    res = client.post(f"/api/jobs/{job['job_id']}/review/approve", json={"gate": "outline"})

    assert res.status_code == 202
    assert res.json()["resumed_status"] == "sourcing_assets"

    from pipeline import read_job

    saved = read_job(job["job_id"])
    assert saved["status"] == "sourcing_assets"
    assert saved["review_gate"] is None
    assert saved["review_gates"]["outline"]["approved_at"] is not None

    # Job "generate" phải khởi động qua generate_jobs_api.start_generate_job()
    # — KHÔNG phải review_api.start_job() (luồng dub, sẽ KeyError vì job này
    # không có source_url/script_mode)
    assert started_generate == [job["job_id"]]
    assert len(client.started) == 0  # type: ignore[attr-defined]


def test_approve_outline_gate_twice_only_runs_once(client, make_generate_job, monkeypatch):
    from web.backend import generate_jobs_api

    monkeypatch.setattr(generate_jobs_api, "start_generate_job", lambda job_id: None)

    job = make_generate_job(
        job_id="job-gen-review-twice",
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=[
            {"index": 0, "narration_text": "Câu 1", "image_query": "q1", "image_path": None, "voice_path": None, "duration": None},
        ],
    )
    url = f"/api/jobs/{job['job_id']}/review/approve"

    first = client.post(url, json={"gate": "outline"})
    second = client.post(url, json={"gate": "outline"})

    assert first.status_code == 202
    assert second.status_code == 409

"""
tests/unit/test_rerun_from_step.py — Quay lại một bước trước đó để thử lại,
thay vì tạo job mới (010-rerun-from-step).

Bao phủ: xoá đúng artifact/file của bước target + mọi bước sau; giữ nguyên
artifact của các bước TRƯỚC target; reset chốt kiểm duyệt (008) khi cần;
guard API 409 khi job đang xử lý hoặc có job khác đang chạy.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import pipeline
from review import gates
from web.backend import auth, jobs_api


@pytest.fixture()
def client(tmp_jobs_dir, monkeypatch):
    from web.backend.main import app

    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)

    started: list[dict] = []

    def fake_start_job(url, script_mode, job_id=None, **kwargs):
        started.append({"url": url, "script_mode": script_mode, "job_id": job_id, **kwargs})

    monkeypatch.setattr(jobs_api, "start_job", fake_start_job)

    c = TestClient(app)
    c.started = started  # type: ignore[attr-defined]
    return c


def _make_done_job(make_job, tmp_jobs_dir):
    """Job 'done' đầy đủ artifact ở mọi bước, để test rerun xoá đúng phần cần xoá."""
    job = make_job(
        status="done",
        script_mode="translate",
        script_segments=[
            {"start": 0.0, "end": 2.0, "source_text": "hi", "translated_text": "chào"}
        ],
    )
    job_dir = tmp_jobs_dir / job["job_id"]

    (job_dir / "source.mp4").write_bytes(b"src")
    (job_dir / "transcript.json").write_text(json.dumps({"segments": []}))
    (job_dir / "voice.wav").write_bytes(b"voice")
    (job_dir / "voice_timeline.json").write_text("{}")
    (job_dir / "output.mp4").write_bytes(b"out")
    (job_dir / "background.wav").write_bytes(b"bg")

    job["artifacts"]["source_video"] = str(job_dir / "source.mp4")
    job["artifacts"]["transcript"] = str(job_dir / "transcript.json")
    job["artifacts"]["voice_track"] = str(job_dir / "voice.wav")
    job["artifacts"]["voice_timeline"] = str(job_dir / "voice_timeline.json")
    job["artifacts"]["output_video"] = str(job_dir / "output.mp4")
    job["artifacts"]["background_audio"] = str(job_dir / "background.wav")
    job["warnings"]["duration_mismatch"] = True
    job["warnings"]["tts_segments_failed"] = True
    job["tts_failed_segments"] = 2
    pipeline._write_job(job["job_id"], job)
    return pipeline.read_job(job["job_id"]), job_dir


# ─── pipeline.rerun_from_step() ──────────────────────────────────────────────


def test_rerun_from_merging_only_clears_merging_artifacts(make_job, tmp_jobs_dir):
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)

    updated = pipeline.rerun_from_step(job["job_id"], "merging")

    assert updated["status"] == "merging"
    # Bước TRƯỚC merging giữ nguyên
    assert updated["artifacts"]["source_video"] is not None
    assert updated["artifacts"]["transcript"] is not None
    assert updated["artifacts"]["voice_track"] is not None
    # Bước merging bị xoá
    assert updated["artifacts"]["output_video"] is None
    assert updated["artifacts"]["background_audio"] is None
    assert updated["warnings"]["duration_mismatch"] is False
    assert not (job_dir / "output.mp4").exists()
    assert not (job_dir / "background.wav").exists()
    # File bước trước KHÔNG bị xoá
    assert (job_dir / "voice.wav").exists()


def test_rerun_from_transcribing_clears_all_downstream(make_job, tmp_jobs_dir):
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)

    updated = pipeline.rerun_from_step(job["job_id"], "transcribing")

    assert updated["status"] == "transcribing"
    assert updated["artifacts"]["source_video"] is not None  # downloading giữ nguyên
    assert updated["artifacts"]["transcript"] is None
    assert updated["artifacts"]["voice_track"] is None
    assert updated["artifacts"]["output_video"] is None
    assert not (job_dir / "transcript.json").exists()
    assert not (job_dir / "voice.wav").exists()
    assert not (job_dir / "output.mp4").exists()
    assert (job_dir / "source.mp4").exists()


def test_rerun_resets_tts_warning_and_counter(make_job, tmp_jobs_dir):
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)

    updated = pipeline.rerun_from_step(job["job_id"], "synthesizing")

    assert updated["warnings"]["tts_segments_failed"] is False
    assert updated["tts_failed_segments"] == 0


def test_rerun_from_synthesizing_clears_cached_segment_units(make_job, tmp_jobs_dir):
    """
    Bug thật: tts/segment_synthesizer.py resume theo từng nhịp bằng cách tái
    dùng file segments/unit_*.wav đã tồn tại — cache đó KHÔNG phân biệt theo
    voice_id/provider. Chạy lại kèm đổi giọng mà không xoá thư mục này thì
    giọng KHÔNG hề đổi dù job.json đã ghi đúng giọng mới.
    """
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)
    segments_dir = job_dir / "segments"
    segments_dir.mkdir()
    (segments_dir / "unit_0000.wav").write_bytes(b"giong cu")

    pipeline.rerun_from_step(job["job_id"], "synthesizing")

    assert not segments_dir.exists()


def test_rerun_from_synthesizing_does_not_touch_transcribing_files(make_job, tmp_jobs_dir):
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)

    updated = pipeline.rerun_from_step(job["job_id"], "synthesizing")

    assert updated["artifacts"]["transcript"] is not None
    assert (job_dir / "transcript.json").exists()


def test_rerun_from_merging_clears_cached_subtitle_frame_images(make_job, tmp_jobs_dir):
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)
    frames_dir = job_dir / "subtitle_frames"
    frames_dir.mkdir()
    (frames_dir / "cue_0000.png").write_bytes(b"anh cu")

    pipeline.rerun_from_step(job["job_id"], "merging")

    assert not frames_dir.exists()


def test_rerun_resets_approved_gates_when_going_before_them(make_job, tmp_jobs_dir):
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)
    job = pipeline.read_job(job["job_id"])
    gates.mark_reached(job, gates.GATE_TRANSCRIPT, 3)
    gates.mark_approved(job, gates.GATE_TRANSCRIPT)
    gates.mark_reached(job, gates.GATE_SCRIPT, 3)
    gates.mark_approved(job, gates.GATE_SCRIPT)
    pipeline._write_job(job["job_id"], job)

    updated = pipeline.rerun_from_step(job["job_id"], "scripting")

    # Chốt lời thoại (TRƯỚC scripting) giữ nguyên đã duyệt
    assert "transcript" in updated["review_gates"]
    assert updated["review_gates"]["transcript"]["approved_at"] is not None
    # Chốt kịch bản (TỪ scripting trở đi) mất hiệu lực, phải duyệt lại
    assert "script" not in updated["review_gates"]


def test_rerun_invalid_step_raises(make_job, tmp_jobs_dir):
    job, _ = _make_done_job(make_job, tmp_jobs_dir)

    with pytest.raises(ValueError):
        pipeline.rerun_from_step(job["job_id"], "merged")  # sai tên


# ─── API endpoint ────────────────────────────────────────────────────────────


def test_rerun_endpoint_success(client, make_job, tmp_jobs_dir):
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)

    res = client.post(f"/api/jobs/{job['job_id']}/rerun-from", json={"step": "merging"})

    assert res.status_code == 202
    assert res.json()["resumed_status"] == "merging"
    after = pipeline.read_job(job["job_id"])
    assert after["status"] == "merging"
    assert len(client.started) == 1  # type: ignore[attr-defined]
    assert client.started[0]["job_id"] == job["job_id"]  # type: ignore[attr-defined]


def test_rerun_endpoint_400_invalid_step(client, make_job, tmp_jobs_dir):
    job, _ = _make_done_job(make_job, tmp_jobs_dir)

    res = client.post(f"/api/jobs/{job['job_id']}/rerun-from", json={"step": "pending"})

    assert res.status_code == 400
    assert len(client.started) == 0  # type: ignore[attr-defined]


def test_rerun_endpoint_409_when_job_actively_processing(client, make_job, tmp_jobs_dir):
    job = make_job(status="synthesizing")

    res = client.post(f"/api/jobs/{job['job_id']}/rerun-from", json={"step": "transcribing"})

    assert res.status_code == 409
    assert len(client.started) == 0  # type: ignore[attr-defined]


def test_rerun_endpoint_409_when_another_job_processing(client, make_job, tmp_jobs_dir):
    job, _ = _make_done_job(make_job, tmp_jobs_dir)
    make_job(job_id="job-busy", status="merging")

    res = client.post(f"/api/jobs/{job['job_id']}/rerun-from", json={"step": "scripting"})

    assert res.status_code == 409
    assert res.json()["running_job_id"] == "job-busy"


def test_rerun_endpoint_404_when_job_missing(client):
    res = client.post("/api/jobs/khong-ton-tai/rerun-from", json={"step": "merging"})

    assert res.status_code == 404


# ─── Đổi giọng đọc rồi chạy lại bước synthesizing ────────────────────────────


def test_rerun_endpoint_changes_voice_before_rerunning(client, make_job, tmp_jobs_dir):
    job, _ = _make_done_job(make_job, tmp_jobs_dir)

    res = client.post(
        f"/api/jobs/{job['job_id']}/rerun-from",
        json={"step": "synthesizing", "tts_provider": "lucyai", "voice_id": "giong-moi"},
    )

    assert res.status_code == 202
    after = pipeline.read_job(job["job_id"])
    assert after["tts_provider"] == "lucyai"
    assert after["voice_id"] == "giong-moi"
    # start_job() phải nhận đúng giọng MỚI, không phải giọng cũ trước khi đổi
    assert client.started[0]["tts_provider"] == "lucyai"  # type: ignore[attr-defined]
    assert client.started[0]["voice_id"] == "giong-moi"  # type: ignore[attr-defined]


def test_rerun_endpoint_400_invalid_tts_provider(client, make_job, tmp_jobs_dir):
    job, _ = _make_done_job(make_job, tmp_jobs_dir)

    res = client.post(
        f"/api/jobs/{job['job_id']}/rerun-from",
        json={"step": "synthesizing", "tts_provider": "khong-hop-le"},
    )

    assert res.status_code == 400
    assert len(client.started) == 0  # type: ignore[attr-defined]


def test_rerun_endpoint_voice_change_survives_artifact_reset(client, make_job, tmp_jobs_dir):
    """voice_id không bị rerun_from_step() xoá theo — nó không thuộc artifact
    của bước synthesizing (voice.wav mới sẽ được tổng hợp lại đúng giọng mới)."""
    job, job_dir = _make_done_job(make_job, tmp_jobs_dir)

    res = client.post(
        f"/api/jobs/{job['job_id']}/rerun-from",
        json={"step": "downloading", "voice_id": "giong-moi"},
    )

    assert res.status_code == 202
    after = pipeline.read_job(job["job_id"])
    assert after["voice_id"] == "giong-moi"

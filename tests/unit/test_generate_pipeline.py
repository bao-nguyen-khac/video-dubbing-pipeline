"""
tests/unit/test_generate_pipeline.py — create_generate_job()/
generate_status_from_artifacts() của tính năng "Tạo video từ chủ đề"
(010-topic-video-generation, data-model.md §1/§5).

Không gọi 9router/Pexels/TTS/hyperframes thật — chỉ test logic thuần trên
job.json + file JSON tạm (Constitution VI).
"""

from __future__ import annotations

import json

import pytest

import generate_pipeline


def _write_scenes(job_dir, scenes: list[dict]) -> str:
    path = job_dir / "scenes.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"source": "outline.json", "scenes": scenes}, f)
    return str(path)


# ─── create_generate_job ──────────────────────────────────────────────────────


def test_create_generate_job_writes_expected_shape(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("tổng quan về tiền tệ", job_id="job-gen-001")

    assert job["job_id"] == "job-gen-001"
    assert job["job_type"] == "generate"
    assert job["topic"] == "tổng quan về tiền tệ"
    assert job["supervised"] is False
    assert job["status"] == "pending"
    assert job["review_gate"] is None
    assert job["review_gates"] == {}
    assert job["artifacts"] == {"outline": None, "scenes": None, "output_video": None}
    assert job["error"] is None

    # Job cũ (luồng dub) không có field này — job "generate" MUST không mang
    # theo field đặc thù dub, tránh nhầm lẫn khi code khác đọc job.json
    assert "source_url" not in job
    assert "platform" not in job

    on_disk = tmp_jobs_dir / "job-gen-001" / "job.json"
    assert on_disk.exists()
    with open(on_disk, encoding="utf-8") as f:
        assert json.load(f)["job_type"] == "generate"


def test_create_generate_job_supervised_flag(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("chủ đề x", job_id="job-gen-002", supervised=True)
    assert job["supervised"] is True


def test_create_generate_job_generates_job_id_when_missing(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("chủ đề y")
    assert job["job_id"]
    assert (tmp_jobs_dir / job["job_id"] / "job.json").exists()


@pytest.mark.parametrize("topic", ["", "   ", "\n\t"])
def test_create_generate_job_rejects_blank_topic(tmp_jobs_dir, topic):
    with pytest.raises(ValueError):
        generate_pipeline.create_generate_job(topic, job_id="job-gen-blank")


# ─── generate_status_from_artifacts ──────────────────────────────────────────


def test_status_from_artifacts_no_outline_returns_outlining(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("x", job_id="job-gen-a")
    assert generate_pipeline.generate_status_from_artifacts(job) == "outlining"


def test_status_from_artifacts_outline_no_scenes_returns_scripting(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("x", job_id="job-gen-b")
    job["artifacts"]["outline"] = str(tmp_jobs_dir / "job-gen-b" / "outline.json")
    assert generate_pipeline.generate_status_from_artifacts(job) == "scripting"


def test_status_from_artifacts_scenes_missing_images_returns_sourcing_assets(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("x", job_id="job-gen-c")
    job_dir = tmp_jobs_dir / "job-gen-c"
    job["artifacts"]["outline"] = str(job_dir / "outline.json")
    job["artifacts"]["scenes"] = _write_scenes(
        job_dir,
        [
            {"index": 0, "narration_text": "a", "image_path": None, "voice_path": None, "duration": None},
            {"index": 1, "narration_text": "b", "image_path": "img1.jpg", "voice_path": None, "duration": None},
        ],
    )
    assert generate_pipeline.generate_status_from_artifacts(job) == "sourcing_assets"


def test_status_from_artifacts_images_done_missing_voice_returns_synthesizing(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("x", job_id="job-gen-d")
    job_dir = tmp_jobs_dir / "job-gen-d"
    job["artifacts"]["outline"] = str(job_dir / "outline.json")
    job["artifacts"]["scenes"] = _write_scenes(
        job_dir,
        [
            {"index": 0, "narration_text": "a", "image_path": "img0.jpg", "voice_path": None, "duration": None},
        ],
    )
    assert generate_pipeline.generate_status_from_artifacts(job) == "synthesizing"


def test_status_from_artifacts_all_scenes_ready_missing_output_returns_rendering(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("x", job_id="job-gen-e")
    job_dir = tmp_jobs_dir / "job-gen-e"
    job["artifacts"]["outline"] = str(job_dir / "outline.json")
    job["artifacts"]["scenes"] = _write_scenes(
        job_dir,
        [
            {"index": 0, "narration_text": "a", "image_path": "img0.jpg", "voice_path": "v0.wav", "duration": 3.1},
        ],
    )
    assert generate_pipeline.generate_status_from_artifacts(job) == "rendering"


def test_status_from_artifacts_everything_done_returns_done(tmp_jobs_dir):
    job = generate_pipeline.create_generate_job("x", job_id="job-gen-f")
    job_dir = tmp_jobs_dir / "job-gen-f"
    job["artifacts"]["outline"] = str(job_dir / "outline.json")
    job["artifacts"]["scenes"] = _write_scenes(
        job_dir,
        [
            {"index": 0, "narration_text": "a", "image_path": "img0.jpg", "voice_path": "v0.wav", "duration": 3.1},
        ],
    )
    job["artifacts"]["output_video"] = str(job_dir / "output.mp4")
    assert generate_pipeline.generate_status_from_artifacts(job) == "done"


def test_status_from_artifacts_empty_scene_list_falls_through_to_rendering(tmp_jobs_dir):
    """0 scene là trường hợp biên hợp lệ về mặt logic (all([]) == True) — không
    phải trường hợp cần chặn ở tầng này."""
    job = generate_pipeline.create_generate_job("x", job_id="job-gen-g")
    job_dir = tmp_jobs_dir / "job-gen-g"
    job["artifacts"]["outline"] = str(job_dir / "outline.json")
    job["artifacts"]["scenes"] = _write_scenes(job_dir, [])
    assert generate_pipeline.generate_status_from_artifacts(job) == "rendering"

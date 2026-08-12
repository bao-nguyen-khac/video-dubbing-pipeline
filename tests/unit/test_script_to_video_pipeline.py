"""
tests/unit/test_script_to_video_pipeline.py — create_script_to_video_project()/
part_status_from_artifacts()/rerun_part_from_step()/
find_running_script_to_video_slug() của tính năng "Script-to-video" v3
(nhiều PHẦN/part, character bible, upload 1 file merge.mp4/phần).

Không gọi 9router/TTS/ffmpeg thật — chỉ test logic thuần trên project.json/
part script.json (Constitution VI).
"""

from __future__ import annotations

import pytest

import script_to_video_pipeline as s2v
from tests.unit.conftest import _part_screen


# ─── create_script_to_video_project ───────────────────────────────────────────


def test_create_project_writes_expected_shape(tmp_jobs_dir):
    project = s2v.create_script_to_video_project(
        "Kỹ sư hệ thống quản lý đàn robot khai thác", num_parts=2, target_screens_per_part=10, slug="proj-001"
    )

    assert project["slug"] == "proj-001"
    assert project["premise"] == "Kỹ sư hệ thống quản lý đàn robot khai thác"
    assert project["num_parts"] == 2
    assert project["target_screens_per_part"] == 10
    assert project["series_notes"] is None
    assert project["status"] == "pending"
    assert project["error"] is None

    project_dir = s2v.project_dir_for("proj-001")
    assert (project_dir / "project.json").exists()
    assert project_dir.parent == s2v.PROJECT_ROOT_DIR
    # Chưa sinh kịch bản — chưa có character.json/part-N/ nào
    assert not (project_dir / "character.json").exists()
    assert not (project_dir / "part-1").exists()


def test_create_project_slug_from_premise_when_not_given(tmp_jobs_dir):
    project = s2v.create_script_to_video_project("Phi công EVA sửa robot ngoài không gian!!")
    project_dir = s2v.project_dir_for(project["slug"])
    assert project["slug"] == "phi-cong-eva-sua-robot-ngoai-khong-gian"
    assert project_dir.parent == s2v.PROJECT_ROOT_DIR


def test_create_project_dedupes_slug_collision(tmp_jobs_dir):
    project1 = s2v.create_script_to_video_project("chủ đề trùng")
    project2 = s2v.create_script_to_video_project("chủ đề trùng")
    assert project1["slug"] != project2["slug"]
    assert project2["slug"] == f"{project1['slug']}-2"


@pytest.mark.parametrize("premise", ["", "   ", "\n\t"])
def test_create_project_rejects_blank_premise(tmp_jobs_dir, premise):
    with pytest.raises(ValueError):
        s2v.create_script_to_video_project(premise, slug="proj-blank")


def test_create_project_rejects_non_positive_num_parts(tmp_jobs_dir):
    with pytest.raises(ValueError):
        s2v.create_script_to_video_project("x", num_parts=0, slug="proj-bad-parts")


def test_create_project_rejects_non_positive_screens_per_part(tmp_jobs_dir):
    with pytest.raises(ValueError):
        s2v.create_script_to_video_project("x", target_screens_per_part=0, slug="proj-bad-screens")


# ─── part_status_from_artifacts ────────────────────────────────────────────────


def test_part_status_missing_upload_returns_awaiting_upload(tmp_jobs_dir):
    s2v.create_script_to_video_project("x", num_parts=1, slug="proj-a")
    part_dir = s2v.part_dir_for("proj-a", 0)
    part_dir.mkdir(parents=True)
    part = {"screens": [_part_screen(0)], "uploaded_video_path": None}
    assert s2v.part_status_from_artifacts(part, part_dir) == "awaiting_upload"


def test_part_status_uploaded_missing_voice_returns_synthesizing(tmp_jobs_dir):
    s2v.create_script_to_video_project("x", num_parts=1, slug="proj-b")
    part_dir = s2v.part_dir_for("proj-b", 0)
    part_dir.mkdir(parents=True)
    part = {"screens": [_part_screen(0)], "uploaded_video_path": "video-raw/merge.mp4"}
    assert s2v.part_status_from_artifacts(part, part_dir) == "synthesizing"


def test_part_status_voice_done_missing_output_returns_merging(tmp_jobs_dir):
    s2v.create_script_to_video_project("x", num_parts=1, slug="proj-c")
    part_dir = s2v.part_dir_for("proj-c", 0)
    part_dir.mkdir(parents=True)
    part = {
        "screens": [_part_screen(0, voice_path="voice/screen-1.wav", voice_duration=8.0)],
        "uploaded_video_path": "video-raw/merge.mp4",
    }
    assert s2v.part_status_from_artifacts(part, part_dir) == "merging"


def test_part_status_output_exists_returns_done(tmp_jobs_dir):
    s2v.create_script_to_video_project("x", num_parts=1, slug="proj-d")
    part_dir = s2v.part_dir_for("proj-d", 0)
    part_dir.mkdir(parents=True)
    (part_dir / "output.mp4").write_bytes(b"fake")
    part = {
        "screens": [_part_screen(0, voice_path="voice/screen-1.wav", voice_duration=8.0)],
        "uploaded_video_path": "video-raw/merge.mp4",
    }
    assert s2v.part_status_from_artifacts(part, part_dir) == "done"


# ─── find_running_script_to_video_slug ─────────────────────────────────────────


def test_find_running_none_when_everything_idle(tmp_jobs_dir, make_script_to_video_project):
    make_script_to_video_project(
        slug="proj-idle-1", status="ready", num_parts=1,
        parts={0: {"status": "awaiting_review"}},
    )
    make_script_to_video_project(
        slug="proj-idle-2", status="ready", num_parts=1,
        parts={0: {"status": "done"}},
    )
    make_script_to_video_project(slug="proj-failed", status="failed")

    assert s2v.find_running_script_to_video_slug() is None


def test_find_running_detects_project_scripting(tmp_jobs_dir, make_script_to_video_project):
    make_script_to_video_project(slug="proj-idle", status="ready", num_parts=1, parts={0: {"status": "done"}})
    make_script_to_video_project(slug="proj-busy", status="scripting", num_parts=1)

    assert s2v.find_running_script_to_video_slug() == "proj-busy"


def test_find_running_detects_part_synthesizing(tmp_jobs_dir, make_script_to_video_project):
    make_script_to_video_project(
        slug="proj-busy", status="ready", num_parts=2,
        parts={0: {"status": "done"}, 1: {"status": "synthesizing"}},
    )
    assert s2v.find_running_script_to_video_slug() == "proj-busy"


def test_find_running_detects_part_merging(tmp_jobs_dir, make_script_to_video_project):
    make_script_to_video_project(
        slug="proj-busy", status="ready", num_parts=1, parts={0: {"status": "merging"}}
    )
    assert s2v.find_running_script_to_video_slug() == "proj-busy"


# ─── rerun_part_from_step ───────────────────────────────────────────────────────


def test_rerun_synthesizing_clears_voice_keeps_upload(tmp_jobs_dir, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-r1", num_parts=1, status="ready",
        parts={
            0: {
                "status": "done",
                "uploaded_video_path": "video-raw/merge.mp4",
                "voice_full_path": "voice/full-narration.wav",
                "voice_full_duration": 76.0,
                "screen_items": [_part_screen(0, voice_path="voice/screen-1.wav", voice_duration=8.0)],
            }
        },
    )
    part_dir = s2v.part_dir_for(project["slug"], 0)
    (part_dir / "output.mp4").write_bytes(b"fake")
    voice_dir = part_dir / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "screen-1.wav").write_bytes(b"fake wav")
    (voice_dir / "full-narration.wav").write_bytes(b"fake full")

    result = s2v.rerun_part_from_step(project["slug"], 0, "synthesizing")

    assert result["status"] == "synthesizing"
    assert result["screens"][0]["voice_path"] is None
    assert result["screens"][0]["voice_duration"] is None
    assert result["voice_full_path"] is None
    assert result["uploaded_video_path"] == "video-raw/merge.mp4"  # upload giữ nguyên
    assert not (part_dir / "output.mp4").exists()
    assert not voice_dir.exists()


def test_rerun_merging_keeps_voice_clears_output(tmp_jobs_dir, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-r2", num_parts=1, status="ready",
        parts={
            0: {
                "status": "done",
                "uploaded_video_path": "video-raw/merge.mp4",
                "voice_full_path": "voice/full-narration.wav",
                "voice_full_duration": 76.0,
                "screen_items": [_part_screen(0, voice_path="voice/screen-1.wav", voice_duration=8.0)],
            }
        },
    )
    part_dir = s2v.part_dir_for(project["slug"], 0)
    (part_dir / "output.mp4").write_bytes(b"fake")

    result = s2v.rerun_part_from_step(project["slug"], 0, "merging")

    assert result["status"] == "merging"
    assert result["screens"][0]["voice_path"] == "voice/screen-1.wav"  # voice từng screen giữ nguyên
    assert result["voice_full_path"] is None  # full-narration bị xoá, ghép lại
    assert not (part_dir / "output.mp4").exists()


def test_rerun_invalid_step_raises(tmp_jobs_dir, make_script_to_video_project):
    project = make_script_to_video_project(slug="proj-r3", num_parts=1, parts={0: {"status": "done"}})
    with pytest.raises(ValueError):
        s2v.rerun_part_from_step(project["slug"], 0, "scripting")

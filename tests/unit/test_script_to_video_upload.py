"""
tests/unit/test_script_to_video_upload.py — POST /api/script-to-video-jobs/
{slug}/parts/{part_index}/upload: kiểm tra trạng thái phần, và việc upload
`merge.mp4` tự đẩy status sang "synthesizing" (v3: 1 file/phần, không còn
per-screen như v2).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import script_to_video_pipeline as s2v
from web.backend import auth, script_to_video_jobs_api
from tests.unit.conftest import _part_screen


@pytest.fixture()
def client(tmp_jobs_dir, monkeypatch):
    from web.backend.main import app

    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)

    started_parts: list[tuple[str, int]] = []
    monkeypatch.setattr(
        script_to_video_jobs_api,
        "start_part_pipeline",
        lambda slug, part_index: started_parts.append((slug, part_index)),
    )

    c = TestClient(app)
    c.started_parts = started_parts  # type: ignore[attr-defined]
    return c


def _upload(client, slug, part_index=0, filename="merge.mp4", content=b"fake video bytes"):
    return client.post(
        f"/api/script-to-video-jobs/{slug}/parts/{part_index}/upload",
        files={"file": (filename, content, "video/mp4")},
    )


def test_upload_rejects_when_not_awaiting_upload(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-up1", num_parts=1, parts={0: {"status": "awaiting_review", "screen_items": [_part_screen(0)]}}
    )
    res = _upload(client, project["slug"])
    assert res.status_code == 409


def test_upload_404_for_missing_part(client, make_script_to_video_project):
    project = make_script_to_video_project(slug="proj-up2", num_parts=1)
    res = _upload(client, project["slug"], part_index=5)
    assert res.status_code == 404


def test_upload_rejects_non_video_content_type(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-up3", num_parts=1, parts={0: {"status": "awaiting_upload", "screen_items": [_part_screen(0)]}}
    )
    res = client.post(
        f"/api/script-to-video-jobs/{project['slug']}/parts/0/upload",
        files={"file": ("merge.txt", b"not a video", "text/plain")},
    )
    assert res.status_code == 400


def test_upload_triggers_synthesizing(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-up4", num_parts=1,
        parts={0: {"status": "awaiting_upload", "screen_items": [_part_screen(0), _part_screen(1)]}},
    )

    res = _upload(client, project["slug"])

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "synthesizing"
    assert client.started_parts == [(project["slug"], 0)]

    stored = s2v.read_part(project["slug"], 0)
    assert stored["status"] == "synthesizing"
    assert stored["uploaded_video_path"]


def test_upload_can_replace_after_first_upload(client, make_script_to_video_project):
    """Upload lại (sửa nhầm file) vẫn được chấp nhận SAU lần đầu — không chỉ
    lúc "awaiting_upload" — vì status chuyển "synthesizing" ngay sau lần đầu."""
    project = make_script_to_video_project(
        slug="proj-up5", num_parts=1, parts={0: {"status": "awaiting_upload", "screen_items": [_part_screen(0)]}}
    )

    first = _upload(client, project["slug"], filename="first.mp4", content=b"first content")
    second = _upload(client, project["slug"], filename="second.mp4", content=b"second content, longer")

    assert first.status_code == 200
    assert second.status_code == 200

    video_raw_dir = s2v.part_dir_for(project["slug"], 0) / "video-raw"
    clips = list(video_raw_dir.glob("merge.*"))
    assert len(clips) == 1  # file cũ bị xoá, không tồn tại song song 2 file
    assert clips[0].read_bytes() == b"second content, longer"


def test_upload_rejects_while_awaiting_review(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-up6", num_parts=1, parts={0: {"status": "awaiting_review", "screen_items": [_part_screen(0)]}}
    )
    res = _upload(client, project["slug"])
    assert res.status_code == 409

    video_raw_dir = s2v.part_dir_for(project["slug"], 0) / "video-raw"
    clips = list(video_raw_dir.glob("merge.*"))
    assert len(clips) == 0

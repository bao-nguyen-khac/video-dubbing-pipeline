"""
tests/unit/test_script_to_video_jobs_api.py — Contract test cho endpoint
web/backend/script_to_video_jobs_api.py (v3: nhiều phần/part, character
bible, upload 1 file merge.mp4/phần).

⚠️ Constitution §VI: `start_script_to_video_job`/`start_part_pipeline` bị
mock hoàn toàn — không test nào ở đây chạy pipeline thật hay gọi 9router/
TTS/ffmpeg.
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

    started_projects: list[str] = []
    started_parts: list[tuple[str, int]] = []
    monkeypatch.setattr(
        script_to_video_jobs_api, "start_script_to_video_job", lambda slug: started_projects.append(slug)
    )
    monkeypatch.setattr(
        script_to_video_jobs_api,
        "start_part_pipeline",
        lambda slug, part_index: started_parts.append((slug, part_index)),
    )

    c = TestClient(app)
    c.started_projects = started_projects  # type: ignore[attr-defined]
    c.started_parts = started_parts  # type: ignore[attr-defined]
    return c


# ─── POST /api/script-to-video-jobs ───────────────────────────────────────────


def test_submit_creates_project(client):
    res = client.post(
        "/api/script-to-video-jobs",
        json={"premise": "Kỹ sư hệ thống quản lý đàn robot khai thác", "num_parts": 2},
    )

    assert res.status_code == 201
    slug = res.json()["slug"]
    assert slug

    detail = client.get(f"/api/script-to-video-jobs/{slug}").json()
    assert detail["job_type"] == "script_to_video"
    assert detail["status"] == "pending"
    assert detail["parts_total"] == 2
    assert client.started_projects == [slug]


def test_submit_rejects_blank_premise(client):
    res = client.post("/api/script-to-video-jobs", json={"premise": "   "})
    assert res.status_code == 400


def test_submit_conflict_when_project_scripting(client, make_script_to_video_project):
    make_script_to_video_project(slug="proj-running", status="scripting")
    res = client.post("/api/script-to-video-jobs", json={"premise": "x"})
    assert res.status_code == 409
    assert "running_job_id" in res.json()


def test_submit_conflict_when_part_processing(client, make_script_to_video_project):
    make_script_to_video_project(
        slug="proj-running", status="ready", num_parts=1, parts={0: {"status": "synthesizing"}}
    )
    res = client.post("/api/script-to-video-jobs", json={"premise": "x"})
    assert res.status_code == 409


def test_submit_not_blocked_by_dub_job(client, make_job):
    make_job(status="downloading")
    res = client.post("/api/script-to-video-jobs", json={"premise": "x"})
    assert res.status_code == 201


# ─── GET /api/script-to-video-jobs ─────────────────────────────────────────────


def test_list_returns_all_projects(client, make_script_to_video_project):
    make_script_to_video_project(slug="proj-1")
    make_script_to_video_project(slug="proj-2")
    res = client.get("/api/script-to-video-jobs")
    assert res.status_code == 200
    slugs = {j["slug"] for j in res.json()["jobs"]}
    assert slugs == {"proj-1", "proj-2"}


# ─── GET /api/script-to-video-jobs/{slug} ─────────────────────────────────────


def test_get_detail_includes_character_and_parts(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-detail", num_parts=2, status="ready",
        parts={
            0: {"title": "Phần 1", "status": "done", "screen_items": [_part_screen(0)]},
            1: {"title": "Phần 2", "status": "awaiting_review", "screen_items": [_part_screen(0), _part_screen(1)]},
        },
    )
    character_path = s2v.project_dir_for(project["slug"]) / "character.json"
    character_path.write_text(
        json.dumps({"character_name": "Erik", "role_title": "Kỹ sư", "arc_title": "Arc", "parts_summary": [], "character_description_md": "...", "ingredients": []}),
        encoding="utf-8",
    )

    detail = client.get(f"/api/script-to-video-jobs/{project['slug']}").json()

    assert detail["character"]["character_name"] == "Erik"
    assert len(detail["parts"]) == 2
    assert detail["parts"][0]["status"] == "done"
    assert detail["parts"][1]["status"] == "awaiting_review"
    assert detail["parts"][1]["screen_count"] == 2
    # Aggregate: part 2 đang chờ duyệt -> status/aggregate ưu tiên awaiting_review
    assert detail["status"] == "awaiting_review"
    assert detail["review_gate"] == "script_to_video"


def test_get_detail_404_for_missing_project(client):
    res = client.get("/api/script-to-video-jobs/does-not-exist")
    assert res.status_code == 404


# ─── Deliverables ──────────────────────────────────────────────────────────────


def test_project_deliverable_serves_character_bible(client, make_script_to_video_project):
    project = make_script_to_video_project(slug="proj-bible")
    project_dir = s2v.project_dir_for(project["slug"])
    (project_dir / "character-bible.md").write_text("# Character Bible")

    res = client.get(f"/api/script-to-video-jobs/{project['slug']}/deliverables/character-bible.md")
    assert res.status_code == 200
    assert res.text == "# Character Bible"


def test_project_deliverable_rejects_other_filenames(client, make_script_to_video_project):
    project = make_script_to_video_project(slug="proj-bible2")
    res = client.get(f"/api/script-to-video-jobs/{project['slug']}/deliverables/script.md")
    assert res.status_code == 404


def test_part_deliverable_serves_whitelisted_file(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-part-deliv", num_parts=1, parts={0: {"screen_items": [_part_screen(0)]}}
    )
    part_dir = s2v.part_dir_for(project["slug"], 0)
    (part_dir / "script.md").write_text("# Phần 1")

    res = client.get(f"/api/script-to-video-jobs/{project['slug']}/parts/0/deliverables/script.md")
    assert res.status_code == 200
    assert res.text == "# Phần 1"


def test_part_deliverable_rejects_path_traversal(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-part-deliv2", num_parts=1, parts={0: {"screen_items": [_part_screen(0)]}}
    )
    res = client.get(f"/api/script-to-video-jobs/{project['slug']}/parts/0/deliverables/../../project.json")
    assert res.status_code in (404, 400)


# ─── Chốt duyệt (theo phần) ──────────────────────────────────────────────────────


def test_review_get_returns_screens_payload(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-review", num_parts=1,
        parts={0: {"status": "awaiting_review", "screen_items": [_part_screen(0)]}},
    )
    res = client.get(f"/api/script-to-video-jobs/{project['slug']}/parts/0/review")
    assert res.status_code == 200
    body = res.json()
    assert body["gate"] == "script_to_video"
    assert len(body["screens"]) == 1
    assert body["screens"][0]["vi_voiceover_text"] == "Lời thoại screen 1."


def test_review_get_409_when_not_awaiting_review(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-review2", num_parts=1, parts={0: {"status": "awaiting_upload"}}
    )
    res = client.get(f"/api/script-to-video-jobs/{project['slug']}/parts/0/review")
    assert res.status_code == 409


def test_review_put_saves_edits_and_rerenders(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-review-put", num_parts=1,
        parts={0: {"status": "awaiting_review", "screen_items": [_part_screen(0)]}},
    )
    part_dir = s2v.part_dir_for(project["slug"], 0)

    res = client.put(
        f"/api/script-to-video-jobs/{project['slug']}/parts/0/review",
        json={"screens": [{"index": 0, "vi_voiceover_text": "Lời thoại mới."}]},
    )

    assert res.status_code == 200
    assert res.json()["saved_count"] == 1
    script_data = json.loads((part_dir / "script.json").read_text())
    assert script_data["screens"][0]["vi_voiceover_text"] == "Lời thoại mới."
    assert (part_dir / "script.md").exists()  # re-rendered


def test_review_approve_transitions_to_awaiting_upload(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-review-approve", num_parts=1,
        parts={0: {"status": "awaiting_review", "screen_items": [_part_screen(0)]}},
    )
    res = client.post(f"/api/script-to-video-jobs/{project['slug']}/parts/0/review/approve")
    assert res.status_code == 202
    assert res.json()["resumed_status"] == "awaiting_upload"
    detail = client.get(f"/api/script-to-video-jobs/{project['slug']}").json()
    assert detail["parts"][0]["status"] == "awaiting_upload"
    assert client.started_parts == []  # phê duyệt không tự chạy nền


# ─── Retry / rerun-from ──────────────────────────────────────────────────────────


def test_retry_project_only_when_failed(client, make_script_to_video_project):
    project = make_script_to_video_project(slug="proj-retry", status="ready")
    res = client.post(f"/api/script-to-video-jobs/{project['slug']}/retry")
    assert res.status_code == 409


def test_retry_project_starts_scripting(client, make_script_to_video_project):
    project = make_script_to_video_project(slug="proj-retry2", status="failed")
    res = client.post(f"/api/script-to-video-jobs/{project['slug']}/retry")
    assert res.status_code == 202
    assert client.started_projects == [project["slug"]]


def test_retry_part_only_when_failed(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-retry-part", num_parts=1, parts={0: {"status": "synthesizing"}}
    )
    res = client.post(f"/api/script-to-video-jobs/{project['slug']}/parts/0/retry")
    assert res.status_code == 409


def test_retry_part_starts_pipeline(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-retry-part2", num_parts=1, parts={0: {"status": "failed"}}
    )
    res = client.post(f"/api/script-to-video-jobs/{project['slug']}/parts/0/retry")
    assert res.status_code == 202
    assert client.started_parts == [(project["slug"], 0)]


def test_rerun_from_rejects_invalid_step(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-rerun", num_parts=1, parts={0: {"status": "done"}}
    )
    res = client.post(
        f"/api/script-to-video-jobs/{project['slug']}/parts/0/rerun-from", json={"step": "scripting"}
    )
    assert res.status_code == 400


def test_rerun_from_synthesizing(client, make_script_to_video_project):
    project = make_script_to_video_project(
        slug="proj-rerun2", num_parts=1,
        parts={
            0: {
                "status": "done",
                "uploaded_video_path": "video-raw/merge.mp4",
                "screen_items": [_part_screen(0, voice_path="voice/screen-1.wav", voice_duration=8.0)],
            }
        },
    )
    res = client.post(
        f"/api/script-to-video-jobs/{project['slug']}/parts/0/rerun-from", json={"step": "synthesizing"}
    )
    assert res.status_code == 202
    assert client.started_parts == [(project["slug"], 0)]
    detail = client.get(f"/api/script-to-video-jobs/{project['slug']}").json()
    assert detail["parts"][0]["status"] == "synthesizing"

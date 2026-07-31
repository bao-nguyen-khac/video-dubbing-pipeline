"""
tests/unit/test_hardsub_preview_endpoint.py — GET /api/jobs/{id}/hardsub-frame
(009 — khung hình đại diện để người dùng tự khoanh vùng phụ đề gốc cần mờ,
thay cho OCR tự động cũ).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.backend import auth


@pytest.fixture()
def client(tmp_jobs_dir, monkeypatch):
    from web.backend.main import app

    monkeypatch.setattr(auth, "verify_session_token", lambda token: True)
    return TestClient(app)


def test_hardsub_frame_returns_png_when_file_exists(client, make_job, tmp_jobs_dir):
    job = make_job(status="done", extra={"hardsub_blur_enabled": True})
    job_dir = tmp_jobs_dir / job["job_id"]
    (job_dir / "hardsub_frame.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")

    res = client.get(f"/api/jobs/{job['job_id']}/hardsub-frame")

    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"


def test_hardsub_frame_404_when_missing(client, make_job):
    job = make_job(status="done", extra={"hardsub_blur_enabled": True})

    res = client.get(f"/api/jobs/{job['job_id']}/hardsub-frame")

    assert res.status_code == 404


def test_hardsub_frame_404_when_job_missing(client):
    res = client.get("/api/jobs/khong-ton-tai/hardsub-frame")

    assert res.status_code == 404

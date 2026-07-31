"""
tests/unit/test_supervised_pipeline.py — State machine chế độ quản lý pipeline
(008-supervised-pipeline).

Bao phủ FR-002/SC-001 (job không bật chế độ quản lý chạy y như cũ), FR-003 (cờ
giữ nguyên qua resume/retry), FR-004 (đúng 2 chốt), và các bất biến ở
data-model.md §2.

Không chạy pipeline thật: chỉ kiểm tra state machine + job.json.
"""

from __future__ import annotations

import pytest

import pipeline
from review import gates
from web.backend.jobs_api import _job_to_detail, _job_to_summary, status_to_progress


# ─── create_job ──────────────────────────────────────────────────────────────


def test_create_job_defaults_to_unsupervised(tmp_jobs_dir):
    """FR-002: chế độ quản lý MẶC ĐỊNH TẮT."""
    job = pipeline.create_job("https://www.tiktok.com/@u/video/1", "tiktok", "translate")

    assert job["supervised"] is False
    assert job["review_gate"] is None
    assert job["review_gates"] == {}
    assert job["artifacts"]["transcript_reviewed"] is None


def test_create_job_supervised_writes_fields(tmp_jobs_dir):
    job = pipeline.create_job(
        "https://www.tiktok.com/@u/video/1", "tiktok", "translate", supervised=True
    )

    assert job["supervised"] is True
    # Cờ phải nằm trên đĩa, không chỉ trong dict trả về (FR-003, FR-007)
    assert pipeline.read_job(job["job_id"])["supervised"] is True


def test_create_job_hardsub_blur_without_supervised_raises(tmp_jobs_dir):
    """009: vùng cần mờ do người dùng tự khoanh tại chốt lời thoại — không có
    chốt nào nếu supervised=False, nên bắt buộc phải bật kèm nhau."""
    with pytest.raises(ValueError):
        pipeline.create_job(
            "https://www.tiktok.com/@u/video/1",
            "tiktok",
            "subtitle",
            hardsub_blur_enabled=True,
            supervised=False,
        )


# ─── VALID_TRANSITIONS ───────────────────────────────────────────────────────


def test_awaiting_review_transitions_allowed():
    """FR-004: đúng 2 chốt — chỉ transcribing và scripting dừng lại được."""
    assert "awaiting_review" in pipeline.VALID_TRANSITIONS["transcribing"]
    assert "awaiting_review" in pipeline.VALID_TRANSITIONS["scripting"]
    assert pipeline.VALID_TRANSITIONS["awaiting_review"] == [
        "scripting",
        "synthesizing",
        "failed",
    ]


@pytest.mark.parametrize("status", ["pending", "downloading", "synthesizing", "merging"])
def test_no_gate_on_other_steps(status):
    """Không bước nào khác được dừng chờ duyệt (FR-004)."""
    assert "awaiting_review" not in pipeline.VALID_TRANSITIONS[status]


def test_transcribing_to_awaiting_review_then_scripting(tmp_jobs_dir):
    job = pipeline.create_job(
        "https://www.tiktok.com/@u/video/1", "tiktok", "translate", supervised=True
    )
    jid = job["job_id"]
    pipeline.update_job_status(jid, "downloading")
    pipeline.update_job_status(jid, "transcribing")

    pipeline.update_job_status(jid, "awaiting_review")
    assert pipeline.read_job(jid)["status"] == "awaiting_review"

    # Phê duyệt → chạy tiếp từ bước sinh kịch bản
    pipeline.update_job_status(jid, "scripting")
    assert pipeline.read_job(jid)["status"] == "scripting"


def test_scripting_to_awaiting_review_then_synthesizing(tmp_jobs_dir):
    job = pipeline.create_job(
        "https://www.tiktok.com/@u/video/1", "tiktok", "translate", supervised=True
    )
    jid = job["job_id"]
    for s in ("downloading", "transcribing", "scripting"):
        pipeline.update_job_status(jid, s)

    pipeline.update_job_status(jid, "awaiting_review")
    pipeline.update_job_status(jid, "synthesizing")

    assert pipeline.read_job(jid)["status"] == "synthesizing"


def test_awaiting_review_cannot_jump_to_merging(tmp_jobs_dir):
    """Chốt không được dùng để nhảy bước — chỉ sang đúng bước kế tiếp."""
    job = pipeline.create_job(
        "https://www.tiktok.com/@u/video/1", "tiktok", "translate", supervised=True
    )
    jid = job["job_id"]
    for s in ("downloading", "transcribing", "awaiting_review"):
        pipeline.update_job_status(jid, s)

    with pytest.raises(ValueError):
        pipeline.update_job_status(jid, "merging")


# ─── Bất biến (data-model.md §2) ─────────────────────────────────────────────


def test_gate_invariant_script_approval_requires_transcript_approval(make_job):
    """review_gates.script.approved_at != null ⟹ transcript.approved_at != null."""
    job = make_job(supervised=True)

    gates.mark_reached(job, gates.GATE_TRANSCRIPT, 3)
    gates.mark_approved(job, gates.GATE_TRANSCRIPT)
    gates.mark_reached(job, gates.GATE_SCRIPT, 3)
    gates.mark_approved(job, gates.GATE_SCRIPT)

    assert gates.is_approved(job, gates.GATE_SCRIPT)
    assert gates.is_approved(job, gates.GATE_TRANSCRIPT)


def test_awaiting_review_iff_review_gate_set(make_job):
    job = make_job(supervised=True)
    assert job["review_gate"] is None  # chưa dừng ở chốt nào

    gates.mark_reached(job, gates.GATE_TRANSCRIPT, 3)
    assert job["review_gate"] == "transcript"

    gates.mark_approved(job, gates.GATE_TRANSCRIPT)
    assert job["review_gate"] is None


# ─── Hồi quy: job không supervised và job cũ (SC-001) ────────────────────────


def test_unsupervised_job_summary_has_null_gate(make_job):
    job = make_job(status="merging")

    summary = _job_to_summary(job)

    assert summary["review_gate"] is None
    assert summary["progress_percent"] == 82  # đúng như trước khi có feature này


def test_legacy_job_json_without_new_fields_renders(tmp_jobs_dir):
    """
    Job tạo TRƯỚC feature này thiếu supervised/review_gate/review_gates —
    summary + detail phải hiện bình thường, không KeyError (FR-002).
    """
    import json

    jid = "job-legacy-001"
    (tmp_jobs_dir / jid).mkdir()
    legacy = {
        "job_id": jid,
        "source_url": "https://www.tiktok.com/@u/video/9",
        "platform": "tiktok",
        "script_mode": "translate",
        "status": "done",
        "error": None,
        "artifacts": {"source_video": None, "output_video": None},
        "warnings": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    with open(tmp_jobs_dir / jid / "job.json", "w", encoding="utf-8") as f:
        json.dump(legacy, f)

    job = pipeline.read_job(jid)
    detail = _job_to_detail(job)

    assert detail["supervised"] is False
    assert detail["review_gate"] is None
    assert detail["review_url"] is None
    assert detail["progress_percent"] == 100


# ─── progress_percent ở chốt ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "gate,expected",
    [("transcript", 40), ("script", 56)],
)
def test_progress_percent_at_gates(make_job, gate, expected):
    job = make_job(status="awaiting_review", supervised=True, review_gate=gate)

    assert status_to_progress(job) == expected

"""
tests/unit/test_review_gates.py — Lõi chốt kiểm duyệt (008-supervised-pipeline).

Bao phủ FR-012 (bước sau dùng nội dung đã sửa), FR-013 (xoá trắng = bỏ câu),
FR-014 (chặn lưu khi rỗng toàn bộ), FR-016 (mốc thời gian read-only) và bất biến
"transcript_reviewed.json KHÔNG có 'words'" (research.md §3).

Không gọi LLM, không gọi HTTP — toàn bộ là logic thuần trên file JSON tạm.
"""

from __future__ import annotations

import json

import pytest

from review import gates
from tests.unit.conftest import REVIEWED_SEGMENTS, SCRIPT_SEGMENTS, TRANSCRIPT_SEGMENTS


def _load(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─── strip_words / write_transcript_review ───────────────────────────────────


def test_strip_words_removes_words_key():
    """Bất biến cốt lõi: payload chốt lời thoại KHÔNG được mang theo 'words'."""
    out = gates.strip_words(TRANSCRIPT_SEGMENTS)

    assert all("words" not in seg for seg in out)
    assert [sorted(seg) for seg in out] == [["end", "start", "text"]] * 2
    # start/end giữ nguyên, text được strip khoảng trắng đầu/cuối của ASR
    assert out[0] == {"start": 0.0, "end": 0.62, "text": "Hey Mr. Beast,"}


def test_write_transcript_review_file_has_no_words(tmp_path):
    path = gates.write_transcript_review(tmp_path, TRANSCRIPT_SEGMENTS, resegmented=True)
    data = _load(path)

    assert path.name == "transcript_reviewed.json"
    assert data["resegmented"] is True
    assert data["source"] == "transcript.json"
    assert all("words" not in seg for seg in data["segments"])


# ─── build_payload ───────────────────────────────────────────────────────────


def test_build_payload_transcript_gate(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
        review_gates={"transcript": {"reached_at": "2026-07-30T00:00:00+00:00"}},
    )

    payload = gates.build_payload(job, gates.GATE_TRANSCRIPT)

    assert payload["gate"] == "transcript"
    assert payload["editable_field"] == "text"
    assert payload["can_regenerate"] is False
    assert payload["edited"] is False
    assert [s["index"] for s in payload["segments"]] == [0, 1]
    assert payload["segments"][0]["text"] == "Này Mít Bít,"
    # Chốt lời thoại không có câu gốc để đối chiếu
    assert all(s["source_text"] is None for s in payload["segments"])


def test_build_payload_script_gate_exposes_source_text(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="script",
        script_segments=SCRIPT_SEGMENTS,
    )

    payload = gates.build_payload(job, gates.GATE_SCRIPT)

    assert payload["editable_field"] == "translated_text"
    assert payload["can_regenerate"] is True
    assert payload["segments"][0]["text"] == "Này MrBeast,"
    assert payload["segments"][0]["source_text"] == "Hey Mr. Beast,"


def test_build_payload_empty_segments_is_valid(make_job):
    """Video không có lời thoại: 0 câu là kết quả hợp lệ, không phải lỗi."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=[],
    )

    payload = gates.build_payload(job, gates.GATE_TRANSCRIPT)

    assert payload["segments"] == []


def test_build_payload_rejects_unknown_gate(make_job):
    job = make_job(reviewed_segments=REVIEWED_SEGMENTS)

    with pytest.raises(gates.GateError):
        gates.build_payload(job, "merging")


# ─── save_edits ──────────────────────────────────────────────────────────────


def test_save_edits_applies_only_listed_segments(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    saved, dropped = gates.save_edits(
        job, gates.GATE_TRANSCRIPT, [{"index": 0, "text": "Này MrBeast,"}]
    )

    assert (saved, dropped) == (2, 0)
    segments = _load(job["artifacts"]["transcript_reviewed"])["segments"]
    assert segments[0]["text"] == "Này MrBeast,"
    # Câu không gửi lên giữ nguyên nội dung đã lưu
    assert segments[1]["text"] == REVIEWED_SEGMENTS[1]["text"]


def test_save_edits_ignores_client_timestamps(make_job):
    """FR-016: mốc thời gian read-only — client gửi lên cũng bị bỏ qua."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    gates.save_edits(
        job,
        gates.GATE_TRANSCRIPT,
        [{"index": 0, "text": "Đã sửa", "start": 99.0, "end": 123.0}],
    )

    segments = _load(job["artifacts"]["transcript_reviewed"])["segments"]
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 0.62


def test_save_edits_drops_blank_segment(make_job):
    """FR-013: xoá trắng nội dung = bỏ câu đó khỏi file."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    saved, dropped = gates.save_edits(
        job, gates.GATE_TRANSCRIPT, [{"index": 0, "text": "   "}]
    )

    assert (saved, dropped) == (1, 1)
    segments = _load(job["artifacts"]["transcript_reviewed"])["segments"]
    assert len(segments) == 1
    assert segments[0]["text"] == REVIEWED_SEGMENTS[1]["text"]


def test_save_edits_all_blank_raises_and_leaves_file_untouched(make_job):
    """FR-014: rỗng toàn bộ → từ chối lưu VÀ không ghi gì lên đĩa."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )
    before = _load(job["artifacts"]["transcript_reviewed"])

    with pytest.raises(gates.EmptyGateError):
        gates.save_edits(
            job,
            gates.GATE_TRANSCRIPT,
            [{"index": 0, "text": ""}, {"index": 1, "text": "  "}],
        )

    assert _load(job["artifacts"]["transcript_reviewed"]) == before


def test_save_edits_unknown_index_raises(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=REVIEWED_SEGMENTS,
    )

    with pytest.raises(gates.UnknownSegmentError):
        gates.save_edits(job, gates.GATE_TRANSCRIPT, [{"index": 7, "text": "x"}])


def test_save_edits_script_gate_writes_translated_text_and_recomputes_content(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="script",
        script_segments=SCRIPT_SEGMENTS,
    )

    gates.save_edits(job, gates.GATE_SCRIPT, [{"index": 0, "text": "Này Mít Bít,"}])

    data = _load(job["artifacts"]["script"])
    assert data["segments"][0]["translated_text"] == "Này Mít Bít,"
    # source_text KHÔNG bị chạm tới — nó là câu gốc để đối chiếu
    assert data["segments"][0]["source_text"] == "Hey Mr. Beast,"
    assert data["content"] == "Này Mít Bít, nếu tôi đưa anh máy ảnh này,"


def test_save_edits_script_gate_backs_up_original_once(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="script",
        script_segments=SCRIPT_SEGMENTS,
    )
    backup = job["artifacts"]["script"].replace("script.json", "script_original.json")

    gates.save_edits(job, gates.GATE_SCRIPT, [{"index": 0, "text": "Lần sửa 1"}])
    first = _load(backup)
    gates.save_edits(job, gates.GATE_SCRIPT, [{"index": 0, "text": "Lần sửa 2"}])

    # Bản lưu giữ nội dung LLM sinh ra, không bị lượt sửa thứ hai ghi đè
    assert first["segments"][0]["translated_text"] == "Này MrBeast,"
    assert _load(backup) == first
    assert _load(job["artifacts"]["script"])["segments"][0]["translated_text"] == "Lần sửa 2"


# ─── Trạng thái chốt trong job.json ──────────────────────────────────────────


def test_mark_reached_then_approved(make_job):
    job = make_job(supervised=True)

    gates.mark_reached(job, gates.GATE_TRANSCRIPT, 12)
    assert job["review_gate"] == "transcript"
    assert job["review_gates"]["transcript"]["segment_count"] == 12
    assert job["review_gates"]["transcript"]["approved_at"] is None
    assert gates.is_approved(job, gates.GATE_TRANSCRIPT) is False

    gates.mark_approved(job, gates.GATE_TRANSCRIPT)
    assert job["review_gate"] is None
    assert gates.is_approved(job, gates.GATE_TRANSCRIPT) is True


def test_mark_regenerated_resets_approval_and_counts(make_job):
    job = make_job(supervised=True)
    gates.mark_reached(job, gates.GATE_SCRIPT, 8)
    gates.mark_edited(job, gates.GATE_SCRIPT, 8)
    gates.mark_approved(job, gates.GATE_SCRIPT)

    gates.mark_regenerated(job)

    entry = job["review_gates"]["script"]
    assert entry["regenerated_count"] == 1
    assert entry["approved_at"] is None
    assert entry["edited"] is False
    assert job["review_gate"] is None


def test_next_status_after_gate():
    assert gates.NEXT_STATUS_AFTER_GATE[gates.GATE_TRANSCRIPT] == "scripting"
    assert gates.NEXT_STATUS_AFTER_GATE[gates.GATE_SCRIPT] == "synthesizing"

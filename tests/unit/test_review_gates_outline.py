"""
tests/unit/test_review_gates_outline.py — Chốt GATE_OUTLINE (scene/kịch bản)
của tính năng "Tạo video từ chủ đề" (010-topic-video-generation).

review/gates.py tái dùng NGUYÊN VẸN build_payload()/save_edits()/mark_reached()/
mark_approved() cho chốt này (research.md §7) — bài test ở đây xác nhận việc mở
rộng GATE_ARRAY_KEY (đọc "scenes" thay vì "segments") không phá hành vi, VÀ full
flow duyệt → resume dùng đúng bản đã sửa (data-model.md §3, contracts/api.md §5-6).
"""

from __future__ import annotations

import json

import pytest

from review import gates
from tests.unit.conftest import SCENE_ITEMS


def _load(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_build_payload_outline_gate(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=SCENE_ITEMS,
        review_gates={"outline": {"reached_at": "2026-08-01T00:00:00+00:00"}},
    )

    payload = gates.build_payload(job, gates.GATE_OUTLINE)

    assert payload["gate"] == "outline"
    assert payload["editable_field"] == "narration_text"
    # v1: không cho sinh lại toàn bộ outline/scene từ chốt này (contracts/api.md §5)
    assert payload["can_regenerate"] is False
    assert [s["index"] for s in payload["segments"]] == [0, 1]
    assert payload["segments"][0]["text"] == SCENE_ITEMS[0]["narration_text"]
    # Scene chưa có timing thật — start/end null, client không hiển thị timeline
    assert payload["segments"][0]["start"] is None
    assert payload["segments"][0]["end"] is None
    # Không có khái niệm "câu gốc" ở chốt outline
    assert all(s["source_text"] is None for s in payload["segments"])


def test_save_edits_outline_gate_writes_narration_text(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=SCENE_ITEMS,
    )

    saved, dropped = gates.save_edits(
        job, gates.GATE_OUTLINE, [{"index": 0, "text": "Bản đã sửa tay."}]
    )

    assert (saved, dropped) == (2, 0)
    data = _load(job["artifacts"]["scenes"])
    assert data["scenes"][0]["narration_text"] == "Bản đã sửa tay."
    # Scene không gửi lên giữ nguyên nội dung đã lưu, và các field khác
    # (image_query/image_path/...) KHÔNG bị đụng tới
    assert data["scenes"][1]["narration_text"] == SCENE_ITEMS[1]["narration_text"]
    assert data["scenes"][0]["image_query"] == SCENE_ITEMS[0]["image_query"]


def test_save_edits_outline_gate_drops_blank_scene(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=SCENE_ITEMS,
    )

    saved, dropped = gates.save_edits(job, gates.GATE_OUTLINE, [{"index": 0, "text": "  "}])

    assert (saved, dropped) == (1, 1)
    data = _load(job["artifacts"]["scenes"])
    assert len(data["scenes"]) == 1


def test_save_edits_outline_gate_all_blank_raises(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=SCENE_ITEMS,
    )
    before = _load(job["artifacts"]["scenes"])

    with pytest.raises(gates.EmptyGateError):
        gates.save_edits(
            job, gates.GATE_OUTLINE, [{"index": 0, "text": ""}, {"index": 1, "text": " "}]
        )

    assert _load(job["artifacts"]["scenes"]) == before


def test_save_edits_outline_gate_unknown_index_raises(make_job):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="outline",
        scene_items=SCENE_ITEMS,
    )

    with pytest.raises(gates.UnknownSegmentError):
        gates.save_edits(job, gates.GATE_OUTLINE, [{"index": 9, "text": "x"}])


def test_outline_gate_full_flow_reach_edit_approve(make_job):
    """Job supervised dừng ở awaiting_review/outline, sửa 1 scene, duyệt →
    review_gate về None, chốt approved (resume dùng đúng bản đã sửa là trách
    nhiệm của generate_pipeline.py, test riêng ở test_generate_pipeline.py)."""
    job = make_job(status="scripting", supervised=True, scene_items=SCENE_ITEMS)

    gates.mark_reached(job, gates.GATE_OUTLINE, len(SCENE_ITEMS))
    assert job["review_gate"] == "outline"
    assert gates.is_approved(job, gates.GATE_OUTLINE) is False

    gates.save_edits(job, gates.GATE_OUTLINE, [{"index": 0, "text": "Câu mở đầu mới."}])
    gates.mark_approved(job, gates.GATE_OUTLINE)

    assert job["review_gate"] is None
    assert gates.is_approved(job, gates.GATE_OUTLINE) is True
    data = _load(job["artifacts"]["scenes"])
    assert data["scenes"][0]["narration_text"] == "Câu mở đầu mới."


def test_next_status_after_outline_gate():
    assert gates.NEXT_STATUS_AFTER_GATE[gates.GATE_OUTLINE] == "sourcing_assets"


def test_gates_tuple_includes_outline():
    assert gates.GATE_OUTLINE in gates.GATES

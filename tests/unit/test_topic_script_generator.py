"""
tests/unit/test_topic_script_generator.py — write_outline_and_scenes() /
write_outline_and_scenes_to_disk() (010-topic-video-generation, T022).

`_chat_completion` LUÔN mock — không gọi 9router thật (Constitution VI).
"""

from __future__ import annotations

import json

import pytest

from script_gen import topic_script_generator as tsg
from script_gen.router_client import TruncatedResponseError

_VALID_RAW = json.dumps(
    {
        "outline": {
            "sections": [
                {"title": "Mở đầu", "key_points": ["a"]},
                {"title": "Kết", "key_points": ["b"]},
            ]
        },
        "scenes": [
            {
                "index": 0,
                "type": "hook",
                "section_index": None,
                "narration_text": "Câu 1.",
                "image_query": "ancient coins",
            },
            {
                "index": 1,
                "type": "outro",
                "section_index": None,
                "narration_text": "Câu 2.",
                "image_query": "modern banknotes",
            },
        ],
    }
)


def test_write_outline_and_scenes_parses_valid_json(monkeypatch):
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: _VALID_RAW)

    result = tsg.write_outline_and_scenes("tổng quan về tiền tệ")

    assert result["outline"]["sections"][0]["title"] == "Mở đầu"
    assert len(result["scenes"]) == 2
    assert result["scenes"][0] == {
        "index": 0,
        "type": "hook",
        "section_index": None,
        "section_title": None,
        "narration_text": "Câu 1.",
        "image_query": "ancient coins",
    }


def test_write_outline_and_scenes_uses_agent_model(monkeypatch):
    captured = {}

    def fake_chat_completion(system, user, temperature=0.7, model=None):
        captured["model"] = model
        return _VALID_RAW

    monkeypatch.setattr(tsg, "_chat_completion", fake_chat_completion)

    tsg.write_outline_and_scenes("x")

    assert captured["model"] == tsg.AGENT_MODEL


def test_write_outline_and_scenes_strips_markdown_fence(monkeypatch):
    fenced = f"```json\n{_VALID_RAW}\n```"
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: fenced)

    result = tsg.write_outline_and_scenes("x")

    assert len(result["scenes"]) == 2


def test_write_outline_and_scenes_reindexes_scenes(monkeypatch):
    """KHÔNG tin tưởng index model tự đánh — đánh số lại tuần tự từ 0."""
    raw = json.dumps(
        {
            "outline": {"sections": [{"title": "A", "key_points": []}]},
            "scenes": [
                {"index": 5, "type": "hook", "section_index": None, "narration_text": "Câu 1.", "image_query": "q1"},
                {"index": 9, "type": "outro", "section_index": None, "narration_text": "Câu 2.", "image_query": "q2"},
            ],
        }
    )
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    result = tsg.write_outline_and_scenes("x")

    assert [s["index"] for s in result["scenes"]] == [0, 1]


def test_write_outline_and_scenes_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: "không phải JSON gì cả")

    with pytest.raises(tsg.OutlineParseError):
        tsg.write_outline_and_scenes("x")


def test_write_outline_and_scenes_raises_on_missing_scenes(monkeypatch):
    raw = json.dumps({"outline": {"sections": [{"title": "A"}]}, "scenes": []})
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    with pytest.raises(tsg.OutlineParseError):
        tsg.write_outline_and_scenes("x")


def test_write_outline_and_scenes_raises_on_scene_missing_narration(monkeypatch):
    raw = json.dumps(
        {
            "outline": {"sections": [{"title": "A"}]},
            "scenes": [{"index": 0, "narration_text": "", "image_query": "q"}],
        }
    )
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    with pytest.raises(tsg.OutlineParseError):
        tsg.write_outline_and_scenes("x")


def test_write_outline_and_scenes_propagates_truncated_response_error(monkeypatch):
    """finish_reason='length' — KHÔNG bị nuốt âm thầm, job phải fail rõ ràng
    ở bước outlining (giống hành vi của router_client.py)."""

    def raise_truncated(*a, **kw):
        raise TruncatedResponseError("output bị cắt")

    monkeypatch.setattr(tsg, "_chat_completion", raise_truncated)

    with pytest.raises(TruncatedResponseError):
        tsg.write_outline_and_scenes("x")


# ─── write_outline_and_scenes_to_disk ────────────────────────────────────────


def test_write_outline_and_scenes_to_disk_writes_both_files(tmp_path, monkeypatch):
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: _VALID_RAW)

    outline_path, scenes_path = tsg.write_outline_and_scenes_to_disk("chủ đề x", tmp_path)

    assert outline_path.name == "outline.json"
    assert scenes_path.name == "scenes.json"

    with open(outline_path, encoding="utf-8") as f:
        outline_data = json.load(f)
    assert outline_data["topic"] == "chủ đề x"
    assert outline_data["search_used"] is True
    assert len(outline_data["sections"]) == 2

    with open(scenes_path, encoding="utf-8") as f:
        scenes_data = json.load(f)
    assert scenes_data["source"] == "outline.json"
    assert len(scenes_data["scenes"]) == 2
    # Chưa qua bước sourcing_assets/synthesizing — 3 field này phải None
    for scene in scenes_data["scenes"]:
        assert scene["image_path"] is None
        assert scene["voice_path"] is None
        assert scene["duration"] is None
    assert scenes_data["scenes"][0]["type"] == "hook"
    assert scenes_data["scenes"][0]["section_title"] is None
    assert scenes_data["scenes"][1]["type"] == "outro"


# ─── type/section_index validation (per-scene template dispatch) ────────────


def test_write_outline_and_scenes_raises_on_invalid_scene_type(monkeypatch):
    raw = json.dumps(
        {
            "outline": {"sections": [{"title": "A"}]},
            "scenes": [
                {"index": 0, "type": "nonsense", "section_index": None, "narration_text": "x", "image_query": "q"},
                {"index": 1, "type": "outro", "section_index": None, "narration_text": "y", "image_query": "q"},
            ],
        }
    )
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    with pytest.raises(tsg.OutlineParseError, match="type"):
        tsg.write_outline_and_scenes("x")


def test_write_outline_and_scenes_raises_when_first_scene_not_hook(monkeypatch):
    raw = json.dumps(
        {
            "outline": {"sections": [{"title": "A"}]},
            "scenes": [
                {"index": 0, "type": "concept", "section_index": 0, "narration_text": "x", "image_query": "q"},
                {"index": 1, "type": "outro", "section_index": None, "narration_text": "y", "image_query": "q"},
            ],
        }
    )
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    with pytest.raises(tsg.OutlineParseError, match="hook"):
        tsg.write_outline_and_scenes("x")


def test_write_outline_and_scenes_raises_when_last_scene_not_outro(monkeypatch):
    raw = json.dumps(
        {
            "outline": {"sections": [{"title": "A"}]},
            "scenes": [
                {"index": 0, "type": "hook", "section_index": None, "narration_text": "x", "image_query": "q"},
                {"index": 1, "type": "concept", "section_index": 0, "narration_text": "y", "image_query": "q"},
            ],
        }
    )
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    with pytest.raises(tsg.OutlineParseError, match="outro"):
        tsg.write_outline_and_scenes("x")


def test_write_outline_and_scenes_raises_on_section_index_out_of_range(monkeypatch):
    raw = json.dumps(
        {
            "outline": {"sections": [{"title": "A"}]},
            "scenes": [
                {"index": 0, "type": "hook", "section_index": None, "narration_text": "x", "image_query": "q"},
                {"index": 1, "type": "concept", "section_index": 5, "narration_text": "y", "image_query": "q"},
                {"index": 2, "type": "outro", "section_index": None, "narration_text": "z", "image_query": "q"},
            ],
        }
    )
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    with pytest.raises(tsg.OutlineParseError, match="section_index"):
        tsg.write_outline_and_scenes("x")


def test_write_outline_and_scenes_resolves_section_title_onto_scene(monkeypatch):
    raw = json.dumps(
        {
            "outline": {
                "sections": [
                    {"title": "Máy ảnh Digital", "key_points": ["a"]},
                    {"title": "Máy ảnh Film", "key_points": ["b"]},
                ]
            },
            "scenes": [
                {"index": 0, "type": "hook", "section_index": None, "narration_text": "x", "image_query": "q"},
                {"index": 1, "type": "concept", "section_index": 0, "narration_text": "y", "image_query": "q"},
                {"index": 2, "type": "transition", "section_index": 1, "narration_text": "z", "image_query": "q"},
                {"index": 3, "type": "outro", "section_index": None, "narration_text": "w", "image_query": "q"},
            ],
        }
    )
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: raw)

    result = tsg.write_outline_and_scenes("x")

    assert result["scenes"][1]["section_title"] == "Máy ảnh Digital"
    assert result["scenes"][2]["section_title"] == "Máy ảnh Film"
    assert result["scenes"][0]["section_title"] is None
    assert result["scenes"][3]["section_title"] is None


def test_write_outline_and_scenes_to_disk_reflects_real_search_used(tmp_path, monkeypatch):
    """search_used trong file phải khớp NHÁNH THẬT đã chạy (T034/US2), không
    phải giá trị cố định."""
    # AGENT_MODEL/DEFAULT_MODEL có thể trùng giá trị nếu máy dev chưa set
    # ROUTER_AGENT_MODEL trong .env thật — ép khác nhau để test không phụ
    # thuộc .env cục bộ.
    monkeypatch.setattr(tsg, "AGENT_MODEL", "agent-model-for-test")
    monkeypatch.setattr(tsg, "DEFAULT_MODEL", "default-model-for-test")

    def fail_then_succeed(system, user, temperature=0.7, model=None):
        if model == tsg.AGENT_MODEL:
            raise ConnectionError("agent model không kết nối được")
        return _VALID_RAW

    monkeypatch.setattr(tsg, "_chat_completion", fail_then_succeed)

    outline_path, _ = tsg.write_outline_and_scenes_to_disk("x", tmp_path)

    with open(outline_path, encoding="utf-8") as f:
        assert json.load(f)["search_used"] is False


# ─── US2: fallback khi lượt gọi agent lỗi (T033-T035) ────────────────────────


def test_write_outline_and_scenes_falls_back_on_agent_error(monkeypatch):
    monkeypatch.setattr(tsg, "AGENT_MODEL", "agent-model-for-test")
    monkeypatch.setattr(tsg, "DEFAULT_MODEL", "default-model-for-test")
    calls = []

    def fake_chat_completion(system, user, temperature=0.7, model=None):
        calls.append(model)
        if model == tsg.AGENT_MODEL:
            raise TimeoutError("9router agent timeout")
        return _VALID_RAW

    monkeypatch.setattr(tsg, "_chat_completion", fake_chat_completion)

    result = tsg.write_outline_and_scenes("x")

    assert result["search_used"] is False
    assert len(result["scenes"]) == 2
    assert calls == [tsg.AGENT_MODEL, tsg.DEFAULT_MODEL]


def test_write_outline_and_scenes_search_used_true_when_agent_succeeds(monkeypatch):
    monkeypatch.setattr(tsg, "_chat_completion", lambda *a, **kw: _VALID_RAW)

    result = tsg.write_outline_and_scenes("x")

    assert result["search_used"] is True


def test_write_outline_and_scenes_does_not_fallback_on_truncated_response(monkeypatch):
    """FR-009 chỉ áp dụng cho lỗi mạng/tool-use — KHÔNG áp dụng cho output bị
    cắt (đổi model không giải quyết được gì, giống router_client.py)."""
    calls = []

    def fake_chat_completion(system, user, temperature=0.7, model=None):
        calls.append(model)
        raise TruncatedResponseError("output bị cắt")

    monkeypatch.setattr(tsg, "_chat_completion", fake_chat_completion)

    with pytest.raises(TruncatedResponseError):
        tsg.write_outline_and_scenes("x")

    assert calls == [tsg.AGENT_MODEL]  # KHÔNG gọi fallback lần 2


def test_write_outline_and_scenes_raises_when_both_agent_and_fallback_fail(monkeypatch):
    def always_fail(system, user, temperature=0.7, model=None):
        raise ConnectionError(f"lỗi mạng ({model})")

    monkeypatch.setattr(tsg, "_chat_completion", always_fail)

    with pytest.raises(ConnectionError):
        tsg.write_outline_and_scenes("x")

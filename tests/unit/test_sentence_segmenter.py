"""
Test script_gen/sentence_segmenter.py — cắt lại segment theo ranh giới câu.

Không gọi LLM thật: truyền hàm llm_call giả để kiểm tra logic align + build +
mọi nhánh fallback an toàn.
"""

from __future__ import annotations

from script_gen.sentence_segmenter import _MARKER, resegment_by_sentences


def _mk_words(text: str, t0: float, t1: float) -> list[dict]:
    toks = text.split()
    dt = (t1 - t0) / len(toks)
    return [
        {"word": " " + w, "start": round(t0 + i * dt, 3), "end": round(t0 + (i + 1) * dt, 3)}
        for i, w in enumerate(toks)
    ]


def _segments_from_example() -> list[dict]:
    # 2 ASR segment chạy liền, ranh giới 10.56 rơi GIỮA CÂU ("...solid in | about...")
    s0 = ("this is me taking an ice bath in minus 52 degrees where I freeze within a "
          "couple of seconds and almost pass out okay so first of all we actually had "
          "to break the ice because it freezes solid in")
    s1 = ("about five minutes time after breaking it I had to sprint to the warm "
          "cabin nearby I changed my clothes there")
    return [
        {"start": 0.0, "end": 10.56, "text": s0, "words": _mk_words(s0, 0.0, 10.56)},
        {"start": 10.56, "end": 18.0, "text": s1, "words": _mk_words(s1, 10.56, 18.0)},
    ]


def _fake_llm_correct(system: str, user: str) -> str:
    """Chèn ⟦S⟧ đúng ranh giới câu, không đổi từ nào."""
    out = user
    out = out.replace("almost pass out okay", f"almost pass out {_MARKER} okay")
    out = out.replace("five minutes time after", f"five minutes time {_MARKER} after")
    out = out.replace("warm cabin nearby I changed", f"warm cabin nearby {_MARKER} I changed")
    return out + f" {_MARKER}"


def test_resegment_splits_at_sentence_ends_not_midsentence():
    segments = _segments_from_example()
    result = resegment_by_sentences(segments, _fake_llm_correct)

    # 2 segment run-on → 4 segment theo câu
    assert len(result) == 4
    # Không segment nào kết thúc giữa câu ở "in" (lỗi user báo)
    assert all(not s["text"].endswith(" in") for s in result)
    assert result[0]["text"].endswith("pass out")
    # Mốc thời gian liền mạch, không chồng lấn
    for a, b in zip(result, result[1:]):
        assert a["end"] <= b["start"] + 1e-6


def test_fallback_when_word_count_mismatch():
    segments = _segments_from_example()
    # LLM trả về khác hẳn (thêm/bớt từ) → giữ nguyên segment cũ
    result = resegment_by_sentences(segments, lambda s, u: "totally different words here")
    assert result is segments


def test_fallback_when_no_word_timestamps():
    old = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    result = resegment_by_sentences(old, _fake_llm_correct)
    assert result == old


def test_fallback_when_llm_raises():
    segments = _segments_from_example()

    def boom(system, user):
        raise RuntimeError("LLM chết")

    result = resegment_by_sentences(segments, boom)
    assert result is segments


def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("DISABLE_SENTENCE_RESEGMENT", "1")
    segments = _segments_from_example()
    result = resegment_by_sentences(segments, _fake_llm_correct)
    assert result is segments


def test_real_word_gap_still_splits():
    # Không có marker nào, nhưng có khoảng lặng thật ≥0.30s giữa 2 từ → vẫn cắt
    words = (
        _mk_words("hello there friend", 0.0, 1.5)
        + [{"word": " later", "start": 3.0, "end": 3.5}]  # gap 1.5s trước từ này
    )
    segments = [{"start": 0.0, "end": 3.5, "text": "hello there friend later", "words": words}]

    def no_marker(system, user):
        return user  # không chèn ranh giới câu

    result = resegment_by_sentences(segments, no_marker)
    assert len(result) == 2
    assert result[0]["text"] == "hello there friend"
    assert result[1]["text"] == "later"

"""
tests/unit/test_group_segments.py — Gom ASR segment thành dubbing unit.

Trọng tâm: GIỮ NGUYÊN nhịp cắt của clip gốc, chỉ gộp khi tách ra chắc chắn tệ
hơn (nửa câu bị đem đi dịch riêng, hoặc nhịp vụn < 1.2s).
"""

from __future__ import annotations

from script_gen.router_client import _is_sentence_continuation, group_segments


def seg(start, end, text):
    return {"start": start, "end": end, "text": text}


# ── Giữ nguyên nhịp cắt gốc ─────────────────────────────────────────────────


def test_hai_cau_lien_mach_van_giu_tach():
    """
    Ca thật người dùng báo lỗi: 2 segment liền nhau (gap = 0.0), mỗi segment là
    1 câu trọn vẹn — luật cũ gộp thành 1 nhịp 9.52s, giờ phải giữ nguyên 2 nhịp.
    """
    units = group_segments(
        [
            seg(0.0, 4.0, "I've had friend who was missing five of his toes on his left leg"),
            seg(4.0, 9.52, "He was running barefoot for like two minutes. Yeah, and he lost all his toes."),
        ]
    )

    assert len(units) == 2
    assert (units[0]["start"], units[0]["end"]) == (0.0, 4.0)
    assert (units[1]["start"], units[1]["end"]) == (4.0, 9.52)


def test_cau_truoc_co_dau_cham_thi_giu_tach():
    units = group_segments(
        [
            seg(0.0, 3.0, "That's it. I'm a period."),
            seg(3.0, 4.5, "Period!"),
        ]
    )

    assert len(units) == 2


def test_ngat_nghi_that_luon_giu_tach():
    """Khoảng trống ≥ 0.30s là ngắt nghỉ thật — không bao giờ gộp."""
    units = group_segments(
        [
            seg(0.0, 4.0, "this is the first part and it keeps going"),
            seg(5.0, 9.0, "continuing here in lowercase"),
        ]
    )

    assert len(units) == 2


# ── Vẫn gộp khi tách ra sẽ hỏng ─────────────────────────────────────────────


def test_noi_tiep_giua_cau_thi_gop():
    """Nửa câu đem đi dịch riêng sẽ ra 2 mẩu tiếng Việt cụt nghĩa."""
    units = group_segments(
        [
            seg(0.0, 4.0, "this is a bit of a ghost town, I was"),
            seg(4.0, 8.0, "now about to head outside for the first time"),
        ]
    )

    assert len(units) == 1
    assert units[0]["source_text"].startswith("this is a bit")
    assert units[0]["source_text"].endswith("first time")
    assert units[0]["end"] == 8.0


def test_nhip_vun_duoi_1_2s_van_duoc_gop():
    units = group_segments(
        [
            seg(0.0, 0.6, "Yeah"),
            seg(1.0, 5.0, "And then we went outside."),
        ]
    )

    assert len(units) == 1


def test_khong_gop_qua_tran_15s():
    """Trần _MAX_UNIT_DURATION chặn mọi quy tắc gộp."""
    units = group_segments(
        [
            seg(0.0, 14.0, "a very long stretch of speech that just keeps on going and"),
            seg(14.0, 20.0, "continues past the fifteen second ceiling here"),
        ]
    )

    assert len(units) == 2


# ── Ngôn ngữ không phân biệt hoa/thường ─────────────────────────────────────


def test_tieng_trung_giu_tach_theo_clip_goc():
    """CJK không có chữ thường → mặc định coi là ranh giới câu, giữ tách."""
    units = group_segments(
        [
            seg(0.0, 3.0, "和他一起去了"),
            seg(3.0, 6.0, "然后就回来了"),
        ]
    )

    assert len(units) == 2


# ── Bất biến chung ──────────────────────────────────────────────────────────


def test_bo_qua_segment_rong_va_danh_index_lien_tuc():
    units = group_segments(
        [
            seg(0.0, 2.0, "First sentence."),
            seg(2.5, 3.0, "   "),
            seg(4.0, 6.0, "Second sentence."),
        ]
    )

    assert [u["index"] for u in units] == [0, 1]


def test_unit_khong_chong_lan_va_tang_dan():
    units = group_segments(
        [
            seg(0.0, 4.0, "One."),
            seg(4.0, 9.52, "Two."),
            seg(10.08, 13.66, "Three."),
        ]
    )

    for prev, cur in zip(units, units[1:]):
        assert cur["start"] >= prev["end"]


def test_is_sentence_continuation():
    assert _is_sentence_continuation("ghost town, I was", "now about to head") is True
    assert _is_sentence_continuation("on his left leg", "He was running") is False
    assert _is_sentence_continuation("I'm a period.", "period!") is False
    assert _is_sentence_continuation("和他一起去了", "然后就回来了") is False
    assert _is_sentence_continuation("something", "") is False

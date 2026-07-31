"""
tests/unit/test_hardsub_ranges.py — Tính "đoạn có phụ đề gốc" (009).

Bao phủ FR-003 (mặc định coi cả video có phụ đề gốc), FR-004 (tái dùng
parse_time_ranges, field độc lập), FR-010 (bỏ qua chuỗi sai định dạng).
Không chạm OCR/ffmpeg — thuần logic tính khoảng.
"""

from __future__ import annotations

from hardsub.ranges import hardsub_ranges


def test_empty_string_means_whole_video_has_hardsub():
    """FR-003: chuỗi rỗng/None → mặc định coi cả video là có phụ đề gốc."""
    assert hardsub_ranges("", 26.0) == [[0.0, 26.0]]
    assert hardsub_ranges(None, 26.0) == [[0.0, 26.0]]


def test_one_range_in_the_middle_splits_into_two():
    result = hardsub_ranges("10-15", 26.0)

    assert result == [[0.0, 10.0], [15.0, 26.0]]


def test_range_touching_start_edge_leaves_one_segment():
    result = hardsub_ranges("0-8", 26.0)

    assert result == [[8.0, 26.0]]


def test_range_touching_end_edge_leaves_one_segment():
    result = hardsub_ranges("20-end", 26.0)

    assert result == [[0.0, 20.0]]


def test_range_covering_whole_video_returns_empty():
    result = hardsub_ranges("0-end", 26.0)

    assert result == []


def test_multiple_non_overlapping_ranges():
    result = hardsub_ranges("5-8, 15-18", 26.0)

    assert result == [[0.0, 5.0], [8.0, 15.0], [18.0, 26.0]]


def test_malformed_range_is_ignored_not_erroring():
    """FR-010: chuỗi sai định dạng bị bỏ qua, không lỗi."""
    # "abc-def" không parse được → parse_time_ranges() bỏ qua → coi như rỗng
    result = hardsub_ranges("abc-def", 26.0)

    assert result == [[0.0, 26.0]]


def test_overlapping_ranges_are_merged_correctly():
    """Khoảng chồng lấn (5-12 và 10-18) phải gộp lại, không tạo khoảng âm."""
    result = hardsub_ranges("10-18, 5-12", 26.0)

    assert result == [[0.0, 5.0], [18.0, 26.0]]


def test_range_exceeding_duration_is_clamped():
    result = hardsub_ranges("20-100", 26.0)

    assert result == [[0.0, 20.0]]

"""
hardsub/ranges.py — Tính "đoạn có phụ đề gốc" (009-hardsub-blur-reposition).

Người dùng khai báo các khoảng KHÔNG có phụ đề gốc (cùng cú pháp chuỗi với
"Giữ nguyên audio gốc" — parse_time_ranges() ở merge/ffmpeg_merge.py). Mặc định
(chuỗi rỗng) coi TOÀN BỘ video là có phụ đề gốc (FR-003). Module này chỉ lo tính
phần bù trong [0, total_duration] — KHÔNG chạm OCR/ffmpeg (xem hardsub/detector.py).
"""

from __future__ import annotations

from merge.ffmpeg_merge import parse_time_ranges


def hardsub_ranges(no_ranges_text: str | None, total_duration: float) -> list[list[float]]:
    """
    Trả về các đoạn CÓ phụ đề gốc = phần bù của `no_ranges_text` trong
    [0, total_duration].

    Chuỗi rỗng/None → coi cả video có phụ đề gốc (FR-003):
    `[[0.0, total_duration]]`.
    """
    no_ranges = parse_time_ranges(no_ranges_text or "", total_duration)
    if not no_ranges:
        return [[0.0, total_duration]] if total_duration > 0 else []

    # parse_time_ranges() đã kẹp trong [0, total] và bỏ khoảng rỗng/âm, nhưng
    # chưa đảm bảo thứ tự — sắp xếp để quét phần bù tuyến tính một lượt.
    no_ranges = sorted(no_ranges)

    result: list[list[float]] = []
    cursor = 0.0
    for start, end in no_ranges:
        if start > cursor:
            result.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < total_duration:
        result.append([cursor, total_duration])

    return result

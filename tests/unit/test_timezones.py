"""
tests/unit/test_timezones.py — Quy đổi giờ Việt Nam <-> UTC (007-schedule-publish).

Bẫy cụ thể cần khoá lại: nếu quên quy đổi, bài sẽ lên lệch đúng 7 tiếng vì
Zernio mặc định UTC (research.md §2).
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from publish.timezones import VN_TIMEZONE, to_local_iso, to_utc_iso


def test_20h_gio_vn_thanh_13h_utc():
    """Ca cụ thể từ quickstart KB3: 20:00 giờ VN -> 13:00Z."""
    local_dt = datetime(2026, 7, 29, 20, 0, 0)  # naive, hiểu là giờ VN

    result = to_utc_iso(local_dt)

    assert result == "2026-07-29T13:00:00Z"


def test_naive_datetime_duoc_hieu_la_gio_vn():
    naive = datetime(2026, 7, 29, 8, 0, 0)
    explicit_vn = datetime(2026, 7, 29, 8, 0, 0, tzinfo=VN_TIMEZONE)

    assert to_utc_iso(naive) == to_utc_iso(explicit_vn)


def test_datetime_co_san_tzinfo_khac_van_quy_doi_dung():
    utc_dt = datetime(2026, 7, 29, 1, 0, 0, tzinfo=timezone.utc)

    # 01:00 UTC = 08:00 giờ VN (+7)
    assert to_utc_iso(utc_dt) == "2026-07-29T01:00:00Z"


def test_to_local_iso_nguoc_lai_dung():
    utc_iso = "2026-07-29T13:00:00Z"

    local_iso = to_local_iso(utc_iso)

    parsed = datetime.fromisoformat(local_iso)
    assert parsed.hour == 20
    assert parsed.tzinfo.utcoffset(parsed).total_seconds() == 7 * 3600


def test_to_local_iso_chap_nhan_offset_khong_phai_z():
    utc_iso = "2026-07-29T13:00:00+00:00"

    local_iso = to_local_iso(utc_iso)

    assert datetime.fromisoformat(local_iso).hour == 20


def test_khu_hoi_gio_khong_bi_mat_qua_2_lan_quy_doi():
    original = datetime(2026, 7, 29, 20, 0, 0, tzinfo=VN_TIMEZONE)

    round_tripped = to_local_iso(to_utc_iso(original))

    assert datetime.fromisoformat(round_tripped).hour == 20


def test_qua_nua_dem_sang_ngay_hom_sau():
    """23:30 giờ VN -> 16:30Z cùng ngày dương lịch UTC (không lùi ngày)."""
    local_dt = datetime(2026, 7, 29, 23, 30, 0)

    assert to_utc_iso(local_dt) == "2026-07-29T16:30:00Z"


def test_khong_dung_muti_gio_khac_gay_nham():
    """Nếu lỡ coi giờ nhập là UTC (bỏ qua quy đổi) thì kết quả phải khác hẳn —
    khoá lại để bug lệch 7 tiếng bị bắt ngay ở unit test."""
    local_dt = datetime(2026, 7, 29, 20, 0, 0)

    wrong_if_treated_as_utc = "2026-07-29T20:00:00Z"

    assert to_utc_iso(local_dt) != wrong_if_treated_as_utc

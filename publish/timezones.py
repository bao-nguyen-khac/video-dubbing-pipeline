"""
publish/timezones.py — Quy đổi múi giờ cho tính năng hẹn giờ đăng
(007-schedule-publish).

Ranh giới bắt buộc (research.md §2): giao diện làm việc bằng giờ Việt Nam, còn
file lưu trữ và payload gửi Zernio LUÔN là UTC tuyệt đối (`...Z`). Quy đổi chỉ
xảy ra ở đúng 2 hàm dưới đây — không có "giờ trần không rõ múi" ở bất kỳ chỗ
nào khác trong hệ thống.

Dùng `zoneinfo` (thư viện chuẩn từ Python 3.9), không thêm dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Công cụ dùng cho 1 người dùng duy nhất — không hỗ trợ chọn múi giờ khác ở bản
# đầu (spec.md → Assumptions).
VN_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def to_utc_iso(local_dt: datetime) -> str:
    """
    Giờ Việt Nam (người dùng nhập) → chuỗi ISO 8601 UTC, dùng để lưu file
    attempt và gửi `scheduledFor` cho Zernio.

    `local_dt` không có tzinfo (vd từ `<input type="datetime-local">`) được
    hiểu là giờ Việt Nam. Nếu đã có tzinfo thì quy đổi từ múi giờ đó.
    """
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=VN_TIMEZONE)
    return local_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def to_local_iso(utc_iso: str) -> str:
    """
    Chuỗi ISO 8601 UTC (từ file attempt hoặc response Zernio) → chuỗi ISO giờ
    Việt Nam, dùng để hiển thị lại cho người dùng.
    """
    dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TIMEZONE).isoformat()

"""
publish/limits.py — Giới hạn thời lượng/kích thước của nền tảng đích.

Kiểm tra TRƯỚC khi upload để người dùng biết ngay nguyên nhân, thay vì tốn một
lượt upload rồi mới bị nền tảng từ chối (spec.md → Edge Cases, research.md §7).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from media_utils import get_media_duration

# Ngưỡng mặc định. TikTok: giới hạn thật phụ thuộc từng creator — lấy động qua
# creator-info (postingLimits.maxVideoDurationSec) khi gọi được, giá trị ở đây
# chỉ là fallback khi không lấy được.
TIKTOK_MAX_DURATION_SECONDS = 600
YOUTUBE_SHORTS_MAX_DURATION_SECONDS = 180

# Zernio nhận file tới 5GB qua presign, nhưng video > 200MB không được nén hộ
# nên dễ bị nền tảng từ chối — chặn sớm ở ngưỡng thận trọng.
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024

_PLATFORM_LABEL = {"tiktok": "TikTok", "youtube": "YouTube Shorts"}

# Biên thời gian cho hẹn giờ đăng (007-schedule-publish, spec.md → Clarifications).
#
# Tối thiểu 15 phút: video phải upload lên Zernio xong trước khi tới giờ đăng —
# hẹn quá sát thì upload xong đã trôi qua mất thời điểm (research.md §7).
MIN_SCHEDULE_LEAD_SECONDS = 15 * 60

# Tối đa 3 ngày: tài liệu Zernio KHÔNG công bố file tạm (publicUrl từ presign)
# được giữ bao lâu — đã tra cả openapi.yaml, docs.zernio.com lẫn llms.txt, không
# nơi nào nói. Một endpoint upload anh em của họ ghi rõ tự xoá sau 7 ngày, nên
# chọn mốc nằm sâu dưới mọi khả năng thay vì đoán (research.md §7).
MAX_SCHEDULE_LEAD_SECONDS = 3 * 24 * 3600


def max_duration_for(platform: str, override_seconds: int | None = None) -> int:
    """Ngưỡng thời lượng áp dụng cho nền tảng (ưu tiên giá trị lấy động)."""
    if override_seconds:
        return override_seconds
    if platform == "youtube":
        return YOUTUBE_SHORTS_MAX_DURATION_SECONDS
    return TIKTOK_MAX_DURATION_SECONDS


def check_limits(
    platform: str,
    video_path: str | Path,
    max_duration_seconds: int | None = None,
) -> str | None:
    """
    Trả về thông báo lỗi tiếng Việt nếu video vượt giới hạn, None nếu hợp lệ.

    `max_duration_seconds` cho phép truyền ngưỡng lấy động từ creator-info của
    TikTok; bỏ trống thì dùng hằng số mặc định ở trên.
    """
    path = Path(video_path)
    if not path.exists():
        return "Không tìm thấy file video kết quả của job này"

    label = _PLATFORM_LABEL.get(platform, platform)

    size = path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        return (
            f"Video nặng {size / 1024 / 1024:.0f}MB, vượt giới hạn "
            f"{MAX_FILE_SIZE_BYTES // 1024 // 1024}MB cho một lượt đăng"
        )

    limit = max_duration_for(platform, max_duration_seconds)
    duration = get_media_duration(path)
    # duration == 0 nghĩa là ffprobe không đọc được — không chặn ở đây, để nền
    # tảng quyết định, tránh chặn nhầm video hợp lệ vì lỗi công cụ cục bộ
    if duration and duration > limit:
        return f"Video dài {duration:.0f}s, vượt giới hạn {limit}s của {label}"

    return None


def check_schedule_time(scheduled_for: datetime, now: datetime | None = None) -> str | None:
    """
    Trả về thông báo lỗi tiếng Việt nếu thời điểm hẹn giờ nằm ngoài biên cho
    phép (FR-003, FR-004), None nếu hợp lệ.

    `scheduled_for` PHẢI có tzinfo (đã quy đổi UTC — publish/timezones.py).
    Naive datetime coi như UTC để tránh so sánh sai lệch múi giờ âm thầm.
    """
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)

    reference = now or datetime.now(timezone.utc)
    lead_seconds = (scheduled_for - reference).total_seconds()

    if lead_seconds < MIN_SCHEDULE_LEAD_SECONDS:
        return (
            f"Phải hẹn cách thời điểm hiện tại ít nhất "
            f"{MIN_SCHEDULE_LEAD_SECONDS // 60} phút — video cần thời gian tải lên "
            f"trước khi tới giờ đăng"
        )

    if lead_seconds > MAX_SCHEDULE_LEAD_SECONDS:
        return (
            f"Chỉ hẹn được tối đa {MAX_SCHEDULE_LEAD_SECONDS // 86400} ngày kể từ bây giờ"
        )

    return None

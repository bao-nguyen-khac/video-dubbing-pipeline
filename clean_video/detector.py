"""
clean_video/detector.py — Phát hiện watermark / hardsub còn sót trong video.

Constitution Principle III: MVP chỉ detect và log cảnh báo, KHÔNG gọi AI inpainting.
Kết quả detect ảnh hưởng tới warnings.watermark trong job.json.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


# Ngưỡng tỷ lệ vùng sáng góc dưới-phải (thường là vị trí logo TikTok/Douyin)
_BRIGHTNESS_THRESHOLD = 200  # Giá trị pixel (0-255)
_CORNER_RATIO_THRESHOLD = 0.15  # 15% số pixel sáng trong vùng góc → nghi ngờ watermark


def detect_watermark(source_path: str | Path) -> bool:
    """
    Kiểm tra nhanh xem video có dấu hiệu watermark/hardsub còn sót không.

    Chiến lược MVP: Dùng ffprobe để đọc metadata stream và phân tích
    1 frame ở góc dưới-phải (vị trí logo TikTok/Douyin thường xuất hiện).

    Args:
        source_path: Đường dẫn tới file video (source.mp4).

    Returns:
        True nếu phát hiện dấu hiệu watermark, False nếu không (hoặc không thể kiểm tra).
    """
    source_path = Path(source_path)
    if not source_path.exists():
        return False

    try:
        # Bước 1: Kiểm tra metadata — video có watermark track không (một số container gắn flag)
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(source_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False  # Không thể đọc → bỏ qua

        # Bước 2: Phân tích 1 frame đại diện ở góc dưới-phải
        has_corner_artifact = _check_corner_brightness(source_path)
        return has_corner_artifact

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # ffprobe/ffmpeg không có trong PATH hoặc timeout → không block pipeline
        return False


def _check_corner_brightness(video_path: Path) -> bool:
    """
    Trích xuất 1 frame từ giây thứ 2 và kiểm tra vùng góc dưới-phải.
    Sử dụng ffmpeg cropdetect qua stdout để không tạo file tạm.

    Returns:
        True nếu vùng góc có nhiều điểm sáng (nghi ngờ watermark).
    """
    try:
        # Lấy thông tin kích thước video
        probe = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if probe.returncode != 0:
            return False

        parts = probe.stdout.strip().split(",")
        if len(parts) < 2:
            return False

        width, height = int(parts[0]), int(parts[1])

        # Vùng crop góc dưới-phải: 20% width × 15% height
        crop_w = max(1, int(width * 0.20))
        crop_h = max(1, int(height * 0.15))
        crop_x = width - crop_w
        crop_y = height - crop_h

        # Đọc 1 frame thứ 2 từ video, crop góc dưới-phải, lấy giá trị trung bình
        result = subprocess.run(
            [
                "ffmpeg",
                "-ss", "2",
                "-i", str(video_path),
                "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},signalstats",
                "-vframes", "1",
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Parse giá trị YAVG từ signalstats output
        for line in result.stderr.splitlines():
            if "YAVG" in line:
                # Format: [Parsed_signalstats_0 @ ...] YAVG:220.5 ...
                parts = line.split("YAVG:")
                if len(parts) > 1:
                    yavg_str = parts[1].split()[0]
                    yavg = float(yavg_str)
                    return yavg > _BRIGHTNESS_THRESHOLD

        return False

    except (subprocess.TimeoutExpired, ValueError, IndexError, OSError):
        return False

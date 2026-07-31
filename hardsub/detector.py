"""
hardsub/detector.py — Vùng phụ đề gốc do người dùng tự khoanh (009-hardsub-blur-reposition).

Trước đây module này dùng OCR (Tesseract qua pytesseract) để TỰ ĐỘNG dò toạ độ
phụ đề gốc. Xác nhận thật trên nhiều video: Tesseract không đọc được phần lớn
kiểu chữ có viền/màu nổi bật phổ biến trên TikTok/YouTube Shorts sau khi video
đã mã hoá — OCR không khả thi cho use-case này (không phải bug có thể sửa bằng
cách chỉnh tham số). Thay vào đó: trích 1 khung hình đại diện cho người dùng tự
khoanh vùng bằng mắt tại chốt kiểm duyệt (`review/gates.py`, `web/backend/
review_api.py`), rồi dùng NGUYÊN vùng đó cho toàn bộ đoạn "có phụ đề gốc".

Dùng chung cho HAI phía: `pipeline.py` (trích khung hình sau bước tách lời) và
`web/backend/` (đọc lại khung hình để hiển thị + ghi vùng đã khoanh — feature
008). MUST NOT import gì từ `web/`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from hardsub.ranges import hardsub_ranges
from media_utils import get_media_duration

# Vị trí (tỉ lệ thời lượng video) lấy khung hình đại diện cho người dùng khoanh
# vùng — 40% để tránh rơi vào intro/outro thường không có phụ đề gốc.
_REPRESENTATIVE_FRAME_RATIO = 0.4


def extract_representative_frame(
    video_path: str | Path, job_dir: str | Path
) -> tuple[Path, dict]:
    """
    Trích 1 khung hình đại diện (giữ nguyên độ phân giải gốc) để người dùng tự
    khoanh vùng phụ đề gốc cần mờ tại chốt kiểm duyệt.

    Idempotent: không trích lại nếu file đã tồn tại — giữ đúng khung hình ban
    đầu người dùng đã dùng để khoanh vùng qua các lượt lưu/duyệt lại.

    Returns: (đường dẫn PNG, {"width": int, "height": int}).
    """
    job_dir = Path(job_dir)
    out_path = job_dir / "hardsub_frame.png"
    if not out_path.exists():
        duration = get_media_duration(video_path)
        ts = max(duration * _REPRESENTATIVE_FRAME_RATIO, 0.0)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", f"{ts:.3f}",
                "-i", str(video_path),
                "-vframes", "1",
                str(out_path),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )

    from PIL import Image

    with Image.open(out_path) as img:
        width, height = img.size
    return out_path, {"width": width, "height": height}


def build_manual_regions(
    video_path: str | Path, no_ranges_text: str | None, job_dir: str | Path, box: dict
) -> Path:
    """
    Ghi `hardsub_regions.json` dùng NGUYÊN vùng người dùng vừa khoanh (`box`)
    cho mọi đoạn "có phụ đề gốc" (`hardsub/ranges.py`) — cùng schema với bản
    OCR cũ nên `merge/subtitle_burner.py::apply_hardsub_blur()` và
    `merge/text_renderer.py::render_cue_overlays()` dùng lại KHÔNG cần sửa gì.

    KHÔNG idempotent: người dùng có thể chỉnh lại vùng nhiều lượt trước khi
    phê duyệt chốt lời thoại — mỗi lượt gọi ghi đè toàn bộ file.
    """
    job_dir = Path(job_dir)
    out_path = job_dir / "hardsub_regions.json"
    total_duration = get_media_duration(video_path)
    ranges = hardsub_ranges(no_ranges_text, total_duration)

    regions = [
        {
            "index": i,
            "start": start,
            "end": end,
            "detected": True,
            "excluded": False,
            "box": box,
        }
        for i, (start, end) in enumerate(ranges)
    ]
    data = {
        "total_duration": total_duration,
        "no_hardsub_ranges": _complement_of(ranges, total_duration),
        "regions": regions,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return out_path


def _complement_of(hardsub_segments: list[list[float]], total_duration: float) -> list[list[float]]:
    """Suy ngược `no_hardsub_ranges` từ các đoạn CÓ phụ đề gốc, để lưu lại đúng
    input đã dùng lúc ghi vùng (data-model.md §2)."""
    if not hardsub_segments:
        return [[0.0, total_duration]] if total_duration > 0 else []

    result: list[list[float]] = []
    cursor = 0.0
    for start, end in hardsub_segments:
        if start > cursor:
            result.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < total_duration:
        result.append([cursor, total_duration])
    return result

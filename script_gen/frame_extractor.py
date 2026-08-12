"""
script_gen/frame_extractor.py — Chia cảnh + trích frame đại diện cho
script_mode="visual" (LLM viết kịch bản CHỈ dựa vào hình ảnh, không dùng
transcript — xem `script_gen/visual_script_generator.py`).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from media_utils import get_media_duration

# Ngưỡng đổi cảnh cho ffmpeg scene-detect filter — 0.4 là mặc định gợi ý của
# ffmpeg, hạ nhẹ xuống 0.35 để bắt được cả chuyển cảnh mềm/pan chậm thường
# gặp ở video unbox.
_SCENE_THRESHOLD = 0.35

# Cảnh ngắn hơn mức này bị coi là vụn (chuyển cảnh giả/nhiễu ảnh) — gộp vào
# cảnh liền trước thay vì tạo 1 nhịp thuyết minh riêng quá ngắn để đọc.
_MIN_SCENE_SECONDS = 1.2

# Cảnh dài hơn mức này bị cắt đều thành nhiều nhịp — 1 cảnh quá dài (video
# unbox cầm tay quay liên tục không cắt cảnh) sẽ chỉ ra đúng 1 câu thuyết
# minh cho cả đoạn dài, kịch bản thưa và không khớp sát hình.
_MAX_SCENE_SECONDS = 4.0

# Khoảng cố định dùng khi scene-detect không ra đủ cảnh thật (video là 1 shot
# liên tục, rất phổ biến ở clip unbox cầm tay) — chia đều theo thời gian thay
# vì theo nội dung hình ảnh.
_FIXED_INTERVAL_SECONDS = 3.0

# Trần số cảnh gửi trong 1 lượt gọi LLM vision — chặn chi phí ảnh/token khi
# video dài hơn dự tính (v1 chỉ nhắm video ngắn, xem
# .claude/plans/dreamy-hugging-globe.md).
_MAX_SCENES = 40

_PTS_TIME_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def _detect_scene_cuts(video_path: Path) -> list[float]:
    """
    Chạy ffmpeg scene-detect filter, trả về mốc thời gian (giây) của từng lần
    đổi cảnh phát hiện được — KHÔNG gồm mốc 0.0 (đầu video).
    """
    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", str(video_path),
        "-an",
        "-vf", f"select='gt(scene,{_SCENE_THRESHOLD})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return sorted({float(m) for m in _PTS_TIME_RE.findall(result.stderr)})


def _normalize_scenes(raw_scenes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Gộp cảnh quá ngắn vào cảnh liền trước, cắt đều cảnh quá dài."""
    if not raw_scenes:
        return []

    merged: list[list[float]] = []
    for start, end in raw_scenes:
        if merged and (end - start) < _MIN_SCENE_SECONDS:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    # Cảnh đầu tiên quá ngắn không có cảnh trước để gộp vào — gộp xuôi sang
    # cảnh kế tiếp thay vì để lọt 1 nhịp quá ngắn.
    if len(merged) > 1 and (merged[0][1] - merged[0][0]) < _MIN_SCENE_SECONDS:
        merged[1][0] = merged[0][0]
        merged.pop(0)

    split: list[tuple[float, float]] = []
    for start, end in merged:
        duration = end - start
        if duration <= _MAX_SCENE_SECONDS:
            split.append((start, end))
            continue
        n_parts = max(1, round(duration / _MAX_SCENE_SECONDS))
        step = duration / n_parts
        split.extend(
            (start + i * step, start + (i + 1) * step) for i in range(n_parts)
        )

    return split


def _fixed_interval_scenes(duration: float) -> list[tuple[float, float]]:
    scenes: list[tuple[float, float]] = []
    t = 0.0
    while t < duration:
        end = min(t + _FIXED_INTERVAL_SECONDS, duration)
        scenes.append((t, end))
        t = end
    return scenes


def _cap_scene_count(
    scenes: list[tuple[float, float]], cap: int
) -> list[tuple[float, float]]:
    """Gộp cặp cảnh liền kề (giảm ~nửa số cảnh mỗi lượt) tới khi <= cap."""
    while len(scenes) > cap:
        merged: list[tuple[float, float]] = []
        i = 0
        while i < len(scenes):
            if i + 1 < len(scenes):
                merged.append((scenes[i][0], scenes[i + 1][1]))
                i += 2
            else:
                merged.append(scenes[i])
                i += 1
        scenes = merged
    return scenes


def extract_scenes(video_path: str | Path) -> list[dict]:
    """
    Chia video thành các cảnh liên tiếp để LLM viết 1 câu thuyết minh / cảnh
    (script_mode="visual").

    Trả về List[{"start": float, "end": float}], phủ kín [0, duration] theo
    đúng thứ tự thời gian.

    Raises:
        RuntimeError: Không đọc được thời lượng video (duration <= 0).
    """
    video_path = Path(video_path)
    duration = get_media_duration(video_path)
    if duration <= 0:
        raise RuntimeError(f"Không đọc được thời lượng video: {video_path}")

    cut_points = _detect_scene_cuts(video_path)
    boundaries = [0.0] + [c for c in cut_points if 0.0 < c < duration] + [duration]
    raw_scenes = [
        (boundaries[i], boundaries[i + 1])
        for i in range(len(boundaries) - 1)
        if boundaries[i + 1] > boundaries[i]
    ]
    scenes = _normalize_scenes(raw_scenes)

    # Video 1 shot liên tục (rất phổ biến ở clip unbox cầm tay) — scene-detect
    # gần như không ra cảnh nào khớp thực tế → chia đều theo thời gian.
    if len(scenes) < 2:
        print(
            "[frame_extractor] Scene-detect không đủ cảnh (video có thể là 1 "
            f"shot liên tục) — chia đều mỗi {_FIXED_INTERVAL_SECONDS}s"
        )
        scenes = _fixed_interval_scenes(duration)

    scenes = _cap_scene_count(scenes, _MAX_SCENES)

    return [{"start": s, "end": e} for s, e in scenes]


def extract_frame(
    video_path: str | Path,
    timestamp: float,
    out_path: str | Path,
    width: int = 768,
) -> Path:
    """
    Trích 1 khung hình tại `timestamp` (giây), resize theo `width` (giữ tỉ lệ,
    chiều cao tự tính chẵn) để giảm token ảnh khi gửi cho LLM vision.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", f"{max(timestamp, 0.0):.3f}",
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", f"scale={width}:-2",
            "-q:v", "3",
            str(out_path),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    return out_path

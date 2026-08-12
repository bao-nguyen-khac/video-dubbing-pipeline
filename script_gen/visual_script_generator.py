"""
script_gen/visual_script_generator.py — generate_visual_script(): sinh
script.json cho script_mode="visual". LLM viết kịch bản CHỈ dựa vào hình ảnh
trích từ video, KHÔNG dùng transcript ASR — dùng cho video không có lời
thoại quan trọng (vd video unbox sản phẩm).
"""

from __future__ import annotations

import json
from pathlib import Path

from script_gen.frame_extractor import extract_frame, extract_scenes
from script_gen.router_client import describe_scenes_in_chunks


def generate_visual_script(
    source_video_path: str | Path,
    job_dir: str | Path,
    user_prompt: str | None = None,
) -> Path:
    """
    Tạo script.json cho script_mode="visual" bằng cách chia cảnh, trích 1
    frame đại diện / cảnh, rồi để LLM (vision) viết 1 câu thuyết minh tiếng
    Việt / cảnh — KHÔNG dùng transcript ASR làm ngữ cảnh.

    Cùng schema output với `router_client.generate_script()`
    (`segments: [{start, end, translated_text}]`) nên
    `tts/segment_synthesizer.py` và `merge/ffmpeg_merge.py` dùng lại nguyên
    xi bước sau, không cần biết script_mode là gì.

    user_prompt: ghi chú định hướng tự do của người dùng, truyền thẳng cho
    `describe_scenes()`. Chỉ ảnh hưởng lượt SINH MỚI — job resume dùng lại
    script.json đã có, không áp dụng lại prompt.

    Returns:
        Path tới script.json vừa tạo (hoặc đã có sẵn từ lần chạy trước — resume).

    Raises:
        RuntimeError: Không đọc được thời lượng video, hoặc LLM vision thất bại.
    """
    job_dir = Path(job_dir)
    script_path = job_dir / "script.json"

    # Resume: cùng quy ước với generate_script() (translate/rewrite) —
    # script.json hợp lệ (có 'segments') thì dùng lại luôn, không tốn thêm
    # lượt gọi LLM/ffmpeg khi resume job dở dang.
    if script_path.exists() and script_path.stat().st_size > 10:
        try:
            with open(script_path, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("segments"):
                return script_path
        except (json.JSONDecodeError, OSError):
            pass  # file hỏng → tạo lại

    scenes = extract_scenes(source_video_path)
    print(f"[visual_script_generator] Chia được {len(scenes)} cảnh")

    frames_dir = job_dir / "frames"
    frame_inputs: list[tuple[float, float, Path]] = []
    for i, scene in enumerate(scenes):
        mid = (scene["start"] + scene["end"]) / 2
        frame_path = frames_dir / f"scene_{i:04d}.jpg"
        extract_frame(source_video_path, mid, frame_path)
        frame_inputs.append((scene["start"], scene["end"], frame_path))

    lines = describe_scenes_in_chunks(frame_inputs, user_prompt=user_prompt)

    segments = [
        {
            "start": scene["start"],
            "end": scene["end"],
            "source_text": None,
            "translated_text": line,
        }
        for scene, line in zip(scenes, lines)
    ]

    script_data = {
        "mode": "visual",
        "content": " ".join(s["translated_text"] for s in segments if s["translated_text"]),
        "target_language": "vi",
        "segments": segments,
    }
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    return script_path

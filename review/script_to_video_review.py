"""
review/script_to_video_review.py — Chốt duyệt kịch bản/prompt của 1 phần
(part) trong dự án script-to-video (xem `script_to_video_pipeline.py`).

Sibling module CỦA `review/gates.py`, KHÔNG mở rộng gates.py trực tiếp: chốt
transcript/script/outline hiện có đều chỉ có 1 trường sửa được / phần tử
(`EDITABLE_FIELD`), còn mỗi screen ở đây có 6 trường sửa được — tổng quát hoá
`gates.py` cho shape này sẽ đụng vào logic 2 pipeline (dub, generate) đã chạy
production đang phụ thuộc, không đáng.

Vẫn TÁI DÙNG các hàm bookkeeping gate-agnostic của gates.py
(`mark_reached`/`mark_edited`/`mark_approved`/`is_approved`,
`UnknownSegmentError`/`GateError`) — chỉ viết riêng phần đọc/ghi payload có
shape khác.
"""

from __future__ import annotations

import json
from pathlib import Path

from review.gates import GateError, UnknownSegmentError

GATE_SCRIPT_TO_VIDEO = "script_to_video"

# Trường text sửa được, không được để trống (mỗi screen ứng với đúng 1 clip
# Google Flow — thiếu 1 trong các trường này thì không đủ để đi tạo video).
_TEXT_FIELDS = (
    "role_label",
    "ingredients_used",
    "prompt_detail_md",
    "visual_prompt",
    "vi_voiceover_text",
)


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _script_path(part_dir: Path) -> Path:
    path = part_dir / "script.json"
    if not path.exists():
        raise GateError("Phần này chưa có kịch bản để duyệt")
    return path


def build_payload(part: dict, part_dir: Path) -> dict:
    """Dựng payload `GET /api/script-to-video-jobs/{slug}/parts/{part_index}/review`.

    Nhận `part_dir` tường minh (thay vì tự suy ra từ slug/part_index) để
    tránh import ngược `script_to_video_pipeline.part_dir_for()` — module đó
    IMPORT `GATE_SCRIPT_TO_VIDEO` từ đây, import ngược lại sẽ vòng lặp.
    """
    data = _read_json(_script_path(part_dir))
    gate_meta = part.get("review_gates", {}).get(GATE_SCRIPT_TO_VIDEO, {})

    screens = [
        {
            "index": s["index"],
            "duration_seconds": s["duration_seconds"],
            "role_label": s["role_label"],
            "ingredients_used": s["ingredients_used"],
            "prompt_detail_md": s["prompt_detail_md"],
            "visual_prompt": s["visual_prompt"],
            "vi_voiceover_text": s["vi_voiceover_text"],
        }
        for s in data.get("screens", [])
    ]

    return {
        "part_index": part["part_index"],
        "gate": GATE_SCRIPT_TO_VIDEO,
        "title": data.get("title"),
        "role": data.get("role"),
        "continuity_notes": data.get("continuity_notes", []),
        "edited": bool(gate_meta.get("edited", False)),
        "reached_at": gate_meta.get("reached_at"),
        "screens": screens,
    }


def save_edits(part_dir: Path, edits: list[dict]) -> int:
    """
    Áp bản sửa của người dùng vào script.json — CHỈ ghi đè trường có mặt
    trong từng phần tử `edits` (partial update).

    Không cho phép xoá trắng các trường text bắt buộc — mỗi screen ứng với
    đúng 1 slot upload video (giờ gộp cả phần thành 1 file merge.mp4), không
    có khái niệm "bỏ screen này" ở chốt duyệt.

    Returns: số screen đã sửa.

    Raises:
        UnknownSegmentError: `index` không tồn tại.
        GateError: cố xoá trắng trường bắt buộc, hoặc `duration_seconds` không hợp lệ.
    """
    path = _script_path(part_dir)
    data = _read_json(path)
    screens = data.get("screens", [])

    touched = 0
    for edit in edits:
        try:
            index = int(edit["index"])
        except (KeyError, TypeError, ValueError):
            raise UnknownSegmentError("Thiếu hoặc sai định dạng số screen (index)") from None
        if index < 0 or index >= len(screens):
            raise UnknownSegmentError(f"Screen số {index} không tồn tại trong chốt này")

        screen = screens[index]
        for field in _TEXT_FIELDS:
            if field not in edit:
                continue
            value = (edit.get(field) or "").strip()
            if not value:
                raise GateError(
                    f"Screen {index}: không thể để trống '{field}' — mỗi screen phải có "
                    "đủ nội dung để đi tạo video"
                )
            screen[field] = value

        if "duration_seconds" in edit:
            try:
                duration = int(edit["duration_seconds"])
            except (TypeError, ValueError):
                raise GateError(f"Screen {index}: 'duration_seconds' phải là số nguyên") from None
            if duration <= 0:
                raise GateError(f"Screen {index}: 'duration_seconds' phải là số dương")
            screen["duration_seconds"] = duration

        touched += 1

    _write_json(path, data)
    return touched

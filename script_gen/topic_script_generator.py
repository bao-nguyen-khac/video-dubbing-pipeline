"""
script_gen/topic_script_generator.py — write_outline_and_scenes(topic): viết
outline + tự tra cứu web (model agent 9router, ROUTER_AGENT_MODEL) + chia
kịch bản thành Scene JSON, cho tính năng "Tạo video từ chủ đề"
(010-topic-video-generation). KHÁC `router_client.py` hiện có — đó là dịch/
viết lại kịch bản từ transcript có sẵn, module này sinh nội dung MỚI từ 1
chủ đề văn bản.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from script_gen.router_client import DEFAULT_MODEL, TruncatedResponseError, _chat_completion

# research.md §3: model 9router có tool-use/browsing riêng cho bước outline —
# ROUTER_MODEL không chắc có tool-use bật sẵn. Trống = fallback ROUTER_MODEL.
AGENT_MODEL = os.environ.get("ROUTER_AGENT_MODEL", "").strip() or DEFAULT_MODEL

# 5 vai trò scene, mỗi vai trò ứng với 1 template hiển thị riêng ở
# merge/hyperframes_renderer.py (không phải chỉ 1 layout ảnh+caption cho mọi
# scene nữa). scenes[0] LUÔN "hook", scenes[-1] LUÔN "outro".
SCENE_TYPES = ("hook", "concept", "transition", "fact", "outro")

_OUTLINE_SYSTEM = """Bạn là biên kịch video ngắn dạng thuyết minh (voiceover) cho mạng xã hội.
Nhiệm vụ: từ MỘT chủ đề do người dùng cho, hãy tự tra cứu thông tin (nếu bạn có khả năng duyệt web) để có dữ kiện chính xác/cập nhật, rồi viết outline VÀ chia kịch bản thành các scene.

Quy tắc:
- Video dài 1-5 phút khi đọc thành tiếng bằng giọng tiếng Việt tự nhiên (tốc độ đọc thông thường).
- Mỗi scene là MỘT đoạn giọng đọc ngắn (1-3 câu), tự nhiên khi đọc thành tiếng, không phải văn viết.
- Mỗi scene có 1 "image_query" — 3-6 từ khoá tiếng ANH, mô tả hình ảnh minh hoạ phù hợp để tìm trên kho ảnh stock (Pexels). KHÔNG dùng tên riêng/thương hiệu cụ thể nếu có thể tránh được vì kho ảnh stock hiếm khi có.
- Toàn bộ narration_text bằng tiếng Việt, image_query bằng tiếng Anh.
- Outline chia thành các phần (sections), mỗi phần có tiêu đề ngắn và các ý chính (key_points).
- Số lượng scene tương ứng nội dung, thường 8-20 scene cho video 1-5 phút.
- Mỗi scene có 1 "type" — vai trò hiển thị của scene đó, PHẢI là 1 trong 5 giá trị:
  - "hook": CHỈ scene đầu tiên (index 0) — câu mở đầu gây tò mò/đặt vấn đề.
  - "concept": scene thân bài bình thường, thuộc 1 "section" của outline.
  - "transition": scene ĐẦU TIÊN của 1 section mới (khi chuyển từ ý này sang ý khác/đối lập) — dùng khi nội dung chuyển hướng rõ rệt (VD từ khái niệm A sang khái niệm B).
  - "fact": scene thân bài nhấn mạnh 1 con số/số liệu/sự thật cụ thể đáng nhớ.
  - "outro": CHỈ scene cuối cùng — câu kết/tổng kết/lời khuyên.
- Mỗi scene có "section_index" — số thứ tự (0-based) của phần tử trong "outline.sections" mà scene đó thuộc về. Scene "hook" và "outro" đặt "section_index": null (không thuộc section nào). Scene "concept"/"transition"/"fact" PHẢI có "section_index" hợp lệ (trỏ đúng vào "outline.sections").

CHỈ trả về JSON hợp lệ theo đúng cấu trúc dưới đây, KHÔNG kèm giải thích, KHÔNG bọc trong markdown code fence:
{
  "outline": {
    "sections": [
      {"title": "...", "key_points": ["...", "..."]}
    ]
  },
  "scenes": [
    {"index": 0, "type": "hook", "section_index": null, "narration_text": "...", "image_query": "..."},
    {"index": 1, "type": "concept", "section_index": 0, "narration_text": "...", "image_query": "..."}
  ]
}"""


class OutlineParseError(RuntimeError):
    """Output của model không parse được thành JSON đúng schema — KHÔNG âm
    thầm dùng bản hỏng, job phải fail rõ ràng ở bước outlining (theo tinh
    thần TruncatedResponseError của router_client.py)."""


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(raw: str) -> dict:
    """Bỏ markdown code fence nếu model lỡ bọc JSON vào đó, rồi parse."""
    cleaned = _JSON_FENCE_RE.sub("", raw.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise OutlineParseError(
            f"Không parse được JSON từ output của model '{AGENT_MODEL}': {e}. "
            f"Output nhận được (rút gọn): {cleaned[:500]!r}"
        ) from e


def _validate_outline_scenes(data: dict) -> None:
    """Kiểm tra tối thiểu đúng shape data-model.md §2-3 — không kiểm tra sâu
    ngữ nghĩa (đó không phải việc của layer này)."""
    outline = data.get("outline")
    scenes = data.get("scenes")
    if not isinstance(outline, dict) or not isinstance(outline.get("sections"), list):
        raise OutlineParseError("JSON thiếu 'outline.sections' hoặc sai kiểu (cần list)")
    for section in outline["sections"]:
        if not isinstance(section, dict) or "title" not in section:
            raise OutlineParseError("Một phần tử 'outline.sections' thiếu 'title'")
    section_count = len(outline["sections"])
    if not isinstance(scenes, list) or not scenes:
        raise OutlineParseError("JSON thiếu 'scenes' hoặc rỗng (cần ít nhất 1 scene)")
    for scene in scenes:
        if not isinstance(scene, dict) or not (scene.get("narration_text") or "").strip():
            raise OutlineParseError("Một phần tử 'scenes' thiếu 'narration_text'")
        if not (scene.get("image_query") or "").strip():
            raise OutlineParseError("Một phần tử 'scenes' thiếu 'image_query'")
        scene_type = scene.get("type")
        if scene_type not in SCENE_TYPES:
            raise OutlineParseError(
                f"Scene có 'type' không hợp lệ: {scene_type!r} (phải là 1 trong {SCENE_TYPES})"
            )
        section_index = scene.get("section_index")
        if scene_type in ("concept", "transition", "fact"):
            if not isinstance(section_index, int) or not (0 <= section_index < section_count):
                raise OutlineParseError(
                    f"Scene type={scene_type!r} có 'section_index' không hợp lệ: "
                    f"{section_index!r} (outline có {section_count} section)"
                )
    if scenes[0].get("type") != "hook":
        raise OutlineParseError("Scene đầu tiên (index 0) phải có type='hook'")
    if scenes[-1].get("type") != "outro":
        raise OutlineParseError("Scene cuối cùng phải có type='outro'")


def write_outline_and_scenes(topic: str) -> dict:
    """
    1 lượt gọi 9router bằng model agent (`AGENT_MODEL`) — prompt yêu cầu viết
    outline có cấu trúc VÀ tự tra cứu web khi cần, trả JSON đúng schema
    data-model.md §2-3.

    US2/FR-009: nếu lượt gọi agent lỗi (mạng/timeout/tool-use không khả dụng),
    fallback gọi lại BẰNG `ROUTER_MODEL` thường (không yêu cầu search) — job
    KHÔNG được fail chỉ vì lý do search (Phase 4). `TruncatedResponseError`
    KHÔNG rơi vào nhánh fallback này — đổi model không giải quyết được câu trả
    lời bị cắt, đúng tinh thần `_chat_completion()` (router_client.py).

    Trả về dict `{"outline": {"sections": [...]}, "scenes": [{"index",
    "narration_text", "image_query"}, ...], "search_used": bool}` — CHƯA ghi
    ra file (xem `write_outline_and_scenes_to_disk()`).

    Raises:
        OutlineParseError: Output không parse được hoặc sai schema (ở CẢ 2
            lượt gọi, nếu có fallback).
        TruncatedResponseError: Output bị cắt vì chạm trần token.
    """
    try:
        raw = _chat_completion(
            _OUTLINE_SYSTEM, f"Chủ đề: {topic}", temperature=0.7, model=AGENT_MODEL
        )
        search_used = True
    except TruncatedResponseError:
        raise
    except Exception as e:
        print(
            f"[topic_script_generator] Agent model '{AGENT_MODEL}' lỗi "
            f"({type(e).__name__}: {e}) → fallback '{DEFAULT_MODEL}' (không search)"
        )
        raw = _chat_completion(
            _OUTLINE_SYSTEM, f"Chủ đề: {topic}", temperature=0.7, model=DEFAULT_MODEL
        )
        search_used = False

    data = _extract_json(raw)
    _validate_outline_scenes(data)

    sections = data["outline"]["sections"]

    # index đánh số lại tuần tự — không tin tưởng model tự đánh đúng thứ tự
    scenes = []
    for i, scene in enumerate(data["scenes"]):
        section_index = scene.get("section_index")
        scenes.append(
            {
                "index": i,
                "type": scene["type"],
                "section_index": section_index,
                # Denormalize tiêu đề section vào scene — renderer chỉ cần
                # scenes.json, không cần đọc thêm outline.json (research.md §5b).
                "section_title": sections[section_index]["title"] if section_index is not None else None,
                "narration_text": scene["narration_text"].strip(),
                "image_query": scene["image_query"].strip(),
            }
        )
    return {"outline": data["outline"], "scenes": scenes, "search_used": search_used}


def write_outline_and_scenes_to_disk(topic: str, job_dir: Path) -> tuple[Path, Path]:
    """
    Gọi `write_outline_and_scenes()` rồi ghi `outline.json` (data-model.md §2)
    và `scenes.json` (data-model.md §3, CHƯA có `image_path`/`voice_path`/
    `duration` — các bước sau điền dần) ra `job_dir`.

    `outline.json.search_used` phản ánh ĐÚNG nhánh đã chạy thật ở
    `write_outline_and_scenes()` (US2/SC-004) — không phải giá trị cố định.

    Returns: (đường dẫn outline.json, đường dẫn scenes.json).
    """
    job_dir = Path(job_dir)
    result = write_outline_and_scenes(topic)

    outline_path = job_dir / "outline.json"
    with open(outline_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "topic": topic,
                "search_used": result["search_used"],
                "sections": result["outline"]["sections"],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    scenes_path = job_dir / "scenes.json"
    with open(scenes_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "outline.json",
                "scenes": [
                    {
                        "index": s["index"],
                        "type": s["type"],
                        "section_title": s["section_title"],
                        "narration_text": s["narration_text"],
                        "image_query": s["image_query"],
                        "image_path": None,
                        "voice_path": None,
                        "duration": None,
                    }
                    for s in result["scenes"]
                ],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return outline_path, scenes_path

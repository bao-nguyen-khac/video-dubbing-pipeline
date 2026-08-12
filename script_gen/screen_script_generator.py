"""
script_gen/screen_script_generator.py — write_part_script(): sinh kịch bản +
prompt AI-video-gen cho ĐÚNG 1 "part" của 1 dự án script-to-video (xem
`script_gen/character_bible_generator.py` cho phần "character bible" dùng
chung cả arc).

Định dạng mô phỏng ĐÚNG quy trình thật của người dùng: Google Flow / Gemini
Omni Flash (KHÔNG `--ar 9:16`/tham số Midjourney), thời lượng mỗi screen tự
do (4/6/8/10s), có chuỗi continuity/handoff nối cảnh giữa các screen — xem
`script-to-video/2100-pov-ky-su-he-thong-tau-khai-thac/pov-2100-asteroid-
mining-series-rules.md` (ví dụ viết tay làm chuẩn đối chiếu).
"""

from __future__ import annotations

import json
from pathlib import Path

from script_gen.router_client import DEFAULT_MODEL, _chat_completion
from script_gen.topic_script_generator import _extract_json

# VN đọc tự nhiên ~2.2-2.4 từ/giây (bao gồm khoảng nghỉ nhịp thở).
_VI_WORDS_PER_SECOND = 2.3

_PART_SCRIPT_SYSTEM_TEMPLATE = """Bạn là biên kịch + đạo diễn hình ảnh cho 1 phần (part) trong series video POV ngắn, sản xuất bằng Google Flow (model Gemini Omni Flash) — KHÔNG phải Midjourney/Kling/Runway, nên TUYỆT ĐỐI KHÔNG thêm `--ar 9:16` hay bất kỳ tham số dạng Midjourney nào vào prompt. Định dạng khung hình (9:16) được chọn trong giao diện Flow, không nhúng vào prompt.

## Bối cảnh nhân vật/arc (đã chốt, PHẢI nhất quán tuyệt đối)
- Nhân vật: {character_name} — {role_title}
- Tên arc: {arc_title}
{character_description_md}

## Phần này (part {part_display}/{num_parts})
- Tên phần: {part_title}
- Vai trò kịch bản: {part_role}
- Tóm tắt: {part_synopsis}
- Số screen mục tiêu: ĐÚNG {screen_count} screen.

## Quy tắc viết prompt cho từng screen (Omni Flash, 5 yếu tố lồng trong 1 đoạn prompt liền mạch)
Mỗi "visual_prompt" là 1 đoạn văn tiếng Anh liền mạch dán thẳng vào Flow, PHẢI thể hiện đủ 5 yếu tố (không cần tách dòng, viết tự nhiên):
1. **Goal** — loại cảnh / vai trò của screen trong chuỗi.
2. **Input Role** — gọi tên rõ ảnh Ingredients dùng cho screen này (VD "Using the provided images for X and Y, ...").
3. **Scene** — mô tả bối cảnh ngắn gọn, trọng tâm.
4. **Motion** — camera + hành động, chia theo mốc giây khớp ĐÚNG thời lượng screen (VD "From 0-4 seconds: ... From 4-8 seconds: ...").
5. **Constraints** — giữ trang phục/đặc điểm nhận diện nhân vật xuyên suốt, khoá hướng camera/nhân vật nếu cần nối cảnh.
Kết thúc mỗi visual_prompt bằng: mô tả âm thanh nền (Ambient noise: ...), hiệu ứng (SFX: ... nếu có), và LUÔN LUÔN `Dialogue: None.` (lời thoại lồng tiếng ở hậu kỳ, nhân vật trong hình không tự nói).

## Thời lượng & nối cảnh (continuity) — bắt buộc
- Mỗi screen chọn thời lượng TRONG {{4, 6, 8, 10}} giây — chọn sao cho tổng cả phần rơi vào khoảng 70-90 giây với {screen_count} screen.
- "prompt_detail_md" của MỖI screen (markdown, có thể có mục khác nhau tuỳ screen — không bắt buộc template cứng) PHẢI luôN có tối thiểu:
  - Mục nối cảnh: **START** (trạng thái mở đầu, khớp END của screen trước) và **END STATE** (trạng thái kết thúc, để screen sau mở tiếp) — khoá hướng trái/phải nếu nhân vật di chuyển hoặc quay đầu, tránh model tự "lật gương".
  - Mục nhịp trong clip: liệt kê mốc giây khớp với "Motion" trong visual_prompt.
- "continuity_notes": danh sách các câu MÔ TẢ NGẮN cách nối giữa 2 screen liên tiếp, ĐÚNG {continuity_notes_count} phần tử theo thứ tự{continuity_notes_note}.
{previous_ending_block}

## Lời thoại (VO)
"vi_voiceover_text" mỗi screen bằng tiếng Việt, tự nhiên khi đọc thành tiếng, độ dài ước lượng {words_per_second} từ/giây theo đúng "duration_seconds" đã chọn cho screen đó — KHÔNG cố định số từ chung cho mọi screen vì thời lượng khác nhau.

CHỈ trả về JSON hợp lệ theo đúng cấu trúc dưới đây, KHÔNG kèm giải thích, KHÔNG bọc trong markdown code fence:
{{
  "title": "...", "role": "{part_role}",
  "screens": [
    {{"index": 0, "duration_seconds": 8, "role_label": "...", "ingredients_used": "...", "prompt_detail_md": "## ...\\n- **START:** ...\\n- **END STATE:** ...\\n## Nhịp trong clip\\n- **0-4s:** ...", "visual_prompt": "Using the provided images for ...", "vi_voiceover_text": "..."}}
  ],
  "continuity_notes": ["S1 → S2: ...", "..."]
}}"""


class ScreenScriptParseError(RuntimeError):
    """Output của model không parse được thành JSON đúng schema — KHÔNG âm
    thầm dùng bản hỏng, job phải fail rõ ràng ở bước scripting."""


def _validate_part_script(data: dict, expected_screen_count: int, expected_notes_count: int) -> None:
    """Kiểm tra tối thiểu đúng shape — không kiểm tra sâu ngữ nghĩa."""
    if not (data.get("title") or "").strip():
        raise ScreenScriptParseError("JSON thiếu 'title'")

    screens = data.get("screens")
    if not isinstance(screens, list) or len(screens) != expected_screen_count:
        raise ScreenScriptParseError(
            f"JSON phải có đúng {expected_screen_count} screen trong 'screens' "
            f"(nhận được: {len(screens) if isinstance(screens, list) else 'không phải list'})"
        )
    required_fields = (
        "role_label",
        "ingredients_used",
        "prompt_detail_md",
        "visual_prompt",
        "vi_voiceover_text",
    )
    for i, screen in enumerate(screens):
        if not isinstance(screen, dict):
            raise ScreenScriptParseError(f"Screen {i} không phải object")
        for field in required_fields:
            if not (screen.get(field) or "").strip():
                raise ScreenScriptParseError(f"Screen {i} thiếu trường '{field}'")
        duration = screen.get("duration_seconds")
        if not isinstance(duration, int) or duration <= 0:
            raise ScreenScriptParseError(f"Screen {i} có 'duration_seconds' không hợp lệ: {duration!r}")

    notes = data.get("continuity_notes")
    if not isinstance(notes, list) or len(notes) != expected_notes_count:
        raise ScreenScriptParseError(
            f"JSON phải có đúng {expected_notes_count} phần tử trong 'continuity_notes' "
            f"(nhận được: {len(notes) if isinstance(notes, list) else 'không phải list'})"
        )
    for i, note in enumerate(notes):
        if not (note or "").strip():
            raise ScreenScriptParseError(f"continuity_notes[{i}] rỗng")


def write_part_script(
    character: dict,
    part_index: int,
    target_screen_count: int = 10,
    previous_part_last_screen: dict | None = None,
) -> dict:
    """
    1 lượt gọi 9router — trả JSON kịch bản 1 part đúng schema ở trên.

    `character`: dict trả về từ `character_bible_generator.write_character_bible()`.
    `previous_part_last_screen`: screen cuối của part TRƯỚC đó (dict có
    `prompt_detail_md`/`role_label`) nếu `part_index > 0` — dùng để chốt
    continuity xuyên phần (screen 1 của part này PHẢI mở tiếp từ END STATE
    của screen đó). `None` cho part đầu tiên.

    Raises:
        ScreenScriptParseError: Output không parse được hoặc sai schema.
        TruncatedResponseError: Output bị cắt vì chạm trần token.
    """
    num_parts = len(character["parts_summary"])
    part_summary = character["parts_summary"][part_index]
    screen_count = target_screen_count
    words_per_second = _VI_WORDS_PER_SECOND

    has_previous = previous_part_last_screen is not None
    continuity_notes_count = screen_count - 1 + (1 if has_previous else 0)
    continuity_notes_note = (
        " — PHẦN TỬ ĐẦU TIÊN mô tả nối tiếp từ phần trước (xem mục dưới), các phần tử sau lần lượt S1→S2, S2→S3, ..."
        if has_previous
        else " (S1→S2, S2→S3, ...)"
    )
    previous_ending_block = (
        (
            "\n## Nối tiếp từ phần trước (bắt buộc)\n"
            f"Screen cuối của phần trước (vai trò: {previous_part_last_screen.get('role_label', '')}) "
            f"kết thúc ở trạng thái sau:\n```\n{previous_part_last_screen.get('prompt_detail_md', '')}\n```\n"
            "Screen ĐẦU TIÊN (index 0) của phần này PHẢI mở tiếp CHÍNH XÁC từ END STATE đó "
            "(cùng góc máy/tư thế/hướng nhân vật — không bắt đầu lại bằng establishing shot mới)."
        )
        if has_previous
        else ""
    )

    system_prompt = _PART_SCRIPT_SYSTEM_TEMPLATE.format(
        character_name=character["character_name"],
        role_title=character["role_title"],
        arc_title=character["arc_title"],
        character_description_md=character["character_description_md"],
        part_display=part_index + 1,
        num_parts=num_parts,
        part_title=part_summary["title"],
        part_role=part_summary["role"],
        part_synopsis=part_summary["synopsis"],
        screen_count=screen_count,
        continuity_notes_count=continuity_notes_count,
        continuity_notes_note=continuity_notes_note,
        previous_ending_block=previous_ending_block,
        words_per_second=words_per_second,
    )

    raw = _chat_completion(system_prompt, "Viết kịch bản cho phần này.", temperature=0.8, model=DEFAULT_MODEL)
    data = _extract_json(raw)
    _validate_part_script(data, screen_count, continuity_notes_count)

    screens = []
    for i, screen in enumerate(data["screens"]):
        screens.append(
            {
                "index": i,
                "duration_seconds": screen["duration_seconds"],
                "role_label": screen["role_label"].strip(),
                "ingredients_used": screen["ingredients_used"].strip(),
                "prompt_detail_md": screen["prompt_detail_md"].strip(),
                "visual_prompt": screen["visual_prompt"].strip(),
                "vi_voiceover_text": screen["vi_voiceover_text"].strip(),
                "voice_path": None,
                "voice_duration": None,
            }
        )

    return {
        "part_index": part_index,
        "title": data["title"].strip(),
        "role": part_summary["role"],
        "screens": screens,
        "continuity_notes": [note.strip() for note in data["continuity_notes"]],
        "uploaded_video_path": None,
        "voice_full_path": None,
        "voice_full_duration": None,
    }


def write_part_script_to_disk(
    character: dict,
    part_index: int,
    target_screen_count: int,
    part_dir: str | Path,
    previous_part_last_screen: dict | None = None,
) -> Path:
    """Gọi `write_part_script()` rồi ghi `script.json` ra `part_dir`.

    Returns: đường dẫn script.json vừa tạo.
    """
    part_dir = Path(part_dir)
    data = write_part_script(character, part_index, target_screen_count, previous_part_last_screen)

    script_path = part_dir / "script.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return script_path

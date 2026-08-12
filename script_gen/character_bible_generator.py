"""
script_gen/character_bible_generator.py — write_character_bible(): sinh
"character bible" cho 1 dự án script-to-video (nhân vật/thế giới dùng chung
xuyên suốt mọi phần của 1 arc POV) — mô phỏng đúng cấu trúc
`character-bible.md` viết tay trong `script-to-video/<slug>/`.

Chỉ sinh VĂN BẢN (mô tả nhân vật + prompt ảnh Ingredients) — KHÔNG tự gọi
API sinh ảnh (Gemini 2.5 Flash Image). Người dùng tự tạo ảnh tham chiếu từ
các prompt này rồi upload thủ công vào Google Flow (bước ngoài hệ thống,
đúng quy trình thật — xem series rules).
"""

from __future__ import annotations

import json
from pathlib import Path

from script_gen.router_client import DEFAULT_MODEL, _chat_completion
from script_gen.topic_script_generator import _extract_json

_CHARACTER_BIBLE_SYSTEM = """Bạn là biên kịch cho series video ngắn dạng POV (góc nhìn thứ nhất) đăng TikTok/Reels/Shorts.
Nhiệm vụ: từ MỘT ý tưởng nhân vật/bối cảnh do người dùng cho, xây dựng "character bible" — tài liệu tham chiếu dùng CHUNG cho {num_parts} phần (part) của arc này, để nhân vật/bối cảnh nhất quán xuyên suốt khi tạo video bằng AI (Google Flow / Gemini Omni Flash, dùng ảnh tham chiếu "Ingredients").

Yêu cầu:
- "character_name": tên nhân vật chính (ngắn, dễ nhớ).
- "role_title": vai trò/nghề nghiệp của nhân vật (VD: "Kỹ sư hệ thống / Robot Fleet").
- "arc_title": tên arc/tập truyện ngắn gọn.
- "parts_summary": ĐÚNG {num_parts} phần tử, mỗi phần tử {{"index": 0-based, "title": tên phần, "role": vai trò kịch bản (VD "Hook + Đào sâu" cho phần đầu, "Twist + Kết/CTA" cho phần cuối, các phần giữa là leo thang/twist), "synopsis": tóm tắt 2-3 câu nội dung phần đó}}. Phần đầu PHẢI là hook + giới thiệu nhân vật/bối cảnh, kết bằng 1 tình huống dở dang. Phần cuối PHẢI có kết/CTA hoặc câu đọng lại. Nội dung các phần phải NỐI TIẾP nhau thành 1 câu chuyện liền mạch, KHÔNG lặp ý.
- "character_description_md": mô tả bằng markdown (dùng bullet "* **Tên mục:** nội dung"), PHẢI có các mục: ngoại hình nhân vật (đủ chi tiết để AI tạo ảnh nhất quán: tuổi, dáng người, khuôn mặt, tóc, trang phục, phụ kiện đặc trưng), nơi làm việc/bối cảnh chính, thế giới/bối cảnh lớn hơn (thời gian, địa điểm, công nghệ/quy tắc thế giới nếu có). Có thể thêm 1 yếu tố xuyên suốt phụ (VD AI đồng hành, vật nuôi, đồng nghiệp) nếu hợp lý với ý tưởng — không bắt buộc.
- "ingredients": ĐÚNG 4 phần tử, mỗi phần tử {{"label": nhãn ngắn tiếng Việt (VD "Erik (ảnh nhân vật)"), "image_prompt": 1 đoạn prompt tiếng ANH để tạo ảnh tham chiếu bằng Gemini 2.5 Flash Image}}. 4 ảnh PHẢI gồm: (1) ảnh nhân vật chính toàn thân/bán thân, nền phẳng trung tính, không logo/chữ/watermark, photorealistic; (2) ảnh bối cảnh nội thất nơi làm việc chính; (3) ảnh bối cảnh thứ 2 (ngoài trời/qua cửa sổ/không gian khác liên quan câu chuyện); (4) ảnh cận 1 vật thể/thiết bị đặc trưng của câu chuyện. Mỗi image_prompt phải nêu rõ "no people" (trừ ảnh nhân vật), "no logos, no text, no watermark", phong cách photorealistic.

{series_notes_block}

CHỈ trả về JSON hợp lệ theo đúng cấu trúc dưới đây, KHÔNG kèm giải thích, KHÔNG bọc trong markdown code fence:
{{
  "character_name": "...", "role_title": "...", "arc_title": "...",
  "parts_summary": [{{"index": 0, "title": "...", "role": "...", "synopsis": "..."}}],
  "character_description_md": "* **...:** ...",
  "ingredients": [{{"label": "...", "image_prompt": "..."}}]
}}"""


class CharacterBibleParseError(RuntimeError):
    """Output của model không parse được thành JSON đúng schema."""


def _validate_character(data: dict, num_parts: int) -> None:
    for field in ("character_name", "role_title", "arc_title", "character_description_md"):
        if not (data.get(field) or "").strip():
            raise CharacterBibleParseError(f"JSON thiếu trường '{field}'")

    parts_summary = data.get("parts_summary")
    if not isinstance(parts_summary, list) or len(parts_summary) != num_parts:
        raise CharacterBibleParseError(
            f"JSON phải có đúng {num_parts} phần tử trong 'parts_summary' "
            f"(nhận được: {len(parts_summary) if isinstance(parts_summary, list) else 'không phải list'})"
        )
    for i, part in enumerate(parts_summary):
        for field in ("title", "role", "synopsis"):
            if not isinstance(part, dict) or not (part.get(field) or "").strip():
                raise CharacterBibleParseError(f"parts_summary[{i}] thiếu trường '{field}'")

    ingredients = data.get("ingredients")
    if not isinstance(ingredients, list) or len(ingredients) != 4:
        raise CharacterBibleParseError(
            f"JSON phải có đúng 4 phần tử trong 'ingredients' "
            f"(nhận được: {len(ingredients) if isinstance(ingredients, list) else 'không phải list'})"
        )
    for i, ing in enumerate(ingredients):
        for field in ("label", "image_prompt"):
            if not isinstance(ing, dict) or not (ing.get(field) or "").strip():
                raise CharacterBibleParseError(f"ingredients[{i}] thiếu trường '{field}'")


def write_character_bible(
    premise: str,
    num_parts: int = 2,
    target_screens_per_part: int = 10,
    series_notes: str | None = None,
) -> dict:
    """
    1 lượt gọi 9router — trả JSON character bible đúng schema ở trên.

    Raises:
        ValueError: `premise.strip()` rỗng, hoặc `num_parts` không dương.
        CharacterBibleParseError: Output không parse được hoặc sai schema.
        TruncatedResponseError: Output bị cắt vì chạm trần token.
    """
    if not premise.strip():
        raise ValueError("Ý tưởng nhân vật/bối cảnh không được để trống")
    if num_parts <= 0:
        raise ValueError("Số phần (num_parts) phải là số dương")

    series_notes_block = (
        f"Quy tắc/ghi chú series PHẢI tuân theo:\n{series_notes.strip()}"
        if series_notes and series_notes.strip()
        else ""
    )
    system_prompt = _CHARACTER_BIBLE_SYSTEM.format(
        num_parts=num_parts, series_notes_block=series_notes_block
    )
    user_message = (
        f"Ý tưởng nhân vật/bối cảnh: {premise}\n"
        f"Mỗi phần khoảng {target_screens_per_part} screen."
    )

    raw = _chat_completion(system_prompt, user_message, temperature=0.8, model=DEFAULT_MODEL)
    data = _extract_json(raw)
    _validate_character(data, num_parts)

    return {
        "character_name": data["character_name"].strip(),
        "role_title": data["role_title"].strip(),
        "arc_title": data["arc_title"].strip(),
        "parts_summary": [
            {
                "index": i,
                "title": p["title"].strip(),
                "role": p["role"].strip(),
                "synopsis": p["synopsis"].strip(),
            }
            for i, p in enumerate(data["parts_summary"])
        ],
        "character_description_md": data["character_description_md"].strip(),
        "ingredients": [
            {"label": ing["label"].strip(), "image_prompt": ing["image_prompt"].strip()}
            for ing in data["ingredients"]
        ],
    }


def write_character_bible_to_disk(
    premise: str,
    num_parts: int,
    target_screens_per_part: int,
    project_dir: str | Path,
    series_notes: str | None = None,
) -> Path:
    """Gọi `write_character_bible()` rồi ghi `character.json` ra `project_dir`.

    Returns: đường dẫn character.json vừa tạo.
    """
    project_dir = Path(project_dir)
    data = write_character_bible(premise, num_parts, target_screens_per_part, series_notes)

    character_path = project_dir / "character.json"
    with open(character_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return character_path

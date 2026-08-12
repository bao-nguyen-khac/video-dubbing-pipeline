"""
script_gen/script_to_video_renderer.py — render_all_part()/render_character_bible_md():
dựng character.json + part script.json (sinh bởi character_bible_generator.py/
screen_script_generator.py) thành character-bible.md + script.md +
prompt-screen-N.md + prompt-screen-vi.md + voiceover.json, ĐÚNG định dạng
mẫu viết tay `script-to-video/2100-pov-ky-su-he-thong-tau-khai-thac/`.

Renderer THUẦN (JSON → markdown/JSON), không gọi LLM — mọi nội dung đã có
sẵn trong `character`/`part_data`.
"""

from __future__ import annotations

import json
from pathlib import Path


def _word_count(text: str) -> int:
    return len(text.split())


# ─── Character bible (1 lần / project) ────────────────────────────────────────


def render_character_bible_md(character: dict, project_dir: Path) -> Path:
    """Ghi `character-bible.md` — tham chiếu nhân vật/thế giới dùng chung cho
    mọi phần của arc."""
    project_dir = Path(project_dir)
    parts_summary = character["parts_summary"]

    lines: list[str] = []
    lines.append(f'# Character Bible: "{character["arc_title"]}" — {character["character_name"]} ({character["role_title"]})')
    lines.append("")
    lines.append(
        "> Tham chiếu bắt buộc cho MỌI phần của arc này. Tạo bộ ảnh Ingredients "
        "trước khi generate Google Flow."
    )
    lines.append("")
    lines.append(f"## Tóm tắt Arc ({len(parts_summary)} phần)")
    for p in parts_summary:
        n = p["index"] + 1
        lines.append(f'{n}. **Phần {n} — "{p["title"]}"** ({p["role"]}): {p["synopsis"]}')
    lines.append("")
    lines.append(f"## Nhân vật chính: {character['character_name']}")
    lines.append(character["character_description_md"])
    lines.append("")
    lines.append("## Ingredients — Prompt tạo ảnh tham chiếu (Gemini 2.5 Flash Image)")
    labels = " / ".join(ing["label"] for ing in character["ingredients"])
    lines.append(f"> Tạo **4 ảnh**: {labels}. Không logo, không chữ, không watermark.")
    lines.append("")
    for i, ing in enumerate(character["ingredients"]):
        lines.append(f"**{i + 1}. {ing['label']}:**")
        lines.append("```")
        lines.append(ing["image_prompt"])
        lines.append("```")
        lines.append("")

    path = project_dir / "character-bible.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


# ─── Continuity labels ──────────────────────────────────────────────────────


def _continuity_labels(part_data: dict) -> list[str]:
    screen_count = len(part_data["screens"])
    has_cross_part = len(part_data["continuity_notes"]) == screen_count
    labels: list[str] = []
    if has_cross_part:
        prev_part_display = part_data["part_index"]  # 0-based index == prev part's 1-based display
        labels.append(f"Phần {prev_part_display} S{screen_count} → Phần {prev_part_display + 1} S1")
    for i in range(1, screen_count):
        labels.append(f"S{i} → S{i + 1}")
    return labels


# ─── Per-part renderers ─────────────────────────────────────────────────────


def render_script_md(part_data: dict, part_dir: Path, num_parts: int) -> Path:
    """Ghi `script.md` — tổng quan 1 phần (continuity chain + bảng phân cảnh
    + voiceover)."""
    part_dir = Path(part_dir)
    part_display = part_data["part_index"] + 1
    screens = part_data["screens"]
    total_seconds = sum(s["duration_seconds"] for s in screens)

    lines: list[str] = []
    lines.append(f'# Phần {part_display}/{num_parts}: "{part_data["title"]}" (~{total_seconds}s · {len(screens)} screen)')
    lines.append("")
    lines.append("> **Format:** 9:16 · Google Flow · Gemini Omni Flash  ")
    lines.append("> **Ingredients:** [`../character-bible.md`](../character-bible.md)  ")
    lines.append(f'> **Vai trò:** {part_data["role"]}')
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Continuity chain (khớp cắt)")
    lines.append("")
    lines.append("| Từ → Sang | Ghi chú |")
    lines.append("|---|---|")
    for label, note in zip(_continuity_labels(part_data), part_data["continuity_notes"]):
        lines.append(f"| {label} | {note} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Bảng phân cảnh")
    lines.append("")
    lines.append("| # | Thời lượng | Vai trò | File |")
    lines.append("|---|------|---------|------|")
    for s in screens:
        n = s["index"] + 1
        lines.append(f'| {n} | **{s["duration_seconds"]}s** | {s["role_label"]} | [`prompt-screen-{n}.md`](prompt-screen-{n}.md) |')
    lines.append("")
    lines.append(f"**Tổng:** {total_seconds} giây · [`prompt-screen-vi.md`](prompt-screen-vi.md)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Voiceover theo screen")
    lines.append("")
    for s in screens:
        n = s["index"] + 1
        lines.append(f'{n}. *({s["duration_seconds"]}s)* *"{s["vi_voiceover_text"]}"*')

    path = part_dir / "script.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def render_prompt_screen_md(screen: dict, part_dir: Path) -> Path:
    """Ghi `prompt-screen-{n}.md` — prompt tiếng Anh cho 1 screen, dán thẳng
    vào Google Flow."""
    part_dir = Path(part_dir)
    n = screen["index"] + 1

    lines: list[str] = []
    lines.append(f'# Prompt Screen {n} — {screen["role_label"]}')
    lines.append("")
    lines.append("## Thời lượng clip")
    lines.append(f'**{screen["duration_seconds"]} giây** — chọn **{screen["duration_seconds"]}s** trong UI Google Flow.')
    lines.append("")
    lines.append("## Ingredients")
    lines.append(screen["ingredients_used"])
    lines.append("")
    lines.append(screen["prompt_detail_md"])
    lines.append("")
    lines.append("## Visual Prompt (dán thẳng vào Flow)")
    lines.append("```")
    lines.append(screen["visual_prompt"])
    lines.append("```")
    lines.append("")
    lines.append(f'## VO (~{screen["duration_seconds"]}s)')
    lines.append(f'*"{screen["vi_voiceover_text"]}"*')

    path = part_dir / f"prompt-screen-{n}.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def render_prompt_screen_vi_md(part_data: dict, part_dir: Path) -> Path:
    """Ghi `prompt-screen-vi.md` — tổng hợp (Visual Prompt tiếng Anh + VO
    tiếng Việt) từng screen trong 1 file, để copy nhanh không cần mở N file."""
    part_dir = Path(part_dir)
    part_display = part_data["part_index"] + 1

    lines: list[str] = []
    lines.append(f'# Tổng hợp — Phần {part_display}: "{part_data["title"]}"')
    lines.append("")
    lines.append("> Chi tiết continuity: xem `script.md`.")
    lines.append("")
    for s in part_data["screens"]:
        n = s["index"] + 1
        lines.append(f'### S{n} · {s["duration_seconds"]} giây')
        lines.append(f'`{s["visual_prompt"]}`')
        lines.append(f'VO: *"{s["vi_voiceover_text"]}"*')
        lines.append("")

    path = part_dir / "prompt-screen-vi.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def render_voiceover_json(part_data: dict, part_dir: Path) -> Path:
    """Ghi `voiceover.json` — dữ liệu kịch bản GỌN cho TTS (chỉ duration +
    text), tách khỏi nội dung prompt (chỉ nằm trong markdown) — đúng quy ước
    file mẫu viết tay."""
    part_dir = Path(part_dir)
    screens = part_data["screens"]
    data = {
        "part": f"part-{part_data['part_index'] + 1}",
        "video_raw": "video-raw/merge.mp4",
        "total_duration_seconds": sum(s["duration_seconds"] for s in screens),
        "screens": [
            {"index": s["index"], "duration_seconds": s["duration_seconds"], "text": s["vi_voiceover_text"]}
            for s in screens
        ],
    }
    path = part_dir / "voiceover.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def render_all_part(part_data: dict, part_dir: Path, num_parts: int) -> dict:
    """Dựng toàn bộ deliverable của 1 phần, trả về path để pipeline ghi vào
    trạng thái/nhật ký nếu cần."""
    part_dir = Path(part_dir)
    part_dir.mkdir(parents=True, exist_ok=True)

    script_md_path = render_script_md(part_data, part_dir, num_parts)
    prompt_screen_paths = [render_prompt_screen_md(screen, part_dir) for screen in part_data["screens"]]
    prompt_vi_path = render_prompt_screen_vi_md(part_data, part_dir)
    voiceover_path = render_voiceover_json(part_data, part_dir)

    return {
        "script_md": script_md_path,
        "prompt_screen_paths": prompt_screen_paths,
        "prompt_vi_path": prompt_vi_path,
        "voiceover_json": voiceover_path,
    }

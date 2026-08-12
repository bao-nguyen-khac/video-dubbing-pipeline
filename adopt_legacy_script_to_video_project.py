"""
adopt_legacy_script_to_video_project.py — "nhận nuôi" 1 thư mục
`script-to-video/<slug>/` làm TAY từ trước (không có project.json/
character.json/part-N/script.json) vào hệ thống mới, bằng cách PARSE NGƯỢC
các file markdown/json đã có (character-bible.md, part-N/script.md,
part-N/prompt-screen-*.md, part-N/voiceover.json) thành đúng schema mà
`script_to_video_pipeline.py` đọc/ghi.

KHÔNG sửa/ghi đè bất kỳ file markdown/video/audio nào đã có sẵn — CHỈ thêm
mới `project.json`, `character.json`, `part-N/script.json` (và
`part-N/voiceover.json` nếu phần đó CHƯA có file này, vì đó vốn là file dẫn
xuất/derived, không phải nội dung viết tay).

Chạy 1 lần cho 1 slug:
    venv/bin/python adopt_legacy_script_to_video_project.py <slug>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from media_utils import get_media_duration
from review import gates
from review.script_to_video_review import GATE_SCRIPT_TO_VIDEO
from script_to_video_pipeline import PROJECT_ROOT_DIR, part_dir_for, project_dir_for


def _split_sections(md_text: str) -> tuple[str, list[tuple[str, str]]]:
    """Tách markdown thành (preamble, [(heading, body), ...]) theo mốc `## `."""
    parts = re.split(r"^## (.+)$", md_text, flags=re.MULTILINE)
    sections = []
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((heading, body.strip("\n")))
    return parts[0], sections


def _section_body(sections: list[tuple[str, str]], prefix: str) -> str | None:
    for heading, body in sections:
        if heading.startswith(prefix):
            return body
    return None


def _code_fence(body: str) -> str:
    m = re.search(r"```\n(.*?)\n```", body, flags=re.DOTALL)
    if not m:
        raise ValueError(f"Không tìm thấy code fence trong: {body[:200]!r}")
    return m.group(1).strip()


# ─── character-bible.md ────────────────────────────────────────────────────


def parse_character_bible(text: str) -> dict:
    preamble, sections = _split_sections(text)
    m = re.search(r'^# Character Bible: "(.+)" — (.+) \((.+)\)\s*$', preamble, flags=re.MULTILINE)
    if not m:
        raise ValueError("Không parse được tiêu đề character-bible.md")
    arc_title, character_name, role_title = m.group(1), m.group(2), m.group(3)

    arc_summary_body = _section_body(sections, "Tóm tắt Arc")
    if arc_summary_body is None:
        raise ValueError("Thiếu mục 'Tóm tắt Arc' trong character-bible.md")
    parts_summary = []
    for line_m in re.finditer(
        r'^\d+\.\s+\*\*Phần \d+ — "(?P<title>.+?)"\*\*\s+\((?P<paren>.+?)\):\s+(?P<synopsis>.+)$',
        arc_summary_body,
        flags=re.MULTILINE,
    ):
        role = line_m.group("paren").split(",")[0].strip()
        parts_summary.append(
            {
                "index": len(parts_summary),
                "title": line_m.group("title").strip(),
                "role": role,
                "synopsis": line_m.group("synopsis").strip(),
            }
        )
    if not parts_summary:
        raise ValueError("Không parse được phần tử nào trong 'Tóm tắt Arc'")

    # character_description_md: mọi mục TỪ "Nhân vật chính" (bỏ heading, giữ
    # body) ĐẾN TRƯỚC "Ingredients —" — gồm cả các mục phụ (Tàu, Tiểu hành
    # tinh, AI đội tàu...) ghép lại nguyên trạng.
    desc_blocks: list[str] = []
    started = False
    for heading, body in sections:
        if heading.startswith("Nhân vật chính"):
            started = True
            desc_blocks.append(body)
            continue
        if heading.startswith("Ingredients"):
            break
        if started:
            desc_blocks.append(f"## {heading}\n{body}")
    character_description_md = "\n\n".join(b for b in desc_blocks if b.strip()).strip()
    if not character_description_md:
        raise ValueError("Không parse được character_description_md")

    ingredients_body = _section_body(sections, "Ingredients —")
    if ingredients_body is None:
        raise ValueError("Thiếu mục 'Ingredients —' trong character-bible.md")
    ingredients = []
    for ing_m in re.finditer(
        r"\*\*\d+\.\s+(?P<label>.+?):\*\*\s*\n```\n(?P<prompt>.*?)\n```",
        ingredients_body,
        flags=re.DOTALL,
    ):
        ingredients.append({"label": ing_m.group("label").strip(), "image_prompt": ing_m.group("prompt").strip()})
    if len(ingredients) != 4:
        raise ValueError(f"Kỳ vọng đúng 4 ingredients, parse được {len(ingredients)}")

    return {
        "character_name": character_name.strip(),
        "role_title": role_title.strip(),
        "arc_title": arc_title.strip(),
        "parts_summary": parts_summary,
        "character_description_md": character_description_md,
        "ingredients": ingredients,
    }


# ─── part-N/script.md ───────────────────────────────────────────────────────

_ROW_RE = re.compile(r"^\|\s*(?P<cells>.+?)\s*\|\s*$", flags=re.MULTILINE)


def _table_rows(body: str) -> list[list[str]]:
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r"-{2,}", c) for c in cells):
            continue  # dòng phân cách header
        rows.append(cells)
    return rows


def parse_script_md(text: str, part_index: int) -> tuple[str, dict[int, tuple[int, str]], list[str]]:
    """Trả về (title, {screen_n: (duration_seconds, role_label)}, continuity_notes)."""
    preamble, sections = _split_sections(text)
    title_m = re.search(r'^# Phần \d+/\d+: "(.+)"', preamble, flags=re.MULTILINE)
    if not title_m:
        raise ValueError("Không parse được tiêu đề script.md")
    title = title_m.group(1).strip()

    continuity_body = _section_body(sections, "Continuity chain")
    if continuity_body is None:
        raise ValueError("Thiếu mục 'Continuity chain' trong script.md")
    cross_note = None
    intra_notes: list[tuple[int, str]] = []
    for row in _table_rows(continuity_body):
        if len(row) < 3 or row[0].lower() in ("từ → sang",):
            continue
        label = row[0].strip("*").strip()
        note = " — ".join(c for c in row[1:] if c)
        m = re.fullmatch(r"S(\d+) → S(\d+)", label)
        if m:
            intra_notes.append((int(m.group(1)), f"{label}: {note}"))
        else:
            cross_note = f"{label}: {note}"
    intra_notes.sort(key=lambda t: t[0])
    continuity_notes = ([cross_note] if part_index > 0 and cross_note else []) + [n for _, n in intra_notes]

    scene_body = _section_body(sections, "Bảng phân cảnh")
    if scene_body is None:
        raise ValueError("Thiếu mục 'Bảng phân cảnh' trong script.md")
    scene_info: dict[int, tuple[int, str]] = {}
    for row in _table_rows(scene_body):
        if len(row) < 4 or not row[0].isdigit():
            continue
        n = int(row[0])
        dur_m = re.search(r"(\d+)s", row[1])
        if not dur_m:
            continue
        scene_info[n] = (int(dur_m.group(1)), row[2].strip())

    return title, scene_info, continuity_notes


# ─── part-N/prompt-screen-N.md ──────────────────────────────────────────────


def parse_prompt_screen_md(text: str) -> dict:
    preamble, sections = _split_sections(text)

    headings = [h for h, _ in sections]
    vp_idx = next((i for i, h in enumerate(headings) if h.startswith("Visual Prompt")), None)
    vo_idx = next((i for i, h in enumerate(headings) if h.startswith("VO")), None)
    ing_idx = next((i for i, h in enumerate(headings) if h.startswith("Ingredients")), None)
    if vp_idx is None or vo_idx is None or ing_idx is None:
        raise ValueError("Thiếu mục Ingredients/Visual Prompt/VO trong prompt-screen-N.md")

    ingredients_used = sections[ing_idx][1].strip()

    before_blocks = [f"## {h}\n{b}" for h, b in sections[ing_idx + 1 : vp_idx]]
    after_blocks = [f"## {h}\n{b}" for h, b in sections[vp_idx + 1 : vo_idx]]
    prompt_detail_md = "\n\n".join(blk for blk in before_blocks + after_blocks if blk.strip())

    visual_prompt = _code_fence(sections[vp_idx][1])

    vo_m = re.search(r'\*"(.+?)"\*', sections[vo_idx][1], flags=re.DOTALL)
    if not vo_m:
        raise ValueError("Không parse được VO trong prompt-screen-N.md")
    vi_voiceover_text = vo_m.group(1).strip()

    return {
        "ingredients_used": ingredients_used,
        "prompt_detail_md": prompt_detail_md,
        "visual_prompt": visual_prompt,
        "vi_voiceover_text": vi_voiceover_text,
    }


# ─── Dựng part-N/script.json ────────────────────────────────────────────────


def build_part(slug: str, part_index: int, character: dict) -> dict:
    pdir = part_dir_for(slug, part_index)
    part_summary = character["parts_summary"][part_index]

    script_md_text = (pdir / "script.md").read_text(encoding="utf-8")
    title, scene_info, continuity_notes = parse_script_md(script_md_text, part_index)

    screen_files = sorted(
        (p for p in pdir.glob("prompt-screen-*.md") if re.fullmatch(r"prompt-screen-\d+", p.stem)),
        key=lambda p: int(re.search(r"\d+", p.stem).group()),
    )
    if len(screen_files) != len(scene_info):
        raise ValueError(f"part-{part_index + 1}: {len(screen_files)} file prompt-screen nhưng bảng phân cảnh có {len(scene_info)} dòng")

    screens = []
    for f in screen_files:
        n = int(re.search(r"\d+", f.stem).group())
        duration_seconds, role_label = scene_info[n]
        parsed = parse_prompt_screen_md(f.read_text(encoding="utf-8"))
        voice_path = pdir / "voice" / f"screen-{n}.wav"
        has_voice = voice_path.exists()
        screens.append(
            {
                "index": n - 1,
                "duration_seconds": duration_seconds,
                "role_label": role_label,
                "ingredients_used": parsed["ingredients_used"],
                "prompt_detail_md": parsed["prompt_detail_md"],
                "visual_prompt": parsed["visual_prompt"],
                "vi_voiceover_text": parsed["vi_voiceover_text"],
                "voice_path": str(voice_path) if has_voice else None,
                "voice_duration": get_media_duration(voice_path) if has_voice else None,
            }
        )

    video_raw_files = list((pdir / "video-raw").glob("merge.*")) if (pdir / "video-raw").exists() else []
    uploaded_video_path = str(video_raw_files[0]) if video_raw_files else None

    full_narration = pdir / "voice" / "full-narration.wav"
    voice_full_path = str(full_narration) if full_narration.exists() else None
    voice_full_duration = get_media_duration(full_narration) if full_narration.exists() else None

    output_exists = (pdir / "output.mp4").exists()
    all_screens_have_voice = all(s["voice_path"] and s["voice_duration"] is not None for s in screens)

    if output_exists:
        status = "done"
    elif uploaded_video_path and all_screens_have_voice:
        status = "merging"
    elif uploaded_video_path:
        status = "synthesizing"
    else:
        status = "awaiting_review"

    part = {
        "part_index": part_index,
        "title": title,
        "role": part_summary["role"],
        "screens": screens,
        "continuity_notes": continuity_notes,
        "uploaded_video_path": uploaded_video_path,
        "voice_full_path": voice_full_path,
        "voice_full_duration": voice_full_duration,
        "status": status,
        "error": None,
        "review_gates": {},
    }

    gates.mark_reached(part, GATE_SCRIPT_TO_VIDEO, len(screens))
    if status != "awaiting_review":
        gates.mark_approved(part, GATE_SCRIPT_TO_VIDEO)
        part["status"] = status  # mark_approved không đổi status, chỉ set review_gate=None

    if not (pdir / "voiceover.json").exists():
        from script_gen.script_to_video_renderer import render_voiceover_json

        render_voiceover_json(part, pdir)

    return part


def adopt(slug: str) -> None:
    pdir = project_dir_for(slug)
    if not pdir.exists():
        raise SystemExit(f"Không tìm thấy thư mục: {pdir}")
    if (pdir / "project.json").exists():
        raise SystemExit(f"Dự án đã có project.json rồi — không cần adopt lại: {pdir}")

    character_bible_path = pdir / "character-bible.md"
    if not character_bible_path.exists():
        raise SystemExit(f"Thiếu character-bible.md: {character_bible_path}")
    character = parse_character_bible(character_bible_path.read_text(encoding="utf-8"))

    num_parts = len(character["parts_summary"])
    part_dirs = sorted(pdir.glob("part-*"), key=lambda p: int(re.search(r"\d+", p.name).group()))
    if len(part_dirs) != num_parts:
        raise SystemExit(f"character-bible.md khai {num_parts} phần nhưng có {len(part_dirs)} thư mục part-*")

    parts = [build_part(slug, i, character) for i in range(num_parts)]
    target_screens_per_part = len(parts[0]["screens"])

    series_notes_path = PROJECT_ROOT_DIR / "pov-2100-asteroid-mining-series-rules.md"
    series_notes = (
        f"Xem quy tắc series đầy đủ tại script-to-video/{series_notes_path.name}"
        if series_notes_path.exists()
        else None
    )

    premise = (
        f"{character['character_name']} — {character['role_title']}. "
        f"Arc: \"{character['arc_title']}\". {character['character_description_md'].splitlines()[0].lstrip('* ').strip()}"
    )

    project = {
        "slug": slug,
        "premise": premise,
        "series_notes": series_notes,
        "num_parts": num_parts,
        "target_screens_per_part": target_screens_per_part,
        "tts_provider": "edge-tts",
        "voice_id": None,
        "status": "ready",
        "error": None,
        "created_at": "2026-08-11T00:00:00+00:00",
        "updated_at": "2026-08-11T00:00:00+00:00",
    }

    with open(pdir / "character.json", "w", encoding="utf-8") as f:
        json.dump(character, f, ensure_ascii=False, indent=2)
    with open(pdir / "project.json", "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)
    for i, part in enumerate(parts):
        with open(part_dir_for(slug, i) / "script.json", "w", encoding="utf-8") as f:
            json.dump(part, f, ensure_ascii=False, indent=2)

    print(f"Đã adopt '{slug}': {num_parts} phần — " + ", ".join(f"part-{i+1}={p['status']}" for i, p in enumerate(parts)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Dùng: python adopt_legacy_script_to_video_project.py <slug>")
    adopt(sys.argv[1])

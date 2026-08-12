"""
script_to_video_pipeline.py — Orchestrator RIÊNG cho tính năng "Script-to-video"
(1 dự án = 1 nhân vật/premise, chia thành nhiều PHẦN (part) — mỗi phần: LLM
sinh kịch bản + prompt AI-video-gen (Google Flow / Gemini Omni Flash) → người
dùng tự tạo clip từng screen ở ngoài rồi TỰ NỐI LẠI thành 1 file
`video-raw/merge.mp4` → upload lại → TTS + ghép thành `output.mp4`).

Mỗi dự án là 1 thư mục TỰ ĐÓNG GÓI `script-to-video/<slug>/` — KHÔNG dùng
`jobs/` và KHÔNG import từ `pipeline.py` — tách biệt hoàn toàn khỏi luồng
dub/generate. `slug` là định danh DUY NHẤT của dự án.

2 cấp trạng thái:
  - Dự án (project): pending → scripting → ready ↘ failed
    ("scripting" = sinh character bible + kịch bản TẤT CẢ các phần, tuần tự,
    mỗi phần đọc screen cuối của phần trước để nối tiếp continuity — xem
    `run_script_to_video_pipeline()`. Sau "ready", tiến trình thật sự nằm ở
    từng phần.)
  - Phần (part), độc lập với nhau: pending → awaiting_review → awaiting_upload
    → synthesizing → merging → done ↘ failed
    (xem `run_part_pipeline()`)

Thư mục dự án:
  script-to-video/<slug>/
    project.json          — premise/series_notes/num_parts/... + status sinh kịch bản
    character.json         — nhân vật/thế giới dùng chung mọi phần
    character-bible.md     — rendered từ character.json
    part-1/
      script.json           — NGUỒN SỰ THẬT của phần: screens[] + continuity_notes +
                              upload/voice/trạng thái + chốt duyệt
      script.md, prompt-screen-N.md, prompt-screen-vi.md, voiceover.json  — rendered
      video-raw/merge.mp4    — người dùng upload (1 file, đã tự nối)
      voice/screen-N.wav, voice/full-narration.wav
      output.mp4
    part-2/  ... (như trên)
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from media_utils import get_media_duration
from review import gates
from review.script_to_video_review import GATE_SCRIPT_TO_VIDEO

load_dotenv()

# ─── Constants ───────────────────────────────────────────────────────────────

PROJECT_ROOT_DIR = Path(__file__).parent / "script-to-video"

ProjectStatusLiteral = Literal["pending", "scripting", "ready", "failed"]
PartStatusLiteral = Literal[
    "pending", "awaiting_review", "awaiting_upload", "synthesizing", "merging", "done", "failed"
]

# Rerun chỉ hỗ trợ 2 bước cuối — rerun "kịch bản" của 1 phần đơn lẻ có nguy cơ
# phá continuity với các phần khác đã sinh/duyệt dựa trên bản cũ (screen cuối
# của phần N làm điểm nối cho phần N+1) nên KHÔNG hỗ trợ ở v1.
PART_RERUN_STEPS: list[str] = ["synthesizing", "merging"]

# Trạng thái KHÔNG tính là "đang chạy" cho concurrency gate.
_PROJECT_NOT_RUNNING = ("ready", "failed")
_PART_NOT_RUNNING = ("awaiting_review", "awaiting_upload", "done", "failed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Slug / thư mục dự án & phần ──────────────────────────────────────────────


def _slugify(text: str) -> str:
    """Chuyển văn bản (tiếng Việt có dấu) thành slug ascii-hyphen để đặt tên
    thư mục — bỏ dấu, chỉ giữ chữ/số, ghép bằng dấu gạch ngang."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "video"


def _unique_project_dir(slug: str) -> Path:
    """Thư mục `script-to-video/<slug>/`, thêm hậu tố số nếu đã tồn tại (dự án
    khác trùng slug do premise giống/gần giống nhau)."""
    candidate = PROJECT_ROOT_DIR / slug
    n = 2
    while candidate.exists():
        candidate = PROJECT_ROOT_DIR / f"{slug}-{n}"
        n += 1
    return candidate


def project_dir_for(slug: str) -> Path:
    return PROJECT_ROOT_DIR / slug


def part_dir_for(slug: str, part_index: int) -> Path:
    return project_dir_for(slug) / f"part-{part_index + 1}"


def _project_json_path(slug: str) -> Path:
    return project_dir_for(slug) / "project.json"


def _part_json_path(slug: str, part_index: int) -> Path:
    return part_dir_for(slug, part_index) / "script.json"


# ─── Đọc/ghi project.json / character.json / part script.json ────────────────


def read_project(slug: str) -> dict:
    path = _project_json_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"Dự án không tồn tại: {slug}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_project(slug: str, project: dict) -> None:
    project["updated_at"] = _now_iso()
    with open(_project_json_path(slug), "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)


def read_character(slug: str) -> dict:
    path = project_dir_for(slug) / "character.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_part(slug: str, part_index: int) -> dict:
    path = _part_json_path(slug, part_index)
    if not path.exists():
        raise FileNotFoundError(f"Phần không tồn tại: {slug}/part-{part_index + 1}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_part(slug: str, part_index: int, part: dict) -> None:
    with open(_part_json_path(slug, part_index), "w", encoding="utf-8") as f:
        json.dump(part, f, ensure_ascii=False, indent=2)


def _iter_script_to_video_projects():
    """Yield (slug, project_dict) cho mỗi thư mục con của PROJECT_ROOT_DIR có
    project.json — thư mục làm tay cũ (không có project.json) bị bỏ qua có
    chủ đích, KHÔNG được "đoán" tiến trình từ nội dung markdown."""
    if not PROJECT_ROOT_DIR.exists():
        return
    for entry in sorted(PROJECT_ROOT_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "project.json").exists():
            continue
        try:
            yield entry.name, read_project(entry.name)
        except (FileNotFoundError, OSError, ValueError):
            continue


def find_running_script_to_video_slug() -> str | None:
    """Trả về slug của dự án script-to-video đang xử lý (dự án đang
    "scripting", HOẶC có ít nhất 1 phần đang synthesizing/merging), hoặc
    None — concurrency gate RIÊNG cho luồng này, tách biệt hoàn toàn khỏi
    `jobs_api.find_running_job_id()` (dub/generate)."""
    for slug, project in _iter_script_to_video_projects():
        if project.get("status") not in _PROJECT_NOT_RUNNING:
            return slug
        for part_index in range(project.get("num_parts", 0)):
            if not _part_json_path(slug, part_index).exists():
                continue
            try:
                part = read_part(slug, part_index)
            except (FileNotFoundError, OSError, ValueError):
                continue
            if part.get("status") not in _PART_NOT_RUNNING:
                return slug
    return None


# ─── Quản lý dự án ─────────────────────────────────────────────────────────────


def create_script_to_video_project(
    premise: str,
    num_parts: int = 2,
    target_screens_per_part: int = 10,
    series_notes: str | None = None,
    slug: str | None = None,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
) -> dict:
    """Tạo dự án script-to-video mới, ghi `script-to-video/<slug>/project.json`.

    `slug` truyền vào (nếu có) dùng NGUYÊN VẸN làm tên thư mục — chỉ dùng cho
    test/tái tạo có kiểm soát; luồng bình thường luôn để trống để tự sinh từ
    `premise` + `_unique_project_dir()`.

    Raises:
        ValueError: `premise.strip()` rỗng, hoặc `num_parts`/
            `target_screens_per_part` không dương.
    """
    if not premise.strip():
        raise ValueError("Ý tưởng nhân vật/bối cảnh không được để trống")
    if num_parts <= 0:
        raise ValueError("Số phần (num_parts) phải là số dương")
    if target_screens_per_part <= 0:
        raise ValueError("Số screen/phần phải là số dương")

    project_dir = project_dir_for(slug) if slug else _unique_project_dir(_slugify(premise))
    project_dir.mkdir(parents=True, exist_ok=False)

    project = {
        "slug": project_dir.name,
        "premise": premise,
        "series_notes": series_notes,
        "num_parts": num_parts,
        "target_screens_per_part": target_screens_per_part,
        "tts_provider": tts_provider,
        "voice_id": voice_id,
        "status": "pending",
        "error": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    _write_project(project_dir.name, project)
    return project


def _fail_script_to_video_project(slug: str, step: str, exc: Exception) -> None:
    try:
        project = read_project(slug)
        project["status"] = "failed"
        project["error"] = f"[{step}] {type(exc).__name__}: {exc}"
        _write_project(slug, project)
    except Exception:
        pass  # Không để lỗi lan rộng khi handling error


def _fail_part(slug: str, part_index: int, step: str, exc: Exception) -> None:
    try:
        part = read_part(slug, part_index)
        part["status"] = "failed"
        part["error"] = f"[{step}] {type(exc).__name__}: {exc}"
        _write_part(slug, part_index, part)
    except Exception:
        pass


def part_status_from_artifacts(part: dict, part_dir: Path) -> PartStatusLiteral:
    """Suy ra trạng thái cần resume tới dựa trên file đã có, dùng khi resume
    1 phần đã "failed" (chỉ xảy ra sau khi đã qua awaiting_upload — hai
    trạng thái awaiting_review/awaiting_upload không tự fail)."""
    if not part.get("uploaded_video_path"):
        return "awaiting_upload"
    screens = part["screens"]
    if not all(s.get("voice_path") and s.get("voice_duration") is not None for s in screens):
        return "synthesizing"
    if not (part_dir / "output.mp4").exists():
        return "merging"
    return "done"


# ─── Chạy lại 1 phần từ synthesizing/merging ──────────────────────────────────


def rerun_part_from_step(slug: str, part_index: int, target_step: str) -> dict:
    """
    Đặt 1 phần quay lại "synthesizing" hoặc "merging" để chạy lại — xoá sạch
    artifact của bước đó và bước sau, rồi đặt status = target_step. Clip đã
    upload (`uploaded_video_path`) KHÔNG bị xoá.

    Hành động PHÁ HUỶ — chỗ gọi PHẢI xác nhận với người dùng trước.

    Raises:
        ValueError: `target_step` không phải một bước hợp lệ.
    """
    if target_step not in PART_RERUN_STEPS:
        raise ValueError(f"Bước không hợp lệ: {target_step}. Chỉ chạy lại được từ: {PART_RERUN_STEPS}")

    part = read_part(slug, part_index)
    pdir = part_dir_for(slug, part_index)
    voice_dir = pdir / "voice"

    (pdir / "output.mp4").unlink(missing_ok=True)

    if target_step == "synthesizing":
        for screen in part["screens"]:
            screen["voice_path"] = None
            screen["voice_duration"] = None
        if voice_dir.exists():
            shutil.rmtree(voice_dir)
    elif target_step == "merging":
        (voice_dir / "full-narration.wav").unlink(missing_ok=True)

    part["voice_full_path"] = None
    part["voice_full_duration"] = None
    part["error"] = None
    part["status"] = target_step
    _write_part(slug, part_index, part)
    return part


# ─── Pipeline Orchestrator — cấp dự án (sinh character bible + kịch bản) ──────


def run_script_to_video_pipeline(slug: str) -> None:
    """
    Sinh character bible (1 lần) rồi sinh kịch bản TUẦN TỰ từng phần — phần
    sau đọc screen cuối của phần trước (đã ghi trên đĩa) để nối continuity.
    Resume-safe: bỏ qua phần đã có `script.json`. Dừng lại ở "ready" — KHÔNG
    tự chạy tiếp synthesizing/merging của phần nào (mỗi phần chờ người dùng
    duyệt + upload riêng, xem `run_part_pipeline()`).
    """
    project = read_project(slug)
    pdir = project_dir_for(slug)
    premise = project["premise"]

    if project["status"] == "failed":
        print(f"[script_to_video_pipeline][{slug}] Resume sau lỗi, tiếp tục sinh kịch bản...")
        project["status"] = "scripting"
        project["error"] = None
        _write_project(slug, project)
        project = read_project(slug)

    if project["status"] not in ("pending", "scripting"):
        return

    try:
        project["status"] = "scripting"
        _write_project(slug, project)

        character_path = pdir / "character.json"
        if not character_path.exists():
            print(f"[script_to_video_pipeline][{slug}] Sinh character bible (premise={premise!r})...")
            from script_gen.character_bible_generator import write_character_bible_to_disk
            from script_gen.script_to_video_renderer import render_character_bible_md

            write_character_bible_to_disk(
                premise, project["num_parts"], project["target_screens_per_part"], pdir,
                series_notes=project.get("series_notes"),
            )
            character = read_character(slug)
            render_character_bible_md(character, pdir)
            print(f"[script_to_video_pipeline][{slug}] Character bible xong: {character['character_name']}")
        character = read_character(slug)

        from script_gen.screen_script_generator import write_part_script_to_disk
        from script_gen.script_to_video_renderer import render_all_part

        for part_index in range(project["num_parts"]):
            part_dir = part_dir_for(slug, part_index)
            script_path = part_dir / "script.json"
            if script_path.exists():
                continue  # resume: phần này đã sinh xong

            previous_last_screen = None
            if part_index > 0:
                previous_last_screen = read_part(slug, part_index - 1)["screens"][-1]

            print(f"[script_to_video_pipeline][{slug}] Sinh kịch bản phần {part_index + 1}...")
            part_dir.mkdir(parents=True, exist_ok=True)
            (part_dir / "video-raw").mkdir(parents=True, exist_ok=True)
            write_part_script_to_disk(
                character, part_index, project["target_screens_per_part"], part_dir, previous_last_screen
            )
            part_data = read_part(slug, part_index)
            render_all_part(part_data, part_dir, project["num_parts"])

            gates.mark_reached(part_data, GATE_SCRIPT_TO_VIDEO, len(part_data["screens"]))
            part_data["status"] = "awaiting_review"
            part_data["error"] = None
            _write_part(slug, part_index, part_data)
            print(f"[script_to_video_pipeline][{slug}] Phần {part_index + 1} chờ duyệt.")

        project = read_project(slug)
        project["status"] = "ready"
        _write_project(slug, project)
        print(f"[script_to_video_pipeline][{slug}] Sinh kịch bản xong, {project['num_parts']} phần chờ duyệt.")
    except Exception as e:
        _fail_script_to_video_project(slug, "scripting", e)
        print(f"[ERROR][{slug}] Sinh kịch bản thất bại: {e}")


# ─── Pipeline Orchestrator — cấp phần (upload → synthesizing → merging) ───────


def run_part_pipeline(slug: str, part_index: int) -> None:
    """
    Điều phối 1 phần từ sau khi upload merge.mp4: synthesizing (TTS mỗi
    screen) → merging (nối voice + ghép vào merge.mp4) → done/failed.
    Resume-safe theo từng screen.
    """
    project = read_project(slug)
    part = read_part(slug, part_index)
    pdir = part_dir_for(slug, part_index)

    if part["status"] == "failed":
        resumed_status = part_status_from_artifacts(part, pdir)
        print(f"[script_to_video_pipeline][{slug}/part-{part_index + 1}] Resume sau lỗi, tiếp tục từ: {resumed_status}")
        part["status"] = resumed_status
        part["error"] = None
        _write_part(slug, part_index, part)
        part = read_part(slug, part_index)

    if part["status"] == "awaiting_upload":
        print(f"[script_to_video_pipeline][{slug}/part-{part_index + 1}] Đang chờ upload merge.mp4.")
        return

    if part["status"] == "synthesizing":
        print(f"[script_to_video_pipeline][{slug}/part-{part_index + 1}] Bắt đầu synthesizing...")
        try:
            from tts.scene_synthesizer import synthesize_scene

            tts_provider = project.get("tts_provider", "edge-tts")
            voice_id = project.get("voice_id")
            for screen in part["screens"]:
                if screen.get("voice_path") and screen.get("voice_duration") is not None:
                    continue  # resume: screen này đã tổng hợp giọng rồi
                voice_path = pdir / "voice" / f"screen-{screen['index'] + 1}.wav"
                duration = synthesize_scene(screen["vi_voiceover_text"], voice_path, tts_provider, voice_id)
                screen["voice_path"] = str(voice_path)
                screen["voice_duration"] = duration
                _write_part(slug, part_index, part)

            part = read_part(slug, part_index)
            part["status"] = "merging"
            _write_part(slug, part_index, part)
            print(f"[script_to_video_pipeline][{slug}/part-{part_index + 1}] synthesizing xong")
        except Exception as e:
            _fail_part(slug, part_index, "synthesizing", e)
            print(f"[ERROR][{slug}/part-{part_index + 1}] synthesizing thất bại: {e}")
            return

    part = read_part(slug, part_index)
    if part["status"] == "merging":
        print(f"[script_to_video_pipeline][{slug}/part-{part_index + 1}] Bắt đầu merging...")
        try:
            from merge.script_to_video_merge import concat_wavs, mux_part_video

            wav_paths = [Path(s["voice_path"]) for s in sorted(part["screens"], key=lambda s: s["index"])]
            full_narration_path = pdir / "voice" / "full-narration.wav"
            concat_wavs(wav_paths, full_narration_path)
            full_narration_duration = get_media_duration(full_narration_path)

            mux_part_video(part["uploaded_video_path"], full_narration_path, pdir / "output.mp4")

            part = read_part(slug, part_index)
            part["voice_full_path"] = str(full_narration_path)
            part["voice_full_duration"] = full_narration_duration
            part["status"] = "done"
            _write_part(slug, part_index, part)
            print(f"[script_to_video_pipeline][{slug}/part-{part_index + 1}] Hoàn tất: {pdir / 'output.mp4'}")
        except Exception as e:
            _fail_part(slug, part_index, "merging", e)
            print(f"[ERROR][{slug}/part-{part_index + 1}] merging thất bại: {e}")
            return

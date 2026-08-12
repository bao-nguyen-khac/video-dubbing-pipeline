"""
web/backend/script_to_video_jobs_api.py — Endpoint quản lý dự án "Script-to-video"
(1 dự án = 1 nhân vật/premise, chia nhiều PHẦN (part); mỗi phần: LLM sinh
kịch bản Google Flow/Omni Flash → người dùng upload 1 clip đã tự nối
(`merge.mp4`) → TTS + ghép). Router RIÊNG (prefix /api/script-to-video-jobs),
KHÔNG đụng jobs_api.py/generate_jobs_api.py — tách biệt hoàn toàn khỏi
`jobs/`, kể cả hàng đợi "1 dự án tại 1 thời điểm" (xem
`script_to_video_pipeline.find_running_script_to_video_slug()`).

Endpoint review (`GET/PUT/POST .../parts/{i}/review*`) nằm NGAY TRÊN ROUTER
NÀY, KHÔNG tái dùng `/api/jobs/{id}/review` (web/backend/review_api.py) —
payload ở đây có 6 trường sửa được / screen, khác hẳn schema
`SaveReviewSegment{index,text}` review_api.py đang dùng cho dub/generate
(xem review/script_to_video_review.py).
"""

from __future__ import annotations

import mimetypes
import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from review import gates
from review.script_to_video_review import GATE_SCRIPT_TO_VIDEO
from review.script_to_video_review import build_payload as build_review_payload
from review.script_to_video_review import save_edits as save_review_edits
from script_to_video_pipeline import (
    PART_RERUN_STEPS,
    _iter_script_to_video_projects,
    _part_json_path,
    _write_part,
    _write_project,
    create_script_to_video_project,
    find_running_script_to_video_slug,
    part_dir_for,
    part_status_from_artifacts,
    project_dir_for,
    read_character,
    read_part,
    read_project,
    rerun_part_from_step,
    run_part_pipeline,
    run_script_to_video_pipeline,
)
from web.backend.jobs_api import _error

router = APIRouter()

_VALID_TTS_PROVIDERS = ("edge-tts", "lucyai", "omnivoice")
_VALID_VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv")


def start_script_to_video_job(slug: str) -> None:
    """Spawn daemon thread chạy `run_script_to_video_pipeline()` (sinh
    character bible + kịch bản mọi phần) nền — không block request HTTP."""

    def _run_and_swallow_errors() -> None:
        try:
            run_script_to_video_pipeline(slug)
        except Exception as e:  # noqa: BLE001 — project.json đã tự ghi "failed" ở lỗi nghiệp vụ
            print(f"[script_to_video_jobs_api] Lỗi không mong đợi khi sinh kịch bản nền {slug}: {e}")

    threading.Thread(target=_run_and_swallow_errors, daemon=True).start()


def start_part_pipeline(slug: str, part_index: int) -> None:
    """Spawn daemon thread chạy `run_part_pipeline()` (synthesizing→merging)
    nền cho 1 phần."""

    def _run_and_swallow_errors() -> None:
        try:
            run_part_pipeline(slug, part_index)
        except Exception as e:  # noqa: BLE001
            print(
                f"[script_to_video_jobs_api] Lỗi không mong đợi khi chạy phần nền "
                f"{slug}/part-{part_index + 1}: {e}"
            )

    threading.Thread(target=_run_and_swallow_errors, daemon=True).start()


# % ước lượng theo trạng thái 1 phần — dùng cho cả progress của phần lẫn
# progress trung bình của cả dự án.
_PART_STATUS_PROGRESS: dict[str, int] = {
    "pending": 0,
    "awaiting_review": 20,
    "awaiting_upload": 35,
    "synthesizing": 60,
    "merging": 80,
    "done": 100,
}


def _part_progress(part: dict, part_dir: Path) -> int:
    status = part.get("status", "pending")
    if status == "failed":
        status = part_status_from_artifacts(part, part_dir)
    return _PART_STATUS_PROGRESS.get(status, 0)


def _part_to_summary(part: dict, slug: str, part_index: int) -> dict:
    pdir = part_dir_for(slug, part_index)
    status = part.get("status", "pending")
    return {
        "index": part_index,
        "title": part.get("title"),
        "role": part.get("role"),
        "screen_count": len(part.get("screens", [])),
        "status": status,
        "progress_percent": _part_progress(part, pdir),
        "error": part.get("error"),
        "review_url": (
            f"/api/script-to-video-jobs/{slug}/parts/{part_index}/review" if status == "awaiting_review" else None
        ),
        "output_video_url": (
            f"/api/script-to-video-jobs/{slug}/parts/{part_index}/output" if (pdir / "output.mp4").exists() else None
        ),
        "can_retry": status == "failed",
    }


def _project_to_summary(project: dict) -> dict:
    slug = project["slug"]
    num_parts = project.get("num_parts", 0)
    project_status = project.get("status", "pending")

    parts_done = 0
    review_gate = None

    if project_status in ("pending", "scripting"):
        generated = sum(1 for i in range(num_parts) if _part_json_path(slug, i).exists())
        status = project_status
        progress_percent = round(10 + 30 * (generated / num_parts)) if num_parts else 10
    elif project_status == "failed":
        status = "failed"
        progress_percent = 5
    else:  # "ready" — trạng thái thật nằm ở từng phần
        parts = [
            read_part(slug, i) for i in range(num_parts) if _part_json_path(slug, i).exists()
        ]
        statuses = [p.get("status", "pending") for p in parts]
        if "failed" in statuses:
            status = "failed"
        elif "synthesizing" in statuses:
            status = "synthesizing"
        elif "merging" in statuses:
            status = "merging"
        elif "awaiting_review" in statuses:
            status = "awaiting_review"
            review_gate = GATE_SCRIPT_TO_VIDEO
        elif "awaiting_upload" in statuses:
            status = "awaiting_upload"
        elif statuses and all(s == "done" for s in statuses):
            status = "done"
        else:
            status = "ready"
        percents = [_part_progress(p, part_dir_for(slug, p["part_index"])) for p in parts]
        progress_percent = round(sum(percents) / len(percents)) if percents else 0
        parts_done = sum(1 for s in statuses if s == "done")

    return {
        "slug": slug,
        "job_type": "script_to_video",
        "premise": project["premise"],
        "status": status,
        "progress_percent": progress_percent,
        "parts_done": parts_done,
        "parts_total": num_parts,
        "created_at": project["created_at"],
        "review_gate": review_gate,
    }


def _project_to_detail(project: dict) -> dict:
    slug = project["slug"]
    detail = _project_to_summary(project)
    pdir = project_dir_for(slug)

    character = None
    if (pdir / "character.json").exists():
        try:
            character = read_character(slug)
        except (OSError, ValueError):
            character = None

    parts = []
    for i in range(project.get("num_parts", 0)):
        if _part_json_path(slug, i).exists():
            parts.append(_part_to_summary(read_part(slug, i), slug, i))
        else:
            parts.append(
                {
                    "index": i, "title": None, "role": None, "screen_count": 0,
                    "status": "pending", "progress_percent": 0, "error": None,
                    "review_url": None, "output_video_url": None, "can_retry": False,
                }
            )

    detail.update(
        {
            "series_notes": project.get("series_notes"),
            "tts_provider": project.get("tts_provider", "edge-tts"),
            "voice_id": project.get("voice_id"),
            "target_screens_per_part": project.get("target_screens_per_part"),
            "error": project.get("error"),
            "character": character,
            "parts": parts,
            "can_retry": project["status"] == "failed",
        }
    )
    return detail


class SubmitScriptToVideoJobRequest(BaseModel):
    premise: str
    num_parts: int = 2
    target_screens_per_part: int = 10
    series_notes: str | None = None
    tts_provider: str = "edge-tts"
    voice_id: str | None = None


@router.post("", status_code=201)
async def submit_script_to_video_job(body: SubmitScriptToVideoJobRequest):
    """POST /api/script-to-video-jobs — tạo dự án mới."""
    if not body.premise.strip():
        return _error(400, "Ý tưởng nhân vật/bối cảnh không được để trống")
    if body.tts_provider not in _VALID_TTS_PROVIDERS:
        return _error(400, "tts_provider phải là 'edge-tts', 'lucyai' hoặc 'omnivoice'")

    running_slug = find_running_script_to_video_slug()
    if running_slug:
        return _error(409, "Đang có dự án script-to-video xử lý, vui lòng chờ", running_job_id=running_slug)

    try:
        project = create_script_to_video_project(
            body.premise,
            num_parts=body.num_parts,
            target_screens_per_part=body.target_screens_per_part,
            series_notes=body.series_notes,
            tts_provider=body.tts_provider,
            voice_id=body.voice_id,
        )
    except ValueError as e:
        return _error(400, str(e))

    start_script_to_video_job(project["slug"])
    return {"slug": project["slug"]}


@router.post("/{slug}/retry", status_code=202)
async def retry_script_to_video_job(slug: str):
    """POST /api/script-to-video-jobs/{slug}/retry — resume sinh kịch bản dự
    án đã failed (character bible/kịch bản 1 phần nào đó lỗi)."""
    try:
        project = read_project(slug)
    except FileNotFoundError:
        return _error(404, "Dự án không tồn tại")
    if project["status"] != "failed":
        return _error(409, f"Dự án đang ở trạng thái '{project['status']}', chỉ retry được dự án 'failed'")

    running_slug = find_running_script_to_video_slug()
    if running_slug:
        return _error(409, "Đang có dự án khác xử lý, vui lòng chờ", running_job_id=running_slug)

    start_script_to_video_job(slug)
    return {"slug": slug}


@router.get("")
async def list_script_to_video_jobs():
    projects = [_project_to_summary(project) for _, project in _iter_script_to_video_projects()]
    projects.sort(key=lambda j: j["created_at"], reverse=True)
    return {"jobs": projects}


@router.get("/{slug}")
async def get_script_to_video_job(slug: str):
    try:
        project = read_project(slug)
    except FileNotFoundError:
        return _error(404, "Dự án không tồn tại")
    return _project_to_detail(project)


@router.get("/{slug}/deliverables/{filename}")
async def get_project_deliverable(slug: str, filename: str):
    """GET /api/script-to-video-jobs/{slug}/deliverables/{filename} — nội
    dung character-bible.md (cấp dự án, dùng chung mọi phần)."""
    try:
        read_project(slug)
    except FileNotFoundError:
        return _error(404, "Dự án không tồn tại")

    if filename != "character-bible.md":
        return _error(404, "File không tồn tại")

    path = project_dir_for(slug) / filename
    if not path.exists():
        return _error(404, "File không tồn tại")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


# ─── Endpoint theo phần (part) ──────────────────────────────────────────────


def _get_project_and_part(slug: str, part_index: int) -> tuple[dict, dict, None] | tuple[None, None, tuple]:
    try:
        project = read_project(slug)
    except FileNotFoundError:
        return None, None, (404, "Dự án không tồn tại")
    try:
        part = read_part(slug, part_index)
    except FileNotFoundError:
        return None, None, (404, "Phần không tồn tại")
    return project, part, None


@router.get("/{slug}/parts/{part_index}/output")
async def get_part_output(slug: str, part_index: int):
    _project, part, err = _get_project_and_part(slug, part_index)
    if err:
        return _error(*err)

    output_path = part_dir_for(slug, part_index) / "output.mp4"
    if not output_path.exists():
        return _error(404, "Phần chưa có video output")
    return FileResponse(output_path, media_type="video/mp4", filename=f"{slug}-part-{part_index + 1}.mp4")


@router.get("/{slug}/parts/{part_index}/deliverables/{filename}")
async def get_part_deliverable(slug: str, part_index: int, filename: str):
    """GET .../parts/{part_index}/deliverables/{filename} — script.md/
    prompt-screen-N.md/prompt-screen-vi.md/voiceover.json của 1 phần, dạng
    text/plain. `filename` chỉ chấp nhận nếu khớp mẫu tên file cố định —
    chặn path traversal."""
    _project, part, err = _get_project_and_part(slug, part_index)
    if err:
        return _error(*err)

    screen_count = len(part.get("screens", []))
    allowed_names = {"script.md", "prompt-screen-vi.md", "voiceover.json"} | {
        f"prompt-screen-{n}.md" for n in range(1, screen_count + 1)
    }
    if filename not in allowed_names:
        return _error(404, "File không tồn tại")

    path = part_dir_for(slug, part_index) / filename
    if not path.exists():
        return _error(404, "File không tồn tại")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.post("/{slug}/parts/{part_index}/retry", status_code=202)
async def retry_part(slug: str, part_index: int):
    _project, part, err = _get_project_and_part(slug, part_index)
    if err:
        return _error(*err)
    if part["status"] != "failed":
        return _error(409, f"Phần đang ở trạng thái '{part['status']}', chỉ retry được phần 'failed'")

    running_slug = find_running_script_to_video_slug()
    if running_slug and running_slug != slug:
        return _error(409, "Đang có dự án khác xử lý, vui lòng chờ", running_job_id=running_slug)

    start_part_pipeline(slug, part_index)
    return {"slug": slug, "part_index": part_index}


_PART_RERUN_ALLOWED_STATUSES = ("done", "failed")


class RerunPartFromStepRequest(BaseModel):
    step: str
    tts_provider: str | None = None
    voice_id: str | None = None


@router.post("/{slug}/parts/{part_index}/rerun-from", status_code=202)
async def rerun_part_from_step_endpoint(slug: str, part_index: int, body: RerunPartFromStepRequest):
    """POST .../rerun-from — quay lại "synthesizing"/"merging". Hành động
    PHÁ HUỶ — frontend PHẢI xác nhận trước."""
    if body.step not in PART_RERUN_STEPS:
        return _error(400, f"Bước không hợp lệ: {body.step}. Chỉ chạy lại được từ: {PART_RERUN_STEPS}")
    if body.tts_provider is not None and body.tts_provider not in _VALID_TTS_PROVIDERS:
        return _error(400, "tts_provider phải là 'edge-tts', 'lucyai' hoặc 'omnivoice'")

    project, part, err = _get_project_and_part(slug, part_index)
    if err:
        return _error(*err)
    if part["status"] not in _PART_RERUN_ALLOWED_STATUSES:
        return _error(409, f"Phần đang xử lý (trạng thái: {part['status']}), không chạy lại được lúc này")

    running_slug = find_running_script_to_video_slug()
    if running_slug and running_slug != slug:
        return _error(409, "Đang có dự án khác xử lý, vui lòng chờ", running_job_id=running_slug)

    if body.tts_provider is not None or body.voice_id is not None:
        if body.tts_provider is not None:
            project["tts_provider"] = body.tts_provider
        if body.voice_id is not None:
            project["voice_id"] = body.voice_id
        _write_project(slug, project)

    rerun_part_from_step(slug, part_index, body.step)
    start_part_pipeline(slug, part_index)
    return {"slug": slug, "part_index": part_index, "resumed_status": body.step}


# ─── Chốt duyệt script/prompt (theo phần) ───────────────────────────────────

_APPROVE_LOCK = threading.Lock()


def _load_awaiting_review(slug: str, part_index: int) -> tuple[dict, None] | tuple[None, tuple]:
    try:
        part = read_part(slug, part_index)
    except FileNotFoundError:
        return None, (404, "Phần không tồn tại")
    if part.get("status") != "awaiting_review":
        return None, (409, f"Phần không đang chờ duyệt (trạng thái: {part.get('status')})")
    return part, None


@router.get("/{slug}/parts/{part_index}/review")
async def get_part_review(slug: str, part_index: int):
    part, err = _load_awaiting_review(slug, part_index)
    if err:
        return _error(*err)
    try:
        return build_review_payload(part, part_dir_for(slug, part_index))
    except (gates.GateError, OSError, ValueError) as e:
        return _error(500, f"Không đọc được nội dung chốt: {e}")


class PartScreenEdit(BaseModel):
    index: int
    role_label: str | None = None
    ingredients_used: str | None = None
    prompt_detail_md: str | None = None
    visual_prompt: str | None = None
    vi_voiceover_text: str | None = None
    duration_seconds: int | None = None


class SavePartReviewRequest(BaseModel):
    screens: list[PartScreenEdit]


@router.put("/{slug}/parts/{part_index}/review")
async def save_part_review(slug: str, part_index: int, body: SavePartReviewRequest):
    part, err = _load_awaiting_review(slug, part_index)
    if err:
        return _error(*err)

    pdir = part_dir_for(slug, part_index)
    edits = [s.model_dump(exclude_none=True) for s in body.screens]
    try:
        saved_count = save_review_edits(pdir, edits)
    except gates.UnknownSegmentError as e:
        return _error(400, str(e))
    except gates.GateError as e:
        return _error(400, str(e))

    # `part` (đọc TRƯỚC save_review_edits) và script.json giờ là CÙNG 1 file —
    # phải đọc lại bản đã ghi rồi mới bump gate metadata, nếu không việc ghi
    # `part` cũ (chưa có edits) đè mất bản edits vừa lưu.
    updated_part = read_part(slug, part_index)
    gates.mark_edited(updated_part, GATE_SCRIPT_TO_VIDEO, len(updated_part.get("screens", [])))
    _write_part(slug, part_index, updated_part)

    # Nội dung vừa sửa cần render lại markdown/voiceover.json deliverable để
    # khớp bản đã lưu.
    from script_gen.script_to_video_renderer import render_all_part

    project = read_project(slug)
    updated_part = read_part(slug, part_index)
    render_all_part(updated_part, pdir, project.get("num_parts", 1))

    return {"slug": slug, "part_index": part_index, "saved_count": saved_count}


@router.post("/{slug}/parts/{part_index}/review/approve", status_code=202)
async def approve_part_review(slug: str, part_index: int):
    with _APPROVE_LOCK:
        part, err = _load_awaiting_review(slug, part_index)
        if err:
            return _error(*err)

        gates.mark_approved(part, GATE_SCRIPT_TO_VIDEO)
        part["status"] = "awaiting_upload"
        _write_part(slug, part_index, part)

    return {
        "slug": slug, "part_index": part_index,
        "approved_gate": GATE_SCRIPT_TO_VIDEO, "resumed_status": "awaiting_upload",
    }


# ─── Upload clip đã tự nối (merge.mp4) ──────────────────────────────────────


@router.post("/{slug}/parts/{part_index}/upload")
async def upload_part_video(slug: str, part_index: int, file: UploadFile = File(...)):
    """POST .../parts/{part_index}/upload — nhận 1 file video đã tự nối các
    clip Google Flow của phần này (`video-raw/merge.mp4`).

    Cho phép upload LẠI (thay video) ở BẤT KỲ trạng thái nào SAU khi đã qua
    chốt duyệt (synthesizing/merging/done/failed) — không chỉ lần đầu — để
    sửa nhầm file mà không phải chạy lại cả kịch bản. Nếu giọng đọc từng
    screen đã tổng hợp xong (không phụ thuộc video), nhảy thẳng tới
    "merging" thay vì tổng hợp lại giọng vô ích."""
    _project, part, err = _get_project_and_part(slug, part_index)
    if err:
        return _error(*err)
    if part.get("status") not in ("awaiting_upload", "synthesizing", "merging", "done", "failed"):
        return _error(409, f"Phần không ở trạng thái nhận video (trạng thái: {part.get('status')})")

    ext = Path(file.filename or "").suffix.lower()
    content_type = file.content_type or ""
    if not content_type.startswith("video/") and ext not in _VALID_VIDEO_EXTENSIONS:
        return _error(400, "File phải là video (mp4/mov/webm/mkv)")
    if not ext:
        ext = mimetypes.guess_extension(content_type) or ".mp4"

    pdir = part_dir_for(slug, part_index)
    video_raw_dir = pdir / "video-raw"
    video_raw_dir.mkdir(parents=True, exist_ok=True)
    for old in video_raw_dir.glob("merge.*"):
        old.unlink()
    dest_path = video_raw_dir / f"merge{ext}"
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    (pdir / "output.mp4").unlink(missing_ok=True)  # video cũ (nếu có) không còn hợp lệ

    screens_have_voice = part["screens"] and all(
        s.get("voice_path") and s.get("voice_duration") is not None for s in part["screens"]
    )
    part["uploaded_video_path"] = str(dest_path)
    part["error"] = None
    part["status"] = "merging" if screens_have_voice else "synthesizing"
    _write_part(slug, part_index, part)
    start_part_pipeline(slug, part_index)

    return {
        "slug": slug, "part_index": part_index,
        "uploaded_video_path": str(dest_path), "status": part["status"],
    }

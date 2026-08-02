"""
web/backend/generate_jobs_api.py — Endpoint quản lý job "generate" (tính năng
"Tạo video từ chủ đề", 010-topic-video-generation). Router RIÊNG song song
jobs_api.py (prefix /api/generate-jobs) — KHÔNG sửa jobs_api.py, payload/state
machine khác hẳn luồng dub (contracts/api.md, data-model.md §5).

Chốt duyệt outline TÁI DÙNG nguyên route `/api/jobs/{id}/review` hiện có
(web/backend/review_api.py) — không có route review riêng ở đây.
"""

from __future__ import annotations

import json
import threading

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from generate_pipeline import (
    GENERATE_RERUN_STEPS,
    JOBS_DIR,
    create_generate_job,
    generate_status_from_artifacts,
    rerun_generate_from_step,
    run_generate_pipeline,
    write_job,
)
from pipeline import read_job
from web.backend.jobs_api import _error, find_running_job_id

router = APIRouter()


_VALID_TTS_PROVIDERS = ("edge-tts", "lucyai", "omnivoice")


def start_generate_job(job_id: str) -> None:
    """
    Spawn daemon thread chạy `run_generate_pipeline()` nền — không block
    request HTTP, theo đúng mẫu `web/backend/job_runner.py::start_job()`.
    Không trả về gì — tiến trình job theo dõi qua `jobs/{job_id}/job.json`.
    """

    def _run_and_swallow_errors() -> None:
        try:
            run_generate_pipeline(job_id)
        except Exception as e:  # noqa: BLE001 — job.json đã tự ghi "failed" ở lỗi nghiệp vụ
            print(f"[generate_jobs_api] Lỗi không mong đợi khi chạy job nền {job_id}: {e}")

    threading.Thread(target=_run_and_swallow_errors, daemon=True).start()

# % ước lượng theo bước generate pipeline hiện tại (đồng bộ tinh thần với
# jobs_api._STATUS_PROGRESS_MAP của luồng dub, nhưng thứ tự bước khác hẳn).
_STATUS_PROGRESS_MAP: dict[str, int] = {
    "pending": 0,
    "outlining": 15,
    "scripting": 30,
    "sourcing_assets": 55,
    "synthesizing": 75,
    "rendering": 90,
    "done": 100,
}

# Job chờ duyệt nằm giữa scripting (30) và sourcing_assets (55).
_REVIEW_GATE_PROGRESS: dict[str, int] = {
    "outline": 42,
}


def _is_generate_job(job: dict) -> bool:
    """job.json vắng mặt `job_type` MẶC ĐỊNH là luồng dub (data-model.md §1)."""
    return job.get("job_type", "dub") == "generate"


def _iter_generate_jobs():
    """Yield job dict cho mỗi jobs/*/job.json có job_type == 'generate'."""
    if not JOBS_DIR.exists():
        return
    for job_dir in sorted(JOBS_DIR.iterdir()):
        if not job_dir.is_dir():
            continue
        job_json_path = job_dir / "job.json"
        if not job_json_path.exists():
            continue
        try:
            job = read_job(job_dir.name)
        except (FileNotFoundError, OSError, ValueError):
            continue
        if _is_generate_job(job):
            yield job


def status_to_progress(job: dict) -> int:
    """Map job.json.status -> % tiến trình ước lượng theo bước."""
    status = job.get("status", "pending")
    if status == "failed":
        status = generate_status_from_artifacts(job)
    if status == "awaiting_review":
        return _REVIEW_GATE_PROGRESS.get(job.get("review_gate"), 0)
    return _STATUS_PROGRESS_MAP.get(status, 0)


def _job_to_summary(job: dict) -> dict:
    """Job Summary (contracts/api.md §2) — CÙNG shape GET /api/jobs, `topic`
    thay cho `source_url`/`platform`."""
    return {
        "job_id": job["job_id"],
        "job_type": "generate",
        "topic": job["topic"],
        "status": job["status"],
        "progress_percent": status_to_progress(job),
        "created_at": job["created_at"],
        "review_gate": job.get("review_gate"),
    }


def _job_to_detail(job: dict) -> dict:
    """Job Detail (contracts/api.md §3) — thêm `scenes` rút gọn (chỉ index/
    narration_text), KHÔNG trả image_path/voice_path tuyệt đối."""
    detail = _job_to_summary(job)
    scenes_path = job.get("artifacts", {}).get("scenes")
    scenes_brief: list[dict] = []
    if scenes_path:
        try:
            with open(scenes_path, encoding="utf-8") as f:
                scenes_brief = [
                    {"index": s.get("index"), "narration_text": s.get("narration_text")}
                    for s in json.load(f).get("scenes", [])
                ]
        except (OSError, ValueError):
            scenes_brief = []
    detail.update(
        {
            "supervised": job.get("supervised", False),
            "tts_provider": job.get("tts_provider", "edge-tts"),
            "voice_id": job.get("voice_id"),
            "error": job.get("error"),
            "scenes": scenes_brief,
            "review_url": (
                f"/api/jobs/{job['job_id']}/review" if job["status"] == "awaiting_review" else None
            ),
            "output_video_url": (
                f"/api/generate-jobs/{job['job_id']}/output"
                if job.get("artifacts", {}).get("output_video")
                else None
            ),
            "can_retry": job["status"] == "failed",
        }
    )
    return detail


class SubmitGenerateJobRequest(BaseModel):
    topic: str
    supervised: bool = False
    tts_provider: str = "edge-tts"
    voice_id: str | None = None


@router.post("", status_code=201)
async def submit_generate_job(body: SubmitGenerateJobRequest):
    """POST /api/generate-jobs — tạo job mới (contracts/api.md §1)."""
    if not body.topic.strip():
        return _error(400, "Chủ đề không được để trống")

    if body.tts_provider not in _VALID_TTS_PROVIDERS:
        return _error(400, "tts_provider phải là 'edge-tts', 'lucyai' hoặc 'omnivoice'")

    # research.md §1: dub và generate là CÙNG 1 hàng đợi — không chạy song song
    running_job_id = find_running_job_id()
    if running_job_id:
        return _error(409, "Đang có job xử lý, vui lòng chờ", running_job_id=running_job_id)

    job = create_generate_job(
        body.topic,
        supervised=body.supervised,
        tts_provider=body.tts_provider,
        voice_id=body.voice_id,
    )
    start_generate_job(job["job_id"])
    return {"job_id": job["job_id"]}


@router.post("/{job_id}/retry", status_code=202)
async def retry_generate_job(job_id: str):
    """
    POST /api/generate-jobs/{job_id}/retry — resume job "generate" đã failed.

    Dùng lại đúng cơ chế resume của run_generate_pipeline(): status "failed" tự
    suy ra bước cần tiếp tục qua generate_status_from_artifacts(), artifact đã
    có (outline/scenes/ảnh/voice đã sinh) được giữ nguyên, không tốn lại chi phí.
    """
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")
    if not _is_generate_job(job):
        return _error(404, "Job không tồn tại")

    if job["status"] != "failed":
        return _error(409, f"Job đang ở trạng thái '{job['status']}', chỉ retry được job 'failed'")

    running_job_id = find_running_job_id()
    if running_job_id:
        return _error(409, "Đang có job khác xử lý, vui lòng chờ", running_job_id=running_job_id)

    start_generate_job(job_id)
    return {"job_id": job_id}


_RERUN_ALLOWED_STATUSES = ("done", "failed", "awaiting_review")


class RerunGenerateFromStepRequest(BaseModel):
    step: str  # "scripting" | "sourcing_assets" | "synthesizing" | "rendering"
    # Đổi giọng đọc trước khi chạy lại — chỉ có tác dụng nếu step còn đi qua
    # synthesizing (mọi bước TRỪ "rendering"); bỏ qua an toàn nếu không.
    tts_provider: str | None = None
    voice_id: str | None = None


@router.post("/{job_id}/rerun-from", status_code=202)
async def rerun_generate_job_from_step(job_id: str, body: RerunGenerateFromStepRequest):
    """
    POST /api/generate-jobs/{job_id}/rerun-from — quay lại một bước TRƯỚC ĐÓ để
    thử lại, thay vì tạo job mới. Cho phép ở CẢ job "done" lẫn "failed"
    (khác /retry — retry chỉ cho job failed), khớp đúng hành vi rerun-from-step
    bên luồng dub (jobs_api.py).

    Hành động PHÁ HUỶ — xoá outline/scenes/ảnh/giọng/video của bước này và mọi
    bước sau. Frontend PHẢI xác nhận với người dùng trước khi gọi.
    """
    if body.step not in GENERATE_RERUN_STEPS:
        return _error(400, f"Bước không hợp lệ: {body.step}. Chỉ chạy lại được từ: {GENERATE_RERUN_STEPS}")

    if body.tts_provider is not None and body.tts_provider not in _VALID_TTS_PROVIDERS:
        return _error(400, "tts_provider phải là 'edge-tts', 'lucyai' hoặc 'omnivoice'")

    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")
    if not _is_generate_job(job):
        return _error(404, "Job không tồn tại")

    if job["status"] not in _RERUN_ALLOWED_STATUSES:
        return _error(
            409,
            f"Job đang xử lý (trạng thái: {job['status']}), không chạy lại được lúc này",
        )

    running_job_id = find_running_job_id()
    if running_job_id:
        return _error(409, "Đang có job khác xử lý, vui lòng chờ", running_job_id=running_job_id)

    if body.tts_provider is not None or body.voice_id is not None:
        if body.tts_provider is not None:
            job["tts_provider"] = body.tts_provider
        if body.voice_id is not None:
            job["voice_id"] = body.voice_id
        write_job(job_id, job)

    rerun_generate_from_step(job_id, body.step)
    start_generate_job(job_id)
    return {"job_id": job_id, "resumed_status": body.step}


@router.get("")
async def list_generate_jobs():
    """GET /api/generate-jobs — danh sách Job Summary, mới nhất trước."""
    jobs = [_job_to_summary(job) for job in _iter_generate_jobs()]
    jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return {"jobs": jobs}


@router.get("/{job_id}")
async def get_generate_job(job_id: str):
    """GET /api/generate-jobs/{job_id} — Job Detail (contracts/api.md §3)."""
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")
    if not _is_generate_job(job):
        return _error(404, "Job không tồn tại")
    return _job_to_detail(job)


@router.get("/{job_id}/output")
async def get_generate_job_output(job_id: str):
    """GET /api/generate-jobs/{job_id}/output — stream video kết quả (contracts/api.md §4)."""
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")
    if not _is_generate_job(job):
        return _error(404, "Job không tồn tại")

    output_path = job.get("artifacts", {}).get("output_video")
    if not output_path:
        return _error(404, "Job chưa có video output")

    return FileResponse(output_path, media_type="video/mp4", filename=f"{job_id}.mp4")

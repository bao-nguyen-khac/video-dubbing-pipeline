"""
web/backend/jobs_api.py — Endpoint quản lý job (submit/list/detail/output/retry).

Chỉ gọi lại các hàm đã có trong pipeline.py (create_job, read_job,
detect_platform, run_pipeline, status_from_artifacts) — không viết lại logic xử
lý media (Constitution Principle I, research.md).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from pipeline import (
    JOBS_DIR,
    create_job,
    detect_platform,
    read_job,
    status_from_artifacts,
)
from pipeline import _write_job as write_job
from web.backend.job_runner import start_job

router = APIRouter()

# % ước lượng theo bước pipeline hiện tại (Clarification 2026-07-26, research.md)
_STATUS_PROGRESS_MAP: dict[str, int] = {
    "pending": 0,
    "downloading": 15,
    "transcribing": 32,
    "scripting": 48,
    "synthesizing": 65,
    "merging": 82,
    "done": 100,
}


def _error(status_code: int, message: str, **extra) -> JSONResponse:
    """Response lỗi đồng nhất `{"error": ...}` cho mọi status code (T026: rà soát)."""
    return JSONResponse(status_code=status_code, content={"error": message, **extra})


def _iter_all_jobs():
    """Yield job dict cho mỗi jobs/*/job.json đọc được (bỏ qua file hỏng/thiếu)."""
    if not JOBS_DIR.exists():
        return
    for job_dir in sorted(JOBS_DIR.iterdir()):
        if not job_dir.is_dir():
            continue
        job_json_path = job_dir / "job.json"
        if not job_json_path.exists():
            continue
        try:
            with open(job_json_path, encoding="utf-8") as f:
                yield json.load(f)
        except (json.JSONDecodeError, OSError):
            continue


def find_running_job_id() -> str | None:
    """
    Trả về job_id của job đang xử lý (status không thuộc {done, failed}), hoặc
    None nếu không có job nào đang chạy.

    Luôn quét trực tiếp jobs/*/job.json (không dùng biến in-memory) để không bị
    lệch trạng thái khi backend restart giữa lúc job đang chạy (research.md).
    """
    for job in _iter_all_jobs():
        if job.get("status") not in ("done", "failed"):
            return job.get("job_id")
    return None


def status_to_progress(job: dict) -> int:
    """
    Map job.json.status -> % tiến trình ước lượng theo bước (research.md).

    Với job đã "failed" (trạng thái cuối, không tự biết bước dở dang), suy ra %
    từ artifact đã có (tái dùng status_from_artifacts của pipeline.py) — giữ %
    của bước cuối cùng đã hoàn tất trước khi lỗi.
    """
    status = job.get("status", "pending")
    if status == "failed":
        status = status_from_artifacts(job)
    return _STATUS_PROGRESS_MAP.get(status, 0)


def _job_to_summary(job: dict) -> dict:
    """Job Summary (data-model.md) — dùng cho GET /api/jobs và làm nền cho detail."""
    return {
        "job_id": job["job_id"],
        "source_url": job["source_url"],
        "platform": job["platform"],
        "status": job["status"],
        "progress_percent": status_to_progress(job),
        "created_at": job["created_at"],
        # Ghim job lên mục "Ưu tiên" ở danh sách lịch sử
        "pinned": bool(job.get("pinned", False)),
        "pinned_at": job.get("pinned_at"),
    }


def _get_artifact_path(job: dict, artifact_key: str, filename: str) -> Path | None:
    """
    Trả về Path thực tế của 1 artifact video, dùng chung cho output_video và
    source_video.

    job.json lưu đường dẫn tuyệt đối ghi lúc pipeline chạy (vd `/app/jobs/...`
    nếu job được tạo trong Docker). Nếu backend đang chạy ở môi trường khác
    (deploy bằng lệnh thay vì Docker, JOBS_DIR trỏ chỗ khác), đường dẫn cũ
    trong job.json không còn đúng dù file vật lý vẫn nằm trong jobs/{job_id}/
    hiện tại — fallback về đúng chỗ đó theo JOBS_DIR + tên file cố định.
    """
    recorded = job.get("artifacts", {}).get(artifact_key)
    if recorded and Path(recorded).exists():
        return Path(recorded)
    job_id = job.get("job_id")
    if job_id:
        fallback = JOBS_DIR / job_id / filename
        if fallback.exists():
            return fallback
    return None


def _get_output_video_path(job: dict) -> Path | None:
    return _get_artifact_path(job, "output_video", "output.mp4")


def _get_source_video_path(job: dict) -> Path | None:
    return _get_artifact_path(job, "source_video", "source.mp4")


def _job_to_detail(job: dict) -> dict:
    """Job Detail (data-model.md) — dùng cho GET /api/jobs/{job_id}."""
    detail = _job_to_summary(job)
    has_output = _get_output_video_path(job) is not None
    detail.update(
        {
            "script_mode": job["script_mode"],
            # .get() vì job.json tạo trước feature 003/004 chưa có field này
            "dynamic_captions": job.get("dynamic_captions", False),
            "subtitles_burned": job.get("subtitles_burned", False),
            "tts_provider": job.get("tts_provider", "edge-tts"),
            "voice_id": job.get("voice_id"),
            # 005-natural-pause-dubbing: số nhịp bị thay bằng khoảng lặng do
            # lỗi TTS cục bộ (warnings.tts_segments_failed đi kèm, được
            # pass-through nguyên vẹn bên dưới)
            "tts_failed_segments": job.get("tts_failed_segments", 0),
            "error": job.get("error"),
            "warnings": job.get("warnings", {}),
            "output_video_url": f"/api/jobs/{job['job_id']}/output" if has_output else None,
            "source_video_url": (
                f"/api/jobs/{job['job_id']}/source" if _get_source_video_path(job) else None
            ),
            "can_retry": job["status"] == "failed",
        }
    )
    return detail


class SubmitJobRequest(BaseModel):
    url: str
    script_mode: str  # "translate" | "rewrite" | "subtitle" | "download"
    dynamic_captions: bool = False
    tts_provider: str = "edge-tts"
    voice_id: str | None = None
    # Khoảng giữ nguyên audio gốc (nhạc/tiếng hát), vd "0:15-0:30, 1:05-end"
    keep_original_ranges: str | None = None


@router.post("", status_code=201)
async def submit_job(body: SubmitJobRequest):
    """POST /api/jobs — submit job mới (FR-001, FR-002, FR-009, contracts/api.md)."""
    if body.script_mode not in ("translate", "rewrite", "subtitle", "download"):
        return _error(400, "script_mode phải là 'translate', 'rewrite', 'subtitle' hoặc 'download'")

    if body.tts_provider not in ("edge-tts", "lucyai", "omnivoice"):
        return _error(400, "tts_provider phải là 'edge-tts', 'lucyai' hoặc 'omnivoice'")

    try:
        platform = detect_platform(body.url)
    except ValueError as e:
        return _error(400, str(e))

    running_job_id = find_running_job_id()
    if running_job_id:
        return _error(409, "Đang có job xử lý, vui lòng chờ", running_job_id=running_job_id)

    job = create_job(
        body.url,
        platform,
        body.script_mode,
        dynamic_captions=body.dynamic_captions,
        tts_provider=body.tts_provider,
        voice_id=body.voice_id,
        keep_original_ranges=body.keep_original_ranges,
    )
    start_job(
        body.url,
        body.script_mode,
        job["job_id"],
        dynamic_captions=body.dynamic_captions,
        tts_provider=body.tts_provider,
        voice_id=body.voice_id,
    )
    return {"job_id": job["job_id"]}


@router.get("")
async def list_jobs():
    """GET /api/jobs — danh sách Job Summary, mới nhất trước (US2, data-model.md)."""
    jobs = [_job_to_summary(job) for job in _iter_all_jobs()]
    jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return {"jobs": jobs}


@router.get("/{job_id}")
async def get_job(job_id: str):
    """GET /api/jobs/{job_id} — Job Detail (data-model.md, contracts/api.md)."""
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")
    return _job_to_detail(job)


@router.get("/{job_id}/output")
async def get_job_output(job_id: str):
    """GET /api/jobs/{job_id}/output — stream video sản phẩm (FR-004)."""
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")

    output_path = _get_output_video_path(job)
    if not output_path:
        return _error(404, "Job chưa có video output")

    return FileResponse(output_path, media_type="video/mp4", filename=f"{job_id}.mp4")


@router.get("/{job_id}/source")
async def get_job_source(job_id: str):
    """
    GET /api/jobs/{job_id}/source — stream video gốc đã tải về, để xem song
    song với video kết quả và so sánh đầu vào/đầu ra.
    """
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")

    source_path = _get_source_video_path(job)
    if not source_path:
        return _error(404, "Job chưa có video gốc")

    return FileResponse(source_path, media_type="video/mp4", filename=f"{job_id}-source.mp4")


@router.post("/{job_id}/retry", status_code=202)
async def retry_job(job_id: str):
    """
    POST /api/jobs/{job_id}/retry — resume job đã failed (US3, FR-008).

    Dùng lại đúng cơ chế resume của pipeline.run_pipeline() (contracts/cli.md
    của 001): gọi lại với cùng job_id + url/script_mode gốc, các artifact đã
    có (source.mp4, transcript.json...) được giữ nguyên, không tải lại từ đầu.
    """
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")

    if job["status"] != "failed":
        return _error(409, f"Job đang ở trạng thái '{job['status']}', chỉ retry được job 'failed'")

    running_job_id = find_running_job_id()
    if running_job_id:
        return _error(409, "Đang có job khác xử lý, vui lòng chờ", running_job_id=running_job_id)

    start_job(
        job["source_url"],
        job["script_mode"],
        job_id,
        dynamic_captions=job.get("dynamic_captions", False),
        tts_provider=job.get("tts_provider", "edge-tts"),
        voice_id=job.get("voice_id"),
    )
    return {"job_id": job_id}


class PinRequest(BaseModel):
    pinned: bool


@router.put("/{job_id}/pin")
async def pin_job(job_id: str, body: PinRequest):
    """PUT /api/jobs/{job_id}/pin — ghim/bỏ ghim job (đưa lên mục Ưu tiên)."""
    from datetime import datetime, timezone

    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")

    job["pinned"] = body.pinned
    job["pinned_at"] = datetime.now(timezone.utc).isoformat() if body.pinned else None
    write_job(job_id, job)
    return {"job_id": job_id, "pinned": body.pinned}


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """
    DELETE /api/jobs/{job_id} — xoá hẳn job và MỌI file trên server.

    Xoá thư mục jobs/{job_id}/ (source, output, voice...), dọn kèm bản ghi
    lượt đăng (publish_data/) và entry sổ tải đã trỏ tới file vừa xoá. Không
    xoá job đang chạy.
    """
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        return _error(404, "Job không tồn tại")

    # Chỉ chặn khi job đang THỰC SỰ xử lý (một bước giữa chừng) — job
    # pending/done/failed đều xoá được.
    if job.get("status") in ("downloading", "transcribing", "scripting", "synthesizing", "merging"):
        return _error(409, "Job đang xử lý, không xoá được — chờ xong hoặc thử lại sau")

    # Xoá thư mục job (nguồn sự thật chính)
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)

    # Dọn bản ghi lượt đăng của job (best-effort, không chặn nếu thiếu module)
    try:
        from publish import store as publish_store

        pub_dir = publish_store.publishes_dir(job_id)
        if pub_dir.exists():
            shutil.rmtree(pub_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001 — dọn kèm lỗi không được chặn việc xoá job
        pass

    # Dọn sổ video đã tải: bỏ các entry trỏ tới file vừa xoá (self-heal)
    try:
        import download_registry

        download_registry.prune_missing()
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "job_id": job_id}

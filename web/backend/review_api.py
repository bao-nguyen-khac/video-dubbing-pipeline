"""
web/backend/review_api.py — Endpoint chốt kiểm duyệt (008-supervised-pipeline).

4 endpoint dưới prefix /api/jobs (nên đi qua đúng auth middleware sẵn có):
  GET    /{job_id}/review              — lấy nội dung chốt để review
  PUT    /{job_id}/review              — lưu bản sửa (không phê duyệt)
  POST   /{job_id}/review/approve      — phê duyệt, chạy tiếp
  POST   /{job_id}/review/regenerate   — sinh lại kịch bản (chỉ chốt kịch bản)

Toàn bộ logic đọc/ghi/validate nội dung nằm ở review/gates.py — file này chỉ lo
phần HTTP: guard trạng thái, map lỗi sang status code, và khoá chống duyệt trùng.
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hardsub.detector import build_manual_regions
from pipeline import JOBS_DIR, read_job, update_job_status
from pipeline import _write_job as write_job
from review import gates
from web.backend.job_runner import start_job
from web.backend.jobs_api import _error, find_running_job_id

router = APIRouter()

# Chuỗi "đọc job → kiểm tra → ghi status mới" MUST là một khối không chen ngang
# được: start_job() chạy pipeline trong thread nền, nên hai request gần nhau
# (nhấn đúp, hoặc 2 tab) thực sự có thể xen giữa read_job() và _write_job() rồi
# tạo hai lượt xử lý song song trên cùng job (FR-019, research.md §6).
_APPROVE_LOCK = threading.Lock()


class _GuardError(Exception):
    """Guard thất bại — mang theo sẵn response để endpoint trả về nguyên vẹn."""

    def __init__(self, response: JSONResponse):
        self.response = response


def _load_awaiting_job(job_id: str, gate: str | None) -> dict:
    """
    Đọc job và khẳng định nó đang chờ duyệt tại đúng chốt `gate`.

    Đây cũng chính là cái chặn cú click phê duyệt thứ hai: lượt đầu đã đổi status
    khỏi "awaiting_review" nên lượt sau rơi vào nhánh 409 (FR-019) — không cần
    token/nonce riêng.

    Raises: _GuardError với response 404/409 tương ứng.
    """
    try:
        job = read_job(job_id)
    except FileNotFoundError:
        raise _GuardError(_error(404, "Job không tồn tại")) from None

    status = job.get("status")
    if status != "awaiting_review":
        raise _GuardError(
            _error(
                409,
                f"Job không đang chờ duyệt (trạng thái: {status})",
                status=status,
            )
        )

    current_gate = job.get("review_gate")
    if gate is not None and gate != current_gate:
        raise _GuardError(
            _error(409, f"Chốt không khớp: job đang chờ duyệt tại '{current_gate}'")
        )

    return job


# ─── GET /review — lấy nội dung chốt ────────────────────────────────────────


@router.get("/{job_id}/review")
async def get_review(job_id: str):
    """
    GET /api/jobs/{job_id}/review — nội dung chốt để review (FR-009, FR-010).

    `segments: []` (video không có lời thoại) là phản hồi THÀNH CÔNG, không phải
    lỗi — người dùng tự quyết định phê duyệt hay xoá job (spec, Edge Cases).
    """
    try:
        job = _load_awaiting_job(job_id, None)
    except _GuardError as e:
        return e.response

    try:
        return gates.build_payload(job, job["review_gate"])
    except (gates.GateError, OSError, ValueError) as e:
        return _error(500, f"Không đọc được nội dung chốt: {e}")


# ─── PUT /review — lưu bản sửa ──────────────────────────────────────────────


class SaveReviewSegment(BaseModel):
    index: int
    text: str = ""


class HardsubBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class SaveReviewRequest(BaseModel):
    gate: str
    segments: list[SaveReviewSegment]
    # 009-hardsub-blur-reposition: vùng phụ đề gốc người dùng tự khoanh trên
    # khung hình đại diện, cùng lượt lưu nội dung transcript.
    hardsub_box: HardsubBox | None = None
    # Khoảng KHÔNG có phụ đề gốc — cho phép chỉnh lại ngay ở chốt review thay
    # vì chỉ đặt được lúc tạo job (field ĐỘC LẬP với keep_original_ranges).
    hardsub_no_ranges: str | None = None


@router.put("/{job_id}/review")
async def save_review(job_id: str, body: SaveReviewRequest):
    """
    PUT /api/jobs/{job_id}/review — lưu bản sửa mà KHÔNG phê duyệt (FR-011).

    Status giữ nguyên `awaiting_review` để người dùng lưu nháp rồi quay lại sau.
    """
    try:
        job = _load_awaiting_job(job_id, body.gate)
    except _GuardError as e:
        return e.response

    if (body.hardsub_box is not None or body.hardsub_no_ranges is not None) and not job.get(
        "hardsub_blur_enabled"
    ):
        return _error(400, "Job không bật tính năng làm mờ phụ đề gốc")

    edits = [seg.model_dump() for seg in body.segments]
    try:
        saved_count, dropped_count = gates.save_edits(job, body.gate, edits)
    except gates.EmptyGateError as e:
        return _error(400, str(e))
    except gates.UnknownSegmentError as e:
        return _error(400, str(e))
    except gates.GateError as e:
        return _error(400, str(e))

    gates.mark_edited(job, body.gate, saved_count)

    if body.hardsub_box is not None:
        gates.save_hardsub_box(job, body.hardsub_box.model_dump())
    if body.hardsub_no_ranges is not None:
        job["hardsub_no_ranges"] = body.hardsub_no_ranges or None

    write_job(job_id, job)

    return {
        "job_id": job_id,
        "gate": body.gate,
        "saved_count": saved_count,
        "dropped_count": dropped_count,
    }


# ─── POST /review/segment — thêm câu thủ công (đoạn ASR bỏ sót) ─────────────


class AddSegmentRequest(BaseModel):
    gate: str
    start: float
    end: float
    text: str


@router.post("/{job_id}/review/segment", status_code=201)
async def add_review_segment(job_id: str, body: AddSegmentRequest):
    """
    POST /api/jobs/{job_id}/review/segment — thêm 1 câu THỦ CÔNG vào chốt lời
    thoại HOẶC chốt kịch bản khi đoạn video tiếng nhỏ, ASR bỏ sót nên không tự
    tách được sub.

    Chỉ áp dụng chốt lời thoại (transcript) + kịch bản (script) — chốt outline
    (generate) không có timing thật để chèn theo thời gian. Status giữ nguyên
    `awaiting_review` để người dùng thêm nhiều câu rồi mới phê duyệt.
    """
    if body.gate not in gates.MANUAL_ADD_GATES:
        return _error(400, "Chỉ thêm câu thủ công được ở chốt lời thoại hoặc kịch bản")

    try:
        job = _load_awaiting_job(job_id, body.gate)
    except _GuardError as e:
        return e.response

    try:
        segment_count, new_index = gates.add_segment(
            job, body.gate, body.start, body.end, body.text
        )
    except gates.GateError as e:
        return _error(400, str(e))

    gates.mark_edited(job, body.gate, segment_count)
    write_job(job_id, job)

    return {
        "job_id": job_id,
        "gate": body.gate,
        "segment_count": segment_count,
        "new_index": new_index,
    }


# ─── POST /review/approve — phê duyệt, chạy tiếp ────────────────────────────


class ApproveRequest(BaseModel):
    gate: str


@router.post("/{job_id}/review/approve", status_code=202)
async def approve_review(job_id: str, body: ApproveRequest):
    """
    POST /api/jobs/{job_id}/review/approve — phê duyệt chốt và chạy tiếp
    (FR-017, FR-018, FR-019).

    Ở MỌI nhánh từ chối, job giữ nguyên trạng thái chờ duyệt cùng toàn bộ nội
    dung đã lưu — không đánh dấu lỗi, không mất bản sửa (FR-018).
    """
    next_status: str
    with _APPROVE_LOCK:
        try:
            job = _load_awaiting_job(job_id, body.gate)
        except _GuardError as e:
            return e.response

        running_job_id = find_running_job_id()
        if running_job_id:
            return _error(
                409,
                "Đang có job khác xử lý, vui lòng chờ rồi phê duyệt lại",
                running_job_id=running_job_id,
            )

        # 009-hardsub-blur-reposition: dựng hardsub_regions.json từ vùng người
        # dùng vừa khoanh, ĐÚNG lúc phê duyệt chốt lời thoại — sau khi cả vùng
        # lẫn hardsub_no_ranges đã chốt (có thể chỉnh lại nhiều lượt trước đó).
        # Nếu khung hình đại diện không trích được (lỗi ffmpeg hiếm gặp), bỏ
        # qua yêu cầu khoanh vùng — merge sẽ không mờ gì, an toàn hơn là chặn
        # cả job (US3, cùng tinh thần "thà bỏ sót còn hơn mờ nhầm").
        if body.gate == gates.GATE_TRANSCRIPT and job.get("hardsub_blur_enabled"):
            frame_path = job.get("artifacts", {}).get("hardsub_frame")
            if frame_path and Path(frame_path).exists():
                box = job.get("hardsub_box")
                if not box:
                    return _error(
                        400, "Cần khoanh vùng phụ đề gốc cần làm mờ trước khi phê duyệt"
                    )
                regions_path = build_manual_regions(
                    job["artifacts"]["source_video"],
                    job.get("hardsub_no_ranges"),
                    JOBS_DIR / job_id,
                    box,
                )
                job["artifacts"]["hardsub_regions"] = str(regions_path)

        next_status = gates.NEXT_STATUS_AFTER_GATE[body.gate]
        gates.mark_approved(job, body.gate)
        # 010-topic-video-generation: job "generate" KHÔNG dùng
        # update_job_status()/VALID_TRANSITIONS của pipeline.py (luồng dub) —
        # "sourcing_assets" không nằm trong state machine đó. Ghi status trực
        # tiếp, giống cách generate_pipeline.py tự quản lý status của nó.
        is_generate_job = job.get("job_type", "dub") == "generate"
        if is_generate_job:
            job["status"] = next_status
            write_job(job_id, job)
        else:
            write_job(job_id, job)
            # Đổi status BÊN TRONG lock: từ đây cú phê duyệt thứ hai sẽ thấy
            # status khác "awaiting_review" và bị `_load_awaiting_job()` từ
            # chối (FR-019).
            update_job_status(job_id, next_status)

    # Spawn thread nền NGOÀI lock để không giữ khoá qua I/O — đúng orchestrator
    # theo job_type (generate_pipeline.py vs pipeline.py, research.md §1).
    if is_generate_job:
        from web.backend.generate_jobs_api import start_generate_job

        start_generate_job(job_id)
    else:
        start_job(
            job["source_url"],
            job["script_mode"],
            job_id,
            dynamic_captions=job.get("dynamic_captions", False),
            tts_provider=job.get("tts_provider", "edge-tts"),
            voice_id=job.get("voice_id"),
            supervised=job.get("supervised", True),
        )

    return {"job_id": job_id, "approved_gate": body.gate, "resumed_status": next_status}


# ─── POST /review/regenerate — sinh lại kịch bản ────────────────────────────


@router.post("/{job_id}/review/regenerate", status_code=202)
async def regenerate_script(job_id: str):
    """
    POST /api/jobs/{job_id}/review/regenerate — dịch lại kịch bản từ lời thoại
    ĐÃ DUYỆT rồi dừng lại tại chính chốt kịch bản (FR-020).

    Xoá script.json là cách duy nhất buộc generate_script() sinh lại: hàm đó
    return sớm khi file đã tồn tại và có 'segments' (research.md §8).

    Cảnh báo "phần sửa tay sẽ bị ghi đè" là hộp xác nhận ở frontend TRƯỚC khi gọi
    endpoint này — API không có bước xác nhận hai pha.
    """
    with _APPROVE_LOCK:
        try:
            job = _load_awaiting_job(job_id, gates.GATE_SCRIPT)
        except _GuardError as e:
            # Message riêng khi đang ở chốt lời thoại: ở đó chưa có kịch bản nào
            # để sinh lại, nói "chốt không khớp" sẽ khó hiểu
            try:
                current = read_job(job_id).get("review_gate")
            except FileNotFoundError:
                current = None
            if current == gates.GATE_TRANSCRIPT:
                return _error(409, "Chỉ sinh lại được kịch bản ở chốt kịch bản")
            return e.response

        running_job_id = find_running_job_id()
        if running_job_id:
            return _error(
                409,
                "Đang có job khác xử lý, vui lòng chờ rồi thử lại",
                running_job_id=running_job_id,
            )

        script_path = job.get("artifacts", {}).get("script")
        if script_path:
            path = Path(script_path)
            path.unlink(missing_ok=True)
            # Bản lưu cũng phải đi: lượt sửa tay tiếp theo cần tạo bản lưu mới
            # khớp với script.json MỚI, không phải bản của kịch bản đã bỏ
            (path.parent / "script_original.json").unlink(missing_ok=True)

        gates.mark_regenerated(job)
        job["artifacts"]["script"] = None
        write_job(job_id, job)
        update_job_status(job_id, "scripting")
        regenerated_count = job["review_gates"][gates.GATE_SCRIPT]["regenerated_count"]

    start_job(
        job["source_url"],
        job["script_mode"],
        job_id,
        dynamic_captions=job.get("dynamic_captions", False),
        tts_provider=job.get("tts_provider", "edge-tts"),
        voice_id=job.get("voice_id"),
        supervised=job.get("supervised", True),
    )

    return {"job_id": job_id, "regenerated_count": regenerated_count}

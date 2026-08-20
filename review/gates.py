"""
review/gates.py — Helper cho chốt kiểm duyệt (008-supervised-pipeline).

Dùng chung cho HAI phía:
  - `pipeline.py`: ghi payload + đánh dấu "đã dừng ở chốt" lúc pipeline dừng lại.
  - `web/backend/review_api.py`: đọc payload, lưu bản sửa của người dùng, đánh
    dấu "đã duyệt".

Vì `pipeline.py` import module này, nó MUST NOT import bất cứ thứ gì từ `web/`
(sẽ đảo chiều phụ thuộc pipeline → web, và làm CLI `pipeline.py` không chạy được
khi chưa cài FastAPI). Toàn bộ hàm ở đây là logic thuần trên dict + file JSON.

⚠️ Bất biến quan trọng nhất của cả feature: `transcript_reviewed.json` KHÔNG
được chứa khoá 'words'. Bước scripting gọi `resegment_by_sentences()`, hàm này
dựng lại `text` từ mảng `words` — còn `words` là phần sửa tay của người dùng bị
ghi đè âm thầm (research.md §3).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

# ─── Định danh chốt ──────────────────────────────────────────────────────────

GATE_TRANSCRIPT = "transcript"
GATE_SCRIPT = "script"
# 010-topic-video-generation: chốt outline/scene của luồng "generate" — tái
# dùng NGUYÊN VẸN cơ chế gate chung này thay vì viết review-gate riêng
# (research.md §7). File payload là scenes.json, KHÔNG phải segments dạng
# transcript/script.
GATE_OUTLINE = "outline"
GATES = (GATE_TRANSCRIPT, GATE_SCRIPT, GATE_OUTLINE)

# Bước pipeline chạy tiếp sau khi duyệt từng chốt (FR-017)
NEXT_STATUS_AFTER_GATE = {
    GATE_TRANSCRIPT: "scripting",
    GATE_SCRIPT: "synthesizing",
    GATE_OUTLINE: "sourcing_assets",
}

# Trường sửa được của từng chốt, theo schema file tương ứng
EDITABLE_FIELD = {
    GATE_TRANSCRIPT: "text",
    GATE_SCRIPT: "translated_text",
    GATE_OUTLINE: "narration_text",
}

# Tên khoá mảng phần tử trong file payload của từng chốt — 2 chốt cũ đều dùng
# "segments" (transcript_reviewed.json/script.json), nhưng scenes.json (chốt
# outline) dùng khoá "scenes". build_payload()/save_edits() MUST đọc/ghi theo
# khoá này thay vì hardcode "segments" (data-model.md §3, research.md §7).
GATE_ARRAY_KEY = {
    GATE_TRANSCRIPT: "segments",
    GATE_SCRIPT: "segments",
    GATE_OUTLINE: "scenes",
}


class GateError(Exception):
    """Lỗi nghiệp vụ ở chốt — chỗ gọi map sang HTTP status phù hợp."""


class EmptyGateError(GateError):
    """Toàn bộ các câu đều rỗng sau khi lọc — không còn gì cho bước sau (FR-014)."""


class UnknownSegmentError(GateError):
    """Client gửi index không tồn tại trong chốt."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Đọc/ghi file payload ────────────────────────────────────────────────────


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def strip_words(segments: list[dict]) -> list[dict]:
    """
    Lược mỗi segment còn đúng start/end/text — BỎ 'words'.

    Đây là hàm hiện thực bất biến ở docstring đầu module: không có 'words' thì
    `_flatten_words()` trong script_gen/sentence_segmenter.py trả None, nên
    `resegment_by_sentences()` giữ nguyên segment và phần sửa tay sống sót.
    """
    return [
        {
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": (seg.get("text") or "").strip(),
        }
        for seg in segments
    ]


def write_transcript_review(job_dir: Path, segments: list[dict], resegmented: bool) -> Path:
    """
    Ghi `transcript_reviewed.json` — payload chốt lời thoại VÀ là đầu vào thật
    của bước scripting với job supervised (data-model.md §3).
    """
    path = Path(job_dir) / "transcript_reviewed.json"
    _write_json(
        path,
        {
            "source": "transcript.json",
            "resegmented": resegmented,
            "segments": strip_words(segments),
        },
    )
    return path


def gate_file_path(job: dict, gate: str) -> Path:
    """File chứa nội dung của chốt tương ứng."""
    if gate == GATE_TRANSCRIPT:
        recorded = job.get("artifacts", {}).get("transcript_reviewed")
    elif gate == GATE_SCRIPT:
        recorded = job.get("artifacts", {}).get("script")
    elif gate == GATE_OUTLINE:
        recorded = job.get("artifacts", {}).get("scenes")
    else:
        raise GateError(f"Chốt không hợp lệ: {gate}")

    if not recorded:
        raise GateError(f"Job chưa có nội dung cho chốt '{gate}'")
    return Path(recorded)


# ─── Payload cho giao diện ───────────────────────────────────────────────────


def build_payload(job: dict, gate: str) -> dict:
    """
    Dựng payload `GET /api/jobs/{id}/review` (contracts/api.md §2).

    `segments` rỗng là kết quả HỢP LỆ (video không có lời thoại) — chỗ gọi
    MUST NOT coi đó là lỗi (spec, Edge Cases; research.md §10).
    """
    if gate not in GATES:
        raise GateError(f"Chốt không hợp lệ: {gate}")

    data = _read_json(gate_file_path(job, gate))
    field = EDITABLE_FIELD[gate]
    array_key = GATE_ARRAY_KEY[gate]
    gate_meta = job.get("review_gates", {}).get(gate, {})

    segments = [
        {
            "index": i,
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": seg.get(field) or "",
            # Chỉ chốt kịch bản có câu gốc để đối chiếu (FR-010). Chốt outline
            # (010) không có khái niệm "câu gốc" — luôn None (contracts/api.md §5).
            "source_text": seg.get("source_text") if gate == GATE_SCRIPT else None,
        }
        for i, seg in enumerate(data.get(array_key, []))
    ]

    payload = {
        "job_id": job["job_id"],
        "gate": gate,
        "editable_field": field,
        "edited": bool(gate_meta.get("edited", False)),
        "can_regenerate": gate == GATE_SCRIPT,
        "reached_at": gate_meta.get("reached_at"),
        "segments": segments,
    }

    # 009-hardsub-blur-reposition (FR-012/FR-013): chỉ hiện khi job bật ĐỒNG
    # THỜI cả làm mờ phụ đề gốc lẫn Quản lý pipeline — field VẮNG MẶT hoàn
    # toàn ở mọi trường hợp khác, kể cả ở chốt kịch bản (chỉ có ý nghĩa ở chốt
    # lời thoại, nơi khung hình đại diện đã trích trước — research.md §6).
    # Người dùng tự khoanh vùng bằng mắt trên khung hình này (không còn OCR tự
    # động) — xem hardsub/detector.py.
    if gate == GATE_TRANSCRIPT and job.get("hardsub_blur_enabled") and job.get("supervised"):
        frame_path = job.get("artifacts", {}).get("hardsub_frame")
        if frame_path and Path(frame_path).exists():
            payload["hardsub_frame_url"] = f"/api/jobs/{job['job_id']}/hardsub-frame"
            payload["hardsub_frame_size"] = job.get("hardsub_frame_size")
            payload["hardsub_box"] = job.get("hardsub_box")
            payload["hardsub_no_ranges"] = job.get("hardsub_no_ranges")

    return payload


# ─── Lưu bản sửa ─────────────────────────────────────────────────────────────


def save_edits(job: dict, gate: str, edits: list[dict]) -> tuple[int, int]:
    """
    Áp bản sửa của người dùng vào file của chốt (contracts/api.md §3).

    Chỉ đọc `index` + `text` của mỗi phần tử `edits`; start/end/source_text client
    gửi lên bị BỎ QUA (FR-016 — mốc thời gian read-only ở v1). Segment không xuất
    hiện trong `edits` giữ nguyên nội dung đã lưu.

    Câu có nội dung rỗng/chỉ khoảng trắng bị LOẠI khỏi file (FR-013: "xoá trắng =
    bỏ câu này") — lọc ngay lúc lưu để "nội dung đã lưu" đúng nghĩa là "nội dung
    các bước sau dùng", không còn nhánh lọc thứ hai nào để quên (FR-012).

    Returns: (saved_count, dropped_count) — số câu còn lại, số câu bị bỏ lượt này.

    Raises:
        UnknownSegmentError: `index` không tồn tại → không ghi gì.
        EmptyGateError: sau khi lọc không còn câu nào → KHÔNG ghi file (FR-014).
    """
    if gate not in GATES:
        raise GateError(f"Chốt không hợp lệ: {gate}")

    path = gate_file_path(job, gate)
    data = _read_json(path)
    array_key = GATE_ARRAY_KEY[gate]
    segments = data.get(array_key, [])
    field = EDITABLE_FIELD[gate]

    for edit in edits:
        try:
            index = int(edit["index"])
        except (KeyError, TypeError, ValueError):
            raise UnknownSegmentError("Thiếu hoặc sai định dạng số câu (index)") from None
        if index < 0 or index >= len(segments):
            raise UnknownSegmentError(f"Câu số {index} không tồn tại trong chốt này")
        segments[index][field] = (edit.get("text") or "").strip()

    kept = [seg for seg in segments if (seg.get(field) or "").strip()]
    dropped = len(segments) - len(kept)

    if not kept:
        # Ném TRƯỚC khi ghi — một lượt lưu sai không được làm hỏng job (FR-014)
        raise EmptyGateError(
            "Không thể lưu: toàn bộ các câu đều rỗng, các bước sau sẽ không có "
            "gì để xử lý"
        )

    if gate == GATE_SCRIPT:
        # Lần sửa tay ĐẦU TIÊN giữ lại bản LLM sinh ra để còn đối chiếu/audit
        # (Constitution VI). Các lượt sau không ghi đè bản lưu đó.
        backup = path.parent / "script_original.json"
        if not backup.exists():
            shutil.copy2(path, backup)
        # `content` phải tính lại cho khớp cách generate_script() tạo nó
        # (router_client.py) — nếu không, nội dung cũ còn sót gây nhầm khi debug
        data["content"] = " ".join(seg.get(field) or "" for seg in kept)

    data[array_key] = kept
    _write_json(path, data)
    return len(kept), dropped


# Chốt cho phép thêm câu thủ công. Outline (010-generate) KHÔNG hỗ trợ: scene
# chưa có timing thật (start/end null tới bước synthesizing), thêm câu theo mốc
# thời gian là vô nghĩa ở đó.
MANUAL_ADD_GATES = (GATE_TRANSCRIPT, GATE_SCRIPT)


def add_segment(job: dict, gate: str, start: float, end: float, text: str) -> tuple[int, int]:
    """
    Chèn 1 câu THỦ CÔNG vào chốt lời thoại HOẶC chốt kịch bản rồi sắp lại theo
    mốc bắt đầu — dùng khi đoạn video tiếng nhỏ, ASR bỏ sót nên không tự tách sub.

    - Chốt lời thoại: câu mới = {start, end, text}.
    - Chốt kịch bản: câu mới = {start, end, source_text: "", translated_text: text}
      — KHÔNG có câu gốc (ASR bỏ sót); `content` được tính lại cho khớp cách
      generate_script() dựng nó (research.md §... — giống nhánh GATE_SCRIPT trong
      save_edits()).

    Câu thêm tay KHÔNG có 'words' (đúng bất biến ở docstring đầu module) nên chảy
    qua bước scripting/synthesizing như mọi câu đã sửa tay khác.

    Returns: (tổng số câu sau khi thêm, index của câu vừa thêm sau khi sort).

    Raises:
        GateError: gate không hỗ trợ, text rỗng, hoặc thời gian không hợp lệ.
    """
    if gate not in MANUAL_ADD_GATES:
        raise GateError(f"Chốt '{gate}' không hỗ trợ thêm câu thủ công")
    text = (text or "").strip()
    if not text:
        raise GateError("Nội dung câu không được để trống")
    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError):
        raise GateError("Mốc thời gian phải là số (giây)") from None
    if start < 0 or end < 0:
        raise GateError("Mốc thời gian không được âm")
    if end <= start:
        raise GateError("Thời điểm kết thúc phải sau thời điểm bắt đầu")

    path = gate_file_path(job, gate)
    data = _read_json(path)
    array_key = GATE_ARRAY_KEY[gate]
    field = EDITABLE_FIELD[gate]
    segments = data.get(array_key, [])

    new_seg: dict = {"start": start, "end": end}
    if gate == GATE_SCRIPT:
        new_seg["source_text"] = ""  # ASR bỏ sót nên không có câu gốc để đối chiếu
    new_seg[field] = text

    segments.append(new_seg)
    # sort giữ nguyên tham chiếu các object — `is` bên dưới vẫn tìm được câu mới
    segments.sort(key=lambda s: (float(s.get("start") or 0.0), float(s.get("end") or 0.0)))
    data[array_key] = segments

    if gate == GATE_SCRIPT:
        data["content"] = " ".join(s.get(field) or "" for s in segments)

    _write_json(path, data)

    new_index = next((i for i, s in enumerate(segments) if s is new_seg), len(segments) - 1)
    return len(segments), new_index


# ─── Trạng thái chốt trong job.json ──────────────────────────────────────────


def mark_reached(job: dict, gate: str, segment_count: int) -> dict:
    """
    Ghi nhận pipeline vừa dừng ở chốt. Sửa `job` tại chỗ và trả về chính nó —
    chỗ gọi tự lo persist (thường qua `update_job_status()`).

    Gọi lại lần nữa cho cùng chốt (sinh lại kịch bản) sẽ làm mới `reached_at` và
    reset `approved_at` — chốt đó phải được duyệt lại.
    """
    gates = job.setdefault("review_gates", {})
    entry = gates.setdefault(gate, {})
    entry.update(
        {
            "reached_at": _now_iso(),
            "approved_at": None,
            "segment_count": segment_count,
            "edited": entry.get("edited", False),
        }
    )
    if gate == GATE_SCRIPT:
        entry.setdefault("regenerated_count", 0)
    job["review_gate"] = gate
    return job


def mark_edited(job: dict, gate: str, segment_count: int) -> dict:
    """Ghi nhận có ≥1 lượt lưu bản sửa ở chốt."""
    entry = job.setdefault("review_gates", {}).setdefault(gate, {})
    entry["edited"] = True
    entry["segment_count"] = segment_count
    return job


def mark_approved(job: dict, gate: str) -> dict:
    """
    Ghi nhận chốt đã được duyệt. `approved_at` là bằng chứng audit rằng chốt đã
    qua, và là cái chặn retry/resume đưa job về chốt đó lần nữa (FR-023).
    """
    entry = job.setdefault("review_gates", {}).setdefault(gate, {})
    entry["approved_at"] = _now_iso()
    job["review_gate"] = None
    return job


def mark_regenerated(job: dict) -> dict:
    """Ghi nhận một lượt sinh lại kịch bản (FR-020) — chỉ có ở chốt kịch bản."""
    entry = job.setdefault("review_gates", {}).setdefault(GATE_SCRIPT, {})
    entry["regenerated_count"] = int(entry.get("regenerated_count", 0)) + 1
    entry["approved_at"] = None
    entry["edited"] = False
    job["review_gate"] = None
    return job


# ─── Vùng phụ đề gốc do người dùng tự khoanh (009) ───────────────────────────


def save_hardsub_box(job: dict, box: dict) -> None:
    """
    Lưu vùng phụ đề gốc người dùng vừa khoanh tay trên khung hình đại diện
    (thay cho OCR tự động — xem hardsub/detector.py). Chỉ ghi vào job dict,
    chỗ gọi tự persist.

    `hardsub_regions.json` thật sự được dựng (`hardsub.detector.
    build_manual_regions()`) lúc PHÊ DUYỆT chốt lời thoại (web/backend/
    review_api.py), vì lúc đó mới chốt cả vùng lẫn `hardsub_no_ranges` cuối
    cùng — người dùng có thể chỉnh lại nhiều lượt trước đó.
    """
    job["hardsub_box"] = box


def is_approved(job: dict, gate: str) -> bool:
    """Chốt đã được duyệt chưa — dùng để không dừng lại lần hai sau retry."""
    return bool(job.get("review_gates", {}).get(gate, {}).get("approved_at"))

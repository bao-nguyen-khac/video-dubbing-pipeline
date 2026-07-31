# Implementation Plan: Chế độ quản lý pipeline (dừng chờ duyệt từng bước)

**Branch**: `008-supervised-pipeline` | **Date**: 2026-07-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-supervised-pipeline/spec.md`

## Summary

Thêm một công tắc `supervised` lúc tạo job. Job bật công tắc này sẽ dừng đúng 2
lần — sau bước `transcribing` và sau bước `scripting` — ở một trạng thái mới
`awaiting_review`, chờ người dùng review/sửa nội dung từng câu trên web rồi bấm
phê duyệt để chạy tiếp.

Cách làm dựa hoàn toàn vào cơ chế đã có: `pipeline.run_pipeline()` vốn dispatch
theo `job["status"]` và resume được từ bước dở dang, nên "dừng ở chốt" chỉ là ghi
`status="awaiting_review"` rồi `return` sớm, và "phê duyệt" chỉ là ghi status về
bước kế tiếp rồi gọi lại `start_job()` với cùng `job_id`. Trạng thái bền vững
miễn phí vì đã nằm trong `jobs/{job_id}/job.json`. Không thêm hàng đợi, không
thêm tiến trình nền, không thêm dependency.

Hai điểm cần xử lý cẩn thận (chi tiết ở [research.md](./research.md)):

1. **Nội dung sửa ở chốt 1 phải không bị `resegment_by_sentences()` ghi đè.**
   Hàm này dựng lại segment từ mảng `words` của transcript, nên nếu chỉ sửa
   `text` thì phần sửa bị mất ở bước scripting. Giải pháp: với job supervised,
   chạy resegment NGAY TRƯỚC chốt 1 và ghi ra `transcript_reviewed.json` đã
   **bỏ `words`** — người dùng review đúng câu theo ranh giới câu, và bước
   scripting sau đó tự bỏ qua resegment (vì thiếu `words`) nên giữ nguyên phần
   sửa. Job không supervised chạy y như cũ.
2. **Job chờ duyệt phải không chiếm suất.** `find_running_job_id()` hiện coi
   "mọi status ngoài done/failed" là đang chạy → phải loại thêm
   `awaiting_review` (FR-021).

## Technical Context

**Language/Version**: Python 3.11 (backend + pipeline, `requires-python >=3.11`);
TypeScript 6 + React 19 (frontend, Vite 8)

**Primary Dependencies**: FastAPI + uvicorn (web backend), pydantic (request
model), react-router-dom 7 (frontend routing). Không thêm dependency mới.

**Storage**: file trên đĩa, không DB — `jobs/{job_id}/job.json` (state máy trạng
thái + field mới `supervised`/`review_gate`/`review_gates`),
`jobs/{job_id}/transcript_reviewed.json` (payload chốt 1, mới),
`jobs/{job_id}/script.json` (payload chốt 2, sửa tại chỗ),
`jobs/{job_id}/script_original.json` (bản gốc trước khi sửa tay, mới)

**Testing**: pytest (`tests/unit/`) với `fastapi.testclient.TestClient` +
`monkeypatch` `JOBS_DIR` sang `tmp_path`; mọi lượt gọi LLM/TTS trong test MUST
được mock (Constitution VI)

**Target Platform**: Linux server (Docker `python:3.11-slim`) hoặc chạy trực tiếp
bằng `uvicorn web.backend.main:app`; frontend là static build trong browser

**Project Type**: web application (FastAPI backend + React SPA) trên nền pipeline
CLI Python

**Performance Goals**: không có yêu cầu throughput mới. Endpoint review chỉ đọc/
ghi 1–2 file JSON nhỏ (vài chục KB) → phản hồi tức thời. Riêng lượt vào chốt 1
tốn thêm 1 lượt gọi LLM chèn dấu câu — nhưng là lượt gọi **đã có sẵn** trong
bước scripting, chỉ chuyển sang chạy sớm hơn, không phát sinh chi phí mới.

**Constraints**: (a) job không bật supervised MUST giữ nguyên 100% hành vi hiện
tại, kể cả job.json tạo trước feature này (đọc field mới bằng `.get()` có
default); (b) chỉ 1 job xử lý thật tại một thời điểm — quy tắc cũ giữ nguyên,
job chờ duyệt là ngoại lệ duy nhất; (c) không thêm ngôn ngữ runtime ngoài Python
ở backend/pipeline (Constitution I).

**Scale/Scope**: 1 người dùng, ~vài chục job trên đĩa, mỗi chốt hiển thị cỡ
10–200 câu — đủ nhỏ để render toàn bộ bảng trong một trang, không cần phân trang
hay virtual scroll.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Kết quả | Ghi chú |
|---|---|---|
| I. Python-Only Stack | ✅ PASS | Toàn bộ logic chốt (pipeline + API) bằng Python; phần UI review là React — đúng ngoại lệ tường minh cho frontend |
| II. Source-First Downloading | ✅ N/A | Feature không chạm bước download |
| III. On-Demand AI Cleanup | ✅ N/A | Không chạm `clean_video/` |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS | plan/research/data-model/contracts/quickstart là markdown thuần, tự đủ nghĩa, không phụ thuộc cơ chế Claude Code |
| V. Token & Context Economy | ✅ PASS | 0 dependency mới, 0 hạ tầng mới; tái dùng `run_pipeline()` dispatch-theo-status + `start_job()` sẵn có thay vì viết engine workflow mới |
| VI. Agentic Harness Discipline | ✅ PASS | Trạng thái mỗi chốt truy vết được qua `job.json` + file JSON trung gian (audit được bước trước); test cho endpoint `regenerate` MUST mock LLM (không gọi 9router thật); feature không chạm TTS trả phí và không chạm Zernio |
| Technology Stack (locked) | ✅ PASS | Không thêm/đổi dòng nào trong bảng → không cần amend constitution |
| Project Structure | ⚠️ Mở rộng | Thêm 1 thư mục top-level `review/` (helper đọc/ghi/validate payload chốt) và 1 file `web/backend/review_api.py`. Đây là phần "Project Structure" chứ không phải bảng "Technology Stack (Locked Decisions)" → không cần amend; lý do cần top-level: `pipeline.py` phải import helper này, nên nó KHÔNG được nằm trong `web/backend/` (sẽ đảo chiều phụ thuộc pipeline → web) |

**Post-Phase-1 re-check**: ✅ PASS — thiết kế Phase 1 không thêm dependency,
không thêm tiến trình nền, không đổi công nghệ đã chốt. Xem
[Complexity Tracking](#complexity-tracking).

## Project Structure

### Documentation (this feature)

```text
specs/008-supervised-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.md           # Phase 1 output — 4 endpoint review
├── checklists/          # (đã có từ /speckit-checklist)
└── tasks.md             # Phase 2 output (/speckit-tasks — KHÔNG tạo ở lệnh này)
```

### Source Code (repository root)

```text
media-generation/
├── pipeline.py                       # SỬA: + status "awaiting_review", + VALID_TRANSITIONS,
│                                     #   + field supervised/review_gate/review_gates trong create_job(),
│                                     #   + 2 điểm dừng (sau transcribing, sau scripting),
│                                     #   + scripting đọc transcript_reviewed.json khi có,
│                                     #   + CLI flag --supervised
├── review/                           # MỚI — helper chốt kiểm duyệt (dùng chung pipeline + backend)
│   ├── __init__.py
│   └── gates.py                      #   build payload chốt, lưu bản sửa, validate (FR-013/FR-014)
├── script_gen/sentence_segmenter.py  # KHÔNG SỬA — tái dùng resegment_by_sentences() nguyên trạng
├── web/backend/
│   ├── main.py                       # SỬA: include_router(review_router, prefix="/api/jobs")
│   ├── jobs_api.py                   # SỬA: find_running_job_id() loại awaiting_review (FR-021),
│   │                                 #   status_to_progress()/_job_to_detail() biết chốt,
│   │                                 #   SubmitJobRequest + supervised
│   ├── job_runner.py                 # SỬA: start_job() truyền supervised xuống run_pipeline()
│   └── review_api.py                 # MỚI — GET/PUT review, POST approve, POST regenerate
├── web/frontend/src/
│   ├── api/client.ts                 # SỬA: + type ReviewPayload, + 4 hàm gọi API, + field JobDetail
│   ├── components/
│   │   ├── StatusBadge.tsx           # SỬA: awaiting_review là nhóm riêng (không phải running/failed)
│   │   ├── JobProgress.tsx           # SỬA: hiện "đang chờ duyệt tại chốt X"
│   │   └── ReviewGatePanel.tsx       # MỚI — bảng câu sửa được + Lưu / Phê duyệt / Sinh lại
│   ├── pages/HomePage.tsx            # SỬA: + checkbox "Quản lý pipeline" (mặc định tắt)
│   ├── pages/JobDetailPage.tsx       # SỬA: render ReviewGatePanel khi status=awaiting_review
│   └── pages/JobListPage.tsx         # SỬA: nhãn "chờ duyệt" phân biệt với đang xử lý (FR-006)
└── tests/unit/
    ├── test_review_gates.py          # MỚI — build payload, bỏ câu rỗng, chặn rỗng toàn bộ
    ├── test_review_api.py            # MỚI — GET/PUT/approve/regenerate + 409 (FR-018/FR-019)
    └── test_supervised_pipeline.py   # MỚI — transition + job không supervised không đổi hành vi
```

**Structure Decision**: giữ đúng layout đã có trong Constitution → Project
Structure. Logic chốt tách thành module top-level `review/` vì cả `pipeline.py`
(ghi payload lúc dừng) và `web/backend/review_api.py` (đọc/ghi lúc người dùng
sửa) đều cần — đặt trong `web/backend/` sẽ buộc `pipeline.py` import từ tầng web.
Toàn bộ endpoint mới nằm dưới prefix `/api/jobs` đã có nên đi qua đúng auth
middleware hiện tại, không cần thêm ngoại lệ auth.

## Complexity Tracking

> Constitution Check không có vi phạm cần biện minh. Bảng dưới ghi lại 2 lựa
> chọn đã cân nhắc để tránh thêm phức tạp không cần thiết.

| Lựa chọn | Vì sao cần | Phương án đơn giản hơn bị loại vì |
|---|---|---|
| 1 status `awaiting_review` + field `review_gate` (thay vì 2 status riêng) | Phân biệt được đang chờ ở chốt nào mà chỉ thêm 1 nhánh vào state machine | 2 status riêng (`awaiting_transcript_review`/`awaiting_script_review`) nhân đôi số nhánh phải thêm ở `VALID_TRANSITIONS`, `_STATUS_PROGRESS_MAP`, `find_running_job_id()`, `delete_job()` và cả 3 component frontend — nhiều chỗ sửa hơn cho cùng một thông tin |
| Thư mục top-level `review/` (thay vì để trong `web/backend/`) | `pipeline.py` cần ghi payload lúc dừng ở chốt | Để trong `web/backend/` khiến `pipeline.py` (tầng pipeline) import tầng web — đảo chiều phụ thuộc, và làm CLI `pipeline.py` không chạy được nếu chưa cài FastAPI |

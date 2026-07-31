---

description: "Task list — 008-supervised-pipeline (Chế độ quản lý pipeline)"
---

# Tasks: Chế độ quản lý pipeline (dừng chờ duyệt từng bước)

**Input**: Design documents from `/specs/008-supervised-pipeline/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: CÓ. Constitution VI yêu cầu mỗi task chỉ được đánh dấu hoàn thành khi
verify được bằng bằng chứng cụ thể, và plan.md đã chốt 3 file test. Mọi test MUST
mock lượt gọi LLM/HTTP — KHÔNG test nào gọi thật 9router, Vivibe, hay Zernio.

**Organization**: Tasks nhóm theo user story để triển khai và kiểm chứng độc lập.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: chạy song song được (file khác nhau, không phụ thuộc task chưa xong)
- **[Story]**: user story tương ứng (US1/US2/US3/US4)
- Mọi task ghi rõ đường dẫn file

## Path Conventions

Dự án này là **web app trên nền pipeline CLI Python** — đường dẫn thật, không có
`src/`:

- Pipeline & module xử lý: `pipeline.py`, `review/`, `script_gen/`, `asr/`
- Backend: `web/backend/`
- Frontend: `web/frontend/src/`
- Test: `tests/unit/`

## ⚠ Hai bất biến MUST giữ suốt mọi task

1. **KHÔNG thêm `words` vào `transcript_reviewed.json`** — nó là điều kiện đúng
   đắn của cả feature ([research.md](./research.md) §3). Có `words` ⟹ phần sửa tay
   bị `resegment_by_sentences()` ghi đè âm thầm ở bước scripting.
2. **Đường đi của job KHÔNG bật `supervised` phải không thêm một nhánh runtime
   nào** — mọi logic chốt nằm trong `if supervised:`, mọi field mới đọc bằng
   `.get()` có default (FR-002, SC-001).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dựng chỗ chứa code mới và mốc hồi quy để so sánh về sau

- [X] T001 Tạo package `review/` với `review/__init__.py` (rỗng) và `review/gates.py` chỉ có module docstring nêu rõ vai trò: helper chốt kiểm duyệt dùng chung cho `pipeline.py` và `web/backend/review_api.py`, MUST NOT import gì từ `web/`
- [X] T002 [P] Thêm fixture `tmp_jobs_dir` vào `tests/unit/conftest.py` — monkeypatch `pipeline.JOBS_DIR` và `web.backend.jobs_api.JOBS_DIR` sang `tmp_path`, kèm helper tạo `job.json` + `transcript.json` + `script.json` giả để mọi test sau dùng lại (không test nào được ghi vào `jobs/` thật)
- [X] T003 [P] Chạy `./venv/bin/python -m pytest tests/ -q` và lưu output làm mốc hồi quy baseline (số test pass hiện tại) vào phần ghi chú của PR/commit

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: State machine + module chốt + kiểu dữ liệu API/frontend mà CẢ 4 story đều cần

**⚠️ CRITICAL**: Không story nào bắt đầu được trước khi phase này xong

- [X] T004 Trong `pipeline.py`: thêm `"awaiting_review"` vào `StatusLiteral`, và sửa đúng 3 dòng `VALID_TRANSITIONS` theo bảng ở [data-model.md](./data-model.md) §1 — `transcribing` +`awaiting_review`, `scripting` +`awaiting_review`, thêm khoá mới `"awaiting_review": ["scripting", "synthesizing", "failed"]`
- [X] T005 Trong `pipeline.py` `create_job()`: thêm tham số `supervised: bool = False` và các field `supervised`, `review_gate: None`, `review_gates: {}`, cùng khoá `artifacts["transcript_reviewed"] = None` ([data-model.md](./data-model.md) §2)
- [X] T006 Trong `review/gates.py`: implement lõi dùng chung — `GATE_TRANSCRIPT`/`GATE_SCRIPT`, `build_payload(job, gate)`, `save_edits(job, gate, edits)`, `mark_reached(job, gate, segment_count)`, `mark_approved(job, gate)`. `save_edits()` MUST bỏ câu có nội dung rỗng/chỉ khoảng trắng (FR-013), MUST raise `EmptyGateError` khi sau khi lọc không còn câu nào và **không ghi file** (FR-014), và MUST bỏ qua `start`/`end`/`source_text` client gửi lên (FR-016). Chỉ chứa logic thuần trên dict/file — KHÔNG import FastAPI
- [X] T007 [P] Trong `tests/unit/test_review_gates.py`: test `save_edits()` bỏ câu rỗng và trả đúng `saved_count`/`dropped_count`; test `EmptyGateError` khi rỗng toàn bộ **và file trên đĩa không đổi**; test `start`/`end` client gửi lên bị bỏ qua; test `index` không tồn tại raise lỗi rõ ràng
- [X] T008 Trong `web/backend/jobs_api.py`: `status_to_progress()` trả 40 khi `review_gate == "transcript"` và 56 khi `"script"`; `_job_to_summary()` thêm `review_gate`; `_job_to_detail()` thêm `supervised` + `review_url` ([data-model.md](./data-model.md) §7). `can_retry` giữ nguyên `status == "failed"`
- [X] T009 Tạo `web/backend/review_api.py`: `router = APIRouter()`, `_APPROVE_LOCK = threading.Lock()` cấp module, và guard dùng chung `_load_awaiting_job(job_id, gate)` trả 404 khi job không tồn tại / 409 khi `status != "awaiting_review"` / 409 khi gate không khớp — đúng nguyên văn message ở [contracts/api.md](./contracts/api.md) §2–§4. Chưa cần endpoint nào
- [X] T010 Trong `web/backend/main.py`: `from web.backend.review_api import router as review_router` và `app.include_router(review_router, prefix="/api/jobs")` (đặt SAU `jobs_router` để không che route `/{job_id}` hiện có)
- [X] T011 [P] Trong `web/frontend/src/lib/labels.ts`: thêm `awaiting_review: "Chờ duyệt"` vào `STATUS_LABELS`; mở rộng `StatusKind` thêm `"waiting"` và cho `statusKind()` trả `"waiting"` cho `awaiting_review`; thêm `REVIEW_GATE_LABELS = { transcript: "chốt lời thoại", script: "chốt kịch bản" }`; `stageStates()` coi bước tương ứng là `"active"` chứ không phải `"failed"` khi status là `awaiting_review`
- [X] T012 [P] Trong `web/frontend/src/api/client.ts`: thêm `review_gate` vào `JobSummary`; `supervised` + `review_url` vào `JobDetail`; thêm `supervised?: boolean` vào tham số `submitJob()`; thêm interface `ReviewSegment`/`ReviewPayload` và 4 hàm `getReview()`, `saveReview()`, `approveReview()`, `regenerateScript()` khớp [contracts/api.md](./contracts/api.md)
- [X] T013 Trong `web/backend/job_runner.py`: `start_job()` + `_run_and_swallow_exit()` thêm tham số `supervised: bool = False` truyền xuống `run_pipeline()`; trong `pipeline.py` `run_pipeline()` thêm tham số `supervised: bool = False` nhưng giá trị dùng thật MUST đọc từ `job.get("supervised", False)` sau khi load job (cùng khuôn mẫu `active_dynamic_captions` ở `pipeline.py:577` — [research.md](./research.md) §11)

**Checkpoint**: State machine chấp nhận `awaiting_review`, module chốt có test xanh, frontend biết nhãn mới. Chưa có điểm dừng nào thực sự xảy ra.

---

## Phase 3: User Story 1 — Duyệt và tinh chỉnh lời thoại đã tách (Priority: P1) 🎯 MVP

**Goal**: Job bật chế độ quản lý dừng sau bước tách lời, người dùng sửa nội dung câu trên web, lưu, phê duyệt, và các bước sau dùng đúng nội dung đã sửa.

**Independent Test**: Tạo 1 job bật chế độ quản lý → job dừng sau tách lời và KHÔNG tự chạy tiếp → sửa 1 câu → phê duyệt → nội dung đã sửa xuất hiện ở sản phẩm cuối. Dùng được trọn vẹn kể cả khi chốt kịch bản (US2) chưa làm.

### Tests for User Story 1 ⚠️

> Viết trước, xác nhận FAIL trước khi implement

- [X] T014 [P] [US1] Trong `tests/unit/test_supervised_pipeline.py`: test `create_job(supervised=True)` ghi đúng field mới; test transition `transcribing → awaiting_review` hợp lệ và `review_gate="transcript"`; test job `supervised=False` KHÔNG bao giờ vào `awaiting_review`; test `job.json` cũ (thiếu mọi field mới) đọc được qua `_job_to_detail()` không lỗi
- [X] T015 [P] [US1] Trong `tests/unit/test_review_api.py`: test `GET /api/jobs/{id}/review` ở gate `transcript` trả `editable_field="text"`, `source_text=null`, `can_regenerate=false`; test `segments: []` là 200 chứ không phải lỗi; test `PUT` lưu thành công không đổi status; test `PUT` rỗng toàn bộ trả 400 và file không đổi; test `POST approve` lần 1 → 202, lần 2 → 409 (FR-019); test 409 khi `status != "awaiting_review"`. Monkeypatch `web.backend.review_api.start_job` để không chạy pipeline thật

### Implementation for User Story 1

- [X] T016 [US1] Trong `web/backend/jobs_api.py`: `SubmitJobRequest` thêm `supervised: bool = False`; truyền xuống `create_job(..., supervised=body.supervised)` và `start_job(..., supervised=body.supervised)`; `retry_job()` truyền `supervised=job.get("supervised", False)` ([contracts/api.md](./contracts/api.md) §1)
- [X] T017 [US1] Trong `pipeline.py` `parse_args()`: thêm flag `--supervised` (`action="store_true"`) với help text đúng như [contracts/api.md](./contracts/api.md) §7, và truyền vào `run_pipeline()` ở `__main__`
- [X] T018 [US1] Trong `pipeline.py` bước transcribing (sau `transcribe()` thành công, TRƯỚC `update_job_status(jid, "scripting")`): nếu `supervised` → gọi `resegment_by_sentences(transcript["segments"], _chat_completion)`, lược mỗi segment còn đúng `start`/`end`/`text` (**bỏ `words`**), ghi `jobs/{jid}/transcript_reviewed.json` theo schema [data-model.md](./data-model.md) §3, gọi `review.gates.mark_reached(job, "transcript", n)`, rồi `update_job_status(jid, "awaiting_review", artifacts_update={"transcript_reviewed": ...})` + in 2 dòng log ở [contracts/api.md](./contracts/api.md) §7 và `return` (KHÔNG `sys.exit(2)` — dừng chờ duyệt không phải lỗi)
- [X] T019 [US1] Trong `pipeline.py` bước scripting: đọc transcript từ `job["artifacts"].get("transcript_reviewed") or job["artifacts"]["transcript"]` cho cả `generate_script()` và `generate_subtitle_script()` — đây là chỗ FR-012 thành hiện thực
- [X] T020 [US1] Trong `web/backend/review_api.py`: `GET /{job_id}/review` — dùng `_load_awaiting_job()` + `review.gates.build_payload()`, trả đúng shape [contracts/api.md](./contracts/api.md) §2
- [X] T021 [US1] Trong `web/backend/review_api.py`: `PUT /{job_id}/review` — validate `gate`, gọi `save_edits()`, map `EmptyGateError` → 400 với message ở [contracts/api.md](./contracts/api.md) §3, cập nhật `review_gates[gate].edited=true` + `segment_count`, trả `saved_count`/`dropped_count`. MUST NOT đổi `status`
- [X] T022 [US1] Trong `web/backend/review_api.py`: `POST /{job_id}/review/approve` — trong `_APPROVE_LOCK`, theo đúng thứ tự 6 bước ở [contracts/api.md](./contracts/api.md) §4; gate `transcript` → `status="scripting"`; ghi `review_gate=None` + `mark_approved()`; `start_job()` gọi NGOÀI lock
- [X] T023 [P] [US1] Tạo `web/frontend/src/components/ReviewGatePanel.tsx` — bảng câu: cột mốc `start–end` read-only (FR-016), `<textarea>` nội dung sửa được, nút *Lưu* và *Phê duyệt*; state `dirty` khi có thay đổi chưa lưu; hiện rõ "Không có câu nào" khi `segments: []`; hiện thông báo lỗi 400/409 từ `ApiError.body.error` mà KHÔNG xoá nội dung đang sửa
- [X] T024 [US1] Trong `web/frontend/src/pages/JobDetailPage.tsx`: render `<ReviewGatePanel>` khi `status === "awaiting_review"`; **tạm dừng poll** khi panel đang mở (poll 3s sẽ đè lên nội dung người dùng đang sửa) và poll lại sau khi phê duyệt thành công; chặn bấm *Phê duyệt* khi còn thay đổi chưa lưu bằng `window.confirm` (FR-015)
- [X] T025 [P] [US1] Trong `web/frontend/src/pages/HomePage.tsx`: thêm checkbox "Quản lý pipeline" (mặc định **tắt**, FR-002) kèm mô tả ngắn "Dừng lại cho tôi duyệt sau bước tách lời và sau bước sinh kịch bản", dùng cùng markup `<label className="switch">` như `dynamicCaptions`; truyền `supervised` vào `submitJob()`
- [X] T026 [P] [US1] Trong `web/frontend/src/pages/JobListPage.tsx` và `web/frontend/src/components/JobProgress.tsx`: hiển thị "Chờ duyệt tại {REVIEW_GATE_LABELS[review_gate]}" phân biệt rõ với đang xử lý và với lỗi (FR-006); thêm style `badge--waiting` vào `web/frontend/src/App.css` (màu khác hẳn nhóm running/failed)
- [X] T027 [US1] Verify Scenario A trong [quickstart.md](./quickstart.md): chạy 1 job thật ngắn với `edge-tts`, xác nhận dừng ở chốt 1, sửa 1 câu, phê duyệt, và chạy đúng lệnh kiểm chứng `transcript_reviewed.json` MUST in ra `False` cho `'words' in segments[0]`. Lưu output làm bằng chứng

**Checkpoint**: US1 dùng được trọn vẹn — đây là MVP. Job chờ duyệt VẪN đang chiếm suất (US3 chưa làm) nên phải phê duyệt hoặc xoá job trước khi submit job mới.

---

## Phase 4: User Story 2 — Duyệt và tinh chỉnh kịch bản (Priority: P2)

**Goal**: Sau chốt lời thoại, job dừng lần hai sau bước sinh kịch bản; người dùng đối chiếu câu dịch với câu gốc, sửa, phê duyệt, rồi hệ thống đọc giọng + ghép.

**Independent Test**: Với job đã qua chốt lời thoại, xác nhận job dừng lần hai sau sinh kịch bản; sửa một câu dịch, phê duyệt, kiểm tra giọng đọc/phụ đề ở sản phẩm cuối khớp nội dung đã sửa.

### Tests for User Story 2 ⚠️

- [X] T028 [P] [US2] Trong `tests/unit/test_supervised_pipeline.py`: test transition `scripting → awaiting_review` với `review_gate="script"`; test bất biến "`script.approved_at != null` ⟹ `transcript.approved_at != null`" ([data-model.md](./data-model.md) §2)
- [X] T029 [P] [US2] Trong `tests/unit/test_review_api.py`: test `GET review` ở gate `script` trả `editable_field="translated_text"`, `source_text` có giá trị, `can_regenerate=true`; test `PUT` ghi vào `translated_text` và **tính lại** `content`; test `PUT` lần đầu tạo `script_original.json`, lần thứ hai KHÔNG ghi đè bản lưu đó; test `approve` gate `script` → `status="synthesizing"`

### Implementation for User Story 2

- [X] T030 [US2] Trong `review/gates.py`: bổ sung nhánh gate `script` cho `build_payload()` (đọc `script.json`, map `translated_text` → `text` và giữ `source_text`) và cho `save_edits()` (ghi vào `translated_text`, tính lại `content` bằng `" ".join(...)` khớp `router_client.py:371`, tạo `script_original.json` một lần trước lượt sửa đầu tiên — [data-model.md](./data-model.md) §4–§5)
- [X] T031 [US2] Trong `pipeline.py` bước scripting (sau khi có `script_path`, TRƯỚC `update_job_status(jid, "synthesizing")`): nếu `supervised` → `mark_reached(job, "script", n)` + `update_job_status(jid, "awaiting_review", artifacts_update={"script": ...})` + log + `return`
- [X] T032 [US2] Trong `web/backend/review_api.py` `approve`: nhánh gate `script` → `status="synthesizing"` (dùng chung toàn bộ guard/lock đã có từ T022, không viết luồng thứ hai)
- [X] T033 [US2] Trong `web/frontend/src/components/ReviewGatePanel.tsx`: khi `source_text != null`, mỗi dòng hiện câu gốc (read-only, chữ mờ hơn) cạnh câu dịch sửa được (FR-010); layout xuống một cột trên màn hình hẹp
- [X] T034 [US2] Verify Scenario B trong [quickstart.md](./quickstart.md) với `script_mode="translate"`, rồi **lặp lại với `script_mode="subtitle"`** để xác nhận cả 2 chốt vẫn áp dụng và phụ đề burn ra khớp nội dung đã sửa (US2 scenario 4). Xác nhận `script_original.json` chứa bản dịch trước khi sửa

**Checkpoint**: US1 + US2 đều chạy độc lập; job supervised dừng đúng 2 lần (SC-002).

---

## Phase 5: User Story 3 — Làm việc khác trong lúc job đang chờ duyệt (Priority: P2)

**Goal**: Job chờ duyệt không chiếm suất "1 job tại một thời điểm"; bù lại, phê duyệt lúc có job khác đang xử lý bị từ chối kèm thông báo rõ ràng và không mất nội dung đã sửa.

**Independent Test**: Để 1 job ở trạng thái chờ duyệt, submit job thứ hai và xác nhận job thứ hai chạy được; sau đó phê duyệt job thứ nhất trong lúc job thứ hai còn đang xử lý và xác nhận hệ thống từ chối kèm thông báo rõ ràng chứ không chạy chồng hai job.

### Tests for User Story 3 ⚠️

- [X] T035 [P] [US3] Trong `tests/unit/test_review_api.py`: test `find_running_job_id()` trả `None` khi job duy nhất đang `awaiting_review`; test `POST /api/jobs` trả 201 khi đang có job `awaiting_review` (SC-005); test `approve` trả 409 + `running_job_id` khi có job khác đang `synthesizing`, **và** job vẫn `awaiting_review` với `review_gate` cũ + nội dung đã lưu nguyên vẹn (FR-018); test `DELETE /api/jobs/{id}` trả 200 khi job đang `awaiting_review` (FR-022 — khẳng định hành vi sẵn có, không sửa code)

### Implementation for User Story 3

- [X] T036 [US3] Trong `web/backend/jobs_api.py` `find_running_job_id()`: đổi điều kiện thành `status not in ("done", "failed", "awaiting_review")` kèm comment nêu rõ lý do (FR-021: job chờ duyệt không tốn tài nguyên xử lý nên phải nhả suất) — [research.md](./research.md) §5
- [X] T037 [US3] Trong `web/backend/jobs_api.py` `delete_job()`: KHÔNG sửa blocklist (đã đúng), chỉ thêm comment nêu rõ `awaiting_review` cố ý xoá được (FR-022) để lần sau không ai "sửa cho đủ" thành chặn
- [X] T038 [US3] Trong `web/frontend/src/components/ReviewGatePanel.tsx`: khi `approveReview()` ném `ApiError` 409, hiện đúng message backend trả về kèm gợi ý "chờ job kia xong rồi bấm lại", giữ nguyên nội dung đang sửa và không đổi trạng thái panel
- [X] T039 [US3] Verify Scenario C trong [quickstart.md](./quickstart.md), gồm cả phép thử bấm *Phê duyệt* hai lần thật nhanh: log backend MUST NOT có hai lượt bắt đầu cùng một bước cho cùng job (FR-019)

**Checkpoint**: Chế độ quản lý đã an toàn để dùng thật — job chờ duyệt không còn khoá hệ thống.

---

## Phase 6: User Story 4 — Sinh lại kịch bản khi bản dịch không dùng được (Priority: P3)

**Goal**: Ở chốt kịch bản, người dùng bấm "sinh lại kịch bản" để dịch lại từ lời thoại đã duyệt, rồi job dừng lại đúng chốt đó để review bản mới.

**Independent Test**: Ở job đang chờ duyệt tại chốt kịch bản, bấm sinh lại → kịch bản có nội dung mới, job vẫn dừng tại chốt đó, và `transcript_reviewed.json` không bị thay đổi.

### Tests for User Story 4 ⚠️

- [X] T040 [P] [US4] Trong `tests/unit/test_review_api.py`: test `regenerate` xoá `script.json` + `script_original.json`, đặt `status="scripting"`, reset `review_gates.script.approved_at=null` + `edited=false`, tăng `regenerated_count`; test `transcript_reviewed.json` **không đổi**; test 409 khi `review_gate == "transcript"`. Monkeypatch `start_job` — MUST NOT gọi 9router thật (Constitution VI)

### Implementation for User Story 4

- [X] T041 [US4] Trong `web/backend/review_api.py`: `POST /{job_id}/review/regenerate` theo [contracts/api.md](./contracts/api.md) §5 — dùng chung `_APPROVE_LOCK` và `_load_awaiting_job()`, thêm guard `review_gate != "script"` → 409
- [X] T042 [US4] Trong `web/frontend/src/components/ReviewGatePanel.tsx`: nút *Sinh lại kịch bản* chỉ hiện khi `can_regenerate`; `window.confirm` cảnh báo rõ "các sửa tay ở chốt này sẽ bị ghi đè" TRƯỚC khi gọi API (FR-020, US4 scenario 2); sau 202 thì poll lại tới khi job về `awaiting_review` rồi tải payload mới
- [X] T043 [US4] Verify hàng "Sinh lại kịch bản" trong bảng Scenario F của [quickstart.md](./quickstart.md)

**Checkpoint**: Cả 4 user story hoạt động độc lập.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T044 Verify Scenario D ([quickstart.md](./quickstart.md)) — bền vững qua restart (SC-006, FR-007). **Nhờ người dùng tự restart hệ thống**, không tự chạy `docker compose`
- [X] T045 Verify Scenario E — hồi quy job KHÔNG bật chế độ quản lý (SC-001, FR-002): chạy 1 job thật liền mạch, kiểm `job.json` có `supervised: false`/`review_gate: null`/`review_gates: {}` và KHÔNG có `transcript_reviewed.json`; mở một job **cũ** tạo trước feature này ở cả danh sách và trang chi tiết
- [X] T046 Verify các hàng còn lại của bảng Scenario F — chế độ chỉ tải bật quản lý vẫn `done` (FR-008), bỏ câu rác (FR-013), rỗng toàn bộ (FR-014), sửa chưa lưu (FR-015), video không lời ([research.md](./research.md) §10), retry sau chốt không bắt duyệt lại (FR-023)
- [X] T047 [P] Cập nhật `README.md`: thêm `--supervised` vào phần mô tả CLI và một đoạn ngắn về chế độ quản lý pipeline trên web UI
- [X] T048 [P] Xác nhận KHÔNG có dependency mới: `git diff requirements.txt web/frontend/package.json` phải rỗng
- [X] T049 Chạy `./venv/bin/python -m pytest tests/ -q` — toàn bộ xanh, số test ≥ mốc baseline ở T003 cộng số test mới; đối chiếu checklist Definition of Done cuối [quickstart.md](./quickstart.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: không phụ thuộc — bắt đầu ngay
- **Foundational (Phase 2)**: sau Phase 1 — **BLOCK toàn bộ user story**
- **US1 (Phase 3)**: sau Phase 2
- **US2 (Phase 4)**: sau Phase 2. Kiểm chứng end-to-end (T034) cần một job đã qua chốt 1, nên **thực tế nên làm sau US1**; phần code (T030–T033) độc lập với US1
- **US3 (Phase 5)**: sau Phase 2, độc lập hoàn toàn với US1/US2 về code (chỉ chạm `jobs_api.py` + xử lý lỗi ở panel)
- **US4 (Phase 6)**: sau **US2** — sinh lại kịch bản chỉ tồn tại ở chốt kịch bản
- **Polish (Phase 7)**: sau các story muốn giao

### User Story Dependencies

- **US1 (P1)**: không phụ thuộc story nào. Tự nó đã đủ giá trị (spec: "Chặn được ở đây là tự nó đã đủ giá trị")
- **US2 (P2)**: dùng lại toàn bộ endpoint + panel của US1; không sửa lại chúng, chỉ thêm nhánh gate `script`
- **US3 (P2)**: độc lập — làm được trước cả US1 nếu muốn, nhưng chỉ có ý nghĩa khi đã có trạng thái chờ duyệt để thử
- **US4 (P3)**: phụ thuộc US2 (chốt kịch bản phải tồn tại)

### Within Each User Story

- Test viết trước và phải FAIL trước khi implement
- `review/gates.py` (logic thuần) trước endpoint; endpoint trước frontend
- Verify scenario end-to-end là task **cuối** của mỗi story

### Parallel Opportunities

- Phase 1: T002, T003 song song
- Phase 2: T007, T011, T012 song song với nhau (test / frontend labels / frontend types là 3 file khác nhau); T004–T006 và T008–T010 phải tuần tự vì cùng chạm `pipeline.py` / `web/backend/`
- Phase 3: T014, T015 song song; T023, T025, T026 song song (3 file frontend khác nhau) nhưng đều cần T012 xong
- Phase 5 gần như độc lập với Phase 3/4 → làm song song bởi người khác được
- Phase 7: T047, T048 song song

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Sau khi T004–T006 xong, chạy 3 task này song song (3 file khác nhau):
Task: "T007 Test review/gates.py trong tests/unit/test_review_gates.py"
Task: "T011 Nhãn awaiting_review trong web/frontend/src/lib/labels.ts"
Task: "T012 Kiểu + hàm gọi API review trong web/frontend/src/api/client.ts"
```

## Parallel Example: User Story 1

```bash
# Viết 2 file test trước (song song), xác nhận FAIL:
Task: "T014 Test transition supervised trong tests/unit/test_supervised_pipeline.py"
Task: "T015 Test endpoint review gate transcript trong tests/unit/test_review_api.py"

# Sau khi T012 + T020–T022 xong, 3 file frontend song song:
Task: "T023 ReviewGatePanel.tsx"
Task: "T025 Checkbox Quản lý pipeline trong pages/HomePage.tsx"
Task: "T026 Nhãn chờ duyệt trong pages/JobListPage.tsx + components/JobProgress.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 + US3)

1. Phase 1: Setup (T001–T003)
2. Phase 2: Foundational (T004–T013) — **CRITICAL, block mọi story**
3. Phase 3: US1 (T014–T027)
4. **DỪNG và VALIDATE**: Scenario A trong quickstart.md
5. Làm luôn Phase 5 (US3, T035–T039) trước khi giao — chỉ 4 task nhưng thiếu nó thì
   một job chờ duyệt bỏ đó sẽ khoá cả hệ thống, đúng cái bẫy spec đã cảnh báo ở US3
6. Deploy/demo

### Incremental Delivery

1. Setup + Foundational → nền tảng xong, hành vi hiện tại chưa đổi gì
2. US1 (+US3) → chốt lời thoại dùng được → **MVP**
3. US2 → đủ 2 chốt như spec mô tả
4. US4 → đường tắt sinh lại kịch bản
5. Phase 7 → hồi quy + tài liệu

Mỗi bước không phá bước trước: job không bật `supervised` chạy y như cũ ở **mọi**
mốc giao hàng (SC-001).

### Parallel Team Strategy

Hai người sau khi Phase 2 xong:

- Người A: US1 (Phase 3) → US2 (Phase 4) → US4 (Phase 6)
- Người B: US3 (Phase 5) → Phase 7 (T047, T048) → hỗ trợ verify các scenario

---

## Notes

- `[P]` = file khác nhau, không phụ thuộc task chưa xong
- Nhiều task chạm chung `pipeline.py`, `web/backend/jobs_api.py`,
  `web/backend/review_api.py`, `web/frontend/src/components/ReviewGatePanel.tsx` —
  các task đó **không** được `[P]`, làm tuần tự để tránh xung đột
- Xác nhận test FAIL trước khi implement
- Commit sau mỗi task hoặc mỗi nhóm hợp lý
- Mọi task chỉ đánh dấu hoàn thành khi có bằng chứng cụ thể — test pass, log, hoặc
  output kiểm tra được (Constitution VI)
- **Verify TTS chỉ dùng `edge-tts`**; KHÔNG gọi thật Vivibe/LucyAI (tốn credit thật
  của người dùng, phải hỏi trước từng lượt) và KHÔNG gọi thật Zernio

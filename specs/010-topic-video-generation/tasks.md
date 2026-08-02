---

description: "Task list — 010-topic-video-generation (Tạo video từ chủ đề bằng AI)"
---

# Tasks: Tạo video từ chủ đề bằng AI (script + ảnh + giọng đọc tự động)

**Input**: Design documents from `/specs/010-topic-video-generation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: CÓ. Constitution VI yêu cầu mỗi task chỉ được đánh dấu hoàn thành khi
verify được bằng bằng chứng cụ thể. Mọi unit test MUST mock 9router/Pexels/
`npx hyperframes`/`ffprobe`/TTS provider thật — KHÔNG test nào phụ thuộc dịch
vụ ngoài thật (CI phải xanh mà không cần key/binary nào cài sẵn).

**Organization**: Tasks nhóm theo user story để triển khai và kiểm chứng độc lập.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: chạy song song được (file khác nhau, không phụ thuộc task chưa xong)
- **[Story]**: user story tương ứng (US1/US2/US3/US4)
- Mọi task ghi rõ đường dẫn file

## Path Conventions

Web app trên nền pipeline CLI Python — đường dẫn thật, không có `src/`:

- Orchestrator mới: `generate_pipeline.py` (repo root, song song `pipeline.py`)
- Module xử lý: `script_gen/`, `assets/` (mới), `tts/`, `merge/`, `review/`
- Backend: `web/backend/`
- Frontend: `web/frontend/src/`
- Test: `tests/unit/`

## ⚠ Ba ràng buộc MUST giữ suốt mọi task

1. **Constitution ĐÃ amend đủ 2 dòng** (HyperFrames v1.11.0, Pexels v1.12.0) —
   không cần amend thêm cho phạm vi tasks.md này. Nhưng **spike HyperFrames
   (T002) MUST xong TRƯỚC** mọi task viết `merge/hyperframes_renderer.py`
   (research.md §5) — không suy đoán cú pháp `data-*`/cấu trúc project.
2. **`job_type` là discriminator, KHÔNG migrate job cũ** — mọi chỗ đọc field
   này MUST dùng `.get("job_type", "dub")`; job.json không có field này MẶC
   ĐỊNH là luồng dub, không được coi là lỗi/thiếu dữ liệu.
3. **Chốt duyệt outline/scene (`GATE_OUTLINE`) TÁI DÙNG `review/gates.py`
   nguyên vẹn** — không viết review-gate riêng cho luồng generate; mọi khác
   biệt (key `"scenes"` thay vì `"segments"`) xử lý bằng cách mở rộng gate-aware
   mapping trong `review/gates.py`, không nhân bản logic sang module khác.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Xác nhận điều kiện tiên quyết, dựng chỗ chứa code, baseline hồi quy

- [X] T001 ✅ **ĐÃ HOÀN TẤT** — Constitution đã amend đủ 2 dòng Technology Stack: HyperFrames (v1.11.0) và Pexels (v1.12.0). `PEXELS_API_KEY` đã có trong `.env.example`. Không có việc gì thêm ở task này.
- [X] T002 ✅ **ĐÃ HOÀN TẤT** (2026-08-01) — Spike chạy thật: `init` blank/portrait, viết composition 2-scene tay, `lint` sạch, `render --quality standard --output output.mp4` ra file MP4 thật (`ffprobe`: duration=5.8s khớp root, có h264+aac). Kết quả ghi ở [research.md](./research.md) §5b: cú pháp `data-*` xác nhận, cảnh báo `HYPERFRAMES_SKIP_SKILLS=1` bắt buộc, quyết định KHÔNG chạy `init` mỗi job mà dùng template copy sẵn.
- [X] T003 [P] ✅ Thêm `ROUTER_AGENT_MODEL` vào `.env.example` (để trống = fallback `ROUTER_MODEL`) — biến mới cho model 9router có tool-use dùng ở bước outline (research.md §3)
- [X] T004 [P] ✅ Tạo package `assets/` với `assets/__init__.py` (docstring: nguồn ẢNH MINH HOẠ cho feature 010, khác `downloader/` — đó là tải VIDEO NGUỒN) và `assets/pexels_client.py` chỉ có module docstring
- [X] T005 [P] ✅ Tạo `merge/hyperframes_renderer.py` chỉ có module docstring (vai trò: sinh HTML timeline từ Scene JSON + gọi `npx hyperframes render`)
- [X] T006 [P] ✅ Tạo `script_gen/topic_script_generator.py` chỉ có module docstring (vai trò: outline + search + scene JSON, KHÁC `router_client.py` hiện có — đó là dịch/rewrite từ transcript có sẵn)
- [X] T007 [P] ✅ Tạo `generate_pipeline.py` ở repo root chỉ có module docstring theo đúng phong cách header của `pipeline.py` (nêu rõ: orchestrator RIÊNG cho `job_type="generate"`, không đụng `run_pipeline()`)
- [X] T008 [P] ✅ Baseline hồi quy: `./venv/bin/python -m pytest tests/ -q` → **270 passed** (2026-08-01, trước khi thêm code feature 010)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Job schema mới, state machine, review gate mở rộng, API skeleton — CẢ 4 story đều cần

**⚠️ CRITICAL**: Không story nào bắt đầu được trước khi phase này xong

- [X] T009 ✅ Trong `generate_pipeline.py`: implement `create_generate_job(topic: str, job_id: str | None = None, supervised: bool = False) -> dict` — ghi `jobs/{job_id}/job.json` với `job_type="generate"`, `topic`, `supervised`, `status="pending"`, `review_gate=None`, `review_gates={}`, `artifacts={"outline": None, "scenes": None, "output_video": None}`, `error=None` (data-model.md §1). Raise `ValueError` nếu `topic.strip()` rỗng
- [X] T010 ✅ Trong `generate_pipeline.py`: định nghĩa `GenerateStatusLiteral` (pending/outlining/scripting/awaiting_review/sourcing_assets/synthesizing/rendering/done/failed) + hàm `generate_status_from_artifacts(job: dict) -> GenerateStatusLiteral` suy trạng thái resume theo artifact đã có (data-model.md §5) — KHÔNG dùng chung `RERUN_STEPS`/`status_from_artifacts()` của `pipeline.py`
- [X] T011 [P] ✅ Trong `tests/unit/test_generate_pipeline.py`: test `create_generate_job()` ghi đúng shape job.json; test `topic` rỗng raise `ValueError`; test `generate_status_from_artifacts()` trả đúng trạng thái ứng với từng tổ hợp artifact có/thiếu (13 test)
- [X] T012 ✅ Trong `review/gates.py`: thêm `GATE_OUTLINE = "outline"` vào `GATES`; `NEXT_STATUS_AFTER_GATE["outline"] = "sourcing_assets"`; `EDITABLE_FIELD["outline"] = "narration_text"`; thêm mapping gate-aware tên field mảng (`GATE_ARRAY_KEY = {GATE_TRANSCRIPT: "segments", GATE_SCRIPT: "segments", GATE_OUTLINE: "scenes"}` — `scenes.json` dùng key `"scenes"`, khác `"segments"` của 2 gate cũ) và sửa `build_payload()`/`save_edits()` đọc/ghi theo `GATE_ARRAY_KEY[gate]` thay vì hardcode `"segments"` (research.md §7, data-model.md §3)
- [X] T013 ✅ Trong `review/gates.py`: `gate_file_path()` thêm nhánh `gate == GATE_OUTLINE` → đọc `job["artifacts"]["scenes"]`
- [X] T014 [P] ✅ Trong `tests/unit/test_review_gates_outline.py`: test `build_payload()`/`save_edits()`/`mark_reached()`/`mark_approved()` hoạt động đúng cho `gate="outline"` với fixture `scenes.json` (8 test); chạy lại `tests/unit/test_review_gates*.py` hiện có xác nhận KHÔNG hồi quy `GATE_TRANSCRIPT`/`GATE_SCRIPT` (29 test, tất cả pass)
- [X] T015 ✅ Trong `web/backend/main.py`: đăng ký router mới `app.include_router(generate_jobs_router, prefix="/api/generate-jobs")`
- [X] T016 ✅ Tạo `web/backend/generate_jobs_api.py` với `POST /api/generate-jobs` (contracts/api.md §1): validate `topic` non-empty (400 nếu rỗng), gọi `find_running_job_id()` có sẵn từ `jobs_api.py` (409 nếu đang chạy job khác — dub HOẶC generate, coi là 1 hàng đợi theo research.md §1), gọi `create_generate_job()`, trả `{"job_id": ...}`. Phase 2: CHƯA gọi start_generate_job() (chưa tồn tại tới T030/Phase 3)
- [X] T017 ✅ Trong `web/backend/generate_jobs_api.py`: implement `GET /api/generate-jobs` (danh sách, lọc `job_type=="generate"`) và `GET /api/generate-jobs/{job_id}` (chi tiết, thêm field `topic`/`scenes` rút gọn) theo contracts/api.md §2-3
- [X] T018 ✅ Trong `web/backend/generate_jobs_api.py`: implement `GET /api/generate-jobs/{job_id}/output` (`FileResponse output.mp4`, 404 nếu chưa `done`) theo contracts/api.md §4
- [X] T019 [P] ✅ Trong `tests/unit/test_generate_jobs_api.py`: contract test cho 4 endpoint T016-T018 bằng FastAPI `TestClient` (11 test, không cần mock job runner vì Phase 2 chưa wiring pipeline thật)

**Checkpoint**: Job tạo được (`job_type="generate"`), API CRUD hoạt động, chốt duyệt outline sẵn sàng dùng — nhưng CHƯA có bước xử lý thật nào chạy.

---

## Phase 3: User Story 1 - Tạo video hoàn chỉnh từ 1 chủ đề văn bản (Priority: P1) 🎯 MVP

**Goal**: Nhập 1 chủ đề → nhận video MP4 hoàn chỉnh có giọng đọc, phụ đề, ảnh minh hoạ — không cần chuẩn bị gì thêm

**Independent Test**: `POST /api/generate-jobs` với 1 topic bất kỳ, `supervised=false`, poll tới `status=="done"`, tải `output.mp4`, xác nhận có audio + nhiều ảnh khác nhau + phụ đề khớp giọng đọc (quickstart.md Scenario A)

### Implementation for User Story 1

- [X] T020 [US1] ✅ Trong `script_gen/topic_script_generator.py`: implement `write_outline_and_scenes(topic: str) -> dict` — 1 lượt gọi 9router bằng model agent (`ROUTER_AGENT_MODEL`, fallback `ROUTER_MODEL` — T003), prompt yêu cầu viết outline có cấu trúc VÀ tự tra cứu web khi cần, trả JSON parse được đúng schema data-model.md §2-3 (`outline.sections[]`, `scenes[].narration_text`/`image_query`). Tái dùng `_chat_completion()` nội bộ của `script_gen/router_client.py` — đã thêm tham số `model` tối giản (mặc định `None` = hành vi cũ y nguyên) để truyền được `ROUTER_AGENT_MODEL`, KHÔNG viết lại HTTP call
- [X] T021 [US1] ✅ Trong `script_gen/topic_script_generator.py`: `write_outline_and_scenes_to_disk()` ghi `outline.json` (data-model.md §2) và `scenes.json` (data-model.md §3, chưa có `image_path`/`voice_path`/`duration`) ra `job_dir`
- [X] T022 [P] [US1] ✅ Trong `tests/unit/test_topic_script_generator.py`: mock `_chat_completion`, test `write_outline_and_scenes()` parse JSON hợp lệ → đúng schema; test JSON lỗi/bị cắt cụt → raise lỗi rõ ràng (10 test)
- [X] T023 [US1] ✅ Trong `assets/pexels_client.py`: implement `search_image(query: str, job_dir: Path) -> Path | None` — gọi Pexels Photos API (`PEXELS_API_KEY`), tải ảnh xếp hạng đầu phù hợp tỉ lệ dọc 9:16, lưu vào `job_dir/image.jpg` (chỗ gọi tự truyền `job_dir` = thư mục riêng từng scene); trả `None` nếu rỗng
- [X] T024 [P] [US1] ✅ Trong `tests/unit/test_pexels_client.py`: mock `httpx` qua `MockTransport`, test `search_image()` trả về path ảnh đã tải khi Pexels có kết quả (5 test)
- [X] T025 [US1] ✅ Tạo `tts/scene_synthesizer.py` với `synthesize_scene(text, output_path, provider="edge-tts", voice_id=None) -> float` — gọi thẳng `_get_adapter()` có sẵn trong `tts/segment_synthesizer.py`, trả về duration thật đo bằng `media_utils.get_media_duration()`
- [X] T026 [P] [US1] ✅ Trong `tests/unit/test_scene_synthesizer.py`: mock adapter + `get_media_duration`, test duration thật không phải ước lượng (4 test)
- [X] T027 [US1] ✅ Trong `merge/hyperframes_renderer.py`: implement `render_scenes_to_video()` — sinh `index.html` từ scene JSON, subprocess gọi `npx hyperframes render`, trả về `output.mp4`. Dùng template project checked-in `merge/hyperframes_template/` (KHÔNG chạy `init` mỗi job — research.md §5b). Đã verify THẬT (không chỉ mock): render 2 scene giả lập ra đúng MP4 h264+aac, duration khớp chính xác
- [X] T028 [P] [US1] ✅ Trong `tests/unit/test_hyperframes_renderer.py`: mock `subprocess.run`, test index.html đúng nội dung/timing/escape HTML, test lỗi → `RuntimeError` (5 test)
- [X] T029 [US1] ✅ Trong `generate_pipeline.py`: implement `run_generate_pipeline(job_id)` — orchestrator nối T020-T021 → T023 mỗi scene → T025 mỗi scene → T027 → `status="done"`; resume-safe (skip scene đã có artifact). Chốt GATE_OUTLINE CHƯA nối (để T039, Phase 6)
- [X] T030 [US1] ✅ Trong `web/backend/generate_jobs_api.py`: `start_generate_job(job_id)` chạy `run_generate_pipeline()` nền (thread daemon), gọi từ `POST /api/generate-jobs`
- [X] T031 [P] [US1] ✅ Trong `tests/unit/test_generate_pipeline_e2e.py`: mock toàn bộ 9router/Pexels/TTS-adapter/`npx hyperframes`, chạy end-to-end, xác nhận `status=="done"` + `output_video` tồn tại + resume-safe sau lỗi (3 test)
- [X] T032 [P] [US1] ✅ Trong `web/frontend/src/pages/GenerateVideoPage.tsx`: entry point "Tạo video từ chủ đề" (input topic text, poll trạng thái tái dùng pattern `HomePage.tsx`), route `/generate` + nav link. Chưa có UI duyệt outline (để T043)

**Checkpoint**: US1 hoàn thành. 329 test pass (baseline 270 + 59 test mới của feature 010). Verify thật (không mock) cho `render_scenes_to_video()` xác nhận render.html/subprocess hoạt động đúng. Verify đầy đủ bằng quickstart.md Scenario A với dịch vụ THẬT (9router/Pexels/edge-tts) để lại chờ xác nhận người dùng — xem T047.

---

## Phase 4: User Story 2 - Tự động tra cứu web để bổ sung dữ kiện còn thiếu (Priority: P2)

**Goal**: Kịch bản chính xác/cập nhật hơn nhờ tra cứu web; lỗi tra cứu KHÔNG được làm hỏng job

**Independent Test**: Mock 9router agent call raise lỗi mạng → job vẫn ra `output.mp4` hoàn chỉnh dựa trên kiến thức sẵn có (quickstart.md Scenario A, phần "kỳ vọng lỗi có kiểm soát")

### Implementation for User Story 2

- [X] T033 [US2] ✅ Trong `script_gen/topic_script_generator.py`: bọc lượt gọi agent (T020) trong try/except — lỗi mạng/timeout/tool-use không khả dụng → fallback gọi lại BẰNG `ROUTER_MODEL` thường (không yêu cầu search), log warning, KHÔNG để lỗi lan lên làm fail job (FR-009). `TruncatedResponseError` KHÔNG rơi vào nhánh fallback (đổi model không giải quyết được output bị cắt)
- [X] T034 [US2] ✅ `outline.json.search_used` giờ lấy từ giá trị THẬT `write_outline_and_scenes()` trả về (`true`/`false` đúng nhánh đã chạy) — bỏ tham số `search_used` cố định trước đây của `write_outline_and_scenes_to_disk()` (SC-004)
- [X] T035 [P] [US2] ✅ Trong `tests/unit/test_topic_script_generator.py`: test fallback khi agent lỗi → `search_used=False`, script vẫn sinh; test agent thành công → `search_used=True`; test `TruncatedResponseError` KHÔNG fallback; test cả 2 lượt cùng lỗi → raise (5 test mới, 14 tổng)

**Checkpoint**: US2 hoàn thành — job không còn fail vì lý do search, verify được `search_used` phản ánh đúng thực tế. 333 test pass, không hồi quy.

---

## Phase 5: User Story 3 - Tự động xử lý khi không tìm được hình ảnh phù hợp (Priority: P3)

**Goal**: Scene không tìm được ảnh khớp vẫn có ảnh thay thế hợp lý, không để trống/lỗi

**Independent Test**: Mock Pexels trả rỗng cho 1 `image_query` → scene đó vẫn có `image_path` hợp lệ sau bước `sourcing_assets` (quickstart.md Scenario C)

### Implementation for User Story 3

- [X] T036 [US3] ✅ Trong `assets/pexels_client.py`: khi `search_image()` (T023) trả rỗng, thử lại 1 lần với `image_query` rút gọn (giữ 2 từ khoá đầu, bỏ qua nếu query đã ≤2 từ); vẫn rỗng → trả về `FALLBACK_IMAGE_PATH` tĩnh — KHÔNG raise lỗi, KHÔNG để `image_path` là `null` (FR-010). Đổi return type `Path | None` → `Path` (không còn khả năng trả None)
- [X] T037 [P] [US3] ✅ Thêm file ảnh tĩnh `assets/fallback_images/generic.jpg` (gradient trung tính 1080×1920, sinh bằng ffmpeg)
- [X] T038 [P] [US3] ✅ Trong `tests/unit/test_pexels_client.py`: test rỗng cả 2 lượt → fallback tĩnh; test lượt 2 (rút gọn) có kết quả → dùng luôn không rơi fallback; test query đã ngắn → không gọi lại thừa (3 test mới, 7 tổng)

**Checkpoint**: US3 hoàn thành — verify quickstart.md Scenario C, không scene nào thiếu ảnh. 335 test pass.

---

## Phase 6: User Story 4 - Duyệt outline/kịch bản trước khi tốn chi phí tìm ảnh/TTS/render (Priority: P4)

**Goal**: Khi bật "quản lý pipeline", job dừng ở chốt outline/scene để người dùng xem/sửa trước khi tiếp tục

**Independent Test**: `POST /api/generate-jobs` với `supervised=true` → job dừng đúng ở `awaiting_review`/`outline`; sửa `narration_text` 1 scene rồi phê duyệt → video cuối phản ánh đúng bản đã sửa (quickstart.md Scenario B)

### Implementation for User Story 4

- [X] T039 [US4] ✅ Trong `generate_pipeline.py`: sau khi ghi outline+scenes, nếu `job["supervised"]` VÀ chưa `is_approved` — `gates.mark_reached(job, GATE_OUTLINE, scene_count)`, set `status="awaiting_review"`, dừng `run_generate_pipeline()` tại đây
- [X] T040 ✅ Trong `web/backend/review_api.py`: `approve_review()` giờ rẽ nhánh theo `job_type` — job "generate" ghi `status` trực tiếp (KHÔNG qua `update_job_status()`/`VALID_TRANSITIONS` của luồng dub, vốn không có "sourcing_assets") và khởi động qua `generate_jobs_api.start_generate_job()` (KHÔNG qua `start_job()` — job này không có `source_url`/`script_mode`). `get_review()`/`save_review()` đã generic sẵn (gates.py dùng `GATE_ARRAY_KEY`), không cần sửa
- [X] T041 [US4] ✅ Không cần hàm resume riêng — `run_generate_pipeline()` (T029) đã resume-safe thuần theo `job["status"]`: `review_api.py` chỉ cần set `status="sourcing_assets"` rồi gọi lại `run_generate_pipeline()`, hàm tự đọc `scenes.json` MỚI NHẤT từ đĩa (đã có bản sửa từ `save_edits()`)
- [X] T042 [P] [US4] ✅ Test full flow ở `tests/unit/test_generate_pipeline_e2e.py` (dừng ở awaiting_review/outline; resume dùng đúng narration_text đã sửa, verify qua spy trên `synthesize_scene`) + `tests/unit/test_review_api.py` (approve qua HTTP thật, xác nhận `start_generate_job` được gọi đúng, KHÔNG phải `start_job` của luồng dub) — 4 test mới
- [X] T043 [P] [US4] ✅ Tái dùng `ReviewGatePanel.tsx` — đủ generic, chỉ thêm: ẩn cột thời gian khi `gate==="outline"` (start/end null), thêm câu dẫn riêng cho chốt outline. `GenerateVideoPage.tsx` thêm toggle "Quản lý pipeline" + render panel khi `awaiting_review` + tạm dừng poll khi đang sửa dở (mẫu `JobDetailPage.tsx`). Verify trực quan trên browser: badge/copy/ẩn cột thời gian đều đúng

**Checkpoint**: US4 hoàn thành — verify quickstart.md Scenario B. 339 test pass, không hồi quy.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hạ tầng chạy thật (Docker/Node), hồi quy toàn hệ thống, verify end-to-end thật

- [X] T044 [P] ✅ Sửa `Dockerfile`: cài Node.js 22+ (NodeSource setup script) + dependency hệ thống cho Chrome headless (research.md §8). KHÔNG tự `docker build`/chạy — theo yêu cầu người dùng, để người dùng tự build/deploy
- [ ] T045 ⏸ **CHỜ NGƯỜI DÙNG** — Build lại Docker image thật, verify `npx hyperframes render` chạy được TRONG container (không chỉ máy dev macOS). Agent KHÔNG tự chạy `docker build`/`docker compose` (yêu cầu người dùng phiên này)
- [X] T046 ✅ `./venv/bin/python -m pytest tests/ -q` → **339 passed** (baseline 270 + 69 test mới của feature 010), không hồi quy luồng dub hiện có
- [ ] T047 ⏸ **CHỜ NGƯỜI DÙNG XÁC NHẬN** — Chạy quickstart.md Scenario A/B/C với dịch vụ THẬT (9router + Pexels + HyperFrames thật, edge-tts) — tốn token LLM thật + quota Pexels thật, agent đã hỏi và người dùng chọn dừng lại xác nhận trước khi chạy (Constitution VI: KHÔNG gọi LucyAI/Vivibe thật)
- [X] T048 [P] ✅ Cập nhật `README.md` — thêm mục "Tạo video từ chủ đề (feature 010-topic-video-generation)"

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Không phụ thuộc gì — bắt đầu ngay. T002 (spike) MUST xong trước T027 (Phase 3)
- **Foundational (Phase 2)**: Phụ thuộc Setup — BLOCKS toàn bộ user story
- **User Stories (Phase 3-6)**: Đều phụ thuộc Foundational hoàn tất
  - US1 (P1): độc lập hoàn toàn, là MVP
  - US2 (P2): SỬA trực tiếp file US1 đã tạo (`topic_script_generator.py`) — nên làm SAU US1 dù về lý thuyết là "story riêng"; không đụng file của US3/US4
  - US3 (P3): SỬA trực tiếp file US1 đã tạo (`pexels_client.py`) — tương tự US2, làm sau US1
  - US4 (P4): SỬA `generate_pipeline.py` (US1) + `review_api.py` (Foundational) — làm sau US1
- **Polish (Phase 7)**: Phụ thuộc toàn bộ story muốn có mặt đã xong

### Parallel Opportunities

- Toàn bộ task Setup đánh dấu [P] chạy song song được (T003-T008, file khác nhau)
- Trong US1: T022/T024/T026/T028/T031/T032 (test + frontend) chạy song song được với nhau SAU KHI implementation tương ứng xong (khác file)
- US2/US3 có thể làm song song NHAU (khác file: `topic_script_generator.py` vs `pexels_client.py`) sau khi US1 xong, nhưng KHÔNG song song với chính US1 (cùng file)
- US4 phải làm SAU US1 (cùng file `generate_pipeline.py`)

---

## Parallel Example: Phase 1 (Setup)

```bash
Task: "Thêm ROUTER_AGENT_MODEL vào .env.example"
Task: "Tạo package assets/ với __init__.py + pexels_client.py stub"
Task: "Tạo merge/hyperframes_renderer.py stub"
Task: "Tạo script_gen/topic_script_generator.py stub"
Task: "Tạo generate_pipeline.py stub"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Hoàn tất Phase 1: Setup (kèm spike HyperFrames T002 — KHÔNG bỏ qua)
2. Hoàn tất Phase 2: Foundational (CRITICAL — chặn mọi story)
3. Hoàn tất Phase 3: User Story 1
4. **DỪNG và VALIDATE**: chạy quickstart.md Scenario A
5. Đây đã là sản phẩm demo được (chủ đề → video hoàn chỉnh)

### Incremental Delivery

1. Setup + Foundational → nền tảng sẵn sàng
2. + US1 → test độc lập → demo (MVP!)
3. + US2 → job không còn fail vì search lỗi
4. + US3 → job không còn thiếu ảnh vì search ảnh rỗng
5. + US4 → thêm khả năng kiểm soát chi phí trước khi render
6. + Polish → verify Docker thật + hồi quy toàn hệ thống

---

## Notes

- [P] tasks = file khác nhau, không phụ thuộc
- [Story] gắn task với user story để truy vết
- T002 (spike HyperFrames) là RỦI RO LỚN NHẤT của toàn bộ feature — không đoán
  trước chi tiết cú pháp, phải xác nhận thật trước T027
- Constitution KHÔNG cần amend thêm cho phạm vi tasks.md này (đã amend đủ 2
  dòng ở `/speckit-plan`/`/speckit-constitution` trước đó)
- Commit sau mỗi task hoặc nhóm task logic; dừng ở mỗi Checkpoint để validate
  story độc lập trước khi sang story tiếp theo

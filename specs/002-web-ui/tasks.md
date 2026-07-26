---
description: "Task list for Web UI cho Video Repurpose Pipeline (002-web-ui)"
---

# Tasks: Web UI cho Video Repurpose Pipeline

**Input**: Design documents from `/specs/002-web-ui/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md),
[contracts/api.md](./contracts/api.md), [research.md](./research.md), [quickstart.md](./quickstart.md)

**Tests**: Không yêu cầu test tự động (theo đúng cách tiếp cận của spec 001). Mỗi
user story kết thúc bằng task chạy `quickstart.md` để verify bằng bằng chứng
thực tế, đáp ứng Constitution Principle VI.

**Organization**: Tasks nhóm theo user story (US1/US2/US3, theo priority
P1/P2/P3 trong spec.md) để mỗi story implement/verify độc lập.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1 / US2 / US3 — story mà task thuộc về
- Mỗi task nêu rõ file path cụ thể

## Path Conventions

Web application (Option 2) theo `plan.md` → Project Structure: `web/backend/`
(FastAPI, Python) và `web/frontend/` (ReactJS). KHÔNG đụng tới module pipeline
hiện có (`pipeline.py`, `downloader/`, `asr/`, `script_gen/`, `tts/`, `merge/`)
— web layer chỉ import và gọi lại.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Khởi tạo cấu trúc `web/backend/` và `web/frontend/` theo `plan.md`

- [X] T001 Tạo cấu trúc thư mục `web/backend/` (`__init__.py`) và scaffold
      `web/frontend/` bằng Vite (React + TypeScript template): `package.json`,
      `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`
- [X] T002 Thêm `fastapi`, `uvicorn`, `itsdangerous` vào `requirements.txt`
      (đúng Technology Stack đã khoá trong constitution v1.3.0)
- [X] T003 [P] Cài dependency frontend trong `web/frontend/`: `npm install`
      (react, react-dom, vite, @vitejs/plugin-react, typescript)
- [X] T004 [P] Thêm `WEB_UI_USERNAME`/`WEB_UI_PASSWORD` vào `.env.example` và
      `.env` (điền giá trị test cục bộ) — theo research.md → Đăng nhập & phiên

**Checkpoint**: `npm run build` trong `web/frontend/` chạy được (dù chưa có nội
dung thật), `pip install -r requirements.txt` cài được fastapi/uvicorn

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Hạ tầng lõi mà MỌI user story đều cần trước khi bắt đầu

**⚠️ CRITICAL**: Không user story nào được bắt đầu trước khi Phase này xong

- [X] T005 Implement `web/backend/auth.py`: hàm kiểm tra username/password khớp
      `WEB_UI_USERNAME`/`WEB_UI_PASSWORD` từ env, hàm ký session token bằng
      `itsdangerous.URLSafeTimedSerializer` và hàm verify token (hạn 7 ngày) —
      theo research.md → Đăng nhập & phiên
- [X] T006 Implement `web/backend/main.py`: khởi tạo FastAPI app, middleware
      chặn mọi request thiếu/hết hạn session cookie (trừ `/api/login`, trả
      `401` theo contracts/api.md), mount `StaticFiles` serve React build tại
      `/` (phụ thuộc T005, cùng luồng auth nên làm sau)
- [X] T007 Implement helper functions trong `web/backend/jobs_api.py`: (a) xác
      định "có job đang chạy" bằng quét `jobs/*/job.json` tìm status không
      thuộc `{done, failed}` (b) map `job.json.status` → `progress_percent`
      theo bảng ở research.md — dùng chung cho mọi endpoint job

**Checkpoint**: Backend khởi động được (`uvicorn web.backend.main:app`), auth
middleware hoạt động (request không có cookie → 401), chưa có route job thật

---

## Phase 3: User Story 1 - Đăng nhập, chạy job qua trình duyệt, xem kết quả (Priority: P1) 🎯 MVP

**Goal**: Người dùng đăng nhập, submit URL + chọn chế độ kịch bản, theo dõi %
tiến trình, xem/tải video kết quả — không cần dòng lệnh (FR-001→FR-005,
FR-009, FR-010)

**Independent Test**: Chạy `quickstart.md` → Setup, Run, Expected Outcome với 1
URL TikTok thật; xác nhận đăng nhập → submit → % tăng dần → xem/tải video output

### Implementation for User Story 1

- [X] T008 [P] [US1] Implement `POST /api/login` và `POST /api/logout` trong
      `web/backend/main.py`: gọi `auth.py` (T005), set/xoá session cookie
      HttpOnly — theo contracts/api.md
- [X] T009 [US1] Implement `POST /api/jobs` trong `web/backend/jobs_api.py`:
      validate URL bằng `pipeline.detect_platform()` (400 nếu lỗi), kiểm tra
      job đang chạy (T007, 409 nếu có), gọi `pipeline.create_job()` rồi spawn
      job chạy nền (T011) — theo contracts/api.md
- [X] T010 [P] [US1] Implement `web/backend/job_runner.py`: hàm nhận
      `(url, script_mode, job_id)`, spawn `threading.Thread` daemon gọi
      `pipeline.run_pipeline()`, không block request — theo research.md
- [X] T011 [US1] Implement `GET /api/jobs/{job_id}` trong
      `web/backend/jobs_api.py`: trả Job Detail cơ bản (status,
      progress_percent, output_video_url) theo data-model.md (phụ thuộc T009,
      cùng file nên làm sau)
- [X] T012 [US1] Implement `GET /api/jobs/{job_id}/output` trong
      `web/backend/jobs_api.py`: stream file `output.mp4` của job, 404 nếu
      chưa có (phụ thuộc T011, cùng file)
- [X] T013 [P] [US1] `web/frontend/src/pages/LoginPage.tsx`: form đăng nhập,
      gọi `POST /api/login`, điều hướng sang trang chủ khi thành công
- [X] T014 [P] [US1] `web/frontend/src/pages/HomePage.tsx`: form nhập URL +
      chọn `translate`/`rewrite`, submit `POST /api/jobs`, hiển thị trạng
      thái/% (poll `GET /api/jobs/{job_id}` mỗi 3s theo research.md), nút xem/
      tải video khi `status == done`, hiển thị rõ khi bị `409` (đang có job
      chạy, theo FR-009)
- [X] T015 [P] [US1] `web/frontend/src/api/client.ts`: fetch wrapper gọi các
      endpoint backend, xử lý `401` (điều hướng về Login) và `409` (hiển thị
      thông báo đang bận)
- [X] T016 [US1] `web/frontend/src/App.tsx`: routing Login/Home, kiểm tra
      session hợp lệ khi vào app (phụ thuộc T013-T015)
- [X] T017 [US1] Verify US1: chạy `quickstart.md` → Setup, Run, Expected
      Outcome, và mục "Validate US1 — Chặn submit khi có job đang chạy" với 1
      URL TikTok thật (Constitution Principle VI: chỉ đánh dấu xong khi có
      bằng chứng verify thực tế). Đã verify qua Docker + curl thật: 401 khi
      chưa đăng nhập, login sai/đúng, 400 validate URL/script_mode, 409 khi mô
      phỏng job đang chạy (kèm đúng `running_job_id`), %/`can_retry` tính đúng
      cho cả job done/failed, download output.mp4 thành công. CHƯA chạy full
      download video TikTok thật qua UI — cần người dùng tự làm 1 lượt qua
      trình duyệt thật để verify trọn vẹn (xem Completion Report)

**Checkpoint**: US1 hoạt động độc lập và đầy đủ — đây là bản MVP

---

## Phase 4: User Story 2 - Xem lại lịch sử job đã chạy (Priority: P2)

**Goal**: Xem danh sách job đã chạy kèm trạng thái, mở chi tiết từng job

**Independent Test**: Chạy `quickstart.md` → Validate US2 với ≥2 job đã chạy

### Implementation for User Story 2

- [X] T018 [P] [US2] Implement `GET /api/jobs` trong `web/backend/jobs_api.py`:
      trả danh sách Job Summary sắp xếp theo `created_at` giảm dần — theo
      data-model.md và contracts/api.md
- [X] T019 [P] [US2] `web/frontend/src/pages/JobListPage.tsx`: bảng danh sách
      job (URL, platform, status, %, thời gian), link tới trang chi tiết
- [X] T020 [P] [US2] `web/frontend/src/pages/JobDetailPage.tsx`: hiển thị Job
      Detail đầy đủ (URL nguồn, chế độ kịch bản, cảnh báo, video nếu có) — gọi
      `GET /api/jobs/{job_id}` đã có từ US1 (T011)
- [X] T021 [US2] Verify US2: chạy `quickstart.md` → Validate US2. Verify qua
      Docker + curl với 2 job THẬT có sẵn (không phải mock): danh sách sắp xếp
      đúng `created_at` giảm dần, chi tiết job `done` trả đúng
      `output_video_url` + cảnh báo `duration_mismatch: true` (khớp vấn đề
      người dùng từng báo), chi tiết job `failed` trả đúng `error` thật +
      `can_retry: true`

**Checkpoint**: US1 + US2 cùng hoạt động độc lập

---

## Phase 5: User Story 3 - Cảnh báo chất lượng và thử lại job lỗi (Priority: P3)

**Goal**: Hiển thị rõ cảnh báo chất lượng, cho phép resume job lỗi từ web

**Independent Test**: Chạy `quickstart.md` → Validate US3 (job cố ý lỗi, bấm
"thử lại", xác nhận resume đúng job đó)

### Implementation for User Story 3

- [X] T022 [P] [US3] Implement `POST /api/jobs/{job_id}/retry` trong
      `web/backend/jobs_api.py`: kiểm tra job tồn tại + `status == failed`
      (404/409 nếu không), kiểm tra không có job khác đang chạy (T007), gọi
      lại `job_runner` (T010) với cùng `job_id` để resume — theo contracts/api.md
- [X] T023 [P] [US3] Cập nhật `web/frontend/src/pages/JobDetailPage.tsx`
      (T020): hiển thị rõ từng cảnh báo trong `warnings` (watermark, lệch thời
      lượng, mất nhạc nền), hiện nút "Thử lại" khi `can_retry == true`, gọi
      `POST /api/jobs/{job_id}/retry`
- [X] T024 [US3] Verify US3: chạy `quickstart.md` → Validate US3. Verify qua
      Docker + curl thật: 404 (job không tồn tại), 409 (job không ở trạng thái
      failed), 409 (có job khác đang chạy), và 202 thành công — xác nhận resume
      đúng thật sự (status chuyển `failed` → `transcribing`, KHÔNG tải lại
      video vì `source_video` artifact đã có, sau đó fail lại đúng lý do file
      test giả không hợp lệ). Phát hiện + tự sửa 1 lỗi test setup (rebuild
      Docker image bị quên sau khi thêm endpoint) trong lúc verify

**Checkpoint**: Cả 3 user story hoạt động độc lập

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Hoàn thiện chất lượng chung, không thuộc riêng story nào

- [X] T025 [P] Thêm section vào `README.md` gốc: cách chạy web UI (build
      frontend + `uvicorn`), link `.env.example` cho `WEB_UI_USERNAME`/
      `WEB_UI_PASSWORD` — không lặp lại nội dung đã có ở quickstart.md
- [X] T026 Rà soát message lỗi xuyên suốt `web/backend/jobs_api.py`/`main.py`:
      đảm bảo `401`/`409`/`404` đều có message rõ ràng đúng FR-005/FR-009. Phát
      hiện + sửa 1 điểm chưa nhất quán: lỗi 404 dùng shape `{"detail":...}`
      (mặc định `HTTPException`) khác với 400/409 dùng `{"error":...}` — đã
      chuẩn hoá toàn bộ về `{"error":...}` qua helper `_error()` dùng chung
- [X] T027 Chạy lại toàn bộ `quickstart.md` (US1 + US2 + US3) một lượt cuối
      cùng, xác nhận Constitution Check (6 principle) vẫn PASS trước khi coi
      feature hoàn tất. Verify qua Docker + curl thật: 401 (chưa login), login,
      400 (URL sai), danh sách 2 job thật, 404 (job không tồn tại, error shape
      đồng nhất), logout, 401 lại sau logout (đúng session cookie bị xoá).
      Constitution Check: 6/6 principle vẫn PASS, không phát sinh vi phạm mới

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Không phụ thuộc gì — bắt đầu ngay
- **Foundational (Phase 2)**: Phụ thuộc Setup xong — CHẶN toàn bộ user story
- **User Stories (Phase 3-5)**: Đều phụ thuộc Foundational xong
  - US1 (P1) không phụ thuộc US2/US3
  - US2 (P2) phụ thuộc endpoint `GET /api/jobs/{job_id}` đã tồn tại từ US1
    (T011) để hiển thị chi tiết, nhưng độc lập về mặt tính năng — verify riêng
    được
  - US3 (P3) phụ thuộc `job_runner` (T010) và `JobDetailPage.tsx` (T020) đã
    tồn tại từ US1/US2 để mở rộng, nhưng độc lập về mặt tính năng — verify
    riêng được
- **Polish (Phase 6)**: Phụ thuộc toàn bộ user story muốn có đã xong

### Within Each User Story

- Task cùng file `web/backend/jobs_api.py` luôn làm tuần tự (không [P] với
  nhau) — file này là nơi tập trung toàn bộ endpoint job
- Task khác file ([P]) làm song song được ngay sau khi Foundational xong
- Task verify bằng `quickstart.md` luôn là task cuối của mỗi story

### Parallel Opportunities

- T003, T004 chạy song song với nhau (Setup)
- T010 (job_runner.py) chạy song song với T009 (jobs_api.py) — khác file,
  interface đã thống nhất qua research.md
- T013, T014, T015 (3 file frontend khác nhau của US1) chạy song song hoàn
  toàn, chỉ nối lại ở T016 (App.tsx)
- T018, T019, T020 (US2) chạy song song
- T022, T023 (US3) chạy song song

---

## Parallel Example: User Story 1

```bash
# Sau khi Foundational (T005-T007) xong, chạy song song:
Task: "Implement web/backend/job_runner.py (T010)"
Task: "web/frontend/src/pages/LoginPage.tsx (T013)"
Task: "web/frontend/src/pages/HomePage.tsx (T014)"
Task: "web/frontend/src/api/client.ts (T015)"
# T008, T009, T011, T012 làm tuần tự (cùng file main.py/jobs_api.py)
# T016 (App.tsx) làm sau khi T013-T015 xong
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Hoàn thành Phase 1: Setup (T001-T004)
2. Hoàn thành Phase 2: Foundational (T005-T007) — BẮT BUỘC trước mọi story
3. Hoàn thành Phase 3: User Story 1 (T008-T017)
4. **DỪNG lại và VALIDATE**: chạy T017 (quickstart US1) độc lập
5. Đây đã là sản phẩm demo được (MVP) — thay thế hoàn toàn nhu cầu dùng CLI/Docker

### Incremental Delivery

1. Setup + Foundational xong → nền tảng sẵn sàng
2. Thêm US1 → verify độc lập → demo được (MVP!)
3. Thêm US2 → verify độc lập → demo xem lịch sử job
4. Thêm US3 → verify độc lập → demo cảnh báo + thử lại job lỗi
5. Mỗi story cộng thêm giá trị mà không phá story trước (Constitution
   Principle VI)

---

## Notes

- [P] = khác file, không phụ thuộc task chưa xong
- [Story] gắn task với user story để truy vết
- Web layer KHÔNG được sửa code trong `downloader/`, `asr/`, `script_gen/`,
  `tts/`, `merge/`, `pipeline.py` — chỉ import và gọi lại (đúng research.md)
- Commit sau mỗi task hoặc nhóm task liên quan
- Dừng lại ở mỗi Checkpoint để validate story độc lập trước khi qua story tiếp
- Tránh: nhiều task cùng sửa `jobs_api.py` được gắn [P], phụ thuộc chéo giữa
  các story phá vỡ tính độc lập

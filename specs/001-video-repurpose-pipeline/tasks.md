---
description: "Task list for Video Repurpose Pipeline (001-video-repurpose-pipeline)"
---

# Tasks: Video Repurpose Pipeline

**Input**: Design documents from `/specs/001-video-repurpose-pipeline/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md),
[contracts/cli.md](./contracts/cli.md), [contracts/job-state-schema.md](./contracts/job-state-schema.md),
[research.md](./research.md), [quickstart.md](./quickstart.md)

**Tests**: Không yêu cầu test tự động (spec.md không yêu cầu TDD). Mỗi user story
kết thúc bằng task chạy `quickstart.md` để verify bằng bằng chứng thực tế, đáp ứng
Constitution Principle VI (task chỉ "done" khi có bằng chứng verify cụ thể).

**Organization**: Tasks nhóm theo user story (US1/US2/US3, theo priority P1/P2/P3
trong spec.md) để mỗi story implement/verify độc lập.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1 / US2 / US3 — story mà task thuộc về
- Mỗi task nêu rõ file path cụ thể

## Path Conventions

Single project (Python CLI) theo `plan.md` → Project Structure: các module ở
repository root (`downloader/`, `clean_video/`, `asr/`, `script_gen/`, `tts/`,
`merge/`, `pipeline.py`), không có `src/`/`backend/`/`frontend/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Khởi tạo cấu trúc project theo `plan.md` → Project Structure

- [X] T001 Tạo cấu trúc thư mục repo: `downloader/`, `clean_video/`, `asr/`,
      `script_gen/`, `tts/`, `merge/`, `tests/unit/`, `tests/integration/`, mỗi
      thư mục module có `__init__.py`; thêm `jobs/.gitignore` (ignore toàn bộ nội
      dung runtime bên trong `jobs/`)
- [X] T002 Tạo `requirements.txt` (hoặc `pyproject.toml`) với dependency: `f2`,
      `yt-dlp`, `faster-whisper`, `openai`, `edge-tts`, `ffmpeg-python` — đúng
      Technology Stack đã khoá trong constitution
- [X] T003 [P] Cấu hình lint/format tối thiểu (`ruff` hoặc `black`, 1 file config)
      — giữ nhẹ theo Constitution Principle V (Token & Context Economy), không
      thêm bộ công cụ nặng

**Checkpoint**: `pip install -r requirements.txt` chạy được, cấu trúc thư mục khớp plan.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Hạ tầng lõi mà MỌI user story đều cần trước khi bắt đầu

**⚠️ CRITICAL**: Không user story nào được bắt đầu trước khi Phase này xong

- [X] T004 Cài đặt quản lý job state trong `pipeline.py`: hàm tạo/đọc/ghi
      `jobs/{job_id}/job.json` đúng schema ở
      [contracts/job-state-schema.md](./contracts/job-state-schema.md), kèm
      validate state transition theo state machine trong
      [data-model.md](./data-model.md#job)
- [X] T005 Cài đặt CLI skeleton trong `pipeline.py`: parse `--url`,
      `--script-mode`, `--job-id`; detect `platform` (tiktok/douyin/youtube) từ
      URL; sinh `job_id` mới hoặc resume job cũ — đúng
      [contracts/cli.md](./contracts/cli.md) (phụ thuộc T004, cùng file nên làm
      tuần tự)
- [X] T006 [P] Viết script/hàm kiểm tra môi trường trong `pipeline.py` (hoặc file
      riêng `env_check.py`): xác nhận `ffmpeg` có trong PATH và 9router phản hồi ở
      `http://localhost:20128`, báo lỗi rõ ràng nếu thiếu (chuẩn bị cho FR-008)

**Checkpoint**: Nền tảng sẵn sàng — có thể bắt đầu implement song song các user story

---

## Phase 3: User Story 1 - Tải video và ghép giọng đọc mới cơ bản (Priority: P1) 🎯 MVP

**Goal**: Từ 1 URL TikTok công khai → video output hoàn chỉnh có giọng đọc tiếng
Việt, chạy hết pipeline không cần thao tác tay giữa chừng (FR-001 → FR-008 áp dụng
đầy đủ cho nguồn TikTok)

**Independent Test**: Chạy `quickstart.md` → Run (US1) với 1 URL TikTok thật, xác
nhận `jobs/<job_id>/output.mp4` được tạo và `job.json.status == "done"`

### Implementation for User Story 1

- [X] T007 [P] [US1] Implement `downloader/f2_client.py`: tải video TikTok qua
      `f2`, lấy bản watermark-free, lưu `jobs/{job_id}/source.mp4`, cập nhật
      `job.json.artifacts.source_video` + `status = downloading` → `done` bước này
- [X] T008 [P] [US1] Implement `clean_video/detector.py`: kiểm tra nhanh video vừa
      tải có dấu hiệu watermark/hardsub còn sót không, set
      `job.json.warnings.watermark` (chỉ log cảnh báo, KHÔNG gọi AI inpainting —
      đúng Constitution Principle III + research.md)
- [X] T009 [P] [US1] Implement `asr/transcriber.py`: dùng `faster-whisper` (model
      `small`) trích xuất transcript từ `source.mp4`, ghi
      `jobs/{job_id}/transcript.json` theo [data-model.md](./data-model.md#source-video),
      xử lý case transcript rỗng (edge case trong spec.md)
- [X] T010 [P] [US1] Implement `script_gen/router_client.py` với mode `translate`:
      gọi 9router (SDK `openai`, `base_url=http://localhost:20128/v1`) dịch
      transcript sang tiếng Việt, ghi `jobs/{job_id}/script.json` theo
      [data-model.md](./data-model.md#script)
- [X] T011 [P] [US1] Implement `tts/edge_tts_client.py`: sinh giọng đọc bằng
      `edge-tts` (voice mặc định `vi-VN-NamMinhNeural`) từ `script.json`, ghi
      `jobs/{job_id}/voice.wav`, tính `duration_seconds`
- [X] T012 [P] [US1] Implement `merge/ffmpeg_merge.py`: ghép `voice.wav` vào
      `source.mp4` (thay audio gốc, theo spec Assumptions) bằng `ffmpeg` qua
      `subprocess`, xuất `jobs/{job_id}/output.mp4`; set
      `job.json.warnings.duration_mismatch` nếu lệch thời lượng đáng kể (edge case
      trong spec.md)
- [X] T013 [US1] Nối toàn bộ luồng trong `pipeline.py`: gọi tuần tự
      `f2_client` → `detector` → `transcriber` → `router_client(translate)` →
      `edge_tts_client` → `ffmpeg_merge`, cập nhật `job.json.status` sau mỗi bước,
      dừng job + ghi `error` rõ bước lỗi khi có exception (FR-007, FR-008) — phụ
      thuộc T007-T012, cùng file `pipeline.py` với T004/T005 nên làm sau cùng
- [ ] T014 [US1] Verify US1: chạy `quickstart.md` → Run, Validate Failure Handling,
      Validate Resume với 1 URL TikTok thật; xác nhận SC-001, SC-002, SC-003 đạt
      (Constitution Principle VI: chỉ đánh dấu US1 xong khi có bằng chứng verify
      thực tế)

**Checkpoint**: US1 hoạt động độc lập và đầy đủ — đây là bản MVP

---

## Phase 4: User Story 2 - Chọn nguồn video từ Douyin và YouTube (Priority: P2)

**Goal**: Mở rộng downloader hỗ trợ Douyin (qua f2) và YouTube (qua yt-dlp fallback)

**Independent Test**: Chạy `quickstart.md` với 1 URL Douyin và 1 URL YouTube, xác
nhận cả hai cho ra `output.mp4` hợp lệ

### Implementation for User Story 2

- [X] T015 [P] [US2] Mở rộng `downloader/f2_client.py` hỗ trợ nhận diện và tải URL
      Douyin (watermark-free qua API gốc, đúng Constitution Principle II)
- [X] T016 [P] [US2] Implement `downloader/ytdlp_client.py`: tải video qua
      `yt-dlp`, dùng cho YouTube và làm fallback khi `f2` không hỗ trợ nguồn
- [X] T017 [US2] Cập nhật logic detect/route platform trong `pipeline.py`: chọn
      đúng client (`f2_client` cho tiktok/douyin, `ytdlp_client` cho youtube/
      fallback) — phụ thuộc T015, T016, cùng file `pipeline.py` nên làm sau
- [ ] T018 [US2] Verify US2: chạy `quickstart.md` với 1 URL Douyin và 1 URL
      YouTube, xác nhận Acceptance Scenarios US2 trong spec.md đạt

**Checkpoint**: US1 + US2 cùng hoạt động độc lập

---

## Phase 5: User Story 3 - Tự soạn kịch bản mới thay vì dịch nguyên văn (Priority: P3)

**Goal**: Thêm chế độ `rewrite` cho script generation — viết lại kịch bản theo ý
chính thay vì dịch nguyên văn từng câu

**Independent Test**: Chạy `quickstart.md` với `--script-mode rewrite`, xác nhận
script khác bản dịch trực tiếp nhưng giữ đúng chủ đề video gốc

### Implementation for User Story 3

- [X] T019 [US3] Thêm mode `rewrite` vào `script_gen/router_client.py`: prompt
      9router viết lại kịch bản mới dựa trên ý chính của transcript (không dịch
      từng câu), ghi `script.json` với `mode = "rewrite"`
- [X] T020 [US3] Kích hoạt nhánh `--script-mode rewrite` trong `pipeline.py` (CLI
      arg đã có sẵn từ T005, giờ route đúng qua `router_client` mode `rewrite`)
- [ ] T021 [US3] Verify US3: chạy `quickstart.md` với `--script-mode rewrite`, xác
      nhận Acceptance Scenario US3 trong spec.md đạt

**Checkpoint**: Cả 3 user story hoạt động độc lập

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Hoàn thiện chất lượng chung, không thuộc riêng story nào

- [X] T022 [P] Viết `README.md` ngắn gọn ở repo root: cách setup, chạy
      `pipeline.py`, link tới `specs/001-video-repurpose-pipeline/quickstart.md`
      (Principle V: không lặp lại nội dung đã có trong specs/)
- [X] T023 Rà soát message lỗi xuyên suốt `downloader/`, `asr/`, `script_gen/`,
      `tts/`, `merge/`: đảm bảo mỗi exception ghi rõ bước nào lỗi vào
      `job.json.error` đúng FR-008
- [ ] T024 Chạy lại toàn bộ `quickstart.md` (US1 + US2 + US3) một lượt cuối cùng,
      xác nhận Constitution Check (6 principle) vẫn PASS trước khi coi feature
      hoàn tất

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Không phụ thuộc gì — bắt đầu ngay
- **Foundational (Phase 2)**: Phụ thuộc Setup xong — CHẶN toàn bộ user story
- **User Stories (Phase 3-5)**: Đều phụ thuộc Foundational xong
  - US1 (P1) không phụ thuộc US2/US3
  - US2 (P2) phụ thuộc module `f2_client.py` đã tồn tại từ US1 (T007) để mở rộng,
    nhưng độc lập về mặt tính năng — verify riêng được
  - US3 (P3) phụ thuộc module `router_client.py` đã tồn tại từ US1 (T010) để mở
    rộng, nhưng độc lập về mặt tính năng — verify riêng được
- **Polish (Phase 6)**: Phụ thuộc toàn bộ user story muốn có đã xong

### Within Each User Story

- Các module implementation ([P]) làm song song vì khác file
- Task nối luồng trong `pipeline.py` luôn làm SAU các module task (cùng file,
  không song song được với nhau)
- Task verify bằng `quickstart.md` luôn là task cuối của mỗi story

### Parallel Opportunities

- T003 chạy song song với T001/T002 (Setup)
- T006 chạy song song với T004/T005 (Foundational, khác file)
- T007-T012 (6 module task của US1) chạy song song hoàn toàn — khác file, chỉ phụ
  thuộc chung vào Foundational, không phụ thuộc lẫn nhau về code (được nối lại ở
  T013)
- T015, T016 (US2) chạy song song
- T022 chạy song song với T023 (Polish)

---

## Parallel Example: User Story 1

```bash
# Sau khi Foundational (T004-T006) xong, chạy song song:
Task: "Implement downloader/f2_client.py (T007)"
Task: "Implement clean_video/detector.py (T008)"
Task: "Implement asr/transcriber.py (T009)"
Task: "Implement script_gen/router_client.py mode translate (T010)"
Task: "Implement tts/edge_tts_client.py (T011)"
Task: "Implement merge/ffmpeg_merge.py (T012)"
# Sau khi cả 6 task trên xong mới làm T013 (nối luồng trong pipeline.py)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Hoàn thành Phase 1: Setup (T001-T003)
2. Hoàn thành Phase 2: Foundational (T004-T006) — BẮT BUỘC trước mọi story
3. Hoàn thành Phase 3: User Story 1 (T007-T014)
4. **DỪNG lại và VALIDATE**: chạy T014 (quickstart US1) độc lập
5. Đây đã là sản phẩm demo được (MVP)

### Incremental Delivery

1. Setup + Foundational xong → nền tảng sẵn sàng
2. Thêm US1 → verify độc lập → demo được (MVP!)
3. Thêm US2 → verify độc lập → demo mở rộng nguồn
4. Thêm US3 → verify độc lập → demo chế độ tự soạn kịch bản
5. Mỗi story cộng thêm giá trị mà không phá story trước (đúng Constitution
   Principle VI)

---

## Notes

- [P] = khác file, không phụ thuộc task chưa xong
- [Story] gắn task với user story để truy vết
- Mỗi user story phải hoàn thành và test được độc lập
- Commit sau mỗi task hoặc nhóm task liên quan
- Dừng lại ở mỗi Checkpoint để validate story độc lập trước khi qua story tiếp
- Tránh: task mơ hồ, nhiều task cùng sửa 1 file được gắn [P], phụ thuộc chéo giữa
  các story phá vỡ tính độc lập

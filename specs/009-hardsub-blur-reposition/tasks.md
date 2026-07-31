---

description: "Task list — 009-hardsub-blur-reposition (Làm mờ phụ đề gốc, chèn phụ đề mới đúng vị trí)"
---

# Tasks: Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí

**Input**: Design documents from `/specs/009-hardsub-blur-reposition/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: CÓ. Constitution VI yêu cầu mỗi task chỉ được đánh dấu hoàn thành khi
verify được bằng bằng chứng cụ thể. Mọi unit test MUST mock `pytesseract` và
`ffmpeg` — KHÔNG test nào được phụ thuộc Tesseract/ffmpeg thật có cài trên máy
hay không (CI phải xanh mà không cần cài Tesseract).

**Organization**: Tasks nhóm theo user story để triển khai và kiểm chứng độc lập.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: chạy song song được (file khác nhau, không phụ thuộc task chưa xong)
- **[Story]**: user story tương ứng (US1/US2/US3/US4)
- Mọi task ghi rõ đường dẫn file

## Path Conventions

Web app trên nền pipeline CLI Python — đường dẫn thật, không có `src/`:

- Pipeline & module xử lý: `pipeline.py`, `hardsub/`, `merge/`, `review/`
- Backend: `web/backend/`
- Frontend: `web/frontend/src/`
- Test: `tests/unit/`

## ⚠ Ba ràng buộc MUST giữ suốt mọi task

1. **Constitution phải được amend TRƯỚC khi viết dòng code nào** (T001) — thêm
   Tesseract/pytesseract/Pillow vào bảng Technology Stack. Governance nói rõ:
   không được đổi ngầm trong plan của từng feature.
2. **Job KHÔNG bật `hardsub_blur_enabled` phải không thêm một nhánh runtime
   nào** — mọi logic mới nằm trong `if hardsub_blur_enabled:`, mọi field mới đọc
   bằng `.get()` có default (FR-002, SC-006).
3. **KHÔNG mờ dòng chữ có nền hộp** (FR-014) — đây là điều kiện đúng đắn phân
   biệt tiêu đề/mô tả bối cảnh với phụ đề khớp lời nói. Mờ nhầm dòng tiêu đề là
   lỗi nghiêm trọng nhất mà tính năng này có thể gây ra.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Amend constitution, cài dependency mới, dựng chỗ chứa code

- [X] T001 ⚠️ **ĐIỀU KIỆN TIÊN QUYẾT — KHÔNG phải task code** (✅ HOÀN TẤT 2026-07-30, constitution v1.7.0 → **v1.8.0**): chạy `/speckit-constitution` để thêm vào bảng Technology Stack của `.specify/memory/constitution.md` một dòng "Phát hiện vùng phụ đề gốc (hardsub)" — công nghệ: Tesseract OCR qua `pytesseract` (CPU thuần, không GPU) + `Pillow` (đọc pixel) — kèm ghi chú tính năng 009 và MINOR version bump. **MUST hoàn tất trước T002**; nếu bỏ qua, mọi task sau đều vi phạm Governance ([research.md](./research.md) §9)
- [X] T002 Thêm `pytesseract>=0.3.10` và `Pillow>=10.0.0` vào `requirements.txt` (kèm comment nêu rõ dùng cho `hardsub/detector.py`, feature 009); thêm `tesseract-ocr` vào danh sách `apt-get install` trong `Dockerfile` (cùng dòng với `ffmpeg`)
- [X] T003 [P] Chạy `./venv/bin/python -m pytest tests/ -q` và lưu số test pass hiện tại làm mốc hồi quy baseline vào ghi chú PR/commit
- [X] T004 [P] Tạo package `hardsub/` với `hardsub/__init__.py` (rỗng), `hardsub/ranges.py` và `hardsub/detector.py` chỉ có module docstring nêu rõ vai trò: phát hiện vùng phụ đề gốc, dùng chung cho `pipeline.py` và `web/backend/`; MUST NOT import gì từ `web/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Field trong job.json + tính khoảng + plumbing bật/tắt mà CẢ 4 story đều cần

**⚠️ CRITICAL**: Không story nào bắt đầu được trước khi phase này xong

- [X] T005 Trong `pipeline.py` `create_job()`: thêm tham số `hardsub_blur_enabled: bool = False` và `hardsub_no_ranges: str | None = None`; ghi 2 field cùng tên vào job dict, cùng khoá `artifacts["hardsub_regions"] = None` ([data-model.md](./data-model.md) §1)
- [X] T006 Trong `hardsub/ranges.py`: implement `hardsub_ranges(no_ranges_text, total_duration)` — parse chuỗi bằng `parse_time_ranges()` (import từ `merge/ffmpeg_merge.py`, KHÔNG viết lại), rồi trả **phần bù** trong `[0, total_duration]` = các đoạn CÓ phụ đề gốc. Chuỗi rỗng/None → trả `[[0.0, total_duration]]` (mặc định cả video là có — FR-003). Bỏ khoảng có độ dài ~0 sau khi bù
- [X] T007 [P] Trong `tests/unit/test_hardsub_ranges.py`: test chuỗi rỗng → nguyên video; test 1 khoảng giữa → 2 đoạn hai bên; test khoảng chạm mép đầu/cuối → 1 đoạn; test khoảng phủ toàn bộ → trả `[]`; test chuỗi sai định dạng bị bỏ qua (FR-010); test khoảng chồng lấn/vượt thời lượng được kẹp lại
- [X] T008 Trong `pipeline.py` `run_pipeline()`: thêm tham số `hardsub_blur_enabled: bool = False` và `hardsub_no_ranges: str | None = None`, nhưng giá trị dùng thật MUST đọc từ `job.get(...)` sau khi load job — đặt cạnh `active_supervised` đã có (cùng lý do ở [research.md](./research.md) của feature 008 §11: resume/retry không truyền lại cờ sẽ âm thầm mất tính năng)
- [X] T009 Trong `web/backend/job_runner.py`: `start_job()` + `_run_and_swallow_exit()` thêm 2 tham số mới, truyền xuống `run_pipeline()`
- [X] T010 Trong `web/backend/jobs_api.py`: `SubmitJobRequest` thêm `hardsub_blur_enabled: bool = False` và `hardsub_no_ranges: str | None = None`; truyền vào `create_job()` + `start_job()` ở `submit_job()`, và `start_job()` ở `retry_job()` (đọc từ job.json); `_job_to_detail()` thêm `hardsub_blur_enabled` ([contracts/api.md](./contracts/api.md) §1, §4)
- [X] T011 [P] Trong `web/frontend/src/api/client.ts`: thêm `hardsub_blur_enabled: boolean` vào `JobDetail`; thêm 2 tham số `hardsubBlurEnabled`/`hardsubNoRanges` vào `submitJob()` (gửi kèm body theo [contracts/api.md](./contracts/api.md) §1)
- [X] T012 [P] Trong `web/frontend/src/pages/HomePage.tsx`: thêm công tắc "Làm mờ phụ đề gốc" (mặc định **tắt**, FR-002) dùng cùng markup `<label className="switch">` như `dynamicCaptions`, kèm mô tả ngắn "Che phụ đề tiếng Anh có sẵn trên hình và chèn phụ đề mới đúng chỗ đó"; chỉ hiện khi chế độ xử lý có phụ đề hiển thị (`subtitle`, hoặc `translate`/`rewrite` kèm phụ đề động — FR-009); truyền vào `submitJob()`

**Checkpoint**: Job tạo được với cờ mới, khoảng "có phụ đề gốc" tính đúng, nhưng chưa có bước phát hiện/mờ nào chạy.

---

## Phase 3: User Story 1 — Video có phụ đề gốc suốt toàn bộ thời lượng (Priority: P1) 🎯 MVP

**Goal**: Bật tính năng, không khai báo gì → hệ thống tự dò vùng phụ đề gốc (bỏ qua dòng có nền hộp), mờ đúng vùng đó, và chèn phụ đề mới đè lên đúng vị trí với cỡ chữ nhỏ hơn.

**Independent Test**: Tạo 1 job bật tính năng, không khai báo khoảng ngoại lệ; xác nhận `hardsub_regions.json` có vùng khớp dòng phụ đề (KHÔNG khớp dòng tiêu đề nền hộp), và sản phẩm cuối có vùng đó bị mờ + phụ đề mới hiển thị đúng chỗ.

### Tests for User Story 1 ⚠️

> Viết trước, xác nhận FAIL trước khi implement

- [X] T013 [P] [US1] Trong `tests/unit/test_hardsub_detector.py`: test `_has_solid_background()` phân biệt đúng vùng nền đồng nhất (độ lệch chuẩn thấp → có nền hộp → LOẠI) với vùng nền là nội dung video (độ lệch chuẩn cao → giữ) — FR-014, [research.md](./research.md) §3; dùng mảng pixel dựng sẵn bằng `numpy`, KHÔNG đọc ảnh thật
- [X] T014 [P] [US1] Trong `tests/unit/test_hardsub_detector.py`: test `_merge_line_cluster()` gộp 2 dòng chữ gần nhau theo trục dọc thành 1 box hợp (union); test 2 cụm cách xa nhau → chọn cụm có `confidence` trung bình cao nhất ([research.md](./research.md) §4)
- [X] T015 [P] [US1] Trong `tests/unit/test_hardsub_detector.py`: test `detect_regions()` thử tối đa 3 khung hình và DỪNG ngay khi tìm được vùng hợp lệ ([research.md](./research.md) §5); test idempotent — `hardsub_regions.json` đã tồn tại thì bỏ qua, không gọi OCR lần nữa. Monkeypatch cả `pytesseract` lẫn hàm trích khung hình
- [X] T016 [P] [US1] Trong `tests/unit/test_subtitle_burner_ass.py`: test `write_ass()` chỉ thêm override `{\pos(...)\fs...}` cho dòng phụ đề có mốc thời gian GIAO với vùng `detected=true, excluded=false`; dòng không giao KHÔNG có override nào (giữ style mặc định — SC-006); test file `.ass` sinh ra có đủ header `[Script Info]`/`[V4+ Styles]`/`[Events]` hợp lệ

### Implementation for User Story 1

- [X] T017 [US1] Trong `hardsub/detector.py`: implement `_extract_frames(video_path, start, end, count=3)` — gọi `ffmpeg -ss <t> -i <video> -vframes 1` xuất ảnh PNG ra thư mục tạm tại các mốc 25%/50%/75% của đoạn (kẹp lại nếu đoạn quá ngắn), trả danh sách `Path`. Theo đúng khuôn mẫu `subprocess.run(..., capture_output=True, timeout=...)` đã dùng ở `clean_video/detector.py`
- [X] T018 [US1] Trong `hardsub/detector.py`: implement `_ocr_lines(image_path)` — dùng `pytesseract.image_to_data(..., output_type=Output.DICT)` gom các word thành DÒNG (theo `block_num`/`par_num`/`line_num`), trả `[{box: {x,y,w,h}, text, confidence}]`; bỏ dòng có `confidence` dưới ngưỡng tối thiểu hoặc text rỗng
- [X] T019 [US1] Trong `hardsub/detector.py`: implement `_has_solid_background(image, box)` — nới box ~20% mỗi chiều, tính độ lệch chuẩn màu RGB bằng `numpy` (đã có sẵn), trả `True` nếu dưới ngưỡng (có nền hộp → LOẠI theo FR-014). Ngưỡng để hằng số cấp module kèm comment nêu rõ cách hiệu chỉnh ([research.md](./research.md) §3)
- [X] T020 [US1] Trong `hardsub/detector.py`: implement `_merge_line_cluster(lines)` — gộp các dòng gần nhau theo trục dọc (khoảng cách < ~1 lần chiều cao dòng) và có chồng lấn theo trục ngang thành 1 box hợp; nếu còn nhiều cụm, chọn cụm có `confidence` trung bình cao nhất ([research.md](./research.md) §4)
- [X] T021 [US1] Trong `hardsub/detector.py`: implement `detect_regions(video_path, no_ranges_text, job_dir)` — dùng `hardsub.ranges.hardsub_ranges()` lấy các đoạn có phụ đề gốc, với mỗi đoạn chạy `_extract_frames` → `_ocr_lines` → lọc `_has_solid_background` → `_merge_line_cluster`, dừng ở khung hình đầu tiên cho kết quả; ghi `hardsub_regions.json` đúng schema [data-model.md](./data-model.md) §2 (kể cả entry `detected: false`). **Idempotent**: return sớm nếu file đã tồn tại
- [X] T022 [US1] Trong `hardsub/detector.py`: thêm `load_regions(path)` trả danh sách vùng dùng được (`detected=true` VÀ `excluded=false`) — hàm dùng chung cho bước merging và cho verify thủ công ở [quickstart.md](./quickstart.md) Scenario B
- [X] T023 [US1] Trong `pipeline.py` bước transcribing (sau `transcribe()` thành công, **TRƯỚC** nhánh chốt 1 của feature 008): nếu `active_hardsub_blur` và `script_mode` có hiển thị phụ đề (FR-009) → gọi `detect_regions()`, ghi `artifacts["hardsub_regions"]`. Lỗi phát hiện MUST NOT làm hỏng job — bắt exception, in cảnh báo, coi như không dò được ([research.md](./research.md) §6)
- [X] T024 [US1] Trong `merge/subtitle_burner.py`: implement `write_ass(cues, ass_path, regions, frame_size, default_font_size, small_font_ratio)` — sinh file `.ass` hợp lệ; mỗi cue giao với một vùng dùng được thì thêm `{\pos(x,y)\fs<n>}` đầu nội dung (toạ độ = tâm dưới của box, cỡ chữ = `default_font_size * small_font_ratio`), cue khác giữ nguyên không override ([data-model.md](./data-model.md) §3, [research.md](./research.md) §1)
- [X] T025 [US1] Trong `merge/subtitle_burner.py`: implement `apply_hardsub_blur(video_path, output_path, regions)` — dựng `-filter_complex` chain `split → crop → boxblur → overlay:enable='between(t,s,e)'` cho từng vùng, nối tiếp qua nhãn `[base]` ([research.md](./research.md) §2); chạy 1 pass ffmpeg riêng, `-c:a copy`; no-op (copy file) nếu `regions` rỗng
- [X] T026 [US1] Trong `merge/subtitle_burner.py` `burn_subtitles()`: chấp nhận file `.ass` (bộ lọc `subtitles` của libass đọc được cả 2 định dạng) — **KHÔNG áp `force_style` khi đầu vào là `.ass`**, vì style/override đã nằm sẵn trong file; giữ nguyên đường `.srt` + `force_style` như cũ cho mọi trường hợp khác (SC-006)
- [X] T027 [US1] Trong `pipeline.py` bước merging, nhánh `script_mode == "subtitle"`: nếu có vùng dùng được → `apply_hardsub_blur(source_video → blurred.mp4)` rồi `write_ass()` + `burn_subtitles(blurred.mp4, subtitles.ass, output.mp4)`; không có vùng nào → giữ nguyên đường `write_srt` + `burn_subtitles(source_video, ...)` hiện tại
- [X] T028 [US1] Trong `pipeline.py` bước merging, nhánh phụ đề động (`active_dynamic_captions`): áp cùng thứ tự — `apply_hardsub_blur()` lên `output.mp4` đã ghép, rồi `write_ass()` + `burn_subtitles()`; giữ nguyên quy tắc "lỗi burn ở nhánh này CHỈ cảnh báo, KHÔNG fail job" đã có
- [X] T029 [US1] Trong `pipeline.py` `parse_args()`: thêm `--hardsub-blur` (`action="store_true"`) và `--hardsub-no-ranges` (mặc định `None`) với help text đúng như [contracts/api.md](./contracts/api.md) §5; truyền vào `run_pipeline()` ở `main()`
- [X] T030 [US1] Verify Scenario A + B trong [quickstart.md](./quickstart.md) trên máy local (KHÔNG cần libass): chạy job thật với video có hardsub, kiểm `hardsub_regions.json` có box khớp dòng phụ đề và KHÔNG khớp dòng tiêu đề nền hộp (FR-014); chạy `apply_hardsub_blur()` rồi xem `blurred_test.mp4` xác nhận mờ đúng vùng đúng lúc. Lưu output làm bằng chứng
- [ ] T031 [US1] Verify Scenario C trong [quickstart.md](./quickstart.md) trên môi trường CÓ libass (Docker): xác nhận `subtitles.ass` có override đúng dòng, và `output.mp4` hiển thị phụ đề mới đúng vị trí vùng đã mờ (SC-001, SC-003). **Nhờ người dùng chạy/deploy Docker**, không tự chạy `docker compose`

**Checkpoint**: US1 dùng được trọn vẹn cho video có hardsub suốt thời lượng — đây là MVP.

---

## Phase 4: User Story 2 — Khai báo đoạn không có phụ đề gốc (Priority: P2)

**Goal**: Người dùng khai báo các khoảng không có phụ đề gốc; hệ thống không mờ gì ở đó, phụ đề mới hiển thị theo vị trí/cỡ chữ mặc định.

**Independent Test**: Bật tính năng + khai báo 1 khoảng; xác nhận đúng đoạn đó không bị mờ ở sản phẩm cuối, các đoạn còn lại vẫn mờ + chèn đúng vị trí như US1.

### Tests for User Story 2 ⚠️

- [X] T032 [P] [US2] Trong `tests/unit/test_hardsub_detector.py`: test `detect_regions()` với `no_ranges_text` khai báo 1 khoảng → `hardsub_regions.json.regions` KHÔNG chứa đoạn đó, và `no_hardsub_ranges` ghi lại đúng khoảng đã parse ([data-model.md](./data-model.md) §2)
- [X] T033 [P] [US2] Trong `tests/unit/test_subtitle_burner_ass.py`: test cue nằm trong khoảng đã khai báo (không thuộc vùng nào) KHÔNG có override — hiển thị mặc định (FR-005)

### Implementation for User Story 2

- [X] T034 [US2] Trong `web/frontend/src/pages/HomePage.tsx`: thêm ô nhập "Đoạn không có phụ đề gốc (tuỳ chọn)" — chỉ hiện khi công tắc làm mờ đang bật; placeholder `"vd: 0:15-0:30, 1:05-end"`, hint nêu rõ "Các đoạn này sẽ KHÔNG bị làm mờ; để trống = cả video đều có phụ đề gốc" (FR-003/FR-004); dùng cùng markup `<input className="input">` như ô `keep-ranges` đã có
- [X] T035 [US2] Trong `web/frontend/src/api/client.ts`: truyền `hardsubNoRanges` vào body `submitJob()` (chỉ gửi khi có giá trị, giống cách `keepOriginalRanges` đang làm)
- [X] T036 [US2] Verify phần Scenario B liên quan khoảng khai báo trong [quickstart.md](./quickstart.md): submit job có khai báo khoảng, xác nhận `blurred_test.mp4` hoàn toàn không có vùng mờ trong đúng khoảng đó (SC-002); và khai báo sai định dạng bị bỏ qua chứ không làm hỏng job (FR-010)

**Checkpoint**: US1 + US2 chạy độc lập; tính năng an toàn với video có nội dung hỗn hợp.

---

## Phase 5: User Story 4 — Review vị trí phụ đề gốc khi bật Quản lý pipeline (Priority: P2)

**Goal**: Job bật đồng thời "Quản lý pipeline" (008) thấy trước các vùng đã dò tại chốt lời thoại và đánh dấu lại được đoạn dò sai trước khi phê duyệt.

**Independent Test**: Bật cả 2 tính năng; ở chốt lời thoại thấy danh sách vùng đã dò; đánh dấu 1 đoạn thành "không có phụ đề gốc"; phê duyệt; xác nhận đoạn đó không bị mờ ở sản phẩm cuối.

### Tests for User Story 4 ⚠️

- [X] T037 [P] [US4] Trong `tests/unit/test_review_gates_hardsub.py`: test `build_payload()` ở gate `transcript` CÓ field `hardsub_regions` khi job bật cả `hardsub_blur_enabled` lẫn `supervised`; test field VẮNG MẶT hoàn toàn (không phải mảng rỗng) khi một trong hai tắt ([contracts/api.md](./contracts/api.md) §2)
- [X] T038 [P] [US4] Trong `tests/unit/test_review_gates_hardsub.py`: test áp `hardsub_overrides` đặt `excluded=true` đúng entry trong `hardsub_regions.json` VÀ nối khoảng tương ứng vào `job["hardsub_no_ranges"]` ([research.md](./research.md) §7); test `index` không tồn tại → lỗi rõ ràng, không ghi file
- [X] T039 [P] [US4] Trong `tests/unit/test_review_api.py` (file đã có từ feature 008): test `PUT /review` với `hardsub_overrides` trả thêm `hardsub_excluded_count`; test 400 khi job không bật `hardsub_blur_enabled` nhưng request có `hardsub_overrides` ([contracts/api.md](./contracts/api.md) §3)

### Implementation for User Story 4

- [X] T040 [US4] Trong `review/gates.py` `build_payload()`: khi `gate == GATE_TRANSCRIPT` và job bật `hardsub_blur_enabled`, đọc `hardsub_regions.json` và thêm field `hardsub_regions` (rút gọn: `index`, `start`, `end`, `detected`, `excluded`, `box` — KHÔNG kèm `frame_size`/`confidence`) theo [data-model.md](./data-model.md) §4
- [X] T041 [US4] Trong `review/gates.py`: implement `apply_hardsub_overrides(job, overrides)` — đặt `excluded=true` cho từng `index` trong `hardsub_regions.json`, nối khoảng `start-end` tương ứng vào `job["hardsub_no_ranges"]` (nối bằng dấu phẩy, giữ đúng cú pháp chuỗi), raise lỗi rõ ràng nếu `index` không tồn tại. Trả số vùng đã loại trừ
- [X] T042 [US4] Trong `web/backend/review_api.py`: `SaveReviewRequest` thêm `hardsub_overrides: list[...] | None = None`; trong `save_review()` gọi `apply_hardsub_overrides()` khi có, map lỗi index sang 400, thêm `hardsub_excluded_count` vào response; trả 400 nếu job không bật `hardsub_blur_enabled` mà request vẫn gửi field này ([contracts/api.md](./contracts/api.md) §3)
- [X] T043 [US4] Trong `web/frontend/src/api/client.ts`: thêm `hardsub_regions?: HardsubRegion[]` vào `ReviewPayload` (+ interface `HardsubRegion`); `saveReview()` nhận thêm tham số tuỳ chọn `hardsubOverrides`
- [X] T044 [US4] Trong `web/frontend/src/components/ReviewGatePanel.tsx`: khi payload có `hardsub_regions`, hiện thêm một mục "Vùng phụ đề gốc đã phát hiện" phía trên bảng câu — mỗi dòng nêu khoảng thời gian, trạng thái (đã dò được / **không xác định được**), và nút "Đánh dấu không có phụ đề gốc"; đánh dấu xong đưa vào state `dirty` như mọi thay đổi khác, gửi kèm khi bấm Lưu (FR-012, FR-015 đã có sẵn)
- [X] T045 [US4] Verify Scenario D trong [quickstart.md](./quickstart.md): chạy job bật cả 2 tính năng, đánh dấu 1 vùng, phê duyệt, kiểm `hardsub_regions.json` có `excluded: true` + `job.json.hardsub_no_ranges` đã nối khoảng, và sản phẩm cuối không mờ đoạn đó (SC-007); lặp lại với job KHÔNG bật `supervised` để xác nhận không có panel nào (FR-013)

**Checkpoint**: Người dùng bắt được lỗi dò sai vị trí trước khi tốn công xử lý tiếp.

---

## Phase 6: User Story 3 — Không xác định được vị trí phụ đề gốc ở một đoạn (Priority: P3)

**Goal**: Đoạn mặc định "có phụ đề gốc" nhưng không dò ra vùng nào → xử lý an toàn, không mờ sai chỗ, không hỏng job, có cảnh báo rõ ràng.

**Independent Test**: Giả lập đoạn không dò được; xác nhận job vẫn hoàn tất, đoạn đó không bị mờ, và cảnh báo hiện ở trang chi tiết job.

### Tests for User Story 3 ⚠️

- [X] T046 [P] [US3] Trong `tests/unit/test_hardsub_detector.py`: test cả 3 khung hình đều không cho vùng hợp lệ → entry `detected: false, box: null`, KHÔNG raise exception ([data-model.md](./data-model.md) §2)
- [X] T047 [P] [US3] Trong `tests/unit/test_subtitle_burner_ass.py`: test `apply_hardsub_blur()` bỏ qua hoàn toàn entry `detected: false` (không sinh chain filter nào cho nó); test `write_ass()` không override cue nằm trong đoạn `detected: false` (FR-008)

### Implementation for User Story 3

- [X] T048 [US3] Trong `pipeline.py` sau khi `detect_regions()` chạy xong: nếu có ≥1 entry `detected: false`, ghi `warnings_update={"hardsub_not_detected": True}` và một field đếm `hardsub_undetected_count` qua `extra_update` — theo đúng khuôn mẫu `tts_segments_failed`/`tts_failed_segments` đã có (FR-008)
- [X] T049 [P] [US3] Trong `web/frontend/src/api/client.ts`: thêm `hardsub_not_detected?: boolean` vào type `warnings` của `JobDetail`, và `hardsub_undetected_count: number`
- [X] T050 [P] [US3] Trong `web/frontend/src/pages/JobDetailPage.tsx`: thêm nhãn cảnh báo vào `WARNING_LABELS`/`warningLabel()` cho `hardsub_not_detected` — nêu rõ SỐ đoạn không xác định được vị trí và gợi ý "khai báo các đoạn đó là không có phụ đề gốc ở lượt sau" (US3 acceptance scenario 2)
- [X] T051 [US3] Verify hàng "video hoàn toàn không có phụ đề gốc" trong Edge Cases của [spec.md](./spec.md): chạy job bật tính năng trên video KHÔNG có hardsub, xác nhận job vẫn `done`, không đoạn nào bị mờ, có cảnh báo, và kết quả tương đương như tắt tính năng

**Checkpoint**: Cả 4 user story hoạt động độc lập.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T052 Verify Scenario E ([quickstart.md](./quickstart.md)) — hồi quy job KHÔNG bật tính năng (SC-006): chạy 1 job thật liền mạch, kiểm KHÔNG có `hardsub_regions.json`, KHÔNG có `subtitles.ass` (vẫn `subtitles.srt`), `job.json` có `hardsub_blur_enabled: false`; mở một job **cũ** (tạo trước feature này) ở cả danh sách lẫn trang chi tiết
- [X] T053 [P] Cập nhật `README.md`: thêm `--hardsub-blur` / `--hardsub-no-ranges` vào bảng tham số CLI, và một mục ngắn mô tả tính năng trên web UI (gồm lưu ý cần cài `tesseract-ocr`)
- [X] T054 [P] Xác nhận dependency mới ĐÚNG như đã amend constitution: `git diff requirements.txt Dockerfile` chỉ chứa `pytesseract`, `Pillow`, `tesseract-ocr` — không có gói nào khác lọt vào
- [X] T055 Chạy `./venv/bin/python -m pytest tests/ -q` — toàn bộ xanh, số test ≥ mốc baseline ở T003 cộng số test mới; đối chiếu checklist Definition of Done cuối [quickstart.md](./quickstart.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 **BLOCK toàn bộ mọi thứ** (điều kiện Governance); T002 phụ thuộc T001
- **Foundational (Phase 2)**: sau Phase 1 — **BLOCK toàn bộ user story**
- **US1 (Phase 3)**: sau Phase 2 — là MVP
- **US2 (Phase 4)**: sau Phase 2 về code (chỉ chạm UI + client), nhưng verify (T036) cần US1 đã chạy được để so sánh có/không mờ
- **US4 (Phase 5)**: sau **US1** — cần `hardsub_regions.json` tồn tại mới có gì để review; cũng cần feature 008 đã có sẵn (đã hoàn tất)
- **US3 (Phase 6)**: sau **US1** — cần `detect_regions()` tồn tại mới có nhánh `detected: false` để xử lý
- **Polish (Phase 7)**: sau các story muốn giao

### User Story Dependencies

- **US1 (P1)**: không phụ thuộc story nào. Tự nó là toàn bộ giá trị cốt lõi
- **US2 (P2)**: độc lập về code với US1 (chỉ thêm ô nhập + truyền field); dùng chung `hardsub_ranges()` đã làm ở Foundational
- **US4 (P2)**: phụ thuộc US1 (phải có vùng dò được thì mới review được)
- **US3 (P3)**: phụ thuộc US1 (nhánh không dò được nằm trong chính `detect_regions()`)

### Within Each User Story

- Test viết trước và phải FAIL trước khi implement
- `hardsub/` (logic thuần) trước `merge/` (ffmpeg) trước `pipeline.py` (nối luồng) trước frontend
- Verify scenario end-to-end là task **cuối** của mỗi story

### Parallel Opportunities

- Phase 1: T003, T004 song song (sau khi T001+T002 xong)
- Phase 2: T007, T011, T012 song song (test / client types / HomePage — 3 file khác nhau); T005–T006 và T008–T010 tuần tự vì cùng chạm `pipeline.py` / `web/backend/`
- Phase 3: T013–T016 song song (viết test trước); T017–T022 tuần tự vì cùng file `hardsub/detector.py`; T024–T026 tuần tự vì cùng `merge/subtitle_burner.py`
- Phase 5: T037–T039 song song; T043, T044 cần T042 xong
- Phase 6: T046, T047 song song; T049, T050 song song
- Phase 7: T053, T054 song song

---

## Parallel Example: User Story 1

```bash
# Viết 4 test trước (song song, 2 file khác nhau), xác nhận FAIL:
Task: "T013 Test lọc nền hộp trong tests/unit/test_hardsub_detector.py"
Task: "T014 Test gộp cụm dòng trong tests/unit/test_hardsub_detector.py"
Task: "T015 Test lấy mẫu 3 khung + idempotent trong tests/unit/test_hardsub_detector.py"
Task: "T016 Test write_ass override theo dòng trong tests/unit/test_subtitle_burner_ass.py"
```

## Parallel Example: Phase 2 (Foundational)

```bash
# Sau khi T005–T006 xong, chạy 3 task này song song (3 file khác nhau):
Task: "T007 Test phần bù khoảng trong tests/unit/test_hardsub_ranges.py"
Task: "T011 Kiểu + tham số submitJob trong web/frontend/src/api/client.ts"
Task: "T012 Công tắc Làm mờ phụ đề gốc trong web/frontend/src/pages/HomePage.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. **T001 — amend constitution TRƯỚC MỌI THỨ** (điều kiện Governance, không bỏ qua)
2. Phase 1 còn lại: cài dependency, dựng khung
3. Phase 2: Foundational (T005–T012) — **CRITICAL, block mọi story**
4. Phase 3: US1 (T013–T031)
5. **DỪNG và VALIDATE**: Scenario A + B ở local, Scenario C trên Docker
6. Deploy/demo

### Incremental Delivery

1. Setup + Foundational → cờ bật/tắt có, hành vi hiện tại chưa đổi gì
2. US1 → tự động mờ + chèn đúng vị trí → **MVP**
3. US2 → khai báo được đoạn ngoại lệ, an toàn với video hỗn hợp
4. US4 → bắt được lỗi dò sai trước khi xử lý tiếp (khi dùng cùng Quản lý pipeline)
5. US3 → cảnh báo rõ ràng cho đoạn không dò được
6. Phase 7 → hồi quy + tài liệu

Mỗi bước không phá bước trước: job không bật `hardsub_blur_enabled` chạy y như
cũ ở **mọi** mốc giao hàng (SC-006).

---

## Notes

- `[P]` = file khác nhau, không phụ thuộc task chưa xong
- Nhiều task chạm chung `hardsub/detector.py`, `merge/subtitle_burner.py`,
  `pipeline.py`, `web/backend/review_api.py`,
  `web/frontend/src/components/ReviewGatePanel.tsx` — các task đó **không** được
  `[P]`, làm tuần tự để tránh xung đột
- Xác nhận test FAIL trước khi implement
- Mọi task chỉ đánh dấu hoàn thành khi có bằng chứng cụ thể — test pass, log,
  hoặc file output kiểm tra được (Constitution VI)
- **Unit test MUST mock `pytesseract` + `ffmpeg`** — CI phải xanh mà không cần
  cài Tesseract
- **libass**: máy dev hiện tại (Homebrew ffmpeg) KHÔNG có bộ lọc `subtitles`,
  nên T031 và mọi verify liên quan burn phải chạy trên môi trường có libass
  (Docker). Bước mờ (`crop`/`boxblur`/`overlay`) KHÔNG cần libass, verify được
  đầy đủ ở local
- **Verify TTS chỉ dùng `edge-tts`**; KHÔNG gọi thật Vivibe/LucyAI, KHÔNG gọi
  thật Zernio

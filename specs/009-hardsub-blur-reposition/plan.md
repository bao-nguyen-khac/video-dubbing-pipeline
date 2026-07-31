# Implementation Plan: Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí

**Branch**: `009-hardsub-blur-reposition` | **Date**: 2026-07-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-hardsub-blur-reposition/spec.md`

## Summary

Thêm một công tắc "làm mờ phụ đề gốc" lúc tạo job. Khi bật, hệ thống coi toàn bộ
video là có phụ đề gốc trừ các khoảng người dùng khai báo là không có (cú pháp
chuỗi khoảng giống "Giữ nguyên audio gốc" nhưng field riêng). Với mỗi đoạn liên
tục "có phụ đề gốc", hệ thống trích 1-3 khung hình đại diện, dùng OCR (Tesseract)
tìm dòng chữ **không có nền hộp** (loại bỏ dòng tiêu đề có nền — FR-014), rồi ghi
lại vùng đó vào `hardsub_regions.json`. Ở bước ghép cuối, video được mờ đúng vùng
+ đúng khoảng thời gian đó (chain `crop→boxblur→overlay` theo từng vùng), và
phụ đề mới được burn bằng file `.ass` (không phải `.srt`) để mỗi dòng phụ đề có
thể override vị trí/cỡ chữ riêng khi rơi vào một vùng đã phát hiện.

Nếu job bật đồng thời "Quản lý pipeline" (008-supervised-pipeline), các vùng đã
phát hiện (và các đoạn không phát hiện được) được hiển thị ngay tại chốt chờ
duyệt sau bước tách lời — người dùng đánh dấu lại đoạn dò sai thành "không có
phụ đề gốc" trước khi phê duyệt (FR-012). Nếu không bật, toàn bộ tự động, chỉ
cảnh báo khi không xác định được vị trí (FR-008/FR-013).

**Quyết định kỹ thuật quan trọng nhất** (chi tiết ở [research.md](./research.md)):

1. **`.ass` thay vì `.srt`** cho phụ đề mới — vì đây là cách DUY NHẤT để một số
   dòng phụ đề dùng vị trí/cỡ chữ khác (đúng vùng đã dò) trong khi các dòng
   khác vẫn dùng vị trí mặc định hiện có, trong CÙNG một lượt burn. `force_style`
   toàn cục của bộ lọc `subtitles` (đang dùng cho mọi chế độ) không làm được
   việc này vì nó áp dụng cho TOÀN BỘ file, không theo từng dòng.
2. **Mờ theo vùng bằng `crop→boxblur→overlay`**, một chain riêng cho mỗi vùng đã
   phát hiện, mỗi chain chỉ bật trong đúng khoảng thời gian của vùng đó
   (`enable='between(t,s,e)'` — đúng khuôn mẫu `apply_keep_original_ranges()`
   đã có). Số chain = số đoạn có phụ đề gốc, đúng tinh thần SC-005 (chi phí tỉ
   lệ số đoạn, không tỉ lệ độ dài video).
3. **Phân biệt "có/không nền hộp" bằng độ lệch chuẩn màu pixel** quanh mỗi dòng
   chữ OCR tìm được — không cần model AI, không cần GPU (FR-014).

## Technical Context

**Language/Version**: Python 3.11 (backend + pipeline); TypeScript 6 + React 19
(frontend, Vite 8) — không đổi so với feature 008.

**Primary Dependencies MỚI**: `pytesseract` (Python binding cho Tesseract OCR) +
`tesseract-ocr` (binary hệ thống, cài qua `apt-get`/`brew`) + `Pillow` (đọc ảnh
đã trích từ ffmpeg, tính độ lệch chuẩn màu). `numpy` đã có sẵn trong
`requirements.txt` (dependency của faster-whisper) — không cần thêm.

⚠️ **Đây là 3 dòng MỚI trong bảng Technology Stack (Locked Decisions) của
constitution.md — theo Governance, MUST đi qua `/speckit-constitution` amend
TRƯỚC khi implement, không được thêm ngầm.** Xem [Constitution Check](#constitution-check).

**Storage**: file JSON — `jobs/{job_id}/hardsub_regions.json` (mới, artifact
trung gian lưu vùng đã phát hiện từng đoạn); `jobs/{job_id}/subtitles.ass` (mới,
thay `subtitles.srt` khi tính năng bật). Field mới trong `job.json`:
`hardsub_blur_enabled`, `hardsub_no_ranges`.

**Testing**: pytest, theo đúng khuôn mẫu đã có — OCR/ffmpeg MUST được mock trong
unit test (Constitution VI: test không được phụ thuộc binary ngoài có/không cài
trên máy CI). Test tích hợp thật (có Tesseract + ffmpeg thật) là tuỳ chọn, đánh
dấu riêng để CI có thể skip nếu thiếu Tesseract.

**Target Platform**: Linux server (Docker `python:3.11-slim` + `apt-get install
tesseract-ocr ffmpeg`). ⚠️ Máy dev hiện tại (Homebrew ffmpeg trên macOS) **không
có libass** (đã phát hiện lại từ feature 008) nên bước burn `.ass` cuối cùng
không chạy được ở local — chỉ verify được các bước trước đó (detect/blur) tại
đây; burn thật cần chạy trên môi trường có libass (Docker image, do `apt-get
install ffmpeg` trên Debian có kèm libass).

**Project Type**: Web application (FastAPI backend + React SPA) trên nền
pipeline CLI Python — không đổi cấu trúc so với feature 008.

**Performance Goals**: SC-005 — chi phí xử lý thêm tỉ lệ với SỐ ĐOẠN có phụ đề
gốc, không tỉ lệ độ dài video; với ≤5 đoạn, thêm không quá vài chục giây. OCR
chỉ chạy trên 1-3 khung hình/đoạn (research.md §5), không quét liên tục.

**Constraints**: (a) job không bật tính năng MUST giữ nguyên 100% hành vi hiện
tại (SC-006); (b) không libass ⟹ không burn được — lỗi này đã tồn tại từ trước
(feature 003/008), tính năng 009 KHÔNG làm nó tệ hơn, chỉ thêm bước phụ thuộc
cùng hạ tầng; (c) OCR/Tesseract chỉ chạy CPU, không yêu cầu GPU.

**Scale/Scope**: 1 người dùng, video vài chục giây tới vài phút, thường ≤10 đoạn
có phụ đề gốc mỗi video.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Kết quả | Ghi chú |
|---|---|---|
| I. Python-Only Stack | ✅ PASS | Toàn bộ logic mới (OCR, blur, burn) là Python + ffmpeg; UI review là React — đúng ngoại lệ đã có |
| II. Source-First Downloading | ✅ N/A | Không chạm bước download |
| III. On-Demand AI Cleanup | ✅ PASS | Tính năng này KHÔNG dùng AI inpainting (video-subtitle-remover) — dùng OCR + blur, nhẹ hơn nhiều, không mở rộng phạm vi nguyên tắc này |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS | plan/research/data-model/contracts/quickstart là markdown thuần |
| V. Token & Context Economy | ⚠️ Có thêm dependency | Thêm 3 dòng công nghệ mới (xem dưới) — có lý do rõ ràng (không có thư viện Python thuần nào thay OCR được), không phải thêm tuỳ tiện |
| VI. Agentic Harness Discipline | ✅ PASS | `hardsub_regions.json` là artifact trung gian audit được; test MUST mock OCR/ffmpeg thật; không chạm TTS trả phí/Zernio |
| **Technology Stack (locked)** | ✅ **PASS — đã amend** | Constitution **v1.8.0** (2026-07-30) đã thêm dòng "Phát hiện vùng phụ đề gốc (hardsub)" — Tesseract OCR qua `pytesseract` + `Pillow`. Amend cũng bổ sung 1 quy tắc vào Principle VI: unit test MUST mock binary ngoài (OCR/ffmpeg) |
| Project Structure | ⚠️ Mở rộng | Thêm module top-level `hardsub/` (detect vùng phụ đề gốc) — theo đúng khuôn mẫu `review/` đã thêm ở feature 008; `clean_video/` KHÔNG dùng vì đó là chỗ dành riêng cho AI inpainting (Principle III), tính năng này không phải AI inpainting |

**Post-Phase-1 re-check**: xem [Complexity Tracking](#complexity-tracking) — thiết
kế Phase 1 không phát sinh thêm vi phạm nào ngoài mục Technology Stack đã nêu.

**✅ ĐÃ HOÀN TẤT (2026-07-30)**: constitution đã được amend lên **v1.8.0** —
thêm dòng công nghệ mới vào bảng Technology Stack, thêm `hardsub/` vào Project
Structure, và bổ sung quy tắc mock binary ngoài vào Principle VI. Điều kiện tiên
quyết Governance đã thoả; `/speckit-implement` chạy được (T001 trong
[tasks.md](./tasks.md) đã đánh dấu xong).

## Project Structure

### Documentation (this feature)

```text
specs/009-hardsub-blur-reposition/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── api.md            # Phase 1 output — field mới + payload review mở rộng
├── checklists/
└── tasks.md              # Phase 2 (/speckit-tasks — KHÔNG tạo ở lệnh này)
```

### Source Code (repository root)

```text
media-generation/
├── pipeline.py                  # SỬA: + field hardsub_blur_enabled/hardsub_no_ranges
│                                #   trong create_job(); + bước detect vùng phụ đề gốc
│                                #   (chạy sau transcribe, TRƯỚC chốt 1 — cả job
│                                #   supervised lẫn không); bước merging đọc
│                                #   hardsub_regions.json để mờ + burn .ass
├── hardsub/                     # MỚI — phát hiện vùng phụ đề gốc
│   ├── __init__.py
│   ├── ranges.py                #   tính "đoạn có phụ đề gốc" = complement của
│   │                            #   hardsub_no_ranges trong [0, duration]; tái
│   │                            #   dùng parse_time_ranges() (merge/ffmpeg_merge.py)
│   └── detector.py              #   trích khung hình đại diện (ffmpeg) + OCR
│                                #   (pytesseract) + lọc "không nền hộp" (FR-014)
│                                #   + gộp theo cụm → 1 vùng/đoạn; ghi
│                                #   hardsub_regions.json
├── merge/
│   ├── ffmpeg_merge.py           # KHÔNG SỬA — parse_time_ranges() tái dùng nguyên trạng
│   └── subtitle_burner.py        # SỬA: + write_ass() (thay/bổ sung write_srt cho
│                                #   trường hợp có vùng cần override vị trí/cỡ chữ
│                                #   theo từng dòng); + apply_hardsub_blur() (chain
│                                #   crop→boxblur→overlay theo từng vùng); burn_subtitles()
│                                #   nhận thêm .ass khi cần
├── review/gates.py               # SỬA: build_payload() cho GATE_TRANSCRIPT thêm
│                                #   field hardsub_regions khi tính năng bật; save_edits()
│                                #   nhận thêm thao tác "đánh dấu không có phụ đề gốc"
├── web/backend/
│   ├── jobs_api.py                # SỬA: SubmitJobRequest + hardsub_blur_enabled/
│                                  #   hardsub_no_ranges; truyền vào create_job()/start_job()
│   ├── job_runner.py               # SỬA: truyền 2 field mới xuống run_pipeline()
│   └── review_api.py               # SỬA: PUT /review nhận thêm hardsub_overrides
├── web/frontend/src/
│   ├── api/client.ts                # SỬA: field mới trong submitJob()/JobDetail,
│                                    #   ReviewPayload.hardsub_regions
│   ├── pages/HomePage.tsx            # SỬA: + công tắc "Làm mờ phụ đề gốc" + ô
│                                    #   khai báo khoảng không có phụ đề gốc
│   └── components/ReviewGatePanel.tsx # SỬA: hiện thêm danh sách vùng phụ đề gốc
│                                     #   (khi có) tại chốt lời thoại, nút đánh dấu
│                                     #   "không có phụ đề gốc" theo từng đoạn
└── tests/unit/
    ├── test_hardsub_ranges.py        # MỚI — complement ranges, tái dùng parse_time_ranges
    ├── test_hardsub_detector.py      # MỚI — lọc nền hộp, gộp cụm; MOCK pytesseract/ffmpeg
    ├── test_subtitle_burner_ass.py   # MỚI — write_ass() sinh đúng override; MOCK ffmpeg
    └── test_review_gates_hardsub.py  # MỚI — payload/redaction hardsub trong chốt 1
```

**Structure Decision**: giữ nguyên layout Constitution → Project Structure, chỉ
thêm 1 module top-level `hardsub/` (phát hiện) — tách khỏi `merge/` (chỉ lo
ffmpeg burn/blur) và khỏi `clean_video/` (dành riêng AI inpainting, Principle
III). `review/gates.py` và `review_api.py` MỞ RỘNG (không viết lại) để tái dùng
đúng cơ chế chốt đã có ở 008, đúng tinh thần FR-012/013.

## Complexity Tracking

> Constitution Check có 1 vi phạm cần biện minh: thêm công nghệ mới vào bảng
> Technology Stack.

| Vi phạm | Vì sao cần | Phương án đơn giản hơn bị loại vì |
|---|---|---|
| Thêm Tesseract (pytesseract) + Pillow vào Technology Stack | Cần xác định TOẠ ĐỘ vùng chữ trong khung hình — không có cách nào làm việc này bằng công nghệ đã có (ffmpeg không tự đọc được nội dung/vị trí chữ) | Dùng LLM vision (đã có sẵn qua 9router) để mô tả vị trí — bị loại vì LLM trả toạ độ pixel không đáng tin cậy để tự động hoá, và tốn 1 lượt gọi trả phí mỗi đoạn thay vì OCR CPU miễn phí (đã thảo luận và chốt với người dùng trước khi viết spec) |
| Thêm module `hardsub/` (không gộp vào `merge/` hay `clean_video/`) | Logic phát hiện (OCR + phân tích pixel) khác hẳn logic ffmpeg thuần của `merge/`, và `clean_video/` dành riêng cho AI inpainting theo Principle III | Gộp vào `merge/` sẽ làm file `subtitle_burner.py` gánh cả trách nhiệm "hiểu nội dung ảnh" lẫn "ghép ffmpeg" — vi phạm tách mối quan tâm đã áp dụng nhất quán cho các module khác (`asr/` tách khỏi `merge/`, `script_gen/` tách khỏi `tts/`) |

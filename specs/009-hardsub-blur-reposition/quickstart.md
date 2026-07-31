# Quickstart & Validation: Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí (009)

**Ngày**: 2026-07-30 | **Plan**: [plan.md](./plan.md) | **API**: [contracts/api.md](./contracts/api.md)

## Prerequisites

- **Constitution phải được amend TRƯỚC** — chạy `/speckit-constitution` để thêm
  Tesseract (pytesseract) + Pillow vào bảng Technology Stack (xem
  [research.md](./research.md) §9, [plan.md](./plan.md) Constitution Check).
  Không implement khi bước này chưa xong.
- Cài `tesseract-ocr` (binary hệ thống): `brew install tesseract` (macOS) hoặc
  `apt-get install tesseract-ocr` (Linux/Docker — đã có trong Dockerfile nếu
  amend đã thêm dòng cài đặt tương ứng).
- `pip install pytesseract Pillow` trong `venv/`.
- ⚠️ **Máy dev hiện tại (Homebrew ffmpeg) KHÔNG có libass** — bước burn `.ass`
  cuối cùng sẽ lỗi cục bộ (đã biết từ feature 008). Scenario A/B dưới đây tách
  riêng phần "detect + blur" (verify được ở local) và phần "burn" (chỉ verify
  được trên môi trường có libass, VD Docker image).
- edge-tts cho mọi lượt verify (Constitution VI) — KHÔNG dùng Vivibe/LucyAI.

## Unit test (chạy trước, nhanh)

```bash
./venv/bin/python -m pytest tests/unit/test_hardsub_ranges.py tests/unit/test_hardsub_detector.py tests/unit/test_subtitle_burner_ass.py tests/unit/test_review_gates_hardsub.py -v
```

Toàn bộ MUST mock `pytesseract`/`ffmpeg` thật — không test nào được gọi
Tesseract hay ffmpeg nhị phân thật (đảm bảo CI không cần cài Tesseract để test
pass). Chạy lại toàn bộ suite để xác nhận không hồi quy:

```bash
./venv/bin/python -m pytest tests/ -q
```

## Scenario A — Phát hiện vùng phụ đề gốc (US1, không cần libass)

Dùng video mẫu có hardsub cố định (VD ảnh ví dụ "Giving President Biden a
disposable camera" + dòng phụ đề vàng "Hey, Mr. President.").

1. Submit job: `hardsub_blur_enabled=true`, không khai báo `hardsub_no_ranges`.
2. Sau bước tách lời, kiểm tra `jobs/<JOB_ID>/hardsub_regions.json`:

```bash
python3 -c "import json; d=json.load(open('jobs/<JOB_ID>/hardsub_regions.json')); print(json.dumps(d,indent=2,ensure_ascii=False))"
```

3. **Kỳ vọng**: `regions[]` phủ gần hết `[0, total_duration]`; entry tương ứng
   đoạn có chữ vàng có `detected: true` với `box` khớp vùng chữ vàng (KHÔNG
   khớp vùng tiêu đề nền trắng — FR-014); nếu video có đoạn tiêu đề CHE HẾT
   màn hình không có phụ đề khớp lời nói, entry đó nên `detected: false`.

## Scenario B — Mờ đúng vùng (US1/US2, verify được ở local, không cần libass)

1. Chạy trực tiếp `hardsub/detector` + bước blur (chưa cần burn):

```bash
./venv/bin/python -c "
from hardsub import detector
from merge.subtitle_burner import apply_hardsub_blur
regions = detector.load_regions('jobs/<JOB_ID>/hardsub_regions.json')
apply_hardsub_blur('jobs/<JOB_ID>/source.mp4', 'jobs/<JOB_ID>/blurred_test.mp4', regions)
"
```

2. Mở `blurred_test.mp4` bằng trình phát video bất kỳ. **Kỳ vọng**: đúng vùng
   chữ vàng bị mờ trong đúng khoảng thời gian nó xuất hiện; dòng tiêu đề nền
   trắng KHÔNG bị mờ (US1 acceptance scenario 3); các đoạn khai báo là "không
   có phụ đề gốc" hoàn toàn không có vùng mờ nào (US2, SC-002).

## Scenario C — Burn phụ đề mới đúng vị trí (chỉ chạy được nơi có libass)

Chạy trên môi trường Docker/production hoặc máy có ffmpeg build kèm libass.

1. Submit job đầy đủ (`script_mode=translate`, `dynamic_captions=true`,
   `hardsub_blur_enabled=true`, TTS `edge-tts`) và để chạy hết tới `done`.
2. Kiểm tra `jobs/<JOB_ID>/subtitles.ass` có override `\pos()\fs` đúng ở các
   dòng rơi vào vùng đã phát hiện, KHÔNG có override ở các dòng khác.
3. Xem `output.mp4`: vùng phụ đề gốc bị mờ + phụ đề mới hiển thị đúng vị trí đó
   (cỡ chữ nhỏ hơn); các đoạn còn lại phụ đề hiển thị mặc định như trước feature
   này (SC-001, SC-003).

## Scenario D — Review vị trí tại chốt lời thoại khi bật Quản lý pipeline (US4)

1. Submit job: `supervised=true` VÀ `hardsub_blur_enabled=true`.
2. Sau bước tách lời, mở trang chi tiết job. **Kỳ vọng**: panel chốt lời thoại
   hiện thêm danh sách vùng phụ đề gốc đã dò được (kèm đoạn nào "không xác định
   được" nếu có) — cùng lúc với bảng câu transcript (contracts/api.md §2).
3. Đánh dấu 1 vùng dò sai thành "không có phụ đề gốc", lưu, rồi phê duyệt.
4. **Kỳ vọng**: `jobs/<JOB_ID>/hardsub_regions.json` — entry đó có
   `excluded: true`; `job.json.hardsub_no_ranges` đã được nối thêm khoảng
   tương ứng; sản phẩm cuối KHÔNG mờ đoạn đó (SC-007).
5. Lặp lại với job KHÔNG bật `supervised` (chỉ bật `hardsub_blur_enabled`):
   **kỳ vọng** không có panel review vùng phụ đề gốc nào, job chạy tự động hết
   (FR-013).

## Scenario E — Hồi quy (SC-006)

1. Submit job KHÔNG bật `hardsub_blur_enabled`. **Kỳ vọng**: chạy y hệt như
   trước feature 009 — không có `hardsub_regions.json`, không có `subtitles.ass`
   (vẫn `subtitles.srt` như cũ), `job.json` không có field `hardsub_*` khác
   `null`/`false`.
2. Mở lại 1 job cũ (tạo trước feature 009) — Job Detail hiển thị bình thường,
   không lỗi vì thiếu field mới.

## Definition of Done

- [ ] Constitution đã amend (Tesseract/pytesseract/Pillow trong Technology Stack)
- [ ] `pytest tests/ -q` xanh toàn bộ (gồm 4 file test mới)
- [ ] Scenario A + B chạy thật ở local (không cần libass), có `hardsub_regions.json`
      + `blurred_test.mp4` làm bằng chứng
- [ ] Scenario C chạy thật trên môi trường có libass (Docker), có `output.mp4`
      + `subtitles.ass` làm bằng chứng
- [ ] Scenario D + E đạt kỳ vọng
- [ ] Không có video nào của người dùng bị mờ nhầm dòng tiêu đề nền hộp (FR-014)

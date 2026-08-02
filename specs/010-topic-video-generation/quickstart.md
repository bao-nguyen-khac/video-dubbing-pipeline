# Quickstart & Validation: Tạo video từ chủ đề bằng AI (010)

**Ngày**: 2026-07-31 | **Plan**: [plan.md](./plan.md) | **API**: [contracts/api.md](./contracts/api.md)

## Prerequisites

- **Constitution phải được amend TRƯỚC** — chạy `/speckit-constitution` để
  thêm Pexels vào bảng Technology Stack (HyperFrames đã amend ở v1.11.0). Xem
  [plan.md](./plan.md) Constitution Check. Không implement bước gọi Pexels
  thật khi chưa amend.
- `PEXELS_API_KEY` trong `.env` — đăng ký free tại pexels.com/api.
- Node.js 22+ đã có sẵn trên máy dev (`node -v` → v22.19.0 xác nhận lúc
  brainstorm). `npx hyperframes init`/`render` cần chạy được — xác nhận trước
  khi viết `hyperframes_renderer.py` (research.md §5, spike bắt buộc).
- edge-tts cho mọi lượt verify (Constitution VI) — KHÔNG dùng LucyAI/Vivibe
  thật khi test.
- 9router (`ROUTER_BASE_URL`) phải đang chạy được — xác nhận model agent có
  tool-use thật bằng 1 lệnh gọi thử trước khi viết `topic_script_generator.py`
  (research.md §3).

## Spike bắt buộc TRƯỚC khi viết code (research.md §5)

```bash
npx hyperframes init /tmp/hf-spike-test
cd /tmp/hf-spike-test
npx hyperframes preview
npx hyperframes render
```

Ghi lại: cấu trúc thư mục project tối thiểu, cú pháp `data-*` timing thật, và
tham số CLI của `render` (output path mặc định ở đâu). Kết quả spike quyết
định chi tiết implementation của `merge/hyperframes_renderer.py` — KHÔNG viết
task chi tiết cho module này trước khi spike xong.

## Unit test (chạy trước, nhanh)

```bash
./venv/bin/python -m pytest tests/unit/test_topic_script_generator.py tests/unit/test_pexels_client.py tests/unit/test_hyperframes_renderer.py tests/unit/test_generate_pipeline.py tests/unit/test_review_gates_outline.py -v
```

Toàn bộ MUST mock 9router/Pexels/`npx hyperframes`/`ffprobe` thật (Constitution
VI) — không test nào gọi API/binary ngoài thật. Chạy lại toàn bộ suite để xác
nhận không hồi quy luồng dub hiện có:

```bash
./venv/bin/python -m pytest tests/ -q
```

## Scenario A — Tạo video KHÔNG bật quản lý pipeline (US1, chạy thẳng)

1. `POST /api/generate-jobs` với `{"topic": "tổng quan về các loại tiền tệ", "supervised": false}`.
2. Poll `GET /api/generate-jobs/{job_id}` tới khi `status == "done"`.
3. Tải `GET /api/generate-jobs/{job_id}/output` → xác nhận file MP4 hợp lệ:
   - Có audio (giọng đọc) suốt toàn bộ thời lượng.
   - Có nhiều ảnh khác nhau (không phải 1 ảnh tĩnh xuyên suốt).
   - Phụ đề hiển thị đúng khớp câu đang đọc (SC-003: lệch <0.3s).
4. Kiểm tra `jobs/{job_id}/outline.json` — `search_used` phản ánh đúng bước
   tra cứu web có chạy thành công hay không (SC-004).

**Kỳ vọng lỗi có kiểm soát**: nếu bước tra cứu web lỗi mạng (mô phỏng bằng
cách tắt 9router tạm thời ở 1 lượt test riêng), job vẫn phải ra `output.mp4`
hoàn chỉnh (FR-009) — không dừng ở `failed`.

## Scenario B — Bật quản lý pipeline, sửa outline trước khi render (US4)

1. `POST /api/generate-jobs` với `supervised: true`.
2. Poll tới khi `status == "awaiting_review"`, `review_gate == "outline"`.
3. `GET /api/jobs/{job_id}/review?gate=outline` → xác nhận `segments` chứa
   đúng số scene, `editable_field == "narration_text"`.
4. `POST /api/jobs/{job_id}/review/save` sửa `narration_text` của scene 0.
5. `POST /api/jobs/{job_id}/review/approve` → xác nhận `status` chuyển sang
   `sourcing_assets` (KHÔNG phải bước của luồng dub).
6. Sau khi job `done`, xác nhận nội dung giọng đọc scene 0 trong `output.mp4`
   KHỚP bản đã sửa, không phải bản gốc LLM sinh ra.

## Scenario C — Ảnh không tìm được kết quả phù hợp (US3)

1. Mock Pexels trả về rỗng cho 1 `image_query` cụ thể trong unit test
   `test_pexels_client.py`.
2. Xác nhận `search_image()` trả về ảnh fallback (research.md §4), KHÔNG raise
   lỗi, KHÔNG để `image_path` là `null` sau bước `sourcing_assets`.

## Rà soát cuối trước khi coi feature hoàn thành

- [ ] Constitution đã amend đủ 2 dòng (HyperFrames + Pexels) trước khi chạy
      Scenario A/B/C với API thật.
- [ ] `Dockerfile` build được với Node.js 22+ + Chrome headless deps
      (research.md §8) — verify trên image Docker thật, không chỉ máy dev macOS.
- [ ] `find_running_job_id()` chặn đúng khi có 1 job dub VÀ 1 job generate cố
      chạy đồng thời (research.md §1).
- [ ] Toàn bộ `pytest tests/ -q` xanh, không hồi quy luồng dub hiện có.

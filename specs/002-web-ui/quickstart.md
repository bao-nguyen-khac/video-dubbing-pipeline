# Quickstart: Validate Web UI (US1 MVP)

## Prerequisites

- Đã hoàn tất setup của [001-video-repurpose-pipeline](../001-video-repurpose-pipeline/quickstart.md)
  (`.env` có `ROUTER_BASE_URL`/`ROUTER_API_KEY`/`ROUTER_MODEL`, `ffmpeg`, 9router
  đang chạy).
- Thêm vào `.env`: `WEB_UI_USERNAME`, `WEB_UI_PASSWORD` (xem `.env.example`).
- Node.js 18+ (chỉ để build frontend, không phải runtime pipeline).

## Setup

```bash
cd media-generation

# Backend
pip install -r requirements.txt   # đã thêm fastapi, uvicorn, itsdangerous

# Frontend
cd web/frontend
npm install
npm run build                      # build ra static file cho FastAPI serve
cd ../..
```

## Run

```bash
uvicorn web.backend.main:app --host 127.0.0.1 --port 8000
```

Mở trình duyệt tại `http://127.0.0.1:8000`.

## Expected Outcome (US1)

1. Truy cập lần đầu → thấy trang đăng nhập, không thấy form chạy job (FR-010).
2. Đăng nhập bằng `WEB_UI_USERNAME`/`WEB_UI_PASSWORD` → vào trang chủ, thấy form
   nhập URL + chọn `translate`/`rewrite`.
3. Dán 1 URL TikTok công khai, chọn `translate`, bấm chạy → thấy trạng thái
   "đang tải video" xuất hiện ngay, % tiến trình bắt đầu tăng theo bước
   (contracts/api.md → polling contract).
4. Job hoàn tất → thấy nút xem/tải video, mở được video trực tiếp trên trình
   duyệt (FR-004).
5. Đóng tab giữa lúc job đang chạy, mở lại `http://127.0.0.1:8000/jobs` → job
   vẫn đang chạy hoặc đã xong, trạng thái đúng thực tế (Edge Case: đóng browser).

## Validate US1 — Chặn submit khi có job đang chạy (FR-009)

Trong lúc 1 job đang chạy, mở tab mới, thử submit URL khác → API trả `409`,
giao diện hiển thị "đang có job xử lý" kèm % tiến trình của job đang chạy, KHÔNG
cho bấm nút chạy.

## Validate US2 — Lịch sử job

Sau khi có ≥2 job đã chạy, vào trang danh sách → thấy cả 2 job kèm trạng thái
đúng; mở chi tiết 1 job → thấy URL nguồn, chế độ kịch bản, cảnh báo (nếu có),
video (nếu xong) — đúng [data-model.md](./data-model.md#job-detail).

## Validate US3 — Cảnh báo + Retry job lỗi

1. Chạy 1 job với URL sẽ lỗi (VD URL không tồn tại) → job `failed`, trang chi
   tiết hiển thị rõ bước lỗi + nút "Thử lại".
2. Bấm "Thử lại" → `POST /api/jobs/{job_id}/retry` → job resume đúng từ artifact
   đã có (không tải lại từ đầu nếu `source.mp4` đã tồn tại).

## References

- API đầy đủ: [contracts/api.md](./contracts/api.md)
- Response shape: [data-model.md](./data-model.md)
- Quyết định thiết kế (polling, session, background thread): [research.md](./research.md)

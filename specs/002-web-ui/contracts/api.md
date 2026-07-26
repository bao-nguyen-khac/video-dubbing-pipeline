# Contract: Web UI REST API

Base URL: `http://127.0.0.1:8000` (localhost, xem Clarification Q1). Mọi endpoint
trừ `/api/login` MUST require session cookie hợp lệ (FR-010) — thiếu/hết hạn trả
`401 Unauthorized`.

## POST /api/login

**Auth**: Không cần (đây là endpoint tạo session).

**Request body**:
```json
{ "username": "string", "password": "string" }
```

**Response**:
- `200 OK` — set-cookie session (HttpOnly, 7 ngày), body `{"ok": true}`.
- `401 Unauthorized` — sai username/password, body `{"error": "Sai tài khoản hoặc mật khẩu"}`.

## POST /api/logout

**Auth**: Required.

**Response**: `200 OK`, xoá session cookie.

## GET /api/jobs

**Auth**: Required.

Trả danh sách Job Summary (xem [data-model.md](../data-model.md#job-summary)),
sắp xếp theo `created_at` giảm dần.

**Response**: `200 OK`
```json
{ "jobs": [ { "job_id": "...", "source_url": "...", "platform": "tiktok", "status": "done", "progress_percent": 100, "created_at": "..." } ] }
```

## POST /api/jobs

**Auth**: Required.

Submit job mới (US1, FR-001/FR-002). Validate URL thuộc TikTok/Douyin/YouTube
trước khi tạo job (FR-002) — không gọi `detect_platform()` của `pipeline.py`
lại nếu không cần, tái dùng trực tiếp hàm đó.

**Request body**:
```json
{ "url": "string", "script_mode": "translate | rewrite" }
```

**Response**:
- `201 Created` — `{ "job_id": "..." }`, job bắt đầu chạy nền ngay (research.md → job_runner).
- `400 Bad Request` — URL không hợp lệ/không thuộc 3 nền tảng (FR-002).
- `409 Conflict` — đang có job khác chạy (FR-009): `{ "error": "Đang có job xử lý, vui lòng chờ", "running_job_id": "..." }`.

## GET /api/jobs/{job_id}

**Auth**: Required.

Trả Job Detail (xem [data-model.md](../data-model.md#job-detail)).

**Response**:
- `200 OK` — Job Detail.
- `404 Not Found` — job_id không tồn tại.

## GET /api/jobs/{job_id}/output

**Auth**: Required.

Stream/download file `output.mp4` của job (FR-004).

**Response**:
- `200 OK` — `Content-Type: video/mp4`, stream file.
- `404 Not Found` — job chưa có output (chưa `done`) hoặc job_id không tồn tại.

## POST /api/jobs/{job_id}/retry

**Auth**: Required.

Resume một job đã `failed` (US3, FR-008) — gọi lại `pipeline.run_pipeline()` với
cùng `job_id` (đúng cơ chế resume đã có ở
[contracts/cli.md của 001](../../001-video-repurpose-pipeline/contracts/cli.md#idempotency)).

**Response**:
- `202 Accepted` — job resume bắt đầu chạy nền, `{ "job_id": "..." }`.
- `404 Not Found` — job_id không tồn tại.
- `409 Conflict` — job không ở trạng thái `failed` (không thể retry job đang
  chạy/đã xong), hoặc đang có job khác chạy.

## Polling contract (frontend)

Sau khi `POST /api/jobs` hoặc `POST /api/jobs/{job_id}/retry` thành công,
frontend MUST poll `GET /api/jobs/{job_id}` mỗi 3 giây cho tới khi
`status ∈ {"done", "failed"}` (research.md → Cập nhật tiến trình phía frontend).

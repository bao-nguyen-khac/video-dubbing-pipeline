# API Contracts: Tạo video từ chủ đề bằng AI (010)

**Ngày**: 2026-07-31 | **Plan**: [../plan.md](../plan.md) | **Kiểu dữ liệu**: [../data-model.md](../data-model.md)

Thêm **router mới** `web/backend/generate_jobs_api.py`, prefix
`/api/generate-jobs` — KHÔNG mở rộng `/api/jobs` hiện có vì payload/state
machine khác hẳn (data-model.md §5). Route review gate (`/api/jobs/{id}/review`)
được TÁI DÙNG nguyên vẹn (đã generic theo `gate` — research.md §7), chỉ cần
`GATE_OUTLINE` hợp lệ trong `review/gates.py`. Quy ước lỗi giữ nguyên
`{"error": "..."}` như các feature trước.

---

## 1. `POST /api/generate-jobs` — tạo job mới (FR-001, FR-002)

Request:

```json
{
  "topic": "tổng quan về các loại tiền tệ",
  "supervised": false
}
```

| Field | Type | Default | Ghi chú |
|---|---|---|---|
| `topic` | `string` | bắt buộc | Không rỗng sau khi `.strip()` — 400 nếu rỗng |
| `supervised` | `bool` | `false` | Bật chốt duyệt outline/scene (FR-012) — cùng khái niệm với luồng dub, field riêng trên job này |

Response `201`: `{"job_id": "..."}` — cùng format `POST /api/jobs`.

Lỗi:
- `400` — `topic` rỗng.
- `409` — đang có job khác (dub HOẶC generate) chạy, dùng chung
  `find_running_job_id()` (research.md §1: 1 hàng đợi cho cả 2 loại job).

## 2. `GET /api/generate-jobs` — danh sách job "generate"

Response: mảng job summary, CÙNG shape với `GET /api/jobs` nhưng lọc
`job_type == "generate"` — field `topic` thay cho `source_url`/`platform`.
Frontend gộp 2 danh sách (dub + generate) để hiển thị 1 danh sách job duy nhất
cho người dùng — chi tiết UI thuộc tasks.md, không thuộc phạm vi contract này.

## 3. `GET /api/generate-jobs/{job_id}` — chi tiết job

Response: `job.json` đã lọc field nội bộ, tương tự `GET /api/jobs/{job_id}` —
thêm field `topic`, `scenes` (rút gọn: chỉ `index`/`narration_text` để hiển
thị tiến trình, KHÔNG trả `image_path`/`voice_path` tuyệt đối — dùng endpoint
riêng §5 nếu cần xem ảnh).

## 4. `GET /api/generate-jobs/{job_id}/output` — tải video hoàn chỉnh

Giống hệt `GET /api/jobs/{job_id}/output` (`FileResponse` `output.mp4`, 404 nếu
job chưa `done`).

## 5. `GET /api/jobs/{job_id}/review` — tái dùng, mở rộng `gate="outline"`

Khi `job_type="generate"` và `supervised=true`, job dừng ở
`review_gate="outline"`. Payload dùng ĐÚNG shape đã có (`review/gates.py::build_payload()`,
research.md §7) — không cần sửa route, chỉ cần `GATE_OUTLINE` hợp lệ:

```json
{
  "job_id": "...",
  "gate": "outline",
  "editable_field": "narration_text",
  "can_regenerate": false,
  "segments": [
    {"index": 0, "start": null, "end": null, "text": "Tiền tệ đã tồn tại...", "source_text": null}
  ]
}
```

- `start`/`end`: `null` — Scene chưa có timing thật ở bước này (`duration` chỉ
  có SAU khi TTS chạy, data-model.md §3) — client KHÔNG hiển thị timeline ở
  chốt này, chỉ hiển thị danh sách scene dạng text.
- `can_regenerate`: `false` ở v1 (khác `GATE_SCRIPT` cho phép sinh lại) — sinh
  lại toàn bộ outline/scene từ đầu chưa nằm trong scope FR-012; người dùng chỉ
  sửa tay từng `narration_text`.
- Field `image_query` KHÔNG xuất hiện trong payload editable (research.md §7,
  data-model.md §3: không editable ở v1) — nếu client cần hiển thị tham khảo,
  đây là điểm mở rộng payload sau, không phải v1.

## 6. `POST /api/jobs/{job_id}/review/save` và `.../approve` — tái dùng nguyên vẹn

Không đổi route/schema — `save_edits()`/`mark_approved()` (`review/gates.py`)
áp dụng được ngay cho `gate="outline"` vì đã tổng quát theo
`data["segments"][i][editable_field]` (research.md §7). `approve` với
`gate="outline"` chuyển `job.json.status` sang `sourcing_assets`
(`NEXT_STATUS_AFTER_GATE["outline"]`, data-model.md §5) thay vì bước của luồng
dub.

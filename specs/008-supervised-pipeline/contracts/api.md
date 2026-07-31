# API Contracts: Chế độ quản lý pipeline (008-supervised-pipeline)

**Ngày**: 2026-07-30 | **Plan**: [../plan.md](../plan.md) | **Kiểu dữ liệu**: [../data-model.md](../data-model.md)

Quy ước dùng chung với các feature trước:

- Mọi endpoint nằm dưới `/api/jobs` → đi qua auth middleware sẵn có
  (`web/backend/main.py`); thiếu/hết hạn session → `401 {"error": "..."}`.
- Lỗi luôn có dạng `{"error": "<tiếng Việt, giải thích được cho người dùng>"}`,
  có thể kèm field phụ (vd `running_job_id`) — theo `_error()` trong `jobs_api.py`.
- `Content-Type: application/json` cho request có body.

---

## 1. `POST /api/jobs` — mở rộng (FR-001, FR-002)

Thêm **một** field vào `SubmitJobRequest`:

| Field | Type | Default | Ghi chú |
|---|---|---|---|
| `supervised` | `bool` | `false` | Bật chế độ quản lý pipeline. **Mặc định tắt** (FR-002) |

Không đổi validation, không đổi response (`201 {"job_id": "..."}`). Client cũ
không gửi field này vẫn chạy liền mạch như trước.

## 2. `GET /api/jobs/{job_id}/review` — lấy nội dung chốt (FR-009, FR-010, FR-016)

**200 OK**

```json
{
  "job_id": "job-26-07-30-11-05-123",
  "gate": "script",
  "editable_field": "translated_text",
  "edited": false,
  "can_regenerate": true,
  "reached_at": "2026-07-30T04:21:40+00:00",
  "segments": [
    {
      "index": 0,
      "start": 0.0,
      "end": 1.94,
      "text": "Này MrBeast, nếu tôi đưa anh máy ảnh này,",
      "source_text": "Hey Mr. Beast, if I give you this camera,"
    }
  ]
}
```

- `gate == "transcript"` → `editable_field: "text"`, `source_text` là `null` ở mọi
  segment, `can_regenerate: false`.
- `segments` **có thể rỗng** (`[]`) — video không có lời thoại. Đây là phản hồi
  **thành công**, không phải lỗi (spec, Edge Cases; research.md §10).
- `start`/`end` chỉ để hiển thị, client MUST render read-only (FR-016).

**Lỗi**

| Code | Khi nào | Body |
|---|---|---|
| 404 | job không tồn tại | `{"error": "Job không tồn tại"}` |
| 409 | `status != "awaiting_review"` | `{"error": "Job không đang chờ duyệt (trạng thái: <status>)", "status": "<status>"}` |

## 3. `PUT /api/jobs/{job_id}/review` — lưu bản sửa (FR-011..FR-014)

**Request**

```json
{
  "gate": "script",
  "segments": [
    { "index": 0, "text": "Này MrBeast, nếu tôi đưa anh chiếc máy ảnh này," },
    { "index": 1, "text": "" }
  ]
}
```

- `gate` MUST khớp `job.review_gate` — chống tab cũ lưu sai chốt.
- Chỉ `index` + `text` được đọc. `start`/`end`/`source_text` client gửi lên bị
  **bỏ qua im lặng** (FR-016).
- Chỉ cần gửi các segment muốn đổi; segment không xuất hiện trong body giữ nguyên
  nội dung đã lưu.
- `text` rỗng hoặc chỉ khoảng trắng ⟹ **bỏ câu đó** khỏi file đã lưu (FR-013).

**200 OK**

```json
{ "job_id": "...", "gate": "script", "saved_count": 39, "dropped_count": 1 }
```

`saved_count` = số câu còn lại sau khi bỏ câu rỗng; `dropped_count` = số câu bị bỏ
ở lượt này. Lưu **không** đổi `status` (vẫn `awaiting_review`) — đúng FR-011 "lưu
nháp rồi quay lại sau".

**Lỗi**

| Code | Khi nào | Body |
|---|---|---|
| 400 | mọi câu đều rỗng sau khi lọc | `{"error": "Không thể lưu: toàn bộ các câu đều rỗng, các bước sau sẽ không có gì để xử lý"}` — **không ghi file** (FR-014) |
| 400 | `index` không tồn tại | `{"error": "Câu số <i> không tồn tại trong chốt này"}` |
| 400 | `gate` không khớp | `{"error": "Chốt không khớp: job đang chờ duyệt tại '<gate>'"}` |
| 404 | job không tồn tại | `{"error": "Job không tồn tại"}` |
| 409 | `status != "awaiting_review"` | như §2 |

## 4. `POST /api/jobs/{job_id}/review/approve` — phê duyệt (FR-017..FR-019)

**Request**: `{ "gate": "transcript" }` — bắt buộc, để chống duyệt sai chốt.

**202 Accepted**

```json
{ "job_id": "...", "approved_gate": "transcript", "resumed_status": "scripting" }
```

`resumed_status` = `"scripting"` (duyệt chốt lời thoại) hoặc `"synthesizing"`
(duyệt chốt kịch bản).

**Lỗi**

| Code | Khi nào | Body |
|---|---|---|
| 409 | `status != "awaiting_review"` — gồm cả **cú click thứ hai** (FR-019) | `{"error": "Job không đang chờ duyệt (trạng thái: <status>)", "status": "<status>"}` |
| 409 | `gate` không khớp | `{"error": "Chốt không khớp: job đang chờ duyệt tại '<gate>'"}` |
| 409 | có job khác đang xử lý (FR-018) | `{"error": "Đang có job khác xử lý, vui lòng chờ rồi phê duyệt lại", "running_job_id": "<id>"}` |
| 404 | job không tồn tại | `{"error": "Job không tồn tại"}` |

**MUST**: ở cả 3 nhánh 409, job giữ nguyên `status="awaiting_review"`, `review_gate`
cũ và toàn bộ nội dung đã lưu — không được đánh dấu lỗi, không được mất bản sửa
(FR-018).

**Thứ tự thực hiện** (research.md §6, trong một `threading.Lock` cấp module):
đọc job → kiểm tra status → kiểm tra gate → kiểm tra job khác đang chạy → ghi
`status` mới + `review_gate=null` + `review_gates[gate].approved_at` → thoát lock →
`start_job()`.

## 5. `POST /api/jobs/{job_id}/review/regenerate` — sinh lại kịch bản (FR-020)

Chỉ hợp lệ ở chốt **`script`**. Không có body.

**202 Accepted**

```json
{ "job_id": "...", "regenerated_count": 1 }
```

Hành vi: xoá `script.json` + `script_original.json`, ghi `status="scripting"`,
`review_gate=null`, `review_gates.script.approved_at=null`,
`review_gates.script.edited=false`, tăng `regenerated_count`, rồi `start_job()`.
Bước scripting sinh lại từ `transcript_reviewed.json` (lời thoại **đã duyệt**, giữ
nguyên không bị đổi) và job dừng lại tại **chính chốt `script`**.

**Lỗi**

| Code | Khi nào | Body |
|---|---|---|
| 409 | `review_gate != "script"` | `{"error": "Chỉ sinh lại được kịch bản ở chốt kịch bản"}` |
| 409 | `status != "awaiting_review"` | như §4 |
| 409 | có job khác đang xử lý | như §4 |
| 404 | job không tồn tại | `{"error": "Job không tồn tại"}` |

**Cảnh báo ghi đè** (FR-020, US4-2) là **hộp xác nhận ở frontend** trước khi gọi
endpoint này — API không có bước xác nhận hai pha.

## 6. `GET /api/jobs` và `GET /api/jobs/{job_id}` — field thêm (FR-006)

| Endpoint | Field thêm | Type |
|---|---|---|
| `GET /api/jobs` (mỗi item) | `review_gate` | `"transcript" \| "script" \| null` |
| `GET /api/jobs/{job_id}` | `review_gate`, `supervised`, `review_url` | `... \| null`, `bool`, `string \| null` |

`status: "awaiting_review"` là giá trị mới client MUST xử lý như một nhóm **riêng**
— không phải `running`, không phải `failed` (FR-006).

## 7. CLI (`pipeline.py`) — flag thêm

```text
--supervised    Bật chế độ quản lý pipeline: dừng chờ phê duyệt sau bước tách lời
                và sau bước sinh kịch bản. Chỉ có tác dụng với --script-mode
                translate/rewrite/subtitle (bị bỏ qua với download).
```

Chạy tới chốt, CLI in rõ trạng thái rồi thoát code **0** (dừng chờ duyệt là kết
quả bình thường, không phải lỗi):

```text
[pipeline][job-...] ⏸ Dừng chờ duyệt tại chốt lời thoại (42 câu).
[pipeline][job-...]   Review và phê duyệt trên web UI, hoặc chạy lại với --job-id sau khi duyệt.
```

Phê duyệt **chỉ** làm được qua web UI (FR-017: "hành động tường minh trên giao
diện web") — CLI không có flag `--approve`.

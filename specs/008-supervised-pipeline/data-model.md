# Data Model: Chế độ quản lý pipeline (008-supervised-pipeline)

**Ngày**: 2026-07-30 | **Plan**: [plan.md](./plan.md) | **Quyết định nền**: [research.md](./research.md)

Không có database. Toàn bộ state nằm trong file JSON dưới `jobs/{job_id}/`.
Tài liệu này chỉ ghi phần **thêm/đổi**; mọi field không nhắc tới giữ nguyên.

---

## 1. State machine (`pipeline.py`)

### Status mới

`awaiting_review` — job đã hoàn thành một bước có chốt và đang chờ người dùng phê
duyệt. **Không phải** đang xử lý, **không phải** lỗi.

```text
pending → downloading → transcribing ─┬─────────────────→ scripting ─┬──────────────────→ synthesizing → merging → done
                                      │                              │
                                      └→ awaiting_review ────────────┘   └→ awaiting_review ─→ synthesizing
                                         (review_gate="transcript")         (review_gate="script")
                    ↘ failed (từ mọi bước đang xử lý)
```

### `VALID_TRANSITIONS` — 3 dòng thay đổi

| Status | Trước | Sau |
|---|---|---|
| `transcribing` | `["scripting", "failed"]` | `["scripting", "awaiting_review", "failed"]` |
| `scripting` | `["synthesizing", "failed"]` | `["synthesizing", "awaiting_review", "failed"]` |
| `awaiting_review` | *(không có)* | `["scripting", "synthesizing", "failed"]` |

`awaiting_review → scripting` phục vụ **hai** đường: phê duyệt chốt 1, và sinh lại
kịch bản ở chốt 2 (FR-020). Endpoint tương ứng mới là chỗ quyết định đường nào
hợp lệ theo `review_gate`, không phải bảng transition.

Thêm `"awaiting_review"` vào `StatusLiteral`.

## 2. `jobs/{job_id}/job.json` — field thêm

| Field | Type | Default | Ý nghĩa |
|---|---|---|---|
| `supervised` | `bool` | `false` | Bật chế độ quản lý pipeline. Đặt lúc `create_job()`, **không đổi** trong suốt đời job (FR-003, Assumption "chỉ chọn lúc tạo job") |
| `review_gate` | `"transcript" \| "script" \| null` | `null` | Chốt đang chờ duyệt. Chỉ khác `null` khi `status == "awaiting_review"` |
| `review_gates` | `object` | `{}` | Lịch sử từng chốt, xem dưới |
| `artifacts.transcript_reviewed` | `string \| null` | `null` | Đường dẫn `transcript_reviewed.json` (chỉ job supervised) |

### `review_gates`

```json
{
  "transcript": {
    "reached_at": "2026-07-30T04:12:11+00:00",
    "approved_at": "2026-07-30T04:19:02+00:00",
    "segment_count": 42,
    "edited": true
  },
  "script": {
    "reached_at": "2026-07-30T04:21:40+00:00",
    "approved_at": null,
    "segment_count": 40,
    "edited": false,
    "regenerated_count": 1
  }
}
```

| Key | Type | Ghi chú |
|---|---|---|
| `reached_at` | ISO-8601 UTC | Thời điểm pipeline dừng ở chốt. Ghi lại mỗi lần vào chốt (sinh lại kịch bản sẽ ghi đè) |
| `approved_at` | ISO-8601 UTC \| `null` | `null` = chưa duyệt. Là **bằng chứng audit** (Principle VI) rằng chốt đã qua |
| `segment_count` | `int` | Số câu tại thời điểm lưu gần nhất (0 là hợp lệ ở `transcript` — video không lời) |
| `edited` | `bool` | Đã có ≥1 lượt `PUT` lưu bản sửa |
| `regenerated_count` | `int` | Chỉ ở `script` — số lượt bấm sinh lại |

**Bất biến** (agent thực thi MUST giữ, và MUST có test khẳng định):

- `status == "awaiting_review"` ⟺ `review_gate != null`
- `supervised == false` ⟹ `review_gate == null` và `review_gates == {}`
- `review_gates.script.approved_at != null` ⟹ `review_gates.transcript.approved_at != null`
  (không thể duyệt chốt 2 mà chưa qua chốt 1)
- Sau khi `approved_at` của một chốt đã có giá trị, retry/resume **MUST NOT** đưa
  job về `awaiting_review` ở chính chốt đó (FR-023) — trừ đúng một ngoại lệ: bấm
  sinh lại kịch bản, khi đó `script.approved_at` được reset về `null`.

## 3. `jobs/{job_id}/transcript_reviewed.json` (MỚI)

Payload chốt 1 và là đầu vào thật của bước scripting với job supervised.

```json
{
  "source": "transcript.json",
  "resegmented": true,
  "segments": [
    { "start": 0.0, "end": 1.94, "text": "Này MrBeast, nếu tôi đưa anh máy ảnh này," }
  ]
}
```

| Field | Ghi chú |
|---|---|
| `segments[].start` / `.end` | `float`, giây. **Read-only** (FR-016) — API MUST bỏ qua nếu client gửi lên |
| `segments[].text` | `string`, trường **duy nhất** sửa được |
| `resegmented` | `true` nếu `resegment_by_sentences()` cắt lại thành công; `false` nếu fallback (transcript cũ thiếu `words`, hoặc LLM lỗi) |

**KHÔNG có key `words`** — cố ý, và là điều kiện đúng đắn của toàn feature: nó vô
hiệu hoá `resegment_by_sentences()` ở bước scripting nên phần sửa tay không bị ghi
đè (research.md §3). Agent thực thi **MUST NOT** thêm `words` vào file này.

Sinh ra ở cuối bước transcribing (chỉ job supervised), từ
`resegment_by_sentences(transcript["segments"], _chat_completion)` rồi lược mỗi
segment còn đúng `start`/`end`/`text`.

## 4. `jobs/{job_id}/script.json` — sửa tại chỗ

Schema **không đổi** (`mode`, `content`, `target_language`, `segments[]` với
`start`/`end`/`source_text`/`translated_text`). Chốt 2 sửa **chỉ**
`segments[].translated_text`.

Sau mỗi lượt lưu, `content` MUST được tính lại từ các `translated_text` còn lại —
`" ".join(...)` — để khớp cách `generate_script()` tạo nó
(router_client.py:371) và không để lại nội dung cũ gây nhầm khi debug.

## 5. `jobs/{job_id}/script_original.json` (MỚI)

Bản sao nguyên trạng của `script.json` do LLM sinh, tạo **một lần** ngay trước
lượt `PUT` đầu tiên ở chốt 2. Chỉ để audit/đối chiếu, **không** bước nào đọc.
Bị xoá kèm khi bấm sinh lại kịch bản (research.md §8).

## 6. Review Payload (API, không phải file)

Hình dạng dữ liệu `GET /api/jobs/{job_id}/review` trả về — hợp đồng đầy đủ ở
[contracts/api.md](./contracts/api.md).

| Field | Type | Ghi chú |
|---|---|---|
| `gate` | `"transcript" \| "script"` | Lấy từ `job.review_gate` |
| `editable_field` | `"text" \| "translated_text"` | Để frontend dùng một component cho cả 2 chốt |
| `segments[].index` | `int` | 0-based, **khoá định danh** khi `PUT` (không dùng mốc thời gian làm khoá) |
| `segments[].start` / `.end` | `float` | Read-only (FR-016) |
| `segments[].text` | `string` | Nội dung sửa được (chốt 2: đây là `translated_text`) |
| `segments[].source_text` | `string \| null` | Chỉ chốt 2 — câu gốc để đối chiếu (FR-010) |
| `edited` | `bool` | `review_gates[gate].edited` |
| `can_regenerate` | `bool` | `gate == "script"` (FR-020) |

## 7. Job Summary / Job Detail (API hiện có) — field thêm

| Field | Có ở | Ghi chú |
|---|---|---|
| `review_gate` | Summary + Detail | Để danh sách job nói rõ "chờ duyệt tại chốt nào" (FR-006) |
| `supervised` | Detail | Hiển thị job này có bật chế độ quản lý |
| `review_url` | Detail | `/api/jobs/{id}/review` nếu `status == "awaiting_review"`, ngược lại `null` |

`progress_percent` khi `status == "awaiting_review"`: `review_gate == "transcript"`
→ **40**, `review_gate == "script"` → **56**. Chèn giữa `transcribing` (32) và
`synthesizing` (65) của `_STATUS_PROGRESS_MAP` hiện có, đúng nghĩa "bước trước đã
xong, bước sau chưa bắt đầu".

`can_retry` giữ nguyên `status == "failed"` — job chờ duyệt **không** phải job cần
retry, nó cần phê duyệt.

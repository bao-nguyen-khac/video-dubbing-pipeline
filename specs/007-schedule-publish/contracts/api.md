# API Contract: hẹn giờ đăng (007-schedule-publish)

**Data model**: [../data-model.md](../data-model.md) · **Research**: [../research.md](../research.md)

Mở rộng contract của [006](../../006-publish-video-tab/contracts/api.md). Chỉ ghi
phần **thay đổi**; endpoint nào không nhắc tới thì giữ nguyên.

Quy ước múi giờ xuyên suốt: **API nhận và trả UTC** (`...Z`); giao diện tự quy
đổi sang giờ Việt Nam để hiển thị (research.md §2).

---

## POST /api/publish *(mở rộng)*

**Request** — thêm 2 trường tuỳ chọn:

```json
{
  "job_id": "job-26-07-28-12-07-735",
  "platform": "tiktok",
  "account_id": "acc_123",
  "title": "Tiêu đề video",
  "publish_mode": "scheduled",
  "scheduled_for": "2026-07-29T03:00:00Z"
}
```

- `publish_mode`: `"now"` (mặc định khi vắng — giữ tương thích ngược) hoặc `"scheduled"`
- `scheduled_for`: bắt buộc khi `publish_mode="scheduled"`, ISO 8601 **UTC**

**202** `{"attempt_id": "…", "status": "pending"}` — xử lý chạy nền như cũ.

**Lỗi bổ sung**

| Mã | Khi nào | Ví dụ `error` |
|---|---|---|
| `400` | `publish_mode="scheduled"` mà thiếu `scheduled_for` | `"Thiếu thời điểm hẹn giờ"` |
| `400` | `scheduled_for` cách hiện tại < 15 phút (FR-003) | `"Phải hẹn cách ít nhất 15 phút — video cần thời gian tải lên"` |
| `400` | `scheduled_for` cách hiện tại > 3 ngày (FR-004) | `"Chỉ hẹn được tối đa 3 ngày"` |
| `409` | Đã có lượt đăng `pending`/`publishing`/**`scheduled`** cho cùng job + nền tảng | `{"error": "Video này đã có bài đang chờ đăng lên nền tảng đã chọn", "attempt_id": "…"}` |

Mọi lỗi của đăng ngay (tiêu đề rỗng, job chưa xong, vượt giới hạn nền tảng, kênh
bị ngắt) áp dụng y nguyên và kiểm **ngay tại đây**, không đợi tới giờ (FR-014).

---

## DELETE /api/publish/attempts/{attempt_id} *(mới)*

Huỷ một bài đang chờ đăng (FR-011).

**200** `{"ok": true}`

| Mã | Khi nào | Ví dụ `error` |
|---|---|---|
| `404` | Không có attempt đó | `"Lượt đăng không tồn tại"` |
| `409` | Attempt không ở trạng thái `scheduled` (FR-012) | `"Bài đã đăng rồi, không huỷ được từ đây — xoá trực tiếp trên nền tảng"` |
| `409` | Attempt đang `publishing` | `"Bài đang được đăng, không huỷ được nữa"` |
| `502` | Zernio không huỷ được | `"Không huỷ được bài ở dịch vụ đăng bài: …"` |

**Bắt buộc về thứ tự**: gọi Zernio huỷ **trước**, thành công mới ghi `cancelled`
vào file. Zernio lỗi ⇒ trạng thái giữ nguyên `scheduled` (research.md §5) — ghi
`cancelled` khi chưa huỷ được thật là nói dối người dùng về một việc không đảo
ngược được.

---

## DELETE /api/publish/connections/{account_id} *(mở rộng)*

Ngoài việc chặn cục bộ như cũ, nay **huỷ luôn mọi bài đang chờ** của kênh đó
(FR-015).

**200**

```json
{
  "ok": true,
  "cancelled_attempts": [
    { "attempt_id": "…", "title": "Tiêu đề video", "scheduled_for": "2026-07-29T03:00:00Z" }
  ],
  "warning": "…"
}
```

- `cancelled_attempts`: các bài vừa bị huỷ theo — giao diện PHẢI hiển thị cho
  người dùng biết (FR-015). Mảng rỗng nếu không có bài nào đang chờ.
- `warning`: có mặt khi một phần thao tác thất bại (vd huỷ được 1/2 bài). Vẫn
  trả `200` vì kênh **đã bị chặn**, nhưng người dùng cần biết bài nào còn treo ở
  Zernio để tự xử lý.

---

## GET /api/publish/attempts · GET /api/publish/attempts/{attempt_id} *(mở rộng)*

Trước khi trả về, backend **đối soát lười** những attempt đáng nghi (data-model
§2) rồi mới trả trạng thái đã cập nhật (FR-009).

Mỗi phần tử thêm 2 trường:

```json
{
  "attempt_id": "…",
  "job_id": "…",
  "platform": "tiktok",
  "account_label": "@mychannel",
  "title": "Tiêu đề video",
  "status": "scheduled",
  "publish_mode": "scheduled",
  "scheduled_for": "2026-07-29T03:00:00Z",
  "error": null,
  "error_kind": null,
  "post_url": null,
  "created_at": "2026-07-28T12:00:00Z",
  "updated_at": "2026-07-28T12:00:05Z"
}
```

`status` nay có thêm `scheduled` và `cancelled`.

Hỗ trợ lọc tuỳ chọn `?status=scheduled` để giao diện lấy riêng danh sách đang
chờ đăng (FR-010), sắp xếp theo `scheduled_for` **tăng dần** (gần nhất trước) —
khác với lịch sử chung vốn sắp theo `created_at` giảm dần.

---

## Ánh xạ sang Zernio *(bổ sung cho 006)*

| Việc | Lời gọi |
|---|---|
| Đặt lịch | `POST /v1/posts` — thay `publishNow: true` bằng `scheduledFor` + `timezone` |
| Huỷ bài chờ | `DELETE /v1/posts/{postId}` |
| Đối soát | `GET /v1/posts/{postId}` (đã dùng ở 006) |

### Body `POST /v1/posts` khi hẹn giờ

```json
{
  "content": "<tiêu đề>",
  "mediaItems": [{ "type": "video", "url": "<publicUrl từ presign>", "mimeType": "video/mp4" }],
  "platforms": [{ "platform": "tiktok", "accountId": "<_id>" }],
  "scheduledFor": "2026-07-29T03:00:00Z",
  "timezone": "Asia/Ho_Chi_Minh",
  "tiktokSettings": { "…": "giữ nguyên như 006" }
}
```

- **KHÔNG** gửi `publishNow` cùng lúc.
- `scheduledFor` gửi mốc **UTC tuyệt đối** (`...Z`) — không phụ thuộc cách Zernio
  diễn giải `timezone`, tránh lệch 7 tiếng (research.md §2).
- `timezone` nhận tên IANA; gửi kèm cho đúng ngữ nghĩa phía Zernio.
- `tiktokSettings` giữ nguyên như đăng ngay, gồm cả mức công khai đặt tường minh.

### Ánh xạ lỗi

Dùng lại nguyên bảng của 006. Riêng `DELETE /v1/posts/{postId}`:

| Zernio | Ý nghĩa |
|---|---|
| `400` | Bài đã đăng rồi, không xoá được ⇒ trả `409` cho người dùng |
| `404` | Bài không còn ở Zernio ⇒ coi như đã huỷ, ghi `cancelled` (không báo lỗi) |

# Data Model: 007-schedule-publish

**Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

Không thêm thực thể mới. Tính năng này **mở rộng Publish Attempt** đã có ở
[006 data-model.md §1](../006-publish-video-tab/data-model.md). Vẫn là file JSON,
không database.

---

## 1. Publish Attempt (mở rộng)

**File**: `jobs/{job_id}/publishes/{attempt_id}.json` — không đổi vị trí.

### 1.1 Trường mới

| Field | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `publish_mode` | `"now" \| "scheduled"` | ✓ | Hình thức đăng (FR-001). Attempt tạo trước tính năng này không có field → đọc mặc định `"now"` |
| `scheduled_for` | string (ISO 8601, **UTC**) \| null | ✓ | Thời điểm sẽ đăng. `null` khi `publish_mode="now"` |

**Bất biến về múi giờ**: `scheduled_for` trong file **luôn là UTC**. Quy đổi
sang/từ giờ Việt Nam chỉ xảy ra ở biên giao diện (research.md §2). Không bao giờ
lưu giờ "trần" không rõ múi.

### 1.2 Trạng thái mới

Bổ sung 2 giá trị vào `status` (các giá trị cũ giữ nguyên):

| Status | Ý nghĩa |
|---|---|
| `scheduled` | Zernio đã nhận bài và đang chờ tới giờ đăng |
| `cancelled` | Người dùng huỷ trước giờ đăng, hoặc bị huỷ theo khi ngắt kết nối kênh |

### 1.3 Chuyển trạng thái

```text
publish_mode = "now"      (không đổi so với 006)
  pending → publishing → success | failed

publish_mode = "scheduled"
  pending ──(upload + tạo bài ở Zernio OK)──> scheduled
     │                                           │
     │                                           ├──(người dùng huỷ,
     │                                           │   hoặc ngắt kết nối kênh)──> cancelled
     │                                           │
     │                                           └──(tới giờ, đối soát lại)──┐
     └──(lỗi trước khi tạo được bài)──> failed                               │
                                                                             ▼
                                              publishing → success | failed
```

**Quy tắc bắt buộc**:

- `scheduled` **KHÔNG BAO GIỜ** được tự chuyển thành `failed` chỉ vì đã lâu chưa
  đăng — chỉ đổi khi đối soát với Zernio cho kết quả thật (FR-008).
- `success` / `failed` / `cancelled` là trạng thái cuối.
- Huỷ chỉ hợp lệ từ `scheduled`. Từ `publishing`/`success` ⇒ từ chối (FR-012).
- Đặt lại lịch = **tạo attempt mới**, không sửa attempt cũ — giữ nguyên nguyên
  tắc của 006, lịch sử không bị ghi đè.

### 1.4 Quy tắc hợp lệ khi tạo (bổ sung cho 006 §1.2)

Với `publish_mode="scheduled"`:

- `scheduled_for` PHẢI cách thời điểm hiện tại **≥ 15 phút** (FR-003) ⇒ vi phạm: `400`
- `scheduled_for` PHẢI cách thời điểm hiện tại **≤ 3 ngày** (FR-004) ⇒ vi phạm: `400`
- Mọi ràng buộc của đăng ngay vẫn áp dụng nguyên vẹn và kiểm **ngay lúc đặt
  lịch** (FR-014): tiêu đề, job `done` + có output, giới hạn nền tảng, kênh còn
  kết nối.
- Không được tạo nếu đã có attempt cùng `job_id` + `platform` ở trạng thái
  `pending` / `publishing` / **`scheduled`** (research.md §8).

---

## 2. Đối soát trạng thái (dẫn xuất, không lưu)

Attempt được coi là **cần đối soát** khi (research.md §4):

| Điều kiện | Lý do |
|---|---|
| `status == "scheduled"` và `now >= scheduled_for - 1 phút` | Đã tới giờ, kết quả có thể đã thay đổi |
| `status == "publishing"` | Trạng thái chuyển tiếp, luôn phải soát |

Attempt `scheduled` mà **chưa tới giờ** thì KHÔNG gọi API — trạng thái chắc chắn
chưa đổi, gọi chỉ tốn quota.

Ánh xạ trạng thái Zernio → attempt (dùng lại bảng của 006, bổ sung `scheduled`):

| Zernio `post.status` | attempt `status` |
|---|---|
| `scheduled` | `scheduled` (giữ nguyên) |
| `publishing` | `publishing` |
| `published` | `success` (+ `post_url`) |
| `failed` / `partial` / `cancelled` | `failed` (+ `error`, `error_kind`) |

---

## 3. Local Publish State

Không đổi so với [006 §3](../006-publish-video-tab/data-model.md) —
`publish_data/state.json` giữ nguyên `profile_id` và `disconnected_account_ids`.

Việc ngắt kết nối kênh nay kéo theo huỷ các attempt `scheduled` của account đó
(FR-015), nhưng danh sách bài bị huỷ **không lưu vào state.json** — nó suy ra
được từ chính các file attempt đã chuyển sang `cancelled`.

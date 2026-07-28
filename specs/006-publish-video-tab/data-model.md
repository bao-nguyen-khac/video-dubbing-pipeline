# Data Model: 006-publish-video-tab

**Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

Không dùng database — toàn bộ trạng thái là file JSON (research.md §5).

---

## 1. Publish Attempt (Lượt đăng)

**File**: `jobs/{job_id}/publishes/{attempt_id}.json` (1 file / 1 lượt đăng)

| Field | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `attempt_id` | string (uuid4) | ✓ | Định danh lượt đăng; cũng dùng làm `Idempotency-Key` gửi Zernio |
| `job_id` | string (uuid4) | ✓ | Job đã sinh ra video được đăng |
| `platform` | `"tiktok" \| "youtube"` | ✓ | Nền tảng đích (FR-003) |
| `account_id` | string | ✓ | Id kênh của Zernio (`GET /accounts`) tại thời điểm đăng |
| `account_label` | string | ✓ | Tên kênh hiển thị lúc đăng — giữ nguyên trong lịch sử kể cả khi sau đó ngắt kết nối |
| `title` | string (1..N) | ✓ | Tiêu đề người dùng nhập (FR-004); TikTok dùng làm caption |
| `status` | `"pending" \| "publishing" \| "success" \| "failed"` | ✓ | Xem §1.1 |
| `error` | string \| null | ✓ | Thông báo lỗi tiếng Việt đã phân loại (SC-004); `null` khi chưa lỗi |
| `error_kind` | string \| null | ✓ | Phân loại máy đọc được: `auth_expired` \| `disconnected` \| `platform_rejected` \| `provider_unavailable` \| `limit_exceeded` \| `network` \| `unknown` |
| `provider_post_id` | string \| null | ✓ | Id bài đăng bên Zernio (`POST /posts` → `id`) |
| `post_url` | string \| null | ✓ | Link bài đăng trên nền tảng khi thành công (`platformPostUrl`) |
| `created_at` | string (ISO 8601, UTC) | ✓ | Lúc bấm "Đăng" |
| `updated_at` | string (ISO 8601, UTC) | ✓ | Lần cập nhật trạng thái gần nhất |

### 1.1 Chuyển trạng thái

```text
pending ──(upload media + tạo post OK)──> publishing ──(provider: published)──> success
   │                                           │
   └──(lỗi trước khi tạo post)──> failed       └──(provider: failed/partial/cancelled
                                                    hoặc quá hạn polling)──> failed
```

- `pending` được ghi ra file **trước** khi gọi Zernio → nếu backend chết giữa
  chừng, lượt đăng dở dang vẫn nhìn thấy được (Principle VI).
- `success` và `failed` là trạng thái cuối, không tự đổi nữa.
- Đăng lại sau lỗi = **tạo attempt mới**, không sửa attempt cũ (giữ lịch sử
  đầy đủ cho FR-010).

### 1.2 Quy tắc hợp lệ

- `title` sau khi trim PHẢI khác rỗng (FR-004) — vi phạm ⇒ `400`, không tạo file.
- Job tham chiếu PHẢI có `status == "done"` và tồn tại `artifacts.output_video`
  trên đĩa (FR-002) — vi phạm ⇒ `400`.
- KHÔNG được tạo attempt mới nếu đã có attempt cùng `job_id` + `platform` ở
  trạng thái `pending`/`publishing` (FR-009) ⇒ `409`.
- `account_id` không được nằm trong `disconnected_account_ids` (FR-011) ⇒ `403`.

---

## 2. Channel Connection (Kết nối kênh)

**Nguồn sự thật**: Zernio `GET /accounts` (đọc trực tiếp mỗi lần cần, không
cache lâu dài) — hợp nhất với blocklist cục bộ ở §3.

Hình dạng sau khi hợp nhất (dùng cho API và UI):

| Field | Kiểu | Mô tả |
|---|---|---|
| `account_id` | string | Id kênh bên Zernio |
| `platform` | `"tiktok" \| "youtube"` | Chỉ giữ 2 nền tảng này, bỏ qua nền tảng khác trong tài khoản Zernio |
| `label` | string | Tên/username kênh hiển thị cho người dùng |
| `status` | `"connected" \| "expired" \| "disconnected"` | `disconnected` khi nằm trong blocklist cục bộ; `expired` khi Zernio báo `connected=false` hoặc thiếu scope đăng bài; còn lại `connected` |

Chỉ `status == "connected"` mới được chọn để đăng (FR-005, FR-008, FR-011).

---

## 3. Local Publish State

**File**: `publish_data/state.json` (thư mục dữ liệu, thêm vào `.gitignore`)

| Field | Kiểu | Mô tả |
|---|---|---|
| `profile_id` | string \| null | Profile Zernio dùng để nhóm các kênh; `null` cho tới lần kết nối đầu tiên |
| `disconnected_account_ids` | string[] | Blocklist cục bộ (research.md §6); được gỡ khi người dùng liên kết lại |
| `updated_at` | string (ISO 8601, UTC) | Lần ghi gần nhất |

---

## 4. Publishable Video (dẫn xuất, không lưu)

Suy ra từ `jobs/*/job.json`, không có file riêng:

| Field | Nguồn |
|---|---|
| `job_id` | `job.job_id` |
| `source_url` | `job.source_url` |
| `created_at` | `job.created_at` |
| `duration_seconds` | `media_utils.get_media_duration(artifacts.output_video)` |
| `already_published_to` | các platform có attempt `status == "success"` của job đó |

Điều kiện xuất hiện: `job.status == "done"` **và** `artifacts.output_video` tồn
tại trên đĩa (FR-002, Edge Case "job chưa xử lý xong").

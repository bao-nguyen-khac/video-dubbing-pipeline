# Quickstart & Verification: 007-schedule-publish

**Spec**: [spec.md](./spec.md) | **Contract**: [contracts/api.md](./contracts/api.md)

---

## 0. Cảnh báo trước khi verify thật (Constitution §VI)

Tính năng này có rủi ro đặc thù so với 006: **bài đã hẹn vẫn tự lên kể cả khi
bạn đã tắt hệ thống**. Đặt lịch thử mà quên huỷ = một bài đăng công khai thật
xuất hiện trên kênh thật, và giao diện này không xoá được.

⇒ Agent **PHẢI hỏi người dùng trước** mỗi lượt gọi thật tới Zernio, và sau khi
verify xong PHẢI **huỷ bài thử nghiệm** (hoặc xác nhận với người dùng là để nó
lên thật).

Kịch bản 1–6 chạy được **không cần** gọi thật; chỉ KB7/KB8 mới đụng Zernio.

---

## 1. Cấu hình

Không có biến môi trường mới — dùng lại `ZERNIO_API_KEY` của
[006](../006-publish-video-tab/quickstart.md).

## 2. Chạy

```bash
uvicorn web.backend.main:app --reload --port 8000
```

Mở giao diện → tab **Đăng video** → khu vực hẹn giờ.

---

## 3. Kịch bản verify

### KB1 — Biên thời gian (không gọi mạng)

| Thử | Mong đợi |
|---|---|
| Hẹn vào thời điểm quá khứ | `400`, nêu rõ mức tối thiểu 15 phút |
| Hẹn cách hiện tại 5 phút | `400`, nêu rõ phải cách ít nhất 15 phút |
| Hẹn cách hiện tại 4 ngày | `400`, nêu rõ tối đa 3 ngày |
| Hẹn cách hiện tại 1 tiếng | Được chấp nhận (`202`) |

Verify thêm: các ca `400` **không** phát sinh lời gọi Zernio nào (kiểm log adapter).

### KB2 — Ràng buộc của đăng ngay vẫn áp dụng khi hẹn giờ (FR-014)

Với `publish_mode="scheduled"` hợp lệ về thời gian, thử lần lượt: tiêu đề rỗng,
job chưa `done`, video vượt giới hạn thời lượng, kênh đã ngắt kết nối.

**Mong đợi**: đều bị chặn **ngay lúc đặt lịch** với đúng mã lỗi như đăng ngay
(`400`/`403`), không có attempt nào được tạo.

### KB3 — Múi giờ (SC-006)

Đặt lịch lúc 20:00 giờ Việt Nam.

**Mong đợi**: file attempt lưu `scheduled_for` = `13:00Z` (UTC, lệch đúng 7
tiếng); payload gửi Zernio cũng là `...T13:00:00Z` kèm
`timezone: "Asia/Ho_Chi_Minh"`; giao diện hiển thị lại **20:00**.

### KB4 — Không báo thất bại nhầm (FR-008, SC-002) ⚠️ then chốt

Với adapter mock trả `status="scheduled"`, tạo 1 bài hẹn giờ rồi **chờ quá 10
phút** (mốc timeout của luồng đăng ngay).

**Mong đợi**: attempt vẫn ở `scheduled`, **không** bị chuyển `failed`. Đây chính
là lỗi mà luồng đăng ngay sẽ mắc nếu dùng chung nhánh runner.

### KB5 — Đối soát lười (FR-009, research.md §4)

1. Tạo attempt `scheduled` với `scheduled_for` trong tương lai → gọi
   `GET /api/publish/attempts` → **không** có lời gọi `GET /v1/posts/{id}` nào.
2. Sửa `scheduled_for` về quá khứ, mock Zernio trả `published` → gọi lại
   → attempt chuyển `success` kèm `post_url`.
3. Mock Zernio trả `failed` → attempt chuyển `failed` kèm nguyên nhân.

### KB6 — Huỷ (mock)

| Thử | Mong đợi |
|---|---|
| Huỷ bài `scheduled`, Zernio OK | `200`, attempt thành `cancelled` |
| Huỷ bài `scheduled`, Zernio lỗi | `502`, attempt **vẫn** `scheduled` (research.md §5) |
| Huỷ bài đã `success` | `409`, nêu rõ phải xoá trên nền tảng |
| Huỷ bài đang `publishing` | `409` |
| Ngắt kết nối kênh còn 2 bài chờ | `200` kèm `cancelled_attempts` gồm đúng 2 bài; cả 2 chuyển `cancelled` |

### KB7 — Đặt lịch thật đầu-cuối (⚠️ HỎI NGƯỜI DÙNG TRƯỚC)

1. Đặt lịch 1 video vào **khoảng 20 phút sau**.
2. Kiểm tra bài xuất hiện trong danh sách "đang chờ đăng", đúng giờ đã chọn.
3. **Tắt hẳn backend** (đây là phần cốt lõi cần chứng minh — SC-001/FR-005).
4. Tới giờ, kiểm tra kênh TikTok: video đã lên công khai đúng giờ ±5 phút.
5. Bật lại backend, mở giao diện → trạng thái tự chuyển `success` kèm link bài.

Bằng chứng cần lưu: ảnh chụp danh sách chờ trước khi tắt, `post_url`, và response
`GET /api/publish/attempts/{id}` sau khi bật lại.

### KB8 — Huỷ thật trước giờ (⚠️ HỎI NGƯỜI DÙNG TRƯỚC)

Đặt lịch 1 video khoảng 20 phút sau → huỷ → **chờ qua thời điểm đã hẹn** → kiểm
tra kênh: video KHÔNG xuất hiện (SC-004).

Đây là kịch bản duy nhất chứng minh việc huỷ có tác dụng thật ở Zernio chứ không
chỉ đổi nhãn trong file.

---

## 4. Test tự động

```bash
pytest tests/unit -q
```

Mọi test PHẢI mock lớp HTTP — không test nào gọi thật tới `zernio.com`, và không
test nào được tạo bài hẹn giờ thật.

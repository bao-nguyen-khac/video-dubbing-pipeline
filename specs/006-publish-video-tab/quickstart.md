# Quickstart & Verification: 006-publish-video-tab

**Spec**: [spec.md](./spec.md) | **Contract**: [contracts/api.md](./contracts/api.md)

Hướng dẫn chạy & kịch bản verify. Không chứa code implementation.

---

## 0. Cảnh báo trước khi verify thật (Constitution §VI, research.md §8)

Mỗi lượt đăng **thành công** tạo ra một bài đăng **công khai thật** trên kênh
thật của người dùng, và giao diện này **không** xoá/sửa được bài đã đăng. Mỗi
kênh kết nối Zernio cũng là chi phí thật.

⇒ Agent **PHẢI hỏi người dùng trước** mỗi lượt gọi thật tới Zernio (kết nối
kênh hoặc bấm "Đăng"). Kịch bản 1–5 dưới đây chạy được **không cần** gọi thật;
chỉ kịch bản 6 mới đăng thật.

---

## 1. Cấu hình

Thêm vào `.env` (mẫu đã có trong `.env.example`):

```bash
ZERNIO_API_KEY=sk_...
ZERNIO_BASE_URL=https://zernio.com/api/v1
ZERNIO_PROFILE_ID=
```

- Không có `ZERNIO_API_KEY`: toàn bộ ứng dụng vẫn chạy bình thường, chỉ riêng
  tab "Đăng video" báo chưa cấu hình (`503`) — không được làm hỏng luồng job.
- `ZERNIO_PROFILE_ID` để trống ở lần đầu; hệ thống tự tạo/ghi nhớ profile trong
  `publish_data/state.json`.

## 2. Chạy

```bash
uvicorn web.backend.main:app --reload --port 8000
```

Frontend dev (tuỳ chọn, khi sửa UI):

```bash
cd web/frontend && npm run dev
```

Mở `http://localhost:8000` → đăng nhập → tab **Đăng video**.

---

## 3. Kịch bản verify

Đánh dấu task hoàn thành chỉ khi có bằng chứng cụ thể (log/response/ảnh chụp).

### KB1 — Chưa cấu hình Zernio (không gọi mạng)

Bỏ trống `ZERNIO_API_KEY` → mở tab Đăng video.
**Mong đợi**: thông báo cần cấu hình, các API `/api/publish/connections`,
`POST /api/publish` trả `503`; các tab Tạo job / Lịch sử vẫn hoạt động.

### KB2 — Danh sách video đăng được (không gọi mạng)

```bash
curl -s -b cookies.txt http://localhost:8000/api/publish/videos | jq
```

**Mong đợi**: chỉ có job `status=done` còn file `output.mp4`; job đang chạy /
`failed` không xuất hiện (FR-002, Edge Case).

### KB3 — Tiêu đề bắt buộc & kiểm tra giới hạn (không gọi mạng)

Bấm "Đăng" khi tiêu đề trống ⇒ bị chặn ở UI; gọi thẳng API với `title: "  "`
⇒ `400 "Tiêu đề là bắt buộc"` (FR-004).

Chọn video dài > 180s + YouTube Shorts ⇒ `400` nêu rõ số giây thực tế và giới
hạn (research.md §7) — verify được rằng **chưa** có lời gọi nào tới Zernio
(kiểm tra log adapter).

### KB4 — Chống đăng trùng (mock, không gọi mạng)

Với adapter Zernio đã mock để "treo" ở bước tạo post, gửi 2 request
`POST /api/publish` liên tiếp cùng `job_id` + `platform`.
**Mong đợi**: request thứ 2 trả `409` kèm `attempt_id` của lượt đang chạy;
`jobs/{job_id}/publishes/` chỉ có **1** file (FR-009, SC-003).

### KB5 — Kênh bị ngắt kết nối (mock)

`DELETE /api/publish/connections/{account_id}` → thử đăng tới chính account đó.
**Mong đợi**: `403` yêu cầu liên kết lại; `publish_data/state.json` chứa
`account_id` trong `disconnected_account_ids` (FR-011).

Mock Zernio trả lỗi token hết hạn cho account đang dùng ⇒ lượt đăng kết thúc
`failed` với `error_kind="auth_expired"` và thông báo yêu cầu xác thực lại
(FR-008, SC-004). Tương tự mock `5xx`/timeout ⇒ `provider_unavailable` với
thông báo nói rõ lỗi ở phía dịch vụ trung gian (Edge Case).

### KB6 — Đăng thật đầu-cuối (⚠️ HỎI NGƯỜI DÙNG TRƯỚC)

1. Tab Đăng video → chọn nền tảng → bấm "Kết nối kênh" → hoàn tất OAuth trên
   TikTok/YouTube → quay lại thấy kênh ở trạng thái `connected` (FR-005).
2. Chọn 1 video đã xử lý xong, điền tiêu đề, bấm "Đăng".
3. **Mong đợi**: trạng thái chạy `pending → publishing → success` trong giao
   diện; lịch sử hiện lượt đăng kèm link bài đăng; mở link thấy video **công
   khai ngay** trên kênh (SC-005), tiêu đề đúng như đã điền.
4. Tải lại trang, đăng video khác lên **cùng** kênh ⇒ **không** phải xác thực
   lại (FR-006, SC-002).

Bằng chứng cần lưu: response `GET /api/publish/attempts/{id}` cuối cùng +
`post_url` + ảnh chụp bài đăng công khai.

---

## 4. Test tự động

```bash
pytest tests/unit -q
```

Mọi test PHẢI mock lớp HTTP của `publish/zernio_client.py` — không test nào
được gọi thật tới `zernio.com` (research.md §8).

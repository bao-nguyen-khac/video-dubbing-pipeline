# Research: Hẹn giờ đăng video (007-schedule-publish)

**Ngày**: 2026-07-28 | **Spec**: [spec.md](./spec.md)

Tính năng này mở rộng [006-publish-video-tab](../006-publish-video-tab/) — mọi
quyết định về dịch vụ trung gian (Zernio), lưu trữ file JSON, ánh xạ lỗi đã chốt
ở đó vẫn giữ nguyên. Tài liệu này chỉ ghi phần **mới** của việc hẹn giờ.

---

## 1. Cơ chế hẹn giờ của Zernio

**Decision**: Gửi `scheduledFor` thay cho `publishNow: true` trong cùng lời gọi
`POST /v1/posts` đã dùng. Zernio giữ bài ở trạng thái `scheduled` và tự đăng khi
tới giờ — **hệ thống này không cần chạy** vào thời điểm đó (FR-005).

**Xác minh thật** trên `https://zernio.com/openapi.yaml` (ngày 2026-07-28):

| Việc | Cách làm |
|---|---|
| Đặt lịch | `POST /v1/posts` với `scheduledFor` (ISO 8601 date-time) + `timezone`, KHÔNG gửi `publishNow` |
| Huỷ bài chờ | `DELETE /v1/posts/{postId}` — *"Delete a draft or scheduled post. Published posts cannot be deleted"*, hoàn lại quota upload |
| Kiểm tra trạng thái | `GET /v1/posts/{postId}` → `scheduled` → `publishing` → `published` / `failed` |

**Rationale**: toàn bộ phần "chờ đến giờ" do Zernio gánh. Nếu tự hẹn giờ ở phía
này thì máy người dùng phải luôn bật — phá hỏng đúng giá trị cốt lõi của tính năng.

**Alternatives considered**:

| Phương án | Bị loại vì |
|---|---|
| Tự hẹn giờ trong hệ thống này (cron/scheduler nội bộ) | Máy tắt là bài không lên — trái FR-005, mất toàn bộ giá trị |
| Dùng hàng đợi của Zernio (`queuedFromProfile`) | Zernio tự chọn khung giờ theo lịch cấu hình sẵn, người dùng không chỉ định được giờ cụ thể — trái FR-002 |

---

## 2. Múi giờ — nguồn sai lệch 7 tiếng nếu làm ẩu

**Decision**: Quy đổi thời điểm người dùng nhập (giờ Việt Nam) sang **UTC tuyệt
đối** rồi gửi `scheduledFor` dạng `...Z`, đồng thời gửi kèm
`timezone: "Asia/Ho_Chi_Minh"`.

**Rationale**: `timezone` của Zernio nhận **tên IANA** (spec ghi rõ *"IANA
timezone (e.g., America/New_York)"*) và **mặc định là UTC**. Mọi ví dụ
`scheduledFor` trong spec đều ở dạng `2024-11-01T10:00:00Z`. Gửi mốc UTC tuyệt
đối thì không phụ thuộc vào cách Zernio diễn giải trường `timezone` — đúng giờ
kể cả khi họ đổi mặc định. Nếu gửi giờ "trần" (không có offset) mà quên
`timezone`, bài sẽ lên **lệch đúng 7 tiếng** (SC-006).

Toàn bộ ranh giới: **giao diện làm việc bằng giờ địa phương, API và file lưu
bằng UTC**, quy đổi đúng 1 chỗ. Không có "giờ trần không rõ múi" ở bất kỳ đâu.

---

## 3. Vấn đề lớn nhất: runner hiện tại sẽ báo thất bại nhầm

**Decision**: Tách 2 nhánh trong `publish/runner.py`:

- **Đăng ngay** — giữ nguyên hành vi hiện có (poll 2s, tối đa 10 phút).
- **Hẹn giờ** — upload video → tạo bài với `scheduledFor` → ghi trạng thái
  `scheduled` → **kết thúc thread ngay**, không poll.

**Rationale**: runner hiện tại poll `get_post()` tối đa 10 phút rồi đánh
`failed`. Bài hẹn 3 ngày sau sẽ ở `scheduled` suốt → sau 10 phút bị ghi **thất
bại** dù thực tế vẫn đang chờ đăng bình thường. Đây chính là thứ FR-008 cấm.
Không thể "poll lâu hơn" vì tiến trình có thể bị tắt bất cứ lúc nào.

---

## 4. Đối soát trạng thái (câu hỏi được hoãn từ `/speckit-clarify`)

**Decision**: Đối soát **lười, lúc đọc** — khi giao diện gọi danh sách hoặc chi
tiết lượt đăng, hệ thống gọi `GET /v1/posts/{id}` cho những attempt **đáng nghi
ngờ** rồi cập nhật file trước khi trả về. Không có tiến trình quét nền.

Chỉ đối soát attempt thoả 1 trong 2 điều kiện:

1. Trạng thái cục bộ là `scheduled` **và** đã qua `scheduled_for` (trừ hao 1 phút)
2. Trạng thái cục bộ là `publishing` (trạng thái chuyển tiếp, luôn cần soát)

**Rationale**: trước giờ hẹn thì trạng thái chắc chắn vẫn là `scheduled`, gọi
API chỉ tốn quota vô ích. Quy tắc này giữ số lời gọi gần như bằng 0 ở trạng thái
bình thường, mà vẫn thoả SC-003 (mở giao diện lần đầu là thấy đúng kết quả).

Không thêm scheduler nền vì nó không mua thêm gì: người dùng chỉ biết kết quả
khi mở giao diện (spec → Assumptions: không có thông báo đẩy), mà lúc đó đối
soát lười đã chạy rồi. Thêm tiến trình nền chỉ tăng thứ phải bảo trì
(Constitution §V).

**Alternatives considered**:

| Phương án | Bị loại vì |
|---|---|
| Webhook của Zernio (`post.published`, `post.failed`) | Backend chạy nội bộ, không có URL public để Zernio gọi tới |
| Quét nền định kỳ | Không mua thêm gì so với đối soát lười (xem trên), lại thêm tiến trình phải quản |

---

## 5. Huỷ bài — phải huỷ thật ở Zernio, không chỉ ở phía này

**Decision**: Huỷ = gọi `DELETE /v1/posts/{postId}` **trước**, thành công mới ghi
trạng thái `cancelled` vào file. Zernio lỗi ⇒ báo lỗi cho người dùng và **giữ
nguyên** trạng thái `scheduled`.

**Rationale**: khác hẳn cơ chế "ngắt kết nối kênh" của 006 — nơi blocklist cục bộ
là đủ vì mọi lượt đăng đều phải đi qua hệ thống này. Ở đây **Zernio đăng bài mà
không hỏi lại hệ thống này**, nên đánh dấu cục bộ không ngăn được gì: tới giờ
video vẫn lên. Ghi `cancelled` khi chưa huỷ được thật là **nói dối người dùng**
về một hành động không đảo ngược được.

Vì lý do đó, thứ tự **bắt buộc** là gọi Zernio trước, ghi file sau.

---

## 6. Ngắt kết nối kênh phải kéo theo huỷ bài đã hẹn (FR-015)

**Decision**: `DELETE /api/publish/connections/{account_id}` bổ sung bước: tìm
mọi attempt `scheduled` của account đó → huỷ từng bài ở Zernio → ghi `cancelled`
→ trả về danh sách bài vừa huỷ để giao diện báo lại người dùng.

**Rationale**: cùng lý do §5. FR-011 của 006 hứa "sau khi ngắt, các lượt đăng tới
kênh đó bị chặn" — mà bài đã nằm ở Zernio thì blocklist cục bộ không chặn được.
Không huỷ = video lên kênh người dùng tưởng đã ngắt.

Bài huỷ không được ⇒ vẫn ngắt kết nối nhưng **cảnh báo rõ** bài nào còn treo, để
người dùng tự xử lý trên dashboard Zernio.

---

## 7. Biên thời gian

**Decision**: tối thiểu **15 phút**, tối đa **3 ngày** kể từ lúc đặt lịch
(spec → Clarifications). Kiểm tra ở backend, không chỉ ở giao diện.

Hằng số đặt cùng chỗ với các ngưỡng nền tảng đã có (`publish/limits.py`) để mọi
giới hạn nằm một chỗ.

**Rationale (tối đa 3 ngày)**: video được upload lên Zernio ngay lúc đặt lịch,
nhưng `publicUrl` nằm ở đường dẫn `temp/` và **không tài liệu nào của Zernio nói
file được giữ bao lâu** — đã tra cả `openapi.yaml`, `docs.zernio.com` lẫn
`llms.txt` của họ. Endpoint anh em `/v1/media/upload-direct` thì ghi rõ tự xoá
sau 7 ngày. File bị dọn trước giờ đăng = bài hỏng đúng lúc người dùng vắng mặt.

**Rationale (tối thiểu 15 phút)**: upload video xong mới tạo được bài; hẹn quá
sát thì upload xong đã trôi qua mất giờ đăng.

---

## 8. Chống trùng và dedup 24h của Zernio

**Decision**: `find_active_attempt()` mở rộng để tính cả trạng thái `scheduled`
là "đang hoạt động" — một video đã có bài chờ đăng lên kênh nào thì không đặt
thêm lịch cho đúng video + kênh đó (spec → Assumptions).

Ngoài ra Zernio có dedup nội dung 24h trả `409` — đã ánh xạ sẵn thành
`error_kind="duplicate_content"` ở 006, dùng lại nguyên vẹn.

---

## 9. Kỷ luật verify (Constitution §VI)

**Decision**: Test tự động mock toàn bộ HTTP. Lượt gọi thật chỉ trong quickstart
và **PHẢI hỏi người dùng trước** — đặt lịch thật là một bài đăng công khai thật
sẽ tự lên, và nếu quên huỷ thì nó lên thật.

Riêng tính năng này có rủi ro đặc thù: **bài đã hẹn vẫn lên kể cả khi đã tắt hệ
thống**. Verify xong PHẢI huỷ bài thử nghiệm, hoặc chấp nhận nó sẽ lên kênh thật.

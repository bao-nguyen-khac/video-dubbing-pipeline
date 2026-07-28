# Research: Đăng video lên TikTok/YouTube Shorts (006-publish-video-tab)

**Ngày**: 2026-07-27 | **Spec**: [spec.md](./spec.md)

Tài liệu này chốt các quyết định kỹ thuật trước khi thiết kế. Mọi mục
NEEDS CLARIFICATION của Technical Context được giải quyết ở đây.

---

## 1. Dịch vụ trung gian đăng bài: Zernio

**Decision**: Dùng **Zernio** (`https://zernio.com`, docs `https://docs.zernio.com`,
OpenAPI `https://zernio.com/openapi.yaml`) làm lớp trung gian cho cả xác thực
kênh (OAuth) lẫn đăng video, cho cả TikTok và YouTube.

**Rationale**:

- Người dùng dự án đã chọn Zernio (spec.md → Clarifications 2026-07-27) và đã
  có tài khoản/API key riêng — không cần hệ thống này tự xin audit TikTok
  Content Posting API (mất nhiều tuần, cần chứng minh UX tuân thủ) hay tự qua
  quy trình verify OAuth của YouTube (app chưa verify chỉ upload được video ở
  chế độ riêng tư).
- Zernio là REST API hợp nhất cho cả 2 nền tảng đích → 1 client duy nhất, 1
  luồng OAuth duy nhất, thay vì 2 tích hợp riêng biệt (TikTok Content Posting
  API + YouTube Data API v3) với 2 vòng duyệt riêng.
- Đáp ứng FR-012 (đi đúng cơ chế nền tảng cho phép chính thức, không giả lập
  thao tác tay) và SC-005 (đăng công khai ngay).

**Alternatives considered**:

| Phương án | Bị loại vì |
|---|---|
| Tự tích hợp TikTok Content Posting API + YouTube Data API | Phải tự qua audit TikTok và verify OAuth YouTube; chưa duyệt thì chỉ đăng được private/SELF_ONLY → vi phạm SC-005 |
| Browser automation (giả lập đăng tay) | Đã bị loại ở vòng clarify (spec.md → Clarifications): rủi ro khoá tài khoản + vượt phạm vi hỗ trợ |
| Ayrshare / Blotato / Upload-Post | Cùng mô hình trung gian nhưng người dùng đã chọn Zernio; giữ 1 provider duy nhất ở v1 (Principle V — không thêm thứ chưa có nhu cầu xác nhận) |

**Rủi ro đã chấp nhận** (spec.md → Assumptions): phụ thuộc tính khả dụng của
Zernio, không có phương án dự phòng tự động ở v1.

---

## 2. Bề mặt API Zernio dùng ở v1

**Decision**: Chỉ dùng đúng 5 lời gọi, gói trong 1 adapter Python duy nhất
(`publish/zernio_client.py`):

| Mục đích | Lời gọi Zernio (theo docs 2026-07-27) |
|---|---|
| Lấy URL để người dùng liên kết kênh | `GET /connect/{platform}?profileId=…` |
| Liệt kê kênh đã liên kết | `GET /accounts` |
| Tải file video lên | `POST /media` (multipart form-data, field `file`) |
| Tạo bài đăng công khai ngay | `POST /posts` (`publishNow: true`, kèm options riêng theo nền tảng) |
| Theo dõi trạng thái đăng | `GET /posts/{postId}` → `scheduled\|publishing\|published\|failed\|partial\|cancelled` |

- Base URL: `https://zernio.com/api/v1`; xác thực: header
  `Authorization: Bearer $ZERNIO_API_KEY` (key dạng `sk_` + 64 hex).
- Lỗi trả về dạng `{error, type, code, param?, platform?, platformError?}` với
  các mã 400/401/402/403/404/429 — dùng trực tiếp để phân loại nguyên nhân cho
  người dùng (SC-004).

**Rationale**: bề mặt càng nhỏ càng dễ đổi provider sau này và dễ verify.
Không dùng webhook ở v1 (backend chạy local, không có URL public) → **polling**
`GET /posts/{postId}` trong thread nền, cùng mô hình với `job_runner.py`.

**⚠️ Điều kiện bắt buộc trước khi code (task đầu tiên của tasks.md)**: tên
trường chính xác trong `POST /posts` (đặc biệt object tuỳ chọn riêng của TikTok
và YouTube, cách tham chiếu media đã upload, tên header idempotency) PHẢI được
đối chiếu lại với `https://zernio.com/openapi.yaml` tại thời điểm implement —
bản tóm tắt docs đọc được ở bước research không đủ chi tiết để chốt schema. Vì
toàn bộ ánh xạ nằm trong 1 adapter, sai lệch tên trường chỉ ảnh hưởng 1 file.

**Alternatives considered**: dùng MCP server của Zernio thay REST — bị loại vì
backend là FastAPI Python chạy nền, không có runtime agent; REST đơn giản hơn.

---

## 3. "Công khai ngay" (SC-005) được đảm bảo thế nào

**Decision**: Mỗi lượt đăng luôn gửi tham số chế độ hiển thị công khai một cách
tường minh — YouTube: `privacyStatus = "public"`; TikTok: mức riêng tư công
khai (`PUBLIC_TO_EVERYONE` theo quy ước Content Posting API mà Zernio ánh xạ
lại). Không bao giờ để mặc định của provider quyết định.

**Rationale**: nếu tài khoản Zernio/kênh chưa đủ quyền đăng công khai, nền tảng
sẽ từ chối thẳng và ta báo lỗi rõ ràng (SC-004) — tốt hơn là âm thầm đăng thành
video riêng tư mà người dùng tưởng đã công khai.

**Alternatives considered**: để provider tự chọn mặc định → bị loại vì tạo ra
"thành công giả" đúng thứ spec cấm.

---

## 4. Chống đăng trùng (FR-009, SC-003)

**Decision**: 2 lớp:

1. **Khoá phía server**: `POST /api/publish` trả `409` nếu đã tồn tại một lượt
   đăng của cùng `job_id` + `platform` đang ở trạng thái `pending`/`publishing`.
   Trạng thái đọc từ file (`jobs/{job_id}/publishes/*.json`), không giữ trong
   biến in-memory — cùng lý do như `find_running_job_id()` (backend restart
   giữa chừng không được làm mất khoá).
2. **Idempotency phía Zernio**: gửi `Idempotency-Key = attempt_id` khi tạo bài
   đăng, để một lần retry mạng của chính adapter không sinh 2 bài.

Frontend disable nút "Đăng" trong lúc chờ chỉ là lớp trải nghiệm, **không** được
tính là cơ chế đảm bảo.

**Rationale**: nguồn sự thật là file trạng thái, đúng Principle VI (truy vết
được, audit được).

---

## 5. Lưu trữ trạng thái kết nối & lượt đăng

**Decision**: File JSON, không thêm database (giữ nguyên mô hình hiện có của
`jobs/`):

- `jobs/{job_id}/publishes/{attempt_id}.json` — mỗi lượt đăng 1 file, nằm ngay
  cạnh artifact của job đã sinh ra video đó → lịch sử (FR-010) chỉ là quét thư
  mục, và mọi quyết định đăng đều audit được cạnh job gốc.
- `publish_data/state.json` — trạng thái cục bộ của lớp kết nối: `profile_id`
  của Zernio và danh sách `disconnected_account_ids` (xem §6).

**Rationale**: tái dùng đúng pattern `_iter_all_jobs()` đã có; không thêm hạ
tầng mới (Principle V).

**Alternatives considered**: SQLite — bị loại vì thừa cho quy mô 1 người dùng và
phá vỡ tính "đọc file là hiểu trạng thái" của dự án.

---

## 6. Ngắt kết nối kênh (FR-011)

**Decision**: Hệ thống này quản lý một **blocklist cục bộ**: ngắt kết nối =
thêm `account_id` vào `publish_data/state.json.disconnected_account_ids`; mọi
lượt đăng tới account đó bị chặn ở backend (`403`) cho tới khi người dùng liên
kết lại qua luồng OAuth (khi đó `account_id` được gỡ khỏi blocklist).

Giao diện PHẢI nói rõ: muốn thu hồi quyền hoàn toàn thì làm ở dashboard Zernio /
cài đặt ứng dụng của TikTok/YouTube — hệ thống này chỉ chặn phía nó.

**Rationale**: docs Zernio đọc được chưa xác nhận có endpoint xoá account; thiết
kế này đúng yêu cầu spec ("các lượt đăng sau tới kênh đó PHẢI bị chặn") mà không
phụ thuộc endpoint chưa chắc tồn tại. Nếu lúc implement xác nhận Zernio có
endpoint huỷ liên kết, gọi thêm nó **sau** khi cập nhật blocklist (blocklist vẫn
là nguồn sự thật để chặn).

---

## 7. Kiểm tra trước giới hạn nền tảng (Edge Case thời lượng/kích thước)

**Decision**: Trước khi upload, kiểm tra tại chỗ bằng `media_utils.get_media_duration()`
và `Path.stat().st_size`:

- YouTube Shorts: thời lượng ≤ 180s (video dài hơn vẫn upload được nhưng không
  còn là Shorts → chặn và báo rõ).
- TikTok: thời lượng ≤ 600s, kích thước file ≤ 500MB (ngưỡng thận trọng).

Vượt ngưỡng → trả `400` kèm thông báo nêu đúng nguyên nhân, **không** tốn một
lượt upload lên Zernio.

**Rationale**: spec yêu cầu "báo lỗi rõ nguyên nhân trước khi thử đăng"; các
ngưỡng này là hằng số trong 1 chỗ (`publish/limits.py`) để chỉnh khi nền tảng
đổi chính sách.

---

## 8. Kỷ luật verify (Principle VI)

**Decision**: Mọi test tự động chạy với HTTP tới Zernio **được mock** — không
gọi thật. Lượt gọi thật tới Zernio chỉ thực hiện trong quickstart thủ công, và
**PHẢI hỏi người dùng trước** vì mỗi kênh kết nối là chi phí thật của họ và mỗi
lượt đăng thành công tạo bài đăng thật, công khai, trên kênh thật (không thể
hoàn tác từ giao diện này — spec.md → Assumptions).

**Rationale**: mở rộng đúng tinh thần quy tắc TTS trả phí trong Constitution
§VI sang một dịch vụ trả phí khác, với hậu quả nặng hơn (bài đăng công khai).

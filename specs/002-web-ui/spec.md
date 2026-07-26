# Feature Specification: Web UI cho Video Repurpose Pipeline

**Feature Branch**: `002-web-ui`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "dùng 1 giao diện web cho dự án này, giao diện đáp
ứng yêu cầu hiện tại"

## Clarifications

### Session 2026-07-26

- Q: Cách tính % tiến trình hiển thị trên giao diện (FR-003)? → A: Ước lượng
  theo bước pipeline hiện tại (mỗi bước ≈ 1/6 tổng tiến trình dựa trên
  `job.json.status`), không track chi tiết tiến trình bên trong từng bước.
- Q: Phiên đăng nhập (FR-010) duy trì bao lâu trước khi cần đăng nhập lại? → A:
  Phiên dài hạn (~7 ngày), không yêu cầu đăng nhập lại mỗi lần mở trình duyệt.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tạo video sản phẩm qua trình duyệt, không cần dòng lệnh (Priority: P1)

Người dùng mở trang web, dán URL video (TikTok/Douyin/YouTube) vào 1 form, chọn
chế độ kịch bản (dịch hoặc tự soạn), bấm chạy, theo dõi tiến trình xử lý ngay trên
trang, và khi xong thì xem hoặc tải về video sản phẩm cuối cùng — không cần mở
terminal, Docker, hay biết `--url`/`--script-mode` là gì.

**Why this priority**: Đây là giá trị cốt lõi của tính năng — biến pipeline CLI
(001-video-repurpose-pipeline) đã có thành công cụ ai cũng dùng được qua trình
duyệt. Không có luồng này thì "giao diện web" không có ý nghĩa.

**Independent Test**: Mở trang web, dán 1 URL TikTok công khai, chọn "dịch", bấm
chạy; xác nhận thấy tiến trình cập nhật qua từng bước và cuối cùng xem/tải được
video sản phẩm — không cần chạm vào dòng lệnh.

**Acceptance Scenarios**:

1. **Given** người dùng chưa đăng nhập, **When** họ truy cập trang, **Then** hệ
   thống yêu cầu đăng nhập bằng tài khoản/mật khẩu trước khi cho thấy form chạy
   job (FR-010).
2. **Given** người dùng đã đăng nhập ở trang chủ, **When** họ dán URL hợp lệ,
   chọn chế độ kịch bản, và bấm nút chạy, **Then** hệ thống bắt đầu xử lý và
   hiển thị trạng thái "đang tải video".
3. **Given** một job đang chạy, **When** từng bước của pipeline hoàn tất (tải →
   tách lời → viết kịch bản → sinh giọng → ghép video), **Then** giao diện cập
   nhật trạng thái và phần trăm hoàn thành tương ứng mà người dùng không cần tự
   làm mới trang thủ công.
4. **Given** job đã hoàn tất, **When** người dùng xem trang kết quả, **Then** họ
   xem/tải được video sản phẩm cuối cùng trực tiếp từ trình duyệt.
5. **Given** người dùng nhập URL không hợp lệ hoặc không thuộc 3 nền tảng hỗ trợ,
   **When** họ bấm chạy, **Then** giao diện báo lỗi rõ ràng ngay, không gửi job đi
   xử lý.

---

### User Story 2 - Xem lại lịch sử job đã chạy (Priority: P2)

Người dùng xem được danh sách các job đã chạy trước đó kèm trạng thái, và mở lại
xem chi tiết/kết quả của bất kỳ job nào trong danh sách.

**Why this priority**: Tương đương SC-005 của spec 001 (xem lại file trung gian)
nhưng qua giao diện thay vì phải tự mở thư mục `jobs/`. Có giá trị thật nhưng
không chặn US1.

**Independent Test**: Chạy xong ít nhất 2 job, vào trang danh sách, xác nhận thấy
cả 2 job kèm trạng thái đúng, mở được chi tiết từng job.

**Acceptance Scenarios**:

1. **Given** đã có job chạy trước đó, **When** người dùng vào trang danh sách job,
   **Then** họ thấy job đó kèm trạng thái (đang chạy/hoàn tất/lỗi) và thời gian.
2. **Given** người dùng chọn 1 job trong danh sách, **When** họ mở chi tiết,
   **Then** họ thấy đầy đủ thông tin: URL nguồn, chế độ kịch bản, cảnh báo (nếu
   có), và video sản phẩm (nếu đã xong).

---

### User Story 3 - Thấy rõ cảnh báo chất lượng và thử lại job lỗi (Priority: P3)

Người dùng thấy rõ trên giao diện các cảnh báo chất lượng (còn watermark, giọng
đọc lệch thời lượng, mất nhạc nền) và có thể bấm nút thử lại trực tiếp trên web
khi job thất bại, thay vì phải chạy lại lệnh CLI thủ công.

**Why this priority**: Nâng cao trải nghiệm và tận dụng đúng cơ chế resume đã có
sẵn ở pipeline (contracts/cli.md của 001), nhưng không phải điều kiện để giao
diện web hoạt động được.

**Independent Test**: Với 1 job có cảnh báo (VD lệch thời lượng), xác nhận cảnh
báo hiển thị rõ trên trang kết quả. Với 1 job thất bại, xác nhận có nút "thử lại"
và bấm vào thực sự resume đúng job đó.

**Acceptance Scenarios**:

1. **Given** job hoàn tất nhưng có cảnh báo chất lượng, **When** người dùng xem
   trang kết quả, **Then** họ thấy rõ cảnh báo đó (VD "nhạc nền gốc không giữ
   được").
2. **Given** job đã thất bại ở một bước, **When** người dùng bấm "thử lại",
   **Then** hệ thống resume đúng job đó từ bước dở dang, không chạy lại từ đầu.

---

### Edge Cases

- Job đang chạy mà người dùng đóng trình duyệt hoặc mất kết nối: job vẫn tiếp tục
  xử lý ở phía hệ thống; khi người dùng quay lại (hoặc người khác mở link job),
  trạng thái mới nhất vẫn hiển thị đúng.
- Có job đang chạy và người dùng submit thêm job mới: hệ thống chặn, hiển thị
  tiến trình (%) của job đang chạy và không cho submit job mới cho tới khi xong
  (FR-009).
- Đăng nhập sai tài khoản/mật khẩu nhiều lần: hệ thống báo lỗi đăng nhập rõ ràng;
  không giới hạn số lần thử ở bản đầu (không phải hệ thống nhiều người dùng công
  khai nên rủi ro brute-force thấp, xem Assumptions).
- Video quá dài hoặc quá trình xử lý mất nhiều thời gian: giao diện vẫn hiển thị
  đang xử lý, không được coi là "treo"/lỗi chỉ vì thời gian dài.
- Job thất bại nhiều lần liên tiếp ở cùng 1 bước dù đã thử lại: hệ thống vẫn hiển
  thị lỗi rõ ràng mỗi lần, không giới hạn số lần thử lại ở bản đầu.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST cung cấp một form trên web cho phép nhập URL video và
  chọn chế độ kịch bản (dịch / tự soạn) trước khi chạy.
- **FR-002**: Hệ thống MUST validate URL (thuộc TikTok/Douyin/YouTube) ngay trên
  giao diện trước khi gửi job đi xử lý, báo lỗi rõ nếu không hợp lệ.
- **FR-003**: Hệ thống MUST hiển thị tiến trình xử lý theo từng bước của pipeline
  (tải, tách lời, viết kịch bản, sinh giọng, ghép video) VÀ theo phần trăm (%)
  hoàn thành, tự cập nhật mà người dùng không cần làm mới trang thủ công. % được
  ước lượng theo bước hiện tại (mỗi bước ≈ 1/6 tổng tiến trình dựa trên
  `job.json.status`), không phải tiến trình chi tiết thật bên trong từng bước.
- **FR-004**: Hệ thống MUST cho phép người dùng xem hoặc tải về video sản phẩm
  cuối cùng ngay từ trình duyệt khi job hoàn tất.
- **FR-005**: Hệ thống MUST hiển thị rõ bước nào thất bại và thông điệp lỗi khi
  job không thành công, không yêu cầu người dùng xem log terminal.
- **FR-006**: Hệ thống MUST cho phép xem danh sách các job đã chạy trước đó kèm
  trạng thái, và mở xem chi tiết từng job.
- **FR-007**: Hệ thống MUST hiển thị các cảnh báo chất lượng sản phẩm (watermark
  còn sót, lệch thời lượng giọng đọc, mất nhạc nền gốc) trên trang kết quả khi có.
- **FR-008**: Hệ thống MUST cho phép người dùng thử lại (resume) một job đã thất
  bại trực tiếp từ giao diện web.
- **FR-009**: Khi đang có 1 job xử lý, hệ thống MUST chặn việc submit job mới
  (không xếp hàng đợi), hiển thị rõ đang có job chạy kèm % tiến trình, và ẩn/vô
  hiệu hoá form chạy job mới cho tới khi job hiện tại hoàn tất hoặc thất bại.
- **FR-010**: Hệ thống MUST yêu cầu đăng nhập bằng một tài khoản (username/
  password) được cấu hình qua biến môi trường trước khi cho truy cập bất kỳ chức
  năng nào của giao diện (form chạy job, danh sách job, chi tiết job). Phiên đăng
  nhập MUST duy trì dài hạn (~7 ngày), không yêu cầu đăng nhập lại mỗi lần mở
  trình duyệt trong thời gian đó.

### Key Entities

Tái sử dụng các entity đã định nghĩa ở
[data-model.md của 001-video-repurpose-pipeline](../001-video-repurpose-pipeline/data-model.md)
(Job, Source Video, Script, Voice Track, Background Audio, Output Video) — giao
diện web là lớp hiển thị/tương tác trên các entity này, không định nghĩa entity
dữ liệu mới.

- **Job List View**: Danh sách rút gọn các Job (job_id, URL nguồn, trạng thái,
  thời gian tạo) hiển thị trên trang danh sách — là 1 view, không phải entity
  lưu trữ riêng.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Người dùng không có kiến thức dòng lệnh vẫn tạo được một video sản
  phẩm hoàn chỉnh từ URL, hoàn toàn qua thao tác trên trình duyệt.
- **SC-002**: Trạng thái tiến trình trên giao diện phản ánh đúng bước hiện tại
  của job trong vòng 10 giây kể từ khi bước đó thực sự bắt đầu/kết thúc ở hệ
  thống nền.
- **SC-003**: 100% job thất bại hiển thị rõ bước lỗi trên giao diện mà không cần
  xem log terminal.
- **SC-004**: Người dùng tìm lại và mở được kết quả của bất kỳ job nào đã chạy
  trước đó từ trang danh sách trong dưới 3 thao tác click.
- **SC-005**: Trang web tải xong và sẵn sàng nhập URL trong dưới 3 giây trên kết
  nối internet thông thường.

## Assumptions

- Giao diện web là một lớp hiển thị/tương tác mỏng bên trên pipeline đã có ở
  001-video-repurpose-pipeline — không thay đổi logic xử lý video (download,
  ASR, script gen, TTS, merge), chỉ thay cách người dùng khởi tạo và theo dõi job.
- Giao diện web triển khai trên localhost (máy cá nhân chạy pipeline) — không mở
  ra LAN/internet công khai ở bản đầu (Clarification Q1).
- Truy cập giao diện yêu cầu đăng nhập bằng một cặp tài khoản/mật khẩu duy nhất
  cấu hình qua biến môi trường (không phải hệ thống quản lý nhiều user/role) —
  cùng cách tiếp cận với `ROUTER_API_KEY`/`TIKTOK_COOKIE` hiện đã dùng `.env`
  (Clarification Q1).
- Hệ thống chỉ xử lý một job tại một thời điểm; khi có job đang chạy, submit mới
  bị chặn (không xếp hàng đợi) và giao diện hiển thị % tiến trình của job đang
  chạy (Clarification Q2).
- Video sản phẩm và file trung gian được phục vụ trực tiếp từ hệ thống chạy
  pipeline (không upload lên dịch vụ lưu trữ ngoài).
- Lịch sử job được giữ lại toàn bộ (không tự động xoá) ở bản đầu, tương ứng với
  cách `jobs/{job_id}/` hiện không tự dọn dẹp.
- Không giới hạn số lần thử lại (resume) một job thất bại ở bản đầu.

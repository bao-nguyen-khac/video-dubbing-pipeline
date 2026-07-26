# Feature Specification: Video Repurpose Pipeline

**Feature Branch**: `001-video-repurpose-pipeline`

**Created**: 2026-07-25

**Status**: Draft

**Input**: User description: "Tải video từ 1 nguồn bất kỳ như TikTok, Douyin, YouTube → dịch hoặc tự soạn kịch bản → sinh voice từ kịch bản → ghép video → ra sản phẩm cuối"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tải video và ghép giọng đọc mới cơ bản (Priority: P1)

Người dùng dán URL video từ TikTok, hệ thống tự động tải video, sinh kịch bản (dịch từ
nội dung gốc), sinh giọng đọc tiếng Việt từ kịch bản đó, và ghép giọng đọc vào video
gốc để tạo ra một video sản phẩm hoàn chỉnh — không cần thao tác thủ công giữa các
bước.

**Why this priority**: Đây là luồng lõi tối thiểu chứng minh toàn bộ pipeline hoạt
động end-to-end; không có luồng này thì các tính năng khác (đa nền tảng, chọn kiểu
kịch bản...) đều vô nghĩa.

**Independent Test**: Chạy pipeline với 1 URL TikTok công khai, xác nhận nhận được 1
file video output có giọng đọc tiếng Việt khớp với nội dung gốc, không cần chỉnh sửa
thủ công nào ở giữa.

**Acceptance Scenarios**:

1. **Given** người dùng có 1 URL video TikTok công khai, **When** họ chạy pipeline
   với URL đó, **Then** hệ thống tải video, trích xuất nội dung, tạo kịch bản, sinh
   voice tiếng Việt, và trả về một video output hoàn chỉnh.
2. **Given** pipeline đang chạy một job, **When** một bước bất kỳ thất bại (ví dụ:
   download lỗi), **Then** hệ thống dừng job, báo lỗi rõ ràng và giữ lại các file
   trung gian đã tạo được đến thời điểm đó.

---

### User Story 2 - Chọn nguồn video từ Douyin và YouTube (Priority: P2)

Ngoài TikTok, người dùng có thể dán URL từ Douyin hoặc YouTube và pipeline xử lý
tương tự, tự động chọn phương thức tải phù hợp cho từng nền tảng.

**Why this priority**: Douyin và YouTube là nguồn quan trọng thứ hai sau TikTok, mở
rộng phạm vi nguồn nhưng không phải điều kiện để có MVP hoạt động.

**Independent Test**: Chạy pipeline với 1 URL Douyin và 1 URL YouTube, xác nhận cả
hai đều cho ra video output hợp lệ.

**Acceptance Scenarios**:

1. **Given** người dùng có 1 URL video Douyin công khai, **When** họ chạy pipeline,
   **Then** hệ thống nhận diện đúng nền tảng và tải video không watermark.
2. **Given** người dùng có 1 URL video YouTube, **When** họ chạy pipeline, **Then**
   hệ thống tải video thành công qua phương thức dự phòng.

---

### User Story 3 - Tự soạn kịch bản mới thay vì dịch nguyên văn (Priority: P3)

Người dùng có thể chọn chế độ "tự soạn kịch bản" thay vì dịch nguyên văn, để hệ
thống dựa trên nội dung/ý chính của video gốc viết ra một kịch bản mới.

**Why this priority**: Tính năng nâng cao phục vụ use case repurpose nội dung sáng
tạo hơn dịch thuần túy — giá trị thêm nhưng không chặn MVP.

**Independent Test**: Chạy pipeline ở chế độ "tự soạn kịch bản" cho 1 video, xác
nhận kịch bản sinh ra khác với bản dịch trực tiếp nhưng vẫn giữ đúng ý chính, và
video output vẫn được tạo thành công.

**Acceptance Scenarios**:

1. **Given** người dùng chọn chế độ tự soạn kịch bản, **When** pipeline chạy,
   **Then** kịch bản sinh ra là nội dung được viết lại (không dịch nguyên văn từng
   câu) nhưng vẫn giữ đúng chủ đề của video gốc.

---

### Edge Cases

- Video ở chế độ riêng tư hoặc đã bị gỡ: hệ thống báo lỗi "không thể tải" rõ ràng
  thay vì dừng đột ngột không rõ nguyên nhân.
- Video không có lời thoại (nội dung trích xuất rỗng): hệ thống thông báo không đủ
  nội dung để dịch, gợi ý chuyển sang chế độ tự soạn kịch bản.
- Video có watermark gắn cứng vào hình ảnh mà không tải được bản sạch: nằm ngoài
  phạm vi MVP này, hệ thống vẫn tạo video output nhưng cảnh báo cho người dùng biết
  video còn watermark.
- Kịch bản sinh ra dài hơn đáng kể so với video gốc: hệ thống MUST cố gắng điều
  chỉnh tốc độ giọng đọc để khớp gần đúng thời lượng video gốc trước khi chấp nhận
  cảnh báo lệch thời lượng (FR-010).
- Tách nhạc nền gốc thất bại (video không có nhạc nền tách được, hoặc lỗi kỹ
  thuật): hệ thống vẫn tạo output bằng cách mute toàn bộ audio gốc như hành vi mặc
  định trước đây, không để lỗi tách nhạc chặn cả pipeline.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST cho phép người dùng nhập một URL video từ TikTok,
  Douyin, hoặc YouTube để bắt đầu xử lý.
- **FR-002**: Hệ thống MUST tải video ở dạng không có watermark khi nguồn hỗ trợ
  lấy bản sạch.
- **FR-003**: Hệ thống MUST trích xuất nội dung/lời thoại từ video gốc để làm cơ sở
  cho bước tạo kịch bản.
- **FR-004**: Hệ thống MUST cho phép người dùng chọn giữa "dịch kịch bản gốc" hoặc
  "tự soạn kịch bản mới" trước khi sinh giọng đọc.
- **FR-005**: Hệ thống MUST sinh giọng đọc tiếng Việt từ kịch bản đã có.
- **FR-006**: Hệ thống MUST ghép giọng đọc mới vào video, tạo ra một file video sản
  phẩm cuối cùng.
- **FR-007**: Hệ thống MUST lưu lại trạng thái và toàn bộ file trung gian của mỗi
  job (video gốc, nội dung trích xuất, kịch bản, giọng đọc, video output) để người
  dùng kiểm tra hoặc xử lý lại khi cần.
- **FR-008**: Hệ thống MUST báo lỗi rõ ràng, chỉ rõ bước nào thất bại, khi bất kỳ
  bước nào trong pipeline không thành công.
- **FR-009**: Hệ thống MUST tách và giữ lại nhạc nền gốc (nếu có) khi ghép giọng
  đọc mới, chỉ loại bỏ giọng nói gốc — không mute toàn bộ audio gốc như mặc định
  trước đây, trừ khi bước tách nhạc thất bại (xem Edge Cases).
- **FR-010**: Hệ thống MUST điều chỉnh tốc độ giọng đọc mới để khớp gần đúng thời
  lượng video gốc, giảm thiểu tình trạng nội dung bị cắt cụt do giọng đọc dài hơn.

### Key Entities

- **Job**: Một lần chạy pipeline cho một video, có trạng thái (đang tải / đang tạo
  kịch bản / đang sinh giọng đọc / đang ghép / hoàn tất / lỗi) và liên kết tới các
  artifact trung gian của nó.
- **Source Video**: Video gốc được tải về — gồm URL nguồn, nền tảng (TikTok/
  Douyin/YouTube), file video, nội dung/lời thoại trích xuất được.
- **Script**: Kịch bản dùng để sinh giọng đọc — có loại (dịch từ gốc / tự soạn mới).
- **Voice Track**: File âm thanh giọng đọc được sinh ra từ kịch bản, tốc độ đã
  được điều chỉnh để khớp gần đúng thời lượng video gốc.
- **Background Audio**: Nhạc nền/âm thanh nền tách được từ audio gốc (loại bỏ
  giọng nói), dùng để trộn lại với Voice Track — có thể vắng mặt nếu tách thất bại.
- **Output Video**: Video sản phẩm cuối cùng, kết hợp hình ảnh của video gốc với
  giọng đọc mới trộn cùng nhạc nền gốc (nếu tách được).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Người dùng tạo ra được một video sản phẩm hoàn chỉnh (có giọng đọc
  mới) từ một URL TikTok/Douyin/YouTube trong một lần chạy pipeline, không cần thao
  tác thủ công giữa các bước.
- **SC-002**: Với video gốc dưới 3 phút, toàn bộ pipeline hoàn thành xử lý trong
  dưới 8 phút (không tính thời gian chờ tải video qua mạng) — mốc được nới từ 5
  lên 8 phút do bước tách nhạc nền (Demucs, chạy CPU) và bước điều chỉnh tốc độ
  giọng đọc (2 lượt sinh voice) cộng thêm thời gian xử lý.
- **SC-003**: Video output giữ nguyên hình ảnh gốc, giọng đọc mới nghe rõ ràng,
  không bị cắt tiếng, rè hoặc mất âm thanh.
- **SC-004**: Ít nhất 90% video test công khai từ TikTok/Douyin tải xuống thành
  công mà không cần can thiệp thủ công.
- **SC-005**: Người dùng có thể xem lại từng file trung gian (video gốc, nội dung
  trích xuất, kịch bản, giọng đọc, nhạc nền tách được) của bất kỳ job nào để kiểm
  tra hoặc gỡ lỗi.
- **SC-006**: Nhạc nền gốc (nếu video có) vẫn nghe được rõ trong video output,
  không bị mất hoàn toàn khi ghép giọng đọc mới.

## Assumptions

- Người dùng tự cung cấp URL video hợp lệ và công khai (không yêu cầu đăng nhập
  hoặc video riêng tư).
- Ngôn ngữ đích cho giọng đọc là tiếng Việt; các ngôn ngữ khác nằm ngoài phạm vi bản
  đầu tiên này.
- Nhạc nền gốc được tách và giữ lại bằng Demucs (two-stems: vocals/no_vocals); nếu
  video gốc không có nhạc nền tách được (vd chỉ có giọng nói), audio output có thể
  chỉ còn giọng đọc mới — đây không phải lỗi.
- Watermark gắn cứng vào hình ảnh không phải trường hợp phổ biến với nguồn ưu tiên
  (TikTok/Douyin); nếu gặp, xử lý xoá watermark bằng AI nằm ngoài phạm vi MVP này.
- Hệ thống chạy dạng công cụ dòng lệnh/script cục bộ, xử lý một job tại một thời
  điểm; không yêu cầu giao diện web hay xử lý đồng thời nhiều job trong bản đầu.

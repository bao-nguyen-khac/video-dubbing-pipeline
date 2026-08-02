# Feature Specification: Tạo video từ chủ đề bằng AI (script + ảnh + giọng đọc tự động)

**Feature Branch**: `010-topic-video-generation`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "làm video bằng HyperFrames, kiểu như input: tổng quan về các loại tiền tệ => LLM sẽ viết script, search web những chổ còn thiếu, tìm hình ảnh phù hợp và tạo thành script chi tiết => dựng video hoàn chỉnh có sub có giọng đọc"

## Clarifications

### Session 2026-07-31

- Q: HyperFrames yêu cầu chạy runtime Node.js + Chrome headless làm bước
  render video — xung đột trực tiếp với Constitution Principle I ("Python-Only
  Stack", cấm Node.js runtime logic ở tầng pipeline). Hướng nào nên chọn? → A:
  Amend constitution — thêm ngoại lệ tường minh cho phép Node.js/HyperFrames
  CHỈ ở bước render video cuối cùng của pipeline "generate" mới; giữ nguyên
  toàn bộ ý tưởng HyperFrames. **Bắt buộc chạy `/speckit-constitution` để
  amend Principle I trước khi `/speckit-plan`** — nếu chưa amend, plan không
  được phép chốt HyperFrames làm renderer. (Đã amend: Constitution v1.11.0.)
- Q: Có nên cho người dùng duyệt (review gate) outline/scene JSON trước khi
  render, giống chế độ "quản lý pipeline" hiện có, hay chạy thẳng luôn? → A:
  Có — thêm 1 chốt duyệt ngay sau khi sinh xong outline/scene JSON, TRƯỚC khi
  tốn chi phí tìm ảnh/đọc giọng/dựng video, dùng đúng cơ chế bật/tắt "quản lý
  pipeline" đã có sẵn cho các luồng khác (mặc định TẮT, chạy thẳng như User
  Story 1; bật thì dừng chờ duyệt).
- Q: 9router có model dạng agent hỗ trợ tool-use/tự tra cứu web hay không,
  hay cần tích hợp thêm 1 search API riêng? → A: Có — 9router đã có model
  agent hỗ trợ tool-use tự tra cứu web; hệ thống dùng trực tiếp khả năng này
  cho bước tra cứu web (FR-003), không cần thêm search API/key của bên thứ
  ba riêng.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tạo video hoàn chỉnh từ 1 chủ đề văn bản (Priority: P1)

Người dùng chỉ cần nhập 1 chủ đề (VD: "tổng quan về các loại tiền tệ") — không có
video nguồn, không cần chuẩn bị hình ảnh hay kịch bản. Hệ thống tự viết kịch
bản, tự tìm hình ảnh minh hoạ phù hợp cho từng đoạn nội dung, tự đọc giọng theo
kịch bản, tự chèn phụ đề khớp giọng đọc, và xuất ra 1 video MP4 hoàn chỉnh.

**Why this priority**: Đây là toàn bộ giá trị cốt lõi của tính năng — biến 1 ý
tưởng/chủ đề thành video xem được ngay mà không cần quay dựng thủ công hay
chuẩn bị bất kỳ tài nguyên nào.

**Independent Test**: Nhập 1 chủ đề bất kỳ, chờ pipeline chạy xong, nhận được 1
file MP4 có giọng đọc, phụ đề, và hình ảnh minh hoạ khớp nội dung — xem được
trọn vẹn từ đầu đến cuối mà không cần chỉnh sửa thêm.

**Acceptance Scenarios**:

1. **Given** người dùng có 1 chủ đề tiếng Việt, **When** họ submit chủ đề đó
   vào hệ thống, **Then** hệ thống trả về, sau khi xử lý xong, 1 video MP4
   hoàn chỉnh có giọng đọc, phụ đề, và hình ảnh minh hoạ cho từng đoạn nội
   dung.
2. **Given** video đã tạo xong, **When** người dùng xem lại, **Then** phụ đề
   hiển thị đúng khớp với từng câu giọng đọc tương ứng, không lệch thời gian.
3. **Given** chủ đề mơ hồ hoặc quá ngắn (VD chỉ 1-2 từ), **When** hệ thống xử
   lý, **Then** hệ thống vẫn tạo ra kịch bản có cấu trúc hợp lý (mở đầu - nội
   dung chính - kết) thay vì báo lỗi hoặc tạo ra video rỗng.

---

### User Story 2 - Tự động tra cứu web để bổ sung dữ kiện còn thiếu (Priority: P2)

Trước khi hoàn thiện kịch bản chi tiết, hệ thống tự tìm kiếm thông tin trên web
liên quan đến chủ đề để bổ sung số liệu/dữ kiện thực tế mà LLM có thể không
biết hoặc đã lỗi thời, giúp nội dung video chính xác và cập nhật hơn thay vì
chỉ dựa vào kiến thức nội tại của LLM.

**Why this priority**: Nâng cao chất lượng và độ tin cậy của nội dung — quan
trọng nhưng không chặn việc có video hoạt động được (User Story 1 vẫn tạo ra
video hoàn chỉnh kể cả khi bước tra cứu web bị lỗi hoặc bỏ qua).

**Independent Test**: So sánh kịch bản sinh ra cho cùng 1 chủ đề có tính thời
sự/số liệu cụ thể khi bật và khi tắt bước tra cứu web — bản có tra cứu chứa
dữ kiện cụ thể/cập nhật hơn bản chỉ dựa vào kiến thức sẵn có.

**Acceptance Scenarios**:

1. **Given** chủ đề cần dữ kiện cụ thể (số liệu, sự kiện thực tế), **When**
   hệ thống viết kịch bản chi tiết, **Then** kịch bản chứa ít nhất một số dữ
   kiện/số liệu lấy được từ kết quả tra cứu web.
2. **Given** bước tra cứu web thất bại (lỗi mạng/API), **When** pipeline tiếp
   tục chạy, **Then** hệ thống vẫn tạo được video hoàn chỉnh dựa trên kiến
   thức sẵn có của LLM, không dừng job vì lý do này.

---

### User Story 3 - Tự động xử lý khi không tìm được hình ảnh phù hợp (Priority: P3)

Với mỗi đoạn kịch bản, hệ thống tìm hình ảnh minh hoạ theo từ khoá liên quan;
khi không tìm được kết quả phù hợp, hệ thống dùng hình ảnh thay thế hợp lý
thay vì để đoạn đó thiếu hình hoặc làm video bị lỗi.

**Why this priority**: Đảm bảo tính ổn định và hoàn thiện của sản phẩm cuối,
tránh video bị "vá lỗi" giữa chừng — nhưng đây là trường hợp biên (edge case),
không phải luồng chính.

**Independent Test**: Dùng 1 chủ đề có từ khoá hiếm/khó tìm ảnh, xác nhận video
ra vẫn đủ hình cho mọi đoạn, không có đoạn nào bị màn hình đen hoặc khiến job
lỗi.

**Acceptance Scenarios**:

1. **Given** 1 đoạn kịch bản có từ khoá tìm ảnh không ra kết quả phù hợp,
   **When** hệ thống dựng video, **Then** đoạn đó vẫn có hình ảnh minh hoạ
   thay thế hợp lý thay vì để trống hoặc lỗi.

---

### User Story 4 - Duyệt outline/kịch bản trước khi tốn chi phí tìm ảnh/TTS/render (Priority: P4)

Khi bật chế độ "quản lý pipeline", người dùng được xem lại outline và scene
JSON (kịch bản đã chia đoạn) ngay sau khi hệ thống sinh xong, có thể chỉnh sửa
nội dung trước khi phê duyệt cho chạy tiếp — tránh tốn chi phí tìm ảnh/đọc
giọng/dựng video cho 1 kịch bản chưa ưng ý.

**Why this priority**: Giá trị bổ sung về kiểm soát chi phí/chất lượng, không
chặn luồng tự động mặc định (User Story 1 vẫn chạy thẳng khi tắt chế độ này)
— ưu tiên thấp nhất vì là tính năng vận hành/kiểm soát, không phải giá trị
đầu ra cốt lõi.

**Independent Test**: Bật chế độ quản lý pipeline, submit 1 chủ đề, xác nhận
job dừng lại đúng ở bước outline/scene JSON chờ duyệt; sửa 1 đoạn rồi phê
duyệt, xác nhận video ra khớp đúng bản đã sửa.

**Acceptance Scenarios**:

1. **Given** người dùng bật chế độ quản lý pipeline khi submit chủ đề,
   **When** hệ thống sinh xong outline/scene JSON, **Then** job dừng lại chờ
   người dùng xem/sửa/phê duyệt trước khi sang bước tìm ảnh/đọc giọng/dựng
   video.
2. **Given** người dùng sửa nội dung 1 đoạn scene JSON tại chốt duyệt,
   **When** họ phê duyệt, **Then** video cuối cùng phản ánh đúng nội dung đã
   sửa, không dùng bản gốc chưa sửa.
3. **Given** người dùng KHÔNG bật chế độ quản lý pipeline, **When** submit
   chủ đề, **Then** hệ thống chạy thẳng tới video hoàn chỉnh, không dừng ở
   bước nào (giữ đúng hành vi User Story 1).

---

### Edge Cases

- Chủ đề nhạy cảm hoặc có khả năng vi phạm chính sách nội dung (bạo lực,
  chính trị gây tranh cãi...) — hệ thống xử lý bằng cách nào?
- Chủ đề quá rộng (VD "lịch sử thế giới") khiến 1 video không thể bao quát đủ
  — hệ thống tự giới hạn phạm vi kịch bản thế nào để video không bị quá dài
  hoặc quá sơ sài?
- Giọng đọc tạo ra dài hơn/ngắn hơn đáng kể so với dự kiến ban đầu của 1 đoạn
  — hệ thống đồng bộ thời lượng hiển thị hình ảnh theo đúng giọng đọc thật ra
  sao?
- Kết quả tra cứu web trả về thông tin không đáng tin cậy hoặc mâu thuẫn — hệ
  thống có cơ chế nào để giảm rủi ro đưa sai thông tin vào kịch bản không?
- Hai chủ đề tương tự nhau được submit liên tiếp — có tái sử dụng tài nguyên
  (hình ảnh, kịch bản) đã tạo trước đó không, hay luôn tạo mới hoàn toàn?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST cho phép người dùng nhập 1 chủ đề dạng văn bản tự
  do làm input duy nhất — không cần URL video nguồn, không cần tải lên bất kỳ
  tài nguyên nào khác.
- **FR-002**: Hệ thống MUST tự động sinh kịch bản có cấu trúc rõ ràng (mở đầu,
  nội dung chính chia theo ý/đoạn, kết) từ chủ đề đầu vào.
- **FR-003**: Hệ thống MUST tự động tra cứu thông tin bổ sung trên web liên
  quan đến chủ đề trước khi hoàn thiện kịch bản chi tiết, nhằm tăng độ chính
  xác và tính cập nhật của nội dung.
- **FR-004**: Hệ thống MUST chia kịch bản thành các đoạn (scene) riêng biệt,
  mỗi đoạn tương ứng 1 phần nội dung sẽ có 1 hình ảnh minh hoạ và 1 đoạn
  giọng đọc riêng.
- **FR-005**: Hệ thống MUST tự động tìm và gán 1 hình ảnh minh hoạ phù hợp
  với nội dung cho mỗi đoạn kịch bản.
- **FR-006**: Hệ thống MUST tự động tạo giọng đọc cho toàn bộ kịch bản, theo
  từng đoạn tương ứng.
- **FR-007**: Hệ thống MUST tự động chèn phụ đề hiển thị đúng khớp thời gian
  với giọng đọc tương ứng của từng đoạn.
- **FR-008**: Hệ thống MUST xuất ra 1 file video hoàn chỉnh (hình ảnh + giọng
  đọc + phụ đề đã đồng bộ) mà không cần người dùng thao tác dựng thủ công.
- **FR-009**: Hệ thống MUST tiếp tục hoàn thành video ngay cả khi bước tra
  cứu web thất bại — dùng kiến thức sẵn có của LLM thay thế, không để job
  dừng/lỗi hoàn toàn chỉ vì lý do này.
- **FR-010**: Hệ thống MUST dùng hình ảnh thay thế hợp lý cho đoạn nào không
  tìm được ảnh khớp từ khoá, thay vì để đoạn đó thiếu hình ảnh.
- **FR-011**: Hệ thống MUST cho phép người dùng theo dõi tiến trình xử lý
  (đang viết kịch bản / đang tìm ảnh / đang đọc giọng / đang dựng video),
  theo cùng cơ chế theo dõi job đã có sẵn cho các luồng xử lý khác.
- **FR-012**: Khi người dùng bật chế độ "quản lý pipeline" (cùng cơ chế
  bật/tắt đã có ở các luồng xử lý khác), hệ thống MUST dừng lại ngay sau khi
  sinh xong outline/scene JSON, cho phép người dùng xem và sửa nội dung, và
  chỉ tiếp tục sang bước tìm ảnh/đọc giọng/dựng video sau khi được phê duyệt.
  Khi TẮT chế độ này (mặc định), hệ thống chạy thẳng không dừng ở bước nào.

### Key Entities *(include if feature involves data)*

- **Topic Request**: Chủ đề văn bản người dùng nhập vào — điểm khởi đầu của
  job, không gắn với video nguồn nào.
- **Script**: Kịch bản văn bản đầy đủ được sinh ra, có cấu trúc mở đầu / nội
  dung chính / kết.
- **Scene**: 1 đơn vị nội dung trong kịch bản — gồm đoạn văn bản giọng đọc, 1
  hình ảnh minh hoạ tương ứng, và khoảng thời gian hiển thị.
- **Generated Video**: File video hoàn chỉnh cuối cùng, tổng hợp từ toàn bộ
  Scene theo đúng thứ tự trong kịch bản.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Người dùng nhập 1 chủ đề và nhận được video hoàn chỉnh mà không
  cần tự chuẩn bị bất kỳ tài nguyên nào khác (không tự tìm ảnh, không tự viết
  kịch bản, không tự thu âm).
- **SC-002**: Ít nhất 90% số đoạn (scene) trong video có hình ảnh minh hoạ
  liên quan trực tiếp đến nội dung đoạn đó, đánh giá trên tập video thử
  nghiệm.
- **SC-003**: Phụ đề hiển thị lệch không quá 0.3 giây so với giọng đọc tương
  ứng, xuyên suốt toàn bộ video.
- **SC-004**: Với chủ đề có yêu cầu dữ kiện cụ thể, kịch bản chứa được ít
  nhất 1 thông tin cập nhật/thực tế lấy từ kết quả tra cứu web thành công
  (không chỉ nội dung chung chung từ kiến thức sẵn có).
- **SC-005**: Toàn bộ quá trình từ lúc nhập chủ đề đến khi có video hoàn
  chỉnh không yêu cầu người dùng can thiệp thủ công, trừ khi người dùng chủ
  động bật chế độ duyệt thủ công (giống các luồng xử lý khác hiện có).

## Assumptions

- Ngôn ngữ kịch bản và giọng đọc mặc định là tiếng Việt, khớp với toàn bộ sản
  phẩm hiện có (giọng đọc vi-VN, nội dung các job khác đều xử lý tiếng Việt).
- Video hướng tới định dạng ngắn/trung bình (khoảng 1-5 phút), tỉ lệ khung
  hình dọc (9:16) — phù hợp nền tảng phân phối chính hiện có của hệ thống
  (TikTok/Shorts); có thể mở rộng sang ngang (16:9) ở phiên bản sau nếu cần.
- Nguồn hình ảnh minh hoạ là kho ảnh/video stock miễn phí có sẵn trên
  internet cho phiên bản đầu — chưa dùng ảnh do AI tự sinh ra.
- Việc dựng video hoàn chỉnh (ghép hình ảnh + giọng đọc + phụ đề thành 1 bố
  cục) dùng công cụ render HTML→video mã nguồn mở "HyperFrames" theo đúng ý
  tưởng ban đầu của người dùng; phiên bản đầu chỉ có 1 bố cục cố định (hình
  ảnh toàn khung hình + phụ đề phía dưới), chưa hỗ trợ nhiều kiểu trình bày.
  HyperFrames chạy runtime Node.js — theo Clarifications, đây là ngoại lệ MUST
  được amend vào Constitution (Principle I) trước khi lập plan kỹ thuật, vì
  hiện Principle I cấm Node.js runtime logic ở tầng pipeline.
- Tính năng này tái sử dụng cơ chế "quản lý pipeline" (bật/tắt) đã có sẵn cho
  các luồng xử lý khác; chốt duyệt duy nhất của tính năng này nằm ngay sau
  bước sinh outline/scene JSON — xem FR-012, User Story 4.
- Bước tra cứu web (FR-003) dùng trực tiếp model dạng agent có sẵn trong
  9router (LLM router hiện có của hệ thống) — model này tự có khả năng
  tool-use/tra cứu web, không cần tích hợp thêm 1 search API/API key của bên
  thứ ba riêng.
- Chủ đề đầu vào được giả định là nội dung hợp lệ, không vi phạm chính sách —
  chưa có yêu cầu kiểm duyệt nội dung đặc biệt ở phiên bản đầu.

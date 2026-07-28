# Feature Specification: Đăng video lên TikTok/YouTube Shorts từ giao diện web

**Feature Branch**: `006-publish-video-tab`

**Created**: 2026-07-27

**Status**: Draft

**Input**: User description: "thêm 1 tab publish video, ở đây sẽ cho chọn tiktok, ytb short cho điền tiêu đề cho video và nút publish cho phép up video lên kênh của tôi"

## Clarifications

### Session 2026-07-27

- Q: TikTok Content Posting API yêu cầu app được TikTok duyệt (audit) mới
  được đăng công khai ngay — nếu chưa duyệt, "đăng thành công" ở v1 nên
  hiểu là gì? → A (đã trải qua 2 vòng điều chỉnh trong phiên clarify — xem
  lịch sử quyết định dưới đây): v1 đạt mục tiêu đăng **công khai ngay lập
  tức**, không phụ thuộc lịch duyệt của nền tảng, **và không cần đánh đổi
  rủi ro tài khoản** — bằng cách đi qua 1 dịch vụ trung gian đã được nền
  tảng cấp phép đăng bài tự động từ trước (kế thừa quyền audit có sẵn của
  dịch vụ đó), thay vì hệ thống tự xin audit riêng hoặc tự động hoá trình
  duyệt để giả lập đăng tay.
  - Lịch sử quyết định (để tránh lặp lại hướng đã loại): ban đầu định tự
    động hoá trình duyệt (browser automation) để đăng công khai ngay, chấp
    nhận rủi ro tài khoản bị khoá — sau đó bị loại bỏ ý định thêm cơ chế
    "qua mặt" hệ thống chống bot (kể cả qua thư viện có sẵn) vì vượt ra
    ngoài phạm vi hỗ trợ được của agent thực hiện task này, không phải giới
    hạn kỹ thuật của bản thân tính năng — cuối cùng tìm được hướng dịch vụ
    trung gian đã audit sẵn, giải quyết đúng gốc vấn đề mà không cần cả
    browser automation lẫn tự xin audit.
- Q: Dịch vụ trung gian cụ thể nào được chọn cho v1? → A: **Zernio**
  (`https://zernio.com`, API docs `https://docs.zernio.com`) — REST API hợp
  nhất, hỗ trợ cả TikTok và YouTube, người dùng liên kết kênh qua luồng OAuth
  chính chủ của từng nền tảng trên dashboard/URL kết nối của Zernio. Đây là
  quyết định của người dùng dự án; mọi ràng buộc "dịch vụ trung gian" nêu
  trong spec này (FR-012, Edge Cases, Assumptions) áp dụng cho Zernio.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Đăng video đã xử lý lên TikTok hoặc YouTube Shorts (Priority: P1)

Người dùng đã có 1 job xử lý xong (video lồng tiếng/phụ đề hoàn chỉnh), muốn
đăng thẳng video đó lên kênh TikTok hoặc YouTube của mình mà không cần tải
video về máy rồi tự đăng tay qua app/website gốc của từng nền tảng.

**Why this priority**: Đây là toàn bộ giá trị của tính năng — hoàn thiện
luồng "tải video gốc → xử lý → đăng lại" thành 1 quy trình liền mạch trong
cùng 1 giao diện, thay vì người dùng phải tự tải file về rồi đăng tay.

**Independent Test**: Từ 1 job đã có video kết quả, mở tab "Đăng video",
chọn nền tảng (TikTok hoặc YouTube Shorts), điền tiêu đề, bấm "Đăng" — video
xuất hiện trên kênh của người dùng ở nền tảng đã chọn.

**Acceptance Scenarios**:

1. **Given** người dùng chưa từng kết nối kênh TikTok, **When** chọn TikTok
   ở tab Đăng video lần đầu, **Then** hệ thống yêu cầu người dùng xác thực
   quyền truy cập kênh TikTok của họ trước khi cho đăng.
2. **Given** người dùng đã kết nối kênh TikTok trước đó, **When** mở tab
   Đăng video ở lần dùng sau, **Then** không cần xác thực lại — có thể chọn
   video, điền tiêu đề và đăng ngay.
3. **Given** người dùng đã chọn 1 job có video kết quả, chọn nền tảng, điền
   tiêu đề, **When** bấm "Đăng", **Then** video được tải lên đúng kênh của
   người dùng ở nền tảng đã chọn, kèm tiêu đề đã điền, và người dùng thấy
   trạng thái đăng thành công.
4. **Given** quá trình đăng đang chạy, **When** có lỗi (mất kết nối, nền
   tảng từ chối, quyền truy cập hết hạn...), **Then** người dùng thấy thông
   báo lỗi rõ ràng và có thể thử đăng lại, video KHÔNG bị đăng trùng lặp.
5. **Given** người dùng chưa điền tiêu đề, **When** bấm "Đăng", **Then** hệ
   thống yêu cầu điền tiêu đề trước khi cho phép đăng (tiêu đề là bắt buộc).

---

### Edge Cases

- Video của job chưa xử lý xong (job đang chạy hoặc lỗi) thì không hiển thị
  trong danh sách video có thể đăng.
- Người dùng bấm "Đăng" nhiều lần liên tiếp trước khi lượt đăng trước hoàn
  tất: hệ thống KHÔNG được tạo ra nhiều bài đăng trùng lặp.
- Quyền truy cập kênh đã kết nối bị nền tảng thu hồi/hết hạn ở lần đăng sau:
  hệ thống báo lỗi rõ ràng và yêu cầu kết nối lại, không đăng nhầm lên kênh
  khác hoặc thất bại âm thầm.
- Video vượt quá giới hạn thời lượng/kích thước cho phép của nền tảng đích:
  hệ thống báo lỗi rõ nguyên nhân trước khi thử đăng (hoặc ngay khi nền tảng
  từ chối), không để người dùng đoán.
- Người dùng ngắt kết nối 1 kênh đã liên kết: các lượt đăng sau tới kênh đó
  bị chặn cho tới khi kết nối lại, không dùng ngầm quyền truy cập cũ.
- Dịch vụ trung gian phụ trách việc đăng bài gặp sự cố/ngừng hoạt động: hệ
  thống PHẢI báo lỗi rõ ràng cho người dùng biết lượt đăng không thực hiện
  được vì lý do ở phía dịch vụ trung gian, không phải lỗi từ video/tài
  khoản của người dùng.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Giao diện web PHẢI có 1 khu vực/tab riêng "Đăng video", tách
  biệt với luồng tạo job xử lý video hiện có.
- **FR-002**: Người dùng PHẢI chọn được 1 video kết quả từ các job đã xử lý
  xong (`status=done`, có video kết quả) để đăng — không hỗ trợ đăng video
  tải lên trực tiếp từ máy ngoài luồng xử lý của hệ thống.
- **FR-003**: Người dùng PHẢI chọn được nền tảng đích cho mỗi lượt đăng:
  TikTok hoặc YouTube Shorts.
- **FR-004**: Người dùng PHẢI điền được tiêu đề cho video trước khi đăng;
  tiêu đề là bắt buộc, hệ thống PHẢI chặn đăng nếu tiêu đề trống.
- **FR-005**: Trước lượt đăng đầu tiên tới 1 nền tảng, hệ thống PHẢI yêu cầu
  người dùng xác thực/cấp quyền truy cập kênh của họ ở nền tảng đó.
- **FR-006**: Sau khi đã xác thực 1 kênh, hệ thống PHẢI ghi nhớ quyền truy
  cập đó cho các lượt đăng sau tới cùng nền tảng, không yêu cầu xác thực lại
  mỗi lần đăng (trừ khi quyền truy cập hết hạn/bị thu hồi — xem FR-008).
- **FR-007**: Khi bấm nút "Đăng", hệ thống PHẢI tải video lên đúng kênh
  người dùng đã xác thực ở nền tảng đã chọn, kèm tiêu đề đã điền, và hiển thị
  trạng thái tiến trình đăng (đang đăng / thành công / thất bại).
- **FR-008**: Nếu quyền truy cập kênh đã hết hạn hoặc bị thu hồi, hệ thống
  PHẢI báo lỗi rõ ràng và yêu cầu người dùng xác thực lại (FR-005), không
  đăng thất bại âm thầm hoặc đăng nhầm kênh.
- **FR-009**: Hệ thống PHẢI ngăn việc tạo nhiều bài đăng trùng lặp từ nhiều
  lượt bấm "Đăng" liên tiếp cho cùng 1 video trong lúc lượt đăng trước chưa
  hoàn tất.
- **FR-010**: Người dùng PHẢI xem được lịch sử các lượt đăng đã thực hiện
  (video nào, nền tảng nào, tiêu đề gì, thành công hay lỗi) để biết video đã
  được đăng ở đâu trước đó.
- **FR-011**: Người dùng PHẢI ngắt kết nối được 1 kênh đã liên kết; sau khi
  ngắt, các lượt đăng tới kênh đó PHẢI bị chặn cho tới khi kết nối lại
  (FR-005).
- **FR-012**: Việc xác thực/cấp quyền truy cập kênh (FR-005) và việc đăng
  video (FR-007) PHẢI đi qua đúng cơ chế được nền tảng đích cho phép chính
  thức (không giả lập hành vi đăng nhập/thao tác tay của người dùng) — đảm
  bảo tài khoản người dùng không có rủi ro bị nền tảng xử lý vì hành vi bất
  thường.

### Key Entities

- **Kết nối kênh (Channel Connection)**: Đại diện quyền truy cập đã được
  người dùng cấp cho 1 kênh TikTok hoặc YouTube cụ thể — gồm nền tảng, thông
  tin nhận diện kênh (tên/id kênh hiển thị cho người dùng), trạng thái còn
  hiệu lực hay đã hết hạn/bị ngắt.
- **Lượt đăng (Publish Attempt)**: 1 lần đăng 1 video kết quả (thuộc 1 job)
  lên 1 kênh đã kết nối — gồm video/job liên quan, nền tảng đích, tiêu đề đã
  điền, trạng thái (đang đăng/thành công/lỗi), thời điểm thực hiện.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Người dùng đăng được 1 video đã xử lý xong lên kênh TikTok
  hoặc YouTube của mình trong vòng 2 phút kể từ lúc mở tab Đăng video (không
  tính thời gian tải lên do tốc độ mạng), không cần rời khỏi giao diện web
  để thao tác thủ công ở nơi khác.
- **SC-002**: Sau lần xác thực kênh đầu tiên, 100% lượt đăng tiếp theo tới
  cùng kênh không yêu cầu xác thực lại.
- **SC-003**: 0% lượt đăng bị trùng lặp do bấm nút nhiều lần trong 1 lượt
  đăng.
- **SC-004**: 100% lượt đăng lỗi hiển thị thông báo cho người dùng biết rõ
  nguyên nhân (hết quyền truy cập, nền tảng từ chối, lỗi mạng...) thay vì
  thất bại im lặng.
- **SC-005**: Video đăng lên hiển thị công khai ngay lập tức trên kênh của
  người dùng (không phải trạng thái riêng tư/chờ duyệt), mà không phát sinh
  cảnh báo/hạn chế bất thường nào từ nền tảng tới tài khoản của người dùng.

## Assumptions

- Chỉ hỗ trợ đăng video kết quả do chính hệ thống này tạo ra (từ job đã xử
  lý xong), không phải công cụ đăng video tổng quát cho file bất kỳ.
- Mỗi lượt đăng chỉ nhắm tới 1 nền tảng; đăng đồng thời lên cả TikTok và
  YouTube Shorts trong 1 lượt bấm không thuộc phạm vi bản đầu — người dùng
  lặp lại thao tác riêng cho từng nền tảng nếu muốn đăng cả hai.
- Video được đăng **công khai ngay lập tức** sau khi hoàn tất lượt đăng
  (không phải trạng thái riêng tư/chờ duyệt) — xem Clarifications — thông
  qua 1 dịch vụ trung gian đã được nền tảng cấp phép sẵn (kế thừa quyền
  audit có sẵn), không tự động hoá hành vi đăng nhập/thao tác tay và không
  cần hệ thống này tự xin duyệt riêng với từng nền tảng.
- Dịch vụ trung gian dùng ở v1 là **Zernio** (xem Clarifications). Người dùng
  tự có tài khoản Zernio và API key riêng; hệ thống này không tự tạo tài khoản
  hộ. Chi phí sử dụng Zernio (tính theo số kênh kết nối) do người dùng chịu,
  nằm ngoài phạm vi tính năng.
- Tính năng phụ thuộc vào tính khả dụng của dịch vụ trung gian đã chọn; nếu
  dịch vụ đó ngừng hoạt động hoặc đổi chính sách, tính năng đăng video có
  thể bị ảnh hưởng cho tới khi chuyển sang dịch vụ/cơ chế khác — rủi ro này
  được chấp nhận ở v1, không có phương án dự phòng tự động.
- Không hỗ trợ chỉnh sửa/xoá bài đăng đã lên nền tảng từ giao diện này — các
  thao tác đó thực hiện trực tiếp trên app/website gốc của nền tảng như hiện
  tại; hệ thống chỉ ghi nhận lịch sử lượt đăng (FR-010), không đồng bộ hai
  chiều.
- Mỗi người dùng (tài khoản đăng nhập giao diện web) kết nối kênh TikTok/
  YouTube của riêng họ; không có khái niệm chia sẻ kênh giữa nhiều người
  dùng ở bản đầu.

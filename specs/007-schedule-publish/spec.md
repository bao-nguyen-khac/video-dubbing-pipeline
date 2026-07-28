# Feature Specification: Hẹn giờ đăng video

**Feature Branch**: `007-schedule-publish`

**Created**: 2026-07-28

**Status**: Draft

**Input**: User description: "tôi muốn thêm tính năng hẹn giờ đăng thì hệ thống mình
sẽ push qua bên zernio và bên zernio sẽ chờ đến giờ mới đăng"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Đặt lịch đăng video vào giờ mong muốn (Priority: P1)

Người dùng có video đã xử lý xong nhưng chưa muốn đăng ngay — muốn bài lên vào
khung giờ có nhiều người xem, hoặc muốn rải nhiều video ra nhiều ngày thay vì
đăng dồn một lúc. Họ chọn video, điền tiêu đề, chọn ngày giờ, và bài sẽ tự lên
đúng giờ đó **kể cả khi máy của họ đã tắt**.

**Why this priority**: Đây là toàn bộ giá trị của tính năng. Hiện tại muốn đăng
đúng khung giờ tốt thì phải ngồi canh đúng lúc đó để bấm nút — bất khả thi với
khung giờ đêm/sáng sớm, và không rải được nhiều video theo lịch đều đặn.

**Independent Test**: Đặt lịch 1 video vào thời điểm khoảng 20 phút sau, **tắt
hẳn hệ thống**, tới giờ kiểm tra kênh — video đã lên công khai đúng giờ.

**Acceptance Scenarios**:

1. **Given** người dùng đã chọn video và điền tiêu đề, **When** chọn "hẹn giờ"
   và nhập thời điểm trong tương lai rồi xác nhận, **Then** hệ thống ghi nhận
   lượt đăng ở trạng thái "đang chờ đăng" kèm thời điểm sẽ đăng.
2. **Given** đã có bài hẹn giờ, **When** hệ thống của người dùng ngừng chạy
   trước thời điểm đó, **Then** video vẫn được đăng đúng giờ đã hẹn.
3. **Given** người dùng nhập thời điểm trong quá khứ hoặc cách hiện tại dưới 15
   phút, **When** xác nhận, **Then** hệ thống từ chối và nêu rõ phải hẹn cách ít
   nhất 15 phút.
4. **Given** bài đã hẹn giờ đã tới giờ và lên thành công, **When** người dùng mở
   lại giao diện, **Then** thấy trạng thái "đã đăng" kèm link bài đăng.
5. **Given** bài đã hẹn giờ bị nền tảng từ chối lúc tới giờ đăng, **When** người
   dùng mở lại giao diện, **Then** thấy trạng thái thất bại kèm nguyên nhân rõ
   ràng — không hiển thị nhầm là vẫn đang chờ.
6. **Given** người dùng nhập thời điểm cách hiện tại quá 3 ngày, **When** xác
   nhận, **Then** hệ thống từ chối và nêu rõ chỉ hẹn được tối đa 3 ngày.

---

### User Story 2 - Xem và huỷ bài đã hẹn giờ (Priority: P2)

Người dùng đặt nhầm giờ, hoặc đổi ý về nội dung, cần huỷ bài trước khi nó lên.
Họ cũng cần nhìn được toàn bộ những bài đang chờ để biết sắp có gì lên kênh.

**Why this priority**: Không có đường lùi thì một lần gõ nhầm ngày sẽ khiến bài
lên sai thời điểm mà không cách nào chặn — mà bài đã lên thì giao diện này không
sửa/xoá được nữa. Tuy vậy vẫn xếp sau US1 vì US1 tự nó đã dùng được.

**Independent Test**: Đặt lịch 1 video, huỷ nó trước giờ, chờ qua thời điểm đã
hẹn — video KHÔNG xuất hiện trên kênh.

**Acceptance Scenarios**:

1. **Given** có các bài đang chờ đăng, **When** mở giao diện, **Then** thấy danh
   sách các bài đó kèm thời điểm sẽ đăng, sắp xếp theo giờ đăng gần nhất trước.
2. **Given** một bài đang chờ đăng, **When** người dùng huỷ, **Then** bài không
   được đăng khi tới giờ, và lịch sử ghi nhận là đã huỷ.
3. **Given** một bài đã đăng rồi, **When** người dùng thử huỷ, **Then** hệ thống
   từ chối và nêu rõ bài đã lên nên phải xoá trực tiếp trên nền tảng.
4. **Given** một bài đang trong quá trình đăng (đã tới giờ), **When** người dùng
   thử huỷ, **Then** hệ thống báo rõ không huỷ được nữa thay vì báo thành công
   giả.
5. **Given** có bài đang chờ đăng lên một kênh, **When** người dùng ngắt kết nối
   chính kênh đó, **Then** các bài đó bị huỷ theo và người dùng được cho biết đã
   huỷ những bài nào; qua giờ đã hẹn, video KHÔNG xuất hiện trên kênh.

---

### Edge Cases

- Thời điểm hẹn rơi đúng lúc dịch vụ trung gian gặp sự cố: bài không lên đúng
  giờ — người dùng PHẢI thấy được trạng thái thất bại kèm nguyên nhân khi quay
  lại, không để bài "treo" mãi ở trạng thái đang chờ.
- Hệ thống của người dùng ngừng chạy nhiều ngày: các bài hẹn giờ trong khoảng đó
  vẫn lên bình thường; khi hệ thống chạy lại, trạng thái hiển thị PHẢI được cập
  nhật đúng với thực tế đã xảy ra.
- Người dùng hẹn 2 bài có cùng nội dung lên cùng một kênh cách nhau dưới 24 giờ:
  nền tảng/dịch vụ trung gian có thể từ chối bài thứ hai vì trùng nội dung — hệ
  thống PHẢI báo rõ nguyên nhân này thay vì báo lỗi chung chung.
- Người dùng ngắt kết nối kênh sau khi đã hẹn giờ bài lên kênh đó: mọi bài đang
  chờ đăng lên kênh đó PHẢI bị huỷ ngay tại thời điểm ngắt kết nối, tuyệt đối
  không để bài lên ngầm sau đó (xem FR-015).
- Người dùng đặt lịch quá xa trong tương lai khiến video đã tải lên dịch vụ
  trung gian có thể bị dọn trước khi tới giờ đăng (xem Clarifications).
- Giờ nhập vào và giờ bài thực sự lên PHẢI khớp nhau — không lệch do khác biệt
  múi giờ giữa giao diện, hệ thống và dịch vụ trung gian.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Người dùng PHẢI chọn được giữa "đăng ngay" và "hẹn giờ đăng" cho
  mỗi lượt đăng; đăng ngay vẫn là hành vi mặc định như hiện tại.
- **FR-002**: Khi chọn hẹn giờ, người dùng PHẢI nhập được ngày và giờ mong muốn.
- **FR-003**: Hệ thống PHẢI từ chối thời điểm cách hiện tại dưới **15 phút**
  (gồm cả thời điểm trong quá khứ), kèm thông báo nêu rõ mức tối thiểu này —
  video cần thời gian tải lên trước khi tới giờ đăng (xem Clarifications).
- **FR-004**: Hệ thống PHẢI từ chối thời điểm cách lúc đặt lịch quá **3 ngày**,
  kèm thông báo nêu rõ giới hạn này (xem Clarifications về lý do chọn ngưỡng).
- **FR-005**: Sau khi đặt lịch thành công, video PHẢI được đăng đúng thời điểm đã
  hẹn **mà không cần hệ thống của người dùng đang chạy** vào lúc đó.
- **FR-006**: Thời điểm hẹn PHẢI được hiểu và hiển thị theo múi giờ của người
  dùng; giờ người dùng thấy và giờ bài thực sự lên PHẢI là một.
- **FR-007**: Lượt đăng đã hẹn PHẢI có trạng thái riêng, phân biệt được với
  "đang đăng" và "đã đăng", kèm thời điểm sẽ đăng.
- **FR-008**: Hệ thống PHẢI KHÔNG đánh dấu thất bại cho một lượt đăng chỉ vì nó
  chưa tới giờ đăng.
- **FR-009**: Khi người dùng mở giao diện, trạng thái các bài đã hẹn PHẢI được
  đối soát lại với thực tế (đã đăng / thất bại / vẫn đang chờ) và hiển thị đúng.
- **FR-010**: Người dùng PHẢI xem được danh sách các bài đang chờ đăng, kèm video
  nào, kênh nào, tiêu đề gì và sẽ lên lúc nào.
- **FR-011**: Người dùng PHẢI huỷ được một bài đang chờ đăng; sau khi huỷ, bài đó
  PHẢI KHÔNG được đăng khi tới giờ.
- **FR-012**: Hệ thống PHẢI từ chối huỷ với bài đã đăng hoặc đang trong quá trình
  đăng, kèm thông báo nêu rõ lý do.
- **FR-013**: Lịch sử lượt đăng PHẢI ghi nhận cả bài đã huỷ lẫn bài hẹn giờ thất
  bại, kèm nguyên nhân, để người dùng biết chuyện gì đã xảy ra khi họ vắng mặt.
- **FR-014**: Mọi ràng buộc đang áp dụng cho đăng ngay (tiêu đề bắt buộc, video
  phải thuộc job đã xử lý xong, giới hạn thời lượng/kích thước của nền tảng, kênh
  phải còn kết nối) PHẢI áp dụng y nguyên cho hẹn giờ và được kiểm tra **ngay lúc
  đặt lịch**, không đợi tới giờ đăng mới báo lỗi.
- **FR-015**: Khi người dùng ngắt kết nối một kênh, hệ thống PHẢI huỷ mọi bài
  đang chờ đăng lên kênh đó sao cho chúng KHÔNG lên được nữa **kể cả khi hệ
  thống này không chạy vào giờ đã hẹn**, và PHẢI cho người dùng biết những bài
  nào vừa bị huỷ theo.

### Key Entities

- **Lượt đăng (Publish Attempt)**: Mở rộng thực thể đã có của tính năng đăng video
  — bổ sung *hình thức đăng* (ngay / hẹn giờ), *thời điểm hẹn đăng*, và các trạng
  thái mới *đang chờ đăng* và *đã huỷ* bên cạnh các trạng thái sẵn có.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Video được hẹn giờ lên đúng thời điểm đã hẹn với sai số không quá
  5 phút, kể cả khi hệ thống của người dùng đã tắt hoàn toàn từ trước đó.
- **SC-002**: 0% bài đang chờ đăng bị hiển thị nhầm thành thất bại chỉ vì chưa
  tới giờ.
- **SC-003**: 100% bài hẹn giờ không lên được (nền tảng từ chối, sự cố dịch vụ
  trung gian, hết hạn quyền truy cập kênh) hiển thị đúng trạng thái thất bại kèm
  nguyên nhân ngay trong lần đầu người dùng mở lại giao diện.
- **SC-004**: 100% bài bị huỷ trước giờ hẹn không xuất hiện trên kênh.
- **SC-005**: Người dùng đặt được lịch cho 1 video trong vòng 1 phút kể từ lúc mở
  giao diện đăng video.
- **SC-006**: Giờ hiển thị trên giao diện và giờ bài thực sự lên trên kênh lệch
  nhau không quá 5 phút — không có sai lệch mang tính hệ thống do múi giờ.

## Clarifications

### Session 2026-07-28

- Q: Khoảng thời gian hẹn tối đa là bao lâu? → A: **Tối đa 3 ngày** kể từ lúc
  đặt lịch.
  - Lý do chọn ngưỡng thận trọng: video được tải lên dịch vụ trung gian ngay lúc
    đặt lịch, nhưng tài liệu của dịch vụ đó **không công bố file được giữ bao
    lâu** (đã tra cả tài liệu API lẫn `llms.txt` của họ), trong khi một endpoint
    tải lên khác của chính họ ghi rõ tự xoá sau 7 ngày. Nếu file bị dọn trước
    giờ đăng thì bài hỏng đúng vào lúc người dùng không có mặt để biết. 3 ngày
    nằm sâu dưới mọi mốc có thể, vẫn đủ cho nhu cầu rải bài trong tuần, và nới
    ra về sau dễ hơn nhiều so với xử lý bài hỏng.
- Q: Bài đang chờ đăng sẽ ra sao khi người dùng ngắt kết nối kênh? → A: **Ngắt
  kết nối kênh sẽ huỷ luôn mọi bài đang chờ đăng lên kênh đó**, và báo cho người
  dùng biết đã huỷ những bài nào.
  - Lý do: dịch vụ trung gian đăng bài mà không cần hệ thống này chạy, nên nếu
    chỉ chặn ở phía hệ thống này mà không huỷ bên đó thì tới giờ video **vẫn
    lên** một kênh người dùng tưởng đã ngắt — đúng thứ mà FR-011 của tính năng
    đăng video cấm. Phương án "để tới giờ rồi báo lỗi" không đảm bảo được vì hệ
    thống có thể đang tắt vào đúng thời điểm đó, không có ai chặn kịp.
- Q: Thời điểm hẹn phải cách hiện tại tối thiểu bao lâu? → A: **Tối thiểu 15
  phút** kể từ lúc đặt lịch.
  - Lý do: video được tải lên dịch vụ trung gian ngay tại thời điểm đặt lịch,
    file vài chục MB có thể mất một lúc — hẹn quá sát thì upload xong đã trôi
    qua mất giờ đăng. 15 phút là biên an toàn kể cả với video nặng và mạng chậm,
    mà không cản trở nhu cầu thật (cần đăng gấp thì đã có "đăng ngay").

## Assumptions

- Việc chờ đến giờ và thực hiện đăng do **dịch vụ trung gian** đảm nhiệm, không
  phải hệ thống này — đó chính là lý do máy người dùng không cần chạy. Hệ thống
  này chỉ đẩy yêu cầu kèm thời điểm sang, rồi đối soát lại trạng thái về sau.
- Múi giờ mặc định là múi giờ Việt Nam (UTC+7) vì đây là công cụ cho một người
  dùng duy nhất; không hỗ trợ chọn múi giờ khác ở bản đầu.
- **Đổi giờ** của một bài đã hẹn không thuộc phạm vi bản đầu — người dùng huỷ bài
  cũ rồi đặt lịch mới, vì kết quả tương đương mà không cần thêm luồng riêng.
- Mỗi lượt hẹn giờ vẫn chỉ nhắm tới 1 nền tảng và 1 kênh, giống hệt luồng đăng
  ngay hiện có.
- Nếu một video đã có bài đang chờ đăng lên một kênh, hệ thống chặn đặt thêm lịch
  cho đúng video + kênh đó — giữ nguyên tinh thần chống đăng trùng của tính năng
  đăng video, tránh vô tình xếp 2 bài giống nhau lên cùng kênh.
- Bài đã lên rồi thì không sửa/xoá được từ giao diện này (giống tính năng đăng
  ngay); huỷ chỉ có tác dụng trước giờ đăng.
- Hệ thống không gửi thông báo chủ động (email/push) khi bài hẹn giờ thất bại —
  người dùng biết khi mở lại giao diện.

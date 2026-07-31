# Feature Specification: Chế độ quản lý pipeline (dừng chờ duyệt từng bước)

**Feature Branch**: `008-supervised-pipeline`

**Created**: 2026-07-30

**Status**: Draft

**Input**: User description: "cho tôi thêm 1 option (quản lý pipeline), khi bật quản lý thì ở mỗi quy trình sẽ dừng lại để tôi review và sau đó phê duyệt qua bước tiếp theo, ví dụ dừng ở bước tách lời tôi có thể review và tinh chỉnh trước khi qua các bước sau"

## Clarifications

### Session 2026-07-30 (chốt trước khi viết spec)

- Q: Bật chế độ quản lý thì dừng chờ duyệt ở những bước nào? → A: **Đúng 2
  bước có nội dung text sửa được**: sau bước tách lời và sau bước sinh kịch
  bản. KHÔNG đặt chốt ở tải video, đọc giọng, ghép video. Lý do: đây là 2 chỗ
  sai sẽ lan xuống toàn bộ các bước phía sau, và là nội dung duy nhất "tinh
  chỉnh" được một cách có ý nghĩa. Dừng ở bước ghép gần như vô nghĩa (ghép
  xong là đã có sản phẩm cuối), còn video gốc đã tải thì xem được sẵn ở tab
  lịch sử.
- Q: Ở mỗi chốt, người dùng sửa nội dung bằng cách nào? → A: **Sửa trực tiếp
  trên giao diện web** — xem bảng các câu (mốc thời gian + nội dung), sửa
  ngay trong trình duyệt, lưu, rồi bấm phê duyệt. KHÔNG bắt người dùng mở
  file trung gian bằng editor ngoài rồi quay lại bấm duyệt.
- Q: Job đang dừng chờ duyệt có chiếm suất "1 job tại một thời điểm" không?
  → A: **Không chiếm**. Job chờ duyệt không tốn tài nguyên xử lý, nên phải
  nhả suất để người dùng submit được job mới. Đổi lại, nếu lúc bấm phê duyệt
  đang có job khác thực sự xử lý thì yêu cầu phê duyệt bị từ chối kèm thông
  báo rõ ràng, người dùng chờ rồi bấm lại.
- Q: Mốc thời gian từng câu có sửa được ở v1 không? → A: **Chỉ để xem
  (read-only)**, người dùng chỉ sửa nội dung chữ (FR-016). Lý do: gần như toàn
  bộ nhu cầu review là sửa tên riêng, thuật ngữ, từ nghe nhầm, câu dịch chưa
  mượt — đều là chữ. Cho sửa mốc thời gian thì phải thêm kiểm tra thứ tự các
  câu, chống chồng lấn, chặn vượt thời lượng video, cùng cách xử lý khi mốc
  sai; đổi lấy giá trị chưa rõ ràng. Vẫn xoá được câu rác bằng cách xoá trắng
  nội dung (FR-013), nên không mất khả năng dọn kết quả ASR bị nhiễu.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Duyệt và tinh chỉnh lời thoại đã tách trước khi xử lý tiếp (Priority: P1)

Người dùng tạo job có bật chế độ quản lý. Hệ thống tải video, tách lời, rồi
**dừng lại** và báo là đang chờ duyệt. Người dùng mở job đó lên, thấy bảng
từng câu đã tách kèm mốc thời gian, sửa lại những câu bị nghe sai (tên riêng,
thuật ngữ, câu bị nghe nhầm thành từ khác), lưu, rồi bấm phê duyệt. Hệ thống
chạy tiếp các bước sau **dựa trên nội dung đã sửa**.

**Why this priority**: Đây là chốt đắt giá nhất. Bước tách lời là đầu vào của
mọi bước sau — một câu nghe sai ở đây kéo theo bản dịch sai, giọng đọc sai, và
sản phẩm cuối sai; người dùng chỉ phát hiện ra khi đã tốn toàn bộ thời gian
dịch + đọc + ghép, rồi phải làm lại từ đầu. Chặn được ở đây là tự nó đã đủ giá
trị, không cần chốt thứ hai.

**Independent Test**: Tạo 1 job bật chế độ quản lý, xác nhận job dừng sau bước
tách lời và **không tự chạy tiếp**; sửa nội dung 1 câu, phê duyệt, rồi kiểm tra
nội dung đã sửa xuất hiện ở sản phẩm cuối. Kể cả khi chốt thứ hai (kịch bản)
chưa được làm, luồng này vẫn dùng được trọn vẹn.

**Acceptance Scenarios**:

1. **Given** một job bật chế độ quản lý vừa tách lời xong, **When** hệ thống
   hoàn thành bước tách lời, **Then** job chuyển sang trạng thái chờ duyệt tại
   chốt lời thoại và không bắt đầu bước sinh kịch bản.
2. **Given** một job đang chờ duyệt tại chốt lời thoại, **When** người dùng mở
   trang chi tiết job, **Then** người dùng thấy toàn bộ các câu đã tách kèm mốc
   thời gian, ở dạng sửa được, cùng nút phê duyệt.
3. **Given** người dùng đã sửa nội dung một câu và lưu lại, **When** người dùng
   bấm phê duyệt, **Then** hệ thống chạy tiếp từ bước sinh kịch bản và các bước
   sau dùng đúng nội dung đã sửa, không dùng nội dung gốc.
4. **Given** một job đang chờ duyệt tại chốt lời thoại, **When** để nguyên
   không làm gì trong thời gian dài (kể cả tắt rồi mở lại hệ thống), **Then**
   job vẫn ở trạng thái chờ duyệt, không tự chạy tiếp và không bị coi là lỗi.
5. **Given** một job KHÔNG bật chế độ quản lý, **When** hệ thống tách lời xong,
   **Then** job chạy tiếp ngay như hiện nay, không dừng và không cần phê duyệt.

---

### User Story 2 - Duyệt và tinh chỉnh kịch bản trước khi đọc giọng và ghép (Priority: P2)

Sau khi duyệt chốt lời thoại, hệ thống sinh kịch bản (bản dịch hoặc bản viết
lại) rồi **dừng lại lần thứ hai**. Người dùng xem từng câu của kịch bản đặt
cạnh câu gốc tương ứng, sửa lại chỗ dịch chưa mượt hoặc chưa đúng ngữ cảnh,
lưu, rồi phê duyệt. Hệ thống chạy tiếp đọc giọng và ghép video.

**Why this priority**: Đây là chốt cuối cùng còn sửa được bằng chữ. Sau chốt
này mọi thứ đã thành âm thanh và hình ảnh — muốn sửa một câu dịch thì phải đọc
lại và ghép lại toàn bộ. Xếp sau US1 vì US1 chặn được lỗi gốc rễ, còn US2 chặn
lỗi tầng dịch; hệ thống vẫn dùng được nếu chỉ có US1.

**Independent Test**: Với một job bật chế độ quản lý đã qua chốt lời thoại (hoặc
job có chốt lời thoại đã duyệt sẵn), xác nhận job dừng lần hai sau bước sinh
kịch bản; sửa một câu dịch, phê duyệt, kiểm tra giọng đọc/phụ đề ở sản phẩm cuối
khớp với nội dung đã sửa.

**Acceptance Scenarios**:

1. **Given** một job bật chế độ quản lý đã duyệt chốt lời thoại, **When** hệ
   thống sinh kịch bản xong, **Then** job chuyển sang chờ duyệt tại chốt kịch
   bản và không bắt đầu bước đọc giọng.
2. **Given** một job đang chờ duyệt tại chốt kịch bản, **When** người dùng mở
   trang chi tiết job, **Then** mỗi câu kịch bản hiện kèm câu gốc tương ứng để
   đối chiếu, và nội dung kịch bản sửa được.
3. **Given** người dùng đã sửa một câu kịch bản và lưu, **When** người dùng bấm
   phê duyệt, **Then** giọng đọc (hoặc phụ đề, tuỳ chế độ xử lý) ở sản phẩm cuối
   khớp với nội dung đã sửa.
4. **Given** một job ở chế độ chỉ thêm phụ đề (không lồng tiếng), **When** job
   bật chế độ quản lý, **Then** cả hai chốt vẫn áp dụng — vì nội dung phụ đề
   chính là kịch bản đã sinh.

---

### User Story 3 - Làm việc khác trong lúc job đang chờ duyệt (Priority: P2)

Người dùng để một job dừng ở chốt chờ duyệt (chưa kịp review), nhưng vẫn muốn
submit job mới cho video khác. Hệ thống cho phép, vì job đang chờ duyệt không
thực sự chiếm tài nguyên xử lý.

**Why this priority**: Không có phần này, chế độ quản lý biến thành cái bẫy —
một job chờ duyệt bỏ đó vài tiếng sẽ chặn toàn bộ hệ thống, khiến tính năng
"an toàn hơn" lại trở thành tính năng không ai dám bật. Xếp P2 vì US1 vẫn
dùng được không cần nó (chỉ là bất tiện).

**Independent Test**: Để 1 job ở trạng thái chờ duyệt, submit job thứ hai và
xác nhận job thứ hai chạy được; sau đó bấm phê duyệt job thứ nhất trong lúc job
thứ hai còn đang xử lý và xác nhận hệ thống từ chối kèm thông báo rõ ràng chứ
không chạy chồng hai job.

**Acceptance Scenarios**:

1. **Given** job A đang chờ duyệt tại một chốt, **When** người dùng submit job
   B mới, **Then** job B được nhận và bắt đầu xử lý bình thường.
2. **Given** job A đang chờ duyệt và job B đang thực sự xử lý, **When** người
   dùng bấm phê duyệt job A, **Then** hệ thống từ chối kèm thông báo nói rõ
   đang có job khác xử lý và mời thử lại sau, đồng thời job A vẫn giữ nguyên
   trạng thái chờ duyệt (không bị mất nội dung đã sửa, không bị đánh dấu lỗi).
3. **Given** job A đang chờ duyệt và không có job nào khác xử lý, **When** người
   dùng bấm phê duyệt, **Then** job A chạy tiếp ngay.

---

### User Story 4 - Sinh lại kịch bản khi bản dịch không dùng được (Priority: P3)

Ở chốt kịch bản, người dùng thấy cả bản dịch sai lệch quá nhiều để sửa tay từng
câu. Thay vì phê duyệt hoặc sửa thủ công cả chục câu, người dùng bấm "sinh lại
kịch bản" để hệ thống dịch lại từ đầu (dựa trên lời thoại đã duyệt), rồi lại
dừng ở chính chốt đó để review bản mới.

**Why this priority**: Chỉ là đường tắt cho một tình huống ít gặp — mọi thứ nó
làm được thì người dùng vẫn làm được bằng cách sửa tay hoặc xoá job chạy lại.
Có thể lược bỏ mà không ảnh hưởng giá trị cốt lõi của tính năng.

**Independent Test**: Ở một job đang chờ duyệt tại chốt kịch bản, bấm sinh lại
và xác nhận kịch bản có nội dung mới, job vẫn dừng tại đúng chốt đó chờ duyệt,
và lời thoại đã duyệt trước đó không bị thay đổi.

**Acceptance Scenarios**:

1. **Given** một job đang chờ duyệt tại chốt kịch bản, **When** người dùng bấm
   sinh lại kịch bản, **Then** hệ thống sinh kịch bản mới từ lời thoại đã duyệt
   và job quay lại trạng thái chờ duyệt tại chốt kịch bản.
2. **Given** người dùng đã sửa tay vài câu kịch bản rồi bấm sinh lại, **When**
   kịch bản mới được sinh, **Then** hệ thống cảnh báo trước rằng các sửa tay ở
   chốt này sẽ bị ghi đè, và chỉ sinh lại sau khi người dùng xác nhận.

---

### Edge Cases

- **Bật chế độ quản lý cho chế độ "chỉ tải video"**: chế độ đó không có bước
  tách lời lẫn sinh kịch bản, nên không có chốt nào để dừng — job phải chạy và
  kết thúc như bình thường, không được treo mãi ở trạng thái chờ duyệt.
- **Hệ thống tắt/khởi động lại khi job đang chờ duyệt**: trạng thái chờ duyệt
  phải sống sót; sau khi mở lại, job vẫn hiện đang chờ duyệt tại đúng chốt cũ
  cùng nội dung đã sửa (nếu có).
- **Bước tách lời không ra câu nào** (video không có lời thoại): chốt vẫn dừng
  nhưng hiển thị rõ là không có câu nào, để người dùng quyết định phê duyệt
  (chạy tiếp và chấp nhận sản phẩm không lời) hay dừng hẳn — không được lặng lẽ
  chạy tiếp cũng không được báo lỗi.
- **Người dùng xoá trắng nội dung một câu**: hiểu là "bỏ câu này", các bước sau
  bỏ qua nó (đây cũng là cách dọn câu rác do ASR nghe tạp âm thành từ). Nhưng
  nếu xoá trắng HẾT mọi câu thì phải từ chối lưu kèm lý do, vì không còn gì để
  xử lý ở các bước sau.
- **Job lỗi ở một bước SAU chốt đã duyệt** (vd đọc giọng lỗi): cơ chế thử lại
  hiện có phải chạy tiếp từ bước lỗi, KHÔNG được bắt người dùng duyệt lại các
  chốt đã duyệt trước đó.
- **Người dùng bấm phê duyệt hai lần liên tiếp** (nhấn đúp, hoặc mở 2 tab):
  chỉ được chạy tiếp một lần, lần thứ hai bị từ chối vô hại chứ không tạo ra
  hai lượt xử lý song song cùng job.
- **Người dùng sửa nội dung nhưng chưa lưu rồi bấm phê duyệt**: hệ thống duyệt
  theo nội dung đã lưu; nếu còn thay đổi chưa lưu, phải cảnh báo trước thay vì
  âm thầm bỏ mất phần sửa.
- **Xoá job đang chờ duyệt**: phải xoá được (job không thực sự đang xử lý), như
  job ở trạng thái chờ/xong/lỗi hiện nay.

## Requirements *(mandatory)*

### Functional Requirements

**Bật/tắt chế độ**

- **FR-001**: Người dùng MUST bật/tắt được chế độ quản lý pipeline khi tạo job
  mới, ngay trên giao diện tạo job.
- **FR-002**: Chế độ quản lý MUST mặc định TẮT. Job không bật chế độ này, và
  mọi job đã tạo từ trước, MUST chạy liền mạch đúng như hành vi hiện tại —
  không dừng, không cần phê duyệt.
- **FR-003**: Trạng thái bật/tắt chế độ quản lý của một job MUST được ghi lại
  cùng job và giữ nguyên qua các lượt chạy tiếp/thử lại của chính job đó.

**Dừng tại chốt**

- **FR-004**: Với job bật chế độ quản lý, hệ thống MUST dừng sau khi hoàn thành
  bước tách lời và sau khi hoàn thành bước sinh kịch bản — đúng 2 chốt, không
  dừng ở các bước khác.
- **FR-005**: Khi dừng tại một chốt, hệ thống MUST NOT bắt đầu bất kỳ bước tiếp
  theo nào cho tới khi có phê duyệt tường minh của người dùng, kể cả sau thời
  gian chờ dài hoặc sau khi hệ thống được khởi động lại.
- **FR-006**: Job đang chờ duyệt MUST được phân biệt rõ ràng với job đang xử lý
  và với job lỗi, ở cả danh sách job và trang chi tiết job — nêu rõ đang chờ
  duyệt tại chốt nào.
- **FR-007**: Trạng thái chờ duyệt MUST tồn tại bền vững (sống sót qua việc
  tắt/khởi động lại hệ thống).
- **FR-008**: Với chế độ xử lý không đi qua bước tách lời và sinh kịch bản (chế
  độ chỉ tải video), hệ thống MUST bỏ qua toàn bộ cơ chế chốt và kết thúc job
  bình thường dù chế độ quản lý có bật.

**Review và sửa nội dung**

- **FR-009**: Ở chốt lời thoại, người dùng MUST xem được toàn bộ các câu đã
  tách kèm mốc thời gian từng câu, và sửa được nội dung từng câu ngay trên giao
  diện web.
- **FR-010**: Ở chốt kịch bản, người dùng MUST xem được từng câu kịch bản kèm
  câu gốc tương ứng để đối chiếu, và sửa được nội dung kịch bản ngay trên giao
  diện web.
- **FR-011**: Người dùng MUST lưu được phần sửa mà không cần phê duyệt ngay
  (lưu nháp rồi quay lại sau).
- **FR-012**: Nội dung đã lưu ở một chốt MUST là nội dung mà các bước sau dùng
  — hệ thống MUST NOT dùng lại nội dung gốc trước khi sửa.
- **FR-013**: Xoá trắng nội dung một câu MUST được hiểu là "bỏ câu đó" (các
  bước sau bỏ qua câu này), KHÔNG phải một câu rỗng đưa xuống bước sau.
- **FR-014**: Hệ thống MUST từ chối lưu khi toàn bộ các câu đều rỗng, kèm lý do
  rõ ràng — thay vì để bước sau lỗi với thông điệp khó hiểu.
- **FR-015**: Nếu người dùng bấm phê duyệt khi vẫn còn thay đổi chưa lưu trên
  giao diện, hệ thống MUST cảnh báo trước, không âm thầm bỏ mất phần sửa.
- **FR-016**: Mốc thời gian từng câu MUST chỉ để xem, không sửa được ở v1. Hệ
  thống MUST hiển thị mốc đó để người dùng định vị câu đang sửa nằm ở đoạn nào
  của video.

**Phê duyệt và chạy tiếp**

- **FR-017**: Người dùng MUST phê duyệt được một chốt bằng một hành động tường
  minh trên giao diện web, sau đó hệ thống chạy tiếp tới chốt kế tiếp (hoặc tới
  khi hoàn thành nếu không còn chốt nào).
- **FR-018**: Nếu tại thời điểm phê duyệt đang có job khác thực sự xử lý, hệ
  thống MUST từ chối lượt phê duyệt kèm thông báo nêu rõ nguyên nhân, và MUST
  giữ nguyên trạng thái chờ duyệt cùng toàn bộ nội dung đã sửa của job đó.
- **FR-019**: Hai lượt phê duyệt liên tiếp cho cùng một chốt MUST chỉ dẫn tới
  một lượt chạy tiếp; lượt sau MUST bị từ chối vô hại, không tạo ra hai lượt xử
  lý song song trên cùng job.
- **FR-020**: Ở chốt kịch bản, người dùng MUST có thể yêu cầu sinh lại kịch bản
  từ lời thoại đã duyệt; sau khi sinh lại, job MUST quay về chờ duyệt tại chính
  chốt đó, và hệ thống MUST cảnh báo trước rằng phần sửa tay ở chốt này sẽ bị
  ghi đè.

**Không chiếm suất xử lý**

- **FR-021**: Job đang chờ duyệt MUST NOT bị tính là job đang xử lý — người
  dùng vẫn submit được job mới trong lúc có job chờ duyệt.
- **FR-022**: Job đang chờ duyệt MUST xoá được như job ở trạng thái chờ/xong/lỗi
  hiện nay.
- **FR-023**: Cơ chế thử lại job lỗi hiện có MUST chạy tiếp từ bước bị lỗi mà
  KHÔNG bắt người dùng duyệt lại các chốt đã duyệt trước đó.

### Key Entities *(include if data involved)*

- **Job (mở rộng)**: bổ sung thông tin "có bật chế độ quản lý hay không" và
  "đang chờ duyệt tại chốt nào (nếu có)". Mọi thông tin khác giữ nguyên.
- **Chốt kiểm duyệt (Review Gate)**: một điểm dừng gắn với một bước pipeline
  (lời thoại hoặc kịch bản). Thuộc tính: bước tương ứng, thời điểm dừng, thời
  điểm được duyệt, nội dung đưa ra review.
- **Câu sửa được (Editable Segment)**: một dòng nội dung ở chốt — mốc bắt đầu,
  mốc kết thúc (chỉ để xem), nội dung hiện tại (sửa được), và (ở chốt kịch bản)
  câu gốc tương ứng để đối chiếu.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% job không bật chế độ quản lý (bao gồm mọi job đã tạo từ
  trước) chạy ra kết quả và trải qua đúng các trạng thái như trước khi có tính
  năng này — không thêm một điểm dừng nào.
- **SC-002**: Job bật chế độ quản lý dừng đúng 2 lần trong một lượt chạy đầy đủ,
  và sau 30 phút không có phê duyệt vẫn đang ở trạng thái chờ duyệt (không tự
  chạy tiếp, không bị đánh dấu lỗi).
- **SC-003**: Nội dung người dùng sửa ở chốt lời thoại xuất hiện nguyên vẹn ở
  kịch bản và ở sản phẩm cuối (giọng đọc hoặc phụ đề) trong 100% lượt thử.
- **SC-004**: Người dùng hoàn tất review + sửa + phê duyệt một chốt trong dưới
  2 phút mà không cần rời giao diện web (không mở terminal, không sửa file
  thủ công).
- **SC-005**: Trong lúc có job chờ duyệt, submit job mới thành công trong 100%
  lượt thử.
- **SC-006**: Khởi động lại hệ thống khi đang có job chờ duyệt: sau khi mở lại,
  job vẫn ở đúng chốt cũ với đúng nội dung đã lưu, trong 100% lượt thử.
- **SC-007**: Với video có lời thoại bị nghe sai (tên riêng/thuật ngữ), người
  dùng sửa được ở chốt lời thoại và ra sản phẩm đúng ngay lượt chạy đầu tiên —
  không phải xoá job chạy lại từ đầu.

## Assumptions

- **Một công tắc cho cả hai chốt**: bật chế độ quản lý là bật cả 2 chốt. Không
  làm tuỳ chọn bật riêng từng chốt ở v1 — người dùng đã diễn đạt là "ở mỗi quy
  trình sẽ dừng lại", và 2 công tắc riêng làm giao diện tạo job rối thêm mà giá
  trị tăng không rõ ràng.
- **Chỉ chọn lúc tạo job**: không hỗ trợ bật/tắt chế độ quản lý cho job đang
  chạy. Muốn đổi thì tạo job mới.
- **Chờ duyệt là vô hạn**: job chờ duyệt không tự hết hạn, không tự chạy tiếp,
  không tự bị đánh dấu lỗi sau bao lâu đi nữa. An toàn vì nó đã không chiếm
  suất xử lý (FR-021).
- **Chế độ phụ đề vẫn đủ 2 chốt**: chế độ chỉ thêm phụ đề đi qua cả bước tách
  lời lẫn bước sinh kịch bản (kịch bản chính là nội dung phụ đề), nên cả 2 chốt
  đều có ý nghĩa và đều áp dụng.
- **Không có "duyệt hết một lần"**: v1 không làm nút bỏ qua toàn bộ các chốt còn
  lại. Người dùng muốn chạy liền mạch thì tắt chế độ quản lý từ đầu.
- **Một người dùng duy nhất**: hệ thống này phục vụ một người dùng (đã có đăng
  nhập ở tính năng web UI), nên không cần phân quyền "ai được duyệt", không cần
  luồng duyệt nhiều người, không cần lịch sử ai duyệt cái gì.
- **Không thông báo chủ động**: người dùng biết job đang chờ duyệt qua danh sách
  job/trang chi tiết khi họ mở giao diện web. Không gửi email/thông báo đẩy.
- **Tái dùng cơ chế sẵn có**: tính năng này dựa trên việc pipeline đã lưu trạng
  thái từng job ra file trung gian và đã chạy tiếp được từ bước dở dang; không
  cần thêm hạ tầng hàng đợi hay tiến trình nền mới.

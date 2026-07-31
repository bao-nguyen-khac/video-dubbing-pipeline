# Feature Specification: Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí

**Feature Branch**: `009-hardsub-blur-reposition`

**Created**: 2026-07-30

**Status**: Draft

**Input**: User description: "Làm mờ phụ đề gốc (hardsub) và chèn phụ đề mới đúng vị trí — với video nguồn đã có phụ đề gốc (tiếng Anh) burn cứng vào hình, hệ thống làm mờ đúng vùng chữ gốc đó và chèn phụ đề mới (nội dung đã dịch) đè lên đúng vị trí, cỡ chữ nhỏ hơn cỡ mặc định hiện tại. Mặc định coi cả video là CÓ phụ đề gốc (nên mờ + chèn đè); người dùng khai báo các khoảng thời gian KHÔNG có phụ đề gốc (dùng đúng định dạng chuỗi khoảng như ô \"Giữ nguyên audio gốc\" hiện có, VD \"0:00-0:08, 0:15-end\", nhưng là field riêng, ý nghĩa khác — không tái dùng chung giá trị với \"Giữ nguyên audio gốc\"); trong các khoảng đó KHÔNG mờ gì cả, phụ đề mới vẫn chèn bình thường theo vị trí/cỡ chữ mặc định hiện có. Để xác định vị trí (toạ độ) của phụ đề gốc: dùng OCR (ưu tiên Tesseract, CPU thuần, không cần GPU) chạy trên 1 khung hình đại diện cho mỗi đoạn được coi là có phụ đề gốc — không quét liên tục toàn video, nên chi phí tỉ lệ với số đoạn chứ không phải độ dài video. Xử lý: áp boxblur (ffmpeg) đúng vùng toạ độ dò được, chỉ kích hoạt trong đúng khoảng thời gian có phụ đề gốc; rồi chèn phụ đề mới đè lên đúng vị trí đó."

## Clarifications

### Session 2026-07-30

- Q: Khi phát hiện tự động tìm SAI vị trí phụ đề gốc (khác với "không tìm thấy"
  đã có ở US3), hệ thống nên xử lý thế nào? → A: **Nếu job bật "Quản lý
  pipeline"** (008-supervised-pipeline), người dùng review được vùng phụ đề gốc
  đã dò được ngay tại chốt chờ duyệt sau bước tách lời, và có thể đánh dấu lại
  một đoạn dò sai thành "không có phụ đề gốc" trước khi phê duyệt chạy tiếp.
  Nếu KHÔNG bật Quản lý pipeline, việc xác định vị trí vẫn hoàn toàn tự động
  (không có bước xem trước) — giữ nguyên lưới an toàn tự động ở FR-008.
- Q: Một khung hình có thể có nhiều dòng chữ khác kiểu nhau (VD dòng tiêu đề mô
  tả bối cảnh có nền hộp riêng, cạnh dòng phụ đề khớp lời nói không có nền) —
  hệ thống nên xử lý dòng nào? → A: Chỉ coi dòng chữ **KHÔNG có nền hộp đặc**
  (background box riêng) là phụ đề gốc cần mờ + thay; dòng chữ nào có nền hộp
  riêng (kiểu tiêu đề/mô tả bối cảnh) thì bỏ qua hoàn toàn, không mờ không đè.
  Phân biệt theo hình dạng (có/không nền hộp), không theo màu chữ cụ thể — để
  áp dụng được cho nhiều video có màu phụ đề khác nhau, không chỉ riêng vàng.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Video có phụ đề gốc suốt toàn bộ thời lượng (Priority: P1)

Người dùng bật tính năng cho một video có phụ đề gốc (tiếng Anh) burn cứng suốt
từ đầu tới cuối, không khai báo ngoại lệ nào. Hệ thống tự động che mờ đúng vùng
chữ gốc và chèn phụ đề mới (nội dung đã dịch) ngay tại vị trí đó, cỡ chữ nhỏ hơn
mặc định để không tràn ra ngoài vùng đã che.

**Why this priority**: Đây là giá trị cốt lõi của tính năng — video ra sản phẩm
"sạch", không lộ 2 lớp phụ đề chồng lên nhau (rất mất thẩm mỹ, gây khó chịu cho
người xem và làm sản phẩm trông rõ ràng là dựng lại từ video khác).

**Independent Test**: Bật tính năng cho 1 job không khai báo khoảng ngoại lệ
nào; xác nhận suốt toàn bộ video ở sản phẩm cuối, vùng phụ đề gốc bị che mờ và
phụ đề mới hiển thị đúng tại vị trí đó.

**Acceptance Scenarios**:

1. **Given** video có phụ đề gốc từ đầu tới cuối, **When** người dùng bật tính
   năng và không khai báo khoảng ngoại lệ nào, **Then** toàn bộ video ở sản
   phẩm cuối có vùng phụ đề gốc bị che mờ và phụ đề mới hiển thị đúng vị trí đó.
2. **Given** tính năng đang bật, **When** hệ thống xử lý xong, **Then** phụ đề
   mới đọc được rõ ràng trên nền đã làm mờ, không bị chữ gốc đè lên hay lộ ra.
3. **Given** khung hình có cả dòng tiêu đề nền hộp (mô tả bối cảnh) và dòng phụ
   đề không nền (khớp lời nói) cùng lúc, **When** hệ thống xử lý, **Then** chỉ
   dòng không nền bị mờ + thay; dòng tiêu đề nền hộp giữ nguyên không bị chạm
   tới.

---

### User Story 2 - Khai báo đoạn không có phụ đề gốc (Priority: P2)

Người dùng biết trước một đoạn của video (VD phần mở đầu, đoạn b-roll) không có
phụ đề gốc burn sẵn. Họ khai báo đoạn đó khi tạo job để hệ thống bỏ qua việc làm
mờ ở đúng đoạn này; phụ đề mới vẫn hiển thị bình thường theo vị trí/cỡ chữ mặc
định hiện có.

**Why this priority**: Tránh làm mờ nhầm phần hình ảnh không có chữ để che — rất
phản cảm nếu xảy ra — và giữ tính năng an toàn để dùng trên các video có nội
dung hỗn hợp (đoạn có phụ đề gốc xen đoạn không có).

**Independent Test**: Bật tính năng, khai báo một khoảng là "không có phụ đề
gốc"; xác nhận đúng đoạn đó ở sản phẩm cuối không bị mờ, các đoạn còn lại vẫn
mờ + chèn đúng vị trí như User Story 1.

**Acceptance Scenarios**:

1. **Given** tính năng bật và người dùng khai báo khoảng X là không có phụ đề
   gốc, **When** job hoàn tất, **Then** đoạn X trong sản phẩm cuối không có
   vùng mờ nào, phụ đề mới hiển thị theo vị trí/cỡ chữ mặc định hiện có.
2. **Given** ngoài khoảng đã khai báo, **When** kiểm tra sản phẩm cuối, **Then**
   vùng phụ đề gốc vẫn bị mờ và phụ đề mới vẫn đúng vị trí như hành vi mặc định
   (User Story 1).
3. **Given** người dùng khai báo khoảng sai định dạng hoặc chồng lấn, **When**
   hệ thống xử lý, **Then** phần khai báo sai bị bỏ qua, không làm hỏng job —
   phần hợp lệ vẫn được áp dụng bình thường.

---

### User Story 3 - Không xác định được vị trí phụ đề gốc ở một đoạn (Priority: P3)

Ở một đoạn mặc định được coi là "có phụ đề gốc" (người dùng không khai báo ngoại
lệ), hệ thống không tìm được vị trí chữ rõ ràng — VD do khung hình đại diện
tình cờ rơi đúng lúc phụ đề chưa xuất hiện. Hệ thống phải xử lý an toàn: không
mờ sai chỗ, không làm hỏng job, và ghi nhận rõ để người dùng biết.

**Why this priority**: Tình huống ít gặp nhưng nếu không xử lý sẽ làm hỏng cả
job hoặc mờ sai vị trí — bảo vệ tính ổn định của tính năng. Không có phần này
tính năng vẫn dùng được cho trường hợp phổ biến (US1/US2), chỉ kém an toàn hơn
ở trường hợp biên.

**Independent Test**: Giả lập một đoạn mặc định "có phụ đề gốc" nhưng khung đại
diện không có chữ; xác nhận job vẫn hoàn tất bình thường, đoạn đó không bị mờ
sai chỗ, và có cảnh báo được ghi nhận.

**Acceptance Scenarios**:

1. **Given** hệ thống không xác định được vị trí phụ đề gốc ở một đoạn mặc
   định là có, **When** job chạy tới bước này, **Then** hệ thống bỏ qua việc
   làm mờ ở đúng đoạn đó và tiếp tục các bước sau bình thường, không lỗi job.
2. **Given** tình huống ở kịch bản 1, **When** người dùng xem lại kết quả,
   **Then** có cảnh báo rõ ràng ghi nhận đoạn nào không xác định được vị trí,
   để họ tự khai báo lại là "không có phụ đề gốc" ở lượt sau nếu muốn.

---

### User Story 4 - Review vị trí phụ đề gốc khi bật Quản lý pipeline (Priority: P2)

Với job bật đồng thời "Quản lý pipeline" (008-supervised-pipeline — dừng chờ
duyệt từng bước), người dùng thấy trước các vùng phụ đề gốc đã dò được (và các
đoạn không dò được) ngay tại chốt chờ duyệt sau bước tách lời, cùng lúc với
việc review nội dung lời thoại. Họ có thể đánh dấu lại một đoạn là "không có
phụ đề gốc" nếu vùng dò sai, trước khi phê duyệt chạy tiếp.

**Why this priority**: Việc xác định vị trí là tự động (không có gì đảm bảo
đúng 100%), nên có rủi ro dò sai mà US3 (không tìm thấy) không bao phủ được —
đó là trường hợp dò được NHƯNG SAI. Người dùng đã đầu tư bật Quản lý pipeline
để bắt lỗi sớm thì cũng cần bắt được lỗi loại này ở cùng một chỗ, không phải
đợi xem xong sản phẩm cuối mới biết bị mờ nhầm. Xếp P2 vì tính năng vẫn dùng
được đầy đủ mà không cần Quản lý pipeline (P1 tự động + cảnh báo qua FR-008).

**Independent Test**: Bật cả hai tính năng (Quản lý pipeline + Làm mờ phụ đề
gốc); ở chốt lời thoại, xác nhận thấy được vùng phụ đề gốc đã dò được cho từng
đoạn; đánh dấu lại 1 đoạn dò sai thành "không có phụ đề gốc"; phê duyệt; xác
nhận đoạn đó không bị mờ ở sản phẩm cuối.

**Acceptance Scenarios**:

1. **Given** job bật cả Quản lý pipeline và tính năng làm mờ phụ đề gốc,
   **When** hệ thống hoàn thành bước tách lời, **Then** chốt chờ duyệt hiển thị
   kèm vùng phụ đề gốc đã dò được cho từng đoạn (hoặc thông báo "không dò được"
   nếu có), cùng lúc với nội dung lời thoại để review.
2. **Given** người dùng thấy một vùng dò sai, **When** họ đánh dấu lại đoạn đó
   là "không có phụ đề gốc" và phê duyệt, **Then** sản phẩm cuối không mờ đoạn
   đó, phụ đề mới hiển thị theo vị trí/cỡ chữ mặc định ở đúng đoạn đó.
3. **Given** job KHÔNG bật Quản lý pipeline, **When** hệ thống xử lý, **Then**
   không có bước xem trước nào — vị trí dò được áp dụng tự động theo FR-006 và
   FR-008, không chặn job lại để chờ duyệt.

---

### Edge Cases

- **Chế độ xử lý không hiển thị phụ đề nào** (VD chỉ tải video, hoặc lồng tiếng
  không bật phụ đề động): tính năng không có phụ đề nào để chèn, nên bị bỏ qua
  hoàn toàn dù có bật.
- **Video hoàn toàn không có phụ đề gốc** (mặc định coi là "có" toàn bộ, người
  dùng không khai báo gì): mọi đoạn đều rơi vào tình huống User Story 3 — không
  đoạn nào bị mờ, phụ đề mới hiển thị mặc định toàn video, kết quả tương đương
  như tắt tính năng.
- **Phụ đề gốc đổi vị trí nhiều lần trong cùng một đoạn liên tục** không có
  khai báo ngắt quãng: hệ thống chỉ lấy một vị trí đại diện cho cả đoạn đó (xem
  Assumptions).
- **Khoảng khai báo vượt quá thời lượng video, hoặc chồng lấn nhau**: tự động
  giới hạn trong thời lượng thật, không báo lỗi cứng — giống cách tính năng
  "Giữ nguyên audio gốc" đang xử lý.
- **Vùng phụ đề gốc nằm sát rìa khung hình**: vùng mờ và phụ đề mới vẫn phải
  nằm trong khung hình, không tràn ra ngoài.
- **Bật Làm mờ phụ đề gốc nhưng KHÔNG bật Quản lý pipeline**: không có bước xem
  trước nào — vị trí dò được (hoặc không dò được) áp dụng hoàn toàn tự động
  theo FR-006/FR-008, giống hệt hành vi trước khi có User Story 4.
- **Bật Quản lý pipeline nhưng KHÔNG bật Làm mờ phụ đề gốc**: chốt chờ duyệt sau
  bước tách lời hoạt động như hiện tại (008-supervised-pipeline), không có mục
  review vị trí phụ đề gốc nào xuất hiện thêm.
- **Khung hình có cả tiêu đề nền hộp lẫn phụ đề khớp lời nói không nền cùng lúc**
  (VD dòng mô tả bối cảnh nền trắng phía trên, dòng phụ đề không nền phía dưới):
  chỉ dòng KHÔNG có nền hộp bị coi là phụ đề gốc cần mờ + thay; dòng có nền hộp
  giữ nguyên, không bị chạm tới.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Người dùng MUST bật/tắt được tính năng "làm mờ phụ đề gốc và
  chèn phụ đề mới đúng vị trí" khi tạo job mới.
- **FR-002**: Tính năng MUST mặc định TẮT; job không bật tính năng này (kể cả
  job tạo trước khi có tính năng) MUST giữ nguyên hành vi phụ đề hiện tại.
- **FR-003**: Khi bật, hệ thống MUST mặc định coi toàn bộ thời lượng video là
  có phụ đề gốc, trừ các khoảng người dùng khai báo là không có.
- **FR-004**: Người dùng MUST khai báo được các khoảng thời gian không có phụ
  đề gốc ngay trên giao diện tạo job, theo cú pháp khoảng thời gian tương tự
  tính năng "Giữ nguyên audio gốc" đã có — nhưng là một cấu hình độc lập, không
  dùng chung giá trị với tính năng đó.
- **FR-005**: Ở các khoảng KHÔNG có phụ đề gốc (mặc định hoặc do người dùng
  khai báo), hệ thống MUST NOT áp dụng hiệu ứng làm mờ, và phụ đề mới (nếu có)
  MUST hiển thị theo đúng vị trí/kích cỡ mặc định hiện có.
- **FR-006**: Ở các khoảng CÓ phụ đề gốc, hệ thống MUST xác định vùng hiển thị
  của phụ đề gốc và áp dụng hiệu ứng làm mờ đúng vùng đó, chỉ trong đúng khoảng
  thời gian tương ứng.
- **FR-007**: Ở các khoảng CÓ phụ đề gốc, hệ thống MUST chèn phụ đề mới (nội
  dung đã dịch) đè lên đúng vùng đã xác định, với cỡ chữ nhỏ hơn cỡ mặc định
  hiện tại để không tràn ra ngoài vùng đã làm mờ.
- **FR-008**: Nếu hệ thống không xác định được vùng phụ đề gốc ở một khoảng
  được coi là có phụ đề gốc, hệ thống MUST xử lý an toàn — không làm mờ sai vị
  trí, không làm hỏng job — và ghi nhận cảnh báo rõ ràng cho khoảng đó.
- **FR-009**: Tính năng MUST chỉ áp dụng cho chế độ xử lý có sinh phụ đề hiển
  thị trên video (phụ đề tự động, hoặc lồng tiếng có bật phụ đề động); với chế
  độ không hiển thị phụ đề nào, tính năng MUST bị bỏ qua hoàn toàn dù có bật.
- **FR-010**: Hệ thống MUST bỏ qua phần khai báo khoảng sai định dạng thay vì
  làm hỏng job, tương tự cách tính năng "Giữ nguyên audio gốc" đang xử lý.
- **FR-011**: Trạng thái bật/tắt và các khoảng đã khai báo của tính năng MUST
  được ghi lại cùng job và giữ nguyên qua các lượt chạy tiếp/thử lại của chính
  job đó.
- **FR-012**: Khi job bật ĐỒNG THỜI cả tính năng này và "Quản lý pipeline"
  (008-supervised-pipeline), hệ thống MUST cho người dùng xem trước các vùng
  phụ đề gốc đã (hoặc chưa) xác định được, ngay tại chốt chờ duyệt sau bước
  tách lời — và cho phép đánh dấu lại một đoạn là "không có phụ đề gốc" nếu
  vùng dò được sai, trước khi phê duyệt chạy tiếp.
- **FR-013**: Khi job KHÔNG bật "Quản lý pipeline", việc xác định vị trí phụ đề
  gốc MUST vẫn hoàn toàn tự động như FR-006/FR-008 — không có bước xem
  trước/xác nhận nào chặn job lại.
- **FR-014**: Hệ thống MUST chỉ coi dòng chữ KHÔNG có nền hộp đặc (background
  box riêng) là phụ đề gốc cần xử lý; dòng chữ nào có nền hộp riêng (VD tiêu
  đề/mô tả bối cảnh) MUST được bỏ qua hoàn toàn — không mờ, không chèn đè lên
  đó — bất kể màu chữ.

### Key Entities *(include if feature involves data)*

- **Job (mở rộng)**: bổ sung thông tin "có bật làm mờ phụ đề gốc hay không" và
  "các khoảng thời gian không có phụ đề gốc". Mọi thông tin khác giữ nguyên.
- **Vùng phụ đề gốc (Original Caption Region)**: vùng hiển thị đã xác định được
  cho một đoạn liên tục có phụ đề gốc — vị trí/kích thước trong khung hình và
  khoảng thời gian áp dụng. Chỉ tính vùng chữ KHÔNG có nền hộp riêng (FR-014);
  dòng tiêu đề/mô tả bối cảnh có nền hộp không được coi là một Vùng phụ đề gốc.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với video có phụ đề gốc suốt toàn bộ thời lượng và không khai báo
  ngoại lệ, 100% thời lượng video ở sản phẩm cuối chỉ còn đúng một lớp phụ đề
  (phụ đề mới, đúng vị trí gốc) — không còn thấy phụ đề gốc lộ ra hay bị chồng
  hai lớp chữ.
- **SC-002**: Trong các khoảng người dùng khai báo là không có phụ đề gốc, 100%
  các khoảng đó không xuất hiện bất kỳ vùng mờ nào ở sản phẩm cuối.
- **SC-003**: Phụ đề mới ở các khoảng có phụ đề gốc luôn đọc được rõ ràng —
  không bị vùng mờ che khuất hay tràn ra ngoài — trong ít nhất 95% số lượt
  kiểm tra.
- **SC-004**: Người dùng cấu hình xong toàn bộ tính năng (bật + khai báo ngoại
  lệ nếu có) trong dưới 1 phút, ngay trên giao diện tạo job, không cần công cụ
  chỉnh sửa video riêng.
- **SC-005**: Thời gian xử lý thêm do tính năng gây ra tỉ lệ thuận với số đoạn
  có phụ đề gốc, không tỉ lệ với độ dài video — với video có tối đa 5 đoạn phụ
  đề gốc, thời gian xử lý thêm không vượt quá vài chục giây.
- **SC-006**: 100% job không bật tính năng này — bao gồm mọi job tạo từ trước —
  cho ra kết quả và trạng thái giống hệt như trước khi có tính năng.
- **SC-007**: Với job bật đồng thời Quản lý pipeline, người dùng phát hiện và
  sửa được một vùng phụ đề gốc dò sai ngay tại chốt chờ duyệt sau bước tách
  lời, trước khi xem sản phẩm cuối, trong 100% lượt thử.

## Assumptions

- **Vị trí ổn định trong một đoạn liên tục**: trong một đoạn liên tục được coi
  là "có phụ đề gốc" (không bị ngắt bởi khoảng khai báo "không có"), hệ thống
  giả định vị trí phụ đề gốc không đổi và chỉ xác định một vị trí đại diện cho
  cả đoạn. Nếu vị trí thực tế đổi nhiều lần trong cùng một đoạn, người dùng cần
  khai báo tách nhỏ thành nhiều khoảng "không có phụ đề gốc" xen giữa để mỗi
  đoạn có phụ đề gốc chỉ còn một vị trí cố định.
- **Một vùng chữ mỗi đoạn**: trong số các dòng chữ KHÔNG có nền hộp (sau khi đã
  loại các dòng tiêu đề có nền hộp theo FR-014), mỗi đoạn có phụ đề gốc được
  giả định chỉ có MỘT vùng chữ cần che — không xử lý trường hợp nhiều dòng phụ
  đề không nền nằm ở 2 vị trí khác nhau xuất hiện đồng thời.
- **Nền hộp là dấu hiệu đáng tin cậy để phân biệt tiêu đề với phụ đề**: giả định
  các nền tảng dựng video (TikTok, CapCut...) dùng nền hộp riêng cho dòng tiêu
  đề/mô tả bối cảnh, khác với kiểu phụ đề khớp lời nói (không nền, chỉ viền
  chữ) — đây là quy tắc chung cho phần lớn video, không cam kết đúng 100% với
  mọi phong cách dựng video.
- **Cỡ chữ cố định theo tỉ lệ**: cỡ chữ "nhỏ hơn mặc định" của phụ đề mới ở các
  khoảng có phụ đề gốc là một tỉ lệ cố định so với cỡ chữ mặc định hiện có của
  phụ đề tự động, không cấu hình riêng theo từng job ở v1.
- **Chữ latin, dễ nhận diện**: tính năng được thiết kế cho phụ đề gốc dạng chữ
  latin phổ thông (tiếng Anh); không cam kết độ chính xác với chữ viết tay hay
  phông chữ cách điệu mạnh.
- **Một người dùng duy nhất**: kế thừa từ các tính năng trước (đã có đăng nhập
  ở web UI), không cần phân quyền cấu hình.
- **Chỉ áp dụng cùng chế độ có phụ đề hiển thị**: tính năng chỉ có ý nghĩa khi
  video thực sự có phụ đề mới hiển thị trên hình (chế độ phụ đề tự động, hoặc
  lồng tiếng có bật phụ đề động) — lồng tiếng không bật phụ đề động thì không
  có phụ đề nào để chèn nên tính năng không áp dụng.
- **Phụ thuộc tuỳ chọn vào "Quản lý pipeline"**: phần review vị trí phụ đề gốc
  (User Story 4) chỉ xuất hiện khi job cũng bật 008-supervised-pipeline; đây là
  một sự kết hợp không bắt buộc — mọi phần còn lại của tính năng dùng được đầy
  đủ mà không cần bật Quản lý pipeline (US1/US2/US3).

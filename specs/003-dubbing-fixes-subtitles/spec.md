# Feature Specification: Sửa lỗi lồng tiếng & thêm phụ đề tự động, phụ đề động

**Feature Branch**: `003-dubbing-fixes-subtitles`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "thêm tính năng và fix bug

1. Lồng tiếng Dịch chuẩn: hiện đang có nhưng còn lỗi Không giữ được nhạc nền
   gốc
2. Lồng tiếng Sáng tạo: hiện đang có nhưng còn lỗi Giọng đọc lệch thời lượng
   đáng kể so với video gốc, Không giữ được nhạc nền gốc
3. Tạo phụ đề tự động: thêm sub ở góc dưới và giữ âm thanh gốc
4. 1,2 thêm tính năng Hiển thị từng từ/từng câu của kịch bản chữ chạy trên màn
   hình đúng khớp theo nhịp giọng đọc"

## Clarifications

### Session 2026-07-26

- Q: Đơn vị đồng bộ của phụ đề động (FR-008) — từng câu/cụm hay từng từ kiểu
  karaoke? → A: Từng câu/cụm — đơn giản hơn, dùng mốc thời gian cấp câu đã có
  sẵn từ TTS, độ tin cậy cao hơn cấp từ.
- Q: Nguồn văn bản cho phụ đề tự động (FR-009) — dịch sát nghĩa như Dịch
  chuẩn, hay văn phong viết lại tự do như Sáng tạo? → A: Dịch sát nghĩa (như
  Dịch chuẩn) — khớp đúng với âm thanh gốc người dùng đang nghe.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Giữ nhạc nền gốc khi lồng tiếng (Priority: P1)

Người dùng chạy job lồng tiếng (Dịch chuẩn hoặc Sáng tạo) cho video có nhạc nền
ở phần âm thanh gốc; video sản phẩm cuối cùng vẫn nghe được nhạc nền đó, chỉ
lời thoại gốc được thay bằng giọng đọc mới — đúng như tính năng đã quảng cáo
nhưng hiện đang lỗi mất nhạc nền ở cả 2 chế độ.

**Why this priority**: Đây là lỗi hồi quy trên một tính năng đã tồn tại và
được người dùng xác nhận là giá trị cốt lõi (video sản phẩm nghe "thật" hơn
khi còn nhạc nền) — không sửa thì cả 2 chế độ lồng tiếng hiện có đều coi như
bị hỏng một phần.

**Independent Test**: Chạy 1 job Dịch chuẩn và 1 job Sáng tạo với cùng 1 video
nguồn có nhạc nền rõ; nghe video sản phẩm của cả 2, xác nhận nhạc nền vẫn hiện
diện xuyên suốt, không bị mất hoàn toàn hay ngắt quãng bất thường.

**Acceptance Scenarios**:

1. **Given** video nguồn có nhạc nền phát hiện được, **When** người dùng chạy
   job ở chế độ Dịch chuẩn, **Then** video sản phẩm giữ được nhạc nền đó song
   song với giọng đọc mới.
2. **Given** video nguồn có nhạc nền phát hiện được, **When** người dùng chạy
   job ở chế độ Sáng tạo, **Then** video sản phẩm giữ được nhạc nền đó song
   song với giọng đọc mới.
3. **Given** hệ thống không thể tách được nhạc nền dù video nguồn thực sự có
   (lỗi kỹ thuật), **When** job hoàn tất, **Then** giao diện hiển thị rõ cảnh
   báo "không giữ được nhạc nền gốc" thay vì âm thầm xuất video thiếu nhạc.

---

### User Story 2 - Khớp thời lượng giọng đọc với video gốc ở chế độ Sáng tạo (Priority: P1)

Người dùng chạy job Sáng tạo; giọng đọc kịch bản tự soạn kết thúc gần đúng lúc
video gốc kết thúc, không bị cắt cụt giữa chừng hay kết thúc sớm để lại một
đoạn video câm dài phía sau.

**Why this priority**: Được người dùng xác nhận trực tiếp là vấn đề chất lượng
sản phẩm thực tế gặp phải khi dùng thử, ảnh hưởng ngay đến trải nghiệm xem của
người xem cuối.

**Independent Test**: Chạy 1 job Sáng tạo với video nguồn có thời lượng đã
biết; so sánh thời lượng giọng đọc với thời lượng video gốc, xác nhận độ lệch
nằm trong ngưỡng chấp nhận được (xem SC-002).

**Acceptance Scenarios**:

1. **Given** một video nguồn có thời lượng xác định, **When** người dùng chạy
   job Sáng tạo, **Then** giọng đọc kết thúc trong ngưỡng lệch chấp nhận được
   so với thời lượng video gốc (SC-002), không bị cắt giữa câu.
2. **Given** kịch bản tự soạn quá dài để đọc vừa khít dù đã điều chỉnh tốc độ
   đọc ở mức tự nhiên tối đa, **When** job hoàn tất, **Then** giao diện hiển
   thị rõ cảnh báo lệch thời lượng thay vì đọc nhanh bất thường/nghe không tự
   nhiên để cố khớp bằng mọi giá.

---

### User Story 3 - Tạo phụ đề tự động, giữ nguyên âm thanh gốc (Priority: P2)

Người dùng chọn một chế độ xử lý mới: video sản phẩm giữ nguyên 100% âm thanh
gốc (lời thoại + nhạc nền, không lồng tiếng), chỉ thêm chữ phụ đề hiển thị ở
góc dưới màn hình, khớp đúng thời điểm lời thoại gốc được nói ra.

**Why this priority**: Một cách repurpose video khác, ít can thiệp hơn lồng
tiếng (giữ giọng thật của nhân vật gốc) — có giá trị độc lập nhưng không chặn
2 chế độ lồng tiếng đã có.

**Independent Test**: Chạy 1 job ở chế độ "Phụ đề tự động" với 1 video nguồn
có lời thoại; xác nhận âm thanh sản phẩm giống hệt âm thanh gốc (không có
giọng đọc mới), và phụ đề xuất hiện ở góc dưới đúng theo nhịp lời thoại.

**Acceptance Scenarios**:

1. **Given** video nguồn có lời thoại, **When** người dùng chọn chế độ "Phụ đề
   tự động" và chạy job, **Then** hệ thống không tạo giọng đọc mới, âm thanh
   sản phẩm giữ nguyên như video gốc.
2. **Given** job "Phụ đề tự động" đã hoàn tất, **When** người dùng xem video
   sản phẩm, **Then** phụ đề chữ hiển thị ở góc dưới khớp theo đúng thời điểm
   lời thoại gốc tương ứng được nói ra.
3. **Given** video nguồn không có lời thoại nào phát hiện được, **When** người
   dùng chạy job "Phụ đề tự động", **Then** hệ thống báo rõ không có nội dung
   để tạo phụ đề thay vì xuất ra một job trống/gây hiểu nhầm là lỗi hệ thống.

---

### User Story 4 - Phụ đề động chạy khớp nhịp giọng đọc cho video đã lồng tiếng (Priority: P3)

Với video đã xử lý ở chế độ Dịch chuẩn hoặc Sáng tạo, người dùng thấy thêm chữ
kịch bản hiển thị/chạy trên màn hình đúng khớp theo nhịp giọng đọc — không
phải phụ đề tĩnh hiện nguyên khối ngay từ đầu.

**Why this priority**: Tính năng bổ sung nâng cao trải nghiệm xem (giống hiệu
ứng phụ đề động phổ biến trên mạng xã hội), phụ thuộc vào User Story 1/2 đã
cho ra giọng đọc đúng nhịp trước, và có độ phức tạp kỹ thuật cao nhất trong
toàn bộ tính năng.

**Independent Test**: Chạy 1 job Dịch chuẩn hoặc Sáng tạo với phụ đề động bật
sẵn; xem video sản phẩm, xác nhận chữ xuất hiện đúng lúc giọng đọc đang đọc
phần nội dung tương ứng, không lệch quá 1 giây so với âm thanh (SC-004).

**Acceptance Scenarios**:

1. **Given** một job Dịch chuẩn hoặc Sáng tạo đã hoàn tất, **When** người dùng
   xem video sản phẩm, **Then** chữ kịch bản hiển thị trên màn hình đúng khớp
   theo nhịp giọng đọc thực tế của job đó.
2. **Given** một đoạn kịch bản dài hơn khung hình cho phép, **When** phụ đề
   động hiển thị đoạn đó, **Then** hệ thống tự chia dòng/đoạn hợp lý, không bị
   tràn ra ngoài khung hình.

---

### Edge Cases

- Video nguồn không thực sự có nhạc nền tách biệt (toàn bộ âm thanh là lời
  thoại/tiếng ồn nền không tách được thành 1 track nhạc rõ ràng): hệ thống
  không hiển thị cảnh báo "mất nhạc nền" giả vì thực tế không có gì để giữ.
- Video nguồn có watermark/hardsub sẵn ở đúng vị trí góc dưới, trùng vị trí
  phụ đề tự động: hệ thống vẫn thêm phụ đề, cảnh báo chồng lấn vị trí tương tự
  cảnh báo watermark đã có ở 001-video-repurpose-pipeline.
- Job "Phụ đề tự động" hoặc phụ đề động thất bại giữa chừng: áp dụng đúng cơ
  chế resume/thử lại đã có (002-web-ui), không phải xử lý lại từ đầu.
- Video nguồn rất ngắn (vài giây) hoặc rất dài: ngưỡng lệch thời lượng (SC-002)
  và đồng bộ phụ đề động vẫn áp dụng theo cùng tỷ lệ %, không có ngoại lệ theo
  độ dài.
- Người dùng chọn "Phụ đề tự động" cho video không có bất kỳ giọng nói nào
  (chỉ nhạc/hình ảnh): xem Acceptance Scenario 3 của User Story 3.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST giữ được nhạc nền gốc trong video sản phẩm ở cả
  2 chế độ lồng tiếng hiện có (Dịch chuẩn, Sáng tạo) khi video nguồn có nhạc
  nền tách được — không chỉ "cố gắng tách" như hiện tại mà phải đảm bảo nhạc
  nền có mặt và nghe rõ trong sản phẩm cuối cùng.
- **FR-002**: Hệ thống MUST đảm bảo giọng đọc lồng tiếng (đặc biệt ở chế độ
  Sáng tạo) kết thúc trong ngưỡng lệch chấp nhận được so với thời lượng video
  gốc (SC-002), không bị cắt cụt giữa câu.
- **FR-003**: Hệ thống MUST hiển thị cảnh báo rõ ràng trên job/kết quả khi
  không đạt được việc giữ nhạc nền hoặc khớp thời lượng (trường hợp không
  tránh được về mặt kỹ thuật) — không âm thầm bỏ qua và xuất sản phẩm thiếu
  sót mà không báo.
- **FR-004**: Hệ thống MUST cung cấp một chế độ xử lý mới "Phụ đề tự động",
  ngang hàng và có thể chọn thay thế cho 2 chế độ lồng tiếng hiện có (Dịch
  chuẩn, Sáng tạo) khi khởi tạo job.
- **FR-005**: Ở chế độ "Phụ đề tự động", hệ thống MUST giữ nguyên 100% âm
  thanh gốc của video (lời thoại + nhạc nền) — không tạo giọng đọc mới, không
  tách/loại bỏ bất kỳ phần âm thanh nào.
- **FR-006**: Ở chế độ "Phụ đề tự động", hệ thống MUST hiển thị phụ đề chữ ở
  góc dưới video, khớp theo đúng mốc thời gian lời thoại gốc tương ứng được
  nói ra.
- **FR-007**: Với job đã xử lý ở chế độ Dịch chuẩn hoặc Sáng tạo, hệ thống
  MUST cung cấp thêm phụ đề động: chữ kịch bản hiển thị/chạy trên màn hình
  đúng khớp theo nhịp thời điểm giọng đọc thực tế phát ra phần nội dung tương
  ứng — không hiển thị nguyên khối tĩnh toàn bộ câu/đoạn ngay từ đầu.
- **FR-008**: Đơn vị đồng bộ của phụ đề động (FR-007) MUST là theo từng
  câu/cụm — mỗi câu hiện lên đúng lúc giọng đọc bắt đầu đọc câu đó, không tách
  nhỏ tới từng từ riêng lẻ (Clarification 2026-07-26 Q1).
- **FR-009**: Nội dung phụ đề tự động (FR-006) MUST là bản dịch sát nghĩa
  khớp với lời thoại gốc thực tế (cùng cách dịch như chế độ Dịch chuẩn) —
  không dùng văn phong viết lại tự do của chế độ Sáng tạo, để tránh lệch nghĩa
  giữa chữ đọc và âm thanh gốc người dùng đang nghe (Clarification 2026-07-26
  Q2).
- **FR-010**: Hệ thống MUST cho phép resume/thử lại job "Phụ đề tự động" hoặc
  job có phụ đề động thất bại giữa chừng, dùng đúng cơ chế resume đã có
  (002-web-ui), không xử lý lại từ đầu.

### Key Entities

Tái sử dụng các entity đã định nghĩa ở
[data-model.md của 001-video-repurpose-pipeline](../001-video-repurpose-pipeline/data-model.md)
(Job, Source Video, Script, Voice Track, Background Audio, Output Video) và mô
hình chế độ kịch bản đã có ở 002-web-ui — bổ sung:

- **Processing Mode**: Thuộc tính của Job xác định cách xử lý — mở rộng từ 2
  giá trị hiện có (Dịch chuẩn, Sáng tạo) thêm giá trị thứ 3 "Phụ đề tự động".
- **Subtitle Track**: Danh sách các đoạn văn bản kèm mốc thời gian bắt
  đầu/kết thúc, dùng để hiển thị phụ đề tự động (FR-006) hoặc phụ đề động
  (FR-007) trên video sản phẩm — không phải track lưu trữ độc lập, sinh ra từ
  Script/Voice Track đã có của job đó.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Trong các job lồng tiếng (Dịch chuẩn hoặc Sáng tạo) mà video
  nguồn có nhạc nền tách được, ít nhất 95% số job cho ra sản phẩm vẫn nghe rõ
  nhạc nền — so với tình trạng hiện tại là gần như luôn mất nhạc nền.
- **SC-002**: Ở chế độ Sáng tạo, thời lượng giọng đọc lệch không quá 10% so
  với thời lượng video gốc ở ít nhất 90% số job.
- **SC-003**: Người dùng tạo được video chỉ có phụ đề (giữ nguyên âm thanh
  gốc, không lồng tiếng) và xác nhận được nội dung phụ đề khớp đúng lời thoại
  đang nghe thấy.
- **SC-004**: Ở video đã bật phụ đề động, chữ xuất hiện lệch không quá 1 giây
  so với thời điểm giọng đọc thực tế đọc tới phần nội dung tương ứng.
- **SC-005**: 100% job có vấn đề chất lượng (mất nhạc nền, lệch thời lượng)
  hiển thị rõ nguyên nhân cho người dùng thay vì âm thầm xuất sản phẩm thiếu
  sót mà không có cảnh báo nào.

## Assumptions

- Kế thừa toàn bộ hạ tầng download/ASR/script-gen/TTS đã có ở
  001-video-repurpose-pipeline; đây là bản sửa lỗi + mở rộng, không thay
  nguồn ASR/TTS/LLM đang dùng.
- "Phụ đề tự động" không lồng tiếng, không cần TTS, không cần tách nhạc nền —
  giữ nguyên track âm thanh gốc 100% (khác biệt cơ bản so với 2 chế độ lồng
  tiếng hiện có).
- Phụ đề (cả tự động ở FR-006 lẫn phụ đề động ở FR-007) được ghi cứng
  (burned-in) vào video xuất ra, để xem được trên bất kỳ nền tảng nào
  (TikTok, Douyin, YouTube...) mà không cần bật riêng track phụ đề.
- Vị trí "góc dưới" cho phụ đề tự động (FR-006) là vị trí cố định ở bản đầu,
  chưa cần tuỳ chỉnh vị trí/kiểu chữ.
- Việc chọn Processing Mode (Dịch chuẩn / Sáng tạo / Phụ đề tự động) và bật/tắt
  phụ đề động là các lựa chọn độc lập, thực hiện qua đúng luồng khởi tạo job
  đã có ở giao diện web (002-web-ui) — không thay đổi cách người dùng nộp
  URL/theo dõi tiến trình/xem lịch sử job.
- Không giới hạn số lần thử lại (resume) cho job thuộc phạm vi tính năng này,
  nhất quán với 002-web-ui.

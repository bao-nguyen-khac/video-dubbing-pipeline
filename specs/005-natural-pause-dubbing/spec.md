# Feature Specification: Lồng tiếng khớp nhịp tự nhiên theo từng câu

**Feature Branch**: `005-natural-pause-dubbing`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "Sửa lỗi lồng tiếng nói liên tục quá chậm/dở khi video gốc có ngắt nghỉ tự nhiên. Hiện tại pipeline dịch/viết lại toàn bộ kịch bản thành 1 khối văn bản, tổng hợp giọng đọc 1 lần liên tục rồi kéo giãn/nén đều toàn bộ audio cho khớp tổng thời lượng video gốc — cách này làm mất hết khoảng lặng tự nhiên (hít thở, ngắt câu, dừng nhấn) của giọng gốc, khiến giọng dịch nghe chậm và không tự nhiên khi video gốc có nhiều đoạn ngắt nghỉ. Cần đổi sang tổng hợp giọng đọc theo từng câu/đoạn (dùng mốc thời gian start/end đã có sẵn từ ASR trong transcript.json), đặt mỗi câu dịch vào đúng khung thời gian của câu gốc tương ứng, chèn khoảng lặng thật giữa các câu thay vì để TTS nói liên tục, và chỉ chỉnh tốc độ nhẹ theo từng câu (thay vì kéo giãn 1 lần cho toàn bộ) để khớp khung thời gian. Áp dụng cho cả 2 chế độ translate và rewrite, cả 3 provider TTS (edge-tts, Vivibe/lucyai, 9router/router-tts)."

## Clarifications

### Session 2026-07-26

- Q: Khi 1 câu dịch/viết lại dài hơn khung thời gian gốc dù đã tăng tốc đọc
  tới giới hạn hợp lý, phần "tràn" nên xử lý thế nào? → A: Cho tràn sang
  khoảng lặng/khung câu kế tiếp, đẩy lùi các câu sau — không cắt nội dung,
  không tăng tốc vượt giới hạn hợp lý.
- Q: Có tận dụng mốc thời gian chính xác theo từng câu (hệ quả của tính năng
  này) để mở rộng phụ đề động (feature 003) sang cả Vivibe/9router (hiện chỉ
  chính xác với edge-tts), hay giữ nguyên phạm vi cũ? → A: Mở rộng luôn cho
  cả 3 provider; cơ chế streaming-caption cũ riêng cho edge-tts trở nên dư
  thừa và có thể bị thay thế hoàn toàn.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Giữ nhịp ngắt nghỉ tự nhiên khi Dịch chuẩn (Priority: P1)

Người dùng chạy lồng tiếng "Dịch chuẩn" (translate) cho 1 video có người nói ngắt
nghỉ rõ ràng (dừng để hít thở, chuyển ý, nhấn câu...). Kết quả lồng tiếng nghe
tự nhiên: mỗi câu được đọc với tốc độ bình thường, các khoảng lặng giữa câu
xuất hiện đúng những chỗ video gốc có ngắt nghỉ — thay vì nghe một mạch không
nghỉ và bị chậm đều để "vừa khít" tổng thời lượng.

**Why this priority**: Đây là giá trị cốt lõi được yêu cầu và là chế độ lồng
tiếng được dùng nhiều nhất (mặc định của tính năng). Không có phần này thì
tính năng chưa giải quyết được vấn đề gốc.

**Independent Test**: Chạy 1 job `script_mode=translate` với video nguồn có
≥3 khoảng lặng rõ rệt (≥1s) giữa các câu thoại; nghe thử `output.mp4` và xác
nhận các khoảng lặng đó xuất hiện đúng vị trí tương ứng, giọng đọc từng câu
không bị kéo chậm bất thường.

**Acceptance Scenarios**:

1. **Given** video gốc có 1 khoảng lặng 2s giữa câu A và câu B, **When** chạy
   job lồng tiếng Dịch chuẩn, **Then** bản ghi giọng đọc kết quả có 1 khoảng
   lặng tương ứng (không nhất thiết đúng 2s tuyệt đối, nhưng rõ ràng nghe
   được) giữa bản dịch câu A và câu B, thay vì nói liền mạch.
2. **Given** video gốc nói gần như liên tục, gần như không có khoảng lặng
   đáng kể, **When** chạy job lồng tiếng Dịch chuẩn, **Then** kết quả không
   tệ hơn hành vi hiện tại (không phát sinh khoảng lặng giả, không làm chậm
   thêm so với trước).
3. **Given** 1 câu dịch có độ dài văn bản gần khớp thời lượng khung gốc của
   câu đó, **When** tổng hợp giọng đọc câu này, **Then** tốc độ đọc gần với
   tốc độ tự nhiên (không cần chỉnh tốc độ đáng kể).

---

### User Story 2 - Giữ nhịp ngắt nghỉ tự nhiên khi Sáng tạo (Priority: P2)

Người dùng chạy lồng tiếng "Sáng tạo" (rewrite, kịch bản được viết lại chứ
không dịch sát nghĩa) và vẫn muốn giọng đọc kết quả bám theo nhịp ngắt nghỉ
của video gốc thay vì đọc liền một mạch rồi kéo giãn toàn bộ.

**Why this priority**: Cùng vấn đề như US1 nhưng ở chế độ ít dùng hơn
(translate là mặc định). Có thể triển khai sau US1 mà vẫn cho MVP dùng được
ngay ở chế độ chính.

**Independent Test**: Chạy 1 job `script_mode=rewrite` với cùng video có
khoảng lặng rõ rệt như US1; xác nhận giọng đọc kết quả cũng giữ được nhịp
ngắt nghỉ tương tự dù nội dung câu chữ được viết lại sáng tạo (không dịch sát
nghĩa từng từ).

**Acceptance Scenarios**:

1. **Given** video gốc có nhiều đoạn ngắt nghỉ, **When** chạy job Sáng tạo,
   **Then** kịch bản sáng tạo được chia theo đúng số đoạn/khung thời gian ASR
   gốc (không phải 1 khối văn bản tự do), và giọng đọc kết quả giữ khoảng
   lặng giữa các đoạn tương tự US1.
2. **Given** người dùng đã quen kịch bản Sáng tạo trước đây được viết như 1
   đoạn văn liền mạch, **When** dùng tính năng mới, **Then** nội dung sáng
   tạo vẫn giữ được văn phong tự nhiên, không bị vụn/cụt vì bị ép chia theo
   từng câu ASR gốc quá ngắn.

---

### User Story 3 - Job vẫn hoàn tất khi 1 vài câu lỗi tổng hợp giọng đọc (Priority: P3)

Khi tổng hợp giọng đọc theo từng câu (thay vì 1 lần cho cả bài), số lượt gọi
TTS tăng lên đáng kể — tăng khả năng 1 vài câu bị lỗi tạm thời (timeout, hết
quota provider...). Người dùng muốn job vẫn hoàn tất với các câu còn lại,
thay vì toàn bộ job thất bại chỉ vì 1 câu.

**Why this priority**: Là yêu cầu chất lượng/độ tin cậy đi kèm khi đổi sang
kiến trúc nhiều lượt gọi API hơn — quan trọng nhưng không chặn giá trị cốt
lõi của US1/US2, có thể bổ sung sau.

**Independent Test**: Giả lập 1 câu bị lỗi tổng hợp giọng đọc (VD tạm ngắt
mạng ở đúng 1 lượt gọi) giữa 1 job có nhiều câu; xác nhận job vẫn hoàn tất
(`status=done`), có cảnh báo rõ ràng câu nào bị ảnh hưởng, thay vì job
`status=failed`.

**Acceptance Scenarios**:

1. **Given** 1 job đang tổng hợp giọng đọc theo từng câu và 1 câu cụ thể gọi
   API TTS thất bại dù đã thử lại, **When** pipeline tiếp tục xử lý các câu
   còn lại, **Then** job vẫn hoàn tất (`status=done`) với 1 cảnh báo cho biết
   có câu bị lỗi/thay thế bằng khoảng lặng.
2. **Given** job đã hoàn tất với cảnh báo "1 số câu lỗi tổng hợp", **When**
   người dùng xem chi tiết job, **Then** họ thấy rõ đây là vấn đề cục bộ
   (không phải toàn bộ giọng đọc bị lỗi) để cân nhắc chạy lại nếu cần.

---

### Edge Cases

- Bản dịch/viết lại của 1 câu dài hơn đáng kể so với khung thời gian câu gốc
  tương ứng, ngay cả khi đã tăng tốc đọc tới giới hạn hợp lý vẫn không vừa:
  xử lý theo FR-009 (cho tràn sang khung câu kế tiếp, đẩy lùi các câu sau).
- 2 câu liên tiếp trong video gốc không có khoảng lặng đáng kể giữa chúng
  (câu sau bắt đầu ngay khi câu trước kết thúc): hệ thống không chèn khoảng
  lặng giả, nối liền như hiện tại.
- Video gốc gần như không có khoảng lặng nào (nói liên tục toàn bộ): hành vi
  kết quả phải tương đương hoặc tốt hơn cách làm hiện tại, không phát sinh
  giật/khoảng lặng giả.
- 1 câu ASR gốc quá ngắn (1-2 từ, VD tiếng cảm thán) khi dịch/viết lại có thể
  ra câu dài hơn nhiều lần khung thời gian gốc — cùng loại vấn đề, xử lý theo
  FR-009.
- Nhiều câu liên tiếp đều tràn (FR-009) có thể khiến tổng thời lượng lồng
  tiếng dài hơn video gốc đáng kể — vẫn hiển thị cảnh báo "lệch thời lượng"
  hiện có (feature 003) nếu độ lệch tổng thể vượt ngưỡng, không che giấu.
- Toàn bộ các câu của 1 job đều lỗi tổng hợp giọng đọc (VD mất kết nối
  provider hoàn toàn): job vẫn phải báo lỗi rõ ràng (`status=failed`) như
  hiện tại — US3 chỉ áp dụng cho lỗi cục bộ 1 phần, không che giấu lỗi toàn
  phần.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Ở chế độ Dịch chuẩn và Sáng tạo, hệ thống PHẢI tổng hợp giọng
  đọc theo từng câu/đoạn tương ứng với các đoạn thời gian đã có từ ASR
  (`transcript.json`), thay vì tổng hợp 1 lần cho toàn bộ kịch bản.
- **FR-002**: Hệ thống PHẢI đặt bản ghi giọng đọc của mỗi câu vào đúng vị trí
  thời gian (thời điểm bắt đầu) tương ứng với khung thời gian của câu gốc
  trong video, và PHẢI chèn khoảng lặng thật giữa các câu tương ứng với
  khoảng lặng giữa các câu trong video gốc.
- **FR-003**: Với mỗi câu, hệ thống PHẢI chỉ điều chỉnh tốc độ đọc cục bộ cho
  câu đó (trong giới hạn tốc độ hợp lý đã có, không đọc quá nhanh/quá chậm
  mất tự nhiên) để cố khớp khung thời gian riêng của câu, thay vì kéo
  giãn/nén đều toàn bộ bản ghi giọng đọc như cơ chế cũ.
- **FR-004**: Chế độ Sáng tạo (rewrite) PHẢI sinh nội dung theo cùng số
  lượng và thứ tự đoạn với các đoạn thời gian ASR gốc (giữ văn phong sáng
  tạo/viết lại tự do TRONG từng đoạn, không dịch sát nghĩa), để có thể áp
  dụng cùng cơ chế khớp nhịp như chế độ Dịch chuẩn.
- **FR-005**: Cả 3 provider giọng đọc (edge-tts, Vivibe/lucyai, 9router
  router-tts) PHẢI hỗ trợ tổng hợp theo cơ chế từng câu này với hành vi nhất
  quán (không riêng cho 1 provider).
- **FR-006**: Nếu tổng hợp giọng đọc của 1 câu cụ thể thất bại (sau khi đã
  thử lại theo cơ chế hiện có của provider đó), hệ thống PHẢI thay thế đoạn
  đó bằng khoảng lặng có độ dài bằng khung thời gian gốc của câu, ghi log rõ
  câu bị ảnh hưởng, và tiếp tục xử lý các câu còn lại thay vì làm job thất
  bại toàn bộ.
- **FR-007**: Job hoàn tất PHẢI hiển thị cảnh báo cho người dùng nếu có ít
  nhất 1 câu bị thay thế bằng khoảng lặng do lỗi tổng hợp (FR-006), phân biệt
  rõ với cảnh báo "lệch thời lượng" hiện có.
- **FR-008**: Hệ thống PHẢI xử lý đúng trường hợp 2 câu liên tiếp không có
  khoảng lặng đáng kể trong video gốc — không chèn khoảng lặng giả gây ngắt
  quãng không cần thiết.
- **FR-009**: Nếu 1 câu dịch/viết lại dài hơn khung thời gian gốc của câu đó
  dù đã tăng tốc đọc tới giới hạn hợp lý hiện có (không tăng tốc vượt giới
  hạn để tránh nghe mất tự nhiên), hệ thống PHẢI cho phần "tràn" kéo dài sang
  khoảng lặng/khung thời gian của câu kế tiếp, đẩy lùi thời điểm bắt đầu của
  câu kế tiếp theo tương ứng — không cắt bớt nội dung, không tăng tốc đọc
  vượt giới hạn hợp lý. Hệ quả: tổng thời lượng bản lồng tiếng có thể dài hơn
  video gốc một chút trong các job có nhiều câu tràn.
- **FR-010**: Tính năng này PHẢI tiếp tục giữ nhạc nền gốc và cơ chế trộn
  audio hiện có (không thay đổi hành vi giữ nhạc nền đã có ở feature 003).
- **FR-011**: Hệ thống PHẢI dùng mốc thời gian chính xác theo từng câu (sinh
  ra bởi cơ chế khớp nhịp mới của tính năng này) làm nguồn cho phụ đề động
  (dynamic captions, feature 003) ở **cả 3 provider** giọng đọc — mở rộng từ
  phạm vi hiện tại (chỉ chính xác với edge-tts nhờ cơ chế streaming riêng của
  thư viện đó). Cơ chế bắt mốc thời gian streaming cũ dành riêng cho edge-tts
  trở nên dư thừa và có thể được thay thế hoàn toàn bởi mốc thời gian mới.

### Key Entities

- **Câu lồng tiếng (Dubbed Segment)**: 1 đơn vị nhỏ nhất được xử lý độc lập —
  gồm khung thời gian gốc (`start`, `end` từ ASR), nội dung đã dịch/viết lại,
  và bản ghi giọng đọc tổng hợp riêng cho câu đó. Áp dụng cho cả 2 chế độ
  Dịch chuẩn/Sáng tạo (mở rộng khái niệm segment đã có ở chế độ Phụ đề tự
  động, feature 003).
- **Bản ghi giọng đọc tổng hợp (Voice Track)**: Kết quả cuối cùng được ghép
  từ nhiều "Câu lồng tiếng" theo đúng thứ tự và vị trí thời gian, xen kẽ
  khoảng lặng thật giữa các câu — thay thế cho bản ghi liên tục 1 khối như
  hiện tại.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với video nguồn có ít nhất 3 khoảng lặng tự nhiên ≥1 giây giữa
  các câu thoại, ít nhất 90% các khoảng lặng đó xuất hiện trong bản lồng
  tiếng kết quả ở vị trí lệch không quá 1 giây so với video gốc.
- **SC-002**: Với ít nhất 80% số câu trong 1 job, mức điều chỉnh tốc độ đọc
  cần thiết để khớp khung thời gian nằm trong khoảng tự nhiên (không bị nghe
  rõ là "đọc nhanh/chậm bất thường") — thay vì hiện tại toàn bộ bản ghi có
  thể bị chậm đều tới mức nghe rõ bất thường.
- **SC-003**: 1 lỗi tổng hợp giọng đọc cục bộ ở 1 câu (trong tổng số nhiều
  câu của job) không làm job thất bại toàn bộ — job vẫn hoàn tất với cảnh báo
  rõ ràng, đo được qua tỉ lệ job hoàn tất thành công tăng lên so với hành vi
  cũ (toàn bộ job fail khi TTS lỗi).
- **SC-004**: Hành vi và chất lượng khớp nhịp tương đương nhau khi dùng bất
  kỳ 1 trong 3 provider giọng đọc đã hỗ trợ.

## Assumptions

- Mốc thời gian `start`/`end` theo từng câu do module ASR hiện có
  (`transcript.json`) cung cấp đã đủ chính xác để làm khung tham chiếu khớp
  nhịp — tính năng này không thay đổi độ chính xác ASR.
- Giới hạn tốc độ đọc "hợp lý" (không quá nhanh/chậm) tiếp tục dùng đúng biên
  đã có sẵn cho từng provider (edge-tts: `rate` [-20%,+40%]; Vivibe: `speed`
  [0.5,2.0]; 9router: hậu xử lý `atempo` [0.5,2.0]) — không mở rộng thêm biên
  độ trong tính năng này.
- Chế độ Phụ đề tự động (`script_mode=subtitle`, không lồng tiếng) không
  thuộc phạm vi tính năng này — chế độ đó vốn đã giữ nguyên audio gốc, không
  có giọng đọc tổng hợp.
- Tăng số lượt gọi API TTS (theo từng câu thay vì 1 lần cho cả bài) có thể
  làm tăng thời gian xử lý tổng thể và chi phí/quota gọi API — được chấp
  nhận đánh đổi để có chất lượng lồng tiếng tự nhiên hơn.

# Feature Specification: Chọn giọng đọc & nghe thử trước khi chạy job

**Feature Branch**: `004-voice-selection-preview`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "ở giao diện web thêm option chọn giọng đọc
(provider edge-tts hoặc LucyAI/Vivibe), người dùng có thể nghe thử giọng
trước khi chạy job, ngoài edge-tts bổ sung thêm LucyAI/Vivibe
(api.lucylab.io) làm nguồn giọng đọc thứ 2"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Chọn giọng đọc trước khi chạy job (Priority: P1)

Người dùng xem được danh sách giọng đọc có sẵn (gồm cả giọng từ edge-tts và
từ LucyAI/Vivibe nếu đã cấu hình), chọn 1 giọng cụ thể trước khi chạy job ở
chế độ Dịch chuẩn hoặc Sáng tạo, và video sản phẩm cuối cùng phát đúng giọng
đã chọn.

**Why this priority**: Đây là giá trị cốt lõi — không chọn được giọng thì
"nghe thử" (US2) không có ý nghĩa gì để dùng. Danh sách giọng có LucyAI cũng
là điều kiện để LucyAI thực sự trở thành "nguồn giọng đọc thứ 2" như mô tả
gốc, không chỉ nằm trong `.env`.

**Independent Test**: Mở form tạo job, thấy danh sách giọng đọc (kèm rõ
provider của từng giọng), chọn 1 giọng khác giọng mặc định, chạy job ở chế độ
Dịch chuẩn; nghe video sản phẩm, xác nhận đúng giọng đã chọn.

**Acceptance Scenarios**:

1. **Given** người dùng mở form tạo job ở chế độ Dịch chuẩn hoặc Sáng tạo,
   **When** trang tải xong, **Then** họ thấy danh sách giọng đọc để chọn, mỗi
   giọng hiển thị rõ tên và provider (edge-tts hoặc LucyAI/Vivibe).
2. **Given** người dùng chọn 1 giọng cụ thể rồi chạy job, **When** job hoàn
   tất, **Then** giọng đọc trong video sản phẩm đúng là giọng đã chọn, không
   phải giọng mặc định khác.
3. **Given** người dùng không chọn giọng nào (giữ mặc định), **When** job
   chạy, **Then** hệ thống dùng đúng giọng mặc định hiện có (không đổi hành
   vi cũ).
4. **Given** LucyAI/Vivibe chưa được cấu hình (chưa có API key), **When**
   người dùng mở form, **Then** danh sách giọng vẫn hiển thị đầy đủ giọng
   edge-tts, không lỗi, không chặn luồng tạo job.
5. **Given** người dùng chọn 1 giọng LucyAI/Vivibe nhưng khi chạy job provider
   đó lỗi/không khả dụng, **When** job thất bại, **Then** hệ thống báo lỗi rõ
   ràng nguyên nhân, không âm thầm đổi sang giọng/provider khác.
6. **Given** chế độ đang chọn là "Phụ đề tự động", **When** người dùng xem
   form, **Then** phần chọn giọng đọc không hiển thị (chế độ này không có
   giọng đọc mới, giữ nguyên âm thanh gốc).

---

### User Story 2 - Nghe thử giọng đọc trước khi chạy job (Priority: P2)

Người dùng bấm nghe thử 1 giọng đọc trong danh sách và nghe được ngay 1 đoạn
âm thanh mẫu bằng đúng giọng đó, trước khi quyết định chọn giọng nào để chạy
job thật.

**Why this priority**: Nâng cao trải nghiệm/độ tin cậy khi chọn giọng (đặc
biệt hữu ích khi danh sách có nhiều giọng LucyAI lạ chưa từng nghe), nhưng
không chặn giá trị cốt lõi của US1 — người dùng vẫn chọn được giọng theo tên
dù chưa nghe thử.

**Independent Test**: Ở danh sách giọng đọc, bấm nút nghe thử 1 giọng bất kỳ
(cả edge-tts lẫn LucyAI nếu có); xác nhận nghe được âm thanh mẫu đúng giọng
đó trong thời gian hợp lý.

**Acceptance Scenarios**:

1. **Given** danh sách giọng đọc đang hiển thị, **When** người dùng bấm nghe
   thử 1 giọng edge-tts, **Then** hệ thống phát ngay đoạn âm thanh mẫu bằng
   giọng đó.
2. **Given** danh sách giọng đọc đang hiển thị, **When** người dùng bấm nghe
   thử 1 giọng LucyAI/Vivibe, **Then** hệ thống phát được đoạn âm thanh mẫu
   bằng giọng đó (có thể mất vài giây xử lý, giao diện hiển thị rõ đang tải).
3. **Given** người dùng đang nghe thử, **When** họ bấm nghe thử giọng khác,
   **Then** hệ thống phát giọng mới, không lẫn/chồng âm thanh giọng cũ.
4. **Given** provider LucyAI lỗi lúc nghe thử, **When** người dùng bấm nghe
   thử, **Then** hệ thống báo lỗi rõ ràng ngay tại đó, không ảnh hưởng tới
   phần còn lại của form (vẫn chọn/chạy job bình thường được).

---

### Edge Cases

- Tài khoản LucyAI/Vivibe của người dùng chưa cấu hình giọng nào
  (`getUserVoices` trả về rỗng): danh sách phần LucyAI trống, không lỗi,
  edge-tts vẫn đầy đủ.
- Nghe thử nhiều giọng liên tiếp nhanh: mỗi lần bấm là 1 lượt tạo âm thanh
  mẫu mới, không cần cache ở bản đầu.
- Đang có 1 job khác chạy (theo rule 1-job-tại-1-thời-điểm đã có): nghe thử
  giọng đọc vẫn dùng được bình thường — đây không phải thao tác tạo job mới,
  không bị chặn bởi rule đó.
- API key LucyAI từng hoạt động lúc nghe thử nhưng hết hạn/lỗi ngay trước lúc
  job thật chạy tới bước sinh giọng: job fail rõ ràng ở đúng bước đó (Edge
  Case này không phải lỗi hệ thống, là rủi ro dịch vụ ngoài).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST cung cấp danh sách giọng đọc để người dùng chọn
  trước khi chạy job ở chế độ Dịch chuẩn hoặc Sáng tạo. Chế độ Phụ đề tự động
  KHÔNG hiển thị phần chọn giọng (không có bước sinh giọng đọc mới).
- **FR-002**: Danh sách giọng đọc MUST gồm giọng từ edge-tts (luôn có sẵn,
  miễn phí) và giọng từ LucyAI/Vivibe nếu đã cấu hình — mỗi giọng hiển thị rõ
  tên và provider nguồn.
- **FR-003**: Nếu LucyAI/Vivibe chưa được cấu hình, hệ thống MUST vẫn hoạt
  động đầy đủ với riêng giọng edge-tts, không lỗi, không chặn tạo job.
- **FR-004**: Hệ thống MUST cho phép nghe thử (phát thử) 1 đoạn âm thanh mẫu
  bằng đúng giọng đang xem, cho cả giọng edge-tts lẫn LucyAI/Vivibe, trước
  khi chạy job thật.
- **FR-005**: Nội dung văn bản dùng để nghe thử MUST là 1 câu mẫu tiếng Việt
  cố định do hệ thống định sẵn — người dùng không tự nhập văn bản khác để
  nghe thử (Clarification Q1).
- **FR-006**: Job đã chạy MUST lưu lại đúng provider và giọng đọc người dùng
  đã chọn, và dùng chính xác giọng đó khi sinh audio thật — không tự ý dùng
  giọng mặc định khác nếu người dùng đã chọn giọng cụ thể.
- **FR-007**: Nếu giọng LucyAI/Vivibe được chọn để chạy job nhưng provider đó
  lỗi/không khả dụng lúc chạy, hệ thống MUST báo lỗi rõ ràng cho job đó,
  KHÔNG tự động âm thầm đổi sang edge-tts hoặc giọng khác.
- **FR-008**: Nghe thử giọng đọc (US2) MUST là thao tác độc lập, KHÔNG tạo
  job mới trong lịch sử job và KHÔNG bị chặn bởi rule "chỉ 1 job xử lý tại 1
  thời điểm" đã có.

### Key Entities

- **Voice**: Đại diện 1 giọng đọc có thể chọn — gồm `provider` (`edge-tts`
  hoặc `lucyai`), `voice_id` (định danh giọng theo provider), `name` (tên
  hiển thị). Danh sách Voice được tổng hợp động từ 2 nguồn (catalog cố định
  của edge-tts, `getUserVoices` của LucyAI) — không phải dữ liệu lưu trữ
  riêng của dự án.
- **Job** (mở rộng, tái sử dụng entity đã có ở
  [001](../001-video-repurpose-pipeline/data-model.md)/[003](../003-dubbing-fixes-subtitles/data-model.md)):
  thêm `tts_provider` và `voice_id` — thay cho giọng mặc định cố định
  `vi-VN-NamMinhNeural` trước đây. Chỉ có ý nghĩa khi `script_mode` là
  `translate`/`rewrite`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Video sản phẩm dùng đúng giọng đọc người dùng đã chọn trong
  100% job (không phát nhầm giọng khác).
- **SC-002**: Người dùng nghe được âm thanh mẫu trong vòng 10 giây kể từ khi
  bấm nghe thử, cho cả giọng edge-tts và LucyAI/Vivibe.
- **SC-003**: Khi chưa cấu hình LucyAI/Vivibe, người dùng vẫn dùng trọn vẹn
  tính năng chọn/nghe thử giọng với edge-tts, không gặp lỗi nào liên quan tới
  LucyAI.
- **SC-004**: 100% job dùng giọng LucyAI/Vivibe mà provider lỗi lúc chạy đều
  hiển thị rõ nguyên nhân trên giao diện, không có trường hợp im lặng đổi
  giọng mà người dùng không biết.

## Assumptions

- Danh sách giọng edge-tts mở rộng ra toàn bộ giọng tiếng Việt (`vi-VN`) có
  sẵn trong catalog edge-tts, không giới hạn ở 2 giọng mặc định/dự phòng hiện
  tại (`vi-VN-NamMinhNeural`/`vi-VN-HoaiMyNeural`) — đúng tinh thần "chọn
  giọng đọc" của mô tả gốc.
- API key LucyAI/Vivibe (`VIVIBE_API_KEY`) là secret cấu hình qua `.env`,
  theo đúng pattern `ROUTER_API_KEY`/`WEB_UI_*` đã có trong dự án — không lưu
  trong code hay job.json.
- Giọng đọc mặc định khi người dùng không chọn gì vẫn là giọng edge-tts hiện
  tại (`vi-VN-NamMinhNeural`) — giữ nguyên hành vi cũ, không phá job đã tạo
  trước feature này.
- Tính năng chỉ áp dụng cho chế độ Dịch chuẩn/Sáng tạo (lồng tiếng); chế độ
  Phụ đề tự động (003) không có bước sinh giọng đọc nên không áp dụng.
- Nghe thử không cần lưu trữ lâu dài (không phải file trung gian của job) —
  phát trực tiếp trên trình duyệt, không cần giữ lại sau khi người dùng rời
  trang.

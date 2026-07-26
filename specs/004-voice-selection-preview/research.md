# Phase 0 Research: Chọn giọng đọc & nghe thử trước khi chạy job

## 1. Danh sách giọng edge-tts — đã verify thật

**Đã kiểm tra thật** (`edge_tts.list_voices()` chạy trong container): toàn bộ
catalog edge-tts chỉ có đúng **2 giọng tiếng Việt**:
`vi-VN-HoaiMyNeural` (Nữ) và `vi-VN-NamMinhNeural` (Nam) — chính là 2 giọng
đã hardcode sẵn ở `tts/edge_tts_client.py` (`DEFAULT_VOICE`/`BACKUP_VOICE`).

- **Decision**: Danh sách giọng edge-tts trong feature này = đúng 2 giọng đã
  biết, lấy động qua `edge_tts.list_voices()` lọc `Locale` bắt đầu `vi-` (để
  không hardcode cứng, tự động cập nhật nếu Microsoft thêm giọng `vi-VN` mới
  sau này) thay vì tiếp tục hardcode.
- **Rationale**: Giả định ban đầu trong spec.md ("mở rộng ra toàn bộ giọng
  tiếng Việt có sẵn") hoá ra không đổi số lượng thực tế, nhưng lấy động vẫn
  đúng tinh thần "không giới hạn cứng ở 2 giọng" và tự thích ứng nếu catalog
  đổi.

## 2. Tích hợp LucyAI/Vivibe — thiết kế client module

**Nguồn**: `https://www.vivibe.app/api-docs.html` (đã fetch thật lúc
`/speckit-specify`). API thực chất là "LucyAI" (`api.lucylab.io`), JSON-RPC
qua POST, `Authorization: Bearer <VIVIBE_API_KEY>`.

- **Decision**: Thêm module `tts/lucyai_client.py` với 2 hàm chính:
  - `list_voices(api_key) -> list[dict]`: gọi `getUserVoices`
    (`{"method": "getUserVoices", "input": {"limit": 50, "page": 1}}`), trả
    về `[{"id", "name", "isActive"}]`. Chỉ giữ voice có `isActive == true`.
  - `synthesize(text, voice_id, api_key, output_path, speed=1.0) ->
    tuple[Path, float]`: gọi `ttsLongText`
    (`{"text", "userVoiceId": voice_id, "speed"}`) lấy `projectExportId`,
    poll `getExportStatus` mỗi 2s (đúng khuyến nghị docs) tới khi
    `state == "completed"` (hoặc `"failed"` → raise rõ), tải file ở field
    `url` (WAV) về `output_path`.
- **Naming**: Dùng định danh nội bộ `provider = "lucyai"` trong code/API
  (khớp đúng domain/API thật, tránh nhầm khi đọc log/response), nhưng nhãn
  hiển thị cho người dùng trên giao diện là **"Vivibe"** (tên người dùng biết
  tới) — ghi chú rõ trong code để người đọc sau không nhầm 2 tên khác nhau
  của cùng 1 dịch vụ.
- **Giới hạn khi implement**: Dự án CHƯA có `VIVIBE_API_KEY` thật (dịch vụ
  trả phí, cần tài khoản riêng của người dùng) — phần verify thật với API
  LucyAI thật (không phải chỉ đọc code) sẽ cần người dùng cung cấp API key
  tại bước implement, tương tự cách `ROUTER_API_KEY`/`TIKTOK_COOKIE` đã làm
  trước đây. Nếu chưa có, implement dựa đúng theo tài liệu API đã fetch, và
  verify được phần graceful-degrade (chưa cấu hình key → không lỗi, ẩn
  LucyAI) mà không cần key thật.
- **Rationale**: Tách module riêng theo đúng pattern `f2_client.py`/
  `ytdlp_client.py`/`edge_tts_client.py` đã có — mỗi provider 1 file, dễ
  thay thế/mở rộng thêm provider sau này.
- **Alternatives considered**: Gộp chung logic edge-tts và LucyAI vào 1 hàm
  `synthesize()` duy nhất với if/else — bị loại vì 2 API khác biệt hoàn toàn
  (edge-tts là local SDK streaming, LucyAI là REST JSON-RPC + polling), gộp
  chung sẽ làm hàm khó đọc; giữ 2 module riêng, thêm 1 lớp dispatch mỏng ở
  `pipeline.py` (xem §4) rõ ràng hơn.

## 3. Cơ chế "nghe thử" (preview) — không tạo job

- **Decision**: Thêm 2 endpoint mới trong `web/backend`:
  - `GET /api/voices`: trả danh sách gộp `[{"provider", "voice_id", "name"}]`
    từ edge-tts (luôn có) + LucyAI (`list_voices()` nếu
    `VIVIBE_API_KEY` đã cấu hình, lỗi thì trả mảng rỗng cho phần LucyAI, log
    warning, KHÔNG làm fail cả endpoint — FR-003).
  - `POST /api/voices/preview`: body `{"provider", "voice_id"}`, dùng 1 câu
    mẫu tiếng Việt cố định (FR-005) gọi đúng `synthesize()` của provider
    tương ứng, stream WAV kết quả thẳng về response (không ghi vào
    `jobs/`), xoá file tạm ngay sau khi response xong.
- **Câu mẫu cố định**: `"Xin chào, đây là giọng đọc mẫu để bạn tham khảo
  trước khi chọn."` — đủ ngắn (~13 từ) để edge-tts/LucyAI xử lý nhanh (khớp
  SC-002 ≤10s, đúng khuyến nghị docs LucyAI "~200 ký tự xử lý trong 2-5s").
- **Rationale**: Preview không phải 1 "job" theo nghĩa `jobs/{job_id}/` (không
  có source video, không qua pipeline 6 bước) — tách hẳn khỏi
  `pipeline.create_job()`/`run_pipeline()` để không vi phạm rule "chỉ 1 job
  tại 1 thời điểm" (FR-008 của spec.md, đã xác nhận đúng ý đồ).
- **Alternatives considered**: Cho người dùng tự nhập text nghe thử — loại bỏ
  ở bước specify (rủi ro tốn quota LucyAI không kiểm soát được, xem
  spec.md → Assumptions).

## 4. Dispatch provider trong pipeline.py (mở rộng bước synthesizing)

- **Decision**: Bước `synthesizing` của `pipeline.py` rẽ nhánh theo
  `job["tts_provider"]` (mặc định `"edge-tts"` nếu job cũ trước feature này
  không có field — dùng `.get()`), gọi đúng `edge_tts_client.synthesize()`
  hoặc `lucyai_client.synthesize()` với `voice_id = job["voice_id"]`. Cả 2
  nhánh đều trả về `(voice_path, duration)` cùng shape để phần còn lại của
  bước (update job status, log) không đổi.
- **Khớp thời lượng (duration-matching, đã có từ 003 US2) cho LucyAI**: Áp
  dụng đúng tinh thần 2-pass đã có ở edge-tts — sinh lần 1 ở `speed=1.0`, nếu
  lệch > ngưỡng thì tính `speed` mới trong khoảng `[0.5, 2.0]` (giới hạn của
  LucyAI, hẹp hơn edge-tts) rồi sinh lại lần 2. KHÔNG áp dụng cơ chế
  `dynamic_captions` (US4/003, dựa vào `SentenceBoundary` riêng của
  edge-tts) cho LucyAI ở bản này — nếu người dùng chọn LucyAI + bật phụ đề
  động, hệ thống bỏ qua caption kèm cảnh báo rõ (tái dùng đúng cơ chế
  graceful-degrade đã có ở US4/003 khi burn lỗi), KHÔNG chặn job. Lý do
  ngoài phạm vi: LucyAI trả `srtUrl` (định dạng/độ chi tiết khác hẳn
  `SentenceBoundary`), cần thiết kế riêng không thuộc scope của feature 004.
- **Rationale**: Tái dùng tối đa kiến trúc 2-pass đã verify kỹ ở 003 thay vì
  viết cơ chế khớp thời lượng hoàn toàn mới cho LucyAI.

## 5. Mở rộng CLI

- **Decision**: Thêm `--tts-provider {edge-tts,lucyai}` (mặc định
  `edge-tts`) và `--voice-id <id>` (mặc định giọng edge-tts hiện tại nếu bỏ
  trống) vào `pipeline.py`.
- **Rationale**: Nhất quán với cách `--dynamic-captions` được thêm ở 003 —
  CLI và web UI dùng chung 1 cơ chế qua `run_pipeline()`.

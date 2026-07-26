# Quickstart Validation: Chọn giọng đọc & nghe thử trước khi chạy job

Yêu cầu: đã build lại Docker image sau khi thêm `tts/lucyai_client.py` +
`VIVIBE_API_KEY` vào `.env.example`. Phần verify LucyAI thật cần
`VIVIBE_API_KEY` thật của người dùng — nếu chưa có, chỉ verify được phần
edge-tts + graceful-degrade (xem ghi chú ở mỗi bước).

## US1 — Chọn giọng đọc trước khi chạy job

1. Gọi `GET /api/voices` (hoặc mở form web) — xác nhận thấy ≥2 giọng
   edge-tts. Nếu đã có `VIVIBE_API_KEY`, xác nhận thấy thêm giọng LucyAI.
2. Chạy 1 job `--script-mode translate --voice-id vi-VN-HoaiMyNeural` (khác
   giọng mặc định) — nghe `output.mp4`, xác nhận đúng giọng nữ (HoaiMy), ghi
   nhận cảm quan/so sánh với giọng nam mặc định.
3. **[Cần VIVIBE_API_KEY thật]** Lặp lại với `--tts-provider lucyai
   --voice-id <id từ getUserVoices>` — xác nhận job thành công, giọng đúng
   như chọn.
4. Chạy 1 job `--tts-provider lucyai --voice-id <id không tồn tại hoặc key
   sai>` — xác nhận job fail rõ ràng ở bước `synthesizing`, không âm thầm
   dùng edge-tts (FR-007).

**Pass**: Cả 4 bước đúng (bước 3 có thể bỏ qua nếu chưa có key thật, ghi rõ
lý do khi báo cáo).

## US2 — Nghe thử giọng đọc

1. Gọi `POST /api/voices/preview` với 1 giọng edge-tts — xác nhận nhận được
   audio WAV hợp lệ trong dưới 10 giây (SC-002), nghe đúng câu mẫu cố định.
2. **[Cần VIVIBE_API_KEY thật]** Lặp lại với 1 giọng LucyAI — xác nhận nhận
   được audio trong dưới 10 giây.
3. Xác nhận `jobs/` KHÔNG có thư mục mới nào sinh ra sau bước 1-2 (FR-008 —
   preview không tạo job).
4. Trong lúc có 1 job khác đang chạy (`downloading`/`transcribing`/...), gọi
   `POST /api/voices/preview` — xác nhận vẫn trả `200 OK`, không bị chặn bởi
   409 "đang có job xử lý".

**Pass**: Bước 1, 3, 4 đúng bắt buộc; bước 2 verify khi có key thật.

## Web UI

Lặp lại US1/US2 qua form thật ở `HomePage` (dropdown chọn giọng + nút nghe
thử cạnh mỗi giọng) — kỳ vọng hành vi giống hệt gọi API trực tiếp.

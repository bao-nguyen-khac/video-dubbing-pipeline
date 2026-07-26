# Quickstart Validation: Sửa lỗi lồng tiếng & thêm phụ đề tự động, phụ đề động

Yêu cầu: đã build lại Docker image (`docker compose build`) sau khi thêm
`torchcodec` vào `requirements.txt` (US1) — nếu chưa rebuild, US1/US4 sẽ vẫn
lỗi vì image cũ thiếu dependency.

## US1 — Giữ nhạc nền gốc

1. Chạy 1 job `--script-mode translate` và 1 job `--script-mode rewrite` với
   cùng 1 video nguồn có nhạc nền rõ (VD nhạc trend TikTok).
2. Nghe `output.mp4` của cả 2 job — xác nhận nhạc nền còn nghe được song song
   giọng đọc mới.
3. Kiểm tra `job.json.warnings.background_music_lost == false` cho cả 2 job.

**Pass**: Cả 3 bước trên đúng cho ≥ 1 video test có nhạc nền thật.

## US2 — Khớp thời lượng ở chế độ Sáng tạo

1. Chạy 1 job `--script-mode rewrite` với video nguồn đã biết thời lượng
   (VD dùng `ffprobe`/`media_utils.get_media_duration`).
2. So sánh `duration_seconds` của `voice.wav` với thời lượng `source.mp4`.

**Pass**: Lệch ≤ 10% (SC-002 của spec.md) cho ≥ 90% số job test (chạy nhiều
video mẫu khác nhau); `job.json.warnings.duration_mismatch` phản ánh đúng khi
vẫn còn lệch vượt ngưỡng cũ (3s, ngưỡng cảnh báo của `ffmpeg_merge.py`).

## US3 — Phụ đề tự động

1. Chạy 1 job `--script-mode subtitle` với video có lời thoại rõ.
2. Xác nhận `job.json.artifacts.voice_track == null` (không có bước TTS).
3. Nghe `output.mp4` — âm thanh giống hệt `source.mp4` gốc (không có giọng
   đọc mới).
4. Xem `output.mp4` — phụ đề chữ Việt hiện ở góc dưới, đúng thời điểm lời
   thoại gốc tương ứng được nói.

**Pass**: Cả 4 bước đúng; job với video không có lời thoại phải fail rõ ràng
ở bước `scripting` với thông điệp lỗi dễ hiểu (Acceptance Scenario 3, US3).

## US4 — Phụ đề động khớp nhịp giọng đọc

1. Chạy 1 job `--script-mode translate --dynamic-captions` (hoặc `rewrite`).
2. Xem `output.mp4` — chữ kịch bản hiện theo từng câu/cụm, đúng lúc giọng đọc
   bắt đầu đọc câu đó.
3. Dùng timestamp trong `jobs/{job_id}/captions.json` so với việc nghe thực
   tế — lệch ≤ 1 giây (SC-004 của spec.md).

**Pass**: Chữ xuất hiện đúng nhịp cho ≥ 1 job test mỗi chế độ (translate và
rewrite).

## Web UI (nếu test qua 002-web-ui thay vì CLI trực tiếp)

Lặp lại 4 kịch bản trên qua form ở `HomePage` sau khi frontend đã thêm option
`script_mode = "Phụ đề tự động"` và checkbox `dynamic_captions` (xem
[contracts/api.md](contracts/api.md)) — kỳ vọng hành vi giống hệt CLI, chỉ
khác cách khởi tạo job.

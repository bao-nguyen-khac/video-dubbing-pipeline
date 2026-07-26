# Phase 0 Research: Video Repurpose Pipeline

Không còn `NEEDS CLARIFICATION` nào trong Technical Context — toàn bộ lựa chọn công
nghệ đã được khoá ở `.specify/memory/constitution.md` (v1.1.0) qua nhiều vòng research
trước đó trong quá trình lên plan. Tài liệu này tổng hợp lại quyết định + lý do +
phương án đã cân nhắc để Antigravity (agent thực thi code) có đủ ngữ cảnh mà không
cần đọc lại hội thoại gốc (Constitution Principle IV).

## Download: Douyin/TikTok/YouTube

**Decision**: `f2` (Johnserf-Seed) làm engine chính cho Douyin + TikTok; `yt-dlp`
làm fallback cho YouTube và các nguồn f2 không hỗ trợ.

**Rationale**: f2 lấy trực tiếp link watermark-free từ API gốc của Douyin/TikTok,
độ ổn định với Douyin cao hơn yt-dlp (extractor Douyin của yt-dlp hay gãy do
platform đổi API). yt-dlp vẫn cần thiết vì hỗ trợ 1800+ site bao gồm YouTube, dùng
làm lưới an toàn.

**Alternatives considered**:
- yt-dlp làm engine chính cho tất cả nguồn — bị loại vì Douyin extractor kém ổn
  định hơn (xem GitHub issue yt-dlp #9557).
- TikTokApi (davidteather) — chỉ chuyên TikTok, không cover Douyin, bị loại để
  tránh phải quản lý 3 thư viện tải riêng biệt.

## Cleanup watermark/hardsub

**Decision**: `video-subtitle-remover` (YaoFANGUK) khai báo dependency nhưng CHƯA
wiring đầy đủ trong feature này — MVP chỉ có bước `detector.py` log cảnh báo khi
nghi ngờ còn watermark/hardsub, không tự động chạy AI inpainting.

**Rationale**: Theo spec Assumptions, watermark burn-cứng không phải trường hợp
phổ biến với nguồn ưu tiên (f2 lấy bản sạch trực tiếp từ API); tích hợp AI
inpainting tốn GPU và làm chậm luồng chính — vi phạm Token & Context Economy nếu
làm ngay khi chưa có nhu cầu xác nhận. Đây là task hoãn lại rõ ràng, không phải bị
bỏ quên.

**Alternatives considered**: Tích hợp ngay từ US1 — bị loại vì tăng độ phức tạp và
compute requirement (GPU) cho một trường hợp hiếm ở nguồn ưu tiên.

## ASR / Transcript

**Decision**: `faster-whisper` (model size mặc định: `small` hoặc `medium`, chạy
CPU).

**Rationale**: Nhanh hơn Whisper gốc ~4x, đủ nhẹ để chạy CPU không cần GPU (đúng
Constraints — "không yêu cầu GPU cho luồng mặc định").

**Alternatives considered**: WhisperX (word-level timestamp + diarization) — hoãn
lại vì US1 MVP không cần đồng bộ thời lượng chính xác từng từ (edge case này đã ghi
nhận trong spec, xử lý ở iteration sau).

## Script generation (dịch / tự soạn)

**Decision**: Gọi 9router qua SDK `openai` Python, `base_url="http://localhost:20128/v1"`.
Hai mode: `translate` (dịch transcript gốc) và `rewrite` (tự soạn kịch bản mới dựa
trên ý chính), chọn qua tham số CLI theo FR-004.

**Rationale**: 9router đã có sẵn (do người dùng cung cấp), expose OpenAI-compatible
endpoint nên tích hợp bằng SDK chuẩn, không cần viết client riêng.

**Alternatives considered**: Gọi thẳng OpenAI/Claude API — bị loại vì người dùng đã
có 9router làm lớp routing/fallback riêng, dùng thẳng sẽ trùng lặp hạ tầng.

## TTS (giọng đọc)

**Decision**: `edge-tts`, giọng mặc định `vi-VN-NamMinhNeural` (có thể cấu hình đổi
sang `vi-VN-HoaiMyNeural`).

**Rationale**: Free, không cần GPU, setup nhanh — đúng lựa chọn đã chốt cho giai
đoạn hiện tại (constitution Technology Stack). VietTTS (voice cloning tự nhiên hơn,
"Adam-like") là hướng nâng cấp sau, không bắt buộc cho MVP.

**Alternatives considered**: VietTTS ngay từ MVP — hoãn lại vì cần setup Docker +
GPU để đạt tốc độ chấp nhận được, tăng effort setup ban đầu không cần thiết cho mục
tiêu chứng minh pipeline hoạt động end-to-end trước.

## Merge video

**Decision**: `ffmpeg` gọi qua `subprocess` (hoặc wrapper `ffmpeg-python` nếu cần
compose filter phức tạp hơn).

**Rationale**: Chuẩn công nghiệp, ổn định, kiểm soát tốt nhất so với MoviePy.

**Alternatives considered**: MoviePy — bị loại vì chậm hơn và thêm một lớp trừu
tượng không cần thiết khi ffmpeg CLI/subprocess đã đủ dùng.

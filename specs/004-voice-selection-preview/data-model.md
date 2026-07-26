# Phase 1 Data Model: Chọn giọng đọc & nghe thử trước khi chạy job

Kế thừa entity đã có ở
[001](../001-video-repurpose-pipeline/data-model.md)/[003](../003-dubbing-fixes-subtitles/data-model.md).
File này chỉ liệt kê phần mở rộng.

## Voice (entity mới — không lưu trữ, tổng hợp động)

| Field | Type | Ghi chú |
|---|---|---|
| `provider` | enum: `edge-tts`, `lucyai`, `router-tts` | Nguồn giọng. Nhãn hiển thị: `lucyai` → "Vivibe" (research.md §2), `router-tts` → "9router" |
| `voice_id` | string | edge-tts: `ShortName` (VD `vi-VN-NamMinhNeural`). LucyAI: `id` trả về từ `getUserVoices`. router-tts: tên giọng Gemini cố định (VD `Puck`) |
| `name` | string | Tên hiển thị. edge-tts: `FriendlyName`. LucyAI: `name`. router-tts: trùng `voice_id` (không có tên riêng khác) |

Không có bảng lưu trữ riêng — `GET /api/voices` tổng hợp trực tiếp từ
`edge_tts.list_voices()` (lọc `vi-`), `lucyai_client.list_voices()` (nếu đã
cấu hình `VIVIBE_API_KEY`), và `router_tts_client.list_voices()` (danh sách
30 giọng Gemini cố định, luôn hiện nếu `ROUTER_API_KEY` đã cấu hình — vốn đã
cần cho `script_gen`) tại thời điểm request.

## Job (mở rộng)

| Field | Type | Ghi chú |
|---|---|---|
| `tts_provider` | enum: `edge-tts`, `lucyai`, `router-tts` | **Mới**. Mặc định `edge-tts` (backward-compatible với job cũ, đọc qua `.get()`). Chỉ có ý nghĩa khi `script_mode` là `translate`/`rewrite` |
| `voice_id` | string | **Mới**. Mặc định giọng edge-tts hiện tại (`vi-VN-NamMinhNeural`) nếu không chọn. Voice cụ thể dùng khi sinh `voice.wav` |

## Voice Track (mở rộng, xem data-model.md của 001)

| Field | Type | Ghi chú |
|---|---|---|
| `provider` | enum: `edge-tts`, `lucyai`, `router-tts` | Trùng `Job.tts_provider` — ghi lại để audit đúng job đã dùng provider nào (Constitution Principle VI) |
| `rate_adjustment` | string \| float | edge-tts: chuỗi `rate` kiểu `+12%` (không đổi so với 001/003). LucyAI: số `speed` trong `[0.5, 2.0]` — khác kiểu dữ liệu theo provider, xem research.md §4 |

## Relationships

Không đổi cấu trúc quan hệ so với 001/003 — `Voice` không phải entity có
quan hệ với `Job` qua khoá lưu trữ, chỉ là input người dùng chọn ở thời điểm
submit (`tts_provider` + `voice_id` ghi thẳng vào `Job`).

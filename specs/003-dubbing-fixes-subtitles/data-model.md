# Phase 1 Data Model: Sửa lỗi lồng tiếng & thêm phụ đề tự động, phụ đề động

Kế thừa toàn bộ entity ở
[data-model.md của 001-video-repurpose-pipeline](../001-video-repurpose-pipeline/data-model.md).
File này chỉ liệt kê phần **mở rộng/thay đổi** cho feature 003 — không định
nghĩa lại field đã có nếu không đổi.

## Job (mở rộng)

| Field | Type | Ghi chú |
|---|---|---|
| `script_mode` | enum: `translate`, `rewrite`, `subtitle` | **Mở rộng thêm giá trị `subtitle`** (US3) — vẫn cùng 1 field, không đổi tên (research.md §5). `subtitle` = giữ nguyên âm thanh gốc, chỉ thêm phụ đề. |
| `dynamic_captions` | bool | **Mới** (US4). Mặc định `false`. Chỉ có ý nghĩa khi `script_mode` là `translate`/`rewrite`; bật thì video sản phẩm có thêm phụ đề động khớp nhịp giọng đọc (research.md §6). Với `script_mode = subtitle`, field này không áp dụng (phụ đề đã luôn bật ở mode đó). |
| `warnings.background_music_lost` | bool | Không đổi field, nhưng ngữ nghĩa "lệch" hiện tại đã root-cause được và có fix (US1) — kỳ vọng còn `true` chỉ ở trường hợp video nguồn thực sự không tách được nhạc nền (edge case), không còn xảy ra mặc định mọi job. |
| `warnings.duration_mismatch` | bool | Không đổi field; kỳ vọng false-rate giảm sau khi áp dụng ngân sách ký tự ở US2 (SC-002 của spec này). |

## Script (mở rộng)

| Field | Type | Ghi chú |
|---|---|---|
| `content` | string | Không đổi — vẫn 1 khối văn bản dùng để sinh Voice Track (translate/rewrite). Với `script_mode = subtitle`, field này KHÔNG dùng để TTS (không có Voice Track), chỉ tồn tại cho tương thích cấu trúc; nội dung phụ đề nằm ở Subtitle Track riêng (bên dưới). |
| `target_char_budget` | int \| null | **Mới** (US2). Ngân sách số ký tự mục tiêu tính từ `source_duration` × tốc độ đọc trung bình của voice edge-tts đang dùng, đưa vào prompt LLM (research.md §2). Chỉ áp dụng cho `translate`/`rewrite`; `null` với `subtitle`. |
| `segments` | list[{start, end, source_text, translated_text}] \| null | **Mới** (US3). Chỉ có khi `script_mode = subtitle` — dịch sát nghĩa theo từng ASR segment, giữ nguyên `start`/`end` gốc (research.md §3). `null` với `translate`/`rewrite`. |

## Voice Track (mở rộng)

| Field | Type | Ghi chú |
|---|---|---|
| `word_boundaries` | list[{start, end, text}] \| null | **Mới** (US4). Chỉ sinh khi `Job.dynamic_captions = true` — gom từ sự kiện `WordBoundary` của `edge-tts` theo ranh giới câu/cụm (research.md §4, Clarification Q1 của spec: đơn vị câu/cụm, không phải từng từ). `null` nếu `dynamic_captions = false` hoặc `script_mode = subtitle` (không có Voice Track). |
| `word_boundaries_path` | string \| null | `jobs/{job_id}/captions.json` — lưu ra đĩa ngay trong bước synthesizing để bước merging (và resume sau lỗi) dùng lại được mà không phải chạy lại TTS. |

## Subtitle Track (entity mới, dùng chung cho US3 và US4)

Danh sách cue phụ đề kèm mốc thời gian, dùng để sinh file SRT/ASS rồi burn-in
vào Output Video bằng bộ lọc `subtitles` của ffmpeg (research.md §3, §4).
Không phải track lưu trữ độc lập trong `job.json` — sinh ra từ `Script.segments`
(US3) hoặc `Voice Track.word_boundaries` (US4) tại thời điểm merge.

| Field | Type | Ghi chú |
|---|---|---|
| `cues` | list[{start: float, end: float, text: string}] | Mốc thời gian tính bằng giây, tương đối so với đầu Output Video. |
| `source` | enum: `subtitle_mode`, `dynamic_captions` | Phân biệt cue này sinh từ US3 (khớp audio gốc) hay US4 (khớp giọng TTS mới) — quyết định input dữ liệu (`Script.segments` hay `Voice Track.word_boundaries`) nhưng cùng chung cơ chế burn-in ở bước merge. |
| `file_path` | string | `jobs/{job_id}/subtitles.srt` — file trung gian ghi ra đĩa trước khi burn-in, giữ đúng nguyên tắc audit-trail (Constitution Principle VI). |

## Output Video (mở rộng)

| Field | Type | Ghi chú |
|---|---|---|
| `subtitles_burned` | bool | **Mới**. True nếu Output Video có phụ đề đã burn-in (US3 luôn true khi `script_mode = subtitle`; US4 true khi `dynamic_captions = true` và burn thành công). |
| `background_music_kept` | bool | Không đổi field — kỳ vọng thực tế đúng với ý nghĩa field (US1 fix), không còn luôn `false`. |
| `audio_source` | enum: `original`, `tts_mixed` | **Mới**. `original` khi `script_mode = subtitle` (audio gốc giữ nguyên 100%, không qua TTS/tách nhạc); `tts_mixed` khi `translate`/`rewrite` (voice mới + nhạc nền tách được, như 001). |

## State Machine (không đổi cấu trúc, chỉ rẽ nhánh hành vi theo `script_mode`)

```text
pending → downloading → transcribing → scripting → synthesizing → merging → done
                                                                            ↘ failed (từ bất kỳ bước nào)
```

- `script_mode = translate | rewrite` (như 001, có mở rộng US1/US2/US4):
  - `synthesizing`: sinh Voice Track như cũ; nếu `dynamic_captions = true`, đồng
    thời thu `word_boundaries` từ `edge-tts` (research.md §4).
  - `merging`: tách/giữ nhạc nền (US1 đã fix), ghép voice+nhạc nền; nếu
    `dynamic_captions = true`, burn thêm Subtitle Track sinh từ
    `word_boundaries` lên trên kết quả ghép.
- `script_mode = subtitle` (US3, mới hoàn toàn):
  - `scripting`: dịch theo từng ASR segment (không dịch nguyên khối), ghi
    `Script.segments`.
  - `synthesizing`: **bỏ qua hoàn toàn** (không TTS, không tách nhạc nền) —
    `artifacts.voice_track` giữ `null` có chủ đích, chuyển thẳng sang
    `merging`.
  - `merging`: sinh Subtitle Track từ `Script.segments`, burn-in lên video
    gốc, audio giữ nguyên 100% (map thẳng audio stream gốc, không qua
    ffmpeg amix).

## Relationships (cập nhật)

```text
Job (1) ── (1) Source Video ── (1) Script ──┬── (1) Voice Track ── (1) Background Audio ──┐
                                             │                                              ├── (1) Output Video
                                             └── (0..1) Subtitle Track ─────────────────────┘
```

`Subtitle Track` là 0..1 vì chỉ tồn tại khi `script_mode = subtitle` hoặc
`dynamic_captions = true`; các trường hợp còn lại giữ đúng quan hệ tuyến tính
1-1 như 001.

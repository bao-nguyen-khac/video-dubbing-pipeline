# Data Model: Lồng tiếng khớp nhịp tự nhiên theo từng câu (005)

**Phase 1 output** — mô tả các entity bị đổi/thêm so với 001/003/004. Chỉ ghi
phần **khác biệt**; field không nhắc tới = giữ nguyên như feature trước.

## 1. Dubbing Unit (đơn vị lồng tiếng — khái niệm mới, in-memory)

Kết quả của bước gom ASR segment (research.md §1). Không phải file riêng —
được vật chất hoá trong `script.json.segments` và `voice_timeline.json`.

| Field | Kiểu | Mô tả |
|---|---|---|
| `index` | int | Thứ tự trong job, bắt đầu từ 0 |
| `start` | float | Mốc bắt đầu (giây) của segment ASR đầu tiên trong unit |
| `end` | float | Mốc kết thúc (giây) của segment ASR cuối cùng trong unit |
| `source_text` | str | Text gốc, nối từ các ASR segment con bằng khoảng trắng |

**Ràng buộc**:
- `end > start`; các unit không chồng lấn và sắp xếp tăng dần theo `start`.
- `_MAX_UNIT_DURATION = 15.0` giây chỉ **chặn việc gộp thêm**, không cắt nhỏ:
  1 ASR segment đơn lẻ vốn đã dài hơn 15s vẫn thành 1 unit dài hơn 15s
  (`group_segments()` chỉ gộp, không tách).
- 2 unit liền nhau cách nhau ≥ `0.30` giây (`_GAP_SILENCE_THRESHOLD`) — khoảng
  trống nhỏ hơn đã bị gộp vào cùng unit. Ngoại lệ duy nhất: gộp bị chặn vì
  vượt `_MAX_UNIT_DURATION`.

## 2. Script (`jobs/{job_id}/script.json`) — MỞ RỘNG

Mode `translate`/`rewrite` nay có thêm mảng `segments` với **cùng shape** như
mode `subtitle` đã có ở 003 (một shape duy nhất cho cả 3 mode):

```json
{
  "mode": "translate",
  "content": "Bản dịch câu 1 Bản dịch câu 2 ...",
  "target_language": "vi",
  "segments": [
    {
      "start": 0.0,
      "end": 3.24,
      "source_text": "原文 ...",
      "translated_text": "Bản dịch/viết lại của nhịp này"
    }
  ]
}
```

| Thay đổi | Chi tiết |
|---|---|
| `segments` | **MỚI với `translate`/`rewrite`** — bắt buộc, đúng 1 phần tử/dubbing unit, cùng thứ tự. Với `subtitle` giữ nguyên như 003 (1 phần tử/ASR segment, không gom). |
| `content` | Vẫn ghi (nối `translated_text` bằng khoảng trắng) nhưng **không còn là input của TTS** — chỉ để đọc/debug. Mode `subtitle` vẫn để `""` như 003. |

**Ràng buộc**: `len(segments)` phải bằng số dubbing unit sinh từ
`transcript.json`; lệch → `RuntimeError` ở bước scripting (không ghép đoán).

**Resume**: `script.json` của `translate`/`rewrite` **thiếu `segments`** bị coi
là không hợp lệ và sinh lại (research.md §7).

## 3. Voice Timeline (`jobs/{job_id}/voice_timeline.json`) — FILE MỚI

Bản ghi vị trí thời gian **thực tế** của từng unit trong `voice.wav` sau khi
ghép. Là nguồn duy nhất cho `captions.json` (FR-011) và cho resume bước TTS.

```json
{
  "total_duration": 58.42,
  "failed_count": 1,
  "segments": [
    {
      "index": 0,
      "source_start": 0.0,
      "source_end": 3.24,
      "start": 0.0,
      "end": 3.51,
      "text": "Bản dịch nhịp này",
      "tempo": 1.12,
      "status": "ok"
    }
  ]
}
```

| Field | Kiểu | Mô tả |
|---|---|---|
| `source_start` / `source_end` | float | Khung thời gian gốc của unit (từ ASR) |
| `start` / `end` | float | Vị trí **thực tế** trong `voice.wav`; `start = max(source_start, end_của_unit_trước)` (FR-009) |
| `tempo` | float | Hệ số `atempo` đã áp, luôn trong `[1.0, 1.4]`; `1.0` = không chỉnh |
| `status` | `"ok"` \| `"failed"` | `"failed"` = TTS lỗi sau 2 lần thử, đoạn này là khoảng lặng dài `source_end - source_start` (FR-006) |
| `failed_count` | int | Số unit `status="failed"`; `== len(segments)` → job phải fail (không ghi file) |

**Ràng buộc**: `segments[i].start ≥ segments[i-1].end` (không chồng lấn, có thể
bằng khi tràn liên tiếp). `total_duration ≥ segments[-1].end`.

## 4. Voice Track (`jobs/{job_id}/voice.wav`) — ĐỔI CÁCH SINH

| | Trước (001/003/004) | Sau (005) |
|---|---|---|
| Số lượt gọi TTS | 1 lượt cho cả kịch bản | 1 lượt/dubbing unit (+ tối đa 1 lần thử lại/unit) |
| Khớp thời lượng | 1 lần cho toàn bộ, cả tăng lẫn giảm tốc | Từng unit, **chỉ tăng tốc**, `tempo ∈ [1.0, 1.4]` |
| Khoảng lặng | Không có (TTS đọc liền mạch) | Khoảng lặng thật giữa các unit, sinh bằng stdlib `wave` |
| Format | Tuỳ provider | Chuẩn hoá `44100 Hz / 2 kênh / pcm_s16le` cho mọi unit trước khi concat |

**File trung gian mới**: `jobs/{job_id}/segments/unit_{index:04d}.wav` (audio
từng unit đã chuẩn hoá + đã `atempo`) và `.../silence_{index:04d}.wav`. Cho
phép resume bước `synthesizing` mà không gọi lại provider cho unit đã xong.

## 5. Caption Track (`jobs/{job_id}/captions.json`) — ĐỔI NGUỒN

Shape **không đổi** so với 003 (`[{start, end, text}]`, giây) — chỉ đổi nguồn
sinh:

| | Trước (003) | Sau (005) |
|---|---|---|
| Nguồn | `SentenceBoundary` streaming của edge-tts | `voice_timeline.json` (`start`/`end`/`text` của unit `status="ok"`) |
| Provider hỗ trợ | Chỉ chính xác với edge-tts | Cả 3 provider, cùng độ chính xác (FR-011) |

## 6. Job (`jobs/{job_id}/job.json`) — MỞ RỘNG

| Field | Kiểu | Mô tả |
|---|---|---|
| `warnings.tts_segments_failed` | bool | **MỚI**, mặc định `false`. `true` khi có ≥1 unit lỗi TTS bị thay bằng khoảng lặng (FR-007). Độc lập hoàn toàn với `warnings.duration_mismatch`. |
| `tts_failed_segments` | int | **MỚI** (top-level, ghi qua `extra_update` như `subtitles_burned` của 003), mặc định `0`. Số unit lỗi — để UI nói rõ "N câu" thay vì chỉ "có câu lỗi". |
| `artifacts.voice_timeline` | str \| null | **MỚI** — đường dẫn `voice_timeline.json`. `null` với `script_mode="subtitle"`. |

**State machine**: KHÔNG đổi (`pending → downloading → transcribing →
scripting → synthesizing → merging → done/failed`). Lỗi TTS cục bộ không tạo
trạng thái mới — job vẫn đi tiếp sang `merging`.

**`status_from_artifacts()`**: không đổi — `voice_track` vẫn là mốc suy ra
bước `synthesizing`; `voice_timeline` luôn được ghi cùng lúc với `voice.wav`.

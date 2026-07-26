# API Contract — bổ sung của feature 005

Phần mở rộng của [`specs/002-web-ui/contracts/api.md`](../../002-web-ui/contracts/api.md)
và [`specs/003-dubbing-fixes-subtitles/contracts/api.md`](../../003-dubbing-fixes-subtitles/contracts/api.md).
Chỉ ghi phần **khác biệt**.

## 1. Endpoint: KHÔNG thêm/xoá/đổi đường dẫn

`POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`,
`GET /api/jobs/{id}/output`, `POST /api/jobs/{id}/retry`,
`GET /api/voices`, `POST /api/voices/preview` — giữ nguyên.

## 2. `POST /api/jobs` — request KHÔNG đổi

```json
{
  "url": "https://...",
  "script_mode": "translate",
  "dynamic_captions": true,
  "tts_provider": "router-tts",
  "voice_id": "Puck"
}
```

`dynamic_captions` nay cho phụ đề chính xác với **mọi** `tts_provider` (trước
chỉ chính xác với `edge-tts`) — không đổi schema, chỉ đổi chất lượng kết quả.

## 3. `GET /api/jobs/{id}` — response MỞ RỘNG

```json
{
  "job_id": "…",
  "status": "done",
  "progress_percent": 100,
  "script_mode": "translate",
  "dynamic_captions": true,
  "subtitles_burned": true,
  "tts_failed_segments": 1,
  "warnings": {
    "watermark": false,
    "duration_mismatch": false,
    "background_music_lost": false,
    "tts_segments_failed": true
  },
  "output_video_url": "/api/jobs/…/output",
  "can_retry": false,
  "error": null
}
```

| Field | Kiểu | Ghi chú |
|---|---|---|
| `warnings.tts_segments_failed` | bool | **MỚI** — `true` khi ≥1 nhịp bị thay bằng khoảng lặng do lỗi TTS (FR-007). Độc lập với `duration_mismatch`: một job có thể bật cái này mà không bật cái kia và ngược lại. |
| `tts_failed_segments` | int | **MỚI** — số nhịp lỗi (0 khi không có). Trả về ở top-level, cùng cách với `subtitles_burned` của 003. |

`warnings` được trả nguyên vẹn từ `job.json` (`jobs_api.py` đang dùng
`job.get("warnings", {})`) → key mới tự động xuất hiện, không đổi logic
serialize.

## 4. Hành vi status khi lỗi TTS cục bộ — ĐỔI

| Tình huống | Trước | Sau |
|---|---|---|
| 1 nhịp lỗi TTS (các nhịp khác OK) | `status="failed"`, `can_retry=true`, không có video | `status="done"`, có `output_video_url`, kèm `warnings.tts_segments_failed=true` (FR-006, SC-003) |
| Toàn bộ nhịp lỗi TTS | `status="failed"` | `status="failed"` (không đổi) |

## 5. Frontend — hiển thị cảnh báo mới

`web/frontend/src/api/client.ts`:

```ts
export interface JobDetail extends JobSummary {
  // …
  tts_failed_segments: number;            // MỚI
  warnings: {
    watermark?: boolean;
    duration_mismatch?: boolean;
    background_music_lost?: boolean;
    tts_segments_failed?: boolean;        // MỚI
  };
}
```

`web/frontend/src/pages/JobDetailPage.tsx` — `WARNING_LABELS` thêm khoá mới;
nhãn phải nêu rõ đây là lỗi **cục bộ** để người dùng phân biệt với lỗi toàn
phần (FR-007, US3 scenario 2), và chèn được số lượng khi có:

```
tts_segments_failed:
  "{n} câu không tổng hợp được giọng đọc, đã thay bằng khoảng lặng —
   phần còn lại của video vẫn có lồng tiếng bình thường"
```

Không thêm component/trang mới: tận dụng đúng khối `Cảnh báo chất lượng` đã
render `activeWarnings` sẵn có.

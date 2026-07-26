# Contract: Job State Schema (`jobs/{job_id}/job.json`)

Đây là "API nội bộ" giữa các module trong pipeline (downloader → asr → script_gen →
tts → merge) — mỗi module đọc/ghi vào cùng 1 file `job.json` theo schema này thay vì
truyền tham số trực tiếp cho nhau, để đảm bảo Constitution Principle VI (truy vết
được qua file trung gian).

## Schema

```json
{
  "job_id": "string (UUID)",
  "source_url": "string",
  "platform": "tiktok | douyin | youtube",
  "script_mode": "translate | rewrite",
  "status": "pending | downloading | transcribing | scripting | synthesizing | merging | done | failed",
  "error": "string | null",
  "artifacts": {
    "source_video": "jobs/{job_id}/source.mp4 | null",
    "transcript": "jobs/{job_id}/transcript.json | null",
    "script": "jobs/{job_id}/script.json | null",
    "voice_track": "jobs/{job_id}/voice.wav | null",
    "background_audio": "jobs/{job_id}/background.wav | null",
    "output_video": "jobs/{job_id}/output.mp4 | null"
  },
  "warnings": {
    "watermark": "boolean",
    "duration_mismatch": "boolean",
    "background_music_lost": "boolean"
  },
  "created_at": "ISO 8601 datetime",
  "updated_at": "ISO 8601 datetime"
}
```

## Rules

- Mỗi module CHỈ được cập nhật field thuộc trách nhiệm của mình rồi ghi đè
  `job.json` (đọc → sửa → ghi, không patch từng phần qua nhiều tiến trình song
  song — MVP xử lý tuần tự, không cần lock).
- `status` chỉ được tiến theo state machine ở [data-model.md](../data-model.md#job)
  — module downstream MUST kiểm tra `status` hợp lệ trước khi chạy (VD: `asr`
  không chạy nếu `status != downloading` sau khi download xong).
- Khi một module lỗi: set `status = failed`, ghi `error` mô tả rõ bước + nguyên
  nhân, KHÔNG xoá các field `artifacts` đã có giá trị từ bước trước (FR-007).
- File tương ứng trong `artifacts` (VD: `transcript.json`, `script.json`) MUST tồn
  tại trên đĩa nếu field đó khác `null` — đây là điều kiện để `--job-id` resume
  hoạt động đúng (xem contracts/cli.md → Idempotency).

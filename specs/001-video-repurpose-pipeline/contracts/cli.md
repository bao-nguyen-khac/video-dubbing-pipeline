# Contract: CLI Interface

`pipeline.py` là entrypoint duy nhất của feature này (không có REST API/web UI ở
MVP — xem spec Assumptions).

## Command

```bash
python pipeline.py \
  --url <video_url> \
  --script-mode <translate|rewrite> \
  [--job-id <existing_job_id>]
```

## Arguments

| Arg | Required | Values | Ghi chú |
|---|---|---|---|
| `--url` | Yes | URL công khai từ TikTok, Douyin, hoặc YouTube | FR-001 |
| `--script-mode` | Yes | `translate` \| `rewrite` | FR-004 |
| `--job-id` | No | UUID string | Dùng để resume/xem lại 1 job đã có; nếu bỏ trống, tự sinh UUID mới |

## Output (stdout)

- Log tiến trình theo từng bước pipeline (`downloading`, `transcribing`,
  `scripting`, `synthesizing`, `merging`) — mỗi bước log 1 dòng bắt đầu và 1 dòng
  kết thúc kèm `job_id`.
- Khi hoàn tất: in đường dẫn tuyệt đối tới `jobs/{job_id}/output.mp4`.
- Khi lỗi: in rõ bước nào lỗi và message lỗi (FR-008), exit code khác 0.

## Exit Codes

| Code | Ý nghĩa |
|---|---|
| `0` | Job hoàn tất, `output.mp4` đã sẵn sàng |
| `1` | Lỗi input (URL không hợp lệ/không thuộc 3 nền tảng hỗ trợ) |
| `2` | Lỗi trong quá trình xử lý (download/ASR/script/TTS/merge thất bại) — chi tiết bước lỗi nằm trong `jobs/{job_id}/job.json.error` |

## Idempotency

Chạy lại với cùng `--job-id` của một job đã `failed` MUST resume từ bước cuối cùng
thành công (dựa trên file trung gian đã có trong `jobs/{job_id}/`), không tải lại
video từ đầu nếu `source.mp4` đã tồn tại.

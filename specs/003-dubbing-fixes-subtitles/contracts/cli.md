# Contract: CLI Interface (mở rộng)

Kế thừa [contracts/cli.md của 001](../../001-video-repurpose-pipeline/contracts/cli.md)
— chỉ liệt kê phần thay đổi. Mọi Exit Code / Idempotency không nhắc lại ở đây
giữ nguyên như 001.

## Command (cập nhật)

```bash
python pipeline.py \
  --url <video_url> \
  --script-mode <translate|rewrite|subtitle> \
  [--dynamic-captions] \
  [--job-id <existing_job_id>]
```

## Arguments (thay đổi)

| Arg | Required | Values | Ghi chú |
|---|---|---|---|
| `--script-mode` | Yes | `translate` \| `rewrite` \| **`subtitle`** (mới, US3) | `subtitle` = giữ nguyên âm thanh gốc, chỉ thêm phụ đề (FR-004/FR-005/FR-006) |
| `--dynamic-captions` | No | flag (mặc định tắt) | **Mới** (US4, FR-007/FR-008). Chỉ có tác dụng khi `--script-mode` là `translate`/`rewrite`; bị bỏ qua (không lỗi) nếu dùng cùng `--script-mode subtitle` vì phụ đề đã luôn bật ở mode đó. |

## Output (stdout) — thay đổi

- Với `--script-mode subtitle`: log bỏ qua bước `synthesizing` (`[pipeline] Bỏ
  qua TTS (chế độ Phụ đề tự động)`), bước `merging` log rõ đang burn phụ đề
  thay vì ghép audio.
- Với `--dynamic-captions`: bước `synthesizing` log thêm số câu/cụm đã thu
  được mốc thời gian; bước `merging` log rõ đã burn phụ đề động.
- Khi không giữ được nhạc nền hoặc lệch thời lượng vẫn còn sau fix (US1/US2),
  log cảnh báo rõ như 001 (không im lặng bỏ qua — FR-003 của spec này).

## Idempotency (mở rộng)

Resume job `--script-mode subtitle` MUST bỏ qua lại bước `synthesizing`
(không tạo `voice_track`), tiếp tục đúng từ `merging` nếu `script.json` đã có
sẵn — theo đúng `status_from_artifacts()` hiện có của 001, không cần logic
resume riêng.

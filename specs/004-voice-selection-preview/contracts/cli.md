# Contract: CLI Interface (mở rộng)

Kế thừa [contracts/cli.md của 001](../../001-video-repurpose-pipeline/contracts/cli.md)
và [contracts/cli.md của 003](../../003-dubbing-fixes-subtitles/contracts/cli.md) —
chỉ liệt kê phần thay đổi.

## Command (cập nhật)

```bash
python pipeline.py \
  --url <video_url> \
  --script-mode <translate|rewrite|subtitle> \
  [--tts-provider <edge-tts|lucyai>] \
  [--voice-id <voice_id>] \
  [--dynamic-captions] \
  [--job-id <existing_job_id>]
```

## Arguments (mới)

| Arg | Required | Values | Ghi chú |
|---|---|---|---|
| `--tts-provider` | No | `edge-tts` (mặc định) \| `lucyai` | Chỉ có tác dụng khi `--script-mode` là `translate`/`rewrite` |
| `--voice-id` | No | Tuỳ provider | edge-tts: `vi-VN-NamMinhNeural`/`vi-VN-HoaiMyNeural`. LucyAI: `id` lấy từ tài khoản người dùng qua `getUserVoices`. Bỏ trống → dùng giọng mặc định hiện có (`vi-VN-NamMinhNeural`) |

## Output (stdout) — thay đổi

- Log bước `synthesizing` in thêm provider + voice đang dùng, VD
  `[pipeline] Bắt đầu synthesizing (provider=lucyai, voice=xxx)...`
- Nếu `--tts-provider lucyai` mà thiếu `VIVIBE_API_KEY` trong `.env`: fail rõ
  ràng ngay ở bước `synthesizing` với message hướng dẫn cấu hình, không thử
  âm thầm fallback sang edge-tts (FR-007 của spec.md).

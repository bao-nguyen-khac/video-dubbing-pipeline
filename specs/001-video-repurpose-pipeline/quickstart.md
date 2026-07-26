# Quickstart: Validate Video Repurpose Pipeline (US1 MVP)

## Prerequisites

- Python 3.11+
- `ffmpeg` cài sẵn trên máy (`brew install ffmpeg` trên macOS)
- 9router đang chạy, có `ROUTER_BASE_URL`/`ROUTER_API_KEY`/`ROUTER_MODEL` hợp lệ
  (xem constitution Technology Stack)
- Dependencies Python: `pip install -r requirements.txt`
  (gồm: `f2`, `yt-dlp`, `faster-whisper`, `openai`, `edge-tts`, `ffmpeg-python`, `python-dotenv`)

## Setup

```bash
cd media-generation
cp .env.example .env   # điền ROUTER_BASE_URL/ROUTER_API_KEY/ROUTER_MODEL thật
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Hoặc: Setup bằng Docker (không cần cài Python 3.11/ffmpeg trên máy)

```bash
cp .env.example .env   # điền giá trị thật trước khi build
docker compose build
```

Khi chạy bằng Docker, thay `python pipeline.py ...` ở phần "Run" bên dưới bằng
`docker compose run --rm pipeline ...` — chi tiết ở
[README.md](../../README.md#chạy-bằng-docker-thay-thế-cài-đặt-thủ-công).

## Run (US1 — TikTok, mode dịch)

```bash
python pipeline.py \
  --url "https://www.tiktok.com/@<user>/video/<id>" \
  --script-mode translate
```

## Expected Outcome

1. Log lần lượt các bước: `downloading` → `transcribing` → `scripting` →
   `synthesizing` → `merging` → `done`, kèm `job_id` sinh ra.
2. Thư mục `jobs/<job_id>/` chứa đủ 5 file: `source.mp4`, `transcript.json`,
   `script.json`, `voice.wav`, `output.mp4`, và `job.json` với `status: "done"`.
3. `output.mp4` mở lên có hình ảnh gốc + giọng đọc tiếng Việt mới, không mất tiếng/
   rè (SC-003).
4. Với video gốc dưới 3 phút, tổng thời gian từ lúc chạy lệnh tới khi có
   `output.mp4` (trừ thời gian tải mạng) dưới 5 phút (SC-002).

## Validate Failure Handling (Acceptance Scenario #2, US1)

```bash
python pipeline.py --url "https://www.tiktok.com/invalid-or-removed-video" --script-mode translate
```

Expected: exit code `2`, `jobs/<job_id>/job.json` có `status: "failed"` và `error`
mô tả rõ bước `downloading` thất bại; không có file `transcript.json` trở đi được
tạo (đúng theo state machine tuần tự ở data-model.md).

## Validate Resume (Idempotency, contracts/cli.md)

```bash
# Giả sử job trước fail ở bước scripting (source.mp4 + transcript.json đã có)
python pipeline.py --url "<same_url>" --script-mode translate --job-id <job_id_from_before>
```

Expected: log KHÔNG in lại bước `downloading`/`transcribing` (dùng file đã có),
tiếp tục thẳng từ `scripting`.

## References

- Chi tiết field/schema: [contracts/job-state-schema.md](./contracts/job-state-schema.md)
- Chi tiết CLI args/exit code: [contracts/cli.md](./contracts/cli.md)
- Data model đầy đủ: [data-model.md](./data-model.md)

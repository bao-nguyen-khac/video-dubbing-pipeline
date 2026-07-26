# Video Repurpose Pipeline

Pipeline Python CLI tự động hoá quá trình tái tạo video:  
**Tải video → Tách lời → Viết kịch bản tiếng Việt → Sinh giọng đọc → Ghép video**

## Yêu cầu hệ thống

- Python 3.11+
- `ffmpeg` trong PATH (`brew install ffmpeg` trên macOS)
- 9router (LLM proxy, OpenAI-compatible)

## Cấu hình (.env)

```bash
cp .env.example .env
# rồi điền ROUTER_BASE_URL / ROUTER_API_KEY / ROUTER_MODEL thật vào .env
```

| Biến | Ý nghĩa |
|---|---|
| `ROUTER_BASE_URL` | Base URL đầy đủ kiểu OpenAI SDK, **đã bao gồm `/v1`** (vd `http://172.16.57.147:20128/v1`) |
| `ROUTER_API_KEY` | API key gọi 9router |
| `ROUTER_MODEL` | Model dùng cho dịch/viết kịch bản (vd `ag/gemini-3-flash-agent`) |
| `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` | Tài khoản đăng nhập giao diện web (chỉ 1 cặp duy nhất) |
| `WEB_UI_SECRET_KEY` | Secret ký session cookie (7 ngày) — sinh 1 chuỗi ngẫu nhiên dài, không để trống |
| `VIVIBE_API_KEY` | API key TTS Vivibe (tuỳ chọn, provider giọng đọc thứ 2 — không cấu hình vẫn dùng đủ tính năng với edge-tts) |

`.env` đã nằm trong `.gitignore` — không commit key thật. Chạy local, `pipeline.py`
tự load `.env` qua `python-dotenv`; chạy Docker, `docker-compose.yml` đã khai báo
`env_file: .env` nên cũng tự đọc, không cần truyền `-e` thủ công.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy bằng Docker (thay thế cài đặt thủ công)

Không cần cài Python 3.11/ffmpeg trên máy — chỉ cần Docker và file `.env` đã điền.

```bash
docker compose build
docker compose run --rm pipeline --url "<video_url>" --script-mode translate
```

Output được mount ra `./jobs/` trên máy host (xem `docker-compose.yml`) nên xem lại
file trung gian bình thường như chạy local. Nếu `ROUTER_BASE_URL` trong `.env` là
`localhost`, đổi host thành `host.docker.internal` khi chạy trong container (image
đã có sẵn fallback này qua `extra_hosts`, cần Docker ≥20.10 trên Linux).

Không dùng `docker compose` thì build/run thủ công bằng `docker build`/`docker run`:

```bash
docker build -t media-generation-pipeline .
docker run --rm \
  --env-file .env \
  -v "$(pwd)/jobs:/app/jobs" \
  media-generation-pipeline \
  --url "<video_url>" --script-mode translate
```

## Cách dùng

```bash
python pipeline.py \
  --url <video_url> \
  --script-mode <translate|rewrite|subtitle> \
  [--dynamic-captions] \
  [--tts-provider <edge-tts|lucyai|router-tts>] \
  [--voice-id <voice_id>] \
  [--job-id <existing_job_id>]
```

| Tham số | Bắt buộc | Mô tả |
|---|---|---|
| `--url` | ✅ | URL TikTok, Douyin hoặc YouTube |
| `--script-mode` | ✅ | `translate` (Dịch chuẩn, lồng tiếng), `rewrite` (Sáng tạo, lồng tiếng), hoặc `subtitle` (Phụ đề tự động — giữ nguyên âm thanh gốc, chỉ thêm phụ đề) |
| `--dynamic-captions` | ❌ | Chỉ áp dụng với `translate`/`rewrite`: thêm phụ đề động (chữ kịch bản chạy khớp nhịp giọng đọc, theo từng câu) lên video đã lồng tiếng |
| `--tts-provider` | ❌ | `edge-tts` (mặc định, free), `lucyai` (Vivibe, cần `VIVIBE_API_KEY`), hoặc `router-tts` (giọng Gemini qua 9router, tái dùng `ROUTER_API_KEY` có sẵn) — chỉ áp dụng với `translate`/`rewrite` |
| `--voice-id` | ❌ | Giọng đọc cụ thể (VD `vi-VN-HoaiMyNeural` cho edge-tts, id giọng trong tài khoản Vivibe, hoặc tên giọng Gemini VD `Puck` cho router-tts); để trống → dùng giọng mặc định |
| `--job-id` | ❌ | Resume job cũ; để trống → tạo job mới |

Cả `translate` và `rewrite` đều giữ nhạc nền gốc (tách bằng Demucs, trộn với
giọng đọc mới) và tự chỉnh tốc độ đọc để khớp gần đúng thời lượng video gốc.

### Chọn giọng đọc — edge-tts / Vivibe / 9router (feature 004)

Mặc định dùng edge-tts (2 giọng tiếng Việt, miễn phí). 2 provider tuỳ chọn
thêm:

```bash
# Vivibe (thương hiệu; API thực chất là LucyAI, api.lucylab.io) — cần tài
# khoản riêng: tạo tại https://www.vivibe.app, lấy API key, cấu hình sẵn ít
# nhất 1 giọng đọc trong tài khoản, rồi điền VIVIBE_API_KEY vào .env
python pipeline.py --url "..." --script-mode translate --tts-provider lucyai --voice-id "<id giọng trong tài khoản>"

# 9router TTS (giọng Gemini, 30 giọng cố định VD Puck/Kore/Zephyr...) — tái
# dùng ROUTER_API_KEY đã có, KHÔNG cần secret riêng
python pipeline.py --url "..." --script-mode translate --tts-provider router-tts --voice-id "Puck"
```

Trên web UI: `GET /api/voices` tự gộp danh sách giọng cả 3 provider (Vivibe
chỉ hiện nếu đã cấu hình `VIVIBE_API_KEY`), có nút "Nghe thử" cạnh mỗi giọng
trước khi chạy job. Chưa cấu hình `VIVIBE_API_KEY` vẫn dùng đủ tính năng với
edge-tts + 9router TTS, không lỗi.

Lưu ý: quota giọng Gemini qua 9router có thể bị giới hạn theo phút (dịch vụ
ngoài dự án) — nếu gặp lỗi "exceeded your current quota", đợi vài chục giây
rồi thử lại.

## Ví dụ

```bash
# Dịch chuẩn (lồng tiếng), giữ nhạc nền gốc
python pipeline.py --url "https://www.tiktok.com/@user/video/123" --script-mode translate

# Sáng tạo (tự soạn kịch bản mới), kèm phụ đề động khớp nhịp giọng đọc
python pipeline.py --url "https://www.douyin.com/video/456" --script-mode rewrite --dynamic-captions

# Phụ đề tự động — giữ nguyên âm thanh gốc, chỉ thêm phụ đề dịch sát nghĩa
python pipeline.py --url "https://www.tiktok.com/@user/video/123" --script-mode subtitle

# Resume job bị lỗi giữa chừng
python pipeline.py --url "..." --script-mode translate --job-id "uuid-của-job-cũ"
```

## Nguồn hỗ trợ

| Nền tảng | Engine | Watermark-free |
|---|---|---|
| TikTok | `f2` | ✅ |
| Douyin (抖音) | `f2` | ✅ |
| YouTube | `yt-dlp` | N/A |

## Giao diện web (thay thế CLI, feature 002-web-ui)

Đăng nhập bằng `WEB_UI_USERNAME`/`WEB_UI_PASSWORD`, submit URL + chọn chế độ xử
lý (Dịch chuẩn / Sáng tạo / Phụ đề tự động) qua form, tuỳ chọn bật "Phụ đề
động" cho 2 chế độ lồng tiếng, theo dõi % tiến trình, xem/tải video kết quả,
xem lịch sử job và thử lại job lỗi — không cần dùng dòng lệnh.

### Chạy bằng Docker (khuyến nghị) — 2 container tách biệt

`web-api` (FastAPI + pipeline) và `web-ui` (nginx serve React build, tự proxy
`/api/*` sang `web-api` — cùng origin nên không cần cấu hình CORS):

```bash
docker compose up -d --build web-api web-ui
```

Mở `http://localhost` (web-ui, cổng 80). `web-api` cũng expose trực tiếp ở
`http://localhost:8000` để tiện curl-test API khi cần. `./jobs/` vẫn mount ra
host như CLI. Dừng: `docker compose down`.

### Chạy local không Docker (1 process, tự serve luôn React build)

```bash
cd web/frontend && npm install && npm run build && cd ../..
uvicorn web.backend.main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`. Chi tiết API, thiết kế và kịch bản validate từng
user story: [`specs/002-web-ui/`](specs/002-web-ui/).

## Kiểm tra môi trường

```bash
python env_check.py
```

## Cấu trúc output

Mỗi lần chạy tạo thư mục `jobs/{job_id}/`:

```
jobs/{job_id}/
├── job.json         # Trạng thái và metadata
├── source.mp4       # Video gốc đã tải
├── transcript.json  # Lời thoại trích xuất (kèm mốc thời gian từng câu)
├── script.json      # Kịch bản tiếng Việt (hoặc segments dịch sát nghĩa nếu subtitle)
├── voice.wav        # Giọng đọc tổng hợp — không có nếu script-mode=subtitle
├── background.wav   # Nhạc nền tách được (Demucs), nếu có
├── captions.json    # Mốc thời gian phụ đề động theo câu, nếu bật --dynamic-captions
├── subtitles.srt     # File phụ đề trung gian trước khi burn-in (subtitle hoặc dynamic-captions)
└── output.mp4       # Sản phẩm cuối cùng
```

## Tài liệu kỹ thuật

- Pipeline CLI (spec, plan, quickstart): [`specs/001-video-repurpose-pipeline/`](specs/001-video-repurpose-pipeline/)
- Giao diện web (spec, plan, API, quickstart): [`specs/002-web-ui/`](specs/002-web-ui/)
- Sửa lỗi lồng tiếng + phụ đề tự động/động (spec, plan, research, quickstart): [`specs/003-dubbing-fixes-subtitles/`](specs/003-dubbing-fixes-subtitles/)
- Chọn giọng đọc + nghe thử, provider Vivibe (spec, plan, research, quickstart): [`specs/004-voice-selection-preview/`](specs/004-voice-selection-preview/)

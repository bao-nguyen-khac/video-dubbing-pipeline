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
  --script-mode <translate|rewrite> \
  [--job-id <existing_job_id>]
```

| Tham số | Bắt buộc | Mô tả |
|---|---|---|
| `--url` | ✅ | URL TikTok, Douyin hoặc YouTube |
| `--script-mode` | ✅ | `translate` (dịch) hoặc `rewrite` (tự soạn) |
| `--job-id` | ❌ | Resume job cũ; để trống → tạo job mới |

## Ví dụ

```bash
# Tải và dịch video TikTok
python pipeline.py --url "https://www.tiktok.com/@user/video/123" --script-mode translate

# Tải video Douyin và tự soạn kịch bản mới
python pipeline.py --url "https://www.douyin.com/video/456" --script-mode rewrite

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

Đăng nhập bằng `WEB_UI_USERNAME`/`WEB_UI_PASSWORD`, submit URL + chọn chế độ
kịch bản qua form, theo dõi % tiến trình, xem/tải video kết quả, xem lịch sử
job và thử lại job lỗi — không cần dùng dòng lệnh.

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
├── transcript.json  # Lời thoại trích xuất
├── script.json      # Kịch bản tiếng Việt
├── voice.wav        # Giọng đọc tổng hợp
├── background.wav   # Nhạc nền tách được (Demucs), nếu có
└── output.mp4       # Sản phẩm cuối cùng
```

## Tài liệu kỹ thuật

- Pipeline CLI (spec, plan, quickstart): [`specs/001-video-repurpose-pipeline/`](specs/001-video-repurpose-pipeline/)
- Giao diện web (spec, plan, API, quickstart): [`specs/002-web-ui/`](specs/002-web-ui/)

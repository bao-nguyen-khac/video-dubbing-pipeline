# AI Video Dubbing Studio

> **Nền tảng tự động hoá lồng tiếng, dịch thuật kịch bản và tái tạo video đa ngôn ngữ bằng AI với giao diện Web Studio hiện đại.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=flat-square&logo=vite&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Supported-007808?style=flat-square&logo=ffmpeg&logoColor=white)

---

## 🌟 Điểm nổi bật & Tính năng chính

### 🎨 1. Giao diện Web Studio Hiện đại
- **Fluid Full-Width UI**: Thiết kế tràn toàn màn hình, co giãn linh hoạt, tối ưu cho cả màn hình tiêu chuẩn và màn hình Ultra-wide.
- **Theme System**: Hỗ trợ 3 chế độ **Sáng (Light)**, **Tối (Dark)** và **Tự động theo hệ điều hành (System)**.
- **Toast & Desktop Notification**: Thông báo trạng thái thời gian thực và thông báo Desktop khi job xử lý hoàn tất.

### 📥 2. Nhận diện & Nạp Nguồn Video Linh hoạt
- **Tải trực tuyến không Watermark**: Hỗ trợ dán link **TikTok**, **Douyin (抖音)** tự động bóc tách sạch watermark chuẩn HD, và **YouTube** (qua `f2` & `yt-dlp`).
- **Drag & Drop Video Uploader**: Kéo thả file video trực tiếp từ máy tính, tự động trích xuất Thumbnail bằng HTML5 Canvas và phát hiện thông số kỹ thuật (độ phân giải, thời lượng, dung lượng).

### 🧠 3. Nhận dạng Giọng nói & Biên soạn Kịch bản AI
- **ASR Đa ngôn ngữ (faster-whisper)**: Tự động phát hiện ngôn ngữ nguồn (~99 thứ tiếng: Trung, Anh, Hàn, Nhật, Thái...) và trích xuất lời thoại kèm word-level timestamps.
- **Đa dạng Chế độ Xử lý**:
  - 🔄 **Dịch chuẩn (Translate)**: Dịch sát nghĩa nội dung gốc sang tiếng Việt tự nhiên.
  - ✍️ **Sáng tạo (Rewrite)**: Viết lại kịch bản mới giữ nguyên bối cảnh và nhịp điệu video.
  - 💬 **Phụ đề tự động (Subtitle)**: Giữ nguyên âm thanh gốc, chỉ chèn phụ đề tiếng Việt.
  - 👁️ **Thuyết minh theo hình ảnh (Visual Dubbing)**: Phân tích khung hình video và tạo lời bình theo prompt tuỳ chọn.

### 🎬 4. Chốt duyệt Đồng bộ Video (Human-in-the-loop)
- **Video-Synced Subtitle Editor**: Bấm vào bất kỳ câu thoại nào để video nhảy đến đúng mốc thời gian đó; câu thoại đang phát sẽ tự động highlight viền tím phát sáng theo thời gian thực. Hỗ trợ phím tắt `Ctrl + S` (Lưu) và `Space` (Phát/Dừng).
- **8-Point Interactive Hardsub Mask**: Kéo co giãn 8 điểm trực tiếp trên frame hình mẫu để khoanh vùng che mờ phụ đề ngoại ngữ có sẵn trên video.

### 🎙️ 5. Lồng tiếng Khớp nhịp Tự nhiên (Natural Pause Dubbing)
- **Khớp nhịp theo từng câu**: Tách nhạc nền gốc bằng Demucs, chèn khoảng lặng thực tế vào các quãng nghỉ, chỉ tăng tốc nhẹ khi đọc tràn khung (tối đa 1.25×) — không làm biến dạng giọng đọc.
- **Đa dạng Giọng đọc (TTS Providers)**:
  - ⚡ **Edge-TTS**: Miễn phí, tốc độ cao, đa dạng giọng Nam/Nữ Bắc - Nam.
  - 💎 **Vivibe (LucyAI)**: Giọng đọc truyền cảm tự nhiên.
  - 🎭 **OmniVoice**: Microservice Voice Cloning (k2-fsa) clone theo giọng mẫu.
- **Nghe thử Giọng trực quan**: Thẻ chọn giọng kèm wave equalizer animation và bộ lọc theo giới tính, vùng miền.
- **Phụ đề động (Word-level Captions)**: Hiệu ứng chữ chạy sáng từng từ khớp theo nhịp giọng đọc.

### 🎥 6. Trình So sánh Video & Quản lý Job
- **Dual-Sync Comparison Player**: Phát đồng bộ song song video gốc vs video kết quả khớp từng mili-giây. Bộ chọn kênh âm thanh linh hoạt (*Tiếng kết quả / Tiếng gốc / Cả hai 50/50*).
- **Dashboard Stats & Tìm kiếm Tức thì**: Thống kê số lượng job, tìm kiếm theo từ khoá, lọc theo trạng thái và ghim ưu tiên.

---

## 🛠️ Yêu cầu hệ thống

- **Python**: 3.11 trở lên
- **Node.js**: 18 trở lên (kèm `npm`)
- **FFmpeg**: Đã cài đặt trong PATH (`brew install ffmpeg` trên macOS, `apt-get install ffmpeg` trên Linux)
- **LLM API**: 9router (OpenAI-compatible) hoặc OpenRouter (Gemini 2.5 Flash, GPT-4o-mini)

---

## 🚀 Hướng dẫn Cài đặt & Khởi chạy Nhanh

### 1. Clone repository & Cấu hình môi trường

```bash
git clone https://github.com/bao-nguyen-khac/video-dubbing-pipeline.git
cd video-dubbing-pipeline

# Tạo file .env từ mẫu
cp .env.example .env
```

Mở file `.env` và điền cấu hình cơ bản:
```env
# LLM Endpoint (OpenAI-compatible)
ROUTER_BASE_URL=https://openrouter.ai/api/v1
ROUTER_API_KEY=your_openrouter_api_key_here
ROUTER_MODEL=google/gemini-2.5-flash

# Tài khoản đăng nhập Web UI
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=your_password_here
WEB_UI_SECRET_KEY=generate_a_random_long_secret_string_here
```

---

### 2. Khởi chạy ứng dụng Web

#### 🔹 Cách 1: Khởi động 1 lệnh với `start.sh` (Khuyến nghị cho Local Dev)

Script sẽ tự động kiểm tra virtualenv, cài đặt dependencies và khởi chạy song song Backend + Frontend:

```bash
chmod +x start.sh
./start.sh
```

- 🌐 **Web Studio UI**: [http://localhost:5173](http://localhost:5173)
- ⚙️ **Backend API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

#### 🔹 Cách 2: Khởi chạy bằng Docker Compose (Khuyến nghị cho Server / Production)

```bash
docker compose up -d --build
```

Mở trình duyệt truy cập: `http://localhost:8000` (hoặc cổng cấu hình).

---

#### 🔹 Cách 3: Khởi chạy thủ công từng phần

**Backend (Python FastAPI):**
```bash
python -m venv .venv
source .venv/bin/activate  # Trên Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**Frontend (React + Vite):**
```bash
cd web/frontend
npm install
npm run dev
```

---

### 3. Chạy qua giao diện Dòng lệnh (CLI Pipeline)

Ngoài giao diện Web, bạn vẫn có thể gọi trực tiếp pipeline bằng CLI:

```bash
python pipeline.py \
  --url "https://www.tiktok.com/@user/video/1234567890" \
  --script-mode translate \
  --dynamic-captions \
  --supervised
```

| Tham số CLI | Bắt buộc | Mô tả |
|---|:---:|---|
| `--url` | ✅ | URL video TikTok, Douyin hoặc YouTube |
| `--script-mode` | ✅ | `translate` (Dịch chuẩn), `rewrite` (Sáng tạo), hoặc `subtitle` (Chỉ làm phụ đề) |
| `--dynamic-captions` | ❌ | Bật phụ đề động chữ chạy khớp nhịp giọng đọc |
| `--tts-provider` | ❌ | `edge-tts` (mặc định), `lucyai` (Vivibe), hoặc `omnivoice` |
| `--voice-id` | ❌ | ID giọng đọc cụ thể (VD: `vi-VN-HoaiMyNeural`) |
| `--supervised` | ❌ | Bật chế độ quản lý pipeline (tạm dừng để duyệt lời thoại/kịch bản trên Web) |
| `--hardsub-blur` | ❌ | Bật làm mờ phụ đề gốc và chèn phụ đề tiếng Việt đè lên |
| `--job-id` | ❌ | Chạy tiếp (resume) một job đã có sẵn |

---

## ⚙️ Bảng cấu hình biến môi trường (`.env`)

| Biến | Mặc định | Mô tả |
|---|---|---|
| `ROUTER_BASE_URL` | `http://localhost:20128/v1` | Endpoint OpenAI-compatible của LLM (9router / OpenRouter / vLLM) |
| `ROUTER_API_KEY` | *(Bắt buộc)* | API Key gọi LLM |
| `ROUTER_MODEL` | `gpt-4o-mini` | Model LLM dùng để dịch và sinh kịch bản tiếng Việt |
| `OPENROUTER_API_KEY` | *(Tuỳ chọn)* | Key OpenRouter dùng làm fallback tự động khi endpoint chính lỗi/timeout |
| `WEB_UI_USERNAME` | `admin` | Tên đăng nhập giao diện Web |
| `WEB_UI_PASSWORD` | *(Bắt buộc)* | Mật khẩu đăng nhập giao diện Web |
| `WEB_UI_SECRET_KEY` | *(Bắt buộc)* | Chuỗi bí mật dùng để mã hoá session cookie đăng nhập |
| `TIKTOK_COOKIE` | *(Tuỳ chọn)* | Cookie TikTok (nếu cần vượt qua giới hạn tải video) |
| `DOUYIN_COOKIE` | *(Tuỳ chọn)* | Cookie Douyin để cào video chuẩn HD |
| `VIVIBE_API_KEY` | *(Tuỳ chọn)* | API key dịch vụ giọng đọc Vivibe (LucyAI) |
| `OMNIVOICE_BASE_URL` | `http://localhost:8100` | URL service OmniVoice Voice Cloning |
| `WHISPER_MODEL` | `small` | Kích thước model Whisper (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `WHISPER_LANGUAGE` | *(Tự động)* | Ghim mã ngôn ngữ nguồn nếu không muốn model tự đoán (`en`, `zh`, `ja`, `ko`...) |

---

## 📂 Cấu trúc thư mục Output của Job

Mỗi video được xử lý sẽ tạo một thư mục riêng trong `jobs/{job_id}/`:

```
jobs/{job_id}/
├── job.json              # Trạng thái, thông số và metadata của job
├── source.mp4            # Video gốc đã tải về
├── transcript.json       # Lời thoại gốc trích xuất từ Whisper (kèm timestamp)
├── script.json           # Kịch bản tiếng Việt đã chia thành từng nhịp
├── background.wav        # Âm thanh nhạc nền đã tách (Demucs)
├── voice.wav             # File audio lồng tiếng hoàn chỉnh theo timeline
├── voice_timeline.json   # Mốc thời gian thực tế từng câu đọc
├── captions.json         # Dữ liệu phụ đề động theo từng từ
├── subtitles.srt          # File phụ đề SRT
└── output.mp4            # Video thành phẩm cuối cùng
```

---

## 🧪 Kiểm tra & Chạy Unit Tests

```bash
# Kiểm tra kết nối môi trường và API
python env_check.py

# Chạy toàn bộ unit tests backend
pytest tests/unit -q

# Kiểm tra build frontend
cd web/frontend && npm run build && npm run lint
```

---

## 📄 License

Dự án được phân phối dưới giấy phép mã nguồn mở [MIT License](LICENSE).

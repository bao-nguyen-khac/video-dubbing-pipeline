FROM python:3.11-slim

# ffmpeg: bắt buộc cho asr/, tts/, merge/, clean_video/ (Constitution Technology Stack)
# build-essential: cần để pip build từ source một số dependency Rust của demucs
# (vd "sphn") khi platform (arm64) chưa có sẵn wheel prebuilt
# fonts-dejavu-core: font có dấu tiếng Việt để VẼ phụ đề bằng Pillow
# (merge/text_renderer.py). Phụ đề KHÔNG còn burn qua bộ lọc `subtitles`/libass
# của ffmpeg nữa — bộ lọc đó không có trên nhiều bản ffmpeg (vd Homebrew macOS),
# nên việc burn từng phụ thuộc vào may rủi của môi trường; nay chỉ cần `overlay`
# (bộ lọc lõi, luôn có) + 1 file font.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        build-essential \
        pkg-config \
        fonts-dejavu-core \
        curl \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# 010-topic-video-generation (Constitution Principle I, Ngoại lệ #2): bước
# render cuối gọi `npx hyperframes render` — CHỈ ngoại lệ này được phép dùng
# Node.js runtime, xem constitution.md. Cài Node.js 22+ qua kênh chính thức
# NodeSource (research.md §8).
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# HyperFrames render bằng Chrome headless — cần đủ thư viện hệ thống chuẩn cho
# Puppeteer/Playwright-class browser trên Debian (research.md §8). CHƯA verify
# build thật trong container (T045, quickstart.md mục rà soát cuối) — danh
# sách này theo đúng khuyến nghị chính thức của Puppeteer, có thể cần chỉnh
# lại tên gói nếu Debian base image đổi version.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libexpat1 \
        libfontconfig1 \
        libgbm1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxcursor1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxrandr2 \
        libxrender1 \
        libxss1 \
        libxtst6 \
        lsb-release \
        wget \
        xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 010: `npx hyperframes render` (merge/hyperframes_renderer.py) cần Chrome
# headless — bản thân lệnh `render` tự tải Chrome lúc cần (đã xác nhận trên
# máy dev macOS, research.md §5b). CHƯA xác nhận hành vi này trong chính
# container này (mạng ra ngoài lúc build có thể bị chặn tuỳ hạ tầng deploy) —
# đây là đúng phần việc của T045 (build Docker thật + verify render chạy được
# TRONG container, quickstart.md mục rà soát cuối), không suy đoán thêm ở đây.

# Default dùng khi không có .env — trỏ 9router qua host.docker.internal (Docker
# Desktop macOS/Windows tự resolve; Linux cần extra_hosts host-gateway, xem
# docker-compose.yml). ROUTER_API_KEY/ROUTER_MODEL/ROUTER_BASE_URL thật nên đặt
# trong .env (docker-compose.yml đã cấu hình env_file: .env, sẽ override giá trị này)
ENV ROUTER_BASE_URL=http://host.docker.internal:20128/v1

ENTRYPOINT ["python", "pipeline.py"]

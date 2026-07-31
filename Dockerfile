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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default dùng khi không có .env — trỏ 9router qua host.docker.internal (Docker
# Desktop macOS/Windows tự resolve; Linux cần extra_hosts host-gateway, xem
# docker-compose.yml). ROUTER_API_KEY/ROUTER_MODEL/ROUTER_BASE_URL thật nên đặt
# trong .env (docker-compose.yml đã cấu hình env_file: .env, sẽ override giá trị này)
ENV ROUTER_BASE_URL=http://host.docker.internal:20128/v1

ENTRYPOINT ["python", "pipeline.py"]

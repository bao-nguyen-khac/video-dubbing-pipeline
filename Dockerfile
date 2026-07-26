FROM python:3.11-slim

# ffmpeg: bắt buộc cho asr/, tts/, merge/, clean_video/ (Constitution Technology Stack)
# build-essential: cần để pip build từ source một số dependency Rust của demucs
# (vd "sphn") khi platform (arm64) chưa có sẵn wheel prebuilt
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        build-essential \
        pkg-config \
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

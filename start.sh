#!/usr/bin/env bash

# ==============================================================================
# Script khởi chạy đồng thời:
# 1. Backend (FastAPI + Pipeline)   - Port 8000
# 2. Frontend (React + Vite)        - Port 5173
# ==============================================================================

# Dừng script nếu gặp lỗi cơ bản
set -e

# Chuyển về thư mục gốc của repository
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Màu sắc thông báo
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BOLD}${CYAN}====================================================${NC}"
echo -e "${BOLD}${CYAN}   🚀 Khởi động Hệ thống Video Repurpose Pipeline   ${NC}"
echo -e "${BOLD}${CYAN}====================================================${NC}\n"

# Khai báo biến PID để dọn dẹp khi tắt
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo -e "\n${YELLOW}🛑 Đang dừng tất cả các dịch vụ...${NC}"

    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi

    # Đợi các tiến trình con dừng hẳn
    wait 2>/dev/null || true
    echo -e "${GREEN}✅ Toàn bộ dịch vụ đã được dừng an toàn.${NC}"
}

# Bắt tín hiệu Ctrl+C (SIGINT), SIGTERM, EXIT
trap cleanup SIGINT SIGTERM EXIT

# ------------------------------------------------------------------------------
# 1. Kiểm tra môi trường Python (venv / .venv)
# ------------------------------------------------------------------------------
echo -e "${BLUE}[1/3] Kiểm tra môi trường Python...${NC}"
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo -e "  ✓ Đã kích hoạt môi trường ảo: ${GREEN}venv${NC}"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo -e "  ✓ Đã kích hoạt môi trường ảo: ${GREEN}.venv${NC}"
else
    echo -e "  ${YELLOW}⚠️ Không tìm thấy venv/.venv, sử dụng Python hệ thống.${NC}"
fi

# Kiểm tra uvicorn
if ! command -v uvicorn &> /dev/null; then
    echo -e "  ${RED}❌ Không tìm thấy 'uvicorn'. Hãy cài đặt bằng: pip install -r requirements.txt${NC}"
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. Khởi chạy Backend (FastAPI)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[2/3] Khởi động Backend FastAPI (Port 8000)...${NC}"
uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!
echo -e "  ✓ Backend đang chạy với PID: ${GREEN}$BACKEND_PID${NC}"

# ------------------------------------------------------------------------------
# 3. Khởi chạy Frontend (Vite)
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[3/3] Khởi động Frontend React (Vite)...${NC}"
if [ ! -d "web/frontend/node_modules" ]; then
    echo -e "  ${YELLOW}📦 Thư mục node_modules chưa có. Đang chạy npm install...${NC}"
    (cd web/frontend && npm install)
fi

(cd web/frontend && npm run dev) &
FRONTEND_PID=$!
echo -e "  ✓ Frontend đang chạy với PID: ${GREEN}$FRONTEND_PID${NC}"

# ------------------------------------------------------------------------------
# Thông tin truy cập
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}${GREEN}====================================================${NC}"
echo -e "${BOLD}${GREEN}   🎉 Tất cả dịch vụ đã khởi động thành công!       ${NC}"
echo -e "${BOLD}${GREEN}====================================================${NC}"
echo -e "  🌐 ${BOLD}Frontend Web UI :${NC} ${CYAN}http://localhost:5173${NC}"
echo -e "  ⚙️  ${BOLD}Backend API Docs:${NC} ${CYAN}http://127.0.0.1:8000/docs${NC}"
echo -e "\n${YELLOW}💡 Nhấn Ctrl + C để dừng toàn bộ dịch vụ cùng lúc.${NC}\n"

# Đợi cho tới khi người dùng nhấn Ctrl+C
wait

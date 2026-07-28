# Implementation Plan: Đăng video lên TikTok/YouTube Shorts từ giao diện web

**Branch**: `006-publish-video-tab` | **Date**: 2026-07-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-publish-video-tab/spec.md`

## Summary

Thêm tab "Đăng video" vào Web UI: người dùng chọn 1 video kết quả từ job đã xử
lý xong, chọn TikTok hoặc YouTube Shorts, điền tiêu đề, bấm "Đăng" — video được
đăng **công khai ngay** lên kênh của họ, kèm lịch sử các lượt đăng.

Cách làm: đi qua dịch vụ trung gian **Zernio** (đã được nền tảng cấp phép đăng
bài tự động) cho cả xác thực kênh (OAuth) lẫn đăng video — không tự xin audit
TikTok/verify YouTube, không giả lập thao tác tay. Backend thêm 1 module Python
`publish/` (adapter Zernio + runner nền + trạng thái file JSON) và 1 router
FastAPI `/api/publish`; frontend thêm 1 trang React `/publish`. Không đụng vào
pipeline xử lý media hiện có.

## Technical Context

**Language/Version**: Python 3.11 (backend/pipeline), TypeScript + React 18 (frontend)

**Primary Dependencies**: FastAPI, uvicorn, httpx (gọi Zernio), python-dotenv,
itsdangerous (session sẵn có); React + react-router-dom, Vite. **Không thêm
dependency mới** — httpx đã có trong `requirements.txt`.

**Storage**: File JSON, không database — `jobs/{job_id}/publishes/{attempt_id}.json`
và `publish_data/state.json` (xem [data-model.md](./data-model.md))

**Testing**: pytest (`tests/unit`) với lớp HTTP tới Zernio được mock; verify
đầu-cuối thủ công theo [quickstart.md](./quickstart.md)

**Target Platform**: Linux/macOS server chạy local hoặc Docker (docker-compose sẵn có)

**Project Type**: Web application (FastAPI backend + React SPA) trên nền pipeline Python

**Performance Goals**: Mở tab → đăng xong thao tác trong < 2 phút (SC-001,
không tính thời gian upload). Poll trạng thái lượt đăng mỗi 2s, timeout 10 phút
rồi chuyển `failed`.

**Constraints**: Đăng phải **công khai ngay** (SC-005); tuyệt đối không tạo bài
đăng trùng (SC-003); mọi lỗi phải có nguyên nhân rõ ràng (SC-004); thiếu
`ZERNIO_API_KEY` không được làm hỏng luồng job hiện có.

**Scale/Scope**: 1 người dùng đăng nhập, vài kênh, đăng tuần tự từng lượt —
không cần hàng đợi/worker riêng, thread nền là đủ (giống `job_runner.py`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Đối chiếu Constitution v1.7.0:

| Nguyên tắc | Kết quả | Ghi chú |
|---|---|---|
| I. Python-Only Stack | ✅ PASS | Adapter Zernio + runner viết bằng Python trong `publish/`; frontend React đúng ngoại lệ đã cho phép |
| II. Source-First Downloading | ✅ N/A | Tính năng không đụng download |
| III. On-Demand AI Cleanup | ✅ N/A | Không đụng bước cleanup |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS | spec/plan/research/data-model/contracts/quickstart đều là markdown tự đủ nghĩa |
| V. Token & Context Economy | ✅ PASS | Không thêm dependency, không thêm database; tái dùng httpx/FastAPI/pattern `jobs/` sẵn có |
| VI. Agentic Harness Discipline | ✅ PASS (có ràng buộc) | Trạng thái mỗi lượt đăng truy vết qua file JSON; test mock, **gọi thật Zernio phải hỏi người dùng trước** (research.md §8, quickstart §0) |

**GATE ĐÃ ĐÓNG** (2026-07-27): Constitution đã amend lên **v1.7.0** — bảng
Technology Stack có dòng "Đăng bài lên nền tảng → Zernio", Principle VI có thêm
quy tắc "mọi lượt gọi thật tới Zernio phải hỏi người dùng trước, test phải mock
HTTP", và Project Structure có `publish/` + `jobs/{job_id}/publishes/`.

*Re-check sau Phase 1*: thiết kế cuối (module `publish/`, router `/api/publish`,
state file) không phát sinh vi phạm mới. Không còn mục treo.

## Project Structure

### Documentation (this feature)

```text
specs/006-publish-video-tab/
├── plan.md              # File này
├── research.md          # Phase 0 — chọn Zernio, bề mặt API, chống trùng, lưu trữ
├── data-model.md        # Phase 1 — Publish Attempt, Channel Connection, Local State
├── quickstart.md        # Phase 1 — cấu hình, chạy, 6 kịch bản verify
├── contracts/
│   └── api.md           # Phase 1 — hợp đồng /api/publish + ánh xạ sang Zernio
├── checklists/          # đã có từ /speckit-checklist
└── tasks.md             # Phase 2 (/speckit-tasks — KHÔNG tạo ở lệnh này)
```

### Source Code (repository root)

```text
publish/                        # MỚI — module Python cho việc đăng bài
├── __init__.py
├── zernio_client.py            # Adapter duy nhất gọi Zernio (httpx): accounts,
│                               #   connect url, upload media, create post, get post
├── limits.py                   # Ngưỡng thời lượng/kích thước theo nền tảng
├── store.py                    # Đọc/ghi publish attempt + publish_data/state.json
└── runner.py                   # Thread nền: upload → tạo post → poll → cập nhật file

publish_data/                   # MỚI — dữ liệu cục bộ (thêm vào .gitignore)
└── state.json                  # profile_id + disconnected_account_ids

jobs/{job_id}/publishes/        # MỚI — 1 file JSON / 1 lượt đăng
└── {attempt_id}.json

web/backend/
└── publish_api.py              # MỚI — router FastAPI, mount /api/publish trong main.py

web/frontend/src/
├── pages/PublishPage.tsx       # MỚI — trang tab "Đăng video"
├── api/client.ts               # SỬA — thêm hàm gọi /api/publish
├── components/AppShell.tsx     # SỬA — thêm NavLink "Đăng video"
└── App.tsx                     # SỬA — thêm route /publish

tests/unit/
└── test_publish_*.py           # MỚI — mock HTTP, không gọi Zernio thật

.env.example                    # SỬA — thêm ZERNIO_API_KEY / ZERNIO_BASE_URL / ZERNIO_PROFILE_ID
```

**Structure Decision**: Giữ đúng bố cục đã có của dự án — logic nghiệp vụ nằm ở
module Python cấp repo (`publish/`, ngang hàng `tts/`, `merge/`), backend web
chỉ là lớp HTTP mỏng gọi lại module đó (giống `jobs_api.py` chỉ gọi
`pipeline.py`). Trạng thái là file JSON cạnh artifact của job, đúng mô hình
`jobs/{job_id}/` hiện tại. Frontend thêm đúng 1 trang + 1 route, không tái cấu
trúc gì.

## Complexity Tracking

Không có vi phạm cần biện minh; Constitution đã amend xong (v1.7.0).

## Thứ tự bàn giao (2026-07-27, yêu cầu người dùng)

Người dùng cần **TikTok trước mắt**. Vì vậy tasks.md chia 2 chặng:

1. **Chặng 1 (MVP, giao trước)**: toàn bộ luồng cho **TikTok** — kết nối kênh,
   chọn video, tiêu đề, đăng công khai, lịch sử, xử lý lỗi. Đủ để dùng thật.
2. **Chặng 2**: bật thêm **YouTube Shorts**. Thiết kế đã trung lập nền tảng
   (`platform` là tham số ở mọi tầng, options riêng gói trong adapter), nên
   chặng 2 chỉ là thêm nhánh options + ngưỡng 180s + lựa chọn trên UI, không
   phải viết lại.

Phạm vi spec **không đổi** — cả 2 nền tảng vẫn thuộc feature này (FR-003), chỉ
khác thứ tự thực thi.

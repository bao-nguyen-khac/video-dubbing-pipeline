# Implementation Plan: Web UI cho Video Repurpose Pipeline

**Branch**: `002-web-ui` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-web-ui/spec.md`

## Summary

Xây dựng một lớp web mỏng (FastAPI backend + ReactJS frontend) bên trên pipeline
CLI đã có (001-video-repurpose-pipeline): người dùng đăng nhập bằng tài khoản cấu
hình qua `.env`, submit URL + chế độ kịch bản qua form, theo dõi tiến trình (%
ước lượng theo bước) qua polling, xem/tải video kết quả, xem lịch sử job, và
resume job lỗi — tất cả gọi lại đúng các module pipeline hiện có (`pipeline.py`,
`downloader/`, `asr/`, `script_gen/`, `tts/`, `merge/`), không viết lại logic xử
lý media. Chạy trên localhost, một job tại một thời điểm (không hàng đợi).

## Technical Context

**Language/Version**: Python 3.11+ (backend, đúng Constitution Principle I),
TypeScript/JavaScript (React frontend — ngoại lệ tường minh của Principle I,
Node.js chỉ dùng build-time).

**Primary Dependencies**:
- Backend: `fastapi`, `uvicorn` (ASGI server), `itsdangerous` (ký session cookie
  ~7 ngày theo Clarification 2026-07-26), reuse trực tiếp `pipeline.py` (import
  `create_job`, `read_job`, `run_pipeline` v.v. — không duplicate logic).
- Frontend: React + Vite (build tool), fetch API polling (không WebSocket — giữ
  đơn giản theo Principle V, đủ đáp ứng SC-002 vì % chỉ ước lượng theo bước).

**Storage**: Không có database mới. `jobs/{job_id}/job.json` vẫn là nguồn sự
thật duy nhất (Constitution Principle VI) — danh sách job (US2) lấy bằng cách
quét thư mục `jobs/`, không cần lưu trữ riêng cho web layer.

**Testing**: Không bắt buộc test tự động (theo đúng cách tiếp cận của spec 001).
`quickstart.md` làm kịch bản validate end-to-end thủ công qua trình duyệt.

**Target Platform**: Localhost (theo Clarification Q1 của spec) — `uvicorn`
bind `127.0.0.1`, không mở LAN/internet ở bản đầu. React build được FastAPI
serve như static file (1 process, 1 port) để đơn giản hoá triển khai.

**Project Type**: Web application (Option 2) — lần đầu tiên trong project có
tách `backend/`/`frontend/`, khác với Option 1 (single project) của feature 001.

**Performance Goals**: Trạng thái tiến trình phản ánh đúng trong 10 giây
(SC-002) → polling mỗi 3-5 giây là đủ. Trang tải xong dưới 3 giây (SC-005).

**Constraints**: Một job tại một thời điểm, submit mới bị chặn khi đang có job
chạy (FR-009, không hàng đợi). Đăng nhập bằng 1 cặp tài khoản/mật khẩu duy nhất
từ biến môi trường, phiên ~7 ngày (FR-010). Web layer KHÔNG được sửa đổi logic
xử lý media hiện có — chỉ import và gọi lại.

**Scale/Scope**: Single-user/local, không multi-tenant, không role-based access
— khớp trực tiếp với scope của spec 001.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Đánh giá | Ghi chú |
|---|---|---|
| I. Python-Only Stack (Backend & Pipeline) | ✅ PASS | Backend FastAPI = Python; frontend ReactJS dùng đúng ngoại lệ tường minh đã amend ở constitution v1.3.0 |
| II. Source-First, Fallback-Ready Downloading | ✅ PASS (N/A) | Feature này không đổi logic download, chỉ gọi lại `downloader/` hiện có qua `pipeline.run_pipeline()` |
| III. On-Demand AI Cleanup | ✅ PASS (N/A) | Không đổi hành vi `clean_video/detector.py` |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS | plan.md, research.md, data-model.md, contracts/, quickstart.md đều markdown thuần |
| V. Token & Context Economy | ✅ PASS | Chọn polling thay vì WebSocket, tái dùng `job.json` thay vì DB mới, tái dùng `pipeline.py` thay vì viết lại — giữ đúng mức cần thiết |
| VI. Agentic Harness Discipline | ✅ PASS (áp dụng ở bước tasks) | Sẽ chia nhỏ task verify-độc-lập ở `/speckit-tasks`, bám đúng plan này |

**Kết quả**: Không có vi phạm nào cần biện minh → Complexity Tracking để trống.

**Re-check sau Phase 1 (design)**: research.md thêm chi tiết implementation
(`uvicorn`, `itsdangerous`, `Vite`) nhưng đều là công cụ phụ trợ nằm trong phạm
vi 2 dòng đã khoá ở Technology Stack (FastAPI, ReactJS) — không phải quyết định
công nghệ mới cần thêm dòng riêng vào constitution. data-model.md/contracts/
quickstart.md không phát sinh vi phạm mới, toàn bộ 6 principle vẫn PASS.

## Project Structure

### Documentation (this feature)

```text
specs/002-web-ui/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   └── api.md
└── tasks.md              # Phase 2 output (/speckit-tasks — chưa tạo)
```

### Source Code (repository root)

```text
media-generation/
├── web/
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, mount routes + serve React build
│   │   ├── auth.py               # Kiểm tra login từ env, ký/verify session cookie
│   │   ├── jobs_api.py           # Endpoints: submit/list/detail/retry job (contracts/api.md)
│   │   └── job_runner.py         # Chạy pipeline.run_pipeline() trong background thread
│   └── frontend/
│       ├── package.json
│       ├── vite.config.ts
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── api/
│           │   └── client.ts     # fetch wrapper gọi backend
│           └── pages/
│               ├── LoginPage.tsx
│               ├── HomePage.tsx      # form submit + tiến trình (US1)
│               ├── JobListPage.tsx   # lịch sử job (US2)
│               └── JobDetailPage.tsx # chi tiết, cảnh báo, nút thử lại (US2/US3)
├── pipeline.py                  # (đã có, 001) — web/backend import trực tiếp
├── downloader/ asr/ script_gen/ tts/ merge/  # (đã có, 001) — không đổi
└── jobs/{job_id}/                # (đã có, 001) — vẫn là nguồn sự thật duy nhất
```

**Structure Decision**: Web application (Option 2) — tách `web/backend/` (FastAPI,
Python) và `web/frontend/` (React) theo đúng Constitution Project Structure đã
amend. Không đụng tới cấu trúc module pipeline hiện có của feature 001.

## Complexity Tracking

> Không có vi phạm Constitution Check nào cần biện minh — bảng này để trống.

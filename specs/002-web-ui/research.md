# Phase 0 Research: Web UI cho Video Repurpose Pipeline

Không còn `NEEDS CLARIFICATION` nào trong Technical Context. Tài liệu này chốt
các quyết định thiết kế phát sinh khi biến pipeline CLI (001) thành web service,
để Antigravity có đủ ngữ cảnh implement mà không cần đọc lại hội thoại gốc
(Constitution Principle IV).

## Backend framework

**Decision**: FastAPI + `uvicorn`.

**Rationale**: Đã khoá trong Constitution v1.3.0 (Technology Stack). Async-native
nên phù hợp để trả response nhanh trong khi job chạy nền; tự sinh OpenAPI docs
hữu ích cho frontend; hệ sinh thái Python nhất quán với Principle I.

**Alternatives considered**: Flask — bị loại vì không async-native, phải thêm
extension mới xử lý background task gọn tương đương.

## Chạy job nền (không block request)

**Decision**: `POST /api/jobs` tạo job rồi spawn `pipeline.run_pipeline()` trong
một `threading.Thread` riêng (daemon thread), trả response ngay với `job_id`.
Không dùng Celery/queue broker.

**Rationale**: `run_pipeline()` là hàm đồng bộ, chạy nhiều phút, gọi nhiều
subprocess (ffmpeg, demucs...) — không thể await trực tiếp trong event loop async
mà không block. Một thread riêng là đủ vì hệ thống chỉ chạy 1 job tại 1 thời điểm
(FR-009) — không cần cơ chế hàng đợi/broker phức tạp (Principle V).

**Alternatives considered**: Celery + Redis — bị loại, over-engineered cho nhu
cầu "1 job tại 1 thời điểm, single-user, localhost".

## Xác định "đang có job chạy" (cho FR-009)

**Decision**: Tại mỗi request `POST /api/jobs`, quét toàn bộ `jobs/*/job.json`
tìm job có `status` KHÔNG thuộc `{"done", "failed"}`. Nếu có → từ chối submit
mới (HTTP 409). KHÔNG dùng biến in-memory làm nguồn sự thật chính.

**Rationale**: `job.json` đã là nguồn sự thật duy nhất theo Constitution
Principle VI. Nếu chỉ dựa vào biến in-memory, backend restart giữa lúc job đang
chạy sẽ làm mất trạng thái "đang bận" (cho phép submit job mới đè lên job cũ dở
dang) — vi phạm chính guarantee mà FR-009 yêu cầu. Quét thư mục (tối đa vài chục
job) đủ rẻ để làm ở mỗi request, không cần cache phức tạp.

**Alternatives considered**: Lock file/in-memory flag riêng — bị loại vì tạo ra
2 nguồn sự thật có thể lệch nhau (file vs memory) sau khi backend restart.

## Tính % tiến trình (FR-003, đã chốt ở Clarification 2026-07-26)

**Decision**: Map tĩnh từ `job.json.status` sang %:

| status | % |
|---|---|
| pending | 0 |
| downloading | 15 |
| transcribing | 32 |
| scripting | 48 |
| synthesizing | 65 |
| merging | 82 |
| done | 100 |
| failed | giữ % của bước cuối cùng đã hoàn tất trước khi lỗi |

**Rationale**: Đã chốt qua clarify — ước lượng theo bước, không cần sửa từng
module pipeline để báo cáo tiến trình chi tiết bên trong.

## Cập nhật tiến trình phía frontend

**Decision**: Polling `GET /api/jobs/{job_id}` mỗi 3 giây khi có job đang chạy;
dừng poll khi status là `done`/`failed`.

**Rationale**: Đơn giản hơn WebSocket/SSE đáng kể (không cần quản lý kết nối
persistent, tự động hoạt động qua mọi reverse proxy/network), vẫn đáp ứng SC-002
(phản ánh đúng trong 10 giây) với biên độ thoải mái.

**Alternatives considered**: WebSocket — bị loại vì thêm độ phức tạp hạ tầng
(quản lý kết nối, reconnect logic) không cần thiết cho single-user localhost tool
(Principle V).

## Đăng nhập & phiên (FR-010, đã chốt ở Clarification 2026-07-26)

**Decision**: 1 cặp `WEB_UI_USERNAME`/`WEB_UI_PASSWORD` đọc từ `.env` (cùng cách
`ROUTER_API_KEY` hiện có). `POST /api/login` kiểm tra khớp, ký session token
bằng `itsdangerous` (`URLSafeTimedSerializer`), set làm HttpOnly cookie, hạn
7 ngày. Mọi endpoint khác require cookie hợp lệ (middleware), trả 401 nếu thiếu/
hết hạn/không hợp lệ.

**Rationale**: Không cần database user/session store — 1 secret ký token là đủ
cho 1 cặp tài khoản duy nhất, single-user tool. `itsdangerous` là thư viện nhỏ,
không kéo theo dependency nặng.

**Alternatives considered**: JWT với thư viện riêng (`python-jose`) — chức năng
tương đương nhưng nặng hơn cho nhu cầu 1-user; OAuth/SSO — quá mức cần thiết.

## Serve React build

**Decision**: Build React (`vite build`) ra static file, FastAPI serve qua
`StaticFiles` mount tại `/`, API tại `/api/*`. Một process, một port.

**Rationale**: Đơn giản hoá triển khai (Clarification Q1: chỉ chạy localhost) —
không cần CORS, không cần 2 process/port riêng cho dev vs prod.

**Alternatives considered**: Chạy Vite dev server riêng port + CORS — chỉ cần
trong lúc dev frontend, không phải kiến trúc production; note lại ở quickstart.md
cho luồng dev, nhưng cấu trúc chính vẫn theo "1 process serve cả 2".

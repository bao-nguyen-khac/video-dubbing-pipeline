# Implementation Plan: Hẹn giờ đăng video

**Branch**: `007-schedule-publish` | **Date**: 2026-07-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-schedule-publish/spec.md`

## Summary

Cho phép chọn "hẹn giờ" thay vì "đăng ngay" ở tab Đăng video: người dùng chọn
ngày giờ, hệ thống tải video lên Zernio ngay lúc đó rồi tạo bài kèm mốc thời
gian — **Zernio giữ bài và tự đăng khi tới giờ, máy người dùng không cần chạy**.
Kèm theo: danh sách bài đang chờ, huỷ bài trước giờ, và đối soát trạng thái khi
mở lại giao diện.

Đây là mở rộng của [006-publish-video-tab](../006-publish-video-tab/) — dùng lại
nguyên adapter Zernio, lớp lưu trữ file JSON và bảng ánh xạ lỗi đã có. Ba thay
đổi có rủi ro cao nhất, đã thiết kế sẵn: **tách nhánh runner** để bài hẹn giờ
không bị đánh thất bại nhầm, **quy đổi múi giờ tại đúng một biên**, và **huỷ
thật ở Zernio** thay vì chỉ đổi nhãn cục bộ.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript + React 18 (frontend)

**Primary Dependencies**: Không thêm gì mới — FastAPI, httpx, `zoneinfo` (thư
viện chuẩn của Python) cho múi giờ; React + react-router-dom ở frontend.

**Storage**: File JSON, mở rộng schema attempt sẵn có (xem [data-model.md](./data-model.md))

**Testing**: pytest (`tests/unit`) với HTTP tới Zernio được mock; verify thủ công
theo [quickstart.md](./quickstart.md)

**Target Platform**: Linux/macOS, chạy bằng uvicorn (người dùng tự triển khai)

**Project Type**: Web application (FastAPI backend + React SPA)

**Performance Goals**: Đối soát lười — attempt chưa tới giờ hẹn KHÔNG phát sinh
lời gọi Zernio nào, nên mở giao diện ở trạng thái bình thường tốn ~0 lời gọi.

**Constraints**: Hẹn tối thiểu 15 phút, tối đa 3 ngày; bài đang chờ tuyệt đối
không được đánh thất bại chỉ vì chưa tới giờ (FR-008); giờ hiển thị và giờ đăng
thật phải là một (SC-006); huỷ phải có hiệu lực thật ở Zernio (SC-004).

**Scale/Scope**: 1 người dùng, vài bài chờ cùng lúc — không cần hàng đợi hay
scheduler riêng.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Đối chiếu Constitution v1.7.0:

| Nguyên tắc | Kết quả | Ghi chú |
|---|---|---|
| I. Python-Only Stack | ✅ PASS | Logic ở module `publish/` (Python); React đúng ngoại lệ đã cho phép |
| II. Source-First Downloading | ✅ N/A | Không đụng download |
| III. On-Demand AI Cleanup | ✅ N/A | Không đụng cleanup |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS | spec/plan/research/data-model/contracts/quickstart đều markdown tự đủ nghĩa |
| V. Token & Context Economy | ✅ PASS | Không thêm dependency, không thêm scheduler nền — đối soát lười đủ đáp ứng SC-003 (research.md §4) |
| VI. Agentic Harness Discipline | ✅ PASS | Trạng thái truy vết qua file; test mock HTTP; **gọi thật Zernio phải hỏi người dùng trước**, và bài hẹn thử nghiệm phải được huỷ sau khi verify (quickstart §0) |

**Technology Stack**: Zernio đã có trong bảng từ v1.7.0, tính năng này không thêm
công nghệ nào ⇒ **không cần amend constitution**.

*Re-check sau Phase 1*: thiết kế cuối không phát sinh vi phạm mới. Không có mục treo.

## Project Structure

### Documentation (this feature)

```text
specs/007-schedule-publish/
├── plan.md              # File này
├── research.md          # Phase 0 — cơ chế hẹn giờ, múi giờ, tách runner, đối soát lười, huỷ thật
├── data-model.md        # Phase 1 — mở rộng Publish Attempt (publish_mode, scheduled_for, 2 trạng thái mới)
├── quickstart.md        # Phase 1 — 8 kịch bản verify (6 mock, 2 gọi thật)
├── contracts/
│   └── api.md           # Phase 1 — thay đổi API + ánh xạ sang Zernio
├── checklists/
│   └── requirements.md  # Từ /speckit-specify + /speckit-clarify (16/16 PASS)
└── tasks.md             # Phase 2 (/speckit-tasks — KHÔNG tạo ở lệnh này)
```

### Source Code (repository root)

Không thêm module mới ngoài 1 file — chỉ mở rộng những file đã có từ 006:

```text
publish/
├── zernio_client.py     # SỬA — create_post() nhận scheduled_for; thêm delete_post()
├── store.py             # SỬA — publish_mode/scheduled_for; trạng thái scheduled/cancelled;
│                        #        find_active_attempt tính cả scheduled; cancel_attempt()
├── limits.py            # SỬA — hằng số MIN_LEAD_TIME (15 phút) / MAX_LEAD_TIME (3 ngày)
├── runner.py            # SỬA — tách nhánh: hẹn giờ thì tạo bài rồi DỪNG, không poll
└── reconcile.py         # MỚI — đối soát lười attempt scheduled/publishing với Zernio

web/backend/
└── publish_api.py       # SỬA — POST /api/publish nhận publish_mode/scheduled_for;
                         #        DELETE /attempts/{id} (mới); DELETE /connections/{id}
                         #        huỷ kèm bài chờ; GET /attempts đối soát trước khi trả

web/frontend/src/
├── pages/PublishPage.tsx  # SỬA — chọn đăng ngay/hẹn giờ, nhập ngày giờ,
│                          #        danh sách đang chờ + nút huỷ
├── api/client.ts          # SỬA — thêm tham số lịch + hàm huỷ + type mở rộng
└── lib/labels.ts          # SỬA — nhãn trạng thái scheduled/cancelled, format giờ địa phương

tests/unit/
├── test_publish_schedule.py   # MỚI — biên thời gian, chống trùng, không-báo-thất-bại-nhầm
└── test_publish_reconcile.py  # MỚI — đối soát lười + huỷ (mock HTTP)
```

**Structure Decision**: Giữ nguyên bố cục của 006 — logic ở module Python cấp
repo, backend web là lớp HTTP mỏng, trạng thái là file JSON cạnh artifact của
job. File mới duy nhất là `publish/reconcile.py`, tách riêng vì đối soát là mối
quan tâm độc lập với việc *tạo* lượt đăng (`runner.py`) và với việc *lưu*
(`store.py`) — nhét vào một trong hai chỗ đó sẽ trộn hai trách nhiệm khác nhau.

## Complexity Tracking

Không có vi phạm cần biện minh. Không thêm dependency, không thêm tiến trình nền,
không thêm thực thể dữ liệu mới.

## Rủi ro đã nhận diện và cách xử lý

| Rủi ro | Xử lý |
|---|---|
| Bài hẹn giờ bị đánh **thất bại nhầm** sau 10 phút (lỗi có sẵn trong runner hiện tại) | Tách nhánh runner (research.md §3); KB4 của quickstart verify riêng ca này |
| Lệch **7 tiếng** do mặc định UTC của Zernio | Lưu và gửi UTC tuyệt đối, quy đổi đúng 1 biên (research.md §2); KB3 verify |
| Huỷ chỉ đổi nhãn cục bộ ⇒ **bài vẫn lên** | Gọi Zernio huỷ trước, ghi file sau (research.md §5); KB8 verify thật |
| Ngắt kết nối kênh nhưng bài đã hẹn **vẫn lên** | FR-015: huỷ kèm mọi bài chờ của kênh đó (research.md §6) |
| Video bị dọn khỏi kho tạm trước giờ đăng | Chốt trần hẹn 3 ngày (spec → Clarifications); tài liệu Zernio không công bố retention nên chọn mốc thận trọng |

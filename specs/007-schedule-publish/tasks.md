---

description: "Task list for 007-schedule-publish"
---

# Tasks: Hẹn giờ đăng video

**Input**: Design documents from `/specs/007-schedule-publish/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: Spec không yêu cầu TDD. Test ở đây **bắt buộc theo Constitution §VI**
(task chỉ đánh dấu xong khi verify được bằng bằng chứng) và **PHẢI mock HTTP** —
không test nào được gọi thật tới Zernio hay tạo bài hẹn giờ thật.

**Nền tảng đã có**: Tính năng này mở rộng
[006-publish-video-tab](../006-publish-video-tab/) (đã triển khai xong phần
TikTok đăng ngay). Mọi task dưới đây SỬA file đã tồn tại trừ khi ghi rõ MỚI.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1 = đặt lịch, US2 = xem/huỷ (spec.md)

## Path Conventions

Theo plan.md → Project Structure: `publish/` (Python cấp repo),
`web/backend/publish_api.py`, `web/frontend/src/pages/PublishPage.tsx`,
`tests/unit/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Hằng số biên thời gian + tiện ích múi giờ dùng chung cho mọi story

- [X] T001 [P] Thêm `MIN_SCHEDULE_LEAD_SECONDS = 15 * 60` và `MAX_SCHEDULE_LEAD_SECONDS = 3 * 24 * 3600` vào `publish/limits.py`, kèm hàm `check_schedule_time(scheduled_for: datetime, now: datetime | None = None) -> str | None` trả thông báo lỗi tiếng Việt (nêu rõ 15 phút / 3 ngày) hoặc `None` nếu hợp lệ (research.md §7, FR-003, FR-004)
- [X] T002 [P] Thêm hằng số `VN_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")` và 2 hàm quy đổi vào `publish/timezones.py` (MỚI): `to_utc_iso(local_naive: datetime) -> str` (giờ Việt Nam người dùng nhập → chuỗi ISO UTC `...Z` để lưu file + gửi Zernio) và `to_local_iso(utc_iso: str) -> str` (ngược lại, để hiển thị) — dùng `zoneinfo` chuẩn thư viện Python, không thêm dependency (research.md §2)
- [X] T003 [P] Unit test `tests/unit/test_timezones.py`: 20:00 giờ VN → `13:00Z` UTC và ngược lại; xử lý đúng khi input đã có `tzinfo` lẫn khi "trần" (naive)

**Checkpoint**: Hằng số + tiện ích múi giờ sẵn sàng, chưa đổi hành vi API

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Mở rộng store + adapter Zernio để chứa được lượt đăng hẹn giờ; runner tách nhánh đúng

**⚠️ CRITICAL**: Không bắt đầu Phase 3 trước khi phase này xong — mọi story đều cần các thay đổi này

- [X] T004 Mở rộng `publish/store.py::create_attempt()`: thêm tham số `publish_mode: str = "now"` và `scheduled_for: str | None = None`, ghi 2 field mới vào file attempt; đọc lại (`read_attempt`/`iter_attempts`) PHẢI mặc định `publish_mode="now"` cho file cũ (006) không có field này (data-model.md §1.1)
- [X] T005 Mở rộng `publish/store.py`: thêm `"scheduled"` vào `ACTIVE_STATUSES` (để `find_active_attempt()` chặn đặt lịch trùng — research.md §8); thêm hàm `cancel_attempt(job_id, attempt_id) -> dict` chuyển `status="cancelled"` (chỉ gọi SAU KHI đã huỷ thành công ở Zernio — không tự ý gọi bên trong store); thêm `list_scheduled_by_account(account_id) -> list[dict]` quét toàn bộ attempt `status="scheduled"` khớp `account_id` (dùng cho FR-015)
- [X] T006 [P] Mở rộng `publish/zernio_client.py::build_post_payload()` và `create_post()`: thêm tham số `scheduled_for: str | None = None`; khi có giá trị thì set `payload["scheduledFor"] = scheduled_for` + `payload["timezone"] = "Asia/Ho_Chi_Minh"` và **KHÔNG** set `publishNow` (ngược lại giữ nguyên `publishNow=True` như cũ) (contracts/api.md, research.md §1/§2)
- [X] T007 [P] Thêm `publish/zernio_client.py::delete_post(post_id: str) -> None`: gọi `DELETE /posts/{post_id}`; ánh xạ `400` (bài đã đăng, không xoá được) thành `ZernioError("platform_rejected", ...)`, `404` thì coi như đã xoá (không raise) — theo bảng lỗi ở contracts/api.md
- [X] T008 [US1] Tách `publish/runner.py::run_publish()` thành 2 nhánh theo `attempt["publish_mode"]`: nhánh `"now"` giữ nguyên hành vi cũ 100%; nhánh `"scheduled"` — upload video, gọi `create_post(..., scheduled_for=attempt["scheduled_for"])`, ghi `status="scheduled"` kèm `provider_post_id`, rồi **return ngay, KHÔNG gọi `_poll_until_done()`** (research.md §3 — đây là fix cho lỗi "báo thất bại nhầm" đã xảy ra thật nếu dùng chung nhánh poll)
- [X] T009 [P] Tạo `publish/reconcile.py` (MỚI): hàm `needs_reconcile(attempt: dict, now: datetime | None = None) -> bool` trả `True` khi (`status == "scheduled"` và đã qua `scheduled_for` trừ hao 1 phút) hoặc `status == "publishing"`; hàm `reconcile_attempt(attempt: dict) -> dict` gọi `zernio_client.get_post()` rồi cập nhật file theo bảng ánh xạ ở data-model.md §2 (`published`→`success`, `failed/partial/cancelled`→`failed`, `scheduled`/`publishing` giữ nguyên); lỗi `ZernioError` khi đối soát thì giữ nguyên trạng thái cũ, không tự đánh `failed` (research.md §4)
- [X] T010 [P] Unit test `tests/unit/test_publish_reconcile.py`: `needs_reconcile()` trả `False` khi còn xa giờ hẹn (không gọi Zernio); trả `True` khi đã qua giờ hoặc đang `publishing`; `reconcile_attempt()` với client mock chuyển đúng trạng thái theo từng ca của bảng ánh xạ; lỗi provider khi đối soát không làm mất trạng thái `scheduled` hiện có
- [X] T011 [P] Unit test `tests/unit/test_publish_runner_schedule.py`: nhánh `"scheduled"` của `run_publish()` dừng ở `status="scheduled"` **ngay cả khi chờ giả lập quá 10 phút** (tái hiện đúng bug đã phát hiện — KB4 quickstart); nhánh `"now"` không đổi hành vi so với test đã có ở 006

**Checkpoint**: Lớp dữ liệu + adapter + runner đã sẵn sàng cho hẹn giờ; chưa có endpoint/UI nào dùng tới

---

## Phase 3: User Story 1 — Đặt lịch đăng vào giờ mong muốn (Priority: P1) 🎯 MVP

**Goal**: Người dùng chọn video, chọn "hẹn giờ", nhập ngày giờ (giờ Việt Nam) —
bài được đăng đúng giờ trên Zernio kể cả khi hệ thống này đã tắt.

**Independent Test**: Chạy KB1–KB5 (mock, quickstart.md) rồi KB7 gọi thật — đặt
lịch, tắt server, tới giờ kiểm tra kênh.

### Backend

- [X] T012 [US1] Sửa `CreatePublishRequest` (Pydantic) trong `web/backend/publish_api.py`: thêm `publish_mode: str = "now"` và `scheduled_for: str | None = None` (nhận giờ **UTC** từ client — client tự quy đổi trước khi gửi, xem T017)
- [X] T013 [US1] Sửa `POST /api/publish` trong `web/backend/publish_api.py`: khi `publish_mode == "scheduled"` — validate có `scheduled_for`, parse ISO, chạy `limits.check_schedule_time()` (T001) trả `400` nếu vi phạm biên 15 phút/3 ngày; validate còn lại (tiêu đề, job done, giới hạn nền tảng, kênh chưa bị chặn, chống trùng qua `find_active_attempt` đã tính cả `scheduled`) giữ nguyên như 006 — tất cả kiểm **trước khi** gọi `store.create_attempt()` (FR-014, data-model.md §1.4)
- [X] T014 [US1] Sửa lời gọi `store.create_attempt()` và `runner.start_publish()` trong `POST /api/publish` để truyền `publish_mode`/`scheduled_for` xuống (nối với T004, T008)
- [X] T015 [US1] Thêm `DELETE /api/publish/attempts/{attempt_id}` trong `web/backend/publish_api.py`: đọc attempt, nếu không `status == "scheduled"` trả `409` (đã đăng → nêu rõ xoá trên nền tảng; đang `publishing` → nêu rõ không huỷ được nữa); nếu `scheduled` thì gọi `zernio_client.delete_post()` **TRƯỚC**, thành công mới gọi `store.cancel_attempt()`; `ZernioError` thì trả `502`, **KHÔNG** đổi trạng thái file (research.md §5, contracts/api.md)
- [X] T016 [US1] Sửa `GET /api/publish/attempts` và `GET /api/publish/attempts/{attempt_id}` trong `web/backend/publish_api.py`: với mỗi attempt trả về, gọi `reconcile.needs_reconcile()` (T009) và nếu `True` thì `reconcile.reconcile_attempt()` trước khi serialize (FR-009); thêm field `publish_mode`, `scheduled_for` vào response; hỗ trợ query `?status=` để lọc (contracts/api.md)

### Frontend

- [X] T017 [US1] `web/frontend/src/lib/labels.ts`: thêm `localDatetimeToUtcIso(value: string) -> string` và `utcIsoToLocalDatetime(value: string) -> string` cho input `<input type="datetime-local">` (giờ Việt Nam ở UI ↔ UTC gửi API) — dùng `Date`/`Intl` thuần, không cần thư viện ngoài vì chỉ 1 múi giờ cố định (research.md §2)
- [X] T018 [US1] `web/frontend/src/api/client.ts`: sửa `createPublish()` nhận thêm `publishMode?: "now" | "scheduled"` và `scheduledFor?: string` (UTC ISO); mở rộng type `PublishAttempt` với `publish_mode`, `scheduled_for`
- [X] T019 [US1] `web/frontend/src/pages/PublishPage.tsx`: thêm toggle "Đăng ngay / Hẹn giờ" trong form đăng; khi chọn hẹn giờ, hiện `<input type="datetime-local">` (giờ địa phương), quy đổi qua T017 trước khi gọi `createPublish()`; validate phía client biên 15 phút/3 ngày để phản hồi tức thời, nhưng **backend vẫn là nguồn sự thật** (T013)

### Verify (Constitution §VI)

- [X] T020 [P] [US1] Unit test `tests/unit/test_publish_schedule_api.py` (client Zernio mock): thiếu `scheduled_for` khi `publish_mode="scheduled"` → 400; hẹn quá khứ / <15 phút / >3 ngày → 400 kèm đúng thông báo; hẹn hợp lệ → 202, file attempt có `status="scheduled"`, `publish_mode="scheduled"`; 2 lần đặt lịch trùng job+platform (1 lần `scheduled`, 1 lần mới) → 409
- [X] T021 [US1] Chạy KB1–KB5 của quickstart.md (không gọi mạng thật), lưu output làm bằng chứng
- [ ] T022 [US1] ⚠️ **HỎI NGƯỜI DÙNG TRƯỚC** (Constitution §VI): chạy KB7 — đặt lịch ~20 phút sau, xác nhận hiện trong danh sách chờ, **tắt hẳn backend**, đợi qua giờ, kiểm tra kênh TikTok đã lên công khai đúng giờ ±5 phút (SC-001), bật lại backend và xác nhận `GET /api/publish/attempts/{id}` tự chuyển `success` kèm `post_url` (FR-009); lưu bằng chứng rồi dọn dẹp (video test là nội dung thật công khai, không xoá được)

**Checkpoint**: Đặt lịch hoạt động đầu-cuối, dùng thật được — có thể dừng ở đây và bàn giao

---

## Phase 4: User Story 2 — Xem và huỷ bài đã hẹn giờ (Priority: P2)

**Goal**: Người dùng thấy danh sách bài đang chờ và huỷ được trước giờ đăng;
ngắt kết nối kênh thì mọi bài chờ của kênh đó tự huỷ theo.

**Independent Test**: Chạy KB6 (mock) rồi KB8 gọi thật — đặt lịch, huỷ, chờ qua
giờ, xác nhận video KHÔNG lên kênh.

### Backend

- [X] T023 [US2] Sửa `DELETE /api/publish/connections/{account_id}` trong `web/backend/publish_api.py`: sau khi chặn cục bộ (như 006), gọi `store.list_scheduled_by_account()` (T005), với mỗi attempt gọi `zernio_client.delete_post()` rồi `store.cancel_attempt()`; gom kết quả vào `cancelled_attempts` trong response; attempt nào huỷ lỗi thì thêm vào `warning` thay vì chặn cả response (FR-015, contracts/api.md)

### Frontend

- [X] T024 [US2] `web/frontend/src/pages/PublishPage.tsx`: thêm khu vực "Đang chờ đăng" — gọi `GET /api/publish/attempts?status=scheduled`, sắp theo `scheduled_for` tăng dần, mỗi dòng có nút "Huỷ" gọi `DELETE /api/publish/attempts/{id}` rồi refetch (FR-010, FR-011)
- [X] T025 [US2] `web/frontend/src/pages/PublishPage.tsx`: khi `DELETE /connections/{id}` trả `cancelled_attempts` không rỗng, hiển thị rõ cho người dùng những bài nào vừa bị huỷ theo (FR-015)

### Verify (Constitution §VI)

- [X] T026 [P] [US2] Unit test `tests/unit/test_publish_cancel.py` (client mock): huỷ bài `scheduled` thành công → `cancelled`; Zernio lỗi khi huỷ → 502, trạng thái **giữ nguyên** `scheduled` (research.md §5); huỷ bài `success`/`publishing` → 409; ngắt kết nối kênh có 2 bài `scheduled` → cả 2 chuyển `cancelled`, response có đúng 2 phần tử trong `cancelled_attempts`
- [X] T027 [US2] Chạy KB6 của quickstart.md (mock), lưu bằng chứng
- [ ] T028 [US2] ⚠️ **HỎI NGƯỜI DÙNG TRƯỚC**: chạy KB8 — đặt lịch ~20 phút sau, huỷ trước giờ, đợi qua thời điểm đã hẹn, xác nhận video KHÔNG xuất hiện trên kênh (SC-004); lưu bằng chứng

**Checkpoint**: Cả đặt lịch lẫn huỷ hoạt động đầu-cuối, tính năng hoàn chỉnh

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T029 [P] Cập nhật `specs/006-publish-video-tab/../../README.md` (mục "Đăng video lên TikTok/YouTube Shorts"): thêm đoạn về hẹn giờ — biên 15 phút/3 ngày, bài đã hẹn vẫn lên khi tắt máy, huỷ chỉ có tác dụng trước giờ đăng
- [X] T030 Rà soát toàn bộ thông báo lỗi liên quan hẹn giờ: mọi lỗi biên thời gian nêu đúng con số (15 phút / 3 ngày) bằng tiếng Việt, không lộ chi tiết kỹ thuật (`scheduledFor`, `ZernioError`) ra UI
- [ ] T031 Cập nhật `specs/007-schedule-publish/checklists/requirements.md` với kết quả verify thật (T022, T028) và chạy lại toàn bộ quickstart.md một lượt cuối

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: không phụ thuộc gì, 3 task chạy song song được
- **Phase 2 (Foundational)**: phụ thuộc Phase 1 (T008 cần T002 để test múi giờ đã có sẵn, nhưng bản thân T004–T009 không cần chờ T001–T003 xong) — chặn toàn bộ Phase 3/4
- **Phase 3 (US1)**: phụ thuộc Phase 2. Đây là **MVP**, dừng được sau T022
- **Phase 4 (US2)**: phụ thuộc Phase 2 (dùng T005/T007), có thể làm song song với Phase 3 nếu chia người vì không đụng chung file, nhưng nên làm sau để tận dụng hạ tầng đã verify ở US1
- **Phase 5 (Polish)**: sau khi các chặng cần bàn giao đã xong

### Trong Phase 2

- T004, T005 cùng sửa `store.py` → làm tuần tự, không song song
- T006, T007 cùng sửa `zernio_client.py` nhưng khác hàm → có thể song song nếu cẩn thận merge, an toàn hơn thì làm tuần tự
- T008 phụ thuộc T004 (cần `attempt["publish_mode"]`) và T006 (cần `create_post(scheduled_for=...)`)
- T009 phụ thuộc T007 (dùng `delete_post`... thực ra reconcile chỉ cần `get_post` đã có từ 006) — chỉ phụ thuộc T004/T005 cho schema attempt
- T010, T011 chạy song song sau khi T008/T009 xong

### Trong Phase 3

- Backend trước frontend: T012–T016 → T017–T019
- T013 phụ thuộc T001 (limits) + T004 (store)
- T014 phụ thuộc T008 (runner nhánh scheduled)
- Verify (T020–T022) sau khi backend + frontend xong; T022 luôn là task cuối

### Parallel Opportunities

- T001, T002, T003 song song (Phase 1)
- T006, T007 song song (khác hàm, cùng file — cẩn trọng khi merge)
- T009, T010, T011 song song sau khi T008 xong
- T020 độc lập, chạy song song với việc viết T017–T019 nếu chia người
- T026 độc lập trong Phase 4

---

## Parallel Example: Phase 1

```bash
Task: "Thêm hằng số biên thời gian + check_schedule_time() trong publish/limits.py"
Task: "Tạo publish/timezones.py với to_utc_iso()/to_local_iso()"
Task: "Unit test tests/unit/test_timezones.py"
```

---

## Implementation Strategy

### MVP First (US1 — đặt lịch)

1. Phase 1: Setup
2. Phase 2: Foundational — **T008 là điểm mấu chốt**, tách đúng nhánh runner để tránh bug "báo thất bại nhầm"
3. Phase 3: US1
4. **DỪNG & VALIDATE**: KB1–KB5 (mock) rồi KB7 gọi thật (hỏi người dùng trước)
5. Bàn giao — người dùng đặt lịch đăng được ngay, kể cả khi tắt máy

### Incremental Delivery

1. Setup + Foundational → nền tảng sẵn sàng
2. + Phase 3 (US1) → đặt lịch được (MVP, giao trước)
3. + Phase 4 (US2) → xem/huỷ bài chờ, ngắt kênh huỷ theo
4. + Phase 5 → tài liệu, rà lỗi, chạy lại quickstart

---

## Notes

- **Kỷ luật gọi thật (Constitution §VI)**: mọi lượt gọi thật tới Zernio — đặt
  lịch thật, huỷ thật — PHẢI hỏi người dùng trước. Bài hẹn giờ vẫn lên **kể cả
  khi hệ thống này đã tắt**, nên "quên huỷ" là một bài đăng công khai thật.
- Test tự động **luôn** mock lớp HTTP; không test nào tạo bài hẹn giờ thật.
- Một task chỉ đánh dấu xong khi có bằng chứng cụ thể — đặc biệt T022/T028 cần
  bằng chứng **backend đã tắt** trong lúc chờ, không chỉ chạy xuyên suốt.
- File attempt cũ (006, trước tính năng này) không có `publish_mode` —
  T004 PHẢI đọc mặc định `"now"`, không được coi là lỗi dữ liệu.

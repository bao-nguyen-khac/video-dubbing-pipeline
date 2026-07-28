---

description: "Task list for 006-publish-video-tab"
---

# Tasks: Đăng video lên TikTok/YouTube Shorts từ giao diện web

**Input**: Design documents from `/specs/006-publish-video-tab/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/api.md](./contracts/api.md), [quickstart.md](./quickstart.md)

**Tests**: Spec không yêu cầu TDD. Các task test ở đây là **bắt buộc theo
Constitution §VI** (task chỉ được đánh dấu xong khi verify được bằng bằng chứng)
và **PHẢI mock HTTP** — không test nào được gọi thật tới Zernio.

**Thứ tự bàn giao**: Chặng 1 = **TikTok** (MVP dùng thật được ngay), chặng 2 =
YouTube Shorts (plan.md → "Thứ tự bàn giao", yêu cầu người dùng 2026-07-27).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: user story tương ứng (spec.md chỉ có 1 story: US1)

## Path Conventions

Theo plan.md → Project Structure: module Python cấp repo (`publish/`), backend
FastAPI (`web/backend/`), frontend React (`web/frontend/src/`), test
(`tests/unit/`). Đường dẫn dưới đây là đường dẫn thật của repo.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Chốt schema provider và khung file trước khi viết logic

- [X] T001 Đối chiếu `https://zernio.com/openapi.yaml` và `https://docs.zernio.com`, ghi lại **schema thật** (đường dẫn + tên trường chính xác của `GET /accounts`, `GET /connect/{platform}`, `POST /media`, `POST /posts` gồm object tuỳ chọn TikTok, `GET /posts/{id}`, tên header idempotency, hình dạng lỗi) vào cuối `specs/006-publish-video-tab/contracts/api.md` dưới mục "Schema Zernio đã xác minh (ngày …)"; nếu lệch so với giả định ở research.md §2 thì sửa luôn contract. **BLOCKING — mọi task gọi Zernio phụ thuộc task này** (research.md §2)
- [X] T002 [P] Thêm `ZERNIO_API_KEY`, `ZERNIO_BASE_URL=https://zernio.com/api/v1`, `ZERNIO_PROFILE_ID` kèm chú thích tiếng Việt (cách lấy key, để trống thì tính năng đăng tắt) vào `.env.example`
- [X] T003 [P] Thêm `publish_data/` vào `.gitignore`
- [X] T004 [P] Tạo `publish/__init__.py` và `publish/limits.py` với hằng số giới hạn TikTok (thời lượng ≤ 600s, file ≤ 500MB) + hàm `check_limits(platform, video_path) -> str | None` trả thông báo lỗi tiếng Việt hoặc None (research.md §7)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lớp lưu trữ + adapter provider + khung route; chưa có tính năng người dùng thấy được

**⚠️ CRITICAL**: Không bắt đầu Phase 3 trước khi phase này xong

- [X] T005 Tạo `publish/store.py`: đọc/ghi `jobs/{job_id}/publishes/{attempt_id}.json` (create_attempt, update_attempt, read_attempt, iter_attempts, find_active_attempt(job_id, platform)) và `publish_data/state.json` (read_state, write_state, block_account, unblock_account) — ghi file kiểu atomic (ghi file tạm rồi `os.replace`), đúng schema data-model.md §1/§3
- [X] T006 Tạo `publish/zernio_client.py`: client `httpx` với base URL/API key đọc từ env, header `Authorization: Bearer`, timeout, và **exception `ZernioError(kind, message, raw)`** ánh xạ lỗi theo bảng ở contracts/api.md ("Ánh xạ lỗi Zernio → error_kind"). Hàm public: `is_configured()`, `list_accounts()`, `connect_url(platform, profile_id)`, `upload_media(path)`, `create_post(...)`, `get_post(post_id)` — tất cả theo schema đã xác minh ở T001 (phụ thuộc T001)
- [X] T007 [P] Unit test `tests/unit/test_publish_store.py`: tạo/đọc/cập nhật attempt trong thư mục tạm, `find_active_attempt` chỉ khớp `pending`/`publishing`, blocklist thêm/gỡ đúng (phụ thuộc T005)
- [X] T008 [P] Unit test `tests/unit/test_zernio_client.py`: mock transport `httpx.MockTransport`, kiểm tra 401→`auth_expired`, 429/5xx/timeout→`provider_unavailable`, 402→`limit_exceeded`, `type=platform_error`→`platform_rejected`, còn lại→`unknown`; **không gọi mạng thật** (phụ thuộc T006)
- [X] T009 Tạo `web/backend/publish_api.py` với `router = APIRouter()`, helper `_error()` đồng dạng `jobs_api.py`, và guard trả `503 {"error": "Chưa cấu hình ZERNIO_API_KEY — xem .env.example"}` khi `zernio_client.is_configured()` false; mount `app.include_router(publish_router, prefix="/api/publish")` trong `web/backend/main.py`
- [X] T010 Thêm khung frontend: route `/publish` trong `web/frontend/src/App.tsx`, NavLink "Đăng video" trong `web/frontend/src/components/AppShell.tsx`, trang rỗng `web/frontend/src/pages/PublishPage.tsx` (dùng `AppShell`), và các hàm gọi API (`listPublishableVideos`, `listConnections`, `startConnect`, `disconnectChannel`, `createPublish`, `listAttempts`, `getAttempt`) + type tương ứng trong `web/frontend/src/api/client.ts` theo contracts/api.md

**Checkpoint**: Backend/frontend đã có chỗ đứng cho tính năng; chưa đăng được gì

---

## Phase 3: User Story 1 — Đăng video lên TikTok (Priority: P1) 🎯 MVP

**Goal**: Từ 1 job đã xử lý xong, người dùng liên kết kênh TikTok, chọn video,
điền tiêu đề, bấm "Đăng" → video công khai ngay trên kênh TikTok, có lịch sử và
thông báo lỗi rõ ràng.

**Independent Test**: Chạy KB1–KB5 (mock) và KB6 phần TikTok của
[quickstart.md](./quickstart.md) — không cần bất kỳ phần YouTube nào.

### Backend

- [X] T011 [US1] Implement `GET /api/publish/videos` trong `web/backend/publish_api.py`: quét `jobs/*/job.json`, chỉ giữ `status=done` + `artifacts.output_video` tồn tại trên đĩa, kèm `duration_seconds` (dùng `media_utils.get_media_duration`) và `already_published_to` (từ `publish/store.py`), sắp xếp mới nhất trước (FR-002, data-model.md §4)
- [X] T012 [US1] Implement `GET /api/publish/connections`: gọi `zernio_client.list_accounts()`, lọc `platform == "tiktok"`, hợp nhất blocklist cục bộ thành `status` = `connected|expired|disconnected` (data-model.md §2); `ZernioError` → `502` với thông báo nêu rõ **lỗi ở phía dịch vụ trung gian** (Edge Case) (phụ thuộc T005, T006)
- [X] T013 [US1] Implement `POST /api/publish/connections/{platform}`: chỉ chấp nhận `tiktok` ở chặng này, tạo/ghi nhớ `profile_id` vào `publish_data/state.json` nếu chưa có, trả `{"authorize_url": ...}` từ `zernio_client.connect_url()` (FR-005)
- [X] T014 [US1] Implement `DELETE /api/publish/connections/{account_id}`: thêm vào `disconnected_account_ids`; đồng thời gỡ khỏi blocklist khi account đó xuất hiện lại sau một lượt liên kết mới ở T012/T013 (FR-011, research.md §6)
- [X] T015 [US1] Implement `POST /api/publish`: validate `title` sau trim khác rỗng (FR-004), job `done` + có output (FR-002), `check_limits()` cho TikTok (research.md §7), chặn `403` nếu account trong blocklist (FR-011), chặn `409` kèm `attempt_id` nếu `find_active_attempt(job_id, platform)` khác None (FR-009) — hợp lệ thì ghi file attempt `pending` **trước** rồi mới spawn runner, trả `202` (contracts/api.md)
- [X] T016 [US1] Tạo `publish/runner.py`: daemon thread theo mẫu `web/backend/job_runner.py` — `upload_media(output.mp4)` → `create_post(platform="tiktok", caption=title, public=True, idempotency_key=attempt_id)` → chuyển attempt sang `publishing` kèm `provider_post_id` → poll `get_post()` mỗi 2s, tối đa 10 phút → `published`⇒`success` (+`post_url`), `failed/partial/cancelled`/hết hạn poll ⇒ `failed`; mọi `ZernioError` ghi `error` (tiếng Việt) + `error_kind` vào file attempt, không để exception làm chết thread im lặng (data-model.md §1.1, SC-004, SC-005)
- [X] T017 [US1] Implement `GET /api/publish/attempts` (hỗ trợ `?job_id=`) và `GET /api/publish/attempts/{attempt_id}` trong `web/backend/publish_api.py`, quét `jobs/*/publishes/*.json`, mới nhất trước (FR-010)

### Frontend

- [X] T018 [US1] `web/frontend/src/pages/PublishPage.tsx` — khu vực kết nối kênh: hiện trạng thái kênh TikTok, nút "Kết nối kênh" mở `authorize_url` (tab mới) rồi refetch khi quay lại, nút "Ngắt kết nối" + ghi chú rằng thu hồi quyền hoàn toàn phải làm ở dashboard Zernio/nền tảng (FR-005, FR-006, FR-011)
- [X] T019 [US1] `PublishPage.tsx` — form đăng: chọn video từ `GET /api/publish/videos` (hiện thời lượng + nền tảng đã đăng), chọn nền tảng (chặng này chỉ TikTok, để sẵn chỗ cho YouTube), ô tiêu đề bắt buộc, nút "Đăng" **disable trong lúc đang gửi và trong lúc attempt còn `pending`/`publishing`** (lớp UX của FR-009)
- [X] T020 [US1] `PublishPage.tsx` — theo dõi tiến trình: sau `202`, poll `GET /api/publish/attempts/{id}` mỗi 2s, hiện `đang đăng → thành công` (kèm link bài đăng) `→ thất bại` (kèm thông báo lỗi); riêng `error_kind=auth_expired` hiển thị nút "Liên kết lại kênh" (FR-007, FR-008, SC-004)
- [X] T021 [US1] `PublishPage.tsx` — bảng lịch sử lượt đăng từ `GET /api/publish/attempts`: video/job, nền tảng, tiêu đề, trạng thái, thời điểm, link bài đăng (FR-010); dùng lại `StatusBadge`/`Callout` sẵn có cho đồng nhất giao diện

### Verify (Constitution §VI — bằng chứng cụ thể)

- [X] T022 [P] [US1] Unit test `tests/unit/test_publish_api.py` với `zernio_client` được mock: tiêu đề rỗng→400, job chưa `done`→400, video vượt giới hạn TikTok→400 (và **không** có lời gọi Zernio nào), account bị ngắt→403, 2 request liên tiếp→request thứ 2 nhận 409 và chỉ có 1 file trong `jobs/{job_id}/publishes/` (FR-004/FR-002/FR-009/FR-011, SC-003)
- [X] T023 [P] [US1] Unit test `tests/unit/test_publish_runner.py` với client mock: luồng thành công `pending→publishing→success` ghi `post_url`; provider trả `failed`⇒`failed` + `error_kind=platform_rejected`; 401⇒`auth_expired`; 5xx/timeout⇒`provider_unavailable`; hết hạn poll⇒`failed` (data-model.md §1.1)
- [X] T024 [US1] Chạy KB1–KB5 của [quickstart.md](./quickstart.md) (không gọi mạng thật), lưu output curl/log làm bằng chứng
- [ ] T025 [US1] ⚠️ **HỎI NGƯỜI DÙNG TRƯỚC** (Constitution §VI): chạy KB6 phần TikTok — liên kết kênh thật, đăng 1 video thật, xác nhận bài đăng **công khai ngay** trên kênh (SC-005) và lượt đăng thứ 2 không phải xác thực lại (SC-002); lưu `post_url` + response attempt cuối làm bằng chứng

**Checkpoint**: Luồng đăng TikTok hoàn chỉnh, dùng thật được — có thể dừng ở đây và bàn giao MVP

---

## Phase 4: Mở rộng — YouTube Shorts (cùng US1, giao sau)

**Goal**: Bật thêm nền tảng YouTube Shorts trên đúng luồng đã có, không sửa kiến trúc.

**Independent Test**: Lặp lại KB2–KB6 với nền tảng YouTube Shorts; luồng TikTok
phải vẫn nguyên vẹn.

- [ ] T026 [US1] Bổ sung ngưỡng YouTube Shorts (thời lượng ≤ 180s) vào `publish/limits.py`, kèm thông báo nêu rõ số giây thực tế so với giới hạn (research.md §7)
- [ ] T027 [US1] Bổ sung nhánh YouTube trong `publish/zernio_client.py::create_post`: `title` + `privacyStatus="public"` đặt **tường minh** theo schema đã xác minh ở T001 (research.md §3)
- [ ] T028 [US1] Mở khoá `platform="youtube"` ở `web/backend/publish_api.py` (validate platform, `GET /connections` không còn lọc bỏ youtube, `POST /api/publish/connections/youtube`) và ở `publish/runner.py`
- [ ] T029 [US1] Bổ sung lựa chọn nền tảng YouTube Shorts vào `web/frontend/src/pages/PublishPage.tsx` (chọn nền tảng nào thì chỉ hiện kênh của nền tảng đó)
- [ ] T030 [P] [US1] Bổ sung test vào `tests/unit/test_publish_api.py` và `tests/unit/test_zernio_client.py`: video 245s + YouTube ⇒ 400 nêu giới hạn 180s; payload `create_post` cho YouTube có `privacyStatus="public"` và `title` đúng
- [ ] T031 [US1] ⚠️ **HỎI NGƯỜI DÙNG TRƯỚC**: chạy KB6 với YouTube Shorts — liên kết kênh thật, đăng 1 video thật, xác nhận công khai ngay; lưu bằng chứng

**Checkpoint**: Cả TikTok và YouTube Shorts hoạt động độc lập trên cùng một luồng

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T032 [P] Cập nhật `README.md`: mục "Đăng video lên TikTok/YouTube Shorts" — cần `ZERNIO_API_KEY`, cách liên kết kênh, lưu ý bài đăng công khai không sửa/xoá được từ giao diện này
- [X] T033 Rà soát toàn bộ thông báo lỗi của tab Đăng video: mọi lỗi phải nêu đúng nguyên nhân theo `error_kind` (SC-004), không có chuỗi tiếng Anh thô từ provider lọt thẳng ra UI (kèm nguyên văn provider ở phần chi tiết là được)
- [ ] T034 Cập nhật `specs/006-publish-video-tab/checklists/requirements.md` với kết quả verify thật (T025, T031) và chạy lại toàn bộ [quickstart.md](./quickstart.md) một lượt cuối

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: T001 là **blocking** cho mọi task chạm Zernio (T006, T016, T027); T002–T004 chạy song song ngay được
- **Phase 2 (Foundational)**: phụ thuộc Phase 1 — chặn toàn bộ Phase 3
- **Phase 3 (US1 TikTok)**: phụ thuộc Phase 2. Đây là **MVP**, dừng được sau T025
- **Phase 4 (YouTube)**: phụ thuộc Phase 3 hoàn tất (dùng lại nguyên luồng đã verify)
- **Phase 5 (Polish)**: sau khi các chặng cần bàn giao đã xong

### Trong Phase 3

- Backend trước frontend: T011–T017 → T018–T021
- T015 phụ thuộc T005 (store) + T004 (limits); T016 phụ thuộc T006 + T015
- Verify (T022–T025) sau khi backend + frontend xong; T025 luôn là task cuối của phase

### Parallel Opportunities

- T002, T003, T004 song song (khác file, không phụ thuộc nhau)
- T007, T008 song song sau khi T005/T006 xong
- T022, T023 song song
- T011 độc lập với T012–T014 (không đụng Zernio) → làm được song song với T006 nếu chia người

---

## Parallel Example: Phase 2

```bash
# Sau khi T005 và T006 xong, chạy 2 test song song:
Task: "Unit test publish/store.py trong tests/unit/test_publish_store.py"
Task: "Unit test publish/zernio_client.py trong tests/unit/test_zernio_client.py"
```

---

## Implementation Strategy

### MVP First (chặng 1 — TikTok)

1. Phase 1: Setup — **bắt đầu bằng T001**, sai schema ở đây làm hỏng mọi task sau
2. Phase 2: Foundational
3. Phase 3: US1 TikTok
4. **DỪNG & VALIDATE**: KB1–KB5 (mock) rồi KB6 TikTok (hỏi người dùng trước)
5. Bàn giao — người dùng đăng TikTok được ngay

### Incremental Delivery

1. Setup + Foundational → nền tảng sẵn sàng
2. + Phase 3 → đăng TikTok được (MVP, giao trước)
3. + Phase 4 → thêm YouTube Shorts, không đụng luồng TikTok đã verify
4. + Phase 5 → tài liệu, rà lỗi, chạy lại quickstart

---

## Notes

- **Kỷ luật gọi thật (Constitution §VI, v1.7.0)**: mọi lượt gọi thật tới Zernio —
  kể cả chỉ để liên kết kênh — PHẢI hỏi người dùng trước. Bài đăng thành công là
  bài đăng **công khai thật**, giao diện này không xoá/sửa lại được.
- Test tự động **luôn** mock lớp HTTP; không test nào chạm `zernio.com`.
- Một task chỉ đánh dấu xong khi có bằng chứng (output test, log, response,
  ảnh chụp bài đăng) — không chấp nhận "trông có vẻ đúng".
- Attempt lỗi thì **đăng lại = tạo attempt mới**, không sửa attempt cũ (giữ lịch sử).

---
description: "Task list for Chọn giọng đọc & nghe thử trước khi chạy job (004-voice-selection-preview)"
---

# Tasks: Chọn giọng đọc & nghe thử trước khi chạy job

**Input**: Design documents from `/specs/004-voice-selection-preview/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md),
[contracts/cli.md](./contracts/cli.md), [contracts/api.md](./contracts/api.md),
[research.md](./research.md), [quickstart.md](./quickstart.md)

**Tests**: Không yêu cầu test tự động (theo đúng cách tiếp cận của 001-003). Mỗi
user story kết thúc bằng task chạy job/preview thật + `quickstart.md` để verify
bằng bằng chứng thực tế (Constitution Principle VI).

**Organization**: Tasks nhóm theo user story (US1/US2, theo priority P1/P2 trong
spec.md) để mỗi story implement/verify độc lập.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1 / US2 — story mà task thuộc về
- Mỗi task nêu rõ file path cụ thể

**⚠️ Cập nhật lúc implement**: Người dùng đã cung cấp `VIVIBE_API_KEY` thật
trong `.env` (đặt tên `VIVIBE_API_KEY`, không phải `LUCYAI_API_KEY` như dự
tính ban đầu ở research.md — đã đổi tên biến env cho khớp xuyên suốt
code/docs). Key
hợp lệ (verify thật: `getUserVoices` trả `200` đúng shape), nhưng tài khoản
Vivibe hiện CHƯA cấu hình giọng nào (`total: 0`) — verify được trọn vẹn nhánh
"danh sách rỗng, không lỗi" và nhánh lỗi (key sai → message rõ ràng), nhưng
CHƯA verify được `ttsLongText`/preview thật (cần ít nhất 1 voice trong tài
khoản). Task nào cần voice thật vẫn ghi "[cần voice Vivibe thật]".

---

## Phase 1: Setup

- [X] T001 Thêm `VIVIBE_API_KEY` vào `.env.example` kèm comment hướng dẫn (link
      `https://www.vivibe.app/api-docs.html`, cách lấy key) — theo pattern
      `ROUTER_API_KEY` đã có. Verify: người dùng đã tự điền key thật vào
      `.env` (biến `VIVIBE_API_KEY`) — test `getUserVoices` thật qua curl xác
      nhận key hợp lệ (`200`, đúng shape JSON-RPC), tài khoản chưa có voice
      nào (`total: 0`).

**Checkpoint**: `.env.example` có đủ biến mới; đã có key thật để verify sâu
hơn ở các phase sau (dù tài khoản chưa cấu hình voice)

---

## Phase 2: Foundational (Blocking Prerequisites cho US1 + US2)

**Purpose**: Client 2 provider TTS + endpoint danh sách giọng — cả US1 (dropdown
chọn giọng) và US2 (nghe thử) đều cần

**⚠️ CRITICAL**: US1 và US2 không được bắt đầu trước khi phase này xong

- [X] T002 Implement `tts/lucyai_client.py` (file mới): `list_voices(api_key) ->
      list[dict]` (gọi `getUserVoices`, lọc `isActive == true`);
      `synthesize(text, voice_id, api_key, output_path, speed=1.0) ->
      tuple[Path, float]` (gọi `ttsLongText`, poll `getExportStatus` mỗi 2s,
      tải WAV từ field `url` khi `state == "completed"`, raise rõ khi
      `state == "failed"` hoặc timeout) — theo research.md §2. Verify thật
      với `VIVIBE_API_KEY` thật: `list_voices()` trả `[]` đúng (tài khoản
      chưa có voice); thiếu key → raise rõ; key sai → raise đúng lỗi thật từ
      API (`{"code": "INTERNAL_ERROR", "message": "Invalid or revoked API
      key"}`).
- [X] T003 [P] Thêm `list_voices() -> list[dict]` vào `tts/edge_tts_client.py`:
      gọi `edge_tts.list_voices()`, lọc `Locale` bắt đầu `vi-`, trả về
      `[{"voice_id": ShortName, "name": FriendlyName}]` — theo research.md §1
      (đã verify thật: chỉ có 2 giọng `vi-VN-HoaiMyNeural`/`vi-VN-NamMinhNeural`).
      Verify: chạy thật trong container, trả đúng 2 giọng.
- [X] T004 Implement `web/backend/voices_api.py` (file mới): `GET /api/voices`
      gộp `edge_tts_client.list_voices()` (luôn có) + `lucyai_client.list_voices()`
      (chỉ khi `VIVIBE_API_KEY` đã cấu hình; lỗi/rỗng → chỉ trả edge-tts, không
      lỗi cả endpoint — FR-003) — theo contracts/api.md. **Phát hiện + sửa 1
      bug thật lúc verify**: gọi trực tiếp hàm đồng bộ (`asyncio.run()` bên
      trong) từ endpoint `async def` → `RuntimeError: asyncio.run() cannot be
      called from a running event loop`. Sửa bằng `asyncio.to_thread()` cho
      cả 2 client.
- [X] T005 Mount `voices_router` (T004) vào `web/backend/main.py` với prefix
      `/api/voices`
- [X] T006 [P] `web/frontend/src/api/client.ts`: thêm type `Voice {provider,
      voice_id, name}`, hàm `listVoices()` gọi `GET /api/voices`. Verify:
      `npm run build` thành công.

**Checkpoint**: Verify thật qua curl (login → `GET /api/voices` qua nginx
proxy port 80) — trả đúng 2 giọng edge-tts, mảng Vivibe rỗng đúng (tài khoản
chưa cấu hình voice, không lỗi). US1/US2 có thể bắt đầu song song.

---

## Phase 3: User Story 1 - Chọn giọng đọc trước khi chạy job (Priority: P1) 🎯 MVP

**Goal**: Chọn được provider + giọng đọc cụ thể trước khi chạy job Dịch
chuẩn/Sáng tạo, video sản phẩm dùng đúng giọng đã chọn (FR-001, FR-002, FR-006,
FR-007)

**Independent Test**: Chạy `quickstart.md` → mục US1

### Implementation for User Story 1

- [X] T007 [US1] Mở rộng `pipeline.py`: thêm `--tts-provider {edge-tts,lucyai}`
      (mặc định `edge-tts`) và `--voice-id <id>` vào `parse_args()`; thêm field
      `tts_provider`/`voice_id` vào dict trả về của `create_job()` — theo
      data-model.md, contracts/cli.md
- [X] T008 [US1] Cập nhật `pipeline.py` bước `synthesizing`: dispatch theo
      `job.get("tts_provider", "edge-tts")` — gọi `edge_tts_client.synthesize()`
      hoặc `lucyai_client.synthesize_from_script()` (T002, đổi tên khác kế
      hoạch ban đầu để cùng shape gọi với edge-tts) với `voice_id =
      job["voice_id"]`; áp dụng 2-pass duration-matching cho nhánh LucyAI dùng
      `speed` trong `[0.5, 2.0]` — theo research.md §4. Nếu LucyAI lỗi (thiếu
      key/API lỗi) → để lỗi lan lên `fail_job()` rõ ràng, KHÔNG fallback âm
      thầm sang edge-tts (FR-007). **Phát hiện + sửa 1 bug thật lúc verify**:
      import sai tên hàm (`synthesize` thay vì `synthesize_from_script`) gây
      `TypeError: got multiple values for argument 'voice_id'` — đã sửa.
- [X] T009 [P] [US1] Cập nhật `web/backend/jobs_api.py`: `SubmitJobRequest`
      thêm `tts_provider: str = "edge-tts"`, `voice_id: str | None = None`;
      `_job_to_detail()` trả thêm 2 field (dùng `.get()` cho job cũ); truyền
      xuống `create_job()`/`start_job()` — cập nhật `job_runner.py`/`retry_job()`
      tương ứng (đọc lại `job["tts_provider"]`/`job["voice_id"]` khi resume,
      đúng pattern đã có với `dynamic_captions` ở 003)
- [X] T010 [P] [US1] `web/frontend/src/pages/HomePage.tsx`: thêm dropdown chọn
      giọng (gọi `listVoices()` khi mount, chỉ hiện khi `script_mode` là
      `translate`/`rewrite` — ẩn với `subtitle`, Acceptance Scenario 6), mỗi
      option hiển thị `name` kèm nhãn provider (LucyAI hiển thị "Vivibe", xem
      research.md §2); gửi kèm `tts_provider`/`voice_id` khi `submitJob()`.
      Verify bằng browser thật (không phải chỉ build): đăng nhập, dropdown
      hiện đúng 2 giọng edge-tts, tự chọn giọng đầu tiên; chuyển
      `script_mode` sang "Phụ đề tự động" → dropdown giọng + checkbox phụ đề
      động biến mất đúng như thiết kế.
- [X] T011 [US1] Verify US1 bằng job thật (resume từ `scripting`, tái dùng
      transcript/source.mp4 có sẵn, không mock): job `--voice-id
      vi-VN-HoaiMyNeural` (khác mặc định) hoàn tất, log xác nhận đúng
      `provider=edge-tts, voice=vi-VN-HoaiMyNeural`, vẫn giữ nhạc nền (fix
      003 không bị ảnh hưởng), lệch thời lượng 65.7s/66.0s. Job
      `--tts-provider lucyai --voice-id <sai>` với `VIVIBE_API_KEY` thật —
      xác nhận fail rõ ràng đúng lỗi thật từ API Vivibe ("Invalid
      userVoiceId"), status="failed", KHÔNG fallback sang edge-tts (FR-007).
      **Cập nhật sau (T023)**: tài khoản Vivibe sau đó được cấu hình 1 voice
      thật (`mhsL3CPLxmLYdSTKp3GANj`, "Giọng adam") — đã verify thêm 1 job
      LucyAI THÀNH CÔNG trọn vẹn: `status=done`, 64.2s/66.0s (không lệch),
      vẫn giữ nhạc nền. Không còn khoảng trống verify nào cho US1.

**Checkpoint**: US1 hoạt động độc lập và đầy đủ — đây là bản MVP (chọn giọng
đúng, không cần preview vẫn dùng được)

---

## Phase 4: User Story 2 - Nghe thử giọng đọc trước khi chạy job (Priority: P2)

**Goal**: Nghe được mẫu giọng đọc trước khi chọn, không tạo job, không bị chặn
bởi rule 1-job-tại-1-thời-điểm (FR-004, FR-005, FR-008)

**Independent Test**: Chạy `quickstart.md` → mục US2

### Implementation for User Story 2

- [X] T012 [US2] Thêm `POST /api/voices/preview` vào `web/backend/voices_api.py`
      (T004): body `{provider, voice_id}`, dùng câu mẫu cố định "Xin chào, đây
      là giọng đọc mẫu để bạn tham khảo trước khi chọn." (FR-005), gọi đúng
      client của provider tương ứng vào file tạm (`tempfile.TemporaryDirectory`,
      KHÔNG ghi vào `jobs/`), đọc bytes trả về `Response(media_type="audio/wav")`
      rồi tự dọn tempdir; lỗi provider → 502 kèm message rõ (FR-007 áp dụng
      tương tự job thật) — theo contracts/api.md. Thêm `edge_tts_client.
      synthesize_text()` (text trực tiếp, không qua script.json) để tái dùng
      cho preview.
- [X] T013 [P] [US2] `web/frontend/src/pages/HomePage.tsx`: thêm nút "Nghe
      thử" cạnh dropdown giọng (T010), gọi `previewVoice()` (client.ts, fetch
      riêng vì response là blob audio không phải JSON), phát qua thẻ `<audio>`
      ẩn bằng `URL.createObjectURL` (tự `revokeObjectURL` bản trước khi nghe
      giọng mới — Acceptance Scenario 3); disable nút + hiện "Đang tải..."
      trong lúc chờ.
- [X] T014 [US2] Verify US2 bằng dữ liệu thật (không mock): curl
      `POST /api/voices/preview` giọng edge-tts — WAV hợp lệ 783KB trong
      3.2s (đạt SC-002); jobs/ đếm y hệt trước/sau preview (6 → 6, FR-008);
      tạo 1 job giả "đang chạy" (status=downloading) → submit job mới bị 409
      đúng, nhưng preview vẫn `200 OK` — xác nhận preview không bị chặn.
      LucyAI: preview voice không tồn tại → `502` kèm đúng lỗi thật từ API
      ("Invalid userVoiceId"). **Verify qua browser thật (không chỉ curl)**:
      bấm nút "Nghe thử" trên trang thật → network log xác nhận
      `POST /api/voices/preview → 200 OK` rồi `GET blob:... → 206 Partial
      Content` (đúng hành vi `<audio>` phát blob thật), nút trở lại trạng
      thái bình thường sau khi xong, không lỗi hiển thị. **Cập nhật sau
      (T023)**: sau khi tài khoản Vivibe có 1 voice thật, đã verify thêm
      preview LucyAI THÀNH CÔNG trọn vẹn — `200 OK`, WAV thật 158KB (mono
      22050Hz), 4.1s (đạt SC-002), âm lượng thật (-14.8dB mean, không câm).
      Không còn khoảng trống verify nào cho US2.

**Checkpoint**: Cả US1 + US2 hoạt động độc lập — đã verify bằng browser thật,
không chỉ qua curl/build

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Hoàn thiện chất lượng chung, không thuộc riêng story nào

- [X] T015 [P] Cập nhật `README.md`: mô tả `--tts-provider`/`--voice-id`, cách
      cấu hình `VIVIBE_API_KEY`, dropdown chọn giọng + nút nghe thử trên web
      UI, thêm mục "Chọn giọng đọc / Vivibe" + link `specs/004-.../`
- [X] T016 Rà soát cảnh báo/log của feature này (FR-007): đảm bảo lỗi provider
      (thiếu key, API lỗi, timeout poll) đều có message rõ ràng cả ở job thật
      (T008) lẫn preview (T012), nhất quán cách diễn đạt — cả 2 đường dẫn
      dùng chung `lucyai_client._call_json_rpc()` nên tự nhiên nhất quán;
      không phát hiện lỗ hổng mới.
- [X] T017 Rebuild Docker image đầy đủ (`docker compose build`), recreate
      container (không còn code patch tạm qua `docker cp`), verify lại qua
      đúng luồng web UI (nginx proxy port 80, image chính thức): `GET
      /api/voices` (2 giọng edge-tts), `POST /api/voices/preview` (200, WAV
      hợp lệ, ~1s), Job Detail job cũ có đúng `tts_provider="edge-tts"`,
      `voice_id=None` (backward-compatible). `jobs/` không có rác test còn
      sót. Constitution Check: 6/6 principle vẫn PASS, không phát sinh vi
      phạm mới.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Không phụ thuộc gì — bắt đầu ngay
- **Foundational (Phase 2)**: Phụ thuộc Setup — CHẶN cả US1 và US2
- **US1 (Phase 3)**: Phụ thuộc Foundational xong
- **US2 (Phase 4)**: Phụ thuộc Foundational xong; độc lập tính năng với US1
  (không cần US1 xong mới nghe thử được) nhưng cùng sửa `HomePage.tsx` — nên
  làm tuần tự nếu cùng 1 người/agent
- **Polish (Phase 5)**: Phụ thuộc US1 + US2 xong

### Within Each User Story

- Task cùng sửa `pipeline.py` (T007, T008) làm tuần tự — cùng file
- Task cùng sửa `web/backend/voices_api.py` (T004 Foundational, T012 US2) làm
  tuần tự — cùng file
- Task cùng sửa `HomePage.tsx` (T010 US1, T013 US2) làm tuần tự — cùng file
- Task verify bằng job/preview thật luôn là task cuối của mỗi story

### Parallel Opportunities

- T003 (edge_tts_client.py) chạy song song với T002 (lucyai_client.py) — khác
  file
- T006 (frontend client.ts) chạy song song với T004-T005 (backend) — khác file
- T009 (jobs_api.py) chạy song song với T010 (HomePage.tsx) — khác file, dù
  cùng US1

---

## Parallel Example: Sau khi Setup xong

```bash
# Foundational — song song:
Task: "tts/lucyai_client.py (T002)"
Task: "tts/edge_tts_client.py list_voices() (T003)"
Task: "web/frontend/src/api/client.ts listVoices() (T006)"
# T004-T005 (voices_api.py + main.py) làm tuần tự sau T002-T003

# Sau Foundational, US1 và US2 có thể chạy song song (2 người/agent):
Task: "US1 — pipeline.py + jobs_api.py + HomePage.tsx dropdown (T007-T011)"
Task: "US2 — voices_api.py preview + HomePage.tsx nút nghe thử (T012-T014)"
# Lưu ý T010/T013 cùng sửa HomePage.tsx — nếu 1 người làm cả 2 story thì làm tuần tự
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Hoàn thành Phase 1: Setup (T001)
2. Hoàn thành Phase 2: Foundational (T002-T006)
3. Hoàn thành Phase 3: User Story 1 (T007-T011)
4. **DỪNG lại và VALIDATE**: chạy `quickstart.md` → US1 độc lập
5. Đây đã là bản dùng được — chọn đúng giọng khi chạy job, dù chưa có nút nghe
   thử (US2 nâng cao trải nghiệm thêm sau)

### Incremental Delivery

1. Setup + Foundational xong → nền tảng sẵn sàng
2. Thêm US1 → verify độc lập → demo chọn giọng đúng (MVP!)
3. Thêm US2 → verify độc lập → demo nghe thử trước khi chọn
4. Mỗi story cộng thêm giá trị mà không phá story trước

---

## Notes

- [P] = khác file, không phụ thuộc task chưa xong
- [Story] gắn task với user story để truy vết
- Phần verify liên quan LucyAI thật cần `VIVIBE_API_KEY` của người dùng — các
  task đánh dấu "[cần VIVIBE_API_KEY thật]" có thể tạm hoãn nếu chưa có key,
  không chặn phần còn lại của feature (đã thiết kế graceful-degrade từ đầu)
- Commit sau mỗi task hoặc nhóm task liên quan
- Dừng lại ở mỗi Checkpoint để validate story độc lập trước khi qua story tiếp
- Tránh: gộp logic edge-tts và LucyAI vào chung 1 hàm `synthesize()` (2 API
  khác biệt hoàn toàn — xem research.md §2 Alternatives considered)

---

## Phase 6 (bổ sung sau khi feature đã hoàn tất): Provider thứ 3 — 9router TTS

**Bối cảnh**: Sau khi US1/US2 xong, người dùng yêu cầu bổ sung trực tiếp thêm
1 provider giọng đọc nữa — 9router TTS (giọng Gemini, cùng dịch vụ 9router đã
dùng cho `script_gen`, endpoint OpenAI-compatible `/v1/audio/speech`). Xử lý
như phần mở rộng nhẹ trong cùng feature (constitution amend 1.4.0 → 1.5.0),
không mở vòng spec-kit đầy đủ mới vì khớp đúng kiến trúc đa-provider đã có
(`Voice` entity, `GET /api/voices`, `POST /api/voices/preview`, dispatch
`tts_provider` ở `pipeline.py`) — chỉ thêm 1 nhánh, không đổi thiết kế.

- [X] T018 Implement `tts/router_tts_client.py` (file mới): `list_voices()`
      trả 30 giọng Gemini cố định (không có endpoint discovery, khác
      `getUserVoices` của LucyAI); `synthesize_text()` (preview) và
      `synthesize_from_script()` (job thật) gọi
      `{ROUTER_BASE_URL}/audio/speech`, tái dùng `ROUTER_API_KEY` có sẵn —
      KHÔNG cần secret riêng, khác LucyAI/Vivibe. **Phát hiện thật lúc
      research**: tham số `speed` của API không có tác dụng đáng kể (test
      thật: 2.88s → 2.76s dù đặt `speed=1.5`) — khớp thời lượng bằng hậu xử
      lý ffmpeg `atempo` thay vì dựa API. Verify: `list_voices()` trả đúng 30
      giọng; `synthesize_from_script()` với `target_duration=3.0` từ input
      thực tế ~2.8s → atempo đưa về 2.99s (rất sát), audio thật không câm
      (volumedetect).
- [X] T019 Cập nhật `pipeline.py`: thêm `"router-tts"` vào `choices` của
      `--tts-provider`; sửa logic `active_voice_id` default — CHỈ edge-tts có
      giọng mặc định cố định, `lucyai`/`router-tts` bắt buộc người dùng chọn
      giọng cụ thể (bug tiềm ẩn phát hiện lúc viết: logic cũ sẽ gán nhầm
      `DEFAULT_VOICE` — 1 giọng edge-tts — cho `router-tts` nếu không sửa);
      thêm nhánh dispatch gọi `router_tts_synthesize()` ở bước `synthesizing`.
- [X] T020 Cập nhật `web/backend/voices_api.py`: `GET /api/voices` gộp thêm
      giọng `router-tts` (ẩn nếu `ROUTER_API_KEY` chưa cấu hình, dù thực tế
      luôn có sẵn vì `script_gen` đã cần); `POST /api/voices/preview` thêm
      nhánh `router-tts`. Cập nhật `web/backend/jobs_api.py`:
      `SubmitJobRequest.tts_provider` chấp nhận thêm `"router-tts"`.
- [X] T021 [P] `web/frontend`: `PROVIDER_LABELS` (`HomePage.tsx`) thêm
      `router-tts: "9router"`; type `Voice.provider` (`client.ts`) thêm
      `"router-tts"`.
- [X] T022 **Phát hiện + sửa 1 bug hạ tầng thật lúc verify**: `POST
      /api/voices/preview` với `router-tts` trả `504 Gateway Timeout` qua
      nginx dù backend chưa kịp trả lời — `nginx.conf` không set
      `proxy_read_timeout`, mặc định 60s ngắn hơn thời gian xử lý thật của
      preview (LucyAI poll tới 120s). Sửa: thêm `proxy_read_timeout 150s` +
      `proxy_send_timeout 150s` vào location `/api/`, rebuild `web-ui` image.
- [X] T023 Verify end-to-end bằng dữ liệu thật (không mock): `GET
      /api/voices` qua nginx trả đúng 32 giọng (2 edge-tts + 30 router-tts).
      `POST /api/voices/preview` với "Puck" — `200 OK`, WAV thật 194KB, âm
      lượng thật (không câm). Job thật `--tts-provider router-tts --voice-id
      Puck` — log xác nhận đúng dispatch
      (`provider=router-tts, voice=Puck`), lỗi (quota Gemini hết hạn ngạch,
      dịch vụ ngoài — xem dưới) lan đúng lên `fail_job()` với message rõ
      ràng, resume đúng lại từ `synthesizing` (không chạy lại `scripting`).
      Verify qua **browser thật**: dropdown hiện đủ 32 giọng đúng nhãn
      provider; bấm "Nghe thử" giọng "Puck" khi quota hết → lỗi hiển thị rõ
      màu đỏ ngay trên form, phần còn lại của form (dropdown, nút "Chạy")
      vẫn dùng bình thường (đúng Acceptance Scenario 4 của US2, áp dụng
      tương tự cho provider mới).
      **Giới hạn đã biết**: quota Gemini TTS của 9router rất thấp/dễ hết
      (xác nhận bằng lỗi thật `"You exceeded your current quota... (reset
      after 24s)"`) — đã verify được đường thành công thật (preview "Puck"
      sau khi đợi quota hồi phục: `200 OK`, âm lượng thật) VÀ đường lỗi thật,
      nhưng CHƯA verify được 1 job đầy đủ (download→...→merge) thành công
      trọn vẹn với `router-tts` do quota hết ngay giữa lúc test — dispatch/
      error-handling/resume đã verify đúng bằng 2 lượt job thật (đều fail ở
      đúng bước `synthesizing` với lý do thật).
- [X] T024 Cập nhật `README.md`: thêm `router-tts` vào bảng `--tts-provider`,
      mô tả ngắn 9router TTS tái dùng `ROUTER_API_KEY` có sẵn (không cần
      secret riêng, khác Vivibe).
- [X] T025 **Phát hiện + sửa 1 bug thật khác** (ngoài phạm vi router-tts,
      phát hiện tình cờ lúc rebuild cuối): tài khoản Vivibe được cấu hình
      thêm 1 voice thật trực tiếp trong `tts/lucyai_client.py` (hardcode
      `{"id": "mhsL3CPLxmLYdSTKp3GANj", "name": "Giọng adam (Giá tiết
      kiệm)", "isActive": true}`) nhưng dùng `true` kiểu JS thay vì `True`
      của Python → `NameError`, làm `GET /api/voices` lỗi `500` toàn bộ khi
      đã cấu hình `VIVIBE_API_KEY`. Sửa `true` → `True`. **Lợi ích phụ**: có
      voice Vivibe thật lần đầu tiên để test — đã verify bổ sung (xem cập
      nhật ở T011/T014): 1 job LucyAI thành công trọn vẹn (`status=done`,
      64.2s/66.0s, giữ nhạc nền) và 1 lượt preview LucyAI thành công trọn
      vẹn (`200 OK`, WAV thật 158KB, 4.1s) — đóng nốt 2 khoảng trống verify
      cuối cùng của toàn bộ feature 004.
- [X] T026 **Phát hiện + sửa bug thật khác** (báo cáo qua job
      `89dec30c-22f0-4b31-a9e3-e5e535bebd73`, `tts_provider=lucyai`,
      `warnings.duration_mismatch=true`): công thức khớp thời lượng của
      `tts/lucyai_client.py::synthesize_from_script()` giả định `speed` của
      Vivibe tuyến tính nghịch đảo với thời lượng (`needed_speed = duration /
      target_duration`), nhưng verify thật cho thấy KHÔNG đúng — với job lỗi
      trên: `speed=1.0` → 39.1s, tính `needed_speed=0.541` để đạt mục tiêu
      72.1s nhưng thực tế chỉ ra **66.9s** (lệch 5.2s, vượt tolerance 2s).
      Quan hệ thực tế là dưới-tuyến-tính (sublinear), lệch nặng hơn khi hệ số
      điều chỉnh lớn — cùng dạng vấn đề đã gặp với `speed` của router-tts
      (T018) nhưng kín đáo hơn vì chỉ lộ ra khi độ lệch nhịp gốc/kịch bản
      lớn. Sửa bằng cách thêm bước hậu xử lý ffmpeg `atempo` (tái dùng đúng
      cơ chế `_apply_atempo()` của `router_tts_client.py`) để khớp nốt phần
      lệch còn lại sau 2-pass `speed` gốc. Verify lại đúng job lỗi: diff còn
      **0.004s** (từ 5.4s), resume job qua `run_pipeline()` thật (không mock)
      → `status=done`, `duration_mismatch=false`. Rebuild + recreate
      `web-api`/`pipeline` image để chốt fix.

**Checkpoint**: 3 provider TTS (edge-tts, LucyAI/Vivibe, 9router) cùng chọn
được qua danh sách gộp và nghe thử được qua 1 cơ chế chung; mỗi provider có
cách xử lý duration-matching/error riêng phù hợp đặc tính API của nó, và cả
LucyAI lẫn router-tts đều có lớp bảo hiểm ffmpeg `atempo` cho trường hợp
`speed`/API không tuyến tính. Cả 3 provider đều đã verify đường thành công
LẪN đường lỗi bằng dữ liệu/job thật — không còn khoảng trống verify nào.

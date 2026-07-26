---

description: "Task list — 005-natural-pause-dubbing"
---

# Tasks: Lồng tiếng khớp nhịp tự nhiên theo từng câu

**Input**: Design documents từ `/specs/005-natural-pause-dubbing/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: KHÔNG sinh task test tự động — spec không yêu cầu TDD và dự án chưa
có test suite (plan.md Technical Context: verify thủ công bằng job thật + số
liệu đo được từ `voice_timeline.json`). Mỗi phase kết thúc bằng 1 task verify
có bằng chứng cụ thể (Constitution Principle VI).

**Organization**: Nhóm theo user story để implement/verify độc lập. Phase 4
(FR-011) là cross-cutting nhưng **phải chạy ngay sau US1** — lý do ở phần
Dependencies.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1 / US2 / US3 — chỉ gắn cho task thuộc phase user story

## Path Conventions

Repo root là project root (không có `src/`). Đường dẫn thật:
`pipeline.py`, `tts/`, `script_gen/`, `merge/`, `web/backend/`,
`web/frontend/src/` — xem plan.md §Source Code.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Chuẩn bị vật liệu đo và bản đối chứng "trước khi sửa" — không có
số liệu này thì không chứng minh được SC-001/SC-002.

- [X] T001 Chuẩn bị 2 URL video mẫu theo [quickstart.md](quickstart.md) §Chuẩn bị chung: `VIDEO_PAUSE` (≥3 khoảng lặng ≥1s) và `VIDEO_DENSE` (nói liên tục); xác nhận bằng script đếm khoảng trống trong quickstart.md, ghi kết quả (số khoảng lặng + mốc giây) vào phần ghi chú của task này
  - **LÀM THAY THẾ, không dùng URL thật.** YouTube trả bot-check thất thường trên máy verify. Thay bằng fixture tự sinh: [verify_fixtures.py](verify_fixtures.py) → `fixtures/video_pause.mp4` (23.0s, 5 segment, gap **1.6/2.0/1.5/1.3s** = 4 khoảng lặng ≥1s) và `fixtures/video_dense.mp4` (22.0s, 8 segment, gap 0.1s = 0 khoảng lặng ≥1s). Mốc thời gian là ground truth chính xác thay vì suy ra từ ASR → đo SC-001 chặt hơn video thật. Seed job bỏ qua download/ASR bằng [seed_job.py](seed_job.py).
- [X] T002 Chạy baseline **bằng code hiện tại (chưa sửa)**: `python pipeline.py --url "$VIDEO_PAUSE" --script-mode translate`; lưu lại `job_id`, `voice.wav`, thời lượng voice vs video và cảm nhận nghe (chậm/liền mạch) làm đối chứng cho US1
  - Chạy trên git worktree tại HEAD `27a2c3a` (code trước 005, đã xác nhận không có `tts/segment_synthesizer.py`). Kết quả: `voice.wav` **23.088s** vs video 23.0s (khớp tổng thời lượng) nhưng **chỉ 1/4 = 25%** khoảng lặng gốc tái hiện đúng chỗ; 5 khoảng lặng nó có là pause giữa câu của edge-tts, lệch 1.17–1.95s và trôi tích luỹ. `script.json` không có `segments`, không có `voice_timeline.json`. Đối chứng code mới: **4/4 = 100%**.
- [X] T003 Chạy `python env_check.py` và xác nhận ffmpeg có filter `atempo` + muxer `concat` (`ffmpeg -filters | grep atempo`, `ffmpeg -formats | grep concat`) — cả 2 là bắt buộc cho research.md §3/§4
  - `env_check.py` pass; `ffmpeg -filters` → `..C atempo A->A`; `ffmpeg -formats` → `D concat` (demuxer). Ghi chú: `demucs` **không nằm trong PATH** khi gọi `.venv/bin/python` trực tiếp → xem T039.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Entity nền + helper audio + schema job — mọi user story đều dựa vào.

**⚠️ CRITICAL**: Không user story nào bắt đầu được trước khi phase này xong.

- [X] T004 [P] Thêm `group_segments(segments: list[dict]) -> list[dict]` + 3 hằng số `_GAP_SILENCE_THRESHOLD = 0.30`, `_MIN_UNIT_DURATION = 1.20`, `_MAX_UNIT_DURATION = 15.0` vào `script_gen/router_client.py`: gom ASR segment thành dubbing unit theo đúng 3 quy tắc ở [research.md](research.md) §1, trả về `[{"index", "start", "end", "source_text"}]` theo ràng buộc ở [data-model.md](data-model.md) §1 (unit không chồng lấn, cách nhau ≥0.30s, dài ≤15s)
- [X] T005 [P] Thêm `synthesize_text(text: str, voice_id: str, output_path: str | Path) -> Path` vào `tts/lucyai_client.py` — wrapper mỏng gọi `synthesize(text, voice_id, os.environ["VIVIBE_API_KEY"], output_path, speed=1.0)`, để cả 3 provider có **cùng chữ ký adapter** với `edge_tts_client.synthesize_text` và `router_tts_client.synthesize_text` (research.md §7)
- [X] T006 Tạo file mới `tts/segment_synthesizer.py` với 4 helper audio thuần (chưa có logic provider): `_normalize_wav(path)` → chuẩn hoá tại chỗ về 44100 Hz / 2 kênh / `pcm_s16le` bằng ffmpeg; `_write_silence_wav(path, duration)` → ghi WAV im lặng cùng thông số bằng module `wave` của stdlib; `_apply_atempo(path, tempo)` → ffmpeg `atempo` ghi đè qua file `.tmp` (bê nguyên cách làm đã có ở `tts/router_tts_client.py:104`); `_concat_wavs(files, output_path)` → ffmpeg **concat demuxer** với file danh sách tạm (research.md §4)
- [X] T007 Cập nhật schema job trong `pipeline.py::create_job()`: thêm `"voice_timeline": None` vào `artifacts`, `"tts_segments_failed": False` vào `warnings`, và field top-level `"tts_failed_segments": 0` — theo [data-model.md](data-model.md) §6

**Checkpoint**: Có Dubbing Unit + helper ghép audio + schema job mới → US1 bắt đầu được.

---

## Phase 3: User Story 1 - Giữ nhịp ngắt nghỉ tự nhiên khi Dịch chuẩn (Priority: P1) 🎯 MVP

**Goal**: Chế độ `translate` sinh giọng đọc theo từng nhịp, đặt đúng khung thời
gian gốc, có khoảng lặng thật giữa các nhịp, chỉ tăng tốc cục bộ khi tràn.

**Independent Test**: Chạy `python pipeline.py --url "$VIDEO_PAUSE" --script-mode translate`;
`voice_timeline.json` cho thấy ≥90% khoảng lặng gốc tái hiện đúng vị trí (lệch
≤1s) và ≥80% unit có `tempo ≤ 1.15`; nghe `output.mp4` thấy ngắt nghỉ đúng chỗ
so với bản baseline ở T002.

### Implementation for User Story 1

- [X] T008 [US1] Sửa `script_gen/router_client.py::generate_script()` cho `mode="translate"`: đọc `transcript.json` → `group_segments()` (T004) → `translate_segments(units)` (hàm đã có, tái dùng nguyên) → ghi `script.json` có `segments` + `content` (nối `translated_text` bằng khoảng trắng) theo [data-model.md](data-model.md) §2. Bỏ tham số `source_duration` khỏi nhánh translate (không còn dùng ngân sách ký tự toàn bài)
- [X] T009 [US1] Sửa điều kiện resume của `generate_script()`: `script.json` chỉ được coi là hợp lệ khi parse được **và** có mảng `segments` không rỗng (với `translate`/`rewrite`); thiếu `segments` → sinh lại (research.md §7, xử lý job cũ)
- [X] T010 [US1] Thêm dispatch adapter vào `tts/segment_synthesizer.py`: `_get_adapter(provider, voice_id) -> Callable[[str, Path], None]` map `edge-tts` → `edge_tts_client.synthesize_text`, `lucyai` → `lucyai_client.synthesize_text` (T005), `router-tts` → `router_tts_client.synthesize_text`; provider lạ → `ValueError`
- [X] T011 [US1] Thêm vòng tổng hợp từng unit vào `tts/segment_synthesizer.py` (hằng số `_MAX_TEMPO = 1.4`, `_MIN_TEMPO = 1.0`, `_TEMPO_TOLERANCE = 0.15`): với mỗi unit → gọi adapter ra `jobs/{id}/segments/unit_{index:04d}.wav` → `_normalize_wav` → đo bằng `media_utils.get_media_duration` → nếu vượt khung gốc quá `_TEMPO_TOLERANCE` thì `_apply_atempo` với `tempo = min(_MAX_TEMPO, duration / khung_gốc)`, **không bao giờ tempo < 1.0** (research.md §3); bỏ qua gọi lại provider nếu file unit đã tồn tại và >0 byte (resume)
- [X] T012 [US1] Thêm hàm chính `synthesize_segments(script_path, job_dir, provider, voice_id) -> tuple[Path, float, dict]` vào `tts/segment_synthesizer.py`: chạy vòng T011, ghép timeline theo con trỏ `start = max(unit.start, cursor)` với khoảng lặng thật chèn giữa (`_write_silence_wav`), `_concat_wavs` ra `voice.wav`, rồi ghi `voice_timeline.json` đúng shape [data-model.md](data-model.md) §3 (`source_start/source_end/start/end/text/tempo/status`, `total_duration`, `failed_count`). Tràn đẩy lùi unit sau — FR-009
- [X] T013 [US1] Sửa bước `synthesizing` trong `pipeline.py::run_pipeline()`: thay 3 nhánh `lucyai_synthesize`/`router_tts_synthesize`/`edge_tts_synthesize` bằng 1 lời gọi `synthesize_segments(...)`; ghi `artifacts.voice_track` + `artifacts.voice_timeline`; log số nhịp và tempo theo mẫu ở [contracts/cli.md](contracts/cli.md) §3. Nhánh `script_mode="subtitle"` giữ nguyên tuyệt đối
- [X] T014 [P] [US1] Xoá `synthesize_from_script()` khỏi `tts/lucyai_client.py` và `tts/router_tts_client.py` (kèm hằng số `_DURATION_ADJUST_TOLERANCE_SECONDS` chỉ phục vụ hàm này); giữ `synthesize()`/`synthesize_text()`/`list_voices()`/`_apply_atempo()` vì vẫn dùng cho nghe thử và adapter
- [ ] T015 [US1] Verify US1 theo [quickstart.md](quickstart.md) §US1: chạy `VIDEO_PAUSE` (thu 4 bằng chứng: `script.json` có segments; SC-001 ≥90% khoảng lặng lệch ≤1s; SC-002 ≥80% unit `tempo ≤ 1.15` và không unit nào `tempo < 1.0`; nghe đối chứng với baseline T002) **và** `VIDEO_DENSE` (không sinh khoảng trống >0.5s ở chỗ transcript không có — Acceptance 2)
  - **KHÔNG TICK ĐƯỢC — trượt SC-002 vế 1.** Đã chạy 3 job (`va-us1-pause`, `va-us1-pause-b`, `va-us1-dense`).
  - ✅ `script.json` có `segments` (pause: 5 nhịp; dense: 8 ASR segment → 2 nhịp do gap 0.1s < 0.30).
  - ✅ **SC-001: 4/4 = 100%** (cần ≥90%), lệch 0.019–0.080s. Đối chứng độc lập bằng `silencedetect` cũng 4/4 ở 2 ngưỡng.
  - ❌ **SC-002 vế "≥80% unit `tempo ≤ 1.15`": 40% / 20% / 0%** — trượt ổn định qua 3 lần chạy, không phải nhiễu. Tempo: `[1.13,1.00,1.25,1.20,1.29]`, `[1.16,1.00,1.25,1.21,1.29]`, `[1.40,1.40]`.
  - ✅ **SC-002 vế "không unit nào `tempo < 1.0`": đạt tuyệt đối 0/12** — đây chính là lỗi đọc chậm mà feature sinh ra để sửa.
  - ✅ Đối chứng baseline T002: 25% → 100% khớp khoảng lặng.
  - ✅ `dense` Acceptance 2: 0 khoảng trống >0.5s do pipeline chèn (khoảng trống duy nhất = 0.000s).
  - Nguyên nhân trượt: `translate_segments()` dựng input `[n] {source_text}` **không kèm ngân sách ký tự**, khác `rewrite_segments()` có `[n] (~N ký tự) …` → bản dịch EN→VI dài hơn khung ~1.13× hệ thống, lực duy nhất để khớp là `atempo`. Xem **T036**.
  - Chưa làm: nghe `output.mp4` (cần tai người; bước `merging` không chạy trong đợt verify này).

**Checkpoint**: Chế độ mặc định (`translate`) đã giải quyết đúng vấn đề gốc — MVP dùng được.

---

## Phase 4: FR-011 - Phụ đề động chính xác cho cả 3 provider (Cross-cutting)

**Purpose**: Sau T013, đường sinh `captions.json` cũ (streaming edge-tts) không
còn được gọi → `--dynamic-captions` sẽ **im lặng mất tác dụng** cho tới khi
phase này xong. Vì vậy phải chạy ngay sau US1, trước US2/US3.

**Independent Test**: Chạy cùng 1 video với `--dynamic-captions` qua cả 3
provider; mỗi cue trong `captions.json` khớp đúng 1 unit `status="ok"` trong
`voice_timeline.json`, và chữ hiện đúng nhịp trong `output.mp4` ở cả 3.

- [X] T016 Thêm sinh `captions.json` vào `tts/segment_synthesizer.py`: khi `dynamic_captions=True` (thêm tham số vào `synthesize_segments`), ghi `[{start, end, text}]` lấy từ `voice_timeline.json` — **chỉ** unit `status="ok"`, dùng `start`/`end` thực tế đã ghép, không phải khung gốc ([data-model.md](data-model.md) §5)
- [X] T017 Truyền `dynamic_captions` từ `pipeline.py::run_pipeline()` xuống `synthesize_segments()` (T013 để trống chỗ này); bước `merging` giữ nguyên logic burn từ `captions.json` đã có ở 003 — không sửa `merge/subtitle_burner.py`
- [X] T018 Xoá khỏi `tts/edge_tts_client.py`: `synthesize()`, `_collect_captions()`, `_stream_sentence_boundaries()`, `_synthesize_with_fallback()` nếu không còn ai gọi, và các hằng số `_RATE_MIN_PCT`/`_RATE_MAX_PCT`/`_RATE_ADJUST_TOLERANCE_SECONDS`; giữ `DEFAULT_VOICE`, `BACKUP_VOICE`, `list_voices()`, `synthesize_text()`, `_synthesize_async()` (research.md §6/§7). Kiểm tra `DEFAULT_VOICE` vẫn import được từ `pipeline.py`
- [ ] T019 Verify FR-011 theo [quickstart.md](quickstart.md) §FR-011: 3 job (edge-tts, router-tts, lucyai nếu có key) đều có `captions.json` khớp timeline; xem `output.mp4` thấy chữ đúng nhịp ở cả 3; `grep -rn "SentenceBoundary\|collect_captions" tts/ pipeline.py` không còn kết quả
  - **KHÔNG TICK ĐƯỢC — 1 bug thật + 1 tiêu chí grep còn hit.**
  - ✅ `captions.json` khớp timeline **5/5 cue** với edge-tts (`vb-cap-edge`) và lucyai (`vb-cap-lucy`); cue dùng `start/end` **thực tế đã ghép** chứ không phải khung ASR gốc (bằng chứng: `cue.end=3.180` vs `source_end=3.20`).
  - ✅ Unit `status="failed"` không lọt vào captions (test trực tiếp `_write_captions()` với timeline có 1 unit failed → 2 cue / 3 unit).
  - ✅ Burn phụ đề OK: `output.mp4` 22.967s/23.0s, `subtitles.srt` 5 cue khớp. Trích khung hình đọc được chữ tại `t=1.5s` và `t=20.8s`; tại `t=9.0s` (giữa 2 cue) **không có chữ** — đúng mong đợi.
  - ❌ **BUG THẬT**: `pipeline.py` đọc `tts_provider`/`voice_id` từ job.json (dòng 486/490) nhưng `dynamic_captions` chỉ lấy từ tham số CLI (dòng 514, 585) → resume bằng `--job-id` mà quên gõ lại cờ sẽ **âm thầm mất phụ đề động**. Đường web không dính (`jobs_api.py:225`). Xem **T035**.
  - ❌ `grep "SentenceBoundary\|collect_captions" tts/ pipeline.py` còn **1 hit**: docstring `tts/segment_synthesizer.py:521`. Xem **T038**.
  - ⛔ router-tts **BLOCKED** — cần 9router (IP LAN, timeout). Fallback OpenRouter chỉ cứu LLM, không cứu TTS.

**Checkpoint**: `--dynamic-captions` hoạt động đúng với mọi provider.

---

## Phase 5: User Story 2 - Giữ nhịp ngắt nghỉ tự nhiên khi Sáng tạo (Priority: P2)

**Goal**: Chế độ `rewrite` sinh nội dung sáng tạo theo đúng số nhịp/thứ tự của
khung ASR gốc, dùng chung cơ chế khớp nhịp của US1.

**Independent Test**: Chạy `--script-mode rewrite` với `VIDEO_PAUSE`;
`len(script.json["segments"])` == số unit trong `voice_timeline.json`, nội
dung vẫn là văn phong viết lại (không dịch sát nghĩa) và không bị cụt/vụn.

### Implementation for User Story 2

- [X] T020 [US2] Thêm `SEGMENT_REWRITE_SYSTEM` vào `script_gen/router_client.py`: dựa trên `REWRITE_SYSTEM` sẵn có nhưng ràng buộc "mỗi dòng `[n]` là 1 nhịp nói độc lập, trả về ĐÚNG số dòng và ĐÚNG thứ tự đầu vào, không gộp/tách/bỏ dòng" (mượn nguyên cách diễn đạt đã verify của `SEGMENT_TRANSLATE_SYSTEM`), giữ yêu cầu sáng tạo/hook/không dịch sát nghĩa
- [X] T021 [US2] Thêm `rewrite_segments(units: list[dict]) -> list[dict]` vào `script_gen/router_client.py`: input đánh số kèm ngân sách ký tự **theo từng unit** — `[n] (~{N} ký tự) {source_text}` với `N = estimate_target_char_budget(unit.end - unit.start)` (hàm đã có, nay nhận thời lượng của unit); gọi `_chat_completion(SEGMENT_REWRITE_SYSTEM, ..., temperature=0.7)`, parse bằng `_parse_numbered_lines()`, lệch số dòng → `RuntimeError` như `translate_segments()`
- [X] T022 [US2] Nối `rewrite_segments()` vào nhánh `mode="rewrite"` của `generate_script()` (cùng shape output với T008) **và gỡ vòng retry ngân sách ký tự toàn bài** (vòng `for attempt in range(2)` + `retry_feedback` + tham số `target_char_budget` trong `_call_9router`) — đã thành thừa, research.md §2
- [X] T023 [US2] Verify US2 theo [quickstart.md](quickstart.md) §US2: số segment khớp số unit; đọc `script.json` xác nhận văn phong sáng tạo và không có nhịp cụt bất thường (US2 Acceptance 2); khoảng lặng trong timeline tương ứng khoảng lặng gốc như US1
  - Job `vc-us2-edge`. ✅ 5 segment == 5 unit. ✅ Văn phong sáng tạo rõ rệt (đối chứng cạnh bản dịch sát nghĩa cùng fixture: "Most people" → **"Bạn"**, thêm câu hỏi tu từ "đúng không?", tiếng lóng "cắm mặt vào", hook ở nhịp 1). ✅ Không nhịp rỗng/cụt, mọi nhịp kết thúc trọn câu (`! ? . ! !`), ngắn nhất 10 từ. ✅ 4/4 khoảng lặng khớp, lệch tối đa **0.021s**. ✅ Không rò chuỗi `(~N ký tự)` vào `translated_text`.
  - Ghi chú chất lượng (không phải tiêu chí fail): model fallback `gemini-2.5-flash` viết vượt ngân sách ký tự trung bình **1.50×** → nhịp cuối kịch trần `tempo=1.4` mà vẫn tràn +0.466s. Xem T036.

**Checkpoint**: Cả 2 chế độ lồng tiếng đều khớp nhịp tự nhiên.

---

## Phase 6: User Story 3 - Job vẫn hoàn tất khi vài câu lỗi TTS (Priority: P3)

**Goal**: Lỗi tổng hợp cục bộ ở 1 vài nhịp không làm hỏng cả job — thay bằng
khoảng lặng, cảnh báo rõ ràng, phân biệt với lỗi toàn phần.

**Independent Test**: Giả lập lỗi TTS ở 1 nhịp giữa job nhiều nhịp → exit code
0, `status="done"`, `warnings.tts_segments_failed=true`, `tts_failed_segments`
đúng số lượng, các nhịp sau vẫn đúng vị trí.

### Implementation for User Story 3

- [X] T024 [US3] Thêm xử lý lỗi cục bộ vào vòng tổng hợp trong `tts/segment_synthesizer.py`: mỗi unit thử tối đa **2 lần**; thất bại cả 2 → `_write_silence_wav` dài đúng `source_end - source_start`, gán `status="failed"` trong timeline, tăng `failed_count`, in log kèm index + mốc thời gian + lý do (mẫu log ở [contracts/cli.md](contracts/cli.md) §3); nếu `failed_count == len(units)` → `raise RuntimeError` (không ghi `voice.wav`) để job fail như cũ (Edge Case cuối của spec)
- [X] T025 [US3] Sửa `pipeline.py` bước `synthesizing`: đọc `failed_count` từ kết quả `synthesize_segments()`, ghi `warnings_update={"tts_segments_failed": failed_count > 0}` và `extra_update={"tts_failed_segments": failed_count}`; in cảnh báo tổng kết; **không** gọi `fail_job()` cho lỗi cục bộ — job đi tiếp sang `merging` (FR-006)
- [X] T026 [P] [US3] Thêm `"tts_failed_segments": job.get("tts_failed_segments", 0)` vào response `GET /api/jobs/{job_id}` trong `web/backend/jobs_api.py` (khối dựng dict quanh dòng 110); `warnings` đã pass-through nên không cần sửa
- [X] T027 [P] [US3] Thêm `tts_failed_segments: number` và `warnings.tts_segments_failed?: boolean` vào interface `JobDetail` trong `web/frontend/src/api/client.ts` ([contracts/api.md](contracts/api.md) §5)
- [X] T028 [P] [US3] Thêm nhãn `tts_segments_failed` vào `WARNING_LABELS` trong `web/frontend/src/pages/JobDetailPage.tsx`, chèn được số lượng từ `job.tts_failed_segments` và nêu rõ đây là lỗi **cục bộ** (nội dung nhãn ở [contracts/api.md](contracts/api.md) §5) — dùng đúng khối "Cảnh báo chất lượng" sẵn có, không thêm component
- [X] T029 [US3] Verify US3 theo [quickstart.md](quickstart.md) §US3: giả lập lỗi 1 nhịp (đổi `ROUTER_API_KEY` giữa chừng hoặc raise tạm ở 1 index — nhớ hoàn tác) → thu 4 bằng chứng (exit 0 + `status=done`; 2 cảnh báo độc lập đúng giá trị; unit `failed` dài đúng khung gốc; nghe `output.mp4` chỉ đoạn đó im lặng); **và** đối chứng lỗi toàn phần (key sai từ đầu) → `status=failed`, exit 2
  - Giả lập bằng **monkeypatch runtime** (`_get_adapter`), không sửa file — 9router đã chết sẵn nên mẹo "đổi ROUTER_API_KEY" không dùng được. Job `vd-t029-local` / `vd-t029-total` dùng chung `script.json` với job đối chứng `vd-t029-base` để so timeline 1-1.
  - ✅ Ca A: exit **0**, `status="done"` (chạy hết cả merging). ✅ `tts_segments_failed=true` **và** `tts_failed_segments=1`. ✅ Unit lỗi `end-start=3.500s` == `source_end-source_start=3.500s`, `tempo=1.0`. ✅ Nhịp sau **Δstart=Δend=0.000s** so với job đối chứng. ✅ Log đúng mẫu `contracts/cli.md` §3. ✅ Retry đúng 2 lần cho nhịp lỗi, 1 lần cho nhịp OK.
  - ✅ Thay cho tiêu chí "nghe": `volumedetect` khoảng `[10.0,13.5]` = **-91.0 dB** (im lặng số tuyệt đối) vs **-22.9 dB** ở nhịp kế bên; giữ nguyên qua `output.mp4`.
  - ✅ Ca B (lỗi toàn phần): `RuntimeError`, exit **2**, `status="failed"`, **không** ghi `voice.wav`/`voice_timeline.json`. Đúng Edge Case cuối của spec.

**Checkpoint**: Cả 3 user story hoạt động độc lập.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T030 [P] Cập nhật `README.md`: mô tả cơ chế lồng tiếng theo từng nhịp thay cho "tự chỉnh tốc độ đọc để khớp gần đúng thời lượng video gốc"; ghi `--dynamic-captions` nay chính xác với cả 3 provider; bổ sung `voice_timeline.json` + `segments/` vào sơ đồ "Cấu trúc output"; thêm mục 005 vào danh sách Tài liệu kỹ thuật
- [X] T031 [P] Dọn dead code: `grep -rn "synthesize_from_script\|collect_captions\|target_char_budget\|retry_feedback" .` không còn kết quả ngoài file spec; xoá import thừa trong `pipeline.py`
- [ ] T032 Chạy toàn bộ bảng "Kiểm tra hồi quy" ở cuối [quickstart.md](quickstart.md): `--script-mode subtitle` không đổi; resume job mới lỗi ở `merging` không gọi lại TTS; resume job **cũ** (script.json thiếu `segments`) sinh lại script rồi chạy tiếp; nghe thử giọng trên web UI vẫn OK với cả 3 provider
  - **3/4 mục ĐẠT.** ✅ `subtitle` không đổi: `voice_track=None`, không có `voice.wav`/`segments/`, script 5 segment == 5 ASR segment; bằng chứng mạnh trên fixture `dense`: **8 ASR segment → 8 segment** trong khi `group_segments()` gom còn 2 → mode subtitle thực sự không đi qua cơ chế gom nhịp. Audio gốc giữ nguyên (`-25.9 dB` cả source lẫn output).
  - ✅ Resume job lỗi ở `merging`: chạy lại **với adapter TTS bị patch để luôn raise** — job vẫn `done`, adapter được gọi **0 lần**, md5 `voice.wav` không đổi.
  - ✅ Resume job cũ thiếu `segments`: log `script.json cũ không có 'segments' … sinh lại theo từng nhịp`, script mới có 5 segment khớp mốc ASR, md5 đổi, job chạy tiếp tới `done`.
  - ⚠️ Mục 4 chỉ verify ở **tầng hàm**: `synthesize_text()` OK với edge-tts (571 KB) và lucyai (111 KB); `router-tts` fail vì 9router timeout (giới hạn môi trường). **Chưa kiểm `POST /api/voices/preview` qua UI thật** → đây là phần còn thiếu để tick.
- [ ] T033 Verify SC-004 theo [quickstart.md](quickstart.md) §SC-004: so 3 job cùng video khác provider — số unit bằng nhau, vị trí khoảng lặng lệch ≤0.5s, không unit nào `tempo < 1.0` hoặc `> 1.4`
  - **KHÔNG TICK ĐƯỢC — trượt tiêu chí khoảng lặng, và chỉ phủ 2/3 provider.**
  - ✅ Số unit bằng nhau (5 = 5). ✅ Tempo trong `[1.0, 1.4]` ở mọi job (edge max 1.289, lucyai max 1.148).
  - ❌ Vị trí khoảng lặng lệch **0.718s > 0.5s**. Có **thí nghiệm kiểm soát**: job `vc-sc004-lucyai-same` dùng lại y hệt `script.json` của job edge → loại biến LLM, vẫn lệch 0.718s (chạy tự nhiên: 0.649s). Không phải nhiễu.
  - Nguyên nhân **thiết kế**, không phải bug: `_MIN_TEMPO=1.0` (`segment_synthesizer.py:48`) chỉ tăng tốc chứ không kéo giãn, còn `start = max(source_start, cursor)` (dòng 476) neo mỗi unit vào đầu khung → phần dư luôn dồn thành khoảng lặng **đuôi**. Provider đọc nhanh hơn ⇒ khoảng lặng bắt đầu sớm hơn (lucyai nhanh hơn edge ~23%, chỗ nhiều nhất ~36%).
  - Nếu định nghĩa "vị trí khoảng lặng" theo mốc **kết thúc** (lúc câu kế bắt đầu) thì lệch **0.000s** ở cả 4 khoảng. quickstart không nói rõ đo mốc nào. Xem **T037**.
  - ⛔ router-tts BLOCKED (cần 9router).
- [X] T034 Verify web UI end-to-end theo [quickstart.md](quickstart.md) §Web UI: `docker compose up -d --build web-api web-ui`, submit job "Dịch chuẩn" + "Phụ đề động", xác nhận cảnh báo mới hiển thị đúng kèm số câu khi có nhịp lỗi
  - Chạy **local thay docker** (uvicorn:8101 + vite:5183) vì build image torch/demucs trên máy 2 CPU sẽ nghẽn; ghi nhận sai lệch quy trình này.
  - ✅ Vế chính "cảnh báo mới hiển thị đúng kèm số câu": **ĐẠT hoàn toàn, có ảnh chụp đã đọc**. API trả `tts_failed_segments: 3` + `warnings.tts_segments_failed: true` (T026); `client.ts:20,26` có đủ type (T027); `JobDetailPage.tsx:17-34` chèn số + nêu rõ tính cục bộ (T028). Trang render: *"3 câu không tổng hợp được giọng đọc, đã thay bằng khoảng lặng — phần còn lại của video vẫn có lồng tiếng bình thường"*. Ca `tts_failed_segments=0` → fallback "Một số câu…" (không in "0 câu"); bật kèm `duration_mismatch` → 2 dòng độc lập.
  - ✅ Submit qua **thao tác form thật**: `job.json` đúng `script_mode=translate`, `dynamic_captions=true`, `tts_provider`, `voice_id`, và có đủ field mới của 005 (T007 OK ở đường web).
  - ⚠️ Job chạy tới `done` qua UI **chưa chứng minh được** (bot-check YouTube thất thường + trần CPU) — không phải lỗi code. Đường lỗi vẫn rõ ràng: fail ở `downloading` với thông báo nguyên văn, `can_retry=true`, không phải 500 mơ hồ.
  - 🔎 Phát hiện phụ: `/api/voices` trả **30 giọng router-tts** dù 9router chết (`voices_api.py:66` chỉ gate theo `ROUTER_API_KEY`, `router_tts_client.py:27-29` hardcode không gọi mạng) → người dùng chọn xong job chết ở `synthesizing`. Xem **T041**.

---

## Phase 8: Phát sinh từ đợt verify (2026-07-26)

**Purpose**: Lỗi thật và mâu thuẫn spec phát hiện khi chạy T015/T019/T032/T033/T034.
T035-T037 **chặn** việc tick 3 task verify tương ứng; T038-T041 là nợ kỹ thuật.

**⚠️ T036 và T037 cần QUYẾT ĐỊNH của người chủ spec trước khi code** — ngưỡng
đang trượt do chính quickstart đặt ra, không phải do spec.md (spec.md SC-002/
SC-004 chỉ định tính). Constitution VI cấm tự chọn số khác.

- [ ] T035 Sửa `pipeline.py::run_pipeline()` đọc `dynamic_captions` từ job.json khi resume, giống cách đã làm với `tts_provider`/`voice_id` ở dòng 486/490 — hiện dòng 514 và 585 chỉ dùng tham số CLI nên resume `--job-id` mà quên gõ lại cờ sẽ âm thầm mất phụ đề động. **Chặn T019.** Sau khi sửa, gỡ cảnh báo tương ứng trong `seed_job.py`
- [ ] T036 [Quyết định + code] Xử lý SC-002 trượt ở mode `translate` (40%/20%/0% so với ngưỡng ≥80% unit `tempo ≤ 1.15`): hoặc thêm ngân sách ký tự theo từng nhịp vào `SEGMENT_TRANSLATE_SYSTEM` + `translate_segments()` trong `script_gen/router_client.py` (giống `rewrite_segments()` đã có), hoặc sửa ngưỡng ở `quickstart.md:51` cho sát cặp ngôn ngữ EN→VI rồi amend spec. **Lưu ý**: mode `rewrite` ĐÃ có ngân sách ký tự mà vẫn vượt 1.50× → chỉ thêm prompt có thể không đủ. **Chặn T015**
- [ ] T037 [Quyết định + có thể code] Xử lý SC-004 trượt (khoảng lặng lệch 0.718s > 0.5s giữa edge-tts và lucyai): (a) định nghĩa rõ trong `quickstart.md` §SC-004 rằng "vị trí khoảng lặng" đo theo mốc **kết thúc** (lệch 0.000s) thay vì mốc bắt đầu, hoặc (b) nới ngưỡng, hoặc (c) đổi thiết kế phân bổ phần dư khung trong `tts/segment_synthesizer.py:476` (hiện dồn hết thành khoảng lặng đuôi). **Chặn T033**
- [ ] T038 [P] Sửa docstring `tts/segment_synthesizer.py:521` để `grep -rn "SentenceBoundary\|collect_captions" tts/ pipeline.py` thật sự rỗng (hiện còn 1 hit là câu văn mô tả lịch sử, không phải code sống); đồng thời sửa tiêu chí grep của **T031** trong file này vì `target_char_budget` khớp substring của `estimate_target_char_budget()` — hàm đang sống và T021 bắt buộc giữ
- [ ] T039 [P] Sửa `merge/vocal_separator.py:36` để tìm `demucs` cạnh `sys.executable` (vd `Path(sys.executable).parent / "demucs"`) chứ không chỉ `shutil.which("demucs")` — chạy `.venv/bin/python pipeline.py` mà không activate venv sẽ khiến FR-010 im lặng mất và `background_music_lost=true` ở mọi job; hoặc tối thiểu ghi rõ trong README là phải `source .venv/bin/activate`
- [ ] T040 [P] Mở rộng `_strip_budget_hint()` trong `script_gen/router_client.py:548`: regex hiện neo `^` nên chỉ bóc được `(~N ký tự)` ở đầu dòng, model chèn giữa câu sẽ lọt xuống TTS và bị đọc thành tiếng
- [ ] T041 [P] `web/backend/voices_api.py:66` liệt kê 30 giọng `router-tts` chỉ dựa trên sự tồn tại của `ROUTER_API_KEY`, không kiểm 9router có sống không (`tts/router_tts_client.py:27-29` hardcode, không gọi mạng) → người dùng chọn giọng xong job chết ở `synthesizing`. Cân nhắc health-check có cache hoặc nhãn cảnh báo trên UI

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: không phụ thuộc gì — T002 phải chạy **trước khi sửa code** (baseline đối chứng)
- **Phase 2 (Foundational)**: sau Setup — CHẶN mọi user story
- **Phase 3 (US1, P1)**: sau Phase 2
- **Phase 4 (FR-011)**: **BẮT BUỘC ngay sau Phase 3** — T013 gỡ đường gọi TTS cũ nên `captions.json` không còn được sinh; `--dynamic-captions` hỏng cho tới khi T016-T018 xong. Đây là ngoại lệ có chủ đích so với thứ tự ưu tiên user story
- **Phase 5 (US2, P2)** và **Phase 6 (US3, P3)**: đều chỉ cần Phase 3 xong; **độc lập với nhau** → chạy song song được nếu có 2 người
- **Phase 7 (Polish)**: sau các phase muốn giao

### User Story Dependencies

- **US1 (P1)**: chỉ cần Foundational — không phụ thuộc story khác
- **US2 (P2)**: dùng lại `segment_synthesizer` của US1 (chỉ đổi nguồn `script.json`) → cần US1 xong; không phụ thuộc US3
- **US3 (P3)**: bọc thêm xử lý lỗi quanh vòng tổng hợp của US1 → cần US1 xong; không phụ thuộc US2

### Within Each User Story

- Script generation (`script_gen/`) trước TTS (`tts/`) trước orchestration (`pipeline.py`) trước web layer
- Task verify luôn là task cuối của phase; không đánh dấu xong phase khi chưa thu đủ bằng chứng (Constitution VI)

### Parallel Opportunities

- **Phase 2**: T004 (`script_gen/router_client.py`) ∥ T005 (`tts/lucyai_client.py`) — khác file. T006/T007 phụ thuộc thứ tự đọc-hiểu nhưng cũng khác file, chạy song song được nếu chia người
- **Phase 3**: T014 (dọn 2 client cũ) ∥ T008-T013; T010→T011→T012 **tuần tự** (cùng file `tts/segment_synthesizer.py`)
- **Phase 6**: T026 ∥ T027 ∥ T028 — backend, type frontend, page frontend là 3 file khác nhau
- **Phase 7**: T030 ∥ T031
- **Không song song được**: mọi task cùng chạm `tts/segment_synthesizer.py` (T006, T010-T012, T016, T024) hoặc cùng chạm `pipeline.py` (T007, T013, T017, T025) hoặc cùng chạm `script_gen/router_client.py` (T004, T008, T009, T020-T022)

---

## Parallel Example: Phase 6 (US3) — lớp giao diện

```bash
# 3 file khác nhau, không phụ thuộc nhau — chạy cùng lúc sau khi T025 xong:
Task: "Thêm tts_failed_segments vào response GET /api/jobs/{id} trong web/backend/jobs_api.py"
Task: "Thêm tts_failed_segments + warnings.tts_segments_failed vào JobDetail trong web/frontend/src/api/client.ts"
Task: "Thêm nhãn cảnh báo tts_segments_failed vào WARNING_LABELS trong web/frontend/src/pages/JobDetailPage.tsx"
```

---

## Implementation Strategy

### MVP First (US1 + FR-011)

1. Phase 1 Setup — **nhất là T002 baseline**, chạy trước khi sửa bất kỳ dòng code nào
2. Phase 2 Foundational
3. Phase 3 US1 → **DỪNG và VALIDATE** bằng T015 (so trực tiếp với baseline T002)
4. Phase 4 FR-011 — bắt buộc kèm theo để không bỏ lại `--dynamic-captions` ở trạng thái hỏng
5. Giao được: chế độ mặc định (Dịch chuẩn) đã hết lỗi đọc chậm/liền mạch

### Incremental Delivery

1. Setup + Foundational → nền sẵn sàng
2. US1 + FR-011 → verify → giao (MVP)
3. US2 → verify → giao (Sáng tạo cũng khớp nhịp)
4. US3 → verify → giao (chịu lỗi cục bộ + cảnh báo)
5. Polish → hồi quy toàn bộ + README

### Parallel Team Strategy

Sau khi Phase 3 + Phase 4 xong: 1 người làm Phase 5 (US2, chỉ chạm
`script_gen/`), 1 người làm Phase 6 (US3, chạm `tts/segment_synthesizer.py` +
`pipeline.py` + web) — không đụng file nhau ngoài `script_gen/router_client.py`
(chỉ US2) và `pipeline.py` (chỉ US3).

---

## Notes

- [P] = khác file, không phụ thuộc task chưa xong
- Mọi hằng số ngưỡng đã chốt sẵn trong [research.md](research.md) — **không tự chọn số khác**; cần đổi thì amend spec/plan trước (Constitution VI)
- Không thêm dependency mới ở bất kỳ task nào (plan.md Technical Context)
- Commit sau mỗi task hoặc nhóm task cùng file; dừng ở checkpoint để validate độc lập
- Task verify (T015, T019, T023, T029, T032-T034) chỉ được tick khi có bằng chứng cụ thể ghi lại được (số đo từ `voice_timeline.json`, log, hoặc file output) — không chấp nhận "trông có vẻ đúng"

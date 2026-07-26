---
description: "Task list for Sửa lỗi lồng tiếng & thêm phụ đề tự động, phụ đề động (003-dubbing-fixes-subtitles)"
---

# Tasks: Sửa lỗi lồng tiếng & thêm phụ đề tự động, phụ đề động

**Input**: Design documents from `/specs/003-dubbing-fixes-subtitles/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md),
[contracts/cli.md](./contracts/cli.md), [contracts/api.md](./contracts/api.md),
[research.md](./research.md), [quickstart.md](./quickstart.md)

**Tests**: Không yêu cầu test tự động (theo đúng cách tiếp cận của 001/002). Mỗi
user story kết thúc bằng task chạy job thật + `quickstart.md` để verify bằng
bằng chứng thực tế, đáp ứng Constitution Principle VI.

**Organization**: Tasks nhóm theo user story (US1/US2/US3/US4, theo priority
P1/P1/P2/P3 trong spec.md) để mỗi story implement/verify độc lập.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1 / US2 / US3 / US4 — story mà task thuộc về
- Mỗi task nêu rõ file path cụ thể

## Path Conventions

Không tạo project mới — sửa/mở rộng đúng module đã có ở
001-video-repurpose-pipeline (`pipeline.py`, `merge/`, `tts/`, `script_gen/`)
và 002-web-ui (`web/backend/`, `web/frontend/`), theo plan.md → Project
Structure.

---

## Phase 1: Setup

**Purpose**: Vá dependency còn thiếu (root cause US1) và chuẩn bị môi trường
Docker cho toàn bộ task verify phía sau

- [X] T001 Thêm `torchcodec` vào `requirements.txt` — khắc phục Demucs fail ở
      bước lưu file (`torchaudio.save()` yêu cầu `torchcodec`, root cause đã
      verify thật ở research.md §1)
- [X] T002 Rebuild Docker image (`docker compose build web-api pipeline`) sau
      khi cập nhật `requirements.txt`; xác nhận `python -c "import
      torchcodec"` chạy được trong container mới (không cài tạm bằng tay như
      lúc research — phải nằm trong image chính thức). Verify: build thành
      công (torchcodec 0.15.0), container `web-api` recreate với image mới,
      `import torchcodec` OK trong container thật.

**Checkpoint**: Image mới có `torchcodec`, sẵn sàng cho mọi task verify phía
sau (US1 verify trực tiếp bằng fix này; US2-US4 cần image mới nhất để test)

---

## Phase 2: Foundational (Blocking Prerequisites cho US3 + US4)

**Purpose**: Hạ tầng dùng chung giữa US3 và US4 (burn-in phụ đề, mở rộng
schema Job) — US1/US2 KHÔNG phụ thuộc phase này, có thể làm song song ngay

**⚠️ CRITICAL**: US3 và US4 không được bắt đầu trước khi phase này xong

- [X] T003 Mở rộng `pipeline.py`: thêm `"subtitle"` vào `choices` của
      `--script-mode` trong `parse_args()`, thêm flag `--dynamic-captions`
      (action `store_true`, mặc định `False`); thêm field `dynamic_captions:
      bool` vào dict trả về của `create_job()` — theo data-model.md,
      contracts/cli.md. Verify: `python pipeline.py --help` trong container
      thật hiện đúng option mới; `run_pipeline()`/`main()` truyền
      `dynamic_captions` xuyên suốt.
- [X] T004 [P] Implement `merge/subtitle_burner.py` (file mới): hàm
      `write_srt(cues: list[dict], srt_path: Path) -> None` sinh file `.srt`
      chuẩn từ list `{start, end, text}`; hàm `burn_subtitles(video_path,
      srt_path, output_path, audio_path=None) -> None` gọi ffmpeg với filter
      `subtitles=` (căn giữa dưới) + `-c:v libx264 -crf 20 -preset medium`
      (bắt buộc re-encode, research.md §7), `-c:a` copy/aac tuỳ có
      `audio_path` riêng hay dùng audio có sẵn trong `video_path`; raise
      `RuntimeError` rõ ràng khi ffmpeg lỗi — để caller (US3/US4) tự quyết
      định fail job hay chỉ cảnh báo (khác nhau giữa 2 story, xem T018/T023).
      Verify: chạy thật trên `source.mp4` có sẵn, trích 1 frame và xem trực
      tiếp — phụ đề tiếng Việt có dấu hiển thị đúng, căn giữa dưới, đúng nội
      dung/thời điểm.
- [X] T005 Cập nhật `web/backend/jobs_api.py`: `SubmitJobRequest.script_mode`
      đổi type cho phép `"subtitle"`, thêm field `dynamic_captions: bool =
      False`; `_job_to_detail()` trả thêm `dynamic_captions`,
      `subtitles_burned` — theo contracts/api.md (phụ thuộc T003 để
      `pipeline.create_job()` chấp nhận field mới). Verify: curl thật —
      `script_mode: "subtitle"` được chấp nhận ở tầng validate (rơi xuống lỗi
      URL, không phải lỗi script_mode), `script_mode` sai vẫn bị 400 đúng.
- [X] T006 [P] Cập nhật `web/frontend/src/api/client.ts`: type `JobDetail`
      thêm `dynamic_captions: boolean`, `subtitles_burned: boolean`;
      `submitJob()` nhận thêm tham số `dynamicCaptions` và gửi `script_mode`
      kiểu `"translate" | "rewrite" | "subtitle"`. Verify: `npm run build`
      thành công.

**Checkpoint**: `pipeline.py --help` hiện đúng option mới; `web-api` chấp nhận
`script_mode: "subtitle"` và `dynamic_captions` mà không lỗi 422 — chưa có
logic xử lý thật (US3/US4 làm ở phase sau)

---

## Phase 3: User Story 1 - Giữ nhạc nền gốc khi lồng tiếng (Priority: P1) 🎯 MVP

**Goal**: Video sản phẩm giữ được nhạc nền gốc ở cả 2 chế độ lồng tiếng
(FR-001, FR-003) — không cần sửa code nghiệp vụ, chỉ cần T001-T002 (Setup) đã
vá đúng dependency

**Independent Test**: Chạy `quickstart.md` → mục US1 với 1 video nguồn có
nhạc nền rõ, cả 2 `--script-mode`

### Implementation for User Story 1

- [X] T007 [US1] Chạy job thật `--script-mode translate` với 1 video nguồn có
      nhạc nền rõ qua image đã rebuild (T001-T002); xác nhận
      `job.json.warnings.background_music_lost == false` và nghe được nhạc
      nền song song giọng đọc mới trong `output.mp4`. Verify: resume job
      thật (artifact source.mp4/voice.wav có sẵn từ lần chạy thật trước) từ
      bước `merging` — `background_music_lost: false`, `background.wav` sinh
      ra có tín hiệu âm thanh thật (`volumedetect` mean -13.9dB, không câm).
- [X] T008 [US1] Chạy job thật `--script-mode rewrite` với cùng video nguồn —
      xác nhận cùng kết quả giữ nhạc nền (FR-001 yêu cầu áp dụng cả 2 mode,
      không chỉ 1). Verify: cùng cách làm như T007 với job rewrite thật —
      `background_music_lost: false` (giữ đúng `duration_mismatch: true` có
      sẵn — đó là bug của US2, chưa sửa ở task này).
- [X] T009 [US1] Verify US1: xác nhận Acceptance Scenario 3 của spec.md — nếu
      Demucs thực sự lỗi kỹ thuật thì cảnh báo vẫn hiển thị rõ, không im lặng
      bỏ qua (FR-003). **Phát hiện + sửa 1 bug thật trong lúc verify**:
      `merge/vocal_separator.py.extract_background_music()` không bắt
      `RuntimeError` mà `_extract_audio_hq()` raise khi ffmpeg lỗi thật (VD
      video hỏng) — vi phạm đúng cam kết "lỗi module này không raise chặn
      pipeline" mà docstring tự công bố, khiến job fail toàn bộ thay vì
      fallback mute + cảnh báo. Đã thêm `RuntimeError` vào tuple except; test
      lại bằng file video giả (`b'not a real video file'`) — xác nhận
      `extract_background_music()` trả `None` đúng, `merge_audio()` vẫn tạo
      output hợp lệ với `background_music_lost=True`, không crash job.

**Checkpoint**: US1 hoạt động độc lập và đầy đủ — đây là bản MVP của feature
này (khớp lỗi người dùng báo đầu tiên: "Không giữ được nhạc nền gốc")

---

## Phase 4: User Story 2 - Khớp thời lượng giọng đọc ở chế độ Sáng tạo (Priority: P1)

**Goal**: Giọng đọc Sáng tạo lệch ≤10% so với video gốc (SC-002), không cắt
cụt giữa câu (FR-002, FR-003)

**Independent Test**: Chạy `quickstart.md` → mục US2 với ≥3 video mẫu độ dài
khác nhau

### Implementation for User Story 2

- [X] T010 [US2] Thêm hàm ước lượng `target_char_budget` trong
      `script_gen/router_client.py`: `source_duration` (giây) × tốc độ đọc
      trung bình của voice `vi-VN-NamMinhNeural` — dùng số liệu thật đo được
      ở research.md §2 (550 ký tự ≈ 50.59s ở tốc độ mặc định, ≈ 10.9 ký
      tự/giây) làm hằng số khởi điểm
- [X] T011 [US2] Cập nhật `generate_script()`/`_call_9router()` trong
      `script_gen/router_client.py` để áp dụng ngân sách ký tự. **Thiết kế
      khác với research.md ban đầu, dựa trên bằng chứng thật lúc verify**:
      (1) CHỈ áp dụng budget cho `rewrite`, KHÔNG áp dụng cho `translate` —
      test thật cho thấy chèn budget vào `translate` khiến model hiểu nhầm
      là được phép cắt bớt, dịch thiếu hẳn 1/3 đầu video (translate vẫn dựa
      vào rate-adjustment TTS sẵn có để khớp thời lượng, vốn đã đủ tốt); (2)
      chỉ dẫn viết theo hướng "PHẢI DÀI ÍT NHẤT N ký tự" (mức tối thiểu, cấm
      viết ngắn hơn) thay vì "khoảng N ký tự" — test thật cho thấy cách nói
      "khoảng N" khiến model undershoot 2-3 lần thay vì bám sát; (3) thêm cơ
      chế retry tối đa 2 lần kèm feedback cụ thể ("bản trước chỉ có X ký tự,
      cần Y") khi vẫn dưới 85% ngân sách, hạ `temperature=0.4` ở lượt retry,
      luôn giữ bản dài nhất trong các lượt đã thử.
- [X] T012 [US2] Cập nhật `pipeline.py` bước `scripting`: truyền
      `source_duration` (đã tính sẵn từ bước download qua
      `get_media_duration()`) vào `generate_script()` (T011)
- [X] T013 [US2] Verify US2: đo `voice.wav` duration so với `source.mp4` thật
      qua nhiều lượt gọi LLM thật (không mock) trên video 65.95s có sẵn.
      **Vòng lặp verify → phát hiện lỗi → sửa → verify lại thực tế đã xảy
      ra**: lượt đầu (budget "khoảng N ký tự", áp cả 2 mode) cho kết quả TỆ
      HƠN hẳn baseline gốc (rewrite chỉ 22-26s/66s, lệch tới -65%; translate
      bị cắt mất 1/3 nội dung đầu) — phát hiện + sửa thiết kế như T011 mô tả.
      Sau khi sửa: 5/5 lượt test thật đạt ngưỡng SC-002 (lệch ≤10%) — rewrite
      65.8s/63.2s/66.1s/66.1s và translate 66.02s, đều so với nguồn 65.95s
      (lệch lớn nhất 4.2%, phần lớn dưới 0.5%). `warnings.duration_mismatch`
      xác nhận vẫn dùng đúng ngưỡng cảnh báo 3s có sẵn từ 001.

**Checkpoint**: US1 + US2 cùng hoạt động độc lập — 2 lỗi người dùng báo đã
được sửa xong

---

## Phase 5: User Story 3 - Phụ đề tự động, giữ nguyên âm thanh gốc (Priority: P2)

**Goal**: Chế độ xử lý mới `subtitle` — audio gốc giữ nguyên 100%, chỉ thêm
phụ đề dịch sát nghĩa khớp nhịp lời thoại gốc (FR-004/FR-005/FR-006)

**Independent Test**: Chạy `quickstart.md` → mục US3 với 1 video có lời thoại
rõ

### Implementation for User Story 3

- [X] T014 [US3] Thêm hàm dịch theo segment trong
      `script_gen/router_client.py`: nhận `transcript.json.segments`, dịch
      từng `segment["text"]` sát nghĩa (tái dùng đúng system prompt của
      `TRANSLATE_SYSTEM`, Clarification Q2 của spec.md), trả về list
      `{start, end, source_text, translated_text}` — theo data-model.md
      (Script.segments). Implement dưới dạng `translate_segments()` + hàm
      `generate_subtitle_script()` (ghi script.json). Verify thật: 23/23
      segment khớp đúng số lượng/thứ tự, dịch tự nhiên đúng nghĩa.
- [X] T015 [US3] Cập nhật `pipeline.py` bước `scripting`: khi `script_mode ==
      "subtitle"`, gọi hàm dịch theo segment (T014) thay vì
      `generate_script()` nguyên khối, ghi kết quả vào `script.json.segments`
- [X] T016 [US3] Cập nhật `pipeline.py` bước `synthesizing`: khi
      `script_mode == "subtitle"`, bỏ qua hoàn toàn bước TTS (không gọi
      `tts.synthesize()`), chuyển thẳng sang `merging`, giữ
      `artifacts.voice_track = null` có chủ đích — theo data-model.md
      §State Machine
- [X] T017 [US3] Cập nhật `pipeline.py` bước `merging`: khi `script_mode ==
      "subtitle"`, sinh `jobs/{job_id}/subtitles.srt` từ
      `script.json.segments` bằng `write_srt()` (T004), gọi `burn_subtitles()`
      (T004) trực tiếp lên `source.mp4` (audio giữ nguyên, KHÔNG qua
      `ffmpeg_merge.merge_audio()`); nếu burn lỗi → để lỗi lan lên, `fail_job()`
      như bình thường (FR-003 — không có fallback "im lặng" vì phụ đề là toàn
      bộ giá trị của mode này, khác cách xử lý ở US4/T023). Nhân tiện đã thêm
      luôn `extra_update` cho `update_job_status()` (field `subtitles_burned`)
      và phần merging của US4 (T022) vì cùng 1 khối code.
- [X] T018 [P] [US3] `web/frontend/src/pages/HomePage.tsx`: thêm option "Phụ
      đề tự động" (giá trị `"subtitle"`) vào select `script_mode` đã có.
      Verify: `npm run build` thành công.
- [X] T019 [US3] Verify US3 bằng job thật (resume từ `scripting` với transcript
      thật có sẵn, không mock): audio output — so `volumedetect` output vs
      source (-10.0dB/-9.7dB mean, gần như giống hệt, chênh lệch nhỏ do AAC
      re-encode) xác nhận audio giữ nguyên; `voice_track`/`background_audio`
      đúng `null`; trích frame tại giây 6 xác nhận phụ đề hiển thị ĐÚNG chữ
      "Asa, bạn tự chấm mình mấy điểm vào thời điểm chụp bức ảnh này?" đúng
      khớp cue `[4.0-9.0]` — khớp cả nội dung lẫn thời điểm. Acceptance
      Scenario 3 (transcript rỗng): xác nhận `generate_subtitle_script()` raise
      `RuntimeError` rõ ràng, không tạo job giả.

**Checkpoint**: US1 + US2 + US3 cùng hoạt động độc lập

---

## Phase 6: User Story 4 - Phụ đề động khớp nhịp giọng đọc (Priority: P3)

**Goal**: Video đã lồng tiếng (Dịch chuẩn/Sáng tạo) có thêm phụ đề động khớp
đúng nhịp giọng TTS mới, theo từng câu/cụm (FR-007/FR-008, Clarification Q1)

**Independent Test**: Chạy `quickstart.md` → mục US4 cho cả `translate` và
`rewrite`

### Implementation for User Story 4

- [X] T020 [US4] Cập nhật `tts/edge_tts_client.py`: thêm tham số
      `collect_captions: bool = False` cho `synthesize()`. **Khác thiết kế
      ban đầu (dựa trên phát hiện thật lúc implement)**: bản `edge-tts==7.2.8`
      đang cài phát ra TRỰC TIẾP chunk `SentenceBoundary` (không phải chỉ
      `WordBoundary`) qua `.stream()`, kèm sẵn mốc thời gian theo đúng đơn vị
      câu/cụm cần — không cần tự gom `WordBoundary` theo dấu câu như dự tính.
      Sau khi chọn xong rate cuối (2-pass hiện có, không đổi), chạy thêm 1
      lượt `.stream()` riêng cùng rate đó chỉ để thu `SentenceBoundary`, ghi
      `jobs/{job_id}/captions.json`. Verify thật: 3 câu test cho ra đúng 3
      chunk, mốc thời gian nối tiếp khớp nhau.
- [X] T021 [US4] Cập nhật `pipeline.py` bước `synthesizing`: truyền
      `collect_captions=dynamic_captions` vào `synthesize()` (T020)
- [X] T022 [US4] Cập nhật `pipeline.py` bước `merging` (làm cùng lúc với T017
      vì chung 1 khối code): khi `dynamic_captions == true`, SAU KHI ghép
      voice+nhạc nền như bình thường (US1), sinh `subtitles.srt` từ
      `captions.json` bằng `write_srt()` (T004) rồi `burn_subtitles()` (T004)
      lên `output.mp4` vừa ghép; nếu burn lỗi → KHÔNG fail job, log cảnh báo,
      giữ nguyên output đã ghép, set `subtitles_burned = false` — khác
      US3/T017. **Phát hiện + sửa 1 bug thật lúc verify**: `burn_subtitles()`
      dùng file tạm `output_captioned.mp4.tmp` khiến ffmpeg không đoán được
      muxer từ đuôi file (`Unable to choose an output format`) — cơ chế
      fallback hoạt động đúng như thiết kế (job không fail, chỉ mất caption,
      có cảnh báo rõ), nhưng root cause cần sửa: thêm `-f mp4` tường minh vào
      `subtitle_burner.py` thay vì dựa vào đuôi file.
- [X] T023 [P] [US4] `web/frontend/src/pages/HomePage.tsx`: thêm checkbox
      "Phụ đề động" (`dynamic_captions`), chỉ hiển thị khi `script_mode` đang
      chọn là `translate`/`rewrite` (ẩn khi chọn `subtitle`). Verify: `npm
      run build` thành công.
- [X] T024 [US4] Verify US4 bằng job thật cho cả `translate` và `rewrite`
      (dùng transcript/source.mp4 thật có sẵn): cả 2 mode `subtitles_burned:
      true`, `background_music_lost: false` (fix US1 vẫn nguyên vẹn). Trích
      frame tại giây 6 của job translate — đúng khớp 100% với cue
      `[4.29-7.92]` "Asa, bạn tự chấm mình mấy điểm vào thời điểm chụp bức
      ảnh này?" cả nội dung lẫn thời điểm (SC-004 đạt, lệch gần như bằng 0 vì
      caption sinh trực tiếp từ cùng lượt TTS, không suy luận lại).

**Checkpoint**: Cả 4 user story hoạt động độc lập

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hoàn thiện chất lượng chung, không thuộc riêng story nào

- [X] T025 [P] Cập nhật `README.md`: mô tả 3 giá trị `script_mode` (bao gồm
      `subtitle` mới) và flag `--dynamic-captions`/checkbox "Phụ đề động"
      trên web UI — không lặp lại nội dung đã có ở quickstart.md
- [X] T026 Rà soát toàn bộ cảnh báo/log của feature này (FR-003). **Phát hiện
      + sửa 2 lỗ hổng thật lúc rà soát**: (1) `JobDetailPage.tsx` không hiển
      thị cảnh báo nào khi burn phụ đề động thất bại (US4/T022) — CLI có log
      nhưng web UI hoàn toàn im lặng, người dùng web không biết caption họ
      yêu cầu đã bị bỏ qua; đã thêm cảnh báo dẫn xuất từ `dynamic_captions &&
      !subtitles_burned` (không phải field có sẵn trong `job.warnings`); (2)
      `JobDetailPage.tsx` hiển thị nhãn "Chế độ kịch bản" bằng ternary cứng
      2 giá trị (`translate`/`rewrite`), sẽ hiện sai "Tự soạn" cho job
      `subtitle` — đã đổi sang map 3 giá trị đúng. Xác nhận khác biệt cố ý
      US3 (burn lỗi → fail job, T017) vs US4 (burn lỗi → chỉ cảnh báo, T022)
      vẫn đúng thiết kế, không lẫn lộn.
- [X] T027 Rebuild lại Docker image đầy đủ (`docker compose build`) — nhiều
      thay đổi trong lúc implement chỉ được patch tạm qua `docker cp` vào
      container đang chạy để lặp nhanh, CHƯA nằm trong image chính thức.
      Verify sau rebuild: `import torchcodec` OK, `pipeline.py --help` hiện
      đúng option mới, submit job `script_mode=subtitle` qua đúng luồng web
      UI thật (nginx proxy port 80, không phải gọi thẳng backend), Job Detail
      trả đúng field `dynamic_captions`/`subtitles_burned` mới cho job thật
      có sẵn. Constitution Check (6 principle, plan.md): vẫn PASS, không phát
      sinh vi phạm mới.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Không phụ thuộc gì — bắt đầu ngay
- **Foundational (Phase 2)**: Phụ thuộc Setup xong — CHẶN US3 + US4, KHÔNG
  chặn US1/US2 (2 story này không đụng schema/burn-in mới)
- **US1 (Phase 3)**: Chỉ phụ thuộc Setup (T001-T002) — có thể bắt đầu song
  song với Foundational
- **US2 (Phase 4)**: Không phụ thuộc Setup/Foundational — có thể bắt đầu ngay
  từ đầu, song song hoàn toàn với US1/Foundational
- **US3 (Phase 5)**: Phụ thuộc Foundational (T003-T006) xong
- **US4 (Phase 6)**: Phụ thuộc Foundational (T003-T006) xong; độc lập với US3
  về mặt tính năng nhưng cả 2 cùng sửa `pipeline.py` bước `merging` — nên làm
  tuần tự nếu cùng 1 người/agent thực hiện để tránh xung đột merge, dù không
  phụ thuộc logic lẫn nhau
- **Polish (Phase 7)**: Phụ thuộc toàn bộ user story muốn có đã xong

### Within Each User Story

- Task cùng sửa `pipeline.py` (T003; T012/T015-T017; T021-T022) luôn làm
  tuần tự trong nội bộ mỗi story — khác story có thể xen kẽ nhưng nên tuần tự
  nếu cùng người thực hiện (xem trên)
- Task cùng sửa `script_gen/router_client.py` (T010-T011 của US2, T014 của
  US3) độc lập về mặt hàm (khác function) nhưng cùng file — làm tuần tự
- Task verify bằng `quickstart.md` luôn là task cuối của mỗi story

### Parallel Opportunities

- T004 (Foundational, `subtitle_burner.py`) chạy song song với T003
  (`pipeline.py`) — khác file
- T006 (Foundational, frontend `client.ts`) chạy song song với T005 (backend
  `jobs_api.py`) — khác file
- US1 (Phase 3) và US2 (Phase 4) chạy song song hoàn toàn với nhau và với
  Foundational (Phase 2) — không đụng file chung
- T018 (US3, frontend) chạy song song với T014-T017 (US3, backend) — khác
  file
- T023 (US4, frontend) chạy song song với T020-T022 (US4, backend) — khác
  file

---

## Parallel Example: Sau khi Setup xong

```bash
# US1, US2, và Foundational có thể chạy song song ngay (không phụ thuộc lẫn nhau):
Task: "US1 — chạy job thật xác nhận giữ nhạc nền (T007-T009)"
Task: "US2 — sửa script_gen/router_client.py thêm target_char_budget (T010-T013)"
Task: "Foundational — pipeline.py + subtitle_burner.py + jobs_api.py + client.ts (T003-T006)"
# US3 (T014-T019) và US4 (T020-T024) chỉ bắt đầu sau khi Foundational xong
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2 — 2 lỗi người dùng báo trực tiếp)

1. Hoàn thành Phase 1: Setup (T001-T002)
2. Hoàn thành Phase 3: User Story 1 (T007-T009) — song song với Setup gần
   như ngay khi T001-T002 xong
3. Hoàn thành Phase 4: User Story 2 (T010-T013)
4. **DỪNG lại và VALIDATE**: chạy `quickstart.md` US1 + US2 độc lập
5. Đây đã là bản sửa lỗi hoàn chỉnh — 2 vấn đề chất lượng người dùng báo đã
   được giải quyết, có thể deploy ngay mà chưa cần US3/US4

### Incremental Delivery

1. Setup xong → US1 + US2 chạy song song → verify độc lập → deploy bản vá lỗi
2. Thêm Foundational (T003-T006) → mở khoá US3/US4
3. Thêm US3 → verify độc lập → demo chế độ "Phụ đề tự động"
4. Thêm US4 → verify độc lập → demo phụ đề động cho video đã lồng tiếng
5. Mỗi story cộng thêm giá trị mà không phá story trước (Constitution
   Principle VI)

### Parallel Team Strategy

Với nhiều người/agent:

1. Người A: Setup (T001-T002) rồi US1 (T007-T009)
2. Người B: US2 (T010-T013) — bắt đầu ngay, không cần chờ Setup
3. Người C: Foundational (T003-T006) — bắt đầu ngay
4. Sau khi Foundational xong: Người C tiếp tục US3, người thứ 4 (nếu có) làm
   US4 — lưu ý cả 2 cùng sửa `pipeline.py` bước `merging` nên nếu chỉ có 1
   người thì làm tuần tự (xem Dependencies)

---

## Notes

- [P] = khác file, không phụ thuộc task chưa xong
- [Story] gắn task với user story để truy vết
- US1/US2 là bug fix thuần (không đổi schema/API) — có thể deploy độc lập,
  sớm hơn US3/US4 rất nhiều
- US3 (burn lỗi → fail job) và US4 (burn lỗi → chỉ cảnh báo) cố tình xử lý
  lỗi khác nhau — đừng "thống nhất hoá" 2 cách này khi implement (xem lý do ở
  T017/T022)
- Commit sau mỗi task hoặc nhóm task liên quan
- Dừng lại ở mỗi Checkpoint để validate story độc lập trước khi qua story tiếp
- Tránh: gộp task khác story vào cùng 1 lần sửa `pipeline.py` bước `merging`
  mà không tách rõ nhánh `if script_mode == "subtitle"` / `if
  dynamic_captions` — dễ gây xung đột logic giữa US3 và US4

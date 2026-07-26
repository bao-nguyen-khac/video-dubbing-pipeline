# Implementation Plan: Sửa lỗi lồng tiếng & thêm phụ đề tự động, phụ đề động

**Branch**: `003-dubbing-fixes-subtitles` | **Date**: 2026-07-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-dubbing-fixes-subtitles/spec.md`

## Summary

Sửa 2 lỗi chất lượng đã reproduce thật trên môi trường đang chạy (mất nhạc
nền do thiếu dependency `torchcodec` khiến Demucs luôn fail ở bước lưu file —
US1; kịch bản Sáng tạo lệch thời lượng do LLM không có ngân sách ký tự mục
tiêu — US2), đồng thời thêm 2 khả năng mới: chế độ "Phụ đề tự động" giữ
nguyên âm thanh gốc (US3) và phụ đề động khớp nhịp giọng đọc cho 2 chế độ
lồng tiếng hiện có (US4). Toàn bộ dựa trên hạ tầng đã có ở
001-video-repurpose-pipeline (state machine, ASR segment timestamp, edge-tts
word-boundary event) và 002-web-ui (form submit job) — không viết lại kiến
trúc, chỉ vá dependency + mở rộng field/rẽ nhánh hành vi theo `script_mode`.

## Technical Context

**Language/Version**: Python 3.11 (pipeline/backend, không đổi so với 001/002); TypeScript/ReactJS (frontend, chỉ thêm 1 option + 1 checkbox vào form đã có)

**Primary Dependencies**: Toàn bộ dependency đã có ở 001 (f2, yt-dlp, faster-whisper, openai SDK, edge-tts, ffmpeg-python, `demucs==4.0.1`) + **mới**: `torchcodec` (US1, research.md §1). `edge-tts` dùng thêm API `WordBoundary` đã có sẵn trong SDK đang dùng (US4, research.md §4) — không thêm package mới cho US4. Burn-in phụ đề dùng filter `subtitles`/`libass` đã verify có sẵn trong ffmpeg build hiện tại (research.md §7) — không thêm dependency.

**Storage**: Files trong `jobs/{job_id}/` như 001, thêm 2 file trung gian mới: `subtitles.srt` (US3/US4), `captions.json` (US4, lưu `word_boundaries` để resume không cần chạy lại TTS).

**Testing**: Verify thủ công qua chạy job thật (CLI + Docker) như 001/002 — dự án chưa có test suite tự động (Constitution Principle V, chưa có nhu cầu cụ thể được xác nhận).

**Target Platform**: Linux container (Docker), không đổi so với 001/002.

**Project Type**: Web application (CLI pipeline + FastAPI backend + React frontend) — kế thừa cấu trúc `web/` đã có ở 002, không thêm project mới.

**Performance Goals**: Job có burn-in phụ đề (US3, hoặc US4 khi bật) MUST re-encode video (`libx264 -crf 20 -preset medium`) thay vì `-c:v copy` như 001 (research.md §7) — chấp nhận thêm thời gian xử lý, nhất quán với SC-002 của 001 (đã nới thời gian đổi lấy chất lượng). Job không bật phụ đề giữ nguyên performance/behavior của 001.

**Constraints**: Máy chạy Docker giới hạn ~2.8GB RAM (đã xác nhận qua `docker system info` lúc research) — Demucs (US1 fix) đã verify chạy ổn định trong giới hạn này (~43s/job).

**Scale/Scope**: Không đổi so với 001/002 — vẫn 1 job xử lý tại 1 thời điểm (FR-009 của 002), video ngắn dạng TikTok/Douyin/YouTube Shorts.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Đánh giá |
|---|---|
| I. Python-Only Stack | ✅ PASS — mọi thay đổi backend/pipeline (US1-US4) đều Python; frontend chỉ thêm UI thuần React cho option/checkbox đã có cơ chế (002), không đổi ngôn ngữ. |
| II. Source-First, Fallback-Ready Downloading | ✅ PASS — không đổi, feature này không chạm bước download. |
| III. On-Demand AI Cleanup | ✅ PASS — không đổi, watermark detector giữ nguyên hành vi on-demand. |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS — spec/plan/research/data-model/contracts/quickstart đều markdown thuần, tự đủ nghĩa. |
| V. Token & Context Economy | ✅ PASS — US4 cố tình chọn tái dùng `edge-tts` WordBoundary có sẵn thay vì thêm forced-alignment tool riêng (research.md §4); US3 tái dùng ASR segment + cách dịch sát nghĩa đã có, không viết ASR/dịch mới. |
| VI. Agentic Harness Discipline | ✅ PASS — root cause của US1/US2 đã reproduce và verify fix thật (không suy đoán) trước khi ghi vào research.md; tasks.md (bước sau) MUST chia nhỏ theo từng US, mỗi task verify được bằng bằng chứng cụ thể như đã làm ở 001/002. |

Không có vi phạm nào cần Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/003-dubbing-fixes-subtitles/
├── plan.md              # This file
├── research.md          # Phase 0 — root cause US1/US2 (verified thật), quyết định kỹ thuật US3/US4
├── data-model.md        # Phase 1 — mở rộng entity của 001 (script_mode+subtitle, dynamic_captions, Subtitle Track)
├── quickstart.md         # Phase 1 — kịch bản validate từng US
├── contracts/
│   ├── cli.md            # Phần mở rộng contracts/cli.md của 001
│   └── api.md            # Phần mở rộng contracts/api.md của 002
└── tasks.md              # Phase 2 (/speckit-tasks, chưa tạo)
```

### Source Code (repository root)

Không tạo project/thư mục mới — feature này sửa/mở rộng đúng các module đã có
ở 001-video-repurpose-pipeline và 002-web-ui:

```text
media-generation/
  requirements.txt        # + torchcodec (US1)
  merge/
    vocal_separator.py     # Không đổi logic — fix nằm ở requirements.txt (US1)
    ffmpeg_merge.py         # + nhánh burn-in subtitles (US3/US4), re-encode khi có phụ đề (research.md §7)
    subtitle_burner.py      # MỚI: sinh subtitles.srt từ Script.segments (US3) hoặc Voice Track.word_boundaries (US4), gọi ffmpeg burn-in
  tts/
    edge_tts_client.py      # + thu WordBoundary khi dynamic_captions=true (US4), ghi captions.json
  script_gen/
    router_client.py        # + tính target_char_budget (US2); + hàm dịch theo segment cho mode subtitle (US3)
  pipeline.py               # + script_mode="subtitle" (bỏ qua synthesizing), + --dynamic-captions flag, rẽ nhánh merging
  web/
    backend/
      jobs_api.py            # SubmitJobRequest + dynamic_captions, script_mode Literal + "subtitle", response + subtitles_burned
    frontend/
      src/pages/HomePage.tsx  # + option "Phụ đề tự động", + checkbox "Phụ đề động"
      src/api/client.ts        # + field dynamic_captions, subtitles_burned trong type JobDetail
```

**Structure Decision**: Web application (kế thừa nguyên cấu trúc `web/backend/`
+ `web/frontend/` đã dựng ở 002-web-ui) kết hợp CLI pipeline gốc của 001 —
đúng "Option 2" của template, không có project mới. Toàn bộ US1-US4 là sửa/mở
rộng file đã tồn tại, chỉ thêm đúng 1 file mới (`merge/subtitle_burner.py`)
cho logic burn-in dùng chung giữa US3 và US4 (tránh trùng lặp code giữa 2 use
case, đúng research.md §3/§4 đã quyết định dùng chung cơ chế).

## Complexity Tracking

Không có vi phạm Constitution Check nào cần biện minh — bảng để trống.

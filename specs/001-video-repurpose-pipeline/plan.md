# Implementation Plan: Video Repurpose Pipeline

**Branch**: `001-video-repurpose-pipeline` | **Date**: 2026-07-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-video-repurpose-pipeline/spec.md`

## Summary

Xây dựng một pipeline Python chạy dạng CLI/script cục bộ: nhận 1 URL video
(TikTok/Douyin ưu tiên, YouTube fallback) → tải video (watermark-free khi có thể)
→ trích xuất nội dung/lời thoại → tạo kịch bản (dịch hoặc tự soạn, theo lựa chọn
người dùng) → sinh giọng đọc tiếng Việt bằng edge-tts → ghép giọng đọc vào video
gốc bằng ffmpeg → xuất video sản phẩm cuối cùng. Toàn bộ trạng thái trung gian của
mỗi lần chạy được lưu theo job để có thể kiểm tra/gỡ lỗi (US1 P1 = MVP; US2/US3 mở
rộng nguồn và chế độ kịch bản).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `f2` (Douyin/TikTok, engine chính), `yt-dlp` (YouTube +
fallback, cũng dùng làm fallback runtime khi `f2` lỗi với TikTok), `faster-whisper`
(ASR/transcript), SDK `openai` trỏ vào 9router (`ROUTER_BASE_URL` từ `.env`, script
gen dịch/viết lại), `edge-tts` (TTS tiếng Việt, hỗ trợ tham số `rate` để khớp thời
lượng), `demucs` (tách vocal/nhạc nền, two-stems), `ffmpeg` qua `subprocess`/
`ffmpeg-python` (ghép video, mix audio). `video-subtitle-remover` được khai báo
dependency nhưng chỉ wiring ở mức detect/stub trong MVP này (xem Constitution
Check → Principle III).

**Storage**: Không dùng database. Toàn bộ state là file trên filesystem theo
`jobs/{job_id}/` (source.mp4, transcript.json, script.json, voice.wav, output.mp4,
job.json chứa trạng thái).

**Testing**: `pytest` cho unit test từng module (downloader, asr, script_gen, tts,
merge) với mock/fixture; `quickstart.md` làm kịch bản validate end-to-end thủ công
bằng 1 URL TikTok thật.

**Target Platform**: Máy cục bộ (macOS/Linux), chạy như CLI tool — không có
server/web deployment trong phạm vi MVP này (theo spec Assumptions).

**Project Type**: Single project — Python CLI tool (Option 1).

**Performance Goals**: Video gốc dưới 3 phút → toàn bộ pipeline (không tính thời
gian tải qua mạng) hoàn thành dưới 8 phút (SC-002, đã nới từ 5 lên 8 phút vì thêm
Demucs + 2-pass TTS).

**Constraints**: Không yêu cầu GPU cho luồng mặc định (faster-whisper, edge-tts,
Demucs two-stems đều chạy CPU chấp nhận được cho video ngắn); cần network để gọi
9router (LLM) và tải video; xử lý tuần tự 1 job tại 1 thời điểm, không cần
concurrency ở MVP. Demucs/TTS rate-adjustment KHÔNG được phép làm job fail cứng —
lỗi ở các bước này MUST fallback về hành vi cũ (mute audio gốc / giữ nguyên rate)
thay vì chặn cả pipeline.

**Scale/Scope**: Single-user, single-job-at-a-time. Không có yêu cầu multi-tenant
hay hàng đợi job trong bản đầu.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Đánh giá | Ghi chú |
|---|---|---|
| I. Python-Only Stack | ✅ PASS | Toàn bộ dependency (f2, yt-dlp, faster-whisper, openai SDK, edge-tts, ffmpeg-python) đều Python |
| II. Source-First, Fallback-Ready Downloading | ✅ PASS | `downloader/` dùng f2 làm engine chính (Douyin/TikTok), yt-dlp làm fallback (YouTube + nguồn khác) đúng thứ tự ưu tiên |
| III. On-Demand AI Cleanup | ✅ PASS (scoped) | Theo spec Assumptions, xử lý watermark cứng nằm ngoài phạm vi MVP. Plan vẫn đưa vào `clean_video/detector.py` như bước kiểm tra/log cảnh báo (đáp ứng yêu cầu "MUST có bước kiểm tra/quyết định" của Principle III) nhưng KHÔNG gọi video-subtitle-remover thật trong US1 — việc tích hợp AI inpainting đầy đủ là task hoãn lại, gắn cờ trong tasks.md |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS | plan.md, research.md, data-model.md, contracts/, quickstart.md đều markdown thuần, không phụ thuộc cơ chế riêng Claude Code |
| V. Token & Context Economy | ✅ PASS | Không thêm framework/skill nào ngoài Spec Kit; plan giữ đúng phạm vi spec, không lặp nội dung constitution |
| VI. Agentic Harness Discipline | ✅ PASS (áp dụng ở bước tasks) | Plan này sẽ được chia nhỏ thành task verify-độc-lập ở `/speckit-tasks`; mỗi task tuân theo plan.md này, không tự đổi phạm vi khi Antigravity thực thi |

**Kết quả**: Không có vi phạm nào cần biện minh → không cần điền Complexity Tracking.

**Re-check sau Phase 1 (design)**: research.md, data-model.md, contracts/, quickstart.md
không đưa thêm công nghệ/dependency nào ngoài bảng Technology Stack đã khoá — toàn
bộ 6 principle vẫn PASS, không phát sinh vi phạm mới.

## Project Structure

### Documentation (this feature)

```text
specs/001-video-repurpose-pipeline/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   ├── cli.md
│   └── job-state-schema.md
└── tasks.md              # Phase 2 output (/speckit-tasks — chưa tạo)
```

### Source Code (repository root)

```text
media-generation/
├── downloader/
│   ├── __init__.py
│   ├── f2_client.py         # Douyin/TikTok, engine chính (Constitution Principle II)
│   └── ytdlp_client.py       # YouTube + fallback
├── clean_video/
│   ├── __init__.py
│   └── detector.py           # detect watermark/hardsub còn sót; MVP chỉ log cảnh báo
├── asr/
│   ├── __init__.py
│   └── transcriber.py        # faster-whisper wrapper
├── script_gen/
│   ├── __init__.py
│   └── router_client.py      # gọi 9router (OpenAI-compatible), 2 mode: translate / rewrite
├── tts/
│   ├── __init__.py
│   └── edge_tts_client.py    # sinh voice tiếng Việt
├── merge/
│   ├── __init__.py
│   ├── vocal_separator.py    # Demucs two-stems: tách nhạc nền khỏi audio gốc
│   └── ffmpeg_merge.py       # trộn voice + nhạc nền, ghép vào video gốc
├── pipeline.py                # orchestrator CLI entrypoint (điều phối tuần tự + lưu job state)
├── jobs/{job_id}/              # runtime output, không commit vào git
├── tests/
│   ├── unit/
│   └── integration/
├── requirements.txt
└── pyproject.toml
```

**Structure Decision**: Single project Python CLI tool (Option 1) — đúng theo
`Project Structure` đã khoá trong constitution, được mở rộng chi tiết thành từng
file cụ thể cho feature này. Không dùng Option 2/3 (không có frontend/mobile).

## Complexity Tracking

> Không có vi phạm Constitution Check nào cần biện minh — bảng này để trống.

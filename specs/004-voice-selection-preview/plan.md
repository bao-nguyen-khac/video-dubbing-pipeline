# Implementation Plan: Chọn giọng đọc & nghe thử trước khi chạy job

**Branch**: `004-voice-selection-preview` | **Date**: 2026-07-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-voice-selection-preview/spec.md`

## Summary

Cho người dùng chọn giọng đọc cụ thể (edge-tts hoặc LucyAI/Vivibe) và nghe
thử trước khi chạy job lồng tiếng, thay vì luôn dùng cố định 1 giọng nam mặc
định. Thêm module `tts/lucyai_client.py` tích hợp API LucyAI (`api.lucylab.io`,
JSON-RPC) làm provider thứ 2; mở rộng `Job` với `tts_provider`/`voice_id`;
thêm 2 endpoint web mới (`GET /api/voices`, `POST /api/voices/preview`)
không đụng tới cơ chế job hiện có (research.md §3).

## Technical Context

**Language/Version**: Python 3.11 (backend/pipeline, không đổi); TypeScript/ReactJS (frontend, thêm dropdown giọng + nút nghe thử)

**Primary Dependencies**: `edge-tts` (đã có, dùng thêm `list_voices()`), `httpx`/`requests` cho JSON-RPC tới LucyAI (đã có `httpx` trong requirements.txt qua f2/yt-dlp, tái dùng thay vì thêm SDK mới) — không thêm dependency ngoài.

**Storage**: Không đổi so với 001/003 — `jobs/{job_id}/job.json` thêm 2 field. Voice list không lưu trữ, tổng hợp động mỗi request.

**Testing**: Verify thủ công qua chạy job thật (CLI + Docker), như 001/002/003. Phần LucyAI thật cần `VIVIBE_API_KEY` của người dùng — xem research.md §2 "Giới hạn khi implement".

**Target Platform**: Linux container (Docker), không đổi.

**Project Type**: Web application (kế thừa `web/backend/` + `web/frontend/` của 002, CLI pipeline của 001) — không thêm project mới.

**Performance Goals**: Preview MUST trả kết quả trong ≤10s (SC-002) — LucyAI polling mỗi 2s theo đúng khuyến nghị docs, timeout tổng hợp lý (research.md §3).

**Constraints**: LucyAI `speed` giới hạn `[0.5, 2.0]` (hẹp hơn edge-tts `rate` `[-20%, +40%]`) — 2-pass duration-matching cho LucyAI dùng đúng khoảng này (research.md §4).

**Scale/Scope**: Không đổi so với 001-003 — vẫn 1 job xử lý tại 1 thời điểm; preview là thao tác độc lập không tính vào rule đó (FR-008).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Đánh giá |
|---|---|
| I. Python-Only Stack | ✅ PASS — `tts/lucyai_client.py` Python thuần; frontend chỉ thêm UI React cho dropdown/nút đã có cơ chế (002). |
| II. Source-First, Fallback-Ready Downloading | ✅ PASS — không đụng bước download. |
| III. On-Demand AI Cleanup | ✅ PASS — không đụng watermark detector. |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS — spec/plan/research/data-model/contracts/quickstart đều markdown thuần. |
| V. Token & Context Economy | ✅ PASS — tái dùng `httpx` đã có thay vì thêm SDK LucyAI riêng; tái dùng kiến trúc 2-pass duration-matching của 003 thay vì viết cơ chế mới; KHÔNG mở rộng dynamic_captions sang LucyAI (ngoài phạm vi, research.md §4) để tránh scope creep. |
| VI. Agentic Harness Discipline | ✅ PASS — danh sách giọng edge-tts đã verify thật (research.md §1) trước khi lên plan; phần LucyAI thật cần key người dùng, đã ghi rõ giới hạn verify thay vì giả vờ đã test. |

Không có vi phạm nào cần Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/004-voice-selection-preview/
├── plan.md              # This file
├── research.md          # Phase 0 — danh sách voice edge-tts thật, thiết kế LucyAI client, preview
├── data-model.md        # Phase 1 — entity Voice mới, mở rộng Job/Voice Track
├── quickstart.md         # Phase 1 — kịch bản validate US1/US2
├── contracts/
│   ├── cli.md            # Mở rộng contracts/cli.md của 001/003
│   └── api.md            # Mở rộng contracts/api.md của 002/003
└── tasks.md              # Phase 2 (/speckit-tasks, chưa tạo)
```

### Source Code (repository root)

Không tạo project mới — mở rộng đúng module đã có ở 001/002/003:

```text
media-generation/
  .env.example             # + VIVIBE_API_KEY
  requirements.txt         # Không thêm dependency mới (dùng httpx đã có)
  tts/
    edge_tts_client.py      # + list_voices() (lọc vi-VN, không hardcode nữa)
    lucyai_client.py        # MỚI: list_voices(), synthesize() qua JSON-RPC api.lucylab.io
  pipeline.py               # + --tts-provider/--voice-id, dispatch provider ở bước synthesizing
  web/
    backend/
      voices_api.py          # MỚI: GET /api/voices, POST /api/voices/preview
      jobs_api.py             # SubmitJobRequest + tts_provider/voice_id, Job Detail + 2 field mới
      main.py                  # mount thêm voices_router
    frontend/
      src/pages/HomePage.tsx   # + dropdown chọn giọng, nút "Nghe thử"
      src/api/client.ts         # + listVoices(), previewVoice(), submitJob() + tts_provider/voice_id
```

**Structure Decision**: Web application (Option 2, kế thừa nguyên cấu trúc
đã có) — chỉ thêm đúng 2 file mới (`tts/lucyai_client.py`,
`web/backend/voices_api.py`), còn lại là mở rộng file đã tồn tại. Không có
project/thư mục mới nào.

## Complexity Tracking

Không có vi phạm Constitution Check nào cần biện minh — bảng để trống.

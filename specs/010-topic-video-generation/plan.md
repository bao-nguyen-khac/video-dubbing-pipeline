# Implementation Plan: Tạo video từ chủ đề bằng AI (script + ảnh + giọng đọc tự động)

**Branch**: `010-topic-video-generation` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-topic-video-generation/spec.md`

## Summary

Thêm 1 pipeline MỚI, song song với pipeline dub hiện có (`pipeline.py`), nhận
**chủ đề văn bản** (không phải URL) làm input: LLM (9router, model agent có
tool-use) viết outline → tự tra cứu web bổ sung dữ kiện còn thiếu → viết kịch
bản chi tiết chia thành Scene (mỗi scene = 1 đoạn giọng đọc + 1 ảnh minh hoạ) →
(nếu bật "quản lý pipeline") dừng chờ người dùng duyệt outline/scene → tìm ảnh
minh hoạ mỗi scene qua Pexels → đọc giọng từng scene (tái dùng adapter TTS đã
có) → sinh HTML timeline theo scene JSON (1 layout cố định) → render bằng
HyperFrames (`npx hyperframes render`, ngoại lệ Node.js đã amend ở Constitution
v1.11.0) ra `output.mp4`.

Vì job.json/state-machine hiện tại (`pipeline.py`) gắn chặt với khái niệm
"download từ URL" (source_url/platform bắt buộc, `status_from_artifacts()` suy
luận theo artifact của luồng dub), tính năng này KHÔNG chèn vào `run_pipeline()`
hiện có mà tạo 1 orchestrator riêng (`generate_pipeline.py`) với state machine
riêng, dùng chung field `job_type` để phân biệt 2 loại job trong cùng
`jobs/{job_id}/job.json`.

**Quyết định kỹ thuật quan trọng nhất** (chi tiết ở [research.md](./research.md)):

1. **Pipeline riêng, không tái dùng `run_pipeline()`** — luồng "generate" không
   có bước download/ASR, và trạng thái/artifact hoàn toàn khác luồng dub; tái
   dùng ép buộc sẽ làm `status_from_artifacts()`/`RERUN_STEPS` phải if/else
   theo `job_type` khắp nơi, vi phạm Token & Context Economy hơn là tách riêng.
2. **HyperFrames CHỈ nhận HTML timeline sinh sẵn từ Scene JSON bằng Python**
   (template string/Jinja2 cố định 1 layout) — không để LLM tự viết HTML, để
   dễ debug/kiểm soát và không lệch ngoại lệ Constitution (chỉ dùng Node.js ở
   đúng bước gọi `npx hyperframes render`, mọi logic sinh HTML vẫn Python).
3. **Search web tái dùng model agent có sẵn trong 9router** (đã xác nhận ở
   `/speckit-clarify`) — không thêm search API/key bên thứ ba, không thêm dòng
   Technology Stack mới cho việc này.
4. **Ảnh minh hoạ: Pexels** (Photos + Videos API hợp nhất, free tier đủ dùng) —
   ĐÂY LÀ 1 DÒNG MỚI trong Technology Stack, MUST amend constitution trước
   `/speckit-implement` (xem [Constitution Check](#constitution-check)).
5. **Chốt duyệt outline/scene (FR-012) tái dùng `review/gates.py`** — thêm
   `GATE_OUTLINE` vào cơ chế gate tổng quát đã có (file JSON + editable field +
   `mark_reached`/`save_edits`/`mark_approved`), không viết review-gate riêng
   từ đầu.

## Technical Context

**Language/Version**: Python 3.11 (toàn bộ orchestration/script-gen/TTS/scene
logic) + Node.js 22+ CHỈ cho bước gọi `npx hyperframes render` qua subprocess
(Constitution Principle I, Ngoại lệ #2, v1.11.0). Máy dev hiện tại đã có Node
v22.19.0/npm 10.9.3.

**Primary Dependencies MỚI**: `httpx` (đã có sẵn — dùng gọi Pexels REST) +
Pexels Photos/Videos API (`https://api.pexels.com/v1` + `/videos`, cần
`PEXELS_API_KEY`) + gói npm `hyperframes` (cài qua `npx hyperframes` khi cần,
không phải Python dependency). Không thêm Python package mới vào
`requirements.txt`.

⚠️ **Pexels là 1 dòng MỚI trong bảng Technology Stack (Locked Decisions) của
constitution.md — theo Governance, MUST đi qua `/speckit-constitution` amend
TRƯỚC khi implement, không được thêm ngầm.** (HyperFrames đã amend xong ở
v1.11.0 — chỉ còn thiếu dòng Pexels.) Xem [Constitution Check](#constitution-check).

**Storage**: file JSON theo đúng khuôn mẫu `jobs/{job_id}/` hiện có —
`outline.json` (mới), `scenes.json` (mới, scene JSON — cũng là file review gate
`GATE_OUTLINE`), `scenes/{i}/image.jpg` + `scenes/{i}/voice.wav` (mới, tài
nguyên từng scene), `render.html` (mới, HTML timeline sinh cho HyperFrames),
`output.mp4`. Field mới trong `job.json`: `job_type` ("dub" mặc định khi vắng
mặt — tương thích ngược với job cũ | "generate"), `topic`, `scenes`.

**Testing**: pytest, theo đúng khuôn mẫu — `httpx`/Pexels/`ffmpeg`/`ffprobe`/
`npx hyperframes` MUST mock trong unit test (Constitution VI). Không có test
tự động gọi 9router/Pexels/HyperFrames thật; verify end-to-end thật là bước
RIÊNG (quickstart.md).

**Target Platform**: Giống pipeline hiện có — Docker `python:3.11-slim` +
`ffmpeg`, CỘNG thêm Node.js 22+ trong cùng image (cần sửa Dockerfile — xem
Complexity Tracking).

**Project Type**: Web application (FastAPI backend + React SPA) trên nền CLI
Python — thêm 1 orchestrator CLI/backend mới (`generate_pipeline.py`), không
đổi cấu trúc frontend/backend hiện có.

**Performance Goals**: Không có SLA cứng (job xử lý bất đồng bộ, người dùng
poll trạng thái — đúng pattern hiện có). Thời gian chạy phụ thuộc số scene
(mỗi scene: 1 lượt search ảnh + 1 lượt TTS) + 1 lần render HyperFrames cuối.

**Constraints**: (a) Chỉ 1 job "generate" hoặc "dub" chạy đồng thời — tái dùng
đúng khoá `find_running_job_id()` hiện có, coi 2 loại job là CÙNG 1 hàng đợi
(không chạy song song 2 job dù khác loại, giữ nguyên giả định tài nguyên máy
đơn hiện tại); (b) HyperFrames render cần Chrome headless — máy chạy pipeline
MUST có đủ dependency hệ thống cho Puppeteer/Playwright-class browser (xem
research.md); (c) Video 1-5 phút, tỉ lệ dọc 9:16 (Assumptions của spec).

**Scale/Scope**: 1 người dùng, 1 job "generate" tại 1 thời điểm — không có yêu
cầu concurrency mới so với hệ thống hiện tại.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Kết quả | Ghi chú |
|---|---|---|
| I. Python-Only Stack | ✅ PASS | Toàn bộ orchestration/script-gen/TTS/scene-JSON/HTML-templating là Python; DUY NHẤT bước gọi `npx hyperframes render` dùng Node.js — đúng Ngoại lệ #2 đã amend (Constitution v1.11.0, xem spec Clarifications) |
| II. Source-First Downloading | ✅ N/A | Không có bước download — input là topic, không phải URL |
| III. On-Demand AI Cleanup | ✅ N/A | Không có video nguồn nên không có watermark/hardsub gốc để cleanup |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS | plan/research/data-model/contracts/quickstart là markdown thuần |
| V. Token & Context Economy | ⚠️ Có thêm dependency | Thêm Pexels (1 dòng Technology Stack) + `npx hyperframes` (đã amend) — có lý do rõ ràng (không có kho ảnh/renderer thuần Python nào đáp ứng đúng yêu cầu người dùng), không phải thêm tuỳ tiện. Tái dùng tối đa: `review/gates.py`, TTS adapter, `router_client.py` |
| VI. Agentic Harness Discipline | ✅ PASS | `outline.json`/`scenes.json`/`render.html` là artifact trung gian audit được; test MUST mock Pexels/ffmpeg/hyperframes thật; TTS test mặc định edge-tts (không gọi LucyAI/Vivibe thật) |
| **Technology Stack (locked)** | ❌ **CHƯA PASS — thiếu 1 amend** | HyperFrames đã có ở bảng (v1.11.0). **Pexels CHƯA có trong bảng** — MUST chạy `/speckit-constitution` thêm dòng "Ảnh minh hoạ (feature 010)" TRƯỚC `/speckit-tasks`/`/speckit-implement`. Xem Complexity Tracking |
| Project Structure | ⚠️ Mở rộng | Thêm module top-level MỚI: `generate_pipeline.py` (orchestrator riêng), `assets/` (Pexels client), `merge/hyperframes_renderer.py` (sinh HTML + gọi render) — theo đúng khuôn mẫu module hoá đã có (`hardsub/`, `publish/`) |

**Post-Phase-1 re-check**: Thiết kế Phase 1 (data-model/contracts) không phát
sinh vi phạm nào ngoài mục Technology Stack (Pexels) đã nêu — xem Complexity
Tracking.

**⚠️ HÀNH ĐỘNG BẮT BUỘC TRƯỚC KHI IMPLEMENT**: chạy `/speckit-constitution`
thêm Pexels vào Technology Stack (mẫu: dòng HyperFrames đã thêm ở v1.11.0).
`/speckit-tasks` vẫn tạo được (không phụ thuộc gate này), nhưng
`/speckit-implement` KHÔNG được chạy task nào gọi Pexels thật cho tới khi amend
xong.

## Project Structure

### Documentation (this feature)

```text
specs/010-topic-video-generation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.md            # Phase 1 output — endpoint mới + payload review gate mở rộng
├── checklists/
└── tasks.md              # Phase 2 (/speckit-tasks — KHÔNG tạo ở lệnh này)
```

### Source Code (repository root)

```text
media-generation/
├── generate_pipeline.py         # MỚI — orchestrator riêng cho job_type="generate":
│                                #   create_generate_job() (tương tự create_job()) +
│                                #   run_generate_pipeline(topic, ...) với state machine
│                                #   riêng: pending → outlining → scripting →
│                                #   (awaiting_review nếu supervised) → sourcing_assets →
│                                #   synthesizing → rendering → done/failed
├── script_gen/
│   ├── router_client.py         # KHÔNG SỬA logic dịch/rewrite hiện có — thêm hàm mới
│   │                            #   dùng chung _chat_completion()/model 9router
│   └── topic_script_generator.py # MỚI — write_outline() → search bằng chính model
│                                #   agent của 9router (tool-use, KHÔNG gọi search API
│                                #   riêng) → write_detailed_script_with_scenes() trả
│                                #   về Scene JSON (data-model.md §2)
├── assets/                      # MỚI — nguồn hình ảnh minh hoạ (KHÁC downloader/:
│   ├── __init__.py               #   đó là tải VIDEO NGUỒN, đây là tìm ẢNH MINH HOẠ)
│   └── pexels_client.py          #   search_image(query) → Pexels Photos API; fallback
│                                #   ảnh generic khi không có kết quả (FR-010)
├── merge/
│   └── hyperframes_renderer.py   # MỚI — render_scenes_to_video(scenes, job_dir):
│                                #   sinh render.html từ scene JSON (template string cố
│                                #   định, KHÔNG để LLM viết HTML) rồi subprocess gọi
│                                #   `npx hyperframes render` → output.mp4
├── review/
│   └── gates.py                  # SỬA: + GATE_OUTLINE vào GATES/NEXT_STATUS_AFTER_GATE/
│                                #   EDITABLE_FIELD (editable_field="narration_text") —
│                                #   tái dùng nguyên build_payload/save_edits/mark_*
├── web/
│   ├── backend/
│   │   ├── generate_jobs_api.py  # MỚI — POST /api/generate-jobs, GET (list/detail),
│   │   │                        #   GET output — song song jobs_api.py, KHÔNG sửa
│   │   │                        #   file đó (job_type khác hẳn payload)
│   │   └── review_api.py         # SỬA: route review hiện có (`/api/jobs/{id}/review`)
│   │                            #   đã generic theo `gate` — chỉ cần GATE_OUTLINE hợp lệ
│   │                            #   trong review/gates.py là dùng lại được, không sửa
│   │                            #   route
│   └── frontend/                 # SỬA: thêm tab/entry point mới "Tạo video từ chủ đề"
│                                #   (input topic text, không phải URL) — chi tiết UI ở
│                                #   Phase 2 tasks, không thuộc phạm vi plan
├── jobs/{job_id}/                # + outline.json, scenes.json, scenes/{i}/image.*,
│                                #   scenes/{i}/voice.wav, render.html (field mới trong
│                                #   Project Structure, xem data-model.md)
├── requirements.txt              # KHÔNG đổi — httpx đã có sẵn
├── package.json                  # MỚI (repo root hoặc jobs/{job_id}/.hyperframes/) —
│                                #   khai báo dependency `hyperframes`, xem research.md §5
└── Dockerfile                    # SỬA: cài thêm Node.js 22+ + dependency hệ thống cho
                                 #   Chrome headless (Complexity Tracking)
```

**Structure Decision**: Web application hiện có (FastAPI + React) giữ nguyên;
thêm 1 pipeline CLI/orchestrator song song (`generate_pipeline.py`) thay vì mở
rộng `pipeline.py`, theo đúng lý do đã nêu ở Summary — state machine và
artifact của luồng "generate" khác hẳn luồng "dub", ép chung sẽ phải rẽ nhánh
`job_type` khắp `pipeline.py`/`status_from_artifacts()`/`RERUN_STEPS`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| Thêm Pexels vào Technology Stack (chưa amend) | Không có kho ảnh/video stock miễn phí nào khác đã tích hợp sẵn trong hệ thống; Pexels có cả Photos + Videos API hợp nhất, free tier đủ dùng cho scope 1-5 phút/video | Tự crawl/scrape ảnh: vi phạm tinh thần "không tự viết scraper khi API sẵn có đáp ứng đủ" (đã áp dụng cho Principle II); AI-generate ảnh (DALL-E/SD): tốn chi phí/thời gian hơn nhiều cho MVP, đã loại ở Assumptions của spec |
| Dockerfile cần cài Node.js 22+ + Chrome headless deps | HyperFrames (đã amend Principle I) bắt buộc runtime này để render | Không có: đây là hệ quả trực tiếp của quyết định dùng HyperFrames đã chốt, không có cách nào chạy `npx hyperframes render` mà không có Node + Chrome |
| `generate_pipeline.py` là orchestrator THỨ HAI (không tái dùng `run_pipeline()`) | State machine/artifact hoàn toàn khác luồng dub (không download/ASR, có outline/scene) — ép chung sẽ buộc `status_from_artifacts()`/`RERUN_STEPS`/mọi endpoint dùng `RERUN_STEPS` phải rẽ nhánh `job_type` ở nhiều nơi | Đã cân nhắc mở rộng `run_pipeline(url=None, topic=...)` — bị loại vì `detect_platform(url)` là bước đầu tiên bắt buộc, và toàn bộ `RERUN_STEPS`/`status_from_artifacts()` giả định thứ tự bước của luồng dub, sửa an toàn tốn công hơn nhiều so với 1 orchestrator riêng dùng chung `job_type` + `find_running_job_id()` |

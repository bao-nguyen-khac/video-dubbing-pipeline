<!--
Sync Impact Report
- Version change: template (unratified) → 1.0.0
- Modified principles: N/A (initial ratification, filled from template placeholders)
- Added sections: Technology Stack (Locked Decisions), Project Structure
- Removed sections: none
- Templates requiring updates:
  - .specify/templates/plan-template.md ✅ no changes needed (generic Constitution Check gate, fills per-feature)
  - .specify/templates/spec-template.md ✅ no changes needed (generic, technology-agnostic by design)
  - .specify/templates/tasks-template.md ✅ no changes needed (generic phase structure)
- Follow-up TODOs: none
-->

# Media Generation Pipeline Constitution

## Core Principles

### I. Python-Only Stack
Toàn bộ pipeline (download, ASR, script gen, TTS, merge) MUST được viết bằng Python.
Không dùng Node.js hay ngôn ngữ khác cho runtime logic. Rationale: các model AI cốt
lõi (ASR, TTS, video inpainting) đều native Python/PyTorch; một stack duy nhất giảm
chi phí bảo trì và tránh phải viết sidecar/bridge giữa 2 runtime.

### II. Source-First, Fallback-Ready Downloading
Douyin và TikTok là nguồn ưu tiên hàng đầu. Download MUST dùng f2 (Johnserf-Seed)
làm engine chính vì lấy được link watermark-free trực tiếp từ API gốc của
Douyin/TikTok. yt-dlp MUST có sẵn làm fallback cho YouTube và các nguồn f2 không
hỗ trợ. Không tự viết scraper riêng khi f2/yt-dlp đã đáp ứng được nhu cầu.

### III. On-Demand AI Cleanup (không phải bước mặc định)
video-subtitle-remover (AI inpainting) CHỈ được gọi khi video tải về vẫn còn
watermark/hardsub burn cứng sau bước download. Đây KHÔNG phải bước bắt buộc trong
pipeline chính vì tốn compute (GPU) và làm chậm luồng xử lý — pipeline MUST có bước
kiểm tra/quyết định trước khi kích hoạt bước cleanup này.

### IV. Portable, Agent-Agnostic Artifacts (NON-NEGOTIABLE)
Mọi spec/plan/tasks sinh ra từ Spec Kit MUST là markdown thuần, tự đủ nghĩa, không
phụ thuộc cơ chế riêng của Claude Code. Rationale: kế hoạch được lập trong Claude
Code nhưng code được thực thi trong Antigravity — artifact phải để agent khác đọc
và implement được mà không cần lại ngữ cảnh hội thoại gốc.

### V. Token & Context Economy
Tránh thêm framework/plugin/skill nặng không cần thiết ngoài Spec Kit trừ khi có
nhu cầu cụ thể được xác nhận. Constitution, spec, plan MUST giữ ngắn gọn, đúng
trọng tâm, không lặp lại thông tin đã có ở artifact khác.

## Technology Stack (Locked Decisions)

| Bước | Công nghệ | Ghi chú |
|---|---|---|
| Download | f2 (chính), yt-dlp (fallback) | Ưu tiên Douyin/TikTok, watermark-free từ nguồn |
| Cleanup watermark/hardsub | video-subtitle-remover | On-demand, xem Principle III |
| ASR | faster-whisper | Dùng khi cần transcript/timestamp để dịch |
| Script gen (dịch/viết lại) | LLM qua 9router | OpenAI-compatible endpoint `http://localhost:20128/v1`, SDK `openai` |
| TTS | edge-tts | Lựa chọn hiện tại: free, không cần GPU. VietTTS (voice cloning tiếng Việt tự nhiên hơn) là hướng nâng cấp sau, không bắt buộc ngay |
| Ghép video | ffmpeg | Qua subprocess hoặc ffmpeg-python |

Thay đổi bất kỳ dòng nào trong bảng này MUST đi qua amend constitution (Governance),
không được đổi ngầm trong plan.md của từng feature.

## Project Structure

```text
media-generation/
  downloader/       # f2 (douyin/tiktok) + yt-dlp (fallback)
  clean_video/       # video-subtitle-remover, gọi on-demand
  asr/               # faster-whisper
  script_gen/        # gọi 9router
  tts/               # edge-tts
  merge/             # ffmpeg
  pipeline.py        # điều phối tuần tự, lưu state theo job
  jobs/{job_id}/      # file trung gian: source.mp4, transcript.json, script.json, voice.wav, output.mp4
```

## Governance

Constitution này supersedes mọi quyết định kỹ thuật ad-hoc trong spec/plan. Thay đổi
công nghệ đã "chốt" (bảng Technology Stack) MUST đi qua amend constitution trước,
không sửa trực tiếp trong plan.md của từng feature. Mọi spec/plan MUST được review
đối chiếu 5 Core Principles ở trên trước khi implement (Constitution Check gate
trong plan-template.md).

Versioning theo semver: MAJOR khi đổi framework nền tảng (vd đổi ngôn ngữ khỏi
Python); MINOR khi thêm/đổi 1 công nghệ trong bảng Technology Stack hoặc thêm
principle mới; PATCH khi chỉnh sửa câu chữ/làm rõ nghĩa không đổi quy tắc.

**Version**: 1.0.0 | **Ratified**: 2026-07-25 | **Last Amended**: 2026-07-25

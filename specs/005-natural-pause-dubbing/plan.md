# Implementation Plan: Lồng tiếng khớp nhịp tự nhiên theo từng câu

**Branch**: `005-natural-pause-dubbing` | **Date**: 2026-07-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-natural-pause-dubbing/spec.md`

## Summary

Thay cơ chế "tổng hợp giọng đọc 1 khối liên tục rồi kéo giãn/nén đều toàn bộ
cho khớp tổng thời lượng" bằng cơ chế **theo từng nhịp**: gom ASR segment
thành các *dubbing unit* theo khoảng lặng thật của video gốc, sinh kịch bản
dịch/viết lại đúng 1 dòng cho mỗi unit, gọi TTS riêng từng unit, chỉ **tăng
tốc cục bộ** trong biên `atempo ∈ [1.0, 1.4]` khi unit tràn khung (không bao
giờ đọc chậm để lấp khung — đó chính là root cause), rồi ghép timeline có
khoảng lặng thật giữa các unit; unit tràn đẩy lùi unit kế tiếp thay vì bị cắt
(FR-009). Kèm 2 hệ quả trực tiếp: lỗi TTS 1 unit không còn làm hỏng cả job
(thay bằng khoảng lặng + cảnh báo riêng), và `captions.json` nay lấy mốc từ
timeline thật nên phụ đề động chính xác với **cả 3 provider** (gỡ hẳn cơ chế
`SentenceBoundary` riêng của edge-tts).

Toàn bộ dựa trên hạ tầng đã có: mốc thời gian ASR (001), cách dịch theo dòng
đánh số đã verify ở chế độ Phụ đề tự động (003/US3), hậu xử lý `atempo` đã
dùng cho Vivibe/9router (004) — không thêm dependency, không thêm bước trong
state machine.

## Technical Context

**Language/Version**: Python 3.11 (pipeline/backend, không đổi so với
001/002/003/004); TypeScript/ReactJS (frontend — chỉ thêm 1 nhãn cảnh báo và
2 field type).

**Primary Dependencies**: Không thêm package mới. Dùng lại `faster-whisper`
(mốc segment), `openai` SDK (9router), `edge-tts` / Vivibe JSON-RPC /
9router `/audio/speech` (TTS mức text — đã có sẵn cho tính năng nghe thử của
004), `ffmpeg` (`atempo`, concat demuxer, chuẩn hoá WAV — đều là filter/muxer
đã dùng trong repo), `wave` (stdlib, sinh file khoảng lặng).

**Storage**: Files trong `jobs/{job_id}/` như các feature trước, thêm
`voice_timeline.json` và thư mục trung gian `segments/` (audio từng nhịp +
khoảng lặng, phục vụ resume). Xem [data-model.md](data-model.md).

**Testing**: Verify thủ công qua chạy job thật (CLI + Docker + web UI) theo
[quickstart.md](quickstart.md) — dự án chưa có test suite tự động
(Constitution Principle V). Các tiêu chí SC-001/SC-002/SC-004 được kiểm bằng
cách đọc số liệu trong `voice_timeline.json` + `transcript.json` (đo được, không
"nghe thấy có vẻ ổn").

**Target Platform**: Linux container (Docker), không đổi.

**Project Type**: Web application (CLI pipeline + FastAPI backend + React
frontend) — kế thừa cấu trúc đã có, không thêm project mới.

**Performance Goals**: Số lượt gọi TTS tăng từ 1 → N (N = số dubbing unit,
thực tế ~15-30 với video ngắn TikTok/Douyin) — spec Assumptions đã chấp nhận
đánh đổi này. Bù lại bỏ được lượt sinh lại toàn bài khi chỉnh rate (edge-tts
hiện gọi 2 lượt cho cả bài) và lượt `stream()` phụ để thu caption. Gọi tuần
tự (không song song) để không phá vỡ giới hạn quota/phút đã biết của 9router
(README đã ghi nhận lỗi "exceeded your current quota").

**Constraints**: Giữ nguyên biên tốc độ đã có, không nới (spec Assumptions) —
trần dùng chung `atempo ≤ 1.4` lấy từ biên hẹp nhất (`edge-tts +40%`), sàn
`1.0` do chính tính năng này áp đặt. Máy chạy Docker ~2.8GB RAM (ghi nhận ở
003) — không đổi vì không thêm model/AI mới.

**Scale/Scope**: Không đổi — 1 job xử lý tại 1 thời điểm, video ngắn dạng
TikTok/Douyin/YouTube Shorts. Phạm vi code: 1 module mới + sửa 6 file có sẵn.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Đánh giá (pre-research) | Re-check (post-design) |
|---|---|---|
| I. Python-Only Stack | ✅ PASS — toàn bộ logic mới là Python thuần trong `tts/`, `script_gen/`, `pipeline.py`; frontend chỉ thêm nhãn cảnh báo + 2 field type. | ✅ PASS — thiết kế không phát sinh runtime nào ngoài Python + ffmpeg subprocess. |
| II. Source-First, Fallback-Ready Downloading | ✅ PASS — không chạm bước download. | ✅ PASS |
| III. On-Demand AI Cleanup | ✅ PASS — không chạm watermark detector. | ✅ PASS |
| IV. Portable, Agent-Agnostic Artifacts | ✅ PASS — mọi artifact là markdown thuần, tự đủ nghĩa cho agent thực thi (Antigravity) đọc mà không cần hội thoại gốc. | ✅ PASS — research/data-model/contracts/quickstart đều nêu rõ hằng số, shape file và bằng chứng cần thu. |
| V. Token & Context Economy | ✅ PASS — không thêm dependency; tái dùng `_parse_numbered_lines()`/`_chat_completion()` của 003 và `atempo` của 004 thay vì viết cơ chế mới. | ✅ PASS — thiết kế còn **giảm** bề mặt code: gỡ 3 hàm tổng hợp nguyên khối, gỡ cơ chế streaming caption riêng của edge-tts, gỡ vòng retry ngân sách ký tự toàn bài (research.md §2/§6/§7). Chỉ 1 file mới. |
| VI. Agentic Harness Discipline | ✅ PASS — mọi hằng số ngưỡng được chốt bằng số cụ thể trong research.md để task không phải "đoán"; timeline ghi ra file nên mọi quyết định của bước TTS audit lại được. | ✅ PASS — `voice_timeline.json` chính là bằng chứng kiểm tra được cho SC-001/SC-002/SC-004; quickstart.md nêu đúng cách đo từng tiêu chí. |

**Lưu ý về Technology Stack (bảng khoá trong Constitution)**: không đổi dòng
nào — vẫn edge-tts (mặc định) + LucyAI/Vivibe + 9router TTS, vẫn ffmpeg cho
ghép, vẫn Demucs cho nhạc nền. Feature này chỉ đổi *cách gọi* các công nghệ đã
khoá, nên **không cần amend constitution**.

Không có vi phạm nào cần Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-natural-pause-dubbing/
├── plan.md              # This file
├── spec.md              # Input (đã có, kèm 2 Clarification đã chốt)
├── research.md          # Phase 0 — 7 quyết định kỹ thuật + hằng số ngưỡng
├── data-model.md        # Phase 1 — Dubbing Unit, Voice Timeline, thay đổi Script/Job/Caption
├── quickstart.md        # Phase 1 — kịch bản validate từng US + cách đo SC-001..SC-004
├── contracts/
│   ├── cli.md            # Mở rộng contracts/cli.md của 001/003
│   └── api.md            # Mở rộng contracts/api.md của 002/003
├── checklists/
│   └── requirements.md   # Đã có từ /speckit-specify
└── tasks.md              # Phase 2 (/speckit-tasks — CHƯA tạo)
```

### Source Code (repository root)

Không tạo project/thư mục mới. Đúng 1 file nguồn mới; phần còn lại là sửa file
đã có:

```text
video-dubbing-pipeline/
  tts/
    segment_synthesizer.py   # MỚI — trái tim của feature: gom unit → gọi TTS từng
                              #   unit (adapter chung 3 provider, 2 lần thử) → atempo
                              #   [1.0,1.4] → ghép timeline có khoảng lặng thật →
                              #   ghi voice.wav + voice_timeline.json + captions.json
    edge_tts_client.py        # − synthesize(), − _collect_captions(),
                              #   − _stream_sentence_boundaries(), − collect_captions
                              #   (research.md §6/§7); giữ synthesize_text()/list_voices()
    lucyai_client.py          # − synthesize_from_script(); + synthesize_text() (chữ ký
                              #   adapter chung, tự đọc VIVIBE_API_KEY từ env)
    router_tts_client.py      # − synthesize_from_script(); giữ synthesize_text()
  script_gen/
    router_client.py          # + group_segments() (gom ASR segment → dubbing unit),
                              #   + SEGMENT_REWRITE_SYSTEM, generate_script() nay sinh
                              #   script.json có segments cho translate/rewrite;
                              #   − vòng retry ngân sách ký tự toàn bài (research.md §2)
    # translate_segments()/_parse_numbered_lines()/_chat_completion(): tái dùng, không đổi
  pipeline.py                 # bước synthesizing gọi segment_synthesizer thay vì 3 nhánh
                              #   provider; + artifacts.voice_timeline, + warnings.
                              #   tts_segments_failed, + tts_failed_segments; lỗi TTS cục
                              #   bộ không còn fail_job()
  web/
    backend/
      jobs_api.py             # + tts_failed_segments vào response GET /api/jobs/{id}
                              #   (warnings tự pass-through, không cần sửa)
    frontend/
      src/api/client.ts        # + tts_failed_segments, + warnings.tts_segments_failed
      src/pages/JobDetailPage.tsx  # + nhãn cảnh báo mới (kèm số câu lỗi)
```

**Structure Decision**: Web application — giữ nguyên cấu trúc `web/backend/` +
`web/frontend/` của 002 kết hợp CLI pipeline của 001, đúng "Option 2" của
template. Logic mới tập trung vào **một** module `tts/segment_synthesizer.py`
thay vì rải vào 3 client provider, vì cả 3 provider dùng chung đúng một cơ chế
khớp nhịp (research.md §3 — `atempo` hậu xử lý); mỗi client chỉ còn vai trò
adapter "text → WAV" (chữ ký chung `synthesize_text(text, voice_id,
output_path)`, vốn đã tồn tại cho tính năng nghe thử của 004). Đây cũng là
điều kiện để đạt SC-004 (hành vi nhất quán giữa 3 provider) mà không phải
kiểm 3 lần cùng một logic.

**Thứ tự triển khai gợi ý cho `/speckit-tasks`** (bám priority của spec):
US1 (gom unit + script theo segment cho `translate` + segment_synthesizer +
ghép timeline) → FR-011 (captions từ timeline, gỡ cơ chế edge-tts cũ) → US2
(`SEGMENT_REWRITE_SYSTEM` cho `rewrite`) → US3 (chịu lỗi cục bộ + cảnh báo mới
xuyên backend/frontend). US1 xong là đã dùng được ở chế độ mặc định.

## Complexity Tracking

Không có vi phạm Constitution Check nào cần biện minh — bảng để trống.

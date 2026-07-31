<!--
Sync Impact Report
- Version change: 1.9.0 → 1.10.0
- Modified principles: VI. Agentic Harness Discipline — thêm quy tắc: code xử
  lý media MUST chỉ dựa vào bộ lọc LÕI của ffmpeg, cấm phụ thuộc
  `subtitles`/`ass` (cần libass) và `drawtext` (cần libfreetype)
- Added sections: Technology Stack — thêm dòng "Vẽ phụ đề (burn-in)" (Pillow +
  ffmpeg `overlay`), thay cho việc burn bằng bộ lọc `subtitles`/libass
- Removed sections: none
- Follow-up TODOs: none

Sync Impact Report (1.8.0 → 1.9.0, giữ lại để tra cứu)
- Modified principles: none
- Modified sections: Technology Stack — dòng "Phát hiện vùng phụ đề gốc
  (hardsub)" đổi từ Tesseract OCR qua `pytesseract` sang NGƯỜI DÙNG TỰ KHOANH
  VÙNG bằng tay trên web UI (feature 009-hardsub-blur-reposition). Xác nhận
  thật: Tesseract không đọc được phần lớn kiểu chữ có viền/màu nổi bật phổ
  biến trên TikTok/YouTube Shorts sau khi video đã mã hoá — không phải bug có
  thể sửa bằng cách chỉnh tham số, OCR không khả thi cho use-case này.
  `pytesseract` bị loại khỏi dependency; `Pillow` vẫn giữ (đọc kích thước
  khung hình đại diện). Project Structure — cập nhật ghi chú thư mục `hardsub/`
- Removed sections: none
- Follow-up TODOs: hardsub_blur_enabled nay BẮT BUỘC kèm supervised=true (vùng
  cần mờ chỉ khoanh được tại chốt lời thoại) — đã enforce ở
  `pipeline.create_job()`, không cần theo dõi thêm

Sync Impact Report (1.7.0 → 1.8.0, giữ lại để tra cứu)
- Modified principles: VI. Agentic Harness Discipline — thêm 1 quy tắc: unit
  test MUST mock binary ngoài (OCR/ffmpeg) để pytest không phụ thuộc môi trường
  máy đang chạy test
- Added sections: Technology Stack — thêm dòng "Phát hiện vùng phụ đề gốc
  (hardsub)" (Tesseract OCR qua pytesseract + Pillow) cho feature
  009-hardsub-blur-reposition; Project Structure — thêm thư mục `hardsub/`
- Removed sections: none
- Templates requiring updates: ✅ không template nào cần đổi (thêm 1 công
  nghệ, không đổi cấu trúc plan/spec/tasks template)
- Follow-up TODOs: none

Sync Impact Report (1.6.0 → 1.7.0, giữ lại để tra cứu)
- Modified principles: VI. Agentic Harness Discipline — thêm 1 quy tắc kỷ
  luật cho dịch vụ đăng bài trả phí (Zernio): mọi lượt gọi thật MUST hỏi
  người dùng trước; test tự động MUST mock HTTP
- Added sections: Technology Stack — thêm dòng "Đăng bài lên nền tảng"
  (Zernio) cho feature 006-publish-video-tab
-->

# Media Generation Pipeline Constitution

## Core Principles

### I. Python-Only Stack (Backend & Pipeline)
Toàn bộ pipeline xử lý media (download, ASR, script gen, TTS, merge) VÀ mọi
backend/API MUST được viết bằng Python. Không dùng Node.js hay ngôn ngữ khác cho
runtime logic ở tầng backend/pipeline. Rationale: các model AI cốt lõi (ASR, TTS,
video inpainting) đều native Python/PyTorch; một stack duy nhất giảm chi phí bảo
trì và tránh phải viết sidecar/bridge giữa 2 runtime.

Ngoại lệ tường minh: frontend web UI — chạy trong trình duyệt người dùng, không
phải runtime của pipeline — được phép dùng ReactJS (xem Technology Stack).
Node.js/npm ở tầng này chỉ là build-time tooling để biên dịch React thành static
JS/HTML/CSS, không phải runtime xử lý media/pipeline, nên không vi phạm tinh
thần nguyên tắc này. Backend phục vụ frontend (API, orchestration) vẫn MUST là
Python.

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

### VI. Agentic Harness Discipline (NON-NEGOTIABLE)
Dự án này được build hoàn toàn qua AI agent (Claude Code lên plan, Antigravity thực
thi code) — quy trình vận hành 2 agent này MUST tuân theo kỷ luật kỹ thuật nghiêm
ngặt, không "vibe coding":
- Mọi task trong tasks.md MUST đủ nhỏ để một agent hoàn thành và verify độc lập
  trong một lượt; không gộp nhiều thay đổi lớn không kiểm soát được vào một task.
- Agent thực thi code (Antigravity) MUST bám theo đúng spec.md/plan.md/tasks.md đã
  chốt; nếu phát sinh nhu cầu đổi phạm vi/kiến trúc, MUST quay lại amend spec/plan
  trước, không tự ý lệch khỏi artifact đã duyệt.
- Một task chỉ được đánh dấu hoàn thành sau khi verify được bằng bằng chứng cụ thể
  (chạy thử thành công, log/output kiểm tra được, hoặc test pass) — không chấp
  nhận "trông có vẻ đúng".
- Trạng thái mỗi job/run pipeline MUST truy vết được qua file trung gian (xem
  Project Structure) để agent hoặc người ở bước sau audit lại được quyết định của
  bước trước.
- Khi verify/test tính năng liên quan giọng đọc (TTS) qua nhiều provider,
  agent MẶC ĐỊNH chỉ dùng **edge-tts** (miễn phí, không giới hạn) cho các
  lượt test/thử nghiệm lặp lại. KHÔNG tự ý gọi thật LucyAI/Vivibe (tốn credit
  trả phí thật của người dùng) hoặc 9router TTS (dùng chung quota giới hạn
  theo phút, đã ghi nhận lỗi "exceeded your current quota" nhiều lần) trừ khi
  cần xác nhận riêng hành vi đặc thù của đúng provider đó. Với LucyAI/Vivibe,
  agent MUST hỏi xin phép người dùng trước mỗi lượt gọi thật (kể cả nghe thử
  hay chạy job đầy đủ) vì mỗi lượt tốn credit thật, không giả định được đồng
  ý từ 1 lần cho phép trước đó.
- Test tự động MUST KHÔNG phụ thuộc việc một binary ngoài có được cài trên máy
  đang chạy test hay không. Cụ thể: mọi unit test gọi `ffmpeg`/`ffprobe` MUST
  mock lớp đó, để `pytest` xanh trên máy có bản ffmpeg thiếu bộ lọc. Lý do: đã xảy ra
  thật — ffmpeg cài qua Homebrew trên máy dev không có libass nên bộ lọc
  `subtitles` không tồn tại; nếu test phụ thuộc binary thật thì kết quả test
  phản ánh môi trường máy chứ không phản ánh code. Verify end-to-end bằng
  binary thật vẫn bắt buộc, nhưng là bước RIÊNG (quickstart.md), không nằm
  trong unit test.
- Code xử lý media MUST chỉ dựa vào các bộ lọc LÕI của ffmpeg (luôn có ở mọi
  bản build). KHÔNG được dựa vào bộ lọc chỉ tồn tại khi ffmpeg build kèm thư
  viện tuỳ chọn — cụ thể `subtitles`/`ass` (cần `libass`) và `drawtext` (cần
  `libfreetype`). Bài học thật: cả tính năng burn phụ đề fail 100% trên máy dev
  dù code đúng, vì formula `ffmpeg` của Homebrew không còn build libass; suốt
  thời gian đó chỉ job chạy trong Docker mới burn được, khiến lỗi rất khó
  truy. Việc vẽ chữ nay do Pillow đảm nhiệm (`merge/text_renderer.py`) rồi
  `overlay` vào video — `overlay` là bộ lọc lõi.
- Với dịch vụ đăng bài Zernio (xem Technology Stack), agent MUST hỏi xin phép
  người dùng trước MỖI lượt gọi thật (liên kết kênh, tạo bài đăng) — vừa tốn
  chi phí thật, vừa tạo bài đăng CÔNG KHAI thật trên kênh của người dùng mà
  hệ thống này không xoá/sửa lại được. Mọi test tự động MUST mock lớp HTTP,
  KHÔNG test nào được gọi thật tới Zernio.

Rationale: khi hai agent khác nhau chia nhau việc lên plan và viết code, thiếu kỷ
luật harness sẽ dẫn tới lệch phạm vi, task không verify được, và mất khả năng audit
— đây là vấn đề cốt lõi mà kỷ luật "agentic engineering" giải quyết bằng quy trình
rõ ràng thay vì tin tưởng agent tự giác.

## Technology Stack (Locked Decisions)

| Bước | Công nghệ | Ghi chú |
|---|---|---|
| Download | f2 (chính), yt-dlp (fallback) | Ưu tiên Douyin/TikTok, watermark-free từ nguồn |
| Cleanup watermark/hardsub | video-subtitle-remover | On-demand, xem Principle III |
| Phát hiện vùng phụ đề gốc (hardsub) | Người dùng tự khoanh vùng trên web UI + `Pillow` | KHÁC hoàn toàn với dòng "Cleanup watermark/hardsub" ở trên: đây KHÔNG phải AI inpainting và KHÔNG thuộc phạm vi Principle III. Trước đây dùng Tesseract OCR (`pytesseract`) để TỰ ĐỘNG dò toạ độ — xác nhận thật KHÔNG khả thi: Tesseract không đọc được phần lớn kiểu chữ có viền/màu nổi bật phổ biến trên TikTok/YouTube Shorts sau khi mã hoá. Thay vào đó: trích 1 khung hình đại diện (ffmpeg), người dùng tự khoanh vùng bằng mắt tại chốt lời thoại (BẮT BUỘC kèm `supervised=true`), rồi ffmpeg `boxblur` đúng vùng đó + chèn phụ đề mới đè lên (feature 009-hardsub-blur-reposition). `Pillow` chỉ để đọc kích thước khung hình |
| ASR | faster-whisper | Dùng khi cần transcript/timestamp để dịch |
| Script gen (dịch/viết lại) | LLM qua 9router | OpenAI-compatible, SDK `openai`. Endpoint/key/model đọc từ `.env`: `ROUTER_BASE_URL` (đã gồm `/v1`), `ROUTER_API_KEY`, `ROUTER_MODEL` — xem `.env.example` |
| TTS | edge-tts (mặc định) + LucyAI/Vivibe + 9router TTS (tuỳ chọn) | edge-tts: free, không cần GPU, không cần API key — vẫn là provider mặc định/fallback khi chưa cấu hình provider khác. LucyAI/Vivibe (`https://api.lucylab.io/json-rpc`, JSON-RPC qua 3 method `getUserVoices`/`ttsLongText`/`getExportStatus`, polling trạng thái, audio trả về WAV): cần `VIVIBE_API_KEY` riêng của người dùng. 9router TTS (`{ROUTER_BASE_URL}/audio/speech`, OpenAI-compatible, model dạng `gemini/gemini-3.1-flash-tts-preview/{voice}`, 30 giọng Gemini cố định — không có endpoint discovery): tái dùng `ROUTER_BASE_URL`/`ROUTER_API_KEY` đã có, không cần secret riêng; tham số `speed` API không đáng tin cậy (đã verify thật), khớp thời lượng bằng hậu xử lý ffmpeg `atempo` thay vì tham số API. Người dùng chọn provider + giọng đọc và nghe thử trên giao diện web trước khi chạy job. VietTTS (voice cloning) vẫn là hướng nâng cấp sau, không bắt buộc |
| Tách nhạc nền | Demucs (two-stems: vocals/no_vocals) | Tách audio gốc để giữ nhạc nền, bỏ giọng nói gốc, trộn với voice mới ở bước merge. Chạy CPU, chấp nhận tốn thêm thời gian xử lý (xem SC-002 đã nới trong spec); lỗi tách KHÔNG được chặn pipeline — fallback về mute toàn bộ audio gốc như hành vi cũ nếu Demucs lỗi |
| Ghép video | ffmpeg | Qua subprocess hoặc ffmpeg-python. CHỈ dùng bộ lọc lõi — xem Principle VI về việc cấm phụ thuộc `subtitles`/`drawtext` |
| Vẽ phụ đề (burn-in) | `Pillow` + ffmpeg `overlay` | Chữ được vẽ sẵn thành ảnh PNG nền trong suốt bằng Pillow (`merge/text_renderer.py`), rồi `overlay` vào video theo đúng khoảng thời gian từng dòng. KHÔNG dùng bộ lọc `subtitles`/libass của ffmpeg: bộ lọc đó vắng mặt ở nhiều bản build phổ biến (formula `ffmpeg` của Homebrew hiện không build libass), từng khiến toàn bộ việc burn fail trên máy dev dù code đúng. Cần 1 font có dấu tiếng Việt trên hệ thống (macOS có sẵn; Linux: `fonts-dejavu-core`), ghi đè được qua `SUBTITLE_FONT_PATH`. Đổi lại còn kiểm soát được vị trí/cỡ chữ từng dòng theo pixel — đúng thứ feature 009 cần |
| Web UI Backend | FastAPI (Python) | Expose API cho React frontend: submit job, poll trạng thái/% tiến trình, danh sách job, resume job lỗi (feature 002-web-ui). Gọi lại các module pipeline hiện có, không viết lại logic xử lý media |
| Web UI Frontend | ReactJS | Chạy trong browser, gọi Web UI Backend qua HTTP. Node.js/npm chỉ là build-time tooling (xem Principle I), không phải runtime pipeline |
| Đăng bài lên nền tảng | Zernio (`https://zernio.com/api/v1`) | Dịch vụ trung gian đã được TikTok/YouTube cấp phép đăng bài tự động — dùng cho CẢ luồng OAuth liên kết kênh LẪN đăng video công khai ngay (feature 006-publish-video-tab). Hệ thống này KHÔNG tự xin audit riêng với từng nền tảng và KHÔNG dùng browser automation/giả lập thao tác tay (FR-012). Gọi qua REST bằng `httpx`, xác thực `Authorization: Bearer $ZERNIO_API_KEY` — key riêng của người dùng, đọc từ `.env` (xem `.env.example`). Thiếu key: chỉ tab "Đăng video" báo chưa cấu hình, pipeline xử lý media KHÔNG bị ảnh hưởng. Kỷ luật gọi thật/mock: xem Principle VI |

Thay đổi bất kỳ dòng nào trong bảng này MUST đi qua amend constitution (Governance),
không được đổi ngầm trong plan.md của từng feature.

## Project Structure

```text
media-generation/
  downloader/       # f2 (douyin/tiktok) + yt-dlp (fallback)
  clean_video/       # video-subtitle-remover, gọi on-demand
  hardsub/           # vùng phụ đề gốc do người dùng tự khoanh — KHÔNG phải AI inpainting
  asr/               # faster-whisper
  script_gen/        # gọi 9router
  tts/               # edge-tts (mặc định) + LucyAI/Vivibe + 9router TTS (tuỳ chọn)
  merge/             # ffmpeg + Demucs (tách/giữ nhạc nền)
  pipeline.py        # điều phối tuần tự, lưu state theo job
  jobs/{job_id}/      # file trung gian: source.mp4, transcript.json, script.json, voice.wav, background.wav, output.mp4
                     #   + publishes/{attempt_id}.json (lượt đăng, feature 006)
  publish/            # adapter Zernio + runner đăng bài nền (feature 006)
  web/
    backend/          # FastAPI, gọi lại pipeline.py/module hiện có qua import
    frontend/          # ReactJS SPA (feature 002-web-ui)
```

## Governance

Constitution này supersedes mọi quyết định kỹ thuật ad-hoc trong spec/plan. Thay đổi
công nghệ đã "chốt" (bảng Technology Stack) MUST đi qua amend constitution trước,
không sửa trực tiếp trong plan.md của từng feature. Mọi spec/plan/tasks MUST được
review đối chiếu 6 Core Principles ở trên trước khi implement (Constitution Check
gate trong plan-template.md), bao gồm cả việc Antigravity tuân thủ Principle VI khi
thực thi tasks.md.

Versioning theo semver: MAJOR khi đổi framework nền tảng (vd đổi ngôn ngữ khỏi
Python); MINOR khi thêm/đổi 1 công nghệ trong bảng Technology Stack hoặc thêm
principle mới; PATCH khi chỉnh sửa câu chữ/làm rõ nghĩa không đổi quy tắc.

**Version**: 1.10.0 | **Ratified**: 2026-07-25 | **Last Amended**: 2026-07-30

# Research: Tạo video từ chủ đề bằng AI

## 1. Kiến trúc pipeline: orchestrator riêng vs mở rộng `pipeline.py`

**Decision**: Tạo `generate_pipeline.py` — orchestrator độc lập, state machine
riêng, dùng chung `jobs/{job_id}/job.json` với field discriminator `job_type`
("dub" | "generate", vắng mặt = "dub" để tương thích ngược với job cũ).

**Rationale**: `pipeline.py::run_pipeline()` bắt đầu bằng
`detect_platform(url)` — bắt buộc có URL. `status_from_artifacts()` và
`RERUN_STEPS` suy luận thứ tự bước (`downloading → transcribing → scripting →
synthesizing → merging`) hoàn toàn theo artifact của luồng dub
(`source_video`/`transcript`/`script`/`voice_track`/`output_video`). Luồng
"generate" không có download/ASR, có thêm outline/scene — ép vào cùng 1 hàm sẽ
buộc rẽ nhánh `job_type` ở mọi nơi dùng các hàm này (bao gồm cả
`jobs_api.py::retry_job`/`rerun_job_from_step`), vi phạm Token & Context
Economy hơn là 1 orchestrator riêng, gọn, độc lập audit.

**Alternatives considered**:
- Mở rộng `run_pipeline(url=None, topic=...)`: bị loại vì `detect_platform`
  không nhận `None`, và mọi bước sau giả định `job["artifacts"]["source_video"]`
  luôn có — quá nhiều điểm phải patch phòng thủ.
- Dùng lại `script_mode="download"` pattern (chỉ tải, không xử lý) làm khuôn
  mẫu: không phù hợp vì đó vẫn là luồng CÓ URL, không giải quyết vấn đề gốc.

**Điểm dùng chung với luồng dub** (để không nhân đôi logic):
`find_running_job_id()` (coi 2 loại job là 1 hàng đợi), `JOBS_DIR`/layout
`jobs/{job_id}/`, `_generate_job_id()`, `review/gates.py` (mở rộng, không viết
lại), TTS adapter trong `tts/segment_synthesizer.py` (gọi trực tiếp adapter
thay vì hàm `synthesize_segments()` cấp cao — xem mục 6).

## 2. Scene JSON — schema và lý do

**Decision**: LLM (9router) KHÔNG viết HTML trực tiếp — chỉ trả về Scene JSON
có cấu trúc chuẩn:

```json
{
  "outline": {"sections": [{"title": "...", "key_points": ["...", "..."]}]},
  "scenes": [
    {"index": 0, "narration_text": "...", "image_query": "vietnamese dong banknotes"}
  ]
}
```

`duration` KHÔNG do LLM quyết định — tính SAU khi TTS đã tạo audio thật cho
từng scene (xem mục 6), vì ước lượng ký tự/giây luôn sai lệch so với audio
thật (bài học đã ghi nhận ở `script_gen/router_client.py` cho luồng dub —
`_CHARS_PER_SECOND_ESTIMATE` chỉ dùng để ước lượng ngân sách ký tự khi VIẾT,
không dùng làm timing thật).

**Rationale**: Để LLM tự sinh HTML/CSS (`data-*` timing, animation) rủi ro cao
— dễ sai cú pháp, khó validate, khó tái sử dụng layout. Scene JSON là hợp đồng
rõ ràng giữa "nội dung" (LLM quyết định) và "trình bày" (code Python quyết
định qua template cố định) — đúng tinh thần tách biệt đã dùng cho
`hardsub_regions.json`/`captions.json` ở các feature trước.

**Alternatives considered**: LLM sinh HTML trực tiếp — loại vì rủi ro cú pháp
và không kiểm soát được layout nhất quán giữa các video.

## 3. Web search — dùng model agent có sẵn trong 9router

**Decision**: `topic_script_generator.py` gọi 9router với model có khả năng
tool-use/browsing (đã xác nhận có sẵn — `/speckit-clarify` phiên
2026-07-31), dùng 1 lượt gọi (system/user prompt yêu cầu model tự tra cứu khi
cần) TRƯỚC khi sinh outline chi tiết. Không tích hợp search API/key bên thứ ba
riêng.

**Rationale**: Đã xác nhận trực tiếp bởi người dùng — 9router có model agent
hỗ trợ việc này, tái dùng được ngay hạ tầng/`.env` hiện có
(`ROUTER_BASE_URL`/`ROUTER_API_KEY`), không tăng Technology Stack, không thêm
chi phí vận hành 1 dịch vụ search riêng.

**Alternatives considered**: Tích hợp Tavily/SerpAPI/Google CSE riêng (đã cân
nhắc lúc brainstorm) — loại bỏ vì không cần thiết khi 9router đã có khả năng
này; giữ như phương án dự phòng nếu sau này phát hiện model agent hiện tại
không đủ tốt.

**Cần xác nhận khi implement** (không chặn plan, nhưng MUST verify sớm ở
`/speckit-tasks`/spike đầu tiên): chọn model 9router cụ thể nào có tool-use
(model hiện tại của `ROUTER_MODEL`/`.env` là `gpt-4o-mini`, KHÔNG chắc có
tool-use bật sẵn) — cần agent model riêng cho bước này, tương tự cách
`ROUTER_MODEL` có thể khác cho từng mục đích. Đề xuất thêm biến env mới
`ROUTER_AGENT_MODEL` (fallback về `ROUTER_MODEL` nếu trống) thay vì hardcode.

## 4. Nguồn hình ảnh minh hoạ: Pexels

**Decision**: Pexels Photos API (`https://api.pexels.com/v1/search`) làm nguồn
chính cho v1 — mỗi scene search bằng `image_query` do LLM sinh, lấy ảnh xếp
hạng đầu tiên phù hợp tỉ lệ dọc. Cần `PEXELS_API_KEY` mới trong `.env`.

**Rationale**: Free tier hào phóng (200 request/giờ, 20.000/tháng — đủ cho quy
mô 1 video/lần), có cả Photos VÀ Videos API dùng chung 1 key/1 SDK pattern
(mở đường cho hybrid ảnh+clip ở version sau mà không phải tích hợp thêm nhà
cung cấp), chất lượng/độ liên quan tìm kiếm tốt hơn Pixabay ở thử nghiệm không
chính thức trong lúc brainstorm.

**Alternatives considered**: Pixabay (API tương tự, free, nhưng chất lượng
search kém hơn theo brainstorm ban đầu) — giữ làm fallback tiềm năng ở version
sau nếu Pexels không đủ đa dạng cho 1 số chủ đề hẹp. AI-generate ảnh
(DALL-E/Stable Diffusion/Flux) — loại khỏi v1 theo Assumptions của spec (tốn
chi phí/thời gian hơn nhiều, để version sau).

**Fallback khi không có kết quả phù hợp (FR-010)**: dùng ảnh generic theo chủ
đề rộng hơn (bỏ bớt từ khoá cụ thể trong `image_query`, thử lại 1 lần với từ
khoá rút gọn); nếu vẫn không có kết quả, dùng 1 ảnh nền trung tính có sẵn
trong repo (asset tĩnh, không phải gọi API) làm phương án cuối cùng — không
để scene nào thiếu ảnh hoàn toàn.

## 5. HyperFrames — cách gọi và rủi ro cần spike

**Decision**: `merge/hyperframes_renderer.py::render_scenes_to_video()` sinh 1
file `render.html` bằng Python string template (KHÔNG dùng Jinja2 mới — repo
chưa có dependency này; string template + escape thủ công đủ dùng cho 1 layout
cố định), rồi gọi `subprocess.run(["npx", "hyperframes", "render", ...],
cwd=<thư mục project HyperFrames trong job_dir>)`.

**Rationale**: Theo README HyperFrames (`github.com/heygen-com/hyperframes`),
quy trình chuẩn là `npx hyperframes init` tạo 1 "project" (thư mục có cấu trúc
riêng) rồi `npx hyperframes render` bên trong đó — KHÔNG phải chỉ trỏ tới 1
file HTML rời. Plan này giả định mỗi job "generate" có 1 thư mục project
HyperFrames tối thiểu (được khởi tạo 1 lần từ template cố định lúc build,
COPY vào `job_dir/hyperframes_project/` mỗi job, chỉ thay nội dung
`render.html`/media links).

⚠️ **RỦI RO — CẦN SPIKE TRƯỚC KHI VIẾT TASK CHI TIẾT**: Tài liệu README (qua
WebFetch) mô tả ở mức tổng quan; CHƯA có xác nhận thật cú pháp chính xác của
`data-*` attribute (timing/track), cấu trúc thư mục project tối thiểu, hay
`npx hyperframes render` nhận tham số gì (output path? cấu hình audio riêng
hay audio nhúng trong HTML `<audio>` tag?). Task đầu tiên trong tasks.md
**MUST** là 1 spike thủ công: `npx hyperframes init test-video && cd
test-video && npx hyperframes preview` để xác nhận cấu trúc thật, TRƯỚC khi
viết `hyperframes_renderer.py`. Không suy đoán thêm chi tiết cú pháp trong plan
này để tránh tài liệu hoá sai.

**Alternatives considered**: Dùng `merge/ffmpeg_merge.py`-style slideshow
thuần ffmpeg (`zoompan`/`xfade`) — đã cân nhắc ở brainstorm, bị loại vì người
dùng chốt rõ muốn dùng đúng HyperFrames (Clarification session 2026-07-31, Q1).

## 6. TTS theo từng scene

**Decision**: Gọi trực tiếp adapter provider có sẵn trong
`tts/segment_synthesizer.py` (hàm nội bộ `_get_adapter(provider, voice_id)` →
`Callable[[str, Path], None]`) cho từng `narration_text` của scene, ghi ra
`jobs/{job_id}/scenes/{i}/voice.wav`, rồi đo thời lượng thật bằng
`media_utils.get_media_duration()` — đây MỚI là `duration` thật của scene
(không dùng ước lượng ký tự/giây).

**Rationale**: `synthesize_segments()` (hàm cấp cao hiện có) được thiết kế
riêng cho khái niệm "dubbing unit" khớp timeline ASR gốc (`_fit_unit_to_window`,
`apad`, resume theo `voice_timeline.json`) — không khớp nhu cầu ở đây (mỗi
scene độc lập, không cần khớp cửa sổ thời gian có sẵn). Gọi thẳng adapter là
tái dùng đúng phần logic dùng chung (kết nối provider), không kéo theo phần
logic không liên quan.

**Alternatives considered**: Viết lại toàn bộ logic gọi TTS riêng cho feature
này — loại vì trùng lặp không cần thiết với adapter đã có.

## 7. Chốt duyệt outline/scene — mở rộng `review/gates.py`

**Decision**: Thêm `GATE_OUTLINE = "outline"` vào `GATES`, map
`NEXT_STATUS_AFTER_GATE["outline"] = "sourcing_assets"`,
`EDITABLE_FIELD["outline"] = "narration_text"`. `gate_file_path()` thêm nhánh
đọc `job["artifacts"]["scenes"]` (trỏ `scenes.json`). Toàn bộ
`build_payload()`/`save_edits()`/`mark_reached()`/`mark_approved()` dùng lại
NGUYÊN VẸN — các hàm này đã tổng quát hoá theo `data["segments"]` (list of
dict có field editable), và Scene JSON đã thiết kế để `scenes` đóng vai trò
`segments` (mục 2).

**Rationale**: Đúng tinh thần Token & Context Economy — không viết review-gate
riêng khi cơ chế chung đã đủ tổng quát; `image_query`/`index` không editable ở
v1 (chỉ `narration_text`), giữ đơn giản như 2 gate hiện có (mỗi gate chỉ có 1
field editable).

**Alternatives considered**: Module review riêng cho generate pipeline — loại
vì trùng lặp logic file JSON + editable-field không cần thiết.

## 8. Docker/Node runtime

**Decision**: `Dockerfile` cài thêm Node.js 22+ (qua `nodesource` setup script
hoặc image đa giai đoạn `FROM node:22-slim AS node-stage` rồi copy binary) +
dependency hệ thống cho Chrome headless (`libnss3`, `libatk-bridge2.0-0`,
`libgtk-3-0`, ... — danh sách chuẩn cho Puppeteer/Playwright trên Debian).

**Rationale**: Hệ quả bắt buộc của quyết định dùng HyperFrames (đã amend
Constitution). Máy dev hiện tại (macOS, Node 22.19.0 có sẵn) không đại diện
cho môi trường Docker chạy thật — MUST verify riêng trên image Docker thật
trước khi coi feature hoàn thành, đúng bài học đã có với libass (constitution
Principle VI, bài học burn phụ đề fail trên Homebrew ffmpeg).

## 5b. Kết quả spike HyperFrames (T002, xác nhận thật 2026-08-01)

Đã chạy thật trên máy dev (Node v22.19.0, `npx hyperframes` resolve bản
`0.7.87`): `init` project blank portrait → viết `index.html` 2-scene thủ công
→ `lint` → `render` → `ffprobe` xác nhận output. Ghi lại đúng những gì đã xác
nhận, KHÔNG suy đoán thêm:

**`init` (chỉ chạy 1 LẦN lúc build template, KHÔNG chạy mỗi job — xem lý do
bên dưới)**:

```bash
HYPERFRAMES_SKIP_SKILLS=1 npx hyperframes init <dir> \
  --example blank --resolution portrait --non-interactive
```

- `--non-interactive` bắt buộc phải kèm `--example` (dùng `blank` cho project
  trống) — không truyền sẽ lỗi ngay `Non-interactive init requires --example`.
- `--resolution portrait` → canvas 1080×1920, khớp yêu cầu 9:16 của spec.
- ⚠️ **Side-effect quan trọng**: dù có `--non-interactive`, `init` mặc định
  vẫn gọi ra GitHub để cài "AI skills" (ghi vào `~/.claude/skills/`,
  `~/.agents/skills/` — THƯ MỤC HOME, không phải project). Đây là side-effect
  không mong muốn cho môi trường server/Docker (network call + ghi ngoài
  phạm vi job). Bắt buộc set `HYPERFRAMES_SKIP_SKILLS=1` để tắt (flag
  `--skip-skills` hiện bị ignore theo help text của bản 0.7.87).
- **Hệ quả cho design**: `init` chỉ nên chạy 1 LẦN lúc build Docker image (hoặc
  đã commit sẵn 1 thư mục template tối thiểu vào repo) để tạo
  `hyperframes_project_template/` — KHÔNG chạy `init` mỗi job. Mỗi job
  "generate" thật chỉ COPY thư mục template này vào
  `job_dir/hyperframes_project/`, ghi `index.html` riêng (sinh từ scene JSON)
  + copy ảnh/audio scene vào, rồi gọi thẳng `render` — đúng giả định ban đầu
  của research.md §5, giờ đã xác nhận là cách BẮT BUỘC (không chỉ là lựa chọn
  tối ưu) để tránh gọi mạng/ghi home dir mỗi job.

**Cấu trúc project tối thiểu sau `init` (đã xác nhận thật)**:

```text
<project>/
├── index.html        # LÀ chính file composition — không có thư mục con nào khác chứa nó
├── package.json       # scripts: dev/check/render/publish đều gọi
│                       #   `npx --yes hyperframes@<pinned-version> <cmd>` — version
│                       #   bị PIN cứng vào version lúc init, không phải "latest"
├── hyperframes.json    # config registry/paths (blocks/components/assets) — không cần sửa cho v1
└── meta.json           # {id, name, createdAt}
```

Không có thư mục `assets/` mặc định — tự tạo và trỏ `src` tương đối từ đó
(đã test `assets/scenes/{i}/image.jpg`, `assets/scenes/{i}/voice.wav`, hoạt
động bình thường, `render` đọc file tương đối đúng cwd project).

**Cú pháp `index.html` đã xác nhận chạy được thật** (khác 1 vài điểm so với
suy đoán ban đầu ở §5):

- Root: `<div id="root" data-composition-id="main" data-start="0" data-duration="<TỔNG GIÂY>" data-width="1080" data-height="1920">` — `data-duration` ở ROOT phải là tổng thời lượng cả video (không tự suy ra được nếu không có GSAP timeline có tween thật — bài test dùng timeline rỗng nên BẮT BUỘC khai `data-duration` ở root).
- Ảnh/caption mỗi scene là `<img class="clip ...">`/`<div class="clip ...">`
  — **bắt buộc** `class="clip"` (thiếu là phần tử hiện xuyên suốt video, bỏ
  qua `data-start`/`data-duration`), và bắt buộc `data-start`/`data-duration`/
  `data-track-index`. Ảnh/caption cùng 1 scene dùng CHUNG `data-start`/
  `data-duration` (khớp giọng đọc), khác `data-track-index` (ảnh track 1,
  caption track 2) vì cùng track không được chồng thời gian.
- Giọng đọc: `<audio src="..." data-start="..." data-duration="..." data-track-index="10">` (không cần `class="clip"` — audio không có phần hiển thị). Mỗi scene 1 thẻ audio riêng, `data-start` = thời điểm bắt đầu scene đó trong timeline TỔNG (không phải 0 cho mỗi scene).
- Vẫn cần đăng ký `window.__timelines["main"] = gsap.timeline({paused:true})`
  dù không có tween nào (composition tĩnh, không animation) — thiếu dòng này
  render vẫn chạy được nhưng KHÔNG nên bỏ, đúng "One paused timeline" contract
  bắt buộc của runtime.
- `npx hyperframes lint` (chạy trước `render`, rất nhanh ~vài giây) bắt được
  lỗi cấu trúc sớm — nên gọi trong `render_scenes_to_video()` trước khi
  subprocess `render` thật, coi lint fail = raise `RuntimeError` sớm thay vì
  để render (chậm hơn nhiều) mới báo lỗi.

**Lệnh `render` đã xác nhận thật**:

```bash
npx hyperframes render --quality standard --output output.mp4 --quiet
```

- Chạy trong cwd = thư mục project (hoặc truyền `dir` positional). Mặc định
  KHÔNG truyền `--output` sẽ ra `renders/<project>_<timestamp>.mp4` (có
  timestamp, không đoán trước được tên) — **BẮT BUỘC luôn truyền `--output`**
  tường minh (`job_dir/output.mp4`) để code Python biết chắc đường dẫn kết
  quả, không phải scan thư mục `renders/`.
- KHÔNG dùng `--docker` (chỉ dành cho máy dev muốn render "byte-identical" qua
  container riêng của HyperFrames — pipeline của ta ĐÃ chạy trong container
  riêng rồi, dùng `--docker` sẽ là Docker-trong-Docker không cần thiết).
- `--strict` (fail render nếu có lint warning) — NÊN bật để job fail sớm rõ
  ràng thay vì render ra video sai mà không biết, khớp tinh thần Constitution
  VI (agent phải có bằng chứng cụ thể, không "trông có vẻ đúng").
- Test thật: render 2 scene (3.2s + 2.6s) ra đúng file MP4 `duration=5.800000`
  (ffprobe xác nhận, khớp CHÍNH XÁC `data-duration` root), có ĐỦ 2 stream
  `video: h264` + `audio: aac` — audio từ NHIỀU thẻ `<audio>` khác nhau ở các
  thời điểm khác nhau được HyperFrames tự mix/ghép đúng vào 1 track audio duy
  nhất của MP4 cuối, KHÔNG cần bước ghép audio riêng bằng ffmpeg (khác hẳn
  `merge/ffmpeg_merge.py` của luồng dub phải tự ghép audio track).
- Không raise lỗi nào trong bài test — case lỗi (subprocess trả exit code
  khác 0) chưa test thật ở spike này; `render_scenes_to_video()` (T027) vẫn
  PHẢI check `subprocess.run(...).returncode` và raise `RuntimeError` theo
  đúng mẫu `merge/ffmpeg_merge.py` như plan đã định, chỉ là chưa có log lỗi
  thật để trích dẫn nguyên văn.

**Không xác nhận được ở spike này (ngoài phạm vi T002, để lại nguyên trạng)**:
hành vi khi Docker container (không phải macOS dev) chạy `render` — vẫn là
việc của T045 (build Docker thật + verify), không suy đoán trước.

## 5c. Animation (bổ sung sau feedback người dùng trên job thật, 2026-08-01)

Bản render đầu tiên (T027/T029) chỉ đặt ảnh/caption TĨNH theo `data-*` —
không có tween nào, timeline GSAP đăng ký nhưng rỗng. Người dùng chạy thử job
thật (12 scene, "chứng khoán cho người mới") và phản hồi đúng: video ra như
slideshow, "chưa thấy sức mạnh HyperFrames". Đã nâng cấp
`merge/hyperframes_renderer.py::_build_index_html()` (tham khảo
`hyperframes-animation` skill, `adapters/gsap-timeline-and-labels.md`):

- **Ken Burns trên ảnh**: `gsap.fromTo(img, {scale}, {scale, duration: scene.duration, ease:"none"})`
  đặt tại thời điểm TUYỆT ĐỐI `scene.start` trên timeline chung — không phải
  `.from()` (an toàn khi HyperFrames seek lại từ đầu). Luân phiên zoom-in/
  zoom-out theo `idx % 2` (quyết định trước, KHÔNG `Math.random()` — cấm theo
  determinism rules của `hyperframes-core`).
- **Caption rise-fade**: `fromTo(caption, {y:24, opacity:0}, {y:0, opacity:1})`
  lúc scene bắt đầu, fade out trước khi scene kết thúc — cả 2 đều `Math.min(...,
  duration/3)` để không tràn quá thời lượng scene ngắn.
- Chỉ tween `scale`/`y`/`opacity` — đúng allowlist của `hyperframes-core`
  (KHÔNG `width`/`height`/`top`/`left`). CSS `.scene-image`/`.caption` KHÔNG
  đặt `transform` sẵn — tránh lỗi lint `gsap_css_transform_conflict`.

**Verify thật** (không chỉ mock): render 3 scene giả lập với ảnh `testsrc`
(pattern có vạch màu + ô caro để thấy zoom bằng mắt) — trích frame ở đầu và
cuối 1 scene, so sánh trực quan xác nhận ảnh phóng to đúng hướng zoom-in.
`npx hyperframes render --strict` không báo lỗi lint nào cho code animation
này.

## 9. Rủi ro tổng hợp cần theo dõi ở tasks.md

- Spike HyperFrames (mục 5) phải là task ĐẦU TIÊN — mọi task viết
  `hyperframes_renderer.py` phụ thuộc kết quả spike này.
- Model 9router có tool-use thật (mục 3) cần xác nhận bằng 1 lệnh gọi thử,
  không giả định `ROUTER_MODEL` hiện tại đã hỗ trợ.
- Pexels cần amend Constitution TRƯỚC khi bất kỳ task nào gọi API thật (xem
  plan.md Constitution Check).

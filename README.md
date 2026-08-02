# Video Repurpose Pipeline

Pipeline Python CLI tự động hoá quá trình tái tạo video:  
**Tải video → Tách lời → Viết kịch bản tiếng Việt → Sinh giọng đọc → Ghép video**

## Yêu cầu hệ thống

- Python 3.11+
- `ffmpeg` trong PATH (`brew install ffmpeg` trên macOS) — KHÔNG cần build kèm
  `libass`: phụ đề được vẽ bằng Pillow rồi overlay, chỉ dùng các bộ lọc lõi
- 9router (LLM proxy, OpenAI-compatible)
- Một font có dấu tiếng Việt. macOS có sẵn (Arial Unicode); trên Linux cài
  `apt-get install fonts-dejavu-core`. Muốn dùng font khác thì trỏ biến môi
  trường `SUBTITLE_FONT_PATH` tới file `.ttf`.

## Cấu hình (.env)

```bash
cp .env.example .env
# rồi điền ROUTER_BASE_URL / ROUTER_API_KEY / ROUTER_MODEL thật vào .env
```

| Biến | Ý nghĩa |
|---|---|
| `ROUTER_BASE_URL` | Base URL đầy đủ kiểu OpenAI SDK, **đã bao gồm `/v1`** (vd `http://172.16.57.147:20128/v1`) |
| `ROUTER_API_KEY` | API key gọi 9router |
| `ROUTER_MODEL` | Model dùng cho dịch/viết kịch bản (vd `ag/gemini-3-flash-agent`) |
| `ROUTER_TIMEOUT` | Timeout (giây) mỗi lượt gọi 9router, mặc định `120` — hết hạn thì fallback OpenRouter |
| `OPENROUTER_API_KEY` | Key OpenRouter dùng dự phòng khi 9router chết (tuỳ chọn, bỏ trống = tắt fallback) |
| `OPENROUTER_BASE_URL` | Mặc định `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | Model bên OpenRouter, mặc định `google/gemini-2.5-flash` — **khác** `ROUTER_MODEL` |
| `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` | Tài khoản đăng nhập giao diện web (chỉ 1 cặp duy nhất) |
| `WEB_UI_SECRET_KEY` | Secret ký session cookie (7 ngày) — sinh 1 chuỗi ngẫu nhiên dài, không để trống |
| `VIVIBE_API_KEY` | API key TTS Vivibe (tuỳ chọn, provider giọng đọc thứ 2 — không cấu hình vẫn dùng đủ tính năng với edge-tts) |

`.env` đã nằm trong `.gitignore` — không commit key thật. Chạy local, `pipeline.py`
tự load `.env` qua `python-dotenv`; chạy Docker, `docker-compose.yml` đã khai báo
`env_file: .env` nên cũng tự đọc, không cần truyền `-e` thủ công.

### Fallback OpenRouter khi 9router không kết nối được

9router là dịch vụ nội bộ (IP LAN) nên khi chạy ngoài mạng công ty sẽ timeout.
Nếu `.env` có `OPENROUTER_API_KEY`, bước dịch/viết kịch bản tự gọi lại qua
OpenRouter thay vì làm hỏng cả job — cùng giao thức OpenAI-compatible nên phần
còn lại của pipeline không đổi. Log sẽ in rõ lúc chuyển:

```
[router_client] 9router lỗi (APITimeoutError: Request timed out.) → chuyển sang OpenRouter dự phòng (model google/gemini-2.5-flash)
```

Kiểm tra nhanh endpoint nào đang dùng được: `python env_check.py`.

**Giới hạn:** fallback chỉ áp dụng cho LLM (dịch/viết kịch bản). Provider giọng
đọc `--tts-provider router-tts` vẫn cần 9router vì OpenRouter không có endpoint
`/audio/speech` — khi 9router chết, dùng `edge-tts` (mặc định, free) hoặc
`lucyai`. Cả 2 endpoint cùng lỗi thì job dừng với thông báo liệt kê lỗi của
từng endpoint.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy bằng Docker (thay thế cài đặt thủ công)

Không cần cài Python 3.11/ffmpeg trên máy — chỉ cần Docker và file `.env` đã điền.

```bash
docker compose build
docker compose run --rm pipeline --url "<video_url>" --script-mode translate
```

Output được mount ra `./jobs/` trên máy host (xem `docker-compose.yml`) nên xem lại
file trung gian bình thường như chạy local. Nếu `ROUTER_BASE_URL` trong `.env` là
`localhost`, đổi host thành `host.docker.internal` khi chạy trong container (image
đã có sẵn fallback này qua `extra_hosts`, cần Docker ≥20.10 trên Linux).

Không dùng `docker compose` thì build/run thủ công bằng `docker build`/`docker run`:

```bash
docker build -t media-generation-pipeline .
docker run --rm \
  --env-file .env \
  -v "$(pwd)/jobs:/app/jobs" \
  media-generation-pipeline \
  --url "<video_url>" --script-mode translate
```

## Cách dùng

```bash
python pipeline.py \
  --url <video_url> \
  --script-mode <translate|rewrite|subtitle> \
  [--dynamic-captions] \
  [--tts-provider <edge-tts|lucyai|router-tts>] \
  [--voice-id <voice_id>] \
  [--supervised] \
  [--hardsub-blur] \
  [--hardsub-no-ranges <ranges>] \
  [--job-id <existing_job_id>]
```

| Tham số | Bắt buộc | Mô tả |
|---|---|---|
| `--url` | ✅ | URL TikTok, Douyin hoặc YouTube |
| `--script-mode` | ✅ | `translate` (Dịch chuẩn, lồng tiếng), `rewrite` (Sáng tạo, lồng tiếng), hoặc `subtitle` (Phụ đề tự động — giữ nguyên âm thanh gốc, chỉ thêm phụ đề) |
| `--dynamic-captions` | ❌ | Chỉ áp dụng với `translate`/`rewrite`: thêm phụ đề động (chữ kịch bản chạy khớp nhịp giọng đọc, theo từng câu) lên video đã lồng tiếng — chính xác như nhau với cả 3 provider giọng đọc |
| `--tts-provider` | ❌ | `edge-tts` (mặc định, free), `lucyai` (Vivibe, cần `VIVIBE_API_KEY`), hoặc `router-tts` (giọng Gemini qua 9router, tái dùng `ROUTER_API_KEY` có sẵn) — chỉ áp dụng với `translate`/`rewrite` |
| `--voice-id` | ❌ | Giọng đọc cụ thể (VD `vi-VN-HoaiMyNeural` cho edge-tts, id giọng trong tài khoản Vivibe, hoặc tên giọng Gemini VD `Puck` cho router-tts); để trống → dùng giọng mặc định |
| `--supervised` | ❌ | Bật chế độ quản lý pipeline: dừng chờ phê duyệt sau bước tách lời và sau bước sinh kịch bản (xem bên dưới). Bị bỏ qua với `download` |
| `--hardsub-blur` | ❌ | Làm mờ phụ đề gốc có sẵn trên hình + chèn phụ đề mới đúng vị trí (xem bên dưới). Chỉ có tác dụng với chế độ có hiển thị phụ đề (`subtitle`, hoặc `translate`/`rewrite` kèm `--dynamic-captions`) |
| `--hardsub-no-ranges` | ❌ | Khoảng thời gian KHÔNG có phụ đề gốc, cú pháp giống `--keep-original-ranges` (VD `"0:00-0:08, 0:15-end"`). Chỉ có ý nghĩa khi `--hardsub-blur` bật |
| `--job-id` | ❌ | Resume job cũ; để trống → tạo job mới |

Cả `translate` và `rewrite` đều giữ nhạc nền gốc (tách bằng Demucs, trộn với
giọng đọc mới).

### Chế độ quản lý pipeline (feature 008)

Bật `--supervised` (hoặc công tắc **Quản lý pipeline** ở form tạo job trên web)
để job **dừng lại 2 lần** cho bạn review và tinh chỉnh trước khi chạy tiếp:

1. **Chốt lời thoại** — sau bước tách lời. Sửa những câu ASR nghe sai (tên riêng,
   thuật ngữ) trước khi chúng lan xuống bản dịch, giọng đọc và sản phẩm cuối.
2. **Chốt kịch bản** — sau bước sinh kịch bản. Đối chiếu từng câu dịch với câu
   gốc, sửa chỗ chưa mượt, hoặc bấm **Sinh lại kịch bản** để dịch lại từ đầu.

Ở mỗi chốt, job chuyển sang trạng thái **Chờ duyệt** và **không tự chạy tiếp** —
kể cả sau khi restart hệ thống hay để đó nhiều ngày. Review/sửa/phê duyệt thực
hiện **trên web UI** ở trang chi tiết job (CLI không có lệnh phê duyệt).

Mốc thời gian từng câu chỉ để xem; xoá trắng nội dung một câu = bỏ câu đó. Job
đang chờ duyệt **không chiếm suất xử lý**, nên bạn vẫn submit được job mới — đổi
lại, nếu lúc bấm phê duyệt đang có job khác thực sự chạy thì lượt phê duyệt bị
từ chối, chờ job kia xong rồi bấm lại.

Mặc định chế độ này **TẮT** — job không bật vẫn chạy liền mạch như trước.

### Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí (feature 009)

Với video nguồn đã có phụ đề burn sẵn (kiểu caption tự động TikTok/CapCut),
bật `--hardsub-blur` để hệ thống **che mờ** đúng vùng chữ gốc và **chèn phụ
đề mới** (nội dung đã dịch) đè lên đúng vị trí đó, cỡ chữ nhỏ hơn mặc định.
**Bắt buộc kèm `--supervised`**: vị trí vùng cần mờ do bạn tự khoanh bằng tay
trên web UI tại chốt lời thoại (chọn giữa: đã thử OCR tự động nhưng không khả
thi — Tesseract không đọc được phần lớn kiểu chữ có viền/màu nổi bật phổ biến
trên TikTok/YouTube Shorts sau khi video đã mã hoá).

Mặc định coi **toàn bộ video** là có phụ đề gốc. Nếu chỉ một phần video có
phụ đề (VD đoạn mở đầu không có), khai báo các đoạn **không có** bằng
`--hardsub-no-ranges` (cùng cú pháp `--keep-original-ranges`, chỉnh lại được
ngay tại chốt lời thoại) — đúng đoạn đó sẽ không bị mờ, phụ đề mới hiển thị
theo vị trí/cỡ chữ mặc định.

Khi job dừng ở chốt lời thoại, web UI hiện 1 khung hình đại diện của video —
kéo chuột trên khung hình đó để khoanh đúng vùng chữ cần mờ, rồi lưu/phê
duyệt như bình thường.

Lưu ý khi khoanh: hãy khoanh vùng **cao đủ để che cả trường hợp phụ đề gốc
xuống 2 dòng**, không chỉ vừa khít dòng chữ đang thấy trên khung hình mẫu —
nếu không, ở những cảnh phụ đề gốc dài hơn, dòng thứ hai sẽ nằm ngoài vùng mờ
và còn hiện trong video kết quả.

Mặc định **TẮT** — job không bật vẫn chạy y như trước.

### Lồng tiếng khớp nhịp tự nhiên (feature 005)

Giọng đọc được tổng hợp **theo từng nhịp** chứ không phải một khối liên tục:
pipeline gom các đoạn ASR thành "nhịp nói" theo đúng chỗ video gốc ngắt nghỉ,
dịch/viết lại mỗi nhịp một dòng, rồi đặt từng nhịp vào đúng khung thời gian
của nó và chèn **khoảng lặng thật** vào các quãng nghỉ. Mỗi nhịp chỉ được
**tăng tốc nhẹ** khi đọc tràn khung (tối đa 1.25×) — không bao giờ đọc chậm để
lấp cho vừa khít, vì đó chính là nguyên nhân khiến bản lồng tiếng cũ nghe chậm
và liền một mạch.

- Nhịp đọc tràn khung sẽ đẩy lùi nhịp kế tiếp thay vì bị cắt nội dung — bản
  lồng tiếng có thể dài hơn video gốc một chút ở video nhiều câu tràn.
- Một vài nhịp lỗi tổng hợp (timeout, hết quota provider...) **không làm hỏng
  cả job**: đoạn đó thành khoảng lặng, job vẫn hoàn tất kèm cảnh báo rõ số câu
  bị ảnh hưởng. Chỉ khi toàn bộ nhịp đều lỗi job mới báo thất bại.
- Mốc thời gian thực tế của từng nhịp được ghi ra `voice_timeline.json` và
  cũng là nguồn của phụ đề động (`--dynamic-captions`) cho cả 3 provider.
- Nhịp cắt **bám theo clip gốc**: mỗi đoạn ASR giữ nguyên thành một nhịp
  riêng. Chỉ gộp 2 đoạn khi tách ra chắc chắn hỏng nghĩa — đoạn sau là phần
  nối tiếp giữa chừng của một câu chưa kết thúc, hoặc nhịp đang mở quá vụn
  (< 1.2s).

### Ngôn ngữ nguồn của video

Bước nhận dạng giọng nói dùng Whisper — model **đa ngôn ngữ (~99 thứ tiếng)**
và **tự nhận diện** ngôn ngữ của clip, nên video tiếng Trung/Nhật/Hàn/Thái…
chạy được ngay, không cần cấu hình gì thêm. Đầu ra luôn là tiếng Việt.

Ngôn ngữ nhận được ghi vào `transcript.json` (`language` + `language_probability`).
Hai biến trong `.env` để tinh chỉnh khi cần:

| Biến | Khi nào cần |
|---|---|
| `WHISPER_LANGUAGE` | Ghim ngôn ngữ nguồn (`zh`, `ja`, `ko`, `vi`…) thay vì để tự đoán. Việc tự đoán chỉ nghe **30 giây đầu** nên dễ sai khi clip mở đầu bằng nhạc/tiếng ồn hoặc nói xen kẽ 2 thứ tiếng — pipeline in cảnh báo khi độ tin cậy < 60% |
| `WHISPER_MODEL` | Đổi `small` (mặc định) sang `medium`/`large-v3`. `small` đủ tốt cho tiếng Anh nhưng kém rõ rệt với tiếng Trung/Nhật/Hàn; đổi lại chậm hơn nhiều trên CPU |

### Chọn giọng đọc — edge-tts / Vivibe / 9router (feature 004)

Mặc định dùng edge-tts (2 giọng tiếng Việt, miễn phí). 2 provider tuỳ chọn
thêm:

```bash
# Vivibe (thương hiệu; API thực chất là LucyAI, api.lucylab.io) — cần tài
# khoản riêng: tạo tại https://www.vivibe.app, lấy API key, cấu hình sẵn ít
# nhất 1 giọng đọc trong tài khoản, rồi điền VIVIBE_API_KEY vào .env
python pipeline.py --url "..." --script-mode translate --tts-provider lucyai --voice-id "<id giọng trong tài khoản>"

# 9router TTS (giọng Gemini, 30 giọng cố định VD Puck/Kore/Zephyr...) — tái
# dùng ROUTER_API_KEY đã có, KHÔNG cần secret riêng
python pipeline.py --url "..." --script-mode translate --tts-provider router-tts --voice-id "Puck"
```

Trên web UI: `GET /api/voices` tự gộp danh sách giọng cả 3 provider (Vivibe
chỉ hiện nếu đã cấu hình `VIVIBE_API_KEY`), có nút "Nghe thử" cạnh mỗi giọng
trước khi chạy job. Chưa cấu hình `VIVIBE_API_KEY` vẫn dùng đủ tính năng với
edge-tts + 9router TTS, không lỗi.

Lưu ý: quota giọng Gemini qua 9router có thể bị giới hạn theo phút (dịch vụ
ngoài dự án) — nếu gặp lỗi "exceeded your current quota", đợi vài chục giây
rồi thử lại.

## Ví dụ

```bash
# Dịch chuẩn (lồng tiếng), giữ nhạc nền gốc
python pipeline.py --url "https://www.tiktok.com/@user/video/123" --script-mode translate

# Sáng tạo (tự soạn kịch bản mới), kèm phụ đề động khớp nhịp giọng đọc
python pipeline.py --url "https://www.douyin.com/video/456" --script-mode rewrite --dynamic-captions

# Phụ đề tự động — giữ nguyên âm thanh gốc, chỉ thêm phụ đề dịch sát nghĩa
python pipeline.py --url "https://www.tiktok.com/@user/video/123" --script-mode subtitle

# Resume job bị lỗi giữa chừng
python pipeline.py --url "..." --script-mode translate --job-id "uuid-của-job-cũ"
```

## Nguồn hỗ trợ

| Nền tảng | Engine | Watermark-free |
|---|---|---|
| TikTok | `f2` | ✅ |
| Douyin (抖音) | `f2` | ✅ |
| YouTube | `yt-dlp` | N/A |

## Giao diện web (thay thế CLI, feature 002-web-ui)

Đăng nhập bằng `WEB_UI_USERNAME`/`WEB_UI_PASSWORD`, submit URL + chọn chế độ xử
lý (Dịch chuẩn / Sáng tạo / Phụ đề tự động) qua form, tuỳ chọn bật "Phụ đề
động" cho 2 chế độ lồng tiếng, theo dõi % tiến trình, xem/tải video kết quả,
xem lịch sử job và thử lại job lỗi — không cần dùng dòng lệnh.

### Chạy bằng Docker (khuyến nghị) — 2 container tách biệt

`web-api` (FastAPI + pipeline) và `web-ui` (nginx serve React build, tự proxy
`/api/*` sang `web-api` — cùng origin nên không cần cấu hình CORS):

```bash
docker compose up -d --build web-api web-ui
```

Mở `http://localhost` (web-ui, cổng 80). `web-api` cũng expose trực tiếp ở
`http://localhost:8000` để tiện curl-test API khi cần. `./jobs/` vẫn mount ra
host như CLI. Dừng: `docker compose down`.

### Chạy local không Docker (1 process, tự serve luôn React build)

```bash
cd web/frontend && npm install && npm run build && cd ../..
uvicorn web.backend.main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`. Chi tiết API, thiết kế và kịch bản validate từng
user story: [`specs/002-web-ui/`](specs/002-web-ui/).

### Đăng video lên TikTok (feature 006-publish-video-tab)

Tab **Đăng video** trong giao diện web cho phép đăng thẳng video đã xử lý xong
lên kênh TikTok của bạn — không cần tải file về rồi đăng tay.

Cần thêm 1 dòng vào `.env`:

```bash
ZERNIO_API_KEY=sk_...
```

Key lấy ở dashboard [Zernio](https://zernio.com) — dịch vụ trung gian đã được
nền tảng cấp phép đăng bài tự động, nên video lên **công khai ngay** mà không
cần tự xin duyệt app riêng và không có rủi ro tài khoản. Không cấu hình key thì
mọi thứ khác chạy bình thường, chỉ tab Đăng video báo chưa cấu hình.

Cách dùng: mở tab **Đăng video** → "Kết nối kênh TikTok" (cấp quyền ngay trên
TikTok, chỉ làm 1 lần) → chọn video đã xử lý xong → điền tiêu đề → **Đăng**.

Lưu ý:

- Bài đăng là **công khai thật** và **không sửa/xoá được từ giao diện này** —
  thao tác đó làm trực tiếp trên app/website của nền tảng.
- Zernio tính phí theo số kênh đã kết nối.
- Ngắt kết nối trong tab này chặn mọi lượt đăng tới kênh đó; muốn thu hồi quyền
  hoàn toàn thì làm thêm trong cài đặt ứng dụng của nền tảng.
- YouTube Shorts nằm trong phạm vi tính năng nhưng chưa bật ở bản này.

Chi tiết: [`specs/006-publish-video-tab/`](specs/006-publish-video-tab/).

#### Hẹn giờ đăng (feature 007-schedule-publish)

Ngoài "Đăng ngay", có thể chọn **"Hẹn giờ"** để đặt lịch đăng vào thời điểm cụ
thể (giờ Việt Nam). Video được tải lên Zernio ngay lúc đặt lịch — **Zernio giữ
bài và tự đăng đúng giờ, hệ thống này không cần chạy vào lúc đó** (kể cả khi đã
tắt máy hoàn toàn).

Ràng buộc:

- Hẹn được từ **15 phút** đến tối đa **3 ngày** kể từ lúc đặt lịch.
- Muốn xem/huỷ bài đang chờ: mục "Đang chờ đăng" trong tab Đăng video. Huỷ chỉ
  có tác dụng **trước** giờ đăng — bài đã lên rồi thì không huỷ được nữa.
- Ngắt kết nối một kênh sẽ **tự huỷ mọi bài đang chờ đăng lên kênh đó**, để
  tránh video lên ngầm một kênh bạn tưởng đã ngắt.
- Trạng thái (thành công/thất bại) chỉ được cập nhật khi bạn **mở lại giao
  diện** sau giờ hẹn — không có thông báo đẩy khi bạn vắng mặt.
- Không hỗ trợ đổi giờ của bài đã hẹn — huỷ rồi đặt lịch lại nếu cần.

Chi tiết: [`specs/007-schedule-publish/`](specs/007-schedule-publish/).

### Tạo video từ chủ đề (feature 010-topic-video-generation)

Tab **Tạo từ chủ đề** trong giao diện web — nhập 1 chủ đề văn bản (không cần
URL video có sẵn), hệ thống tự viết kịch bản (tự tra cứu web khi cần), tìm ảnh
minh hoạ qua Pexels, đọc giọng từng đoạn, rồi dựng thành video dọc (9:16) hoàn
chỉnh. Bật **"Quản lý pipeline"** để dừng lại duyệt/sửa outline và lời thoại
từng scene trước khi hệ thống tốn chi phí tìm ảnh/đọc giọng/render.

Cần thêm 1 dòng vào `.env` (đăng ký free tại [pexels.com/api](https://www.pexels.com/api/)):

```bash
PEXELS_API_KEY=...
```

Bước render cuối gọi `npx hyperframes render` — máy chạy pipeline cần có sẵn
Node.js 22+ và Chrome headless (Dockerfile đã cài sẵn khi build bằng Docker).

Chi tiết: [`specs/010-topic-video-generation/`](specs/010-topic-video-generation/).

## Kiểm tra môi trường

```bash
python env_check.py
```

## Chạy test

```bash
pytest tests/unit -q
```

Test của tính năng đăng video (kể cả hẹn giờ) luôn mock lớp HTTP — không lượt
test nào gọi thật tới Zernio (tốn chi phí thật và tạo bài đăng công khai thật).

## Cấu trúc output

Mỗi lần chạy tạo thư mục `jobs/{job_id}/`:

```
jobs/{job_id}/
├── job.json         # Trạng thái và metadata
├── source.mp4       # Video gốc đã tải
├── transcript.json  # Lời thoại trích xuất (kèm mốc thời gian từng câu)
├── script.json      # Kịch bản tiếng Việt, chia theo từng nhịp (mảng segments)
├── segments/        # Audio trung gian từng nhịp + khoảng lặng (phục vụ resume)
├── voice.wav        # Giọng đọc đã ghép theo timeline — không có nếu script-mode=subtitle
├── voice_timeline.json  # Mốc thời gian THỰC TẾ từng nhịp trong voice.wav + nhịp lỗi (nếu có)
├── background.wav   # Nhạc nền tách được (Demucs), nếu có
├── captions.json    # Mốc thời gian phụ đề động theo nhịp, nếu bật --dynamic-captions
├── subtitles.srt     # File phụ đề trung gian trước khi burn-in (subtitle hoặc dynamic-captions)
└── output.mp4       # Sản phẩm cuối cùng
```

## Tài liệu kỹ thuật

- Pipeline CLI (spec, plan, quickstart): [`specs/001-video-repurpose-pipeline/`](specs/001-video-repurpose-pipeline/)
- Giao diện web (spec, plan, API, quickstart): [`specs/002-web-ui/`](specs/002-web-ui/)
- Đăng video lên TikTok/YouTube (spec, plan, API, quickstart): [`specs/006-publish-video-tab/`](specs/006-publish-video-tab/)
- Hẹn giờ đăng (spec, plan, API, quickstart): [`specs/007-schedule-publish/`](specs/007-schedule-publish/)
- Sửa lỗi lồng tiếng + phụ đề tự động/động (spec, plan, research, quickstart): [`specs/003-dubbing-fixes-subtitles/`](specs/003-dubbing-fixes-subtitles/)
- Chọn giọng đọc + nghe thử, provider Vivibe (spec, plan, research, quickstart): [`specs/004-voice-selection-preview/`](specs/004-voice-selection-preview/)
- Lồng tiếng khớp nhịp tự nhiên theo từng câu (spec, plan, research, quickstart): [`specs/005-natural-pause-dubbing/`](specs/005-natural-pause-dubbing/)

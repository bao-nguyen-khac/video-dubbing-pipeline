# Phase 0 Research: Sửa lỗi lồng tiếng & thêm phụ đề tự động, phụ đề động

Toàn bộ quyết định dưới đây dựa trên **root-cause thật** đã reproduce trực tiếp
trên container `web-api` đang chạy thật (không phải suy đoán từ đọc code), và
dữ liệu thật từ 3 job đã chạy qua giao diện web (`jobs/0ecd7793.../job.json`,
`jobs/c7809e4a.../job.json`, `jobs/5eb21cb3.../job.json`).

## 1. US1 — Mất nhạc nền gốc (áp dụng cả Dịch chuẩn lẫn Sáng tạo)

**Root cause đã xác nhận**: `merge/vocal_separator.py` gọi Demucs, Demucs
tách audio thành công (~43s) nhưng **fail ở bước cuối lưu file** —
`torchaudio.save()` trong bản `torchaudio==2.11.0` đang cài (kéo theo tự động
qua `torch==2.13.0`, không pin cứng trong `requirements.txt`) chỉ còn đường
lưu qua `save_with_torchcodec`, và raise `ImportError: TorchCodec is required
...` vì thiếu package `torchcodec`. Lỗi này bị `vocal_separator.py` bắt như
"Demucs lỗi" chung chung rồi trả `None` → `merge/ffmpeg_merge.py` fallback mute
toàn bộ audio gốc — đúng 100% với triệu chứng người dùng báo (mất nhạc nền ở
CẢ 2 chế độ, không phải lỗi ngẫu nhiên theo video). Xác nhận bằng dữ liệu thật:
cả 3 job gần nhất (2 Dịch chuẩn, 1 Sáng tạo) đều có
`warnings.background_music_lost = true`.

**Đã verify fix**: `pip install torchcodec` ngay trong container đang chạy rồi
chạy lại `extract_background_music()` với đúng `source.mp4` thật của 1 job đã
lưu — tách thành công, sinh `background.wav` hợp lệ (~11.6MB) trong 42.7s.

- **Decision**: Thêm `torchcodec` vào `requirements.txt` (cùng nhóm với
  `demucs`/`torchaudio`), rebuild Docker image. Không cần đổi logic
  `vocal_separator.py`/`ffmpeg_merge.py` — cơ chế giữ nhạc nền (FR-009 của
  001, amix voice+background) vốn đã đúng, chỉ là môi trường thiếu 1
  dependency khiến Demucs luôn fail ở bước lưu file.
- **Rationale**: Root cause nằm ở tầng dependency/môi trường, không phải
  logic nghiệp vụ — fix tối thiểu, đúng bản chất, không viết lại module.
- **Alternatives considered**: Pin `torchaudio` xuống bản cũ hơn (còn backend
  `soundfile`/`sox_io` không cần torchcodec) — khả thi nhưng rủi ro breaking
  API khác của `torchaudio` mà `demucs`/`openunmix` phụ thuộc; thêm
  `torchcodec` là thay đổi nhỏ nhất, đúng hướng nâng cấp chính thức của
  PyTorch (torchcodec là thư viện I/O audio/video thế hệ mới chính thức từ
  PyTorch, không phải một fork/patch tạm).

## 2. US2 — Lệch thời lượng giọng đọc ở chế độ Sáng tạo

**Root cause đã xác nhận**: Đo trực tiếp job Sáng tạo thật
(`0ecd7793...`): video gốc 65.95s, kịch bản Sáng tạo (550 ký tự) sau khi
đọc chỉ dài 50.59s ở tốc độ mặc định — **ngắn hơn 23.3%** so với video gốc.
Cơ chế 2-pass hiện có ở `tts/edge_tts_client.py` (chỉnh `rate` edge-tts) chỉ
được phép chỉnh trong khoảng `[-20%, +40%]` (`_RATE_MIN_PCT`/`_RATE_MAX_PCT`)
để tránh nghe bất thường — không đủ bù hết mức lệch 23.3% này (mức lệch thực
tế trước khi chỉnh còn lớn hơn nữa), nên vẫn còn dư lệch sau lượt 2. Nguyên
nhân gốc không nằm ở TTS mà ở bước sinh kịch bản: `REWRITE_SYSTEM` prompt
(`script_gen/router_client.py`) chỉ ghi "Độ dài tương đương transcript gốc"
— một chỉ dẫn định tính, LLM không biết số giây/số ký tự mục tiêu cụ thể nên
độ dài kịch bản trả về không ổn định.

- **Decision (đã sửa lại dựa trên bằng chứng thật lúc implement/verify — xem
  tasks.md T011/T013)**: Tính ngân sách độ dài mục tiêu (số ký tự) từ
  `source_duration` × tốc độ đọc trung bình đã biết của voice edge-tts đang
  dùng (`vi-VN-NamMinhNeural`), CHỈ áp dụng cho `REWRITE_SYSTEM` (không áp
  dụng `TRANSLATE_SYSTEM`), chèn dưới dạng chỉ dẫn "PHẢI DÀI ÍT NHẤT N ký tự"
  (mức tối thiểu, cấm viết ngắn hơn) — không phải "khoảng N ký tự". Thêm cơ
  chế retry tối đa 2 lần kèm feedback cụ thể khi vẫn dưới 85% ngân sách, hạ
  `temperature` ở lượt retry. Giữ nguyên cơ chế 2-pass rate-adjustment hiện
  có ở `edge_tts_client.py` làm lớp bù sai số cuối cùng.
- **Vì sao đổi so với thiết kế ban đầu**: Test thật lúc implement (T013) cho
  thấy thiết kế ban đầu (áp cả 2 mode, nói "khoảng N ký tự") phản tác dụng
  RÕ RỆT — rewrite chỉ đạt 22-26s/66s (lệch tới -65%, TỆ HƠN cả baseline gốc
  -23.3%), và translate bị cắt mất hẳn 1/3 nội dung đầu video (LLM hiểu
  "khoảng N" kèm "ưu tiên bám sát số này hơn kể đầy đủ" là được phép cắt bớt
  nội dung). Sau khi sửa theo thiết kế mới: 5/5 lượt test thật đạt SC-002
  (lệch ≤10%, phần lớn dưới 0.5%).
- **Rationale**: Sửa đúng gốc (kịch bản sinh ra sai độ dài ngay từ đầu) rẻ
  hơn và hiệu quả hơn cố nới biên độ `rate` (nới biên độ rate quá xa sẽ làm
  giọng đọc nghe rõ ràng bất thường — đánh đổi chất lượng để che gốc sai).
  `translate` không cần budget vì bản chất là dịch đầy đủ (độ dài tự nhiên đã
  khá gần video gốc, xem T013), thêm ràng buộc độ dài chỉ tạo rủi ro cắt xén
  không cần thiết.
- **Alternatives considered**: Nới `_RATE_MIN_PCT`/`_RATE_MAX_PCT` rộng hơn —
  bị loại vì chỉ che triệu chứng, giọng đọc nghe nhanh/chậm bất thường hơn;
  áp budget cho cả 2 mode — đã thử thật và bị loại vì gây regression nặng ở
  translate (xem trên); nói "khoảng N ký tự" thay vì "tối thiểu N" — đã thử
  thật và bị loại vì LLM undershoot mạnh.

## 3. US3 — Phụ đề tự động (giữ nguyên âm thanh gốc)

**Vấn đề kiến trúc cần giải quyết**: `script_gen/router_client.py` hiện dịch
`transcript.json.full_text` như MỘT khối văn bản duy nhất, không giữ lại mốc
thời gian theo từng câu — trong khi `asr/transcriber.py` đã sẵn có
`segments: [{start, end, text}]` với timestamp chính xác. Phụ đề cần khớp
đúng nhịp lời thoại gốc, nên bắt buộc phải dịch theo từng segment, giữ
nguyên `start`/`end` của ASR.

- **Decision**: Thêm 1 hàm dịch theo segment (dịch từng `segment.text`, giữ
  nguyên `start`/`end`, gộp lại thành 1 danh sách "subtitle cues") — tái dùng
  cùng cách dịch sát nghĩa như `TRANSLATE_SYSTEM` (đúng Clarification Q2 của
  spec: phụ đề tự động luôn dịch sát nghĩa). Sinh file phụ đề (SRT/ASS) từ
  danh sách cues này, ghi cứng (burn-in) vào video bằng bộ lọc `subtitles`
  của ffmpeg (`-vf "subtitles=...:force_style='Alignment=2,...'"` — căn giữa
  dưới), giữ nguyên toàn bộ audio gốc (map thẳng audio stream gốc, không qua
  TTS/tách nhạc).
- **Rationale**: Tái dùng tối đa hạ tầng đã có (ASR segment timestamp, cách
  dịch sát nghĩa hiện có) — chỉ thêm 1 module burn-subtitle mới, không viết
  lại ASR/dịch từ đầu.
- **Alternatives considered**: Dịch nguyên khối rồi tự chia đều theo tỷ lệ
  thời gian — bị loại vì tỷ lệ ký tự Việt/nguồn không tuyến tính theo thời
  gian nói thật, phụ đề sẽ lệch nhịp; giữ subtitle như track phụ đề mềm
  (soft-sub, không burn) — bị loại vì Assumptions của spec đã chốt burn-in để
  xem được trên mọi nền tảng re-upload (TikTok/Douyin không hiển thị soft-sub
  track ngoài ý).

## 4. US4 — Phụ đề động khớp nhịp giọng đọc (cho video đã lồng tiếng)

**Vấn đề kỹ thuật cần giải quyết**: Khác US3 (audio giữ nguyên, khớp theo
mốc ASR gốc), ở US4 audio phát ra là **giọng TTS mới** — mốc thời gian phải
khớp theo chính giọng đọc mới đó, không phải theo ASR gốc (2 track có nhịp
khác nhau, nhất là ở chế độ Sáng tạo nội dung đã viết lại hoàn toàn khác).

- **Đã verify thật**: `edge_tts.Communicate.stream()` (bản `edge-tts==7.2.8`
  đang cài) phát ra TRỰC TIẾP chunk `type="SentenceBoundary"` kèm
  `offset`/`duration` (đơn vị 100-ns, tự tính `/1e7` ra giây) cho từng câu —
  test thật với 3 câu tiếng Việt cho ra đúng 3 chunk, mốc thời gian nối tiếp
  khớp nhau (`end` câu trước == `offset` câu sau). Không cần tự gom
  `WordBoundary` theo dấu câu như dự tính ban đầu — SDK đã làm sẵn đúng đơn
  vị cần (câu/cụm, Clarification Q1 của spec).
- **Decision**: Dùng trực tiếp chunk `SentenceBoundary` từ `.stream()` làm
  cue phụ đề động — không xử lý `WordBoundary`. Sau khi `synthesize()` chọn
  xong rate cuối cùng (2-pass hiện có ở US1/US2, không đổi), chạy thêm 1 lượt
  `.stream()` riêng CÙNG rate đó chỉ để thu `SentenceBoundary` (bỏ audio bytes
  của lượt này, không ghi đè `voice.wav` đã chốt) — ghi ra
  `jobs/{job_id}/captions.json`. Tái dùng đúng cơ chế burn-in `subtitles`
  filter của US3 để hiển thị.
- **Rationale**: `edge-tts` đã trả sẵn đúng đơn vị (câu/cụm) cần dùng, không
  cần thêm công cụ forced-alignment riêng (VD Montreal Forced Aligner) — giữ
  đúng Constitution Principle V (Token & Context Economy). Tách lượt thu
  caption riêng (không lồng vào logic 2-pass rate-adjustment đã verify kỹ ở
  US1/US2) để không rủi ro hồi quy code đã test.
- **Alternatives considered**: Forced-alignment giọng đọc TTS bằng công cụ
  riêng (whisper lại chính voice.wav để lấy timestamp) — bị loại vì tốn thêm
  1 lượt ASR không cần thiết trong khi `edge-tts` đã trả sẵn timing chính xác
  hơn; tự gom `WordBoundary` theo dấu câu — bị loại vì `SentenceBoundary` đã
  làm đúng việc này, không cần tự suy luận ranh giới câu từ dấu câu (rủi ro
  sai với câu không có dấu chấm rõ ràng).

## 5. Mở rộng Processing Mode (US3) trong state machine hiện có

- **Decision**: Giữ nguyên field `script_mode` và toàn bộ 7 trạng thái
  (`pending → downloading → transcribing → scripting → synthesizing →
  merging → done`, `failed` từ bất kỳ bước nào) của
  001-video-repurpose-pipeline — chỉ thêm giá trị enum thứ 3 `subtitle`.
  Khi `script_mode == "subtitle"`: bước `synthesizing` không sinh
  `voice_track` (bỏ qua TTS, `artifacts.voice_track` giữ `null` có chủ đích),
  bước `merging` chuyển sang burn phụ đề + giữ nguyên audio gốc thay vì
  ghép voice/nhạc nền.
- **Rationale**: Không đổi state machine đã audit/verify kỹ ở 001 — giảm rủi
  ro hồi quy, đúng Constitution Principle VI (thay đổi nhỏ, verify được từng
  bước).
- **Alternatives considered**: Thêm state machine riêng cho mode `subtitle`
  — bị loại vì tăng độ phức tạp không cần thiết trong khi 2 bước
  `synthesizing`/`merging` chỉ cần rẽ nhánh hành vi theo `script_mode`, không
  cần trạng thái mới.

## 7. Burn-in phụ đề bắt buộc re-encode video (thay đổi so với 001)

**Đã verify**: `ffmpeg -filters` trong container `web-api` đang chạy xác nhận
có sẵn filter `subtitles`/`ass` (build kèm `--enable-libass` và
`--enable-libx264`) — không cần cài thêm dependency nào cho việc burn-in.

**Vấn đề kỹ thuật cần lưu ý**: `merge/ffmpeg_merge.py` hiện tại luôn dùng
`-c:v copy` (không re-encode video, chỉ thay/ghép audio) — nhanh và giữ
nguyên chất lượng gốc. Bộ lọc `subtitles=` của ffmpeg (dùng để burn-in ở US3
và US4) là video filter, **bắt buộc phải re-encode video stream**, không thể
dùng `-c:v copy` khi có phụ đề.

- **Decision**: Với job có burn-in phụ đề (`script_mode = subtitle` hoặc
  `dynamic_captions = true`), encode lại video bằng `libx264`, `-crf 20
  -preset medium` (chất lượng gần lossless, thời gian encode chấp nhận được
  cho video ngắn TikTok/Douyin/YouTube Shorts). Job không có phụ đề (translate/
  rewrite không bật `dynamic_captions`) giữ nguyên `-c:v copy` như 001, không
  đổi hành vi/performance đã có.
- **Rationale**: Không có cách nào burn chữ vào khung hình mà không re-encode
  — chấp nhận đánh đổi thêm thời gian xử lý cho các job có bật phụ đề, đúng
  tinh thần SC-002 của 001 (đã chấp nhận nới thời gian xử lý để đổi lấy chất
  lượng sản phẩm tốt hơn).
- **Alternatives considered**: Xuất phụ đề dạng track rời (soft-sub) để tránh
  re-encode — đã loại ở research.md §3 (không xem được khi re-upload lên
  TikTok/Douyin).

## 6. Phụ đề động (US4) là tuỳ chọn độc lập, không phải Processing Mode riêng

- **Decision**: Thêm 1 field boolean mới `dynamic_captions` trên Job (mặc
  định `false`), chỉ có ý nghĩa khi `script_mode` là `translate` hoặc
  `rewrite`. Bật/tắt độc lập với việc chọn Processing Mode, set ở bước khởi
  tạo job giống `script_mode`.
- **Rationale**: US4 là tính năng cộng thêm cho 2 chế độ lồng tiếng đã có
  (đúng như mô tả gốc "1,2 thêm tính năng..."), không phải một Processing
  Mode ngang hàng như `subtitle` — tách field riêng để không phá vỡ ý nghĩa
  3 giá trị enum của `script_mode`.

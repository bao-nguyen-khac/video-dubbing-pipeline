# Research: Lồng tiếng khớp nhịp tự nhiên theo từng câu (005)

**Phase 0 output** — mọi quyết định kỹ thuật cần chốt trước khi thiết kế
data-model/contracts. Ghi lại từ khảo sát code hiện có trong repo
(001/003/004) + ràng buộc đã có trong Constitution v1.5.0.

## §1. Đơn vị lồng tiếng: gom ASR segment thành "dubbing unit"

**Decision**: KHÔNG dùng thẳng 1 ASR segment = 1 câu lồng tiếng. Thêm bước gom
(`group_segments()`) biến `transcript.json.segments` thành danh sách *dubbing
unit*, theo 3 quy tắc:

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `_GAP_SILENCE_THRESHOLD` | `0.30` giây | Khoảng trống giữa 2 segment nhỏ hơn ngưỡng này = KHÔNG phải ngắt nghỉ thật → gộp 2 segment vào cùng 1 unit (FR-008) |
| `_MIN_UNIT_DURATION` | `1.20` giây | Unit ngắn hơn ngưỡng này được gộp tiếp với unit kế tiếp (nếu khoảng trống giữa chúng < 1.0s) — tránh vụn câu ở chế độ Sáng tạo (FR-004, US2 scenario 2) |
| `_MAX_UNIT_DURATION` | `15.0` giây | Không gộp vượt ngưỡng này — giữ tính "theo câu", tránh thoái hoá về cơ chế nguyên khối cũ |

`start` của unit = `start` của segment đầu, `end` = `end` của segment cuối trong
unit; text = nối các segment con bằng khoảng trắng.

**Rationale**: faster-whisper cắt segment theo VAD/độ dài chứ không theo nhịp
nghỉ ngữ nghĩa — nhiều segment liền nhau cách nhau 0.0–0.2s (thực chất là 1
câu nói liền mạch). Nếu TTS từng segment rồi ghép, mỗi ranh giới đó thành 1
điểm nối audio → nghe giật, và LLM phải dịch/viết những mẩu 3-4 từ → cụt.
Gom theo ngưỡng khoảng lặng vừa đúng định nghĩa "ngắt nghỉ tự nhiên" của
spec, vừa giảm số lượt gọi TTS.

**Alternatives considered**:
- *1 ASR segment = 1 unit*: đơn giản nhất nhưng vi phạm FR-008 (chèn khoảng
  lặng giả tại các ranh giới 0.0s) và làm vụn kịch bản Sáng tạo.
- *Gom theo dấu câu của bản dịch*: cần dịch trước rồi mới cắt được → mất mốc
  thời gian ASR làm khung, ngược với FR-001/FR-002.
- *Forced alignment (WhisperX/aeneas) để lấy mốc chính xác hơn*: thêm
  dependency nặng, vi phạm Constitution Principle V; spec Assumptions đã chốt
  mốc ASR hiện có là "đủ chính xác".

## §2. Sinh kịch bản theo unit cho cả translate và rewrite

**Decision**: Tái dùng nguyên cơ chế "đánh số dòng" đã verify thật ở
`translate_segments()` (003/US3): gửi 1 lượt gọi LLM duy nhất chứa toàn bộ
unit đã đánh số, bắt model trả về đúng số dòng/đúng thứ tự, parse bằng
`_parse_numbered_lines()`, lệch số dòng → `RuntimeError` (không "đoán" ghép).

- `translate`: dùng lại `SEGMENT_TRANSLATE_SYSTEM` sẵn có.
- `rewrite`: prompt mới `SEGMENT_REWRITE_SYSTEM` — giữ yêu cầu sáng tạo/viết
  lại (không dịch sát nghĩa) NHƯNG ràng buộc "mỗi dòng là 1 nhịp nói độc lập,
  trả đúng số dòng". Input mỗi dòng kèm ngân sách ký tự riêng của unit:
  `[n] (~{N} ký tự) {text gốc}` với `N = round(unit_duration * 10.9)` —
  chính là `estimate_target_char_budget()` đã có, nay áp **theo từng unit**
  thay vì cho cả bài.

**Rationale**: 1 lượt gọi duy nhất giữ được ngữ cảnh xuyên suốt (đã chứng minh
ở 003) và không làm tăng chi phí LLM so với hiện tại. Ngân sách ký tự theo
unit là ràng buộc mạnh hơn hẳn ngân sách toàn bài: model biết chính xác mỗi
nhịp được bao nhiêu chữ.

**Hệ quả — bỏ vòng retry ngân sách ký tự toàn bài của 003/US2**: cơ chế cũ
(gọi lại tối đa 2 lần khi bản rewrite ngắn hơn 85% ngân sách toàn bài) sinh ra
để chống lỗi "audio quá ngắn → bị kéo giãn nghe chậm". Với kiến trúc mới,
audio ngắn hơn khung chỉ đơn giản để lại khoảng lặng thật đúng chỗ, không kéo
giãn gì cả → vòng retry đó không còn lý do tồn tại và bị gỡ. `translate` giữ
nguyên tinh thần cũ (dịch đầy đủ, không áp ngân sách — đã verify ở 003 rằng
áp ngân sách vào translate làm model cắt bớt nội dung).

**Alternatives considered**:
- *Gọi LLM riêng cho từng unit*: mất ngữ cảnh, chi phí gấp N lần, dễ lệch văn
  phong giữa các câu.
- *Giữ rewrite nguyên khối rồi tự cắt theo số unit*: không có cách cắt đúng
  ranh giới ngữ nghĩa mà vẫn khớp số unit → vi phạm FR-004.

## §3. Khớp thời lượng từng câu: `atempo` hậu xử lý, chỉ tăng tốc

**Decision**: Với mọi provider, mỗi unit được sinh **1 lượt gọi TTS ở tốc độ
mặc định**, đo thời lượng thật bằng `ffprobe`, rồi khớp khung bằng ffmpeg
`atempo` hậu xử lý với 2 ràng buộc:

- `tempo ≥ 1.0` — CHỈ tăng tốc khi tràn khung, **không bao giờ kéo chậm**
  (`tempo < 1.0`) để lấp khung: đọc chậm để "vừa khít" chính là root cause
  của lỗi đang sửa. Thiếu thời lượng → để lại khoảng lặng thật.
- `tempo ≤ _MAX_TEMPO = 1.4` — trần dùng chung cho cả 3 provider, lấy đúng
  biên trên hẹp nhất đang có (`edge-tts rate +40%`), nằm trọn trong biên của
  Vivibe/9router (`[0.5, 2.0]`) → không nới biên nào (đúng Assumptions của
  spec) và cho hành vi đồng nhất giữa 3 provider (SC-004).
- Bỏ qua chỉnh khi tràn dưới `_TEMPO_TOLERANCE = 0.15` giây.

**Rationale**: tham số tốc độ của 2/3 provider đã được verify thật là không
dùng được để khớp thời lượng — Vivibe `speed` phi tuyến (`needed_speed=0.541`
dự kiến ~72s nhưng thực tế ra 66.9s), 9router `speed` gần như không tác dụng
(2.88s → 2.76s dù `speed=1.5`) — cả hai hiện đã phải đóng phần lệch còn lại
bằng `atempo`. Dùng thẳng `atempo` cho cả 3: 1 lượt gọi API/unit (quan trọng
khi số lượt gọi tăng theo số câu), hành vi giống hệt nhau giữa các provider,
và không phụ thuộc tham số nhà cung cấp.

**Alternatives considered**:
- *edge-tts dùng `rate` (chất lượng tốt hơn atempo) còn 2 provider kia dùng
  atempo*: cần gọi API lần 2 cho mỗi unit đọc lệch (chi phí/độ trễ nhân đôi ở
  provider mặc định) và làm hành vi khác nhau giữa các provider, ngược SC-004.
- *Cho phép `tempo < 1.0` để lấp đầy khung*: đúng thứ tính năng này đang loại
  bỏ.

## §4. Ghép timeline: concat demuxer + khoảng lặng WAV sinh bằng stdlib

**Decision**: `voice.wav` được ghép bằng ffmpeg **concat demuxer** trên một
danh sách file xen kẽ `[silence_i.wav, unit_i.wav, silence_i+1.wav, ...]`.
Mọi file unit được chuẩn hoá về `44100 Hz / 2 kênh / pcm_s16le` ngay sau khi
tải từ provider; file khoảng lặng sinh bằng module `wave` của stdlib (ghi
frame 0) cùng thông số — không cần gọi ffmpeg cho từng khoảng lặng.

Con trỏ thời gian khi ghép (thực thi FR-009):

```
cursor = 0.0
for unit in units:
    start = max(unit.start, cursor)      # tràn từ câu trước đẩy lùi câu này
    if start > cursor: chèn khoảng lặng (start - cursor)
    ghi audio unit (đã atempo nếu cần)
    cursor = start + duration_thực_tế_của_unit
```

**Rationale**: concat demuxer là O(N) file, lệnh ngắn, không đụng giới hạn số
input/độ dài `filter_complex` khi video có 40-60 unit; đồng thời cho phép
resume theo từng file unit đã sinh. Chuẩn hoá format trước là bắt buộc vì
concat demuxer yêu cầu các file cùng thông số, mà 3 provider trả về định dạng
khác nhau (edge-tts: MP3 → WAV 44.1k/stereo; Vivibe: WAV tải từ URL; 9router:
bytes thô từ `/audio/speech`).

**Alternatives considered**:
- *`adelay` + `amix` trong 1 `filter_complex`*: lệnh phình theo số unit, khó
  debug, và không cho resume từng phần.
- *Ghép bằng pydub/numpy*: thêm dependency mới cho việc ffmpeg đã làm được →
  vi phạm Constitution Principle V.

## §5. Lỗi cục bộ 1 câu: thay bằng khoảng lặng, không fail job

**Decision**: Mỗi unit được gọi TTS với tối đa **2 lần thử** (lần 2 sau khi
thất bại lần 1; edge-tts vẫn giữ thêm fallback backup-voice sẵn có). Thất bại
cả 2 lần → ghi 1 khoảng lặng dài đúng bằng khung gốc của unit đó vào timeline,
đánh dấu `status: "failed"` trong `voice_timeline.json`, in log rõ index +
mốc thời gian, và **tiếp tục** các unit còn lại (FR-006).

- Kết thúc: nếu `failed_count > 0` → `warnings.tts_segments_failed = true` và
  `tts_failed_segments = <số unit lỗi>` trong `job.json` (FR-007).
- Nếu **toàn bộ** unit đều lỗi → raise `RuntimeError` → `fail_job()` như hiện
  tại (Edge Case cuối của spec: không che giấu lỗi toàn phần).

**Rationale**: giữ đúng ranh giới "lỗi cục bộ ≠ lỗi toàn phần" mà spec vạch
ra, và cảnh báo mới phải tách khỏi `duration_mismatch` để người dùng phân biệt
được 2 loại vấn đề (FR-007).

**Alternatives considered**:
- *Retry vô hạn/backoff dài*: job dài lê thê khi provider hết quota — trong khi
  người dùng có sẵn nút "Thử lại" ở web UI (002) để chạy lại.
- *Bỏ hẳn unit lỗi (không chèn khoảng lặng)*: làm lệch toàn bộ mốc thời gian
  các câu sau so với hình ảnh.

## §6. Phụ đề động: lấy mốc từ timeline, gỡ hẳn cơ chế streaming của edge-tts

**Decision**: `captions.json` được sinh trực tiếp từ `voice_timeline.json`
(mỗi unit → 1 cue `{start, end, text}` theo vị trí **thực tế đã ghép**), áp
dụng cho cả 3 provider. Gỡ bỏ `_collect_captions()` /
`_stream_sentence_boundaries()` và tham số `collect_captions` trong
`tts/edge_tts_client.py`. Unit `status: "failed"` không sinh cue (không có
giọng đọc thì không hiện phụ đề).

**Rationale**: đúng Clarification Q2 của spec. Mốc từ timeline chính xác hơn
`SentenceBoundary` (đây là mốc do chính pipeline đặt, không phải ước lượng của
provider), lại đồng nhất 3 provider và tiết kiệm 1 lượt gọi `stream()` phụ
mà edge-tts đang phải chạy riêng.

## §7. Gỡ luôn 3 hàm tổng hợp nguyên khối cũ

**Decision**: Xoá `edge_tts_client.synthesize()`,
`lucyai_client.synthesize_from_script()`,
`router_tts_client.synthesize_from_script()` — toàn bộ luồng
`translate`/`rewrite` đi qua module mới `tts/segment_synthesizer.py`. Giữ lại
`synthesize_text()`/`synthesize()` mức-text của từng provider (đang phục vụ
nghe thử ở `web/backend/voices_api.py` và nay thành adapter cho từng unit);
bổ sung `lucyai_client.synthesize_text(text, voice_id, output_path)` (đọc
`VIVIBE_API_KEY` từ env) để cả 3 provider có cùng chữ ký adapter.

**Rationale**: hai đường tổng hợp song song (nguyên khối + theo câu) sẽ có 2
hành vi khớp thời lượng khác nhau cùng tồn tại — nguồn lỗi và nợ kỹ thuật,
trong khi không có yêu cầu nào giữ lại đường cũ.

**Hệ quả cho job cũ**: `script.json` của job `translate`/`rewrite` tạo trước
feature này không có mảng `segments`. Xử lý: điều kiện resume của
`generate_script()` bổ sung yêu cầu "có `segments`" — file cũ bị coi là chưa
hợp lệ và được sinh lại (1 lượt gọi LLM), thay vì phải nuôi 1 nhánh fallback
nguyên khối chỉ để phục vụ job cũ.

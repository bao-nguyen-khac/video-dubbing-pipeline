# Quickstart / Validation — Lồng tiếng khớp nhịp tự nhiên (005)

Kịch bản chạy thật để chứng minh từng User Story hoạt động end-to-end. Mỗi
mục nêu: chuẩn bị → lệnh chạy → bằng chứng phải thu được (Constitution
Principle VI: task chỉ được coi là xong khi có bằng chứng cụ thể).

## Chuẩn bị chung

```bash
cp .env.example .env      # điền ROUTER_BASE_URL / ROUTER_API_KEY / ROUTER_MODEL
pip install -r requirements.txt
python env_check.py        # phải PASS (ffmpeg + 9router)
```

**Video mẫu bắt buộc** — cần 2 clip khác tính chất, dùng lại xuyên suốt:

| Ký hiệu | Đặc điểm | Dùng cho |
|---|---|---|
| `VIDEO_PAUSE` | Có ≥3 khoảng lặng rõ rệt ≥1s giữa các câu thoại | US1, US2, SC-001, SC-002 |
| `VIDEO_DENSE` | Nói gần như liên tục, hầu như không có khoảng lặng | Edge case "không phát sinh khoảng lặng giả" |

Cách xác nhận nhanh một clip thuộc loại nào (chạy sau khi có
`transcript.json`) — in các khoảng trống giữa segment ASR:

```bash
python - <<'PY'
import json, sys
segs = json.load(open(sys.argv[1]))["segments"]
gaps = [(round(b["start"] - a["end"], 2), round(a["end"], 2))
        for a, b in zip(segs, segs[1:])]
print("Số khoảng trống ≥1s:", sum(1 for g, _ in gaps if g >= 1.0))
print("Chi tiết (gap, tại giây):", [g for g in gaps if g[0] >= 0.5])
PY
jobs/<job_id>/transcript.json
```

## US1 — Giữ nhịp ngắt nghỉ khi Dịch chuẩn (P1)

```bash
python pipeline.py --url "$VIDEO_PAUSE" --script-mode translate
```

**Bằng chứng phải thu được**:

1. `jobs/{id}/script.json` có mảng `segments`, mỗi phần tử có `start`/`end`/
   `translated_text` (data-model.md §2).
2. `jobs/{id}/voice_timeline.json` tồn tại; với mỗi khoảng trống ≥1s trong
   `transcript.json`, tồn tại cặp unit liền nhau trong timeline có
   `segments[i+1].start - segments[i].end ≥ 0.8s` — và ≥90% các khoảng lặng
   gốc lệch vị trí ≤1s so với `transcript.json` (**SC-001**).
3. Trong `voice_timeline.json`, ≥80% unit có `tempo ≤ 1.15` (**SC-002** —
   phần lớn câu đọc gần tốc độ tự nhiên). Không unit nào có `tempo < 1.0`.
4. Nghe `jobs/{id}/output.mp4`: các khoảng lặng xuất hiện đúng chỗ video gốc
   ngắt nghỉ; giọng đọc từng câu không bị chậm bất thường.

**Đối chứng "không tệ hơn trước" (Acceptance 2)**:

```bash
python pipeline.py --url "$VIDEO_DENSE" --script-mode translate
```
`voice_timeline.json` không được có khoảng trống > 0.5s ở chỗ
`transcript.json` không có khoảng trống tương ứng (không sinh khoảng lặng giả).

## US2 — Giữ nhịp ngắt nghỉ khi Sáng tạo (P2)

```bash
python pipeline.py --url "$VIDEO_PAUSE" --script-mode rewrite
```

**Bằng chứng**:

1. `len(script.json["segments"])` == số unit trong `voice_timeline.json`
   (FR-004: kịch bản sáng tạo chia đúng số nhịp, không phải 1 khối tự do).
2. Đọc `script.json`: nội dung từng nhịp vẫn là văn phong viết lại (không
   dịch sát nghĩa) và **không bị cụt/vụn** — không có nhịp chỉ 1-2 từ trừ khi
   segment gốc vốn là cảm thán (US2 Acceptance 2).
3. Khoảng lặng trong `voice_timeline.json` tương ứng khoảng lặng gốc như US1.

## US3 — Job vẫn hoàn tất khi vài câu lỗi TTS (P3)

Cách giả lập rẻ và tái lập được: chạy với `--tts-provider router-tts` rồi rút
mạng/đổi `ROUTER_API_KEY` sai **giữa chừng** bước synthesizing; hoặc tạm sửa
`tts/segment_synthesizer.py` để raise ở đúng 1 index (nhớ hoàn tác trước khi
commit).

```bash
python pipeline.py --url "$VIDEO_PAUSE" --script-mode translate --tts-provider router-tts
```

**Bằng chứng**:

1. Exit code `0`; `job.json` có `status: "done"` và `artifacts.output_video`.
2. `job.json`: `warnings.tts_segments_failed == true`,
   `tts_failed_segments == <số nhịp lỗi>`, và `warnings.duration_mismatch`
   phản ánh đúng thực tế (2 cảnh báo độc lập — FR-007).
3. `voice_timeline.json`: unit lỗi có `status: "failed"`, độ dài đúng bằng
   khung gốc (`end - start == source_end - source_start`), và các unit sau vẫn
   đúng vị trí.
4. Nghe `output.mp4`: chỉ đoạn đó im lặng, phần còn lại lồng tiếng bình
   thường (**SC-003**).

**Đối chứng lỗi toàn phần** — đặt `ROUTER_API_KEY` sai ngay từ đầu:
job phải `status: "failed"`, exit code `2` (Edge Case cuối của spec: không che
giấu lỗi toàn phần).

## FR-011 — Phụ đề động chính xác với cả 3 provider

Chạy cùng 1 `VIDEO_PAUSE` qua từng provider:

```bash
python pipeline.py --url "$VIDEO_PAUSE" --script-mode translate --dynamic-captions
python pipeline.py --url "$VIDEO_PAUSE" --script-mode translate --dynamic-captions \
  --tts-provider router-tts --voice-id Puck
python pipeline.py --url "$VIDEO_PAUSE" --script-mode translate --dynamic-captions \
  --tts-provider lucyai --voice-id "<id giọng Vivibe>"   # bỏ qua nếu chưa có VIVIBE_API_KEY
```

**Bằng chứng**:

1. Cả 3 job đều có `captions.json`, và mỗi cue khớp đúng 1 unit `status="ok"`
   trong `voice_timeline.json` (cùng `start`/`end`/`text`).
2. Xem `output.mp4`: chữ hiện đúng lúc giọng đọc câu đó bắt đầu ở **cả 3**
   provider (trước feature này chỉ đúng với edge-tts).
3. `grep -rn "SentenceBoundary\|collect_captions" tts/ pipeline.py` không còn
   kết quả (research.md §6 — cơ chế cũ đã gỡ hẳn).

## FR-010 — Nhạc nền gốc không bị ảnh hưởng

Ở mọi job trên: `job.json` phải có `artifacts.background_audio` khác `null` và
`warnings.background_music_lost == false` (trừ khi Demucs thật sự lỗi) — hành
vi giữ nhạc nền của 003 không được đổi.

## SC-004 — Nhất quán giữa 3 provider

So 3 job của mục FR-011 với nhau: số unit bằng nhau, vị trí khoảng lặng lệch
≤0.5s giữa các provider, và không provider nào có unit `tempo < 1.0` hay
`tempo > 1.25` (T043, hạ từ `1.4`).

**T037 (làm rõ, 2026-07-27)**: "vị trí khoảng lặng" đo theo mốc **Kết thúc**
của mỗi unit (`voice_timeline.json.segments[i].end` — lúc câu kế tiếp bắt
đầu), KHÔNG phải mốc Bắt đầu. Lý do: mỗi unit neo `start = max(source_start,
end_của_unit_trước)` (research.md §4) nên phần dư khi provider đọc nhanh hơn
khung luôn dồn thành khoảng lặng **đuôi** của chính unit đó — đo theo mốc kết
thúc phản ánh đúng cái người nghe thực sự cảm nhận (khoảng lặng dừng lại lúc
nào), còn đo theo mốc bắt đầu sẽ lẫn cả phần lệch tốc độ đọc của TỪNG
provider (không phải sai lệch vị trí ngắt nghỉ thật) vào phép so sánh.

## Web UI

```bash
docker compose up -d --build web-api web-ui   # hoặc chạy local, xem README
```

Mở `http://localhost`, submit 1 job `VIDEO_PAUSE` với "Dịch chuẩn" + "Phụ đề
động". Khi job có nhịp lỗi TTS, trang chi tiết job phải hiện dòng cảnh báo mới
kèm số lượng câu bị ảnh hưởng ở khối "Cảnh báo chất lượng"
(contracts/api.md §5), và vẫn hiện video kết quả + nút tải về.

## Kiểm tra hồi quy (không được vỡ)

| Kịch bản | Kỳ vọng |
|---|---|
| `--script-mode subtitle` | Không đổi hoàn toàn: không TTS, không `voice_timeline.json`, audio gốc giữ nguyên, phụ đề burn như 003 |
| Resume `--job-id` của job mới lỗi ở `merging` | Không gọi lại TTS (dùng `voice.wav` + `voice_timeline.json` sẵn có) |
| Resume `--job-id` của job **cũ** (script.json không có `segments`) | `script.json` được sinh lại kèm `segments`, rồi chạy tiếp bình thường (research.md §7) |
| Nghe thử giọng trên web UI (`POST /api/voices/preview`) | Không đổi với cả 3 provider |

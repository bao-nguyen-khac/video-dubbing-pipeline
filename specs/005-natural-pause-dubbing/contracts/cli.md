# CLI Contract — bổ sung của feature 005

Phần mở rộng của [`specs/001-video-repurpose-pipeline/contracts/cli.md`](../../001-video-repurpose-pipeline/contracts/cli.md)
và [`specs/003-dubbing-fixes-subtitles/contracts/cli.md`](../../003-dubbing-fixes-subtitles/contracts/cli.md).
Chỉ ghi phần **khác biệt**.

## 1. Tham số dòng lệnh: KHÔNG đổi

```bash
python pipeline.py --url <url> --script-mode <translate|rewrite|subtitle> \
  [--dynamic-captions] [--tts-provider <edge-tts|lucyai|router-tts>] \
  [--voice-id <voice_id>] [--job-id <job_id>]
```

Không thêm/bớt/đổi tên flag nào. Tính năng này đổi *cách* bước `synthesizing`
làm việc, không đổi giao diện gọi.

**Ngưỡng kỹ thuật là hằng số trong code, KHÔNG expose ra CLI** (`0.30s` gộp
segment, `1.20s` unit tối thiểu, `15.0s` unit tối đa, `atempo ∈ [1.0, 1.25]`)
— giữ đúng Constitution Principle V, tránh phình bề mặt tham số cho thứ người
dùng không có cơ sở để chỉnh.

## 2. Ngữ nghĩa đổi

| Flag | Trước | Sau |
|---|---|---|
| `--dynamic-captions` | Mốc phụ đề lấy từ streaming của edge-tts → chỉ chính xác với `--tts-provider edge-tts` | Mốc lấy từ `voice_timeline.json` → chính xác như nhau với **cả 3 provider** (FR-011) |
| `--job-id` (resume ở bước `synthesizing`) | Có `voice.wav` → bỏ qua toàn bộ TTS | Có `voice.wav` + `voice_timeline.json` → bỏ qua; chỉ có 1 phần file trong `segments/` → sinh tiếp các unit còn thiếu, không gọi lại provider cho unit đã xong |

## 3. Output stdout — dòng log mới

Bước `synthesizing` in tiến độ theo unit và tổng kết:

```
[pipeline][{jid}] Bắt đầu synthesizing (provider=edge-tts, voice=vi-VN-NamMinhNeural)...
[segment_synthesizer] 24 nhịp lồng tiếng (gộp từ 41 segment ASR)
[segment_synthesizer] [7/24] 12.30s→15.10s | tempo=1.18
[segment_synthesizer] ⚠ Nhịp 12 (21.40s→24.02s) TTS lỗi sau 2 lần thử, thay bằng khoảng lặng: <lý do>
[pipeline][{jid}] TTS xong: .../voice.wav (58.4s, video gốc 57.9s, 1/24 nhịp lỗi)
```

Cảnh báo cuối job (khi có unit lỗi), song song với cảnh báo lệch thời lượng
đã có:

```
[pipeline][{jid}] ⚠ Cảnh báo: 1 nhịp bị lỗi tổng hợp giọng đọc, đã thay bằng khoảng lặng
```

## 4. Exit code — KHÔNG đổi

| Code | Ý nghĩa |
|---|---|
| `0` | Hoàn tất (**kể cả khi có unit TTS lỗi cục bộ** — FR-006, đây là thay đổi hành vi: trước đây 1 lỗi TTS bất kỳ → exit 2) |
| `1` | Môi trường/tham số không hợp lệ |
| `2` | Job failed — với bước `synthesizing`, chỉ còn khi **toàn bộ** unit đều lỗi, hoặc `script.json` không có `segments` hợp lệ |

## 5. Cấu trúc thư mục job — file mới

```
jobs/{job_id}/
├── voice_timeline.json      # MỚI — vị trí thực tế từng nhịp trong voice.wav
├── segments/                 # MỚI — audio trung gian từng nhịp (phục vụ resume)
│   ├── unit_0000.wav
│   ├── silence_0001.wav
│   └── ...
├── voice.wav                 # Nay là kết quả ghép từ segments/, không phải 1 lượt TTS
├── captions.json             # Nay sinh từ voice_timeline.json, dùng được cho cả 3 provider
└── ...                       # các file khác không đổi
```

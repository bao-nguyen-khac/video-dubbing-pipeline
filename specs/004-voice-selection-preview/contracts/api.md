# Contract: Web UI REST API (mở rộng)

Kế thừa [contracts/api.md của 002](../../002-web-ui/contracts/api.md) và
[contracts/api.md của 003](../../003-dubbing-fixes-subtitles/contracts/api.md)
— chỉ liệt kê phần thay đổi/mới.

## GET /api/voices (mới)

**Auth**: Required.

Trả danh sách Voice gộp từ edge-tts + LucyAI (nếu đã cấu hình
`VIVIBE_API_KEY`) — xem [data-model.md](../data-model.md).

**Response**: `200 OK`
```json
{
  "voices": [
    { "provider": "edge-tts", "voice_id": "vi-VN-NamMinhNeural", "name": "Microsoft NamMinh Online (Natural)" },
    { "provider": "edge-tts", "voice_id": "vi-VN-HoaiMyNeural", "name": "Microsoft HoaiMy Online (Natural)" },
    { "provider": "lucyai", "voice_id": "...", "name": "..." }
  ]
}
```

Nếu `VIVIBE_API_KEY` chưa cấu hình hoặc `getUserVoices` lỗi: mảng `voices`
chỉ gồm giọng `edge-tts`, response vẫn `200 OK` (FR-003 — không lỗi cả
endpoint vì 1 provider phụ lỗi).

## POST /api/voices/preview (mới)

**Auth**: Required.

Sinh và trả về audio mẫu (FR-004/FR-005) — KHÔNG tạo job trong `jobs/`,
KHÔNG bị chặn bởi rule "đang có job chạy" (FR-008).

**Request body**:
```json
{ "provider": "edge-tts | lucyai", "voice_id": "string" }
```

**Response**:
- `200 OK` — `Content-Type: audio/wav`, stream trực tiếp audio mẫu.
- `400 Bad Request` — `provider`/`voice_id` không hợp lệ.
- `502 Bad Gateway` — provider lỗi lúc sinh audio (VD LucyAI API key sai/hết
  hạn, hoặc timeout poll `getExportStatus`), body `{"error": "..."}` nêu rõ
  nguyên nhân (FR-007 áp dụng tương tự cho cả preview lẫn job thật).

## POST /api/jobs (request body thay đổi)

```json
{
  "url": "string",
  "script_mode": "translate | rewrite | subtitle",
  "dynamic_captions": false,
  "tts_provider": "edge-tts",
  "voice_id": "vi-VN-NamMinhNeural"
}
```

- `tts_provider`/`voice_id`: optional, mặc định `edge-tts`/giọng hiện có nếu
  không gửi (backward-compatible với client cũ). Chỉ có hiệu lực khi
  `script_mode` là `translate`/`rewrite`.

## GET /api/jobs/{job_id} (Job Detail — field mới)

```json
{
  "...": "...(field cũ giữ nguyên)",
  "tts_provider": "edge-tts",
  "voice_id": "vi-VN-NamMinhNeural"
}
```

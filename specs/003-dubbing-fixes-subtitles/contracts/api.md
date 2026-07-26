# Contract: Web UI REST API (mở rộng)

Kế thừa [contracts/api.md của 002-web-ui](../../002-web-ui/contracts/api.md) —
chỉ liệt kê phần thay đổi. Auth/polling contract giữ nguyên như 002.

## POST /api/jobs (request body thay đổi)

```json
{
  "url": "string",
  "script_mode": "translate | rewrite | subtitle",
  "dynamic_captions": false
}
```

- `script_mode`: thêm giá trị `subtitle` (US3). Validate như cũ ở FR-002 của
  002 (400 nếu không hợp lệ).
- `dynamic_captions` (mới, US4): boolean, optional, mặc định `false` nếu
  không gửi (backward-compatible với client cũ chưa biết field này). Chỉ có
  hiệu lực khi `script_mode` là `translate`/`rewrite`; gửi kèm `script_mode:
  "subtitle"` không lỗi, chỉ bị bỏ qua (phụ đề đã luôn bật ở mode đó).

Response/status code giữ nguyên như 002 (`201`/`400`/`409`).

## GET /api/jobs/{job_id} (Job Detail — field mới)

Bổ sung vào Job Detail (xem [data-model.md](../data-model.md)):

```json
{
  "...": "...(các field cũ của 002 giữ nguyên)",
  "dynamic_captions": false,
  "subtitles_burned": false
}
```

- `dynamic_captions`: đúng giá trị đã chọn lúc submit job.
- `subtitles_burned`: `true` nếu Output Video đã có phụ đề burn-in (US3 luôn
  `true` khi `script_mode = subtitle`; US4 `true` khi `dynamic_captions =
  true` và burn thành công).

## GET /api/jobs (Job Summary)

Không đổi field — `script_mode` trả nguyên giá trị đã lưu (giờ có thể là
`"subtitle"`), frontend tự hiển thị nhãn tương ứng.

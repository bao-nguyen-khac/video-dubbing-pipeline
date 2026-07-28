# API Contract: /api/publish (006-publish-video-tab)

**Data model**: [../data-model.md](../data-model.md)

Mọi endpoint dưới đây nằm sau auth middleware hiện có (`web/backend/main.py`):
thiếu/hết hạn session ⇒ `401 {"error": "..."}`. Lỗi luôn có dạng
`{"error": "<tiếng Việt, nêu rõ nguyên nhân>"}`, có thể kèm field phụ — đồng
nhất với `_error()` của `jobs_api.py`.

Router mount tại prefix `/api/publish`.

---

## GET /api/publish/videos

Danh sách video có thể đăng (FR-002).

**200**

```json
{
  "videos": [
    {
      "job_id": "0ecd7793-…",
      "source_url": "https://www.tiktok.com/@…/video/763…",
      "created_at": "2026-07-26T04:10:17.196342+00:00",
      "duration_seconds": 47.2,
      "already_published_to": ["tiktok"]
    }
  ]
}
```

Chỉ chứa job `status=done` có `output_video` tồn tại; mới nhất trước.

---

## GET /api/publish/connections

Danh sách kênh đã liên kết, đã hợp nhất blocklist cục bộ (data-model §2).

**200**

```json
{
  "connections": [
    { "account_id": "acc_123", "platform": "tiktok",  "label": "@mychannel",  "status": "connected" },
    { "account_id": "acc_456", "platform": "youtube", "label": "My Channel",  "status": "expired" }
  ]
}
```

**502** — không gọi được Zernio:
`{"error": "Không kết nối được dịch vụ đăng bài (Zernio): …"}` (Edge Case
"dịch vụ trung gian gặp sự cố" — thông báo PHẢI nói rõ lỗi ở phía dịch vụ trung
gian, không phải lỗi video/tài khoản người dùng).

**503** — thiếu `ZERNIO_API_KEY` trong `.env`:
`{"error": "Chưa cấu hình ZERNIO_API_KEY — xem .env.example"}`.

---

## POST /api/publish/connections/{platform}

Bắt đầu liên kết kênh (FR-005). `platform` ∈ `tiktok` | `youtube`.

Trả URL OAuth để frontend mở cho người dùng cấp quyền trên chính nền tảng đích
(không có form nhập mật khẩu ở giao diện này).

**200** `{"authorize_url": "https://…"}`

**400** platform không hợp lệ · **502/503** như trên.

Sau khi người dùng hoàn tất OAuth và quay lại, frontend gọi lại
`GET /api/publish/connections` để lấy trạng thái mới; `account_id` vừa liên kết
lại được **gỡ khỏi** blocklist cục bộ nếu trước đó bị ngắt (FR-011).

---

## DELETE /api/publish/connections/{account_id}

Ngắt kết nối kênh (FR-011) — thêm vào blocklist cục bộ.

**200** `{"ok": true}` · **404** account không có trong danh sách của Zernio.

---

## POST /api/publish

Tạo 1 lượt đăng (FR-007). Xử lý thật chạy nền; endpoint trả ngay.

**Request**

```json
{
  "job_id": "0ecd7793-…",
  "platform": "tiktok",
  "account_id": "acc_123",
  "title": "Tiêu đề video"
}
```

**202** `{"attempt_id": "…", "status": "pending"}`

**Lỗi**

| Mã | Khi nào | Ví dụ `error` |
|---|---|---|
| `400` | `title` rỗng sau trim (FR-004) | `"Tiêu đề là bắt buộc"` |
| `400` | job không tồn tại / chưa `done` / không có output (FR-002) | `"Job chưa có video kết quả để đăng"` |
| `400` | vượt giới hạn nền tảng (research.md §7) | `"Video dài 245s, vượt giới hạn 180s của YouTube Shorts"` |
| `403` | `account_id` đang bị ngắt kết nối (FR-011) | `"Kênh đã bị ngắt kết nối, hãy liên kết lại trước khi đăng"` |
| `409` | đã có lượt đăng `pending`/`publishing` cho cùng job + platform (FR-009) | `{"error": "Video này đang được đăng lên nền tảng đã chọn", "attempt_id": "…"}` |
| `503` | thiếu `ZERNIO_API_KEY` | như trên |

---

## GET /api/publish/attempts

Lịch sử lượt đăng (FR-010), mới nhất trước.

**200**

```json
{
  "attempts": [
    {
      "attempt_id": "…",
      "job_id": "0ecd7793-…",
      "platform": "tiktok",
      "account_label": "@mychannel",
      "title": "Tiêu đề video",
      "status": "success",
      "error": null,
      "error_kind": null,
      "post_url": "https://www.tiktok.com/@mychannel/video/…",
      "created_at": "2026-07-27T09:00:00+00:00",
      "updated_at": "2026-07-27T09:01:12+00:00"
    }
  ]
}
```

Hỗ trợ lọc tuỳ chọn `?job_id=…`.

---

## GET /api/publish/attempts/{attempt_id}

Trạng thái 1 lượt đăng — frontend poll endpoint này trong lúc đăng (FR-007).

**200** cùng hình dạng 1 phần tử của `attempts` ở trên.

**404** `{"error": "Lượt đăng không tồn tại"}`

---

## Ánh xạ sang Zernio (nội bộ, không lộ ra frontend)

Toàn bộ nằm trong `publish/zernio_client.py` (research.md §2). Base URL
`https://zernio.com/api/v1`, header `Authorization: Bearer $ZERNIO_API_KEY`.

| Việc | Lời gọi |
|---|---|
| Liệt kê kênh | `GET /accounts` |
| URL liên kết | `GET /connect/{platform}?profileId=…` |
| Upload video | `POST /media` (multipart, field `file`) |
| Đăng công khai ngay | `POST /posts` với `publishNow: true`, media vừa upload, và chế độ hiển thị **công khai đặt tường minh**: YouTube `privacyStatus="public"` + `title`; TikTok mức công khai (`PUBLIC_TO_EVERYONE`) + caption = `title` (research.md §3) |
| Theo dõi | `GET /posts/{postId}` — poll tới khi `published` (⇒ `success`) hoặc `failed`/`partial`/`cancelled` (⇒ `failed`) |

Gửi kèm `Idempotency-Key: {attempt_id}` khi tạo bài đăng (research.md §4).

**Ánh xạ lỗi Zernio → `error_kind`** (SC-004):

| Zernio | `error_kind` | Thông báo cho người dùng nói về |
|---|---|---|
| `401` / `403` liên quan token kênh, `connected=false` | `auth_expired` | quyền truy cập kênh hết hạn → yêu cầu liên kết lại (FR-008) |
| `type=platform_error`, hoặc post `failed`/`partial` | `platform_rejected` | nền tảng từ chối, kèm nguyên nhân gốc nếu có |
| `429`, `5xx`, timeout, không kết nối được | `provider_unavailable` | sự cố phía dịch vụ trung gian |
| `402` (`free_tier_exceeded`…) | `limit_exceeded` | tài khoản Zernio hết hạn mức |
| lỗi mạng cục bộ khi upload | `network` | lỗi kết nối, thử lại được |
| còn lại | `unknown` | lỗi không xác định, kèm nguyên văn từ provider |

---

## Schema Zernio đã xác minh (2026-07-27, T001)

Nguồn: `https://zernio.com/openapi.yaml` (OpenAPI 3.1, Zernio API v1.0.4, tải
thật ngày 2026-07-27). Phần này **thay thế** mọi giả định trước đó ở research.md §2.

- **Base URL**: `https://zernio.com/api` — path đã bao gồm `/v1`, nên URL đầy đủ
  là `https://zernio.com/api/v1/...`
- **Auth**: `Authorization: Bearer $ZERNIO_API_KEY` (`securitySchemes.bearerAuth`)

### Khác biệt so với giả định ban đầu (QUAN TRỌNG)

| Giả định cũ | Thực tế |
|---|---|
| `POST /media` multipart rồi tham chiếu media id | **`POST /v1/media/presign`** → PUT file lên `uploadUrl` → dùng `publicUrl`. `mediaItems` nhận **URL**, không nhận id. (`/v1/media/upload-direct` có multipart nhưng giới hạn 25MB, dành cho inbox — KHÔNG dùng cho video) |
| Header `Idempotency-Key` | **`x-request-id`** (UUID, cửa sổ ~5 phút). Retry cùng id ⇒ HTTP 200 kèm `existingPost`, không tạo bài mới |
| — | **Dedup nội dung 24h**: cùng `(platform, accountId, content + media URL)` trong 24h ⇒ **409** kèm `details.existingPostId` — kể cả khi `x-request-id` khác |
| `profileId` tuỳ chọn | **Bắt buộc** ở `GET /v1/connect/{platform}` — lấy từ `GET /v1/profiles` (`profiles[]._id`, có `isDefault`) |
| Chưa rõ có endpoint ngắt kết nối | **Có**: `DELETE /v1/accounts/{accountId}` ("Disconnects and removes a connected social account") |
| Ngưỡng thời lượng TikTok hardcode | Lấy được từ `GET /v1/accounts/{accountId}/tiktok/creator-info` → `postingLimits.maxVideoDurationSec` (fallback 600s) |

### Lời gọi dùng trong feature này

| Việc | Lời gọi |
|---|---|
| Lấy profile | `GET /v1/profiles` → `{profiles: [{_id, name, isDefault}]}` |
| Liệt kê kênh | `GET /v1/accounts?platform=tiktok` → `{accounts: [{_id, platform, username, displayName, isActive, profileId}]}` |
| URL liên kết kênh | `GET /v1/connect/{platform}?profileId=…&redirect_url=…` → `{authUrl, state}`; sau OAuth, Zernio redirect kèm `connected={platform}&profileId=…&accountId=…&username=…` |
| Ngắt kết nối | `DELETE /v1/accounts/{accountId}` → `{message}` |
| Thông tin creator TikTok | `GET /v1/accounts/{accountId}/tiktok/creator-info?mediaType=video` → `{creator:{canPostMore}, privacyLevels:[{value,label}], postingLimits:{maxVideoDurationSec, interactionSettings}}` |
| Xin URL upload | `POST /v1/media/presign` body `{filename, contentType:"video/mp4", size}` → `{uploadUrl, publicUrl, key, expiresIn}` |
| Upload file | `PUT {uploadUrl}` với body là bytes video, header `Content-Type: video/mp4` (không kèm Authorization) |
| Đăng công khai ngay | `POST /v1/posts` (xem body bên dưới), header `x-request-id: {attempt_id}` |
| Theo dõi | `GET /v1/posts/{postId}` → `post.status ∈ draft\|scheduled\|publishing\|published\|failed\|partial`, `post.platforms[].platformPostUrl` |

### Body `POST /v1/posts` — TikTok video, công khai ngay

```json
{
  "content": "<tiêu đề người dùng nhập>",
  "mediaItems": [{ "type": "video", "url": "<publicUrl từ presign>", "mimeType": "video/mp4" }],
  "platforms": [{ "platform": "tiktok", "accountId": "<_id>" }],
  "publishNow": true,
  "tiktokSettings": {
    "privacyLevel": "PUBLIC_TO_EVERYONE",
    "allowComment": true,
    "allowDuet": true,
    "allowStitch": true,
    "contentPreviewConfirmed": true,
    "expressConsentGiven": true
  }
}
```

- `draft` **KHÔNG** được set (draft=true ⇒ vào Creator Inbox, không đăng công
  khai — trái SC-005).
- `allowDuet`/`allowStitch` bắt buộc với bài video.
- `privacyLevel` phải nằm trong `privacyLevels` trả về từ creator-info; nếu
  `PUBLIC_TO_EVERYONE` không có trong danh sách ⇒ báo lỗi trước khi đăng thay vì
  đăng nhầm chế độ riêng tư.

### Body `POST /v1/posts` — YouTube Shorts (Phase 4)

```json
{
  "content": "<mô tả>",
  "mediaItems": [{ "type": "video", "url": "…", "mimeType": "video/mp4" }],
  "platforms": [{
    "platform": "youtube",
    "accountId": "<_id>",
    "platformSpecificData": {
      "title": "<tiêu đề, ≤100 ký tự>",
      "privacyStatus": "public",
      "madeForKids": false
    }
  }],
  "publishNow": true
}
```

Video < 3 phút được YouTube tự nhận là Shorts (không có cờ `shorts` riêng).

### Response `POST /v1/posts` (201)

```json
{ "post": { "_id": "…", "status": "published",
            "platforms": [{ "platform": "tiktok", "status": "published",
                            "platformPostId": "…", "platformPostUrl": "https://…" }] },
  "message": "Post published successfully" }
```

Retry trùng `x-request-id` ⇒ **200** với `existingPost` thay vì 201.

### Mã lỗi thực tế → `error_kind`

| Zernio | `error_kind` |
|---|---|
| `401` | `auth_expired` (API key sai/hết hạn) |
| `403` + `code=ACCOUNT_DISCONNECTED` | `auth_expired` → yêu cầu liên kết lại kênh (FR-008) |
| `403` + `code=PROFILE_OVER_LIMIT`, `402` (`free_tier_exceeded`/`enterprise_required`) | `limit_exceeded` |
| `409` (dedup nội dung 24h, kèm `details.existingPostId`) | `duplicate_content` → nói rõ "nội dung này đã đăng lên kênh đó trong 24h qua" |
| `429` (kèm `Retry-After`), `5xx`, timeout, không kết nối được | `provider_unavailable` |
| `type=platform_error` (kèm `platformError`), post `failed`/`partial` | `platform_rejected` |
| lỗi mạng khi PUT file lên `uploadUrl` | `network` |
| còn lại | `unknown` |

Envelope lỗi chuẩn: `{error, type, code?, param?, platform?, platformError?}` với
`type ∈ invalid_request_error|authentication_error|permission_error|not_found|rate_limit_error|platform_error|api_error`.

# API Contracts: Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí (009)

**Ngày**: 2026-07-30 | **Plan**: [../plan.md](../plan.md) | **Kiểu dữ liệu**: [../data-model.md](../data-model.md)

Không thêm endpoint mới — tính năng này MỞ RỘNG các endpoint đã có ở feature
001 (`POST /api/jobs`) và feature 008 (`GET`/`PUT /api/jobs/{id}/review`). Quy
ước lỗi/response giữ nguyên như các feature trước (`{"error": "..."}`).

---

## 1. `POST /api/jobs` — mở rộng (FR-001, FR-002, FR-004)

Thêm 2 field vào `SubmitJobRequest`:

| Field | Type | Default | Ghi chú |
|---|---|---|---|
| `hardsub_blur_enabled` | `bool` | `false` | Bật tính năng. **Mặc định TẮT** (FR-002) |
| `hardsub_no_ranges` | `string \| null` | `null` | Khoảng thời gian KHÔNG có phụ đề gốc — chỉ có ý nghĩa khi `hardsub_blur_enabled=true`. Sai định dạng bị bỏ qua khi parse, không lỗi request (FR-010, giống `keep_original_ranges`) |

Không đổi response (`201 {"job_id": "..."}`). Client cũ không gửi 2 field này
vẫn chạy như trước (SC-006).

## 2. `GET /api/jobs/{job_id}/review` — mở rộng (FR-012)

Chỉ áp dụng ở `gate == "transcript"` **và** job có `hardsub_blur_enabled=true`
**và** `supervised=true` (data-model.md §4). Thêm field `hardsub_regions`:

```json
{
  "job_id": "...",
  "gate": "transcript",
  "editable_field": "text",
  "segments": [ /* ... như feature 008, không đổi ... */ ],
  "hardsub_regions": [
    {
      "index": 0,
      "start": 3.0,
      "end": 26.0,
      "detected": true,
      "excluded": false,
      "box": { "x": 120, "y": 540, "w": 400, "h": 90 }
    },
    {
      "index": 1,
      "start": 26.0,
      "end": 40.0,
      "detected": false,
      "excluded": false,
      "box": null
    }
  ]
}
```

- `detected: false` → tương ứng US3 (không xác định được vị trí) — client hiển
  thị rõ "không xác định được", vẫn cho phép người dùng đánh dấu `excluded` nếu
  muốn (dù không có box để xem trước).
- Field `hardsub_regions` **vắng mặt hoàn toàn** (không phải mảng rỗng) khi
  tính năng tắt hoặc job không supervised — client dựa vào `"hardsub_regions" in
  payload` để quyết định có hiện mục này hay không.

## 3. `PUT /api/jobs/{job_id}/review` — mở rộng (FR-012, data-model.md §5)

Thêm field tuỳ chọn `hardsub_overrides` vào body hiện có (`gate`, `segments`):

```json
{
  "gate": "transcript",
  "segments": [ /* ... như feature 008, có thể rỗng nếu chỉ sửa hardsub ... */ ],
  "hardsub_overrides": [
    { "index": 1, "excluded": true }
  ]
}
```

- Chỉ hỗ trợ `excluded: true` — không có luồng bỏ đánh dấu (Assumption ở
  data-model.md §5). Gửi `excluded: false` bị bỏ qua im lặng (không có tác
  dụng, không lỗi).
- `index` không tồn tại trong `hardsub_regions.json` → **400** cùng dạng lỗi đã
  có ở FR-013/008 (`{"error": "Vùng phụ đề gốc số <i> không tồn tại"}`).
- Response **200** giữ nguyên shape hiện có (`saved_count`, `dropped_count`),
  thêm field `hardsub_excluded_count`:

```json
{ "job_id": "...", "gate": "transcript", "saved_count": 6, "dropped_count": 0, "hardsub_excluded_count": 1 }
```

`hardsub_excluded_count` chỉ xuất hiện khi request có gửi `hardsub_overrides`.

**Lỗi** (thêm vào bảng lỗi đã có ở feature 008, contracts/api.md §3 của
008-supervised-pipeline):

| Code | Khi nào | Body |
|---|---|---|
| 400 | `index` trong `hardsub_overrides` không tồn tại | `{"error": "Vùng phụ đề gốc số <i> không tồn tại"}` |
| 400 | job không bật `hardsub_blur_enabled` nhưng request có `hardsub_overrides` | `{"error": "Job không bật tính năng làm mờ phụ đề gốc"}` |

## 4. `GET /api/jobs/{job_id}` — mở rộng (data-model.md §6)

Thêm field `hardsub_blur_enabled: bool` vào Job Detail. Không đổi Job Summary
(`GET /api/jobs`).

## 5. CLI (`pipeline.py`) — flag thêm

```text
--hardsub-blur          Bật làm mờ phụ đề gốc + chèn phụ đề mới đúng vị trí.
                         Chỉ có tác dụng với chế độ có hiển thị phụ đề
                         (subtitle, hoặc translate/rewrite kèm --dynamic-captions).
--hardsub-no-ranges TEXT Khoảng thời gian KHÔNG có phụ đề gốc, cú pháp giống
                         --keep-original-ranges (VD "0:00-0:08, 0:15-end").
                         Chỉ có ý nghĩa khi --hardsub-blur được bật.
```

Đánh dấu "không có phụ đề gốc" tại chốt kiểm duyệt **chỉ làm được qua web UI**
(giống mọi thao tác duyệt khác của 008) — CLI không có flag tương đương.

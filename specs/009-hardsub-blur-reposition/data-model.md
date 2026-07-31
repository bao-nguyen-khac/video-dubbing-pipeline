# Data Model: Làm mờ phụ đề gốc và chèn phụ đề mới đúng vị trí (009)

**Ngày**: 2026-07-30 | **Plan**: [plan.md](./plan.md) | **Quyết định nền**: [research.md](./research.md)

Không có database. Toàn bộ state nằm trong file JSON dưới `jobs/{job_id}/`, kế
thừa đúng cách feature 008 đã làm. Tài liệu này chỉ ghi phần **thêm/đổi**; mọi
field không nhắc tới giữ nguyên.

---

## 1. `jobs/{job_id}/job.json` — field thêm

| Field | Type | Default | Ghi chú |
|---|---|---|---|
| `hardsub_blur_enabled` | `bool` | `false` | Bật tính năng làm mờ phụ đề gốc. Đặt lúc `create_job()` (FR-001/002) |
| `hardsub_no_ranges` | `string \| null` | `null` | Chuỗi khoảng thời gian KHÔNG có phụ đề gốc, cùng cú pháp `keep_original_ranges` (VD `"0:00-0:08, 0:15-end"`) — field ĐỘC LẬP, không dùng chung giá trị (FR-004). **Có thể được nối thêm sau lúc tạo job**, tại chốt lời thoại nếu job cũng bật `supervised` (FR-012, research.md §7) |
| `artifacts.hardsub_regions` | `string \| null` | `null` | Đường dẫn `hardsub_regions.json`. Chỉ khác `null` khi `hardsub_blur_enabled=true` |

**Bất biến**:

- `hardsub_blur_enabled == false` ⟹ `hardsub_no_ranges == null` và
  `artifacts.hardsub_regions == null` (SC-006 — job không bật không thêm field
  gì có tác dụng).
- Việc bật/tắt CHỈ chọn được lúc tạo job (FR-001); `hardsub_no_ranges` là
  NGOẠI LỆ duy nhất được sửa sau khi tạo — qua chốt kiểm duyệt (nếu có), không
  qua API job thường.

## 2. `jobs/{job_id}/hardsub_regions.json` (MỚI)

Artifact trung gian — cả kết quả phát hiện lẫn đầu vào thật của bước blur+burn
ở merging. Ghi MỘT LẦN (idempotent — bỏ qua nếu đã tồn tại, giống
`generate_script()`), sau đó chỉ field `excluded` của từng entry có thể bị sửa
(qua chốt kiểm duyệt — research.md §7).

```json
{
  "total_duration": 26.0,
  "no_hardsub_ranges": [[0.0, 3.0]],
  "regions": [
    {
      "index": 0,
      "start": 3.0,
      "end": 26.0,
      "detected": true,
      "excluded": false,
      "box": { "x": 120, "y": 540, "w": 400, "h": 90 },
      "frame_size": { "width": 630, "height": 1122 },
      "confidence": 0.87
    }
  ]
}
```

| Field | Ghi chú |
|---|---|
| `total_duration` | Độ dài video (giây) tại thời điểm phát hiện — dùng để tái tính `no_hardsub_ranges` nếu cần đối chiếu, không tính lại mỗi lần đọc |
| `no_hardsub_ranges` | Kết quả `parse_time_ranges(job["hardsub_no_ranges"], total_duration)` tại thời điểm phát hiện — đóng băng lại, không tính động mỗi lần đọc file |
| `regions[]` | Danh sách đoạn **CÓ phụ đề gốc** (complement của `no_hardsub_ranges` trong `[0, total_duration]` — research.md, `hardsub/ranges.py`) |
| `regions[].index` | 0-based, khoá định danh khi đánh dấu "không có phụ đề gốc" qua chốt kiểm duyệt |
| `regions[].detected` | `true` nếu tìm được vùng hợp lệ (research.md §3–§5); `false` = US3 (không tìm thấy trong cả 3 khung hình thử) |
| `regions[].excluded` | `true` nếu người dùng đã đánh dấu lại là "không có phụ đề gốc" tại chốt kiểm duyệt (research.md §7). Bước merging bỏ qua entry có `excluded=true` dù `detected=true` |
| `regions[].box` | `null` nếu `detected=false`. Toạ độ pixel `x,y` (góc trên-trái) + `w,h`, đã gộp cụm (research.md §4) |
| `regions[].frame_size` | Kích thước khung hình đại diện lúc phát hiện — để đối chiếu nếu cần, KHÔNG dùng để scale lại (video không đổi kích thước giữa các bước) |
| `regions[].confidence` | Độ tin cậy OCR trung bình của cụm đã gộp (0–1). Không phải ngưỡng quyết định "có/không nền hộp" (đó là quyết định nhị phân riêng, xem research.md §3) — chỉ để chọn cụm tốt nhất khi có ≥2 cụm hợp lệ (research.md §4) |

## 3. `jobs/{job_id}/subtitles.ass` (MỚI — thay `subtitles.srt` khi tính năng bật)

Sinh bởi `merge/subtitle_burner.py::write_ass()`. Mỗi dòng thoại tương ứng 1 cue
từ `script.json.segments`. Dòng nào có mốc thời gian **giao với** một
`regions[]` entry có `detected=true` và `excluded=false` → thêm override
`{\pos(x,y)\fs<cỡ nhỏ hơn>}` ngay đầu nội dung dòng đó, toạ độ lấy TỪ
`regions[].box` (research.md §1–§2). Dòng không giao với vùng nào → giữ nguyên,
không override — dùng đúng style mặc định hiện có (`Alignment=2, FontSize=16...`
từ `merge/subtitle_burner.py`, không đổi).

## 4. Review Payload (chốt lời thoại, `GET /api/jobs/{job_id}/review`) — field thêm

Chỉ xuất hiện khi `job.hardsub_blur_enabled == true` **và** job cũng
`supervised == true` (FR-012; nếu `supervised == false` thì hoàn toàn tự động,
không có payload này — FR-013).

| Field | Type | Ghi chú |
|---|---|---|
| `hardsub_regions` | `array \| omitted` | Danh sách rút gọn từ `hardsub_regions.json.regions` — `index`, `start`, `end`, `detected`, `excluded`, `box` (không có `frame_size`/`confidence`, không cần thiết cho UI) |

## 5. Lưu bản sửa (chốt lời thoại, `PUT /api/jobs/{job_id}/review`) — field thêm

| Field | Type | Ghi chú |
|---|---|---|
| `hardsub_overrides` | `array \| omitted` | `[{ "index": int, "excluded": true }]` — chỉ hỗ trợ đánh dấu `excluded=true` (không hỗ trợ bỏ đánh dấu ở v1, khớp Assumption "chỉ thêm khoảng không có phụ đề gốc", không có luồng gỡ) |

Khi có `hardsub_overrides`, xử lý (research.md §7):

1. Với mỗi override, đặt `regions[index].excluded = true` trong `hardsub_regions.json`.
2. Nối khoảng `[start, end]` tương ứng vào `job["hardsub_no_ranges"]` (dùng
   đúng cú pháp chuỗi, nối bằng dấu phẩy).

Đây là thao tác ĐỘC LẬP với việc lưu nội dung câu transcript (segments) — cùng
gửi trong một lượt `PUT`, nhưng không phụ thuộc lẫn nhau.

## 6. Job Detail (API hiện có) — field thêm

| Field | Ghi chú |
|---|---|
| `hardsub_blur_enabled` | Hiển thị job có bật tính năng này |

Không thêm vào Job Summary (danh sách job) — không cần thiết cho danh sách,
đúng khuôn mẫu `keep_original_ranges` hiện tại (chỉ có ở Detail).

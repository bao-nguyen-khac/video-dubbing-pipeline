# Data Model: Tạo video từ chủ đề bằng AI

## 1. GenerateJob (`jobs/{job_id}/job.json`, `job_type="generate"`)

Cùng file `job.json` như luồng dub hiện có, phân biệt bằng field
`job_type` — job cũ (không có field này) MẶC ĐỊNH coi là `"dub"`, không cần
migrate dữ liệu cũ.

| Field | Type | Ghi chú |
|---|---|---|
| `job_id` | string | Giống hệt luồng dub |
| `job_type` | `"dub"` \| `"generate"` | MỚI. Vắng mặt = `"dub"` (tương thích ngược) |
| `topic` | string | Chủ đề văn bản người dùng nhập (thay cho `source_url`) |
| `supervised` | bool | Tái dùng nguyên field/khái niệm đã có (008) — bật thì dừng ở `GATE_OUTLINE` |
| `status` | enum (§3) | State machine RIÊNG, không dùng chung enum với luồng dub |
| `review_gate` | `"outline"` \| `null` | Tái dùng field/cơ chế `review/gates.py` |
| `review_gates` | dict | Tái dùng nguyên (`{"outline": {reached_at, approved_at, edited, segment_count}}`) |
| `artifacts.outline` | path \| null | `outline.json` |
| `artifacts.scenes` | path \| null | `scenes.json` — cũng là file gate `GATE_OUTLINE` |
| `artifacts.output_video` | path \| null | `output.mp4` |
| `error` | string \| null | Giống luồng dub |

**Không có** các field đặc thù dub: `source_url`, `platform`,
`dynamic_captions`, `hardsub_blur_enabled`, `keep_original_ranges`,
`tts_provider`/`voice_id` ở CẤP JOB (chọn giọng có thể vẫn cần — xem §2 Scene,
để mỗi scene tự chọn hoặc dùng 1 giọng chung mặc định `edge-tts`).

## 2. Outline (`jobs/{job_id}/outline.json`)

```json
{
  "topic": "tổng quan về các loại tiền tệ",
  "search_used": true,
  "sections": [
    {"title": "Mở đầu", "key_points": ["..."]},
    {"title": "Tiền pháp định vs tiền hàng hoá", "key_points": ["...", "..."]},
    {"title": "Kết", "key_points": ["..."]}
  ]
}
```

- `search_used`: true nếu bước tra cứu web (research.md §3) thành công ít
  nhất 1 lần cho topic này — dùng để hiển thị ở UI review gate (FR-003/SC-004)
  và audit (Constitution VI: truy vết quyết định bước trước).
- Không lưu raw search results — chỉ lưu outline đã tổng hợp, tránh phình file
  (Token & Context Economy áp dụng cả cho artifact, không chỉ code).

## 3. Scene JSON (`jobs/{job_id}/scenes.json`) — cũng là file `GATE_OUTLINE`

```json
{
  "source": "outline.json",
  "scenes": [
    {
      "index": 0,
      "type": "hook",
      "section_title": null,
      "narration_text": "Tiền tệ đã tồn tại hàng nghìn năm...",
      "image_query": "ancient coins currency history",
      "image_path": null,
      "voice_path": null,
      "duration": null
    }
  ]
}
```

| Field | Type | Set ở bước nào |
|---|---|---|
| `index` | int | Sinh kịch bản (thứ tự cố định, KHÔNG đổi sau khi tạo) |
| `type` | enum: `"hook"` \| `"concept"` \| `"transition"` \| `"fact"` \| `"outro"` | Sinh kịch bản — vai trò hiển thị của scene, chọn template render tương ứng (merge/hyperframes_renderer.py). `scenes[0]` LUÔN `"hook"`, `scenes[-1]` LUÔN `"outro"` (không editable ở v1) |
| `section_title` | string \| null | Sinh kịch bản — denormalize từ `outline.sections[section_index].title` (chỉ có ở type `concept`/`transition`/`fact`; `null` ở `hook`/`outro`). Không editable ở v1 |
| `narration_text` | string | Sinh kịch bản — field EDITABLE ở `GATE_OUTLINE` (review/gates.py) |
| `image_query` | string | Sinh kịch bản — từ khoá tiếng Anh để search Pexels (không editable ở v1) |
| `image_path` | path \| null | Bước `sourcing_assets` (research.md §4) |
| `voice_path` | path \| null | Bước `synthesizing` (research.md §6) |
| `duration` | float (giây) \| null | Bước `synthesizing` — đo THẬT từ `voice_path`, không phải ước lượng |

**Lifecycle của `duration`**: `null` cho tới khi TTS chạy xong scene đó — đây
là điểm khác biệt quan trọng với `Script`/`Scene` mô tả trong spec.md (spec
không đi vào chi tiết field-level, chỉ nói "khoảng thời gian hiển thị" ở mức
khái niệm; data-model này cụ thể hoá: không có ước lượng trung gian, chỉ có
`null` → giá trị thật).

**Bất biến khi qua `GATE_OUTLINE`** (nếu `supervised=true`): người dùng chỉ
sửa được `narration_text` từng scene (đúng `EDITABLE_FIELD["outline"]`,
research.md §7) — không thêm/xoá scene, không sửa `image_query` ở v1 (đủ đơn
giản để tái dùng `save_edits()` nguyên vẹn theo index cố định, giống hệt
`GATE_SCRIPT` hiện có chỉ cho sửa `translated_text`).

## 4. Generated Video (`jobs/{job_id}/output.mp4`)

File MP4 cuối cùng — không có metadata riêng ngoài `job.json.artifacts.output_video`
trỏ tới, giống hệt luồng dub.

## 5. State Machine (`job.json.status`, chỉ áp dụng khi `job_type="generate"`)

```text
pending → outlining → scripting → [awaiting_review nếu supervised, chốt "outline"]
        → sourcing_assets → synthesizing → rendering → done
                                                       ↘ failed (từ bất kỳ bước nào)
```

| Status | Việc xảy ra | Artifact ghi ra |
|---|---|---|
| `pending` | Job vừa tạo, chưa chạy | — |
| `outlining` | Viết outline + tra cứu web (research.md §3) | `outline.json` |
| `scripting` | Viết kịch bản chi tiết, chia scene | `scenes.json` (chưa có `image_path`/`voice_path`/`duration`) |
| `awaiting_review` | CHỈ khi `supervised=true` — dừng ở `GATE_OUTLINE` | — (chờ `POST /review/approve`) |
| `sourcing_assets` | Search Pexels cho từng scene (research.md §4) | `scenes.json` cập nhật `image_path` mỗi scene |
| `synthesizing` | TTS từng scene + đo duration thật (research.md §6) | `scenes.json` cập nhật `voice_path`/`duration` mỗi scene |
| `rendering` | Sinh `render.html` + `npx hyperframes render` (research.md §5) | `output.mp4` |
| `done` | Xong | — |
| `failed` | Lỗi ở bất kỳ bước nào | `job.json.error` |

**Resume/retry**: cần 1 hàm tương đương `status_from_artifacts()` riêng cho
`job_type="generate"`, suy theo thứ tự artifact ở bảng trên (khác hoàn toàn
`RERUN_STEPS` của luồng dub — không dùng chung).

## 6. Quan hệ với entity đã có trong spec.md

| spec.md (khái niệm nghiệp vụ) | data-model.md (field/file thật) |
|---|---|
| Topic Request | `job.json.topic` |
| Script | `outline.json` (cấu trúc) + `scenes.json.scenes[].narration_text` (nội dung ghép lại theo thứ tự) |
| Scene | 1 phần tử `scenes.json.scenes[]` |
| Generated Video | `output.mp4` |

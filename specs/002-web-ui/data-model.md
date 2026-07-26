# Phase 1 Data Model: Web UI cho Video Repurpose Pipeline

Nguồn: mục "Key Entities" của [spec.md](./spec.md). Không có entity lưu trữ mới
— toàn bộ dữ liệu vẫn là `jobs/{job_id}/job.json` đã định nghĩa ở
[data-model.md của 001](../001-video-repurpose-pipeline/data-model.md#job).
Tài liệu này chỉ định nghĩa các **view/response shape** mà backend trả về cho
frontend, dẫn xuất từ `Job` entity gốc.

## Job Summary (dùng cho danh sách job — US2)

Rút gọn từ `Job` gốc, dùng cho `GET /api/jobs`.

| Field | Type | Nguồn |
|---|---|---|
| `job_id` | string | `Job.job_id` |
| `source_url` | string | `Job.source_url` |
| `platform` | enum | `Job.platform` |
| `status` | enum | `Job.status` |
| `progress_percent` | int (0-100) | Suy ra từ `Job.status` (xem research.md) |
| `created_at` | ISO datetime | `Job.created_at` |

## Job Detail (dùng cho trang chi tiết — US2/US3)

Job Summary + các field sau, dùng cho `GET /api/jobs/{job_id}`.

| Field | Type | Nguồn |
|---|---|---|
| `script_mode` | enum | `Job.script_mode` |
| `error` | string \| null | `Job.error` |
| `warnings` | object | `Job.warnings` (watermark, duration_mismatch, background_music_lost) |
| `output_video_url` | string \| null | Suy ra từ `Job.artifacts.output_video`, null nếu chưa có — link tới `GET /api/jobs/{job_id}/output` |
| `can_retry` | bool | `True` khi `status == "failed"` |

## Session (đăng nhập — FR-010)

Không lưu trữ persistent — session là 1 signed token (`itsdangerous`) chứa:

| Field | Type | Ghi chú |
|---|---|---|
| `username` | string | Khớp `WEB_UI_USERNAME` từ `.env` |
| `issued_at` | timestamp | Dùng để tính hạn 7 ngày khi verify |

## Relationships

```text
Job (001, nguồn sự thật) ──derive──> Job Summary ──derive──> Job Detail
                                            │
                                            └──derive──> progress_percent (research.md)
```

Web UI không sở hữu dữ liệu — mọi response đều derive real-time từ
`jobs/{job_id}/job.json` tại thời điểm request, không cache/đồng bộ lệch pha.

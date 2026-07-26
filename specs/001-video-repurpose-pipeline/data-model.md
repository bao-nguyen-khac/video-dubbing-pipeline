# Phase 1 Data Model: Video Repurpose Pipeline

Nguồn: mục "Key Entities" của [spec.md](./spec.md). Không dùng database — mỗi entity
là một phần của file `jobs/{job_id}/job.json` hoặc file riêng cùng thư mục job (xem
Constitution → Project Structure).

## Job

Đại diện một lần chạy pipeline cho một video.

| Field | Type | Ghi chú |
|---|---|---|
| `job_id` | string (UUID) | Định danh duy nhất, cũng là tên thư mục `jobs/{job_id}/` |
| `source_url` | string | URL người dùng nhập |
| `platform` | enum: `tiktok`, `douyin`, `youtube` | Suy ra từ `source_url` |
| `script_mode` | enum: `translate`, `rewrite` | Theo FR-004, người dùng chọn trước khi chạy |
| `status` | enum (xem State Transitions) | Trạng thái hiện tại |
| `error` | string \| null | Thông điệp lỗi nếu `status = failed`, chỉ rõ bước nào lỗi (FR-008) |
| `created_at` / `updated_at` | ISO 8601 datetime | Audit trail (Constitution Principle VI) |

**State Transitions** (tuần tự, không rẽ nhánh song song ở MVP):

```text
pending → downloading → transcribing → scripting → synthesizing → merging → done
                                                                            ↘ failed (từ bất kỳ bước nào)
```

- Chuyển trạng thái chỉ tiến, không lùi.
- `failed` có thể xảy ra ở bất kỳ bước nào; khi đó `error` MUST được set và các file
  trung gian đã tạo trước đó MUST được giữ nguyên (FR-007, Constitution Principle VI).

## Source Video

| Field | Type | Ghi chú |
|---|---|---|
| `file_path` | string | `jobs/{job_id}/source.mp4` |
| `platform` | enum | Trùng với `Job.platform` |
| `has_watermark_warning` | bool | Set bởi `clean_video/detector.py` (xem Constitution Principle III) |
| `transcript` | string \| null | Nội dung/lời thoại trích xuất; null nếu video không có lời thoại (edge case trong spec) |
| `transcript_path` | string | `jobs/{job_id}/transcript.json` (gồm transcript + timestamp segment nếu có) |

## Script

| Field | Type | Ghi chú |
|---|---|---|
| `mode` | enum: `translate`, `rewrite` | Trùng `Job.script_mode` |
| `content` | string | Nội dung kịch bản dùng để sinh voice |
| `file_path` | string | `jobs/{job_id}/script.json` |
| `target_language` | string | Mặc định `vi` (tiếng Việt) theo spec Assumptions |

## Voice Track

| Field | Type | Ghi chú |
|---|---|---|
| `file_path` | string | `jobs/{job_id}/voice.wav` |
| `voice_name` | string | VD `vi-VN-NamMinhNeural` (xem research.md) |
| `duration_seconds` | float | Dùng để so sánh với thời lượng video gốc (cảnh báo lệch, edge case trong spec) |
| `rate_adjustment` | string | Tham số `rate` edge-tts dùng ở lượt sinh cuối (VD `+12%`), `+0%` nếu không cần chỉnh (FR-010) |

## Background Audio

| Field | Type | Ghi chú |
|---|---|---|
| `file_path` | string \| null | `jobs/{job_id}/background.wav`; null nếu Demucs tách thất bại (edge case trong spec) |
| `separation_failed` | bool | True nếu Demucs lỗi — khi đó Output Video fallback mute audio gốc như hành vi cũ |

## Output Video

| Field | Type | Ghi chú |
|---|---|---|
| `file_path` | string | `jobs/{job_id}/output.mp4` |
| `duration_mismatch_warning` | bool | True nếu sau khi áp dụng `rate_adjustment` vẫn còn lệch đáng kể so với video gốc |
| `watermark_warning` | bool | Trùng `Source Video.has_watermark_warning`, truyền tiếp ra output để người dùng biết |
| `background_music_kept` | bool | True nếu audio output = Voice Track trộn Background Audio; False nếu fallback mute toàn bộ (Demucs lỗi) |

## Relationships

```text
Job (1) ── (1) Source Video ── (1) Script ── (1) Voice Track ──┐
                            └── (1) Background Audio ──────────┴── (1) Output Video
```

Quan hệ 1-1 tuyến tính trong MVP (US1). US2/US3 (mở rộng nguồn, thêm mode script)
không đổi cấu trúc quan hệ, chỉ mở rộng giá trị hợp lệ của `platform`/`script_mode`.

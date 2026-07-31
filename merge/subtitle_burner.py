"""
merge/subtitle_burner.py — Ghi cứng (burn-in) phụ đề vào video bằng ffmpeg.

Dùng chung cho:
- script_mode = "subtitle" (US3, 003-dubbing-fixes-subtitles): cue lấy từ
  Script.segments (dịch sát nghĩa theo mốc thời gian ASR gốc).
- dynamic_captions = true (US4): cue lấy từ Voice Track.word_boundaries (gom
  theo câu/cụm từ sự kiện WordBoundary của edge-tts).

Chữ được VẼ SẴN thành ảnh PNG bằng Pillow (`merge/text_renderer.py`) rồi
`overlay` vào video — KHÔNG dùng bộ lọc `subtitles`/libass của ffmpeg nữa, vì
bộ lọc đó không tồn tại trên nhiều bản ffmpeg phổ biến (xem docstring của
text_renderer.py). `write_srt()` vẫn giữ để xuất file .srt kèm theo trong thư
mục job (tiện tra cứu/ghép thủ công), không còn dùng để burn.

Burn-in bắt buộc re-encode video (không dùng -c:v copy được nữa khi có filter
video) — xem research.md §7.

009-hardsub-blur-reposition: `apply_hardsub_blur()` làm mờ vùng phụ đề gốc,
chạy TRƯỚC bước burn; vị trí/cỡ chữ riêng cho từng dòng rơi vào vùng đó do
`text_renderer.render_cue_overlays()` tính.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Mức mờ áp cho vùng phụ đề gốc. boxblur=<n> (không đặt tên) gán CÙNG giá trị
# cho cả luma_radius VÀ chroma_radius — nhưng chroma_radius giới hạn thấp hơn
# (< 9) so với luma_radius (< 18) trên ffmpeg 8.1.2 (xác nhận thật, lỗi
# "Invalid chroma_param radius value"), nên MUST dùng tham số có tên riêng.
_BLUR_LUMA_RADIUS = 15
_BLUR_CHROMA_RADIUS = 8


def _format_srt_timestamp(seconds: float) -> str:
    """Chuyển giây (float) sang định dạng timestamp SRT: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(cues: list[dict], srt_path: str | Path) -> Path:
    """
    Sinh file .srt chuẩn từ danh sách cue {start, end, text} (giây).

    Args:
        cues: List[{"start": float, "end": float, "text": str}], đã sắp xếp
            theo thời gian tăng dần.
        srt_path: Đường dẫn file .srt sẽ ghi ra.

    Returns:
        Path tới file .srt vừa ghi.

    Raises:
        RuntimeError: Nếu cues rỗng — không có gì để burn.
    """
    srt_path = Path(srt_path)

    if not cues:
        raise RuntimeError("Danh sách cue rỗng — không có nội dung để tạo phụ đề")

    lines = []
    for i, cue in enumerate(cues, start=1):
        text = cue["text"].strip()
        if not text:
            continue
        start_ts = _format_srt_timestamp(cue["start"])
        end_ts = _format_srt_timestamp(cue["end"])
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def apply_hardsub_blur(
    video_path: str | Path,
    output_path: str | Path,
    regions: list[dict],
) -> Path:
    """
    Làm mờ đúng vùng phụ đề gốc trong đúng khoảng thời gian tương ứng
    (research.md §2) — chain `split → crop → boxblur → overlay:enable=` cho
    MỖI vùng, nối tiếp nhau. Chạy 1 pass ffmpeg riêng, TRƯỚC bước burn phụ đề.

    Args:
        regions: TOÀN BỘ vùng (kể cả `detected=false`/`excluded=true`) — hàm tự
            lọc lấy vùng dùng được, chỗ gọi không cần lọc trước.

    Returns:
        Path tới output_path. Nếu không có vùng nào dùng được, COPY nguyên
        video_path sang output_path (no-op, không gọi ffmpeg).

    Raises:
        RuntimeError: Nếu ffmpeg lỗi hoặc không tạo được output hợp lệ.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)

    usable = [r for r in regions if r["detected"] and not r["excluded"]]
    if not usable:
        shutil.copy2(video_path, output_path)
        return output_path

    filter_parts = []
    base = "[0:v]"
    for i, region in enumerate(usable):
        box = region["box"]
        next_base = f"[base{i}]"
        region_in = f"[region_in{i}]"
        blurred = f"[blurred{i}]"

        filter_parts.append(f"{base}split=2{next_base}{region_in}")
        filter_parts.append(
            f"{region_in}crop={box['w']}:{box['h']}:{box['x']}:{box['y']},"
            f"boxblur=luma_radius={_BLUR_LUMA_RADIUS}:chroma_radius={_BLUR_CHROMA_RADIUS}{blurred}"
        )

        is_last = i == len(usable) - 1
        out_label = "[outv]" if is_last else f"[base{i}_out]"
        filter_parts.append(
            f"{next_base}{blurred}overlay={box['x']}:{box['y']}:"
            f"enable='between(t,{region['start']:.3f},{region['end']:.3f})'{out_label}"
        )
        base = out_label

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-map_metadata", "-1",
        # Ép format MP4 tường minh — không dựa vào đuôi file để đoán, vì
        # output_path là file tạm "output_blurred.mp4.tmp" (đuôi thật là
        # ".tmp"), khiến ffmpeg lỗi "Invalid argument"/"Error initializing the
        # muxer" (cùng bug đã sửa ở burn_subtitles(), chỉ khác chỗ chưa vá).
        "-f", "mp4",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg làm mờ vùng phụ đề gốc thất bại (exit {result.returncode}):\n"
            f"{result.stderr[-500:]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg không tạo được output hợp lệ sau khi làm mờ")

    return output_path


def burn_subtitles(
    video_path: str | Path,
    overlays: list[dict],
    output_path: str | Path,
    audio_path: str | Path | None = None,
) -> Path:
    """
    Burn-in phụ đề bằng cách `overlay` các ảnh PNG đã vẽ sẵn vào video, mỗi ảnh
    chỉ hiện trong đúng khoảng thời gian của cue tương ứng (`enable=between`).

    KHÔNG dùng bộ lọc `subtitles`/libass — xem docstring đầu module và
    `merge/text_renderer.py` về lý do (libass không có sẵn trên nhiều bản
    ffmpeg, gây fail toàn bộ việc burn dù code đúng).

    Args:
        video_path: Video nguồn để lấy video stream (và audio stream nếu
            audio_path=None).
        overlays: Kết quả `text_renderer.render_cue_overlays()` —
            [{"image", "x", "y", "start", "end"}].
        output_path: Đường dẫn output.mp4 sẽ ghi ra.
        audio_path: Nếu khác None, dùng audio từ file này thay vì audio có
            sẵn trong video_path (VD dùng cho US4: video_path là output đã
            ghép voice+nhạc nền, audio đã đúng sẵn nên audio_path=None; US3
            audio_path cũng None vì audio gốc nằm sẵn trong source.mp4).

    Returns:
        Path tới output_path.

    Raises:
        RuntimeError: Nếu ffmpeg lỗi hoặc không tạo được output hợp lệ. Việc
            fail job hay chỉ cảnh báo khi lỗi là quyết định của caller (US3
            fail job, US4 chỉ cảnh báo — xem tasks.md T017/T022).
    """
    video_path = Path(video_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise RuntimeError(f"Video nguồn không tồn tại: {video_path}")
    if not overlays:
        raise RuntimeError("Không có dòng phụ đề nào để burn")

    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    for overlay in overlays:
        cmd += ["-i", str(overlay["image"])]

    audio_input_index = len(overlays) + 1
    if audio_path is not None:
        cmd += ["-i", str(audio_path)]

    # Chuỗi overlay nối tiếp: [0:v] + ảnh 1 → [v1] + ảnh 2 → [v2] ... → [outv]
    filter_parts = []
    base = "[0:v]"
    for i, overlay in enumerate(overlays):
        out_label = "[outv]" if i == len(overlays) - 1 else f"[v{i + 1}]"
        filter_parts.append(
            f"{base}[{i + 1}:v]overlay={overlay['x']}:{overlay['y']}:"
            f"enable='between(t,{overlay['start']:.3f},{overlay['end']:.3f})'{out_label}"
        )
        base = out_label

    cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[outv]"]
    cmd += ["-map", f"{audio_input_index}:a:0" if audio_path is not None else "0:a:0"]
    cmd += [
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map_metadata", "-1",
        "-movflags", "+faststart",
        # Ép format MP4 tường minh — không dựa vào đuôi file để đoán, vì
        # output_path có thể là file tạm không có đuôi ".mp4" chuẩn (VD
        # "*.mp4.tmp" ở US4), khiến ffmpeg lỗi "Unable to choose an output
        # format" (bug thật phát hiện lúc verify US4)
        "-f", "mp4",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg burn phụ đề thất bại (exit {result.returncode}):\n"
            f"{result.stderr[-500:]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg không tạo được output hợp lệ sau khi burn phụ đề")

    return output_path

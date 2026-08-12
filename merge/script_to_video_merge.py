"""
merge/script_to_video_merge.py — Ghép giọng đọc TTS (đã nối thành 1 file) vào
clip video đã ghép sẵn của 1 phần (part) trong dự án script-to-video (xem
`script_to_video_pipeline.py`).

v3: người dùng tự tạo từng clip screen ở Google Flow rồi TỰ NỐI LẠI thành 1
file `video-raw/merge.mp4` trước khi upload — khác v2 (mỗi screen 1 clip rời,
hệ thống phải tự nối bằng `concat_screen_clips()`). Vì vậy bước ghép giờ chỉ
còn 2 thao tác đơn giản:
  1. `concat_wavs()` — nối các file voice/screen-N.wav (cùng 1 TTS provider,
     cùng định dạng) thành voice/full-narration.wav. Tái dùng NGUYÊN VẸN
     `tts.segment_synthesizer._concat_wavs()` — audio cùng nguồn nên an toàn
     dùng `-f concat` stream-copy (khác video clip nhiều nguồn AI khác nhau
     mà v2 phải chuẩn hoá/re-encode).
  2. `mux_part_video()` — ghép merge.mp4 + full-narration.wav thành
     output.mp4, ĐÚNG chiến lược `apad` + `-shortest` của
     `merge/ffmpeg_merge.py::_run_ffmpeg_merge()`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tts.segment_synthesizer import _concat_wavs


def concat_wavs(wav_paths: list[Path], output_path: str | Path) -> Path:
    """Nối các file voice/screen-N.wav của 1 phần thành 1 file
    full-narration.wav, theo ĐÚNG thứ tự `wav_paths`."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return _concat_wavs(list(wav_paths), output_path)


def mux_part_video(
    merged_video_path: str | Path, full_narration_path: str | Path, output_path: str | Path
) -> Path:
    """
    Ghép audio full-narration.wav vào video-raw/merge.mp4 của 1 phần, THAY
    THẾ hoàn toàn audio gốc (`Dialogue: None` — clip AI-video-gen không có
    lời, lời thoại lồng ở đây).

    Video giữ nguyên `-c:v copy` (không re-encode) — merge.mp4 do người dùng
    tự nối, không cần chuẩn hoá lại ở đây.

    Raises:
        RuntimeError: ffmpeg lỗi hoặc không tạo được output hợp lệ.
    """
    merged_video_path = Path(merged_video_path)
    full_narration_path = Path(full_narration_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(merged_video_path),
        "-i", str(full_narration_path),
        "-filter_complex", "[1:a]apad[a]",
        "-map", "0:v:0",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-map_metadata", "-1",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg mux phần thất bại (exit {result.returncode}):\n{result.stderr[-500:]}"
        )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg không tạo được output.mp4 hợp lệ")
    return output_path

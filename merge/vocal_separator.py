"""
merge/vocal_separator.py — Tách nhạc nền khỏi audio gốc bằng Demucs (two-stems).

Constitution Technology Stack: Demucs. Lỗi ở module này KHÔNG được raise chặn
pipeline — luôn trả về None nếu tách thất bại, để merge/ffmpeg_merge.py fallback
về hành vi mute audio gốc hoàn toàn (hành vi mặc định trước đây).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def extract_background_music(source_video_path: str | Path, job_dir: Path) -> Path | None:
    """
    Tách nhạc nền (loại bỏ giọng nói) từ audio gốc của video bằng Demucs.

    Args:
        source_video_path: Đường dẫn tới source.mp4.
        job_dir: Thư mục job (jobs/{job_id}/).

    Returns:
        Path tới jobs/{job_id}/background.wav nếu tách thành công, None nếu lỗi
        (không raise — caller phải tự fallback).
    """
    source_video_path = Path(source_video_path)
    job_dir = Path(job_dir)
    background_path = job_dir / "background.wav"

    # Resume: nếu đã tách xong, bỏ qua
    if background_path.exists() and background_path.stat().st_size > 0:
        return background_path

    if shutil.which("demucs") is None:
        print("[vocal_separator] Không tìm thấy lệnh 'demucs' trong PATH, bỏ qua tách nhạc nền")
        return None

    raw_audio_path = job_dir / "_source_audio.wav"
    separated_dir = job_dir / "_demucs_out"

    try:
        _extract_audio_hq(source_video_path, raw_audio_path)

        result = subprocess.run(
            [
                "demucs",
                "--two-stems", "vocals",
                "-n", "htdemucs",
                "-o", str(separated_dir),
                str(raw_audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=600,  # video ngắn, đủ dư cho CPU
        )
        if result.returncode != 0:
            print(f"[vocal_separator] Demucs lỗi (exit {result.returncode}): {result.stderr[-500:]}")
            return None

        # Demucs xuất ra {output_dir}/htdemucs/{tên_file_không_ext}/no_vocals.wav
        no_vocals_path = separated_dir / "htdemucs" / raw_audio_path.stem / "no_vocals.wav"
        if not no_vocals_path.exists():
            print(f"[vocal_separator] Không tìm thấy no_vocals.wav sau khi tách: {no_vocals_path}")
            return None

        shutil.copy(no_vocals_path, background_path)
        return background_path

    except (subprocess.TimeoutExpired, OSError, RuntimeError) as e:
        # RuntimeError: _extract_audio_hq() raise khi ffmpeg tách audio lỗi
        # (VD source.mp4 hỏng) — phải bắt ở đây để giữ đúng cam kết "lỗi ở
        # module này không được raise chặn pipeline" (xem docstring), nếu
        # không job sẽ fail toàn bộ thay vì fallback mute + cảnh báo (FR-003
        # của 003-dubbing-fixes-subtitles, phát hiện khi verify US1)
        print(f"[vocal_separator] Lỗi chạy Demucs: {e}")
        return None
    finally:
        raw_audio_path.unlink(missing_ok=True)
        shutil.rmtree(separated_dir, ignore_errors=True)


def _extract_audio_hq(video_path: Path, audio_path: Path) -> None:
    """Tách audio gốc ra WAV chất lượng cao (44.1kHz stereo) làm input cho Demucs."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ar", "44100",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg tách audio (cho Demucs) thất bại (exit {result.returncode}): "
            f"{result.stderr[-500:]}"
        )

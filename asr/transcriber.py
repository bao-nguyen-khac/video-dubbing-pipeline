"""
asr/transcriber.py — Trích xuất transcript từ video bằng faster-whisper.

Output: jobs/{job_id}/transcript.json
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


# Model size: 'tiny', 'base', 'small', 'medium', 'large-v3'
# MVP dùng 'small' — cân bằng tốc độ và độ chính xác, không cần GPU
_WHISPER_MODEL = "small"
_WHISPER_DEVICE = "cpu"
_WHISPER_COMPUTE_TYPE = "int8"  # Tối ưu tốc độ trên CPU


def transcribe(source_path: str | Path, job_dir: Path) -> Path:
    """
    Trích xuất transcript từ file video bằng faster-whisper.

    Args:
        source_path: Đường dẫn tới source.mp4.
        job_dir: Thư mục job (jobs/{job_id}/).

    Returns:
        Path tới transcript.json vừa tạo.

    Raises:
        RuntimeError: Nếu tách audio hoặc chạy Whisper thất bại.
    """
    source_path = Path(source_path)
    job_dir = Path(job_dir)
    transcript_path = job_dir / "transcript.json"

    # Resume: nếu transcript.json đã tồn tại và parse được, bỏ qua (tránh trust
    # nhầm file bị corrupt/truncated do process bị kill giữa chừng)
    if transcript_path.exists() and transcript_path.stat().st_size > 10:
        try:
            with open(transcript_path, encoding="utf-8") as f:
                json.load(f)
            return transcript_path
        except (json.JSONDecodeError, OSError):
            pass  # file hỏng → transcribe lại

    if not source_path.exists():
        raise RuntimeError(f"File video nguồn không tồn tại: {source_path}")

    # Bước 1: Tách audio thành WAV 16kHz mono (tối ưu cho Whisper)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
        tmp_audio_path = Path(tmp_audio.name)

    try:
        _extract_audio(source_path, tmp_audio_path)

        # Bước 2: Chạy Whisper ASR
        segments, language = _run_whisper(tmp_audio_path)

    finally:
        # Dọn file tạm dù có lỗi hay không
        if tmp_audio_path.exists():
            tmp_audio_path.unlink()

    # Bước 3: Ghi transcript.json
    transcript_data = {
        "language": language,
        "segments": segments,
        "full_text": " ".join(s["text"].strip() for s in segments),
    }

    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, ensure_ascii=False, indent=2)

    return transcript_path


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Tách audio từ video, chuyển sang WAV 16kHz mono."""
    cmd = [
        "ffmpeg",
        "-y",                    # Ghi đè nếu file tạm đã tồn tại
        "-i", str(video_path),
        "-vn",                   # Chỉ lấy audio, bỏ video stream
        "-ar", "16000",          # Sample rate 16kHz (chuẩn Whisper)
        "-ac", "1",              # Mono channel
        "-c:a", "pcm_s16le",    # PCM 16-bit
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg tách audio thất bại (exit {result.returncode}): {result.stderr[-500:]}"
        )


def _run_whisper(audio_path: Path) -> tuple[list[dict], str]:
    """
    Chạy faster-whisper trên file audio.

    Returns:
        (segments, detected_language)
        segments: List[{"start": float, "end": float, "text": str}]
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper chưa được cài đặt. Chạy: pip install faster-whisper"
        ) from e

    model = WhisperModel(
        _WHISPER_MODEL,
        device=_WHISPER_DEVICE,
        compute_type=_WHISPER_COMPUTE_TYPE,
    )

    raw_segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,  # Lọc khoảng im lặng tự động
    )

    segments = []
    for seg in raw_segments:
        segments.append(
            {
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text,
            }
        )

    # Edge case: video không có lời thoại → trả về transcript rỗng (không raise)
    language = getattr(info, "language", "unknown")
    return segments, language

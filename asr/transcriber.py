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

# VAD (lọc khoảng im lặng) mặc định của faster-whisper dùng
# min_silence_duration_ms=2000 — chỉ coi là ngắt nghỉ khi im lặng ≥2 giây, nên
# nhiều câu ngắt quãng thật (hít thở, chuyển ý, <2s) bị gộp chung thành 1
# segment dài (VD "This is inside, this is the weirdest airport exit, this
# is a bit of a ghost town..." gộp thành 1 segment 11.6s dù thực chất là 3-4
# câu ngắt quãng). Vì 005-natural-pause-dubbing dựa hẳn vào mốc segment ASR để
# xác định vị trí khoảng lặng thật (group_segments(), _GAP_SILENCE_THRESHOLD=
# 0.30s), segment quá thô làm dubbing unit gộp sai, khiến bản dịch cho cả
# unit dài đọc xong sớm rồi im lặng bất thường giữa chừng (job người dùng báo
# lỗi: 60.5s dựng được so với 72.1s gốc — thiếu 11.5s). Hạ ngưỡng xuống 300ms
# để khớp đúng `_GAP_SILENCE_THRESHOLD` phía script_gen — ASR cắt segment ở
# mọi khoảng lặng ≥0.3s, còn việc gộp lại thành nhịp nói tự nhiên vẫn do
# group_segments() lo (nên không sợ vụn quá — segment quá ngắn/gần nhau vẫn
# được gộp lại đúng logic đã có).
_VAD_MIN_SILENCE_MS = 300

# Hạ VAD chưa xử lý hết: verify thật cho thấy có segment Whisper giữ liền
# mạch dù bên trong có khoảng trống 11.5s giữa 2 từ ("I'm" ... 11.5s ...
# "going to get some sleep...") — do tạp âm/gió giữ mức âm lượng trên ngưỡng
# "có tiếng nói" của VAD suốt đoạn đó, nên VAD không cắt được. `word_timestamps
# =True` cho mốc thời gian từng từ; `_split_by_word_gaps()` tự cắt thêm segment
# tại mọi khoảng trống GIỮA 2 TỪ ≥ ngưỡng này, độc lập với quyết định của VAD.
_WORD_GAP_SPLIT_THRESHOLD = 0.30


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
        vad_parameters={"min_silence_duration_ms": _VAD_MIN_SILENCE_MS},
        word_timestamps=True,  # cải thiện độ chính xác mốc start/end của segment
    )

    segments = []
    for seg in raw_segments:
        segments.extend(_split_by_word_gaps(seg))

    # Edge case: video không có lời thoại → trả về transcript rỗng (không raise)
    language = getattr(info, "language", "unknown")
    return segments, language


def _split_by_word_gaps(seg) -> list[dict]:
    """
    Cắt thêm 1 segment Whisper thành nhiều segment con tại mọi khoảng trống
    GIỮA 2 TỪ ≥ `_WORD_GAP_SPLIT_THRESHOLD`, độc lập với quyết định của VAD.

    Verify thật phát hiện: model 'small' có thể lẫn tạp âm/gió thành 1 từ ảo
    ("I'm") cách xa nội dung thật tới 11.5s, khiến segment bị coi là bắt đầu
    sớm hơn thực tế rất nhiều — VAD không cắt vì mức âm lượng vẫn cao suốt
    đoạn đó (tạp âm, không phải im lặng thật). Cắt theo khoảng trống giữa từ
    xử lý đúng CẢ 2 trường hợp: khoảng lặng thật giữa 2 câu, VÀ từ ảo do model
    nghe nhầm tạp âm — ở cả 2 trường hợp, tách riêng ra vẫn cho kết quả đúng
    hơn giữ nguyên 1 segment dài sai lệch.

    Nếu segment không có `words` (model/tham số không trả về) thì giữ nguyên
    y như cũ, không raise.
    """
    words = getattr(seg, "words", None)
    if not words:
        return [{"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text}]

    result: list[dict] = []
    current_words = [words[0]]
    for prev_word, word in zip(words, words[1:]):
        if word.start - prev_word.end >= _WORD_GAP_SPLIT_THRESHOLD:
            result.append(_words_to_segment(current_words))
            current_words = []
        current_words.append(word)
    if current_words:
        result.append(_words_to_segment(current_words))

    return result


def _words_to_segment(words: list) -> dict:
    return {
        "start": round(words[0].start, 3),
        "end": round(words[-1].end, 3),
        "text": "".join(w.word for w in words),
    }

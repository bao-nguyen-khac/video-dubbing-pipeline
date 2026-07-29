"""
asr/transcriber.py — Trích xuất transcript từ video bằng faster-whisper.

Output: jobs/{job_id}/transcript.json
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from media_utils import has_audio_stream


# Model size: 'tiny', 'base', 'small', 'medium', 'large-v3'
# Mặc định 'small' — cân bằng tốc độ và độ chính xác, không cần GPU.
#
# Whisper là model ĐA NGÔN NGỮ (~99 thứ tiếng) và bước transcribe() bên dưới
# KHÔNG ghim ngôn ngữ nào, nên tiếng Trung/Nhật/Hàn/Thái... đều chạy được sẵn.
# Tuy nhiên độ chính xác của 'small' với các thứ tiếng không phải tiếng Anh
# thấp hơn rõ rệt — đổi sang 'medium'/'large-v3' qua WHISPER_MODEL trong .env
# nếu cần chất lượng cao hơn (đổi lại chạy chậm hơn nhiều trên CPU).
_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
_WHISPER_DEVICE = "cpu"
_WHISPER_COMPUTE_TYPE = "int8"  # Tối ưu tốc độ trên CPU

# Ngôn ngữ nguồn. Để TRỐNG = tự nhận diện (mặc định).
#
# Tự nhận diện chỉ nghe 30 GIÂY ĐẦU của audio, nên có thể đoán sai khi clip mở
# đầu bằng nhạc/tiếng ồn, hoặc khi nói xen kẽ 2 thứ tiếng. Ghim mã ngôn ngữ
# (vd "zh", "ja", "ko", "vi", "en") qua WHISPER_LANGUAGE trong .env để bỏ qua
# bước đoán khi đã biết chắc clip nói tiếng gì.
_WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "").strip() or None

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

    # Kiểm tra sớm: video không có audio stream nào (vd bài đăng dạng ảnh/
    # slideshow của TikTok, nhạc nền phát tách riêng khỏi track hình) sẽ khiến
    # ffmpeg thất bại với thông điệp kỹ thuật khó hiểu ("Output file does not
    # contain any stream") — báo rõ nguyên nhân ngay tại đây thay vì để lộ
    # stderr của ffmpeg ra người dùng (root cause đã verify thật: source.mp4
    # chỉ có 1 stream video HEVC, 0 audio stream).
    if not has_audio_stream(source_path):
        raise RuntimeError(
            "Video gốc không có âm thanh (không tìm thấy audio stream nào). "
            "Đây thường là bài đăng dạng ảnh/slideshow của TikTok — nhạc nền "
            "phát tách riêng khỏi phần hình nên không tải kèm được. Thử một "
            "video khác (video quay thường có tiếng)."
        )

    # Bước 1: Tách audio thành WAV 16kHz mono (tối ưu cho Whisper)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_audio:
        tmp_audio_path = Path(tmp_audio.name)

    try:
        _extract_audio(source_path, tmp_audio_path)

        # Bước 2: Chạy Whisper ASR
        segments, language, language_probability = _run_whisper(tmp_audio_path)

    finally:
        # Dọn file tạm dù có lỗi hay không
        if tmp_audio_path.exists():
            tmp_audio_path.unlink()

    # Bước 3: Ghi transcript.json
    transcript_data = {
        "language": language,
        # Độ tin cậy của bước đoán ngôn ngữ (1.0 khi đã ghim WHISPER_LANGUAGE).
        # Ghi lại để khi bản dịch ra kết quả lạ, còn kiểm được nguyên nhân có
        # phải do nhận diện sai ngôn ngữ hay không.
        "language_probability": language_probability,
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


def _run_whisper(audio_path: Path) -> tuple[list[dict], str, float]:
    """
    Chạy faster-whisper trên file audio.

    Returns:
        (segments, language, language_probability)
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
        # None = tự nhận diện (mặc định); đặt WHISPER_LANGUAGE để ghim
        language=_WHISPER_LANGUAGE,
        vad_filter=True,  # Lọc khoảng im lặng tự động
        vad_parameters={"min_silence_duration_ms": _VAD_MIN_SILENCE_MS},
        word_timestamps=True,  # cải thiện độ chính xác mốc start/end của segment
    )

    segments = []
    for seg in raw_segments:
        segments.extend(_split_by_word_gaps(seg))

    # Edge case: video không có lời thoại → trả về transcript rỗng (không raise)
    language = getattr(info, "language", "unknown")
    probability = float(getattr(info, "language_probability", 0.0) or 0.0)

    if _WHISPER_LANGUAGE:
        print(f"[transcriber] Ngôn ngữ nguồn: {language} (ghim qua WHISPER_LANGUAGE)")
    else:
        print(f"[transcriber] Ngôn ngữ nguồn tự nhận diện: {language} ({probability:.0%})")
        # Đoán ngôn ngữ chỉ dựa trên 30s đầu — độ tin cậy thấp thường đi kèm
        # transcript sai bét, cảnh báo để người dùng biết đường ghim lại
        if probability and probability < 0.6:
            print(
                f"[transcriber] ⚠ Độ tin cậy nhận diện ngôn ngữ thấp ({probability:.0%}). "
                f"Nếu transcript sai, đặt WHISPER_LANGUAGE trong .env (vd 'zh', 'ja', 'ko')."
            )

    return segments, language, probability


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
        # Không có word-timestamp → không kèm 'words' (sentence_segmenter sẽ
        # tự bỏ qua và giữ nguyên nhịp cắt cũ, không raise)
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
    # Giữ mốc thời gian TỪNG TỪ trong 'words' để script_gen cắt lại đúng ranh
    # giới câu (sentence_segmenter) — faster-whisper 'small' hay bỏ dấu câu,
    # nên không thể cắt theo câu nếu chỉ có mốc segment thô.
    return {
        "start": round(words[0].start, 3),
        "end": round(words[-1].end, 3),
        "text": "".join(w.word for w in words),
        "words": [
            {"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3)}
            for w in words
        ],
    }

"""
tts/segment_synthesizer.py — Tổng hợp giọng đọc THEO TỪNG NHỊP và ghép thành
timeline khớp nhịp ngắt nghỉ của video gốc (005-natural-pause-dubbing).

Thay thế hoàn toàn cơ chế cũ "tổng hợp 1 khối liên tục rồi kéo giãn/nén đều
toàn bộ cho khớp tổng thời lượng" — cách cũ làm mất hết khoảng lặng tự nhiên
và khiến giọng dịch nghe chậm bất thường.

Luồng xử lý (research.md §3/§4):
1. Đọc `script.json.segments` (mỗi phần tử = 1 dubbing unit, đã có start/end
   từ ASR và nội dung đã dịch/viết lại).
2. Với mỗi unit: gọi TTS ở tốc độ mặc định qua adapter chung của provider →
   chuẩn hoá WAV → đo thời lượng → nếu TRÀN khung thì tăng tốc cục bộ bằng
   ffmpeg `atempo` trong `[1.0, 1.4]`. KHÔNG BAO GIỜ đọc chậm (`tempo < 1.0`)
   để lấp khung — đó chính là lỗi đang sửa.
3. Ghép timeline: đặt mỗi unit tại `max(start_gốc, hết_unit_trước)` và chèn
   khoảng lặng THẬT vào các quãng trống (FR-002, FR-008); unit tràn đẩy lùi
   unit kế tiếp thay vì bị cắt (FR-009).
4. Ghi `voice.wav`, `voice_timeline.json` và (tuỳ chọn) `captions.json`.

Lỗi tổng hợp CỤC BỘ ở vài unit không làm hỏng cả job: unit lỗi được thay bằng
khoảng lặng đúng bằng khung gốc và job đi tiếp (FR-006). Chỉ khi TOÀN BỘ unit
đều lỗi mới raise để pipeline fail job.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path
from typing import Callable

from media_utils import get_media_duration

# ─── Config ──────────────────────────────────────────────────────────────────

# Thông số WAV chuẩn hoá dùng chung cho mọi unit + khoảng lặng — bắt buộc phải
# đồng nhất thì ffmpeg concat demuxer mới ghép được (research.md §4). 3 provider
# trả về định dạng khác nhau nên luôn phải chuẩn hoá lại.
_SAMPLE_RATE = 44100
_CHANNELS = 2
_SAMPLE_WIDTH = 2  # bytes → pcm_s16le

# Biên chỉnh tốc độ theo từng unit (research.md §3). Trần 1.4 lấy đúng biên
# trên hẹp nhất đang có (edge-tts rate +40%) nên không nới biên của provider
# nào, đồng thời cho hành vi giống hệt nhau giữa 3 provider (SC-004).
_MIN_TEMPO = 1.0
_MAX_TEMPO = 1.4
_TEMPO_TOLERANCE = 0.15  # tràn dưới ngưỡng này (giây) thì không chỉnh

# Số lần thử tổng hợp cho mỗi unit trước khi thay bằng khoảng lặng (FR-006)
_SYNTH_ATTEMPTS = 2

_FFMPEG_TIMEOUT_SECONDS = 120


# ─── Helper audio (T006) ─────────────────────────────────────────────────────


def _run_ffmpeg(cmd: list[str], what: str) -> None:
    """Chạy ffmpeg, raise RuntimeError kèm stderr rút gọn nếu lỗi."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SECONDS
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg {what} thất bại (exit {result.returncode}): {result.stderr[-300:]}"
        )


def _normalize_wav(path: Path) -> None:
    """
    Chuẩn hoá file audio tại chỗ về 44100 Hz / 2 kênh / pcm_s16le.

    Ghi ra file `.tmp.wav` rồi thay thế — không đọc/ghi cùng lúc trên 1 file.
    """
    tmp_path = path.with_suffix(".norm.wav")
    try:
        _run_ffmpeg(
            [
                "ffmpeg", "-y",
                "-i", str(path),
                "-ar", str(_SAMPLE_RATE),
                "-ac", str(_CHANNELS),
                "-c:a", "pcm_s16le",
                str(tmp_path),
            ],
            "chuẩn hoá WAV",
        )
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise RuntimeError("ffmpeg không tạo được file WAV chuẩn hoá hợp lệ")
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _write_silence_wav(path: Path, duration: float) -> Path:
    """
    Ghi 1 file WAV im lặng dài `duration` giây, cùng thông số với unit đã chuẩn
    hoá. Dùng `wave` của stdlib thay vì gọi ffmpeg cho từng khoảng lặng — rẻ
    hơn nhiều khi 1 video có vài chục quãng nghỉ.
    """
    frames = max(0, int(round(duration * _SAMPLE_RATE)))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(_CHANNELS)
        wav.setsampwidth(_SAMPLE_WIDTH)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(b"\x00" * (frames * _CHANNELS * _SAMPLE_WIDTH))
    return path


def _apply_atempo(path: Path, tempo: float) -> None:
    """Đổi tốc độ phát (không đổi cao độ đáng kể) bằng ffmpeg atempo, ghi đè path."""
    tmp_path = path.with_suffix(".tempo.wav")
    try:
        _run_ffmpeg(
            [
                "ffmpeg", "-y",
                "-i", str(path),
                "-filter:a", f"atempo={tempo:.4f}",
                "-ar", str(_SAMPLE_RATE),
                "-ac", str(_CHANNELS),
                "-c:a", "pcm_s16le",
                str(tmp_path),
            ],
            f"atempo={tempo:.4f}",
        )
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise RuntimeError("ffmpeg atempo không tạo được file hợp lệ")
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _escape_concat_path(path: Path) -> str:
    """Escape dấu nháy đơn trong đường dẫn cho file danh sách của concat demuxer."""
    return str(path.resolve()).replace("'", "'\\''")


def _concat_wavs(files: list[Path], output_path: Path) -> Path:
    """
    Ghép danh sách WAV (đã cùng thông số) thành 1 file bằng concat demuxer.

    Dùng demuxer thay vì filter_complex vì số phần tử tỉ lệ với số nhịp (vài
    chục file) — lệnh vẫn ngắn và không đụng giới hạn số input.
    """
    if not files:
        raise RuntimeError("Không có đoạn audio nào để ghép thành voice.wav")

    list_path = output_path.with_suffix(".concat.txt")
    # concat demuxer: đường dẫn tuyệt đối, escape dấu nháy đơn theo cú pháp ffmpeg
    lines = [f"file '{_escape_concat_path(p)}'" for p in files]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        _run_ffmpeg(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                str(output_path),
            ],
            "concat các đoạn giọng đọc",
        )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("ffmpeg concat không tạo được voice.wav hợp lệ")
    finally:
        list_path.unlink(missing_ok=True)

    return output_path


# ─── Adapter provider (T010) ─────────────────────────────────────────────────


def _get_adapter(provider: str, voice_id: str | None) -> Callable[[str, Path], None]:
    """
    Trả về hàm `(text, output_path) -> None` sinh audio cho 1 unit bằng đúng
    provider được chọn.

    Cả 3 provider đều đã có sẵn hàm mức-text cùng chữ ký (vốn phục vụ tính
    năng nghe thử của 004) — ở đây chỉ bind sẵn `voice_id` (research.md §7).

    Raises:
        ValueError: Nếu provider không được hỗ trợ.
        RuntimeError: Nếu provider yêu cầu voice_id mà không có.
    """
    if provider == "edge-tts":
        from tts.edge_tts_client import DEFAULT_VOICE
        from tts.edge_tts_client import synthesize_text as edge_synthesize_text

        voice = voice_id or DEFAULT_VOICE
        return lambda text, out: edge_synthesize_text(text, voice, out)

    if provider == "lucyai":
        from tts.lucyai_client import synthesize_text as lucyai_synthesize_text

        if not voice_id:
            raise RuntimeError(
                "Provider 'lucyai' (Vivibe) bắt buộc phải chọn giọng đọc cụ thể "
                "— không có giọng mặc định cho tài khoản riêng của người dùng."
            )
        return lambda text, out: lucyai_synthesize_text(text, voice_id, out)

    if provider == "router-tts":
        from tts.router_tts_client import synthesize_text as router_synthesize_text

        if not voice_id:
            raise RuntimeError(
                "Provider 'router-tts' (9router) bắt buộc phải chọn giọng đọc "
                "cụ thể (VD 'Puck')."
            )
        return lambda text, out: router_synthesize_text(text, voice_id, out)

    raise ValueError(
        f"tts_provider không hợp lệ: {provider}. "
        "Dùng 'edge-tts', 'lucyai' hoặc 'router-tts'."
    )


# ─── Tổng hợp từng unit (T011, T024) ─────────────────────────────────────────


def _synthesize_unit(
    adapter: Callable[[str, Path], None],
    text: str,
    unit_path: Path,
) -> Exception | None:
    """
    Sinh audio cho 1 unit, thử tối đa `_SYNTH_ATTEMPTS` lần.

    Returns:
        None nếu thành công (file đã chuẩn hoá tại `unit_path`), hoặc exception
        của lần thử cuối nếu thất bại — để hàm gọi thay bằng khoảng lặng thay
        vì làm hỏng cả job (FR-006).
    """
    last_error: Exception | None = None

    for attempt in range(_SYNTH_ATTEMPTS):
        try:
            adapter(text, unit_path)
            if not unit_path.exists() or unit_path.stat().st_size == 0:
                raise RuntimeError("provider không tạo được file audio hợp lệ")
            _normalize_wav(unit_path)
            return None
        except Exception as e:  # noqa: BLE001 — mọi lỗi provider đều xử lý như nhau
            last_error = e
            unit_path.unlink(missing_ok=True)
            if attempt + 1 < _SYNTH_ATTEMPTS:
                print(
                    f"[segment_synthesizer] Thử lại nhịp {unit_path.stem} "
                    f"(lần {attempt + 2}/{_SYNTH_ATTEMPTS}) sau lỗi: {e}"
                )

    return last_error


def _fit_unit_to_window(unit_path: Path, window: float) -> tuple[float, float]:
    """
    Khớp 1 unit vào khung thời gian gốc bằng cách CHỈ tăng tốc (research.md §3).

    Thiếu thời lượng so với khung → giữ nguyên, phần dư thành khoảng lặng thật.
    Tràn khung → atempo tối đa `_MAX_TEMPO`; tràn phần còn lại được chấp nhận
    và sẽ đẩy lùi unit kế tiếp (FR-009).

    Returns:
        (duration_sau_khi_chỉnh, tempo_đã_áp)
    """
    duration = get_media_duration(unit_path)
    if duration <= 0 or window <= 0:
        return duration, 1.0

    if duration <= window + _TEMPO_TOLERANCE:
        return duration, 1.0

    tempo = min(_MAX_TEMPO, duration / window)
    if tempo <= _MIN_TEMPO:
        return duration, 1.0

    try:
        _apply_atempo(unit_path, tempo)
        return get_media_duration(unit_path), tempo
    except RuntimeError as e:
        print(
            f"[segment_synthesizer] Chỉnh tempo={tempo:.2f} cho {unit_path.stem} "
            f"thất bại ({e}), giữ bản tốc độ mặc định"
        )
        return duration, 1.0


# ─── Hàm chính (T012, T016) ──────────────────────────────────────────────────


def synthesize_segments(
    script_path: str | Path,
    job_dir: Path,
    provider: str = "edge-tts",
    voice_id: str | None = None,
    dynamic_captions: bool = False,
) -> tuple[Path, float, dict]:
    """
    Sinh `voice.wav` khớp nhịp từ `script.json.segments`.

    Args:
        script_path: Đường dẫn `script.json` (phải có mảng `segments`).
        job_dir: Thư mục job (`jobs/{job_id}/`).
        provider: 'edge-tts' | 'lucyai' | 'router-tts'.
        voice_id: Giọng cụ thể; None → giọng mặc định (chỉ edge-tts có).
        dynamic_captions: True → ghi thêm `captions.json` lấy mốc từ timeline
            thực tế, dùng được cho cả 3 provider (FR-011).

    Returns:
        (voice_path, duration_seconds, timeline_dict)

    Raises:
        RuntimeError: Nếu script.json thiếu/rỗng/không có `segments`, hoặc
            TOÀN BỘ unit đều lỗi tổng hợp (lỗi toàn phần — không che giấu).
        ValueError: Nếu provider không hợp lệ.
    """
    script_path = Path(script_path)
    job_dir = Path(job_dir)
    voice_path = job_dir / "voice.wav"
    timeline_path = job_dir / "voice_timeline.json"
    captions_path = job_dir / "captions.json"

    # Resume: voice.wav + timeline đã có và hợp lệ → không gọi lại provider
    if (
        voice_path.exists()
        and voice_path.stat().st_size > 0
        and timeline_path.exists()
        and timeline_path.stat().st_size > 0
    ):
        try:
            with open(timeline_path, encoding="utf-8") as f:
                timeline = json.load(f)
            if dynamic_captions and not captions_path.exists():
                _write_captions(timeline, captions_path)
            return voice_path, get_media_duration(voice_path), timeline
        except (json.JSONDecodeError, OSError):
            pass  # timeline hỏng → tổng hợp lại từ đầu

    if not script_path.exists():
        raise RuntimeError(f"script.json không tồn tại: {script_path}")

    with open(script_path, encoding="utf-8") as f:
        script_data = json.load(f)

    units = script_data.get("segments") or []
    if not units:
        raise RuntimeError(
            "script.json không có 'segments' — không thể lồng tiếng theo nhịp. "
            "Video gốc có thể không có lời thoại, hoặc script.json được tạo "
            "bởi phiên bản pipeline cũ (hãy xoá script.json để sinh lại)."
        )

    adapter = _get_adapter(provider, voice_id)
    segments_dir = job_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    print(f"[segment_synthesizer] {len(units)} nhịp lồng tiếng cần tổng hợp")

    # ── Bước 1: tổng hợp + khớp khung từng unit ─────────────────────────────
    records: list[dict] = []
    failed_count = 0

    for i, unit in enumerate(units):
        text = (unit.get("translated_text") or "").strip()
        source_start = float(unit["start"])
        source_end = float(unit["end"])
        window = max(0.0, source_end - source_start)
        unit_path = segments_dir / f"unit_{i:04d}.wav"

        # Resume theo từng nhịp: file đã có → không gọi lại provider
        if unit_path.exists() and unit_path.stat().st_size > 0:
            duration = get_media_duration(unit_path)
            records.append(
                {
                    "index": i,
                    "path": unit_path,
                    "duration": duration,
                    "tempo": 1.0,  # đã khớp ở lần chạy trước
                    "source_start": source_start,
                    "source_end": source_end,
                    "text": text,
                    "status": "ok",
                }
            )
            continue

        if not text:
            # Unit không có nội dung (LLM trả dòng rỗng) — giữ khoảng lặng
            # đúng khung gốc, không tính là lỗi provider
            silence_path = segments_dir / f"empty_{i:04d}.wav"
            _write_silence_wav(silence_path, window)
            records.append(
                {
                    "index": i,
                    "path": silence_path,
                    "duration": window,
                    "tempo": 1.0,
                    "source_start": source_start,
                    "source_end": source_end,
                    "text": "",
                    "status": "failed",
                }
            )
            failed_count += 1
            print(
                f"[segment_synthesizer] ⚠ Nhịp {i} ({source_start:.2f}s→"
                f"{source_end:.2f}s) không có nội dung, thay bằng khoảng lặng"
            )
            continue

        error = _synthesize_unit(adapter, text, unit_path)

        if error is not None:
            # FR-006: lỗi cục bộ → khoảng lặng dài đúng khung gốc, job đi tiếp
            silence_path = segments_dir / f"failed_{i:04d}.wav"
            _write_silence_wav(silence_path, window)
            records.append(
                {
                    "index": i,
                    "path": silence_path,
                    "duration": window,
                    "tempo": 1.0,
                    "source_start": source_start,
                    "source_end": source_end,
                    "text": text,
                    "status": "failed",
                }
            )
            failed_count += 1
            print(
                f"[segment_synthesizer] ⚠ Nhịp {i} ({source_start:.2f}s→"
                f"{source_end:.2f}s) TTS lỗi sau {_SYNTH_ATTEMPTS} lần thử, "
                f"thay bằng khoảng lặng: {error}"
            )
            continue

        duration, tempo = _fit_unit_to_window(unit_path, window)
        records.append(
            {
                "index": i,
                "path": unit_path,
                "duration": duration,
                "tempo": tempo,
                "source_start": source_start,
                "source_end": source_end,
                "text": text,
                "status": "ok",
            }
        )
        print(
            f"[segment_synthesizer] [{i + 1}/{len(units)}] "
            f"{source_start:.2f}s→{source_end:.2f}s | tempo={tempo:.2f}"
        )

    # Lỗi TOÀN PHẦN (mất kết nối provider hoàn toàn) vẫn phải fail rõ ràng —
    # US3 chỉ áp dụng cho lỗi cục bộ (Edge Case cuối của spec)
    if failed_count == len(records):
        raise RuntimeError(
            f"Toàn bộ {failed_count} nhịp đều tổng hợp giọng đọc thất bại — "
            f"kiểm tra kết nối/API key của provider '{provider}'."
        )

    # ── Bước 2: ghép timeline có khoảng lặng thật ───────────────────────────
    concat_files: list[Path] = []
    timeline_segments: list[dict] = []
    cursor = 0.0

    for rec in records:
        # FR-009: unit trước tràn thì đẩy lùi unit này thay vì cắt nội dung
        start = max(rec["source_start"], cursor)
        gap = start - cursor
        if gap > 0.001:
            silence_path = segments_dir / f"silence_{rec['index']:04d}.wav"
            _write_silence_wav(silence_path, gap)
            concat_files.append(silence_path)

        concat_files.append(rec["path"])
        end = start + rec["duration"]

        timeline_segments.append(
            {
                "index": rec["index"],
                "source_start": round(rec["source_start"], 3),
                "source_end": round(rec["source_end"], 3),
                "start": round(start, 3),
                "end": round(end, 3),
                "text": rec["text"],
                "tempo": round(rec["tempo"], 4),
                "status": rec["status"],
            }
        )
        cursor = end

    _concat_wavs(concat_files, voice_path)
    total_duration = get_media_duration(voice_path)

    timeline = {
        "total_duration": round(total_duration, 3),
        "failed_count": failed_count,
        "segments": timeline_segments,
    }
    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)

    # ── Bước 3: phụ đề động lấy mốc từ chính timeline này (FR-011) ──────────
    if dynamic_captions:
        _write_captions(timeline, captions_path)

    return voice_path, total_duration, timeline


def _write_captions(timeline: dict, captions_path: Path) -> None:
    """
    Ghi `captions.json` từ timeline thực tế — nguồn duy nhất cho phụ đề động ở
    CẢ 3 provider (FR-011, thay hoàn toàn cơ chế SentenceBoundary streaming
    riêng của edge-tts trước đây).

    Unit `status="failed"` không sinh cue: không có giọng đọc thì không hiện
    phụ đề.
    """
    cues = [
        {"start": seg["start"], "end": seg["end"], "text": seg["text"]}
        for seg in timeline.get("segments", [])
        if seg.get("status") == "ok" and seg.get("text", "").strip()
    ]
    if not cues:
        print("[segment_synthesizer] Không có nhịp hợp lệ nào, bỏ qua captions.json")
        return
    with open(captions_path, "w", encoding="utf-8") as f:
        json.dump(cues, f, ensure_ascii=False, indent=2)

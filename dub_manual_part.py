"""
dub_manual_part.py — Lồng tiếng cho 1 "part" của dự án script-to-video được
viết/tạo THỦ CÔNG (không đi qua job system của `script_to_video_pipeline.py`),
khi người dùng đã tự merge toàn bộ 10 clip Flow thành 1 video duy nhất
(`video-raw/merge.mp4`) thay vì upload từng clip riêng theo từng screen.

Khác `script_to_video_pipeline.py` (yêu cầu 1 clip RIÊNG mỗi screen, mux từng
clip rồi mới concat): ở đây video đã concat sẵn, nên chỉ cần dựng ĐÚNG 1 track
giọng đọc dài bằng cả video (mỗi đoạn giọng ép khớp đúng khung giây của screen
tương ứng để không lệch so với điểm cắt đã có trong video), rồi mux 1 lần bằng
`merge.ffmpeg_merge.merge_audio()` (tái dùng nguyên, không sửa) — coi
`merge.mp4` vừa là nguồn video vừa là nguồn audio nền (SFX/ambient gốc, mix
nhẹ dưới giọng đọc) vì mọi clip Flow đều `Dialogue: None` (không có lời thoại
gốc cần lọc bỏ).

Input bắt buộc trong thư mục `--part`:
  voiceover.json   — {"video_raw": "video-raw/merge.mp4",
                      "screens": [{"index", "duration_seconds", "text"}, ...]}
  video-raw/merge.mp4

Output: `<part>/output.mp4` (không đụng merge.mp4/voiceover.json/*.md).

Cách chạy:
    python dub_manual_part.py --part script-to-video/<project>/part-1
    python dub_manual_part.py --part <...>/part-1 --provider lucyai --voice-id <id>
    python dub_manual_part.py --part <...>/part-1 --force   # dub lại từ đầu
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from media_utils import get_media_duration

_FFMPEG_TIMEOUT_SECONDS = 120
# Cùng biên atempo với tts/segment_synthesizer.py — chỉ tăng tốc, không giảm.
_MAX_TEMPO = 1.25
_TEMPO_TOLERANCE = 0.05


def _run_ffmpeg(cmd: list[str], what: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg {what} thất bại (exit {result.returncode}): {result.stderr[-400:]}")


def _load_voiceover(part_dir: Path) -> dict:
    voiceover_path = part_dir / "voiceover.json"
    if not voiceover_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {voiceover_path} — cần file manifest voiceover.json "
            "(xem docstring dub_manual_part.py) trước khi chạy dub."
        )
    with open(voiceover_path, encoding="utf-8") as f:
        return json.load(f)


def _fit_audio_to_duration(raw_path: Path, target_seconds: float, fitted_path: Path) -> tuple[float, float, bool]:
    """
    Ép `raw_path` (giọng đọc vừa tổng hợp) khớp ĐÚNG `target_seconds` — bằng
    đúng khung giây của screen trong video đã merge.

    - Ngắn hơn khung: pad im lặng cho đủ (`apad` + `-t`).
    - Dài hơn khung: tăng tốc tối đa `_MAX_TEMPO` (giống
      `segment_synthesizer._fit_unit_to_window()`), rồi pad/cắt phần còn dư.

    Returns:
        (final_duration, tempo_applied, overflow_after_tempo) — overflow=True
        nghĩa là dù đã tăng tốc tối đa vẫn còn bị cắt cuối câu, cần cảnh báo.
    """
    raw_duration = get_media_duration(raw_path)
    if raw_duration <= 0:
        raise RuntimeError(f"Không đọc được thời lượng audio vừa tổng hợp: {raw_path}")

    tempo = 1.0
    source_path = raw_path
    overflow = False

    if raw_duration > target_seconds + _TEMPO_TOLERANCE:
        tempo = min(_MAX_TEMPO, raw_duration / target_seconds)
        if tempo > 1.0 + 1e-4:
            tempo_path = fitted_path.with_suffix(".tempo.wav")
            _run_ffmpeg(
                [
                    "ffmpeg", "-y",
                    "-i", str(raw_path),
                    "-filter:a", f"atempo={tempo:.4f}",
                    "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
                    str(tempo_path),
                ],
                f"atempo={tempo:.4f}",
            )
            source_path = tempo_path
            new_duration = get_media_duration(tempo_path)
            if new_duration > target_seconds + _TEMPO_TOLERANCE:
                overflow = True

    _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-i", str(source_path),
            "-af", "apad",
            "-t", f"{target_seconds}",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            str(fitted_path),
        ],
        "pad/trim theo khung screen",
    )

    if source_path != raw_path:
        source_path.unlink(missing_ok=True)

    if not fitted_path.exists() or fitted_path.stat().st_size == 0:
        raise RuntimeError(f"Không tạo được audio đã ép khung: {fitted_path}")

    return get_media_duration(fitted_path), tempo, overflow


def _concat_wavs(files: list[Path], output_path: Path) -> Path:
    """Nối các wav (đã chuẩn hoá cùng thông số ở bước fit) bằng concat demuxer."""
    list_path = output_path.with_suffix(".concat.txt")
    lines = [f"file '{str(p.resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for p in files]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output_path)],
            "nối các đoạn giọng theo screen",
        )
    finally:
        list_path.unlink(missing_ok=True)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Không tạo được file giọng đọc tổng: {output_path}")
    return output_path


def dub_manual_part(
    part_dir: Path,
    provider: str = "edge-tts",
    voice_id: str | None = None,
    force: bool = False,
) -> Path:
    """
    Lồng tiếng cho `part_dir` (vd `.../part-1`), trả về đường dẫn `output.mp4`.

    Resume-safe theo từng screen: screen nào đã có file giọng đã ép khung thì
    bỏ qua tổng hợp lại, trừ khi `force=True`. `merge_audio()` tự resume nếu
    `output.mp4` đã tồn tại — dùng `force=True` để dub lại từ đầu.
    """
    from merge.ffmpeg_merge import merge_audio
    from tts.scene_synthesizer import synthesize_scene

    part_dir = Path(part_dir)
    data = _load_voiceover(part_dir)
    video_raw_path = part_dir / data["video_raw"]
    if not video_raw_path.exists():
        raise FileNotFoundError(f"Không tìm thấy video đã merge: {video_raw_path}")

    voice_dir = part_dir / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    output_path = part_dir / "output.mp4"
    if force:
        output_path.unlink(missing_ok=True)

    fitted_paths: list[Path] = []
    warnings: list[str] = []

    for screen in sorted(data["screens"], key=lambda s: s["index"]):
        n = screen["index"] + 1
        target = float(screen["duration_seconds"])
        fitted_path = voice_dir / f"screen-{n}.wav"
        fitted_paths.append(fitted_path)

        if fitted_path.exists() and fitted_path.stat().st_size > 0 and not force:
            print(f"[dub_manual_part] Screen {n}: đã có giọng đã ép khung, bỏ qua tổng hợp lại")
            continue

        raw_path = voice_dir / f"screen-{n}-raw.wav"
        print(f"[dub_manual_part] Screen {n}/{len(data['screens'])}: tổng hợp giọng ({provider})...")
        synthesize_scene(screen["text"], raw_path, provider, voice_id)

        _, tempo, overflow = _fit_audio_to_duration(raw_path, target, fitted_path)
        raw_path.unlink(missing_ok=True)

        if overflow:
            msg = (
                f"Screen {n}: giọng đọc vẫn dài hơn khung {target:.0f}s dù đã tăng tốc "
                f"{tempo:.2f}x — audio có thể bị cắt cuối câu, cân nhắc rút ngắn "
                "vi_voiceover_text."
            )
            warnings.append(msg)
            print(f"[dub_manual_part] ⚠ {msg}")
        elif tempo > 1.0 + 1e-4:
            print(f"[dub_manual_part] Screen {n}: tăng tốc {tempo:.2f}x cho vừa khung {target:.0f}s")

    full_narration_path = voice_dir / "full-narration.wav"
    print(f"[dub_manual_part] Nối {len(fitted_paths)} đoạn giọng thành 1 track...")
    _concat_wavs(fitted_paths, full_narration_path)

    narration_duration = get_media_duration(full_narration_path)
    video_duration = get_media_duration(video_raw_path)
    if abs(narration_duration - video_duration) > 1.0:
        print(
            f"[dub_manual_part] ⚠ Lệch thời lượng: giọng đọc {narration_duration:.2f}s "
            f"vs video {video_duration:.2f}s — kiểm tra lại voiceover.json khớp đúng "
            "số screen/thời lượng với merge.mp4."
        )

    print(f"[dub_manual_part] Mux vào {video_raw_path.name} (giữ SFX gốc mix nhẹ dưới giọng đọc)...")
    output_path, duration_mismatch, background_kept = merge_audio(
        source_video_path=video_raw_path,
        voice_path=full_narration_path,
        job_dir=part_dir,
        background_audio_path=video_raw_path,
    )

    print(f"[dub_manual_part] Xong: {output_path}")
    print(f"[dub_manual_part] duration_mismatch={duration_mismatch} background_music_kept={background_kept}")
    if warnings:
        print(f"[dub_manual_part] {len(warnings)} cảnh báo cần nghe lại:")
        for w in warnings:
            print(f"  - {w}")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--part", required=True, help="Thư mục part (vd .../part-1), chứa voiceover.json + video-raw/merge.mp4")
    parser.add_argument("--provider", default="edge-tts", choices=["edge-tts", "lucyai", "omnivoice"])
    parser.add_argument("--voice-id", default=None, help="Bắt buộc với lucyai/omnivoice; mặc định vi-VN-NamMinhNeural nếu bỏ trống với edge-tts")
    parser.add_argument("--force", action="store_true", help="Dub lại từ đầu, bỏ qua resume")
    args = parser.parse_args()

    voice_id = args.voice_id
    if args.provider == "edge-tts" and not voice_id:
        from tts.edge_tts_client import DEFAULT_VOICE

        voice_id = DEFAULT_VOICE

    dub_manual_part(Path(args.part), provider=args.provider, voice_id=voice_id, force=args.force)


if __name__ == "__main__":
    main()

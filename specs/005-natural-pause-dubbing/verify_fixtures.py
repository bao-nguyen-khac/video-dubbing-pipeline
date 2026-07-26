"""
verify_fixtures.py — Dựng video mẫu + transcript.json cho các task verify của
005-natural-pause-dubbing (T001 thay thế).

Lý do tồn tại: quickstart.md §Chuẩn bị chung yêu cầu 2 video thật (VIDEO_PAUSE
có ≥3 khoảng lặng ≥1s, VIDEO_DENSE nói liên tục). Môi trường verify hiện tại
không tải được video từ TikTok/YouTube (IP datacenter bị chặn bot check), nên
fixture được TỰ SINH tại chỗ với cấu trúc khoảng lặng biết trước — thực ra chặt
hơn video tải về cho việc đo SC-001, vì mốc khoảng lặng là ground truth chính
xác thay vì phải suy ra từ ASR.

Sinh ra (dưới specs/005-natural-pause-dubbing/fixtures/):
  video_pause.mp4  + transcript_pause.json   — 4 khoảng lặng ≥1s
  video_dense.mp4  + transcript_dense.json   — nói liên tục, gap ≤0.15s

Chạy: .venv/bin/python specs/005-natural-pause-dubbing/verify_fixtures.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SOURCE_VOICE = "en-US-AriaNeural"  # video "gốc" giả lập là tiếng Anh, như ca dùng thật

# (start, end, text) — mốc thời gian là ground truth để đối chiếu SC-001.
# 4 khoảng lặng ≥1s: 1.6s, 2.0s, 1.5s, 1.3s
PAUSE_SEGMENTS = [
    (0.0, 3.2, "Most people set up their morning completely wrong."),
    (4.8, 8.0, "They check the phone before they even get out of bed."),
    (10.0, 13.5, "That single habit drains your focus for the whole day."),
    (15.0, 18.2, "Here is the fix that took me two weeks to find."),
    (19.5, 23.0, "Leave the phone in another room overnight. That is it."),
]

# Nói liên tục — gap ≤0.15s, không có khoảng lặng ≥1s nào
DENSE_SEGMENTS = [
    (0.0, 2.6, "Okay so listen up because this part matters a lot."),
    (2.7, 5.4, "The algorithm rewards watch time above everything else."),
    (5.5, 8.1, "That means your first three seconds decide the whole video."),
    (8.2, 10.9, "Start with motion, start with a question, never with a logo."),
    (11.0, 13.6, "Then keep every single sentence under two seconds long."),
    (13.7, 16.4, "Cut the pauses, cut the throat clearing, cut the intro."),
    (16.5, 19.1, "People decide in half a second whether to keep watching."),
    (19.2, 22.0, "Do that consistently and the reach takes care of itself."),
]


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Lệnh thất bại: {' '.join(cmd[:4])}...\n{proc.stderr[-800:]}")


def _tts_to_wav(text: str, out_path: Path) -> None:
    """Sinh giọng đọc tiếng Anh cho 1 câu nguồn (dùng edge-tts, không tốn key)."""
    import edge_tts

    mp3 = out_path.with_suffix(".mp3")

    async def _go() -> None:
        await edge_tts.Communicate(text, SOURCE_VOICE).save(str(mp3))

    asyncio.run(_go())
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
          "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out_path)])
    mp3.unlink(missing_ok=True)


def _silence_wav(path: Path, duration: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00\x00\x00\x00" * int(44100 * max(duration, 0.0)))


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build(name: str, segments: list[tuple[float, float, str]], work: Path) -> dict:
    """Dựng 1 fixture: audio khớp đúng mốc segment → mux với video test pattern."""
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    cursor = 0.0

    for i, (start, end, text) in enumerate(segments):
        if start > cursor + 0.01:
            gap = work / f"gap_{i:02d}.wav"
            _silence_wav(gap, start - cursor)
            parts.append(gap)

        speech = work / f"seg_{i:02d}.wav"
        _tts_to_wav(text, speech)

        # Ép giọng đọc vừa đúng khung [start, end] để mốc transcript là thật,
        # không phải xấp xỉ — apad rồi cắt cứng bằng -t.
        fitted = work / f"fit_{i:02d}.wav"
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(speech),
              "-af", "apad", "-t", f"{end - start:.3f}",
              "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(fitted)])
        parts.append(fitted)
        cursor = end

    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    audio = work / "audio.wav"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", str(listing), "-c", "copy", str(audio)])

    total = _duration(audio)
    video = FIXTURE_DIR / f"video_{name}.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error",
          "-f", "lavfi", "-i", f"testsrc=size=720x1280:rate=30:duration={total:.3f}",
          "-i", str(audio), "-c:v", "libx264", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "128k", "-shortest", str(video)])

    transcript = FIXTURE_DIR / f"transcript_{name}.json"
    transcript.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    {"start": s, "end": e, "text": t} for s, e, t in segments
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    gaps = [
        round(segments[i + 1][0] - segments[i][1], 2) for i in range(len(segments) - 1)
    ]
    return {
        "name": name,
        "video": str(video),
        "transcript": str(transcript),
        "duration": round(total, 2),
        "segments": len(segments),
        "gaps": gaps,
        "pauses_ge_1s": [g for g in gaps if g >= 1.0],
    }


def main() -> int:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"❌ Thiếu {tool} trong PATH", file=sys.stderr)
            return 1

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    work_root = FIXTURE_DIR / "_work"

    report = [
        build("pause", PAUSE_SEGMENTS, work_root / "pause"),
        build("dense", DENSE_SEGMENTS, work_root / "dense"),
    ]
    shutil.rmtree(work_root, ignore_errors=True)

    (FIXTURE_DIR / "fixtures.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for r in report:
        print(
            f"✅ {r['name']}: {r['duration']}s, {r['segments']} segment, "
            f"gaps={r['gaps']}, khoảng lặng ≥1s: {len(r['pauses_ge_1s'])} "
            f"({r['pauses_ge_1s']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

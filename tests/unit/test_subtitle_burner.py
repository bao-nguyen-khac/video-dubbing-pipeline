"""
tests/unit/test_subtitle_burner.py — Làm mờ vùng phụ đề gốc + burn phụ đề (009).

Bao phủ: `apply_hardsub_blur()` chỉ dựng chain cho vùng dùng được
(research.md §2); `burn_subtitles()` dựng đúng chuỗi overlay ảnh theo thời gian
và ép format MP4 tường minh (bug thật: file tạm `*.mp4.tmp` khiến ffmpeg không
đoán được định dạng).

⚠️ Constitution VI: MUST mock mọi lời gọi ffmpeg thật — không test nào chạy
subprocess ffmpeg thật.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from merge import subtitle_burner


REGION_USABLE = {
    "index": 0,
    "start": 0.0,
    "end": 6.0,
    "detected": True,
    "excluded": False,
    "box": {"x": 100, "y": 500, "w": 300, "h": 60},
}

REGION_NOT_DETECTED = {
    "index": 1,
    "start": 10.0,
    "end": 13.0,
    "detected": False,
    "excluded": False,
    "box": None,
}

REGION_EXCLUDED = {
    "index": 0,
    "start": 0.0,
    "end": 6.0,
    "detected": True,
    "excluded": True,  # người dùng đã đánh dấu lại là "không có phụ đề gốc"
    "box": {"x": 100, "y": 500, "w": 300, "h": 60},
}


class _FakeResult:
    returncode = 0
    stderr = ""


@pytest.fixture()
def capture_ffmpeg(monkeypatch):
    """Chặn subprocess.run, ghi lại cmd và giả lập ffmpeg có tạo file output."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"fake video")  # đối số cuối là output path
        return _FakeResult()

    monkeypatch.setattr(subtitle_burner.subprocess, "run", fake_run)
    return captured


# ─── apply_hardsub_blur ──────────────────────────────────────────────────────


def test_apply_hardsub_blur_skips_not_detected_and_excluded_regions(capture_ffmpeg, tmp_path):
    """FR-008 + US4: chỉ dựng chain filter cho vùng detected=true, excluded=false."""
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"fake")

    subtitle_burner.apply_hardsub_blur(
        video_path,
        tmp_path / "blurred_out.mp4",
        [REGION_USABLE, REGION_NOT_DETECTED, REGION_EXCLUDED],
    )

    joined = " ".join(capture_ffmpeg["cmd"])
    # Chỉ 1 vùng dùng được (REGION_USABLE) → đúng 1 chain crop/boxblur/overlay
    assert joined.count("boxblur") == 1
    assert joined.count("overlay") == 1


def test_apply_hardsub_blur_forces_mp4_format(capture_ffmpeg, tmp_path):
    """
    Bug thật: output là file tạm `*.mp4.tmp` nên ffmpeg không đoán được định
    dạng từ đuôi file ("Error initializing the muxer") — MUST ép `-f mp4`.
    """
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"fake")

    subtitle_burner.apply_hardsub_blur(
        video_path, tmp_path / "output_blurred.mp4.tmp", [REGION_USABLE]
    )

    cmd = capture_ffmpeg["cmd"]
    assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "mp4"


def test_apply_hardsub_blur_noop_when_no_usable_regions(monkeypatch, tmp_path):
    """Không có vùng nào dùng được → copy file, không dựng filter_complex nào."""

    def fake_run(cmd, **kwargs):
        raise AssertionError("Không được gọi ffmpeg khi không có vùng nào để mờ")

    monkeypatch.setattr(subtitle_burner.subprocess, "run", fake_run)

    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"nguyen ban")
    out_path = tmp_path / "out.mp4"

    subtitle_burner.apply_hardsub_blur(video_path, out_path, [REGION_NOT_DETECTED, REGION_EXCLUDED])

    assert out_path.read_bytes() == b"nguyen ban"


# ─── burn_subtitles (overlay ảnh, KHÔNG dùng libass) ────────────────────────


def _overlays(tmp_path, count=2):
    overlays = []
    for i in range(count):
        image = tmp_path / f"cue_{i}.png"
        image.write_bytes(b"fake png")
        overlays.append(
            {"image": image, "x": 10 * i, "y": 20 * i, "start": float(i), "end": float(i) + 1}
        )
    return overlays


def test_burn_subtitles_builds_overlay_chain_per_cue(capture_ffmpeg, tmp_path):
    video_path = tmp_path / "in.mp4"
    video_path.write_bytes(b"fake")

    subtitle_burner.burn_subtitles(video_path, _overlays(tmp_path, 3), tmp_path / "out.mp4")

    joined = " ".join(str(c) for c in capture_ffmpeg["cmd"])
    # Mỗi cue = 1 input ảnh + 1 overlay có enable theo mốc thời gian
    assert joined.count("overlay=") == 3
    assert joined.count("enable='between(t,") == 3
    assert "[outv]" in joined


def test_burn_subtitles_never_uses_libass_filter(capture_ffmpeg, tmp_path):
    """
    Bảo vệ quyết định kiến trúc: bộ lọc `subtitles` cần ffmpeg build kèm libass,
    KHÔNG có trên nhiều bản phổ biến (Homebrew macOS hiện tại) — dùng lại sẽ
    làm burn fail hoàn toàn dù code đúng.
    """
    video_path = tmp_path / "in.mp4"
    video_path.write_bytes(b"fake")

    subtitle_burner.burn_subtitles(video_path, _overlays(tmp_path), tmp_path / "out.mp4")

    cmd = capture_ffmpeg["cmd"]
    # Chỉ soi CHUỖI FILTER, không soi cả dòng lệnh: đường dẫn file tạm có thể
    # tình cờ chứa chữ "subtitles" và làm test báo sai
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "subtitles" not in filter_complex
    assert "force_style" not in filter_complex
    assert "-vf" not in cmd  # bộ lọc cũ dùng -vf subtitles=...


def test_burn_subtitles_uses_external_audio_when_given(capture_ffmpeg, tmp_path):
    video_path = tmp_path / "in.mp4"
    video_path.write_bytes(b"fake")
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"fake")

    subtitle_burner.burn_subtitles(
        video_path, _overlays(tmp_path, 2), tmp_path / "out.mp4", audio_path=audio_path
    )

    # 1 video + 2 ảnh = input index 0..2, nên audio là input index 3
    assert "3:a:0" in capture_ffmpeg["cmd"]


def test_burn_subtitles_maps_source_audio_by_default(capture_ffmpeg, tmp_path):
    video_path = tmp_path / "in.mp4"
    video_path.write_bytes(b"fake")

    subtitle_burner.burn_subtitles(video_path, _overlays(tmp_path, 2), tmp_path / "out.mp4")

    assert "0:a:0" in capture_ffmpeg["cmd"]


def test_burn_subtitles_raises_when_no_overlays(tmp_path):
    video_path = tmp_path / "in.mp4"
    video_path.write_bytes(b"fake")

    with pytest.raises(RuntimeError):
        subtitle_burner.burn_subtitles(video_path, [], tmp_path / "out.mp4")


def test_burn_subtitles_raises_when_source_missing(tmp_path):
    with pytest.raises(RuntimeError):
        subtitle_burner.burn_subtitles(
            tmp_path / "khong-ton-tai.mp4", _overlays(tmp_path), tmp_path / "out.mp4"
        )

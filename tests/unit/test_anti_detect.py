"""
tests/unit/test_anti_detect.py — Test Anti-Detect FFMPEG filter (apply_anti_detect,
chạy 1 lần ở đầu bước transcribing) & metadata scrubbing ở các bước burn/merge.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from merge import ffmpeg_merge, subtitle_burner


class _FakeResult:
    returncode = 0
    stderr = ""


@pytest.fixture()
def capture_ffmpeg_merge(monkeypatch):
    """Chặn subprocess.run trong ffmpeg_merge, ghi lại cmd và tạo file output."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"fake video")
        return _FakeResult()

    monkeypatch.setattr(ffmpeg_merge.subprocess, "run", fake_run)
    return captured


@pytest.fixture()
def capture_ffmpeg_subtitles(monkeypatch):
    """Chặn subprocess.run trong subtitle_burner, ghi lại cmd và tạo file output."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"fake video")
        return _FakeResult()

    monkeypatch.setattr(subtitle_burner.subprocess, "run", fake_run)
    return captured


def test_apply_anti_detect_includes_crop_scale_grading_and_metadata_scrubbing(capture_ffmpeg_merge, tmp_path):
    source_path = tmp_path / "source.mp4"
    out_path = tmp_path / "source_anti_detect.mp4"
    source_path.write_bytes(b"fake video")

    result = ffmpeg_merge.apply_anti_detect(source_path, out_path)

    assert result == out_path
    cmd = capture_ffmpeg_merge["cmd"]
    joined = " ".join(cmd)

    # Check Micro-Crop (kích thước ép chẵn, tránh libx264 lỗi "not divisible by 2")
    assert "crop=trunc(iw*0.975/2)*2:trunc(ih*0.975/2)*2" in joined
    # Check Scale phục hồi ĐÚNG độ phân giải gốc — dùng [orig] (chưa crop) làm
    # tham chiếu (`rw`/`rh`), KHÔNG dùng `scale=iw:ih` vì trong cùng chain đó
    # là kích thước SAU crop (bug thật đã confirm: scale=iw:ih không phục hồi
    # được độ phân giải, ra nhỏ hơn gốc ~2.5%)
    assert "[graded][orig]scale=trunc(rw/2)*2:trunc(rh/2)*2[v]" in joined
    # Check Color Grading
    assert "eq=brightness=0.01:contrast=1.02:saturation=1.04" in joined
    # Audio giữ nguyên, không re-encode (transcribe/ASR cần audio gốc y hệt)
    assert "-c:a" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "copy"
    # Check Metadata Scrubbing
    assert "-map_metadata" in cmd
    assert cmd[cmd.index("-map_metadata") + 1] == "-1"


def test_apply_anti_detect_is_noop_when_output_already_exists(monkeypatch, tmp_path):
    """Resume: nếu source_anti_detect.mp4 đã tồn tại và hợp lệ, không gọi lại ffmpeg."""
    called = False

    def fake_run(cmd, **kwargs):
        nonlocal called
        called = True
        return _FakeResult()

    monkeypatch.setattr(ffmpeg_merge.subprocess, "run", fake_run)

    source_path = tmp_path / "source.mp4"
    out_path = tmp_path / "source_anti_detect.mp4"
    source_path.write_bytes(b"fake video")
    out_path.write_bytes(b"already processed")

    result = ffmpeg_merge.apply_anti_detect(source_path, out_path)

    assert result == out_path
    assert called is False


def test_ffmpeg_merge_no_longer_applies_anti_detect_filters(capture_ffmpeg_merge, tmp_path):
    """
    010: crop/scale/color-grade đã chuyển sang apply_anti_detect() (chạy 1 lần
    ở bước transcribing) — _run_ffmpeg_merge coi video đầu vào là ĐÃ anti-detect
    sẵn, không áp filter/re-encode video lần nữa (giữ -c:v copy, nhanh).
    """
    video_path = tmp_path / "source_anti_detect.mp4"
    audio_path = tmp_path / "voice.wav"
    out_path = tmp_path / "output.mp4"

    video_path.write_bytes(b"fake video")
    audio_path.write_bytes(b"fake audio")

    ffmpeg_merge._run_ffmpeg_merge(video_path, audio_path, out_path)

    cmd = capture_ffmpeg_merge["cmd"]
    joined = " ".join(cmd)

    assert "crop=" not in joined
    assert "eq=brightness" not in joined
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "-map_metadata" in cmd
    assert cmd[cmd.index("-map_metadata") + 1] == "-1"


def test_ffmpeg_merge_with_bg_no_longer_applies_anti_detect_filters(capture_ffmpeg_merge, tmp_path):
    video_path = tmp_path / "source_anti_detect.mp4"
    audio_path = tmp_path / "voice.wav"
    bg_path = tmp_path / "bg.wav"
    out_path = tmp_path / "output.mp4"

    video_path.write_bytes(b"fake video")
    audio_path.write_bytes(b"fake audio")
    bg_path.write_bytes(b"fake bg")

    ffmpeg_merge._run_ffmpeg_merge_with_background(video_path, audio_path, bg_path, out_path)

    cmd = capture_ffmpeg_merge["cmd"]
    joined = " ".join(cmd)

    assert "crop=" not in joined
    assert "eq=brightness" not in joined
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "-map_metadata" in cmd
    assert cmd[cmd.index("-map_metadata") + 1] == "-1"


def test_subtitle_burner_includes_metadata_scrubbing(capture_ffmpeg_subtitles, tmp_path):
    video_path = tmp_path / "source.mp4"
    out_path = tmp_path / "output.mp4"
    video_path.write_bytes(b"fake video")

    overlays = [{
        "image": tmp_path / "cue1.png",
        "x": 100,
        "y": 200,
        "start": 0.0,
        "end": 2.0,
    }]
    Path(overlays[0]["image"]).write_bytes(b"fake png")

    subtitle_burner.burn_subtitles(video_path, overlays, out_path)

    cmd = capture_ffmpeg_subtitles["cmd"]
    assert "-map_metadata" in cmd
    assert cmd[cmd.index("-map_metadata") + 1] == "-1"

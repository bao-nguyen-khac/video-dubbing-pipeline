"""
tests/unit/test_script_to_video_merge.py — concat_wavs()/mux_part_video()
của merge/script_to_video_merge.py (v3: nối voice từng screen thành
full-narration.wav rồi ghép 1 lần vào merge.mp4 người dùng tự nối — khác v2,
không còn concat video/mux-per-screen).

Không gọi ffmpeg thật — chặn subprocess.run và kiểm tra cấu trúc lệnh, theo
mẫu tests/unit/test_anti_detect.py. `concat_wavs()` tái dùng
`tts.segment_synthesizer._concat_wavs()` nên chỉ cần test hành vi wrapper
(đường dẫn/thứ tự), không lặp lại test của hàm gốc.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from merge import script_to_video_merge as s2v_merge


class _FakeResult:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture()
def capture_ffmpeg(monkeypatch):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"fake output")
        return _FakeResult()

    monkeypatch.setattr(s2v_merge.subprocess, "run", fake_run)
    return captured


@pytest.fixture()
def failing_ffmpeg(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _FakeResult(returncode=1, stderr="boom")

    monkeypatch.setattr(s2v_merge.subprocess, "run", fake_run)


# ─── concat_wavs ────────────────────────────────────────────────────────────────


def test_concat_wavs_writes_files_in_order(tmp_path, monkeypatch):
    captured = {}

    def fake_concat_wavs(files, output_path):
        captured["files"] = files
        captured["output_path"] = output_path
        output_path.write_bytes(b"fake wav")
        return output_path

    monkeypatch.setattr(s2v_merge, "_concat_wavs", fake_concat_wavs)

    wavs = [tmp_path / "screen-1.wav", tmp_path / "screen-2.wav", tmp_path / "screen-3.wav"]
    output_path = tmp_path / "voice" / "full-narration.wav"

    result = s2v_merge.concat_wavs(wavs, output_path)

    assert result == output_path
    assert captured["files"] == wavs
    assert output_path.exists()


# ─── mux_part_video ─────────────────────────────────────────────────────────────


def test_mux_part_video_uses_apad_and_shortest(capture_ffmpeg, tmp_path):
    merged_video = tmp_path / "video-raw" / "merge.mp4"
    full_narration = tmp_path / "voice" / "full-narration.wav"
    output_path = tmp_path / "output.mp4"

    result = s2v_merge.mux_part_video(merged_video, full_narration, output_path)

    assert result == output_path
    cmd = capture_ffmpeg["cmd"]
    joined = " ".join(cmd)
    assert "[1:a]apad[a]" in joined
    assert "-shortest" in cmd
    assert "-c:v" in cmd and "copy" in cmd  # video giữ nguyên, không re-encode
    assert str(merged_video) in cmd
    assert str(full_narration) in cmd


def test_mux_part_video_raises_on_ffmpeg_error(failing_ffmpeg, tmp_path):
    with pytest.raises(RuntimeError):
        s2v_merge.mux_part_video(tmp_path / "merge.mp4", tmp_path / "full.wav", tmp_path / "out.mp4")


def test_mux_part_video_raises_when_output_missing(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return _FakeResult()  # returncode 0 nhưng KHÔNG tạo file output

    monkeypatch.setattr(s2v_merge.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        s2v_merge.mux_part_video(tmp_path / "merge.mp4", tmp_path / "full.wav", tmp_path / "out.mp4")

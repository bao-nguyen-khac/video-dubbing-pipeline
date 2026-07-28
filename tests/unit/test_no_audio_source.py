"""
tests/unit/test_no_audio_source.py — Video gốc không có audio stream.

Ca thật đã gặp: bài đăng TikTok dạng ảnh/slideshow (metadata "Bento4 Video
Handler") chỉ tải về được track hình, không có audio — ffmpeg trước đây thất
bại với thông điệp kỹ thuật khó hiểu ("Output file does not contain any
stream"). Giờ phải báo lỗi rõ ràng ngay từ bước transcribe(), trước khi chạm
tới ffmpeg.
"""

from __future__ import annotations

import subprocess

import pytest

from asr.transcriber import transcribe
from media_utils import has_audio_stream


def _make_video(path, with_audio: bool):
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
    ]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += ["-loglevel", "error", str(path)]
    subprocess.run(cmd, check=True, timeout=30)


def test_has_audio_stream_video_khong_am_thanh(tmp_path):
    video = tmp_path / "no_audio.mp4"
    _make_video(video, with_audio=False)

    assert has_audio_stream(video) is False


def test_has_audio_stream_video_co_am_thanh(tmp_path):
    video = tmp_path / "with_audio.mp4"
    _make_video(video, with_audio=True)

    assert has_audio_stream(video) is True


def test_has_audio_stream_file_khong_ton_tai_tra_false(tmp_path):
    """ffprobe báo lỗi (exit code khác 0) với file không tồn tại -> coi như
    không có audio. Không phải ca thực tế phát sinh trong pipeline: transcribe()
    đã kiểm tra source_path.exists() TRƯỚC has_audio_stream()."""
    assert has_audio_stream(tmp_path / "khong-ton-tai.mp4") is False


def test_transcribe_bao_loi_ro_rang_khi_khong_co_audio(tmp_path):
    video = tmp_path / "source.mp4"
    _make_video(video, with_audio=False)
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    with pytest.raises(RuntimeError) as e:
        transcribe(video, job_dir)

    message = str(e.value)
    assert "không có âm thanh" in message
    assert "slideshow" in message
    # Không được lộ thông điệp kỹ thuật của ffmpeg ra ngoài
    assert "does not contain any stream" not in message

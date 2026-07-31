"""
tests/unit/test_hardsub_detector.py — Vùng phụ đề gốc do người dùng tự khoanh (009).

OCR (Tesseract) đã bị loại bỏ khỏi module này — xác nhận thật trên nhiều video
là không khả thi (không đọc được phần lớn kiểu chữ có viền/màu nổi bật phổ biến
trên TikTok/YouTube Shorts). Thay vào đó người dùng tự khoanh vùng bằng mắt tại
chốt kiểm duyệt; module này chỉ lo (a) trích khung hình đại diện và (b) ghi
`hardsub_regions.json` từ vùng đã khoanh.

⚠️ Constitution VI (v1.8.0): mọi test ở đây MUST mock `ffmpeg`/`subprocess` —
không test nào được phụ thuộc ffmpeg thật có cài trên máy hay không.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from PIL import Image

from hardsub import detector


@pytest.fixture()
def fake_frame(tmp_path):
    """Tạo sẵn 1 ảnh PNG giả (100x50) tại đúng chỗ extract_representative_frame()
    sẽ ghi ra, và mock subprocess.run để không gọi ffmpeg thật."""
    def _make(job_dir):
        frame_path = job_dir / "hardsub_frame.png"
        Image.new("RGB", (100, 50), color=(10, 20, 30)).save(frame_path)
        return frame_path
    return _make


# ─── extract_representative_frame ────────────────────────────────────────────


def test_extract_representative_frame_calls_ffmpeg_and_reads_size(tmp_path, fake_frame, monkeypatch):
    monkeypatch.setattr(detector, "get_media_duration", lambda path: 20.0)

    def fake_run(cmd, **kwargs):
        # Mô phỏng ffmpeg ghi file ra đúng out_path (arg cuối của cmd)
        fake_frame(tmp_path)
        return None

    with patch("subprocess.run", side_effect=fake_run) as mock_run:
        video_path = tmp_path / "source.mp4"
        video_path.write_bytes(b"fake")

        out_path, frame_size = detector.extract_representative_frame(video_path, tmp_path)

    assert mock_run.called
    assert out_path == tmp_path / "hardsub_frame.png"
    assert frame_size == {"width": 100, "height": 50}


def test_extract_representative_frame_is_idempotent(tmp_path, fake_frame, monkeypatch):
    """File đã tồn tại → KHÔNG gọi lại ffmpeg (giữ đúng khung hình người dùng
    đã dùng để khoanh vùng qua các lượt lưu/duyệt lại)."""
    fake_frame(tmp_path)
    monkeypatch.setattr(detector, "get_media_duration", lambda path: 20.0)

    with patch("subprocess.run") as mock_run:
        video_path = tmp_path / "source.mp4"
        video_path.write_bytes(b"fake")

        out_path, frame_size = detector.extract_representative_frame(video_path, tmp_path)

    mock_run.assert_not_called()
    assert out_path == tmp_path / "hardsub_frame.png"
    assert frame_size == {"width": 100, "height": 50}


# ─── build_manual_regions ────────────────────────────────────────────────────


def test_build_manual_regions_uses_same_box_for_whole_video(tmp_path, monkeypatch):
    monkeypatch.setattr(detector, "get_media_duration", lambda path: 26.0)
    box = {"x": 10, "y": 700, "w": 200, "h": 40}

    out_path = detector.build_manual_regions(tmp_path / "source.mp4", None, tmp_path, box)
    data = json.loads(out_path.read_text())

    assert data["total_duration"] == 26.0
    assert len(data["regions"]) == 1
    region = data["regions"][0]
    assert region["start"] == 0.0
    assert region["end"] == 26.0
    assert region["detected"] is True
    assert region["excluded"] is False
    assert region["box"] == box
    assert data["no_hardsub_ranges"] == []


def test_build_manual_regions_excludes_declared_no_hardsub_range(tmp_path, monkeypatch):
    """FR-003/FR-004: khoảng đã khai báo KHÔNG có phụ đề gốc → không xuất hiện
    trong regions[] (không dùng box ở đó); no_hardsub_ranges ghi lại đúng
    khoảng đã parse (data-model.md §2)."""
    monkeypatch.setattr(detector, "get_media_duration", lambda path: 26.0)
    box = {"x": 10, "y": 700, "w": 200, "h": 40}

    out_path = detector.build_manual_regions(tmp_path / "source.mp4", "10-15", tmp_path, box)
    data = json.loads(out_path.read_text())

    segments = [(r["start"], r["end"]) for r in data["regions"]]
    assert segments == [(0.0, 10.0), (15.0, 26.0)]
    assert all(r["box"] == box for r in data["regions"])
    assert data["no_hardsub_ranges"] == [[10.0, 15.0]]


def test_build_manual_regions_overwrites_existing_file(tmp_path, monkeypatch):
    """KHÔNG idempotent — người dùng chỉnh lại vùng thì lượt sau phải ghi đè,
    khác hẳn `extract_representative_frame()` (giữ nguyên khung hình gốc)."""
    monkeypatch.setattr(detector, "get_media_duration", lambda path: 26.0)
    first_box = {"x": 10, "y": 700, "w": 200, "h": 40}
    second_box = {"x": 20, "y": 600, "w": 150, "h": 30}

    detector.build_manual_regions(tmp_path / "source.mp4", None, tmp_path, first_box)
    out_path = detector.build_manual_regions(tmp_path / "source.mp4", None, tmp_path, second_box)
    data = json.loads(out_path.read_text())

    assert data["regions"][0]["box"] == second_box


def test_build_manual_regions_no_ranges_covering_whole_video_produces_no_regions(tmp_path, monkeypatch):
    monkeypatch.setattr(detector, "get_media_duration", lambda path: 26.0)
    box = {"x": 10, "y": 700, "w": 200, "h": 40}

    out_path = detector.build_manual_regions(tmp_path / "source.mp4", "0-26", tmp_path, box)
    data = json.loads(out_path.read_text())

    assert data["regions"] == []

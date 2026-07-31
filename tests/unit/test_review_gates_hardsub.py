"""
tests/unit/test_review_gates_hardsub.py — Tích hợp vùng phụ đề gốc do người
dùng tự khoanh vào chốt lời thoại (009 US4, tái dùng chốt kiểm duyệt của 008).

Bao phủ FR-012 (chỉ hiện khi bật đồng thời hardsub_blur_enabled + supervised),
FR-013 (không có gì khi tắt một trong hai). OCR đã bị loại bỏ (không khả thi
với phần lớn kiểu chữ có viền/màu nổi bật, xác nhận thật) — người dùng tự
khoanh vùng trên khung hình đại diện, xem hardsub/detector.py.
"""

from __future__ import annotations

from review import gates


def _touch_frame(job_dir):
    path = job_dir / "hardsub_frame.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return path


# ─── build_payload: hardsub_frame_url / hardsub_box ──────────────────────────


def test_build_payload_includes_hardsub_frame_when_both_enabled(make_job, tmp_jobs_dir):
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=[{"start": 0.0, "end": 2.0, "text": "xin chào"}],
        extra={
            "hardsub_blur_enabled": True,
            "hardsub_frame_size": {"width": 608, "height": 1080},
            "hardsub_box": {"x": 10, "y": 700, "w": 200, "h": 40},
            "hardsub_no_ranges": "0:00-0:05",
        },
    )
    job_dir = tmp_jobs_dir / job["job_id"]
    frame_path = _touch_frame(job_dir)
    job["artifacts"]["hardsub_frame"] = str(frame_path)

    payload = gates.build_payload(job, gates.GATE_TRANSCRIPT)

    assert payload["hardsub_frame_url"] == f"/api/jobs/{job['job_id']}/hardsub-frame"
    assert payload["hardsub_frame_size"] == {"width": 608, "height": 1080}
    assert payload["hardsub_box"] == {"x": 10, "y": 700, "w": 200, "h": 40}
    assert payload["hardsub_no_ranges"] == "0:00-0:05"


def test_build_payload_omits_hardsub_frame_when_hardsub_disabled(make_job, tmp_jobs_dir):
    """FR-013: hardsub_blur_enabled=false → field VẮNG MẶT."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=[{"start": 0.0, "end": 2.0, "text": "xin chào"}],
        extra={"hardsub_blur_enabled": False},
    )

    payload = gates.build_payload(job, gates.GATE_TRANSCRIPT)

    assert "hardsub_frame_url" not in payload
    assert "hardsub_box" not in payload


def test_build_payload_omits_hardsub_frame_when_not_supervised(make_job, tmp_jobs_dir):
    """FR-013: không bật Quản lý pipeline → field VẮNG MẶT dù hardsub bật."""
    job = make_job(
        status="awaiting_review",
        supervised=False,
        reviewed_segments=[{"start": 0.0, "end": 2.0, "text": "xin chào"}],
        extra={"hardsub_blur_enabled": True},
    )
    job_dir = tmp_jobs_dir / job["job_id"]
    frame_path = _touch_frame(job_dir)
    job["artifacts"]["hardsub_frame"] = str(frame_path)

    # Job không supervised thì thực tế không đi qua build_payload() ở gate này,
    # nhưng nếu có gọi nhầm, field vẫn phải vắng mặt.
    payload = gates.build_payload(job, gates.GATE_TRANSCRIPT)

    assert "hardsub_frame_url" not in payload


def test_build_payload_omits_hardsub_frame_when_not_yet_extracted(make_job):
    """Khung hình chưa trích được (lỗi ffmpeg hiếm gặp, US3) → field VẮNG MẶT."""
    job = make_job(
        status="awaiting_review",
        supervised=True,
        review_gate="transcript",
        reviewed_segments=[{"start": 0.0, "end": 2.0, "text": "xin chào"}],
        extra={"hardsub_blur_enabled": True},
    )

    payload = gates.build_payload(job, gates.GATE_TRANSCRIPT)

    assert "hardsub_frame_url" not in payload


# ─── save_hardsub_box ────────────────────────────────────────────────────────


def test_save_hardsub_box_sets_job_field():
    job: dict = {}
    gates.save_hardsub_box(job, {"x": 1, "y": 2, "w": 3, "h": 4})

    assert job["hardsub_box"] == {"x": 1, "y": 2, "w": 3, "h": 4}

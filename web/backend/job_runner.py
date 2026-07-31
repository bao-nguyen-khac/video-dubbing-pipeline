"""
web/backend/job_runner.py — Chạy pipeline.run_pipeline() trong background
thread để không block request HTTP (research.md).
"""

from __future__ import annotations

import threading

from pipeline import run_pipeline


def start_job(
    url: str,
    script_mode: str,
    job_id: str | None = None,
    dynamic_captions: bool = False,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
    supervised: bool = False,
    hardsub_blur_enabled: bool = False,
    hardsub_no_ranges: str | None = None,
) -> None:
    """
    Spawn một daemon thread chạy pipeline.run_pipeline(). Không trả về gì —
    tiến trình job được theo dõi qua jobs/{job_id}/job.json, không qua giá trị
    trả về của hàm này.
    """
    thread = threading.Thread(
        target=_run_and_swallow_exit,
        args=(
            url,
            script_mode,
            job_id,
            dynamic_captions,
            tts_provider,
            voice_id,
            supervised,
            hardsub_blur_enabled,
            hardsub_no_ranges,
        ),
        daemon=True,
    )
    thread.start()


def _run_and_swallow_exit(
    url: str,
    script_mode: str,
    job_id: str | None,
    dynamic_captions: bool = False,
    tts_provider: str = "edge-tts",
    voice_id: str | None = None,
    supervised: bool = False,
    hardsub_blur_enabled: bool = False,
    hardsub_no_ranges: str | None = None,
) -> None:
    """
    run_pipeline() tự gọi sys.exit() khi hoàn tất/lỗi (thiết kế cho CLI). Trong
    thread nền, SystemExit chỉ dừng thread đó — "nuốt" nó ở đây để tránh in
    traceback thừa; trạng thái thật luôn nằm trong job.json.
    """
    try:
        run_pipeline(
            url,
            script_mode,
            job_id,
            dynamic_captions=dynamic_captions,
            tts_provider=tts_provider,
            voice_id=voice_id,
            supervised=supervised,
            hardsub_blur_enabled=hardsub_blur_enabled,
            hardsub_no_ranges=hardsub_no_ranges,
        )
    except SystemExit:
        pass
    except Exception as e:
        print(f"[job_runner] Lỗi không mong đợi khi chạy job nền: {e}")

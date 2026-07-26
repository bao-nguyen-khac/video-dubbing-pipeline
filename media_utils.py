"""media_utils.py — Shared ffmpeg/ffprobe helper dùng chung giữa các module."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_media_duration(media_path: str | Path) -> float:
    """Lấy thời lượng file media (video/audio) bằng ffprobe (giây)."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return 0.0

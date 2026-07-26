"""
env_check.py — Kiểm tra môi trường runtime trước khi chạy pipeline (T006, FR-008).

Checks:
1. ffmpeg có trong PATH không
2. 9router có phản hồi tại http://localhost:20128 không
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
import urllib.error

# Đọc từ env (.env ở repo root) — cùng biến với script_gen/router_client.py,
# ROUTER_BASE_URL là base URL đầy đủ kiểu OpenAI SDK (đã có /v1)
ROUTER_BASE_URL = os.environ.get("ROUTER_BASE_URL", "http://localhost:20128/v1")
ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", "9router")


def check_ffmpeg() -> tuple[bool, str]:
    """Kiểm tra ffmpeg có trong PATH."""
    path = shutil.which("ffmpeg")
    if path:
        return True, f"✅ ffmpeg tìm thấy: {path}"
    return False, "❌ ffmpeg không tìm thấy trong PATH. Cài đặt: brew install ffmpeg"


def check_9router() -> tuple[bool, str]:
    """Kiểm tra 9router có phản hồi tại localhost:20128."""
    try:
        req = urllib.request.Request(
            f"{ROUTER_BASE_URL}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {ROUTER_API_KEY}",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, f"✅ 9router phản hồi tại {ROUTER_BASE_URL}"
            return False, f"❌ 9router trả về HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, (
                f"❌ 9router từ chối xác thực (401) tại {ROUTER_BASE_URL}\n"
                "   → Kiểm tra lại ROUTER_API_KEY trong .env."
            )
        return False, f"❌ 9router trả về HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, (
            f"❌ Không thể kết nối 9router tại {ROUTER_BASE_URL}: {e.reason}\n"
            "   → Hãy đảm bảo 9router đang chạy và ROUTER_BASE_URL đúng."
        )
    except Exception as e:
        return False, f"❌ Lỗi kiểm tra 9router: {e}"


def run_checks(raise_on_fail: bool = False) -> bool:
    """
    Chạy toàn bộ môi trường checks.

    Args:
        raise_on_fail: Nếu True, raise RuntimeError khi có check thất bại.

    Returns:
        True nếu tất cả checks pass, False nếu có lỗi.
    """
    checks = [
        check_ffmpeg,
        check_9router,
    ]

    all_pass = True
    for check_fn in checks:
        ok, message = check_fn()
        print(message)
        if not ok:
            all_pass = False

    if not all_pass and raise_on_fail:
        raise RuntimeError(
            "Môi trường chưa sẵn sàng. Xem thông tin lỗi ở trên."
        )

    return all_pass


if __name__ == "__main__":
    ok = run_checks()
    sys.exit(0 if ok else 1)

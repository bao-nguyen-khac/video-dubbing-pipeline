"""
env_check.py — Kiểm tra môi trường runtime trước khi chạy pipeline (T006, FR-008).

Checks:
1. ffmpeg có trong PATH không
2. 9router có phản hồi tại http://localhost:20128 không — nếu không, kiểm tra
   tiếp OpenRouter dự phòng (cùng cơ chế fallback của script_gen/router_client.py)
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
import urllib.error

from dotenv import load_dotenv

# Load .env ở repo root TRƯỚC khi đọc os.environ bên dưới — chạy trực tiếp
# `python env_check.py` không đi qua pipeline.py/web.backend.main (2 chỗ đã
# load_dotenv sẵn), thiếu dòng này thì mọi biến rơi về default localhost và
# check báo sai.
load_dotenv()

# Đọc từ env (.env ở repo root) — cùng biến với script_gen/router_client.py,
# ROUTER_BASE_URL là base URL đầy đủ kiểu OpenAI SDK (đã có /v1)
ROUTER_BASE_URL = os.environ.get("ROUTER_BASE_URL", "http://localhost:20128/v1")
ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", "9router")

# Fallback khi 9router không kết nối được — xem script_gen/router_client.py
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


def check_ffmpeg() -> tuple[bool, str]:
    """Kiểm tra ffmpeg có trong PATH."""
    path = shutil.which("ffmpeg")
    if path:
        return True, f"✅ ffmpeg tìm thấy: {path}"
    return False, "❌ ffmpeg không tìm thấy trong PATH. Cài đặt: brew install ffmpeg"


def _probe_models_endpoint(base_url: str, api_key: str, label: str) -> tuple[bool, str]:
    """GET {base_url}/models — dùng chung cho 9router và OpenRouter dự phòng."""
    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, f"{label} phản hồi tại {base_url}"
            return False, f"{label} trả về HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, f"{label} từ chối xác thực (401) tại {base_url}"
        return False, f"{label} trả về HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Không thể kết nối {label} tại {base_url}: {e.reason}"
    except Exception as e:
        return False, f"Lỗi kiểm tra {label}: {e}"


def check_llm_endpoint() -> tuple[bool, str]:
    """
    Kiểm tra endpoint LLM dùng để dịch/viết kịch bản: ưu tiên 9router, nếu
    không kết nối được thì thử OpenRouter dự phòng (đúng thứ tự mà
    `script_gen/router_client._chat_completion()` sẽ chạy lúc thật).
    """
    ok, message = _probe_models_endpoint(ROUTER_BASE_URL, ROUTER_API_KEY, "9router")
    if ok:
        return True, f"✅ {message}"

    if not OPENROUTER_API_KEY:
        return False, (
            f"❌ {message}\n"
            "   → Hãy đảm bảo 9router đang chạy và ROUTER_BASE_URL đúng,\n"
            "     hoặc điền OPENROUTER_API_KEY trong .env để dùng OpenRouter dự phòng."
        )

    fb_ok, fb_message = _probe_models_endpoint(
        OPENROUTER_BASE_URL, OPENROUTER_API_KEY, "OpenRouter"
    )
    if fb_ok:
        return True, (
            f"⚠️  {message}\n"
            f"✅ Dùng OpenRouter dự phòng: {fb_message}\n"
            "   → Lưu ý: fallback chỉ áp dụng cho dịch/viết kịch bản (LLM).\n"
            "     Provider giọng đọc 'router-tts' vẫn cần 9router; dùng edge-tts/lucyai thay thế."
        )

    return False, (
        f"❌ {message}\n"
        f"❌ OpenRouter dự phòng cũng lỗi: {fb_message}\n"
        "   → Kiểm tra ROUTER_BASE_URL / OPENROUTER_API_KEY trong .env."
    )


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
        check_llm_endpoint,
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

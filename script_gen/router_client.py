"""
script_gen/router_client.py — Gọi 9router (OpenAI-compatible) để tạo kịch bản.

Hỗ trợ 2 mode:
- translate: Dịch transcript sang tiếng Việt (US1)
- rewrite:   Viết lại kịch bản mới theo ý chính (US3)

9router chạy tại http://localhost:20128/v1 (OpenAI-compatible API).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────

# Đọc từ env (.env ở repo root, xem .env.example) — không hardcode secret/model
# trong code. ROUTER_BASE_URL là base URL đầy đủ kiểu OpenAI SDK (đã có /v1).
ROUTER_BASE_URL = os.environ.get("ROUTER_BASE_URL", "http://localhost:20128/v1")
ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", "9router")
DEFAULT_MODEL = os.environ.get("ROUTER_MODEL", "gpt-4o-mini")

# ─── Prompts ─────────────────────────────────────────────────────────────────

TRANSLATE_SYSTEM = """Bạn là chuyên gia dịch thuật và viết kịch bản video ngắn.
Nhiệm vụ: Dịch văn bản đầu vào sang tiếng Việt tự nhiên, phù hợp để đọc thành tiếng (Text-to-Speech).

Quy tắc:
- Dịch đầy đủ, tự nhiên như người Việt nói chuyện hằng ngày
- Giữ nguyên thuật ngữ chuyên môn nếu không có từ tiếng Việt tương đương
- KHÔNG thêm bình luận, tiêu đề hay chú thích — chỉ trả về bản dịch tiếng Việt thuần túy
- Giữ đúng nhịp điệu, dừng đúng chỗ ngắt câu để khi TTS đọc sẽ tự nhiên"""

REWRITE_SYSTEM = """Bạn là copywriter chuyên viết kịch bản video ngắn viral cho TikTok/Douyin.
Nhiệm vụ: Dựa trên nội dung transcript đầu vào, viết lại một kịch bản hoàn toàn mới bằng tiếng Việt.

Quy tắc:
- KHÔNG dịch từng câu — hãy nắm ý chính rồi viết lại bằng ngôn ngữ của bạn
- Mở đầu bằng hook mạnh (câu hỏi, số liệu, hoặc tuyên bố táo bạo) trong 5 giây đầu
- Giọng văn năng động, gần gũi, phù hợp với người xem trẻ Việt Nam
- Giữ đúng chủ đề và thông điệp chính của video gốc
- Độ dài tương đương transcript gốc (để khớp với thời lượng video)
- KHÔNG thêm tiêu đề hay chú thích — chỉ trả về kịch bản thuần túy"""


# ─── Main Function ───────────────────────────────────────────────────────────


def generate_script(
    transcript_path: str | Path,
    job_dir: Path,
    mode: str = "translate",
) -> Path:
    """
    Tạo kịch bản tiếng Việt từ transcript qua 9router.

    Args:
        transcript_path: Đường dẫn tới transcript.json.
        job_dir: Thư mục job (jobs/{job_id}/).
        mode: 'translate' hoặc 'rewrite'.

    Returns:
        Path tới script.json vừa tạo.

    Raises:
        ValueError: Nếu mode không hợp lệ.
        RuntimeError: Nếu gọi API thất bại hoặc trả về kết quả trống.
    """
    if mode not in ("translate", "rewrite"):
        raise ValueError(f"script_mode không hợp lệ: {mode}. Dùng 'translate' hoặc 'rewrite'.")

    transcript_path = Path(transcript_path)
    job_dir = Path(job_dir)
    script_path = job_dir / "script.json"

    # Resume: nếu script.json đã tồn tại và parse được, bỏ qua (tránh trust nhầm
    # file bị corrupt/truncated do process bị kill giữa chừng)
    if script_path.exists() and script_path.stat().st_size > 10:
        try:
            with open(script_path, encoding="utf-8") as f:
                json.load(f)
            return script_path
        except (json.JSONDecodeError, OSError):
            pass  # file hỏng → tạo lại

    # Đọc transcript
    if not transcript_path.exists():
        raise RuntimeError(f"transcript.json không tồn tại: {transcript_path}")

    with open(transcript_path, encoding="utf-8") as f:
        transcript_data = json.load(f)

    full_text = transcript_data.get("full_text", "").strip()

    # Edge case: transcript rỗng (video không có lời thoại) — báo lỗi rõ ràng
    # ngay ở bước scripting thay vì "thành công giả" rồi để synthesize() fail mơ hồ sau
    if not full_text:
        raise RuntimeError(
            "Transcript rỗng — video gốc không có lời thoại để dịch. "
            "Hãy thử lại với --script-mode rewrite để tự soạn kịch bản mới."
        )

    # Gọi 9router
    content = _call_9router(full_text, mode)

    # Ghi script.json
    script_data = {
        "mode": mode,
        "content": content,
        "target_language": "vi",
    }
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    return script_path


def _call_9router(text: str, mode: str) -> str:
    """
    Gọi 9router API để xử lý văn bản.

    Args:
        text: Văn bản đầu vào (transcript).
        mode: 'translate' hoặc 'rewrite'.

    Returns:
        Kịch bản tiếng Việt.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai SDK chưa được cài đặt. Chạy: pip install openai"
        ) from e

    client = OpenAI(
        base_url=ROUTER_BASE_URL,
        api_key=ROUTER_API_KEY,
    )

    system_prompt = TRANSLATE_SYSTEM if mode == "translate" else REWRITE_SYSTEM
    user_message = f"Transcript:\n\n{text}"

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=2048,
        )
    except Exception as e:
        raise RuntimeError(
            f"Gọi 9router thất bại (mode={mode}): {e}\n"
            "Kiểm tra 9router đang chạy tại http://localhost:20128"
        ) from e

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(
            f"9router trả về kết quả rỗng (mode={mode}). "
            "Kiểm tra model đang hoạt động trong 9router."
        )

    return content.strip()

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
import re
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────

# Đọc từ env (.env ở repo root, xem .env.example) — không hardcode secret/model
# trong code. ROUTER_BASE_URL là base URL đầy đủ kiểu OpenAI SDK (đã có /v1).
ROUTER_BASE_URL = os.environ.get("ROUTER_BASE_URL", "http://localhost:20128/v1")
ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", "9router")
DEFAULT_MODEL = os.environ.get("ROUTER_MODEL", "gpt-4o-mini")

# Tốc độ đọc trung bình đo thật của voice vi-VN-NamMinhNeural ở tốc độ mặc định
# (003-dubbing-fixes-subtitles, research.md §2: 550 ký tự / 50.59s ≈ 10.9 ký
# tự/giây) — dùng để ước lượng ngân sách ký tự mục tiêu cho kịch bản (US2).
_CHARS_PER_SECOND_ESTIMATE = 10.9

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

# US3 (003-dubbing-fixes-subtitles): dịch sát nghĩa theo từng dòng đã đánh số,
# giữ đúng số dòng/thứ tự để zip lại với start/end của ASR segment gốc —
# Clarification Q2 của spec.md (phụ đề tự động dùng dịch sát nghĩa, không
# phải văn phong Sáng tạo)
SEGMENT_TRANSLATE_SYSTEM = (
    TRANSLATE_SYSTEM
    + """

Đầu vào là danh sách câu đã đánh số theo định dạng "[n] nội dung", mỗi dòng 1
câu. Dịch sát nghĩa TỪNG DÒNG sang tiếng Việt. QUAN TRỌNG: trả về ĐÚNG số
dòng và ĐÚNG thứ tự như đầu vào — không gộp 2 dòng thành 1, không tách 1 dòng
thành nhiều dòng, không bỏ sót dòng nào, kể cả dòng chỉ có 1-2 từ. Trả về mỗi
dòng theo định dạng "[n] bản dịch", không thêm giải thích/tiêu đề nào khác."""
)


# ─── Main Function ───────────────────────────────────────────────────────────


def estimate_target_char_budget(source_duration: float | None) -> int | None:
    """
    Ước lượng ngân sách ký tự mục tiêu để giọng đọc khớp gần đúng
    source_duration (US2, research.md §2 — sửa lệch thời lượng bằng cách cho
    LLM biết trước con số cụ thể thay vì chỉ nói định tính "tương đương").

    Returns None nếu source_duration không hợp lệ (không áp dụng ràng buộc).
    """
    if not source_duration or source_duration <= 0:
        return None
    return round(source_duration * _CHARS_PER_SECOND_ESTIMATE)


def generate_script(
    transcript_path: str | Path,
    job_dir: Path,
    mode: str = "translate",
    source_duration: float | None = None,
) -> Path:
    """
    Tạo kịch bản tiếng Việt từ transcript qua 9router.

    Args:
        transcript_path: Đường dẫn tới transcript.json.
        job_dir: Thư mục job (jobs/{job_id}/).
        mode: 'translate' hoặc 'rewrite'.
        source_duration: Thời lượng video gốc (giây), dùng để tính ngân sách
            ký tự mục tiêu chèn vào prompt (US2). None → không áp dụng.

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

    # Gọi 9router. Ngân sách ký tự (US2) CHỈ áp dụng cho 'rewrite' — thử
    # nghiệm thật cho thấy áp cả vào 'translate' khiến model hiểu nhầm là
    # được phép cắt bớt nội dung, dịch thiếu hẳn 1/3 đầu video (xem tasks.md
    # T013, phát hiện lúc verify). 'translate' giữ nguyên yêu cầu dịch đầy đủ
    # như trước, chỉ dựa vào rate-adjustment của TTS để khớp thời lượng.
    target_char_budget = estimate_target_char_budget(source_duration) if mode == "rewrite" else None
    content = _call_9router(full_text, mode, target_char_budget)

    # Rewrite thường undershoot ngân sách rất xa ở lượt đầu (model không đếm
    # ký tự chính xác, độ lệch giữa các lượt gọi cũng dao động mạnh — thử
    # nghiệm thật cho thấy 1 lần retry chưa đủ ổn định). Thử tối đa 2 lần
    # retry (tối đa 3 lượt gọi), dừng sớm khi đạt ≥85% ngân sách, luôn giữ
    # bản dài nhất trong số các lượt đã thử (không bao giờ tệ hơn lượt đầu).
    if mode == "rewrite" and target_char_budget:
        best = content
        for attempt in range(2):
            if len(best) >= target_char_budget * 0.85:
                break
            retry_content = _call_9router(
                full_text,
                mode,
                target_char_budget,
                retry_feedback=(
                    f"Bản kịch bản trước bạn viết chỉ có {len(best)} ký tự, "
                    f"NGẮN HƠN nhiều so với mức tối thiểu cần đạt là "
                    f"{target_char_budget} ký tự. Hãy viết lại, giữ đúng ý "
                    "tưởng/phong cách nhưng MỞ RỘNG chi tiết, ví dụ, miêu tả "
                    f"tự nhiên hơn để đạt ít nhất {target_char_budget} ký tự."
                ),
                # Retry: hạ temperature để model bám sát chỉ dẫn độ dài hơn,
                # bớt "sáng tạo" theo hướng rút gọn
                temperature=0.4,
            )
            if len(retry_content) > len(best):
                best = retry_content
        content = best

    # Ghi script.json
    script_data = {
        "mode": mode,
        "content": content,
        "target_language": "vi",
    }
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    return script_path


def generate_subtitle_script(transcript_path: str | Path, job_dir: Path) -> Path:
    """
    Sinh script.json cho US3 (script_mode="subtitle") — dịch sát nghĩa theo
    từng ASR segment (translate_segments()) thay vì dịch nguyên khối, để giữ
    đúng mốc thời gian cho phụ đề (data-model.md Script.segments).

    Returns:
        Path tới script.json vừa tạo.

    Raises:
        RuntimeError: Nếu transcript rỗng, gọi API thất bại, hoặc số dòng
            dịch trả về không khớp số segment.
    """
    transcript_path = Path(transcript_path)
    job_dir = Path(job_dir)
    script_path = job_dir / "script.json"

    if script_path.exists() and script_path.stat().st_size > 10:
        try:
            with open(script_path, encoding="utf-8") as f:
                json.load(f)
            return script_path
        except (json.JSONDecodeError, OSError):
            pass

    if not transcript_path.exists():
        raise RuntimeError(f"transcript.json không tồn tại: {transcript_path}")

    with open(transcript_path, encoding="utf-8") as f:
        transcript_data = json.load(f)

    segments = transcript_data.get("segments", [])
    if not segments:
        raise RuntimeError(
            "Transcript rỗng — video gốc không có lời thoại để tạo phụ đề."
        )

    cues = translate_segments(segments)

    script_data = {
        "mode": "subtitle",
        "content": "",
        "target_language": "vi",
        "segments": cues,
    }
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    return script_path


def _call_9router(
    text: str,
    mode: str,
    target_char_budget: int | None = None,
    retry_feedback: str | None = None,
    temperature: float = 0.7,
) -> str:
    """
    Gọi 9router API để xử lý văn bản.

    Args:
        text: Văn bản đầu vào (transcript).
        mode: 'translate' hoặc 'rewrite'.
        target_char_budget: Ngân sách ký tự mục tiêu (US2, chỉ áp dụng
            'rewrite') — chèn vào system prompt dưới dạng mức TỐI THIỂU cần
            đạt, không phải mức trần được phép cắt xuống.
        retry_feedback: Nếu có, thêm vào cuối user message làm phản hồi cụ
            thể cho lượt gọi lại (VD lượt trước quá ngắn) — giúp model sửa
            đúng vấn đề thay vì đoán lại từ đầu.
        temperature: Mặc định 0.7; các lượt retry độ dài (US2) hạ xuống để
            model bám sát chỉ dẫn hơn thay vì "sáng tạo" theo hướng rút gọn.

    Returns:
        Kịch bản tiếng Việt.
    """
    system_prompt = TRANSLATE_SYSTEM if mode == "translate" else REWRITE_SYSTEM
    if target_char_budget:
        # Ngân sách ký tự (US2, research.md §2) — CỐ TÌNH viết như một mức
        # TỐI THIỂU, không phải mức trần: thử nghiệm thật cho thấy nếu chỉ nói
        # "khoảng N ký tự" mà không nói rõ hướng, model có xu hướng viết NGẮN
        # hơn hẳn N (undershoot 2-3 lần), không phải dài hơn.
        system_prompt += (
            f"\n\nĐỘ DÀI MỤC TIÊU: bài viết PHẢI DÀI ÍT NHẤT {target_char_budget} "
            "ký tự (tính cả dấu câu/khoảng trắng) để khớp thời lượng video gốc "
            "khi đọc thành tiếng — đây là mức TỐI THIỂU, không phải mức trần. "
            "Nếu ý tưởng chính ngắn, hãy CHỦ ĐỘNG diễn giải, thêm ví dụ, chi "
            "tiết hoặc miêu tả tự nhiên (không bịa thông tin sai lệch chủ đề "
            "gốc) để đạt đủ độ dài. TUYỆT ĐỐI KHÔNG viết ngắn hơn mức này."
        )
    user_message = f"Transcript:\n\n{text}"
    if retry_feedback:
        user_message += f"\n\n---\n{retry_feedback}"

    try:
        return _chat_completion(system_prompt, user_message, temperature)
    except RuntimeError as e:
        raise RuntimeError(f"Gọi 9router thất bại (mode={mode}): {e}") from e


def _chat_completion(system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
    """
    Gọi 9router (OpenAI-compatible chat completion) — helper dùng chung cho
    `_call_9router()` (translate/rewrite nguyên khối) và `translate_segments()`
    (dịch theo segment cho US3).

    Raises:
        RuntimeError: Nếu gọi API thất bại hoặc trả về kết quả trống.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai SDK chưa được cài đặt. Chạy: pip install openai"
        ) from e

    client = OpenAI(base_url=ROUTER_BASE_URL, api_key=ROUTER_API_KEY)

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=4096,
        )
    except Exception as e:
        raise RuntimeError(
            f"{e}\nKiểm tra 9router đang chạy tại {ROUTER_BASE_URL}"
        ) from e

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError("9router trả về kết quả rỗng. Kiểm tra model đang hoạt động trong 9router.")

    return content.strip()


def translate_segments(segments: list[dict]) -> list[dict]:
    """
    Dịch sát nghĩa từng ASR segment, giữ nguyên start/end gốc — dùng cho US3
    (script_mode="subtitle", data-model.md Script.segments). Gọi 1 lần API
    duy nhất cho toàn bộ segments (đánh số dòng) để LLM có ngữ cảnh xuyên
    suốt thay vì dịch rời rạc từng câu riêng lẻ.

    Args:
        segments: List[{"start": float, "end": float, "text": str}] từ
            transcript.json (asr/transcriber.py).

    Returns:
        List[{"start": float, "end": float, "source_text": str,
        "translated_text": str}], cùng độ dài và thứ tự với segments đầu vào.

    Raises:
        RuntimeError: Nếu gọi API thất bại, hoặc số dòng trả về không khớp số
            segment đầu vào (không cố "đoán" ghép sai — thà báo lỗi rõ còn
            hơn tạo phụ đề lệch thời gian).
    """
    if not segments:
        return []

    numbered_input = "\n".join(f"[{i + 1}] {seg['text'].strip()}" for i, seg in enumerate(segments))
    raw = _chat_completion(SEGMENT_TRANSLATE_SYSTEM, numbered_input, temperature=0.3)
    translations = _parse_numbered_lines(raw)

    if len(translations) != len(segments):
        raise RuntimeError(
            f"Dịch theo segment thất bại: model trả về {len(translations)} dòng, "
            f"cần đúng {len(segments)} dòng để khớp mốc thời gian ASR gốc."
        )

    return [
        {
            "start": seg["start"],
            "end": seg["end"],
            "source_text": seg["text"].strip(),
            "translated_text": translated,
        }
        for seg, translated in zip(segments, translations)
    ]


def _parse_numbered_lines(raw: str) -> list[str]:
    """Trích các dòng "[n] nội dung" theo đúng thứ tự n, bỏ qua dòng lạ khác."""
    pattern = re.compile(r"^\s*\[(\d+)\]\s*(.*\S)?\s*$")
    numbered: dict[int, str] = {}
    for line in raw.splitlines():
        match = pattern.match(line)
        if match:
            numbered[int(match.group(1))] = (match.group(2) or "").strip()
    if not numbered:
        return []
    max_n = max(numbered.keys())
    return [numbered.get(n, "") for n in range(1, max_n + 1)]

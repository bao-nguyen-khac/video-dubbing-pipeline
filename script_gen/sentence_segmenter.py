"""
script_gen/sentence_segmenter.py — Cắt lại luồng từ (ASR word-timestamps) theo
đúng RANH GIỚI CÂU trước khi gom thành dubbing unit.

Vì sao cần: faster-whisper (model 'small', chạy CPU) tạo segment dài, nhiều câu
chạy liền và KHÔNG có dấu câu; ranh giới giữa các segment lại rơi vào giữa câu.
Cả VAD lẫn cắt-theo-khoảng-lặng đều không biết câu kết thúc ở đâu (không có dấu
câu để biết), nên `group_segments()` đôi khi buộc phải cắt giữa câu (khi gộp
lại sẽ vượt trần thời lượng).

Cách xử lý: dùng LLM (đã có sẵn cho bước dịch) CHÈN dấu ranh giới câu vào luồng
từ mà KHÔNG đổi từ nào, rồi cắt lại segment tại các ranh giới đó — cộng với mọi
khoảng lặng thật giữa 2 từ (≥ `_WORD_GAP_SPLIT`) để không mất nhịp nghỉ gốc.

An toàn: mọi lỗi (transcript cũ không có 'words', LLM lỗi, số từ trả về lệch)
đều rơi về giữ nguyên segment cũ — không bao giờ làm hỏng job.
"""

from __future__ import annotations

import os
from typing import Callable

# Dấu ranh giới câu LLM chèn — ký tự hiếm để không trùng nội dung thật.
_MARKER = "⟦S⟧"

# Khoảng lặng thật giữa 2 từ vẫn luôn là 1 điểm cắt (khớp ASR
# _WORD_GAP_SPLIT_THRESHOLD) — giữ nhịp nghỉ gốc của clip.
_WORD_GAP_SPLIT = 0.30

PUNCTUATE_SYSTEM = (
    "Bạn là công cụ tách câu. Đầu vào là một chuỗi từ đã được nhận dạng giọng "
    "nói, có thể thiếu dấu câu.\n"
    "Nhiệm vụ: chèn dấu " + _MARKER + " vào NGAY SAU mỗi chỗ KẾT THÚC một câu "
    "hoặc một ý trọn vẹn.\n"
    "QUY TẮC BẮT BUỘC:\n"
    "- TUYỆT ĐỐI không thêm, bớt, đổi, hay sắp xếp lại bất kỳ từ nào. Giữ "
    "nguyên chính xác mọi từ theo đúng thứ tự.\n"
    "- Chỉ được chèn thêm dấu " + _MARKER + " (và có thể thêm dấu câu . , ! ? "
    "nếu muốn). Không viết gì khác.\n"
    "- Không giải thích, không thêm tiêu đề. Trả về đúng chuỗi từ đã chèn dấu."
)


def _flatten_words(segments: list[dict]) -> list[dict] | None:
    """
    Gom 'words' của mọi segment thành 1 danh sách theo thứ tự thời gian.
    Trả None nếu bất kỳ segment nào thiếu 'words' (transcript cũ) — để chỗ gọi
    giữ nguyên hành vi cũ.
    """
    words: list[dict] = []
    for seg in segments:
        seg_words = seg.get("words")
        if not seg_words:
            return None
        words.extend(seg_words)
    return words or None


def _align_sentence_ends(words: list[dict], punctuated: str) -> list[int] | None:
    """
    Đọc chuỗi LLM trả về, xác định chỉ số từ (0-based) KẾT THÚC mỗi câu.

    Chỉ đếm vị trí từ + vị trí dấu `_MARKER`, bỏ qua mọi dấu câu LLM thêm vào —
    nên không phụ thuộc việc LLM có sửa nhẹ chính tả/dấu hay không. Nếu tổng số
    từ đếm được KHÁC len(words) (LLM thêm/bớt từ) → trả None để fallback.
    """
    text = punctuated.replace(_MARKER, f" {_MARKER} ")
    ends: list[int] = []
    word_index = -1
    for token in text.split():
        if token == _MARKER:
            if word_index >= 0:
                ends.append(word_index)
        else:
            word_index += 1

    if word_index + 1 != len(words):
        return None  # số từ lệch → không tin được, giữ nguyên segment cũ

    # Từ cuối luôn là ranh giới (kết thúc đoạn)
    last = len(words) - 1
    if not ends or ends[-1] != last:
        ends.append(last)
    return sorted(set(ends))


def _build_segments(words: list[dict], sentence_ends: list[int]) -> list[dict]:
    """Dựng segment mới: cắt tại ranh giới câu HOẶC khoảng lặng thật giữa 2 từ."""
    end_set = set(sentence_ends)

    def _mk(chunk: list[dict]) -> dict:
        return {
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "text": "".join(w["word"] for w in chunk).strip(),
        }

    segments: list[dict] = []
    current: list[dict] = [words[0]]
    for i in range(1, len(words)):
        prev, word = words[i - 1], words[i]
        gap = float(word["start"]) - float(prev["end"])
        if (i - 1) in end_set or gap >= _WORD_GAP_SPLIT:
            segments.append(_mk(current))
            current = []
        current.append(word)
    if current:
        segments.append(_mk(current))
    return segments


def resegment_by_sentences(
    segments: list[dict],
    llm_call: Callable[[str, str], str],
) -> list[dict]:
    """
    Cắt lại `segments` (transcript.json) theo ranh giới câu qua LLM.

    Args:
        segments: List[{"start","end","text","words":[...]}] từ transcript.
        llm_call: Hàm (system_prompt, user_message) -> str gọi LLM (thường là
            `router_client._chat_completion`), có sẵn fallback OpenRouter.

    Returns:
        Danh sách segment mới cắt theo câu, hoặc chính `segments` cũ nếu không
        áp dụng được (tắt qua env, thiếu word-timestamp, LLM lỗi, lệch số từ).
    """
    if os.environ.get("DISABLE_SENTENCE_RESEGMENT", "").strip() in ("1", "true", "True"):
        return segments

    words = _flatten_words(segments)
    if not words:
        return segments  # transcript cũ không có 'words' → giữ nguyên

    plain = " ".join(str(w["word"]).strip() for w in words if str(w["word"]).strip())
    if not plain:
        return segments

    try:
        punctuated = llm_call(PUNCTUATE_SYSTEM, plain)
    except Exception as e:  # noqa: BLE001 — LLM lỗi không được làm hỏng job
        print(f"[sentence_segmenter] LLM chèn dấu câu thất bại, giữ nhịp cắt cũ: {e}")
        return segments

    sentence_ends = _align_sentence_ends(words, punctuated)
    if sentence_ends is None:
        print("[sentence_segmenter] Số từ LLM trả về lệch với transcript, giữ nhịp cắt cũ")
        return segments

    new_segments = _build_segments(words, sentence_ends)
    print(
        f"[sentence_segmenter] Cắt lại theo câu: {len(segments)} segment ASR "
        f"→ {len(new_segments)} segment theo câu"
    )
    return new_segments

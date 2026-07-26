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

# Timeout gọi 9router. Mặc định OpenAI SDK là 600s — quá dài, một 9router treo
# sẽ giữ pipeline 10 phút trước khi kịp fallback, nên hạ xuống 120s (vẫn dư cho
# 1 lượt dịch cả transcript dài).
ROUTER_TIMEOUT = float(os.environ.get("ROUTER_TIMEOUT", "120"))

# Fallback khi 9router không kết nối được (timeout/refused/HTTP lỗi): gọi
# OpenRouter — cũng là endpoint OpenAI-compatible nên dùng lại nguyên luồng
# gọi, chỉ khác base_url/key/model. Chỉ bật khi OPENROUTER_API_KEY có trong
# .env; model 9router (vd `ag/gemini-3-flash-agent`) không tồn tại bên
# OpenRouter nên phải có OPENROUTER_MODEL riêng.
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"

# Tốc độ đọc trung bình đo thật của voice vi-VN-NamMinhNeural ở tốc độ mặc định
# (003-dubbing-fixes-subtitles, research.md §2: 550 ký tự / 50.59s ≈ 10.9 ký
# tự/giây) — dùng để ước lượng ngân sách ký tự mục tiêu. Từ 005 áp dụng theo
# TỪNG dubbing unit thay vì cho cả bài.
_CHARS_PER_SECOND_ESTIMATE = 10.9

# Ngưỡng gom ASR segment thành "dubbing unit" (005-natural-pause-dubbing,
# research.md §1) — faster-whisper cắt segment theo VAD/độ dài chứ không theo
# nhịp nghỉ ngữ nghĩa, nên phải gom lại trước khi lồng tiếng theo câu.
_GAP_SILENCE_THRESHOLD = 0.30   # khoảng trống nhỏ hơn = KHÔNG phải ngắt nghỉ thật
_MIN_UNIT_DURATION = 1.20       # unit ngắn hơn thì gộp tiếp (tránh vụn câu)
_MAX_UNIT_DURATION = 15.0       # trần gộp — giữ tính "theo câu"
_SHORT_UNIT_MERGE_MAX_GAP = 1.0  # chỉ gộp unit quá ngắn khi khoảng trống < ngưỡng này

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

# 005-natural-pause-dubbing (US2/FR-004): chế độ Sáng tạo cũng phải sinh nội
# dung theo đúng số nhịp/thứ tự của khung thời gian ASR gốc, để dùng chung cơ
# chế khớp nhịp với chế độ Dịch chuẩn. Giữ nguyên tinh thần viết lại sáng tạo
# của REWRITE_SYSTEM, chỉ thêm ràng buộc cấu trúc dòng (mượn cách diễn đạt đã
# verify thật của SEGMENT_TRANSLATE_SYSTEM).
SEGMENT_REWRITE_SYSTEM = (
    REWRITE_SYSTEM
    + """

Đầu vào là danh sách nhịp nói đã đánh số theo định dạng
"[n] (~N ký tự) nội dung gốc", mỗi dòng là MỘT nhịp nói độc lập của video gốc.
Với mỗi dòng, hãy viết lại sáng tạo bằng tiếng Việt nội dung của đúng nhịp đó
(KHÔNG dịch sát nghĩa từng từ).

QUAN TRỌNG:
- Trả về ĐÚNG số dòng và ĐÚNG thứ tự như đầu vào — không gộp 2 dòng thành 1,
  không tách 1 dòng thành nhiều dòng, không bỏ sót dòng nào, kể cả dòng chỉ có
  1-2 từ (nhịp cảm thán ngắn thì viết lại cũng ngắn tương ứng).
- "(~N ký tự)" là độ dài mục tiêu của riêng dòng đó để đọc vừa khung thời gian
  của nhịp gốc — hãy bám sát con số này, đừng viết dài gấp nhiều lần. Đây là
  chỉ dẫn nội bộ: TUYỆT ĐỐI KHÔNG chép lại "(~N ký tự)" vào kết quả, vì kết
  quả sẽ được đọc thành tiếng nguyên văn.
- Mỗi dòng phải đọc lên nghe trọn vẹn, tự nhiên như một nhịp nói; hook mạnh
  đặt ở dòng đầu tiên.
- Trả về mỗi dòng theo định dạng "[n] nội dung viết lại", không thêm giải
  thích/tiêu đề nào khác."""
)


# ─── Main Function ───────────────────────────────────────────────────────────


def group_segments(segments: list[dict]) -> list[dict]:
    """
    Gom ASR segment (`transcript.json.segments`) thành các "dubbing unit" —
    đơn vị nhỏ nhất được dịch/viết lại và tổng hợp giọng đọc độc lập
    (005-natural-pause-dubbing, research.md §1, data-model.md §1).

    Quy tắc gộp segment kế tiếp vào unit đang mở:
    1. Khoảng trống < `_GAP_SILENCE_THRESHOLD` (0.30s) → không phải ngắt nghỉ
       thật, gộp (FR-008: không chèn khoảng lặng giả).
    2. Unit đang mở còn ngắn hơn `_MIN_UNIT_DURATION` (1.20s) và khoảng trống
       < `_SHORT_UNIT_MERGE_MAX_GAP` (1.0s) → gộp để tránh câu vụn (FR-004).
    3. Cả 2 quy tắc trên đều bị chặn nếu unit sau khi gộp vượt
       `_MAX_UNIT_DURATION` (15s) — giữ tính "theo câu", không thoái hoá về
       cơ chế nguyên khối cũ. Đây là lý do duy nhất khiến 2 unit liền nhau có
       thể cách nhau < 0.30s.

    Args:
        segments: List[{"start": float, "end": float, "text": str}] từ
            transcript.json (asr/transcriber.py).

    Returns:
        List[{"index": int, "start": float, "end": float, "source_text": str}],
        index đánh số từ 0, không chồng lấn, tăng dần theo start.
    """
    units: list[dict] = []

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue  # segment rỗng (nhiễu VAD) — không tạo nhịp lồng tiếng riêng

        start = float(seg["start"])
        end = float(seg["end"])

        if units:
            current = units[-1]
            gap = start - current["end"]
            merged_duration = end - current["start"]
            current_duration = current["end"] - current["start"]

            fits_max = merged_duration <= _MAX_UNIT_DURATION
            no_real_pause = gap < _GAP_SILENCE_THRESHOLD
            too_short = (
                current_duration < _MIN_UNIT_DURATION
                and gap < _SHORT_UNIT_MERGE_MAX_GAP
            )

            if fits_max and (no_real_pause or too_short):
                current["end"] = end
                current["source_text"] = f"{current['source_text']} {text}".strip()
                continue

        units.append(
            {
                "index": len(units),
                "start": start,
                "end": end,
                "source_text": text,
            }
        )

    return units


def estimate_target_char_budget(source_duration: float | None) -> int | None:
    """
    Ước lượng ngân sách ký tự mục tiêu để giọng đọc khớp gần đúng
    `source_duration` — cho LLM biết trước con số cụ thể thay vì chỉ nói định
    tính "tương đương" (003 research.md §2).

    Từ 005 áp dụng theo TỪNG dubbing unit (`rewrite_segments()`) thay vì cho
    cả bài: model biết chính xác mỗi nhịp được bao nhiêu chữ, ràng buộc mạnh
    hơn hẳn ngân sách toàn bài.

    Returns None nếu source_duration không hợp lệ (không áp dụng ràng buộc).
    """
    if not source_duration or source_duration <= 0:
        return None
    return round(source_duration * _CHARS_PER_SECOND_ESTIMATE)


def generate_script(
    transcript_path: str | Path,
    job_dir: Path,
    mode: str = "translate",
) -> Path:
    """
    Tạo kịch bản tiếng Việt từ transcript qua 9router, chia THEO TỪNG NHỊP
    (005-natural-pause-dubbing, FR-001/FR-004).

    Khác cơ chế cũ: thay vì dịch/viết lại 1 khối văn bản rồi để TTS đọc liền
    mạch, transcript được gom thành dubbing unit (`group_segments()`) rồi
    dịch/viết lại đúng 1 dòng cho mỗi unit — giữ được mốc thời gian gốc để
    `tts/segment_synthesizer.py` đặt từng nhịp đúng chỗ.

    Args:
        transcript_path: Đường dẫn tới transcript.json.
        job_dir: Thư mục job (jobs/{job_id}/).
        mode: 'translate' hoặc 'rewrite'.

    Returns:
        Path tới script.json vừa tạo (luôn có mảng `segments`).

    Raises:
        ValueError: Nếu mode không hợp lệ.
        RuntimeError: Nếu transcript rỗng, gọi API thất bại, hoặc số dòng trả
            về không khớp số unit.
    """
    if mode not in ("translate", "rewrite"):
        raise ValueError(f"script_mode không hợp lệ: {mode}. Dùng 'translate' hoặc 'rewrite'.")

    transcript_path = Path(transcript_path)
    job_dir = Path(job_dir)
    script_path = job_dir / "script.json"

    # Resume: script.json chỉ hợp lệ khi parse được VÀ có 'segments' — file do
    # phiên bản pipeline cũ (trước 005) sinh ra không có 'segments' nên phải
    # tạo lại, thay vì nuôi thêm 1 nhánh fallback nguyên khối (research.md §7)
    if script_path.exists() and script_path.stat().st_size > 10:
        try:
            with open(script_path, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("segments"):
                return script_path
            print(
                "[router_client] script.json cũ không có 'segments' "
                "(tạo trước feature 005) — sinh lại theo từng nhịp"
            )
        except (json.JSONDecodeError, OSError):
            pass  # file hỏng → tạo lại

    # Đọc transcript
    if not transcript_path.exists():
        raise RuntimeError(f"transcript.json không tồn tại: {transcript_path}")

    with open(transcript_path, encoding="utf-8") as f:
        transcript_data = json.load(f)

    units = group_segments(transcript_data.get("segments", []))

    # Edge case: transcript rỗng (video không có lời thoại) — báo lỗi rõ ràng
    # ngay ở bước scripting thay vì "thành công giả" rồi để TTS fail mơ hồ sau
    if not units:
        raise RuntimeError(
            "Transcript rỗng — video gốc không có lời thoại để lồng tiếng."
        )

    print(f"[router_client] Gom {len(transcript_data.get('segments', []))} segment ASR → {len(units)} nhịp lồng tiếng")

    if mode == "translate":
        cues = translate_segments(units)
    else:
        cues = rewrite_segments(units)

    # Ghi script.json. `content` chỉ để đọc/debug — TTS nay dùng `segments`
    script_data = {
        "mode": mode,
        "content": " ".join(c["translated_text"] for c in cues if c["translated_text"]),
        "target_language": "vi",
        "segments": cues,
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


def _openrouter_config() -> tuple[str, str, str] | None:
    """
    Cấu hình OpenRouter dự phòng, hoặc None nếu chưa khai báo
    OPENROUTER_API_KEY trong .env (khi đó không có fallback).

    Đọc os.environ tại thời điểm gọi (không phải lúc import) để đúng cả khi
    load_dotenv() chạy sau lúc module này được import.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.environ.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip()
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip()
    return base_url, api_key, model


def _call_chat_api(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
) -> str:
    """
    Một lượt gọi chat completion tới endpoint OpenAI-compatible bất kỳ
    (9router hoặc OpenRouter — cùng giao thức nên dùng chung code).

    Raises:
        RuntimeError: Nếu gọi API thất bại hoặc trả về kết quả trống.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai SDK chưa được cài đặt. Chạy: pip install openai"
        ) from e

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=ROUTER_TIMEOUT)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=4096,
    )

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(f"Endpoint trả về kết quả rỗng. Kiểm tra model '{model}' còn hoạt động.")

    return content.strip()


def _chat_completion(system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
    """
    Gọi 9router (OpenAI-compatible chat completion) — helper dùng chung cho
    `translate_segments()` (Dịch chuẩn/Phụ đề tự động) và `rewrite_segments()`
    (Sáng tạo).

    Nếu 9router lỗi (timeout, connection refused, HTTP lỗi, kết quả rỗng) và
    .env có OPENROUTER_API_KEY thì tự động gọi lại qua OpenRouter thay vì làm
    hỏng cả job — cùng giao thức OpenAI-compatible nên kết quả trả về giữ
    nguyên định dạng, phần parse phía sau không đổi.

    Raises:
        RuntimeError: Nếu 9router lỗi và không có (hoặc cũng lỗi nốt) fallback.
    """
    try:
        return _call_chat_api(
            ROUTER_BASE_URL, ROUTER_API_KEY, DEFAULT_MODEL,
            system_prompt, user_message, temperature,
        )
    except Exception as primary_error:
        fallback = _openrouter_config()
        if fallback is None:
            raise RuntimeError(
                f"{primary_error}\nKiểm tra 9router đang chạy tại {ROUTER_BASE_URL} "
                "(chưa có OPENROUTER_API_KEY trong .env nên không có endpoint dự phòng)."
            ) from primary_error

        fb_base_url, fb_api_key, fb_model = fallback
        print(
            f"[router_client] 9router lỗi ({type(primary_error).__name__}: {primary_error}) "
            f"→ chuyển sang OpenRouter dự phòng (model {fb_model})"
        )
        try:
            return _call_chat_api(
                fb_base_url, fb_api_key, fb_model,
                system_prompt, user_message, temperature,
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"Cả 2 endpoint LLM đều thất bại.\n"
                f"  - 9router ({ROUTER_BASE_URL}, model {DEFAULT_MODEL}): {primary_error}\n"
                f"  - OpenRouter ({fb_base_url}, model {fb_model}): {fallback_error}"
            ) from fallback_error


def _segment_source_text(seg: dict) -> str:
    """
    Lấy text gốc của 1 phần tử đầu vào — chấp nhận cả ASR segment thô
    (`text`, từ transcript.json) lẫn dubbing unit đã gom (`source_text`, từ
    `group_segments()`).
    """
    return (seg.get("source_text") or seg.get("text") or "").strip()


def translate_segments(segments: list[dict]) -> list[dict]:
    """
    Dịch sát nghĩa từng segment/nhịp, giữ nguyên start/end gốc. Gọi 1 lần API
    duy nhất cho toàn bộ danh sách (đánh số dòng) để LLM có ngữ cảnh xuyên
    suốt thay vì dịch rời rạc từng câu riêng lẻ.

    Dùng cho cả `script_mode="subtitle"` (003, mỗi ASR segment 1 dòng) và
    `script_mode="translate"` (005, mỗi dubbing unit 1 dòng).

    Args:
        segments: List[{"start", "end", "text" | "source_text"}].

    Returns:
        List[{"start": float, "end": float, "source_text": str,
        "translated_text": str}], cùng độ dài và thứ tự với segments đầu vào.

    Raises:
        RuntimeError: Nếu gọi API thất bại, hoặc số dòng trả về không khớp số
            segment đầu vào (không cố "đoán" ghép sai — thà báo lỗi rõ còn
            hơn tạo phụ đề/lồng tiếng lệch thời gian).
    """
    if not segments:
        return []

    numbered_input = "\n".join(
        f"[{i + 1}] {_segment_source_text(seg)}" for i, seg in enumerate(segments)
    )
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
            "source_text": _segment_source_text(seg),
            "translated_text": translated,
        }
        for seg, translated in zip(segments, translations)
    ]


def rewrite_segments(units: list[dict]) -> list[dict]:
    """
    Viết lại sáng tạo theo TỪNG nhịp, giữ nguyên start/end gốc — dùng cho
    `script_mode="rewrite"` (005-natural-pause-dubbing, US2/FR-004).

    Cùng cơ chế 1-lượt-gọi/đánh-số-dòng với `translate_segments()`, khác 2
    điểm: prompt giữ tinh thần sáng tạo (`SEGMENT_REWRITE_SYSTEM`), và mỗi
    dòng đầu vào kèm ngân sách ký tự RIÊNG của nhịp đó — ràng buộc mạnh hơn
    hẳn ngân sách toàn bài của cơ chế cũ vì model biết chính xác mỗi nhịp
    được bao nhiêu chữ (research.md §2).

    Args:
        units: List[{"start", "end", "source_text"}] từ `group_segments()`.

    Returns:
        Cùng shape với `translate_segments()`.

    Raises:
        RuntimeError: Nếu gọi API thất bại, hoặc số dòng trả về không khớp số
            nhịp đầu vào.
    """
    if not units:
        return []

    lines = []
    for i, unit in enumerate(units):
        budget = estimate_target_char_budget(float(unit["end"]) - float(unit["start"]))
        budget_hint = f"(~{budget} ký tự) " if budget else ""
        lines.append(f"[{i + 1}] {budget_hint}{_segment_source_text(unit)}")

    raw = _chat_completion(SEGMENT_REWRITE_SYSTEM, "\n".join(lines), temperature=0.7)
    rewrites = [_strip_budget_hint(line) for line in _parse_numbered_lines(raw)]

    if len(rewrites) != len(units):
        raise RuntimeError(
            f"Viết lại theo nhịp thất bại: model trả về {len(rewrites)} dòng, "
            f"cần đúng {len(units)} dòng để khớp mốc thời gian ASR gốc."
        )

    return [
        {
            "start": unit["start"],
            "end": unit["end"],
            "source_text": _segment_source_text(unit),
            "translated_text": rewritten,
        }
        for unit, rewritten in zip(units, rewrites)
    ]


_BUDGET_HINT_RE = re.compile(r"^\(\s*~?\s*\d+\s*ký\s*tự\s*\)\s*", re.IGNORECASE)


def _strip_budget_hint(line: str) -> str:
    """
    Bỏ tiền tố "(~N ký tự)" nếu model chép nguyên chỉ dẫn ngân sách ký tự vào
    kết quả viết lại — đã gặp thật với `google/gemini-2.5-flash` (model
    OpenRouter dự phòng). Prompt đã cấm chép, đây là lớp chặn cuối: lọt xuống
    TTS thì giọng đọc sẽ đọc thành tiếng "khoảng 33 ký tự ..." ngay trong video.
    """
    return _BUDGET_HINT_RE.sub("", line).strip()


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

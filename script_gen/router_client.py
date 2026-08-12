"""
script_gen/router_client.py — Gọi 9router (OpenAI-compatible) để tạo kịch bản.

Hỗ trợ 2 mode:
- translate: Dịch transcript sang tiếng Việt (US1)
- rewrite:   Viết lại kịch bản mới theo ý chính (US3)

9router chạy tại http://localhost:20128/v1 (OpenAI-compatible API).
"""

from __future__ import annotations

import base64
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

# Số ảnh tối đa gửi trong 1 lượt gọi vision (script_mode="visual",
# describe_scenes_in_chunks() bên dưới) — 9router (model cu/gemini-3.1-pro)
# trả lỗi cứng "Too many images in one request (max 12)" khi vượt, gặp thật
# với video ~47s/13 cảnh. Không tăng số này lên mà không kiểm tra lại giới
# hạn thật của model đang cấu hình.
ROUTER_MAX_IMAGES_PER_CALL = int(os.environ.get("ROUTER_MAX_IMAGES_PER_CALL", "12"))

# Trần token đầu ra mỗi lượt gọi LLM.
#
# 4096 (giá trị cũ) là bẫy với model dạng reasoning/agent: đo thật trên
# `ag/gemini-3-flash-agent` với 29 nhịp, model tiêu 3933/4092 token cho phần
# SUY LUẬN, chỉ còn ~160 token để trả lời → output bị cắt ngang giữa dòng 7,
# job chết ở bước scripting sau khi đã tải video + chạy ASR xong. Reasoning
# token là chi phí gần như cố định mỗi lượt gọi, không tỉ lệ với đầu vào, nên
# trần phải đủ rộng để chứa cả phần suy luận lẫn phần trả lời.
ROUTER_MAX_TOKENS = int(os.environ.get("ROUTER_MAX_TOKENS", "16384"))

# Số dòng tối đa gửi trong 1 lượt gọi khi dịch/viết lại theo nhịp. Chia lô để
# độ dài đầu ra mỗi lượt luôn có trần, dù video dài bao nhiêu nhịp đi nữa —
# ROUTER_MAX_TOKENS một mình không đủ bảo đảm với video dài.
_SEGMENT_CHUNK_SIZE = int(os.environ.get("ROUTER_SEGMENT_CHUNK_SIZE", "25"))

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

# Dấu kết thúc câu, gồm cả dấu toàn chiều rộng của tiếng Trung/Nhật
_SENTENCE_END_RE = re.compile(r'[.!?…。！？]["\'”’\)\]]*$')

class TruncatedResponseError(RuntimeError):
    """
    Output của LLM bị cắt vì chạm trần token (`finish_reason="length"`).

    Tách riêng khỏi RuntimeError thường để chỗ gọi phân biệt được "endpoint
    hỏng" (đáng chuyển sang fallback) với "câu trả lời quá dài" (chuyển
    endpoint cũng vô ích, phải chia nhỏ hoặc nới trần).
    """


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

# 005-natural-pause-dubbing (T036): bản dịch EN→VI đo được dài hơn khung
# thời gian gốc trung bình ~13% (tiếng Việt cần nhiều âm tiết hơn để diễn đạt
# cùng nghĩa) — khiến nhiều nhịp phải tăng tốc `atempo` vượt SC-002. Thêm
# ngân sách ký tự riêng từng nhịp, NHƯNG khác hẳn cơ chế toàn-bài cũ của 003
# (đã bị gỡ vì làm model cắt bớt nội dung — research.md §2): ở đây ngân sách
# CHỈ được phép ảnh hưởng CÁCH diễn đạt (chọn từ ngắn gọn hơn khi nghĩa tương
# đương), KHÔNG được phép bỏ bớt Ý để đạt con số — bản dịch vẫn phải đầy đủ,
# sát nghĩa như `SEGMENT_TRANSLATE_SYSTEM` gốc. Dùng riêng cho
# `script_mode="translate"` (qua `generate_script()`), KHÔNG áp dụng cho
# `script_mode="subtitle"` (`generate_subtitle_script()` không lồng tiếng
# nên không có áp lực khớp thời lượng, ép ngân sách ở đó chỉ có hại).
SEGMENT_TRANSLATE_BUDGET_SYSTEM = (
    SEGMENT_TRANSLATE_SYSTEM
    + """

Mỗi dòng đầu vào có định dạng "[n] (~N ký tự) văn bản gốc". "(~N ký tự)" là
độ dài mục tiêu để bản dịch đọc vừa khung thời gian của câu gốc đó — nếu có
nhiều cách diễn đạt cùng nghĩa, hãy ưu tiên cách ngắn gọn, tự nhiên hơn, đừng
viết dài hơn nhiều lần con số này. TUYỆT ĐỐI KHÔNG được bỏ bớt ý/nội dung để
đạt ngân sách — bản dịch vẫn phải đầy đủ, sát nghĩa như yêu cầu ở trên; ngân
sách chỉ là gợi ý về CÁCH diễn đạt, không phải lý do để cắt nghĩa. TUYỆT ĐỐI
KHÔNG chép lại "(~N ký tự)" vào kết quả, vì kết quả sẽ được đọc thành tiếng
nguyên văn."""
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


def _is_sentence_continuation(prev_text: str, next_text: str) -> bool:
    """
    Đoán xem `next_text` có phải phần NỐI TIẾP GIỮA CÂU của `prev_text` không.

    Dùng 2 dấu hiệu cùng lúc, vì mỗi dấu hiệu riêng lẻ đều không đủ tin cậy:
    - Câu trước KHÔNG kết thúc bằng dấu câu, VÀ
    - Câu sau mở đầu bằng chữ THƯỜNG.

    Chỉ dựa vào dấu câu là hỏng: faster-whisper (model 'small') rất hay bỏ dấu
    chấm cuối segment — đo trên transcript thật của repo, 169 ranh giới có
    khoảng trống < 0.30s thì chỉ ~155 ranh giới là hết câu nhưng phần lớn
    không có dấu chấm nào.

    Với ngôn ngữ không phân biệt hoa/thường (Trung, Nhật, Thái...), `islower()`
    trả False nên mặc định coi là RANH GIỚI CÂU → giữ tách. Đây là hướng an
    toàn: giữ đúng nhịp cắt của clip gốc.
    """
    if _SENTENCE_END_RE.search(prev_text.strip()):
        return False
    nxt = next_text.strip()
    return bool(nxt) and nxt[0].islower()


def group_segments(segments: list[dict]) -> list[dict]:
    """
    Gom ASR segment (`transcript.json.segments`) thành các "dubbing unit" —
    đơn vị nhỏ nhất được dịch/viết lại và tổng hợp giọng đọc độc lập
    (005-natural-pause-dubbing, research.md §1, data-model.md §1).

    Nguyên tắc: GIỮ NGUYÊN nhịp cắt của clip gốc, chỉ gộp khi việc tách chắc
    chắn cho kết quả tệ hơn. Chỉ 2 trường hợp được gộp:

    1. Segment sau là phần NỐI TIẾP GIỮA CÂU của segment trước
       (`_is_sentence_continuation()`) và khoảng trống < `_GAP_SILENCE_THRESHOLD`
       (0.30s) → tách ra sẽ đem nửa câu đi dịch riêng, cho ra 2 mẩu tiếng Việt
       cụt nghĩa.
    2. Unit đang mở còn ngắn hơn `_MIN_UNIT_DURATION` (1.20s) và khoảng trống
       < `_SHORT_UNIT_MERGE_MAX_GAP` (1.0s) → gộp để tránh câu vụn (FR-004).

    Cả 2 đều bị chặn nếu unit sau khi gộp vượt `_MAX_UNIT_DURATION` (15s).

    LƯU Ý (sửa 2026-07-27): trước đây quy tắc 1 gộp MỌI segment cách nhau
    < 0.30s, không xét ngữ nghĩa. Whisper phát ra các segment liền mạch
    (gap = 0.0) ngay tại ranh giới CÂU, nên luật cũ nuốt luôn nhịp cắt gốc:
    đo trên toàn bộ transcript thật của repo, 237 segment ASR bị gom còn 93
    nhịp (mất 61% ranh giới), sinh ra 40 nhịp dài > 10s. Nhịp càng dài thì
    bản dịch càng dễ đọc xong sớm rồi im lặng giữa chừng, và phụ đề hiện 1
    khối chữ dài thay vì bám câu như clip gốc. Sau khi sửa: 204 nhịp, chỉ còn
    12 nhịp > 10s.

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
            mid_sentence = gap < _GAP_SILENCE_THRESHOLD and _is_sentence_continuation(
                current["source_text"], text
            )
            too_short = (
                current_duration < _MIN_UNIT_DURATION
                and gap < _SHORT_UNIT_MERGE_MAX_GAP
            )

            if fits_max and (mid_sentence or too_short):
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

    from script_gen.sentence_segmenter import resegment_by_sentences

    segments = resegment_by_sentences(transcript_data.get("segments", []), _chat_completion)
    units = group_segments(segments)

    # Edge case: transcript rỗng (video không có lời thoại) — báo lỗi rõ ràng
    # ngay ở bước scripting thay vì "thành công giả" rồi để TTS fail mơ hồ sau
    if not units:
        raise RuntimeError(
            "Transcript rỗng — video gốc không có lời thoại để lồng tiếng."
        )

    print(f"[router_client] Gom {len(transcript_data.get('segments', []))} segment ASR → {len(units)} nhịp lồng tiếng")

    if mode == "translate":
        cues = translate_segments(units, apply_budget=True)  # T036
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

    from script_gen.sentence_segmenter import resegment_by_sentences

    segments = resegment_by_sentences(segments, _chat_completion)

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


# Tham số mà một model cụ thể từ chối — nhớ lại trong process để những lượt gọi
# sau không tốn thêm một lượt hỏng nữa. Key: (base_url, model).
#
# Vì sao cần: một số model chỉ nhận đúng bộ tham số mặc định và trả 400
# "Unsupported parameter: 'temperature' is not supported with this model"
# (đã gặp thật với `github/gpt-5.4-mini` qua 9router). Trước đây lỗi đó làm hỏng
# nguyên job dù chỉ cần bỏ 1 tham số tuỳ chọn đi là gọi được.
_UNSUPPORTED_PARAMS: dict[tuple[str, str], set[str]] = {}

# Các tham số CHỈ để tinh chỉnh — bỏ đi thì chất lượng có thể khác chút nhưng
# vẫn ra kết quả dùng được. `model`/`messages` KHÔNG nằm ở đây: thiếu chúng thì
# lượt gọi vô nghĩa, phải để lỗi nổi lên.
_OPTIONAL_PARAMS = ("temperature", "max_tokens", "max_completion_tokens")


def _rejected_param(error_message: str, sent_params) -> str | None:
    """
    Tìm tên tham số mà endpoint vừa báo là không hỗ trợ.

    Bắt theo cả 2 cách diễn đạt hay gặp: "Unsupported parameter: 'x'" (OpenAI)
    và "... 'x' is not supported ..." — chỉ nhận tham số ta THỰC SỰ đã gửi và
    nằm trong danh sách bỏ được, để không nuốt nhầm một lỗi 400 khác.

    KHÔNG khớp theo dấu nháy quanh tên tham số: lỗi thật đi qua nhiều lớp JSON
    lồng nhau nên `str(exc)` có thể chứa `\\'temperature\\'` (nháy đã bị escape)
    thay vì `'temperature'`. Khớp theo ranh giới từ mới đủ bền — điều kiện
    "phải có chữ unsupported/not supported" đã lọc đúng loại lỗi từ trước.
    """
    lowered = error_message.lower()
    if "unsupported" not in lowered and "not supported" not in lowered:
        return None
    for param in _OPTIONAL_PARAMS:
        if param in sent_params and re.search(rf"(?<!\w){re.escape(param)}(?!\w)", lowered):
            return param
    return None


def _build_user_content(user_message: str, images: list[Path] | None):
    """
    Build nội dung message user — string thuần khi không có ảnh (hành vi cũ,
    giữ nguyên với mọi lượt gọi translate/rewrite hiện có), hoặc content dạng
    list chuẩn OpenAI-vision khi có ảnh (script_mode="visual" —
    `describe_scenes()`). Ảnh encode base64 inline (data URL), không upload
    qua endpoint riêng — cùng cách 9router/OpenRouter đều chấp nhận.
    """
    if not images:
        return user_message

    content: list[dict] = [{"type": "text", "text": user_message}]
    for image_path in images:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    return content


def _call_chat_api(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    images: list[Path] | None = None,
) -> str:
    """
    Một lượt gọi chat completion tới endpoint OpenAI-compatible bất kỳ
    (9router hoặc OpenRouter — cùng giao thức nên dùng chung code).

    Model nào từ chối tham số tuỳ chọn (`temperature`, `max_tokens`) sẽ được gọi
    lại NGAY mà không có tham số đó, thay vì làm hỏng cả job — xem
    `_UNSUPPORTED_PARAMS`.

    `images`: danh sách đường dẫn ảnh gửi kèm user_message (script_mode=
    "visual") — model phải hỗ trợ vision, nếu không endpoint sẽ trả lỗi và
    lan lên như mọi lỗi API khác (không có xử lý riêng).

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

    known_bad = _UNSUPPORTED_PARAMS.setdefault((base_url, model), set())
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_content(user_message, images)},
        ],
    }
    if "temperature" not in known_bad:
        kwargs["temperature"] = temperature
    if "max_tokens" not in known_bad:
        kwargs["max_tokens"] = ROUTER_MAX_TOKENS

    # Mỗi vòng bỏ đúng 1 tham số bị từ chối rồi thử lại; số vòng chặn trên bằng
    # số tham số bỏ được nên không thể lặp vô hạn.
    for _ in range(len(_OPTIONAL_PARAMS) + 1):
        try:
            response = client.chat.completions.create(**kwargs)
            break
        except Exception as e:
            param = _rejected_param(str(e), kwargs)
            if param is None:
                raise
            known_bad.add(param)
            kwargs.pop(param, None)
            print(
                f"[router_client] Model '{model}' không nhận tham số "
                f"'{param}' — gọi lại không kèm tham số này"
            )
    else:
        raise RuntimeError(
            f"Model '{model}' từ chối mọi tham số tuỳ chọn mà vẫn không gọi được."
        )

    choice = response.choices[0]
    content = choice.message.content
    if not content or not content.strip():
        raise RuntimeError(f"Endpoint trả về kết quả rỗng. Kiểm tra model '{model}' còn hoạt động.")

    # Output bị cắt vì chạm trần token. KHÔNG được trả về âm thầm: phần gọi
    # bên trên sẽ đếm số dòng thiếu rồi báo "model trả về N dòng" — sai nguyên
    # nhân và khiến người dùng đi tìm nhầm chỗ (đã xảy ra thật, xem
    # ROUTER_MAX_TOKENS).
    if getattr(choice, "finish_reason", None) == "length":
        raise TruncatedResponseError(
            f"Model '{model}' bị cắt output vì chạm trần {ROUTER_MAX_TOKENS} token"
            f"{_reasoning_token_note(response)}. Tăng ROUTER_MAX_TOKENS trong .env, "
            f"hoặc giảm ROUTER_SEGMENT_CHUNK_SIZE (hiện {_SEGMENT_CHUNK_SIZE}) để mỗi "
            f"lượt gọi phải trả ít dòng hơn."
        )

    return content.strip()


def _reasoning_token_note(response) -> str:
    """Nêu rõ số token đã đốt cho suy luận, nếu endpoint có báo cáo."""
    usage = getattr(response, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None)
    if not reasoning:
        return ""
    completion = getattr(usage, "completion_tokens", None) or 0
    return f" (trong đó {reasoning}/{completion} token dành cho suy luận nội bộ)"


def _chat_completion(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    model: str | None = None,
    images: list[Path] | None = None,
) -> str:
    """
    Gọi 9router (OpenAI-compatible chat completion) — helper dùng chung cho
    `translate_segments()` (Dịch chuẩn/Phụ đề tự động), `rewrite_segments()`
    (Sáng tạo), và `script_gen/topic_script_generator.py` (010-topic-video-
    generation, dùng model agent riêng qua tham số `model`).

    `model=None` (mặc định, mọi lượt gọi hiện có) giữ NGUYÊN hành vi cũ — dùng
    `DEFAULT_MODEL` (`ROUTER_MODEL`). Chỉ topic_script_generator.py truyền
    `model` tường minh (`ROUTER_AGENT_MODEL`) để dùng model agent có tool-use
    khác hẳn model dịch/viết lại (research.md §3 của feature 010).

    Nếu 9router lỗi (timeout, connection refused, HTTP lỗi, kết quả rỗng) và
    .env có OPENROUTER_API_KEY thì tự động gọi lại qua OpenRouter thay vì làm
    hỏng cả job — cùng giao thức OpenAI-compatible nên kết quả trả về giữ
    nguyên định dạng, phần parse phía sau không đổi. Fallback OpenRouter LUÔN
    dùng `OPENROUTER_MODEL` (không có khái niệm "agent model" bên OpenRouter).

    Raises:
        RuntimeError: Nếu 9router lỗi và không có (hoặc cũng lỗi nốt) fallback.
    """
    try:
        return _call_chat_api(
            ROUTER_BASE_URL, ROUTER_API_KEY, model or DEFAULT_MODEL,
            system_prompt, user_message, temperature, images=images,
        )
    except TruncatedResponseError:
        # Câu trả lời quá dài so với trần token — đổi endpoint không giải quyết
        # được gì, chỉ tốn thêm 1 lượt gọi. Ném thẳng lên để chỗ gọi chia nhỏ.
        raise
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
                system_prompt, user_message, temperature, images=images,
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


def _budget_line(seg: dict) -> str:
    """Dòng đầu vào kèm ngân sách ký tự riêng của nhịp đó."""
    budget = estimate_target_char_budget(float(seg["end"]) - float(seg["start"]))
    hint = f"(~{budget} ký tự) " if budget else ""
    return f"{hint}{_segment_source_text(seg)}"


def _generate_numbered_lines(
    segments: list[dict],
    system_prompt: str,
    build_line,
    temperature: float,
    what: str,
    offset: int = 0,
) -> list[str]:
    """
    Sinh đúng 1 dòng kết quả cho mỗi phần tử `segments`, chia lô và TỰ CHIA ĐÔI
    lô lỗi thay vì làm hỏng cả job.

    Vì sao cần: cơ chế cũ gửi TOÀN BỘ nhịp trong 1 lượt gọi và bắt buộc số dòng
    trả về khớp tuyệt đối — chỉ cần 1 lượt trả lời hụt là mất trắng công tải
    video + chạy ASR. Đã xảy ra thật: model reasoning đốt gần hết trần token
    cho suy luận rồi bị cắt ở dòng 7/29 (xem ROUTER_MAX_TOKENS).

    Chia đôi đệ quy xử lý được cả 2 nguyên nhân hụt dòng — output quá dài bị
    cắt, và model tự ý gộp dòng — vì lô càng nhỏ thì cả 2 đều khó xảy ra. Đáy
    đệ quy là lô 1 dòng: hụt ở mức đó mới thực sự là lỗi.
    """
    lines = [f"[{i + 1}] {build_line(seg)}" for i, seg in enumerate(segments)]

    problem: str | None = None
    try:
        raw = _chat_completion(system_prompt, "\n".join(lines), temperature=temperature)
        results = _parse_numbered_lines(raw)
        if len(results) == len(segments):
            return results
        problem = f"trả về {len(results)} dòng, cần {len(segments)}"
    except TruncatedResponseError as e:
        problem = str(e)

    if len(segments) == 1:
        raise RuntimeError(f"{what} thất bại ở nhịp {offset + 1}: {problem}")

    mid = len(segments) // 2
    print(
        f"[router_client] {what}: lô nhịp {offset + 1}-{offset + len(segments)} "
        f"({problem}) — chia đôi và thử lại"
    )
    return _generate_numbered_lines(
        segments[:mid], system_prompt, build_line, temperature, what, offset
    ) + _generate_numbered_lines(
        segments[mid:], system_prompt, build_line, temperature, what, offset + mid
    )


def _generate_in_chunks(
    segments: list[dict],
    system_prompt: str,
    build_line,
    temperature: float,
    what: str,
) -> list[str]:
    """Chia `segments` thành lô `_SEGMENT_CHUNK_SIZE` rồi sinh từng lô."""
    results: list[str] = []
    for start in range(0, len(segments), _SEGMENT_CHUNK_SIZE):
        chunk = segments[start : start + _SEGMENT_CHUNK_SIZE]
        results.extend(
            _generate_numbered_lines(chunk, system_prompt, build_line, temperature, what, start)
        )
    return results


def translate_segments(segments: list[dict], apply_budget: bool = False) -> list[dict]:
    """
    Dịch sát nghĩa từng segment/nhịp, giữ nguyên start/end gốc. Gửi theo LÔ
    (đánh số dòng) để LLM vẫn có ngữ cảnh liền mạch quanh mỗi câu thay vì dịch
    rời rạc từng câu — xem `_generate_in_chunks()` cho cách chia lô và cơ chế
    tự chia đôi khi một lô trả hụt dòng.

    Dùng cho cả `script_mode="subtitle"` (003, mỗi ASR segment 1 dòng) và
    `script_mode="translate"` (005, mỗi dubbing unit 1 dòng).

    Args:
        segments: List[{"start", "end", "text" | "source_text"}].
        apply_budget: T036 (005) — chỉ bật cho `script_mode="translate"`
            (qua `generate_script()`). Thêm ngân sách ký tự riêng từng dòng
            (`SEGMENT_TRANSLATE_BUDGET_SYSTEM`) để giảm tỉ lệ nhịp phải tăng
            tốc `atempo` do bản dịch EN→VI dài hơn khung gốc (SC-002). KHÔNG
            bật cho `script_mode="subtitle"` — mode đó không lồng tiếng nên
            không có áp lực khớp thời lượng.

    Returns:
        List[{"start": float, "end": float, "source_text": str,
        "translated_text": str}], cùng độ dài và thứ tự với segments đầu vào.

    Raises:
        RuntimeError: Nếu gọi API thất bại, hoặc một nhịp ĐƠN LẺ vẫn không
            dịch được sau khi đã chia nhỏ hết cỡ (không cố "đoán" ghép sai —
            thà báo lỗi rõ còn hơn tạo phụ đề/lồng tiếng lệch thời gian).
    """
    if not segments:
        return []

    if apply_budget:
        system_prompt = SEGMENT_TRANSLATE_BUDGET_SYSTEM
        build_line = _budget_line
    else:
        system_prompt = SEGMENT_TRANSLATE_SYSTEM
        build_line = _segment_source_text

    translations = _generate_in_chunks(
        segments, system_prompt, build_line, temperature=0.3, what="Dịch theo nhịp"
    )
    if apply_budget:
        translations = [_strip_budget_hint(t) for t in translations]

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

    rewrites = [
        _strip_budget_hint(line)
        for line in _generate_in_chunks(
            units, SEGMENT_REWRITE_SYSTEM, _budget_line, temperature=0.7, what="Viết lại theo nhịp"
        )
    ]

    return [
        {
            "start": unit["start"],
            "end": unit["end"],
            "source_text": _segment_source_text(unit),
            "translated_text": rewritten,
        }
        for unit, rewritten in zip(units, rewrites)
    ]


_BUDGET_HINT_RE = re.compile(r"\s*\(\s*~?\s*\d+\s*ký\s*tự\s*\)\s*", re.IGNORECASE)


def _strip_budget_hint(line: str) -> str:
    """
    Bỏ chỉ dẫn "(~N ký tự)" nếu model chép nguyên vào kết quả viết lại — đã
    gặp thật với `google/gemini-2.5-flash` (model OpenRouter dự phòng).
    Prompt đã cấm chép, đây là lớp chặn cuối: lọt xuống TTS thì giọng đọc sẽ
    đọc thành tiếng "khoảng 33 ký tự ..." ngay trong video.

    T040 (005): không neo `^` — model có thể chèn chỉ dẫn vào GIỮA câu, không
    chỉ ở đầu dòng, nên phải quét khớp ở bất kỳ vị trí nào trong `line`
    (`re.sub` mặc định đã thay hết mọi lần khớp không chồng lấn, không chỉ
    lần đầu).
    """
    return _BUDGET_HINT_RE.sub(" ", line).strip()


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


# ─── script_mode="visual" — kịch bản sinh từ hình ảnh, không dùng transcript ──

_VISUAL_SCRIPT_SYSTEM_PROMPT = """Bạn là người viết lời thuyết minh (voice-over) tiếng Việt cho video, ví dụ video unbox/giới thiệu sản phẩm.

Bạn sẽ nhận một chuỗi ảnh, mỗi ảnh là 1 khung hình đại diện của 1 cảnh liên tiếp trong video, đánh số đúng theo thứ tự thời gian xuất hiện.

Với MỖI cảnh, viết đúng 1 câu thuyết minh tiếng Việt tự nhiên, liền mạch với các câu trước/sau (như đang thuyết minh xuyên suốt cả video chứ không phải mô tả rời rạc từng ảnh), mô tả đúng những gì thấy được trong ảnh.

Quy tắc bắt buộc:
- Chỉ nêu thông tin THẤY ĐƯỢC trong ảnh (hình dáng, màu sắc, thao tác, chữ đọc rõ trên bao bì/sản phẩm). KHÔNG bịa tên hãng, model, thông số kỹ thuật nếu không đọc rõ được chữ trong ảnh.
- Không lặp lại nguyên văn câu trước.
- Câu ngắn gọn, tự nhiên như giọng thuyết minh video thật, không văn viết cứng nhắc.
- Mỗi dòng đầu vào có kèm "(~N ký tự)" — đó là độ dài mục tiêu để câu đọc VỪA ĐÚNG khung thời gian của cảnh đó (cảnh càng ngắn thì câu càng phải ngắn). Nếu 1 cảnh có nhiều chi tiết, hãy CHỌN đúng 1-2 chi tiết nổi bật nhất để nói, KHÔNG cố nhồi hết mọi thứ nhìn thấy vào 1 câu dài hơn nhiều lần con số này. TUYỆT ĐỐI KHÔNG chép lại "(~N ký tự)" vào kết quả, vì kết quả sẽ được đọc thành tiếng nguyên văn.
- Nếu đầu vào có dòng "Định hướng thêm từ người dùng", hãy ưu tiên bám theo định hướng đó (giọng điệu, trọng tâm, điều cần nhấn mạnh) khi viết các câu — nhưng vẫn PHẢI tuân thủ quy tắc chỉ mô tả những gì thấy được trong ảnh, KHÔNG bịa thêm chi tiết không có trong hình chỉ vì định hướng yêu cầu.
- Trả lời ĐÚNG theo định dạng "[số thứ tự] nội dung câu", mỗi cảnh 1 dòng, không thêm giải thích, không thêm dòng nào khác."""


def describe_scenes(
    frames: list[tuple[float, float, Path]],
    offset: int = 0,
    user_prompt: str | None = None,
) -> list[str]:
    """
    Sinh đúng 1 câu thuyết minh tiếng Việt cho MỖI cảnh trong `frames`
    (script_mode="visual", `script_gen/visual_script_generator.py`) — LLM chỉ
    dựa vào ảnh, KHÔNG có transcript làm ngữ cảnh.

    Args:
        frames: List[(start, end, frame_path)] theo đúng thứ tự thời gian.
        offset: Chỉ số cảnh đầu tiên trong `frames` so với danh sách gốc — chỉ
            dùng để log/báo lỗi đúng số cảnh khi đệ quy chia đôi.
        user_prompt: Ghi chú định hướng tự do của người dùng (vd "nhấn mạnh
            tính năng chống nước") — chèn vào đầu prompt để LLM ưu tiên bám
            theo, không thay đổi quy tắc chỉ mô tả những gì thấy trong ảnh.

    Returns:
        List[str] cùng độ dài với `frames`, 1 câu / cảnh, đúng thứ tự.

    Raises:
        RuntimeError: Model không hỗ trợ ảnh, hoặc số dòng trả về lệch dù đã
            chia đôi tới lô 1 cảnh (cùng chiến lược với `_generate_numbered_lines()`).
    """
    markers = []
    for i, (start, end, _path) in enumerate(frames):
        budget = estimate_target_char_budget(end - start)
        hint = f"(~{budget} ký tự) " if budget else ""
        markers.append(
            f"[{i + 1}] {hint}Cảnh lúc {start:.1f}s-{end:.1f}s (ảnh {i + 1} kèm theo)"
        )
    user_message = ""
    if user_prompt and user_prompt.strip():
        user_message += f"Định hướng thêm từ người dùng: {user_prompt.strip()}\n\n"
    user_message += (
        f"Video có {len(frames)} cảnh liên tiếp, ảnh gửi kèm đúng theo thứ tự dưới đây:\n"
        + "\n".join(markers)
    )
    images = [path for _, _, path in frames]

    problem: str | None = None
    try:
        raw = _chat_completion(
            _VISUAL_SCRIPT_SYSTEM_PROMPT, user_message, temperature=0.7, images=images
        )
        results = [_strip_budget_hint(line) for line in _parse_numbered_lines(raw)]
        if len(results) == len(frames):
            return results
        problem = f"trả về {len(results)} dòng, cần {len(frames)}"
    except TruncatedResponseError as e:
        problem = str(e)

    if len(frames) == 1:
        raise RuntimeError(
            f"Viết kịch bản từ hình ảnh thất bại ở cảnh {offset + 1}: {problem}"
        )

    mid = len(frames) // 2
    print(
        f"[router_client] Kịch bản hình ảnh: lô cảnh {offset + 1}-{offset + len(frames)} "
        f"({problem}) — chia đôi và thử lại"
    )
    return describe_scenes(
        frames[:mid], offset, user_prompt
    ) + describe_scenes(frames[mid:], offset + mid, user_prompt)


def describe_scenes_in_chunks(
    frames: list[tuple[float, float, Path]],
    user_prompt: str | None = None,
) -> list[str]:
    """
    Chia `frames` thành lô tối đa `ROUTER_MAX_IMAGES_PER_CALL` ảnh/lượt gọi
    rồi nối kết quả — bắt buộc vì model vision (9router) từ chối thẳng lượt
    gọi vượt trần ảnh (400 "Too many images in one request"), khác hẳn lỗi
    hụt dòng mà `describe_scenes()` tự chia đôi xử lý được. Video dài hơn
    `ROUTER_MAX_IMAGES_PER_CALL` cảnh LUÔN cần hàm này, không chỉ khi lỗi.

    Đây là điểm vào chính cho `visual_script_generator.py` — dùng thay vì gọi
    thẳng `describe_scenes()`.
    """
    results: list[str] = []
    for start in range(0, len(frames), ROUTER_MAX_IMAGES_PER_CALL):
        chunk = frames[start : start + ROUTER_MAX_IMAGES_PER_CALL]
        results.extend(describe_scenes(chunk, offset=start, user_prompt=user_prompt))
    return results

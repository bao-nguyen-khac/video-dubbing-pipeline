"""
tests/unit/test_segment_chunking.py — Chia lô + tự chia đôi khi LLM trả hụt dòng.

Bối cảnh: job thật chết ở bước scripting vì model reasoning đốt 3933/4092 token
cho suy luận rồi bị cắt ở dòng 7/29. Cơ chế cũ gửi tất cả trong 1 lượt gọi và
fail cứng — mất trắng công tải video + ASR.

Không gọi mạng: `_chat_completion` được thay bằng bản giả.
"""

from __future__ import annotations

import pytest

from script_gen import router_client
from script_gen.router_client import TruncatedResponseError, translate_segments


def seg(i, start, end):
    return {"start": start, "end": end, "text": f"line {i}"}


def segments(n):
    return [seg(i, float(i), float(i) + 1.0) for i in range(1, n + 1)]


def install_llm(monkeypatch, handler):
    """Thay _chat_completion bằng handler(user_message) -> raw response."""
    calls = []

    def fake(system_prompt, user_message, temperature=0.7):
        calls.append(user_message)
        return handler(user_message)

    monkeypatch.setattr(router_client, "_chat_completion", fake)
    return calls


def count_input_lines(user_message: str) -> int:
    return len([ln for ln in user_message.splitlines() if ln.strip()])


def echo_all(user_message: str) -> str:
    """Model ngoan: trả đúng số dòng đã nhận."""
    n = count_input_lines(user_message)
    return "\n".join(f"[{i + 1}] dịch {i + 1}" for i in range(n))


# ── Chia lô ─────────────────────────────────────────────────────────────────


def test_chia_lo_theo_chunk_size(monkeypatch):
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 10)
    calls = install_llm(monkeypatch, echo_all)

    result = translate_segments(segments(25))

    assert len(result) == 25
    # 25 nhịp / lô 10 → 3 lượt gọi (10 + 10 + 5)
    assert [count_input_lines(c) for c in calls] == [10, 10, 5]


def test_moi_lo_danh_so_lai_tu_1(monkeypatch):
    """Model luôn thấy [1]..[n] của riêng lô đó, không phải số toàn cục."""
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 5)
    calls = install_llm(monkeypatch, echo_all)

    translate_segments(segments(10))

    for call in calls:
        assert call.splitlines()[0].startswith("[1] ")


def test_ket_qua_giu_dung_thu_tu_va_moc_thoi_gian(monkeypatch):
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 3)
    install_llm(monkeypatch, echo_all)

    result = translate_segments(segments(7))

    assert [r["start"] for r in result] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert result[0]["source_text"] == "line 1"
    assert result[-1]["source_text"] == "line 7"


# ── Tự chia đôi khi lô lỗi ──────────────────────────────────────────────────


def test_output_bi_cat_thi_chia_doi_va_thu_lai(monkeypatch):
    """Ca thật: lô lớn bị cắt vì chạm trần token, lô nhỏ thì lọt."""
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 100)

    def handler(user_message):
        if count_input_lines(user_message) > 4:
            raise TruncatedResponseError("chạm trần token")
        return echo_all(user_message)

    calls = install_llm(monkeypatch, handler)
    result = translate_segments(segments(8))

    assert len(result) == 8
    # 8 (cắt) → 4 + 4, cả 2 lô 4 dòng đều lọt
    assert [count_input_lines(c) for c in calls] == [8, 4, 4]


def test_model_gop_dong_thi_cung_chia_doi(monkeypatch):
    """Trả hụt dòng vì model tự gộp — xử lý cùng một đường với ca bị cắt."""
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 100)

    def handler(user_message):
        n = count_input_lines(user_message)
        if n > 2:
            return "\n".join(f"[{i + 1}] gộp" for i in range(n - 1))  # thiếu 1 dòng
        return echo_all(user_message)

    install_llm(monkeypatch, handler)
    result = translate_segments(segments(4))

    assert len(result) == 4
    assert all(r["translated_text"] for r in result)


def test_chia_doi_de_quy_nhieu_tang(monkeypatch):
    """Chỉ lô 1 dòng mới trả đúng — phải chia tới tận đáy."""
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 100)

    def handler(user_message):
        if count_input_lines(user_message) > 1:
            raise TruncatedResponseError("chạm trần token")
        return "[1] dịch đơn lẻ"

    install_llm(monkeypatch, handler)
    result = translate_segments(segments(5))

    assert len(result) == 5
    assert all(r["translated_text"] == "dịch đơn lẻ" for r in result)


def test_nhip_don_le_that_bai_thi_bao_loi_ro_vi_tri(monkeypatch):
    """Đáy đệ quy: hụt ở mức 1 dòng mới thực sự là lỗi, và phải chỉ rõ nhịp nào."""
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 100)
    install_llm(monkeypatch, lambda _: "không có dòng đánh số nào")

    with pytest.raises(RuntimeError) as e:
        translate_segments(segments(2))

    assert "nhịp 1" in str(e.value)


def test_mot_lo_hong_khong_keo_do_lo_khac(monkeypatch):
    """Lô 2 lỗi rồi tự chia đôi; lô 1 và 3 không bị ảnh hưởng."""
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 2)

    def handler(user_message):
        if "line 3" in user_message and count_input_lines(user_message) == 2:
            raise TruncatedResponseError("chạm trần token")
        return echo_all(user_message)

    install_llm(monkeypatch, handler)
    result = translate_segments(segments(6))

    assert len(result) == 6
    assert [r["source_text"] for r in result] == [f"line {i}" for i in range(1, 7)]


# ── Bất biến ────────────────────────────────────────────────────────────────


def test_danh_sach_rong_khong_goi_api(monkeypatch):
    calls = install_llm(monkeypatch, echo_all)

    assert translate_segments([]) == []
    assert calls == []


def test_apply_budget_them_goi_y_ky_tu_va_go_khoi_ket_qua(monkeypatch):
    monkeypatch.setattr(router_client, "_SEGMENT_CHUNK_SIZE", 10)

    def handler(user_message):
        n = count_input_lines(user_message)
        # Model chép lại gợi ý ngân sách vào kết quả (đã gặp thật)
        return "\n".join(f"[{i + 1}] (~30 ký tự) bản dịch {i + 1}" for i in range(n))

    calls = install_llm(monkeypatch, handler)
    result = translate_segments(segments(3), apply_budget=True)

    assert "ký tự)" in calls[0]  # đầu vào CÓ gợi ý ngân sách
    for r in result:
        assert "ký tự)" not in r["translated_text"]  # đầu ra thì KHÔNG

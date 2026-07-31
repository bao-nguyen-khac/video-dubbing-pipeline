"""
tests/unit/test_text_renderer.py — Vẽ phụ đề thành ảnh PNG bằng Pillow (009).

Bao phủ: tách cue quá dài thành mẩu đọc được (giữ nguyên hai đầu mốc thời
gian), gộp mẩu quá ngắn, đặt đúng vị trí trong vùng phụ đề gốc vs vị trí mặc
định, và quy đổi cỡ chữ theo chiều cao khung hình.

KHÔNG gọi ffmpeg — module này chỉ vẽ ảnh, hoàn toàn chạy bằng Pillow.
"""

from __future__ import annotations

import pytest
from PIL import Image

from merge import text_renderer


FRAME = {"width": 608, "height": 1080}

REGION_USABLE = {
    "index": 0,
    "start": 0.0,
    "end": 30.0,
    "detected": True,
    "excluded": False,
    "box": {"x": 50, "y": 736, "w": 524, "h": 68},
}

REGION_EXCLUDED = {
    "index": 0,
    "start": 0.0,
    "end": 30.0,
    "detected": True,
    "excluded": True,
    "box": {"x": 50, "y": 736, "w": 524, "h": 68},
}


# ─── Tách cue dài / gộp cue ngắn ─────────────────────────────────────────────


def test_short_cue_is_left_untouched():
    cues = [{"start": 0.0, "end": 3.0, "text": "Một câu ngắn."}]

    assert text_renderer._split_long_cues(cues) == cues


def test_long_cue_is_split_and_keeps_outer_timestamps():
    """
    Mốc đầu/cuối của cue gốc PHẢI giữ nguyên — phụ đề bám nhịp giọng đọc, việc
    chia nhỏ chỉ để đọc kịp (xem `_MAX_WORDS_PER_CUE`).
    """
    text = (
        "Đây là tôi đang tắm bồn băng ở âm 52 độ, nơi tôi bị đông cứng trong vài "
        "giây và suýt ngất. Ok, đầu tiên chúng tôi thực sự phải đập băng vì nó "
        "đông cứng lại chỉ trong vòng năm phút."
    )
    cues = [{"start": 0.0, "end": 14.0, "text": text}]

    result = text_renderer._split_long_cues(cues)

    assert len(result) > 1
    assert result[0]["start"] == 0.0
    assert result[-1]["end"] == 14.0
    # Các mẩu nối tiếp liền mạch, không chồng lấn/hở
    for earlier, later in zip(result, result[1:]):
        assert earlier["end"] == later["start"]


def test_split_chunks_stay_within_word_budget():
    text = " ".join(["từ"] * 200)
    cues = [{"start": 0.0, "end": 60.0, "text": text}]

    result = text_renderer._split_long_cues(cues)

    assert all(
        len(c["text"].split()) <= text_renderer._MAX_WORDS_PER_CUE for c in result
    )


def test_split_shows_three_words_at_a_time():
    """Yêu cầu người dùng: hiện tối đa 3 từ mỗi lần, không dồn cả câu dài."""
    text = "Tôi ngâm mình khoảng bốn mươi giây và cũng không thấy tệ lắm"
    cues = [{"start": 0.0, "end": 8.0, "text": text}]

    result = text_renderer._split_long_cues(cues)

    assert len(result) > 1
    for c in result:
        assert len(c["text"].split()) <= 3


def test_split_does_not_produce_flash_cues():
    """
    Bug thật khi verify: chia đều vẫn sinh mẩu vài từ chỉ hiện ~0.2s, không
    đọc kịp — `_merge_too_short()` phải gộp chúng vào mẩu liền kề.
    """
    text = (
        "Tôi ngâm mình khoảng bốn mươi giây và cũng không thấy tệ lắm vì nước "
        "khá là trong. Ok."
    )
    cues = [{"start": 0.0, "end": 8.0, "text": text}]

    result = text_renderer._split_long_cues(cues)

    assert all(
        c["end"] - c["start"] >= text_renderer._MIN_CUE_DURATION for c in result
    )


def test_split_chunks_are_balanced_not_one_leftover_word():
    """
    Bug thật: gộp tham lam tới sát giới hạn dồn hết chữ vào cụm đầu, để lại
    cụm cuối chỉ 1 từ — MUST chia đều số từ giữa các cụm.
    """
    text = " ".join(f"từ{i}" for i in range(10))  # 10 từ, budget 3 từ/cụm
    cues = [{"start": 0.0, "end": 10.0, "text": text}]

    result = text_renderer._split_long_cues(cues)

    word_counts = [len(c["text"].split()) for c in result]
    assert min(word_counts) >= 2  # không cụm nào chỉ 1 từ


def test_merge_too_short_folds_leading_fragment_forward():
    """Mẩu ĐẦU quá ngắn không có mẩu trước để gộp vào → gộp vào mẩu liền sau."""
    sub_cues = [
        {"start": 0.0, "end": 0.2, "text": "Ừ,"},
        {"start": 0.2, "end": 4.0, "text": "phần còn lại của câu."},
    ]

    merged = text_renderer._merge_too_short(sub_cues, 0.8)

    assert len(merged) == 1
    assert merged[0]["start"] == 0.0
    assert merged[0]["end"] == 4.0
    assert merged[0]["text"] == "Ừ, phần còn lại của câu."


def test_empty_cue_is_dropped():
    cues = [{"start": 0.0, "end": 3.0, "text": "   "}]

    assert text_renderer._split_long_cues(cues) == []


# ─── render_cue_overlays: vị trí ─────────────────────────────────────────────


def test_cue_in_hardsub_region_is_placed_at_region_box(tmp_path):
    """FR-005: cue giao vùng phụ đề gốc → đáy chữ trùng đáy box, căn giữa box."""
    cues = [{"start": 1.0, "end": 4.0, "text": "Thay đồ đó."}]

    overlays = text_renderer.render_cue_overlays(cues, [REGION_USABLE], FRAME, tmp_path)

    assert len(overlays) == 1
    box = REGION_USABLE["box"]
    with Image.open(overlays[0]["image"]) as img:
        width, height = img.size
    assert overlays[0]["y"] == box["y"] + box["h"] - height
    assert overlays[0]["x"] == round(box["x"] + box["w"] / 2 - width / 2)


def test_cue_outside_region_uses_default_bottom_position(tmp_path):
    """Cue không giao vùng nào → căn giữa ngang, cách đáy đúng lề mặc định."""
    cues = [{"start": 40.0, "end": 43.0, "text": "Ngoài vùng."}]

    overlays = text_renderer.render_cue_overlays(cues, [REGION_USABLE], FRAME, tmp_path)

    with Image.open(overlays[0]["image"]) as img:
        width, height = img.size
    margin = round(
        text_renderer._LEGACY_MARGIN_V * text_renderer._scale_for(FRAME["height"])
    )
    assert overlays[0]["y"] == FRAME["height"] - margin - height
    assert overlays[0]["x"] == round(FRAME["width"] / 2 - width / 2)


def test_excluded_region_is_ignored(tmp_path):
    """FR-008: vùng đã đánh dấu 'không có phụ đề gốc' → dùng vị trí mặc định."""
    cues = [{"start": 1.0, "end": 4.0, "text": "Vùng bị loại trừ."}]

    overlays = text_renderer.render_cue_overlays(cues, [REGION_EXCLUDED], FRAME, tmp_path)

    with Image.open(overlays[0]["image"]) as img:
        height = img.size[1]
    margin = round(
        text_renderer._LEGACY_MARGIN_V * text_renderer._scale_for(FRAME["height"])
    )
    assert overlays[0]["y"] == FRAME["height"] - margin - height


def test_overlay_never_falls_outside_frame(tmp_path):
    """Box sát mép dưới → ảnh vẫn phải nằm trọn trong khung hình."""
    edge_region = {
        **REGION_USABLE,
        "box": {"x": 0, "y": FRAME["height"] - 10, "w": 100, "h": 10},
    }
    cues = [{"start": 1.0, "end": 4.0, "text": "Sát mép dưới."}]

    overlays = text_renderer.render_cue_overlays(cues, [edge_region], FRAME, tmp_path)

    with Image.open(overlays[0]["image"]) as img:
        width, height = img.size
    assert 0 <= overlays[0]["x"] <= FRAME["width"] - width
    assert 0 <= overlays[0]["y"] <= FRAME["height"] - height


# ─── render_cue_overlays: cỡ chữ + file sinh ra ─────────────────────────────


def test_font_size_scales_with_frame_height(tmp_path):
    """
    Tham số style cũ nằm trong hệ toạ độ ASS mặc định (PlayResY=288) — chữ phải
    to lên theo chiều cao khung hình, nếu không sẽ nhỏ xíu trên video 1080p.
    """
    cues = [{"start": 40.0, "end": 43.0, "text": "Cùng một câu"}]

    small = text_renderer.render_cue_overlays(
        cues, [], {"width": 304, "height": 540}, tmp_path / "small"
    )
    large = text_renderer.render_cue_overlays(
        cues, [], {"width": 608, "height": 1080}, tmp_path / "large"
    )

    with Image.open(small[0]["image"]) as img:
        small_height = img.size[1]
    with Image.open(large[0]["image"]) as img:
        large_height = img.size[1]
    assert large_height > small_height


def test_region_cue_uses_smaller_font_than_default(tmp_path):
    """FR-006: phụ đề chèn vào vùng phụ đề gốc dùng cỡ chữ nhỏ hơn mặc định."""
    text = "Cùng một câu"
    in_region = text_renderer.render_cue_overlays(
        [{"start": 1.0, "end": 4.0, "text": text}], [REGION_USABLE], FRAME, tmp_path / "in"
    )
    outside = text_renderer.render_cue_overlays(
        [{"start": 40.0, "end": 43.0, "text": text}], [REGION_USABLE], FRAME, tmp_path / "out"
    )

    with Image.open(in_region[0]["image"]) as img:
        in_height = img.size[1]
    with Image.open(outside[0]["image"]) as img:
        out_height = img.size[1]
    assert in_height < out_height


def test_renders_one_png_per_cue(tmp_path):
    cues = [
        {"start": 0.0, "end": 3.0, "text": "Câu một"},
        {"start": 3.0, "end": 6.0, "text": "Câu hai"},
        {"start": 6.0, "end": 9.0, "text": ""},  # rỗng → bỏ qua
    ]

    overlays = text_renderer.render_cue_overlays(cues, [], FRAME, tmp_path)

    assert len(overlays) == 2
    assert all(o["image"].exists() for o in overlays)
    assert len(list(tmp_path.glob("*.png"))) == 2


def test_rendered_image_has_transparent_background(tmp_path):
    cues = [{"start": 0.0, "end": 3.0, "text": "Xin chào"}]

    overlays = text_renderer.render_cue_overlays(cues, [], FRAME, tmp_path)

    with Image.open(overlays[0]["image"]) as img:
        assert img.mode == "RGBA"
        assert img.getpixel((0, 0))[3] == 0  # góc trên trái trong suốt


# ─── Font ────────────────────────────────────────────────────────────────────


def test_font_env_override_missing_file_raises(monkeypatch):
    monkeypatch.setenv(text_renderer._FONT_ENV_VAR, "/khong/ton/tai.ttf")

    with pytest.raises(text_renderer.FontNotFoundError):
        text_renderer.find_font_path()


def test_no_font_available_raises_with_install_hint(monkeypatch):
    monkeypatch.delenv(text_renderer._FONT_ENV_VAR, raising=False)
    monkeypatch.setattr(text_renderer, "_FONT_CANDIDATES", ())

    with pytest.raises(text_renderer.FontNotFoundError) as exc:
        text_renderer.find_font_path()

    assert "fonts-dejavu-core" in str(exc.value)

"""
merge/text_renderer.py — Vẽ phụ đề thành ảnh PNG bằng Pillow.

Vì sao KHÔNG dùng bộ lọc `subtitles` của ffmpeg (libass) như trước: bộ lọc đó
chỉ tồn tại khi ffmpeg được build kèm `libass`, mà điều đó KHÔNG đảm bảo —
formula `ffmpeg` của Homebrew (macOS) hiện không còn build libass, nên burn phụ
đề fail hoàn toàn trên máy dev dù code đúng (xác nhận thật: `ffmpeg -filters`
không có `subtitles`, job duy nhất từng burn được là job chạy trong Docker).
Vẽ chữ bằng Pillow rồi `overlay` ảnh vào video chạy được với MỌI bản ffmpeg
(chỉ cần `overlay` — bộ lọc lõi, luôn có), đồng thời cho toàn quyền kiểm soát
vị trí từng dòng theo pixel — đúng thứ feature 009 cần.

Kích cỡ chữ/lề GIỮ NGUYÊN diện mạo cũ: tham số cũ (`FontSize=16`, `MarginV=40`,
`Outline=1`) nằm trong hệ toạ độ ASS mặc định của libass (PlayResY=288), nên
quy đổi sang pixel thật bằng tỉ lệ `frame_height / 288` — xem `_scale_for()`.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Hệ toạ độ ASS mặc định của libass khi file phụ đề không khai PlayResX/Y —
# mọi tham số style cũ (.srt + force_style) được libass hiểu trong hệ này, nên
# phải quy đổi qua đây thì chữ mới ra đúng cỡ như trước.
_LEGACY_PLAY_RES_Y = 288
_LEGACY_FONT_SIZE = 16
_LEGACY_MARGIN_V = 40
_LEGACY_OUTLINE = 1

# Cỡ chữ phụ đề mới ở vùng có phụ đề gốc = tỉ lệ này × cỡ chữ mặc định
# (Assumption "cỡ chữ cố định theo tỉ lệ", spec.md 009).
_HARDSUB_SMALL_FONT_RATIO = 0.75

# Bề rộng tối đa của khối chữ, theo tỉ lệ bề ngang khung hình
_DEFAULT_MAX_WIDTH_RATIO = 0.9
# Sàn bề rộng khi vẽ đè vùng phụ đề gốc — vùng người dùng khoanh có thể rất hẹp,
# ép xuống cạnh đó sẽ dựng thành tháp chữ nhiều dòng
_REGION_MIN_WIDTH_RATIO = 0.5

# Khoảng cách giữa 2 dòng = tỉ lệ này × chiều cao chữ
_LINE_SPACING_RATIO = 1.25

# Số TỪ tối đa của MỘT cue hiển thị cùng lúc — kiểu chữ chạy từng cụm ngắn
# quen thuộc của TikTok/Shorts. Cue dài hơn bị tách thành nhiều mẩu nối tiếp
# nhau, chia thời lượng theo tỉ lệ độ dài (`_split_long_cues()`).
#
# Vì sao tách ở ĐÂY chứ không sửa chỗ sinh cue: cue đến từ timeline TTS
# (tts/segment_synthesizer.py), mỗi cue khớp đúng 1 nhịp giọng đọc — mốc thời
# gian đó phải giữ nguyên cho việc lồng tiếng. Chia nhỏ để đọc được là chuyện
# thuần hiển thị, không được đụng vào timeline gốc.
_MAX_WORDS_PER_CUE = 3

# Thời lượng tối thiểu (giây) một mẩu phụ đề được hiện. Mẩu ngắn hơn bị gộp vào
# mẩu liền kề — không có mốc thời gian theo TỪNG TỪ (voice_timeline.json chỉ có
# mốc theo nhịp), nên thời lượng mỗi cụm suy ra theo tỉ lệ độ dài; cụm rơi vào
# đoạn đọc nhanh có thể chỉ hiện ~0.1s, chớp qua không kịp đọc.
# Ngưỡng thấp (0.35s) vì cụm chỉ 3 từ đọc rất nhanh — đặt cao sẽ gộp ngược lại
# thành cụm dài, phá đúng thứ đang muốn.
_MIN_CUE_DURATION = 0.35

_TEXT_COLOUR = (255, 255, 255, 255)  # trắng
_OUTLINE_COLOUR = (0, 0, 0, 255)  # viền đen

# Biến môi trường cho phép chỉ định font riêng, ưu tiên hơn mọi ứng viên dưới
_FONT_ENV_VAR = "SUBTITLE_FONT_PATH"

# Ứng viên font theo thứ tự ưu tiên. BẮT BUỘC phải có dấu tiếng Việt đầy đủ —
# đây là lý do không dùng bừa font đầu tiên tìm được trên máy.
_FONT_CANDIDATES = (
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux (Debian/Ubuntu — gói fonts-dejavu-core / fonts-liberation)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


class FontNotFoundError(RuntimeError):
    """Không tìm thấy font nào để vẽ phụ đề."""


def find_font_path() -> Path:
    """
    Đường dẫn font dùng để vẽ phụ đề: `$SUBTITLE_FONT_PATH` nếu có, ngược lại
    ứng viên đầu tiên tồn tại trong `_FONT_CANDIDATES`.

    Raises:
        FontNotFoundError: không có ứng viên nào tồn tại — kèm hướng dẫn cài.
    """
    override = os.environ.get(_FONT_ENV_VAR)
    if override:
        path = Path(override)
        if not path.exists():
            raise FontNotFoundError(
                f"{_FONT_ENV_VAR} trỏ tới font không tồn tại: {path}"
            )
        return path

    for candidate in _FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path

    raise FontNotFoundError(
        "Không tìm thấy font nào để vẽ phụ đề. Cài một font có dấu tiếng Việt "
        "(Linux: `apt-get install fonts-dejavu-core`), hoặc trỏ biến môi trường "
        f"{_FONT_ENV_VAR} tới file .ttf muốn dùng."
    )


def _scale_for(frame_height: int) -> float:
    """Tỉ lệ quy đổi từ hệ toạ độ ASS mặc định (PlayResY=288) sang pixel thật."""
    return frame_height / _LEGACY_PLAY_RES_Y


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """
    Ngắt `text` thành các dòng không vượt `max_width` (pixel), ngắt theo TỪ.

    Từ đơn dài hơn cả `max_width` vẫn được giữ nguyên trên một dòng (không cắt
    giữa từ) — thà tràn một chút còn hơn cắt vỡ chữ khó đọc.
    """
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _render_text_image(
    lines: list[str], font: ImageFont.FreeTypeFont, stroke_width: int
) -> Image.Image:
    """Vẽ các dòng chữ (đã ngắt sẵn) căn giữa lên ảnh RGBA nền trong suốt."""
    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    line_step = round(line_height * _LINE_SPACING_RATIO)

    text_width = max((font.getlength(line) for line in lines), default=0)
    # Nới thêm bề dày viền ở cả 4 phía để nét viền không bị cắt cụt ở mép ảnh
    pad = stroke_width * 2
    img_width = max(1, round(text_width) + pad * 2)
    img_height = max(1, line_step * (len(lines) - 1) + line_height + pad * 2)

    image = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text(
            (img_width / 2, pad + i * line_step),
            line,
            font=font,
            fill=_TEXT_COLOUR,
            anchor="ma",  # middle-ascender: căn giữa ngang, mốc dọc ở đỉnh chữ
            stroke_width=stroke_width,
            stroke_fill=_OUTLINE_COLOUR,
        )
    return image


def _split_text_into_chunks(text: str, max_words: int) -> list[str]:
    """
    Chia `text` thành các cụm dài tối đa `max_words` TỪ, CÂN BẰNG số từ giữa
    các cụm (không gộp tham lam tới sát giới hạn rồi để lại cụm lẻ 1 từ ở cuối
    — bug thật đã gặp: dồn hết chữ vào cụm đầu, cụm cuối chỉ còn 1 từ, hiện
    chớp qua không kịp đọc).
    """
    words = text.strip().split()
    n = len(words)
    if n == 0:
        return []

    chunk_count = max(1, -(-n // max_words))  # ceil(n / max_words)
    base, remainder = divmod(n, chunk_count)

    chunks: list[str] = []
    idx = 0
    for i in range(chunk_count):
        size = base + (1 if i < remainder else 0)
        chunks.append(" ".join(words[idx : idx + size]))
        idx += size
    return chunks


def _merge_too_short(sub_cues: list[dict], min_duration: float) -> list[dict]:
    """
    Gộp các mẩu ngắn hơn `min_duration` vào mẩu liền trước (mẩu đầu tiên gộp
    vào mẩu liền sau, vì nó không có mẩu trước). Giữ nguyên hai đầu mốc thời
    gian của cả chuỗi.
    """
    if len(sub_cues) <= 1:
        return sub_cues

    merged: list[dict] = []
    for cue in sub_cues:
        if merged and (cue["end"] - cue["start"]) < min_duration:
            previous = merged[-1]
            previous["text"] = f"{previous['text']} {cue['text']}"
            previous["end"] = cue["end"]
        else:
            merged.append(dict(cue))

    if len(merged) > 1 and (merged[0]["end"] - merged[0]["start"]) < min_duration:
        merged[1]["start"] = merged[0]["start"]
        merged[1]["text"] = f"{merged[0]['text']} {merged[1]['text']}"
        merged.pop(0)

    return merged


def _split_long_cues(cues: list[dict], max_words: int = _MAX_WORDS_PER_CUE) -> list[dict]:
    """
    Tách các cue có nhiều hơn `max_words` từ thành nhiều cue nối tiếp
    (`_MAX_WORDS_PER_CUE` từ mỗi lần hiện — kiểu chữ chạy cụm ngắn), chia thời
    lượng của cue gốc theo TỈ LỆ ĐỘ DÀI từng cụm — tổng thời gian và hai đầu
    mốc giữ nguyên, nên phụ đề vẫn bám đúng nhịp giọng đọc.

    Cue đã đủ ngắn được trả về nguyên vẹn (không sao chép thừa).
    """
    result: list[dict] = []
    for cue in cues:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        if len(text.split()) <= max_words:
            result.append(cue)
            continue

        chunks = _split_text_into_chunks(text, max_words)
        if len(chunks) <= 1:
            result.append(cue)
            continue

        start = float(cue["start"])
        end = float(cue["end"])
        total_chars = sum(len(c) for c in chunks)
        cursor = start
        sub_cues: list[dict] = []
        for i, chunk in enumerate(chunks):
            # Mẩu cuối lấy đúng `end` để không lệch do làm tròn dồn lại
            chunk_end = end if i == len(chunks) - 1 else cursor + (end - start) * (
                len(chunk) / total_chars
            )
            sub_cues.append({"start": cursor, "end": chunk_end, "text": chunk})
            cursor = chunk_end

        result.extend(_merge_too_short(sub_cues, _MIN_CUE_DURATION))

    return result


def _find_overlapping_region(cue: dict, regions: list[dict]) -> dict | None:
    """
    Vùng phụ đề gốc (đã lọc dùng được) mà `cue` giao vào, hoặc None. Các vùng là
    các đoạn liên tục tách biệt theo thời gian nên không cần xử lý chồng lấn.
    """
    for region in regions:
        if cue["start"] < region["end"] and cue["end"] > region["start"]:
            return region
    return None


def render_cue_overlays(
    cues: list[dict],
    regions: list[dict],
    frame_size: dict,
    out_dir: str | Path,
) -> list[dict]:
    """
    Vẽ mỗi cue thành 1 file PNG nền trong suốt và tính sẵn toạ độ overlay.

    Cue nào GIAO với một vùng phụ đề gốc dùng được (`detected=true`,
    `excluded=false` — hàm tự lọc, chỗ gọi không cần lọc trước) thì được đặt
    đúng vào vùng đó (căn giữa ngang theo tâm box, đáy chữ trùng đáy box) với
    cỡ chữ nhỏ hơn mặc định. Cue khác nằm ở vị trí mặc định: căn giữa ngang,
    cách đáy khung hình đúng bằng lề cũ (FR-005, SC-006).

    Cue quá dài được tách thành nhiều mẩu nối tiếp trước khi vẽ
    (`_split_long_cues()`) — xem `_MAX_WORDS_PER_CUE` về lý do tách ở đây.

    Args:
        cues: List[{"start", "end", "text"}], giây.
        regions: TOÀN BỘ vùng phụ đề gốc (kể cả không dùng được).
        frame_size: {"width", "height"} của video sẽ burn lên.
        out_dir: thư mục chứa PNG sinh ra (tạo nếu chưa có).

    Returns:
        List[{"image": Path, "x": int, "y": int, "start": float, "end": float}]
        — cue rỗng chữ bị bỏ qua, nên danh sách có thể ngắn hơn `cues`.

    Raises:
        FontNotFoundError: máy không có font nào vẽ được.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frame_width = int(frame_size["width"])
    frame_height = int(frame_size["height"])
    scale = _scale_for(frame_height)

    font_path = find_font_path()
    default_font_px = max(1, round(_LEGACY_FONT_SIZE * scale))
    small_font_px = max(1, round(default_font_px * _HARDSUB_SMALL_FONT_RATIO))
    stroke_px = max(1, round(_LEGACY_OUTLINE * scale))
    margin_v_px = round(_LEGACY_MARGIN_V * scale)

    default_font = ImageFont.truetype(str(font_path), default_font_px)
    small_font = ImageFont.truetype(str(font_path), small_font_px)

    usable_regions = [r for r in regions if r["detected"] and not r["excluded"]]

    overlays: list[dict] = []
    for i, cue in enumerate(_split_long_cues(cues)):
        text = (cue.get("text") or "").strip()
        if not text:
            continue

        region = _find_overlapping_region(cue, usable_regions)
        if region is not None:
            box = region["box"]
            font = small_font
            max_width = max(box["w"], frame_width * _REGION_MIN_WIDTH_RATIO)
            center_x = box["x"] + box["w"] / 2
            bottom_y = box["y"] + box["h"]
        else:
            font = default_font
            max_width = frame_width * _DEFAULT_MAX_WIDTH_RATIO
            center_x = frame_width / 2
            bottom_y = frame_height - margin_v_px

        lines = _wrap_lines(text, font, max_width)
        if not lines:
            continue

        image = _render_text_image(lines, font, stroke_px)
        image_path = out_dir / f"cue_{i:04d}.png"
        image.save(image_path)

        # Kẹp trong khung hình để overlay không bị ffmpeg cắt mất một phần
        x = round(center_x - image.width / 2)
        y = round(bottom_y - image.height)
        x = max(0, min(x, frame_width - image.width))
        y = max(0, min(y, frame_height - image.height))

        overlays.append(
            {
                "image": image_path,
                "x": x,
                "y": y,
                "start": float(cue["start"]),
                "end": float(cue["end"]),
            }
        )

    return overlays

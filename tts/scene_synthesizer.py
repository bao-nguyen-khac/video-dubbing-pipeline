"""
tts/scene_synthesizer.py — synthesize_scene(): tổng hợp giọng đọc cho ĐÚNG 1
scene của tính năng "Tạo video từ chủ đề" (010-topic-video-generation).

Gọi THẲNG adapter provider có sẵn trong `tts/segment_synthesizer.py`
(`_get_adapter()`) thay vì qua `synthesize_segments()` cấp cao — hàm đó được
thiết kế cho khái niệm "dubbing unit" khớp timeline ASR gốc (fit vào cửa sổ
thời gian có sẵn, resume theo voice_timeline.json), không khớp nhu cầu ở đây:
mỗi scene độc lập, không cần khớp cửa sổ thời gian nào (research.md §6).
"""

from __future__ import annotations

from pathlib import Path

from media_utils import get_media_duration
from tts.segment_synthesizer import _get_adapter


def synthesize_scene(
    text: str,
    output_path: Path,
    provider: str = "edge-tts",
    voice_id: str | None = None,
) -> float:
    """
    Tổng hợp giọng đọc cho `text` bằng `provider`, ghi ra `output_path`, trả về
    thời lượng THẬT đo từ file audio vừa tạo (KHÔNG phải ước lượng ký tự/giây
    — data-model.md §3: `duration` chỉ có giá trị thật sau bước này).

    Raises:
        ValueError: `provider` không hợp lệ (từ `_get_adapter()`).
        RuntimeError: `provider` yêu cầu `voice_id` mà không có, hoặc TTS lỗi.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    adapter = _get_adapter(provider, voice_id)
    adapter(text, output_path)

    return get_media_duration(output_path)

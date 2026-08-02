"""
assets/pexels_client.py — search_image(query) tìm ảnh minh hoạ qua Pexels
Photos API, dùng cho từng scene của tính năng "Tạo video từ chủ đề"
(010-topic-video-generation, data-model.md §3, research.md §4).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

_TIMEOUT = 20.0

# US3/FR-010: ảnh nền trung tính tĩnh — phương án CUỐI khi cả 2 lượt tìm trên
# Pexels đều rỗng. Không phải gọi API, luôn có sẵn trong repo.
FALLBACK_IMAGE_PATH = Path(__file__).parent / "fallback_images" / "generic.jpg"


def _client(timeout: float = _TIMEOUT) -> httpx.Client:
    """Factory riêng để test thay bằng `httpx.MockTransport` (Constitution VI)."""
    return httpx.Client(headers={"Authorization": PEXELS_API_KEY}, timeout=timeout)


def _fetch_top_image_url(query: str, client: httpx.Client) -> str | None:
    """1 lượt gọi Pexels — trả URL ảnh xếp hạng đầu, hoặc `None` nếu rỗng."""
    res = client.get(
        PEXELS_SEARCH_URL,
        params={"query": query, "orientation": "portrait", "per_page": 1},
    )
    res.raise_for_status()
    photos = res.json().get("photos", [])
    if not photos:
        return None

    # "large2x" (~1880px) đủ nét cho render 1080x1920 mà không quá nặng như
    # "original"; fallback "original" nếu Pexels đổi shape response.
    src = photos[0].get("src", {})
    return src.get("large2x") or src.get("original")


def _shorten_query(query: str) -> str:
    """Giữ 2 từ khoá đầu — thu hẹp về chủ đề rộng hơn cho lượt tìm thứ 2
    (US3, research.md §4). Trả nguyên `query` nếu đã ≤ 2 từ (không có gì để
    rút gọn thêm — `search_image()` tự bỏ qua lượt gọi lại vô nghĩa đó)."""
    words = query.split()
    return " ".join(words[:2]) if len(words) > 2 else query


def search_image(query: str, job_dir: Path) -> Path:
    """
    Tìm 1 ảnh minh hoạ tỉ lệ dọc (9:16) trên Pexels khớp `query`, tải về
    `job_dir/image.jpg`.

    Gọi cho ĐÚNG 1 scene mỗi lượt — `job_dir` ở đây là thư mục RIÊNG của scene
    đó (VD `jobs/{job_id}/scenes/{i}/`), không phải thư mục job gốc. Chỗ gọi
    (`generate_pipeline.py`) tự lo tạo đường dẫn `scenes/{i}/` cho từng scene.

    US3/FR-010: KHÔNG BAO GIỜ trả về rỗng. Pexels không có kết quả cho
    `query` → thử lại 1 lần với từ khoá rút gọn (`_shorten_query()`); vẫn
    rỗng → dùng `FALLBACK_IMAGE_PATH` (ảnh nền trung tính tĩnh, không gọi
    API) làm phương án cuối. Scene không bao giờ thiếu ảnh hoàn toàn.

    Raises:
        RuntimeError: Nếu thiếu `PEXELS_API_KEY`.
        httpx.HTTPStatusError: Nếu Pexels trả lỗi HTTP thật (khác "0 kết
            quả" — đó là lỗi thật, phải nổi lên rõ ràng, không lặng lẽ dùng
            fallback).
    """
    if not PEXELS_API_KEY:
        raise RuntimeError("Thiếu PEXELS_API_KEY trong .env — không gọi được Pexels")

    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    image_path = job_dir / "image.jpg"

    with _client() as client:
        image_url = _fetch_top_image_url(query, client)

        if not image_url:
            shortened = _shorten_query(query)
            if shortened != query:
                image_url = _fetch_top_image_url(shortened, client)

        if not image_url:
            image_path.write_bytes(FALLBACK_IMAGE_PATH.read_bytes())
            return image_path

        image_res = client.get(image_url)
        image_res.raise_for_status()

    image_path.write_bytes(image_res.content)
    return image_path

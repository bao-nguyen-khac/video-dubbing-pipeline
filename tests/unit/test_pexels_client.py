"""
tests/unit/test_pexels_client.py — search_image() (010-topic-video-generation).

⚠️ Constitution §VI: KHÔNG test nào được gọi thật tới api.pexels.com — mọi
request đi qua httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from assets import pexels_client


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setattr(pexels_client, "PEXELS_API_KEY", "test-pexels-key")


def mock_client(handler):
    def factory(timeout: float = pexels_client._TIMEOUT):
        return httpx.Client(
            headers={"Authorization": pexels_client.PEXELS_API_KEY},
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    return factory


def test_search_image_downloads_top_result(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "api.pexels.com/v1/search" in str(request.url):
            assert request.headers["Authorization"] == "test-pexels-key"
            return httpx.Response(
                200,
                json={
                    "photos": [
                        {"src": {"large2x": "https://images.pexels.com/photo1.jpg"}}
                    ]
                },
            )
        assert str(request.url) == "https://images.pexels.com/photo1.jpg"
        return httpx.Response(200, content=b"fake-jpeg-bytes")

    monkeypatch.setattr(pexels_client, "_client", mock_client(handler))

    result = pexels_client.search_image("ancient coins currency", tmp_path)

    assert result == tmp_path / "image.jpg"
    assert result.read_bytes() == b"fake-jpeg-bytes"


def test_search_image_retries_with_shortened_query_when_first_empty(monkeypatch, tmp_path):
    """US3/T036: query dài rỗng lượt 1 → thử lại với 2 từ khoá đầu, lượt 2 có
    kết quả → dùng luôn, KHÔNG rơi xuống fallback tĩnh."""
    queries_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "api.pexels.com/v1/search" in str(request.url):
            q = request.url.params.get("query")
            queries_seen.append(q)
            if q == "ancient coins":  # lượt 2 (rút gọn) có kết quả
                return httpx.Response(
                    200, json={"photos": [{"src": {"large2x": "https://images.pexels.com/ok.jpg"}}]}
                )
            return httpx.Response(200, json={"photos": []})  # lượt 1 (đầy đủ) rỗng
        return httpx.Response(200, content=b"real-photo-bytes")

    monkeypatch.setattr(pexels_client, "_client", mock_client(handler))

    result = pexels_client.search_image("ancient coins currency history museum", tmp_path)

    assert queries_seen == ["ancient coins currency history museum", "ancient coins"]
    assert result.read_bytes() == b"real-photo-bytes"


def test_search_image_falls_back_to_static_image_when_both_empty(monkeypatch, tmp_path):
    """US3/T036: CẢ 2 lượt (đầy đủ + rút gọn) đều rỗng → dùng ảnh nền tĩnh có
    sẵn trong repo, KHÔNG raise lỗi, KHÔNG để image_path null."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"photos": []})

    monkeypatch.setattr(pexels_client, "_client", mock_client(handler))

    result = pexels_client.search_image("một chủ đề rất hiếm gặp không ai tìm ra", tmp_path)

    assert result == tmp_path / "image.jpg"
    assert result.exists()
    assert result.read_bytes() == pexels_client.FALLBACK_IMAGE_PATH.read_bytes()


def test_search_image_skips_redundant_retry_when_query_already_short(monkeypatch, tmp_path):
    """Query ≤ 2 từ — rút gọn ra chính nó, KHÔNG gọi lại vô nghĩa lần 2."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"photos": []})

    monkeypatch.setattr(pexels_client, "_client", mock_client(handler))

    result = pexels_client.search_image("coins", tmp_path)

    assert call_count["n"] == 1  # chỉ 1 lượt search (không có lượt rút gọn trùng lặp)
    assert result.read_bytes() == pexels_client.FALLBACK_IMAGE_PATH.read_bytes()


def test_search_image_raises_without_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(pexels_client, "PEXELS_API_KEY", "")

    with pytest.raises(RuntimeError):
        pexels_client.search_image("x", tmp_path)


def test_search_image_raises_on_http_error(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    monkeypatch.setattr(pexels_client, "_client", mock_client(handler))

    with pytest.raises(httpx.HTTPStatusError):
        pexels_client.search_image("x", tmp_path)


def test_search_image_creates_job_dir_if_missing(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "api.pexels.com" in str(request.url):
            return httpx.Response(
                200, json={"photos": [{"src": {"original": "https://images.pexels.com/p.jpg"}}]}
            )
        return httpx.Response(200, content=b"bytes")

    monkeypatch.setattr(pexels_client, "_client", mock_client(handler))
    nested_dir = tmp_path / "scenes" / "0"

    result = pexels_client.search_image("x", nested_dir)

    assert result == nested_dir / "image.jpg"
    assert nested_dir.exists()

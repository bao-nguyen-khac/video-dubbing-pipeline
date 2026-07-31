"""
tests/unit/test_router_unsupported_params.py — Model từ chối tham số tuỳ chọn.

Bối cảnh thật: 9router định tuyến sang `github/gpt-5.4-mini`, model này trả 400
"Unsupported parameter: 'temperature' is not supported with this model" và làm
hỏng nguyên job dù chỉ cần bỏ 1 tham số tuỳ chọn là gọi được.

⚠️ Constitution §VI: SDK openai được thay bằng client giả — không lượt nào ra
mạng thật.
"""

from __future__ import annotations

import pytest

from script_gen import router_client


@pytest.fixture(autouse=True)
def clear_param_cache():
    """Bộ nhớ 'model này không nhận tham số X' là cấp module — dọn giữa các test."""
    router_client._UNSUPPORTED_PARAMS.clear()
    yield
    router_client._UNSUPPORTED_PARAMS.clear()


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]
        self.usage = None


class _FakeCompletions:
    """Từ chối các tham số trong `reject`, ghi lại kwargs của từng lượt gọi."""

    def __init__(self, reject: set[str], calls: list[dict]):
        self.reject = reject
        self.calls = calls

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        for param in self.reject:
            if param in kwargs:
                raise Exception(
                    f"[github/gpt-5.4-mini] [400]: {{\"error\":{{\"message\":"
                    f"\"Unsupported parameter: '{param}' is not supported with "
                    f"this model.\",\"code\":\"invalid_request_body\"}}}}"
                )
        return _Response("KẾT QUẢ")


@pytest.fixture()
def fake_openai(monkeypatch):
    """Thay openai.OpenAI bằng client giả; trả về danh sách kwargs đã gửi."""
    calls: list[dict] = []
    state = {"reject": set()}

    class _FakeClient:
        def __init__(self, **_):
            self.chat = type("chat", (), {"completions": _FakeCompletions(state["reject"], calls)})()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)
    return state, calls


def test_rejected_param_matches_real_9router_message():
    """
    Chuỗi lỗi THẬT ghi lại từ 9router: đi qua nhiều lớp JSON lồng nhau nên dấu
    nháy quanh tên tham số bị escape thành \\' — khớp theo dấu nháy sẽ trượt.
    """
    real = (
        "Error code: 400 - {'error': {'message': '[github/gpt-5.4-mini] [400]: "
        '{"error":{"message":"Unsupported parameter: \\\'temperature\\\' is not '
        'supported with this model.","code":"invalid_request_body"}}\\n '
        "(reset after 30s)'}}"
    )

    assert router_client._rejected_param(real, {"temperature", "max_tokens"}) == "temperature"
    # Không gửi temperature thì không có gì để bỏ
    assert router_client._rejected_param(real, {"max_tokens"}) is None


def test_retries_without_temperature_when_model_rejects_it(fake_openai):
    state, calls = fake_openai
    state["reject"].add("temperature")

    out = router_client._call_chat_api(
        "http://router.test/v1", "key", "github/gpt-5.4-mini", "sys", "user", 0.3
    )

    assert out == "KẾT QUẢ"
    assert len(calls) == 2
    assert "temperature" in calls[0]  # lượt đầu vẫn gửi như bình thường
    assert "temperature" not in calls[1]  # lượt sau bỏ đúng tham số bị từ chối
    # Các tham số khác KHÔNG bị bỏ lây
    assert calls[1]["model"] == "github/gpt-5.4-mini"
    assert calls[1]["messages"][0]["content"] == "sys"
    assert "max_tokens" in calls[1]


def test_remembers_rejection_so_next_call_skips_the_bad_param(fake_openai):
    state, calls = fake_openai
    state["reject"].add("temperature")

    router_client._call_chat_api("http://r/v1", "k", "m", "sys", "u1", 0.3)
    calls.clear()
    router_client._call_chat_api("http://r/v1", "k", "m", "sys", "u2", 0.3)

    # Lượt gọi thứ hai không được lặp lại cú gọi hỏng nữa
    assert len(calls) == 1
    assert "temperature" not in calls[0]


def test_rejection_is_remembered_per_model(fake_openai):
    state, calls = fake_openai
    state["reject"].add("temperature")

    router_client._call_chat_api("http://r/v1", "k", "model-a", "sys", "u", 0.3)
    calls.clear()
    # Model khác chưa biết gì → vẫn phải thử với temperature như bình thường
    router_client._call_chat_api("http://r/v1", "k", "model-b", "sys", "u", 0.3)

    assert "temperature" in calls[0]


def test_drops_multiple_rejected_params(fake_openai):
    state, calls = fake_openai
    state["reject"].update({"temperature", "max_tokens"})

    out = router_client._call_chat_api("http://r/v1", "k", "m", "sys", "u", 0.3)

    assert out == "KẾT QUẢ"
    assert "temperature" not in calls[-1]
    assert "max_tokens" not in calls[-1]


def test_other_400_errors_are_not_swallowed(fake_openai):
    """Lỗi 400 KHÁC phải nổi lên nguyên vẹn, không bị hiểu nhầm là tham số thừa."""
    state, calls = fake_openai

    class _AlwaysFail(_FakeCompletions):
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            raise Exception("[400]: model_not_found: No active credentials for provider")

    import openai

    class _C:
        def __init__(self, **_):
            self.chat = type("chat", (), {"completions": _AlwaysFail(set(), calls)})()

    openai.OpenAI = _C

    with pytest.raises(Exception, match="model_not_found"):
        router_client._call_chat_api("http://r/v1", "k", "m", "sys", "u", 0.3)

    assert len(calls) == 1  # không thử lại vô ích


def test_unsupported_message_for_param_we_did_not_send_is_not_swallowed(fake_openai):
    """
    Endpoint than phiền về tham số ta KHÔNG gửi → không có gì để bỏ, phải ném lỗi
    thay vì lặp lại lượt gọi hỏng.
    """
    state, calls = fake_openai

    class _Weird(_FakeCompletions):
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            raise Exception("Unsupported parameter: 'top_k' is not supported")

    import openai

    class _C:
        def __init__(self, **_):
            self.chat = type("chat", (), {"completions": _Weird(set(), calls)})()

    openai.OpenAI = _C

    with pytest.raises(Exception, match="top_k"):
        router_client._call_chat_api("http://r/v1", "k", "m", "sys", "u", 0.3)

    assert len(calls) == 1

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from providers.qwen import (
    DashScopeOpenAITransport,
    QwenLLMProvider,
    QwenMultimodalProvider,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_real_llm_transport_calls_dashscope_and_normalizes_text():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(
            {"choices": [{"message": {"content": "带伞并检查钥匙。"}}]}
        )

    provider = QwenLLMProvider(
        api_key="sk-secret",
        model_name="qwen-plus",
        client=DashScopeOpenAITransport(opener=opener, timeout_seconds=12),
    )

    result = provider.generate("给出出门提醒", trace_id="trace-llm")

    assert result.succeeded
    assert result.output == {"text": "带伞并检查钥匙。"}
    request, timeout = requests[0]
    body = json.loads(request.data)
    assert request.full_url.endswith("/compatible-mode/v1/chat/completions")
    assert request.headers["Authorization"] == "Bearer sk-secret"
    assert body == {
        "model": "qwen-plus",
        "messages": [{"role": "user", "content": "给出出门提醒"}],
    }
    assert timeout == 12
    assert "sk-secret" not in repr(result)


def test_provider_repr_never_exposes_api_key():
    provider = QwenLLMProvider(
        api_key="sk-do-not-log",
        model_name="qwen-plus",
        client=lambda payload: {"text": "ok"},
    )

    assert "sk-do-not-log" not in repr(provider)


def test_multimodal_transport_accepts_encoded_frames_and_normalizes_scene():
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "scene_summary": "桌面上有钥匙和雨伞。",
                                    "visible_items": ["keys", "umbrella"],
                                    "umbrella_visible": True,
                                }
                            )
                        }
                    }
                ]
            }
        )

    provider = QwenMultimodalProvider(
        api_key="sk-secret",
        model_name="qwen-vl-plus",
        client=DashScopeOpenAITransport(opener=opener),
    )

    result = provider.describe(
        {
            "frames": (
                {"bytes": b"jpeg-one", "mime_type": "image/jpeg"},
                {"data": b"png-two", "mime_type": "image/png"},
            ),
            "handoff_goal": "看看桌上有没有伞",
        },
        trace_id="trace-vision",
    )

    assert result.output == {
        "scene_summary": "桌面上有钥匙和雨伞。",
        "visible_items": ("keys", "umbrella"),
        "umbrella_visible": True,
    }
    body = json.loads(requests[0].data)
    content = body["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (
            HTTPError(
                "https://dashscope.aliyuncs.com",
                401,
                "Unauthorized",
                {},
                BytesIO(b'{"message":"invalid key"}'),
            ),
            "authentication_error",
        ),
        (
            HTTPError(
                "https://dashscope.aliyuncs.com",
                429,
                "Too Many Requests",
                {},
                BytesIO(b'{"message":"rate limited"}'),
            ),
            "rate_limit_error",
        ),
        (TimeoutError("timed out"), "timeout_error"),
        (URLError("connection refused"), "transport_error"),
    ],
)
def test_transport_failures_become_structured_provider_errors(
    failure,
    expected_code,
):
    def opener(request, timeout):
        raise failure

    provider = QwenLLMProvider(
        api_key="sk-secret",
        model_name="qwen-plus",
        client=DashScopeOpenAITransport(opener=opener),
    )

    result = provider.generate("hello", trace_id="trace-error")

    assert result.failed
    assert result.error.code == expected_code
    assert result.error.provider_name == "qwen_llm"
    assert "sk-secret" not in result.error.message
    assert "sk-secret" not in repr(result.error.metadata)


def test_malformed_response_becomes_structured_provider_error():
    provider = QwenLLMProvider(
        api_key="sk-secret",
        model_name="qwen-plus",
        client=DashScopeOpenAITransport(
            opener=lambda request, timeout: FakeResponse({"choices": []})
        ),
    )

    result = provider.generate("hello")

    assert result.failed
    assert result.error.code == "malformed_response"

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from providers.qwen import DashScopeOpenAITransport, QwenSpeechProvider


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def microphone_audio():
    return {
        "type": "audio",
        "bytes": b"pcm-s16le",
        "mime_type": "audio/L16",
        "sample_format": "int16",
        "sample_rate": 16_000,
        "channels": 1,
        "duration_seconds": 5,
    }


def test_qwen_speech_encodes_microphone_audio_and_normalizes_transcript():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Ella，我要出门了。",
                            "annotations": [{"language": "zh"}],
                        }
                    }
                ]
            }
        )

    provider = QwenSpeechProvider(
        api_key="sk-test",
        model_name="qwen3-asr-flash",
        client=DashScopeOpenAITransport(opener=opener),
    )

    result = provider.transcribe(
        microphone_audio(),
        trace_id="trace-speech",
    )

    assert result.succeeded
    assert result.output == {
        "text": "Ella，我要出门了。",
        "language": "zh",
    }
    request, timeout = requests[0]
    body = json.loads(request.data)
    audio_data = body["messages"][0]["content"][0]["input_audio"]["data"]
    assert request.full_url.endswith("/compatible-mode/v1/chat/completions")
    assert audio_data.startswith("data:audio/pcm;base64,")
    assert body["model"] == "qwen3-asr-flash"
    assert body["stream"] is False
    assert body["asr_options"] == {"enable_itn": False}
    assert timeout == 30.0


def test_qwen_transport_passes_timeout_as_keyword_for_real_urlopen_signature():
    calls = []

    def opener(request, *, timeout):
        calls.append(timeout)
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Ella，我要出门了。",
                            "annotations": [{"language": "zh"}],
                        }
                    }
                ]
            }
        )

    provider = QwenSpeechProvider(
        api_key="sk-test",
        model_name="qwen3-asr-flash",
        client=DashScopeOpenAITransport(opener=opener),
    )

    result = provider.transcribe(microphone_audio())

    assert result.succeeded
    assert calls == [30.0]


def test_qwen_speech_preserves_normalized_injected_transport_output():
    provider = QwenSpeechProvider(
        api_key="sk-test",
        model_name="qwen3-asr-flash",
        client=lambda payload: {"text": "hello", "language": "en"},
    )

    result = provider.transcribe(microphone_audio())

    assert result.output == {"text": "hello", "language": "en"}


@pytest.mark.parametrize(
    ("audio_update", "expected_code"),
    [
        ({"bytes": None}, "invalid_audio_format"),
        ({"sample_rate": 8_000}, "invalid_audio_format"),
        ({"channels": 0}, "invalid_audio_format"),
        ({"mime_type": "video/mp4"}, "invalid_audio_format"),
    ],
)
def test_qwen_speech_rejects_invalid_microphone_audio_shape(
    audio_update,
    expected_code,
):
    audio = {**microphone_audio(), **audio_update}
    provider = QwenSpeechProvider(
        api_key="sk-test",
        model_name="qwen3-asr-flash",
        client=DashScopeOpenAITransport(
            opener=lambda request, timeout: pytest.fail("network called")
        ),
    )

    result = provider.transcribe(audio)

    assert result.failed
    assert result.error.code == expected_code


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (
            HTTPError(
                "https://dashscope.aliyuncs.com",
                401,
                "Unauthorized",
                {},
                BytesIO(b"{}"),
            ),
            "authentication_error",
        ),
        (
            HTTPError(
                "https://dashscope.aliyuncs.com",
                429,
                "Too Many Requests",
                {},
                BytesIO(b"{}"),
            ),
            "rate_limit_error",
        ),
        (TimeoutError("timed out"), "timeout_error"),
        (URLError("connection refused"), "transport_error"),
    ],
)
def test_qwen_speech_transport_failures_are_structured(
    failure,
    expected_code,
):
    def opener(request, timeout):
        raise failure

    provider = QwenSpeechProvider(
        api_key="sk-test",
        model_name="qwen3-asr-flash",
        client=DashScopeOpenAITransport(opener=opener),
    )

    result = provider.transcribe(microphone_audio())

    assert result.failed
    assert result.error.code == expected_code


def test_qwen_speech_malformed_response_is_structured():
    provider = QwenSpeechProvider(
        api_key="sk-test",
        model_name="qwen3-asr-flash",
        client=DashScopeOpenAITransport(
            opener=lambda request, timeout: FakeResponse({"choices": []})
        ),
    )

    result = provider.transcribe(microphone_audio())

    assert result.failed
    assert result.error.code == "malformed_response"

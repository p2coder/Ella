from types import SimpleNamespace

from providers.deepseek import DeepSeekLLMProvider, DeepSeekOpenAITransport


def test_provider_normalizes_chat_completion_content() -> None:
    received = {}

    def client(payload):
        received.update(payload)
        return {
            "choices": [
                {"message": {"content": '{"action":"SUBMIT_RESULT"}'}}
            ]
        }

    provider = DeepSeekLLMProvider(
        api_key="secret",
        model_name="deepseek-v4-pro",
        client=client,
        thinking_enabled=True,
        reasoning_effort="high",
    )

    result = provider.generate("Decide the next action", task_id="task-1")

    assert result.succeeded
    assert result.output == {"text": '{"action":"SUBMIT_RESULT"}'}
    assert received["prompt"] == "Decide the next action"
    assert received["thinking_enabled"] is True
    assert received["reasoning_effort"] == "high"


def test_transport_uses_official_openai_compatible_parameters(monkeypatch) -> None:
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
            )

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=Completions())

    def factory(**kwargs):
        captured["client"] = kwargs
        return Client()

    direct_client = object()
    monkeypatch.setattr(
        DeepSeekOpenAITransport,
        "_direct_http_client",
        staticmethod(lambda: direct_client),
    )
    transport = DeepSeekOpenAITransport(client_factory=factory)
    response = transport(
        {
            "api_key": "secret",
            "model_name": "deepseek-v4-pro",
            "prompt": "Hello",
            "thinking_enabled": True,
            "reasoning_effort": "high",
        }
    )

    assert response.choices[0].message.content == "ok"
    assert captured["client"]["base_url"] == "https://api.deepseek.com"
    assert captured["client"]["http_client"] is direct_client
    assert captured["request"] == {
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
        "reasoning_effort": "high",
        "extra_body": {"thinking": {"type": "enabled"}},
    }


def test_missing_key_returns_structured_error() -> None:
    result = DeepSeekLLMProvider(api_key=None).generate("hello")

    assert result.failed
    assert result.error.code == "provider_unavailable"
    assert "secret" not in repr(result)

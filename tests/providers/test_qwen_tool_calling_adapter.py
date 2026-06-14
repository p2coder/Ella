from tools.base import ToolDefinition
from providers.factory import ProviderFactory
from providers.llm import serialize_tool_definition
from providers.qwen import (
    qwen_tool_call_to_decision,
    qwen_tools_from_definitions,
    QwenLLMProvider,
)
from config.settings import load_settings


def make_definition() -> ToolDefinition:
    return ToolDefinition(
        name="get_weather",
        description="Get current weather for a city. Do not use without location.",
        schema_version="1",
        input_schema={
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "api_key": {"type": "string"},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
        input_examples=({"location": "Tokyo"},),
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
    )


def test_internal_tool_definition_converts_to_qwen_native_metadata() -> None:
    tools = qwen_tools_from_definitions((make_definition(),))

    assert tools == (
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a city. Do not use without location.",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                    "additionalProperties": False,
                },
            },
        },
    )


def test_provider_neutral_definition_converts_to_qwen_native_metadata() -> None:
    serialized = serialize_tool_definition(make_definition())

    tools = qwen_tools_from_definitions((serialized,))

    assert tools[0]["function"]["name"] == "get_weather"
    assert tools[0]["function"]["parameters"]["required"] == ["location"]


def test_provider_native_tool_response_converts_to_internal_decision() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"location": "Tokyo"}',
                            },
                        }
                    ]
                }
            }
        ]
    }

    decision = qwen_tool_call_to_decision(
        response,
        known_tool_names=("get_weather",),
    )

    assert decision == {
        "action": "CALL_TOOL",
        "tool_name": "get_weather",
        "arguments": {"location": "Tokyo"},
        "reason": "Qwen requested tool get_weather.",
    }


def test_malformed_provider_tool_call_becomes_structured_error() -> None:
    decision = qwen_tool_call_to_decision(
        {"choices": [{"message": {"tool_calls": [{"function": {"name": "get_weather"}}]}}]},
        known_tool_names=("get_weather",),
    )

    assert decision["action"] == "REPLAN"
    assert decision["error"]["code"] == "malformed_tool_call"


def test_unknown_tool_call_name_becomes_structured_error() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "not_registered",
                                "arguments": "{}",
                            }
                        }
                    ]
                }
            }
        ]
    }

    decision = qwen_tool_call_to_decision(response, known_tool_names=("get_weather",))

    assert decision["action"] == "REPLAN"
    assert decision["error"]["code"] == "unknown_tool"


def test_credentials_are_not_serialized_into_tool_metadata() -> None:
    rendered = repr(qwen_tools_from_definitions((make_definition(),)))

    assert "api_key" not in rendered
    assert "secret" not in rendered
    assert "Authorization" not in rendered


def test_provider_tool_calling_does_not_leak_provider_fields() -> None:
    tools = qwen_tools_from_definitions((make_definition(),))

    assert "qwen" not in tools[0]
    assert "dashscope" not in tools[0]
    assert "provider" not in tools[0]


def test_factory_can_select_qwen_tool_calling_adapter_when_configured() -> None:
    factory = ProviderFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "true",
                "ELLA_QWEN_API_KEY": "sk-test",
                "ELLA_QWEN_LLM_MODEL": "qwen-plus",
            }
        )
    )

    provider = factory.llm()

    assert provider.provider_name == "qwen_llm"
    assert provider.supports_native_tool_calling is True


def test_qwen_provider_sends_native_tools_to_fake_transport() -> None:
    captured_payload = {}

    def fake_client(payload):
        captured_payload.update(payload)
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"location": "Tokyo"}',
                                }
                            }
                        ]
                    }
                }
            ]
        }

    provider = QwenLLMProvider(
        api_key="sk-test",
        model_name="qwen-plus",
        client=fake_client,
    )

    result = provider.generate_with_tools(
        "Should I use a tool?",
        tool_definitions=(make_definition(),),
        trace_id="trace-tool",
    )

    assert captured_payload["input"]["tools"][0]["function"]["name"] == "get_weather"
    assert result.output["action"] == "CALL_TOOL"
    assert result.output["tool_name"] == "get_weather"

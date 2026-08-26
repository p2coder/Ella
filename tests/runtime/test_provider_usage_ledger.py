from providers.base import ProviderResult
from runtime.provider_usage import aggregate_provider_usage, record_provider_usage


class Provider:
    provider_name = "test-provider"
    model_name = "test-model"


def _result(usage):
    return ProviderResult(
        "test-provider",
        "test-model",
        "trace-usage",
        {"text": "ok"},
        metadata={"usage": usage},
    )


def test_usage_calls_append_without_overwriting_previous_boundaries():
    state = {}

    record_provider_usage(
        state,
        boundary="first_decision",
        provider=Provider(),
        result=_result(
            {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
                "prompt_tokens_details": {"cached_tokens": 40},
            }
        ),
        success=True,
    )
    record_provider_usage(
        state,
        boundary="verification_decision",
        provider=Provider(),
        result=_result(
            {
                "prompt_tokens": 50,
                "completion_tokens": 5,
                "total_tokens": 55,
                "prompt_tokens_details": {"cached_tokens": 30},
            }
        ),
        success=True,
    )

    assert [item["boundary"] for item in state["provider_usage_calls"]] == [
        "first_decision",
        "verification_decision",
    ]
    assert state["provider_usage"]["prompt_tokens"] == 50
    assert aggregate_provider_usage(state["provider_usage_calls"]) == {
        "token_usage": 165,
        "prompt_tokens": 150,
        "completion_tokens": 15,
        "cached_tokens": 70,
        "cache_hit_rate": 46.7,
    }


def test_missing_provider_usage_is_recorded_without_estimation():
    state = {}

    record_provider_usage(
        state,
        boundary="execution_decision",
        provider=Provider(),
        result=None,
        success=False,
    )

    entry = state["provider_usage_calls"][0]
    assert entry["success"] is False
    assert entry["prompt_tokens"] is None
    assert entry["cached_tokens"] is None
    assert aggregate_provider_usage(state["provider_usage_calls"]) is None


def test_modalities_are_aggregated_separately():
    state = {}
    record_provider_usage(
        state,
        boundary="execution_decision",
        provider=Provider(),
        result=_result({"prompt_tokens": 10, "completion_tokens": 2}),
        modality="text",
        success=True,
    )
    record_provider_usage(
        state,
        boundary="camera_scene",
        provider=Provider(),
        result=_result({"prompt_tokens": 500, "completion_tokens": 20}),
        modality="multimodal",
        success=True,
    )

    assert aggregate_provider_usage(state["provider_usage_calls"], modality="text")[
        "prompt_tokens"
    ] == 10
    assert aggregate_provider_usage(
        state["provider_usage_calls"], modality="multimodal"
    )["prompt_tokens"] == 500

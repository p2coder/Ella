from providers.base import ProviderResult
from runtime.provider_usage import (
    aggregate_provider_usage,
    merge_provider_usage_calls,
    record_provider_usage,
)


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
    # The checkpoint rollup must be the aggregate over ALL calls, not the raw
    # usage of the latest call.
    assert state["provider_usage"] == {
        "token_usage": 165,
        "prompt_tokens": 150,
        "completion_tokens": 15,
        "cached_tokens": 70,
        "cache_hit_rate": 46.7,
    }
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
    assert state["provider_usage"] == {}


def test_deepseek_cache_field_names_are_recognized():
    state = {}

    record_provider_usage(
        state,
        boundary="execution_decision",
        provider=Provider(),
        result=_result(
            {
                "prompt_tokens": 900,
                "prompt_cache_hit_tokens": 800,
                "prompt_cache_miss_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 920,
            }
        ),
        success=True,
    )

    entry = state["provider_usage_calls"][0]
    assert entry["cached_tokens"] == 800
    assert state["provider_usage"]["cached_tokens"] == 800
    assert state["provider_usage"]["cache_hit_rate"] == 88.9


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


def test_child_call_ledgers_merge_into_the_task_aggregate():
    state = {}
    merge_provider_usage_calls(
        state,
        (
            {
                "boundary": "execution_decision",
                "modality": "text",
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "cached_tokens": 80,
                "total_tokens": 110,
                "success": True,
                "node_id": "research_a",
            },
            {
                "boundary": "execution_decision",
                "modality": "text",
                "prompt_tokens": 200,
                "completion_tokens": 20,
                "cached_tokens": 100,
                "total_tokens": 220,
                "success": True,
                "node_id": "research_b",
            },
        ),
    )

    assert len(state["provider_usage_calls"]) == 2
    assert state["provider_usage"] == {
        "token_usage": 330,
        "prompt_tokens": 300,
        "completion_tokens": 30,
        "cached_tokens": 180,
        "cache_hit_rate": 60.0,
    }


def test_empty_child_call_ledger_does_not_replace_existing_usage():
    state = {
        "provider_usage_calls": [{"boundary": "first_decision"}],
        "provider_usage": {"prompt_tokens": 10},
    }

    merge_provider_usage_calls(state, ())

    assert state["provider_usage_calls"] == [{"boundary": "first_decision"}]
    assert state["provider_usage"] == {"prompt_tokens": 10}

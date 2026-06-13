from datetime import datetime, timezone

from events import (
    EVENT_CANDIDATE_STAGE,
    STANDARDIZED_EVENT_STAGE,
    EventStage,
    EventStageRegistry,
    EventTriggerPipeline,
    PipelineStage,
    RawSignal,
    StandardizedEvent,
)
from events.source import CLITextSignalSource
from events.trigger_pipeline import CliTextToStandardizedEventStage


FIXED_TIME = datetime(2026, 6, 13, 9, 15, tzinfo=timezone.utc)


def test_cli_text_source_creates_raw_signal_without_runtime_side_effects():
    source = CLITextSignalSource()

    signal = source.create_signal(
        text="Ella, I am heading out",
        trace_id="trace-cli-001",
        timestamp=FIXED_TIME,
    )

    assert signal == RawSignal(
        trace_id="trace-cli-001",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella, I am heading out"},
        signal_type="cli_text",
    )


def test_stage_registry_can_add_and_remove_stage_keys():
    registry = EventStageRegistry()
    custom_stage = EventStage("normalized_cli_text")

    registry.register(custom_stage)
    assert registry.get("normalized_cli_text") == custom_stage

    registry.unregister("normalized_cli_text")
    assert registry.get("normalized_cli_text") is None


def test_cli_text_stage_can_be_tested_independently():
    signal = RawSignal(
        trace_id="trace-cli-002",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella, I am heading out"},
        signal_type="cli_text",
    )

    event = CliTextToStandardizedEventStage().process(signal)

    assert event == StandardizedEvent(
        trace_id="trace-cli-002",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella, I am heading out"},
        event_type="USER_UTTERANCE",
        confidence=1.0,
        priority=0.9,
        metadata={"trigger_kind": "user_initiated"},
    )


def test_pipeline_runs_configured_stages_in_order():
    class MarkCandidateStage(PipelineStage):
        stage = EVENT_CANDIDATE_STAGE

        def process(self, item):
            return {
                "trace_id": item.trace_id,
                "source": item.source,
                "timestamp": item.timestamp,
                "payload": item.payload,
                "candidate_seen": True,
            }

    class StandardizeMarkedCandidateStage(PipelineStage):
        stage = STANDARDIZED_EVENT_STAGE

        def process(self, item):
            return StandardizedEvent(
                trace_id=item["trace_id"],
                source=item["source"],
                timestamp=item["timestamp"],
                payload=item["payload"] | {"candidate_seen": item["candidate_seen"]},
                event_type="USER_UTTERANCE",
            )

    signal = RawSignal(
        trace_id="trace-cli-003",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella, I am heading out"},
        signal_type="cli_text",
    )
    pipeline = EventTriggerPipeline(
        stages=[
            MarkCandidateStage(),
            StandardizeMarkedCandidateStage(),
        ]
    )

    event = pipeline.run(signal)

    assert isinstance(event, StandardizedEvent)
    assert event.payload == {
        "text": "Ella, I am heading out",
        "candidate_seen": True,
    }


def test_mock_cli_text_input_can_convert_to_standardized_event():
    signal = CLITextSignalSource().create_signal(
        text="Ella, I am heading out",
        trace_id="trace-cli-004",
        timestamp=FIXED_TIME,
    )
    pipeline = EventTriggerPipeline(stages=[CliTextToStandardizedEventStage()])

    event = pipeline.run(signal)

    assert event.event_type == "USER_UTTERANCE"
    assert event.stage == STANDARDIZED_EVENT_STAGE
    assert event.to_dict()["payload"] == {"text": "Ella, I am heading out"}

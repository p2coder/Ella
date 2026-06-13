from datetime import datetime, timezone

from events import (
    DEFAULT_EVENT_STAGES,
    EVENT_CANDIDATE_STAGE,
    OBSERVATION_STAGE,
    STANDARDIZED_EVENT_STAGE,
    Event,
    EventCandidate,
    EventStage,
    Observation,
    RawSignal,
    StandardizedEvent,
)


FIXED_TIME = datetime(2026, 6, 13, 8, 30, tzinfo=timezone.utc)


def test_raw_signal_constructs_and_serializes_payload_context():
    signal = RawSignal(
        trace_id="trace-001",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella, I am heading out"},
    )

    assert signal.trace_id == "trace-001"
    assert signal.source == "cli_input"
    assert signal.payload["text"] == "Ella, I am heading out"
    assert signal.to_dict() == {
        "trace_id": "trace-001",
        "source": "cli_input",
        "timestamp": "2026-06-13T08:30:00+00:00",
        "payload": {"text": "Ella, I am heading out"},
        "signal_type": "raw_signal",
        "metadata": {},
    }


def test_observation_and_candidate_express_configurable_event_stages():
    custom_stage = EventStage("ambient_observation", "Ambient state update")
    observation = Observation(
        trace_id="trace-002",
        source="multimodal_model",
        timestamp=FIXED_TIME,
        payload={"summary": "environment changed"},
        stage=custom_stage,
        confidence=0.72,
    )
    candidate = EventCandidate(
        trace_id="trace-002",
        source="multimodal_model",
        timestamp=FIXED_TIME,
        payload={"summary": "environment changed"},
        event_type="ENVIRONMENT_CHANGE_CANDIDATE",
        confidence=0.72,
    )

    assert observation.stage == custom_stage
    assert candidate.stage == EVENT_CANDIDATE_STAGE
    assert observation.to_dict()["stage"] == "ambient_observation"
    assert candidate.to_dict()["stage"] == "event_candidate"


def test_standardized_event_has_routing_relevant_contract_fields_only():
    event = StandardizedEvent(
        trace_id="trace-003",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella, I am heading out"},
        event_type="USER_UTTERANCE",
        confidence=1.0,
        priority=0.9,
        target_session_id="task-123",
        caused_by_task_id="task-123",
    )

    assert event.stage == STANDARDIZED_EVENT_STAGE
    assert event.to_dict() == {
        "trace_id": "trace-003",
        "source": "cli_input",
        "timestamp": "2026-06-13T08:30:00+00:00",
        "payload": {"text": "Ella, I am heading out"},
        "event_type": "USER_UTTERANCE",
        "stage": "standardized_event",
        "confidence": 1.0,
        "priority": 0.9,
        "target_session_id": "task-123",
        "caused_by_task_id": "task-123",
        "metadata": {},
    }
    assert Event is StandardizedEvent


def test_raw_media_signal_keeps_media_reference_without_semantic_interpretation():
    signal = RawSignal(
        trace_id="trace-004",
        source="camera_frame",
        timestamp=FIXED_TIME,
        payload={
            "media_ref": "frame://local/0001",
            "mime_type": "image/jpeg",
        },
    )

    assert signal.to_dict()["payload"] == {
        "media_ref": "frame://local/0001",
        "mime_type": "image/jpeg",
    }


def test_default_event_stages_are_replaceable_registry_keys():
    assert DEFAULT_EVENT_STAGES == (
        OBSERVATION_STAGE,
        EVENT_CANDIDATE_STAGE,
        STANDARDIZED_EVENT_STAGE,
    )

    custom_stages = DEFAULT_EVENT_STAGES + (EventStage("user_defined_stage"),)

    assert [stage.name for stage in custom_stages] == [
        "observation",
        "event_candidate",
        "standardized_event",
        "user_defined_stage",
    ]

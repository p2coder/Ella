from pathlib import Path

from runtime.trace import TraceRecorder


def test_trace_is_append_only_task_isolated_and_deterministic(tmp_path):
    path = tmp_path / "events.jsonl"
    recorder = TraceRecorder(path)
    recorder.record(
        task_id="task-a", trace_id="trace-a", boundary="task_graph.plan",
        event_type="plan_written", payload={"version": "1"},
    )
    recorder.record(
        task_id="task-a", trace_id="trace-a", boundary="tool_attempt.camera",
        event_type="failed", payload={"code": "busy"},
    )
    recorder.record(
        task_id="task-b", trace_id="trace-b", boundary="task",
        event_type="created", payload={},
    )
    snapshot = recorder.snapshot("task-a")
    assert tuple(event.sequence for event in snapshot.events) == (1, 2)
    assert len(snapshot.task_graph.events) == 1
    assert len(snapshot.tool_attempts.events) == 1
    assert recorder.snapshot("task-b").events[0].sequence == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_trace_redacts_secrets_paths_and_raw_media():
    recorder = TraceRecorder()
    recorder.record(
        task_id="task", trace_id="trace", boundary="tool_attempt.screen",
        event_type="completed",
        payload={
            "api_key": "secret-value",
            "authorization": "Bearer secret",
            "path": "/Users/example/private/image.png",
            "raw_media": b"image bytes",
        },
    )
    payload = recorder.snapshot("task").events[0].payload
    assert payload["api_key"] == "[REDACTED]"
    assert payload["authorization"] == "[REDACTED]"
    assert "private" not in payload["path"]
    assert payload["raw_media"] == "[RAW_MEDIA_REDACTED]"


def test_timing_can_attach_to_matching_boundary_without_becoming_state():
    recorder = TraceRecorder()
    recorder.record(
        task_id="task", trace_id="trace", boundary="reasoning.llm",
        event_type="completed", payload={"timing": {"duration_ms": 12.5}},
    )
    snapshot = recorder.snapshot("task")
    assert snapshot.reasoning.events[0].payload["timing"]["duration_ms"] == 12.5
    assert not hasattr(recorder, "transition_to")


def test_subagent_has_no_fixed_trace_file_overwrite():
    source = Path("sessions/subagent.py").read_text(encoding="utf-8")
    assert 'open("trace/trace.json", "w"' not in source

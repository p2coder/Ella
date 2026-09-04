from pathlib import Path

from runtime.trace import TraceRecorder


def test_trace_is_append_only_task_isolated_and_deterministic(tmp_path):
    path = tmp_path / "events.jsonl"
    recorder = TraceRecorder(path)
    recorder.record(
        task_id="task-a", boundary="reasoning.plan",
        event_type="workflow_completed", payload={"version": "1"},
    )
    recorder.record(
        task_id="task-a", boundary="tool_attempt.camera",
        event_type="failed", payload={"code": "busy"},
    )
    recorder.record(
        task_id="task-b", boundary="task",
        event_type="created", payload={},
    )
    snapshot = recorder.snapshot("task-a")
    assert tuple(event.sequence for event in snapshot.events) == (1, 2)
    assert snapshot.events[0].boundary == "reasoning.plan"
    assert snapshot.events[1].boundary == "tool_attempt.camera"
    assert recorder.snapshot("task-b").events[0].sequence == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_trace_redacts_secrets_paths_and_raw_media():
    recorder = TraceRecorder()
    recorder.record(
        task_id="task", boundary="tool_attempt.screen",
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
        task_id="task", boundary="reasoning.llm",
        event_type="completed", payload={"timing": {"duration_ms": 12.5}},
    )
    snapshot = recorder.snapshot("task")
    assert snapshot.events[0].payload["timing"]["duration_ms"] == 12.5
    assert not hasattr(recorder, "transition_to")


def test_subagent_has_no_fixed_trace_file_overwrite():
    source = Path("agent/subagent.py").read_text(encoding="utf-8")
    assert 'open("trace/trace.json", "w"' not in source


def test_directory_mode_persists_one_append_only_file_per_task(tmp_path):
    recorder = TraceRecorder.for_directory(tmp_path)
    recorder.record(
        task_id="task-a", boundary="task",
        event_type="created", payload={},
    )
    recorder.record(
        task_id="task-b", boundary="task",
        event_type="created", payload={},
    )
    recorder.record(
        task_id="task-a", boundary="step",
        event_type="started", payload={},
    )

    task_a_lines = (tmp_path / "task-a.jsonl").read_text(encoding="utf-8").splitlines()
    task_b_lines = (tmp_path / "task-b.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(task_a_lines) == 2
    assert len(task_b_lines) == 1


def test_directory_mode_continues_sequence_after_recorder_restart(tmp_path):
    first = TraceRecorder.for_directory(tmp_path)
    first.record(
        task_id="task", boundary="task",
        event_type="created", payload={},
    )
    second = TraceRecorder.for_directory(tmp_path)
    event = second.record(
        task_id="task", boundary="task",
        event_type="restored", payload={},
    )
    assert event.sequence == 2

import ast
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace

import app_runtime
from memory import MemoryWriteResult
from tasks.completion import TaskCompletionPackage
from tasks.output import UserVisibleAgentOutput


class _DisplayTaskResult:
    def __init__(self):
        self.completion = TaskCompletionPackage(
            context=None,
            summary="done",
            user_visible_output=UserVisibleAgentOutput(
                process={
                    "task_goal": "Answer.",
                    "execution_decision_prompt_text": "EXECUTION",
                    "final_response_prompt_text": "FINAL",
                },
                final_response="Done.",
            ),
            tool_results=(),
        )
        self.memory_result = MemoryWriteResult(
            action="recorded",
            memory_path=Path("memory.md"),
        )
        self.handle = SimpleNamespace(task_id="task-1")
        self.task = SimpleNamespace(
            state=SimpleNamespace(value="completed"),
            active_step_ids=(),
            paused_from_state=None,
            terminal_outcome=None,
            delivery=None,
            goal_state=SimpleNamespace(value="achieved"),
            terminal_execution_state=SimpleNamespace(value="completed"),
            task_local_state={
                "first_decision_prompt_text": "FIRST",
                "verification_prompt_text": "VERIFY",
            },
        )
        self.timing = None


def test_formal_app_runtime_uses_neutral_event_context():
    source = inspect.getsource(app_runtime.AppRuntime.create_default)

    assert "before leaving" not in source
    assert "short, practical reminders" not in source
    assert "user_preference_summary=" not in source
    assert "environment_summary=" not in source


def test_formal_app_runtime_is_not_a_demo_runtime_wrapper():
    source = inspect.getsource(app_runtime)

    assert "DemoRuntime" not in source
    assert "demo.cli_demo" not in source
    assert "run_text_with_display" in source


def test_formal_app_runtime_injects_llm_into_subagent_skill_selection():
    source = inspect.getsource(app_runtime.AppRuntime.create_default)
    tree = ast.parse(textwrap.dedent(source))
    subagent_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "SubAgent"
    ]

    assert len(subagent_calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in subagent_calls[0].keywords}
    assert "llm_provider" in keywords
    assert isinstance(keywords["llm_provider"], ast.Name)
    assert keywords["llm_provider"].id == "llm_provider"


def test_formal_app_runtime_snapshot_preserves_all_generated_prompts():
    snapshot = app_runtime._build_display_snapshot(
        "hello",
        _DisplayTaskResult(),
    )

    assert snapshot.first_decision_prompt_text == "FIRST"
    assert snapshot.execution_decision_prompt_text == "EXECUTION"
    assert snapshot.verification_prompt_text == "VERIFY"
    assert snapshot.final_response_prompt_text == "FINAL"
    assert snapshot.goal_state == "achieved"

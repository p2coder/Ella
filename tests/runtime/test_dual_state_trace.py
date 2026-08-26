from runtime.task_runtime import TaskRuntime
from runtime.trace import TraceRecorder
from skill.manager import SkillManager
from agent.subagent import SubAgent
from agent.verification import (
    VerificationAction,
    VerificationAgent,
    VerificationVerdict,
)
from runtime.executor import CapabilityExecutor
from tasks.factory import TaskFactory
from tasks.task import TaskGoalState
from tools.manager import ToolManager

from tests.runtime.test_first_decision_flow import FirstDecisionProvider, _event


class EmptyCriteriaProvider:
    provider_name = "empty-criteria-test"
    model_name = "test-model"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        from providers.base import ProviderResult

        return ProviderResult(
            self.provider_name,
            self.model_name,
            trace_id,
            {
                "intent": {
                    "goal": "Acknowledge the greeting.",
                    "constraints": [],
                    "deliverables": ["A direct greeting."],
                    "minimum_acceptance_criteria": [],
                },
                "action": {
                    "action": "SUBMIT_RESULT",
                    "decision_reason": "The greeting can be answered directly.",
                    "completion_summary": "The greeting was acknowledged.",
                    "final_response_draft": "你好，很高兴见到你。",
                    "evidence_refs": [],
                },
            },
        )


class VerificationMustNotRun:
    def decide(self, task, definitions=()):
        raise AssertionError("empty acceptance criteria must not call verification LLM")


class DraftRejectingVerifier:
    def decide(self, task, definitions=()):
        return VerificationAction(
            "VERIFICATION_VERDICT",
            verdict=VerificationVerdict(
                goal_state=TaskGoalState.NOT_ACHIEVED,
                criterion_results=("The draft is unsupported.",),
                deliverable_results=(),
                draft_quality_issues=("The draft claims an unverified result.",),
                recoverable=False,
                feedback_for_execution="Replace the claim with an honest result.",
                public_summary="The draft cannot be delivered.",
            ),
        )


class FailingVerificationAgent:
    def decide(self, task, definitions=()):
        raise ValueError("invalid verification payload")


def test_trace_separates_first_decision_and_verification(tmp_path) -> None:
    recorder = TraceRecorder.for_directory(tmp_path)
    tool_manager = ToolManager()
    subagent = SubAgent(
        skill_manager=SkillManager(),
        tool_directory=tool_manager,
        llm_provider=FirstDecisionProvider(),
    )
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            task_id_factory=lambda: "task-trace",
            tool_manager=tool_manager,
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            subagent=subagent,
            skill_manager=SkillManager(),
            tool_manager=tool_manager,
        ),
        verification_agent=VerificationAgent(),
        trace_recorder=recorder,
    )
    handle = runtime.create_task(_event())

    runtime.step(handle.task_id)
    result = runtime.step(handle.task_id)

    assert result.task.intent is not None
    snapshot = recorder.snapshot(handle.task_id)
    assert snapshot is not None
    markers = {
        (event.boundary, event.event_type) for event in snapshot.events
    }
    assert ("reasoning.first_decision", "started") in markers
    assert ("reasoning.first_decision", "intent_committed") in markers
    assert ("reasoning.first_decision", "completed") in markers
    assert ("reasoning.submit_result", "candidate_persisted") in markers
    assert ("reasoning.verification", "started") in markers
    assert ("reasoning.verification", "verdict") in markers
    assert ("task", "completed") in markers
    assert ("checkpoint", "persisted") in markers


def test_verification_failure_does_not_expose_unverified_draft(tmp_path) -> None:
    recorder = TraceRecorder.for_directory(tmp_path)
    tool_manager = ToolManager()
    subagent = SubAgent(
        skill_manager=SkillManager(),
        tool_directory=tool_manager,
        llm_provider=FirstDecisionProvider(),
    )
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            task_id_factory=lambda: "task-invalid-verification",
            tool_manager=tool_manager,
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            subagent=subagent,
            skill_manager=SkillManager(),
            tool_manager=tool_manager,
        ),
        verification_agent=FailingVerificationAgent(),
        trace_recorder=recorder,
    )
    handle = runtime.create_task(_event())

    runtime.step(handle.task_id)
    result = runtime.step(handle.task_id)

    assert result.task.state.value == "failed"
    assert result.task.completion is None
    assert result.completion is None
    assert result.task.failure["code"] == "verification_failed"


def test_empty_acceptance_criteria_delivers_submitted_draft_without_llm_verification(
    tmp_path,
) -> None:
    recorder = TraceRecorder.for_directory(tmp_path)
    tool_manager = ToolManager()
    subagent = SubAgent(
        skill_manager=SkillManager(),
        tool_directory=tool_manager,
        llm_provider=EmptyCriteriaProvider(),
    )
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            task_id_factory=lambda: "task-empty-criteria",
            tool_manager=tool_manager,
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            subagent=subagent,
            skill_manager=SkillManager(),
            tool_manager=tool_manager,
        ),
        verification_agent=VerificationMustNotRun(),
        trace_recorder=recorder,
    )
    handle = runtime.create_task(_event())

    runtime.step(handle.task_id)
    result = runtime.step(handle.task_id)

    assert result.stop_reason == "completed"
    assert result.completion is not None
    assert result.completion.summary == "The greeting was acknowledged."
    assert result.completion.user_visible_output.final_response == (
        "你好，很高兴见到你。"
    )
    markers = {
        (event.boundary, event.event_type)
        for event in recorder.snapshot(handle.task_id).events
    }
    assert ("reasoning.submit_result", "candidate_persisted") in markers
    assert ("reasoning.final_response", "started") not in markers


def test_untrusted_draft_is_not_delivered_after_verification_budget_exhausts(
    tmp_path,
) -> None:
    recorder = TraceRecorder.for_directory(tmp_path)
    tool_manager = ToolManager()
    subagent = SubAgent(
        skill_manager=SkillManager(),
        tool_directory=tool_manager,
        llm_provider=FirstDecisionProvider(),
    )
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            task_id_factory=lambda: "task-rejected-draft",
            tool_manager=tool_manager,
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            subagent=subagent,
            skill_manager=SkillManager(),
            tool_manager=tool_manager,
        ),
        verification_agent=DraftRejectingVerifier(),
        max_verification_rounds=1,
        trace_recorder=recorder,
    )
    handle = runtime.create_task(_event())

    runtime.step(handle.task_id)
    result = runtime.step(handle.task_id)

    assert result.task.state.value == "failed"
    assert result.task.goal_state is TaskGoalState.NOT_ACHIEVED
    assert result.completion is None
    assert result.task.failure["code"] == "unverified_response_draft"

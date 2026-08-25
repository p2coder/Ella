import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Mapping

from prompts.engine import PromptEngine, PromptType
from runtime.timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder
from tasks.task import Task, TaskGoalState


class VerificationDecisionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerificationVerdict:
    goal_state: TaskGoalState
    criterion_results: tuple[str, ...]
    deliverable_results: tuple[str, ...]
    draft_quality_issues: tuple[str, ...]
    recoverable: bool
    feedback_for_execution: str
    public_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_state": self.goal_state.value,
            "criterion_results": self.criterion_results,
            "deliverable_results": self.deliverable_results,
            "draft_quality_issues": self.draft_quality_issues,
            "recoverable": self.recoverable,
            "feedback_for_execution": self.feedback_for_execution,
            "public_summary": self.public_summary,
        }


@dataclass(frozen=True, slots=True)
class VerificationAgent:
    prompt_engine: PromptEngine = field(default_factory=PromptEngine)
    llm_provider: Any | None = None
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder = field(
        default_factory=NoOpRuntimeTimingRecorder
    )

    def verify(self, task: Task) -> VerificationVerdict:
        if task.intent is None:
            raise VerificationDecisionError("verification requires TaskIntent")
        draft = str(task.task_local_state.get("draft_final_response", "")).strip()
        context = {
            "user_prompt": (
                "" if task.source_event is None else task.source_event.payload.get("text", "")
            ),
            "workspace": {
                "task_id": task.task_id,
                "intent": task.intent.to_dict(),
                "plan": None if task.graph is None else {
                    "version": task.graph.definition.version,
                    "node_runs": task.graph.node_runs,
                },
                "observations": task.tool_trace,
                "failures": tuple(
                    item.to_dict() for item in task.current_step.failures
                ),
                "candidate_result": task.task_local_state.get("completion_summary", ""),
                "draft_final_response": draft,
                "verification_round": int(
                    task.task_local_state.get("verification_round", 1)
                ),
                "verification_results": tuple(
                    task.task_local_state.get("verification_results", ())
                ),
            },
        }
        prompt = self.prompt_engine.build(PromptType.VERIFICATION_DECISION, context)
        task.task_local_state["verification_prompt_text"] = prompt.prompt
        if self.llm_provider is None:
            return self._deterministic_verdict(draft)
        started = perf_counter()
        try:
            result = self.llm_provider.generate(
                prompt.prompt,
                trace_id=task.trace_id,
                metadata={"boundary": "verification_decision"},
            )
        except Exception:
            self._record_timing(task, started, False, None)
            raise
        self._record_timing(task, started, not result.failed, result)
        if result.failed:
            raise VerificationDecisionError("verification provider failed")
        try:
            return self._verdict_from_output(result.output)
        except VerificationDecisionError:
            if bool(getattr(result, "metadata", {}).get("mock")):
                return self._deterministic_verdict(draft)
            raise

    def _record_timing(self, task: Task, started: float, success: bool, result: Any) -> None:
        self.timing_recorder.record_llm_call(
            task.trace_id,
            boundary="verification_decision",
            duration_ms=round((perf_counter() - started) * 1000, 3),
            success=success,
            provider_name=getattr(result or self.llm_provider, "provider_name", None),
            model_name=getattr(result or self.llm_provider, "model_name", None),
        )

    @staticmethod
    def _verdict_from_output(output: Any) -> VerificationVerdict:
        if isinstance(output, Mapping) and isinstance(output.get("text"), str):
            output = output["text"]
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError as error:
                raise VerificationDecisionError("invalid verification JSON") from error
        if not isinstance(output, Mapping):
            raise VerificationDecisionError("verification verdict must be an object")
        if output.get("action", "VERIFICATION_VERDICT") != "VERIFICATION_VERDICT":
            raise VerificationDecisionError("unsupported verification action")
        try:
            return VerificationVerdict(
                goal_state=TaskGoalState(str(output["goal_state"]).lower()),
                criterion_results=tuple(output.get("criterion_results", ())),
                deliverable_results=tuple(output.get("deliverable_results", ())),
                draft_quality_issues=tuple(output.get("draft_quality_issues", ())),
                recoverable=bool(output.get("recoverable", False)),
                feedback_for_execution=str(output.get("feedback_for_execution", "")),
                public_summary=str(output.get("public_summary", "")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise VerificationDecisionError(f"invalid verification verdict: {error}") from error

    @staticmethod
    def _deterministic_verdict(draft: str) -> VerificationVerdict:
        state = TaskGoalState.ACHIEVED if draft else TaskGoalState.NOT_ACHIEVED
        return VerificationVerdict(
            goal_state=state,
            criterion_results=(
                "A non-empty user-facing response was generated."
                if draft
                else "No user-facing response was generated."
            ,),
            deliverable_results=(),
            draft_quality_issues=() if draft else ("The response draft is empty.",),
            recoverable=not bool(draft),
            feedback_for_execution=(
                "" if draft else "Generate a concrete user-facing response."
            ),
            public_summary=(
                "The response passed deterministic verification."
                if draft
                else "The response could not be verified."
            ),
        )

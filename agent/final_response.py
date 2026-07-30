from dataclasses import dataclass, field
import re
from time import perf_counter
from typing import Any, Iterable, Mapping

from prompts.engine import PromptEngine, PromptType, redact_prompt_text
from providers.llm import LLMProvider
from runtime.timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder
from tasks.state import ToolFailureObservation
from tools.base import ToolResult


LOCAL_PATH_PATTERN = re.compile(
    r"(?:(?:[A-Za-z]:\\\\)|/)[^\s;,]+"
)


@dataclass(frozen=True, slots=True)
class FinalResponseResult:
    final_response: str
    tool_results_summary: str
    prompt_trace: dict[str, Any]
    provider_error: dict[str, str | None] | None = None


@dataclass(frozen=True, slots=True)
class FinalResponseGenerator:
    prompt_engine: PromptEngine
    llm_provider: LLMProvider
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder = field(
        default_factory=NoOpRuntimeTimingRecorder
    )

    @staticmethod
    def failure_report_text(payload: Mapping[str, Any]) -> str:
        """Render an already-decided failure without another model call."""
        reason = str(payload.get("reason", "任务未能完成"))
        unknown = tuple(payload.get("unknown_side_effects", ()))
        suffix = ""
        if unknown:
            suffix = " 外部操作结果仍未知：" + "；".join(map(str, unknown))
        return f"任务未能完成：{reason}。{suffix}".strip()

    def generate(
        self,
        *,
        trace_id: str | None,
        user_input: str,
        task_goal: str,
        tool_results: Iterable[ToolResult | Mapping[str, Any]],
        task_constraints: Iterable[str] = (),
        completion_criteria: Iterable[str] = (),
        user_preference_summary: str = "",
        environment_summary: str = "",
        memory_context: str = "",
        execution_failures: Iterable[
            ToolFailureObservation | Mapping[str, Any]
        ] = (),
        **_: Any,
    ) -> FinalResponseResult:
        generation_started = perf_counter()
        tool_results_tuple = tuple(tool_results)
        execution_failures_tuple = tuple(execution_failures)
        tool_results_summary = self.summarize_tool_results(tool_results_tuple)
        tool_errors = self._tool_errors(tool_results_tuple)
        execution_failure_summary = self.summarize_execution_failures(
            execution_failures_tuple
        )
        legacy_context = {
            "trace_id": trace_id,
            "user_input": user_input,
            "task_goal": task_goal,
            "task_constraints": tuple(task_constraints),
            "completion_criteria": tuple(completion_criteria),
            "tool_results_summary": tool_results_summary,
            "scene_summary": self._first_payload_text(
                tool_results_tuple,
                ("scene_summary", "summary"),
            ),
            "visible_items": self._visible_items(tool_results_tuple),
            "user_preference_summary": user_preference_summary,
            "environment_summary": environment_summary,
            "memory_context": memory_context,
            "provider_or_tool_errors": tool_errors,
        }
        if execution_failure_summary:
            legacy_context["execution_failure_summary"] = execution_failure_summary
        context = dict(legacy_context)
        if isinstance(self.prompt_engine, PromptEngine):
            context.update(
                {
                    "user_prompt": user_input,
                    "workspace": {
                        "overall_goal": task_goal,
                        "current_goal": task_goal,
                        "completed_steps": self._completed_steps(tool_results_tuple),
                        "current_step_state": {
                            "task_constraints": tuple(task_constraints),
                            "completion_criteria": tuple(completion_criteria),
                            "uncertainty_and_failure_notes": (
                                *tool_errors,
                                *(
                                    (execution_failure_summary,)
                                    if execution_failure_summary
                                    else ()
                                ),
                            ),
                        },
                        "tool_results_summary": tool_results_summary,
                        "scene_summary": self._first_payload_text(
                            tool_results_tuple,
                            ("scene_summary", "summary"),
                        ),
                        "visible_items": self._visible_items(tool_results_tuple),
                        "observations": self._observation_summaries(
                            tool_results_tuple
                        ),
                    },
                },
            )
        prompt_result = self.prompt_engine.build(PromptType.FINAL_RESPONSE, context)

        llm_started = perf_counter()
        try:
            provider_result = self.llm_provider.generate(
                prompt_result.prompt,
                trace_id=trace_id,
                metadata={"boundary": "final_response"},
            )
        except Exception as error:
            self._record_llm_timing(
                trace_id=trace_id,
                started=llm_started,
                success=False,
                provider_name=self.llm_provider.provider_name,
                model_name=self.llm_provider.model_name,
            )
            result = self._fallback_result(
                trace_id=trace_id,
                prompt_result=prompt_result,
                tool_results_summary=tool_results_summary,
                user_input=user_input,
                task_goal=task_goal,
                provider_name=self.llm_provider.provider_name,
                model_name=self.llm_provider.model_name,
                llm_output=None,
                code="provider_exception",
                message=str(error),
                execution_failure_summary=execution_failure_summary,
            )
            self._record_generation_timing(trace_id, generation_started)
            return result

        self._record_llm_timing(
            trace_id=trace_id,
            started=llm_started,
            success=not provider_result.failed,
            provider_name=provider_result.provider_name,
            model_name=provider_result.model_name,
        )

        prompt_trace = {
            "trace_id": trace_id,
            "prompt_type": prompt_result.prompt_type,
            "prompt_name": prompt_result.prompt_name,
            "prompt_text": prompt_result.prompt,
            "provider_name": provider_result.provider_name,
            "model_name": provider_result.model_name,
            "llm_output": provider_result.output,
        }

        if provider_result.failed:
            error = provider_result.error
            result = self._fallback_result(
                trace_id=trace_id,
                prompt_result=prompt_result,
                tool_results_summary=tool_results_summary,
                user_input=user_input,
                task_goal=task_goal,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                llm_output=provider_result.output,
                code=None if error is None else error.code,
                message="provider failed" if error is None else error.message,
                execution_failure_summary=execution_failure_summary,
            )
            self._record_generation_timing(trace_id, generation_started)
            return result

        final_response = self._provider_text(provider_result.output)
        if final_response is None:
            result = self._fallback_result(
                trace_id=trace_id,
                prompt_result=prompt_result,
                tool_results_summary=tool_results_summary,
                user_input=user_input,
                task_goal=task_goal,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
                llm_output=provider_result.output,
                code="invalid_provider_output",
                message="provider output did not include final response text",
                execution_failure_summary=execution_failure_summary,
            )
            self._record_generation_timing(trace_id, generation_started)
            return result

        result = FinalResponseResult(
            final_response=final_response,
            tool_results_summary=tool_results_summary,
            prompt_trace=prompt_trace,
        )
        self._record_generation_timing(trace_id, generation_started)
        return result

    def summarize_tool_results(
        self,
        tool_results: Iterable[ToolResult | Mapping[str, Any]],
    ) -> str:
        summaries = []
        for result in tool_results:
            tool_name, payload = self._tool_name_and_payload(result)
            if not payload:
                summaries.append(f"{tool_name}: no payload")
                continue
            lines = [f"{tool_name}:"]
            for key in sorted(payload):
                value = payload[key]
                if value is None:
                    continue
                lines.append(f"- {key}: {self._format_value(value)}")
            summaries.append("\n".join(lines))
        return "\n\n".join(summaries)

    def summarize_execution_failures(
        self,
        failures: Iterable[ToolFailureObservation | Mapping[str, Any]],
    ) -> str:
        summaries = []
        for failure in failures:
            if isinstance(failure, ToolFailureObservation):
                tool_name = failure.tool_name
                kind = failure.kind.value
                code = failure.code
                message = self._safe_failure_message(failure.message)
                retryable = failure.retryable
            else:
                tool_name = str(failure.get("tool_name", "unknown_tool"))
                raw_kind = failure.get("kind", "tool_execution_failed")
                kind = getattr(raw_kind, "value", str(raw_kind))
                code = str(failure.get("code", kind))
                message = self._safe_failure_message(
                    str(failure.get("message", "tool execution failed"))
                )
                retryable = bool(failure.get("retryable", False))
            summaries.append(
                f"{tool_name}: {kind} ({code}) - {message}; "
                f"retryable={str(retryable).lower()}"
            )
        return "\n".join(summaries)

    @staticmethod
    def _safe_failure_message(message: str) -> str:
        redacted = redact_prompt_text(message)
        return LOCAL_PATH_PATTERN.sub("[REDACTED]", redacted)

    def _fallback_result(
        self,
        *,
        trace_id: str | None,
        prompt_result: Any,
        tool_results_summary: str,
        user_input: str,
        task_goal: str,
        provider_name: str,
        model_name: str,
        llm_output: Any,
        code: str | None,
        message: str,
        execution_failure_summary: str = "",
    ) -> FinalResponseResult:
        details = tool_results_summary or execution_failure_summary
        final_response = self._fallback_text(user_input, details)
        return FinalResponseResult(
            final_response=final_response,
            tool_results_summary=tool_results_summary,
            prompt_trace={
                "trace_id": trace_id,
                "prompt_type": prompt_result.prompt_type,
                "prompt_name": prompt_result.prompt_name,
                "prompt_text": prompt_result.prompt,
                "provider_name": provider_name,
                "model_name": model_name,
                "llm_output": llm_output,
            },
            provider_error={
                "provider_name": provider_name,
                "code": code,
                "message": message,
            },
        )

    @classmethod
    def _fallback_text(cls, user_input: str, details: str) -> str:
        normalized_input = user_input.strip().lower().rstrip("!！。,.，?？")
        if normalized_input in {"你好", "您好", "hello", "hi", "hey"}:
            return "你好！有什么我可以帮你的吗？"
        if details:
            visual_note = ""
            if "visual context is unavailable" in details.lower():
                visual_note = " 视觉上下文当前不可用。"
            return (
                "我已经根据当前可用信息完成了处理："
                f"{cls._compact_summary(details)}。{visual_note}"
            )
        return "抱歉，我暂时无法生成完整回复，请稍后再试。"

    def _provider_text(self, output: Any) -> str | None:
        if isinstance(output, str) and output.strip():
            return output.strip()
        if not isinstance(output, Mapping):
            return None
        for key in ("final_response", "text", "answer", "response"):
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _record_llm_timing(
        self,
        *,
        trace_id: str | None,
        started: float,
        success: bool,
        provider_name: str | None,
        model_name: str | None,
    ) -> None:
        if trace_id is None:
            return
        self.timing_recorder.record_llm_call(
            trace_id,
            boundary="final_response",
            duration_ms=round((perf_counter() - started) * 1000, 3),
            success=success,
            provider_name=provider_name,
            model_name=model_name,
        )

    def _record_generation_timing(
        self,
        trace_id: str | None,
        started: float,
    ) -> None:
        if trace_id is None:
            return
        self.timing_recorder.record_final_response_generation(
            trace_id,
            round((perf_counter() - started) * 1000, 3),
        )

    def _tool_name_and_payload(
        self,
        result: ToolResult | Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any]]:
        if isinstance(result, ToolResult):
            return result.tool_name, result.payload
        tool_name = result.get("tool_name", "unknown_tool")
        payload = result.get("payload", {})
        if not isinstance(tool_name, str):
            tool_name = "unknown_tool"
        if not isinstance(payload, Mapping):
            payload = {}
        return tool_name, payload

    def _first_payload_text(
        self,
        tool_results: Iterable[ToolResult | Mapping[str, Any]],
        keys: tuple[str, ...],
    ) -> str:
        for result in tool_results:
            _, payload = self._tool_name_and_payload(result)
            for key in keys:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def _visible_items(
        self,
        tool_results: Iterable[ToolResult | Mapping[str, Any]],
    ) -> tuple[str, ...]:
        for result in tool_results:
            _, payload = self._tool_name_and_payload(result)
            value = payload.get("visible_items")
            if isinstance(value, str) and value.strip():
                return (value.strip(),)
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                return tuple(str(item) for item in value)
        return ()

    def _tool_errors(
        self,
        tool_results: Iterable[ToolResult | Mapping[str, Any]],
    ) -> tuple[str, ...]:
        errors = []
        for result in tool_results:
            tool_name, payload = self._tool_name_and_payload(result)
            error = payload.get("error")
            available = payload.get("available")
            summary = payload.get("summary") or payload.get("scene_summary")
            if isinstance(error, str) and error.strip():
                errors.append(f"{tool_name}: {error.strip()}")
            elif available is False and isinstance(summary, str) and summary.strip():
                errors.append(f"{tool_name}: {summary.strip()}")
        return tuple(errors)

    def _completed_steps(
        self,
        tool_results: Iterable[ToolResult | Mapping[str, Any]],
    ) -> tuple[str, ...]:
        steps = []
        for result in tool_results:
            tool_name, payload = self._tool_name_and_payload(result)
            status = payload.get("status")
            if status:
                steps.append(f"{tool_name}: {status}")
            else:
                steps.append(tool_name)
        return tuple(steps)

    def _observation_summaries(
        self,
        tool_results: Iterable[ToolResult | Mapping[str, Any]],
    ) -> tuple[dict[str, Any], ...]:
        observations = []
        for result in tool_results:
            tool_name, payload = self._tool_name_and_payload(result)
            observations.append(
                {
                    "tool_name": tool_name,
                    "summary": payload.get("summary")
                    or payload.get("scene_summary")
                    or self._format_value(payload),
                    "status": payload.get("status", "unknown"),
                    "error": payload.get("error"),
                }
            )
        return tuple(observations)

    @staticmethod
    def _compact_summary(text: str) -> str:
        normalized = " ".join(line.strip() for line in text.splitlines() if line.strip())
        if len(normalized) > 240:
            return normalized[:237].rstrip() + "..."
        return normalized

    def _format_value(self, value: Any) -> str:
        if isinstance(value, Mapping):
            return ", ".join(
                f"{key}: {self._format_value(item)}"
                for key, item in sorted(value.items())
            )
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            return ", ".join(str(item) for item in value)
        return str(value)

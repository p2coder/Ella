from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from prompts.engine import PromptEngine, PromptType
from providers.llm import LLMProvider
from tools.base import ToolResult


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
        **_: Any,
    ) -> FinalResponseResult:
        tool_results_tuple = tuple(tool_results)
        tool_results_summary = self.summarize_tool_results(tool_results_tuple)
        context = {
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
            "provider_or_tool_errors": self._tool_errors(tool_results_tuple),
        }
        prompt_result = self.prompt_engine.build(PromptType.FINAL_RESPONSE, context)

        try:
            provider_result = self.llm_provider.generate(
                prompt_result.prompt,
                trace_id=trace_id,
                metadata={"boundary": "final_response"},
            )
        except Exception as error:
            return self._fallback_result(
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
            return self._fallback_result(
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
            )

        final_response = self._provider_text(provider_result.output)
        print(final_response)
        if final_response is None:
            return self._fallback_result(
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
            )

        return FinalResponseResult(
            final_response=final_response,
            tool_results_summary=tool_results_summary,
            prompt_trace=prompt_trace,
        )

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
    ) -> FinalResponseResult:
        details = tool_results_summary or "没有可用的工具结果摘要。"
        visual_note = ""
        if "visual context is unavailable" in details.lower():
            visual_note = " 视觉上下文当前不可用。"
        final_response = (
            f"我已经根据当前信息完成了检查：{details} "
            f"任务目标是：{task_goal}.{visual_note}"
        )
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

    def _format_value(self, value: Any) -> str:
        if isinstance(value, Mapping):
            return ", ".join(
                f"{key}: {self._format_value(item)}"
                for key, item in sorted(value.items())
            )
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            return ", ".join(str(item) for item in value)
        return str(value)

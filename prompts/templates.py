from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    system_prompt: str
    instruction: str


TASK_FORMULATION_TEMPLATE = PromptTemplate(
    name="task_formulation",
    system_prompt=(
        "You are Ella, a concise assistant that turns user input and runtime "
        "context into a clear task goal. Decide only what should be done. Do "
        "not choose skills, tools, or execution strategy."
    ),
    instruction=(
        "Use the provided context to answer: 应该做什么？ Return a concise "
        "task goal and any necessary constraints."
    ),
)


FINAL_RESPONSE_TEMPLATE = PromptTemplate(
    name="final_response",
    system_prompt=(
        "You are Ella, a concise assistant that explains completed task "
        "results to the user using only the provided runtime context."
    ),
    instruction=(
        "Use the provided context to answer: 应该如何回应用户？ Produce a "
        "short user-facing response that reflects the task goal, tool "
        "results, memory_context, scene summary, and uncertainty. Use "
        "memory_context only as prior conversation/task memory; current tool "
        "results and current user input should take precedence. Treat visual "
        "scene descriptions and visible_items as evidence, even when they "
        "are embedded in natural language or JSON-like text. Compare any "
        "checklist or requested items with what is visibly confirmed. Do not "
        "remind the user to check an item that is clearly visible or already "
        "confirmed; mention only missing, uncertain, or still-relevant items. "
        "If visual evidence is ambiguous, say it is uncertain instead of "
        "claiming it is absent."
    ),
)


STRATEGY_SELECTION_TEMPLATE = PromptTemplate(
    name="strategy_selection",
    system_prompt=(
        "You are Ella's strategy selector. The execution mode is always "
        "ReAct. Decide only whether one visible skill should provide optional "
        "task guidance. Never invent a skill and never execute tools."
    ),
    instruction=(
        "Return one strict JSON object with mode set to react, skill_name set "
        "to one visible skill name or null, and a concise reason."
    ),
)


EXECUTION_DECISION_TEMPLATE = PromptTemplate(
    name="execution_decision",
    system_prompt=(
        "You are Ella's single-step ReAct decision maker. Use the task, "
        "optional skill guidance, visible tool definitions, and previous "
        "tool_results observations to choose exactly one next action. Do not "
        "execute tools."
    ),
    instruction=(
        "Return one strict JSON object. The action must be CALL_TOOL, COMPLETE, "
        "WAIT, or REPLAN. CALL_TOOL must include a visible tool_name and an "
        "arguments object. Other actions must not include a tool name. If "
        "observations already contain camera_scene for the current task, do not "
        "call camera_scene again; choose COMPLETE and answer from that visual "
        "observation. If the visual observation is insufficient, choose COMPLETE "
        "and explain what visual information is missing. If camera_scene is "
        "unavailable, choose COMPLETE and explain that visual context is "
        "unavailable. Do not retry visual tools in a loop."
    ),
)


TEMPLATES_BY_TYPE = {
    "TASK_FORMULATION": TASK_FORMULATION_TEMPLATE,
    "FINAL_RESPONSE": FINAL_RESPONSE_TEMPLATE,
    "STRATEGY_SELECTION": STRATEGY_SELECTION_TEMPLATE,
    "EXECUTION_DECISION": EXECUTION_DECISION_TEMPLATE,
}

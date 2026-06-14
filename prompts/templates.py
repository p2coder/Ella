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
        "short user-facing response that reflects task goal, tool results, "
        "scene summary, and any uncertainty."
    ),
)


TEMPLATES_BY_TYPE = {
    "TASK_FORMULATION": TASK_FORMULATION_TEMPLATE,
    "FINAL_RESPONSE": FINAL_RESPONSE_TEMPLATE,
}

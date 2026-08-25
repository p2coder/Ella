from dataclasses import dataclass

from agent.context import AgentExecutionContext
from runtime.interactions import InteractionBroker
from .base import CapabilityKind, ToolDefinition, ToolResult


@dataclass(frozen=True, slots=True)
class AskUserQuestionTool:
    broker: InteractionBroker
    user_id: str = "local-user"
    max_questions: int = 1
    name: str = "ask_user_question"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    def __post_init__(self) -> None:
        if self.max_questions < 1:
            raise ValueError("max_questions must be positive")

    @property
    def definition(self) -> ToolDefinition:
        question_schema = {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["question"],
            "additionalProperties": False,
        }
        return ToolDefinition(
            name=self.name,
            description=(
                "Ask the user for information that only the user can provide. "
                "Use only when current observations and visible capabilities "
                "cannot supply the missing information."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": question_schema,
                    }
                },
                "required": ["questions"],
                "additionalProperties": False,
            },
            input_examples=({"questions": [{"question": "Who should I contact?"}]},),
            output_schema={
                "type": "object",
                "properties": {
                    "answers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_id": {"type": "string"},
                                "task_id": {"type": "string"},
                                "user_id": {"type": "string"},
                                "answer": {"type": "string"},
                                "metadata": {"type": "object"},
                            },
                            "required": [
                                "question_id",
                                "task_id",
                                "user_id",
                                "answer",
                                "metadata",
                            ],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["answers"],
                "additionalProperties": False,
            },
            capability_kind=CapabilityKind.INTERACTION,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict | None = None,
    ) -> ToolResult:
        questions = tuple((arguments or {}).get("questions", ()))
        if not questions or len(questions) > self.max_questions:
            raise ValueError(
                f"questions must contain between 1 and {self.max_questions} items"
            )
        answers = tuple(
            self.broker.ask(
                task_id=context.task_id,
                user_id=self.user_id,
                question=str(item["question"]),
                metadata=dict(item.get("metadata", {})),
            ).to_dict()
            for item in questions
        )
        return ToolResult(
            self.name,
            context.task_id,
            context.trace_id,
            {"answers": answers},
        )

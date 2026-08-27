from dataclasses import dataclass

from agent.context import AgentExecutionContext
from runtime.interactions import InteractionBroker, UserQuestionOption
from .base import CapabilityKind, ToolDefinition, ToolResult


@dataclass(frozen=True, slots=True)
class AskUserQuestionTool:
    broker: InteractionBroker
    user_id: str = "local-user"
    max_questions: int = 3
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
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "recommended": {"type": "boolean"},
                        },
                        "required": ["text", "recommended"],
                        "additionalProperties": False,
                    },
                },
                "metadata": {"type": "object"},
            },
            "required": ["question", "options"],
            "additionalProperties": False,
        }
        return ToolDefinition(
            name=self.name,
            description=(
                "Purpose: Ask the user for information that only the user can "
                "provide. Use when: A decision cannot proceed because required "
                "information is absent from the request, observations, and visible "
                "capabilities. Do not use when: A visible capability can reasonably "
                "obtain the information or the task can be concluded honestly "
                "without it. Execution behavior: Submit the bounded questions and "
                "wait for the matching user answers before reasoning continues. "
                "For every question, provide 1 to 3 concise answer options and "
                "mark exactly one best option with recommended=true. The user "
                "may choose an option or provide a custom answer."
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
            input_examples=(
                {
                    "questions": [
                        {
                            "question": "Who should I contact?",
                            "options": [
                                {"text": "Ella", "recommended": True},
                                {"text": "My teammate", "recommended": False},
                            ],
                        }
                    ]
                },
            ),
            output_schema={
                "type": "object",
                "properties": {
                    "answers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_id": {"type": "string"},
                                "question": {"type": "string"},
                                "task_id": {"type": "string"},
                                "user_id": {"type": "string"},
                                "answer": {"type": "string"},
                                "metadata": {"type": "object"},
                            },
                            "required": [
                                "question_id",
                                "question",
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
        normalized_questions = tuple(
            self._normalize_question(item) for item in questions
        )
        user_answers = self.broker.ask_many(
            task_id=context.task_id,
            user_id=self.user_id,
            questions=normalized_questions,
        )
        answers = tuple(
            {
                **answer.to_dict(),
                "question": normalized_questions[index][0],
            }
            for index, answer in enumerate(user_answers)
        )
        return ToolResult(
            self.name,
            context.task_id,
            context.trace_id,
            {"answers": answers},
        )

    @staticmethod
    def _normalize_question(item: dict) -> tuple[
        str, tuple[UserQuestionOption, ...], dict
    ]:
        question = str(item.get("question", "")).strip()
        raw_options = tuple(item.get("options", ()))
        if not question:
            raise ValueError("question must be non-empty")
        if not 1 <= len(raw_options) <= 3:
            raise ValueError("each question must contain between 1 and 3 options")
        options = tuple(
            UserQuestionOption(
                text=str(option.get("text", "")).strip(),
                recommended=option.get("recommended") is True,
            )
            for option in raw_options
        )
        if any(not option.text for option in options):
            raise ValueError("option text must be non-empty")
        if len({option.text for option in options}) != len(options):
            raise ValueError("option text must be unique within one question")
        if sum(option.recommended for option in options) != 1:
            raise ValueError("each question must have exactly one recommended option")
        return question, options, dict(item.get("metadata", {}))

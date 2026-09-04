from __future__ import annotations

from dataclasses import dataclass
from threading import Condition
from typing import Any, Callable
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class UserQuestionOption:
    text: str
    recommended: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "recommended": self.recommended}


@dataclass(frozen=True, slots=True)
class UserQuestion:
    question_id: str
    task_id: str
    user_id: str
    question: str
    options: tuple[UserQuestionOption, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "question": self.question,
            "options": tuple(option.to_dict() for option in self.options),
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class UserAnswer:
    question_id: str
    task_id: str
    user_id: str
    answer: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "answer": self.answer,
            "metadata": self.metadata,
        }


class InteractionInterrupted(RuntimeError):
    pass


class InteractionBroker:
    """Correlate blocking interaction calls with their first valid answer."""

    def __init__(
        self,
        on_question: Callable[[UserQuestion], None] | None = None,
    ) -> None:
        self._condition = Condition()
        self._questions: dict[str, UserQuestion] = {}
        self._answers: dict[str, UserAnswer] = {}
        self._interrupted_tasks: set[str] = set()
        self._on_question = on_question

    def ask(
        self,
        *,
        task_id: str,
        user_id: str,
        question: str,
        options: tuple[UserQuestionOption, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> UserAnswer:
        return self.ask_many(
            task_id=task_id,
            user_id=user_id,
            questions=((question, options, dict(metadata or {})),),
        )[0]

    def ask_many(
        self,
        *,
        task_id: str,
        user_id: str,
        questions: tuple[
            tuple[str, tuple[UserQuestionOption, ...], dict[str, Any]], ...
        ],
    ) -> tuple[UserAnswer, ...]:
        if not questions:
            raise ValueError("questions must be non-empty")
        items = tuple(
            UserQuestion(
                question_id=f"question-{uuid4().hex}",
                task_id=task_id,
                user_id=user_id,
                question=question.strip(),
                options=tuple(options),
                metadata=dict(metadata),
            )
            for question, options, metadata in questions
        )
        if any(not item.question for item in items):
            raise ValueError("question must be non-empty")
        with self._condition:
            for item in items:
                self._questions[item.question_id] = item
        if self._on_question is not None:
            for item in items:
                self._on_question(item)
        with self._condition:
            while any(item.question_id not in self._answers for item in items):
                if task_id in self._interrupted_tasks:
                    raise InteractionInterrupted(
                        f"interaction interrupted for task {task_id}"
                    )
                self._condition.wait()
            return tuple(self._answers[item.question_id] for item in items)

    def answer(self, answer: UserAnswer) -> bool:
        if not answer.answer.strip():
            return False
        with self._condition:
            question = self._questions.get(answer.question_id)
            if question is None:
                return False
            if (
                question.task_id != answer.task_id
                or question.user_id != answer.user_id
                or answer.question_id in self._answers
            ):
                return False
            self._answers[answer.question_id] = answer
            self._condition.notify_all()
            return True

    def pending_for_task(self, task_id: str) -> tuple[UserQuestion, ...]:
        with self._condition:
            return tuple(
                item
                for question_id, item in self._questions.items()
                if item.task_id == task_id and question_id not in self._answers
            )

    def interrupt_task(self, task_id: str) -> None:
        with self._condition:
            self._interrupted_tasks.add(task_id)
            self._condition.notify_all()

    def reset_task(self, task_id: str) -> None:
        with self._condition:
            self._interrupted_tasks.discard(task_id)

    def set_question_handler(
        self,
        handler: Callable[[UserQuestion], None] | None,
    ) -> None:
        with self._condition:
            self._on_question = handler

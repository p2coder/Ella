from __future__ import annotations

from dataclasses import dataclass
from threading import Condition
from typing import Any, Callable
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class UserQuestion:
    question_id: str
    task_id: str
    user_id: str
    question: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "question": self.question,
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


class InteractionCancelled(RuntimeError):
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
        self._cancelled_tasks: set[str] = set()
        self._on_question = on_question

    def ask(
        self,
        *,
        task_id: str,
        user_id: str,
        question: str,
        metadata: dict[str, Any] | None = None,
    ) -> UserAnswer:
        if not question.strip():
            raise ValueError("question must be non-empty")
        item = UserQuestion(
            question_id=f"question-{uuid4().hex}",
            task_id=task_id,
            user_id=user_id,
            question=question.strip(),
            metadata=dict(metadata or {}),
        )
        with self._condition:
            self._questions[item.question_id] = item
        if self._on_question is not None:
            self._on_question(item)
        with self._condition:
            while item.question_id not in self._answers:
                if task_id in self._cancelled_tasks:
                    raise InteractionCancelled(
                        f"interaction cancelled for task {task_id}"
                    )
                self._condition.wait()
            return self._answers[item.question_id]

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

    def cancel_task(self, task_id: str) -> None:
        with self._condition:
            self._cancelled_tasks.add(task_id)
            self._condition.notify_all()

    def reset_task(self, task_id: str) -> None:
        with self._condition:
            self._cancelled_tasks.discard(task_id)

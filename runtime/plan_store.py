from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any


class PlanStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    goal: str
    completion_criteria: tuple[str, ...]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanRecord:
    task_id: str
    version_id: str
    steps: tuple[PlanStep, ...]
    parent_version_id: str | None
    content_digest: str
    created_from_decision_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "version_id": self.version_id,
            "parent_version_id": self.parent_version_id,
            "content_digest": self.content_digest,
            "created_from_decision_id": self.created_from_decision_id,
            "steps": [
                {
                    "step_id": step.step_id,
                    "goal": step.goal,
                    "completion_criteria": list(step.completion_criteria),
                    "depends_on": list(step.depends_on),
                }
                for step in self.steps
            ],
        }


class PlanStore:
    """Immutable Plan versions backed by one bare Git repository."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._ensure_repository()

    def write(
        self,
        *,
        task_id: str,
        steps: tuple[PlanStep, ...],
        created_from_decision_id: str | None = None,
    ) -> PlanRecord:
        _validate_identity(task_id)
        _validate_steps(steps)
        parent = self.active_version(task_id)
        body = _canonical_body(task_id, steps, parent, created_from_decision_id)
        payload = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        blob = self._git("hash-object", "-w", "--stdin", input_bytes=payload)
        tree = self._git(
            "mktree",
            input_bytes=f"100644 blob {blob}\tplan.json\n".encode(),
        )
        args = ["commit-tree", tree]
        if parent is not None:
            args.extend(("-p", parent))
        args.extend(("-m", f"plan {task_id}"))
        version_id = self._git(*args, env=_git_identity_env())
        self._git(
            "update-ref",
            self._ref(task_id),
            version_id,
            parent or ("0" * 40),
        )
        return PlanRecord(
            task_id,
            version_id,
            steps,
            parent,
            digest,
            created_from_decision_id,
        )

    def load(self, task_id: str, version_id: str | None = None) -> PlanRecord | None:
        _validate_identity(task_id)
        target = version_id or self.active_version(task_id)
        if target is None:
            return None
        try:
            raw = self._git("show", f"{target}:plan.json")
        except subprocess.CalledProcessError:
            return None
        body = json.loads(raw)
        steps = tuple(
            PlanStep(
                str(item["step_id"]),
                str(item["goal"]),
                tuple(item["completion_criteria"]),
                tuple(item.get("depends_on", ())),
            )
            for item in body["steps"]
        )
        payload = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return PlanRecord(
            str(body["task_id"]),
            target,
            steps,
            body.get("parent_version_id"),
            hashlib.sha256(payload).hexdigest(),
            body.get("created_from_decision_id"),
        )

    def active_version(self, task_id: str) -> str | None:
        _validate_identity(task_id)
        try:
            return self._git("rev-parse", "--verify", self._ref(task_id))
        except subprocess.CalledProcessError:
            return None

    def _ensure_repository(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / "HEAD").exists():
            subprocess.run(
                ["git", "init", "--bare", str(self.root)],
                check=True,
                capture_output=True,
            )

    def _git(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        result = subprocess.run(
            ["git", "--git-dir", str(self.root), *args],
            input=input_bytes,
            check=True,
            capture_output=True,
            env=env,
        )
        return result.stdout.decode("utf-8").strip()

    @staticmethod
    def _ref(task_id: str) -> str:
        return f"refs/ella/tasks/{task_id}"


def _canonical_body(
    task_id: str,
    steps: tuple[PlanStep, ...],
    parent: str | None,
    decision_id: str | None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "parent_version_id": parent,
        "created_from_decision_id": decision_id,
        "steps": [
            {
                "step_id": step.step_id,
                "goal": step.goal,
                "completion_criteria": list(step.completion_criteria),
                "depends_on": list(step.depends_on),
            }
            for step in steps
        ],
    }


def _validate_identity(value: str) -> None:
    if not value or Path(value).name != value or value.startswith("."):
        raise ValueError("task_id must be a safe Git ref component")


def _validate_steps(steps: tuple[PlanStep, ...]) -> None:
    if not steps:
        raise ValueError("plan requires at least one step")
    if any(not isinstance(step, PlanStep) for step in steps):
        raise TypeError("plan steps must be PlanStep values")
    ids = tuple(step.step_id for step in steps)
    if any(
        not isinstance(item, str)
        or not item.strip()
        or Path(item).name != item
        for item in ids
    ):
        raise ValueError("step_id must be a safe non-empty name")
    if len(ids) != len(set(ids)):
        raise ValueError("plan step IDs must be unique")
    known = set(ids)
    dependencies = {step.step_id: step.depends_on for step in steps}
    for step in steps:
        if not isinstance(step.goal, str) or not step.goal.strip():
            raise ValueError("each plan step needs a non-empty goal")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in step.completion_criteria
        ):
            raise ValueError("completion criteria must be non-empty strings")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in step.depends_on
        ):
            raise ValueError("plan dependencies must be non-empty strings")
        if len(step.depends_on) != len(set(step.depends_on)):
            raise ValueError("plan dependencies must not contain duplicates")
        if step.step_id in step.depends_on or not set(step.depends_on) <= known:
            raise ValueError("invalid plan dependency")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("plan dependencies must be acyclic")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in dependencies[step_id]:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in ids:
        visit(step_id)


def _git_identity_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "Ella Runtime",
            "GIT_AUTHOR_EMAIL": "runtime@ella.local",
            "GIT_COMMITTER_NAME": "Ella Runtime",
            "GIT_COMMITTER_EMAIL": "runtime@ella.local",
        }
    )
    return env

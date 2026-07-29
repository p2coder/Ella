from dataclasses import dataclass, replace
from enum import StrEnum
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class ProjectionStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"


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
    status: PlanStepStatus = PlanStepStatus.PENDING
    result_summary: str | None = None


@dataclass(frozen=True, slots=True)
class PlanRecord:
    task_id: str
    version_id: str
    steps: tuple[PlanStep, ...]
    projection_status: ProjectionStatus = ProjectionStatus.CURRENT
    revision: int = 1


class PlanStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def write(self, record: PlanRecord) -> PlanRecord:
        _validate_plan(record)
        if self.load(record.task_id, record.version_id) is not None:
            raise ValueError("plan version already exists and is immutable")
        self._write(record)
        return record

    def load(self, task_id: str, version_id: str) -> PlanRecord | None:
        path = self._path(task_id, version_id)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PlanRecord(
            raw["task_id"], raw["version_id"],
            tuple(PlanStep(step["step_id"], step["goal"], tuple(step["completion_criteria"]), tuple(step["depends_on"]), PlanStepStatus(step["status"]), step.get("result_summary")) for step in raw["steps"]),
            ProjectionStatus(raw["projection_status"]), raw["revision"],
        )

    def update_progress(
        self,
        task_id: str,
        version_id: str,
        step_id: str,
        expected_old_status: PlanStepStatus,
        new_status: PlanStepStatus,
        result_summary: str | None = None,
    ) -> PlanRecord:
        record = self.load(task_id, version_id)
        if record is None:
            raise KeyError((task_id, version_id))
        index = next((i for i, step in enumerate(record.steps) if step.step_id == step_id), None)
        if index is None:
            raise KeyError(step_id)
        old = record.steps[index]
        if old.status is not expected_old_status:
            raise ValueError("plan progress compare-and-set conflict")
        steps = list(record.steps)
        steps[index] = replace(old, status=new_status, result_summary=result_summary)
        updated = replace(record, steps=tuple(steps), revision=record.revision + 1)
        self._write(updated)
        return updated

    def mark_stale(self, task_id: str, version_id: str) -> PlanRecord:
        record = self.load(task_id, version_id)
        if record is None:
            raise KeyError((task_id, version_id))
        updated = replace(record, projection_status=ProjectionStatus.STALE, revision=record.revision + 1)
        self._write(updated)
        return updated

    def _write(self, record: PlanRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": record.task_id,
            "version_id": record.version_id,
            "projection_status": record.projection_status.value,
            "revision": record.revision,
            "steps": [
                {"step_id": step.step_id, "goal": step.goal, "completion_criteria": step.completion_criteria, "depends_on": step.depends_on, "status": step.status.value, "result_summary": step.result_summary}
                for step in record.steps
            ],
        }
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        path = self._path(record.task_id, record.version_id)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as temp:
            temp.write(payload)
            temp.flush()
            os.fsync(temp.fileno())
            temporary = temp.name
        os.replace(temporary, path)

    def _path(self, task_id: str, version_id: str) -> Path:
        for value in (task_id, version_id):
            if not value or Path(value).name != value:
                raise ValueError("plan identity must not contain a path")
        return self.root / f"{task_id}--{version_id}.json"


def _validate_plan(record: PlanRecord) -> None:
    if not record.task_id or not record.version_id or not record.steps:
        raise ValueError("plan identity and steps are required")
    ids = [step.step_id for step in record.steps]
    if len(ids) != len(set(ids)):
        raise ValueError("plan step IDs must be unique")
    known = set(ids)
    for step in record.steps:
        if not step.goal or not step.completion_criteria:
            raise ValueError("each plan step needs a goal and completion criteria")
        if not set(step.depends_on) <= known or step.step_id in step.depends_on:
            raise ValueError("invalid plan dependency")
    visiting: set[str] = set()
    visited: set[str] = set()
    dependencies = {step.step_id: step.depends_on for step in record.steps}
    def visit(step_id):
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

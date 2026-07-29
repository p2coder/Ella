import pytest
from runtime.plan_store import PlanRecord, PlanStep, PlanStepStatus, PlanStore, ProjectionStatus


def record():
    return PlanRecord("task", "v1", (PlanStep("a", "First", ("done",)), PlanStep("b", "Second", ("done",), ("a",))))


def test_plan_versions_are_immutable_and_progress_is_cas(tmp_path):
    store = PlanStore(tmp_path)
    store.write(record())
    with pytest.raises(ValueError): store.write(record())
    updated = store.update_progress("task", "v1", "a", PlanStepStatus.PENDING, PlanStepStatus.SUCCEEDED, "done")
    assert updated.steps[0].status is PlanStepStatus.SUCCEEDED
    assert updated.steps[1].depends_on == ("a",)
    with pytest.raises(ValueError): store.update_progress("task", "v1", "a", PlanStepStatus.PENDING, PlanStepStatus.FAILED)


def test_invalid_dag_and_paths_are_rejected(tmp_path):
    store = PlanStore(tmp_path)
    with pytest.raises(ValueError): store.write(PlanRecord("task", "v", (PlanStep("a", "A", ("done",), ("b",)), PlanStep("b", "B", ("done",), ("a",)))))
    with pytest.raises(ValueError): store.write(PlanRecord("../task", "v", (PlanStep("a", "A", ("done",)),)))


def test_old_version_can_be_marked_stale_without_structure_change(tmp_path):
    store = PlanStore(tmp_path); store.write(record())
    stale = store.mark_stale("task", "v1")
    assert stale.projection_status is ProjectionStatus.STALE
    assert tuple(step.step_id for step in stale.steps) == ("a", "b")

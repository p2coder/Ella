from agent.context import AgentExecutionContext, CapabilityScope
from runtime.plan_store import PlanStore
from tools.plan import PlanUpdateTool, PlanWrittenTool


def context():
    return AgentExecutionContext("agent", "main_agent", None, "task", "trace", "goal", "task_local", capability_scope=CapabilityScope("main_agent", (), ("plan_written", "plan_update")))


def test_plan_tools_create_and_update_progress(tmp_path):
    store = PlanStore(tmp_path); ctx = context()
    written = PlanWrittenTool(store).run(ctx, {"task_id": "task", "version_id": "v1", "steps": [{"step_id": "a", "goal": "Do it", "completion_criteria": ["done"]}]})
    updated = PlanUpdateTool(store).run(ctx, {"task_id": "task", "version_id": "v1", "step_id": "a", "expected_old_status": "pending", "new_status": "succeeded"})
    assert written.payload["version_id"] == "v1"
    assert updated.payload["status"] == "succeeded"
    assert PlanWrittenTool(store).definition.input_schema["additionalProperties"] is False

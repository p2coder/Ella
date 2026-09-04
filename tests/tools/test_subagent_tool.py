from agent.child_runner import ChildAgentRunner
from agent.context import AgentExecutionContext, CapabilityScope
from agent.decision import CALL_TOOL, SUBMIT_RESULT, ExecutionDecision, FirstDecision
from runtime.executor import CapabilityExecutor
from runtime.trace import TraceRecorder
from skill import SkillManager
from tasks.task import Task, TaskIntent, TaskState
from tools import SubagentForkTool, SubagentTool, ToolManager
from tools.base import ToolDefinition, ToolResult, ToolUncertainPolicy


class EchoTool:
    name = "echo"
    allowed_roles = ("main_agent",)

    @property
    def definition(self):
        return ToolDefinition(
            self.name,
            "Echo a value.",
            "1.0",
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            ({"value": "ok"},),
            {"type": "object"},
        )

    def run(self, context, arguments=None):
        return ToolResult(
            self.name,
            context.task_id,
            {"value": (arguments or {})["value"]},
        )


class UncertainTool(EchoTool):
    name = "uncertain"

    @property
    def definition(self):
        definition = super().definition
        return ToolDefinition(
            definition.name,
            definition.description,
            definition.schema_version,
            definition.input_schema,
            definition.input_examples,
            definition.output_schema,
            side_effecting=True,
            uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
        )

    def run(self, context, arguments=None):
        raise RuntimeError("outcome unknown")


class ScriptedAgent:
    def __init__(self, *, use_tool=False):
        self.use_tool = use_tool
        self.first_context = None
        self.first_task = None

    def decide_first_action(self, context, task):
        self.first_context = context
        self.first_task = task
        action = (
            ExecutionDecision(CALL_TOOL, "echo", {"value": "child"}, "Echo.")
            if self.use_tool
            else self._submit()
        )
        return FirstDecision(TaskIntent("Complete child prompt"), action)

    def decide_next_action(self, context, task):
        return self._submit()

    @staticmethod
    def _submit():
        return ExecutionDecision(
            SUBMIT_RESULT,
            None,
            None,
            "Done.",
            "Child completed.",
            (),
            "child answer",
        )


def _context(*, depth=0):
    return AgentExecutionContext(
        agent_id="parent-agent",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-child",
        memory_scope="task_local",
        permissions=("workspace",),
        capability_scope=CapabilityScope(
            "main_agent",
            ("skill-a",),
            ("subagent", "subagent_fork", "echo", "uncertain"),
        ),
        agent_depth=depth,
    )


def _assembly(agent, *, progress_recorder=None, trace_recorder=None):
    root = Task("task-child", state=TaskState.TOOL_EXECUTION)
    root.message_history = ({"role": "user", "content": "parent secret"},)
    root.tool_trace = ({"tool_name": "parent-observation"},)
    manager = ToolManager()
    manager.register(EchoTool())
    executor = CapabilityExecutor(SkillManager(), manager)
    runner = ChildAgentRunner(
        agent,
        executor,
        lambda _: root,
        progress_recorder=progress_recorder,
        trace_recorder=trace_recorder or TraceRecorder(),
        child_agent_id_factory=lambda: "child-agent",
    )
    manager.register(SubagentTool(runner))
    manager.register(SubagentForkTool(runner))
    return root, executor


def test_subagent_uses_clean_context_and_inherits_scope() -> None:
    agent = ScriptedAgent()
    root, executor = _assembly(agent)
    result = executor.execute(
        ExecutionDecision(
            CALL_TOOL, "subagent", {"prompt": "bounded work"}, "Delegate."
        ),
        _context(),
        root,
    )

    assert result.failure is None
    assert result.tool_result.payload["status"] == "completed"
    assert result.tool_result.payload["final_response"] == "child answer"
    assert agent.first_context.task_id == "task-child"
    assert agent.first_context.agent_id == "child-agent"
    assert agent.first_context.parent_agent_id == "parent-agent"
    assert agent.first_context.capability_scope == _context().capability_scope
    assert agent.first_context.permissions == _context().permissions
    assert agent.first_context.agent_depth == 1
    assert agent.first_task.message_history == ()
    assert agent.first_task.tool_trace == ()
    assert agent.first_task.task_local_state == {"latest_user_input": "bounded work"}
    assert result.tool_result.payload["mode"] == "clean"
    assert result.tool_result.payload["depth"] == 1
    assert result.tool_result.payload["parent_agent_id"] == "parent-agent"
    assert result.tool_result.payload["capability_scope"] == (
        _context().capability_scope.to_dict()
    )
    assert result.tool_result.payload["started_at"].endswith("Z")
    definition = executor.tool_manager.get_definition("subagent")
    assert definition.side_effecting is True
    assert definition.uncertain_policy is (
        ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH
    )


def test_subagent_nests_child_tool_observations() -> None:
    agent = ScriptedAgent(use_tool=True)
    root, executor = _assembly(agent)
    result = executor.execute(
        ExecutionDecision(CALL_TOOL, "subagent", {"prompt": "echo"}, "Delegate."),
        _context(),
        root,
    )

    observations = result.tool_result.payload["observations"]
    assert len(observations) == 1
    assert observations[0]["tool_name"] == "echo"
    assert observations[0]["task_id"] == "task-child"
    assert observations[0]["agent_id"] == "child-agent"


def test_subagent_checkpoints_in_flight_tool_and_completed_result() -> None:
    checkpoints = []
    agent = ScriptedAgent(use_tool=True)
    root, executor = _assembly(
        agent,
        progress_recorder=lambda _, state: checkpoints.append(state),
    )

    result = executor.execute(
        ExecutionDecision(CALL_TOOL, "subagent", {"prompt": "echo"}, "Delegate."),
        _context(),
        root,
    )

    dispatched = [state for state in checkpoints if state["in_flight_action"]]
    assert dispatched[0]["in_flight_action"]["tool_name"] == "echo"
    assert dispatched[0]["in_flight_action"]["tool_use_id"]
    assert checkpoints[-1]["status"] == "completed"
    assert checkpoints[-1]["in_flight_action"] is None
    assert checkpoints[-1]["observations"][0]["tool_name"] == "echo"


def test_subagent_traces_child_tool_boundaries_with_child_identity() -> None:
    recorder = TraceRecorder()
    agent = ScriptedAgent(use_tool=True)
    root, executor = _assembly(agent, trace_recorder=recorder)

    executor.execute(
        ExecutionDecision(CALL_TOOL, "subagent", {"prompt": "echo"}, "Delegate."),
        _context(),
        root,
    )

    snapshot = recorder.snapshot(root.task_id)
    assert snapshot is not None
    assert [event.event_type for event in snapshot.events] == [
        "started",
        "tool_dispatched",
        "tool_completed",
        "completed",
    ]
    assert all(
        event.payload["child_agent_id"] == "child-agent"
        for event in snapshot.events
    )


def test_subagent_retains_in_flight_tool_when_outcome_is_uncertain() -> None:
    checkpoints = []
    root = Task("task-child", state=TaskState.TOOL_EXECUTION)
    manager = ToolManager()
    manager.register(UncertainTool())
    executor = CapabilityExecutor(SkillManager(), manager)

    class UncertainAgent(ScriptedAgent):
        def decide_first_action(self, context, task):
            return FirstDecision(
                TaskIntent("Attempt uncertain work"),
                ExecutionDecision(
                    CALL_TOOL,
                    "uncertain",
                    {"value": "child"},
                    "Attempt.",
                ),
            )

    runner = ChildAgentRunner(
        UncertainAgent(),
        executor,
        lambda _: root,
        progress_recorder=lambda _, state: checkpoints.append(state),
        child_agent_id_factory=lambda: "child-agent",
    )

    result = runner.run(
        _context(), prompt="uncertain work", timeout_seconds=5
    )

    assert result.status == "uncertain"
    assert checkpoints[-1]["status"] == "uncertain"
    assert checkpoints[-1]["in_flight_action"]["tool_name"] == "uncertain"


def test_subagent_rejects_depth_above_four_before_child_dispatch() -> None:
    agent = ScriptedAgent()
    root, executor = _assembly(agent)
    result = executor.execute(
        ExecutionDecision(CALL_TOOL, "subagent", {"prompt": "too deep"}, "Delegate."),
        _context(depth=4),
        root,
    )

    assert result.failure is not None
    assert result.failure.code == "invalid_tool_input"
    assert agent.first_context is None


def test_subagent_fork_copies_parent_context_without_sharing_mutable_state() -> None:
    agent = ScriptedAgent()
    root, executor = _assembly(agent)
    root.intent = TaskIntent("Parent intent", constraints=("keep this",))
    root.task_local_state["workspace_summary"] = {"branch": "main"}
    result = executor.execute(
        ExecutionDecision(
            CALL_TOOL,
            "subagent_fork",
            {"prompt": "inspect inherited state"},
            "Fork.",
        ),
        _context(),
        root,
    )

    assert result.failure is None
    inherited = agent.first_task.task_local_state["inherited_context"]
    assert inherited["intent"]["goal"] == "Parent intent"
    assert inherited["message_history"] == root.message_history
    assert inherited["observations"] == root.tool_trace
    assert inherited["task_local_state"]["workspace_summary"] == {"branch": "main"}
    assert result.tool_result.payload["observations"] == ()

    inherited["task_local_state"]["workspace_summary"]["branch"] = "child"
    assert root.task_local_state["workspace_summary"] == {"branch": "main"}

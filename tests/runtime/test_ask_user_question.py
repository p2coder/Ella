from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep

from events import StandardizedEvent
from runtime.interactions import InteractionBroker, UserAnswer
from runtime.executor import CapabilityExecutor
from runtime.task_runtime import TaskRuntime
from skill import SkillManager
from tasks.factory import TaskFactory
from tools import ToolManager
from tools.ask_user_question import AskUserQuestionTool
from tools.base import CapabilityKind


def _wait_for_question(broker, task_id, timeout=1.0):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        pending = broker.pending_for_task(task_id)
        if pending:
            return pending[0]
        sleep(0.005)
    raise AssertionError("question was not published")


def test_interaction_tool_blocks_until_first_matching_answer() -> None:
    broker = InteractionBroker()
    tool = AskUserQuestionTool(broker)
    manager = ToolManager()
    manager.register(tool)
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            skill_manager=SkillManager(),
            tool_manager=manager,
            task_id_factory=lambda: "task-question",
        ),
        executor=CapabilityExecutor(SkillManager(), manager),
    )
    event = StandardizedEvent(
        trace_id="trace-question",
        source="test",
        payload={"text": "contact someone"},
        event_type="USER_UTTERANCE",
    )
    handle = runtime.create_task(event)
    context = runtime.get_context(handle.task_id)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            tool.run,
            context,
            {"questions": [{"question": "Who should I contact?"}]},
        )
        question = _wait_for_question(broker, handle.task_id)
        assert not future.done()
        assert runtime.provide_input(
            handle.task_id,
            correlation_key=question.question_id,
            value="Ella",
        )
        result = future.result(timeout=1)

    answer = result.payload["answers"][0]
    assert answer["question_id"] == question.question_id
    assert answer["task_id"] == handle.task_id
    assert answer["answer"] == "Ella"
    assert not broker.answer(
        UserAnswer(
            question.question_id,
            handle.task_id,
            question.user_id,
            "another answer",
            {},
        )
    )


def test_question_interface_is_multi_shaped_but_limited_to_one() -> None:
    tool = AskUserQuestionTool(InteractionBroker(), max_questions=1)

    assert tool.definition.capability_kind is CapabilityKind.INTERACTION
    assert tool.definition.input_schema["properties"]["questions"]["type"] == "array"

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from multiprocessing import get_context
from multiprocessing.connection import Connection
from time import monotonic
from time import sleep
from typing import Any, Callable

from agent.child_runner import ChildAgentRunner
from agent.context import AgentExecutionContext
from tasks.task import TaskState
from runtime.trace import NoOpTraceRecorder, TraceRecorder


MAX_SCRIPT_BYTES = 64 * 1024
MAX_RETURN_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class WorkflowRuntime:
    child_runner: ChildAgentRunner
    task_reader: Any
    trace_recorder: TraceRecorder | NoOpTraceRecorder = field(
        default_factory=NoOpTraceRecorder
    )
    progress_recorder: Callable[[str, dict[str, Any]], None] | None = None
    max_script_bytes: int = MAX_SCRIPT_BYTES
    max_wall_seconds: float = 600
    max_parallel_children: int = 8
    max_total_children: int = 32
    memory_limit_bytes: int = 64 * 1024 * 1024
    max_return_bytes: int = MAX_RETURN_BYTES

    def __post_init__(self) -> None:
        limits = (
            ("max_script_bytes", self.max_script_bytes, MAX_SCRIPT_BYTES),
            ("max_wall_seconds", self.max_wall_seconds, 600),
            ("max_parallel_children", self.max_parallel_children, 8),
            ("max_total_children", self.max_total_children, 32),
            ("memory_limit_bytes", self.memory_limit_bytes, 64 * 1024 * 1024),
            ("max_return_bytes", self.max_return_bytes, MAX_RETURN_BYTES),
        )
        for name, value, hard_limit in limits:
            if value <= 0 or value > hard_limit:
                raise ValueError(f"{name} must be in (0, {hard_limit}]")
        if self.max_total_children < self.max_parallel_children:
            raise ValueError(
                "max_total_children must allow max_parallel_children"
            )

    def execute(
        self,
        context: AgentExecutionContext,
        script: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not isinstance(script, str) or not script.strip():
            raise ValueError("script must be a non-empty string")
        if len(script.encode("utf-8")) > self.max_script_bytes:
            raise ValueError("workflow script exceeds configured byte limit")
        wall_seconds = (
            self.max_wall_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if wall_seconds <= 0 or wall_seconds > self.max_wall_seconds:
            raise ValueError(
                f"timeout_seconds must be in (0, {self.max_wall_seconds:g}]"
            )
        self._trace(
            context,
            "script_started",
            {
                "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
                "script_bytes": len(script.encode("utf-8")),
            },
        )
        workflow_state: dict[str, Any] = {
            "status": "running",
            "script": script,
            "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
            "started_at": _utc_now(),
            "completed_at": None,
            "active_tool_count": 0,
            "child_results": (),
            "control_state": self.task_reader(context.task_id).state.value,
        }
        self._checkpoint(context, workflow_state)

        process_context = get_context("spawn")
        parent_connection, child_connection = process_context.Pipe()
        process = process_context.Process(
            target=_quickjs_worker,
            args=(child_connection, script, self.memory_limit_bytes),
            daemon=True,
        )
        process.start()
        child_connection.close()
        started = monotonic()
        calls: list[dict[str, Any]] = []
        futures: dict[Future, tuple[int, str]] = {}
        script_result: Any = None
        script_done = False
        connection_open = True
        error: str | None = None
        child_failure: str | None = None
        pool = ThreadPoolExecutor(max_workers=self.max_parallel_children)
        pause_recorded = False
        try:
            while process.is_alive() or futures:
                if monotonic() - started > wall_seconds:
                    raise TimeoutError("workflow execution timed out")
                task_state = self.task_reader(context.task_id).state
                while task_state in {TaskState.PAUSE_REQUESTED, TaskState.PAUSED}:
                    if not pause_recorded:
                        self._trace(context, "control_safe_point", {"state": task_state.value})
                        workflow_state["control_state"] = task_state.value
                        self._checkpoint(context, workflow_state)
                        pause_recorded = True
                    if monotonic() - started > wall_seconds:
                        raise TimeoutError("workflow execution timed out while paused")
                    sleep(0.01)
                    task_state = self.task_reader(context.task_id).state
                pause_recorded = False
                workflow_state["control_state"] = task_state.value
                if task_state in {TaskState.KILL_REQUESTED, TaskState.KILLED}:
                    self._trace(context, "control_safe_point", {"state": task_state.value})
                    raise RuntimeError("parent task was killed")
                if connection_open and parent_connection.poll(0.01):
                    try:
                        message = parent_connection.recv()
                    except EOFError:
                        connection_open = False
                        message = None
                    if message is None:
                        continue
                    kind = message[0]
                    if kind == "call":
                        _, call_id, tool_name, raw_arguments = message
                        if child_failure is not None:
                            parent_connection.send(
                                (
                                    "settle",
                                    call_id,
                                    False,
                                    "workflow dispatch closed after child failure",
                                )
                            )
                            continue
                        if tool_name not in {"subagent", "subagent_fork"}:
                            parent_connection.send(
                                ("settle", call_id, False, "workflow Tool is not allowed")
                            )
                            continue
                        if len(calls) >= self.max_total_children:
                            parent_connection.send(
                                ("settle", call_id, False, "child call limit exceeded")
                            )
                            continue
                        arguments = json.loads(raw_arguments)
                        if not isinstance(arguments, dict):
                            raise ValueError("workflow child arguments must be an object")
                        unsupported = set(arguments) - {"prompt", "timeout_seconds"}
                        if unsupported:
                            raise ValueError("workflow child arguments are invalid")
                        prompt = arguments.get("prompt")
                        if not isinstance(prompt, str) or not prompt.strip():
                            raise ValueError("workflow child prompt must be non-empty")
                        timeout = float(arguments.get("timeout_seconds", 300))
                        calls.append(
                            {
                                "call_id": call_id,
                                "tool_name": tool_name,
                                "status": "running",
                                "called_at": _utc_now(),
                                "completed_at": None,
                                "result": None,
                            }
                        )
                        self._trace(
                            context,
                            "tool_dispatched",
                            {"call_id": call_id, "tool_name": tool_name},
                        )
                        workflow_state["active_tool_count"] = len(futures) + 1
                        workflow_state["child_results"] = tuple(calls)
                        self._checkpoint(context, workflow_state)
                        future = pool.submit(
                            self.child_runner.run,
                            context,
                            prompt=prompt,
                            timeout_seconds=timeout,
                            fork=tool_name == "subagent_fork",
                        )
                        futures[future] = (len(calls) - 1, call_id)
                    elif kind == "done":
                        _, succeeded, raw_value = message
                        script_done = True
                        if succeeded:
                            script_result = json.loads(raw_value)
                        else:
                            error = str(raw_value)
                for future in tuple(futures):
                    if not future.done():
                        continue
                    call_index, call_id = futures.pop(future)
                    try:
                        child_result = future.result().to_dict()
                        calls[call_index]["result"] = child_result
                        calls[call_index]["status"] = child_result["status"]
                        calls[call_index]["called_at"] = child_result.get(
                            "started_at"
                        ) or calls[call_index]["called_at"]
                        calls[call_index]["completed_at"] = child_result.get(
                            "completed_at"
                        ) or _utc_now()
                        succeeded = child_result["status"] == "completed"
                        payload = (
                            json.dumps(child_result, ensure_ascii=False)
                            if succeeded
                            else str(child_result.get("error") or child_result["status"])
                        )
                    except Exception as child_error:
                        calls[call_index]["status"] = "failed"
                        calls[call_index]["completed_at"] = _utc_now()
                        succeeded = False
                        payload = str(child_error)
                    if not succeeded and child_failure is None:
                        child_failure = payload
                    if process.is_alive():
                        parent_connection.send(("settle", call_id, succeeded, payload))
                    self._trace(
                        context,
                        "tool_completed",
                        {
                            "call_id": call_id,
                            "tool_name": calls[call_index]["tool_name"],
                            "status": calls[call_index]["status"],
                        },
                    )
                    workflow_state["active_tool_count"] = len(futures)
                    workflow_state["child_results"] = tuple(calls)
                    self._checkpoint(context, workflow_state)
                if script_done and not futures:
                    self._trace(
                        context,
                        "promise_join",
                        {"completed_calls": len(calls)},
                    )
                    break
            if child_failure is not None:
                raise RuntimeError(f"workflow child failed: {child_failure}")
            if error is not None:
                raise RuntimeError(f"workflow script failed: {error}")
            if not script_done:
                raise RuntimeError("workflow isolate exited without a result")
            result = {
                "status": "completed",
                "active_tool_count": 0,
                "script_return_value": script_result,
                "child_results": tuple(calls),
            }
            encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
            if len(encoded) > self.max_return_bytes:
                raise ValueError("workflow result exceeds configured byte limit")
            self._trace(
                context,
                "script_completed",
                {"completed_calls": len(calls)},
            )
            workflow_state.update(
                {
                    "status": "completed",
                    "completed_at": _utc_now(),
                    "active_tool_count": 0,
                    "child_results": tuple(calls),
                }
            )
            self._checkpoint(context, workflow_state)
            return result
        except Exception as workflow_error:
            self._trace(
                context,
                "script_failed",
                {"error": str(workflow_error), "completed_calls": len(calls)},
            )
            workflow_state.update(
                {
                    "status": "failed",
                    "completed_at": _utc_now(),
                    "active_tool_count": len(futures),
                    "child_results": tuple(calls),
                    "error": str(workflow_error),
                }
            )
            self._checkpoint(context, workflow_state)
            uncertain = any(
                call.get("status") in {"running", "uncertain"} for call in calls
            )
            workflow_error.tool_outcome_uncertain = uncertain
            raise
        finally:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            pool.shutdown(wait=False, cancel_futures=True)
            parent_connection.close()

    def _trace(
        self,
        context: AgentExecutionContext,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.trace_recorder.record(
            task_id=context.task_id,
            boundary="workflow",
            event_type=event_type,
            payload=payload,
        )

    def _checkpoint(
        self,
        context: AgentExecutionContext,
        workflow_state: dict[str, Any],
    ) -> None:
        if self.progress_recorder is not None:
            self.progress_recorder(context.task_id, deepcopy(workflow_state))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _quickjs_worker(
    connection: Connection, script: str, memory_limit_bytes: int
) -> None:
    import quickjs

    context = quickjs.Context()
    context.set_memory_limit(memory_limit_bytes)
    next_call_id = 0
    completion: list[tuple[bool, str]] = []

    def enqueue(tool_name: str, arguments_json: str) -> int:
        nonlocal next_call_id
        next_call_id += 1
        connection.send(("call", next_call_id, tool_name, arguments_json))
        return next_call_id

    def complete(succeeded: bool, result_json: str) -> None:
        completion.append((bool(succeeded), result_json))

    context.add_callable("__workflow_enqueue", enqueue)
    context.add_callable("__workflow_complete", complete)
    bootstrap = """
        const __hostEnqueue = globalThis.__workflow_enqueue;
        const __hostComplete = globalThis.__workflow_complete;
        delete globalThis.__workflow_enqueue;
        delete globalThis.__workflow_complete;
        const __pending = new Map();
        const __call = (name, args) => new Promise((resolve, reject) => {
          const id = __hostEnqueue(name, JSON.stringify(args));
          __pending.set(id, {resolve, reject});
        });
        globalThis.__workflow_settle = (id, ok, payload) => {
          const pending = __pending.get(id);
          if (!pending) throw new Error('unknown workflow call');
          __pending.delete(id);
          if (ok) pending.resolve(JSON.parse(payload));
          else pending.reject(new Error(payload));
        };
        Object.defineProperty(globalThis, 'tools', {
          value: Object.freeze({
            subagent: (args) => __call('subagent', args),
            subagent_fork: (args) => __call('subagent_fork', args),
          }),
          writable: false,
          configurable: false,
        });
        globalThis.eval = undefined;
        globalThis.Function = undefined;
        globalThis.require = undefined;
        globalThis.process = undefined;
    """
    try:
        context.eval(bootstrap)
        context.eval(
            "(async () => {\n'use strict';\n"
            + script
            + "\n})().then("
            "value => __hostComplete(true, JSON.stringify(value)),"
            "error => __hostComplete(false, String(error && error.message || error))"
            ");"
        )
        while not completion:
            while context.execute_pending_job():
                pass
            if connection.poll(0.01):
                kind, call_id, succeeded, payload = connection.recv()
                if kind != "settle":
                    raise RuntimeError("invalid workflow host message")
                context.eval(
                    "__workflow_settle("
                    + json.dumps(call_id)
                    + ","
                    + json.dumps(succeeded)
                    + ","
                    + json.dumps(payload)
                    + ")"
                )
        connection.send(("done", *completion[0]))
    except BaseException as error:
        try:
            connection.send(("done", False, str(error)))
        except BaseException:
            pass
    finally:
        connection.close()

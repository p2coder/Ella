from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import json
from multiprocessing import get_context
from multiprocessing.connection import Connection
from time import monotonic
from typing import Any

from agent.child_runner import ChildAgentRunner
from agent.context import AgentExecutionContext
from tasks.task import TaskState


MAX_SCRIPT_BYTES = 64 * 1024
MAX_RETURN_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class WorkflowRuntime:
    child_runner: ChildAgentRunner
    task_reader: Any
    max_wall_seconds: float = 600
    max_parallel_children: int = 8
    max_total_children: int = 32
    memory_limit_bytes: int = 64 * 1024 * 1024
    max_return_bytes: int = MAX_RETURN_BYTES

    def execute(
        self, context: AgentExecutionContext, script: str
    ) -> dict[str, Any]:
        if not isinstance(script, str) or not script.strip():
            raise ValueError("script must be a non-empty string")
        if len(script.encode("utf-8")) > MAX_SCRIPT_BYTES:
            raise ValueError("workflow script exceeds 64 KiB")

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
        error: str | None = None
        pool = ThreadPoolExecutor(max_workers=self.max_parallel_children)
        try:
            while process.is_alive() or futures:
                if monotonic() - started > self.max_wall_seconds:
                    raise TimeoutError("workflow execution timed out")
                task_state = self.task_reader(context.task_id).state
                if task_state in {TaskState.KILL_REQUESTED, TaskState.KILLED}:
                    raise RuntimeError("parent task was killed")
                if parent_connection.poll(0.01):
                    message = parent_connection.recv()
                    kind = message[0]
                    if kind == "call":
                        _, call_id, tool_name, raw_arguments = message
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
                        timeout = float(arguments.get("timeout_seconds", 120))
                        calls.append(
                            {
                                "call_id": call_id,
                                "tool_name": tool_name,
                                "result": None,
                            }
                        )
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
                        succeeded = child_result["status"] == "completed"
                        payload = (
                            json.dumps(child_result, ensure_ascii=False)
                            if succeeded
                            else str(child_result.get("error") or child_result["status"])
                        )
                    except Exception as child_error:
                        succeeded = False
                        payload = str(child_error)
                    if process.is_alive():
                        parent_connection.send(("settle", call_id, succeeded, payload))
                if script_done and not futures:
                    break
            if error is not None:
                raise RuntimeError(f"workflow script failed: {error}")
            if not script_done:
                raise RuntimeError("workflow isolate exited without a result")
            encoded = json.dumps(script_result, ensure_ascii=False).encode("utf-8")
            if len(encoded) > self.max_return_bytes:
                raise ValueError("workflow return value exceeds 1 MiB")
            return {
                "script_return_value": script_result,
                "child_results": tuple(calls),
            }
        finally:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            pool.shutdown(wait=True, cancel_futures=True)
            parent_connection.close()


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
        const __pending = new Map();
        const __call = (name, args) => new Promise((resolve, reject) => {
          const id = __workflow_enqueue(name, JSON.stringify(args));
          __pending.set(id, {resolve, reject});
        });
        globalThis.__workflow_settle = (id, ok, payload) => {
          const pending = __pending.get(id);
          if (!pending) throw new Error('unknown workflow call');
          __pending.delete(id);
          if (ok) pending.resolve(JSON.parse(payload));
          else pending.reject(new Error(payload));
        };
        globalThis.tools = Object.freeze({
          subagent: (args) => __call('subagent', args),
          subagent_fork: (args) => __call('subagent_fork', args),
        });
        globalThis.eval = undefined;
        globalThis.Function = undefined;
        globalThis.require = undefined;
        globalThis.process = undefined;
    """
    try:
        context.eval(bootstrap)
        context.eval(
            "(async () => {\n"
            + script
            + "\n})().then("
            "value => __workflow_complete(true, JSON.stringify(value)),"
            "error => __workflow_complete(false, String(error && error.message || error))"
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

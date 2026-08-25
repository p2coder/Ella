# PRD: Unified Action Model, Durable Execution, and Concurrent Task Runtime

## 1. Status and authority

This document is the authoritative target contract for the next Ella Runtime
version. Current code is the source of truth only when diagnosing the old
implementation. Old checkpoints, old action payloads, and old task states do
not require migration or compatibility.

```text
checkpoint before reasoning
-> REASONING
-> one ExecutionDecision
-> checkpoint after reasoning
-> CALL_TOOL or COMPLETE
-> observation / terminal result
-> repeat when needed
```

There is no separate Strategy Selection model call.

## 2. Goals

- Use one model-visible action protocol for simple tasks, plans, interaction,
  and external tools.
- Remove the duplicate strategy call from first-action latency.
- Make plans a versioned internal capability rather than an execution mode.
- Support durable recovery from the latest complete checkpoint.
- Execute independent TaskGraph nodes in deterministic concurrent waves.
- Run multiple Tasks concurrently while keeping permissions, retries, trace,
  and checkpoints isolated.
- Persist complete reasoning, capability, state, checkpoint, and delivery trace.

## 3. Non-goals

- No migration for old checkpoint or action schemas.
- No forced cancellation of arbitrary Python code in this version.
- No provider-specific action type in Runtime contracts.
- No global node pool shared by different Tasks.
- No model-visible pause, resume, kill, checkpoint, or memory-write capability.
- Runtime failure describes a failed execution process, not an unavailable
  requested real-world outcome.

## 4. ExecutionDecision contract

The only actions are `CALL_TOOL` and `COMPLETE`. `WAIT` and `REPLAN` are deleted
from model output, Runtime branching, Task states, prompts, persistence, and
tests.

```python
ExecutionDecision
- action: CALL_TOOL | COMPLETE
- tool_name: str | None
- tool_input: dict | None
- decision_reason: str
- completion_summary: str | None
- evidence_refs: tuple[str, ...]
```

- `decision_reason` explains why the action was selected. It is trace/display
  metadata, not the user-facing conclusion.
- `CALL_TOOL` requires a visible capability and object-shaped input.
- `COMPLETE` requires a non-empty `completion_summary`.
- `evidence_refs` may reference only observations visible to the Task. It may be
  empty only when the conclusion does not depend on capability output.
- Malformed JSON, unknown action/capability, missing fields, and unknown evidence
  references are rejected without execution.

## 5. Capability model

All callable capabilities use `ToolDefinition` and one Executor entry:

```text
CapabilityKind.EXTERNAL
CapabilityKind.RUNTIME
CapabilityKind.INTERACTION
```

- `EXTERNAL` observes or changes the external environment.
- `RUNTIME` changes Ella's internal execution model, such as `plan_written`.
- `INTERACTION` exchanges structured information with the user, such as
  `ask_user_question`.

The model receives only definitions visible in the current Task's immutable
capability scope. ToolManager may store process-level instances, but visibility
is Task-local and instances are resolved by name at execution time.

## 6. Planning

Planning is expressed only as `CALL_TOOL(plan_written)`. `plan_written` is
model-visible and has `CapabilityKind.RUNTIME`. `plan_update` is not
model-visible; progress is derived from node-run state.

The first plan creates a version. Structural changes create a new version whose
parent is the active version. A Runtime observer validates the successful
result, activates the version, migrates valid unfinished nodes, creates or
updates `TaskGraphRun`, checkpoints it, and publishes an observation. SubAgent
and the Tool never mutate Task state directly.

### 6.1 Git PlanStore

Plan versions are stored in a dedicated bare Git repository. Each Task has one
active ref: `refs/ella/tasks/<task_id>`. Each version is a commit containing a
canonical Plan document and metadata; its parent records lineage. Runtime uses
compare-and-swap `update-ref`. History may branch, but execution uses one active
ref. Runtime generates version IDs instead of trusting model-provided IDs.

## 7. Task states

```text
CREATED, FORMULATING, READY, REASONING, TOOL_EXECUTION,
PAUSE_REQUESTED, PAUSED, KILL_REQUESTED,
SUCCEEDED, FAILED, UNCERTAIN, KILLED, DELIVERED
```

`RUNNING`, `WAITING`, `PLANNING`, and `REPLANNING` do not exist.

- Entering PAUSED records the real interrupted state, never PAUSE_REQUESTED.
- Resume loads the latest checkpoint and restores that interrupted state.
- KILLED cannot resume.
- SUCCEEDED includes an honest conclusion that information was unavailable.
- FAILED means the execution process failed.
- UNCERTAIN is reserved for an external side-effect whose outcome is unknown.
- SUCCEEDED and FAILED may transition to DELIVERED. Uncertain resolution records
  details, converts to FAILED, and can then be delivered.

## 8. AskUserQuestion

Missing user-owned information is obtained through the model-selected
`ask_user_question` INTERACTION capability.

The interface is array-shaped with a configurable maximum. Version one limits
it to one question while preserving a future multi-question contract.

```text
Question: question_id, task_id, user_id, question, metadata
Answer: question_id, task_id, user_id, answer, metadata
```

Runtime generates IDs. The Tool remains blocked in TOOL_EXECUTION until a
matching answer arrives. There is no Question state enum and no Task WAITING
state. The first valid answer wins; later answers are rejected. Recovery may
emit the same question again. The owning Task worker remains occupied.

Other Tools never invoke this capability. Missing or mismatched Tool content is
an observation; the model decides whether to use another capability, ask the
user, or COMPLETE honestly.

## 9. Retry and failure semantics

Each logical Step has one retry budget: two retries after the initial attempt.
There are no separate argument and decision budgets.

- Invalid decision or arguments consume the Step retry budget.
- Argument repair locks `active_tool_name`; switching Tools is a repair
  violation and is not executed.
- Permission, environment, backend, output, and internal errors become failure
  observations, never successful ToolResult facts.
- Ordinary capability failure may lead to another capability or honest COMPLETE.
- Structural plan correction uses `plan_written` and consumes a Tool attempt.
- Side-effect uncertainty follows UNCERTAIN policy.

## 10. Worker model

TaskRuntime owns a fixed reusable worker pool:

```text
max_task_workers = 500
max_parallel_steps_per_task = 8
```

- One Task worker owns one Task until terminal state.
- A PAUSED Task continues occupying its worker.
- Tasks remain queued while all workers are occupied.
- A worker returns idle only after its Task is terminal.
- One global control worker routes pause, resume, and kill to owning workers.
- Every Task worker manages its own bounded wave executor; there is no global
  node pool.

Python cannot safely terminate arbitrary in-flight threads. Control is applied
at checkpoint-safe boundaries. Unknown side-effect outcomes use UNCERTAIN.

## 11. TaskGraph wave execution

At a wave boundary, Runtime derives all READY Step nodes from
`TaskGraphRun.node_runs` and dispatches up to eight concurrently.

- A completed node does not immediately dispatch its successor.
- Successors wait until every node in the current wave settles.
- Any successful terminal path satisfies the goal. Runtime settles the already
  dispatched wave, marks undispatched alternatives SKIPPED, and emits no next
  wave.
- UNCERTAIN in the dispatched wave overrides simultaneous terminal success.
- A failed path does not fail the Task while another reachable path exists.
- No reachable success path produces FAILED.

Checkpoint policy is deterministic: wave size at most 20 writes one atomic
checkpoint after the wave; larger waves checkpoint each node completion. The
threshold is configurable.

## 12. Checkpoint and restore

The latest complete checkpoint is the only recovery source. Checkpoints are
written before and after reasoning, before Tool dispatch, after normalized Tool
result, after wave settlement, at lifecycle/control safe points, and before
terminal delivery metadata is published.

Exit during reasoning restores the pre-reasoning checkpoint and repeats that
call. A completed post-reasoning checkpoint resumes from the saved decision.

The checkpoint stores Task state, interrupted state, capability scope, current
decision, active Plan version, graph definition/run, Step state, observations,
failures, wave metadata, control metadata, and delivery metadata. Trace is
append-only observability data, not the restore source. Paths come from
`config/config.py` and default to project-relative directories.

## 13. Prompt contract

The only action prompt is EXECUTION_DECISION. Its WorkSpace contains Task and
Step identity/state, goal, active Plan and graph, Task-visible Skills and
Capabilities, observations with IDs, retry/lock/blacklist state, and relevant
memory. Prompt Engine only composes text; it never calls providers, executes
capabilities, mutates Runtime, or persists memory.

## 14. Completion and delivery

`COMPLETE.completion_summary` and evidence feed final response generation.
Provider failure uses a deterministic readable fallback and still SUCCEEDS.
The final answer must not expose Python representations or confuse
`decision_reason` with the conclusion.

Terminal results are published asynchronously by Task ID. Delivery retry never
re-runs reasoning or capabilities.

## 15. Acceptance criteria

- Exactly one LLM decision boundary exists before the first action.
- Only CALL_TOOL and COMPLETE exist in the model protocol.
- No source/persistence contract depends on StrategyDecision, WAIT, REPLAN,
  RUNNING, or WAITING.
- `plan_written` creates a Git-backed Plan version and activates a TaskGraph.
- `ask_user_question` blocks as an interaction Tool and resumes from a matching
  answer without a waiting Task state.
- Tasks restore from the latest checkpoint at every supported safe boundary.
- Multiple Tasks run concurrently with isolated workers and context.
- Ready DAG nodes run in strict bounded waves.
- On-disk trace covers reasoning, Tool, state, checkpoint, and delivery.
- Default mock-safe startup remains runnable.

> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella Task / Step / Tool Graph PRD Implementation Prompts

本文档依据 `docs/task_step_tool_graph_prd.md` 和当前仓库实现拆分。以下每一节都是可以直接复制给 Codex 的单 PR 提示词。

## 总体执行规则

- 必须按 PR 编号顺序实施，不得跳过前置条件。
- 每个 PR 只修改一个主要模块边界，并严格遵守 Allowed files。
- 如果实现需要修改未列出的文件，必须停止并解释，不得擅自扩大范围。
- 每个 PR 完成后必须运行定向测试、`python -m pytest` 和 `python main.py`。
- 每个 PR 合并后主分支必须可运行；兼容代码只能是只读 alias/projection，不得形成第二份可变状态。
- 不得通过硬编码 Tool、Skill、Plan 或状态来绕过领域契约。
- 不得提前实现后续 PR 的行为。
- 本文中的 MUST、不得、必须均为验收要求。

## 实施顺序总览

| PR | 唯一边界 | 完成后新增能力 |
| --- | --- | --- |
| 1 | Graph 契约 | edges-only DAG 与动态容量 |
| 2 | Tool 元数据 | ToolDefinition 权威安全元数据与 override 校验 |
| 3 | 状态契约 | Task/Step/ToolNode 状态与纯转移表 |
| 4 | Task 聚合 | Task 替代 TaskSession 聚合 |
| 5 | 标识协议 | 公共协议移除 session_id |
| 6 | TaskStore | 本地原子 checkpoint |
| 7 | Queue/Scheduler | READY Task 领取与恢复队列 |
| 8 | 创建边界 | Task 在 formulation 前创建 |
| 9 | StepRuntime | 一次 tick 执行一个 ToolNode |
| 10 | TaskRuntime | TaskGraph 调度、预算与终态 |
| 11 | Plan Tool | PlanStore、plan_written、plan_update |
| 12 | Plan/ReAct | Bootstrap Graph 和唯一分流 |
| 13 | 控制面 | Pause/Resume/Kill 与阶段恢复 |
| 14 | Waiting/熔断 | WaitingCondition 与 Step 局部 Tool 阻断 |
| 15 | Uncertain/交付 | 不确定失败收口及成功/失败交付 |
| 16 | Trace | Append-only 分层运行轨迹 |
| 17 | App/UI | Facade 控制命令与状态展示 |
| 18 | 包所有权 | 机械迁移到 tasks/agent/runtime |
| 19 | 契约回归 | 最终架构边界验证 |

任何 PR 的全量测试失败都必须在该 PR 范围内解决或停止说明阻塞，不得继续执行后续 PR。

---

## PR 1：Graph Definition 与 Graph Run 数据契约

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 1: add graph definition and graph run contracts.

Before making changes, read:

docs/task_step_tool_graph_prd.md
docs/architecture.md
docs/tune.md
sessions/session.py
sessions/execution_state.py

## Goal

Add immutable TaskGraph and ToolGraph data contracts with edges as the only topology source.

This PR only defines graph data and pure validation/projection helpers. It must not wire graphs into TaskRuntime, SubAgent, Executor, EventRuntime, tools, memory, or UI.

## Allowed files

Only create or modify:

sessions/graph.py
tests/sessions/test_graph_contracts.py

Do not modify any other files. Do not modify __init__.py.

## Implement

Define equivalent contracts for:

- GraphEdge:
  - from_node_id
  - to_node_id
  - condition
  - priority
- TaskGraphNodeDefinition with node_id, node_type, payload.
- TaskGraphDefinition with graph_id, version, nodes, edges, entry_node_ids, terminal_node_ids.
- ToolNodeDefinition with node_id, tool_name, tool_version, input_binding, success_condition, execution_override.
- ToolGraphDefinition with graph_id, nodes, edges, entry_node_ids, terminal_node_ids.
- TaskGraphRun / ToolGraphRun and node run mappings.
- DynamicGraphCapacity with allocated_slots, used_slots, max_slots.

Requirements:

- edges are the only topology, dependency, branch-condition, and priority source.
- Node definitions must not contain dependencies, condition, or priority duplicates.
- Reject duplicate node IDs, missing edge endpoints, cycles, invalid entries, and invalid terminals.
- Conditions must be declarative data and must not execute arbitrary Python.
- Provide deterministic predecessor, successor, topological-order, and reachable-terminal helpers.
- Multiple ready nodes sort by edge priority, topological order, then node_id.
- Dynamic capacity initializes to min(5, max_steps), doubles within max_steps, and empty slots are not nodes.
- Contracts are immutable and deterministic.
- Do not define TaskState, StepState, or ToolNodeState in this PR.

## Tests

Add tests for valid DAGs, duplicate IDs, missing endpoints, cycles, deterministic ordering, edges-only topology, terminal reachability, and 5-slot/doubling capacity behavior.

Run:

python -m pytest tests/sessions/test_graph_contracts.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

feat(graph): add task and tool graph contracts
```

---

## PR 2：ToolDefinition 执行安全元数据

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 2: add authoritative Tool execution metadata and validated node overrides.

Before making changes, read:

docs/task_step_tool_graph_prd.md
docs/pr_tool.md
docs/tune.md
tools/base.py
tools/manager.py
sessions/graph.py

## Precondition

PR 1 must already be merged. Stop if ToolNodeDefinition does not exist.

## Goal

Make ToolDefinition the single source of tool version, idempotency, side-effect, uncertain, and override policy.

## Allowed files

Only create or modify:

tools/base.py
tools/manager.py
tests/tools/test_tool_execution_metadata.py

Do not modify any other files. Do not modify __init__.py.

## Implement

Extend ToolDefinition with equivalent fields for:

- version
- idempotency: IDEMPOTENT | NON_IDEMPOTENT | UNKNOWN
- side_effecting
- uncertain_policy
- overridable_fields

Add ToolManager validation/resolution that:

- resolves ToolDefinition by stable name and version.
- rejects missing or version-mismatched tools.
- accepts ToolNode execution_override only for fields explicitly listed in overridable_fields.
- returns an immutable effective metadata snapshot for ToolNodeRun/Trace.
- never stores StepToolAvailability or Task state.
- keeps ToolRegistry, if used, as the only Tool instance storage source.

Existing tools must receive backward-compatible safe defaults. Do not alter their run behavior.

## Forbidden scope

Do not modify sessions/graph.py, TaskRuntime, Executor, SubAgent, providers, devices, memory, or demo.

## Tests

Test default metadata, stable version lookup, valid override, forbidden override, missing version, immutable snapshots, and that ToolManager stores no Step state.

Run:

python -m pytest tests/tools/test_tool_execution_metadata.py
python -m pytest
python main.py

PR title:

feat(tools): add authoritative execution metadata
```

---

## PR 3：分层状态与纯状态转移契约

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 3: add hierarchical task, step, and tool-node state contracts.

Before making changes, read:

docs/task_step_tool_graph_prd.md
docs/tool_failure_prd.md
docs/tune.md
sessions/session.py
sessions/execution_state.py

## Preconditions

PR 1 and PR 2 must already be merged.

## Goal

Define the single TaskState, StepState, ToolNodeState, WaitingCondition, control command, delivery, and pure transition contracts.

## Allowed files

Only create or modify:

sessions/session.py
sessions/execution_state.py
tests/sessions/test_hierarchical_state_contracts.py
tests/sessions/test_task_transition_table.py

Do not modify any other files. Do not modify __init__.py.

## Implement

TaskState:

CREATED, FORMULATING, READY, RUNNING, WAITING, PAUSE_REQUESTED, PAUSED,
KILL_REQUESTED, SUCCEEDED, FAILED, UNCERTAIN, KILLED, DELIVERED.

StepState:

PENDING, READY, RUNNING, PAUSED, SUCCEEDED, FAILED, UNCERTAIN, KILLED, SKIPPED.

ToolNodeState:

PENDING, READY, RUNNING, SUCCEEDED, FAILED, UNCERTAIN, SKIPPED.

Also define equivalent immutable contracts for:

- WaitingCondition
- TaskControlCommand / TaskControlResult
- UncertainResolutionRecord
- TaskDeliveryRecord / DeliveryAttempt
- StepToolAvailability with AVAILABLE/BLOCKED and blocked_until
- ToolAttempt with attempt_index scoped to one ToolNodeRun

Requirements:

- Implement the exact transition table from PRD section 7.6 as pure validated transitions.
- Invalid transitions return/raise stable invalid_state_transition behavior.
- terminal success policy is ANY: any terminal success completes the Step/Task and unused paths become SKIPPED.
- pause records paused_from_state as the state before PAUSE_REQUESTED, never PAUSE_REQUESTED itself.
- resume target is paused_from_state, not always READY.
- KILLED and DELIVERED are terminal.
- FAILED and SUCCEEDED may only proceed through delivery behavior.
- Existing legacy enum names may be temporary read-only aliases only if required to keep main runnable; new state mutation must use the new states.
- Do not implement Runtime orchestration.

## Tests

Cover every allowed and rejected transition, pause origin, resume target, ANY terminal behavior, SKIPPED paths, terminal immutability, and immutable isolated defaults.

Run:

python -m pytest tests/sessions/test_hierarchical_state_contracts.py tests/sessions/test_task_transition_table.py
python -m pytest
python main.py

PR title:

feat(tasks): add hierarchical state contracts
```

---

## PR 4：Task 聚合替代 TaskSession

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 4: replace TaskSession with the single Task aggregate.

Before making changes, read:

docs/task_step_tool_graph_prd.md
docs/tune.md
sessions/session.py
sessions/session_manager.py
agent/context.py

## Preconditions

PR 1 through PR 3 must already be merged.

## Goal

Make Task the only mutable task/runtime aggregate and remove the independent Session lifecycle concept.

## Allowed files

Only create or modify:

sessions/session.py
sessions/session_manager.py
tests/sessions/test_task_aggregate.py
tests/sessions/test_session_manager.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- Rename the runtime aggregate to Task.
- Task owns task_id, trace_id, source_event, optional handoff/graph, execution_context, state, waiting_condition, paused_from_state, completion, terminal_outcome, failure, uncertain resolution, delivery, control request, and timestamps.
- CREATED starts with handoff=None, graph=None, completion=None, terminal_outcome=None.
- Replace TaskSessionManager with TaskFactory or TaskManager semantics.
- Remove TaskSessionCreation as a domain concept; use TaskCreationResult only if multiple return values are unavoidable.
- TaskFactory must create isolated Task/context instances.
- active_step_ids must be a read-only projection from TaskGraphRun.node_runs and never a stored mutable field.
- A temporary TaskSession = Task import alias is permitted only for old imports. It must not create a second class, ID, state, or store.
- Do not change TaskRuntime orchestration yet.

## Tests

Verify one aggregate, isolated mutable state, CREATED invariants, no independent session lifecycle, active-step projection, and compatibility imports if retained.

Run:

python -m pytest tests/sessions/test_task_aggregate.py tests/sessions/test_session_manager.py
python -m pytest
python main.py

PR title:

refactor(tasks): replace task session with task aggregate
```

---

## PR 5：移除 session_id 公共协议

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 5: remove session_id from public runtime contracts.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md, agent/context.py,
sessions/strategy.py, tools/base.py, runtime/timing.py, memory/manager.py, and runtime/event_router.py.

## Precondition

PR 4 must already be merged. Stop if Task is not the primary aggregate.

## Goal

Remove the duplicate session identifier from cross-module contracts and use task_id/trace_id/conversation_id according to their documented meanings.

## Allowed files

Only create or modify:

agent/context.py
sessions/strategy.py
sessions/decision.py
sessions/completion.py
tools/base.py
runtime/timing.py
memory/manager.py
runtime/event_router.py
runtime/task_runtime.py
sessions/subagent.py
tools/camera_scene.py
tools/screen_scene.py
tools/mock_tools.py
tests/contracts/test_task_identity_protocol.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- AgentExecutionContext uses task_id and trace_id; remove session_id.
- StrategyDecision, ToolResult, completion, timing, memory requests/records, and routing contracts must not propagate session_id.
- Runtime-owned IDs must not appear as LLM-generated Tool arguments.
- Router fields that target tasks become target_task_id/active_task_ids; true conversation routing uses conversation_id.
- Do not write session_id=task_id compatibility values into Memory, Trace, checkpoint, or new serialized output.
- Read-only deserialization/constructor compatibility for old records and tests is allowed, but it must not be stored as an independent field and serialization must emit only new fields.
- Runtime, SubAgent, and existing Tool implementations must use task_id internally after this PR.
- Preserve existing functional behavior.

## Tests

Test serialization, old-record reading if supported, no session_id leakage, correct task/conversation routing semantics, and context propagation.

Run:

python -m pytest tests/contracts/test_task_identity_protocol.py
python -m pytest
python main.py

PR title:

refactor(contracts): remove duplicate session identity
```

---

## PR 6：本地 TaskStore 与原子 Checkpoint

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 6: add durable local TaskStore checkpoints.

Before making changes, read:

docs/task_step_tool_graph_prd.md
docs/tune.md
sessions/session.py
sessions/graph.py
runtime/task_runtime.py

## Preconditions

PR 1 through PR 5 must already be merged.

## Goal

Add the single durable storage boundary for Task aggregates without adding a database.

## Allowed files

Only create or modify:

runtime/task_store.py
tests/runtime/test_task_store_checkpoint.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- TaskStore save/load/list using task_id as key.
- Versioned deterministic checkpoint serialization.
- Atomic temp-write, fsync where supported, and replace behavior.
- Optimistic expected-version compare-and-set.
- Persist Task state, graph runs, budgets, waiting condition, pause origin, control request, uncertain details, and delivery records.
- Never persist Tool instances, Provider clients, API keys, full prompt text, or raw media.
- Define recovery classification helpers for READY, PAUSED, WAITING, UNCERTAIN, result-delivery, RUNNING, PAUSE_REQUESTED, KILL_REQUESTED, KILLED, and DELIVERED.
- A checkpoint write failure must be structured and must not corrupt the previous checkpoint.
- Do not wire TaskRuntime yet.

## Tests

Test round-trip, deterministic data, atomic replacement failure, compare-and-set conflict, secret exclusion, corrupt checkpoint handling, and recovery classification.

Run:

python -m pytest tests/runtime/test_task_store_checkpoint.py
python -m pytest
python main.py

PR title:

feat(runtime): add durable local task checkpoints
```

---

## PR 7：TaskQueue 与单 Worker Scheduler

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 7: add TaskQueue and deterministic single-worker scheduling.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
runtime/event_queue.py, runtime/task_runtime.py, and runtime/task_store.py.

## Preconditions

PR 6 must already be merged. Stop if TaskStore compare-and-set is unavailable.

## Goal

Add a task-id queue and scheduler that claim only READY Tasks while keeping TaskStore as the state source.

## Allowed files

Only create or modify:

runtime/task_queue.py
runtime/task_scheduler.py
tests/runtime/test_task_queue_scheduler.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- TaskQueue stores task_id only.
- Only READY Tasks may enqueue/claim.
- Scheduler performs atomic READY -> RUNNING compare-and-set before returning a Task.
- Duplicate enqueue is idempotent.
- PAUSED, WAITING, UNCERTAIN, KILL_REQUESTED, KILLED, DELIVERED, SUCCEEDED, and FAILED are not normal execution claims.
- Rebuild queue from TaskStore after restart.
- Add a recovery path separate from normal READY claims for restored RUNNING/control-request Tasks.
- First implementation executes serially but must not encode assumptions that prevent a future multi-worker scheduler.
- Do not call SubAgent, Executor, LLM, Tool, Memory, or UI.

## Tests

Test state filtering, duplicate enqueue, CAS conflict, deterministic order, restart rebuild, and separation of recovery work from normal READY claims.

Run:

python -m pytest tests/runtime/test_task_queue_scheduler.py
python -m pytest
python main.py

PR title:

feat(runtime): add task queue and scheduler
```

---

## PR 8：Task 创建前移至 Formulation 之前

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 8: create and persist Task before formulation.

Before making changes, read:

docs/task_step_tool_graph_prd.md
docs/tune.md
runtime/event_runtime.py
agent/main_agent.py
agent/formulation.py
runtime/task_runtime.py
runtime/task_store.py
runtime/task_queue.py

## Preconditions

PR 1 through PR 7 must already be merged.

## Goal

Make the Event/Application boundary create Task(CREATED), formulate under that task_id, then persist READY and enqueue.

## Allowed files

Only create or modify:

runtime/event_runtime.py
agent/main_agent.py
runtime/task_runtime.py
tests/runtime/test_task_creation_formulation_flow.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- After Presence policy allows an event, create Task(CREATED) before formulation.
- Persist CREATED -> FORMULATING before the formulation LLM call.
- Formulation receives task_id/trace_id and writes a complete handoff atomically on success.
- Only a Task with complete goal, constraints, and completion criteria may become READY and enqueue.
- Formulation failure with no safe fallback becomes FAILED and produces a failure delivery payload; it must not enqueue.
- Checkpoint failure prevents the next external LLM/Tool boundary.
- EventRuntime result exposes task_id, not session_id.
- Preserve EventRuntime -> TaskRuntime public flow and default main behavior.
- Do not implement graph execution, pause, or Plan tools yet.

## Tests

Test exact CREATED/FORMULATING/READY ordering, persisted IDs, no READY without handoff, formulation failure, queue submission, and no Session creation.

Run:

python -m pytest tests/runtime/test_task_creation_formulation_flow.py
python -m pytest
python main.py

PR title:

refactor(runtime): create tasks before formulation
```

---

## PR 9：Step ToolGraph 串行协调器

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 9: execute one Step ToolGraph node per runtime tick.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tool_failure_prd.md,
docs/tune.md, sessions/graph.py, sessions/execution_state.py, sessions/executor.py,
tools/manager.py, and runtime/task_runtime.py.

## Preconditions

PR 1 through PR 8 must already be merged.

## Goal

Add a Step coordinator that resolves READY ToolNodes and executes at most one ToolNode per tick.

## Allowed files

Only create or modify:

runtime/step_runtime.py
sessions/executor.py
tests/runtime/test_step_tool_graph_runtime.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- Resolve dependencies from edges only.
- Select one READY ToolNode by edge priority, topological order, then node_id.
- Validate task capability scope, ToolManager live resolution, ToolDefinition metadata/version, ToolNode override, StepToolAvailability, and input schema before invocation.
- Execute exactly one Tool call and pass validated arguments.
- Normalize success, failure, and uncertain into ToolNodeRun/ToolAttempt proposals without mutating Task state directly.
- attempt_index and max_tool_attempts_per_tool_node are scoped to one ToolNodeRun.
- ANY terminal ToolNode success completes Step and marks unused candidate paths SKIPPED.
- All success terminals unreachable with no uncertain fails Step.
- Preserve existing argument-repair active-tool binding and failure observations.
- No internal loop, no SubAgent calls, no Memory writes, no final response generation.

## Tests

Test deterministic READY selection, one Tool per tick, edge-only dependencies, argument propagation, per-node attempts, override validation, ANY terminal success, SKIPPED paths, failure reachability, and uncertain propagation proposal.

Run:

python -m pytest tests/runtime/test_step_tool_graph_runtime.py
python -m pytest
python main.py

PR title:

feat(runtime): execute step tool graphs
```

---

## PR 10：TaskGraph Scheduler 与预算终态

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 10: schedule TaskGraph steps and enforce task budgets.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
sessions/graph.py, sessions/session.py, runtime/step_runtime.py, and runtime/task_runtime.py.

## Preconditions

PR 1 through PR 9 must already be merged.

## Goal

Replace the linear step-number loop with edge-driven TaskGraph scheduling while preserving one decision/action per tick.

## Allowed files

Only create or modify:

runtime/task_runtime.py
tests/runtime/test_task_graph_scheduler.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- TaskRuntime stores/loads Task only through TaskStore.
- Scheduler resolves READY Step nodes from edges only.
- Select one Step deterministically and let one tick produce at most one SubAgent decision and one ToolNode execution.
- TaskGraphRun.node_runs is the active-step fact source; active_step_ids is derived only.
- ANY terminal Step success makes Task SUCCEEDED and marks unused candidate paths SKIPPED.
- No reachable success terminal and no UNCERTAIN makes Task FAILED.
- Enforce independent max_steps, max_tool_attempts_per_tool_node, max_argument_retries, max_runtime_ticks, and max_plan_updates budgets exactly as PRD section 8.5.
- Budget exhaustion produces stable failure codes and Task FAILED, never RUNNING plus a detached max_steps result.
- Persist every accepted transition before the next LLM/Tool boundary.
- Preserve existing completion/memory behavior through compatibility projections, but do not implement new delivery behavior yet.

## Tests

Test edge scheduling, deterministic serial order, one action per tick, ANY success, SKIPPED paths, unreachable failure, every budget independently, active-step derivation, checkpoint-before-next-action, and no linear step_number advancement.

Run:

python -m pytest tests/runtime/test_task_graph_scheduler.py
python -m pytest
python main.py

PR title:

refactor(runtime): schedule task graphs and budgets
```

---

## PR 11：PlanStore 与 plan_written / plan_update

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 11: add versioned plan storage and plan progress tools.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
tools/base.py, tools/manager.py, sessions/graph.py, and runtime/task_store.py.

## Preconditions

PR 1 through PR 10 must already be merged.

## Goal

Add PlanRecord persistence plus ordinary registered tools for creating plan versions and updating progress projections.

## Allowed files

Only create or modify:

runtime/plan_store.py
tools/plan.py
tests/tools/test_plan_tools.py
tests/runtime/test_plan_store.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- PlanRecord keyed by (task_id, version_id), with immutable ordered PlanSteps and projection_status CURRENT/STALE.
- PlanStore uses deterministic versioned local persistence and atomic writes.
- plan_written validates unique steps, independent goals/completion criteria, DAG dependencies, and task/version identity.
- plan_written never accepts an arbitrary file path.
- plan_update accepts task_id/version_id/step_id/expected_old_status/new_status/result_summary and uses compare-and-set.
- plan_update changes progress only; it cannot add/delete/reorder steps or alter dependencies.
- plan_update never mutates TaskGraphRun/StepRun.
- Structure changes require a new version through plan_written; old versions remain immutable.
- Both tools expose complete ToolDefinition schemas and are not globally registered by default in ToolManager constructor.

## Tests

Test plan creation, atomic versioning, invalid DAG, no arbitrary paths, CAS progress update, stale projection, forbidden structure mutation, old-version immutability, and ToolDefinition contracts.

Run:

python -m pytest tests/tools/test_plan_tools.py tests/runtime/test_plan_store.py
python -m pytest
python main.py

PR title:

feat(planning): add versioned plan tools
```

---

## PR 12：PLAN / REACT 分流与 Bootstrap Graph

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 12: route tasks through bootstrap graph into PLAN or REACT execution.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/prompt_prd.md,
docs/tune.md, sessions/subagent.py, prompts/engine.py, runtime/task_runtime.py,
runtime/plan_store.py, and tools/plan.py.

## Preconditions

PR 1 through PR 11 must already be merged.

## Goal

Implement the unique PLAN/REACT decision and remove the plan_written bootstrap cycle.

## Allowed files

Only create or modify:

sessions/subagent.py
prompts/engine.py
prompts/templates.py
runtime/task_runtime.py
app_runtime.py
demo/cli_demo.py
tests/runtime/test_plan_react_bootstrap.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- Before first RUNNING action, create a bootstrap dynamic TaskGraphRun.
- Strategy decision returns mode and estimated_logical_steps.
- PLAN only when task is decomposable and estimate > 5; malformed/missing/<=5 output falls back REACT.
- PLAN first materializes CALL_TOOL(plan_written) in bootstrap graph.
- Missing/unavailable/not-allowed plan_written records plan_tool_unavailable and falls back REACT.
- Application assembly registers plan_written and plan_update once in the long-lived ToolManager; TaskRuntime and SubAgent do not register per task.
- On plan_written success, retain bootstrap graph in history and activate a formal TaskGraphRun from the Plan version.
- REACT uses initial min(5,max_steps) slots and doubles capacity within max_steps; slots are not nodes.
- plan_update records progress only.
- Structural replan creates a new version_id through plan_written, migrates only semantically identical SUCCEEDED nodes, and retains old Plan/Graph/migration mapping.
- SubAgent still returns one decision and never executes tools or mutates graph state.
- Skill does not decide PLAN/REACT.

## Tests

Test PLAN threshold, malformed fallback, bootstrap call, no circular dependency, unavailable plan tool fallback, graph activation/history, REACT capacity, progress-only update, and structural replan version migration.

Run:

python -m pytest tests/runtime/test_plan_react_bootstrap.py
python -m pytest
python main.py

PR title:

feat(runtime): bootstrap plan and react execution
```

---

## PR 13：暂停、恢复与 Kill 控制面

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 13: add durable pause, resume, and kill control commands.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
sessions/session.py, runtime/task_store.py, runtime/task_scheduler.py,
runtime/task_runtime.py, app_runtime.py, and demo/app_runtime.py.

## Preconditions

PR 1 through PR 12 must already be merged.

## Goal

Add idempotent control commands that pause at safe points, resume the real prior stage, and cooperatively kill without restoring KILLED tasks.

## Allowed files

Only create or modify:

runtime/task_runtime.py
runtime/task_scheduler.py
app_runtime.py
demo/app_runtime.py
tests/runtime/test_task_control_commands.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- AppRuntime APIs submit TaskControlCommand with command_id/task_id/type/time/actor/reason.
- Idempotency key is (task_id, command_id).
- PAUSE from CREATED/FORMULATING/READY/RUNNING/WAITING records paused_from_state as the original state, never PAUSE_REQUESTED.
- Pause confirms PAUSED only at documented safe points and after checkpointing sufficient formulation/graph/observation/budget/wait state.
- RESUME returns to paused_from_state: CREATED continues formulation start; FORMULATING continues formulation; READY requeues; RUNNING uses recovery scheduler; WAITING restores its condition.
- KILL has priority over PAUSE. KILL_REQUESTED stops new LLM/Tool calls and becomes KILLED at a safe point.
- KILLED is terminal and never restored into execution.
- Startup recovery completes KILL_REQUESTED to KILLED instead of normal scheduling.
- Do not claim synchronous third-party calls are forcibly interrupted.

## Tests

Test every pause source, stored origin, resume destination/snapshot, command idempotency, invalid-state errors, kill priority, safe-point behavior, KILLED restart behavior, and no repeated completed actions.

Run:

python -m pytest tests/runtime/test_task_control_commands.py
python -m pytest
python main.py

PR title:

feat(runtime): add durable task controls
```

---

## PR 14：WAITING 条件与 Step Tool 熔断

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 14: add durable waiting conditions and step-local tool circuit blocking.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tool_failure_prd.md,
docs/tune.md, sessions/execution_state.py, runtime/task_runtime.py,
runtime/task_scheduler.py, and tools/manager.py.

## Preconditions

PR 1 through PR 13 must already be merged.

## Goal

Implement WaitingCondition wakeups and StepToolAvailability without storing Step state in ToolManager.

## Allowed files

Only create or modify:

runtime/waiting.py
runtime/task_runtime.py
runtime/task_scheduler.py
tests/runtime/test_waiting_and_step_tool_availability.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- WAIT requires WaitingCondition(kind, correlation_key, reason, wake_at, created_at).
- USER_INPUT and EXTERNAL_EVENT wake only on matching correlation_key.
- TIME wakes when wake_at is reached.
- WaitingCondition persists and is re-registered after restart.
- StepToolAvailability is keyed by (step_id, tool_name), with AVAILABLE/BLOCKED.
- Before discovery and execution, expired blocked_until transitions directly BLOCKED -> AVAILABLE and clears block details.
- No HALF_OPEN or health probe in first version.
- blocked_until=None means permanently blocked for that Step.
- If no other path is executable but a required Tool has a future blocked_until, Task enters WAITING until the earliest deadline instead of failing immediately.
- A new Step has independent availability; historical failure remains an observation.
- ToolManager must not store/read StepToolAvailability.

## Tests

Test each waiting kind, correlation filtering, restart registration, timed wakeup, BLOCKED before deadline, direct AVAILABLE after deadline, permanent block, wait-vs-fail behavior, Step isolation, and ToolManager separation.

Run:

python -m pytest tests/runtime/test_waiting_and_step_tool_availability.py
python -m pytest
python main.py

PR title:

feat(runtime): add waiting and step tool blocking
```

---

## PR 15：Uncertain 收口与成功/失败交付

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 15: add uncertain failure resolution and explicit result delivery.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tool_failure_prd.md,
docs/tune.md, sessions/completion.py, agent/final_response.py, runtime/task_runtime.py,
runtime/task_store.py, and sessions/executor.py.

## Preconditions

PR 1 through PR 14 must already be merged.

## Goal

Normalize uncertain Tool outcomes, resolve them only as documented failure, and deliver either success results or failure reports without rerunning the graph.

## Allowed files

Only create or modify:

sessions/executor.py
sessions/completion.py
agent/final_response.py
runtime/task_runtime.py
tests/runtime/test_uncertain_and_delivery.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- Executor uses effective ToolDefinition metadata to classify unconfirmed side effects as ToolAttempt UNCERTAIN.
- ToolNode UNCERTAIN immediately projects Step and Task to UNCERTAIN and stops all ordinary paths.
- Only RESOLVE_UNCERTAIN_AS_FAILED is accepted for UNCERTAIN.
- Resolution performs no Tool, LLM, retry, query, compensation, or rollback.
- Preserve original UNCERTAIN ToolAttempt unchanged; create UncertainResolutionRecord and stable uncertain_outcome_treated_as_failed failure.
- Normalize Task/Step/ToolNode schedulable state to FAILED while explicitly reporting that the external outcome is still unknown.
- SUCCEEDED and FAILED may enter DELIVERED only after DeliveryAttempt success.
- Delivery failure keeps SUCCEEDED/FAILED and permits delivery retry with the exact same payload.
- Delivery retry must not regenerate prompt/LLM response, TaskGraph, or Tool execution.
- Failure payload includes goal, budget/no-path reason, trustworthy observations, failed nodes, user-fixable causes, and unknown side effects.

## Tests

Test uncertain classification, immediate propagation, forbidden ordinary scheduling, resolution with zero external calls, preserved uncertain history, user-visible unknown detail, FAILED->DELIVERED, SUCCEEDED->DELIVERED, failed delivery retry, and no graph rerun.

Run:

python -m pytest tests/runtime/test_uncertain_and_delivery.py
python -m pytest
python main.py

PR title:

feat(runtime): resolve uncertain outcomes and deliver failures
```

---

## PR 16：Append-only 分层 Trace

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 16: add append-only hierarchical task tracing.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
runtime/timing.py, runtime/task_runtime.py, sessions/subagent.py, and sessions/graph.py.

## Preconditions

PR 1 through PR 15 must already be merged.

## Goal

Add task-isolated append-only Trace events and derived Task/Step/ToolNode snapshots without making Trace a Runtime state source.

## Allowed files

Only create or modify:

runtime/trace.py
runtime/task_runtime.py
sessions/subagent.py
tests/runtime/test_hierarchical_trace.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- Append-only TraceRecorder keyed by task_id/trace_id.
- Events for Task transitions, graph activation/version migration, reasoning/LLM, Step transitions, ToolNode/Attempt, waiting, control commands, uncertain resolution, checkpoint, and delivery.
- Derive TaskTraceSnapshot, TaskGraphTrace, TaskNodeTrace, ReasoningTrace, StepTrace, ToolNodeTrace, and ToolAttemptTrace.
- Graph structure uses edges; active steps derive from node_runs.
- Trace effective Tool metadata, StepToolAvailability snapshot, ToolManager resolution, attempts, failure, and timing.
- Remove SubAgent fixed-file overwrite behavior.
- Redact API keys, headers, sensitive paths, raw media, and configured sensitive Tool fields.
- Trace must not write Memory and must never drive state transitions or checkpoint restore.
- RuntimeTiming entries attach to matching trace boundaries instead of duplicating timers.

## Tests

Test append-only behavior, task isolation, deterministic snapshots, graph/version history, attempt traces, redaction, timing association, no fixed-file overwrite, and no reverse state mutation.

Run:

python -m pytest tests/runtime/test_hierarchical_trace.py
python -m pytest
python main.py

PR title:

feat(trace): add hierarchical runtime tracing
```

---

## PR 17：AppRuntime 控制接口与 Web 状态投影

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 17: expose task graph controls and state projections through AppRuntime and Web UI.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
app_runtime.py, demo/app_runtime.py, demo/display_snapshot.py, demo/web_ui.py,
runtime/task_runtime.py, and runtime/trace.py.

## Preconditions

PR 1 through PR 16 must already be merged.

## Goal

Expose submit/query/pause/resume/kill/resolve-uncertain commands and display hierarchical state without letting UI orchestrate Runtime.

## Allowed files

Only create or modify:

app_runtime.py
demo/app_runtime.py
demo/display_snapshot.py
demo/web_ui.py
demo/static/web_ui.html
tests/test_app_runtime_task_controls.py
tests/demo/test_task_graph_web_projection.py

Do not modify any other files. Do not modify __init__.py.

## Implement

- AppRuntime is the only UI-facing application facade.
- Expose submit_text, get_task, pause, resume, kill, and resolve_uncertain_as_failed using TaskControlCommand/Result.
- UI never accesses TaskStore, Queue, Scheduler, SubAgent, Executor, Tool, Provider, Device, or Memory directly.
- Display Task, TaskGraph, active derived Step, Step ToolGraph, attempts, WAITING condition, pause origin, control request, UNCERTAIN details, terminal_outcome, delivery status, and trace/timing summaries.
- Clearly distinguish WAITING, PAUSE_REQUESTED, PAUSED, KILL_REQUESTED, KILLED, UNCERTAIN, FAILED, SUCCEEDED, and DELIVERED.
- A DELIVERED failure must remain visually failed even though delivery succeeded.
- KILLED tasks are not shown as resumable.
- Escape all user/model/tool text and preserve localhost-only default binding.
- Preserve existing text/microphone and frame display paths.

## Tests

Test facade-only calls, command result display, pause/resume origin, killed non-resumability, uncertain details, failed delivery outcome, HTML escaping, localhost binding, and no Runtime bypass.

Run:

python -m pytest tests/test_app_runtime_task_controls.py tests/demo/test_task_graph_web_projection.py
python -m pytest
python main.py

PR title:

feat(app): expose task graph controls and status
```

---

## PR 18：机械迁移最终包所有权

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 18: migrate task/runtime modules to final ownership packages.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
sessions/, runtime/, agent/, and all tests importing sessions.session or sessions.session_manager.

## Preconditions

PR 1 through PR 17 must already be merged.

Stop if any production code still constructs TaskSession as an independent aggregate, stores session_id, or stores state outside TaskStore/GraphRun.

## Goal

Perform a mechanical package migration after behavior is complete while retaining narrow read-only import compatibility for existing external/tests callers.

## Allowed files

Only create, move, or modify:

tasks/__init__.py
tasks/task.py
tasks/state.py
tasks/graph.py
tasks/factory.py
tasks/completion.py
agent/subagent.py
agent/decision.py
agent/strategy.py
runtime/executor.py
runtime/step_runtime.py
runtime/task_runtime.py
runtime/timing.py
sessions/__init__.py
sessions/session.py
sessions/session_manager.py
sessions/execution_state.py
sessions/completion.py
sessions/subagent.py
sessions/decision.py
sessions/strategy.py
sessions/executor.py
agent/final_response.py
app_runtime.py
demo/cli_demo.py
memory/manager.py
tests/test_imports.py
tests/contracts/test_no_session_runtime_contract.py

Do not modify other behavior or unrelated tests. Empty __init__.py files must have no side effects.

## Implement

- Move Task/state/graph/factory/completion to tasks/.
- Move SubAgent/decision/strategy ownership to agent/.
- Keep Executor and Step coordinator in runtime/.
- Update production imports within the allowed set.
- Remove TaskSession, TaskSessionManager, TaskSessionCreation, session_id, and _sessions from production ownership and serialization.
- Compatibility modules may re-export Task/TaskFactory under deprecated import names for one release, but must not define classes, IDs, stores, or mutable state.
- All production imports in the allowed files must use tasks/, agent/, and runtime/ directly after this PR.
- This PR is mechanical: no state transition, scheduling, retry, prompt, Tool, or UI behavior changes.

## Tests

Test final production imports, no Session-owned state in Runtime, no session_id serialization, compatibility re-exports are identity aliases only, no duplicate TaskState/Graph state, and unchanged runtime behavior.

Run:

python -m pytest tests/test_imports.py tests/contracts/test_no_session_runtime_contract.py
python -m pytest
python main.py

PR title:

refactor(project): finalize task runtime ownership
```

---

## PR 19：最终 Task / Step / Tool Graph 契约回归

```text
You are working in the Ella Runtime MVP repository.

Please implement Task Graph PR 19: add final task-step-tool graph contract regression tests.

Before making changes, read docs/task_step_tool_graph_prd.md, docs/tune.md,
tasks/, runtime/, agent/, tools/, app_runtime.py, and demo/web_ui.py.

## Preconditions

PR 1 through PR 18 must already be merged.

Stop if Session compatibility still owns state or if Graph execution remains linear step_number advancement.

## Goal

Verify the complete architecture without introducing new runtime behavior.

## Allowed files

Only create or modify:

tests/contracts/test_task_step_tool_graph_contract.py

Do not modify any production file or __init__.py.

## Contract tests

Cover at minimum:

- Task is the only task aggregate; no session_id/_sessions/TaskSession state source exists. A deprecated identity import alias is not a state source.
- Task creation precedes formulation and READY requires complete handoff.
- TaskStore is the durable source; Queue stores task_id only.
- Graph topology/conditions/priority come only from edges.
- One tick performs at most one decision and one ToolNode execution.
- TaskGraphRun.node_runs is the active-Step source.
- ANY terminal success and SKIPPED alternate paths.
- Independent Task, ToolNode attempt, argument retry, runtime tick, and plan-update budgets.
- Bootstrap plan_written, PLAN threshold >5, REACT fallback, 5-slot doubling, and versioned structural replan.
- ToolDefinition metadata authority and validated overrides.
- StepToolAvailability isolation and direct timed BLOCKED->AVAILABLE.
- Durable WAITING correlation and timed wakeup.
- Pause stores real prior stage and resumes that exact stage with snapshots.
- KILL priority and no KILLED recovery.
- UNCERTAIN stops the graph and resolves only as detailed FAILED.
- SUCCEEDED/FAILED delivery never reruns graph/LLM/Tool.
- Trace is append-only, redacted, task-isolated, and not a state source.
- App/Web use only facade commands and preserve mock-safe main execution.

Run:

python -m pytest tests/contracts/test_task_step_tool_graph_contract.py
python -m pytest
python main.py

## Final response

Include changed file, exact contracts covered, intentionally unchanged production behavior, and exact test results.

PR title:

test(contracts): verify task step tool graph runtime
```

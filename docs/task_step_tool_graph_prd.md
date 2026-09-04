> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella Task / Step / Tool 图执行与分层状态 PRD

## 1. 文档信息

- 功能名称：Task / Step / Tool Graph Execution and Hierarchical State
- 适用范围：Ella Agent Runtime
- 文档状态：已确认架构基线，待按阶段实施
- 文档目标：在不建立重复状态来源的前提下，将现有线性 TaskRuntime 升级为 Task Graph 与 Step Tool Graph 执行模型，并定义可暂停、恢复、终止、重试、不确定性处理和分层 Trace 契约。

## 2. 背景与目标

Ella 当前已经具备一条可运行的单任务执行链：

```text
EventRuntime
  -> MainAgent / TaskFormulator
  -> HandoffRequest
  -> TaskRuntime.submit()
  -> Task
  -> SubAgent 产生一个 ExecutionDecision
  -> CapabilityExecutor 最多执行一个 Tool
  -> TaskRuntime 继续下一次 step()
```

当前模型已经支持：

- Task 基础状态机。
- 单次 `TaskRuntime.step()` 最多一个动作。
- `StepExecutionState` 中的参数修复次数、active Tool、Step 黑名单与失败记录。
- Tool 输入/输出 Schema 校验。
- Tool 失败归一化为 `ToolFailureObservation`。
- TaskRuntime 持有执行循环与 `max_steps` 上限。

但当前 `StepExecutionState` 本质上仍是“一次动作及参数重试”状态，不是真正的 Step Graph；TaskRuntime 也没有 Task Graph、Task Queue、暂停/恢复和 uncertain 处理边界。

本 PRD 的最终目标是：

```text
Task 拥有 Task Graph 和 TaskState
  -> Task Graph 的执行节点是 Step
  -> Step 拥有 Tool Graph 和 StepState
  -> Tool Graph 的执行节点是 ToolNode
  -> ToolNode 拥有 ToolNodeState 和 Attempt 历史
```

## 3. 现有实现审计

### 3.1 已有能力，禁止重复实现

| 已有内容 | 当前位置 | 本 PRD 的处理 |
| --- | --- | --- |
| Task 状态与转移校验 | `sessions/session.py` | 原位升级，不新建第二套 TaskState |
| Task 本地 Step 状态 | `sessions/execution_state.py` | 演进为 Step aggregate，保留参数重试契约 |
| Tool 失败分类 | `ToolFailureKind` | 保留并扩展，不再建平行枚举 |
| Tool 失败观测 | `ToolFailureObservation` | 作为 Tool Attempt 失败的标准记录 |
| Tool 参数修复与 active Tool 锁定 | `TaskRuntime._handle_failure()` | 下沉到 ToolNode/Attempt 边界，语义保持 |
| Step 黑名单 | `StepExecutionState.blacklisted_tools` | 迁移为 `StepToolAvailability` 的派生视图，不保留第二份可变集合 |
| 单动作 Executor | `CapabilityExecutor` | 继续一次只执行一个 ToolNode，不在 Executor 内建立循环 |
| Runtime 循环预算 | `TaskRuntime.run_until_blocked()` | 升级为 Task/Step/Attempt 多层预算 |
| 成功 Tool 观测 | `TaskSession.tool_trace` | 随 `TaskSession -> Task` 迁移，并改为 ToolNode Attempt 记录的派生视图 |
| Runtime timing | `runtime/timing.py` | 与新 Trace 关联，不重复计时 |

### 3.2 当前缺失的核心能力

- 没有 Task Queue；`TaskRuntime` 仅用 dict 保存 Task，AppRuntime 同步指定 `task_id` 运行。
- 没有“SubAgent 从 Queue 领取 READY Task”的调度器。
- 没有 Task Graph 或 Step Graph 数据契约。
- 没有 Step 内 Tool Graph 数据契约。
- 没有 Task/Step/ToolNode 分层状态机。
- 没有 pause request、resume、kill request 的控制 API。
- 没有 uncertain 状态及其专用恢复流程。
- 没有 Tool 幂等性/副作用元数据，Runtime 无法可靠判断 uncertain。
- 没有 Tool 全局可用性与熔断冷却的统一目录。
- 当前 Trace 不是按 Task 追加写入；SubAgent 会覆盖固定的 `trace/trace.json`。

### 3.3 现有语义与新设计的冲突

#### Task 创建时机冲突

当前数据流是：

```text
TaskFormulator 完成 goal
  -> 创建 HandoffRequest
  -> TaskRuntime.submit()
  -> TaskSessionManager 创建 TaskSession(CREATED)
```

因此现有 `TaskSession.CREATED` 已经发生在 formulation 之后，无法如实表示 `CREATED -> FORMULATING -> READY`。

本 PRD 要求同时调整命名和创建边界：删除运行时的 `Session` 概念，将 `TaskSession` 收口为唯一 `Task` 聚合。当 Event 通过 Presence Policy 并准备建立任务时，先创建拥有 `task_id` 和 `trace_id` 的 Task，再进入 formulation。`handoff` 在 FORMULATING 完成前可为空，但 READY Task 必须已经具备完整 handoff。

#### Task 与 Session 概念重复

当前 `TaskSessionManager.create_session()` 会为一个 HandoffRequest 同时创建 `task_id` 和 `session_id`，`TaskRuntime._tasks` 与 `TaskRuntime._sessions` 最终指向同一个 `TaskSessionCreation`。当前没有实现：

- 一个 Task 对应多个 Session。
- Session 独立生命周期。
- Session 独立恢复或独立调度。
- Session 与 Task 之间的明确归属关系。

因此当前 `TaskSession` 实际上就是 Task 的运行实体，`session_id` 是与 `task_id` 重复的标识。本 PRD 做出以下收口：

- 将 `TaskSession` 重命名为 `Task`。
- 删除 Task 领域中的 `session_id`。
- 删除 `TaskRuntime._sessions` 重复索引。
- 删除 `TaskSessionCreation` 包装，将 Task 和任务本地 `AgentExecutionContext` 由单一 Task 创建结果或 Task 对象直接持有。
- pause/resume 恢复的是同一个 Task，不新建 Session。
- 进程重启后恢复的也是同一个 `task_id`。

如果未来真正需要“同一个 Task 的多次独立执行”，应在独立 PRD 中引入 `run_id` 和 `TaskRun`，不恢复语义模糊的 Session。

#### `submit` 名称冲突

当前 `TaskRuntime.submit()` 表示任务入队/注册。附件设计又将 `submit` 用作“结果已发送给用户”。两个语义不能共用同一名称。

本 PRD 统一为：

- `submit/enqueue`：操作名，表示 READY Task 进入调度队列。
- `DELIVERED`：Task 状态，表示成功结果已交付给用户。

#### `WAITING` 与 `PAUSED` 冲突

当前 `WAITING` 是 SubAgent 主动返回 WAIT 后的阻塞状态。用户请求暂停属于控制面行为，不应与 WAIT 混为一类。

- `WAITING`：等待外部输入或条件，是 Agent 执行结果。
- `PAUSE_REQUESTED`：收到暂停请求，但当前安全点尚未确认。
- `PAUSED`：已在安全点停止推进，可恢复。

#### `KILLED` 语义冲突

用户发送 kill 时，如果 LLM/Tool 同步调用正在运行，Runtime 无法立即声称已终止。因此必须区分：

- `KILL_REQUESTED`：终止请求已记录，等待达到安全点。
- `KILLED`：Runtime 已确认不会再发起新的 LLM/Tool 调用。

第一版采用 cooperative cancellation，不承诺强制中断已经进入的第三方阻塞调用。

#### Tool 注册、Step 调用资格与 ToolNode 状态冲突

现有表述容易把三种不同事实都称为“Tool 可用性”。本 PRD 将它们严格拆开：

1. `ToolManager` 保存进程内已注册 Tool，并负责按任务权限与实时设备/Provider 条件解析 Tool。它不拥有任何 Step 状态。
2. `StepToolAvailability` 表示某个 Tool name 在某个 `StepRun` 内是否仍可再次选择，以及最早允许再次选择的时间。它用于 Step 级黑名单、冷却和局部熔断。
3. `ToolNodeState` 表示某个具体 ToolNode 实例的执行生命周期，如 `READY/RUNNING/SUCCEEDED`。

三者不得互相包含或互相充当事实来源。`ToolManager` 不保存 `StepToolAvailability`；`StepRun` 不保存 Tool 实例或进程注册表；`ToolNodeRun` 不改写同名 Tool 在其他 Step 中的资格。


## 4. 设计原则

1. **单一事实来源**：Task、Step、ToolNode 各自只有一个可变状态所有者。
2. **状态分层**：上层状态由下层状态和显式控制事件推导，但不通过多份字段同步。
3. **图与运行状态分离**：GraphDefinition 是不可变结构；GraphRun 保存节点运行状态。
4. **状态变更受控**：不允许 UI、SubAgent、Tool 直接赋值上层 state，必须通过 Runtime 命令和转移校验。
5. **安全点控制**：pause/kill 只在可确认不会丢失执行结果的安全点生效。
6. **Uncertain 优先**：一旦出现不可确定的副作用，禁止执行其他图路径，直到不确定性被解决。
7. **Trace 不反向驱动 Runtime**：Trace 是执行事件的只读投影，不是另一套状态存储。
8. **默认串行**：图允许表达多个 READY 节点，第一版调度器仍按确定性顺序一次执行一个，不引入并发安全问题。
9. **术语不可复用**：同一个名称不得同时表示进程能力状态、Step 内调用资格和 ToolNode 执行状态。
10. **预算先于扩容**：图容量扩展只提供记录空间，绝不扩大 `max_steps`、attempt 或 argument retry 预算。
11. **Plan 也是受控能力**：规划的创建和更新通过注册 Tool 完成，仍受 capability scope、Schema 校验、单动作执行和失败策略约束。

### 4.1 规范性用语

为避免实现者对要求强度产生不同理解，本文统一使用：

- **必须 / 不得**：验收所必需的行为，不允许实现自行取舍。
- **应当**：默认实现要求；若无法满足，必须在对应 PR 中记录原因和兼容方案。
- **可以**：允许但非必需，不得据此改变其他强制契约。
- **第一版**：本 PRD 各 Phase 完成后的最小目标，不代表可以绕开强制边界。

本文中的 `tick` 指一次 TaskRuntime 调度推进：最多产生一个 SubAgent decision，最多执行一个 ToolNode，并在返回前持久化本次状态变化。`attempt` 指一次已实际发起的 Tool 调用；参数校验失败属于 decision/validation attempt，不属于 Tool attempt。

## 5. 分层领域模型

### 5.1 Task：唯一任务与运行聚合

`Task` 同时表示用户要完成的目标以及该目标的当前运行聚合。它是 Task 生命周期的唯一可变状态所有者。不再建立 `TaskSession`、`TaskRun` 或 `TaskStatusStore` 与之平行保存同一份运行状态。

必须实现以下等价数据契约；字段可以按仓库命名规范调整，但语义和所有权不得改变：

```python
Task
- task_id: str
- conversation_id: str | None
- trace_id: str
- source_event: StandardizedEvent
- handoff: HandoffRequest | None
- state: TaskState
- execution_context: AgentExecutionContext
- graph: TaskGraphRun | None
- waiting_condition: WaitingCondition | None
- paused_from_state: TaskState | None
- completion: TaskCompletionPackage | None
- terminal_outcome: SUCCEEDED | FAILED | None
- failure_reason: str | None
- uncertain_resolution: UncertainResolutionRecord | None
- delivery: TaskDeliveryRecord | None
- control_request: TaskControlRequest | None
- created_at / updated_at
```

`state` 表示 Task 当前生命周期位置，`terminal_outcome` 保留 Task Graph 的最终业务结论。Task 从 SUCCEEDED 或 FAILED 进入 DELIVERED 后，`terminal_outcome` 不得被 DELIVERED 覆盖。

创建时字段规则必须固定：

- `CREATED` 时 `handoff=None`、`graph=None`、`completion=None`、`terminal_outcome=None`。
- formulation 成功后必须一次性写入完整 `handoff`；不得让缺少 goal 或 completion criteria 的 Task 进入 READY。
- Task 在首次进入 RUNNING 前统一创建 bootstrap dynamic `TaskGraphRun`。REACT 继续在该 GraphRun 中追加动态节点；PLAN 先在 bootstrap graph 中物化并执行 `plan_written` ToolNode，成功后再将 Task 的 active graph 切换为对应 Plan 版本生成的正式 TaskGraphRun。bootstrap graph 必须作为历史保留在 Trace/checkpoint 中，不得被覆盖。
- `active_step_ids` 不作为 Task 可变字段保存，只能由 `TaskGraphRun.node_runs` 中处于 READY/RUNNING/PAUSED 的 Step 节点推导。第一版串行调度时，处于 RUNNING 的 Step 最多一个。
- `execution_context` 在 Task 创建时建立任务本地权限快照；后续新增 Tool 不自动进入该 Task scope，Tool 删除或实时不可用仍在执行前重新校验。

### 5.2 标识符语义

| 标识符 | 语义 | 是否必需 |
| --- | --- | --- |
| `conversation_id` | 用户与 Ella 的一段连续对话，可包含多个 Task | 否 |
| `task_id` | 一个需要完成的用户目标及其完整生命周期 | 是 |
| `trace_id` | 跨 Event、LLM、Tool 和交付边界关联观测数据 | 是 |

`conversation_id` 不拥有 Task 状态，`trace_id` 不拥有 Runtime 状态。`task_id` 是查询、暂停、恢复、kill 和 checkpoint restore 的唯一业务标识。

### 5.3 TaskGraph

```python
TaskGraphDefinition
- graph_id: str
- version: str
- nodes: tuple[TaskGraphNodeDefinition, ...]
- edges: tuple[GraphEdge, ...]
- entry_node_ids: tuple[str, ...]
- terminal_node_ids: tuple[str, ...]

TaskGraphNodeDefinition
- node_id: str
- node_type: REASONING | STEP
- payload: ReasoningDefinition | StepDefinition

GraphEdge
- from_node_id: str
- to_node_id: str
- condition: GraphCondition | None
- priority: int

TaskGraphRun
- definition: TaskGraphDefinition
- node_runs: Mapping[str, TaskNodeRun]
```

Graph 必须是 DAG。注册时必须校验：

- node id 唯一。
- edge 引用存在的 node。
- 不存在环。
- entry/terminal node 有效。
- 条件表达式不允许执行任意 Python 代码。

`edges` 是 Graph 拓扑、分支条件和调度优先级的唯一事实来源。节点依赖、前驱、后继和拓扑顺序必须从 `edges` 计算，不得在 NodeDefinition 中再保存可独立修改的 `dependencies/condition/priority`。

### 5.4 StepRun

`StepExecutionState` 从单纯的 retry DTO 升级为某个 Step 的运行聚合，但必须保留当前参数修复语义。

```python
StepRun
- step_id: str
- state: StepState
- tool_graph: ToolGraphRun
- current_attempt_id: str | None
- tool_availability: Mapping[str, StepToolAvailability]
- failures: tuple[ToolFailureObservation, ...]
- started_at / finished_at
```

当前 `step_number/retry_index/max_argument_retries/active_tool_name` 不应丢失，但应明确迁移为 StepRun 与 ToolNodeAttempt 的派生字段，避免 `StepExecutionState` 同时代表 Step 和 Tool argument retry。Step 总 ToolAttempt 数只能由各 ToolNodeRun.attempts 聚合得到，不单独保存第二份可变计数。

### 5.5 ToolGraph 与 ToolNodeRun

```python
ToolGraphDefinition
- graph_id: str
- nodes: tuple[ToolNodeDefinition, ...]
- edges: tuple[GraphEdge, ...]
- entry_node_ids: tuple[str, ...]
- terminal_node_ids: tuple[str, ...]

ToolNodeDefinition
- node_id: str
- tool_name: str
- tool_version: str
- input_binding: Mapping[str, InputBinding]
- success_condition: GraphCondition | None
- execution_override: ToolExecutionOverride | None

ToolNodeRun
- node_id: str
- state: ToolNodeState
- resolved_arguments: Mapping[str, Any]
- attempts: tuple[ToolAttempt, ...]
- output: ToolResult | None
- failure: ToolFailureObservation | None
- started_at / finished_at
```

`input_binding` 只能引用 Task input、Step input 或前置 ToolNode 的规范化 output，不允许直接引用 Tool 实例、Provider 或本地运行资源。

ToolGraph 同样只以 `edges` 表示依赖。`ToolDefinition(name, version)` 是 idempotency、side effect 和 uncertain policy 的事实来源。`execution_override` 只能覆盖 ToolDefinition 明确声明为 `overridable` 的字段，并必须在 Graph 注册时由 ToolManager 校验；未通过校验的 Graph 不得运行。ToolNodeRun 必须保存最终生效元数据的只读快照，保证执行后可审计。

### 5.6 ToolAttempt

```python
ToolAttempt
- attempt_id: str
- attempt_index: int
- arguments: Mapping[str, Any]
- state: RUNNING | SUCCEEDED | FAILED | UNCERTAIN
- result: ToolResult | None
- failure: ToolFailureObservation | None
- started_at / finished_at
```

Tool retry 计数属于 ToolNodeRun/ToolAttempt，不属于进程级 ToolDefinition，也不在 ToolManager 全局共享。
`attempt_index` 从 1 开始，并且只在同一个 ToolNodeRun 内递增；不同 ToolNode 即使引用同名 Tool，也拥有独立 attempt 预算。

### 5.7 StepToolAvailability：Step 内 Tool 调用资格

```python
StepToolAvailability
- step_id: str
- tool_name: str
- state: AVAILABLE | BLOCKED
- blocked_reason: str | None
- blocked_until: datetime | None
- updated_at: datetime
```

该对象只属于一个 `StepRun`，键为 `(step_id, tool_name)`，作用范围在 Step 结束时终止：

- `BLOCKED` 表示该 Tool 在当前 Step 熔断，不得被 SubAgent 选择。
- `blocked_until` 表示当前 Step 内熔断截止时间。每次准备可见 ToolDefinition 或执行 Tool 前，Runtime 必须使用单调时钟对应的截止时间检查该字段。
- 当前时间未达到 `blocked_until` 时保持 BLOCKED；达到或超过后，直接转为 AVAILABLE，并清空 `blocked_reason/blocked_until`。第一版不使用 HALF_OPEN，也不执行额外健康探测。
- `blocked_until=None` 的 BLOCKED 表示当前 Step 永久熔断，直到该 Step 结束。
- 新 Step 默认创建独立 AVAILABLE 状态，不继承前一 Step 的 BLOCKED，但必须把前一 Step 的失败作为 observation 提供给决策层。
- ToolManager 的注册、权限与实时依赖检查始终优先。即使 StepToolAvailability.state 为 AVAILABLE，未注册、无权限或实时依赖不可用的 Tool 仍不得执行。
- StepToolAvailability 不得存入 ToolManager，也不得成为其他 Task/Step 的共享对象。

### 5.8 PlanRecord 与动态 Graph 容量

```python
PlanRecord
- task_id: str
- version_id: str
- steps: tuple[PlanStep, ...]
- created_at: datetime
- updated_at: datetime
- projection_status: CURRENT | STALE

PlanStep
- step_id: str
- goal: str
- status: PENDING | RUNNING | SUCCEEDED | FAILED | SKIPPED
- dependencies: tuple[str, ...]
- result_summary: str | None
```

Plan 由 `PlanStore` 按 `(task_id, version_id)` 唯一保存。模型和 Tool schema 只传结构化 `task_id/version_id/steps`，不得自行生成任意文件路径。文件系统只是第一版 PlanStore 的存储实现，不属于领域契约。

`PlanRecord` 是用户可读计划文档，不是 Runtime state 的事实来源。TaskGraphRun/StepRun 始终决定哪些节点可执行以及任务是否结束。`PlanStep.status` 只能投影对应 StepRun 的已确认状态；两者不一致时必须标记 `projection_status=STALE`，调度器不得读取 PlanRecord 来覆盖 Runtime state。

无 Plan 的 ReAct Graph 使用容量字段管理动态节点记录：

```python
DynamicGraphCapacity
- allocated_slots: int
- used_slots: int
- max_slots: int
```

- 初始化 `allocated_slots = min(5, max_steps)`。
- 容量耗尽且预算仍允许下一逻辑 Step 时，扩容为 `min(allocated_slots * 2, max_steps)`。
- 未使用 slot 不是 GraphNode，不参与依赖、READY、成功或失败判定。
- 达到 `max_slots/max_steps` 后不得继续扩容，未完成 Task 按预算耗尽规则进入 FAILED。

### 5.9 控制命令契约

所有应用层控制命令必须包含幂等键，并通过 `AppRuntime -> TaskRuntime` 提交：

```python
TaskControlCommand
- command_id: str
- task_id: str
- command_type: PAUSE | RESUME | KILL | RESOLVE_UNCERTAIN_AS_FAILED
- requested_at: datetime
- actor: str
- reason: str | None
```

```python
WaitingCondition
- kind: USER_INPUT | EXTERNAL_EVENT | TIME
- correlation_key: str
- reason: str
- wake_at: datetime | None
- created_at: datetime
```

```python
TaskControlResult
- command_id: str
- task_id: str
- accepted: bool
- previous_state: TaskState
- current_state: TaskState
- code: str
- message: str
```

- `(task_id, command_id)` 唯一；重复提交必须返回首次处理结果，不得重复转移状态。
- `accepted=True` 只表示命令已持久化或完成，不代表同步外部调用已被强制中断。
- 状态不允许该命令时返回 `accepted=False, code="command_not_allowed_in_state"`，不得静默忽略。
- `RESOLVE_UNCERTAIN_AS_FAILED` 只接受处于 UNCERTAIN 的 Task。
- UI 不得自行推断成功，必须展示 `TaskControlResult.current_state`。
- 接受 PAUSE 时必须在 `paused_from_state` 保存请求到达前的真实执行阶段，如 FORMULATING、READY、RUNNING 或 WAITING；不得保存 PAUSE_REQUESTED。
- WAIT 必须同时写入完整 WaitingCondition。USER_INPUT/EXTERNAL_EVENT 由 correlation_key 匹配事件唤醒；TIME 由 `wake_at` 到期唤醒。无法构造等待条件时不得进入 WAITING。

### 5.10 TaskStore 与本地 Checkpoint

第一版不要求数据库，但必须实现本地持久化 checkpoint，才能满足“进程退出后恢复同一个 Task”的产品语义：

- TaskStore 是 Task 聚合的唯一持久化接口；内存索引只是 TaskStore 的进程内缓存。
- 每次有效状态转移、GraphRun 变化、ToolAttempt 落定、控制命令接受和 DeliveryAttempt 完成后，必须以原子替换方式保存完整 Task checkpoint。
- checkpoint key 为 `task_id`，内容必须包含 schema version、Task state、GraphRun、预算、control request、uncertain detail 和 delivery record。
- Prompt 全文、API key、Provider client、Tool 实例和原始媒体不得进入 checkpoint。
- 进程启动时扫描未终结 Task：READY 重新入队；PAUSED 载入恢复所需快照但保持 PAUSED；WAITING 重新注册 WaitingCondition；UNCERTAIN 保持原状态；SUCCEEDED/FAILED 只恢复交付；DELIVERED/KILLED 不恢复执行也不入队。
- 恢复 RUNNING/KILL_REQUESTED/PAUSE_REQUESTED Task 时，必须先检查是否存在未落定的 ToolAttempt：
  - RUNNING 且没有未落定 ToolAttempt：加载 GraphRun/预算/observation 后恢复为 RUNNING，并由恢复调度器从已持久化安全点继续，不重新执行已完成动作。
  - PAUSE_REQUESTED：完成当前安全点持久化后转 PAUSED，`paused_from_state` 使用暂停请求到达前保存的真实阶段。
  - KILL_REQUESTED：恢复协调器直接完成终止收口并转 KILLED，不恢复普通执行。
  - 存在未落定且可能有副作用的 ToolAttempt：恢复为 UNCERTAIN。
  - 存在未落定、明确幂等且未确认发起成功的 ToolAttempt：记录恢复 observation 后回到 READY；是否重试仍由下一决策决定。
- checkpoint 写入失败时不得继续发起下一个 LLM/Tool 调用；Task 保持最近一次已持久化状态，并返回 `checkpoint_write_failed`。

## 6. 状态契约

### 6.1 TaskState

```text
CREATED
FORMULATING
READY
RUNNING
WAITING
PAUSE_REQUESTED
PAUSED
KILL_REQUESTED
SUCCEEDED
FAILED
UNCERTAIN
KILLED
DELIVERED
```

语义：

| 状态 | 语义 |
| --- | --- |
| `CREATED` | Task id/trace id 已创建，尚未开始 goal formulation |
| `FORMULATING` | 正在建立 goal、constraints 和 completion criteria |
| `READY` | handoff 完整，且可被 Task Scheduler 领取 |
| `RUNNING` | 任务已被 worker/SubAgent 执行链领取并正在推进 |
| `WAITING` | Agent 主动等待用户输入或外部条件 |
| `PAUSE_REQUESTED` | 暂停请求已记录，尚未到安全点 |
| `PAUSED` | 已在安全点暂停，不可被 READY scheduler 领取 |
| `KILL_REQUESTED` | 终止请求已记录，等待安全点确认 |
| `SUCCEEDED` | 任务目标达成，结果已生成，但尚未确认交付 |
| `FAILED` | Task Graph 已确认任务无法达成，或 uncertain resolution 已按失败收口；错误信息可待交付 |
| `UNCERTAIN` | 存在未确认的副作用，禁止继续普通调度 |
| `KILLED` | Runtime 已确认任务不会再发起新执行 |
| `DELIVERED` | Task 的成功结果或失败错误报告已成功发送给用户；实际结论由 `terminal_outcome` 保留 |

`KILLED` 和 `DELIVERED` 是终态。`SUCCEEDED` 和 `FAILED` 是 Task Graph 的终结论，但在用户可见结果交付完成前不是整个 Task 生命周期的最后状态。交付失败时应保留成功结果或失败报告并允许重试交付，不得重新执行 Task Graph。

### 6.2 StepState

```text
PENDING
READY
RUNNING
PAUSED
SUCCEEDED
FAILED
UNCERTAIN
KILLED
SKIPPED
```

- `PENDING`：前置 Step 未满足。
- `READY`：依赖和条件已满足。
- `RUNNING`：Step 正在调度 Tool Graph。
- `PAUSED`：Task 在安全点暂停时，当前未完成 Step 的投影状态。
- `SUCCEEDED`：Tool Graph 已到达成功终点。
- `FAILED`：已无成功路径，且不存在 UNCERTAIN ToolNode。
- `UNCERTAIN`：任一 ToolNode 进入 UNCERTAIN。
- `KILLED`：Task 终止时当前未完成 Step 被终止。
- `SKIPPED`：其他 terminal 路径已成功或入边条件确定为 false，因此该 Step 永远不会执行。

### 6.3 ToolNodeState

```text
PENDING
READY
RUNNING
SUCCEEDED
FAILED
UNCERTAIN
SKIPPED
```

单个 Tool 调用第一版不支持 PAUSED。已进入 RUNNING 的 ToolAttempt 要么返回 SUCCEEDED/FAILED/UNCERTAIN，要么由外层 timeout 归一化。`SKIPPED` 只适用于尚未进入 RUNNING 且因分支条件或其他 terminal 成功而不再需要的 ToolNode。

## 7. Task 状态转移

除本节列出的转移外，所有 TaskState 转移都必须被拒绝并返回结构化 `invalid_state_transition`。状态更新与引发该更新的领域事件必须在同一持久化事务内完成。

### 7.1 正常路径

```text
CREATED
  -> FORMULATING
  -> READY
  -> RUNNING
  -> SUCCEEDED
  -> DELIVERED
```

Formulation 失败且无安全 fallback 时：

```text
FORMULATING -> FAILED -> DELIVERED
```

Task Graph 失败时：

```text
RUNNING -> FAILED -> DELIVERED
```

`FAILED -> DELIVERED` 不代表失败被改成成功，只代表失败详情已成功发送给用户。

### 7.2 暂停与恢复

```text
CREATED | FORMULATING | READY | RUNNING | WAITING
  -> PAUSE_REQUESTED
  -> PAUSED(paused_from_state=<original state>)
  -> <paused_from_state>
```

暂停请求必须幂等。即使 Task 已位于安全点，也必须先记录 PAUSE_REQUESTED，再在同一命令处理中确认 PAUSED，以便 Trace 保留控制事件。`paused_from_state` 必须取暂停请求到达前的状态，禁止记录为 PAUSE_REQUESTED。恢复必须回到 `paused_from_state`，不得统一转 READY，也不得清空 TaskGraphRun、formulation snapshot、StepRun、ToolAttempt、observations 或 retry 预算。

恢复后的推进规则：

- CREATED：继续 START_FORMULATION。
- FORMULATING：从 formulation checkpoint 继续；若 Provider 不支持调用内恢复，则复用已完成输入快照重新发起该 formulation LLM 调用，并记录新的 attempt。
- READY：重新入 TaskQueue。
- RUNNING：由 recovery scheduler 从最近安全点继续，不经 READY 队列重新领取。
- WAITING：恢复 WaitingCondition 注册，条件未满足前不执行。

### 7.3 终止

```text
CREATED | FORMULATING | READY | RUNNING | WAITING | PAUSE_REQUESTED | PAUSED
  -> KILL_REQUESTED
  -> KILLED
```

对于尚未发起外部调用的 CREATED/READY/PAUSED/WAITING Task，kill 可以立即确认为 KILLED。对 RUNNING Task，在下一个安全点确认。

`SUCCEEDED`、`FAILED`、`UNCERTAIN` 和 `DELIVERED` 不接受 kill：前两者只允许交付，UNCERTAIN 只允许 uncertain resolution，DELIVERED 已结束。重复 kill KILLED Task 返回当前状态并视为幂等成功。

### 7.4 Uncertain

任一 ToolNode 产生 UNCERTAIN 时：

```text
ToolNode.UNCERTAIN
  -> Step.UNCERTAIN
  -> Task.UNCERTAIN
```

Task.UNCERTAIN 时：

- 不调度其他 Step/Tool 路径。
- 不自动重试非幂等 Tool。
- 只允许执行显式 uncertain resolution 命令。

第一版 uncertain resolution 不执行任何额外外部操作，而是使用确定的失败收口命令：

```text
Task.UNCERTAIN
  -> receive RESOLVE_UNCERTAIN_AS_FAILED
  -> ToolNode.FAILED
  -> Step.FAILED
  -> Task.FAILED
  -> build uncertain failure report
  -> Task.DELIVERED
```

命令行为必须满足：

- 不调用额外 Tool。
- 不调用 LLM 判断外部操作是否成功。
- 不自动重试、查询、补偿或回滚原操作。
- 将当前 ToolNode、Step 和 Task 的可调度状态收口为 FAILED。
- 原 ToolAttempt 的 `UNCERTAIN` 历史必须永久保留，不得改写成“外部操作已确认失败”。
- 新增 `UncertainResolutionRecord(resolution="treated_as_failed")`，记录原 Tool、输入、调用时间、timeout/断连原因、可能已产生的副作用和处理时间。
- `failure_reason` 使用稳定代码 `uncertain_outcome_treated_as_failed`。
- 用户可见报告必须明确说明：Task 已按失败结束，但外部操作的真实结果仍然未知，不得宣称该外部操作已确认失败。

### 7.5 结果交付

Task 交付使用独立记录：

```python
TaskDeliveryRecord
- outcome: SUCCEEDED | FAILED
- payload_type: SUCCESS_RESULT | FAILURE_REPORT | UNCERTAIN_FAILURE_REPORT
- payload: UserVisibleAgentOutput
- attempts: tuple[DeliveryAttempt, ...]
- delivered_at: datetime | None
```

状态转移：

```text
SUCCEEDED -> DELIVERED(terminal_outcome=SUCCEEDED)
FAILED    -> DELIVERED(terminal_outcome=FAILED)
```

- DELIVERED 表示信息交付成功，不表示 Task Graph 执行成功。
- 交付失败时，Task 保持 SUCCEEDED 或 FAILED，记录 DeliveryAttempt 并允许重试交付。
- 交付重试不得重新生成 Task Graph、重新调用 LLM 决策或重新执行 Tool。
- 对 FAILED Task，交付内容是用户可理解的错误报告，不能只暴露 `max_steps`、内部枚举或异常堆栈。

### 7.6 完整事件转移表

| 当前状态 | 事件/命令 | 前置条件 | 下一状态 | 必须产生的记录 |
| --- | --- | --- | --- | --- |
| CREATED | START_FORMULATION | 无待处理 kill/pause | FORMULATING | formulation trace start |
| FORMULATING | FORMULATION_SUCCEEDED | handoff 完整 | READY | handoff、queue entry |
| FORMULATING | FORMULATION_FAILED | 无安全 fallback | FAILED | failure observation |
| READY | CLAIM_TASK | scheduler 原子领取成功 | RUNNING | claim event、queue wait timing |
| RUNNING | DECISION_WAIT | 给出明确等待原因/条件 | WAITING | waiting condition |
| WAITING | RESUME_CONDITION_MET | 外部输入或条件已到达 | READY | resume event、queue entry |
| RUNNING | GRAPH_SUCCEEDED | 成功终点已满足 | SUCCEEDED | completion payload、terminal_outcome |
| RUNNING | GRAPH_FAILED | 预算耗尽或成功路径不可达 | FAILED | failure payload、terminal_outcome |
| RUNNING | TOOL_OUTCOME_UNCERTAIN | 未确认副作用已持久化 | UNCERTAIN | uncertain attempt/detail |
| CREATED/FORMULATING/READY/RUNNING/WAITING/PAUSE_REQUESTED/PAUSED | REQUEST_KILL | 非结果终结状态 | KILL_REQUESTED | control request |
| KILL_REQUESTED | REACH_SAFE_POINT | 已持久化当前边界结果 | KILLED | kill confirmation |
| CREATED/FORMULATING/READY/RUNNING/WAITING | REQUEST_PAUSE | 尚未终结 | PAUSE_REQUESTED | control request、paused_from_state=原状态 |
| PAUSE_REQUESTED | REACH_SAFE_POINT | 已持久化当前边界结果，paused_from_state 有效 | PAUSED | pause confirmation、恢复快照 |
| PAUSED | REQUEST_RESUME | 无 kill request且 paused_from_state 有效 | paused_from_state | resume event；仅恢复为 READY 时写 queue entry |
| UNCERTAIN | RESOLVE_UNCERTAIN_AS_FAILED | uncertain detail 完整 | FAILED | resolution record、failure payload |
| SUCCEEDED | DELIVERY_SUCCEEDED | 成功响应已发送 | DELIVERED | delivery attempt、terminal_outcome=SUCCEEDED |
| FAILED | DELIVERY_SUCCEEDED | 错误报告已发送 | DELIVERED | delivery attempt、terminal_outcome=FAILED |
| SUCCEEDED/FAILED | DELIVERY_FAILED | payload 保持不变 | 原状态 | failed delivery attempt |

控制请求优先级固定为 `KILL > PAUSE > 普通调度`。若 pause 和 kill 在同一安全点前先后到达，以 kill 为准；PAUSE_REQUESTED 可转 KILL_REQUESTED，不得先进入 PAUSED 再丢失 kill 请求。`paused_from_state` 只用于恢复执行阶段，不参与暂停请求优先级判断。

## 8. 图执行语义

### 8.1 READY 判定

节点只有在以下条件全部满足时才能进入 READY：

- 所有必需依赖已 SUCCEEDED。
- edge condition 评估为 true。
- 节点不在 Task/Step 屏蔽集合中。
- Task 允许继续运行。
- ToolNode 所需 Tool 存在于 task capability scope 且当前实时可用。

Tool 实时不可用不能静默保持 READY；应生成结构化失败或等待条件，由 Runtime 按图规则处理。

### 8.2 调度顺序

某一时刻可能存在多个 READY Step 或 ToolNode。第一版采用稳定串行顺序：

1. graph definition 显式 priority。
2. topological order。
3. node_id 作为最后稳定排序键。

“罗列所有 READY Tool 并执行”在本版表示依次执行，不表示并发。并发执行需要独立 PRD。

### 8.3 Step 成功与失败

- 任一 ToolNode UNCERTAIN：Step 立即 UNCERTAIN。
- 存在可达成功终点的 READY/PENDING/RUNNING 路径：Step 不结束。
- 任意一个 terminal ToolNode 已 SUCCEEDED：Step SUCCEEDED，并将该 Step 中尚未开始且只服务于其他成功路径的节点标记为 SKIPPED。
- 所有成功终点均不可达，且无 UNCERTAIN：Step FAILED。

禁止使用“距离终点最近的节点”作为失败判定，因为分支图中该概念不唯一。应使用图可达性判定。

### 8.4 Task 成功与失败

有预定 Task Graph 时：

- 任一 Step UNCERTAIN：Task UNCERTAIN。
- 任意一个 terminal Step 已 SUCCEEDED：Task SUCCEEDED，并将尚未开始的其他候选成功路径节点标记为 SKIPPED。
- 成功终点均不可达，且无 UNCERTAIN：Task FAILED。
- Task/Step/Tool 的总尝试次数或步数预算耗尽，且未达成成功终点：Task FAILED。
- 不存在 READY/RUNNING 节点，所有其他成功路径均因依赖失败、Tool 不可用、黑名单或条件不满足而不可达，且无 UNCERTAIN：Task FAILED。

无预定 Graph 的 ReAct 任务时：

- 每次 SubAgent 只决定一个下一动作。
- Runtime 将每个动作物化为动态 Step/ToolNode，以便状态与 Trace 一致。
- `COMPLETE` 只是完成候选，Runtime 应根据 completion criteria 和已有 observation 确认。
- 达到 Task 步数/迭代硬上限且未完成：Task FAILED，不再只返回游离于状态机外的 `max_steps` blocked 结果。

Task 进入 FAILED 后，Runtime 必须使用已有结构化失败和 Trace 生成用户可见错误报告，然后执行交付：

```text
FAILED
  -> build failure delivery payload
  -> deliver to user
  -> DELIVERED(terminal_outcome=FAILED)
```

错误报告至少包含：

- Task 未达成的目标。
- 失败是因步数/尝试预算耗尽，还是无其他可用路径。
- 最后可信 observation 和主要失败节点。
- 是否存在用户可解决的权限、输入或外部环境问题。
- 如果来自 uncertain resolution，明确列出状态未知的外部操作和不可确认的副作用。

### 8.5 预算定义与计数

第一版必须同时配置以下互不替代的预算：

| 预算 | 计数对象 | 消耗时机 | 耗尽行为 |
| --- | --- | --- | --- |
| `max_steps` | 业务逻辑 Step | 新业务 Step 首次进入 RUNNING | 未完成则 Task FAILED |
| `max_tool_attempts_per_tool_node` | 同一个 ToolNodeRun 内已实际发起的 ToolAttempt | 该 ToolNode 的 Tool 进入 RUNNING 前 | 该 ToolNode FAILED，并重新计算 Step 可达性 |
| `max_argument_retries` | 参数修复 decision | 初始参数失败后的每次修复结果 | Tool 在当前 Step 熔断 |
| `max_runtime_ticks` | TaskRuntime tick | 每次调度推进开始 | 未完成则 Task FAILED |
| `max_plan_updates` | 成功或失败的 plan_update 调用 | 每次调用开始 | Plan 投影标记 STALE，禁止继续更新 |

默认值固定为：

```text
max_argument_retries = 2
max_tool_attempts_per_tool_node = 3
max_runtime_ticks = max(16, 4 * max_steps + 4)
max_plan_updates = max_steps + 1
```

`max_steps` 是创建 Task 时必须提供的正整数，并作为不可变预算快照保存；运行中不得通过图扩容修改。其余默认预算可以由创建配置显式覆盖，但覆盖值也必须是正整数并写入 Task checkpoint。

- `plan_written` 和 `plan_update` 是控制型 ToolNode，不增加业务 `max_steps` 计数，但会消耗 runtime tick、对应 ToolAttempt 和 `max_plan_updates`（仅 plan_update）。
- 参数校验失败不增加 ToolAttempt，但其后每次 repair 都消耗 runtime tick 和 argument retry。
- 每个 ToolNode 独立拥有 `max_tool_attempts_per_tool_node`；同一 Step 中不同 ToolNode 的 attempt 不共享该计数。同一 ToolNode retry 不新增业务 Step；转入另一个业务小目标时才增加 `max_steps`。
- Graph 容量扩容不消耗 tick，但扩容后实际追加节点会受上述预算限制。
- 任意预算耗尽都必须形成稳定 failure code，并进入图可达性判定；不得只在 API 返回值中报告 blocked 而保持 Task RUNNING。

## 9. 参数重试、黑名单与熔断

### 9.1 参数修复

保留现有契约：

- 默认最多两次 argument repair。
- 修复期间锁定 `active_tool_name`。
- 返回其他 Tool 时不执行，记录 `INVALID_ARGUMENTS_REPAIR_VIOLATION`。
- 参数错误不进入 Tool RUNNING，因此不计为 Tool execution attempt；它属于 decision/validation attempt。
- 耗尽后将该 Tool name 放入当前 Step 黑名单。

### 9.2 Step 黑名单

- 黑名单是 `StepToolAvailability(state=BLOCKED, blocked_until=None)` 的一种状态，不再维护平行的 `blacklisted_tool_names` 可变事实源；如需兼容旧接口，只能提供由该映射计算出的只读属性。
- 仅对当前 StepRun 生效。
- 不改写 ToolManager 注册状态。
- 新 Step 不自动继承黑名单，但必须保留历史失败 observation。

### 9.3 Step 内 Tool 熔断

- 熔断属于 `StepToolAvailability`，只影响当前 Step 中对同名 Tool 的后续选择。
- BLOCKED 期间该 Step 不得再次调用 Tool；存在 `blocked_until` 时，到期后直接转 AVAILABLE，不做 HALF_OPEN 或额外探测。
- 权限不足使用 `blocked_until=None`，在当前 Step 永久 BLOCKED。可恢复的临时环境失败必须给出确定 `blocked_until`；未知内部失败默认在当前 Step 永久 BLOCKED。参数修复只有在耗尽 retry 后才永久 BLOCKED。
- 如果当前 Step 没有其他可执行路径，但至少一个必要 Tool 具有未来 `blocked_until`，Task 进入 WAITING，并创建 `WaitingCondition(kind=TIME, wake_at=最早 blocked_until)`；到期后恢复原 RUNNING 阶段、刷新 StepToolAvailability，再重新计算 READY 节点。
- ToolManager 仍独立执行注册、任务权限和调用时实时依赖检查，不读取或持有 StepToolAvailability。
- 熔断状态不得写入 Task capability permission snapshot。

## 10. 暂停、恢复和 Kill 安全点

Runtime 必须在以下位置检查 control request：

1. Task formulation 开始前。
2. Prompt 已组装、LLM 调用尚未发起时。
3. LLM 返回后、其结果尚未引发 Tool 调用时。
4. Tool 参数已校验、Tool 尚未发起时。
5. ToolAttempt 返回并已完整记录后。
6. Step/Task 节点转移前。

暂停时：

- 不丢弃已完成 LLM/Tool 结果。
- 不把未执行的节点标记为失败。
- 当前 RUNNING Step 在安全点投影为 PAUSED；ToolNode 不新增 PAUSED。
- PAUSED Task 保留在 TaskStore/paused index，不进入 READY dequeue 集合。

恢复时：

- Task 加载暂停时保存的 formulation/GraphRun/预算/observation/WaitingCondition 快照，并转回 `paused_from_state`。
- 只有 `paused_from_state=READY` 才重新入 TaskQueue；RUNNING 由 recovery scheduler 继续，FORMULATING 继续 formulation，WAITING 重新注册等待条件。
- 不重新执行已 SUCCEEDED 节点。KILLED Task 不执行恢复。

## 11. Task Queue 与调度

新增 TaskQueue/TaskScheduler，与 PresenceQueue 分离：

```text
PresenceQueue: StandardizedEvent 级队列
TaskQueue: READY Task id 级队列
TaskStore: 所有 Task 的唯一存储索引
```

规则：

- 只有 READY Task 可入 TaskQueue。
- Scheduler 只能领取 READY Task。
- 领取成功后以原子操作转为 RUNNING，防止重复领取。
- PAUSED/WAITING/UNCERTAIN/KILL_REQUESTED Task 不可领取。
- 第一版可以只有一个 worker，但队列契约不得依赖单 worker。
- AppRuntime/Web UI 只通过应用命令提交、暂停、恢复、kill 和查询，不直接修改 Task.state。
- TaskQueue 只保存可重建的 `task_id`，不是 Task 状态事实来源。进程启动后必须按 5.10 从 TaskStore 重建队列。
- dequeue 后必须先对 TaskStore 执行带预期版本的 `READY -> RUNNING` compare-and-set；失败时不得执行该 Task。

## 12. Plan Graph 与 ReAct 兼容

### 12.1 有 Plan 任务

- Plan 只用于“目标可拆解且预计需要超过 5 个逻辑 Step”的任务。预计不超过 5 个 Step、无法可靠预先拆解或需要根据 observation 决定后续动作的任务，使用无 Plan ReAct。
- 是否需要 Plan 的判断发生在首次执行决策，不新增 TaskState。决策输出必须包含 `mode` 和 `estimated_logical_steps`。只有 `mode=PLAN` 且 `estimated_logical_steps > 5` 才允许进入 Plan 分支；字段缺失、类型错误、估算不大于 5 或输出无法解析时统一回退 REACT。
- 若选择 Plan，首次可执行动作必须是调用 `plan_written`。若该 Tool 不在任务权限范围、未注册或实时依赖不可用，则记录 `plan_tool_unavailable` 并回退 REACT，不得停留在 RUNNING 空转。
- `plan_written` 在 bootstrap dynamic graph 中作为控制型 ToolNode 执行，因此不存在“必须先有正式 Plan Graph 才能调用 plan_written”的循环依赖。
- `plan_written` 接收 `task_id`、新 `version_id` 和有序 PlanStep；每一步必须描述一个可独立验收的小目标。成功后 PlanStore 原子写入完整版本，Task Graph 再引用该不可变版本。
- Task Graph 在 `plan_written` 成功后建立并固化版本。写入失败时不得假装 Plan 已存在；记录普通 Tool failure 后回退 REACT，并将失败作为 observation，禁止在同一 Step 重复调用 `plan_written`。
- 可以有 Reasoning Node 和 Step Node。
- Step Node 内部使用 Tool Graph。
- 只调度依赖满足的 READY Step。
- Plan 文档中的步骤投影只能通过 `plan_update` 修改。`plan_update` 必须指定 `task_id/version_id/step_id/expected_old_status/new_status/result_summary?`，并执行 compare-and-set；版本、Step 或旧状态不匹配时返回结构化失败。
- Runtime 必须先完成 StepRun 状态转移，再允许调用 `plan_update` 投影该结果。`plan_update` 不得直接修改 Task/Step/ToolNode Runtime state，也不得让失败的 Runtime Step 变成成功。
- `plan_update` 失败不回滚已确认的 Runtime 状态；PlanRecord 标记 `STALE`，失败作为 observation/Trace 保存。后续可以在预算内重试一次更新，但不得重做业务 Tool。
- `plan_written` 和 `plan_update` 都是普通注册 Tool：按名称发现、受 capability scope 限制、由 Executor 校验并执行，不得由 SubAgent 直接写文件。

### 12.2 无 Plan / ReAct 任务

- 不预造伪执行节点。GraphRun 初始化 5 个记录容量 slot，但只有 decision 实际产生后才物化 GraphNode。
- 每次 SubAgent decision 形成一个动态节点并追加到 GraphRun。
- 5 个 slot 用尽且 `max_steps` 仍有余额时按 2 倍扩容；扩容上限为 `max_steps`，扩容不增加执行预算。
- Tool result/failure 作为 observation 进入下一次 decision。
- Runtime 仍持有循环、预算、状态转移和中断控制。
- CapabilityExecutor 仍然只执行一个 ToolNode，不升级为 ReAct Executor。

### 12.3 Plan 与 ReAct 的唯一分流规则

首次执行决策必须输出且只输出以下一种模式：

```text
PLAN: task is decomposable AND estimated logical steps > 5
REACT: all other tasks
```

- `PLAN` 不允许携带已执行结果；它只触发一个 `CALL_TOOL(plan_written, ...)` decision。
- `REACT` 不得调用 `plan_written`，除非后续 observation 证明剩余任务可拆解且预计仍超过 5 步；此时允许通过一次明确的 mode-change decision 转为 PLAN，并记录转换原因。
- Plan 执行中，`plan_update` 只负责把现有 PlanStep 投影为 RUNNING/SUCCEEDED/FAILED/SKIPPED 并记录进度，不得增加、删除、重排 Step 或修改依赖。
- observation 导致计划结构变化时，必须生成新的 `version_id`，通过 `plan_written` 写入完整新 Plan，再建立新 TaskGraphDefinition。迁移时只复制旧版本中语义相同且已 SUCCEEDED 的 Step 结果；未完成节点必须以新版本定义为准。旧 PlanRecord、旧 TaskGraphRun 和迁移映射永久保留用于审计。
- Skill 只提供执行指导，不决定 PLAN/REACT；ToolDefinition 只描述能力，不自行触发规划。

这里的“可拆解”必须同时满足：每个候选 Step 都有独立小目标、明确完成条件，并且依赖关系可以表示为 DAG。纯对话、一次直接回答、需要先观察才能知道后续动作或无法给出独立完成条件的任务一律判为 REACT。

## 13. Trace 契约

### 13.1 原则

- Trace 是 append-only 事件流及其派生快照。
- 每个 Task 按 `task_id/trace_id` 隔离。
- 不得由 SubAgent 覆盖全局固定文件。
- Prompt 与 LLM output 可记录于本地 debug trace，但必须脱敏且不默认写入 Memory。
- RuntimeTimingRecorder 的耗时字段关联到对应 TraceEvent，不再重复计时。

### 13.2 TaskTraceSnapshot

```python
TaskTraceSnapshot
- timestamp: datetime
- task_id: str
- conversation_id: str | None
- trace_id: str
- user_prompt: str
- task_state: TaskState
- logical_steps_used: int
- max_steps: int
- task_graph: TaskGraphTrace
- timing: RuntimeTimingSnapshot | None
```

### 13.3 TaskGraphTrace

```python
TaskGraphTrace
- graph_id: str
- graph_version: str
- structure: tuple[GraphEdge, ...]
- node_traces: tuple[TaskNodeTrace, ...]
```

### 13.4 TaskNodeTrace

```python
TaskNodeTrace
- node_id: str
- node_type: REASONING | STEP
- position: GraphPosition
- state: str
- reasoning_trace: ReasoningTrace | None
- step_trace: StepTrace | None
```

`position` 不应仅依赖易变的 list index；`node_id` 是稳定定位，position 仅作展示用拓扑层级/顺序。

### 13.5 ReasoningTrace

```python
ReasoningTrace
- prompt_type: str
- prompt_name: str
- prompt_text: str
- llm_provider: str
- model_name: str
- llm_parameters_fingerprint: str
- output: str
- started_at / finished_at / duration_ms
- success: bool
- error_code: str | None
```

`llm_parameters_fingerprint` 由稳定序列化后的非敏感推理参数计算，不得包含 API key、header 或 client 对象。

### 13.6 StepTrace

```python
StepTrace
- step_id: str
- step_state: StepState
- tool_attempts_total: int
- max_tool_attempts_per_tool_node: int
- tool_graph: ToolGraphTrace
- started_at / finished_at / duration_ms
```

### 13.7 ToolNodeTrace

```python
ToolNodeTrace
- node_id: str
- tool_name: str
- tool_version: str
- tool_state: ToolNodeState
- attempts: tuple[ToolAttemptTrace, ...]
- output_summary: Mapping[str, Any] | None
```

```python
ToolAttemptTrace
- attempt_id: str
- attempt_index: int
- input: Mapping[str, Any]
- output: Mapping[str, Any] | None
- state: str
- failure: ToolFailureObservation | None
- started_at / finished_at / duration_ms
- step_availability_snapshot: StepToolAvailability | None
- manager_resolution: REGISTERED_AND_ALLOWED | NOT_REGISTERED | NOT_ALLOWED | LIVE_DEPENDENCY_UNAVAILABLE
```

`failed_reason` 不再是嵌套嵌套的自由 JSON，直接复用 `ToolFailureObservation`。

## 14. 状态所有权与命令边界

| 对象 | 状态唯一所有者 | 可提交命令者 | 禁止直接修改者 |
| --- | --- | --- | --- |
| Task | TaskRuntime / TaskScheduler | AppRuntime、Web UI adapter、EventRuntime | SubAgent、Tool、Provider、页面 |
| TaskGraphRun | TaskRuntime graph coordinator | SubAgent 只返回 decision/plan proposal | Tool、Provider、页面 |
| StepRun | StepRuntime/TaskRuntime 内的 Step coordinator | Task graph scheduler | SubAgent、Tool |
| ToolNodeRun | Step coordinator | CapabilityExecutor 返回执行结果 | Tool 实例、SubAgent |
| StepToolAvailability | 所属 Step coordinator | Executor 提交当前 Step 的失败/成功事实 | ToolManager、其他 Task/Step、SubAgent |
| Tool 注册与实时解析结果 | ToolManager | App assembly 注册；Executor 请求解析 | Task/Step/ToolNode 不得反向写入 |
| Trace | TraceRecorder | 各边界提交事件 | Trace consumer/UI |

## 15. 需要修改或删除的现有内容

### 15.1 现有 `sessions/session.py` 与 Session 命名

- 用新 TaskState 替换现有 `PLANNING/REPLANNING/COMPLETED/CANCELLED` 语义，不保留两套并行状态。
- `PLANNING/REPLANNING` 应转为 TaskGraph 中的 Reasoning Node/operation，而不是 Task 生命周期状态。
- `COMPLETED` 拆为 `SUCCEEDED -> DELIVERED`。
- `CANCELLED` 迁移为 `KILL_REQUESTED -> KILLED`。
- `WAITING` 保留为等待条件，不与 PAUSED 合并。
- `TaskSession` 重命名为 `Task`，并删除 `session_id`。
- `TaskSessionManager` 收口为 `TaskFactory` 或 `TaskManager`，只负责创建 Task 及任务本地 execution context。
- `TaskSessionCreation` 删除；如果创建过程仍需要返回多个对象，应使用语义明确的 `TaskCreationResult`，但不能再引入 session id。
- `TaskRuntime._sessions` 删除，`_tasks[task_id]` 作为唯一索引。
- Task 创建边界前移至 formulation 之前。
- 为了限制迁移爆炸半径，可以短期保留 `TaskSession = Task` 只读导入别名；新 Runtime 代码不得继续构造或依赖 Session 概念。

### 15.2 `session_id` 协议迁移

删除 Session 概念必须同时删除其在公共数据契约中的传播，不允许只重命名 `TaskSession` 类。

需要迁移的契约包括：

- `AgentExecutionContext.session_id` 删除，任务本地权限边界使用 `task_id`。
- `TaskHandle.session_id` 删除，Handle 仅保留 `task_id` 和 `trace_id`。
- `StrategyDecision.session_id` 删除。
- `ToolResult.session_id` 删除，Tool 输出使用 `task_id/trace_id/tool_name` 归属。
- Camera/Screen/Mock Tool 输入 Schema 中为 Runtime 归属而人为暴露的 `session_id` 删除；Runtime 标识不应由 LLM 生成为 Tool argument。
- `RuntimeTimingSnapshot.session_id` 删除，Timing 使用 `task_id/trace_id` 关联。
- `MemoryManagementRequest.session_id` 和 Memory 文本中的 `session_id` 删除，历史记录使用 `task_id/trace_id/conversation_id?`。
- CompletionPackage、DisplaySnapshot、TraceSnapshot 不得通过嵌套 Context 继续泄漏旧 `session_id`。
- `runtime/event_router.py` 中的 `target_session_id/active_session_ids` 必须根据真实语义拆分：指向运行任务时重命名为 `target_task_id/active_task_ids`；指向对话时使用 `conversation_id`。

迁移期间不得使用 `session_id = task_id` 的假别名继续写入新 checkpoint、Trace 或 Memory。这会使重复概念永久化。

### 15.3 `sessions/execution_state.py`

- 保留 `ToolFailureKind` 与 `ToolFailureObservation`。
- 拆分当前 `StepExecutionState` 中 Step 运行状态与 Tool argument retry 语义。
- 新增 StepState、ToolNodeState、ToolAttempt 契约。
- 移除由 `step_number` 暗示线性 Step 的唯一定位方式，增加稳定 `step_id/node_id`。

### 15.4 `runtime/task_runtime.py`

- 将线性 `if state ...` 分支升级为命令处理 + TaskGraph scheduler。
- 保留“一次 Runtime tick 最多执行一个 Tool”契约。
- `_archive_and_advance()` 不再无条件生成 `step_number + 1`，改为依图依赖解锁节点。
- `_stop_reason()` 必须与 TaskState 一致，禁止状态为 RUNNING 但只通过 `max_steps` 局部标志表示失败。
- 新增 pause/resume/kill/resolve_uncertain 命令入口。
- 将调度与完成结果交付分离，防止 delivery retry 重新执行 Tool。

### 15.5 `runtime/event_runtime.py` 与 `agent/main_agent.py`

- 先创建 Task(CREATED)，再以该 task id 进入 FORMULATING。
- formulation 完成后写入 handoff，转 READY 并入 TaskQueue。
- formulation 期间可检查 pause/kill control request。
- PresenceQueue 仍处理 Event，不兼任 TaskQueue。

### 15.6 `sessions/subagent.py`

- 不再直接覆盖 `trace/trace.json`。
- 只返回 reasoning/plan/decision proposal，不直接修改 GraphRun state。
- 将当前 `tool_trace` 和 `step_history` 输入改为来自 GraphRun/Trace projection 的结构化 observations。
- 不承担 Task Queue 的实际 dequeue；Scheduler 先领取 Task，再调用 SubAgent。

### 15.7 `sessions/executor.py`

- 继续保持 single-action executor。
- 输入改为当前 ToolNodeRun + ExecutionDecision + Context。
- 执行前依次检查 Task capability scope、ToolManager 实时解析结果和当前 StepToolAvailability。
- 返回规范化 success/failure/uncertain，但不直接修改 Step/Task state。
- 需要新增 uncertain 判定契约，不能仅靠捕获 timeout 猜测。

### 15.8 Tool 元数据与 ToolManager

- ToolDefinition 增加 tool version、idempotency、side-effect 和 uncertain 判定所需的公开元数据。
- ToolManager 保持 Tool 注册唯一存储来源。
- ToolManager 负责进程级 Tool 注册、权限过滤与调用时实时依赖检查；不得持有 StepToolAvailability。
- StepToolAvailability 只保存在所属 StepRun；不得放入 ToolDefinition 或 ToolManager。
- 注册 `plan_written` 与 `plan_update`，其存储访问封装在 PlanStore/Tool 内，不向模型暴露本地路径。
- Tool 不自行修改 Task/Step state。

### 15.9 AppRuntime / Web UI

- 只调用 submit/pause/resume/kill/get_task 应用命令。
- 页面不直接修改 state，不直接操作 Queue。
- 展示 Task、Step、ToolNode 分层状态和 Trace 快照。
- 区分 WAITING、PAUSE_REQUESTED、PAUSED、UNCERTAIN 和 KILL_REQUESTED，不将它们都显示为“任务失败”。

### 15.10 包结构迁移

`sessions/` 当前同时放置 Task、SubAgent、Executor、Decision 和 Completion 对象。删除 Session 概念后，建议分阶段迁移为：

```text
tasks/
  task.py
  state.py
  graph.py
  factory.py
  completion.py

agent/
  subagent.py
  decision.py
  strategy.py

runtime/
  task_runtime.py
  task_queue.py
  scheduler.py
  executor.py
```

目录迁移不得和状态机行为改动混在同一个 PR；先建立新契约和兼容导入，再做机械迁移。

## 16. 非目标

本 PRD 第一阶段不实现：

- 多进程/分布式 Task Scheduler。
- 并发 Tool 调用。
- 强制中断正在运行的第三方 SDK 调用。
- 任意图脚本或任意 Python condition 执行。
- 跨进程 Trace 服务。
- 数据库持久化和分布式锁。
- 自动回滚所有非幂等操作。
- 仅凭 LLM 文本判断 uncertain 已解决。

## 17. 分阶段实施计划

该改造不可在一个代码 PR 中完成。

### Phase 1：领域契约与转移表

- 定义 TaskState、StepState、ToolNodeState、ControlRequest。
- 定义 GraphDefinition/GraphRun/Attempt 不可变契约。
- 完成 `TaskSession -> Task` 命名与标识契约，删除新代码对 `session_id` 的依赖。
- 从 AgentExecutionContext、TaskHandle、StrategyDecision、ToolResult、Timing、Memory 和 EventRouter 迁移 `session_id`。
- 只做数据契约和纯函数转移校验。

### Phase 2：Task 创建边界与 TaskQueue

- Task 在 formulation 前创建。
- 实现 CREATED -> FORMULATING -> READY。
- 实现本地原子 checkpoint TaskStore、TaskQueue、启动恢复与单 worker scheduler。

### Phase 3：Step Tool Graph 串行执行

- 实现 DAG 校验和 READY 节点选择。
- 一次 Runtime tick 只执行一个 ToolNode。
- 将现有 argument retry/failure/blacklist 迁移到新聚合。

### Phase 4：Task Graph、Plan Tool 与 ReAct 动态节点

- 实现有 Plan Task Graph。
- 实现 `plan_written`、`plan_update` 与 PlanStore 的版本化写入。
- 实现唯一 PLAN/REACT 分流规则。
- 实现无 Plan ReAct 的 5-slot 初始容量与受 `max_steps` 限制的 2 倍扩容。
- 统一 Task 终态判定。

### Phase 5：Pause / Resume / Kill

- 增加应用命令。
- 在 formulation、LLM、Tool 和 graph transition 安全点检查。
- 恢复时保留 GraphRun 与预算。

### Phase 6：Uncertain 与 Step Tool 熔断

- ToolDefinition 增加幂等性/副作用元数据。
- 实现 uncertain 上浮和 `RESOLVE_UNCERTAIN_AS_FAILED` 失败收口命令。
- resolution 不执行额外 Tool/LLM/补偿操作，但必须保留原 UNCERTAIN Attempt 和用户可见详情。
- 实现 StepToolAvailability 与 Step 级 circuit breaker，不在 ToolManager 中增加第二份 Step 状态。

### Phase 7：分层 Trace 与 UI 投影

- 实现 append-only TraceRecorder。
- 移除 SubAgent 固定文件覆盖写入。
- 实现 Task/Step/ToolNode Trace snapshot 和 Web UI 展示。

## 18. 验收标准

### 18.1 状态与所有权

- Task、Step、ToolNode 各自有唯一状态来源。
- 旧 TaskState 不与新 TaskState 并行存在。
- UI、SubAgent、Tool 无法直接改写上层 state。
- 两个 Task 不共享 GraphRun、Attempt、blacklist 或 failure。
- Runtime 内不存在与 Task 一对一重复的 Session 聚合、`session_id` 或 `_sessions` 索引。
- AgentExecutionContext、TaskHandle、ToolResult、TimingSnapshot、MemoryRecord 和 TraceSnapshot 不再包含 `session_id`。
- Tool input schema 不要求 LLM 提供 `session_id`，Tool 归属由 Runtime context 保证。

### 18.2 图执行

- Task Graph 和 Tool Graph 拒绝重复 node、缺失 edge 和 cycle。
- Graph 拓扑、条件和 priority 只来源于 edges，NodeDefinition 不保存第二份 dependencies。
- 只有依赖满足的节点能进入 READY。
- 多个 READY 节点在第一版以确定性串行顺序执行。
- 一次 Runtime tick 最多执行一个 ToolNode。
- PLAN 通过 bootstrap dynamic graph 执行首个 `plan_written`，成功后再切换到正式 Plan Graph。
- 失败分支不阻断仍然可达的成功路径。
- 无成功路径且无 uncertain 时，正确进入 FAILED。
- 步数/尝试预算耗尽时进入 FAILED，生成错误报告并可转入 DELIVERED。
- 无其他可用路径时进入 FAILED，生成错误报告并可转入 DELIVERED。
- ReAct Graph 初始容量为 `min(5, max_steps)`，容量不足时按 2 倍扩容但绝不突破 `max_steps`。
- 空容量 slot 不被当作节点，不参与图状态判定。
- 可规划且预计超过 5 个逻辑 Step 的任务首先调用 `plan_written`；其他任务默认进入 ReAct。
- `plan_update` 只更新指定 Plan 版本的步骤投影，不直接修改 Runtime state。
- Plan 结构变化必须创建新 version_id，并保留旧 Plan、旧 GraphRun 和迁移映射。
- 任意一个 terminal 成功即可结束对应 Step/Task，未采用路径被标记为 SKIPPED。
- 每个 ToolNode 独立计算 ToolAttempt 次数；不同 ToolNode 不共享 attempt 预算。
- ToolDefinition 是副作用/幂等性元数据事实来源，ToolNode override 未通过注册校验时 Graph 不得运行。
- 各层预算按 8.5 独立计数，控制型 Plan Tool 不消耗业务 step，但受 tick、attempt 和 plan update 预算保护。

### 18.3 控制流

- 只有 READY Task 可被 Scheduler 领取。
- pause request 在下一安全点转为 PAUSED。
- PAUSED 保存暂停请求前的真实 `paused_from_state`，不得保存 PAUSE_REQUESTED。
- resume 回到 paused_from_state 并加载足够恢复的快照，不统一转 READY，不重做已完成节点。
- kill request 不再发起新的 LLM/Tool 调用。
- KILLED Task 不恢复；重启遇到 KILL_REQUESTED 时由恢复协调器完成 KILLED 收口。
- SUCCEEDED 后交付失败可重试交付，不重新执行 Task Graph。
- FAILED 后可交付错误报告并转为 DELIVERED，`terminal_outcome` 仍为 FAILED。
- DELIVERED 可区分交付的是成功结果、普通失败报告还是 uncertain 失败报告。
- 控制命令按 `(task_id, command_id)` 幂等，非法状态返回稳定错误码。
- 重启后 READY Task 可重新入队，PAUSED/WAITING/UNCERTAIN 不被错误领取。
- 恢复含未落定副作用 ToolAttempt 的 Task 时进入 UNCERTAIN，不重复执行原 Tool。
- WAITING 必须具有可持久化 WaitingCondition，并可按用户输入、外部事件或时间条件恢复。
- Step Tool 熔断到期后直接由 BLOCKED 转 AVAILABLE，不使用 HALF_OPEN；永久 BLOCKED 使用 blocked_until=None。

### 18.4 Uncertain

- 非幂等副作用无法确认时进入 UNCERTAIN。
- ToolNode UNCERTAIN 立即上浮到 Step 和 Task。
- UNCERTAIN Task 不执行其他图路径。
- `RESOLVE_UNCERTAIN_AS_FAILED` 不执行额外操作，将 ToolNode/Step/Task 收口为 FAILED。
- 原 ToolAttempt 仍保留 UNCERTAIN 记录，不伪造外部操作已确认失败。
- 用户能收到包含 Tool、原因、可能副作用与未知范围的详细报告。

### 18.5 Trace

- 不同 Task 的 Trace 按 task_id/trace_id 隔离。
- Trace 追加写入，不覆盖其他 Task。
- Trace 可重建 Task/Step/ToolNode 执行快照。
- Prompt、LLM 参数指纹、Tool input/output 均会脱敏。
- Trace 不写入 Memory，不作为 Runtime 的反向状态来源。

## 19. 风险与兼容性

### 19.1 改造规模

这不是小型状态枚举修改，而是 Task 创建边界、调度、图执行、Tool 失败、Trace 与 UI 投影的系统性迁移。必须按 Phase 实施，每个 Phase 合并后保持 `python -m pytest` 和 `python main.py` 可运行。

### 19.2 兼容层

- 可以为旧 `TaskState.COMPLETED/CANCELLED` 提供短期只读映射，但 Runtime 内部不得同时写旧新状态。
- 可以短期保留 `TaskSession` 导入别名用于迁移现有测试，但 checkpoint、TaskStore、TaskQueue 和新 API 只使用 `Task/task_id`。
- 可以从新 GraphRun 投影出旧 `tool_trace/step_history`，但旧 tuple 不得继续作为事实来源。
- AppRuntime 现有同步 `run_until_complete` 可在第一阶段作为 Scheduler 的同步 facade，但底层必须通过 TaskQueue/TaskStore。

### 19.3 主要风险

- 图节点条件与 LLM 动态输出混合后可能导致不可重现。
- 暂停发生在外部副作用调用附近时，容易错误标记已执行或未执行。
- uncertain 缺乏 Tool 元数据和幂等 key 时无法可靠恢复。
- Trace 若保存完整 Prompt/Tool output，可能带来隐私和存储成本。
- 旧测试大量断言现有 TaskState，需要按 Phase 迁移，不能通过放宽断言掩盖行为改变。

## 20. 已确认设计决策

- `TaskSession` 收口为唯一 `Task` 聚合，删除 `session_id`、`_sessions` 索引和 Session 概念，并将 Task 创建前移到 formulation 之前。
- 使用 `DELIVERED` 表示结果或错误报告已经交付；`submit/enqueue` 只表示 Task 入队操作。
- 使用 `KILL_REQUESTED` 区分“终止请求已收到”与“Runtime 已在安全点确认终止”。
- 第一版 Graph Scheduler 对多个 READY 节点执行稳定、确定性的串行调度。
- UNCERTAIN 第一版通过 `RESOLVE_UNCERTAIN_AS_FAILED` 直接按失败收口，不进行自动探测、重试、补偿或回滚。
- SUCCEEDED 和 FAILED 均可转入 DELIVERED；DELIVERED 仅表示信息已交付，原执行结论保存在 `terminal_outcome`。
- `StepToolAvailability` 是 `(step_id, tool_name)` 维度的 Step 局部状态；`ToolManager` 负责进程级 Tool 注册与解析，二者不得互相包含或维护对方状态。
- Step Tool 熔断使用 `BLOCKED/AVAILABLE` 避免 circuit OPEN 的反向歧义；到达 blocked_until 后直接恢复 AVAILABLE，不执行 HALF_OPEN 探测。
- 无 Plan ReAct 使用动态 GraphRun：初始化 5 个容量 slot，用尽后在 `max_steps` 内按 2 倍扩容；slot 不是预建执行节点。
- 可规划且预计超过 5 个逻辑 Step 的任务使用 PLAN，并首先调用 `plan_written`；其余任务使用 REACT。
- `plan_written` 首先在 bootstrap dynamic graph 内执行，成功后才切换到正式 Plan Graph。
- Plan 通过 `plan_written` 创建版本，通过 `plan_update` 更新步骤进度投影；结构变化必须创建新 version_id 并迁移已完成节点。PlanStore 使用 `(task_id, version_id)` 唯一定位，不允许模型操作任意路径。
- Graph 只以 edges 保存拓扑、条件和 priority，NodeDefinition 不保存第二份 dependencies。
- 暂停必须保存暂停前真实执行阶段；恢复回到该阶段并加载完整快照。KILLED 不恢复执行。
- 任意一个 terminal 成功即表示当前 Step/Task 目标达成，未采用路径进入 SKIPPED。
- ToolAttempt 预算属于单个 ToolNodeRun，不属于整个 Step。
- ToolDefinition 是幂等性、副作用和 uncertain policy 的事实来源；ToolNode 只允许经过注册校验的 override。
- WAITING 必须携带可持久化 WaitingCondition；`active_step_ids` 只能从 TaskGraphRun.node_runs 派生。

本文不再保留待实现者自行选择的架构分支。后续发现无法满足某条已确认决策时，必须先修改并重新审核本 PRD，不得在代码 PR 中隐式采用另一种语义。

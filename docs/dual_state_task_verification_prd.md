> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella Runtime 双状态任务与结果验证 PRD

## 1. 文档目的

本文定义 Ella Runtime 下一版任务模型的唯一目标设计，覆盖：

- 任务首次决策与意图生成；
- 统一的 Decide -> Act -> Observe 执行循环；
- TaskExecutionState 与 TaskGoalState 双状态；
- 结果草稿、机械验证、回答质量验证；
- checkpoint、暂停、恢复、取消与交付；
- 前端和 Trace 对状态的展示方式。

新实现直接采用本 PRD，不兼容旧 checkpoint 和旧任务数据。本文明确删除的状态、动作和流程不得以兼容分支继续保留。

## 2. 产品目标

Ella 必须分别回答两个问题：

1. Runtime 当前执行到哪里，是否还能继续运行？
2. 用户目标最终达到多少？

这两个问题不能继续混在一个状态字段中。执行成功不天然等于目标达到；目标已经达到也不保证结果已经成功交付。

目标链路为：

```text
用户输入
-> Task 入队（goal=None）
-> First Decision：识别意图并选择第一个 Action
-> Decide -> Act -> Observe
-> SUBMIT_RESULT（同时提交任务摘要与用户回答草稿）
-> VerificationAgent 验证目标与回答
-> COMPLETED 或 FAILED
-> DELIVERED
```

## 3. 核心原则

### 3.1 双状态正交

- `TaskExecutionState` 描述 Runtime 生命周期和恢复位置。
- `TaskGoalState` 描述用户目标的达成程度。
- 调度、暂停和恢复只依据 `TaskExecutionState`。
- `TaskGoalState` 只用于验收、展示、Trace 和统计。
- 活跃任务的 `goal_state` 必须为 `None`，不得增加 `PENDING`、`UNKNOWN` 等占位值。

### 3.2 规划是一种内部能力

规划不是独立策略模式。模型通过 `CALL_TOOL(plan_written)` 创建计划，通过计划修改工具更新计划。

```text
简单任务 -> CALL_TOOL / SUBMIT_RESULT
复杂任务 -> CALL_TOOL(plan_written)
```

`plan_written` 在动作协议上与 Tool 一致，但治理上属于 Runtime internal capability。

### 3.3 完成前必须验证

模型输出 `SUBMIT_RESULT` 只表示提交候选结果，不表示任务完成。`SUBMIT_RESULT` 必须同时包含内部任务摘要和实际用户回答草稿。Runtime 不得在其后调用独立 FinalResponseGenerator 再次生成回答；它必须把模型提交的原始草稿交给 VerificationAgent 检查目标、产物、证据和回答质量。

### 3.4 流程失败与目标未达到分离

- 流程失败：Runtime、Provider、持久化或恢复机制无法继续，执行状态为 `FAILED`。
- 目标未达到：流程正常结束，但没有实现用户目标，目标状态为 `NOT_ACHIEVED`。
- 用户取消和副作用结果不确定均标记目标 `NOT_ACHIEVED`。

## 4. Task 数据契约

Task 至少持有：

```text
task_id
trace_id
user_id（可选）
raw_user_input
execution_state
goal_state: TaskGoalState | None
terminal_execution_state: TaskExecutionState | None
intent: TaskIntent | None
plan/version（可选）
observations
failures
candidate_result（可选）
draft_final_response（可选）
verification_state
created_at / updated_at
```

Task 创建和入队时：

```text
raw_user_input = 用户原始输入
intent = None
goal_state = None
execution_state = CREATED -> READY
```

Task 入队不得要求预先生成 goal。

## 5. TaskIntent

First Decision 成功后生成不可随意漂移的 `TaskIntent`：

```text
goal
constraints
deliverables
minimum_acceptance_criteria
```

约束：

- `goal` 是用户真正希望达到的结果，不是固定模板。
- `constraints` 保存用户限制和安全边界。
- `deliverables` 描述应交付的结果或产物。
- `minimum_acceptance_criteria` 只描述“什么事实成立才算达到目标”。
- 验收条件必须是声明式条件，不包含 checker 名、Tool 名或具体执行方案。
- `constraints` 和 `minimum_acceptance_criteria` 均允许为空数组；模型不得为了填充字段而虚构限制或验收条件。
- 上述数组非空时，每个元素必须是非空字符串，不得包含空字符串或占位项。
- 简单问候或无需外部事实验证的直接回答应使用最小 Intent。
- Replan 只能修改 Plan，不得修改 Intent。
- 如果用户提出新的目标，应创建新 Task 或走后续明确设计的意图变更流程，不得暗中覆盖原 Intent。

## 6. TaskExecutionState

唯一允许的执行状态：

```text
CREATED
READY
REASONING
TOOL_EXECUTION
PAUSE_REQUESTED
PAUSED
KILL_REQUESTED
KILLED
UNCERTAIN
COMPLETED
FAILED
DELIVERED
```

必须删除：

```text
FORMULATING
PLANNING
REPLANNING
RUNNING
SUCCEEDED
WAITING
```

状态含义：

- `CREATED`：Task 已创建，尚未进入可调度队列。
- `READY`：Task 可由 worker 获取并继续执行。
- `REASONING`：正在进行任何模型推理，包括 First Decision、普通动作决策、草稿生成和验证决策。
- `TOOL_EXECUTION`：正在执行任何 Tool，包括外部 Tool、Runtime capability、验证 Tool 和 ask_user_question。
- `PAUSE_REQUESTED`：已请求暂停，等待到达可安全持久化边界。
- `PAUSED`：已持久化足够恢复的数据，当前不执行。
- `KILL_REQUESTED`：已请求取消，等待 Runtime 在安全边界终止。
- `KILLED`：用户取消后的终态。
- `UNCERTAIN`：带副作用操作中断后无法确认实际结果的终态。
- `COMPLETED`：执行已结束，VerificationAgent 已给出目标验收结论，结果尚未完成应用交付。
- `FAILED`：Runtime 流程失败，无法正常继续。
- `DELIVERED`：终态结果已持久化并成功发布至应用事件边界。

### 6.1 状态转移

主要合法转移：

```text
CREATED -> READY
READY -> REASONING
REASONING -> TOOL_EXECUTION
TOOL_EXECUTION -> REASONING
REASONING -> COMPLETED
REASONING -> FAILED
TOOL_EXECUTION -> FAILED
任意可中断活跃状态 -> PAUSE_REQUESTED -> PAUSED
PAUSED -> 上次被暂停的执行状态
任意允许取消的活跃状态 -> KILL_REQUESTED -> KILLED
TOOL_EXECUTION -> UNCERTAIN
COMPLETED -> DELIVERED
FAILED -> DELIVERED
KILLED -> DELIVERED
UNCERTAIN -> DELIVERED
```

暂停时必须记录真正的恢复阶段，例如 `REASONING` 或 `TOOL_EXECUTION`，不能把 `PAUSE_REQUESTED` 当作恢复阶段。

`DELIVERED` 不是浏览器已读确认；它表示结果已成功发布到应用事件边界。

## 7. TaskGoalState

唯一允许的目标状态：

```text
ACHIEVED
PARTIALLY_ACHIEVED
NOT_ACHIEVED
```

判定规则：

- `ACHIEVED`：所有必要 deliverables 和最低验收条件均有证据支持。
- `PARTIALLY_ACHIEVED`：至少一部分用户目标真实完成，但仍有明确部分未达到。
- `NOT_ACHIEVED`：没有任何目标部分达成，或任务被取消，或副作用结果不确定。

禁止用 `PARTIALLY_ACHIEVED` 表示“不确定”“执行出错”或“无法判断”。

GoalState 由 VerificationAgent 提议，由 Runtime 校验并提交。SubAgent 和 Tool 均不得直接写入。

## 8. First Decision

### 8.1 目的

删除独立 Task Formulation 阶段。Task 的第一次模型决策同时完成：

1. 识别用户意图；
2. 生成 TaskIntent；
3. 判断是否需要计划；
4. 返回第一个 Action。

第一轮输出示意：

```json
{
  "intent": {
    "goal": "...",
    "constraints": [],
    "deliverables": [],
    "minimum_acceptance_criteria": []
  },
  "action": {
    "type": "CALL_TOOL",
    "tool_name": "...",
    "arguments": {}
  }
}
```

后续轮次只返回 Action，不重复生成 Intent。

### 8.2 意图不清晰

当无法可靠识别用户目的时：

- `intent` 保持 `None`；
- 模型选择 `CALL_TOOL(ask_user_question)`；
- Tool 以 question_id、task_id、user_id 等字段发布问题；
- 用户回答通过相同标识关联；
- Tool 返回后重新执行 First Decision。

第一版接口允许多问题数据结构，但一次最多发布一个问题。第一条合法答案生效，后续答案拒绝。

### 8.3 First Decision 失败

- 非法 JSON、协议缺失或 Provider 失败最多重试 2 次。
- 重试仍失败时进入 `FAILED`。
- 不得回退到关键词意图识别或固定 goal 模板。

### 8.4 持久化顺序

First Decision 输出必须先校验，再原子持久化：

```text
TaskIntent + pending_action + checkpoint
```

持久化成功后才能执行 Action。若推理结束但持久化前进程退出，应重新执行 First Decision；若 Intent 和 pending Action 已落盘，恢复时不得重新识别意图。

## 9. 统一 Action 模型

执行阶段只保留：

```text
CALL_TOOL
SUBMIT_RESULT
```

删除：

```text
COMPLETE
REPLAN
WAIT
```

### 9.1 CALL_TOOL

所有外部能力和 Runtime internal capability 都通过同一执行链：

```text
Decision
-> CapabilityExecutor
-> Tool/Capability
-> ToolResult 或结构化 failure
-> Observation
-> 下一轮 Decision
```

### 9.2 SUBMIT_RESULT

`SUBMIT_RESULT` 表示模型认为已有信息足以提交候选结果。动作协议必须包含：

```text
action = SUBMIT_RESULT
completion_summary = 非空内部任务摘要
final_response_draft = 非空用户可见候选回答
evidence_refs = 与当前 observations 对应的证据引用，可为空
decision_reason = 非空决策原因
```

其中：

- `completion_summary` 用于 Task 内部摘要、Trace 和 Memory，不直接作为用户回答。
- `final_response_draft` 必须已经是可以交给用户阅读的完整候选回答，不得只写“稍后生成”“正在处理”或未来承诺。
- `evidence_refs` 必须引用已经存在的 observation，不得伪造。
- 缺少 `final_response_draft`、草稿为空或字段类型非法均属于动作协议错误，按 decision repair 预算处理。

Runtime 收到合法 `SUBMIT_RESULT` 后必须：

1. 原子持久化 `completion_summary`、`final_response_draft`、`evidence_refs` 和 pending verification；
2. 进入 Verification；
3. 根据验证结果完成、返回执行或流程失败。

`SUBMIT_RESULT` 不得直接将 Task 标记为 `COMPLETED`。

## 10. Plan 与 Plan Update

- 创建计划必须调用 `plan_written`。
- 计划结构变化创建新的 `version_id`。
- 新版本迁移旧版本中仍有效的未完成节点。
- `plan_update` 只更新节点进度和完成情况，不负责改变图结构。
- 如果执行中发现原计划不可行，模型应调用计划修改能力；这本身是一个正常 Step，而不是 `REPLAN` 状态或动作。
- Task Graph 的 terminal 表示当前目标是否有任一路径达到；任一合法路径达到 terminal 即可结束当前图执行。
- 如果 Plan 执行期间模型已经输出合法 `SUBMIT_RESULT`，Runtime 立即进入 Verification，不再安排额外汇总推理。
- 如果 Plan Graph 已明确结束，且仍没有合法 `SUBMIT_RESULT`，Runtime 必须自动安排一次普通 `REASONING`。该推理接收完整 Plan 状态、节点结果、failures 和 observations，并由模型返回 `SUBMIT_RESULT` 或继续选择合法 Action。
- “Plan Graph 已明确结束”是自动安排上述 Reasoning 的唯一条件。不得因为单个节点完成、当前 ready node 暂时为空或一次 Tool 返回就推断整个 Plan 已结束。
- 非 Plan 的 React 任务没有预定节点集合和 terminal node。每次 Tool 完成后只产生 observation 并回到普通 Reasoning；Runtime 不得应用 Plan Graph 的自动汇总规则。
- React 任务是否继续调用 Tool 或提交结果，只由下一次模型决策决定。
- 流程失败、Tool 失败或 Plan 无可用路径时，失败信息作为结构化 observation 进入同一 Reasoning 链。如果尚未产生 `SUBMIT_RESULT`，模型必须基于这些事实形成诚实结果；不得增加独立 Failure Response 流程。

## 11. 候选结果与回答草稿

`SUBMIT_RESULT.final_response_draft` 是 Verification 和最终交付使用的唯一候选回答来源。Runtime 不再拥有独立 FinalResponseGenerator，也不得在 Verification 前后对已提交草稿进行一次无条件 LLM 改写。

模型生成 `SUBMIT_RESULT` 时可见上下文至少包含：

- 原始用户输入；
- TaskIntent；
- 当前 Plan 与完成进度；
- 成功 observations；
- 结构化 failures；
- 产物引用；
- 当前 Memory 摘要（如适用）。

草稿不得先发送给用户。验证对象必须是实际草稿，而不是一句候选摘要。

Verification 通过后，Runtime 直接交付被验证的 `final_response_draft`。仅当 LLM 边界完全不可用且无法形成合法 `SUBMIT_RESULT` 时，Runtime 才可使用 deterministic failure fallback；fallback 必须如实说明流程失败，不得声称任务目标已经完成。

## 12. VerificationAgent

### 12.1 职责

VerificationAgent 是独立边界，负责：

- 判断哪些最低验收条件需要机械验证；
- 调用只读验证工具；
- 检查 deliverables 和 observation 是否支持任务结论；
- 检查实际回答草稿是否真实、完整、与证据一致；
- 提议 GoalState；
- 判断应完成还是返回执行阶段修复。

它可以复用同一 LLMProvider，但必须使用独立 `VERIFICATION_DECISION` PromptType。

### 12.2 输入

```text
raw_user_input
TaskIntent
Plan / TaskGraph 状态
observations
failures
candidate_result
draft_final_response
verification_round
existing_verification_results
```

不得向验证模型提供隐藏推理链。

### 12.3 输出

验证动作只允许：

```text
CALL_TOOL
VERIFICATION_VERDICT
```

Verdict 至少包含：

```text
goal_state
criterion_results
deliverable_results
draft_quality_issues
recoverable
feedback_for_execution
public_summary
```

### 12.4 验证轮数

- 每个 Task 都必须经过 Verification 边界。
- 如果 `minimum_acceptance_criteria` 为空，Verification 直接通过，不调用 LLM，也不调用验证 Tool；Runtime 将 GoalState 设为 `ACHIEVED` 并交付原始 `final_response_draft`。
- 非空验收标准必须进入 VerificationAgent 判断；不得因为任务看起来简单而绕过。
- 最多 2 个 verification round。
- 如果问题可修复且预算未耗尽：丢弃旧草稿，将验证反馈作为 observation，回到 `REASONING`。
- 如果问题不可修复，但现有草稿真实、明确说明未达到或部分达到：使用该草稿完成，GoalState 为 `PARTIALLY_ACHIEVED` 或 `NOT_ACHIEVED`。
- 如果问题不可修复且草稿包含虚假完成声明、与产物矛盾或不能安全交付：返回一次受预算限制的普通 `REASONING`，把 verdict 作为 observation，要求模型生成诚实的 `SUBMIT_RESULT`，然后重新验证。
- 所有 Verification 返回执行的路径都受 verification round 和 Runtime 总迭代预算约束，不得无限循环。
- 验证 Provider 连续失败属于 Runtime 流程失败：`FAILED + NOT_ACHIEVED`。

## 13. 验证工具

第一版只提供以下只读工具：

```text
artifact_exists
document_read
tool_observation_check
```

### 13.1 可见性

VerificationAgent 可见工具集合：

```text
ToolRegistry 已注册
∩ Task capability scope
∩ role visibility
∩ verification whitelist
```

验证阶段不得看到或调用：

```text
document_write
camera_scene
screen_scene
web_search
web_page_read
plan_written
ask_user_question
```

### 13.2 工具语义

- `artifact_exists`：只检查受控输出目录中的安全相对引用。
- `document_read`：只读受控文档根目录，限制字节数和内容长度。
- `tool_observation_check`：查询已经持久化的 observation，不执行原 Tool。

不得为验证新增非标准 `ToolDefinition.produces` 字段。产物关系由 Intent、ToolResult、observation 和验证上下文表达。

## 14. 推理与工具执行状态统一

不增加 `VERIFYING`、`VERIFICATION_TOOL_EXECUTION`、`DRAFTING` 等 Task 状态。

- 所有模型调用统一处于 `REASONING`。
- 所有 Tool 调用统一处于 `TOOL_EXECUTION`。

为了准确恢复，checkpoint 必须保存 continuation metadata：

```text
pending_reasoning.purpose:
- first_decision
- execution
- verification

pending_tool.purpose:
- execution
- verification
```

Purpose 不是新的状态，只用于恢复时定位下一动作。

## 15. Tool 结果与失败

- Tool 成功结果保存为 observation。
- 所有 Tool 失败归一化为结构化 failure，不伪装成成功 ToolResult。
- 参数校验失败、权限不足、环境不可用、工具内部失败采用现有分类和 Step retry 规则。
- 带副作用 Tool 在中断后无法确认结果时进入 `UNCERTAIN`。
- Tool 的内容缺失、不匹配或检索不到不是流程失败；模型根据 observation 判断是否继续检索、询问用户或提交未达到结果。
- camera_scene 已成功产生 observation 但信息不足时，不重复拍摄；模型应说明未观察到什么。

## 16. 暂停、恢复与取消

### 16.1 暂停

- 控制面发出 `PAUSE_REQUESTED`。
- Runtime 在安全 checkpoint 边界进入 `PAUSED`。
- checkpoint 记录暂停前真实状态和 continuation metadata。

### 16.2 恢复

- 恢复完全由 `TaskExecutionState` 和最新 checkpoint 决定。
- 若暂停前为 `REASONING`，恢复为 `REASONING` 并按 checkpoint 语义重做或续接该推理边界。
- 若暂停前为 `TOOL_EXECUTION`，依据 Tool 副作用策略恢复；不得由 GoalState 决定。
- `KILLED` 不可恢复。

### 16.3 取消

- 全局控制 worker 定位 Task 并发送 `KILL_REQUESTED`。
- 控制 worker 可中断处于阻塞等待中的 Task worker。
- 取消后进入 `KILLED`，GoalState 为 `NOT_ACHIEVED`。

## 17. Worker 与调度

- 采用固定 worker，最大数量 500，可复用。
- 一个 Task worker 一次独占一个 Task，直到 Task 进入终态后才可接收下一任务。
- `ask_user_question` 阻塞期间 worker 不释放，避免任务进度所有权漂移。
- 没有空闲 worker 时 Task 保留在队列中。
- 单个 Task 的可见 Skill/Tool 和权限来自该 Task capability scope，不使用全局权限快照代替。

## 18. Checkpoint 与恢复

checkpoint 至少保存：

```text
Task 原始输入与标识
TaskExecutionState
TaskGoalState
terminal_execution_state
TaskIntent
Plan/TaskGraph version 与 node runs
observations 与 failures
pending Action
pending_reasoning / pending_tool purpose
candidate_result
draft_final_response
verification round/results/verdict
completion package
delivery status
```

恢复规则：

- 永远从该 Task 最新有效 checkpoint 恢复。
- 推理开始前有 checkpoint、推理中退出：重新执行该次推理。
- 推理结果已校验并随 pending Action 落盘：不重复推理，继续 Action。
- 只读验证 Tool 的结果已落盘：不重复执行。
- Tool 执行前或完成后创建 checkpoint；执行中的副作用不确定使用 `UNCERTAIN`。
- 新版本不迁移旧 checkpoint；切换时清理旧任务数据。

## 19. Trace 与可观测性

Trace 必须记录：

- Task 创建、入队、获取和终态；
- First Decision 开始、结束、重试和失败；
- Intent 写入；
- 每次 Action；
- Tool 调用、参数、结果引用和 failure；
- Plan version 和 node 状态变化；
- SUBMIT_RESULT 中的任务摘要、回答草稿和证据引用；
- Verification decision、Tool 和 verdict；
- ExecutionState 与 GoalState 的每次变化；
- checkpoint sequence 和恢复来源；
- completion 与 delivery。

Trace 不保存 API key、认证头、原始敏感媒体或隐藏推理链。

## 20. Timing

删除独立 `task_formulation` timing。至少保留：

```text
input_to_task_submitted
queue_wait
llm:first_decision
llm:execution_decision
llm:verification_decision
tool:<tool_name>
verification_total
runtime_execution
end_to_end
```

LLM 总耗时和 Tool 总耗时是子项求和，不得与阶段 wall time 混作互斥分段。

## 21. 前端投影

前端分别展示：

```text
Execution State
Goal State
Terminal Execution State（DELIVERED 时）
```

活跃任务的 Goal State 显示为“待验收”，但底层值仍为 `None`。

前端控制规则继续由 ExecutionState 决定：

- 活跃任务可请求暂停或取消；
- `PAUSE_REQUESTED`、`PAUSED` 不可重复暂停；
- 只有 `PAUSED` 可恢复；
- 终态不可恢复或重复取消。

## 22. 删除项

实现时必须删除生产链路中的：

- 独立 TaskFormulator 调用；
- Task formulation PromptType、Trace、Timing 和 UI 展示；
- `FORMULATING`、`PLANNING`、`REPLANNING`、`RUNNING`、`SUCCEEDED`、`WAITING`；
- `COMPLETE`、`REPLAN`、`WAIT` Action；
- 关键词意图识别和固定 goal fallback；
- 通过 strategy mode 决定是否规划；
- 旧 checkpoint 兼容迁移。

## 23. 非目标

本阶段不实现：

- Goal 在 Task 执行中动态改写；
- 多问题同时等待（接口保留，最大数量仍为 1）；
- 分布式 worker 或跨进程调度；
- 推理流式续传；
- 浏览器已读 ACK；
- 任意写操作型验证工具；
- `ToolDefinition.produces`；
- 旧状态和旧 checkpoint 兼容层。

## 24. 建议 PR 拆分

### PR 1：双状态数据契约

- 新增 TaskGoalState。
- 收敛 TaskExecutionState。
- 增加 terminal_execution_state。
- 更新序列化、Trace 和状态转换单测。

### PR 2：First Decision 替代 Task Formulation

- Task 允许 goal=None 入队。
- 新增 First Decision 协议和 Prompt。
- 删除生产 TaskFormulator 链路、关键词 fallback 及相关 timing/UI trace。

### PR 3：统一 Action 与内部规划能力

- 只保留 CALL_TOOL、SUBMIT_RESULT。
- 删除 COMPLETE、REPLAN、WAIT。
- plan_written/plan update 走 Runtime capability。

### PR 4：回答草稿与 VerificationAgent

- SUBMIT_RESULT 同时生成 completion_summary 和 final_response_draft。
- 删除独立 FinalResponseGenerator 及 FINAL_RESPONSE LLM 调用。
- 新增 VerificationAgent、VERIFICATION_DECISION 和 verdict。
- Runtime 提交 GoalState。

### PR 5：只读验证工具

- 新增 artifact_exists、document_read、tool_observation_check。
- 实现严格白名单和受控路径。

### PR 6：Checkpoint 与恢复

- 持久化双状态、Intent、pending purpose、草稿和验证进度。
- 覆盖推理中断、Action 已落盘、验证 Tool 已完成等恢复场景。

### PR 7：前端、Trace 与 Timing 投影

- 展示双状态和 terminal execution state。
- 展示验证过程与新 timing。
- 删除 task formulation 展示。

## 25. 测试要求

至少覆盖：

- Task 可在 `goal=None` 时入队。
- First Decision 一次产生 Intent 和首个 Action。
- 意图不清晰时调用 ask_user_question，回答后重试 First Decision。
- First Decision 失败最多重试 2 次。
- 简单任务直接 CALL_TOOL 或 SUBMIT_RESULT。
- 复杂任务通过 plan_written 创建计划。
- Replan 不修改 Intent。
- SUBMIT_RESULT 不直接进入 COMPLETED。
- SUBMIT_RESULT 缺少非空 final_response_draft 时进入 decision repair。
- Plan Graph 结束但尚未 SUBMIT_RESULT 时只自动安排一次普通 Reasoning。
- React Tool 完成不会触发 Plan Graph 的自动汇总规则。
- 实际回答草稿进入验证上下文，Verification 通过后不再次生成回答。
- minimum_acceptance_criteria 为空时 Verification 确定性直接通过且不调用 LLM。
- minimum_acceptance_criteria 非空时必须执行 VerificationAgent 判断。
- VerificationAgent 只能调用白名单只读工具。
- 验证失败可返回执行，最多 2 轮。
- GoalState 只有三种终值，活跃期为 None。
- KILLED 和 UNCERTAIN 均为 NOT_ACHIEVED。
- COMPLETED、FAILED、KILLED、UNCERTAIN 可交付为 DELIVERED。
- DELIVERED 保留 terminal_execution_state 和 GoalState。
- 恢复只依据 ExecutionState 和 checkpoint continuation metadata。
- 推理中断会重做当前推理；已落盘 Action 不重复推理。
- 已持久化的只读验证 Tool 不重复执行。
- 不加载旧 checkpoint。
- Trace 足以还原任务、动作、验证、状态和恢复链路。
- 全量测试和 `python main.py` 保持可运行。

## 26. 验收标准

- 生产链路中不存在独立 Task Formulation 阶段。
- 第一次决策同时识别意图并选择 Action。
- 规划通过内部 capability 完成，不再依赖 strategy mode。
- Runtime 状态和目标状态职责完全分离。
- 模型通过 SUBMIT_RESULT 同时提交摘要与完整回答草稿。
- 生产链路中不存在独立 FinalResponseGenerator 或无条件 FINAL_RESPONSE LLM 调用。
- Plan 与 React 的结束判定严格分离，不会把 React 的单次 Tool 完成误判为任务结束。
- 所有任务都经过 Verification 边界；空验收标准确定性通过，非空验收标准由 VerificationAgent 判断。
- 机械验证由模型选择只读验证工具完成。
- Verification 通过后直接交付已验证草稿。
- Runtime 能从最新 checkpoint 按真实执行阶段恢复。
- 用户看到的最终状态能区分流程结果、目标达成和交付结果。

# Ella Task Runtime 渐进式重构方案

## 1. 目的

Ella 当前仍由 `demo/cli_demo.py` 手动编排完整任务流程：

```text
run_demo()
  → Event Trigger Pipeline
  → Event Router
  → PresenceRuntime
  → HandoffRequest
  → TaskSession
  → SubAgent
  → CapabilityExecutor
  → TaskCompletionPackage
  → MemoryManager
```

目标是让调用方只提交事件或任务，由长期存在的 Runtime 管理任务生命周期：

```text
RawSignal
  → EventRuntime.publish()
  → TaskRuntime.submit(handoff)
  → TaskRuntime 管理 Session、规划、执行、重规划、完成和 Memory
```

`TaskRuntime` 是应用级任务总控，不是每个任务创建一个实例。每个任务仍创建独立的
`TaskSession` 和 `AgentExecutionContext`。

## 2. 当前已完成能力

以下能力已经存在，本重构不得重复实现：

- Event Trigger Pipeline。
- Session-aware Event Router。
- Presence Queue 和 PresenceRuntime。
- InterruptionPolicy。
- Task Formulation 和 HandoffRequest。
- TaskSessionManager、TaskSession 和 AgentExecutionContext。
- SubAgent 和 StrategyDecision。
- SkillManager、ToolManager 和热插拔能力目录。
- CapabilityExecutor。
- UserVisibleAgentOutput 和 TaskCompletionPackage。
- MemoryManager。
- CLI going_out demo 和 runtime contract tests。

当前缺少：

- 应用级 TaskRuntime。
- TaskRuntime 管理的任务队列与 Session 索引。
- 自动 TaskState 推进。
- 一次只执行一个动作的执行决策。
- 持续规划、执行、观察和重规划循环。
- 应用级 EventRuntime。
- 只负责输入输出的精简 demo。

## 3. 全局实施规则

本方案必须按下列步骤依次实施。每一步对应一个独立 PR。

每个 PR 必须遵守：

- 一次只添加或修改一个生产模块。
- 只修改该步骤列出的允许文件。
- 不修改任何未列出的源码、测试、文档或配置。
- 不修改 `__init__.py`；调用方和测试直接从具体模块导入。
- 不顺手修复、重命名或格式化其他模块。
- 不提前实现后续步骤。
- 如果必须修改列表外文件，立即停止并解释原因，不得自行扩大范围。
- 每一步结束后运行专项测试、`python -m pytest` 和 `python main.py`。
- 每一步合并后，现有 CLI demo 必须继续可运行。

## 4. Step 1：扩展 TaskSession 状态模型

### 单一目标

只让 TaskSession 能表达和校验任务生命周期状态，不创建 TaskRuntime，不执行任务。

### 允许文件

```text
sessions/session.py
tests/sessions/test_task_state_machine.py
```

### 修改内容

- 扩展 `TaskState`：

```text
CREATED
PLANNING
RUNNING
REPLANNING
WAITING
COMPLETED
FAILED
CANCELLED
```

- 在 `TaskSession` 中增加：
  - `current_strategy`
  - `completion`
  - `failure_reason`
- 增加 `transition_to(next_state)`。
- 只允许以下状态转换：

```text
CREATED → PLANNING
PLANNING → RUNNING | WAITING | FAILED | CANCELLED
RUNNING → REPLANNING | WAITING | COMPLETED | FAILED | CANCELLED
REPLANNING → RUNNING | WAITING | FAILED | CANCELLED
WAITING → PLANNING | CANCELLED
```

- `COMPLETED`、`FAILED`、`CANCELLED` 是终止状态，不能再转换。

### 不要修改

```text
sessions/session_manager.py
sessions/subagent.py
sessions/executor.py
sessions/strategy.py
runtime/*
demo/*
```

### 验证

```bash
python -m pytest tests/sessions/test_task_state_machine.py
python -m pytest
python main.py
```

## 5. Step 2：增加单步 ExecutionDecision 数据契约

### 单一目标

只定义“SubAgent 下一步想做什么”的数据对象，不修改 SubAgent 或 Executor。

### 允许文件

```text
sessions/decision.py
tests/sessions/test_execution_decision.py
```

### 修改内容

- 定义 `ExecutionDecision`：

```python
@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    action: str
    tool_name: str | None
    tool_input: dict[str, object] | None
    reason: str
    is_complete: bool
```

- 支持的 `action`：

```text
CALL_TOOL
COMPLETE
WAIT
REPLAN
```

- `CALL_TOOL` 必须包含 `tool_name`。
- `COMPLETE` 不得同时包含 `tool_name`。
- 增加基础序列化测试。

### 不要修改

```text
sessions/__init__.py
sessions/subagent.py
sessions/executor.py
sessions/session.py
runtime/*
demo/*
```

### 验证

```bash
python -m pytest tests/sessions/test_execution_decision.py
python -m pytest
python main.py
```

## 6. Step 3：让 SubAgent 只生成一个下一步决策

### 单一目标

只增加 SubAgent 的单步决策能力，不执行 Tool，不推进 TaskState。

### 允许文件

```text
sessions/subagent.py
tests/sessions/test_subagent_decision.py
```

### 修改内容

- 保留现有 `select_strategy()`。
- 新增 `decide_next_action()`，输入：
  - HandoffRequest
  - AgentExecutionContext
  - TaskSession
  - 当前 StrategyDecision
- 返回一个 `ExecutionDecision`。
- 第一版允许使用确定性 going_out 规则。
- 不得直接调用 ToolManager 或 Tool。
- 不得循环生成多个动作。
- 不得生成 TaskCompletionPackage 或写 Memory。

### 不要修改

```text
sessions/decision.py
sessions/executor.py
sessions/session.py
skill/*
tools/*
runtime/*
demo/*
```

### 验证

```bash
python -m pytest tests/sessions/test_subagent_decision.py
python -m pytest
python main.py
```

## 7. Step 4：将 CapabilityExecutor 改为单动作执行器

### 单一目标

只让 CapabilityExecutor 执行一个 ExecutionDecision，不再遍历所有 `allowed_tools`。

### 允许文件

```text
sessions/executor.py
tests/sessions/test_capability_executor.py
```

### 修改内容

- `execute()` 每次只接收一个 `ExecutionDecision`。
- `CALL_TOOL` 时通过 ToolManager 实时解析并执行一个 Tool。
- `allowed_tools` 只表示权限上限，不表示执行顺序。
- Tool 不存在或已移除时返回结构化 `replan_required=True`。
- Skill 已移除时返回结构化 `replan_required=True`。
- `COMPLETE`、`WAIT`、`REPLAN` 不调用 Tool。
- Executor 不自动循环。
- Executor 不修改 TaskSession 状态。
- Executor 不生成 UserVisibleAgentOutput、TaskCompletionPackage 或 Memory 请求。

### 不要修改

```text
sessions/decision.py
sessions/subagent.py
sessions/session.py
skill/*
tools/*
runtime/*
demo/*
```

### 验证

```bash
python -m pytest tests/sessions/test_capability_executor.py
python -m pytest
python main.py
```

## 8. Step 5：增加 TaskRuntime 的任务提交边界

### 单一目标

只实现 TaskRuntime 接收任务、创建 Session 和维护索引，不进行规划或执行。

### 允许文件

```text
runtime/task_runtime.py
tests/runtime/test_task_runtime_submission.py
```

### 修改内容

- 在同一模块定义：

```python
TaskHandle
TaskRuntimeResult
TaskRuntime
```

- `TaskRuntime` 是应用级长期对象。
- `submit(handoff)` 调用现有 TaskSessionManager。
- 保存：

```text
task_id → TaskSessionCreation
session_id → TaskSessionCreation
```

- `submit()` 返回 `TaskHandle(task_id, session_id, trace_id)`。
- 增加 `get_session(task_id)` 和 `get_context(task_id)`。
- 重复 task/session ID 必须拒绝。
- 此步骤只产生 CREATED Session。

### 不要修改

```text
runtime/__init__.py
sessions/*
agent/*
skill/*
tools/*
memory/*
demo/*
main.py
```

### 验证

```bash
python -m pytest tests/runtime/test_task_runtime_submission.py
python -m pytest
python main.py
```

## 9. Step 6：给 TaskRuntime 增加单步状态推进

### 单一目标

只在 TaskRuntime 中实现 `step()`，每次调用最多推进一个状态或执行一个动作。

### 允许文件

```text
runtime/task_runtime.py
tests/runtime/test_task_runtime_step.py
```

### 修改内容

- `CREATED`：转换到 `PLANNING`。
- `PLANNING`：调用 SubAgent 选择策略，保存到 Session，然后转换到 `RUNNING`。
- `RUNNING`：调用 SubAgent 生成一个 ExecutionDecision，再让 CapabilityExecutor 执行一次。
- ToolResult 追加到当前 Session 的 `tool_trace`。
- Executor 请求重新规划时转换到 `REPLANNING`。
- `REPLANNING`：重新读取最新 Skill/Tool 能力并生成新策略。
- `WAIT` 决策转换到 `WAITING`。
- `COMPLETE` 决策暂时只记录“可完成”，不要在本步骤生成 CompletionPackage。
- 终止状态调用 `step()` 必须被拒绝。

### 不要修改

```text
sessions/*
agent/*
skill/*
tools/*
memory/*
runtime/presence_runtime.py
runtime/event_router.py
demo/*
```

### 验证

```bash
python -m pytest tests/runtime/test_task_runtime_step.py
python -m pytest
python main.py
```

## 10. Step 7：给 TaskRuntime 增加同步运行循环

### 单一目标

只增加循环驱动接口，不生成 Completion，不写 Memory。

### 允许文件

```text
runtime/task_runtime.py
tests/runtime/test_task_runtime_loop.py
```

### 修改内容

- 新增 `run_until_blocked(task_id, max_steps)`。
- 内部重复调用 `step()`。
- 遇到以下情况停止：
  - WAITING
  - COMPLETED
  - FAILED
  - CANCELLED
  - 当前无可执行动作
  - 达到 max_steps
- 达到 max_steps 时返回结构化失败或阻塞结果，禁止无限循环。
- 不实现线程、asyncio 或多任务并发。

### 不要修改

```text
sessions/*
agent/*
skill/*
tools/*
memory/*
runtime/event_runtime.py
demo/*
```

### 验证

```bash
python -m pytest tests/runtime/test_task_runtime_loop.py
python -m pytest
python main.py
```

## 11. Step 8：在 TaskRuntime 中收口 Completion

### 单一目标

只让 TaskRuntime 在任务完成时生成用户输出和 TaskCompletionPackage，不调用 MemoryManager。

### 允许文件

```text
runtime/task_runtime.py
tests/runtime/test_task_runtime_completion.py
```

### 修改内容

- COMPLETE 决策后生成 `UserVisibleAgentOutput`。
- 使用同一个 AgentExecutionContext 生成 `TaskCompletionPackage`。
- CompletionPackage 包含当前 Session 收集到的 ToolResult。
- 将 CompletionPackage 保存到 TaskSession。
- 将 Session 转换为 COMPLETED。
- `TaskRuntimeResult` 返回 CompletionPackage。
- 不在此步骤调用 MemoryManager。

### 不要修改

```text
sessions/completion.py
sessions/output.py
memory/*
sessions/*
agent/*
skill/*
tools/*
demo/*
```

### 验证

```bash
python -m pytest tests/runtime/test_task_runtime_completion.py
python -m pytest
python main.py
```

## 12. Step 9：在 TaskRuntime 中接入 MemoryManager

### 单一目标

只让已经完成的任务通过现有 MemoryManager 收口，不改变 MemoryManager 行为。

### 允许文件

```text
runtime/task_runtime.py
tests/runtime/test_task_runtime_memory.py
```

### 修改内容

- TaskRuntime 长期持有一个 MemoryManager 引用。
- CompletionPackage 生成后创建 MemoryManagementRequest。
- 只通过 MemoryManager 写入 Memory。
- 保存 MemoryWriteResult。
- Memory 写入失败时：
  - 保留 CompletionPackage。
  - 将 RuntimeResult 标记为失败。
  - 返回明确 failure reason。
- 新增 `run_until_complete(task_id, max_steps)` 便利接口。

### 不要修改

```text
memory/manager.py
sessions/completion.py
sessions/output.py
sessions/*
agent/*
skill/*
tools/*
demo/*
```

### 验证

```bash
python -m pytest tests/runtime/test_task_runtime_memory.py
python -m pytest
python main.py
```

## 13. Step 10：增加 EventRuntime

### 单一目标

只把 RawSignal 到 TaskRuntime.submit() 的事件入口收进一个应用级 EventRuntime。

### 允许文件

```text
runtime/event_runtime.py
tests/runtime/test_event_runtime.py
```

### 修改内容

- EventRuntime 长期持有：
  - EventTriggerPipeline
  - SessionAwareEventRouter
  - PresenceQueue
  - PresenceRuntime
  - MainAgent
  - TaskRuntime
- `publish(raw_signal)` 处理完整事件入口。
- 只有 PRESENCE_QUEUE 且被 InterruptionPolicy 允许的事件才能创建 HandoffRequest。
- HandoffRequest 必须交给 `TaskRuntime.submit()`。
- SESSION_INBOX、AMBIENT_STATE 和 SUPPRESSED 不创建新任务。
- 返回 TaskHandle 或明确的未提交结果。
- EventRuntime 不选择 Skill、不调用 Tool、不生成 Completion。

### 不要修改

```text
runtime/task_runtime.py
runtime/presence_runtime.py
runtime/event_router.py
events/*
agent/*
sessions/*
skill/*
tools/*
memory/*
demo/*
```

### 验证

```bash
python -m pytest tests/runtime/test_event_runtime.py
python -m pytest
python main.py
```

## 14. Step 11：简化 CLI Demo

### 单一目标

只删除 demo 的内部流程编排，让它调用 EventRuntime 和 TaskRuntime 的公共接口。

### 允许文件

```text
demo/cli_demo.py
tests/demo/test_cli_demo.py
```

### 修改内容

- `DemoRuntime.create_default()` 只负责应用启动装配。
- `run_demo()`：
  1. 创建 CLI RawSignal。
  2. 调用 `event_runtime.publish(signal)`。
  3. 调用 `task_runtime.run_until_complete(task_id)`。
  4. 渲染 CompletionPackage 中的 UserVisibleAgentOutput 和 Memory 状态。
- 删除 demo 中以下直接调用：
  - Event Router 内部编排。
  - Presence Queue 消费编排。
  - MainAgent.create_handoff()。
  - TaskSessionManager.create_session()。
  - SubAgent.select_strategy()。
  - CapabilityExecutor.execute()。
  - TaskCompletionPackage 构造。
  - MemoryManager.handle()。
- 保持 `python main.py` 的现有用户可见输出格式。

### 不要修改

```text
main.py
runtime/*
events/*
agent/*
sessions/*
skill/*
tools/*
memory/*
README.md
```

### 验证

```bash
python -m pytest tests/demo/test_cli_demo.py
python -m pytest
python main.py
```

## 15. Step 12：增加最终架构契约测试

### 单一目标

只增加测试，确认 demo 不再手动编排任务生命周期，不修改任何生产代码。

### 允许文件

```text
tests/contracts/test_task_runtime_pipeline.py
```

### 测试内容

- EventRuntime 是 RawSignal 的应用入口。
- TaskRuntime 是应用级单一任务总控。
- 每个提交任务创建独立 TaskSession 和 AgentExecutionContext。
- TaskRuntime 管理状态推进、重规划、Completion 和 Memory。
- Skill/Tool 热插拔对当前 Session 生效。
- demo 不直接创建 TaskSession、选择 Skill、调用 Tool 或写 Memory。
- 两个 TaskSession 的状态、历史和 ToolResult 不互相污染。

### 不要修改

```text
任何生产代码
任何已有测试
任何文档
任何配置文件
```

### 验证

```bash
python -m pytest tests/contracts/test_task_runtime_pipeline.py
python -m pytest
python main.py
```

## 16. 最终目标形态

全部步骤完成后，外部流程应收敛为：

```python
handle = event_runtime.publish(raw_signal)
result = task_runtime.run_until_complete(handle.task_id)
print(result.completion.user_visible_output)
```

职责关系：

```text
EllaRuntime（应用级）
├── EventRuntime（应用级事件入口）
├── TaskRuntime（应用级任务总控）
│   ├── TaskSession A（任务级）
│   ├── TaskSession B（任务级）
│   └── TaskSession C（任务级）
├── SkillManager（应用级能力目录）
├── ToolManager（应用级能力目录）
└── MemoryManager（应用级 Memory 入口）
```

核心原则：

> TaskRuntime 管理任务，TaskSession 承载任务，SubAgent 决定下一步，Executor 只执行一个动作。

## 17. 本轮重构明确不包含

- 真实模型接入。
- 摄像头或麦克风接入。
- ASR、TTS 或真实天气 API。
- asyncio 和多任务并发。
- 分布式任务队列。
- Skill 权限管理。
- Tool 运行中强制取消。
- 高级 Memory 检索。
- 多 Agent 协作。

这些能力必须在 TaskRuntime 单进程同步状态机稳定后，再分别拆成独立 PR。

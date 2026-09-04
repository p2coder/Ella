> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella Runtime MVP PR 实施计划

本文档定义 Ella Runtime MVP 的 Pull Request 拆分计划与提交规范。后续实现应以 `docs/prd.md` 和 `docs/architecture.md` 作为产品与架构基线，并通过小粒度 PR 逐步落地。

MVP 的实现目标不是一次性做完整生活伴侣，而是证明以下 Runtime 闭环可以端到端跑通：

```text
Raw Signal
→ Event Trigger Pipeline
→ Configurable Event Stages
→ Session-aware Event Router
→ Configurable Route Destinations
→ Presence Runtime
→ Interruption Policy
→ Task Formulation
→ Task Handoff
→ TaskSessionManager
→ TaskSession
→ AgentExecutionContext
→ SubAgent
→ Task Decomposition / Execution Strategy Selection
→ Task Execution
→ TaskCompletionPackage
→ Memory Manager
→ Back to Presence Runtime
```

## Implementation Principles

- 每个 PR 只做一件事：一个新能力、一个架构层、或一个明确的测试增强。
- 每个 PR 合并后，`main` 分支必须保持可运行、可验证。
- 先落数据契约和生命周期骨架，再接 mock skill、mock tools 和 CLI demo。
- MVP 中不接入真实视觉、听觉、TTS、真实天气 API、高级 Memory、多 Agent 并发或 MCP。
- `Task Formulation` 只决定任务目标；执行方式由 TaskSession 内部的 SubAgent 决定。
- `AgentExecutionContext` 由 TaskSessionManager 在创建 TaskSession 后、唤起 SubAgent 前构造。
- `MemoryManager` 负责接收带 context 的任务完成信息，并决定如何管理 memory。
- 当前 MVP 代码直接放在仓库根目录下，不再额外创建小写 `ella/` 包目录。也就是说，`main.py`、`runtime/`、`events/`、`agent/` 等目录直接位于 `Ella/` 根目录内。

## PR Breakdown

### PR 1: docs: freeze PRD and architecture baseline

#### Title

冻结 Ella Runtime MVP 的 PRD、架构和 PR 实施基线。

#### Goal

让后续工程实现有稳定的中文产品定义、架构边界和 PR 拆分依据。

#### Feature Description

该 PR 只整理文档，不实现 Runtime 代码。它明确 Ella MVP 做什么、不做什么，以及事件系统、Presence Runtime、TaskSession、SubAgent、Skill Registry、Prompt Engine、MemoryManager 和用户可见输出的职责边界。

#### Implementation Approach

更新并校准 `docs/prd.md`、`docs/architecture.md` 和 `docs/pr_plan.md`，确保三份文档对主链路、核心对象、旁路基础设施、UI 输出层级和 PR 提交约定的描述一致。

#### Files to Create or Modify

- `docs/prd.md`
- `docs/architecture.md`
- `docs/pr_plan.md`
- `README.md`

#### Out of Scope

- 不创建运行时代码结构。
- 不实现事件、会话、工具、Memory 或 demo 代码。
- 不引入真实外部 API。

#### Test Method

人工阅读三份文档，确认术语一致，并检查 README 是否能正确指向文档入口。

#### Acceptance Criteria

- [ ] PRD 清楚说明 MVP 是 Runtime 骨架验证。
- [ ] Architecture 清楚说明 TaskSession、SubAgent 和 AgentExecutionContext 的关系。
- [ ] PR plan 包含完整 PR 拆分和 PR 提交规范。
- [ ] 文档中不包含已移出 MVP 的执行机制。

#### Main Branch Runnable Check

该 PR 为文档 PR。合并后确认仓库仍可正常打开，文档链接有效，且没有引入会破坏后续根目录代码结构的目录或命名冲突。

### PR 2: chore(project): add root runtime skeleton and test harness

#### Title

创建 Ella Runtime MVP 的根目录代码骨架和基础测试环境。

#### Goal

为后续每个功能 PR 提供可运行、可测试、可持续演进的最小工程结构。

#### Feature Description

该 PR 增加根目录代码结构、`tests/` 目录和基础项目配置，让后续模块可以按架构文档中的目录逐步填充。

#### Implementation Approach

创建最小根目录模块结构、测试配置和空入口。保持模块实现为空或最小占位，仅保证基础 smoke test 可以通过。

#### Files to Create or Modify

- `pyproject.toml`
- `main.py`
- `tests/test_imports.py`
- `.gitignore`

#### Out of Scope

- 不实现事件模型。
- 不实现 Runtime loop。
- 不实现 demo 行为。

#### Test Method

运行：

```bash
python -m pytest
python main.py
```

#### Acceptance Criteria

- [ ] 根目录入口和基础模块可以被加载。
- [ ] 测试命令可以执行。
- [ ] `python main.py` 不报错。
- [ ] 没有引入与 Runtime 行为相关的未完成逻辑。

#### Main Branch Runnable Check

合并后在干净环境运行 `python -m pytest` 和 `python main.py`，确认主分支仍处于可执行状态。

### PR 3: feat(events): add core event data models

#### Title

新增 Ella Runtime 的核心事件数据对象。

#### Goal

建立 RawSignal、Observation、EventCandidate、StandardizedEvent 和 EventStage 等可扩展事件契约。

#### Feature Description

该 PR 提供事件系统的基础数据模型，使后续事件触发、标准化和路由可以基于稳定结构实现。事件阶段和事件类型必须便于增加、删除和替换。

#### Implementation Approach

使用 dataclass 或等价结构定义事件对象，并通过可配置枚举、字符串常量或 registry key 表达事件阶段，避免把 `Observation / Event Candidate / Standardized Event` 写死成不可扩展流程。

#### Files to Create or Modify

- `events/__init__.py`
- `events/signal.py`
- `events/observation.py`
- `events/event.py`
- `events/stage.py`
- `tests/events/test_event_models.py`

#### Out of Scope

- 不实现事件路由。
- 不实现 Presence Runtime。
- 不接入真实输入源。

#### Test Method

运行：

```bash
python -m pytest tests/events/test_event_models.py
```

#### Acceptance Criteria

- [ ] 事件对象能表达原始信号、观察结果、候选事件和标准化事件。
- [ ] 事件阶段可配置，后续可新增或移除阶段。
- [ ] 事件对象包含 trace、source、timestamp、payload 等必要字段。
- [ ] 单元测试覆盖对象构造和基础序列化。

#### Main Branch Runnable Check

合并后运行全量 `python -m pytest`，确认现有 import smoke test 和事件模型测试都通过。

### PR 4: feat(events): add trigger pipeline and configurable stages

#### Title

实现可配置的事件触发管线和事件阶段注册机制。

#### Goal

让 RawSignal 能通过可调整的阶段链路转换为后续可路由的标准事件。

#### Feature Description

该 PR 增加 Event Trigger Pipeline，用于把输入源产生的 RawSignal 转换为 Observation、EventCandidate 或 StandardizedEvent。阶段列表应可配置，方便后续增删类型或替换处理逻辑。

#### Implementation Approach

实现 `EventStageRegistry` 或等价机制，允许按配置顺序执行事件阶段处理器。MVP 可先提供 mock stage，例如 CLI 文本输入到标准化用户事件的转换。

#### Files to Create or Modify

- `events/source.py`
- `events/trigger_pipeline.py`
- `events/stage.py`
- `tests/events/test_trigger_pipeline.py`

#### Out of Scope

- 不实现 Session-aware Event Router。
- 不接入真实 camera、microphone、ASR 或 vision。
- 不做复杂事件去重、优先级排序或长期日志存储。

#### Test Method

运行：

```bash
python -m pytest tests/events/test_trigger_pipeline.py
```

#### Acceptance Criteria

- [ ] pipeline 可按配置加载阶段。
- [ ] 阶段可以独立测试。
- [ ] mock CLI 输入可以转换为标准化事件。
- [ ] 新增或移除阶段不需要改主流程代码。

#### Main Branch Runnable Check

合并后运行 `python -m pytest`，并确认已有事件模型测试仍通过。

### PR 5: feat(runtime): add session-aware event router and presence queue

#### Title

新增 Session-aware Event Router、路由目的地和 Presence Queue。

#### Goal

把标准化事件按照当前会话状态路由到 SESSION_INBOX、AMBIENT_STATE、SUPPRESSED 或 PRESENCE_QUEUE。

#### Feature Description

该 PR 实现事件进入 Presence Runtime 前的路由层。Router 根据事件类型、活跃 TaskSession、环境更新属性和打扰策略前置条件，将事件送往不同目的地。

#### Implementation Approach

实现可配置 `RouteDestinationRegistry` 或等价机制。默认目的地包括：

```text
SESSION_INBOX
AMBIENT_STATE
SUPPRESSED
PRESENCE_QUEUE
```

Router 不直接执行任务，只决定事件应该进入哪个目的地。

#### Files to Create or Modify

- `runtime/event_router.py`
- `runtime/event_queue.py`
- `runtime/ambient_state.py`
- `tests/runtime/test_event_router.py`

#### Out of Scope

- 不实现 Task Formulation。
- 不实现 TaskSession 具体执行。
- 不接入 MemoryManager。

#### Test Method

运行：

```bash
python -m pytest tests/runtime/test_event_router.py
```

#### Acceptance Criteria

- [ ] Router 支持四个默认目的地。
- [ ] 路由目的地可配置，后续可新增或删除。
- [ ] 活跃 TaskSession 相关事件可进入 SESSION_INBOX。
- [ ] 环境状态类事件可只更新 AMBIENT_STATE。
- [ ] 用户主动触发事件可进入 PRESENCE_QUEUE。

#### Main Branch Runnable Check

合并后运行 `python -m pytest`，确认事件 pipeline 和 router 测试可以共同通过。

### PR 6: feat(runtime): add presence runtime and interruption policy

#### Title

实现 Presence Runtime Loop 和最小打扰判断策略。

#### Goal

让进入 PRESENCE_QUEUE 的事件经过 Presence Runtime 和 Interruption Policy，再决定是否进入任务目标设定。

#### Feature Description

该 PR 增加 Ella 持续在场的主循环骨架。Presence Runtime 负责消费 Presence Queue 中的事件，并调用 Interruption Policy 判断是否应该响应、延迟、忽略或记录。

#### Implementation Approach

实现轻量 `PresenceRuntime` 和 `InterruptionPolicy`。MVP 中，用户主动输入如“Ella，我要出门了”应被允许进入 Task Formulation；被抑制事件只记录或丢弃。

#### Files to Create or Modify

- `runtime/presence_runtime.py`
- `runtime/interruption_policy.py`
- `tests/runtime/test_presence_runtime.py`
- `tests/runtime/test_interruption_policy.py`

#### Out of Scope

- 不实现完整长期 presence 感知。
- 不做复杂用户注意力建模。
- 不执行任务。

#### Test Method

运行：

```bash
python -m pytest tests/runtime/test_presence_runtime.py tests/runtime/test_interruption_policy.py
```

#### Acceptance Criteria

- [ ] PresenceRuntime 能消费 PRESENCE_QUEUE 事件。
- [ ] InterruptionPolicy 能区分用户主动触发和不应打扰事件。
- [ ] 允许处理的事件可以进入后续 Task Formulation 接口。
- [ ] 被抑制事件不会触发任务执行。

#### Main Branch Runnable Check

合并后运行全量 `python -m pytest`，确认主循环骨架不会破坏已有事件与路由测试。

### PR 7: feat(agent): add task formulation and handoff

#### Title

新增 Task Formulation 和 HandoffRequest。

#### Goal

让 Main Agent 能根据当前输入、用户偏好和环境摘要形成任务目标，并创建 HandoffRequest。

#### Feature Description

该 PR 实现 Main Agent 的任务入口能力。Task Formulation 只回答“这次任务目标是什么”，不选择 Skill、不制定完整执行策略、不调用工具。

#### Implementation Approach

实现 `TaskFormulation` 和 `HandoffRequest` 数据对象。Formulation 输入包括标准化事件、用户偏好摘要、Ambient State 和当前 Agent 输入；输出包括 goal、constraints、context summary 和 completion criteria。

#### Files to Create or Modify

- `agent/__init__.py`
- `agent/main_agent.py`
- `agent/formulation.py`
- `agent/handoff.py`
- `tests/agent/test_task_formulation.py`
- `tests/agent/test_handoff.py`

#### Out of Scope

- 不创建 AgentExecutionContext。
- 不创建 TaskSession。
- 不选择 Skill、Plan-to-Execute 或 ReAct。
- 不写 Memory。

#### Test Method

运行：

```bash
python -m pytest tests/agent/test_task_formulation.py tests/agent/test_handoff.py
```

#### Acceptance Criteria

- [ ] “Ella，我要出门了”可以形成出门前提醒目标。
- [ ] 输出目标包含约束和完成标准。
- [ ] HandoffRequest 包含目标、上下文、偏好和环境摘要。
- [ ] Main Agent 不执行具体任务。

#### Main Branch Runnable Check

合并后运行 `python -m pytest`，并确认 PresenceRuntime 到 HandoffRequest 的单元级链路可验证。

### PR 8: feat(sessions): add task session manager and execution context

#### Title

新增 TaskSessionManager、TaskSession 和 AgentExecutionContext。

#### Goal

建立隔离任务生命周期容器，并在唤起 SubAgent 前构造结构化执行上下文。

#### Feature Description

该 PR 实现任务执行前的会话层。TaskSession 是隔离任务空间，保存 task-local state、message history、tool trace 和 TaskState；AgentExecutionContext 由 TaskSessionManager 创建并传给后续 SubAgent。

#### Implementation Approach

实现 `TaskSessionManager.create_session()`、`TaskSession`、`TaskState` 和 `AgentExecutionContext`。context 应包含 agent_id、agent_role、parent_agent_id、session_id、task_id、trace_id、memory_scope、allowed_tools 和 permissions 等字段。

#### Files to Create or Modify

- `sessions/__init__.py`
- `sessions/session.py`
- `sessions/session_manager.py`
- `agent/context.py`
- `tests/sessions/test_session_manager.py`
- `tests/sessions/test_execution_context.py`

#### Out of Scope

- 不实现 SubAgent 执行逻辑。
- 不实现工具调用。
- 不实现 MemoryManager。
- 不做多 TaskSession 并发调度。

#### Test Method

运行：

```bash
python -m pytest tests/sessions/test_session_manager.py tests/sessions/test_execution_context.py
```

#### Acceptance Criteria

- [ ] TaskSessionManager 可以从 HandoffRequest 创建 TaskSession。
- [ ] AgentExecutionContext 在创建 TaskSession 后、唤起 SubAgent 前生成。
- [ ] context 能稳定携带 session_id、task_id 和 trace_id。
- [ ] TaskSession 不修改 Main Agent 全局状态。

#### Main Branch Runnable Check

合并后运行全量 `python -m pytest`，确认 agent handoff 与 session context 测试共同通过。

### PR 9: feat(skills): add skill registry and mock going_out skill

#### Title

新增 Skill Registry 和 mock going_out skill。

#### Goal

让 SubAgent 后续可以先读取候选 skill 摘要，再按需加载完整 SKILL.md。

#### Feature Description

该 PR 实现 Skill 加载模块。Skill 存储格式为 `skill/skills/<skill-name>/SKILL.md`。MVP 中提供 `going_out` skill，用于出门前提醒 demo。`skill/` 可以承载 registry、loader 等 skill 相关能力，`skill/skills/` 只存放具体 skill。

#### Implementation Approach

实现 Skill Registry 两阶段加载：

1. 初始 prompt 只加入候选 skill 的名称、描述和使用时机。
2. 当模型或策略选择某个 skill 后，再加载对应 `SKILL.md` 的完整内容。

MVP 默认候选 skill 收集方式为全部 skill。

#### Files to Create or Modify

- `registries/__init__.py`
- `skill/__init__.py`
- `skill/registry.py`
- `skill/loader.py`
- `skill/skills/going_out/SKILL.md`
- `tests/registries/test_skill_registry.py`

#### Out of Scope

- 不实现复杂 skill marketplace。
- 不实现在线安装 skill。
- 不实现多 skill 组合规划。
- 不执行 going_out skill。

#### Test Method

运行：

```bash
python -m pytest tests/registries/test_skill_registry.py
```

#### Acceptance Criteria

- [ ] Skill Registry 可以列出候选 skill 摘要。
- [ ] `going_out` 完整 SKILL.md 只在被选择后加载。
- [ ] skill_name 与 task_type 解耦。
- [ ] 新增 skill 文件夹不需要改主流程代码。

#### Main Branch Runnable Check

合并后运行 `python -m pytest`，确认 skill registry 测试和已有 runtime 测试都通过。

### PR 10: feat(execution): add subagent runner and strategy selection

#### Title

新增 SubAgent Runner 和任务执行策略选择。

#### Goal

让 TaskSession 内部的执行体能够基于 HandoffRequest 和 AgentExecutionContext 选择执行方式。

#### Feature Description

该 PR 实现 MVP 版 SubAgent。SubAgent 是 TaskSession 内部的任务执行器，不是完整多 Agent 平台。它负责选择 Skill、Plan-to-Execute 或 ReAct，并生成 StrategyDecision。

#### Implementation Approach

实现 `SubAgent` 或 `TaskSubAgentRunner` 协议，以及 `StrategyDecision` 数据对象。MVP 中，当任务目标匹配出门前提醒时，选择 `mode="skill"` 和 `skill_name="going_out"`。

#### Files to Create or Modify

- `sessions/subagent.py`
- `sessions/strategy.py`
- `tests/sessions/test_subagent_strategy.py`

#### Out of Scope

- 不实现复杂 Planner。
- 不实现完整 ReAct 循环。
- 不做多 SubAgent 注册中心或多 Agent 通信。

#### Test Method

运行：

```bash
python -m pytest tests/sessions/test_subagent_strategy.py
```

#### Acceptance Criteria

- [ ] SubAgent 接收 HandoffRequest 和 AgentExecutionContext。
- [ ] SubAgent 在 TaskSession 内部选择执行策略。
- [ ] `going_out` 被作为 skill_name 选择，而不是 Main Agent 的 task_type。
- [ ] StrategyDecision 包含 mode、skill_name、reason、initial_plan 和 completion_criteria。

#### Main Branch Runnable Check

合并后运行全量 `python -m pytest`，确认 session、skill 和 strategy 相关测试都通过。

### PR 11: feat(tools): add mock tools and task execution output

#### Title

新增 mock tools、工具调用结果和用户可见输出对象。

#### Goal

让 going_out demo 可以在不接真实外部 API 的情况下生成过程摘要和最终建议。

#### Feature Description

该 PR 增加 mock tools 和 `UserVisibleAgentOutput`。输出分为弱展示的 Agent Process Panel 和强展示的 Final Answer Card。

#### Implementation Approach

实现 Tool 接口、ToolResult、mock weather、mock vision summary、mock checklist 等工具。SubAgent 执行 going_out skill 时可以通过这些 mock tools 生成结构化过程信息和最终建议。

#### Files to Create or Modify

- `tools/__init__.py`
- `tools/base.py`
- `tools/mock_tools.py`
- `registries/tool_registry.py`
- `sessions/output.py`
- `tests/tools/test_mock_tools.py`
- `tests/sessions/test_user_visible_output.py`

#### Out of Scope

- 不接真实天气 API。
- 不接真实视觉模型、麦克风或 TTS。
- 不实现前端 UI。

#### Test Method

运行：

```bash
python -m pytest tests/tools/test_mock_tools.py tests/sessions/test_user_visible_output.py
```

#### Acceptance Criteria

- [ ] ToolResult 携带 task_id、session_id 和 trace_id。
- [ ] mock tools 可以返回稳定可测试结果。
- [ ] UserVisibleAgentOutput 区分 process 和 final_response。
- [ ] 最终建议默认比过程信息更突出。

#### Main Branch Runnable Check

合并后运行 `python -m pytest`，确认 mock execution 不破坏已有 strategy 和 skill 测试。

### PR 12: feat(memory): add completion package and memory manager

#### Title

新增 TaskCompletionPackage 和 MemoryManager。

#### Goal

让任务执行结果可以带着 AgentExecutionContext 交给 MemoryManager 管理。

#### Feature Description

该 PR 实现任务完成后的收口层。TaskCompletionPackage 汇总用户可见输出、执行摘要、工具结果和 context；MemoryManager 接收完成信息并决定如何记录。

#### Implementation Approach

实现 `TaskCompletionPackage`、`MemoryManagementRequest` 和最小 `MemoryManager`。MVP 可先将 memory 记录追加到本地 `memory.md` 或内存存储中，但写入逻辑必须通过 MemoryManager 统一入口。

#### Files to Create or Modify

- `sessions/completion.py`
- `memory/__init__.py`
- `memory/manager.py`
- `memory/memory.md`
- `tests/memory/test_memory_manager.py`
- `tests/sessions/test_completion_package.py`

#### Out of Scope

- 不实现高级检索。
- 不实现向量数据库。
- 不让 Main Agent 或 SubAgent 直接写长期 Memory。
- 不实现复杂 Memory Service。

#### Test Method

运行：

```bash
python -m pytest tests/memory/test_memory_manager.py tests/sessions/test_completion_package.py
```

#### Acceptance Criteria

- [ ] TaskCompletionPackage 包含 context、summary、user_visible_output 和 tool_results。
- [ ] MemoryManager 是 memory 写入或管理的唯一入口。
- [ ] Memory 记录能关联 task_id、session_id 和 trace_id。
- [ ] Main Agent 不直接写 Memory。

#### Main Branch Runnable Check

合并后运行全量 `python -m pytest`，确认 completion 和 memory 测试与前序执行测试都通过。

### PR 13: feat(demo): add CLI end-to-end going_out demo

#### Title

新增 Ella Runtime MVP 的 CLI 端到端 going_out demo。

#### Goal

证明 Ella 可以从用户输入“Ella，我要出门了”跑通完整 Runtime 闭环。

#### Feature Description

该 PR 添加 CLI demo，串联事件输入、事件管线、路由、Presence Runtime、打扰判断、Task Formulation、Handoff、TaskSession、AgentExecutionContext、SubAgent、going_out skill、mock tools、TaskCompletionPackage 和 MemoryManager。

#### Implementation Approach

实现 `demo/cli_demo.py` 或 `python main.py` demo 入口。demo 使用固定 mock 环境和 mock tools，输出过程区和最终建议，并写入 MemoryManager 管理的 memory 记录。

#### Files to Create or Modify

- `main.py`
- `demo/cli_demo.py`
- `tests/demo/test_cli_demo.py`
- `README.md`

#### Out of Scope

- 不实现 GUI。
- 不接真实外部工具。
- 不支持多轮复杂任务。
- 不实现 TTS 或语音播放。

#### Test Method

运行：

```bash
python -m pytest tests/demo/test_cli_demo.py
python main.py
```

手动输入：

```text
Ella，我要出门了
```

确认输出包含 Agent Process Panel 内容、Final Answer Card 内容和 memory 写入记录。

#### Acceptance Criteria

- [ ] demo 可以从 CLI 输入触发 going_out 流程。
- [ ] 输出包含弱展示过程摘要。
- [ ] 输出包含突出最终建议。
- [ ] TaskCompletionPackage 被生成。
- [ ] MemoryManager 接收到完成信息。
- [ ] Ella 最后回到 Presence Runtime。

#### Main Branch Runnable Check

合并后运行 `python -m pytest` 和 `python main.py`，确认 reviewer 可以复现 MVP demo。

### PR 14: test: add runtime contract tests

#### Title

新增 Ella Runtime 生命周期契约测试。

#### Goal

用测试固定 MVP 主链路、隔离边界和 memory 管理入口，防止后续重构破坏核心架构。

#### Feature Description

该 PR 补充跨模块契约测试，验证端到端链路、handoff 隔离、context 传递、skill 加载、工具调用 trace 和 MemoryManager 收口行为。

#### Implementation Approach

新增集成测试和契约测试，覆盖 `going_out` demo 的关键可观察输出。测试不依赖真实外部 API，全部使用 mock 输入和 mock tools。

#### Files to Create or Modify

- `tests/contracts/test_runtime_lifecycle.py`
- `tests/contracts/test_handoff_isolation.py`
- `tests/contracts/test_context_propagation.py`
- `tests/contracts/test_memory_management.py`
- `tests/contracts/test_skill_loading_contract.py`

#### Out of Scope

- 不新增产品功能。
- 不重构已通过的 Runtime 模块。
- 不引入端到端真实设备测试。

#### Test Method

运行：

```bash
python -m pytest tests/contracts
python -m pytest
```

#### Acceptance Criteria

- [ ] 生命周期测试覆盖从事件到 MemoryManager 的闭环。
- [ ] Handoff 隔离测试确认 Main Agent 不执行任务。
- [ ] Context 传递测试确认 ToolResult、CompletionPackage 和 Memory 请求共享 trace。
- [ ] Skill 加载测试确认先摘要后完整 SKILL.md。
- [ ] 所有测试在无外部网络条件下通过。

#### Main Branch Runnable Check

合并后运行全量 `python -m pytest` 和 CLI demo，确认主分支既能通过测试，也能复现 MVP 行为。

## PR Submission Convention

Ella 项目采用 PR-based development。每一个新功能、架构层或有意义的变更都必须通过 Pull Request 提交。

每个 PR 必须遵守以下规则：

- 一个 PR 只做一件事。
- 一个 PR 只实现或修改一个单一功能、一个单一架构层，或一个明确测试增强。
- 大功能必须拆成多个独立、可审查、可合并的小 PR。
- 优先提交小粒度、边界清晰、reviewer 容易理解的 PR。
- 每个 PR 必须有清晰标题和描述。
- PR 描述必须包含 Feature Description、Implementation Approach 和 Test Method。
- 每个 PR 合并后，`main` 分支必须保持 runnable。
- reviewer 应该能在任意 PR 合并后复现 demo，或至少验证当前系统状态。
- 不允许把 `main` 留在 broken、半集成或无法验证的状态。

推荐 PR 标题风格：

```text
docs: freeze PRD and architecture baseline
feat(events): add core event data models
feat(runtime): add event router and presence queue
feat(agent): add task formulation and handoff
feat(sessions): add task session manager and execution context
feat(skills): add mock going_out skill
feat(demo): add CLI end-to-end demo
test: add runtime contract tests
```

每个 PR 描述建议使用以下模板：

```md
#### Title

一句话说明这个 PR 添加或修改了什么。

#### Feature Description

说明该能力面向用户、开发者或架构层提供了什么。

#### Implementation Approach

说明核心技术设计、模块边界和关键实现逻辑。

#### Test Method

说明 reviewer 如何验证该 PR 工作正常。
```

## Merge Readiness Checklist

每个 PR 在请求 review 前，应至少确认：

- [ ] PR 只做一件事。
- [ ] PR 标题简洁清楚。
- [ ] PR 描述包含目标、能力说明、实现方式和测试方法。
- [ ] 相关测试已添加或更新。
- [ ] 本地验证命令已运行。
- [ ] 合并后 `main` 分支仍可运行。
- [ ] 如果当前阶段已有 CLI demo，reviewer 可以复现 demo。

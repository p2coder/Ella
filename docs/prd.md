# Ella Agent Runtime MVP PRD

> **⚠️ 已过期文档（核对日期：2026-08-27）**
> 本文档描述的是早期 MVP 设计，与当前实际实现差距较大，仅作历史记录保留，不再作为实现依据。
> 主要差异：MVP 基于 TaskSession/PresenceRuntime 的链路已被 TaskRuntime + TaskGraph wave 执行 + checkpoint 取代；`sessions/` 目录已清空；`going_out` 场景不再是唯一 demo。
> 当前架构与设计请参阅 [`docs/design_overview.md`](design_overview.md)。

## 1. 产品概要

Ella 是一个 Agent Native 的 AI 生活伴侣。第一阶段不追求完整的视觉、听觉、语音或真实世界工具能力，而是先验证一个持续在场的 Agent Runtime 骨架是否成立。

MVP 的核心目标是跑通一条事件驱动的完整闭环：

```text
Raw Signal
→ Event Trigger Pipeline
→ 可配置事件阶段
→ Session-aware Event Router
→ 可配置路由目的地
→ Presence Runtime
→ 是否打扰判断
→ 任务目标设定
→ 任务交接
→ TaskSessionManager
→ 创建 TaskSession
→ 构造 AgentExecutionContext
→ 唤起 SubAgent
→ SubAgent 在 TaskSession 内执行任务
→ 任务拆解与执行策略选择
→ Task Execution
→ TaskCompletionPackage
→ Memory Manager
→ 回到 Presence Runtime
```

这意味着 Ella 在第一阶段要证明自己不是一个普通聊天机器人，也不是一个固定 workflow 系统，而是一个能够接收事件、谨慎判断是否打扰、将任务交给隔离执行环境，并把经验交给 Memory 沉淀的 Agent Runtime。

## 2. 目标读者

这份 PRD 面向：

- 项目作者本人，用于统一产品意图和阶段边界。
- 后续工程实现者，用于理解 MVP 应该实现什么、不应该提前实现什么。
- 后续架构文档和实现计划，用于把产品需求转化为模块设计、根目录代码结构和测试用例。

本文档偏产品和工程落地，不是融资展示稿。

## 3. 产品目标

Ella Runtime MVP 要实现以下目标：

1. 维持一个可解释的 Presence Runtime。Presence Runtime 不是主动轮询世界的 while-loop，而是事件等待与分发循环。
2. 将外部或内部触发先抽象为 Raw Signal，并通过 Event Trigger Pipeline 转化为可配置的事件阶段，例如 Observation、Event Candidate 或标准化 Event。
3. 通过 Session-aware Event Router 判断事件应该进入 Active Task Session、Ambient State、Presence Queue，还是被抑制或仅记录。
4. 只对进入 Presence Queue 的事件使用 Interruption Policy，判断是否值得进入主动任务链路。
5. 使用 Task Formulation 综合用户当前偏好、Agent 当前输入和用户当前环境，只设定本次任务目标。
6. 通过 HandoffRequest 将目标、上下文、用户偏好、环境摘要和完成标准交给 TaskSessionManager。
7. 由 TaskSessionManager 创建 TaskSession，并在唤起 SubAgent 前构造 AgentExecutionContext。
8. 由 SubAgent 在 TaskSession 内进行 Task Decomposition / Execution Strategy Selection，决定怎么执行。
9. 由 SubAgent 生成 TaskCompletionPackage，而不是直接污染主 Agent 状态。
10. 由 Memory Manager 接收携带 AgentExecutionContext 的任务结果或 MemoryManagementRequest，并决定如何管理、存储或忽略这些信息。

## 4. 非目标

以下内容不进入 MVP：

- 真实摄像头、麦克风、TTS 或音频播放能力。
- 真实天气、日历、位置、文件系统等外部 API 集成。
- 视觉识别、ASR、唤醒检测或语音合成模型选择。
- 复杂长期记忆、短期记忆、Diary、用户画像的完整实现。
- GoingOutSkill 内部的真实物品检查逻辑。
- 多 Agent 并发、任务抢占、资源竞争调度。
- MCP、商业化闭源 Core、插件市场或远程部署。
- 完整 Planner 或复杂 ReAct 推理系统。

MVP 可以使用 mock tools、mock skills 和本地简化存储来验证 Runtime 闭环。

## 5. 用户价值

Ella 的第一阶段价值不是“回答更多问题”，而是建立一个未来生活伴侣能力可以依附的稳定运行骨架。

对用户而言，这个骨架带来三点基础体验：

1. **持续在场**：Ella 不因单个任务完成而结束，而是回到 Presence 状态继续等待未来事件。
2. **谨慎打扰**：Ella 不把所有事件都推给用户，而是根据事件来源、紧急程度、置信度和用户状态做判断。
3. **经验沉淀**：Ella 不把任务过程丢弃，而是把携带 AgentExecutionContext 的任务完成信息交给 Memory Manager，由 Memory Manager 决定如何管理、存储或忽略。

## 6. MVP 主链路

Ella Runtime MVP 的主链路是：

```text
Event Sources
  ↓
Event Trigger Pipeline
  ↓
Observation / Event Candidate / Standardized Event
  ↓
Session-aware Event Router
  ├─ SESSION_INBOX     → Task Session Inbox
  ├─ AMBIENT_STATE     → Update Ambient State only
  ├─ SUPPRESSED        → Log / Drop
  └─ PRESENCE_QUEUE    → Presence Runtime Loop
                         ↓
                       Interruption Policy
                         ↓
                       Task Formulation
  ↓
Task Handoff
  ↓
TaskSessionManager
  ↓
TaskSession
  ↓
AgentExecutionContext
  ↓
SubAgent / Task Agent Runner
  ↓
Task Decomposition / Execution Strategy Selection
  ↓
Execution Mode
   ├─ Skill
   ├─ Plan-to-Execute
   └─ ReAct
  ↓
Task Execution
  ↓
TaskCompletionPackage
  ↓
Memory Manager
  ↓
Back to Presence Runtime
```

`Observation / Event Candidate / Standardized Event` 是 MVP 默认事件阶段集合，不是写死的固定类型。工程实现需要把事件阶段做成可配置集合，例如 `EventStageRegistry` 或可扩展枚举，后续可以增加、删除或重命名阶段。

`SESSION_INBOX`、`AMBIENT_STATE`、`SUPPRESSED` 和 `PRESENCE_QUEUE` 是 MVP 默认路由目的地，也不是写死的固定目的地。工程实现需要把 Router 目的地做成可配置集合，例如 `RouteDestinationRegistry` 或可扩展枚举，后续可以增加新的 session inbox、外部 channel、monitor queue 或其他目的地。

只有进入 `PRESENCE_QUEUE` 的事件才会继续进入 `Presence Runtime Loop → Interruption Policy → Task Formulation → Task Handoff`。被路由到 `SESSION_INBOX` 的事件回流给对应 Task Session；被路由到 `AMBIENT_STATE` 的事件只更新背景状态；被路由到 `SUPPRESSED` 的事件只记录或丢弃。

主链路只描述任务生命周期与事件流转。Tool Registry、Skill Registry、Permission Manager、Resource Manager、Prompt Engine 和 Memory Service 是旁路基础设施，不作为主链路节点出现。

其中 Prompt Engine 虽然不在主链路中直接作为生命周期节点出现，但它是整个系统的关键上下文基础设施。Main Agent、Task Formulation、Task Session、Event Router、Memory Manager 等模块都可以通过 Prompt Engine / Context Builder 获得结构化、可控、可审计的模型上下文。

## 7. 核心 Demo

MVP 使用“我要出门了”作为唯一端到端 demo。

### 7.1 触发

用户输入：

```text
Ella，我要出门了
```

MVP 中该输入可以由 mock hearing tool 或 CLI demo 生成标准化事件：

```text
Event(
  type="USER_UTTERANCE",
  source="cli_input",
  trigger_kind="user_initiated",
  payload={"text": "Ella，我要出门了"},
  confidence=1.0,
  priority=0.9
)
```

### 7.2 预期流程

1. CLIInputSource 接收用户输入：“Ella，我要出门了”。
2. Event Trigger Pipeline 将该输入从 Raw Signal 标准化为 `USER_UTTERANCE` Event。
3. Event Router 判断当前没有相关 Active Task Session，因此将该事件路由到 Presence Queue。
4. Presence Runtime Loop 从 Presence Queue 中取出该事件，并进入 Main Agent 主动处理链路。
5. Interruption Policy 判断该事件由用户主动触发，允许继续处理。
6. Task Formulation 综合用户偏好、Agent 输入和当前环境，形成本次任务目标。
7. Main Agent 创建 HandoffRequest。
8. TaskSessionManager 创建隔离 TaskSession。
9. TaskSessionManager 为本次 TaskSession 构造 AgentExecutionContext。
10. TaskSessionManager 唤起 SubAgent / Task Agent Runner。
11. SubAgent 接收 HandoffRequest、AgentExecutionContext 和 TaskSession。
12. SubAgent 在 TaskSession 内进行 Task Decomposition / Execution Strategy Selection。
13. SubAgent 查询候选 Skill 轻量信息。
14. SubAgent 判断 `going_out` skill 适合本次任务，并加载完整 skill。
15. SubAgent 使用 mock GoingOutSkill 和 mock tools 执行任务。
16. SubAgent 生成用户可见提醒。
17. SubAgent 生成 TaskCompletionPackage。
18. Memory Manager 接收任务包和 AgentExecutionContext，决定如何管理 memory。
19. Ella 回到 Presence Runtime。

`going_out` 不是 Event 阶段的类型，也不是 Main Agent 直接生成的 Task 类型。`going_out` 是 SubAgent 在执行策略选择阶段可能采用的 `skill_name`。

### 7.3 用户可见输出

Ella 的用户可见输出分为两层：

- Agent Process Panel：浅色、弱化、可折叠、可关闭，用于展示结构化过程摘要。
- Final Answer Card：高亮、默认展开、最明显，用于展示最终建议。

过程区用于展示 Agent 对输入的可解释摘要，包括“我看到什么”“我听到什么”“我的目标是什么”“我准备怎么做”。该区域采用浅色背景、更小字号和较低视觉权重，并支持折叠或隐藏，避免干扰用户阅读最终结果。

最终结果区用于展示 Ella 给用户的直接建议，是主要用户输出。该区域默认展开，并使用更明显的视觉样式突出显示。未来可以在该区域加入语音播放按钮。

Ella 不展示完整隐藏推理链，而只展示结构化、可控、用户可理解的过程摘要。

示例结构：

```text
[Ella Process]  可折叠 / 浅色

我看到：桌上有水杯、耳机和电脑，但没有明显看到雨伞。
我听到：你说你准备出门，希望我帮你检查一下。
我的目标：帮你在出门前快速确认是否遗漏重要物品。
我会这样做：结合当前画面、天气和常见出门物品，给出简短提醒。

[Final Suggestion]  高亮 / 明显

我没有明显看到雨伞，今天下午可能会下雨，建议你带一把伞。
钥匙和手机也再确认一下。水杯和耳机看起来已经在桌上了。
```

MVP 可以先使用结构化 JSON 表示：

```json
{
  "process": {
    "vision_summary": "我看到桌上有水杯、耳机和电脑，但没有明显看到雨伞。",
    "audio_summary": "我听到你说你准备出门，希望我帮你检查一下。",
    "task_goal": "帮你在出门前快速确认是否遗漏重要物品。",
    "steps": [
      "检查当前画面中的物品",
      "结合天气判断是否需要带伞",
      "给出简短提醒"
    ]
  },
  "final_response": "我没有明显看到雨伞，今天下午可能会下雨，建议你带一把伞。钥匙和手机也再确认一下。",
  "show_process": true,
  "process_collapsed": false
}
```

该输出只证明 SubAgent 能产生用户可见结果，不要求真实天气或真实视觉检查。

## 8. 核心模块需求

### 8.1 Main Agent

职责：

- 维持 Presence Runtime 中 Main Agent 的主动处理部分。
- 从 Presence Queue 接收已经过 Session-aware Event Router 路由的标准化 Event。
- 调用 Interruption Policy 和 Task Formulation。
- 创建 HandoffRequest。
- 将 HandoffRequest 交给 TaskSessionManager。
- 接收 TaskCompletionPackage。
- 在任务结束后回到 Presence 状态。

非职责：

- 不直接接触摄像头、麦克风、天气 API、文件系统等外部环境。
- 不主动轮询世界。
- 不直接执行具体任务。
- 不直接写长期 Memory。
- 不创建完整 AgentExecutionContext。
- 不决定任务执行策略。
- 不关心 Tool 内部实现。
- 不关心 Skill 内部流程细节。

### 8.2 Presence Runtime

Presence Runtime 是 Ella 的常驻事件调度循环。它不是主动持续调用 LLM，也不直接轮询摄像头、麦克风或所有外部环境，而是等待事件进入队列，并根据路由结果调度事件。

职责：

- 等待 Presence Queue 中的标准化 Event。
- 在 Presence Queue 出现事件后，将事件交给 Main Agent 主动处理链路。
- 保持系统在没有事件时空闲。
- 在任务结束后恢复到等待事件状态。

非职责：

- 不主动调用 LLM 观察世界。
- 不直接轮询摄像头、麦克风或外部环境。
- 不把所有输入都视为新任务。
- 不代替 Session-aware Event Router 做路由判断。

正确理解：

```python
while running:
    event = await presence_queue.get()
    await main_agent.handle(event)
```

错误理解：

```python
while True:
    observe_world()
    think()
    maybe_create_task()
    execute_task()
```

核心原则：

```text
Presence Runtime ≠ 主动轮询世界
Presence Runtime = 等待 Presence Queue 事件并进入主动处理链路
```

### 8.3 Event Trigger Pipeline

职责：

- 接收来自用户输入、感知工具、定时器、系统状态、Memory 和 Task Session 的 Raw Signal。
- 过滤明显噪音。
- 将低层信号转化为可配置事件阶段中的一种，例如 Observation、Event Candidate 或标准化 Event。
- 为事件补充 source、confidence、priority、timestamp、trigger_kind 等元信息。
- 将标准化结果送入 Session-aware Event Router。

非职责：

- 不判断是否打扰用户。
- 不设定任务目标。
- 不决定是否创建 Task Session。
- 不选择 Skill。
- 不执行工具调用。
- 不写长期 Memory。

MVP 默认事件阶段：

| 阶段 | 说明 |
| --- | --- |
| `Observation` | 环境观察结果，不一定触发任务。 |
| `EventCandidate` | 候选事件，可能进入标准化 Event，也可能只更新 Ambient State。 |
| `Event` | 标准化事件，可以被 Router 送入 Presence Queue 或 Task Session。 |

这些阶段必须是可配置的。实现时不要把 `Observation / EventCandidate / Event` 写死在流程分支里，而应通过 `EventStageRegistry`、配置表或可扩展枚举来维护，方便后续增加或减少事件阶段。

示例：

```python
Event(
    type="USER_UTTERANCE",
    source="cli_input",
    trigger_kind="user_initiated",
    payload={"text": "Ella，我要出门了"},
    confidence=1.0,
    priority=0.9,
    timestamp=...
)
```

Event 阶段不应该生成：

```python
Event(type="GOING_OUT")
```

因为 `going_out` 是后续 Task Session 可能选择的 Skill，而不是 Event 阶段应该确定的任务类型。

### 8.4 Session-aware Event Router

职责：

- 接收 Observation、Event Candidate 或标准化 Event。
- 判断事件是否属于当前 Active Task Session。
- 判断事件是否是某个 Task Session 的 expected outcome。
- 判断事件是否携带 caused_by_task_id 或 target_session_id。
- 将事件路由到可配置目的地，例如 Active Task Session Inbox、Ambient State、Presence Queue 或 Suppressed / Log Only。
- 避免任务执行中的中间事件被误判为新任务。
- 避免用户响应当前任务的行为被误判为新任务。

非职责：

- 不判断是否打扰用户。
- 不设定任务目标。
- 不执行任务。
- 不选择 Skill。
- 不写长期 Memory。

MVP 默认路由目的地：

| 路由目的地 | 含义 |
| --- | --- |
| `SESSION_INBOX` | 当前任务需要处理这个事件。 |
| `AMBIENT_STATE` | 只更新背景状态，不打扰用户。 |
| `SUPPRESSED` | 噪音、重复事件或暂不处理，仅日志记录或丢弃。 |
| `PRESENCE_QUEUE` | 交给 Main Agent，可能进入主动任务链路。 |

这些目的地必须是可配置的。实现时不要把 `SESSION_INBOX / AMBIENT_STATE / SUPPRESSED / PRESENCE_QUEUE` 写死成不可扩展分支，而应通过 `RouteDestinationRegistry`、配置表或可扩展枚举维护，方便后续增加新的 session inbox、外部 channel、monitor queue 或其他目的地。

示例：

```python
Event(
    type="USER_LEFT_DESK",
    source="vision",
    caused_by_task_id="walk_break_123",
    target_session_id="session_001"
)
```

Event Router 看到 `caused_by_task_id` 或 `target_session_id` 后，会优先将该事件路由回对应 Task Session，而不是进入 Presence Queue 创建新任务。

### 8.5 Ambient State / Presence Context

职责：

- 持续保存非打扰式环境状态。
- 接收低频视觉观察、用户行为变化、定时器、系统资源状态和 Memory 建议等信息。
- 支撑情绪识别、久坐检测、疲劳检测、用户是否在场等长期模式判断。
- 在模式长期满足时生成 Event Candidate。
- 为 Task Formulation 和 Prompt Engine 提供当前环境摘要。

非职责：

- 不直接打扰用户。
- 不创建 Task Session。
- 不执行任务。
- 不写长期 Memory。

示例：

```python
AmbientState(
    user_present=True,
    sitting_duration_minutes=75,
    possible_fatigue=True,
    attention_state="focused",
    recent_interruptions=0,
    last_movement_time="..."
)
```

示例候选事件：

```text
用户久坐 75 分钟
+ 看起来有些疲惫
+ 最近 30 分钟没有被打扰
→ 生成 WELLBEING_NUDGE_CANDIDATE
→ 进入 Event Router
→ 进入 Presence Queue
→ Interruption Policy 判断是否提醒
```

### 8.6 Interruption Policy

职责：

- 只判断已经进入 Presence Queue 的 Event 是否值得进入主动任务链路。
- 综合事件紧急程度、重要性、置信度、用户状态、近期打扰频率和用户偏好。
- 对用户主动触发的事件默认放宽打扰限制。

非职责：

- 不处理 Raw Signal。
- 不作为 Event Trigger Pipeline 的第一道门。
- 不做事件路由。
- 不创建任务。
- 不执行任务。
- 不修改长期 Memory。

新的位置关系：

```text
Raw Signal
  ↓
Event Trigger Pipeline
  ↓
Observation / Event Candidate / Standardized Event
  ↓
Session-aware Event Router
  ↓
Presence Queue
  ↓
Interruption Policy
  ↓
Task Formulation
```

### 8.7 Task Formulation

职责：

- 综合用户当前偏好、Agent 当前输入和用户当前环境，设定本次任务目标。
- 将模糊输入转化为可交给 Task Session 的明确 goal。
- 保持目标设定的最小边界，只回答“这次任务要达成什么”。
- 为 HandoffRequest 提供 goal、任务背景和必要约束。

非职责：

- 不执行任务。
- 不选择具体工具调用顺序。
- 不展开完整计划。
- 不直接调用 Tools。
- 不修改 Memory。

示例：

```text
输入：
- 用户当前偏好：提醒要简短，出门时优先提醒天气和钥匙
- Agent 当前输入：用户说“Ella，我要出门了”
- 用户当前环境：可能下雨，用户处于出门前场景

输出：
- goal: 在用户出门前给出简短、必要的提醒，优先覆盖天气、钥匙和手机
- constraints:
  - 不要长篇解释
  - 优先提醒天气、钥匙、手机
  - 不要反复追问
```

### 8.8 Task Handoff

职责：

- 将主 Agent 的任务目标、触发事件、用户上下文、相关记忆、允许工具和完成标准封装成 HandoffRequest。
- 将 Task Formulation 生成的任务目标作为 HandoffRequest 的核心输入。
- 保证 TaskSessionManager 和后续 TaskSession 拿到足够上下文，但不会继承全部全局状态。

非职责：

- 不重新定义任务目标。
- 不创建完整 AgentExecutionContext。
- 不决定执行策略。
- 不决定 Memory 最终如何存储。
- 不把主 Agent 全局状态暴露给 Task Session。

### 8.9 TaskSessionManager

TaskSessionManager 负责创建和管理 TaskSession 生命周期，并在唤起 SubAgent 前构造 AgentExecutionContext。

职责：

- 接收 Main Agent 创建的 HandoffRequest。
- 创建隔离 TaskSession。
- 基于 HandoffRequest、任务权限、允许工具、session_id、task_id 和 trace_id 构造 AgentExecutionContext。
- 唤起 SubAgent / Task Agent Runner，并传入 HandoffRequest、AgentExecutionContext 和 TaskSession。
- 管理 TaskSession 的创建、运行、完成、失败和取消。
- 将携带 AgentExecutionContext 的 TaskCompletionPackage 或 MemoryManagementRequest 交给后续 Memory Manager 流程。

非职责：

- 不重新定义任务目标。
- 不执行具体任务。
- 不选择 Skill / Plan-to-Execute / ReAct。
- 不写长期 Memory。

### 8.10 TaskSession

TaskSession 是隔离任务空间、生命周期和状态容器，不是实际执行任务推理的 agent runner。

职责：

- 承载任务级隔离状态。
- 初始化并保存 task-local state、task-local memory、tool trace 和 message history。
- 接收 HandoffRequest。
- 声明自己关心的事件类型、预期结果和 AgentExecutionContext，让 Session-aware Event Router 能判断后续事件是否应该回流给当前 Task Session。
- 管理 TaskState。
- 接收回流事件。
- 保存 SubAgent 执行过程中产生的 observations、action trace 和 tool trace。

非职责：

- 不直接执行任务推理。
- 不选择执行策略。
- 不生成最终用户反馈。
- 不生成 TaskCompletionPackage。
- 不直接写长期 Memory。
- 不修改 Main Agent 全局状态。
- 不决定 Memory 最终如何存储。
- 不绕过 Tool Registry 调用外部能力。

示例：

```python
TaskSession(
    session_id="session_001",
    task_id="walk_break_123",
    goal="提醒用户出去走走，并确认用户是否开始活动",
    subscribed_event_types=[
        "USER_UTTERANCE",
        "USER_LEFT_DESK",
        "USER_RETURNED",
        "TIMER_TIMEOUT"
    ],
    expected_outcomes=[
        "user_stands_up",
        "user_leaves_desk"
    ]
)
```

Task Session 内部可以有自己的 Task Session Loop，但这个 loop 只服务于当前任务。任务完成后，Task Session Loop 结束，系统回到 Presence Runtime。

### 8.11 SubAgent / Task Agent Runner

SubAgent 是 TaskSession 内部的任务执行体。MVP 中，SubAgent 不代表复杂的多 Agent 系统，而是一个可被 TaskSessionManager 唤起的任务执行接口。

TaskSession 负责隔离任务生命周期、task-local state、message history、tool trace 和状态管理。SubAgent 负责在该 TaskSession 内根据 HandoffRequest 和 AgentExecutionContext 执行任务。

职责：

- 接收 HandoffRequest、AgentExecutionContext 和 TaskSession。
- 在 AgentExecutionContext 约束下执行任务。
- 进行 Task Decomposition / Execution Strategy Selection。
- 执行 Skill / Plan-to-Execute / ReAct。
- 通过 Executor 调用 Tools。
- 生成用户可见反馈。
- 生成 TaskCompletionPackage。

非职责：

- 不自行生成全局 AgentExecutionContext。
- 不修改 Main Agent 状态。
- 不管理多个 SubAgent。
- 不提供 SubAgent 注册中心。
- 不实现 SubAgent 间通信。
- 不写长期 Memory。

MVP 可以先定义轻量接口：

```python
class SubAgent:
    async def run(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
    ) -> TaskCompletionPackage:
        ...
```

或更轻量：

```python
class TaskSubAgentRunner:
    async def run(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
    ) -> TaskCompletionPackage:
        ...
```

SubAgent 可以基于 AgentExecutionContext 为 Tool Call 派生更细粒度的调用上下文，但所有派生上下文必须保留 `task_id`、`session_id` 和 `trace_id`。

MVP 不需要做多 SubAgent 调度、SubAgent 注册中心、SubAgent 间通信、多 Agent 并发、Agent marketplace 或完整 supervisor / worker 架构。

### 8.12 Task Decomposition / Execution Strategy Selection

Task Decomposition / Execution Strategy Selection 是 SubAgent 在 TaskSession 内部执行的策略判断节点。它不回答“这次任务目标是什么”，而是回答：

```text
这个目标应该用哪种执行方式完成？
```

可选策略包括：

- 使用成熟 Skill。
- Plan-to-Execute。
- ReAct。

职责：

- 基于 HandoffRequest、AgentExecutionContext、task-local state、task-local memory、可用工具权限、候选 skill 摘要和完成标准判断执行策略。
- 在需要使用成熟 skill 时，通过 Skill Registry 加载对应 skill 的完整 `SKILL.md` 内容。
- 为 SubAgent 生成 StrategyDecision。

非职责：

- 不重新设定任务目标。
- 不修改 Main Agent 状态。
- 不直接写长期 Memory。
- 不替代 Task Execution。

策略选择规则：

- **Skill**：适合目标明确、已有沉淀 workflow、步骤稳定、需要复用固定经验的任务。`going_out` 是 SubAgent 在策略选择阶段选择的 `skill_name`，不是 Main Agent 预先决定的 `task_type`。
- **Plan-to-Execute**：适合任务复杂、需要多步规划、目标清楚但路径不确定、需要先拆计划再执行的任务。
- **ReAct**：适合任务简单、路径不需要完整提前规划、需要边观察边调用工具的任务。
示例：

```python
StrategyDecision(
    mode="skill",
    skill_name="going_out",
    reason="用户目标与出门前提醒场景高度匹配，已有成熟 GoingOutSkill。",
    initial_plan=None,
    completion_criteria={
        "user_facing_response_generated": True,
        "task_summary_generated": True
    }
)
```

### 8.13 AgentExecutionContext

AgentExecutionContext 用于让 SubAgent、TaskSession、Tool Call、Memory Manager 和 Event Router 都能知道“是谁在执行、属于哪个任务、属于哪个隔离上下文”。

AgentExecutionContext 由 TaskSessionManager 为本次 TaskSession 构造，并在唤起 SubAgent 时传入。SubAgent 在该 context 约束下执行任务，TaskSession 则负责承载隔离状态和生命周期。

示例：

```python
AgentExecutionContext(
    agent_id="task_agent",
    agent_role="task_agent",
    parent_agent_id="main_agent",
    session_id="session_001",
    task_id="task_001",
    trace_id="trace_001",
    memory_scope="task",
    allowed_tools=[...],
    permissions={...}
)
```

设计原则：

- `agent_id` 是身份。
- `session_id` 是隔离上下文。
- `task_id` 是任务目标。
- `trace_id` 是过程链路。
- `memory_scope` 是记忆作用域。

所有 Tool Call、TaskCompletionPackage 和 MemoryManagementRequest 都应该携带 AgentExecutionContext。

### 8.14 Memory Manager

职责：

- 为未来独立 Memory Service 保留接口边界。
- 接收携带 AgentExecutionContext 的 TaskCompletionPackage 或 MemoryManagementRequest。
- 管理进入 Memory 系统的信息流，决定信息应被忽略、短期保存、长期保存、写入 Diary、更新偏好或更新未来策略。

非职责：

- 不执行任务。
- 不参与任务中的工具调用。
- 不直接影响当前 Task Session 的完成判断。

## 9. 旁路基础设施

以下模块为主链路提供能力支撑，但不是主任务链路节点。

### 9.1 Tool Registry

管理所有可用 Tools。Executor 通过 Tool Registry 查询并调用工具。

### 9.2 Skill Registry

Skill Registry 是标准 skill 的加载模块，用于让 Ella 接入按约定格式编写的 skill。

核心接入理念：

1. 第一次 prompt 不加载所有 skill 全文，只注入可能采用的 skill 的轻量信息。
2. 轻量信息包括 skill 名字、描述和“什么时候使用”。
3. 模型根据第一次 prompt 判断本次任务是否需要使用某个 skill。
4. 如果模型决定使用 skill，Skill Registry 再加载对应 `SKILL.md` 的完整内容，并把完整 skill 信息加入后续 prompt。

MVP 阶段，候选 skill 的收集方式先简化为“全部 skill 都是候选”。后续可以再扩展为按任务类型、用户偏好、权限、环境或历史使用情况筛选候选 skill。

标准 skill 的存储格式：

```text
skill/
  skills/
    skill-a/
      SKILL.md
    skill-b/
      SKILL.md
```

每个 `skill/skills/<skill-name>/SKILL.md` 表示一个独立 skill 的完整描述。不同 skill 必须放在不同文件夹中，文件夹名作为 skill 的稳定标识。

职责：

- 扫描 `skill/skills/*/SKILL.md`，发现可用 skill。
- 从每个 `SKILL.md` 中提取轻量信息：名字、描述和使用时机。
- 为 Prompt Engine 提供第一次 prompt 所需的候选 skill 摘要。
- 按模型选择加载指定 skill 的完整 `SKILL.md` 内容。
- 向 Task Decomposition / Execution Strategy Selection 和 SubAgent 暴露已加载 skill 的结构化信息。

非职责：

- 不决定任务执行策略。
- 不设定任务目标。
- 不执行 skill。
- 不调用 Tools。
- 不把所有 skill 全文默认塞进第一次 prompt。

### 9.3 Permission Manager

判断某个 Task Session 是否有权限调用某个 Tool，例如摄像头、麦克风、Memory 写入或主动语音输出。

### 9.4 Resource Manager

管理设备和资源状态，例如摄像头开关、麦克风监听状态和多任务资源占用。

### 9.5 Prompt Engine / Context Builder

Prompt Engine / Context Builder 是 Ella 的关键旁路基础设施。它不属于主任务生命周期节点，但它决定模型在每个决策点“看见什么、以什么结构看见、哪些信息被压缩或排除”。

职责：

- 将 Event、Agent State、Task Formulation 输入、Task State、Memory 结果、Tool 结果、Skill 描述和用户偏好整理为模型可理解的上下文。
- 为 Main Agent 的打扰判断、Task Formulation 的目标设定、SubAgent 的任务执行和 Memory Manager 的存储判断提供不同的上下文视图。
- 在 SubAgent 的策略选择 prompt 中注入候选 skill 的轻量信息，并在模型选择 skill 后注入对应 skill 的完整内容。
- 控制上下文边界，避免 Task Session 继承不必要的全局状态。
- 记录上下文来源，便于调试为什么某次任务目标被这样设定。
- 在未来支持上下文压缩、优先级排序、记忆引用和 prompt 模板版本管理。

非职责：

- 不自行决定是否打扰用户。
- 不自行设定任务目标。
- 不执行任务。
- 不调用 Tools。
- 不写 Memory。

MVP 中可以先实现为简单的上下文拼装层，但 PRD 层必须保留它在系统中的重要性。

### 9.6 Memory Service

提供 Memory 的对外抽象。MVP 可以用本地 `memory.md` 或内存存储实现，但 PRD 层保留服务边界。

## 10. 核心数据对象

MVP 需要在产品和工程层面对以下对象建立稳定命名：

| 对象 | 说明 |
| --- | --- |
| `RawSignal` | 原始输入信号，例如 CLI 输入、视觉变化、定时器触发、工具返回。 |
| `Observation` | 环境观察结果，不一定触发任务。 |
| `EventCandidate` | 候选事件，可能进入标准化 Event，也可能只更新 Ambient State。 |
| `Event` | 标准化事件。 |
| `EventStageRegistry` | 可配置事件阶段集合，用于维护 Observation、EventCandidate、Event 等阶段。 |
| `EventRouteResult` | Session-aware Event Router 的路由结果。 |
| `RouteDestinationRegistry` | 可配置路由目的地集合，用于维护 Session Inbox、Ambient State、Presence Queue、Suppressed 等目的地。 |
| `AmbientState` | 持续存在的背景状态 / Presence Context。 |
| `AgentExecutionContext` | 标识执行者、任务、会话、权限、记忆作用域和 trace 的统一上下文。 |
| `TaskFormulation` | 综合用户偏好、Agent 输入和用户环境后得到的任务目标设定。 |
| `HandoffRequest` | 主 Agent 交给 Task Session 的任务包。 |
| `TaskSessionManager` | 创建 TaskSession、构造 AgentExecutionContext 并唤起 SubAgent 的生命周期管理器。 |
| `TaskSession` | 隔离任务执行环境。 |
| `SubAgent` | TaskSession 内部的任务执行体，MVP 中可实现为轻量 Task Agent Runner 接口。 |
| `StrategyDecision` | SubAgent 对执行模式、skill 和计划的选择结果。 |
| `UserVisibleAgentOutput` | 面向前端的结构化用户可见输出，包含弱展示过程摘要和强展示最终建议。 |
| `TaskCompletionPackage` | SubAgent 完成任务后生成，并携带 AgentExecutionContext 交给 Memory Manager 的任务结果包。 |
| `MemoryManagementRequest` | Memory Manager 接收并判断管理、存储或忽略策略的输入。 |
| `AgentState` | Main Agent 的状态枚举。 |
| `TaskState` | Task Session 的状态枚举。 |
| `ToolResult` | Tool 调用结果的标准返回对象。 |

## 11. 状态模型

### 11.1 AgentState

```text
PRESENCE
FORMULATING
TASK_RUNNING
WAITING_USER
SLEEPING
ERROR
```

### 11.2 TaskState

```text
INIT
SELECTING_STRATEGY
OBSERVING
THINKING
ACTING
WAITING_TOOL
WAITING_USER
SUMMARIZING
DONE
FAILED
CANCELLED
```

关键原则：

```text
Task Done != Agent Done
```

任务完成只代表 Task Session 结束，不代表 Ella 结束。Ella 必须回到 Presence Runtime。

## 12. 验收标准

MVP PRD 的验收标准如下：

1. 读者能清楚理解 Ella Runtime MVP 是什么、不是什么。
2. 读者能理解为什么第一阶段先做 Runtime 骨架，而不是先做真实视觉、听觉或语音工具。
3. `going_out` demo 有清晰的端到端流程、触发输入、事件路由、用户可见输出和 Memory Manager 输入。
4. 每个核心模块都有明确职责、非职责和在生命周期中的位置。
5. 主链路和旁路基础设施边界清晰。
6. Event Trigger Pipeline 被明确为 Raw Signal 到可配置事件阶段的转换层。
7. Event 阶段集合通过 `EventStageRegistry` 或等价机制保持可增删。
8. Session-aware Event Router 的目的地通过 `RouteDestinationRegistry` 或等价机制保持可增删。
9. Presence Runtime 被明确为事件等待与分发循环，而不是主动轮询世界的 while-loop。
10. Interruption Policy 被明确为只处理 Presence Queue 事件，不是 Raw Signal 的第一道门。
11. Ambient State / Presence Context 被明确为非打扰式背景状态模块。
12. Task Formulation 被明确为独立步骤，只负责根据用户偏好、Agent 输入和用户环境设定任务目标。
13. TaskSessionManager 被明确为创建 TaskSession、构造 AgentExecutionContext 和唤起 SubAgent 的模块。
14. SubAgent 被明确为 TaskSession 内部的执行体，而不是完整独立 Agent 平台。
15. Task Decomposition / Execution Strategy Selection 被明确为 SubAgent 在 TaskSession 内部执行的步骤，只负责决定使用 Skill、Plan-to-Execute 或 ReAct。
16. `going_out` 被明确为 SubAgent 选择的 `skill_name`，不是 Main Agent 预先决定的 `task_type`。
17. AgentExecutionContext 被明确为由 TaskSessionManager 构造，并作为 Tool Call、TaskCompletionPackage 和 MemoryManagementRequest 的共享上下文。
18. 用户可见输出被明确分为可折叠的 Agent Process Panel 和默认突出的 Final Answer Card。
19. Prompt Engine 被明确为关键旁路基础设施，并说明它对上下文组织、边界控制和调试审计的作用。
20. 核心数据对象命名稳定，后续可以直接转为 Python 类型或协议。
21. 文档可以直接支撑后续产出：
   - `docs/architecture.md`
   - `docs/pr_plan.md`
   - 根目录代码结构
   - 事件管线、路由、Presence Runtime、handoff 隔离、Memory Manager 的测试用例

## 13. 后续文档和实现方向

PRD 通过后，下一步建议依次产出：

1. `docs/architecture.md`：定义模块边界、目录结构、对象关系和数据流。
2. `docs/pr_plan.md`：拆分第一阶段开发任务和验收顺序。
3. 根目录代码骨架：在仓库根目录直接实现 RawSignal、Observation、EventCandidate、Event、Event Router、AmbientState、AgentExecutionContext、Task Formulation、Handoff、TaskSessionManager、TaskSession、SubAgent、StrategyDecision、UserVisibleAgentOutput、Prompt Engine、Memory Service 等基础类型。
4. `tests/`：覆盖事件管线、路由目的地、Presence Runtime、Task Session 隔离、Memory Manager、going_out demo。

推荐项目结构：

```text
Ella/
  main.py

  runtime/
    presence_runtime.py      # Presence Runtime Loop
    event_queue.py           # Event Queue / Presence Queue
    event_router.py          # Session-aware Event Router
    ambient_state.py         # Ambient State / Presence Context

  events/
    source.py                # EventSource 抽象
    signal.py                # RawSignal 定义
    observation.py           # Observation 定义
    event.py                 # Event / EventCandidate 定义
    trigger_pipeline.py      # Raw Signal → Observation / Event

  agent/
    main_agent.py
    formulation.py           # Task Formulation
    handoff.py               # HandoffRequest
    context.py               # AgentExecutionContext

  sessions/
    session.py               # TaskSession
    session_manager.py       # Task Session Manager
    subagent.py              # SubAgent / Task Agent Runner
    strategy.py              # StrategyDecision
    completion.py            # TaskCompletionPackage

  execution/
    executor.py
    action.py
    decision.py

  memory/
    manager.py
    service.py
    memory.md

  registries/
    tool_registry.py

  tools/
    base.py
    mock_tools.py

  skill/
    registry.py
    loader.py
    skills/
      going_out/
        SKILL.md

  prompts/
    engine.py
    context_builder.py

  docs/
    prd.md
    architecture.md
    pr_plan.md

  demo/
    cli_demo.py

  README.md
  LICENSE
  requirements.txt
```

## 14. 默认假设

- 文档语言为中文。
- 第一阶段读者是项目作者本人和未来工程实现者。
- MVP 优先级是闭环可运行，高于真实工具集成、视觉体验和广泛生活场景。
- mock tools 和 mock skills 是允许的，只要主链路和隔离边界清晰。
- Memory 在 MVP 可以简化实现，但架构上必须保留独立服务边界。

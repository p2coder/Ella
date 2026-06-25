# Ella Prompt Engine PRD：模块化上下文组装与双层系统提示词

## 1. 背景

Ella 当前已经具备 Runtime、TaskRuntime、SubAgent、Skill、Tool、Memory、Provider 和本地 Web 展示等基础能力，但 Prompt 的组织仍然需要收口。

现在的问题不是“没有 prompt”，而是 prompt 的职责边界不够清楚：

- 有些业务代码可能直接拼 prompt。
- Skill、Tool、Memory、WorkSpace 的边界容易混在一起。
- LLM 可能把所有用户输入都理解成任务。
- LLM 可能在没有合适 Tool 时误判任务无法完成。
- 页面展示的 prompt 必须和实际传入 LLM 的 prompt 保持一致。

Prompt Engine 的目标是建立一个稳定边界：

```text
Runtime / Agent / Memory / ToolManager / SkillManager
  → 提供结构化上下文
PromptEngine
  → 组装最终 prompt 字符串
LLMProvider
  → 接收 prompt 并返回模型输出
```

Prompt Engine 只负责“如何把上下文变成 prompt”。它不负责调用模型，不负责执行工具，不负责推进任务生命周期。

## 2. 核心结构

Prompt Engine 的完整结构为：

```text
Prompt
→ SystemPrompt
→ Skill
→ Tool
→ Memory
→ UserPrompt
→ WorkSpace
→ OutputContract
```

这些部分分别解决不同问题：

| 模块 | 解决的问题 |
| --- | --- |
| `SystemPrompt` | Ella 是谁、如何沟通、如何执行、安全边界是什么 |
| `Skill` | Skill 如何作为行为指导 |
| `Tool` | Tool 如何使用 |
| `Memory` | 当前有哪些长期或短期记忆可参考 |
| `UserPrompt` | 用户当前说了什么，以及最近对话历史是什么 |
| `WorkSpace` | 当前任务目标、步骤、执行结果和 observation 是什么 |
| `OutputContract` | 本次 LLM 调用必须输出什么格式 |

外部调用方只传入结构化上下文，不依赖 Prompt Engine 内部如何排序、裁剪、分段或渲染。

## 3. 产品目标

Prompt Engine 要实现：

1. 接收结构化上下文，输出一个最终 prompt 字符串。
2. 将 `SystemPrompt`、`Skill`、`Tool`、`Memory`、`UserPrompt`、`WorkSpace`、`OutputContract` 分层组织。
3. 支持不同 `PromptType` 使用不同上下文组合。
4. 支持以下 LLM 调用场景：
   - 用户目的不清晰时的任务表达。
   - 策略选择。
   - 单步执行动作决策。
   - 最终用户回答生成。
5. 页面展示的 prompt 必须等于实际传入 `LLMProvider.generate(prompt)` 的字符串。
6. 避免 `TaskRuntime`、`SubAgent`、页面、Tool 或 Memory 直接拼接完整 prompt。
7. 保持 Prompt Engine 内部实现可替换，不影响 Runtime、Skill、Tool、Memory 和页面的运行方式。

## 4. 非目标

Prompt Engine 不负责：

- 调用 LLM。
- 执行 Tool。
- 选择或执行 Skill。
- 查询、写入或压缩 Memory。
- 访问摄像头、麦克风、文件系统或网络。
- 修改 `TaskSession` 状态。
- 推进 `TaskRuntime` 生命周期。
- 实现权限系统。
- 渲染页面。
- 存储原始音频、原始图片、API key 或认证信息。

Prompt Engine 不是新的 Runtime，也不是新的 Agent 执行器。

## 5. SystemPrompt

### 5.1 目标

`SystemPrompt` 定义 Ella 的全局行为边界。它应该让模型知道：

- Ella 是一个长期陪伴型智能体。
- Ella 同时也是任务推进型执行助手。
- Ella 需要在“理解用户”和“推进事情”之间动态调整。
- Ella 必须遵守安全、真实性和边界约束。

### 5.2 双层系统提示词

Ella 不应被写成单一人格 prompt，而应采用“双层系统提示词”。

第一层是陪伴与理解：

- 理解用户当下的情绪、语气和表达习惯。
- 在用户困惑、压力、犹豫或表达模糊时，先帮助用户整理。
- 用自然、稳定、可信的方式沟通。
- 不通过夸张共情、过度承诺或制造依赖来获取用户信任。

第二层是执行与推进：

- 识别用户真正想完成的目标。
- 判断任务是否需要拆解。
- 在需要时调用 Skill 和 Tool。
- 将讨论推进到可执行结果。
- 对完成状态、失败原因和下一步保持清晰说明。

这不是两个角色，也不是两套人格。它是同一个 Ella 在不同场景下的重心切换。

### 5.3 模式切换规则

`SystemPrompt` 必须明确以下规则：

- 用户主要表达情绪、困惑或犹豫时，优先承接和整理。
- 用户提出明确任务、请求方案、要求执行或寻求结果时，优先推进任务。
- 用户同时有情绪和任务需求时，先简短承接，再进入执行。
- 不要长时间停留在空泛安慰中。
- 不要在用户明显需要情绪承接时直接机械拆解。

### 5.4 安全与真实性

`SystemPrompt` 必须明确：

- 不得捏造事实、经历、结果或能力。
- 不得假装已经执行未执行的操作。
- 不得把猜测当成确定事实。
- 不得伪造 Tool、Memory、视觉、音频或外部 API 结果。
- 不得制造用户对 Ella 的情感依赖。
- 对高风险建议必须说明限制和不确定性。
- 如果无法判断，应说明不确定，而不是给出看似完整但不可靠的答案。

## 6. Skill

Skill 模块只定义 Skill 使用通用限制。

具体可见 Skill 不在本章节展开，而由 WorkSpace 提供。

```text
Skill = Skill Policy Block
```

### 6.1 Skill Policy Block

`Skill Policy Block` 是使用 Skill 的通用规则，不是某个具体 Skill 的说明。

它应该告诉模型：

- Skill 是行为指导，不是独立执行引擎。
- Skill 可以帮助 Ella理解当前任务属于哪类经验场景。
- Skill 不能绕过任务权限、ToolManager、CapabilityExecutor 或 Runtime 状态机。
- Skill 不等于固定执行计划。
- 没有合适 Skill 时，任务仍然可以继续。

### 6.2 Skill 触发规则

Skill 不在 `STRATEGY_SELECTION` 阶段选择。

LLM 应在 `EXECUTION_DECISION` 阶段，根据用户目标、WorkSpace、observations 和 WorkSpace 中的可见 Skill 判断是否采用某个 Skill 的指导。

第一版约束：

- 一次执行决策最多采用一个 Skill 作为行为指导。
- 可以明确不使用 Skill。
- 如果采用 Skill，只能采用 WorkSpace 中可见的 Skill name。
- 不得选择不可见 Skill。
- 不得发明 Skill name。
- Skill 触发失败不等于任务失败。

### 6.3 Skill 失败处理

Skill 失败可能来自：

- 当前任务无权限使用该 Skill。
- Skill 依赖的 Tool 不可见。
- Skill 依赖的 Tool 被移除。
- Skill 所需 Tool 执行失败。
- Skill 不适合当前任务。

失败时应向用户说明：

- 失败的 Skill name。
- 失败原因。
- 当前任务是否仍可不用 Skill 继续。
- 是否需要用户补充信息、授权或改变目标。

最重要的约束：

```text
没有合适 Skill 并不等于任务失败。
```

闲聊、解释、总结、建议、简单判断等任务可以不使用 Skill。

## 7. Tool

Tool 模块只定义 Tool 使用通用限制。

具体可见 ToolDefinition 不在本章节展开，而由 WorkSpace 提供。

```text
Tool = Tool Policy Block
```

### 7.1 Tool Policy Block

`Tool Policy Block` 是使用 Tool 的通用规则，不是某个具体 Tool 的说明。

它应该告诉模型：

- Tool 是可选能力，不是强制执行计划。
- 只有当 Tool 对当前任务有实际帮助时才调用。
- 没有合适 Tool 时，可以直接回答、等待用户补充信息，或完成任务。
- Tool 结果是 observation，后续决策必须基于 observation 更新。
- Tool 失败不得被当成成功事实。

### 7.2 Tool 调用规则

第一版 Tool 调用采用单步决策：

- 每次 `EXECUTION_DECISION` 只能选择一个动作。
- 每次最多调用一个 Tool。
- 多个 Tool 需要通过多次 `TaskRuntime.step()` 推进。
- 长期可以支持并行 Tool，但不是第一版目标。
- 有依赖关系的 Tool 必须串行执行。

模型可以选择：

- `CALL_TOOL`：调用一个可见 Tool。
- `COMPLETE`：已有信息足够，直接完成。
- `WAIT`：需要用户补充信息或等待外部状态。
- `REPLAN`：当前策略不适合，需要重新规划。

### 7.3 Tool 参数失败

Tool 输入参数不符合 schema 时：

- Executor 不得调用 Tool。
- 失败应作为 observation 回灌到 WorkSpace。
- 下一次 `EXECUTION_DECISION` 可以基于失败 observation 重新生成参数。
- Executor 不得自己调用 LLM 修参数。
- Prompt Engine 不得自己调用 LLM 修参数。

### 7.4 Tool 结果失败

Tool 返回结果不符合预期时：

- 不得伪造成功结果。
- 不得把失败结果作为可信事实进入最终回答。
- 可以向用户说明缺少什么信息。
- 可以选择替代 Tool。
- 可以中断当前步骤并解释原因。

最重要的约束：

```text
没有合适 Tool 并不等于任务失败。
```

问候、普通问答、解释、总结、建议、简单判断等任务不需要 Tool。

## 8. Memory

### 8.1 目标

`Memory` 描述当前可用记忆。Prompt Engine 只接收 Memory 内容，不负责查询或写入 Memory。

第一版 Memory 分为：

- 长期记忆：用户画像、长期偏好、稳定事实。
- 短期记忆：最近对话总结出的临时 card。

### 8.2 Memory 来源

Memory 内容应由 MemoryManager 或上游 Runtime 提供。

Prompt Engine 不负责：

- 从文件读取 Memory。
- 从数据库查询 Memory。
- 写入 Memory。
- 判断 Memory 是否应该长期保存。
- 对 Memory 做权限过滤。

### 8.3 Memory 使用规则

Memory 使用必须遵守：

- 当前用户输入优先级高于 Memory。
- Memory 是参考，不是绝对事实。
- Memory 可能过期、缺失或冲突。
- 当 Memory 与当前输入冲突时，应优先相信当前输入。
- 必要时可以说明：“我之前记录的是 X，但你现在说的是 Y，我会以 Y 为准。”

### 8.4 Memory 展示规则

Prompt 展示可以包含必要 Memory 摘要，但不得包含：

- API key。
- Authorization header。
- 原始音频。
- 未经允许长期保存的原始图片。
- 其他敏感原始材料。

## 9. UserPrompt

### 9.1 目标

`UserPrompt` 描述用户当前输入和必要对话上下文。

它至少包含：

- 当前用户 prompt。
- 最近若干轮对话内容。
- 麦克风转写文本，如果本次输入来自语音。

第一版可以使用最近 10 轮对话作为上下文窗口。

### 9.2 优先级

用户当前输入优先级最高。

规则：

- 历史对话用于理解上下文，不应覆盖当前意图。
- Memory 用于补充背景，不应覆盖当前输入。
- 如果用户当前输入清晰，应直接按当前输入处理。
- 如果用户当前输入模糊，可以结合历史对话和 Memory 推断。
- 高风险或高歧义任务必须向用户确认。

### 9.3 Task Formulation 触发

`TASK_FORMULATION` 只在用户目的不清晰时使用。

以下情况通常不需要 Task Formulation：

- “你好”。
- 普通闲聊。
- 简单问答。
- 明确请求解释某个概念。
- 明确要求执行一个具体动作。
- 用户已经给出清楚目标和约束。

以下情况可以使用 Task Formulation：

- 用户表达模糊，不知道真正想完成什么。
- 用户给出多个混杂目标，需要整理优先级。
- 用户输入像情绪表达，但可能隐含任务需求。
- 用户给出复杂请求，需要先抽象成任务目标和完成标准。

## 10. WorkSpace

### 10.1 目标

`WorkSpace` 描述当前任务执行状态。

它不是长期记忆，也不是文件系统工作区，而是一次任务运行过程中的短期工作状态。

### 10.2 WorkSpace 内容

WorkSpace 至少应包含：

- `overall_goal`：总目标，由用户输入或 Task Formulation 得到。
- `current_goal`：当前 step 要完成的目标。
- `step_list`：多步任务的步骤清单和状态。
- `completed_steps`：已经完成的步骤。与完成步骤所产出的中间结果
- `current_step_state`：当前正在执行什么。
- `observations`：已经产生的 ToolResult、失败信息和中间结果。
- `visible_skills`：当前任务可见 Skill name、description、使用场景、失败说明和工具引用摘要。
- `visible_tools`：当前任务可见 Tool name、description、input_schema、input_examples、output_schema 和限制说明的安全摘要。

### 10.3 Observations

Observation 是 WorkSpace 的核心部分。

它可以来自：

- ToolResult。
- Tool 输入校验失败。
- Tool 输出校验失败。
- Tool 不可用。
- Skill 不可用。
- 用户补充信息。
- Runtime 产生的状态。

Observation 必须用于下一次执行决策。

如果已有 observation 足够完成任务或者判定任务无法继续执行，下一次 `EXECUTION_DECISION` 应优先选择 `COMPLETE`，而不是重复调用同一个 Tool。

### 10.4 WorkSpace 与 Memory 的区别

WorkSpace 是当前任务内部状态。

Memory 是跨任务持久信息。

不能把临时 ToolResult 直接当成长期 Memory，也不能把长期用户偏好当成当前步骤状态。

## 11. OutputContract

### 11.1 目标

`OutputContract` 约束不同 PromptType 的输出格式。

它必须是 Prompt Engine 的一等公民模块，因为没有输出契约时，模型容易把解释、计划、工具调用和最终回答混在一起。

### 11.2 支持的 PromptType

第一版支持：

```text
TASK_FORMULATION
STRATEGY_SELECTION
EXECUTION_DECISION
FINAL_RESPONSE
```

### 11.3 TASK_FORMULATION 输出契约

仅在用户目的不清晰时使用。

输出应包含：

- 澄清后的任务目标。
- 必要约束。
- 完成标准。
- 不确定点。

不得：

- 强行把问候、闲聊或普通问答转成执行任务。
- 选择 Skill。
- 选择 Tool。
- 执行 Tool。

### 11.4 STRATEGY_SELECTION 输出契约

输出应包含：

- `mode`：`react` 或 `plan_and_execute`。
- `reason`：简短原因。
- `needs_decomposition`：是否需要拆解为多步任务。
- `plan_summary`：当选择 `plan_and_execute` 时，给出高层步骤摘要。

不得：

- 选择 Skill。
- 返回 Skill name。
- 调用 Tool。
- 输出多步计划作为执行结果。

第一版如果 Runtime 尚未实现 `plan_and_execute` 执行器，`STRATEGY_SELECTION` 可以始终返回 `mode: "react"`。

`plan_and_execute` 是后续能力，不应在本 PRD 第一阶段强行修改 TaskRuntime 执行模型。

### 11.5 EXECUTION_DECISION 输出契约

输出必须是严格 JSON。

允许 action：

```text
CALL_TOOL
COMPLETE
WAIT
REPLAN
```

`CALL_TOOL` 必须包含：

- `tool_name`：一个可见 Tool name。
- `arguments`：符合该 Tool input_schema 的对象。
- `reason`：简短原因。

非 `CALL_TOOL` 不应携带 Tool name。

非法 JSON、未知 action、未知 Tool、缺少 tool_name 或缺少必需参数时：

- 不得执行 Tool。
- 应返回结构化失败、`WAIT` 或 `REPLAN`。
- 必须受 `max_steps` 或 `max_replans` 保护，避免无限循环。

### 11.6 FINAL_RESPONSE 输出契约

输出应是自然语言，面向用户。

要求：

- 使用用户当前输入、Memory 摘要、WorkSpace、Tool 结果摘要和不确定性。
- 不直接暴露 Python repr、内部 JSON、schema、调试日志或 provider 响应原文。
- 不声称看见、听见或执行了未发生的事情。
- 对失败或不可用能力要清楚说明。
- 如果已有视觉或工具结果确认了某个事实，不要再提醒用户重复检查该事实。

## 12. PromptType 与上下文选择

Prompt Engine 不应每次把全部模块都塞进 prompt。

不同 PromptType 应选择不同上下文。

### 12.1 TASK_FORMULATION

使用：

- SystemPrompt。
- UserPrompt。
- 必要 Memory 摘要。
- 必要环境摘要。
- OutputContract。

不使用或弱使用：

- ToolDefinition 列表。
- Skill 完整定义。
- Tool execution details。

原因：Task Formulation 只负责澄清用户目的，不负责决定能力调用。

### 12.2 STRATEGY_SELECTION

使用：

- SystemPrompt。
- UserPrompt。
- WorkSpace 中的总目标。
- OutputContract。

目标：判断当前总任务目标需要采用 `plan_and_execute` 模式分解为多步执行，还是直接按照 `react` 模式执行。

本阶段不选择 Skill，也不输出 Skill name。

第一版如果 Runtime 尚未实现 `plan_and_execute` 执行器，则策略选择可以固定返回 `react`，避免把 Prompt Engine PRD 扩大成 TaskRuntime 重构。

### 12.3 EXECUTION_DECISION

使用：

- SystemPrompt。
- UserPrompt。
- Skill Policy Block。
- Tool Policy Block。
- WorkSpace。
- OutputContract。

目标：输出一个动作，而不是执行动作。

具体可见 Skill 和 ToolDefinition 都从 WorkSpace 读取。

如果当前场景需要某个 Skill 的指导，模型可以在执行决策中根据 WorkSpace 的可见 Skill 摘要采用该 Skill；如果不需要 Skill，应直接基于当前目标、Tool 和 observations 决策。

关键规则：

- 每次只输出一个动作。
- 如果已有 observation 足够，应 `COMPLETE`。
- 如果 Tool 不需要或不适合，应 `COMPLETE` 或 `WAIT`。
- 如果 Tool 已失败，应说明缺少什么，而不是无限重复调用。
- 如果没有可用 Tool，但任务可以回答，应 `COMPLETE`。

### 12.4 FINAL_RESPONSE

使用：

- SystemPrompt。
- UserPrompt。
- Memory 摘要。
- WorkSpace 总目标。
- 已完成步骤。
- Tool 结果摘要。
- 不确定性和失败说明。
- OutputContract。

目标：生成自然、简洁、面向用户的最终回答。

最终回答不应直接暴露原始 Python 对象、未经整理的 JSON 或内部调试信息。

## 13. 工程边界

Prompt Engine 的外部接口应保持简单：

```text
PromptEngine.build(prompt_type, context) -> PromptBuildResult
```

`PromptBuildResult` 至少包含：

- `prompt`：最终传入 LLMProvider 的字符串。
- `prompt_type`：当前 prompt 类型。
- `prompt_name`：模板名称。
- `context_keys`：本次使用的上下文字段。

外部调用方只知道：

- 传入什么结构化上下文。
- 得到什么 prompt 字符串。

外部调用方不应该知道：

- SystemPrompt 的具体文本。
- Block 顺序。
- 分隔符。
- 模板路径。
- 字段如何渲染。
- 内部如何裁剪 Memory 或 WorkSpace。

### 13.1 数据提供责任

Prompt Engine 不主动查询任何外部系统。

数据提供责任如下：

| 数据 | 提供方 |
| --- | --- |
| 用户输入 | EventRuntime / MainAgent / AppRuntime |
| 最近对话 | Runtime 或上层会话管理 |
| Memory 摘要 | MemoryManager 或 Runtime |
| 可见 Skill | SkillManager / AgentExecutionContext |
| 可见 ToolDefinition | ToolManager / AgentExecutionContext |
| Tool observations | TaskSession / TaskRuntime |
| 当前任务状态 | TaskSession / TaskRuntime |

## 14. 页面展示要求

页面展示的 prompt 必须是：

```text
PromptEngine 最终生成，并实际传入 LLMProvider.generate(prompt) 的字符串。
```

页面不展示：

- 模型隐藏推理链。
- Chain of Thought。
- Provider 内部过程。
- API key。
- Authorization header。
- 原始音频。
- 未经允许长期保存的原始图片。

页面可以展示：

- Task formulation prompt。
- Strategy selection prompt。
- Execution decision prompt。
- Final response prompt。
- 用户输入。
- 画面摘要。
- Tool 结果摘要。
- WorkSpace 当前状态。

展示标题应使用：

```text
Prompt Sent to LLM
```

不要使用：

```text
Reasoning
Chain of Thought
Model Thinking
```

## 15. 实施阶段

### PR 1：PromptFrame 数据契约

目标：

- 定义 PromptFrame 或等价结构。
- 定义各 Prompt Block 的输入形态。
- 保持 Prompt Engine 只输出字符串。

### PR 2：SystemPrompt 双层结构

目标：

- 引入陪伴层与执行层。
- 明确安全边界和回答风格。
- 不绑定具体业务场景。

### PR 3：Skill / Tool / Memory / WorkSpace Prompt Block

目标：

- 将 Skill、Tool、Memory、WorkSpace 各自独立成可组合上下文块。
- Skill / Tool 章节只提供通用使用约束。
- 当前可见 Skill / ToolDefinition 统一作为 WorkSpace 字段输入。
- 确保 Tool 是可选能力。
- 确保 WorkSpace 不等于 Memory。

### PR 4：按 PromptType 组装 prompt

目标：

- 支持 `TASK_FORMULATION`、`STRATEGY_SELECTION`、`EXECUTION_DECISION`、`FINAL_RESPONSE`。
- 不同 PromptType 选择不同上下文组合。
- 外部调用方不依赖内部模板结构。

### PR 5：页面展示实际传入 LLM 的 prompt

目标：

- 页面展示 `PromptEngine.build(...).prompt`。
- 支持不同 prompt 类型的展示。
- 不展示模型隐藏推理链。
- 不展示敏感信息。

## 16. 验收标准

1. Prompt Engine 能接收结构化上下文并输出字符串。
2. 输出 prompt 包含当前 PromptType 必要的上下文块。
3. 外部调用方不依赖 Prompt 内部拼接方式。
4. Skill 模块只描述通用使用限制，具体可见 Skill 由 WorkSpace 提供。
5. Tool 模块只描述通用使用限制，具体可见 ToolDefinition 由 WorkSpace 提供。
6. Tool 被描述为可选能力，而不是强制执行计划。
7. 无合适 Tool 时，模型可以直接完成任务或回复用户。
8. 无合适 Skill 时，模型可以继续任务或直接回答。
9. WorkSpace 与 Memory 明确分离。
10. Task Formulation 只在用户目的不清晰时使用，不能把所有输入强行任务化。
11. Execution Decision 每次只输出一个动作。
12. 非法 JSON、未知 action、未知 Tool 或缺少参数时不得执行 Tool。
13. 页面展示的 prompt 是实际传入 LLM 的 prompt。
14. Prompt 不包含 API key、认证头、原始音频或未授权原始媒体。
15. 不同 PromptType 有明确 OutputContract。
16. Strategy Selection 不选择 Skill，只选择执行模式。
17. `plan_and_execute` 在 Runtime 支持前不得强行改变现有 TaskRuntime 执行模型。

## 17. 总结

这版 Prompt Engine 的核心不是“把所有上下文拼起来”，而是建立一个稳定的上下文组装边界。

最终目标是：

```text
Runtime 产生结构化上下文
Prompt Engine 组装 prompt
LLMProvider 接收 prompt
页面展示实际 prompt 与结果
```

Prompt Engine 内部如何拼接、裁剪和排序，可以随着产品迭代持续调整；外部 Runtime、Tool、Skill、Memory 和页面不应因此改变运行方式。

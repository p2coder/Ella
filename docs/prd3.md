# Ella Runtime PRD 3：Prompt Engine 与页面显示器

## 1. 产品概要

PRD 3 在 Ella Runtime 2.1 的真实模型、摄像头和麦克风能力之上，增加两个关键产品边界：

1. `Prompt Engine`：统一收集上下文、选择 system prompt、拼接 prompt，并输出一个字符串作为 LLM 的唯一输入。
2. 页面显示器：把一次任务运行过程中 Ella 接收到、看到、理解、规划和回答的内容可视化出来。

PRD 3 的目标不是重写 Runtime，而是让现有链路变得可解释、可调试、可演示：

```text
用户说了什么
→ Ella 看见了什么
→ Ella 如何总结画面
→ Ella 生成了什么任务目标
→ Ella 输入给 LLM 的 prompt 是什么
→ Ella 最终如何回答用户
```

当前实现中，LLM 只参与任务目标生成，最终回答仍由 `TaskRuntime` 模板生成：

```text
Task completed: <task_goal>
```

PRD 3 要补上“最终回复生成”边界，让最终回答可以基于用户输入、视觉结果、任务目标和执行结果生成，而不是只复述任务目标。

## 2. 核心产品判断

Ella 的优势不只是“调用摄像头或模型”，而是能够解释自己如何理解当前任务。

因此页面显示器不应该只是一个聊天框，也不应该只是日志窗口。它应该像一个轻量 Runtime Inspector，展示：

- 用户原始输入。
- 麦克风转写文本。
- 摄像头捕获画面或画面占位。
- 多模态模型生成的画面总结。
- Prompt Engine 拼出的 prompt。
- MainAgent / TaskFormulation 生成的任务目标。
- SubAgent 执行过程中的工具结果摘要。
- 最终面向用户的回答。

这能帮助开发者和评委理解 Ella 的内部状态，也能帮助后续调 prompt、调视觉策略和调任务边界。

## 3. 产品目标

1. PRD 3 范围内新增或改造的文本 LLM 调用必须经过 Prompt Engine，包括 Task Formulation 和 Final Response Generation。
2. Prompt Engine 输出必须是一个字符串，作为 LLMProvider 的输入。
3. Prompt Engine 内部维护 prompts，作为不同场景的 system prompts。
4. Prompt Engine 能根据调用目的收集并组织上下文。
5. Task Formulation 使用 Prompt Engine 生成任务目标 prompt。
6. Final Response Generation 使用 Prompt Engine 生成最终回答 prompt。
7. 页面显示器展示一次任务的关键可观测状态。
8. 页面显示器可以用于 mock provider 和真实 provider。
9. 页面显示器不能绕过 EventRuntime 或 TaskRuntime。
10. 页面显示器不能直接调用摄像头、麦克风、工具或 MemoryManager。

## 4. 非目标

PRD 3 不实现：

- 通用 Web 产品后台。
- 用户登录、权限系统或数据库。
- 多用户会话。
- 并发任务调度。
- 复杂前端框架迁移。
- WebSocket 实时流。
- 长期保存原始图片或音频。
- Prompt 自动优化。
- 多 prompt 版本实验平台。
- 让页面直接调用 provider、device、tool 或 memory。

第一版页面显示器可以是本地开发页面，不要求部署到公网。

## 5. 当前实现问题

### 5.1 LLM 调用分散且缺少统一 Prompt 边界

当前 `TaskFormulator` 直接构造 prompt 并调用 LLM：

```text
TaskFormulator
  → llm_provider.generate(prompt)
```

这导致：

- Prompt 逻辑混在业务代码里。
- System prompt 没有统一管理。
- 无法在页面中稳定展示“这次 LLM 到底收到了什么 prompt”。
- 后续增加最终回答生成时容易重复拼 prompt。

### 5.2 最终回答没有使用 LLM

当前 `TaskRuntime._build_completion()` 直接模板化生成：

```text
Task completed: <task_goal>
```

它没有读取：

- 摄像头画面总结。
- 工具结果。
- 用户原始问题。
- 任务约束。
- 用户偏好。

因此它不能真正回答用户，例如：

```text
手机还在桌上，出门前记得带上。
```

### 5.3 Demo 输出不能展示完整推理链路

当前 CLI 只展示：

```text
[Ella Process]
[Final Answer]
[Memory]
```

这对真实模型调试不够。开发者需要看到：

- ASR 识别结果是否正确。
- 摄像头是否真的捕获了画面。
- 多模态模型怎么理解画面。
- Task goal 是否被 LLM 误写。
- Final answer 是否真正使用了工具结果。
- 输入 LLM 的 prompt 是否符合预期。

## 6. Prompt Engine 设计

### 6.1 职责

Prompt Engine 是 PRD 3 范围内文本 LLM 调用的唯一 prompt 生成入口。

职责：

- 持有不同用途的 system prompts。
- 接收结构化上下文。
- 按调用目的生成最终 prompt 字符串。
- 返回 prompt 字符串和可选调试元数据。
- 保证 prompt 可被页面显示器记录和展示。

非职责：

- 不调用 LLM。
- 不访问摄像头、麦克风或工具。
- 不决定任务策略。
- 不写 memory。
- 不直接生成 TaskSession。

### 6.1.1 封装原则

Prompt Engine 的 prompt 拼接方式必须完全隔离在 Prompt Engine 内部。

外部模块只允许向 Prompt Engine 传入：

```text
prompt_type
必要的结构化上下文信息
```

外部模块不得依赖：

```text
system prompt 内容
模板文件路径
字段排列顺序
分隔符格式
上下文如何转成文本
prompt 的内部段落结构
```

Prompt Engine 内部如何选择 system prompt、如何组织上下文、如何拼接字符串，都不应该影响外部 Runtime 的运行方式。后续调整 prompt 模板、语言风格、字段顺序或格式时，不应要求修改 `EventRuntime`、`TaskRuntime`、`SubAgent`、`CapabilityExecutor`、provider、device 或页面调用逻辑。

允许变化的是 Prompt Engine 输出的 `prompt` 字符串内容；不允许变化的是外部调用契约。

### 6.2 Prompt 类型

第一版至少支持两类 prompt：

```text
TASK_FORMULATION
FINAL_RESPONSE
```

#### TASK_FORMULATION

用于回答：

```text
应该做什么？
```

输入上下文：

- 用户输入文本。
- 用户偏好摘要。
- 环境摘要。
- 事件类型。
- trace_id。

输出：

```text
一个字符串 prompt
```

该 prompt 输入 LLM 后，LLM 输出 task goal 或结构化 formulation 内容。

#### FINAL_RESPONSE

用于回答：

```text
应该如何回应用户？
```

输入上下文：

- 用户输入文本。
- task goal。
- task constraints。
- completion criteria。
- tool results。
- 摄像头画面总结。
- 可见物体列表。
- provider/tool 错误。
- 用户偏好摘要。
- 环境摘要。

输出：

```text
一个字符串 prompt
```

该 prompt 输入 LLM 后，LLM 输出最终用户可见回答。

### 6.3 System Prompts

Prompt Engine 内部维护 prompts。第一版可以使用本地文本常量或独立 prompt 文件。

推荐第一版结构：

```text
prompts/
  task_formulation.md
  final_response.md
```

或者先在代码中定义：

```text
PromptTemplate(name="task_formulation", system_prompt="...")
PromptTemplate(name="final_response", system_prompt="...")
```

无论采用哪种方式，业务模块不应直接拼完整 prompt。

### 6.4 Prompt 输出契约

Prompt Engine 的核心输出是字符串：

```python
prompt: str
```

可以额外返回调试元数据：

```python
PromptBuildResult(
    prompt=str,
    prompt_type=str,
    prompt_name=str,
    context_keys=tuple[str, ...],
)
```

每次 LLM 调用至少应记录可展示的 prompt trace：

```text
trace_id
prompt_type
prompt_name
prompt_text
provider_name
model_name
llm_output
```

其中 `prompt_text` 必须等于实际传入 `LLMProvider.generate(prompt)` 的字符串。页面字段推荐命名为：

```text
task_formulation_prompt_text
final_response_prompt_text
```

页面标题推荐使用：

```text
Prompt Sent to LLM
```

不得使用 `Reasoning`、`Chain of Thought`、`Model Thinking` 等容易误导为模型隐藏推理的标题。

但传入 LLMProvider 的必须是：

```python
llm_provider.generate(prompt)
```

## 7. Final Response Generator

PRD 3 需要新增一个明确边界，让最终回答不再由 TaskRuntime 模板生成。

推荐边界：

```text
FinalResponseGenerator
  → PromptEngine.build(FINAL_RESPONSE, context)
  → LLMProvider.generate(prompt)
  → UserVisibleAgentOutput.final_response
```

职责：

- 收集 task goal、tool results、用户输入和上下文。
- 调用 Prompt Engine 生成最终回答 prompt。
- 调用 LLMProvider。
- 将 LLM 输出归一化为最终回答文本。
- provider 失败时提供 deterministic fallback，且不能退回到旧的 `Task completed: <task_goal>` 模板。

非职责：

- 不执行工具。
- 不选择 skill。
- 不修改 TaskSession 状态机。
- 不直接写 memory。

TaskRuntime 可以在 `_build_completion()` 阶段使用 FinalResponseGenerator，但要保持 TaskRuntime 仍只管理生命周期。

理想边界：

```text
TaskRuntime 收集 completion context
  → FinalResponseGenerator.generate(context)
  → 返回 final_response
  → TaskRuntime 组装 TaskCompletionPackage
```

TaskRuntime 不应承担 prompt 拼接、LLM 调用细节或 ToolResult 文本化规则。

FinalResponseGenerator 的 fallback 应使用 `user_input`、`task_goal` 和 `tool_results_summary` 生成可读回答，例如：

```text
我已经根据当前信息完成了检查：{tool_summary}。{safe_recommendation}
```

Fallback 不得退回 `Task completed: <task_goal>`。

## 8. 页面显示器设计

### 8.1 页面目标

页面显示器用于展示一次任务运行过程中的关键状态。

第一版页面可以是本地单页应用或轻量 HTML 页面。目标不是替代 Runtime，而是观察 Runtime。

### 8.2 页面内容

页面必须展示：

1. 用户说了什么。
2. 麦克风转写文本。
3. 智能体看见的画面。
4. 智能体看见画面的总结。
5. 智能体生成的目标。
6. 智能体输入给 LLM 的 prompt。
7. 智能体的最终回答。

推荐分区：

```text
Input
  - input mode: text / microphone
  - raw user text
  - transcript text

Vision
  - latest captured frame or placeholder
  - camera provider
  - multimodal provider
  - scene summary
  - visible items

Prompt
  - task formulation prompt
  - final response prompt
  - prompt type

Agent
  - task goal
  - selected skill
  - execution decisions
  - tool results

Answer
  - final response
  - memory status
```

### 8.3 页面数据来源

页面不应直接调用底层模块，而应读取 Runtime 产出的展示数据。

推荐新增展示快照：

```text
RunDisplaySnapshot
  user_input
  transcript
  captured_frame
  image_status
  scene_summary
  visible_items
  task_goal
  task_formulation_prompt_text
  final_response_prompt_text
  tool_results_summary
  final_response
  memory_status
```

第一版可以由 demo assembly 收集该 snapshot。demo assembly 只做 snapshot 组装适配，不得重新编排 Runtime 流程。

后续更成熟时，应由 `TaskRuntimeResult` 或独立 `RuntimeTraceRecorder` 生成。

### 8.4 画面显示策略

默认不长期保存原始画面。

页面显示画面时应满足：

- mock 模式显示 mock 占位画面或说明。
- real 模式显示最近一次任务内有界截图。
- 只有 `DEBUG_STORE_RAW_MEDIA=true` 或显式页面会话需要时才保留图片。
- 截图仅用于当前本地页面展示。
- 不写入 memory。
- 图片区域必须标明来源状态，例如 `mock image`、`camera frame`、`camera unavailable` 或 `text-only`。

### 8.5 页面交互范围

第一版页面显示器不要追求实时。不要实现：

```text
WebSocket
实时刷新
摄像头流
任务状态流
多轮会话
```

第一版推荐流程：

```text
任务跑完
  → 生成 RunDisplaySnapshot
  → 生成本地 HTML
  → 打开页面或保存页面
```

## 9. 数据流

### 9.1 Task Formulation Prompt Flow

```text
RawSignal
  → EventRuntime
  → MainAgent
  → TaskFormulator
  → PromptEngine.build(TASK_FORMULATION, context)
  → LLMProvider.generate(prompt)
  → TaskFormulation
  → HandoffRequest
```

### 9.2 Tool / Vision Flow

```text
SubAgent
  → CALL_TOOL(camera_scene)
  → CapabilityExecutor
  → CameraSceneTool
  → CameraProvider.capture_frame()
  → MultimodalProvider.describe()
  → ToolResult(scene_summary, visible_items, frame metadata)
  → TaskSession.tool_trace
```

### 9.3 Final Response Flow

```text
TaskRuntime completion boundary
  → collect HandoffRequest + ToolResult + context
  → summarize ToolResult into readable tool_results_summary
  → PromptEngine.build(FINAL_RESPONSE, context)
  → LLMProvider.generate(prompt)
  → UserVisibleAgentOutput.final_response
  → TaskCompletionPackage
  → MemoryManager
```

ToolResult 不应以 Python 对象 repr 直接塞进 prompt，例如不得直接传入：

```text
ToolResult(...)
```

应先转成可读摘要，例如：

```text
camera_scene:
- scene_summary: 桌面上有手机、水杯和耳机
- visible_items: phone, cup, earbuds
- missing_or_uncertain: umbrella not clearly visible
- error: none
```

### 9.4 Page Display Flow

```text
TaskRuntimeResult
  → RunDisplaySnapshot
  → Page Renderer
  → local browser page
```

## 10. 配置与安全

### 10.1 默认模式

默认应支持 mock-safe 运行：

```text
USE_REAL_PROVIDERS=false
```

在 mock 模式下：

- 不访问真实网络。
- 不访问真实摄像头。
- 不访问真实麦克风。
- 页面仍能展示 mock 输入、mock 画面总结和 mock prompt。

### 10.2 真实模式

真实模式需要显式开启：

```text
USE_REAL_PROVIDERS=true
CAMERA_ENABLED=true
MIC_ENABLED=true
```

API key 仍建议通过环境变量提供：

```text
DASHSCOPE_API_KEY
```

### 10.3 Prompt 展示安全

页面显示 prompt 时不得展示：

- API key。
- 原始认证 header。
- 本地绝对路径中的敏感信息。
- 未经用户允许的长期原始音视频。

Prompt 展示仅用于本地开发和演示，展示的是 PromptEngine 最终生成、并实际传入 `LLMProvider.generate(prompt)` 的字符串。它不是模型隐藏推理链，也不是 LLM 输出过程。

Prompt 展示区域默认应可折叠。Prompt 中如包含用户隐私信息，第一版可以本地展示，但不得默认写入 memory。

PromptEngine 不允许把 config、environment variables、HTTP headers 或 provider credentials 放进 prompt context。若 prompt 展示前发现 API-key-like 字符串，应替换为：

```text
[REDACTED]
```

Display trace 可以展示 prompt；Memory 只能写任务结果摘要和必要的用户可见回答，不得默认写入完整 prompt。

## 11. 验收标准

### 11.1 Prompt Engine

- PRD 3 范围内新增或改造的文本 LLM 调用都通过 Prompt Engine 生成 prompt。
- Task Formulation 不再直接拼完整 prompt。
- Final Response Generation 使用 Prompt Engine。
- Prompt Engine 至少支持 `TASK_FORMULATION` 和 `FINAL_RESPONSE`。
- Prompt Engine 输出是字符串。
- 测试能断言 LLMProvider 收到的 prompt 来自 Prompt Engine。
- 测试必须断言 `TaskFormulator` 调用 `LLMProvider.generate(prompt)` 时，`prompt == PromptEngine.build(...).prompt`。
- 测试必须断言 `FinalResponseGenerator` 调用 `LLMProvider.generate(prompt)` 时，`prompt == PromptEngine.build(FINAL_RESPONSE, ...).prompt`。
- PromptEngine 不得把 `going_out` 写死为默认身份；`going_out` 只能作为 task goal、tool result 或 skill metadata 中的具体场景出现。

### 11.2 最终回答

- 最终回答不再只是 `Task completed: <task_goal>`。
- 最终回答能使用 ToolResult 中的视觉总结。
- 当摄像头或多模态 provider 失败时，回答能说明视觉上下文不可用。
- provider 失败时有 deterministic fallback，且 fallback 不能退回到 `Task completed: <task_goal>`。

### 11.3 页面显示器

- 页面能显示用户输入。
- 页面能显示麦克风转写文本。
- 页面能显示当前画面或画面占位。
- 页面能显示画面总结。
- 页面能显示生成的任务目标。
- 页面能显示输入给 LLM 的 prompt。
- 页面能显示最终回答。
- 页面不绕过 EventRuntime / TaskRuntime。

### 11.4 主分支可运行

合并后仍需通过：

```bash
python -m pytest
python main.py
```

默认 mock-safe 配置下，评委应能稳定复现演示效果。

## 12. 推荐 PR 拆分

PRD 3 不应一次性实现。建议拆成以下小 PR。优先级上，先完成 PR 3.1 到 PR 3.4，闭合最终回答；再完成 PR 3.5 到 PR 3.7，建设页面显示器。

### PR 3.1：Prompt Engine 数据契约

目标：

```text
新增 Prompt Engine 的数据对象、prompt 类型和 build 接口。
```

只允许修改：

```text
prompts/__init__.py
prompts/engine.py
prompts/templates.py
tests/prompts/test_prompt_engine.py
```

不接入 LLM，不改 Runtime。`prompts/__init__.py` 必须为空，不做初始化、不加载模板、不创建对象。

### PR 3.2：Task Formulation 接入 Prompt Engine

目标：

```text
让 TaskFormulator 使用 PromptEngine 生成 task formulation prompt。
```

只允许修改：

```text
agent/formulation.py
tests/agent/test_prompt_engine_task_formulation.py
```

不改最终回答，不改页面。

### PR 3.3：Final Response Generator

目标：

```text
新增最终回答生成边界，使用 PromptEngine + LLMProvider 生成用户回答。
```

只允许修改：

```text
agent/final_response.py
tests/agent/test_final_response_generation.py
```

不改 TaskRuntime。

### PR 3.4：TaskRuntime 接入 Final Response Generator

目标：

```text
TaskRuntime 完成任务时使用 FinalResponseGenerator 生成 UserVisibleAgentOutput.final_response。
```

只允许修改：

```text
runtime/task_runtime.py
tests/runtime/test_task_runtime_final_response.py
```

不改 tool、device、provider。

### PR 3.5：运行展示快照

目标：

```text
新增 RunDisplaySnapshot，用于描述页面需要展示的数据。
```

只允许修改：

```text
demo/display_snapshot.py
tests/demo/test_display_snapshot.py
```

不实现页面。

### PR 3.6：本地页面显示器

目标：

```text
新增本地页面，展示用户输入、画面、画面总结、目标、prompt 和回答。
```

只允许修改：

```text
demo/page_viewer.py
demo/static/display.html
tests/demo/test_page_viewer.py
```

不改 Runtime 内部。

### PR 3.7：Demo 接入页面显示器

目标：

```text
DemoRuntime 运行后生成展示快照，并可打开或保存页面显示器。
```

只允许修改：

```text
demo/cli_demo.py
tests/demo/test_cli_demo_page_display.py
```

不改 Prompt Engine、TaskRuntime 或底层 provider。

## 13. 风险与注意事项

1. 不要让页面直接调用摄像头或 LLM。
2. 不要把 prompt 展示和 memory 写入混在一起。
3. 不要在 Prompt Engine 中执行 provider 调用。
4. 不要让 Final Response Generator 选择工具或改变任务状态。
5. 不要把 `going_out` 继续写成所有任务的默认路径。
6. 不要把真实设备访问作为默认测试路径。
7. 不要让 PromptEngine 成为“上帝对象”。它只拼 prompt，不调用模型、不选 skill、不访问设备、不写 memory。
8. 不要让页面成为新的 Runtime。Runtime 产生数据，页面展示数据。
9. 不要把完整 prompt 默认写入 Memory。
10. 不要先做页面再修最终回答。先闭合回答，再做展示。

## 14. 当前版本到 PRD 3 的关键变化

当前版本：

```text
LLM → 只生成 task goal
ToolResult → 只展示在 process
Final Answer → Runtime 模板
Prompt → 不可统一观察
页面 → 无
```

PRD 3 目标：

```text
PromptEngine → 统一 PRD 3 范围内的 LLM prompt
LLM → 生成 task goal + final response
ToolResult → 参与最终回答
Page Display → 展示输入、画面、总结、目标、prompt、回答
```


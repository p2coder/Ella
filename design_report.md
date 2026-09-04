> [!WARNING]
> 本报告描述旧 Runtime，仅保留为历史记录。现役契约见 `docs/runtime_tools_workflow_prd.md`。

# Ella Runtime 设计文档：用户故事与成本控制

## 1. 项目概述

Ella Runtime 是一个 Agent Native 的 AI 生活伴侣原型。它不是固定意图识别加 workflow 的脚本系统，而是一个可运行的 Agent Runtime Harness，用来验证以下主链路：

```text
RawSignal
→ EventRuntime
→ PresenceRuntime
→ TaskRuntime
→ TaskSession
→ AgentExecutionContext
→ SubAgent
→ CapabilityExecutor
→ ToolResult
→ FinalResponseGenerator
→ TaskCompletionPackage
→ MemoryManager
→ RunDisplaySnapshot / Web UI
```

当前实现重点不是把所有真实世界能力一次性做满，而是先建立清晰边界：

- Runtime 管生命周期。
- Provider / Device 管真实模型和真实设备。
- Source 把外部输入变成 RawSignal。
- SubAgent 决定下一步动作。
- CapabilityExecutor 只执行一个动作。
- PromptEngine 只拼 prompt，不调用模型。
- MemoryManager 是唯一 memory 读写入口。
- Web UI 只提交输入和展示 Runtime 结果，不成为新的 Runtime。

## 2. 计划实现的用户故事与实际实现情况

### 2.1 用户故事总览

| 编号 | 计划用户故事 | 目标价值 | 当前实现状态 |
| --- | --- | --- | --- |
| US-1 | 用户可以通过文本向 Ella 发起请求。 | 验证最小 Runtime 输入链路。 | 已实现。Web UI 和 AppRuntime 支持文本输入。 |
| US-2 | 用户可以通过麦克风说话，Ella 将语音转成文本后执行任务。 | 支持更自然的输入方式。 | 已实现手动有界麦克风入口，ASR 后复用文本链路。 |
| US-3 | 用户可以要求 Ella 查看当前画面。 | 验证真实或 mock 摄像头、多模态模型和工具调用闭环。 | 已实现 CameraSceneTool、CameraProvider / MultimodalProvider 注入和 Web UI 展示。 |
| US-4 | 用户可以看到 Ella 生成的任务目标。 | 降低调试和演示时的理解成本。 | 已实现 RunDisplaySnapshot / Web UI 展示 task goal。 |
| US-5 | 用户可以看到 Ella 看见的画面、画面摘要和可见物品。 | 证明视觉结果确实进入 Runtime。 | 已实现 captured frame reference、scene summary、visible_items 展示。 |
| US-6 | 用户可以看到 Ella 的最终回答。 | 形成可用的用户体验闭环。 | 已实现 FinalResponseGenerator，最终回答可由 LLM 基于上下文生成。 |
| US-7 | 用户可以看到工具执行过程和工具结果摘要。 | 展示 Agent 执行过程而非黑盒输出。 | 已实现 tool trace、tool_results_summary 和页面展示。 |
| US-8 | 用户可以看到输入给 LLM 的 prompt。 | 便于调试 PromptEngine 和模型调用。 | 部分实现。Prompt trace 已进入数据结构，页面目前保留展示边界，部分 prompt 展示仍可继续完善。 |
| US-9 | Ella 可以把已完成任务写入 memory。 | 让系统具备最小长期上下文能力。 | 已实现。MemoryManager 追加保存每次完成结果。 |
| US-10 | Ella 后续回答可以参考历史 memory。 | 让回答具备连续性。 | 已实现最小版本。TaskRuntime 查询全部 memory 并注入 final response prompt。 |
| US-11 | 工具可以自描述，让 LLM 根据工具定义判断是否使用。 | 从固定 workflow 走向动态能力选择。 | 已实现 ToolDefinition、ToolManager discovery、SubAgent 可见工具决策边界。 |
| US-12 | Skill 可以通过工具名声明所需工具。 | 让 Skill 成为策略上下文，而不是工具容器。 | 已实现 required_tools / optional_tools 元数据解析。 |
| US-13 | 工具输入输出需要结构化校验。 | 防止 LLM 生成错误参数后直接执行工具。 | 已实现 CapabilityExecutor 输入/输出 schema 校验。 |
| US-14 | 默认运行不访问真实网络、摄像头或麦克风。 | 控制成本并避免测试不稳定。 | 部分实现。项目支持 mock / real 分层，但当前本地配置可能选择真实 provider，需要通过配置管理保持 mock-safe 默认。 |
| US-15 | 后台低频环境理解、疲劳/久坐提醒。 | 形成更完整的 Ambient Agent 方向。 | 未实现。PRD 2.1 中作为后续阶段规划。 |

### 2.2 已实现的主要用户路径

#### 文本输入路径

用户在 Web UI 输入文本后，系统执行：

```text
Web UI
→ AppRuntime.run_text_with_display(text)
→ CLITextSignalSource
→ RawSignal
→ EventRuntime.publish()
→ MainAgent / TaskFormulator
→ TaskRuntime.submit()
→ TaskRuntime.run_until_complete()
→ FinalResponseGenerator
→ MemoryManager
→ RunDisplaySnapshot
→ Web UI
```

该路径已经可用于普通文本请求和演示。

#### 麦克风输入路径

用户点击 Web UI 的麦克风按钮后，系统执行：

```text
Web UI
→ AppRuntime.run_microphone_with_display()
→ MicrophoneSource.capture_transcript()
→ SpeechProvider
→ transcript
→ CLITextSignalSource
→ 文本输入路径
```

设计上刻意让 ASR 后的文本复用文本链路，避免为麦克风单独分叉 Runtime 行为。

#### 视觉任务路径

当 SubAgent 决定需要视觉上下文时，系统执行：

```text
SubAgent
→ ExecutionDecision(CALL_TOOL, camera_scene)
→ CapabilityExecutor
→ ToolManager.get_tool("camera_scene")
→ CameraSceneTool.run(context, arguments)
→ CameraProvider.capture_frame()
→ MultimodalProvider.describe()
→ ToolResult(scene_summary, visible_items)
→ TaskSession.tool_trace
→ FinalResponseGenerator
→ Web UI
```

当前视觉输出已经从 `umbrella_visible` 这类场景绑定字段中解耦，通用视觉工具只描述 `scene_summary` 和 `visible_items`。

#### Memory 路径

任务完成后：

```text
TaskCompletionPackage
→ MemoryManagementRequest
→ MemoryManager.handle()
→ append memory file
```

生成最终回答前：

```text
MemoryManager.query()
→ all stored memory
→ TaskRuntime._memory_context()
→ FinalResponseGenerator.generate(memory_context=...)
→ PromptEngine.build(FINAL_RESPONSE)
```

第一版 memory 策略非常简单：全部保存，查询时全部提交给 prompt。

### 2.3 计划但尚未完成的用户故事

以下能力已经进入 PRD 或规划，但尚未完整实现：

1. **低频背景感知**
   - 计划：摄像头约五分钟懒采样，判断场景变化或稳定状态。
   - 当前：只有任务模式下的 CameraSceneTool，尚无 AmbientSensorRuntime。

2. **AmbientState 时间序列**
   - 计划：记录场景稳定持续时间、变化时间、声音活动和安静持续时间。
   - 当前：基础 ambient state 边界存在，但没有完整低频感知循环。

3. **疲劳 / 久坐提醒候选**
   - 计划：基于稳定画面、时间和声音活动生成温和提醒候选。
   - 当前：未实现，仍属于 PRD 2.1 后续阶段。

4. **完整权限和角色模型**
   - 计划：不同 agent role 只能发现和使用对应能力。
   - 当前：Tool / Skill 已有 role visibility 雏形，默认仍以 `main_agent` 兼容。

5. **更强的 Memory 检索**
   - 计划：未来可增加摘要、过滤、时间窗口、向量检索或用户偏好抽取。
   - 当前：只实现全部追加保存和全部读取。

6. **更完整的 Prompt Trace 页面展示**
   - 计划：页面展示 task formulation prompt 和 final response prompt。
   - 当前：数据边界已经存在，但页面展示还可以继续打磨。

## 3. 技术架构设计

### 3.1 Runtime 分层

```text
Input Layer
  ├─ Web UI
  ├─ CLI
  └─ MicrophoneSource

Application Layer
  └─ AppRuntime

Runtime Layer
  ├─ EventRuntime
  ├─ PresenceRuntime
  └─ TaskRuntime

Agent Layer
  ├─ MainAgent
  ├─ TaskFormulator
  ├─ SubAgent
  └─ FinalResponseGenerator

Capability Layer
  ├─ ToolManager
  ├─ ToolDefinition
  ├─ CapabilityExecutor
  ├─ CameraSceneTool
  └─ Mock Tools

Provider / Device Layer
  ├─ ProviderFactory
  ├─ DeviceFactory
  ├─ Qwen Providers
  ├─ Mock Providers
  ├─ CameraProvider
  └─ MicrophoneProvider

Persistence / Display
  ├─ MemoryManager
  ├─ RunDisplaySnapshot
  └─ Local Web UI
```

### 3.2 关键边界

#### AppRuntime

`AppRuntime` 是 CLI 和 Web UI 共享的应用入口。它负责把输入提交给 Runtime，并返回可展示结果。UI 不直接接触 EventRuntime、TaskRuntime、ToolManager 或 MemoryManager。

#### PromptEngine

`PromptEngine` 只接受 `prompt_type` 和结构化上下文，输出 prompt 字符串。它不调用 LLM，不访问文件，不访问设备，不读取 memory。prompt 如何拼接完全封装在 PromptEngine 内部。

#### Tool Runtime

Tool 通过 `ToolDefinition` 自描述能力。SubAgent 看到的是当前任务可见的 ToolDefinition 快照，而不是 Tool 实例。CapabilityExecutor 根据 `ExecutionDecision` 进行单步执行，并负责输入/输出 schema 校验。

#### MemoryManager

`MemoryManager` 是唯一 memory 读写入口。当前实现采用追加式文件存储，查询时返回全部内容。PromptEngine 不直接读 memory，TaskRuntime 负责读取并作为 `memory_context` 传给最终回答生成器。

## 4. 成本控制技巧：想到的与实际采用的

### 4.1 成本控制总览

| 成本控制技巧 | 计划/设想 | 实际采用情况 |
| --- | --- | --- |
｜Prompt Cache｜Prompt模版化，前缀不变，便于推理的kv cache|未采用，当前只是简单组装，未控制头部不变|
| 默认 mock provider | 默认测试和本地开发不访问真实网络或设备。 | 已采用架构分层和 mock provider；实际默认配置需要持续校准，避免误启真实 provider。 |
| 真实 provider 显式开启 | 只有配置开启时才访问 Qwen、摄像头、麦克风。 | 已采用 ProviderFactory / DeviceFactory 分层。 |
| 任务模式有界采样 | CameraSceneTool 每次调用限制帧数和时长。 | 已采用。CameraSceneTool 支持 `max_frames` / `max_duration_seconds`。 |
| 不做持续视频流 | 第一版不做浏览器摄像头直播，也不持续上传帧。 | 已采用。Web UI 只展示 Runtime 产出的 frame reference。 |
| 麦克风手动触发 | 不做 always-listening，先做一次性有界录音。 | 已采用。Web UI 麦克风按钮触发一次 bounded capture。 |
| ASR 后复用文本链路 | 避免麦克风路径产生独立 Runtime 分支。 | 已采用。转写后重新走文本 RawSignal。 |
| 低频背景理解后置 | 不一开始做持续环境理解和疲劳提醒。 | 已采用。Ambient 低频能力仍停留在规划阶段。 |
| PromptEngine 统一 prompt | 避免多处重复拼 prompt，降低调试和 token 浪费。 | 已采用。Task formulation、final response、execution prompt 走 PromptEngine 边界。 |
| 工具定义快照 | LLM 只看当前任务可见工具，不暴露全部内部能力。 | 已采用。ToolManager 返回可见 ToolDefinition。 |
| 单步执行器 | CapabilityExecutor 只执行一个动作，避免隐藏无限循环。 | 已采用。循环和 `max_steps` 留在 TaskRuntime。 |
| max_steps 边界 | 防止 WAIT / REPLAN / 工具调用无限循环。 | 已采用。TaskRuntime 有 `run_until_complete(..., max_steps)`。 |
| schema 校验 | 避免非法参数导致真实工具或真实 API 被错误调用。 | 已采用。CapabilityExecutor 校验输入输出 schema。 |
| 不保存原始音视频 | 默认不长期存储原始媒体，减少隐私和存储成本。 | 已采用。raw media 默认不存，调试存储通过配置控制。 |
| HTML escape 和本地绑定 | 防止本地 UI 暴露敏感信息或 XSS。 | 已采用。默认绑定 127.0.0.1，页面输出 escape。 |
| Memory 第一版全量读取 | 用最简单机制换取可用性，避免先做昂贵检索系统。 | 已采用。当前 query 返回全部 memory。 |


### 4.2 实际已经采用的成本控制

#### Mock-first 开发和测试

系统设计了 MockLLMProvider、MockSpeechProvider、MockVisionProvider、MockMultimodalProvider、MockCameraProvider 和 MockMicrophoneProvider。这样大部分测试不需要真实 API key、真实摄像头或真实麦克风，避免：

- 网络费用。
- API 调用费用。
- 设备权限弹窗。
- 测试不稳定。

#### Provider / Device 工厂隔离真实能力

真实模型和真实设备不散落在 Runtime 里，而是通过 ProviderFactory 和 DeviceFactory 创建。Runtime 只依赖接口，因此可以在 mock 和 real 之间切换。

#### 有界工具调用

`CameraSceneTool` 不允许无限采样。调用时可以使用：

```text
max_frames
max_duration_seconds
```

这样可以控制多模态模型输入规模，也避免摄像头长时间占用。

#### 单动作 Executor + TaskRuntime max_steps

CapabilityExecutor 不实现完整 ReAct loop，只执行一个 `ExecutionDecision`。TaskRuntime 控制循环推进和最大步数。这避免了某个工具或 LLM 决策失控后无限调用模型。

#### Tool schema 校验

工具调用前校验 input schema，调用后校验 output schema。非法参数不会触发工具执行，非法输出不会被当作可信事实进入后续 prompt。

#### PromptEngine 统一上下文组装

PromptEngine 把 prompt 拼接逻辑集中起来，避免不同模块各自拼接重复上下文。这样后续可以统一控制：

- 字段顺序。
- 是否加入 memory。
- 是否加入 tool definitions。
- prompt 长度。
- secret redaction。

#### Memory 先做最小版本

当前 Memory 不做向量库、embedding、召回排序或摘要压缩。它只做：

```text
handle(request) → append
query() → load all
```

这降低了实现复杂度和运行成本。后续如果 memory 变大，再引入摘要或检索策略。

### 4.3 想到但尚未采用的成本控制

#### 低频场景变化检测

PRD 2.1 规划了本地低成本图像变化判断：

```text
STABLE → 不调用视觉模型，只更新时间
CHANGED → 调用 VisionProvider
UNKNOWN → 建立或刷新基准
```

这能显著降低持续环境理解的多模态调用成本，但当前尚未实现。

#### 声音活动检测 / VAD

计划通过本地 VAD 先判断是否存在语音，再决定是否调用 SpeechProvider。当前实现是手动触发有界录音，还没有 always-listening 或 VAD。

#### Memory 摘要与窗口化

当前 query 返回全部 memory。未来可以改为：

- 最近 N 条。
- 按 task type 过滤。
- 先做摘要再进 prompt。
- 用户偏好单独抽取。

这些能控制 prompt token 成本，但当前为了简单和可观察性尚未采用。并且需要综合考虑与prompt cache相比两者如何平衡

#### ToolDefinition 裁剪

当前 ToolDefinition 已经是结构化的，但未来可以根据任务进一步裁剪给 LLM 的工具描述，例如只传当前 Skill 相关工具或只传 name/description/input_schema，减少 token。

## 5. 当前实现的取舍

### 5.1 为什么先做 Web UI

Ella 的核心价值不是“能不能调一个 API”，而是展示：

```text
用户说了什么
Ella 看见了什么
Ella 形成了什么目标
Ella 调用了哪些工具
Ella 给 LLM 的 prompt 里有什么上下文
Ella 最终如何回答
```

Web UI 能让评审直观看到 Runtime 的数据流，也能帮助调试模型行为。

### 5.2 为什么 Memory 先做全量读取

完整 memory 系统需要检索、摘要、权限、遗忘策略和隐私策略。当前阶段最重要的是让 memory 进入 prompt，验证端到端链路。因此第一版选择：

```text
所有完成结果都保存。
查询时全部返回。
```

这个方案简单、可测试、可解释，也方便后续替换为更高级的检索策略。

### 5.3 为什么工具不再绑定 going_out

早期 `going_out` 用于验证视觉闭环，但它不应该成为系统主流程。当前已经把通用视觉工具从 `umbrella_visible` 这类场景字段中解耦，改为返回通用的 `scene_summary` 和 `visible_items`。是否需要伞，应由任务目标、Skill 语境和最终回答生成器判断。

## 6. 风险与后续工作

### 6.1 当前风险

1. **配置默认值需要继续校准**
   - 文档要求 mock-safe 默认，但本地配置可能启用真实 provider。

2. **Memory 全量注入会增长 prompt token**
   - 当前实现简单，但 memory 变大后需要摘要或检索。

3. **Prompt 展示仍需完善**
   - Prompt trace 数据存在，但 Web UI 展示可以继续补齐。

4. **SubAgent ReAct 决策仍在演进中**
   - 当前默认 ReAct 和动态工具决策已建立，但旧测试和旧策略断言仍需逐步更新。

5. **低频 Ambient 能力尚未实现**
   - 疲劳提醒、久坐提醒和环境稳定状态仍停留在 PRD 阶段。

### 6.2 下一步建议

1. 校准默认配置，保证不开启真实 provider 时测试和 demo mock-safe。
2. 完善 Web UI 中 PromptEngine prompt trace 的展示。
3. 为 Memory 增加摘要或最近窗口，避免 prompt 过长。
4. 实现低频 scene change detector，但先保持本地低成本判断，不直接调用视觉模型。
5. 继续把 SubAgent 的策略和工具选择从 demo 场景中抽象出来。

## 7. 总结

Ella 当前已经从最初的 Runtime 骨架，推进到一个可交互、可观察、可接真实模型和设备的本地 Agent Runtime Demo。

已经实现的核心闭环是：

```text
用户输入
→ Runtime 接收并路由
→ Agent 生成任务目标
→ SubAgent 选择动作
→ Executor 调用工具
→ 工具返回结构化结果
→ PromptEngine 组装最终回答 prompt
→ LLM 生成回答
→ Memory 保存结果
→ Web UI 展示过程与结果
```

成本控制上，项目已经采用 mock-first、有界采样、单步执行器、schema 校验、PromptEngine 集中拼接、本地 Web UI 和最小 Memory 等策略。后续最重要的成本优化会集中在低频环境理解、memory 摘要和工具定义裁剪上。

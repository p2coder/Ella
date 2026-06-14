# Ella Runtime PRD 2.0：真实感知与真实模型接入

## 1. 产品概要

Ella Runtime 2.0 建立在 MVP Runtime 骨架之上，目标是把现有的事件驱动任务生命周期接入真实模型和真实感知输入。

PRD 2.0 不推翻现有架构。它要解决的是：让 Ella 能够从文本、麦克风和摄像头接收真实用户输入，通过合适的语言模型和多模态模型理解这些输入，然后继续进入同一条 Runtime 生命周期：

```text
真实输入
→ RawSignal
→ Event Trigger Pipeline
→ EventRuntime
→ PresenceRuntime
→ MainAgent
→ TaskRuntime
→ TaskSession
→ SubAgent
→ Tools / Skills
→ UserVisibleAgentOutput
→ MemoryManager
```

PRD 2.0 的目标是让 Ella 不再只是一个 CLI demo，而更像一个真实存在于桌面环境中的 AI 生活伴侣：架构默认支持接入麦克风和摄像头，但默认运行和默认测试使用 mock providers，不访问真实设备；在显式开启真实 provider 和对应设备开关后，它可以通过默认麦克风听见用户，通过默认摄像头看见当前环境，使用真实 LLM 进行任务理解与表达，并在任务需要时使用多模态模型理解视觉或音频上下文。

第一版真实模型 provider 默认使用阿里云 Qwen 系列。所有 provider key、模型名和设备开关通过环境变量配置，不提交到仓库。

## 2. 产品目标

1. 接入真实 LLM，用于任务目标设定、策略推理支持、用户可见回复和结构化摘要。
2. 架构支持接入电脑默认摄像头，作为真实视觉输入来源；默认运行不访问真实摄像头。
3. 架构支持接入电脑默认麦克风，作为真实音频输入来源；默认运行不访问真实麦克风。
4. 增加必要的多模态模型边界，使 Ella 能理解摄像头画面、用户语音以及音视频与文本组合上下文。
5. 保留 MVP 的 Runtime 原则：外部信号先作为事件进入系统，PresenceRuntime 不直接轮询世界。
6. 保留 Ella 区别于 intent + workflow 系统的核心特点：Ella 设定任务目标，在 TaskSession 内选择执行策略，并通过 Runtime 状态自适应，而不是把每个输入硬映射到固定 workflow。
7. 即使接入真实模型和真实设备，也必须保留 mock provider，使默认测试可重复、可自动化、可在无设备和无 API key 环境运行。

## 3. 非目标

以下内容不属于 PRD 2.0 的必做范围：

- 生产级认证、计费或云端部署。
- 多用户账号系统。
- 移动端 App 接入。
- 持续录像或长期保存原始音视频。
- 未经用户可见提示的后台监控式行为。
- 完整自主多 Agent 并发。
- 高级向量记忆或语义检索。
- 真实智能家居、日历、邮件或定位集成。
- 用户可见的权限管理 UI。
- 模型微调。
- 把唤醒词检测作为硬性要求。

PRD 2.0 使用环境变量保存 API key、模型选择和设备设置。系统默认不得永久保存原始摄像头画面或麦克风音频。

## 4. 用户体验目标

目标 demo 仍然接近当前的 going-out 场景，但要引入真实感知：

```text
用户说：“Ella，我要出门了”

Ella 可以：
1. 通过默认 always-listening 麦克风听到这句话。
2. 把语音转成用户事件。
3. 在任务需要视觉上下文时使用摄像头。
4. 请求多模态模型总结当前画面。
5. 结合用户偏好、环境摘要、视觉上下文和任务目标。
6. 给出简短、必要的出门提醒。
```

示例输出：

```text
[Process]
我听到你说你准备出门。
我检查了当前场景和可用上下文。
我会保持提醒简短。

[Final Answer]
出门前确认一下手机、钥匙和钱包。我没有清楚看到雨伞，如果天气不确定，可以考虑带一把。
```

过程区仍然只展示结构化摘要，不展示隐藏推理链。

## 5. 核心 Runtime 原则

### 5.1 事件驱动的感知

摄像头和麦克风输入必须通过 source adapter 进入 Ella，并产出 `RawSignal`、`Observation` 或标准化事件。

PRD 2.0 允许麦克风默认 always-listening，摄像头默认常开，但这不改变核心边界：设备采集层只负责产生信号或观察结果，PresenceRuntime 仍然不直接轮询设备。设备状态必须通过用户可见文字提示表达，例如“正在听”“正在看”“正在使用模型上下文”。

默认运行模式必须使用 mock providers，不访问真实网络、真实麦克风或真实摄像头。只有同时满足以下条件时，才允许访问真实设备：

- `ELLA_USE_REAL_PROVIDERS=true`
- 麦克风访问还需要 `ELLA_MIC_ENABLED=true`
- 摄像头访问还需要 `ELLA_CAMERA_ENABLED=true`

PresenceRuntime 不得直接调用：

- 摄像头 API
- 麦克风 API
- ASR provider
- vision model provider
- multimodal model provider

正确边界是：

```text
CameraSource / MicrophoneSource
→ RawSignal
→ Event Trigger Pipeline
→ Router / Presence Queue
```

如果任务执行过程中需要视觉或音频上下文，SubAgent 应该通过 tool 获取，而不是直接访问设备 API。

EventRuntime 的统一入口仍然是 `RawSignal`。麦克风、摄像头或其他 source 不应直接把 `StandardizedEvent` 交给 EventRuntime，也不应直接创建 TaskSession 或修改 AmbientState。所有 source 产出的信号都应先进入 Event Trigger Pipeline，再由 Router 决定去向。

第一版不要新增 `RawSignal` 子类。音频、文本、图片等输入都使用现有 `RawSignal`，通过 `source`、`payload` 和 `signal_type` / `payload["type"]` 等字段表达：

```text
source="microphone"
payload={"type": "audio", ...}

source="speech_transcript"
payload={"type": "text", "text": "..."}

source="camera"
payload={"type": "image_summary", "summary": "..."}
```

摄像头默认采用两种采样模式：

- 背景模式：约每 5 秒捕获一次画面，用于更新 AmbientState 或背景观察摘要。
- 任务模式：当任务明确需要视觉上下文时，例如“你看看我带没带伞”，提高到约每秒 1 帧，供视觉 / 多模态 tool 生成任务内观察结果。

背景模式产生的视觉摘要默认只进入 AmbientState，不应自动创建新任务。任务模式产生的视觉结果必须携带当前 `task_id`、`session_id` 和 `trace_id`，并写入当前 TaskSession 的 tool trace。

### 5.2 模型边界

LLM 和多模态模型调用必须位于明确的 provider 接口之后。

推荐 provider 边界：

```text
LLMProvider
  - 结构化文本生成
  - 任务目标设定支持
  - 用户回复生成

SpeechProvider
  - 音频转写
  - 可选音频事件摘要

VisionProvider
  - 图片 / 帧摘要
  - 物体和场景描述

MultimodalProvider
  - 文本 + 图片联合理解
  - 语音转写 + 图片联合理解
```

Runtime 应依赖 provider 接口，而不是直接依赖具体模型 SDK。第一版真实 provider 默认使用阿里云 Qwen 系列；测试必须使用 mock provider。

ProviderFactory 负责根据环境变量创建 LLM / Speech / Vision / Multimodal providers。DeviceFactory 负责根据环境变量创建 Microphone / Camera providers。`ELLA_USE_REAL_PROVIDERS=false` 时不得访问真实网络、真实麦克风或真实摄像头。

### 5.3 任务自主性

Ella 不能退化成一个 intent classifier：

```text
“我要出门了” → going_out workflow
```

PRD 2.0 期望的流程是：

```text
用户 / 事件上下文
→ MainAgent 形成任务目标
→ TaskRuntime 创建隔离 TaskSession
→ SubAgent 选择策略
→ SubAgent 请求需要的 tool / 模型上下文
→ TaskRuntime 一次推进一个执行步骤
→ CompletionPackage 和 MemoryManager 收口任务
```

`going_out` 可以继续作为 skill 存在，但它应该由 SubAgent 在策略选择阶段选中，而不是由事件解析或硬编码意图路由直接决定。

## 6. 必需能力

### 6.1 真实 LLM 接入

Ella 必须支持真实 LLM provider，用于：

- 任务目标设定。
- 打扰判断相关的解释摘要。
- 策略推理支持。
- 用户可见最终回复。
- 过程摘要。
- memory 摘要。

第一版真实模型 provider 默认使用阿里云 Qwen 系列。具体模型名称通过环境变量配置。

当 Runtime 需要结构化契约时，LLM provider 必须支持结构化输出。自由文本模型回复不能替代现有数据契约，例如 `HandoffRequest`、`ExecutionDecision`、`StrategyDecision`、`UserVisibleAgentOutput` 或 `TaskCompletionPackage`。

验收标准：

- 真实 LLM provider 可以在测试中替换为 mock provider。
- 模型失败时返回结构化错误。
- LLM 调用失败时 Runtime 状态仍然有效。
- 不向用户展示隐藏推理链。

### 6.2 默认摄像头接入

Ella 必须支持电脑默认摄像头作为视觉来源。

必需行为：

- 默认打开电脑摄像头。
- 背景模式下约每 5 秒捕获一帧，用于背景状态理解。
- 任务模式下约每秒捕获 1 帧，用于摄像头相关任务。
- 将捕获到的视觉输入转换为 Runtime signal 或 tool 可访问的 observation。
- 允许任务通过 tool 请求视觉上下文。
- CameraSceneTool 每次调用必须是有边界的，例如默认 `max_frames=3` 或 `max_duration_seconds=3`。
- 默认避免连续录像。
- 默认不保存原始帧，除非显式开启 debug 配置。

验收标准：

- 摄像头集成可以关闭。
- 测试可以使用 mock camera provider，不依赖真实摄像头。
- 摄像头失败不会导致 Runtime 崩溃。
- 用户可见过程摘要能说明视觉上下文不可用。

### 6.3 默认麦克风接入

Ella 必须支持电脑默认麦克风作为音频来源。

必需行为：

- 默认使用 always-listening 方式从电脑麦克风监听用户语音。
- 通过 speech provider 或 multimodal provider 转写语音。
- 将转写结果转换为 `USER_UTTERANCE` 事件。
- 保留 CLI 输入作为 fallback 输入源。
- 默认不保存原始音频。

验收标准：

- 麦克风集成可以关闭。
- 测试可以使用 mock microphone provider，不依赖真实麦克风。
- 转写失败时返回结构化错误。
- 用户主动语音可以进入与 CLI 输入相同的 EventRuntime 路径。

### 6.4 必要多模态模型接入

当任务需要超过文本的信息时，Ella 必须支持多模态理解。

必需行为：

- 在需要视觉上下文时总结摄像头画面。
- 结合用户表达、环境摘要、用户偏好和视觉摘要。
- 返回结构化 observation，而不是只有自由文本。
- 让多模态输出携带并延续 `trace_id`、`task_id` 和 `session_id`。

验收标准：

- going-out reminder 可以包含真实或 mock 的视觉场景摘要。
- 当多模态 provider 不可用时，系统可以以纯文本模式继续运行。
- 模型输出进入任务执行前必须被标准化。
- Runtime 不会把每一次视觉变化都当成新的用户任务。

## 7. PRD 2.0 主流程

### 7.1 语音触发任务

```text
DefaultMicrophoneSource
→ always-listening audio capture
→ RawSignal(source="microphone", payload={"type": "audio", ...})
→ SpeechProvider.transcribe()
→ RawSignal(source="speech_transcript", payload={"type": "text", "text": ...})
→ EventRuntime.publish(raw_signal)
→ EventTriggerPipeline
→ USER_UTTERANCE Event
→ PresenceRuntime
→ MainAgent.create_handoff()
→ TaskRuntime.submit()
→ TaskRuntime.run_until_complete()
```

### 7.2 视觉辅助任务

```text
TaskSession running
→ SubAgent 判断需要视觉上下文
→ CapabilityExecutor 调用 CameraSceneTool
→ CameraProvider 切换到任务模式并按约 1fps 捕获有限帧数
→ VisionProvider / MultimodalProvider 总结画面
→ ToolResult 追加到 TaskSession.tool_trace
→ SubAgent 决定下一步动作
```

### 7.3 背景视觉状态

```text
DefaultCameraSource
→ background capture every ~5s
→ VisionProvider / MultimodalProvider 生成轻量 scene summary
→ RawSignal(source="camera", payload={"type": "image_summary", "summary": ...})
→ EventRuntime.publish()
→ EventTriggerPipeline
→ Observation / EventCandidate
→ SessionAwareEventRouter
→ AMBIENT_STATE
→ AmbientState 更新
```

背景视觉状态只更新 Ella 对当前环境的理解，不应自动打扰用户，也不应直接创建新任务。

### 7.4 文本 fallback

CLI 输入仍然有效：

```text
CLITextSignalSource
→ RawSignal(source="cli_input", payload={"type": "text", "text": ...})
→ EventRuntime.publish()
→ TaskRuntime
```

这样可以保证本地开发和自动化测试在没有设备或模型 API key 的环境里仍然稳定。

## 8. 数据与隐私要求

PRD 2.0 会引入敏感的本地输入。Runtime 必须保守处理这些数据。

要求：

- 默认不保存原始音频。
- 默认不保存原始摄像头画面。
- 除非显式开启 debug 模式，否则只保存结构化摘要。
- Observation 中应包含 source、timestamp、trace 和 provider metadata。
- 当真实摄像头或麦克风不可用时，应在日志或结构化结果中清楚说明。
- API key、模型名和设备设置通过环境变量读取，不得提交到仓库。
- 所有真实 provider 都必须能在测试中替换为 mock provider。
- UI 或 CLI 必须用文字提示 Ella 当前是否正在听、正在看或正在使用模型上下文。

## 9. 错误处理要求

Runtime 必须优雅降级：

- 如果摄像头访问失败，继续使用文本 / 音频上下文。
- 如果麦克风访问失败，允许使用 CLI 输入。
- 如果 ASR 失败，返回未提交结果或澄清结果，不得污染任务状态。
- 如果视觉或多模态理解失败，允许 SubAgent 带着明确的缺失上下文继续执行或重规划。
- 如果 LLM provider 失败，保留 TaskSession 状态并返回结构化失败。

任何模型或设备失败都不能绕过 TaskSession 状态机。

## 10. 测试要求

PRD 2.0 必须通过 provider 边界支持确定性测试。

必需测试类别：

- LLM provider 契约测试。
- Speech provider 契约测试。
- Camera provider 契约测试。
- Vision / multimodal provider 契约测试。
- 麦克风转写生成用户事件的 Event Pipeline 测试。
- 摄像头 / 视觉场景摘要 tool 测试。
- 证明模型或设备失败不会破坏 TaskSession 状态的 Runtime 测试。
- 使用 mock provider 的端到端 demo 测试。

以下命令必须持续通过：

```bash
python -m pytest
python main.py
```

真实摄像头、真实麦克风和需要网络模型调用的测试应为 opt-in，不应进入默认测试套件。

## 11. 建议实施阶段

### Phase 1：Provider 契约

增加 provider 接口和 mock provider：

- LLM。
- speech / transcription。
- camera capture。
- vision / multimodal summary。

这一阶段不得让 Runtime 行为依赖真实外部服务。

### Phase 2：真实 LLM Provider

在现有契约后面接入阿里云 Qwen provider，用于任务目标设定、SubAgent 决策支持、最终回复生成或 memory 摘要生成。

结构化 Runtime 对象仍然是系统事实来源。`agent/`、`runtime/` 和 `sessions/` 模块不得直接 import Qwen provider，只能依赖 `LLMProvider` 等 provider 接口，由 ProviderFactory 或应用组装层注入。

### Phase 2.5：ProviderFactory

增加 ProviderFactory，根据环境变量创建 mock 或 Qwen providers。

在 Qwen provider 接入前，ProviderFactory 只支持 mock providers 或 provider unavailable。默认 `ELLA_USE_REAL_PROVIDERS=false` 时必须返回 mock providers，且不得访问真实网络。缺少 API key 或真实 provider 尚未接入时不得导致应用启动崩溃，应返回 provider unavailable 或 fallback mock。

### Phase 2.6：Device provider contracts and DeviceFactory

增加 Microphone / Camera provider 契约、mock / unavailable device provider，以及 DeviceFactory。

默认 `ELLA_USE_REAL_PROVIDERS=false` 时必须返回 mock device providers。只有 `ELLA_USE_REAL_PROVIDERS=true` 且 `ELLA_MIC_ENABLED=true` / `ELLA_CAMERA_ENABLED=true` 时，才允许真实设备 provider 访问真实麦克风或真实摄像头。

### Phase 2.7：Qwen Provider and Factory Wiring

增加阿里云 Qwen provider，并把 Qwen 分支接入 ProviderFactory。默认测试不得真实联网，真实调用只能放在 opt-in 测试中。

### Phase 3：麦克风 Source

增加默认麦克风 always-listening 捕获和转写。第一版继续使用现有 `RawSignal`，用 `source="speech_transcript"` 和 `payload={"type": "text", "text": ...}` 表达转写文本，再由 Event Trigger Pipeline 标准化为 `USER_UTTERANCE` 事件。第一版可以直接使用 mock microphone + mock speech provider 生成 `speech_transcript` RawSignal，不要求保留 `source="microphone"`、`payload={"type": "audio"}` 的中间 RawSignal。UI 或 CLI 必须显示“正在听”。

### Phase 4：摄像头和视觉 Tool

增加默认摄像头常开帧捕获和 scene-summary tool。

背景模式约每 5 秒捕获一次用于 AmbientState。任务需要视觉上下文时，由执行链路调用该 tool，并提升到约每秒 1 帧。每次 tool 调用必须有明确上限，例如 `max_frames=3` 或 `max_duration_seconds=3`，不能形成无限采样窗口。摄像头输入不应自动创建新任务，除非后续显式把它作为 event source 路由进系统。

### Phase 4.5：going_out 视觉策略决策

在多模态 demo 前，必须让 going_out 相关任务在需要视觉上下文时可以生成 `CALL_TOOL(camera_scene)`。这个能力可以来自 `skill/skills/going_out/SKILL.md` 的 metadata，也可以在必要时由 `sessions/subagent.py` 的 deterministic 规则支持。

### Phase 5：多模态 going-out demo

升级 going-out demo 前，必须确认 LLMProvider 已经能被 demo / EventRuntime 注入，且 going_out 已经能生成 `CALL_TOOL(camera_scene)`。如果前置能力缺失，应停止实现 demo 并说明依赖未满足，不能在 demo 中硬编码绕过 Runtime。

升级 going-out demo，让 Ella 能结合：

- 用户语音意图。
- 当前场景摘要。
- 用户偏好摘要。
- 环境摘要。
- task-local tool 结果。

用户可见输出应保持简洁、直接、以用户为中心。

### Phase 6：能力治理

在开放用户可安装 tool / skill 或多个专用 agent role 前，实现 `doc/todo.md` 中记录的基于角色的 skill / tool 可见性。

## 12. 验收标准

PRD 2.0 成功的标准：

- Ella 可以通过 provider 边界使用真实 LLM。
- Ella 可以通过默认 always-listening 麦克风接收语音，并转换为 Runtime 事件。
- Ella 可以在任务需要视觉上下文时访问默认摄像头。
- Ella 可以在背景模式下约每 5 秒更新一次视觉 AmbientState。
- Ella 可以在摄像头相关任务中约每秒捕获 1 帧用于任务内视觉理解。
- Ella 可以使用多模态模型生成结构化场景或上下文摘要。
- Runtime 仍然是事件驱动的。
- PresenceRuntime 不直接轮询摄像头、麦克风或模型。
- TaskRuntime 仍然是任务生命周期 owner。
- SubAgent 仍然负责决定下一步任务动作。
- mock provider 让默认测试套件保持确定性。
- `python main.py` 不需要真实设备或 API key 也能继续运行。

## 13. 已确认的产品决策

PRD 2.0 采用以下默认决策：

- 第一版真实模型 provider 默认使用阿里云 Qwen 系列。
- 麦克风输入默认采用 always-listening。
- 摄像头默认常开。
- 摄像头背景模式约每 5 秒捕获一次，用于分析 AmbientState。
- 摄像头任务模式约每秒捕获 1 帧，用于摄像头相关任务，例如“你看看我带没带伞”。
- Provider key、模型名和设备设置通过环境变量配置。
- UI 或 CLI 直接用文字显示 Ella 正在听、正在看或正在使用模型上下文。
- 默认测试仍然使用 mock provider，真实 provider 只在本地 opt-in 运行中启用。

这些决策不改变 MVP Runtime 的核心边界：设备和模型通过 source、tool 与 provider 接入，PresenceRuntime 不直接访问设备，TaskRuntime 仍然管理任务生命周期。

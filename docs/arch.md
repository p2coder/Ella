> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella Runtime 2.0 架构设计：真实模型、摄像头与麦克风接入

## 1. 架构目标

Ella Runtime 2.0 在现有 MVP Runtime 之上增加真实感知和真实模型能力。它不重写 `EventRuntime`、`TaskRuntime`、`TaskSession`、`SubAgent`、`ToolManager` 或 `MemoryManager` 的职责，而是在这些边界外增加清晰的设备、模型和 provider 层。

核心目标：

- 默认接入阿里云 Qwen 系列模型。
- 架构默认支持接入电脑麦克风，并采用 always-listening。
- 架构默认支持接入电脑摄像头，并保持常开。
- 默认运行和默认测试使用 mock providers，不访问真实设备或真实网络。
- 摄像头背景模式约每 5 秒采样一次，用于 AmbientState。
- 摄像头任务模式约每秒 1 帧，用于任务内视觉理解。
- 所有真实模型和设备都必须通过 provider / source / tool 边界进入 Runtime。
- 默认测试继续使用 mock provider，不依赖真实设备、真实网络或 API key。

## 2. 总体架构

```text
Environment Config
  ↓
ProviderFactory
  ├─ QwenLLMProvider
  ├─ QwenSpeechProvider
  ├─ QwenVisionProvider / QwenMultimodalProvider

DeviceFactory
  ├─ DefaultMicrophoneProvider
  └─ DefaultCameraProvider

DefaultMicrophoneSource
  ↓
RawSignal(source="microphone", payload={"type": "audio", ...})
  ↓
SpeechProvider
  ↓
RawSignal(source="speech_transcript", payload={"type": "text", "text": ...})
  ↓
EventRuntime.publish(raw_signal)
  ↓
EventTriggerPipeline
  ↓
USER_UTTERANCE Event
  ↓
TaskRuntime.submit()

DefaultCameraSource
  ├─ background mode: ~5s/frame → scene summary RawSignal → EventRuntime.publish() → EventTriggerPipeline → Router → AMBIENT_STATE
  └─ task mode: bounded ~1fps → CameraSceneTool → ToolResult → TaskSession.tool_trace

TaskRuntime
  ↓
SubAgent
  ↓
CapabilityExecutor
  ↓
CameraSceneTool / LLM-backed tools
  ↓
TaskCompletionPackage
  ↓
MemoryManager
```

关键原则：

- `PresenceRuntime` 不直接访问摄像头、麦克风或模型。
- `TaskRuntime` 不直接访问摄像头、麦克风或模型。
- `SubAgent` 只决定下一步需要什么，不直接调用设备或模型。
- `CapabilityExecutor` 只执行一个 `ExecutionDecision`。
- 真正的设备和模型调用发生在 source、provider 或 tool 内。
- `EventRuntime.publish()` 的统一入口仍然是 `RawSignal`。
- Source 不直接修改 AmbientState，不直接创建 TaskSession。
- 第一版不新增 `RawSignal` 子类；文本、音频和图像摘要都用现有 `RawSignal`，通过 `source`、`payload` 和 `payload["type"]` 表达。

## 3. 新增模块边界

建议新增以下顶层模块。每个模块应通过独立 PR 渐进落地。

```text
providers/
  __init__.py
  base.py                 # Provider 数据契约和错误对象
  llm.py                  # LLMProvider 接口
  speech.py               # SpeechProvider 接口
  vision.py               # VisionProvider / MultimodalProvider 接口
  qwen.py                 # 阿里云 Qwen provider 实现
  mock.py                 # Mock providers
  factory.py              # 根据环境变量创建 mock 或 real providers

devices/
  __init__.py
  microphone.py           # DefaultMicrophoneProvider
  camera.py               # DefaultCameraProvider
  factory.py              # 根据环境变量创建 mock 或 real devices

config/
  __init__.py
  settings.py             # 从环境变量读取 provider key、模型名、设备设置

tools/
  camera_scene.py         # CameraSceneTool
  model_tools.py          # 可选 LLM / multimodal task tools

events/
  microphone_source.py    # MicrophoneSource → RawSignal(payload.type=audio/text)
  camera_source.py        # CameraSource → RawSignal(payload.type=image_summary)
```

如果当前阶段希望更小，可以先只创建 `providers/` 和 mock provider；真实设备 source 和 tools 分后续 PR。

新建顶层 package 时可以创建空的 `__init__.py`，但不要在 `__init__.py` 中做统一导出、运行时初始化、provider 创建或设备访问。

## 4. 配置设计

PRD 2.0 使用环境变量，不引入配置文件。

建议环境变量：

```text
ELLA_MODEL_PROVIDER=qwen
ELLA_QWEN_API_KEY=...
ELLA_QWEN_LLM_MODEL=...
ELLA_QWEN_MULTIMODAL_MODEL=...
ELLA_QWEN_SPEECH_MODEL=...

ELLA_MIC_ENABLED=true
ELLA_MIC_DEVICE=default
ELLA_MIC_ALWAYS_LISTENING=true

ELLA_CAMERA_ENABLED=true
ELLA_CAMERA_DEVICE=default
ELLA_CAMERA_BACKGROUND_INTERVAL_SECONDS=5
ELLA_CAMERA_TASK_FPS=1

ELLA_USE_REAL_PROVIDERS=false
ELLA_DEBUG_STORE_RAW_MEDIA=false
```

默认行为：

- 测试环境默认 `ELLA_USE_REAL_PROVIDERS=false`。
- `ELLA_USE_REAL_PROVIDERS=false` 时不得访问真实网络、真实麦克风或真实摄像头。
- 只有 `ELLA_USE_REAL_PROVIDERS=true` 且 `ELLA_MIC_ENABLED=true` 时才允许访问真实麦克风。
- 只有 `ELLA_USE_REAL_PROVIDERS=true` 且 `ELLA_CAMERA_ENABLED=true` 时才允许访问真实摄像头。
- 没有 API key 时使用 mock provider 或返回明确的 provider unavailable。
- 默认不保存原始音频和摄像头帧。
- 只有显式设置 `ELLA_DEBUG_STORE_RAW_MEDIA=true` 时才允许保留原始媒体样本。

## 5. Provider 契约

### 5.0 ProviderFactory

ProviderFactory 是应用组装边界，负责根据 `config/settings.py` 读取到的环境变量创建 provider。

职责：

- 当 `ELLA_USE_REAL_PROVIDERS=false` 时创建 mock providers。
- 当 `ELLA_USE_REAL_PROVIDERS=true` 且配置完整时创建 Qwen LLM / Speech / Vision / Multimodal providers。
- 当缺少 API key 或模型配置时返回 provider unavailable 或 fallback mock，不让应用启动崩溃。
- 统一组装 LLM、speech、vision、multimodal providers。

非职责：

- 不创建 TaskSession。
- 不调用 EventRuntime。
- 不执行 Tool。
- 不写 Memory。

`agent/`、`runtime/` 和 `sessions/` 不应直接 import `providers.qwen`。它们只依赖 provider interface，真实 provider 由 ProviderFactory 或应用组装层注入。

### 5.0.1 DeviceFactory

DeviceFactory 是设备组装边界，负责根据 `config/settings.py` 读取到的环境变量创建麦克风和摄像头 provider。

职责：

- 当 `ELLA_USE_REAL_PROVIDERS=false` 时创建 mock microphone / camera providers。
- 只有 `ELLA_USE_REAL_PROVIDERS=true` 且 `ELLA_MIC_ENABLED=true` 时创建真实麦克风 provider。
- 只有 `ELLA_USE_REAL_PROVIDERS=true` 且 `ELLA_CAMERA_ENABLED=true` 时创建真实摄像头 provider。
- 设备不可用时返回明确 unavailable 状态，不让应用启动崩溃。

非职责：

- 不调用 SpeechProvider、VisionProvider 或 MultimodalProvider。
- 不发布事件。
- 不创建 TaskSession。

### 5.1 LLMProvider

职责：

- 接收结构化 prompt 输入。
- 返回结构化文本结果。
- 支持 task formulation、response generation、process summary、memory summary。
- 失败时返回结构化错误，不抛出破坏 Runtime 状态的裸异常。

非职责：

- 不创建 TaskSession。
- 不选择 Skill。
- 不调用 Tool。
- 不写 Memory。

建议结果对象：

```text
ModelResult
  provider_name
  model_name
  trace_id
  output
  metadata
  error
```

### 5.2 SpeechProvider

职责：

- 将麦克风音频片段转写为文本。
- 返回置信度、语言、时间范围和 provider metadata。
- 生成可进入 Event Trigger Pipeline 的文本信号。

非职责：

- 不直接创建 HandoffRequest。
- 不直接触发 TaskRuntime。
- 不保存原始音频。

### 5.3 VisionProvider / MultimodalProvider

职责：

- 对摄像头帧生成场景摘要。
- 在任务需要时结合文本指令和图像生成结构化观察。
- 输出必须可追踪到 `trace_id`、`task_id`、`session_id`。

非职责：

- 不决定是否创建新任务。
- 不直接路由事件。
- 不直接生成最终用户回复。

## 6. 麦克风架构

麦克风默认 always-listening，但采集层和 Runtime 仍然解耦。

```text
DefaultMicrophoneProvider
  ↓
DefaultMicrophoneSource
  ↓
RawSignal(source="microphone", payload={"type": "audio", ...})
  ↓
SpeechProvider.transcribe()
  ↓
RawSignal(source="speech_transcript", payload={"type": "text", "text": ...})
  ↓
EventRuntime.publish(raw_signal)
  ↓
EventTriggerPipeline
  ↓
USER_UTTERANCE Event
```

设计要求：

- CLI 或 UI 必须显示“正在听”。
- 麦克风不可用时，系统回退到 CLI 输入。
- 转写失败时返回明确错误，不创建脏任务。
- 默认不保存原始音频。
- 默认测试使用 mock microphone provider。

第一版可以采用同步录音窗口或简单音频 chunk，不要求实现复杂 VAD、唤醒词或流式 ASR。

## 7. 摄像头架构

摄像头默认常开，但分为背景模式和任务模式。

### 7.1 背景模式

```text
DefaultCameraProvider
  ↓ every ~5s
FrameSample
  ↓
VisionProvider.summarize_frame()
  ↓
RawSignal(source="camera", payload={"type": "image_summary", "summary": ...})
  ↓
EventRuntime.publish(raw_signal)
  ↓
EventTriggerPipeline
  ↓
Observation / EventCandidate
  ↓
SessionAwareEventRouter
  ↓
AMBIENT_STATE
  ↓
AmbientState.update()
```

背景模式只维护 Ella 对环境的轻量理解。它不应自动打扰用户，也不应自动创建 TaskSession。

### 7.2 任务模式

```text
SubAgent decides CALL_TOOL(camera_scene)
  ↓
CapabilityExecutor
  ↓
CameraSceneTool
  ↓
DefaultCameraProvider.capture(rate=~1fps, max_frames=3)
  ↓
MultimodalProvider.summarize_frames()
  ↓
ToolResult
  ↓
TaskSession.tool_trace
```

任务模式只在当前 TaskSession 需要视觉上下文时启用。每次 CameraSceneTool 调用必须是 bounded call，必须包含 `max_frames` 或 `max_duration_seconds`，默认建议 `max_frames=3` 或 `max_duration_seconds=3`。结果必须归属于当前任务，不能污染全局状态。

## 8. 多模态 going-out 流程

目标场景：

```text
用户说：“Ella，我要出门了，你看看我带没带伞”
```

推荐流程：

```text
MicrophoneSource
→ SpeechProvider
→ RawSignal(source="speech_transcript", payload={"type": "text", "text": ...})
→ EventRuntime.publish()
→ EventTriggerPipeline
→ USER_UTTERANCE
→ MainAgent.create_handoff()
→ TaskRuntime.submit()
→ TaskRuntime.step()
→ SubAgent.select_strategy()
→ SubAgent.decide_next_action()
→ CALL_TOOL(camera_scene)
→ CameraSceneTool captures bounded ~1fps frames
→ MultimodalProvider summarizes umbrella / visible items
→ ToolResult appended
→ SubAgent decides next action
→ COMPLETE
→ UserVisibleAgentOutput
→ TaskCompletionPackage
→ MemoryManager
```

SubAgent 仍然是决定“需要看画面”的位置。事件解析不能直接把输入硬编码成 `going_out` workflow。

## 9. UI / CLI 状态提示

PRD 2.0 第一版只要求文字提示：

```text
Ella status:
- 正在听
- 正在看
- 正在使用 Qwen LLM
- 正在使用 Qwen 多模态模型
- 摄像头不可用，已跳过视觉上下文
- 麦克风不可用，请使用文本输入
```

这些提示属于用户可见运行状态，不是隐藏推理链。

## 10. 错误边界

错误必须在 provider、source、tool 和 runtime 边界被结构化处理。

| 错误 | 处理方式 |
| --- | --- |
| 缺少 Qwen API key | provider unavailable，默认测试仍用 mock provider |
| LLM 调用失败 | 返回 ModelResult.error，TaskSession 状态不损坏 |
| 麦克风不可用 | 回退 CLI 输入 |
| 转写失败 | 不创建任务，返回明确未提交结果 |
| 摄像头不可用 | task 可继续，ToolResult 标记视觉上下文不可用 |
| 多模态失败 | SubAgent 可 replan 或生成缺失上下文输出 |
| 原始媒体保存未开启 | 丢弃原始音频 / 图片，只保留摘要 |

## 11. 测试架构

默认测试必须只使用 mock provider。

必需测试层：

- `tests/providers/`：Provider 契约和 mock provider。
- `tests/events/`：麦克风转写事件、摄像头背景 observation。
- `tests/tools/`：CameraSceneTool 和 model-backed tool。
- `tests/runtime/`：provider 失败不破坏 TaskSession。
- `tests/contracts/`：真实感知接入后 Runtime 边界仍然成立。
- `tests/demo/`：mock provider 下的多模态 going-out demo。

真实设备和真实网络测试必须 opt-in，例如：

```bash
ELLA_USE_REAL_PROVIDERS=true python -m pytest tests/integration_real
```

默认命令仍然必须通过：

```bash
python -m pytest
python main.py
```

## 12. 渐进 PR 顺序

每个 PR 只做一个模块边界。

### PR 1：Provider 数据契约

允许文件：

```text
providers/__init__.py
providers/base.py
providers/llm.py
providers/speech.py
providers/vision.py
tests/providers/test_provider_contracts.py
```

目标：只定义 provider 接口、结果对象和错误对象，不接真实服务。`providers/__init__.py` 必须为空，不做统一导出、初始化或 provider 创建。

### PR 2：Mock Providers

允许文件：

```text
providers/mock.py
tests/providers/test_mock_providers.py
```

目标：为 LLM、speech、vision、multimodal 提供确定性 mock 实现。

### PR 3：环境变量配置

允许文件：

```text
config/__init__.py
config/settings.py
tests/config/test_settings.py
```

目标：从环境变量读取 provider、模型、设备和采样设置。`config/__init__.py` 必须为空，不读取环境变量。

### PR 4：ProviderFactory mock/unavailable 边界

允许文件：

```text
providers/factory.py
tests/providers/test_provider_factory.py
```

目标：根据 `config/settings.py` 创建 LLM / Speech / Vision / Multimodal providers。此时 `providers/qwen.py` 还不存在，所以 PR4 只允许返回 mock providers 或 provider unavailable。默认 `ELLA_USE_REAL_PROVIDERS=false` 时返回 mock providers；`ELLA_USE_REAL_PROVIDERS=true` 但 Qwen provider 尚未接入或缺少 API key 时不得崩溃。

### PR 5：Device provider contracts and DeviceFactory

允许文件：

```text
devices/__init__.py
devices/microphone.py
devices/camera.py
devices/factory.py
tests/devices/test_device_factory.py
```

目标：定义 Microphone / Camera provider 契约、mock / unavailable device provider，以及 DeviceFactory。默认 `ELLA_USE_REAL_PROVIDERS=false` 时返回 mock device providers；只有 `ELLA_USE_REAL_PROVIDERS=true` 且 `ELLA_MIC_ENABLED=true` / `ELLA_CAMERA_ENABLED=true` 时，才允许真实设备 provider 尝试访问真实设备。`devices/__init__.py` 必须为空，不打开设备。

### PR 6：Qwen Provider and Factory Wiring

允许文件：

```text
providers/qwen.py
providers/factory.py
tests/providers/test_qwen_provider.py
tests/providers/test_provider_factory_qwen.py
```

目标：接入阿里云 Qwen provider，并把 Qwen 分支接入 ProviderFactory。默认测试不得真实联网，真实调用放 opt-in 测试。`agent/`、`runtime/` 和 `sessions/` 仍然不得直接 import Qwen provider。

### PR 7：麦克风 Source

允许文件：

```text
events/microphone_source.py
tests/events/test_microphone_source.py
```

目标：将 always-listening 麦克风输入转成现有 `RawSignal(source="speech_transcript", payload={"type": "text", "text": ...})`，再通过 `EventRuntime.publish(raw_signal)` 进入事件管线。第一版可以直接使用 mock microphone + mock speech provider 生成 `speech_transcript` RawSignal，不要求保留 `RawSignal(source="microphone", payload={"type": "audio", ...})` 中间对象。不得新增 `RawSignal` 子类。设备 provider 已在 PR5 提供，本 PR 不修改 `devices/`。

### PR 8：摄像头背景 Source

允许文件：

```text
events/camera_source.py
tests/events/test_camera_source.py
```

目标：实现约 5 秒背景采样，通过 VisionProvider 生成轻量 scene summary，并放入现有 `RawSignal(source="camera", payload={"type": "image_summary", "summary": ...})`。通过 EventRuntime 和 Router 更新 AmbientState，不触发新任务。EventRuntime / EventTriggerPipeline 不直接调用真实 provider。设备 provider 已在 PR5 提供，本 PR 不修改 `devices/`。

### PR 9：CameraSceneTool

允许文件：

```text
tools/camera_scene.py
tests/tools/test_camera_scene_tool.py
```

目标：任务态约 1fps 捕获有限画面，并通过 multimodal provider 返回 ToolResult。每次调用必须有 `max_frames` 或 `max_duration_seconds`。

注册规则：本 PR 只定义 `CameraSceneTool`，测试里可以局部注册到测试用 `ToolManager`。不要在 `ToolManager` 默认构造里自动注册，也不要修改 demo assembly。

### PR 10：LLM 接入任务表达边界

允许文件：

```text
agent/formulation.py
tests/agent/test_llm_task_formulation.py
```

目标：只让 formulation 层可接收 `LLMProvider` 接口并使用 provider 生成结构化任务目标或摘要。`agent/formulation.py` 不得直接 import Qwen provider。本 PR 不把 provider 注入 MainAgent、EventRuntime 或 demo。

### PR 11：LLM Provider 应用组装注入

允许文件：

```text
agent/main_agent.py
runtime/event_runtime.py
demo/cli_demo.py
tests/runtime/test_event_runtime_llm_provider.py
tests/demo/test_cli_demo_llm_provider.py
```

目标：把 ProviderFactory 创建的 `LLMProvider` 传入 MainAgent / EventRuntime / demo assembly，使 PR 10 的 formulation provider 能真正被应用使用。不得在 agent/runtime 内直接 import Qwen provider。

### PR 12：going_out 视觉策略决策

允许文件：

```text
skill/skills/going_out/SKILL.md
sessions/subagent.py
tests/sessions/test_subagent_multimodal_decision.py
```

目标：只让 going_out 相关任务在需要视觉上下文时可以生成 `CALL_TOOL(camera_scene)`。如果仅修改 skill metadata 足够，则不修改 `sessions/subagent.py`；如果当前 deterministic SubAgent 规则需要代码支持，才允许改 `sessions/subagent.py`。本 PR 不注册 tool、不执行 tool、不修改 demo。

### PR 13：多模态 going-out demo

允许文件：

```text
demo/cli_demo.py
tests/demo/test_multimodal_demo.py
```

目标：在 mock provider 下展示语音 + 视觉摘要 + TaskRuntime 的完整用户体验。`CameraSceneTool` 的 demo 注册发生在本 PR 的 `demo/cli_demo.py` 应用组装层；不得通过修改 `ToolManager` 默认构造来隐式注册。

前置依赖：PR11 和 PR12 必须已经合并。如果 `LLMProvider` 还不能被 demo / EventRuntime 注入，或 going_out 还不能生成 `CALL_TOOL(camera_scene)`，不要实现 PR13，应停止并说明缺少依赖，避免在 demo 中硬编码绕过 Runtime。

## 13. 暂不实现

PRD 2.0 架构暂不实现：

- 复杂 VAD。
- 唤醒词。
- 视频流理解。
- 长期保存原始媒体。
- 用户权限 UI。
- 多 Agent 并发调度。
- 外部智能家居、日历、邮件或定位服务。
- 向量记忆。

这些能力应在真实模型和真实感知的基础边界稳定后再拆成独立 PR。

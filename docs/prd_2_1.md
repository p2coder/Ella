# Ella Runtime PRD 2.1：真实感知与低频环境理解

> **⚠️ 已过期文档（核对日期：2026-08-27）**
> 本文档的低频环境理解主线（AmbientSensorRuntime、本地场景变化检测、声音活动检测、AmbientState 时间序列、疲劳/久坐提醒）整体未实现，是当前唯一完全未落地的大块。
> 真实 LLM/麦克风/摄像头接入（主线 A）已落地，并已额外接入 DeepSeek provider 与 screen_scene 工具（文档未覆盖）。
> 当前架构与设计请参阅 [`docs/design_overview.md`](design_overview.md)。

## 1. 产品概要

Ella Runtime 2.1 在现有 EventRuntime、TaskRuntime 和 Provider/Device 边界上，完成真实 LLM、真实麦克风和真实摄像头接入，并增加低功耗、非打扰式的持续环境理解能力。

PRD 2.1 不把 `going_out` 视为系统主流程。`going_out` 只是任务按需调用视觉能力的一个示例。Ella 的通用感知由两条独立通道组成：

1. 背景感知通道：低频维护 AmbientState，不直接创建任务。
2. 任务感知通道：TaskSession 明确需要时，有界调用摄像头、麦克风或模型。

PRD 2.1 是产品方向文档，不对应一个代码 PR。实现必须分阶段、分模块提交，不得在一个 PR 中同时修改 Provider、Device、Runtime、Policy 和 Demo。

交付优先级为：

1. 先跑通文字输入、真实摄像头和 Qwen-VL 的任务感知闭环。
2. 再增加手动触发、有界录音的真实麦克风入口。
3. 最后实现低频环境理解、AmbientState 时间序列和主动提醒。

## 2. 核心产品判断

环境“没有明显变化”本身也是有价值的信息。

连续多次相似的画面可以表示用户长时间停留在同一地点或保持相同活动状态。结合时间、声音活动和已有环境摘要，这些信息可以支持久坐、疲劳、深夜工作等温和提醒。

因此，背景采样不能简单地将无变化画面丢弃。系统应区分：

- 视觉语义没有变化：不重复调用昂贵模型，但更新稳定持续时间。
- 视觉场景明显变化：重新生成场景摘要并更新 AmbientState。
- 声音保持安静：更新安静持续时间，不调用 ASR。
- 检测到语音或明显声音：按需唤醒转写或额外视觉采样。

稳定状态只能作为弱背景证据，不得被解释为医学诊断，也不能仅凭一张画面认定用户疲劳。

## 3. 产品目标

1. 首先接通可配置的真实 LLM 和多模态模型。
2. 首先接通电脑默认摄像头，完成真实任务视觉闭环。
3. 默认使用 mock providers，默认不访问网络或真实设备。
4. 第二阶段接通电脑默认麦克风和真实语音识别。
5. 第三阶段建立低频、低成本的背景感知循环。
6. 第三阶段将场景变化和场景持续稳定都记录为 AmbientState。
7. 让任务可以按需调用有界的视觉或音频能力。
8. 保持 EventRuntime 和 TaskRuntime 的现有职责边界。
9. 为疲劳、久坐和环境变化提醒提供可靠的背景事实。
10. 摄像头和麦克风设备层至少支持 macOS 与 Windows，并保持相同的上层 Provider 接口。

## 4. 非目标

PRD 2.1 不实现：

- 医疗级疲劳识别或健康诊断。
- 人脸身份识别、情绪识别或持续录像。
- 原始音视频长期保存。
- 云端视频流传输。
- 多摄像头融合。
- 多用户识别。
- 并发任务调度重构。
- 基于单次背景采样直接创建 TaskSession。
- 未经策略判断的主动打扰。
- 将 PRD 2.1 的所有能力一次性实现或合并为一个大型 PR。
- 第一阶段就实现 always-listening、后台摄像头调度或疲劳提醒。
- 在 Runtime、Source、Tool、Agent 或 Demo 中散布 macOS / Windows 条件分支。

## 5. 交付策略

### 5.1 主线 A：真实任务感知闭环

第一条交付主线只解决真实任务中的视觉能力：

```text
文字输入
  → EventRuntime
  → TaskRuntime
  → SubAgent
  → CALL_TOOL(camera_scene)
  → 真实 CameraProvider
  → Qwen Multimodal Provider
  → ToolResult
  → TaskCompletionPackage
```

第一阶段不依赖麦克风、VAD、摄像头后台调度、AmbientState 时间序列或疲劳提醒。默认运行仍使用 mock provider，真实模式必须显式开启。

推荐的首个真实演示输入为：

```text
Ella，我要出门了，你看看桌上有没有伞。
```

`going_out` 在这里仅作为验证任务感知闭环的场景，不代表通用 Runtime 数据流。

### 5.2 主线 B：低频环境理解

真实任务视觉闭环稳定后，再实现：

- 手动触发的真实麦克风输入。
- 本地声音活动检测。
- 本地场景变化检测。
- AmbientState 时间序列。
- 摄像头五分钟懒采样。
- 疲劳和久坐提醒候选。
- InterruptionPolicy 主动提醒规则。

主线 B 的能力不得成为主线 A 的前置条件。

## 6. 通用感知模型

### 6.1 背景感知通道

背景感知只维护 Ella 对当前环境的轻量理解：

```text
AmbientSensorRuntime
  ├─ Microphone activity detector
  └─ Camera lazy sampler
           ↓
Local change/activity detection
           ↓
Ambient Observation
           ↓
EventRuntime.publish(RawSignal)
           ↓
Event Router → AMBIENT_STATE
           ↓
AmbientState timeline
```

背景 Source 不得直接修改 AmbientState，不得直接创建 HandoffRequest，也不得直接创建 TaskSession。

### 6.2 任务感知通道

任务感知由 SubAgent 根据当前任务目标决定：

```text
TaskRuntime
  → SubAgent.decide_next_action()
  → CALL_TOOL(camera_scene / audio_context / other tool)
  → CapabilityExecutor
  → bounded device capture
  → Provider inference
  → ToolResult
  → current TaskSession
```

每次设备调用必须有帧数或时间上限。任务工具结果必须携带 `task_id`、`session_id` 和 `trace_id`。

### 6.3 主动提醒通道

背景事实本身不等于提醒。提醒必须经过独立判断：

```text
AmbientState timeline
  → Derived ambient condition
  → EventCandidate
  → Event Router / Presence Queue
  → InterruptionPolicy
  → allowed reminder or suppressed event
```

例如“工作场景稳定超过较长时间”只能生成疲劳提醒候选。InterruptionPolicy 仍需考虑冷却时间、当前 TaskSession、用户偏好、时间段和近期是否已经提醒。

## 7. 摄像头懒状态

### 7.1 默认采样策略

- 安静状态下，摄像头默认每 5 分钟采样一帧。
- 采样间隔必须可以在 `config/config.py` 中配置。
- 检测到明显声音或语音活动时，可以提前触发一次背景采样。
- 任务模式不受 5 分钟间隔限制，但每次调用必须有明确上限。

### 7.2 场景变化判断

每次背景采样先进行本地、低成本变化比较，不应默认调用视觉模型。

比较结果分为：

- `STABLE`：与基准场景相似。
- `CHANGED`：超过变化阈值。
- `UNKNOWN`：没有基准帧、画面质量不足或比较失败。

第一版可以使用图像缩放后的感知哈希、直方图或结构相似度。变化检测必须可替换，不与具体视觉模型绑定。

### 7.3 稳定场景的处理

当结果为 `STABLE`：

- 不重复调用 VisionProvider。
- 更新 `last_observed_at`。
- 保留 `stable_since`。
- 增加或重新计算 `stable_duration_seconds`。
- 更新 `consecutive_stable_observations`。
- 记录最近声音活动时间和安静持续时间。
- 原始帧在完成比较后释放，除非显式开启调试存储。

稳定场景是时间序列事实，而不是空结果。

### 7.4 场景变化的处理

当结果为 `CHANGED` 或需要建立新基准：

- 调用 VisionProvider 生成轻量场景摘要。
- 更新场景摘要和可见对象类别。
- 重置 `stable_since`。
- 记录 `last_changed_at`。
- 更新用于下一次比较的内存基准。
- 通过 RawSignal 和 EventRuntime 更新 AmbientState。

## 8. 麦克风低功耗监听

### 8.1 活动检测

麦克风默认只执行本地声音活动检测或 VAD，不持续调用 SpeechProvider。

- 无声音时更新 `quiet_since` 和 `quiet_duration_seconds`。
- 非语音声音只更新环境活动状态。
- 检测到疑似语音时才截取有界音频片段并调用 SpeechProvider。
- 转写成功后生成现有 `RawSignal(source="speech_transcript")`。
- 转写文本继续通过 EventRuntime 进入任务生命周期。

### 8.2 与摄像头协同

声音活动可以作为摄像头提前采样的提示，但不是强制任务触发器：

```text
No sound
  → camera remains lazy
  → five-minute heartbeat sample

Sound activity
  → update ambient activity
  → optionally request one camera background sample

User speech
  → bounded ASR
  → RawSignal
  → EventRuntime
```

麦克风静默和视觉稳定可以共同提高“环境长期无明显活动”的置信度，但不能单独证明用户疲劳或仍在摄像头前。

## 9. AmbientState 时间序列

PRD 2.1 要求 AmbientState 从“仅保存最新事件”演进为能够表达当前状态及其持续时间的轻量时间序列边界。

至少需要表达：

- 当前场景摘要。
- 当前场景指纹或比较基准引用。
- `first_observed_at`。
- `last_observed_at`。
- `last_changed_at`。
- `stable_since`。
- `stable_duration_seconds`。
- `consecutive_stable_observations`。
- `last_sound_activity_at`。
- `quiet_since`。
- `quiet_duration_seconds`。
- 观察置信度和数据新鲜度。

AmbientState 默认只保存摘要、时间和比较特征，不保存原始图像或音频。

## 10. 疲劳与久坐提醒

第一版只提供保守的候选判断，不做健康诊断。

候选条件可以组合：

- 工作或桌面场景持续稳定。
- 稳定持续时间超过可配置阈值。
- 长时间没有明显移动或声音活动。
- 当前时间处于深夜或用户设定的工作时段。
- 最近没有发送相同提醒。

系统必须支持：

- 提醒阈值配置。
- 提醒冷却时间。
- 用户关闭此类提醒。
- 当前有高优先级任务时延迟提醒。
- 证据不足时不提醒。

提醒文案应表达不确定性，例如“你似乎已经保持这个工作状态一段时间了，要不要休息一下？”，不得声称“检测到你已经疲劳”。

## 11. 真实 Provider 与设备

### 11.1 配置入口

普通运行配置保存在 `config/config.py`，由 `config/settings.py` 解析和校验。

API Key 可以通过厂商环境变量提供。Qwen 至少支持：

- `ELLA_QWEN_API_KEY`
- `DASHSCOPE_API_KEY`
- `QWEN_API_KEY`

密钥不得写入日志、ToolResult、Memory 或提交到 Git。

### 11.2 真实模型

ProviderFactory 应能够创建：

- 真实 LLMProvider。
- 真实 SpeechProvider。
- 真实 VisionProvider。
- 真实 MultimodalProvider。

agent、runtime 和 sessions 只能依赖 Provider 接口，不得直接 import 具体厂商实现。

### 11.3 真实设备

DeviceFactory 应能够创建：

- 默认电脑麦克风 Provider。
- 默认电脑摄像头 Provider。

设备必须支持显式打开、超时、关闭和结构化错误。应用退出、异常或任务结束后不得遗留设备占用。

### 11.4 跨平台设备策略

真实摄像头和麦克风必须采用“统一 Provider 接口、可替换采集后端”的设计，目标平台至少包括：

- macOS。
- Windows。

Linux 可以作为兼容目标，但不作为第一阶段现场演示的阻塞条件。

实现时必须遵守以下优先级：

1. 优先选择维护活跃、同时支持 macOS 和 Windows 的跨平台采集库。
2. 摄像头优先评估 OpenCV 等跨平台单帧采集后端。
3. 麦克风优先评估 `sounddevice` 等跨平台录音后端。
4. 只有经过验证，跨平台后端无法满足设备枚举、权限、稳定性或延迟要求时，才允许增加平台专用 backend。
5. 平台专用 backend 必须隐藏在 `CameraProvider` / `MicrophoneProvider` 后面，不得改变 Source、Tool 或 Runtime 调用方式。

允许的设备层结构为：

```text
DeviceFactory
  → CameraProvider
      → CrossPlatformCameraBackend
      → MacOSCameraBackend (仅必要时)
      → WindowsCameraBackend (仅必要时)

  → MicrophoneProvider
      → CrossPlatformMicrophoneBackend
      → MacOSMicrophoneBackend (仅必要时)
      → WindowsMicrophoneBackend (仅必要时)
```

禁止出现：

```text
if platform == "macOS" / "Windows"
```

这类判断不得出现在 EventRuntime、TaskRuntime、CameraSceneTool、MicrophoneSource、SubAgent 或 Demo 中。平台选择只能发生在 DeviceFactory 或设备 backend 内部。

设备配置必须使用稳定的逻辑值：

- `"default"` 表示操作系统默认设备。
- 可选设备配置应支持稳定设备标识或用户可读设备名。
- 配置文件不得要求用户填写平台专用 API 名称。
- 找不到配置设备时，应回退默认设备或返回结构化 unavailable 结果，不得静默选择错误设备。

系统权限由操作系统管理。Ella 必须能够识别并区分：

- 用户未授权摄像头或麦克风。
- 配置设备不存在。
- 设备正被其他应用占用。
- 后端或驱动不可用。
- 采集超时。

这些情况必须映射为统一的结构化设备错误，上层不得依赖平台原始错误文本。

## 12. 数据流示例

### 12.1 第一阶段真实任务视觉闭环

```text
Text RawSignal
  → EventRuntime
  → TaskRuntime
  → SubAgent decides CALL_TOOL(camera_scene)
  → real CameraProvider captures bounded frames
  → real Qwen Multimodal Provider
  → ToolResult
  → TaskCompletionPackage
```

这是 PRD 2.1 首先需要完成的真实闭环。

### 12.2 通用背景稳定场景

```text
Five-minute timer
  → CameraProvider.capture_frame()
  → local scene comparison = STABLE
  → RawSignal(type="ambient_stability")
  → EventRuntime
  → AMBIENT_STATE
  → extend stable duration
  → optional fatigue candidate evaluation
```

### 12.3 通用背景变化场景

```text
Camera sample or sound-triggered sample
  → local scene comparison = CHANGED
  → VisionProvider lightweight summary
  → RawSignal(type="image_summary")
  → EventRuntime
  → AMBIENT_STATE
```

### 12.4 用户语音任务

```text
VAD detects speech
  → bounded microphone capture
  → SpeechProvider.transcribe()
  → RawSignal(type="text")
  → EventRuntime
  → TaskRuntime
```

### 12.5 going_out 视觉辅助任务

```text
User says they are leaving and requests visual context
  → EventRuntime
  → TaskRuntime
  → SubAgent decides CALL_TOOL(camera_scene)
  → bounded camera capture
  → MultimodalProvider
  → ToolResult
  → TaskCompletionPackage
```

这只是任务感知示例，不是 Ella 的通用主数据流。

## 13. 隐私与资源要求

- 默认不保存原始图像和音频。
- 默认 mock 模式不访问网络或真实设备。
- 真实设备访问必须在配置中显式开启。
- 摄像头和麦克风处于活动状态时必须有用户可见状态。
- 背景视觉摘要不得写入长期 Memory，除非后续明确通过 MemoryManager 策略批准。
- 场景比较优先本地完成。
- ASR 和视觉模型调用应按需发生，不得因固定轮询持续产生云端请求。
- 设备失败不得导致 Runtime 崩溃。

## 14. 测试要求

默认测试必须完全 mock-only、无网络、无真实设备依赖，并覆盖：

- 配置解析和安全默认值。
- 真实 Provider client 的 mocked 网络行为。
- 摄像头设备打开、单帧捕获、超时和关闭。
- 麦克风有界录音、VAD、超时和关闭。
- 场景稳定时不重复调用 VisionProvider。
- 场景稳定时持续时间仍然更新。
- 场景变化时重新生成摘要。
- 声音活动可以请求提前视觉采样。
- 静默时不调用 SpeechProvider。
- 背景观察不直接创建 TaskSession。
- 疲劳候选必须经过 InterruptionPolicy。
- 任务感知结果只进入对应 TaskSession。
- 原始音视频默认不落盘。
- DeviceFactory 的平台选择只发生在设备层。
- 同一 CameraProvider / MicrophoneProvider 契约可用于 macOS 和 Windows backend。
- 平台原始异常会被转换成统一结构化错误。
- Runtime、Source、Tool 和 Demo 不包含平台条件分支。

真实设备和真实网络测试必须是显式 opt-in，不进入默认测试套件。

跨平台验证分为两层：

1. 默认 CI：使用 fake/mock backend 验证 macOS 与 Windows 选择逻辑、接口一致性和错误映射，不访问真实设备。
2. 发布前手工验收：分别在一台 macOS 和一台 Windows 设备上验证默认摄像头、默认麦克风、权限拒绝、设备不存在和资源释放。

不得仅因开发机器是 macOS，就把 Windows 支持推迟到上层接口已经固化之后。

## 15. 建议实施阶段

每个阶段应继续遵守“一次只修改一个模块边界”。

### 15.1 阶段 1：真实任务感知

阶段 1 的目标是尽快跑通可演示的真实视觉任务闭环。建议拆为三个独立 PR：

1. 真实 Qwen Multimodal Client 与 ProviderFactory wiring。
2. 跨平台 CameraProvider 与 DeviceFactory wiring。
3. Demo assembly 注入真实 CameraProvider 和 MultimodalProvider。

这三个 PR 不得提前实现麦克风、VAD、后台采样、AmbientState 时间序列或疲劳提醒。

### 15.2 阶段 2：真实麦克风入口

阶段 2 先采用用户显式触发的有界录音，不直接实现 always-listening：

1. 跨平台 MicrophoneProvider 与 DeviceFactory wiring。
2. 有界录音和真实 SpeechProvider 转写。
3. 文本输入 / 麦克风输入选择入口。
4. Speech transcript RawSignal 接入 EventRuntime。

完成这一阶段后，再评估 always-listening 的资源、隐私和交互成本。

### 15.3 阶段 3：低频环境理解

阶段 3 依次实现：

1. 本地 VAD / sound activity detector。
2. 本地 scene change detector。
3. AmbientState 时间状态模型。
4. 摄像头五分钟懒采样调度器。
5. 声音活动与摄像头提前采样协调器。
6. 疲劳/久坐派生条件和提醒候选。
7. InterruptionPolicy 主动提醒规则。

### 15.4 PR 切分规则

- 一个 PR 只能实现一个 Provider、Device、Source、Runtime、Policy 或 Demo 边界。
- 不得在设备 PR 中修改 TaskRuntime 或 InterruptionPolicy。
- 不得在 Demo PR 中硬编码工具调用或绕过 Runtime。
- 真实网络与真实设备测试必须 opt-in；默认测试使用 mock 或 mocked client。
- 每个 PR 必须保持 `python -m pytest` 和 `python main.py` 可运行。
- 摄像头和麦克风 PR 必须先实现统一跨平台 backend；若确需平台专用实现，应为 macOS backend 和 Windows backend 分别创建后续单一目标 PR。
- 平台专用 PR 只能修改对应设备 backend、DeviceFactory wiring 和定向测试，不得修改 Runtime、Agent、Tool 或 Demo。

## 16. 验收标准

### 16.1 阶段 1 验收

- 用户可以通过文字输入触发真实摄像头视觉任务。
- CameraSceneTool 通过 Factory 注入的真实 CameraProvider 和 Qwen Multimodal Provider 工作。
- 摄像头采集有明确帧数或时间上限。
- 同一 CameraProvider 接口可以在 macOS 和 Windows 上使用。
- 默认运行仍保持 mock-safe。
- 无 API Key、无摄像头或模型失败时返回结构化错误，不使 Runtime 崩溃。

### 16.2 阶段 2 验收

- 用户可以显式选择有界麦克风录音输入。
- 同一 MicrophoneProvider 接口可以在 macOS 和 Windows 上使用。
- SpeechProvider 转写结果通过 RawSignal 进入 EventRuntime。
- 麦克风失败时可以继续使用文字输入。

### 16.3 跨平台验收

- macOS 和 Windows 使用相同的 `CameraProvider`、`MicrophoneProvider` 和 DeviceFactory 公共接口。
- macOS 和 Windows 都能选择并访问操作系统默认设备。
- 权限拒绝、设备缺失、设备占用和采集超时返回相同结构的错误对象。
- 关闭、异常和任务结束后，两个平台都不会遗留摄像头或麦克风占用。
- EventRuntime、TaskRuntime、Source、Tool、Agent 和 Demo 不包含平台判断。
- 默认测试不要求 CI 主机具有摄像头或麦克风。

### 16.4 阶段 3 验收

- 用户可以通过配置启用真实 Qwen、麦克风和摄像头。
- 安静状态下摄像头约每 5 分钟采样一帧。
- 场景稳定时不重复调用视觉模型，但 AmbientState 的稳定持续时间会增长。
- 场景变化时会更新轻量场景摘要。
- 麦克风静默时不持续调用 ASR。
- 检测到用户语音时可以进入现有 EventRuntime 和 TaskRuntime。
- 背景观察不直接创建 TaskSession。
- 任务可以按需、有界地调用视觉能力。
- 疲劳或久坐提醒必须基于持续背景事实并经过 InterruptionPolicy。
- 默认不保存原始音视频。
- `python -m pytest` 和 `python main.py` 继续可运行。

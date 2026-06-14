# Ella Runtime 2.1 可执行 PR 提示词

本文根据以下文档和当前仓库状态整理：

```text
docs/prd.md
docs/architecture.md
docs/pr_plan.md
docs/prd_2_0.md
docs/prd_2_1.md
docs/arch.md
docs/tune.md
doc/restructure.md
doc/todo.md
```

使用方法：按顺序一次复制一个 PR Prompt 给 ChatGPT 或 Codex。每个 PR 只完成一个模块边界。前置 PR 未完成时必须停止，不得在 Demo 或 Runtime 中硬编码绕过。

默认约束：

- 默认运行和默认测试必须使用 mock，不访问网络、摄像头或麦克风。
- 真实网络和真实设备测试必须显式 opt-in。
- 普通配置来自 `config/config.py`；API Key 可以来自受支持的环境变量。
- macOS 和 Windows 使用相同 Provider 公共接口。
- 平台判断只能位于 DeviceFactory 或设备 backend。
- 每个 PR 都必须运行定向测试、完整测试和 `python main.py`。
- 新增依赖时必须固定合理的最低版本，并解释其跨平台支持。

---

# Phase 0：真实能力接入前的权限边界

该阶段来自 `doc/todo.md`。真实摄像头、麦克风和用户可安装能力接入前，应先移除 Demo 中的进程级硬编码权限。

## PR 0.1：Tool 角色可见性元数据

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 0.1: add role-based visibility metadata for tools.

Before making changes, read:

docs/prd.md
docs/architecture.md
docs/prd_2_1.md
docs/tune.md
doc/todo.md

## Goal

Let each Tool declare which stable agent role codes may discover and use it.

This PR only changes the tool capability boundary. Do not modify sessions, runtime, skills, or demo.

## Allowed files

Only create or modify:

tools/base.py
tools/manager.py
tools/mock_tools.py
tools/camera_scene.py
tests/tools/test_tool_role_visibility.py

Do not modify any other files.

## Implement

- Add immutable allowed role metadata to the Tool contract.
- Existing tools should default to allowing the stable role code `main_agent` so current behavior remains compatible.
- Add ToolManager methods that list or resolve tools visible to one agent_role.
- ToolManager.execute() must reject a tool when the context agent_role is not allowed.
- Preserve live availability checks and existing context.allowed_tools enforcement.
- Registration remains process-level and must not mutate task context.

## Forbidden scope

Do not modify AgentExecutionContext, TaskSessionManager, TaskRuntime, SkillManager, demo, providers, or devices.
Do not add authentication, users, databases, or permission UI.

## Tests

Add tests for visible and hidden roles, execution rejection, default compatibility, and no mutation of context.

Run:

python -m pytest tests/tools/test_tool_role_visibility.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

feat(tools): add role-based tool visibility
```

## PR 0.2：Skill 角色可见性元数据

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 0.2: add role-based visibility metadata for skills.

Before making changes, read docs/prd.md, docs/architecture.md, docs/prd_2_1.md, docs/tune.md, and doc/todo.md.

## Precondition

PR 0.1 must already be merged. Stop if it is not present.

## Goal

Let skill definitions declare which stable agent role codes may discover them.

## Allowed files

Only create or modify:

skill/registry.py
skill/loader.py
skill/manager.py
skill/skills/going_out/SKILL.md
tests/registries/test_skill_role_visibility.py

Do not modify any other files.

## Implement

- Add allowed role metadata to SkillDefinition and SKILL.md parsing.
- SkillManager must list and resolve summaries visible to one agent_role.
- Existing going_out behavior must remain available to main_agent.
- Missing metadata must use a safe, backward-compatible default documented by tests.
- Do not select or execute skills in this PR.

## Forbidden scope

Do not modify SubAgent, sessions, runtime, tools, demo, providers, or devices.

## Tests

Run:

python -m pytest tests/registries/test_skill_role_visibility.py
python -m pytest
python main.py

PR title:

feat(skills): add role-based skill visibility
```

## PR 0.3：任务本地 CapabilityScope 数据契约

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 0.3: add task-local CapabilityScope to AgentExecutionContext.

Before making changes, read docs/prd.md, docs/architecture.md, docs/prd_2_1.md, docs/tune.md, and doc/todo.md.

## Precondition

PR 0.1 and PR 0.2 must already be merged.

## Goal

Define the immutable effective skill/tool permission scope carried by one task context.

## Allowed files

Only create or modify:

agent/context.py
tests/sessions/test_execution_context_capability_scope.py

Do not modify any other files.

## Implement

- Add a frozen CapabilityScope data object in agent/context.py.
- It should contain allowed skill names, allowed tool names, agent role, and optional capability version metadata.
- AgentExecutionContext should carry CapabilityScope.
- Preserve compatibility with existing allowed_tools consumers through a read-only property if needed.
- Context serialization must include the scope.
- The scope is a task-local permission snapshot, not a process registry.

## Forbidden scope

Do not resolve the scope from managers yet. Do not modify TaskSessionManager, TaskRuntime, Executor, ToolManager, SkillManager, or demo.

## Tests

Run:

python -m pytest tests/sessions/test_execution_context_capability_scope.py
python -m pytest
python main.py

PR title:

feat(agent): add task-local capability scope
```

## PR 0.4：TaskSessionManager 能力范围解析

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 0.4: resolve task capability scope during session creation.

Before making changes, read docs/prd.md, docs/architecture.md, docs/prd_2_1.md, docs/tune.md, and doc/todo.md.

## Precondition

PR 0.1 through PR 0.3 must already be merged.

## Goal

Make TaskSessionManager create AgentExecutionContext from currently visible SkillManager and ToolManager capabilities instead of a hard-coded tool tuple.

## Allowed files

Only create or modify:

sessions/session_manager.py
tests/sessions/test_session_capability_resolution.py

Do not modify any other files.

## Implement

- TaskSessionManager may receive SkillManager and ToolManager dependencies.
- At create_session(), resolve capabilities visible to the configured agent_role.
- Store the immutable result in AgentExecutionContext CapabilityScope.
- Newly registered capabilities are visible to newly created sessions.
- Capabilities added later do not automatically enter an existing session scope.
- Do not execute capabilities or modify TaskRuntime.

## Forbidden scope

Do not modify managers, context contract, executor, runtime, demo, providers, or devices.

## Tests

Run:

python -m pytest tests/sessions/test_session_capability_resolution.py
python -m pytest
python main.py

PR title:

refactor(sessions): resolve task capability scope
```

## PR 0.5：移除 Demo 硬编码能力名单

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 0.5: remove hard-coded capability permissions from demo assembly.

Before making changes, read docs/prd.md, docs/architecture.md, docs/prd_2_1.md, docs/tune.md, and doc/todo.md.

## Precondition

PR 0.1 through PR 0.4 must already be merged. Stop if TaskSessionManager cannot resolve capability scope from managers.

## Goal

Make DemoRuntime register capabilities but not manually define task permission name tuples.

## Allowed files

Only create or modify:

demo/cli_demo.py
tests/demo/test_demo_capability_assembly.py

Do not modify any other files.

## Implement

- Demo assembly may register concrete tools and load skills.
- Pass SkillManager and ToolManager to the session creation boundary.
- Remove hard-coded allowed tool names from DemoRuntime.
- Preserve EventRuntime/TaskRuntime public flow and visible output.
- Do not expose managers as fields on DemoRuntime.

## Forbidden scope

Do not modify runtime, sessions, managers, providers, devices, or skill/tool behavior.

## Tests

Run:

python -m pytest tests/demo/test_demo_capability_assembly.py
python -m pytest
python main.py

PR title:

refactor(demo): resolve capabilities through managers
```

---

# Phase 1：真实任务视觉闭环

## PR 1.1：真实 Qwen LLM 与多模态 Client

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 1.1: add real Qwen LLM and multimodal client transport.

Before making changes, read docs/prd_2_1.md, docs/arch.md, docs/tune.md, config/config.py, providers/base.py, providers/qwen.py, and providers/factory.py.

## Goal

Replace the current client-missing Qwen LLM and multimodal behavior with opt-in real network clients while preserving structured ProviderResult errors.

## Allowed files

Only create or modify:

providers/qwen.py
providers/factory.py
pyproject.toml
tests/providers/test_qwen_real_client.py
tests/providers/test_provider_factory_real_qwen.py

Do not modify any other files.

## Implementation requirements

- Before coding, verify the current official Alibaba Cloud DashScope documentation. Use only official documentation as the protocol source.
- Support LLM text generation and multimodal frame/image understanding.
- LLM output must be normalized to a mapping containing at least `text` so TaskFormulator can consume it.
- Multimodal output must be normalized to a mapping containing `scene_summary`, with optional `visible_items` and `umbrella_visible`.
- Multimodal input must accept the bounded `frames` collection used by CameraSceneTool, including encoded image bytes and MIME metadata from a real CameraProvider.
- Factory-created real providers must be usable without injecting a test callable.
- Network calls occur only when USE_REAL_PROVIDERS is true and API key/model config is complete.
- Support ELLA_QWEN_API_KEY, DASHSCOPE_API_KEY, and QWEN_API_KEY through existing settings.
- Convert authentication, timeout, rate-limit, malformed response, and transport failures into ProviderError.
- Never log or serialize the API key.
- Preserve injectable client/transport support for deterministic tests.
- Default tests must mock all network calls.

## Forbidden scope

Do not modify agent, runtime, sessions, tools, devices, demo, SpeechProvider, or camera behavior.
Do not make network calls during tests.

## Tests

Run:

python -m pytest tests/providers/test_qwen_real_client.py
python -m pytest tests/providers/test_provider_factory_real_qwen.py
python -m pytest
python main.py

PR title:

feat(providers): add real qwen inference client
```

## PR 1.2：跨平台 CameraProvider

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 1.2: add a cross-platform real CameraProvider.

Before making changes, read docs/prd_2_1.md, docs/tune.md, devices/camera.py, devices/factory.py, and config/settings.py.

## Precondition

PR 1.1 must already be merged.

## Goal

Capture one bounded frame from the configured default camera through the same public interface on macOS and Windows.

## Allowed files

Only create or modify:

devices/camera.py
devices/factory.py
pyproject.toml
tests/devices/test_real_camera_provider.py
tests/devices/test_camera_factory_wiring.py

Do not modify any other files.

## Implement

- Prefer one maintained cross-platform backend such as OpenCV.
- Keep platform differences inside the device layer.
- Support camera_device="default" and an explicit index/name where the backend permits it.
- Capture must be bounded and release the camera on success and failure.
- A successful DeviceResult should expose an encoded frame payload with explicit type and MIME metadata, suitable for the existing CameraSceneTool and QwenMultimodalProvider without platform-specific handling.
- Map permission denied, missing device, busy device, backend failure, and timeout into DeviceError codes.
- DeviceFactory returns the real provider only when USE_REAL_PROVIDERS and CAMERA_ENABLED are true.
- Importing the module must not open the camera.
- Tests must inject/fake the backend and never access a real device.

## Forbidden scope

Do not modify CameraSceneTool, EventRuntime, TaskRuntime, Source, Agent, Demo, or platform-specific upper layers.

## Tests

Run:

python -m pytest tests/devices/test_real_camera_provider.py
python -m pytest tests/devices/test_camera_factory_wiring.py
python -m pytest
python main.py

PR title:

feat(devices): add cross-platform camera provider
```

## PR 1.3：真实视觉 Demo 组装注入

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 1.3: wire real camera and Qwen multimodal providers into demo assembly.

Before making changes, read docs/prd_2_1.md, docs/tune.md, demo/cli_demo.py, providers/factory.py, devices/factory.py, and tools/camera_scene.py.

## Preconditions

- PR 1.1 real Qwen client is merged.
- PR 1.2 real CameraProvider is merged.
- Demo capability permissions are manager-resolved.

Stop if any precondition is false. Do not hardcode around missing behavior.

## Goal

Make CameraSceneTool receive camera and multimodal providers from factories so the same demo runs mock-safe by default and real when explicitly configured.

## Allowed files

Only create or modify:

demo/cli_demo.py
tests/demo/test_real_multimodal_assembly.py

Do not modify any other files.

## Implement

- Create ProviderFactory and DeviceFactory in app assembly.
- Inject factory camera and multimodal providers into CameraSceneTool.
- Default config must still create mock providers.
- Real config must select real providers without platform checks in demo.
- Preserve EventRuntime → TaskRuntime flow and output sections.
- Demo must not directly call CameraSceneTool or construct completion/memory objects.

## Tests

Run:

python -m pytest tests/demo/test_real_multimodal_assembly.py
python -m pytest
python main.py

PR title:

feat(demo): wire configurable real visual providers
```

---

# Phase 2：有界真实麦克风入口

## PR 2.0：有界录音配置

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 2.0: add bounded microphone capture settings.

Before making changes, read docs/prd_2_1.md, docs/tune.md, config/config.py, and config/settings.py.

## Goal

Define and validate the user-editable settings required by one bounded microphone capture.

## Allowed files

Only create or modify:

config/config.py
config/settings.py
tests/config/test_microphone_capture_settings.py

Do not modify any other files.

## Implement

- Add microphone capture duration, sample rate, and channel count settings.
- Use safe cross-platform defaults suitable for speech transcription.
- Duration must be positive and bounded by a documented maximum.
- Sample rate and channel count must be positive integers.
- Ordinary settings come only from config/config.py; do not add environment-variable overrides.
- Do not open devices or create providers while loading settings.

## Forbidden scope

Do not modify device providers, ProviderFactory, SpeechProvider, Source, Runtime, or Demo.

## Tests

Run:

python -m pytest tests/config/test_microphone_capture_settings.py
python -m pytest
python main.py

PR title:

feat(config): add bounded microphone settings
```

## PR 2.1：跨平台 MicrophoneProvider

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 2.1: add a cross-platform bounded MicrophoneProvider.

Before making changes, read docs/prd_2_1.md, docs/tune.md, devices/microphone.py, devices/factory.py, and config/settings.py.

## Precondition

PR 2.0 must already be merged.

## Goal

Record one explicitly requested, bounded audio clip through the same provider interface on macOS and Windows.

## Allowed files

Only create or modify:

devices/microphone.py
devices/factory.py
pyproject.toml
tests/devices/test_real_microphone_provider.py
tests/devices/test_microphone_factory_wiring.py

Do not modify any other files.

## Implement

- Prefer a maintained cross-platform backend such as sounddevice.
- Use the bounded duration/sample-rate/channel settings introduced by PR 2.0.
- Support microphone_device="default".
- Release resources on success and failure.
- Return audio bytes/array plus format metadata through DeviceResult.
- Map permission, missing device, busy device, backend failure, and timeout into stable DeviceError codes.
- DeviceFactory selects the real provider only when real providers and microphone are enabled.
- Importing modules must not open devices.
- Tests use a fake backend only.

## Forbidden scope

Do not implement VAD, always-listening, SpeechProvider, EventRuntime wiring, demo input selection, or platform branches outside devices.

## Tests

Run:

python -m pytest tests/devices/test_real_microphone_provider.py
python -m pytest tests/devices/test_microphone_factory_wiring.py
python -m pytest
python main.py

PR title:

feat(devices): add cross-platform microphone provider
```

## PR 2.2：真实 Qwen SpeechProvider

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 2.2: add real Qwen speech transcription.

Before making changes, read docs/prd_2_1.md, docs/tune.md, providers/qwen.py, providers/factory.py, and providers/speech.py.

## Precondition

PR 2.1 must already provide bounded audio with explicit format metadata.

## Goal

Transcribe one bounded audio clip through Qwen and return the existing ProviderResult contract.

## Allowed files

Only create or modify:

providers/qwen.py
providers/factory.py
tests/providers/test_qwen_speech_client.py
tests/providers/test_provider_factory_real_speech.py

Do not modify any other files.

## Implement

- Verify current official DashScope speech documentation before coding.
- Accept the audio shape produced by MicrophoneProvider.
- Return transcript text and language metadata.
- Convert authentication, format, timeout, rate-limit, and transport failures into ProviderError.
- Preserve injected transport for tests.
- No network in default tests.

## Forbidden scope

Do not modify microphone devices, Source, Runtime, Agent, Demo, VAD, or always-listening behavior.

## Tests

Run:

python -m pytest tests/providers/test_qwen_speech_client.py
python -m pytest tests/providers/test_provider_factory_real_speech.py
python -m pytest
python main.py

PR title:

feat(providers): add real qwen speech transcription
```

## PR 2.3：麦克风 Source 真实依赖注入

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 2.3: inject configured microphone and speech providers into MicrophoneSource.

Before making changes, read docs/prd_2_1.md, docs/tune.md, events/microphone_source.py, devices/factory.py, and providers/factory.py.

## Preconditions

PR 2.1 and PR 2.2 must already be merged.

## Goal

Add an application assembly boundary that creates MicrophoneSource from DeviceFactory and ProviderFactory without changing EventRuntime.

## Allowed files

Only create or modify:

events/microphone_source.py
tests/events/test_microphone_source_factory.py

Do not modify any other files.

## Implement

- Add a factory/classmethod that accepts or creates configured provider factories.
- Preserve direct dependency injection for tests.
- capture_transcript remains one bounded operation.
- Output remains RawSignal(source="speech_transcript", payload type="text").
- No device access during import or source construction.

## Forbidden scope

Do not modify EventRuntime, TaskRuntime, Demo, devices, providers, VAD, or always-listening behavior.

## Tests

Run:

python -m pytest tests/events/test_microphone_source_factory.py
python -m pytest
python main.py

PR title:

feat(events): assemble configured microphone source
```

## PR 2.4：CLI 文本/麦克风输入选择

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 2.4: add explicit text or microphone input selection to the CLI demo.

Before making changes, read docs/prd_2_1.md, docs/tune.md, demo/cli_demo.py, and events/microphone_source.py.

## Preconditions

PR 2.1 through PR 2.3 must already be merged.

## Goal

Allow a user to explicitly choose one text input or one bounded microphone capture before publishing a RawSignal.

## Allowed files

Only create or modify:

demo/cli_demo.py
tests/demo/test_microphone_input_demo.py

Do not modify any other files.

## Implement

- Preserve non-interactive python main.py mock behavior.
- Add a callable demo input mode API for text or microphone.
- Microphone mode obtains one RawSignal from MicrophoneSource and passes it to EventRuntime.publish().
- Show clear listening/transcription status.
- On device/provider failure, return a clear fallback message and preserve text mode.
- Do not implement always-listening or threads.

## Forbidden scope

Do not modify Runtime, Agent, sessions, providers, devices, Source internals, VAD, or background sensing.

## Tests

Run:

python -m pytest tests/demo/test_microphone_input_demo.py
python -m pytest
python main.py

PR title:

feat(demo): add bounded microphone input mode
```

---

# Phase 3：低频环境理解

## PR 3.1：Ambient 配置项

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.1: add low-frequency ambient sensing settings.

Before making changes, read docs/prd_2_1.md, docs/tune.md, config/config.py, and config/settings.py.

## Goal

Define and validate configuration for lazy camera sampling, scene comparison, quiet tracking, and reminder thresholds.

## Allowed files

Only create or modify:

config/config.py
config/settings.py
tests/config/test_ambient_settings.py

Do not modify any other files.

## Implement

Add safe defaults for ambient sensing enabled, camera heartbeat interval (default 300 seconds), scene change threshold, fatigue candidate threshold, reminder cooldown, and optional sound-triggered sample behavior.

Validate positive durations and bounded thresholds. Ordinary settings must come from config.py, not environment variables.

## Forbidden scope

Do not create schedulers, detectors, events, Runtime behavior, devices, reminders, or UI.

## Tests

Run:

python -m pytest tests/config/test_ambient_settings.py
python -m pytest
python main.py

PR title:

feat(config): add ambient sensing settings
```

## PR 3.2：本地场景变化检测器

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.2: add a local scene change detector.

Before making changes, read docs/prd_2_1.md and docs/tune.md.

## Goal

Classify two frames as STABLE, CHANGED, or UNKNOWN without calling a model.

## Allowed files

Only create or modify:

events/scene_change.py
tests/events/test_scene_change_detector.py

Do not modify any other files.

## Implement

- Define structured SceneChangeResult and status constants/enumeration.
- Use a deterministic, replaceable local comparison algorithm.
- Accept a configured threshold.
- Handle missing/invalid frames as UNKNOWN.
- Return a serializable comparison score and reason.
- Do not retain raw frames after comparison.

## Forbidden scope

Do not call VisionProvider, devices, EventRuntime, AmbientState, schedulers, or external services.

## Tests

Run:

python -m pytest tests/events/test_scene_change_detector.py
python -m pytest
python main.py

PR title:

feat(events): add local scene change detector
```

## PR 3.3：本地声音活动检测器

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.3: add a local sound activity detector.

Before making changes, read docs/prd_2_1.md and docs/tune.md.

## Goal

Classify bounded audio as QUIET, SOUND, SPEECH_CANDIDATE, or UNKNOWN without calling SpeechProvider.

## Allowed files

Only create or modify:

events/sound_activity.py
tests/events/test_sound_activity_detector.py

Do not modify any other files.

## Implement

- Define a structured serializable result.
- Use injectable/local energy or VAD backend behavior.
- Keep thresholds configurable through constructor input.
- Never call ASR or external APIs.
- Invalid audio returns UNKNOWN rather than crashing.

## Forbidden scope

Do not modify microphone provider, Source, Runtime, AmbientState, Demo, or implement continuous listening.

## Tests

Run:

python -m pytest tests/events/test_sound_activity_detector.py
python -m pytest
python main.py

PR title:

feat(events): add local sound activity detector
```

## PR 3.4：AmbientState 时间序列状态

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.4: extend AmbientState with lightweight temporal state.

Before making changes, read docs/prd_2_1.md, docs/architecture.md, docs/tune.md, and runtime/ambient_state.py.

## Goal

Represent scene stability and quiet duration over time without storing raw media.

## Allowed files

Only create or modify:

runtime/ambient_state.py
tests/runtime/test_ambient_state_timeline.py

Do not modify any other files.

## Implement

- Preserve existing latest(event_type) behavior.
- Add current scene summary and temporal fields from PRD 2.1.
- Add explicit methods for stable observation, changed observation, quiet observation, and sound activity.
- Accept timestamps as inputs for deterministic tests.
- Stable observations extend duration even without a new vision summary.
- Changed observations reset stable_since.
- Do not store frames or audio.

## Forbidden scope

Do not implement sampling, detectors, reminders, EventRuntime changes, or task creation.

## Tests

Run:

python -m pytest tests/runtime/test_ambient_state_timeline.py
python -m pytest
python main.py

PR title:

feat(runtime): add ambient state timeline
```

## PR 3.5：单步 Ambient 感知协调器

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.5: add a single-step AmbientSensorRuntime.

Before making changes, read docs/prd_2_1.md, docs/tune.md, events/camera_source.py, events/scene_change.py, and runtime/ambient_state.py.

## Preconditions

PR 3.1, PR 3.2, and PR 3.4 must already be merged.

## Goal

Perform exactly one background camera observation step and publish an ambient RawSignal.

## Allowed files

Only create or modify:

runtime/ambient_sensor_runtime.py
tests/runtime/test_ambient_sensor_step.py

Do not modify any other files.

## Implement

- Accept CameraProvider, SceneChangeDetector, VisionProvider, and EventRuntime dependencies.
- One step captures at most one frame.
- STABLE publishes ambient_stability data without calling VisionProvider.
- CHANGED/UNKNOWN may call VisionProvider once and publish image_summary data.
- Publish only through EventRuntime; do not directly update AmbientState.
- Do not create TaskSession.
- No loop, thread, asyncio, timer, or sleep in this PR.

## Tests

Run:

python -m pytest tests/runtime/test_ambient_sensor_step.py
python -m pytest
python main.py

PR title:

feat(runtime): add single-step ambient sensing
```

## PR 3.6：摄像头五分钟懒采样循环

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.6: add a bounded synchronous lazy camera sampler.

Before making changes, read docs/prd_2_1.md, docs/tune.md, config/settings.py, and runtime/ambient_sensor_runtime.py.

## Precondition

PR 3.5 must already be merged.

## Goal

Schedule AmbientSensorRuntime.step() using the configured heartbeat interval, defaulting to five minutes.

## Allowed files

Only create or modify:

runtime/ambient_sampler.py
tests/runtime/test_ambient_sampler.py

Do not modify any other files.

## Implement

- Inject clock and wait functions for deterministic tests.
- Provide start/stop or run_once_due behavior without starting work at import.
- Never overlap camera captures.
- Stop cleanly and release no resources itself beyond delegated calls.
- No asyncio, multi-task scheduler, or daemon thread in the first version.

## Forbidden scope

Do not modify EventRuntime, TaskRuntime, devices, detectors, AmbientState, reminders, or demo.

## Tests

Run:

python -m pytest tests/runtime/test_ambient_sampler.py
python -m pytest
python main.py

PR title:

feat(runtime): add lazy camera sampler
```

## PR 3.7：声音活动提前采样协调

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.7: coordinate sound activity with early ambient camera sampling.

Before making changes, read docs/prd_2_1.md, docs/tune.md, events/sound_activity.py, and runtime/ambient_sampler.py.

## Preconditions

PR 3.3 and PR 3.6 must already be merged.

## Goal

Allow meaningful sound activity to request one early background camera sample without creating a task.

## Allowed files

Only create or modify:

runtime/ambient_activity_coordinator.py
tests/runtime/test_ambient_activity_coordinator.py

Do not modify any other files.

## Implement

- QUIET updates activity timing but does not request a camera sample.
- SOUND or SPEECH_CANDIDATE may request one early sample subject to cooldown.
- Coalesce repeated requests.
- The coordinator does not call ASR, create TaskSession, or directly update AmbientState.
- Use injected clock for deterministic tests.

## Tests

Run:

python -m pytest tests/runtime/test_ambient_activity_coordinator.py
python -m pytest
python main.py

PR title:

feat(runtime): coordinate sound-triggered ambient sampling
```

## PR 3.8：疲劳/久坐候选判断

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.8: derive fatigue and sedentary reminder candidates from AmbientState.

Before making changes, read docs/prd_2_1.md, docs/tune.md, and runtime/ambient_state.py.

## Goal

Produce a conservative EventCandidate from sustained ambient evidence without notifying the user.

## Allowed files

Only create or modify:

runtime/ambient_conditions.py
tests/runtime/test_ambient_conditions.py

Do not modify any other files.

## Implement

- Define a deterministic evaluator receiving AmbientState, thresholds, current time, and recent reminder time.
- Require sustained evidence; one frame is never enough.
- Respect cooldown and data freshness.
- Return no candidate when evidence is insufficient.
- Candidate language must express uncertainty and must not diagnose fatigue.
- Do not enqueue, route, formulate, or execute a task.

## Tests

Run:

python -m pytest tests/runtime/test_ambient_conditions.py
python -m pytest
python main.py

PR title:

feat(runtime): derive ambient reminder candidates
```

## PR 3.9：InterruptionPolicy 背景提醒规则

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.9: add ambient reminder handling to InterruptionPolicy.

Before making changes, read docs/prd_2_1.md, docs/tune.md, runtime/interruption_policy.py, and runtime/ambient_conditions.py.

## Precondition

PR 3.8 must already be merged.

## Goal

Decide whether an ambient fatigue/sedentary candidate may enter the next lifecycle boundary.

## Allowed files

Only create or modify:

runtime/interruption_policy.py
tests/runtime/test_ambient_interruption_policy.py

Do not modify any other files.

## Implement

- Preserve user-initiated event behavior.
- Support ambient reminder candidate metadata.
- Suppress stale, duplicate, cooldown-blocked, disabled, or low-confidence candidates.
- Allow an eligible candidate without creating or executing a task in the policy.
- Keep decision reasons structured and testable.

## Tests

Run:

python -m pytest tests/runtime/test_ambient_interruption_policy.py
python -m pytest
python main.py

PR title:

feat(runtime): add ambient reminder interruption policy
```

## PR 3.10：背景感知应用组装

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.10: assemble opt-in background sensing services.

Before making changes, read docs/prd_2_1.md, docs/tune.md, demo/cli_demo.py, and all merged Phase 3 runtime modules.

## Preconditions

PR 3.1 through PR 3.9 must already be merged.

## Goal

Create application-level assembly for ambient sensing without moving orchestration into the CLI demo.

## Allowed files

Only create or modify:

runtime/ambient_app.py
tests/runtime/test_ambient_app_assembly.py

Do not modify any other files.

## Implement

- Assemble configured factories, detectors, AmbientSensorRuntime, sampler, coordinator, conditions, and existing EventRuntime.
- Default construction must not start devices or background work.
- Provide explicit start/stop/run-once public methods.
- Disabled config produces an inert service.
- Do not modify TaskRuntime internals.
- No platform branches outside DeviceFactory/backend.

## Tests

Run:

python -m pytest tests/runtime/test_ambient_app_assembly.py
python -m pytest
python main.py

PR title:

feat(runtime): assemble opt-in ambient sensing
```

## PR 3.11：Runtime 2.1 最终契约测试

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.11: add Ella Runtime 2.1 contract tests.

Before making changes, read docs/prd_2_1.md, docs/tune.md, and all existing contract tests.

## Preconditions

All Phase 1, Phase 2, and Phase 3 PRs must already be merged.

## Goal

Verify real-capability boundaries and low-frequency ambient lifecycle without changing production behavior.

## Allowed files

Only create:

tests/contracts/test_runtime_2_1_contracts.py

Do not modify any other file.

## Add contract tests for

- Default startup is mock-safe and does not open devices or network.
- Real visual task path uses EventRuntime and TaskRuntime.
- Camera and microphone public contracts are platform-neutral.
- Platform selection exists only in device layer.
- Background stable observations update duration without model calls.
- Background changes request one lightweight summary.
- Background observations do not directly create TaskSession.
- Microphone silence does not call SpeechProvider.
- Fatigue candidates require sustained evidence and InterruptionPolicy approval.
- Raw media is not stored by default.
- No real network or device access occurs in tests.

Run:

python -m pytest tests/contracts/test_runtime_2_1_contracts.py
python -m pytest
python main.py

PR title:

test(contracts): add runtime 2.1 capability contracts
```

---

# 发布前手工验收（不作为代码 PR）

完成以上 PR 后，分别在 macOS 和 Windows 执行：

1. 默认 mock 配置运行 `python main.py`。
2. 配置真实 Qwen API Key，验证文字 LLM。
3. 启用摄像头，验证默认设备、权限拒绝、设备不存在和资源释放。
4. 运行真实视觉任务，确认 CameraSceneTool 有界采集并返回 Qwen-VL 摘要。
5. 启用麦克风，验证有界录音、权限拒绝、设备不存在和文字 fallback。
6. 验证退出后摄像头指示灯熄灭、麦克风不再占用。
7. 验证背景模式五分钟心跳、稳定持续时间和变化摘要。
8. 验证疲劳候选不会绕过 InterruptionPolicy 直接提醒。

真实验收中发现的平台差异必须通过独立 backend PR 解决，不得在 Runtime、Tool、Source 或 Demo 中加入平台条件分支。

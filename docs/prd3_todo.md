> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella PRD 3 Implementation Prompts

> **⚠️ 已过期文档（核对日期：2026-08-27）**
> 本实施清单引用的 `agent/formulation.py`、`agent/final_response.py`、`demo/cli_demo.py` 路径已失效，对应 PR 已无法直接执行；目标能力大多已通过其他路径实现。
> 仅作历史记录保留。当前架构与设计请参阅 [`docs/design_overview.md`](design_overview.md)。

以下每一节都是可以直接复制给 Codex 的单 PR 提示词。每个 PR 只做一件事，必须严格遵守 allowed files，不要提前实现后续 PR。

---

## PR 3.1：Prompt Engine 数据契约

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.1: add Prompt Engine data contracts.

Before making changes, read:

doc/prd3.md
docs/prd_2_1.md
docs/tune.md

## Goal

Add the Prompt Engine boundary that builds prompt strings from structured context.

This PR only defines the prompt engine contract and templates. It must not wire Prompt Engine into TaskFormulator, FinalResponseGenerator, TaskRuntime, Demo, providers, devices, tools, or memory.

## Scope rule

Only implement PR 3.1.

Prompt Engine must be internally encapsulated:

- External callers pass only prompt_type and required structured context.
- External callers must not depend on system prompt content, template file paths, field ordering, separators, or prompt internal sections.
- Prompt Engine may change how it composes prompt strings without affecting EventRuntime, TaskRuntime, SubAgent, CapabilityExecutor, providers, devices, tools, memory, or page display callers.

## Allowed files

Only create or modify:

prompts/__init__.py
prompts/engine.py
prompts/templates.py
tests/prompts/test_prompt_engine.py

Do not modify any other files.

prompts/__init__.py must remain empty. Do not add exports, template loading, object creation, runtime initialization, or side effects.

## Implement

Define minimal Prompt Engine contracts:

- PromptType or equivalent constants for:
  - TASK_FORMULATION
  - FINAL_RESPONSE
- PromptBuildResult containing:
  - prompt: str
  - prompt_type: str
  - prompt_name: str
  - context_keys: tuple[str, ...]
- PromptEngine with a build(prompt_type, context) method.
- Internal prompt templates/system prompts for task formulation and final response.
- Prompt output must be a string suitable for LLMProvider.generate(prompt).
- PromptEngine must not call LLMProvider.
- PromptEngine must not access camera, microphone, tools, memory, config, env vars, HTTP headers, API keys, or provider credentials.
- PromptEngine must not hardcode going_out as the default identity. going_out may only appear if passed through task context, tool result, or skill metadata.
- Add minimal redaction helper for prompt display: API-key-like strings should become [REDACTED].

The system prompt should be generic Ella agent behavior, not a going_out-specific identity.

## Forbidden scope

Do not modify:

agent/
runtime/
sessions/
demo/
providers/
devices/
tools/
memory/
config/

Do not implement FinalResponseGenerator.
Do not wire PromptEngine into existing LLM calls.
Do not create a page viewer.
Do not modify current demo behavior.

## Tests

Add tests for:

- building TASK_FORMULATION prompt returns PromptBuildResult.
- building FINAL_RESPONSE prompt returns PromptBuildResult.
- prompt is a string.
- prompt_type and prompt_name are included.
- context_keys reflect provided context keys.
- external context does not need to know internal template structure.
- changing context values changes prompt content without changing external call shape.
- redaction replaces API-key-like values with [REDACTED].
- PromptEngine does not call LLMProvider or access external runtime services.
- PromptEngine system prompt is not going_out-specific.

Run:

python -m pytest tests/prompts/test_prompt_engine.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(prompts): add prompt engine contracts
```

---

## PR 3.2：Task Formulation 接入 Prompt Engine

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.2: wire Prompt Engine into task formulation.

Before making changes, read:

doc/prd3.md
docs/prd_2_1.md
docs/tune.md
agent/formulation.py
prompts/engine.py

## Precondition

PR 3.1 must already be merged. Stop if PromptEngine does not exist.

## Goal

Make TaskFormulator use PromptEngine to build the TASK_FORMULATION prompt before calling LLMProvider.generate(prompt).

This PR only changes the task formulation boundary. It must not implement final response generation or page display.

## Scope rule

Only implement PR 3.2.

Prompt composition must remain encapsulated inside PromptEngine. TaskFormulator may pass structured context to PromptEngine, but must not depend on template internals, field order, separators, or system prompt text.

## Allowed files

Only create or modify:

agent/formulation.py
tests/agent/test_prompt_engine_task_formulation.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update TaskFormulator so that:

- It can accept a PromptEngine dependency, with a default PromptEngine if appropriate.
- When llm_provider is present, it builds a TASK_FORMULATION prompt through PromptEngine.
- The string passed to LLMProvider.generate(prompt) is exactly PromptEngine.build(...).prompt.
- The prompt context includes at least:
  - user input text
  - user preference summary
  - environment summary
  - event type
  - trace_id
- Existing deterministic formulation still works without provider.
- Provider failure still falls back safely.
- Prompt build metadata can be retained if consistent with existing data style, but do not add page display yet.
- Remove any debug print of provider output if present.

## Forbidden scope

Do not modify:

runtime/
sessions/
demo/
providers/
devices/
tools/
memory/
prompts/engine.py
prompts/templates.py

Do not implement FinalResponseGenerator.
Do not change TaskRuntime completion behavior.
Do not create page display or snapshot.
Do not add real provider behavior.

## Tests

Add tests for:

- TaskFormulator calls PromptEngine for TASK_FORMULATION.
- LLMProvider.generate receives exactly PromptEngine.build(...).prompt.
- structured context passed to PromptEngine includes user input, preference summary, environment summary, event type, and trace_id.
- formulation still works without LLMProvider.
- provider failure uses deterministic fallback.
- TaskFormulator does not directly assemble full prompt internals.
- no direct providers.qwen import.

Run:

python -m pytest tests/agent/test_prompt_engine_task_formulation.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(agent): build formulation prompts through prompt engine
```

---

## PR 3.3：Final Response Generator

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.3: add Final Response Generator.

Before making changes, read:

doc/prd3.md
docs/prd_2_1.md
docs/tune.md
prompts/engine.py
sessions/output.py
tools/base.py

## Precondition

PR 3.1 must already be merged. Stop if PromptEngine does not exist.

## Goal

Add a FinalResponseGenerator that uses PromptEngine and LLMProvider to generate user-visible final responses from task context and tool results.

This PR only adds the generator boundary. It must not wire it into TaskRuntime yet.

## Scope rule

Only implement PR 3.3.

FinalResponseGenerator must not execute tools, select skills, mutate TaskSession, write memory, or modify Runtime orchestration.

## Allowed files

Only create or modify:

agent/final_response.py
tests/agent/test_final_response_generation.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Create FinalResponseGenerator.

Requirements:

- Accept PromptEngine and LLMProvider dependencies.
- Build FINAL_RESPONSE prompt through PromptEngine.
- Call LLMProvider.generate(prompt) with exactly PromptEngine.build(...).prompt.
- Normalize LLM output into final response text.
- Include prompt trace metadata if useful:
  - trace_id
  - prompt_type
  - prompt_name
  - prompt_text
  - provider_name
  - model_name
  - llm_output
- Convert ToolResult objects or dictionaries into readable tool_results_summary before they enter prompt context.
- Do not put Python repr like ToolResult(...) into prompts.
- If provider is unavailable or fails, produce deterministic fallback using user_input, task_goal, and tool_results_summary.
- Fallback must not return old template `Task completed: <task_goal>`.
- If camera or multimodal result is unavailable, final response should mention that visual context is unavailable when relevant.
- PromptEngine must remain responsible for prompt composition; FinalResponseGenerator only prepares structured context.

## Forbidden scope

Do not modify:

runtime/
sessions/
demo/
providers/
devices/
tools/
memory/
prompts/engine.py
prompts/templates.py

Do not wire into TaskRuntime.
Do not create TaskCompletionPackage.
Do not write memory.
Do not execute tools.
Do not create page display.

## Tests

Add tests for:

- FinalResponseGenerator builds FINAL_RESPONSE prompt through PromptEngine.
- LLMProvider.generate receives exactly PromptEngine.build(FINAL_RESPONSE, ...).prompt.
- tool results are summarized into readable text.
- camera_scene summary and visible_items can influence final response prompt context.
- provider output becomes final response.
- provider failure returns deterministic fallback.
- fallback does not equal or start with `Task completed:`.
- unavailable visual context is reflected in fallback or prompt context.
- FinalResponseGenerator does not execute tools, mutate sessions, or write memory.

Run:

python -m pytest tests/agent/test_final_response_generation.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(agent): add final response generator
```

---

## PR 3.4：TaskRuntime 接入 Final Response Generator

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.4: wire FinalResponseGenerator into TaskRuntime completion.

Before making changes, read:

doc/prd3.md
docs/prd_2_1.md
docs/tune.md
runtime/task_runtime.py
agent/final_response.py

## Preconditions

PR 3.1 and PR 3.3 must already be merged. Stop if PromptEngine or FinalResponseGenerator does not exist.

## Goal

Make TaskRuntime use FinalResponseGenerator at completion time so UserVisibleAgentOutput.final_response is generated from task context and tool results instead of the old `Task completed: <task_goal>` template.

## Scope rule

Only implement PR 3.4.

TaskRuntime should remain a lifecycle and completion boundary. It must not own prompt composition or LLM response logic.

## Allowed files

Only create or modify:

runtime/task_runtime.py
tests/runtime/test_task_runtime_final_response.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update TaskRuntime so that:

- It can receive a FinalResponseGenerator dependency.
- During completion package creation, it collects completion context and delegates final response generation to FinalResponseGenerator.
- It passes user input, task_goal, constraints, completion criteria, tool results, user preference summary, environment summary, and trace_id when available.
- It stores the generated final response in UserVisibleAgentOutput.final_response.
- It preserves UserVisibleAgentOutput.process data for task goal, strategy, and tool result names.
- It does not build prompt strings itself.
- It does not call LLMProvider directly.
- It does not execute extra tools.
- It does not write memory directly outside existing MemoryManager flow.
- The old `Task completed: <task_goal>` template is no longer used for successful final response generation or fallback.

## Forbidden scope

Do not modify:

agent/final_response.py
prompts/
sessions/
demo/
providers/
devices/
tools/
memory/

Do not implement page display.
Do not alter TaskSession state machine transitions.
Do not change EventRuntime.
Do not add new tools or providers.

## Tests

Add tests for:

- completed task uses FinalResponseGenerator.
- final response uses tool results summary when tool results exist.
- final response is not `Task completed: <task_goal>`.
- TaskRuntime does not call LLMProvider directly.
- TaskRuntime does not build prompt text itself.
- TaskRuntime still creates TaskCompletionPackage.
- MemoryManager flow still receives completion package through existing path.
- existing task runtime completion behavior remains compatible.

Run:

python -m pytest tests/runtime/test_task_runtime_final_response.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(runtime): generate final responses through agent boundary
```

---

## PR 3.5：运行展示快照

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.5: add RunDisplaySnapshot data contract.

Before making changes, read:

doc/prd3.md
docs/prd_2_1.md
docs/tune.md
demo/cli_demo.py
runtime/task_runtime.py

## Preconditions

PR 3.1 through PR 3.4 should already be merged. Stop and explain if final responses are still generated by the old `Task completed: <task_goal>` template.

## Goal

Add a display snapshot data object that captures the information the local page display needs, without implementing the page itself.

## Scope rule

Only implement PR 3.5.

RunDisplaySnapshot is display data only. It must not orchestrate Runtime, call providers, call devices, execute tools, create sessions, or write memory.

## Allowed files

Only create or modify:

demo/display_snapshot.py
tests/demo/test_display_snapshot.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Create RunDisplaySnapshot.

It should include fields for:

- user_input
- transcript
- captured_frame or captured_frame_reference
- image_status
- scene_summary
- visible_items
- task_goal
- task_formulation_prompt_text
- final_response_prompt_text
- tool_results_summary
- final_response
- memory_status

Requirements:

- Snapshot can be constructed from explicit values.
- Snapshot serialization is deterministic.
- Prompt fields are display traces only and must not be marked for memory writing.
- Prompt text should be redacted for API-key-like secrets if included.
- Image status should support at least:
  - mock image
  - camera frame
  - camera unavailable
  - text-only
- Snapshot does not call Runtime, providers, devices, tools, or memory.

## Forbidden scope

Do not modify:

runtime/
agent/
sessions/
providers/
devices/
tools/
memory/
demo/cli_demo.py

Do not implement HTML page.
Do not implement browser opening.
Do not alter CLI output.
Do not access real devices or network.

## Tests

Add tests for:

- snapshot construction.
- deterministic serialization.
- prompt fields are present.
- API-key-like prompt text is redacted to [REDACTED].
- image_status supports required values.
- snapshot does not call Runtime or providers.
- snapshot does not write memory.

Run:

python -m pytest tests/demo/test_display_snapshot.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): add run display snapshot contract
```

---

## PR 3.6：本地页面显示器

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.6: add local page viewer for RunDisplaySnapshot.

Before making changes, read:

doc/prd3.md
docs/prd_2_1.md
docs/tune.md
demo/display_snapshot.py

## Precondition

PR 3.5 must already be merged. Stop if RunDisplaySnapshot does not exist.

## Goal

Add a local HTML page renderer that displays a completed RunDisplaySnapshot.

This PR only renders display data. It must not run Runtime or access real providers/devices.

## Scope rule

Only implement PR 3.6.

The page viewer is not a Runtime. Runtime produces data; page viewer displays data.

## Allowed files

Only create or modify:

demo/page_viewer.py
demo/static/display.html
tests/demo/test_page_viewer.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Create a local page viewer that:

- Accepts RunDisplaySnapshot or serialized snapshot data.
- Renders local HTML output.
- Displays sections:
  - Input
  - Vision
  - Prompt Sent to LLM
  - Agent
  - Answer
- Shows user input and transcript.
- Shows image status and captured frame/placeholder if available.
- Shows scene summary and visible items.
- Shows task goal.
- Shows task_formulation_prompt_text.
- Shows final_response_prompt_text.
- Shows final response.
- Prompt sections should be collapsible by default if practical.
- The page must not label prompt text as Reasoning, Chain of Thought, or Model Thinking.
- The page must not call EventRuntime, TaskRuntime, providers, devices, tools, or memory.
- The first version should be static/local and not implement WebSocket, live camera stream, task status stream, or multi-turn sessions.

## Forbidden scope

Do not modify:

runtime/
agent/
sessions/
providers/
devices/
tools/
memory/
demo/cli_demo.py

do not access real camera, microphone, network, or Qwen.
Do not implement live refresh or websocket.
Do not write memory.

## Tests

Add tests for:

- page viewer renders required sections.
- prompt section title is Prompt Sent to LLM.
- prompt text appears from snapshot fields.
- page does not contain Reasoning, Chain of Thought, or Model Thinking labels.
- image_status appears.
- scene summary appears.
- final response appears.
- renderer does not call Runtime or providers.

Run:

python -m pytest tests/demo/test_page_viewer.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): add local run display page
```

---

## PR 3.7：Demo 接入页面显示器

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 3.7: connect CLI demo output to the local page viewer.

Before making changes, read:

doc/prd3.md
docs/prd_2_1.md
docs/tune.md
demo/cli_demo.py
demo/display_snapshot.py
demo/page_viewer.py

## Preconditions

PR 3.1 through PR 3.6 must already be merged.
Stop if PromptEngine, FinalResponseGenerator, RunDisplaySnapshot, or page viewer is missing.

## Goal

Allow DemoRuntime to generate a RunDisplaySnapshot and local display page after the Runtime flow completes.

This PR only adapts demo assembly. It must not change PromptEngine, TaskRuntime, providers, devices, tools, or memory behavior.

## Scope rule

Only implement PR 3.7.

Demo assembly may collect display data from existing Runtime results, but must not re-orchestrate Runtime flow.

## Allowed files

Only create or modify:

demo/cli_demo.py
tests/demo/test_cli_demo_page_display.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update demo behavior so that after a normal EventRuntime → TaskRuntime run completes, it can:

- Build a RunDisplaySnapshot.
- Include user input.
- Include transcript when microphone mode is used.
- Include image_status.
- Include scene summary and visible items from camera_scene ToolResult when present.
- Include task goal.
- Include task_formulation_prompt_text if available.
- Include final_response_prompt_text if available.
- Include final response.
- Render or save local page through page viewer.

Requirements:

- Existing run_demo() and python main.py behavior must remain runnable.
- Text mode must still work.
- Microphone mode must still work.
- Demo must not directly call CameraSceneTool.
- Demo must not directly call LLMProvider.
- Demo must not directly create TaskSession.
- Demo must not directly write MemoryManager.
- Demo must not bypass EventRuntime or TaskRuntime.
- Page generation must use snapshot data only.

## Forbidden scope

Do not modify:

runtime/
agent/
sessions/
prompts/
providers/
devices/
tools/
memory/
demo/page_viewer.py
demo/display_snapshot.py

Do not implement live page updates.
Do not access real devices outside existing runtime paths.
Do not add new prompt behavior.
Do not change final response generation.

## Tests

Add tests for:

- demo can build RunDisplaySnapshot after text run.
- demo can build RunDisplaySnapshot after microphone run using injected microphone source.
- snapshot includes user_input or transcript.
- snapshot includes final response.
- snapshot includes prompt fields when available.
- snapshot includes visual summary when camera_scene result exists.
- demo uses page viewer rather than rendering HTML inline if that is the established page viewer API.
- demo does not directly call CameraSceneTool, LLMProvider, TaskSession, or MemoryManager.
- python main.py still runs.

Run:

python -m pytest tests/demo/test_cli_demo_page_display.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): connect runtime display page
```

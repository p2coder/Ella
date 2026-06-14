# Ella Tool Runtime Refactor TODO Prompts

下面每一段都是可以直接复制给 Codex / ChatGPT 的实施提示词。每个 PR 只做一个模块边界，必须按顺序推进，不要合并多个 PR 一次完成。

---

## PR 1：ToolDefinition 数据契约

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 1: add ToolDefinition data contracts.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
tools/base.py

## Goal

Add the structured ToolDefinition contract for self-describing tools.

This PR only defines data contracts. It must not change ToolManager, SubAgent, CapabilityExecutor, TaskRuntime, skills, providers, devices, memory, or demo behavior.

## Scope rule

Only implement Tool Runtime PR 1.

Do not implement tool discovery.
Do not implement tool execution changes.
Do not modify existing tool behavior.
Do not connect ToolDefinition to LLM calls yet.

## Allowed files

Only create or modify:

tools/base.py
tests/tools/test_tool_definition.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add ToolDefinition with at least:

- name
- description
- schema_version
- input_schema
- input_examples
- output_schema

Requirements:

- ToolDefinition should be immutable if consistent with existing style.
- name must be non-empty and stable.
- description must be non-empty.
- schema_version must be non-empty.
- input_schema top level must describe an object.
- output_schema top level must describe an object.
- input_examples should be stored deterministically.
- ToolDefinition must not contain Tool instances, provider credentials, local paths, class names, raw media, or runtime resources.
- Add minimal serialization support if consistent with existing code style.
- Preserve existing Tool and ToolResult compatibility.
- Do not require existing tools to define ToolDefinition in this PR.

## Forbidden scope

Do not modify:

tools/manager.py
tools/mock_tools.py
tools/camera_scene.py
registries/
sessions/
runtime/
agent/
skill/
providers/
devices/
memory/
demo/

Do not implement ToolManager discovery.
Do not implement schema validation in Executor.
Do not implement LLM tool selection.
Do not modify going_out behavior.

## Tests

Add tests for:

- ToolDefinition construction.
- empty name is rejected.
- empty description is rejected.
- empty schema_version is rejected.
- input_schema must be object-shaped.
- output_schema must be object-shaped.
- input_examples are preserved deterministically.
- serialization works if implemented.
- ToolDefinition does not include runtime resources.
- existing ToolResult construction still works.

Run:

python -m pytest tests/tools/test_tool_definition.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(tools): add tool definition contract
```

---

## PR 2：现有 Tool 提供结构化定义

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 2: add ToolDefinition to existing tools.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
tools/base.py
tools/mock_tools.py
tools/camera_scene.py

## Precondition

PR 1 must already be merged. Stop if ToolDefinition does not exist.

## Goal

Make existing mock tools and CameraSceneTool declare structured ToolDefinition.

This PR only adds tool metadata. It must not change tool selection, execution orchestration, TaskRuntime, SubAgent planning, or demo assembly.

## Scope rule

Only implement Tool Runtime PR 2.

Existing tools may continue to support the old context-only behavior through compatibility. First phase may use arguments={} and tools may temporarily ignore arguments.

## Allowed files

Only create or modify:

tools/mock_tools.py
tools/camera_scene.py
tests/tools/test_tool_definitions.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add ToolDefinition to:

- MockVisionSummaryTool
- MockWeatherTool
- MockChecklistTool
- CameraSceneTool

Each ToolDefinition should include:

- stable name
- natural language description
- schema_version
- input_schema
- input_examples
- output_schema

Descriptions should explain:

- what the tool does
- when it should be used
- when it should not be used
- key limitations or side effects

Requirements:

- Existing tool names must remain stable.
- Existing behavior must remain compatible.
- CameraSceneTool must remain bounded and mock-safe by default.
- Do not expose credentials, local paths, internal class names, raw media, permission internals, or debug-only fields in ToolDefinition.
- Do not register tools globally in this PR.
- Do not make ToolManager execute tools.

## Forbidden scope

Do not modify:

tools/manager.py
registries/
sessions/
runtime/
agent/
skill/
providers/
devices/
memory/
demo/

Do not implement ToolManager discovery.
Do not implement schema validation in Executor.
Do not implement LLM tool selection.
Do not remove going_out hardcoded sequences.

## Tests

Add tests for:

- each existing tool exposes ToolDefinition.
- each ToolDefinition has name, description, schema_version, input_schema, input_examples, output_schema.
- tool names remain stable.
- ToolDefinition descriptions are non-empty.
- ToolDefinition schemas are object-shaped.
- input_examples are deterministic.
- ToolDefinition excludes credentials, local paths, class names, raw media, and permission internals.
- existing tool run behavior still works with current compatibility path.

Run:

python -m pytest tests/tools/test_tool_definitions.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(tools): describe existing tools with definitions
```

---

## PR 3：ToolManager 定义发现接口

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 3: add ToolManager ToolDefinition discovery.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
tools/manager.py
registries/tool_registry.py
agent/context.py
tools/base.py

## Preconditions

PR 1 and PR 2 must already be merged. Stop if ToolDefinition is missing from existing tools.

## Goal

Allow ToolManager to return the current task-visible ToolDefinition snapshot.

This PR only changes the tool directory/discovery boundary. It must not execute tools or modify SubAgent, Executor, TaskRuntime, skills, providers, devices, memory, or demo.

## Scope rule

Only implement Tool Runtime PR 3.

ToolManager is a process-level capability directory. It must not become an executor.

## Allowed files

Only create or modify:

tools/manager.py
tests/tools/test_tool_definition_discovery.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add ToolManager directory/discovery methods such as:

- get_tool(tool_name)
- list_definitions(context)

Requirements:

- ToolManager must not execute Tool.
- ToolManager may use ToolRegistry internally.
- If ToolManager uses ToolRegistry, ToolRegistry must be the only Tool storage source.
- Do not maintain a second Tool mapping inside ToolManager if ToolRegistry already stores tools.
- Discovery must return ToolDefinition snapshots, not Tool instances.
- Discovery must filter by registered tools, role visibility, and task allowed tools:

registered_tools
∩ role_visible_tools
∩ task_allowed_tools

- If there is no stable role model yet, do not broadly modify AgentExecutionContext. Use current compatible defaults such as main_agent.
- Task permissions should come from existing context capability scope / allowed_tools compatibility.
- ToolManager must remain process-level and long-lived.
- Registering tools should remain app assembly behavior, not per task.

## Forbidden scope

Do not modify:

registries/tool_registry.py
sessions/
runtime/
agent/context.py
agent/
skill/
providers/
devices/
memory/
demo/

Do not implement schema validation.
Do not implement LLM tool decision.
Do not modify TaskRuntime.
Do not remove going_out hardcoded sequences.

## Tests

Add tests for:

- ToolManager returns ToolDefinition snapshots.
- list_definitions filters by allowed_tools.
- list_definitions filters by allowed_roles using compatible main_agent defaults.
- get_tool returns live registered tools by name.
- unknown tool name returns clear missing behavior.
- ToolManager does not execute tools.
- ToolManager does not return Tool instances from list_definitions.
- ToolManager does not duplicate storage if ToolRegistry is used.
- registering once supports multiple discovery calls.

Run:

python -m pytest tests/tools/test_tool_definition_discovery.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(tools): add tool definition discovery
```

---

## PR 4：Tool 参数与结果 Schema 校验

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 4: validate tool input and output schemas in CapabilityExecutor.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
sessions/executor.py
sessions/decision.py
tools/base.py
tools/manager.py
pyproject.toml

## Preconditions

PR 1 through PR 3 must already be merged. Stop if ToolDefinition discovery is unavailable.

## Goal

Make CapabilityExecutor validate one ExecutionDecision's tool input and output against ToolDefinition schemas.

This PR only changes execution validation. It must not modify SubAgent decision logic, TaskRuntime orchestration, tools, providers, devices, memory, or demo.

## Scope rule

Only implement Tool Runtime PR 4.

CapabilityExecutor executes exactly one action. It must not loop, select skills, select tools, generate final answers, create completion packages, or write memory.

## Allowed files

Only create or modify:

sessions/executor.py
pyproject.toml
tests/sessions/test_tool_schema_validation.py

Do not modify any other files.
Do not modify __init__.py.

If no dependency change is needed, do not modify pyproject.toml.
If another file appears necessary, stop and explain why before changing it.

## Implement

Update CapabilityExecutor so that:

- CALL_TOOL validates tool_input / arguments against ToolDefinition.input_schema before calling Tool.
- invalid input returns structured failure and does not call Tool.
- after Tool.run(), ToolResult.payload is validated against ToolDefinition.output_schema.
- invalid output returns structured failure.
- invalid_tool_output is not written to successful tool trace.
- invalid_tool_output is not included in successful ToolResult list.
- invalid_tool_output must not be treated as trusted facts for final response prompts.
- unknown tool names are not executed.
- removed tools return replan_required or equivalent structured failure.
- COMPLETE, WAIT, and REPLAN do not call tools.
- Executor still validates allowed_tools / capability scope and live availability.
- Existing old tools remain compatible with arguments={} where needed.

JSON Schema first version should only require support for:

- type
- properties
- required
- enum
- additionalProperties
- array items
- string / number / boolean / object / array

Do not implement full JSON Schema support such as oneOf, anyOf, allOf, $ref, patternProperties, or complex format unless a library handles it naturally.

## Forbidden scope

Do not modify:

sessions/subagent.py
sessions/decision.py
sessions/session.py
runtime/
agent/
tools/base.py
tools/mock_tools.py
tools/camera_scene.py
tools/manager.py
skill/
providers/
devices/
memory/
demo/

Do not implement LLM tool selection.
Do not modify TaskRuntime state transitions.
Do not remove going_out hardcoded sequences.

## Tests

Add tests for:

- valid CALL_TOOL input executes one tool.
- invalid input does not call tool.
- unknown tool does not execute.
- missing or removed tool returns replan_required or structured failure.
- valid output is accepted.
- invalid output returns invalid_tool_output.
- invalid output is not appended to successful tool trace.
- invalid output is not returned as a successful ToolResult.
- COMPLETE / WAIT / REPLAN do not call tools.
- existing tools remain compatible with arguments={}.
- Executor does not mutate TaskSession state directly.

Run:

python -m pytest tests/sessions/test_tool_schema_validation.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(execution): validate tool schemas in executor
```

---

## PR 5a：Provider-neutral ToolDefinition 序列化

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 5a: add provider-neutral ToolDefinition serialization.

Before making changes, read:

pr_tool.md
doc/prd3.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
tools/base.py
providers/llm.py
providers/mock.py
prompts/engine.py

## Preconditions

PR 1 through PR 4 must already be merged. Stop if ToolDefinition or executor schema validation is missing.

## Goal

Serialize internal ToolDefinition into a provider-neutral LLM input format.

This PR only prepares tool definition serialization for prompts / provider calls. It must not modify SubAgent decision behavior or implement provider-native tool calling.

## Scope rule

Only implement Tool Runtime PR 5a.

ToolDefinition serialization must expose only public, model-appropriate tool metadata.

## Allowed files

Only create or modify:

providers/llm.py
providers/mock.py
prompts/engine.py
tests/providers/test_tool_definition_serialization.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add provider-neutral serialization for ToolDefinition.

The serialized tool view may include:

- name
- description
- input_schema
- necessary input_examples
- optionally trimmed output_schema

The serialized tool view must not include:

- provider credentials
- API keys
- authorization headers
- local file paths
- internal class names
- debug-only fields
- raw media
- permission implementation internals
- Tool instances

Requirements:

- Serialization must be deterministic.
- It must be safe to include in PromptEngine context.
- It must not call LLMProvider.
- It must not call ToolManager.
- It must not execute tools.
- Mock provider tests may inspect received tool metadata but must not execute tools.
- Provider-native Qwen/OpenAI tool calling is explicitly out of scope.

## Forbidden scope

Do not modify:

sessions/subagent.py
sessions/executor.py
runtime/
agent/
tools/
skill/
devices/
memory/
demo/
providers/qwen.py

Do not implement provider-native tool calling.
Do not alter ExecutionDecision.
Do not remove going_out hardcoded sequences.

## Tests

Add tests for:

- ToolDefinition serializes to provider-neutral shape.
- serialization includes name, description, input_schema, and examples.
- output_schema is omitted or trimmed according to implementation.
- credentials/API-key-like values are not serialized.
- local paths are not serialized.
- internal class names are not serialized.
- raw media is not serialized.
- permission internals are not serialized.
- serialization is deterministic.
- PromptEngine can accept serialized tool definitions as structured context without depending on template internals.

Run:

python -m pytest tests/providers/test_tool_definition_serialization.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(providers): serialize tool definitions for llm input
```

---

## PR 5b：SubAgent 使用可见 ToolDefinition 决策

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 5b: let SubAgent decide using visible ToolDefinition.

Before making changes, read:

pr_tool.md
doc/prd3.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
sessions/subagent.py
sessions/decision.py
tools/manager.py
providers/llm.py
prompts/engine.py

## Preconditions

PR 1 through PR 5a must already be merged. Stop if provider-neutral ToolDefinition serialization is missing.

## Goal

Let SubAgent consume visible ToolDefinition and normalize LLM output into one internal ExecutionDecision.

This PR only changes SubAgent decision behavior. It must not execute tools or implement provider-native tool calling.

## Scope rule

Only implement Tool Runtime PR 5b.

SubAgent decides one next action. CapabilityExecutor remains responsible for validation and execution.

## Allowed files

Only create or modify:

sessions/subagent.py
tests/sessions/test_llm_tool_decision.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update SubAgent so that:

- it can read visible ToolDefinition snapshots from the configured tool directory boundary when available.
- it sends task context, skill instructions, previous tool result summary, and visible ToolDefinition metadata into the LLM decision boundary.
- it expects provider-neutral/internal JSON decision output in the first version.
- it normalizes output into one ExecutionDecision.
- supported actions remain CALL_TOOL, COMPLETE, WAIT, REPLAN.
- LLM output illegal JSON, unknown action, missing action, missing tool_name, or missing required parameters must not execute Tool.
- invalid model output returns structured failure, REPLAN, or blocked decision.
- unknown tool_name must not execute and should return REPLAN or structured failure.
- WAIT / REPLAN must remain compatible with TaskRuntime max_steps / max_replans protections.
- SubAgent must not hold Tool instances.
- SubAgent must not call ToolManager.execute because ToolManager must not execute.
- SubAgent must not call tools.
- SubAgent must not write memory.
- SubAgent must not create completion packages.

Important compatibility:

- Do not remove GOING_OUT_TOOL_SEQUENCE / GOING_OUT_VISUAL_TOOL_SEQUENCE yet unless this PR also preserves current demo determinism.
- Mock-safe mode must keep deterministic tool decision fallback when no real LLM decision is available.

## Forbidden scope

Do not modify:

sessions/executor.py
sessions/decision.py
runtime/
agent/
tools/
skill/
providers/
devices/
memory/
demo/

Do not implement provider-native tool calling.
Do not remove deterministic going_out fallback.
Do not execute tools.

## Tests

Add tests for:

- SubAgent receives visible ToolDefinition metadata.
- LLM internal JSON CALL_TOOL becomes ExecutionDecision.
- LLM internal JSON COMPLETE becomes ExecutionDecision.
- invalid JSON does not execute tools and returns structured failure/REPLAN/blocked.
- unknown action does not execute tools.
- missing tool_name for CALL_TOOL does not execute tools.
- unknown tool_name does not execute tools.
- decision returns only one action.
- mock-safe going_out fallback remains deterministic.
- SubAgent does not call tools, ToolManager.execute, MemoryManager, or TaskRuntime.
- existing select_strategy behavior remains compatible.

Run:

python -m pytest tests/sessions/test_llm_tool_decision.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(execution): decide next action from tool definitions
```

---

## PR 5c：Provider 原生 Tool Calling 适配

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 5c: add provider-native tool calling adapter.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
providers/qwen.py
providers/factory.py
providers/llm.py
tools/base.py

## Preconditions

PR 1 through PR 5b must already be merged. Stop if SubAgent cannot already use provider-neutral internal JSON tool decisions.

## Goal

Add a provider-native tool calling adapter for Qwen or equivalent providers while keeping Ella's internal ToolDefinition and ExecutionDecision contracts stable.

This PR only changes provider adaptation. It must not modify Tool, Executor, TaskRuntime, Skill, demo, or runtime orchestration.

## Scope rule

Only implement Tool Runtime PR 5c.

Provider-specific formats must not leak into SubAgent, TaskRuntime, CapabilityExecutor, ToolManager, or Tool implementations.

## Allowed files

Only create or modify:

providers/qwen.py
providers/factory.py
tests/providers/test_qwen_tool_calling_adapter.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add provider-native tool calling support behind provider boundaries.

Requirements:

- Verify current official provider documentation before coding if implementing real Qwen protocol.
- Default tests must not access network.
- Accept internal ToolDefinition or provider-neutral serialized definitions.
- Convert them into provider-native tools/functions format inside providers only.
- Convert provider-native tool call responses back into internal decision data.
- Missing, malformed, unknown, or unsupported provider-native tool calls must become structured provider/decision errors.
- Do not expose credentials, API keys, local paths, raw media, or permission internals in provider tool metadata.
- Preserve injectable/fake transport for tests.
- Default mock-safe behavior must still work without real Qwen.

## Forbidden scope

Do not modify:

sessions/
runtime/
agent/
tools/
skill/
devices/
memory/
demo/
prompts/

Do not execute tools from provider code.
Do not change CapabilityExecutor validation.
Do not remove deterministic fallback.
Do not make network calls in tests.

## Tests

Add tests for:

- internal ToolDefinition converts to Qwen-native tool metadata.
- provider-native tool response converts back to internal decision shape.
- malformed provider tool call becomes structured error.
- unknown tool call name becomes structured error.
- credentials/API keys are not serialized into tool metadata.
- provider-specific fields do not leak to sessions/runtime/tools.
- factory can select provider-native adapter only when configured.
- default tests use fake transport and make no network calls.

Run:

python -m pytest tests/providers/test_qwen_tool_calling_adapter.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(providers): add qwen tool calling adapter
```

---

## PR 6：Skill 按名称声明 Tool 依赖

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 6: let skills declare tool references by name.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
skill/registry.py
skill/loader.py
skill/skills/going_out/SKILL.md
tools/manager.py

## Preconditions

PR 1 through PR 5b must already be merged. Provider-native PR 5c is optional for this PR.

## Goal

Allow Skill metadata to declare required_tools and optional_tools by stable ToolDefinition.name.

This PR only changes skill metadata parsing and representation. It must not execute tools or turn required_tools into an execution plan.

## Scope rule

Only implement Tool Runtime PR 6.

Skill is task experience and strategy metadata, not a Tool container.

## Allowed files

Only create or modify:

skill/registry.py
skill/loader.py
skill/skills/going_out/SKILL.md
tests/registries/test_skill_tool_references.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add skill metadata support for:

- required_tools
- optional_tools

Requirements:

- Skill references tools only by stable name.
- Skill must not cache Tool instances.
- Loader should parse required_tools and optional_tools from SKILL.md.
- Registry should expose these references in skill definitions/summaries if consistent with existing style.
- Existing going_out skill should declare appropriate tool names.
- Missing metadata should use a safe backward-compatible default.
- Skill.required_tools is not a direct execution plan.
- required_tools must not bypass SubAgent decisions.
- required_tools must not bypass CapabilityExecutor validation.
- Tool removed from ToolManager must still be unavailable even if a skill references it.

## Forbidden scope

Do not modify:

sessions/
runtime/
agent/
tools/
providers/
devices/
memory/
demo/

Do not execute tools.
Do not modify SubAgent decision logic.
Do not remove GOING_OUT_TOOL_SEQUENCE yet.
Do not add new tools.

## Tests

Add tests for:

- Skill loader parses required_tools.
- Skill loader parses optional_tools.
- going_out skill declares expected tool names.
- Skill definitions store tool names, not Tool instances.
- missing metadata remains backward compatible.
- required_tools is not treated as an execution plan.
- SkillManager/registry does not execute tools.
- Skill references do not bypass ToolManager or Executor validation.

Run:

python -m pytest tests/registries/test_skill_tool_references.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(skills): reference tools by stable name
```

---

## PR 7：移除 SubAgent 硬编码工具序列

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 7: remove hardcoded going_out tool sequences from SubAgent.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
sessions/subagent.py
skill/skills/going_out/SKILL.md
tools/manager.py

## Preconditions

PR 1 through PR 6 must already be merged.

Stop if any of these are false:

- existing tools expose ToolDefinition.
- ToolManager can list visible ToolDefinition snapshots.
- CapabilityExecutor validates tool input/output.
- SubAgent can use visible ToolDefinition in decisions.
- Skill metadata can declare required_tools / optional_tools.
- mock-safe deterministic decision fallback exists or can remain in SubAgent without hardcoded sequence constants.

## Goal

Remove GOING_OUT_TOOL_SEQUENCE and related hardcoded tool order constants from SubAgent, replacing them with Skill guidance, visible ToolDefinition, and LLM/internal decision behavior.

## Scope rule

Only implement Tool Runtime PR 7.

This PR changes SubAgent dynamic tool selection only. It must not modify Executor, ToolManager, tools, TaskRuntime, providers, devices, memory, or demo.

## Allowed files

Only create or modify:

sessions/subagent.py
tests/sessions/test_dynamic_tool_selection.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Remove hardcoded tool sequence behavior such as:

- GOING_OUT_TOOL_SEQUENCE
- GOING_OUT_VISUAL_TOOL_SEQUENCE
- fixed mock_weather / mock_checklist / camera_scene ordering rules

Replace with:

- current task context
- skill instructions/tool references
- visible ToolDefinition snapshots
- LLM/internal JSON decision output
- deterministic mock-safe fallback when LLM/tool-decision provider is unavailable

Requirements:

- SubAgent still returns one ExecutionDecision per call.
- SubAgent does not execute tools.
- SubAgent does not hold Tool instances.
- SubAgent does not call ToolManager.execute.
- Unknown, invalid, or missing LLM actions do not execute tools.
- WAIT / REPLAN decisions remain bounded by TaskRuntime max_steps / max_replans protections.
- mock-safe going_out demo remains deterministic and runnable without real LLM/provider-native tool calling.
- Removal must not break python main.py.

## Forbidden scope

Do not modify:

sessions/executor.py
runtime/
agent/
tools/
skill/
providers/
devices/
memory/
demo/

Do not implement provider-native tool calling.
Do not change ToolDefinition.
Do not change schema validation.
Do not add new tools.

## Tests

Add tests for:

- SubAgent no longer depends on GOING_OUT_TOOL_SEQUENCE constants.
- SubAgent chooses next action from visible ToolDefinition / skill guidance.
- going_out can still call relevant tools through dynamic decision.
- non-going_out tasks are not forced into going_out behavior.
- invalid LLM output does not execute tools.
- unknown tool decision does not execute tools.
- deterministic fallback works in mock-safe mode.
- SubAgent returns one ExecutionDecision per call.
- SubAgent does not mutate TaskSession state.
- python main.py remains runnable.

Run:

python -m pytest tests/sessions/test_dynamic_tool_selection.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(execution): remove hardcoded tool sequences
```

---

## PR 8：应用装配和契约回归

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Runtime PR 8: add tool runtime assembly and contract regression tests.

Before making changes, read:

pr_tool.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
demo/cli_demo.py
tools/manager.py
sessions/subagent.py
sessions/executor.py
runtime/task_runtime.py

## Preconditions

PR 1 through PR 7 must already be merged.

Stop if dynamic tool selection is not implemented or if the demo still requires hardcoded SubAgent tool sequence constants.

## Goal

Verify that tools are registered once at application assembly, discovered through ToolManager, selected by SubAgent, executed by CapabilityExecutor, and remain hot-plug/permission safe.

This PR is primarily assembly and contract regression. It must not add new tools or change TaskRuntime state machine behavior.

## Scope rule

Only implement Tool Runtime PR 8.

The app assembly may register concrete tools, but must not define task permission tuples manually or duplicate Tool storage.

## Allowed files

Only create or modify:

demo/cli_demo.py
tests/contracts/test_tool_runtime_contract.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update or verify application assembly so that:

- tools are registered once during app/demo runtime construction.
- ToolManager is process-level and long-lived.
- ToolManager does not execute tools.
- ToolRegistry, if used internally, remains the only Tool storage source.
- TaskRuntime does not define concrete tool names.
- TaskSession / AgentExecutionContext hold permission scope by name, not Tool instances.
- SubAgent sees current visible ToolDefinition snapshots.
- CapabilityExecutor resolves tools by name at execution time.
- Removed tools are observed before next execution/replan.
- Newly added tools do not bypass an existing task's permission scope.
- default mock-safe demo still runs deterministically.

## Forbidden scope

Do not modify:

runtime/task_runtime.py
sessions/
tools/
skill/
providers/
devices/
memory/
agent/

Do not add new tools.
Do not change TaskRuntime state machine.
Do not add provider-native tool calling.
Do not access real network, camera, or microphone in tests.

## Tests

Add contract tests for:

- tools are registered once in app assembly.
- ToolManager is reused across multiple tasks.
- ToolManager does not execute tools.
- ToolRegistry is the only storage source if ToolManager uses it.
- LLM/SubAgent receives only visible ToolDefinition snapshots.
- ToolDefinition sent to LLM excludes credentials, local paths, class names, raw media, and permission internals.
- two tasks can have different visible tool scopes.
- tool added after task creation does not enter existing task scope.
- removed tool is unavailable before execution/replan.
- invalid LLM action does not execute tool.
- WAIT / REPLAN is bounded by max_steps / max_replans or equivalent.
- Skill.required_tools does not bypass SubAgent and Executor validation.
- going_out demo remains mock-safe and deterministic.
- python main.py remains runnable.

Run:

python -m pytest tests/contracts/test_tool_runtime_contract.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

test(contracts): add tool runtime boundary contracts
```

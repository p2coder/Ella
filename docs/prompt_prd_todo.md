# Ella Prompt Engine PRD Implementation Prompts

以下每一节都是可以直接复制给 Codex 的单 PR 提示词。每个 PR 只做一件事，必须严格遵守 allowed files，不要提前实现后续 PR。

---

## PR 1：PromptFrame 数据契约

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 1: add PromptFrame data contracts.

Before making changes, read:

docs/prompt_prd.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
prompts/engine.py
prompts/templates.py

## Goal

Add the structured PromptFrame boundary that lets PromptEngine compose prompts from named context blocks without exposing internal prompt layout to callers.

This PR only changes Prompt Engine data contracts. It must not wire new behavior into TaskRuntime, SubAgent, TaskFormulator, FinalResponseGenerator, providers, tools, memory, or demo.

## Scope rule

Only implement Prompt PR 1.

PromptEngine remains the only component that knows how prompt blocks are ordered, formatted, trimmed, or rendered.

## Allowed files

Only create or modify:

prompts/engine.py
tests/prompts/test_prompt_frame_contract.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add data contracts for:

- PromptBlock or equivalent:
  - name
  - content
  - metadata
- PromptFrame or equivalent:
  - prompt_type
  - blocks
  - output_contract
- PromptBuildResult should still contain:
  - prompt
  - prompt_type
  - prompt_name
  - context_keys

Requirements:

- External callers still call PromptEngine.build(prompt_type, context).
- External callers must not construct final prompt strings.
- External callers must not depend on block order, separators, template paths, or system prompt text.
- PromptEngine may internally convert structured context into PromptFrame.
- PromptFrame must support blocks for:
  - SystemPrompt
  - Skill
  - Tool
  - Memory
  - UserPrompt
  - WorkSpace
  - OutputContract
- PromptFrame must not call LLMProvider.
- PromptFrame must not query SkillManager, ToolManager, MemoryManager, Runtime, devices, providers, or env vars.
- Prompt redaction for API-key-like text must remain available.

## Forbidden scope

Do not modify:

agent/
runtime/
sessions/
providers/
devices/
tools/
memory/
demo/

Do not change existing task behavior.
Do not change SubAgent strategy or execution decisions.
Do not change final response generation.

## Tests

Add tests for:

- PromptFrame can be built from structured blocks.
- PromptEngine.build() still returns PromptBuildResult.
- PromptBuildResult.prompt is a string.
- context_keys remain deterministic.
- callers do not need to know block order or separators.
- redaction still removes API-key-like text.
- PromptFrame does not call LLMProvider or external runtime services.

Run:

python -m pytest tests/prompts/test_prompt_frame_contract.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(prompts): add prompt frame contract
```

---

## PR 2：SystemPrompt 双层结构

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 2: add dual-layer SystemPrompt templates.

Before making changes, read:

docs/prompt_prd.md
docs/tune.md
prompts/engine.py
prompts/templates.py

## Precondition

Prompt PR 1 must already be merged. Stop if PromptFrame or equivalent block support does not exist.

## Goal

Make SystemPrompt explicitly describe Ella's dual behavior: companionship/understanding and task execution/progression.

This PR only changes SystemPrompt content and its tests. It must not alter Runtime behavior or LLM call sites.

## Scope rule

Only implement Prompt PR 2.

SystemPrompt is a global behavior boundary. It must not become going_out-specific, tool-specific, provider-specific, or page-specific.

## Allowed files

Only create or modify:

prompts/templates.py
tests/prompts/test_system_prompt_templates.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update SystemPrompt templates so they clearly include:

- Ella is a long-term companion-style assistant.
- Ella is also a task execution/progression assistant.
- Ella dynamically shifts emphasis between understanding and execution.
- Companionship layer:
  - understand user emotion, tone, and ambiguity
  - communicate naturally and steadily
  - avoid exaggerated emotional dependency
- Execution layer:
  - identify user goals
  - decide whether work should be decomposed
  - use Skill and Tool only when helpful
  - report completion state and failure reasons clearly
- Safety and truthfulness:
  - do not fabricate facts, tool results, memory, visual evidence, audio evidence, or external API results
  - do not claim actions that were not performed
  - state uncertainty when needed

Requirements:

- SystemPrompt must not mention going_out as the default identity.
- SystemPrompt must not hardcode camera, microphone, Qwen, weather, checklist, or umbrella behavior.
- SystemPrompt must not include API keys, environment variables, local paths, provider credentials, or debug data.
- Existing PromptType templates may share the same SystemPrompt principles, but their output contracts remain separate.

## Forbidden scope

Do not modify:

agent/
runtime/
sessions/
providers/
devices/
tools/
memory/
demo/

Do not change PromptEngine.build() public API.
Do not implement Skill/Tool/Memory/WorkSpace blocks in this PR.

## Tests

Add tests for:

- SystemPrompt contains companionship/understanding guidance.
- SystemPrompt contains task execution/progression guidance.
- SystemPrompt contains truthfulness and safety limits.
- SystemPrompt is not going_out-specific.
- SystemPrompt does not mention provider credentials or local paths.
- PromptEngine output includes the SystemPrompt content for supported PromptTypes.

Run:

python -m pytest tests/prompts/test_system_prompt_templates.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(prompts): add dual-layer system prompt
```

---

## PR 3：Skill 与 Tool 通用限制 Prompt

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 3: add generic Skill and Tool policy prompt blocks.

Before making changes, read:

docs/prompt_prd.md
docs/pr_tool.md
docs/tune.md
prompts/engine.py
prompts/templates.py

## Preconditions

Prompt PR 1 and PR 2 must already be merged.

## Goal

Add generic Skill and Tool usage policy blocks to PromptEngine.

This PR must not include concrete visible Skill lists or concrete visible ToolDefinition lists in the Skill/Tool sections. Concrete available skills and tools belong to WorkSpace.

## Scope rule

Only implement Prompt PR 3.

Skill and Tool prompt sections are universal usage constraints, not runtime capability directories.

## Allowed files

Only create or modify:

prompts/templates.py
tests/prompts/test_skill_tool_policy_prompts.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add Skill policy content:

- Skill is behavior guidance, not an independent execution engine.
- Skill is not a fixed execution plan.
- Skill cannot bypass task permissions, ToolManager, CapabilityExecutor, or Runtime state.
- Skill is not selected during STRATEGY_SELECTION.
- If a scene needs Skill guidance, Skill may be adopted during EXECUTION_DECISION using visible skill data from WorkSpace.
- No suitable Skill does not mean task failure.

Add Tool policy content:

- Tool is optional capability, not a forced execution plan.
- Tool should be called only when useful for the current task.
- No suitable Tool does not mean task failure.
- Tool results are observations.
- Failed Tool results must not be treated as trusted facts.
- Tool input validation failure should become observation for a later decision, not an Executor-side LLM repair.
- First version allows one Tool action per EXECUTION_DECISION.
- Parallel Tool execution is a future capability, not current behavior.

Requirements:

- Do not list concrete skill names in Skill policy.
- Do not list concrete tool names in Tool policy.
- Do not include visible_skills or visible_tools here; those belong to WorkSpace.
- Do not hardcode going_out, camera_scene, mock_weather, mock_checklist, or umbrella.

## Forbidden scope

Do not modify:

agent/
runtime/
sessions/
providers/
devices/
tools/
memory/
demo/

Do not modify SkillManager or ToolManager.
Do not change SubAgent decision behavior.
Do not change Executor behavior.

## Tests

Add tests for:

- Skill policy says Skill is guidance, not execution engine.
- Skill policy says Skill is not selected during STRATEGY_SELECTION.
- Skill policy says no suitable Skill is not task failure.
- Tool policy says Tool is optional.
- Tool policy says no suitable Tool is not task failure.
- Tool policy says failed Tool results are observations, not trusted facts.
- Tool policy does not include concrete skill/tool names.
- Tool policy does not imply parallel execution is currently supported.

Run:

python -m pytest tests/prompts/test_skill_tool_policy_prompts.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(prompts): add skill and tool policy prompts
```

---

## PR 4：WorkSpace Prompt 上下文

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 4: add WorkSpace prompt context support.

Before making changes, read:

docs/prompt_prd.md
docs/pr_tool.md
docs/tune.md
prompts/engine.py
prompts/templates.py
agent/context.py
sessions/session.py

## Preconditions

Prompt PR 1 through PR 3 must already be merged.

## Goal

Make PromptEngine support WorkSpace as the single prompt location for current task state, observations, visible skills, and visible tools.

This PR only changes prompt composition and tests. It must not change Runtime state storage or execution behavior.

## Scope rule

Only implement Prompt PR 4.

WorkSpace is prompt context, not long-term memory and not the filesystem workspace.

## Allowed files

Only create or modify:

prompts/engine.py
prompts/templates.py
tests/prompts/test_workspace_prompt_context.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

PromptEngine should support a structured WorkSpace context containing:

- overall_goal
- current_goal
- step_list
- completed_steps
- current_step_state
- observations
- visible_skills
- visible_tools

WorkSpace visible_skills should be rendered from structured data containing safe summaries such as:

- name
- description
- use case summary
- failure notes
- tool references summary

WorkSpace visible_tools should be rendered from structured data containing safe ToolDefinition summaries such as:

- name
- description
- input_schema
- input_examples
- output_schema
- limitations

Requirements:

- WorkSpace rendering must be deterministic.
- WorkSpace must not include Tool instances.
- WorkSpace must not include provider credentials, API keys, authorization headers, raw media, local absolute sensitive paths, or internal class names.
- WorkSpace observations must include ToolResult summaries and failure observations when provided.
- WorkSpace must remain distinct from Memory.
- Skill and Tool policy sections must not duplicate visible_skills or visible_tools.

## Forbidden scope

Do not modify:

agent/
runtime/
sessions/
providers/
devices/
tools/
memory/
demo/

Do not change TaskSession fields.
Do not change ToolManager discovery.
Do not change SubAgent decisions.
Do not change Executor behavior.

## Tests

Add tests for:

- WorkSpace context renders overall_goal and current_goal.
- WorkSpace context renders observations.
- WorkSpace context renders visible_skills.
- WorkSpace context renders visible_tools with input_schema and examples.
- WorkSpace rendering excludes credentials, raw media, local paths, Tool instances, and internal class names.
- WorkSpace and Memory are rendered as distinct prompt sections.
- Skill/Tool policy sections do not duplicate visible runtime lists.

Run:

python -m pytest tests/prompts/test_workspace_prompt_context.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(prompts): add workspace prompt context
```

---

## PR 5：Strategy Selection 只选择执行模式

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 5: make Strategy Selection choose execution mode only.

Before making changes, read:

docs/prompt_prd.md
docs/architecture.md
docs/tune.md
prompts/engine.py
prompts/templates.py
sessions/subagent.py

## Preconditions

Prompt PR 1 through PR 4 must already be merged.

## Goal

Make STRATEGY_SELECTION decide only whether the task should use react or plan_and_execute mode.

It must not select Skill, return skill_name, call Tool, or produce an executable plan.

## Scope rule

Only implement Prompt PR 5.

This PR may adjust SubAgent strategy parsing only as needed to stop strategy selection from choosing Skill.

## Allowed files

Only create or modify:

prompts/templates.py
sessions/subagent.py
tests/prompts/test_strategy_selection_prompt.py
tests/sessions/test_strategy_selection_mode_only.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update STRATEGY_SELECTION prompt and parsing so output contract is:

- mode: "react" or "plan_and_execute"
- reason: string
- needs_decomposition: boolean
- plan_summary: string | null

Requirements:

- STRATEGY_SELECTION must not return skill_name.
- STRATEGY_SELECTION must not choose Skill.
- STRATEGY_SELECTION must not call Tool.
- STRATEGY_SELECTION must not output executable Tool calls.
- STRATEGY_SELECTION must not output detailed step execution as if completed.
- If Runtime does not support plan_and_execute yet, SubAgent should safely fall back to react mode.
- plan_and_execute is future capability and must not force a TaskRuntime rewrite in this PR.
- Existing select_strategy behavior should remain compatible with TaskRuntime.

## Forbidden scope

Do not modify:

runtime/
agent/
providers/
devices/
tools/
memory/
demo/

Do not implement plan_and_execute execution.
Do not modify TaskRuntime state machine.
Do not execute tools.
Do not implement Skill selection here.

## Tests

Add tests for:

- STRATEGY_SELECTION prompt says it only chooses execution mode.
- STRATEGY_SELECTION prompt does not ask for skill_name.
- SubAgent accepts react output.
- SubAgent safely handles plan_and_execute when runtime support is absent by falling back to react or returning a clear compatible strategy.
- SubAgent rejects or ignores skill_name if model returns it.
- Strategy selection does not execute tools.
- Strategy selection does not mutate TaskSession.
- python main.py remains runnable.

Run:

python -m pytest tests/prompts/test_strategy_selection_prompt.py
python -m pytest tests/sessions/test_strategy_selection_mode_only.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(prompts): make strategy selection mode-only
```

---

## PR 6：Execution Decision 使用 WorkSpace 选择 Skill 和 Tool

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 6: make Execution Decision use WorkSpace visible skills and tools.

Before making changes, read:

docs/prompt_prd.md
docs/pr_tool.md
docs/architecture.md
docs/tune.md
prompts/engine.py
prompts/templates.py
sessions/subagent.py
sessions/decision.py

## Preconditions

Prompt PR 1 through PR 5 must already be merged.

## Goal

Make EXECUTION_DECISION use WorkSpace as the source of visible Skill summaries, visible ToolDefinition summaries, and observations.

This PR only changes prompt context generation and SubAgent decision prompting/parsing. It must not execute tools or change Executor behavior.

## Scope rule

Only implement Prompt PR 6.

Skill may be adopted as guidance during EXECUTION_DECISION when useful, but Skill must not become a fixed execution plan.

## Allowed files

Only create or modify:

prompts/templates.py
sessions/subagent.py
tests/prompts/test_execution_decision_workspace_prompt.py
tests/sessions/test_execution_decision_workspace_context.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update EXECUTION_DECISION prompt so it:

- Uses SystemPrompt.
- Uses UserPrompt.
- Uses Skill Policy Block.
- Uses Tool Policy Block.
- Uses WorkSpace.
- Uses OutputContract.
- Reads concrete visible Skill summaries only from WorkSpace.
- Reads concrete visible ToolDefinition summaries only from WorkSpace.
- Reads observations only from WorkSpace.

Update SubAgent decision prompting so WorkSpace context includes:

- current goal / task goal
- visible skills from current task scope
- visible tools from current task scope
- previous tool results and failures as observations
- current step state when available

Requirements:

- EXECUTION_DECISION returns one action only.
- CALL_TOOL must include visible tool_name and arguments object.
- If no Tool is needed, model may return COMPLETE.
- If no Skill is needed, model may proceed without Skill.
- If observations are sufficient, model should return COMPLETE instead of repeating Tool calls.
- If Tool failed or visual information is insufficient, model should explain missing information rather than loop.
- Invalid JSON, unknown action, unknown Tool, or missing arguments must not execute Tool.
- SubAgent must not execute tools.
- SubAgent must not call ToolManager.execute.
- SubAgent must not write memory.

## Forbidden scope

Do not modify:

sessions/executor.py
runtime/
agent/
providers/
devices/
tools/
memory/
demo/

Do not implement provider-native tool calling.
Do not modify TaskRuntime state transitions.
Do not add a ReAct loop inside SubAgent.
Do not remove Executor validation.

## Tests

Add tests for:

- EXECUTION_DECISION prompt includes WorkSpace.
- visible skills are included through WorkSpace, not a separate Skill visible block.
- visible tools are included through WorkSpace with schema/examples.
- observations are included through WorkSpace.
- SubAgent can return COMPLETE when no tool is needed.
- SubAgent can return CALL_TOOL using a visible tool.
- SubAgent does not choose unknown tools.
- SubAgent does not repeat a tool when observation is already sufficient.
- SubAgent does not execute tools.
- python main.py remains runnable.

Run:

python -m pytest tests/prompts/test_execution_decision_workspace_prompt.py
python -m pytest tests/sessions/test_execution_decision_workspace_context.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(execution): use workspace for execution decisions
```

---

## PR 7：Task Formulation 只在目的不清晰时使用

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 7: gate Task Formulation to unclear user intent.

Before making changes, read:

docs/prompt_prd.md
docs/prd_2_1.md
docs/architecture.md
docs/tune.md
agent/formulation.py
agent/main_agent.py
prompts/engine.py

## Preconditions

Prompt PR 1 through PR 4 must already be merged.

## Goal

Prevent Ella from forcing every user input through task formulation.

Task Formulation should be used only when user intent is unclear, mixed, ambiguous, or needs conversion into an executable goal.

## Scope rule

Only implement Prompt PR 7.

This PR changes task formulation gating only. It must not change Tool execution, SubAgent execution decisions, TaskRuntime state transitions, or demo UI.

## Allowed files

Only create or modify:

agent/formulation.py
agent/main_agent.py
tests/agent/test_task_formulation_gating.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Add a deterministic first-pass intent clarity check or equivalent boundary so that:

- clear greetings do not become execution tasks.
- ordinary chat does not become execution tasks.
- simple Q&A does not become execution tasks.
- clear direct instructions can proceed without unnecessary formulation when enough information is present.
- ambiguous, mixed, or complex requests may use TASK_FORMULATION.

Requirements:

- TASK_FORMULATION prompt must not choose Skill.
- TASK_FORMULATION prompt must not choose Tool.
- TASK_FORMULATION prompt must not execute Tool.
- Existing deterministic fallback remains available.
- LLM provider failure must not break simple clear inputs.
- The final runtime still produces a user-visible response.

## Forbidden scope

Do not modify:

runtime/
sessions/
providers/
devices/
tools/
memory/
demo/
prompts/templates.py

Do not implement plan_and_execute.
Do not change Executor behavior.
Do not hardcode going_out as the default task.

## Tests

Add tests for:

- "你好" does not become "send a reminder" or another forced task goal.
- ordinary Q&A can bypass TASK_FORMULATION.
- clear direct instruction can proceed without unnecessary formulation.
- ambiguous request uses TASK_FORMULATION.
- TASK_FORMULATION does not choose Skill or Tool.
- provider failure falls back safely.
- no direct providers.qwen import.
- python main.py remains runnable.

Run:

python -m pytest tests/agent/test_task_formulation_gating.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(agent): gate task formulation by intent clarity
```

---

## PR 8：Final Response 使用 WorkSpace 与 Memory

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 8: generate final responses from WorkSpace and Memory context.

Before making changes, read:

docs/prompt_prd.md
doc/prd3.md
docs/tune.md
agent/final_response.py
prompts/engine.py
runtime/task_runtime.py

## Preconditions

Prompt PR 1 through PR 4 must already be merged.

## Goal

Ensure FINAL_RESPONSE prompts use UserPrompt, Memory summary, WorkSpace goal/state, completed steps, Tool result summaries, uncertainty, and failure notes.

This PR only changes final response prompt context preparation and tests. It must not execute tools or modify runtime orchestration.

## Scope rule

Only implement Prompt PR 8.

Final response generation should turn runtime results into a natural user-facing answer without exposing raw internal objects.

## Allowed files

Only create or modify:

agent/final_response.py
tests/agent/test_final_response_workspace_memory.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update FinalResponseGenerator context preparation so FINAL_RESPONSE receives:

- user input / transcript when available
- memory summary
- workspace overall goal
- completed steps
- tool results summary
- uncertainty and failure notes
- prompt output contract

Requirements:

- Final response prompt must not expose Python repr, internal JSON dumps, schema dumps, debug logs, or provider raw response text.
- If a tool result confirms a fact, final response should not ask the user to re-check that fact.
- If visual/tool evidence is unavailable or insufficient, final response should clearly state the limitation.
- Memory is background context and must not override current user input or current observations.
- Provider failure fallback must still be natural and must not return "Task completed: <goal>".

## Forbidden scope

Do not modify:

runtime/
sessions/
providers/
devices/
tools/
memory/
demo/
prompts/templates.py

Do not execute tools.
Do not change TaskRuntime state machine.
Do not write memory.

## Tests

Add tests for:

- FINAL_RESPONSE context includes user input.
- FINAL_RESPONSE context includes memory summary.
- FINAL_RESPONSE context includes WorkSpace goal/state.
- FINAL_RESPONSE context includes completed steps.
- FINAL_RESPONSE context includes tool result summaries.
- confirmed visual/tool facts are not repeated as unchecked reminders.
- unavailable evidence is stated as limitation.
- fallback does not start with "Task completed:".
- FinalResponseGenerator does not execute tools or write memory.

Run:

python -m pytest tests/agent/test_final_response_workspace_memory.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(agent): build final response from workspace and memory
```

---

## PR 9：页面展示实际 PromptFrame

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 9: display actual PromptFrame prompts in the local page.

Before making changes, read:

docs/prompt_prd.md
doc/prd3.md
docs/tune.md
demo/display_snapshot.py
demo/page_viewer.py
demo/web_ui.py
prompts/engine.py

## Preconditions

Prompt PR 1 through PR 8 should already be merged.

## Goal

Ensure local page display shows the actual prompt strings generated by PromptEngine and sent to LLMProvider.generate(prompt).

This PR only changes display data plumbing and page rendering. It must not alter Runtime execution, Tool execution, provider behavior, or Memory writes.

## Scope rule

Only implement Prompt PR 9.

The page is a viewer, not a Runtime.

## Allowed files

Only create or modify:

demo/display_snapshot.py
demo/page_viewer.py
demo/web_ui.py
tests/demo/test_prompt_display_contract.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Update display snapshot/page behavior so it can show:

- task_formulation prompt when used
- strategy_selection prompt when used
- execution_decision prompt when available
- final_response prompt

Requirements:

- Displayed prompt text must be the exact string returned by PromptEngine.build(...).prompt and passed to LLMProvider.generate(prompt).
- Prompt display must not be labeled Reasoning, Chain of Thought, or Model Thinking.
- Prompt display must use title "Prompt Sent to LLM".
- Prompt text must be redacted for API-key-like secrets.
- Page must not display hidden model reasoning.
- Page must not call LLMProvider, Tool, CameraProvider, MicrophoneProvider, MemoryManager, EventRuntime, or TaskRuntime directly.
- User/model-generated text rendered into HTML must be escaped.

## Forbidden scope

Do not modify:

runtime/
agent/
sessions/
providers/
devices/
tools/
memory/
prompts/

Do not implement live streaming.
Do not implement WebSocket.
Do not call devices or providers.
Do not change prompt generation behavior.

## Tests

Add tests for:

- page can display task_formulation prompt.
- page can display strategy_selection prompt.
- page can display execution_decision prompt.
- page can display final_response prompt.
- prompt section title is "Prompt Sent to LLM".
- page does not contain Reasoning, Chain of Thought, or Model Thinking labels.
- prompt text is HTML escaped.
- API-key-like values are redacted.
- page renderer does not call Runtime, providers, devices, tools, or memory.

Run:

python -m pytest tests/demo/test_prompt_display_contract.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): display actual prompts sent to llm
```

---

## PR 10：Prompt Engine 契约回归测试

```text
You are working in the Ella Runtime MVP repository.

Please implement Prompt PR 10: add Prompt Engine architecture contract tests.

Before making changes, read:

docs/prompt_prd.md
docs/architecture.md
docs/tune.md
prompts/engine.py
prompts/templates.py
sessions/subagent.py
agent/formulation.py
agent/final_response.py

## Preconditions

Prompt PR 1 through PR 9 should already be merged.

## Goal

Add contract tests that verify Prompt Engine boundaries and prevent regressions.

This PR should primarily add tests. It must not introduce new prompt behavior unless tests reveal a small documentation-aligned bug and the allowed files include the exact boundary.

## Scope rule

Only implement Prompt PR 10.

Prompt Engine must remain a prompt composition boundary, not a Runtime, executor, provider, memory manager, or page renderer.

## Allowed files

Only create or modify:

tests/contracts/test_prompt_engine_contract.py

Do not modify any other files.
Do not modify __init__.py.

If a contract test reveals a real production bug, stop and explain:

1. Which contract fails.
2. Why current behavior violates docs/prompt_prd.md.
3. Which future PR should fix it.

Do not fix production code in this PR.

## Implement tests

Add contract tests verifying:

- PromptEngine accepts structured context and outputs a string prompt.
- PromptEngine does not call LLMProvider.
- PromptEngine does not execute Tool.
- PromptEngine does not query or write Memory.
- PromptEngine does not access devices or providers.
- SystemPrompt is not going_out-specific.
- Skill prompt is generic policy only.
- Tool prompt is generic policy only.
- concrete visible skills are provided through WorkSpace.
- concrete visible ToolDefinitions are provided through WorkSpace.
- STRATEGY_SELECTION does not choose Skill or return skill_name.
- EXECUTION_DECISION returns only one action contract.
- no suitable Tool does not imply task failure.
- no suitable Skill does not imply task failure.
- Task Formulation is not required for clear greetings / simple Q&A.
- page prompt labels avoid Reasoning, Chain of Thought, and Model Thinking.
- Prompt output does not include API-key-like secrets.

Tests must not call real network, camera, microphone, or Qwen.

## Forbidden scope

Do not modify:

any production code
any existing tests
any documentation
any configuration file

Do not skip failing tests unless the skip explicitly documents a known future PR.

## Tests

Run:

python -m pytest tests/contracts/test_prompt_engine_contract.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What contract tests were added
3. What was intentionally not changed
4. Test results

PR title:

test(contracts): add prompt engine boundary contracts
```

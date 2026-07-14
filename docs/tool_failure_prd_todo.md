# Ella Tool Failure PRD Implementation Prompts

本文档依据 `docs/tool_failure_prd.md` 拆分实现步骤。以下每一节都是可以直接复制给
Codex 的单 PR 提示词。

执行规则：

- 每个 PR 只修改一个模块边界。
- 严格遵守每个 PR 的 allowed files。
- 每个 PR 合并后必须保持 `python -m pytest` 和 `python main.py` 可运行。
- 不得提前实现后续 PR。
- 如果前置条件不满足，停止并说明，不得通过临时硬编码绕过。

---

## PR 1：Tool Failure 与 Step 状态数据契约

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 1: add tool failure and step execution state contracts.

Before making changes, read:

docs/tool_failure_prd.md
docs/architecture.md
docs/tune.md
sessions/session.py
sessions/executor.py
tools/base.py

## Goal

Add immutable data contracts for normalized Tool failures and task-local logical Step state.

This PR only defines contracts. It must not wire them into TaskSession, CapabilityExecutor,
SubAgent, TaskRuntime, PromptEngine, FinalResponseGenerator, tools, or demo.

## Scope rule

Only implement Tool Failure PR 1.

## Allowed files

Only create or modify:

sessions/execution_state.py
tests/sessions/test_execution_state_contracts.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

Define:

- ToolFailureKind with:
  - INVALID_ARGUMENTS
  - INVALID_ARGUMENTS_REPAIR_VIOLATION
  - PERMISSION_DENIED
  - ENVIRONMENT_UNAVAILABLE
  - TOOL_EXECUTION_FAILED
- ToolFailureObservation with:
  - attempt_id
  - tool_name
  - kind
  - code
  - message
  - arguments
  - retryable
- StepExecutionState with:
  - step_number
  - retry_index
  - active_tool_name
  - blacklisted_tools
  - failures
  - derived attempt_id

Attempt ID rules:

- step 1 with retry_index=0 is `step1_try`
- step 1 with retry_index=1 is `step1_retry1`
- step 1 with retry_index=2 is `step1_retry2`

Requirements:

- Contracts should be frozen/immutable.
- Tuple fields must be deterministic.
- Mutable argument dictionaries must be defensively copied or exposed read-only.
- step_number must be at least 1.
- retry_index must be at least 0.
- active_tool_name may be null only when parameter repair is not active.
- No contract may contain Tool instances, providers, credentials, raw media, or Runtime services.
- Add deterministic to_dict() support if consistent with the repository style.

## Forbidden scope

Do not modify:

sessions/session.py
sessions/executor.py
sessions/subagent.py
runtime/
agent/
prompts/
tools/
providers/
devices/
memory/
demo/

Do not implement retries.
Do not classify existing ToolResult objects.
Do not change TaskRuntime loop behavior.

## Tests

Add tests for:

- every ToolFailureKind value.
- ToolFailureObservation construction and deterministic serialization.
- StepExecutionState default attempt ID.
- retry attempt ID generation.
- invalid step_number and retry_index rejection.
- tuple/dictionary state does not leak mutable shared data.
- contracts contain no Runtime or Tool instances.

Run:

python -m pytest tests/sessions/test_execution_state_contracts.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

feat(execution): add tool failure and step state contracts
```

---

## PR 2：TaskSession 持有隔离的 Step 状态

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 2: attach isolated StepExecutionState to TaskSession.

Before making changes, read:

docs/tool_failure_prd.md
docs/architecture.md
docs/tune.md
sessions/execution_state.py
sessions/session.py
sessions/session_manager.py

## Precondition

Tool Failure PR 1 must already be merged. Stop if StepExecutionState and
ToolFailureObservation do not exist.

## Goal

Make every TaskSession own an isolated current logical Step state and immutable completed
Step history.

This PR only changes the TaskSession state boundary. It must not implement retry policy,
Tool failure normalization, SubAgent behavior, Prompt changes, or Runtime loop changes.

## Allowed files

Only create or modify:

sessions/session.py
tests/sessions/test_task_step_state.py

Do not modify any other files.
Do not modify __init__.py.

## Implement

Add TaskSession fields:

- current_step: StepExecutionState
- step_history: tuple[StepExecutionState, ...]

Requirements:

- current_step starts at step1_try.
- Every TaskSession receives a distinct state instance.
- step_history defaults to an empty tuple.
- Existing task_local_state, tool_trace, state transitions, completion, and failure_reason
  remain compatible.
- TaskSession may expose small state replacement/archive helpers if needed, but these helpers
  must not decide retry policy.
- Session methods must not call SubAgent, Tool, Executor, PromptEngine, or TaskRuntime.
- Completed Step objects must not be mutated when a new Step is created.

## Forbidden scope

Do not modify:

sessions/executor.py
sessions/subagent.py
sessions/session_manager.py
runtime/
agent/
prompts/
tools/
providers/
devices/
memory/
demo/

Do not implement blacklist filtering.
Do not advance steps automatically from TaskSession.
Do not change Runtime state transitions.

## Tests

Add tests for:

- a new TaskSession starts at step1_try.
- two TaskSessions do not share current_step.
- failures and blacklist from one session do not appear in another.
- completed Step history is immutable.
- replacing current_step does not mutate archived history.
- existing TaskSession construction and state transitions remain compatible.

Run:

python -m pytest tests/sessions/test_task_step_state.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

feat(sessions): add isolated logical step state
```

---

## PR 3：CapabilityExecutor 统一失败归一化

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 3: normalize CapabilityExecutor failures.

Before making changes, read:

docs/tool_failure_prd.md
docs/architecture.md
docs/tune.md
sessions/execution_state.py
sessions/executor.py
sessions/session.py
tools/base.py
tools/camera_scene.py
tools/screen_scene.py

## Preconditions

Tool Failure PR 1 and PR 2 must already be merged.

## Goal

Make CapabilityExecutor return one normalized success or failure result for every Tool
execution attempt.

This PR only changes execution normalization. It must not implement retry orchestration,
step advancement, Prompt changes, SubAgent repair behavior, or final response behavior.

## Allowed files

Only create or modify:

sessions/executor.py
tests/sessions/test_capability_failure_normalization.py

Do not modify any other files.
Do not modify __init__.py.

## Implement

Extend CapabilityExecutionResult with:

- failure: ToolFailureObservation | None
- raw_result: Any | None

Enforce:

- success means tool_result is present and failure is absent.
- failure means tool_result is absent and failure is present.
- tool_result and failure must never both be present.

Normalize failures:

- invalid input schema or explicit argument constraint:
  - INVALID_ARGUMENTS
  - retryable=True
- task permission or role visibility rejection:
  - PERMISSION_DENIED
  - retryable=False
- missing/removed Tool, unavailable device/backend/file/network, device busy, or timeout:
  - ENVIRONMENT_UNAVAILABLE
  - retryable=False
- Tool exception, backend failure, provider internal error, or invalid output schema:
  - TOOL_EXECUTION_FAILED
  - retryable=False

Legacy normalization:

- If a Tool returns ToolResult payload with status="unavailable" or a failure error code,
  return tool_result=None and failure=ToolFailureObservation(...).
- Preserve the original ToolResult only in raw_result.
- A successful negative business result, such as no matching object being visible, remains
  a successful ToolResult.

Requirements:

- Executor still executes at most one Tool.
- Invalid input never calls Tool.
- Catch Tool exceptions so they do not crash Runtime.
- Executor must not mutate TaskSession, current_step, blacklist, retry counters, or history.
- Existing COMPLETE, WAIT, and REPLAN behavior remains non-executing.
- raw_result is diagnostic only and is not written anywhere by Executor.

## Forbidden scope

Do not modify:

sessions/execution_state.py
sessions/session.py
sessions/subagent.py
runtime/
agent/
prompts/
tools/
providers/
devices/
memory/
demo/

Do not retry Tool calls.
Do not advance logical Steps.
Do not write tool_trace.

## Tests

Add tests for:

- successful Tool returns tool_result and no failure.
- invalid input returns INVALID_ARGUMENTS and does not call Tool.
- permission rejection returns PERMISSION_DENIED.
- removed Tool returns ENVIRONMENT_UNAVAILABLE.
- status="unavailable" ToolResult is normalized into failure.
- permission_denied payload maps to PERMISSION_DENIED.
- backend_unavailable and timeout map to ENVIRONMENT_UNAVAILABLE.
- Tool exception maps to TOOL_EXECUTION_FAILED without escaping.
- invalid output schema maps to TOOL_EXECUTION_FAILED.
- negative successful business result remains ToolResult.
- success/failure mutual exclusion is enforced.
- raw_result is retained only for normalized legacy failure.
- Executor does not mutate TaskSession.

Run:

python -m pytest tests/sessions/test_capability_failure_normalization.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

refactor(execution): normalize tool execution failures
```

---

## PR 4：Tool 失败与参数修复 Prompt Policy

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 4: add tool failure and argument repair prompt policy.

Before making changes, read:

docs/tool_failure_prd.md
docs/prompt_prd.md
docs/tune.md
prompts/templates.py
prompts/engine.py
tools/camera_scene.py

## Preconditions

Tool Failure PR 1 through PR 3 must already be merged.

## Goal

Define model-facing policy for structured Tool failures, same-Tool argument repair, and
camera information insufficiency.

This PR only changes prompt and ToolDefinition text. It must not implement Runtime retry,
blacklist enforcement, SubAgent filtering, Tool execution, or camera capture behavior.

## Allowed files

Only create or modify:

prompts/templates.py
tools/camera_scene.py
tests/prompts/test_tool_failure_policy.py
tests/tools/test_camera_scene_retry_policy.py

Do not modify any other files.
Do not modify __init__.py.

## Implement

Update EXECUTION_DECISION policy so the model understands:

- ToolResult entries are successful business observations.
- ToolFailureObservation entries are failures and must not be treated as facts.
- INVALID_ARGUMENTS repair must regenerate arguments for active_tool_name only.
- Repair mode must not switch Tool, COMPLETE, WAIT, or REPLAN.
- blacklisted_tools must not be selected.
- permission, environment, and internal Tool failures must not be blindly retried.

Update CameraSceneTool ToolDefinition description and execution policy:

- If the current task already has one successful camera_scene observation, do not call
  camera_scene again.
- This remains true when the image does not contain the requested object.
- This remains true when the image is blurred, obstructed, poorly angled, or otherwise
  insufficient.
- Use the existing observation and explain what is visible, missing, or uncertain.
- The user may be asked to adjust the environment or provide information, but the agent must
  not automatically capture again.

Requirements:

- Prompt policy must not claim that Prompt alone enforces security.
- Prompt must not expose internal exceptions, credentials, local paths, or raw media.
- PromptEngine still only builds strings and does not execute Runtime behavior.
- CameraSceneTool capture implementation remains unchanged.

## Forbidden scope

Do not modify:

sessions/
runtime/
agent/
providers/
devices/
memory/
demo/

Do not implement retry counters.
Do not filter ToolDefinitions in code.
Do not add a visual sufficiency model.

## Tests

Add tests for:

- execution prompt distinguishes ToolResult and ToolFailureObservation.
- repair policy requires the same active Tool.
- repair policy forbids selecting blacklisted Tool names.
- camera ToolDefinition says successful insufficient observation must not trigger recapture.
- camera policy applies across logical Steps in the same task.
- camera policy asks the agent to report visible, missing, and uncertain information.
- PromptEngine remains side-effect free.

Run:

python -m pytest tests/prompts/test_tool_failure_policy.py
python -m pytest tests/tools/test_camera_scene_retry_policy.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

feat(prompts): add tool failure and repair policy
```

---

## PR 5：SubAgent 接收 Step 状态并约束决策

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 5: make SubAgent consume logical Step execution state.

Before making changes, read:

docs/tool_failure_prd.md
docs/prompt_prd.md
docs/tune.md
sessions/execution_state.py
sessions/session.py
sessions/subagent.py
prompts/templates.py
tools/manager.py

## Preconditions

Tool Failure PR 1 through PR 4 must already be merged.

## Goal

Expose Step state and failure observations to SubAgent, constrain argument repair to the
locked Tool, and prevent repeated camera capture after a successful observation.

This PR only changes the SubAgent decision boundary. It must not mutate Step state, consume
retry budgets, execute tools, or change TaskRuntime loops.

## Allowed files

Only create or modify:

sessions/subagent.py
tests/sessions/test_subagent_step_context.py

Do not modify any other files.
Do not modify __init__.py.

## Implement

Add current Step context to EXECUTION_DECISION WorkSpace:

- attempt_id
- retry_index
- active_tool_name
- repair_mode
- retries_remaining when supplied by Runtime state
- blacklisted_tools
- current Step failures
- historical Step failures

Observations must clearly separate:

- successful_tool_results from task_session.tool_trace
- failure_observations from current Step and completed Step history

Normal decision mode:

- Filter current Step blacklisted tools from visible ToolDefinition.
- If task_session.tool_trace already contains a successful camera_scene result, remove
  camera_scene from callable visible tools for the rest of the task.
- Existing successful camera observation remains in observations.

Repair mode:

- Only expose the ToolDefinition matching active_tool_name.
- Include previous invalid arguments and validation failure.
- Preserve enough raw decision information for TaskRuntime to detect a different tool_name.
- Do not execute or silently correct a switched Tool.
- A non-CALL_TOOL action, malformed arguments, missing Tool name, or different Tool name must
  remain detectable as a repair protocol violation by TaskRuntime.

Requirements:

- SubAgent still returns one ExecutionDecision per call.
- SubAgent must not mutate TaskSession or StepExecutionState.
- SubAgent must not execute Tool.
- No Tool instance enters Prompt context.
- Camera prevention must use successful tool_trace, not a failure observation.
- A camera permission failure must not be mistaken for a successful camera observation.

## Forbidden scope

Do not modify:

sessions/execution_state.py
sessions/session.py
sessions/executor.py
runtime/
agent/
prompts/
tools/
providers/
devices/
memory/
demo/

Do not consume retries.
Do not advance Steps.
Do not write blacklist state.

## Tests

Add tests for:

- current Step fields enter WorkSpace.
- successful and failed observations are separated.
- current Step blacklisted ToolDefinitions are hidden.
- repair mode exposes only active_tool_name ToolDefinition.
- previous invalid arguments and failure reason enter repair context.
- a switched Tool remains detectable and is not executed.
- successful camera_scene observation removes camera_scene from future callable definitions.
- insufficient camera information still prevents recapture.
- failed/unavailable camera observation does not count as successful capture.
- SubAgent returns one decision and does not mutate Session.

Run:

python -m pytest tests/sessions/test_subagent_step_context.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

refactor(execution): make subagent step-state aware
```

---

## PR 6：TaskRuntime 参数修复、Step 推进与双预算

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 6: orchestrate logical Step retries in TaskRuntime.

Before making changes, read:

docs/tool_failure_prd.md
docs/architecture.md
docs/tune.md
runtime/task_runtime.py
sessions/execution_state.py
sessions/session.py
sessions/subagent.py
sessions/executor.py

## Preconditions

Tool Failure PR 1 through PR 5 must already be merged.

## Goal

Make TaskRuntime own logical Step progression, same-Tool argument repair, Step blacklist
updates, and bounded run budgets.

This PR only changes TaskRuntime orchestration. It must not move retries into Executor or
SubAgent and must not change Tool implementations.

## Allowed files

Only create or modify:

runtime/task_runtime.py
tests/runtime/test_task_runtime_tool_retry.py
tests/runtime/test_task_runtime_step_budget.py

Do not modify any other files.
Do not modify __init__.py.

## Implement

Add TaskRuntime configuration:

- max_argument_retries defaults to 2.

Each TaskRuntime.step() call remains one attempt:

- call SubAgent once.
- execute at most one Tool.
- never loop internally.

Argument failure flow:

- First INVALID_ARGUMENTS locks active_tool_name.
- Record failure on current Step.
- If retry_index is below max_argument_retries, increment retry_index and remain RUNNING.
- Do not enter REPLANNING for parameter repair.
- Retry attempt IDs must be stepN_retry1 and stepN_retry2.

Repair binding:

- During repair, CALL_TOOL must use active_tool_name.
- A different tool_name must not reach Executor.
- A different tool_name records INVALID_ARGUMENTS_REPAIR_VIOLATION.
- Illegal JSON normalized by SubAgent, non-CALL_TOOL action, missing Tool, missing/malformed
  arguments, or switched Tool consumes one repair opportunity.
- active_tool_name remains locked after a repair violation.
- When retry2 fails or violates repair protocol, blacklist active_tool_name for the completed
  Step, record parameter_generation_failed, archive the Step, and create the next Step.

Non-retry failures:

- PERMISSION_DENIED, ENVIRONMENT_UNAVAILABLE, and TOOL_EXECUTION_FAILED are recorded.
- Add the Tool to current Step blacklist.
- Archive the Step and create the next Step.
- Do not append failure raw_result to tool_trace.

Success:

- Append only successful ToolResult to tool_trace.
- Archive current Step and create the next Step.

Action behavior:

- COMPLETE and WAIT resolve/archive the current Step.
- Explicit REPLAN does not increment retry_index or logical Step number.
- Parameter repair never transitions Session to REPLANNING.

Budgets:

- max_steps limits resolved logical Steps, not raw TaskRuntime.step() calls.
- max_argument_retries independently limits parameter repair.
- Add a deterministic internal hard iteration cap covering lifecycle transitions, retries,
  and repeated REPLAN.
- TaskRuntimeResult.steps remains the number of TaskRuntime.step() calls.
- Add logical_steps or an equivalent result field without changing existing steps meaning.
- max_steps and internal cap must return clear, distinct stop reasons.

Compatibility:

- Existing callers of run_until_blocked(task_id, max_steps) and
  run_until_complete(task_id, max_steps) remain source compatible.
- Existing state machine transitions remain valid.
- No memory write occurs before completion.

## Forbidden scope

Do not modify:

sessions/
agent/
prompts/
tools/
providers/
devices/
memory/
demo/

Do not add an Executor loop.
Do not execute multiple Tools per TaskRuntime.step().
Do not store raw_result in Session.

## Tests

Add tests for:

- step1_try invalid arguments becomes step1_retry1.
- step1_retry1 failure becomes step1_retry2.
- retry2 failure exhausts repair and advances to step2_try.
- active_tool_name is locked on first argument failure.
- switched Tool produces INVALID_ARGUMENTS_REPAIR_VIOLATION.
- switched Tool never reaches Executor.
- repair violation consumes retry and keeps active_tool_name.
- permission/environment/internal failure does not retry.
- only successful ToolResult enters tool_trace.
- failed legacy raw_result is not stored.
- successful Tool advances logical Step.
- explicit REPLAN does not consume argument retry.
- max_steps limits logical Steps.
- internal hard cap prevents infinite REPLAN.
- TaskRuntimeResult.steps remains raw call count.
- logical step count is separately reported.
- two tasks do not share retry or blacklist state.

Run:

python -m pytest tests/runtime/test_task_runtime_tool_retry.py
python -m pytest tests/runtime/test_task_runtime_step_budget.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

feat(runtime): orchestrate bounded tool argument repair
```

---

## PR 7：最终回答接收结构化 Tool 失败

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 7: include normalized Tool failures in final responses.

Before making changes, read:

docs/tool_failure_prd.md
docs/prompt_prd.md
docs/tune.md
agent/final_response.py
runtime/task_runtime.py
sessions/execution_state.py
prompts/templates.py

## Preconditions

Tool Failure PR 1 through PR 6 must already be merged.

## Goal

Make final user-visible responses explain normalized Tool failures and parameter repair
exhaustion without exposing internal diagnostics.

This PR only changes completion context and final response generation. It must not change
retry policy, Step progression, Tool execution, or SubAgent decisions.

## Allowed files

Only create or modify:

agent/final_response.py
runtime/task_runtime.py
tests/agent/test_final_response_tool_failures.py
tests/runtime/test_task_runtime_failure_response.py

Do not modify any other files.
Do not modify __init__.py.

## Implement

Extend FinalResponseGenerator input with normalized failure observations.

Prompt context should include a user-safe failure summary:

- Tool name.
- failure kind.
- safe message.
- attempt count/retry exhaustion.
- whether the failure was retryable.

Requirements:

- TaskRuntime gathers failures from current/completed Step history.
- Runtime passes only normalized ToolFailureObservation data.
- raw_result must not enter final response context.
- API keys, local paths, raw media, stack traces, and credentials must not appear.
- Permission failure should explain that permission is missing.
- Environment failure should explain the unavailable dependency.
- Parameter retry exhaustion should explain that valid arguments could not be generated after
  the configured attempts.
- Camera successful-but-insufficient observation must be described as information
  insufficiency, not Tool failure.
- Deterministic fallback must also mention the blocking reason.
- Existing successful final response behavior remains compatible.

## Forbidden scope

Do not modify:

sessions/
prompts/
tools/
providers/
devices/
memory/
demo/

Do not change retry counters.
Do not change Task state transitions.
Do not expose raw_result.

## Tests

Add tests for:

- permission failure becomes a user-readable explanation.
- environment unavailable becomes a user-readable explanation.
- parameter retry exhaustion reports the failed repair.
- internal Tool failure does not expose stack trace.
- raw_result does not enter Prompt or final answer.
- successful ToolResult remains separate from failures.
- camera information insufficiency is not labeled as execution failure.
- deterministic fallback includes safe blocking reason.
- CompletionPackage still contains only successful ToolResult entries.

Run:

python -m pytest tests/agent/test_final_response_tool_failures.py
python -m pytest tests/runtime/test_task_runtime_failure_response.py
python -m pytest
python main.py

## Final response

Include changed files, implementation summary, intentionally excluded work, and exact test results.

PR title:

feat(agent): explain normalized tool failures
```

---

## PR 8：Tool Failure 架构契约回归

```text
You are working in the Ella Runtime MVP repository.

Please implement Tool Failure PR 8: add tool failure handling contract regression tests.

Before making changes, read:

docs/tool_failure_prd.md
docs/architecture.md
docs/tune.md
sessions/execution_state.py
sessions/executor.py
sessions/subagent.py
runtime/task_runtime.py
agent/final_response.py
tools/camera_scene.py

## Preconditions

Tool Failure PR 1 through PR 7 must already be merged.

Stop if any of these are false:

- CapabilityExecutor normalizes every failure.
- TaskSession owns isolated Step state.
- TaskRuntime controls retry and Step progression.
- SubAgent receives failure observations.
- final response receives normalized failures.
- camera successful information insufficiency prevents recapture.

## Goal

Add final architecture contract tests for Tool failure normalization, bounded argument repair,
task isolation, and camera non-recapture behavior.

This PR is test-only. Do not modify production code.

## Allowed files

Only create:

tests/contracts/test_tool_failure_runtime_contract.py

Do not modify any other files.
Do not modify existing tests.
Do not modify __init__.py.

If a contract fails because production behavior is incomplete, stop and explain the failing
contract and the required future fix. Do not fix production code in this PR.

## Contract tests

Verify:

- Every failure produces failure and no successful tool_result.
- Every success produces tool_result and no failure.
- Legacy status="unavailable" is normalized.
- raw_result never enters Session, Prompt, CompletionPackage, Memory, or user-visible output.
- parameter repair binds active_tool_name.
- switched Tool records INVALID_ARGUMENTS_REPAIR_VIOLATION and is not executed.
- initial attempt plus two retries is the maximum.
- permission, environment, and internal failures do not retry in the current Step.
- tool_trace contains only successful ToolResult entries.
- failure observations remain available to later decisions.
- current Step blacklist does not leak across tasks.
- Step state and history do not leak across tasks.
- max_steps and max_argument_retries are independent.
- repeated REPLAN is bounded.
- successful camera_scene observation prevents all later automatic camera_scene calls in the
  same task, including when the image is insufficient.
- failed camera attempt does not count as successful observation.
- final user response explains blocking failures safely.
- python main.py remains runnable.

Tests must not access real network, camera, microphone, screen capture, or external APIs.

## Tests

Run:

python -m pytest tests/contracts/test_tool_failure_runtime_contract.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. Contracts added
3. What was intentionally not changed
4. Exact test results

PR title:

test(contracts): add tool failure runtime contracts
```

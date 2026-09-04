> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# PRD: Progressive Intent Formation and User Clarification

## 1. Background

Ella currently uses `task.intent is None` for two different meanings:

- the Task has not completed its First Decision;
- the model could not yet describe the user's overall goal.

This coupling can repeat First Decision after `ask_user_question` succeeds. The
answer is already present in `tool_trace`, but Runtime sees an empty Intent and
runs First Decision again, allowing the model to ask the same question twice.

## 2. Goal

Separate the user's overall Intent from Runtime execution phase.

Intent describes the overall outcome the user wants. It is not a container for
domain-specific execution parameters. First Decision completion is an explicit,
checkpointed Task fact and does not depend on whether Intent fields are empty.

## 3. Core Principles

1. First Decision must produce the best meaningful Intent available from a
   non-empty user request.
2. Missing execution details do not make Intent null. For example, a restaurant
   location may be missing while the Intent remains "book dinner tonight".
3. When the overall purpose is vague, First Decision produces a weak but honest
   goal and may call `ask_user_question` to refine it.
4. First Decision completion is stored independently from Intent.
5. `ask_user_question` only returns the questions and user answers as a
   `ToolResult`. The result becomes a normal persisted observation.
   Returned answers are direct user-provided information for the Task identified
   by `task_id`; the next decision must not dismiss them as another execution
   context or immediately repeat the same questions merely for confirmation.
6. Runtime does not select a current or latest answer. Multiple question results
   remain independent observations for the model to interpret in context.
7. The same question may be asked in a later phase because the user's answer may
   have changed. This PR does not add a duplicate-question rejection policy.
8. A user question contains one to three options. One recommended option is
   preferred but optional; more than one recommended option is invalid.

## 4. Data Contract

### 4.1 Task Intent

The current `TaskIntent` remains the formulation contract:

- `goal`: overall user outcome;
- `constraints`: explicit task restrictions;
- `deliverables`: requested outputs;
- `minimum_acceptance_criteria`: smallest observable completion conditions.

Execution slots such as location, party size, file path, or cuisine are not
added to Intent as a generic field map. They may remain in user input and Tool
observations until Reasoning uses them.

### 4.2 First Decision Completion

`Task` stores:

```text
first_decision_completed: bool
```

It is false when a raw Task is created and becomes true after one valid First
Decision has produced and committed Intent and one action. Checkpoints persist
this field. Runtime selects First Decision from this field, not from
`task.intent is None`.

### 4.3 User Question Result

Each answer includes at least:

```text
question_id
question
task_id
user_id
answer
metadata
```

The complete ToolResult is appended to `tool_trace` before Runtime honors a
pause or kill request that arrived while the interaction Tool was running.

## 5. Runtime Flow

```text
Raw user input
  -> First Decision
  -> commit non-empty Intent
  -> mark first_decision_completed
  -> CALL_TOOL ask_user_question when execution information is missing
  -> persist question/answer ToolResult as observation
  -> next Runtime step uses Execution Decision
  -> model consumes Intent and all observations
```

A successful interaction never sends the Task back to First Decision solely
because more task details were needed.

## 6. Prompt Requirements

First Decision must:

- always return an Intent object for non-empty input;
- describe the overall outcome rather than execution slots;
- distinguish an unclear goal from missing execution information;
- use a weak, honest goal when the request is genuinely vague;
- call `ask_user_question` when user-only information is required;
- avoid treating missing parameters as evidence that no Intent exists.

Execution Decision continues receiving persisted observations. This PR does not
add an answer projection or change Prompt block ordering.

## 7. Recovery

Checkpoint restoration must preserve:

- the committed Intent;
- `first_decision_completed`;
- `tool_trace`, including question and answer content;
- the existing Task execution state.

Restoring a Task after a completed First Decision must not rerun First Decision.
Legacy checkpoint migration is out of scope.

## 8. Non-goals

- Domain-specific Intent schemas or slot registries.
- A current/latest-answer projection.
- Automatic Intent mutation from Tool results.
- Semantic duplicate-question detection.
- Preventing the same question in a later execution phase.
- Changing TaskGraph, Verification, Tool retry, or Prompt block ordering.

## 9. Acceptance Criteria

- A missing restaurant location does not require `intent=null`.
- A valid First Decision always commits a non-empty Intent.
- Runtime records First Decision completion independently.
- After `ask_user_question` returns, the next decision uses Execution Decision.
- The next decision receives question text and answer content in observations.
- Checkpoint round-trip preserves First Decision completion.
- Existing pause, resume, kill, Tool execution, and Verification behavior remains
  unchanged.

# Ella Single-Feature PR Prompt

## Role

You are working in the Ella Runtime MVP repository.

Implement exactly one feature, one refactor target, or one test target:

```text
<PR_TITLE>
```

Do not broaden the task beyond this single purpose.

## Repository Context

Before changing code, read the relevant project sources of truth:

```text
docs/prd.md
docs/architecture.md
docs/pr_plan.md
```

Then inspect the current repository state, relevant production modules, existing tests, and recent commits.

Confirm that the requested work has not already been implemented. If it is complete, outdated, duplicated by a merged PR, or conflicts with the current repository, stop and explain instead of rewriting it.

Use `docs/pr_plan.md` as the direct implementation boundary when the target corresponds to a planned PR. Architecture describes the long-term design; it does not authorize implementing future work early.

## PR Target

### Title

```text
<PR_TITLE>
```

### Goal

```text
<PR_GOAL>
```

Before editing, state the PR's single purpose in one sentence. If the request contains multiple independent features, refactors, or test targets, stop and propose how to split them into separate PRs.

## Scope Rule

This PR must do exactly one thing:

```text
One PR = one feature, one refactor target, or one test target.
```

- Implement only `<PR_GOAL>`.
- Do not implement later PRs or adjacent features.
- Do not perform unrelated cleanup or opportunistic refactors.
- Do not redesign existing architecture unless `<PR_GOAL>` explicitly names that refactor.
- Do not add placeholders, speculative abstractions, or TODO-heavy stubs for future work.
- Preserve existing behavior outside the declared target.

## Allowed Files

Only create or modify these files:

```text
<ALLOWED_FILES>
```

Before editing, verify that every planned change fits this list.

Do not modify any other file. If another file appears necessary:

1. Stop before changing it.
2. Name the file.
3. Explain why the PR cannot be completed without it.
4. Explain whether the work should be split into another PR.

Do not silently expand the allowed file list.

## Forbidden Scope

Do not implement or modify:

```text
<FORBIDDEN_SCOPE>
```

Also forbidden unless explicitly included in `<PR_GOAL>` and `<ALLOWED_FILES>`:

- Future PR behavior.
- Unrelated modules or tests.
- Real external integrations.
- Broad repository restructuring.
- Dependency upgrades or configuration churn.
- API changes outside the target boundary.
- Reformatting or renaming unrelated code.

## Implementation Rules

- Follow existing repository patterns and public contracts.
- Keep the implementation minimal and directly tied to `<PR_GOAL>`.
- Add or update only tests that verify this PR's behavior.
- Prefer behavior-focused tests over implementation-detail assertions.
- Keep runtime boundaries explicit: task data may flow through contexts and requests, while application-level services or registries remain owned by their modules.
- Do not weaken, delete, or skip existing tests to make the change pass.
- Do not modify production code when the PR is test-only.
- Do not modify tests when the PR explicitly permits production files only.
- Keep `main` runnable and preserve the established CLI demo unless the PR explicitly targets it.
- Work with existing user changes; do not revert unrelated work.

## Testing Requirements

Run the PR-specific commands:

```bash
<TARGETED_TEST_COMMANDS>
```

Then run the full verification commands:

```bash
python -m pytest
python main.py
```

Report the exact pass/fail result for every command. Do not claim success if a command was not run or did not pass.

If a failure is unrelated to this PR, report it clearly and do not modify out-of-scope files to hide it.

## Final Response Requirements

The final response must include:

1. Changed files.
2. What was implemented.
3. What was intentionally excluded.
4. Targeted test results.
5. Full `python -m pytest` result.
6. `python main.py` result.
7. Confirmation that only allowed files were changed.
8. Confirmation that the branch remains runnable and testable.

If the work could not be completed within scope, explain the blocker and the additional file or separate PR required. Do not describe incomplete work as finished.

## PR Description Requirements

Prepare the PR summary using this structure:

### Title

```text
<PR_TITLE>
```

### Feature Description

Explain the single capability, refactor, or test target delivered by this PR.

### Implementation Approach

Explain the minimal implementation and its module boundaries. Do not claim that excluded or future behavior was implemented.

### Test Method

List the targeted tests, full test suite, and `python main.py` commands that were run.

### Intentionally Excluded

List `<FORBIDDEN_SCOPE>` and any adjacent work deliberately left for later PRs.

### Main Branch Runnable Check

Confirm that after merging this PR, the main branch remains runnable and testable and the existing demo still works unless the PR explicitly changes that demo.

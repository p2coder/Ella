# Ella TODO

## Deferred: Role-Based Capability Visibility

Status: deferred for the current demo phase.

For the MVP demo, it is acceptable to keep the current explicit tool allowlist used by
`TaskSessionManager` setup. This keeps the demo focused on proving the main runtime
path:

```text
EventRuntime
→ TaskRuntime
→ SubAgent
→ CapabilityExecutor
→ mock tools
→ TaskCompletionPackage
→ MemoryManager
```

The capability governance layer should be revisited before connecting real models,
real camera/microphone input, user-installable skills/tools, or multiple agent roles.

Target direction:

- Agents have stable role codes, such as `main_agent`, `task_agent`, or future
  specialized agent roles.
- Skills and tools declare which agent roles may use them.
- `SkillManager` and `ToolManager` remain process-level capability directories.
- Managers filter visible capabilities by the current `AgentExecutionContext`.
- `AgentExecutionContext` remains the task-local effective permission boundary.
- Newly submitted tasks can see capabilities currently registered and allowed for
  their agent role.
- Capabilities added after session creation must not automatically bypass that
  session's permission scope.
- Capabilities removed at runtime must be rejected before the next execution or
  replan step.

Suggested future PR sequence:

1. Add role-based visibility metadata for tools.
   - Modify only `tools/base.py`, `tools/manager.py`, `tools/mock_tools.py`, and
     focused tool tests.
   - Do not modify skill, session, runtime, or demo code.

2. Add role-based visibility metadata for skills.
   - Modify only skill manager/registry files and focused skill tests.
   - Do not modify runtime, session, or demo code.

3. Extend `AgentExecutionContext` with task-local capability scope.
   - Keep the context as the boundary for what one task may use.
   - Preserve existing context propagation behavior.

4. Move capability snapshot creation into `TaskSessionManager`.
   - Resolve visible skills/tools from the current managers when a session context
     is created.
   - Do not let `TaskRuntime` own or define capability permissions.

5. Remove hard-coded demo tool names.
   - Update demo assembly only after the manager/context/session boundaries are in
     place.
   - Keep `python main.py` output behavior stable.

This is intentionally not part of the immediate demo work. Treat it as an
architecture cleanup milestone, not a blocker for validating the current user
experience.

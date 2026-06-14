# Ella PRD 4 Implementation Prompts

以下每一节都是可以直接复制给 Codex 的单 PR 提示词。每个 PR 只做一件事，必须严格遵守 allowed files，不要提前实现后续 PR。

---

## PR 4.1：本地 Web UI Shell

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 4.1: add local interactive web UI shell.

Before making changes, read:

doc/pr4.md
doc/prd3.md
docs/prd_2_1.md
docs/tune.md
demo/page_viewer.py
demo/display_snapshot.py

## Goal

Add a local web UI shell that can render input, vision, prompt, agent, and answer sections.

This PR only creates the UI shell. It must not run Runtime, call providers, call devices, execute tools, or write memory.

## Scope rule

Only implement PR 4.1.

The Web UI is display and input surface only. It must not become a new Runtime.

## Allowed files

Only create or modify:

demo/web_ui.py
demo/static/web_ui.html
tests/demo/test_web_ui_shell.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

- Add a local HTML UI shell with:
  - text input area
  - submit button placeholder
  - Input section
  - Vision section
  - Prompt Sent to LLM section
  - Agent section
  - Answer section
- Add a renderer boundary that can render empty initial state or a provided RunDisplaySnapshot.
- All user-controlled or model-generated text rendered into HTML must be escaped.
- The prompt section title must be `Prompt Sent to LLM`.
- The UI must not label prompt text as `Reasoning`, `Chain of Thought`, or `Model Thinking`.
- The UI must not access camera, microphone, network, provider, tool, runtime, or memory.

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

Do not implement text submit behavior yet.
Do not create AppRuntime.
Do not access real devices.
Do not call LLM.
Do not create TaskSession.
Do not implement WebSocket, streaming, or concurrent tasks.

## Tests

Add tests for:

- Web UI shell renders required sections.
- Text input and submit button placeholder are present.
- Prompt section is titled `Prompt Sent to LLM`.
- Page does not contain `Reasoning`, `Chain of Thought`, or `Model Thinking`.
- User/model text is HTML escaped.
- Renderer does not call Runtime, providers, devices, tools, or memory.

Run:

python -m pytest tests/demo/test_web_ui_shell.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): add local web ui shell
```

---

## PR 4.2：抽出 AppRuntime Facade

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 4.2: extract minimal AppRuntime facade.

Before making changes, read:

doc/pr4.md
doc/prd3.md
docs/prd_2_1.md
docs/tune.md
demo/cli_demo.py

## Precondition

PRD 3 must already be merged. Stop if RunDisplaySnapshot, LocalPageViewer, PromptEngine, or FinalResponseGenerator is missing.

## Goal

Extract a thin application facade that CLI and Web UI can share.

The facade should be the only application-level entrypoint Web UI needs later.

## Scope rule

Only implement PR 4.2.

This PR may adapt CLI demo to call the facade, but it must not change Runtime internals or implement Web UI submit behavior.

## Allowed files

Only create or modify:

demo/app_runtime.py
demo/cli_demo.py
tests/demo/test_app_runtime_facade.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

- Add AppRuntime or equivalent thin facade.
- Provide `create_default()`.
- Provide `run_text_with_display(text)`.
- The facade may reuse current DemoRuntime assembly.
- `run_text_with_display(text)` should return existing display/result data suitable for Web UI.
- CLI demo may call the facade instead of owning all text-run logic directly.
- Preserve existing `python main.py` behavior.
- Preserve visible CLI output shape.
- Do not expose EventRuntime, TaskRuntime, managers, providers, devices, tools, or memory as Web UI-facing concepts.

## Forbidden scope

Do not modify:

runtime/
agent/
sessions/
providers/
devices/
tools/
memory/
demo/web_ui.py

Do not implement Web UI submit behavior.
Do not change EventRuntime or TaskRuntime internals.
Do not change SubAgent decisions.
Do not change provider/device behavior.
Do not add new tools.
Do not implement WebSocket, streaming, or concurrent tasks.

## Tests

Add tests for:

- AppRuntime can be created with default assembly.
- AppRuntime exposes `run_text_with_display(text)`.
- AppRuntime returns a RunDisplaySnapshot-compatible result.
- CLI demo can still run through the facade.
- `python main.py` remains runnable.
- AppRuntime does not bypass EventRuntime or TaskRuntime.
- Web UI is not modified in this PR.

Run:

python -m pytest tests/demo/test_app_runtime_facade.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

refactor(demo): extract shared app runtime facade
```

---

## PR 4.3：Web UI 通过 AppRuntime 提交文本

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 4.3: submit Web UI text through AppRuntime.

Before making changes, read:

doc/pr4.md
doc/prd3.md
docs/tune.md
demo/web_ui.py
demo/app_runtime.py

## Precondition

PR 4.1 and PR 4.2 must already be merged.

Stop if:

- the local Web UI shell does not exist
- AppRuntime does not exist
- AppRuntime does not expose `run_text_with_display(text)`

## Goal

Allow the local Web UI to submit one text input through AppRuntime and render the returned RunDisplaySnapshot.

## Scope rule

Only implement PR 4.3.

The Web UI must call AppRuntime only. It must not know or call Runtime internals.

## Allowed files

Only create or modify:

demo/web_ui.py
demo/static/web_ui.html
tests/demo/test_web_ui_text_submit.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

- Add a thin local request handler or callable API for text submission.
- The handler should call only `AppRuntime.run_text_with_display(text)`.
- Return or render RunDisplaySnapshot data.
- Default local server binding must be `127.0.0.1`.
- Do not default bind to `0.0.0.0`.
- HTML output must escape user input, prompt text, tool summaries, scene summaries, and final responses.
- First version may synchronously wait for task completion.
- Preserve existing CLI demo behavior.

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
demo/app_runtime.py

Do not directly call EventRuntime.
Do not directly call TaskRuntime.
Do not directly create TaskSession.
Do not directly select skill.
Do not directly call tools.
Do not directly call LLMProvider.
Do not directly write memory.
Do not implement camera frame display yet.
Do not introduce WebSocket, streaming, or concurrent scheduling.

## Tests

Add tests for:

- Web UI submits text through AppRuntime.
- Web UI does not directly call EventRuntime or TaskRuntime.
- Web UI does not directly call tools, LLMProvider, TaskSession, or MemoryManager.
- Returned snapshot data is rendered.
- Default binding is `127.0.0.1`.
- `0.0.0.0` is not the default binding.
- User/model-generated output is HTML escaped.
- CLI demo still works.

Run:

python -m pytest tests/demo/test_web_ui_text_submit.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): submit web ui text through app runtime
```

---

## PR 4.4：RunDisplaySnapshot 支持捕获画面展示数据

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 4.4: add captured frame display data to RunDisplaySnapshot.

Before making changes, read:

doc/pr4.md
doc/prd3.md
docs/tune.md
demo/display_snapshot.py
tools/camera_scene.py
sessions/completion.py

## Goal

Allow RunDisplaySnapshot to carry safe captured frame display data or references produced by the runtime/tool-result path.

This PR only changes display data contracts. It must not make the page or browser open the camera.

## Scope rule

Only implement PR 4.4.

Snapshot is display data only. It must not call Runtime, providers, devices, tools, or memory.

## Allowed files

Only create or modify:

demo/display_snapshot.py
tests/demo/test_display_snapshot_frame.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

- Add display-safe captured frame field(s), such as data URI or safe relative reference.
- Preserve existing snapshot fields and serialization behavior.
- Serialization must remain deterministic.
- If no frame exists, image_status should remain camera unavailable, mock image, or text-only.
- Raw media must not be stored unless existing settings explicitly allow it.
- Accept only safe image references:
  - `data:image/...;base64,...`
  - or controlled relative paths under the display output area
- Reject or sanitize:
  - `file://...`
  - absolute paths
  - `../` path traversal
  - arbitrary local file reads

## Forbidden scope

Do not modify:

tools/
runtime/
agent/
sessions/
providers/
devices/
memory/
demo/web_ui.py
demo/cli_demo.py
demo/app_runtime.py

Do not access camera.
Do not call CameraSceneTool.
Do not add real provider behavior.
Do not implement Web UI display changes.

## Tests

Add tests for:

- snapshot can carry safe data URI frame data.
- snapshot can carry safe relative frame references if supported.
- unsafe `file://` references are rejected or sanitized.
- absolute paths are rejected or sanitized.
- `../` path traversal is rejected or sanitized.
- serialization remains deterministic.
- snapshot does not call Runtime, providers, devices, tools, or memory.

Run:

python -m pytest tests/demo/test_display_snapshot_frame.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): add captured frame display data
```

---

## PR 4.5：Web UI 展示摄像头捕获画面

```text
You are working in the Ella Runtime MVP repository.

Please implement PR 4.5: display captured camera frame in local Web UI.

Before making changes, read:

doc/pr4.md
doc/prd3.md
docs/tune.md
demo/web_ui.py
demo/display_snapshot.py

## Precondition

PR 4.4 must already be merged. Stop if RunDisplaySnapshot cannot carry safe captured frame display data.

## Goal

Render captured frame data or safe frame placeholders from RunDisplaySnapshot in the local Web UI.

## Scope rule

Only implement PR 4.5.

The Web UI must display snapshot data only. It must not open the camera or call CameraSceneTool.

## Allowed files

Only create or modify:

demo/web_ui.py
demo/static/web_ui.html
tests/demo/test_web_ui_frame_display.py

Do not modify any other files.
Do not modify __init__.py.

If another file appears necessary, stop and explain why before changing it.

## Implement

- Show captured frame when snapshot includes safe frame data or reference.
- Show clear image_status when frame is missing.
- Show scene summary near the frame.
- Show visible items near the frame.
- Escape all text rendered into HTML.
- Do not use browser camera APIs.
- Do not request camera permission from the browser.
- Do not call CameraSceneTool.
- Do not call CameraProvider.
- Do not call providers or devices.

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
demo/app_runtime.py
demo/display_snapshot.py

Do not implement live camera streaming.
Do not implement WebSocket.
Do not change Runtime behavior.
Do not change snapshot contract.

## Tests

Add tests for:

- Web UI renders safe captured frame data.
- Web UI renders safe captured frame reference if supported.
- Web UI shows image_status when no frame exists.
- Web UI shows scene summary and visible items.
- Web UI escapes text.
- Web UI does not request browser camera permission.
- Web UI does not call CameraSceneTool, CameraProvider, providers, or devices.

Run:

python -m pytest tests/demo/test_web_ui_frame_display.py
python -m pytest
python main.py

## Final response

Include:

1. Changed files
2. What was implemented
3. What was intentionally not implemented
4. Test results

PR title:

feat(demo): show captured frame in local web ui
```

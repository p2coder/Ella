> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# PRD：TaskRuntime 独立执行、服务端状态推送与任务列表

## 1. 背景问题

当前 Web UI 在提交任务后会执行：

```text
Web UI submit
→ AppRuntime.submit_text()
→ 获得 task_id
→ Web UI 创建后台线程
→ 调用 TaskRuntime.run_until_complete()
```

恢复任务时，Web UI 还会判断旧线程是否结束，并决定是否创建新线程。

这使 Web UI 承担了不应属于界面的职责：

- 启动任务执行线程。
- 调用 `TaskRuntime.run_until_complete()`。
- 判断恢复后是否重新启动线程。
- 使用 `_running_tasks` 记录任务是否正在执行。
- 保存任务完成 snapshot 作为额外状态来源。

## 2. 产品目标

调整为：

```text
Web UI 负责提交任务、展示任务、发送控制信号；
TaskRuntime 负责任务排队、执行、暂停、恢复和终止；
服务端主动向 Web UI 推送状态与最终结果。
```

用户提交的任务默认：

```text
auto_start = true
```

前端不提供手动启动按钮。

提交成功后，服务端立即返回 `task_id`，TaskRuntime 自动执行任务。

## 3. 目标架构

```text
Web UI
  │
  ├─ POST 用户输入
  │
  ├─ POST PAUSE / RESUME / KILL
  │
  └─ 接收服务端任务事件
          │
          ▼
AppRuntime
          │
          ▼
EventRuntime
  → 创建 Task
  → 返回 task_id
          │
          ▼
TaskRuntime Queue
          │
          ▼
TaskRuntime Worker
  → FORMULATING
  → READY
  → RUNNING
  → WAITING / PAUSED
  → SUCCEEDED / FAILED / UNCERTAIN / KILLED
          │
          ▼
TaskEventPublisher
          │
          ▼
服务端主动推送给 Web UI
```

## 4. 核心原则

### 4.1 Web UI 不执行任务

Web UI 不得调用：

```python
TaskRuntime.run_until_complete()
TaskRuntime.run_until_blocked()
TaskRuntime.step()
AppRuntime.run_submitted_task_with_display()
```

Web UI 不得创建任务执行线程。

需要移除：

```python
_running_tasks
_start_task()
_run_task()
_resume_task()
_start_after_current_run()
```

### 4.2 TaskRuntime 独占任务执行

TaskRuntime 负责：

- Formulation 调度。
- READY Task 入队。
- Worker 生命周期。
- ReAct 循环。
- Step 和 Tool Attempt 调度。
- Pause safe point。
- Resume 后重新入队。
- Kill 请求处理。
- Completion 与失败处理。
- Terminal event 发布。

### 4.3 Web UI 仍然控制任务

Web UI 可以控制任务是否继续执行，但控制方式是发送命令：

```text
PAUSE
RESUME
KILL
```

Web UI 只表达用户意图，不负责实现控制动作。

例如：

```text
用户点击恢复
→ Web UI 发送 RESUME
→ TaskRuntime 修改状态
→ TaskRuntime 重新入队
→ TaskRuntime Worker 继续执行
```

Web UI 不判断是否需要创建新线程。

## 5. 任务提交

### 5.1 提交请求

```http
POST /tasks
Content-Type: application/json
```

```json
{
  "input": "帮我检查当前屏幕"
}
```

所有用户任务默认：

```text
auto_start = true
```

第一版不允许前端修改该参数。

### 5.2 提交响应

任务创建成功后立即返回：

```http
202 Accepted
```

```json
{
  "task_id": "task-xxx",
  "trace_id": "trace-xxx",
  "state": "created",
  "auto_start": true
}
```

该请求不得等待：

- Task Formulation 完成。
- LLM 调用完成。
- Tool 调用完成。
- Final Response 完成。
- Memory 写入完成。

## 6. TaskRuntime Worker

AppRuntime 启动时创建并启动 TaskRuntime Worker：

```text
AppRuntime.create_default()
→ TaskRuntime.start()
→ Worker 等待 TaskQueue
```

TaskRuntime 应提供：

```python
start()
stop()
join()
```

任务创建后：

```text
Task CREATED
→ 自动加入 Runtime 调度
→ FORMULATING
→ READY
→ RUNNING
```

同一个 Task 同一时间只能被一个 Worker claim。

第一版使用单进程、单 Worker。
worker消耗task queue的消耗规则：
由scheduler将task queue中的任务分配给worker
worker获得任务之后持续执行任务，直到任务处于终止态，第一版本不做任务切换
EventRuntime 只提交 SourceEvent / TaskCreationRequest。
TaskRuntime 创建 CREATED Task、持久化并返回 task_id。
Worker 再执行 CREATED → FORMULATING → READY。

## 7. 前端任务展示

Web UI 将任务分为两个模块。

### 7.1 进行中任务

显示所有非最终状态的任务：

```text
CREATED
FORMULATING
READY
RUNNING
WAITING
PAUSE_REQUESTED
PAUSED
KILL_REQUESTED
```

每条任务至少展示：

- task_id
- 用户输入摘要
- 当前状态
- 创建时间
- 最近更新时间
- 当前执行阶段
- active_step_ids
- waiting_condition
- failure/blocking summary
- Pause 按钮
- Resume 按钮
- Cancel 按钮

### 7.2 已结束任务

显示所有最终状态的任务：

```text
SUCCEEDED
FAILED
UNCERTAIN
KILLED
DELIVERED
```

每条任务至少展示：

- task_id
- 用户输入摘要
- 最终状态
- 创建时间
- 结束时间
- final_response 或 failure message
- terminal_outcome
- Trace 查看入口

已结束任务只作为历史记录展示，不提供 Pause、Resume 或 Cancel 操作。

如果同一个 Task 从 `SUCCEEDED` 转为 `DELIVERED`，应更新原记录，不得生成两条历史记录。

## 8. 控制按钮规则

### 8.1 Pause

允许发送 PAUSE 的状态：

```text
CREATED
FORMULATING
READY
RUNNING
WAITING
```

以下状态不可重复发送 PAUSE：

```text
PAUSE_REQUESTED
PAUSED
KILL_REQUESTED
所有最终状态
```

点击 Pause 后：

```text
Web UI
→ POST PAUSE
→ TaskRuntime 根据task id为对应的task修改状态为 PAUSE_REQUESTED
→ 该task到达安全点
→ PAUSED
→ 服务端推送状态变化
```

### 8.2 Resume

仅当任务处于：

```text
PAUSED
```

Resume 按钮才可用。

点击后：

```text
Web UI
→ POST RESUME
→ TaskRuntime 恢复必要状态
→ Task 转为 READY
→ TaskRuntime 重新入队
→ Worker 自动继续执行
```

Web UI 不创建恢复线程。

### 8.3 Cancel

Cancel 对应：

```text
KILL
```

以下状态不允许发送 KILL：

```text
PAUSE_REQUESTED
KILL_REQUESTED
SUCCEEDED
FAILED
UNCERTAIN
KILLED
DELIVERED
```

允许从以下状态取消：

```text
CREATED
FORMULATING
READY
RUNNING
WAITING
PAUSED
```

取消后由 TaskRuntime 处理：

```text
KILL_REQUESTED
→ 到达安全点时立即终止
→ KILLED
```

## 9. 服务端主动推送

任务状态与最终结果不再依赖 Web UI 轮询发现。

第一版采用 **Server-Sent Events（SSE）**：

```http
GET /task-events
Accept: text/event-stream
```

选择 SSE 的原因：

- 服务端向浏览器单向推送即可满足需求。
- Pause、Resume、Kill 继续使用普通 HTTP POST。
- 比 WebSocket 更轻量。
- 适合任务状态、交互请求和最终结果推送。

## 10. 服务端事件类型

### 10.1 任务创建

```text
event: task_created
```

```json
{
  "event_id": "event-xxx",
  "task_id": "task-xxx",
  "state": "created",
  "user_input_summary": "帮我检查当前屏幕"
}
```

### 10.2 状态变化

```text
event: task_state_changed
```

```json
{
  "event_id": "event-xxx",
  "task_id": "task-xxx",
  "previous_state": "running",
  "current_state": "pause_requested",
  "updated_at": "..."
}
```

### 10.3 执行进度

```text
event: task_progress
```

内容包括：

```json
{
  "task_id": "task-xxx",
  "state": "running",
  "execution_stage": "tool_execution",
  "active_step_ids": ["step-1"],
  "tool_name": "screen_scene"
}
```

### 10.4 需要用户交互

```text
event: task_interaction_required
```

```json
{
  "task_id": "task-xxx",
  "state": "waiting",
  "interaction_request": {
    "correlation_key": "request-xxx",
    "kind": "user_input",
    "message": "请说明需要检查哪个窗口"
  }
}
```

### 10.5 任务结束

```text
event: task_terminal
```

无论任务以何种最终状态结束，都必须推送该事件：

```json
{
  "task_id": "task-xxx",
  "state": "succeeded",
  "finished_at": "...",
  "final_response": "...",
  "failure": null,
  "terminal_outcome": {},
  "display_snapshot": {}
}
```

包括：

```text
SUCCEEDED
FAILED
UNCERTAIN
KILLED
DELIVERED
```

## 11. 推送可靠性

SSE 连接建立后，服务端应先发送当前任务列表快照：

```text
event: task_snapshot
```

包含：

```json
{
  "active_tasks": [],
  "terminal_tasks": []
}
```

之后再发送增量事件。

每个事件必须包含单调递增或唯一的 `event_id`。

浏览器断线重连时，可以携带：

```text
Last-Event-ID
```

第一版至少保证：

- 重连后重新发送完整任务快照。
- 不依赖浏览器内存恢复任务状态。
- 重复事件按照 `task_id + event_id` 去重。
- 终态事件重复到达不会生成重复历史记录。

## 12. 服务端任务投影

服务端提供统一的只读任务投影：

```python
TaskStatusProjection
```

建议字段：

```text
task_id
trace_id
user_input_summary
state
execution_stage
active_step_ids
waiting_condition
paused_from_state
terminal_outcome
failure
final_response
created_at
updated_at
finished_at
```

前端不得直接读取：

```python
TaskRuntime._tasks
Task.task_local_state
TaskGraphRun.node_runs
```

这些内部对象应由 Runtime 转换为稳定投影。

## 13. 前端状态处理

收到服务端事件后：

```text
如果 Task 非最终状态
→ 更新 active_tasks 模块

如果 Task 进入最终状态
→ 从 active_tasks 删除
→ 按 task_id 写入 terminal_tasks
```

前端任务列表以 `task_id` 为唯一键。

禁止：

- 同一个 Task 同时出现在两个模块。
- 同一个终态 Task 出现多条历史记录。
- 前端自行推测 Task 状态。
- 根据按钮点击提前修改最终状态。

前端可以先显示“命令发送中”，但最终状态必须以服务端事件为准。

## 14. AppRuntime 接口

AppRuntime 对 Web UI 暴露：

```python
submit_text(text) -> TaskHandle
get_task(task_id) -> TaskStatusProjection
list_active_tasks() -> tuple[TaskStatusProjection, ...]
list_terminal_tasks() -> tuple[TaskStatusProjection, ...]
pause(task_id, reason)
resume(task_id, reason)
kill(task_id, reason)
provide_input(task_id, correlation_key, value)
subscribe_task_events(last_event_id=None)
```

不得向 Web UI 暴露：

```python
run_until_complete()
step()
TaskQueue
TaskScheduler
TaskStore
Worker Thread
```

## 15. Runtime 事件发布原则

TaskRuntime 应在完成状态持久化之后发布事件：

```text
修改 Task
→ 写 TaskStore checkpoint
→ 发布 task event
→ Web UI 收到事件
```

禁止先推送状态，再持久化状态。

如果推送失败：

- 不回滚 Task 状态。
- 事件可以重发。
- 前端重连后通过 snapshot 获得真实状态。

TaskStore 是状态事实来源，Task event 是状态投影通知，Trace 是诊断记录。

## 16. Memory 与 Final Response

终态事件应在以下内容准备完成后发布：

```text
Task 进入最终状态
→ Final Response 或 Failure Response 完成
→ Memory 写入结果确定
→ DisplaySnapshot 完成
→ 发布 task_terminal
```

对于 `KILLED` 或 `UNCERTAIN`：

- 可以没有正常 FinalResponse。
- 必须提供用户可读的终止原因。
- 不得只返回内部状态码。

## 17. 验收标准

- 用户提交任务后立即获得 `task_id`。
- 所有任务默认自动执行。
- Web UI 不调用 `run_until_complete()`。
- Web UI 不创建、恢复或管理 Task 执行线程。
- TaskRuntime Worker 独立消费任务。
- 页面关闭后，服务端任务仍继续执行。
- Web UI 可以发送 Pause、Resume 和 Kill。
- Resume 后由 TaskRuntime 自动重新入队。
- 服务端主动推送任务状态变化。
- 任意最终状态都会产生 `task_terminal` 事件。
- 页面具有进行中任务和已结束任务两个模块。
- 进行中任务具有 Pause、Resume、Cancel 控件。
- 已结束任务只显示历史记录。
- 同一个 Task 不会同时出现在两个模块。
- 同一个 Task 不会生成重复终态记录。
- SSE 重连后能恢复当前任务列表。
- CLI、麦克风和后台事件提交的 Task 也由同一 Worker 执行。
- Prompt、Tool、Memory 和任务决策语义保持不变。

## 18. 非目标

本 PR 不实现：

- 多进程 Worker。
- 分布式任务队列。
- WebSocket 双向通信。
- Token 流式输出。
- 多用户权限。
- 终态任务分页和数据库归档。
- 新的 Tool、Skill 或 Prompt 策略。
- 完整跨机器恢复。

## 19. 建议 PR 拆分

1. **TaskRuntime Worker 与自动执行队列**
2. **异步 Task Formulation 和立即返回 task_id**
3. **AppRuntime 任务投影与查询接口**
4. **TaskRuntime 状态事件发布器**
5. **SSE 任务状态推送**
6. **Web UI 移除执行线程**
7. **Web UI 进行中与已结束任务列表**
8. **Pause、Resume、Kill 控件接入**
9. **WAITING 交互请求与用户输入回传**
10. **事件重连、去重与完整契约测试**

# Ella Tool 失败分类、参数修复与 Step 状态 PRD

## 1. 文档信息

- 功能名称：Tool Failure Handling and Step Retry
- 适用范围：Ella Agent Runtime
- 文档状态：设计基线
- 目标：统一 Tool 成功结果、失败观察、参数修复、步骤状态和用户可见失败说明

## 2. 背景

当前 `CapabilityExecutor` 已能识别部分 Tool 输入、权限、可用性和输出错误，
但多数失败最终只表现为 `replan_required`。Runtime 尚未形成统一、可观察且有明确
上限的 Tool 失败处理机制。

当前主要问题包括：

- 缺少稳定的 Tool 失败分类。
- 参数错误无法在同一逻辑步骤内进行有限修复。
- 没有明确的逻辑 Step、attempt 和 retry 标识。
- 没有 Step 级 Tool 黑名单。
- 成功 `ToolResult` 与失败结果的语义边界不统一。
- Executor 失败未稳定反馈给 SubAgent 和最终回答。
- `camera_scene` 在已经成功拍摄但信息不足时可能被重复调用。

## 3. 产品目标

本版本实现以下能力：

1. 参数错误允许模型修复最多两次。
2. 参数修复期间只能修复同一个 Tool 的 arguments。
3. 权限、外部环境和 Tool 内部失败默认不在当前 Step 重试。
4. 所有失败统一归一化为 `ToolFailureObservation`。
5. `ToolResult` 只表示 Tool 成功执行后的业务结果。
6. 每个 `TaskSession` 拥有相互隔离的 Step 状态和历史。
7. SubAgent 可以同时看到成功 observation 和失败 observation。
8. 逻辑步骤和参数修复分别受到独立预算约束。
9. `camera_scene` 成功观测后，即使信息不足，也不在当前任务中重复拍摄。

## 4. 非目标

本版本不实现：

- Tool 内部自行重试。
- CapabilityExecutor 内部 ReAct 循环。
- 一次 attempt 执行多个 Tool。
- 自动申请或检测操作系统权限变化。
- 网络指数退避。
- 并发 Tool 执行。
- 跨 TaskSession 共享 Step 状态。
- 新的视觉充分性识别模型。
- TaskRuntime 多任务调度重构。

## 5. 核心术语

### 5.1 Runtime step 调用

一次 `TaskRuntime.step(task_id)` 调用称为一次 Runtime step 调用。

每次调用必须满足：

- 最多生成一个 `ExecutionDecision`。
- 最多执行一个 Tool。
- 不在方法内部循环调用 Tool。

### 5.2 逻辑 Step

逻辑 Step 表示任务中的一个待完成动作。一个逻辑 Step 可以包含一次初始尝试和
最多两次参数修复：

```text
step1_try
step1_retry1
step1_retry2
step2_try
```

### 5.3 Attempt

Attempt 是一次动作决策以及至多一次 Tool 调用。

参数校验失败且仍有修复机会时，当前逻辑 Step 不推进，而是进入同一逻辑 Step 的
下一个 retry attempt。

## 6. 架构边界

```text
TaskRuntime
├── 管理逻辑 Step 和 attempt
├── 管理参数 retry 预算
├── 管理 active_tool_name
├── 管理当前 Step 黑名单
└── 管理运行硬上限
        ↓
SubAgent
├── 接收结构化 Step 状态和 observations
└── 每次只生成一个 ExecutionDecision
        ↓
CapabilityExecutor
├── 校验权限与实时可用性
├── 校验 Tool 输入
├── 执行一次 Tool
├── 校验 Tool 输出
└── 将结果归一化为成功或失败
```

Tool 不负责 Runtime 的重试策略。Prompt 只指导模型，Runtime 必须执行最终校验。

## 7. StepExecutionState

新增显式、任务本地的数据契约：

```python
StepExecutionState
- step_number: int
- retry_index: int
- attempt_id: str
- active_tool_name: str | None
- blacklisted_tools: tuple[str, ...]
- failures: tuple[ToolFailureObservation, ...]
```

### 7.1 Attempt ID

Attempt ID 采用以下生成规则：

```text
retry_index == 0 -> step{step_number}_try
retry_index > 0  -> step{step_number}_retry{retry_index}
```

### 7.2 状态隔离

- 每个 `TaskSession` 必须通过独立 `default_factory` 创建 Step 状态。
- 不同 TaskSession 不得共享 blacklist、failures、attempt 或 retry 计数。
- 当前逻辑 Step 结束后保存为只读历史。
- 新逻辑 Step 必须重新初始化 retry、active Tool 和 blacklist。
- 历史失败必须继续作为 observation 提供，但不得成为成功事实。

## 8. ToolFailureObservation

失败类型定义为：

```python
ToolFailureKind
- INVALID_ARGUMENTS
- INVALID_ARGUMENTS_REPAIR_VIOLATION
- PERMISSION_DENIED
- ENVIRONMENT_UNAVAILABLE
- TOOL_EXECUTION_FAILED
```

失败记录至少包含：

```python
ToolFailureObservation
- attempt_id: str
- tool_name: str
- kind: ToolFailureKind
- code: str
- message: str
- arguments: dict
- retryable: bool
```

失败信息不得包含 API Key、Authorization Header、Provider 凭据、原始音频、原始
图片或未脱敏的本地敏感路径。

## 9. CapabilityExecutionResult

执行结果统一为：

```python
CapabilityExecutionResult
- decision: ExecutionDecision
- strategy: StrategyDecision
- tool_result: ToolResult | None
- failure: ToolFailureObservation | None
- raw_result: Any | None
- replan_required: bool
```

结果必须满足互斥约束：

```text
成功：
tool_result != None
failure == None

失败：
tool_result == None
failure != None
```

禁止同时设置 `tool_result` 和 `failure`。Runtime 只能依据规范化后的
`tool_result` 和 `failure` 判断执行结果。

## 10. ToolResult 边界

`ToolResult` 只表示 Tool 已经成功执行，并产生了可供任务使用的业务结果。

以下属于成功业务结果：

- 摄像头成功拍摄，但没有看到任务所需对象。
- 摄像头成功拍摄，但当前画面不足以完成判断。
- 屏幕截图成功，但未识别到人物。
- 文件搜索成功，但没有匹配文件。
- 天气查询成功，降雨概率为零。

以下属于失败，不得作为 Runtime 可见的成功 `ToolResult`：

- `status="unavailable"`
- `permission_denied`
- `device_unavailable`
- `backend_unavailable`
- `timeout`
- 输入或输出 Schema 不合法
- Tool 未处理异常

## 11. Legacy ToolResult 归一化

兼容阶段内，现有 Tool 可能仍返回：

```python
ToolResult(
    payload={
        "status": "unavailable",
        "error": {...},
    }
)
```

CapabilityExecutor 必须将其归一化为：

```python
CapabilityExecutionResult(
    tool_result=None,
    failure=ToolFailureObservation(...),
    raw_result=original_tool_result,
)
```

`raw_result` 仅用于本地诊断和测试：

- 不写入 `tool_trace`。
- 不作为事实传给 LLM。
- 不写入 Memory。
- 不进入 CompletionPackage。
- 不显示给普通用户。
- 不默认序列化。
- 不长期保存原始媒体。

## 12. 参数修复策略

### 12.1 初次参数失败

```text
step1_try
→ 输入参数校验失败
→ 记录 INVALID_ARGUMENTS
→ 锁定 active_tool_name
→ retry_index = 1
→ step1_retry1
```

参数修复上下文必须包含：

- 锁定的 Tool 名称。
- 上一次失败的 arguments。
- Tool 输入 Schema。
- 参数校验失败原因。
- 当前 retry 次数。
- 剩余 retry 次数。

### 12.2 同一 Tool 绑定

`active_tool_name` 在第一次参数校验失败时锁定。参数修复期间只允许返回：

```json
{
  "action": "CALL_TOOL",
  "tool_name": "<active_tool_name>",
  "arguments": {}
}
```

如果 retry attempt 返回不同 `tool_name`：

- Runtime 不执行任何 Tool。
- 记录 `INVALID_ARGUMENTS_REPAIR_VIOLATION`。
- 本次违规消耗一次 retry。
- `active_tool_name` 保持不变。
- 将违规原因反馈给下一次参数修复决策。

以下情况同样属于 repair violation：

- 非法 JSON。
- 未知 action。
- 返回非 `CALL_TOOL` action。
- 缺少 `tool_name`。
- 缺少 `arguments`。
- `arguments` 不是对象。
- 返回与 `active_tool_name` 不同的 Tool。

### 12.3 重试次数

默认参数修复预算：

```text
max_argument_retries = 2
```

完整 attempt 序列为：

```text
step1_try
step1_retry1
step1_retry2
```

如果 `step1_retry2` 仍然失败或违反修复协议：

- 将 `active_tool_name` 加入当前 Step 黑名单。
- 记录 `parameter_generation_failed`。
- 结束当前逻辑 Step。
- 推进到 `step2_try`。

无效参数在任何情况下都不得调用 Tool。

## 13. 失败分类策略

### 13.1 权限不足

权限不足包括：

- Task capability scope 拒绝。
- Agent role 不可见。
- `permission_denied`。

处理规则：

- `retryable=False`。
- 加入当前 Step 黑名单。
- 保存具体失败原因。
- 不在当前 Step 再次调用。
- 结束当前 Step 并进入下一逻辑 Step。

### 13.2 外部环境不可用

外部环境不可用包括：

- `file_not_found`
- `device_not_found`
- `device_unavailable`
- `device_busy`
- `network_unavailable`
- `backend_unavailable`
- `timeout`

处理规则：

- 不在当前 Step 重复调用同一 Tool。
- 记录环境阻塞原因。
- 结束当前 Step 并推进下一逻辑 Step。
- 后续模型不得把失败结果当成成功事实。

### 13.3 Tool 自身执行失败

Tool 自身执行失败包括：

- Tool 未处理异常。
- Provider 或服务内部错误。
- `backend_failure`。
- Tool 输出不符合 output schema。
- 无法识别的其他错误。

处理规则：

- Executor 捕获异常，避免 Runtime 崩溃。
- `retryable=False`。
- 不进入成功 ToolResult。
- 记录失败后推进逻辑 Step。

## 14. Step 黑名单

当前 Step 黑名单用于阻止本 Step 再次调用已确定不可用的 Tool。

加入黑名单的情况：

- 参数重试耗尽。
- 权限不足。
- 外部环境不可用。
- Tool 自身执行失败。

黑名单规则：

- 黑名单中的 Tool 不提供给当前 Step 的普通决策。
- 参数修复尚未耗尽时，`active_tool_name` 不加入黑名单。
- 进入下一逻辑 Step 后清空 blacklist。
- 历史失败继续作为 observation 保留。

Step 黑名单不负责 `camera_scene` 的重复观测限制；Camera 使用独立的任务级成功观测
规则。

## 15. Camera Scene 信息不足处理

### 15.1 语义

`camera_scene` 已成功获得画面，但画面中没有任务所需对象，或者画面信息不足以
完成判断，属于成功业务 observation，不属于 Tool 执行失败。

示例：

```python
ToolResult(
    payload={
        "status": "available",
        "summary": "当前画面没有清晰显示用户询问的对象。",
        "visible_items": [],
    }
)
```

### 15.2 不重复拍摄约束

只要当前任务已经存在一次成功的 `camera_scene` observation：

- 不得再次调用 `camera_scene`。
- 不因目标对象未出现而重新拍摄。
- 不因画面模糊、遮挡、角度不足或信息不足而自动重新拍摄。
- 不通过推进到下一逻辑 Step 绕过该限制。

SubAgent 必须使用已有 observation：

- 说明画面中实际观察到了什么。
- 说明没有观察到什么。
- 说明哪些信息因画面不足而无法确认。
- 在必要时请用户主动调整环境或补充信息，但不得自动再次拍摄。

该限制必须写入：

- `camera_scene` 的 ToolDefinition description。

当前只依赖模型遵守 Prompt。

### 15.3 与失败的区别

```text
成功拍摄，但信息不足
→ ToolResult
→ 当前任务不再自动拍摄
→ 根据已有画面说明不足

摄像头权限不足或设备不可用
→ ToolFailureObservation
→ 不产生成功 ToolResult
→ 向用户说明阻塞原因
```

## 16. SubAgent WorkSpace

`EXECUTION_DECISION` 的 WorkSpace 增加：

```text
current_step:
- attempt_id
- retry_index
- active_tool_name
- repair_mode
- retries_remaining
- blacklisted_tools
- failures

observations:
- successful_tool_results
- failure_observations
```

普通模式：

- 当前 Step 黑名单中的 Tool 不进入可见 ToolDefinition。
- 当前任务已有成功 `camera_scene` observation 时，`camera_scene` 不再作为可调用
  Tool 提供。
- 模型可以选择其他 Tool、`COMPLETE`、`WAIT` 或 `REPLAN`。

参数修复模式：

- 只提供 `active_tool_name` 对应的 ToolDefinition。
- Prompt 只要求修复 arguments。
- Runtime 必须再次校验 Tool 名称绑定，不能只依赖 Prompt。

策略选择阶段不参与 Tool 参数修复。

## 17. Session 记录边界

```text
TaskSession.tool_trace
```

只保存成功的 `ToolResult`。

失败保存到：

```text
TaskSession.current_step.failures
TaskSession.step_history[*].failures
```

Prompt 必须明确区分：

```text
ToolResult
→ 可以作为任务事实

ToolFailureObservation
→ 只能用于调整行为、说明阻塞和避免无效调用
```

## 18. Step 推进规则

以下情况结束当前逻辑 Step：

- Tool 成功执行。
- 参数重试耗尽。
- 权限不足。
- 外部环境不可用。
- Tool 自身执行失败。
- `COMPLETE`。
- `WAIT`。

以下情况不推进当前逻辑 Step：

- 参数仍有修复机会。
- Repair violation 后仍有修复机会。
- 显式 `REPLAN`。

进入新逻辑 Step 时：

- `retry_index` 重置为 `0`。
- `active_tool_name` 清空。
- 当前 Step blacklist 清空。
- 历史失败和成功 observation 继续保留。
- Camera 的任务级成功观测限制继续生效。

## 19. 运行预算

采用双预算：

```text
max_steps
```

限制逻辑步骤数量。

```text
max_argument_retries = 2
```

限制单个逻辑 Step 的参数修复次数。

另外设置内部硬迭代上限，用于覆盖：

- 生命周期状态迁移。
- 参数 retry。
- 显式 `REPLAN`。
- 非执行决策。

`TaskRuntimeResult.steps` 保留实际 `TaskRuntime.step()` 调用次数，并增加逻辑步骤计数，
避免改变既有监控字段的含义。

## 20. 用户可见失败

最终响应上下文必须包含：

- Tool 名称。
- 失败类别。
- 用户可理解的失败原因。
- 已尝试次数。
- 是否重试耗尽。
- 是否存在替代方案。

禁止只向用户显示：

```text
max_steps
permission_denied
backend_failure
```

应转换为自然说明，例如：

```text
我无法读取摄像头画面，因为当前没有摄像头权限。
```

```text
我尝试修正了两次工具参数，但仍无法生成有效参数，因此没有执行该工具。
```

对于 Camera 信息不足，应说明：

```text
我已经查看了当前画面，但画面没有提供足够信息来确认该对象。
```

不得通过再次拍摄掩盖信息不足。

## 21. 验收标准

- 参数失败后锁定 `active_tool_name`。
- Retry attempt 不能切换 Tool。
- 切换 Tool 被记录为 `INVALID_ARGUMENTS_REPAIR_VIOLATION`。
- Repair violation 消耗 retry，但不执行 Tool。
- 最多允许两次参数 retry。
- 所有失败统一进入 `CapabilityExecutionResult.failure`。
- Runtime 不接收失败形式的成功 `ToolResult`。
- `tool_trace` 只包含成功业务结果。
- 权限、环境和内部失败默认不在当前 Step 重试。
- 当前 Step blacklist 正确过滤 Tool。
- 两个 TaskSession 不共享 Step 状态或历史。
- Camera 成功拍摄但信息不足时不重复拍摄。
- Camera 重复拍摄限制跨逻辑 Step 保持生效。
- 用户能够看到明确、可理解的阻塞或信息不足说明。
- `max_steps` 和 `max_argument_retries` 分别生效。
- 所有循环受到内部硬上限保护。
- `python -m pytest` 通过。
- `python main.py` 可正常运行。

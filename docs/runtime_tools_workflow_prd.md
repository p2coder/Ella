# Ella Runtime 工具、JS Workflow、Subagent、结果时效与任务标识重构 PRD

## 1. 文档信息

- 功能名称：Runtime Tools, JavaScript Workflow, Subagent, Result Freshness and Task Identity Simplification
- 适用范围：Ella Agent Runtime、工具系统、任务持久化、Provider、Memory 与 Web UI
- 文档状态：已实施并通过验收（2026-09-04）
- 兼容策略：破坏性升级，不兼容旧 checkpoint、旧 API 返回和旧 Trace 文件
- 文档目标：以 Tool 为统一能力边界，补齐本地文件、命令、验证、结果刷新、JS 流程和子 Agent 能力；删除冗余运行时层级及 Runtime DAG，并将 `task_id` 收口为唯一任务关联标识。

## 2. 背景

当前 Ella 已具备 ToolManager、CapabilityExecutor、TaskRuntime、TaskGraph、checkpoint、TraceRecorder 和 Web UI 状态投影，但系统仍存在六类结构性问题：

1. 缺少通用的文本文件读取、创建、精确编辑和命令执行工具，Agent 无法通过一致的 Tool 契约完成本地工程任务。
2. ToolResult 没有统一完成时间，ToolDefinition 也没有结果有效时长，Agent 无法判断历史观察是否过期。
3. 过期结果缺少统一、安全且可审计的刷新入口。
4. 当前 TaskGraph、ToolGraph、PlanStore 和 DAG wave 调度侵入 TaskRuntime；新的 workflow 不应继续建立第二套图执行内核。
5. Verification 仍是 Runtime 在 `SUBMIT_RESULT` 后强制触发的特殊阶段，没有作为普通能力进入 ToolManager。
6. Event Router、Presence Runtime、HandoffRequest、`trace_id` 与大量 Task 对象跨层传递形成重复边界和重复身份来源。

本 PRD 将目标链路收口为：

```text
RawSignal
  -> 入口立即创建 task_id
  -> EventTriggerPipeline 携带 task_id 标准化
  -> TaskRuntime 创建 Task
  -> Agent Decide -> Tool Act -> Observe
  -> Agent 完整编写 JS workflow 脚本
  -> workflow 在 QuickJS 中按 await / Promise.all 编排 child Agent
  -> Observation 记录结果完成时间与有效期
  -> SUBMIT_RESULT
  -> Task 终态与交付
```

## 3. 目标与非目标

### 3.1 目标

- 新增九个正式 Tool：`read`、`write`、`edit`、`bash`、`verification`、`refresh`、`workflow`、`subagent`、`subagent_fork`。
- 所有 ToolResult 在结果生成时记录 UTC 完成时间戳；所有 ToolDefinition 声明结果有效时长。
- `refresh` 使用 tool_use_id 定位原 Tool 和原始输入参数重新获得结果，并保留来源链。
- 所有新能力进入现有 ToolManager、CapabilityScope、CapabilityExecutor 和统一观察链路。
- workflow 以完整 JavaScript 脚本表达 Agent 编排：`await` 表达串行，`Promise.all` 表达并行，脚本只能调用 subagent/subagent_fork。
- 删除 Runtime TaskGraph/ToolGraph、DAG、wave 和图调度；执行统一回到推理、执行、观察循环。
- 保留任务暂停、恢复、kill、Trace、Timing、checkpoint、失败和 uncertain 恢复。
- 将验证从 Runtime 特殊阶段改为 Agent 显式选择的 Tool。
- 支持完整继承父上下文的子 Agent，以及只继承最小身份和权限的干净上下文子 Agent。
- 删除 route、Presence Runtime 和 handoff 层，使输入标准化后直接创建 Task。
- 删除 `trace_id`，全系统只用 `task_id` 关联 Task、事件、Provider、工具、计时、日志、Memory 和交付。
- 跨模块默认传递 `task_id`；只有执行聚合逻辑确实需要 Task 时，才通过 TaskRuntime 或 TaskStore 查询。

### 3.2 非目标

- 不支持任意机器路径访问；文件和 shell 写入范围仅限 `PROJECT_ROOT`。
- 不把 workflow 编译成 Runtime DAG，也不维护与 Task 状态平行的图状态机。
- 不提供异步 child handle、独立 child Task 或跨 Task 子 Agent。
- 不保留旧字段别名、旧 checkpoint 转换器或双写兼容期。
- 不以 Trace 反向驱动 Runtime 状态。
- 不在本次重构中引入新的远程执行器或分布式调度系统。

## 4. 设计原则

1. **Tool 是统一能力边界**：文件、shell、验证、刷新、JS 流程和子 Agent 均通过同一发现、授权、执行和观察协议运行。
2. **Task 是唯一任务聚合**：TaskIntent、观察、失败、交付和恢复状态只能有一个事实来源。
3. **task_id 是唯一关联键**：不得再创建与 Task 生命周期一一对应的第二个 trace 标识。
4. **默认最小权限**：路径必须被解析到项目根内；子 Agent 只能继承或收窄权限，不能提权。
5. **失败时不猜测**：路径、编辑匹配、沙箱、子 Agent 副作用状态不明确时必须明确失败或进入 uncertain。
6. **脚本不是第二套 Runtime**：workflow 只是一次受控 Tool 执行；TaskRuntime 不理解脚本中的业务 DAG，只记录普通推理、执行、观察和脚本事件。
7. **显式验证**：Runtime 不再把验证隐藏在提交结果之后；Agent 必须主动调用 `verification` 才会发生验证。
8. **同步子 Agent**：第一版保持现有 `CALL_TOOL` 的同步语义，不引入额外 wait/poll 协议。
9. **结果时效显式化**：完成时间属于 ToolResult，有效时长属于 ToolDefinition，过期状态通过二者计算。
10. **状态能力保留**：删除 DAG 不得削弱暂停、恢复、kill、Trace、checkpoint 或 uncertain 安全边界。

## 5. 公共 Tool 契约

### 5.1 ToolDefinition 有效时长

所有 ToolDefinition 新增：

```text
result_ttl_seconds: float | null
```

- 正数表示 Tool 建议模型将结果视为有效的秒数。
- `null` 表示结果不会仅因时间流逝而失效，适用于写入确认等历史事实。
- `0` 表示结果只可作为历史执行记录，生成后即不应作为“当前事实”使用。
- 负数、NaN 和无穷值非法，Tool 注册时必须拒绝。
- TTL 是 Tool 自身固定属性，模型不能在单次调用中覆盖。
- ToolDefinition 的模型可见描述必须包含有效时长；Runtime 不据此判定过期、阻止使用或自动刷新。
- 迁移时必须为每个现有 Tool 显式选择 TTL，不使用含义模糊的全局默认值。

### 5.2 ToolResult 完成时间与结果归属

所有 Tool 继续实现 `Tool` 协议，但 `ToolResult` 调整为：

```text
tool_name: str
task_id: str
tool_use_id: str
agent_id: str
parent_agent_id: str | null
arguments: object
called_at: str
completed_at: str
result_ttl_seconds: float | null
status: succeeded | failed | timed_out | uncertain
payload: object | null
failure: object | null
```

- tool_use_id 在 schema 与权限校验通过后、实际 dispatch 前生成，全局唯一。
- called_at 在 dispatch 前由 CapabilityExecutor 记录；completed_at 在 Tool 返回或异常被捕获后记录。
- `completed_at` 是 Tool 执行完毕且结果生成时的 UTC RFC 3339 时间戳，必须包含时区并规范化为 `Z`。
- Tool 不接收或信任模型提供的时间；CapabilityExecutor 使用统一 UTC clock 生成两个时间戳。
- Tool failure observation 同样记录 completed_at，表示 Runtime 确认失败的时间。
- `duration_ms` 不进入模型、不写 Trace 或 checkpoint；前端仅根据 called_at 与 completed_at 动态计算并展示。
- `ToolResult`、Tool observation、失败记录和 UI 投影不得包含 `trace_id`。
- 工具输入 schema 不接受模型传入 task_id、tool_use_id、时间或 observation ID；执行器从 AgentExecutionContext 注入归属。
- 参数或权限校验失败发生在 dispatch 前，不生成 tool_use_id，不能通过 refresh 重放。

### 5.3 Observation 时间信息

成功 observation 至少保存：

```text
observation_id
tool_use_id
tool_name
task_id
agent_id
parent_agent_id
arguments
called_at
completed_at
result_ttl_seconds
payload
refresh_of_tool_use_id: str | null
```

- Runtime 只向模型提供 called_at、completed_at 和 result_ttl_seconds。
- Runtime 不生成 expires_at、fresh、expired 或 is_expired，也不自行判断 observation 是否过期。
- 是否需要刷新完全由模型结合时间、TTL、任务语境和数据版本决定。
- 历史 observation 不因刷新而被覆盖或删除。

### 5.4 `refresh`

输入：

```json
{
  "tool_use_id": "tool-use-unique-id"
}
```

- tool_use_id 唯一定位当前 Agent 顶层 observation 索引中一次已经 dispatch 的 Tool use，并自动取回原 Tool 名、原始已验证参数和原 Tool 版本信息。
- Child 内部 Tool use 虽有独立 ID 并写入嵌套 checkpoint/Trace，但不进入父 Agent 可寻址索引；父 Agent只能 refresh 整个 subagent、subagent_fork 或 workflow 外层 Tool use。
- Runtime 不判断来源是否过期；模型决定是否调用 refresh。
- refresh 不接受参数覆盖。需要新参数时，模型必须直接调用原 Tool。
- 原 Tool 必须仍注册、当前 Agent 仍有权限，并且不能是 refresh 本身。
- refresh 使用当前注册的 Tool 版本执行原参数；若旧参数不再通过当前 schema，则明确失败，不保存旧 Tool 代码用于兼容重放。
- refresh 必须通过 CapabilityExecutor 重新调用原 Tool，完整执行原 Tool 的 schema、权限、幂等性、副作用、超时和 uncertain 规则。
- 不新增 refresh_policy，不由 Runtime 判断重放是否必要或安全；包括 write、edit、bash、workflow 和 subagent 在内的任意 Tool 都可由模型决定 refresh，原 Tool 自身规则仍可能令重放失败或 uncertain。
- 成功后创建新的 observation，使用新的 tool_use_id、called_at、completed_at 和 TTL，并以 refresh_of_tool_use_id 指向来源；旧 observation 保留。
- 同一 Task 内对相同来源 tool_use_id 的并发刷新必须合并或串行化。
- dispatch 后状态未知时按原 Tool uncertain policy 处理，不得自动重试。
- refresh ToolDefinition 自身 TTL 固定为 `0`；重放结果使用原 Tool 当前 TTL。

### 5.5 路径安全公共规则

`read`、`write`、`edit` 与 `bash` 共享以下安全边界：

- Tool 构造时注入规范化后的 `PROJECT_ROOT`。
- 对输入路径先拒绝绝对路径，再解析 `.`、`..` 和符号链接，最终路径必须位于项目根内。
- 不允许通过项目根内的符号链接访问根外文件。
- 错误 payload 必须区分非法路径、文件不存在、文件已存在、非文本文件、大小超限和系统 I/O 失败。
- Tool 不得在失败时留下部分写入；文件写操作必须使用同目录临时文件加原子替换，或提供等价原子保证。
- 第一版统一使用 UTF-8；解码失败视为非文本文件。

### 5.6 `read`

输入：

```json
{
  "path": "relative/path.txt"
}
```

行为：

- 只读取普通文件，不读取目录或设备文件。
- 设置固定最大读取字节数；超出时返回前缀内容并标记 `truncated=true`，不得无界读取。
- 不改变文件内容、时间戳或工作区状态。

输出至少包含：

```text
path
content
byte_count
truncated
content_hash_algorithm
content_hash
```

`content_hash_algorithm` 固定为 sha256，content_hash 是磁盘原始文件字节的 64 位小写十六进制 SHA-256。换行与 Unicode 不做规范化。read 的 TTL 为 `null`；结果只证明该 hash 对应版本的内容，不能证明文件当前仍是该版本。

执行元数据：idempotent、非 side-effecting。

### 5.7 `write`

输入：

```json
{
  "path": "relative/new-file.txt",
  "content": "text"
}
```

行为：

- 仅创建新 UTF-8 文本文件。
- 可以在项目根内创建缺失的父目录。
- 目标已存在时必须失败，不能提供隐式覆盖，也不提供 `overwrite` 参数。
- 内容超过写入上限时，在写入前失败。

输出至少包含 path、byte_count、created=true、content_hash_algorithm=sha256 和写入后 content_hash。

执行元数据：non-idempotent、side-effecting、dispatch 后可能 uncertain，TTL 为 `null`。

### 5.8 `edit`

输入：

```json
{
  "path": "relative/existing-file.txt",
  "old_text": "unique original text",
  "new_text": "replacement text"
}
```

行为：

- `old_text` 必须为非空字符串，并在文件中恰好出现一次。
- 零次或多次匹配时返回明确失败，文件保持不变。
- 替换后的文件超过写入上限时，在写入前失败。
- 成功时原子替换文件内容。

输出至少包含 path、replacement_count=1、byte_count_before、byte_count_after、content_hash_algorithm=sha256 和修改后 content_hash。

执行元数据：non-idempotent、side-effecting、dispatch 后可能 uncertain，TTL 为 `null`。

### 5.9 `bash`

输入：

```json
{
  "command": "python -m pytest -q",
  "timeout_seconds": 30
}
```

行为：

- `command` 为必填非空字符串；`timeout_seconds` 可选，但不得超过 Runtime 全局上限。
- 子进程 cwd 固定为 `PROJECT_ROOT`。
- macOS 使用系统 `sandbox-exec` 建立 profile：允许读取运行所需系统路径，但文件写入仅允许 `PROJECT_ROOT` 和系统必要临时目录。
- 沙箱能力不可用或 profile 初始化失败时 fail closed，不能降级为不受限 shell。
- 超时后终止完整进程组，避免遗留子进程。
- stdout 与 stderr 分别捕获并限制字节数；超出时截断并在结果中标记。

输出至少包含：

```text
exit_code: int | null
stdout
stderr
timed_out
stdout_truncated
stderr_truncated
```

执行元数据：non-idempotent、side-effecting、dispatch 后可能 uncertain，TTL 默认 300 秒。模型可以选择 refresh，但 Runtime 不保证重放安全。

## 6. Verification Tool

### 6.1 边界调整

删除 `TaskRuntime._verify_candidate()`、verification round、`verification_in_progress`、`pending_reasoning=verification` 及 `SUBMIT_RESULT` 后的隐式验证分支。`SUBMIT_RESULT` 直接进入既有完成与交付路径。

现有 VerificationAgent 的 verdict 解析、LLM prompt 和机械检查能力迁移到 `verification` Tool 内部，不再作为 Runtime 的特殊协作者装配。

### 6.2 输入与数据获取

输入：

```json
{
  "candidate_result": "candidate user-facing result"
}
```

Tool 通过 `context.task_id` 查询当前 Task，并读取：

- TaskIntent 的 goal、constraints、deliverables 和 minimum acceptance criteria；
- 当前工具观察、called_at、completed_at、TTL 与失败记录；
- 输入中的候选结果。

模型不得在输入中伪造 TaskIntent、观察或 `task_id`。

### 6.3 执行与输出

- Tool 内部允许调用现有只读机械检查能力，如产物存在、文档读取和工具观察查询。
- 机械检查调用仍受 ToolManager 可见性与固定调用预算约束。
- minimum acceptance criteria 为空时，可以生成确定性 verdict，但仍只在 Agent 显式调用本 Tool 时发生。
- Provider、机械检查或 verdict 解析失败时返回标准 Tool failure，不直接把 Task 标记为 FAILED。
- Runtime 不替 verification 判断 observation 是否过期；验证模型根据时间与 TTL 决定是否先建议 refresh。

输出保持以下字段：

```text
goal_state
criterion_results
deliverable_results
draft_quality_issues
recoverable
feedback_for_execution
public_summary
```

Agent 可以依据结果继续调用工具或提交结果。Runtime 不强制要求提交前必须存在 verification observation。verification 默认 TTL 为 300 秒，但是否复用仍由模型判断。

## 7. Workflow Tool

### 7.1 定位

`workflow` 是一个执行完整 JavaScript 脚本的 Tool，替换 `plan_written`、PlanStore 和 Runtime DAG。它不是 TaskRuntime 的图调度接口，也不把脚本编译为 TaskGraph。

Agent 必须先生成完整脚本，再以一次 `CALL_TOOL(workflow)` 提交并运行。Runtime 不接受“追加一行并立即执行”或未闭合的增量脚本。

### 7.2 输入与输出

输入：

```json
{
  "script": "const [a, b] = await Promise.all([tools.subagent({prompt: 'Analyze A'}), tools.subagent_fork({prompt: 'Analyze B'})]);\nreturn {a, b};",
  "timeout_seconds": 120
}
```

- script 是完整 JavaScript 程序；timeout_seconds 可选并受 Runtime 全局上限约束。
- 脚本只能调用 `tools.subagent({prompt})` 和 `tools.subagent_fork({prompt})`；workflow 不直接编排 read、write、edit、bash、verification、refresh 或其他普通 Tool。
- 普通 Tool 只能由被编排的子 Agent在自身 Decide → Act → Observe 循环中调用。
- 脚本返回值必须可 JSON 序列化，并成为 workflow ToolResult payload。
- 输出包含 script_return_value、按声明顺序排列的 child_results、called_at、completed_at、失败或超时信息；不包含 DAG 或节点状态。
- workflow TTL 为 `null`，表示历史编排结果不会仅因时间流逝消失；模型仍根据 child 结果中的时间与 TTL 判断事实是否仍适用。

### 7.3 串行与并行语义

- 串行由普通 `await` 顺序表达：前一个 Tool promise 完成后才调用下一项。
- 并行由 `Promise.all([...])` 表达：全部 promise 完成后脚本才继续下一条语句。
- `Promise.all` 任一分支失败时整体拒绝；宿主停止新的 child dispatch，并等待全部已 dispatch child 到达安全终态后返回聚合失败。
- 已成功 child 结果全部保留；存在未确认副作用时父 Task 进入 UNCERTAIN。
- Agent 可以使用标准 JavaScript 的变量、函数、条件、数组和有限循环动态决定调用；Runtime 不从脚本推导 DAG、节点或依赖关系。
- workflow 的 child_results 保持 Promise.all 声明顺序；Trace 按真实 dispatch/completion 顺序记录。
- 并行 child 调用受 workflow 专用并发上限和 Task 总预算约束；超出时排队，不扩张预算。

### 7.4 JS 执行沙箱

- 使用嵌入式 QuickJS 独立 isolate 执行，通过 Python 宿主回调和 pending-job 循环桥接 child Promise。
- 不允许 eval、动态 import、CommonJS require、Node 内置模块、网络、文件系统、进程或宿主对象访问。
- 全局仅暴露冻结的 `tools` 代理、受控 console 记录、JSON 和必要的标准 JavaScript 原语。
- 所有外部副作用只能由 child Agent 通过 CapabilityExecutor 发起。
- tools 代理只能创建 child runner，不能直接持有 SubAgent、Task 或 Tool 实例。
- 禁止 workflow 脚本递归调用 workflow，避免嵌套 isolate 和不可控调度。
- 默认限制：script 64 KiB、wall time 10 分钟、并行 child 8、总 child 调用 32、QuickJS heap 64 MiB、返回值 1 MiB；全部进入 Settings 并保留硬上限。
- isolate 初始化或限制能力不可用时 fail closed。

### 7.5 与推理—执行循环的关系

- workflow 对 TaskRuntime 来说只是一次 CALL_TOOL。
- 脚本内部每次 child 调用产生嵌套 child result；父 Task 顶层只保存 workflow observation。
- TaskRuntime 不创建 workflow node state、active step、GraphRun、wave 或恢复游标。
- workflow 完成后汇总结果作为一次 observation 返回父 Agent，父 Agent进入下一轮推理。
- workflow 失败形成标准 Tool failure；副作用状态不明时提升为 uncertain，并阻止整个 workflow 自动重放。

### 7.6 暂停、kill 与 checkpoint

- 父 Task 与所有后代 Agent 共享同一个 control token。pause/kill 递归阻止所有后代发起新的 LLM/Tool 调用。
- pause/kill 在每次 child/Tool 调用前后以及 promise 汇合处检查。
- 已 dispatch 的同步调用必须等待返回或自身超时；全部活跃后代到达安全边界后，父 Task 才进入 PAUSED、KILLED 或 UNCERTAIN。
- 同一进程内 pause 在安全点阻塞 QuickJS continuation，resume 后继续；kill 不再继续脚本。
- 每个 child dispatch 前原子写入 in_flight，完成后先原子写入 child result 再清除 in_flight。checkpoint 保存完整 script、开始时间、已完成 child 结果、当前控制请求和 in-flight action。
- 第一版不保存 JavaScript 堆栈或 promise continuation；进程崩溃时不得从脚本中点恢复。
- 若崩溃前所有已执行调用均可确认且无副作用风险，已完成 child 结果保留，workflow 作为 failed observation 返回，由父 Agent恢复后重新推理；存在未确认副作用时 Task 恢复为 UNCERTAIN。
- 不自动从头重跑 workflow。

### 7.7 Trace 与 UI

- Trace 记录 script_started、tool_dispatched、tool_completed、promise_join、script_completed、script_failed、control_safe_point 等事件，全部使用 task_id。
- UI 展示当前 workflow 是否 running、脚本摘要、活动 Tool 数、已完成调用数、失败/uncertain 和完成时间。
- UI 不绘制或持久化 DAG；调用时间线只是 Trace 的只读投影，不是 Runtime 状态来源。

## 8. Subagent Tools

### 8.1 共同契约

`subagent` 与 `subagent_fork` 都表示当前 Task 内的一次子 Agent 执行，不创建新 Task。两者均：

- 沿用父 Task 的 `task_id`；
- 创建新的唯一 `child_agent_id`；
- 将父 Agent ID 记录为 `parent_agent_id`；
- 同步等待子 Agent 完成、失败、超时或进入 uncertain；
- 将结构化结果作为一条父 Task Tool observation 写回；
- 使用与父 Agent 完全相同的 Tool、Skill 和角色权限配置，不提供提权或收窄参数。

共同输入：

```json
{
  "prompt": "bounded task for the child agent",
  "timeout_seconds": 120
}
```

- `prompt` 必须为非空字符串，并应描述一个有终止条件的子任务。
- allowed_tools 与 allowed_skills 不属于输入 schema；child 完整复制父 Agent 的 CapabilityScope。
- Skill 仍只是 prompt 中的可见说明；Skill 引用的 Tool 仍必须通过 ToolManager 权限检查。
- timeout 受 Runtime 全局上限约束。

共同输出：

```text
child_agent_id
status: completed | failed | timed_out | uncertain
final_response
observations
error
provider_usage
completed_at
```

两种子 Agent Tool 的 TTL 均为 `null`。Runtime 不判断 child 事实是否过期，模型依据嵌套调用的时间和 TTL 决定。

### 8.2 `subagent`：干净上下文

subagent 只自动获得：

- task_id；
- child_agent_id 与 parent_agent_id；
- 与父 Agent 相同的 CapabilityScope；
- PROJECT_ROOT、系统基础提示和必要运行配置；
- 调用时提供的 prompt。

它不自动注入父 Agent 的消息历史、TaskIntent、用户输入、观察、当前步骤、失败或推理 prompt。它仍可使用与父 Agent 相同的 Tool 权限；这是权限继承，不是上下文继承。

### 8.3 `subagent_fork`：完整上下文继承

subagent_fork 在实际 dispatch 时复制父 Agent 当前完整只读上下文快照，包括：

- TaskIntent、原始输入和消息历史；
- 已有 observations 及其 called_at、completed_at、TTL 和 tool_use_id；
- 当前步骤、重试、失败与工作区摘要；
- 已记录的 workflow 调用；
- task_id、child/parent 身份、相同 CapabilityScope 和调用 prompt。

多个并行 fork 各自复制 dispatch 时的父快照，互相看不到兄弟 Agent 后续产生的结果。完整继承只复制序列化快照，不允许 child 持有父 Task 可变对象。

### 8.4 嵌套、恢复与不确定性

- 两种子 Agent 都可以调用普通 Tool、refresh、workflow 以及子 Agent Tool。
- 默认最大子 Agent 深度为 4；根 Agent 深度为 0，创建超过限制的 child 时在执行前失败。
- Child 使用完整 Decide → Act → Observe runner，直到 SUBMIT_RESULT、失败、父级 pause/kill、超时或预算耗尽，而不是只执行一次 decision。
- 默认每个 child wall time 5 分钟、最多 50 次 decision/Tool 推进；配置可调但受硬上限约束。
- 顶层 workflow 计父 Task 一个 logical step；child 内部步骤只计 child 上限，但所有 Provider/Tool 调用同时进入父 Task usage 与 wall-time 总账。
- checkpoint 至少记录 child_agent_id、parent_agent_id、模式、深度、权限、开始时间和当前状态。
- 因第一版是同步调用，进程崩溃后无法确认完成的 child 执行必须恢复为 uncertain，不能自动重放整个 child。
- child 内任一已 dispatch 的 side-effecting Tool 状态未知时，child 和父 ToolResult 均为 uncertain。
- child 的普通可恢复错误返回 failed observation，由父 Agent 决定是否换方案；不得隐式无限重试。
- Child 内部 Tool use 保存在 child result/checkpoint 中，并以同一 task_id、child_agent_id 写入 Trace，但不进入父 Task 顶层 observation 索引。
- 父 Task 只保存一条 subagent/subagent_fork observation，其中内嵌 final response、child observations 和引用信息。
- 父 Agent只能 refresh 整个 subagent Tool use，不能直接 refresh child 内部 Tool use。

### 8.5 通用 Context Compression Hook

- 所有 Agent 上下文使用同一个通用 compression hook，不只服务于 child。
- Settings 默认 `context_window_tokens=1_000_000`、`compression_threshold_ratio=0.8`；window 必须为正整数，ratio 必须在 `(0, 1)`。
- 对即将发送给 Provider 的完整序列化 prompt 粗估 token，包括 system prompt、Tool schemas、消息、observations 和当前输入。
- 估算按 Unicode 字符逐个累加：ASCII 字符 0.3 token，中文汉字 0.6 token，其他 Unicode 字符 1.0 token，最终向上取整。
- 估算达到 800,000 tokens 时调用 compression hook。第一版 hook 是空函数，不修改上下文。
- 空 hook 触发时只记录 `context_compression_requested` 事件，不生成 compaction checkpoint、摘要或“已压缩”状态。
- 空 hook 返回后继续使用原上下文；估算超过 1,000,000 tokens 时返回 context_too_large，不向 Provider 发送。
- 未来实现真实压缩时再保存 compaction ID、来源引用与摘要；第一版不得伪造这些数据。

## 9. Runtime 精简

### 9.1 删除 Runtime Graph 与 DAG 调度

从现役系统删除：

- TaskGraphDefinition、TaskGraphRun、TaskGraphNode 与 GraphEdge；
- ToolGraphDefinition、ToolGraphRun 和 ToolNode DAG；
- 拓扑排序、依赖就绪计算、wave 调度和图恢复分支；
- PlanStore、PlanRecord、PlanStep 和 plan_written Tool；
- max_parallel_steps_per_task、wave checkpoint threshold、active_step_ids 及图 UI。

不得以兼容层保留第二套图状态。历史 PRD 中关于 DAG、图节点状态或 Runtime pipeline/parallel 的要求由本 PRD 取代。

删除 DAG 后必须保留 TaskState、First Decision、TaskIntent、StepExecutionState、参数修复、Tool 黑名单、重试、Task Queue、后台 worker、任务间并发、PAUSE_REQUESTED、PAUSED、RESUME、KILL_REQUESTED、KILLED、FAILED、UNCERTAIN、COMPLETED、DELIVERED、checkpoint、Trace、Timing、Provider usage、Memory 和 Task events。

TaskRuntime 每个 tick 只处理控制/恢复边界，并最多产生一次 Agent decision 和一次顶层 Tool 调用。多步骤工作由 Agent 根据 observations 继续推理；workflow 脚本内部的调用属于同一次 Tool 执行，不产生 Runtime DAG。

### 9.2 删除 route 与 Presence Runtime

删除以下运行时概念及装配：

- TaskAwareEventRouter；
- RouteDestination、RouteDestinationRegistry 与 EventRouteResult；
- PresenceQueue、PresenceRuntime 与 PresenceRuntimeResult；
- route/presence 对应的 timing 字段和 UI/debug 投影。

EventTriggerPipeline 仍负责将 RawSignal 标准化为 StandardizedEvent，但标准化成功后直接调用 `TaskRuntime.create_task()`。需要抑制噪声、环境更新或打断策略时，应在 Signal Source 或未来独立输入策略 PRD 中定义，不得恢复同名的中转层。

### 9.3 删除 Handoff

删除 HandoffRequest 及以下依赖：

- Task.handoff；
- AgentExecutionContext.handoff_goal；
- TaskStore 的 handoff 编解码；
- SubAgent 接口中的 handoff 参数；
- prompt workspace 中由 handoff 派生的 goal 与 completion criteria。

First Decision 生成的 TaskIntent 是目标、约束、交付物和验收标准的唯一来源。用户偏好与环境摘要保存在 Task 自身上下文状态中，不再包装成 handoff。

### 9.4 Task 对象传递规则

- App、控制面、Queue、事件发布、Tool context、Provider 和查询 API 默认只传 `task_id`。
- 需要读取聚合状态时通过 TaskRuntime/TaskStore 的明确查询接口取得 Task 快照。
- 只有 TaskRuntime 内部负责原子状态转换、checkpoint 和循环推进的函数可以接收可变 Task。
- Tool 不得直接接收 Task；需要 Task 数据的 Tool 通过注入的只读 task lookup 按 `context.task_id` 获取快照。
- 不得缓存跨 tick 的可变 Task 引用。

## 10. `task_id` 唯一标识迁移

### 10.1 删除范围

从以下契约完全删除 `trace_id`：

- RawSignal 与 StandardizedEvent；
- Task、AgentExecutionContext 和 TaskHandle；
- ToolResult、Tool observations 和工具失败；
- Provider generate/transcribe/describe/capture 接口与 ProviderResult；
- RuntimeTimingRecorder 与 RuntimeTimingSnapshot；
- TraceEvent、TaskTraceSnapshot 和 TraceRecorder API；
- MemoryManagementRequest 与 Memory 文本；
- checkpoint、Task event、AppRuntime 投影及 Web UI。

不得保留 `trace_id=task_id` 的别名字段或重复参数。

### 10.2 新创建顺序

```text
接收 RawSignal
  -> 分配 task_id
  -> 以 task_id 标准化 Event
  -> 创建 Task 与 AgentExecutionContext
  -> 后续 Provider、Tool、Timing、Trace、Memory、UI 全部绑定该 task_id
```

输入 source 不再自行生成 trace ID。设备或 Provider 在 Task 创建前产生的诊断信息使用 source-local metadata，不进入 Task 级公共契约；一旦 Task 已创建，所有后续调用必须携带 `task_id`。

### 10.3 Trace 保留方式

TraceRecorder 作为可观测事件记录器继续存在，但接口收口为：

```text
record(task_id, boundary, event_type, payload)
snapshot(task_id)
```

每个 Task 对应一个按 `task_id` 命名的追加 JSONL 文件。TraceEvent 只保存 sequence、task_id、boundary、event_type、payload 和 recorded_at。

## 11. Checkpoint、API 与 UI 迁移

### 11.1 Checkpoint

- 直接提升 schema version。
- 新 schema 不保存 trace ID、handoff、route、presence、verification continuation、TaskGraph 或 ToolGraph 字段。
- 保存 TaskIntent、消息历史、当前 Step、child execution metadata、workflow 脚本执行元数据、Tool observations、tool_use_id、called_at、completed_at、TTL、refresh_of_tool_use_id、控制状态和交付状态。
- Runtime 不计算结果是否过期；checkpoint 只保存时间与 TTL 原始事实。
- 遇到旧 schema 时抛出 UnsupportedCheckpointSchema，并向 UI 明确展示“旧版本不可恢复”；不静默忽略、不做字段映射或后台迁移。

### 11.2 Runtime 与 Provider API

- `TaskHandle` 只保留 `task_id`。
- `TaskRuntimeResult` 可以包含 Task 快照，但调用入口和查询键必须是 `task_id`。
- Provider 参数由 `trace_id` 改为 `task_id`，metadata boundary 继续用于区分 first decision、execution、verification 和 child execution。
- Timing 直接按 `task_id` 创建、记录和查询，不维护 task-to-trace 映射。

### 11.3 Memory

- Memory 写入和检索只关联 `task_id`，删除 trace 字段和文本模板中的 trace 描述。
- 子 Agent 的观察仍归属父 Task，可额外保存 child_agent_id 作为非主键来源信息。
- 时效性事实写入长期 Memory 时必须保留来源 Tool 的 completed_at。

### 11.4 Web UI

- 删除任务详情中的 `trace_id` 展示。
- 保留 Trace 详情入口，但 URL 和查询仅使用 `task_id`。
- 删除现有 DAG/流程图展示。
- 展示 Tool use 的 called_at、completed_at、TTL 和 refresh 来源，不展示额外的结果时效状态字段。
- duration_ms 仅由前端依据两个时间戳动态计算；不进入模型、Trace 或 checkpoint。
- 展示 workflow 脚本运行状态、活动 Tool 数、调用时间线与 child Agent 摘要，但不得把调用时间线作为图状态源。
- 所有 SSE Task event 继续以 `task_id` 定位任务。

## 12. 分阶段实施

### Phase 1：唯一标识与输入链路

- 删除 route、Presence Runtime 和 Handoff。
- 调整输入链路，使入口在 RawSignal 后、EventTriggerPipeline 前创建 task_id。
- 从核心领域、Provider、Timing、Trace、Memory、checkpoint 和 UI 删除 `trace_id`。
- 升级 checkpoint schema 并修复现有测试夹具。

完成条件：文本与麦克风输入可以直接创建、执行、控制并交付仅由 `task_id` 标识的 Task。

### Phase 2：删除 DAG 与归一执行循环

- 删除 TaskGraph、ToolGraph、PlanStore、plan_written、wave 调度和图 UI。
- 将 TaskRuntime 收口为 First Decision 与 Decide → Act → Observe 循环。
- 保留控制、安全点、失败、uncertain、checkpoint、Trace 和后台 Task 并发。

完成条件：多轮 Tool 调用可由 observations 驱动推进，暂停、恢复、kill 和 crash 恢复保持有效，现役 Runtime 不存在 DAG 分支。

### Phase 3：Tool 时间、TTL 与 Refresh

- 为 ToolDefinition 增加 result_ttl_seconds，为 ToolResult 和失败 observation 增加 completed_at。
- 扩展 observation 持久化、Prompt、Trace、Memory 和 UI 时间/TTL 投影，不实现 Runtime 过期判断。
- 为全部现有 Tool 显式配置 TTL。
- 实现 refresh 的来源匹配、权限复核、安全重放、并发去重和来源链。

完成条件：任一结果均提供调用时间、完成时间和 TTL；refresh 通过 tool_use_id 使用相同 Tool 与相同原始参数重放，由模型决定是否需要。

### Phase 4：文件与 Bash 工具

- 实现共享路径解析和大小限制。
- 实现 read、write、edit 与 macOS 沙箱化 bash。
- 注册工具并补齐定义、TTL、执行元数据、错误归一化和安全测试。

完成条件：Agent 可在项目根内安全完成文本工程操作，且无法通过路径、符号链接或 shell 写出允许范围。

### Phase 5：Verification Tool

- 将现有 VerificationAgent 能力迁移为 Tool。
- 删除 Runtime 隐式验证状态机。
- 接入 observation 时间、TTL 与只读 task lookup。

完成条件：Agent 可显式验证候选结果；未调用 verification 的 SUBMIT_RESULT 不触发隐藏验证。

### Phase 6：JS Workflow Tool

- 集成受限 JavaScript isolate 和冻结的 tools 代理。
- 实现完整脚本提交、await 串行、Promise.all 并行、权限复核、预算、控制安全点和 Trace 事件。
- 替换 plan_written 模型接口，但不引入 TaskGraph 或图状态。
- 增加 checkpoint 的脚本/in-flight 元数据与 Web UI 调用时间线。

完成条件：脚本可以串行或并行调用 subagent/subagent_fork，Runtime 仍只运行推理、执行、观察循环；崩溃和未知副作用不会导致脚本自动重放。

### Phase 7：Subagent Tools

- 建立 child execution context、同权限复制和同步 runner。
- 实现 subagent 干净窗口与 subagent_fork 完整继承。
- 实现通用 context token 粗估与第一版空 compression hook。
- 接入预算、观察、checkpoint、uncertain 和 Provider usage 汇总。

完成条件：两种工具的上下文隔离符合契约，权限与父 Agent 相同，副作用未知时不会被自动重放。

### Phase 8：文档与残留清理

- 更新 README、架构文档和模型提示。
- 删除废弃模块、导出、配置、测试和过时术语。
- 全量搜索残留的 trace_id、HandoffRequest、PresenceRuntime、EventRouter、TaskGraph、ToolGraph、PlanStore 和 plan_written。

完成条件：现役代码和现役文档只描述新链路；历史文档如保留，必须明确标为 superseded。

## 13. 测试要求

### 13.1 Tool 契约与安全

- ToolDefinition schema、注册、发现、角色可见性和单一 task 归属。
- ToolDefinition 接受正数、0、null TTL，拒绝负数、NaN 和无穷值。
- 所有 dispatch 成功、Tool 成功和 Tool 失败记录包含唯一 tool_use_id、规范 UTC called_at/completed_at 和 TTL。
- 参数/权限校验失败不生成 tool_use_id。
- Prompt、checkpoint 与 UI 只暴露时间和 TTL，不生成 expires_at、fresh 或 expired。
- refresh 通过 tool_use_id 定位原 Tool 与原参数，并拒绝参数覆盖、缺失来源、权限不足、递归 refresh 和当前 schema 不兼容。
- refresh 允许重放任何 Tool；原 Tool 的失败和 uncertain 规则仍然生效。
- 刷新成功保留旧 observation 并建立 refresh_of_tool_use_id；并发刷新同一来源不重复执行。
- duration_ms 仅在前端动态计算，不进入模型、Trace 或 checkpoint。
- read 的正常读取、截断、非文本、目录和不存在文件。
- write 的正常创建、父目录创建、重复文件和超限输入。
- edit 的唯一匹配、零匹配、多匹配、空 old_text 和原子性。
- 绝对路径、`..`、符号链接和 shell 的根外写入均被拒绝。
- bash 的成功、非零退出、stdout/stderr、超时、进程组终止和输出截断。

### 13.2 Verification

- 有/无验收标准的 verdict。
- 机械检查、LLM 通过、可恢复失败、Provider 失败和非法 verdict。
- verification 可读取 observation 时间和 TTL，Runtime 不替模型判断是否过期。
- `SUBMIT_RESULT` 不隐式调用 verification。
- verification failure 只形成 Tool failure observation，不越权改变 Task 终态。

### 13.3 Workflow

- 完整脚本提交后才开始执行，非法或未闭合脚本不调用 Tool。
- 普通 await 严格串行；Promise.all 并行发起并等待全部成功。
- Promise.all 失败、已发起分支安全收口和 observation/Trace 完整记录。
- tools 代理只暴露 subagent 与 subagent_fork，直接调用其他 Tool 或递归 workflow 被拒绝。
- eval、import、require、Node API、网络、文件、进程和宿主对象访问被拒绝。
- workflow 递归调用、无限循环、内存超限、调用超限、并发超限和超时被安全终止。
- pause/kill 在 Tool 调用前后及 promise 汇合点生效。
- crash 后不恢复 JS continuation，也不自动重跑脚本；未知副作用进入 uncertain。
- UI 时间线与 Trace 一致，且系统不存在 Runtime 图状态。

### 13.4 Subagent

- subagent 使用干净上下文，只看到系统提示、身份、相同权限、工作区和 prompt。
- subagent_fork 完整复制 dispatch 时的父上下文；并行 fork 互相不可见。
- 相同 task_id、不同 child_agent_id 和正确 parent_agent_id。
- 父子 CapabilityScope 完全相同，输入 schema 不接受权限增减参数。
- 同步完成、失败、超时、uncertain、深度 4 边界和深度超限。
- child observations 嵌套保存且不进入父级索引；父 Agent只能 refresh 整个 child Tool use。
- Provider usage 汇总、步骤预算、共享 pause/kill 及 crash 恢复。
- 1M context window、80% hook 触发、字符粗估、空 hook 事件和超过硬上限失败。

### 13.5 Runtime 与唯一标识

- 标准化输入直接创建 Task，不经过 route、presence 或 handoff。
- 每个 Task tick 最多一次 decision 和一次顶层 Tool 调用。
- 多轮 observations 驱动推理，不创建 Graph、依赖节点或 wave。
- 文本和麦克风入口、暂停、恢复、kill、交付与 checkpoint 恢复。
- 删除 DAG 后 Trace、Timing、任务控制和 uncertain 行为保持有效。
- Event、Provider、Tool、Timing、Trace、Memory、API 和 UI 中不存在 `trace_id`。
- 不同 Task 的数据按 `task_id` 隔离。
- 旧 checkpoint 明确不可恢复。

每个 Phase 合并前运行对应聚焦测试；全部 Phase 完成后必须运行完整 pytest 套件。

## 14. 总体验收标准

以下条件全部满足才视为本 PRD 完成：

1. 九个新 Tool 均可被 ToolManager 发现、授权和执行，并产生标准 ToolResult。
2. 每个 ToolDefinition 都有明确 TTL，每个 dispatch 后的成功和失败结果都有 tool_use_id、called_at 与 completed_at。
3. Prompt、checkpoint、Trace、Memory 与 UI 一致暴露时间和 TTL，但 Runtime 不计算额外的时效状态。
4. refresh 仅输入 tool_use_id，并以当前 Tool 版本重放完全相同的原始参数；是否需要重放由模型决定。
5. 文件与 shell 操作无法写出 PROJECT_ROOT，沙箱失效时 bash 不执行。
6. workflow 在 QuickJS isolate 中通过 await/Promise.all 仅编排 subagent/subagent_fork，普通 Tool 由 child 调用。
7. workflow 是一次 Tool 执行，TaskRuntime 不创建 DAG、GraphRun、节点状态或 wave。
8. 脚本崩溃、kill 和未知副作用不会触发自动重放；Trace 与 checkpoint 保留可恢复的 Task 状态。
9. verification 仅作为显式 Tool 调用存在，Runtime 无隐藏验证阶段。
10. subagent 使用干净窗口，subagent_fork 完整继承父上下文，二者权限与父 Agent 相同。
11. child 执行与父 Task 使用同一 task_id，并正确记录独立 agent 身份和父子关系。
12. 暂停、恢复、kill、Trace、Timing、checkpoint、失败和 uncertain 在删除 DAG 后保持可用。
13. route、Presence Runtime、HandoffRequest、TaskGraph、ToolGraph、PlanStore 与 plan_written 不再出现在现役运行链路。
14. 现役代码、checkpoint、API、Provider、Tool、Memory、Timing、Trace 和 UI 不再包含 trace_id。
15. 跨层 API 默认传递 task_id，需要 Task 时通过受控查询取得。
16. 旧 checkpoint 被明确拒绝，完整测试套件通过。

## 15. 明确决策与默认值

- Tool 类提供 TTL 默认值，Settings 可以覆盖；第一版默认表为：

```text
read/write/edit                 null
ask_user_question               null
artifact_exists/document_read   3600 秒
tool_observation_check          0 秒
camera_scene/screen_scene       120 秒
web_search/web_page_read        3600 秒
verification                    300 秒
refresh                         0 秒
workflow                        null
subagent/subagent_fork          null
bash                            300 秒
Mock Tools                      60 秒
```

- workflow 默认限制为 script 64 KiB、wall time 10 分钟、并行 child 8、总 child 32、QuickJS heap 64 MiB、返回值 1 MiB。
- 每个 child 默认 wall time 5 分钟、最多 50 次 decision/Tool 推进；顶层 workflow 只计父 Task 一个 logical step，全部内部调用仍进入父 Task usage 与 wall-time 总账。
- 项目根目录是文件与 shell 的唯一可写范围。
- `write` 永不覆盖已有文件；修改已有文件必须使用 `edit`。
- `edit` 使用唯一精确字符串替换，不使用行号或 unified diff。
- bash 在沙箱不可用时 fail closed。
- 新工具集合为 read、write、edit、bash、verification、refresh、workflow、subagent、subagent_fork。
- 所有结果在执行完成时写入 UTC RFC 3339 `Z` 格式 completed_at。
- TTL 属于 ToolDefinition，只作为模型判断依据；Runtime 不计算或提供 expires_at、fresh、expired。
- Tool use 在校验后、dispatch 前生成 tool_use_id 和 called_at，在返回或异常捕获后生成 completed_at。
- duration_ms 仅由前端动态计算，不进入模型、Trace 或 checkpoint。
- refresh 只输入 tool_use_id，使用当前 Tool 版本重放原 Tool 和完全相同的已验证参数；需要新参数时直接调用原 Tool。
- 不增加 refresh_policy；任意 Tool 都可以由模型决定 refresh，Runtime 不替模型判断必要性或安全性。
- workflow 完全替换 plan_written，但不替代 TaskRuntime 或建立 DAG。
- workflow 输入是一段完整 JS 脚本；脚本编写完成后才运行。
- await 表达串行，Promise.all 表达并行；脚本通过冻结 tools 代理且只能调用 subagent/subagent_fork。
- workflow 不保存或展示动态 DAG，只展示脚本状态和 Tool 调用时间线。
- workflow 不支持递归调用，并且崩溃后不从头自动重跑。
- verification 是单一显式 Tool，不是自动完成门禁。
- 两种子 Agent Tool 均同步返回，并属于同一个父 Task。
- subagent 是干净上下文；subagent_fork 在 dispatch 时完整复制父上下文。
- child 权限配置与父 Agent 完全相同，不支持调用参数收窄或提权。
- 所有 Agent 使用 1M token context window；估算达到 80% 时调用第一版空 compression hook，超过硬上限才失败。
- token 粗估为 ASCII 0.3、中文汉字 0.6、其他 Unicode 1.0，统计完整序列化 prompt 并向上取整。
- 最大子 Agent 嵌套深度固定为 4。
- `task_id` 是唯一任务关联标识；不得以兼容名义保留 trace ID。
- 本重构采用一次性破坏性升级。

## 16. 实施验收记录

- Phase 1—8 已在 `codex/runtime-tools-refactor` 分支按小功能独立提交完成。
- 九个新 Tool 已注册到统一 ToolManager/CapabilityExecutor 链路。
- workflow 与 child Agent 的 dispatch、完成、失败、Trace、checkpoint、Provider usage 和 Web UI 投影已接通。
- 现役 Python/HTML 代码扫描未发现 `trace_id`、HandoffRequest、PresenceRuntime、TaskGraph、ToolGraph、PlanStore 或 `plan_written` 残留；历史文档与架构图均已明确标记 superseded。
- checkpoint schema 已执行破坏性升级，旧 schema 明确拒绝恢复。
- Markdown 基础检查与 Python 编译检查通过。
- 完整测试套件通过：`515 passed`。

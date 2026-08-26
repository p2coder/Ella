# Ella Runtime 历史 Checkpoint 续跑 PRD

## 1. 文档状态

- 文档类型：产品与 Runtime 行为规范
- 能力名称：基于 TaskGraph 的历史 Checkpoint 续跑
- 适用范围：Ella Agent Runtime、本地 TaskStore、TaskGraph 调度、任务控制接口和本地 Web UI
- 当前实现基线：每个 Task 仅保存最新原子 checkpoint，并可在进程重启后从该 checkpoint 恢复
- 本 PRD 新增能力：保留一个 Task 的多个语义 checkpoint，并允许用户选择其中一个安全 checkpoint 创建新的普通 Task 继续执行

本文以当前代码中的 `Task`、`TaskGraphRun`、`TaskStore`、`TaskRuntime` 和双状态任务模型为基础。本文描述的新能力尚未实现时，不得在产品说明中宣称已经支持。

## 2. 背景与问题

当前 `TaskStore` 使用 `task_id.json` 保存一个 Task 的最新完整快照。每次保存会原子替换旧文件，因此能够支持：

```text
进程退出
-> 加载该 Task 最新完整 checkpoint
-> 按保存的 TaskExecutionState 和 continuation metadata 继续执行
```

但它不能支持：

```text
用户查看一个 Task 的历史执行图
-> 选择某个历史节点边界
-> 从该 checkpoint 创建一条新的执行路径
```

历史续跑不能简单实现为原 Task 回滚。原 Task 已产生的 Trace、Tool observation、交付结果和外部副作用都必须保持不可变；同时，父任务和新任务不能共同持有同一条执行路径的执行权。

## 3. 产品目标

实现以下完整体验：

1. Runtime 在 TaskGraph 的语义安全边界保留历史 checkpoint。
2. Web UI 使用 TaskGraph 展示可选择的恢复位置。
3. 用户只能从允许恢复的 checkpoint 发起续跑。
4. 历史续跑创建一个新的普通 Task，并自动进入任务队列。
5. 新 Task 获得新的 `task_id` 和 `trace_id`，从所选 checkpoint 的运行快照开始执行。
6. 源 Task 在执行权转移后不可再次继续，也不可再次创建另一条恢复分支。
7. 已成功产生副作用的 Tool 不会因为历史续跑而被重复执行。
8. checkpoint 历史与续跑操作均可审计、可持久化，并能在进程重启后保持一致。

## 4. 非目标

本能力不实现：

- 对正在执行的 Task 进行任意时间点回滚。
- 在同一个 `task_id` 上覆盖状态或倒退版本。
- 从同一个源 Task 创建多个并行恢复分支。
- 重放 Tool 执行过程中的内存、线程栈或网络连接。
- 恢复到一个 Tool 调用的中间状态。
- 绕过 Tool 权限、版本、可见性或实时可用性检查。
- 为恢复后的 Task 增加特殊生命周期状态、特殊 Prompt 或特殊执行器。
- 迁移旧 checkpoint 格式或保证旧 checkpoint 历史可用。
- 在前端展示原始 prompt、完整 Tool 参数、敏感媒体或隐藏推理内容。

## 5. 核心原则

### 5.1 所有 Task 都以图执行

Ella 的执行统一基于 `TaskGraphDefinition` 与 `TaskGraphRun`。Task 必须至少拥有一个节点；简单任务使用最小单节点图，复杂任务使用包含多个 node 和 edge 的图。

因此历史恢复位置统一挂载在 TaskGraph 节点边界，不存在“无图 Task”的独立恢复协议。

### 5.2 历史续跑不是原地恢复

需要严格区分两种行为：

```text
崩溃恢复 / 暂停恢复
-> 同一个 Task
-> 同一个 task_id
-> 从该 Task 最新有效 checkpoint 恢复

历史 checkpoint 续跑
-> 创建新的 Task
-> 新 task_id / trace_id
-> 从用户选择的历史 checkpoint 初始化
```

### 5.3 新 Task 不具有特殊身份

checkpoint 只参与新 Task 的创建。创建完成后，新 Task 必须与普通提交的 Task 使用相同的：

- 生命周期状态机；
- TaskGraph scheduler；
- Reasoning 与 ToolExecution 边界；
- Tool schema 校验和失败策略；
- checkpoint、Trace、Verification 与 Delivery 流程；
- Pause、Resume 和 Kill 控制协议。

Runtime 不得根据“来自历史 checkpoint”选择另一套执行逻辑。

### 5.4 单一执行权

一个源 Task 最多允许发生一次历史续跑。成功创建新 Task 后：

- 新 Task 获得该执行路径的唯一执行权；
- 源 Task 不得继续执行；
- 源 Task 不得再次从其他 checkpoint 创建新 Task；
- 前端必须禁用源 Task 的所有历史续跑入口。

该规则用于避免同一历史状态被重复消费、相同副作用被多次触发以及父子任务并行修改同一逻辑结果。

## 6. 术语

### 6.1 Latest Checkpoint

某个 Task 最新保存且完整有效的 checkpoint。用于进程崩溃恢复和同一 Task 的 Pause/Resume。

### 6.2 Historical Checkpoint

Runtime 在已定义语义边界保存的历史快照。它有稳定 `checkpoint_id`，可用于审计和历史续跑资格判断。

### 6.3 Safe Point

Runtime 已经完成状态归一化且能够明确下一动作的边界。第一版只允许在以下位置创建可恢复 checkpoint：

- Reasoning node 执行前；
- Reasoning node 结果已校验并持久化后；
- Tool node 调用前；
- Tool node 返回并完成成功、失败或 uncertain 归一化后；
- 一个并发 wave 完成并落定 node run 状态后；
- Task 生命周期或控制命令的既有安全边界。

Tool 调用正在进行时不是 Safe Point。

### 6.4 Continuation Record

记录一次历史续跑关系的持久化清单。它是恢复操作和执行权转移的事实来源，但不要求向 `Task` 核心数据结构增加大量 lineage 字段。

最小字段：

```text
continuation_id
source_task_id
source_checkpoint_id
continued_as_task_id
created_at
actor
```

### 6.5 Checkpoint Eligibility

一个 checkpoint 是否允许创建新 Task 的确定性判断结果。Eligibility 由 Runtime 根据源 Task 状态、checkpoint 完整性、副作用历史和执行权状态计算，前端不得自行推断。

## 7. 历史 Checkpoint 数据契约

每个历史 checkpoint 至少包含：

```text
checkpoint_id
schema_version
checkpoint_sequence
task_id
trace_id
recorded_at
boundary
node_id
node_phase              # before | after | wave_settled | lifecycle
task_snapshot
side_effect_summary
integrity metadata
```

`task_snapshot` 必须包含足够继续执行的既有 Task 数据：

- TaskExecutionState 与 TaskGoalState；
- Task 原始输入、Intent 和 capability scope；
- TaskGraphDefinition、TaskGraphRun 与 node runs；
- 当前 decision、pending action 和 continuation metadata；
- observations、failures 和 retry budget；
- active Plan version；
- candidate result、verification 和 delivery 数据（若边界已产生）；
- Pause/Kill/Uncertain 等控制信息。

checkpoint 不得包含：

- API key、Authorization header 或 Provider credential；
- Provider client、Tool 实例、线程、锁或 socket；
- 原始音频和未获准保存的原始媒体；
- 隐藏推理链；
- 不受控绝对文件路径。

## 8. 存储模型

### 8.1 最新快照与历史快照

TaskStore 必须同时维护：

1. 当前 Task 最新快照：用于启动恢复和普通 Pause/Resume。
2. 历史 checkpoint 集合：用于图上预览、Eligibility 和创建新 Task。
3. Continuation Record：用于保证源 Task 只能转移一次执行权。

三者均为 Runtime 的持久化事实，不得依赖 Trace 重建。Trace 仍然只用于可观测和审计。

### 8.2 原子写入

单个 checkpoint 文件必须使用临时文件、`fsync` 和原子替换写入。损坏或未完成写入不能替代已有有效 checkpoint。

历史续跑操作必须作为一个逻辑原子事务完成：

```text
校验源 Task 与 checkpoint
-> 预留 continuation ownership
-> 创建并持久化新 Task
-> 写入 Continuation Record
-> 关闭源 Task 的执行权
-> 将新 Task 入队
```

若任一步骤失败，系统必须保证不会出现两个可运行 Task 同时拥有同一执行路径。第一版可使用 TaskStore 范围内的进程锁与原子 manifest 更新实现，不要求引入数据库。

### 8.3 保留策略

- 每个 Task 最多保存 1000 个历史 checkpoint。
- 默认保留 30 天。
- 清理顺序必须确定：先删除超过保留期且未被 Continuation Record 引用的最旧 checkpoint，再按 sequence 删除超过数量上限的最旧 checkpoint。
- 被有效 Continuation Record 引用的 source checkpoint 在对应新 Task 仍存在时不得提前删除。
- 清理失败不得影响 Task 执行，只记录结构化存储错误和 Trace。

## 9. Checkpoint 创建策略

### 9.1 语义 checkpoint

不是每次对象字段变化都创建历史 checkpoint。只有第 6.3 节定义的 Safe Point 才生成历史 checkpoint。

每个 checkpoint 必须明确关联：

- TaskGraph `node_id`；
- 节点前或节点后；
- 对应 graph version；
- checkpoint sequence。

### 9.2 并发 wave

并发 wave 沿用当前确定性 checkpoint 策略：

- wave 节点数不超过配置阈值时，在整波节点全部落定后创建统一 checkpoint；
- wave 节点数超过阈值时，每个节点完成后创建 checkpoint；
- 未完成 wave 的部分结果必须通过 node runs 表达，不能通过前端猜测。

### 9.3 重复边界

同一 Task、graph version、node、phase 和规范化状态不得无意义地产生内容完全相同的多个历史 checkpoint。实现可通过状态摘要去重，但不得因此遗漏状态或 observation 已变化的 checkpoint。

## 10. 恢复资格规则

### 10.1 源 Task 状态

只有以下源 Task 可发起历史续跑：

- `PAUSED`；
- 已经处于最终状态的 Task。

以下情况禁止历史续跑：

- Task 正在 `REASONING` 或 `TOOL_EXECUTION`；
- Task 处于 `READY`、控制请求处理中或队列可执行状态；
- checkpoint 损坏、schema 不支持或完整性校验失败；
- 源 Task 已存在 Continuation Record；
- checkpoint 被副作用规则判定为不可恢复。

终态源 Task 本身不会重新执行，因此无需改变其已经提交的 GoalState 或 Delivery 语义；它只需被 continuation ownership 永久锁定。处于 `PAUSED` 的源 Task在执行权成功转移后必须经过控制状态机关闭为 `KILLED`，其 GoalState 为 `NOT_ACHIEVED`。

### 10.2 普通无副作用 Tool

对于明确声明无副作用的 Tool：

- Tool 调用前 checkpoint 可恢复；
- Tool 调用后 checkpoint 可恢复；
- 已持久化的成功 observation 随快照继承；
- 恢复逻辑根据 node run 与 pending action 判断是否需要重新调用，不得无条件重放已成功节点。

### 10.3 已确认成功的副作用 Tool

ToolDefinition 必须显式声明副作用语义。若某副作用 Tool 已确认成功：

- 该 Tool 成功之前的所有历史 checkpoint 均不可恢复；
- 只能选择该 Tool 成功并落盘之后的安全 checkpoint；
- 新 Task 必须继承该成功 observation 和已完成 node 状态；
- Runtime 不得重复调用该副作用 Tool。

### 10.4 已确认失败且未产生副作用

若 Tool 明确失败，并且 Runtime 能确认外部副作用没有发生：

- Tool 调用前 checkpoint 可以恢复；
- Tool 失败 observation 是否继承由所选 checkpoint 的时间边界决定；
- 新 Task 仍需使用当前 ToolDefinition、权限和可用性重新校验后续调用。

### 10.5 副作用结果为 UNCERTAIN

当副作用 Tool 被中断或无法确认执行结果时，不允许 Runtime自行假设成功或失败。系统必须先向用户请求确认外部结果，再确定 checkpoint Eligibility：

1. 用户确认副作用已经发生：
   - 该 Tool 调用前及更早的 checkpoint 全部不可恢复；
   - 只允许从该 Tool 结果确认后的安全 checkpoint 继续；
   - 恢复后不得重复该副作用 Tool。
2. 用户确认副作用没有发生：
   - 允许从该 Tool 调用前的安全 checkpoint 继续；
   - 后续是否再次调用该 Tool由普通 Reasoning 与当前权限决定。
3. 用户仍无法确认：
   - 与该 uncertain Tool 有关的 checkpoint 全部不可用于历史续跑；
   - 系统向用户显示无法安全恢复的原因；
   - 不创建新 Task。

用户确认及其关联的 `task_id`、Tool attempt 和 observation 必须持久化并写入 Trace。该确认只影响 Eligibility，不引入新的 Task 生命周期状态。

## 11. 新 Task 初始化

### 11.1 标识

新 Task 必须生成：

- 新 `task_id`；
- 新 `trace_id`；
- 新 checkpoint sequence 空间；
- 新的 TaskStore 最新快照。

### 11.2 继承内容

从 source checkpoint 复制：

- 用户原始输入和 TaskIntent；
- checkpoint 当时的 TaskGraphDefinition/Run；
- 已落定 node runs；
- 可安全继承的 observations、failures、Plan version 和预算消耗；
- checkpoint 中已完成并可复用的 decision 或 continuation metadata。

不得复制运行时对象、worker 所有权、线程、锁、Provider client 或 Tool 实例。

### 11.3 当前能力重新解析

新 Task 创建时必须使用当前应用装配重新解析：

- 当前注册 Tool；
- 当前 Tool version；
- 当前 Skill；
- 当前角色和任务权限；
- 当前设备与 Provider 可用性。

source checkpoint 的 capability scope 只用于审计和缩小权限，不能使新 Task 获得当前已经不存在或已经撤销的能力。有效能力至少满足：

```text
source checkpoint允许
intersection 当前角色允许
intersection 当前任务策略允许
intersection 当前已注册且版本兼容
```

### 11.4 恢复后的行为

新 Task 根据快照中的 `TaskExecutionState`、node runs 和 continuation metadata 决定下一步。TaskGoalState 只用于目标验收，不参与恢复调度。

- 若 checkpoint 位于 Reasoning 前，重新执行该次 Reasoning。
- 若 Reasoning 结果和 Action 已完整落盘，继续执行该 Action。
- 若 Tool 结果已完整落盘，使用 observation 推进后续节点，不重复 Tool。
- 若 checkpoint 位于 wave settlement 后，从下一批 READY 节点继续。

## 12. 执行权转移

### 12.1 单分支限制

每个源 Task 只能产生一个 `continued_as_task_id`。一旦 Continuation Record 成功写入：

- 对同一源 Task 的后续 continuation 请求返回幂等结果或明确的 `already_continued` 错误；
- 不创建第二个新 Task；
- 前端显示已经续跑到的新 Task，并禁用所有 checkpoint 入口。

### 12.2 源 Task 处理

- `PAUSED` 源 Task：在新 Task 持久化成功后，转为 `KILL_REQUESTED -> KILLED`，原因包含新 Task 和 source checkpoint 的公开引用；不得再次 Resume。
- 已终态源 Task：保留原终态、GoalState 和交付记录，不倒退或改写业务结果；通过 Continuation Record 禁止再次执行或续跑。
- 新 Task 创建失败：源 Task 保持原状态和执行权，不写入成功 Continuation Record。

### 12.3 Worker 所有权

- 正在运行的源 Task不能发起历史续跑。
- PAUSED Task 在创建新 Task 前必须确认没有 worker 正在执行其节点。
- 新 Task 作为普通任务进入 TaskQueue，由空闲 worker claim。
- Web UI 不创建线程、不调用 `run_until_complete()`，也不直接驱动节点执行。

## 13. Runtime API

应用层至少提供：

```text
list_task_checkpoints(task_id)
preview_task_checkpoint(task_id, checkpoint_id)
continue_from_checkpoint(task_id, checkpoint_id, actor)
```

### 13.1 list_task_checkpoints

返回 TaskGraph 展示所需的最小数据：

```text
checkpoint_id
node_id
node_phase
eligible
ineligible_reason_code
```

不返回完整 Task snapshot、敏感 Tool 参数或原始媒体。

### 13.2 preview_task_checkpoint

返回对应 TaskGraph 的节点和 edge，以及每个 checkpoint 的图上位置与 Eligibility。前端不得自行读取 checkpoint 文件。

### 13.3 continue_from_checkpoint

请求必须携带：

```text
command_id
source_task_id
source_checkpoint_id
actor
```

成功结果至少返回：

```text
source_task_id
source_checkpoint_id
new_task_id
new_trace_id
submitted
```

重复 `command_id` 必须幂等，不得创建多个新 Task。

## 14. Web UI

### 14.1 展示形式

前端保持简洁，使用现有 TaskGraph 表达 checkpoint：

- checkpoint 显示在对应 node 的执行前或执行后；
- 可恢复 checkpoint 可点击；
- 不可恢复 checkpoint 置灰；
- 不展示完整 checkpoint 表格；
- 不展示 checkpoint 内部序列化数据；
- 不展示隐藏推理、敏感参数或原始媒体。

### 14.2 操作约束

- 运行中的 Task 不显示可用的历史续跑操作。
- 只有 PAUSED 或终态 Task 可选择 checkpoint。
- 用户提交续跑后，按钮立即禁用，等待后端返回结果。
- 源 Task 已完成一次续跑后，所有 checkpoint 操作永久禁用，并显示新 Task 的可跳转标识。
- 新 Task 出现在普通任务队列或终态列表中，不增加“恢复任务”专属区域。

### 14.3 前端边界

Web UI 只调用 AppRuntime 的查询与命令接口。它不得：

- 读取或写入 TaskStore 文件；
- 创建 Task 对象；
- 修改 TaskGraphRun；
- 启动 worker 或直接执行节点；
- 判断副作用安全性；
- 绕过 Runtime Eligibility。

## 15. Trace 与审计

必须记录：

- 历史 checkpoint 创建、去重、清理和损坏；
- checkpoint 的 node、phase、graph version 和 sequence；
- Eligibility 判断及公开原因码；
- uncertain 副作用的用户确认；
- continuation 请求、拒绝、成功和幂等命中；
- source task、source checkpoint 与 new task 的关联；
- 源 Task 执行权关闭；
- 新 Task 入队、claim 和后续执行。

推荐原因码：

```text
eligible
task_still_running
source_state_not_supported
checkpoint_corrupt
checkpoint_schema_unsupported
side_effect_already_confirmed
side_effect_uncertain
source_already_continued
capability_incompatible
checkpoint_expired
continuation_conflict
```

Trace 不作为恢复事实来源，不能用 Trace 重建缺失的 checkpoint 或 Continuation Record。

## 16. 错误与一致性处理

- checkpoint 不存在：返回 `checkpoint_not_found`，不创建 Task。
- checkpoint 损坏：返回 `checkpoint_corrupt`，保留源 Task。
- 源 Task 状态在校验后发生变化：返回 `continuation_conflict`。
- 当前能力无法满足安全恢复：返回 `capability_incompatible`，不创建 Task。
- 新 Task 持久化失败：不得关闭源 Task 执行权。
- Continuation Record 写入状态不确定：不得同时启动源 Task和新 Task；启动恢复时必须先完成一致性修复。
- 入队失败但新 Task 已持久化：新 Task 保持 `READY`，由 TaskRuntime 启动恢复重新入队；不得重新创建另一个 Task。
- 前端请求超时：客户端应按 `command_id` 查询结果，不能重复创建。

## 17. 安全与隐私

- checkpoint 文件路径必须来自配置并限制在受控 TaskStore 根目录。
- `task_id` 和 `checkpoint_id` 必须经过安全文件名校验。
- UI 只接收展示白名单字段。
- 权限以新 Task 创建时的当前配置为准；历史 checkpoint 不能恢复已撤销权限。
- 副作用标记来自 ToolDefinition，是 Eligibility 的事实来源。
- checkpoint 和 Continuation Record 不得记录 credential、认证头或隐藏推理链。

## 18. 验收标准

### 18.1 存储

- 一个 Task 可以保存并列出多个有序历史 checkpoint。
- 最新 checkpoint 恢复行为保持可用。
- 历史 checkpoint 写入失败不会损坏最新有效快照。
- 每个 Task 最多保留 1000 个 checkpoint，并执行确定性清理。

### 18.2 图与 UI

- 每个 Task 均有 TaskGraph，简单任务使用最小单节点图。
- UI 能在 node 前后显示 checkpoint 位置。
- UI 不显示复杂 checkpoint 表格或内部快照。
- 不可恢复 checkpoint 被置灰并显示简短原因。

### 18.3 续跑

- PAUSED Task 可从 eligible checkpoint 创建新 Task。
- 终态 Task 可从 eligible checkpoint 创建新 Task。
- 运行中 Task 无法发起历史续跑。
- 新 Task 使用新的 `task_id` 和 `trace_id`，自动入队并按普通 Task 执行。
- 源 Task只能成功转移一次执行权。
- PAUSED 源 Task转为 KILLED，终态源 Task 保留原终态并被 continuation lock。

### 18.4 副作用

- 已确认成功的副作用 Tool 之前的 checkpoint 不可恢复。
- 已确认无副作用的失败允许从 Tool 前 checkpoint 恢复。
- UNCERTAIN Tool 必须先由用户确认结果。
- 确认已发生时不重复副作用；确认未发生时允许 Tool 前恢复；无法确认时拒绝续跑。

### 18.5 一致性

- 并发 continuation 请求最多创建一个新 Task。
- 重复 command_id 不会重复创建 Task。
- 任意失败点都不会导致源 Task和新 Task同时可执行。
- 进程重启后仍能识别执行权已转移及新 Task 的队列状态。

## 19. 测试要求

至少覆盖：

1. 多 checkpoint 保存、排序、加载、去重和清理。
2. 原子写入失败与损坏 checkpoint 隔离。
3. 单节点和多节点 TaskGraph 的 checkpoint 定位。
4. node before/after 与 wave checkpoint。
5. PAUSED、终态和运行中源 Task 的 Eligibility。
6. 普通 Tool、成功副作用 Tool、明确失败 Tool 和 UNCERTAIN Tool。
7. 用户对 UNCERTAIN 结果的三种确认分支。
8. 新 Task 标识、状态、图、observation、预算和能力重新解析。
9. Reasoning 前、Reasoning 后、Tool 后和 wave 后的准确 continuation。
10. 单源 Task 单分支和并发请求冲突。
11. PAUSED 源 Task关闭、终态源 Task保持不变。
12. 新 Task自动入队并由普通 worker claim。
13. Web UI 图上显示、置灰、提交禁用和父子 Task 跳转。
14. 前端不读取存储、不驱动 Runtime、不判断副作用。
15. Trace 完整且不泄漏 credential、隐藏推理或原始敏感媒体。
16. 全量 `python -m pytest` 与 `python main.py` 保持可运行。

## 20. 建议实施拆分

后续代码实施应拆成独立 PR：

1. 历史 Checkpoint 与 Continuation Record 数据契约。
2. TaskStore 历史快照、保留策略和原子 manifest。
3. Checkpoint Eligibility 与副作用安全判断。
4. Runtime `continue_from_checkpoint` 原子执行权转移。
5. AppRuntime 查询和命令边界。
6. Web UI TaskGraph checkpoint 选择与状态展示。
7. 端到端恢复、一致性、重启和安全回归测试。

每个 PR 必须保持主分支可运行，不得通过临时兼容分支绕过本文的单执行权、副作用和普通 Task 语义。

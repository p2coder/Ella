> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella Agent Runtime 综合设计文档

> 核对基线日期：2026-08-27　|　本文档综合整理自 `docs/` 全部 27 份文档并与实际代码核对
> 本文只描述架构、演进与设计原理，不包含实现细节。具体契约与实施清单见各专项 PRD。

## 1. 文档目的

本文档是 Ella 项目的架构权威参考，解决两个问题：

1. **文档与实现的对齐**：`docs/` 下部分早期文档已与当前实现差距巨大，已逐一标记「已过期」并保留为历史记录；本文替代它们作为当前架构的单一入口。
2. **演进可追溯**：把分散在 14 份 PRD / 架构文档 / 重构方案里的设计决策串联成一条演进主线，让读者一次看懂「为什么现在是这个样子」。

## 2. 项目定位

Ella 是一个面向长期运行、本地交互、可恢复任务执行的 Agent Runtime 原型。它不是固定意图识别加 workflow 的脚本系统，而是一套可观察、可控制、可恢复的 Agent 执行骨架：用户输入被转成异步任务，由 Runtime 负责排队、推理、工具调用、验证、持久化和结果交付；Web UI 只负责提交任务、展示状态以及发送暂停/恢复/取消命令。

核心验证的不是单一聊天能力，而是这条主链路：

```
RawSignal → EventRuntime → TaskRuntime → SubAgent → CapabilityExecutor
        → ToolResult → VerificationAgent → FinalResponse → Memory → Web UI
```

## 3. 文档地图

### 3.1 已过期文档（已标记，仅作历史记录）

| 文件 | 原主题 | 过期原因 |
|---|---|---|
| `prd.md` | MVP 事件驱动骨架 | TaskSession/PresenceRuntime 链路被 TaskRuntime + TaskGraph + checkpoint 取代；`sessions/` 已清空 |
| `architecture.md` | v1 目标架构 | 只有 PresenceRuntime 手动编排，无现役 EventRuntime/TaskRuntime/CapabilityExecutor/TaskGraph/Verification |
| `prd_2_1.md` | 低频环境理解 | AmbientSensorRuntime / 疲劳提醒等主线整体未实现（当前唯一完全未落地的大块） |
| `todo_prd.md` | 2.1 执行清单 | Phase 3 未实现，清单已部分失效 |
| `prd3.md` | PromptEngine + 页面 | 模块路径全部失效（formulation 已并入 decision/factory，cli_demo/page_viewer 已移除） |
| `prd3_todo.md` | PRD3 实施提示词 | 引用路径失效，PR 无法直接执行 |

### 3.2 已完成的计划稿（历史记录，未标记过期但不再作为执行依据）

| 文件 | 原主题 | 状态 |
|---|---|---|
| `pr_plan.md` | MVP 的 PR1-14 实施计划 | 14 个 PR 已全部完成 |
| `restructure.md` | TaskRuntime 化 12 步重构方案 | 已全部落地 |
| `pr_tool.md` / `pr_tool_todo.md` | Tool 边界重构 PRD | 主体已实现；注意 §11「CapabilityExecutor 不得迁出 sessions」的约束实施时被打破（已迁至 `runtime/`） |
| `prd4_todo.md` | PRD4 Web UI 实施提示词 | 已完成 |
| `todo.md` | 角色可见性治理延期备忘 | 原标记 deferred，实际已实现 |
| `tune.md` | 单 PR 流程模板 | 仍适用，引用的 `pr_plan.md` 作为边界已过时 |

### 3.3 当前有效的文档（作为权威参考）

| 文件 | 主题 | 新鲜度 |
|---|---|---|
| `arch.md` | Runtime 2.0：providers/devices/config 接入 | 离当前实现最近的架构基线（缺 TaskGraph/checkpoint/Web UI/DeepSeek 等后续能力） |
| `pr4.md` | Web UI + AppRuntime 解耦 | 仍大体适用 |
| `prompt_prd.md` / `prompt_prd_todo.md` | PromptEngine 模块化与双层系统提示词 | 已被 structure_improve 演进 |
| `prompt_structure_improve_prd.md` | Prompt 结构稳定化 + Tool 描述 + 缓存聚合 | **当前最新生效** |
| `task_step_tool_graph_prd.md` / `*_todo.md` | Task/Step/Tool 图执行与分层状态机 | 大部分已落地 |
| `tool_failure_prd.md` / `*_todo.md` | Tool 失败分类与参数修复 | 已落地 |
| `task_runtime_worker_prd.md` | Worker 独立执行 + SSE 推送 | 部分落地 |
| `dual_state_task_verification_prd.md` | 双状态 + Verification | 已落地 |
| `checkpoint_history_restore_prd.md` | 历史 Checkpoint 续跑 | **纯规划，未落地** |
| `unified_action_model_prd.md` | 统一 Action + wave 并发 Runtime | 部分落地 / 演进中 |

> 文档间存在两处契约分歧需注意：`dual_state_task_verification_prd.md` 用 `SUBMIT_RESULT`，而 `unified_action_model_prd.md` 用 `COMPLETE`——两者是不同迭代版本的目标契约，以代码实际实现为准。

## 4. 架构演进主线

Ella 的演进不是推倒重来，而是「先建骨架，再补边界，最后加执行模型」。可分七个阶段：

### 阶段一：MVP 事件驱动骨架（`prd.md` / `architecture.md`）

验证一个持续在场的 Agent Runtime 骨架是否成立。定义 RawSignal → EventTriggerPipeline → 事件路由 → PresenceRuntime → TaskFormulation → TaskSession → SubAgent → TaskCompletionPackage → Memory 的生命周期闭环。核心贡献是把「事件进入—任务交接—隔离执行—结果交付」拆成清晰边界，并确立 `going_out` 作为策略选择结果而非事件类型的设计原则。

### 阶段二：Runtime 化重构（`restructure.md`）

把 CLI demo 的手动编排改造成应用级 Runtime：引入 `EventRuntime.publish → TaskRuntime.submit → run_until_complete` 的应用级任务总控、TaskState 状态机、单步 ExecutionDecision、TaskHandle。这一阶段确立了「Runtime 管生命周期、SubAgent 只决定下一步、Executor 只执行一个动作」的三角分工。

### 阶段三：Tool 边界重构（`pr_tool.md`）

把工具从硬编码序列变成自描述、可发现、可校验、可热插拔的能力：ToolDefinition（name/description/input_schema/output_schema）、ToolManager 只做进程级目录与发现、CapabilityExecutor 负责校验并执行单次调用、ToolRegistry 唯一存储源、Skill 仅按名称引用工具。这一阶段让系统从固定 workflow 走向动态能力选择。

### 阶段四：真实感知与真实模型接入（`arch.md` / `prd_2_0.md`）

在 Runtime 之上叠加 ProviderFactory（Qwen LLM/Speech/Vision/Multimodal）与 DeviceFactory（Microphone/Camera）边界，默认 mock provider，真实能力显式开启。确立「Provider/Device 管真实模型与真实设备，Runtime 只依赖接口」的隔离原则。`prd_2_1.md` 规划的低频环境理解（AmbientSensorRuntime、场景变化检测、疲劳提醒）是本阶段的延伸，但整体未实现。

### 阶段五：Prompt 与可观测（`prd3.md` → `prompt_prd.md` → `prompt_structure_improve_prd.md`）

引入 PromptEngine 作为唯一 prompt 拼装入扣，集中控制字段顺序、是否注入 memory / tool definitions、prompt 长度与敏感信息脱敏。演进到最新一版时，prompt 结构为前缀缓存友好做稳定化（稳定内容在前、动态内容在后），Tool 描述改写为 Purpose / Use when / Do not use when / Execution behavior / Failure 格式，并新增 provider usage 聚合以展示真实缓存命中率。

### 阶段六：交互界面与任务执行模型升级

- **Web UI 解耦**（`pr4.md`）：AppRuntime 作为 CLI/Web UI 共享入口，页面只提交输入与展示 RunDisplaySnapshot，不直连 EventRuntime/TaskRuntime；绑定 127.0.0.1、HTML escape、frame 安全引用。
- **图执行**（`task_step_tool_graph_prd.md`）：线性 TaskRuntime 升级为 Task/Step/Tool 三层图执行——TaskGraph 以 edges 为唯一拓扑源，前驱全部成功才计算 ready 集合作为一波并行执行，PLAN/REACT 二分流 + `plan_written` bootstrap。
- **双状态与验证**（`dual_state_task_verification_prd.md`）：TaskExecutionState 与 TaskGoalState 正交（后者只用于验收/展示），First Decision 一次输出 Intent + 首个 Action，统一 Action 只保留 CALL_TOOL/SUBMIT_RESULT，SUBMIT_RESULT 后进 VerificationAgent 做独立验收。
- **失败分类与确定性收口**（`tool_failure_prd.md`）：ToolFailureKind 五类、参数修复（锁定 active_tool、max retries）、Step 级黑名单、UNCERTAIN 以 `RESOLVE_UNCERTAIN_AS_FAILED` 收口，避免悬而未决。
- **Worker 独立执行**（`task_runtime_worker_prd.md`）：Web UI 不得驱动 `run_until_complete`，TaskRuntime Worker 独占执行循环，SSE 推送状态变更，支持 PAUSE/RESUME/KILL。
- **统一 Action 与并发 Runtime**（`unified_action_model_prd.md`，演进中）：唯一协议 CALL_TOOL/COMPLETE、CapabilityKind 三类、plan_written 用 Git bare repo PlanStore、wave 并发执行（每波最多 8 个 READY 节点，≤20 统一 checkpoint）。

### 阶段七：Prompt 稳定化（`prompt_structure_improve_prd.md`，当前最新）

为提升前缀缓存命中率重排 Decision Prompt 字段顺序，固定 visible_tools/visible_skills 排序，Instruction 与 OutputContract 拆分，删除 Decision Prompt 中的具体 Tool 路由规则；Tool 选择权完全保留给模型；Provider usage 按 boundary+modality 聚合并展示真实 `cache_hit_rate`。

### 当前实现精简（2026-08-31）

- TaskRuntime 直接持有和传递 Task，执行上下文由 Task 独占，不再经过 TaskCreationResult 包装。
- 工具注册、版本和发现统一由 ToolManager 管理，移除独立 ToolRegistry 及旧 registries 转发包。
- AgentExecutionContext 必须显式提供 CapabilityScope，工具权限只存放在 scope 中，不再接收或输出重复的顶层 allowed_tools。
- 移除未接入执行链路的 StepRuntime；现有 TaskGraph wave 执行、工具调用及 checkpoint 数据契约保持不变。
- 用量展示仅从 provider_usage_calls 聚合，不再读取旧版 usage/provider_usage 展示回退字段。

## 5. 当前架构分层

```
Input Layer          Web UI / 文本输入 / 麦克风（有界录音→ASR→复用文本链路）
Application Layer    AppRuntime（依赖注入根，UI 不直连 Runtime）
Runtime Layer        EventRuntime（标准化与路由） / TaskRuntime（队列/worker/状态机/checkpoint/wave 执行）
Agent Layer          SubAgent（First Decision / Next Decision） / VerificationAgent（独立验收）
Capability Layer     ToolManager（发现/角色可见性） / CapabilityExecutor（单步执行 + 双向 schema 校验）
Provider/Device Layer ProviderFactory（Mock/Qwen/DeepSeek LLM/Speech/Vision/Multimodal） / DeviceFactory（Camera/Microphone/Screen）
Persistence/Display  TaskStore（checkpoint）/ PlanStore / MemoryManager / TraceRecorder / RunDisplaySnapshot / Web UI
```

职责边界一句话：Runtime 管生命周期；Provider/Device 管真实模型与设备；Source 把外部输入变成 RawSignal；SubAgent 决定下一步动作；CapabilityExecutor 只执行一个动作；PromptEngine 只拼 prompt 不调模型；MemoryManager 是唯一 memory 读写入口；Web UI 只提交输入与展示结果。

## 6. 核心设计原理

跨文档抽取的、贯穿各阶段的设计哲学：

1. **Runtime 管生命周期，UI 不成为 Runtime**。页面只提交输入、展示 RunDisplaySnapshot、发送控制命令；执行循环、状态机、checkpoint 都在 Runtime 侧，UI 永远不直接驱动 `run_until_complete` 或创建执行线程。
2. **单步执行器 + max_steps 防失控**。CapabilityExecutor 只执行一个 `ExecutionDecision`，循环推进与最大步数留在 TaskRuntime。某个工具或 LLM 决策失控后不会无限调用模型或无限触发工具。
3. **双状态：执行态与目标态正交**。TaskExecutionState 驱动调度，TaskGoalState 只用于验收与展示。提交结果后由独立 VerificationAgent 判断目标是否达成，避免「执行完成」被误等于「目标达成」。
4. **First Decision 一步直达**。一次输出 Intent + 首个 Action（CALL_TOOL 或 SUBMIT_RESULT），省去 Task Formulation 与 Strategy Selection 的额外往返；无 intent 时只允许 ask_user_question。
5. **TaskGraph wave 执行**。以前驱全部成功为 gate 计算 ready 集合，作为一波并行执行；wave 超过阈值统一 checkpoint；PLAN/REACT 二分流 + `plan_written` bootstrap 复杂任务。
6. **Tool 自描述 + 双向 schema 校验 + 角色可见性**。LLM 只看当前任务可见的 ToolDefinition 快照而非 Tool 实例；输入输出均校验，非法参数不触发执行，非法输出不进入后续 prompt；不同 agent role 只能发现和使用对应能力。
7. **PromptEngine 唯一拼装入扣**。字段顺序、是否注入 memory / tool definitions、prompt 长度、敏感信息脱敏全部集中控制；为前缀缓存友好做稳定化排序（稳定内容在前、动态内容在后）。
8. **Mock-first + Provider/Device 工厂隔离**。默认不访问真实网络、摄像头、麦克风；真实能力通过工厂显式开启；Runtime 只依赖接口，可在 mock/real 间切换。
9. **确定性收口，不悬而未决**。UNCERTAIN 以 `RESOLVE_UNCERTAIN_AS_FAILED` 收口；副作用 Tool 已确认成功后前置 checkpoint 不可恢复；camera_scene 成功观测后任务内不重复拍摄。
10. **成本控制矩阵**。有界采样、不做持续视频流、麦克风手动触发、ASR 后复用文本链路、低频背景理解后置、Memory 先做最小版本、ToolDefinition 裁剪空间预留。
11. **checkpoint 安全点 + 历史续跑（规划）**。当前为最新原子 checkpoint + wave 增量落盘；历史续跑设计为「创建新 Task 转移执行权」而非原地回滚，副作用 Tool 规则约束可恢复边界（未实现）。

## 7. 当前边界与限制

下列结论已与代码核对，是当前真实状态：

- **MCP 未接入**：`mcp/` 为完全空目录，源码无 `import mcp`，依赖未声明。README 中「工具生态尚未接入 MCP」属实。
- **Memory 仍是最小版本**：MemoryManager 是单文件全量 append + 全量 `read_text` 读取，无检索、裁剪、嵌入、摘要、遗忘策略。README 中「Memory 仍是最小版本」属实。
- **Runtime 是单进程多线程，非分布式**：单进程内多线程 + ThreadPoolExecutor（任务 worker 池、wave 级并行、控制线程），无多进程 / 分布式 / 外部服务。README 中「本地单进程」属实，但已远超简单单线程循环。
- **Ambient 低频感知未实现**：AmbientSensorRuntime、场景变化检测、声音活动检测、疲劳/久坐提醒整体停留在 PRD 阶段，是当前唯一完全未落地的大块。
- **历史 Checkpoint 续跑未实现**：`checkpoint_history_restore_prd.md` 为纯规划，代码无 `continue_from_checkpoint` / `list_task_checkpoints`。
- **统一 Action Model 演进中**：wave 并发、Git bare repo PlanStore、worker 池等部分落地，与 `dual_state` 存在契约分歧（SUBMIT_RESULT vs COMPLETE），以代码实际实现为准。

## 8. 参考文档索引

需要深入某一块时，按主题查对应专项 PRD（均为当前有效）：

| 主题 | 文档 |
|---|---|
| PromptEngine 设计 | `prompt_prd.md` → `prompt_structure_improve_prd.md`（最新） |
| Task/Step/Tool 图执行 | `task_step_tool_graph_prd.md` |
| Tool 失败分类 | `tool_failure_prd.md` |
| 双状态与验证 | `dual_state_task_verification_prd.md` |
| Worker 与 SSE | `task_runtime_worker_prd.md` |
| 统一 Action 与并发 | `unified_action_model_prd.md`（演进中） |
| 历史 Checkpoint 续跑 | `checkpoint_history_restore_prd.md`（规划） |
| 2.0 架构基线 | `arch.md` |
| Web UI 解耦 | `pr4.md` |

> 已过期文档（见 §3.1）只作历史记录，不作为实现依据。本文档与代码同为权威来源，出现冲突以代码为准。

# Ella Agent Runtime 竞争分析报告

> 分析对象：Ella Agent Runtime（本仓库，本地 Agent Runtime / Harness）
> 对比对象：LangGraph、OpenAI Agents SDK、Google ADK、Letta (MemGPT)、Temporal
> 方法：基于各项目公开资料（官方文档 / GitHub README / release notes）逐项核实；检索不到或表述模糊的能力一律标注「未确认」，不凭印象补全。
> 时效：2026-08 前后公开资料（各项目最新版本：LangGraph 1.2.11、OpenAI Agents SDK 0.22.0、Google ADK 2.7.1、Letta V1 v0.16.8 / letta-code 0.30.32、Temporal v1.31.2）。各项目迭代快，结论有时效性。
> 说明：不同项目对同一概念命名不同，先统一为同一套比较口径（见 §2），再在各维度对比。

---

## 1. 选型范围

| 分类 | 项目 | 选择理由 |
| --- | --- | --- |
| 开发框架 | LangGraph (LangChain) | 图状态机编排的事实标准之一，checkpoint 持久化 + Human-in-the-loop 最成熟 |
| 开发框架 | OpenAI Agents SDK | 轻量框架 + 托管 tracing 的代表，handoff / workflow / sessions 模型 |
| Agent Runtime / Harness | Google ADK | 官方定位 Agent Development Kit，自带 session 持久化、memory service、checkpoint 与前端，最接近 Runtime 定位 |
| Agent Runtime / Harness | Letta (MemGPT) | 以 Memory 为核心的自托管 Agent Server，记忆维度标杆 |
| 工作流编排 | Temporal | Durable Execution 事实标准，signal / HITL / 重放恢复 / 重试策略，是众多 Agent Runtime 的底层底座 |

未选说明（非能力否定）：CrewAI / AutoGen / Pydantic AI 与 LangGraph、OpenAI Agents SDK 的框架维度高度重叠；Claude Agent SDK 偏闭源工具链；BeeAI 文档与社区成熟度目前低于上选。

---

## 2. 统一比较口径（7 个维度）

| 维度 | 统一口径定义 | 常见别名（各项目叫法） |
| --- | --- | --- |
| 任务规划 | 目标 → 可执行步骤的拆解与编排：静态预定义（图/工作流/代码）vs LLM 动态规划；计划是否版本化、条件分支、子任务/子代理拆分 | plan / workflow / graph / handoff / StrategyDecision |
| Tool 调用 | 工具发现与自描述（registry + schema）、输入/输出校验、执行模型（单步/并行）、生态接入（MCP 等）、人工确认 | function calling / tool node / activity / capability |
| Memory | 短期上下文 vs 长期持久记忆；写入/读取策略；检索（全量/窗口/向量）；摘要；遗忘 | context / sessions / store / memory blocks / archival memory |
| Pause/Resume | 运行中暂停/恢复；人类介入（human-in-the-loop）；崩溃后从 checkpoint 恢复；从历史节点续跑 | interrupt / checkpoint / signal / resume |
| Trace/Observability | 执行记录（事件/span/历史）、可视化（UI/仪表盘）、耗时分析、脱敏 | tracing / event history / telemetry / runs |
| 并发执行 | 单任务内并行步骤；多任务并行；多代理并行；隔离与上限 | parallel / send API / child workflows / multi-agent |
| 失败恢复 | 失败分类、重试策略、补偿/回滚、崩溃恢复、幂等 | retry policy / replay / saga / recovery |

评分符号：● 成熟 / ◐ 部分能力 / ○ 弱或无；标注「未确认」表示公开资料无法确认。

---

## 3. 对比总表

> ● 成熟 / ◐ 部分能力 / ○ 弱或无；「未确认」= 公开资料不足以确认。表后逐项目给出证据与来源。

| 维度 | LangGraph | OpenAI Agents SDK | Google ADK | Letta | Temporal | Ella |
| --- | --- | --- | --- | --- | --- | --- |
| 任务规划 | ● StateGraph 图建模 + 条件边/子图 + Functional API + Send 动态扇出；plan-and-execute 属上层模式 | ◐ agent loop + handoffs + agents-as-tools；无声明式 DAG 原语，代码编排用 asyncio.gather | ● agent types + 模板 workflow agents + 2.0 图 Workflow + 显式 planner（BuiltInPlanner/PlanReActPlanner）+ RoutedAgent | ◐ agent loop + 子智能体分解 + cron/睡眠任务（dreaming）；心跳机制已弃用 | ● 代码即计划（确定性 workflow）+ 子 workflow + Saga；无 LLM 动态规划 | ◐ TaskGraph + plan_written 动态计划 + Skill/Plan/ReAct 策略选择 |
| Tool 调用 | ● ToolNode 预置执行 + 并行工具 + MCP adapters + ValidationNode + interrupt 审批 | ● function tools 自动 schema + hosted tools + MCP + 并行调用 + guardrail + needs_approval | ● FunctionTool 自动 schema + MCP 双向（client/server）+ code_executor + Auth 体系 + 工具确认 HITL | ● server/client/MCP 三类工具 + skills + 内置工具（web_search/run_code）+ 审批模式；自动重试未确认 | ○ Activity 为通用执行原语（非 agent 工具）；agent tool 无直接对应，靠上层 cookbook 集成 | ● 自描述 schema + 输入/输出双端校验 + 失败归一化 + ask_user；无 MCP |
| Memory | ● 双层：checkpointer（thread 内状态快照，多后端）+ Store（跨 thread KV + 语义搜索） | ◐ Sessions（SQLite/Redis/SQLAlchemy/MongoDB/Dapr/OpenAI）+ 压缩；无内置向量长期记忆 | ● Session/State（短期）+ MemoryService（长期，Memory Bank/RAG 向量）+ preload/load_memory + compaction 摘要 | ● 签名维度：Memory blocks（常驻 context）+ Archival（向量）+ Recall（历史）+ MemFS（letta-code，git 记忆文件系统）+ compaction | ○ Event History + Memo + Search Attributes；agent 长期记忆无直接对应 | ○ 追加文件 + 全量注入；无检索/向量/摘要/遗忘 |
| Pause/Resume | ● interrupt() 动态中断 + 静态断点 + Command(resume) + time travel（replay/fork） | ◐ interruptions（工具审批）+ RunState 可序列化 checkpoint（跨进程恢复）；durable 编排需外部集成 | ◐ Session 持久化 + Resume（invocation_id 续跑）+ 动态工作流 Automatic Checkpointing + RequestInput/工具确认 + Rewind；无通用 checkpoint 快照 API（未确认） | ◐ 状态持久化 + /resume + AgentFile 导入导出 + background 可续流 + teleportation；无显式 pause 原语 | ● Signal/Query/Update + 阻塞等待审批 + Workflow Pause（新）+ Continue-As-New + 重放恢复 | ◐ 安全点暂停/恢复 + 最新 checkpoint 崩溃续跑；历史多 checkpoint 续跑未实现 |
| Trace/Observability | ◐ LangSmith 集成（可选、云端）+ 流式事件（多 stream_mode）+ Studio 可视化；本地 trace 依赖 LangSmith | ● 内置 tracing（traces/spans），默认导出 OpenAI 平台，30+ 第三方集成，draw_graph | ● Events 事件流 + OTel GenAI semconv（OTLP 导出）+ 默认脱敏 + GenAI 指标 | ◐ Runs & Steps（status/stop_reason/耗时/token）+ reasoning_message + trace/usage/metrics + hooks 事件；无独立 dashboard | ● Event History 审计 + Web UI + CLI + Visibility + OTel/Prometheus | ● 本地脱敏 JSONL trace（分层 boundary）+ Web 过程面板 + 计时 |
| 并发执行 | ● Pregel 每 super-step 并行 + Send 扇出 + ToolNode 并行工具 + 子图并行（有 checkpoint 冲突限制） | ◐ asyncio 原生 + parallel_tool_calls + 工具并发上限 + 实验性 hosted multi-agent | ◐ 并行工具（需 async）+ ParallelAgent + asyncio.gather/Go maxConcurrency + 线程池（max_workers=8）+ max_llm_calls=500 | ◐ App Server 多 agent 单进程管理 + 多客户端订阅 + 后台子智能体 + 多会话并行；显式并发上限未确认 | ● 并行 Activity + 子 workflow fan-out + Task Queue；百万级并发 workflow | ◐ 单任务内 wave 并行步骤（≤8）+ 任务队列/worker 池；单进程线程模型 |
| 失败恢复 | ● 节点级 RetryPolicy + error_handler（Saga 补偿）+ checkpoint 断点恢复 + durability 模式（sync 每步落盘） | ◐ max_turns=10 + timeout + opt-in 重试策略 + error_handlers；跨进程恢复无直接对应 | ◐ 2.0 自动重试（RetryConfig）+ Resume 断点续跑 + Rewind 回滚 + RoutedAgent 故障回退；无独立 recovery 策略对象 | ◐ Run/Step 失败语义完整（stop_reason 枚举 + error_data）+ compaction 溢出恢复 + abort；自动重试配置未确认（归应用层） | ● Retry Policy + 超时体系 + 确定性重放 + Saga 补偿 + 心跳 checkpoint | ◐ 失败分类 + 重试预算 + checkpoint 崩溃恢复；无补偿/回滚 |

---

## 4. 各项目速览

### 4.1 LangGraph
- **身份**：低层 agent 编排框架 + 运行时，官方定位 "low-level orchestration framework and runtime for building, managing, and deploying long-running, stateful agents"；Python 与 JS/TS 双官方实现；MIT；最新 langgraph 1.2.11（2026-08-11，PyPI）；付费托管原名 LangGraph Platform 已更名 **LangSmith Deployment**（[overview](https://docs.langchain.com/oss/python/langgraph/overview)、[PyPI](https://pypi.org/pypi/langgraph/json)）。
- **任务规划**：`StateGraph`（State + Nodes + Edges + reducer 更新语义）建模；条件边/条件入口动态路由；子图嵌入 + `Command(graph=Command.PARENT)` 跳回；Functional API（`@entrypoint`/`@task`）用普通 Python 控制流；默认 recursion_limit=1000 super-step；内置 LLM planner 原语未确认，plan-and-execute 属上层构建模式（[graph-api](https://docs.langchain.com/oss/python/langgraph/graph-api)、[functional-api](https://docs.langchain.com/oss/python/langgraph/functional-api)）。
- **Tool 调用**：预置 `ToolNode` 自动处理并行工具执行与错误；工具可注入 `ToolRuntime` 读图状态；`langchain-mcp-adapters` 提供 MCP 工具转换（Python/JS 双版本）；预置 `ValidationNode` 校验/重提示结构化输出；`interrupt()` 可在工具执行前暂停待人工审批（[workflows-agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)、[langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters)、[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)）。
- **Memory**：双层体系——checkpointer（短期、thread 内状态快照，InMemory/SQLite/Postgres/CosmosDB 后端）+ Store（长期、跨 thread KV，命名空间 put/get/search，支持语义搜索向量检索）；每 super-step 存一个 checkpoint；`DeltaChannel`（beta）只写增量减小体积（[persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)、[stores](https://docs.langchain.com/oss/python/langgraph/stores)）。
- **Pause/Resume**：动态 `interrupt(payload)` 任意位置暂停（需 checkpointer + thread_id），`Command(resume=...)` 恢复；静态断点 `interrupt_before/after`；time travel 用旧 checkpoint_id 重放或 `update_state` fork 新分支；多路并行 interrupt 可用 {id: value} 一次恢复（[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)、[use-time-travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)）。
- **Trace/Observability**：LangSmith 集成（`LANGSMITH_TRACING=true`），支持选择性 tracing_context 与 anonymizer 脱敏；流式事件多 stream_mode（values/updates/messages/checkpoints/tasks/debug）；LangSmith Studio 可视化调试（[observability](https://docs.langchain.com/oss/python/langgraph/observability)、[streaming](https://docs.langchain.com/oss/python/langgraph/streaming)）。
- **并发执行**：Pregel 运行时每 super-step 并行执行被选中 actor；多出边节点并行；Send API 动态扇出（map-reduce）；ToolNode 并行工具；per-thread 子图不支持并行工具调用（checkpoint 冲突，需 ToolCallLimitMiddleware）；全局并行度上限配置项未确认（[pregel](https://docs.langchain.com/oss/python/langgraph/pregel)、[graph-api](https://docs.langchain.com/oss/python/langgraph/graph-api)）。
- **失败恢复**：节点级 `RetryPolicy`（默认 max_attempts=3、0.5s、backoff 2.0、jitter，默认不重试 ValueError/TypeError 等）；`error_handler`（langgraph>=1.2）节点失败重试耗尽后接收 NodeError 返回 Command 路由到补偿分支（Saga）；checkpoint 断点恢复（同 super-step 已成功写入不重跑）；durability 模式 exit/async/sync（sync 每步落盘可崩溃恢复）；节点整体重跑要求幂等（[fault-tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)、[checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)）。
- **术语映射**：planning=Graph API/Functional API（无独立 planner 原语）；tool=ToolNode/tools/MCP adapters；memory=checkpointer+Store；pause/resume=interrupt+Command(resume)+time travel；observability=LangSmith tracing+streaming；concurrency=Send API/并行 super-step；recovery=retry_policy/error_handler/checkpoint。

### 4.2 OpenAI Agents SDK
- **身份**：轻量级多智能体编排库（Agent framework），Python 主库（另有 TS 版 openai-agents-js）；MIT；最新 0.22.0（2026-08-19，PyPI）；不含自托管运行时，但内置 tracing 默认导出 OpenAI 平台（[PyPI](https://pypi.org/project/openai-agents/)、[docs](https://openai.github.io/openai-agents-python/)）。
- **任务规划**：`Runner` 内置 agent loop（LLM 决策 → final output / handoff / tool calls → 重跑，超 `max_turns` 抛 `MaxTurnsExceeded`）；编排分 LLM 决策（handoffs、agents-as-tools）与代码编排（chaining / while 循环 / `asyncio.gather`）；文档明确**无声明式 workflow/DAG 节点图原语**；Guardrails 承担输入/输出校验节点（默认并行、可阻塞 fail-fast）（[multi_agent](https://openai.github.io/openai-agents-python/multi_agent/)、[handoffs](https://openai.github.io/openai-agents-python/handoffs/)、[guardrails](https://openai.github.io/openai-agents-python/guardrails/)）。
- **Tool 调用**：`@function_tool` 自动生成参数 JSON Schema 并校验；hosted tools（WebSearch/FileSearch/CodeInterpreter 等）；MCP 支持 Stdio/SSE/StreamableHttp + 托管 HostedMCPTool；并行调用由 `ModelSettings.parallel_tool_calls` + `ToolExecutionConfig.max_function_tool_concurrency` 控制；`tool_input/output_guardrail`；`needs_approval` 产生 ToolApprovalItem（[tools](https://openai.github.io/openai-agents-python/tools/)、[mcp](https://openai.github.io/openai-agents-python/mcp/)、[running_agents](https://openai.github.io/openai-agents-python/running_agents/)）。
- **Memory**：Sessions 会话记忆（run 前后自动取回/存储历史），内置 SQLite/Redis/SQLAlchemy/MongoDB/Dapr/OpenAI Conversations 实现 + `OpenAIResponsesCompactionSession` 压缩 + `SessionSettings(limit)` 等旋钮；**无内置向量/语义长期记忆**（[sessions](https://openai.github.io/openai-agents-python/sessions/)）。
- **Pause/Resume**：工具审批时 run 暂停产生 interruption；`result.to_state()` → `RunState`（`approve()/reject()/add_input()`），可 `to_json()/from_json()` 序列化为 checkpoint 跨进程恢复；非内建 durable 编排需 Dapr/Temporal/Restate/DBOS 集成（[human_in_the_loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)、[running_agents](https://openai.github.io/openai-agents-python/running_agents/)）。
- **Trace/Observability**：内置 tracing 默认开启（task/turn/agent/generation/function/guardrail/handoff span），默认导出 OpenAI Traces dashboard；`add_trace_processor()` 可换导出目标；30+ 第三方观测集成；`trace_include_sensitive_data` 控制敏感数据；`draw_graph()` 结构可视化（[tracing](https://openai.github.io/openai-agents-python/tracing/)）。
- **并发执行**：asyncio 原生；并行工具调用两层控制；guardrail 与 agent 并行执行；实验性 hosted multi-agent（`max_concurrent_subagents`）；SDK 全局并发池是否存在未说明（未确认）（[multi_agent](https://openai.github.io/openai-agents-python/multi_agent/)、[models](https://openai.github.io/openai-agents-python/models/)）。
- **失败恢复**：`max_turns` 默认 10（源码 run_config.py）；`ModelSettings.timeout` 单次尝试超时；重试为 opt-in（`ModelRetrySettings` + retry_policies，默认不重试）；run 级 `error_handlers`（max_turns/model_refusal/invalid_final_output）；工具 `timeout_behavior`（error_as_result / raise_exception）；跨进程恢复无直接对应，依赖外部 durable 集成（[running_agents](https://openai.github.io/openai-agents-python/running_agents/)、[models](https://openai.github.io/openai-agents-python/models/)）。
- **术语映射**：planning=handoffs/agents-as-tools/agent loop（无独立 planner、无声明式 DAG）；tool=function/hosted/MCP tools；memory=Sessions；pause/resume=interruptions+RunState；observability=tracing；concurrency=parallel tool calls/asyncio.gather；recovery=retry policies/error_handlers（跨进程恢复无直接对应）。

### 4.3 Temporal
- **身份**：通用 Durable Execution / 工作流编排平台（非 Agent 专用底座）；服务端 Go 编写 + 外部数据库，MIT；8 种官方 SDK（Go/Java/Python/TS/.NET/Ruby/PHP/Rust）；最新 v1.31.2（2026-07-08）；自托管 + SaaS Temporal Cloud（[docs.temporal.io](https://docs.temporal.io/temporal.md)、[GitHub](https://api.github.com/repos/temporalio/temporal)）。
- **任务规划**：计划即确定性代码（Workflow Definition），分支/循环/定时器为普通语言结构 + 持久化 Timer；Child Workflow 分区块执行；Saga 为官方 pattern；确定性约束：重放必须以相同 Event History 作出相同决策（不得直接调 Date.now/随机数）（[workflows](https://docs.temporal.io/workflows.md)、[child-workflows](https://docs.temporal.io/child-workflows.md)、[saga-pattern](https://docs.temporal.io/design-patterns/saga-pattern.md)）。
- **Tool 调用**：**明确不是 agent 工具调用框架**；对应原语为 Activity（单一明确定义的执行单元，heartbeat 证明存活、可带进度 checkpoint、异步完成、Local Activity）；agent tool 概念无直接对应，官方 AI Cookbook 提供 tool calling 示例与 OpenAI Agents SDK/LangGraph/ADK 集成（[activities](https://docs.temporal.io/activities.md)、[ai](https://docs.temporal.io/ai.md)）。
- **Memory**：Event History（append-only 事件日志，崩溃后重放重建）+ Memo（非索引元数据，40KB）+ Search Attributes（索引元数据）；**agent 式长期记忆无直接对应**，业务数据经 Activity 存外部数据源（[event-history](https://docs.temporal.io/encyclopedia/event-history.md)、[search-attribute](https://docs.temporal.io/search-attribute.md)）。
- **Pause/Resume**：Signal/Query/Update 三种消息；human-in-the-loop 用阻塞等待（`workflow.wait_condition()` 等）直到收到审批 Signal；新 Workflow Pause（Server v1.30+ 预发布）；Continue-As-New 长期运行；崩溃恢复为**从头重放 Event History**（非内存快照）+ Reset（[approval](https://docs.temporal.io/design-patterns/approval.md)、[workflow-pause](https://docs.temporal.io/encyclopedia/workflow/workflow-pause.md)、[workflows](https://docs.temporal.io/workflows.md)）。
- **Trace/Observability**：Event History 即审计日志；Web UI（时间线/JSON 下载/Pending Activities/Call Stack）；CLI；Visibility（Search Attributes 过滤，最终一致）；SDK 指标（Prometheus/OpenTelemetry）（[web-ui](https://docs.temporal.io/web-ui.md)、[visibility](https://docs.temporal.io/visibility.md)）。
- **并发执行**：并行 Activity（Future/Promise/asyncio.gather）；Child Workflow fan-out（单父 in-flight 上限 2000）；Task Queue（默认 4 partition）+ Worker 槽位配置；平台支持百万到十亿级并发 Workflow Executions（[parallel-execution](https://docs.temporal.io/design-patterns/parallel-execution.md)、[task-queue](https://docs.temporal.io/task-queue.md)）。
- **失败恢复**：Retry Policy 默认 1s/2.0/100s/∞，Activity 默认自动重试、Workflow 默认不重试；完整超时体系（S2S/S2C/Heartbeat/Workflow）；确定性重放实现平台级透明恢复；Heartbeat 检查点续跑；Saga 补偿（幂等要求）（[retry-policies](https://docs.temporal.io/encyclopedia/retry-policies.md)、[saga-pattern](https://docs.temporal.io/design-patterns/saga-pattern.md)）。
- **术语映射**：planning=Workflow Definition（无独立 planner）；tool=Activity（非 agent 工具，无直接对应）；memory=Event History/Memo/Search Attributes（agent 长期记忆无直接对应）；pause/resume=Signal+阻塞等待/Workflow Pause/Continue-As-New/重放；observability=Event History+Web UI+Visibility+OTel；concurrency=并行 Activity/Child Workflow/Task Queue；recovery=Retry Policy/超时/重放/Saga/心跳 checkpoint。

### 4.4 Letta (MemGPT)
- **身份**：有状态智能体（stateful agent）平台/运行时 + 开发框架，官方定位 "Platform for stateful agents: AI with advanced memory that can learn and self-improve"；letta-ai/letta 仓库已转 landing page，V1 服务端（Python/FastAPI）归档在 archive 分支不再维护，当前实现为 letta-ai/letta-code（TypeScript stateful agent harness + CLI + 桌面/Web + App Server）；Apache-2.0（历史 AGPL 拆分未确认）；V1 最新 v0.16.8（2026-05-14），letta-code npm 0.30.32（[GitHub](https://github.com/letta-ai/letta)、[letta-code](https://github.com/letta-ai/letta-code)、[blog](https://www.letta.com/blog/announcing-letta)）。
- **任务规划**：V1 agent loop（每个动作都是工具调用，`request_heartbeat` 请求继续，新版已弃用 heartbeat）；letta-code 用内置 7 种子智能体（fork/general-purpose/recall/reflection 等）做任务分解与并行；`letta cron` 定时任务（云计划离线照常触发、本地计划每 agent 上限 50 个）；后台记忆巩固 dreaming（sleeptime）；一 agent 多 conversations 并行线程（[subagents](https://docs.letta.com/configuration/subagents/)、[schedules](https://docs.letta.com/configuration/schedules/)、[blog letta-v1-agent](https://www.letta.com/blog/letta-v1-agent)）。
- **Tool 调用**：V1 三类工具——server tools（sandbox 内）/ client tools（应用内）/ MCP tools（外部 MCP server），命名空间 `mcp__<server>__<tool>`；内置 web_search（Exa）、fetch_webpage、run_code（E2B 沙箱）；skills 可动态加载/卸载；人工审批 V1 approval 消息 + letta-code 权限模式（strict=每个工具批准）；**工具失败自动重试：未确认**（[builtin-tools](https://docs.letta.com/v1-sdk/tools/builtin-tools)、[mcp](https://docs.letta.com/agent-sdk/mcp)、[permissions](https://docs.letta.com/configuration/permissions/)）。
- **Memory（签名维度）**：V1 三层——Memory blocks（core memory，常驻 context 的结构化文本段，prepend 进 system prompt，persona/human 默认 label，agent 可自改）+ Archival memory（通用向量库语义检索，agent-immutable，passage 300 tokens）+ Recall memory（会话历史持久化，compaction 后仍可检索）；上下文分层 Memory blocks → Files(5MB) → Archival → 外部 RAG；自动 compaction 做压力管理。letta-code 改为 **MemFS**（每 agent 记忆 = 专属 git 仓库，`system/` 目录每轮注入 system prompt，按路径寻址、git commit 版本历史）+ shared memory（组织级共享 git 仓库）+ dreaming 后台巩固；语义/向量检索默认关闭（需 Search mod）（[memory-blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks)、[archival-memory](https://docs.letta.com/v1-sdk/memory/archival-memory)、[context-hierarchy](https://docs.letta.com/v1-sdk/memory/context-hierarchy)、[memfs](https://docs.letta.com/concepts/memfs/)）。
- **Pause/Resume**：无显式 pause 原语，属"状态保存/加载"模型——agent 全状态持久化于数据库；`/resume`、`--conv <id>` 恢复会话；AgentFile (.af) 导入/导出完整重建 agent；V1 background mode + resumable streaming（run_id/seq_id + `starting_after` 光标续流，断线可续）；Teleportation 跨电脑迁移进行中会话（[long-running](https://docs.letta.com/v1-sdk/messages/long-running)、[conversations](https://docs.letta.com/concepts/conversations/)、[agent-file](https://docs.letta.com/v1-sdk/concepts/agent-file/)）。
- **Trace/Observability**：V1 Runs & Steps（status/stop_reason/total_duration_ns/ttft_ns/token 用量）+ 每 run/step 的 trace/usage/metrics 子资源；message types 含 reasoning_message（内部推理，带 source/signature）；letta-code App Server stream_delta 事件流 + hooks/mods 生命周期事件（turn_start/turn_end、tool_start/tool_end）+ /status、/context、/doctor；无独立可视化 dashboard（[runs](https://docs.letta.com/api/python/resources/runs/)、[message-types](https://docs.letta.com/v1-sdk/messages/message-types)、[hooks](https://docs.letta.com/letta-code/hooks)）。
- **并发执行**：App Server 单进程并行管理多 agent，/ws 多并发客户端、多连接可订阅同一 runtime；V1 background mode 解耦执行与连接；后台子智能体并行；一 agent 与多用户并发消息；headless `--new` 并行会话；**显式并发上限配置：未确认**（[app-server](https://docs.letta.com/platform/app-server/)、[headless](https://docs.letta.com/platform/cli/headless/)）。
- **失败恢复**：V1 Run 级失败语义完整（status "failed" + stop_reason 枚举：error/llm_api_error/invalid_llm_response/invalid_tool_call/max_steps/max_tokens_exceeded/requires_approval/context_window_overflow_in_system_prompt 等）+ Step error_data/error_type + callback_url；App Server loop_error/error_message、abort_message 中止 turn、requires_approval 为继续边界；上下文溢出靠自动 compaction 恢复；**显式自动重试配置：未确认**（官方把 retry policy 划给应用层）（[runs](https://docs.letta.com/api/python/resources/runs/)、[protocol-lifecycle](https://docs.letta.com/platform/app-server/protocol-lifecycle/)）。
- **术语映射**：planning=agent loop/runs&steps/subagents/cron/dreaming；tool=tools/skills/server|client|MCP tools；memory=memory blocks/MemFS/archival/recall/shared；pause/resume=无 pause 原语（状态持久化+会话恢复+AgentFile+可续流+teleportation）；observability=messages/runs&steps/trace/metrics/stream_delta/hooks；concurrency=multi-agent/conversations/后台子智能体；recovery=无 retry 配置（stop_reason 语义+loop_error+abort+compaction）。

### 4.5 Google ADK
- **身份**：开源 agent 框架（code-first 开发库）+ 自带运行时服务器与前端，官方定位 "An open-source, code-first Python framework for building, evaluating, and deploying sophisticated AI agents"；Python 主实现（另有 TS/Go/Java/Kotlin SDK，2.0 Workflow Runtime 仅 Python/Go）；Apache-2.0；最新 google-adk 2.7.1（2026-08-17，PyPI，约每两周一版）；自带 CLI（adk run/web/api_server/eval）+ REST API server（默认 localhost:8000）+ Dev UI（[PyPI](https://pypi.org/project/google-adk/)、[GitHub](https://github.com/google/adk-python)）。
- **任务规划**：agent types（`LlmAgent` + 模板 workflow agents Sequential/Loop/Parallel，确定性编排）+ ADK 2.0 图工作流 `Workflow`（edges 定义节点与条件路由，动态工作流 `@node`/`ctx.run_node` 支持循环/递归）+ **显式 planner**（`BuiltInPlanner` 利用 Gemini thinking、`PlanReActPlanner` 强制 PLANNING/ACTION/REASONING/FINAL_ANSWER 结构输出）+ `AgentTool`/`transfer_to_agent` 层级委托 + Task API + 实验性 RoutedAgent（TS，按复杂度路由）（[llm-agents](https://adk.dev/agents/llm-agents/)、[graphs](https://adk.dev/graphs/)、[workflow-agents](https://adk.dev/agents/workflow-agents/)）。
- **Tool 调用**：普通函数自动包装 `FunctionTool`（类型注解生成 schema）；MCP 双向——`McpToolset` 作客户端接入外部 MCP server，也可把 ADK 工具暴露为 MCP server；`code_executor=BuiltInCodeExecutor()` 代码执行；`AuthScheme`/`AuthCredential` 认证体系（OAuth2 等）；`input/output_schema` 结构化输出；工具确认 HITL（`require_confirmation`/`request_confirmation`）；`LongRunningFunctionTool` 长任务（[function-tools](https://adk.dev/tools-custom/function-tools/)、[mcp-tools](https://adk.dev/tools-custom/mcp-tools/)、[confirmation](https://adk.dev/tools-custom/confirmation/)）。
- **Memory**：三层——`Session`（events 历史）+ `State`（session.state 短期记忆）+ `MemoryService`（长期跨会话知识：`add_session_to_memory`/`add_memory`/`search_memory`）；内置实现 InMemory（默认，重启即失）/ VertexAiMemoryBankService（LLM 抽取合并 + 语义检索）/ VertexAiRagMemoryService（Knowledge Engine 向量检索）；`preload_memory` 每轮预取、`load_memory` 按需检索、`after_agent_callback` 自动写入；`EventsCompactionConfig` + `LlmEventSummarizer` 会话摘要压缩（[sessions/memory](https://adk.dev/sessions/memory/)、[compaction](https://adk.dev/context/compaction/)）。
- **Pause/Resume**：Session 持久化由 `SessionService` 管理（InMemory/Database/VertexAi 后端）；`ResumabilityConfig(is_resumable=True)` + invocation_id 断点续跑（工具可能至少执行一次、恢复时重跑）；动态工作流 **Automatic Checkpointing**（恢复时跳过已完成节点，`rerun_on_resume` 控制）；HITL 中断——工具确认 + 图工作流 `yield RequestInput(...)` 暂停等用户输入；`rewind_async` 回滚会话状态；无通用 checkpoint 快照 API（未确认）（[resume](https://adk.dev/runtime/resume/)、[human-input](https://adk.dev/graphs/human-input/)、[rewind](https://adk.dev/sessions/session/rewind/)）。
- **Trace/Observability**：Events 事件流为核心（author/invocation_id/actions/error_code/error_message 字段）；OTel GenAI Semantic Conventions + OTLP 导出（`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`、`adk web --otel_to_cloud`）；span 层级 invoke_agent→invoke_workflow→execute_tool→generate_content；prompt 默认脱敏（`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` 控制）；GenAI 指标（gen_ai.invoke_agent.duration 等）；session export 未确认（[observability](https://adk.dev/observability/)、[events](https://adk.dev/events/)）。
- **并发执行**：并行工具调用（Python 1.10+，要求 async 函数，同步会阻塞）；`ParallelAgent` 并发子代理（分支独立不共享 state）；动态工作流 asyncio.gather / Go `NewParallelWorker(maxConcurrency)`；`RunConfig`（max_llm_calls 默认 500）+ `tool_thread_pool_config(max_workers=8)`；TS AbortSignal 取消（[performance](https://adk.dev/tools-custom/performance/)、[runconfig](https://adk.dev/runtime/runconfig/)）。
- **失败恢复**：ADK 2.0 框架自动重试（`RetryConfig(max_attempts=3)`，工具内吞异常会禁用自动重试）；错误事件 error_code/error_message；Resume 断点续跑（工具 C 失败时保留 A/B 结果重跑 C）；Rewind 回滚会话级状态；RoutedAgent 失败回退；无独立 recovery 策略对象（[2.0](https://adk.dev/2.0/)、[resume](https://adk.dev/runtime/resume/)）。
- **术语映射**：planning=agent types/workflows/planner 参数（无独立 planner 服务）；tool=function calling/McpToolset/code_executor；memory=Session State（短期）+ MemoryService（长期）+ compaction；pause/resume=Resume（invocation_id）+ Automatic Checkpointing + confirmation/RequestInput + Rewind（无通用 checkpoint 快照 API，未确认）；observability=Events + OTel Telemetry；concurrency=Parallel；recovery=Retry（RetryConfig）+ Resume/Rewind/故障回退。

---

## 5. Ella 差异化潜力方向（3 个）

结论基于对比总表与逐项目证据；每个方向说明「为什么对手做不到/没做」。

### 5.1 事件驱动的 Presence / Ambient 常驻运行时（always-on local companion）
- **现状**：Ella 的核心链路是 RawSignal → Event Trigger Pipeline → Session-aware Router → Presence Runtime → Interruption Policy（`runtime/presence_runtime.py`、`runtime/event_router.py`、`runtime/interruption_policy.py`），配合本地多模态感知（摄像头/麦克风/屏幕，`devices/`、`tools/camera_scene.py` 等）。对比的 5 个项目全部是「任务发起式」调用模型（LangGraph invoke、OpenAI SDK run、ADK runner、Letta conversation、Temporal signal/start）：有 session、有事件流（ADK 的 Events、Temporal 的 Signal），但**没有「常驻等待 + 打扰策略 + 背景状态」这一层**——没有一个项目把「判断某个事件值不值得打断用户」做成 Runtime 的一等概念。
- **差异化价值**：生活伴侣/个人助理场景（Ella 的定位）天然是事件驱动的：环境变化、时间、用户随口一句话都可能触发任务。Ella 的 Presence + Interruption Policy 是这 5 个项目都不覆盖的空白位。本地优先（默认绑定 127.0.0.1、媒体不入库、mock-first）进一步构成隐私差异化。
- **注意**：这是「方向」而非「当前已验证能力」——ambient 低频感知（疲劳/久坐提醒）在 PRD 中仍属规划（design_report §2.3）。

### 5.2 零云依赖的本地全链路可观测（脱敏 JSONL + Web 过程面板）
- **现状**：TraceRecorder 把每次执行写成带自动脱敏（secret/path/raw media）的分层 JSONL（boundary 细分 task_graph → task_node → reasoning → step → tool_node → tool_attempt，`runtime/trace.py`），Web 过程面板展示 task goal、tool results、prompt、timing、memory 状态，RuntimeTiming 记录各阶段耗时。
- **对比**：LangGraph 的可观测依赖 LangSmith（云端）；OpenAI SDK 默认导出 OpenAI 平台；ADK 走 OTLP 导出（默认倾向 Google Cloud，虽内置脱敏）；Letta 无独立 dashboard（API 级观测）；Temporal 需要部署 Server + UI。Ella 是 6 个项目中唯一「开箱即本地、零云依赖、脱敏内建、带过程面板」的可观测形态。
- **差异化价值**：对「本地个人智能体」而言，可解释 + 可审计 + 隐私优先（脱敏内建）是用户信任的关键；对手要么默认把数据送云，要么需要自建基础设施。

### 5.3 「安全执行语义」打包：目标验证 + 失败分类 + 安全点暂停/恢复 + checkpoint 崩溃续跑
- **现状**：Ella 把可靠性做成了 Runtime 一等公民：`VerificationAgent` 目标验证（goal_state + recoverable + feedback_for_execution，`agent/verification.py`）、工具失败分类（retryable / safe_to_retry / ToolFailureObservation，`docs/tool_failure_prd.md`）、UNCERTAIN 状态（wave 中不可确认节点）、安全点暂停/恢复（paused_at_safe_point、kill>pause 优先级）、TaskStore 原子 checkpoint + 进程重启自动续跑（`_restore_from_checkpoints`）。
- **对比**：LangGraph/Temporal 的恢复是通用重试/重放，**不做「目标是否真的达成」的语义验证**；ADK 有 Resume/checkpoint 但明确「工具可能重跑」；OpenAI SDK/Letta 的重试基本归应用层。Ella 的「验证目标达成 → 判定可恢复 → 从安全边界续跑」组合在 6 个项目中是独一份的。
- **差异化价值**：这是「本地 Runtime 可靠性的完整打包」，可以成为 Ella 对外叙事里最硬的能力点（代码已实现，非仅 PRD）。

---

## 6. Ella 最明显的短板（3 个）

### 6.1 Memory：6 个项目中明显最弱
- **现状**：`MemoryManager` 追加式 markdown 文件 + 查询时全量读取注入 final response prompt（`memory/manager.py`）；无检索、无向量、无摘要、无窗口、无遗忘策略（design_report 明确这是刻意的最小版本）。
- **对比差距**：LangGraph checkpointer + Store（含语义搜索）、ADK MemoryService（Memory Bank/RAG + compaction）、Letta 三层记忆（core blocks / archival 向量 / recall 历史，当前为 MemFS）、OpenAI Sessions + 压缩，甚至 Temporal 都有 Event History + Search Attributes。Ella 的 Memory 与所有对手都不在同一水平线，是全表最刺眼的 ○。
- **影响**：长对话/长期个人数据场景（生活伴侣的核心场景）直接不可用；这也是 token 成本失控的源头。

### 6.2 生态接入：无 MCP、provider 单一、无标准可观测导出
- **现状**：`mcp/` 目录为空（无 MCP 实现）；LLM provider 仅 Qwen/DashScope + DeepSeek（`providers/`）；trace 只落本地 JSONL，无 OTLP/LangSmith 类导出；Python 单进程，无多语言 SDK。
- **对比差距**：LangGraph（langchain-mcp-adapters）、OpenAI SDK（Stdio/SSE/StreamableHttp + HostedMCP）、ADK（MCP 双向 client/server）、Letta（MCP tools）全部内置 MCP；ADK/OpenAI/Temporal 均有 OTel/Prometheus 类标准导出。Ella 目前是唯一没有 MCP 和标准观测协议的项目——工具生态和集成能力被锁死在本项目内部。

### 6.3 编排深度与生产级可靠性不足
- **现状**：规划是 plan_written 写一次性结构化计划 + TaskGraph wave 执行，**没有重规划/反思循环**；无补偿/Saga 机制；多 checkpoint 历史续跑只有 PRD（`docs/checkpoint_history_restore_prd.md`，明确未实现）；并发是单进程线程模型（无 durable replay、无跨进程）；HITL 只有 ask_user_question 单工具（无通用 interrupt 原语）。
- **对比差距**：ADK 有显式 planner（BuiltInPlanner / PlanReActPlanner），LangGraph 有条件路由 + time travel，Temporal 有确定性重放 + Saga + 完整重试/超时体系；LangGraph error_handler 与 Temporal Saga 提供补偿，Ella 没有。任务一旦计划失误或产生副作用后失败，Ella 缺少「优雅回退」路径。

---

## 7. 未来 4 周迭代优先级计划

优先级逻辑：先补「对比中最刺眼且自研可控」的短板（Memory、生态接入），再做「已有 PRD、改动边界清晰」的恢复/HITL 增强，最后做可观测导出与规划增强。每周含目标、为什么、交付物与验收标准。

### Week 1 — Memory 最小可行升级（对标 Letta / ADK / LangGraph 的最低差距）
- **目标**：把「全量追加 + 全量注入」升级为「最近窗口 + 任务摘要 + 轻量本地检索」，让长期记忆在 prompt token 与可用性之间取得平衡。
- **为什么**：§6.1 是全表最大短板；也是生活伴侣场景的前提。
- **交付物**：
  1. `MemoryManager` 查询策略可配置：recent-window（最近 N 条）、按 task_type 过滤、按摘要注入（对旧记录先做摘要）。
  2. 可选本地轻量检索：SQLite + 简单 embedding（模型无关、mock 可测），不引入外部向量库。
  3. 与 PromptEngine 的 prompt-cache 成本控制对齐（design_report §4.3 已列此权衡）。
- **验收**：长记忆场景下注入 prompt 的 token 显著下降且最终回答质量不回退；现有 memory 相关测试全绿。

### Week 2 — 生态接入：MCP 客户端 + provider 抽象扩展（对标 LangGraph / OpenAI / ADK / Letta）
- **目标**：让 Ella 能调用外部 MCP 工具，并支持 OpenAI-compatible 端点，打破生态封闭。
- **为什么**：§6.2 的「无 MCP」使 Ella 与 4 个框架项目差一个时代；这是投入产出比最高的生态动作。
- **交付物**：
  1. `mcp/` 实现 MCP 客户端（stdio / streamable-http），工具发现（list_tools）→ 映射到现有 `ToolDefinition` → 复用 CapabilityExecutor 的输入/输出 schema 校验与失败归一化。
  2. `ToolManager` 支持注册 MCP 工具并纳入角色可见性。
  3. provider 增加 OpenAI-compatible base_url 配置（复用现有 Qwen/DeepSeek 接入模式）。
- **验收**：用一个 mock MCP server 完成端到端调用；新增工具走通 schema 校验、失败归一化、trace 记录。

### Week 3 — 恢复与 HITL：多 checkpoint 历史续跑 + 通用 interrupt（实现已有 PRD）
- **目标**：落地 `docs/checkpoint_history_restore_prd.md`，并把 ask_user 升级为通用 interrupt/resume 原语。
- **为什么**：§6.3 与 §5.3 的交汇点——「历史 checkpoint 续跑」是 PRD 已定义、改动边界清晰的高价值能力；ADK 的 Automatic Checkpointing 与 LangGraph 的 time travel 已证明这是 Runtime 的标配能力。
- **交付物**：
  1. TaskStore 支持保留多语义 checkpoint（在 TaskGraph 安全边界），用户可从 Web UI 选择恢复位置。
  2. 历史续跑创建新 Task（新 task_id/trace_id），源 Task 执行权转移后不可再次续跑；已成功副作用不重放（沿用 PRD 第 7 条原则）。
  3. 通用 interrupt/resume 原语：把 `ask_user_question` 的 InteractionBroker 泛化为可暂停/恢复的执行边界（含序列化与崩溃后恢复）。
- **验收**：进程重启 + 历史 checkpoint 续跑集成测试通过；恢复分支与源 Task 互斥；Web UI 可展示并选择恢复点。

### Week 4 — 可观测导出 + 规划增强（重规划循环）+ 自测基准
- **目标**：trace 对齐标准协议（便于接入外部观测），给规划补上「失败后重规划」闭环，并建立 7 维度自测基准。
- **为什么**：§5.2 的本地可观测若支持 OTLP/JSON 导出则兼顾「本地 + 可集成」；§6.3 的重规划缺失会导致复杂任务一次计划失误即失败。
- **交付物**：
  1. TraceRecorder 增加 JSON/OTLP 导出器（对齐 OTel GenAI semconv 的 span 命名，脱敏策略复用现有 _redact）。
  2. 重规划循环：STEP 节点失败且 retry 耗尽时，触发 plan 修订（新 PlanStore 版本，parent_version_id 关联）而非直接 FAIL；沿用 UNCERTAIN 语义。
  3. `benchmark/` 自测脚本：覆盖 7 个维度（规划/工具/Memory/暂停恢复/可观测/并发/失败恢复）的本地回归基准，输出对比报告。
- **验收**：本地 OTLP collector 可接收 Ella trace；replan 场景测试通过（含预算上限）；基准脚本产出可复现报告。

> 4 周计划的前提约束：全部改动保持现有架构边界（Runtime 管生命周期、SubAgent 决策、Executor 单步执行、MemoryManager 唯一读写入口、UI 不直接触 Runtime），并维持 mock-first 可测性。

---

## 8. 参考来源

> 全部为各项目官方资料（2026-08 前后抓取）；详细分节引用见 §4 各项目速览内嵌链接。

**LangGraph（LangChain）**
- 官方文档：https://docs.langchain.com/oss/python/langgraph/overview （graph-api / persistence / checkpointers / stores / interrupts / use-time-travel / fault-tolerance / functional-api / streaming / observability / workflows-agents / pregel / use-subgraphs / deploy 等子页）
- PyPI：https://pypi.org/pypi/langgraph/json ｜ GitHub Releases：https://api.github.com/repos/langchain-ai/langgraph/releases ｜ LICENSE：https://raw.githubusercontent.com/langchain-ai/langgraph/main/LICENSE
- MCP：https://github.com/langchain-ai/langchain-mcp-adapters ｜ 更名公告：https://changelog.langchain.com/announcements/product-naming-changes-langsmith-deployment-and-langsmith-studio

**OpenAI Agents SDK**
- 官方文档：https://openai.github.io/openai-agents-python/ （running_agents / multi_agent / handoffs / tools / mcp / sessions / human_in_the_loop / tracing / guardrails / models 等子页）
- PyPI：https://pypi.org/project/openai-agents/ ｜ 源码：https://github.com/openai/openai-agents-python （run_config.py：DEFAULT_MAX_TURNS=10）

**Google ADK**
- 官方文档：https://adk.dev/ （get-started / agents/llm-agents / agents/workflow-agents / graphs / graphs/dynamic / events / sessions / sessions/memory / runtime/resume / runtime/runconfig / observability / context/compaction / tools-custom/* 等子页）
- PyPI：https://pypi.org/project/google-adk/ ｜ GitHub：https://github.com/google/adk-python

**Letta (MemGPT)**
- 官方文档：https://docs.letta.com/ （v1-sdk/memory/memory-blocks / archival-memory / context-hierarchy / concepts/memfs / configuration/subagents / schedules / memory / platform/app-server / api/python/resources/runs 等子页）
- GitHub：https://github.com/letta-ai/letta 、https://github.com/letta-ai/letta-code ｜ 官方博客：https://www.letta.com/blog/announcing-letta 、https://www.letta.com/blog/letta-v1-agent ｜ npm：https://www.npmjs.com/package/@letta-ai/letta-code

**Temporal**
- 官方文档：https://docs.temporal.io/ （temporal.md / workflows.md / activities.md / design-patterns/approval / saga-pattern / encyclopedia/retry-policies / event-history / task-queue / cloud/limits 等子页；llms.txt 索引：https://docs.temporal.io/llms.txt）
- GitHub：https://github.com/temporalio/temporal ｜ Releases API：https://api.github.com/repos/temporalio/temporal/releases/latest

**Ella（本仓库自评）**
- README.md、design_report.md、docs/architecture.md、docs/checkpoint_history_restore_prd.md、docs/tool_failure_prd.md、docs/task_step_tool_graph_prd.md；代码：runtime/task_runtime.py、runtime/trace.py、runtime/task_store.py、runtime/interactions.py、tasks/graph.py、memory/manager.py、agent/verification.py、tools/plan.py

---

## 9. 局限性与未确认项

- 结论基于 2026-08 前后公开资料，未对对手做源码级逐行审计；能力描述以官方文档/README/release 为准。
- 标注「未确认」的项不代表不存在，只代表本次公开资料不足以确认。汇总如下：
  - LangGraph：内置 LLM planner 原语（未确认）；全局并行度上限配置项（未确认）。
  - OpenAI Agents SDK：SDK 全局并发池/总并发上限（未确认）；sessions 是否仍为 beta（历史标注未确认）。
  - Google ADK：通用 checkpoint 快照 API（未确认）；session export 功能（未确认）。
  - Letta：历史 AGPL 拆分（未确认）；工具失败自动重试配置（未确认，官方把 retry policy 划给应用层）；显式并发上限配置（未确认）；V1「recall memory」术语在现行文档中的存续（未确认）。
  - Temporal：报告中全部事实均有来源、无未确认项（未证实内容已省略而非猜测）。
- 版本时效注意：Letta V1（Python 服务端）已归档不再维护，当前实现为 letta-code（TypeScript）；LangGraph 托管平台更名 LangSmith Deployment；ADK 2.0 Workflow Runtime 仅 Python/Go；Temporal Workflow Pause 为预发布功能（Server v1.30+）。这些会影响后续版本对比结论。
- Ella 侧结论基于本仓库代码与 `docs/` 内 PRD；PRD 中标注「尚未实现」的能力（如历史多 checkpoint 续跑、ambient 低频感知）未计入已具备能力。
- 评分符号为相对定性判断（●/◐/○），用于快速定位差距，具体依据见 §4 逐项目证据。

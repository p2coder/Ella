> [!WARNING]
> 本文档已被 `docs/runtime_tools_workflow_prd.md` 取代，仅保留为历史记录；其中的旧 DAG、route、presence、handoff 与多标识设计不再是现役契约。

# Ella Prompt 结构与 Tool 描述优化 PRD

## 1. 文档目的

本文档定义 Ella Prompt 结构稳定化、模型可见 Tool 描述优化和 Provider 缓存用量聚合的实现要求。

本轮改造解决三个问题：

1. 当前 Prompt 中稳定内容与高频变化内容交错，降低相同任务多轮推理时的前缀缓存利用率。
2. Tool 的适用场景、禁止场景和执行语义分散在 Tool 描述与决策模板中，导致重复、耦合和规则冲突。
3. 当前前端缓存指标主要反映最近一次 Provider 调用，无法准确表达一个任务内全部 LLM 调用的缓存使用情况。

本 PRD 不引入 Runtime 级 Tool 选择策略。Tool 是否使用、使用哪个 Tool，继续由模型根据用户输入、任务上下文和模型可见的 ToolDefinition 自主判断。

## 2. 设计原则

### 2.1 Prompt Engine 保持封装

Prompt Engine 只接收结构化上下文并输出最终 Prompt 字符串。

外部模块不得依赖：

- Prompt Block 的内部排序。
- Tool 或 Skill 在 Prompt 中的具体渲染格式。
- 分隔符、字段顺序或 JSON 缩进方式。
- SystemPrompt、Instruction 或 OutputContract 的具体文本。

Prompt Engine 不调用 Provider，不执行 Tool，不读写 Memory，也不修改 Task 或 Runtime 状态。

### 2.2 Tool 选择由模型负责

系统不增加以下运行时概念：

- `selection_policy`
- `selection_order`
- Tool 路由表
- 基于关键词的 Tool 选择代码
- Runtime 强制 Tool 优先级

Tool 的模型可见选择信息全部包含在现有 `ToolDefinition.description` 中。Runtime 只负责提供当前任务可见的 ToolDefinition、校验调用并执行模型选中的 Tool。

### 2.3 稳定内容在前，动态内容在后

Prompt 应优先放置跨调用稳定的内容，并把 observations、Step 状态、失败记录等高频变化内容放到后部。

该优化首先服务于同一任务内的多轮 Decision 调用，也可在 PromptType、可见能力和 Memory 相同的任务之间获得部分前缀复用。

### 2.4 缓存指标以 Provider 返回值为准

系统不得根据 Prompt 文本、摘要或本地指纹推测缓存命中量。

以下数据只能来自 Provider 响应中的 usage：

- `prompt_tokens`
- `completion_tokens`
- `cached_tokens`

本轮不新增 Prompt digest 作为缓存命中依据。

## 3. 范围

### 3.1 本轮包含

- 稳定化 `FIRST_DECISION` 和 `EXECUTION_DECISION` 的 Prompt Block 顺序。
- 将 `Instruction` 与 `OutputContract` 拆成不同模板字段和不同 Prompt Block。
- 在 WorkSpace 内固定 `visible_tools` 和 `visible_skills` 的优先顺序。
- 对高决策成本 Tool 的模型可见 description 进行完整改写。
- 删除 Decision Prompt 中与具体 Tool 绑定的路由规则和重复说明。
- 为每次 Provider 调用保存 usage 明细，并在任务级聚合。
- 在 Web UI 中使用聚合后的真实 Provider usage 展示缓存利用率。

### 3.2 本轮不包含

- 不修改 Tool 的 schema、执行逻辑、权限或副作用语义。
- 不增加 Runtime Tool 选择器。
- 不增加 Tool description 解析器。
- 不根据 description 标题实施程序分支。
- 不调整 Verification 的业务判断规则。
- 不调整 Task 状态机、执行图、Worker 或恢复机制。
- 不新增 Prompt 压缩、Token Budget 或语义缓存。
- 不把缓存指标写入 Memory 或模型 Prompt。

## 4. 最终 Prompt 结构

### 4.1 Decision Prompt 顺序

`FIRST_DECISION` 和 `EXECUTION_DECISION` 必须按以下顺序渲染：

```text
1. SystemPrompt
2. GlobalCapabilityPolicy
3. PromptTypeInstruction
4. OutputContract
5. Memory
6. UserPrompt
7. WorkSpace
   7.1 visible_tools
   7.2 visible_skills
   7.3 其他 WorkSpace 字段
8. FinalOutputReminder
```

`FinalOutputReminder` 只保留简短、稳定的格式提醒，例如：

```text
Return only the output required by OutputContract.
```

不得在末尾重复完整 Instruction 或完整 OutputContract。

### 4.2 WorkSpace 归属与顺序

`visible_tools` 和 `visible_skills` 继续属于 WorkSpace，不提取成独立顶层 Prompt Block。

Prompt Engine 在格式化 WorkSpace 时必须使用以下顶层顺序：

```text
visible_tools
visible_skills
其余字段按字段名稳定排序
```

要求：

- `visible_tools` 内部按 Tool name 稳定排序。
- `visible_skills` 内部按 Skill name 稳定排序。
- 其余嵌套 Mapping 使用确定性字段排序。
- 不要求 SubAgent 或其他调用方改变现有结构化 context 的传递方式。
- Prompt Engine 不得修改调用方传入的原始 Mapping。
- Tool 和 Skill 不得在 WorkSpace 内重复渲染。

这项排序是 Prompt 表示层规则，不是 Tool 或 Skill 的执行优先级。

### 4.3 Memory 与 UserPrompt

Memory 放在 UserPrompt 之前。UserPrompt 放在 WorkSpace 之前。

原因：

- 同一 Task 中，用户原始请求通常保持不变。
- WorkSpace 中的 observations、当前 Step、失败和执行结果会频繁变化。
- 把 WorkSpace 放在最后可以尽量延长多轮 Decision Prompt 的稳定前缀。

UserPrompt 必须表达当前任务对应的原始用户输入，不得用 task goal、completion summary 或 Runtime 状态替代。

### 4.4 确定性序列化

模型 Prompt 内的结构化数据采用紧凑、确定性 JSON 表示：

- Mapping key 使用确定性顺序。
- 不输出仅用于美化的缩进和空白。
- 相同结构化输入必须生成完全相同的字符串。
- 页面如需可读格式，可以在展示层格式化，但实际发送给 Provider 的 Prompt 不得因此变化。

## 5. PromptTemplate 数据契约

`PromptTemplate` 应从当前的：

```text
system_prompt
instruction
```

调整为至少：

```text
system_prompt
instruction
output_contract
```

职责边界：

- `system_prompt`：Ella 的稳定身份、安全和真实性边界。
- `instruction`：当前 PromptType 要解决的问题和允许采取的行为。
- `output_contract`：模型必须返回的结构、字段、枚举和必填要求。

`PromptFrame.output_contract` 必须来自 `PromptTemplate.output_contract`，不得继续复制完整 `instruction`。

## 6. GlobalCapabilityPolicy

`GlobalCapabilityPolicy` 只包含跨 Tool 和 Skill 通用的能力原则：

- Tool 是可选能力，不是每个任务的必经步骤。
- 模型只能调用当前 WorkSpace 中可见的 Tool。
- 任务可直接回答时，可以不调用 Tool。
- 模型不得声称执行了实际未执行的 Tool。
- Tool 结果是 observation，不自动等于任务完成。
- Tool 失败不是成功事实，不得作为已完成结果使用。
- Skill 是行为指导，不是独立执行引擎或固定 Tool 序列。
- 没有合适 Skill 时可以继续执行任务。

`GlobalCapabilityPolicy` 不得包含：

- 具体 Tool name。
- 特定关键词到 Tool 的路由。
- Tool 调用顺序。
- 某个场景必须使用某个 Tool 的硬编码规则。
- `selection_policy` 或 `selection_order`。

## 7. Tool Description 改造

### 7.1 改造范围

本轮只改写高决策成本 Tool：

```text
plan_written
ask_user_question
web_search
web_page_read
document_write
camera_scene
screen_scene
artifact_exists
document_read
tool_observation_check
```

Mock Tool 不因本 PRD 增加额外 description Token，除非其当前描述与实际行为明显冲突。

### 7.2 Description 表达约定

Tool 仍只暴露一个 `description: str`。可以按需使用以下标题：

```text
Purpose:
Use when:
Do not use when:
Execution behavior:
Failure and limitations:
```

这些标题是编写约定，不是运行时协议：

- Runtime 不解析标题。
- Runtime 不检查标题是否齐全。
- Runtime 不根据标题实施 Tool 选择或失败处理。
- Description 可以省略不需要的段落。

### 7.3 严格替换规则

新 description 必须完整覆盖旧 description。

禁止：

- 自动合并新旧 description。
- 因旧 description 存在某项限制而自动继承该限制文本。
- 新 description 缺少输入限制、失败语义或其他段落时，从旧 description 补齐。

如果新 description 没有说明某项内容，该内容对模型不可见。Tool 的实际输入约束、权限和执行事实仍由 ToolDefinition schema 与 Tool 实现负责。

新 description 不得虚构当前 Tool 不具备的能力。描述与实现不一致应由代码评审和测试发现，而不是通过 Prompt 内的继承规则修正。

### 7.4 Decision Prompt 去耦

以下具体规则不得继续硬编码在通用 Decision Prompt 中：

- 屏幕关键词固定路由到 `screen_scene`。
- 物理环境关键词固定路由到 `camera_scene`。
- `camera_scene` 是否允许重复调用的具体规则。
- `ask_user_question` 的具体适用条件。
- 某个具体 Tool 的重试、限制或优先级。

这些模型可见信息应由对应 Tool 的新 description 完整表达。

Tool 的实际重试预算、schema 校验、权限校验和执行失败归一化仍由 Runtime 与 Executor 负责，不依赖 description。

## 8. PromptType 改造范围

### 8.1 第一阶段

第一阶段只改造：

- `FIRST_DECISION`
- `EXECUTION_DECISION`

这两个 PromptType 使用本文定义的完整稳定结构。

### 8.2 Verification

`VERIFICATION_DECISION` 本轮不修改业务提示词和验证规则。

它可以适配新的 `PromptTemplate.output_contract` 数据契约，但不得借此改变：

- goal state 判断。
- verification Tool 调用逻辑。
- recoverable 判断。
- draft 验证语义。

### 8.3 Final Response

如果当前实际执行链路不再调用独立 Final Response Prompt，本轮不得为追求形式统一而重新引入该调用。

## 9. Provider Usage 观测

### 9.1 数据来源

缓存与 Token 数据只使用 Provider 响应中实际返回的 usage。

每次调用至少记录：

```text
boundary
provider_name
model_name
modality
prompt_tokens
completion_tokens
cached_tokens
success
```

`modality` 至少区分：

```text
text
multimodal
speech
```

Provider 未返回某项数据时，应记录为不可用或 `None`，不得估算。

### 9.2 任务级调用明细

保留现有最近一次调用兼容字段：

```text
task_local_state["provider_usage"]
```

新增任务级调用明细：

```text
task_local_state["provider_usage_calls"]
```

`provider_usage_calls` 是当前 Task 内 Provider usage 聚合的事实来源。每次调用追加一条记录，不得覆盖此前记录。

### 9.3 聚合口径

任务级汇总至少包含：

```text
prompt_tokens_total
completion_tokens_total
cached_tokens_total
cache_hit_rate
```

计算方式：

```text
cache_hit_rate = cached_tokens_total / prompt_tokens_total
```

当 `prompt_tokens_total` 为 0 或 Provider 未提供有效数据时，缓存命中率显示为不可用，不得除零或伪造为 0%。

不同 modality 必须分组聚合。Web UI 的文本 Prompt 缓存率不得混入 multimodal 或 speech usage。

### 9.4 调用边界

所有实际经过统一 Provider 边界的调用都应记录，包括但不限于：

- first decision
- execution decision
- verification
- failure closure
- 当前代码实际存在的其他文本 LLM boundary
- multimodal 和 speech Provider 调用

不存在的调用边界不得仅为了统计而新增。

### 9.5 Web UI

Web UI 优先使用 `provider_usage_calls` 聚合结果；旧任务或没有明细的任务可以回退到 `provider_usage`。

页面至少展示：

- 文本 Prompt Token 总量。
- 文本 Completion Token 总量。
- 文本 Cached Token 总量。
- 文本缓存命中率。
- 按 boundary 的 Provider usage 明细。

该页面只展示真实 Provider usage，不展示推测缓存率或本地 Prompt digest。

## 10. 安全与隐私

- Provider usage 不得包含完整 Prompt、API key、Authorization Header 或 Provider credential。
- Tool description 不得包含 API key、本地敏感路径或内部认证信息。
- Prompt 页面继续展示实际发送字符串时，必须沿用现有脱敏规则。
- Usage 统计不得进入 Memory 或下一轮模型 Prompt。

## 11. 测试要求

### 11.1 Prompt 结构

- `FIRST_DECISION` 按本文顺序生成 Prompt。
- `EXECUTION_DECISION` 按本文顺序生成 Prompt。
- `Instruction` 与 `OutputContract` 不再重复。
- Prompt 末尾只有简短 `FinalOutputReminder`。
- Memory 位于 UserPrompt 前。
- UserPrompt 位于 WorkSpace 前。

### 11.2 WorkSpace 稳定性

- `visible_tools` 是 WorkSpace 第一个字段。
- `visible_skills` 是 WorkSpace 第二个字段。
- 其他字段顺序确定。
- Tool 和 Skill 列表顺序确定。
- 不同 Mapping 插入顺序产生相同 Prompt。
- Prompt Engine 不修改调用方 context。
- Tool 和 Skill 不重复渲染。
- WorkSpace observation 变化不改变 WorkSpace 之前的 Prompt 内容。

### 11.3 Tool Description

- 目标 Tool 使用新的完整 description。
- 新 description 完全替换旧文本，不发生自动合并。
- 通用 Decision Prompt 不再包含具体 Tool 路由规则。
- Runtime 不解析 description 标题。
- Tool schema、权限和执行行为保持不变。
- Tool description 不包含凭据和敏感路径。

### 11.4 Provider Usage

- 同一 Task 的多次 Provider usage 不再互相覆盖。
- 每条记录包含 boundary、provider、model、modality 和 Provider 返回的 Token 数据。
- 任务级 Token 聚合正确。
- 缓存命中率只由 Provider 返回的 `cached_tokens` 和 `prompt_tokens` 计算。
- 文本、多模态和语音 usage 不混算。
- Provider 缺少 usage 时不估算。
- 旧 `provider_usage` 回退路径仍可用。

### 11.5 回归

必须运行：

```bash
python -m pytest
python main.py
```

不得因 Prompt 结构调整改变 Tool 权限、Task 状态机或执行循环。

## 12. 实施拆分

### Commit 1

```text
refactor(prompts): stabilize decision prompt structure
```

只负责：

- PromptTemplate 拆分 OutputContract。
- Decision Prompt Block 排序。
- WorkSpace 内 Tool/Skill 优先排序。
- 紧凑确定性 JSON。
- 删除 Decision Prompt 中具体 Tool 路由。

### Commit 2

```text
refactor(tools): clarify model-facing tool descriptions
```

只负责：

- 改写选定高决策成本 Tool 的 description。
- 验证 description 与现有 Tool 能力一致。
- 不修改 Tool schema 和执行行为。

### Commit 3

```text
feat(observability): aggregate provider usage by boundary
```

只负责：

- 保存每次 Provider usage。
- 按 Task 和 modality 聚合。
- Web UI 展示真实缓存指标和 boundary 明细。
- 保留旧 usage 字段回退。

## 13. 验收标准

- [ ] Decision Prompt 的稳定内容位于动态 WorkSpace 之前。
- [ ] WorkSpace 中 `visible_tools`、`visible_skills` 固定为前两个字段。
- [ ] Prompt 中结构化数据采用紧凑确定性 JSON。
- [ ] Instruction 与 OutputContract 职责分离且不重复。
- [ ] 通用 Decision Prompt 不含具体 Tool 路由策略。
- [ ] 高决策成本 Tool 的新 description 完全覆盖旧 description。
- [ ] Runtime 不解析 Tool description，也不新增 Tool 选择策略。
- [ ] Provider usage 调用明细不会被后续调用覆盖。
- [ ] Web UI 缓存指标来自 Provider 返回值。
- [ ] 不同 modality 的 usage 不混算。
- [ ] 现有 Task、Tool、Verification 和恢复流程行为保持可运行。
- [ ] 全量测试和 `python main.py` 通过。


# Ella Agent Runtime

Ella 是一个面向长期运行、本地交互和可恢复任务执行的 Agent Runtime。它将用户输入转换为异步任务，由 Runtime 负责排队、推理、工具调用、验证、持久化和结果交付；Web UI 只负责提交任务、展示状态以及发送暂停、恢复和取消命令。

当前仓库重点验证的不是单一聊天功能，而是一套可观察、可控制、可恢复的 Agent 执行骨架。

## 当前能力

- 文本和有界麦克风输入，经事件管线进入任务队列。
- 统一的 First Decision：识别意图，并直接选择 `CALL_TOOL` 或 `SUBMIT_RESULT`。
- 自描述 Tool、任务级能力范围、Schema 校验和结构化失败处理。
- 摄像头、屏幕理解、网页检索、网页读取、文档读写和用户追问等工具。
- `workflow` 在 QuickJS 隔离环境中用 `await` 与 `Promise.all` 编排子 Agent。
- 独立的任务执行状态与目标达成状态，以及提交结果后的 Verification。
- 后台 TaskRuntime worker，支持任务排队、暂停、恢复、取消和安全点 checkpoint。
- 本地 JSONL trace、阶段耗时、任务 checkpoint、Memory 和生成文档持久化。
- 本地 Web UI，展示任务队列、终态任务、视觉结果、工具过程、Prompt 和耗时。
- Qwen 与 DeepSeek 文本模型；Qwen 多模态与语音能力；默认能力可切换为 Mock。

## 执行链路

```text
User input
  -> RawSignal
  -> EventTriggerPipeline
  -> StandardizedEvent
  -> EventRuntime
  -> Task creation and queue
  -> TaskRuntime worker
  -> First Decision / Reasoning
       -> CALL_TOOL -> CapabilityExecutor -> ToolResult -> next Reasoning
       -> SUBMIT_RESULT -> Verification
  -> Task terminal state
  -> Web UI delivery
```

职责边界：

- `EventRuntime`：标准化输入、路由事件并创建任务。
- `TaskRuntime`：任务队列、worker、状态机、执行循环、checkpoint 和交付。
- `SubAgent`：每轮生成一个结构化动作，不直接执行工具。
- `PromptEngine`：只接收结构化上下文并生成实际传给 LLM 的字符串。
- `ToolManager`：注册和发现工具；`CapabilityExecutor` 负责校验并执行单次调用。
- `VerificationAgent`：在提交结果后判断目标达成情况和回答是否可交付。
- `MemoryManager`：统一持久化和读取当前简化版记忆。

## 环境要求

- Python 3.11 或更高版本
- macOS 或 Windows（真实摄像头和麦克风通过跨平台设备层接入）
- 使用真实 Qwen 或 DeepSeek 时需要相应 API Key

## 创建虚拟环境

macOS / Linux：

```bash
cd /path/to/Ella
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "openai>=1.0,<2" "opencv-python>=4.12,<5" "sounddevice>=0.5,<1" pytest
```

Windows PowerShell：

```powershell
cd C:\path\to\Ella
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "openai>=1.0,<2" "opencv-python>=4.12,<5" "sounddevice>=0.5,<1" pytest
```

本仓库当前采用 flat-layout 多包结构，不需要先将 Ella 打包或执行 `pip install -e .`。直接在仓库根目录运行即可。

## 配置

普通用户配置集中在 [`config/config.py`](config/config.py)，`config/settings.py` 负责解析和校验。默认路径都从项目根目录推导，不依赖某一台电脑的绝对路径。

### Mock 模式

不访问真实模型和设备，适合开发与测试：

```python
MODEL_PROVIDER = "mock"
USE_REAL_PROVIDERS = False
MIC_ENABLED = False
CAMERA_ENABLED = False
DEBUG_STORE_RAW_MEDIA = False
```

### Qwen 模式

```python
MODEL_PROVIDER = "qwen"
USE_REAL_PROVIDERS = True

QWEN_LLM_MODEL = "qwen-plus"
QWEN_MULTIMODAL_MODEL = "qwen-vl-plus"
QWEN_SPEECH_MODEL = "qwen3-asr-flash"

CAMERA_ENABLED = True
MIC_ENABLED = True
```

API Key 可以写入本地 `config/config.py`，也可以使用以下任一环境变量：

```bash
export ELLA_QWEN_API_KEY="your-key"
# 或 DASHSCOPE_API_KEY / QWEN_API_KEY
```

### DeepSeek 文本模型

DeepSeek 只替换文本推理模型；摄像头多模态理解和语音转写仍使用 Qwen：

```python
MODEL_PROVIDER = "deepseek"
USE_REAL_PROVIDERS = True
DEEPSEEK_LLM_MODEL = "deepseek-v4-pro"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_BYPASS_PROXY = True
DEEPSEEK_THINKING_ENABLED = True
DEEPSEEK_REASONING_EFFORT = "low"
```

```bash
export DEEPSEEK_API_KEY="your-key"
```

### 设备配置

```python
MIC_ENABLED = True
MIC_DEVICE = "default"
MIC_CAPTURE_DURATION_SECONDS = 5
MIC_SAMPLE_RATE = 16000
MIC_CHANNELS = 1

CAMERA_ENABLED = True
CAMERA_DEVICE = "default"
CAMERA_TASK_FPS = 1
```

首次使用真实设备时，macOS 或 Windows 可能请求摄像头和麦克风权限。模块导入和 Runtime 创建不会主动打开设备，设备只在对应输入或 Tool 被调用时访问。

## 启动 Ella

激活虚拟环境后，在项目根目录运行：

```bash
python main.py
```

Ella 会从 `127.0.0.1:8001` 开始寻找可用端口，启动本地 Web 服务并自动打开浏览器。终端会输出实际地址，例如：

```text
Ella Runtime is available at http://127.0.0.1:8001
```

使用 `Ctrl+C` 停止服务。Runtime 会在退出前关闭后台 worker。

## Web UI

Web UI 当前支持：

- 提交文本任务和有界麦克风输入。
- 查看活动任务与已终止任务。
- 查看任务状态、执行过程、视觉摘要、Prompt、最终回答和耗时。
- 对活动任务发送暂停、恢复和取消命令。
- 通过服务端事件流接收任务状态和完成结果。

任务提交后默认进入队列并由 TaskRuntime worker 执行，前端不会调用 `run_until_complete()` 驱动任务。

## 本地数据

默认数据位置由 `config/config.py` 统一管理：

| 数据 | 默认路径 |
| --- | --- |
| Memory | `memory/memory.md` |
| Trace | `trace/` |
| Task checkpoint | `output/tasks/` |
| Plan | `output/plans/` |
| 页面显示文件 | `output/display/` |
| 文档工具输出 | `output/documents/` |
| 调试原始媒体 | `output/raw_media/` |

`DEBUG_STORE_RAW_MEDIA` 默认应保持关闭；只有本地调试确有需要时再启用。API Key 不会写入 Memory、Trace 或 Prompt 展示数据。

## 测试

运行全部测试：

```bash
python -m pytest
```

运行启动检查：

```bash
python main.py
```

测试默认应使用 Mock 或注入的 fake backend，不访问真实网络、摄像头和麦克风。

## 主要目录

```text
agent/       决策、SubAgent 与 Verification
config/      用户配置和设置校验
devices/     摄像头、麦克风和屏幕设备边界
events/      RawSignal、标准事件和输入源
memory/      简化版记忆管理
prompts/     Prompt Engine 与模板
providers/   Mock、Qwen、DeepSeek、语音和多模态 Provider
runtime/     EventRuntime、TaskRuntime、执行、trace 和 checkpoint
skill/       Skill 定义、加载与注册
tasks/       Task、状态和单步推理执行数据契约
tools/       ToolDefinition、ToolManager 与具体工具
demo/        本地 Web UI 和展示适配
tests/       单元、集成与契约测试
```

## 设计文档

- [`docs/runtime_tools_workflow_prd.md`](docs/runtime_tools_workflow_prd.md)：当前工具、Workflow、Subagent、checkpoint 与唯一任务标识契约，是现役架构入口。
- [`docs/design_overview.md`](docs/design_overview.md)：旧架构综合说明，仅保留为历史记录。
- [`docs/prompt_prd.md`](docs/prompt_prd.md)：Prompt Engine 设计（最新演进见 `prompt_structure_improve_prd.md`）。
- [`docs/task_runtime_worker_prd.md`](docs/task_runtime_worker_prd.md)：旧后台任务执行模型（历史）。
- [`docs/task_step_tool_graph_prd.md`](docs/task_step_tool_graph_prd.md)：旧图执行结构（历史）。
- [`docs/tool_failure_prd.md`](docs/tool_failure_prd.md)：Tool 失败分类与重试语义。
- [`docs/dual_state_task_verification_prd.md`](docs/dual_state_task_verification_prd.md)：双状态与 Verification。

> 注：包含旧架构术语的早期文档均已标记为 superseded，仅作历史记录。

## 当前限制

- Runtime 当前是本地单进程实现，不是分布式调度系统。
- Memory 仍是最小版本，尚未实现向量检索、压缩和遗忘策略。
- 工具生态尚未接入 MCP。
- 真实设备质量、权限和可用性受操作系统及硬件环境影响。
- checkpoint 面向当前数据模型，不承诺兼容早期开发版本生成的旧快照。

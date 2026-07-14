# Ella

Ella 是一个本地运行的 Agent Runtime。它把用户输入、Prompt Engine、Skill / Tool、LLM、多模态感知、记忆和 Web 展示串成一条可观察的执行链路，用来探索一个可解释、可扩展的个人智能体。

当前版本默认启动本地 Web 页面，支持文本输入、麦克风输入、屏幕理解、摄像头理解、工具调用、最终回答生成、Memory 写入和运行过程展示。

## 环境要求

- Python 3.11 或更高版本
- macOS / Windows / Linux 均可运行基础功能
- 真实摄像头依赖 OpenCV
- 真实麦克风依赖 sounddevice
- 真实 LLM / ASR / 多模态能力当前通过 Qwen / DashScope 配置

## 创建虚拟环境

在项目根目录执行：

```bash
python -m venv .venv
```

激活虚拟环境：

```bash
source .venv/bin/activate
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

升级基础安装工具：

```bash
python -m pip install --upgrade pip
```

## 安装依赖

本项目暂时不需要打包安装，直接安装运行依赖即可：

```bash
pip install -r requirement.txt
```

当前主要依赖：

- `opencv-python`：摄像头截图
- `sounddevice`：麦克风录音
- `pytest`：测试

## 配置 Ella

用户可编辑配置在：

```text
config/config.py
```

配置解析和校验在：

```text
config/settings.py
```

普通配置优先读取 `config/config.py`。API key 可以写在 `config/config.py`，但更推荐通过环境变量提供。

### Mock 模式

如果你只想安全启动，不访问真实网络、摄像头或麦克风，可以在 `config/config.py` 中设置：

```python
USE_REAL_PROVIDERS = False
MIC_ENABLED = False
CAMERA_ENABLED = False
DEBUG_STORE_RAW_MEDIA = False
```

Mock 模式会使用本地 mock provider 和 mock device，适合开发、测试和无设备环境。

### 真实 LLM / 摄像头 / 麦克风

如果你要使用真实 Qwen、真实摄像头和真实麦克风，可以设置：

```python
MODEL_PROVIDER = "qwen"

QWEN_LLM_MODEL = "qwen-plus"
QWEN_MULTIMODAL_MODEL = "qwen-vl-plus"
QWEN_SPEECH_MODEL = "qwen3-asr-flash"

USE_REAL_PROVIDERS = True
MIC_ENABLED = True
CAMERA_ENABLED = True

MIC_DEVICE = "default"
CAMERA_DEVICE = "default"
MIC_CAPTURE_DURATION_SECONDS = 5
MIC_SAMPLE_RATE = 16_000
MIC_CHANNELS = 1
```

推荐用环境变量配置 API key：

```bash
export DASHSCOPE_API_KEY="你的 DashScope API Key"
```

也支持：

```bash
export ELLA_QWEN_API_KEY="你的 DashScope API Key"
export QWEN_API_KEY="你的 DashScope API Key"
```

`settings.py` 会按以下环境变量名查找 Qwen API key：

```text
ELLA_QWEN_API_KEY
DASHSCOPE_API_KEY
QWEN_API_KEY
```

## 启动 Ella

在虚拟环境已激活、依赖已安装后运行：

```bash
python main.py
```

启动后终端会输出类似：

```text
Ella Runtime is available at http://127.0.0.1:8000
```

程序会自动打开本地浏览器。如果默认端口被占用，Ella 会尝试后续端口。

停止服务：

```text
Ctrl-C
```

## Web 页面功能

本地 Web 页面会展示：

- 用户输入
- 麦克风转写结果
- 摄像头 / 屏幕捕获状态
- 画面总结和可见物体
- Task goal
- Tool results
- Timing 性能摘要
- 实际发送给 LLM 的 Prompt
- Agent 最终回答
- Memory 写入状态

页面只是本地展示和输入入口，不直接调用 Tool、Provider、Memory 或 Runtime 内部对象。

## Memory

默认运行时 Memory 写入：

```text
/Users/wx/ella-runtime-memory.md
```

仓库内的 `memory/memory.md` 主要是项目内默认占位文件，不建议把本地运行产生的个人数据提交到仓库。

## 常用测试

运行全部测试：

```bash
python -m pytest
```

运行 Runtime 计时相关测试：

```bash
python -m pytest tests/runtime/test_runtime_timing.py
```

运行主入口 smoke test：

```bash
python main.py
```

## 项目结构

```text
agent/       MainAgent、TaskFormulator、FinalResponseGenerator
runtime/     EventRuntime、TaskRuntime、PresenceRuntime、timing
sessions/    TaskSession、SubAgent、CapabilityExecutor、执行状态
prompts/     Prompt Engine 和 Prompt 模板
tools/       ToolDefinition、ToolManager、摄像头/屏幕/mock tools
devices/     摄像头、麦克风、屏幕设备 provider
providers/   Mock / Qwen LLM、Speech、Vision、Multimodal provider
memory/      MemoryManager
demo/        Web UI、Display Snapshot、页面渲染
config/      用户配置和 settings 解析
tests/       单元测试、契约测试和 demo 测试
```

## 参考文档

- [MVP PRD](docs/prd.md)
- [Architecture](docs/architecture.md)
- [PRD 2.1](docs/prd_2_1.md)
- [Prompt PRD](docs/prompt_prd.md)
- [Tool Runtime PRD](docs/pr_tool.md)
- [Tool Failure PRD](docs/tool_failure_prd.md)

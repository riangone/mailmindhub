# MailMindHub Project Context

MailMindHub 是一个 AI 驱动的邮件守护进程，它将用户的电子邮箱转变为 AI 交互界面。它监听传入邮件，通过各种 AI 后端（CLI 或 API）处理指令，并自动回复处理结果。

## 🏗️ 架构与核心组件

- **`email_daemon.py`**: 系统的核心引擎。负责 IMAP 连接（支持 IDLE 实时推送或轮询）、邮件解析、调用 AI 以及 SMTP 回复。它还集成了一个任务调度器。
- **`manage.sh`**: 用户的主要入口。提供交互式安装、服务生命周期管理（启动/停止/重启）、日志查看、Web UI 启动以及 systemd 集成。
- **`core/`**: 核心逻辑层。
    - `config.py`: 统一配置管理，处理环境变量和邮箱服务器设置。
    - `mail_client.py`: 封装 IMAP 操作，支持 OAuth 和密码认证。
    - `mail_sender.py`: 封装 SMTP 操作及结果归档逻辑。
    - `validator.py`: 提供白名单验证和配置合法性检查。
- **`ai/`**: AI 后端抽象层。
    - `providers/`: 包含多个 AI 驱动，支持 CLI 工具（如 Claude Code, Gemini CLI）和 REST API（如 OpenAI, Anthropic, DeepSeek, 阿里云通义千问等）。
- **`tasks/`**: 任务管理系统。
    - `scheduler.py`: 基于 SQLite 的持久化调度器，支持一次性定时、时间间隔和 Cron 表达式。
    - `registry.py`: 定义不同任务类型（如 `weather`, `news`, `web_search`, `report`, `system_status`）的执行逻辑。
- **`skills/`**: 插件化能力。支持 `code_review`, `stock`, `summarize` 等扩展功能。
- **`utils/`**: 通用工具集。包括邮件内容解析器、日志记录器及网页搜索（DuckDuckGo/Bing）封装。
- **`webui/`**: 基于 FastAPI 的 Web 管理界面，用于实时监控、任务管理和日志查看。

## 🛠️ 技术栈

- **语言**: Python 3.8+
- **数据存储**: SQLite (`tasks.db`)
- **协议**: IMAP (接收), SMTP (发送)
- **主要库**:
    - `imapclient`: 用于 IMAP IDLE 实时推送。
    - `requests`: 用于 AI API 和 Web 交互。
    - `markdown`: 将 AI 生成的内容渲染为 HTML 邮件。
    - `croniter`: 解析复杂的定时任务。
    - `fastapi`: 驱动 Web UI。

## 🚀 开发与运行规范

### 1. 环境配置
项目主要通过环境变量进行配置，通常定义在 `.env` 文件中。关键变量包括：
- `MAIL_<NAME>_ADDRESS/PASSWORD/ALLOWED`: 各邮箱的认证和白名单。
- `AI`: 全局默认 AI 后端。
- 各 AI 服务的 `API_KEY`。

### 2. 启动与管理
- 启动服务: `bash manage.sh start`
- 启动 Web UI: `bash manage.sh webui start`
- 实时日志: `bash manage.sh log`

### 3. 任务与持久化
- 任务持久化在 `tasks.db` 中。
- 定时任务生成的报告默认存档在 `reports/` 目录下。

### 4. 编码实践
- **PEP 8**: 遵循标准的 Python 代码风格。
- **日志**: 使用 `utils/logger.py` 进行统一记录，日志文件为 `daemon.log` 和 `webui.log`。
- **安全性**: 始终通过 `core/validator.py` 检查发送者是否在 `ALLOWED` 白名单内。

## 📅 定时指令示例
用户可以通过邮件发送自然语言指令来创建任务：
- `每天 08:00 天气 Beijing`
- `每2小时 新闻 AI 相关，归档`
- `每周一 10:00 AI 分析：整理进度，归档`

---
*此 GEMINI.md 由 AI 自动生成，用于记录项目核心架构与开发准则。*

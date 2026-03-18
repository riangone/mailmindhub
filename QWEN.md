# MailMindHub — QWEN.md

## 项目概述

**MailMindHub** 是一个邮件到 AI 的桥接守护进程。用户发送包含指令的邮件，守护进程通过 IMAP 接收邮件，将指令传递给 AI 后端处理，然后通过 SMTP 将结果回复到用户邮箱。

**核心理念**：邮件即是界面，无需打开任何 App。

```
你发邮件（指令）→ MailMindHub 接收 → AI 处理 → 邮件回复结果
```

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| 核心依赖 | `requests`, `imapclient`, `markdown`, `ddgs`, `googlesearch-python`, `croniter` |
| 可选依赖 | `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2` (Gmail OAuth), `msal` (Outlook OAuth) |
| Web UI | `fastapi`, `uvicorn`, `jinja2`, `python-multipart` |
| 部署方式 | 后台进程 / systemd 服务 / Docker |
| 定时任务 | SQLite 持久化，支持单次/周期/cron 任务 |

## 项目结构

```
MailMind/
├── email_daemon.py          # 主入口 (~580 行，模块化重构版)
├── manage.sh                # 统一管理脚本（启动/停止/重启/日志/systemd 安装）
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量模板
├── .env                     # 实际配置（需手动创建，包含敏感信息）
├── docker-compose.yml       # Docker Compose 配置
├── Dockerfile               # Docker 镜像构建
├── email-daemon.service     # systemd 服务模板（由 manage.sh 生成）
├── README.md                # 用户文档（多语言：中文/日本語/English/한국어）
├── CLAUDE.md                # Claude Code 上下文
├── QWEN.md                  # 本文件
├── tasks.db                 # SQLite 定时任务数据库
├── tasks.json               # 定时任务 JSON（旧版，兼容用）
├── reports/                 # 定时报告归档目录
├── workspace/               # Workspace 目录（可选，限制 AI 操作范围）
├── core/                    # 核心模块
│   ├── __init__.py
│   ├── config.py            # 邮箱/AI 配置，环境变量读取（含 WORKSPACE_DIR）
│   ├── mail_client.py       # IMAP 客户端，邮件获取，模板推送
│   ├── mail_sender.py       # SMTP 发送，归档（workspace 路径校验）
│   ├── email_manager.py     # 邮件管理器
│   ├── validator.py         # 配置验证（含 validate_path 路径校验函数）
│   └── one_click_unsubscribe.py  # RFC 8058 一键退订支持
├── ai/                      # AI 模块
│   ├── __init__.py
│   ├── base.py              # AIBase 抽象类
│   └── providers/           # AI 提供商实现
│       └── __init__.py      # CLI/API 提供商（OpenAI/Anthropic/Gemini/Qwen/Cohere/Spark/Ernie）
├── tasks/                   # 定时任务模块
│   ├── __init__.py
│   ├── scheduler.py         # TaskScheduler（SQLite 持久化，支持 cron）
│   └── registry.py          # 任务执行逻辑（天气/新闻/搜索/系统状态）
├── utils/                   # 工具模块
│   ├── __init__.py
│   ├── logger.py            # 日志封装
│   ├── parser.py            # AI 响应解析，定时任务自动识别
│   ├── search.py            # 网页搜索（DuckDuckGo/Google/Wikipedia/Bing）
│   └── mcp_client.py        # MCP (Model Context Protocol) 客户端
├── webui/                   # Web UI（可选）
│   ├── __init__.py
│   ├── server.py            # FastAPI 服务器
│   ├── static/              # 静态资源
│   └── templates/           # Jinja2 模板
├── tests/                   # 测试
│   └── test_email_logic.py  # 单元测试
├── venv/                    # Python 虚拟环境（.gitignore）
├── daemon.log               # 运行日志（.gitignore）
├── daemon.pid               # 进程 ID 文件（.gitignore）
├── credentials_gmail.json   # Gmail OAuth 凭据（.gitignore）
├── token_gmail.json         # Gmail OAuth token（.gitignore）
└── token_outlook.json       # Outlook OAuth token（.gitignore）
```

## 构建与运行

### 环境准备

```bash
# 克隆项目
git clone https://github.com/yourname/MailMindHub.git
cd MailMindHub

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装基础依赖
pip install -r requirements.txt

# 可选：Gmail OAuth 支持
pip install google-auth google-auth-oauthlib google-auth-httplib2

# 可选：Outlook OAuth 支持
pip install msal

# 可选：Web UI
pip install fastapi uvicorn jinja2 python-multipart itsdangerous
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填写真实邮箱凭证和 AI 配置
```

### 启动守护进程

```bash
# 推荐：使用 manage.sh
bash manage.sh start      # 后台启动
bash manage.sh stop       # 停止
bash manage.sh restart    # 重启
bash manage.sh status     # 查看状态和最近日志
bash manage.sh log        # 实时查看日志
bash manage.sh install    # 安装为 systemd 服务（开机自启）
bash manage.sh uninstall  # 卸载 systemd 服务
bash manage.sh webui      # 启动 Web UI
bash manage.sh push-templates  # 推送指令模板到邮箱

# 直接运行
python3 email_daemon.py --mailbox 126 --ai claude          # IMAP IDLE 模式（默认）
python3 email_daemon.py --mailbox gmail --ai openai --poll # 轮询模式
python3 email_daemon.py --list                             # 显示配置状态
python3 email_daemon.py --mailbox gmail --auth             # 首次 OAuth 授权
```

### Docker 部署

```bash
# 构建并运行
docker compose up -d

# 查看日志
docker compose logs -f daemon
```

### 启动模式

| 模式 | 说明 | 配置 |
|------|------|------|
| `idle` | IMAP IDLE，服务器推送新邮件通知（默认） | `MODE=idle` |
| `poll` | 定时轮询 | `MODE=poll` + `POLL_INTERVAL=60` |

## 支持的邮箱

| 邮箱 | 认证方式 | 说明 |
|------|----------|------|
| 126 | 授权码 | 需开启 IMAP，短信获取授权码 |
| 163 | 授权码 | 同上 |
| QQ | 授权码 | 同上 |
| Gmail | OAuth（推荐）/ 应用密码 | OAuth 需下载 `credentials_gmail.json` |
| Outlook | OAuth | 需 Azure 应用注册获取 Client ID |
| iCloud | 应用密码 | 需生成 App-specific password |
| Proton | Bridge 密码 | 需运行 Proton Bridge |
| Custom | 密码 | 自定义 IMAP/SMTP 服务器 |

### OAuth 首次授权

**Gmail OAuth:**
```bash
export MAIL_GMAIL_ADDRESS="your@gmail.com"
export MAIL_GMAIL_ALLOWED="your@gmail.com"
python3 email_daemon.py --mailbox gmail --auth
# 终端打印 URL → 浏览器打开授权 → 粘贴 code 回终端
```

**Outlook OAuth:**
```bash
export MAIL_OUTLOOK_ADDRESS="your@outlook.com"
export OUTLOOK_CLIENT_ID="your-client-id"
export MAIL_OUTLOOK_ALLOWED="your@outlook.com"
python3 email_daemon.py --mailbox outlook --auth
# 终端显示短码 → 浏览器打开 https://microsoft.com/devicelogin → 输入短码授权
```

## 支持的 AI 后端

### CLI 方式

| 名称 | 命令 | 所需环境 |
|------|------|----------|
| `claude` | `claude --print` | Claude Code 已安装 |
| `codex` | `codex exec --skip-git-repo-check` | Codex CLI 已安装 |
| `gemini` | `gemini -p` | Gemini CLI 已安装 |
| `qwen` | `qwen --prompt --web-search-default --yolo` | Qwen CLI 已安装 |
| `copilot` | `copilot` | GitHub Copilot CLI 已安装 |

### API 方式

#### 国际模型

| 名称 | 所需环境变量 | 默认模型 | API 端点 |
|------|-------------|----------|----------|
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` | Anthropic 官方 |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` | OpenAI 官方 |
| `gemini-api` | `GEMINI_API_KEY` | `gemini-2.0-flash` | Google 官方 |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` | DeepSeek 官方 |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | Groq 高速推理 |
| `perplexity` | `PERPLEXITY_API_KEY` | `sonar-pro` | Perplexity 搜索增强 |
| `cohere` | `COHERE_API_KEY` | `command-r-plus` | Cohere 企业级 |

#### 中国模型

| 名称 | 所需环境变量 | 默认模型 | 说明 |
|------|-------------|----------|------|
| `qwen-api` | `QWEN_API_KEY` | `qwen-max` | 通义千问（阿里云） |
| `moonshot` | `MOONSHOT_API_KEY` | `moonshot-v1-8k` | 月之暗面 Kimi |
| `glm` | `GLM_API_KEY` | `glm-4` | 智谱 AI（清华系） |
| `spark` | `SPARK_API_KEY` | `4.0Ultra` | 讯飞星火 |
| `ernie` | `ERNIE_API_KEY` | `ernie-4.0-8k` | 百度文心一言 |
| `yi` | `YI_API_KEY` | `yi-lightning` | 零一万物 |

#### 本地模型

| 名称 | 所需环境变量 | 说明 |
|------|-------------|------|
| `ollama` | `OLLAMA_BASE_URL` (可选) | Ollama 本地服务 |
| `vllm` | `VLLM_BASE_URL`, `VLLM_MODEL` | vLLM 本地服务 |

## 核心架构

### 模块依赖关系

```
email_daemon.py
├── core.config      → MAILBOXES, AI_BACKENDS, PROMPT_TEMPLATE
├── core.validator   → validate_config()
├── core.mail_client → fetch_unread_emails(), imap_login(), get_oauth_token(), push_templates_to_mailbox()
├── core.mail_sender → send_reply(), archive_output()
├── core.email_manager → 邮件管理器
├── core.one_click_unsubscribe → RFC 8058 一键退订
├── ai.providers     → get_ai_provider(), CLIProvider, OpenAIProvider, AnthropicProvider, ...
├── utils.parser     → parse_ai_response(), auto_detect_tasks(), trim_email_body(), detect_lang()
├── utils.logger     → log
├── utils.search     → web_search(), format_search_results()
├── utils.mcp_client → MCP 客户端（filesystem/github/sqlite）
├── tasks.scheduler  → TaskScheduler (SQLite, 支持 cron)
└── tasks.registry   → execute_task_logic()
```

### 数据流

```
fetch_unread_emails() → process_email() → call_ai() → send_reply()
                                         ↓
                              auto_detect_tasks() → scheduler.add_task()
```

### 关键数据结构

**`MAILBOXES`** (core/config.py)
- 邮箱预设字典，键名为 `126`, `163`, `qq`, `gmail`, `outlook`, `icloud`, `proton`, `custom`
- 包含 IMAP/SMTP 服务器、端口、认证类型、环境变量名、OAuth 文件路径

**`AI_BACKENDS`** (core/config.py)
- AI 后端预设字典
- `type`: `cli`, `api_anthropic`, `api_openai`, `api_gemini`, `api_qwen`, `cli_copilot`, `api_cohere`, `api_spark`, `api_ernie`, `api_ollama`, `api_vllm`

### 邮件处理流程

1. **接收邮件**: `fetch_unread_emails()` 通过 IMAP 获取未读邮件
2. **白名单检查**: 验证发件人是否在 `ALLOWED` 列表中
3. **提取内容**: `get_body_and_attachments()` 提取正文和附件
4. **语言检测**: `detect_lang()` 自动识别邮件语言（zh/ja/en/ko）
5. **调用 AI**: `call_ai()` 使用 `PROMPT_TEMPLATE` 调用 AI（支持多语言提示）
6. **解析响应**: 期望 AI 返回 JSON:
   ```json
   {
     "subject": "邮件标题",
     "body": "回复正文",
     "schedule_at": "可选：ISO 或相对秒",
     "schedule_every": "可选：5m/2h/1d",
     "schedule_until": "可选：截止时间",
     "schedule_cron": "可选：cron 表达式",
     "attachments": [{"filename": "report.md", "content": "文件内容"}],
     "task_type": "email|ai_job|weather|news|web_search|report|system_status|mcp_call",
     "task_payload": {"location": "...", "query": "...", "prompt": "...", "server": "...", "tool": "..."},
     "output": {"email": true, "archive": true, "archive_dir": "reports"}
   }
   ```
7. **发送回复**: `send_reply()` 通过 SMTP 发送回复（含附件）
8. **定时任务**: `scheduler.add_task()` 添加到 SQLite 持久化

### 定时任务调度

**`TaskScheduler`** 类（tasks/scheduler.py）负责管理定时任务：
- 使用 SQLite (`tasks.db`) 持久化任务
- 后台线程轮询检查到期任务
- 支持单次任务（`schedule_at`）和周期任务（`schedule_every`）
- 支持 cron 表达式（`schedule_cron`）
- 任务状态：`pending` → `processing` → `completed`/`failed`
- 支持任务暂停/恢复功能

### 自动识别与多任务

未显式提供 `task_type` 时，`utils/parser.py` 的 `auto_detect_tasks()` 会根据关键词自动识别：
- **关键词**：`天气`/`新闻`/`检索`/`搜索`/`日报`/`AI`/`系统状态`
- **时间解析**：`每 X 分钟/小时/天`、`每天 18:00`、`每周一 10:00`、`今天/明天/今晚/早上/下午`
- **多任务**：用分号或换行分隔，可拆分多个任务分别定时执行

### MCP (Model Context Protocol) 支持

通过 MCP 扩展 AI 能力，支持调用本地 MCP 服务器工具：
- **filesystem**: 文件系统操作（list_directory, read_file, write_file 等）
- **github**: GitHub API 操作
- **sqlite**: SQLite 数据库查询

配置示例（`.env`）：
```bash
MCP_SERVERS=filesystem,github
MCP_SERVER_FILESYSTEM=npx -y @modelcontextprotocol/server-filesystem /home/user/reports
MCP_SERVER_GITHUB=npx -y @modelcontextprotocol/server-github
```

### 附件支持

- **接收**: 
  - 文本附件（.txt, .md, .csv）解码后追加到 AI prompt
  - 二进制附件（PDF, 图片）仅记录文件名
- **发送**: AI 返回的 `attachments` 字段被 base64 编码后作为 MIME 附件发送

### 网络搜索/天气/新闻

支持多种外部数据源（tasks/registry.py, utils/search.py）：
- **DuckDuckGo**（默认，无需 API Key，使用 `ddgs`）
- **Google**（无需 API Key，使用 `googlesearch-python`）
- **Wikipedia**（无需 API Key）
- **Bing Search**（需 `BING_API_KEY`）
- **WeatherAPI**（需 `WEATHER_API_KEY`）
- **NewsAPI**（需 `NEWS_API_KEY`）

### 一键退订 (RFC 8058)

为定时/循环邮件自动添加 `List-Unsubscribe` 标头，支持 Gmail/Outlook/Apple Mail 的原生一键退订按钮。

配置（`.env`）：
```bash
UNSUBSCRIBE_BASE_URL="https://mailmind.example.com"
UNSUBSCRIBE_SECRET=""  # 留空则自动生成
```

## 开发约定

### 添加新邮箱

在 `core/config.py` 的 `MAILBOXES` 字典中添加条目：

```python
"newmail": {
    "address":         os.environ.get("MAIL_NEWMAIL_ADDRESS", ""),
    "password":        os.environ.get("MAIL_NEWMAIL_PASSWORD", ""),
    "imap_server":     "imap.newmail.com",
    "imap_port":       993,
    "smtp_server":     "smtp.newmail.com",
    "smtp_port":       465,
    "smtp_ssl":        True,
    "imap_id":         False,
    "auth":            "password",  # 或 "oauth_google" / "oauth_microsoft"
    "allowed_senders": [s.strip() for s in os.environ.get("MAIL_NEWMAIL_ALLOWED", "").split(",") if s.strip()],
    "spam_folder":     os.environ.get("MAIL_NEWMAIL_SPAM_FOLDER", "Junk"),
    "trash_folder":    os.environ.get("MAIL_NEWMAIL_TRASH_FOLDER", "Trash"),
},
```

### 添加新 AI 后端

在 `core/config.py` 的 `AI_BACKENDS` 字典中添加条目：

```python
"newai": {"type": "api_newai", "api_key": os.environ.get("NEWAI_API_KEY", ""), "model": "model-name"},
```

然后在 `ai/providers/__init__.py` 添加对应的 Provider 类：

```python
class NewAIProvider(AIBase):
    def __init__(self, backend: dict):
        self.backend = backend

    def call(self, prompt: str) -> str:
        # 实现 API 调用逻辑
        ...

# 在 get_ai_provider() 中添加分支
if t == "api_newai": return NewAIProvider(backend)
```

### 添加新任务类型

在 `tasks/registry.py` 的 `execute_task_logic()` 中添加分支：

```python
elif task_type == "newtask":
    # 实现任务逻辑
    body = ...
    subject = subject or "新任务结果"
```

### 环境变量命名规范

| 类型 | 命名格式 | 示例 |
|------|----------|------|
| 邮箱地址 | `MAIL_<NAME>_ADDRESS` | `MAIL_126_ADDRESS` |
| 邮箱密码/授权码 | `MAIL_<NAME>_PASSWORD` | `MAIL_126_PASSWORD` |
| 白名单 | `MAIL_<NAME>_ALLOWED` | `MAIL_126_ALLOWED` |
| API Key | `<PROVIDER>_API_KEY` | `ANTHROPIC_API_KEY` |
| 运行参数 | 大写 | `MAILBOX`, `AI`, `MODE`, `POLL_INTERVAL` |
| Workspace | `WORKSPACE_DIR` | `WORKSPACE_DIR="./workspace"` |

### Workspace（工作区）

**功能**：限制 AI 文件操作范围到指定目录，防止路径穿越攻击，增强安全性。

**配置**：
```bash
# 在 .env 中设置
WORKSPACE_DIR="./workspace"
```

**影响范围**：
- 归档输出（`reports/` 等）将限制在 workspace 目录内
- 未设置时保持向后兼容（不限制路径）

**安全机制**：
- 使用 `os.path.realpath()` 解析符号链接，防止路径穿越
- 通过 `validate_path()` 函数校验所有归档路径
- 超出 workspace 的操作会被拒绝并记录日志

### 测试

运行测试：
```bash
python3 -m pytest tests/
# 或
python3 tests/test_email_logic.py
```

测试覆盖：
- `decode_str()` - 邮件头解码
- `parse_ai_response()` - AI 响应 JSON 解析
- `is_sender_allowed()` - 白名单验证
- `get_body_and_attachments()` - 邮件正文和附件提取

## 安全建议

1. **白名单**: 始终设置 `ALLOWED` 为本人邮箱，防止陌生人滥用
2. **敏感文件**: `.env`, `credentials_gmail.json`, `token_*.json` 已在 `.gitignore` 中
3. **授权码**: 使用邮箱授权码而非登录密码
4. **OAuth**: 优先使用 OAuth 而非应用密码（更安全）
5. **manage.sh**: 包含敏感信息，不要提交到 git
6. **Workspace**: 生产环境建议设置 `WORKSPACE_DIR` 限制 AI 操作范围

## systemd 服务

`manage.sh install` 会动态生成 service 文件并安装到 `/etc/systemd/system/email-daemon.service`。

**注意**: 服务使用 `EnvironmentFile` 读取 `.env`，切换邮箱只需修改 `.env` 后重启服务。

```bash
# 查看服务状态
sudo systemctl status email-daemon

# 查看日志
sudo journalctl -u email-daemon -f
```

## Web UI

可选的 Web 界面，提供任务管理、日志查看、配置编辑等功能。

```bash
# 启动 Web UI
bash manage.sh webui

# 访问 http://localhost:8000
```

配置选项（`.env`）：
```bash
WEBUI_HOST="0.0.0.0"
WEBUI_PORT="8000"
WEBUI_PASSWORD=""       # 留空则不需要登录
WEBUI_SECRET=""         # Session 签名密钥
WEBUI_LANG="zh"         # 界面语言：zh/ja/ko/en
```

**支持的 AI 后端**：Web UI 配置页面已同步更新，支持所有 AI 后端：
- CLI 方式：Claude、Codex、Gemini、Qwen、Copilot
- 国际 API：OpenAI、Anthropic、Gemini API、DeepSeek、Groq、Perplexity、Cohere
- 中国 API：通义千问、月之暗面 Kimi、智谱 GLM、讯飞星火、百度文心一言、零一万物 Yi
- 本地模型：Ollama、vLLM

## 常见问题

### 日志位置

- 后台模式：`./daemon.log`
- systemd 模式：`sudo journalctl -u email-daemon -f`
- Web UI：`./webui.log`

### PID 文件

- 守护进程：`./daemon.pid`
- Web UI：`./webui.pid`, `./webui.pid.meta`

### 已处理邮件追踪

`processed_ids_<mailbox>.json` 存储已处理的邮件 ID，防止重复处理

### 定时任务文件

`tasks.db` (SQLite) 存储所有定时任务配置

### 报告归档

定时任务生成的报告自动保存到 `reports/` 目录，文件名格式：`YYYYMMDD_HHMMSS_<主题>.txt`

## 快速参考

### 常用命令

```bash
# 配置向导
bash manage.sh setup

# 启动/停止/重启
bash manage.sh start|stop|restart

# 查看状态
bash manage.sh status

# 实时日志
bash manage.sh log

# 安装 systemd 服务
bash manage.sh install

# 启动 Web UI
bash manage.sh webui

# 推送模板到邮箱
bash manage.sh push-templates
```

### 示例指令模板

```
# 定时日报（含天气、新闻、网页检索）
每天 18:00 生成日报：天气 Tokyo，新闻 AI，网页检索 OpenAI 发布会，并归档

# 每 2 小时新闻汇总
每 2 小时 新闻 AI 相关，归档

# 每天早上天气
每天 08:00 天气 Beijing

# 系统状态监控
每 10 分钟 提供 OS 系统运行状态信息（CPU/内存/磁盘/进程）

# 使用 cron 表达式
cron: 0 9 * * 1-5 工作日早上 9 点发送新闻摘要

# MCP 调用示例
查询 /home/user/reports 目录下的文件列表
```

## 多语言支持

系统支持多语言邮件指令和回复：
- **中文 (zh)**: 默认语言
- **日本語 (ja)**: 自动检测并切换提示语言
- **English (en)**: 自动检测并切换提示语言
- **한국어 (ko)**: 自动检测并切换提示语言

语言检测基于邮件正文内容自动识别，也可在 `.env` 中设置默认语言：
```bash
PROMPT_LANG="zh"  # zh/ja/en/ko
```

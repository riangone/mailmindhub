# MailMind — QWEN.md

## 项目概述

**MailMind** 是一个邮件到 AI 的桥接守护进程。用户发送包含指令的邮件，守护进程通过 IMAP 接收邮件，将指令传递给 AI 后端处理，然后通过 SMTP 将结果回复到用户邮箱。

**核心理念**：邮件即是界面，无需打开任何 App。

```
你发邮件（指令）→ MailMind 接收 → AI 处理 → 邮件回复结果
```

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3 |
| 核心依赖 | `requests`, `imapclient` |
| 可选依赖 | `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2` (Gmail OAuth), `msal` (Outlook OAuth) |
| 部署方式 | 后台进程 / systemd 服务 |

## 项目结构

```
MailMind/
├── email_daemon.py      # 核心守护进程 (~758 行)
├── manage.sh            # 服务管理脚本（启动/停止/重启/日志/systemd 安装）
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量模板
├── .env                 # 实际配置（需手动创建，包含敏感信息）
├── email-daemon.service # systemd 服务模板（由 manage.sh 生成）
├── README.md            # 用户文档（多语言）
├── CLAUDE.md            # Claude Code 上下文
└── QWEN.md              # 本文件
```

## 构建与运行

### 环境准备

```bash
# 克隆项目
git clone https://github.com/yourname/MailMind.git
cd MailMind

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装基础依赖
pip install -r requirements.txt

# 可选：Gmail OAuth 支持
pip install google-auth google-auth-oauthlib google-auth-httplib2

# 可选：Outlook OAuth 支持
pip install msal
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填写邮箱凭证和 AI 配置
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

# 直接运行
python3 email_daemon.py --mailbox gmail --ai claude          # IMAP IDLE 模式（默认）
python3 email_daemon.py --mailbox 126 --ai anthropic --poll  # 轮询模式
python3 email_daemon.py --list                               # 显示配置状态
python3 email_daemon.py --mailbox gmail --auth               # 首次 OAuth 授权
```

### 运行模式

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
| `qwen` | `qwen --prompt` | Qwen CLI 已安装 |
| `copilot` | `copilot` | GitHub Copilot CLI 已安装 |

### API 方式

| 名称 | 所需环境变量 | 默认模型 |
|------|-------------|----------|
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `gemini-api` | `GEMINI_API_KEY` | `gemini-3-flash-preview` |
| `qwen-api` | `QWEN_API_KEY` | `qwen-max` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |

## 核心架构

### 数据流

```
fetch_unread_emails() → process_email() → call_ai() → send_reply()
```

### 关键数据结构

**`MAILBOXES`** (email_daemon.py ~line 29)
- 邮箱预设字典，键名为 `126`, `163`, `qq`, `gmail`, `outlook`
- 包含 IMAP/SMTP 服务器、端口、认证类型、环境变量名

**`AI_BACKENDS`** (email_daemon.py ~line 99)
- AI 后端预设字典
- `type`: `cli`, `api_anthropic`, `api_openai`, `api_gemini`, `api_qwen`, `cli_copilot`

### 邮件处理流程

1. **接收邮件**: `fetch_unread_emails()` 通过 IMAP 获取未读邮件
2. **白名单检查**: 验证发件人是否在 `ALLOWED` 列表中
3. **提取内容**: `get_body_and_attachments()` 提取正文和附件
4. **调用 AI**: `call_ai()` 使用 `PROMPT_TEMPLATE` 调用 AI
5. **解析响应**: 期望 AI 返回 JSON:
   ```json
   {
     "subject": "邮件标题",
     "body": "回复正文",
     "attachments": [{"filename": "report.md", "content": "文件内容"}]
   }
   ```
6. **发送回复**: `send_reply()` 通过 SMTP 发送回复（含附件）

### 附件支持

- **接收**: 文本附件（.txt, .md, .csv）解码后追加到 AI prompt；二进制附件（PDF, 图片）仅记录文件名
- **发送**: AI 返回的 `attachments` 字段被 base64 编码后作为 MIME 附件发送

## 开发约定

### 添加新邮箱

在 `email_daemon.py` 的 `MAILBOXES` 字典中添加条目：

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
},
```

### 添加新 AI 后端

在 `email_daemon.py` 的 `AI_BACKENDS` 字典中添加条目：

```python
"newai": {"type": "api_newai", "api_key": os.environ.get("NEWAI_API_KEY", ""), "model": "model-name"},
```

### 环境变量命名规范

| 类型 | 命名格式 | 示例 |
|------|----------|------|
| 邮箱地址 | `MAIL_<NAME>_ADDRESS` | `MAIL_126_ADDRESS` |
| 邮箱密码/授权码 | `MAIL_<NAME>_PASSWORD` | `MAIL_126_PASSWORD` |
| 白名单 | `MAIL_<NAME>_ALLOWED` | `MAIL_126_ALLOWED` |
| API Key | `<PROVIDER>_API_KEY` | `ANTHROPIC_API_KEY` |
| 运行参数 | 大写 | `MAILBOX`, `AI`, `MODE`, `POLL_INTERVAL` |

## 安全建议

1. **白名单**: 始终设置 `ALLOWED` 为本人邮箱，防止滥用
2. **敏感文件**: `.env`, `credentials_gmail.json`, `token_*.json` 已在 `.gitignore` 中
3. **授权码**: 使用邮箱授权码而非登录密码
4. **OAuth**: 优先使用 OAuth 而非应用密码（更安全）

## systemd 服务

`manage.sh install` 会动态生成 service 文件并安装到 `/etc/systemd/system/email-daemon.service`。

**注意**: 目前仅内联 `MAIL_126_*` 变量，若使用其他邮箱，需手动在 service 文件中添加对应的 `Environment=` 行。

```bash
# 查看服务状态
sudo systemctl status email-daemon

# 查看日志
sudo journalctl -u email-daemon -f
```

## 常见问题

### 日志位置

- 后台模式：`./daemon.log`
- systemd 模式：`sudo journalctl -u email-daemon -f`

### PID 文件

`./daemon.pid` 存储当前运行的进程 ID

### 已处理邮件追踪

`processed_ids` 集合在内存中追踪已处理的邮件 ID，守护进程重启后重置

## 测试

目前没有自动化测试套件。手动测试流程：

1. 启动守护进程
2. 从白名单邮箱发送测试邮件
3. 60 秒内检查是否收到 AI 回复

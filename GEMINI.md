# MailMind 项目指南

**MailMind** 是一个基于 Python 的 AI 邮件守护进程。它通过 IMAP 协议监听邮箱（支持 IDLE 实时推送或轮询），利用多种 AI 后端（命令行工具或 API）处理收到的邮件指令，并自动通过 SMTP 协议回复处理结果。其设计目标是为 AI 模型提供一个轻量级的“邮件即界面（Email-as-an-Interface）”运行环境。

## 🛠️ 技术栈与核心技术

- **开发语言**: Python 3.8+
- **邮件协议**: IMAP（接收/监听）与 SMTP（发送）。
- **AI 后端支持**:
    - **CLI 工具**: Claude Code (`claude`), Gemini CLI (`gemini`), Codex CLI (`codex`), 通义千问 CLI (`qwen`)。
    - **API 接口**: Anthropic, OpenAI, Gemini API, 通义千问 API。
- **关键库**: `imaplib`, `smtplib`, `requests`, `imapclient` (用于 IDLE 模式)。
- **服务管理**: 使用 Bash 脚本 (`manage.sh`) 进行生命周期管理，并支持 systemd 服务集成。

## 📂 项目结构

- `email_daemon.py`: 核心守护进程，实现主循环、邮件解析、AI 调用逻辑及自动回复。
- `manage.sh`: 统一管理脚本，支持启动、停止、重启、查看日志及安装为系统服务。
- `.env.example`: 环境变量模板，包含邮箱凭据、白名单及 AI API 密钥配置。
- `requirements.txt`: Python 依赖列表。
- `--email-daemon.service`: 用于 Linux systemd 的服务配置模板。

## 🚀 部署与运行

### 环境准备
- Python 3.x
- 建议使用虚拟环境 (venv)
- 已安装相应的 AI CLI 工具或拥有有效的 API Key

### 安装步骤
1. **克隆项目**:
   ```bash
   git clone <repository_url> MailMind
   cd MailMind
   ```
2. **初始化环境**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **配置文件**:
   ```bash
   cp .env.example .env
   # 编辑 .env，填写邮箱地址、授权码/应用密码及 AI 密钥
   ```

### 运行管理
使用 `manage.sh` 脚本进行操作：
- **启动**: `bash manage.sh start`
- **停止**: `bash manage.sh stop`
- **重启**: `bash manage.sh restart`
- **查看状态/日志**: `bash manage.sh status` 或 `bash manage.sh log`
- **安装为系统服务**: `bash manage.sh install`（支持开机自启）

## 🛠️ 开发与贡献规范

### 配置项 (Environment Variables)
项目高度依赖 `.env` 文件进行配置。关键变量包括：
- `MAILBOX`: 指定使用的邮箱配置（如 `126`, `gmail`, `outlook`）。
- `AI`: 指定使用的 AI 后端（如 `claude`, `gemini-api`, `anthropic`）。
- `MAIL_<NAME>_ALLOWED`: **安全白名单**，仅允许来自特定地址或域名的邮件触发 AI。

### 安全建议
- **白名单机制**: 务必配置 `ALLOWED` 变量，防止接口被非法调用。
- **敏感信息**: 严禁将 `.env`、`token_*.json` 或 `credentials_*.json` 提交至版本库。

### 扩展 AI 后端
若需添加新的 AI 支持，需在 `email_daemon.py` 的 `AI_CONFIGS` 字典中添加配置，并在 AI 处理逻辑部分实现对应的调用接口。

## 📜 待办事项与改进方向
- [ ] 增加邮件解析和回复格式化的单元测试。
- [ ] 优化长连接（IDLE）模式下的网络异常自动重连机制。
- [ ] 扩展支持更多小众邮件服务商的自动配置。

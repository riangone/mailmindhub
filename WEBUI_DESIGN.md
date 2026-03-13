# MailMind Web UI 设计文档

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Jinja2 模板 |
| 前端交互 | HTMX 2.0.4 + htmx-ext-sse 2.2.2 |
| 字体 | JetBrains Mono (Google Fonts CDN) |
| 样式 | 纯手写 CSS（无框架） |
| 日志推送 | SSE (Server-Sent Events) |

## 文件结构

```
webui/
├── __init__.py
├── server.py               # FastAPI 应用主文件
├── templates/
│   ├── index.html          # 页面骨架
│   └── partials/
│       ├── header_status.html   # 顶部状态栏（含守护进程控制按钮）
│       ├── tab_mail.html        # 邮件设置 Tab
│       ├── tab_ai.html          # AI 设置 Tab
│       ├── tab_logs.html        # 日志查看 Tab
│       └── autoconfig_result.html  # 邮箱自动检测结果片段
└── static/
    └── style.css           # 全局样式
```

## 路由表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 首页（加载邮件设置 Tab） |
| GET | `/partials/header_status` | 状态栏局部刷新（每 5s 轮询） |
| GET | `/tabs/mail` | 邮件设置 Tab 内容 |
| GET | `/tabs/ai` | AI 设置 Tab 内容 |
| GET | `/tabs/logs` | 日志 Tab 内容 |
| POST | `/autoconfig` | 邮箱域名检测，返回服务器配置片段 |
| POST | `/config/mail` | 保存邮件设置 |
| POST | `/config/ai` | 保存 AI 设置 |
| POST | `/daemon/{action}` | 启动/停止/重启守护进程 |
| GET | `/logs/stream` | SSE 日志实时推流 |

## UI 布局

```
┌─────────────────────────────────────────────────┐
│ MAILMIND  ● PID:1234 · 126 · deepseek · IDLE  ▶■↺│  ← header (黑底)
├─────────────────────────────────────────────────┤
│ [邮件设置]  [AI 设置]  [日志]                    │  ← nav tabs
├─────────────────────────────────────────────────┤
│                                                  │
│  MAILBOX ADDRESS                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ your@example.com                         │   │
│  └──────────────────────────────────────────┘   │
│  ▌AUTO  自动检测成功                            │
│  IMAP imap.example.com:993                       │  ← #content
│  SMTP smtp.example.com:465                       │
│                                                  │
│  [保存邮件设置]                                  │
│                                                  │
└─────────────────────────────────────────────────┘
```

## 设计规范

- **字体**: JetBrains Mono，13px 正文，10px 标签（大写 + 字距）
- **配色**: 背景 #fafafa，前景 #0f0f0f，Header 纯黑 #0f0f0f
- **强调色**: 仅一种 —— #22c55e（绿色，运行状态指示点）
- **边框圆角**: 0（全部直角）
- **日志区**: 黑底 #0d0d0d，绿色文字 #a3e635

## 启动命令

```bash
# 安装依赖
pip install fastapi uvicorn jinja2 httpx python-multipart

# 启动 Web UI（默认 0.0.0.0:8765）
python3 webui/server.py

# 指定地址端口
python3 webui/server.py --host 127.0.0.1 --port 9000
```

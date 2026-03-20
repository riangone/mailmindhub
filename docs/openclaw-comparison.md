# MailMindHub vs OpenClaw 功能对比与路线图

> OpenClaw 是 2026 年 GitHub 上获得 68,000 星的开源 AI 代理工具，由 PSPDFKit 创始人 Peter Steinberger 创建。
> 定位：全天候主动运行的个人 AI 助手，连接 AI 模型与本地文件、消息应用。

## 功能对比

| 功能 | OpenClaw | MailMindHub |
|------|----------|-------------|
| 邮件读取 / 自动回复 | ✅ | ✅ |
| 多 AI 后端集成 | ✅ | ✅ |
| 技能插件系统 | ✅ 100+ 技能 | ✅ 少量内置 |
| 定时任务调度 | ✅ | ✅ |
| 网页搜索 | ✅ | ✅ |
| Gmail / Outlook OAuth | ✅ | ✅ |
| WhatsApp / Discord 集成 | ✅ | ❌ |
| 本地文件操作 | ✅ | 部分支持 |
| Shell 命令执行 | ✅ | ❌ |
| 网页自动化 | ✅ | ❌ |
| 邮件标签 / 整理 | ✅ | 部分支持 |
| 100+ 预设技能库 | ✅ | ❌ |

---

## 改进路线图

### 优先级：高

#### 1. 消息渠道扩展

将 MailMindHub「邮件接收 → AI 处理 → 邮件回复」的核心循环扩展到其他渠道：

```
skills/
  whatsapp.py    # WhatsApp Business API
  discord.py     # Discord Bot
  telegram.py    # Telegram Bot API
```

每个渠道实现统一的消息收发接口，复用现有的 AI 调用和任务调度逻辑。

#### 2. Shell 命令执行技能

```python
# skills/shell_exec.py
class ShellExecSkill(BaseSkill):
    name = "shell_exec"
    description = "Execute sandboxed shell commands"
    keywords = ["run", "execute", "command", "script"]

    def run(self, payload: dict, ai_caller=None) -> str:
        # 在沙箱环境中执行命令，限制权限和超时
        result = subprocess.run(
            payload["command"],
            shell=True,
            capture_output=True,
            timeout=30,
            text=True
        )
        return result.stdout or result.stderr

SKILL = ShellExecSkill()
```

这是通用性最高的单项改进，可解锁大量自动化场景。

#### 3. 网页自动化技能

```python
# skills/browser.py（基于 Playwright）
class BrowserSkill(BaseSkill):
    name = "web_automation"
    description = "Browse and interact with web pages"
    keywords = ["scrape", "browse", "click", "fill form"]
```

---

### 优先级：中

#### 4. 邮件整理能力增强

利用现有 `manage_only` 邮箱机制，扩展以下 IMAP 操作（在 `core/mail_client.py` 中实现）：

- 自动标签 / 文件夹归类
- 已读标记 / 星标 / 归档标志操作
- 邮件线程智能整理

#### 5. 技能库扩充

在现有 `translate`、`summarize`、`code_review` 基础上新增：

```
skills/
  invoice.py       # 发票 / 账单处理
  lead_nurture.py  # 销售线索管理
  ticket.py        # 支持工单处理
  calendar.py      # 日历事件集成（Google / Outlook）
  github.py        # GitHub Issue / PR 操作
  weather.py       # 天气查询（现已在 tasks/ 中，可提升为技能）
```

#### 6. Gmail Push 通知（Google Pub/Sub）

替代现有 IMAP IDLE，实现更低延迟的邮件接收：

```
core/
  pubsub_client.py   # Google Cloud Pub/Sub 订阅
```

---

### 优先级：低

#### 7. Web UI 工作流构建器

OpenClaw 提供可视化的工作流编排界面。可在 `webui/server.py` 中新增：

- 拖拽式技能链构建
- 规则触发器配置（如：发件人 + 关键词 → 指定技能）

---

## 核心优势与差异化定位

MailMindHub 已具备坚实基础：**邮件专精 × 多 AI 后端 × 任务调度器**。

与 OpenClaw 相比的差异化方向：

| 维度 | OpenClaw | MailMindHub 定位 |
|------|----------|------------------|
| 渠道 | 多渠道（邮件、WhatsApp、Discord）| 邮件深度集成 + 渐进扩展 |
| AI 后端 | 主要为单一模型 | 15+ AI 后端自由切换 |
| 部署 | 自托管 | 自托管 + systemd 原生集成 |
| 邮件协议 | Gmail API / Pub/Sub 为主 | IMAP/SMTP 广泛兼容 |

**最快缩短差距的三步：**

1. `skills/shell_exec.py` — 通用性最高，一周内可完成
2. `skills/telegram.py` — 实现成本低，扩展消息渠道
3. 扩充技能数量至 20+ — 建立社区贡献机制

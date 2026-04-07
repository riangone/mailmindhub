# MailMindHub

> **Send an email, get an AI response. That simple.**

**[中文](#中文)** | **[日本語](#日本語)** | **[English](#english)** | **[한국어](#한국어)**

---

<a name="中文"></a>
# 中文

## MailMindHub — 通过邮件与 AI 对话

通过发送邮件向 AI 下达指令，AI 处理后自动将结果回复到你的邮箱。无需打开任何 App，邮件即是界面。

```
你发邮件（指令）→ MailMindHub 接收 → AI 处理 → 邮件回复结果
```

### ✨ 功能特性

- **多邮箱支持**：126、163、QQ、Gmail（OAuth/应用密码）、Outlook（OAuth）
- **多 AI 支持**：
  - **CLI 方式**：Claude Code、Codex、Gemini、通义千问、GitHub Copilot
  - **国际 API**：Anthropic、OpenAI、Gemini、DeepSeek、Groq、Perplexity、Cohere
  - **中国 API**：通义千问、月之暗面 Kimi、智谱 GLM、讯飞星火、百度文心一言、零一万物 Yi
- **白名单安全**：每个邮箱独立配置白名单，支持多个地址或域名
- **AI 自动拟标题**：AI 根据回复内容自动生成邮件标题
- **多语言自动检测与回复**：自动识别邮件语言（中/英/日/韩），AI 自动以对应语言回复
- **服务化管理**：一个脚本完成启动、停止、重启、日志、系统服务安装
- **定时任务扩展**：可定时执行 AI 任务、天气、新闻、网页检索与日报汇总（支持归档）

### 📦 安装

```bash
git clone https://github.com/yourname/MailMindHub.git
cd MailMindHub
python3 -m venv venv
source venv/bin/activate
pip install requests
```

### ⚙️ 配置与认证

编辑 `manage.sh` 顶部配置区，选择邮箱和 AI：

```bash
MAILBOX="126"   # 使用的邮箱
AI="claude"     # 使用的 AI
```

---

### ⏰ 定时任务与外部数据（默认方案）

新增任务类型支持：`email` / `ai_job` / `weather` / `news` / `web_search` / `report` / `system_status`。  
当指令包含定时（`schedule_at`/`schedule_every`）且设置 `task_type` 时，任务会按类型执行并可归档到 `reports/`。

**默认所需环境变量：**

```bash
export WEATHER_API_KEY="your_weatherapi_key"
export NEWS_API_KEY="your_newsapi_key"
export BING_API_KEY="your_bing_search_key"
export TASK_DEFAULT_AI="openai"   # 任务使用的默认 AI（不填则使用启动参数 --ai）
```

**可选默认参数：**

```bash
export WEATHER_DEFAULT_LOCATION="Tokyo"
export NEWS_DEFAULT_QUERY="technology OR AI"
export NEWS_DEFAULT_LANGUAGE="zh"
export NEWS_DEFAULT_COUNTRY=""
export NEWS_DEFAULT_PAGE_SIZE="8"
```

### 📋 指令模板

**方式一：推送模板到邮箱（推荐）**

运行以下命令将 7 个预制模板直接写入邮箱的 `MailMindHub模板` 文件夹，在邮件客户端打开即可编辑发送：

```bash
bash manage.sh push-templates
```

**方式二：发送「帮助」获取模板列表**

给 MailMindHub 邮箱发一封正文为 `帮助`（或 `模板`）的邮件，系统会自动回复全部模板，无需调用 AI。

---

**常用指令示例：**

**1) 定时日报（含天气、新闻、网页检索）**

```
每天 18:00 生成日报：天气 Tokyo，新闻 AI，网页检索 OpenAI 发布会，并归档
```

**2) 每 2 小时新闻汇总**

```
每2小时 新闻 AI 相关，归档
```

**3) 每天早上天气**

```
每天 08:00 天气 Beijing
```

**4) 每天网页检索某关键词**

```
每天 09:30 网页检索 深度学习 前沿
```

**5) 定期 AI 工作**

```
每周一 10:00 AI 分析：整理上周项目进度并生成下周计划，归档
```

**6) 每 10 分钟系统运行状态**

```
每10分钟 提供 OS 系统运行状态信息（CPU/内存/磁盘/进程）
```

### ⚙️ 自动识别说明

当用户未显式给出 `task_type` 时，系统会根据关键词自动判断任务类型与定时参数：
- `天气` / `weather` → `weather`
- `新闻` / `news` → `news`
- `检索` / `搜索` / `网页` / `search` → `web_search`
- `日报` / `周报` / `月报` / `report` → `report`
- `AI` / `分析` / `总结` / `翻译` / `生成` → `ai_job`
- `系统` / `OS` / `运行状态` / `CPU` / `内存` / `磁盘` / `进程` → `system_status`
- 包含 `归档` / `archive` / `保存` → 自动启用归档
- 包含 `不要发邮件` / `no email` / `仅归档` → 关闭邮件发送

时间识别规则：
- `每 X 分钟/小时/天` 会自动解析为 `schedule_every`
- `YYYY-MM-DD HH:MM` 或 `YYYY-MM-DD` 会解析为 `schedule_at`
- `截止 YYYY-MM-DD` 会解析为 `schedule_until`

支持更多自然时间：
- `今天/明天/今晚/早上/下午` + 时间（如 `明天 8:30`）
- `每天 18:00` 会自动生成 `schedule_every=1d` 与下一次执行时间
- `每周一 10:00` 会自动生成 `schedule_every=7d` 与下一次执行时间

多任务识别：
- 使用分号、中文分号或换行分隔，可自动拆分成多个任务并分别定时执行

### 💻 编码开发指令模板

以下模板适用于 **CLI AI + WORKSPACE_DIR** 配置（AI 可直接读写项目文件，无需粘贴代码）。

> **通用结构**
> ```
> 【任务类型】简短标题
>
> 目标：具体要做什么
> 文件：涉及哪些文件/目录
> 要求：风格/约束/注意事项
> ```

---

**🆕 新功能开发**

```
【新功能】实现用户登录限流

目标：在 auth/login.py 的登录接口加入限流逻辑，
      同一 IP 5分钟内失败超过5次则锁定10分钟。
文件：auth/login.py，utils/cache.py
要求：
- 用现有的 Redis 客户端，不要引入新依赖
- 锁定期间返回 429 状态码和剩余等待时间
- 写对应的单元测试
```

**🐛 Bug 修复**

```
【Bug】用户头像上传偶发 500 错误

现象：上传大于 2MB 的图片时概率报错，日志：
  OSError: [Errno 28] No space left on device

文件：api/upload.py，core/storage.py
要求：
- 找出根本原因
- 上传前先检查临时目录空间
- 失败时返回友好的错误信息而非 500
```

**🔍 代码审查**

```
【审查】检查 payment/ 模块的安全性

文件：payment/
重点检查：
- SQL 注入风险
- 敏感信息是否明文记录在日志
- 金额计算是否存在浮点精度问题
- 异常处理是否完整
输出：列出问题清单（按严重程度排序），不要直接修改代码
```

**♻️ 重构**

```
【重构】拆分 god class UserManager

文件：services/user_manager.py（当前约800行）
目标：按职责拆分为独立模块：
- UserAuthService    ← 认证相关
- UserProfileService ← 资料相关
- UserNotifyService  ← 通知相关
要求：
- 保持对外接口不变（向后兼容）
- 原有测试必须全部通过
- 不要修改数据库 Schema
```

**🧪 补充测试**

```
【测试】为 utils/parser.py 补充单元测试

文件：utils/parser.py，tests/test_parser.py
要求：
- 覆盖所有 public 函数
- 重点覆盖边界条件：空输入、超长输入、特殊字符
- 使用现有的 pytest 框架和 fixture 风格
- 目标覆盖率 90% 以上
```

**⚡ 性能优化**

```
【性能】优化首页接口响应时间

文件：api/home.py
背景：P99 约 800ms，瓶颈在 get_recommended_items()，每次都全量查询数据库。
要求：
- 加入内存缓存，TTL 5分钟
- 缓存 key 包含用户 ID
- 不改变接口返回格式
- 注释中说明缓存策略
```

**🗄️ 数据库变更**

```
【数据库】为 orders 表添加软删除支持

文件：models/order.py，migrations/（Alembic）
目标：
- 添加 deleted_at 字段（nullable timestamp）
- 所有查询默认过滤已删除记录
- 添加 soft_delete() 和 restore() 方法
- 生成对应的 migration 文件
注意：不影响现有的硬删除逻辑
```

**📡 API 设计**

```
【API】设计文件批量下载接口

文件：api/files.py，core/zip_helper.py（不存在则新建）
要求：
- POST /api/files/batch-download，接受 file_ids 数组，打包成 zip 返回
- 最多 50 个文件，总大小不超过 100MB
- 超出限制返回 400 和明确的错误信息
- 添加 OpenAPI 注释
```

**🔐 安全加固**

```
【安全】审查并修复 API 鉴权漏洞

文件：middleware/auth.py，api/（全目录）
任务：
1. 找出所有未经鉴权即可访问的接口
2. 检查 JWT 验证是否存在 alg=none 攻击风险
3. 修复发现的问题
4. 回复中附上修复清单
```

**📖 文档补全**

```
【文档】为 core/ 模块补充 docstring

文件：core/（全目录）
要求：
- 为每个 public 函数补充 Google 风格 docstring
- 包含参数类型、返回值、异常说明
- 只补充缺失的，不修改已有的
- 不改动任何业务逻辑
```

**🔗 依赖升级**

```
【升级】将 SQLAlchemy 从 1.4 升级到 2.0

文件：requirements.txt，models/（全目录），database.py
背景：2.0 的 Session 用法有 breaking change。
要求：
- 更新所有废弃的 API 用法
- 保持现有测试全部通过
- 回复中列出主要改动点
```

**🚨 紧急修复**

```
【紧急】生产报错，立即修复

错误：TypeError: 'NoneType' object is not subscriptable
位置：services/order.py，create_order() 函数
请找出原因并修复，不要改动其他逻辑。
```

**🔄 多轮迭代（回复上一封继续对话）**

```
（直接回复上一封邮件）

上面的实现有个问题：当 user_id 为空时会崩溃。
请在 validate_input() 中加入空值检查，其他不变。
```

```
（再次回复继续）

测试跑了，有两个失败：
  FAILED tests/test_order.py::test_create_with_null_user
  FAILED tests/test_order.py::test_bulk_create

请查看测试文件，修复这两个用例。
```

---

**常用修饰词**（加在任意模板末尾）：

| 需求 | 添加的语句 |
|------|-----------|
| 只分析不改代码 | `输出：只分析，不修改任何文件` |
| 改完跑测试 | `改完后运行 pytest tests/ 确认通过` |
| 保守修改 | `改动范围尽量小，不做额外优化` |
| 解释改动 | `在回复正文中说明改了什么、为什么` |
| 分步执行 | `先只做第1步，等我确认再继续` |

#### 📮 126 / 163 / QQ 邮箱（授权码方式）

1. 登录网页版邮箱 → **设置** → **POP3/IMAP/SMTP**
2. 开启 **IMAP 服务**，按提示发短信获取**授权码**（16位）
3. 在 `manage.sh` 中填写：

```bash
export MAIL_126_ADDRESS="your@126.com"
export MAIL_126_PASSWORD="your-auth-code"   # 授权码，不是登录密码
export MAIL_126_ALLOWED="your@126.com"
```

---

#### 📮 Gmail — OAuth 方式（推荐）

**第一步：创建 Google Cloud 项目**
1. 打开 https://console.cloud.google.com/ → 新建项目
2. **API 和服务** → **启用 API** → 搜索 `Gmail API` → 启用
3. **OAuth 同意屏幕** → 外部 → 填写应用名称 → 添加测试用户（你的 Gmail）
4. **凭据** → **创建凭据** → **OAuth 客户端 ID** → 类型选**桌面应用**
5. 下载 JSON 文件，重命名为 `credentials_gmail.json` 放到项目目录

**第二步：安装依赖**
```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2
```

**第三步：首次授权（只需一次）**
```bash
export MAIL_GMAIL_ADDRESS="your@gmail.com"
export MAIL_GMAIL_ALLOWED="your@gmail.com"
python3 email_daemon.py --mailbox gmail --auth
```
终端会打印一个 URL，在本地浏览器打开 → 用 Google 账号登录授权 → 将页面显示的 code 粘贴回终端。
授权成功后自动保存 `token_gmail.json`，之后 token 自动刷新，无需再次授权。

---

#### 📮 Gmail — 应用专用密码方式（较简单）

1. 开启 Google 账号两步验证
2. 打开 https://myaccount.google.com/apppasswords → 生成应用密码（16位）
3. Gmail 网页版 → 设置 → 转发和 POP/IMAP → 启用 IMAP
4. 修改 `email_daemon.py` 中 gmail 的 `"auth": "oauth_google"` 改为 `"auth": "password"`
5. 在 `manage.sh` 中填写：

```bash
export MAIL_GMAIL_ADDRESS="your@gmail.com"
export MAIL_GMAIL_PASSWORD="xxxx xxxx xxxx xxxx"   # 16 位应用专用密码
export MAIL_GMAIL_ALLOWED="your@gmail.com"
```

---

#### 📮 Outlook — OAuth 方式

**第一步：在 Azure Portal 注册应用**
1. 打开 https://portal.azure.com/ → **Azure Active Directory** → **应用注册** → **新注册**
2. 名称随意，受支持的账户类型选**任何组织目录中的账户和个人 Microsoft 账户**
3. 重定向 URI 类型选**公共客户端/本机**，值填 `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. 注册完成后复制**应用程序（客户端）ID**

**第二步：安装依赖**
```bash
pip install msal
```

**第三步：首次授权（只需一次，设备码方式）**
```bash
export MAIL_OUTLOOK_ADDRESS="your@outlook.com"
export OUTLOOK_CLIENT_ID="your-client-id"
export MAIL_OUTLOOK_ALLOWED="your@outlook.com"
python3 email_daemon.py --mailbox outlook --auth
```
终端会显示一个**短码**和 URL：
- 在本地浏览器打开 https://microsoft.com/devicelogin
- 输入终端显示的短码（如 `ABCD1234`）
- 用 Microsoft 账号登录并授权

授权成功后自动保存 `token_outlook.json`，之后自动刷新。

---

### 🚀 启动与管理

```bash
bash manage.sh start            # 后台启动
bash manage.sh stop             # 停止
bash manage.sh restart          # 重启
bash manage.sh status           # 查看状态和最近日志
bash manage.sh log              # 实时查看日志
bash manage.sh push-templates   # 将指令模板写入邮箱文件夹
bash manage.sh install          # 安装为 systemd 服务（开机自启）
bash manage.sh uninstall        # 卸载 systemd 服务
```

启动后，给配置的邮箱发一封邮件，正文写指令，60秒内收到 AI 回复。

### 🧩 系统托盘（纯 Python 方案）

托盘入口会同时管理「邮件守护进程」与「Web UI」，并提供快捷菜单操作：

- **Start Service**：启动守护进程 + Web UI
- **Restart**：重启两者
- **Stop**：停止两者
- **Open Console**：打开浏览器访问 `http://localhost:8000`
- **Quit**：退出托盘并停止服务

**启动方式**

```bash
python3 tray_app.py
```

**运行说明**

- 托盘启动时会读取 `.env` 中的 `MAILBOX` / `AI` / `MODE` / `WEBUI_HOST` / `WEBUI_PORT` 作为启动参数。
- 日志输出到 `daemon.log` 与 `webui.log`。
- Web UI 依赖 `fastapi/uvicorn/jinja2/python-multipart/itsdangerous`，未安装会导致 Web UI 子进程启动失败（可在 `webui.log` 中查看）。

### 🤖 支持的 AI

> **💡 如何选择 CLI 还是 API？**
>
> - **CLI 模式（推荐简单使用）**：AI 工具本身具备读取本地文件、联网搜索、执行代码等能力，MailMindHub 只需将你的邮件指令传递过去，AI 会自主收集所需上下文。配置最少，开箱即用。
> - **API 模式（适合服务器/云部署）**：AI 只能处理你显式发送的文本内容。若需要天气、新闻、网页搜索等实时数据，必须在 `.env` 中单独配置对应的数据源（`WEATHER_API_KEY`、`NEWS_API_KEY`、`WEB_SEARCH` 等）。

#### CLI 方式

| 参数名 | 说明 | 所需环境 |
|--------|------|----------|
| `claude` | Claude Code | 需安装 Claude Code |
| `codex` | OpenAI Codex CLI | 需安装 Codex CLI |
| `gemini` | Gemini CLI | 需安装 Gemini CLI |
| `qwen` | 通义千问 CLI | 需安装 Qwen CLI |
| `copilot` | GitHub Copilot CLI | 需安装 Copilot CLI |

#### API 方式 - 国际模型

| 参数名 | 说明 | 所需环境变量 |
|--------|------|--------------|
| `anthropic` | Anthropic API | `ANTHROPIC_API_KEY` |
| `openai` | OpenAI API | `OPENAI_API_KEY` |
| `gemini-api` | Gemini API | `GEMINI_API_KEY` |
| `deepseek` | DeepSeek API | `DEEPSEEK_API_KEY` |
| `groq` | Groq 高速推理 | `GROQ_API_KEY` |
| `perplexity` | Perplexity 搜索增强 | `PERPLEXITY_API_KEY` |
| `cohere` | Cohere 企业级 | `COHERE_API_KEY` |

#### API 方式 - 中国模型

| 参数名 | 说明 | 所需环境变量 |
|--------|------|--------------|
| `qwen-api` | 通义千问（阿里云） | `QWEN_API_KEY` |
| `moonshot` | 月之暗面 Kimi | `MOONSHOT_API_KEY` |
| `glm` | 智谱 AI（清华系） | `GLM_API_KEY` |
| `spark` | 讯飞星火 | `SPARK_API_KEY` |
| `ernie` | 百度文心一言 | `ERNIE_API_KEY` |
| `yi` | 零一万物 | `YI_API_KEY` |

### 🔒 安全建议

- 设置 `ALLOWED` 白名单为自己的邮箱，防止陌生人触发 AI
- `credentials_gmail.json`、`token_*.json` 已加入 `.gitignore`，不会被提交
- `manage.sh` 包含密码，推送前检查或加入 `.gitignore`

### 🛡️ Workspace（可选）

限制 AI 文件操作范围到指定目录，增强安全性：

```bash
# 在 .env 中配置
WORKSPACE_DIR="./workspace"
```

设置后，所有归档输出（如 `reports/`）将限制在该目录内，防止路径穿越攻击。留空则不限制（向后兼容）。

### 💡 有效使用技巧

长期使用 MailMindHub 后，交互记录本身可能导致收件箱混乱。以下方案可以保持整洁：

**1. 使用专用交互邮箱（最推荐）**

创建一个专门用于 MailMindHub 的邮箱账号，所有指令和回复都在那里，完全不影响主邮箱。

**2. 定时任务结果存本地，不发邮件**

发送指令时指定不发邮件，只归档到本地：

```
每天 8 点生成系统状态报告，不发邮件，存到 reports 目录
```

AI 会生成带 `"output": {"email": false, "archive": true}` 的任务，结果只写入 `reports/` 文件夹。

**3. 用邮件客户端过滤器自动归文件夹**

在 Gmail/Outlook 中建立规则：来自 MailMindHub 邮箱的回复自动移入专属文件夹，不出现在主收件箱。

**4. 统一主题命名，利用线程聚合**

同类指令使用固定主题，所有相关回复自动汇聚成一个线程：

```
主题：【天气查询】     ← 所有天气相关指令
主题：【代码任务】     ← 所有代码修改指令
主题：【每日简报】     ← 定时任务线程
```

**5. 用 `email_manage` 定期清理交互记录**

```
把 30 天前主题含【AI回复】的邮件全部归档
```

---

<a name="日本語"></a>
# 日本語

## MailMindHub — メールで AI と対話する

メールで指示を送ると、AI が処理して結果をメールで返信します。アプリ不要、メールがインターフェースです。

```
メール送信（指示）→ MailMindHub 受信 → AI 処理 → メールで返信
```

### ✨ 主な機能

- **複数メールボックス対応**：126、163、QQ、Gmail（OAuth/アプリパスワード）、Outlook（OAuth）
- **複数 AI 対応**：CLI 方式（Claude Code、Codex、Gemini、Qwen）、API 方式（Anthropic、OpenAI、Gemini API、Qwen API）
- **ホワイトリスト機能**：メールボックスごとに独立設定、複数アドレス・ドメイン対応
- **AI による件名自動生成**：返信内容に基づき AI が件名を自動作成
- **サービス管理**：1 スクリプトで起動・停止・再起動・ログ・systemd 登録

### 📦 インストール

```bash
git clone https://github.com/yourname/MailMindHub.git
cd MailMindHub
python3 -m venv venv
source venv/bin/activate
pip install requests
```

### ⚙️ 設定と認証

---

#### 📮 126 / 163 / QQ メール（認証コード方式）

1. ウェブメール → **設定** → **POP3/IMAP/SMTP** → IMAP サービスを有効化
2. SMS 認証で**認証コード**（16桁）を取得
3. `manage.sh` に記入：

```bash
export MAIL_126_ADDRESS="your@126.com"
export MAIL_126_PASSWORD="your-auth-code"
export MAIL_126_ALLOWED="your@126.com"
```

---

#### 📮 Gmail — OAuth 方式（推奨）

**ステップ 1：Google Cloud プロジェクト作成**
1. https://console.cloud.google.com/ → 新しいプロジェクト作成
2. **API とサービス** → **Gmail API** を有効化
3. **OAuth 同意画面** → 外部 → アプリ名入力 → テストユーザーに自分の Gmail を追加
4. **認証情報** → **OAuth クライアント ID 作成** → タイプ：**デスクトップアプリ**
5. JSON をダウンロードし `credentials_gmail.json` にリネームしてプロジェクトに配置

**ステップ 2：依存パッケージのインストール**
```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2
```

**ステップ 3：初回認証（一度だけ）**
```bash
export MAIL_GMAIL_ADDRESS="your@gmail.com"
python3 email_daemon.py --mailbox gmail --auth
```
ターミナルに URL が表示されます → ローカルブラウザで開く → Google アカウントで認証 → 表示された code をターミナルに貼り付け。
`token_gmail.json` が自動保存され、以降は自動更新されます。

---

#### 📮 Outlook — OAuth 方式

**ステップ 1：Azure Portal でアプリ登録**
1. https://portal.azure.com/ → **Azure Active Directory** → **アプリの登録** → **新規登録**
2. サポートするアカウントの種類：**任意の組織ディレクトリのアカウントと個人の Microsoft アカウント**
3. リダイレクト URI（パブリック クライアント）：`https://login.microsoftonline.com/common/oauth2/nativeclient`
4. 登録後、**アプリケーション（クライアント）ID** をコピー

**ステップ 2：依存パッケージのインストール**
```bash
pip install msal
```

**ステップ 3：初回認証（デバイスコード方式）**
```bash
export MAIL_OUTLOOK_ADDRESS="your@outlook.com"
export OUTLOOK_CLIENT_ID="your-client-id"
python3 email_daemon.py --mailbox outlook --auth
```
ターミナルに**短いコード**と URL が表示されます → https://microsoft.com/devicelogin をブラウザで開く → コードを入力 → Microsoft アカウントでログインして認証。
`token_outlook.json` が自動保存されます。

---

### ⏰ 定期タスク（デフォルト）

対応タスク：`email` / `ai_job` / `weather` / `news` / `web_search` / `report` / `system_status`  
定時実行の結果はメール送信＋`reports/` にアーカイブ可能。

**環境変数（デフォルト）**
```bash
export WEATHER_API_KEY="your_weatherapi_key"
export NEWS_API_KEY="your_newsapi_key"
export BING_API_KEY="your_bing_search_key"
export TASK_DEFAULT_AI="openai"
```

**自動判定**
- キーワード：天気/ニュース/検索/レポート/AI
- 時間解析：`毎日 18:00`、`毎週月曜 10:00`、`今日/明日/今夜`
- マルチタスク：`;` または改行で分割

**例**
```
毎日 18:00 日報：天気 Tokyo、ニュース AI、検索 OpenAI 発表
```
```
毎週月曜 10:00 ニュース AI を要約、アーカイブ
```
```
毎日 08:00 天気 Tokyo
```
```
毎日 09:30 検索 深層学習 前線
```

### 📋 指示テンプレート

**方法 1：メールボックスにテンプレートを送信（推奨）**

以下のコマンドで7つのテンプレートをメールボックスの `MailMindHubテンプレート` フォルダに直接書き込み、メールクライアントから開いて編集して送信できます：

```bash
bash manage.sh push-templates
```

**方法 2：「テンプレート」と送信してテンプレート一覧を取得**

MailMindHub のメールボックスに本文が `テンプレート`（または `ヘルプ`）のメールを送ると、AI を呼ばず自動でテンプレート一覧を返信します。

### 🚀 使い方

```bash
bash manage.sh start             # バックグラウンドで起動
bash manage.sh stop              # 停止
bash manage.sh restart           # 再起動
bash manage.sh status            # 状態と最近のログを表示
bash manage.sh log               # リアルタイムログ
bash manage.sh push-templates    # 指示テンプレートをメールボックスに書き込む
bash manage.sh install           # systemd サービスとして登録
bash manage.sh uninstall         # systemd サービスを削除
```

### 🤖 対応 AI

> **💡 CLI と API、どちらを選ぶ？**
>
> - **CLI モード（シンプルに使いたい方に推奨）**：AIツール自身がローカルファイルの読み取り・Web 検索・コード実行などを自律的に行えます。MailMindHub はメール本文の指示を渡すだけで OK。設定が最小限で済みます。
> - **API モード（サーバー/クラウド運用向け）**：AI が受け取るのは送信したテキストのみ。天気・ニュース・Web 検索などのリアルタイムデータが必要な場合は、`.env` で `WEATHER_API_KEY`・`NEWS_API_KEY`・`WEB_SEARCH` 等を別途設定する必要があります。

#### CLI 方式

| パラメータ | 説明 | 必要環境 |
|-----------|------|---------|
| `claude` | Claude Code | Claude Code インストール済み |
| `codex` | Codex CLI | Codex CLI インストール済み |
| `gemini` | Gemini CLI | Gemini CLI インストール済み |
| `qwen` | Qwen CLI | Qwen CLI インストール済み |
| `copilot` | GitHub Copilot CLI | Copilot CLI インストール済み |

#### API 方式 - 国際モデル

| パラメータ | 説明 | 必要環境変数 |
|-----------|------|-------------|
| `anthropic` | Anthropic API | `ANTHROPIC_API_KEY` |
| `openai` | OpenAI API | `OPENAI_API_KEY` |
| `gemini-api` | Gemini API | `GEMINI_API_KEY` |
| `deepseek` | DeepSeek API | `DEEPSEEK_API_KEY` |
| `groq` | Groq 高速推論 | `GROQ_API_KEY` |
| `perplexity` | Perplexity 検索強化 | `PERPLEXITY_API_KEY` |
| `cohere` | Cohere エンタープライズ | `COHERE_API_KEY` |

#### API 方式 - 中国モデル

| パラメータ | 説明 | 必要環境変数 |
|-----------|------|-------------|
| `qwen-api` | 通義千問（アリババ） | `QWEN_API_KEY` |
| `moonshot` | 月之暗面 Kimi | `MOONSHOT_API_KEY` |
| `glm` | 智譜 AI（清華大学） | `GLM_API_KEY` |
| `spark` | iFLYTEK 星火 | `SPARK_API_KEY` |
| `ernie` | Baidu 文心一言 | `ERNIE_API_KEY` |
| `yi` | 零一万物 | `YI_API_KEY` |

### 💻 コーディング開発 指示テンプレート

**CLI AI + WORKSPACE_DIR** 構成向け（AI がプロジェクトファイルを直接読み書きできるため、コードの貼り付けは不要）。

> **基本構造**
> ```
> 【タスク種別】短いタイトル
>
> 目標：何をすべきか
> ファイル：対象ファイル/ディレクトリ
> 要件：スタイル・制約・注意点
> ```

---

**🆕 新機能開発**

```
【新機能】ログイン試行回数制限の実装

目標：auth/login.py のログインエンドポイントにレート制限を追加。
      同一 IP で5分以内に5回失敗したら10分ロック。
ファイル：auth/login.py、utils/cache.py
要件：
- 既存の Redis クライアントを使用（新規依存禁止）
- ロック中は 429 ステータスと残り待機時間を返す
- 対応するユニットテストを追加
```

**🐛 バグ修正**

```
【バグ】アバター画像アップロードで間欠的に 500 エラー

現象：2MB 超の画像アップロード時に確率でエラー発生、ログ：
  OSError: [Errno 28] No space left on device

ファイル：api/upload.py、core/storage.py
要件：
- 根本原因を特定
- アップロード前に一時ディレクトリの空き容量を確認
- 失敗時は 500 ではなく適切なエラーメッセージを返す
```

**🔍 コードレビュー**

```
【レビュー】payment/ モジュールのセキュリティ確認

ファイル：payment/
重点確認：
- SQL インジェクションリスク
- ログへの機密情報の平文出力
- 金額計算の浮動小数点精度問題
- 例外処理の網羅性
出力：問題点一覧を重大度順に列挙（コードは修正しない）
```

**♻️ リファクタリング**

```
【リファクタ】UserManager の god class を分割

ファイル：services/user_manager.py（約800行）
目標：責務別に分割：
- UserAuthService    ← 認証関連
- UserProfileService ← プロフィール関連
- UserNotifyService  ← 通知関連
要件：
- 外部インターフェースは変更しない（後方互換）
- 既存テストをすべて通過させる
- DB スキーマは変更しない
```

**🧪 テスト追加**

```
【テスト】utils/parser.py のユニットテスト補完

ファイル：utils/parser.py、tests/test_parser.py
要件：
- すべての public 関数をカバー
- 境界条件を重点的に：空入力・超長入力・特殊文字
- 既存の pytest フレームワーク・fixture スタイルに準拠
- カバレッジ目標 90% 以上
```

**⚡ パフォーマンス最適化**

```
【最適化】トップページ API のレスポンス改善

ファイル：api/home.py
背景：P99 約 800ms。get_recommended_items() で毎回全件 DB クエリが発生。
要件：
- メモリキャッシュ追加、TTL 5分
- キャッシュキーにユーザー ID を含める
- レスポンス形式は変更しない
- キャッシュ戦略をコメントで説明
```

**🗄️ DB スキーマ変更**

```
【DB】orders テーブルに論理削除を追加

ファイル：models/order.py、migrations/（Alembic）
目標：
- deleted_at カラム追加（nullable timestamp）
- 全クエリのデフォルトフィルタで削除済みを除外
- soft_delete() と restore() メソッドを追加
- migration ファイルを生成
注意：既存の物理削除ロジックに影響を与えない
```

**📡 API 設計**

```
【API】ファイル一括ダウンロードエンドポイント

ファイル：api/files.py、core/zip_helper.py（なければ新規作成）
要件：
- POST /api/files/batch-download、file_ids 配列を受け取り zip で返す
- 最大 50 ファイル、合計サイズ 100MB 以内
- 制限超過時は 400 と明確なエラーメッセージを返す
- OpenAPI コメントを追加
```

**🔐 セキュリティ強化**

```
【セキュリティ】API 認証の脆弱性を調査・修正

ファイル：middleware/auth.py、api/（全ディレクトリ）
タスク：
1. 認証なしでアクセス可能なエンドポイントを洗い出す
2. JWT 検証の alg=none 攻撃リスクを確認
3. 発見した問題を修正
4. 修正内容の一覧を返信に含める
```

**📖 ドキュメント補完**

```
【ドキュメント】core/ モジュールに docstring を追加

ファイル：core/（全ディレクトリ）
要件：
- 全 public 関数に Google スタイル docstring を追加
- 引数の型・戻り値・例外を含める
- 既存のものは変更しない（欠けているものだけ追加）
- ビジネスロジックには一切触れない
```

**🔗 依存ライブラリ更新**

```
【アップグレード】SQLAlchemy 1.4 → 2.0 対応

ファイル：requirements.txt、models/（全体）、database.py
背景：2.0 の Session API に破壊的変更あり。
要件：
- 非推奨 API をすべて更新
- 既存テストを全通過させる
- 主な変更点を返信に列挙
```

**🚨 緊急修正**

```
【緊急】本番エラー、即時修正

エラー：TypeError: 'NoneType' object is not subscriptable
場所：services/order.py、create_order() 関数
原因を特定して修正。他のロジックには触れないこと。
```

**🔄 マルチターン（前のメールに返信して継続）**

```
（前のメールに返信）

上の実装に問題があります：user_id が空のときクラッシュします。
validate_input() に null チェックを追加してください。他は変更不要。
```

---

**汎用修飾フレーズ**（任意のテンプレートの末尾に追加）：

| 目的 | 追加フレーズ |
|------|------------|
| 分析のみ（変更なし） | `出力：分析のみ、ファイルは変更しないこと` |
| 変更後にテスト実行 | `変更後に pytest tests/ を実行して通過を確認すること` |
| 最小限の変更 | `変更範囲は最小限に、余計な最適化は不要` |
| 変更理由を説明 | `返信本文に何をなぜ変更したかを記載すること` |
| 段階的に実行 | `まず第1ステップだけ実行し、確認後に続行` |

### 💡 効果的な使い方

長期利用すると、MailMindHub との交互メールが増えて受信ボックスが散らかりがちです。以下の方法で整理できます：

**1. 専用メールボックスを使う（最推奨）**

MailMindHub 専用のメールアカウントを作成し、すべての指示と返信をそこに集約。メインの受信ボックスへの影響をゼロにします。

**2. 定期タスクの結果はメール送信せずローカル保存**

指示メール内で出力先を指定するだけ：

```
毎朝8時にシステム状態レポートを生成、メールせずに reports フォルダに保存
```

AI が `"output": {"email": false, "archive": true}` のタスクを生成し、結果は `reports/` に書き込まれます。

**3. メールクライアントのフィルターで自動フォルダ振り分け**

Gmail/Outlook でフィルタールールを設定し、MailMindHub からの返信を専用フォルダへ自動移動。メインの受信ボックスには表示されません。

**4. 件名を統一してスレッドにまとめる**

同じ種類の指示は同じ件名を使うと、返信がひとつのスレッドに集約されます：

```
件名：【天気確認】     ← 天気関連の指示すべて
件名：【コード作業】   ← コード修正の指示すべて
件名：【日次レポート】 ← 定期タスクのスレッド
```

**5. `email_manage` で古い交互メールを定期クリーンアップ**

```
30日以上前の件名に【AI返信】が含まれるメールをすべてアーカイブ
```

---

<a name="english"></a>
# English

## MailMindHub — Chat with AI via Email

Send an email with your instructions, AI processes it and replies with the result. No app needed — your inbox is the interface.

```
Send email (instruction) → MailMindHub receives → AI processes → Reply via email
```

### ✨ Features

- **Multiple mailboxes**: 126, 163, QQ, Gmail (OAuth/App Password), Outlook (OAuth)
- **Multiple AI backends**: CLI (Claude Code, Codex, Gemini, Qwen) and API (Anthropic, OpenAI, Gemini API, Qwen API)
- **Whitelist security**: Per-mailbox whitelist supporting multiple addresses or domains
- **AI-generated subjects**: AI crafts a meaningful reply subject automatically
- **Service management**: One script for start, stop, restart, logs, and systemd install

### 📦 Installation

```bash
git clone https://github.com/yourname/MailMindHub.git
cd MailMindHub
python3 -m venv venv
source venv/bin/activate
pip install requests
```

### ⚙️ Configuration & Authentication

---

#### 📮 126 / 163 / QQ Mail (Auth Code)

1. Log in to webmail → **Settings** → **POP3/IMAP/SMTP** → Enable IMAP
2. Follow SMS verification to get an **auth code** (16 characters)
3. Set in `manage.sh`:

```bash
export MAIL_126_ADDRESS="your@126.com"
export MAIL_126_PASSWORD="your-auth-code"
export MAIL_126_ALLOWED="your@126.com"
```

---

#### 📮 Gmail — OAuth (Recommended)

**Step 1: Create a Google Cloud project**
1. Go to https://console.cloud.google.com/ → Create a project
2. **APIs & Services** → Enable **Gmail API**
3. **OAuth consent screen** → External → Fill in app name → Add your Gmail as test user
4. **Credentials** → **Create OAuth client ID** → Type: **Desktop app**
5. Download the JSON, rename it `credentials_gmail.json`, place it in the project directory

**Step 2: Install dependencies**
```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2
```

**Step 3: First-time authorization (once only)**
```bash
export MAIL_GMAIL_ADDRESS="your@gmail.com"
export MAIL_GMAIL_ALLOWED="your@gmail.com"
python3 email_daemon.py --mailbox gmail --auth
```
The terminal prints a URL → Open it in your local browser → Sign in with Google → Paste the code back into the terminal.
`token_gmail.json` is saved automatically and refreshed silently from then on.

---

#### 📮 Gmail — App Password (Simpler)

1. Enable Google 2-Step Verification
2. Go to https://myaccount.google.com/apppasswords → Generate an app password (16 chars)
3. In Gmail settings → Forwarding and POP/IMAP → Enable IMAP
4. In `email_daemon.py`, change gmail's `"auth": "oauth_google"` to `"auth": "password"`
5. Set in `manage.sh`:

```bash
export MAIL_GMAIL_ADDRESS="your@gmail.com"
export MAIL_GMAIL_PASSWORD="xxxx xxxx xxxx xxxx"
export MAIL_GMAIL_ALLOWED="your@gmail.com"
```

---

#### 📮 Outlook — OAuth

**Step 1: Register an app in Azure Portal**
1. Go to https://portal.azure.com/ → **Azure Active Directory** → **App registrations** → **New registration**
2. Supported account types: **Accounts in any organizational directory and personal Microsoft accounts**
3. Redirect URI (Public client/native): `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. After registration, copy the **Application (client) ID**

**Step 2: Install dependencies**
```bash
pip install msal
```

**Step 3: First-time authorization (device code flow)**
```bash
export MAIL_OUTLOOK_ADDRESS="your@outlook.com"
export OUTLOOK_CLIENT_ID="your-client-id"
export MAIL_OUTLOOK_ALLOWED="your@outlook.com"
python3 email_daemon.py --mailbox outlook --auth
```
The terminal shows a **short code** and a URL → Open https://microsoft.com/devicelogin in your browser → Enter the code → Sign in with your Microsoft account.
`token_outlook.json` is saved and refreshed automatically.

---

### ⏰ Scheduled Tasks (Default)

Supported types: `email` / `ai_job` / `weather` / `news` / `web_search` / `report` / `system_status`  
Results can be emailed and archived to `reports/`.

**Env (default)**
```bash
export WEATHER_API_KEY="your_weatherapi_key"
export NEWS_API_KEY="your_newsapi_key"
export BING_API_KEY="your_bing_search_key"
export TASK_DEFAULT_AI="openai"
```

**Auto-detect**
- Keywords: weather/news/search/report/AI
- Time parsing: `every day 18:00`, `every Monday 10:00`, `today/tomorrow/tonight`
- Multi-task: split by `;` or newline

**Example**
```
Every day 18:00: report with weather Tokyo, AI news, and web search OpenAI event.
```
```
Every 2 hours: news AI summary, archive
```
```
Every day 08:00 weather Tokyo
```
```
Every day 09:30 web search deep learning trends
```

### 📋 Instruction Templates

**Option 1: Push templates to your mailbox (recommended)**

Run the command below to write 7 ready-to-use templates directly into a `MailMindHub Templates` folder in your mailbox. Open any template, fill in the placeholders, and send:

```bash
bash manage.sh push-templates
```

**Option 2: Send "help" to get the template list**

Send an email to your MailMindHub mailbox with just `help` (or `templates`) as the body. The system replies with all templates instantly — no AI call needed.

### 🚀 Usage

```bash
bash manage.sh start             # Start in background
bash manage.sh stop              # Stop
bash manage.sh restart           # Restart
bash manage.sh status            # View status and recent logs
bash manage.sh log               # Tail live logs
bash manage.sh push-templates    # Write instruction templates to mailbox folder
bash manage.sh install           # Install as systemd service (auto-start on boot)
bash manage.sh uninstall         # Remove systemd service
```

Once running, send an email to your configured mailbox with your instruction as the body. You'll receive an AI reply within 60 seconds.

### 🤖 Supported AI Backends

> **💡 CLI vs API — which should I choose?**
>
> - **CLI mode (recommended for simple use)**: The AI tool itself can read local files, browse the web, execute code, and gather context autonomously. MailMindHub just forwards your email instruction — minimal configuration needed.
> - **API mode (for server/cloud deployment)**: The AI only sees what you explicitly send it. To provide real-time data like weather, news, or web search results, you must configure the corresponding data sources in `.env` (`WEATHER_API_KEY`, `NEWS_API_KEY`, `WEB_SEARCH`, etc.).

#### CLI Backends

| Name | Required |
|------|---------|
| `claude` | Claude Code installed |
| `codex` | Codex CLI installed |
| `gemini` | Gemini CLI installed |
| `qwen` | Qwen CLI installed |
| `copilot` | GitHub Copilot CLI installed |

#### API Backends - International Models

| Name | Required |
|------|---------|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `gemini-api` | `GEMINI_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `perplexity` | `PERPLEXITY_API_KEY` |
| `cohere` | `COHERE_API_KEY` |

#### API Backends - China Models

| Name | Provider | Required |
|------|----------|---------|
| `qwen-api` | Alibaba Cloud | `QWEN_API_KEY` |
| `moonshot` | Moonshot AI (Kimi) | `MOONSHOT_API_KEY` |
| `glm` | Zhipu AI | `GLM_API_KEY` |
| `spark` | iFLYTEK | `SPARK_API_KEY` |
| `ernie` | Baidu | `ERNIE_API_KEY` |
| `yi` | 01.AI | `YI_API_KEY` |

### 💻 Coding Development Templates

For **CLI AI + WORKSPACE_DIR** setups where the AI can read and write project files directly — no need to paste code in the email.

> **General structure**
> ```
> [Task Type] Short title
>
> Goal: What needs to be done
> Files: Which files/directories are involved
> Requirements: Style, constraints, and notes
> ```

---

**🆕 New Feature**

```
[Feature] Implement login rate limiting

Goal: Add rate limiting to the login endpoint in auth/login.py.
      Lock the IP for 10 minutes after 5 failures within 5 minutes.
Files: auth/login.py, utils/cache.py
Requirements:
- Use the existing Redis client, no new dependencies
- Return 429 status with remaining wait time when locked
- Add corresponding unit tests
```

**🐛 Bug Fix**

```
[Bug] Intermittent 500 error on avatar upload

Symptom: Images larger than 2MB fail with this error in the logs:
  OSError: [Errno 28] No space left on device

Files: api/upload.py, core/storage.py
Requirements:
- Identify the root cause
- Check temp directory space before uploading
- Return a friendly error message instead of 500
```

**🔍 Code Review**

```
[Review] Security audit of the payment/ module

Files: payment/
Focus on:
- SQL injection risks
- Sensitive data logged in plaintext
- Floating-point precision in monetary calculations
- Completeness of exception handling
Output: List issues sorted by severity. Do not modify code.
```

**♻️ Refactoring**

```
[Refactor] Split UserManager god class

Files: services/user_manager.py (~800 lines)
Goal: Split by responsibility:
- UserAuthService    ← authentication
- UserProfileService ← profile management
- UserNotifyService  ← notifications
Requirements:
- Keep external interfaces unchanged (backward compatible)
- All existing tests must still pass
- Do not alter the DB schema
```

**🧪 Add Tests**

```
[Tests] Add unit tests for utils/parser.py

Files: utils/parser.py, tests/test_parser.py
Requirements:
- Cover all public functions
- Focus on edge cases: empty input, very long input, special characters
- Follow existing pytest framework and fixture style
- Target 90%+ coverage
```

**⚡ Performance**

```
[Performance] Improve homepage API response time

Files: api/home.py
Context: P99 ~800ms. Bottleneck is get_recommended_items() — full DB scan on every request.
Requirements:
- Add in-memory cache with 5-minute TTL
- Include user ID in cache key
- Do not change the response format
- Comment the caching strategy
```

**🗄️ Database Change**

```
[DB] Add soft delete to the orders table

Files: models/order.py, migrations/ (Alembic)
Goal:
- Add deleted_at column (nullable timestamp)
- Default all queries to filter out deleted records
- Add soft_delete() and restore() methods
- Generate the migration file
Note: Do not affect existing hard-delete logic
```

**📡 API Design**

```
[API] Batch file download endpoint

Files: api/files.py, core/zip_helper.py (create if missing)
Requirements:
- POST /api/files/batch-download, accept file_ids array, return zip
- Max 50 files, total size under 100MB
- Return 400 with clear error message when limits are exceeded
- Add OpenAPI annotations
```

**🔐 Security Hardening**

```
[Security] Audit and fix API authentication issues

Files: middleware/auth.py, api/ (all)
Tasks:
1. Find all endpoints accessible without authentication
2. Check JWT validation for alg=none attack vulnerability
3. Fix discovered issues
4. Include a fix summary in the reply
```

**📖 Documentation**

```
[Docs] Add docstrings to the core/ module

Files: core/ (all)
Requirements:
- Add Google-style docstrings to all public functions
- Include parameter types, return values, and exceptions
- Only add missing ones, do not modify existing
- Do not touch any business logic
```

**🔗 Dependency Upgrade**

```
[Upgrade] SQLAlchemy 1.4 → 2.0

Files: requirements.txt, models/ (all), database.py
Context: 2.0 has breaking changes to the Session API.
Requirements:
- Update all deprecated API usage
- All existing tests must still pass
- List main changes in the reply
```

**🚨 Urgent Fix**

```
[Urgent] Production error, fix immediately

Error: TypeError: 'NoneType' object is not subscriptable
Location: services/order.py, create_order() function
Find the cause and fix it. Do not touch any other logic.
```

**🔄 Multi-turn (reply to continue conversation)**

```
(Reply to previous email)

The implementation above has a problem: it crashes when user_id is empty.
Please add a null check in validate_input(). No other changes.
```

---

**Modifier phrases** (append to any template):

| Purpose | Phrase to add |
|---------|--------------|
| Analyze only, no changes | `Output: analysis only, do not modify any files` |
| Run tests after changes | `After changes, run pytest tests/ to confirm they pass` |
| Minimal changes | `Keep changes minimal, no extra optimization` |
| Explain changes | `Include what and why you changed in the reply body` |
| Step by step | `Do only step 1 first; wait for my confirmation before continuing` |

### 🔒 Security Tips

- Always set `ALLOWED` whitelist to your own email to prevent abuse
- `credentials_gmail.json` and `token_*.json` are in `.gitignore` and won't be committed
- `manage.sh` contains credentials — review before pushing, or add to `.gitignore`

### 🛡️ Workspace (Optional)

Limit AI file operations to a specific directory for enhanced security:

```bash
# In .env
WORKSPACE_DIR="./workspace"
```

When set, all archive outputs (e.g., `reports/`) will be restricted to this directory, preventing path traversal attacks. Leave empty for no restrictions (backward compatible).

### 💡 Tips for Effective Use

Over time, interaction threads with MailMindHub can clutter your inbox. Here are strategies to stay organized:

**1. Use a dedicated mailbox (recommended)**

Create a separate email account exclusively for MailMindHub. All instructions and replies live there, leaving your main inbox untouched.

**2. Archive scheduled task results locally — skip email delivery**

Specify output destination in your instruction:

```
Every morning at 8am generate a system status report, save to reports folder, do not send email
```

The AI will produce a task with `"output": {"email": false, "archive": true}`, writing results to `reports/` only.

**3. Use email client filters for automatic folder routing**

Set up a filter in Gmail/Outlook to auto-move MailMindHub replies into a dedicated folder, keeping them out of the main inbox.

**4. Use consistent subject lines to keep threads grouped**

Same-type instructions under the same subject line automatically consolidate into a single thread:

```
Subject: [Weather]       ← all weather queries
Subject: [Code Task]     ← all code-related instructions
Subject: [Daily Report]  ← scheduled task thread
```

**5. Schedule periodic cleanup with `email_manage`**

```
Archive all emails older than 30 days whose subject contains [AI Reply]
```

---

<a name="한국어"></a>
# 한국어

## MailMindHub — 이메일로 AI와 대화하기

이메일로 지시를 보내면 AI가 처리하여 결과를 이메일로 회신합니다. 별도의 앱 없이 이메일이 인터페이스입니다.

```
이메일 발송（지시）→ MailMindHub 수신 → AI 처리 → 이메일로 회신
```

### ✨ 주요 기능

- **다중 메일함 지원**：126、163、QQ、Gmail（OAuth/앱 비밀번호）、Outlook（OAuth）
- **다중 AI 지원**：CLI 방식（Claude Code、Codex、Gemini、Qwen）、API 방식（Anthropic、OpenAI、Gemini API、Qwen API）
- **화이트리스트 보안**：메일함별 독립 설정, 여러 주소·도메인 지원
- **AI 자동 제목 생성**：AI가 회신 내용에 맞는 제목을 자동 생성
- **서비스 관리**：하나의 스크립트로 시작·정지·재시작·로그·systemd 등록

### 📦 설치

```bash
git clone https://github.com/yourname/MailMindHub.git
cd MailMindHub
python3 -m venv venv
source venv/bin/activate
pip install requests
```

### ⚙️ 설정 및 인증

---

#### 📮 126 / 163 / QQ 메일（인증 코드 방식）

1. 웹메일 로그인 → **설정** → **POP3/IMAP/SMTP** → IMAP 서비스 활성화
2. SMS 인증으로 **인증 코드**（16자리）취득
3. `manage.sh` 에 입력：

```bash
export MAIL_126_ADDRESS="your@126.com"
export MAIL_126_PASSWORD="your-auth-code"
export MAIL_126_ALLOWED="your@126.com"
```

---

#### 📮 Gmail — OAuth 방식（권장）

**1단계：Google Cloud 프로젝트 생성**
1. https://console.cloud.google.com/ → 새 프로젝트 생성
2. **API 및 서비스** → **Gmail API** 활성화
3. **OAuth 동의 화면** → 외부 → 앱 이름 입력 → 테스트 사용자에 본인 Gmail 추가
4. **사용자 인증 정보** → **OAuth 클라이언트 ID 만들기** → 유형：**데스크톱 앱**
5. JSON 다운로드 후 `credentials_gmail.json` 으로 이름 변경, 프로젝트 디렉토리에 배치

**2단계：의존성 설치**
```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2
```

**3단계：최초 인증（1회만）**
```bash
export MAIL_GMAIL_ADDRESS="your@gmail.com"
export MAIL_GMAIL_ALLOWED="your@gmail.com"
python3 email_daemon.py --mailbox gmail --auth
```
터미널에 URL이 출력됩니다 → 로컬 브라우저에서 열기 → Google 계정으로 로그인 → 표시된 code를 터미널에 붙여넣기.
`token_gmail.json` 이 자동 저장되며 이후 자동 갱신됩니다.

---

#### 📮 Outlook — OAuth 방식

**1단계：Azure Portal에서 앱 등록**
1. https://portal.azure.com/ → **Azure Active Directory** → **앱 등록** → **새 등록**
2. 지원되는 계정 유형：**모든 조직 디렉터리의 계정 및 개인 Microsoft 계정**
3. 리디렉션 URI（퍼블릭 클라이언트）：`https://login.microsoftonline.com/common/oauth2/nativeclient`
4. 등록 후 **애플리케이션（클라이언트）ID** 복사

**2단계：의존성 설치**
```bash
pip install msal
```

**3단계：최초 인증（장치 코드 방식）**
```bash
export MAIL_OUTLOOK_ADDRESS="your@outlook.com"
export OUTLOOK_CLIENT_ID="your-client-id"
export MAIL_OUTLOOK_ALLOWED="your@outlook.com"
python3 email_daemon.py --mailbox outlook --auth
```
터미널에 **짧은 코드**와 URL이 표시됩니다 → https://microsoft.com/devicelogin 을 브라우저에서 열기 → 코드 입력 → Microsoft 계정으로 로그인하여 인증.
`token_outlook.json` 이 자동 저장됩니다.

---

### ⏰ 정기 작업（기본）

지원 유형: `email` / `ai_job` / `weather` / `news` / `web_search` / `report` / `system_status`  
결과는 이메일 발송 및 `reports/` 아카이브 가능.

**환경 변수（기본）**
```bash
export WEATHER_API_KEY="your_weatherapi_key"
export NEWS_API_KEY="your_newsapi_key"
export BING_API_KEY="your_bing_search_key"
export TASK_DEFAULT_AI="openai"
```

**자동 인식**
- 키워드: 날씨/뉴스/검색/리포트/AI
- 시간 해석: `매일 18:00`, `매주 월요일 10:00`, `오늘/내일/오늘 밤`
- 멀티 태스크: `;` 또는 줄바꿈으로 분리

**예시**
```
매일 18:00 리포트: 날씨 Tokyo, AI 뉴스, 웹 검색 OpenAI 발표
```
```
매주 월요일 10:00 뉴스 AI 요약, 아카이브
```
```
매일 08:00 날씨 Tokyo
```
```
매일 09:30 검색 딥러닝 트렌드
```

### 📋 지시 템플릿

**방법 1：메일함에 템플릿 푸시（권장）**

아래 명령으로 7개 템플릿을 메일함의 `MailMindHub Templates` 폴더에 직접 저장합니다. 메일 클라이언트에서 열어 편집 후 전송하면 됩니다：

```bash
bash manage.sh push-templates
```

**방법 2：「help」 전송으로 템플릿 목록 받기**

MailMindHub 메일함에 본문이 `help`（또는 `templates`）인 이메일을 보내면 AI 호출 없이 즉시 템플릿 목록을 회신합니다.

### 🚀 사용법

```bash
bash manage.sh start             # 백그라운드 시작
bash manage.sh stop              # 정지
bash manage.sh restart           # 재시작
bash manage.sh status            # 상태 및 최근 로그 확인
bash manage.sh log               # 실시간 로그 보기
bash manage.sh push-templates    # 지시 템플릿을 메일함 폴더에 저장
bash manage.sh install           # systemd 서비스로 등록（부팅 시 자동 시작）
bash manage.sh uninstall         # systemd 서비스 제거
```

시작 후 설정된 메일함으로 이메일을 보내고 본문에 지시를 작성하면 60초 이내에 AI 회신을 받을 수 있습니다.

### 🤖 지원 AI

#### CLI 방식

| 파라미터 | 필요 조건 |
|---------|---------|
| `claude` | Claude Code 설치 |
| `codex` | Codex CLI 설치 |
| `gemini` | Gemini CLI 설치 |
| `qwen` | Qwen CLI 설치 |
| `copilot` | GitHub Copilot CLI 설치 |

#### API 방식 - 국제 모델

| 파라미터 | 필요 조건 |
|---------|---------|
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `gemini-api` | `GEMINI_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `perplexity` | `PERPLEXITY_API_KEY` |
| `cohere` | `COHERE_API_KEY` |

#### API 방식 - 중국 모델

| 파라미터 | 제공업체 | 필요 조건 |
|---------|---------|---------|
| `qwen-api` | 알리바바 | `QWEN_API_KEY` |
| `moonshot` | 월지암면 Kimi | `MOONSHOT_API_KEY` |
| `glm` | 지푸 AI | `GLM_API_KEY` |
| `spark` | iFLYTEK | `SPARK_API_KEY` |
| `ernie` | 바이두 | `ERNIE_API_KEY` |
| `yi` | 01.AI | `YI_API_KEY` |

### 💻 코딩 개발 지시 템플릿

**CLI AI + WORKSPACE_DIR** 구성용（AI가 프로젝트 파일을 직접 읽고 쓸 수 있으므로 코드 붙여넣기 불필요）。

> **기본 구조**
> ```
> 【작업 유형】짧은 제목
>
> 목표：무엇을 해야 하는지
> 파일：관련 파일/디렉토리
> 요구사항：스타일·제약·주의사항
> ```

---

**🆕 신규 기능 개발**

```
【신기능】로그인 횟수 제한 구현

목표：auth/login.py 의 로그인 엔드포인트에 레이트 리밋 추가.
      동일 IP에서 5분 내 5회 실패 시 10분 잠금.
파일：auth/login.py、utils/cache.py
요구사항：
- 기존 Redis 클라이언트 사용（신규 의존성 금지）
- 잠금 중에는 429 상태코드와 남은 대기 시간 반환
- 대응 유닛 테스트 추가
```

**🐛 버그 수정**

```
【버그】아바타 업로드 시 간헐적 500 오류

증상：2MB 초과 이미지 업로드 시 확률적으로 오류 발생, 로그：
  OSError: [Errno 28] No space left on device

파일：api/upload.py、core/storage.py
요구사항：
- 근본 원인 파악
- 업로드 전 임시 디렉토리 용량 확인
- 실패 시 500 대신 친절한 오류 메시지 반환
```

**🔍 코드 리뷰**

```
【리뷰】payment/ 모듈 보안 점검

파일：payment/
중점 확인：
- SQL 인젝션 위험
- 민감 정보 로그 평문 출력
- 금액 계산 부동소수점 정밀도 문제
- 예외 처리 완전성
출력：문제 목록을 심각도 순으로 나열（코드 수정 금지）
```

**♻️ 리팩토링**

```
【리팩토링】UserManager god class 분리

파일：services/user_manager.py（약 800줄）
목표：책임별로 분리：
- UserAuthService    ← 인증 관련
- UserProfileService ← 프로필 관련
- UserNotifyService  ← 알림 관련
요구사항：
- 외부 인터페이스 변경 없음（하위 호환 유지）
- 기존 테스트 전부 통과
- DB 스키마 변경 금지
```

**🧪 테스트 추가**

```
【테스트】utils/parser.py 유닛 테스트 보완

파일：utils/parser.py、tests/test_parser.py
요구사항：
- 모든 public 함수 커버
- 경계 조건 집중：빈 입력·초장문·특수문자
- 기존 pytest 프레임워크·fixture 스타일 준수
- 커버리지 목표 90% 이상
```

**⚡ 성능 최적화**

```
【성능】홈페이지 API 응답 시간 개선

파일：api/home.py
배경：P99 약 800ms. get_recommended_items() 에서 매번 전체 DB 쿼리 발생.
요구사항：
- 메모리 캐시 추가, TTL 5분
- 캐시 키에 사용자 ID 포함
- 응답 형식 변경 없음
- 캐싱 전략을 주석으로 설명
```

**🗄️ DB 변경**

```
【DB】orders 테이블에 소프트 삭제 추가

파일：models/order.py、migrations/（Alembic）
목표：
- deleted_at 컬럼 추가（nullable timestamp）
- 모든 쿼리 기본적으로 삭제된 레코드 필터링
- soft_delete()、restore() 메서드 추가
- migration 파일 생성
주의：기존 하드 삭제 로직에 영향 없을 것
```

**🚨 긴급 수정**

```
【긴급】운영 오류, 즉시 수정

오류：TypeError: 'NoneType' object is not subscriptable
위치：services/order.py、create_order() 함수
원인을 파악하고 수정하세요. 다른 로직은 건드리지 마세요.
```

**🔄 멀티턴（이전 메일에 답장해서 계속）**

```
（이전 메일에 답장）

위 구현에 문제가 있습니다：user_id가 비어 있을 때 크래시가 납니다.
validate_input()에 null 체크를 추가해 주세요. 다른 변경은 없습니다.
```

---

**공통 수식어**（임의 템플릿 끝에 추가）：

| 목적 | 추가 문구 |
|------|---------|
| 분석만（변경 없음） | `출력：분석만, 어떤 파일도 수정하지 말 것` |
| 변경 후 테스트 실행 | `변경 후 pytest tests/ 실행하여 통과 확인` |
| 최소한의 변경 | `변경 범위는 최소한으로, 추가 최적화 불필요` |
| 변경 이유 설명 | `답장 본문에 무엇을 왜 변경했는지 기재` |
| 단계적 실행 | `1단계만 먼저 실행하고, 확인 후 계속` |

### 🔒 보안 권장 사항

- `ALLOWED` 화이트리스트를 반드시 본인 이메일로 설정하여 무단 사용 방지
- `credentials_gmail.json`, `token_*.json` 은 `.gitignore` 에 포함되어 커밋되지 않음
- `manage.sh` 에 자격 증명이 포함되어 있으므로 푸시 전 확인 또는 `.gitignore` 에 추가

### 💡 효과적인 사용 팁

장기 사용 시 MailMindHub와의 교신 메일이 쌓여 받은편지함이 복잡해질 수 있습니다. 다음 방법으로 정리할 수 있습니다:

**1. 전용 메일함 사용（추천）**

MailMindHub 전용 이메일 계정을 만들어 모든 지시와 답변을 그곳에 집중. 메인 받은편지함에 전혀 영향을 주지 않습니다.

**2. 정기 태스크 결과는 이메일 발송 없이 로컬 저장**

지시 메일에 출력 방식 명시：

```
매일 아침 8시 시스템 상태 보고서 생성, 이메일 발송 없이 reports 폴더에 저장
```

AI가 `"output": {"email": false, "archive": true}` 태스크를 생성하여 결과를 `reports/` 에만 기록합니다.

**3. 메일 클라이언트 필터로 자동 폴더 분류**

Gmail/Outlook에서 필터 규칙을 설정해 MailMindHub의 답장을 전용 폴더로 자동 이동. 메인 받은편지함에 표시되지 않습니다.

**4. 제목 통일로 스레드 집약**

같은 종류의 지시에 동일한 제목을 사용하면 모든 관련 답장이 하나의 스레드로 묶입니다:

```
제목: [날씨 확인]     ← 날씨 관련 지시 전체
제목: [코드 작업]     ← 코드 수정 지시 전체
제목: [일일 보고서]   ← 정기 태스크 스레드
```

**5. `email_manage`로 오래된 교신 메일 정기 정리**

```
30일 이상된 제목에 [AI답변]이 포함된 메일을 모두 아카이브
```

---

## License

MIT License — feel free to use, modify, and distribute.

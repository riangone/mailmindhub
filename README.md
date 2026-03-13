# MailMind

> **Send an email, get an AI response. That simple.**

**[中文](#中文)** | **[日本語](#日本語)** | **[English](#english)** | **[한국어](#한국어)**

---

<a name="中文"></a>
# 中文

## MailMind — 通过邮件与 AI 对话

通过发送邮件向 AI 下达指令，AI 处理后自动将结果回复到你的邮箱。无需打开任何 App，邮件即是界面。

```
你发邮件（指令）→ MailMind 接收 → AI 处理 → 邮件回复结果
```

### ✨ 功能特性

- **多邮箱支持**：126、163、QQ、Gmail（OAuth/应用密码）、Outlook（OAuth）
- **多 AI 支持**：Claude Code、Codex、Gemini、通义千问（CLI）；Anthropic、OpenAI、Gemini API、通义千问 API（API）
- **白名单安全**：每个邮箱独立配置白名单，支持多个地址或域名
- **AI 自动拟标题**：AI 根据回复内容自动生成邮件标题
- **服务化管理**：一个脚本完成启动、停止、重启、日志、系统服务安装
- **定时任务扩展**：可定时执行 AI 任务、天气、新闻、网页检索与日报汇总（支持归档）

### 📦 安装

```bash
git clone https://github.com/yourname/MailMind.git
cd MailMind
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

新增任务类型支持：`email` / `ai_job` / `weather` / `news` / `web_search` / `report`。  
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

### 🧩 示例指令模板

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

### ⚙️ 自动识别说明

当用户未显式给出 `task_type` 时，系统会根据关键词自动判断任务类型与定时参数：
- `天气` / `weather` → `weather`
- `新闻` / `news` → `news`
- `检索` / `搜索` / `网页` / `search` → `web_search`
- `日报` / `周报` / `月报` / `report` → `report`
- `AI` / `分析` / `总结` / `翻译` / `生成` → `ai_job`
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
bash manage.sh start      # 后台启动
bash manage.sh stop       # 停止
bash manage.sh restart    # 重启
bash manage.sh status     # 查看状态和最近日志
bash manage.sh log        # 实时查看日志
bash manage.sh install    # 安装为 systemd 服务（开机自启）
bash manage.sh uninstall  # 卸载 systemd 服务
```

启动后，给配置的邮箱发一封邮件，正文写指令，60秒内收到 AI 回复。

### 🤖 支持的 AI

| 参数名 | 类型 | 说明 | 所需环境变量 |
|--------|------|------|------------|
| `claude` | CLI | Claude Code | 需安装 Claude Code |
| `codex` | CLI | OpenAI Codex CLI | 需安装 Codex CLI |
| `gemini` | CLI | Gemini CLI | 需安装 Gemini CLI |
| `qwen` | CLI | 通义千问 CLI | 需安装 Qwen CLI |
| `anthropic` | API | Anthropic API | `ANTHROPIC_API_KEY` |
| `openai` | API | OpenAI API | `OPENAI_API_KEY` |
| `gemini-api` | API | Gemini API | `GEMINI_API_KEY` |
| `qwen-api` | API | 通义千问 API | `QWEN_API_KEY` |

### 🔒 安全建议

- 设置 `ALLOWED` 白名单为自己的邮箱，防止陌生人触发 AI
- `credentials_gmail.json`、`token_*.json` 已加入 `.gitignore`，不会被提交
- `manage.sh` 包含密码，推送前检查或加入 `.gitignore`

---

<a name="日本語"></a>
# 日本語

## MailMind — メールで AI と対話する

メールで指示を送ると、AI が処理して結果をメールで返信します。アプリ不要、メールがインターフェースです。

```
メール送信（指示）→ MailMind 受信 → AI 処理 → メールで返信
```

### ✨ 主な機能

- **複数メールボックス対応**：126、163、QQ、Gmail（OAuth/アプリパスワード）、Outlook（OAuth）
- **複数 AI 対応**：CLI 方式（Claude Code、Codex、Gemini、Qwen）、API 方式（Anthropic、OpenAI、Gemini API、Qwen API）
- **ホワイトリスト機能**：メールボックスごとに独立設定、複数アドレス・ドメイン対応
- **AI による件名自動生成**：返信内容に基づき AI が件名を自動作成
- **サービス管理**：1 スクリプトで起動・停止・再起動・ログ・systemd 登録

### 📦 インストール

```bash
git clone https://github.com/yourname/MailMind.git
cd MailMind
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

対応タスク：`email` / `ai_job` / `weather` / `news` / `web_search` / `report`  
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

### 🚀 使い方

```bash
bash manage.sh start      # バックグラウンドで起動
bash manage.sh stop       # 停止
bash manage.sh restart    # 再起動
bash manage.sh status     # 状態と最近のログを表示
bash manage.sh log        # リアルタイムログ
bash manage.sh install    # systemd サービスとして登録
bash manage.sh uninstall  # systemd サービスを削除
```

### 🤖 対応 AI

| パラメータ | タイプ | 必要な環境変数 |
|-----------|--------|-------------|
| `claude` | CLI | Claude Code インストール済み |
| `codex` | CLI | Codex CLI インストール済み |
| `gemini` | CLI | Gemini CLI インストール済み |
| `qwen` | CLI | Qwen CLI インストール済み |
| `anthropic` | API | `ANTHROPIC_API_KEY` |
| `openai` | API | `OPENAI_API_KEY` |
| `gemini-api` | API | `GEMINI_API_KEY` |
| `qwen-api` | API | `QWEN_API_KEY` |

---

<a name="english"></a>
# English

## MailMind — Chat with AI via Email

Send an email with your instructions, AI processes it and replies with the result. No app needed — your inbox is the interface.

```
Send email (instruction) → MailMind receives → AI processes → Reply via email
```

### ✨ Features

- **Multiple mailboxes**: 126, 163, QQ, Gmail (OAuth/App Password), Outlook (OAuth)
- **Multiple AI backends**: CLI (Claude Code, Codex, Gemini, Qwen) and API (Anthropic, OpenAI, Gemini API, Qwen API)
- **Whitelist security**: Per-mailbox whitelist supporting multiple addresses or domains
- **AI-generated subjects**: AI crafts a meaningful reply subject automatically
- **Service management**: One script for start, stop, restart, logs, and systemd install

### 📦 Installation

```bash
git clone https://github.com/yourname/MailMind.git
cd MailMind
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

Supported types: `email` / `ai_job` / `weather` / `news` / `web_search` / `report`  
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

### 🚀 Usage

```bash
bash manage.sh start      # Start in background
bash manage.sh stop       # Stop
bash manage.sh restart    # Restart
bash manage.sh status     # View status and recent logs
bash manage.sh log        # Tail live logs
bash manage.sh install    # Install as systemd service (auto-start on boot)
bash manage.sh uninstall  # Remove systemd service
```

Once running, send an email to your configured mailbox with your instruction as the body. You'll receive an AI reply within 60 seconds.

### 🤖 Supported AI Backends

| Name | Type | Required |
|------|------|---------|
| `claude` | CLI | Claude Code installed |
| `codex` | CLI | Codex CLI installed |
| `gemini` | CLI | Gemini CLI installed |
| `qwen` | CLI | Qwen CLI installed |
| `anthropic` | API | `ANTHROPIC_API_KEY` |
| `openai` | API | `OPENAI_API_KEY` |
| `gemini-api` | API | `GEMINI_API_KEY` |
| `qwen-api` | API | `QWEN_API_KEY` |

### 🔒 Security Tips

- Always set `ALLOWED` whitelist to your own email to prevent abuse
- `credentials_gmail.json` and `token_*.json` are in `.gitignore` and won't be committed
- `manage.sh` contains credentials — review before pushing, or add to `.gitignore`

---

<a name="한국어"></a>
# 한국어

## MailMind — 이메일로 AI와 대화하기

이메일로 지시를 보내면 AI가 처리하여 결과를 이메일로 회신합니다. 별도의 앱 없이 이메일이 인터페이스입니다.

```
이메일 발송（지시）→ MailMind 수신 → AI 처리 → 이메일로 회신
```

### ✨ 주요 기능

- **다중 메일함 지원**：126、163、QQ、Gmail（OAuth/앱 비밀번호）、Outlook（OAuth）
- **다중 AI 지원**：CLI 방식（Claude Code、Codex、Gemini、Qwen）、API 방식（Anthropic、OpenAI、Gemini API、Qwen API）
- **화이트리스트 보안**：메일함별 독립 설정, 여러 주소·도메인 지원
- **AI 자동 제목 생성**：AI가 회신 내용에 맞는 제목을 자동 생성
- **서비스 관리**：하나의 스크립트로 시작·정지·재시작·로그·systemd 등록

### 📦 설치

```bash
git clone https://github.com/yourname/MailMind.git
cd MailMind
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

지원 유형: `email` / `ai_job` / `weather` / `news` / `web_search` / `report`  
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

### 🚀 사용법

```bash
bash manage.sh start      # 백그라운드 시작
bash manage.sh stop       # 정지
bash manage.sh restart    # 재시작
bash manage.sh status     # 상태 및 최근 로그 확인
bash manage.sh log        # 실시간 로그 보기
bash manage.sh install    # systemd 서비스로 등록（부팅 시 자동 시작）
bash manage.sh uninstall  # systemd 서비스 제거
```

시작 후 설정된 메일함으로 이메일을 보내고 본문에 지시를 작성하면 60초 이내에 AI 회신을 받을 수 있습니다.

### 🤖 지원 AI

| 파라미터 | 유형 | 필요 조건 |
|---------|------|---------|
| `claude` | CLI | Claude Code 설치 |
| `codex` | CLI | Codex CLI 설치 |
| `gemini` | CLI | Gemini CLI 설치 |
| `qwen` | CLI | Qwen CLI 설치 |
| `anthropic` | API | `ANTHROPIC_API_KEY` |
| `openai` | API | `OPENAI_API_KEY` |
| `gemini-api` | API | `GEMINI_API_KEY` |
| `qwen-api` | API | `QWEN_API_KEY` |

### 🔒 보안 권장 사항

- `ALLOWED` 화이트리스트를 반드시 본인 이메일로 설정하여 무단 사용 방지
- `credentials_gmail.json`, `token_*.json` 은 `.gitignore` 에 포함되어 커밋되지 않음
- `manage.sh` 에 자격 증명이 포함되어 있으므로 푸시 전 확인 또는 `.gitignore` 에 추가

---

## License

MIT License — feel free to use, modify, and distribute.

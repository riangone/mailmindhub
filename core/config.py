import os
import shutil

# ═══════════════════════════════════════════════════════════════
#  邮箱配置
# ═══════════════════════════════════════════════════════════════

MAILBOXES = {
    "126": {
        "address":         os.environ.get("MAIL_126_ADDRESS", ""),
        "password":        os.environ.get("MAIL_126_PASSWORD", ""),
        "imap_server":     "imap.126.com",
        "imap_port":       993,
        "smtp_server":     "smtp.126.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         True,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_126_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_126_SPAM_FOLDER", "Junk"),
    },
    "163": {
        "address":         os.environ.get("MAIL_163_ADDRESS", ""),
        "password":        os.environ.get("MAIL_163_PASSWORD", ""),
        "imap_server":     "imap.163.com",
        "imap_port":       993,
        "smtp_server":     "smtp.163.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         True,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_163_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_163_SPAM_FOLDER", "Junk"),
    },
    "qq": {
        "address":         os.environ.get("MAIL_QQ_ADDRESS", ""),
        "password":        os.environ.get("MAIL_QQ_PASSWORD", ""),
        "imap_server":     "imap.qq.com",
        "imap_port":       993,
        "smtp_server":     "smtp.qq.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_QQ_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_QQ_SPAM_FOLDER", "Junk"),
    },
    "gmail": {
        "address":         os.environ.get("MAIL_GMAIL_ADDRESS", ""),
        "password":        os.environ.get("MAIL_GMAIL_PASSWORD", ""),
        "imap_server":     "imap.gmail.com",
        "imap_port":       993,
        "smtp_server":     "smtp.gmail.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         False,
        "auth":            os.environ.get("MAIL_GMAIL_AUTH", "oauth_google"),
        "oauth_token_file": os.path.join(os.path.dirname(__file__), "..", "token_gmail.json"),
        "oauth_creds_file": os.path.join(os.path.dirname(__file__), "..", "credentials_gmail.json"),
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_GMAIL_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_GMAIL_SPAM_FOLDER", "[Gmail]/Spam"),
    },
    "outlook": {
        "address":         os.environ.get("MAIL_OUTLOOK_ADDRESS", ""),
        "imap_server":     "outlook.office365.com",
        "imap_port":       993,
        "smtp_server":     "smtp.office365.com",
        "smtp_port":       587,
        "smtp_ssl":        False,
        "imap_id":         False,
        "auth":            "oauth_microsoft",
        "oauth_token_file": os.path.join(os.path.dirname(__file__), "..", "token_outlook.json"),
        "oauth_client_id":  os.environ.get("OUTLOOK_CLIENT_ID", ""),
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_OUTLOOK_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_OUTLOOK_SPAM_FOLDER", "Junk"),
    },
    "icloud": {
        "address":         os.environ.get("MAIL_ICLOUD_ADDRESS", ""),
        "password":        os.environ.get("MAIL_ICLOUD_PASSWORD", ""),  # App-specific password
        "imap_server":     "imap.mail.me.com",
        "imap_port":       993,
        "smtp_server":     "smtp.mail.me.com",
        "smtp_port":       587,
        "smtp_ssl":        False,
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_ICLOUD_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_ICLOUD_SPAM_FOLDER", "Junk"),
    },
    "proton": {
        "address":         os.environ.get("MAIL_PROTON_ADDRESS", ""),
        "password":        os.environ.get("MAIL_PROTON_PASSWORD", ""),  # Bridge password
        "imap_server":     "127.0.0.1",
        "imap_port":       1143,
        "smtp_server":     "127.0.0.1",
        "smtp_port":       1025,
        "smtp_ssl":        False,
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_PROTON_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_PROTON_SPAM_FOLDER", "Spam"),
    },
    "custom": {
        "address":         os.environ.get("MAIL_CUSTOM_ADDRESS", ""),
        "password":        os.environ.get("MAIL_CUSTOM_PASSWORD", ""),
        "imap_server":     os.environ.get("MAIL_CUSTOM_IMAP_SERVER", ""),
        "imap_port":       int(os.environ.get("MAIL_CUSTOM_IMAP_PORT", "993")),
        "smtp_server":     os.environ.get("MAIL_CUSTOM_SMTP_SERVER", ""),
        "smtp_port":       int(os.environ.get("MAIL_CUSTOM_SMTP_PORT", "465")),
        "smtp_ssl":        os.environ.get("MAIL_CUSTOM_SMTP_SSL", "true").lower() == "true",
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_CUSTOM_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_CUSTOM_SPAM_FOLDER", ""),
    },
}

# ═══════════════════════════════════════════════════════════════
#  AI 配置
# ═══════════════════════════════════════════════════════════════

def _find_cli(name: str, env_key: str) -> str:
    """在环境变量或常见路径中查找 CLI 可执行文件"""
    env_cmd = os.environ.get(env_key, "")
    if env_cmd:
        return env_cmd
    
    # 常见路径
    paths = [
        os.path.expanduser(f"~/.local/bin/{name}"),
        os.path.expanduser(f"~/bin/{name}"),
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
    ]
    for p in paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
            
    # 最后尝试直接返回名称（依赖 PATH）
    return shutil.which(name) or name

def _copilot_cmd() -> str:
    """查找 GitHub Copilot CLI 可执行文件路径"""
    env_cmd = os.environ.get("COPILOT_CMD", "")
    if env_cmd:
        return env_cmd
    bundled = os.path.expanduser(
        "~/.vscode-server/data/User/globalStorage/github.copilot-chat/copilotCli/copilot"
    )
    if os.path.isfile(bundled):
        return bundled
    return _find_cli("copilot", "COPILOT_CMD")


AI_BACKENDS = {
    # CLI 方式
    "claude":      {"type": "cli",           "cmd": _find_cli("claude", "CLAUDE_CMD"), "args": ["--print"],                                 "native_web_search": True, "label": "Claude CLI",       "env_key": None},
    "codex":       {"type": "cli",           "cmd": _find_cli("codex", "CODEX_CMD"),  "args": ["exec", "--skip-git-repo-check"],           "native_web_search": True, "label": "Codex CLI",        "env_key": None},
    "gemini":      {"type": "cli",           "cmd": _find_cli("gemini", "GEMINI_CMD"), "args": ["-p"],                                      "native_web_search": True, "label": "Gemini CLI",       "env_key": None},
    "qwen":        {"type": "cli",           "cmd": _find_cli("qwen", "QWEN_CMD"),   "args": ["--prompt", "--web-search-default", "--yolo"], "native_web_search": True, "label": "Qwen CLI",         "env_key": None},
    "copilot":     {"type": "cli_copilot",   "cmd": _copilot_cmd(),                                                                         "native_web_search": True, "label": "GitHub Copilot",   "env_key": "GITHUB_COPILOT_TOKEN"},

    # API 方式 - 国际模型
    "anthropic":   {"type": "api_anthropic", "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),  "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),                                                      "label": "Anthropic Claude",  "env_key": "ANTHROPIC_API_KEY"},
    "openai":      {"type": "api_openai",    "api_key": os.environ.get("OPENAI_API_KEY", ""),     "model": os.environ.get("OPENAI_MODEL",     "gpt-4o"),            "url": "https://api.openai.com/v1/chat/completions",          "label": "OpenAI (gpt-4o)",   "env_key": "OPENAI_API_KEY"},
    "gemini-api":  {"type": "api_gemini",    "api_key": os.environ.get("GEMINI_API_KEY", ""),     "model": os.environ.get("GEMINI_MODEL",     "gemini-3-flash-preview"),                                                 "label": "Gemini API",        "env_key": "GEMINI_API_KEY"},
    "deepseek":    {"type": "api_openai",    "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),   "model": os.environ.get("DEEPSEEK_MODEL",    "deepseek-chat"),     "url": "https://api.deepseek.com/v1/chat/completions",        "label": "DeepSeek",          "env_key": "DEEPSEEK_API_KEY"},
    "groq":        {"type": "api_openai",    "api_key": os.environ.get("GROQ_API_KEY", ""),       "model": os.environ.get("GROQ_MODEL",         "llama-3.3-70b-versatile"), "url": "https://api.groq.com/openai/v1/chat/completions",  "label": "Groq (Llama)",      "env_key": "GROQ_API_KEY"},
    "perplexity":  {"type": "api_openai",    "api_key": os.environ.get("PERPLEXITY_API_KEY", ""), "model": os.environ.get("PERPLEXITY_MODEL",   "sonar-pro"),             "url": "https://api.perplexity.ai/chat/completions",      "label": "Perplexity",        "env_key": "PERPLEXITY_API_KEY"},
    "cohere":      {"type": "api_cohere",    "api_key": os.environ.get("COHERE_API_KEY", ""),     "model": os.environ.get("COHERE_MODEL",       "command-r-plus"),                                                        "label": "Cohere",            "env_key": "COHERE_API_KEY"},

    # API 方式 - 中国模型
    "qwen-api":    {"type": "api_qwen",      "api_key": os.environ.get("QWEN_API_KEY", ""),       "model": os.environ.get("QWEN_MODEL",       "qwen-max"),                                                               "label": "通义千问 (Qwen)",    "env_key": "QWEN_API_KEY"},
    "moonshot":    {"type": "api_openai",    "api_key": os.environ.get("MOONSHOT_API_KEY", ""),   "model": os.environ.get("MOONSHOT_MODEL",   "moonshot-v1-8k"),      "url": "https://api.moonshot.cn/v1/chat/completions",        "label": "月之暗面 Kimi",      "env_key": "MOONSHOT_API_KEY"},
    "glm":         {"type": "api_openai",    "api_key": os.environ.get("GLM_API_KEY", ""),        "model": os.environ.get("GLM_MODEL",        "glm-4"),               "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "label": "智谱 GLM",          "env_key": "GLM_API_KEY"},
    "spark":       {"type": "api_spark",     "api_key": os.environ.get("SPARK_API_KEY", ""),      "model": os.environ.get("SPARK_MODEL",      "4.0Ultra"),                                                               "label": "讯飞星火",           "env_key": "SPARK_API_KEY"},
    "ernie":       {"type": "api_ernie",     "api_key": os.environ.get("ERNIE_API_KEY", ""),      "model": os.environ.get("ERNIE_MODEL",      "ernie-4.0-8k"),                                                           "label": "百度文心一言",        "env_key": "ERNIE_API_KEY"},
    "yi":          {"type": "api_openai",    "api_key": os.environ.get("YI_API_KEY", ""),         "model": os.environ.get("YI_MODEL",         "yi-lightning"),        "url": "https://api.lingyiwanwu.com/v1/chat/completions",     "label": "零一万物 Yi",        "env_key": "YI_API_KEY"},
}

# ────────────────────────────────────────────────────────────────
#  Web Search / Weather / News 配置
# ────────────────────────────────────────────────────────────────

WEB_SEARCH_ENABLED = os.environ.get("WEB_SEARCH", "false").lower() == "true"
WEB_SEARCH_ENGINE = os.environ.get("WEB_SEARCH_ENGINE", "google")
SEARCH_RESULTS_COUNT = int(os.environ.get("SEARCH_RESULTS_COUNT", "5"))
WEB_SEARCH_TIMEOUT = int(os.environ.get("WEB_SEARCH_TIMEOUT", "10"))
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
WEATHER_DEFAULT_LOCATION = os.environ.get("WEATHER_DEFAULT_LOCATION", "Tokyo")
NEWS_DEFAULT_QUERY = os.environ.get("NEWS_DEFAULT_QUERY", "technology OR AI")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
DEFAULT_TASK_AI = os.environ.get("TASK_DEFAULT_AI", "")
ATTACHMENT_MAX_SIZE_MB = int(os.environ.get("ATTACHMENT_MAX_SIZE_MB", "10"))
AI_CONCURRENCY = int(os.environ.get("AI_CONCURRENCY", "3"))
CONTEXT_MAX_DEPTH = int(os.environ.get("CONTEXT_MAX_DEPTH", "5"))
AI_MODIFY_SUBJECT = os.environ.get("AI_MODIFY_SUBJECT", "false").lower() == "true"

# ────────────────────────────────────────────────────────────────
#  Prompts
# ────────────────────────────────────────────────────────────────

_PROMPT_TEMPLATES = {
    "zh": """\
当前时间：{{now}}
你是邮件 AI 助手。请阅读以下邮件并执行任务，回复必须为纯 JSON，不含其他文字：
{{"subject": "可选：简短标题(不加 Re:/回复: 前缀)",
  "body": "回复正文",
  "schedule_at": "一次性定时：ISO格式或相对秒数，如 2026-03-17T09:00:00 或 3600",
  "schedule_every": "固定间隔重复：如 5m / 2h / 1d（与 schedule_cron 二选一）",
  "schedule_cron": "按规律重复：cron 表达式，如每天9点→'0 9 * * *'，工作日9点→'0 9 * * 1-5'（与 schedule_every 二选一）",
  "schedule_until": "重复任务截止时间（ISO格式），与 schedule_every/schedule_cron 配合",
  "attachments": [{{"filename": "a.txt", "content": "文本内容"}}],
  "task_type": "email|ai_job|weather|news|web_search|report|system_status",
  "task_payload": {{"query": "...", "location": "...", "prompt": "..."}},
  "output": {{"email": true, "archive": true}}
}}
规则：
- schedule_at / schedule_every / schedule_cron 三选一，不可同时设置。
- 有定时要求时必须设置 task_type：新闻/股市/简报 → news，天气 → weather，AI 问答/分析 → ai_job，系统状态 → system_status，综合报告 → report。
- task_payload 填写任务参数，例如 {{"query": "日本股市行情"}} 或 {{"location": "东京"}}。
- 即时回复（无定时）时省略所有 schedule_* 字段。
- 附件仅限文本内容。
邮件内容：
{{instruction}}""",

    "ja": """\
現在時刻：{{now}}
あなたはメールAIアシスタントです。以下のメールを読みタスクを実行し、純粋なJSONのみで回答してください：
{{"subject": "任意：短い件名(Re:/返信:不要)",
  "body": "返信本文",
  "schedule_at": "一回限り：ISO形式または相対秒 例: 2026-03-17T09:00:00 または 3600",
  "schedule_every": "固定間隔繰り返し：例 5m/2h/1d（schedule_cronと二択）",
  "schedule_cron": "規則的繰り返し：cron式 例 毎朝9時→'0 9 * * *' 平日9時→'0 9 * * 1-5'（schedule_everyと二択）",
  "schedule_until": "繰り返し終了時刻（ISO形式）、schedule_every/schedule_cronと併用",
  "attachments": [{{"filename": "a.txt", "content": "..."}}],
  "task_type": "email|ai_job|weather|news|web_search|report|system_status",
  "task_payload": {{"query": "...", "location": "...", "prompt": "..."}},
  "output": {{"email": true, "archive": true}}
}}
ルール：
- schedule_at/schedule_every/schedule_cronは三択、同時設定不可。
- スケジュール時はtask_typeを必須設定：ニュース/株→news、天気→weather、AI分析→ai_job、システム→system_status、総合レポート→report。
- task_payloadに必要なパラメータを設定（例：{{"query":"日本株式市場"}}）。
- 即時返信の場合はschedule_*フィールドを省略。
{{instruction}}""",

    "en": """\
Current time: {{now}}
You are an email AI assistant. Read the email below and execute the task. Reply in pure JSON only:
{{"subject": "Optional: Short title (no Re:/Reply: prefix)",
  "body": "Reply body",
  "schedule_at": "One-time: ISO format or relative seconds, e.g. 2026-03-17T09:00:00 or 3600",
  "schedule_every": "Fixed interval repeat: e.g. 5m/2h/1d (mutually exclusive with schedule_cron)",
  "schedule_cron": "Pattern repeat: cron expression, e.g. daily 9am→'0 9 * * *', weekdays 9am→'0 9 * * 1-5' (mutually exclusive with schedule_every)",
  "schedule_until": "End time for repeating tasks (ISO format), used with schedule_every/schedule_cron",
  "attachments": [{{"filename": "a.txt", "content": "text content"}}],
  "task_type": "email|ai_job|weather|news|web_search|report|system_status",
  "task_payload": {{"query": "...", "location": "...", "prompt": "..."}},
  "output": {{"email": true, "archive": true}}
}}
Rules:
- Use exactly one of schedule_at / schedule_every / schedule_cron, never multiple.
- Scheduled tasks MUST set task_type: news/stocks→news, weather→weather, AI analysis→ai_job, system info→system_status, summary→report.
- Set task_payload with required params, e.g. {{"query": "Japan stock market"}}.
- For immediate replies, omit all schedule_* fields.
- Attachments: text content only.
Email:
{{instruction}}""",
}


def _load_prompt_template() -> str:
    custom_file = os.environ.get("PROMPT_TEMPLATE_FILE", "")
    if custom_file and os.path.isfile(custom_file):
        with open(custom_file, "r", encoding="utf-8") as f:
            tmpl = f.read()
        if "{instruction}" not in tmpl and "{{instruction}}" in tmpl:
            tmpl = tmpl.replace("{{instruction}}", "{instruction}")
        if "{now}" not in tmpl and "{{now}}" in tmpl:
            tmpl = tmpl.replace("{{now}}", "{now}")
        return tmpl
    lang = os.environ.get("PROMPT_LANG", "zh").lower()
    tmpl = _PROMPT_TEMPLATES.get(lang, _PROMPT_TEMPLATES["zh"])
    # Convert {{instruction}}/{{now}} → {instruction}/{now} for .format() compatibility
    return tmpl.replace("{{instruction}}", "{instruction}").replace("{{now}}", "{now}")

PROMPT_TEMPLATE = _load_prompt_template()
PROMPT_LANG = os.environ.get("PROMPT_LANG", "zh").lower()

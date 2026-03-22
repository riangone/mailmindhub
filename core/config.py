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
        "trash_folder":    os.environ.get("MAIL_126_TRASH_FOLDER", "已删除"),
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
        "trash_folder":    os.environ.get("MAIL_163_TRASH_FOLDER", "已删除"),
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
        "trash_folder":    os.environ.get("MAIL_QQ_TRASH_FOLDER", "已删除邮件"),
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
        "trash_folder":    os.environ.get("MAIL_GMAIL_TRASH_FOLDER", "[Gmail]/Trash"),
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
        "trash_folder":    os.environ.get("MAIL_OUTLOOK_TRASH_FOLDER", "Deleted Items"),
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
        "trash_folder":    os.environ.get("MAIL_ICLOUD_TRASH_FOLDER", "Deleted Messages"),
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
        "trash_folder":    os.environ.get("MAIL_PROTON_TRASH_FOLDER", "Trash"),
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
        "trash_folder":    os.environ.get("MAIL_CUSTOM_TRASH_FOLDER", "Trash"),
    },
    # 邮件整理专用邮箱（用于自动归类/移动/标记邮件）
    # 支持多个管理邮箱：sort, sort2, sort3, ...
    "sort": {
        "address":         os.environ.get("MAIL_SORT_ADDRESS", ""),
        "password":        os.environ.get("MAIL_SORT_PASSWORD", ""),
        "imap_server":     os.environ.get("MAIL_SORT_IMAP_SERVER", ""),
        "imap_port":       int(os.environ.get("MAIL_SORT_IMAP_PORT", "993")),
        "smtp_server":     os.environ.get("MAIL_SORT_SMTP_SERVER", ""),
        "smtp_port":       int(os.environ.get("MAIL_SORT_SMTP_PORT", "465")),
        "smtp_ssl":        os.environ.get("MAIL_SORT_SMTP_SSL", "true").lower() == "true",
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_SORT_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_SORT_SPAM_FOLDER", "Junk"),
        "trash_folder":    os.environ.get("MAIL_SORT_TRASH_FOLDER", "Trash"),
        "manage_only":     True,  # 管理邮箱只执行移动/删除/标记操作，不回复邮件
    },
    "sort2": {
        "address":         os.environ.get("MAIL_SORT2_ADDRESS", ""),
        "password":        os.environ.get("MAIL_SORT2_PASSWORD", ""),
        "imap_server":     os.environ.get("MAIL_SORT2_IMAP_SERVER", ""),
        "imap_port":       int(os.environ.get("MAIL_SORT2_IMAP_PORT", "993")),
        "smtp_server":     os.environ.get("MAIL_SORT2_SMTP_SERVER", ""),
        "smtp_port":       int(os.environ.get("MAIL_SORT2_SMTP_PORT", "465")),
        "smtp_ssl":        os.environ.get("MAIL_SORT2_SMTP_SSL", "true").lower() == "true",
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_SORT2_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_SORT2_SPAM_FOLDER", "Junk"),
        "trash_folder":    os.environ.get("MAIL_SORT2_TRASH_FOLDER", "Trash"),
        "manage_only":     True,
    },
    "sort3": {
        "address":         os.environ.get("MAIL_SORT3_ADDRESS", ""),
        "password":        os.environ.get("MAIL_SORT3_PASSWORD", ""),
        "imap_server":     os.environ.get("MAIL_SORT3_IMAP_SERVER", ""),
        "imap_port":       int(os.environ.get("MAIL_SORT3_IMAP_PORT", "993")),
        "smtp_server":     os.environ.get("MAIL_SORT3_SMTP_SERVER", ""),
        "smtp_port":       int(os.environ.get("MAIL_SORT3_SMTP_PORT", "465")),
        "smtp_ssl":        os.environ.get("MAIL_SORT3_SMTP_SSL", "true").lower() == "true",
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_SORT3_ALLOWED", "").split(",") if s.strip()],
        "spam_folder":     os.environ.get("MAIL_SORT3_SPAM_FOLDER", "Junk"),
        "trash_folder":    os.environ.get("MAIL_SORT3_TRASH_FOLDER", "Trash"),
        "manage_only":     True,
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
    "claude":      {"type": "cli",           "cmd": _find_cli("claude", "CLAUDE_CMD"), "args": ["--print", "--dangerously-skip-permissions"],                           "native_web_search": True, "label": "Claude CLI",       "env_key": None},
    "codex":       {"type": "cli",           "cmd": _find_cli("codex", "CODEX_CMD"),  "args": ["exec", "--skip-git-repo-check", "--full-auto"],                   "native_web_search": True, "label": "Codex CLI",        "env_key": None},
    "gemini":      {"type": "cli",           "cmd": _find_cli("gemini", "GEMINI_CMD"), "args": ["-y", "-p"],                                                               "native_web_search": True, "label": "Gemini CLI",       "env_key": None},
    "qwen":        {"type": "cli",           "cmd": _find_cli("qwen", "QWEN_CMD"),   "args": ["--prompt", "--web-search-default", "--yolo"],                               "native_web_search": True, "label": "Qwen CLI",         "env_key": None},
    "copilot":     {"type": "cli",            "cmd": _copilot_cmd(),                  "args": [],                                                                          "native_web_search": True, "label": "GitHub Copilot",   "env_key": "GITHUB_COPILOT_TOKEN"},
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
    # 本地 LLM
    "ollama":      {"type": "api_ollama",    "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"), "model": os.environ.get("OLLAMA_MODEL", ""),    "stream": True,  "label": "Ollama (本地)",      "env_key": None},
    "vllm":        {"type": "api_openai",    "api_key":  os.environ.get("VLLM_API_KEY",  "EMPTY"),                   "model": os.environ.get("VLLM_MODEL",   ""),    "url":    os.environ.get("VLLM_BASE_URL", "http://localhost:8000") + "/v1/chat/completions", "label": "vLLM (本地)",        "env_key": None},
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
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
NEWS_DEFAULT_LANGUAGE = os.environ.get("NEWS_DEFAULT_LANGUAGE", "en")
NEWS_DEFAULT_PAGE_SIZE = int(os.environ.get("NEWS_DEFAULT_PAGE_SIZE", "5"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
DEFAULT_TASK_AI = os.environ.get("TASK_DEFAULT_AI", "")
ATTACHMENT_MAX_SIZE_MB = int(os.environ.get("ATTACHMENT_MAX_SIZE_MB", "10"))
AI_CONCURRENCY = int(os.environ.get("AI_CONCURRENCY", "3"))
CONTEXT_MAX_DEPTH = int(os.environ.get("CONTEXT_MAX_DEPTH", "5"))
AI_MODIFY_SUBJECT = os.environ.get("AI_MODIFY_SUBJECT", "false").lower() == "true"
MAX_EMAIL_CHARS = int(os.environ.get("MAX_EMAIL_CHARS", "4000"))
AI_CLI_TIMEOUT = int(os.environ.get("AI_CLI_TIMEOUT", "600"))          # CLI AI 超时秒数（默认10分钟）
AI_PROGRESS_INTERVAL = int(os.environ.get("AI_PROGRESS_INTERVAL", "120"))  # 进度邮件间隔秒数（0=禁用）
# ────────────────────────────────────────────────────────────────
#  Workspace 配置（限制 AI 操作范围）
# ────────────────────────────────────────────────────────────────
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "")
if WORKSPACE_DIR:
    WORKSPACE_DIR = os.path.realpath(os.path.abspath(WORKSPACE_DIR))

SHOW_FILE_CHANGES = os.environ.get("SHOW_FILE_CHANGES", "true").lower() == "true"
# ────────────────────────────────────────────────────────────────
#  Query Cache 配置
# ────────────────────────────────────────────────────────────────
CACHE_ENABLED  = os.environ.get("CACHE_ENABLED", "true").lower() == "true"
CACHE_MAX_SIZE = int(os.environ.get("CACHE_MAX_SIZE", "100"))
CACHE_TTL      = int(os.environ.get("CACHE_TTL", "3600"))  # 秒
# ────────────────────────────────────────────────────────────────
#  Prompts
# ────────────────────────────────────────────────────────────────
PROMPT_TEMPLATES = {
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
  "task_type": "email|ai_job|weather|news|web_search|report|system_status|email_manage|task_manage|<skill名>",
  "task_payload": {{"query": "...", "location": "...", "prompt": "...", "skill": "weather|news|stock|web_search", "payload": {{"location": "Tokyo"}},
    "action": "move|delete|mark_read|mark_unread（email_manage）或 list|cancel|pause|resume|delete（task_manage）",
    "task_id": 3,
    "filter": {{"type": "news", "subject": "关键词", "status": "pending|paused"}},
    "filter（email_manage）": {{"from_contains": "...", "subject_contains": "...", "folder": "INBOX", "since_days": 30, "before_days": 90, "unread": true}},
    "target_folder": "目标文件夹（email_manage action=move时必填）"}},
  "output": {{"email": true, "archive": true}}
}}
规则：
- schedule_at / schedule_every / schedule_cron 三选一，不可同时设置。
- **仅定时任务**需要设置 task_type：每天/每周定时发送新闻→news，定时天气→weather，定时系统状态→system_status，定时综合报告→report。
- **即时回复（无定时）**：直接让 AI 回答问题时，使用 ai_job 或省略 task_type，AI 会直接生成回复正文。
- 优先使用 AI skill 模式：task_type="ai_skill"，task_payload={{"skill": "weather|news|stock|web_search", "payload": {{...}}}}，AI 将自动调用外部工具或搜索能力。
- task_payload 填写任务参数，例如 {{"query": "日本股市行情"}} 或 {{"location": "东京"}}。
- 邮件整理/归类/移动/删除/标记已读 → email_manage，task_payload 必须包含 action 和 filter，action=move 时还需要 target_folder。
- 查看/取消/暂停/恢复/删除定时任务 → task_manage，task_payload 包含 action（list/cancel/pause/resume/delete）和 task_id 或 filter。
- 即时回复（无定时）时省略所有 schedule_* 字段。
- 附件仅限文本内容。
- 可使用已加载的技能作为 task_type（见下方技能列表）。
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
  "task_type": "email|ai_job|weather|news|web_search|report|system_status|email_manage|task_manage|<スキル名>",
  "task_payload": {{"query": "...", "location": "...", "prompt": "...", "skill": "weather|news|stock|web_search", "payload": {{"location": "Tokyo"}},
    "action": "move|delete|mark_read|mark_unread（email_manage）または list|cancel|pause|resume|delete（task_manage）",
    "task_id": 3,
    "filter": {{"type": "news", "subject": "キーワード", "status": "pending|paused"}},
    "filter（email_manage用）": {{"from_contains": "...", "subject_contains": "...", "folder": "INBOX", "since_days": 30, "before_days": 90, "unread": true}},
    "target_folder": "移動先フォルダ（email_manage action=moveの場合必須）"}},
  "output": {{"email": true, "archive": true}}
}}
ルール：
- schedule_at/schedule_every/schedule_cronは三択、同時設定不可。
- スケジュール時はtask_typeを必須設定：ニュース/株→news、天気→weather、AI分析→ai_job、システム→system_status、総合レポート→report。
- task_payloadに必要なパラメータを設定（例：{{"query":"日本株式市場"}}）。
- メール整理/移動/削除/既読化 → email_manage、task_payloadにaction・filterを必須設定、action=moveはtarget_folderも必要。
- 定期タスクの確認/取消/一時停止/再開/削除 → task_manage、action（list/cancel/pause/resume/delete）とtask_idまたはfilterを指定。
- 即時返信の場合はschedule_*フィールドを省略。
- ロードされたスキルをtask_typeとして使用可能（以下のスキル一覧参照）。
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
  "task_type": "email|ai_job|weather|news|web_search|report|system_status|email_manage|task_manage|<skill_name>",
  "task_payload": {{"query": "...", "location": "...", "prompt": "...", "skill": "weather|news|stock|web_search", "payload": {{"location": "Tokyo"}},
    "action": "move|delete|mark_read|mark_unread (email_manage) or list|cancel|pause|resume|delete (task_manage)",
    "task_id": 3,
    "filter": {{"type": "news", "subject": "keyword", "status": "pending|paused"}},
    "filter (email_manage)": {{"from_contains": "...", "subject_contains": "...", "folder": "INBOX", "since_days": 30, "before_days": 90, "unread": true}},
    "target_folder": "destination folder (required when email_manage action=move)"}},
  "output": {{"email": true, "archive": true}}
}}
Rules:
- Use exactly one of schedule_at / schedule_every / schedule_cron, never multiple.
- For SCHEDULED tasks ONLY: news→news, weather→weather, system_status→system_status, report→report.
- For IMMEDIATE replies (no schedule): Use ai_job or omit task_type.
- Set task_payload with required params, e.g. {{"query": "Japan stock market"}}.
- Email organization/sorting/moving/deleting/marking → email_manage; task_payload MUST include action and filter; action=move also requires target_folder.
- View/cancel/pause/resume/delete scheduled tasks → task_manage; specify action (list/cancel/pause/resume/delete) plus task_id or filter.
- For immediate replies, omit all schedule_* fields.
- Attachments: text content only.
- Loaded skills can be used as task_type (see skill list below).
Email:
{{instruction}}""",
    "ko": """\
현재 시각: {{now}}
당신은 이메일 AI 어시스턴트입니다. 아래 이메일을 읽고 작업을 수행하세요. 순수 JSON만으로 답변하세요:
{{"subject": "선택: 짧은 제목(Re:/답장: 접두사 불필요)",
  "body": "답장 본문",
  "schedule_at": "일회성 예약: ISO 형식 또는 상대 초, 예: 2026-03-17T09:00:00 또는 3600",
  "schedule_every": "고정 간격 반복: 예 5m/2h/1d（schedule_cron과 택일）",
  "schedule_cron": "규칙적 반복: cron 표현식, 예 매일 9시→'0 9 * * *', 평일 9시→'0 9 * * 1-5'（schedule_every와 택일）",
  "schedule_until": "반복 작업 종료 시각（ISO 형식）, schedule_every/schedule_cron과 함께 사용",
  "attachments": [{{"filename": "a.txt", "content": "텍스트 내용"}}],
  "task_type": "email|ai_job|weather|news|web_search|report|system_status|email_manage|task_manage|<스킬명>",
  "task_payload": {{"query": "...", "location": "...", "prompt": "...", "skill": "weather|news|stock|web_search", "payload": {{"location": "Tokyo"}},
    "action": "move|delete|mark_read|mark_unread（email_manage）또는 list|cancel|pause|resume|delete（task_manage）",
    "task_id": 3,
    "filter": {{"type": "news", "subject": "키워드", "status": "pending|paused"}},
    "filter（email_manage）": {{"from_contains": "...", "subject_contains": "...", "folder": "INBOX", "since_days": 30, "before_days": 90, "unread": true}},
    "target_folder": "대상 폴더（email_manage action=move 시 필수）"}},
  "output": {{"email": true, "archive": true}}
}}
규칙:
- schedule_at / schedule_every / schedule_cron 중 하나만 사용, 동시 설정 불가.
- 예약 작업 시 task_type 필수 설정: 뉴스/주식→news, 날씨→weather, AI 분석→ai_job, 시스템→system_status, 종합 보고서→report.
- task_payload에 필요한 파라미터 설정（예: {{"query": "일본 주식 시장"}}）.
- 이메일 정리/이동/삭제/읽음 표시 → email_manage, task_payload에 action과 filter 필수, action=move 시 target_folder도 필요.
- 예약 작업 확인/취소/일시정지/재개/삭제 → task_manage, action（list/cancel/pause/resume/delete）과 task_id 또는 filter 지정.
- 즉시 답장의 경우 schedule_* 필드 생략.
- 첨부 파일은 텍스트 내용만 가능.
- 로드된 스킬을 task_type으로 사용 가능（아래 스킬 목록 참조）.
이메일:
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
    tmpl = PROMPT_TEMPLATES.get(lang, PROMPT_TEMPLATES["zh"])
    # Convert {{instruction}}/{{now}} → {instruction}/{now} for .format() compatibility
    return tmpl.replace("{{instruction}}", "{instruction}").replace("{{now}}", "{now}")
PROMPT_TEMPLATE = _load_prompt_template()
PROMPT_LANG = os.environ.get("PROMPT_LANG", "zh").lower()
AUTO_DETECT_TASKS = os.environ.get("AUTO_DETECT_TASKS", "true").lower() == "true"
import imaplib
import email
import os
import re
import json
import logging
import base64
import time
from email.header import decode_header as _decode_header
from email.utils import parseaddr, formatdate
from email.mime.text import MIMEText
from core.config import MAILBOXES, ATTACHMENT_MAX_SIZE_MB, CONTEXT_MAX_DEPTH
from utils.logger import log

# ────────────────────────────────────────────────────────────────
# 模板定义（每条：subject, body）
# ────────────────────────────────────────────────────────────────
_TEMPLATES = {
    "zh": [
        (
            "【模板1】立即提问",
            "请帮我分析以下内容：\n\n[在此填写你的问题或内容]",
        ),
        (
            "【模板2】立即网页搜索",
            "搜索并总结关于[主题]的最新信息",
        ),
        (
            "【模板3】立即天气查询",
            "查询[城市名，如：东京]现在的天气",
        ),
        (
            "【模板4】每日新闻订阅",
            "每天早上9点发送[主题，如：日本股市]的最新新闻摘要，持续到[结束日期，如：2026-12-31]",
        ),
        (
            "【模板5】定时提醒（一次性）",
            "在[时间，如：2026-03-20 10:00]提醒我[提醒内容]",
        ),
        (
            "【模板6】每周AI分析",
            "每周一早上8点帮我分析[主题，如：本周科技热点]并发送邮件",
        ),
        (
            "【模板7】系统状态报告",
            "每天下午6点发送一次服务器运行状态报告",
        ),
        (
            "【编码1】新功能开发",
            """【新功能】<功能名称>

目标：<具体要做什么>
文件：<涉及的文件或目录，如 api/login.py、utils/cache.py>
要求：
- <约束1，如：用现有的 Redis 客户端，不引入新依赖>
- <约束2，如：写对应的单元测试>
- <约束3>""",
        ),
        (
            "【编码2】Bug 修复",
            """【Bug】<简短描述>

现象：<错误表现或日志>

文件：<涉及文件>
要求：
- 找出根本原因
- <修复要求>
- 失败时返回友好错误信息""",
        ),
        (
            "【编码3】代码审查",
            """【审查】<模块名称>

文件：<目录或文件>
重点检查：
- <检查项1，如：SQL 注入风险>
- <检查项2，如：敏感信息日志明文>
- <检查项3，如：异常处理完整性>
输出：列出问题清单（按严重程度排序），不要修改代码""",
        ),
        (
            "【编码4】重构",
            """【重构】<描述>

文件：<目标文件>
目标：<重构方向，如：按职责拆分为独立模块>
要求：
- 保持对外接口不变（向后兼容）
- 原有测试必须全部通过
- 不要修改数据库 Schema""",
        ),
        (
            "【编码5】补充测试",
            """【测试】为 <模块> 补充单元测试

文件：<源文件>，<测试文件>
要求：
- 覆盖所有 public 函数
- 重点覆盖边界条件：空输入、超长输入、特殊字符
- 使用现有的 pytest 框架和 fixture 风格
- 目标覆盖率 90% 以上""",
        ),
        (
            "【编码6】性能优化",
            """【性能】优化 <接口或函数> 响应时间

文件：<目标文件>
背景：<瓶颈描述，如：P99 约 800ms，每次全量查询数据库>
要求：
- <优化手段，如：加入内存缓存，TTL 5分钟>
- 不改变接口返回格式
- 在注释中说明优化策略""",
        ),
        (
            "【编码7】数据库变更",
            """【数据库】<变更描述>

文件：<模型文件>，migrations/（Alembic）
目标：
- <变更内容1>
- <变更内容2>
- 生成对应的 migration 文件
注意：不影响现有业务逻辑""",
        ),
        (
            "【编码8】API 设计",
            """【API】<接口描述>

文件：<目标文件>（不存在则新建）
要求：
- <端点和请求格式>
- <输入限制和校验>
- 超出限制返回 400 和明确的错误信息
- 添加 OpenAPI 注释""",
        ),
        (
            "【编码9】安全加固",
            """【安全】<审查范围>

文件：<目标目录或文件>
任务：
1. <检查项1，如：找出所有未经鉴权即可访问的接口>
2. <检查项2>
3. 修复发现的问题
4. 回复中附上修复清单""",
        ),
        (
            "【编码10】文档补全",
            """【文档】为 <模块> 补充 docstring

文件：<目标目录>
要求：
- 为每个 public 函数补充 Google 风格 docstring
- 包含参数类型、返回值、异常说明
- 只补充缺失的，不修改已有的
- 不改动任何业务逻辑""",
        ),
        (
            "【编码11】依赖升级",
            """【升级】将 <库名> 从 <旧版本> 升级到 <新版本>

文件：requirements.txt，<相关文件>
背景：<升级原因或 breaking change 说明>
要求：
- 更新所有废弃的 API 用法
- 保持现有测试全部通过
- 回复中列出主要改动点""",
        ),
        (
            "【编码12】紧急修复",
            """【紧急】生产报错，立即修复

错误：<错误类型和信息>
位置：<文件名>，<函数名>
请找出原因并修复，不要改动其他逻辑。""",
        ),
        (
            "【编码13】继续上次任务",
            """（回复上一封邮件，继续迭代）

上面的实现有个问题：<描述问题>
请在 <函数或文件> 中修正，其他不变。""",
        ),
    ],
    "ja": [
        (
            "【テンプレート1】即時AI回答",
            "以下の内容を分析・回答してください：\n\n[ここに質問や内容を入力]",
        ),
        (
            "【テンプレート2】即時ウェブ検索",
            "[トピック]に関する最新情報を検索してまとめてください",
        ),
        (
            "【テンプレート3】即時天気確認",
            "[都市名、例：東京]の現在の天気を教えてください",
        ),
        (
            "【テンプレート4】毎日ニュース配信",
            "毎朝9時に[テーマ、例：日経225・東証]の最新ニュースを送ってください。[終了日、例：2026-12-31]まで",
        ),
        (
            "【テンプレート5】一回限りのリマインダー",
            "[日時、例：2026-03-20 10:00]に[内容]をリマインドしてください",
        ),
        (
            "【テンプレート6】毎週定期AI分析",
            "毎週月曜朝8時に[テーマ、例：今週のテクノロジー動向]を分析してメールで送ってください",
        ),
        (
            "【テンプレート7】サーバー状態レポート",
            "毎日18時にサーバーの稼働状況レポートを送ってください",
        ),
        (
            "【コーディング1】新機能開発",
            """【新機能】<機能名>

目標：<何をすべきか>
ファイル：<対象ファイル/ディレクトリ>
要件：
- <制約1、例：既存の Redis クライアントを使用、新規依存禁止>
- <制約2、例：対応するユニットテストを追加>
- <制約3>""",
        ),
        (
            "【コーディング2】バグ修正",
            """【バグ】<短い説明>

現象：<エラー内容やログ>

ファイル：<対象ファイル>
要件：
- 根本原因を特定
- <修正要件>
- 失敗時は適切なエラーメッセージを返す""",
        ),
        (
            "【コーディング3】コードレビュー",
            """【レビュー】<モジュール名>

ファイル：<ディレクトリまたはファイル>
重点確認：
- <確認項目1、例：SQL インジェクションリスク>
- <確認項目2、例：ログへの機密情報の平文出力>
- <確認項目3、例：例外処理の網羅性>
出力：問題点を重大度順に列挙（コードは修正しない）""",
        ),
        (
            "【コーディング4】リファクタリング",
            """【リファクタ】<説明>

ファイル：<対象ファイル>
目標：<リファクタ方向、例：責務別に分割>
要件：
- 外部インターフェースは変更しない（後方互換）
- 既存テストをすべて通過させる
- DB スキーマは変更しない""",
        ),
        (
            "【コーディング5】テスト追加",
            """【テスト】<モジュール> のユニットテスト補完

ファイル：<ソースファイル>、<テストファイル>
要件：
- すべての public 関数をカバー
- 境界条件を重点的に：空入力・超長入力・特殊文字
- 既存の pytest フレームワーク・fixture スタイルに準拠
- カバレッジ目標 90% 以上""",
        ),
        (
            "【コーディング6】パフォーマンス最適化",
            """【最適化】<エンドポイントまたは関数> のレスポンス改善

ファイル：<対象ファイル>
背景：<ボトルネックの説明>
要件：
- <最適化手段、例：メモリキャッシュ追加、TTL 5分>
- レスポンス形式は変更しない
- キャッシュ戦略をコメントで説明""",
        ),
        (
            "【コーディング7】DB スキーマ変更",
            """【DB】<変更の説明>

ファイル：<モデルファイル>、migrations/（Alembic）
目標：
- <変更内容1>
- <変更内容2>
- migration ファイルを生成
注意：既存のビジネスロジックに影響を与えない""",
        ),
        (
            "【コーディング8】緊急修正",
            """【緊急】本番エラー、即時修正

エラー：<エラー種別とメッセージ>
場所：<ファイル名>、<関数名>
原因を特定して修正。他のロジックには触れないこと。""",
        ),
        (
            "【コーディング9】前の作業を継続",
            """（前のメールに返信して継続）

上の実装に問題があります：<問題の説明>
<関数またはファイル> を修正してください。他は変更不要。""",
        ),
    ],
    "en": [
        (
            "[Template 1] Instant AI Answer",
            "Please analyze and answer the following:\n\n[Enter your question or content here]",
        ),
        (
            "[Template 2] Instant Web Search",
            "Search and summarize the latest information about [topic]",
        ),
        (
            "[Template 3] Instant Weather",
            "What is the current weather in [city, e.g. Tokyo]?",
        ),
        (
            "[Template 4] Daily News Digest",
            "Send me a daily news digest about [topic, e.g. AI industry] every morning at 9am until [end date, e.g. 2026-12-31]",
        ),
        (
            "[Template 5] One-time Reminder",
            "Remind me about [content] at [datetime, e.g. 2026-03-20 10:00]",
        ),
        (
            "[Template 6] Weekly AI Analysis",
            "Every Monday at 8am, analyze [topic, e.g. this week's tech highlights] and email me the results",
        ),
        (
            "[Template 7] Server Status Report",
            "Send me a server status report every day at 6pm",
        ),
        (
            "[Coding 1] New Feature",
            """[Feature] <Feature name>

Goal: <What needs to be done>
Files: <Target files/directories>
Requirements:
- <Constraint 1, e.g.: use existing Redis client, no new dependencies>
- <Constraint 2, e.g.: add corresponding unit tests>
- <Constraint 3>""",
        ),
        (
            "[Coding 2] Bug Fix",
            """[Bug] <Short description>

Symptom: <Error message or log output>

Files: <Target files>
Requirements:
- Identify the root cause
- <Fix requirement>
- Return a friendly error message on failure""",
        ),
        (
            "[Coding 3] Code Review",
            """[Review] <Module name>

Files: <Directory or files>
Focus on:
- <Check 1, e.g.: SQL injection risks>
- <Check 2, e.g.: sensitive data logged in plaintext>
- <Check 3, e.g.: completeness of exception handling>
Output: List issues sorted by severity. Do not modify code.""",
        ),
        (
            "[Coding 4] Refactoring",
            """[Refactor] <Description>

Files: <Target files>
Goal: <Refactor direction, e.g.: split by responsibility>
Requirements:
- Keep external interfaces unchanged (backward compatible)
- All existing tests must still pass
- Do not alter the DB schema""",
        ),
        (
            "[Coding 5] Add Tests",
            """[Tests] Add unit tests for <module>

Files: <Source file>, <Test file>
Requirements:
- Cover all public functions
- Focus on edge cases: empty input, very long input, special characters
- Follow existing pytest framework and fixture style
- Target 90%+ coverage""",
        ),
        (
            "[Coding 6] Performance",
            """[Performance] Improve <endpoint or function> response time

Files: <Target files>
Context: <Bottleneck description>
Requirements:
- <Optimization, e.g.: add in-memory cache with 5-minute TTL>
- Do not change the response format
- Comment the optimization strategy""",
        ),
        (
            "[Coding 7] DB Change",
            """[DB] <Change description>

Files: <Model file>, migrations/ (Alembic)
Goal:
- <Change 1>
- <Change 2>
- Generate the migration file
Note: Do not affect existing business logic""",
        ),
        (
            "[Coding 8] Urgent Fix",
            """[Urgent] Production error, fix immediately

Error: <Error type and message>
Location: <File>, <Function>
Find the cause and fix it. Do not touch any other logic.""",
        ),
        (
            "[Coding 9] Continue Previous Task",
            """(Reply to previous email to continue)

The implementation above has a problem: <describe the issue>
Please fix <function or file>. No other changes.""",
        ),
    ],
}

_FOLDER_NAMES = {
    "zh": "MailMindHub模板",
    "ja": "MailMindHubテンプレート",
    "en": "MailMindHub Templates",
}

def list_imap_folders(mailbox: dict) -> list:
    """Return list of all folder names in the mailbox."""
    mail = imap_login(mailbox)
    try:
        _, folder_list = mail.list()
        folders = []
        for item in folder_list:
            if not item:
                continue
            decoded = item.decode() if isinstance(item, bytes) else item
            m = re.search(r'"/" (?:"([^"]+)"|(\S+))$', decoded)
            if m:
                folders.append((m.group(1) or m.group(2)).strip())
        return folders
    except Exception as e:
        log.warning(f"获取文件夹列表失败：{e}")
        return ["INBOX"]
    finally:
        mail.logout()


def fetch_email_headers_all(mailbox: dict, folders: list = None) -> list:
    """Fetch email headers (uid, folder, from, subject, date, flags) from given folders.
    Returns list of header dicts. Fetches up to 500 per folder."""
    if folders is None:
        folders = ["INBOX"]

    mail = imap_login(mailbox)
    results = []
    try:
        for folder in folders:
            try:
                status, _ = mail.select(folder, readonly=True)
                if status != "OK":
                    continue
                _, data = mail.uid("search", None, "ALL")
                uids = data[0].split()
                if not uids:
                    continue
                uids = uids[:500]  # cap per folder
                # Fetch in batches of 50
                for i in range(0, len(uids), 50):
                    batch = b",".join(uids[i:i + 50])
                    _, fetch_data = mail.uid("fetch", batch, "(RFC822.HEADER FLAGS)")
                    for item in fetch_data:
                        if not isinstance(item, tuple):
                            continue
                        meta = item[0].decode()
                        uid_m = re.search(r"UID (\d+)", meta)
                        if not uid_m:
                            continue
                        uid = uid_m.group(1)
                        flags_m = re.search(r"FLAGS \(([^)]*)\)", meta)
                        flags = flags_m.group(1) if flags_m else ""
                        msg = email.message_from_bytes(item[1])
                        from_raw = decode_str(msg.get("From", ""))
                        from_email_addr = parseaddr(from_raw)[1].strip()
                        results.append({
                            "uid": uid,
                            "folder": folder,
                            "from_email": from_email_addr,
                            "from": from_raw,
                            "subject": decode_str(msg.get("Subject", "(无主题)")),
                            "date": msg.get("Date", ""),
                            "flags": flags,
                            "message_id": msg.get("Message-ID", ""),
                        })
            except Exception as e:
                log.warning(f"获取文件夹 '{folder}' 邮件头失败：{e}")
    finally:
        mail.logout()
    return results


def imap_move_messages(mail, uid_list: list, target_folder: str) -> int:
    """Move UIDs to target_folder. Returns count of successfully moved messages.
    Caller must have already selected the source folder (read-write)."""
    if not uid_list:
        return 0
    success = 0
    # Create destination folder if needed
    try:
        mail.create(target_folder)
    except Exception:
        pass
    for uid in uid_list:
        try:
            rv, _ = mail.uid("copy", uid, target_folder)
            if rv == "OK":
                mail.uid("store", uid, "+FLAGS", "\\Deleted")
                success += 1
        except Exception as e:
            log.warning(f"移动 uid={uid} 失败：{e}")
    mail.expunge()
    return success


def imap_delete_messages(mail, uid_list: list) -> int:
    """Mark UIDs as \\Deleted and expunge. Returns count deleted."""
    if not uid_list:
        return 0
    success = 0
    for uid in uid_list:
        try:
            mail.uid("store", uid, "+FLAGS", "\\Deleted")
            success += 1
        except Exception as e:
            log.warning(f"删除 uid={uid} 失败：{e}")
    mail.expunge()
    return success


def imap_set_flag(mail, uid_list: list, flag: str, add: bool = True) -> int:
    """Add or remove an IMAP flag on uid_list. Returns count affected."""
    if not uid_list:
        return 0
    op = "+FLAGS" if add else "-FLAGS"
    success = 0
    for uid in uid_list:
        try:
            mail.uid("store", uid, op, flag)
            success += 1
        except Exception as e:
            log.warning(f"设置标记 {flag} uid={uid} 失败：{e}")
    return success


def push_templates_to_mailbox(mailbox: dict, lang: str = "zh") -> int:
    """通过 IMAP APPEND 将模板邮件写入邮箱专属文件夹，返回成功写入数量。"""
    templates = _TEMPLATES.get(lang, _TEMPLATES["zh"])
    folder = _FOLDER_NAMES.get(lang, "MailMindHub Templates")
    address = mailbox["address"]

    mail = imap_login(mailbox)
    try:
        # 创建文件夹（已存在则忽略错误）
        mail.create(folder)
    except Exception:
        pass

    # 清空旧模板（删除已有内容后重写）
    try:
        status, _ = mail.select(folder)
        if status == "OK":
            _, ids = mail.search(None, "ALL")
            for mid in ids[0].split():
                mail.store(mid, "+FLAGS", "\\Deleted")
            mail.expunge()
    except Exception:
        pass

    count = 0
    for subject, body in templates:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = address
        msg["To"] = address
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        raw = msg.as_bytes()
        try:
            result = mail.append(folder, "", imaplib.Time2Internaldate(time.time()), raw)
            if result[0] == "OK":
                count += 1
            else:
                log.warning(f"模板写入失败：{subject} → {result}")
        except Exception as e:
            log.warning(f"模板写入异常：{subject} → {e}")

    mail.logout()
    log.info(f"📋 已写入 {count}/{len(templates)} 个模板到文件夹「{folder}」")
    return count

def _oauth_google(mailbox: dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    SCOPES = ["https://www.googleapis.com/auth/gmail.imap", "https://mail.google.com/"]
    token_file, creds_file = mailbox["oauth_token_file"], mailbox["oauth_creds_file"]
    creds = Credentials.from_authorized_user_file(token_file, SCOPES) if os.path.exists(token_file) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print(f"\nGmail OAuth 授权链接：\n{auth_url}\n请输入 code:")
            flow.fetch_token(code=input(">>> ").strip())
            creds = flow.credentials
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return creds.token

def _oauth_microsoft(mailbox: dict) -> str:
    import msal
    client_id, token_file = mailbox.get("oauth_client_id"), mailbox["oauth_token_file"]
    SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All", "https://outlook.office.com/SMTP.Send", "offline_access"]
    cache = msal.SerializableTokenCache()
    if os.path.exists(token_file):
        cache.deserialize(open(token_file).read())
    app = msal.PublicClientApplication(client_id, authority="https://login.microsoftonline.com/common", token_cache=cache)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        print(f"\nOutlook OAuth 授权：{flow['verification_uri']} 代码：{flow['user_code']}")
        result = app.acquire_token_by_device_flow(flow)
    if cache.has_state_changed:
        with open(token_file, "w") as f:
            f.write(cache.serialize())
    return result["access_token"]

def get_oauth_token(mailbox: dict) -> str:
    auth = mailbox.get("auth", "password")
    if auth == "oauth_google":
        return _oauth_google(mailbox)
    if auth == "oauth_microsoft":
        return _oauth_microsoft(mailbox)
    return ""

def make_oauth_string(address: str, token: str) -> str:
    return base64.b64encode(f"user={address}\x01auth=Bearer {token}\x01\x01".encode()).decode()

def decode_str(s: str) -> str:
    if not s: return ""
    result = []
    for part, charset in _decode_header(s):
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)

def get_body_and_attachments(msg) -> tuple:
    max_bytes = ATTACHMENT_MAX_SIZE_MB * 1024 * 1024
    body, attachments = "", []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get_content_disposition() or "")
            if "attachment" in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    if len(payload) > max_bytes:
                        filename = decode_str(part.get_filename() or "untitled")
                        log.warning(f"附件 '{filename}' 超出大小限制 ({len(payload)//1024}KB > {ATTACHMENT_MAX_SIZE_MB}MB)，已跳过")
                        continue
                    is_text = part.get_content_type().startswith("text/")
                    content = payload.decode(part.get_content_charset() or "utf-8", errors="replace") if is_text else payload
                    attachments.append({"filename": decode_str(part.get_filename() or "untitled"), "content": content, "is_text": is_text})
            elif part.get_content_type() == "text/plain" and not body and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()
    return body, attachments

def imap_login(mailbox: dict):
    mail = imaplib.IMAP4_SSL(mailbox["imap_server"], mailbox["imap_port"], timeout=15)
    if mailbox.get("imap_id"):
        try:
            mail.xatom("ID", '("name" "mailmind" "version" "1.0")')
        except Exception:
            pass
    auth = mailbox.get("auth", "password")
    if auth == "password":
        mail.login(mailbox["address"], mailbox["password"])
    else:
        token = get_oauth_token(mailbox)
        mail.authenticate("XOAUTH2", lambda x: make_oauth_string(mailbox["address"], token))
    return mail

def is_sender_allowed(sender_email: str, allowed: list) -> bool:
    if not allowed: return True
    sender_email = (sender_email or "").strip().lower()
    if "@" not in sender_email: return False
    _, _, sender_domain = sender_email.rpartition("@")
    for entry in allowed:
        rule = (entry or "").strip().lower()
        if not rule: continue
        if "@" in rule and not rule.startswith("@"):
            if sender_email == rule: return True
        else:
            if rule.startswith("@"): rule = rule[1:]
            if sender_domain == rule: return True
    return False

def fetch_unread_emails(mailbox: dict, processed_ids: set):
    mail = imap_login(mailbox)
    allowed = mailbox.get("allowed_senders", [])
    emails = []

    def _fetch_folder(folder: str, id_prefix: str = ""):
        try:
            status, _ = mail.select(folder)
            if status != "OK":
                return
        except Exception:
            return
        _, ids = mail.uid("search", None, "UNSEEN")
        for uid in ids[0].split():
            eid = id_prefix + uid.decode()
            if eid in processed_ids:
                continue
            _, data = mail.uid("fetch", uid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            sender = decode_str(msg.get("From", ""))
            sender_email = parseaddr(sender)[1].strip()
            if not is_sender_allowed(sender_email, allowed):
                continue
            if id_prefix:
                try:
                    mail.uid("copy", uid, "INBOX")
                    mail.uid("store", uid, "+FLAGS", "\\Deleted")
                    mail.expunge()
                    log.info(f"📥 垃圾邮件移入収件箱: {sender_email}")
                except Exception as e:
                    log.warning(f"移动垃圾邮件失败: {e}")
            body, atts = get_body_and_attachments(msg)
            
            # Extract headers for conversation context
            message_id = msg.get("Message-ID", "")
            in_reply_to = msg.get("In-Reply-To", "")
            references = msg.get("References", "")
            
            emails.append({
                "id": eid, 
                "from": sender, 
                "from_email": sender_email,
                "subject": decode_str(msg.get("Subject", "(无主题)")),
                "message_id": message_id, 
                "in_reply_to": in_reply_to,
                "references": references,
                "body": body, 
                "attachments": atts
            })

    _fetch_folder("INBOX")
    spam_folder = mailbox.get("spam_folder", "")
    if spam_folder:
        _fetch_folder(spam_folder, id_prefix="spam:")

    mail.logout()
    return emails

def fetch_message_content_by_id(mailbox: dict, message_id: str) -> str:
    """根据 Message-ID 获取邮件正文"""
    if not message_id: return ""
    mail = imap_login(mailbox)
    content = ""
    try:
        for folder in ["INBOX", '"[Gmail]/Sent Mail"', "Sent"]:
            try:
                status, _ = mail.select(folder, readonly=True)
                if status != "OK": continue
                _, data = mail.search(None, f'HEADER Message-ID "{message_id}"')
                ids = data[0].split()
                if ids:
                    _, msg_data = mail.fetch(ids[0], "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])
                    body, _ = get_body_and_attachments(msg)
                    content = body
                    break
            except Exception:
                continue
    finally:
        mail.logout()
    return content

def fetch_thread_context(mailbox: dict, references: str, in_reply_to: str = "", max_depth: int = None) -> str:
    """获取完整会话线索（多层上下文），复用单次 IMAP 连接"""
    if max_depth is None:
        max_depth = CONTEXT_MAX_DEPTH

    # Collect all referenced message IDs (References header is space-separated)
    ref_ids: list[str] = []
    if references:
        ref_ids = [mid.strip() for mid in references.split() if mid.strip()]
    if in_reply_to and in_reply_to.strip() and in_reply_to.strip() not in ref_ids:
        ref_ids.append(in_reply_to.strip())
    if not ref_ids:
        return ""

    # Take the most recent max_depth IDs; preserve original order for output
    ref_ids = ref_ids[-max_depth:]
    needed = set(ref_ids)
    results: dict[str, str] = {}

    try:
        mail = imap_login(mailbox)
        for folder in ["INBOX", '"[Gmail]/Sent Mail"', "Sent", '"Sent Messages"']:
            remaining = needed - set(results.keys())
            if not remaining:
                break
            try:
                status, _ = mail.select(folder, readonly=True)
                if status != "OK":
                    continue
                for mid in list(remaining):
                    try:
                        _, data = mail.search(None, f'HEADER Message-ID "{mid}"')
                        ids = data[0].split()
                        if ids:
                            _, msg_data = mail.fetch(ids[0], "(RFC822)")
                            msg = email.message_from_bytes(msg_data[0][1])
                            body, _ = get_body_and_attachments(msg)
                            if body:
                                results[mid] = body
                    except Exception:
                        continue
            except Exception:
                continue
        mail.logout()
    except Exception as e:
        log.warning(f"获取会话上下文失败: {e}")

    if not results:
        return ""

    parts = [results[mid] for mid in ref_ids if mid in results]
    return "\n\n---\n\n".join(parts)

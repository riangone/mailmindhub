"""
ticket skill — Support ticket management via external APIs or AI formatting.

Supported platforms (via env vars):
  GitHub Issues  — GITHUB_TOKEN
  Jira           — JIRA_BASE_URL + JIRA_EMAIL + JIRA_API_TOKEN
  Linear         — LINEAR_API_KEY

Supported actions:
  create  — Create a new ticket
  list    — List recent tickets
  update  — Update ticket status/comment
  close   — Close a ticket

Falls back to AI-formatted ticket summary when no platform is configured.
"""

import os
import json
import requests
from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider

_GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
_JIRA_BASE       = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
_JIRA_EMAIL      = os.environ.get("JIRA_EMAIL", "")
_JIRA_TOKEN      = os.environ.get("JIRA_API_TOKEN", "")
_LINEAR_KEY      = os.environ.get("LINEAR_API_KEY", "")


class TicketSkill(BaseSkill):
    name = "ticket"
    description = "创建或查询支持工单（GitHub Issues / Jira / Linear）"
    description_ja = "サポートチケットの作成・照会（GitHub Issues / Jira / Linear）"
    description_en = "Create or query support tickets (GitHub Issues / Jira / Linear)"
    keywords = ["工单", "ticket", "issue", "bug report", "チケット", "jira", "linear", "support", "故障", "缺陷"]

    def run(self, payload: dict, ai_caller=None) -> str:
        platform = (payload.get("platform") or _detect_platform()).lower()
        action   = payload.get("action", "create")

        if platform == "github":
            return _github_action(payload, action)
        elif platform == "jira":
            return _jira_action(payload, action)
        elif platform == "linear":
            return _linear_action(payload, action)
        else:
            # No platform configured — use AI to format a ticket
            return _ai_format_ticket(payload)


def _detect_platform() -> str:
    if _GITHUB_TOKEN:
        return "github"
    if _JIRA_BASE and _JIRA_TOKEN:
        return "jira"
    if _LINEAR_KEY:
        return "linear"
    return "none"


# ── GitHub ──────────────────────────────────────────────────────────────────

def _gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {_GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_action(payload: dict, action: str) -> str:
    repo = payload.get("repo", "")
    if not repo:
        return "⚠️ GitHub platform 需要 repo（格式：owner/repo）"

    if action == "create":
        title  = payload.get("title", "")
        body   = payload.get("body") or payload.get("description", "")
        labels = payload.get("labels", [])
        if not title:
            return "⚠️ 请提供 title"
        try:
            r = requests.post(
                f"https://api.github.com/repos/{repo}/issues",
                headers=_gh_headers(),
                json={"title": title, "body": body, "labels": labels},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            return f"✅ Issue 已创建：#{data['number']} {data['title']}\n{data['html_url']}"
        except Exception as e:
            return f"❌ 创建失败：{e}"

    elif action == "list":
        try:
            r = requests.get(
                f"https://api.github.com/repos/{repo}/issues",
                headers=_gh_headers(),
                params={"state": payload.get("state", "open"), "per_page": 15},
                timeout=15,
            )
            r.raise_for_status()
            issues = [i for i in r.json() if "pull_request" not in i]
            if not issues:
                return f"📭 {repo} 没有开放的 Issue。"
            lines = [f"🐛 {repo} Issues（{len(issues)} 个）："]
            for i in issues[:10]:
                lines.append(f"  #{i['number']} {i['title']}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 获取失败：{e}"

    elif action in ("close", "update"):
        number = payload.get("number") or payload.get("issue_number")
        if not number:
            return "⚠️ 请提供 number（Issue 编号）"
        update_data = {}
        if action == "close":
            update_data["state"] = "closed"
        if payload.get("comment"):
            try:
                requests.post(
                    f"https://api.github.com/repos/{repo}/issues/{number}/comments",
                    headers=_gh_headers(),
                    json={"body": payload["comment"]},
                    timeout=15,
                )
            except Exception:
                pass
        if update_data:
            try:
                r = requests.patch(
                    f"https://api.github.com/repos/{repo}/issues/{number}",
                    headers=_gh_headers(),
                    json=update_data,
                    timeout=15,
                )
                r.raise_for_status()
                return f"✅ Issue #{number} 已更新。"
            except Exception as e:
                return f"❌ 更新失败：{e}"
        return f"✅ Issue #{number} 已处理。"

    return f"⚠️ 未知 action：{action}"


# ── Jira ─────────────────────────────────────────────────────────────────────

def _jira_action(payload: dict, action: str) -> str:
    if not (_JIRA_BASE and _JIRA_EMAIL and _JIRA_TOKEN):
        return "⚠️ Jira 未配置。请设置 JIRA_BASE_URL、JIRA_EMAIL、JIRA_API_TOKEN"

    auth = (_JIRA_EMAIL, _JIRA_TOKEN)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    if action == "create":
        project = payload.get("project", "")
        title   = payload.get("title", "")
        body    = payload.get("body") or payload.get("description", "")
        if not project or not title:
            return "⚠️ 请提供 project（Jira 项目键）和 title"
        try:
            r = requests.post(
                f"{_JIRA_BASE}/rest/api/3/issue",
                auth=auth, headers=headers,
                json={
                    "fields": {
                        "project": {"key": project},
                        "summary": title,
                        "description": {"type": "doc", "version": 1, "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": body}]}
                        ]},
                        "issuetype": {"name": payload.get("issue_type", "Task")},
                    }
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            key = data.get("key", "?")
            return f"✅ Jira Issue 已创建：{key}\n{_JIRA_BASE}/browse/{key}"
        except Exception as e:
            return f"❌ 创建失败：{e}"

    elif action == "list":
        project = payload.get("project", "")
        jql     = payload.get("jql") or (f"project={project} AND status!=Done ORDER BY created DESC" if project else "assignee=currentUser() AND status!=Done ORDER BY created DESC")
        try:
            r = requests.get(
                f"{_JIRA_BASE}/rest/api/3/search",
                auth=auth, headers=headers,
                params={"jql": jql, "maxResults": 10},
                timeout=15,
            )
            r.raise_for_status()
            issues = r.json().get("issues", [])
            if not issues:
                return "📭 没有找到匹配的 Jira Issue。"
            lines = [f"🎫 Jira Issues（{len(issues)} 个）："]
            for i in issues:
                lines.append(f"  {i['key']} {i['fields']['summary']}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 查询失败：{e}"

    return f"⚠️ 未知 action：{action}"


# ── Linear ────────────────────────────────────────────────────────────────────

def _linear_action(payload: dict, action: str) -> str:
    if not _LINEAR_KEY:
        return "⚠️ LINEAR_API_KEY 未设置"

    headers = {"Authorization": _LINEAR_KEY, "Content-Type": "application/json"}

    if action == "create":
        title = payload.get("title", "")
        body  = payload.get("body") or payload.get("description", "")
        team  = payload.get("team", "")
        if not title:
            return "⚠️ 请提供 title"
        query = """
        mutation IssueCreate($title: String!, $description: String, $teamId: String!) {
          issueCreate(input: {title: $title, description: $description, teamId: $teamId}) {
            success
            issue { id title url }
          }
        }
        """
        try:
            r = requests.post(
                "https://api.linear.app/graphql",
                headers=headers,
                json={"query": query, "variables": {"title": title, "description": body, "teamId": team}},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            issue = data.get("data", {}).get("issueCreate", {}).get("issue", {})
            if issue:
                return f"✅ Linear Issue 已创建：{issue['title']}\n{issue['url']}"
            return f"❌ 创建失败：{json.dumps(data)}"
        except Exception as e:
            return f"❌ 创建失败：{e}"

    return f"⚠️ 未知 action：{action}"


# ── AI fallback ──────────────────────────────────────────────────────────────

def _ai_format_ticket(payload: dict) -> str:
    ai_name, backend = pick_task_ai(payload)
    ai = get_ai_provider(ai_name, backend)
    title = payload.get("title", "")
    body  = payload.get("body") or payload.get("description", "")
    prompt = f"""请将以下问题整理为标准工单格式（Markdown）：

标题：{title}
描述：{body}

输出包含：摘要、问题现象、复现步骤、期望行为、优先级建议。"""
    result = ai.call(prompt)
    prefix = "（未配置工单平台 — 以下为 AI 格式化工单）\n\n"
    return prefix + (result or "⚠️ AI 无响应。")


SKILL = TicketSkill()

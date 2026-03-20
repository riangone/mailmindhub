"""
github skill — GitHub operations via REST API v3.

Supported actions:
  list_prs      — List open pull requests in a repo
  list_issues   — List open issues in a repo
  create_issue  — Create a new issue
  get_repo      — Get repository info and recent commits
  search_code   — Search code in a repo

Environment:
  GITHUB_TOKEN  — Personal access token (required)
"""

import os
import json
import requests
from skills import BaseSkill

_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
_API_BASE = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if _GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {_GITHUB_TOKEN}"
    return h


def _get(path: str, params: dict = None) -> dict | list | None:
    try:
        r = requests.get(f"{_API_BASE}{path}", headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _post(path: str, data: dict) -> dict:
    try:
        r = requests.post(f"{_API_BASE}{path}", headers=_headers(), json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


class GitHubSkill(BaseSkill):
    name = "github"
    description = "GitHub 操作：列出 PR/Issue、创建 Issue、查看仓库状态、搜索代码"
    description_ja = "GitHub 操作：PR/Issue 一覧・Issue 作成・リポジトリ状態確認・コード検索"
    description_en = "GitHub operations: list PRs/issues, create issues, repo status, code search"
    keywords = ["github", "pull request", "PR", "issue", "repository", "repo", "commit", "コード検索"]

    def run(self, payload: dict, ai_caller=None) -> str:
        if not _GITHUB_TOKEN:
            return "⚠️ GITHUB_TOKEN 未设置。请在 .env 中添加 GITHUB_TOKEN=ghp_xxx"

        action = payload.get("action", "list_prs")
        repo   = payload.get("repo", "")  # owner/repo format

        if action == "list_prs":
            if not repo:
                return "⚠️ 请提供 repo（格式：owner/repo）"
            data = _get(f"/repos/{repo}/pulls", {"state": payload.get("state", "open"), "per_page": 20})
            if isinstance(data, list):
                if not data:
                    return f"📭 {repo} 没有开放的 PR。"
                lines = [f"📋 {repo} 的开放 PR（共 {len(data)} 个）：\n"]
                for pr in data[:10]:
                    lines.append(f"  #{pr['number']} {pr['title']} (@{pr['user']['login']})")
                return "\n".join(lines)
            return json.dumps(data, ensure_ascii=False)

        elif action == "list_issues":
            if not repo:
                return "⚠️ 请提供 repo（格式：owner/repo）"
            data = _get(f"/repos/{repo}/issues", {
                "state": payload.get("state", "open"),
                "per_page": 20,
                "labels": payload.get("labels", ""),
            })
            if isinstance(data, list):
                issues = [i for i in data if "pull_request" not in i]
                if not issues:
                    return f"📭 {repo} 没有开放的 Issue。"
                lines = [f"🐛 {repo} 的开放 Issue（共 {len(issues)} 个）：\n"]
                for iss in issues[:10]:
                    labels = ", ".join(l["name"] for l in iss.get("labels", []))
                    label_str = f" [{labels}]" if labels else ""
                    lines.append(f"  #{iss['number']} {iss['title']}{label_str}")
                return "\n".join(lines)
            return json.dumps(data, ensure_ascii=False)

        elif action == "create_issue":
            if not repo:
                return "⚠️ 请提供 repo（格式：owner/repo）"
            title = payload.get("title", "")
            body  = payload.get("body", "")
            if not title:
                return "⚠️ 请提供 title 字段"
            data = _post(f"/repos/{repo}/issues", {
                "title": title,
                "body": body,
                "labels": payload.get("labels", []),
            })
            if "error" in data:
                return f"❌ 创建 Issue 失败：{data['error']}"
            return f"✅ Issue 已创建：{data.get('html_url', '')}\n#{data['number']} {data['title']}"

        elif action == "get_repo":
            if not repo:
                return "⚠️ 请提供 repo（格式：owner/repo）"
            info = _get(f"/repos/{repo}")
            commits = _get(f"/repos/{repo}/commits", {"per_page": 5})
            if "error" in info:
                return f"❌ 获取仓库信息失败：{info['error']}"
            lines = [
                f"📦 {info['full_name']}",
                f"  描述：{info.get('description', '—')}",
                f"  Stars: {info.get('stargazers_count', 0)}  Forks: {info.get('forks_count', 0)}",
                f"  默认分支：{info.get('default_branch', 'main')}",
                f"  语言：{info.get('language', '—')}",
                "",
            ]
            if isinstance(commits, list):
                lines.append("最近提交：")
                for c in commits[:5]:
                    msg = c["commit"]["message"].split("\n")[0][:60]
                    author = c["commit"]["author"]["name"]
                    lines.append(f"  • {msg} ({author})")
            return "\n".join(lines)

        elif action == "search_code":
            query = payload.get("query", "")
            if not query:
                return "⚠️ 请提供 query 字段"
            if repo:
                query = f"{query} repo:{repo}"
            data = _get("/search/code", {"q": query, "per_page": 10})
            if isinstance(data, dict) and "items" in data:
                items = data["items"]
                if not items:
                    return f"🔍 未找到匹配代码：{query}"
                lines = [f"🔍 代码搜索结果（{data['total_count']} 个匹配）：\n"]
                for item in items[:8]:
                    lines.append(f"  {item['repository']['full_name']} → {item['path']}")
                return "\n".join(lines)
            return json.dumps(data, ensure_ascii=False)

        else:
            return f"⚠️ 未知 action：{action}。支持：list_prs / list_issues / create_issue / get_repo / search_code"


SKILL = GitHubSkill()

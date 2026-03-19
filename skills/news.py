"""
News Skill — 新闻搜索与摘要

支持多种执行方式（优先级从高到低）:
1. AI 原生搜索（如果 AI 支持 native_web_search）
2. NewsAPI（如果配置了 API Key）
3. 网页搜索（本地搜索引擎）
"""

from skills import BaseSkill
from ai.skills import execute_ai_skill, fetch_news_via_api, format_news_result, fetch_news_via_search
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider
from core.config import SEARCH_RESULTS_COUNT, PROMPT_LANG


class NewsSkill(BaseSkill):
    name = "news"
    description = "新闻搜索与摘要"
    description_ja = "ニュース検索と要約"
    description_en = "News search and summarization"
    keywords = ["新闻", "新闻摘要", "news", "ニュース", "뉴스", "资讯"]

    def run(self, payload: dict, ai_caller=None) -> str:
        q = payload.get("query") or "最新的新闻"
        lang = payload.get("lang", PROMPT_LANG)
        
        # 获取 AI 后端配置
        ai_name, backend = pick_task_ai(payload)
        ai = ai_caller or get_ai_provider(ai_name, backend)
        
        # 1. 优先使用 AI 原生搜索（如果 AI 支持）
        if backend.get("native_web_search"):
            prompt = f"请搜索并总结关于以下主题的最新新闻：{q}。重要提示：必须在回复中包含每条新闻的原始链接（URL），不要删减链接信息。"
            result = ai.call(prompt)
            if result:
                return result
        
        # 2. 尝试 NewsAPI
        articles = fetch_news_via_api(q, lang)
        if articles:
            search_ctx = format_news_result(articles, lang)
            prompt = f"以下是关于「{q}」的新闻搜索结果，请将其整理为新闻摘要，按重要性排列，保留并完整显示每条的原始链接（URL）。\n\n{search_ctx}"
            return ai.call(prompt) or "⚠️ 新闻获取失败。"
        
        # 3. 尝试网页搜索
        results = fetch_news_via_search(q, SEARCH_RESULTS_COUNT)
        if results:
            search_ctx = format_news_result(results, lang)
            prompt = f"以下是关于「{q}」的网络搜索结果，请将其整理为新闻摘要，按重要性排列，保留并完整显示每条的原始链接（URL）。\n\n{search_ctx}"
            return ai.call(prompt) or "⚠️ 新闻获取失败。"
        
        return "⚠️ 新闻获取失败。"


SKILL = NewsSkill()

"""
Stock Skill — 股票/加密货币行情查询

支持多种执行方式（优先级从高到低）:
1. AI 原生搜索（如果 AI 支持 native_web_search）
2. 网页搜索获取实时行情
"""

from skills import BaseSkill
from ai.skills import execute_ai_skill, fetch_stock_via_search, format_stock_result
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider
from core.config import SEARCH_RESULTS_COUNT, PROMPT_LANG


class StockSkill(BaseSkill):
    name = "stock"
    description = "查询股票/加密货币行情及分析"
    description_ja = "株価・暗号通貨の相場照会と分析"
    description_en = "Look up stock/crypto prices and market analysis"
    keywords = ["股票", "股市", "行情", "stock", "stocks", "crypto", "bitcoin", "加密货币", "株価", "相場", "주식", "코인"]

    def run(self, payload: dict, ai_caller=None) -> str:
        query = payload.get("query") or payload.get("symbol") or payload.get("prompt") or ""
        if not query:
            return "⚠️ 请在 task_payload 中提供 query（股票名称/代码）字段。"
        
        lang = payload.get("lang", PROMPT_LANG)
        
        # 获取 AI 后端配置
        ai_name, backend = pick_task_ai(payload)
        ai = ai_caller or get_ai_provider(ai_name, backend)
        
        # 1. 优先使用 AI 原生搜索（如果 AI 支持）
        if backend.get("native_web_search"):
            prompt = f"请搜索并报告 {query} 的最新股价/行情，包括今日涨跌幅，重要：请提供数据来源链接。"
            result = ai.call(prompt)
            if result:
                return result
        
        # 2. 尝试网页搜索
        results = fetch_stock_via_search(query, SEARCH_RESULTS_COUNT)
        if results:
            ctx = format_stock_result(results, lang)
            prompt = f"根据以下搜索结果，整理 {query} 的最新行情：\n\n{ctx}"
            return ai.call(prompt) or "⚠️ 查询失败。"
        
        return "⚠️ 查询失败。"


SKILL = StockSkill()

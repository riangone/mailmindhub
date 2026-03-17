from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider
from utils.search import web_search, format_search_results
from core.config import SEARCH_RESULTS_COUNT


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
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        if backend.get("native_web_search"):
            prompt = f"请搜索并报告 {query} 的最新股价/行情，包括今日涨跌幅，重要：请提供数据来源链接。"
            return ai.call(prompt) or "⚠️ 查询失败。"
        results = web_search(f"{query} stock price today", SEARCH_RESULTS_COUNT)
        if results:
            ctx = format_search_results(results)
            prompt = f"根据以下搜索结果，整理 {query} 的最新行情：\n\n{ctx}"
        else:
            prompt = f"请告诉我 {query} 的最新股价/行情信息，包括今日涨跌幅。"
        return ai.call(prompt) or "⚠️ 查询失败。"


SKILL = StockSkill()

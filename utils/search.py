import os
import requests
import logging
from typing import Optional
from core.config import WEB_SEARCH_ENGINE, WEB_SEARCH_TIMEOUT, BRAVE_API_KEY, SEARCH_RESULTS_COUNT
from utils.logger import log

def web_search(query: str, num_results: int = 5, engine: Optional[str] = None) -> list:
    from utils.cache import query_cache
    engine = (engine or WEB_SEARCH_ENGINE).lower().strip()
    cache_key = f"search:{engine}:{query}:{num_results}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        log.debug(f"[Cache] ヒット: {cache_key[:60]}")
        return cached

    results = []

    if engine == "brave":
        if not BRAVE_API_KEY:
            log.warning("Brave Search: 未配置 BRAVE_API_KEY")
            return results
        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {"X-Subscription-Token": BRAVE_API_KEY, "Accept": "application/json"}
            params = {"q": query, "count": num_results, "text_decorations": False}
            resp = requests.get(url, headers=headers, params=params, timeout=WEB_SEARCH_TIMEOUT)
            resp.raise_for_status()
            for item in resp.json().get("web", {}).get("results", [])[:num_results]:
                results.append({"title": item.get("title", ""), "snippet": item.get("description", ""), "url": item.get("url", "")})
        except Exception as e:
            log.warning(f"Brave 搜索失败：{e}")

    elif engine == "duckduckgo":
        try:
            from ddgs import DDGS
            with DDGS() as ddgs_client:
                for item in ddgs_client.text(query, max_results=num_results):
                    results.append({"title": item.get("title", ""), "snippet": item.get("body", ""), "url": item.get("href", "")})
        except ImportError:
            log.warning("DuckDuckGo 搜索：未安装 ddgs，请运行 pip install ddgs")
        except Exception as e:
            log.warning(f"DuckDuckGo 搜索失败：{e}")

    elif engine == "wikipedia":
        try:
            lang = os.environ.get("WIKIPEDIA_LANG", "zh")
            params = {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": num_results}
            resp = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params=params, headers={"User-Agent": "MailMindHub/1.0"}, timeout=WEB_SEARCH_TIMEOUT)
            for item in resp.json().get("query", {}).get("search", [])[:num_results]:
                results.append({"title": item.get("title", ""), "snippet": item.get("snippet", "").replace('<span class="searchmatch">', "").replace("</span>", ""), "url": f"https://{lang}.wikipedia.org/wiki/{item.get('title', '')}"})
        except Exception as e:
            log.warning(f"Wikipedia 搜索失败：{e}")

    elif engine == "google":
        log.warning("Google 爬虫搜索已禁用，请使用 DuckDuckGo 或其他引擎")

    elif engine == "bing":
        api_key = os.environ.get("BING_API_KEY", "")
        if api_key:
            try:
                resp = requests.get(f"https://api.bing.microsoft.com/v7.0/search?q={requests.utils.quote(query)}", headers={"Ocp-Apim-Subscription-Key": api_key}, timeout=WEB_SEARCH_TIMEOUT)
                resp.raise_for_status()
                for item in resp.json().get("webPages", {}).get("value", [])[:num_results]:
                    results.append({"title": item.get("name", ""), "snippet": item.get("snippet", ""), "url": item.get("url", "")})
            except Exception as e:
                log.warning(f"Bing 搜索失败：{e}")

    elif engine == "google_api":
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        cse_id = os.environ.get("GOOGLE_CSE_ID", "")
        if not api_key or not cse_id:
            log.warning("Google API 搜索：未配置 GOOGLE_API_KEY 或 GOOGLE_CSE_ID")
        else:
            try:
                resp = requests.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"key": api_key, "cx": cse_id, "q": query, "num": min(num_results, 10)},
                    timeout=WEB_SEARCH_TIMEOUT,
                )
                resp.raise_for_status()
                for item in resp.json().get("items", [])[:num_results]:
                    results.append({"title": item.get("title", ""), "snippet": item.get("snippet", ""), "url": item.get("link", "")})
            except Exception as e:
                log.warning(f"Google API 搜索失败：{e}")

    if results:
        query_cache.set(cache_key, results)
    return results

def format_search_results(results: list) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. 【{r.get('title', '无标题')}】\n   {r.get('snippet', '')}\n   🔗 链接: {r.get('url', '')}\n")
    return "\n".join(lines)

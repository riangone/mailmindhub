import os
import requests
import logging
from typing import Optional
from core.config import WEB_SEARCH_ENGINE, WEB_SEARCH_TIMEOUT, BRAVE_API_KEY, SEARCH_RESULTS_COUNT
from utils.logger import log

def web_search(query: str, num_results: int = 5, engine: Optional[str] = None) -> list:
    results = []
    engine = (engine or WEB_SEARCH_ENGINE).lower().strip()

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
        google_ok = False
        try:
            from googlesearch import search as google_search
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            urls = list(google_search(query, num_results=num_results, lang="zh-CN"))
            for url in urls:
                try:
                    resp = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
                    title, snippet = url, ""
                    if resp.ok and "text/html" in resp.headers.get("Content-Type", ""):
                        import re as _re
                        m_title = _re.search(r"<title[^>]*>([^<]{1,200})</title>", resp.text, _re.I)
                        if m_title:
                            title = m_title.group(1).strip()
                        m_desc = _re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{1,300})', resp.text, _re.I)
                        if not m_desc:
                            m_desc = _re.search(r'<meta[^>]+content=["\']([^"\']{1,300})[^>]+name=["\']description["\']', resp.text, _re.I)
                        if m_desc:
                            snippet = m_desc.group(1).strip()
                except Exception:
                    title, snippet = url, ""
                results.append({"title": title, "snippet": snippet, "url": url})
            google_ok = bool(results)
        except ImportError:
            log.warning("Google 搜索：未安装 googlesearch-python，请运行 pip install googlesearch-python")
        except Exception as e:
            log.warning(f"Google 爬虫搜索失败（{e}），自动回退至 DuckDuckGo")
        if not google_ok:
            try:
                from ddgs import DDGS
                with DDGS() as ddgs_client:
                    for item in ddgs_client.text(query, max_results=num_results):
                        results.append({"title": item.get("title", ""), "snippet": item.get("body", ""), "url": item.get("href", "")})
                if results:
                    log.info("Google 不可用，已使用 DuckDuckGo 替代")
            except Exception as e2:
                log.warning(f"DuckDuckGo 回退也失败：{e2}")

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

    return results

def format_search_results(results: list) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. 【{r.get('title', '无标题')}】\n   {r.get('snippet', '')}\n   🔗 链接: {r.get('url', '')}\n")
    return "\n".join(lines)

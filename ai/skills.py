def get_ai_skills_prompt(lang: str = "zh") -> str:
    """生成 AI Skill 调用提示词"""
    if lang == "ja":
        return """
## 利用可能な AI スキル
以下の形式でスキルを呼び出すことができます：
1. task_type="ai_skill", task_payload={"skill": "スキル名", "payload": {...}}
2. 直接スキル名を task_type として使用: task_type="スキル名", task_payload={...}

スキル一覧：
- **weather**: 天気予報と確認（MCP/WeatherAPI/ウェブ検索対応）
- **news**: ニュース検索と要約（NewsAPI/ウェブ検索/AIネイティブ検索対応）
- **stock**: 株価/仮想通貨のレート確認と分析（ウェブ検索対応）
- **web_search**: ウェブ検索（MCP/ローカル検索エンジン対応）
- **news_briefing**: 統一されたMarkdown形式のニュースブリーフィング生成
"""
    elif lang == "en":
        return """
## Available AI Skills
You can call skills in the following ways:
1. task_type="ai_skill", task_payload={"skill": "skill_name", "payload": {...}}
2. Use skill name as task_type directly: task_type="skill_name", task_payload={...}

Skill List:
- **weather**: Weather forecast and query (Supports MCP/WeatherAPI/Web Search)
- **news**: News search and summary (Supports NewsAPI/Web Search/AI Native Search)
- **stock**: Stock/Crypto market query and analysis (Supports Web Search)
- **web_search**: Web search (Supports MCP/Local Search Engines)
- **news_briefing**: Generate unified Markdown news briefings
"""
    elif lang == "ko":
        return """
## 사용 가능한 AI 스킬
다음과 같은 방식으로 스킬을 호출할 수 있습니다:
1. task_type="ai_skill", task_payload={"skill": "스킬명", "payload": {...}}
2. 스킬명을 직접 task_type으로 사용: task_type="스킬명", task_payload={...}

스킬 목록:
- **weather**: 날씨 조회 및 예보 (MCP/WeatherAPI/웹 검색 지원)
- **news**: 뉴스 검색 및 요약 (NewsAPI/웹 검색/AI 네이티브 검색 지원)
- **stock**: 주식/암호화폐 시세 조회 및 분석 (웹 검색 지원)
- **web_search**: 웹 검색 (MCP/로컬 검색 엔진 지원)
- **news_briefing**: 통일된 Markdown 형식의 뉴스 브리핑 생성
"""
    else:
        return """
## 可用 AI 技能
你可以通过以下方式调用技能：
1. task_type="ai_skill", task_payload={"skill": "技能名", "payload": {...}}
2. 直接使用技能名作为 task_type: task_type="技能名", task_payload={...}

技能列表：
- **weather**: 天气查询与播报（支持 MCP/WeatherAPI/网络搜索）
- **news**: 新闻搜索与摘要（支持 NewsAPI/网页搜索/AI 原生搜索）
- **stock**: 查询股票/加密货币行情及分析（支持网页搜索/AI 原生搜索）
- **web_search**: 网页搜索（支持 MCP/本地搜索引擎）
- **news_briefing**: 生成统一格式的 Markdown 新闻简报
"""


def list_ai_skills():
    """返回已注册的 AI 技能列表"""
    return [
        {"name": "weather", "description": "天气查询"},
        {"name": "news", "description": "新闻搜索"},
        {"name": "stock", "description": "股票查询"},
        {"name": "web_search", "description": "网页搜索"},
        {"name": "news_briefing", "description": "新闻简报"},
    ]

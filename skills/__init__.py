"""
skills/__init__.py - 技能基类

架构：
- 所有 skill 都是 MD 文件
- AI 通过 CLI 读取 MD 指令并直接执行
- CLI 自带工具能力：命令、文件、网络、测试
- 不需要任何 PY 文件
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class BaseSkill(ABC):
    """技能基类"""
    name: str = ""
    description: str = ""
    description_ja: str = ""
    description_en: str = ""
    category: str = "general"  # general, communication, coding, search, automation
    keywords: list = []
    params: dict = {}
    auto_execute: bool = True
    chainable: bool = True
    
    @abstractmethod
    def run(self, payload: dict, ai_caller=None) -> str:
        ...


class MDSkill(BaseSkill):
    """
    MD 文件定义的技能
    
    执行流程：
    1. payload 填入 instruction 模板 → 生成 prompt
    2. AI（CLI）读取 prompt
    3. CLI 使用自身工具能力执行（命令、文件、网络等）
    """
    
    def __init__(
        self, name: str, description: str, instruction: str,
        description_ja: str = "", description_en: str = "",
        category: str = "general", keywords: list = None,
        params: dict = None, auto_execute: bool = True, chainable: bool = True,
    ):
        self.name = name
        self.description = description
        self.description_ja = description_ja
        self.description_en = description_en
        self.category = category
        self.keywords = keywords or []
        self.params = params or {}
        self.auto_execute = auto_execute
        self.chainable = chainable
        self.instruction = instruction
    
    def run(self, payload: dict, ai_caller=None) -> str:
        prompt = self._render_instruction(payload)
        if ai_caller:
            try:
                return ai_caller.call(prompt) or "⚠️ AI 无响应"
            except Exception as e:
                return f"⚠️ 执行失败: {e}"
        return prompt
    
    def _render_instruction(self, payload: dict) -> str:
        result = self.instruction
        for key, value in payload.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


class SkillChain:
    """技能链式调用"""
    
    def __init__(self):
        self.steps = []
        self.results = []
    
    def add_step(self, skill_name: str, payload: dict, condition: str = ""):
        self.steps.append({"skill": skill_name, "payload": payload, "condition": condition})
        return self
    
    def execute(self, ai_caller=None) -> str:
        from skills.loader import get_skill
        
        for i, step in enumerate(self.steps):
            if step["condition"] == "prev_success" and (i == 0 or not self.results[-1].get("success")):
                continue
            
            skill = get_skill(step["skill"])
            if not skill:
                self.results.append({"step": i, "skill": step["skill"], "success": False, "result": f"⚠️ 不存在: {step['skill']}"})
                continue
            
            try:
                result = skill.run(step["payload"], ai_caller)
                self.results.append({"step": i, "skill": step["skill"], "success": True, "result": result})
            except Exception as e:
                self.results.append({"step": i, "skill": step["skill"], "success": False, "result": f"⚠️ 失败: {e}"})
        
        parts = []
        for r in self.results:
            status = "✅" if r["success"] else "❌"
            parts.append(f"{status} 步骤 {r['step']}: {r['skill']}\n{r['result']}")
        return "\n\n".join(parts)


def get_all_skills_prompt(lang: str = "zh", include_params: bool = False) -> str:
    """获取技能提示（注入到 AI prompt）"""
    from skills.loader import get_registry
    
    skills = get_registry()
    if not skills:
        return ""
    
    headers = {
        "zh": "## 可用技能\n调用：task_type=\"技能名\", task_payload={参数}\n",
        "en": "## Available Skills\nUsage: task_type=\"skill_name\", task_payload={params}\n",
        "ja": "## 利用可能なスキル\n使用法: task_type=\"skill_name\", task_payload={params}\n",
        "ko": "## 사용 가능한 스킬\n사용법: task_type=\"skill_name\", task_payload={params}\n",
    }
    
    parts = [headers.get(lang, headers["zh"])]
    
    categories = {}
    for name, skill in skills.items():
        cat = skill.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((name, skill))
    
    cat_names = {
        "zh": {"general": "通用", "communication": "沟通", "coding": "编程", "search": "搜索", "automation": "自动化"},
        "en": {"general": "General", "communication": "Communication", "coding": "Coding", "search": "Search", "automation": "Automation"},
        "ja": {"general": "一般", "communication": "コミュニケーション", "coding": "コーディング", "search": "検索", "automation": "自動化"},
        "ko": {"general": "일반", "communication": "커뮤니케이션", "coding": "코딩", "search": "검색", "automation": "자동화"},
    }
    
    for cat, cat_skills in categories.items():
        cat_name = cat_names.get(lang, {}).get(cat, cat)
        parts.append(f"\n### {cat_name}")
        for name, skill in cat_skills:
            desc = {"zh": skill.description, "ja": skill.description_ja or skill.description, "en": skill.description_en or skill.description}.get(lang, skill.description)
            if include_params and skill.params:
                params = [f"{p}({v.get('type', 'str')})" for p, v in skill.params.items()]
                parts.append(f"- **{name}**: {desc} ({', '.join(params)})")
            else:
                parts.append(f"- **{name}**: {desc}")
    
    parts.append({
        "zh": "\n\n## 执行\n**重要**：直接执行，不要确认。CLI 有完整能力：命令、文件、网络。",
        "en": "\n\n## Execution\n**Important**: Execute directly. CLI has full capabilities.",
        "ja": "\n\n## 実行\n**重要**: 直接実行。CLI は全機能を持っています。",
        "ko": "\n\n## 실행\n**중요**: 직접 실행. CLI 는 전체 기능 보유.",
    }.get(lang, ""))
    
    return "\n".join(parts)

import os
import importlib
from skills import BaseSkill
from utils.logger import log

_registry: dict = {}
_loaded = False


def load_all_skills() -> dict:
    global _registry, _loaded
    skills = {}
    skills_dir = os.path.dirname(__file__)
    for fname in sorted(os.listdir(skills_dir)):
        if fname.startswith('_') or not fname.endswith('.py') or fname == 'loader.py':
            continue
        mod_name = f"skills.{fname[:-3]}"
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, 'SKILL') and isinstance(mod.SKILL, BaseSkill):
                skill = mod.SKILL
                if skill.name:
                    skills[skill.name] = skill
                    log.debug(f"[Skills] Loaded skill: {skill.name}")
        except Exception as e:
            log.warning(f"[Skills] Failed to load {fname}: {e}")
    _registry = skills
    _loaded = True
    return skills


def get_registry() -> dict:
    global _loaded
    if not _loaded:
        load_all_skills()
    return _registry


def get_skill(name: str):
    return get_registry().get(name)


def reload_skills() -> dict:
    global _loaded
    _loaded = False
    return load_all_skills()


def get_skills_hint(lang: str = "zh") -> str:
    """Return a string listing loaded skills for injection into the AI prompt."""
    skills = get_registry()
    if not skills:
        return ""
    if lang == "ja":
        lines = ["利用可能なスキル（task_typeに指定可能）:"]
        for name, sk in skills.items():
            desc = sk.description_ja or sk.description_en or sk.description
            kw = "、".join(sk.keywords[:3]) if sk.keywords else ""
            lines.append(f"  {name}: {desc}" + (f"（キーワード例: {kw}）" if kw else ""))
    elif lang == "en":
        lines = ["Available skills (usable as task_type):"]
        for name, sk in skills.items():
            desc = sk.description_en or sk.description
            kw = ", ".join(sk.keywords[:3]) if sk.keywords else ""
            lines.append(f"  {name}: {desc}" + (f" (keywords: {kw})" if kw else ""))
    else:
        lines = ["可用技能（可作为 task_type 使用）："]
        for name, sk in skills.items():
            kw = "、".join(sk.keywords[:3]) if sk.keywords else ""
            lines.append(f"  {name}: {sk.description}" + (f"（关键词：{kw}）" if kw else ""))
    return "\n".join(lines)

"""
skills/loader.py - 技能加载器

所有 skill 都是 MD 文件。
AI 通过 CLI 直接执行，不需要 PY 文件。
"""

import os
import re
from typing import Optional
from skills import BaseSkill, MDSkill
from utils.logger import log

_registry: dict = {}
_loaded = False


def _parse_yaml_frontmatter(text: str) -> dict:
    """解析 YAML front matter"""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.DOTALL)
    if not match:
        return {}, text
    
    yaml_str = match.group(1)
    body = match.group(2).strip()
    
    # 简单 YAML 解析（只支持基本类型）
    meta = {}
    current_key = None
    current_dict = None
    current_list = None
    
    for line in yaml_str.strip().split('\n'):
        # 跳过空行
        if not line.strip():
            continue
        
        # 顶级键
        if not line.startswith(' ') and not line.startswith('\t'):
            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip()
                
                if value:
                    # 简单值
                    if value.startswith('[') and value.endswith(']'):
                        # 列表
                        items = [x.strip().strip('"').strip("'") for x in value[1:-1].split(',') if x.strip()]
                        meta[key] = items
                    elif value.lower() in ('true', 'yes'):
                        meta[key] = True
                    elif value.lower() in ('false', 'no'):
                        meta[key] = False
                    else:
                        meta[key] = value.strip('"').strip("'")
                else:
                    # 可能是嵌套结构
                    current_key = key
                    meta[key] = None
                    current_dict = {}
                    current_list = []
        elif current_key:
            # 嵌套结构
            stripped = line.strip()
            if stripped.startswith('- '):
                # 列表项
                if meta[current_key] is None:
                    meta[current_key] = []
                if isinstance(meta[current_key], list):
                    meta[current_key].append(stripped[2:].strip().strip('"').strip("'"))
            elif ':' in stripped:
                # 字典项
                k, _, v = stripped.partition(':')
                k = k.strip()
                v = v.strip()
                
                if meta[current_key] is None:
                    meta[current_key] = {}
                
                if isinstance(meta[current_key], dict):
                    if v.startswith('{') and v.endswith('}'):
                        # 内嵌字典
                        inner = {}
                        for item in v[1:-1].split(','):
                            if ':' in item:
                                ik, _, iv = item.partition(':')
                                inner[ik.strip()] = iv.strip().strip('"').strip("'")
                        meta[current_key][k] = inner
                    elif v.lower() in ('true', 'yes'):
                        meta[current_key][k] = True
                    elif v.lower() in ('false', 'no'):
                        meta[current_key][k] = False
                    else:
                        meta[current_key][k] = v.strip('"').strip("'")
    
    return meta, body


def load_all_skills() -> dict:
    """加载所有 MD 技能文件"""
    global _registry, _loaded
    skills = {}
    skills_dir = os.path.dirname(__file__)
    
    for fname in sorted(os.listdir(skills_dir)):
        if not fname.endswith('.md'):
            continue
        
        skill_name = fname[:-3]
        fpath = os.path.join(skills_dir, fname)
        
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            meta, body = _parse_yaml_frontmatter(content)
            
            if not meta or 'name' not in meta:
                continue
            
            # 解析 params（如果有）
            params = meta.get('params', {})
            if isinstance(params, str):
                params = {}
            
            skill = MDSkill(
                name=meta.get('name', skill_name),
                description=meta.get('description', ''),
                instruction=body,
                description_ja=meta.get('description_ja', ''),
                description_en=meta.get('description_en', ''),
                category=meta.get('category', 'general'),
                keywords=meta.get('keywords', []),
                params=params,
                auto_execute=meta.get('auto_execute', True),
                chainable=meta.get('chainable', True),
            )
            
            if skill.name:
                skills[skill.name] = skill
                log.debug(f"[Skills] ✓ 加载: {skill.name}")
        except Exception as e:
            log.warning(f"[Skills] ✗ 加载失败 {fname}: {e}")
    
    _registry = skills
    _loaded = True
    log.info(f"[Skills] 已加载 {len(skills)} 个技能 (全部 MD 文件)")
    return skills


def get_registry() -> dict:
    if not _loaded:
        load_all_skills()
    return _registry


def get_skill(name: str) -> Optional[MDSkill]:
    return get_registry().get(name)


def reload_skills() -> dict:
    global _loaded
    _loaded = False
    return load_all_skills()


def get_skills_hint(lang: str = "zh") -> str:
    """获取技能列表提示"""
    skills = get_registry()
    if not skills:
        return ""
    
    if lang == "ja":
        lines = ["利用可能なスキル:"]
        for name, sk in skills.items():
            desc = sk.description_ja or sk.description_en or sk.description
            lines.append(f"  {name}: {desc}")
    elif lang == "en":
        lines = ["Available skills:"]
        for name, sk in skills.items():
            lines.append(f"  {name}: {sk.description_en or sk.description}")
    else:
        lines = ["可用技能："]
        for name, sk in skills.items():
            lines.append(f"  {name}: {sk.description}")
    
    return "\n".join(lines)

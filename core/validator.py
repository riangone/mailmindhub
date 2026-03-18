import os
import shutil
import logging
from typing import List, Dict

log = logging.getLogger("mailmind")

# ────────────────────────────────────────────────────────────────
#  配置验证
# ────────────────────────────────────────────────────────────────

def validate_config(mailboxes: Dict, ai_backends: Dict) -> bool:
    """验证配置的完整性"""
    success = True

    # 验证邮箱
    active_mailboxes = []
    for name, mb in mailboxes.items():
        if mb.get("address"):
            active_mailboxes.append(name)
            # 基础验证
            if not mb.get("imap_server") or not mb.get("smtp_server"):
                log.warning(f"邮箱 '{name}' 配置缺失服务器信息")
                success = False

    if not active_mailboxes:
        log.warning("未检测到配置了 address 的有效邮箱")
        # success = False # 允许空配置启动，可能是为了 list

    # 验证 AI
    active_ai = []
    for name, ai in ai_backends.items():
        t = ai.get("type")
        if t == "cli":
            if os.path.isfile(ai.get("cmd", "")) or shutil.which(ai.get("cmd", "")):
                active_ai.append(name)
        elif t.startswith("api_"):
            if ai.get("api_key"):
                active_ai.append(name)

    if not active_ai:
        log.warning("未检测到有效的 AI 后端（CLI 或 API Key）")
        # success = False

    return success

# ────────────────────────────────────────────────────────────────
#  Workspace 路径校验（防止路径穿越攻击）
# ────────────────────────────────────────────────────────────────

def validate_path(path: str, workspace_dir: str = None) -> str:
    """
    校验并规范化路径，确保其在 workspace 目录内。
    
    Args:
        path: 待校验的路径
        workspace_dir: workspace 根目录（留空则使用 core.config.WORKSPACE_DIR）
    
    Returns:
        规范化后的绝对路径
    
    Raises:
        ValueError: 路径超出 workspace 范围
    """
    if not workspace_dir:
        from core.config import WORKSPACE_DIR
        workspace_dir = WORKSPACE_DIR

    # workspace 未设置时，保持向后兼容（不限制）
    if not workspace_dir:
        return os.path.realpath(os.path.abspath(path))

    # 解析绝对路径（跟随符号链接）
    resolved = os.path.realpath(os.path.abspath(path))
    workspace_resolved = os.path.realpath(workspace_dir)

    # 检查路径是否在 workspace 内
    # 使用 os.path.commonpath 确保严格的前缀匹配
    try:
        common = os.path.commonpath([resolved, workspace_resolved])
        if common != workspace_resolved:
            raise ValueError(f"路径超出 workspace 范围：{path}")
    except ValueError as e:
        if "path" in str(e):
            # Windows 不同盘符情况
            raise ValueError(f"路径超出 workspace 范围：{path}")
        raise

    return resolved


def is_path_in_workspace(path: str, workspace_dir: str = None) -> bool:
    """
    检查路径是否在 workspace 内（不抛异常版本）。
    
    Returns:
        True: 路径有效且在 workspace 内
        False: 路径无效或超出范围
    """
    try:
        validate_path(path, workspace_dir)
        return True
    except (ValueError, OSError):
        return False

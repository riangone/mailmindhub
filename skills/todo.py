import json
import os
from datetime import datetime
from skills import BaseSkill

_TODO_FILE = os.path.join(os.path.dirname(__file__), "..", "todos.json")


def _load() -> list:
    if os.path.isfile(_TODO_FILE):
        try:
            with open(_TODO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save(todos: list):
    with open(_TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


class TodoSkill(BaseSkill):
    name = "todo"
    description = "管理个人待办事项（添加/查看/完成/删除）"
    description_ja = "個人TODOリスト管理（追加/一覧/完了/削除）"
    description_en = "Personal todo list management (add/list/complete/delete)"
    keywords = ["todo", "待办", "待做", "to-do", "to do", "タスク追加", "やること", "할일"]

    def run(self, payload: dict, ai_caller=None) -> str:
        action = (payload.get("action") or "list").lower()
        todos = _load()

        if action == "add":
            item = payload.get("item") or payload.get("text") or payload.get("prompt") or ""
            if not item:
                return "⚠️ Please provide item in task_payload"
            todos.append({"id": len(todos) + 1, "item": item, "done": False, "created": datetime.now().isoformat()})
            _save(todos)
            return f"✅ 已添加待办：{item}"

        elif action in ("done", "complete"):
            idx = payload.get("id") or payload.get("task_id")
            if idx is None:
                return "⚠️ Please provide id in task_payload"
            for t in todos:
                if t["id"] == int(idx):
                    t["done"] = True
                    _save(todos)
                    return f"✅ 已完成：{t['item']}"
            return f"⚠️ Todo #{idx} not found"

        elif action == "delete":
            idx = payload.get("id") or payload.get("task_id")
            if idx is None:
                return "⚠️ Please provide id in task_payload"
            todos = [t for t in todos if t["id"] != int(idx)]
            _save(todos)
            return f"✅ 已删除 Todo #{idx}"

        else:  # list
            if not todos:
                return "📋 待办列表为空"
            lines = ["📋 待办事项："]
            for t in todos:
                status = "✅" if t["done"] else "⬜"
                lines.append(f"  {status} #{t['id']} {t['item']}")
            return "\n".join(lines)


SKILL = TodoSkill()

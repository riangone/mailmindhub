"""
invoice skill — Parse or generate invoices via AI.

Supported actions:
  parse    — Extract structured data (amount, date, vendor, items) from invoice text/PDF
  generate — Generate a formatted invoice as text

Optionally uses pdfplumber for PDF parsing (install separately if needed).
Falls back to AI-only extraction when pdfplumber is not available.
"""

from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider


class InvoiceSkill(BaseSkill):
    name = "invoice"
    description = "解析或生成发票（提取金额、日期、供应商、明细）"
    description_ja = "請求書の解析または生成（金額・日付・取引先・明細の抽出）"
    description_en = "Parse or generate invoices (extract amount, date, vendor, line items)"
    keywords = ["发票", "invoice", "请款", "账单", "billing", "インボイス", "請求書", "receipt", "收据"]

    def run(self, payload: dict, ai_caller=None) -> str:
        action = payload.get("action", "parse")
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)

        if action == "parse":
            text = payload.get("text") or payload.get("content") or payload.get("prompt") or ""

            # Try PDF extraction first if a file path is provided
            pdf_path = payload.get("pdf_path") or payload.get("file")
            if pdf_path and not text:
                text = _try_extract_pdf(pdf_path)

            if not text:
                return "⚠️ 请在 task_payload 中提供 text（发票内容）或 pdf_path（PDF 文件路径）"

            prompt = f"""请从以下发票/账单内容中提取结构化信息，以 JSON 格式输出：
{{
  "vendor": "供应商/开票方",
  "invoice_number": "发票号",
  "date": "开票日期 (YYYY-MM-DD)",
  "due_date": "到期日期",
  "total_amount": 总金额数字,
  "currency": "货币代码 (CNY/USD/JPY...)",
  "tax_amount": 税额数字,
  "items": [{{"description": "...", "quantity": 数量, "unit_price": 单价, "amount": 金额}}],
  "notes": "备注"
}}

仅输出 JSON，不加任何说明。

发票内容：
{text[:3000]}"""
            result = ai.call(prompt)
            return result or "⚠️ AI 解析失败，无响应。"

        elif action == "generate":
            vendor   = payload.get("vendor", "")
            client   = payload.get("client", "")
            items    = payload.get("items", [])
            currency = payload.get("currency", "CNY")
            notes    = payload.get("notes", "")

            items_str = "\n".join(
                f"  - {i.get('description', '')}: {i.get('quantity', 1)} × {i.get('unit_price', 0)} {currency}"
                for i in items
            ) if items else "  （请提供 items 明细）"

            prompt = f"""请生成一份专业的发票文本，包含以下信息：

开票方：{vendor or '（未填写）'}
客户：{client or '（未填写）'}
货币：{currency}
明细：
{items_str}
备注：{notes}

请按标准发票格式排版，计算总金额（含税）。"""
            result = ai.call(prompt)
            return result or "⚠️ AI 生成失败，无响应。"

        else:
            return f"⚠️ 未知 action：{action}。支持：parse / generate"


def _try_extract_pdf(pdf_path: str) -> str:
    """Try to extract text from PDF using pdfplumber. Returns empty string on failure."""
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        return ""
    except Exception:
        return ""


SKILL = InvoiceSkill()

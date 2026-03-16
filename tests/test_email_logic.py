import unittest
import json
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# 导入待测试的函数
# 注意：由于 email_daemon.py 包含大量全局初始化逻辑（如日志和环境变量），
# 这里的导入可能需要小心处理，或者我们可以直接将这些纯逻辑函数提取出来测试。
# 为了保持简单，我们直接从 email_daemon 导入。
from core.mail_client import decode_str, get_body_and_attachments, is_sender_allowed
from utils.parser import parse_ai_response

class TestEmailLogic(unittest.TestCase):

    def test_decode_str(self):
        # 测试正常字符串
        self.assertEqual(decode_str("hello"), "hello")
        # 测试编码字符串 (Base64 UTF-8)
        # =?utf-8?b?5L2g5aW9?= -> "你好"
        self.assertEqual(decode_str("=?utf-8?b?5L2g5aW9?="), "你好")
        # 测试空
        self.assertEqual(decode_str(""), "")

    def test_parse_ai_response(self):
        # parse_ai_response returns (subject, body, schedule_at, schedule_every,
        #   schedule_until, schedule_cron, attachments, task_type, task_payload, output)

        # 测试包含 JSON 的响应
        raw_with_json = 'Some chatty text before. {"subject": "Test Sub", "body": "Test Body"} and after.'
        sub, body, *_ = parse_ai_response(raw_with_json)
        self.assertEqual(sub, "Test Sub")
        self.assertEqual(body, "Test Body")

        # 测试不包含 JSON 的响应
        raw_plain = "Just plain text response."
        sub, body, *_ = parse_ai_response(raw_plain)
        self.assertEqual(sub, "")
        self.assertEqual(body, raw_plain)

        # 测试 JSON 缺少字段
        raw_partial = '{"body": "Only Body"}'
        sub, body, *_ = parse_ai_response(raw_partial)
        self.assertEqual(sub, "")
        self.assertEqual(body, "Only Body")

        # 测试调度字段
        raw_sched = '{"subject": "S", "body": "B", "schedule_every": "5m", "task_type": "weather"}'
        sub, body, sch_at, sch_every, sch_until, sch_cron, atts, task_type, task_payload, output = parse_ai_response(raw_sched)
        self.assertEqual(sch_every, "5m")
        self.assertEqual(task_type, "weather")
        self.assertIsNone(sch_at)

    def test_is_sender_allowed(self):
        allowed = ["me@example.com", "@company.com"]
        # 精确匹配
        self.assertTrue(is_sender_allowed("me@example.com", allowed))
        # 域名匹配
        self.assertTrue(is_sender_allowed("boss@company.com", allowed))
        # 不匹配
        self.assertFalse(is_sender_allowed("stranger@other.com", allowed))
        # 空白名单（默认允许）
        self.assertTrue(is_sender_allowed("any@any.com", []))

    def test_get_body_and_attachments(self):
        # 构造一个复杂的邮件对象
        msg = MIMEMultipart()
        msg["Subject"] = "Test Multipart"
        
        # 文本正文
        body_text = "Hello world!"
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        
        # 附件
        filename = "test.txt"
        attachment_content = "This is a text file."
        part = MIMEBase("text", "plain")
        part.set_payload(attachment_content.encode("utf-8"))
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)
        
        # 将消息转换为对象再测试解析
        email_obj = email.message_from_bytes(msg.as_bytes())
        body, atts = get_body_and_attachments(email_obj)
        
        self.assertEqual(body, body_text)
        self.assertEqual(len(atts), 1)
        self.assertEqual(atts[0]["filename"], filename)
        self.assertEqual(atts[0]["content"], attachment_content)

if __name__ == "__main__":
    unittest.main()

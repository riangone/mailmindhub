"""
tests/test_ai_logger.py - AI 日志数据库测试

验证 INSERT 语句列数与参数数量匹配，防止 "33 values for 34 columns" 错误。
"""
import os
import sys
import re
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAILoggerSQLIntegrity(unittest.TestCase):
    """测试 AI 日志器 SQL 完整性"""

    def test_insert_columns_match_placeholders(self):
        """验证 INSERT 语句的列名数量与占位符数量匹配"""
        from utils import ai_logger
        
        # 读取源代码
        source_file = ai_logger.__file__
        with open(source_file, "r", encoding="utf-8") as f:
            source_code = f.read()
        
        # 提取 INSERT 语句
        match = re.search(
            r"INSERT INTO ai_messages\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
            source_code,
            re.DOTALL
        )
        self.assertIsNotNone(match, "未找到 INSERT INTO ai_messages 语句")
        
        columns_str, placeholders_str = match.groups()
        
        # 数列名
        columns = [c.strip() for c in columns_str.split(",") if c.strip()]
        
        # 数占位符
        placeholders = re.findall(r"\?", placeholders_str)
        
        self.assertEqual(
            len(columns),
            len(placeholders),
            f"INSERT 语句列数({len(columns)})与占位符数({len(placeholders)})不匹配！\n"
            f"列名: {columns}"
        )
    
    def test_insert_params_count_match_columns(self):
        """通过实际写入验证列数和参数数匹配"""
        from utils.ai_logger import log_ai_message, init_db
        import tempfile
        import os
        
        # 使用临时数据库
        from utils import ai_logger
        original_db = ai_logger.DB_PATH
        test_db = os.path.join(tempfile.gettempdir(), "test_ai_params.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        
        try:
            ai_logger.DB_PATH = test_db
            init_db()
            
            # 写入一条包含所有字段的消息
            # 如果列数与参数不匹配，这里会抛出 OperationalError
            row_id = log_ai_message(
                ai_name="test_ai",
                raw_response="Test response",
                parse_success=True,
                mailbox_name="gmail",
                from_email="test@example.com",
                email_subject="Test",
                task_type="email",
                subject="Test Subject",
                body="Test body",
                schedule_at="2026-04-13T10:00:00",
                schedule_every="1h",
                schedule_cron="0 * * * *",
                schedule_until="2026-12-31",
                task_payload={"key": "value"},
                output={"email": True},
                attachments=[{"filename": "test.txt", "content": "content"}],
                task_executed=True,
                task_result_subject="Result",
                task_result_body="Completed",
                ai_call_ms=100,
                task_exec_ms=200,
                lang="en"
            )
            
            self.assertIsNotNone(row_id)
            self.assertGreater(row_id, 0)
            
        except Exception as e:
            if "values" in str(e).lower() and "column" in str(e).lower():
                self.fail(f"INSERT 列数与参数数不匹配: {e}")
            raise
        finally:
            ai_logger.DB_PATH = original_db
            if os.path.exists(test_db):
                os.remove(test_db)


class TestAILoggerFunctionality(unittest.TestCase):
    """测试 AI 日志器功能"""

    @classmethod
    def setUpClass(cls):
        """设置测试数据库"""
        # 使用临时数据库文件
        import tempfile
        test_db = os.path.join(tempfile.gettempdir(), "test_ai_messages.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        
        # 替换数据库路径
        from utils import ai_logger
        cls.original_db_path = ai_logger.DB_PATH
        ai_logger.DB_PATH = test_db
        
        # 重新初始化
        ai_logger.init_db()

    @classmethod
    def tearDownClass(cls):
        """清理测试数据库"""
        from utils import ai_logger
        ai_logger.DB_PATH = cls.original_db_path
        import tempfile
        test_db = os.path.join(tempfile.gettempdir(), "test_ai_messages.db")
        if os.path.exists(test_db):
            os.remove(test_db)

    def test_log_ai_message_with_all_fields(self):
        """测试记录包含所有字段的 AI 消息"""
        from utils.ai_logger import log_ai_message, query_ai_messages
        
        row_id = log_ai_message(
            ai_name="test_ai",
            raw_response='{"subject": "Test", "body": "Test body"}',
            parse_success=True,
            mailbox_name="gmail",
            from_email="test@example.com",
            email_subject="Test Email",
            email_id="msg123",
            ai_type="api_openai",
            model="gpt-4",
            prompt="Test prompt",
            task_type="email",
            subject="Test Subject",
            body="This is a test body content",
            schedule_at="2026-04-13T10:00:00",
            schedule_every="1h",
            schedule_cron="0 * * * *",
            schedule_until="2026-12-31",
            task_payload={"query": "test query"},
            output={"email": True, "archive": True},
            attachments=[{"filename": "test.txt", "content": "content"}],
            task_executed=True,
            task_result_subject="Task Result",
            task_result_body="Task completed successfully",
            task_error="",
            ai_call_ms=1500,
            task_exec_ms=2000,
            lang="en"
        )
        
        self.assertIsNotNone(row_id)
        self.assertGreater(row_id, 0)
        
        # 查询验证
        msgs = query_ai_messages(limit=1, from_email="test@example.com")
        self.assertEqual(len(msgs), 1)
        
        msg = msgs[0]
        self.assertEqual(msg["ai_name"], "test_ai")
        self.assertEqual(msg["task_type"], "email")
        self.assertEqual(msg["subject"], "Test Subject")
        self.assertEqual(msg["lang"], "en")
        self.assertEqual(msg["ai_call_ms"], 1500)
        self.assertEqual(msg["task_exec_ms"], 2000)
        self.assertEqual(msg["attachments_count"], 1)

    def test_log_ai_message_minimal_fields(self):
        """测试仅必填字段的消息记录"""
        from utils.ai_logger import log_ai_message, query_ai_messages
        
        row_id = log_ai_message(
            ai_name="minimal_ai",
            raw_response="Simple response",
            parse_success=False,
            parse_error="No JSON found"
        )
        
        self.assertIsNotNone(row_id)
        
        msgs = query_ai_messages(ai_name="minimal_ai", parse_success=False)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["parse_error"], "No JSON found")


if __name__ == "__main__":
    unittest.main()

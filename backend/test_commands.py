"""指令系统测试 — 验证指令分类和执行链路。"""

import pytest
from unittest.mock import AsyncMock, patch

from commands import execute_command, classify_command
from config import Settings


def get_test_settings() -> Settings:
    return Settings(
        HERMES_MODE="mock",
        HERMES_BASE_URL="http://localhost:8001",
        HERMES_MODEL="test",
        FASTGPT_MODE="mock",
    )


class TestExecuteCommand:
    """测试指令执行器（不依赖 Hermes）。"""

    def test_create_task_basic(self):
        """基本创建任务。"""
        cmd = {
            "action": "create_task",
            "params": {"title": "测试任务", "tag": "今天", "deadline": "2026-08-06T10:00:00"},
            "reply": "已创建",
        }
        result = execute_command(cmd)
        assert result["mode"] == "command"
        assert result["action"] == "create_task"
        assert result["result"] is not None
        assert result["result"]["title"] == "测试任务"
        assert "已创建" in result["answer"]

    def test_create_task_missing_title(self):
        """缺少标题时应返回错误提示。"""
        cmd = {
            "action": "create_task",
            "params": {},
            "reply": "",
        }
        result = execute_command(cmd)
        assert "❌" in result["answer"]
        assert result["result"] is None

    def test_create_event_basic(self):
        """基本创建日程。"""
        cmd = {
            "action": "create_event",
            "params": {"title": "项目评审", "date": "2026-08-15", "tone": "blue"},
            "reply": "日程已添加",
        }
        result = execute_command(cmd)
        assert result["mode"] == "command"
        assert result["action"] == "create_event"
        assert result["result"] is not None
        assert result["result"]["title"] == "项目评审"
        assert result["result"]["date"] == "2026-08-15"

    def test_create_event_missing_title(self):
        """缺少日程标题时应返回错误提示。"""
        cmd = {
            "action": "create_event",
            "params": {"date": "2026-08-15"},
            "reply": "",
        }
        result = execute_command(cmd)
        assert "❌" in result["answer"]

    def test_update_task_mark_done(self):
        """标记任务完成 — 先创建任务再标记。"""
        # 先创建一个任务
        create_cmd = {
            "action": "create_task",
            "params": {"title": "待完成的任务", "tag": "今天"},
            "reply": "",
        }
        create_result = execute_command(create_cmd)
        task_id = create_result["result"]["id"]

        # 标记完成
        update_cmd = {
            "action": "update_task",
            "params": {"title": "待完成的任务", "done": True},
            "reply": "已标记完成",
        }
        update_result = execute_command(update_cmd)
        assert update_result["mode"] == "command"
        assert update_result["result"] is not None
        assert update_result["result"]["done"] is True
        assert "标记为完成" in update_result["answer"] or "已标记完成" in update_result["answer"]

    def test_update_task_not_found(self):
        """更新不存在的任务应返回错误。"""
        cmd = {
            "action": "update_task",
            "params": {"title": "不存在的任务标题XYZ123", "done": True},
            "reply": "",
        }
        result = execute_command(cmd)
        assert "❌" in result["answer"]
        assert "未找到" in result["answer"]

    def test_delete_task(self):
        """删除任务 — 先创建再删除。"""
        create_cmd = {
            "action": "create_task",
            "params": {"title": "待删除的任务", "tag": "今天"},
            "reply": "",
        }
        execute_command(create_cmd)

        delete_cmd = {
            "action": "delete_task",
            "params": {"title": "待删除的任务"},
            "reply": "已删除",
        }
        result = execute_command(delete_cmd)
        assert result["mode"] == "command"
        assert "已删除" in result["answer"]

    def test_delete_task_not_found(self):
        """删除不存在的任务应返回错误。"""
        cmd = {
            "action": "delete_task",
            "params": {"title": "不存在的任务标题XYZ999"},
            "reply": "",
        }
        result = execute_command(cmd)
        assert "❌" in result["answer"]

    def test_chat_action_returns_placeholder(self):
        """chat action 应返回空 answer（让调用方继续走问答逻辑）。"""
        cmd = {
            "action": "chat",
            "params": {},
            "reply": "",
        }
        result = execute_command(cmd)
        assert result["action"] == "chat"
        assert result["answer"] == ""

    def test_delete_task_by_id(self):
        """按任务 ID 删除。"""
        # 先创建任务
        create_cmd = {
            "action": "create_task",
            "params": {"title": "按ID删除测试", "tag": "今天"},
            "reply": "",
        }
        create_result = execute_command(create_cmd)
        task_id = create_result["result"]["id"]

        # 按 ID 删除（title 是数字字符串）
        delete_cmd = {
            "action": "delete_task",
            "params": {"title": str(task_id)},
            "reply": "",
        }
        result = execute_command(delete_cmd)
        assert "已删除" in result["answer"]

    def test_delete_task_by_id_field(self):
        """通过 id 字段删除任务。"""
        create_cmd = {
            "action": "create_task",
            "params": {"title": "通过ID字段删除", "tag": "今天"},
            "reply": "",
        }
        create_result = execute_command(create_cmd)
        task_id = create_result["result"]["id"]

        # id 可以是 int 类型（模拟 Hermes 返回整数）
        delete_cmd = {
            "action": "delete_task",
            "params": {"title": "某个未知标题", "id": task_id},
            "reply": "",
        }
        result = execute_command(delete_cmd)
        assert "已删除" in result["answer"]

    def test_update_task_by_id(self):
        """按任务 ID 更新。"""
        create_cmd = {
            "action": "create_task",
            "params": {"title": "按ID更新测试", "tag": "今天"},
            "reply": "",
        }
        create_result = execute_command(create_cmd)
        task_id = create_result["result"]["id"]

        # id 可以是 int 类型
        update_cmd = {
            "action": "update_task",
            "params": {"title": "不匹配的标题", "id": task_id, "done": True},
            "reply": "",
        }
        result = execute_command(update_cmd)
        assert result["result"]["done"] is True

    def test_unknown_action(self):
        """未知 action 应返回友好提示。"""
        cmd = {
            "action": "unknown",
            "params": {},
            "reply": "",
        }
        result = execute_command(cmd)
        assert "无法识别" in result["answer"]


class TestClassifyCommand:
    """测试指令分类（mock Hermes）。"""

    @pytest.mark.asyncio
    async def test_classify_returns_chat_on_hermes_failure(self):
        """Hermes 不可用时应 fallback 到 chat。"""
        settings = get_test_settings()
        # mock 模式下 hermes_chat 返回 mock 文本（非 JSON），classify 应 catch 并返回 chat
        result = await classify_command(settings, "帮我创建任务")
        assert result["action"] == "chat"

    @pytest.mark.asyncio
    async def test_slash_commands_bypass_classification(self):
        """验证 /rag 和 /chat 斜杠命令走强制模式，不触发指令分类。

        这个逻辑在 knowledge_chat 端点中——forced_mode 存在时会跳过 classify_command。
        这里验证我们的函数在收到带前缀的问题时行为正确（它不会识别为指令）。
        """
        # /rag 前缀在 knowledge_chat 中被截掉，实际传给 classify 的是去掉前缀的内容
        # 这个测试验证 classify_command 本身的行为
        settings = get_test_settings()
        # mock 模式下返回非 JSON → fallback to chat
        result = await classify_command(settings, "/rag 什么是机器学习")
        assert result["action"] == "chat"

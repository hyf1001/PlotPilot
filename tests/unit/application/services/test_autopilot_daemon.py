"""AutopilotDaemon 辅助逻辑测试"""
from unittest.mock import Mock

from application.engine.services.autopilot_daemon import AutopilotDaemon


def test_get_latest_completed_chapter_prefers_highest_number():
    """审计阶段应按真实章节号选择最近完成章节。"""
    chapters = [
        Mock(number=11, status=Mock(value="completed")),
        Mock(number=12, status=Mock(value="draft")),
        Mock(number=13, status=Mock(value="completed")),
    ]

    chapter = AutopilotDaemon._get_latest_completed_chapter(chapters)

    assert chapter.number == 13


def test_get_latest_completed_chapter_returns_none_when_no_completed():
    """没有完成章节时应返回 None。"""
    chapters = [
        Mock(number=11, status=Mock(value="draft")),
        Mock(number=12, status=Mock(value="reviewing")),
    ]

    chapter = AutopilotDaemon._get_latest_completed_chapter(chapters)

    assert chapter is None

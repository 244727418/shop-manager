import json
import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from manager.shop_manager import ShopManagerApp


class FakeDB:
    def __init__(self):
        self.reminders = []
        self.records = []

    def safe_execute(self, query, params=()):
        if "INSERT INTO task_reminders" in query:
            self.reminders.append((params[2], params[3]))
        elif "INSERT OR REPLACE INTO records" in query:
            self.records = json.loads(params[-1])

    def safe_fetchall(self, query, params=()):
        if "FROM task_reminders" in query:
            return list(self.reminders)
        if "FROM daily_tasks" in query:
            return [("检查推广", "2026-07-17 09:00:00"), ("更换主图", "2026-07-17 08:00:00")]
        if "FROM records" in query:
            return [(json.dumps(self.records, ensure_ascii=False),)] if self.records else []
        return []


def test_reminder_creation_is_recorded_and_pending_tasks_are_visible():
    host = SimpleNamespace(
        db=FakeDB(),
        daily_task_dialog=None,
        product_spec_dialog=None,
        force_refresh_product_widget=lambda _product_id: None,
        show_toast=lambda _text: None,
    )
    host._sort_records_by_time = MethodType(ShopManagerApp._sort_records_by_time, host)
    host._record_time_on_date = MethodType(ShopManagerApp._record_time_on_date, host)
    host.record_product_operation = MethodType(ShopManagerApp.record_product_operation, host)

    first = ShopManagerApp.create_product_reminder(host, 1, 2, "检查推广", "2026-07-18 09:00:00")
    ShopManagerApp.create_product_reminder(host, 1, 2, "复查价格", "2026-07-18 10:00:00")

    assert first["changes"][0]["metric"] == "创建任务"
    assert len(host.db.records) == 2
    lines = ShopManagerApp.get_product_pending_task_lines(host, 2)
    assert lines == [
        "提醒时间：2026-07-18 09:00:00\n任务内容：检查推广",
        "提醒时间：2026-07-18 10:00:00\n任务内容：复查价格",
        "创建时间：2026-07-17 08:00:00\n任务内容：更换主图",
    ]

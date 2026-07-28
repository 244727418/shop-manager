from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from manager.dialogs.records import OperationRecordDialog
from manager.shop_manager import OperationRecordDelegate, ShopManagerApp


class PddLinkOperationTest(TestCase):
    def test_created_link_is_not_classified_as_spec_or_title_change(self):
        change = {
            "metric": "新建链接",
            "text": "新建链接",
            "type": "product_created",
            "old": "",
            "new": "",
        }
        self.assertEqual("other", OperationRecordDialog._change_group(None, change))
        self.assertEqual("新建链接", OperationRecordDelegate._summary_label(None, "新建链接", change["text"], change))

    def test_browser_data_is_shared_by_build_but_isolated_by_account_and_store(self):
        root = Path("shared_data_root")
        archive = SimpleNamespace(active={"name": "account_a"})
        archive.get_active_data_account = lambda: archive.active
        archive._archive_browser_dir_for_account = lambda account: str(root / account["name"] / "浏览器数据")
        host = SimpleNamespace(archive_manager=archive, pdd_browser_monitor=None)

        first = ShopManagerApp._get_pdd_browser_monitor(host)
        first.set_store_context(1)
        self.assertEqual(root / "account_a" / "浏览器数据" / "pdd_merchant_profiles" / "store_1", Path(first.profile_dir))
        first.set_store_context(2)
        self.assertEqual(root / "account_a" / "浏览器数据" / "pdd_merchant_profiles" / "store_2", Path(first.profile_dir))

        archive.active = {"name": "account_b"}
        second = ShopManagerApp._get_pdd_browser_monitor(host)
        second.set_store_context(1)
        self.assertIsNot(first, second)
        self.assertEqual(root / "account_b" / "浏览器数据" / "pdd_merchant_profiles" / "store_1", Path(second.profile_dir))

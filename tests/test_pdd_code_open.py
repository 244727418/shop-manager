import os
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel

from manager.shop_manager import ShopManagerApp


class _Dialog:
    def __init__(self):
        self.lbl_summary = QLabel()

    def isMinimized(self):
        return False

    def windowState(self):
        return 0

    def setWindowState(self, _state):
        pass

    def show(self):
        pass

    def raise_(self):
        pass

    def activateWindow(self):
        pass


class PddCodeOpenTest(TestCase):
    def test_opens_browser_and_copies_id_without_searching(self):
        app = QApplication.instance() or QApplication([])
        calls = []

        class Monitor:
            def activate_store_browser(self, *args, **kwargs):
                calls.append((args, kwargs))

            def open_goods_list_and_search_product(self, *_args, **_kwargs):
                raise AssertionError("不应自动搜索商品列表")

        dialog = _Dialog()
        host = type("Host", (), {
            "_get_pdd_browser_monitor": lambda _self: Monitor(),
            "pdd_code_fetch_dialogs": {3: dialog},
            "statusBar": lambda _self: type("Bar", (), {"showMessage": lambda *_args: None})(),
        })()

        ShopManagerApp._open_pdd_fetch_for_store(host, 3, "code", "9513241661")

        self.assertEqual("9513241661", app.clipboard().text())
        self.assertEqual([((3,), {"open_url": True, "open_new_tab": False})], calls)
        self.assertIn("已打开商家端并复制商品ID", dialog.lbl_summary.text())

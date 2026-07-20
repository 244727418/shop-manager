from unittest import TestCase
from unittest.mock import patch

from manager.pdd_browser_monitor import PddBrowserMonitor


class PddTargetSelectionTest(TestCase):
    def test_visible_tab_wins_over_price_preference(self):
        monitor = PddBrowserMonitor(".")
        targets = [
            {
                "id": "price",
                "type": "page",
                "url": "https://mms.pinduoduo.com/kit/goods-price-management",
                "title": "商品价格管理",
            },
            {
                "id": "active",
                "type": "page",
                "url": "https://mms.pinduoduo.com/goods/goods_list",
                "title": "商品列表",
            },
        ]

        with patch("manager.pdd_browser_monitor.requests.get") as request:
            request.return_value.json.return_value = targets
            with patch.object(monitor, "_target_is_visible", side_effect=lambda target: target["id"] == "active"):
                self.assertEqual(monitor._get_pdd_target(prefer_price=True)["id"], "active")

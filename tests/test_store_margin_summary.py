from unittest import TestCase

from manager.dialogs.store_margin import _price_match_summary_html


class PriceMatchSummaryTest(TestCase):
    def test_complete_and_unmatched_summaries(self):
        self.assertIn("全部匹配", _price_match_summary_html(3, 3, 0, 0, 0, 0, 0))
        summary = _price_match_summary_html(4, 1, 3, 2, 1, 0, 0)
        self.assertIn("匹配 1", summary)
        self.assertIn("未匹配 3", summary)
        self.assertIn("规格未匹配 2", summary)
        self.assertNotIn("活动/营销", summary)
        self.assertIn("活动/营销未匹配 1", _price_match_summary_html(2, 1, 1, 0, 0, 1, 0))

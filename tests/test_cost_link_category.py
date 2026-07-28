import unittest

from manager.dialogs.cost_library import CostLinkCreateDialog


class CostLinkCategoryTest(unittest.TestCase):
    def test_majority_category_wins_and_tie_uses_first_spec(self):
        subject = type("Subject", (), {})()
        subject.specs = [
            {"category_label": "练习本"},
            {"category_label": "资料卡"},
            {"category_label": "资料卡"},
        ]
        self.assertEqual(CostLinkCreateDialog._inferred_category_label(subject), "资料卡")

        subject.specs = [{"category_label": "练习本"}, {"category_label": "资料卡"}]
        self.assertEqual(CostLinkCreateDialog._inferred_category_label(subject), "练习本")


if __name__ == "__main__":
    unittest.main()

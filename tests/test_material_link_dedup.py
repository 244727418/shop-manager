import unittest

from manager.dialogs.material_library import MaterialLibraryDialog


class FakeCombo:
    def count(self):
        return 1


class FakeCheckbox:
    def __init__(self, checked):
        self.checked = checked

    def isChecked(self):
        return self.checked


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""

    def safe_fetchall(self, query, _params):
        self.query = query
        return self.rows


class LinkDataSubject:
    LINK_NO_TYPE = "无链接类型"
    LINK_UNGROUPED = "未分组"
    load_link_data = MaterialLibraryDialog.load_link_data

    def __init__(self, rows, show_inactive):
        self.store_filter_combo = FakeCombo()
        self.show_inactive_links_checkbox = FakeCheckbox(show_inactive)
        self.link_store_filter_id = None
        self.selected_link_combo = ""
        self.selected_link_type = ""
        self.selected_link_product_ids = set()
        self.db = FakeDatabase(rows)

    def root_folder(self):
        return ""


class MaterialLinkDedupTest(unittest.TestCase):
    rows = [
        (7, "100", "旧记录", "", None, "", 4, "店铺", "商品类型A", "#ddebf7", 1),
        (25, "100", "有效记录", "", None, "", 4, "店铺", "商品类型A", "#ddebf7", 0),
        (8, "200", "仅下架", "", None, "", 4, "店铺", "商品类型B", "#e8f4ea", 1),
    ]

    def test_default_hides_archived_rows(self):
        subject = LinkDataSubject(self.rows, False)
        subject.load_link_data()
        self.assertEqual([item["db_id"] for item in subject.link_items], [25])
        self.assertIn("COALESCE(p.is_archived, 0)=0", subject.db.query)
        self.assertIn("p.product_category_label", subject.db.query)
        self.assertNotIn("link_combinations", subject.db.query)

    def test_active_row_wins_over_archived_duplicate(self):
        subject = LinkDataSubject(self.rows, True)
        subject.load_link_data()
        self.assertEqual([item["db_id"] for item in subject.link_items], [25, 8])
        self.assertTrue(subject.link_items[1]["archived"])


if __name__ == "__main__":
    unittest.main()

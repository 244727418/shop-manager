import os
import tempfile
import unittest
from unittest.mock import patch

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialog

from manager.db import SafeDatabaseManager
from manager.dialogs.cost_library import CostLibraryDialog


class _NoChangeDialog(QDialog):
    def __init__(self, *_args, **_kwargs):
        super().__init__()

    def exec_(self):
        return QDialog.Rejected


class CostLibraryChildRefreshTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = SafeDatabaseManager(os.path.join(self.temp.name, "cost.db"))
        self.db.cursor.execute(
            "INSERT INTO cost_library (spec_code, spec_name, category_label, cost_price) VALUES ('A1', '测试商品', '测试类型', 1)"
        )
        self.db.conn.commit()
        self.app = QApplication.instance() or QApplication([])
        self.library = CostLibraryDialog(self.db)
        self.library.load_data()
        self.app.processEvents()

    def tearDown(self):
        self.library.close()
        self.app.processEvents()
        self.db.close()
        self.temp.cleanup()

    def test_closing_management_windows_without_changes_does_not_refresh_cost_table(self):
        with patch.object(self.library, "load_data") as full_load, \
                patch.object(self.library, "_refresh_cost_rows") as row_refresh, \
                patch.object(self.library, "_refresh_main_products_for_specs") as product_refresh:
            with patch("manager.dialogs.cost_library.CostComboReviewDialog", _NoChangeDialog):
                self.library.show_combo_review()
            with patch("manager.dialogs.cost_library.CostCategoryManageDialog", _NoChangeDialog):
                self.library.show_category_manage()
            with patch("manager.dialogs.cost_library.LinkCombinationDialog", _NoChangeDialog):
                self.library.show_link_combinations()
                self.library.link_combination_dialog.close()
                QTest.qWait(20)
                self.app.processEvents()

            full_load.assert_not_called()
            row_refresh.assert_not_called()
            product_refresh.assert_not_called()

    def test_changed_rows_update_and_reorder_without_full_reload(self):
        self.db.cursor.execute(
            "INSERT INTO cost_library (spec_code, spec_name, category_label, cost_price) VALUES ('A2', '测试商品2', '测试类型', 2)"
        )
        self.db.conn.commit()
        self.library.load_data()
        self.db.update_cost_manual_sort_orders(["A2", "A1"])
        with patch.object(self.library, "load_data") as full_load:
            self.library._refresh_cost_rows(["A1", "A2"])
            self.library._reorder_visible_cost_rows()

        full_load.assert_not_called()
        visible_codes = [
            self.library.model.item(row, self.library.COL_CODE).text()
            for row in range(self.library.model.rowCount())
        ]
        self.assertEqual(visible_codes, ["A2", "A1"])

        self.db.ensure_cost_category("新类型")
        self.db.update_cost_spec_category("A1", "新类型")
        with patch.object(self.library, "load_data") as full_load:
            self.library._refresh_cost_rows(["A1"])
            self.library._reorder_visible_cost_rows()
        full_load.assert_not_called()
        row = self.library._row_by_spec_code["A1"]
        self.assertEqual(self.library.model.item(row, self.library.COL_CATEGORY).text(), "新类型")

    def test_progressive_load_shows_first_rows_and_search_reuses_cache(self):
        self.db.cursor.executemany(
            "INSERT INTO cost_library (spec_code, spec_name, category_label, cost_price) VALUES (?, ?, '测试类型', 1)",
            [(f"B{index:03d}", f"测试商品{index:03d}") for index in range(80)],
        )
        self.db.conn.commit()

        self.library._load_data_progressive()
        self.assertIsNotNone(self.library.model.item(0, self.library.COL_CODE))
        self.assertIsNone(
            self.library.model.item(self.library.LOAD_VISIBLE_BATCH_SIZE, self.library.COL_CODE)
        )
        for _ in range(200):
            if not self.library._loading:
                break
            QTest.qWait(5)
        self.assertFalse(self.library._loading)
        self.assertIsNotNone(
            self.library.model.item(self.library.model.rowCount() - 1, self.library.COL_CODE)
        )

        with patch.object(self.library, "_fetch_cost_rows") as fetch_rows:
            self.library.search_input.setText("测试商品")
            QTest.qWait(180)
        fetch_rows.assert_not_called()

    def test_spec_code_auto_save_and_ten_step_undo_redo(self):
        self.db.cursor.execute(
            "INSERT INTO products (id, store_id, name, title) VALUES (1, 1, 'LINK-1', '测试链接')"
        )
        self.db.cursor.execute(
            """INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent)
               VALUES (1, '测试商品', 'A1', 0, 0)"""
        )
        self.db.conn.commit()
        row = self.library._row_by_spec_code["A1"]
        code_item = self.library.model.item(row, self.library.COL_CODE)
        self.assertTrue(code_item.flags() & Qt.ItemIsEditable)

        code_item.setText("A2")
        self.library._auto_save_timer.stop()
        self.library.save_changes(auto_save=True)
        self.assertEqual(
            self.db.safe_fetchall("SELECT spec_code FROM cost_library"), [("A2",)]
        )
        self.assertEqual(
            self.db.safe_fetchall("SELECT spec_code FROM product_specs"), [("A2",)]
        )

        self.library.undo_last_cost_change()
        self.assertEqual(
            self.db.safe_fetchall("SELECT spec_code FROM cost_library"), [("A1",)]
        )
        self.assertEqual(
            self.db.safe_fetchall("SELECT spec_code FROM product_specs"), [("A1",)]
        )
        self.library.redo_last_cost_change()
        self.assertEqual(
            self.db.safe_fetchall("SELECT spec_code FROM cost_library"), [("A2",)]
        )
        self.assertEqual(
            self.db.safe_fetchall("SELECT spec_code FROM product_specs"), [("A2",)]
        )

        for index in range(11):
            self.library._push_cost_undo(
                f"测试{index}",
                {"before": (index,)},
                {"after": (index,)},
            )
        self.assertEqual(len(self.library._undo_stack), self.library.UNDO_LIMIT)


if __name__ == "__main__":
    unittest.main()

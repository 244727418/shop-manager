import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from manager.db import SafeDatabaseManager
from manager.dialogs.cost_library import (
    CostComboReviewDialog, CostItemCreateDialog, CostLibraryDialog, ProductAttributeDialog,
)
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QLabel, QLineEdit, QPushButton, QSpinBox, QWidget,
)


class CostComboTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = SafeDatabaseManager(os.path.join(self.temp.name, "combo.db"))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def add(self, code, name, product_cost=1.0, weight=0.1, attribute="尺寸：A5", category="练习本"):
        self.db.cursor.execute(
            """INSERT INTO cost_library
               (spec_code, spec_name, category_label, quantity, product_cost, unit_weight,
                cost_price, cost_calc_mode, product_attribute)
               VALUES (?, ?, ?, '1', ?, ?, 0, 'detail', ?)""",
            (code, name, category, product_cost, weight, attribute),
        )
        self.db.conn.commit()

    def test_detail_item_can_be_blank_and_selected_single_builds_multiplier_combo(self):
        app = QApplication.instance() or QApplication([])
        self.db.set_cost_library_mode("detail")

        blank = CostItemCreateDialog(self.db)
        blank.category_combo.setEditText("练习本")
        blank.name_input.setText("待补成本商品")
        blank.code_input.setText("BLANK")
        with patch("manager.dialogs.cost_library.QMessageBox.information"):
            blank.create_item()
        self.assertEqual(
            self.db.safe_fetchall(
                """SELECT quantity, product_cost, unit_weight, cost_price
                   FROM cost_library WHERE spec_code='BLANK'"""
            )[0],
            ("", None, None, None),
        )
        self.assertFalse(hasattr(blank, "quantity_input"))

        self.add("SINGLE", "错题本", 1.5, 0.2)
        combo = CostItemCreateDialog(self.db)
        combo.category_combo.setEditText("练习本")
        combo.code_input.setText("COMBO")
        combo.selected_single_spec = {
            "category": "练习本", "name": "错题本", "code": "SINGLE",
            "product_cost": 1.5, "unit_weight": 0.2, "attribute": "尺寸：A5",
        }
        combo.name_input.setText("错题本3本")
        self.assertEqual(combo.cost_input.text(), "4.5")
        self.assertEqual(combo.weight_input.text(), "0.6")
        with patch("manager.dialogs.cost_library.QMessageBox.information"):
            combo.create_item()
        product_cost, unit_weight, is_combo, raw_items = self.db.safe_fetchall(
            """SELECT product_cost, unit_weight, product_attribute_is_combo, combo_components_json
               FROM cost_library WHERE spec_code='COMBO'"""
        )[0]
        self.assertEqual((product_cost, unit_weight, is_combo), (4.5, 0.6, 1))
        self.assertEqual(json.loads(raw_items), [{"spec_code": "SINGLE", "quantity": 3}])

        library = CostLibraryDialog(self.db)
        deadline = time.time() + 1.5
        while "SINGLE" not in library._row_by_spec_code and time.time() < deadline:
            app.processEvents()
        self.assertTrue(library.table_view.isColumnHidden(library.COL_QUANTITY))
        self.assertEqual(library.model.headerData(library.COL_UNIT_WEIGHT, Qt.Horizontal), "重量（kg）")
        row = library._row_by_spec_code["SINGLE"]
        library.model.item(row, library.COL_PRODUCT_COST).setText("")
        library.save_changes(auto_save=True)
        self.assertEqual(
            self.db.safe_fetchall(
                "SELECT product_cost, cost_price FROM cost_library WHERE spec_code='SINGLE'"
            )[0],
            (None, None),
        )
        library.close()
        app.processEvents()

    def test_combo_cost_clears_when_component_cost_is_missing(self):
        self.add("SINGLE", "错题本", 1.5, 0.2)
        self.add("COMBO", "错题本3本", 4.5, 0.6)
        self.db.safe_execute(
            """UPDATE cost_library
               SET product_attribute_is_combo=1,
                   combo_components_json='[{"spec_code":"SINGLE","quantity":3}]'
               WHERE spec_code='COMBO'"""
        )
        self.db.safe_execute(
            "UPDATE cost_library SET product_cost=NULL WHERE spec_code='SINGLE'"
        )
        self.db.recalculate_cost_combinations_for_components(["SINGLE"])
        self.assertEqual(
            self.db.safe_fetchall(
                """SELECT product_cost, unit_weight, shipping_fee, misc_fee, cost_price
                   FROM cost_library WHERE spec_code='COMBO'"""
            )[0],
            (None, None, None, None, None),
        )

    def test_single_multiplier_combo_inherits_single_thumbnail_only(self):
        self.add("S", "Workbook")
        self.add("C2", "Workbook 2 copies")
        self.add("PLUS", "Workbook+Pencil")
        self.add("C1", "Workbook one copy")
        self.db.set_cost_thumbnail("S", b"single-white-image")
        self.db.cursor.executemany(
            """UPDATE cost_library
               SET product_attribute_is_combo=1, combo_components_json=?
               WHERE spec_code=?""",
            [
                ('[{"spec_code":"S","quantity":2}]', "C2"),
                ('[{"spec_code":"S","quantity":2}]', "PLUS"),
                ('[{"spec_code":"S","quantity":1}]', "C1"),
            ],
        )
        self.db.conn.commit()

        self.assertEqual(self.db.inherit_single_multiplier_combo_thumbnails(), ["C2"])
        self.assertEqual(
            dict(self.db.safe_fetchall(
                "SELECT spec_code, thumbnail_data FROM cost_library WHERE spec_code IN ('C2','PLUS','C1')"
            )),
            {"C2": b"single-white-image", "PLUS": None, "C1": None},
        )
        synced_image_codes = {
            image["spec_code"] for image in self.db.build_cost_sync_snapshot()["images"]
        }
        self.assertIn("C2", synced_image_codes)
        self.assertNotIn("PLUS", synced_image_codes)

    def test_quantity_and_plus_combos_are_suggested_and_recalculate(self):
        self.add("F1", "方格【20张（1本）】")
        self.add("F3", "方格【60张（3本）】", 99, 9)
        self.add("W1", "每日10个单词（30张/本）")
        self.add("W5", "每日10个单词（30张/本）（5本）", 99, 9)
        self.add("C1", "错字默写本（20/本）")
        self.add("C3", "错字默写本(20/本)3本", 99, 9)
        self.add("A", "英语介词")
        self.add("B", "一眼秒懂16大时态")
        self.add("AB", "【两套】英语介词+一眼秒懂16大时态", 99, 9)
        self.add("R3", "成绩登记表  共3本", 99, 9)
        self.add("R4", "成绩登记表  共4本", 99, 9)
        self.add("R1", "成绩登记表")
        self.add("EMPTY", "未填写属性单品", attribute="")
        self.add("ML", "多行属性单品", attribute="尺寸：A5\n彩色单面印刷\n左胶装")
        for index in range(12):
            self.add(f"AB{index}", f"英语介词+一眼秒懂16大时态 {index}", 99, 9)

        self.db.safe_execute(
            """UPDATE cost_library
               SET product_attribute_is_combo=1,
                   combo_components_json='[{"spec_code":"R4","quantity":3}]'
               WHERE spec_code='R3'"""
        )
        self.db.detect_cost_combo_candidates()
        self.assertEqual(
            self.db._cost_combo_family_name("作业完成情况登记表   共2本"),
            self.db._cost_combo_family_name("作业完成情况登记表"),
        )
        flags = dict(self.db.safe_fetchall("SELECT spec_code, product_attribute_is_combo FROM cost_library"))
        self.assertEqual(flags["F1"], 0)
        self.assertEqual(flags["W1"], 0)
        self.assertEqual(flags["C1"], 0)
        self.assertEqual(flags["F3"], 1)
        self.assertEqual(flags["W5"], 1)
        self.assertEqual(flags["C3"], 1)

        self.assertEqual([(item["code"], item["combo_quantity"]) for item in self.db.get_cost_combo_items("F3")], [("F1", 3)])
        self.assertEqual([(item["code"], item["combo_quantity"]) for item in self.db.get_cost_combo_items("W5")], [("W1", 5)])
        self.assertEqual([(item["code"], item["combo_quantity"]) for item in self.db.get_cost_combo_items("C3")], [("C1", 3)])
        self.assertEqual({item["code"] for item in self.db.get_cost_combo_items("AB")}, {"A", "B"})
        self.assertEqual(
            [(item["code"], item["combo_quantity"]) for item in self.db.get_cost_combo_items("R3")],
            [("R1", 3)],
        )
        self.assertEqual(
            [(item["code"], item["combo_quantity"]) for item in self.db.get_cost_combo_items("R4")],
            [("R1", 4)],
        )
        self.assertEqual(
            self.db.safe_fetchall("SELECT product_cost, unit_weight FROM cost_library WHERE spec_code='F3'")[0],
            (3.0, 0.3),
        )

        self.db.save_cost_combo_definition("F3", True, [{"spec_code": "F1", "quantity": 3}], "尺寸：A5")
        row = self.db.safe_fetchall("SELECT product_cost, unit_weight FROM cost_library WHERE spec_code='F3'")[0]
        self.assertEqual(row, (3.0, 0.3))

        self.db.cursor.execute("UPDATE cost_library SET product_cost=2, unit_weight=0.2 WHERE spec_code='F1'")
        self.db.conn.commit()
        self.db.recalculate_cost_combinations_for_components(["F1"])
        row = self.db.safe_fetchall("SELECT product_cost, unit_weight FROM cost_library WHERE spec_code='F3'")[0]
        self.assertEqual(row, (6.0, 0.6))

        app = QApplication.instance() or QApplication([])
        library = CostLibraryDialog(self.db)
        library.cost_mode = "detail"
        library.load_data()
        app.processEvents()
        self.assertEqual(library.load_progress.value(), library.load_progress.maximum())
        self.assertEqual(library.load_progress.maximum(), library.model.rowCount())
        rows_by_code = {
            library.model.item(row, library.COL_CODE).text(): row
            for row in range(library.model.rowCount())
        }
        related_codes = {
            row[2] for row in library._filter_and_sort_rows(
                library._fetch_cost_rows(), "成绩登记表"
            )
        }
        self.assertTrue({"R1", "R3", "R4"}.issubset(related_codes))
        self.assertTrue(library.model.item(rows_by_code["F1"], library.COL_PRODUCT_COST).flags() & Qt.ItemIsEditable)
        for column in (library.COL_PRODUCT_COST, library.COL_UNIT_WEIGHT, library.COL_COST):
            self.assertFalse(library.model.item(rows_by_code["F3"], column).flags() & Qt.ItemIsEditable)
        library._apply_cost_mode_visibility()
        library.show()
        library.activateWindow()
        QTest.qWait(20)
        library.table_view.setFocus()
        QTest.keyClick(library.table_view, Qt.Key_F, Qt.ControlModifier)
        app.processEvents()
        self.assertTrue(library.search_input.hasFocus())
        cost_index = library.model.index(rows_by_code["F1"], library.COL_PRODUCT_COST)
        library.table_view.scrollTo(cost_index)
        app.processEvents()
        QTest.mouseClick(library.table_view.viewport(), Qt.LeftButton, pos=library.table_view.visualRect(cost_index).center())
        app.processEvents()
        self.assertFalse(any(editor.isVisible() for editor in library.table_view.findChildren(QLineEdit)))
        QTest.keyClick(library.table_view, Qt.Key_1)
        QTest.qWait(20)
        cost_editor = QApplication.focusWidget()
        self.assertIsInstance(cost_editor, QLineEdit)
        self.assertEqual(cost_editor.text(), "1")
        QTest.keyClicks(cost_editor, "2.5")
        self.assertEqual(cost_editor.text(), "12.5")
        QTest.keyClick(cost_editor, Qt.Key_Escape)
        reloads = []
        library.load_data = lambda: reloads.append(True)
        library.model.item(rows_by_code["F1"], library.COL_PRODUCT_COST).setText("3.00")
        self.assertEqual(library.model.item(rows_by_code["F3"], library.COL_PRODUCT_COST).text(), "9.00")
        library.save_changes(auto_save=True)
        self.assertEqual(
            self.db.safe_fetchall("SELECT product_cost FROM cost_library WHERE spec_code='F3'")[0][0],
            9.0,
        )
        self.assertEqual(library.model.item(rows_by_code["F3"], library.COL_PRODUCT_COST).text(), "9.00")

        class AcceptedAttributeEditor:
            def __init__(self, *_args, **_kwargs):
                pass

            def exec_(self):
                return QDialog.Accepted

            def is_combo_product(self):
                return False

            def component_items(self):
                return []

            def attribute_text(self):
                return "尺寸：A4"

            def auto_detect_disable_value(self):
                return 1

        attribute_index = library.model.index(rows_by_code["F1"], library.COL_ATTRIBUTE)
        with patch("manager.dialogs.cost_library.ProductAttributeDialog", AcceptedAttributeEditor):
            library.open_product_attribute_editor(attribute_index)
        self.assertEqual(reloads, [])
        self.assertEqual(library.model.item(rows_by_code["F1"], library.COL_ATTRIBUTE).text(), "尺寸：A4")
        self.assertEqual(
            self.db.safe_fetchall("SELECT product_attribute FROM cost_library WHERE spec_code='F1'")[0][0],
            "尺寸：A4",
        )
        library.close()
        app.processEvents()
        editor = ProductAttributeDialog(
            self.db, "", "W5", "每日10个单词（30张/本）（5本）", False, True
        )
        self.assertTrue(editor.combo_check.isChecked())
        self.assertEqual(editor.component_items(), [{"spec_code": "W1", "quantity": 5}])
        self.assertIn("每日10个单词", editor.current_product_label.text())
        self.assertNotIn("F3", {spec["code"] for spec in editor.all_specs})
        self.assertNotIn("AB", {spec["code"] for spec in editor.all_specs})
        self.assertNotIn("R4", {spec["code"] for spec in editor.all_specs})
        self.assertIn("R1", {spec["code"] for spec in editor.all_specs})
        self.assertIn("EMPTY", {spec["code"] for spec in editor.all_specs})
        self.assertGreaterEqual(editor.width(), 1000)
        editor.search_input.setText("EMPTY")
        app.processEvents()
        self.assertEqual(editor.spec_model.item(0, 2).text(), "EMPTY")
        editor.search_input.clear()
        app.processEvents()
        multiline_row = next(
            row for row in range(editor.spec_model.rowCount())
            if editor.spec_model.item(row, 2).text() == "ML"
        )
        self.assertNotIn("\n", editor.spec_model.item(multiline_row, 4).text())
        self.assertIn(" / ", editor.spec_model.item(multiline_row, 4).text())
        chip = editor.selected_content.findChildren(QWidget, "attributeComboChip")[0]
        quantity_input = chip.findChild(QSpinBox)
        self.assertEqual(quantity_input.value(), 5)
        quantity_input.setValue(7)
        self.assertEqual(editor.component_items(), [{"spec_code": "W1", "quantity": 7}])
        name_label = next(label for label in chip.findChildren(QLabel) if label.text() != "×")
        self.assertGreaterEqual(chip.width(), name_label.sizeHint().width() + 100)
        specs_by_code = {spec["code"]: spec for spec in editor.all_specs}
        editor.selected_specs = {
            "A": {**specs_by_code["A"], "attribute": "尺寸：A5\n纸张：75g"},
            "B": {**specs_by_code["B"], "attribute": "尺寸：A4\n纸张：75g"},
        }
        editor.refresh_selected_table()
        editor._update_attribute_preview()
        self.assertEqual(editor.generated_attribute(), "尺寸：A5\n纸张：75g\n尺寸：A4")
        self.assertEqual(editor.attribute_preview.toPlainText(), editor.generated_attribute())
        editor.show()
        app.processEvents()
        QTest.qWait(30)
        self.assertTrue(editor._initial_rows_sized)
        self.assertGreaterEqual(editor.height(), 650)
        self.assertLessEqual(
            max(editor.spec_table.rowHeight(row) for row in range(editor.spec_model.rowCount())),
            80,
        )
        editor.close()
        self.db.detect_cost_combo_candidates = lambda: self.fail("待处理窗口不应重复扫描组合产品")
        original_get_combo_items = self.db.get_cost_combo_items
        review_calls = []

        def stored_combo_items(code, suggest=False):
            review_calls.append(suggest)
            return original_get_combo_items(code, suggest=suggest)

        with patch.object(self.db, "get_cost_combo_items", side_effect=stored_combo_items):
            review = CostComboReviewDialog(self.db)
        self.assertTrue(review_calls)
        self.assertFalse(any(review_calls))
        self.assertGreaterEqual(review.table.rowCount(), 1)
        self.assertEqual(review.table.selectionMode(), QAbstractItemView.ExtendedSelection)
        self.assertTrue(review.table.cellWidget(0, 2).testAttribute(Qt.WA_TransparentForMouseEvents))
        review.table.setFixedHeight(120)
        review.show()
        app.processEvents()
        bulk_before = review.table.rowCount()
        bulk_codes = [review._record(row)["code"] for row in (0, 1)]
        QTest.mouseClick(
            review.table.viewport(), Qt.LeftButton, Qt.NoModifier,
            review.table.visualItemRect(review.table.item(0, 0)).center(),
        )
        QTest.mouseClick(
            review.table.viewport(), Qt.LeftButton, Qt.ControlModifier,
            review.table.visualItemRect(review.table.item(1, 0)).center(),
        )
        self.assertEqual(len(review.table.selectionModel().selectedRows(0)), 2)
        QTest.mouseClick(review.bulk_confirm_button, Qt.LeftButton)
        QTest.qWait(380)
        self.assertEqual(review.table.rowCount(), bulk_before - 2)
        self.assertEqual(
            self.db.safe_fetchall(
                f"SELECT COUNT(*) FROM cost_library WHERE combo_reviewed=1 AND spec_code IN ({','.join('?' for _ in bulk_codes)})",
                tuple(bulk_codes),
            )[0][0],
            2,
        )
        review.table.verticalScrollBar().setValue(review.table.verticalScrollBar().maximum())
        before = review.table.rowCount()
        confirm_button = review.table.cellWidget(before - 1, 3).findChild(QPushButton)
        self.assertEqual(confirm_button.focusPolicy(), Qt.NoFocus)
        QTest.mouseClick(confirm_button, Qt.LeftButton)
        QTest.qWait(380)
        self.assertEqual(review.table.rowCount(), before - 1)
        self.assertEqual(
            review.table.verticalScrollBar().value(), review.table.verticalScrollBar().maximum()
        )
        scroll_bar = review.table.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum() // 2)
        app.processEvents()
        anchor_row = review.table.rowAt(0)
        anchor_code = review._record(anchor_row)["code"]
        middle_row = min(anchor_row + 1, review.table.rowCount() - 1)
        QTest.mouseClick(review.table.cellWidget(middle_row, 3).findChild(QPushButton), Qt.LeftButton)
        QTest.qWait(380)
        self.assertEqual(review._record(review.table.rowAt(0))["code"], anchor_code)

        class AcceptedComboEditor:
            def __init__(self, *_args, **_kwargs):
                pass

            def exec_(self):
                return QDialog.Accepted

            def is_combo_product(self):
                return True

            def component_items(self):
                return [{"spec_code": "A", "quantity": 1}]

            def attribute_text(self):
                return "A5"

            def auto_detect_disable_value(self):
                return 0

        scroll_bar.setValue(scroll_bar.maximum() // 2)
        app.processEvents()
        edit_row = min(review.table.rowAt(0) + 1, review.table.rowCount() - 1)
        with patch.object(review, "edit_current") as open_editor:
            review._edit_from_index(review.table.model().index(edit_row, 1))
            review._edit_from_index(review.table.model().index(edit_row, 2))
            review._edit_from_index(review.table.model().index(edit_row, 0))
        self.assertEqual(open_editor.call_count, 2)
        review.table.setCurrentCell(edit_row, 0)
        app.processEvents()
        edit_code = review._record(edit_row)["code"]
        edit_anchor_code = review._record(review.table.rowAt(0))["code"]
        edit_count = review.table.rowCount()
        review.refresh = lambda: self.fail("编辑组合包含单品不应刷新整张待处理表")
        with patch("manager.dialogs.cost_library.ProductAttributeDialog", AcceptedComboEditor):
            review.edit_current()
        QTest.qWait(380)
        self.assertEqual(review.table.rowCount(), edit_count)
        self.assertEqual(review._record(review.table.rowAt(0))["code"], edit_anchor_code)
        edited_row = review._row_for_code(edit_code)
        self.assertGreaterEqual(edited_row, 0)
        self.assertTrue(any("英语介词" in label.text() for label in review.table.cellWidget(edited_row, 2).findChildren(QLabel)))
        self.assertEqual(
            self.db.safe_fetchall("SELECT combo_reviewed FROM cost_library WHERE spec_code=?", (edit_code,))[0][0],
            0,
        )
        synced = next(
            row for row in self.db.build_cost_sync_snapshot()["rows"] if row["spec_code"] == edit_code
        )
        self.assertEqual(synced["combo_reviewed"], 0)
        self.assertTrue(synced["combo_components_json"])
        QTest.mouseClick(review.table.cellWidget(edited_row, 3).findChild(QPushButton), Qt.LeftButton)
        QTest.qWait(380)
        self.assertEqual(review.table.rowCount(), edit_count - 1)
        self.assertEqual(
            self.db.safe_fetchall("SELECT combo_reviewed FROM cost_library WHERE spec_code=?", (edit_code,))[0][0],
            1,
        )
        review.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()

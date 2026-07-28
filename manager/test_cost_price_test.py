import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QTextEdit

from manager.db import SafeDatabaseManager
from manager.dialogs.cost_library import (
    CostLibraryDialog, CostPriceTestDialog, MultiLineTextEditDelegate,
    SelectAllLineEditDelegate,
)


class _Db:
    def safe_fetchall(self, *_args):
        return []

    def parse_cost_number(self, value, default=None):
        try:
            return float(str(value).replace("%", ""))
        except ValueError:
            return default

    def parse_cost_quantity_factor(self, value):
        return self.parse_cost_number(value, 1)

    def calculate_cost_shipping_fee(self, _weight):
        return 1.7


def test_manual_receipt_calculates_margin():
    app = QApplication.instance() or QApplication([])
    dialog = CostPriceTestDialog(_Db())
    spec = {
        "name": "测试商品", "code": "SKU1", "quantity": "1",
        "product_cost": 2, "unit_weight": 0.2, "misc_fee": 0.3,
        "shipping_fee": 1.7, "cost_price": 4,
    }
    dialog.add_test_row(spec, buy_count="3")
    dialog.test_model.item(0, dialog.TEST_COL_RECEIPT).setText("20")
    assert dialog.test_model.item(0, dialog.TEST_COL_TOTAL_COST).text() == "8.00"
    assert dialog.test_model.item(0, dialog.TEST_COL_PROFIT).text() == "12.00"
    assert dialog.test_model.item(0, dialog.TEST_COL_MARGIN).text() == "60.00%"
    dialog.close()
    app.processEvents()


def test_multiline_editor_focus_out_is_not_closed_twice():
    app = QApplication.instance() or QApplication([])
    delegate = MultiLineTextEditDelegate()
    editor = QTextEdit()
    commits = []
    closes = []
    delegate.commitData.connect(commits.append)
    delegate.closeEditor.connect(closes.append)
    delegate.eventFilter(editor, QEvent(QEvent.FocusOut))
    assert len(commits) == 1
    assert len(closes) <= 1
    editor.close()
    app.processEvents()


def test_category_edit_can_save_after_editor_focus_change(tmp_path):
    app = QApplication.instance() or QApplication([])
    db = SafeDatabaseManager(str(tmp_path / "category-save.db"))
    db.safe_execute(
        "INSERT INTO cost_library (spec_code, spec_name, cost_price, category_label, cost_calc_mode) VALUES (?, ?, ?, ?, ?)",
        ("SKU1", "测试商品", 5, "旧类型", "total"),
    )
    dialog = CostLibraryDialog(db)
    dialog.show()
    app.processEvents()
    assert isinstance(dialog.table_view.itemDelegateForColumn(dialog.COL_CATEGORY), SelectAllLineEditDelegate)
    index = dialog.model.index(0, dialog.COL_CATEGORY)
    dialog.table_view.edit(index)
    app.processEvents()
    editor = QApplication.focusWidget()
    assert editor is not None
    QTest.keyClick(editor, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(editor, "new-category")
    dialog.table_view.setFocus(Qt.OtherFocusReason)
    app.processEvents()
    QTest.qWait(300)
    assert db.safe_fetchall("SELECT category_label FROM cost_library WHERE spec_code='SKU1'")[0][0] == "new-category"
    dialog.close()
    db.conn.close()


def test_cost_library_does_not_rebuild_main_window():
    source = Path("manager/dialogs/cost_library.py").read_text(encoding="utf-8-sig")
    assert "main_window.load_data_safe" not in source
    assert "btn_ai_pick" not in source
    assert "def show_ai_pick" not in source


def test_cost_import_finish_uses_incremental_refresh():
    source = Path("manager/shop_manager.py").read_text(encoding="utf-8-sig")
    body = source.split("def finish_cost_import_refresh", 1)[1].split("def sync_material_library_after_cost_import", 1)[0]
    assert "load_data_safe" not in body
    assert "refresh_external_products" in body
    assert "ps.spec_code IN" in body
    assert "SELECT id FROM products" not in body
    assert "changed_cost_spec_codes.add(spec_code)" in source


def test_cost_library_first_open_does_not_recalculate_every_row():
    source = Path("manager/dialogs/cost_library.py").read_text(encoding="utf-8-sig")
    init_body = source.split("class CostLibraryDialog", 1)[1].split("def _setup_button", 1)[0]
    load_body = source.split("    def load_data(self):", 1)[1].split("    def _configure_column_widths", 1)[0]
    assert "QTimer.singleShot(0, self._run_initial_load)" in init_body
    assert "recalculate_detailed_cost_library" not in init_body
    assert "self.recalculate_row(row_index)" not in load_body

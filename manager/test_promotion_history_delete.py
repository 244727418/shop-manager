import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtWidgets import QApplication, QMessageBox

from manager.dialogs.promotion_data import PromotionImportHistoryDialog


def test_history_supports_multi_select_delete(monkeypatch):
    class Db:
        def __init__(self):
            self.rows = [
                ("2026-07-20", 2, 10, 30, 1, 5, 2, "2026-07-21 10:00:00"),
                ("2026-07-19", 3, 20, 40, 2, 6, 3, "2026-07-20 10:00:00"),
            ]
            self.deleted = ()

        def safe_fetchall(self, _sql, _params=()):
            return self.rows

        def safe_execute(self, _sql, params=()):
            self.deleted = params
            removed = set(params[1:])
            self.rows = [row for row in self.rows if row[0] not in removed]

    app = QApplication.instance() or QApplication([])
    db = Db()
    dialog = PromotionImportHistoryDialog(7, "测试店铺", db)
    dialog.table.selectRow(0)
    dialog.table.selectionModel().select(
        dialog.table.model().index(1, 0),
        QItemSelectionModel.Select | QItemSelectionModel.Rows,
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.Yes)

    dialog.delete_selected_dates()
    app.processEvents()

    assert db.deleted[0] == 7
    assert set(db.deleted[1:]) == {"2026-07-19", "2026-07-20"}
    assert dialog.table.rowCount() == 0
    dialog.close()

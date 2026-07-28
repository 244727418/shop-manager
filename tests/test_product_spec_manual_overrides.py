from PyQt5.QtCore import Qt

from manager.dialogs.product_spec import ProductSpecDialog


class _CheckBox:
    def __init__(self):
        self.checked = False

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked


class _Item:
    def __init__(self, text):
        self.text = text

    def data(self, _role):
        return self.text

    def setData(self, role, value):
        assert role == Qt.DisplayRole
        self.text = value


def test_average_weights_enables_manual_weight_override():
    item = _Item("25.00")
    dialog = type("Dialog", (), {
        "table": type("Table", (), {
            "rowCount": lambda self: 1,
            "item": lambda self, row, column: item,
        })(),
        "COL_WEIGHT": ProductSpecDialog.COL_WEIGHT,
        "chk_manual_weight": _CheckBox(),
        "calculate_all_margins": lambda self: None,
        "_record_undo_step": lambda self: None,
    })()

    ProductSpecDialog.average_weights(dialog)

    assert dialog.chk_manual_weight.isChecked()
    assert item.text == "100.00"

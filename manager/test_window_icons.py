import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog

from manager.window_icons import _title_initial, apply_standard_window_flags, apply_window_icon, get_window_icon


def test_visible_window_flags_are_not_recreated():
    app = QApplication.instance() or QApplication([])
    dialog = QDialog()
    dialog.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
    dialog.show()
    app.processEvents()
    before = int(dialog.windowFlags())

    apply_standard_window_flags(dialog)

    assert int(dialog.windowFlags()) == before
    dialog.close()


def test_window_title_icons_use_the_first_character():
    app = QApplication.instance() or QApplication([])
    assert _title_initial("🏪 店铺毛利管理", "主") == "店"
    assert not get_window_icon("main").isNull()
    dialog = QDialog()
    apply_window_icon(dialog, "cost")
    fallback_icon_key = dialog.windowIcon().cacheKey()
    dialog.setWindowTitle("素材库")
    app.processEvents()
    assert dialog.windowIcon().cacheKey() != fallback_icon_key


if __name__ == "__main__":
    test_visible_window_flags_are_not_recreated()
    test_window_title_icons_use_the_first_character()
    print("window icons OK")

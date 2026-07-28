from PyQt5.QtWidgets import QApplication, QLineEdit, QPushButton

from manager.dialogs.product_spec import ProductSpecDialog


def test_marketing_activity_tag_cancels_and_clears():
    app = QApplication.instance() or QApplication([])
    dialog = type("Dialog", (), {
        "marketing_activity_input": QLineEdit("618活动"),
        "marketing_activity_tag": QPushButton(),
        "btn_marketing": QPushButton(),
        "update_tag_button_styles": lambda self: None,
        "_record_undo_step": lambda self: None,
    })()
    dialog.btn_marketing.setCheckable(True)
    dialog.btn_marketing.setChecked(True)
    dialog._update_marketing_activity_tag = ProductSpecDialog._update_marketing_activity_tag.__get__(dialog)

    dialog._update_marketing_activity_tag()
    assert not dialog.marketing_activity_tag.isHidden()
    assert dialog.marketing_activity_tag.text() == "618活动"

    ProductSpecDialog._cancel_marketing_activity(dialog)
    assert not dialog.btn_marketing.isChecked()
    assert dialog.marketing_activity_input.text() == ""
    assert dialog.marketing_activity_tag.isHidden()
    app.processEvents()

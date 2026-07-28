from manager.dialogs.product_spec import ProductSpecDialog


class _Label:
    def setText(self, text):
        self.text = text


def test_negative_margin_reports_no_break_even_or_scale_roi():
    dialog = type("Dialog", (), {
        "get_current_margin_rate": lambda self: -0.1494,
        "get_return_rate": lambda self: 0.0,
        "on_current_roi_changed": lambda self: None,
    })()
    for name in ("lbl_gross_break_even", "lbl_net_break_even", "lbl_best_roi", "lbl_scale_roi"):
        setattr(dialog, name, _Label())

    ProductSpecDialog.calculate_roi_metrics(dialog)

    assert dialog.lbl_gross_break_even.text == "无法保本"
    assert dialog.lbl_net_break_even.text == "无法保本"
    assert dialog.lbl_best_roi.text == "无法保本"
    assert dialog.lbl_scale_roi.text == "无法放量"

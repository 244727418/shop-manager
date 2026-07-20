from manager.dialogs.input_data_dialog import _normalize_number_text, _parse_number


def test_thousands_separator_is_removed():
    assert _normalize_number_text(" 1,376.72 ") == "1376.72"
    assert _parse_number("1,376.72") == 1376.72
    assert _parse_number("1，376", integer=True) == 1376

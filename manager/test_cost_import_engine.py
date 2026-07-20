import sys
import types

from manager.dialogs.cost_import import _read_cost_file_direct


def test_excel_engine_selection():
    calls = []
    pandas = types.SimpleNamespace(read_excel=lambda path, **kwargs: calls.append(kwargs["engine"]))
    original = sys.modules.get("pandas")
    sys.modules["pandas"] = pandas
    try:
        _read_cost_file_direct("cost.xls")
        _read_cost_file_direct("cost.xlsx")
        _read_cost_file_direct("cost.xlsm")
    finally:
        if original is None:
            sys.modules.pop("pandas", None)
        else:
            sys.modules["pandas"] = original
    assert calls == ["xlrd", "openpyxl", "openpyxl"]


if __name__ == "__main__":
    test_excel_engine_selection()
    print("OK")

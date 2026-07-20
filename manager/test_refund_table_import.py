import zipfile

from openpyxl import Workbook

from manager.dialogs.input_data_dialog import (
    _summarize_refund_rows,
    _summarize_refund_workbook,
)


def test_refund_table_summary_counts_unique_orders_and_sums_amounts(tmp_path):
    rows = [["导出说明"] for _ in range(35)] + [
        ["订单编号", "退款金额"],
        ["1001", "1,200.50"],
        ["1001", 20],
        ["1002", "¥30.25"],
        ["", 999],
        ["1003", ""],
    ]
    assert _summarize_refund_rows(rows) == (1250.75, 2)

    path = tmp_path / "refund.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "退款明细"
    for row in rows:
        sheet.append(row)
    workbook.save(path)

    broken_path = tmp_path / "refund-broken-dimension.xlsx"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(broken_path, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b'<dimension ref="A1:B41"/>', b'<dimension ref="A1:A1"/>')
            target.writestr(item, data)

    assert _summarize_refund_workbook(str(path)) == ((1250.75, 2), "退款明细")
    assert _summarize_refund_workbook(str(broken_path)) == ((1250.75, 2), "退款明细")


def test_refund_headers_can_be_on_adjacent_header_rows():
    rows = [
        ["订单编号", ""],
        ["", "退款金额"],
        ["1001", 12.5],
        ["", 99],
    ]
    assert _summarize_refund_rows(rows) == (12.5, 1)

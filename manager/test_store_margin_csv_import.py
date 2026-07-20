from datetime import datetime

from manager.dialogs.store_margin import StoreMarginDialog


def test_order_import_reader_supports_utf8_and_gb18030_csv(tmp_path):
    expected = [["商品ID", "规格维度", "数量"], ["967384774515", "10001", "2"]]
    for encoding in ("utf-8-sig", "gb18030"):
        path = tmp_path / f"orders-{encoding}.csv"
        path.write_text("商品ID,规格维度,数量\n967384774515,10001,2\n", encoding=encoding)
        assert StoreMarginDialog._read_import_rows(object(), str(path)) == expected


def test_csv_order_dates_with_year_are_formatted_as_month_day():
    parser = type(
        "DateParser",
        (),
        {
            "_parse_order_date_value": StoreMarginDialog._parse_order_date_value,
            "_format_import_order_date": StoreMarginDialog._format_import_order_date,
        },
    )()
    assert parser._format_import_order_date("2026/7/6") == "7/6"
    assert parser._format_import_order_date("2026-07-12 10:20:30") == "7/12"
    assert parser._format_import_order_date(datetime(2026, 7, 12, 10, 20)) == "7/12"

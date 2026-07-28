import sqlite3
from types import SimpleNamespace

from PyQt5.QtCore import QDate

from manager.dialogs.promotion_data import PromotionDataDialog, _promotion_quick_range, _promotion_search_match


def test_promotion_quick_ranges():
    today = QDate(2026, 7, 13)  # 周一
    assert _promotion_quick_range(today, "yesterday") == (QDate(2026, 7, 12), QDate(2026, 7, 12))
    assert _promotion_quick_range(today, "recent_7") == (QDate(2026, 7, 6), QDate(2026, 7, 12))
    assert _promotion_quick_range(today, "last_week") == (QDate(2026, 7, 6), QDate(2026, 7, 12))
    assert _promotion_quick_range(today, "this_week", QDate(2026, 7, 13)) == (QDate(2026, 7, 13), QDate(2026, 7, 13))


def test_promotion_search_supports_exact_and_pinyin():
    row = {"product_id": "967384774515", "product_title": "测试水杯", "link_type": "稳定成本"}
    assert _promotion_search_match(row, "967384774515") == (True, True)
    assert _promotion_search_match(row, "稳定成本") == (True, True)
    assert _promotion_search_match(row, "cssb") == (False, True)
    assert _promotion_search_match(row, "967 shui") == (False, True)


def test_promotion_range_aggregates_by_product():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE products (store_id INTEGER, name TEXT, title TEXT, image_data BLOB, is_archived INTEGER, is_violation INTEGER, link_type TEXT, sort_order INTEGER)")
    conn.execute("""CREATE TABLE promotion_daily_data (
        store_id INTEGER, record_date TEXT, product_id TEXT, product_title TEXT, bid_method TEXT,
        cost REAL, transaction_amount REAL, net_transaction_amount REAL, net_orders REAL,
        impressions REAL, clicks REAL, promotion_impressions REAL, net_profit REAL
    )""")
    conn.execute("INSERT INTO products VALUES (1, '1001', '商品', NULL, 0, 0, '', 1)")
    conn.executemany(
        "INSERT INTO promotion_daily_data VALUES (1, ?, '1001', '商品', '', ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("2026-07-10", 10, 40, 30, 1, 100, 10, 50, 6),
            ("2026-07-11", 20, 50, 45, 2, 200, 20, 100, 9),
        ],
    )
    view = SimpleNamespace(
        store_id=1,
        db=SimpleNamespace(safe_fetchall=lambda sql, params=(): conn.execute(sql, params).fetchall()),
        _selected_range=lambda: (QDate(2026, 7, 10), QDate(2026, 7, 11)),
    )
    row = PromotionDataDialog._fetch_current_rows(view)[0]
    assert row[4:10] == (30.0, 90.0, 3.0, 75.0, 2.5, 3.0)
    assert row[18:20] == (15.0, 20.0)

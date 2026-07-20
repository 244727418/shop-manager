import sqlite3
from types import SimpleNamespace

from PyQt5.QtCore import QDate

from manager.dialogs.promotion_data import PromotionDataDialog, _promotion_quick_range


def test_promotion_quick_ranges():
    today = QDate(2026, 7, 13)  # 周一
    assert _promotion_quick_range(today, "recent_7") == (QDate(2026, 7, 6), QDate(2026, 7, 12))
    assert _promotion_quick_range(today, "last_week") == (QDate(2026, 7, 6), QDate(2026, 7, 12))
    assert _promotion_quick_range(today, "this_week", QDate(2026, 7, 13)) == (QDate(2026, 7, 13), QDate(2026, 7, 13))


def test_promotion_range_aggregates_by_product():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE products (store_id INTEGER, name TEXT, title TEXT, image_data BLOB, is_archived INTEGER, sort_order INTEGER)")
    conn.execute("""CREATE TABLE promotion_daily_data (
        store_id INTEGER, record_date TEXT, product_id TEXT, product_title TEXT, bid_method TEXT,
        cost REAL, transaction_amount REAL, net_transaction_amount REAL, net_orders REAL,
        impressions REAL, clicks REAL, promotion_impressions REAL, net_profit REAL
    )""")
    conn.execute("INSERT INTO products VALUES (1, '1001', '商品', NULL, 0, 1)")
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

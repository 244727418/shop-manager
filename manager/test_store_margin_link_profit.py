import os
import json
import sqlite3
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QWidget

from manager.dialogs.store_margin import StoreMarginDialog


class Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")

    def safe_fetchall(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()


def _profit_view():
    db = Db()
    db.conn.executescript("""
        CREATE TABLE products (id INTEGER, store_id INTEGER, name TEXT);
        CREATE TABLE product_specs (product_id INTEGER, spec_code TEXT);
        CREATE TABLE cost_library (spec_code TEXT, cost_price REAL);
        CREATE TABLE imported_orders (
            store_id INTEGER, product_id TEXT, spec_code TEXT, order_count INTEGER,
            actual_amount REAL, refund_amount REAL, period_start TEXT, period_end TEXT,
            order_date TEXT, import_time TEXT
        );
        CREATE TABLE promotion_daily_data (
            store_id INTEGER, product_id TEXT, record_date TEXT, cost REAL
        );
        INSERT INTO products VALUES (1, 7, 'P1');
        INSERT INTO product_specs VALUES (1, 'A'), (1, 'B');
        INSERT INTO cost_library VALUES ('A', 10), ('B', 15);
        INSERT INTO imported_orders VALUES
            (7, 'P1', 'A', 2, 100, 20, '2026-07-06', '2026-07-12', '7/6~7/12', '2026-07-13 10:00:00'),
            (7, 'P1', 'B', 1, 50, 0, '2026-07-06', '2026-07-12', '7/6~7/12', '2026-07-13 10:00:00');
        INSERT INTO promotion_daily_data VALUES
            (7, 'P1', '2026-07-06', 7),
            (7, 'P1', '2026-07-10', 3);
    """)
    return SimpleNamespace(store_id=7, db=db)


def test_link_profit_uses_current_cost_and_partial_promotion_days():
    view = _profit_view()
    result = StoreMarginDialog._link_profit_breakdown(view, "P1")
    assert result["available"]
    assert result["profit"] == 85

    view.db.conn.execute("UPDATE cost_library SET cost_price=12 WHERE spec_code='A'")
    assert StoreMarginDialog._link_profit_breakdown(view, "P1")["profit"] == 81


def test_link_profit_uses_saved_actual_amount_for_legacy_orders():
    view = _profit_view()
    view.db.conn.execute(
        "UPDATE imported_orders SET refund_amount=NULL, period_start=NULL, period_end=NULL"
    )
    result = StoreMarginDialog._link_profit_breakdown(view, "P1")
    assert result["available"]
    assert result["profit"] == 105
    assert result["refund_amount"] == 0
    assert not result["refund_amount_exact"]

    view.db.conn.execute("DELETE FROM promotion_daily_data")
    assert "无该链接推广数据" in StoreMarginDialog._link_profit_breakdown(view, "P1")["reason"]


def test_link_profit_rejects_legacy_orders_without_actual_amount():
    view = _profit_view()
    view.db.conn.execute("UPDATE imported_orders SET actual_amount=0")
    assert "实收金额" in StoreMarginDialog._link_profit_breakdown(view, "P1")["reason"]


def test_link_profit_display_colors_profit_and_loss():
    app = QApplication.instance() or QApplication([])
    table = QTableWidget(2, 16)
    for row, code in enumerate(("WIN", "LOSS")):
        product = QTableWidgetItem(code)
        product.setData(256, code)
        table.setItem(row, 1, product)
        table.setItem(row, 15, QTableWidgetItem())
    results = {
        "WIN": {"available": True, "profit": 12.5, "actual_amount": 50, "promotion_cost": 5,
                "total_cost": 30, "refund_amount": 2.5, "refund_amount_exact": True,
                "period_start": "2026-07-06", "period_end": "2026-07-12"},
        "LOSS": {"available": True, "profit": -8, "actual_amount": 20, "promotion_cost": 8,
                 "total_cost": 20, "refund_amount": 0, "refund_amount_exact": True,
                 "period_start": "2026-07-06", "period_end": "2026-07-12"},
    }
    view = SimpleNamespace(table=table, _link_profit_breakdown=lambda code: results[code])
    StoreMarginDialog.update_link_profit_display(view)
    app.processEvents()

    assert table.item(0, 15).text() == "¥12.50"
    assert table.item(0, 15).foreground().color() == QColor("#159447")
    assert table.item(1, 15).text() == "-¥8.00"
    assert table.item(1, 15).foreground().color() == QColor("#d32f2f")


def test_link_profit_status_and_sort_helpers():
    host = SimpleNamespace()
    assert StoreMarginDialog._is_effective_shipped_status(host, "已发货退款成功")
    assert StoreMarginDialog._is_effective_shipped_status(host, "已收货")
    assert not StoreMarginDialog._is_effective_shipped_status(host, "待发货退款成功")
    assert StoreMarginDialog._is_refund_status(host, "已收货退款")
    assert StoreMarginDialog._order_table_sort_value(host, 15, "-¥8.25") == -8.25


def test_order_table_reapplies_saved_sort_after_reload():
    app = QApplication.instance() or QApplication([])
    table = QTableWidget(2, 16)
    table.setItem(0, 1, QTableWidgetItem("A"))
    table.setItem(0, 8, QTableWidgetItem("3"))
    table.setItem(1, 1, QTableWidgetItem("B"))
    table.setItem(1, 8, QTableWidgetItem("12"))
    view = SimpleNamespace(
        table=table,
        _order_sort_column=8,
        _order_sort_order=Qt.DescendingOrder,
        _table_cell_text=lambda target, row, col: target.item(row, col).text(),
        _order_table_sort_value=lambda col, text: StoreMarginDialog._order_table_sort_value(None, col, text),
    )

    StoreMarginDialog._apply_order_table_sort(view)
    app.processEvents()

    assert table.item(0, 1).text() == "B"
    assert table.horizontalHeader().sortIndicatorSection() == 8
    assert table.horizontalHeader().sortIndicatorOrder() == Qt.DescendingOrder


def test_sales_amount_comparison_uses_previous_snapshot():
    app = QApplication.instance() or QApplication([])
    table = QTableWidget(1, 16)
    product = QTableWidgetItem("P1")
    product.setData(Qt.UserRole, "P1")
    table.setItem(0, 1, product)
    labels = {}
    for column in (7, 9, 11):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        label = QLabel()
        layout.addWidget(label)
        table.setCellWidget(0, column, widget)
        labels[column] = label

    previous = {
        "weights": {"P1": 100},
        "orders": {"P1_S": {"count": 3, "actual_amount": 300, "dates": ["7/5"]}},
    }

    class CompareDb:
        @staticmethod
        def safe_fetchall(sql, _params=()):
            if "FROM imported_orders" in sql:
                return [("P1", "S", 5, "7/6~7/12", 500)]
            if "FROM import_history" in sql:
                return [(1, json.dumps(previous))]
            return []

    view = SimpleNamespace(
        store_id=1,
        db=CompareDb(),
        table=table,
        product_weights={"P1": {"weight": 100}},
        _normalize_imported_order_store_ids=lambda: None,
    )
    StoreMarginDialog.update_compare_columns(view)
    app.processEvents()
    assert labels[11].text() == "↑¥200.00"
    assert "#27ae60" in labels[11].styleSheet()

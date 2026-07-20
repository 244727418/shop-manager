import sqlite3

import pytest

from manager.db import SafeDatabaseManager


def test_product_delete_is_atomic_and_complete(tmp_path):
    db = SafeDatabaseManager(str(tmp_path / "delete.db"))
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    db.safe_execute("INSERT INTO stores (id, name) VALUES (1, 'store')")
    db.safe_execute("INSERT INTO products (id, store_id, name) VALUES (7, 1, 'code-7')")
    db.safe_execute("INSERT INTO product_specs (product_id, spec_name, spec_code) VALUES (7, 'spec', 'sku')")
    db.safe_execute(
        "INSERT INTO daily_tasks (store_id, product_id, year, month, day, task_content, created_time) "
        "VALUES (1, 7, 2026, 7, 4, 'task', 'now')"
    )
    db.safe_execute(
        "INSERT INTO task_reminders (store_id, product_id, task_content, remind_time, created_time) "
        "VALUES (1, 7, 'reminder', 'now', 'now')"
    )
    db.safe_execute(
        "INSERT INTO imported_orders (store_id, product_id, spec_code, import_time) VALUES (1, 'code-7', 'sku', 'now')"
    )

    db.safe_execute(
        "CREATE TRIGGER block_product_delete BEFORE DELETE ON products "
        "BEGIN SELECT RAISE(ABORT, 'blocked'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.delete_product_cascade(7)
    assert db.safe_fetchall("SELECT COUNT(*) FROM product_specs WHERE product_id=7")[0][0] == 1
    assert db.safe_fetchall("SELECT COUNT(*) FROM daily_tasks WHERE product_id=7")[0][0] == 1

    db.safe_execute("DROP TRIGGER block_product_delete")
    assert db.delete_product_cascade(7)
    for table in ("products", "product_specs", "daily_tasks", "task_reminders"):
        assert db.safe_fetchall(f"SELECT COUNT(*) FROM {table}")[0][0] == 0
    assert db.safe_fetchall("SELECT COUNT(*) FROM imported_orders WHERE product_id='code-7'")[0][0] == 0
    db.conn.close()


def test_init_rejects_incomplete_schema_after_migration_error(tmp_path):
    db_path = tmp_path / "broken.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE cost_library (spec_code TEXT, spec_name TEXT);
        INSERT INTO cost_library VALUES ('DUPLICATE', 'first');
        INSERT INTO cost_library VALUES ('DUPLICATE', 'second');
        CREATE TRIGGER block_cost_cleanup
        BEFORE DELETE ON cost_library
        BEGIN
            SELECT RAISE(ABORT, 'cleanup blocked');
        END;
        """
    )
    conn.close()

    with pytest.raises(RuntimeError, match="数据库结构不完整"):
        SafeDatabaseManager(str(db_path))


def test_init_removes_legacy_knowledge_table(tmp_path):
    db_path = tmp_path / "legacy-knowledge.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE knowledge_base (id INTEGER PRIMARY KEY, content TEXT)")
    conn.execute("INSERT INTO knowledge_base (content) VALUES ('legacy')")
    conn.commit()
    conn.close()

    db = SafeDatabaseManager(str(db_path))
    assert not db.safe_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_base'"
    )
    db.conn.close()


def test_init_migrates_legacy_product_specs_off_shelf_column(tmp_path):
    db_path = tmp_path / "legacy-specs.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE product_specs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            spec_name TEXT NOT NULL,
            spec_code TEXT,
            sale_price REAL,
            weight_percent REAL,
            is_locked INTEGER DEFAULT 0,
            spec_image_data BLOB
        )"""
    )
    conn.execute(
        "INSERT INTO product_specs (product_id, spec_name, spec_code) VALUES (1, 'spec', 'sku')"
    )
    conn.commit()
    conn.close()

    db = SafeDatabaseManager(str(db_path))
    columns = {row[1] for row in db.safe_fetchall("PRAGMA table_info(product_specs)")}
    assert "is_temporarily_off_shelf" in columns
    assert db.safe_fetchall(
        "SELECT is_temporarily_off_shelf FROM product_specs WHERE spec_code='sku'"
    ) == [(0,)]
    db.conn.close()


def test_repair_missing_promotion_profit_uses_shared_margin(tmp_path):
    db = SafeDatabaseManager(str(tmp_path / "promotion-profit.db"))
    db.safe_execute("INSERT INTO stores (id, name) VALUES (1, 'store')")
    db.safe_execute("INSERT INTO products (id, store_id, name) VALUES (7, 1, 'product-7')")
    db.safe_execute("INSERT INTO cost_library (spec_code, cost_price) VALUES ('sku', 4)")
    db.safe_execute(
        "INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent) "
        "VALUES (7, 'spec', 'sku', 10, 100)"
    )
    db.safe_execute(
        "INSERT INTO promotion_daily_data "
        "(store_id, record_date, product_id, cost, net_transaction_amount, imported_at) "
        "VALUES (1, '2026-07-15', 'product-7', 10, 100, 'now')"
    )

    assert db.repair_missing_promotion_profits() == 1
    profit, rate = db.safe_fetchall(
        "SELECT net_profit, net_margin_rate FROM promotion_daily_data"
    )[0]
    assert profit == pytest.approx(49.4)
    assert rate == pytest.approx(49.4)
    db.conn.close()


def test_batch_margin_matches_single_product_calculation(tmp_path):
    db = SafeDatabaseManager(str(tmp_path / "margin.db"))
    db.safe_execute("INSERT INTO stores (id, name) VALUES (1, 'one')")
    db.safe_execute("INSERT INTO stores (id, name) VALUES (2, 'two')")
    db.safe_execute("INSERT INTO products (id, store_id, name) VALUES (7, 1, 'same-code')")
    db.safe_execute("INSERT INTO products (id, store_id, name) VALUES (8, 2, 'same-code')")
    db.safe_execute("INSERT INTO cost_library (spec_code, cost_price) VALUES ('sku-1', 5)")
    db.safe_execute("INSERT INTO cost_library (spec_code, cost_price) VALUES ('sku-2', 15)")
    db.safe_execute(
        "INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent) "
        "VALUES (7, 'a', 'sku-1', 10, 100)"
    )
    db.safe_execute(
        "INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent) "
        "VALUES (8, 'b', 'sku-2', 20, 100)"
    )
    db.safe_execute(
        "INSERT INTO imported_orders (store_id, product_id, spec_code, order_count, import_time) "
        "VALUES (1, 'same-code', 'sku-1', 3, 'now')"
    )

    batch = db.calculate_products_gross_margin_metrics([7, 8])
    for product_id in (7, 8):
        single = db.calculate_product_gross_margin_metrics(product_id)
        assert batch[product_id]["gross_margin_pct"] == pytest.approx(single["gross_margin_pct"])
        assert batch[product_id]["avg_final_price"] == pytest.approx(single["avg_final_price"])
        assert batch[product_id]["recognized_order_count"] == single["recognized_order_count"]
        assert batch[product_id]["spec_count"] == 1
    db.conn.close()


def test_order_import_replace_is_atomic(tmp_path):
    db = SafeDatabaseManager(str(tmp_path / "orders.db"))
    db.safe_execute("INSERT INTO stores (id, name) VALUES (1, 'store')")
    db.safe_execute(
        "INSERT INTO imported_orders (store_id, product_id, spec_code, order_count, import_time) "
        "VALUES (1, 'old', 'old-sku', 1, 'old-time')"
    )
    db.safe_execute(
        "CREATE TRIGGER block_new_order BEFORE INSERT ON imported_orders "
        "WHEN NEW.product_id='new' BEGIN SELECT RAISE(ABORT, 'blocked'); END"
    )
    history = (1, "now", "orders.xlsx", 1, 1, 2, 20.0, "{}")
    rows = [(1, "new", "new-sku", 2, "now", None, 20.0, 0)]

    with pytest.raises(sqlite3.IntegrityError):
        db.replace_imported_orders(1, history, rows)

    assert db.safe_fetchall(
        "SELECT product_id, spec_code FROM imported_orders WHERE store_id=1"
    ) == [("old", "old-sku")]
    assert db.safe_fetchall("SELECT COUNT(*) FROM import_history")[0][0] == 0
    db.conn.close()


def test_product_weights_save_is_atomic(tmp_path):
    db = SafeDatabaseManager(str(tmp_path / "weights.db"))
    db.safe_execute("INSERT INTO stores (id, name) VALUES (1, 'store')")
    db.safe_execute("INSERT INTO products (id, store_id, name, store_weight) VALUES (7, 1, 'a', 10)")
    db.safe_execute("INSERT INTO products (id, store_id, name, store_weight) VALUES (8, 1, 'b', 20)")
    db.safe_execute(
        "CREATE TRIGGER block_weight BEFORE UPDATE ON products WHEN NEW.id=8 "
        "BEGIN SELECT RAISE(ABORT, 'blocked'); END"
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.save_product_weights([(30, 0, 7), (40, 1, 8)])

    assert db.safe_fetchall("SELECT id, store_weight FROM products ORDER BY id") == [(7, 10.0), (8, 20.0)]
    db.conn.close()

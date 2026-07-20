import os
import sqlite3
import sys
import tempfile

from manager.db import SafeDatabaseManager


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE imported_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                spec_code TEXT NOT NULL,
                order_count INTEGER DEFAULT 1,
                import_time TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO imported_orders (store_id, product_id, spec_code, order_count, import_time) VALUES (1, 123, 'A', 2, 'now')"
        )
        conn.commit()
        conn.close()

        db = SafeDatabaseManager(path)
        info = {row[1]: row[2].upper() for row in db.cursor.execute("PRAGMA table_info(imported_orders)")}
        assert info["product_id"] == "TEXT", info
        assert {"order_date", "actual_amount", "refund_count"} <= set(info), info
        db.conn.close()
        print("OK")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    main()

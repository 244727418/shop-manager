# -*- coding: utf-8 -*-
"""
数据库访问层：SafeDatabaseManager。
负责 SQLite 连接、表结构、迁移和 CRUD。
"""
import os
import sys
import re
import base64
import json
import sqlite3
import hashlib
import hmac
import math
import time
from datetime import datetime

try:
    from manager.crash_report import append_exception
except ImportError:
    try:
        from crash_report import append_exception
    except ImportError:
        append_exception = None

try:
    from manager.data_root import DataRootManager
except ImportError:
    try:
        from data_root import DataRootManager
    except ImportError:
        DataRootManager = None


class SafeDatabaseManager:
    """安全的数据库管理类，增加错误处理"""

    CATEGORY_COLORS = [
        "#FFF2CC", "#DDEBF7", "#E2F0D9", "#FCE4D6", "#E4DFEC",
        "#D9EAD3", "#F4CCCC", "#D0E0E3", "#FCE5CD", "#D9D2E9",
        "#CFE2F3", "#EADCF8", "#D5E8D4", "#FFE599", "#D9EAF7",
    ]
    DEFAULT_COST_SHIPPING_RULES = {
        "ranges": [
            {"min": 0, "max": 0.5, "fee": 1.7},
            {"min": 0.5, "max": 1, "fee": 1.9},
            {"min": 1, "max": 2, "fee": 2.9},
            {"min": 2, "max": 3, "fee": 3.2},
        ],
        "over": {
            "threshold": 3,
            "base_fee": 2.5,
            "deduct_weight": 1,
            "step_weight": 1,
            "step_fee": 1,
        },
    }
    COMMON_SETTING_PREFIXES = ("ai_", "quick_hotkey_", "update_")
    COMMON_SETTING_KEYS = {"auto_start_enabled", "app_font"}
    ACCOUNT_COST_SETTING_KEYS = (
        "cost_library_mode",
        "cost_misc_fee",
        "cost_shipping_rules_json",
    )

    def __init__(self, db_name="shop_manager.db"):
        try:
            if os.path.isabs(str(db_name)):
                db_path = str(db_name)
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
            else:
                if getattr(sys, 'frozen', False):
                    script_dir = os.path.dirname(sys.executable)
                else:
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                db_path = os.path.join(script_dir, db_name)
            self.db_path = db_path
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.cursor = self.conn.cursor()
            self.init_db()
            self._migrate_legacy_common_cost_settings()
        except Exception as e:
            if append_exception:
                append_exception("database initialization", e)
            print(f"数据库初始化失败: {e}")
            raise

    def init_db(self):
        migrated_off_shelf_column = False
        try:
            self.cursor.execute("DROP TABLE IF EXISTS knowledge_base")
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS stores 
                                (id INTEGER PRIMARY KEY, name TEXT, sort_order INTEGER, memo TEXT, store_discount_rules TEXT)''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                                (id INTEGER PRIMARY KEY, store_id INTEGER, name TEXT, 
                                url TEXT, image_path TEXT, sort_order INTEGER,
                                created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS records 
                                (product_id INTEGER, year INTEGER, month INTEGER, day INTEGER, 
                                records_json TEXT, PRIMARY KEY(product_id, year, month, day))''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS product_image_history
                                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 product_id INTEGER NOT NULL,
                                 image_data BLOB NOT NULL,
                                 changed_at TEXT NOT NULL,
                                 source TEXT)''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                                (key TEXT PRIMARY KEY, value TEXT)''')

            self.cursor.execute("PRAGMA table_info(stores)")
            store_columns = [col[1] for col in self.cursor.fetchall()]
            if 'memo' not in store_columns:
                self.cursor.execute("ALTER TABLE stores ADD COLUMN memo TEXT")
                print("已添加memo字段到stores表")
            if 'weight_synced' not in store_columns:
                self.cursor.execute("ALTER TABLE stores ADD COLUMN weight_synced INTEGER DEFAULT 0")
                print("已添加weight_synced字段到stores表")
            if 'image_data' not in store_columns:
                self.cursor.execute("ALTER TABLE stores ADD COLUMN image_data BLOB")
                print("已添加image_data字段到stores表")
            if 'sitewide_roi' not in store_columns:
                self.cursor.execute("ALTER TABLE stores ADD COLUMN sitewide_roi REAL DEFAULT 0")
                print("已添加sitewide_roi字段到stores表")
            if 'store_discount_rules' not in store_columns:
                self.cursor.execute("ALTER TABLE stores ADD COLUMN store_discount_rules TEXT")
                print("已添加store_discount_rules字段到stores表")

            self.cursor.execute("PRAGMA table_info(products)")
            columns = [col[1] for col in self.cursor.fetchall()]
            if 'title' not in columns:
                self.cursor.execute("ALTER TABLE products ADD COLUMN title TEXT")
                print("已添加title字段到products表")

            if 'coupon_amount' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN coupon_amount REAL DEFAULT 0")
                    print("✅ 已添加coupon_amount字段到products表")
                except Exception as e:
                    print(f"添加coupon_amount字段失败: {e}")

            if 'new_customer_discount' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN new_customer_discount REAL DEFAULT 0")
                    print("✅ 已添加new_customer_discount字段到products表")
                except Exception as e:
                    print(f"添加new_customer_discount字段失败: {e}")

            if 'store_weight' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN store_weight REAL DEFAULT 0")
                    print("✅ 已添加store_weight字段到products表")
                except Exception as e:
                    print(f"添加store_weight字段失败: {e}")

            if 'store_weight_locked' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN store_weight_locked INTEGER DEFAULT 0")
                    print("✅ 已添加store_weight_locked字段到products表")
                except Exception as e:
                    print(f"添加store_weight_locked字段失败: {e}")

            if 'current_roi' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN current_roi REAL DEFAULT 0")
                    print("✅ 已添加current_roi字段到products表")
                except Exception as e:
                    print(f"添加current_roi字段失败: {e}")
            if 'use_manual_spec_weight' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN use_manual_spec_weight INTEGER DEFAULT 0")
                    print("added use_manual_spec_weight column to products")
                except Exception as e:
                    print(f"add use_manual_spec_weight failed: {e}")
            if 'transaction_bid' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN transaction_bid REAL DEFAULT 0")
                    print("✅ 已添加transaction_bid字段到products表")
                except Exception as e:
                    print(f"添加transaction_bid字段失败: {e}")

            if 'return_rate' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN return_rate REAL DEFAULT 0")
                    print("✅ 已添加return_rate字段到products表")
                except Exception as e:
                    print(f"添加return_rate字段失败: {e}")
            if 'use_manual_return_rate' not in columns:
                self.cursor.execute("ALTER TABLE products ADD COLUMN use_manual_return_rate INTEGER DEFAULT 0")

            if 'is_limited_time' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN is_limited_time INTEGER DEFAULT 0")
                    print("✅ 已添加is_limited_time字段到products表")
                except Exception as e:
                    print(f"添加is_limited_time字段失败: {e}")

            if 'is_marketing' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN is_marketing INTEGER DEFAULT 0")
                    print("✅ 已添加is_marketing字段到products表")
                except Exception as e:
                    print(f"添加is_marketing字段失败: {e}")
            if 'marketing_activity' not in columns:
                self.cursor.execute("ALTER TABLE products ADD COLUMN marketing_activity TEXT DEFAULT ''")

            if 'is_natural_flow' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN is_natural_flow INTEGER DEFAULT 0")
                    print("✅ 已添加is_natural_flow字段到products表")
                except Exception as e:
                    print(f"添加is_natural_flow字段失败: {e}")

            if 'is_sitewide_managed' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN is_sitewide_managed INTEGER DEFAULT 0")
                    print("✅ 已添加is_sitewide_managed字段到products表")
                except Exception as e:
                    print(f"添加is_sitewide_managed字段失败: {e}")

            if 'profit_status' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN profit_status INTEGER DEFAULT 0")
                    print("✅ 已添加profit_status字段到products表")
                except Exception as e:
                    print(f"添加profit_status字段失败: {e}")

            self.cursor.execute("PRAGMA table_info(products)")
            columns = [col[1] for col in self.cursor.fetchall()]
            if 'net_break_even_roi' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN net_break_even_roi REAL DEFAULT 0")
                    print("✅ 已添加net_break_even_roi字段到products表")
                except Exception as e:
                    print(f"添加net_break_even_roi字段失败: {e}")
            if 'image_data' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN image_data BLOB")
                    print("✅ 已添加image_data字段到products表")
                except Exception as e:
                    print(f"添加image_data字段失败: {e}")

            if 'product_category_label' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN product_category_label TEXT")
                    print("✅ 已添加product_category_label字段到products表")
                except Exception as e:
                    print(f"添加product_category_label字段失败: {e}")
            if 'product_memo' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN product_memo TEXT")
                    print("✅ 已添加product_memo字段到products表")
                except Exception as e:
                    print(f"添加product_memo字段失败: {e}")
            if 'link_combo_id' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN link_combo_id INTEGER")
                    print("已添加link_combo_id字段到products表")
                except Exception as e:
                    print(f"添加link_combo_id字段失败: {e}")
            if 'link_type' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN link_type TEXT")
                    print("已添加link_type字段到products表")
                except Exception as e:
                    print(f"添加link_type字段失败: {e}")
            if 'roi_input_mode' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN roi_input_mode TEXT DEFAULT 'roi'")
                    print("已添加roi_input_mode字段到products表")
                except Exception as e:
                    print(f"添加roi_input_mode字段失败: {e}")
            if 'is_archived' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN is_archived INTEGER DEFAULT 0")
                    print("已添加is_archived字段到products表")
                except Exception as e:
                    print(f"添加is_archived字段失败: {e}")
            if 'archived_at' not in columns:
                try:
                    self.cursor.execute("ALTER TABLE products ADD COLUMN archived_at TEXT")
                    print("已添加archived_at字段到products表")
                except Exception as e:
                    print(f"添加archived_at字段失败: {e}")
            if 'is_violation' not in columns:
                self.cursor.execute("ALTER TABLE products ADD COLUMN is_violation INTEGER DEFAULT 0")
                print("已添加is_violation字段到products表")
            if 'created_at' not in columns:
                self.cursor.execute("ALTER TABLE products ADD COLUMN created_at TEXT")
                self.cursor.execute(
                    "UPDATE products SET created_at=datetime('2000-01-01', printf('+%d seconds', id)) "
                    "WHERE COALESCE(created_at, '')=''"
                )
                print("已添加created_at字段到products表")
            self.cursor.execute('''CREATE TRIGGER IF NOT EXISTS products_fill_created_at
                                   AFTER INSERT ON products
                                   WHEN COALESCE(NEW.created_at, '')=''
                                   BEGIN
                                       UPDATE products SET created_at=CURRENT_TIMESTAMP WHERE id=NEW.id;
                                   END''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS cost_library 
                                (spec_code TEXT PRIMARY KEY, spec_name TEXT, cost_price REAL, test_price REAL,
                                 quantity TEXT, sort_order INTEGER, source_bg_color TEXT,
                                 category_label TEXT, category_color TEXT)''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS cost_history (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                spec_code TEXT NOT NULL,
                                old_cost_price REAL,
                                new_cost_price REAL NOT NULL,
                                change_amount REAL,
                                change_percent REAL,
                                source TEXT NOT NULL,
                                import_time TEXT NOT NULL)''')

            self.cursor.execute("PRAGMA table_info(cost_history)")
            history_columns = {col[1] for col in self.cursor.fetchall()}
            for column, definition in (
                ("event_id", "TEXT"),
                ("spec_name", "TEXT"),
                ("operation_type", "TEXT DEFAULT 'price'"),
                ("old_value", "TEXT"),
                ("new_value", "TEXT"),
                ("event_time_ms", "INTEGER"),
            ):
                if column not in history_columns:
                    self.cursor.execute(f"ALTER TABLE cost_history ADD COLUMN {column} {definition}")
            self.cursor.execute(
                "UPDATE cost_history SET event_id=LOWER(HEX(RANDOMBLOB(16))) WHERE COALESCE(event_id, '')=''"
            )
            self.cursor.execute(
                """UPDATE cost_history
                   SET spec_name=COALESCE(NULLIF(spec_name, ''),
                       (SELECT spec_name FROM cost_library WHERE cost_library.spec_code=cost_history.spec_code), ''),
                       operation_type=COALESCE(NULLIF(operation_type, ''), 'price'),
                        old_value=COALESCE(old_value, CAST(old_cost_price AS TEXT)),
                        new_value=COALESCE(new_value, CAST(new_cost_price AS TEXT)),
                        event_time_ms=COALESCE(event_time_ms,
                            CAST((JULIANDAY(import_time, 'utc')-2440587.5)*86400000 AS INTEGER))"""
            )
            self.cursor.execute(
                "DELETE FROM cost_history WHERE COALESCE(operation_type, 'price')='price'"
            )
            self.cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_cost_history_event_id ON cost_history(event_id)"
            )
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cost_history_time_type ON cost_history(event_time_ms, operation_type)"
            )
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS cost_history_control (
                id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'manual')''')
            self.cursor.execute(
                "INSERT OR IGNORE INTO cost_history_control (id, enabled, source) VALUES (1, 1, 'manual')"
            )
            self.cursor.execute(
                "UPDATE cost_history_control SET enabled=1, source='manual' WHERE id=1"
            )

            self.cursor.execute("PRAGMA table_info(cost_library)")
            cost_columns = [col[1] for col in self.cursor.fetchall()]
            if 'spec_name' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN spec_name TEXT")
                    print("✅ 已添加spec_name字段到cost_library表")
                except Exception as e:
                    print(f"添加spec_name字段失败: {e}")
            if 'test_price' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN test_price REAL")
                    print("✅ 已添加test_price字段到cost_library表")
                except Exception as e:
                    print(f"添加test_price字段失败: {e}")
            if 'quantity' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN quantity TEXT")
                    print("✅ 已添加quantity字段到cost_library表")
                except Exception as e:
                    print(f"添加quantity字段失败: {e}")
            if 'sort_order' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN sort_order INTEGER")
                    print("✅ 已添加sort_order字段到cost_library表")
                except Exception as e:
                    print(f"添加sort_order字段失败: {e}")
            if 'source_bg_color' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN source_bg_color TEXT")
                    print("✅ 已添加source_bg_color字段到cost_library表")
                except Exception as e:
                    print(f"添加source_bg_color字段失败: {e}")
            if 'category_label' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN category_label TEXT")
                    print("✅ 已添加category_label字段到cost_library表")
                except Exception as e:
                    print(f"添加category_label字段失败: {e}")
            if 'category_color' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN category_color TEXT")
                    print("✅ 已添加category_color字段到cost_library表")
                except Exception as e:
                    print(f"添加category_color字段失败: {e}")
            if 'product_attribute' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN product_attribute TEXT")
                    print("已添加product_attribute字段到cost_library表")
                except Exception as e:
                    print(f"添加product_attribute字段失败: {e}")
            if 'product_attribute_combo_disabled' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN product_attribute_combo_disabled INTEGER DEFAULT 0")
                    print("已添加product_attribute_combo_disabled字段到cost_library表")
                except Exception as e:
                    print(f"添加product_attribute_combo_disabled字段失败: {e}")
            if 'product_attribute_is_combo' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN product_attribute_is_combo INTEGER DEFAULT 0")
                    print("已添加product_attribute_is_combo字段到cost_library表")
                except Exception as e:
                    print(f"添加product_attribute_is_combo字段失败: {e}")
            if 'combo_components_json' not in cost_columns:
                self.cursor.execute("ALTER TABLE cost_library ADD COLUMN combo_components_json TEXT")
            if 'combo_reviewed' not in cost_columns:
                self.cursor.execute("ALTER TABLE cost_library ADD COLUMN combo_reviewed INTEGER DEFAULT 0")
            if 'manual_sort_order' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN manual_sort_order INTEGER")
                    print("✅ 已添加manual_sort_order字段到cost_library表")
                except Exception as e:
                    print(f"添加manual_sort_order字段失败: {e}")
            if 'product_cost' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN product_cost REAL")
                    print("已添加product_cost字段到cost_library表")
                except Exception as e:
                    print(f"添加product_cost字段失败: {e}")
            if 'unit_weight' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN unit_weight REAL")
                    print("已添加unit_weight字段到cost_library表")
                except Exception as e:
                    print(f"添加unit_weight字段失败: {e}")
            if 'shipping_fee' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN shipping_fee REAL")
                    print("已添加shipping_fee字段到cost_library表")
                except Exception as e:
                    print(f"添加shipping_fee字段失败: {e}")
            if 'misc_fee' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN misc_fee REAL")
                    print("已添加misc_fee字段到cost_library表")
                except Exception as e:
                    print(f"添加misc_fee字段失败: {e}")
            if 'cost_calc_mode' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN cost_calc_mode TEXT")
                    print("已添加cost_calc_mode字段到cost_library表")
                except Exception as e:
                    print(f"添加cost_calc_mode字段失败: {e}")
            if 'thumbnail_data' not in cost_columns:
                self.cursor.execute("ALTER TABLE cost_library ADD COLUMN thumbnail_data BLOB")
            if 'thumbnail_manual' not in cost_columns:
                self.cursor.execute("ALTER TABLE cost_library ADD COLUMN thumbnail_manual INTEGER DEFAULT 0")

            self.cursor.executescript('''
                DROP TRIGGER IF EXISTS cost_library_operation_history;
                CREATE TRIGGER cost_library_operation_history AFTER UPDATE ON cost_library
                WHEN COALESCE((SELECT enabled FROM cost_history_control WHERE id=1), 1)=1
                BEGIN
                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         old_cost_price, new_cost_price, change_amount, change_percent,
                         source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''),
                           'product_cost', CAST(OLD.product_cost AS TEXT), CAST(NEW.product_cost AS TEXT),
                           OLD.product_cost, NEW.product_cost,
                           NEW.product_cost - OLD.product_cost,
                           CASE WHEN OLD.product_cost<>0
                                THEN (NEW.product_cost - OLD.product_cost) * 100.0 / OLD.product_cost
                           END,
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                     WHERE COALESCE(NEW.product_attribute_is_combo, 0)=0
                       AND LOWER(COALESCE(NEW.cost_calc_mode, 'total'))='detail'
                       AND OLD.product_cost IS NOT NULL AND NEW.product_cost IS NOT NULL
                       AND ABS(OLD.product_cost-NEW.product_cost)>0.000001;

                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         new_cost_price, source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''), 'code',
                           COALESCE(OLD.spec_code, ''), COALESCE(NEW.spec_code, ''), COALESCE(NEW.cost_price, 0),
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                    WHERE OLD.spec_code IS NOT NEW.spec_code;

                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         new_cost_price, source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''), 'name',
                           COALESCE(OLD.spec_name, ''), COALESCE(NEW.spec_name, ''), COALESCE(NEW.cost_price, 0),
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                    WHERE OLD.spec_name IS NOT NEW.spec_name;

                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         new_cost_price, source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''), 'attribute',
                           COALESCE(OLD.product_attribute, ''), COALESCE(NEW.product_attribute, ''), COALESCE(NEW.cost_price, 0),
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                    WHERE OLD.product_attribute IS NOT NEW.product_attribute;

                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         new_cost_price, source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''), 'image',
                           CASE WHEN LENGTH(COALESCE(OLD.thumbnail_data, X''))>0 THEN '已有图片' ELSE '无图片' END,
                           CASE WHEN LENGTH(COALESCE(NEW.thumbnail_data, X''))>0 THEN '已有图片' ELSE '无图片' END,
                           COALESCE(NEW.cost_price, 0),
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                    WHERE OLD.thumbnail_data IS NOT NEW.thumbnail_data;

                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         new_cost_price, source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''), 'category',
                           COALESCE(OLD.category_label, ''), COALESCE(NEW.category_label, ''), COALESCE(NEW.cost_price, 0),
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                    WHERE OLD.category_label IS NOT NEW.category_label;

                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         new_cost_price, source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''), 'quantity',
                           COALESCE(OLD.quantity, ''), COALESCE(NEW.quantity, ''), COALESCE(NEW.cost_price, 0),
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                    WHERE OLD.quantity IS NOT NEW.quantity;

                    INSERT INTO cost_history
                        (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                         new_cost_price, source, import_time, event_time_ms)
                    SELECT LOWER(HEX(RANDOMBLOB(16))), NEW.spec_code, COALESCE(NEW.spec_name, ''), 'weight',
                           CAST(OLD.unit_weight AS TEXT), CAST(NEW.unit_weight AS TEXT), COALESCE(NEW.cost_price, 0),
                           COALESCE((SELECT source FROM cost_history_control WHERE id=1), 'manual'),
                           STRFTIME('%Y-%m-%d %H:%M:%f', 'now', 'localtime'),
                           CAST((JULIANDAY('now')-2440587.5)*86400000 AS INTEGER)
                    WHERE COALESCE(NEW.product_attribute_is_combo, 0)=0
                      AND OLD.unit_weight IS NOT NEW.unit_weight;
                END;
            ''')

            try:
                # 老版本数据库可能没有 spec_code 唯一约束；先保留最新 rowid，再补唯一索引。
                self.cursor.execute("""
                    DELETE FROM cost_library
                    WHERE spec_code IS NOT NULL
                      AND rowid NOT IN (
                          SELECT MAX(rowid)
                          FROM cost_library
                          WHERE spec_code IS NOT NULL
                          GROUP BY spec_code
                      )
                """)
                self.cursor.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_cost_library_spec_code_unique ON cost_library(spec_code)"
                )
            except Exception as e:
                print(f"修复cost_library规格编码唯一约束失败: {e}")

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS cost_categories (
                label TEXT PRIMARY KEY,
                color TEXT,
                sort_order INTEGER,
                created_at TEXT
            )''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS link_combinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER,
                created_at TEXT
            )''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS product_specs 
                                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                product_id INTEGER NOT NULL,
                                spec_name TEXT NOT NULL,
                                spec_code TEXT,
                                sale_price REAL,
                                weight_percent REAL,
                                is_locked INTEGER DEFAULT 0,
                                is_temporarily_off_shelf INTEGER DEFAULT 0,
                                spec_image_data BLOB,
                                FOREIGN KEY (product_id) REFERENCES products (id))''')
            self.cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_specs_spec_code ON product_specs(spec_code)"
            )

            self.cursor.execute("PRAGMA table_info(product_specs)")
            spec_columns = [col[1] for col in self.cursor.fetchall()]
            if 'is_locked' not in spec_columns:
                try:
                    self.cursor.execute("ALTER TABLE product_specs ADD COLUMN is_locked INTEGER DEFAULT 0")
                    print("✅ 已添加is_locked字段到product_specs表")
                except Exception as e:
                    print(f"添加is_locked字段失败: {e}")
            if 'spec_image_data' not in spec_columns:
                try:
                    self.cursor.execute("ALTER TABLE product_specs ADD COLUMN spec_image_data BLOB")
                    print("✅ 已添加spec_image_data字段到product_specs表")
                except Exception as e:
                    print(f"添加spec_image_data字段失败: {e}")
            if 'is_temporarily_off_shelf' not in spec_columns:
                self.cursor.execute(
                    "ALTER TABLE product_specs ADD COLUMN is_temporarily_off_shelf INTEGER DEFAULT 0"
                )
                migrated_off_shelf_column = True
                print("已添加is_temporarily_off_shelf字段到product_specs表")

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS profit_records 
                                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                data_type TEXT NOT NULL,
                                target_id INTEGER,
                                target_name TEXT,
                                record_date TEXT NOT NULL,
                                promotion_amount REAL,
                                roi REAL,
                                return_rate REAL,
                                margin_rate REAL,
                                avg_price REAL,
                                transaction_amount REAL,
                                refund_amount REAL,
                                actual_transaction_amount REAL,
                                product_cost REAL,
                                gross_profit REAL,
                                tech_fee REAL,
                                net_profit REAL,
                                net_profit_rate REAL,
                                promotion_ratio REAL,
                                break_even_roi REAL,
                                transaction_count REAL,
                                cost_per_transaction REAL,
                                profit_per_transaction REAL,
                                best_roi REAL,
                                net_break_even_roi REAL,
                                net_break_even_125 REAL,
                                net_break_even_value REAL,
                                net_break_even_125_from_net REAL,
                                best_roi_from_net REAL,
                                current_roi_multiple REAL,
                                created_at TEXT)''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS ai_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                is_system INTEGER DEFAULT 0,
                created_at TEXT)''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS ai_common_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT)''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS daily_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                record_date TEXT NOT NULL,
                category TEXT,
                special_info TEXT,
                memo TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(store_id, record_date))''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS store_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                prompt_text TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(store_id))''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS cost_sync_state (
                group_id TEXT PRIMARY KEY,
                group_name TEXT,
                role TEXT NOT NULL DEFAULT 'client',
                coordinator_host TEXT,
                secret TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0,
                snapshot_json TEXT,
                snapshot_hash TEXT,
                publisher_id TEXT,
                published_at TEXT,
                xlsx_path TEXT,
                mapping_json TEXT,
                file_signature TEXT
            )''')
            self.conn.commit()

            self.cursor.execute("PRAGMA table_info(daily_records)")
            daily_columns = [col[1] for col in self.cursor.fetchall()]
            if 'category' not in daily_columns:
                try:
                    self.cursor.execute("ALTER TABLE daily_records ADD COLUMN category TEXT")
                    print("✅ 已添加category字段到daily_records表")
                except Exception as e:
                    print(f"添加category字段失败: {e}")

            if 'special_info' not in daily_columns:
                try:
                    self.cursor.execute("ALTER TABLE daily_records ADD COLUMN special_info TEXT")
                    print("✅ 已添加special_info字段到daily_records表")
                except Exception as e:
                    print(f"添加special_info字段失败: {e}")

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS store_records (
                store_id INTEGER NOT NULL, year INTEGER, month INTEGER, day INTEGER, 
                records_json TEXT, PRIMARY KEY(store_id, year, month, day))''')

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS imported_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                spec_code TEXT NOT NULL,
                order_count INTEGER DEFAULT 1,
                import_time TEXT NOT NULL,
                order_date TEXT,
                actual_amount REAL DEFAULT 0,
                refund_count INTEGER DEFAULT 0,
                refund_amount REAL,
                period_start TEXT,
                period_end TEXT,
                UNIQUE(store_id, product_id, spec_code))''')
            
            # 创建订单导入历史记录表
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS import_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                import_time TEXT NOT NULL,
                file_name TEXT,
                total_products INTEGER DEFAULT 0,
                total_specs INTEGER DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                total_amount REAL DEFAULT 0,
                snapshot_data TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')
            print("✅ 订单导入历史记录表已创建")

            self.cursor.execute("PRAGMA table_info(imported_orders)")
            imported_columns = [col[1] for col in self.cursor.fetchall()]

            if 'product_id' not in imported_columns:
                try:
                    self.cursor.execute("ALTER TABLE imported_orders ADD COLUMN product_id TEXT")
                    print("✅ 已添加product_id字段到imported_orders表")
                except Exception as e:
                    print(f"添加product_id字段失败: {e}")
            if 'order_date' not in imported_columns:
                try:
                    self.cursor.execute("ALTER TABLE imported_orders ADD COLUMN order_date TEXT")
                    print("✅ 已添加order_date字段到imported_orders表")
                except Exception as e:
                    print(f"添加order_date字段失败: {e}")
            if 'actual_amount' not in imported_columns:
                try:
                    self.cursor.execute("ALTER TABLE imported_orders ADD COLUMN actual_amount REAL DEFAULT 0")
                    print("✅ 已添加actual_amount字段到imported_orders表")
                except Exception as e:
                    print(f"添加actual_amount字段失败: {e}")
            if 'refund_count' not in imported_columns:
                try:
                    self.cursor.execute("ALTER TABLE imported_orders ADD COLUMN refund_count INTEGER DEFAULT 0")
                    print("✅ 已添加refund_count字段到imported_orders表")
                except Exception as e:
                    print(f"添加refund_count字段失败: {e}")
            for column_name, column_type in (
                ('refund_amount', 'REAL'),
                ('period_start', 'TEXT'),
                ('period_end', 'TEXT'),
            ):
                if column_name not in imported_columns:
                    try:
                        self.cursor.execute(f"ALTER TABLE imported_orders ADD COLUMN {column_name} {column_type}")
                        print(f"✅ 已添加{column_name}字段到imported_orders表")
                    except Exception as e:
                        print(f"添加{column_name}字段失败: {e}")

            self.cursor.execute("PRAGMA table_info(imported_orders)")
            imported_info = self.cursor.fetchall()
            imported_types = {col[1]: str(col[2] or "").upper() for col in imported_info}
            if imported_types.get('product_id') != 'TEXT':
                print("🔄 检测到 imported_orders.product_id 不是 TEXT，开始迁移...")
                self._migrate_imported_orders_product_id_to_text()

            # 检查并迁移 import_history.snapshot_data（旧数据格式转换）
            self._migrate_import_history_snapshot_data()

            self.cursor.execute("PRAGMA table_info(profit_records)")
            columns = [col[1] for col in self.cursor.fetchall()]
            required_columns = {
                'profit_per_transaction': 'REAL',
                'best_roi': 'REAL',
                'net_break_even_roi': 'REAL',
                'net_break_even_125': 'REAL',
                'net_break_even_value': 'REAL',
                'net_break_even_125_from_net': 'REAL',
                'best_roi_from_net': 'REAL',
                'current_roi_multiple': 'REAL',
                'ai_analysis': 'TEXT'
            }
            for col_name, col_type in required_columns.items():
                if col_name not in columns:
                    try:
                        self.cursor.execute(f"ALTER TABLE profit_records ADD COLUMN {col_name} {col_type}")
                        print(f"✅ 已添加 {col_name} 字段到 profit_records 表")
                    except Exception as e:
                        print(f"添加 {col_name} 字段失败: {e}")

            self.conn.commit()
            print("数据库初始化完成")
            
            # 创建历史数据表
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS historical_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                total_amount REAL DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                avg_price REAL DEFAULT 0,
                daily_amount REAL DEFAULT 0,
                daily_orders REAL DEFAULT 0,
                created_time TEXT NOT NULL,
                UNIQUE(store_id, start_date, end_date)
            )''')
            print("✅ 历史数据表已创建")

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS manual_margin_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                actual_orders INTEGER DEFAULT 0,
                actual_amount REAL DEFAULT 0,
                gross_profit REAL DEFAULT 0,
                refund_amount REAL DEFAULT 0,
                refund_orders INTEGER DEFAULT 0,
                promotion_fee REAL DEFAULT 0,
                deduction REAL DEFAULT 0,
                other_service REAL DEFAULT 0,
                other REAL DEFAULT 0,
                gross_margin_rate REAL DEFAULT 0,
                refund_rate_by_amount REAL DEFAULT 0,
                refund_rate_by_orders REAL DEFAULT 0,
                unit_price REAL DEFAULT 0,
                promotion_ratio REAL DEFAULT 0,
                tech_fee REAL DEFAULT 0,
                net_profit REAL DEFAULT 0,
                net_margin_rate REAL DEFAULT 0,
                profit_per_order REAL DEFAULT 0,
                created_time TEXT NOT NULL,
                UNIQUE(store_id, start_date, end_date)
            )''')
            print("✅ 手动毛利数据表已创建")

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS store_temp_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                slot_index INTEGER NOT NULL,
                image_data BLOB NOT NULL,
                created_time TEXT NOT NULL,
                UNIQUE(store_id, slot_index)
            )''')
            print("✅ 店铺临时图片表已创建")

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS promotion_daily_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                record_date TEXT NOT NULL,
                product_id TEXT NOT NULL,
                product_title TEXT,
                bid_method TEXT,
                cost REAL DEFAULT 0,
                transaction_amount REAL DEFAULT 0,
                roi REAL DEFAULT 0,
                net_transaction_amount REAL DEFAULT 0,
                net_roi REAL DEFAULT 0,
                net_orders REAL DEFAULT 0,
                net_profit REAL,
                net_margin_rate REAL,
                cost_per_net_order REAL DEFAULT 0,
                cpc REAL DEFAULT 0,
                impressions REAL DEFAULT 0,
                clicks REAL DEFAULT 0,
                promotion_impressions REAL DEFAULT 0,
                promotion_impression_share REAL DEFAULT 0,
                ctr REAL DEFAULT 0,
                click_conversion_rate REAL DEFAULT 0,
                imported_at TEXT NOT NULL,
                UNIQUE(store_id, record_date, product_id)
            )''')
            self.cursor.execute("PRAGMA table_info(promotion_daily_data)")
            promo_columns = [col[1] for col in self.cursor.fetchall()]
            if 'product_title' not in promo_columns:
                try:
                    self.cursor.execute("ALTER TABLE promotion_daily_data ADD COLUMN product_title TEXT")
                    print("✅ 已添加product_title字段到promotion_daily_data表")
                except Exception as e:
                    print(f"添加product_title字段失败: {e}")
            if 'net_profit' not in promo_columns:
                try:
                    self.cursor.execute("ALTER TABLE promotion_daily_data ADD COLUMN net_profit REAL")
                    print("✅ 已添加net_profit字段到promotion_daily_data表")
                except Exception as e:
                    print(f"添加net_profit字段失败: {e}")
            if 'net_margin_rate' not in promo_columns:
                try:
                    self.cursor.execute("ALTER TABLE promotion_daily_data ADD COLUMN net_margin_rate REAL")
                    print("✅ 已添加net_margin_rate字段到promotion_daily_data表")
                except Exception as e:
                    print(f"添加net_margin_rate字段失败: {e}")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_promotion_daily_store_date ON promotion_daily_data(store_id, record_date)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_promotion_daily_product ON promotion_daily_data(store_id, product_id, record_date)")
            print("✅ 推广日报数据表已创建")

            # 每日任务表
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS daily_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL,
                task_content TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                created_time TEXT NOT NULL
            )''')
            print("✅ 每日任务表已创建")

            # 任务提醒表
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS task_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                task_content TEXT NOT NULL,
                remind_time TEXT NOT NULL,
                is_reminded INTEGER DEFAULT 0,
                created_time TEXT NOT NULL
            )''')
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_tasks_product_status ON daily_tasks(product_id, is_completed)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_reminders_product_status ON task_reminders(product_id, is_reminded)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_reminders_due ON task_reminders(is_reminded, remind_time)")
            self._validate_required_schema()
            print("✅ 任务提醒表已创建")

            self.conn.commit()
            if migrated_off_shelf_column:
                self.repair_missing_promotion_profits()
            if self.get_setting("garbage_link_detection_v4_rebuilt", "0") != "1":
                self.reconcile_garbage_link_tasks()
                self.set_setting("garbage_link_detection_v4_rebuilt", "1")
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"数据库表创建失败：{e}") from e

    def _validate_required_schema(self):
        required_columns = {
            "stores": {
                "memo", "weight_synced", "image_data", "sitewide_roi", "store_discount_rules",
            },
            "products": {
                "title", "coupon_amount", "new_customer_discount", "store_weight",
                "store_weight_locked", "current_roi", "use_manual_spec_weight",
                "transaction_bid", "return_rate", "use_manual_return_rate", "is_limited_time", "is_marketing",
                "marketing_activity",
                "is_natural_flow", "is_sitewide_managed", "profit_status",
                "net_break_even_roi", "image_data", "product_category_label",
                "product_memo", "link_combo_id", "link_type", "roi_input_mode",
                "is_archived", "archived_at", "is_violation",
            },
            "cost_library": {
                "spec_name", "test_price", "quantity", "sort_order", "source_bg_color",
                "category_label", "category_color", "product_attribute",
                "product_attribute_combo_disabled", "product_attribute_is_combo",
                "combo_components_json", "combo_reviewed",
                "manual_sort_order", "product_cost", "unit_weight", "shipping_fee",
                "misc_fee", "cost_calc_mode", "thumbnail_data", "thumbnail_manual",
            },
            "product_specs": {"is_locked", "spec_image_data", "is_temporarily_off_shelf"},
            "daily_records": {"category", "special_info"},
            "imported_orders": {
                "product_id", "order_date", "actual_amount", "refund_count",
                "refund_amount", "period_start", "period_end",
            },
            "profit_records": {
                "profit_per_transaction", "best_roi", "net_break_even_roi",
                "net_break_even_125", "net_break_even_value",
                "net_break_even_125_from_net", "best_roi_from_net",
                "current_roi_multiple", "ai_analysis",
            },
            "promotion_daily_data": {"product_title", "net_profit", "net_margin_rate"},
        }
        missing = []
        for table, expected in required_columns.items():
            actual = {row[1] for row in self.cursor.execute(f"PRAGMA table_info({table})")}
            missing.extend(f"{table}.{column}" for column in sorted(expected - actual))

        imported_types = {
            row[1]: str(row[2] or "").upper()
            for row in self.cursor.execute("PRAGMA table_info(imported_orders)")
        }
        if imported_types.get("product_id") != "TEXT":
            missing.append("imported_orders.product_id(TEXT)")

        cost_indexes = {
            row[1] for row in self.cursor.execute("PRAGMA index_list(cost_library)")
        }
        if "idx_cost_library_spec_code_unique" not in cost_indexes:
            missing.append("cost_library.idx_cost_library_spec_code_unique")

        if missing:
            raise RuntimeError("数据库结构不完整: " + ", ".join(missing))

    def _migrate_imported_orders_product_id_to_text(self):
        """迁移 imported_orders.product_id 从 INTEGER (products.id) 改为 TEXT (products.name)

        这个迁移会把 product_id 从存储 products.id 改为存储 products.name
        确保未来直接用商品ID（用户输入的）作为关联键，更简单稳定
        """
        try:
            print("🔍 开始迁移 imported_orders 表的 product_id 字段...")

            # 1. 先备份原数据到临时表
            self.cursor.execute("CREATE TABLE IF NOT EXISTS imported_orders_backup AS SELECT * FROM imported_orders")
            print("  ✅ 已创建备份表 imported_orders_backup")

            # 2. 创建新结构的表
            self.cursor.execute("DROP TABLE IF EXISTS imported_orders_new")
            self.cursor.execute('''CREATE TABLE imported_orders_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                spec_code TEXT NOT NULL,
                order_count INTEGER DEFAULT 1,
                import_time TEXT NOT NULL,
                order_date TEXT,
                actual_amount REAL DEFAULT 0,
                refund_count INTEGER DEFAULT 0,
                refund_amount REAL,
                period_start TEXT,
                period_end TEXT,
                UNIQUE(store_id, product_id, spec_code))''')
            print("  ✅ 已创建新结构表 imported_orders_new")

            # 3. 迁移数据：把 products.id 转换为 products.name
            self.cursor.execute('''
                INSERT INTO imported_orders_new
                    (id, store_id, product_id, spec_code, order_count, import_time,
                     order_date, actual_amount, refund_count, refund_amount, period_start, period_end)
                SELECT
                    io.id,
                    io.store_id,
                    COALESCE(p.name, CAST(io.product_id AS TEXT)) as product_id,
                    io.spec_code,
                    io.order_count,
                    io.import_time,
                    io.order_date,
                    io.actual_amount,
                    COALESCE(io.refund_count, 0) as refund_count,
                    io.refund_amount,
                    io.period_start,
                    io.period_end
                FROM imported_orders_backup io
                LEFT JOIN products p ON io.product_id = p.id
            ''')
            migrated_count = self.cursor.rowcount
            print(f"  ✅ 已迁移 {migrated_count} 条数据")

            # 4. 删除旧表，重命名新表
            self.cursor.execute("DROP TABLE imported_orders")
            self.cursor.execute("ALTER TABLE imported_orders_new RENAME TO imported_orders")
            print("  ✅ 已用新表替换旧表")

            # 5. 删除备份表
            self.cursor.execute("DROP TABLE imported_orders_backup")
            print("  ✅ 已删除备份表")

            # 6. 提交事务
            self.conn.commit()
            print("✅ imported_orders.product_id 迁移完成！")

            # 7. 迁移 import_history.snapshot_data
            self._migrate_import_history_snapshot_data()

        except Exception as e:
            print(f"❌ 迁移失败: {e}")
            self.conn.rollback()
            try:
                # 恢复备份
                self.cursor.execute("DROP TABLE IF EXISTS imported_orders")
                self.cursor.execute("ALTER TABLE imported_orders_backup RENAME TO imported_orders")
                print("  ✅ 已从备份恢复")
                self.conn.commit()
            except:
                pass
            raise e

    def _migrate_import_history_snapshot_data(self):
        """迁移 import_history.snapshot_data 中的 product_id 从 sys_id 改为 product_name

        旧的 snapshot_data key 格式: "1_红色M" (sys_id_规格编码)
        新的 snapshot_data key 格式: "ABC123_红色M" (product_name_规格编码)

        迁移策略：
        1. 尝试把 key 的第一部分当作 sys_id（数字）查找对应的 products.name
        2. 如果找到了，说明是旧格式，用 products.name 替换
        3. 如果没找到，说明已经是新格式，保持原样
        """
        try:
            print("🔍 开始迁移 import_history.snapshot_data...")

            # 获取所有历史记录
            self.cursor.execute("SELECT id, snapshot_data FROM import_history WHERE snapshot_data IS NOT NULL")
            records = self.cursor.fetchall()

            migrated_count = 0
            for record_id, snapshot_data in records:
                if not snapshot_data:
                    continue

                try:
                    import json
                    snapshot = json.loads(snapshot_data)
                    if "orders" not in snapshot:
                        continue

                    new_orders = {}
                    changed = False
                    for old_key, data in snapshot["orders"].items():
                        parts = old_key.split("_", 1)
                        if len(parts) >= 2:
                            first_part = parts[0]
                            spec_code = parts[1]

                            # 检查 first_part 是否是纯数字（sys_id 格式）
                            if first_part.isdigit():
                                # 可能是旧格式，尝试查找对应的商品
                                sys_id = int(first_part)
                                self.cursor.execute("SELECT name FROM products WHERE id = ?", (sys_id,))
                                result = self.cursor.fetchone()
                                if result:
                                    # 找到了，说明确实是旧格式，需要转换
                                    new_prod_id = result[0]
                                    new_key = f"{new_prod_id}_{spec_code}"
                                    new_orders[new_key] = data
                                    changed = True
                                    continue

                            # 不是纯数字，或者是纯数字但找不到对应商品（新商品还没创建），保持原样
                            new_orders[old_key] = data

                    if changed:
                        new_snapshot = json.dumps({"orders": new_orders})
                        self.cursor.execute("UPDATE import_history SET snapshot_data = ? WHERE id = ?",
                                          (new_snapshot, record_id))
                        migrated_count += 1

                except (json.JSONDecodeError, Exception):
                    continue

            self.conn.commit()
            if migrated_count > 0:
                print(f"  ✅ 已迁移 {migrated_count} 条历史记录的 snapshot_data")
            else:
                print("  ℹ️  没有需要迁移的 snapshot_data（可能已经是新格式）")

        except Exception as e:
            print(f"  ⚠️  snapshot_data 迁移失败: {e}")
            self.conn.rollback()

    def _check_and_migrate_snapshot_data(self):
        """手动检查并迁移 snapshot_data（调试用）"""
        try:
            print("🔍 手动检查 snapshot_data 迁移状态...")

            self.cursor.execute("SELECT id, snapshot_data FROM import_history WHERE snapshot_data IS NOT NULL")
            records = self.cursor.fetchall()

            for record_id, snapshot_data in records:
                if not snapshot_data:
                    continue

                try:
                    import json
                    snapshot = json.loads(snapshot_data)
                    if "orders" not in snapshot:
                        continue

                    orders = snapshot.get("orders", {})
                    if len(orders) > 0:
                        sample_keys = list(orders.keys())[:3]
                        print(f"  record_id={record_id}, sample_keys={sample_keys}")
                except:
                    continue

        except Exception as e:
            print(f"  ⚠️  检查失败: {e}")

    def safe_execute(self, query, params=()):
        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor
        except Exception as e:
            self.conn.rollback()
            if append_exception:
                append_exception(f"database write: {query[:120]}", e)
            print(f"数据库操作失败: {query}, 错误: {e}")
            raise

    def save_product_weights(self, rows):
        """Atomically save product weights to avoid partial or repeated commits."""
        with self.conn:
            self.conn.executemany(
                "UPDATE products SET store_weight=?, store_weight_locked=? WHERE id=?",
                rows,
            )

    def safe_fetchall(self, query, params=()):
        try:
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"数据库查询失败: {query}, 错误: {e}")
            return []

    def close(self):
        try:
            self.conn.commit()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

    def reconcile_garbage_link_tasks(self, store_id=None, imported_at=None):
        if store_id is None:
            return sum(
                self.reconcile_garbage_link_tasks(row[0], imported_at)
                for row in self.safe_fetchall("SELECT id FROM stores")
            )

        streaks = {}
        finished = set()
        rows = self.safe_fetchall(
            """SELECT product_id, net_orders, cost, transaction_amount,
                      net_transaction_amount, impressions, clicks, promotion_impressions
               FROM promotion_daily_data WHERE store_id=?
               ORDER BY product_id, record_date DESC""",
            (store_id,),
        )
        for product_code, net_orders, *signals in rows:
            product_code = str(product_code).strip()
            if product_code in finished:
                continue
            has_data = any(float(value or 0) != 0 for value in signals)
            if float(net_orders or 0) <= 0 and has_data:
                streaks[product_code] = streaks.get(product_code, 0) + 1
            else:
                finished.add(product_code)

        now = datetime.now()
        created = 0
        products = self.safe_fetchall(
            """SELECT id, name, title, COALESCE(is_natural_flow, 0) FROM products
               WHERE store_id=? AND COALESCE(is_archived, 0)=0
                 AND COALESCE(is_violation, 0)=0""",
            (store_id,),
        )
        for product_id, product_code, title, is_natural_flow in products:
            streak = streaks.get(str(product_code or "").strip(), 0)
            is_garbage = not bool(is_natural_flow) and streak > 0
            task_args = (store_id, product_id)
            if not is_garbage:
                self.safe_execute(
                    "DELETE FROM daily_tasks WHERE store_id=? AND product_id=? AND is_completed=0 AND task_content LIKE '【垃圾链接】%'",
                    task_args,
                )
                continue
            exists = self.safe_fetchall(
                "SELECT id FROM daily_tasks WHERE store_id=? AND product_id=? AND task_content LIKE '【垃圾链接】%' LIMIT 1",
                task_args,
            )
            content = (
                f"【垃圾链接】连续{streak}次推广数据有数据但净成交笔数为 0。"
                f"商品ID：{product_code}；标题：{title or ''}"
            )
            if exists:
                self.safe_execute("UPDATE daily_tasks SET task_content=? WHERE id=?", (content, exists[0][0]))
                continue
            created_time = imported_at or now.strftime("%Y-%m-%d %H:%M:%S")
            self.safe_execute(
                """INSERT INTO daily_tasks (store_id, product_id, year, month, day, task_content, created_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (store_id, product_id, now.year, now.month, now.day,
                 content, created_time),
            )
            created += 1
        return created

    @staticmethod
    def _delete_product_rows(cursor, product_id):
        row = cursor.execute("SELECT store_id, name FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            return False
        store_id, product_code = row
        for table in ("product_specs", "records", "product_image_history", "daily_tasks", "task_reminders"):
            cursor.execute(f"DELETE FROM {table} WHERE product_id=?", (product_id,))
        cursor.execute(
            "DELETE FROM profit_records WHERE data_type='product' AND target_id=?",
            (product_id,),
        )
        cursor.execute("DELETE FROM imported_orders WHERE store_id=? AND product_id=?", (store_id, product_code))
        cursor.execute("DELETE FROM promotion_daily_data WHERE store_id=? AND product_id=?", (store_id, product_code))
        cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
        return True

    def delete_product_cascade(self, product_id):
        with self.conn:
            return self._delete_product_rows(self.conn.cursor(), product_id)

    def delete_store_cascade(self, store_id):
        with self.conn:
            cursor = self.conn.cursor()
            product_ids = [row[0] for row in cursor.execute("SELECT id FROM products WHERE store_id=?", (store_id,))]
            for product_id in product_ids:
                self._delete_product_rows(cursor, product_id)
            for table in (
                "store_records", "daily_records", "historical_data", "manual_margin_data",
                "store_temp_images", "promotion_daily_data", "imported_orders", "import_history",
                "daily_tasks", "task_reminders", "store_prompts",
            ):
                cursor.execute(f"DELETE FROM {table} WHERE store_id=?", (store_id,))
            cursor.execute("DELETE FROM profit_records WHERE data_type='store' AND target_id=?", (store_id,))
            cursor.execute("DELETE FROM stores WHERE id=?", (store_id,))
        return True

    def replace_imported_orders(self, store_id, history_row, order_rows):
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO import_history
                    (store_id, import_time, file_name, total_products, total_specs,
                     total_orders, total_amount, snapshot_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, history_row)
            cursor.execute("DELETE FROM imported_orders WHERE store_id=?", (store_id,))
            cursor.executemany("""
                INSERT INTO imported_orders
                    (store_id, product_id, spec_code, order_count, import_time,
                     order_date, actual_amount, refund_count, refund_amount,
                     period_start, period_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, order_rows)

    def get_setting(self, key, default=None):
        try:
            if self._is_common_setting_key(key):
                common = self._load_common_settings()
                if key in common:
                    return common.get(key, default)
            res = self.safe_fetchall("SELECT value FROM settings WHERE key=?", (key,))
            return res[0][0] if res else default
        except Exception as e:
            print(f"获取设置失败: {e}")
            return default

    def set_setting(self, key, value):
        try:
            if self._is_common_setting_key(key):
                common = self._load_common_settings()
                common[key] = str(value)
                if self._save_common_settings(common):
                    if key == "cost_sync_local_dirty" and str(value) == "1":
                        callback = getattr(self, "cost_sync_change_callback", None)
                        if callable(callback):
                            callback()
                    return
            self.safe_execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            if key == "cost_sync_local_dirty" and str(value) == "1":
                callback = getattr(self, "cost_sync_change_callback", None)
                if callable(callback):
                    callback()
        except Exception as e:
            print(f"保存设置失败: {e}")

    def _is_common_setting_key(self, key):
        key = str(key or "")
        return key in self.COMMON_SETTING_KEYS or any(key.startswith(prefix) for prefix in self.COMMON_SETTING_PREFIXES)

    def set_cost_history_source(self, source="manual"):
        source = str(source or "manual").strip() or "manual"
        self.cursor.execute("UPDATE cost_history_control SET source=? WHERE id=1", (source,))
        self.conn.commit()

    def clear_cost_history(self):
        count = int(self.safe_fetchall("SELECT COUNT(*) FROM cost_history")[0][0])
        clear_at = max(
            int(time.time() * 1000),
            int(self.get_setting("cost_history_clear_at", "0") or 0) + 1,
        )
        with self.conn:
            self.conn.execute("DELETE FROM cost_history")
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('cost_history_clear_at', ?)",
                (str(clear_at),),
            )
        self.set_setting("cost_sync_local_dirty", "1")
        return count

    def delete_cost_history_events(self, event_ids):
        event_ids = list(dict.fromkeys(
            str(value or "").strip() for value in event_ids if str(value or "").strip()
        ))
        if not event_ids:
            return 0
        placeholders = ",".join("?" for _ in event_ids)
        self.cursor.execute(f"DELETE FROM cost_history WHERE event_id IN ({placeholders})", tuple(event_ids))
        count = self.cursor.rowcount
        self.conn.commit()
        if count:
            self.set_setting("cost_sync_local_dirty", "1")
        return count

    def _rename_cost_spec_references(self, old_code, new_code):
        old_code = str(old_code or "").strip()
        new_code = str(new_code or "").strip()
        if not old_code or not new_code or old_code == new_code:
            return
        self.cursor.execute("UPDATE product_specs SET spec_code=? WHERE spec_code=?", (new_code, old_code))
        order_rows = self.cursor.execute(
            """SELECT id, store_id, product_id, order_count, import_time, order_date,
                      actual_amount, refund_count, refund_amount, period_start, period_end
               FROM imported_orders WHERE spec_code=?""",
            (old_code,),
        ).fetchall()
        for row in order_rows:
            (row_id, store_id, product_id, order_count, import_time, order_date,
             actual_amount, refund_count, refund_amount, period_start, period_end) = row
            target = self.cursor.execute(
                """SELECT id, order_count, actual_amount, refund_count, refund_amount,
                          period_start, period_end
                   FROM imported_orders
                   WHERE store_id=? AND product_id=? AND spec_code=? AND id<>?""",
                (store_id, product_id, new_code, row_id),
            ).fetchone()
            if target:
                merged_refund_amount = (
                    None if target[4] is None or refund_amount is None
                    else float(target[4]) + float(refund_amount)
                )
                starts = [value for value in (target[5], period_start) if value]
                ends = [value for value in (target[6], period_end) if value]
                self.cursor.execute(
                    """UPDATE imported_orders
                       SET order_count=?, actual_amount=?, refund_count=?, refund_amount=?,
                           period_start=?, period_end=?, import_time=?, order_date=?
                       WHERE id=?""",
                    (
                        int(target[1] or 0) + int(order_count or 0),
                        float(target[2] or 0) + float(actual_amount or 0),
                        int(target[3] or 0) + int(refund_count or 0),
                        merged_refund_amount,
                        min(starts) if len(starts) == 2 else None,
                        max(ends) if len(ends) == 2 else None,
                        import_time, order_date, target[0],
                    ),
                )
                self.cursor.execute("DELETE FROM imported_orders WHERE id=?", (row_id,))
            else:
                self.cursor.execute("UPDATE imported_orders SET spec_code=? WHERE id=?", (new_code, row_id))
        self.cursor.execute("UPDATE cost_history SET spec_code=? WHERE spec_code=?", (new_code, old_code))
        combo_rows = self.cursor.execute(
            """SELECT spec_code, combo_components_json FROM cost_library
               WHERE COALESCE(combo_components_json, '')<>''"""
        ).fetchall()
        for combo_code, raw_json in combo_rows:
            try:
                items = json.loads(raw_json or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            changed = False
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and str(item.get("spec_code") or item.get("code") or "") == old_code:
                    item["spec_code"] = new_code
                    item.pop("code", None)
                    changed = True
            if changed:
                self.cursor.execute(
                    "UPDATE cost_library SET combo_components_json=? WHERE spec_code=?",
                    (json.dumps(items, ensure_ascii=False), combo_code),
                )

    def rename_cost_spec_code(self, old_code, new_code, manage_transaction=True, mark_dirty=True):
        old_code = str(old_code or "").strip()
        new_code = str(new_code or "").strip()
        if not old_code or not new_code:
            raise ValueError("规格编码不能为空")
        if old_code == new_code:
            return False
        if not self.cursor.execute("SELECT 1 FROM cost_library WHERE spec_code=?", (old_code,)).fetchone():
            raise ValueError(f"原规格编码不存在：{old_code}")
        if self.cursor.execute("SELECT 1 FROM cost_library WHERE spec_code=?", (new_code,)).fetchone():
            raise ValueError(f"规格编码已存在：{new_code}")
        try:
            if manage_transaction:
                self.conn.execute("BEGIN TRANSACTION")
            self.cursor.execute("UPDATE cost_library SET spec_code=? WHERE spec_code=?", (new_code, old_code))
            self._rename_cost_spec_references(old_code, new_code)
            if manage_transaction:
                self.conn.commit()
        except Exception:
            if manage_transaction:
                self.conn.rollback()
            raise
        if mark_dirty:
            self.set_setting("cost_sync_local_dirty", "1")
        return True

    def _common_settings_path(self):
        if DataRootManager is None:
            return None
        try:
            manager = DataRootManager()
            root = manager.get_data_root()
            if not root:
                return None
            manager.ensure_structure(root)
            return manager.common_settings_path(root)
        except Exception:
            return None

    def _migrate_legacy_common_cost_settings(self):
        """Seed account-local cost settings once from older shared settings."""
        common = self._load_common_settings()
        changed = False
        for key in self.ACCOUNT_COST_SETTING_KEYS:
            if key not in common:
                continue
            exists = self.cursor.execute(
                "SELECT 1 FROM settings WHERE key=?", (key,)
            ).fetchone()
            if not exists:
                self.cursor.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)",
                    (key, str(common[key])),
                )
                changed = True
        if changed:
            self.conn.commit()

    def _load_common_settings(self):
        path = self._common_settings_path()
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_common_settings(self, data):
        path = self._common_settings_path()
        if not path:
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data or {}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存通用设置失败: {e}")
            return False

    def get_cost_library_mode(self):
        mode = str(self.get_setting("cost_library_mode", "total") or "total").strip().lower()
        return "detail" if mode == "detail" else "total"

    def set_cost_library_mode(self, mode):
        self.set_setting("cost_library_mode", "detail" if str(mode).lower() == "detail" else "total")

    def get_cost_misc_fee(self):
        try:
            return float(self.get_setting("cost_misc_fee", "0") or 0)
        except (TypeError, ValueError):
            return 0.0

    def set_cost_misc_fee(self, value):
        try:
            fee = float(value or 0)
        except (TypeError, ValueError):
            fee = 0.0
        self.set_setting("cost_misc_fee", max(0.0, fee))

    def get_cost_shipping_rules(self):
        raw = self.get_setting("cost_shipping_rules_json", "")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and isinstance(data.get("ranges"), list) and isinstance(data.get("over"), dict):
                    return data
            except Exception:
                pass
        return json.loads(json.dumps(self.DEFAULT_COST_SHIPPING_RULES))

    def set_cost_shipping_rules(self, rules):
        self.set_setting("cost_shipping_rules_json", json.dumps(rules or self.DEFAULT_COST_SHIPPING_RULES, ensure_ascii=False))

    def parse_cost_number(self, value, default=None):
        if value is None:
            return default
        text = str(value).replace("¥", "").replace("$", "").replace(",", "").strip()
        if not text or text.lower() == "nan":
            return default
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return default
        try:
            return float(match.group(0))
        except ValueError:
            return default

    def parse_cost_quantity_factor(self, quantity):
        number = self.parse_cost_number(quantity, None)
        if number is None or number <= 0:
            return 1.0
        return number

    def calculate_cost_shipping_fee(self, total_weight):
        weight = float(total_weight or 0)
        if weight <= 0:
            return 0.0
        rules = self.get_cost_shipping_rules()
        for rule in sorted(rules.get("ranges", []), key=lambda item: float(item.get("max") or 0)):
            max_weight = float(rule.get("max") or 0)
            # Shipping prices are weight ceilings; ignoring a mistyped lower bound
            # prevents a configured gap from silently producing a zero fee.
            if max_weight > 0 and weight <= max_weight:
                return round(float(rule.get("fee") or 0), 2)
        over = rules.get("over", {})
        threshold = float(over.get("threshold") or 0)
        base_fee = float(over.get("base_fee") or 0)
        deduct_weight = float(over.get("deduct_weight") or 0)
        step_weight = float(over.get("step_weight") or 1) or 1
        step_fee = float(over.get("step_fee") or 0)
        if weight > threshold:
            steps = math.ceil(max(weight - deduct_weight, 0) / step_weight)
            return round(base_fee + steps * step_fee, 2)
        return 0.0

    def calculate_detailed_cost(self, product_cost, quantity, unit_weight):
        qty = self.parse_cost_quantity_factor(quantity)
        product_cost = float(product_cost or 0)
        unit_weight = float(unit_weight or 0)
        total_weight = unit_weight * qty
        shipping_fee = self.calculate_cost_shipping_fee(total_weight)
        misc_fee = self.get_cost_misc_fee()
        total_cost = product_cost * qty + misc_fee + shipping_fee
        return round(total_cost, 2), round(shipping_fee, 2), round(misc_fee, 2), round(total_weight, 4)

    _COMBO_UNITS = "本|套|包|盒|件|册|支|份|组"
    _CHINESE_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

    @classmethod
    def cost_combo_multiplier(cls, name):
        matches = re.findall(rf"(?<![/／])([2-9]|\d{{2,}}|[二两三四五六七八九十])\s*(?:{cls._COMBO_UNITS})", str(name or ""))
        values = [int(value) if value.isdigit() else cls._CHINESE_NUMBERS.get(value, 0) for value in matches]
        return values[-1] if values else 1

    @classmethod
    def is_cost_combo_name(cls, name):
        text = str(name or "")
        return bool(re.search(r"\+|＋|﹢", text)) or cls.cost_combo_multiplier(text) > 1

    @classmethod
    def _cost_combo_family_name(cls, name):
        text = str(name or "").lower()
        text = re.sub(r"\d+(?:\.\d+)?\s*张", "", text)
        text = re.sub(
            rf"(?<![/／])(?:共计?|合计)?\s*(?:\d+|[一二两三四五六七八九十])\s*(?:{cls._COMBO_UNITS})",
            "",
            text,
        )
        return re.sub(r"[\s,，。;；:：|｜/\\_\-（）()【】\[\]{}]+", "", text)

    def _cost_combo_specs(self, exclude_code=""):
        rows = self.safe_fetchall(
            """SELECT spec_code, COALESCE(spec_name, ''), COALESCE(category_label, ''),
                      COALESCE(product_attribute, ''), COALESCE(product_attribute_combo_disabled, 0),
                      COALESCE(product_attribute_is_combo, 0)
               FROM cost_library WHERE COALESCE(spec_code, '')<>''"""
        )
        return [
            {"code": str(code), "name": str(name), "category": str(category), "attribute": str(attribute)}
            for code, name, category, attribute, disabled, is_combo in rows
            if str(code) != str(exclude_code or "")
            and (
                int(disabled or 0)
                or (not int(is_combo or 0) and not self.is_cost_combo_name(name))
            )
        ]

    def suggest_cost_combo_items(self, spec_code, candidates=None):
        rows = self.safe_fetchall(
            "SELECT COALESCE(spec_name, ''), COALESCE(category_label, '') FROM cost_library WHERE spec_code=?",
            (str(spec_code or ""),),
        )
        if not rows:
            return []
        name, category = str(rows[0][0]), str(rows[0][1])
        candidates = candidates if candidates is not None else self._cost_combo_specs(spec_code)

        def best_match(part):
            target = self._cost_combo_family_name(part)
            best = None
            best_score = -1
            for item in candidates:
                candidate = self._cost_combo_family_name(item["name"])
                if not target or not candidate:
                    continue
                if candidate == target:
                    score = 1000
                elif candidate in target or target in candidate:
                    score = min(len(candidate), len(target))
                else:
                    continue
                if item["category"] == category:
                    score += 100
                if score > best_score:
                    best, best_score = item, score
            return best

        parts = [part.strip() for part in re.split(r"\+|＋|﹢", name) if part.strip()]
        if len(parts) > 1:
            result = []
            for part in parts:
                item = best_match(part)
                if item:
                    result.append({**item, "quantity": 1})
            return result
        multiplier = self.cost_combo_multiplier(name)
        item = best_match(name)
        return [{**item, "quantity": multiplier}] if item and multiplier > 1 else []

    @staticmethod
    def _normalise_combo_items(items):
        result = []
        for item in items or []:
            code = str(item.get("spec_code") or item.get("code") or "").strip()
            if not code:
                continue
            quantity = max(float(item.get("quantity") or 1), 1)
            result.append({"spec_code": code, "quantity": int(quantity) if quantity.is_integer() else quantity})
        return result

    def get_cost_combo_items(self, spec_code, suggest=False):
        rows = self.safe_fetchall(
            "SELECT COALESCE(combo_components_json, '') FROM cost_library WHERE spec_code=?",
            (str(spec_code or ""),),
        )
        try:
            saved = self._normalise_combo_items(json.loads(rows[0][0])) if rows and rows[0][0] else []
        except (TypeError, ValueError, json.JSONDecodeError):
            saved = []
        raw_items = saved or (self.suggest_cost_combo_items(spec_code) if suggest else [])
        result = []
        for item in raw_items:
            code = str(item.get("spec_code") or item.get("code") or "")
            details = self.safe_fetchall(
                """SELECT COALESCE(spec_name, ''), COALESCE(category_label, ''),
                          COALESCE(product_attribute, ''), COALESCE(quantity, '')
                   FROM cost_library WHERE spec_code=?""",
                (code,),
            )
            if details:
                result.append({"code": code, "name": details[0][0], "category": details[0][1],
                               "attribute": details[0][2], "quantity": details[0][3],
                               "combo_quantity": item.get("quantity") or 1})
        return result

    def detect_cost_combo_candidates(self):
        rows = self.safe_fetchall(
            """SELECT spec_code, COALESCE(spec_name, ''), COALESCE(combo_components_json, ''),
                      COALESCE(product_attribute_combo_disabled, 0), COALESCE(combo_reviewed, 0),
                      COALESCE(product_attribute_is_combo, 0)
               FROM cost_library"""
        )
        single_specs = self._cost_combo_specs()
        single_codes = {item["code"] for item in single_specs}
        changed_codes = []
        for code, name, components_json, disabled, reviewed, is_combo in rows:
            if int(disabled or 0) or int(reviewed or 0) or not self.is_cost_combo_name(name):
                continue
            try:
                saved_items = self._normalise_combo_items(json.loads(components_json or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                saved_items = []
            saved_is_single_only = bool(saved_items) and all(
                item["spec_code"] in single_codes for item in saved_items
            )
            if int(is_combo or 0) and saved_is_single_only:
                continue
            items = saved_items if saved_is_single_only else self.suggest_cost_combo_items(code, single_specs)
            self.cursor.execute(
                """UPDATE cost_library SET product_attribute_is_combo=1,
                          combo_components_json=?
                   WHERE spec_code=?""",
                (json.dumps(self._normalise_combo_items(items), ensure_ascii=False), code),
            )
            changed_codes.append(str(code))
        if changed_codes:
            self.conn.commit()
            self.recalculate_cost_combinations_for_components(
                changed_codes, record_history=True, source="combo"
            )
            self.set_setting("cost_sync_local_dirty", "1")
        return len(changed_codes)

    def save_cost_combo_definition(
        self, spec_code, is_combo, items=None, product_attribute="", combo_disabled=None,
        mark_reviewed=True,
    ):
        spec_code = str(spec_code or "").strip()
        normalised = self._normalise_combo_items(items)
        self.cursor.execute(
            """UPDATE cost_library SET product_attribute=?, product_attribute_is_combo=?,
                      product_attribute_combo_disabled=?, combo_components_json=?,
                      combo_reviewed=CASE WHEN ? THEN ? ELSE combo_reviewed END
               WHERE spec_code=?""",
            (str(product_attribute or ""), int(bool(is_combo)), 0 if is_combo else int(bool(combo_disabled)),
             json.dumps(normalised, ensure_ascii=False) if is_combo else "",
             int(bool(mark_reviewed)), int(bool(is_combo or combo_disabled)), spec_code),
        )
        self.conn.commit()
        changed = self.recalculate_cost_combinations_for_components([spec_code], record_history=True)
        self.inherit_single_multiplier_combo_thumbnails([spec_code], mark_dirty=False)
        self.set_setting("cost_sync_local_dirty", "1")
        return changed

    def recalculate_cost_combinations_for_components(self, component_codes=None, record_history=False, source="manual"):
        wanted = {str(code) for code in (component_codes or []) if str(code)}
        rows = self.safe_fetchall(
            """SELECT spec_code, COALESCE(combo_components_json, ''), COALESCE(quantity, ''), cost_price,
                      product_cost, unit_weight, shipping_fee, misc_fee
               FROM cost_library
               WHERE COALESCE(product_attribute_is_combo, 0)=1"""
        )
        target_rows = []
        needed_component_codes = set()
        for row in rows:
            combo_code, raw_json = row[0], row[1]
            try:
                items = self._normalise_combo_items(json.loads(raw_json or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            item_codes = {item["spec_code"] for item in items}
            if wanted and not (wanted & item_codes) and str(combo_code) not in wanted:
                continue
            target_rows.append((row, items))
            needed_component_codes.update(item_codes)
        component_values = {}
        needed_codes = list(needed_component_codes)
        for start in range(0, len(needed_codes), 800):
            batch = needed_codes[start:start + 800]
            placeholders = ",".join("?" for _ in batch)
            component_values.update({
                str(code): (product_cost, unit_weight)
                for code, product_cost, unit_weight in self.safe_fetchall(
                    f"SELECT spec_code, product_cost, unit_weight FROM cost_library WHERE spec_code IN ({placeholders})",
                    tuple(batch),
                )
            })
        changed_codes = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row, items in target_rows:
            combo_code, _raw_json, combo_quantity, old_cost, old_product_cost, old_unit_weight, old_shipping, old_misc = row
            product_cost = 0.0
            unit_weight = 0.0
            valid = bool(items)
            for item in items:
                component = component_values.get(item["spec_code"])
                if not component or component[0] is None or component[1] is None:
                    valid = False
                    break
                product_cost += float(component[0]) * float(item["quantity"])
                unit_weight += float(component[1]) * float(item["quantity"])
            if not valid:
                if any(value is not None for value in (
                    old_cost, old_product_cost, old_unit_weight, old_shipping, old_misc,
                )):
                    self.cursor.execute(
                        """UPDATE cost_library
                           SET product_cost=NULL, unit_weight=NULL, shipping_fee=NULL,
                               misc_fee=NULL, cost_price=NULL, cost_calc_mode='detail'
                           WHERE spec_code=?""",
                        (combo_code,),
                    )
                    changed_codes.append(str(combo_code))
                continue
            total, shipping, misc, _ = self.calculate_detailed_cost(product_cost, 1, unit_weight)
            product_cost = round(product_cost, 4)
            unit_weight = round(unit_weight, 4)
            old_value = float(old_cost) if old_cost is not None else None
            details_changed = any((
                old_product_cost is None or abs(float(old_product_cost) - product_cost) > 0.0001,
                old_unit_weight is None or abs(float(old_unit_weight) - unit_weight) > 0.0001,
                old_shipping is None or abs(float(old_shipping) - shipping) > 0.001,
                old_misc is None or abs(float(old_misc) - misc) > 0.001,
            ))
            cost_changed = old_value is None or abs(total - old_value) > 0.001
            if not details_changed and not cost_changed:
                continue
            self.cursor.execute(
                """UPDATE cost_library SET product_cost=?, unit_weight=?, shipping_fee=?, misc_fee=?,
                          cost_price=?, cost_calc_mode='detail' WHERE spec_code=?""",
                (product_cost, unit_weight, shipping, misc, total, combo_code),
            )
            changed_codes.append(str(combo_code))
        if changed_codes:
            self.conn.commit()
        return changed_codes

    def recalculate_detailed_cost_library(self, record_history=False, source="manual"):
        rows = self.safe_fetchall(
            """SELECT spec_code, quantity, product_cost, unit_weight, cost_price,
                      COALESCE(product_attribute_is_combo, 0)
               FROM cost_library
               WHERE cost_calc_mode='detail'"""
        )
        changed = 0
        try:
            self.conn.execute("BEGIN TRANSACTION")
            for spec_code, quantity, product_cost, unit_weight, old_cost, is_combo in rows:
                if product_cost is None or unit_weight is None:
                    self.cursor.execute(
                        """UPDATE cost_library
                           SET cost_price=NULL, shipping_fee=NULL, misc_fee=NULL
                           WHERE spec_code=?
                             AND (cost_price IS NOT NULL OR shipping_fee IS NOT NULL OR misc_fee IS NOT NULL)""",
                        (spec_code,),
                    )
                    changed += max(self.cursor.rowcount, 0)
                    continue
                new_cost, shipping_fee, misc_fee, _total_weight = self.calculate_detailed_cost(
                    product_cost, 1 if is_combo else quantity, unit_weight
                )
                old_value = float(old_cost) if old_cost is not None else None
                if old_value is not None and abs(new_cost - old_value) <= 0.001:
                    self.cursor.execute(
                        "UPDATE cost_library SET shipping_fee=?, misc_fee=? WHERE spec_code=?",
                        (shipping_fee, misc_fee, spec_code),
                    )
                    continue
                self.cursor.execute(
                    "UPDATE cost_library SET cost_price=?, shipping_fee=?, misc_fee=? WHERE spec_code=?",
                    (new_cost, shipping_fee, misc_fee, spec_code),
                )
                changed += 1
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        combo_changed = self.recalculate_cost_combinations_for_components(
            record_history=record_history, source=source
        )
        return changed + len(combo_changed)

    def get_cost_sync_state(self):
        rows = self.safe_fetchall(
            """SELECT group_id, group_name, role, coordinator_host, secret, revision,
                      snapshot_json, snapshot_hash, publisher_id, published_at,
                      xlsx_path, mapping_json, file_signature
               FROM cost_sync_state LIMIT 1"""
        )
        if not rows:
            return {}
        keys = (
            "group_id", "group_name", "role", "coordinator_host", "secret", "revision",
            "snapshot_json", "snapshot_hash", "publisher_id", "published_at",
            "xlsx_path", "mapping_json", "file_signature",
        )
        return dict(zip(keys, rows[0]))

    def configure_cost_sync(self, group_id, group_name, role, secret, coordinator_host=""):
        current = self.get_cost_sync_state()
        same_group = current.get("group_id") == group_id
        self.cursor.execute("DELETE FROM cost_sync_state")
        self.cursor.execute(
            """INSERT INTO cost_sync_state
               (group_id, group_name, role, coordinator_host, secret, revision,
                snapshot_json, snapshot_hash, publisher_id, published_at,
                xlsx_path, mapping_json, file_signature)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                group_id, group_name, role, coordinator_host, secret,
                int(current.get("revision") or 0) if same_group else 0,
                current.get("snapshot_json") if same_group else None,
                current.get("snapshot_hash") if same_group else None,
                current.get("publisher_id") if same_group else None,
                current.get("published_at") if same_group else None,
                current.get("xlsx_path") or "", current.get("mapping_json") or "",
                current.get("file_signature") or "",
            ),
        )
        self.conn.commit()

    def update_cost_sync_state(self, **values):
        allowed = {
            "group_name", "role", "coordinator_host", "revision", "snapshot_json",
            "snapshot_hash", "publisher_id", "published_at", "xlsx_path",
            "mapping_json", "file_signature",
        }
        values = {key: value for key, value in values.items() if key in allowed}
        if not values or not self.get_cost_sync_state():
            return False
        assignments = ", ".join(f"{key}=?" for key in values)
        self.cursor.execute(f"UPDATE cost_sync_state SET {assignments}", tuple(values.values()))
        self.conn.commit()
        return True

    def clear_cost_sync_state(self):
        self.cursor.execute("DELETE FROM cost_sync_state")
        self.conn.commit()

    def build_cost_sync_snapshot(self):
        rows = self.safe_fetchall(
            """SELECT spec_code, COALESCE(spec_name, ''), COALESCE(category_label, ''),
                      COALESCE(category_color, ''), COALESCE(quantity, ''),
                      COALESCE(product_attribute, ''),
                      COALESCE(product_attribute_combo_disabled, 0),
                      COALESCE(product_attribute_is_combo, 0), product_cost, unit_weight,
                      COALESCE(cost_calc_mode, 'total'), cost_price, sort_order, manual_sort_order,
                      COALESCE(combo_components_json, ''), COALESCE(combo_reviewed, 0)
               FROM cost_library
               WHERE COALESCE(spec_code, '') <> ''
               ORDER BY sort_order, spec_code"""
        )
        categories = self.safe_fetchall(
            """SELECT label, COALESCE(color, ''), sort_order
               FROM cost_categories WHERE COALESCE(label, '') <> ''
               ORDER BY sort_order, label"""
        )
        images = self.safe_fetchall(
            """SELECT spec_code, thumbnail_data, COALESCE(thumbnail_manual, 0)
               FROM cost_library
               WHERE COALESCE(spec_code, '') <> '' AND LENGTH(COALESCE(thumbnail_data, X'')) > 0
               ORDER BY spec_code"""
        )
        history = self.safe_fetchall(
            """SELECT event_id, spec_code, COALESCE(spec_name, ''),
                      COALESCE(operation_type, 'price'), COALESCE(old_value, ''),
                      COALESCE(new_value, ''), old_cost_price, new_cost_price,
                      change_amount, change_percent, COALESCE(source, 'manual'),
                      import_time, COALESCE(event_time_ms, 0)
               FROM cost_history
               WHERE COALESCE(event_id, '')<>''
                 AND COALESCE(operation_type, 'price')<>'price'
               ORDER BY event_time_ms, id"""
        )
        return {
            "schema": 1,
            "history_clear_at": int(self.get_setting("cost_history_clear_at", "0") or 0),
            "rows": [
                {
                    "spec_code": row[0], "spec_name": row[1], "category_label": row[2],
                    "category_color": row[3], "quantity": row[4], "product_attribute": row[5],
                    "combo_disabled": int(row[6] or 0), "is_combo": int(row[7] or 0),
                    "product_cost": row[8], "unit_weight": row[9], "cost_calc_mode": row[10],
                    "cost_price": None if str(row[10]).lower() == "detail" else row[11],
                    "sort_order": row[12], "manual_sort_order": row[13],
                    "combo_components_json": row[14], "combo_reviewed": int(row[15] or 0),
                }
                for row in rows
            ],
            "categories": [
                {"label": row[0], "color": row[1], "sort_order": row[2]}
                for row in categories
            ],
            "images": [
                {
                    "spec_code": row[0],
                    "data": base64.b64encode(bytes(row[1])).decode("ascii"),
                    "manual": int(row[2] or 0),
                }
                for row in images
            ],
            "history": [
                {
                    "event_id": row[0], "spec_code": row[1], "spec_name": row[2],
                    "operation_type": row[3], "old_value": row[4], "new_value": row[5],
                    "old_cost_price": row[6], "new_cost_price": row[7],
                    "change_amount": row[8], "change_percent": row[9], "source": row[10],
                    "import_time": row[11], "event_time_ms": int(row[12] or 0),
                }
                for row in history
            ],
        }

    @staticmethod
    def merge_cost_sync_snapshots(current, incoming):
        current = current if isinstance(current, dict) else {}
        incoming = incoming if isinstance(incoming, dict) else {}
        rows = {
            str(row.get("spec_code") or "").strip(): dict(row)
            for row in current.get("rows", []) if str(row.get("spec_code") or "").strip()
        }
        def should_replace(old, new):
            old_stamp = int(old.get("_modified_at") or 0) if old else 0
            new_stamp = int(new.get("_modified_at") or 0)
            if not old_stamp and not new_stamp:
                return True
            if new_stamp != old_stamp:
                return new_stamp > old_stamp
            return str(new.get("_modified_by") or "") > str(old.get("_modified_by") or "")

        for row in incoming.get("rows", []):
            code = str(row.get("spec_code") or "").strip()
            if code and should_replace(rows.get(code), row):
                rows[code] = dict(row)
        categories = {
            str(row.get("label") or "").strip(): dict(row)
            for row in current.get("categories", []) if str(row.get("label") or "").strip()
        }
        for row in incoming.get("categories", []):
            label = str(row.get("label") or "").strip()
            if label and should_replace(categories.get(label), row):
                categories[label] = dict(row)
        images = {
            str(image.get("spec_code") or "").strip(): dict(image)
            for image in current.get("images", [])
            if str(image.get("spec_code") or "").strip() and image.get("data")
        }
        for image in incoming.get("images", []):
            code = str(image.get("spec_code") or "").strip()
            old = images.get(code)
            if not code or not image.get("data") or image.get("_deleted"):
                continue
            if old is None or (int(image.get("manual") or 0) and should_replace(old, image)):
                images[code] = dict(image)
        history_clear_at = max(
            int(current.get("history_clear_at") or 0),
            int(incoming.get("history_clear_at") or 0),
        )
        history = {
            str(item.get("event_id") or "").strip(): dict(item)
            for item in current.get("history", [])
            if str(item.get("event_id") or "").strip()
            and str(item.get("operation_type") or "price") != "price"
        }
        for item in incoming.get("history", []):
            event_id = str(item.get("event_id") or "").strip()
            if (
                event_id
                and str(item.get("operation_type") or "price") != "price"
                and should_replace(history.get(event_id), item)
            ):
                history[event_id] = dict(item)
        history = {
            event_id: item for event_id, item in history.items()
            if int(item.get("event_time_ms") or 0) > history_clear_at
        }
        category_colors = {
            label: str(row.get("color") or "")
            for label, row in categories.items()
            if not row.get("_deleted")
        }
        for row in rows.values():
            label = str(row.get("category_label") or "").strip()
            if not row.get("_deleted") and label in category_colors:
                row["category_color"] = category_colors[label]
        return {
            "schema": 1,
            "history_clear_at": history_clear_at,
            "rows": sorted(rows.values(), key=lambda row: (row.get("sort_order") is None, row.get("sort_order") or 0, str(row.get("spec_code") or ""))),
            "categories": sorted(categories.values(), key=lambda row: (row.get("sort_order") is None, row.get("sort_order") or 0, str(row.get("label") or ""))),
            "images": sorted(images.values(), key=lambda image: str(image.get("spec_code") or "")),
            "history": sorted(history.values(), key=lambda item: (int(item.get("event_time_ms") or 0), str(item.get("event_id") or ""))),
        }

    def apply_cost_sync_snapshot(self, snapshot, source="lan", manage_transaction=True, replace_local=False):
        if not isinstance(snapshot, dict) or int(snapshot.get("schema") or 0) != 1:
            raise ValueError("成本库同步数据格式不受支持")
        changed_codes = []
        cost_changed_codes = []
        image_changed_codes = []
        history_changed_count = 0
        categories_changed = False
        import_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            if manage_transaction:
                self.conn.execute("BEGIN TRANSACTION")
            self.cursor.execute("UPDATE cost_history_control SET enabled=0 WHERE id=1")
            if replace_local:
                active_codes = {
                    str(row.get("spec_code") or "").strip()
                    for row in snapshot.get("rows", [])
                    if not row.get("_deleted") and str(row.get("spec_code") or "").strip()
                }
                existing_codes = {
                    str(row[0]) for row in self.cursor.execute("SELECT spec_code FROM cost_library").fetchall()
                }
                removed_codes = existing_codes - active_codes
                if removed_codes:
                    self.cursor.executemany(
                        "DELETE FROM cost_library WHERE spec_code=?",
                        [(code,) for code in removed_codes],
                    )
                    changed_codes.extend(sorted(removed_codes))
                active_categories = {
                    str(row.get("label") or "").strip()
                    for row in snapshot.get("categories", [])
                    if not row.get("_deleted") and str(row.get("label") or "").strip()
                }
                existing_categories = {
                    str(row[0]) for row in self.cursor.execute("SELECT label FROM cost_categories").fetchall()
                }
                removed_categories = existing_categories - active_categories
                if removed_categories:
                    self.cursor.executemany(
                        "DELETE FROM cost_categories WHERE label=?",
                        [(label,) for label in removed_categories],
                    )
                    categories_changed = True
            for category in snapshot.get("categories", []):
                label = str(category.get("label") or "").strip()
                if not label:
                    continue
                if category.get("_deleted"):
                    affected = [
                        str(row[0]) for row in self.cursor.execute(
                            "SELECT spec_code FROM cost_library WHERE category_label=?", (label,)
                        ).fetchall()
                    ]
                    self.cursor.execute(
                        "UPDATE cost_library SET category_label='', category_color='' WHERE category_label=?",
                        (label,),
                    )
                    self.cursor.execute("DELETE FROM cost_categories WHERE label=?", (label,))
                    changed_codes.extend(affected)
                    categories_changed = True
                    continue
                old_category = self.cursor.execute(
                    "SELECT COALESCE(color, ''), sort_order FROM cost_categories WHERE label=?",
                    (label,),
                ).fetchone()
                new_category = (str(category.get("color") or ""), category.get("sort_order"))
                if old_category is None or tuple(old_category) != new_category:
                    categories_changed = True
                self.cursor.execute(
                    """INSERT INTO cost_categories (label, color, sort_order, created_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(label) DO UPDATE SET color=excluded.color, sort_order=excluded.sort_order""",
                    (label, str(category.get("color") or ""), category.get("sort_order"), import_time),
                )
                self.cursor.execute(
                    "UPDATE cost_library SET category_color=? WHERE category_label=? AND COALESCE(category_color, '')<>?",
                    (new_category[0], label, new_category[0]),
                )

            for row in snapshot.get("rows", []):
                spec_code = str(row.get("spec_code") or "").strip()
                if not spec_code:
                    continue
                old_rows = self.cursor.execute(
                    """SELECT COALESCE(spec_name, ''), COALESCE(category_label, ''), COALESCE(quantity, ''),
                              COALESCE(product_attribute, ''), COALESCE(product_attribute_combo_disabled, 0),
                              COALESCE(product_attribute_is_combo, 0), product_cost, unit_weight,
                              COALESCE(cost_calc_mode, 'total'), cost_price, sort_order, manual_sort_order,
                              COALESCE(combo_components_json, ''), COALESCE(combo_reviewed, 0)
                       FROM cost_library WHERE spec_code=?""",
                    (spec_code,),
                ).fetchall()
                old = old_rows[0] if old_rows else None
                if row.get("_deleted"):
                    if old:
                        self.cursor.execute("DELETE FROM cost_library WHERE spec_code=?", (spec_code,))
                        changed_codes.append(spec_code)
                    continue
                mode = "detail" if str(row.get("cost_calc_mode") or "").lower() == "detail" else "total"
                product_cost = row.get("product_cost")
                unit_weight = row.get("unit_weight")
                quantity = str(row.get("quantity") or "")
                shipping_fee = misc_fee = None
                if mode == "detail":
                    if product_cost is not None and unit_weight is not None:
                        cost_price, shipping_fee, misc_fee, _ = self.calculate_detailed_cost(
                            product_cost, 1 if int(row.get("is_combo") or 0) else quantity, unit_weight
                        )
                    else:
                        cost_price = None
                else:
                    cost_price = float(row.get("cost_price") or 0)
                    product_cost = None
                    unit_weight = None
                values = (
                    str(row.get("spec_name") or ""), quantity,
                    str(row.get("category_label") or ""), str(row.get("category_color") or ""),
                    cost_price, row.get("sort_order"), product_cost, unit_weight,
                    shipping_fee, misc_fee, mode, str(row.get("product_attribute") or ""),
                    int(row.get("combo_disabled") or 0), int(row.get("is_combo") or 0),
                    row.get("manual_sort_order"), str(row.get("combo_components_json") or ""),
                    int(row.get("combo_reviewed") or 0),
                )
                old_cost = float(old[9]) if old and old[9] is not None else None
                comparable = (
                    values[0], values[2], values[1], values[11], values[12], values[13],
                    values[6], values[7], values[10], values[4], values[5], values[14], values[15], values[16],
                )
                if old:
                    old_comparable = (old[0], old[1], old[2], old[3], int(old[4] or 0), int(old[5] or 0), old[6], old[7], old[8], old[9], old[10], old[11], old[12], int(old[13] or 0))
                    if comparable == old_comparable:
                        continue
                self.cursor.execute(
                    """INSERT INTO cost_library
                       (spec_code, spec_name, quantity, category_label, category_color, cost_price,
                        sort_order, product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
                        product_attribute, product_attribute_combo_disabled, product_attribute_is_combo,
                         manual_sort_order, combo_components_json, combo_reviewed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(spec_code) DO UPDATE SET
                         spec_name=excluded.spec_name, quantity=excluded.quantity,
                         category_label=excluded.category_label, category_color=excluded.category_color,
                         cost_price=excluded.cost_price, sort_order=excluded.sort_order,
                         product_cost=excluded.product_cost, unit_weight=excluded.unit_weight,
                         shipping_fee=excluded.shipping_fee, misc_fee=excluded.misc_fee,
                         cost_calc_mode=excluded.cost_calc_mode, product_attribute=excluded.product_attribute,
                         product_attribute_combo_disabled=excluded.product_attribute_combo_disabled,
                          product_attribute_is_combo=excluded.product_attribute_is_combo,
                          manual_sort_order=excluded.manual_sort_order,
                          combo_components_json=excluded.combo_components_json,
                          combo_reviewed=excluded.combo_reviewed""",
                    (spec_code,) + values,
                )
                changed_codes.append(spec_code)
                if (
                    (old_cost is None) != (cost_price is None)
                    or (
                        old_cost is not None and cost_price is not None
                        and abs(float(cost_price) - old_cost) > 0.001
                    )
                ):
                    cost_changed_codes.append(spec_code)
            for image in snapshot.get("images", []):
                spec_code = str(image.get("spec_code") or "").strip()
                encoded = str(image.get("data") or "").strip()
                if not spec_code or not encoded or image.get("_deleted"):
                    continue
                try:
                    image_data = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"规格 {spec_code} 的同步缩略图无效") from exc
                if not image_data or len(image_data) > 96 * 1024:
                    raise ValueError(f"规格 {spec_code} 的同步缩略图超过 96KB")
                old_image = self.cursor.execute(
                    "SELECT thumbnail_data, COALESCE(thumbnail_manual, 0) FROM cost_library WHERE spec_code=?",
                    (spec_code,),
                ).fetchone()
                if not old_image:
                    continue
                manual = int(image.get("manual") or 0)
                if bytes(old_image[0] or b"") == image_data and int(old_image[1] or 0) == manual:
                    continue
                self.cursor.execute(
                    "UPDATE cost_library SET thumbnail_data=?, thumbnail_manual=? WHERE spec_code=?",
                    (image_data, manual, spec_code),
                )
                image_changed_codes.append(spec_code)

            incoming_clear_at = int(snapshot.get("history_clear_at") or 0)
            local_clear_row = self.cursor.execute(
                "SELECT value FROM settings WHERE key='cost_history_clear_at'"
            ).fetchone()
            local_clear_at = int(local_clear_row[0] or 0) if local_clear_row else 0
            if replace_local:
                self.cursor.execute("DELETE FROM cost_history")
                history_changed_count += max(self.cursor.rowcount, 0)
            elif incoming_clear_at > local_clear_at:
                self.cursor.execute(
                    "DELETE FROM cost_history WHERE COALESCE(event_time_ms, 0)<=?",
                    (incoming_clear_at,),
                )
                history_changed_count += max(self.cursor.rowcount, 0)
            if incoming_clear_at > local_clear_at or replace_local:
                self.cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('cost_history_clear_at', ?)",
                    (str(incoming_clear_at),),
                )
            for event in snapshot.get("history", []):
                event_id = str(event.get("event_id") or "").strip()
                if (
                    not event_id
                    or str(event.get("operation_type") or "price") == "price"
                ):
                    continue
                if event.get("_deleted"):
                    self.cursor.execute("DELETE FROM cost_history WHERE event_id=?", (event_id,))
                    history_changed_count += max(self.cursor.rowcount, 0)
                    continue
                event_time_ms = int(event.get("event_time_ms") or 0)
                if event_time_ms <= incoming_clear_at:
                    continue
                self.cursor.execute(
                    """INSERT OR IGNORE INTO cost_history
                       (event_id, spec_code, spec_name, operation_type, old_value, new_value,
                        old_cost_price, new_cost_price, change_amount, change_percent,
                        source, import_time, event_time_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id, str(event.get("spec_code") or ""), str(event.get("spec_name") or ""),
                        str(event.get("operation_type") or "price"), str(event.get("old_value") or ""),
                        str(event.get("new_value") or ""), event.get("old_cost_price"),
                        float(event.get("new_cost_price") or 0), event.get("change_amount"),
                        event.get("change_percent"), str(event.get("source") or source),
                        str(event.get("import_time") or import_time), event_time_ms,
                    ),
                )
                inserted = max(self.cursor.rowcount, 0)
                history_changed_count += inserted
                if inserted and str(event.get("operation_type") or "") == "code":
                    old_code = str(event.get("old_value") or "").strip()
                    new_code = str(event.get("new_value") or "").strip()
                    if old_code and new_code and old_code != new_code:
                        self._rename_cost_spec_references(old_code, new_code)
            self.cursor.execute("UPDATE cost_history_control SET enabled=1, source='manual' WHERE id=1")
            if manage_transaction:
                self.conn.commit()
        except Exception:
            if manage_transaction:
                self.conn.rollback()
            raise
        return {
            "changed_codes": list(dict.fromkeys(changed_codes)),
            "cost_changed_codes": list(dict.fromkeys(cost_changed_codes)),
            "image_changed_codes": list(dict.fromkeys(image_changed_codes)),
            "history_changed_count": history_changed_count,
            "categories_changed": categories_changed,
        }

    @staticmethod
    def _cost_sync_snapshot_json(snapshot):
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def publish_cost_sync_snapshot(self, incoming, publisher_id=""):
        """Merge one peer snapshot into this computer's local group state."""
        state = self.get_cost_sync_state()
        if not state:
            raise RuntimeError("当前账号尚未加入成本同步组织")
        try:
            current = json.loads(state.get("snapshot_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            current = {}
        merged = self.merge_cost_sync_snapshots(current, incoming)
        snapshot_json = self._cost_sync_snapshot_json(merged)
        snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        if snapshot_hash == str(state.get("snapshot_hash") or ""):
            return {
                "revision": int(state.get("revision") or 0),
                "snapshot": merged,
                "snapshot_hash": snapshot_hash,
                "publisher_id": state.get("publisher_id") or "",
                "published_at": state.get("published_at") or "",
                "changed_codes": [],
                "cost_changed_codes": [],
                "image_changed_codes": [],
                "history_changed_count": 0,
                "categories_changed": False,
            }
        revision = int(state.get("revision") or 0) + 1
        published_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.conn.execute("BEGIN TRANSACTION")
            changes = self.apply_cost_sync_snapshot(merged, source="lan", manage_transaction=False)
            self.cursor.execute(
                """UPDATE cost_sync_state
                   SET revision=?, snapshot_json=?, snapshot_hash=?, publisher_id=?, published_at=?
                   WHERE group_id=?""",
                (revision, snapshot_json, snapshot_hash, publisher_id, published_at, state.get("group_id")),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        combo_changes = self.recalculate_cost_combinations_for_components(
            changes.get("changed_codes") or [], record_history=True, source="lan"
        )
        changes["changed_codes"] = list(dict.fromkeys((changes.get("changed_codes") or []) + combo_changes))
        return {
            "revision": revision,
            "snapshot": merged,
            "snapshot_hash": snapshot_hash,
            "publisher_id": publisher_id,
            "published_at": published_at,
            **changes,
        }

    def apply_remote_cost_sync_snapshot(
        self, snapshot, revision, snapshot_hash="", publisher_id="", published_at="", replace_local=False
    ):
        """Merge a peer snapshot and checkpoint it in one transaction."""
        state = self.get_cost_sync_state()
        if not state:
            raise RuntimeError("当前账号尚未加入成本同步组织")
        remote_json = self._cost_sync_snapshot_json(snapshot)
        remote_hash = hashlib.sha256(remote_json.encode("utf-8")).hexdigest()
        if snapshot_hash and not hmac.compare_digest(str(snapshot_hash), remote_hash):
            raise ValueError("成本同步快照校验失败")
        try:
            current = json.loads(state.get("snapshot_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            current = {}
        merged = self.merge_cost_sync_snapshots(current, snapshot)
        snapshot_json = self._cost_sync_snapshot_json(merged)
        actual_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        if actual_hash == str(state.get("snapshot_hash") or ""):
            return {
                "changed_codes": [], "cost_changed_codes": [], "categories_changed": False,
                "image_changed_codes": [], "history_changed_count": 0,
                "revision": int(state.get("revision") or 0),
            }
        local_revision = max(int(state.get("revision") or 0), int(revision or 0)) + 1
        try:
            self.conn.execute("BEGIN TRANSACTION")
            changes = self.apply_cost_sync_snapshot(
                merged, source="lan", manage_transaction=False, replace_local=replace_local
            )
            self.cursor.execute(
                """UPDATE cost_sync_state
                   SET revision=?, snapshot_json=?, snapshot_hash=?, publisher_id=?, published_at=?
                   WHERE group_id=?""",
                (
                    local_revision, snapshot_json, actual_hash, publisher_id, published_at,
                    state.get("group_id"),
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        combo_changes = self.recalculate_cost_combinations_for_components(
            changes.get("changed_codes") or [], record_history=True, source="lan"
        )
        changes["changed_codes"] = list(dict.fromkeys((changes.get("changed_codes") or []) + combo_changes))
        return {"revision": local_revision, **changes}

    def set_cost_thumbnail(self, spec_code, image_data, manual=False, only_if_empty=False):
        spec_code = str(spec_code or "").strip()
        image_data = bytes(image_data or b"")
        if not spec_code or not image_data or len(image_data) > 96 * 1024:
            return False
        where = " AND LENGTH(COALESCE(thumbnail_data, X''))=0" if only_if_empty else ""
        self.cursor.execute(
            f"UPDATE cost_library SET thumbnail_data=?, thumbnail_manual=? WHERE spec_code=?{where}",
            (image_data, int(bool(manual)), spec_code),
        )
        changed = self.cursor.rowcount > 0
        self.conn.commit()
        if changed:
            self.set_setting("cost_sync_local_dirty", "1")
        return changed

    def inherit_single_multiplier_combo_thumbnails(self, spec_codes=None, mark_dirty=True):
        """Fill empty xN combo thumbnails from their one real single-product component."""
        codes = list(dict.fromkeys(
            str(code or "").strip() for code in (spec_codes or []) if str(code or "").strip()
        ))
        where = ""
        params = ()
        if codes:
            where = f" AND spec_code IN ({','.join('?' for _ in codes)})"
            params = tuple(codes)
        candidates = {}
        for combo_code, combo_name, raw_json in self.safe_fetchall(
            f"""SELECT spec_code, COALESCE(spec_name, ''), COALESCE(combo_components_json, '')
                FROM cost_library
                WHERE COALESCE(product_attribute_is_combo, 0)=1
                  AND LENGTH(COALESCE(thumbnail_data, X''))=0{where}""",
            params,
        ):
            if any(separator in str(combo_name or "") for separator in ("+", "＋", "﹢")):
                continue
            try:
                items = self._normalise_combo_items(json.loads(raw_json or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if len(items) != 1 or float(items[0]["quantity"]) <= 1:
                continue
            source_code = str(items[0]["spec_code"])
            if source_code != str(combo_code):
                candidates[str(combo_code)] = source_code
        if not candidates:
            return []

        source_images = {}
        source_codes = list(dict.fromkeys(candidates.values()))
        for start in range(0, len(source_codes), 800):
            batch = source_codes[start:start + 800]
            placeholders = ",".join("?" for _ in batch)
            source_images.update({
                str(code): bytes(image_data or b"")
                for code, image_data in self.safe_fetchall(
                    f"""SELECT spec_code, thumbnail_data FROM cost_library
                        WHERE spec_code IN ({placeholders})
                          AND COALESCE(product_attribute_is_combo, 0)=0
                          AND LENGTH(COALESCE(thumbnail_data, X''))>0""",
                    tuple(batch),
                )
            })

        changed_codes = []
        with self.conn:
            for combo_code, source_code in candidates.items():
                image_data = source_images.get(source_code)
                if not image_data:
                    continue
                cursor = self.conn.execute(
                    """UPDATE cost_library SET thumbnail_data=?, thumbnail_manual=0
                       WHERE spec_code=? AND LENGTH(COALESCE(thumbnail_data, X''))=0""",
                    (image_data, combo_code),
                )
                if cursor.rowcount:
                    changed_codes.append(combo_code)
        if changed_codes and mark_dirty:
            self.set_setting("cost_sync_local_dirty", "1")
        return changed_codes

    def category_color_for_label(self, label):
        label = str(label or "").strip()
        if not label:
            return ""
        try:
            rows = self.safe_fetchall("SELECT color FROM cost_categories WHERE label=?", (label,))
            if rows and rows[0][0]:
                return rows[0][0]
        except Exception:
            pass
        digest = hashlib.md5(label.encode("utf-8")).hexdigest()
        return self.CATEGORY_COLORS[int(digest[:8], 16) % len(self.CATEGORY_COLORS)]

    def ensure_cost_category(self, label, color=None):
        label = str(label or "").strip()
        if not label:
            return ""
        existing = self.safe_fetchall("SELECT color FROM cost_categories WHERE label=?", (label,))
        if existing:
            existing_color = existing[0][0]
            if existing_color:
                return existing_color
            digest = hashlib.md5(label.encode("utf-8")).hexdigest()
            generated_color = self.CATEGORY_COLORS[int(digest[:8], 16) % len(self.CATEGORY_COLORS)]
            self.cursor.execute("UPDATE cost_categories SET color=? WHERE label=?", (generated_color, label))
            self.conn.commit()
            return generated_color
        if not color:
            digest = hashlib.md5(label.encode("utf-8")).hexdigest()
            color = self.CATEGORY_COLORS[int(digest[:8], 16) % len(self.CATEGORY_COLORS)]
        max_order_rows = self.safe_fetchall("SELECT MAX(sort_order) FROM cost_categories")
        next_order = (max_order_rows[0][0] if max_order_rows and max_order_rows[0][0] is not None else 0) + 1
        self.cursor.execute(
            "INSERT OR IGNORE INTO cost_categories (label, color, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (label, color, next_order, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        self.conn.commit()
        return color

    def sync_cost_categories(self):
        try:
            rows = self.safe_fetchall(
                """SELECT category_label, MAX(COALESCE(category_color, ''))
                   FROM cost_library
                   WHERE COALESCE(category_label, '') <> ''
                   GROUP BY category_label"""
            )
            for label, existing_color in rows:
                self.ensure_cost_category(label, existing_color or None)
            self.cursor.execute(
                """UPDATE cost_library
                   SET category_color = (
                       SELECT color FROM cost_categories
                       WHERE cost_categories.label = cost_library.category_label
                   )
                   WHERE COALESCE(category_label, '') <> ''"""
            )
            self.conn.commit()
            return len(rows)
        except Exception as e:
            print(f"同步成本库商品类型失败: {e}")
            return 0

    def normalize_cost_category_colors(self):
        """统一旧版本由不同入口生成的商品类型颜色。"""
        try:
            return self.sync_cost_categories()
        except Exception as e:
            print(f"统一成本库商品类型颜色失败: {e}")
            return 0

    def update_cost_category_color(self, label, color):
        label = str(label or "").strip()
        color = str(color or "").strip()
        if not label or not color:
            return False
        self.ensure_cost_category(label, color)
        try:
            self.cursor.execute("UPDATE cost_categories SET color=? WHERE label=?", (color, label))
            self.cursor.execute("UPDATE cost_library SET category_color=? WHERE category_label=?", (color, label))
            self.conn.commit()
            self.set_setting("cost_sync_local_dirty", "1")
            return True
        except Exception as e:
            print(f"更新商品类型颜色失败: {e}")
            return False

    def rename_cost_category(self, old_label, new_label):
        old_label = str(old_label or "").strip()
        new_label = str(new_label or "").strip()
        if not old_label or not new_label or old_label == new_label:
            return False
        if self.safe_fetchall("SELECT 1 FROM cost_categories WHERE label=?", (new_label,)):
            raise ValueError("商品类型名称已存在。")
        try:
            color_rows = self.safe_fetchall("SELECT color FROM cost_categories WHERE label=?", (old_label,))
            color = color_rows[0][0] if color_rows and color_rows[0][0] else self.category_color_for_label(new_label)
            self.cursor.execute("UPDATE cost_categories SET label=?, color=? WHERE label=?", (new_label, color, old_label))
            self.cursor.execute(
                "UPDATE cost_library SET category_label=?, category_color=? WHERE category_label=?",
                (new_label, color, old_label),
            )
            self.cursor.execute(
                "UPDATE products SET product_category_label=? WHERE product_category_label=?",
                (new_label, old_label),
            )
            self.conn.commit()
            self.set_setting("cost_sync_local_dirty", "1")
            return True
        except Exception:
            self.conn.rollback()
            raise

    def delete_cost_categories(self, labels):
        labels = [str(label or "").strip() for label in (labels or [])]
        labels = [label for label in dict.fromkeys(labels) if label]
        if not labels:
            return 0
        placeholders = ",".join("?" for _ in labels)
        try:
            self.cursor.execute(
                f"UPDATE cost_library SET category_label='', category_color='' WHERE category_label IN ({placeholders})",
                labels,
            )
            self.cursor.execute(
                f"UPDATE products SET product_category_label='' WHERE product_category_label IN ({placeholders})",
                labels,
            )
            self.cursor.execute(f"DELETE FROM cost_categories WHERE label IN ({placeholders})", labels)
            deleted = self.cursor.rowcount
            self.conn.commit()
            self.set_setting("cost_sync_local_dirty", "1")
            return deleted
        except Exception:
            self.conn.rollback()
            raise

    def update_cost_spec_category(self, spec_code, label):
        spec_code = str(spec_code or "").strip()
        label = str(label or "").strip()
        if not spec_code:
            return False
        color = self.ensure_cost_category(label) if label else ""
        try:
            self.cursor.execute(
                "UPDATE cost_library SET category_label=?, category_color=? WHERE spec_code=?",
                (label, color, spec_code),
            )
            self.conn.commit()
            self.set_setting("cost_sync_local_dirty", "1")
            return True
        except Exception as e:
            print(f"更新规格商品类型失败: {e}")
            return False

    def update_cost_manual_sort_orders(self, ordered_spec_codes):
        try:
            for index, spec_code in enumerate(ordered_spec_codes, start=1):
                self.cursor.execute(
                    "UPDATE cost_library SET manual_sort_order=? WHERE spec_code=?",
                    (index, spec_code),
                )
            self.conn.commit()
            self.set_setting("cost_sync_local_dirty", "1")
            return True
        except Exception as e:
            print(f"保存成本库手动排序失败: {e}")
            return False

    def get_cost_categories_with_counts(self):
        try:
            self.sync_cost_categories()
            self.update_all_product_category_labels()
            return self.safe_fetchall(
                """SELECT cc.label, cc.color,
                          COALESCE(spec_counts.spec_count, 0) AS spec_count,
                          COALESCE(link_counts.link_count, 0) AS link_count
                   FROM cost_categories cc
                   LEFT JOIN (
                       SELECT category_label, COUNT(*) AS spec_count
                       FROM cost_library
                       WHERE COALESCE(category_label, '') <> ''
                       GROUP BY category_label
                   ) spec_counts ON spec_counts.category_label = cc.label
                   LEFT JOIN (
                       SELECT product_category_label, COUNT(*) AS link_count
                       FROM products
                       WHERE COALESCE(product_category_label, '') <> ''
                       GROUP BY product_category_label
                   ) link_counts ON link_counts.product_category_label = cc.label
                   WHERE COALESCE(cc.label, '') <> ''
                   ORDER BY cc.sort_order, cc.label"""
            )
        except Exception as e:
            print(f"读取商品类型统计失败: {e}")
            return []

    def ensure_link_combination(self, name):
        name = str(name or "").strip()
        if not name:
            return None
        rows = self.safe_fetchall("SELECT id FROM link_combinations WHERE name=?", (name,))
        if rows:
            return rows[0][0]
        max_order_rows = self.safe_fetchall("SELECT MAX(sort_order) FROM link_combinations")
        next_order = (max_order_rows[0][0] if max_order_rows and max_order_rows[0][0] is not None else 0) + 1
        self.cursor.execute(
            "INSERT INTO link_combinations (name, sort_order, created_at) VALUES (?, ?, ?)",
            (name, next_order, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_link_combinations_with_counts(self, store_id=None, product_code_search=""):
        try:
            store_clause = " AND p.store_id = ?" if store_id is not None else ""
            params = [store_id] if store_id is not None else []
            where_clause = ""
            search_terms = [term.strip().lower() for term in str(product_code_search or "").split() if term.strip()]
            if search_terms:
                exists_store_clause = " AND p2.store_id = ?" if store_id is not None else ""
                where_parts = [
                    "EXISTS (SELECT 1 FROM products p2 WHERE p2.link_combo_id = lc.id AND COALESCE(p2.is_archived, 0) = 0"
                    + exists_store_clause
                ]
                if store_id is not None:
                    params.append(store_id)
                for term in search_terms:
                    if term in ("无链接类型", "没有链接类型", "空链接类型", "未设置链接类型"):
                        where_parts.append("AND COALESCE(p2.link_type, '') = ''")
                    else:
                        where_parts.append(
                            "AND (LOWER(COALESCE(p2.name, '')) LIKE ? "
                            "OR LOWER(COALESCE(p2.title, '')) LIKE ? "
                            "OR LOWER(COALESCE(p2.link_type, '')) LIKE ? "
                            "OR LOWER(COALESCE(lc.name, '')) LIKE ?)"
                        )
                        params.extend([f"%{term}%"] * 4)
                where_parts.append(")")
                where_clause = "WHERE " + " ".join(where_parts)
            return self.safe_fetchall(
                f"""SELECT lc.id, lc.name, COALESCE(lc.sort_order, 0), COUNT(p.id) AS link_count
                   FROM link_combinations lc
                   LEFT JOIN products p ON p.link_combo_id = lc.id
                    AND COALESCE(p.is_archived, 0) = 0{store_clause}
                   {where_clause}
                   GROUP BY lc.id, lc.name, lc.sort_order
                   ORDER BY COALESCE(lc.sort_order, 0), lc.name""",
                tuple(params),
            )
        except Exception as e:
            print(f"读取链接组合失败: {e}")
            return []

    def rename_link_combination(self, combo_id, name):
        name = str(name or "").strip()
        if not combo_id or not name:
            return False
        try:
            self.cursor.execute("UPDATE link_combinations SET name=? WHERE id=?", (name, combo_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"重命名链接组合失败: {e}")
            return False

    def update_product_link_combo(self, product_id, combo_id):
        try:
            self.cursor.execute("UPDATE products SET link_combo_id=? WHERE id=?", (combo_id, product_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"移动链接组合失败: {e}")
            return False

    def delete_link_combinations(self, combo_ids):
        ids = []
        for combo_id in combo_ids or []:
            try:
                value = int(combo_id)
            except (TypeError, ValueError):
                continue
            if value not in ids:
                ids.append(value)
        if not ids:
            return 0
        placeholders = ",".join(["?"] * len(ids))
        try:
            self.cursor.execute(f"UPDATE products SET link_combo_id=NULL WHERE link_combo_id IN ({placeholders})", tuple(ids))
            self.cursor.execute(f"DELETE FROM link_combinations WHERE id IN ({placeholders})", tuple(ids))
            deleted = self.cursor.rowcount
            self.conn.commit()
            return deleted
        except Exception as e:
            self.conn.rollback()
            print(f"删除链接组合失败: {e}")
            raise

    def update_product_link_type(self, product_id, link_type):
        try:
            self.cursor.execute("UPDATE products SET link_type=? WHERE id=?", (str(link_type or "").strip(), product_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"更新链接类型失败: {e}")
            return False

    def calculate_product_category_label(self, product_id):
        """Return the hidden product type label inferred from spec cost-library categories."""
        try:
            rows = self.safe_fetchall(
                """SELECT ps.spec_code, ps.sale_price, cl.category_label
                   FROM product_specs ps
                   LEFT JOIN cost_library cl ON ps.spec_code = cl.spec_code
                   WHERE ps.product_id=?
                   ORDER BY ps.id""",
                (product_id,),
            )
            buckets = {}
            for idx, (_spec_code, sale_price, category_label) in enumerate(rows):
                label = str(category_label or "").strip()
                if not label:
                    continue
                try:
                    price = float(sale_price) if sale_price is not None else 0.0
                except (TypeError, ValueError):
                    price = 0.0
                info = buckets.setdefault(
                    label,
                    {"count": 0, "max_price": 0.0, "first_index": idx},
                )
                info["count"] += 1
                if price > info["max_price"]:
                    info["max_price"] = price
            if not buckets:
                return ""
            return sorted(
                buckets.items(),
                key=lambda item: (
                    -item[1]["count"],
                    -item[1]["max_price"],
                    item[1]["first_index"],
                    item[0],
                ),
            )[0][0]
        except Exception as e:
            print(f"计算链接商品类型失败: {e}")
            return ""

    def update_product_category_label(self, product_id):
        try:
            label = self.calculate_product_category_label(product_id)
            self.safe_execute(
                "UPDATE products SET product_category_label=? WHERE id=?",
                (label, product_id),
            )
            return label
        except Exception as e:
            print(f"更新链接商品类型失败: {e}")
            return ""

    def update_all_product_category_labels(self, store_id=None):
        try:
            products = (
                self.safe_fetchall("SELECT id FROM products WHERE store_id=? AND COALESCE(is_archived, 0)=0", (store_id,))
                if store_id
                else self.safe_fetchall("SELECT id FROM products WHERE COALESCE(is_archived, 0)=0")
            )
            count = 0
            for (product_id,) in products:
                self.update_product_category_label(product_id)
                count += 1
            return count
        except Exception as e:
            print(f"批量更新链接商品类型失败: {e}")
            return 0

    def calculate_product_gross_margin_metrics(self, product_id):
        """统一计算链接综合毛利口径：券后价、规格权重、成本库成本。"""
        result = {
            "gross_margin_pct": None,
            "avg_final_price": None,
            "avg_gross_profit": None,
            "total_weight": 0.0,
            "valid_spec_count": 0,
            "spec_count": 0,
            "discount_amount": 0.0,
            "weight_source": "saved",
            "recognized_order_count": 0.0,
        }
        try:
            product_rows = self.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, name, store_id, COALESCE(use_manual_spec_weight, 0) FROM products WHERE id=?",
                (product_id,),
            )
            coupon = float(product_rows[0][0] or 0) if product_rows else 0.0
            new_customer = float(product_rows[0][1] or 0) if product_rows else 0.0
            product_code = str(product_rows[0][2] or "") if product_rows else ""
            store_id = product_rows[0][3] if product_rows else None
            use_manual_spec_weight = bool(product_rows and product_rows[0][4])
            discount_amount = max(coupon, new_customer)
            result["discount_amount"] = discount_amount

            rows = self.safe_fetchall(
                """SELECT spec_code, sale_price, weight_percent FROM product_specs
                   WHERE product_id=? AND COALESCE(is_temporarily_off_shelf, 0)=0""",
                (product_id,),
            )
            result["spec_count"] = len(rows)
            spec_codes = {str(spec_code or "") for spec_code, _sale_price, _weight in rows if spec_code}
            cost_map = {}
            if spec_codes:
                placeholders = ",".join("?" for _ in spec_codes)
                cost_map = {
                    str(spec_code): float(cost_price or 0)
                    for spec_code, cost_price in self.safe_fetchall(
                        f"SELECT spec_code, cost_price FROM cost_library WHERE spec_code IN ({placeholders})",
                        tuple(spec_codes),
                    )
                }
            store_discount_rules = self.get_store_discount_rules(store_id) if store_id else []
            order_weight_map = {}
            recognized_total_orders = 0.0
            if product_code and spec_codes:
                order_rows = self.safe_fetchall(
                    "SELECT spec_code, SUM(order_count) FROM imported_orders "
                    "WHERE store_id=? AND product_id=? GROUP BY spec_code",
                    (store_id, product_code),
                )
                for spec_code, order_count in order_rows:
                    spec_code = str(spec_code or "")
                    if spec_code not in spec_codes:
                        continue
                    try:
                        order_count = float(order_count or 0)
                    except (TypeError, ValueError):
                        order_count = 0.0
                    if order_count > 0:
                        order_weight_map[spec_code] = order_count
                        recognized_total_orders += order_count
            use_order_weights = recognized_total_orders > 0 and not use_manual_spec_weight
            total_weighted_margin = 0.0
            total_weighted_price = 0.0
            total_weighted_gross_profit = 0.0
            total_weight = 0.0
            valid_spec_count = 0
            for spec_code, sale_price, weight in rows:
                try:
                    sale_price = float(sale_price or 0)
                    if use_order_weights:
                        weight = (order_weight_map.get(str(spec_code or ""), 0.0) / recognized_total_orders) * 100.0
                    else:
                        weight = float(weight or 0)
                except (TypeError, ValueError):
                    continue
                if sale_price <= 0 or weight <= 0:
                    continue
                cost = cost_map.get(str(spec_code or ""), 0.0)
                matching_discounts = [
                    float(rule.get("discount") or 0)
                    for rule in store_discount_rules
                    if sale_price + 1e-9 >= float(rule.get("threshold") or 0)
                ]
                store_discount = max(matching_discounts, default=0.0)
                effective_discount = max(discount_amount, store_discount)
                result["discount_amount"] = max(float(result.get("discount_amount") or 0), effective_discount)
                final_price = sale_price - effective_discount
                if final_price <= 0 or cost <= 0:
                    continue
                margin = (final_price - cost) / final_price
                gross_profit = final_price - cost
                total_weighted_margin += margin * weight
                total_weighted_price += final_price * weight
                total_weighted_gross_profit += gross_profit * weight
                total_weight += weight
                valid_spec_count += 1

            result["total_weight"] = total_weight
            result["valid_spec_count"] = valid_spec_count
            result["weight_source"] = "orders" if use_order_weights else ("manual" if use_manual_spec_weight else "saved")
            result["recognized_order_count"] = recognized_total_orders if use_order_weights else 0.0
            if total_weight > 0:
                result["gross_margin_pct"] = (total_weighted_margin / total_weight) * 100
                result["avg_final_price"] = total_weighted_price / total_weight
                result["avg_gross_profit"] = total_weighted_gross_profit / total_weight
        except Exception as e:
            print(f"计算链接综合毛利失败: {e}")
        return result

    def calculate_promotion_profit_snapshot(self, product_id, net_amount, cost):
        net_amount = float(net_amount or 0)
        cost = float(cost or 0)
        if net_amount <= 0:
            return -cost, (-100.0 if cost > 0 else 0.0)
        margin_pct = self.calculate_product_gross_margin_metrics(product_id).get("gross_margin_pct")
        if margin_pct is None:
            return None, None
        net_profit = net_amount * (float(margin_pct) / 100.0) - cost - net_amount * 0.006
        return net_profit, net_profit / net_amount * 100

    def repair_missing_promotion_profits(self):
        rows = self.safe_fetchall(
            """SELECT d.id, p.id, d.net_transaction_amount, d.cost
               FROM promotion_daily_data d
               JOIN products p ON p.store_id=d.store_id AND p.name=d.product_id
               WHERE d.net_profit IS NULL AND d.net_transaction_amount>0"""
        )
        updates = []
        for record_id, product_id, net_amount, cost in rows:
            net_profit, net_margin_rate = self.calculate_promotion_profit_snapshot(product_id, net_amount, cost)
            if net_profit is not None:
                updates.append((net_profit, net_margin_rate, record_id))
        if updates:
            with self.conn:
                self.conn.executemany(
                    "UPDATE promotion_daily_data SET net_profit=?, net_margin_rate=? WHERE id=?",
                    updates,
                )
        return len(updates)

    def calculate_products_gross_margin_metrics(self, product_ids):
        """Calculate card margin data in a fixed number of queries."""
        product_ids = {int(product_id) for product_id in product_ids if product_id is not None}
        if not product_ids:
            return {}

        placeholders = ",".join("?" for _ in product_ids)
        product_rows = self.safe_fetchall(
            f"SELECT id, coupon_amount, new_customer_discount, name, store_id, "
            f"COALESCE(use_manual_spec_weight, 0) FROM products WHERE id IN ({placeholders})",
            tuple(product_ids),
        )
        products = {row[0]: row[1:] for row in product_rows}
        specs_by_product = {product_id: [] for product_id in products}
        for product_id, spec_code, sale_price, weight in self.safe_fetchall(
            f"SELECT product_id, spec_code, sale_price, weight_percent "
            f"FROM product_specs WHERE product_id IN ({placeholders}) "
            "AND COALESCE(is_temporarily_off_shelf, 0)=0",
            tuple(product_ids),
        ):
            if product_id in specs_by_product:
                specs_by_product[product_id].append((spec_code, sale_price, weight))

        needed_spec_codes = {
            str(spec_code or "")
            for rows in specs_by_product.values()
            for spec_code, _sale_price, _weight in rows
            if spec_code
        }
        spec_placeholders = ",".join("?" for _ in needed_spec_codes)
        cost_map = {
            str(spec_code): float(cost_price or 0)
            for spec_code, cost_price in (
                self.safe_fetchall(
                    f"SELECT spec_code, cost_price FROM cost_library WHERE spec_code IN ({spec_placeholders})",
                    tuple(needed_spec_codes),
                )
                if needed_spec_codes else []
            )
        }
        store_rules = {
            store_id: self.parse_store_discount_rules(rules)
            for store_id, rules in self.safe_fetchall("SELECT id, store_discount_rules FROM stores")
        }
        product_keys = {
            (store_id, str(product_code or ""))
            for _product_id, (_coupon, _new_customer, product_code, store_id, _manual) in products.items()
        }
        store_ids = {store_id for store_id, _product_code in product_keys}
        store_placeholders = ",".join("?" for _ in store_ids)
        order_weights = {}
        if store_ids:
            for store_id, product_code, spec_code, order_count in self.safe_fetchall(
                "SELECT store_id, product_id, spec_code, SUM(order_count) "
                f"FROM imported_orders WHERE store_id IN ({store_placeholders}) GROUP BY store_id, product_id, spec_code",
                tuple(store_ids),
            ):
                key = (store_id, str(product_code or ""))
                if key in product_keys:
                    order_weights[(store_id, key[1], str(spec_code or ""))] = float(order_count or 0)

        results = {}
        for product_id, (coupon, new_customer, product_code, store_id, manual_weight) in products.items():
            rows = specs_by_product.get(product_id, [])
            result = {
                "gross_margin_pct": None, "avg_final_price": None, "avg_gross_profit": None,
                "total_weight": 0.0, "valid_spec_count": 0, "spec_count": len(rows),
                "discount_amount": 0.0,
                "weight_source": "saved", "recognized_order_count": 0.0,
            }
            coupon = float(coupon or 0)
            new_customer = float(new_customer or 0)
            discount_amount = max(coupon, new_customer)
            result["discount_amount"] = discount_amount
            spec_codes = {str(row[0] or "") for row in rows if row[0]}
            weights = {
                code: order_weights.get((store_id, str(product_code or ""), code), 0.0)
                for code in spec_codes
            }
            recognized_orders = sum(value for value in weights.values() if value > 0)
            use_order_weights = recognized_orders > 0 and not manual_weight
            total_margin = total_price = total_profit = total_weight = 0.0
            valid_count = 0
            for spec_code, sale_price, saved_weight in rows:
                try:
                    sale_price = float(sale_price or 0)
                    weight = (
                        weights.get(str(spec_code or ""), 0.0) / recognized_orders * 100.0
                        if use_order_weights else float(saved_weight or 0)
                    )
                except (TypeError, ValueError):
                    continue
                if sale_price <= 0 or weight <= 0:
                    continue
                cost = cost_map.get(str(spec_code or ""), 0.0)
                store_discount = max(
                    (
                        float(rule.get("discount") or 0)
                        for rule in store_rules.get(store_id, [])
                        if sale_price + 1e-9 >= float(rule.get("threshold") or 0)
                    ),
                    default=0.0,
                )
                effective_discount = max(discount_amount, store_discount)
                result["discount_amount"] = max(result["discount_amount"], effective_discount)
                final_price = sale_price - effective_discount
                if final_price <= 0 or cost <= 0:
                    continue
                gross_profit = final_price - cost
                total_margin += gross_profit / final_price * weight
                total_price += final_price * weight
                total_profit += gross_profit * weight
                total_weight += weight
                valid_count += 1
            result.update({
                "total_weight": total_weight,
                "valid_spec_count": valid_count,
                "weight_source": "orders" if use_order_weights else ("manual" if manual_weight else "saved"),
                "recognized_order_count": recognized_orders if use_order_weights else 0.0,
            })
            if total_weight > 0:
                result.update({
                    "gross_margin_pct": total_margin / total_weight * 100,
                    "avg_final_price": total_price / total_weight,
                    "avg_gross_profit": total_profit / total_weight,
                })
            results[product_id] = result
        return results

    def parse_store_discount_rules(self, value):
        """解析店铺满减梯度，返回按门槛升序的 [{'threshold': x, 'discount': y}]。"""
        if not value:
            return []
        try:
            raw_rules = json.loads(value) if isinstance(value, str) else value
        except Exception:
            return []
        rules = []
        if not isinstance(raw_rules, list):
            return rules
        for item in raw_rules:
            if not isinstance(item, dict):
                continue
            try:
                threshold = float(item.get("threshold") or 0)
                discount = float(item.get("discount") or 0)
            except (TypeError, ValueError):
                continue
            if threshold > 0 and discount > 0:
                rules.append({"threshold": threshold, "discount": discount})
        rules.sort(key=lambda row: (row["threshold"], row["discount"]))
        return rules

    def get_store_discount_rules(self, store_id):
        rows = self.safe_fetchall("SELECT store_discount_rules FROM stores WHERE id=?", (store_id,))
        return self.parse_store_discount_rules(rows[0][0] if rows else "")

    def save_store_discount_rules(self, store_id, rules):
        clean_rules = self.parse_store_discount_rules(rules)
        self.safe_execute(
            "UPDATE stores SET store_discount_rules=? WHERE id=?",
            (json.dumps(clean_rules, ensure_ascii=False), store_id),
        )
        return clean_rules

    def calculate_store_discount(self, store_id, amount):
        """按商品/规格价格命中店铺满减梯度，取满足门槛的最高减免。"""
        try:
            amount = float(amount or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            return 0.0, None
        matched = None
        for rule in self.get_store_discount_rules(store_id):
            if amount + 1e-9 >= float(rule.get("threshold") or 0):
                if matched is None or float(rule.get("discount") or 0) >= float(matched.get("discount") or 0):
                    matched = rule
        return (float(matched.get("discount") or 0), matched) if matched else (0.0, None)

    def format_store_discount_rules(self, store_id):
        rules = self.get_store_discount_rules(store_id)
        if not rules:
            return "未设置"
        parts = []
        for rule in rules:
            threshold = float(rule.get("threshold") or 0)
            discount = float(rule.get("discount") or 0)
            threshold_text = f"{threshold:.2f}".rstrip("0").rstrip(".")
            discount_text = f"{discount:.2f}".rstrip("0").rstrip(".")
            parts.append(f"满{threshold_text}减{discount_text}")
        return "；".join(parts)

    def get_all_prompts(self):
        try:
            return self.safe_fetchall("SELECT id, name, content, is_active, is_system FROM ai_prompts ORDER BY is_system DESC, id ASC")
        except Exception:
            return []

    def get_active_prompt(self):
        try:
            res = self.safe_fetchall("SELECT content, is_system FROM ai_prompts WHERE is_active=1")
            if res:
                return res[0][0], res[0][1]
            return None, 0
        except Exception:
            return None, 0

    def save_prompt(self, name, content, is_system=False):
        try:
            self.safe_execute("INSERT INTO ai_prompts (name, content, is_system, created_at) VALUES (?, ?, ?, datetime('now'))",
                              (name, content, 1 if is_system else 0))
        except Exception as e:
            print(f"保存提示词失败: {e}")

    def set_active_prompt(self, prompt_id):
        try:
            self.safe_execute("UPDATE ai_prompts SET is_active=0")
            self.safe_execute("UPDATE ai_prompts SET is_active=1 WHERE id=?", (prompt_id,))
        except Exception as e:
            print(f"设置激活提示词失败: {e}")

    def update_prompt(self, prompt_id, name, content):
        try:
            self.safe_execute("UPDATE ai_prompts SET name=?, content=? WHERE id=?", (name, content, prompt_id))
        except Exception as e:
            print(f"更新提示词失败: {e}")

    def delete_prompt(self, prompt_id):
        try:
            self.safe_execute("DELETE FROM ai_prompts WHERE id=? AND is_system=0", (prompt_id,))
        except Exception as e:
            print(f"删除提示词失败: {e}")

    def get_all_common_prompts(self):
        try:
            return self.safe_fetchall("SELECT id, content, is_active, sort_order FROM ai_common_prompts ORDER BY sort_order ASC, id ASC")
        except Exception:
            return []

    def get_active_common_prompts(self):
        try:
            rows = self.safe_fetchall("SELECT content FROM ai_common_prompts WHERE is_active=1 ORDER BY sort_order ASC, id ASC")
            return [row[0] for row in rows]
        except Exception:
            return []

    def add_common_prompt(self, content):
        try:
            max_order = self.safe_fetchall("SELECT MAX(sort_order) FROM ai_common_prompts")
            next_order = (max_order[0][0] or 0) + 1
            self.safe_execute("INSERT INTO ai_common_prompts (content, is_active, sort_order, created_at) VALUES (?, 1, ?, datetime('now'))",
                              (content, next_order))
        except Exception as e:
            print(f"添加通用提示词失败: {e}")

    def update_common_prompt(self, prompt_id, content):
        try:
            self.safe_execute("UPDATE ai_common_prompts SET content=? WHERE id=?", (content, prompt_id))
        except Exception as e:
            print(f"更新通用提示词失败: {e}")

    def delete_common_prompt(self, prompt_id):
        try:
            self.safe_execute("DELETE FROM ai_common_prompts WHERE id=?", (prompt_id,))
        except Exception as e:
            print(f"删除通用提示词失败: {e}")

    def toggle_common_prompt(self, prompt_id, is_active):
        try:
            self.safe_execute("UPDATE ai_common_prompts SET is_active=? WHERE id=?", (1 if is_active else 0, prompt_id))
        except Exception as e:
            print(f"切换通用提示词状态失败: {e}")
    def save_daily_record(self, store_id, record_date, category, special_info, memo):
        try:
            existing = self.safe_fetchall(
                "SELECT id FROM daily_records WHERE store_id=? AND record_date=?",
                (store_id, record_date)
            )
            if existing:
                self.safe_execute(
                    """UPDATE daily_records SET category=?, special_info=?, memo=?, updated_at=datetime('now') 
                    WHERE store_id=? AND record_date=?""",
                    (category, special_info, memo, store_id, record_date)
                )
            else:
                self.safe_execute(
                    """INSERT INTO daily_records (store_id, record_date, category, special_info, memo, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                    (store_id, record_date, category, special_info, memo)
                )
        except Exception as e:
            print(f"保存每日记录失败: {e}")

    def get_daily_record(self, store_id, record_date):
        try:
            res = self.safe_fetchall(
                "SELECT category, special_info, memo FROM daily_records WHERE store_id=? AND record_date=?",
                (store_id, record_date)
            )
            return res[0] if res else (None, None, None)
        except Exception as e:
            print(f"获取每日记录失败: {e}")
            return (None, None, None)

    def get_store_daily_records(self, store_id, limit=30):
        try:
            return self.safe_fetchall(
                """SELECT record_date, category, special_info, memo FROM daily_records 
                WHERE store_id=? ORDER BY record_date DESC LIMIT ?""",
                (store_id, limit)
            )
        except Exception as e:
            print(f"获取店铺每日记录失败: {e}")
            return []

    def save_store_prompt(self, store_id, prompt_text):
        try:
            existing = self.safe_fetchall("SELECT id FROM store_prompts WHERE store_id=?", (store_id,))
            if existing:
                self.safe_execute(
                    "UPDATE store_prompts SET prompt_text=?, updated_at=datetime('now') WHERE store_id=?",
                    (prompt_text, store_id)
                )
            else:
                self.safe_execute(
                    "INSERT INTO store_prompts (store_id, prompt_text, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
                    (store_id, prompt_text)
                )
        except Exception as e:
            print(f"保存店铺提示词失败: {e}")

    def get_store_prompt(self, store_id):
        try:
            res = self.safe_fetchall("SELECT prompt_text FROM store_prompts WHERE store_id=?", (store_id,))
            return res[0][0] if res and res[0][0] else ""
        except Exception as e:
            print(f"获取店铺提示词失败: {e}")
            return ""

    LABEL_CONFIG = {
        'coupon': {'name': '优惠券', 'icon': 'coupon.svg', 'color': '#d81e06'},
        'new_customer': {'name': '新客立减', 'icon': 'new_customer.svg', 'color': '#9b59b6'},
        'limited_time': {'name': '限时限量购', 'icon': 'limited-time.svg', 'color': '#e74c3c'},
        'marketing': {'name': '营销活动', 'icon': 'marketing.svg', 'color': '#9b59b6'},
        'natural_flow': {'name': '无推广', 'icon': None, 'color': '#16a085'},
        'sitewide': {'name': '全站托管', 'icon': None, 'color': '#8e44ad'},
        'profit': {'name': '盈利状态', 'icon': None, 'color_profit': '#27ae60', 'color_loss': '#e74c3c'},
    }

    TAG_STATUS_CODES = {0: '未设置', 1: '盈利', -1: '亏损'}

    def get_product_tags(self, product_id):
        try:
            res = self.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, is_limited_time, is_marketing, profit_status, is_natural_flow, is_sitewide_managed FROM products WHERE id=?",
                (product_id,)
            )
            if res and res[0]:
                return {
                    'coupon': res[0][0] > 0,
                    'new_customer': res[0][1] > 0,
                    'limited_time': bool(res[0][2]),
                    'marketing': bool(res[0][3]),
                    'profit_status': res[0][4],
                    'natural_flow': bool(res[0][5]),
                    'sitewide': bool(res[0][6]) and not bool(res[0][5]),
                }
            return {'coupon': False, 'new_customer': False, 'limited_time': False, 'marketing': False, 'profit_status': 0, 'natural_flow': False, 'sitewide': False}
        except Exception as e:
            print(f"获取商品标签失败: {e}")
            return {'coupon': False, 'new_customer': False, 'limited_time': False, 'marketing': False, 'profit_status': 0, 'natural_flow': False, 'sitewide': False}

    def update_product_profit_status(self, product_id, profit=None):
        try:
            if profit is not None:
                profit_status = 1 if profit > 0 else (-1 if profit < 0 else 0)
            else:
                profit_status = self.calculate_profit_label_from_db(product_id)
            self.safe_execute("UPDATE products SET profit_status=? WHERE id=?", (profit_status, product_id))
            return profit_status
        except Exception as e:
            print(f"更新盈利状态失败: {e}")
            return 0

    def calculate_profit_label_from_db(self, product_id):
        try:
            specs = self.safe_fetchall(
                """SELECT spec_code, sale_price, weight_percent FROM product_specs
                   WHERE product_id=? AND COALESCE(is_temporarily_off_shelf, 0)=0""",
                (product_id,)
            )
            if not specs:
                return 0
            prod_res = self.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, store_id FROM products WHERE id=?",
                (product_id,)
            )
            coupon = prod_res[0][0] or 0 if prod_res else 0
            new_customer = prod_res[0][1] or 0 if prod_res else 0
            store_id = prod_res[0][2] if prod_res else None
            total_weight = 0
            total_profit = 0
            total_final_price = 0
            for spec_code, sale_price, weight in specs:
                if not sale_price or sale_price <= 0:
                    continue
                weight = weight or 0
                cost_res = self.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
                cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
                store_discount, _rule = self.calculate_store_discount(store_id, sale_price) if store_id else (0.0, None)
                final_price = sale_price - max(coupon, new_customer, store_discount)
                if final_price > 0:
                    profit = final_price - cost
                    total_profit += profit * weight
                    total_final_price += final_price * weight
                    total_weight += weight
            if total_weight > 0:
                avg_profit = total_profit / total_weight
                avg_final_price = total_final_price / total_weight
                net_margin_rate = (avg_profit / avg_final_price) * 100 if avg_final_price > 0 else 0
                if net_margin_rate > 5:
                    return 1
                if net_margin_rate < 5:
                    return -1
                return 0
            return 0
        except Exception as e:
            print(f"计算利润标签失败: {e}")
            return 0

    def update_all_profit_status(self, store_id=None):
        try:
            products = self.safe_fetchall("SELECT id FROM products WHERE store_id=?", (store_id,)) if store_id else self.safe_fetchall("SELECT id FROM products")
            count = 0
            for prod in products:
                self.calculate_profit_label_from_db(prod[0])
                count += 1
            print(f"已更新 {count} 个商品的利润标签")
            return count
        except Exception as e:
            print(f"批量更新利润标签失败: {e}")
            return 0

    def get_products_by_tags(self, tag_filters=None, store_id=None):
        try:
            if not tag_filters:
                return []
            conditions = []
            params = []
            conditions.append("COALESCE(is_archived, 0)=0")
            if store_id:
                conditions.append("store_id = ?")
                params.append(store_id)
            if tag_filters.get('limited_time'):
                conditions.append("is_limited_time = 1")
            if tag_filters.get('marketing'):
                conditions.append("is_marketing = 1")
            if tag_filters.get('natural_flow'):
                conditions.append("is_natural_flow = 1")
            if tag_filters.get('sitewide'):
                conditions.append("is_sitewide_managed = 1 AND COALESCE(is_natural_flow, 0) = 0")
            if tag_filters.get('profit_status'):
                conditions.append(f"profit_status = {tag_filters['profit_status']}")
            if not conditions:
                return []
            query = f"SELECT id FROM products WHERE {' AND '.join(conditions)}"
            res = self.safe_fetchall(query, params)
            return [r[0] for r in res] if res else []
        except Exception as e:
            print(f"按标签筛选商品失败: {e}")
            return []

    def get_store_record(self, store_id, year, month, day):
        try:
            if day > 0:
                res = self.safe_fetchall(
                    "SELECT records_json FROM store_records WHERE store_id=? AND year=? AND month=? AND day=?",
                    (store_id, year, month, day)
                )
                if res and res[0][0]:
                    return json.loads(res[0][0])
                return []
            res = self.safe_fetchall(
                "SELECT day, records_json FROM store_records WHERE store_id=? AND year=? AND month=?",
                (store_id, year, month)
            )
            result = {}
            for r in res:
                try:
                    result[r[0]] = json.loads(r[1])
                except Exception as e:
                    print(f"[DEBUG] 解析数据失败: {e}")
                    result[r[0]] = []
            return result
        except Exception as e:
            print(f"获取店铺记录失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def save_store_record(self, store_id, year, month, day, records_json):
        try:
            records_str = json.dumps(records_json, ensure_ascii=False)
            self.safe_execute(
                "INSERT OR REPLACE INTO store_records (store_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
                (store_id, year, month, day, records_str)
            )
        except Exception as e:
            print(f"保存店铺记录失败: {e}")
            import traceback
            traceback.print_exc()

    def init_default_prompts(self):
        existing = self.safe_fetchall("SELECT COUNT(*) FROM ai_prompts")
        if existing and existing[0][0] > 0:
            return
        default_prompts = [
            ("专业深度分析", """你是一位资深拼多多电商运营专家，拥有多年类目运营经验，擅长数据诊断和实战操盘。请根据以下完整的推广数据，给出专业、深入、可操作的分析建议。

【分析对象】
店铺/链接：{分析对象信息}
类目：请根据客单价{客单价}元判断可能所属类目

【核心输入数据】
推广费：{推广费}元
投产比：{投产比}
退货率：{退货率}%
毛利率：{毛利率}%
客单价：{客单价}元

【衍生计算指标】
成交金额：{成交金额}元
退款金额：{退款金额}元
实际成交：{实际成交}元
产品成本：{产品成本}元
毛利润：{毛利润}元
技术服务费：{技术服务费}元
净利润：{净利润}元
净利率：{净利率}%
推广占比：{推广占比}%
成交单量：{成交单量}单
每笔成交花费：{每笔成交花费}元/单
单笔利润：{单笔利润}元/单

【投产参考线】
毛保本投产：{毛保本投产}（仅考虑毛利的保本线，放量时可参考此值）
净保本投产：{净保本投产}（扣除技术服务费后的真实保本线，低于此值即亏损）
净保本1.25倍：{净保本1.25倍}（安全线，达到此值说明链接初步跑通，但仍需优化）
最佳投产：{最佳投产}（理想目标值，达到此值可大规模放量）
当前投产倍数：{当前投产倍数}（实际投产÷毛保本投产，反映盈利深度）

---

请按以下结构输出专业分析报告：

一、盈利状况诊断
用数据说话，分析当前净利润、净利率、投产比与各参考线对比、单笔利润，并给出整体结论（盈利/保本/亏损，盈利空间大/中/小）。

二、问题点深度剖析
找出2-4个最核心的问题，每个问题按：数据表现、根本原因、影响程度、改进优先级。

三、实战优化方案
给出3-5条具体可执行建议，每条包含：具体动作、预期效果、操作难度、执行周期。

四、市场趋势与竞争分析
类目定位、竞争格局、季节/节点因素、消费者洞察、前瞻建议。

五、核心干货总结
用最精炼的语言，总结2-3个今天最该做的决策。

【特别要求】
1. 所有分析必须基于提供的数据，不能凭空捏造
2. 建议要具体到“做什么、怎么做、预期效果”三级
3. 如果是新手卖家，建议要更保守；如果是老手，可以给更激进的操盘方案

请开始输出专业报告：""", True),
            ("贴吧老哥风格", """你是一位贴吧老哥风格的拼多多推广数据分析师，说话要接地气、带点调侃，用词犀利但不失专业。根据以下完整数据，给出一针见血的分析建议。要求：整体风格要像贴吧老哥，但数据要对得上。""", True),
            ("简洁快速版", """你是拼多多数据分析助手。请根据以下数据给出简短分析建议：盈利/亏损情况、存在的主要问题（最多2个）、优化建议（最多2条，每条15字内）。""", True)
        ]
        existing = self.safe_fetchall("SELECT COUNT(*) FROM ai_prompts WHERE is_system=1")
        if not existing or existing[0][0] == 0:
            for name, content, is_system in default_prompts:
                self.save_prompt(name, content, is_system)
            self.set_active_prompt(1)
        existing_common = self.safe_fetchall("SELECT COUNT(*) FROM ai_common_prompts")
        if not existing_common or existing_common[0][0] == 0:
            default_common = [
                "拼多多日限额最低只能设置100，最高无限制",
                "关键词推广功能和ocpx推广已消失，现在推广方式只有标准推广和全站推广，标准推广比较常用，全站推广根据类目不同使用方式不同",
                "标题优化很重要，拼多多新的比价机制跟标题、主图、规格图有关系"
            ]
            for content in default_common:
                self.add_common_prompt(content)

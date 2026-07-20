# -*- coding: utf-8 -*-
"""
数据库访问层：SafeDatabaseManager。
负责 SQLite 连接、表结构、迁移和 CRUD。
"""
import os
import sys
import re
import json
import sqlite3
import hashlib
import math
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
    COMMON_SETTING_KEYS = {"auto_start_enabled", "cost_library_mode", "cost_misc_fee", "cost_shipping_rules_json"}

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
                                url TEXT, image_path TEXT, sort_order INTEGER)''')
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
            if self.get_setting("garbage_link_detection_v3_rebuilt", "0") != "1":
                self.reconcile_garbage_link_tasks()
                self.set_setting("garbage_link_detection_v3_rebuilt", "1")
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
                "transaction_bid", "return_rate", "is_limited_time", "is_marketing",
                "is_natural_flow", "is_sitewide_managed", "profit_status",
                "net_break_even_roi", "image_data", "product_category_label",
                "product_memo", "link_combo_id", "link_type", "roi_input_mode",
                "is_archived", "archived_at", "is_violation",
            },
            "cost_library": {
                "spec_name", "test_price", "quantity", "sort_order", "source_bg_color",
                "category_label", "category_color", "product_attribute",
                "product_attribute_combo_disabled", "product_attribute_is_combo",
                "manual_sort_order", "product_cost", "unit_weight", "shipping_fee",
                "misc_fee", "cost_calc_mode",
            },
            "product_specs": {"is_locked", "spec_image_data", "is_temporarily_off_shelf"},
            "daily_records": {"category", "special_info"},
            "imported_orders": {"product_id", "order_date", "actual_amount", "refund_count"},
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
                UNIQUE(store_id, product_id, spec_code))''')
            print("  ✅ 已创建新结构表 imported_orders_new")

            # 3. 迁移数据：把 products.id 转换为 products.name
            self.cursor.execute('''
                INSERT INTO imported_orders_new (id, store_id, product_id, spec_code, order_count, import_time, order_date, actual_amount, refund_count)
                SELECT
                    io.id,
                    io.store_id,
                    COALESCE(p.name, CAST(io.product_id AS TEXT)) as product_id,
                    io.spec_code,
                    io.order_count,
                    io.import_time,
                    io.order_date,
                    io.actual_amount,
                    COALESCE(io.refund_count, 0) as refund_count
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

        recent_data = {}
        rows = self.safe_fetchall(
            """SELECT product_id, net_orders FROM (
                   SELECT product_id, net_orders,
                          ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY record_date DESC) AS recent_rank
                   FROM promotion_daily_data WHERE store_id=?
               ) WHERE recent_rank<=2
               ORDER BY product_id, recent_rank""",
            (store_id,),
        )
        for product_code, net_orders in rows:
            recent_data.setdefault(str(product_code), []).append(float(net_orders or 0))

        now = datetime.now()
        created = 0
        products = self.safe_fetchall(
            """SELECT id, name, title, COALESCE(is_natural_flow, 0) FROM products
               WHERE store_id=? AND COALESCE(is_archived, 0)=0
                 AND COALESCE(is_violation, 0)=0""",
            (store_id,),
        )
        for product_id, product_code, title, is_natural_flow in products:
            values = recent_data.get(str(product_code or "").strip(), [])
            is_garbage = (
                not bool(is_natural_flow)
                and len(values) == 2
                and all(value <= 0 for value in values)
            )
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
            if exists:
                continue
            created_time = imported_at or now.strftime("%Y-%m-%d %H:%M:%S")
            self.safe_execute(
                """INSERT INTO daily_tasks (store_id, product_id, year, month, day, task_content, created_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (store_id, product_id, now.year, now.month, now.day,
                 f"【垃圾链接】该链接最近两条推广数据记录净成交笔数均为 0。商品ID：{product_code}；标题：{title or ''}", created_time),
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
                     order_date, actual_amount, refund_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    return
            self.safe_execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        except Exception as e:
            print(f"保存设置失败: {e}")

    def _is_common_setting_key(self, key):
        key = str(key or "")
        return key in self.COMMON_SETTING_KEYS or any(key.startswith(prefix) for prefix in self.COMMON_SETTING_PREFIXES)

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

    def recalculate_detailed_cost_library(self, record_history=False, source="manual"):
        rows = self.safe_fetchall(
            """SELECT spec_code, quantity, product_cost, unit_weight, cost_price
               FROM cost_library
               WHERE cost_calc_mode='detail'"""
        )
        changed = 0
        import_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.conn.execute("BEGIN TRANSACTION")
            for spec_code, quantity, product_cost, unit_weight, old_cost in rows:
                if product_cost is None or unit_weight is None:
                    continue
                new_cost, shipping_fee, misc_fee, _total_weight = self.calculate_detailed_cost(product_cost, quantity, unit_weight)
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
                if record_history and old_value is not None:
                    change_amount = new_cost - old_value
                    change_percent = (change_amount / old_value * 100) if old_value else None
                    self.cursor.execute(
                        """INSERT INTO cost_history
                           (spec_code, old_cost_price, new_cost_price, change_amount, change_percent, source, import_time)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (spec_code, old_value, new_cost, change_amount, change_percent, source, import_time),
                    )
                changed += 1
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return changed

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

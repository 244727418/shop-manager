# -*- coding: utf-8 -*-
"""
数据库与 RAG 层：SafeDatabaseManager。
负责 SQLite 连接、表结构、迁移、CRUD、知识库与向量检索。
"""
import os
import sys
import re
import json
import sqlite3
from datetime import datetime


class SafeDatabaseManager:
    """安全的数据库管理类，增加错误处理"""

    def __init__(self, db_name="shop_manager.db"):
        try:
            if getattr(sys, 'frozen', False):
                script_dir = os.path.dirname(sys.executable)
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(script_dir, db_name)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.init_db()
        except Exception as e:
            print(f"数据库初始化失败: {e}")
            raise

    def init_db(self):
        try:
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS stores 
                                (id INTEGER PRIMARY KEY, name TEXT, sort_order INTEGER, memo TEXT)''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                                (id INTEGER PRIMARY KEY, store_id INTEGER, name TEXT, 
                                url TEXT, image_path TEXT, sort_order INTEGER)''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS records 
                                (product_id INTEGER, year INTEGER, month INTEGER, day INTEGER, 
                                records_json TEXT, PRIMARY KEY(product_id, year, month, day))''')
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

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS cost_library 
                                (spec_code TEXT PRIMARY KEY, spec_name TEXT, cost_price REAL)''')

            self.cursor.execute("PRAGMA table_info(cost_library)")
            cost_columns = [col[1] for col in self.cursor.fetchall()]
            if 'spec_name' not in cost_columns:
                try:
                    self.cursor.execute("ALTER TABLE cost_library ADD COLUMN spec_name TEXT")
                    print("✅ 已添加spec_name字段到cost_library表")
                except Exception as e:
                    print(f"添加spec_name字段失败: {e}")

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS product_specs 
                                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                product_id INTEGER NOT NULL,
                                spec_name TEXT NOT NULL,
                                spec_code TEXT,
                                sale_price REAL,
                                weight_percent REAL,
                                is_locked INTEGER DEFAULT 0,
                                FOREIGN KEY (product_id) REFERENCES products (id))''')

            self.cursor.execute("PRAGMA table_info(product_specs)")
            spec_columns = [col[1] for col in self.cursor.fetchall()]
            if 'is_locked' not in spec_columns:
                try:
                    self.cursor.execute("ALTER TABLE product_specs ADD COLUMN is_locked INTEGER DEFAULT 0")
                    print("✅ 已添加is_locked字段到product_specs表")
                except Exception as e:
                    print(f"添加is_locked字段失败: {e}")

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

            self.cursor.execute('''CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_system INTEGER DEFAULT 0,
                embedding BLOB,
                created_at TEXT,
                updated_at TEXT)''')

            self.cursor.execute("PRAGMA table_info(knowledge_base)")
            kb_columns = [col[1] for col in self.cursor.fetchall()]
            if 'is_system' not in kb_columns:
                try:
                    self.cursor.execute("ALTER TABLE knowledge_base ADD COLUMN is_system INTEGER DEFAULT 0")
                    print("✅ 已添加is_system字段到knowledge_base表")
                except Exception as e:
                    print(f"添加is_system字段失败: {e}")

            if 'embedding' not in kb_columns:
                try:
                    self.cursor.execute("ALTER TABLE knowledge_base ADD COLUMN embedding BLOB")
                    print("✅ 已添加embedding字段到knowledge_base表")
                except Exception as e:
                    print(f"添加embedding字段失败: {e}")

            if 'sort_order' not in kb_columns:
                try:
                    self.cursor.execute("ALTER TABLE knowledge_base ADD COLUMN sort_order INTEGER DEFAULT 0")
                    print("✅ 已添加sort_order字段到knowledge_base表")
                except Exception as e:
                    print(f"添加sort_order字段失败: {e}")

            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_kb_file_name ON knowledge_base(file_name)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_kb_title ON knowledge_base(title)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_kb_file_path ON knowledge_base(file_path)")
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
                product_id INTEGER NOT NULL,
                spec_code TEXT NOT NULL,
                order_count INTEGER DEFAULT 1,
                import_time TEXT NOT NULL,
                order_date TEXT,
                actual_amount REAL DEFAULT 0,
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
                    self.cursor.execute("ALTER TABLE imported_orders ADD COLUMN product_id INTEGER")
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

        except Exception as e:
            print(f"数据库表创建失败：{e}")

    def safe_execute(self, query, params=()):
        try:
            self.cursor.execute(query, params)
            self.conn.commit()
            return self.cursor
        except Exception as e:
            print(f"数据库操作失败: {query}, 错误: {e}")
            return None

    def safe_fetchall(self, query, params=()):
        try:
            self.cursor.execute(query, params)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"数据库查询失败: {query}, 错误: {e}")
            return []

    def get_setting(self, key, default=None):
        try:
            res = self.safe_fetchall("SELECT value FROM settings WHERE key=?", (key,))
            return res[0][0] if res else default
        except Exception as e:
            print(f"获取设置失败: {e}")
            return default

    def set_setting(self, key, value):
        try:
            self.safe_execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        except Exception as e:
            print(f"保存设置失败: {e}")

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

    def parse_knowledge_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            knowledge_items = []
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                # 查找【标题】
                if line.startswith("【") and line.endswith("】") and len(line) > 2:
                    title = line[1:-1]  # 去掉【】
                    # 下一行是内容
                    i += 1
                    content_lines = []
                    while i < len(lines):
                        next_line = lines[i]
                        # 如果遇到下一个【标题】，停止
                        if next_line.strip().startswith("【") and next_line.strip().endswith("】"):
                            break
                        content_lines.append(next_line)
                        i += 1
                    content = ''.join(content_lines).strip()
                    if title and content:
                        knowledge_items.append({'title': title, 'content': content})
                else:
                    i += 1
            
            # 如果没有解析到新格式，尝试旧格式兼容
            if not knowledge_items:
                content = ''.join(lines)
                # 旧格式1: 【标题】内容（同一行）
                pattern1 = r'【([^】]+)】([^\n]*)'
                matches1 = re.findall(pattern1, content)
                for title, item_content in matches1:
                    title = title.strip()
                    item_content = item_content.strip()
                    if title and item_content:
                        knowledge_items.append({'title': title, 'content': item_content})
            
            return knowledge_items
        except Exception as e:
            print(f"解析知识库文件失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def import_knowledge_file(self, file_path, is_system=False, skip_embedding=False, check_duplicates=True):
        try:
            file_name = os.path.basename(file_path)
            knowledge_items = self.parse_knowledge_file(file_path)
            if not knowledge_items:
                return False, "未找到有效的知识条目，请检查文件格式（需使用【标题】格式）"
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 只有在不跳过时才初始化模型和计算embedding
            embedding = None
            if not skip_embedding:
                if not hasattr(self, 'rag_model') or self.rag_model is None:
                    self.init_rag_model()
            
            imported_count = 0
            updated_count = 0
            skipped_count = 0
            
            # 记录顺序
            for sort_idx, item in enumerate(knowledge_items):
                title = item['title'].strip()
                content = item['content'].strip()
                
                if not title or not content:
                    continue
                
                if not skip_embedding and self.rag_model:
                    text = f"{title}: {content}"
                    embedding = self.get_embedding(text)
                
                # 1. 检查同一文件中是否存在相同标题
                existing_same_file = self.safe_fetchall(
                    "SELECT id, content FROM knowledge_base WHERE file_path=? AND title=?",
                    (file_path, title)
                )
                
                if existing_same_file:
                    # 同一文件中存在，更新内容
                    existing_id = existing_same_file[0][0]
                    existing_content = existing_same_file[0][1]
                    if existing_content != content:
                        if embedding:
                            self.safe_execute(
                                "UPDATE knowledge_base SET content=?, embedding=?, updated_at=?, sort_order=? WHERE id=?",
                                (content, embedding, now, sort_idx, existing_id)
                            )
                        else:
                            self.safe_execute(
                                "UPDATE knowledge_base SET content=?, updated_at=?, sort_order=? WHERE id=?",
                                (content, now, sort_idx, existing_id)
                            )
                        updated_count += 1
                    else:
                        skipped_count += 1
                    continue
                
                # 2. 如果启用全局重复检测，检查其他文件是否已存在相同内容
                if check_duplicates:
                    # 检查全局标题+内容重复
                    existing_global = self.safe_fetchall(
                        "SELECT id, file_path, file_name FROM knowledge_base WHERE title=? AND content=?",
                        (title, content)
                    )
                    if existing_global:
                        # 全局已存在相同内容，跳过
                        skipped_count += 1
                        continue
                
                # 3. 插入新记录
                if embedding:
                    self.safe_execute(
                        "INSERT INTO knowledge_base (file_path, file_name, title, content, is_active, is_system, embedding, created_at, updated_at, sort_order) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
                        (file_path, file_name, title, content, 1 if is_system else 0, embedding, now, now, sort_idx)
                    )
                else:
                    self.safe_execute(
                        "INSERT INTO knowledge_base (file_path, file_name, title, content, is_active, is_system, created_at, updated_at, sort_order) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
                        (file_path, file_name, title, content, 1 if is_system else 0, now, now, sort_idx)
                    )
                imported_count += 1
            
            return True, f"导入完成: 新增 {imported_count} 条, 更新 {updated_count} 条, 跳过重复 {skipped_count} 条"
        except Exception as e:
            return False, f"导入知识库失败: {e}"

    def load_system_knowledge_base(self, script_dir):
        system_file = os.path.join(script_dir, "knowledge_base.txt")
        if os.path.exists(system_file):
            print(f"发现系统知识库文件: {system_file}")
            self.safe_execute("DELETE FROM knowledge_base WHERE is_system=1")
            self.conn.commit()
            print("已清除旧系统知识库，重新导入...")
            success, msg = self.import_knowledge_file(system_file, is_system=True)
            self.conn.commit()
            if success:
                print(f"系统知识库导入成功: {msg}")
            return success, msg
        return False, "未找到系统知识库文件"

    def get_all_knowledge_items(self):
        try:
            return self.safe_fetchall("SELECT id, file_path, file_name, title, content, is_active, is_system FROM knowledge_base ORDER BY file_name, sort_order, id")
        except Exception as e:
            print(f"获取知识库失败: {e}")
            return []

    def get_knowledge_items_by_file(self, file_name):
        try:
            return self.safe_fetchall(
                "SELECT id, file_path, file_name, title, content, is_active, is_system FROM knowledge_base WHERE file_name=? ORDER BY sort_order, id",
                (file_name,)
            )
        except Exception as e:
            print(f"按文件名获取知识库失败: {e}")
            return []

    def get_active_knowledge_items(self):
        try:
            rows = self.safe_fetchall("SELECT title, content FROM knowledge_base ORDER BY file_name, title")
            return [{'title': row[0], 'content': row[1]} for row in rows]
        except Exception as e:
            print(f"获取知识库失败: {e}")
            return []

    def get_knowledge_items_by_titles(self, titles):
        if not titles:
            return []
        try:
            placeholders = ','.join(['?'] * len(titles))
            rows = self.safe_fetchall(
                f"SELECT title, content FROM knowledge_base WHERE title IN ({placeholders})",
                titles
            )
            return [{'title': row[0], 'content': row[1]} for row in rows]
        except Exception as e:
            print(f"获取知识库失败: {e}")
            return []

    def toggle_knowledge_item(self, item_id, is_active):
        try:
            self.safe_execute("UPDATE knowledge_base SET is_active=? WHERE id=?", (1 if is_active else 0, item_id))
        except Exception as e:
            print(f"切换知识库状态失败: {e}")

    def delete_knowledge_item(self, item_id):
        try:
            self.safe_execute("DELETE FROM knowledge_base WHERE id=?", (item_id,))
        except Exception as e:
            print(f"删除知识库失败: {e}")

    def update_knowledge_content(self, item_id, content):
        try:
            self.safe_execute("UPDATE knowledge_base SET content=? WHERE id=?", (content, item_id))
            self.conn.commit()
        except Exception as e:
            print(f"更新知识库内容失败: {e}")

    def delete_knowledge_by_file(self, file_path):
        try:
            self.safe_execute("DELETE FROM knowledge_base WHERE file_path=?", (file_path,))
        except Exception as e:
            print(f"删除知识库文件失败: {e}")

    def get_unique_files(self):
        try:
            return self.safe_fetchall("SELECT DISTINCT file_path, file_name, is_system FROM (SELECT file_path, file_name, is_system FROM knowledge_base) ORDER BY is_system DESC, file_name")
        except Exception as e:
            print(f"获取知识库文件列表失败: {e}")
            return []

    def init_rag_model(self):
        if getattr(self, '_rag_model_initialized', False):
            return getattr(self, '_rag_model_loaded', False)
        
        self._rag_model_initialized = True
        self._rag_model_loaded = False
        self._rag_model_info = "未加载"
        
        # 检查模型缓存标记（避免重复加载）
        import os
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        cache_marker = os.path.join(base_dir, ".rag_model_loaded.marker")
        
        # 如果缓存标记存在，说明模型已加载，跳过
        if os.path.exists(cache_marker):
            self._rag_model_loaded = True
            self._rag_model_info = "SentenceTransformer (已缓存，跳过加载)"
            print("[INFO] RAG模型已缓存，跳过加载")
            return True
        
        possible_paths = [
            os.path.join(base_dir, "sentence-transformers", "paraphrase-multilingual-MiniLM-L12-v2"),
            os.path.join(base_dir, "minilm_model"),
        ]
        print(f"[DEBUG] Model search base dir: {base_dir}")
        print(f"[DEBUG] Model search paths: {possible_paths}")
        model_path = None
        for path in possible_paths:
            normalized = os.path.normpath(path)
            if os.path.exists(normalized) and os.path.isdir(normalized):
                model_path = normalized
                break
        try:
            from sentence_transformers import SentenceTransformer
            if model_path:
                print(f"[INFO] Loading model from local: {model_path}")
                self.rag_model = SentenceTransformer(model_path)
                self.rag_type = "sentence_transformers"
                self._rag_model_info = f"SentenceTransformer (本地模型: {model_path})"
                print("[OK] RAG model loaded successfully (SentenceTransformer - Local Model)")
                self._rag_model_loaded = True
                # 创建缓存标记
                try:
                    with open(cache_marker, 'w') as f:
                        f.write("model loaded")
                except:
                    pass
                return True
            raise Exception("Local model not found")
        except Exception as e1:
            print(f"[WARN] SentenceTransformer load failed: {e1}")
            print("[INFO] Falling back to TF-IDF vectorizer")
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                self.rag_model = TfidfVectorizer(max_features=384, ngram_range=(1, 2))
                self.rag_type = "tfidf"
                self._rag_model_info = "TF-IDF (sklearn)"
                self.rag_embeddings = {}
                self.rag_item_ids = []
                print("[OK] RAG model loaded successfully (TF-IDF)")
                self._rag_model_loaded = True
                return True
            except Exception as e2:
                print(f"❌ TF-IDF加载失败: {e2}")
                print("💡 解决方案: pip install scikit-learn")
                self.rag_model = None
                self._rag_model_info = "加载失败"
                self._rag_model_loaded = False
                return False

    def get_rag_model_info(self):
        if hasattr(self, '_rag_model_info'):
            return self._rag_model_info
        return "未加载"

    def get_embedding(self, text):
        if not hasattr(self, 'rag_model') or self.rag_model is None:
            self.init_rag_model()
        if self.rag_model is None:
            return None
        try:
            if self.rag_type == "sentence_transformers":
                embedding = self.rag_model.encode(text, convert_to_numpy=True)
                return embedding.tobytes()
            emb = self.rag_model.fit_transform([text]).toarray()[0]
            return emb.tobytes()
        except Exception as e:
            print(f"向量化失败: {e}")
            return None

    def compute_similarity(self, emb1_bytes, emb2_bytes):
        import numpy as np
        emb1 = np.frombuffer(emb1_bytes, dtype=np.float32)
        emb2 = np.frombuffer(emb2_bytes, dtype=np.float32)
        if len(emb1) != len(emb2):
            return 0
        emb1 = emb1 / (np.linalg.norm(emb1) + 1e-8)
        emb2 = emb2 / (np.linalg.norm(emb2) + 1e-8)
        return np.dot(emb1, emb2)

    def update_knowledge_embeddings(self):
        if not hasattr(self, 'rag_model') or self.rag_model is None:
            self.init_rag_model()
        if self.rag_model is None:
            return False, "RAG模型未初始化"
        try:
            items = self.safe_fetchall("SELECT id, title, content FROM knowledge_base")
            updated = 0
            for item_id, title, content in items:
                text = f"{title}: {content}"
                emb = self.get_embedding(text)
                if emb:
                    self.safe_execute("UPDATE knowledge_base SET embedding=? WHERE id=?", (emb, item_id))
                    updated += 1
            return True, f"已更新 {updated} 条知识的向量化"
        except Exception as e:
            return False, f"向量化失败: {e}"

    def rag_retrieve(self, query, top_k=3):
        if not hasattr(self, 'rag_model') or self.rag_model is None:
            self.init_rag_model()
        if self.rag_model is None:
            return []
        try:
            query_emb = self.get_embedding(query)
            if query_emb is None:
                return []
            items = self.safe_fetchall(
                "SELECT id, title, content, embedding FROM knowledge_base WHERE embedding IS NOT NULL"
            )
            results = []
            for item_id, title, content, emb_bytes in items:
                if emb_bytes:
                    similarity = self.compute_similarity(query_emb, emb_bytes)
                    results.append({'id': item_id, 'title': title, 'content': content, 'similarity': similarity})
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:top_k]
        except Exception as e:
            print(f"RAG检索失败: {e}")
            return []

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
        'profit': {'name': '盈利状态', 'icon': None, 'color_profit': '#27ae60', 'color_loss': '#e74c3c'},
    }

    TAG_STATUS_CODES = {0: '未设置', 1: '盈利', -1: '亏损'}

    def get_product_tags(self, product_id):
        try:
            res = self.safe_fetchall(
                "SELECT is_limited_time, is_marketing, profit_status FROM products WHERE id=?",
                (product_id,)
            )
            if res and res[0]:
                return {
                    'coupon': res[0][0] > 0,
                    'new_customer': res[0][0] > 0,
                    'limited_time': bool(res[0][0]),
                    'marketing': bool(res[0][1]),
                    'profit_status': res[0][2],
                }
            return {'coupon': False, 'new_customer': False, 'limited_time': False, 'marketing': False, 'profit_status': 0}
        except Exception as e:
            print(f"获取商品标签失败: {e}")
            return {'coupon': False, 'new_customer': False, 'limited_time': False, 'marketing': False, 'profit_status': 0}

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
                "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                (product_id,)
            )
            if not specs:
                return 0
            prod_res = self.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
                (product_id,)
            )
            coupon = prod_res[0][0] or 0 if prod_res else 0
            new_customer = prod_res[0][1] or 0 if prod_res else 0
            max_discount = max(coupon, new_customer)
            total_weight = 0
            total_profit = 0
            total_final_price = 0
            for spec_code, sale_price, weight in specs:
                if not sale_price or sale_price <= 0:
                    continue
                weight = weight or 0
                cost_res = self.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
                cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
                final_price = sale_price - max_discount
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
            if store_id:
                conditions.append("store_id = ?")
                params.append(store_id)
            if tag_filters.get('limited_time'):
                conditions.append("is_limited_time = 1")
            if tag_filters.get('marketing'):
                conditions.append("is_marketing = 1")
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

# -*- coding: utf-8 -*-
"""
云同步模块：支持腾讯云COS云同步功能
提供账号管理、数据上传下载、账号切换等功能
"""
import os
import sys
import json
import base64
import hashlib
from datetime import datetime

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QLineEdit, QComboBox, QMessageBox, QTextEdit, QProgressBar,
        QGroupBox, QCheckBox, QGridLayout, QListWidget, QListWidgetItem,
        QAbstractItemView, QInputDialog, QDialogButtonBox
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt5.QtGui import QFont, QIcon
except ImportError:
    print("PyQt5 未安装")
    raise

try:
    from manager.db import SafeDatabaseManager
except ImportError:
    from db import SafeDatabaseManager


class CloudSyncManager:
    """云同步管理器 - 负责账号管理和数据同步"""

    def __init__(self, db_manager):
        self.db = db_manager
        self.accounts_file = self._get_accounts_file_path()
        self.current_account = None
        self.cos_client = None
        self._load_accounts()

    @staticmethod
    def _safe_serialize_value(value):
        """安全地序列化值，处理二进制数据"""
        if value is None:
            return None
        if isinstance(value, bytes):
            try:
                return value.decode('utf-8')
            except UnicodeDecodeError:
                return base64.b64encode(value).decode('utf-8')
        if isinstance(value, (int, float, str, bool)):
            return value
        return str(value)

    @staticmethod
    def _safe_deserialize_value(value, column_name):
        """安全地反序列化值，将字符串转回bytes（用于图片等二进制字段）"""
        if value is None:
            return None
        # 图片相关字段需要转回bytes
        if column_name in ('image_data', 'spec_image_data', 'image', 'thumbnail', 'icon'):
            if isinstance(value, str):
                try:
                    return base64.b64decode(value)
                except Exception:
                    return value
        return value

    @staticmethod
    def _convert_row_to_dict(columns, row):
        """将数据库行转换为字典，安全处理所有类型"""
        result = {}
        for col, val in zip(columns, row):
            result[col] = CloudSyncManager._safe_serialize_value(val)
        return result

    @staticmethod
    def _convert_dict_for_db(data_dict, columns):
        """将字典转换为数据库值，处理二进制字段"""
        result = []
        for col in columns:
            val = data_dict.get(col)
            result.append(CloudSyncManager._safe_deserialize_value(val, col))
        return result

    def _get_base_dir(self):
        """获取基础目录"""
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return base

    def _get_accounts_file_path(self):
        """获取账号配置文件路径"""
        base_dir = self._get_base_dir()
        return os.path.join(base_dir, "cloud_accounts.json")

    def _load_accounts(self):
        """加载账号列表"""
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.accounts = data.get('accounts', [])
                    self.current_account_id = data.get('current_account')
                    self.active_data_account_id = data.get('active_data_account_id')
                    if self.current_account_id:
                        self.current_account = self._find_account_by_id(self.current_account_id)
            except Exception as e:
                print(f"加载账号文件失败: {e}")
                self.accounts = []
                self.current_account_id = None
                self.active_data_account_id = None
                self.current_account = None
        else:
            self.accounts = []
            self.current_account_id = None
            self.active_data_account_id = None
            self.current_account = None

    def _save_accounts(self):
        """保存账号列表到文件"""
        try:
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'accounts': self.accounts,
                    'current_account': self.current_account_id,
                    'active_data_account_id': self.active_data_account_id
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"淇濆瓨璐﹀彿鏂囦欢澶辫触: {e}")
        return

    def _find_account_by_id(self, account_id):
        """根据ID查找账号"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                return acc
        return None

    def _generate_account_id(self):
        """生成唯一账号ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_str = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:4]
        return f"acc_{timestamp}_{random_str}"

    def add_account(self, name, secret_id, secret_key, bucket, region, folder=""):
        """添加新账号"""
        account_id = self._generate_account_id()
        folder_name = folder.strip() if folder.strip() else name.strip()
        local_folder = os.path.join(self._get_base_dir(), folder_name)
        account = {
            'id': account_id,
            'name': name.strip(),
            'secret_id': secret_id.strip(),
            'secret_key': secret_key.strip(),
            'bucket': bucket.strip(),
            'region': region.strip(),
            'folder': folder_name,
            'local_backup_path': local_folder,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'last_upload_time': None,
            'last_download_time': None
        }
        self.accounts.append(account)
        self._save_accounts()
        return account

    def get_last_used_credentials(self):
        """从cloud_accounts.json获取最近使用过的凭证"""
        accounts = self.get_all_accounts()
        if accounts:
            last_account = accounts[-1]
            return {
                'secret_id': last_account.get('secret_id', ''),
                'secret_key': last_account.get('secret_key', '')
            }
        return None

    def set_local_backup_path(self, account_id, local_path):
        """设置账号的本地备份路径"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                acc['local_backup_path'] = local_path if local_path else os.path.join(self._get_base_dir(), acc['folder'])
                self._save_accounts()
                if self.current_account_id == account_id:
                    self.current_account = acc
                return acc
        return None

    def update_account(self, account_id, **kwargs):
        """更新账号信息"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                for key, value in kwargs.items():
                    if key in ['name', 'secret_id', 'secret_key', 'bucket', 'region', 'folder']:
                        acc[key] = value
                self._save_accounts()
                if self.current_account_id == account_id:
                    self.current_account = acc
                return acc
        return None

    def delete_account(self, account_id):
        """删除账号"""
        self.accounts = [acc for acc in self.accounts if acc.get('id') != account_id]
        if self.current_account_id == account_id:
            self.current_account_id = None
            self.current_account = None
        self._save_accounts()

    def switch_account(self, account_id):
        """切换当前账号"""
        account = self._find_account_by_id(account_id)
        if account:
            self.current_account_id = account_id
            self.current_account = account
            self._save_accounts()
            return True
        return False

    def get_current_account(self):
        """获取当前账号"""
        return self.current_account

    def get_active_data_account(self):
        """获取当前本地表格数据归属账号"""
        if not getattr(self, 'active_data_account_id', None):
            return None
        return self._find_account_by_id(self.active_data_account_id)

    def set_active_data_account(self, account_id):
        """设置当前本地表格数据归属账号"""
        account = self._find_account_by_id(account_id)
        if not account:
            return False
        self.active_data_account_id = account_id
        self._save_accounts()
        return True

    def get_all_accounts(self):
        """获取所有账号"""
        return self.accounts

    def update_last_upload_time(self, account_id):
        """更新最后上传时间"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                acc['last_upload_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_accounts()
                if self.current_account_id == account_id:
                    self.current_account = acc
                return

    def update_last_download_time(self, account_id):
        """更新最后下载时间"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                acc['last_download_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_accounts()
                if self.current_account_id == account_id:
                    self.current_account = acc
                return

    def save_local_backup(self, account_id, data=None):
        """保存本地备份 - 直接复制db文件"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                try:
                    os.makedirs(backup_path, exist_ok=True)
                    backup_file = os.path.join(backup_path, "backup.db")
                    import shutil
                    shutil.copy2(self.db.db_path, backup_file)
                    return True, backup_file
                except Exception as e:
                    return False, str(e)
        return False, "账号不存在"

    def save_local_backup_before_download(self, account_id):
        """下载覆盖本地前，备份当前本地DB。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                try:
                    os.makedirs(os.path.join(backup_path, "local_backup_before_download"), exist_ok=True)
                    backup_file = os.path.join(backup_path, "local_backup_before_download", "backup.db")
                    import shutil
                    shutil.copy2(self.db.db_path, backup_file)
                    return True, backup_file
                except Exception as e:
                    return False, str(e)
        return False, "账号不存在"

    def _get_timestamped_backup_file(self, backup_dir):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        backup_file = os.path.join(backup_dir, f"backup_{timestamp}.db")
        if not os.path.exists(backup_file):
            return backup_file

        index = 1
        while True:
            backup_file = os.path.join(backup_dir, f"backup_{timestamp}_{index:02d}.db")
            if not os.path.exists(backup_file):
                return backup_file
            index += 1

    def _backup_sort_key(self, file_path):
        name = os.path.basename(file_path)
        try:
            stem = os.path.splitext(name)[0]
            parts = stem.split("_")
            if len(parts) >= 3 and parts[0] == "backup":
                created_at = datetime.strptime(f"{parts[1]}_{parts[2]}", "%Y%m%d_%H%M")
                suffix = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 0
                return (created_at.timestamp(), suffix, os.path.getmtime(file_path))
        except Exception:
            pass
        modified_at = os.path.getmtime(file_path)
        return (modified_at, 0, modified_at)

    def _rotate_timestamped_backups(self, backup_dir, max_backups=5):
        backup_files = [
            os.path.join(backup_dir, name)
            for name in os.listdir(backup_dir)
            if name.lower().endswith(".db")
        ]
        backup_files.sort(key=self._backup_sort_key, reverse=True)
        for old_file in backup_files[max_backups:]:
            try:
                os.remove(old_file)
            except Exception:
                pass

    def save_local_backup_before_upload(self, account_id, max_backups=5):
        """上传覆盖云端前，按时间备份当前本地DB，最多保留最近几份。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                try:
                    backup_dir = os.path.join(backup_path, "local_backup_before_upload")
                    os.makedirs(backup_dir, exist_ok=True)
                    try:
                        self.db.conn.commit()
                    except Exception:
                        pass
                    backup_file = self._get_timestamped_backup_file(backup_dir)
                    import shutil
                    shutil.copy2(self.db.db_path, backup_file)
                    self._rotate_timestamped_backups(backup_dir, max_backups=max_backups)
                    return True, backup_file
                except Exception as e:
                    return False, str(e)
        return False, "账号不存在"

    def save_local_profile(self, account_id):
        """保存当前主库为该账号的本地应用档案。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                try:
                    profile_dir = os.path.join(backup_path, "local_current")
                    os.makedirs(profile_dir, exist_ok=True)
                    profile_file = os.path.join(profile_dir, "backup.db")
                    try:
                        self.db.conn.commit()
                    except Exception:
                        pass
                    import shutil
                    shutil.copy2(self.db.db_path, profile_file)
                    return True, profile_file
                except Exception as e:
                    return False, str(e)
        return False, "账号不存在"

    def load_local_profile(self, account_id):
        """返回该账号本地应用档案路径。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                profile_file = os.path.join(backup_path, "local_current", "backup.db")
                if os.path.exists(profile_file):
                    return True, profile_file
                legacy_file = os.path.join(backup_path, "backup.db")
                if os.path.exists(legacy_file):
                    return True, legacy_file
                return False, "该账号暂无本地数据"
        return False, "账号不存在"

    def has_local_profile(self, account_id):
        """判断该账号是否已有本地应用档案。"""
        ok, _ = self.load_local_profile(account_id)
        return ok

    def ensure_local_profile_normalized(self, account_id, profile_path):
        """将旧本地档案迁移为标准 local_current/backup.db。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                standard_file = os.path.join(backup_path, "local_current", "backup.db")
                if os.path.abspath(profile_path) == os.path.abspath(standard_file):
                    return True, standard_file
                try:
                    os.makedirs(os.path.dirname(standard_file), exist_ok=True)
                    import shutil
                    shutil.copy2(profile_path, standard_file)
                    return True, standard_file
                except Exception as e:
                    return False, str(e)
        return False, "账号不存在"

    def get_accounts_with_local_profiles(self):
        """获取已有本地数据的账号列表。"""
        result = []
        for acc in self.accounts:
            ok, path = self.load_local_profile(acc.get('id'))
            if ok:
                result.append((acc, path))
        return result

    def save_cloud_backup_before_upload(self, account_id, cloud_data):
        """上传覆盖云端前，备份当前云端JSON数据。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                try:
                    backup_dir = os.path.join(backup_path, "cloud_backup_before_upload")
                    os.makedirs(backup_dir, exist_ok=True)
                    backup_file = os.path.join(backup_dir, "data.json")
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        json.dump(cloud_data, f, ensure_ascii=False, indent=2)
                    return True, backup_file
                except Exception as e:
                    return False, str(e)
        return False, "账号不存在"

    def load_local_backup(self, account_id):
        """加载本地备份 - 返回db文件路径"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                backup_file = os.path.join(backup_path, "backup.db")
                if os.path.exists(backup_file):
                    return True, backup_file
                else:
                    return False, "本地备份文件不存在"
        return False, "账号不存在"

    def export_data_to_json(self):
        """导出数据库数据为JSON（动态获取所有表）"""
        try:
            data = {
                'version': '1.0',
                'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            self.db.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = self.db.cursor.fetchall()

            for (table_name,) in tables:
                if table_name in ('sqlite_sequence', 'sqlite_stat1', 'sqlite_stat2', 'sqlite_stat3', 'sqlite_stat4'):
                    continue

                self.db.cursor.execute(f"SELECT * FROM {table_name}")
                rows = self.db.cursor.fetchall()
                columns = [desc[0] for desc in self.db.cursor.description]

                table_data = []
                for row in rows:
                    row_dict = {}
                    for col, val in zip(columns, row):
                        row_dict[col] = self._safe_serialize_value(val)
                    table_data.append(row_dict)

                data[table_name] = table_data

            return data
        except Exception as e:
            print(f"导出数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _quote_identifier(name):
        return '"' + str(name).replace('"', '""') + '"'

    def _get_existing_table_columns(self, table_name):
        self.db.cursor.execute(f"PRAGMA table_info({self._quote_identifier(table_name)})")
        return [row[1] for row in self.db.cursor.fetchall()]

    def _insert_compatible_row(self, table_name, row, table_columns, replace=True):
        if not isinstance(row, dict):
            return
        columns = [col for col in row.keys() if col in table_columns]
        if not columns:
            return
        placeholders = ','.join(['?'] * len(columns))
        quoted_table = self._quote_identifier(table_name)
        quoted_columns = ','.join(self._quote_identifier(col) for col in columns)
        verb = "INSERT OR REPLACE" if replace else "INSERT"
        values = [self._safe_deserialize_value(row.get(col), col) for col in columns]
        self.db.cursor.execute(
            f"{verb} INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})",
            values,
        )

    def _delete_table_if_exists(self, table_name, table_columns_cache):
        columns = self._get_existing_table_columns(table_name)
        if not columns:
            return False
        table_columns_cache[table_name] = columns
        self.db.cursor.execute(f"DELETE FROM {self._quote_identifier(table_name)}")
        return True

    def import_data_from_json(self, data):
        """从JSON导入数据到数据库（整体覆盖，先清空再导入）"""
        try:
            if not data or 'version' not in data:
                return False

            if data.get('settings') and isinstance(data['settings'], list):
                settings_dict = {}
                for item in data['settings']:
                    if isinstance(item, dict) and 'key' in item:
                        settings_dict[item['key']] = item['value']
                data['settings'] = settings_dict

            self.db.safe_execute("DELETE FROM stores")
            self.db.safe_execute("DELETE FROM products")
            self.db.safe_execute("DELETE FROM product_specs")
            self.db.safe_execute("DELETE FROM cost_library")
            self.db.safe_execute("DELETE FROM imported_orders")
            self.db.safe_execute("DELETE FROM import_history")
            self.db.safe_execute("DELETE FROM records")
            self.db.safe_execute("DELETE FROM store_records")
            self.db.safe_execute("DELETE FROM daily_records")
            self.db.safe_execute("DELETE FROM profit_records")
            self.db.safe_execute("DELETE FROM historical_data")
            self.db.safe_execute("DELETE FROM manual_margin_data")
            self.db.safe_execute("DELETE FROM store_temp_images")
            self.db.safe_execute("DELETE FROM promotion_daily_data")
            self.db.safe_execute("DELETE FROM settings")

            if data.get('stores'):
                for store in data['stores']:
                    store_id = store.get('id')
                    columns = [col for col in store.keys() if col != 'id']
                    if store_id is not None and columns:
                        cols_with_id = ['id'] + columns
                        vals = [store_id] + [self._safe_deserialize_value(store[col], col) for col in columns]
                        placeholders = ','.join(['?'] * len(cols_with_id))
                        self.db.safe_execute(f"INSERT INTO stores ({','.join(cols_with_id)}) VALUES ({placeholders})", vals)

            if data.get('products'):
                for product in data['products']:
                    product_id = product.get('id')
                    columns = [col for col in product.keys() if col != 'id']
                    if product_id is not None and columns:
                        cols_with_id = ['id'] + columns
                        vals = [product_id] + [self._safe_deserialize_value(product[col], col) for col in columns]
                        placeholders = ','.join(['?'] * len(cols_with_id))
                        self.db.safe_execute(f"INSERT INTO products ({','.join(cols_with_id)}) VALUES ({placeholders})", vals)

            if data.get('product_specs'):
                for spec in data['product_specs']:
                    spec_id = spec.get('id')
                    columns = [col for col in spec.keys() if col != 'id']
                    if spec_id is not None and columns:
                        cols_with_id = ['id'] + columns
                        vals = [spec_id] + [self._safe_deserialize_value(spec[col], col) for col in columns]
                        placeholders = ','.join(['?'] * len(cols_with_id))
                        self.db.safe_execute(f"INSERT INTO product_specs ({','.join(cols_with_id)}) VALUES ({placeholders})", vals)

            if data.get('cost_library'):
                for item in data['cost_library']:
                    columns = [col for col in item.keys() if col]
                    if columns:
                        placeholders = ','.join(['?'] * len(columns))
                        vals = [self._safe_deserialize_value(item.get(col), col) for col in columns]
                        self.db.safe_execute(
                            f"INSERT OR REPLACE INTO cost_library ({','.join(columns)}) VALUES ({placeholders})",
                            vals,
                        )

            if data.get('imported_orders'):
                for order in data['imported_orders']:
                    self.db.safe_execute(
                        """INSERT OR REPLACE INTO imported_orders
                        (store_id, product_id, spec_code, order_count, import_time, order_date, actual_amount, refund_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (order.get('store_id'), order.get('product_id'), order.get('spec_code'),
                         order.get('order_count', 0), order.get('import_time'), order.get('order_date'),
                         order.get('actual_amount', 0), order.get('refund_count', 0))
                    )

            if data.get('import_history'):
                for hist in data['import_history']:
                    self.db.safe_execute(
                        """INSERT OR REPLACE INTO import_history
                        (store_id, import_time, file_name, total_products, total_specs, total_orders, total_amount, snapshot_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (hist.get('store_id'), hist.get('import_time'), hist.get('file_name'),
                         hist.get('total_products', 0), hist.get('total_specs', 0), hist.get('total_orders', 0),
                         hist.get('total_amount', 0), hist.get('snapshot_data'))
                    )

            if data.get('records'):
                for record in data['records']:
                    self.db.safe_execute(
                        """INSERT OR REPLACE INTO records
                        (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)""",
                        (record.get('product_id'), record.get('year'), record.get('month'),
                         record.get('day'), record.get('records_json'))
                    )

            if data.get('store_records'):
                for sr in data['store_records']:
                    self.db.safe_execute(
                        """INSERT OR REPLACE INTO store_records
                        (store_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)""",
                        (sr.get('store_id'), sr.get('year'), sr.get('month'),
                         sr.get('day'), sr.get('records_json'))
                    )

            if data.get('daily_records'):
                for dr in data['daily_records']:
                    self.db.safe_execute(
                        """INSERT OR REPLACE INTO daily_records
                        (store_id, record_date, category, special_info, memo) VALUES (?, ?, ?, ?, ?)""",
                        (dr.get('store_id'), dr.get('record_date'), dr.get('category'),
                         dr.get('special_info'), dr.get('memo'))
                    )

            if data.get('profit_records'):
                for pr in data['profit_records']:
                    columns = [col for col in pr.keys() if col != 'id']
                    placeholders = ','.join(['?'] * (len(columns) + 1))
                    cols_with_id = ['id'] + columns
                    vals = [pr.get('id')] + [pr.get(col) for col in columns]
                    self.db.safe_execute(
                        f"INSERT OR REPLACE INTO profit_records ({','.join(cols_with_id)}) VALUES ({placeholders})",
                        vals
                    )

            if data.get('promotion_daily_data'):
                for promo in data['promotion_daily_data']:
                    columns = [col for col in promo.keys() if col != 'id']
                    placeholders = ','.join(['?'] * (len(columns) + 1))
                    cols_with_id = ['id'] + columns
                    vals = [promo.get('id')] + [promo.get(col) for col in columns]
                    self.db.safe_execute(
                        f"INSERT OR REPLACE INTO promotion_daily_data ({','.join(cols_with_id)}) VALUES ({placeholders})",
                        vals
                    )

            if data.get('historical_data'):
                for h in data['historical_data']:
                    columns = [col for col in h.keys() if col != 'id']
                    placeholders = ','.join(['?'] * (len(columns) + 1))
                    cols_with_id = ['id'] + columns
                    vals = [h.get('id')] + [h.get(col) for col in columns]
                    self.db.safe_execute(
                        f"INSERT OR REPLACE INTO historical_data ({','.join(cols_with_id)}) VALUES ({placeholders})",
                        vals
                    )

            if data.get('manual_margin_data'):
                for m in data['manual_margin_data']:
                    columns = [col for col in m.keys() if col != 'id']
                    placeholders = ','.join(['?'] * (len(columns) + 1))
                    cols_with_id = ['id'] + columns
                    vals = [m.get('id')] + [self._safe_deserialize_value(m.get(col), col) for col in columns]
                    self.db.safe_execute(
                        f"INSERT OR REPLACE INTO manual_margin_data ({','.join(cols_with_id)}) VALUES ({placeholders})",
                        vals
                    )

            if data.get('store_temp_images'):
                for img in data['store_temp_images']:
                    columns = [col for col in img.keys() if col != 'id']
                    placeholders = ','.join(['?'] * (len(columns) + 1))
                    cols_with_id = ['id'] + columns
                    vals = [img.get('id')] + [self._safe_deserialize_value(img.get(col), col) for col in columns]
                    self.db.safe_execute(
                        f"INSERT OR REPLACE INTO store_temp_images ({','.join(cols_with_id)}) VALUES ({placeholders})",
                        vals
                    )

            if data.get('settings'):
                for key, value in data['settings'].items():
                    self.db.safe_execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, value)
                    )

            if data.get('ai_prompts'):
                for prompt in data['ai_prompts']:
                    prompt_id = prompt.get('id')
                    columns = [col for col in prompt.keys() if col != 'id']
                    if prompt_id is not None and columns:
                        cols_with_id = ['id'] + columns
                        vals = [prompt_id] + [prompt.get(col) for col in columns]
                        placeholders = ','.join(['?'] * len(cols_with_id))
                        self.db.safe_execute(f"INSERT OR REPLACE INTO ai_prompts ({','.join(cols_with_id)}) VALUES ({placeholders})", vals)

            if data.get('ai_common_prompts'):
                for prompt in data['ai_common_prompts']:
                    prompt_id = prompt.get('id')
                    columns = [col for col in prompt.keys() if col != 'id']
                    if prompt_id is not None and columns:
                        cols_with_id = ['id'] + columns
                        vals = [prompt_id] + [prompt.get(col) for col in columns]
                        placeholders = ','.join(['?'] * len(cols_with_id))
                        self.db.safe_execute(f"INSERT OR REPLACE INTO ai_common_prompts ({','.join(cols_with_id)}) VALUES ({placeholders})", vals)

            if data.get('store_prompts'):
                for prompt in data['store_prompts']:
                    prompt_id = prompt.get('id')
                    columns = [col for col in prompt.keys() if col != 'id']
                    if prompt_id is not None and columns:
                        cols_with_id = ['id'] + columns
                        vals = [prompt_id] + [prompt.get(col) for col in columns]
                        placeholders = ','.join(['?'] * len(cols_with_id))
                        self.db.safe_execute(f"INSERT OR REPLACE INTO store_prompts ({','.join(cols_with_id)}) VALUES ({placeholders})", vals)

            if data.get('knowledge_base'):
                for kb in data['knowledge_base']:
                    kb_id = kb.get('id')
                    columns = [col for col in kb.keys() if col != 'id']
                    if kb_id is not None and columns:
                        cols_with_id = ['id'] + columns
                        vals = [kb_id] + [kb.get(col) for col in columns]
                        placeholders = ','.join(['?'] * len(cols_with_id))
                        self.db.safe_execute(f"INSERT OR REPLACE INTO knowledge_base ({','.join(cols_with_id)}) VALUES ({placeholders})", vals)

            self.db.update_all_product_category_labels()
            self.db.conn.commit()
            return True
        except Exception as e:
            print(f"导入数据失败: {e}")
            import traceback
            traceback.print_exc()
            return False


    def import_data_from_json(self, data):
        """从JSON导入数据：事务覆盖，并兼容本地缺失的新字段。"""
        self.last_import_error = ""
        current_table = ""
        try:
            if not data or 'version' not in data:
                self.last_import_error = "云端数据格式无效"
                return False

            if data.get('settings') and isinstance(data['settings'], list):
                settings_dict = {}
                for item in data['settings']:
                    if isinstance(item, dict) and 'key' in item:
                        settings_dict[item['key']] = item['value']
                data['settings'] = settings_dict

            table_order = [
                'stores', 'products', 'product_specs', 'cost_categories',
                'cost_library', 'cost_history', 'imported_orders', 'import_history',
                'records', 'product_image_history', 'store_records', 'daily_records', 'profit_records',
                'promotion_daily_data', 'historical_data', 'manual_margin_data', 'store_temp_images',
                'daily_tasks', 'task_reminders', 'settings', 'ai_prompts', 'ai_common_prompts', 'store_prompts',
                'knowledge_base', 'link_combinations',
            ]
            delete_order = [
                'imported_orders', 'import_history', 'records', 'product_image_history', 'store_records',
                'daily_records', 'profit_records', 'promotion_daily_data', 'historical_data',
                'manual_margin_data', 'store_temp_images', 'daily_tasks', 'task_reminders', 'product_specs',
                'products', 'stores', 'cost_history', 'cost_library',
                'cost_categories', 'settings', 'ai_prompts', 'ai_common_prompts',
                'store_prompts', 'knowledge_base', 'link_combinations',
            ]

            table_columns_cache = {}
            self.db.conn.execute("BEGIN")

            for table_name in delete_order:
                current_table = table_name
                self._delete_table_if_exists(table_name, table_columns_cache)

            for table_name in table_order:
                current_table = table_name
                if table_name not in table_columns_cache:
                    columns = self._get_existing_table_columns(table_name)
                    if not columns:
                        continue
                    table_columns_cache[table_name] = columns
                columns = table_columns_cache[table_name]

                if table_name == 'settings' and isinstance(data.get('settings'), dict):
                    for key, value in data['settings'].items():
                        self._insert_compatible_row(table_name, {'key': key, 'value': value}, columns)
                    continue

                rows = data.get(table_name)
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    self._insert_compatible_row(table_name, row, columns)

            self.db.conn.commit()

            try:
                self.db.update_all_product_category_labels()
            except Exception as e:
                print(f"更新商品类型标签失败: {e}")
            return True
        except Exception as e:
            try:
                self.db.conn.rollback()
            except Exception:
                pass
            self.last_import_error = f"{current_table or '未知表'} 导入失败：{e}"
            print(f"瀵煎叆鏁版嵁澶辫触: {self.last_import_error}")
            import traceback
            traceback.print_exc()
            return False


class TencentCOSUploader:
    """腾讯云COS上传下载器"""

    def __init__(self, secret_id, secret_key, bucket, region):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region
        self.cos_client = None
        self._init_client()

    def _init_client(self):
        """初始化COS客户端"""
        try:
            from qcloud_cos import CosConfig, CosS3Client
            config = CosConfig(
                Region=self.region,
                SecretId=self.secret_id,
                SecretKey=self.secret_key,
                Token=None,
                Scheme='https'
            )
            self.cos_client = CosS3Client(config)
        except ImportError:
            print("腾讯云COS SDK未安装，请运行: pip install cos-python-sdk-v5")
            self.cos_client = None

    def _get_cos_path(self, folder, filename):
        """获取COS上的文件路径"""
        if folder:
            return f"{folder}/{filename}"
        return filename

    def upload_json(self, data, folder, filename="data.json", progress_callback=None):
        """上传JSON数据到COS"""
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            json_bytes = json_str.encode('utf-8')

            if self.cos_client:
                cos_path = self._get_cos_path(folder, filename)
                self.cos_client.put_object(
                    Bucket=self.bucket,
                    Body=json_bytes,
                    Key=cos_path,
                    ContentLength=str(len(json_bytes))
                )
                return True, cos_path
            else:
                return False, "COS客户端未初始化，请安装SDK: pip install cos-python-sdk-v5"

        except Exception as e:
            return False, str(e)

    def download_json(self, folder, filename="data.json", progress_callback=None):
        """从COS下载JSON数据"""
        try:
            if self.cos_client:
                cos_path = self._get_cos_path(folder, filename)
                response = self.cos_client.get_object(
                    Bucket=self.bucket,
                    Key=cos_path
                )
                json_str = response['Body'].get_raw_stream().read().decode('utf-8')
                return True, json.loads(json_str)
            else:
                return False, "COS客户端未初始化，请安装SDK: pip install cos-python-sdk-v5"

        except Exception as e:
            error_str = str(e)
            if "NoSuchKey" in error_str or "does not exist" in error_str or "NoSuch" in error_str:
                return False, "云端没有数据，请先上传"
            return False, error_str


class CloudSyncDialog(QDialog):
    """云同步登录对话框"""

    MESSAGEBOX_STYLE = """
        QMessageBox {
            background-color: #ffffff;
        }
        QMessageBox QLabel {
            color: #1a5f2a;
            font-size: 14px;
            font-weight: bold;
            background-color: #d4edda;
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #28a745;
        }
        QMessageBox QPushButton {
            min-width: 90px;
            padding: 8px 20px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 13px;
            border: none;
        }
        QMessageBox QPushButton[text="OK"] {
            background-color: #28a745;
            color: #ffffff;
        }
        QMessageBox QPushButton[text="OK"]:hover {
            background-color: #218838;
        }
        QMessageBox QPushButton[text="Cancel"] {
            background-color: #6c757d;
            color: #ffffff;
        }
        QMessageBox QPushButton[text="Cancel"]:hover {
            background-color: #5a6268;
        }
        QMessageBox QPushButton[text="Yes"] {
            background-color: #28a745;
            color: #ffffff;
        }
        QMessageBox QPushButton[text="Yes"]:hover {
            background-color: #218838;
        }
        QMessageBox QPushButton[text="No"] {
            background-color: #dc3545;
            color: #ffffff;
        }
        QMessageBox QPushButton[text="No"]:hover {
            background-color: #c82333;
        }
    """

    def __init__(self, db_manager, cloud_manager=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.cloud_manager = cloud_manager if cloud_manager else CloudSyncManager(db_manager)
        self.parent_window = parent
        self.setWindowTitle("☁️ 云同步 - 账号管理")
        self.resize(700, 500)
        self.setStyleSheet("background-color: #f5f5f5;")
        self.init_ui()
        self.load_accounts_to_list()

    def _show_message_box(self, icon, title, text, buttons=QMessageBox.Ok):
        """显示自定义样式的信息框"""
        msg_box = QMessageBox(icon, title, text, buttons, self)
        style = """
            QMessageBox { background-color: #ffffff; }
            QLabel { color: #1a5f2a; font-size: 14px; font-weight: bold;
                     background-color: #d4edda; padding: 12px; border-radius: 6px;
                     border: 1px solid #28a745; }
            QPushButton { min-width: 90px; padding: 8px 20px; border-radius: 6px;
                          font-weight: bold; font-size: 13px; border: none;
                          background-color: #28a745; color: #000000; }
            QPushButton:hover { background-color: #218838; }
        """
        msg_box.setStyleSheet(style)
        for btn in msg_box.buttons():
            btn.setText(btn.text())
        return msg_box.exec_()

    def _show_question_box(self, title, text):
        """显示自定义样式的询问框"""
        msg_box = QMessageBox(QMessageBox.Question, title, text, QMessageBox.Yes | QMessageBox.No, self)
        style = """
            QMessageBox { background-color: #ffffff; }
            QLabel { color: #1a5f2a; font-size: 14px; font-weight: bold;
                     background-color: #d4edda; padding: 12px; border-radius: 6px;
                     border: 1px solid #28a745; }
            QPushButton { min-width: 90px; padding: 8px 20px; border-radius: 6px;
                          font-weight: bold; font-size: 13px; border: none;
                          background-color: #28a745; color: #000000; }
            QPushButton:hover { background-color: #218838; }
        """
        msg_box.setStyleSheet(style)
        for btn in msg_box.buttons():
            btn_text = btn.text()
            if btn_text == "Yes" or btn_text == "是":
                btn.setStyleSheet("background-color: #28a745; color: #000000; min-width: 90px; padding: 8px 20px; border-radius: 6px; font-weight: bold; border: none;")
            elif btn_text == "No" or btn_text == "否":
                btn.setStyleSheet("background-color: #dc3545; color: #000000; min-width: 90px; padding: 8px 20px; border-radius: 6px; font-weight: bold; border: none;")
        return msg_box.exec_()

    def init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("☁️ 云同步 - 多设备数据同步")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(title)

        content_layout = QHBoxLayout()

        left_panel = QVBoxLayout()

        account_group = QGroupBox("📋 已登录账号")
        account_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        account_layout = QVBoxLayout()

        self.account_list = QListWidget()
        self.account_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.account_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
        """)
        self.account_list.itemClicked.connect(self.on_account_clicked)
        account_layout.addWidget(self.account_list)

        btn_layout = QHBoxLayout()
        self.btn_add_account = QPushButton("➕ 添加账号")
        self.btn_add_account.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        self.btn_add_account.clicked.connect(self.show_add_account_dialog)

        self.btn_create_new_data = QPushButton("新建空白数据")
        self.btn_create_new_data.setStyleSheet("""
            QPushButton {
                background-color: #16a085;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #138d75;
            }
        """)
        self.btn_create_new_data.clicked.connect(self.create_new_blank_data)

        self.btn_switch_account = QPushButton("🔄 切换账号")
        self.btn_switch_account.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.btn_switch_account.clicked.connect(self.switch_to_selected_account)

        self.btn_delete_account = QPushButton("🗑️ 删除")
        self.btn_delete_account.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.btn_delete_account.clicked.connect(self.delete_selected_account)

        self.btn_sync_upload = QPushButton("⬆️ 上传云端数据")
        self.btn_sync_upload.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.btn_sync_upload.clicked.connect(self.upload_current_data)

        self.btn_sync_download = QPushButton("⬇️ 下载云端数据")
        self.btn_sync_download.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.btn_sync_download.clicked.connect(self.download_current_data)

        btn_layout.addWidget(self.btn_add_account)
        btn_layout.addWidget(self.btn_create_new_data)
        btn_layout.addWidget(self.btn_delete_account)
        account_layout.addLayout(btn_layout)

        btn_layout2 = QHBoxLayout()
        btn_layout2.addWidget(self.btn_sync_upload)
        btn_layout2.addWidget(self.btn_sync_download)
        account_layout.addLayout(btn_layout2)

        account_group.setLayout(account_layout)
        left_panel.addWidget(account_group)

        right_panel = QVBoxLayout()

        info_group = QGroupBox("📊 当前账号信息")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(5, 5, 5, 5)

        self.lbl_current_account = QLabel("未登录")
        self.lbl_current_account.setStyleSheet("font-size: 14px; color: #666; padding: 2px;")
        info_layout.addWidget(self.lbl_current_account)

        self.lbl_last_upload = QLabel("最后上传：从未")
        self.lbl_last_upload.setStyleSheet("font-size: 12px; color: #888; padding: 2px;")
        info_layout.addWidget(self.lbl_last_upload)

        self.lbl_last_download = QLabel("最后下载：从未")
        self.lbl_last_download.setStyleSheet("font-size: 12px; color: #888; padding: 2px;")
        info_layout.addWidget(self.lbl_last_download)

        self.lbl_local_path = QLabel("本地路径：未设置")
        self.lbl_local_path.setStyleSheet("font-size: 11px; color: #888; padding: 2px;")
        self.lbl_local_path.setWordWrap(True)
        info_layout.addWidget(self.lbl_local_path)

        path_btn_layout = QHBoxLayout()
        self.btn_set_local_path = QPushButton("📁 设置本地路径")
        self.btn_set_local_path.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        self.btn_set_local_path.clicked.connect(self.set_local_backup_path)
        path_btn_layout.addWidget(self.btn_set_local_path)

        self.btn_open_local_folder = QPushButton("📂 打开文件夹")
        self.btn_open_local_folder.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        self.btn_open_local_folder.clicked.connect(self.open_local_backup_folder)
        path_btn_layout.addWidget(self.btn_open_local_folder)
        info_layout.addLayout(path_btn_layout)

        self.lbl_sync_status = QLabel("")
        self.lbl_sync_status.setStyleSheet("font-size: 12px; color: #27ae60; padding: 2px;")
        info_layout.addWidget(self.lbl_sync_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
            }
        """)
        info_layout.addWidget(self.progress_bar)

        info_group.setLayout(info_layout)
        right_panel.addWidget(info_group)

        help_group = QGroupBox("💡 使用帮助")
        help_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        help_layout = QVBoxLayout()
        help_text = QLabel(
            "1. 点击「添加账号」配置腾讯云COS信息\n"
            "2. 平时切换账号用主界面右下角「切换账号」\n"
            "3. 需要跨电脑时再点击「上传云端数据」或「下载云端数据」\n"
            "4. 在其他设备上添加相同账号，输入COS信息\n"
            "5. 本地切换不会访问云端，速度更快\n\n"
            "📎 腾讯云COS配置说明：\n"
            "- SecretId/SecretKey: 访问密钥管理获取\n"
            "- Bucket: 存储桶名称（如 my-shop-data）\n"
            "- Region: 地域（如 ap-guangzhou）\n"
            "- 文件夹: 用于区分不同用户的数据"
        )
        help_text.setStyleSheet("font-size: 11px; color: #666; padding: 5px;")
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)
        help_group.setLayout(help_layout)
        right_panel.addWidget(help_group)

        content_layout.addLayout(left_panel, 1)
        content_layout.addLayout(right_panel, 1)

        layout.addLayout(content_layout)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 30px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def load_accounts_to_list(self):
        """加载账号列表"""
        self.account_list.clear()
        accounts = self.cloud_manager.get_all_accounts()
        current = self.cloud_manager.get_current_account()
        current_row = -1

        for row, acc in enumerate(accounts):
            is_current = current and current.get('id') == acc.get('id')
            prefix = "⭐ " if is_current else "  "
            last_upload = acc.get('last_upload_time', '从未')
            item = QListWidgetItem(f"{prefix}{acc.get('name', '未知')} (上传:{last_upload})")
            item.setData(Qt.UserRole, acc.get('id'))
            self.account_list.addItem(item)
            if is_current:
                current_row = row

        if current_row >= 0:
            self.account_list.setCurrentRow(current_row)

        self.update_sync_info()

    def update_sync_info(self):
        """更新同步信息显示"""
        current = self.cloud_manager.get_current_account()
        if current:
            self.lbl_current_account.setText(f"当前账号：{current.get('name', '未知')}")
            self.lbl_last_upload.setText(f"最后上传：{current.get('last_upload_time', '从未')}")
            self.lbl_last_download.setText(f"最后下载：{current.get('last_download_time', '从未')}")
            local_path = current.get('local_backup_path', '未设置')
            self.lbl_local_path.setText(f"本地路径：{local_path}")
        else:
            self.lbl_current_account.setText("未登录")
            self.lbl_last_upload.setText("最后上传：从未")
            self.lbl_last_download.setText("最后下载：从未")
            self.lbl_local_path.setText("本地路径：未设置")

    def set_local_backup_path(self):
        """设置本地备份路径"""
        from PyQt5.QtWidgets import QFileDialog
        current = self.cloud_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先选择要设置的账号")
            return

        current_path = current.get('local_backup_path', '')
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择本地备份文件夹",
            current_path if current_path else self.cloud_manager._get_base_dir(),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            self.cloud_manager.set_local_backup_path(current['id'], folder)
            self.update_sync_info()
            self.lbl_sync_status.setText(f"✅ 本地路径已设置：{folder}")

    def open_local_backup_folder(self):
        """打开本地备份文件夹"""
        import subprocess
        current = self.cloud_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先选择账号")
            return

        folder_path = current.get('local_backup_path', '')
        if not folder_path or folder_path == '未设置':
            default_path = os.path.join(self.cloud_manager._get_base_dir(), current.get('folder', current.get('name', 'backup')))
            folder_path = default_path

        folder_path = os.path.normpath(folder_path)

        if not os.path.exists(folder_path):
            try:
                os.makedirs(folder_path, exist_ok=True)
            except Exception as e:
                self._show_message_box(QMessageBox.Warning, "错误", f"无法创建文件夹：{e}")
                return

        try:
            subprocess.Popen(f'start "" "{folder_path}"', shell=True)
        except Exception as e:
            self._show_message_box(QMessageBox.Warning, "错误", f"无法打开文件夹：{e}")

    def on_account_clicked(self, item):
        """点击账号时切换到该账号并显示信息"""
        account_id = item.data(Qt.UserRole)
        if account_id:
            account = self.cloud_manager._find_account_by_id(account_id)
            if account:
                self.cloud_manager.switch_account(account_id)
                self.cloud_manager._load_accounts()
                self.load_accounts_to_list()
                self.lbl_sync_status.setText(f"已选择账号：{account.get('name', '未知')}")
                self.lbl_sync_status.setStyleSheet("font-size: 12px; color: #3498db; padding: 5px;")
                self.update_sync_info()

    def switch_to_selected_account(self):
        """切换到选中的账号"""
        current_item = self.account_list.currentItem()
        if not current_item:
            self._show_message_box(QMessageBox.Warning, "提示", "请先在列表中选择一个账号")
            return

        account_id = current_item.data(Qt.UserRole)
        if account_id:
            account = self.cloud_manager._find_account_by_id(account_id)
            if account:
                self.cloud_manager.switch_account(account_id)
                self.cloud_manager._load_accounts()
                self.load_accounts_to_list()
                self.lbl_sync_status.setText(f"已切换到账号：{account.get('name', '未知')}")
                self.lbl_sync_status.setStyleSheet("font-size: 12px; color: #27ae60; padding: 5px; font-weight: bold;")
                QTimer.singleShot(2000, lambda: self.lbl_sync_status.setStyleSheet("font-size: 12px; color: #888; padding: 5px;"))
                self.update_sync_info()

    def show_add_account_dialog(self):
        """显示添加账号对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("➕ 添加云同步账号")
        dialog.resize(500, 400)
        dialog.setStyleSheet("background-color: white;")

        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("📝 请输入腾讯云COS配置信息："))
        layout.addSpacing(10)

        grid = QGridLayout()
        grid.addWidget(QLabel("账号名称："), 0, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("如：zhangsan_leimu")
        grid.addWidget(self.name_input, 0, 1)

        grid.addWidget(QLabel("SecretId："), 1, 0)
        self.secret_id_input = QLineEdit()
        self.secret_id_input.setPlaceholderText("腾讯云 SecretId")
        grid.addWidget(self.secret_id_input, 1, 1)

        grid.addWidget(QLabel("SecretKey："), 2, 0)
        self.secret_key_input = QLineEdit()
        self.secret_key_input.setPlaceholderText("腾讯云 SecretKey")
        self.secret_key_input.setEchoMode(QLineEdit.Password)
        grid.addWidget(self.secret_key_input, 2, 1)

        grid.addWidget(QLabel("Bucket："), 3, 0)
        self.bucket_input = QLineEdit()
        self.bucket_input.setPlaceholderText("存储桶名称")
        self.bucket_input.setText("dianpuguanli-1305093930")
        grid.addWidget(self.bucket_input, 3, 1)

        grid.addWidget(QLabel("Region："), 4, 0)
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText("地域，如 ap-guangzhou")
        self.region_input.setText("ap-beijing")
        grid.addWidget(self.region_input, 4, 1)

        grid.addWidget(QLabel("数据文件夹："), 5, 0)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("留空则使用账号名称")
        grid.addWidget(self.folder_input, 5, 1)

        layout.addLayout(grid)

        layout.addSpacing(20)
        help_label = QLabel(
            "💡 如何获取这些信息？\n"
            "1. 登录腾讯云控制台 → 对象存储 COS\n"
            "2. 创建存储桶，获取Bucket名称和地域\n"
            "3. 访问密钥 → 获取 SecretId 和 SecretKey"
        )
        help_label.setStyleSheet("color: #888; font-size: 11px; padding: 10px; background-color: #f9f9f9; border-radius: 4px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定添加")
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 10px 30px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        btn_ok.clicked.connect(lambda: self.add_account(dialog))
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 30px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        saved_creds = self.cloud_manager.get_last_used_credentials()
        if saved_creds:
            self.secret_id_input.setText(saved_creds.get('secret_id', ''))
            self.secret_key_input.setText(saved_creds.get('secret_key', ''))

        dialog.exec_()

    def add_account(self, dialog):
        """添加账号"""
        name = self.name_input.text().strip()
        secret_id = self.secret_id_input.text().strip()
        secret_key = self.secret_key_input.text().strip()
        bucket = self.bucket_input.text().strip()
        region = self.region_input.text().strip()
        folder = self.folder_input.text().strip()

        if not name:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入账号名称")
            return
        if not secret_id or not secret_key:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入SecretId和SecretKey")
            return
        if not bucket:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入Bucket名称")
            return
        if not region:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入地域")
            return

        account = self.cloud_manager.add_account(name, secret_id, secret_key, bucket, region, folder)
        if account:
            self.cloud_manager.switch_account(account['id'])
            self._show_message_box(QMessageBox.Information, "成功", f"账号「{name}」添加成功！")
            dialog.accept()
            self.load_accounts_to_list()

    def _read_account_dialog_values(self):
        name = self.name_input.text().strip()
        secret_id = self.secret_id_input.text().strip()
        secret_key = self.secret_key_input.text().strip()
        bucket = self.bucket_input.text().strip()
        region = self.region_input.text().strip()
        folder = self.folder_input.text().strip()

        if not name:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入账号名称")
            return None
        if not secret_id or not secret_key:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入 SecretId 和 SecretKey")
            return None
        if not bucket:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入 Bucket 名称")
            return None
        if not region:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入地域")
            return None
        return name, secret_id, secret_key, bucket, region, folder

    def _prompt_new_account_config(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("创建新数据账号")
        dialog.resize(500, 400)
        dialog.setStyleSheet("background-color: white;")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("请输入新数据的云同步账号配置："))
        layout.addSpacing(10)

        grid = QGridLayout()
        grid.addWidget(QLabel("账号名称："), 0, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如：new_shop_data")
        grid.addWidget(self.name_input, 0, 1)

        grid.addWidget(QLabel("SecretId："), 1, 0)
        self.secret_id_input = QLineEdit()
        self.secret_id_input.setPlaceholderText("腾讯云 SecretId")
        grid.addWidget(self.secret_id_input, 1, 1)

        grid.addWidget(QLabel("SecretKey："), 2, 0)
        self.secret_key_input = QLineEdit()
        self.secret_key_input.setPlaceholderText("腾讯云 SecretKey")
        self.secret_key_input.setEchoMode(QLineEdit.Password)
        grid.addWidget(self.secret_key_input, 2, 1)

        grid.addWidget(QLabel("Bucket："), 3, 0)
        self.bucket_input = QLineEdit()
        self.bucket_input.setPlaceholderText("存储桶名称")
        self.bucket_input.setText("dianpuguanli-1305093930")
        grid.addWidget(self.bucket_input, 3, 1)

        grid.addWidget(QLabel("Region："), 4, 0)
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText("例如 ap-beijing")
        self.region_input.setText("ap-beijing")
        grid.addWidget(self.region_input, 4, 1)

        grid.addWidget(QLabel("数据文件夹："), 5, 0)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("留空则使用账号名称")
        grid.addWidget(self.folder_input, 5, 1)
        layout.addLayout(grid)

        help_label = QLabel("创建后会生成新的空白本地数据，并自动上传空白数据到该云账号。")
        help_label.setStyleSheet("color: #666; font-size: 12px; padding: 10px; background-color: #f6f8fa; border-radius: 4px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("创建新数据")
        btn_ok.setStyleSheet("QPushButton { background-color: #16a085; color: white; border: none; padding: 10px 30px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #138d75; }")
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("QPushButton { background-color: #95a5a6; color: white; border: none; padding: 10px 30px; border-radius: 4px; }")

        values = {}
        def accept_if_valid():
            form_values = self._read_account_dialog_values()
            if not form_values:
                return
            values['account'] = form_values
            dialog.accept()

        btn_ok.clicked.connect(accept_if_valid)
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        saved_creds = self.cloud_manager.get_last_used_credentials()
        if saved_creds:
            self.secret_id_input.setText(saved_creds.get('secret_id', ''))
            self.secret_key_input.setText(saved_creds.get('secret_key', ''))

        if dialog.exec_() != QDialog.Accepted:
            return None
        return values.get('account')

    def _ask_current_data_save_mode(self):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("创建新数据")
        box.setText("创建新空白数据前，当前这份数据要怎么处理？")
        local_btn = box.addButton("只保存本地", QMessageBox.AcceptRole)
        upload_btn = box.addButton("保存本地并上传", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(local_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == upload_btn:
            return "upload"
        if clicked == local_btn:
            return "local"
        if clicked == cancel_btn:
            return None
        return None

    def _upload_account_snapshot(self, account, data):
        local_backup_ok, local_backup_result = self.cloud_manager.save_local_backup_before_upload(account['id'])
        if not local_backup_ok:
            return False, f"本地上传前备份失败：{local_backup_result}"

        uploader = TencentCOSUploader(
            account['secret_id'],
            account['secret_key'],
            account['bucket'],
            account['region']
        )

        cloud_ok, cloud_result = uploader.download_json(account['folder'])
        if cloud_ok and cloud_result:
            backup_ok, backup_result = self.cloud_manager.save_cloud_backup_before_upload(account['id'], cloud_result)
            if not backup_ok:
                return False, f"云端旧数据备份失败：{backup_result}"
        elif not cloud_ok and "云端没有数据" not in str(cloud_result) and "浜戠娌℃湁鏁版嵁" not in str(cloud_result):
            return False, f"云端旧数据读取失败：{cloud_result}"

        success, result = uploader.upload_json(data, account['folder'])
        if not success:
            return False, result
        self.cloud_manager.update_last_upload_time(account['id'])
        return True, result

    def _create_blank_profile_for_account(self, account):
        import shutil

        backup_path = account.get('local_backup_path', os.path.join(self.cloud_manager._get_base_dir(), account['folder']))
        profile_dir = os.path.join(backup_path, "local_current")
        os.makedirs(profile_dir, exist_ok=True)
        profile_file = os.path.join(profile_dir, "backup.db")
        temp_file = os.path.join(profile_dir, "blank_new.db")

        if os.path.exists(temp_file):
            os.remove(temp_file)

        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            temp_db = SafeDatabaseManager(temp_file)
        try:
            temp_db.conn.commit()
        finally:
            try:
                temp_db.conn.close()
            except Exception:
                pass

        shutil.copy2(temp_file, profile_file)
        try:
            os.remove(temp_file)
        except Exception:
            pass
        return profile_file

    def create_new_blank_data(self):
        active_account = self.cloud_manager.get_active_data_account()
        if not active_account and self.cloud_manager.get_current_account():
            active_account = self._ensure_active_account_for_local_save()
            if not active_account:
                return

        save_mode = self._ask_current_data_save_mode()
        if not save_mode:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(10)
        try:
            if active_account:
                self.lbl_sync_status.setText("正在保存当前数据到本地...")
                save_ok, save_result = self.cloud_manager.save_local_profile(active_account['id'])
                if not save_ok:
                    self._show_message_box(QMessageBox.Critical, "创建已取消", f"当前数据保存本地失败：{save_result}")
                    return

                if save_mode == "upload":
                    self.progress_bar.setValue(25)
                    self.lbl_sync_status.setText("正在上传当前数据...")
                    current_data = self.cloud_manager.export_data_to_json()
                    if not current_data:
                        self._show_message_box(QMessageBox.Critical, "创建已取消", "当前数据导出失败，未创建新数据。")
                        return
                    upload_ok, upload_result = self._upload_account_snapshot(active_account, current_data)
                    if not upload_ok:
                        self._show_message_box(QMessageBox.Critical, "创建已取消", f"当前数据上传失败：{upload_result}")
                        return

            values = self._prompt_new_account_config()
            if not values:
                return

            self.progress_bar.setValue(45)
            name, secret_id, secret_key, bucket, region, folder = values
            account = self.cloud_manager.add_account(name, secret_id, secret_key, bucket, region, folder)
            if not account:
                self._show_message_box(QMessageBox.Critical, "错误", "新账号创建失败")
                return

            self.lbl_sync_status.setText("正在创建空白本地数据...")
            profile_file = self._create_blank_profile_for_account(account)

            self.progress_bar.setValue(65)
            if self.parent_window and hasattr(self.parent_window, 'replace_database_from_local_profile'):
                ok, result = self.parent_window.replace_database_from_local_profile(profile_file, account['id'])
                if not ok:
                    self._show_message_box(QMessageBox.Critical, "错误", f"切换到新空白数据失败：{result}")
                    return
                self.db = self.parent_window.db
                self.cloud_manager.db = self.parent_window.db
            else:
                self._show_message_box(QMessageBox.Critical, "错误", "主窗口不支持切换到新空白数据")
                return

            self.cloud_manager.switch_account(account['id'])
            self.cloud_manager.set_active_data_account(account['id'])

            self.progress_bar.setValue(80)
            self.lbl_sync_status.setText("正在上传空白数据到云端...")
            blank_data = self.cloud_manager.export_data_to_json()
            if not blank_data:
                self._show_message_box(QMessageBox.Warning, "部分完成", "已创建本地空白数据，但空白数据导出失败，请稍后手动上传。")
                return
            blank_upload_ok, blank_upload_result = self._upload_account_snapshot(account, blank_data)
            if not blank_upload_ok:
                self._show_message_box(QMessageBox.Warning, "部分完成", f"已创建本地空白数据，但上传空白云端失败：{blank_upload_result}\n\n可稍后手动点击上传。")
                return

            self.progress_bar.setValue(100)
            self.load_accounts_to_list()
            self.update_sync_info()
            self.update_parent_data()
            if self.parent_window and hasattr(self.parent_window, 'update_cloud_account_label'):
                self.parent_window.update_cloud_account_label()
            self.lbl_sync_status.setText(f"✅ 已创建新空白数据：{account.get('name', '未知')}")
            self._show_message_box(QMessageBox.Information, "成功", f"已创建新空白数据并上传云端。\n\n账号：{account.get('name', '未知')}")
        except Exception as e:
            self._show_message_box(QMessageBox.Critical, "错误", f"创建新数据失败：{e}")
            import traceback
            traceback.print_exc()
        finally:
            self.progress_bar.setVisible(False)
            self.load_accounts_to_list()

    def delete_selected_account(self):
        """删除选中的账号"""
        current_item = self.account_list.currentItem()
        if not current_item:
            self._show_message_box(QMessageBox.Warning, "提示", "请先选择一个账号")
            return

        account_id = current_item.data(Qt.UserRole)
        account = self.cloud_manager._find_account_by_id(account_id)

        reply = self._show_question_box(
            "确认删除",
            f"确定要删除账号「{account.get('name', '未知')}」吗？\n删除后本地数据不受影响，但云端数据需要手动清理。"
        )

        if reply == QMessageBox.Yes:
            self.cloud_manager.delete_account(account_id)
            self.load_accounts_to_list()
            self._show_message_box(QMessageBox.Information, "成功", "账号已删除")

    def _ensure_active_account_for_local_save(self):
        active_account = self.cloud_manager.get_active_data_account()
        if active_account:
            return active_account

        current = self.cloud_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先选择当前本地数据所属账号")
            return None

        reply = self._show_question_box(
            "确认当前应用账号",
            f"当前主表格数据还没有绑定本地账号。\n\n"
            f"是否确认当前主表格数据属于账号：{current.get('name', '未知')}？"
        )
        if reply != QMessageBox.Yes:
            return None

        if self.cloud_manager.set_active_data_account(current['id']):
            if self.parent_window and hasattr(self.parent_window, 'update_cloud_account_label'):
                self.parent_window.update_cloud_account_label()
            return current
        self._show_message_box(QMessageBox.Critical, "错误", "绑定当前应用账号失败")
        return None

    def save_current_local_profile(self):
        """保存当前主表格数据到当前应用账号的本地档案。"""
        active_account = self._ensure_active_account_for_local_save()
        if not active_account:
            return

        ok, result = self.cloud_manager.save_local_profile(active_account['id'])
        if ok:
            self.lbl_sync_status.setText(f"✅ 已保存到本地账号：{active_account.get('name', '未知')}")
            self._show_message_box(QMessageBox.Information, "成功", f"当前数据已保存到本地账号。\n\n账号：{active_account.get('name', '未知')}\n路径：{result}")
        else:
            self._show_message_box(QMessageBox.Critical, "错误", f"保存本地账号失败：{result}")

    def _resolve_local_profile_target(self):
        """自动推断要应用的本地账号。"""
        current_item = self.account_list.currentItem()
        if current_item:
            target_id = current_item.data(Qt.UserRole)
            target_account = self.cloud_manager._find_account_by_id(target_id)
            if not target_account:
                return None, None, "账号不存在"
            return target_account, target_id, None

        available_profiles = self.cloud_manager.get_accounts_with_local_profiles()
        if not available_profiles:
            return None, None, "没有找到任何本地账号数据。"

        active_account = self.cloud_manager.get_active_data_account()
        active_id = active_account.get('id') if active_account else None
        candidates = [
            (acc, path)
            for acc, path in available_profiles
            if acc.get('id') != active_id
        ]
        if not candidates:
            return None, None, "没有其他可切换的本地账号数据。"

        if len(candidates) == 1:
            target_account, _ = candidates[0]
            return target_account, target_account.get('id'), None

        current = self.cloud_manager.get_current_account()
        if current:
            for acc, _ in candidates:
                if acc.get('id') == current.get('id'):
                    return acc, acc.get('id'), None

        target_account, _ = candidates[0]
        return target_account, target_account.get('id'), None

    def apply_selected_local_profile(self):
        """应用选中账号的本地档案到主表格。"""
        target_account, target_id, error = self._resolve_local_profile_target()
        if error:
            self._show_message_box(QMessageBox.Warning, "提示", error)
            return

        profile_ok, profile_path = self.cloud_manager.load_local_profile(target_id)
        if not profile_ok:
            self._show_message_box(QMessageBox.Warning, "提示", f"账号「{target_account.get('name', '未知')}」暂无本地数据。\n请先保存该账号本地数据，或从云端下载一次。")
            return

        normalize_ok, normalized_path = self.cloud_manager.ensure_local_profile_normalized(target_id, profile_path)
        if not normalize_ok:
            self._show_message_box(QMessageBox.Critical, "错误", f"本地账号数据迁移失败：{normalized_path}")
            return
        profile_path = normalized_path

        active_account = self.cloud_manager.get_active_data_account()
        if not active_account:
            self._show_message_box(
                QMessageBox.Warning,
                "请先保存当前数据",
                "当前主表格数据还没有绑定本地账号。\n\n"
                "为避免把当前数据误保存到要切换的目标账号，请先选择当前数据所属账号并点击「保存到本地账号」，再应用其他本地账号。"
            )
            return

        if active_account.get('id') == target_id:
            self._show_message_box(QMessageBox.Information, "提示", f"当前主表格已经是账号「{target_account.get('name', '未知')}」的数据。")
            return

        save_ok, save_result = self.cloud_manager.save_local_profile(active_account['id'])
        if not save_ok:
            self._show_message_box(QMessageBox.Critical, "切换已取消", f"当前应用账号数据保存失败，已取消切换：\n{save_result}")
            return

        reply = self._show_question_box(
            "确认应用本地账号",
            f"将应用账号「{target_account.get('name', '未知')}」的本地数据到主表格。\n\n"
            f"当前账号「{active_account.get('name', '未知')}」已先保存到本地。\n"
            f"是否继续？"
        )
        if reply != QMessageBox.Yes:
            return

        if self.parent_window and hasattr(self.parent_window, 'replace_database_from_local_profile'):
            ok, result = self.parent_window.replace_database_from_local_profile(profile_path, target_id)
        else:
            ok, result = False, "主窗口不支持安全切换本地账号"

        if ok:
            self.db = self.parent_window.db
            self.cloud_manager.db = self.parent_window.db
            self.cloud_manager.set_active_data_account(target_id)
            self.cloud_manager.switch_account(target_id)
            self.load_accounts_to_list()
            self.lbl_sync_status.setText(f"✅ 已应用本地账号：{target_account.get('name', '未知')}")
            self._show_message_box(QMessageBox.Information, "成功", f"已应用本地账号：{target_account.get('name', '未知')}")
        else:
            self._show_message_box(QMessageBox.Critical, "错误", f"应用本地账号失败：{result}")

    def upload_current_data(self):
        """上传当前账号数据"""
        current = self.cloud_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先添加并切换到要上传的账号")
            return

        if self.parent_window and hasattr(self.parent_window, 'ensure_upload_account_allowed'):
            if not self.parent_window.ensure_upload_account_allowed(current):
                return
        else:
            active_account = self.cloud_manager.get_active_data_account()
            if active_account and active_account.get('id') != current.get('id'):
                self._show_message_box(
                    QMessageBox.Warning,
                    "账号不一致，已取消上传",
                    f"当前表格数据属于账号：{active_account.get('name', '未知')}\n"
                    f"你当前选择的云同步账号：{current.get('name', '未知')}\n\n"
                    f"为避免覆盖错误存档，本次上传已取消。"
                )
                return
            if not active_account:
                reply = self._show_question_box(
                    "确认数据归属账号",
                    f"当前本地表格数据还没有绑定云同步账号。\n\n"
                    f"是否确认这份本地数据属于账号：{current.get('name', '未知')}？"
                )
                if reply != QMessageBox.Yes:
                    return
                self.cloud_manager.set_active_data_account(current['id'])

        reply = self._show_question_box(
            "确认上传",
            f"上传将覆盖云端存档！\n\n账号：{current.get('name', '未知')}\n是否继续上传？"
        )
        if reply != QMessageBox.Yes:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(20)
        self.lbl_sync_status.setText("正在备份本地数据...")

        try:
            local_backup_ok, local_backup_result = self.cloud_manager.save_local_backup_before_upload(current['id'])
            if not local_backup_ok:
                self._show_message_box(QMessageBox.Critical, "上传已取消", f"本地上传前备份失败，已取消上传：{local_backup_result}")
                return

            self.progress_bar.setValue(30)
            self.lbl_sync_status.setText("正在导出本地数据...")
            data = self.cloud_manager.export_data_to_json()
            if not data:
                self._show_message_box(QMessageBox.Critical, "错误", "数据导出失败")
                return

            uploader = TencentCOSUploader(
                current['secret_id'],
                current['secret_key'],
                current['bucket'],
                current['region']
            )

            self.progress_bar.setValue(40)
            self.lbl_sync_status.setText("正在备份云端旧数据...")
            cloud_ok, cloud_result = uploader.download_json(current['folder'])
            cloud_backup_path = "云端无旧数据"
            if cloud_ok and cloud_result:
                backup_ok, backup_result = self.cloud_manager.save_cloud_backup_before_upload(current['id'], cloud_result)
                if not backup_ok:
                    self._show_message_box(QMessageBox.Critical, "上传已取消", f"云端旧数据备份失败，已取消上传：{backup_result}")
                    return
                cloud_backup_path = backup_result
            elif not cloud_ok and "云端没有数据" not in str(cloud_result):
                self._show_message_box(QMessageBox.Critical, "上传已取消", f"云端旧数据读取失败，已取消上传：{cloud_result}")
                return

            self.progress_bar.setValue(60)
            self.lbl_sync_status.setText("正在上传到云端...")

            success, result = uploader.upload_json(data, current['folder'])
            if success:
                data_size = len(json.dumps(data, ensure_ascii=False))
                size_mb = data_size / (1024 * 1024)
                self.cloud_manager.update_last_upload_time(current['id'])
                self.progress_bar.setValue(100)
                self.lbl_sync_status.setText(f"✅ 上传成功！({size_mb:.2f} MB)")
                self._show_message_box(QMessageBox.Information, "成功", f"数据已上传到云端，上传前本地数据已备份（最多保留5份）。\n\n账号：{current['name']}\n文件大小：{size_mb:.2f} MB\n云端路径：{result}\n本地备份：{local_backup_result}\n云端旧备份：{cloud_backup_path}")
                self.update_sync_info()
            else:
                self._show_message_box(QMessageBox.Critical, "错误", f"上传失败：{result}")

        except Exception as e:
            self._show_message_box(QMessageBox.Critical, "错误", f"上传异常：{str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.progress_bar.setVisible(False)
            self.load_accounts_to_list()

    def download_current_data(self):
        """下载当前账号数据"""
        current = self.cloud_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先添加并切换到要下载的账号")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(20)
        self.lbl_sync_status.setText("正在检查云端数据...")

        try:
            uploader = TencentCOSUploader(
                current['secret_id'],
                current['secret_key'],
                current['bucket'],
                current['region']
            )

            success, result = uploader.download_json(current['folder'])

            if not success:
                if "云端没有数据" in str(result):
                    self.progress_bar.setVisible(False)
                    self.lbl_sync_status.setText("云端没有数据，请先上传")
                    self.lbl_sync_status.setStyleSheet("font-size: 12px; color: #e74c3c; padding: 5px; font-weight: bold;")
                    QTimer.singleShot(2000, lambda: self.lbl_sync_status.setStyleSheet("font-size: 12px; color: #27ae60; padding: 5px;"))
                    self._show_message_box(QMessageBox.Information, "提示", "云端没有数据，请先上传！")
                    return
                else:
                    self.progress_bar.setVisible(False)
                    self._show_message_box(QMessageBox.Critical, "错误", f"下载失败：{result}")
                    return

            if not result or len(result) == 0:
                self.progress_bar.setVisible(False)
                self.lbl_sync_status.setText("云端没有数据，请先上传")
                self._show_message_box(QMessageBox.Information, "提示", "云端没有数据，请先上传！")
                return

            reply = self._show_question_box(
                "确认下载",
                "下载将覆盖本地数据！\n是否继续？"
            )
            if reply != QMessageBox.Yes:
                self.progress_bar.setVisible(False)
                return

            self.lbl_sync_status.setText("正在备份本地旧数据...")
            backup_ok, backup_result = self.cloud_manager.save_local_backup_before_download(current['id'])
            if not backup_ok:
                self.progress_bar.setVisible(False)
                self._show_message_box(QMessageBox.Critical, "下载已取消", f"本地旧数据备份失败，已取消下载：{backup_result}")
                return

            self.progress_bar.setValue(30)
            self.lbl_sync_status.setText("正在下载...")

            data_size = len(json.dumps(result, ensure_ascii=False))
            size_mb = data_size / (1024 * 1024)

            self.progress_bar.setValue(50)

            if self.cloud_manager.import_data_from_json(result):
                self.cloud_manager.update_last_download_time(current['id'])
                self.cloud_manager.set_active_data_account(current['id'])
                self.cloud_manager.save_local_profile(current['id'])
                self.progress_bar.setValue(100)
                self.lbl_sync_status.setText(f"✅ 下载成功！({size_mb:.2f} MB)")
                if self.parent_window and hasattr(self.parent_window, 'show_toast'):
                    self.parent_window.show_toast(f"✅ 下载成功！({size_mb:.2f} MB)")
                else:
                    self.lbl_sync_status.setText(f"✅ 下载成功！({size_mb:.2f} MB) - 数据已导入")
                self.update_sync_info()
                self.update_parent_data()
                if self.parent_window and hasattr(self.parent_window, 'update_cloud_account_label'):
                    self.parent_window.update_cloud_account_label()
            else:
                self._show_message_box(QMessageBox.Critical, "错误", "数据导入失败")

        except Exception as e:
            self._show_message_box(QMessageBox.Critical, "错误", f"下载异常：{str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.progress_bar.setVisible(False)
            self.load_accounts_to_list()

    def download_current_data(self):
        """下载当前云账号数据，覆盖前按当前应用账号保存本地档案。"""
        current = self.cloud_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先添加并切换到要下载的账号")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(20)
        self.lbl_sync_status.setText("正在检查云端数据...")

        try:
            uploader = TencentCOSUploader(
                current['secret_id'],
                current['secret_key'],
                current['bucket'],
                current['region']
            )

            success, result = uploader.download_json(current['folder'])
            if not success:
                self.progress_bar.setVisible(False)
                if "云端没有数据" in str(result) or "浜戠娌℃湁鏁版嵁" in str(result):
                    self.lbl_sync_status.setText("云端没有数据，请先上传")
                    self._show_message_box(QMessageBox.Information, "提示", "云端没有数据，请先上传。")
                else:
                    self._show_message_box(QMessageBox.Critical, "错误", f"下载失败：{result}")
                return

            if not result or len(result) == 0:
                self.progress_bar.setVisible(False)
                self.lbl_sync_status.setText("云端没有数据，请先上传")
                self._show_message_box(QMessageBox.Information, "提示", "云端没有数据，请先上传。")
                return

            active_account = self.cloud_manager.get_active_data_account()
            if not active_account:
                reply = self._show_question_box(
                    "确认当前数据归属",
                    f"当前主表格数据还没有绑定本地账号。\n\n"
                    f"是否确认当前主表格数据属于账号：{current.get('name', '未知')}？\n"
                    f"确认后会先保存本地档案，再下载云端数据覆盖。"
                )
                if reply != QMessageBox.Yes:
                    self.progress_bar.setVisible(False)
                    return
                if not self.cloud_manager.set_active_data_account(current['id']):
                    self.progress_bar.setVisible(False)
                    self._show_message_box(QMessageBox.Critical, "错误", "绑定当前数据归属账号失败")
                    return
                active_account = current

            reply = self._show_question_box(
                "确认下载",
                f"下载将覆盖当前主表格数据！\n\n"
                f"当前主表格属于：{active_account.get('name', '未知')}\n"
                f"将从云端下载账号：{current.get('name', '未知')}\n\n"
                f"覆盖前会先保存并备份当前主表格数据。是否继续？"
            )
            if reply != QMessageBox.Yes:
                self.progress_bar.setVisible(False)
                return

            self.lbl_sync_status.setText("正在保存当前账号本地档案...")
            save_ok, save_result = self.cloud_manager.save_local_profile(active_account['id'])
            if not save_ok:
                self.progress_bar.setVisible(False)
                self._show_message_box(QMessageBox.Critical, "下载已取消", f"当前账号本地档案保存失败，已取消下载：{save_result}")
                return

            self.lbl_sync_status.setText("正在备份当前账号旧数据...")
            backup_ok, backup_result = self.cloud_manager.save_local_backup_before_download(active_account['id'])
            if not backup_ok:
                self.progress_bar.setVisible(False)
                self._show_message_box(QMessageBox.Critical, "下载已取消", f"当前账号旧数据备份失败，已取消下载：{backup_result}")
                return

            self.progress_bar.setValue(30)
            self.lbl_sync_status.setText("正在导入云端数据...")

            data_size = len(json.dumps(result, ensure_ascii=False))
            size_mb = data_size / (1024 * 1024)

            self.progress_bar.setValue(50)
            if self.cloud_manager.import_data_from_json(result):
                self.cloud_manager.update_last_download_time(current['id'])
                self.cloud_manager.set_active_data_account(current['id'])
                self.cloud_manager.switch_account(current['id'])
                self.cloud_manager.save_local_profile(current['id'])
                self.progress_bar.setValue(100)
                self.lbl_sync_status.setText(f"✅ 下载成功！({size_mb:.2f} MB)")
                if self.parent_window and hasattr(self.parent_window, 'show_toast'):
                    self.parent_window.show_toast(f"✅ 下载成功！({size_mb:.2f} MB)")
                self.update_sync_info()
                self.update_parent_data()
                if self.parent_window and hasattr(self.parent_window, 'update_cloud_account_label'):
                    self.parent_window.update_cloud_account_label()
            else:
                error = getattr(self.cloud_manager, 'last_import_error', '') or "数据导入失败"
                self._show_message_box(QMessageBox.Critical, "错误", f"数据导入失败：{error}")

        except Exception as e:
            self._show_message_box(QMessageBox.Critical, "错误", f"下载异常：{str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.progress_bar.setVisible(False)
            self.load_accounts_to_list()

    def update_parent_data(self):
        """更新父窗口数据"""
        if self.parent_window:
            if hasattr(self.parent_window, 'load_data_safe'):
                self.parent_window.load_data_safe()
            if hasattr(self.parent_window, 'show_toast'):
                self.parent_window.show_toast("数据已刷新")


__all__ = ["CloudSyncManager", "TencentCOSUploader", "CloudSyncDialog"]

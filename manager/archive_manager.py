# -*- coding: utf-8 -*-
"""
本地存档模块。
提供账号管理、本地保存读取、账号切换等功能。
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

try:
    from manager.data_root import DataRootManager
except ImportError:
    from data_root import DataRootManager

try:
    from manager.window_icons import apply_window_icon
except ImportError:
    from window_icons import apply_window_icon


class ArchiveManager:
    """存档管理器 - 负责账号管理和本地数据保存读取"""

    def __init__(self, db_manager):
        self.db = db_manager
        self.data_root_manager = DataRootManager()
        self.accounts_file = self._get_accounts_file_path()
        self.current_account = None
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
            result[col] = ArchiveManager._safe_serialize_value(val)
        return result

    @staticmethod
    def _convert_dict_for_db(data_dict, columns):
        """将字典转换为数据库值，处理二进制字段"""
        result = []
        for col in columns:
            val = data_dict.get(col)
            result.append(ArchiveManager._safe_deserialize_value(val, col))
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
        data_root = self.data_root_manager.get_data_root()
        if data_root:
            self.data_root_manager.ensure_structure(data_root)
            return self.data_root_manager.accounts_config_path(data_root)
        base_dir = self._get_base_dir()
        return os.path.join(base_dir, "archive_accounts.json")

    def refresh_storage_paths(self):
        self.accounts_file = self._get_accounts_file_path()
        self._load_accounts()

    def get_data_root(self):
        return self.data_root_manager.get_data_root()

    def set_data_root(self, root_path):
        root = self.data_root_manager.set_data_root(root_path)
        self.data_root_manager.migrate_common_files(root)
        self.refresh_storage_paths()
        for acc in self.accounts:
            self._ensure_archive_account_dir(acc)
        self._save_accounts()
        return root

    def _archive_account_name(self, account):
        return account.get("name") or account.get("folder") or account.get("id") or "未命名账号"

    def _archive_db_path_for_account(self, account):
        root = self.get_data_root()
        if not root:
            return None
        return self.data_root_manager.account_db_path(self._archive_account_name(account), root)

    def _archive_browser_dir_for_account(self, account):
        root = self.get_data_root()
        if not root:
            return None
        return self.data_root_manager.account_browser_dir(self._archive_account_name(account), root)

    def _ensure_archive_account_dir(self, account):
        root = self.get_data_root()
        if not root or not account:
            return None
        account_name = self._archive_account_name(account)
        account_dir = self.data_root_manager.ensure_account_dirs(account_name, root)
        account["local_backup_path"] = account_dir
        account["folder"] = self.data_root_manager.safe_account_folder_name(account_name)
        return account_dir

    def _load_accounts(self):
        """加载账号列表"""
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.accounts = data.get('accounts', [])
                    self._normalize_account_metadata()
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
            data = self.data_root_manager.load_accounts_data(self.get_data_root())
            self.accounts = data.get('accounts', []) if isinstance(data, dict) else []
            self._normalize_account_metadata()
            self.current_account_id = data.get('current_account') if isinstance(data, dict) else None
            self.active_data_account_id = data.get('active_data_account_id') if isinstance(data, dict) else None
            self.current_account = self._find_account_by_id(self.current_account_id) if self.current_account_id else None

    def _normalize_account_metadata(self):
        """补齐本地存档账号元数据。"""
        for acc in getattr(self, "accounts", []):
            acc.setdefault("last_save_time", None)
            acc.setdefault("last_read_time", None)

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

    def add_account(self, name, folder=""):
        """添加新账号"""
        account_id = self._generate_account_id()
        folder_name = folder.strip() if folder.strip() else name.strip()
        local_folder = os.path.join(self._get_base_dir(), folder_name)
        account = {
            'id': account_id,
            'name': name.strip(),
            'folder': folder_name,
            'local_backup_path': local_folder,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'last_save_time': None,
            'last_read_time': None
        }
        self._ensure_archive_account_dir(account)
        self.accounts.append(account)
        self._save_accounts()
        return account

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
                    if key in ['name', 'folder', 'local_backup_path']:
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

    def update_last_save_time(self, account_id):
        """更新最后保存时间"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                acc['last_save_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_accounts()
                if self.current_account_id == account_id:
                    self.current_account = acc
                return

    def update_last_read_time(self, account_id):
        """更新最后读取时间"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                acc['last_read_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    def save_local_backup_before_read(self, account_id):
        """读取存档覆盖本地前，备份当前本地DB。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                archive_backup = self.data_root_manager.account_read_backup_path(self._archive_account_name(acc), self.get_data_root()) if self.get_data_root() else None
                if archive_backup:
                    try:
                        os.makedirs(os.path.dirname(archive_backup), exist_ok=True)
                        try:
                            self.db.conn.commit()
                        except Exception:
                            pass
                        import shutil
                        shutil.copy2(self.db.db_path, archive_backup)
                        return True, archive_backup
                    except Exception as e:
                        return False, str(e)
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                try:
                    os.makedirs(os.path.join(backup_path, "local_backup_before_read"), exist_ok=True)
                    backup_file = os.path.join(backup_path, "local_backup_before_read", "backup.db")
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

    def save_local_backup_before_save(self, account_id, max_backups=5):
        """保存覆盖存档前，按时间备份当前本地DB，最多保留最近几份。"""
        for acc in self.accounts:
            if acc.get('id') == account_id:
                if self.get_data_root():
                    return self.save_local_profile(account_id)
                backup_path = acc.get('local_backup_path', os.path.join(self._get_base_dir(), acc['folder']))
                try:
                    backup_dir = os.path.join(backup_path, "local_backup_before_save")
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
                archive_db = self._archive_db_path_for_account(acc)
                if archive_db:
                    try:
                        self._ensure_archive_account_dir(acc)
                        try:
                            self.db.conn.commit()
                        except Exception:
                            pass
                        if os.path.abspath(self.db.db_path) != os.path.abspath(archive_db):
                            import shutil
                            source_stat = os.stat(self.db.db_path)
                            target_stat = os.stat(archive_db) if os.path.exists(archive_db) else None
                            if target_stat is None or (
                                source_stat.st_size,
                                source_stat.st_mtime_ns,
                            ) != (
                                target_stat.st_size,
                                target_stat.st_mtime_ns,
                            ):
                                shutil.copy2(self.db.db_path, archive_db)
                        return True, archive_db
                    except Exception as e:
                        return False, str(e)
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
                archive_db = self._archive_db_path_for_account(acc)
                if archive_db:
                    if os.path.exists(archive_db):
                        return True, archive_db
                    return False, "该账号暂无本地存档"
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
                    if os.path.exists(standard_file):
                        source_stat = os.stat(profile_path)
                        target_stat = os.stat(standard_file)
                        if (source_stat.st_size, source_stat.st_mtime_ns) == (target_stat.st_size, target_stat.st_mtime_ns):
                            return True, standard_file
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
        """从JSON导入数据：事务覆盖，并兼容本地缺失的新字段。"""
        self.last_import_error = ""
        current_table = ""
        try:
            if not data or 'version' not in data:
                self.last_import_error = "存档数据格式无效"
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
                'link_combinations',
            ]
            delete_order = [
                'imported_orders', 'import_history', 'records', 'product_image_history', 'store_records',
                'daily_records', 'profit_records', 'promotion_daily_data', 'historical_data',
                'manual_margin_data', 'store_temp_images', 'daily_tasks', 'task_reminders', 'product_specs',
                'products', 'stores', 'cost_history', 'cost_library',
                'cost_categories', 'settings', 'ai_prompts', 'ai_common_prompts',
                'store_prompts', 'link_combinations',
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


class ArchiveDialog(QDialog):
    """存档账号管理对话框"""

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

    def __init__(self, db_manager, archive_manager=None, parent=None):
        super().__init__(parent)
        apply_window_icon(self, "archive")
        self.db = db_manager
        self.archive_manager = archive_manager if archive_manager else ArchiveManager(db_manager)
        self.parent_window = parent
        self.setWindowTitle("💾 存档 - 账号管理")
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

        title = QLabel("💾 存档 - 本地多版本共用数据")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(title)

        content_layout = QHBoxLayout()

        left_panel = QVBoxLayout()

        account_group = QGroupBox("📋 存档账号")
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

        self.btn_save_archive = QPushButton("💾 保存到存档")
        self.btn_save_archive.setStyleSheet("""
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
        self.btn_save_archive.clicked.connect(self.save_current_data_to_archive)

        self.btn_read_archive = QPushButton("📂 读取存档")
        self.btn_read_archive.setStyleSheet("""
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
        self.btn_read_archive.clicked.connect(self.read_current_data_from_archive)

        btn_layout.addWidget(self.btn_add_account)
        btn_layout.addWidget(self.btn_create_new_data)
        btn_layout.addWidget(self.btn_delete_account)
        account_layout.addLayout(btn_layout)

        btn_layout2 = QHBoxLayout()
        btn_layout2.addWidget(self.btn_save_archive)
        btn_layout2.addWidget(self.btn_read_archive)
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

        self.lbl_last_save = QLabel("最后保存：从未")
        self.lbl_last_save.setStyleSheet("font-size: 12px; color: #888; padding: 2px;")
        info_layout.addWidget(self.lbl_last_save)

        self.lbl_last_read = QLabel("最后读取：从未")
        self.lbl_last_read.setStyleSheet("font-size: 12px; color: #888; padding: 2px;")
        info_layout.addWidget(self.lbl_last_read)

        self.lbl_local_path = QLabel("存档母文件夹：未设置")
        self.lbl_local_path.setStyleSheet("font-size: 11px; color: #888; padding: 2px;")
        self.lbl_local_path.setWordWrap(True)
        info_layout.addWidget(self.lbl_local_path)

        path_btn_layout = QHBoxLayout()
        self.btn_set_local_path = QPushButton("📁 设置存档母文件夹")
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

        self.lbl_archive_status = QLabel("")
        self.lbl_archive_status.setStyleSheet("font-size: 12px; color: #27ae60; padding: 2px;")
        info_layout.addWidget(self.lbl_archive_status)

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
            "1. 先设置「存档母文件夹」，源码版和打包版会共用这个位置\n"
            "2. 每个账号保存到「账号数据/账号名/data.db」\n"
            "3. Ctrl+S 会保存当前账号到存档\n"
            "4. 「读取存档」会先保留一个读取前备份，再切换到所选账号\n"
            "5. 浏览器数据按账号放在「账号数据/账号名/浏览器数据」"
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
        accounts = self.archive_manager.get_all_accounts()
        current = self.archive_manager.get_current_account()
        current_row = -1

        for row, acc in enumerate(accounts):
            is_current = current and current.get('id') == acc.get('id')
            prefix = "⭐ " if is_current else "  "
            last_save = acc.get('last_save_time', '从未')
            item = QListWidgetItem(f"{prefix}{acc.get('name', '未知')} (保存:{last_save})")
            item.setData(Qt.UserRole, acc.get('id'))
            self.account_list.addItem(item)
            if is_current:
                current_row = row

        if current_row >= 0:
            self.account_list.setCurrentRow(current_row)

        self.update_archive_info()

    def update_archive_info(self):
        """更新同步信息显示"""
        current = self.archive_manager.get_current_account()
        if current:
            self.lbl_current_account.setText(f"当前账号：{current.get('name', '未知')}")
            self.lbl_last_save.setText(f"最后保存：{current.get('last_save_time', '从未')}")
            self.lbl_last_read.setText(f"最后读取：{current.get('last_read_time', '从未')}")
            root = self.archive_manager.get_data_root() or "未设置"
            self.lbl_local_path.setText(f"存档母文件夹：{root}")
        else:
            self.lbl_current_account.setText("未选择账号")
            self.lbl_last_save.setText("最后保存：从未")
            self.lbl_last_read.setText("最后读取：从未")
            root = self.archive_manager.get_data_root() or "未设置"
            self.lbl_local_path.setText(f"存档母文件夹：{root}")

    def set_local_backup_path(self):
        """设置存档母文件夹"""
        from PyQt5.QtWidgets import QFileDialog
        current_path = self.archive_manager.get_data_root() or self.archive_manager.data_root_manager.suggest_existing_data_root() or self.archive_manager._get_base_dir()
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择存档母文件夹",
            current_path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if folder:
            root = self.archive_manager.set_data_root(folder)
            self.update_archive_info()
            self.load_accounts_to_list()
            self.lbl_archive_status.setText(f"✅ 存档母文件夹已设置：{root}")

    def open_local_backup_folder(self):
        """打开存档母文件夹"""
        folder_path = self.archive_manager.get_data_root()
        if not folder_path:
            self._show_message_box(QMessageBox.Warning, "提示", "请先设置存档母文件夹")
            return

        folder_path = os.path.normpath(folder_path)

        if not os.path.exists(folder_path):
            try:
                os.makedirs(folder_path, exist_ok=True)
            except Exception as e:
                self._show_message_box(QMessageBox.Warning, "错误", f"无法创建文件夹：{e}")
                return

        try:
            os.startfile(folder_path)
        except Exception as e:
            self._show_message_box(QMessageBox.Warning, "错误", f"无法打开文件夹：{e}")

    def on_account_clicked(self, item):
        """点击账号时切换到该账号并显示信息"""
        account_id = item.data(Qt.UserRole)
        if account_id:
            account = self.archive_manager._find_account_by_id(account_id)
            if account:
                self.archive_manager.switch_account(account_id)
                self.archive_manager._load_accounts()
                self.load_accounts_to_list()
                self.lbl_archive_status.setText(f"已选择账号：{account.get('name', '未知')}")
                self.lbl_archive_status.setStyleSheet("font-size: 12px; color: #3498db; padding: 5px;")
                self.update_archive_info()

    def show_add_account_dialog(self):
        """显示添加账号对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("➕ 添加存档账号")
        dialog.resize(500, 240)
        dialog.setStyleSheet("background-color: white;")

        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("📝 请输入本地存档账号名称："))
        layout.addSpacing(10)

        grid = QGridLayout()
        grid.addWidget(QLabel("账号名称："), 0, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("如：zhangsan_leimu")
        grid.addWidget(self.name_input, 0, 1)

        self.folder_input = QLineEdit()

        layout.addLayout(grid)

        layout.addSpacing(20)
        help_label = QLabel(
            "💡 账号名称会作为文件夹名称。\n"
            "保存位置：存档母文件夹/账号数据/账号名称/data.db"
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

        dialog.exec_()

    def add_account(self, dialog):
        """添加账号"""
        name = self.name_input.text().strip()
        folder = self.folder_input.text().strip()

        if not name:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入账号名称")
            return
        account = self.archive_manager.add_account(name, folder=folder)
        if account:
            self.archive_manager.switch_account(account['id'])
            self._show_message_box(QMessageBox.Information, "成功", f"账号「{name}」添加成功！")
            dialog.accept()
            self.load_accounts_to_list()

    def _read_account_dialog_values(self):
        name = self.name_input.text().strip()
        folder = self.folder_input.text().strip()

        if not name:
            self._show_message_box(QMessageBox.Warning, "提示", "请输入账号名称")
            return None
        return name, folder

    def _prompt_new_account_config(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("创建新数据账号")
        dialog.resize(500, 400)
        dialog.setStyleSheet("background-color: white;")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("请输入新数据的本地存档账号名称："))
        layout.addSpacing(10)

        grid = QGridLayout()
        grid.addWidget(QLabel("账号名称："), 0, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如：new_shop_data")
        grid.addWidget(self.name_input, 0, 1)

        grid.addWidget(QLabel("数据文件夹："), 1, 0)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("留空则使用账号名称")
        grid.addWidget(self.folder_input, 1, 1)
        layout.addLayout(grid)

        help_label = QLabel("创建后会生成新的空白本地数据，并保存到本地存档账号。")
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

        if dialog.exec_() != QDialog.Accepted:
            return None
        return values.get('account')

    def _ask_current_data_save_mode(self):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("创建新数据")
        box.setText("创建新空白数据前，当前这份数据要怎么处理？")
        local_btn = box.addButton("只保存本地", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(local_btn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == local_btn:
            return "local"
        if clicked == cancel_btn:
            return None
        return None

    def _create_blank_profile_for_account(self, account):
        import shutil

        backup_path = account.get('local_backup_path', os.path.join(self.archive_manager._get_base_dir(), account['folder']))
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
        active_account = self.archive_manager.get_active_data_account()
        if not active_account and self.archive_manager.get_current_account():
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
                self.lbl_archive_status.setText("正在保存当前数据到本地...")
                save_ok, save_result = self.archive_manager.save_local_profile(active_account['id'])
                if not save_ok:
                    self._show_message_box(QMessageBox.Critical, "创建已取消", f"当前数据保存本地失败：{save_result}")
                    return

            values = self._prompt_new_account_config()
            if not values:
                return

            self.progress_bar.setValue(45)
            name, folder = values
            account = self.archive_manager.add_account(name, folder=folder)
            if not account:
                self._show_message_box(QMessageBox.Critical, "错误", "新账号创建失败")
                return

            self.lbl_archive_status.setText("正在创建空白本地数据...")
            profile_file = self._create_blank_profile_for_account(account)

            self.progress_bar.setValue(65)
            if self.parent_window and hasattr(self.parent_window, 'replace_database_from_local_profile'):
                ok, result = self.parent_window.replace_database_from_local_profile(profile_file, account['id'])
                if not ok:
                    self._show_message_box(QMessageBox.Critical, "错误", f"切换到新空白数据失败：{result}")
                    return
                self.db = self.parent_window.db
                self.archive_manager.db = self.parent_window.db
            else:
                self._show_message_box(QMessageBox.Critical, "错误", "主窗口不支持切换到新空白数据")
                return

            self.archive_manager.switch_account(account['id'])
            self.archive_manager.set_active_data_account(account['id'])

            self.progress_bar.setValue(80)
            self.lbl_archive_status.setText("正在保存空白数据到存档...")
            blank_save_ok, blank_save_result = self.archive_manager.save_local_profile(account['id'])
            if not blank_save_ok:
                self._show_message_box(QMessageBox.Warning, "部分完成", f"已创建本地空白数据，但保存存档失败：{blank_save_result}")
                return

            self.progress_bar.setValue(100)
            self.load_accounts_to_list()
            self.update_archive_info()
            self.update_parent_data()
            if self.parent_window and hasattr(self.parent_window, 'update_archive_account_label'):
                self.parent_window.update_archive_account_label()
            self.lbl_archive_status.setText(f"✅ 已创建新空白数据：{account.get('name', '未知')}")
            self._show_message_box(QMessageBox.Information, "成功", f"已创建新空白数据并保存到本地存档。\n\n账号：{account.get('name', '未知')}")
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
        account = self.archive_manager._find_account_by_id(account_id)

        reply = self._show_question_box(
            "确认删除",
            f"确定要删除账号「{account.get('name', '未知')}」吗？\n删除账号不会删除当前正在使用的本地数据。"
        )

        if reply == QMessageBox.Yes:
            self.archive_manager.delete_account(account_id)
            self.load_accounts_to_list()
            self._show_message_box(QMessageBox.Information, "成功", "账号已删除")

    def _ensure_active_account_for_local_save(self):
        active_account = self.archive_manager.get_active_data_account()
        if active_account:
            return active_account

        current = self.archive_manager.get_current_account()
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

        if self.archive_manager.set_active_data_account(current['id']):
            if self.parent_window and hasattr(self.parent_window, 'update_archive_account_label'):
                self.parent_window.update_archive_account_label()
            return current
        self._show_message_box(QMessageBox.Critical, "错误", "绑定当前应用账号失败")
        return None

    def save_current_local_profile(self):
        """保存当前主表格数据到当前应用账号的本地档案。"""
        active_account = self._ensure_active_account_for_local_save()
        if not active_account:
            return

        ok, result = self.archive_manager.save_local_profile(active_account['id'])
        if ok:
            self.lbl_archive_status.setText(f"✅ 已保存到本地账号：{active_account.get('name', '未知')}")
            self._show_message_box(QMessageBox.Information, "成功", f"当前数据已保存到本地账号。\n\n账号：{active_account.get('name', '未知')}\n路径：{result}")
        else:
            self._show_message_box(QMessageBox.Critical, "错误", f"保存本地账号失败：{result}")

    def _resolve_local_profile_target(self):
        """自动推断要应用的本地账号。"""
        current_item = self.account_list.currentItem()
        if current_item:
            target_id = current_item.data(Qt.UserRole)
            target_account = self.archive_manager._find_account_by_id(target_id)
            if not target_account:
                return None, None, "账号不存在"
            return target_account, target_id, None

        available_profiles = self.archive_manager.get_accounts_with_local_profiles()
        if not available_profiles:
            return None, None, "没有找到任何本地账号数据。"

        active_account = self.archive_manager.get_active_data_account()
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

        current = self.archive_manager.get_current_account()
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

        profile_ok, profile_path = self.archive_manager.load_local_profile(target_id)
        if not profile_ok:
            self._show_message_box(QMessageBox.Warning, "提示", f"账号「{target_account.get('name', '未知')}」暂无本地数据。\n请先保存该账号本地数据，或读取该账号存档。")
            return

        normalize_ok, normalized_path = self.archive_manager.ensure_local_profile_normalized(target_id, profile_path)
        if not normalize_ok:
            self._show_message_box(QMessageBox.Critical, "错误", f"本地账号数据迁移失败：{normalized_path}")
            return
        profile_path = normalized_path

        active_account = self.archive_manager.get_active_data_account()
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

        save_ok, save_result = self.archive_manager.save_local_profile(active_account['id'])
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
            self.archive_manager.db = self.parent_window.db
            self.archive_manager.set_active_data_account(target_id)
            self.archive_manager.switch_account(target_id)
            self.load_accounts_to_list()
            self.lbl_archive_status.setText(f"✅ 已应用本地账号：{target_account.get('name', '未知')}")
            self._show_message_box(QMessageBox.Information, "成功", f"已应用本地账号：{target_account.get('name', '未知')}")
        else:
            self._show_message_box(QMessageBox.Critical, "错误", f"应用本地账号失败：{result}")

    def save_current_data_to_archive(self):
        """保存当前账号数据到本地存档。"""
        current = self.archive_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先添加并切换到要保存的账号")
            return
        if not self.archive_manager.get_data_root():
            self._show_message_box(QMessageBox.Warning, "提示", "请先设置存档母文件夹")
            return

        if self.parent_window and hasattr(self.parent_window, 'ensure_archive_account_allowed'):
            if not self.parent_window.ensure_archive_account_allowed(current):
                return
        else:
            active_account = self.archive_manager.get_active_data_account()
            if active_account and active_account.get('id') != current.get('id'):
                self._show_message_box(
                    QMessageBox.Warning,
                    "账号不一致，已取消保存",
                    f"当前表格数据属于账号：{active_account.get('name', '未知')}\n"
                    f"你当前选择的存档账号：{current.get('name', '未知')}\n\n"
                    f"为避免覆盖错误存档，本次保存已取消。"
                )
                return
            if not active_account:
                reply = self._show_question_box(
                    "确认数据归属账号",
                    f"当前本地表格数据还没有绑定存档账号。\n\n"
                    f"是否确认这份本地数据属于账号：{current.get('name', '未知')}？"
                )
                if reply != QMessageBox.Yes:
                    return
                self.archive_manager.set_active_data_account(current['id'])

        reply = self._show_question_box("确认保存", f"将保存当前数据到本地存档。\n\n账号：{current.get('name', '未知')}\n是否继续？")
        if reply != QMessageBox.Yes:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(30)
        self.lbl_archive_status.setText("正在保存到存档...")

        try:
            success, result = self.archive_manager.save_local_profile(current['id'])
            if success:
                self.archive_manager.update_last_save_time(current['id'])
                self.progress_bar.setValue(100)
                self.lbl_archive_status.setText("✅ 保存成功")
                self._show_message_box(QMessageBox.Information, "成功", f"数据已保存到本地存档。\n\n账号：{current['name']}\n路径：{result}")
                self.update_archive_info()
            else:
                self._show_message_box(QMessageBox.Critical, "错误", f"保存失败：{result}")

        except Exception as e:
            self._show_message_box(QMessageBox.Critical, "错误", f"保存异常：{str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.progress_bar.setVisible(False)
            self.load_accounts_to_list()

    def read_current_data_from_archive(self):
        """从本地存档读取当前账号数据。"""
        current = self.archive_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先选择要读取的账号")
            return
        if not self.archive_manager.get_data_root():
            self._show_message_box(QMessageBox.Warning, "提示", "请先设置存档母文件夹")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(20)
        self.lbl_archive_status.setText("正在检查本地存档...")

        try:
            profile_ok, profile_path = self.archive_manager.load_local_profile(current['id'])
            if not profile_ok:
                self.progress_bar.setVisible(False)
                self._show_message_box(QMessageBox.Warning, "提示", f"该账号没有本地存档：{profile_path}")
                return

            active_account = self.archive_manager.get_active_data_account()
            if not active_account:
                reply = self._show_question_box(
                    "确认当前数据归属",
                    f"当前主表格数据还没有绑定本地账号。\n\n"
                    f"是否确认当前主表格数据属于账号：{current.get('name', '未知')}？\n"
                    f"确认后会先保存读取前备份，再读取存档。"
                )
                if reply != QMessageBox.Yes:
                    self.progress_bar.setVisible(False)
                    return
                if not self.archive_manager.set_active_data_account(current['id']):
                    self.progress_bar.setVisible(False)
                    self._show_message_box(QMessageBox.Critical, "错误", "绑定当前数据归属账号失败")
                    return
                active_account = current

            reply = self._show_question_box(
                "确认读取存档",
                f"读取存档将切换当前主表格数据！\n\n"
                f"当前主表格属于：{active_account.get('name', '未知')}\n"
                f"将读取账号：{current.get('name', '未知')}\n\n"
                f"读取前会先保留一个当前账号备份。是否继续？"
            )
            if reply != QMessageBox.Yes:
                self.progress_bar.setVisible(False)
                return

            self.lbl_archive_status.setText("正在保存读取前备份...")
            backup_ok, backup_result = self.archive_manager.save_local_backup_before_read(active_account['id'])
            if not backup_ok:
                self.progress_bar.setVisible(False)
                self._show_message_box(QMessageBox.Critical, "读取已取消", f"当前账号读取前备份失败，已取消读取：{backup_result}")
                return

            self.progress_bar.setValue(30)
            self.lbl_archive_status.setText("正在读取本地存档...")

            self.progress_bar.setValue(50)
            if self.parent_window and hasattr(self.parent_window, 'replace_database_from_local_profile'):
                ok, result = self.parent_window.replace_database_from_local_profile(profile_path, current['id'])
            else:
                ok, result = False, "主窗口不支持读取本地存档"

            if ok:
                self.archive_manager.update_last_read_time(current['id'])
                self.archive_manager.set_active_data_account(current['id'])
                self.archive_manager.switch_account(current['id'])
                self.progress_bar.setValue(100)
                self.lbl_archive_status.setText("✅ 读取成功")
                if self.parent_window and hasattr(self.parent_window, 'show_toast'):
                    self.parent_window.show_toast(f"✅ 已读取存档：{current.get('name', '未知')}")
                self.update_archive_info()
                if self.parent_window and hasattr(self.parent_window, 'update_archive_account_label'):
                    self.parent_window.update_archive_account_label()
            else:
                self._show_message_box(QMessageBox.Critical, "错误", f"读取存档失败：{result}")

        except Exception as e:
            self._show_message_box(QMessageBox.Critical, "错误", f"读取异常：{str(e)}")
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


__all__ = ["ArchiveManager", "ArchiveDialog"]

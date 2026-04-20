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
        if column_name in ('image_data', 'image', 'thumbnail', 'icon'):
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

    def _get_accounts_file_path(self):
        """获取账号配置文件路径"""
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "cloud_accounts.json")

    def _load_accounts(self):
        """加载账号列表"""
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.accounts = data.get('accounts', [])
                    self.current_account_id = data.get('current_account')
                    if self.current_account_id:
                        self.current_account = self._find_account_by_id(self.current_account_id)
            except Exception as e:
                print(f"加载账号文件失败: {e}")
                self.accounts = []
                self.current_account_id = None
                self.current_account = None
        else:
            self.accounts = []
            self.current_account_id = None
            self.current_account = None

    def _save_accounts(self):
        """保存账号列表到文件"""
        try:
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'accounts': self.accounts,
                    'current_account': self.current_account_id
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存账号文件失败: {e}")

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

    def _get_base_dir(self):
        """获取基础目录"""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

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
                    spec_code = item.get('spec_code')
                    cost_price = item.get('cost_price', 0)
                    self.db.safe_execute(
                        "INSERT OR REPLACE INTO cost_library (spec_code, cost_price, spec_name) VALUES (?, ?, ?)",
                        (spec_code, cost_price, item.get('spec_name'))
                    )

            if data.get('imported_orders'):
                for order in data['imported_orders']:
                    self.db.safe_execute(
                        """INSERT OR REPLACE INTO imported_orders
                        (store_id, product_id, spec_code, order_count, import_time, order_date, actual_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (order.get('store_id'), order.get('product_id'), order.get('spec_code'),
                         order.get('order_count', 0), order.get('import_time'), order.get('order_date'),
                         order.get('actual_amount', 0))
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

            self.db.conn.commit()
            return True
        except Exception as e:
            print(f"导入数据失败: {e}")
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

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.cloud_manager = CloudSyncManager(db_manager)
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

        self.btn_sync_upload = QPushButton("⬆️ 上传数据")
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

        self.btn_sync_download = QPushButton("⬇️ 下载数据")
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
            "2. 配置好账号后点击「上传数据」备份到云端\n"
            "3. 在其他设备上添加相同账号，输入COS信息\n"
            "4. 点击「下载数据」同步云端数据到本地\n\n"
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

        for acc in accounts:
            is_current = current and current.get('id') == acc.get('id')
            prefix = "⭐ " if is_current else "  "
            last_upload = acc.get('last_upload_time', '从未')
            item = QListWidgetItem(f"{prefix}{acc.get('name', '未知')} (上传:{last_upload})")
            item.setData(Qt.UserRole, acc.get('id'))
            self.account_list.addItem(item)

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

    def upload_current_data(self):
        """上传当前账号数据"""
        current = self.cloud_manager.get_current_account()
        if not current:
            self._show_message_box(QMessageBox.Warning, "提示", "请先添加并切换到要上传的账号")
            return

        reply = self._show_question_box(
            "确认上传",
            f"上传将覆盖云端存档！\n\n账号：{current.get('name', '未知')}\n是否继续上传？"
        )
        if reply != QMessageBox.Yes:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(20)
        self.lbl_sync_status.setText("正在导出本地数据...")

        try:
            data = self.cloud_manager.export_data_to_json()
            if not data:
                self._show_message_box(QMessageBox.Critical, "错误", "数据导出失败")
                return

            self.progress_bar.setValue(40)
            self.lbl_sync_status.setText("正在保存本地备份...")

            local_ok, local_result = self.cloud_manager.save_local_backup(current['id'])
            if local_ok:
                self.lbl_sync_status.setText(f"本地备份已保存: {local_result}")
            else:
                self.lbl_sync_status.setText(f"本地备份保存失败: {local_result}")

            self.progress_bar.setValue(60)
            self.lbl_sync_status.setText("正在上传到云端...")

            uploader = TencentCOSUploader(
                current['secret_id'],
                current['secret_key'],
                current['bucket'],
                current['region']
            )

            success, result = uploader.upload_json(data, current['folder'])
            if success:
                data_size = len(json.dumps(data, ensure_ascii=False))
                size_mb = data_size / (1024 * 1024)
                self.cloud_manager.update_last_upload_time(current['id'])
                self.progress_bar.setValue(100)
                self.lbl_sync_status.setText(f"✅ 上传成功！({size_mb:.2f} MB)")
                self._show_message_box(QMessageBox.Information, "成功", f"数据已上传到云端并保存本地备份！\n\n账号：{current['name']}\n文件大小：{size_mb:.2f} MB\n云端路径：{result}\n本地备份：{local_result if local_ok else '保存失败'}")
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

            self.progress_bar.setValue(30)
            self.lbl_sync_status.setText("正在下载...")

            data_size = len(json.dumps(result, ensure_ascii=False))
            size_mb = data_size / (1024 * 1024)

            self.progress_bar.setValue(50)

            if self.cloud_manager.import_data_from_json(result):
                self.cloud_manager.update_last_download_time(current['id'])
                local_ok, local_result = self.cloud_manager.save_local_backup(current['id'])
                self.progress_bar.setValue(100)
                self.lbl_sync_status.setText(f"✅ 下载成功！({size_mb:.2f} MB)")
                if self.parent_window and hasattr(self.parent_window, 'show_toast'):
                    self.parent_window.show_toast(f"✅ 下载成功！({size_mb:.2f} MB)")
                else:
                    self.lbl_sync_status.setText(f"✅ 下载成功！({size_mb:.2f} MB) - 数据已导入")
                self.update_sync_info()
                self.update_parent_data()
            else:
                self._show_message_box(QMessageBox.Critical, "错误", "数据导入失败")

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

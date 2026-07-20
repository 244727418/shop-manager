# -*- coding: utf-8 -*-
"""本地存档母文件夹管理。"""
import json
import os
import shutil
import sys
from pathlib import Path


APP_CONFIG_DIR_NAME = "店铺管理软件"
DATA_ROOT_CONFIG_NAME = "data_root.json"
DEFAULT_DATA_ROOT_NAME = "店铺管理数据"


class DataRootManager:
    """管理跨源码版/打包版共享的本地存档母文件夹。"""

    def __init__(self):
        self.config_path = self._config_path()

    @staticmethod
    def app_dir():
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @staticmethod
    def _config_path():
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(appdata, APP_CONFIG_DIR_NAME, DATA_ROOT_CONFIG_NAME)

    def get_data_root(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                root = data.get("data_root")
                if root and os.path.isdir(root):
                    return os.path.abspath(root)
        except Exception:
            pass
        return None

    def set_data_root(self, root_path):
        root = os.path.abspath(root_path)
        self.ensure_structure(root)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"data_root": root}, f, ensure_ascii=False, indent=2)
        return root

    def suggest_existing_data_root(self):
        candidates = [
            os.path.join(self.app_dir(), DEFAULT_DATA_ROOT_NAME),
            os.path.join(os.getcwd(), DEFAULT_DATA_ROOT_NAME),
        ]
        for path in candidates:
            if os.path.isdir(path):
                return os.path.abspath(path)
        return None

    def ensure_structure(self, root_path=None):
        root = root_path or self.get_data_root()
        if not root:
            return None
        os.makedirs(self.common_dir(root), exist_ok=True)
        os.makedirs(self.accounts_dir(root), exist_ok=True)
        return root

    def common_dir(self, root_path=None):
        root = root_path or self.get_data_root()
        return os.path.join(root, "通用数据") if root else None

    def accounts_dir(self, root_path=None):
        root = root_path or self.get_data_root()
        return os.path.join(root, "账号数据") if root else None

    def accounts_config_path(self, root_path=None):
        common = self.common_dir(root_path)
        return os.path.join(common, "账号配置.json") if common else None

    def common_settings_path(self, root_path=None):
        common = self.common_dir(root_path)
        return os.path.join(common, "common_settings.json") if common else None

    def update_settings_path(self, root_path=None):
        common = self.common_dir(root_path)
        return os.path.join(common, "update_settings.json") if common else None

    def account_dir(self, account_name, root_path=None):
        accounts_dir = self.accounts_dir(root_path)
        if not accounts_dir:
            return None
        safe_name = self.safe_account_folder_name(account_name)
        return os.path.join(accounts_dir, safe_name)

    def account_db_path(self, account_name, root_path=None):
        account_dir = self.account_dir(account_name, root_path)
        return os.path.join(account_dir, "data.db") if account_dir else None

    def account_browser_dir(self, account_name, root_path=None):
        account_dir = self.account_dir(account_name, root_path)
        return os.path.join(account_dir, "浏览器数据") if account_dir else None

    def account_read_backup_path(self, account_name, root_path=None):
        account_dir = self.account_dir(account_name, root_path)
        return os.path.join(account_dir, "读取前备份", "backup.db") if account_dir else None

    @staticmethod
    def safe_account_folder_name(name):
        text = str(name or "").strip()
        invalid = '<>:"/\\|?*'
        return "".join("_" if ch in invalid else ch for ch in text) or "未命名账号"

    def ensure_account_dirs(self, account_name, root_path=None):
        account_dir = self.account_dir(account_name, root_path)
        browser_dir = self.account_browser_dir(account_name, root_path)
        if account_dir:
            os.makedirs(account_dir, exist_ok=True)
        if browser_dir:
            os.makedirs(browser_dir, exist_ok=True)
        return account_dir

    def legacy_accounts_files(self):
        manager_dir = os.path.join(self.app_dir(), "manager")
        return [
            os.path.join(manager_dir, "archive_accounts.json"),
        ]

    def load_accounts_data(self, root_path=None):
        path = self.accounts_config_path(root_path)
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        for legacy in self.legacy_accounts_files():
            if not os.path.exists(legacy):
                continue
            try:
                with open(legacy, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception:
                continue
        return {}

    def save_accounts_data(self, data, root_path=None):
        root = root_path or self.get_data_root()
        if not root:
            return False
        self.ensure_structure(root)
        path = self.accounts_config_path(root)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=False, indent=2)
        return True

    def resolve_startup_account(self):
        root = self.get_data_root()
        if not root:
            return None, None
        data = self.load_accounts_data(root)
        accounts = data.get("accounts", []) if isinstance(data, dict) else []
        preferred_ids = [data.get("active_data_account_id"), data.get("current_account")]
        for account_id in preferred_ids:
            if not account_id:
                continue
            for account in accounts:
                if account.get("id") == account_id:
                    db_path = self.account_db_path(account.get("name"), root)
                    if db_path:
                        return account, db_path
        for account in accounts:
            db_path = self.account_db_path(account.get("name"), root)
            if db_path and os.path.exists(db_path):
                return account, db_path
        accounts_dir = self.accounts_dir(root)
        if accounts_dir and os.path.isdir(accounts_dir):
            for data_db in sorted(Path(accounts_dir).glob("*/data.db")):
                return {"name": data_db.parent.name, "id": data_db.parent.name}, str(data_db)
        return None, None

    def migrate_common_files(self, root_path):
        self.ensure_structure(root_path)
        mappings = [
            (os.path.join(self.app_dir(), "manager", "archive_accounts.json"), self.accounts_config_path(root_path)),
            (os.path.join(self.app_dir(), "manager", "config.json"), os.path.join(self.common_dir(root_path), "基础配置.json")),
            (os.path.join(self.app_dir(), "update_settings.json"), self.update_settings_path(root_path)),
        ]
        for src, dst in mappings:
            if src and dst and os.path.exists(src) and not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

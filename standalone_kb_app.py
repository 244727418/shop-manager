# -*- coding: utf-8 -*-
"""
知识库独立管理系统 - 直接打开知识库窗口
"""
import sys
import os
import traceback

def main():
    print(f"[DEBUG] Script dir: {os.path.dirname(os.path.abspath(__file__))}", flush=True)
    
    # 设置路径 - standalone_kb_app.py 在根目录，shop_manager 在子目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    shop_manager_dir = os.path.join(script_dir, 'shop_manager')
    
    if os.path.exists(shop_manager_dir):
        sys.path.insert(0, shop_manager_dir)
        sys.path.insert(0, os.path.join(shop_manager_dir, 'dialogs'))
        sys.path.insert(0, os.path.join(shop_manager_dir, 'rag'))
        sys.path.insert(0, os.path.join(shop_manager_dir, 'icons'))
        sys.path.insert(0, os.path.join(shop_manager_dir, 'widgets'))
        print(f"[DEBUG] Added shop_manager paths: {shop_manager_dir}", flush=True)
    else:
        print(f"[DEBUG] shop_manager not found at: {shop_manager_dir}", flush=True)
    
    # 延迟导入 Qt 相关模块
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    # 导入并初始化数据库
    print("[DEBUG] Importing db...", flush=True)
    from db import SafeDatabaseManager
    print("[DEBUG] Creating db...", flush=True)
    db = SafeDatabaseManager()
    
    # 显示知识库
    print("[DEBUG] Importing KnowledgeBaseDialog...", flush=True)
    from dialogs.knowledge_base import KnowledgeBaseDialog
    
    print("[DEBUG] Creating dialog...", flush=True)
    dialog = KnowledgeBaseDialog(db, None)
    # 使用标准Windows窗口（带最小化、最大化、关闭按钮）
    dialog.setWindowFlags(Qt.Window)
    dialog.show()
    
    print("[DEBUG] Starting event loop...", flush=True)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

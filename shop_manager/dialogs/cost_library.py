# -*- coding: utf-8 -*-
"""成本库管理对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableView, QMessageBox, QHeaderView, QAbstractItemView
)
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt


class CostLibraryDialog(QDialog):
    """查看和管理成本库对话框"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("📦 成本库管理")
        self.resize(600, 400)
        try:
            self.init_ui()
            self.load_data()
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            QMessageBox.critical(self, "严重错误", f"打开成本库窗口失败:\n{str(e)}\n\n请检查控制台详情。")
            self.reject()

    def init_ui(self):
        self.model = QStandardItemModel()
        layout = QVBoxLayout(self)
        self._debug_cl_label = QLabel("【板块:成本库对话框\n文件:cost_library.py】规格编码/成本价/搜索/导入导出")
        self._debug_cl_label.setStyleSheet("background-color: #F0E68C; color: #000; font-weight: bold; padding: 1px;")
        self._debug_cl_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._debug_cl_label)
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 搜索规格编码:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入规格编码关键字...")
        self.search_input.textChanged.connect(self.load_data)
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self.load_data)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_refresh)
        layout.addLayout(search_layout)
        self.table_view = QTableView()
        self.model.setHorizontalHeaderLabels(["规格编码 (Spec Code)", "成本价 (Cost Price)"])
        self.table_view.setModel(self.model)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.table_view)
        btn_layout = QHBoxLayout()
        self.lbl_count = QLabel("共 0 条数据")
        btn_del = QPushButton("🗑️ 删除选中项")
        btn_del.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
        btn_del.clicked.connect(self.delete_selected)
        btn_clear = QPushButton("🧹 清空成本库")
        btn_clear.setStyleSheet("background-color: #fd7e14; color: white; font-weight: bold;")
        btn_clear.clicked.connect(self.clear_all)
        btn_close = QPushButton("❌ 关闭")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_clear)
        btn_layout.addWidget(btn_del)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def load_data(self):
        try:
            self.model.setRowCount(0)
            keyword = self.search_input.text().strip()
            if keyword:
                query = "SELECT spec_code, cost_price FROM cost_library WHERE spec_code LIKE ? ORDER BY spec_code"
                params = (f"%{keyword}%",)
            else:
                query = "SELECT spec_code, cost_price FROM cost_library ORDER BY spec_code"
                params = ()
            rows = self.db.safe_fetchall(query, params)
            if not rows:
                self.lbl_count.setText("共 0 条数据")
                return
            for row_data in rows:
                spec_code = str(row_data[0]) if row_data[0] is not None else ""
                cost_price = f"{float(row_data[1]):.2f}" if row_data[1] is not None else "0.00"
                row_index = self.model.rowCount()
                self.model.insertRow(row_index)
                self.model.setItem(row_index, 0, QStandardItem(spec_code))
                self.model.setItem(row_index, 1, QStandardItem(cost_price))
            self.lbl_count.setText(f"共 {self.model.rowCount()} 条数据")
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.lbl_count.setText("加载失败")

    def delete_selected(self):
        try:
            indexes = self.table_view.selectedIndexes()
            if not indexes:
                QMessageBox.warning(self, "提示", "请先选中要删除的行！")
                return
            rows = sorted(list(set(index.row() for index in indexes)), reverse=True)
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除选中的 {len(rows)} 条数据吗？\n此操作不可恢复！",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                count = 0
                for row in rows:
                    item = self.model.item(row, 0)
                    if item:
                        self.db.safe_execute("DELETE FROM cost_library WHERE spec_code=?", (item.text(),))
                        count += 1
                QMessageBox.information(self, "成功", f"已删除 {count} 条数据。")
                self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", f"删除过程中出错：{str(e)}")

    def clear_all(self):
        try:
            reply = QMessageBox.question(
                self, "确认清空",
                "确定要清空整个成本库吗？\n此操作不可恢复！",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.db.safe_execute("DELETE FROM cost_library")
                QMessageBox.information(self, "成功", "成本库已清空！")
                self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "清空失败", f"清空过程中出错：{str(e)}")

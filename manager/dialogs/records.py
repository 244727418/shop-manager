# -*- coding: utf-8 -*-
"""操作记录、每日记录对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QMessageBox, QLineEdit, QTextEdit, QDateEdit, QFrame
)
from PyQt5.QtCore import QDate, Qt

try:
    from ..widgets import RecordRow
except ImportError:
    from widgets import RecordRow


class OperationRecordDialog(QDialog):
    """操作记录弹窗编辑对话框"""
    def __init__(self, records, prod_id, prod_code, year, month, day, save_callback, parent=None):
        super().__init__(parent)
        self.records = records
        self.prod_id = prod_id
        self.prod_code = prod_code
        self.year = year
        self.month = month
        self.day = day
        self.save_callback = save_callback
        self.rows = []

        self.setWindowTitle(f"编辑操作记录 - {year}年{month:02d}月{day:02d}日")
        self.resize(500, 400)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)


        self._debug_ord_label = QLabel("【板块:操作记录对话框\n文件:records.py】商品ID/日期/操作列表/添加删除")
        self._debug_ord_label.setStyleSheet("background-color: #87CEEB; color: #000; font-weight: bold; padding: 1px;")
        self._debug_ord_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        main_layout.addWidget(self._debug_ord_label)

        info_label = QLabel(f"商品ID: {self.prod_code} | 日期: {self.year}年{self.month:02d}月{self.day:02d}日")
        info_label.setStyleSheet("font-weight: bold; color: #333; padding: 5px;")
        main_layout.addWidget(info_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.scroll_widget)

        for rec in self.records:
            self.add_row(rec.get("time", ""), rec.get("text", ""))
        if not self.records:
            self.add_row()

        main_layout.addWidget(self.scroll)

        bottom_layout = QHBoxLayout()
        btn_add = QPushButton("+ 加一行")
        btn_add.clicked.connect(lambda: self.add_row())
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 6px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 6px 20px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a6268; }
        """)
        btn_cancel.clicked.connect(self.reject)

        bottom_layout.addWidget(btn_add)
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_cancel)

        main_layout.addLayout(bottom_layout)

    def add_row(self, time_str="", text=""):
        row = RecordRow(time_str, text)
        self.scroll_layout.addWidget(row)
        self.rows.append(row)

    def save(self):
        data = []
        for row in self.rows:
            try:
                row_data = row.get_data()
                if row_data and row_data.get("text"):
                    data.append(row_data)
            except Exception:
                continue

        self.save_callback(data)
        self.accept()


class DailyRecordDialog(QDialog):
    """每日记录对话框 - 记录店铺每天的信息"""
    def __init__(self, store_id, store_name, main_app, parent=None):
        super().__init__(parent)
        self.store_id = store_id
        self.store_name = store_name
        self.main_app = main_app
        self.db = main_app.db

        self.setWindowTitle(f"📝 每日记录 - {store_name}")
        self.resize(700, 600)
        self.init_ui()
        self.load_today_record()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        self._debug_drd_label = QLabel("【板块:日报记录对话框\n文件:records.py】日期选择/操作记录/历史查看")
        self._debug_drd_label.setStyleSheet("background-color: #DDA0DD; color: #000; font-weight: bold; padding: 1px; font-size: 13px;")
        self._debug_drd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        main_layout.addWidget(self._debug_drd_label)

        header = QLabel(f"📝 每日记录 - {self.store_name}")
        header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; color: #2c3e50;")
        main_layout.addWidget(header)

        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("📅 记录日期:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.dateChanged.connect(self.on_date_changed)
        date_layout.addWidget(self.date_edit)
        date_layout.addStretch()
        main_layout.addLayout(date_layout)

        category_label = QLabel("📂 类目信息:")
        category_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(category_label)

        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("例如: 女装/零食/数码配件等")
        main_layout.addWidget(self.category_edit)

        special_label = QLabel("⚠️ 特殊情况记录:")
        special_label.setStyleSheet("font-weight: bold;")
        main_layout.addWidget(special_label)

        self.special_edit = QTextEdit()
        self.special_edit.setPlaceholderText("记录店铺当天的特殊情况，如: 促销活动、异常订单、库存问题、客服问题等")
        self.special_edit.setMaximumHeight(120)
        main_layout.addWidget(self.special_edit)

        prompt_label = QLabel("💡 通用指导提示词 (应用于所有AI功能):")
        prompt_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        main_layout.addWidget(prompt_label)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("输入店铺运营指导大纲...")
        self.prompt_edit.setMaximumHeight(150)
        main_layout.addWidget(self.prompt_edit)

        prompt_hint = QLabel("💡 提示: 此提示词具有最高优先级，会自动附加到所有AI调用的系统提示中")
        prompt_hint.setStyleSheet("color: #7f8c8d; font-size: 11px; padding: 5px;")
        main_layout.addWidget(prompt_hint)

        btn_layout = QHBoxLayout()
        self.btn_history = QPushButton("📋 查看历史记录")
        self.btn_history.clicked.connect(self.show_history)
        btn_layout.addWidget(self.btn_history)
        btn_layout.addStretch()
        self.btn_save = QPushButton("💾 保存记录")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #219a52; }
        """)
        self.btn_save.clicked.connect(self.save_record)
        btn_layout.addWidget(self.btn_save)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)

    def on_date_changed(self):
        self.load_today_record()

    def load_today_record(self):
        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        category, special_info, memo = self.db.get_daily_record(self.store_id, record_date)
        self.category_edit.setText(category or "")
        self.special_edit.setPlainText(special_info or "")
        self.prompt_edit.setPlainText(memo or "")

    def save_record(self):
        record_date = self.date_edit.date().toString("yyyy-MM-dd")
        category = self.category_edit.text().strip()
        special_info = self.special_edit.toPlainText().strip()
        prompt_text = self.prompt_edit.toPlainText().strip()
        self.db.save_daily_record(self.store_id, record_date, category, special_info, prompt_text)
        self.db.save_store_prompt(self.store_id, prompt_text)
        QMessageBox.information(self, "✅ 保存成功", f"每日记录已保存到 {record_date}")
        self.main_app.show_toast("✅ 每日记录已保存")

    def show_history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"📋 历史记录 - {self.store_name}")
        dialog.resize(600, 500)
        layout = QVBoxLayout(dialog)
        records = self.db.get_store_daily_records(self.store_id, 30)
        if not records:
            QMessageBox.information(self, "提示", "暂无历史记录")
            return
        label = QLabel(f"共 {len(records)} 条历史记录:")
        layout.addWidget(label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        for record_date, category, special_info, memo in records:
            record_widget = QWidget()
            record_layout = QVBoxLayout(record_widget)
            date_label = QLabel(f"📅 {record_date}")
            date_label.setStyleSheet("font-weight: bold; color: #2980b9;")
            record_layout.addWidget(date_label)
            if category:
                record_layout.addWidget(QLabel(f"📂 类目: {category}"))
            if special_info:
                record_layout.addWidget(QLabel(f"⚠️ 特殊情况: {special_info}"))
            if memo:
                memo_label = QLabel(f"💡 提示词: {memo[:100]}{'...' if len(memo) > 100 else ''}")
                memo_label.setWordWrap(True)
                memo_label.setStyleSheet("color: #7f8c8d;")
                record_layout.addWidget(memo_label)
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setStyleSheet("color: #ddd;")
            record_layout.addWidget(separator)
            scroll_layout.addWidget(record_widget)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.exec_()

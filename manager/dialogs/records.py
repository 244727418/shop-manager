# -*- coding: utf-8 -*-
"""操作记录、每日记录对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QMessageBox, QLineEdit, QTextEdit, QDateEdit, QFrame,
    QTimeEdit, QCheckBox, QSizePolicy
)
from PyQt5.QtCore import QDate, Qt, QTime, QTimer
from PyQt5.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QTextOption
from html import escape
import re


METRIC_STYLES = {
    "规格售价": ("#e8f4ff", "#1f6fb2"),
    "规格新增": ("#e8f8ef", "#1e8449"),
    "规格删除": ("#fdecea", "#c0392b"),
    "规格名称": ("#f3e8ff", "#7d3c98"),
    "优惠券": ("#fff3cd", "#b7791f"),
    "新客立减": ("#fce4ec", "#ad1457"),
    "投产": ("#e8f0fe", "#2f5fb3"),
    "成交出价": ("#e0f7fa", "#00838f"),
    "退货率": ("#fff0e6", "#d35400"),
    "推广模式": ("#eceff1", "#455a64"),
    "投产/出价模式": ("#e8f0fe", "#2f5fb3"),
    "主轮播图": ("#e8f5e9", "#2e7d32"),
    "限时限量购": ("#fdecea", "#c0392b"),
    "营销活动": ("#f3e8ff", "#7d3c98"),
    "综合毛利": ("#e8f8ef", "#1e8449"),
    "商品标题": ("#fff7e6", "#a35f00"),
    "新建链接": ("#e8f8ef", "#1e8449"),
}


class SpecNameHighlighter(QSyntaxHighlighter):
    """Bold spec names inside editable operation-record text without changing saved plain text."""
    def __init__(self, document, terms=None):
        super().__init__(document)
        self.terms = [str(term).strip() for term in (terms or []) if str(term).strip()]
        self.spec_format = QTextCharFormat()
        self.spec_format.setFontWeight(QFont.Bold)

    def highlightBlock(self, text):
        for match in re.finditer(r"\[[^\]]+\]", text):
            self.setFormat(match.start(), match.end() - match.start(), self.spec_format)
        for term in self.terms:
            for match in re.finditer(re.escape(term), text):
                self.setFormat(match.start(), match.end() - match.start(), self.spec_format)


class OperationRecordDialog(QDialog):
    """操作记录弹窗编辑对话框"""
    def __init__(self, records, prod_id, prod_code, year, month, day, save_callback, parent=None, store_id=None, store_name=None):
        super().__init__(parent)
        self.records = records
        self.prod_id = prod_id
        self.prod_code = prod_code
        self.year = year
        self.month = month
        self.day = day
        self.save_callback = save_callback
        self.store_id = store_id
        self.store_name = store_name
        self.rows = []

        self.setWindowTitle(f"编辑操作记录 - {year}年{month:02d}月{day:02d}日")
        self.resize(1100, 720)
        self.setMinimumSize(900, 580)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 8, 10, 10)

        debug_label = QLabel("🔧 调试: records.py (OperationRecordDialog)")
        debug_label.setFixedHeight(16)
        debug_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        debug_label.setStyleSheet("font-size: 9px; color: #999; background-color: #f4f4f4; padding: 1px 6px; border: 1px solid #e5e5e5;")
        debug_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        debug_label.setCursor(Qt.IBeamCursor)
        main_layout.addWidget(debug_label)

        add_panel = QFrame()
        add_panel.setFrameShape(QFrame.StyledPanel)
        add_panel.setStyleSheet("""
            QFrame {
                background: #f8fafc;
                border: 1px solid #d9e2ec;
                border-radius: 4px;
            }
            QLabel {
                border: none;
                background: transparent;
                color: #34495e;
                font-weight: bold;
            }
        """)
        add_layout = QVBoxLayout(add_panel)
        add_layout.setContentsMargins(10, 8, 10, 8)
        add_layout.setSpacing(6)

        add_title = QLabel("新增操作记录")
        add_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50; border: none; background: transparent;")
        add_layout.addWidget(add_title)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        input_layout.addWidget(QLabel("时间"))
        self.new_time_edit = QTimeEdit()
        self.new_time_edit.setDisplayFormat("HH:mm")
        self.new_time_edit.setTime(QTime.currentTime())
        self.new_time_edit.setFixedWidth(70)
        input_layout.addWidget(self.new_time_edit)

        input_layout.addWidget(QLabel("内容"))
        self.new_text_edit = QTextEdit()
        self.new_text_edit.setPlaceholderText("输入本次操作记录...")
        self.new_text_edit.setMinimumHeight(56)
        self.new_text_edit.setMaximumHeight(80)
        self.new_text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.new_text_edit.setStyleSheet("""
            QTextEdit {
                border: 1px solid #b8c7d6;
                border-radius: 4px;
                background: white;
                color: #2c3e50;
                font-size: 13px;
                padding: 5px;
            }
            QTextEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        self._new_spec_highlighter = SpecNameHighlighter(self.new_text_edit.document())
        input_layout.addWidget(self.new_text_edit, 1)

        self.chk_task = QCheckBox("任务")
        self.chk_reminder = QCheckBox("提醒")
        input_layout.addWidget(self.chk_task)
        input_layout.addWidget(self.chk_reminder)

        self.reminder_date = QDateEdit()
        self.reminder_date.setCalendarPopup(True)
        self.reminder_date.setDate(QDate.currentDate().addDays(1))
        self.reminder_date.setDisplayFormat("yyyy-MM-dd")
        self.reminder_date.setFixedWidth(110)
        self.reminder_date.setVisible(False)
        input_layout.addWidget(self.reminder_date)

        self.reminder_time = QTimeEdit()
        self.reminder_time.setDisplayFormat("HH:mm")
        self.reminder_time.setTime(QTime.currentTime())
        self.reminder_time.setFixedWidth(70)
        self.reminder_time.setVisible(False)
        input_layout.addWidget(self.reminder_time)
        self.chk_reminder.stateChanged.connect(self._toggle_reminder_inputs)

        btn_add = QPushButton("+ 添加")
        btn_add.setFixedWidth(76)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        btn_add.clicked.connect(self.add_new_record_from_input)
        input_layout.addWidget(btn_add)

        add_layout.addLayout(input_layout)
        main_layout.addWidget(add_panel)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)

        manual_panel = QFrame()
        manual_panel.setFrameShape(QFrame.StyledPanel)
        manual_panel.setStyleSheet("QFrame { border: 1px solid #e1e5ea; border-radius: 4px; background: white; }")
        manual_layout = QVBoxLayout(manual_panel)
        manual_layout.setContentsMargins(8, 8, 8, 8)
        manual_layout.setSpacing(6)

        manual_title = QLabel("文字记录区")
        manual_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50; border: none; background: transparent;")
        manual_layout.addWidget(manual_title)

        table_header = QWidget()
        table_header.setStyleSheet("""
            QWidget {
                background: #eef3f8;
                border: 1px solid #cfd9e3;
            }
            QLabel {
                border: none;
                background: transparent;
                color: #34495e;
                font-size: 12px;
                font-weight: bold;
                padding: 5px;
            }
        """)
        header_layout = QHBoxLayout(table_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        time_header = QLabel("时间")
        time_header.setFixedWidth(82)
        content_header = QLabel("记录内容")
        action_header = QLabel("操作")
        action_header.setFixedWidth(58)
        header_layout.addWidget(time_header)
        header_layout.addWidget(content_header, 1)
        header_layout.addWidget(action_header)
        manual_layout.addWidget(table_header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setSpacing(0)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.scroll_widget)
        self.scroll.setMinimumHeight(260)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        for rec in self.records:
            self.add_row(rec.get("time", ""), self._record_edit_text(rec), rec)

        manual_layout.addWidget(self.scroll, 1)
        body_layout.addWidget(manual_panel, 3)

        metric_panel = QFrame()
        metric_panel.setFrameShape(QFrame.StyledPanel)
        metric_panel.setStyleSheet("QFrame { border: 1px solid #e1e5ea; border-radius: 4px; background: #fbfcfe; }")
        metric_layout = QVBoxLayout(metric_panel)
        metric_layout.setContentsMargins(8, 8, 8, 8)
        metric_layout.setSpacing(6)

        metric_title = QLabel("系统指标变化")
        metric_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50; border: none; background: transparent;")
        metric_layout.addWidget(metric_title)

        metric_scroll = QScrollArea()
        metric_scroll.setWidgetResizable(True)
        metric_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        metric_widget = QWidget()
        metric_list = QVBoxLayout(metric_widget)
        metric_list.setContentsMargins(0, 0, 0, 0)
        metric_list.setSpacing(6)
        metric_list.setAlignment(Qt.AlignTop)

        metric_changes = self._collect_metric_changes()
        if metric_changes:
            for change in metric_changes:
                metric_list.addWidget(self._create_metric_card(change))
        else:
            empty = QLabel("暂无系统指标变化")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #95a5a6; padding: 30px; border: none; background: transparent;")
            metric_list.addWidget(empty)

        metric_scroll.setWidget(metric_widget)
        metric_layout.addWidget(metric_scroll, 1)
        body_layout.addWidget(metric_panel, 2)

        main_layout.addLayout(body_layout, 1)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        btn_save = QPushButton("💾 保存")
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 5px 20px;
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
                padding: 5px 20px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a6268; }
        """)
        btn_cancel.clicked.connect(self.reject)

        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_cancel)

        main_layout.addLayout(bottom_layout)

    def _toggle_reminder_inputs(self, state):
        visible = state == Qt.Checked
        self.reminder_date.setVisible(visible)
        self.reminder_time.setVisible(visible)

    def add_new_record_from_input(self):
        text = self.new_text_edit.toPlainText().strip()
        if not text:
            return
        row = self.add_row(self.new_time_edit.time().toString("HH:mm"), text)
        row.pending_task = self.chk_task.isChecked()
        row.pending_reminder = self.chk_reminder.isChecked()
        if row.pending_reminder:
            row.pending_reminder_datetime = f"{self.reminder_date.date().toString('yyyy-MM-dd')} {self.reminder_time.time().toString('HH:mm')}"
        self.new_text_edit.clear()
        self.chk_task.setChecked(False)
        self.chk_reminder.setChecked(False)
        self.new_time_edit.setTime(QTime.currentTime())
        QTimer.singleShot(0, lambda: self.scroll.ensureWidgetVisible(row, 0, 12))

    def add_row(self, time_str="", text="", original_record=None):
        row = OperationRecordRow(time_str, text, original_record, self._record_spec_terms(original_record))
        self.scroll_layout.addWidget(row)
        self.rows.append(row)
        return row

    def _record_spec_terms(self, record):
        terms = []
        if not isinstance(record, dict):
            return terms
        for change in record.get("changes", []) or []:
            if not isinstance(change, dict):
                continue
            spec_text, _cleaned = self._extract_spec_text(change.get("metric", ""), change.get("text", ""), change)
            if spec_text:
                terms.append(spec_text)
        return terms

    def _record_edit_text(self, record):
        changes = record.get("changes") if isinstance(record, dict) else None
        if not changes:
            return record.get("text", "") if isinstance(record, dict) else ""
        lines = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            text = str(change.get("text", "") or "").strip()
            if not text:
                metric = str(change.get("metric", "") or "").strip()
                old_value = str(change.get("old", "") or "").strip()
                new_value = str(change.get("new", "") or "").strip()
                text = f"{metric}: {old_value} -> {new_value}".strip()
            if text:
                lines.append(text)
        return "\n".join(lines) if lines else record.get("text", "")

    def _collect_metric_changes(self):
        changes = []
        for rec in self.records:
            for change in rec.get("changes", []) or []:
                item = dict(change)
                item.setdefault("time", rec.get("time", ""))
                changes.append(item)
        return changes

    def _create_metric_card(self, change):
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #dfe6ee;
                border-radius: 4px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(5)

        time_label = self._create_pill_label(change.get("time", ""), "#eef2f7", "#34495e")
        metric = change.get("metric", "指标变化")
        metric_bg, metric_fg = self._metric_colors(metric)
        metric_label = self._create_pill_label(metric, metric_bg, metric_fg)
        top_row.addWidget(time_label)
        top_row.addWidget(metric_label)

        spec_text, cleaned_text = self._extract_spec_text(metric, change.get("text", ""), change)
        top_row.addStretch()
        layout.addLayout(top_row)

        if spec_text:
            spec_label = QLabel(f"规格：<b>{escape(str(spec_text))}</b>")
            spec_label.setWordWrap(True)
            spec_label.setTextFormat(Qt.RichText)
            spec_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            spec_label.setToolTip(spec_text)
            spec_label.setStyleSheet(
                "background: #e9f2ff; color: #245269; border-radius: 4px; "
                "padding: 5px 7px; font-size: 12px; font-weight: normal;"
            )
            layout.addWidget(spec_label)

        old_value = change.get("old", "")
        new_value = change.get("new", "")
        if old_value != "" or new_value != "":
            value = QLabel(f"{old_value}  ->  {new_value}")
            value.setStyleSheet("font-size: 12px; color: #6f42c1; font-weight: bold; background: #f8f3ff; border-radius: 3px; padding: 4px 6px;")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(value)

        text = QLabel(cleaned_text or change.get("text", ""))
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text.setToolTip(change.get("text", ""))
        text.setStyleSheet("font-size: 12px; color: #2c3e50; line-height: 1.35; padding: 1px 2px;")
        layout.addWidget(text)
        return card

    def _metric_colors(self, metric):
        for key, colors in METRIC_STYLES.items():
            if key in str(metric or ""):
                return colors
        return "#edf2f7", "#34495e"

    def _create_pill_label(self, text, bg, fg):
        label = QLabel(str(text or ""))
        label.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 4px; "
            "padding: 3px 7px; font-size: 12px; font-weight: bold;"
        )
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        return label

    def _extract_spec_text(self, metric, text, change):
        metric = str(metric or "")
        text = str(text or "")
        if "规格" not in metric and "规格" not in text:
            return "", text

        bracket_matches = re.findall(r"\[([^\]]{1,120})\]", text)
        if bracket_matches:
            spec = bracket_matches[0].strip()
            cleaned = re.sub(r"\s*\[[^\]]{1,120}\]\s*", " ", text, count=1).strip()
            return spec, cleaned

        old_value = str(change.get("old", "") or "").strip()
        new_value = str(change.get("new", "") or "").strip()
        if metric == "规格名称" and (old_value or new_value):
            return (new_value or old_value), "规格名称已修改"

        for pattern in (
            r"^(.{1,120}?)(?:售价设置为|设置售价到|从.+?(?:涨价到|降价到))",
            r"^(?:新增规格|删除规格)\s*[:：]?\s*(.{1,120})$",
        ):
            match = re.search(pattern, text)
            if match:
                spec = match.group(1).strip()
                cleaned = text.replace(spec, "", 1).strip()
                return spec, cleaned
        return "", text

    def save(self):
        data = []
        task_list = []
        reminder_list = []

        for row in self.rows:
            try:
                row_data = row.get_data()
                if row_data and row_data.get("text"):
                    record = {"time": row_data.get("time", ""), "text": row_data.get("text", "")}
                    if row_data.get("history_id"):
                        record["history_id"] = row_data.get("history_id")
                    if row_data.get("changes"):
                        record["changes"] = row_data.get("changes")
                    data.append(record)

                    if row_data.get("add_task"):
                        task_list.append(row_data.get("text", ""))

                    if row_data.get("add_reminder"):
                        reminder_list.append({
                            "text": row_data.get("text", ""),
                            "datetime": row_data.get("reminder_datetime", "")
                        })
            except Exception:
                continue

        self.save_callback(data)

        if task_list or reminder_list:
            try:
                from datetime import datetime
                created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for task_text in task_list:
                    self.parent().db.safe_execute(
                        """INSERT INTO daily_tasks (store_id, product_id, year, month, day, task_content, created_time)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (self.store_id, self.prod_id, self.year, self.month, self.day, task_text, created_time)
                    )

                for reminder in reminder_list:
                    self.parent().db.safe_execute(
                        """INSERT INTO task_reminders (store_id, product_id, task_content, remind_time, created_time)
                           VALUES (?, ?, ?, ?, ?)""",
                        (self.store_id, self.prod_id, reminder["text"], reminder["datetime"], created_time)
                    )

                if task_list:
                    self.parent().show_toast(f"✅ 已添加 {len(task_list)} 条到每日任务")
                if reminder_list:
                    self.parent().show_toast(f"✅ 已设置 {len(reminder_list)} 个提醒")
                if hasattr(self.parent(), "force_refresh_product_widget"):
                    self.parent().force_refresh_product_widget(self.prod_id)

            except Exception as e:
                print(f"添加任务/提醒失败: {e}")

        self.accept()


class OperationRecordRow(QWidget):
    """操作记录列表中的单条文本记录。"""
    def __init__(self, time_str="", text="", original_record=None, spec_terms=None):
        super().__init__()
        self.original_record = original_record or {}
        self.pending_task = False
        self.pending_reminder = False
        self.pending_reminder_datetime = ""
        self.deleted = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setObjectName("recordRow")
        self.setStyleSheet("""
            QWidget#recordRow {
                background: #ffffff;
                border-left: 1px solid #cfd9e3;
                border-right: 1px solid #cfd9e3;
                border-bottom: 1px solid #cfd9e3;
                border-radius: 0px;
            }
            QTimeEdit {
                border: none;
                border-radius: 0px;
                background: white;
                color: #2c3e50;
                font-size: 13px;
                padding: 6px;
            }
            QTextEdit {
                border: 1px solid #b8c7d6;
                border-radius: 3px;
                background: white;
                color: #2c3e50;
                font-size: 13px;
                padding: 5px;
                margin: 2px 4px;
            }
            QTextEdit:focus {
                border: 1px solid #3498db;
            }
        """)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFixedWidth(82)
        self.time_edit.setAlignment(Qt.AlignCenter)
        parsed_time = QTime.fromString(time_str or "", "HH:mm")
        self.time_edit.setTime(parsed_time if parsed_time.isValid() else QTime.currentTime())
        self.time_edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(self.time_edit, 0, Qt.AlignTop)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setMinimumHeight(44)
        self.text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapAnywhere)
        self.text_edit.document().setDefaultTextOption(text_option)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.text_edit.document().setDocumentMargin(4)
        self._spec_highlighter = SpecNameHighlighter(self.text_edit.document(), spec_terms)
        self.text_edit.textChanged.connect(self.adjust_text_height)
        layout.addWidget(self.text_edit, 1, Qt.AlignTop)

        self.btn_del = QPushButton("删除")
        self.btn_del.setFixedWidth(58)
        self.btn_del.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_del.setStyleSheet("""
            QPushButton {
                border: none;
                background: #e74c3c;
                color: white;
                border-radius: 0px;
                font-size: 12px;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        self.btn_del.clicked.connect(self.mark_deleted)
        layout.addWidget(self.btn_del, 0, Qt.AlignTop)
        QTimer.singleShot(0, self.adjust_text_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.adjust_text_height)

    def adjust_text_height(self):
        if self.deleted:
            return
        document = self.text_edit.document()
        document.setTextWidth(max(1, self.text_edit.viewport().width()))
        height = int(document.size().height()) + 16
        height = max(44, height)
        self.text_edit.setFixedHeight(height)
        self.time_edit.setFixedHeight(height)
        self.btn_del.setFixedHeight(height)
        self.setMinimumHeight(height)
        self.updateGeometry()

    def mark_deleted(self):
        self.deleted = True
        self.hide()
        self.setParent(None)
        self.deleteLater()

    def get_data(self):
        if self.deleted:
            return {}
        text = self.text_edit.toPlainText().strip()
        time_text = self.time_edit.time().toString("HH:mm")
        data = {
            "time": time_text,
            "text": text,
            "add_task": self.pending_task,
            "add_reminder": self.pending_reminder,
        }
        if self.original_record.get("history_id"):
            data["history_id"] = self.original_record.get("history_id")
        if self.pending_reminder:
            data["reminder_datetime"] = self.pending_reminder_datetime
        changes = self.original_record.get("changes")
        if changes:
            synced_changes = []
            for change in changes:
                if isinstance(change, dict):
                    if change.get("type") == "main_carousel_image" and change.get("history_id") and not data.get("history_id"):
                        data["history_id"] = change.get("history_id")
                    synced_change = dict(change)
                    synced_change["time"] = time_text
                    if data.get("history_id") and synced_change.get("type") == "main_carousel_image":
                        synced_change["history_id"] = data.get("history_id")
                    synced_changes.append(synced_change)
                else:
                    synced_changes.append(change)
            data["changes"] = synced_changes
        return data


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

        debug_label = QLabel("🔧 调试: records.py (DailyRecordDialog)")
        debug_label.setStyleSheet("font-size: 10px; color: #999; background-color: #f0f0f0; padding: 2px 8px; border-bottom: 1px solid #ddd;")
        debug_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        debug_label.setCursor(Qt.IBeamCursor)
        main_layout.addWidget(debug_label)

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

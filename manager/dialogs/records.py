# -*- coding: utf-8 -*-
"""操作记录、每日记录对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QMessageBox, QLineEdit, QTextEdit, QDateEdit, QFrame,
    QTimeEdit, QCheckBox, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import QDate, QDateTime, Qt, QTime
from PyQt5.QtGui import QColor
import re

try:
    from ..window_icons import apply_window_icon
except ImportError:
    from window_icons import apply_window_icon


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
    "毛利": ("#e8f8ef", "#1e8449"),
    "净利": ("#e8f8ef", "#1e8449"),
    "商品标题": ("#fff7e6", "#a35f00"),
    "新建链接": ("#e8f8ef", "#1e8449"),
}

METRIC_ABBR = {
    "规格售价": "改价",
    "改价": "改价",
    "规格新增": "新增规格",
    "规格删除": "删除规格",
    "规格名称": "规格名",
    "优惠券": "优惠券",
    "新客立减": "新客立减",
    "投产": "投产",
    "成交出价": "出价",
    "退货率": "退",
    "推广模式": "推广",
    "修改推广": "推广",
    "营销活动": "营销",
    "限时限量购": "限时购",
    "综合毛利": "毛利",
    "毛利": "毛利",
    "净利": "净利",
    "商品标题": "标题",
    "新建链接": "新建链接",
    "操作记录": "记录",
}


class OperationRecordDialog(QDialog):
    """操作记录弹窗编辑对话框"""
    def __init__(
        self, records, prod_id, prod_code, year, month, day, save_callback,
        parent=None, store_id=None, store_name=None, load_callback=None,
        save_with_date=False, title_prefix=None, product_memo="",
        memo_save_callback=None, quick_reminder_callback=None,
    ):
        super().__init__(parent)
        apply_window_icon(self, "record")
        self.records = records
        self.prod_id = prod_id
        self.prod_code = prod_code
        self.year = year
        self.month = month
        self.day = day
        self.save_callback = save_callback
        self.load_callback = load_callback
        self.save_with_date = save_with_date
        self.title_prefix = title_prefix or "编辑操作记录"
        self.product_memo = str(product_memo or "")
        self.memo_save_callback = memo_save_callback
        self.quick_reminder_callback = quick_reminder_callback
        self.store_id = store_id
        self.store_name = store_name
        self.rows = []
        self.week_start_date = self._week_start(QDate(year, month, day))

        self._update_window_title()
        self.resize(980, 620)
        self.setMinimumSize(820, 520)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 8, 10, 10)

        if self.quick_reminder_callback:
            quick_layout = QHBoxLayout()
            quick_layout.addWidget(QLabel("快捷操作"))
            btn_quick_reminder = QPushButton("24小时后提醒")
            btn_quick_reminder.setToolTip("使用当前输入的操作记录内容，立即设置24小时后的提醒。")
            btn_quick_reminder.clicked.connect(self.quick_set_reminder)
            quick_layout.addWidget(btn_quick_reminder)
            quick_layout.addStretch()
            main_layout.addLayout(quick_layout)

        if self.load_callback:
            date_layout = QHBoxLayout()
            date_layout.addWidget(QLabel("记录日期"))
            self.date_edit = QDateEdit()
            self.date_edit.setCalendarPopup(True)
            self.date_edit.setDisplayFormat("yyyy-MM-dd")
            self.date_edit.setDate(QDate(self.year, self.month, self.day))
            self.date_edit.setFixedWidth(130)
            self.date_edit.dateChanged.connect(self.on_record_date_changed)
            date_layout.addWidget(self.date_edit)
            date_layout.addStretch()
            main_layout.addLayout(date_layout)

        if self.memo_save_callback:
            memo_layout = QHBoxLayout()
            memo_label = QLabel("链接备注")
            memo_label.setFixedWidth(70)
            self.memo_edit = QTextEdit()
            self.memo_edit.setPlainText(self.product_memo)
            self.memo_edit.setPlaceholderText("输入长期备注...")
            self.memo_edit.setFixedHeight(30)
            self.memo_edit.setStyleSheet("QTextEdit { padding: 1px; }")
            self.memo_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.memo_edit.setToolTip("长期保留的链接备注，详细导出时会显示。")
            memo_layout.addWidget(memo_label)
            memo_layout.addWidget(self.memo_edit, 1)
            main_layout.addLayout(memo_layout)

        if self.quick_reminder_callback:
            pending_layout = QHBoxLayout()
            pending_label = QLabel("待完成任务")
            pending_label.setFixedWidth(70)
            self.pending_task_edit = QTextEdit()
            self.pending_task_edit.setReadOnly(True)
            self.pending_task_edit.setFixedHeight(64)
            self.pending_task_edit.setStyleSheet(
                "QTextEdit { padding: 1px; background: #fffdf2; border: 1px solid #eadf9a; }"
            )
            pending_layout.addWidget(pending_label)
            pending_layout.addWidget(self.pending_task_edit, 1)
            main_layout.addLayout(pending_layout)
            self.refresh_pending_tasks()

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
        self.new_text_edit = QLineEdit()
        self.new_text_edit.setPlaceholderText("补充一条手动记录...")
        self.new_text_edit.setFixedHeight(30)
        self.new_text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.new_text_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #b8c7d6;
                border-radius: 4px;
                background: white;
                color: #2c3e50;
                font-size: 13px;
                padding: 3px 6px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        self.new_text_edit.returnPressed.connect(self.add_new_record_from_input)
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
        btn_add.setFocusPolicy(Qt.NoFocus)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:focus { outline: none; }
        """)
        btn_add.clicked.connect(self.add_new_record_from_input)
        input_layout.addWidget(btn_add)

        add_layout.addLayout(input_layout)
        main_layout.addWidget(add_panel)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)

        week_panel = QFrame()
        week_panel.setFrameShape(QFrame.StyledPanel)
        week_panel.setStyleSheet("QFrame { border: 1px solid #e1e5ea; border-radius: 4px; background: white; }")
        week_layout = QVBoxLayout(week_panel)
        week_layout.setContentsMargins(8, 8, 8, 8)
        week_layout.setSpacing(6)

        week_bar = QHBoxLayout()
        btn_prev_week = QPushButton("上一周")
        btn_next_week = QPushButton("下一周")
        btn_this_week = QPushButton("本周")
        for btn in (btn_prev_week, btn_next_week, btn_this_week):
            btn.setFocusPolicy(Qt.NoFocus)
        self.week_label = QLabel()
        self.week_label.setAlignment(Qt.AlignCenter)
        self.week_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        btn_prev_week.clicked.connect(lambda: self.change_week(-7))
        btn_next_week.clicked.connect(lambda: self.change_week(7))
        btn_this_week.clicked.connect(self.goto_current_week)
        week_bar.addWidget(btn_prev_week)
        week_bar.addWidget(btn_this_week)
        week_bar.addWidget(btn_next_week)
        week_bar.addWidget(self.week_label, 1)
        week_layout.addLayout(week_bar)

        self.week_table = QTableWidget(0, 7)
        self.week_table.setFocusPolicy(Qt.NoFocus)
        self.week_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.week_table.setSelectionMode(QTableWidget.NoSelection)
        self.week_table.setWordWrap(True)
        self.week_table.verticalHeader().setVisible(False)
        self.week_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.week_table.setStyleSheet("""
            QTableWidget { gridline-color: #d9e2ec; background: white; font-size: 12px; }
            QTableWidget::item:focus { outline: none; }
            QHeaderView::section { background: #eef3f8; color: #34495e; padding: 4px; border: 1px solid #cfd9e3; }
        """)
        self.week_table.cellDoubleClicked.connect(self.show_week_cell_detail)
        week_layout.addWidget(self.week_table, 1)
        body_layout.addWidget(week_panel, 1)

        main_layout.addLayout(body_layout, 1)
        self.refresh_week_table()

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        btn_save = QPushButton("💾 保存")
        btn_save.setFocusPolicy(Qt.NoFocus)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 5px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #218838; }
            QPushButton:focus { outline: none; }
        """)
        btn_save.clicked.connect(self.save)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFocusPolicy(Qt.NoFocus)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 5px 20px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a6268; }
            QPushButton:focus { outline: none; }
        """)
        btn_cancel.clicked.connect(self.reject)

        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_cancel)

        main_layout.addLayout(bottom_layout)

    def on_record_date_changed(self):
        if not self.load_callback:
            return
        qdate = self.date_edit.date()
        self.year, self.month, self.day = qdate.year(), qdate.month(), qdate.day()
        self.week_start_date = self._week_start(qdate)
        self._update_window_title()
        self.reload_records(self.load_callback(self.year, self.month, self.day) or [])

    def _update_window_title(self):
        self.setWindowTitle(f"{self.title_prefix} - {self.year}-{self.month:02d}-{self.day:02d}")

    def reload_records(self, records):
        self.records = records or []
        self.refresh_week_table()

    def _week_start(self, qdate):
        return qdate.addDays(1 - qdate.dayOfWeek())

    def change_week(self, days):
        self.week_start_date = self.week_start_date.addDays(days)
        self.refresh_week_table()

    def goto_current_week(self):
        today = QDate.currentDate()
        self.week_start_date = self._week_start(today)
        self.year, self.month, self.day = today.year(), today.month(), today.day()
        self.reload_records(self.load_callback(self.year, self.month, self.day) if self.load_callback else self.records)

    def refresh_week_table(self):
        if not hasattr(self, "week_table"):
            return
        days = [self.week_start_date.addDays(i) for i in range(7)]
        self.week_label.setText(f"{days[0].toString('yyyy-MM-dd')}  至  {days[-1].toString('yyyy-MM-dd')}")
        self.week_table.setHorizontalHeaderLabels([d.toString("MM-dd ddd") for d in days])
        entries_by_day = []
        max_rows = 1
        for d in days:
            if d.year() == self.year and d.month() == self.month and d.day() == self.day:
                records = self.records or []
            elif self.load_callback:
                records = self.load_callback(d.year(), d.month(), d.day()) or []
            else:
                records = []
            records = sorted(records, key=lambda r: str(r.get("time", "")) if isinstance(r, dict) else "")
            entries = []
            for record in records:
                entries.extend(self._record_table_entries(record))
            entries_by_day.append(entries)
            max_rows = max(max_rows, len(entries))
        self.week_table.setRowCount(max_rows)
        for col in range(7):
            self.week_table.setColumnWidth(col, 138)
            for row in range(max_rows):
                self.week_table.setItem(row, col, QTableWidgetItem(""))
        for col, day_entries in enumerate(entries_by_day):
            for row, entry in enumerate(day_entries):
                item = QTableWidgetItem(entry["text"])
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip(entry["detail"])
                item.setData(Qt.UserRole, entry["detail"])
                item.setData(Qt.UserRole + 1, entry.get("changes", []))
                item.setBackground(QColor(entry["bg"]))
                item.setForeground(QColor(entry["fg"]))
                self.week_table.setItem(row, col, item)
        for row in range(max_rows):
            self.week_table.setRowHeight(row, 76)

    def show_week_cell_detail(self, row, col):
        item = self.week_table.item(row, col)
        if not item:
            return
        detail = item.data(Qt.UserRole)
        if not detail:
            return
        self.show_record_detail_dialog(item.text(), item.data(Qt.UserRole + 1) or [], str(detail))

    def show_record_detail_dialog(self, title, changes, fallback_text):
        dialog = QDialog(self)
        dialog.setWindowTitle("操作记录详情")
        dialog.resize(620, 460)
        layout = QVBoxLayout(dialog)
        header = QLabel(str(title or "").replace("\n", "  "))
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50; padding: 4px 2px;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #d9e2ec; border-radius: 6px; background: white; }")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(8)
        has_rows = False
        for change in changes or []:
            if isinstance(change, dict):
                content_layout.addWidget(self._change_detail_widget(change))
                has_rows = True
        if not has_rows:
            label = QLabel(str(fallback_text or ""))
            label.setWordWrap(True)
            label.setStyleSheet("color:#2c3e50; line-height:1.6;")
            content_layout.addWidget(label)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        btn_close = QPushButton("关闭")
        btn_close.setFocusPolicy(Qt.NoFocus)
        btn_close.clicked.connect(dialog.accept)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(btn_close)
        layout.addLayout(footer)
        dialog.exec_()

    def _tag_label(self, text, bg="#eef2f7", fg="#34495e"):
        label = QLabel(str(text or ""))
        label.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid #000; border-radius:8px; "
            "padding:4px 8px; font-weight:600;"
        )
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        return label

    def _change_detail_widget(self, change):
        metric = str(change.get("metric", "") or "操作记录")
        metric_bg, metric_fg = self._metric_colors(metric)
        old = str(change.get("old", "") or "").strip()
        new = str(change.get("new", "") or "").strip()
        spec = self._detail_spec_text(change)
        direction = self._detail_direction(change)
        box = QFrame()
        box.setStyleSheet("QFrame { border-bottom:1px solid #edf2f7; background:white; }")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)
        tags = QHBoxLayout()
        tags.setContentsMargins(0, 0, 0, 0)
        tags.setSpacing(2)
        tags.addWidget(self._tag_label(metric, metric_bg, metric_fg))
        if spec:
            tags.addWidget(self._tag_label(spec, "#e9f2ff", "#245269"))
        elif old and new and direction in ("提升至", "降低至"):
            tags.addWidget(self._tag_label("从", "#f8fafc", "#34495e"))
        if old:
            tags.addWidget(self._tag_label(old, "#fff3cd", "#8a5a00"))
        if direction:
            tags.addWidget(self._tag_label(direction, "#fdecea" if "降" in direction else "#e8f8ef", "#c0392b" if "降" in direction else "#1e8449"))
        if new:
            tags.addWidget(self._tag_label(new, "#e8f0fe", "#2f5fb3"))
        tags.addStretch()
        layout.addLayout(tags)
        summary = self._detail_clean_text(change, spec, old, new, direction)
        if summary:
            detail = QLabel(summary)
            detail.setWordWrap(True)
            detail.setStyleSheet("color:#2c3e50; line-height:1.6; padding-left:3px;")
            layout.addWidget(detail)
        return box

    def _detail_spec_text(self, change):
        text = str(change.get("text", "") or "").strip()
        metric = str(change.get("metric", "") or "")
        if "规格" in metric or "售价" in metric or "价格" in metric:
            for pattern in (
                r"^(.+?)(?:从|售价设置为|设置售价到)",
                r"^(?:新增规格|删除规格)\s*[:：]?\s*(.+)$",
            ):
                match = re.search(pattern, text)
                if match:
                    return match.group(1).strip(" ：:")
        bracket = re.search(r"\[([^\]]{1,120})\]", text)
        return bracket.group(1).strip() if bracket else ""

    def _detail_direction(self, change):
        text = str(change.get("text", "") or "")
        metric = str(change.get("metric", "") or "")
        old = self._first_number(change.get("old", ""))
        new = self._first_number(change.get("new", ""))
        if "涨价" in text:
            return "涨价"
        if "降价" in text:
            return "降价"
        if old is not None and new is not None and old != new:
            delta = new - old
            if "优惠券" in metric or "立减" in metric:
                delta = -delta
            if self._change_group(change) == "price":
                return "涨价" if delta > 0 else "降价"
            return "提升至" if delta > 0 else "降低至"
        if "提高" in text or "提升" in text:
            return "提升至"
        if "降低" in text or "下降" in text:
            return "降低至"
        return ""

    def _detail_clean_text(self, change, spec, old, new, direction):
        text = str(change.get("text", "") or "").strip()
        if not text:
            return ""
        cleaned = text
        for value in (spec, old, new):
            if value:
                cleaned = cleaned.replace(value, "").strip()
        cleaned = re.sub(r"[\[\]：:，,\s]+", " ", cleaned).strip()
        if direction:
            cleaned = cleaned.replace(direction, "").strip()
        cleaned = re.sub(r"^(净利率|净利|毛利率|毛利|综合毛利)?\s*(从|到|至|变为|变化|改变|调整|修改|提升|降低|提升至|降低至|\s)+$", "", cleaned)
        return cleaned

    def _toggle_reminder_inputs(self, state):
        visible = state == Qt.Checked
        self.reminder_date.setVisible(visible)
        self.reminder_time.setVisible(visible)

    def refresh_pending_tasks(self):
        view = getattr(self, "pending_task_edit", None)
        loader = getattr(self.parent(), "get_product_pending_task_lines", None)
        if view is None:
            return
        lines = loader(self.prod_id) if callable(loader) else []
        view.setPlainText("\n\n".join(lines) if lines else "暂无待完成任务")

    def quick_set_reminder(self):
        text = self.new_text_edit.text().strip()
        if not text:
            QMessageBox.information(self, "快速设置提醒", "请先输入操作记录内容。")
            return
        remind_time = QDateTime.currentDateTime().addSecs(24 * 60 * 60).toString("yyyy-MM-dd HH:mm:ss")
        try:
            record = self.quick_reminder_callback(text, remind_time)
            today = QDate.currentDate()
            if (
                isinstance(record, dict)
                and getattr(self, "year", 0) == today.year()
                and getattr(self, "month", 0) == today.month()
                and getattr(self, "day", 0) == today.day()
            ):
                self.records.append(record)
            clear_input = getattr(self.new_text_edit, "clear", None)
            if callable(clear_input):
                clear_input()
            refresh_pending = getattr(self, "refresh_pending_tasks", None)
            if callable(refresh_pending):
                refresh_pending()
            if hasattr(self, "week_table"):
                self.refresh_week_table()
        except Exception as e:
            QMessageBox.warning(self, "快速设置提醒", f"设置提醒失败：{e}")

    def add_new_record_from_input(self):
        text = self.new_text_edit.text().strip()
        if not text:
            return
        time_text = self.new_time_edit.time().toString("HH:mm")
        record = {
            "time": time_text,
            "text": text,
            "_add_task": self.chk_task.isChecked(),
            "_add_reminder": self.chk_reminder.isChecked(),
        }
        if record["_add_reminder"]:
            record["_reminder_datetime"] = f"{self.reminder_date.date().toString('yyyy-MM-dd')} {self.reminder_time.time().toString('HH:mm')}"
        if record["_add_task"] or record["_add_reminder"]:
            target = record.get("_reminder_datetime", "待完成")
            record["changes"] = [{
                "time": time_text,
                "metric": "创建任务",
                "old": "",
                "new": target,
                "text": f"创建任务：{text}" + (f"；提醒时间：{target}" if record["_add_reminder"] else ""),
                "type": "task_reminder_created" if record["_add_reminder"] else "task_created",
            }]
        self.records.append(record)
        self.new_text_edit.clear()
        self.chk_task.setChecked(False)
        self.chk_reminder.setChecked(False)
        self.new_time_edit.setTime(QTime.currentTime())
        self.refresh_week_table()

    def add_row(self, time_str="", text="", original_record=None):
        record = {"time": time_str, "text": text}
        if original_record:
            record.update(original_record)
        self.records.append(record)
        self.refresh_week_table()
        return record

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

    def _metric_colors(self, metric):
        for key, colors in METRIC_STYLES.items():
            if key in str(metric or ""):
                return colors
        return "#edf2f7", "#34495e"

    def _metric_abbr(self, metric):
        metric = str(metric or "").strip()
        for key, abbr in METRIC_ABBR.items():
            if key in metric:
                return abbr
        return metric[:2] or "记"

    def _first_number(self, value):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value or "").replace(",", ""))
        return float(match.group(0)) if match else None

    def _fmt_number(self, value):
        if value is None:
            return ""
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def _change_group(self, change):
        combined = " ".join(str(change.get(k, "") or "") for k in ("metric", "text", "type"))
        if any(word in combined for word in ("售价", "价格", "改价", "优惠券", "立减", "涨价", "降价")):
            return "price"
        if "投产" in combined or "roi" in combined.lower():
            return "roi"
        if "规格" in combined:
            return "spec"
        return "other"

    def _price_summary(self, changes):
        deltas = []
        ratios = []
        detail_lines = []
        fallback = ""
        for change in changes:
            old = self._first_number(change.get("old", ""))
            new = self._first_number(change.get("new", ""))
            text = str(change.get("text", "") or "").strip()
            metric = str(change.get("metric", "") or "")
            if text and not fallback:
                fallback = text
            if old is None or new is None:
                detail_lines.append(text or self._change_detail_line(change))
                continue
            delta = new - old
            if "优惠券" in metric or "立减" in metric:
                delta = -delta
            deltas.append(delta)
            if old:
                ratios.append(delta / old * 100)
            detail_lines.append(self._change_detail_line(change))
        if not deltas:
            return self._text_price_summary(fallback), detail_lines
        if all(delta > 0 for delta in deltas):
            title = "涨价"
        elif all(delta < 0 for delta in deltas):
            title = "降价"
        else:
            return "改价", detail_lines
        abs_deltas = [abs(delta) for delta in deltas]
        if max(abs_deltas) - min(abs_deltas) < 0.01:
            return f"{title}\n{title}{self._fmt_number(abs_deltas[0])}元", detail_lines
        if ratios and all(ratio > 0 for ratio in ratios) == all(delta > 0 for delta in deltas):
            avg_ratio = sum(abs(ratio) for ratio in ratios) / len(ratios)
            return f"{title}\n约{title}{self._fmt_number(avg_ratio)}%", detail_lines
        return title, detail_lines

    def _text_price_summary(self, text):
        text = str(text or "")
        if "涨价" in text:
            match = re.search(r"涨价\s*([0-9.]+)\s*(元|%)?", text)
            return f"涨价\n涨价{match.group(1)}{match.group(2) or '元'}" if match else "涨价"
        if "降价" in text:
            match = re.search(r"降价\s*([0-9.]+)\s*(元|%)?", text)
            return f"降价\n降价{match.group(1)}{match.group(2) or '元'}" if match else "降价"
        return "改价"

    def _roi_summary(self, changes):
        vals = []
        detail_lines = []
        for change in changes:
            old = self._first_number(change.get("old", ""))
            new = self._first_number(change.get("new", ""))
            detail_lines.append(self._change_detail_line(change))
            if old is not None and new is not None:
                vals.append((old, new))
        if not vals:
            text = " ".join(str(c.get("text", "") or "") for c in changes)
            if "降" in text:
                return "降投产", detail_lines
            return "提投产", detail_lines
        old, new = vals[-1]
        if new >= old:
            pct = ((new - old) / old * 100) if old else None
            amount = f"{self._fmt_number(pct)}%" if pct is not None else self._fmt_number(new - old)
            return f"提投产\n提升{amount}到{self._fmt_number(new)}", detail_lines
        pct = ((old - new) / old * 100) if old else None
        amount = f"{self._fmt_number(pct)}%" if pct is not None else self._fmt_number(old - new)
        return f"降投产\n降低{amount}到{self._fmt_number(new)}", detail_lines

    def _change_detail_line(self, change):
        metric = str(change.get("metric", "") or "操作记录")
        old = str(change.get("old", "") or "").strip()
        new = str(change.get("new", "") or "").strip()
        text = str(change.get("text", "") or "").strip()
        if old or new:
            return f"{metric}: {old} → {new}\n{text}".strip()
        return f"{metric}: {text}".strip()

    def _numeric_change_summary(self, change):
        metric = str(change.get("metric", "") or "指标")
        old = self._first_number(change.get("old", ""))
        new = self._first_number(change.get("new", ""))
        if old is None or new is None or old == new:
            return self._metric_abbr(metric)
        name = self._metric_abbr(metric)
        old_text = str(change.get("old", "") or self._fmt_number(old)).strip()
        new_text = str(change.get("new", "") or self._fmt_number(new)).strip()
        if new > old:
            direction = f"提{name}"
            verb = "提升至"
        else:
            direction = f"降{name}"
            verb = "降低至"
        return f"{direction}\n{old_text}{verb}{new_text}"

    def _record_table_entries(self, record):
        if not isinstance(record, dict):
            return []
        time_text = str(record.get("time", "") or "")
        changes = [c for c in (record.get("changes") or []) if isinstance(c, dict)]
        if not changes:
            text = str(record.get("text", "") or "").strip()
            return [{
                "text": f"{time_text}\n记录\n{text[:18]}" if text else time_text,
                "detail": text,
                "changes": [],
                "bg": "#f8fafc",
                "fg": "#34495e",
            }]
        entries = []
        used = set()
        for group, builder, default_metric in (
            ("price", self._price_summary, "改价"),
            ("roi", self._roi_summary, "投产"),
        ):
            by_metric = {}
            for change in changes:
                if self._change_group(change) == group:
                    metric = str(change.get("metric", "") or default_metric)
                    by_metric.setdefault(metric, []).append(change)
            for metric, grouped in by_metric.items():
                for c in grouped:
                    used.add(id(c))
                summary, detail_lines = builder(grouped)
                bg, fg = self._metric_colors(metric)
                entries.append({
                    "text": f"{time_text}\n{summary}" if time_text else summary,
                    "detail": "\n\n".join(detail_lines),
                    "changes": grouped,
                    "bg": bg,
                    "fg": fg,
                })
        for change in changes:
            if id(change) in used:
                continue
            metric = str(change.get("metric", "") or "操作记录")
            if self._change_group(change) == "spec":
                title = "修改规格"
            else:
                title = self._numeric_change_summary(change)
            bg, fg = self._metric_colors(metric)
            entries.append({
                "text": f"{time_text}\n{title}",
                "detail": self._change_detail_line(change),
                "changes": [change],
                "bg": bg,
                "fg": fg,
            })
        return entries

    def save(self):
        if self.new_text_edit.text().strip():
            self.add_new_record_from_input()
        data = []
        task_list = []
        reminder_list = []

        for row_data in self.records:
            try:
                if row_data and row_data.get("text"):
                    record = {"time": row_data.get("time", ""), "text": row_data.get("text", "")}
                    if row_data.get("history_id"):
                        record["history_id"] = row_data.get("history_id")
                    if row_data.get("changes"):
                        record["changes"] = row_data.get("changes")
                    data.append(record)

                    if row_data.get("_add_task"):
                        task_list.append(row_data.get("text", ""))

                    if row_data.get("_add_reminder"):
                        reminder_list.append({
                            "text": row_data.get("text", ""),
                            "datetime": row_data.get("_reminder_datetime", "")
                        })
            except Exception:
                continue

        if self.memo_save_callback:
            try:
                self.memo_save_callback(self.memo_edit.toPlainText().strip())
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"保存链接备注失败：{e}")
                return

        if self.save_with_date:
            self.save_callback(data, self.year, self.month, self.day)
        else:
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

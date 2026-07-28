# -*- coding: utf-8 -*-
"""每日任务对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QTextEdit, QPushButton,
    QWidget, QScrollArea, QFrame, QCheckBox, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QApplication, QSplitter, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle
)
from PyQt5.QtCore import QPoint, Qt, QTimer, QDateTime
from PyQt5.QtGui import QFont, QPixmap
from datetime import datetime, timedelta

try:
    from ..window_icons import apply_window_icon
except ImportError:
    from window_icons import apply_window_icon


class TaskReminderPopupDialog(QDialog):
    """到时代办提醒强制弹窗。"""
    def __init__(self, reminder, parent=None):
        super().__init__(parent)
        self.reminder = reminder
        self.completed = False
        self._shake_origin = None
        self._shake_step = 0
        self._shake_started = False
        apply_window_icon(self, "daily")
        self.setWindowTitle(f"代办提醒 - {reminder.get('store_name', '')}")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags((self.windowFlags() | Qt.WindowStaysOnTopHint) & ~Qt.WindowCloseButtonHint)
        self.resize(560, 420)
        self._build_ui()
        self._shake_timer = QTimer(self)
        self._shake_timer.setInterval(60)
        self._shake_timer.timeout.connect(self._shake_window)
        self._shake_stop_timer = QTimer(self)
        self._shake_stop_timer.setSingleShot(True)
        self._shake_stop_timer.timeout.connect(self._stop_shaking)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("代办提醒时间已到")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #c0392b;")
        layout.addWidget(title)

        info = QLabel(
            f"时间：{self.reminder.get('remind_time', '')}\n"
            f"店铺：{self.reminder.get('store_name', '')}\n"
            f"链接ID：{self.reminder.get('product_code', '')}\n"
            f"链接类型：{self.reminder.get('link_type', '未分类')}\n"
            f"标题：{self.reminder.get('product_title', '')}"
        )
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.setStyleSheet("font-size: 13px; color: #2c3e50; line-height: 1.5;")
        product_layout = QHBoxLayout()
        self.image_label = QLabel("无图")
        self.image_label.setFixedSize(120, 120)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border:1px solid #d0d7de; background:#f6f8fa; color:#6b7280;")
        self.product_pixmap = QPixmap()
        image_data = self.reminder.get("product_image_data")
        if image_data and self.product_pixmap.loadFromData(image_data):
            self.image_label.setPixmap(
                self.product_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        product_layout.addWidget(self.image_label)
        product_layout.addWidget(info, 1)
        layout.addLayout(product_layout)

        content = QTextEdit()
        content.setReadOnly(True)
        content.setPlainText(str(self.reminder.get("task_content", "") or ""))
        content.setStyleSheet("""
            QTextEdit {
                border: 1px solid #d0d7de;
                border-radius: 4px;
                padding: 8px;
                background: #fffdf7;
                font-size: 13px;
            }
        """)
        layout.addWidget(content, 1)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("复制 ID")
        btn_copy.clicked.connect(self.copy_product_id)
        btn_copy_image = QPushButton("复制图片")
        btn_copy_image.setEnabled(not self.product_pixmap.isNull())
        btn_copy_image.clicked.connect(self.copy_product_image)
        btn_copy_type = QPushButton("复制链接类型")
        btn_copy_type.clicked.connect(self.copy_link_type)
        btn_done = QPushButton("已完成")
        btn_done.setStyleSheet("QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px; }")
        btn_done.clicked.connect(self.mark_completed)
        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_copy_image)
        btn_layout.addWidget(btn_copy_type)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_done)
        layout.addLayout(btn_layout)

    def copy_product_id(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(str(self.reminder.get("product_code", "") or ""))

    def copy_product_image(self):
        if not self.product_pixmap.isNull():
            QApplication.clipboard().setPixmap(self.product_pixmap)

    def copy_link_type(self):
        QApplication.clipboard().setText(str(self.reminder.get("link_type", "未分类") or "未分类"))

    def showEvent(self, event):
        super().showEvent(event)
        if not self._shake_started:
            self._shake_started = True
            QTimer.singleShot(0, self._start_shaking)

    def _start_shaking(self):
        self._shake_origin = self.pos()
        self._shake_step = 0
        self._shake_timer.start()
        self._shake_stop_timer.start(5000)

    def _shake_window(self):
        if self._shake_origin is None:
            return
        offsets = (-7, 7, -5, 5)
        self.move(self._shake_origin + QPoint(offsets[self._shake_step % len(offsets)], 0))
        self._shake_step += 1

    def _stop_shaking(self):
        self._shake_timer.stop()
        if self._shake_origin is not None:
            self.move(self._shake_origin)

    def mark_completed(self):
        self.completed = True
        super().accept()

    def accept(self):
        if self.completed:
            super().accept()

    def reject(self):
        if self.completed:
            super().reject()

    def closeEvent(self, event):
        if self.completed:
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and not self.completed:
            event.ignore()
            return
        super().keyPressEvent(event)


class FocuslessItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option = QStyleOptionViewItem(option)
        option.state &= ~QStyle.State_HasFocus
        super().paint(painter, option, index)


class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.UserRole)
        right = other.data(Qt.UserRole)
        if left is not None and right is not None:
            return float(left) < float(right)
        return super().__lt__(other)


class CopyableTableWidget(QTableWidget):
    """支持选中单元格/多行后 Ctrl+C 复制为表格文本。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setItemDelegate(FocuslessItemDelegate(self))
        self.sortable_columns = set()
        self._sort_column = -1
        self._sort_order = Qt.AscendingOrder
        self.horizontalHeader().sectionClicked.connect(self.sort_by_column)

    def set_sortable_columns(self, columns):
        self.sortable_columns = set(columns)
        self._sort_column = -1
        self._sort_order = Qt.AscendingOrder
        self.horizontalHeader().setSortIndicatorShown(False)

    def sort_by_column(self, column):
        if column not in self.sortable_columns:
            return
        self._sort_order = (
            Qt.DescendingOrder
            if column == self._sort_column and self._sort_order == Qt.AscendingOrder
            else Qt.AscendingOrder
        )
        self._sort_column = column
        self.sortItems(column, self._sort_order)
        self.horizontalHeader().setSortIndicator(column, self._sort_order)
        self.horizontalHeader().setSortIndicatorShown(True)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_C:
            self.copy_selection()
            return
        super().keyPressEvent(event)

    def copy_selection(self):
        indexes = sorted(self.selectedIndexes(), key=lambda idx: (idx.row(), idx.column()))
        if not indexes:
            return
        rows = sorted({idx.row() for idx in indexes})
        cols = sorted({idx.column() for idx in indexes})
        lines = []
        for row in rows:
            values = []
            for col in cols:
                item = self.item(row, col)
                values.append(item.text() if item else "")
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))


class DailyTaskDialog(QDialog):
    """每日任务对话框 - 大盘分析和亏损链接优化"""
    def __init__(self, db_manager, parent=None):
        super().__init__(None)
        self.db = db_manager
        self.main_app = parent
        apply_window_icon(self, "daily")
        self.setWindowTitle("📋 每日任务 - 大盘分析")
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.resize(1180, 760)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(left_splitter)
        layout.addWidget(main_splitter, 1)

        task_section = QWidget()
        task_layout = QVBoxLayout(task_section)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(6)
        header = QLabel("每日任务大盘")
        header.setStyleSheet("font-size: 16px; font-weight: bold; padding: 1px 2px; color: #1f2937;")
        task_layout.addWidget(header)

        task_scroll = QScrollArea()
        task_scroll.setWidgetResizable(True)
        task_scroll.setFrameShape(QFrame.NoFrame)
        task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        task_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        task_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        task_container = QWidget()
        self.task_cards_layout = QHBoxLayout(task_container)
        self.task_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.task_cards_layout.setSpacing(8)
        task_scroll.setWidget(task_container)
        task_layout.addWidget(task_scroll, 1)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(54)
        self.detail_text.setPlaceholderText("任务说明和统计摘要...")
        self.detail_text.setStyleSheet("""
            QTextEdit {
                background: #fffdf7;
                border: 1px solid #f1d9a8;
                border-radius: 8px;
                padding: 5px;
                font-size: 12px;
                color: #374151;
            }
        """)
        task_layout.addWidget(self.detail_text)
        left_splitter.addWidget(task_section)

        spec_section = QWidget()
        spec_layout = QVBoxLayout(spec_section)
        spec_layout.setContentsMargins(0, 0, 0, 0)
        spec_layout.setSpacing(6)
        spec_header = QHBoxLayout()
        self.spec_section_title = QLabel("规格图片检查")
        self.spec_section_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #111827;")
        spec_header.addWidget(self.spec_section_title)
        spec_header.addStretch()
        btn_copy = QPushButton("复制选中")
        btn_copy.clicked.connect(lambda: self.result_table.copy_selection())
        spec_header.addWidget(btn_copy)
        self.btn_known_garbage = QPushButton("已知垃圾链接")
        self.btn_known_garbage.clicked.connect(self.show_known_garbage_links)
        spec_header.addWidget(self.btn_known_garbage)
        spec_layout.addLayout(spec_header)

        self.store_filter_scroll = QScrollArea()
        self.store_filter_scroll.setWidgetResizable(True)
        self.store_filter_scroll.setFrameShape(QFrame.NoFrame)
        self.store_filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.store_filter_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.store_filter_scroll.setFixedHeight(40)
        self.store_filter_container = QWidget()
        self.store_filter_layout = QHBoxLayout(self.store_filter_container)
        self.store_filter_layout.setContentsMargins(0, 2, 0, 2)
        self.store_filter_layout.setSpacing(5)
        self.store_filter_scroll.setWidget(self.store_filter_container)
        spec_layout.addWidget(self.store_filter_scroll)

        self.spec_image_table = CopyableTableWidget()
        self.result_table = self.spec_image_table
        self.spec_image_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.spec_image_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.spec_image_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.spec_image_table.setAlternatingRowColors(True)
        self.spec_image_table.setWordWrap(True)
        self.spec_image_table.verticalHeader().setVisible(False)
        self.spec_image_table.horizontalHeader().setStretchLastSection(True)
        self.spec_image_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.spec_image_table.setStyleSheet("""
            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #dbe3ef;
                border-radius: 8px;
                gridline-color: #e5e7eb;
                font-size: 13px;
            }
            QHeaderView::section {
                background: #f1f5f9;
                color: #111827;
                font-weight: bold;
                padding: 5px;
                border: none;
                border-right: 1px solid #dbe3ef;
                border-bottom: 1px solid #dbe3ef;
            }
            QTableWidget::item {
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background: #dbeafe;
                color: #111827;
            }
            QTableWidget::item:focus { outline: none; }
        """)
        spec_layout.addWidget(self.spec_image_table, 1)
        left_splitter.addWidget(spec_section)

        reminder_section = QWidget()
        reminder_layout = QVBoxLayout(reminder_section)
        reminder_layout.setContentsMargins(0, 0, 0, 0)
        reminder_layout.setSpacing(6)
        self.reminder_label = QLabel("待办提醒")
        self.reminder_label.setStyleSheet("font-size: 15px; font-weight: bold; padding: 1px; color: #b91c1c;")
        reminder_layout.addWidget(self.reminder_label)
        self.reminder_list = QListWidget()
        self.reminder_list.setStyleSheet("""
            QListWidget {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 8px;
            }
            QListWidget::item:selected { background: #fee2e2; color: #7f1d1d; }
        """)
        self.reminder_list.itemClicked.connect(self.on_reminder_item_clicked)
        reminder_layout.addWidget(self.reminder_list, 1)
        main_splitter.addWidget(reminder_section)
        left_splitter.setSizes([190, 520])
        main_splitter.setSizes([920, 260])

        self.load_store_filter()
        self.load_tasks()
        self.load_reminders()
        self.analyze_missing_spec_images()

        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self.on_refresh)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        for btn in (btn_refresh, btn_close):
            btn.setStyleSheet("""
                QPushButton {
                    background: #f8fafc;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 7px 16px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #eef2f7; }
            """)
        btn_layout.addWidget(btn_refresh)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def start_reminder_check(self):
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(30000)

    def check_reminders(self):
        try:
            now = QDateTime.currentDateTime()
            current_time_str = now.toString("yyyy-MM-dd HH:mm:ss")

            reminders = self.db.safe_fetchall(
                """SELECT id, store_id, product_id, task_content, remind_time
                   FROM task_reminders WHERE is_reminded = 0 ORDER BY remind_time"""
            )

            for rem_id, store_id, product_id, task_content, remind_time in reminders:
                if str(remind_time) <= current_time_str:
                    self.show_reminder_popup(rem_id, store_id, product_id, task_content, remind_time)
                    self.db.safe_execute(
                        "UPDATE task_reminders SET is_reminded = 1 WHERE id = ?",
                        (rem_id,)
                    )
                    if self.main_app and hasattr(self.main_app, "force_refresh_product_widget"):
                        self.main_app.force_refresh_product_widget(product_id)
        except Exception as e:
            print(f"检查提醒失败: {e}")

    def show_reminder_popup(self, rem_id, store_id, product_id, task_content, remind_time):
        store_name = ""
        try:
            store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
            if store_res and store_res[0][0]:
                store_name = store_res[0][0]
        except:
            pass

        product_code = str(product_id)
        product_title = ""
        try:
            prod_res = self.db.safe_fetchall("SELECT name, title FROM products WHERE id=?", (product_id,))
            if prod_res and prod_res[0][0]:
                product_code = prod_res[0][0]
                product_title = prod_res[0][1] if prod_res[0][1] else ""
        except:
            pass

        msg = QMessageBox(self)
        msg.setWindowTitle(f"🔔 提醒 - {store_name}")
        msg.setText(f"""<b>⏰ 时间: {remind_time}</b><br><br>
<b>🏪 店铺:</b> {store_name}<br><br>
<b>📦 链接ID:</b> {product_code} <button id="copy_btn">复制</button><br><br>
<b>📝 任务内容:</b><br>{task_content}""")
        msg.setTextFormat(Qt.RichText)
        msg.setIcon(QMessageBox.Information)

        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(product_code)

        msg.exec_()

    def load_reminders(self):
        self.reminder_list.clear()
        try:
            reminders = self.db.safe_fetchall(
                """SELECT id, store_id, product_id, task_content, remind_time, is_reminded
                   FROM task_reminders WHERE is_reminded = 0 ORDER BY remind_time DESC LIMIT 50"""
            )

            for rem_id, store_id, product_id, task_content, remind_time, is_reminded in reminders:
                store_name = ""
                try:
                    store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
                    if store_res and store_res[0][0]:
                        store_name = store_res[0][0]
                except:
                    pass

                product_code = str(product_id)
                try:
                    prod_res = self.db.safe_fetchall("SELECT name FROM products WHERE id=?", (product_id,))
                    if prod_res and prod_res[0][0]:
                        product_code = prod_res[0][0]
                except:
                    pass

                status_icon = "✅" if is_reminded else "🔔"
                item_text = f"{status_icon} [{store_name}] {product_code} - {remind_time}"
                self.reminder_list.addItem(item_text)

        except Exception as e:
            print(f"加载提醒失败: {e}")

    def on_reminder_item_clicked(self, item):
        pass

    def on_refresh(self):
        self.load_store_filter()
        self.load_tasks()
        self.load_reminders()
        self.analyze_missing_spec_images()
        self.show_toast("已刷新")

    def show_toast(self, message):
        if self.main_app and hasattr(self.main_app, 'show_toast'):
            self.main_app.show_toast(message)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _create_task_card(self, icon, title, subtitle, count_text, color, callback):
        card = QPushButton()
        card.setCursor(Qt.PointingHandCursor)
        card.setMinimumSize(190, 82)
        card.setMaximumWidth(240)
        card.setText(f"{icon}  {title}\n{subtitle}\n{count_text}")
        card.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                background: #ffffff;
                color: #111827;
                border: 2px solid {color};
                border-radius: 18px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: bold;
                line-height: 1.5;
            }}
            QPushButton:hover {{
                background: #f8fafc;
                border-color: #111827;
            }}
            QPushButton:pressed {{
                background: #eef2ff;
            }}
        """)
        card.clicked.connect(callback)
        return card

    def _set_result_table(self, title, summary, headers, rows):
        if hasattr(self, "spec_section_title"):
            self.spec_section_title.setText(title)
        self.detail_text.setPlainText(summary or "")
        self.result_table.clear()
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        sortable_headers = {"客单价", "单量", "毛利率", "净利率", "净利润", "当前投产", "投产倍数", "预计盈亏（100限额）"}
        self.result_table.set_sortable_columns(i for i, header in enumerate(headers) if header in sortable_headers)
        self.result_table.setRowCount(len(rows))
        for row_idx, row_values in enumerate(rows):
            for col_idx, value in enumerate(row_values):
                if headers[col_idx] == "图片":
                    label = QLabel("无图")
                    label.setAlignment(Qt.AlignCenter)
                    label.setAttribute(Qt.WA_TransparentForMouseEvents)
                    if value:
                        pixmap = QPixmap()
                        if pixmap.loadFromData(bytes(value)):
                            label.setPixmap(pixmap.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    self.result_table.setCellWidget(row_idx, col_idx, label)
                    self.result_table.setRowHeight(row_idx, 72)
                    continue
                item = NumericTableWidgetItem(str(value if value is not None else ""))
                if headers[col_idx] in sortable_headers:
                    try:
                        item.setData(Qt.UserRole, float(str(value).replace("¥", "").replace("%", "").replace("倍", "").replace(",", "")))
                    except (TypeError, ValueError):
                        pass
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if col_idx in (1, 2, len(headers) - 1) else Qt.AlignCenter))
                item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.result_table.setItem(row_idx, col_idx, item)
        self.result_table.resizeRowsToContents()
        self.result_table.resizeColumnsToContents()
        header = self.result_table.horizontalHeader()
        for col in range(len(headers)):
            width = self.result_table.columnWidth(col)
            if headers[col] == "图片":
                self.result_table.setColumnWidth(col, 78)
            elif headers[col] in ("商品ID", "规格编码"):
                self.result_table.setColumnWidth(col, max(width, 130))
            elif headers[col] in ("商品标题", "缺图规格", "建议", "任务内容"):
                self.result_table.setColumnWidth(col, min(max(width, 220), 360))
            elif headers[col] == "店铺":
                self.result_table.setColumnWidth(col, min(max(width, 120), 180))
        if headers:
            header.setStretchLastSection(True)

    def _product_id_column(self):
        for col in range(self.result_table.columnCount()):
            header_item = self.result_table.horizontalHeaderItem(col)
            if header_item and header_item.text() == "商品ID":
                return col
        return -1

    def _copy_product_ids_from_rows(self, rows):
        product_col = self._product_id_column()
        if product_col < 0:
            self.show_toast("当前表格没有商品ID列")
            return
        ids = []
        seen = set()
        for row in rows:
            item = self.result_table.item(row, product_col)
            product_id = item.text().strip() if item else ""
            if product_id and product_id not in seen:
                ids.append(product_id)
                seen.add(product_id)
        if not ids:
            self.show_toast("没有可复制的商品ID")
            return
        QApplication.clipboard().setText("\n".join(ids))
        self.show_toast(f"已复制 {len(ids)} 个商品ID")

    def copy_selected_product_ids(self):
        rows = sorted({index.row() for index in self.result_table.selectedIndexes()})
        self._copy_product_ids_from_rows(rows)

    def copy_all_product_ids(self):
        self._copy_product_ids_from_rows(range(self.result_table.rowCount()))

    def load_store_filter(self):
        if not hasattr(self, "store_filter_layout"):
            return
        current_store_id = getattr(self, "selected_store_id", None)
        self._clear_layout(self.store_filter_layout)
        self.store_filter_buttons = {}
        rows = self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order, id")
        choices = [(None, "全部")] + [(store_id, str(store_name or f"店铺{store_id}")) for store_id, store_name in rows]
        valid_ids = {store_id for store_id, _name in choices}
        self.selected_store_id = current_store_id if current_store_id in valid_ids else None
        for store_id, store_name in choices:
            button = QPushButton(store_name)
            button.setCheckable(True)
            button.setChecked(store_id == self.selected_store_id)
            button.setMinimumWidth(80 if store_id is None else 110)
            button.setFixedHeight(30)
            button.setStyleSheet("QPushButton { padding: 1px; }")
            button.clicked.connect(lambda _checked=False, sid=store_id: self.select_store_filter(sid))
            self.store_filter_layout.addWidget(button)
            self.store_filter_buttons[store_id] = button
        self.store_filter_layout.addStretch()

    def select_store_filter(self, store_id):
        self.selected_store_id = store_id
        for button_store_id, button in self.store_filter_buttons.items():
            button.setChecked(button_store_id == store_id)
        getattr(self, "_current_analysis", self.analyze_missing_spec_images)()

    def _store_filter(self):
        store_id = getattr(self, "selected_store_id", None)
        if store_id is None:
            return "", (), "全部店铺"
        rows = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
        name = str(rows[0][0] or f"店铺{store_id}") if rows else f"店铺{store_id}"
        return " AND p.store_id=?", (store_id,), name

    def load_tasks(self):
        self._clear_layout(self.task_cards_layout)

        total_products = self.db.safe_fetchall("SELECT COUNT(*) FROM products WHERE COALESCE(is_archived, 0)=0")
        total = total_products[0][0] if total_products and total_products[0][0] else 0
        missing_specs = self.db.safe_fetchall("""
            SELECT COUNT(*)
            FROM product_specs ps
            JOIN products p ON ps.product_id = p.id
            WHERE COALESCE(p.is_archived, 0)=0
              AND (ps.spec_image_data IS NULL OR length(ps.spec_image_data)=0)
        """)
        missing_count = missing_specs[0][0] if missing_specs and missing_specs[0][0] else 0
        waste_rows = self.db.safe_fetchall(
            """SELECT COUNT(*) FROM daily_tasks
               WHERE is_completed=0 AND task_content LIKE '【废物链接】%'"""
        )
        waste_count = waste_rows[0][0] if waste_rows and waste_rows[0][0] else 0
        garbage_rows = self.db.safe_fetchall(
            """SELECT COUNT(*) FROM daily_tasks
               WHERE is_completed=0 AND task_content LIKE '【垃圾链接】%'"""
        )
        garbage_count = garbage_rows[0][0] if garbage_rows and garbage_rows[0][0] else 0

        self.task_data = {
            0: {"title": "亏损链接优化", "total": total},
            1: {"title": "链接健康检查", "total": total},
            2: {"title": "规格图片检查", "total": missing_count},
            3: {"title": "废物链接", "total": waste_count},
            4: {"title": "垃圾链接", "total": garbage_count},
        }

        cards = [
            self._create_task_card("🔴", "亏损链接优化", "检查所有亏损商品", f"扫描 {total} 个链接", "#ef4444", self.analyze_loss_links),
            self._create_task_card("🟠", "链接健康检查", "可调整链接 / 异常链接", f"扫描 {total} 个链接", "#f97316", self.analyze_link_health),
            self._create_task_card("🟣", "规格图片检查", "找出任意规格未上传图片", f"待检查缺图规格 {missing_count} 个", "#8b5cf6", self.analyze_missing_spec_images),
            self._create_task_card("⚠", "废物链接", "最近一周无订单（新链接 7 天保护）", f"待处理 {waste_count} 个", "#dc2626", self.analyze_waste_links),
            self._create_task_card("🗑", "垃圾链接", "连续两批推广无净成交", f"待处理 {garbage_count} 个", "#b91c1c", self.analyze_garbage_links),
        ]
        for card in cards:
            self.task_cards_layout.addWidget(card)

        daily_tasks = self.db.safe_fetchall(
            """SELECT id, store_id, product_id, task_content, is_completed, created_time
               FROM daily_tasks
               WHERE is_completed = 0 AND task_content NOT LIKE '【废物链接】%' AND task_content NOT LIKE '【垃圾链接】%'
               ORDER BY created_time DESC LIMIT 20"""
        )

        for task_id, store_id, product_id, task_content, is_completed, created_time in daily_tasks:
            store_name = ""
            try:
                store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
                if store_res and store_res[0][0]:
                    store_name = store_res[0][0]
            except:
                pass

            product_code = str(product_id)
            try:
                prod_res = self.db.safe_fetchall("SELECT name FROM products WHERE id=?", (product_id,))
                if prod_res and prod_res[0][0]:
                    product_code = prod_res[0][0]
            except:
                pass

            status_icon = "✅" if is_completed else "📋"
            card = self._create_task_card(
                status_icon,
                f"{store_name or '未分店铺'}",
                f"{product_code}",
                f"{str(task_content or '')[:28]}...",
                "#64748b",
                lambda _checked=False, tid=task_id: self.show_daily_task_detail_by_id(tid),
            )
            self.task_cards_layout.addWidget(card)

        self.task_cards_layout.addStretch()

    def on_task_selected(self, index):
        if index < 0:
            return

        if index == 0:
            self.analyze_loss_links()
        elif index == 1:
            self.analyze_link_health()
        elif index == 2:
            self.analyze_missing_spec_images()
        elif index == 3:
            self.analyze_waste_links()
        elif index == 4:
            self.analyze_garbage_links()
        elif index >= 5:
            self.show_daily_task_detail(index)

    def show_daily_task_detail_by_id(self, task_id):
        rows = self.db.safe_fetchall(
            """SELECT id, store_id, product_id, task_content, is_completed, created_time
               FROM daily_tasks WHERE id=?""",
            (task_id,),
        )
        if not rows:
            return
        task_id, store_id, product_id, task_content, is_completed, created_time = rows[0]
        store_name = ""
        try:
            store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
            if store_res and store_res[0][0]:
                store_name = store_res[0][0]
        except Exception:
            pass

        product_code = str(product_id)
        product_title = ""
        try:
            prod_res = self.db.safe_fetchall("SELECT name, title FROM products WHERE id=?", (product_id,))
            if prod_res and prod_res[0][0]:
                product_code = prod_res[0][0]
                product_title = prod_res[0][1] if prod_res[0][1] else ""
        except Exception:
            pass

        self._set_result_table(
            "📋 待办任务详情",
            f"创建时间：{created_time}\n任务内容：{task_content}\n完成方式：处理完成后，可在原任务入口或数据库任务状态中标记完成。",
            ["店铺", "商品ID", "商品标题", "任务内容", "创建时间"],
            [[store_name, product_code, product_title, task_content, created_time]],
        )

    def show_daily_task_detail(self, index):
        self.detail_text.clear()
        daily_tasks = self.db.safe_fetchall(
            """SELECT id, store_id, product_id, task_content, is_completed, created_time
               FROM daily_tasks
               WHERE is_completed = 0 AND task_content NOT LIKE '【废物链接】%' AND task_content NOT LIKE '【垃圾链接】%'
               ORDER BY created_time DESC LIMIT 20"""
        )

        task_offset = 5
        if index - task_offset < len(daily_tasks):
            task_id, store_id, product_id, task_content, is_completed, created_time = daily_tasks[index - task_offset]

            store_name = ""
            try:
                store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
                if store_res and store_res[0][0]:
                    store_name = store_res[0][0]
            except:
                pass

            product_code = str(product_id)
            product_title = ""
            try:
                prod_res = self.db.safe_fetchall("SELECT name, title FROM products WHERE id=?", (product_id,))
                if prod_res and prod_res[0][0]:
                    product_code = prod_res[0][0]
                    product_title = prod_res[0][1] if prod_res[0][1] else ""
            except:
                pass

            self.detail_text.append("=" * 70)
            self.detail_text.append(f"📋 每日任务详情")
            self.detail_text.append("=" * 70)
            self.detail_text.append(f"🏪 店铺: {store_name}")
            self.detail_text.append(f"📦 链接ID: {product_code}")
            if product_title:
                self.detail_text.append(f"📝 标题: {product_title}")
            self.detail_text.append(f"📅 创建时间: {created_time}")
            self.detail_text.append(f"📝 任务内容:\n{task_content}")

            btn_complete = QPushButton("标记完成")
            btn_complete.clicked.connect(lambda: self.complete_task(task_id))
            self.detail_text.append("")
            self.detail_text.append("")

    def complete_task(self, task_id):
        try:
            rows = self.db.safe_fetchall("SELECT product_id FROM daily_tasks WHERE id = ?", (task_id,))
            product_id = rows[0][0] if rows else None
            self.db.safe_execute("UPDATE daily_tasks SET is_completed = 1 WHERE id = ?", (task_id,))
            self.load_tasks()
            if self.main_app and hasattr(self.main_app, "update_daily_task_button_badge"):
                self.main_app.update_daily_task_button_badge()
            if product_id and self.main_app and hasattr(self.main_app, "force_refresh_product_widget"):
                self.main_app.force_refresh_product_widget(product_id)
            self.show_toast("✅ 任务已标记完成")
        except Exception as e:
            print(f"完成任务失败: {e}")

    def _safe_float(self, value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _fmt_number(self, value, digits=2):
        if value is None:
            return "--"
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "--"

    def _get_product_order_count(self, store_id, product_code):
        try:
            rows = self.db.safe_fetchall(
                """SELECT COALESCE(SUM(order_count), 0)
                   FROM imported_orders
                   WHERE store_id=? AND product_id=?""",
                (store_id, str(product_code or "")),
            )
            return float(rows[0][0] or 0) if rows else 0.0
        except Exception:
            return 0.0

    def _get_latest_promotion_data(self, store_id, product_code):
        if self.main_app and hasattr(self.main_app, "get_latest_promotion_data"):
            try:
                return self.main_app.get_latest_promotion_data(store_id, product_code)
            except Exception:
                pass
        try:
            cutoff = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            rows = self.db.safe_fetchall(
                """SELECT record_date, cost, transaction_amount, net_transaction_amount, net_roi,
                          net_orders, promotion_impression_share, cost_per_net_order,
                          ctr, click_conversion_rate, net_profit, net_margin_rate
                   FROM promotion_daily_data
                   WHERE store_id=? AND product_id=? AND record_date<=?
                   ORDER BY record_date DESC
                   LIMIT 1""",
                (store_id, str(product_code or ""), cutoff),
            )
            if not rows:
                return None
            row = rows[0]
            return {
                "record_date": row[0],
                "cost": self._safe_float(row[1]),
                "transaction_amount": self._safe_float(row[2]),
                "net_transaction_amount": self._safe_float(row[3]),
                "net_roi": self._safe_float(row[4]),
                "net_orders": self._safe_float(row[5]),
                "promotion_impression_share": self._safe_float(row[6]),
                "cost_per_net_order": self._safe_float(row[7]),
                "ctr": self._safe_float(row[8]),
                "click_conversion_rate": self._safe_float(row[9]),
                "net_profit": None if row[10] is None else self._safe_float(row[10]),
                "net_margin_rate": None if row[11] is None else self._safe_float(row[11]),
            }
        except Exception:
            return None

    def _calculate_margin_context(self, product_id, max_discount, return_rate):
        metrics = self.db.calculate_product_gross_margin_metrics(product_id)
        margin_pct = metrics.get("gross_margin_pct")
        if margin_pct is None:
            return None
        margin_rate = self._safe_float(margin_pct) / 100
        avg_price = self._safe_float(metrics.get("avg_final_price"))
        net_margin_formula = margin_rate * (1 - return_rate / 100) - 0.006
        net_break_even = 1 / net_margin_formula if net_margin_formula > 0 else 0.0
        return {
            "margin_rate": margin_rate,
            "avg_price": avg_price,
            "net_break_even": net_break_even,
            "scale_roi": net_break_even * 0.8 if net_break_even > 0 else 0.0,
        }

    def _build_link_health_context(self, product):
        (
            product_id, store_id, product_code, title, store_name, current_roi,
            return_rate, saved_net_break_even, is_natural_flow, is_sitewide_managed,
            roi_input_mode, transaction_bid, sitewide_roi, spec_count, image_data, link_type,
        ) = product

        current_roi = self._safe_float(current_roi)
        return_rate = self._safe_float(return_rate)
        saved_net_break_even = self._safe_float(saved_net_break_even)
        transaction_bid = self._safe_float(transaction_bid)
        sitewide_roi = self._safe_float(sitewide_roi)
        is_natural_flow = bool(is_natural_flow)
        is_sitewide_managed = bool(is_sitewide_managed) and not is_natural_flow

        product_rows = self.db.safe_fetchall(
            "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
            (product_id,),
        )
        coupon = self._safe_float(product_rows[0][0]) if product_rows else 0.0
        new_customer = self._safe_float(product_rows[0][1]) if product_rows else 0.0
        margin_ctx = self._calculate_margin_context(product_id, max(coupon, new_customer), return_rate)
        if not margin_ctx:
            return None

        effective_roi = current_roi
        if is_natural_flow:
            effective_roi = 0.0
        elif is_sitewide_managed:
            effective_roi = sitewide_roi
        elif roi_input_mode == "bid" and transaction_bid > 0 and margin_ctx["avg_price"] > 0:
            effective_roi = margin_ctx["avg_price"] / transaction_bid

        net_break_even = margin_ctx["net_break_even"]
        scale_roi = net_break_even * 0.8 if net_break_even > 0 else margin_ctx["scale_roi"]

        if is_natural_flow:
            net_margin_rate = (margin_ctx["margin_rate"] * (1 - return_rate / 100) - 0.006) * 100
        elif effective_roi > 0:
            net_margin_rate = (margin_ctx["margin_rate"] * (1 - return_rate / 100) - 0.006 - (1 / effective_roi)) * 100
        else:
            net_margin_rate = None

        imported_orders = self._get_product_order_count(store_id, product_code)
        use_real_data = (
            self.main_app is not None
            and hasattr(self.main_app, "is_real_promotion_data_mode")
            and self.main_app.is_real_promotion_data_mode()
        )
        promotion = self._get_latest_promotion_data(store_id, product_code) if use_real_data else None
        orders = imported_orders
        net_profit = None
        net_margin_source = "理论"
        if promotion:
            orders = self._safe_float(promotion.get("net_orders"), imported_orders)
            net_profit = promotion.get("net_profit")
            if promotion.get("net_margin_rate") is not None:
                net_margin_rate = self._safe_float(promotion.get("net_margin_rate"))
                net_margin_source = f"推广日报 {promotion.get('record_date', '')}"
        elif net_margin_rate is not None:
            net_profit = margin_ctx["avg_price"] * orders * net_margin_rate / 100

        expected_profit = None
        if effective_roi > 0:
            actual_amount = 100 * effective_roi * max(0, 1 - return_rate / 100)
            expected_profit = actual_amount * (margin_ctx["margin_rate"] - 0.006) - 100

        return {
            "product_id": product_id,
            "store_id": store_id,
            "product_code": str(product_code or ""),
            "title": str(title or ""),
            "store_name": str(store_name or "未分店铺"),
            "current_roi": effective_roi,
            "net_break_even": net_break_even,
            "scale_roi": scale_roi,
            "net_margin_rate": net_margin_rate,
            "net_margin_source": net_margin_source,
            "orders": orders,
            "imported_orders": imported_orders,
            "net_profit": net_profit,
            "avg_price": margin_ctx["avg_price"],
            "gross_margin_rate": margin_ctx["margin_rate"] * 100,
            "expected_profit": expected_profit,
            "spec_count": int(spec_count or 0),
            "image_data": image_data,
            "link_type": str(link_type or "无"),
            "is_natural_flow": is_natural_flow,
            "promotion": promotion,
            "roi_multiple": effective_roi / net_break_even if effective_roi > 0 and net_break_even > 0 else None,
        }

    def _format_health_line(self, ctx, reason):
        title = f"｜{ctx['title']}" if ctx.get("title") else ""
        profit_text = "--" if ctx.get("net_profit") is None else f"¥{ctx['net_profit']:.2f}"
        return (
            f"{ctx['store_name']}｜{ctx['product_code']}{title}\n"
            f"  {reason}；单量 {self._fmt_number(ctx.get('orders'), 0)}；"
            f"净利率 {self._fmt_number(ctx.get('net_margin_rate'))}%（{ctx.get('net_margin_source')}）；"
            f"净利润 {profit_text}；当前投产 {self._fmt_number(ctx.get('current_roi'))}；"
            f"放量投产 {self._fmt_number(ctx.get('scale_roi'))}"
        )

    def analyze_link_health(self):
        self._current_analysis = self.analyze_link_health
        store_clause, store_params, store_name_filter = self._store_filter()
        products = self.db.safe_fetchall(f"""
            SELECT p.id, p.store_id, p.name, p.title, s.name as store_name,
                   COALESCE(p.current_roi, 0), COALESCE(p.return_rate, 0),
                   COALESCE(p.net_break_even_roi, 0), COALESCE(p.is_natural_flow, 0),
                   COALESCE(p.is_sitewide_managed, 0), COALESCE(p.roi_input_mode, 'roi'),
                   COALESCE(p.transaction_bid, 0), COALESCE(s.sitewide_roi, 0),
                   (SELECT COUNT(*) FROM product_specs WHERE product_id = p.id) as spec_count,
                   p.image_data, COALESCE(p.link_type, '')
            FROM products p
            LEFT JOIN stores s ON p.store_id = s.id
            WHERE COALESCE(p.is_archived, 0)=0 {store_clause}
            ORDER BY s.name, p.name
        """, store_params)

        if not products:
            self._set_result_table("🟠 链接健康检查", "暂无链接数据。", ["图片", "商品ID", "链接类型", "单量", "净利率", "净利润", "当前投产", "投产倍数"], [])
            return

        adjustable = []
        skipped = 0

        for product in products:
            ctx = self._build_link_health_context(product)
            if not ctx:
                skipped += 1
                continue

            orders = self._safe_float(ctx.get("orders"))
            net_margin = ctx.get("net_margin_rate")
            if orders < 20 and net_margin is not None and net_margin > 0:
                adjustable.append(ctx)

        adjustable.sort(key=lambda item: (self._safe_float(item.get("orders")), -self._safe_float(item.get("net_margin_rate"))))

        table_rows = []

        for ctx in adjustable:
            profit_text = "--" if ctx.get("net_profit") is None else f"¥{ctx['net_profit']:.2f}"
            table_rows.append([
                ctx.get("image_data"), ctx.get("product_code", ""), ctx.get("link_type", "无"),
                self._fmt_number(ctx.get("orders"), 0), f"{self._fmt_number(ctx.get('net_margin_rate'))}%",
                profit_text, self._fmt_number(ctx.get("current_roi")), self._fmt_number(ctx.get("roi_multiple")),
            ])

        summary = (
            f"当前筛选：{store_name_filter}；仅显示净利率为正且单量低于 20 的链接。"
            f"共 {len(adjustable)} 个；因缺少规格/成本/售价无法判断 {skipped} 个。"
        )
        self._set_result_table(
            "🟠 链接健康检查",
            summary,
            ["图片", "商品ID", "链接类型", "单量", "净利率", "净利润", "当前投产", "投产倍数"],
            table_rows,
        )

    def analyze_loss_links(self):
        self._current_analysis = self.analyze_loss_links
        store_clause, store_params, store_name_filter = self._store_filter()
        products = self.db.safe_fetchall(f"""
            SELECT p.id, p.store_id, p.name, p.title, s.name as store_name,
                   COALESCE(p.current_roi, 0), COALESCE(p.return_rate, 0),
                   COALESCE(p.net_break_even_roi, 0), COALESCE(p.is_natural_flow, 0),
                   COALESCE(p.is_sitewide_managed, 0), COALESCE(p.roi_input_mode, 'roi'),
                   COALESCE(p.transaction_bid, 0), COALESCE(s.sitewide_roi, 0),
                   (SELECT COUNT(*) FROM product_specs WHERE product_id = p.id),
                   p.image_data, COALESCE(p.link_type, '')
            FROM products p
            LEFT JOIN stores s ON p.store_id = s.id
            WHERE COALESCE(p.is_archived, 0)=0 {store_clause}
            ORDER BY s.name, p.name
        """, store_params)

        if not products:
            self._set_result_table("🔴 亏损链接优化", "暂无链接数据。", ["图片", "商品ID", "链接类型", "客单价", "单量", "毛利率", "净利率", "当前投产", "投产倍数", "预计盈亏（100限额）"], [])
            return

        losses = []
        skipped = 0
        for product in products:
            ctx = self._build_link_health_context(product)
            if not ctx or ctx.get("net_margin_rate") is None:
                skipped += 1
            elif self._safe_float(ctx.get("net_margin_rate")) < 0:
                losses.append(ctx)
        # 最低净利率放在表格下面。
        losses.sort(key=lambda item: self._safe_float(item.get("net_margin_rate")), reverse=True)
        table_rows = [[
            ctx.get("image_data"), ctx.get("product_code", ""), ctx.get("link_type", "无"),
            f"¥{self._fmt_number(ctx.get('avg_price'))}", self._fmt_number(ctx.get("orders"), 0),
            f"{self._fmt_number(ctx.get('gross_margin_rate'))}%", f"{self._fmt_number(ctx.get('net_margin_rate'))}%",
            self._fmt_number(ctx.get("current_roi")), self._fmt_number(ctx.get("roi_multiple")),
            "--" if ctx.get("expected_profit") is None else f"¥{ctx['expected_profit']:.2f}",
        ] for ctx in losses]
        summary = f"当前筛选：{store_name_filter}；仅显示亏损链接，共 {len(losses)} 个；无法判断 {skipped} 个。"
        self._set_result_table(
            "🔴 亏损链接优化",
            summary,
            ["图片", "商品ID", "链接类型", "客单价", "单量", "毛利率", "净利率", "当前投产", "投产倍数", "预计盈亏（100限额）"],
            table_rows,
        )

    def analyze_waste_links(self):
        self._current_analysis = self.analyze_waste_links
        store_id = getattr(self, "selected_store_id", None)
        store_clause = " AND dt.store_id=?" if store_id is not None else ""
        params = (store_id,) if store_id is not None else ()
        rows = self.db.safe_fetchall(f"""
            SELECT s.name, p.name, p.title, dt.task_content, dt.created_time
            FROM daily_tasks dt
            JOIN products p ON dt.product_id = p.id
            LEFT JOIN stores s ON dt.store_id = s.id
            WHERE dt.is_completed=0
              AND dt.task_content LIKE '【废物链接】%'
              {store_clause}
            ORDER BY dt.created_time DESC, s.name, p.name
        """, params)
        table_rows = [
            [store_name or "未分店铺", product_code, title or "", created_time, task_content]
            for store_name, product_code, title, task_content, created_time in rows
        ]
        store_name_filter = "全部店铺"
        if store_id is not None:
            store_rows = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
            store_name_filter = str(store_rows[0][0] or f"店铺{store_id}") if store_rows else f"店铺{store_id}"
        self._set_result_table(
            "⚠ 废物链接",
            f"当前筛选：{store_name_filter}；连续两次导入订单表都没有订单的链接，共 {len(table_rows)} 个。",
            ["店铺", "商品ID", "商品标题", "记录时间", "任务内容"],
            table_rows,
        )

    def analyze_garbage_links(self):
        self._current_analysis = self.analyze_garbage_links
        store_id = getattr(self, "selected_store_id", None)
        store_clause = " AND dt.store_id=?" if store_id is not None else ""
        rows = self.db.safe_fetchall(f"""
            SELECT dt.id, s.name, p.name, p.title, dt.created_time
            FROM daily_tasks dt
            JOIN products p ON p.id=dt.product_id
            LEFT JOIN stores s ON s.id=dt.store_id
            WHERE dt.is_completed=0 AND dt.task_content LIKE '【垃圾链接】%'{store_clause}
            ORDER BY dt.created_time DESC, s.name, p.name
        """, (store_id,) if store_id is not None else ())
        self._set_result_table(
            "🗑 垃圾链接",
            f"连续两批导入推广数据且净成交笔数都为 0 的非无推广链接，共 {len(rows)} 个。勾选“已知”后隐藏主界面垃圾标签。",
            ["店铺", "商品ID", "商品标题", "记录时间", "已知"],
            [[store_name or "未分店铺", product_code, title or "", created_time, ""] for _task_id, store_name, product_code, title, created_time in rows],
        )
        for row_index, (task_id, *_values) in enumerate(rows):
            known = QCheckBox("已知")
            known.toggled.connect(lambda checked, tid=task_id: checked and self._set_garbage_link_known(tid, True))
            self.result_table.setCellWidget(row_index, 4, known)

    def show_known_garbage_links(self):
        self._current_analysis = self.show_known_garbage_links
        store_id = getattr(self, "selected_store_id", None)
        store_clause = " AND dt.store_id=?" if store_id is not None else ""
        rows = self.db.safe_fetchall(f"""
            SELECT dt.id, s.name, p.name, p.title, dt.created_time
            FROM daily_tasks dt
            JOIN products p ON p.id=dt.product_id
            LEFT JOIN stores s ON s.id=dt.store_id
            WHERE dt.is_completed=1 AND dt.task_content LIKE '【垃圾链接】%'{store_clause}
            ORDER BY dt.created_time DESC, s.name, p.name
        """, (store_id,) if store_id is not None else ())
        self._set_result_table(
            "🗑 已知垃圾链接",
            f"已知链接共 {len(rows)} 个；点击“还原”后会重新显示主界面垃圾标签。",
            ["店铺", "商品ID", "商品标题", "记录时间", "操作"],
            [[store_name or "未分店铺", product_code, title or "", created_time, ""] for _task_id, store_name, product_code, title, created_time in rows],
        )
        for row_index, (task_id, *_values) in enumerate(rows):
            restore = QPushButton("还原")
            restore.clicked.connect(lambda _checked=False, tid=task_id: self._set_garbage_link_known(tid, False))
            self.result_table.setCellWidget(row_index, 4, restore)

    def _set_garbage_link_known(self, task_id, known):
        self.db.safe_execute("UPDATE daily_tasks SET is_completed=? WHERE id=?", (1 if known else 0, task_id))
        if self.main_app and hasattr(self.main_app, "autosave_current_archive"):
            self.main_app.autosave_current_archive()
        if self.main_app and hasattr(self.main_app, "force_refresh_frozen_table"):
            self.main_app.force_refresh_frozen_table()
        if self.main_app and hasattr(self.main_app, "update_daily_task_button_badge"):
            self.main_app.update_daily_task_button_badge()
        self.load_tasks()
        (self.analyze_garbage_links if known else self.show_known_garbage_links)()

    def analyze_missing_spec_images(self):
        self._current_analysis = self.analyze_missing_spec_images
        store_clause, params, store_name_filter = self._store_filter()

        rows = self.db.safe_fetchall(f"""
            SELECT s.name AS store_name,
                   p.name AS product_code,
                   p.title AS product_title,
                   ps.spec_name,
                   ps.spec_code
            FROM product_specs ps
            JOIN products p ON ps.product_id = p.id
            LEFT JOIN stores s ON p.store_id = s.id
            WHERE COALESCE(p.is_archived, 0)=0
              AND (ps.spec_image_data IS NULL OR length(ps.spec_image_data)=0)
              {store_clause}
            ORDER BY s.name, p.name, ps.spec_code
        """, params)

        table_rows = []
        product_ids = set()
        for store_name, product_code, product_title, spec_name, spec_code in rows:
            product_code = str(product_code or "").strip()
            if product_code:
                product_ids.add(product_code)
            table_rows.append([
                store_name or "未分店铺",
                product_code,
                product_title or "",
                spec_name or "",
                spec_code or "",
                "规格未上传图片",
            ])

        summary = (
            f"检查口径：只检查未归档商品；当前筛选：{store_name_filter}；只要商品下任意规格的规格图片为空，就列出该规格。\n"
            f"结果：涉及商品ID {len(product_ids)} 个，缺图规格 {len(table_rows)} 个。"
            if table_rows else
            f"检查口径：只检查未归档商品；当前筛选：{store_name_filter}；没有发现规格图片为空的规格。"
        )
        self._set_result_table(
            "🟣 规格图片检查",
            summary,
            ["店铺", "商品ID", "商品标题", "规格名称", "规格编码", "问题"],
            table_rows,
        )

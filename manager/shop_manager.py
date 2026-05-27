# ================= 版本信息 =================
VERSION = "3.13"

# ================= 系统标准库 =================
import sys
import os
import json
import calendar
import traceback
import re
import requests
import subprocess
import ctypes
import shutil
from datetime import datetime, timedelta

# Windows下隐藏控制台窗口的常量（防止黑框闪烁）
if sys.platform == 'win32':
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0

# ================= 第三方库 =================
from typing import TYPE_CHECKING
import psutil  # 系统资源监控
if TYPE_CHECKING:
    import pandas as pd  # type: ignore

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    import pandas as pd  # type: ignore
    HAS_OPENPYXL = True
    HAS_PANDAS = True
except ImportError as e:
    print(f"警告: 缺少依赖库 - {e}")
    HAS_OPENPYXL = False
    HAS_PANDAS = False

# ================= PyQt5 核心库 =================
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QInputDialog, QFileDialog, QMessageBox, QScrollArea, QTimeEdit,
    QTextEdit, QTextBrowser, QAbstractItemView, QFrame, QDialog, QComboBox,   
    QSpinBox, QTableView, QStyle, QStyledItemDelegate, QLineEdit,
    QCalendarWidget, QDateEdit, QStatusBar, QProgressBar, QProgressDialog, QSplitter,
    QGroupBox, QRadioButton, QCheckBox, QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QMenu, QAction, QToolBar, QSystemTrayIcon,
    QGraphicsDropShadowEffect, QSizePolicy, QShortcut, QStyleOptionViewItem,
    QToolTip
)

from PyQt5.QtCore import (
    Qt, QTimer, QEvent, QRect, QMimeData, QThread, pyqtSignal,
    QModelIndex, QSize, QPoint, QUrl, QSettings, QTranslator, QLocale,
    QAbstractTableModel, QSortFilterProxyModel, QTime, QDate
)

from PyQt5.QtGui import (
    QPixmap, QColor, QIcon, QFont, QDrag, QStandardItemModel, QStandardItem,
    QFontMetrics, QDoubleValidator, QIntValidator, QRegExpValidator,
    QPainter, QPen, QBrush, QCursor, QKeySequence, QPalette, QImage
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

import sqlite3
import os

try:
    from manager.db import SafeDatabaseManager
except ImportError:
    from db import SafeDatabaseManager

try:
    from manager.widgets import ProductWidget, StoreWidget, RecordRow, InPlaceEditor
except ImportError:
    from widgets import ProductWidget, StoreWidget, RecordRow, InPlaceEditor

try:
    from manager.dialogs import (
        OperationRecordDialog, DailyRecordDialog, StoreMarginDialog, CostImportDialog,
        CostLibraryDialog, ApiConfigDialog,
        ProfitAnalysisDialog, ProfitCalculatorDialog, ProfitHistoryDialog,
        DailyTaskDialog, TaskReminderPopupDialog, ProductSpecDialog,
    )
    from manager.dialogs.cost_import import read_cost_file, read_cost_row_colors
except ImportError:
    from dialogs import (
        OperationRecordDialog, DailyRecordDialog, StoreMarginDialog, CostImportDialog,
        CostLibraryDialog, ApiConfigDialog,
        ProfitAnalysisDialog, ProfitCalculatorDialog, ProfitHistoryDialog,
        DailyTaskDialog, TaskReminderPopupDialog, ProductSpecDialog,
    )
    from dialogs.cost_import import read_cost_file, read_cost_row_colors

try:
    from manager.delegates import SpecNameDelegate, CenterAlignDelegate, WeightDelegate
except ImportError:
    from delegates import SpecNameDelegate, CenterAlignDelegate, WeightDelegate

try:
    from manager.prompts import get_default_prompt
except ImportError:
    from prompts import get_default_prompt

try:
    from manager.ui_utils import convert_markdown_to_html
except ImportError:
    from ui_utils import convert_markdown_to_html


SINGLE_INSTANCE_KEY = "shop_manager_v3_7_single_instance"
SINGLE_INSTANCE_MUTEX_NAME = "shop_manager_v3_7_single_instance_mutex"
MAIN_WINDOW_TITLE = f"电商店铺操作记录管理工具 v{VERSION}"
ERROR_ALREADY_EXISTS = 183
SW_SHOW = 5
SW_RESTORE = 9


def notify_existing_instance():
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if not socket.waitForConnected(300):
        socket.abort()
        return False

    socket.write(b"activate")
    socket.flush()
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def acquire_single_instance_mutex():
    if sys.platform != 'win32':
        return None, False

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
    if not handle:
        return None, False
    return handle, kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def activate_existing_window_by_title():
    if sys.platform != 'win32':
        return False

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, MAIN_WINDOW_TITLE)
    if not hwnd:
        return False

    user32.ShowWindow(hwnd, SW_SHOW)
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True


def setup_single_instance(window_holder):
    if notify_existing_instance():
        return None, True

    server = QLocalServer()

    def activate_window():
        window = window_holder.get("window")
        if window is not None:
            window.show_window()

    def handle_new_connection():
        while server.hasPendingConnections():
            client = server.nextPendingConnection()
            client.readAll()
            client.disconnectFromServer()
        QTimer.singleShot(0, activate_window)

    if not server.listen(SINGLE_INSTANCE_KEY):
        if notify_existing_instance():
            return None, True
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        if not server.listen(SINGLE_INSTANCE_KEY):
            if notify_existing_instance():
                return None, True
            return None, False

    server.newConnection.connect(handle_new_connection)
    return server, False



class TodayColumnDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, today_col=-1):
        super().__init__(parent)
        self._today_col = today_col
        self._today_bg = QColor("#ffe0b2")
        self._today_text = QColor("#e65100")

    def set_today_col(self, col):
        self._today_col = col

    def paint(self, painter, option, index):
        if index.column() == self._today_col and self._today_col > 0:
            painter.fillRect(option.rect, self._today_bg)
            option.palette.setColor(QPalette.Text, self._today_text)
            option.palette.setColor(QPalette.HighlightedText, self._today_text)
        super().paint(painter, option, index)


class OperationRecordDelegate(TodayColumnDelegate):
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

    def __init__(self, parent=None, today_col=-1):
        super().__init__(parent, today_col)
        self._time_bg = QColor("#eef2f7")
        self._time_fg = QColor("#34495e")
        self._spec_bg = QColor("#e9f2ff")
        self._spec_fg = QColor("#245269")
        self._text_fg = QColor("#1f2d3d")
        self._selected_bg = QColor("#ffe0b2")
        self._fallback_font = QFont("Microsoft YaHei", 11)
        self._fallback_font.setBold(True)

    def paint(self, painter, option, index):
        records = index.data(Qt.UserRole)
        if not self._has_structured_records(records):
            super().paint(painter, option, index)
            return

        painter.save()
        self._paint_background(painter, option, index)
        painter.setClipRect(option.rect.adjusted(1, 1, -1, -1))

        x = option.rect.left() + 5
        y = option.rect.top() + 5
        right = option.rect.right() - 5
        line_height = 22
        normal_font = QFont("Microsoft YaHei", 10)
        bold_font = QFont("Microsoft YaHei", 10)
        bold_font.setBold(True)

        for part in self._record_parts(records):
            if y + line_height > option.rect.bottom() - 2:
                break
            cx = x
            time_text = part.get("time", "")
            if time_text:
                cx = self._draw_pill(painter, cx, y, time_text, self._time_bg, self._time_fg, bold_font, right)

            metric = part.get("metric", "记录")
            bg, fg = self._metric_colors(metric)
            cx = self._draw_pill(painter, cx, y, metric, bg, fg, bold_font, right)

            spec_text = part.get("spec", "")
            if spec_text:
                spec_width = QFontMetrics(bold_font).horizontalAdvance(spec_text) + 12
                if cx + spec_width > right:
                    y += line_height
                    if y + line_height > option.rect.bottom() - 2:
                        break
                    cx = x
                y = self._draw_wrapped_block(painter, cx, y + 2, spec_text, self._spec_bg, self._spec_fg, bold_font, right)
                cx = x

            text = part.get("text", "")
            if text:
                start_x = cx if cx > x else x
                if start_x >= right:
                    start_x = x
                    y += line_height
                if y + line_height > option.rect.bottom() - 2:
                    break
                y = self._draw_wrapped_text(painter, start_x, y, text, normal_font, right, option.rect.bottom() - 2)
            else:
                y += line_height

        painter.restore()

    def _paint_background(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, self._selected_bg)
            return
        bg = index.data(Qt.BackgroundRole)
        if isinstance(bg, QBrush) and bg.style() != Qt.NoBrush:
            painter.fillRect(option.rect, bg)
            return
        if index.column() == self._today_col and self._today_col > 0:
            painter.fillRect(option.rect, self._today_bg)
            return
        painter.fillRect(option.rect, option.palette.base())

    def _has_structured_records(self, records):
        if not isinstance(records, list):
            return False
        return any(
            isinstance(r, dict) and (r.get("changes") or str(r.get("text", "") or "").strip())
            for r in records
        )

    def _record_parts(self, records):
        parts = []
        for record in records or []:
            if not isinstance(record, dict):
                continue
            time_text = str(record.get("time", "") or "")
            changes = record.get("changes") or []
            if changes:
                for change in changes:
                    if not isinstance(change, dict):
                        continue
                    text = str(change.get("text", "") or "")
                    metric = str(change.get("metric", "记录") or "记录")
                    spec, cleaned = self._extract_spec_text(metric, text, change)
                    parts.append({
                        "time": str(change.get("time", "") or time_text),
                        "metric": metric,
                        "spec": spec,
                        "text": cleaned or text,
                    })
            elif record.get("text"):
                parts.append({"time": time_text, "metric": "记录", "spec": "", "text": str(record.get("text", ""))})
        return parts

    def _metric_colors(self, metric):
        for key, colors in self.METRIC_STYLES.items():
            if key in metric:
                return QColor(colors[0]), QColor(colors[1])
        return QColor("#edf2f7"), QColor("#34495e")

    def _extract_spec_text(self, metric, text, change):
        if "规格" not in metric and "规格" not in text:
            return "", text

        bracket_matches = re.findall(r"\[([^\]]{1,80})\]", text)
        if bracket_matches:
            spec = bracket_matches[0].strip()
            cleaned = re.sub(r"\s*\[[^\]]{1,80}\]\s*", " ", text, count=1).strip()
            return spec, cleaned

        old_value = str(change.get("old", "") or "").strip()
        new_value = str(change.get("new", "") or "").strip()
        if metric == "规格名称" and (old_value or new_value):
            return (new_value or old_value), "规格名称已修改"

        for pattern in (
            r"^(.{1,80}?)(?:售价设置为|设置售价到|从.+?(?:涨价到|降价到))",
            r"^(?:新增规格|删除规格)\s*[:：]?\s*(.{1,80})$",
        ):
            match = re.search(pattern, text)
            if match:
                spec = match.group(1).strip()
                cleaned = text.replace(spec, "", 1).strip()
                return spec, cleaned
        return "", text

    def _draw_pill(self, painter, x, y, text, bg_color, fg_color, font, right, max_width=None):
        painter.setFont(font)
        fm = QFontMetrics(font)
        width = fm.horizontalAdvance(text) + 12
        if max_width:
            width = min(width, max_width)
        if x + width > right:
            return x
        rect = QRect(x, y + 2, width, 18)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(fg_color)
        elided = fm.elidedText(text, Qt.ElideRight, width - 10)
        painter.drawText(rect.adjusted(5, 0, -5, 0), Qt.AlignCenter, elided)
        return x + width + 4

    def _draw_wrapped_block(self, painter, x, y, text, bg_color, fg_color, font, right):
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(QRect(0, 0, max(20, right - x - 10), 1000), Qt.TextWordWrap, text)
        rect = QRect(x, y, max(20, right - x), text_rect.height() + 8)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(fg_color)
        painter.drawText(rect.adjusted(5, 4, -5, -4), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
        return rect.bottom() + 4

    def _draw_wrapped_text(self, painter, x, y, text, font, right, bottom):
        painter.setFont(font)
        painter.setPen(self._text_fg)
        fm = QFontMetrics(font)
        rect = QRect(x, y + 2, max(20, right - x), max(18, bottom - y))
        bounds = fm.boundingRect(rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
        painter.drawText(rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, text)
        return min(bottom + 1, y + max(22, bounds.height() + 6))


class CloudSyncProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("云同步")
        self.setFixedSize(380, 140)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint & ~Qt.WindowCloseButtonHint)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)

        self.status_label = QLabel("正在准备...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 13px; color: #333; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 10px;
                background-color: #f0f0f0;
                text-align: center;
                font-size: 11px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 10px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def set_status(self, text, value=None):
        self.status_label.setText(text)
        if value is not None:
            self.progress_bar.setValue(value)

    def set_error(self, text):
        self.status_label.setText(text)
        self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c; font-weight: bold;")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 10px;
                background-color: #f0f0f0;
                text-align: center;
                font-size: 11px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #e74c3c;
                border-radius: 10px;
            }
        """)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(500, 450)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("⚙️ 程序设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        layout.addWidget(QLabel("<hr>"))

        self.auto_start_checkbox = QCheckBox("开机自启")
        self.auto_start_checkbox.setStyleSheet("""
            QCheckBox {
                spacing: 10px;
                font-size: 14px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
        """)
        self.auto_start_checkbox.setToolTip("勾选后，程序将在Windows启动时自动运行")
        layout.addWidget(self.auto_start_checkbox)

        layout.addSpacing(10)
        layout.addWidget(QLabel("<hr>"))

        shortcuts_title = QLabel("⌨️ 快捷键说明")
        shortcuts_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; padding-top: 5px;")
        layout.addWidget(shortcuts_title)

        shortcuts_table = QTableWidget()
        shortcuts_table.setColumnCount(2)
        shortcuts_table.setHorizontalHeaderLabels(["快捷键", "功能说明"])
        shortcuts_table.setRowCount(2)
        shortcuts_table.verticalHeader().setVisible(False)
        shortcuts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        shortcuts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        shortcuts_table.setItem(0, 0, QTableWidgetItem("Ctrl+F"))
        shortcuts_table.setItem(0, 1, QTableWidgetItem("聚焦搜索框，快速搜索商品"))
        shortcuts_table.setItem(1, 0, QTableWidgetItem("Ctrl+S"))
        shortcuts_table.setItem(1, 1, QTableWidgetItem("快速云同步，自动上传数据到云端"))
        
        shortcuts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        shortcuts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        shortcuts_table.setColumnWidth(0, 100)
        shortcuts_table.verticalHeader().setDefaultSectionSize(35)
        shortcuts_table.setFixedHeight(100)
        shortcuts_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #f9f9f9;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 5px 10px;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 6px;
                border: none;
            }
        """)
        
        layout.addWidget(shortcuts_table)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_save = QPushButton("保存")
        btn_save.setFixedSize(100, 35)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        btn_save.clicked.connect(self.save_settings)
        btn_layout.addWidget(btn_save)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedSize(100, 35)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)

    def load_settings(self):
        is_enabled = self._is_auto_start_enabled()
        self.auto_start_checkbox.setChecked(is_enabled)

    def _is_auto_start_enabled(self):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ
            )
            try:
                value, _ = winreg.QueryValueEx(key, "ShopManager")
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception as e:
            print(f"检查开机自启状态失败: {e}")
            return False

    def _set_auto_start(self, enabled):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            
            if enabled:
                app_path = sys.executable
                winreg.SetValueEx(key, "ShopManager", 0, winreg.REG_SZ, app_path)
            else:
                try:
                    winreg.DeleteValue(key, "ShopManager")
                except FileNotFoundError:
                    pass
            
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"设置开机自启失败: {e}")
            return False

    def save_settings(self):
        auto_start_enabled = self.auto_start_checkbox.isChecked()
        
        if self._set_auto_start(auto_start_enabled):
            QMessageBox.information(self, "成功", "设置已保存！")
            self.accept()
        else:
            QMessageBox.warning(self, "错误", "设置保存失败，请以管理员权限运行程序！")
            self.reject()


class ShopManagerApp(QMainWindow):
    PRODUCT_ROW_HEIGHT = 160
    STORE_ROW_HEIGHT = 140
    
    def __init__(self):
        
        super().__init__()
        self.db = SafeDatabaseManager()
        self.db.init_default_prompts()
        
        if getattr(sys, 'frozen', False):
            script_dir = os.path.dirname(sys.executable)
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.current_date = datetime.now()
        self.year = self.current_date.year
        self.month = self.current_date.month
        self.row_store_map = {}
        self.row_data_map = {}
        self.product_store_map = {}
        self.product_sort_mode = self.db.get_setting("product_sort_mode", "order") or "order"

        self.is_loading = False  # 防止重复加载
        self._is_quitting = False  # 防止退出时重复触发自动上传
        self._is_switching_local_account = False  # 防止本地账号切换重复触发
        self._today_col = -1  # 今日列索引，-1表示不是当月
        self._startup_locate_today_pending = True
        self.current_category_filter = ""
        self.current_search_match_ids = None
        self._search_highlighted_rows = set()
        self._tag_filter_global_filter_installed = False
        self.current_store_filter = set()  # 店铺筛选状态
        self.daily_task_dialog = None
        self._active_reminder_ids = set()
        self._task_reminder_popup_active = False
        self._record_tooltip_cell = None
        self._record_tooltip_text = ""
        self._record_tooltip_pos = QPoint()

        # 初始化云同步管理器
        self.cloud_manager = None
        try:
            from manager.cloud_sync import CloudSyncManager
            self.cloud_manager = CloudSyncManager(self.db)
        except Exception as e:
            print(f"云同步管理器初始化失败: {e}")

        self.init_ui()
        self.load_data_safe()
        self.update_cloud_account_label()

        self.installEventFilter(self)
        
        # 初始化系统托盘
        self.init_system_tray()
        
        # 初始化快捷键
        self.init_shortcuts()
        self.start_global_reminder_check()
        
        

    def start_global_reminder_check(self):
        """启动主界面的全局待办提醒检查。"""
        self.task_reminder_timer = QTimer(self)
        self.task_reminder_timer.timeout.connect(self.check_due_task_reminders)
        self.task_reminder_timer.start(10000)
        QTimer.singleShot(500, self.check_due_task_reminders)

    def check_due_task_reminders(self):
        """检查已到时间的待办提醒，并按顺序强制弹窗。"""
        if getattr(self, "_task_reminder_popup_active", False):
            return
        try:
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = self.db.safe_fetchall(
                """SELECT id, store_id, product_id, task_content, remind_time
                   FROM task_reminders
                   WHERE is_reminded = 0 AND remind_time <= ?
                   ORDER BY remind_time ASC
                   LIMIT 1""",
                (now_text,)
            )
            if not rows:
                return
            rem_id, store_id, product_id, task_content, remind_time = rows[0]
            if rem_id in self._active_reminder_ids:
                return

            reminder = self._build_task_reminder_payload(rem_id, store_id, product_id, task_content, remind_time)
            self._active_reminder_ids.add(rem_id)
            self._task_reminder_popup_active = True
            try:
                self.show_window()
                dialog = TaskReminderPopupDialog(reminder, self)
                dialog.raise_()
                dialog.activateWindow()
                result = dialog.exec_()
                if result == QDialog.Accepted and getattr(dialog, "completed", False):
                    self.db.safe_execute("DELETE FROM task_reminders WHERE id = ?", (rem_id,))
                    self._refresh_after_task_reminder_completed(product_id)
            finally:
                self._active_reminder_ids.discard(rem_id)
                self._task_reminder_popup_active = False
                QTimer.singleShot(100, self.check_due_task_reminders)
        except Exception as e:
            self._task_reminder_popup_active = False
            print(f"全局待办提醒检查失败: {e}")

    def _build_task_reminder_payload(self, rem_id, store_id, product_id, task_content, remind_time):
        store_name = ""
        product_code = str(product_id)
        product_title = ""
        try:
            store_rows = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
            if store_rows and store_rows[0][0]:
                store_name = store_rows[0][0]
        except Exception:
            pass
        try:
            product_rows = self.db.safe_fetchall("SELECT name, title FROM products WHERE id=?", (product_id,))
            if product_rows and product_rows[0][0]:
                product_code = str(product_rows[0][0])
                product_title = product_rows[0][1] or ""
        except Exception:
            pass
        return {
            "id": rem_id,
            "store_id": store_id,
            "store_name": store_name,
            "product_id": product_id,
            "product_code": product_code,
            "product_title": product_title,
            "task_content": task_content,
            "remind_time": remind_time,
        }

    def _refresh_after_task_reminder_completed(self, product_id):
        try:
            self.force_refresh_product_widget(product_id)
        except Exception as e:
            print(f"刷新提醒商品标签失败: {e}")
        dialog = getattr(self, "daily_task_dialog", None)
        if dialog:
            try:
                dialog.load_reminders()
                dialog.load_tasks()
            except Exception as e:
                print(f"刷新每日任务窗口失败: {e}")

    def init_system_tray(self):
        """初始化系统托盘"""
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.create_star_icon()
        self.tray_icon.setIcon(icon)
        
        tray_menu = QMenu()
        self.show_action = QAction("⭐ 显示主窗口", self)
        self.show_action.triggered.connect(self.show_window)
        tray_menu.addAction(self.show_action)
        
        tray_menu.addSeparator()
        
        self.shortcuts_action = QAction("⌨️ 快捷键", self)
        self.shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        tray_menu.addAction(self.shortcuts_action)
        
        self.settings_action = QAction("⚙️ 设置", self)
        self.settings_action.triggered.connect(self.show_settings_dialog)
        tray_menu.addAction(self.settings_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("❌ 退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
        
        self.tray_icon.showMessage(
            "电商店铺操作记录管理工具",
            "程序已最小化到系统托盘，双击图标可显示窗口",
            QSystemTrayIcon.Information,
            3000
        )
    
    def create_star_icon(self):
        """创建星星图标"""
        import sys
        if getattr(sys, 'frozen', False):
            icons_dir = os.path.join(sys._MEIPASS, "manager", "icons")
        else:
            icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        svg_path = os.path.join(icons_dir, "xingxing.svg")
        if os.path.exists(svg_path):
            renderer = QSvgRenderer(svg_path)
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)
        else:
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            font = QFont()
            font.setPixelSize(24)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "⭐")
            painter.end()
            return QIcon(pixmap)
    
    def on_tray_activated(self, reason):
        """托盘图标被激活时的处理"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()
    
    def show_window(self):
        """显示窗口"""
        self.showNormal()
        self.raise_()
        self.activateWindow()
    
    def open_knowledge_base(self):
        """打开知识库（已禁用）"""
        self.show_knowledge_base_disabled()

    def open_pinduoduo(self):
        """打开拼多多商家后台"""
        import webbrowser
        url = "https://mms.pinduoduo.com/login/?redirectUrl=https%3A%2F%2Fmms.pinduoduo.com%2F"
        webbrowser.open(url)
        self.statusBar().showMessage(f"已打开拼多多商家后台: {url}", 3000)

    def show_settings_dialog(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        dialog.exec_()

    def show_shortcuts_dialog(self):
        """打开快捷键说明对话框（复用设置对话框）"""
        self.show_settings_dialog()

    def init_shortcuts(self):
        """初始化快捷键（仅在主界面激活时生效）"""
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.quick_cloud_sync)

    def focus_search(self):
        """聚焦搜索框，全选文本"""
        self.search_input.setFocus()
        self.search_input.selectAll()

    def ensure_upload_account_allowed(self, target_account):
        """确保本地表格数据只能上传到其归属账号。"""
        if not self.cloud_manager or not target_account:
            return False

        active_account = self.cloud_manager.get_active_data_account()
        if active_account:
            if active_account.get('id') == target_account.get('id'):
                return True
            QMessageBox.warning(
                self,
                "账号不一致，已取消上传",
                f"当前表格数据属于账号：{active_account.get('name', '未知')}\n"
                f"你当前选择的云同步账号：{target_account.get('name', '未知')}\n\n"
                f"为避免覆盖错误存档，本次上传已取消。\n"
                f"请先切换到正确账号，或下载对应账号的数据后再上传。"
            )
            return False

        reply = QMessageBox.question(
            self,
            "确认数据归属账号",
            f"当前本地表格数据还没有绑定云同步账号。\n\n"
            f"是否确认这份本地数据属于账号：{target_account.get('name', '未知')}？\n\n"
            f"确认后以后只能上传到这个账号，避免误覆盖其他账号存档。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return False
        self.cloud_manager.set_active_data_account(target_account['id'])
        self.update_cloud_account_label()
        return True

    def quick_cloud_sync(self):
        """快速云同步 - 弹窗进度条 + 完成后自动关闭并气泡提示"""
        if not self.cloud_manager:
            self.show_toast("❌ 云同步未初始化", 1000)
            return

        current = self.cloud_manager.get_current_account()
        if not current:
            self.show_toast("⚠️ 请先登录云同步账号", 1000)
            return
        if not self.ensure_upload_account_allowed(current):
            return

        progress_dialog = CloudSyncProgressDialog(self)
        progress_dialog.set_status("💾 正在备份本地数据...", 10)
        progress_dialog.show()
        QApplication.processEvents()

        try:
            local_backup_ok, local_backup_result = self.cloud_manager.save_local_backup_before_upload(current['id'])
            if not local_backup_ok:
                progress_dialog.set_error(f"❌ 本地备份失败: {local_backup_result}")
                progress_dialog.progress_bar.setValue(100)
                QTimer.singleShot(1500, progress_dialog.close)
                QMessageBox.warning(self, "上传已取消", f"本地上传前备份失败，已取消上传：\n{local_backup_result}")
                return

            progress_dialog.set_status("⏳ 正在导出本地数据...", 25)
            QApplication.processEvents()
            data = self.cloud_manager.export_data_to_json()
            if not data:
                progress_dialog.set_error("❌ 数据导出失败")
                progress_dialog.progress_bar.setValue(100)
                QTimer.singleShot(800, progress_dialog.close)
                QTimer.singleShot(1600, lambda: self.show_toast("❌ 数据导出失败", 1000))
                return

            progress_dialog.set_status("💾 正在备份云端旧数据...", 40)
            QApplication.processEvents()

            uploader = self._create_cos_uploader(current)
            cloud_ok, cloud_result = uploader.download_json(current['folder'])
            cloud_backup_path = "云端无旧数据"
            if cloud_ok and cloud_result:
                backup_ok, backup_result = self.cloud_manager.save_cloud_backup_before_upload(current['id'], cloud_result)
                if not backup_ok:
                    progress_dialog.set_error(f"❌ 云端旧数据备份失败: {backup_result}")
                    progress_dialog.progress_bar.setValue(100)
                    QTimer.singleShot(1500, progress_dialog.close)
                    QMessageBox.warning(self, "上传已取消", f"云端旧数据备份失败，已取消上传：\n{backup_result}")
                    return
                cloud_backup_path = backup_result
            elif not cloud_ok and "云端没有数据" not in str(cloud_result):
                progress_dialog.set_error(f"❌ 云端旧数据读取失败: {cloud_result}")
                progress_dialog.progress_bar.setValue(100)
                QTimer.singleShot(1500, progress_dialog.close)
                QMessageBox.warning(self, "上传已取消", f"云端旧数据读取失败，已取消上传：\n{cloud_result}")
                return

            progress_dialog.set_status("☁️ 正在上传到云端...", 70)
            QApplication.processEvents()

            success, result = uploader.upload_json(data, current['folder'])
            if success:
                self.cloud_manager.update_last_upload_time(current['id'])
                progress_dialog.set_status("✅ 上传完成", 100)
                QApplication.processEvents()
                QTimer.singleShot(500, progress_dialog.close)
                QTimer.singleShot(1000, lambda l=local_backup_result: self.show_toast(f"✅ 已上传云同步，本地备份已保留(最多5份): {l}", 1800))
            else:
                progress_dialog.set_error(f"❌ 上传失败: {result}")
                progress_dialog.progress_bar.setValue(100)
                QTimer.singleShot(1500, progress_dialog.close)
                QTimer.singleShot(2000, lambda r=result: self.show_toast(f"❌ 上传失败: {r}", 1000))

        except Exception as e:
            print(f"快速云同步失败: {e}")
            progress_dialog.set_error(f"❌ 上传异常")
            progress_dialog.progress_bar.setValue(100)
            QTimer.singleShot(1500, progress_dialog.close)
            QTimer.singleShot(2000, lambda: self.show_toast(f"❌ 上传异常", 1000))

    def _create_cos_uploader(self, account):
        try:
            from manager.cloud_sync import TencentCOSUploader
        except ImportError:
            from cloud_sync import TencentCOSUploader

        return TencentCOSUploader(
            account['secret_id'],
            account['secret_key'],
            account['bucket'],
            account['region']
        )

    def _normalized_sync_data(self, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized.pop('export_time', None)
        return normalized

    def _is_cloud_data_changed(self, cloud_data):
        local_data = self.cloud_manager.export_data_to_json()
        if not local_data:
            return True

        local_normalized = self._normalized_sync_data(local_data)
        cloud_normalized = self._normalized_sync_data(cloud_data)
        return json.dumps(local_normalized, ensure_ascii=False, sort_keys=True) != json.dumps(cloud_normalized, ensure_ascii=False, sort_keys=True)

    def replace_database_from_local_profile(self, profile_path, account_id):
        """用本地账号档案替换当前主库，并刷新界面。"""
        if not os.path.exists(profile_path):
            return False, "本地账号数据文件不存在"

        profile_path = os.path.abspath(profile_path)
        db_path = os.path.abspath(self.db.db_path)
        temp_path = f"{db_path}.switching"

        if profile_path == db_path:
            return True, db_path

        try:
            if hasattr(self, '_scroll_save_timer') and self._scroll_save_timer.isActive():
                self._scroll_save_timer.stop()

            try:
                self.db.conn.commit()
            except Exception:
                pass
            try:
                self.db.conn.close()
            except Exception:
                pass

            if os.path.exists(temp_path):
                os.remove(temp_path)
            shutil.copy2(profile_path, temp_path)
            os.replace(temp_path, db_path)

            self.db = SafeDatabaseManager()
            if self.cloud_manager:
                self.cloud_manager.db = self.db
            self.load_data_safe()
            if self.cloud_manager:
                self.cloud_manager.set_active_data_account(account_id)
            self.update_cloud_account_label()
            return True, db_path
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            try:
                self.db = SafeDatabaseManager()
                if self.cloud_manager:
                    self.cloud_manager.db = self.db
            except Exception:
                pass
            return False, str(e)

    def _resolve_next_local_profile_account(self):
        """按当前应用账号自动推断下一个要切换的本地账号。"""
        if not self.cloud_manager:
            return None, None, "云同步管理器未初始化"

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

    def show_local_account_switch_menu(self):
        """显示可切换的本地账号列表，点击账号后自动切换。"""
        if self._is_switching_local_account:
            return
        if not self.cloud_manager:
            QMessageBox.warning(self, "提示", "云同步管理器未初始化")
            return

        available_profiles = self.cloud_manager.get_accounts_with_local_profiles()
        if not available_profiles:
            QMessageBox.warning(self, "提示", "没有找到任何本地账号数据。")
            return

        active_account = self.cloud_manager.get_active_data_account()
        active_id = active_account.get('id') if active_account else None
        menu = QMenu(self)
        for account, _profile_path in available_profiles:
            account_id = account.get('id')
            account_name = account.get('name', '未知')
            action_text = f"✓ {account_name}" if account_id == active_id else account_name
            action = QAction(action_text, menu)
            action.setEnabled(account_id != active_id)
            action.triggered.connect(lambda _checked=False, acc=account, aid=account_id: self.switch_local_account(acc, aid))
            menu.addAction(action)

        if menu.isEmpty():
            QMessageBox.warning(self, "提示", "没有可切换的本地账号数据。")
            return

        menu.exec_(self.btn_switch_local_account.mapToGlobal(self.btn_switch_local_account.rect().bottomLeft()))

    def switch_local_account(self, target_account=None, target_id=None):
        """切换到指定本地账号；未指定时兼容旧逻辑切到下一个账号。"""
        if self._is_switching_local_account:
            return

        self._is_switching_local_account = True
        if hasattr(self, 'btn_switch_local_account'):
            self.btn_switch_local_account.setEnabled(False)

        try:
            if not self.cloud_manager:
                QMessageBox.warning(self, "提示", "云同步管理器未初始化")
                return

            if target_account is None or target_id is None:
                target_account, target_id, error = self._resolve_next_local_profile_account()
                if error:
                    QMessageBox.warning(self, "提示", error)
                    return

            profile_ok, profile_path = self.cloud_manager.load_local_profile(target_id)
            if not profile_ok:
                QMessageBox.warning(
                    self,
                    "提示",
                    f"账号「{target_account.get('name', '未知')}」暂无本地数据。\n请先保存该账号本地数据，或从云端下载一次。"
                )
                return

            normalize_ok, normalized_path = self.cloud_manager.ensure_local_profile_normalized(target_id, profile_path)
            if not normalize_ok:
                QMessageBox.critical(self, "错误", f"本地账号数据迁移失败：{normalized_path}")
                return
            profile_path = normalized_path

            active_account = self.cloud_manager.get_active_data_account()
            if not active_account:
                current = self.cloud_manager.get_current_account()
                if not current:
                    QMessageBox.warning(self, "请先绑定当前数据", "当前主表格数据还没有绑定本地账号，请先在云同步中选择当前数据所属账号。")
                    return

                if not self.cloud_manager.set_active_data_account(current['id']):
                    QMessageBox.critical(self, "错误", "绑定当前应用账号失败")
                    return
                active_account = current
                self.update_cloud_account_label()

            if active_account.get('id') == target_id:
                QMessageBox.information(self, "提示", f"当前主表格已经是账号「{target_account.get('name', '未知')}」的数据。")
                return

            save_ok, save_result = self.cloud_manager.save_local_profile(active_account['id'])
            if not save_ok:
                QMessageBox.critical(self, "切换已取消", f"当前应用账号数据保存失败，已取消切换：\n{save_result}")
                return

            ok, result = self.replace_database_from_local_profile(profile_path, target_id)
            if ok:
                self.cloud_manager.switch_account(target_id)
                self.update_cloud_account_label()
                self.show_toast(f"✅ 已切换到：{target_account.get('name', '未知')}", 1500)
            else:
                QMessageBox.critical(self, "错误", f"应用本地账号失败：{result}")
        finally:
            self._is_switching_local_account = False
            if hasattr(self, 'btn_switch_local_account'):
                self.btn_switch_local_account.setEnabled(True)

    def auto_upload_on_exit(self):
        """退出软件时自动保存本地备份并上传一次数据。"""
        if not self.cloud_manager:
            return True

        current = self.cloud_manager.get_current_account()
        if not current:
            return True
        if not self.ensure_upload_account_allowed(current):
            return False

        reply = QMessageBox.question(
            self,
            "退出前云同步",
            f"是否在退出前上传并备份当前本地数据？\n\n"
            f"当前应用账号：{self.cloud_manager.get_active_data_account().get('name', current.get('name', '未知'))}\n"
            f"云端文件夹：{current.get('folder', '') or '默认'}\n\n"
            f"选择“是”：先保存本地备份，再用本地数据覆盖云端。\n"
            f"选择“否”：不上传，直接退出。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return True

        progress_dialog = CloudSyncProgressDialog(self)
        progress_dialog.setWindowTitle("退出前云同步")
        progress_dialog.set_status("💾 正在备份本地数据...", 20)
        progress_dialog.show()
        QApplication.processEvents()

        try:
            try:
                self.db.conn.commit()
            except Exception:
                pass

            progress_dialog.set_status("💾 正在备份本地数据...", 25)
            QApplication.processEvents()
            local_backup_ok, local_backup_result = self.cloud_manager.save_local_backup_before_upload(current['id'])
            if not local_backup_ok:
                progress_dialog.set_error(f"❌ 本地备份失败: {local_backup_result}")
                QApplication.processEvents()
                QMessageBox.warning(self, "退出前上传失败", f"本地上传前备份失败，已取消自动上传：\n{local_backup_result}")
                return False

            progress_dialog.set_status("📦 正在导出本地数据...", 45)
            QApplication.processEvents()
            data = self.cloud_manager.export_data_to_json()
            if not data:
                progress_dialog.set_error("❌ 数据导出失败")
                QApplication.processEvents()
                QMessageBox.warning(self, "退出前上传失败", "数据导出失败，已取消自动上传。")
                return False

            progress_dialog.set_status("💾 正在备份云端旧数据...", 60)
            QApplication.processEvents()
            uploader = self._create_cos_uploader(current)
            cloud_ok, cloud_result = uploader.download_json(current['folder'])
            if cloud_ok and cloud_result:
                backup_ok, backup_result = self.cloud_manager.save_cloud_backup_before_upload(current['id'], cloud_result)
                if not backup_ok:
                    progress_dialog.set_error(f"❌ 云端旧数据备份失败: {backup_result}")
                    QApplication.processEvents()
                    QMessageBox.warning(self, "退出前上传失败", f"云端旧数据备份失败，已取消上传：\n{backup_result}")
                    return False
            elif not cloud_ok and "云端没有数据" not in str(cloud_result):
                progress_dialog.set_error(f"❌ 云端旧数据读取失败: {cloud_result}")
                QApplication.processEvents()
                QMessageBox.warning(self, "退出前上传失败", f"云端旧数据读取失败，已取消上传：\n{cloud_result}")
                return False

            progress_dialog.set_status("☁️ 正在上传到云端...", 70)
            QApplication.processEvents()
            success, result = uploader.upload_json(data, current['folder'])
            if success:
                self.cloud_manager.update_last_upload_time(current['id'])
                progress_dialog.set_status("✅ 上传完成，正在退出...", 100)
                QApplication.processEvents()
                QTimer.singleShot(300, progress_dialog.close)
                return True

            progress_dialog.set_error(f"❌ 上传失败: {result}")
            QApplication.processEvents()
            QMessageBox.warning(self, "退出前上传失败", f"云端上传失败：\n{result}")
            return False
        except Exception as e:
            print(f"退出自动上传失败: {e}")
            progress_dialog.set_error("❌ 上传异常")
            QApplication.processEvents()
            QMessageBox.warning(self, "退出前上传失败", f"上传异常：\n{str(e)}")
            return False
        finally:
            progress_dialog.close()

    def quit_application(self):
        """退出应用"""
        if self._is_quitting:
            return
        self._is_quitting = True
        if not self.auto_upload_on_exit():
            self._is_quitting = False
            return
        self.tray_icon.hide()
        QApplication.quit()
    
    def closeEvent(self, event):
        """关闭事件处理 - 最小化到托盘而不是退出"""
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "电商店铺操作记录管理工具",
                "程序已最小化到系统托盘，双击图标可显示窗口",
                QSystemTrayIcon.Information,
                2000
            )
            event.ignore()
        else:
            event.accept()
    
    def changeEvent(self, event):
        """窗口状态改变事件"""
        if event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                # 最小化到任务栏（默认行为，不做额外处理）
                pass
        super().changeEvent(event)

    def center_on_screen(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen:
            return
        screen_rect = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(screen_rect.center())
        frame.moveTop(max(screen_rect.top(), frame.top() - 40))
        self.move(frame.topLeft())

    def init_ui(self):
        self.setWindowTitle(MAIN_WINDOW_TITLE)
        self.resize(1350, 1000)
        self.center_on_screen()

        # 调试标签
        self.debug_label = QLabel("🔧 调试: shop_manager.py (ShopManagerApp)")
        self.debug_label.setStyleSheet("font-size: 10px; color: #999; background-color: #f0f0f0; padding: 2px 8px; border-bottom: 1px solid #ddd;")
        self.debug_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.debug_label.setCursor(Qt.IBeamCursor)

        # 系统资源监控显示（顶部细条）
        self.resource_label = QLabel("📊 系统资源: 初始化...")
        self.resource_label.setStyleSheet("""
            background-color: #2c3e50; 
            color: #ecf0f1; 
            font-size: 10px; 
            padding: 1px 10px;
        """)
        self.resource_label.setFixedHeight(18)
        self.resource_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # 启动资源监控定时器
        self.resource_timer = QTimer()
        self.resource_timer.timeout.connect(self.update_resource_usage)
        self.resource_timer.start(3000)  # 每3秒更新一次

        toolbar = QHBoxLayout()
        btn_prev = QPushButton("◀ 上个月")
        btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 1px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        btn_prev.clicked.connect(self.prev_month)
        self.lbl_month = QLabel(f"{self.year}年 {self.month}月")
        self.lbl_month.setFont(QFont("Arial", 14, QFont.Bold))
        btn_next = QPushButton("下个月 ▶")
        btn_next.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 1px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        btn_next.clicked.connect(self.next_month)
        
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品ID、标题或备注...")
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.apply_realtime_search)
        self.search_input.textChanged.connect(lambda: self.search_timer.start(200))
        
        self.btn_tag_filter = QPushButton("🏷️ 筛选")
        self.btn_tag_filter.setFixedWidth(80)
        self.btn_tag_filter.setStyleSheet("""
            QPushButton {
                border: 1px solid #3498db;
                background-color: transparent;
                color: #3498db;
                border-radius: 3px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3498db;
                color: white;
            }
        """)
        self.btn_tag_filter.clicked.connect(self.show_tag_filter_menu)

        self.btn_store_filter = QPushButton("🏪 店铺")
        self.btn_store_filter.setFixedWidth(80)
        self.btn_store_filter.setStyleSheet("""
            QPushButton {
                border: 1px solid #27ae60;
                background-color: transparent;
                color: #27ae60;
                border-radius: 3px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27ae60;
                color: white;
            }
        """)
        self.btn_store_filter.clicked.connect(self.show_store_filter_menu)

        self.tag_filter_menu = QDialog(self)
        self.tag_filter_menu.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.tag_filter_menu.setModal(False)
        self.tag_filter_menu.setStyleSheet("""
            QDialog {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            QCheckBox {
                padding: 5px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        
        filter_layout = QVBoxLayout(self.tag_filter_menu)
        filter_layout.setContentsMargins(10, 10, 10, 10)
        filter_layout.setSpacing(5)
        
        filter_title = QLabel("🏷️ 选择筛选标签")
        filter_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50; padding-bottom: 5px;")
        filter_layout.addWidget(filter_title)

        category_title = QLabel("商品类型筛选")
        category_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #2c3e50;")
        filter_layout.addWidget(category_title)

        self.category_filter_input = QLineEdit()
        self.category_filter_input.setPlaceholderText("输入商品类型关键字...")
        self.category_filter_input.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.category_filter_input.setInputMethodHints(Qt.ImhNone)
        self.category_filter_input.textChanged.connect(self.refresh_category_filter_candidates)
        filter_layout.addWidget(self.category_filter_input)

        self.category_candidate_widget = QWidget()
        self.category_candidate_layout = QVBoxLayout(self.category_candidate_widget)
        self.category_candidate_layout.setContentsMargins(0, 0, 0, 0)
        self.category_candidate_layout.setSpacing(4)
        filter_layout.addWidget(self.category_candidate_widget)

        self.btn_clear_category_filter = QPushButton("清除类型筛选")
        self.btn_clear_category_filter.setStyleSheet("""
            QPushButton {
                border: 1px solid #7f8c8d;
                background-color: transparent;
                color: #7f8c8d;
                border-radius: 4px;
                padding: 5px 10px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
                color: white;
            }
        """)
        self.btn_clear_category_filter.clicked.connect(self.clear_category_filter)
        filter_layout.addWidget(self.btn_clear_category_filter)
        
        icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        
        filter_layout.addWidget(QLabel("<hr>"))
        
        self.btn_filter_coupon = self._create_filter_button("优惠券", "coupon.svg", "#d81e06")
        self.btn_filter_coupon.setCheckable(True)
        self.btn_filter_new_customer = self._create_filter_button("新客立减", "new_customer.svg", "#9b59b6")
        self.btn_filter_new_customer.setCheckable(True)
        self.btn_filter_limited_time = self._create_filter_button("限时限量购", "limited-time.svg", "#e74c3c")
        self.btn_filter_limited_time.setCheckable(True)
        self.btn_filter_marketing = self._create_filter_button("营销活动", "marketing.svg", "#9b59b6")
        self.btn_filter_marketing.setCheckable(True)
        self.btn_filter_natural_flow = self._create_filter_button("无推广", None, "#16a085")
        self.btn_filter_natural_flow.setCheckable(True)
        self.btn_filter_sitewide = self._create_filter_button("全站托管", None, "#8e44ad")
        self.btn_filter_sitewide.setCheckable(True)
        
        filter_layout.addWidget(QLabel("<hr>"))
        
        profit_label = QLabel("利润标签")
        profit_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #2c3e50;")
        filter_layout.addWidget(profit_label)
        
        self.btn_filter_profit = self._create_filter_button("赚钱 (≥1%)", None, "#27ae60")
        self.btn_filter_profit.setCheckable(True)

        self.btn_filter_loss = self._create_filter_button("亏钱 (<-2%)", None, "#e74c3c")
        self.btn_filter_loss.setCheckable(True)

        self.btn_filter_break_even = self._create_filter_button("保本 (-2%~1%)", None, "#f39c12")
        self.btn_filter_break_even.setCheckable(True)

        self.btn_filter_missing_roi_bid = self._create_filter_button("未填投产/出价", None, "#8e44ad")
        self.btn_filter_missing_roi_bid.setCheckable(True)
        
        filter_layout.addWidget(self.btn_filter_coupon)
        filter_layout.addWidget(self.btn_filter_new_customer)
        filter_layout.addWidget(self.btn_filter_limited_time)
        filter_layout.addWidget(self.btn_filter_marketing)
        filter_layout.addWidget(self.btn_filter_natural_flow)
        filter_layout.addWidget(self.btn_filter_sitewide)
        filter_layout.addWidget(self.btn_filter_profit)
        filter_layout.addWidget(self.btn_filter_loss)
        filter_layout.addWidget(self.btn_filter_break_even)
        filter_layout.addWidget(self.btn_filter_missing_roi_bid)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_save_filter = QPushButton("💾 保存筛选")
        btn_save_filter.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        # 保存按钮连接筛选并关闭窗口
        btn_save_filter.clicked.connect(lambda: self.apply_tag_filter(close_menu=True))
        
        btn_clear_filter = QPushButton("清空")
        btn_clear_filter.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        btn_clear_filter.clicked.connect(self.clear_tag_filter)
        
        btn_layout.addWidget(btn_save_filter)
        btn_layout.addWidget(btn_clear_filter)
        filter_layout.addLayout(btn_layout)
        
        self.current_filter_tags = set()
        
        # 筛选按钮连接实时筛选（不关闭窗口）
        self.btn_filter_coupon.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_new_customer.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_limited_time.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_marketing.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_natural_flow.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_sitewide.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_profit.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_loss.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_break_even.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_missing_roi_bid.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_tag_filter)
        search_layout.addWidget(self.btn_store_filter)
        toolbar.addLayout(search_layout)
        
        icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        
        btn_add_store = QPushButton()
        btn_add_store.setIcon(QIcon(os.path.join(icons_dir, "add_link.svg")))
        btn_add_store.setIconSize(QSize(20, 20))
        btn_add_store.setToolTip("添加链接")
        btn_add_store.setFixedSize(32, 32)
        btn_add_store.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        btn_add_store.clicked.connect(self.add_store)
        toolbar.addWidget(btn_add_store)
        
        btn_daily_task = QPushButton("📋 每日任务")
        btn_daily_task.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        btn_daily_task.clicked.connect(self.show_daily_task_dialog)
        toolbar.addWidget(btn_daily_task)

        btn_export = QPushButton("📊导出Excel")
        btn_export.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        btn_export.clicked.connect(self.export_to_excel)
        toolbar.addWidget(btn_export)

        toolbar.addWidget(btn_prev)
        toolbar.addWidget(self.lbl_month)
        toolbar.addWidget(btn_next)

        self.btn_today = QPushButton("📍 定位今天")
        self.btn_today.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 1px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.btn_today.clicked.connect(self.go_to_today)
        toolbar.addWidget(self.btn_today)

        self.product_sort_combo = QComboBox()
        self.product_sort_combo.addItem("按单量", "order")
        self.product_sort_combo.addItem("按净利率", "net_margin")
        self.product_sort_combo.addItem("按商品类型", "category")
        self.product_sort_combo.setFixedWidth(105)
        sort_index = self.product_sort_combo.findData(self.product_sort_mode)
        self.product_sort_combo.setCurrentIndex(sort_index if sort_index >= 0 else 0)
        self.product_sort_combo.currentIndexChanged.connect(self.on_product_sort_changed)
        self.product_sort_combo.setToolTip("排序当前店铺内显示的链接")
        self.product_sort_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #6c757d;
                border-radius: 4px;
                padding: 2px 8px;
                font-weight: bold;
                font-size: 13px;
                background: white;
            }
        """)
        toolbar.addWidget(self.product_sort_combo)

        toolbar.addStretch()

        # 状态栏左下角按钮区域
        bottom_left_widget = QWidget()
        bottom_left_layout = QHBoxLayout(bottom_left_widget)
        bottom_left_layout.setContentsMargins(5, 0, 0, 0)
        bottom_left_layout.setSpacing(5)

        self.btn_api_config = QPushButton("🔑 API配置")
        self.btn_api_config.setFixedSize(80, 26)
        self.btn_api_config.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                font-size: 13px;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """)
        self.btn_api_config.clicked.connect(self.show_api_config_dialog)
        bottom_left_layout.addWidget(self.btn_api_config)

        self.btn_import_cost = QPushButton("📥 导入成本表")
        self.btn_import_cost.setFixedSize(100, 26)
        self.btn_import_cost.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                font-size: 13px;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        self.btn_import_cost.clicked.connect(self.import_cost_data)
        bottom_left_layout.addWidget(self.btn_import_cost)

        self.btn_view_cost = QPushButton("📦 查看成本库")
        self.btn_view_cost.setFixedSize(100, 26)
        self.btn_view_cost.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                font-size: 13px;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        self.btn_view_cost.clicked.connect(self.show_cost_library)
        bottom_left_layout.addWidget(self.btn_view_cost)

        self.btn_real_promotion_mode = QPushButton("真实推广数据模式")
        self.btn_real_promotion_mode.setCheckable(True)
        self.btn_real_promotion_mode.setFixedSize(125, 26)
        self.btn_real_promotion_mode.setChecked(self.db.get_setting("real_promotion_data_mode", "0") == "1")
        self.btn_real_promotion_mode.clicked.connect(self.toggle_real_promotion_data_mode)
        bottom_left_layout.addWidget(self.btn_real_promotion_mode)
        self._update_real_promotion_mode_button_style()

        self.statusBar().addWidget(bottom_left_widget)

        # 状态栏右下角按钮区域
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 5, 0)

        self.lbl_cloud_account = QLabel("未登录")
        self.lbl_cloud_account.setStyleSheet("color: #888; font-size: 12px; padding: 0 5px;")
        self.lbl_cloud_account.setAlignment(Qt.AlignVCenter)
        status_layout.addWidget(self.lbl_cloud_account)

        self.btn_switch_local_account = QPushButton("🔁 切换账号")
        self.btn_switch_local_account.setFixedSize(90, 26)
        self.btn_switch_local_account.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                font-size: 13px;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #d68910;
            }
        """)
        self.btn_switch_local_account.clicked.connect(self.show_local_account_switch_menu)
        self.btn_switch_local_account.setToolTip("选择要切换的本地账号数据")
        status_layout.addWidget(self.btn_switch_local_account)

        self.btn_pinduoduo = QPushButton("🛒 拼多多")
        self.btn_pinduoduo.setFixedSize(80, 26)
        self.btn_pinduoduo.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                font-size: 13px;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.btn_pinduoduo.clicked.connect(self.open_pinduoduo)
        self.btn_pinduoduo.setToolTip("打开拼多多商家后台")
        status_layout.addWidget(self.btn_pinduoduo)

        self.btn_cloud_login = QPushButton("☁️ 云同步")
        self.btn_cloud_login.setFixedSize(80, 26)
        self.btn_cloud_login.setStyleSheet("""
            QPushButton {
                background-color: #009688;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                font-size: 13px;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #00796b;
            }
        """)
        self.btn_cloud_login.clicked.connect(self.show_cloud_login_dialog)
        self.btn_cloud_login.setToolTip("云同步账号管理")
        status_layout.addWidget(self.btn_cloud_login)

        self.statusBar().addPermanentWidget(status_widget)

        toolbar.addWidget(btn_add_store)

        # 1. 创建表格
        self.table = QTableWidget()
        from PyQt5.QtGui import QStandardItemModel
        self.model = QStandardItemModel()
        self.frozen_table = QTableWidget(self.table)  # 冻结表作为主表的子控件
        
        # 2. 初始化表格属性
        self.setup_tables()
        
        # 2.5 设置今日列高亮代理
        self.today_delegate = OperationRecordDelegate(self.table, -1)
        self.table.setItemDelegate(self.today_delegate)
        
        # 3. 【关键】连接选中同步信号
        self.table.selectionModel().selectionChanged.connect(self.sync_frozen_selection)
        self.frozen_table.selectionModel().selectionChanged.connect(self.sync_main_selection)
        
        # 4. 【关键】安装事件过滤器 (给两个表格的视口都安装，用于拦截滚轮)
        self.table.viewport().installEventFilter(self)
        self.frozen_table.viewport().installEventFilter(self)
        
        # 5. 绑定双击事件 (打开规格弹窗)
        self.frozen_table.cellDoubleClicked.connect(self.open_product_spec_dialog_from_table)
        
        # --- 布局代码 (保持你原有的不变) ---
        main_layout = QVBoxLayout()

        # 添加调试标签到最顶部
        main_layout.addWidget(self.debug_label)

        # 添加资源监控标签到顶部
        main_layout.addWidget(self.resource_label)

        debug_label = QLabel("【主界面工具栏区】")
        debug_label.setStyleSheet("background-color: #FFB6C1; color: #000; padding: 2px 5px; font-size: 11px;")
        debug_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        main_layout.addWidget(debug_label)

        main_layout.addLayout(toolbar)

        debug_container = QWidget()
        debug_layout = QHBoxLayout(debug_container)
        debug_layout.setContentsMargins(0, 0, 0, 0)
        debug_layout.setSpacing(10)

        debug_label1 = QLabel("【左侧冻结列区】")
        debug_label1.setStyleSheet("background-color: #98FB98; color: #000; padding: 2px 5px; font-size: 11px;")
        debug_label1.setTextInteractionFlags(Qt.TextSelectableByMouse)
        debug_layout.addWidget(debug_label1)

        debug_label2 = QLabel("【右侧主表区】")
        debug_label2.setStyleSheet("background-color: #87CEEB; color: #000; padding: 2px 5px; font-size: 11px;")
        debug_label2.setTextInteractionFlags(Qt.TextSelectableByMouse)
        debug_layout.addWidget(debug_label2)

        main_layout.addWidget(debug_container)
        main_layout.addWidget(self.table)
        
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # --- Toast 提示代码 (保持你原有的不变) ---
        self.toast_label = QLabel(self)
        self.toast_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            font-size: 14px;
        """)
        self.toast_label.setAlignment(Qt.AlignCenter)
        self.toast_label.hide()
        
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.hide_toast)

    def resizeEvent(self, event):
        """
        【中文功能说明】
        窗口大小改变事件：当用户拉伸窗口时触发。
        作用：强制更新冻结表的位置和大小，防止按钮被遮挡或左右错位。
        """
        super().resizeEvent(event)
        self.update_frozen_geometry()

    def eventFilter(self, obj, event):
        """
        事件过滤器：处理滚轮事件，实现丝滑滚动功能。
        冻结表格滚动时同步到主表格。
        
        配置说明：
        - speed_factor: 滚动速度因子，值越大滚动越慢/越精细
          推荐范围：60-500
          120: 每次滚动约1像素
          240: 每次滚动约0.5像素
          480: 每次滚动约0.25像素
        """
        if event.type() == QEvent.MouseButtonPress:
            if self._should_close_tag_filter_on_click(event):
                self.tag_filter_menu.close()

        if obj == self.table.viewport():
            if event.type() == QEvent.ToolTip:
                return True
            if event.type() == QEvent.Leave:
                self._cancel_record_tooltip()
            elif event.type() == QEvent.MouseMove:
                self._handle_record_tooltip_mouse_move(event)

        if event.type() == QEvent.Wheel:
            v_scroll = self.table.verticalScrollBar()
            h_scroll = self.table.horizontalScrollBar()

            if not v_scroll:
                return super().eventFilter(obj, event)

            delta_y = event.angleDelta().y()
            delta_x = event.angleDelta().x()

            speed_factor = 120.0

            if obj == self.frozen_table.viewport():
                if delta_y != 0:
                    current_value = v_scroll.value()
                    if (current_value == v_scroll.minimum() and delta_y > 0) or \
                       (current_value == v_scroll.maximum() and delta_y < 0):
                        self._accumulated_v = 0
                    else:
                        step = delta_y / speed_factor
                        self._accumulated_v = getattr(self, '_accumulated_v', 0) + step
                        if abs(self._accumulated_v) >= 1.0:
                            scroll_step = int(self._accumulated_v)
                            self._accumulated_v -= scroll_step
                            new_value = current_value - scroll_step
                            v_scroll.setValue(max(v_scroll.minimum(), min(v_scroll.maximum(), new_value)))
                return True

            if obj == self.table.viewport():
                if delta_y != 0:
                    current_value = v_scroll.value()
                    if (current_value == v_scroll.minimum() and delta_y > 0) or \
                       (current_value == v_scroll.maximum() and delta_y < 0):
                        self._accumulated_v = 0
                    else:
                        step = delta_y / speed_factor
                        self._accumulated_v = getattr(self, '_accumulated_v', 0) + step
                        if abs(self._accumulated_v) >= 1.0:
                            scroll_step = int(self._accumulated_v)
                            self._accumulated_v -= scroll_step
                            new_value_y = current_value - scroll_step
                            v_scroll.setValue(max(v_scroll.minimum(), min(v_scroll.maximum(), new_value_y)))

                if h_scroll and delta_x != 0:
                    current_h_value = h_scroll.value()
                    if (current_h_value == h_scroll.minimum() and delta_x > 0) or \
                       (current_h_value == h_scroll.maximum() and delta_x < 0):
                        self._accumulated_h = 0
                    else:
                        h_step = delta_x / speed_factor
                        self._accumulated_h = getattr(self, '_accumulated_h', 0) + h_step
                        if abs(self._accumulated_h) >= 1.0:
                            h_scroll_step = int(self._accumulated_h)
                            self._accumulated_h -= h_scroll_step
                            new_value_x = current_h_value - h_scroll_step
                            h_scroll.setValue(max(h_scroll.minimum(), min(h_scroll.maximum(), new_value_x)))

                return True

        return super().eventFilter(obj, event)

    def _handle_record_tooltip_mouse_move(self, event):
        index = self.table.indexAt(event.pos())
        if not index.isValid() or index.column() <= 0:
            self._cancel_record_tooltip()
            return

        item = self.table.item(index.row(), index.column())
        text = item.toolTip() if item else ""
        if not text:
            self._cancel_record_tooltip()
            return

        cell = (index.row(), index.column())
        global_pos = event.globalPos() if hasattr(event, "globalPos") else self.table.viewport().mapToGlobal(event.pos())
        if cell != self._record_tooltip_cell:
            QToolTip.hideText()
            if hasattr(self, "_record_tooltip_timer"):
                self._record_tooltip_timer.stop()
            self._record_tooltip_cell = cell
            self._record_tooltip_text = text
            self._record_tooltip_pos = global_pos
            self._record_tooltip_timer.start(900)
            return

        self._record_tooltip_pos = global_pos

    def _show_pending_record_tooltip(self):
        cell = getattr(self, "_record_tooltip_cell", None)
        text = getattr(self, "_record_tooltip_text", "")
        if not cell or not text:
            return
        row, col = cell
        index = self.table.model().index(row, col)
        if not index.isValid():
            return
        current_index = self.table.indexAt(self.table.viewport().mapFromGlobal(QCursor.pos()))
        if not current_index.isValid() or current_index.row() != row or current_index.column() != col:
            return
        rect = self.table.visualRect(index)
        QToolTip.showText(self._record_tooltip_pos, text, self.table.viewport(), rect)

    def _cancel_record_tooltip(self):
        if hasattr(self, "_record_tooltip_timer"):
            self._record_tooltip_timer.stop()
        self._record_tooltip_cell = None
        self._record_tooltip_text = ""
        QToolTip.hideText()

    def _should_close_tag_filter_on_click(self, event):
        if not hasattr(self, "tag_filter_menu") or not self.tag_filter_menu.isVisible():
            return False
        if not hasattr(event, "globalPos"):
            return False
        global_pos = event.globalPos()
        menu_rect = QRect(self.tag_filter_menu.mapToGlobal(QPoint(0, 0)), self.tag_filter_menu.size())
        button_rect = QRect(self.btn_tag_filter.mapToGlobal(QPoint(0, 0)), self.btn_tag_filter.size())
        return not menu_rect.contains(global_pos) and not button_rect.contains(global_pos)

    def show_toast(self, message, duration=3000):
        """显示悬浮提示
        
        Args:
            message: 提示消息
            duration: 显示时长（毫秒），默认3000毫秒
        """
        self.toast_label.setText(message)
        self.toast_label.adjustSize() # 根据文字调整大小
        
        # 计算位置：让提示居中显示
        x = (self.width() - self.toast_label.width()) // 2
        y = self.height() - 100 # 距离底部 100 像素，或者改成 self.height()//2 居中
        
        self.toast_label.move(x, y)
        self.toast_label.show()
        
        # 指定时长后自动隐藏
        self.toast_timer.start(duration)

    def hide_toast(self):
        """隐藏提示"""
        self.toast_label.hide()

    def _on_scroll_changed(self):
        """滚动位置变化时自动保存（带防抖）"""
        self._scroll_save_timer.stop()
        self._scroll_save_timer.start(500)

    def _save_scroll_position_to_db(self):
        """实际保存滚动位置到数据库"""
        try:
            v_scroll = self.table.verticalScrollBar()
            h_scroll = self.table.horizontalScrollBar()
            if v_scroll:
                self.db.set_setting("scroll_vertical", v_scroll.value())
            if h_scroll:
                self.db.set_setting("scroll_horizontal", h_scroll.value())
        except Exception as e:
            print(f"保存滚动位置失败: {e}")

    def setup_tables(self):
        # --- 主表设置 ---
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.cellDoubleClicked.connect(self.open_editor)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows) # 整行选中
        self.table.verticalHeader().setDefaultSectionSize(self.PRODUCT_ROW_HEIGHT)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        
        # --- 冻结表设置 ---
        self.frozen_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.frozen_table.verticalHeader().hide()
        self.frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_table.setWordWrap(True)
        self.frozen_table.setMouseTracking(True)
        self.frozen_table.viewport().setMouseTracking(True)
        
        # 【关键】确保冻结表也能整行选中和获取焦点
        self.frozen_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.frozen_table.setFocusPolicy(Qt.StrongFocus)
        self.frozen_table.verticalHeader().setDefaultSectionSize(self.PRODUCT_ROW_HEIGHT)
        
        # 样式：右边框加粗
        self.frozen_table.setStyleSheet("QTableWidget { border-right: 2px solid #555; background-color: white; }")
        
        # --- 信号连接 ---
        # 1. 垂直滚动条同步 (主表带动冻结表)
        self.table.verticalScrollBar().valueChanged.connect(self.frozen_table.verticalScrollBar().setValue)
        
        # 2. 滚动位置自动保存（使用防抖，避免频繁写入）
        self._scroll_save_timer = QTimer(self)
        self._scroll_save_timer.setSingleShot(True)
        self._scroll_save_timer.timeout.connect(self._save_scroll_position_to_db)
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.table.horizontalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self._record_tooltip_timer = QTimer(self)
        self._record_tooltip_timer.setSingleShot(True)
        self._record_tooltip_timer.timeout.connect(self._show_pending_record_tooltip)
        
        # 3. 行高同步
        self.table.verticalHeader().sectionResized.connect(self.sync_row_height)
        
        # 3. 列宽同步 (第0列)
        self.table.horizontalHeader().sectionResized.connect(self.sync_col_width)
        
        # 4. 保存列宽设置到数据库
        self._suppress_col0_width_save = False
        self.frozen_table.horizontalHeader().sectionResized.connect(self._save_frozen_col_width)
            # 主表样式
        self.table.setStyleSheet("""
            /* 选中行的样式 */
            QTableWidget::item:selected {
                background-color: #ffe0b2;
                color: black;                   /* 选中行文字颜色 - 黑色 */
                border: none;
                padding: 0px;
                outline: none;
            }

            /* 当窗口失去焦点时的选中行样式 */
            QTableWidget::item:selected:!active {
                background-color: #ffe0b2;
                color: black;
                padding: 0px;
                outline: none;
            }

            /* 单元格基础样式 */
            QTableWidget::item {
                padding: 0px;
                border: none;
            }
        """)
        
        # 冻结表样式（和主表保持一致，但确保文字清晰可读）
        self.frozen_table.setStyleSheet("""
            QTableWidget {
                border: none;
                border-right: 2px solid #000000;
                background-color: white;
                color: #333333;
                font-weight: bold;
                gridline-color: #000000;
            }

            QTableWidget::item {
                color: #333333;
                font-weight: bold;
                padding: 5px;
                border: none;
            }

            /* 选中行的样式 */
            QTableWidget::item:selected {
                background-color: #ffe0b2;
                color: #333333;
                padding: 5px;
            }

            /* 失焦时的选中行样式 */
            QTableWidget::item:selected:!active {
                background-color: #ffe0b2;
                color: #333333;
                padding: 5px;
            }
        """)
    def _sync_frozen_from_main(self):
        """主表 -> 冻结表"""
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            self.frozen_table.clearSelection()
            self._update_frozen_selection_highlight(None)
            self.frozen_table.viewport().update()
            return
        row = indexes[0].row()
        if 0 <= row < self.frozen_table.rowCount():
            self.frozen_table.blockSignals(True)
            self.frozen_table.selectRow(row)
            self._update_frozen_selection_highlight(row)
            self.frozen_table.viewport().update()
            self.frozen_table.update()
            self.frozen_table.blockSignals(False)

    def _sync_main_from_frozen(self):
        """冻结表 -> 主表"""
        indexes = self.frozen_table.selectionModel().selectedRows()
        if not indexes:
            self.table.clearSelection()
            self._update_frozen_selection_highlight(None)
            self.table.viewport().update()
            return
        row = indexes[0].row()
        if 0 <= row < self.table.rowCount():
            self.table.blockSignals(True)
            self.table.selectRow(row)
            self._update_frozen_selection_highlight(row)
            self.table.viewport().update()
            self.table.update()
            self.table.blockSignals(False)    

    def sync_row_height(self, logicalIndex, oldSize, newSize):
        try:
            self.frozen_table.setRowHeight(logicalIndex, newSize)
        except Exception as e:
            print(f"同步行高失败：{e}")
        
    def sync_col_width(self, logicalIndex, oldSize, newSize):
        try:
            if logicalIndex == 0:
                self.frozen_table.setColumnWidth(0, newSize)
            self.update_frozen_geometry()
        except Exception as e:
            print(f"同步列宽失败：{e}")

    def sync_frozen_selection(self, selected, deselected):
        """主表选中变化时，同步冻结表选中状态"""
        indexes = selected.indexes()
        if not indexes:
            self.frozen_table.clearSelection()
            self._update_frozen_selection_highlight(None)
            return
        row = indexes[0].row()
        if 0 <= row < self.frozen_table.rowCount():
            self.frozen_table.blockSignals(True)
            self.frozen_table.selectRow(row)
            self._update_frozen_selection_highlight(row)
            self.frozen_table.viewport().update()
            self.frozen_table.update()
            self.frozen_table.blockSignals(False)

    def sync_main_selection(self, selected, deselected):
        """冻结表选中变化时，同步主表选中状态"""
        indexes = selected.indexes()
        if not indexes:
            self.table.clearSelection()
            self._update_frozen_selection_highlight(None)
            return
        row = indexes[0].row()
        if 0 <= row < self.table.rowCount():
            self.table.blockSignals(True)
            self.table.selectRow(row)
            self._update_frozen_selection_highlight(row)
            self.table.viewport().update()
            self.table.update()
            self.table.blockSignals(False)

    def _update_frozen_selection_highlight(self, selected_row):
        selected_color = QColor("#ffe0b2")
        normal_color = QColor("#ffffff")
        for row in range(self.frozen_table.rowCount()):
            widget = self.frozen_table.cellWidget(row, 0)
            if not widget:
                continue
            palette = widget.palette()
            palette.setColor(QPalette.Window, selected_color if row == selected_row else normal_color)
            widget.setAutoFillBackground(True)
            widget.setPalette(palette)

    def update_frozen_geometry(self):
        try:
            x = self.table.frameWidth()
            y = self.table.frameWidth()
            w = self.table.columnWidth(0)
            h = self.table.viewport().height() + self.table.horizontalHeader().height()
            self.frozen_table.setGeometry(x, y, w, h)
        except Exception as e:
            print(f"更新冻结表几何位置失败：{e}")

    def force_refresh_frozen_table(self):
        """强制刷新 frozen_table 的显示，确保数据更新后能正确显示"""
        try:
            self.frozen_table.viewport().update()
            self.frozen_table.update()
            for row in range(self.frozen_table.rowCount()):
                widget = self.frozen_table.cellWidget(row, 0)
                if widget and isinstance(widget, ProductWidget):
                    widget.update_margin_display()
                    widget.update_promo_badges()
                    widget.update_task_badge()
        except Exception as e:
            print(f"强制刷新frozen_table失败: {e}")

    def is_real_promotion_data_mode(self):
        return self.db.get_setting("real_promotion_data_mode", "0") == "1"

    def _update_real_promotion_mode_button_style(self):
        if not hasattr(self, "btn_real_promotion_mode"):
            return
        enabled = self.btn_real_promotion_mode.isChecked()
        self.btn_real_promotion_mode.setText("真实推广: 开" if enabled else "真实推广数据模式")
        bg = "#e74c3c" if enabled else "#6c757d"
        hover = "#c0392b" if enabled else "#5a6268"
        self.btn_real_promotion_mode.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                font-weight: bold;
                border-radius: 4px;
                font-size: 12px;
                padding: 1px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)

    def toggle_real_promotion_data_mode(self, *_args):
        enabled = self.btn_real_promotion_mode.isChecked()
        self.db.set_setting("real_promotion_data_mode", "1" if enabled else "0")
        self._update_real_promotion_mode_button_style()
        self.load_data_safe()

    def _save_frozen_col_width(self, logicalIndex, oldSize, newSize):
        if logicalIndex != 0 or getattr(self, "_suppress_col0_width_save", False):
            return
        saved_width = int(newSize) - (30 if self.is_real_promotion_data_mode() else 0)
        self.db.set_setting("col_0_width", max(120, saved_width))

    def get_latest_promotion_data(self, store_id, product_code):
        cutoff = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        rows = self.db.safe_fetchall("""
            SELECT record_date, cost, transaction_amount, net_transaction_amount, net_roi,
                   net_orders, promotion_impression_share
            FROM promotion_daily_data
            WHERE store_id=? AND product_id=? AND record_date<=?
            ORDER BY record_date DESC
            LIMIT 1
        """, (store_id, product_code, cutoff))
        if not rows:
            return None
        row = rows[0]
        return {
            "record_date": row[0],
            "cost": float(row[1] or 0),
            "transaction_amount": float(row[2] or 0),
            "net_transaction_amount": float(row[3] or 0),
            "net_roi": float(row[4] or 0),
            "net_orders": float(row[5] or 0),
            "promotion_impression_share": float(row[6] or 0),
        }

    def force_refresh_product_widget(self, product_id):
        """根据 product_id 强制刷新对应的 ProductWidget"""
        try:
            for row, prod_id in self.row_data_map.items():
                if prod_id == product_id:
                    widget = self.frozen_table.cellWidget(row, 0)
                    if widget and isinstance(widget, ProductWidget):
                        widget.update_margin_display()
                        widget.update_promo_badges()
                        widget.update_task_badge()
                        widget.update()
                    self.frozen_table.viewport().update()
                    self.frozen_table.update()
                    return
            # 如果没找到，尝试刷新所有
            self.force_refresh_frozen_table()
        except Exception as e:
            print(f"强制刷新ProductWidget失败: {e}")




    def save_scroll_position(self):
        """保存当前滚动位置和选中的商品ID到数据库"""
        v_scroll = self.table.verticalScrollBar()
        h_scroll = self.table.horizontalScrollBar()
        
        v_value = v_scroll.value() if v_scroll else 0
        h_value = h_scroll.value() if h_scroll else 0
        
        self.db.set_setting("scroll_vertical", v_value)
        self.db.set_setting("scroll_horizontal", h_value)
        
        selected_rows = self.table.selectionModel().selectedRows()
        selected_product_id = None
        if selected_rows:
            row = selected_rows[0].row()
            if row in self.row_data_map:
                selected_product_id = self.row_data_map[row]
                self.db.set_setting("selected_product_id", selected_product_id)
        
        return v_value, h_value, selected_product_id
    
    def restore_scroll_position(self, scroll_value, selected_product_id, h_scroll_value=None):
        """恢复滚动位置和选中状态"""
        v_scroll = self.table.verticalScrollBar()
        h_scroll = self.table.horizontalScrollBar()
        
        if selected_product_id:
            for row, prod_id in self.row_data_map.items():
                if prod_id == selected_product_id:
                    self.table.selectRow(row)
                    if v_scroll:
                        v_scroll.setValue(scroll_value)
                    if h_scroll and h_scroll_value is not None:
                        h_scroll.setValue(h_scroll_value)
                    return
        
        if v_scroll:
            v_scroll.setValue(scroll_value)
        if h_scroll and h_scroll_value is not None:
            h_scroll.setValue(h_scroll_value)

    def open_store_margin_dialog(self, store_id, store_name):
        """打开店铺毛利管理对话框（供 StoreWidget 调用，避免 widgets 依赖本模块 Dialog）"""
        def on_margin_changed(sid, new_margin):
            self.load_data_safe()
            self.refresh_store_weight_sync_flag(sid)
        dialog = StoreMarginDialog(store_id, store_name, self, self, on_margin_changed)
        dialog.exec_()

    def refresh_store_weight_sync_flag(self, store_id):
        """刷新店铺的权重已同步标签（供 StoreMarginDialog 调用）"""
        for row in range(self.frozen_table.rowCount()):
            widget = self.frozen_table.cellWidget(row, 0)
            if widget and hasattr(widget, 'store_id') and widget.store_id == store_id:
                if hasattr(widget, 'refresh_sync_flag'):
                    widget.refresh_sync_flag()
                break

    def open_product_spec_dialog(self, db, product_id, product_code, product_title, parent):
        """打开规格与毛利对话框（供 StoreMarginDialog 等调用，避免 dialogs 依赖本模块）"""
        dialog = ProductSpecDialog(db, product_id, product_code, product_title, parent)
        dialog.main_app = self
        dialog.show()

    def open_profit_calculator_dialog(self, margin_rate, avg_price, store_id, store_name, scope, parent, db):
        """打开利润计算器对话框（供 StoreMarginDialog 等调用）"""
        dialog = ProfitCalculatorDialog(margin_rate, avg_price, store_id, store_name, scope, parent, db)
        dialog.show()

    def _get_product_order_count(self, prod_code):
        """获取商品的单量（从 imported_orders 表汇总）"""
        try:
            spec_counts = self.db.safe_fetchall(
                "SELECT order_count FROM imported_orders WHERE product_id=?",
                (prod_code,)
            )
            return sum(sc[0] for sc in spec_counts) if spec_counts else 0
        except:
            return 0

    def on_product_sort_changed(self):
        if not hasattr(self, "product_sort_combo"):
            return
        mode = self.product_sort_combo.currentData() or "order"
        if mode == self.product_sort_mode:
            return
        self.product_sort_mode = mode
        self.db.set_setting("product_sort_mode", mode)
        self.load_data_safe()

    def _calculate_product_net_margin(self, product_id):
        try:
            rows = self.db.safe_fetchall(
                "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                (product_id,),
            )
            if not rows:
                return None
            product_rows = self.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate, is_natural_flow, is_sitewide_managed, store_id, name FROM products WHERE id=?",
                (product_id,),
            )
            if not product_rows:
                return None
            coupon = product_rows[0][0] if product_rows[0][0] else 0
            new_customer = product_rows[0][1] if product_rows[0][1] else 0
            current_roi = product_rows[0][2] if product_rows[0][2] else 0
            return_rate = product_rows[0][3] if product_rows[0][3] else 0
            is_natural_flow = product_rows[0][4] if product_rows[0][4] else 0
            is_sitewide_managed = product_rows[0][5] if product_rows[0][5] else 0
            store_id = product_rows[0][6] if product_rows[0][6] else None
            product_code = product_rows[0][7] if product_rows[0][7] else ""
            sitewide_roi = 0
            if store_id:
                store_rows = self.db.safe_fetchall("SELECT sitewide_roi FROM stores WHERE id=?", (store_id,))
                sitewide_roi = store_rows[0][0] if store_rows and store_rows[0][0] else 0
            effective_roi = sitewide_roi if is_sitewide_managed and not is_natural_flow else current_roi
            if not is_natural_flow and effective_roi <= 0:
                return None

            max_discount = max(coupon, new_customer)
            total_weighted_margin = 0.0
            total_weight = 0.0
            for spec_code, sale_price, weight in rows:
                if sale_price is None or weight is None:
                    continue
                cost_res = self.db.safe_fetchall(
                    "SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,)
                )
                cost = cost_res[0][0] if cost_res else 0.0
                final_price = sale_price - max_discount
                if final_price > 0 and cost > 0:
                    margin = (final_price - cost) / final_price
                    total_weighted_margin += margin * weight
                    total_weight += weight
            if total_weight <= 0:
                return None
            gross_margin_pct = (total_weighted_margin / total_weight) * 100
            margin_rate_decimal = gross_margin_pct / 100
            if self.is_real_promotion_data_mode() and not is_natural_flow and store_id and product_code:
                promo = self.get_latest_promotion_data(store_id, product_code)
                if not promo:
                    return None
                cost = float(promo.get("cost") or 0)
                net_amount = float(promo.get("net_transaction_amount") or 0)
                if net_amount > 0:
                    net_profit = net_amount * margin_rate_decimal - cost - net_amount * 0.006
                    return net_profit / net_amount * 100
                return -100.0 if cost > 0 else 0.0
            if is_natural_flow:
                return (margin_rate_decimal * (1 - return_rate / 100) - 0.006) * 100
            return (margin_rate_decimal * (1 - return_rate / 100) - 0.006 - (1 / effective_roi)) * 100
        except Exception as e:
            print(f"计算链接净利率失败: {e}")
            return None

    def _build_product_sort_info(self, product):
        product_id, product_code, _title, _image_data, sort_order, category_label = product
        category_label = str(category_label or "").strip()
        calculated_category = self.db.calculate_product_category_label(product_id)
        if calculated_category != category_label:
            category_label = self.db.update_product_category_label(product_id)
        order_count = self._get_product_order_count(product_code)
        net_margin = self._calculate_product_net_margin(product_id)
        fallback_order = sort_order if sort_order is not None else product_id
        return {
            "product": product,
            "order_count": order_count,
            "net_margin": net_margin,
            "category_label": category_label,
            "fallback_order": fallback_order,
            "product_id": product_id,
        }

    def _product_metric_sort_key(self, info):
        net_margin = info["net_margin"]
        return (
            -info["order_count"],
            1 if net_margin is None else 0,
            -(net_margin if net_margin is not None else -10**9),
            info["fallback_order"],
            info["product_id"],
        )

    def _sort_products_for_display(self, products_raw):
        infos = [self._build_product_sort_info(product) for product in products_raw]
        mode = self.product_sort_mode or "order"
        if mode == "net_margin":
            infos.sort(
                key=lambda info: (
                    1 if info["net_margin"] is None else 0,
                    -(info["net_margin"] if info["net_margin"] is not None else -10**9),
                    -info["order_count"],
                    info["fallback_order"],
                    info["product_id"],
                )
            )
        elif mode == "category":
            group_stats = {}
            for info in infos:
                label = info["category_label"]
                if not label:
                    continue
                stat = group_stats.setdefault(label, {"max_order": 0, "max_margin": None})
                stat["max_order"] = max(stat["max_order"], info["order_count"])
                margin = info["net_margin"]
                if margin is not None and (stat["max_margin"] is None or margin > stat["max_margin"]):
                    stat["max_margin"] = margin
            infos.sort(
                key=lambda info: (
                    1 if not info["category_label"] else 0,
                    -group_stats.get(info["category_label"], {}).get("max_order", 0),
                    1 if group_stats.get(info["category_label"], {}).get("max_margin") is None else 0,
                    -(
                        group_stats.get(info["category_label"], {}).get("max_margin")
                        if group_stats.get(info["category_label"], {}).get("max_margin") is not None
                        else -10**9
                    ),
                    info["category_label"],
                    *self._product_metric_sort_key(info),
                )
            )
        else:
            infos.sort(key=self._product_metric_sort_key)
        return [info["product"] for info in infos]

    def load_data_safe(self, restore_position=True):
        """安全加载数据，防止闪退"""
        if self.is_loading:
            return  # 防止重复加载
        
        # 保存当前滚动位置和选中状态
        v_scroll_value, h_scroll_value, selected_product_id = 0, 0, None
        if restore_position:
            v_scroll_value, h_scroll_value, selected_product_id = self.save_scroll_position()
        
        # 尝试从数据库读取上次保存的位置（用于切换月份时保持位置）
        saved_v = self.db.get_setting("scroll_vertical", 0)
        saved_h = self.db.get_setting("scroll_horizontal", 0)
        saved_product = self.db.get_setting("selected_product_id")
        try:
            if not restore_position:
                v_scroll_value = int(saved_v) if saved_v else 0
                h_scroll_value = int(saved_h) if saved_h else 0
            selected_product_id = saved_product
        except:
            pass
        
        self.is_loading = True
        
        try:
            self.lbl_month.setText(f"{self.year}年 {self.month}月")
            days_in_month = calendar.monthrange(self.year, self.month)[1]
            
            stores = self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order")
            
            # 临时禁用信号以提高性能
            self.table.blockSignals(True)
            self.frozen_table.blockSignals(True)
            
            # 清空表格
            while self.table.rowCount() > 0:
                self.table.removeRow(0)
            while self.frozen_table.rowCount() > 0:
                self.frozen_table.removeRow(0)
            
            total_cols = days_in_month + 1
            self.table.setColumnCount(total_cols)
            self.frozen_table.setColumnCount(1)
            
            headers = ["商品信息"]
            today = datetime.now()
            self._today_col = -1
            for i in range(1, days_in_month + 1):
                dt = datetime(self.year, self.month, i)
                weekday_idx = dt.weekday()
                weekday_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday_idx]
                headers.append(f"{i}号 {weekday_name}")
                if self.year == today.year and self.month == today.month and i == today.day:
                    self._today_col = i
            self.table.setHorizontalHeaderLabels(headers)
            self.frozen_table.setHorizontalHeaderLabels(["商品信息"])

            if hasattr(self, 'today_delegate'):
                self.today_delegate.set_today_col(self._today_col)

            # 恢复表头样式，并给今日列设置高亮
            header_style = "QHeaderView::section { background-color: #f0f0f0; }"
            if self._today_col > 0:
                header_style += f"QTableWidget::item:column({self._today_col}):selected, QHeaderView::section:column({self._today_col}) {{ background-color: #fff3e0; }}"
                header_style += f"QHeaderView::section:column({self._today_col}) {{ background-color: #ffe0b2; font-weight: bold; }}"
            self.table.horizontalHeader().setStyleSheet(header_style)
            
            col0_width = int(self.db.get_setting("col_0_width", 278))  # 调整宽度以容纳按钮
            if self.db.get_setting("col_0_width_plus_20_applied", "0") != "1":
                col0_width += 20
                self.db.set_setting("col_0_width", col0_width)
                self.db.set_setting("col_0_width_plus_20_applied", "1")
            display_col0_width = col0_width + (30 if self.is_real_promotion_data_mode() else 0)
            self._suppress_col0_width_save = True
            self.table.setColumnWidth(0, display_col0_width)
            self.frozen_table.setColumnWidth(0, display_col0_width)
            self._suppress_col0_width_save = False
            for i in range(1, total_cols):
                self.table.setColumnWidth(i, int(self.db.get_setting(f"col_{i}_width", 250)))
                
            self.row_data_map.clear()
            self.row_store_map.clear()
            self.product_store_map.clear()
            row_idx = 0
            
            for s_idx, store in enumerate(stores):
                store_id, store_name = store
                self.table.insertRow(row_idx)
                self.frozen_table.insertRow(row_idx)
                
                # 使用新的店铺控件，包含删除按钮和添加商品按钮
                store_widget = StoreWidget(store_id, f"{s_idx+1}. {store_name}", self)
                self.frozen_table.setCellWidget(row_idx, 0, store_widget)
                self.row_store_map[row_idx] = store_id
                
                # 店铺行需要为所有日期列创建单元格
                for day in range(1, days_in_month + 1):
                    item = self.table.item(row_idx, day)
                    if not item:
                        item = QTableWidgetItem()
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        self.table.setItem(row_idx, day, item)
                
                # 渲染店铺操作记录
                rec_dict = self.db.get_store_record(store_id, self.year, self.month, 0)
                self.render_store_records(row_idx, store_id, days_in_month)
                
                self.table.setRowHeight(row_idx, self.STORE_ROW_HEIGHT)
                self.frozen_table.setRowHeight(row_idx, self.STORE_ROW_HEIGHT)
                row_idx += 1
                
                products_raw = self.db.safe_fetchall(
                    "SELECT id, name, title, image_data, sort_order, product_category_label FROM products WHERE store_id=?",
                    (store_id,),
                )
                products = self._sort_products_for_display(products_raw)
                for prod in products:
                    p_id, p_code, p_title, p_img = prod[:4]  # 注意这里：p_code是商品ID，p_title是商品标题
                    self.table.insertRow(row_idx)
                    self.frozen_table.insertRow(row_idx)
                    
                    p_widget = ProductWidget(p_id, p_code, p_title, p_img, self)
                    self.frozen_table.setCellWidget(row_idx, 0, p_widget)
                    self.row_data_map[row_idx] = p_id
                    self.product_store_map[p_id] = store_id
                    
                    self._set_product_display_row_height(row_idx)
                    
                    self.render_records_for_product(row_idx, p_id, days_in_month)
                    
                    row_idx += 1

            QApplication.processEvents() 
            self.frozen_table.repaint()
            
        except Exception as e:
            print(f"加载数据失败: {e}")
            QMessageBox.critical(self, "错误", f"加载数据失败: {e}")
        finally:
            self.table.blockSignals(False)
            self.frozen_table.blockSignals(False)
            self.is_loading = False
            
        # 恢复滚动位置和选中状态
        QTimer.singleShot(10, lambda: self.restore_scroll_position(v_scroll_value, selected_product_id, h_scroll_value))
        
        QTimer.singleShot(10, self.update_frozen_geometry)
        QTimer.singleShot(30, self._reapply_search_and_filters_after_load)
        if getattr(self, "_startup_locate_today_pending", False):
            self._startup_locate_today_pending = False
            QTimer.singleShot(80, self._locate_today_on_startup)
        
    def _format_operation_record_for_cell(self, record):
        time_text = record.get("time", "")
        body = str(record.get("text", "") or "")
        body = re.sub(r"^自动记录[:：]\s*", "", body).strip()
        if not body and record.get("changes"):
            body = "；".join([c.get("text", "") for c in record.get("changes", []) if c.get("text")])
        return f"[{time_text}] {body}" if time_text else body

    def _format_operation_record_tooltip(self, records):
        lines = []
        for record in records or []:
            if not isinstance(record, dict):
                continue
            time_text = str(record.get("time", "") or "")
            changes = record.get("changes") or []
            if changes:
                for change in changes:
                    if not isinstance(change, dict):
                        continue
                    change_time = str(change.get("time", "") or time_text)
                    metric = str(change.get("metric", "") or "")
                    text = str(change.get("text", "") or "").strip()
                    prefix = f"[{change_time}]" if change_time else ""
                    if metric:
                        prefix = f"{prefix} {metric}".strip()
                    lines.append(f"{prefix}\n{text}" if prefix and text else (prefix or text))
            else:
                line = self._format_operation_record_for_cell(record)
                if line:
                    lines.append(line)
        return "\n\n".join([line for line in lines if line])

    def _apply_record_cell_style(self, item):
        font = QFont("Microsoft YaHei", 11)
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QColor("#1f2d3d"))
        item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)

    def _get_product_display_row_height(self, row):
        widget = self.frozen_table.cellWidget(row, 0)
        if widget and hasattr(widget, "recommended_row_height"):
            try:
                return widget.recommended_row_height(self.PRODUCT_ROW_HEIGHT)
            except Exception as e:
                print(f"计算商品行高失败: {e}")
        return self.PRODUCT_ROW_HEIGHT

    def _set_product_display_row_height(self, row):
        row_height = self._get_product_display_row_height(row)
        self.table.setRowHeight(row, row_height)
        self.frozen_table.setRowHeight(row, row_height)

    def update_product_row_height(self, prod_id):
        for row, row_prod_id in self.row_data_map.items():
            if row_prod_id == prod_id:
                self._set_product_display_row_height(row)
                return

    def render_records_for_product(self, row, prod_id, days):
        try:
            # 1. 从数据库获取最新记录
            records = self.db.safe_fetchall(
                "SELECT day, records_json FROM records WHERE product_id=? AND year=? AND month=?", 
                (prod_id, self.year, self.month)
            )
            rec_dict = {}
            
            for r in records:
                try:
                    rec_dict[r[0]] = json.loads(r[1])
                except:
                    rec_dict[r[0]] = []
            
            # 定义基础参数
            for day in range(1, days + 1):
                cell_data = rec_dict.get(day, [])
                
                # 构建显示文本
                if cell_data:
                    display_text = "\n".join([self._format_operation_record_for_cell(item) for item in cell_data])
                else:
                    display_text = ""
                
                # 【关键修复 1】获取或创建单元格
                item = self.table.item(row, day)
                if not item:
                    item = QTableWidgetItem()
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row, day, item)
                
                # ❌ 已删除 item.setWordWrap(True) 因为这方法不存在
                
                # 强制更新文本
                item.setText(display_text)
                item.setToolTip(self._format_operation_record_tooltip(cell_data) if cell_data else display_text)
                item.setData(Qt.UserRole, cell_data)
                
                # 确保文字靠上对齐，方便多行显示
                self._apply_record_cell_style(item)

            self._set_product_display_row_height(row)

        except Exception as e:
            print(f"渲染记录失败：{e}")
            import traceback
            traceback.print_exc()
    
    def render_store_records(self, row, store_id, days):
        try:
            rec_dict = self.db.get_store_record(store_id, self.year, self.month, 0)
            
            for day in range(1, days + 1):
                cell_data = rec_dict.get(day, [])
                
                if cell_data:
                    display_text = "\n".join([self._format_operation_record_for_cell(item) for item in cell_data])
                else:
                    display_text = ""
                
                item = self.table.item(row, day)
                if not item:
                    item = QTableWidgetItem()
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row, day, item)
                
                item.setText(display_text)
                item.setToolTip(self._format_operation_record_tooltip(cell_data) if cell_data else display_text)
                item.setData(Qt.UserRole, cell_data)
                self._apply_record_cell_style(item)

        except Exception as e:
            print(f"渲染店铺记录失败：{e}")
            import traceback
            traceback.print_exc()
    
    def open_editor(self, row, col):
        if col == 0:
            return
        
        if row in self.row_store_map:
            self.open_store_record_editor(row, col)
            return
        
        if row not in self.row_data_map:
            return
            
        prod_id = self.row_data_map[row]
        day = col

        try:
            res = self.db.safe_fetchall("SELECT records_json FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                                   (prod_id, self.year, self.month, day))
            records = json.loads(res[0][0]) if res else []
        except:
            records = []

        prod_code = str(prod_id)
        prod_store_id = self.product_store_map.get(prod_id)
        try:
            prod_res = self.db.safe_fetchall("SELECT name FROM products WHERE id=?", (prod_id,))
            if prod_res and prod_res[0][0]:
                prod_code = prod_res[0][0]
        except:
            pass

        store_name = ""
        if prod_store_id:
            try:
                store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (prod_store_id,))
                if store_res and store_res[0][0]:
                    store_name = store_res[0][0]
            except:
                pass

        def save_callback(new_data):
            try:
                self._sync_main_image_history_from_record_save(prod_id, records, new_data, self.year, self.month, day)
                if new_data:
                    new_data = self._sort_records_by_time(new_data)
                    self.db.safe_execute("INSERT OR REPLACE INTO records (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
                                    (prod_id, self.year, self.month, day, json.dumps(new_data)))
                else:
                    self.db.safe_execute("DELETE FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                                    (prod_id, self.year, self.month, day))
                self.load_data_safe()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"保存记录失败：{e}")
                self.load_data_safe()

        dialog = OperationRecordDialog(records, prod_id, prod_code, self.year, self.month, day, save_callback, self, store_id=prod_store_id, store_name=store_name)
        dialog.exec_()

    def _sort_records_by_time(self, records):
        def key(record):
            text = str(record.get("time", "") if isinstance(record, dict) else "")
            try:
                hour, minute = text.split(":", 1)
                return (int(hour), int(minute))
            except Exception:
                return (99, 99)
        return sorted(records or [], key=key)

    def _main_image_history_id_from_record(self, record):
        if not isinstance(record, dict):
            return None
        history_id = record.get("history_id")
        if history_id:
            return history_id
        for change in record.get("changes", []) or []:
            if isinstance(change, dict) and change.get("type") == "main_carousel_image" and change.get("history_id"):
                return change.get("history_id")
        return None

    def _main_image_history_ids_from_records(self, records):
        ids = set()
        for record in records or []:
            history_id = self._main_image_history_id_from_record(record)
            if history_id:
                ids.add(history_id)
        return ids

    def _sync_main_image_history_from_record_save(self, product_id, old_records, new_records, year, month, day):
        old_ids = self._main_image_history_ids_from_records(old_records)
        new_ids = self._main_image_history_ids_from_records(new_records)
        deleted_ids = old_ids - new_ids
        for history_id in deleted_ids:
            self.db.safe_execute(
                "DELETE FROM product_image_history WHERE id=? AND product_id=?",
                (history_id, product_id)
            )

        for record in new_records or []:
            history_id = self._main_image_history_id_from_record(record)
            if not history_id:
                continue
            time_text = record.get("time", "")
            if not time_text:
                continue
            changed_at = f"{year:04d}-{month:02d}-{day:02d} {time_text}:00"
            self.db.safe_execute(
                "UPDATE product_image_history SET changed_at=? WHERE id=? AND product_id=?",
                (changed_at, history_id, product_id)
            )

    def open_store_record_editor(self, row, col):
        store_id = self.row_store_map[row]
        day = col
        
        records = self.db.get_store_record(store_id, self.year, self.month, day)
        
        store_name = ""
        try:
            store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
            if store_res and store_res[0][0]:
                store_name = store_res[0][0]
        except:
            pass
        
        def save_callback(new_data):
            try:
                if new_data:
                    self.db.save_store_record(store_id, self.year, self.month, day, new_data)
                else:
                    self.db.safe_execute("DELETE FROM store_records WHERE store_id=? AND year=? AND month=? AND day=?",
                                    (store_id, self.year, self.month, day))
                self.load_data_safe()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"保存记录失败：{e}")
                self.load_data_safe()

        dialog = OperationRecordDialog(records, store_id, store_name, self.year, self.month, day, save_callback, self, store_id=store_id, store_name=store_name)
        dialog.exec_()
    
    def _activate_cell(self, row, col):
        """辅助方法：安全地选中并刷新指定单元格"""
        try:
            if 0 <= row < self.table.rowCount() and 0 <= col < self.table.columnCount():
                # 选中单元格
                self.table.setCurrentCell(row, col)
                # 强制视口重绘
                self.table.viewport().update()
                # 把焦点给表格，防止焦点还停留在空气里
                self.table.setFocus()
        except:
            pass

    def open_product_spec_dialog_from_table(self, row, col):
        """双击格子打开规格管理弹窗"""
        if row not in self.row_data_map:
            return
        
        product_id = self.row_data_map[row]  # 数据库自增ID
        
        # 从冻结列控件获取商品ID和标题
        widget = self.frozen_table.cellWidget(row, 0)
        prod_code = "未知ID"
        prod_title = "未知标题"
        
        if widget and isinstance(widget, ProductWidget):
            # 从ProductWidget中获取
            prod_code = widget.prod_code      # 用户输入的ID
            prod_title = widget.prod_title    # 商品标题
        
        # 直接使用 ProductSpecDialog（不需要导入，因为在同一个文件）
        dialog = ProductSpecDialog(self.db, product_id, prod_code, prod_title, self)
        dialog.show()

    def prev_month(self):
        try:
            if self.month == 1:
                self.month = 12
                self.year -= 1
            else:
                self.month -= 1
            self.load_data_safe()
        except Exception as e:
            print(f"切换上个月失败: {e}")

    def next_month(self):
        try:
            if self.month == 12:
                self.month = 1
                self.year += 1
            else:
                self.month += 1
            self.load_data_safe()
        except Exception as e:
            print(f"切换下个月失败: {e}")

    def go_to_today(self):
        try:
            today = datetime.now()
            need_reload = self.year != today.year or self.month != today.month
            if need_reload:
                self.year = today.year
                self.month = today.month
                self.load_data_safe()
            day = today.day
            if 0 < day < self.table.columnCount():
                v_scroll = self.table.verticalScrollBar()
                saved_y = v_scroll.value()
                h_scroll = self.table.horizontalScrollBar()
                has_filter = bool(self.current_store_filter)
                if has_filter:
                    for row in range(self.table.rowCount()):
                        self.table.setRowHidden(row, False)
                        self.frozen_table.setRowHidden(row, False)
                target_index = self.table.model().index(0, day)
                self.table.scrollTo(target_index, QAbstractItemView.PositionAtCenter)
                self.table.setCurrentCell(0, day)
                if has_filter:
                    for row in range(self.table.rowCount()):
                        prod_id = self.row_data_map.get(row)
                        store_id_at_row = self.row_store_map.get(row)
                        should_hide = True
                        if row in self.row_store_map:
                            if self.row_store_map[row] in self.current_store_filter:
                                should_hide = False
                        elif prod_id:
                            product_store_id = self.product_store_map.get(prod_id)
                            if product_store_id and product_store_id in self.current_store_filter:
                                should_hide = False
                        if should_hide:
                            self.table.setRowHidden(row, True)
                            self.frozen_table.setRowHidden(row, True)
                v_scroll.setValue(saved_y)
                self.show_toast(f"已定位到今天: {today.month}月{today.day}日")
        except Exception as e:
            print(f"定位今天失败: {e}")

    def _locate_today_on_startup(self):
        try:
            today = datetime.now()
            if self.year != today.year or self.month != today.month:
                return
            day = today.day
            if not (0 < day < self.table.columnCount()):
                return
            target_index = self.table.model().index(0, day)
            self.table.scrollTo(target_index, QAbstractItemView.PositionAtCenter)
            self.table.setCurrentCell(0, day)
            self.update_frozen_geometry()
        except Exception as e:
            print(f"启动定位今天失败: {e}")

    def add_store(self):
        try:
            name, ok = QInputDialog.getText(self, "添加店铺", "请输入店铺名称:")
            if ok and name:
                result = self.db.safe_fetchall("SELECT MAX(sort_order) FROM stores")
                max_order = result[0][0] if result and result[0][0] is not None else 0
                self.db.safe_execute("INSERT INTO stores (name, sort_order) VALUES (?, ?)", (name, max_order + 1))
                self.load_data_safe()
        except Exception as e:
            print(f"添加店铺失败: {e}")
            QMessageBox.warning(self, "错误", f"添加店铺失败: {e}")

    def record_store_link_change(self, store_id, action, product_id, product_title):
        """记录店铺链接上架/删除到店铺行操作记录。"""
        try:
            now = datetime.now()
            time_str = now.strftime("%H:%M")
            action_text = "链接上架" if action == "add" else "链接删除"
            product_id = str(product_id or "").strip()
            product_title = str(product_title or "").strip()
            log_text = f"【{action_text}】商品ID：{product_id}｜标题：{product_title}"
            records = self.db.get_store_record(store_id, now.year, now.month, now.day)
            if not isinstance(records, list):
                records = []
            records.append({
                "time": time_str,
                "text": log_text,
                "type": "link_change",
                "action": action,
                "product_id": product_id,
                "product_title": product_title,
            })
            self.db.save_store_record(store_id, now.year, now.month, now.day, records)
        except Exception as e:
            print(f"记录店铺链接变化失败: {e}")

    def record_product_operation(self, product_db_id, text, metric="操作记录", old="", new="", change_type="product_operation"):
        """给商品当天日期格追加一条结构化操作记录。"""
        try:
            if not product_db_id:
                return
            now = datetime.now()
            time_str = now.strftime("%H:%M")
            year, month, day = now.year, now.month, now.day
            text = str(text or "").strip()
            metric = str(metric or "操作记录").strip()
            record = {
                "time": time_str,
                "text": text,
                "changes": [{
                    "time": time_str,
                    "metric": metric,
                    "old": "" if old is None else str(old),
                    "new": "" if new is None else str(new),
                    "text": text,
                    "type": change_type,
                }]
            }
            rows = self.db.safe_fetchall(
                "SELECT records_json FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                (product_db_id, year, month, day)
            )
            records = []
            if rows and rows[0][0]:
                try:
                    records = json.loads(rows[0][0])
                except Exception:
                    records = []
            if not isinstance(records, list):
                records = []
            records.append(record)
            records = self._sort_records_by_time(records)
            self.db.safe_execute(
                "INSERT OR REPLACE INTO records (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
                (product_db_id, year, month, day, json.dumps(records, ensure_ascii=False))
            )
        except Exception as e:
            print(f"记录商品操作失败: {e}")

    def add_product(self, store_id, copy_from_id=None):
        """添加商品 - 支持手动输入商品ID和标题，copy_from_id用于复制同款"""
        try:
            # 如果是复制模式，获取原商品信息
            copy_data = {}
            if copy_from_id:
                rows = self.db.safe_fetchall(
                    "SELECT name, title, coupon_amount, new_customer_discount, image_path, product_memo FROM products WHERE id=?",
                    (copy_from_id,)
                )
                if rows and rows[0]:
                    copy_data = {
                        'name': rows[0][0],
                        'title': rows[0][1],
                        'coupon_amount': rows[0][2],
                        'new_customer_discount': rows[0][3],
                        'image_path': rows[0][4],
                        'product_memo': rows[0][5]
                    }
            
            # 创建一个自定义对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("添加新商品 - 复制同款" if copy_from_id else "添加新商品")
            dialog.setFixedSize(500, 350)
            
            layout = QVBoxLayout(dialog)
            
            # 商品ID输入
            id_layout = QHBoxLayout()
            id_layout.addWidget(QLabel("商品ID:"))
            id_input = QLineEdit()
            id_input.setPlaceholderText("请输入商品ID（用于搜索和绑定链接）")
            id_layout.addWidget(id_input)
            layout.addLayout(id_layout)
            
            # 商品标题输入
            title_layout = QHBoxLayout()
            title_layout.addWidget(QLabel("商品标题:"))
            title_input = QLineEdit()
            title_input.setPlaceholderText("请输入商品标题")
            if copy_data:
                title_input.setText(copy_data.get('title', ''))
            title_layout.addWidget(title_input)
            layout.addLayout(title_layout)
            
            # 优惠券金额
            coupon_layout = QHBoxLayout()
            coupon_layout.addWidget(QLabel("优惠券金额:"))
            coupon_input = QLineEdit()
            coupon_input.setPlaceholderText("请输入优惠券金额")
            if copy_data and copy_data.get('coupon_amount'):
                coupon_input.setText(str(copy_data.get('coupon_amount')))
            coupon_layout.addWidget(coupon_input)
            layout.addLayout(coupon_layout)
            
            # 新客立减
            newcust_layout = QHBoxLayout()
            newcust_layout.addWidget(QLabel("新客立减:"))
            newcust_input = QLineEdit()
            newcust_input.setPlaceholderText("请输入新客立减金额")
            if copy_data and copy_data.get('new_customer_discount'):
                newcust_input.setText(str(copy_data.get('new_customer_discount')))
            newcust_layout.addWidget(newcust_input)
            layout.addLayout(newcust_layout)
            
            # 提示标签
            tip_text = "提示：复制同款模式 - 除商品ID外，其他信息已从原商品复制，请修改ID后保存。"
            if not copy_from_id:
                tip_text = "提示：商品ID是您手动输入的链接ID，用于搜索；商品标题是商品名称。"
            tip_label = QLabel(tip_text)
            tip_label.setStyleSheet("color: #666; font-size: 10px;")
            tip_label.setWordWrap(True)
            layout.addWidget(tip_label)
            
            # 按钮
            btn_layout = QHBoxLayout()
            btn_ok = QPushButton("确定")
            btn_ok.clicked.connect(dialog.accept)
            btn_cancel = QPushButton("取消")
            btn_cancel.clicked.connect(dialog.reject)
            btn_layout.addWidget(btn_ok)
            btn_layout.addWidget(btn_cancel)
            layout.addLayout(btn_layout)
            
            # 显示对话框
            if dialog.exec_() != QDialog.Accepted:
                return
                
            product_id = id_input.text().strip()
            product_title = title_input.text().strip()
            coupon_amount = coupon_input.text().strip()
            new_customer_discount = newcust_input.text().strip()
            
            if not product_id:
                QMessageBox.warning(self, "提示", "商品ID不能为空！")
                return
            if not product_title:
                QMessageBox.warning(self, "提示", "商品标题不能为空！")
                return
            
            # 检查商品ID是否已存在
            existing = self.db.safe_fetchall("SELECT id FROM products WHERE name=?", (product_id,))
            if existing:
                QMessageBox.warning(self, "提示", f"商品ID '{product_id}' 已存在，请使用不同的ID！")
                return
            
            # 获取当前店铺的最大排序值
            result = self.db.safe_fetchall("SELECT MAX(sort_order) FROM products WHERE store_id=?", (store_id,))
            max_order = result[0][0] if result and result[0][0] is not None else 0
            
            # 插入数据库
            self.db.safe_execute(
                "INSERT INTO products (store_id, name, title, coupon_amount, new_customer_discount, image_path, sort_order, product_memo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                (store_id, product_id, product_title, 
                 float(coupon_amount) if coupon_amount else None,
                 float(new_customer_discount) if new_customer_discount else None,
                 copy_data.get('image_path') if copy_from_id else None,
                 max_order + 1,
                 copy_data.get('product_memo') if copy_from_id else None)
            )
            
            # 获取新插入商品的数据库自增ID（不是用户输入的商品ID）
            new_product_db_id = self.db.safe_fetchall("SELECT last_insert_rowid()")[0][0]
            
            # 如果是复制模式，复制规格信息（使用数据库自增ID）
            if copy_from_id:
                specs = self.db.safe_fetchall(
                    "SELECT spec_name, spec_code, sale_price, weight_percent, is_locked FROM product_specs WHERE product_id=? ORDER BY id",
                    (copy_from_id,)
                )
                if specs:
                    for spec in specs:
                        self.db.safe_execute(
                            "INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent, is_locked) VALUES (?, ?, ?, ?, ?, ?)",
                            (new_product_db_id, spec[0], spec[1], spec[2], spec[3], spec[4])
                        )
            
            # 显示成功提示
            self.show_toast(f"✅ 商品添加成功\nID: {product_id}\n标题: {product_title}")
            self.record_product_operation(
                new_product_db_id,
                f"新建链接：商品ID {product_id}，标题：{product_title}",
                metric="新建链接",
                old="",
                new=product_id,
                change_type="product_created",
            )
            self.record_store_link_change(store_id, "add", product_id, product_title)
            self.load_data_safe()
            
        except Exception as e:
            print(f"添加商品失败: {e}")
            QMessageBox.warning(self, "错误", f"添加商品失败: {e}")
            
    def perform_search(self):
        self.apply_realtime_search()

    def _split_search_terms(self, text):
        return [term.strip().lower() for term in str(text or "").split() if term.strip()]

    def apply_realtime_search(self):
        try:
            terms = self._split_search_terms(self.search_input.text())
            if not terms:
                self.clear_search_filter()
                return

            product_ids = [pid for pid in self.row_data_map.values() if pid]
            if not product_ids:
                self.clear_search_filter()
                return

            placeholders = ",".join(["?"] * len(product_ids))
            rows = self.db.safe_fetchall(
                f"SELECT id, name, title, product_memo FROM products WHERE id IN ({placeholders})",
                tuple(product_ids)
            )
            match_ids = set()
            for pid, name, title, memo in rows:
                haystack = " ".join([
                    str(name or ""),
                    str(title or ""),
                    str(memo or "")
                ]).lower()
                if all(term in haystack for term in terms):
                    match_ids.add(pid)

            highlighted_rows = set()
            for row, pid in self.row_data_map.items():
                active = pid in match_ids
                self._set_row_search_highlight(row, active)
                if active:
                    highlighted_rows.add(row)
            self._search_highlighted_rows = highlighted_rows
            self.current_search_match_ids = match_ids
            self.apply_tag_filter(close_menu=False, show_message=False)
            self._scroll_to_first_search_match(highlighted_rows)
        except Exception as e:
            print(f"实时搜索失败: {e}")

    def clear_search_filter(self):
        self.current_search_match_ids = None
        self.clear_search_highlight()
        self.apply_tag_filter(close_menu=False, show_message=False)

    def clear_search_highlight(self):
        try:
            for row in list(getattr(self, "_search_highlighted_rows", set())):
                self._set_row_search_highlight(row, False)
            self._search_highlighted_rows = set()
        except Exception as e:
            print(f"清除搜索高亮失败: {e}")

    def _set_row_search_highlight(self, row, active):
        widget = self.frozen_table.cellWidget(row, 0)
        if widget and hasattr(widget, "set_search_highlight"):
            widget.set_search_highlight(active)

        color = QBrush(QColor("#fff8d8")) if active else QBrush()
        for col in range(1, self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(color)

    def _scroll_to_first_search_match(self, rows):
        try:
            if not rows:
                return
            visible_rows = [
                row for row in sorted(rows)
                if not self.table.isRowHidden(row) and not self.frozen_table.isRowHidden(row)
            ]
            target_row = visible_rows[0] if visible_rows else sorted(rows)[0]
            h_scroll = self.table.horizontalScrollBar()
            saved_x = h_scroll.value() if h_scroll else None
            target_index = self.frozen_table.model().index(target_row, 0)
            self.frozen_table.scrollTo(target_index, QAbstractItemView.PositionAtCenter)
            if h_scroll and saved_x is not None:
                h_scroll.setValue(saved_x)
            self.update_frozen_geometry()
        except Exception as e:
            print(f"搜索跳转失败: {e}")

    def _reapply_search_and_filters_after_load(self):
        try:
            if self.search_input.text().strip():
                self.apply_realtime_search()
            else:
                self.clear_search_filter()
            if getattr(self, "current_category_filter", "") or getattr(self, "current_filter_tags", None):
                self.apply_tag_filter(close_menu=False)
        except Exception as e:
            print(f"刷新搜索和筛选状态失败: {e}")
    
    def on_filter_toggle(self, state):
        if state == Qt.Unchecked:
            # 取消勾选时清除筛选
            self.clear_filter()
    
    def _create_filter_button(self, text, icon_name=None, color="#333"):
        """创建筛选按钮，带图标"""
        icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        btn = QPushButton(text)
        
        if icon_name:
            icon_path = os.path.join(icons_dir, icon_name)
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
        
        btn.setStyleSheet(f"""
            QPushButton {{
                border: 1px solid {color};
                background-color: transparent;
                color: {color};
                border-radius: 4px;
                padding: 6px 12px;
                text-align: left;
                icon-size: 20px;
            }}
            QPushButton:checked {{
                background-color: {color};
                color: white;
            }}
            QPushButton:hover {{
                background-color: {color};
                color: white;
            }}
        """)
        return btn
    
    def get_all_product_ids_with_current_store(self):
        """获取当前视图所有商品的ID（不受筛选影响）"""
        try:
            product_ids = []
            for row in range(self.table.rowCount()):
                prod_id = self.row_data_map.get(row)
                if prod_id:
                    product_ids.append(prod_id)
            return product_ids
        except Exception as e:
            print(f"获取商品ID失败: {e}")
            return []

    def _clear_layout_widgets(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _get_current_category_counts(self, keyword=""):
        product_ids = self.get_all_product_ids_with_current_store()
        if not product_ids:
            return []
        placeholders = ",".join(["?"] * len(product_ids))
        rows = self.db.safe_fetchall(
            f"""
            SELECT product_category_label, COUNT(*)
            FROM products
            WHERE id IN ({placeholders})
              AND COALESCE(product_category_label, '') <> ''
            GROUP BY product_category_label
            ORDER BY COUNT(*) DESC, product_category_label ASC
            """,
            tuple(product_ids)
        )
        keyword = str(keyword or "").strip().lower()
        result = []
        for label, count in rows:
            label_text = str(label or "").strip()
            if not label_text:
                continue
            if keyword and keyword not in label_text.lower():
                continue
            result.append((label_text, count))
        return result

    def refresh_category_filter_candidates(self):
        try:
            if not hasattr(self, "category_candidate_layout"):
                return
            self._clear_layout_widgets(self.category_candidate_layout)
            keyword = self.category_filter_input.text().strip() if hasattr(self, "category_filter_input") else ""
            categories = self._get_current_category_counts(keyword)[:12]
            if not keyword and not self.current_category_filter:
                hint = QLabel("输入关键字后显示类型候选")
                hint.setStyleSheet("color: #999; font-size: 12px; padding: 4px;")
                self.category_candidate_layout.addWidget(hint)
                return
            if not categories:
                hint = QLabel("没有匹配的商品类型")
                hint.setStyleSheet("color: #999; font-size: 12px; padding: 4px;")
                self.category_candidate_layout.addWidget(hint)
                return
            for label, count in categories:
                btn = QPushButton(f"{label} ({count})")
                btn.setCheckable(True)
                btn.setChecked(label == self.current_category_filter)
                btn.setStyleSheet("""
                    QPushButton {
                        border: 1px solid #3498db;
                        background-color: transparent;
                        color: #2c3e50;
                        border-radius: 4px;
                        padding: 5px 8px;
                        text-align: left;
                    }
                    QPushButton:checked {
                        background-color: #3498db;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #3498db;
                        color: white;
                    }
                """)
                btn.clicked.connect(lambda checked=False, value=label: self.set_category_filter(value))
                self.category_candidate_layout.addWidget(btn)
        except Exception as e:
            print(f"刷新商品类型候选失败: {e}")

    def set_category_filter(self, category_label):
        self.current_category_filter = str(category_label or "").strip()
        if hasattr(self, "category_filter_input"):
            self.category_filter_input.blockSignals(True)
            self.category_filter_input.setText(self.current_category_filter)
            self.category_filter_input.blockSignals(False)
        self.refresh_category_filter_candidates()
        self.apply_tag_filter(close_menu=False)

    def clear_category_filter(self):
        self.current_category_filter = ""
        if hasattr(self, "category_filter_input"):
            self.category_filter_input.blockSignals(True)
            self.category_filter_input.clear()
            self.category_filter_input.blockSignals(False)
        self.refresh_category_filter_candidates()
        self.apply_tag_filter(close_menu=False)

    def _product_matches_category_filter(self, product_id):
        if not self.current_category_filter:
            return True
        rows = self.db.safe_fetchall(
            "SELECT product_category_label FROM products WHERE id=?",
            (product_id,)
        )
        label = str(rows[0][0] or "").strip() if rows else ""
        return label == self.current_category_filter
    
    def show_tag_filter_menu(self):
        """显示标签筛选下拉菜单"""
        self.refresh_category_filter_candidates()
        btn_rect = self.btn_tag_filter.rect()
        global_pos = self.btn_tag_filter.mapToGlobal(QPoint(0, btn_rect.bottom()))
        self.tag_filter_menu.move(global_pos)
        if not self._tag_filter_global_filter_installed:
            QApplication.instance().installEventFilter(self)
            self._tag_filter_global_filter_installed = True
        self.tag_filter_menu.show()
        self.tag_filter_menu.raise_()
        self.tag_filter_menu.activateWindow()
        QTimer.singleShot(0, self.category_filter_input.setFocus)

    def show_store_filter_menu(self):
        """显示店铺筛选下拉菜单"""
        self.store_filter_menu = QDialog(self)
        self.store_filter_menu.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)
        self.store_filter_menu.setStyleSheet("""
            QDialog {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            QCheckBox {
                padding: 5px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)

        filter_layout = QVBoxLayout(self.store_filter_menu)
        filter_layout.setContentsMargins(10, 10, 10, 10)
        filter_layout.setSpacing(5)

        filter_title = QLabel("🏪 选择筛选店铺")
        filter_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50; padding-bottom: 5px;")
        filter_layout.addWidget(filter_title)

        filter_layout.addWidget(QLabel("<hr>"))

        self.store_checkboxes = {}
        stores = self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order")
        saved_filter_ids = self.db.get_setting("store_filter_ids", "")
        if saved_filter_ids:
            saved_filter_set = set(int(x) for x in saved_filter_ids.split(",") if x)
        else:
            saved_filter_set = set()
        for store_id, store_name in stores:
            cb = QCheckBox(store_name)
            cb.setCheckable(True)
            if store_id in saved_filter_set:
                cb.setChecked(True)
            cb.stateChanged.connect(lambda state, sid=store_id: self.apply_store_filter(sid))
            self.store_checkboxes[store_id] = cb
            filter_layout.addWidget(cb)

        filter_layout.addWidget(QLabel("<hr>"))

        btn_layout = QHBoxLayout()
        btn_save_filter = QPushButton("💾 保存筛选")
        btn_save_filter.setStyleSheet("""
            QPushButton { background-color: #27ae60; color: white; border: none; padding: 8px 16px; border-radius: 3px; font-weight: bold; }
            QPushButton:hover { background-color: #219a52; }
        """)
        btn_save_filter.clicked.connect(lambda: self.apply_store_filter(close_menu=True))
        btn_clear_filter = QPushButton("清空")
        btn_clear_filter.setStyleSheet("""
            QPushButton { background-color: #95a5a6; color: white; border: none; padding: 8px 16px; border-radius: 3px; font-weight: bold; }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        btn_clear_filter.clicked.connect(self.clear_store_filter_selection)
        btn_layout.addWidget(btn_save_filter)
        btn_layout.addWidget(btn_clear_filter)
        filter_layout.addLayout(btn_layout)

        self.current_store_filter = saved_filter_set.copy()
        self.store_filter_menu_selected_store = None

        btn_rect = self.btn_store_filter.rect()
        global_pos = self.btn_store_filter.mapToGlobal(QPoint(0, btn_rect.bottom()))
        self.store_filter_menu.move(global_pos)
        self.store_filter_menu.exec_()

    def apply_store_filter(self, store_id=None, close_menu=False):
        """应用店铺筛选

        Args:
            store_id: 如果指定，则只切换该店铺的选中状态
            close_menu: 是否关闭筛选菜单
        """
        try:
            if store_id is not None:
                checkbox = self.store_checkboxes.get(store_id)
                if checkbox:
                    if checkbox.isChecked():
                        self.current_store_filter.add(store_id)
                    else:
                        self.current_store_filter.discard(store_id)

            if close_menu and self.store_filter_menu:
                self.store_filter_menu.close()
                return

            if not self.current_store_filter:
                self.clear_store_filter()
                return

            selected_store_id = store_id if store_id else (list(self.current_store_filter)[0] if self.current_store_filter else None)

            hidden_count = 0
            for row in range(self.table.rowCount()):
                prod_id = self.row_data_map.get(row)
                store_id_at_row = self.row_store_map.get(row)

                should_hide = True
                if row in self.row_store_map:
                    if self.row_store_map[row] in self.current_store_filter:
                        should_hide = False
                elif prod_id:
                    product_store_id = self.product_store_map.get(prod_id)
                    if product_store_id and product_store_id in self.current_store_filter:
                        should_hide = False

                if should_hide:
                    hidden_count += 1
                    self.table.setRowHidden(row, True)
                    self.frozen_table.setRowHidden(row, True)
                else:
                    self.table.setRowHidden(row, False)
                    self.frozen_table.setRowHidden(row, False)

            filtered_count = self.table.rowCount() - hidden_count
            self.btn_store_filter.setText(f"🏪 店铺 ({filtered_count})")
            self.db.set_setting("store_filter_ids", ",".join(map(str, self.current_store_filter)) if self.current_store_filter else "")
            self.show_toast(f"店铺筛选: 显示 {filtered_count} 个商品")

        except Exception as e:
            print(f"应用店铺筛选失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "筛选失败", f"店铺筛选出错: {e}")

    def clear_store_filter_selection(self):
        """清空店铺筛选选择"""
        for cb in self.store_checkboxes.values():
            cb.setChecked(False)
        self.current_store_filter.clear()
        self.db.set_setting("store_filter_ids", "")

    def clear_store_filter(self):
        """清除店铺筛选，显示所有商品"""
        self.clear_store_filter_selection()
        self.btn_store_filter.setText("🏪 店铺")

        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
            self.frozen_table.setRowHidden(row, False)

        self.show_toast("已清除店铺筛选")
        self.current_store_filter = set()
    
    def calculate_profit_label(self, product_id):
        """根据净利润率计算利润标签: 赚钱>5%, 亏钱<5%, 保本=5%"""
        try:
            specs = self.db.safe_fetchall(
                "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                (product_id,)
            )
            
            if not specs:
                return 0
            
            prod_res = self.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
                (product_id,)
            )
            
            coupon = 0
            new_customer = 0
            if prod_res:
                coupon = prod_res[0][0] or 0
                new_customer = prod_res[0][1] or 0
            
            max_discount = max(coupon, new_customer)
            
            total_weight = 0
            total_profit = 0
            total_final_price = 0
            
            for spec_code, sale_price, weight in specs:
                if not sale_price or sale_price <= 0:
                    continue
                
                weight = weight or 0
                
                cost_res = self.db.safe_fetchall(
                    "SELECT cost_price FROM cost_library WHERE spec_code=?",
                    (spec_code,)
                )
                cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
                
                final_price = sale_price - max_discount
                
                if final_price > 0:
                    profit = final_price - cost
                    total_profit += profit * weight
                    total_final_price += final_price * weight
                    total_weight += weight
            
            if total_weight > 0:
                avg_profit = total_profit / total_weight
                avg_final_price = total_final_price / total_weight
                net_margin_rate = (avg_profit / avg_final_price) * 100 if avg_final_price > 0 else 0

                if net_margin_rate >= 1:
                    return 1
                elif net_margin_rate >= -2:
                    return 0
                else:
                    return -1
            
            return 0
        except Exception as e:
            print(f"计算利润标签失败: {e}")
            return 0
    
    def _calculate_profit_category(self, product_id):
        """根据净利率计算利润分类: 赚钱≥5%, 亏钱<5%, 保本-5%~5%"""
        try:
            rows = self.db.safe_fetchall(
                "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?", 
                (product_id,)
            )
            
            if not rows:
                return 'loss'
            
            product_rows = self.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate, is_natural_flow, is_sitewide_managed, store_id FROM products WHERE id=?",
                (product_id,)
            )
            max_discount = 0
            current_roi = 0
            return_rate = 0
            is_natural_flow = 0
            is_sitewide_managed = 0
            sitewide_roi = 0
            
            if product_rows:
                coupon = product_rows[0][0] if product_rows[0][0] else 0
                new_customer = product_rows[0][1] if product_rows[0][1] else 0
                max_discount = max(coupon, new_customer)
                current_roi = product_rows[0][2] if product_rows[0][2] else 0
                return_rate = product_rows[0][3] if product_rows[0][3] else 0
                is_natural_flow = product_rows[0][4] if product_rows[0][4] else 0
                is_sitewide_managed = product_rows[0][5] if product_rows[0][5] else 0
                store_id = product_rows[0][6] if product_rows[0][6] else None
                if store_id:
                    store_rows = self.db.safe_fetchall("SELECT sitewide_roi FROM stores WHERE id=?", (store_id,))
                    sitewide_roi = store_rows[0][0] if store_rows and store_rows[0][0] else 0
            
            total_weighted_margin = 0.0
            total_weight = 0.0
            
            for r in rows:
                spec_code = r[0]
                sale_price = r[1]
                weight = r[2]
                
                if sale_price is None or weight is None:
                    continue
                
                cost_res = self.db.safe_fetchall(
                    "SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,)
                )
                cost = cost_res[0][0] if cost_res else 0.0
                
                final_price = sale_price - max_discount
                if final_price > 0 and cost > 0:
                    margin = (final_price - cost) / final_price
                    total_weighted_margin += margin * weight
                    total_weight += weight
            
            if total_weight > 0:
                final_margin_pct = (total_weighted_margin / total_weight) * 100
                
                margin_rate_decimal = final_margin_pct / 100
                effective_roi = sitewide_roi if is_sitewide_managed and not is_natural_flow else current_roi
                final_net_margin_pct = -100
                if is_natural_flow:
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006) * 100
                elif effective_roi > 0 and return_rate >= 0:
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006 - (1 / effective_roi)) * 100
                
                if final_net_margin_pct >= 1:
                    return 'profit'
                elif final_net_margin_pct >= -2:
                    return 'break_even'
                else:
                    return 'loss'
            
            return 'loss'
        except Exception as e:
            print(f"计算利润分类失败: {e}")
            return 'loss'
    
    def apply_tag_filter(self, close_menu=False, show_message=True):
        """应用标签筛选
        
        Args:
            close_menu: 是否关闭筛选菜单，True=关闭，False=保持打开
        """
        try:
            filters = {}
            
            if self.btn_filter_coupon.isChecked():
                filters['coupon'] = True
            if self.btn_filter_new_customer.isChecked():
                filters['new_customer'] = True
            if self.btn_filter_limited_time.isChecked():
                filters['limited_time'] = True
            if self.btn_filter_marketing.isChecked():
                filters['marketing'] = True
            if self.btn_filter_natural_flow.isChecked():
                filters['natural_flow'] = True
            if self.btn_filter_sitewide.isChecked():
                filters['sitewide'] = True
            if self.btn_filter_missing_roi_bid.isChecked():
                filters['missing_roi_bid'] = True
            
            profit_filters = []
            if self.btn_filter_profit.isChecked():
                profit_filters.append('profit')
            if self.btn_filter_loss.isChecked():
                profit_filters.append('loss')
            if self.btn_filter_break_even.isChecked():
                profit_filters.append('break_even')
            
            # 只有明确要求关闭菜单时才关闭
            if close_menu:
                self.tag_filter_menu.close()
            
            has_category_filter = bool(getattr(self, "current_category_filter", ""))
            search_match_ids = getattr(self, "current_search_match_ids", None)
            has_search_filter = search_match_ids is not None

            if not filters and not profit_filters and not has_category_filter and not has_search_filter:
                self.clear_tag_filter()
                self.btn_tag_filter.setText("🏷️ 筛选")
                for row in range(self.table.rowCount()):
                    self.table.setRowHidden(row, False)
                    self.frozen_table.setRowHidden(row, False)
                if show_message:
                    self.show_toast("已显示所有商品")
                return
            
            all_product_ids = self.get_all_product_ids_with_current_store()
            if not all_product_ids:
                self.show_toast("当前视图无商品")
                return
            
            matching_ids = set()
            
            for pid in all_product_ids:
                should_include = True
                
                if filters.get('coupon'):
                    coupon_res = self.db.safe_fetchall("SELECT coupon_amount FROM products WHERE id=?", (pid,))
                    if not coupon_res or not coupon_res[0][0]:
                        should_include = False
                
                if filters.get('new_customer') and should_include:
                    nc_res = self.db.safe_fetchall("SELECT new_customer_discount FROM products WHERE id=?", (pid,))
                    if not nc_res or not nc_res[0][0]:
                        should_include = False
                
                if filters.get('limited_time') and should_include:
                    lt_res = self.db.safe_fetchall("SELECT is_limited_time FROM products WHERE id=?", (pid,))
                    if not lt_res or not lt_res[0][0]:
                        should_include = False
                
                if filters.get('marketing') and should_include:
                    mk_res = self.db.safe_fetchall("SELECT is_marketing FROM products WHERE id=?", (pid,))
                    if not mk_res or not mk_res[0][0]:
                        should_include = False

                if filters.get('natural_flow') and should_include:
                    nf_res = self.db.safe_fetchall("SELECT is_natural_flow FROM products WHERE id=?", (pid,))
                    if not nf_res or not nf_res[0][0]:
                        should_include = False

                if filters.get('sitewide') and should_include:
                    sw_res = self.db.safe_fetchall("SELECT is_sitewide_managed, is_natural_flow FROM products WHERE id=?", (pid,))
                    if not sw_res or not sw_res[0][0] or sw_res[0][1]:
                        should_include = False

                if filters.get('missing_roi_bid') and should_include:
                    roi_res = self.db.safe_fetchall("SELECT current_roi, is_natural_flow, is_sitewide_managed FROM products WHERE id=?", (pid,))
                    current_roi = roi_res[0][0] if roi_res and roi_res[0][0] is not None else 0
                    is_natural_flow = roi_res[0][1] if roi_res else 0
                    is_sitewide_managed = roi_res[0][2] if roi_res else 0
                    try:
                        current_roi = float(current_roi)
                    except (TypeError, ValueError):
                        current_roi = 0
                    if current_roi > 0 or is_natural_flow or is_sitewide_managed:
                        should_include = False
                
                if profit_filters and should_include:
                    profit_category = self._calculate_profit_category(pid)
                    if profit_category not in profit_filters:
                        should_include = False

                if has_category_filter and should_include:
                    if not self._product_matches_category_filter(pid):
                        should_include = False

                if has_search_filter and should_include:
                    if pid not in search_match_ids:
                        should_include = False
                
                if should_include:
                    matching_ids.add(pid)
            
            for row in range(self.table.rowCount()):
                prod_id = self.row_data_map.get(row)
                if prod_id and prod_id in matching_ids:
                    self.table.setRowHidden(row, False)
                    self.frozen_table.setRowHidden(row, False)
                else:
                    self.table.setRowHidden(row, True)
                    self.frozen_table.setRowHidden(row, True)
            
            filtered_count = len(matching_ids)
            self.current_filter_tags = filters.copy()
            if profit_filters:
                self.current_filter_tags['profit'] = profit_filters
            if has_category_filter:
                self.current_filter_tags['category'] = self.current_category_filter
            
            self.btn_tag_filter.setText(f"🏷️ 筛选 ({filtered_count})")
            if show_message:
                self.show_toast(f"筛选: 显示 {filtered_count} 个商品")
            
        except Exception as e:
            print(f"应用标签筛选失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "筛选失败", f"标签筛选出错: {e}")
    
    def clear_tag_filter_selection(self):
        """清空标签筛选选择"""
        buttons = [
            self.btn_filter_coupon,
            self.btn_filter_new_customer,
            self.btn_filter_limited_time,
            self.btn_filter_marketing,
            self.btn_filter_natural_flow,
            self.btn_filter_sitewide,
            self.btn_filter_profit,
            self.btn_filter_loss,
            self.btn_filter_break_even,
            self.btn_filter_missing_roi_bid,
        ]
        for btn in buttons:
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self.current_category_filter = ""
        if hasattr(self, "category_filter_input"):
            self.category_filter_input.blockSignals(True)
            self.category_filter_input.clear()
            self.category_filter_input.blockSignals(False)
        if hasattr(self, "category_candidate_layout"):
            self.refresh_category_filter_candidates()
    
    def clear_tag_filter(self):
        """清除标签筛选，显示所有商品"""
        self.clear_tag_filter_selection()
        self.btn_tag_filter.setText("🏷️ 筛选")
        
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
            self.frozen_table.setRowHidden(row, False)
        
        self.show_toast("已清除标签筛选")
        self.current_filter_tags = set()

        if getattr(self, "current_search_match_ids", None) is not None:
            self.apply_tag_filter(close_menu=False, show_message=False)
            return
        
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
            self.frozen_table.setRowHidden(row, False)
        
        self.show_toast("已清除标签筛选")
    
    def clear_filter(self):
        # 显示所有行
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
            self.frozen_table.setRowHidden(row, False)
        
        self.show_toast("已清除筛选，显示全部商品")

    def export_to_excel(self):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from openpyxl.utils import get_column_letter
        except ImportError:
            QMessageBox.warning(self, "错误", "请先安装openpyxl库: pip install openpyxl")
            return
        
        # 选择保存位置
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(self, "导出Excel", f"店铺数据_{self.year}_{self.month}.xlsx", "Excel文件 (*.xlsx)")
        if not file_path:
            return
        
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = f"{self.year}年{self.month}月数据"
            
            # 设置表头
            days_in_month = calendar.monthrange(self.year, self.month)[1]
            headers = ["店铺", "商品ID", "商品名称"] + [f"{i}号" for i in range(1, days_in_month + 1)]
            
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.fill = PatternFill(start_color="E6E6FA", end_color="E6E6FA", fill_type="solid")
                cell.border = Border(
                    left=Side(style="thin"),
                    right=Side(style="thin"),
                    top=Side(style="thin"),
                    bottom=Side(style="thin")
                )
            
            # 填充数据
            row_idx = 2
            stores = self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order")
            
            for store in stores:
                store_id, store_name = store
                products = self.db.safe_fetchall("SELECT id, name FROM products WHERE store_id=? ORDER BY sort_order", (store_id,))
                
                for prod in products:
                    prod_id, prod_name = prod
                    
                    # 获取该商品的记录
                    records = self.db.safe_fetchall(
                        "SELECT day, records_json FROM records WHERE product_id=? AND year=? AND month=?", 
                        (prod_id, self.year, self.month)
                    )
                    
                    record_dict = {}
                    for day, json_data in records:
                        try:
                            record_dict[day] = json.loads(json_data)
                        except:
                            record_dict[day] = []
                    
                    # 写入数据行
                    ws.cell(row=row_idx, column=1, value=store_name)
                    ws.cell(row=row_idx, column=2, value=prod_id)
                    ws.cell(row=row_idx, column=3, value=prod_name)
                    
                    for day in range(1, days_in_month + 1):
                        day_records = record_dict.get(day, [])
                        display_text = "\n".join([f"[{item['time']}] {item['text']}" for item in day_records])
                        ws.cell(row=row_idx, column=day + 3, value=display_text)
                    
                    row_idx += 1
            
            # 自动调整列宽
            for col in range(1, len(headers) + 1):
                column_letter = get_column_letter(col)
                ws.column_dimensions[column_letter].width = min(len(str(headers[col-1])) * 2, 50)
            
            wb.save(file_path)
            QMessageBox.information(self, "成功", f"数据已导出到: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")


    def _format_cost_quantity(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return ""
        numeric_text = text.replace(",", "")
        try:
            number = float(numeric_text)
        except ValueError:
            return text
        if number.is_integer():
            return str(int(number))
        return str(int(round(number)))

    def import_cost_data(self):
        """导入成本表 - 最终版 (直接全量读取，无预览，只显示结果)"""
        # 1. 检查依赖
        try:
            import pandas as pd  # type: ignore
        except ImportError as e:
            import sys
            python_path = sys.executable
            QMessageBox.critical(self, "缺少依赖", 
                f"未检测到 pandas 库！\n\n"
                f"当前Python: {python_path}\n"
                f"错误: {str(e)}\n\n"
                f"请在终端运行:\n"
                f"pip install pandas openpyxl")
            return

        # 2. 选择文件
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "选择成本表文件", 
            "", 
            "Excel Files (*.xlsx *.xlsm *.xls);;CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        # 4. 弹出配置对话框 (选择列)
        try:
            cost_mode = self.db.get_cost_library_mode() if hasattr(self.db, "get_cost_library_mode") else "total"
            dialog = CostImportDialog(file_path, self, cost_mode=cost_mode)
            if dialog.exec_() != QDialog.Accepted:
                return
            
            mapping = dialog.get_mapping()
            if len(mapping) == 6:
                spec_col_idx, price_col_idx, name_col_idx, quantity_col_idx, category_col_idx, weight_col_idx = mapping
                attribute_col_indices = None
            else:
                spec_col_idx, price_col_idx, name_col_idx, quantity_col_idx, category_col_idx, weight_col_idx, attribute_col_indices = mapping
            unit_by_quantity = dialog.should_unit_by_quantity() if hasattr(dialog, "should_unit_by_quantity") else False
            
            if spec_col_idx is None or price_col_idx is None:
                QMessageBox.warning(self, "提示", "请先选择【规格编码】和【总成本/产品成本】所在的列！")
                return
            if cost_mode == "detail" and weight_col_idx is None:
                QMessageBox.warning(self, "提示", "详细成本模式下请先选择【单个重量kg】所在的列！")
                return
                
        except Exception as e:
            QMessageBox.critical(self, "配置错误", f"打开配置窗口失败:\n{str(e)}")
            return

        # 5. 开始全量读取和处理
        try:
            self.statusBar().showMessage("正在读取并处理数据...", 0)
            QApplication.processEvents()

            df = read_cost_file(file_path)

            if df.empty:
                QMessageBox.warning(self, "提示", "文件内容为空！")
                self.statusBar.showMessage("导入取消", 3000)
                return

            total_rows = len(df)
            print(f"文件总行数：{total_rows}")

            # 获取用户选中的列数据 (使用 iloc 按位置索引获取)
            # astype(str) 确保规格编码变成字符串，防止数字变科学计数法
            col_spec = df.iloc[:, spec_col_idx].astype(str)
            col_price = df.iloc[:, price_col_idx]
            col_name = df.iloc[:, name_col_idx] if name_col_idx is not None else None
            col_quantity = df.iloc[:, quantity_col_idx] if quantity_col_idx is not None else None
            col_category = df.iloc[:, category_col_idx] if category_col_idx is not None else None
            col_weight = df.iloc[:, weight_col_idx] if weight_col_idx is not None else None
            attribute_cols = {}
            if attribute_col_indices:
                for key, col_idx in attribute_col_indices.items():
                    if col_idx is not None:
                        attribute_cols[key] = df.iloc[:, int(col_idx)]
            row_colors = read_cost_row_colors(file_path, name_col_idx=name_col_idx, spec_col_idx=spec_col_idx)
            
            count_success = 0
            count_skip = 0
            count_error = 0
            count_history = 0
            count_changed = 0
            count_unit_converted = 0
            import_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 批量插入准备 (为了提高速度，可以每100条提交一次，这里为了简单逐条处理但加了事务优化)
            # 实际上 safe_execute 已经是逐条提交，对于几万行数据可能会慢，但最稳定
            
            self.db.conn.execute("BEGIN TRANSACTION") # 开启事务，极大提高写入速度
            self.db.cursor.execute("UPDATE cost_library SET sort_order=NULL")

            for idx in range(total_rows):
                try:
                    # 获取规格
                    spec_val = col_spec.iloc[idx]
                    if not spec_val or spec_val.strip() == "" or spec_val.lower() == "nan":
                        count_skip += 1
                        continue
                    spec_code = spec_val.strip()

                    spec_name = ""
                    if col_name is not None:
                        name_val = col_name.iloc[idx]
                        if not pd.isna(name_val):
                            spec_name = str(name_val).strip()
                            if spec_name.lower() == "nan":
                                spec_name = ""

                    quantity = ""
                    if col_quantity is not None:
                        quantity_val = col_quantity.iloc[idx]
                        if not pd.isna(quantity_val):
                            quantity = self._format_cost_quantity(quantity_val)
                            if quantity.lower() == "nan":
                                quantity = ""

                    category_label = ""
                    if col_category is not None:
                        category_val = col_category.iloc[idx]
                        if not pd.isna(category_val):
                            category_label = str(category_val).strip()
                            if category_label.lower() == "nan":
                                category_label = ""
                    category_color = self.db.category_color_for_label(category_label)
                    source_bg_color = row_colors.get(idx, "")

                    product_attribute = ""
                    if attribute_cols and not re.search(r"\+|＋|﹢", spec_name or ""):
                        attr_parts = []
                        for key in ("size", "pages", "cover", "print"):
                            col_attr = attribute_cols.get(key)
                            if col_attr is None:
                                continue
                            attr_val = col_attr.iloc[idx]
                            if pd.isna(attr_val):
                                continue
                            attr_text = str(attr_val).strip()
                            if attr_text and attr_text.lower() != "nan":
                                attr_parts.append(attr_text)
                        product_attribute = " ".join(attr_parts)
                    
                    # 获取价格
                    price_val = col_price.iloc[idx]
                    parsed_price = self.db.parse_cost_number(price_val, None) if hasattr(self.db, "parse_cost_number") else None
                    if parsed_price is None:
                        parsed_price = 0.0

                    product_cost = None
                    unit_weight = None
                    shipping_fee = None
                    misc_fee = None
                    cost_calc_mode = cost_mode
                    if cost_mode == "detail":
                        product_cost = float(parsed_price)
                        if col_weight is None:
                            count_error += 1
                            continue
                        unit_weight = self.db.parse_cost_number(col_weight.iloc[idx], None) if hasattr(self.db, "parse_cost_number") else None
                        if unit_weight is None or unit_weight <= 0:
                            count_error += 1
                            continue
                        if unit_by_quantity and hasattr(self.db, "parse_cost_quantity_factor"):
                            quantity_factor = self.db.parse_cost_quantity_factor(quantity)
                            if quantity_factor and quantity_factor > 1:
                                product_cost = product_cost / quantity_factor
                                unit_weight = unit_weight / quantity_factor
                                count_unit_converted += 1
                        cost_price, shipping_fee, misc_fee, _total_weight = self.db.calculate_detailed_cost(product_cost, quantity, unit_weight)
                    else:
                        cost_price = float(parsed_price)
                        cost_calc_mode = "total"

                    old_rows = self.db.cursor.execute(
                        "SELECT cost_price FROM cost_library WHERE spec_code=?",
                        (spec_code,)
                    ).fetchall()
                    old_cost = float(old_rows[0][0]) if old_rows and old_rows[0][0] is not None else None
                    should_record_history = old_cost is not None and abs(cost_price - old_cost) > 0.001

                    self.db.cursor.execute(
                        """INSERT INTO cost_library
                           (spec_code, spec_name, quantity, category_label, category_color, cost_price, sort_order, source_bg_color,
                            product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode, product_attribute)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(spec_code) DO UPDATE SET
                               spec_name=excluded.spec_name,
                               quantity=excluded.quantity,
                               category_label=excluded.category_label,
                               category_color=excluded.category_color,
                               cost_price=excluded.cost_price,
                               sort_order=excluded.sort_order,
                               source_bg_color=excluded.source_bg_color,
                               product_cost=excluded.product_cost,
                               unit_weight=excluded.unit_weight,
                               shipping_fee=excluded.shipping_fee,
                               misc_fee=excluded.misc_fee,
                               cost_calc_mode=excluded.cost_calc_mode,
                               product_attribute=CASE
                                   WHEN excluded.product_attribute <> '' THEN excluded.product_attribute
                                   ELSE cost_library.product_attribute
                               END""",
                        (spec_code, spec_name, quantity, category_label, category_color, cost_price, idx + 1, source_bg_color,
                         product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode, product_attribute)
                    )

                    if should_record_history:
                        change_amount = cost_price - old_cost
                        change_percent = (cost_price - old_cost) / old_cost * 100 if old_cost else None
                        self.db.cursor.execute(
                            """INSERT INTO cost_history
                               (spec_code, old_cost_price, new_cost_price, change_amount, change_percent, source, import_time)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (spec_code, old_cost, cost_price, change_amount, change_percent, "import", import_time)
                        )
                        count_history += 1
                        count_changed += 1
                    
                    count_success += 1
                    
                    # 每处理 1000 行提交一次事务，防止内存溢出并保持响应
                    if count_success % 1000 == 0:
                        self.db.conn.commit()
                        self.statusBar().showMessage(f"已处理 {count_success}/{total_rows} 条...", 0)
                        QApplication.processEvents()

                except Exception as row_err:
                    count_error += 1
                    # 单行错误不中断，继续下一条
                    # print(f"第 {idx+1} 行处理失败：{row_err}")
                    continue
            
            # 提交剩余事务
            self.db.conn.commit()
            self.db.normalize_cost_category_colors()
            self.db.update_all_product_category_labels()
            self.statusBar().showMessage("导入完成！", 3000)

            # 6. 显示结果
            msg = (f"✅ **导入完成！**\n\n"
                   f"📌 成本模式：{'详细成本模式' if cost_mode == 'detail' else '总成本模式'}\n"
                   f"📊 文件总行数：{total_rows}\n"
                   f"✅ 成功入库：{count_success} 条\n"
                   f"🕘 历史记录：{count_history} 条\n"
                   f"📈 价格变化：{count_changed} 条\n"
                   f"⏭️ 跳过空行：{count_skip} 条\n"
                   f"❌ 处理异常：{count_error} 条\n\n"
                   f"数据已更新至数据库 cost_library 表。")
            
            QMessageBox.information(self, "导入结果", msg)
            print(msg)

        except Exception as e:
            # 发生严重错误，回滚事务
            try:
                self.db.conn.rollback()
            except:
                pass
            
            import traceback
            error_detail = traceback.format_exc()
            print(error_detail)
            
            QMessageBox.critical(self, "严重错误", 
                                 f"❌ 导入过程中发生未知错误！\n\n"
                                 f"错误信息：{str(e)}\n\n"
                                 f"详细信息已打印到控制台。\n\n"
                                 f"建议：\n"
                                 f"1. 检查文件是否损坏。\n"
                                 f"2. 确保选中了正确的列。\n"
                                 f"3. 尝试将文件另存为新的 .xlsx 文件。")
            self.statusBar().showMessage("导入失败", 3000)

    def show_cost_library(self):
        """打开成本库管理窗口"""
        dialog = CostLibraryDialog(self.db, self)
        dialog.show()

    def show_cloud_login_dialog(self):
        """打开云同步登录窗口"""
        try:
            from manager.cloud_sync import CloudSyncDialog
            active_account = self.cloud_manager.get_active_data_account() if self.cloud_manager else None
            if active_account:
                self.cloud_manager.switch_account(active_account['id'])
            dialog = CloudSyncDialog(self.db, self.cloud_manager, self)
            dialog.exec_()
            self.update_cloud_account_label()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"打开云同步窗口失败：\n{str(e)}")
            import traceback
            traceback.print_exc()

    def update_cloud_account_label(self):
        """更新当前本地数据归属账号显示标签"""
        try:
            if hasattr(self, 'cloud_manager') and self.cloud_manager:
                active_account = self.cloud_manager.get_active_data_account()
                if active_account:
                    self.lbl_cloud_account.setText(f"☁️ 当前应用: {active_account.get('name', '未知')}")
                    self.lbl_cloud_account.setStyleSheet("color: #27ae60; font-size: 11px; padding: 0 5px;")
                else:
                    self.lbl_cloud_account.setText("当前应用: 未绑定")
                    self.lbl_cloud_account.setStyleSheet("color: #888; font-size: 11px; padding: 0 5px;")
            else:
                self.lbl_cloud_account.setText("当前应用: 未绑定")
                self.lbl_cloud_account.setStyleSheet("color: #888; font-size: 11px; padding: 0 5px;")
        except Exception as e:
            print(f"更新云账号标签失败: {e}")

    def show_api_config_dialog(self):
        """打开API配置窗口"""
        dialog = ApiConfigDialog(self.db, self)
        dialog.show()
    
    def show_knowledge_base_disabled(self):
        """知识库功能（暂时禁用）"""
        QMessageBox.information(self, "提示",
            "知识库功能正在完善中，暂时禁用。\n\n"
            "请等待后续版本更新。")
    
    def show_daily_task_dialog(self):
        """打开每日任务大盘窗口"""
        if self.daily_task_dialog:
            self.daily_task_dialog.show()
            self.daily_task_dialog.raise_()
            self.daily_task_dialog.activateWindow()
            return
        self.daily_task_dialog = DailyTaskDialog(self.db, self)
        self.daily_task_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self.daily_task_dialog.destroyed.connect(lambda _obj=None: setattr(self, "daily_task_dialog", None))
        self.daily_task_dialog.show()
    
    def update_resource_usage(self):
        """更新当前程序的资源使用情况"""
        try:
            cpu_percent = 0
            memory_info = "N/A"
            gpu_info = "N/A"
            
            try:
                # 获取当前进程
                current_process = psutil.Process()
                
                # 获取当前进程的 CPU 使用率（interval 需要配合首次调用）
                cpu_percent = current_process.cpu_percent(interval=0.1)
                
                # 获取当前进程的内存使用（单位 MB）
                memory_info_mb = current_process.memory_info().rss / 1024 / 1024
                memory_info = f"{memory_info_mb:.1f}MB"
                
            except Exception as e:
                memory_info = f"错误: {str(e)[:20]}"
            
            try:
                result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
                                      capture_output=True, text=True, timeout=2, creationflags=CREATE_NO_WINDOW)
                if result.returncode == 0:
                    gpu_data = result.stdout.strip().split(',')
                    if len(gpu_data) >= 3:
                        gpu_util = gpu_data[0].strip()
                        gpu_mem_used = int(float(gpu_data[1].strip()))
                        gpu_mem_total = int(float(gpu_data[2].strip()))
                        gpu_info = f"GPU:{gpu_util}% 显存:{gpu_mem_used}/{gpu_mem_total}MB"
            except:
                gpu_info = "无GPU"
            
            self.resource_label.setText(f"📊 本进程 CPU:{cpu_percent}% | 内存:{memory_info} | {gpu_info}")
            
        except Exception as e:
            self.resource_label.setText("📊 资源: 获取失败")

if __name__ == "__main__":
    # 启用高分屏支持
    from PyQt5.QtCore import Qt
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except:
        pass
    
    app = QApplication(sys.argv)
    single_instance_mutex, already_running = acquire_single_instance_mutex()
    if already_running:
        if not notify_existing_instance():
            activate_existing_window_by_title()
        sys.exit(0)

    window_holder = {}
    single_instance_server, should_exit = setup_single_instance(window_holder)
    if should_exit:
        sys.exit(0)

    font = QFont("微软雅黑", 10)
    app.setFont(font)
    
    style = """
    QPushButton {
        background-color: #f0f0f0;
        color: #333;
        border: 1px solid #ccc;
        padding: 8px 16px;
        border-radius: 6px;
        font-size: 13px;
    }
    QPushButton:hover {
        background-color: #e0e0e0;
    }
    QPushButton:pressed {
        background-color: #d0d0d0;
    }
    QPushButton:disabled {
        background-color: #f5f5f5;
        color: #999;
    }
    QLineEdit, QTextEdit, QSpinBox, QComboBox {
        border: 1px solid #dcdcdc;
        border-radius: 5px;
        padding: 6px 10px;
        background-color: white;
        font-size: 13px;
    }
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {
        border: 1px solid #3498db;
    }
    QComboBox::drop-down {
        border: none;
        width: 25px;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #7f8c8d;
        margin-right: 8px;
    }
    QTableWidget {
        gridline-color: #000000;
        border: 2px solid #000000;
    }
    QTableWidget::item {
        padding: 5px;
    }
    QTableWidget::item:selected {
        background-color: #ffe0b2;
        color: black;
    }
    QHeaderView::section {
        background-color: #f8f9fa;
        color: #333;
        padding: 8px;
        border: none;
        border-bottom: 2px solid #3498db;
        font-weight: bold;
    }
    QScrollBar:vertical {
        border: none;
        background-color: #f0f0f0;
        width: 10px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background-color: #c0c0c0;
        border-radius: 5px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #a0a0a0;
    }
    QScrollBar:horizontal {
        border: none;
        background-color: #f0f0f0;
        height: 10px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background-color: #c0c0c0;
        border-radius: 5px;
        min-width: 20px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #a0a0a0;
    }
    QDialog {
        background-color: #fafafa;
    }
    QGroupBox {
        border: 1px solid #dcdcdc;
        border-radius: 8px;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
    QMenu {
        background-color: white;
        border: 1px solid #dcdcdc;
        border-radius: 5px;
    }
    QMenu::item:selected {
        background-color: #3498db;
        color: white;
        border-radius: 3px;
    }
    QCheckBox, QRadioButton {
        spacing: 8px;
    }
    QCheckBox::indicator, QRadioButton::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
    }
    QCheckBox::indicator {
        border: 2px solid #dcdcdc;
        border-radius: 4px;
    }
    QRadioButton::indicator {
        border: 2px solid #dcdcdc;
        border-radius: 9px;
    }
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {
        background-color: #3498db;
        border-color: #3498db;
    }
    QProgressBar {
        border: none;
        border-radius: 5px;
        background-color: #e0e0e0;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #3498db;
        border-radius: 5px;
    }
    """
    app.setStyleSheet(style)
    
    window = ShopManagerApp()
    window_holder["window"] = window
    window.show()
    sys.exit(app.exec_())

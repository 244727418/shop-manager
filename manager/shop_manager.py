# ================= 版本信息 =================
VERSION = "2.8.1"

# ================= 系统标准库 =================
import sys
import os
import json
import calendar
import traceback
import re
import requests
import subprocess
from datetime import datetime

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
    QGraphicsDropShadowEffect, QSizePolicy
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
        DailyTaskDialog, ProductSpecDialog,
    )
except ImportError:
    from dialogs import (
        OperationRecordDialog, DailyRecordDialog, StoreMarginDialog, CostImportDialog,
        CostLibraryDialog, ApiConfigDialog,
        ProfitAnalysisDialog, ProfitCalculatorDialog, ProfitHistoryDialog,
        DailyTaskDialog, ProductSpecDialog,
    )

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



class ShopManagerApp(QMainWindow):
    
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

        self.is_loading = False  # 防止重复加载

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

    def quit_application(self):
        """退出应用"""
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

    def init_ui(self):
        self.setWindowTitle(f"电商店铺操作记录管理工具 v{VERSION}")
        self.resize(1350, 850)

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
        btn_prev.clicked.connect(self.prev_month)
        self.lbl_month = QLabel(f"{self.year}年 {self.month}月")
        self.lbl_month.setFont(QFont("Arial", 14, QFont.Bold))
        btn_next = QPushButton("下个月 ▶")
        btn_next.clicked.connect(self.next_month)
        
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品ID或标题...")
        self.search_input.returnPressed.connect(self.perform_search)
        btn_search = QPushButton("🔍搜索")
        btn_search.clicked.connect(self.perform_search)
        
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
        self.tag_filter_menu.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)
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
        
        filter_layout.addWidget(QLabel("<hr>"))
        
        profit_label = QLabel("利润标签")
        profit_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #2c3e50;")
        filter_layout.addWidget(profit_label)
        
        self.btn_filter_profit = self._create_filter_button("赚钱 (≥5%)", None, "#27ae60")
        self.btn_filter_profit.setCheckable(True)
        
        self.btn_filter_loss = self._create_filter_button("亏钱 (<5%)", None, "#e74c3c")
        self.btn_filter_loss.setCheckable(True)
        
        self.btn_filter_break_even = self._create_filter_button("保本 (-5%~5%)", None, "#f39c12")
        self.btn_filter_break_even.setCheckable(True)
        
        filter_layout.addWidget(self.btn_filter_coupon)
        filter_layout.addWidget(self.btn_filter_new_customer)
        filter_layout.addWidget(self.btn_filter_limited_time)
        filter_layout.addWidget(self.btn_filter_marketing)
        filter_layout.addWidget(self.btn_filter_profit)
        filter_layout.addWidget(self.btn_filter_loss)
        filter_layout.addWidget(self.btn_filter_break_even)
        
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
        btn_clear_filter.clicked.connect(self.clear_tag_filter_selection)
        
        btn_layout.addWidget(btn_save_filter)
        btn_layout.addWidget(btn_clear_filter)
        filter_layout.addLayout(btn_layout)
        
        self.current_filter_tags = set()
        
        # 筛选按钮连接实时筛选（不关闭窗口）
        self.btn_filter_coupon.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_new_customer.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_limited_time.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_marketing.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_profit.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_loss.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        self.btn_filter_break_even.toggled.connect(lambda: self.apply_tag_filter(close_menu=False))
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_search)
        search_layout.addWidget(self.btn_tag_filter)
        search_layout.addWidget(self.btn_store_filter)
        toolbar.addLayout(search_layout)
        
        icons_dir = os.path.join(os.path.dirname(__file__), "icons")
        
        btn_add_store = QPushButton()
        btn_add_store.setIcon(QIcon(os.path.join(icons_dir, "add_link.svg")))
        btn_add_store.setIconSize(QSize(24, 24))
        btn_add_store.setToolTip("添加链接")
        btn_add_store.setFixedSize(32, 32)
        btn_add_store.clicked.connect(self.add_store)
        toolbar.addWidget(btn_add_store)
        
        btn_daily_task = QPushButton("📋 每日任务")
        btn_daily_task.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
        btn_daily_task.clicked.connect(self.show_daily_task_dialog)
        toolbar.addWidget(btn_daily_task)

        btn_export = QPushButton("📊导出Excel")
        btn_export.clicked.connect(self.export_to_excel)
        toolbar.addWidget(btn_export)

        toolbar.addWidget(btn_prev)
        toolbar.addWidget(self.lbl_month)
        toolbar.addWidget(btn_next)
        toolbar.addStretch()

        # 状态栏左下角按钮区域
        bottom_left_widget = QWidget()
        bottom_left_layout = QHBoxLayout(bottom_left_widget)
        bottom_left_layout.setContentsMargins(5, 0, 0, 0)
        bottom_left_layout.setSpacing(5)

        self.btn_api_config = QPushButton("🔑 API配置")
        self.btn_api_config.setFixedSize(80, 24)
        self.btn_api_config.setStyleSheet("""
            background-color: #e67e22;
            color: white;
            font-weight: bold;
            border-radius: 4px;
            font-size: 12px;
            padding: 1px;
        """)
        self.btn_api_config.clicked.connect(self.show_api_config_dialog)
        bottom_left_layout.addWidget(self.btn_api_config)

        self.btn_import_cost = QPushButton("📥 导入成本表")
        self.btn_import_cost.setFixedSize(100, 24)
        self.btn_import_cost.setStyleSheet("""
            background-color: #17a2b8;
            color: white;
            font-weight: bold;
            border-radius: 4px;
            font-size: 12px;
            padding: 1px;
        """)
        self.btn_import_cost.clicked.connect(self.import_cost_data)
        bottom_left_layout.addWidget(self.btn_import_cost)

        self.btn_view_cost = QPushButton("📦 查看成本库")
        self.btn_view_cost.setFixedSize(100, 24)
        self.btn_view_cost.setStyleSheet("""
            background-color: #6c757d;
            color: white;
            font-weight: bold;
            border-radius: 4px;
            font-size: 12px;
            padding: 1px;
        """)
        self.btn_view_cost.clicked.connect(self.show_cost_library)
        bottom_left_layout.addWidget(self.btn_view_cost)

        self.statusBar().addWidget(bottom_left_widget)

        # 状态栏右下角按钮区域
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 5, 0)

        self.lbl_cloud_account = QLabel("未登录")
        self.lbl_cloud_account.setStyleSheet("color: #888; font-size: 12px; padding: 0 5px;")
        self.lbl_cloud_account.setAlignment(Qt.AlignVCenter)
        status_layout.addWidget(self.lbl_cloud_account)

        self.btn_pinduoduo = QPushButton("🛒 拼多多")
        self.btn_pinduoduo.setFixedSize(80, 24)
        self.btn_pinduoduo.setStyleSheet("""
            background-color: #dc3545;
            color: #ffffff;
            font-weight: bold;
            border-radius: 4px;
            font-size: 12px;
            padding: 1px;
        """)
        self.btn_pinduoduo.clicked.connect(self.open_pinduoduo)
        self.btn_pinduoduo.setToolTip("打开拼多多商家后台")
        status_layout.addWidget(self.btn_pinduoduo)

        self.btn_cloud_login = QPushButton("☁️ 云同步")
        self.btn_cloud_login.setFixedSize(80, 24)
        self.btn_cloud_login.setStyleSheet("""
            background-color: #009688;
            color: #ffffff;
            font-weight: bold;
            border-radius: 4px;
            font-size: 12px;
            padding: 1px;
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
                    step = delta_y / speed_factor
                    self._accumulated_v = getattr(self, '_accumulated_v', 0) + step
                    if abs(self._accumulated_v) >= 0.5:
                        scroll_step = int(round(self._accumulated_v))
                        self._accumulated_v -= scroll_step
                        new_value = v_scroll.value() - scroll_step
                        v_scroll.setValue(max(v_scroll.minimum(), min(v_scroll.maximum(), new_value)))
                return True

            if obj == self.table.viewport():
                if delta_y != 0:
                    step = delta_y / speed_factor
                    self._accumulated_v = getattr(self, '_accumulated_v', 0) + step
                    if abs(self._accumulated_v) >= 0.5:
                        scroll_step = int(round(self._accumulated_v))
                        self._accumulated_v -= scroll_step
                        new_value_y = v_scroll.value() - scroll_step
                        v_scroll.setValue(max(v_scroll.minimum(), min(v_scroll.maximum(), new_value_y)))

                if h_scroll and delta_x != 0:
                    h_step = delta_x / speed_factor
                    self._accumulated_h = getattr(self, '_accumulated_h', 0) + h_step
                    if abs(self._accumulated_h) >= 0.5:
                        h_scroll_step = int(round(self._accumulated_h))
                        self._accumulated_h -= h_scroll_step
                        new_value_x = h_scroll.value() - h_scroll_step
                        h_scroll.setValue(max(h_scroll.minimum(), min(h_scroll.maximum(), new_value_x)))

                return True

        return super().eventFilter(obj, event)

    def show_toast(self, message):
        """显示悬浮提示"""
        self.toast_label.setText(message)
        self.toast_label.adjustSize() # 根据文字调整大小
        
        # 计算位置：让提示居中显示
        x = (self.width() - self.toast_label.width()) // 2
        y = self.height() - 100 # 距离底部 100 像素，或者改成 self.height()//2 居中
        
        self.toast_label.move(x, y)
        self.toast_label.show()
        
        # 3000 毫秒 (3秒) 后自动隐藏
        self.toast_timer.start(3000)

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
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.cellDoubleClicked.connect(self.open_editor)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows) # 整行选中
        self.table.verticalHeader().setDefaultSectionSize(100)
        
        # --- 冻结表设置 ---
        self.frozen_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.frozen_table.verticalHeader().hide()
        self.frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen_table.setWordWrap(True)
        
        # 【关键】确保冻结表也能整行选中和获取焦点
        self.frozen_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.frozen_table.setFocusPolicy(Qt.StrongFocus)
        self.frozen_table.verticalHeader().setDefaultSectionSize(100)
        
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
        
        # 3. 行高同步
        self.table.verticalHeader().sectionResized.connect(self.sync_row_height)
        
        # 3. 列宽同步 (第0列)
        self.table.horizontalHeader().sectionResized.connect(self.sync_col_width)
        
        # 4. 保存列宽设置到数据库
        self.frozen_table.horizontalHeader().sectionResized.connect(
            lambda logicalIndex, oldSize, newSize: self.db.set_setting("col_0_width", newSize)
        )
            # 主表样式
        self.table.setStyleSheet("""
            /* 选中行的样式 */
            QTableWidget::item:selected {
                background-color: #e6f3ff;    /* 选中行背景色 - 蓝色 */
                color: black;                   /* 选中行文字颜色 - 白色 */
                border: none;
                padding: 0px;
            }

            /* 当窗口失去焦点时的选中行样式 */
            QTableWidget::item:selected:!active {
                background-color: #d4edda;    /* 失焦时的背景色 - 灰色 */
                color: black;
                padding: 0px;
            }

            /* 鼠标悬停时的行样式 */
            QTableWidget::item:hover {
                background-color: #d4edda;    /* 悬停时的背景色 - 浅蓝色 */
                padding: 0px;
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
                border-right: 2px solid #555;
                background-color: white;
                color: #333333;
                font-weight: bold;
            }

            QTableWidget::item {
                color: #333333;
                font-weight: bold;
                padding: 0px;
                border: none;
            }

            /* 选中行的样式 */
            QTableWidget::item:selected {
                background-color: #e6f3ff;    /* 选中行背景色 - 蓝色 */
                color: #333333;
                padding: 0px;
            }

            /* 失焦时的选中行样式 */
            QTableWidget::item:selected:!active {
                background-color: #d4edda;
                color: #333333;
                padding: 0px;
            }

            /* 悬停行样式 */
            QTableWidget::item:hover {
                background-color: #e6f3ff;
                color: #333333;
                padding: 0px;
            }
        """)
    def _sync_frozen_from_main(self):
        """主表 -> 冻结表"""
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            self.frozen_table.clearSelection()
            self.frozen_table.viewport().update()
            return
        row = indexes[0].row()
        if 0 <= row < self.frozen_table.rowCount():
            self.frozen_table.blockSignals(True)
            self.frozen_table.selectRow(row)
            self.frozen_table.viewport().update()
            self.frozen_table.update()
            self.frozen_table.blockSignals(False)

    def _sync_main_from_frozen(self):
        """冻结表 -> 主表"""
        indexes = self.frozen_table.selectionModel().selectedRows()
        if not indexes:
            self.table.clearSelection()
            self.table.viewport().update()
            return
        row = indexes[0].row()
        if 0 <= row < self.table.rowCount():
            self.table.blockSignals(True)
            self.table.selectRow(row)
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
            return
        row = indexes[0].row()
        if 0 <= row < self.frozen_table.rowCount():
            self.frozen_table.blockSignals(True)
            self.frozen_table.selectRow(row)
            self.frozen_table.viewport().update()
            self.frozen_table.update()
            self.frozen_table.blockSignals(False)

    def sync_main_selection(self, selected, deselected):
        """冻结表选中变化时，同步主表选中状态"""
        indexes = selected.indexes()
        if not indexes:
            self.table.clearSelection()
            return
        row = indexes[0].row()
        if 0 <= row < self.table.rowCount():
            self.table.blockSignals(True)
            self.table.selectRow(row)
            self.table.viewport().update()
            self.table.update()
            self.table.blockSignals(False)

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
                    widget.update_roi_display()
                    widget.update_promo_badges()
        except Exception as e:
            print(f"强制刷新frozen_table失败: {e}")

    def force_refresh_product_widget(self, product_id):
        """根据 product_id 强制刷新对应的 ProductWidget"""
        try:
            for row, prod_id in self.row_data_map.items():
                if prod_id == product_id:
                    widget = self.frozen_table.cellWidget(row, 0)
                    if widget and isinstance(widget, ProductWidget):
                        widget.update_margin_display()
                        widget.update_roi_display()
                        widget.update_promo_badges()
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
        dialog.show()

    def open_profit_calculator_dialog(self, margin_rate, avg_price, store_id, store_name, scope, parent, db):
        """打开利润计算器对话框（供 StoreMarginDialog 等调用）"""
        dialog = ProfitCalculatorDialog(margin_rate, avg_price, store_id, store_name, scope, parent, db)
        dialog.show()

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
            
            headers = ["商品信息"] + [f"{i}号" for i in range(1, days_in_month + 1)]
            self.table.setHorizontalHeaderLabels(headers)
            self.frozen_table.setHorizontalHeaderLabels(["商品信息"])
            
            # 恢复表头样式
            self.table.horizontalHeader().setStyleSheet("QHeaderView::section { background-color: #f0f0f0; }")
            
            col0_width = int(self.db.get_setting("col_0_width", 400))  # 调整宽度以容纳按钮
            self.table.setColumnWidth(0, col0_width)
            self.frozen_table.setColumnWidth(0, col0_width)
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
                
                self.table.setRowHeight(row_idx, 120)  # 调整高度以适应内容
                self.frozen_table.setRowHeight(row_idx, 120)
                row_idx += 1
                
                products = self.db.safe_fetchall("SELECT id, name, title, image_data FROM products WHERE store_id=? ORDER BY sort_order", (store_id,))
                for prod in products:
                    p_id, p_code, p_title, p_img = prod  # 注意这里：p_code是商品ID，p_title是商品标题
                    self.table.insertRow(row_idx)
                    self.frozen_table.insertRow(row_idx)
                    
                    p_widget = ProductWidget(p_id, p_code, p_title, p_img, self)
                    self.frozen_table.setCellWidget(row_idx, 0, p_widget)
                    self.row_data_map[row_idx] = p_id
                    self.product_store_map[p_id] = store_id
                    
                    self.table.setRowHeight(row_idx, 100)
                    self.frozen_table.setRowHeight(row_idx, 100)
                    
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
            min_row_height = 120
            pixel_per_line = 24
            
            max_needed_height = min_row_height

            for day in range(1, days + 1):
                cell_data = rec_dict.get(day, [])
                
                # 构建显示文本
                if cell_data:
                    display_text = "\n".join([f"[{item.get('time', '')}] {item.get('text', '')}" for item in cell_data])
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
                
                # 确保文字靠上对齐，方便多行显示
                item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
                
                # 设置今日高亮
                if self.year == datetime.now().year and self.month == datetime.now().month and day == datetime.now().day:
                    item.setBackground(QColor("#fff3e0"))
                else:
                    item.setBackground(QColor("white")) 

                # 【关键修复 3】更保守的行高计算
                if display_text:
                    explicit_lines = display_text.count('\n') + 1
                    
                    # 多条记录时额外加缓冲
                    safety_buffer = 0
                    if len(cell_data) > 1:
                        safety_buffer = 15 # 增加缓冲到 15
                    
                    needed_height = (explicit_lines * pixel_per_line) + 15 + safety_buffer
                    
                    if needed_height > max_needed_height:
                        max_needed_height = needed_height
            
            # 统一设置行高
            final_height = max(max_needed_height, min_row_height)
            
            self.table.setRowHeight(row, final_height)
            self.frozen_table.setRowHeight(row, final_height)

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
                    display_text = "\n".join([f"[{item.get('time', '')}] {item.get('text', '')}" for item in cell_data])
                else:
                    display_text = ""
                
                item = self.table.item(row, day)
                if not item:
                    item = QTableWidgetItem()
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row, day, item)
                
                item.setText(display_text)
                item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
                
                # 与链接操作记录保持一致的背景色设置
                if self.year == datetime.now().year and self.month == datetime.now().month and day == datetime.now().day:
                    item.setBackground(QColor("#fff3e0"))
                else:
                    item.setBackground(QColor("white"))
        
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
                if new_data:
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

    def add_product(self, store_id, copy_from_id=None):
        """添加商品 - 支持手动输入商品ID和标题，copy_from_id用于复制同款"""
        try:
            # 如果是复制模式，获取原商品信息
            copy_data = {}
            if copy_from_id:
                rows = self.db.safe_fetchall(
                    "SELECT name, title, coupon_amount, new_customer_discount, image_path FROM products WHERE id=?",
                    (copy_from_id,)
                )
                if rows and rows[0]:
                    copy_data = {
                        'name': rows[0][0],
                        'title': rows[0][1],
                        'coupon_amount': rows[0][2],
                        'new_customer_discount': rows[0][3],
                        'image_path': rows[0][4]
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
                "INSERT INTO products (store_id, name, title, coupon_amount, new_customer_discount, image_path, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                (store_id, product_id, product_title, 
                 float(coupon_amount) if coupon_amount else None,
                 float(new_customer_discount) if new_customer_discount else None,
                 copy_data.get('image_path') if copy_from_id else None,
                 max_order + 1)
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
            self.load_data_safe()
            
        except Exception as e:
            print(f"添加商品失败: {e}")
            QMessageBox.warning(self, "错误", f"添加商品失败: {e}")
            
    def perform_search(self):
        search_term = self.search_input.text().strip()
        if not search_term:
            QMessageBox.warning(self, "提示", "请输入要搜索的关键字")
            return
        
        # 保存当前列位置
        current_col = self.table.currentColumn() if self.table.currentColumn() >= 0 else 0
        
        # 同时搜索ID和标题
        results = self.db.safe_fetchall(
            "SELECT id FROM products WHERE name LIKE ? OR title LIKE ?", 
            (f"%{search_term}%", f"%{search_term}%")
        )
        
        if not results:
            QMessageBox.information(self, "提示", f"未找到包含 '{search_term}' 的商品")
            return
        
        # 定位到第一个匹配的商品
        for row in range(self.table.rowCount()):
            if row in self.row_data_map and self.row_data_map[row] == results[0][0]:
                self.table.setCurrentCell(row, current_col)
                self.table.scrollTo(self.table.model().index(row, current_col), QAbstractItemView.PositionAtCenter)
                self.table.selectRow(row)
                self.show_toast(f"已定位到: {search_term}")
                return
        
        QMessageBox.information(self, "提示", f"未找到包含 '{search_term}' 的商品")
    
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
    
    def show_tag_filter_menu(self):
        """显示标签筛选下拉菜单"""
        btn_rect = self.btn_tag_filter.rect()
        global_pos = self.btn_tag_filter.mapToGlobal(QPoint(0, btn_rect.bottom()))
        self.tag_filter_menu.move(global_pos)
        self.tag_filter_menu.exec_()

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
        for store_id, store_name in stores:
            cb = QCheckBox(store_name)
            cb.setCheckable(True)
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

        self.current_store_filter = set()
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
                
                if net_margin_rate > 5:
                    return 1
                elif net_margin_rate < 5:
                    return -1
                else:
                    return 0
            
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
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate FROM products WHERE id=?",
                (product_id,)
            )
            max_discount = 0
            current_roi = 0
            return_rate = 0
            
            if product_rows:
                coupon = product_rows[0][0] if product_rows[0][0] else 0
                new_customer = product_rows[0][1] if product_rows[0][1] else 0
                max_discount = max(coupon, new_customer)
                current_roi = product_rows[0][2] if product_rows[0][2] else 0
                return_rate = product_rows[0][3] if product_rows[0][3] else 0
            
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
                
                final_net_margin_pct = -100
                if current_roi > 0 and return_rate >= 0:
                    margin_rate_decimal = final_margin_pct / 100
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006 - (1 / current_roi)) * 100
                
                if final_net_margin_pct >= 5:
                    return 'profit'
                elif final_net_margin_pct >= -5:
                    return 'break_even'
                else:
                    return 'loss'
            
            return 'loss'
        except Exception as e:
            print(f"计算利润分类失败: {e}")
            return 'loss'
    
    def apply_tag_filter(self, close_menu=False):
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
            
            if not filters and not profit_filters:
                self.clear_tag_filter()
                self.btn_tag_filter.setText("🏷️ 筛选")
                for row in range(self.table.rowCount()):
                    self.table.setRowHidden(row, False)
                    self.frozen_table.setRowHidden(row, False)
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
                
                if profit_filters and should_include:
                    profit_category = self._calculate_profit_category(pid)
                    if profit_category not in profit_filters:
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
            
            self.btn_tag_filter.setText(f"🏷️ 筛选 ({filtered_count})")
            self.show_toast(f"标签筛选: 显示 {filtered_count} 个商品")
            
        except Exception as e:
            print(f"应用标签筛选失败: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "筛选失败", f"标签筛选出错: {e}")
    
    def clear_tag_filter_selection(self):
        """清空标签筛选选择"""
        self.btn_filter_coupon.setChecked(False)
        self.btn_filter_new_customer.setChecked(False)
        self.btn_filter_limited_time.setChecked(False)
        self.btn_filter_marketing.setChecked(False)
        self.btn_filter_profit.setChecked(False)
        self.btn_filter_loss.setChecked(False)
        self.btn_filter_break_even.setChecked(False)
    
    def clear_tag_filter(self):
        """清除标签筛选，显示所有商品"""
        self.clear_tag_filter_selection()
        self.btn_tag_filter.setText("🏷️ 筛选")
        
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
            self.frozen_table.setRowHidden(row, False)
        
        self.show_toast("已清除标签筛选")
        self.current_filter_tags = set()
        
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

        # 3. 检查文件占用
        try:
            with open(file_path, 'r+b'):
                pass
        except PermissionError:
            QMessageBox.critical(self, "文件被占用", "无法读取文件！\n请**关闭**该 Excel 文件（不要在 WPS/Excel 中打开），然后再试。")
            return
        except Exception:
            pass

        # 4. 弹出配置对话框 (选择列)
        try:
            dialog = CostImportDialog(file_path, self)
            if dialog.exec_() != QDialog.Accepted:
                return
            
            spec_col_idx, price_col_idx = dialog.get_mapping()
            
            if spec_col_idx is None or price_col_idx is None:
                QMessageBox.warning(self, "提示", "请先选择【规格编码】和【成本价】所在的列！")
                return
                
        except Exception as e:
            QMessageBox.critical(self, "配置错误", f"打开配置窗口失败:\n{str(e)}")
            return

        # 5. 开始全量读取和处理
        try:
            self.statusBar().showMessage("正在读取并处理数据...", 0)
            QApplication.processEvents()

            # --- 关键修改：读取整个文件，不限制行数 ---
            if file_path.endswith('.csv'):
                # CSV 文件尝试多种编码
                try:
                    df = pd.read_csv(file_path, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    df = pd.read_csv(file_path, encoding='gbk')
            else:
                # Excel 文件：读取所有行，指定第一行为表头
                df = pd.read_excel(file_path, engine='openpyxl')

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
            
            count_success = 0
            count_skip = 0
            count_error = 0
            
            # 批量插入准备 (为了提高速度，可以每100条提交一次，这里为了简单逐条处理但加了事务优化)
            # 实际上 safe_execute 已经是逐条提交，对于几万行数据可能会慢，但最稳定
            
            self.db.conn.execute("BEGIN TRANSACTION") # 开启事务，极大提高写入速度

            for idx in range(total_rows):
                try:
                    # 获取规格
                    spec_val = col_spec.iloc[idx]
                    if not spec_val or spec_val.strip() == "" or spec_val.lower() == "nan":
                        count_skip += 1
                        continue
                    spec_code = spec_val.strip()
                    
                    # 获取价格
                    price_val = col_price.iloc[idx]
                    try:
                        # 清洗价格：去除货币符号，转为浮点数
                        if pd.isna(price_val):
                            cost_price = 0.0
                        else:
                            price_str = str(price_val).replace('¥', '').replace('$', '').replace(',', '').strip()
                            cost_price = float(price_str)
                    except ValueError:
                        cost_price = 0.0 # 如果价格不是数字，记为0

                    # 执行插入/更新
                    # SQL: 如果 spec_code 已存在则更新 cost_price，不存在则插入
                    self.db.cursor.execute(
                        "INSERT OR REPLACE INTO cost_library (spec_code, cost_price) VALUES (?, ?)",
                        (spec_code, cost_price)
                    )
                    
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
            self.statusBar().showMessage("导入完成！", 3000)

            # 6. 显示结果
            msg = (f"✅ **导入完成！**\n\n"
                   f"📊 文件总行数：{total_rows}\n"
                   f"✅ 成功入库：{count_success} 条\n"
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
            dialog = CloudSyncDialog(self.db, self)
            dialog.exec_()
            self.update_cloud_account_label()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"打开云同步窗口失败：\n{str(e)}")
            import traceback
            traceback.print_exc()

    def update_cloud_account_label(self):
        """更新云账号显示标签"""
        try:
            if hasattr(self, 'cloud_manager') and self.cloud_manager:
                current = self.cloud_manager.get_current_account()
                if current:
                    self.lbl_cloud_account.setText(f"☁️ {current.get('name', '未知')}")
                    self.lbl_cloud_account.setStyleSheet("color: #27ae60; font-size: 11px; padding: 0 5px;")
                else:
                    self.lbl_cloud_account.setText("未登录")
                    self.lbl_cloud_account.setStyleSheet("color: #888; font-size: 11px; padding: 0 5px;")
            else:
                self.lbl_cloud_account.setText("未登录")
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
        dialog = DailyTaskDialog(self.db, self)
        dialog.show()
    
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
        gridline-color: #e0e0e0;
        border: 1px solid #dcdcdc;
    }
    QTableWidget::item {
        padding: 5px;
    }
    QTableWidget::item:selected {
        background-color: #3498db;
        color: white;
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
    window.show()
    sys.exit(app.exec_())

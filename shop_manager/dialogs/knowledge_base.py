# -*- coding: utf-8 -*-
"""本地知识库管理对话框"""
import os
import sys
import re
import time
import psutil  # 系统资源监控
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QWidget,
    QListWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QLineEdit, QTextEdit, QMessageBox, QProgressBar, QApplication, QStyle,
    QItemDelegate, QSlider, QCheckBox, QStyleOptionViewItem
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QColor, QFont, QPainter, QPalette


class NoSelectionRectDelegate(QItemDelegate):
    def drawFocus(self, painter, option, rect):
        pass


def _project_root():
    """从 dialogs 所在包得到项目根目录（与 shop_manager 同级）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class KnowledgeBaseDialog(QDialog):
    # 信号用于从文件监控线程安全地调用主线程
    file_changed_signal = pyqtSignal()
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("📚 本地知识库管理")
        self.resize(1600, 850)
        self.kb_folder = os.path.join(_project_root(), "knowledge_base")
        self.file_watcher = None
        self.last_known_files = {}
        self._sync_enabled = True
        self._sync_pending = False
        self._search_pending = False
        self._search_timer = None
        self._is_search_mode = False
        self._search_results = []
        self._is_editing = False
        self._other_items = []
        self._is_other_expanded = False
        
        # 先显示窗口，然后延迟初始化UI
        self.show()
        QTimer.singleShot(100, self._delayed_init)

    def _delayed_init(self):
        """延迟初始化UI"""
        # 初始化搜索定时器
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._on_search_timer_timeout)

        # 加载持久化的文件缓存
        self._cache_file = os.path.join(_project_root(), ".kb_file_cache.json")
        self._load_file_cache()

        # 检查并创建知识库文件夹
        if not os.path.exists(self.kb_folder):
            os.makedirs(self.kb_folder)
        local_txt_files = [f for f in os.listdir(self.kb_folder) if f.endswith('.txt')]
        if not local_txt_files:
            self.db.safe_execute("DELETE FROM knowledge_base WHERE is_system=0")

        self.init_ui()
        # 已移除实时文件监控功能，使用手动同步按钮

        # 延迟加载数据，让界面先显示（约1秒后开始加载）
        QTimer.singleShot(1000, self._delayed_load)

        # 更新stence开关状态显示（确保与实际状态一致）
        self._update_stence_switch_status()

    def _delayed_load(self):
        """延迟加载数据，让界面先显示出来"""
        # 显示加载进度条
        self._show_progress("正在加载知识库...")
        
        # 加载数据 - 延迟执行
        QTimer.singleShot(200, self._do_delayed_load)
    
    def _do_delayed_load(self):
        """实际执行延迟加载"""
        self.load_data()
        self._hide_progress()
    
    def _on_file_changed(self):
        """文件变化信号处理，带防抖"""
        if self._sync_pending:
            return
        self._sync_pending = True
        # 延迟1000ms执行，避免频繁触发
        QTimer.singleShot(1000, self._do_sync)
    
    def _do_sync(self):
        """实际执行同步"""
        self._sync_pending = False
        self.sync_local_files()

    _watchdog_warning_shown = False

    def setup_file_watcher(self):
        if KnowledgeBaseDialog._watchdog_warning_shown:
            if self.file_watcher is None and hasattr(self, 'sync_timer'):
                return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class KnowledgeBaseFileHandler(FileSystemEventHandler):
                def __init__(self, dialog):
                    super().__init__()
                    self.dialog = dialog
                def on_any_event(self, event):
                    if not self.dialog._sync_enabled:
                        return
                    if event.is_directory:
                        return
                    if not event.src_path.endswith('.txt'):
                        return
                    # 使用信号而不是直接调用，确保在主线程执行
                    self.dialog.file_changed_signal.emit()

            self.file_handler = KnowledgeBaseFileHandler(self)
            self.file_watcher = Observer()
            self.file_watcher.schedule(self.file_handler, self.kb_folder, recursive=False)
            self.file_watcher.start()
            print(f"✅ 文件监控已启动: {self.kb_folder}")
            KnowledgeBaseDialog._watchdog_warning_shown = True
        except ImportError as e:
            if not KnowledgeBaseDialog._watchdog_warning_shown:
                print(f"⚠️ watchdog 库未安装或导入失败: {e}，将使用定时检查模式")
                print("💡 解决方案: pip install watchdog")
                KnowledgeBaseDialog._watchdog_warning_shown = True
            self.file_watcher = None
            self.sync_timer = QTimer()
            self.sync_timer.timeout.connect(self.sync_local_files)
            self.sync_timer.start(3000)
        except Exception as e:
            if not KnowledgeBaseDialog._watchdog_warning_shown:
                print(f"⚠️ 文件监控启动失败: {e}，将使用定时检查模式")
                print("💡 解决方案: pip install watchdog")
                KnowledgeBaseDialog._watchdog_warning_shown = True
            self.file_watcher = None
            self.sync_timer = QTimer()
            self.sync_timer.timeout.connect(self.sync_local_files)
            self.sync_timer.start(3000)

    def sync_local_files(self):
        if not getattr(self, '_sync_enabled', True):
            return
        if not os.path.exists(self.kb_folder):
            return
        try:
            current_files = {}
            for f in os.listdir(self.kb_folder):
                if f.endswith('.txt'):
                    fpath = os.path.join(self.kb_folder, f)
                    current_files[f] = os.path.getmtime(fpath)
            # 初始化 last_known_files
            if not hasattr(self, 'last_known_files') or self.last_known_files is None:
                self.last_known_files = {}
            if self.last_known_files != current_files:
                changed = False
                for f, mtime in current_files.items():
                    if f not in self.last_known_files:
                        # 文件监控同步时跳过embedding计算，避免卡顿
                        self.db.import_knowledge_file(os.path.join(self.kb_folder, f), skip_embedding=True)
                        changed = True
                for f in list(self.last_known_files.keys()):
                    if f not in current_files:
                        self.db.delete_knowledge_by_file(os.path.join(self.kb_folder, f))
                        changed = True
                for f in current_files:
                    if f in self.last_known_files and current_files[f] != self.last_known_files[f]:
                        # 文件监控同步时跳过embedding计算，避免卡顿
                        self.db.import_knowledge_file(os.path.join(self.kb_folder, f), skip_embedding=True)
                        changed = True
                if changed:
                    self.load_data()
                self.last_known_files = current_files
        except Exception as e:
            print(f"同步本地文件失败: {e}")

    def _reenable_sync(self):
        self._sync_enabled = True

    def _on_threshold_changed(self, value):
        """相关度阈值滑块变化"""
        threshold = value / 100.0
        self.lbl_threshold.setText(f"{threshold:.2f}")
        
        if hasattr(self, 'rag_adapter') and self.rag_adapter:
            if hasattr(self.rag_adapter, 'engine') and self.rag_adapter.engine:
                if hasattr(self.rag_adapter.engine.hybrid_retriever, 'min_relevance_score'):
                    self.rag_adapter.engine.hybrid_retriever.min_relevance_score = threshold

    def _get_selected_files(self):
        """获取选中的文件列表（支持多选）"""
        selected_files = []
        selected_items = self.files_list.selectedItems()
        
        for item in selected_items:
            display_name = item.text()
            if display_name.startswith("📦 ") or display_name.startswith("📁 "):
                file_name = display_name.split(" ", 1)[1].replace(" (系统)", "")
            else:
                file_name = display_name
            selected_files.append(file_name)
        
        return selected_files
    
    def _show_progress(self, message=""):
        """显示底部进度条"""
        if hasattr(self, 'status_progress_bar'):
            self.status_progress_bar.setVisible(True)
            self.status_progress_bar.setRange(0, 0)
            self.status_progress_bar.setFormat(message if message else "加载中...")
    
    def _hide_progress(self):
        """隐藏底部进度条"""
        if hasattr(self, 'status_progress_bar'):
            self.status_progress_bar.setVisible(False)

    def closeEvent(self, event):
        # 隐藏窗口而不是关闭（保留引用以便重新打开）
        self.hide()
        event.ignore()
    
    def changeEvent(self, event):
        """窗口状态变化事件"""
        if event.type() == 24:
            if self.isMinimized():
                # 最小化到任务栏（Windows默认行为）
                pass
        super().changeEvent(event)

    def init_ui(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QToolTip
        QToolTip.setFont(self.font())
        # 设置窗口背景和多巴胺配色 - 使用对象名限定作用域，防止影响主界面
        self.setObjectName("KnowledgeBaseDialog")
        self.setStyleSheet("""
            #KnowledgeBaseDialog {
                background-color: #FFF9E6;
                font-family: Microsoft YaHei, 微软雅黑, sans-serif;
            }
            #KnowledgeBaseDialog QToolTip {
                border: 1px solid #FF6B6B;
                background-color: #FFE66D;
                color: #333;
                padding: 5px;
                font-family: Microsoft YaHei, 微软雅黑, sans-serif;
            }
            #KnowledgeBaseDialog QLabel {
                font-family: Microsoft YaHei, 微软雅黑, sans-serif;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(5)
        
        # 顶部状态栏（资源监控 + API状态）
        top_status_layout = QHBoxLayout()
        
        # API配置状态标签（右上角最小化显示）
        self.api_status_label = QLabel("🤖")
        self.api_status_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        self.api_status_label.setToolTip("AI API未配置")
        top_status_layout.addWidget(self.api_status_label)

        # RAG向量索引状态标签
        self.rag_status_label = QLabel("🟠")
        self.rag_status_label.setStyleSheet("font-size: 12px;")
        self.rag_status_label.setToolTip("RAG向量索引: 模型加载中...")
        top_status_layout.addWidget(self.rag_status_label)

        # stence模型启用开关（使用按钮样式，更明显）
        self.stence_switch_btn = QPushButton("🔌 启用")
        self.stence_switch_btn.setFixedSize(80, 22)
        self.stence_switch_btn.setStyleSheet("""
            QPushButton {
                background-color: #4ECDC4;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45B7D1;
            }
            QPushButton:pressed {
                background-color: #3CAEA3;
            }
        """)
        self.stence_switch_btn.setToolTip("点击切换stence模型启用状态")
        self.stence_switch_btn.setDefault(False)
        self.stence_switch_btn.setAutoDefault(False)
        self.stence_switch_btn.clicked.connect(self.toggle_stence_model)
        top_status_layout.addWidget(self.stence_switch_btn)

        top_status_layout.addStretch()

        # 系统资源监控显示（顶部细条）
        self.resource_label = QLabel("📊 系统资源: 初始化...")
        self.resource_label.setStyleSheet("""
            background-color: #2c3e50;
            color: #ecf0f1;
            font-size: 10px;
            padding: 1px 10px;
            border-radius: 3px;
        """)
        self.resource_label.setFixedHeight(18)
        self.resource_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top_status_layout.addWidget(self.resource_label)
        
        main_layout.addLayout(top_status_layout)

        # 初始化时检查API配置
        self._update_api_status()

        # 启动资源监控定时器
        self.resource_timer = QTimer()
        self.resource_timer.timeout.connect(self.update_resource_usage)
        self.resource_timer.start(3000)

        # 启动RAG状态监控定时器
        self.rag_status_timer = QTimer()
        self.rag_status_timer.timeout.connect(self._update_rag_status)
        self.rag_status_timer.start(2000)  # 每2秒检查一次

        # 初始化RAG搜索引擎（在后台加载模型和索引）
        
        self._init_rag_search()

        debug_label = QLabel(f"【知识库管理】模型: stence模型已启用（后台加载中...）")
        debug_label.setStyleSheet("background-color: #FFE66D; color: #333; font-size: 15px; padding: 5px; font-family: Microsoft YaHei, 微软雅黑;")
        debug_label.setFixedHeight(27)
        debug_label.setWordWrap(True)
        debug_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        main_layout.addWidget(debug_label)

        debug_label2 = QLabel("【knowledge_base.py】左侧文件列表│右侧知识点列表│双击内容编辑│知识点自动同步txt文件")
        debug_label2.setStyleSheet("background-color: #FF6B6B; color: white; font-size: 11px; padding: 5px; font-family: Microsoft YaHei, 微软雅黑;")
        debug_label2.setFixedHeight(23)
        debug_label2.setWordWrap(True)
        debug_label2.setTextInteractionFlags(Qt.TextSelectableByMouse)
        main_layout.addWidget(debug_label2)
        
        # 按钮行：导出/搜索
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        # 打开知识库文件夹按钮
        self.btn_open_folder = QPushButton("📂 打开文件夹")
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background-color: #9B59B6; color: white; padding: 8px 15px; font-size: 12px; 
                border-radius: 8px; font-weight: bold; font-family: Microsoft YaHei, 微软雅黑;
            }
            QPushButton:hover { background-color: #8E44AD; }
            QPushButton:pressed { background-color: #7D3C98; }
        """)
        self.btn_open_folder.clicked.connect(self.open_knowledge_folder)
        self.btn_open_folder.setDefault(False)
        self.btn_open_folder.setAutoDefault(False)
        self.btn_open_folder.setToolTip("打开知识库文件夹目录")
        btn_layout.addWidget(self.btn_open_folder)

        # 知识库文件数量显示
        self.lbl_file_count = QLabel("📚 共 0 个文件")
        self.lbl_file_count.setStyleSheet("color: #666; font-size: 12px; padding: 5px 10px; font-family: Microsoft YaHei, 微软雅黑;")
        btn_layout.addWidget(self.lbl_file_count)

        self.btn_export = QPushButton("📤 导出")
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #FF6B6B; color: white; padding: 8px 15px; font-size: 12px; 
                border-radius: 8px; font-weight: bold; font-family: Microsoft YaHei, 微软雅黑;
            }
            QPushButton:hover { background-color: #FF5252; }
            QPushButton:pressed { background-color: #E55555; }
        """)
        self.btn_export.clicked.connect(self.export_knowledge)
        self.btn_export.setDefault(False)
        self.btn_export.setAutoDefault(False)
        btn_layout.addWidget(self.btn_export)
        
        # 搜索框
        btn_layout.addSpacing(20)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 输入关键词搜索...")
        self.search_input.setMinimumWidth(280)
        self.search_input.setMaximumWidth(380)
        self.search_input.setStyleSheet("padding: 8px 15px; font-size: 13px; border: 2px solid #45B7D1; border-radius: 15px; background-color: #ffffff; font-family: Microsoft YaHei, 微软雅黑;")
        btn_layout.addWidget(self.search_input)

        # 主动搜索按钮
        self.btn_search = QPushButton("🔍 搜索")
        self.btn_search.setStyleSheet("""
            QPushButton {
                background-color: #45B7D1; color: white; padding: 8px 20px; font-size: 13px; 
                border-radius: 10px; font-weight: bold; font-family: Microsoft YaHei, 微软雅黑;
            }
            QPushButton:hover { background-color: #3BA3BA; }
            QPushButton:pressed { background-color: #2D8A9E; }
        """)
        self.btn_search.clicked.connect(self.on_search_button_clicked)
        self.btn_search.setDefault(False)
        self.btn_search.setAutoDefault(False)
        btn_layout.addWidget(self.btn_search)

        # 相关度阈值滑块
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(0)
        self.threshold_slider.setMaximum(50)
        self.threshold_slider.setValue(1)
        self.threshold_slider.setToolTip("调节相关度阈值")
        self.threshold_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #ddd; border-radius: 3px; }
            QSlider::handle:horizontal { width: 14px; margin: -4px 0; background: #45B7D1; border-radius: 7px; }
            QSlider::add-page:horizontal { background: #ddd; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #45B7D1; border-radius: 3px; }
        """)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        btn_layout.addWidget(QLabel("🔎"))
        btn_layout.addWidget(self.threshold_slider)
        self.lbl_threshold = QLabel("0.01")
        self.lbl_threshold.setStyleSheet("font-size: 11px; color: #666;")
        btn_layout.addWidget(self.lbl_threshold)

        # 重置搜索按钮
        self.btn_reset_search = QPushButton("🔄 重置")
        self.btn_reset_search.setStyleSheet("""
            QPushButton {
                background-color: #A8E6CF; color: white; padding: 8px 15px; font-size: 12px; 
                border-radius: 8px; font-weight: bold; font-family: Microsoft YaHei, 微软雅黑;
            }
            QPushButton:hover { background-color: #8DD3BC; }
            QPushButton:pressed { background-color: #72C0A7; }
        """)
        self.btn_reset_search.clicked.connect(self.reset_search)
        self.btn_reset_search.setDefault(False)
        self.btn_reset_search.setAutoDefault(False)
        self.btn_reset_search.setVisible(True)
        btn_layout.addWidget(self.btn_reset_search)

        # 向量搜索按钮
        self.btn_vector_search = QPushButton("📊 向量搜索")
        self.btn_vector_search.setStyleSheet("""
            QPushButton {
                background-color: #9B59B6; color: white; padding: 8px 15px; font-size: 12px;
                border-radius: 8px; font-weight: bold; font-family: Microsoft YaHei, 微软雅黑;
            }
            QPushButton:hover { background-color: #8E44AD; }
            QPushButton:pressed { background-color: #7D3C98; }
        """)
        self.btn_vector_search.clicked.connect(self.on_vector_search_clicked)
        self.btn_vector_search.setDefault(False)
        self.btn_vector_search.setAutoDefault(False)
        btn_layout.addWidget(self.btn_vector_search)

        # AI智能搜索按钮
        self.btn_ai_search = QPushButton("🤖 AI搜索")
        self.btn_ai_search.setStyleSheet("""
            QPushButton {
                background-color: #FF6B6B; color: white; padding: 8px 15px; font-size: 12px; 
                border-radius: 8px; font-weight: bold; font-family: Microsoft YaHei, 微软雅黑;
            }
            QPushButton:hover { background-color: #FF5252; }
            QPushButton:pressed { background-color: #E55555; }
        """)
        self.btn_ai_search.clicked.connect(self.on_ai_search_clicked)
        self.btn_ai_search.setDefault(False)
        self.btn_ai_search.setAutoDefault(False)
        btn_layout.addWidget(self.btn_ai_search)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)
        splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("📁 知识库文件列表"))
        self.files_list = QListWidget()
        self.files_list.setMinimumWidth(200)
        self.files_list.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 支持Ctrl/Shift多选
        self.files_list.setStyleSheet("""
            QListWidget { border: 2px solid #FFD93D; border-radius: 10px; padding: 8px; font-size: 13px; background-color: #ffffff; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #FFE66D; border-radius: 5px; margin: 2px; }
            QListWidget::item:selected { background-color: #FF6B6B; color: white; border-radius: 5px; }
            QListWidget::item:hover { background-color: #FFE66D; border-radius: 5px; }
        """)
        QTimer.singleShot(0, lambda: self.files_list.setSelectionRectVisible(False))
        self.files_list.itemClicked.connect(self.on_file_selected)
        left_layout.addWidget(self.files_list)
        files_btn_layout = QHBoxLayout()

        # 手动同步按钮
        self.btn_manual_sync = QPushButton("🔄 同步")
        self.btn_manual_sync.setStyleSheet("""
            QPushButton {
                background-color: #27AE60; color: white; padding: 8px 15px; font-size: 12px;
                border-radius: 8px; font-weight: bold; font-family: Microsoft YaHei, 微软雅黑;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #229954; }
            QPushButton:pressed { background-color: #1E8449; }
        """)
        self.btn_manual_sync.clicked.connect(self.on_manual_sync_clicked)
        self.btn_manual_sync.setToolTip("手动同步本地文件到数据库")
        files_btn_layout.addWidget(self.btn_manual_sync)

        files_btn_layout.addStretch()
        left_layout.addLayout(files_btn_layout)
        splitter.addWidget(left_widget)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("📋 知识点列表（双击标题或内容可编辑）"))
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(3)
        self.items_table.setHorizontalHeaderLabels(["匹配", "标题", "内容"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.items_table.setColumnWidth(1, 150)  # 标题列宽150
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # 内容自动拉伸
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.items_table.setWordWrap(True)
        self.items_table.verticalHeader().setDefaultSectionSize(60)  # 行高自适应
        self.items_table.cellDoubleClicked.connect(self.on_item_double_click)
        self.items_table.cellChanged.connect(self.on_cell_changed)
        self.items_table.setItemDelegate(NoSelectionRectDelegate(self.items_table))
        QTimer.singleShot(0, lambda: self.items_table.setSelectionRectVisible(False))
        self.items_table.setStyleSheet("""
            QTableWidget { border: 2px solid #bdc3c7; font-size: 13px; background-color: #f8f9fa; }
            QTableWidget::item { padding: 8px; outline: none; border: none; }
            QTableWidget::item:selected { background-color: #A8E6CF; color: #333; }
            QTableWidget::item:focus { outline: none; border: none; }
            QHeaderView::section { background-color: #FFE66D; color: #333; padding: 10px; font-weight: bold; font-size: 13px; }
            QTableCornerButton::section { background-color: #FFE66D; }
        """)
        right_layout.addWidget(self.items_table)

        # 已复制提示标签 - 初始隐藏
        self.copied_label = QLabel("已复制 ✓", self.items_table)
        self.copied_label.setWindowFlags(Qt.ToolTip)
        self.copied_label.setStyleSheet("""
            background-color: rgba(39, 174, 96, 150);
            color: white;
            padding: 6px 16px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: bold;
            border: 1px solid rgba(39, 174, 96, 100);
        """)
        self.copied_label.hide()
        self.copied_timer = QTimer()
        self.copied_timer.setSingleShot(True)

        # 悬停事件（已禁用）
        self.items_table.cellClicked.connect(self.on_cell_clicked)

        items_btn_layout = QHBoxLayout()
        self.btn_add_single = QPushButton("➕ 添加知识点")
        self.btn_add_single.setStyleSheet("background-color: #e67e22; color: white; padding: 8px 15px; font-size: 11px; border-radius: 8px; font-weight: bold;")
        self.btn_add_single.setDefault(False)
        self.btn_add_single.setAutoDefault(False)
        self.btn_add_single.clicked.connect(self.add_single_knowledge)
        items_btn_layout.addWidget(self.btn_add_single)
        items_btn_layout.addStretch()
        right_layout.addLayout(items_btn_layout)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 800])
        main_layout.addWidget(splitter)
        
        # 底部进度条（始终可见，显示搜索状态）
        self.status_progress_bar = QProgressBar()
        self.status_progress_bar.setFixedHeight(8)
        self.status_progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #f0f0f0;
                text-align: left;
            }
            QProgressBar::chunk {
                background-color: #45B7D1;
            }
        """)
        self.status_progress_bar.setVisible(False)
        main_layout.addWidget(self.status_progress_bar)

        # 底部按钮水平布局
        bottom_btn_layout = QHBoxLayout()
        bottom_btn_layout.addStretch()

        self.btn_rebuild_index = QPushButton("🔨 重建索引")
        self.btn_rebuild_index.setStyleSheet("QPushButton { background-color: #E67E22; color: white; padding: 8px 25px; font-size: 12px; border-radius: 8px; font-weight: bold; } QPushButton:hover { background-color: #D35400; }")
        self.btn_rebuild_index.clicked.connect(self.on_rebuild_index_clicked)
        self.btn_rebuild_index.setToolTip("重建向量索引")

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("QPushButton { background-color: #FF6B6B; color: white; padding: 8px 25px; font-size: 12px; border-radius: 8px; font-weight: bold; } QPushButton:hover { background-color: #FF8E8E; }")
        close_btn.clicked.connect(self.close)

        bottom_btn_layout.addWidget(self.btn_rebuild_index)
        bottom_btn_layout.addWidget(close_btn)

        main_layout.addLayout(bottom_btn_layout)

    def import_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择知识库文件", "", "文本文件 (*.txt);;所有文件 (*.*)")
        if file_path:
            success, msg = self.db.import_knowledge_file(file_path)
            if success:
                QMessageBox.information(self, "✅ 成功", msg)
                self.load_data()
            else:
                QMessageBox.warning(self, "⚠️ 导入失败", msg)

    def open_knowledge_folder(self):
        """打开知识库文件夹"""
        import subprocess
        folder_path = self.kb_folder
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        try:
            subprocess.Popen(f'explorer "{folder_path}"')
        except Exception as e:
            QMessageBox.warning(self, "⚠️ 错误", f"无法打开文件夹：{e}")

    def create_new_file(self):
        kb_folder = self.kb_folder
        if not os.path.exists(kb_folder):
            os.makedirs(kb_folder)
        dialog = QDialog(self)
        dialog.setWindowTitle("📄 新建知识库文件")
        dialog.resize(450, 180)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("请输入文件名（支持任意字符）："))
        name_input = QLineEdit()
        name_input.setPlaceholderText("如：商品知识库、My Knowledge、商品知识 2024")
        layout.addWidget(name_input)
        layout.addWidget(QLabel("💡 文件将保存到: knowledge_base/ 文件夹（.txt后缀会自动添加）"))
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("创建")
        cancel_btn = QPushButton("取消")
        def do_create():
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "⚠️ 提示", "请输入文件名！")
                return
            if name.lower().endswith('.txt'):
                name = name[:-4]
            if not name:
                QMessageBox.warning(self, "⚠️ 提示", "文件名无效！")
                return
            file_name = f"{name}.txt"
            file_path = os.path.join(kb_folder, file_name)
            for fp, fn, is_sys in self.db.get_unique_files():
                if fn == file_name:
                    QMessageBox.warning(self, "⚠️ 提示", "文件已存在，请使用其他名称！")
                    return
            if os.path.exists(file_path):
                QMessageBox.warning(self, "⚠️ 提示", "文件已存在，请使用其他名称！")
                return
            try:
                self._sync_enabled = False
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("【示例标题】这是示例内容。你可以在这里添加自己的知识条目。\n")
                self._sync_enabled = True
                QTimer.singleShot(100, self._reenable_sync)
            except Exception as e:
                self._sync_enabled = True
                QMessageBox.warning(self, "⚠️ 提示", f"创建文件失败: {e}")
                return
            success, msg = self.db.import_knowledge_file(file_path)
            if success:
                QMessageBox.information(self, "✅ 成功", "知识库文件创建成功！")
                dialog.accept()
                self.load_data()
            else:
                QMessageBox.warning(self, "⚠️ 失败", msg)
        ok_btn.clicked.connect(do_create)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        dialog.exec_()

    def add_single_knowledge(self):
        current_file_item = self.files_list.currentItem()
        if not current_file_item:
            QMessageBox.warning(self, "⚠️ 提示", "请先在左侧选择一个知识库文件！")
            return
        display_name = current_file_item.text()
        file_name = display_name.split(" ", 1)[1] if (display_name.startswith("📦 ") or display_name.startswith("📁 ")) else display_name
        is_system = "(系统)" in file_name
        if is_system:
            file_name = file_name.replace(" (系统)", "")
            QMessageBox.warning(self, "⚠️ 提示", "系统知识库文件无法添加知识点！")
            return
        
        # 直接从本地文件夹构造文件路径，而不是从数据库查询
        file_path = os.path.join(self.kb_folder, file_name)
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "⚠️ 提示", f"文件不存在: {file_path}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"➕ 添加知识点到 - {file_name}")
        dialog.resize(500, 350)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("标题："))
        title_input = QLineEdit()
        title_input.setPlaceholderText("如：SKU命名技巧")
        layout.addWidget(title_input)
        layout.addWidget(QLabel("内容："))
        content_input = QTextEdit()
        content_input.setPlaceholderText("请输入知识点内容...")
        layout.addWidget(content_input)
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        if dialog.exec_() == QDialog.Accepted:
            title = title_input.text().strip()
            content = content_input.toPlainText().strip()
            if not title:
                QMessageBox.warning(self, "⚠️ 提示", "请输入标题！")
                return
            if not content:
                QMessageBox.warning(self, "⚠️ 提示", "请输入内容！")
                return
            if title.startswith("【") and title.endswith("】"):
                title = title[1:-1]
            title_for_db = title
            title_for_file = f"【{title}】"
            try:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                text = f"{title_for_file} {content}"
                embedding = self.db.get_embedding(text) if getattr(self.db, 'rag_model', None) else None
                # 获取当前文件的最大sort_order
                existing_items = self.db.safe_fetchall(
                    "SELECT COUNT(*) FROM knowledge_base WHERE file_path=?",
                    (file_path,)
                )
                max_sort_order = existing_items[0][0] if existing_items else 0
                if embedding:
                    self.db.safe_execute(
                        "INSERT INTO knowledge_base (file_path, file_name, title, content, is_active, is_system, embedding, created_at, updated_at, sort_order) VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, ?)",
                        (file_path, os.path.basename(file_path), title_for_db, content, embedding, now, now, max_sort_order)
                    )
                else:
                    self.db.safe_execute(
                        "INSERT INTO knowledge_base (file_path, file_name, title, content, is_active, is_system, created_at, updated_at, sort_order) VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?)",
                        (file_path, os.path.basename(file_path), title_for_db, content, now, now, max_sort_order)
                    )
                try:
                    self._sync_enabled = False
                    with open(file_path, 'a', encoding='utf-8') as f:
                        # 新格式：【标题】\n内容\n
                        f.write(f"\n{title_for_file}\n{content}\n")
                    self._sync_enabled = True
                    QTimer.singleShot(100, self._reenable_sync)
                except Exception as e:
                    self._sync_enabled = True
                    print(f"写入文件失败: {e}")
                QMessageBox.information(self, "✅ 成功", "知识点添加成功！")
                # 快速刷新显示
                if hasattr(self, '_quick_refresh_display'):
                    self._quick_refresh_display()
                else:
                    self.load_data()
            except Exception as e:
                QMessageBox.warning(self, "⚠️ 失败", f"添加失败: {e}")

    def get_full_content(self, item_id):
        try:
            rows = self.db.safe_fetchall("SELECT content FROM knowledge_base WHERE id=?", (item_id,))
            if rows:
                return rows[0][0]
        except Exception:
            pass
        return ""

    def edit_knowledge_content(self, title, content):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑知识点 - {title}")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"标题: {title}"))
        text_edit = QTextEdit()
        text_edit.setText(content)
        layout.addWidget(text_edit)
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(save_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        if dialog.exec_() == QDialog.Accepted:
            return text_edit.toPlainText()
        return None

    def save_knowledge_content(self, item_id, content):
        try:
            self.db.safe_execute(
                "UPDATE knowledge_base SET content=?, updated_at=? WHERE id=?",
                (content, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_id)
            )
            QMessageBox.information(self, "✅ 成功", "知识点内容已保存！")
        except Exception as e:
            QMessageBox.warning(self, "⚠️ 失败", f"保存失败: {e}")

    def export_knowledge(self):
        # 获取选中的文件
        selected_files = self._get_selected_files()
        all_items = self.db.get_all_knowledge_items()

        # 如果有选中文件，只导出选中的
        if selected_files:
            items = [item for item in all_items if len(item) >= 3 and item[2] in selected_files]
            file_name_hint = "_".join(selected_files[:2])
            if len(selected_files) > 2:
                file_name_hint += f"_{len(selected_files)-2}个文件"
        else:
            items = all_items
            file_name_hint = "全部知识库"

        # 去重：基于标题+内容进行去重
        seen = set()
        unique_items = []
        for item in items:
            if len(item) >= 5:
                title = item[3] if len(item) > 3 else ""
                content = item[4] if len(item) > 4 else ""
                key = f"{title}|{content}"
                if key not in seen:
                    seen.add(key)
                    unique_items.append(item)
                else:
                    print(f"[DEBUG] 导出去重: 跳过重复条目 '{title[:20]}...'", flush=True)

        print(f"[DEBUG] 导出: 原始条目 {len(items)}, 去重后 {len(unique_items)}", flush=True)

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出知识库", f"knowledge_export_{file_name_hint}.txt",
            "文本文件 (*.txt);;所有文件 (*.*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for item in unique_items:
                        item_id, fp, fn, title, content, is_active, is_system = item
                        f.write(f"【{title}】\n{content}\n\n")

                export_count = len(unique_items)
                QMessageBox.information(self, "✅ 成功", f"已导出 {export_count} 条知识到:\n{file_path}")
            except Exception as e:
                QMessageBox.warning(self, "⚠️ 导出失败", f"导出失败: {e}")

    def load_data(self):
         # 清除可能存在的单元格合并（来自无结果提示）
         self.items_table.clearSpans()
         
         # 如果不在搜索模式，清除右边知识点表格
         if not self._is_search_mode:
             self.items_table.setRowCount(0)
         
         current_row = self.files_list.currentRow()
         current_file_name = None
         if current_row >= 0 and self.files_list.count() > 0:
             current_item = self.files_list.item(current_row)
             if current_item:
                 display_name = current_item.text()
                 if display_name.startswith("📦 ") or display_name.startswith("📁 "):
                     current_file_name = display_name.split(" ", 1)[1].replace(" (系统)", "")
         
         # 从本地文件夹获取文件列表，而不是从数据库
         local_files = []
         if os.path.exists(self.kb_folder):
             for f in os.listdir(self.kb_folder):
                 if f.endswith('.txt'):
                     local_files.append(f)
         
         # 获取数据库中的系统文件标记
         db_files = self.db.get_unique_files()
         db_file_system_map = {}
         for file_path, file_name, is_system in db_files:
             db_file_system_map[file_name] = is_system
         
         self.files_list.clear()
         for file_name in sorted(local_files):
             is_system = db_file_system_map.get(file_name, 0)
             self.files_list.addItem(f"📦 {file_name} (系统)" if is_system else f"📁 {file_name}")
         
         # 更新知识库文件数量显示
         file_count = len(local_files)
         self.lbl_file_count.setText(f"📚 共 {file_count} 个文件")
         
         # 从本地文件重新同步到数据库（以文件为准）
         if local_files:
             self._sync_files_to_db(local_files, db_file_system_map)
         
         # 只有在有文件且不在搜索模式下才加载知识点
         if local_files and not self._is_search_mode:
             if current_file_name:
                 target_row = -1
                 for i in range(self.files_list.count()):
                     item = self.files_list.item(i)
                     display_name = item.text()
                     fn = display_name.split(" ", 1)[1].replace(" (系统)", "") if (display_name.startswith("📦 ") or display_name.startswith("📁 ")) else display_name
                     if fn == current_file_name:
                         target_row = i
                         break
                 if target_row >= 0:
                     self.files_list.setCurrentRow(target_row)
                     self.on_file_selected(self.files_list.item(target_row))
                 else:
                     self.files_list.setCurrentRow(0)
                     self.on_file_selected(self.files_list.currentItem())
             else:
                 self.files_list.setCurrentRow(0)
                 self.on_file_selected(self.files_list.currentItem())
         elif not local_files:
             # 没有文件时，清空右边表格
             self.items_table.setRowCount(0)
    
    def _sync_files_to_db(self, local_files, db_file_system_map):
        """从本地文件同步到数据库（以文件为准）- 优化：跳过未变化的文件"""
        try:
            import re
            from datetime import datetime
            
            # 获取数据库中现有的非系统文件
            existing_files = set()
            for file_path, file_name, is_system in self.db.get_unique_files():
                if not is_system:
                    existing_files.add(file_name)
            
            # 删除数据库中已不存在的文件记录
            for file_name in existing_files:
                if file_name not in local_files:
                    self.db.safe_execute(
                        "DELETE FROM knowledge_base WHERE file_name=? AND is_system=0",
                        (file_name,)
                    )
                    print(f"删除数据库中不存在的文件记录: {file_name}")
            
            # 同步每个文件的内容到数据库
            sync_count = 0
            files_to_sync = []
            
            for file_name in local_files:
                file_path = os.path.join(self.kb_folder, file_name)
                is_system = db_file_system_map.get(file_name, 0)
                
                try:
                    # 检查文件是否有变化（基于mtime和大小）
                    file_stat = os.stat(file_path)
                    file_key = f"{file_path}_{file_stat.st_mtime}_{file_stat.st_size}"
                    
                    # 如果文件没变化，跳过
                    if file_name in self._file_sync_cache and self._file_sync_cache[file_name] == file_key:
                        continue
                    
                    self._file_sync_cache[file_name] = file_key
                    files_to_sync.append((file_name, file_path, is_system))
                    sync_count += 1
                    
                except Exception as e:
                    print(f"检查文件变化失败 {file_name}: {e}")
                    continue
            
            # 如果所有文件都没变化，直接返回
            if sync_count == 0:
                print("[同步] 所有文件未变化，跳过同步")
                return
            
            print(f"[同步] 检测到 {sync_count} 个文件有变化，开始同步...")
            
            # 只同步有变化的文件
            for file_name, file_path, is_system in files_to_sync:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 解析文件中的知识点
                    knowledge_items = self.db.parse_knowledge_file(file_path)
                    
                    # 获取数据库中该文件的现有知识点
                    db_items = self.db.safe_fetchall(
                        "SELECT id, title FROM knowledge_base WHERE file_path=?",
                        (file_path,)
                    )
                    db_titles = {item[1]: item[0] for item in db_items}
                    
                    # 更新或插入知识点
                    file_titles = set()
                    for idx, item in enumerate(knowledge_items):
                        title = item['title']
                        content_text = item['content']
                        file_titles.add(title)
                        
                        if title in db_titles:
                            # 更新现有知识点
                            self.db.safe_execute(
                                "UPDATE knowledge_base SET content=?, sort_order=?, updated_at=? WHERE id=?",
                                (content_text, idx, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), db_titles[title])
                            )
                        else:
                            # 插入新知识点
                            self.db.safe_execute(
                                "INSERT INTO knowledge_base (file_path, file_name, title, content, is_active, is_system, created_at, updated_at, sort_order) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
                                (file_path, file_name, title, content_text, 1 if is_system else 0,
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), idx)
                            )
                    
                    # 删除文件中已不存在的知识点
                    for title, item_id in db_titles.items():
                        if title not in file_titles:
                            self.db.safe_execute(
                                "DELETE FROM knowledge_base WHERE id=?",
                                (item_id,)
                            )
                            print(f"删除数据库中不存在的知识点: {title}")
                    
                except Exception as e:
                    print(f"同步文件失败 {file_name}: {e}")
                    
            # 保存缓存到文件
            self._save_file_cache()
            
        except Exception as e:
            print(f"同步文件到数据库失败: {e}")
    
    def _load_file_cache(self):
        """从文件加载持久化的缓存"""
        import json
        self._file_sync_cache = {}
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    self._file_sync_cache = json.load(f)
                print(f"[缓存] 已加载 {len(self._file_sync_cache)} 个文件的缓存")
            except Exception as e:
                print(f"[缓存] 加载缓存失败: {e}")
                self._file_sync_cache = {}
    
    def _save_file_cache(self):
        """保存缓存到文件"""
        import json
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._file_sync_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[缓存] 保存缓存失败: {e}")
         
    def load_knowledge_items(self):
        self.on_file_selected(self.files_list.currentItem())

    def on_file_selected(self, item):
        if not item:
            return
        
        # 如果在搜索模式下，不重新加载文件内容
        if self._is_search_mode:
            return
        
        display_name = item.text()
        if "(系统)" in display_name:
            file_name = display_name.replace("(系统)", "").strip().replace("📦", "").replace("📁", "").strip()
        elif display_name.startswith("📦 ") or display_name.startswith("📁 "):
            file_name = display_name.split(" ", 1)[1]
        else:
            file_name = display_name
        items = self.db.get_all_knowledge_items()
        file_items = [x for x in items if x[2] == file_name]
        
        # 去重：基于标题+内容
        seen_content = set()
        unique_items = []
        for item in file_items:
            content_key = f"{item[3]}|{item[4]}"  # title|content
            if content_key not in seen_content:
                seen_content.add(content_key)
                unique_items.append(item)
        
        self.items_table.setRowCount(len(unique_items))
        for row, item_data in enumerate(unique_items):
            item_id, file_path, file_name, title, content, is_active, is_system = item_data

            # 列1: 匹配（显示"-"表示非搜索模式）
            match_item = QTableWidgetItem("-")
            match_item.setForeground(QColor("#95a5a6"))
            match_item.setTextAlignment(Qt.AlignCenter)
            self.items_table.setItem(row, 0, match_item)

            # 列2: 标题
            title_display = f"【系统】{title}" if is_system else title
            title_item = QTableWidgetItem(title_display)
            title_item.setData(Qt.UserRole, item_id)
            title_item.setData(Qt.UserRole + 1, title)
            title_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 1, title_item)

            # 列3: 内容预览
            content_preview = content if content else ""
            content_item = QTableWidgetItem(content_preview)
            content_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, content_item)

    def delete_item(self, item_id):
        reply = QMessageBox.question(self, "确认删除", "确定要删除这个知识点吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            delete_success = False
            rows = self.db.safe_fetchall("SELECT file_path, title, content FROM knowledge_base WHERE id=?", (item_id,))
            if rows:
                file_path, title, content = rows[0][0], rows[0][1], rows[0][2]
                if file_path and os.path.exists(file_path):
                    try:
                        self._sync_enabled = False
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        # 新格式：查找【标题】行并删除标题+内容
                        title_pattern = f"【{title}】"
                        title_line_idx = -1
                        for i, line in enumerate(lines):
                            if line.strip() == title_pattern:
                                title_line_idx = i
                                break
                        
                        if title_line_idx >= 0:
                            # 找到标题，确定内容范围
                            content_start = title_line_idx
                            content_end = len(lines)
                            for i in range(title_line_idx + 1, len(lines)):
                                if lines[i].strip().startswith("【") and lines[i].strip().endswith("】"):
                                    content_end = i
                                    break
                            
                            # 删除标题和内容行
                            new_lines = lines[:content_start] + lines[content_end:]
                            
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.writelines(new_lines)
                            delete_success = True
                        
                        self._sync_enabled = True
                        QTimer.singleShot(100, self._reenable_sync)
                    except Exception as e:
                        self._sync_enabled = True
                        print(f"删除文件内容失败: {e}")
            
            # 删除数据库记录
            self.db.delete_knowledge_item(item_id)
            
            # 快速刷新显示（不触发完整同步）
            if hasattr(self, '_quick_refresh_display'):
                self._quick_refresh_display()
            else:
                self.load_data()
            
            # 提示用户结果
            if delete_success:
                QMessageBox.information(self, "✅ 成功", "知识点已删除！")
            else:
                QMessageBox.warning(self, "⚠️ 警告", "知识点已从数据库删除，但本地文件可能未更新。")

    def on_item_double_click(self, row, col):
        # 匹配列（col == 0）不支持双击编辑
        if col == 0:
            return

        # 处理标题列的双击（col == 1）
        if col == 1:
            item = self.items_table.item(row, 1)
            if not item:
                return
            
            # 获取原始标题（从UserRole + 1）
            original_title = item.data(Qt.UserRole + 1)
            if not original_title:
                # 如果没有保存原始标题，从数据库获取
                item_id = item.data(Qt.UserRole)
                for db_item in self.db.get_all_knowledge_items():
                    if db_item[0] == item_id:
                        original_title = db_item[3]
                        break
            
            if original_title:
                # 设置编辑文本为原始标题
                item.setText(original_title)
                # 启动编辑
                self.items_table.editItem(item)
            return
        
        # 处理内容列的双击（col == 2）
        if col != 2:
            return
        item_id = self.items_table.item(row, 1).data(Qt.UserRole)
        full_content = None
        file_path = None
        title = None
        for item in self.db.get_all_knowledge_items():
            if item[0] == item_id:
                full_content, file_path, title = item[4], item[1], item[3]
                break
        if full_content is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("✏️ 编辑知识点内容")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("内容："))
        content_input = QTextEdit()
        content_input.setText(full_content)
        layout.addWidget(content_input)
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("💾 保存")
        cancel_btn = QPushButton("取消")
        def save():
            new_content = content_input.toPlainText()
            self.db.update_knowledge_content(item_id, new_content)
            if file_path and os.path.exists(file_path):
                try:
                    self._sync_enabled = False
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    # 新格式：【标题】\n内容\n
                    # 查找标题位置
                    title_pattern = f"【{title}】"
                    title_line_idx = -1
                    for i, line in enumerate(lines):
                        if line.strip() == title_pattern:
                            title_line_idx = i
                            break
                    
                    if title_line_idx >= 0:
                        # 找到标题，确定内容范围（从标题下一行到下一个【标题】或文件结束）
                        content_start = title_line_idx + 1
                        content_end = len(lines)
                        for i in range(content_start, len(lines)):
                            if lines[i].strip().startswith("【") and lines[i].strip().endswith("】"):
                                content_end = i
                                break
                        
                        # 重建文件内容
                        new_lines = lines[:title_line_idx]  # 标题前的内容
                        new_lines.append(f"【{title}】\n")  # 标题行
                        new_lines.append(f"{new_content}\n")  # 新内容行
                        if content_end < len(lines):
                            new_lines.extend(lines[content_end:])  # 保留后面的内容
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(new_lines)
                    else:
                        # 未找到标题，追加到文件末尾
                        with open(file_path, 'a', encoding='utf-8') as f:
                            f.write(f"\n【{title}】\n{new_content}\n")
                    
                    self._sync_enabled = True
                    QTimer.singleShot(100, self._reenable_sync)
                except Exception as e:
                    self._sync_enabled = True
                    print(f"同步到文件失败: {e}")
                    import traceback
                    traceback.print_exc()
            dialog.accept()
            self.load_data()
        save_btn.clicked.connect(save)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        dialog.exec_()

    def delete_selected_file(self):
        current_item = self.files_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要删除的文件！")
            return
        display_name = current_item.text()
        file_name = display_name.split(" ", 1)[1].replace(" (系统)", "") if (display_name.startswith("📦 ") or display_name.startswith("📁 ")) else display_name
        items = self.db.get_all_knowledge_items()
        file_items = [x for x in items if x[2] == file_name]
        if not file_items:
            return
        if file_items[0][6]:
            QMessageBox.warning(self, "提示", "系统知识库文件无法删除！")
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除文件「{file_name}」及其所有知识点吗？\n\n💡 注意：本地文件也会被删除！", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                fp = os.path.join(self.kb_folder, file_name)
                if os.path.exists(fp):
                    os.remove(fp)
                for x in file_items:
                    self.db.delete_knowledge_item(x[0])
                QMessageBox.information(self, "✅ 成功", f"文件「{file_name}」及本地文件已删除！")
                self.load_data()
            except Exception as e:
                QMessageBox.warning(self, "⚠️ 失败", f"删除失败: {e}")

    def on_cell_changed(self, row, col):
        """单元格内容改变时触发（标题编辑）"""
        if col != 0:  # 只处理标题列
            return
        
        # 防止递归：如果正在处理编辑，直接返回
        if hasattr(self, '_is_editing') and self._is_editing:
            return
        
        item = self.items_table.item(row, col)
        if not item:
            return
        
        item_id = item.data(Qt.UserRole)
        new_title = item.text().strip()
        
        if not item_id or not new_title:
            return
        
        # 获取旧标题（从保存的原始标题）
        old_title = item.data(Qt.UserRole + 1)
        if not old_title:
            # 如果没有保存，从数据库获取
            for db_item in self.db.get_all_knowledge_items():
                if db_item[0] == item_id:
                    old_title = db_item[3]
                    break
        
        if not old_title or old_title == new_title:
            return
        
        # 设置编辑标志，防止递归
        self._is_editing = True
        
        # 获取文件路径
        file_path = None
        for db_item in self.db.get_all_knowledge_items():
            if db_item[0] == item_id:
                file_path = db_item[1]
                break
        
        # 检查是否有重复标题
        duplicates = self._check_duplicate_titles(new_title, exclude_id=item_id)
        if duplicates:
            reply = QMessageBox.question(
                self, 
                "⚠️ 发现重复标题", 
                f'标题 "{new_title}" 已存在（{len(duplicates)}个重复）。\n\n是否继续修改？',
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                # 恢复原标题
                item.setText(old_title)
                self._is_editing = False
                return
        
        # 先同步到文件（以文件为准）
        if file_path and os.path.exists(file_path):
            try:
                self._sync_enabled = False
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 查找【旧标题】并替换为【新标题】
                old_pattern = f"【{old_title}】"
                new_pattern = f"【{new_title}】"
                
                title_line_idx = -1
                for i, line in enumerate(lines):
                    if line.strip() == old_pattern:
                        title_line_idx = i
                        lines[i] = line.replace(old_pattern, new_pattern)
                        break
                
                if title_line_idx >= 0:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    
                    # 文件修改成功后再更新数据库
                    self.db.safe_execute(
                        "UPDATE knowledge_base SET title=? WHERE id=?",
                        (new_title, item_id)
                    )
                    
                    # 更新保存的原始标题
                    item.setData(Qt.UserRole + 1, new_title)
                    
                    QMessageBox.information(self, "✅ 成功", f"标题已修改为：{new_title}")
                else:
                    QMessageBox.warning(self, "⚠️ 失败", f"在文件中未找到标题：{old_title}")
                    item.setText(old_title)
                
                self._sync_enabled = True
                QTimer.singleShot(100, self._reenable_sync)
                
            except Exception as e:
                self._sync_enabled = True
                QMessageBox.warning(self, "⚠️ 失败", f"同步到文件失败: {e}")
                item.setText(old_title)
        else:
            QMessageBox.warning(self, "⚠️ 失败", f"文件不存在：{file_path}")
            item.setText(old_title)
        
        # 清除编辑标志
        self._is_editing = False
    
    def _check_duplicate_titles(self, title, exclude_id=None):
        """检查重复标题"""
        if exclude_id:
            rows = self.db.safe_fetchall(
                "SELECT id, title, file_name FROM knowledge_base WHERE title=? AND id!=?",
                (title, exclude_id)
            )
        else:
            rows = self.db.safe_fetchall(
                "SELECT id, title, file_name FROM knowledge_base WHERE title=?",
                (title,)
            )
        return rows
    
    def _sync_title_change(self, file_path, old_title, new_title):
        """同步标题修改到文件"""
        try:
            self._sync_enabled = False
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 替换标题
            old_pattern = f"【{old_title}】"
            new_pattern = f"【{new_title}】"
            content = content.replace(old_pattern, new_pattern)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self._sync_enabled = True
            QTimer.singleShot(100, self._reenable_sync)
        except Exception as e:
            self._sync_enabled = True
            print(f"同步标题修改到文件失败: {e}")

    def check_duplicates(self):
        """检测重复话术"""
        try:
            all_items = self.db.get_all_knowledge_items()
            if not all_items:
                QMessageBox.information(self, "检测结果", "知识库为空，无重复内容。")
                return
            
            # 收集重复项
            title_duplicates = {}  # 标题重复
            content_duplicates = {}  # 内容重复
            
            title_map = {}
            content_map = {}
            
            for item in all_items:
                item_id, file_path, file_name, title, content, is_active, is_system = item
                
                # 检查标题重复
                title_key = title.strip()
                if title_key in title_map:
                    if title_key not in title_duplicates:
                        title_duplicates[title_key] = [title_map[title_key]]
                    title_duplicates[title_key].append(item)
                else:
                    title_map[title_key] = item
                
                # 检查内容重复（前100字符）
                content_key = content.strip()[:100]
                if content_key in content_map:
                    if content_key not in content_duplicates:
                        content_duplicates[content_key] = [content_map[content_key]]
                    content_duplicates[content_key].append(item)
                else:
                    content_map[content_key] = item
            
            # 显示检测报告
            self._show_duplicate_report(title_duplicates, content_duplicates)
            
        except Exception as e:
            QMessageBox.warning(self, "⚠️ 检测失败", f"重复检测失败: {e}")
    
    def _show_duplicate_report(self, title_duplicates, content_duplicates):
        """显示重复检测报告"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🔍 重复话术检测报告")
        dialog.resize(800, 600)
        
        layout = QVBoxLayout(dialog)
        
        # 统计信息
        total_title_dups = sum(len(items) for items in title_duplicates.values())
        total_content_dups = sum(len(items) for items in content_duplicates.values())
        
        info_label = QLabel(f"""
        <h3>检测结果</h3>
        <p><b>标题重复:</b> {len(title_duplicates)} 组，共 {total_title_dups} 条</p>
        <p><b>内容重复:</b> {len(content_duplicates)} 组，共 {total_content_dups} 条</p>
        """)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 创建表格显示重复项
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["类型", "内容", "文件", "操作", "ID"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        row = 0
        
        # 添加标题重复项
        for title, items in title_duplicates.items():
            for item in items:
                item_id, file_path, file_name, _, content, _, _ = item
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem("🔴 标题重复"))
                table.setItem(row, 1, QTableWidgetItem(f"标题: {title[:50]}...\n内容: {content[:50]}..."))
                table.setItem(row, 2, QTableWidgetItem(file_name))
                
                delete_btn = QPushButton("删除")
                delete_btn.clicked.connect(lambda checked, id=item_id: self.delete_duplicate_item(id, dialog))
                table.setCellWidget(row, 3, delete_btn)
                
                table.setItem(row, 4, QTableWidgetItem(str(item_id)))
                row += 1
        
        # 添加内容重复项
        for content_key, items in content_duplicates.items():
            for item in items:
                item_id, file_path, file_name, title, content, _, _ = item
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem("🟡 内容重复"))
                table.setItem(row, 1, QTableWidgetItem(f"标题: {title}\n内容: {content[:100]}..."))
                table.setItem(row, 2, QTableWidgetItem(file_name))
                
                delete_btn = QPushButton("删除")
                delete_btn.clicked.connect(lambda checked, id=item_id: self.delete_duplicate_item(id, dialog))
                table.setCellWidget(row, 3, delete_btn)
                
                table.setItem(row, 4, QTableWidgetItem(str(item_id)))
                row += 1
        
        layout.addWidget(table)
        
        # 批量操作按钮
        btn_layout = QHBoxLayout()
        auto_clean_btn = QPushButton("🧹 自动清理（保留第一条）")
        auto_clean_btn.clicked.connect(lambda: self.auto_clean_duplicates(title_duplicates, content_duplicates, dialog))
        btn_layout.addWidget(auto_clean_btn)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def delete_duplicate_item(self, item_id, parent_dialog=None):
        """删除重复项"""
        reply = QMessageBox.question(self, "确认删除", "确定要删除这条重复内容吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.delete_item(item_id)
            if parent_dialog:
                parent_dialog.accept()
                self.check_duplicates()  # 重新检测
    
    def auto_clean_duplicates(self, title_duplicates, content_duplicates, parent_dialog=None):
        """自动清理重复项（保留每组第一条）- 同步删除本地文件"""
        reply = QMessageBox.question(
            self, 
            "确认自动清理", 
            "自动清理将删除每组重复内容中的后续条目，只保留第一条。\n\n⚠️ 同时会从本地文件同步删除！\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        deleted_count = 0
        failed_items = []
        
        # 收集所有要删除的项
        items_to_delete = []
        
        # 收集标题重复（保留第一条）
        for title, items in title_duplicates.items():
            for item in items[1:]:  # 跳过第一条
                items_to_delete.append(item)
        
        # 收集内容重复（保留第一条）
        for content_key, items in content_duplicates.items():
            for item in items[1:]:  # 跳过第一条
                items_to_delete.append(item)
        
        # 执行删除（同步到文件）
        for item in items_to_delete:
            item_id = item[0]
            file_path = item[1]
            title = item[3]
            
            # 同步删除本地文件中的内容
            if file_path and os.path.exists(file_path):
                try:
                    self._sync_enabled = False
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    # 查找【标题】行并删除标题+内容
                    title_pattern = f"【{title}】"
                    title_line_idx = -1
                    for i, line in enumerate(lines):
                        if line.strip() == title_pattern:
                            title_line_idx = i
                            break
                    
                    if title_line_idx >= 0:
                        # 找到标题，确定内容范围
                        content_start = title_line_idx
                        content_end = len(lines)
                        for i in range(title_line_idx + 1, len(lines)):
                            if lines[i].strip().startswith("【") and lines[i].strip().endswith("】"):
                                content_end = i
                                break
                        
                        # 删除标题和内容行
                        new_lines = lines[:content_start] + lines[content_end:]
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(new_lines)
                    
                    self._sync_enabled = True
                    QTimer.singleShot(100, self._reenable_sync)
                except Exception as e:
                    self._sync_enabled = True
                    failed_items.append(title)
                    print(f"同步删除到文件失败: {e}")
            
            # 删除数据库记录
            self.db.delete_knowledge_item(item_id)
            deleted_count += 1
        
        # 显示清理结果
        if failed_items:
            QMessageBox.warning(
                self, 
                "✅ 清理完成（部分失败）", 
                f"已删除 {deleted_count} 条重复内容。\n\n以下项目文件同步失败：\n" + "\n".join(failed_items)
            )
        else:
            QMessageBox.information(self, "✅ 清理完成", f"已自动删除 {deleted_count} 条重复内容，并已同步到本地文件。")
        
        self.load_data()
        if parent_dialog:
            parent_dialog.accept()

    def rename_selected_file(self):
        current_item = self.files_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要重命名的文件！")
            return
        display_name = current_item.text()
        old_file_name = display_name.split(" ", 1)[1].replace(" (系统)", "") if (display_name.startswith("📦 ") or display_name.startswith("📁 ")) else display_name
        items = self.db.get_all_knowledge_items()
        file_items = [x for x in items if x[2] == old_file_name]
        if not file_items:
            return
        if file_items[0][6]:
            QMessageBox.warning(self, "提示", "系统知识库文件无法重命名！")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("✏️ 重命名文件")
        dialog.resize(400, 150)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"当前文件名：{old_file_name}"))
        layout.addWidget(QLabel("新文件名："))
        new_name_input = QLineEdit()
        new_name_input.setText(old_file_name)
        layout.addWidget(new_name_input)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("✅ 确认")
        cancel_btn = QPushButton("取消")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        if dialog.exec_() == QDialog.Accepted:
            new_file_name = new_name_input.text().strip()
            if not new_file_name:
                QMessageBox.warning(self, "⚠️ 错误", "文件名不能为空！")
                return
            if new_file_name == old_file_name:
                return
            old_fp = os.path.join(self.kb_folder, old_file_name)
            new_fp = os.path.join(self.kb_folder, new_file_name)
            if os.path.exists(new_fp):
                QMessageBox.warning(self, "⚠️ 错误", f"文件「{new_file_name}」已存在！")
                return
            try:
                if os.path.exists(old_fp):
                    os.rename(old_fp, new_fp)
                self.db.safe_execute(
                    "UPDATE knowledge_base SET file_name = ?, file_path = ? WHERE file_name = ?",
                    (new_file_name, new_fp, old_file_name)
                )
                QMessageBox.information(self, "✅ 成功", f"文件「{old_file_name}」已重命名为「{new_file_name}」！")
                self.load_data()
            except Exception as e:
                QMessageBox.warning(self, "⚠️ 失败", f"重命名失败: {e}")

    def clear_all(self):
        reply = QMessageBox.question(self, "确认清空", "确定要清空所有用户知识库吗？系统知识库不会被删除。", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.safe_execute("DELETE FROM knowledge_base WHERE is_system=0")
            QMessageBox.information(self, "✅ 成功", "用户知识库已清空！系统知识库保留。")
            self.load_data()

    def _on_search_timer_timeout(self):
        """搜索定时器超时回调"""
        query = self.search_input.text().strip()
        if query:
            selected_files = self._get_selected_files()
            self.perform_rag_search(query, selected_files=selected_files if selected_files else None)
    
    def on_search_text_changed(self, text):
        """实时搜索（带防抖）"""
        if not text or not text.strip():
            self.reset_search()
            return

        # 取消之前的定时器并重新启动
        self._search_timer.stop()
        self._search_timer.start(300)
    
    def _init_rag_search(self):
        """初始化RAG搜索适配器（AI搜索需要）- 使用单例模式避免重复加载"""
        if not self._is_stence_enabled():
            self.rag_adapter = None
            return

        # 检查是否已经初始化过（避免重复加载）
        if hasattr(self, 'rag_adapter') and self.rag_adapter is not None:
            if hasattr(self.rag_adapter, 'engine') and self.rag_adapter.engine is not None:
                if hasattr(self.rag_adapter.engine, '_is_initialized') and self.rag_adapter.engine._is_initialized:
                    return

        try:
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            rag_dir = os.path.join(os.path.dirname(current_dir), 'rag')
            if rag_dir not in sys.path:
                sys.path.insert(0, rag_dir)

            from search_ui_adapter import get_search_adapter
            self.rag_adapter = get_search_adapter(self.db)

            import threading
            def init_engine():
                try:
                    self.rag_adapter.initialize(timeout=60)
                except Exception as e:
                    print(f"[RAG] 初始化引擎失败: {e}")
            threading.Thread(target=init_engine, daemon=True).start()
        except Exception as e:
            self.rag_adapter = None
    
    def perform_rag_search(self, query, selected_files=None):
        """执行RAG智能搜索 - 使用向量检索实现语义理解"""
        if not query:
            return

        try:
            # 获取所有知识库条目
            all_items = self.db.get_all_knowledge_items()
            if not all_items:
                return

            # 过滤到选中的文件
            if selected_files:
                all_items = [item for item in all_items if len(item) >= 3 and item[2] in selected_files]

            # 对数据库结果去重 - 基于标题+内容
            unique_items = []
            seen_content = set()
            for item in all_items:
                if len(item) >= 5:
                    item_id, file_path, file_name, title, content = item[0], item[1], item[2], item[3], item[4]
                    # 使用标题+内容作为唯一键
                    content_key = f"{title}|{content}"
                    if content_key not in seen_content:
                        seen_content.add(content_key)
                        unique_items.append(item)

            # 设置搜索模式
            self._is_search_mode = True

            # 使用本地模糊搜索（快速）
            results = self._simple_search(query, unique_items)
            self._search_results = results

            # 显示结果
            self._display_search_results()

        except Exception as e:
            print(f"搜索失败: {e}")
            import traceback
            traceback.print_exc()

    def _simple_search(self, query, items):
        """智能搜索 - 支持模糊匹配、同义词和关键词组合匹配"""
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        results = []
        seen_ids = set()  # 防止重复

        # 扩展查询词 - 添加常见同义词/相似词
        query_words = self._expand_query(query_lower)

        # 将查询拆分为单个字符或词组，用于匹配不连续的关键词
        query_chars = list(query_lower.replace(" ", ""))

        for item in items:
            if len(item) >= 5:
                item_id = item[0]
                # 跳过已处理的项目
                if item_id in seen_ids:
                    continue

                title = item[3] if len(item) > 3 else ""
                content = item[4] if len(item) > 4 else ""

                title_lower = title.lower()
                content_lower = content.lower()

                score = 0
                match_type = ""

                # 检查所有扩展词
                for qword in query_words:
                    # 优先级1: 标题精确匹配
                    if title_lower == qword:
                        score = max(score, 100)
                        match_type = "标题精确"
                        break

                    # 优先级2: 标题包含关键词
                    if qword in title_lower:
                        score = max(score, 90)
                        match_type = "标题匹配"

                    # 优先级3: 内容精确匹配
                    if content_lower == qword:
                        score = max(score, 80)
                        match_type = "内容精确"

                    # 优先级4: 内容包含关键词
                    if qword in content_lower:
                        score = max(score, 70)
                        match_type = "内容匹配"

                    # 优先级5: 模糊匹配（编辑距离）
                    if self._fuzzy_match(title_lower, qword):
                        score = max(score, 60)
                        match_type = "标题模糊"

                    if self._fuzzy_match(content_lower, qword):
                        score = max(score, 50)
                        match_type = "内容模糊"

                    # 优先级6: 分词匹配
                    title_words = [w for w in title_lower.split() if len(w) >= 2]
                    for word in title_words:
                        if qword in word or word in qword or self._fuzzy_match(word, qword):
                            score = max(score, 40)
                            match_type = "标题分词"
                            break

                    content_words = [w for w in content_lower.split() if len(w) >= 2]
                    for word in content_words:
                        if qword in word or word in qword or self._fuzzy_match(word, qword):
                            score = max(score, 30)
                            match_type = "内容分词"
                            break

                # 新增：检查查询词和标题是否有字符重叠（双向匹配）
                # 只要有任意一个字符匹配就计分
                if score < 90 and query_chars:
                    title_chars = list(title_lower.replace(" ", ""))
                    matched_chars = sum(1 for c in query_chars if c in title_lower)
                    if matched_chars > 0:
                        score = max(score, 20 + matched_chars * 15)
                        match_type = "标题字符"

                if score < 70 and query_chars:
                    matched_chars = sum(1 for c in query_chars if c in content_lower)
                    if matched_chars > 0:
                        score = max(score, 15 + matched_chars * 10)
                        match_type = "内容字符"

                if score > 0:
                    seen_ids.add(item_id)
                    results.append({
                        "rank": len(results) + 1,
                        "item_id": item_id,
                        "title": title,
                        "content": content,
                        "file_name": item[2] if len(item) > 2 else "",
                        "file_path": item[1] if len(item) > 1 else "",
                        "hybrid_score": score,
                        "vector_score": 0,
                        "bm25_score": 0,
                        "match_type": match_type
                    })

        # 按分数从高到低排序
        return sorted(results, key=lambda x: x["hybrid_score"], reverse=True)

    def _chars_all_in_text(self, text, chars):
        """检查chars中的所有字符是否都出现在text中（不要求顺序）"""
        if not text or not chars:
            return False

        # 只检查每个字符是否存在于文本中，不要求顺序
        for char in chars:
            if char not in text:
                return False
        return True

    def _expand_query(self, query):
        """直接返回原始查询词，不进行同义词扩展"""
        return [query]

    def _fuzzy_match(self, text, query, threshold=0.6):
        """模糊匹配 - 使用简单的编辑距离比例"""
        if not text or not query:
            return False

        # 如果文本包含查询词，直接返回True
        if query in text:
            return True

        # 计算编辑距离比例
        import difflib
        similarity = difflib.SequenceMatcher(None, text, query).ratio()
        return similarity >= threshold
    
    def _display_search_results(self):
        """显示搜索结果 - 仅显示匹配项"""
        # 更新知识点表格
        self.items_table.clearSpans()

        # 如果没有匹配结果，显示提示
        if not self._search_results:
            self.items_table.setRowCount(1)
            # 清除第0行可能存在的cellWidget（删除按钮）
            for col in range(4):
                self.items_table.removeCellWidget(0, col)

            no_result_item = QTableWidgetItem("未找到匹配结果")
            no_result_item.setTextAlignment(Qt.AlignCenter)
            font = no_result_item.font()
            font.setPointSize(12)
            no_result_item.setFont(font)
            no_result_item.setForeground(QColor("#7f8c8d"))
            self.items_table.setItem(0, 0, no_result_item)

            suggest_item = QTableWidgetItem('没有找到相关内容\n建议：\n1. 检查关键词拼写\n2. 尝试使用更简短的关键词\n3. 使用相关词汇搜索')
            suggest_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(0, 1, suggest_item)
            self.items_table.setItem(0, 2, QTableWidgetItem(""))
            self.items_table.setItem(0, 3, QTableWidgetItem(""))
            self.items_table.setSpan(0, 0, 1, 4)
            return

        # 只显示匹配结果
        self.items_table.setRowCount(len(self._search_results))

        row = 0
        for r in self._search_results:
            # 匹配结果分数（转换为百分比）
            score = r.get("hybrid_score", 0)
            # 确保分数在0-100之间
            score_percent = min(100, max(0, int(score)))
            match_type = r.get("match_type", "匹配")

            # 根据分数计算小火苗数量（0-3个）
            if score_percent >= 80:
                flames = 3
                color = "#ff0000"  # 红色 - 高匹配
            elif score_percent >= 50:
                flames = 2
                color = "#f39c12"  # 橙色 - 中匹配
            elif score_percent >= 20:
                flames = 1
                color = "#3498db"  # 蓝色 - 低匹配
            else:
                flames = 0
                color = "#95a5a6"  # 灰色 - 很低匹配

            # 生成小火苗字符串
            flame_str = "🔥" * flames + "〇" * (3 - flames)

            # 列1: 匹配类型（小火苗+百分比）
            match_label = f"{flame_str} {score_percent}%"
            match_item = QTableWidgetItem(match_label)
            match_item.setForeground(QColor(color))
            match_item.setTextAlignment(Qt.AlignCenter)
            self.items_table.setItem(row, 0, match_item)

            # 列2: 标题
            title = r.get("title", "")
            title_item = QTableWidgetItem(title)
            title_item.setData(Qt.UserRole, r.get("item_id"))
            title_item.setData(Qt.UserRole + 1, title)
            title_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 1, title_item)

            # 列3: 内容预览（最多100字）
            content = r.get("content", "")
            if len(content) > 100:
                content = content[:100] + "..."
            content_item = QTableWidgetItem(content)
            content_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, content_item)

            row += 1

    def _update_api_status(self):
        """更新API配置状态显示（最小化版本）"""
        if self.db:
            api_key = self.db.get_setting("ai_api_key", "") or ""
            if api_key:
                # 判断API类型
                if "sk-" in api_key or api_key.startswith("deepseek-"):
                    self.api_status_label.setText("🤖")
                    self.api_status_label.setToolTip("AI API: DeepSeek 已配置")
                else:
                    self.api_status_label.setText("🤖")
                    self.api_status_label.setToolTip("AI API: OpenAI 已配置")
                self.api_status_label.setStyleSheet("color: #27ae60; font-size: 10px;")
            else:
                self.api_status_label.setText("🤖")
                self.api_status_label.setToolTip("AI API未配置")
                self.api_status_label.setStyleSheet("color: #95a5a6; font-size: 10px;")

    def _update_rag_status(self):
        """更新RAG向量索引状态显示"""
        try:
            if not self._is_stence_enabled():
                self.rag_status_label.setText("⚪")
                self.rag_status_label.setToolTip("stence模型未启用")
                self.rag_status_label.setStyleSheet("font-size: 12px;")
                return

            if hasattr(self, 'rag_adapter') and self.rag_adapter:
                if self.rag_adapter.engine and self.rag_adapter.engine._is_initialized:
                    # 检查索引状态
                    try:
                        index_stats = self.rag_adapter.engine.vector_store.get_stats()
                        doc_count = index_stats.get("total_documents", 0)
                        collection_exists = index_stats.get("exists", True)
                        if doc_count > 0 and collection_exists:
                            self.rag_status_label.setText("🟢")
                            self.rag_status_label.setToolTip(f"RAG向量索引: 已构建 ({doc_count} 条) - 可用语义搜索")
                            self.rag_status_label.setStyleSheet("font-size: 12px;")
                        else:
                            self.rag_status_label.setText("🟠")
                            self.rag_status_label.setToolTip("RAG向量索引: 未构建，请点击重建索引")
                            self.rag_status_label.setStyleSheet("font-size: 12px;")
                    except Exception as e:
                        error_msg = str(e)
                        if "does not exist" in error_msg or "not found" in error_msg:
                            self.rag_status_label.setText("🟠")
                            self.rag_status_label.setToolTip("RAG向量索引: 未构建，请点击重建索引")
                            self.rag_status_label.setStyleSheet("font-size: 12px;")
                        else:
                            self.rag_status_label.setText("🔴")
                            self.rag_status_label.setToolTip(f"RAG向量索引: 检查失败 ({e})")
                            self.rag_status_label.setStyleSheet("font-size: 12px;")
                else:
                    self.rag_status_label.setText("🟠")
                    self.rag_status_label.setToolTip("RAG向量索引: 模型加载中...")
                    self.rag_status_label.setStyleSheet("font-size: 12px;")
            else:
                self.rag_status_label.setText("⚪")
                self.rag_status_label.setToolTip("RAG向量索引: 未初始化")
                self.rag_status_label.setStyleSheet("font-size: 12px;")
        except Exception as e:
            self.rag_status_label.setText("⚪")
            self.rag_status_label.setToolTip("RAG向量索引: 未初始化")
            self.rag_status_label.setStyleSheet("font-size: 12px;")

    def _is_stence_enabled(self):
        """检查stence模型是否启用"""
        if self.db:
            return self.db.get_setting("stence_model_enabled", "1") == "1"
        return True

    def _update_stence_switch_status(self):
        """更新stence模型开关状态显示"""
        if self._is_stence_enabled():
            self.stence_switch_btn.setText("🔌 启用")
            self.stence_switch_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4ECDC4;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45B7D1;
                }
            """)
            self.stence_switch_btn.setToolTip("stence模型: 已启用 - 点击关闭")
        else:
            self.stence_switch_btn.setText("⛔ 关闭")
            self.stence_switch_btn.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
            """)
            self.stence_switch_btn.setToolTip("stence模型: 未启用 - 点击开启")

    def toggle_stence_model(self):
        """切换stence模型启用状态"""
        current = self._is_stence_enabled()
        new_value = "0" if current else "1"
        if self.db:
            self.db.set_setting("stence_model_enabled", new_value)
        self._update_stence_switch_status()

        if new_value == "1":
            QMessageBox.information(self, "提示", "stence模型已启用，将在下次打开知识库时加载模型")
        else:
            QMessageBox.information(self, "提示", "stence模型已关闭，将跳过模型加载，加快启动速度")

    def on_rebuild_index_clicked(self):
        """重建索引按钮点击"""
        reply = QMessageBox.question(self, "确认重建索引",
            "确定要重建向量索引吗？\n这将清空现有索引并重新构建。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply != QMessageBox.Yes:
            return

        if not hasattr(self, 'rag_adapter') or not self.rag_adapter:
            QMessageBox.warning(self, "⚠️ RAG未初始化", "请先启用stence模型")
            return

        self._rebuild_result = None

        def do_rebuild():
            try:
                all_items = self.db.get_all_knowledge_items()
                if not all_items:
                    self._rebuild_result = ("empty", None)
                    return

                knowledge_items = []
                for item in all_items:
                    if len(item) >= 5:
                        item_id, file_path, file_name, title, content = item[0], item[1], item[2], item[3], item[4]
                        knowledge_items.append((item_id, file_path, file_name, title, content))

                result = self.rag_adapter.build_index(knowledge_items, force=True)
                self._rebuild_result = ("success", result)

            except Exception as e:
                self._rebuild_result = ("error", str(e))

        def check_result():
            if self._rebuild_result is None:
                QTimer.singleShot(100, check_result)
                return
            self._hide_progress()
            status, data = self._rebuild_result
            if status == "empty":
                QMessageBox.information(self, "提示", "知识库为空，无需重建索引")
            elif status == "success":
                if data.get("status") == "success":
                    doc_count = data.get("total_chunks", 0)
                    QMessageBox.information(self, "✅ 索引重建完成",
                        f"索引重建成功！\n\n共索引 {doc_count} 个知识条目")
                else:
                    QMessageBox.warning(self, "⚠️ 索引重建失败", data.get("message", "未知错误"))
            else:
                QMessageBox.critical(self, "❌ 错误", f"重建索引失败：{data}")

        import threading
        self._show_progress("正在重建索引...")
        threading.Thread(target=do_rebuild, daemon=True).start()
        QTimer.singleShot(100, check_result)

    def on_manual_sync_clicked(self):
        """手动同步按钮点击"""
        self.btn_manual_sync.setEnabled(False)
        self.btn_manual_sync.setText("同步中...")

        def do_sync():
            try:
                # 获取本地文件列表
                local_files = []
                if hasattr(self, 'kb_folder') and self.kb_folder and os.path.exists(self.kb_folder):
                    for f in os.listdir(self.kb_folder):
                        if f.endswith('.txt'):
                            local_files.append(f)

                # 获取数据库中的文件列表
                db_items = self.db.get_all_knowledge_items()
                db_files = set()
                for item in db_items:
                    if len(item) >= 3:
                        db_files.add(item[2])

                # 找出需要删除的（数据库有但本地没有的）
                files_to_delete = db_files - set(local_files)

                deleted_count = 0
                if files_to_delete:
                    for file_name in files_to_delete:
                        self.db.safe_execute(
                            "DELETE FROM knowledge_base WHERE file_name=?",
                            (file_name,)
                        )
                        deleted_count += 1
                    self.db.conn.commit()

                # 重新导入本地文件
                reimport_count = 0
                for file_name in local_files:
                    file_path = os.path.join(self.kb_folder, file_name)
                    if os.path.exists(file_path):
                        self.db.import_knowledge_file(file_path)
                        reimport_count += 1

                # 更新缓存
                self._update_cache_after_sync(local_files)

                # 刷新界面
                self.load_data()

                # 提示结果
                QMessageBox.information(self, "✅ 同步完成",
                    f"同步完成！\n\n删除了 {deleted_count} 个已不存在文件的知识点\n重新导入了 {reimport_count} 个文件")

            except Exception as e:
                QMessageBox.critical(self, "❌ 同步失败", f"同步失败：{str(e)}")
            finally:
                self.btn_manual_sync.setEnabled(True)
                self.btn_manual_sync.setText("🔄 同步")

        # 在后台线程执行同步
        import threading
        threading.Thread(target=do_sync, daemon=True).start()

    def _update_cache_after_sync(self, local_files):
        """同步完成后更新缓存"""
        import json
        self._file_sync_cache = {}
        for file_name in local_files:
            file_path = os.path.join(self.kb_folder, file_name)
            if os.path.exists(file_path):
                import hashlib
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    file_key = hashlib.md5(content.encode('utf-8')).hexdigest()
                    self._file_sync_cache[file_name] = file_key
        self._save_file_cache()

    def on_ai_search_clicked(self):
        """AI智能搜索按钮点击 - RAG+AI两轮搜索"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.information(self, "提示", "请先输入关键词")
            self.search_input.setFocus()
            return

        # 检查API配置
        if self.db:
            api_key = self.db.get_setting("ai_api_key", "") or ""
            if not api_key:
                QMessageBox.warning(self, "⚠️ 未配置API", "请先配置AI API Key\n\n路径：主界面 → API配置 → 输入DeepSeek或OpenAI的API Key")
                return
        else:
            QMessageBox.warning(self, "⚠️ 错误", "数据库未连接")
            return

        # 获取选中文件
        selected_files = self._get_selected_files()
        
        # 执行AI搜索（传递选中的文件）
        self._perform_ai_search(query, selected_files)

    def on_vector_search_clicked(self):
        """向量搜索按钮点击 - 纯向量检索"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.information(self, "提示", "请先输入关键词")
            self.search_input.setFocus()
            return

        if not hasattr(self, 'rag_adapter') or not self.rag_adapter:
            QMessageBox.warning(self, "⚠️ 向量搜索未就绪", "RAG引擎尚未初始化")
            return

        if not hasattr(self.rag_adapter, 'engine') or not self.rag_adapter.engine:
            QMessageBox.warning(self, "⚠️ 向量引擎未就绪", "向量搜索引擎未初始化，请重新打开知识库窗口")
            return

        if not self.rag_adapter.engine._is_initialized:
            reply = QMessageBox.question(self, "⏳ 模型加载中",
                "向量模型正在后台加载中，是否等待加载完成后立即搜索？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.btn_vector_search.setEnabled(False)
                self.btn_vector_search.setText("加载中...")
                for _ in range(30):
                    time.sleep(1)
                    if self.rag_adapter.engine._is_initialized:
                        break
                self.btn_vector_search.setEnabled(True)
                self.btn_vector_search.setText("📊 向量搜索")
                if not self.rag_adapter.engine._is_initialized:
                    QMessageBox.warning(self, "⚠️ 超时", "模型加载超时，请稍后再试")
                    return
            else:
                return

        try:
            # 显示底部进度条
            self._show_progress("向量搜索中...")

            # 获取选中文件
            selected_files = self._get_selected_files()
            print(f"[DEBUG] 向量搜索 - 选中文件: {selected_files}", flush=True)

            # 获取知识库条目 - 根据选中文件过滤
            all_items = self.db.get_all_knowledge_items()

            if selected_files:
                # 只搜索选中的文件
                all_items = [item for item in all_items if len(item) >= 3 and item[2] in selected_files]
                print(f"[DEBUG] 搜索选中文件: {selected_files}, 条目数: {len(all_items)}", flush=True)

            if not all_items:
                QMessageBox.information(self, "提示", "知识库为空")
                self._hide_progress()
                return

            # 构建搜索列表（仅用于BM25检索，向量检索使用已有索引）
            knowledge_items = []
            for item in all_items:
                if len(item) >= 5:
                    item_id, file_path, file_name, title, content = item[0], item[1], item[2], item[3], item[4]
                    knowledge_items.append((item_id, file_path, file_name, title, content))

            # 直接搜索（使用已有索引）
            print(f"[DEBUG] 使用已有索引进行搜索", flush=True)

            # 执行搜索
            current_threshold = self.threshold_slider.value() / 100.0
            results = self.rag_adapter.search(query, top_k=10, selected_files=selected_files, use_rag=True, min_relevance=current_threshold)

            # 隐藏进度条
            self._hide_progress()

            if not results:
                self._show_no_results_message(query)
                return

            # 显示结果
            self._show_vector_search_results(results, query)

        except Exception as e:
            self._hide_progress()
            QMessageBox.critical(self, "❌ 向量搜索失败", f"搜索出错：{str(e)}")

    def _show_vector_search_results(self, results, query):
        """显示向量搜索结果"""
        self._is_search_mode = True
        self._search_results = results
        self.items_table.clearSpans()
        self.items_table.setRowCount(len(results))

        for row, result in enumerate(results):
            if isinstance(result, dict):
                item_id = result.get('item_id', '')
                title = result.get('title', '')
                content = result.get('content', '')
                score = result.get('hybrid_score', result.get('vector_score', result.get('score', 0)))
            else:
                item_id, title, content, score = '', '', '', 0

            # 分数显示优化
            score_percent = min(score * 100, 99)
            
            if score >= 0.08:
                stars = "⭐⭐⭐"
            elif score >= 0.05:
                stars = "⭐⭐"
            elif score >= 0.02:
                stars = "⭐"
            else:
                stars = ""
            
            score_display = f"{stars} {score_percent:.0f}%" if stars else f"{score_percent:.0f}%"
            score_item = QTableWidgetItem(score_display)
            score_item.setTextAlignment(Qt.AlignCenter)
            self.items_table.setItem(row, 0, score_item)

            title_item = QTableWidgetItem(title)
            title_item.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            title_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 1, title_item)

            content_preview = content if content else ""
            content_item = QTableWidgetItem(content_preview)
            content_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, content_item)

            self.items_table.item(row, 0).setData(Qt.UserRole, {
                'item_id': item_id,
                'title': title,
                'content': content,
                'score': score
            })

        self.items_table.setHorizontalHeaderLabels(["匹配度", "标题", "内容预览"])
        self.lbl_file_count.setText(f"📊 向量搜索: 找到 {len(results)} 条相关结果")

    def _perform_ai_search(self, query, selected_files=None):
        """执行AI智能搜索 - 两步：1.RAG向量粗筛 2.AI语义精筛"""
        try:
            # 获取选中文件
            selected_files = self._get_selected_files()
            
            # 获取所有知识库条目
            all_items = self.db.get_all_knowledge_items()
            if not all_items:
                QMessageBox.information(self, "提示", "知识库为空")
                return

            # 过滤到选中的文件（没选则搜索全部）
            if selected_files:
                all_items = [item for item in all_items if len(item) >= 3 and item[2] in selected_files]
            
            if not all_items:
                QMessageBox.information(self, "提示", "选中文件中没有知识库内容")
                return

            # 提取所有标题
            titles = []
            for item in all_items:
                if len(item) >= 5:
                    item_id = item[0]
                    file_name = item[2] if len(item) > 2 else ""
                    title = item[3] if len(item) > 3 else ""
                    content = item[4] if len(item) > 4 else ""
                    if title.strip():
                        titles.append({
                            "item_id": item_id,
                            "file_name": file_name,
                            "title": title,
                            "content": content
                        })

            if not titles:
                QMessageBox.information(self, "提示", "没有找到可搜索的标题")
                return

            # 显示加载提示和进度条
            self.btn_ai_search.setEnabled(False)
            self.btn_ai_search.setText("🤖 向量检索中...")
            self._show_progress("RAG向量检索中...")

            # 第一步：使用RAG向量检索进行粗筛
            print(f"[AI 搜索] 原始标题数量：{len(titles)}")
            self._init_rag_search()
            
            candidates = titles
            if hasattr(self, 'rag_adapter') and self.rag_adapter and hasattr(self.rag_adapter, 'engine') and self.rag_adapter.engine and self.rag_adapter.engine._is_initialized:
                try:
                    # 构建索引（如果需要）
                    knowledge_items = [(t['item_id'], "", t['file_name'], t['title'], t['content']) for t in titles]
                    self.rag_adapter.build_index(knowledge_items, force=False)
                    
                    # 向量检索粗筛
                    current_threshold = 0.3
                    if hasattr(self.rag_adapter.engine, 'hybrid_retriever'):
                        current_threshold = self.rag_adapter.engine.hybrid_retriever.min_relevance_score
                    
                    vector_results = self.rag_adapter.search(query, top_k=min(50, len(titles)), use_rag=True, min_relevance=current_threshold)
                    print(f"[AI 搜索] 向量检索粗筛结果数量：{len(vector_results)}")
                    
                    # 将向量结果转换为标题列表
                    if vector_results:
                        result_ids = set()
                        for r in vector_results:
                            if hasattr(r, 'metadata'):
                                result_ids.add(r.metadata.get('item_id', 0))
                            elif isinstance(r, dict):
                                result_ids.add(r.get('item_id', 0))
                        
                        # 只保留在向量结果中的标题
                        candidates = [t for t in titles if t['item_id'] in result_ids]
                        print(f"[AI 搜索] 粗筛后候选标题数量：{len(candidates)}")
                except Exception as e:
                    print(f"[AI 搜索] 向量检索失败，使用全部标题: {e}")
            
            if not candidates:
                QMessageBox.information(self, "提示", "向量检索未找到相关结果")
                self.btn_ai_search.setEnabled(True)
                self.btn_ai_search.setText("🤖 AI搜索")
                self._hide_progress()
                return

            # 第二步：使用AI对粗筛后的标题进行语义匹配打分
            self.btn_ai_search.setText("🤖 AI分析中...")
            self._show_progress("AI语义分析中...")
            
            ai_results = self._ai_semantic_search(query, candidates)
            print(f"[AI 搜索] AI评分后结果数量：{len(ai_results)}")

            if not ai_results:
                QMessageBox.information(self, "提示", "AI未能找到相关结果，请尝试其他关键词")
                self.btn_ai_search.setEnabled(True)
                self.btn_ai_search.setText("🤖 AI搜索")
                self._hide_progress()
                return

            # 显示 AI 搜索结果
            self._display_ai_search_results(ai_results)

        except Exception as e:
            QMessageBox.critical(self, "❌ AI搜索失败", f"搜索过程中出错：\n{str(e)}")
        finally:
            self.btn_ai_search.setEnabled(True)
            self.btn_ai_search.setText("🤖 AI搜索")
            self._hide_progress()

    def _get_search_candidates(self, query, items, top_k=20, selected_files=None):
        """第一轮：使用本地搜索获取候选集（支持分词匹配）"""
        query_lower = query.lower().strip()

        # 过滤到选中的文件
        if selected_files:
            items = [item for item in items if len(item) >= 3 and item[2] in selected_files]

        # 将查询拆分为词组（支持2-4个字的词组）
        query_words = []
        # 添加完整查询
        query_words.append(query_lower)
        # 拆分为单个词（2-4字组合）
        for length in range(4, 1, -1):  # 4,3,2
            for i in range(len(query_lower) - length + 1):
                word = query_lower[i:i+length]
                if len(word) >= 2:
                    query_words.append(word)

        # 去重
        query_words = list(set(query_words))

        results = []
        seen_ids = set()

        for item in items:
            if len(item) >= 5:
                item_id = item[0]
                if item_id in seen_ids:
                    continue

                title = item[3] if len(item) > 3 else ""
                content = item[4] if len(item) > 4 else ""
                title_lower = title.lower()
                content_lower = content.lower()

                best_score = 0
                match_reason = ""

                # 检查所有词组
                for word in query_words:
                    # 完整查询匹配（最高分）
                    if word == query_lower:
                        if query_lower in title_lower:
                            best_score = max(best_score, 100)
                            match_reason = "完整标题匹配"
                        elif query_lower in content_lower:
                            best_score = max(best_score, 90)
                            match_reason = "完整内容匹配"
                    # 词组匹配
                    else:
                        if word in title_lower:
                            # 词越长分数越高
                            score = min(70 + len(word) * 5, 85)
                            if score > best_score:
                                best_score = score
                                match_reason = f"词组匹配:{word}"
                        elif word in content_lower:
                            score = min(50 + len(word) * 5, 65)
                            if score > best_score:
                                best_score = score
                                match_reason = f"内容词组:{word}"

                # 字符级匹配（保底）
                if best_score == 0:
                    query_chars = list(query_lower.replace(" ", ""))
                    matched_chars = sum(1 for c in query_chars if c in title_lower or c in content_lower)
                    if matched_chars >= len(query_chars) * 0.5:  # 至少50%字符匹配
                        best_score = 30
                        match_reason = "字符匹配"

                if best_score > 0:
                    seen_ids.add(item_id)
                    results.append({
                        "item_id": item_id,
                        "title": title,
                        "content": content,
                        "file_name": item[2] if len(item) > 2 else "",
                        "hybrid_score": best_score,
                        "match_type": match_reason
                    })

        # 按分数排序，取前 top_k 个
        results = sorted(results, key=lambda x: x.get("hybrid_score", 0), reverse=True)
        
        # 调试信息：检查候选集中是否有重复的标题+内容组合
        title_content_map = {}
        for r in results:
            key = f"{r['title']}|||{r['content'][:100]}"
            if key not in title_content_map:
                title_content_map[key] = []
            title_content_map[key].append(r['item_id'])
        
        duplicate_keys = {k: v for k, v in title_content_map.items() if len(v) > 1}
        if duplicate_keys:
            print(f"[候选集警告] 发现 {len(duplicate_keys)} 组内容重复但 item_id 不同的记录:")
            for key, ids in duplicate_keys.items():
                title = key.split('|||')[0]
                print(f"  标题：{title}, 重复的 item_id: {ids}")
        
        return results[:top_k]

    def _ai_semantic_search(self, query, titles):
        """使用AI对所有标题进行语义匹配打分"""
        import requests
        import json
        import re

        api_key = self.db.get_setting("ai_api_key", "")
        if not api_key:
            QMessageBox.warning(self, "⚠️ 未配置API", "请先配置AI API Key")
            return []

        # 构建标题列表
        title_list = []
        for i, t in enumerate(titles):
            title_list.append(f"【{i+1}】{t['title']}")

        # 如果标题太多，分批处理
        max_titles_per_batch = 30
        all_results = []

        for batch_start in range(0, len(title_list), max_titles_per_batch):
            batch_titles = title_list[batch_start:batch_start + max_titles_per_batch]
            batch_data = titles[batch_start:batch_start + max_titles_per_batch]
            titles_str = "\n".join(batch_titles)

            # 优化后的AI提示词 - 让AI自由生成人性化评价
            prompt = f"""用户搜索关键词："{query}"

以下是知识库中的标题列表（按编号排列）：
{titles_str}

请分析每个标题与用户搜索词的匹配程度，然后生成评价。

要求：
1. 对每个标题判断相关度，只输出相关的（完全不相关的不输出）
2. 输出格式：每行一个，格式为"编号|评价"
   - 评价用最贴切的词语（最多10个字），可以包含换行符\n
   - 评价由AI根据标题和搜索词自由生成，要准确描述匹配程度
   - 例如：非常相关\n、比较符合\n、十\n分\n相\n似等（每个评价最多10个字）
3. 按相关度从高到低排序输出

直接输出结果，不要有其他解释。"""

            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }

                # 判断API类型
                if "sk-" in api_key or api_key.startswith("deepseek-"):
                    url = "https://api.deepseek.com/v1/chat/completions"
                    model = "deepseek-chat"
                else:
                    url = "https://api.openai.com/v1/chat/completions"
                    model = "gpt-3.5-turbo"

                data = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800,
                    "temperature": 0.3
                }

                response = requests.post(url, headers=headers, json=data, timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    ai_response = result["choices"][0]["message"]["content"].strip()
                    print(f"[AI 原始响应] {ai_response[:500]}...")

                    # 解析AI响应
                    batch_results = self._parse_ai_scoring(ai_response, batch_data, batch_start)
                    all_results.extend(batch_results)
                else:
                    print(f"[AI API错误] {response.status_code}: {response.text}")

            except Exception as e:
                print(f"[AI 调用失败] {e}")
                continue

        # 按分数从高到低排序
        all_results.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)

        # 去重
        final_results = []
        seen_contents = set()
        for r in all_results:
            fingerprint = f"{r.get('title', '')}|||{r.get('content', '')[:200]}"
            if fingerprint not in seen_contents:
                seen_contents.add(fingerprint)
                final_results.append(r)

        return final_results

    def _parse_ai_scoring(self, ai_response, batch_data, batch_offset):
        """解析AI的打分结果 - 新格式：编号|人话评价"""
        import re

        results = []
        lines = ai_response.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 尝试匹配新格式: "编号|评价" 
            parts = line.split('|')
            
            if len(parts) >= 2:
                # 提取编号（第一个数字）
                idx = None
                first_part = parts[0].strip()
                if first_part.isdigit():
                    idx = int(first_part) - 1
                    # 评价是第二部分
                    comment = parts[1].strip() if len(parts) > 1 else "有点像"
                else:
                    # 尝试匹配 "编号: 评价" 格式
                    match = re.match(r'(\d+)[:：]\s*(.+)', line)
                    if match:
                        idx = int(match.group(1)) - 1
                        comment = match.group(2).strip()
                
                if idx is not None and 0 <= idx < len(batch_data):
                    if not comment:
                        comment = "有点像"
                    
                    # 根据位置计算分数（排得越前分数越高）
                    position_score = 100 - len(results) * 5
                    score = max(position_score, 50)
                    
                    item = batch_data[idx]
                    results.append({
                        "rank": len(results) + 1,
                        "item_id": item["item_id"],
                        "title": item["title"],
                        "content": item["content"],
                        "file_name": item["file_name"],
                        "hybrid_score": score,
                        "vector_score": 0,
                        "bm25_score": 0,
                        "match_type": comment
                    })

        return results

    def _score_to_comment(self, score):
        """将分数转换为通俗评价"""
        if score >= 90:
            return "这个最像！"
        elif score >= 70:
            return "挺像的"
        elif score >= 50:
            return "有点那意思"
        elif score >= 30:
            return "不太像"
        else:
            return "不相关"

    def _ai_rank_results(self, query, candidates):
        """第二轮：使用 AI 对候选结果进行语义排序"""
        import requests
        import json

        api_key = self.db.get_setting("ai_api_key", "")

        # 构建候选标题列表（只包含标题，不包含内容，减少 token）
        candidate_texts = []
        for i, c in enumerate(candidates):
            candidate_texts.append(f"{i+1}. {c['title']}")

        candidates_str = "\n".join(candidate_texts)

        # 从数据库获取提示词，如果没有则使用默认
        default_prompt = """你是一个智能搜索助手。用户搜索："{query}"

以下是知识库中可能相关的标题列表：
{candidates}

请分析用户搜索意图，从上述列表中选出所有相关的标题。
要求：
1. 只返回标题编号（如：1, 3, 5）
2. 按相关度从高到低排序
3. 如果完全不相关，返回"无"
4. 格式：直接返回数字，用逗号分隔
5. 不要返回重复的编号
6. **尽量返回 5-10 个相关标题，除非确实没有那么多相关的**
7. **宁可多返回一些可能相关的，也不要漏掉可能的答案**"""

        ai_prompt = self.db.get_setting("ai_search_prompt", "")
        if not ai_prompt:
            ai_prompt = default_prompt

        # 替换变量
        prompt = ai_prompt.replace("{query}", query).replace("{candidates}", candidates_str)

        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # 判断API类型
            if "sk-" in api_key or api_key.startswith("deepseek-"):
                url = "https://api.deepseek.com/v1/chat/completions"
                model = "deepseek-chat"
            else:
                url = "https://api.openai.com/v1/chat/completions"
                model = "gpt-3.5-turbo"

            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.3
            }

            response = requests.post(url, headers=headers, json=data, timeout=15)

            if response.status_code == 200:
                result = response.json()
                ai_response = result["choices"][0]["message"]["content"].strip()
                
                # 打印 AI 返回的原始内容（调试用）
                print(f"[AI 原始响应] {ai_response}")

                # 解析 AI 返回的编号
                ranked_results = []
                seen_ai_ids = set()  # 防止AI返回重复编号
                try:
                    # 提取数字（更精确的正则表达式，匹配独立的数字）
                    import re
                    # 使用更精确的模式，匹配逗号分隔的数字或单独的数字
                    numbers = re.findall(r'\b\d+\b', ai_response)
                    
                    # 先去重数字列表（防止 AI 返回重复数字如 "1, 2, 1, 3"）
                    seen_numbers = set()
                    unique_numbers = []
                    for num in numbers:
                        if num not in seen_numbers:
                            seen_numbers.add(num)
                            unique_numbers.append(num)
                    
                    for num_str in unique_numbers:
                        idx = int(num_str) - 1  # 转换为 0-based 索引
                        # 严格检查索引范围
                        if 0 <= idx < len(candidates):
                            candidate = candidates[idx]
                            # 双重检查：确保 item_id 未出现过
                            if candidate["item_id"] in seen_ai_ids:
                                print(f"跳过重复 item_id: {candidate['item_id']}")
                                continue
                            seen_ai_ids.add(candidate["item_id"])
                            ranked_results.append({
                                "rank": len(ranked_results) + 1,
                                "item_id": candidate["item_id"],
                                "title": candidate["title"],
                                "content": candidate["content"],
                                "file_name": candidate["file_name"],
                                "hybrid_score": 95 - len(ranked_results) * 5,  # AI 排序分数递减
                                "vector_score": 0,
                                "bm25_score": 0,
                                "match_type": "AI 语义匹配"
                            })
                        else:
                            # 索引超出范围，跳过并记录
                            print(f"跳过无效索引：{idx + 1} (候选数量：{len(candidates)})")
                except Exception as e:
                    print(f"解析AI响应失败: {e}")

                # 如果 AI 没有返回有效结果，返回原始候选
                if not ranked_results:
                    for c in candidates[:10]:
                        ranked_results.append({
                            "rank": len(ranked_results) + 1,
                            "item_id": c["item_id"],
                            "title": c["title"],
                            "content": c["content"],
                            "file_name": c["file_name"],
                            "hybrid_score": c.get("hybrid_score", 50),
                            "vector_score": 0,
                            "bm25_score": 0,
                            "match_type": c.get("match_type", "候选匹配")
                        })

                # 最终去重检查：只在内容完全相同时才去重
                final_results = []
                final_seen_ids = set()
                final_seen_contents = set()  # 基于内容去重
                
                for r in ranked_results:
                    item_id = r["item_id"]
                    # 创建内容指纹（标题 + 内容前 200 字）
                    content_fingerprint = f"{r['title']}|||{r['content'][:200]}"
                    
                    # 只在内容完全相同时才去重
                    if content_fingerprint in final_seen_contents:
                        print(f"最终去重：移除内容完全重复的记录 (item_id={r['item_id']}, 标题={r['title']})")
                        continue
                    
                    # item_id 重复但内容不同，保留（可能是数据库问题）
                    if item_id in final_seen_ids:
                        print(f"警告：item_id 重复但内容不同，保留 (item_id={item_id}, 标题={r['title']})")
                    
                    final_seen_ids.add(item_id)
                    final_seen_contents.add(content_fingerprint)
                    final_results.append(r)
                
                print(f"[AI 排序完成] 返回 {len(final_results)} 条结果")
                return final_results
            else:
                # API调用失败，返回原始候选
                return candidates[:10]

        except Exception as e:
            print(f"AI排序失败: {e}")
            # 出错时返回原始候选
            return candidates[:10]

    def _display_ai_search_results(self, results):
        """显示 AI 搜索结果"""
        import random
        
        # 根据分数生成随机emoji的映射
        def get_random_emoji(score, comment):
            if score >= 90:
                emojis = ["🔥", "⭐", "💯", "🎯", "✨", "🌟"]
            elif score >= 70:
                emojis = ["👍", "😊", "💪", "🙂", "🤔", "😉"]
            elif score >= 50:
                emojis = ["😐", "🤨", "😄", "🙃", "😌", "😊"]
            else:
                emojis = ["🤔", "🤷", "😶", "🧐", "🙄", "😕"]
            return random.choice(emojis)
        
        # 去重：只在内容完全相同时才去重
        seen_contents = set()  # 基于内容去重
        unique_results = []
        
        for r in results:
            item_id = r.get("item_id")
            # 创建内容指纹（标题 + 内容前 200 字）
            content_fingerprint = f"{r.get('title', '')}|||{r.get('content', '')[:200]}"
            
            # 只在内容完全相同时才去重
            if content_fingerprint in seen_contents:
                print(f"[显示阶段] 检测到内容完全重复，移除：{r.get('title', '')} (item_id={item_id})")
                continue
            
            seen_contents.add(content_fingerprint)
            unique_results.append(r)
        
        # 打印调试信息
        print(f"[显示阶段] 原始结果数：{len(results)}, 去重后结果数：{len(unique_results)}")
        if len(unique_results) < len(results):
            print(f"[显示阶段] 移除了 {len(results) - len(unique_results)} 条内容重复的记录")

        self._is_search_mode = True
        self._search_results = unique_results

        # 清除表格
        self.items_table.clearSpans()
        self.items_table.setRowCount(len(unique_results))

        for row, r in enumerate(unique_results):
            score = r.get("hybrid_score", 0)
            match_type = r.get("match_type", "AI匹配")

            # 生成随机emoji
            emoji = get_random_emoji(score, match_type)
            
            # 列1: 显示AI生成的人话评价 + 随机emoji（支持换行）
            display_text = f"{emoji} {match_type}"
            match_item = QTableWidgetItem(display_text)
            match_item.setForeground(QColor("#e74c3c"))
            match_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.items_table.setItem(row, 0, match_item)

            # 列2: 标题
            title = r.get("title", "")
            title_item = QTableWidgetItem(title)
            title_item.setData(Qt.UserRole, r.get("item_id"))
            title_item.setData(Qt.UserRole + 1, title)
            title_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 1, title_item)

            # 列3: 内容预览
            content = r.get("content", "")
            if len(content) > 100:
                content = content[:100] + "..."
            content_item = QTableWidgetItem(content)
            content_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, content_item)

    def on_search_button_clicked(self):
        """主动搜索按钮点击"""
        query = self.search_input.text().strip()
        if query:
            # 显示进度条
            self._show_progress("搜索中...")
            
            # 执行搜索
            selected_files = self._get_selected_files()
            if selected_files:
                print(f"[DEBUG] 普通搜索选中文件: {selected_files}", flush=True)
            
            self.perform_rag_search(query, selected_files=selected_files if selected_files else None)
            
            # 隐藏进度条
            self._hide_progress()
        else:
            QMessageBox.information(self, "提示", "请先输入关键词")
            self.search_input.setFocus()
    
    def perform_search(self, query, selected_files=None):
        """执行智能搜索 - 基于文本匹配的快速排序"""
        try:
            if not query:
                self._is_search_mode = False
                self._search_results = []
                self.load_data()
                return
            
            # 设置搜索模式标志
            self._is_search_mode = True
            
            all_items = self.db.get_all_knowledge_items()
            if not all_items:
                self.load_data()
                return
            
            # 过滤到选中的文件（没选则搜索全部）
            if selected_files:
                all_items = [item for item in all_items if len(item) >= 3 and item[2] in selected_files]
            
            if not all_items:
                QMessageBox.information(self, "提示", "选中文件中没有知识库内容")
                self._is_search_mode = False
                return
            
            query_lower = query.lower()
            
            # 计算每个知识点的相关性分数
            scored_items = []
            
            for item in all_items:
                item_id, file_path, file_name, title, content, is_active, is_system = item
                title_lower = title.lower()
                content_lower = content.lower()
                
                # 基础分数
                relevance_score = 0.0
                match_details = []
                
                # 1. 标题精确匹配
                if query_lower == title_lower:
                    relevance_score += 100.0
                    match_details.append("标题完全匹配")
                # 2. 标题包含查询（子串匹配）
                elif query_lower in title_lower:
                    relevance_score += 80.0
                    match_details.append("标题包含关键词")
                # 3. 标题分词包含查询（词匹配）
                else:
                    title_words = title_lower.split()
                    for word in title_words:
                        if query_lower in word or word in query_lower:
                            relevance_score += 40.0
                            match_details.append("标题分词匹配")
                            break
                
                # 4. 内容包含查询
                if query_lower in content_lower:
                    relevance_score += 60.0
                    match_details.append("内容包含关键词")
                # 5. 内容分词匹配
                else:
                    content_words = content_lower.split()
                    for word in content_words:
                        if query_lower in word or word in query_lower:
                            relevance_score += 20.0
                            match_details.append("内容分词匹配")
                            break
                
                # 只保留有相关性的结果
                if relevance_score > 0:
                    scored_items.append((relevance_score, match_details, item))
            
            # 按相关性分数排序（从高到低）
            scored_items.sort(key=lambda x: x[0], reverse=True)
            
            # 只取前30个最相关的结果
            top_items = scored_items[:30]
            
            if top_items:
                # 提取item并添加相关性信息
                matched_items = []
                for score, details, item in top_items:
                    # 将相关性分数存入item（用于显示）
                    item_with_score = item + (score, details)
                    matched_items.append(item_with_score)
                
                self._update_display_with_search_results_scored(matched_items)
            else:
                # 无匹配结果，显示提示
                self._show_no_results_message(query)
            
        except Exception as e:
            # 出错时显示所有内容
            self.load_data()
    
    def _get_cached_query_embedding(self, query):
        """获取查询的embedding（带缓存）"""
        if not hasattr(self, '_query_embedding_cache'):
            self._query_embedding_cache = {}
        
        if query not in self._query_embedding_cache:
            if hasattr(self.db, 'rag_model') and self.db.rag_model:
                self._query_embedding_cache[query] = self.db.get_embedding(query)
        
        return self._query_embedding_cache.get(query)
    
    def _show_no_results_message(self, query):
        """显示无结果提示"""
        self.files_list.clear()
        self.items_table.setRowCount(1)
        no_result_item = QTableWidgetItem("未找到匹配结果")
        no_result_item.setTextAlignment(Qt.AlignCenter)
        font = no_result_item.font()
        font.setPointSize(12)
        no_result_item.setFont(font)
        no_result_item.setForeground(QColor("#7f8c8d"))
        self.items_table.setItem(0, 0, no_result_item)
        
        suggest_item = QTableWidgetItem(f'没有找到与"{query}"相关的内容\n建议：\n1. 检查关键词拼写\n2. 尝试使用更简短的关键词\n3. 使用相关词汇搜索')
        suggest_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.items_table.setItem(0, 1, suggest_item)
        self.items_table.setItem(0, 2, QTableWidgetItem(""))
        self.items_table.setSpan(0, 0, 1, 3)
    
    def _cosine_similarity(self, a, b):
        """计算余弦相似度"""
        import numpy as np
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    def _text_search(self, all_items, query):
        """文本模糊搜索（降级方案）"""
        query_lower = query.lower()
        matched_items = []
        for item in all_items:
            item_id, file_path, file_name, title, content, is_active, is_system = item
            # 检查标题和内容是否包含查询词
            if query_lower in title.lower() or query_lower in content.lower():
                matched_items.append(item)
        return matched_items
    
    def _update_display_with_search_results(self, matched_items):
        """根据搜索结果更新显示"""
        # 获取匹配的文件名
        matched_files = set()
        for item in matched_items:
            file_name = item[2]  # file_name 在第3个位置
            matched_files.add(file_name)
        
        # 更新文件列表 - 只显示包含匹配知识点的文件
        self.files_list.clear()
        local_files = []
        if os.path.exists(self.kb_folder):
            for f in os.listdir(self.kb_folder):
                if f.endswith('.txt'):
                    local_files.append(f)
        
        # 获取系统文件标记
        db_files = self.db.get_unique_files()
        db_file_system_map = {}
        for file_path, file_name, is_system in db_files:
            db_file_system_map[file_name] = is_system
        
        # 只显示匹配的文件
        for file_name in sorted(local_files):
            if file_name in matched_files:
                is_system = db_file_system_map.get(file_name, 0)
                self.files_list.addItem(f"📦 {file_name} (系统)" if is_system else f"📁 {file_name}")
        
        # 更新知识点表格 - 显示所有匹配的知识点
        self.items_table.setRowCount(len(matched_items))
        for row, item_data in enumerate(matched_items):
            item_id, file_path, file_name, title, content, is_active, is_system = item_data
            title_display = f"【系统】{title}" if is_system else title
            title_item = QTableWidgetItem(title_display)
            title_item.setData(Qt.UserRole, item_id)
            title_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 1, title_item)
            content_preview = content if content else ""
            content_item = QTableWidgetItem(content_preview)
            content_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, content_item)
    
    def _update_display_with_search_results_scored(self, matched_items):
        """根据搜索结果更新显示 - 带相关性评分"""
        # 获取匹配的文件名
        matched_files = set()
        for item in matched_items:
            file_name = item[2]
            matched_files.add(file_name)
        
        # 更新文件列表 - 显示所有文件，高亮匹配的文件
        self.files_list.clear()
        local_files = []
        if os.path.exists(self.kb_folder):
            for f in os.listdir(self.kb_folder):
                if f.endswith('.txt'):
                    local_files.append(f)
        
        db_files = self.db.get_unique_files()
        db_file_system_map = {}
        for file_path, file_name, is_system in db_files:
            db_file_system_map[file_name] = is_system
        
        for file_name in sorted(local_files):
            is_system = db_file_system_map.get(file_name, 0)
            item_text = f"📦 {file_name} (系统)" if is_system else f"📁 {file_name}"
            self.files_list.addItem(item_text)
            # 如果该文件有匹配结果，高亮显示
            if file_name in matched_files:
                # 找到该文件对应的列表项并高亮
                pass  # 可以添加高亮逻辑
        
        # 如果有匹配的文件，默认选中第一个匹配的文件
        if matched_files:
            first_matched = sorted(matched_files)[0]
            for i in range(self.files_list.count()):
                item = self.files_list.item(i)
                if first_matched in item.text():
                    self.files_list.setCurrentRow(i)
                    break
        
        # 更新知识点表格 - 搜索模式下使用图标显示相关度
        self.items_table.setRowCount(len(matched_items))
        for row, item_data in enumerate(matched_items):
            if len(item_data) >= 9:
                item_id, file_path, file_name, title, content, is_active, is_system, score, details = item_data
                has_score = True
            else:
                item_id, file_path, file_name, title, content, is_active, is_system = item_data
                score = 0
                details = []
                has_score = False
            
            # 标题列 - 始终显示原始标题
            title_display = f"【系统】{title}" if is_system else title

            title_item = QTableWidgetItem(title_display)
            title_item.setData(Qt.UserRole, item_id)
            title_item.setData(Qt.UserRole + 1, title)
            title_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            if has_score and self._is_search_mode:
                if score >= 80:
                    icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
                    color = "#e74c3c"
                    tooltip = "高度相关 ⭐⭐⭐"
                elif score >= 50:
                    icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
                    color = "#f39c12"
                    tooltip = "中度相关 ⭐⭐"
                else:
                    icon = self.style().standardIcon(QStyle.SP_FileIcon)
                    color = "#27ae60"
                    tooltip = "低度相关 ⭐"

                title_item.setIcon(icon)
                title_item.setForeground(QColor(color))

            self.items_table.setItem(row, 1, title_item)

            content_preview = content if content else ""
            if has_score and details and self._is_search_mode:
                detail_text = " | ".join(details[:2])
                content_display = f"[{detail_text}]\n{content_preview}"
            else:
                content_display = content_preview

            content_item = QTableWidgetItem(content_display)
            content_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, content_item)
    
    def reset_search(self):
        """重置搜索 - 快速恢复到默认状态（优化版，不触发文件同步）"""
        # 清空搜索框
        self.search_input.clear()
        # 清除搜索模式标志
        self._is_search_mode = False
        self._search_results = []
        # 清除表格单元格合并
        self.items_table.clearSpans()
        # 快速恢复显示：只刷新当前选中文件的知识点，不触发完整同步
        self._quick_refresh_display()
        # 将焦点设置回搜索框
        self.search_input.setFocus()

    def _quick_refresh_display(self):
        """快速刷新显示 - 不触发文件同步，直接显示当前选中文件的知识点"""
        # 清除表格
        self.items_table.setRowCount(0)
        self.items_table.clearSpans()

        # 获取当前选中的文件
        current_item = self.files_list.currentItem()
        if not current_item:
            # 如果没有选中文件，但有文件列表，选中第一个
            if self.files_list.count() > 0:
                self.files_list.setCurrentRow(0)
                current_item = self.files_list.currentItem()
            else:
                return

        if current_item:
            # 直接显示当前文件的知识点（不触发同步）
            self._display_file_items_quick(current_item)

    def _display_file_items_quick(self, file_item):
        """快速显示文件知识点 - 直接从数据库读取，不同步文件"""
        display_name = file_item.text()
        if "(系统)" in display_name:
            file_name = display_name.replace("(系统)", "").strip().replace("📦", "").replace("📁", "").strip()
        elif display_name.startswith("📦 ") or display_name.startswith("📁 "):
            file_name = display_name.split(" ", 1)[1]
        else:
            file_name = display_name

        # 直接从数据库获取该文件的知识点（不触发文件同步）
        items = self.db.get_all_knowledge_items()
        file_items = [x for x in items if x[2] == file_name]

        # 去重：基于标题+内容
        seen_content = set()
        unique_items = []
        for item in file_items:
            content_key = f"{item[3]}|{item[4]}"  # title|content
            if content_key not in seen_content:
                seen_content.add(content_key)
                unique_items.append(item)

        # 设置表格行数
        self.items_table.setRowCount(len(unique_items))

        for row, item_data in enumerate(unique_items):
            item_id, file_path, file_name, title, content, is_active, is_system = item_data

            # 列1: 匹配（显示"-"表示非搜索模式）
            match_item = QTableWidgetItem("-")
            match_item.setForeground(QColor("#95a5a6"))
            match_item.setTextAlignment(Qt.AlignCenter)
            self.items_table.setItem(row, 0, match_item)

            # 列2: 标题
            title_display = f"【系统】{title}" if is_system else title
            title_item = QTableWidgetItem(title_display)
            title_item.setData(Qt.UserRole, item_id)
            title_item.setData(Qt.UserRole + 1, title)
            title_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 1, title_item)

            # 列3: 内容预览
            content_preview = content if content else ""
            content_item = QTableWidgetItem(content_preview)
            content_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.items_table.setItem(row, 2, content_item)

    def on_cell_clicked(self, row, col):
        """单击单元格复制内容"""
        if col not in [1, 2]:
            return

        item = self.items_table.item(row, col)
        if not item:
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(item.text())

        self.show_copied_toast()

    def show_copied_toast(self):
        """显示已复制提示"""
        table_rect = self.items_table.geometry()
        x = table_rect.x() + table_rect.width() // 2 - 40
        y = table_rect.y() + table_rect.height() - 50

        self.copied_label.move(self.items_table.mapToGlobal(QPoint(x, y)))
        self.copied_label.show()
        self.copied_label.setWindowOpacity(0.6)

        self.copied_fade_timer = QTimer()
        self.copied_fade_timer.timeout.connect(lambda: self.fade_out_toast(0.15))
        self.copied_fade_timer.start(500)

    def fade_out_toast(self, step):
        """渐隐提示"""
        current_opacity = self.copied_label.windowOpacity()
        new_opacity = current_opacity - step
        if new_opacity <= 0:
            self.copied_label.hide()
            self.copied_label.setWindowOpacity(0.6)
            if hasattr(self, 'copied_fade_timer'):
                self.copied_fade_timer.stop()
        else:
            self.copied_label.setWindowOpacity(new_opacity)
            QTimer.singleShot(30, lambda: self.fade_out_toast(step))

    def update_resource_usage(self):
        """更新当前程序的资源使用情况"""
        try:
            cpu_percent = 0
            memory_info = "N/A"
            gpu_info = "N/A"
            
            try:
                # 获取当前进程
                current_process = psutil.Process()
                
                # 获取当前进程的 CPU 使用率
                cpu_percent = current_process.cpu_percent(interval=0.1)
                
                # 获取当前进程的内存使用（单位 MB）
                memory_info_mb = current_process.memory_info().rss / 1024 / 1024
                memory_info = f"{memory_info_mb:.1f}MB"
            except Exception as e:
                memory_info = f"错误: {str(e)[:20]}"
            
            try:
                import subprocess
                result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    gpu_data = result.stdout.strip().split(',')
                    if len(gpu_data) >= 3:
                        gpu_util = gpu_data[0].strip()
                        gpu_mem_used = int(float(gpu_data[1].strip()))
                        gpu_mem_total = int(float(gpu_data[2].strip()))
                        gpu_info = f"GPU:{gpu_util}%"
            except:
                gpu_info = "无GPU"
            
            self.resource_label.setText(f"📊 本进程 CPU:{cpu_percent}% | 内存:{memory_info} | {gpu_info}")
        except:
            self.resource_label.setText("📊 系统资源: 获取失败")

    def check_content_duplicates_advanced(self):
        """高级重复内容检测 - 支持高亮和跳转"""
        try:
            all_items = self.db.get_all_knowledge_items()
            if not all_items:
                QMessageBox.information(self, "检测结果", "知识库为空，无重复内容。")
                return
            
            # 收集重复项（标题+内容双重检测）
            exact_duplicates = []  # 完全重复
            title_duplicates = []  # 标题重复（内容不同）
            content_similars = []  # 内容相似
            
            # 使用字典进行高效查找
            title_map = {}
            content_map = {}
            
            for i, item in enumerate(all_items):
                item_id, file_path, file_name, title, content, is_active, is_system = item
                title_key = title.strip()
                content_key = content.strip()
                
                # 1. 检查完全重复（标题+内容都相同）
                full_key = (title_key, content_key)
                if full_key in content_map:
                    exact_duplicates.append({
                        'type': 'exact',
                        'item': item,
                        'duplicate_with': content_map[full_key],
                        'row': i
                    })
                else:
                    content_map[full_key] = item
                
                # 2. 检查标题重复
                if title_key in title_map:
                    title_duplicates.append({
                        'type': 'title',
                        'item': item,
                        'duplicate_with': title_map[title_key],
                        'row': i
                    })
                else:
                    title_map[title_key] = item
            
            if not exact_duplicates and not title_duplicates and not content_similars:
                QMessageBox.information(self, "检测结果", "未发现重复内容！")
                return
            
            # 显示高级检测报告
            self._show_advanced_duplicate_report(exact_duplicates, title_duplicates, content_similars)
            
        except Exception as e:
            QMessageBox.warning(self, "⚠️ 检测失败", f"重复检测失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _show_advanced_duplicate_report(self, exact_duplicates, title_duplicates, content_similars):
        """显示高级重复检测报告 - 支持高亮和跳转"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🔍 高级重复内容检测报告")
        dialog.resize(900, 700)
        
        layout = QVBoxLayout(dialog)
        
        # 统计信息
        info_text = f"""
        <h3>📊 检测结果统计</h3>
        <table style='width:100%'>
        <tr><td style='color:#e74c3c'><b>🔴 完全重复:</b></td><td>{len(exact_duplicates)} 条</td></tr>
        <tr><td style='color:#f39c12'><b>🟡 标题重复:</b></td><td>{len(title_duplicates)} 条</td></tr>
        <tr><td style='color:#3498db'><b>🔵 内容相似:</b></td><td>{len(content_similars)} 条</td></tr>
        </table>
        <p style='font-size:11px;color:#7f8c8d'>提示：点击"定位"按钮可跳转到重复内容位置并高亮显示</p>
        """
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 创建表格显示重复项
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["类型", "标题", "内容预览", "所在文件", "操作", "ID"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        
        all_duplicates = exact_duplicates + title_duplicates + content_similars
        table.setRowCount(len(all_duplicates))
        
        for row, dup in enumerate(all_duplicates):
            item = dup['item']
            item_id, file_path, file_name, title, content, is_active, is_system = item
            dup_type = dup['type']
            
            # 类型列
            if dup_type == 'exact':
                type_item = QTableWidgetItem("🔴 完全重复")
                type_item.setBackground(QColor("#ffebee"))
                type_item.setForeground(QColor("#c62828"))
            elif dup_type == 'title':
                type_item = QTableWidgetItem("🟡 标题重复")
                type_item.setBackground(QColor("#fff3e0"))
                type_item.setForeground(QColor("#ef6c00"))
            else:
                type_item = QTableWidgetItem("🔵 内容相似")
                type_item.setBackground(QColor("#e3f2fd"))
                type_item.setForeground(QColor("#1565c0"))
            table.setItem(row, 0, type_item)
            
            # 标题列
            title_item = QTableWidgetItem(title)
            if dup_type in ['exact', 'title']:
                title_item.setBackground(QColor("#ffebee"))
            table.setItem(row, 1, title_item)
            
            # 内容预览列
            content_preview = content if content else ""
            content_item = QTableWidgetItem(content_preview)
            if dup_type == 'exact':
                content_item.setBackground(QColor("#ffebee"))
            table.setItem(row, 2, content_item)
            
            # 文件名列
            file_item = QTableWidgetItem(file_name)
            table.setItem(row, 3, file_item)
            
            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            
            locate_btn = QPushButton("🔍 定位")
            locate_btn.setStyleSheet("background-color: #3498db; color: white; padding: 2px 8px; font-size: 10px;")
            locate_btn.clicked.connect(lambda checked, id=item_id: self._locate_and_highlight_duplicate(id, dialog))
            btn_layout.addWidget(locate_btn)
            
            delete_btn = QPushButton("🗑️ 删除")
            delete_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 2px 8px; font-size: 10px;")
            delete_btn.clicked.connect(lambda checked, id=item_id: self._delete_duplicate_and_refresh(id, dialog))
            btn_layout.addWidget(delete_btn)
            
            btn_layout.addStretch()
            table.setCellWidget(row, 4, btn_widget)
            
            # ID列（隐藏）
            id_item = QTableWidgetItem(str(item_id))
            table.setItem(row, 5, id_item)
        
        layout.addWidget(table)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        
        highlight_all_btn = QPushButton("🔦 高亮显示所有重复")
        highlight_all_btn.setStyleSheet("background-color: #9b59b6; color: white; padding: 5px 15px;")
        highlight_all_btn.clicked.connect(lambda: self._highlight_all_duplicates(all_duplicates))
        btn_layout.addWidget(highlight_all_btn)
        
        auto_clean_btn = QPushButton("🧹 自动清理完全重复")
        auto_clean_btn.setStyleSheet("background-color: #e67e22; color: white; padding: 5px 15px;")
        auto_clean_btn.clicked.connect(lambda: self._auto_clean_exact_duplicates(exact_duplicates, dialog))
        btn_layout.addWidget(auto_clean_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def _locate_and_highlight_duplicate(self, item_id, parent_dialog=None):
        """定位并高亮显示重复内容"""
        # 关闭检测报告对话框
        if parent_dialog:
            parent_dialog.accept()
        
        # 在主表格中查找并选中该项
        for row in range(self.items_table.rowCount()):
            item = self.items_table.item(row, 0)
            if item and item.data(Qt.UserRole) == item_id:
                # 选中该行
                self.items_table.selectRow(row)
                self.items_table.scrollToItem(item)
                
                # 高亮显示（设置背景色）
                for col in range(3):
                    cell_item = self.items_table.item(row, col)
                    if cell_item:
                        cell_item.setBackground(QColor("#ffeb3b"))  # 黄色高亮
                
                # 3秒后取消高亮
                QTimer.singleShot(3000, lambda: self._clear_highlight(row))
                break
    
    def _clear_highlight(self, row):
        """清除高亮"""
        for col in range(3):
            item = self.items_table.item(row, col)
            if item:
                item.setBackground(QColor("white"))
    
    def _delete_duplicate_and_refresh(self, item_id, parent_dialog):
        """删除重复项并刷新报告"""
        # 先获取重复项的信息用于文件同步删除
        rows = self.db.safe_fetchall("SELECT file_path, title, content FROM knowledge_base WHERE id=?", (item_id,))
        if rows:
            file_path, title, content = rows[0][0], rows[0][1], rows[0][2]
            
            reply = QMessageBox.question(self, "确认删除", f"确定要删除这条重复内容吗？\n\n标题: {title}\n\n同时会从本地文件同步删除。", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                # 同步删除本地文件中的内容
                if file_path and os.path.exists(file_path):
                    try:
                        self._sync_enabled = False
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        # 查找【标题】行并删除标题+内容
                        title_pattern = f"【{title}】"
                        title_line_idx = -1
                        for i, line in enumerate(lines):
                            if line.strip() == title_pattern:
                                title_line_idx = i
                                break
                        
                        if title_line_idx >= 0:
                            # 找到标题，确定内容范围
                            content_start = title_line_idx
                            content_end = len(lines)
                            for i in range(title_line_idx + 1, len(lines)):
                                if lines[i].strip().startswith("【") and lines[i].strip().endswith("】"):
                                    content_end = i
                                    break
                            
                            # 删除标题和内容行
                            new_lines = lines[:content_start] + lines[content_end:]
                            
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.writelines(new_lines)
                        
                        self._sync_enabled = True
                        QTimer.singleShot(100, self._reenable_sync)
                    except Exception as e:
                        self._sync_enabled = True
                        print(f"同步删除到文件失败: {e}")
                
                # 删除数据库记录
                self.db.delete_knowledge_item(item_id)
                self.load_data()
                
                if parent_dialog:
                    parent_dialog.accept()
                    # 重新检测
                    self.check_content_duplicates_advanced()
    
    def _highlight_all_duplicates(self, all_duplicates):
        """在主表格中高亮显示所有重复项"""
        duplicate_ids = [dup['item'][0] for dup in all_duplicates]
        
        highlighted_count = 0
        for row in range(self.items_table.rowCount()):
            item = self.items_table.item(row, 0)
            if item and item.data(Qt.UserRole) in duplicate_ids:
                for col in range(3):
                    cell_item = self.items_table.item(row, col)
                    if cell_item:
                        cell_item.setBackground(QColor("#ffeb3b"))
                highlighted_count += 1
        
        QMessageBox.information(self, "高亮完成", f"已在主界面高亮显示 {highlighted_count} 条重复内容。\n\n3秒后自动清除高亮。")
        
        # 3秒后清除所有高亮
        QTimer.singleShot(3000, self._clear_all_highlights)
    
    def _clear_all_highlights(self):
        """清除所有高亮"""
        for row in range(self.items_table.rowCount()):
            for col in range(3):
                item = self.items_table.item(row, col)
                if item:
                    item.setBackground(QColor("white"))
    
    def _auto_clean_exact_duplicates(self, exact_duplicates, parent_dialog):
        """自动清理完全重复项"""
        if not exact_duplicates:
            QMessageBox.information(self, "提示", "没有完全重复的内容需要清理。")
            return
        
        reply = QMessageBox.question(
            self,
            "确认自动清理",
            f"将删除 {len(exact_duplicates)} 条完全重复的内容（保留第一条）。\n\n⚠️ 同时会从本地文件同步删除！\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        deleted_count = 0
        failed_items = []
        
        for dup in exact_duplicates:
            item = dup['item']
            item_id = item[0]
            file_path = item[1]
            title = item[3]
            
            # 同步删除本地文件中的内容
            if file_path and os.path.exists(file_path):
                try:
                    self._sync_enabled = False
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    # 查找【标题】行并删除标题+内容
                    title_pattern = f"【{title}】"
                    title_line_idx = -1
                    for i, line in enumerate(lines):
                        if line.strip() == title_pattern:
                            title_line_idx = i
                            break
                    
                    if title_line_idx >= 0:
                        # 找到标题，确定内容范围
                        content_start = title_line_idx
                        content_end = len(lines)
                        for i in range(title_line_idx + 1, len(lines)):
                            if lines[i].strip().startswith("【") and lines[i].strip().endswith("】"):
                                content_end = i
                                break
                        
                        # 删除标题和内容行
                        new_lines = lines[:content_start] + lines[content_end:]
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(new_lines)
                    
                    self._sync_enabled = True
                    QTimer.singleShot(100, self._reenable_sync)
                except Exception as e:
                    self._sync_enabled = True
                    failed_items.append(title)
                    print(f"同步删除到文件失败: {e}")
            
            # 删除数据库记录
            self.db.delete_knowledge_item(item_id)
            deleted_count += 1
        
        # 显示清理结果
        if failed_items:
            QMessageBox.warning(
                self, 
                "✅ 清理完成（部分失败）", 
                f"已删除 {deleted_count} 条完全重复内容。\n\n以下项目文件同步失败：\n" + "\n".join(failed_items)
            )
        else:
            QMessageBox.information(self, "✅ 清理完成", f"已自动删除 {deleted_count} 条完全重复内容，并已同步到本地文件。")
        
        self.load_data()
        
        if parent_dialog:
            parent_dialog.accept()


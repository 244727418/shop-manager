# -*- coding: utf-8 -*-
"""商品规格管理与毛利计算器对话框"""
import os
import re
import json
import time
import requests
from datetime import datetime, timedelta, date

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QWidget, QLineEdit, QSpinBox,
    QComboBox, QCheckBox, QFrame, QGridLayout, QAbstractItemView, QFileDialog,
    QProgressDialog, QApplication, QInputDialog, QTextEdit, QScrollArea,
    QGraphicsOpacityEffect, QStyledItemDelegate, QStyleOptionViewItem, QStyle,
    QPlainTextEdit, QSlider, QSplitter, QButtonGroup, QDateEdit, QMenu, QAction,
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QSize, QPropertyAnimation, QEasingCurve, QDate, QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import QColor, QPixmap, QIcon, QIntValidator, QKeySequence, QPalette, QFontMetrics

try:
    from ..delegates import CenterAlignDelegate, WeightDelegate
except ImportError:
    from delegates import CenterAlignDelegate, WeightDelegate

try:
    from .profit import ProfitCalculatorDialog
except ImportError:
    from profit import ProfitCalculatorDialog

try:
    from .api_config import SpecPromptEditorDialog, ProductPromptEditorDialog
except ImportError:
    from api_config import SpecPromptEditorDialog, ProductPromptEditorDialog


class InlineTextEditDelegate(QStyledItemDelegate):
    """用于保证编辑态与展示态视觉一致的单行文本代理。"""
    def __init__(self, alignment, max_length=None, wrap_display=False, parent=None):
        super().__init__(parent)
        self.alignment = alignment
        self.max_length = max_length
        self.wrap_display = wrap_display

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.displayAlignment = self.alignment
        opt.textElideMode = Qt.ElideNone
        if self.wrap_display:
            opt.features |= QStyleOptionViewItem.WrapText
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        if not self.wrap_display:
            return base

        text = index.data(Qt.DisplayRole) or ""
        if not text:
            return base

        column_width = option.rect.width()
        if column_width <= 0 and option.widget:
            column_width = option.widget.columnWidth(index.column())
        if column_width <= 0:
            return base

        wrapped = option.fontMetrics.boundingRect(
            0, 0, max(1, column_width), 10000,
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
            str(text)
        )
        return QSize(base.width(), max(base.height(), wrapped.height() + 2))

    def createEditor(self, parent, option, index):
        if self.wrap_display:
            editor = QPlainTextEdit(parent)
            editor.setFrameStyle(0)
            editor.setFont(option.font)
            editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            editor.document().setDocumentMargin(1)
            editor.setStyleSheet(
                "QPlainTextEdit {"
                "padding: 1px; "
                "margin: 0px; "
                "border: none; "
                "background-color: #eaf8ee; "
                "font-size: 13px; "
                "font-family: YouYuan, 'Microsoft YaHei UI', sans-serif; "
                "font-weight: bold; "
                "}"
            )
            return editor

        editor = QLineEdit(parent)
        editor.setFrame(False)
        editor.setAlignment(self.alignment)
        editor.setFont(option.font)
        editor.setTextMargins(1, 0, 1, 0)
        if self.max_length is not None:
            editor.setMaxLength(self.max_length)
        editor.setStyleSheet(
            "QLineEdit {"
            "padding: 1px; "
            "margin: 0px; "
            "border: none; "
            "background-color: #eaf8ee; "
            "font-size: 13px; "
            "font-family: YouYuan, 'Microsoft YaHei UI', sans-serif; "
            "font-weight: bold; "
            "}"
        )
        return editor

    def setEditorData(self, editor, index):
        text = index.data(Qt.DisplayRole) or ""
        if isinstance(editor, QPlainTextEdit):
            editor.setPlainText(text)
        else:
            editor.setText(text)

    def setModelData(self, editor, model, index):
        text = editor.toPlainText() if isinstance(editor, QPlainTextEdit) else editor.text()
        if self.max_length is not None and len(text) > self.max_length:
            text = text[:self.max_length]
        model.setData(index, text, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect
        if self.wrap_display and rect.width() > 2 and rect.height() > 2:
            # 显示优先：轻微内缩，匹配常态 CE_ItemViewItem 的文本起点
            rect = rect.adjusted(1, 1, -1, -1)
        editor.setGeometry(rect)


class SpecImageCell(QLabel):
    """规格图缩略图单元格，负责接收粘贴和双击查看。"""
    def __init__(self, table, paste_callback, view_callback, parent=None):
        super().__init__(parent)
        self.table = table
        self.paste_callback = paste_callback
        self.view_callback = view_callback
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(54, 46)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("鼠标悬停后 Ctrl+V 粘贴规格图；双击查看大图")
        self.setStyleSheet("""
            QLabel {
                background: #f8f9fa;
                border: 1px solid #d9dee5;
                border-radius: 4px;
                color: #8c98a4;
                font-size: 11px;
                font-weight: bold;
            }
        """)

    def _current_row(self):
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, ProductSpecDialog.COL_SPEC_IMAGE) is self:
                return row
        return -1

    def mousePressEvent(self, event):
        row = self._current_row()
        if row >= 0:
            self.table.setCurrentCell(row, ProductSpecDialog.COL_SPEC_IMAGE)
        self.setFocus(Qt.MouseFocusReason)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        row = self._current_row()
        if row >= 0:
            self.table.setCurrentCell(row, ProductSpecDialog.COL_SPEC_IMAGE)
        self.setFocus(Qt.MouseFocusReason)
        super().enterEvent(event)

    def mouseDoubleClickEvent(self, event):
        row = self._current_row()
        if row >= 0:
            self.view_callback(row)
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            row = self._current_row()
            if row >= 0:
                self.paste_callback(row)
            event.accept()
            return
        super().keyPressEvent(event)


class SpecImageViewerDialog(QDialog):
    """可滚轮缩放的规格图查看器。"""
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self.scale_factor = 1.0
        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_h = 0
        self._drag_start_v = 0
        self.setWindowTitle("规格图查看")
        self.resize(760, 620)

        layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.viewport().setCursor(Qt.OpenHandCursor)
        self.scroll_area.viewport().installEventFilter(self)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setBackgroundRole(QPalette.Base)
        self.image_label.setCursor(Qt.OpenHandCursor)
        self.image_label.installEventFilter(self)
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)
        self._refresh_image()
        self._resize_to_image()
        QTimer.singleShot(0, self._center_image_view)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            self._zoom_by_wheel(event)
            return True
        if obj in (self.scroll_area.viewport(), self.image_label):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._dragging = True
                self._drag_start_pos = event.globalPos()
                self._drag_start_h = self.scroll_area.horizontalScrollBar().value()
                self._drag_start_v = self.scroll_area.verticalScrollBar().value()
                self.scroll_area.viewport().setCursor(Qt.ClosedHandCursor)
                self.image_label.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return True
            if event.type() == QEvent.MouseMove and self._dragging and self._drag_start_pos is not None:
                delta = event.globalPos() - self._drag_start_pos
                self.scroll_area.horizontalScrollBar().setValue(self._drag_start_h - delta.x())
                self.scroll_area.verticalScrollBar().setValue(self._drag_start_v - delta.y())
                event.accept()
                return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._dragging:
                self._dragging = False
                self._drag_start_pos = None
                self.scroll_area.viewport().setCursor(Qt.OpenHandCursor)
                self.image_label.setCursor(Qt.OpenHandCursor)
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self._zoom_by_wheel(event)
            return
        super().wheelEvent(event)

    def _zoom_by_wheel(self, event):
        if event.angleDelta().y() > 0:
            self.scale_factor *= 1.15
        else:
            self.scale_factor *= 0.85
        self.scale_factor = max(0.2, min(8.0, self.scale_factor))
        self._refresh_image()
        self._center_image_view()
        event.accept()

    def _refresh_image(self):
        if self.original_pixmap.isNull():
            return
        base_size = self.original_pixmap.size()
        size = QSize(
            max(1, int(base_size.width() * self.scale_factor)),
            max(1, int(base_size.height() * self.scale_factor))
        )
        scaled = self.original_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())

    def _resize_to_image(self):
        if self.original_pixmap.isNull():
            return
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        image_size = self.original_pixmap.size()
        target_width = image_size.width() + 42
        target_height = image_size.height() + 62
        if available:
            target_width = min(target_width, int(available.width() * 0.85))
            target_height = min(target_height, int(available.height() * 0.85))
        self.resize(max(320, target_width), max(240, target_height))

    def _center_image_view(self):
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue((h_bar.maximum() + h_bar.minimum()) // 2)
        v_bar.setValue((v_bar.maximum() + v_bar.minimum()) // 2)


class ProductSpecDialog(QDialog):
    """商品规格管理与毛利计算器"""
    SPEC_PROMPT_VERSION = "sku_axis_product_memo_deterrence_v4"
    COL_AI = 0
    COL_SPEC_IMAGE = 1
    COL_SPEC_NAME = 2
    COL_SPEC_NAME_2 = 3
    COL_SPEC_CODE = 4
    COL_COST = 5
    COL_SALE_PRICE = 6
    COL_FINAL_PRICE = 7
    COL_MARGIN_RATE = 8
    COL_GROSS_PROFIT = 9
    COL_WEIGHT = 10
    COL_WEIGHT_COMPARE = 11
    COL_ORDER_COUNT = 12
    COL_ORDER_COMPARE = 13
    COL_REFUND_ORDERS = 14
    COL_REFUND_RATIO = 15
    SPEC_TABLE_COLUMN_COUNT = 16
    EDITABLE_SPEC_BG = QColor("#eaf8ee")

    def __init__(self, db_manager, product_id, product_code, product_name, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.product_id = product_id
        self.product_code = product_code
        self.product_name = product_name
        self.main_app = parent
        self._ensure_ai_spec_prompt_defaults()
        self.two_level_specs = self.db.get_setting(f"product_spec_two_level_{self.product_id}", "0") == "1"
        self.setWindowTitle(f"📦 规格与毛利管理 - {product_name}")
        self.setWindowFlags(Qt.Window)
        self.resize(1720, 930)
        self.setMinimumWidth(1500)
        self._code_click_timer = QTimer(self)
        self._code_click_timer.setSingleShot(True)
        self._code_click_timer.timeout.connect(self._copy_product_code_to_clipboard)
        self._copy_toast = None
        self._copy_toast_animations = []
        self.roi_input_mode = "roi"
        self._roi_bid_syncing = False
        self._initial_roi_input_mode = self.roi_input_mode
        self._roi_bid_manual_source = None
        self._roi_bid_mode_switches = []
        self.init_ui()
        self.is_balancing = False  # 【新增】防止递归死循环的锁
        # 【新增】用于存储加载时的原始规格编码集合，用于后续对比谁被删除了
        self.original_spec_codes = set() 
        # 🔑【新增】保存当前选中的行
        self._saved_current_row = 0
        self.load_specs()
        self.update_total_orders_label()
        self._col_resize_timer = QTimer(self)
        self._col_resize_timer.setSingleShot(True)
        self._col_resize_timer.timeout.connect(self._save_col_width_to_db)
        QTimer.singleShot(100, self.delayed_refresh)

    def closeEvent(self, event):
        self.load_specs()
        super().closeEvent(event)

    def _ensure_ai_spec_prompt_defaults(self):
        """一次性升级规格优化提示词，避免旧保存模板继续生效。"""
        try:
            if self.db.get_setting("ai_spec_prompt_version", "") == self.SPEC_PROMPT_VERSION:
                return
            self.db.set_setting("ai_spec_base_prompt", self._get_default_spec_base_prompt())
            self.db.set_setting("ai_spec_conversion_axis_prompt", self._get_default_conversion_axis_prompt())
            self.db.set_setting("ai_spec_price_audience_prompt", self._get_default_price_audience_prompt())
            self.db.set_setting("ai_spec_prompt_version", self.SPEC_PROMPT_VERSION)
        except Exception as e:
            print(f"升级规格优化提示词失败: {e}")
        

    def delayed_refresh(self):
        """延迟刷新表格"""
        try:
            self.table.resizeRowsToContents()
            self._resize_spec_table_columns_to_content()
            self.table.viewport().update()
            if hasattr(self, 'lbl_gross_break_even'):
                self.calculate_roi_metrics()
        except:
            pass

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.main_splitter = QSplitter(Qt.Horizontal, self)
        left_widget = QWidget()
        layout = QVBoxLayout(left_widget)
        layout.setContentsMargins(8, 8, 6, 8)
        self.main_splitter.addWidget(left_widget)
        root_layout.addWidget(self.main_splitter)

        # 调试标签
        debug_widget = QWidget()
        debug_layout = QHBoxLayout(debug_widget)
        debug_layout.setContentsMargins(5, 2, 5, 2)
        debug_label = QLabel(f"[DEBUG] 文件: dialogs/product_spec.py")
        debug_label.setStyleSheet("background-color: #ffeb3b; color: #000; font-size: 11px; padding: 2px 8px;")
        debug_label.setCursor(Qt.PointingHandCursor)
        debug_label.setToolTip("点击复制文件路径")
        debug_layout.addWidget(debug_label)
        debug_layout.addStretch()
        layout.addWidget(debug_widget)

        def copy_path():
            clipboard = QApplication.clipboard()
            clipboard.setText("e:/zhuomian/shop/manager/dialogs/product_spec.py")
        debug_label.mousePressEvent = lambda e: copy_path()

        # 顶部信息
        info_widget = QWidget()
        info_layout = QHBoxLayout(info_widget)
        info_layout.setContentsMargins(10, 10, 10, 10)
        
        # 商品ID（用户手动输入的链接ID）
        self.lbl_code = QLabel(f"商品ID: <b style='color:#4a90e2;'>{self.product_code}</b>")
        self.lbl_code.setStyleSheet("font-size: 14px; padding: 0 10px;")
        self.lbl_code.setCursor(Qt.PointingHandCursor)
        self.lbl_code.setToolTip("单击复制商品ID，双击修改商品ID")
        
        # 商品标题
        self.lbl_name = QLabel(f"商品标题: <b>{self.product_name}</b>")
        self.lbl_name.setStyleSheet("font-size: 14px; padding: 0 10px;")
        self.lbl_name.setCursor(Qt.PointingHandCursor)
        self.lbl_name.setToolTip("双击修改商品标题")
        
        info_layout.addWidget(self.lbl_code)
        info_layout.addWidget(self.lbl_name)
        info_layout.addStretch()
        
        info_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(info_widget)
        
        # 安装事件过滤器
        self.lbl_code.installEventFilter(self)
        self.lbl_name.installEventFilter(self)
        
        # 【促销标签设置板块】优惠券/新客立减/限时限量购/营销活动
        # ===================================================================
        promo_widget = QWidget()
        promo_layout = QVBoxLayout(promo_widget)
        promo_layout.setContentsMargins(8, 5, 8, 5)
        promo_layout.setSpacing(5)
        
        promo_title = QLabel("🎯 促销标签设置")
        promo_title.setStyleSheet("font-weight: bold; font-size: 16px; color: #2c3e50; padding-bottom: 3px;")
        promo_layout.addWidget(promo_title)

        promo_h_layout = QHBoxLayout()
        promo_h_layout.setSpacing(20)
        promo_h_layout.setAlignment(Qt.AlignLeft)

        # ===== 优惠券 =====
        coupon_widget = QWidget()
        coupon_h = QHBoxLayout(coupon_widget)
        coupon_h.setContentsMargins(0, 0, 0, 0)
        coupon_h.setSpacing(5)

        cp_icon = QLabel()
        cp_icon.setFixedSize(16, 16)
        cp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons", "coupon.svg")
        if os.path.exists(cp_path):
            cp_icon.setPixmap(QPixmap(cp_path).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        cp_text = QLabel("优惠券")
        cp_text.setStyleSheet("font-weight: bold; color: #d81e06; font-size: 12px;")

        self.coupon_input = QLineEdit()
        self.coupon_input.setPlaceholderText("金额...")
        self.coupon_input.setFixedWidth(70)
        self.coupon_input.setStyleSheet("padding: 3px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;")
        self.coupon_input.setValidator(QIntValidator(0, 99999, self))
        self.coupon_input.textChanged.connect(self.on_discount_changed)
        
        coupon_h.addWidget(cp_icon)
        coupon_h.addWidget(cp_text)
        coupon_h.addWidget(self.coupon_input)
        
        # ===== 新客立减 =====
        nc_widget = QWidget()
        nc_h = QHBoxLayout(nc_widget)
        nc_h.setContentsMargins(0, 0, 0, 0)
        nc_h.setSpacing(5)

        nc_icon = QLabel()
        nc_icon.setFixedSize(16, 16)
        nc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons", "new_customer.svg")
        if os.path.exists(nc_path):
            nc_icon.setPixmap(QPixmap(nc_path).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        nc_text = QLabel("新客立减")
        nc_text.setStyleSheet("font-weight: bold; color: #9b59b6; font-size: 12px;")

        self.new_customer_input = QLineEdit()
        self.new_customer_input.setPlaceholderText("金额...")
        self.new_customer_input.setFixedWidth(70)
        self.new_customer_input.setStyleSheet("padding: 3px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;")
        self.new_customer_input.setValidator(QIntValidator(0, 99999, self))
        self.new_customer_input.textChanged.connect(self.on_discount_changed)
        
        nc_h.addWidget(nc_icon)
        nc_h.addWidget(nc_text)
        nc_h.addWidget(self.new_customer_input)
        
        # ===== 限时限量购 =====
        lt_widget = QWidget()
        lt_v = QVBoxLayout(lt_widget)
        lt_v.setContentsMargins(0, 0, 0, 0)
        lt_v.setSpacing(3)

        self.btn_limited_time = QPushButton()
        self.btn_limited_time.setFixedSize(35, 35)
        lt_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons", "limited-time.svg")
        if os.path.exists(lt_icon_path):
            self.btn_limited_time.setIcon(QIcon(lt_icon_path))
        self.btn_limited_time.setIconSize(QSize(28, 28))
        self.btn_limited_time.setStyleSheet("""
            QPushButton { border: 2px solid #e74c3c; background-color: transparent; border-radius: 8px; }
            QPushButton:checked { background-color: #e74c3c; }
        """)
        self.btn_limited_time.setCheckable(True)
        self.btn_limited_time.clicked.connect(self.update_tag_button_styles)

        lt_v.addWidget(self.btn_limited_time, 0, Qt.AlignCenter)
        
        # ===== 营销活动 =====
        mk_widget = QWidget()
        mk_v = QVBoxLayout(mk_widget)
        mk_v.setContentsMargins(0, 0, 0, 0)
        mk_v.setSpacing(3)

        self.btn_marketing = QPushButton()
        self.btn_marketing.setFixedSize(35, 35)
        mk_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons", "marketing.svg")
        if os.path.exists(mk_icon_path):
            self.btn_marketing.setIcon(QIcon(mk_icon_path))
        self.btn_marketing.setIconSize(QSize(28, 28))
        self.btn_marketing.setStyleSheet("""
            QPushButton { border: 2px solid #9b59b6; background-color: transparent; border-radius: 8px; }
            QPushButton:checked { background-color: #9b59b6; }
        """)
        self.btn_marketing.setCheckable(True)
        self.btn_marketing.clicked.connect(self.update_tag_button_styles)

        mk_v.addWidget(self.btn_marketing, 0, Qt.AlignCenter)
        
        # ===== 最大优惠 =====
        max_widget = QWidget()
        max_v = QVBoxLayout(max_widget)
        max_v.setContentsMargins(0, 0, 0, 0)
        max_v.setSpacing(3)

        self.max_discount_label = QLabel("¥0.00")
        self.max_discount_label.setStyleSheet("font-weight: bold; font-size: 18px; color: #27ae60; padding: 5px 12px; background-color: #e8f8f5; border-radius: 8px; border: 2px solid #27ae60;")
        self.max_discount_label.setAlignment(Qt.AlignCenter)

        max_v.addWidget(self.max_discount_label, 0, Qt.AlignCenter)
        
        # 添加到主水平布局
        promo_h_layout.addWidget(coupon_widget)
        promo_h_layout.addWidget(nc_widget)
        promo_h_layout.addWidget(lt_widget)
        promo_h_layout.addWidget(mk_widget)
        promo_h_layout.addWidget(max_widget)
        promo_h_layout.addStretch()
        
        promo_layout.addLayout(promo_h_layout)
        
        promo_widget.setStyleSheet("background-color: #fff3cd; border-radius: 1px; border: 1px solid #ffc107;")
        layout.addWidget(promo_widget)
        
        # 投产比分析模块
        roi_widget = QWidget()
        roi_layout = QVBoxLayout(roi_widget)
        roi_layout.setContentsMargins(10, 10, 10, 10)
        
        roi_title = QLabel("📈 投产比分析")
        roi_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        roi_layout.addWidget(roi_title)
        
        roi_grid = QGridLayout()
        
        roi_grid.addWidget(QLabel("当前投产:"), 0, 0)
        
        # 创建水平布局容器用于当前投产输入框和按钮
        current_roi_container = QWidget()
        current_roi_layout = QHBoxLayout(current_roi_container)
        current_roi_layout.setContentsMargins(0, 0, 0, 0)
        current_roi_layout.setSpacing(5)
        
        self.current_roi_input = QLineEdit()
        self.current_roi_input.setPlaceholderText("输入当前投产...")
        self.current_roi_input.setFixedWidth(120)
        self.current_roi_input.setStyleSheet("padding: 5px; border: 1px solid #ddd; border-radius: 3px;")
        self.current_roi_input.textChanged.connect(self.on_current_roi_changed)
        self.current_roi_input.installEventFilter(self)
        current_roi_layout.addWidget(self.current_roi_input)
        
        # 添加涨5%按钮
        self.btn_increase_5 = QPushButton("涨5%")
        self.btn_increase_5.setFixedWidth(60)
        self.btn_increase_5.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 5px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.btn_increase_5.clicked.connect(self.increase_roi_5_percent)
        current_roi_layout.addWidget(self.btn_increase_5)
        
        # 添加降5%按钮
        self.btn_decrease_5 = QPushButton("降5%")
        self.btn_decrease_5.setFixedWidth(60)
        self.btn_decrease_5.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 5px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        self.btn_decrease_5.clicked.connect(self.decrease_roi_5_percent)
        current_roi_layout.addWidget(self.btn_decrease_5)
        
        roi_grid.addWidget(current_roi_container, 0, 1)

        roi_grid.addWidget(QLabel("成交出价:"), 1, 0)

        bid_container = QWidget()
        bid_layout = QHBoxLayout(bid_container)
        bid_layout.setContentsMargins(0, 0, 0, 0)
        bid_layout.setSpacing(5)

        self.transaction_bid_input = QLineEdit()
        self.transaction_bid_input.setPlaceholderText("自动计算...")
        self.transaction_bid_input.setFixedWidth(120)
        self.transaction_bid_input.textChanged.connect(self.on_transaction_bid_changed)
        self.transaction_bid_input.installEventFilter(self)
        bid_layout.addWidget(self.transaction_bid_input)

        self.btn_bid_increase_5 = QPushButton("涨5%")
        self.btn_bid_increase_5.setFixedWidth(60)
        self.btn_bid_increase_5.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 5px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #219a52; }
            QPushButton:pressed { background-color: #1e8449; }
        """)
        self.btn_bid_increase_5.clicked.connect(self.increase_bid_5_percent)
        bid_layout.addWidget(self.btn_bid_increase_5)

        self.btn_bid_decrease_5 = QPushButton("降5%")
        self.btn_bid_decrease_5.setFixedWidth(60)
        self.btn_bid_decrease_5.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 5px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:pressed { background-color: #a93226; }
        """)
        self.btn_bid_decrease_5.clicked.connect(self.decrease_bid_5_percent)
        bid_layout.addWidget(self.btn_bid_decrease_5)

        roi_grid.addWidget(bid_container, 1, 1)
        
        roi_grid.addWidget(QLabel("退货率 (%):"), 0, 2)
        self.return_rate_input = QLineEdit()
        self.return_rate_input.setPlaceholderText("0-100...")
        self.return_rate_input.setFixedWidth(80)
        self.return_rate_input.setStyleSheet("padding: 5px; border: 1px solid #ddd; border-radius: 3px;")
        self.return_rate_input.textChanged.connect(self.on_return_rate_changed)
        roi_grid.addWidget(self.return_rate_input, 0, 3)

        roi_grid.addWidget(QLabel("毛保本投产:"), 0, 4)
        self.lbl_gross_break_even = QLabel("0.00")
        self.lbl_gross_break_even.setStyleSheet("font-weight: bold; color: #e74c3c; background-color: #fdeaea; padding: 5px 10px; border-radius: 3px;")
        self.lbl_gross_break_even.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_gross_break_even, 0, 5)

        roi_grid.addWidget(QLabel("净保本投产:"), 0, 6)
        self.lbl_net_break_even = QLabel("0.00")
        self.lbl_net_break_even.setStyleSheet("font-weight: bold; color: #e67e22; background-color: #fef5e7; padding: 5px 10px; border-radius: 3px;")
        self.lbl_net_break_even.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_net_break_even, 0, 7)

        roi_grid.addWidget(QLabel("最佳投产:"), 0, 8)
        self.lbl_best_roi = QLabel("0.00")
        self.lbl_best_roi.setStyleSheet("font-weight: bold; color: #27ae60; background-color: #e8f8f5; padding: 5px 10px; border-radius: 3px;")
        self.lbl_best_roi.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_best_roi, 0, 9)

        roi_grid.addWidget(QLabel("净利率:"), 1, 2)
        self.lbl_net_profit_rate = QLabel("0.00%")
        self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #3498db; background-color: #ebf5fb; padding: 5px 10px; border-radius: 3px;")
        self.lbl_net_profit_rate.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_net_profit_rate, 1, 3)

        roi_grid.addWidget(QLabel("投产倍数:"), 1, 4)
        self.lbl_roi_multiple = QLabel("--")
        self.lbl_roi_multiple.setStyleSheet("font-weight: bold; color: #9b59b6; background-color: #f5eef8; padding: 5px 10px; border-radius: 3px;")
        self.lbl_roi_multiple.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_roi_multiple, 1, 5)

        roi_grid.addWidget(QLabel("放量投产:"), 1, 6)
        self.lbl_scale_roi = QLabel("--")
        self.lbl_scale_roi.setStyleSheet("font-weight: bold; color: #e67e22; background-color: #fef5e7; padding: 5px 10px; border-radius: 3px;")
        self.lbl_scale_roi.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_scale_roi, 1, 7)

        roi_grid.addWidget(QLabel("推广占比:"), 1, 8)
        self.lbl_promotion_ratio = QLabel("--")
        self.lbl_promotion_ratio.setStyleSheet("font-weight: bold; color: #3498db; background-color: #ebf5fb; padding: 5px 10px; border-radius: 3px;")
        self.lbl_promotion_ratio.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_promotion_ratio, 1, 9)

        roi_grid.setColumnStretch(4, 1)
        roi_grid.setColumnStretch(5, 1)
        roi_grid.setColumnStretch(6, 1)
        roi_grid.setColumnStretch(7, 1)
        roi_grid.setColumnStretch(8, 1)
        roi_grid.setColumnStretch(9, 1)

        self._apply_roi_bid_input_mode()
        roi_layout.addLayout(roi_grid)
        
        roi_widget.setStyleSheet("background-color: #f8f9fa; border-radius: 5px; border: 1px solid #dee2e6;")
        layout.addWidget(roi_widget)

        spec_filter_widget = QWidget()
        spec_filter_layout = QHBoxLayout(spec_filter_widget)
        spec_filter_layout.setContentsMargins(8, 5, 8, 5)
        spec_filter_layout.setSpacing(8)

        self.chk_two_level_specs = QCheckBox("两层规格模式")
        self.chk_two_level_specs.setChecked(self.two_level_specs)
        self.chk_two_level_specs.toggled.connect(self._on_two_level_mode_toggled)
        spec_filter_layout.addWidget(self.chk_two_level_specs)

        self.two_level_controls = QWidget()
        two_level_layout = QHBoxLayout(self.two_level_controls)
        two_level_layout.setContentsMargins(0, 0, 0, 0)
        two_level_layout.setSpacing(8)

        two_level_layout.addWidget(QLabel("筛选第一层:"))
        self.spec_filter_level1 = QComboBox()
        self.spec_filter_level1.setFixedWidth(150)
        self.spec_filter_level1.currentTextChanged.connect(self._apply_spec_filters)
        two_level_layout.addWidget(self.spec_filter_level1)

        two_level_layout.addWidget(QLabel("筛选第二层:"))
        self.spec_filter_level2 = QComboBox()
        self.spec_filter_level2.setFixedWidth(120)
        self.spec_filter_level2.currentTextChanged.connect(self._apply_spec_filters)
        two_level_layout.addWidget(self.spec_filter_level2)

        two_level_layout.addWidget(QLabel("批量售价:"))

        self.batch_price_value = QLineEdit()
        self.batch_price_value.setPlaceholderText("输入价格...")
        self.batch_price_value.setFixedWidth(120)
        two_level_layout.addWidget(self.batch_price_value)

        self.btn_batch_update_prices = QPushButton("批量修改可见行价格")
        self.btn_batch_update_prices.clicked.connect(self._batch_update_visible_prices)
        two_level_layout.addWidget(self.btn_batch_update_prices)

        spec_filter_layout.addWidget(self.two_level_controls)
        spec_filter_layout.addStretch()
        spec_filter_widget.setStyleSheet("background-color: #eef7ff; border: 1px solid #cfe8ff; border-radius: 4px;")
        layout.addWidget(spec_filter_widget)

        # 规格表格区

        # 2. 规格表格
        self.table = QTableWidget()
        self.table.setColumnCount(self.SPEC_TABLE_COLUMN_COUNT)
        
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(True)
        self.table.installEventFilter(self)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_spec_row_context_menu)
        self._apply_spec_table_headers_and_column_sizing()

        # 设置表格字体和样式
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                font-family: YouYuan, "Microsoft YaHei UI", sans-serif;
                font-weight: bold;
            }
            QTableWidget::item {
                text-align: center;
                font-weight: bold;
                padding: 0px;
            }
            QTableWidget::item:selected {
                background-color: #e6f3ff;
                color: black;
                outline: none;
                padding: 0px;
            }
            QHeaderView::section {
                font-size: 13px;
                font-family: YouYuan, "Microsoft YaHei UI", sans-serif;
                font-weight: bold;
                padding: 3px 2px;
            }
        """)
        
        # 设置默认行高，确保输入框显示完整
        self.table.verticalHeader().setDefaultSectionSize(35)  # 设置合适的行高
        
        # 启用自动行高调整
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        # 设置数值列居中显示（权重列使用专用代理处理锁图标）
        self.center_delegate = CenterAlignDelegate(self)
        for col in [self.COL_COST, self.COL_SALE_PRICE, self.COL_FINAL_PRICE, self.COL_MARGIN_RATE, self.COL_GROSS_PROFIT]:
            self.table.setItemDelegateForColumn(col, self.center_delegate)
        
        layout.addWidget(self.table)
        
        # 设置代理：规格名称/关联编码编辑框与单元格视觉保持一致
        self.spec_name_inline_delegate = InlineTextEditDelegate(
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            max_length=40,
            wrap_display=True,
            parent=self.table
        )
        self.table.setItemDelegateForColumn(self.COL_SPEC_NAME, self.spec_name_inline_delegate)
        self.table.setItemDelegateForColumn(self.COL_SPEC_NAME_2, self.spec_name_inline_delegate)

        self.spec_code_inline_delegate = InlineTextEditDelegate(
            alignment=Qt.AlignCenter,
            parent=self.table
        )
        self.table.setItemDelegateForColumn(self.COL_SPEC_CODE, self.spec_code_inline_delegate)
        
        # 权重列
        self.weight_delegate = WeightDelegate(self)
        self.table.setItemDelegateForColumn(self.COL_WEIGHT, self.weight_delegate)
        self._set_two_level_mode(self.two_level_specs, transform_rows=False)

        # 底部按钮操作区

        # 3. 底部按钮区
        btn_layout = QHBoxLayout()
        
        btn_add = QPushButton("➕ 添加规格")
        btn_add.clicked.connect(self.add_row)
        
        btn_avg = QPushButton("⚖️ 一键均分权重")
        btn_avg.clicked.connect(self.average_weights)
        
        self.btn_profit_calc = QPushButton("🧮 投产计算器")
        self.btn_profit_calc.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.btn_profit_calc.clicked.connect(self.open_profit_calculator)

        btn_save = QPushButton("💾 保存数据")
        btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 8px 20px;")
        btn_save.clicked.connect(self.save_data)
        
        btn_cancel = QPushButton("❌ 取消")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_avg)
        btn_layout.addWidget(self.btn_profit_calc)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        # 底部数据显示区

        stats_container = QWidget()
        stats_layout = QVBoxLayout(stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(5)

        stats_row1 = QHBoxLayout()
        stats_row1.setSpacing(20)

        self.lbl_total_margin = QLabel("当前综合毛利率：0.00%")
        self.lbl_total_margin.setStyleSheet("font-size: 14px; font-weight: bold; color: #d9534f; padding: 5px 10px;")
        self.lbl_total_margin.setAlignment(Qt.AlignLeft)
        stats_row1.addWidget(self.lbl_total_margin)

        self.lbl_total_orders = QLabel("订单时间范围: 无日期 | 导入: 未知")
        self.lbl_total_orders.setStyleSheet("font-size: 14px; color: #666; padding: 5px 10px;")
        self.lbl_total_orders.setAlignment(Qt.AlignLeft)
        stats_row1.addWidget(self.lbl_total_orders)

        stats_row1.addStretch()

        stats_layout.addLayout(stats_row1)

        stats_row2 = QHBoxLayout()
        stats_row2.setSpacing(20)

        self.lbl_sales_info = QLabel("销售额: - | 客单价: -")
        self.lbl_sales_info.setStyleSheet("font-size: 14px; color: #27ae60; padding: 5px 10px; font-weight: bold;")
        self.lbl_sales_info.setAlignment(Qt.AlignLeft)
        stats_row2.addWidget(self.lbl_sales_info)

        self.lbl_order_date_range = QLabel("")
        self.lbl_order_date_range.setStyleSheet("font-size: 14px; color: #8e44ad; padding: 5px 10px; font-weight: bold;")
        self.lbl_order_date_range.setAlignment(Qt.AlignLeft)
        stats_row2.addWidget(self.lbl_order_date_range)

        stats_row2.addStretch()

        stats_layout.addLayout(stats_row2)

        layout.addWidget(stats_container)

        # 5. 信号连接
        self.table.cellChanged.connect(self.on_cell_change)

        self.metric_range_mode = "week"
        self.metric_panel = self._create_metric_change_panel()
        self.main_splitter.addWidget(self.metric_panel)
        self.main_splitter.setStretchFactor(0, 7)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([1460, 240])
        self.refresh_metric_change_panel()

    def _create_metric_change_panel(self):
        panel = QFrame()
        panel.setMinimumWidth(220)
        panel.setStyleSheet("""
            QFrame {
                background: #fbfcfe;
                border: 1px solid #dfe6ee;
                border-radius: 4px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)

        title = QLabel("指标变化")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50;")
        panel_layout.addWidget(title)

        range_buttons = QWidget()
        range_layout = QGridLayout(range_buttons)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setHorizontalSpacing(5)
        range_layout.setVerticalSpacing(5)

        self.metric_range_group = QButtonGroup(self)
        self.metric_range_group.setExclusive(True)
        for index, (mode, text) in enumerate([("week", "近一周"), ("month", "近一个月"), ("custom", "手动时间"), ("all", "全部")]):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #b8c7d6;
                    background: white;
                    color: #34495e;
                    border-radius: 3px;
                    padding: 3px 8px;
                    font-size: 12px;
                }
                QPushButton:checked {
                    background: #3498db;
                    color: white;
                    border-color: #3498db;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked=False, m=mode: self._set_metric_range_mode(m))
            self.metric_range_group.addButton(btn)
            range_layout.addWidget(btn, index // 2, index % 2)
            if mode == "week":
                btn.setChecked(True)

        panel_layout.addWidget(range_buttons)

        custom_widget = QWidget()
        custom_layout = QGridLayout(custom_widget)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setHorizontalSpacing(6)
        custom_layout.setVerticalSpacing(4)

        custom_layout.addWidget(QLabel("开始"), 0, 0)
        self.metric_start_date = QDateEdit()
        self.metric_start_date.setCalendarPopup(True)
        self.metric_start_date.setDisplayFormat("yyyy-MM-dd")
        self.metric_start_date.setDate(QDate.currentDate().addDays(-6))
        self.metric_start_date.dateChanged.connect(lambda: self._on_metric_custom_date_changed())
        custom_layout.addWidget(self.metric_start_date, 0, 1)

        custom_layout.addWidget(QLabel("结束"), 1, 0)
        self.metric_end_date = QDateEdit()
        self.metric_end_date.setCalendarPopup(True)
        self.metric_end_date.setDisplayFormat("yyyy-MM-dd")
        self.metric_end_date.setDate(QDate.currentDate())
        self.metric_end_date.dateChanged.connect(lambda: self._on_metric_custom_date_changed())
        custom_layout.addWidget(self.metric_end_date, 1, 1)
        self.metric_custom_widget = custom_widget
        self.metric_custom_widget.setVisible(False)
        panel_layout.addWidget(self.metric_custom_widget)

        self.metric_range_label = QLabel("")
        self.metric_range_label.setWordWrap(True)
        self.metric_range_label.setStyleSheet("font-size: 12px; color: #607d8b; padding: 2px 0;")
        panel_layout.addWidget(self.metric_range_label)

        self.metric_scroll = QScrollArea()
        self.metric_scroll.setWidgetResizable(True)
        self.metric_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.metric_scroll_widget = QWidget()
        self.metric_list_layout = QVBoxLayout(self.metric_scroll_widget)
        self.metric_list_layout.setContentsMargins(0, 0, 0, 0)
        self.metric_list_layout.setSpacing(7)
        self.metric_list_layout.setAlignment(Qt.AlignTop)
        self.metric_scroll.setWidget(self.metric_scroll_widget)
        panel_layout.addWidget(self.metric_scroll, 1)

        return panel

    def _set_metric_range_mode(self, mode):
        self.metric_range_mode = mode
        if hasattr(self, "metric_custom_widget"):
            self.metric_custom_widget.setVisible(mode == "custom")
        self.refresh_metric_change_panel()

    def _on_metric_custom_date_changed(self):
        if getattr(self, "metric_range_mode", "week") == "custom":
            self.refresh_metric_change_panel()

    def _get_metric_date_range(self):
        mode = getattr(self, "metric_range_mode", "week")
        today = date.today()
        if mode == "all":
            return None, None, "全部记录"
        if mode == "month":
            start = today - timedelta(days=29)
            return start, today, f"{start.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')}"
        if mode == "custom":
            start = self.metric_start_date.date().toPyDate()
            end = self.metric_end_date.date().toPyDate()
            if start > end:
                start, end = end, start
            return start, end, f"{start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}"
        start = today - timedelta(days=6)
        return start, today, f"{start.strftime('%Y-%m-%d')} 至 {today.strftime('%Y-%m-%d')}"

    def _load_metric_changes(self, start_date, end_date):
        rows = self.db.safe_fetchall(
            "SELECT year, month, day, records_json FROM records WHERE product_id=?",
            (self.product_id,)
        )
        changes = []
        legacy_count = 0

        for year, month, day, records_json in rows:
            try:
                record_date = date(int(year), int(month), int(day))
            except Exception:
                continue

            if start_date and record_date < start_date:
                continue
            if end_date and record_date > end_date:
                continue

            try:
                records = json.loads(records_json) if records_json else []
            except Exception:
                records = []

            for rec_index, rec in enumerate(records):
                rec_changes = rec.get("changes", []) or []
                if not rec_changes:
                    if rec.get("text"):
                        legacy_count += 1
                    continue

                time_text = rec.get("time", "")
                for change_index, change in enumerate(rec_changes):
                    item = dict(change)
                    item["date"] = record_date
                    item["date_text"] = record_date.strftime("%Y-%m-%d")
                    item["time"] = item.get("time") or time_text
                    item["sort_key"] = f"{item['date_text']} {item.get('time', '')}"
                    item["_record_index"] = rec_index
                    item["_change_index"] = change_index
                    changes.append(item)

        changes.sort(key=lambda item: item.get("sort_key", ""), reverse=True)
        return changes, legacy_count

    def _clear_metric_change_list(self):
        if not hasattr(self, "metric_list_layout"):
            return
        while self.metric_list_layout.count():
            item = self.metric_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh_metric_change_panel(self):
        if not hasattr(self, "metric_list_layout"):
            return

        start_date, end_date, range_text = self._get_metric_date_range()
        self.metric_range_label.setText(f"当前范围：{range_text}")
        self._clear_metric_change_list()

        changes, legacy_count = self._load_metric_changes(start_date, end_date)
        if not changes:
            empty = QLabel("当前时间范围内暂无指标变化")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #95a5a6; padding: 28px 12px; font-size: 13px;")
            self.metric_list_layout.addWidget(empty)
        else:
            for change in changes:
                self.metric_list_layout.addWidget(self._create_metric_change_card(change))

        if legacy_count > 0:
            hint = QLabel(f"有 {legacy_count} 条旧文字记录无结构化指标明细")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #95a5a6; font-size: 11px; padding: 6px;")
            self.metric_list_layout.addWidget(hint)

    def _create_metric_change_card(self, change):
        color_map = {
            "price_increase": "#e74c3c",
            "price_decrease": "#27ae60",
            "price_set": "#3498db",
            "roi": "#9b59b6",
            "transaction_bid": "#8e44ad",
            "gross_margin": "#d35400",
            "return_rate": "#f39c12",
            "coupon": "#16a085",
            "new_customer_discount": "#2980b9",
            "limited_time": "#c0392b",
            "marketing": "#7d3c98",
            "spec_deleted": "#7f8c8d",
            "roi_bid_mode": "#2c7be5",
        }
        change_type = change.get("type", "")
        accent = color_map.get(change_type, "#3498db")

        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid #dfe6ee;
                border-left: 4px solid {accent};
                border-radius: 4px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, item=dict(change), widget=card: self._show_metric_change_context_menu(
                item, widget.mapToGlobal(pos)
            )
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        top = QLabel(f"{change.get('date_text', '')} {change.get('time', '')}  {change.get('metric', '指标变化')}")
        top.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50;")
        top.setWordWrap(True)
        layout.addWidget(top)

        old_value = change.get("old", "")
        new_value = change.get("new", "")
        if old_value != "" or new_value != "":
            value = QLabel(f"{old_value}  ->  {new_value}")
            value.setWordWrap(True)
            value.setStyleSheet(f"font-size: 12px; color: {accent}; font-weight: bold;")
            layout.addWidget(value)

        text = QLabel(change.get("text", ""))
        text.setWordWrap(True)
        text.setStyleSheet("font-size: 12px; color: #34495e; line-height: 1.35;")
        layout.addWidget(text)
        return card

    def _show_metric_change_context_menu(self, change, global_pos):
        menu = QMenu(self)
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self._delete_metric_change(change))
        menu.addAction(delete_action)
        menu.exec_(global_pos)

    def _delete_metric_change(self, change):
        try:
            record_date = change.get("date")
            if not record_date:
                record_date = datetime.strptime(change.get("date_text", ""), "%Y-%m-%d").date()
            year, month, day = record_date.year, record_date.month, record_date.day

            rows = self.db.safe_fetchall(
                "SELECT records_json FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                (self.product_id, year, month, day)
            )
            if not rows:
                return

            try:
                records = json.loads(rows[0][0]) if rows[0][0] else []
            except Exception:
                records = []

            rec_index = change.get("_record_index")
            change_index = change.get("_change_index")
            removed = False

            if isinstance(rec_index, int) and 0 <= rec_index < len(records):
                changes = records[rec_index].get("changes", []) or []
                if isinstance(change_index, int) and 0 <= change_index < len(changes):
                    candidate = changes[change_index]
                    if self._metric_change_matches(candidate, change):
                        changes.pop(change_index)
                        removed = True
                if not removed:
                    for idx, candidate in enumerate(changes):
                        if self._metric_change_matches(candidate, change):
                            changes.pop(idx)
                            removed = True
                            break
                if removed:
                    self._sync_metric_record_after_delete(records, rec_index, changes)

            if not removed:
                for idx, rec in enumerate(records):
                    changes = rec.get("changes", []) or []
                    for change_idx, candidate in enumerate(changes):
                        if self._metric_change_matches(candidate, change):
                            changes.pop(change_idx)
                            self._sync_metric_record_after_delete(records, idx, changes)
                            removed = True
                            break
                    if removed:
                        break

            if not removed:
                return

            self.db.safe_execute(
                "INSERT OR REPLACE INTO records (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
                (self.product_id, year, month, day, json.dumps(records, ensure_ascii=False))
            )
            self.refresh_metric_change_panel()
            self._show_action_bubble("已删除指标变化")
        except Exception as e:
            print(f"删除指标变化失败: {e}")

    def _metric_change_matches(self, candidate, target):
        for key in ("time", "metric", "old", "new", "text", "type"):
            if str(candidate.get(key, "")) != str(target.get(key, "")):
                return False
        return True

    def _sync_metric_record_after_delete(self, records, rec_index, changes):
        if not changes:
            records.pop(rec_index)
            return
        records[rec_index]["changes"] = changes
        texts = [str(change.get("text", "")).strip() for change in changes if str(change.get("text", "")).strip()]
        records[rec_index]["text"] = "；".join(texts)

    def _split_two_level_spec_name(self, spec_name):
        """按最后一个空格拆分两层规格名。"""
        text = (spec_name or "").strip()
        if not text or " " not in text:
            return text, ""
        first, second = text.rsplit(" ", 1)
        return first.strip(), second.strip()

    def _compose_spec_name(self, row):
        """根据当前模式从表格行合成保存用的完整规格名。"""
        first_item = self.table.item(row, self.COL_SPEC_NAME)
        first = first_item.text().strip() if first_item else ""
        if not self.two_level_specs:
            return first

        second_item = self.table.item(row, self.COL_SPEC_NAME_2)
        second = second_item.text().strip() if second_item else ""
        return f"{first} {second}".strip() if second else first

    def _mark_editable_spec_item(self, item):
        """给规格表可手动编辑单元格统一浅绿色背景。"""
        if item:
            item.setBackground(self.EDITABLE_SPEC_BG)
        return item

    def _set_spec_name_cells(self, row, spec_name):
        """按当前模式写入规格名单元格。"""
        if self.two_level_specs:
            first, second = self._split_two_level_spec_name(spec_name)
        else:
            first, second = spec_name, ""

        first_item = QTableWidgetItem(first)
        first_item.setToolTip("规格名称（最大40字符）")
        self._mark_editable_spec_item(first_item)
        self.table.setItem(row, self.COL_SPEC_NAME, first_item)

        second_item = QTableWidgetItem(second)
        second_item.setToolTip("第二层规格")
        self._mark_editable_spec_item(second_item)
        self.table.setItem(row, self.COL_SPEC_NAME_2, second_item)

    def _get_spec_table_headers(self, enabled=None):
        """返回规格表格表头；指标列用换行适配数据优先的列宽。"""
        two_level = self.two_level_specs if enabled is None else bool(enabled)
        first_spec_header = "第一层\n规格" if two_level else "规格\n名称"
        return [
            "",
            "规格\n图",
            first_spec_header,
            "第二层\n规格",
            "关联\n编码",
            "自动\n成本",
            "手动\n售价",
            "券后\n价",
            "毛利\n率",
            "毛利润",
            "权重\n%",
            "权重\n对比\n(较上周)",
            "单量",
            "单量\n对比\n(较上周)",
            "退款\n订单",
            "退款\n占比\n(单规格)",
        ]

    def _apply_spec_table_headers_and_column_sizing(self, enabled=None):
        """统一应用表头；列宽按当前内容动态测量。"""
        if not hasattr(self, "table"):
            return

        self.table.setHorizontalHeaderLabels(self._get_spec_table_headers(enabled))

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setMinimumHeight(62)
        header.setFixedHeight(64)
        header.setMinimumSectionSize(42)
        header.setStretchLastSection(False)
        for col in range(self.SPEC_TABLE_COLUMN_COUNT):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        self._resize_spec_table_columns_to_content()

    def _schedule_spec_table_column_resize(self):
        if not hasattr(self, "table"):
            return
        if not hasattr(self, "_spec_content_resize_timer"):
            self._spec_content_resize_timer = QTimer(self)
            self._spec_content_resize_timer.setSingleShot(True)
            self._spec_content_resize_timer.timeout.connect(self._resize_spec_table_columns_to_content)
        self._spec_content_resize_timer.start(80)

    def _text_width_for_column(self, metrics, text):
        lines = str(text or "").splitlines() or [""]
        return max(metrics.horizontalAdvance(line) for line in lines)

    def _resize_spec_table_columns_to_content(self):
        """按当前表头、可见数据和单元格控件宽度计算列宽。"""
        if not hasattr(self, "table"):
            return

        header_metrics = QFontMetrics(self.table.horizontalHeader().font())
        cell_metrics = QFontMetrics(self.table.font())
        headers = self._get_spec_table_headers()

        min_widths = {
            self.COL_AI: 48,
            self.COL_SPEC_IMAGE: 62,
            self.COL_WEIGHT: 64,
        }
        max_widths = {
            self.COL_SPEC_NAME: 520,
            self.COL_SPEC_NAME_2: 360,
            self.COL_SPEC_CODE: 300,
            self.COL_WEIGHT_COMPARE: 150,
            self.COL_ORDER_COMPARE: 150,
            self.COL_REFUND_RATIO: 150,
        }
        default_min = 58
        default_max = 220

        visible_rows = [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]
        rows_to_measure = visible_rows if visible_rows else list(range(self.table.rowCount()))

        column_widths = {}
        for col in range(self.SPEC_TABLE_COLUMN_COUNT):
            if self.table.isColumnHidden(col):
                continue

            header_width = self._text_width_for_column(header_metrics, headers[col] if col < len(headers) else "")
            width = header_width + 16

            for row in rows_to_measure:
                item = self.table.item(row, col)
                if item:
                    display = item.data(Qt.DisplayRole)
                    if display is None:
                        display = item.text()
                    width = max(width, self._text_width_for_column(cell_metrics, display) + 18)

                widget = self.table.cellWidget(row, col)
                if widget:
                    hint = widget.sizeHint()
                    widget_width = max(hint.width(), widget.minimumWidth())
                    width = max(width, widget_width + 8)

            min_width = min_widths.get(col, default_min)
            max_width = max_widths.get(col, default_max)
            column_widths[col] = max(min_width, min(width, max_width))

        remaining = self.table.viewport().width() - sum(column_widths.values()) - 2
        if remaining > 0 and column_widths:
            flexible_columns = [
                col for col in (self.COL_SPEC_NAME, self.COL_SPEC_NAME_2, self.COL_SPEC_CODE)
                if col in column_widths and not self.table.isColumnHidden(col)
            ]
            if not flexible_columns:
                flexible_columns = [max(column_widths)]
            base_extra = remaining // len(flexible_columns)
            leftover = remaining % len(flexible_columns)
            for index, col in enumerate(flexible_columns):
                column_widths[col] += base_extra + (1 if index < leftover else 0)

        for col, width in column_widths.items():
            self.table.setColumnWidth(col, width)

    def _on_two_level_mode_toggled(self, checked):
        self.db.set_setting(f"product_spec_two_level_{self.product_id}", "1" if checked else "0")
        self._set_two_level_mode(bool(checked), transform_rows=True)

    def _set_two_level_mode(self, enabled, transform_rows=True):
        old_mode = self.two_level_specs
        self.two_level_specs = bool(enabled)
        self._apply_spec_table_headers_and_column_sizing(enabled)
        self.table.setColumnHidden(self.COL_SPEC_NAME_2, not enabled)
        self.two_level_controls.setVisible(enabled)

        if transform_rows:
            for row in range(self.table.rowCount()):
                if old_mode:
                    first_item = self.table.item(row, self.COL_SPEC_NAME)
                    second_item = self.table.item(row, self.COL_SPEC_NAME_2)
                    first = first_item.text().strip() if first_item else ""
                    second = second_item.text().strip() if second_item else ""
                    full_name = f"{first} {second}".strip() if second else first
                else:
                    first_item = self.table.item(row, self.COL_SPEC_NAME)
                    full_name = first_item.text().strip() if first_item else ""
                self._set_spec_name_cells(row, full_name)

        if not enabled:
            self._set_combo_items(self.spec_filter_level1, [])
            self._set_combo_items(self.spec_filter_level2, [])
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, False)
        else:
            self._refresh_spec_filter_options()
            self._apply_spec_filters()
        self._schedule_spec_table_column_resize()

    def _set_combo_items(self, combo, values):
        current = combo.currentText()
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("全部")
            for value in values:
                combo.addItem(value)
            index = combo.findText(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            combo.blockSignals(False)

    def _refresh_spec_filter_options(self):
        if not hasattr(self, "table"):
            return

        first_values = []
        second_values = []
        for row in range(self.table.rowCount()):
            first_item = self.table.item(row, self.COL_SPEC_NAME)
            second_item = self.table.item(row, self.COL_SPEC_NAME_2)
            first = first_item.text().strip() if first_item else ""
            second = second_item.text().strip() if second_item else ""
            if first and first not in first_values:
                first_values.append(first)
            if second and second not in second_values:
                second_values.append(second)

        self._set_combo_items(self.spec_filter_level1, sorted(first_values))
        self._set_combo_items(self.spec_filter_level2, sorted(second_values))

    def _get_combo_filter_value(self, combo):
        value = combo.currentText().strip()
        return "" if value == "全部" else value

    def _apply_spec_filters(self):
        if not self.two_level_specs or not hasattr(self, "table"):
            return

        first_filter = self._get_combo_filter_value(self.spec_filter_level1)
        second_filter = self._get_combo_filter_value(self.spec_filter_level2)

        for row in range(self.table.rowCount()):
            first_item = self.table.item(row, self.COL_SPEC_NAME)
            second_item = self.table.item(row, self.COL_SPEC_NAME_2)
            first = first_item.text().strip() if first_item else ""
            second = second_item.text().strip() if second_item else ""
            match_first = not first_filter or first_filter == first
            match_second = not second_filter or second_filter == second
            self.table.setRowHidden(row, not (match_first and match_second))
        self._schedule_spec_table_column_resize()

    def _batch_update_visible_prices(self):
        if not self.two_level_specs:
            QMessageBox.information(self, "提示", "请先勾选两层规格模式。")
            return

        value_text = self.batch_price_value.text().strip()
        if not value_text:
            QMessageBox.information(self, "提示", "请输入要批量修改的价格。")
            return

        try:
            new_price = float(value_text)
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字价格。")
            return

        if new_price < 0:
            QMessageBox.warning(self, "输入错误", "价格不能为负数。")
            return

        changed = 0
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                if self.table.isRowHidden(row):
                    continue
                item = self.table.item(row, self.COL_SALE_PRICE)
                if not item:
                    item = QTableWidgetItem()
                    self._mark_editable_spec_item(item)
                    self.table.setItem(row, self.COL_SALE_PRICE, item)
                item.setText(f"{new_price:.2f}")
                self.calculate_row_margin(row)
                changed += 1
        finally:
            self.table.blockSignals(False)

        if changed == 0:
            QMessageBox.information(self, "提示", "当前筛选条件下没有可修改的可见行。")
            return

        self.calculate_total_margin()
        if hasattr(self, 'lbl_gross_break_even'):
            self.calculate_roi_metrics()
        self._refresh_spec_filter_options()
        self._apply_spec_filters()
        self.batch_price_value.clear()
        self._schedule_spec_table_column_resize()
        self._show_action_bubble(f"已批量修改 {changed} 行价格")

    def eventFilter(self, obj, event):
        """事件过滤器：处理标签双击事件"""
        if obj == getattr(self, "table", None) and event.type() == QEvent.KeyPress and event.matches(QKeySequence.Paste):
            row = self.table.currentRow()
            col = self.table.currentColumn()
            if row >= 0 and col == self.COL_SPEC_IMAGE:
                self._paste_spec_image_from_clipboard(row)
                return True

        if event.type() == QEvent.MouseButtonPress:
            if obj == getattr(self, "current_roi_input", None):
                if getattr(self, "roi_input_mode", "roi") != "roi":
                    self._set_roi_bid_input_mode("roi", user_action=True)
                    self.current_roi_input.setFocus()
                    QTimer.singleShot(0, self.current_roi_input.selectAll)
                    return True
                self._mark_roi_bid_manual_source("roi")
            elif obj == getattr(self, "transaction_bid_input", None):
                if getattr(self, "roi_input_mode", "roi") != "bid":
                    self._set_roi_bid_input_mode("bid", user_action=True)
                    self.transaction_bid_input.setFocus()
                    QTimer.singleShot(0, self.transaction_bid_input.selectAll)
                    return True
                self._mark_roi_bid_manual_source("transaction_bid")
        elif event.type() == QEvent.FocusIn:
            if obj == getattr(self, "current_roi_input", None) and getattr(self, "roi_input_mode", "roi") == "roi":
                self._mark_roi_bid_manual_source("roi")
            elif obj == getattr(self, "transaction_bid_input", None) and getattr(self, "roi_input_mode", "roi") == "bid":
                self._mark_roi_bid_manual_source("transaction_bid")

        if event.type() == QEvent.MouseButtonDblClick:
            if obj == self.lbl_code:
                self._code_click_timer.stop()
                self.edit_product_code()
                return True
            elif obj == self.lbl_name:
                self.edit_product_name()
                return True
            elif obj == getattr(self, "current_roi_input", None):
                self._set_roi_bid_input_mode("roi", user_action=True)
                self.current_roi_input.setFocus()
                QTimer.singleShot(0, self.current_roi_input.selectAll)
                return True
            elif obj == getattr(self, "transaction_bid_input", None):
                self._set_roi_bid_input_mode("bid", user_action=True)
                self.transaction_bid_input.setFocus()
                QTimer.singleShot(0, self.transaction_bid_input.selectAll)
                return True
        elif event.type() == QEvent.MouseButtonRelease and obj == self.lbl_code:
            self._code_click_timer.start(QApplication.doubleClickInterval())
            return True
        return super().eventFilter(obj, event)

    def _copy_product_code_to_clipboard(self):
        """复制商品ID并显示窗口内气泡提示。"""
        QApplication.clipboard().setText(str(self.product_code))
        self._show_copy_bubble(f"已复制商品ID: {self.product_code}")

    def _show_copy_bubble(self, text, fade_in_ms=500, hold_ms=900, fade_out_ms=500):
        """显示窗口内气泡提示，默认保留商品 ID 复制提示的淡入淡出节奏。"""
        for anim in self._copy_toast_animations:
            anim.stop()
        self._copy_toast_animations = []

        if self._copy_toast:
            self._copy_toast.deleteLater()
            self._copy_toast = None

        toast = QLabel(text, self)
        toast.setAttribute(Qt.WA_TransparentForMouseEvents)
        toast.setStyleSheet("""
            QLabel {
                background-color: rgba(44, 62, 80, 230);
                color: white;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        toast.adjustSize()

        anchor = self.lbl_code.mapTo(self, self.lbl_code.rect().bottomLeft())
        x = min(max(anchor.x(), 8), max(8, self.width() - toast.width() - 8))
        y = min(anchor.y() + 8, max(8, self.height() - toast.height() - 8))
        toast.move(x, y)

        opacity = QGraphicsOpacityEffect(toast)
        opacity.setOpacity(0.0)
        toast.setGraphicsEffect(opacity)
        toast.show()
        toast.raise_()
        self._copy_toast = toast

        fade_in = QPropertyAnimation(opacity, b"opacity", self)
        fade_in.setDuration(fade_in_ms)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)

        fade_out = QPropertyAnimation(opacity, b"opacity", self)
        fade_out.setDuration(fade_out_ms)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)

        def close_toast():
            if self._copy_toast is toast:
                self._copy_toast = None
            toast.deleteLater()
            self._copy_toast_animations = [
                anim for anim in self._copy_toast_animations
                if anim not in (fade_in, fade_out)
            ]

        fade_in.finished.connect(lambda: QTimer.singleShot(hold_ms, fade_out.start))
        fade_out.finished.connect(close_toast)
        self._copy_toast_animations = [fade_in, fade_out]
        fade_in.start()

    def _show_action_bubble(self, text):
        """显示 1 秒操作结果气泡提示。"""
        self._show_copy_bubble(text, fade_in_ms=250, hold_ms=500, fade_out_ms=250)

    def _snapshot_has_product_refunds(self, snapshot):
        """检查历史快照里当前商品是否包含退款数据。"""
        prefix = f"{self.product_code}_"
        for key, data in snapshot.get("orders", {}).items():
            if key.startswith(prefix) and isinstance(data, dict) and (data.get("refund_count") or 0) > 0:
                return True
        return False

    def _restore_orders_from_snapshot(self, store_id, snapshot, import_time=None):
        """按历史快照恢复指定店铺 imported_orders，不触发界面副作用。"""
        orders_data = snapshot.get("orders", {})
        if not orders_data:
            return False

        restore_time = import_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.safe_execute("DELETE FROM imported_orders WHERE store_id=?", (store_id,))

        for key, data in orders_data.items():
            if not isinstance(data, dict):
                continue
            parts = key.split("_", 1)
            if len(parts) < 2:
                continue

            user_product_id = parts[0]
            spec_code = parts[1]
            order_count = data.get("count", 0)
            refund_count = data.get("refund_count", 0)
            dates = data.get("dates", [])
            earliest_date = min(dates) if dates else None
            latest_date = max(dates) if dates else None
            date_range = f"{earliest_date}~{latest_date}" if earliest_date and latest_date else None

            self.db.safe_execute("""
                INSERT OR REPLACE INTO imported_orders
                (store_id, product_id, spec_code, order_count, import_time, order_date, actual_amount, refund_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (store_id, user_product_id, spec_code, order_count,
                  restore_time, date_range, 0, refund_count))

        return True

    def _restore_latest_import_history_if_needed(self):
        """当前商品订单缺少退款数时，自动从最新历史快照恢复。"""
        current = self.db.safe_fetchall("""
            SELECT COUNT(*), COALESCE(SUM(COALESCE(refund_count, 0)), 0)
            FROM imported_orders
            WHERE product_id=?
        """, (self.product_code,))
        current_count = current[0][0] if current else 0
        current_refunds = current[0][1] if current else 0
        if current_count > 0 and current_refunds > 0:
            return False

        store_rows = self.db.safe_fetchall(
            "SELECT store_id FROM products WHERE id=?",
            (self.product_id,)
        )
        if not store_rows:
            return False
        store_id = store_rows[0][0]

        history_records = self.db.safe_fetchall("""
            SELECT import_time, snapshot_data
            FROM import_history
            WHERE store_id=? AND snapshot_data IS NOT NULL AND snapshot_data != ''
            ORDER BY import_time DESC, id DESC
            LIMIT 1
        """, (store_id,))
        if not history_records:
            return False

        import_time, snapshot_data = history_records[0]
        try:
            snapshot = json.loads(snapshot_data)
        except Exception:
            return False

        if not self._snapshot_has_product_refunds(snapshot):
            return False

        return self._restore_orders_from_snapshot(store_id, snapshot, import_time)

    def _make_unselectable_item(self, text=""):
        """创建不可编辑、不可选中的表格项。"""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)
        return item

    def _set_unselectable_cell_widget(self, row, column, widget):
        """给 widget 单元格补一个不可选中的底层 item。"""
        self.table.setItem(row, column, self._make_unselectable_item())
        self.table.setCellWidget(row, column, widget)

    def _pixmap_from_spec_image_data(self, image_data):
        pixmap = QPixmap()
        if image_data:
            pixmap.loadFromData(bytes(image_data))
        return pixmap

    def _get_spec_image_data(self, row):
        item = self.table.item(row, self.COL_SPEC_IMAGE)
        if not item:
            return None
        image_data = item.data(Qt.UserRole)
        return bytes(image_data) if image_data else None

    def _set_spec_image_cell(self, row, image_data=None):
        item = self._make_unselectable_item()
        item.setData(Qt.UserRole, bytes(image_data) if image_data else None)
        self.table.setItem(row, self.COL_SPEC_IMAGE, item)

        label = SpecImageCell(self.table, self._paste_spec_image_from_clipboard, self._show_spec_image_viewer, self.table)
        self._refresh_spec_image_label(label, image_data)
        self.table.setCellWidget(row, self.COL_SPEC_IMAGE, label)
        self.table.setRowHeight(row, max(self.table.rowHeight(row), 52))

    def _refresh_spec_image_label(self, label, image_data):
        pixmap = self._pixmap_from_spec_image_data(image_data)
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setText("粘贴\n图片")
            return
        label.setText("")
        label.setPixmap(pixmap.scaled(48, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _paste_spec_image_from_clipboard(self, row):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if not mime_data.hasImage():
            self._show_action_bubble("剪贴板没有图片")
            return

        pixmap = QPixmap.fromImage(clipboard.image())
        if pixmap.isNull():
            self._show_action_bubble("图片读取失败")
            return

        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        if not buffer.open(QIODevice.WriteOnly):
            self._show_action_bubble("图片读取失败")
            return
        pixmap.save(buffer, "PNG")
        image_data = bytes(byte_array)
        if not image_data:
            self._show_action_bubble("图片读取失败")
            return

        item = self.table.item(row, self.COL_SPEC_IMAGE)
        if not item:
            item = self._make_unselectable_item()
            self.table.setItem(row, self.COL_SPEC_IMAGE, item)
        item.setData(Qt.UserRole, image_data)

        label = self.table.cellWidget(row, self.COL_SPEC_IMAGE)
        if label:
            self._refresh_spec_image_label(label, image_data)
        self._show_action_bubble("规格图已粘贴，保存后生效")

    def _show_spec_image_viewer(self, row):
        image_data = self._get_spec_image_data(row)
        pixmap = self._pixmap_from_spec_image_data(image_data)
        if pixmap.isNull():
            self._show_action_bubble("该规格暂无图片")
            return
        dialog = SpecImageViewerDialog(pixmap, self)
        dialog.exec_()

    def load_specs(self):
        """从数据库加载规格数据到表格，并初始化删除功能"""
        try:
            self._restore_latest_import_history_if_needed()
            # 0. 加载优惠券和新客立减金额
            discount_rows = self.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate, is_limited_time, is_marketing FROM products WHERE id=?",
                (self.product_id,)
            )
            if discount_rows:
                coupon_amount = discount_rows[0][0] if discount_rows[0][0] else 0
                new_customer_discount = discount_rows[0][1] if discount_rows[0][1] else 0
                saved_roi = discount_rows[0][2] if discount_rows[0][2] else 0
                saved_return_rate = discount_rows[0][3] if discount_rows[0][3] else 0
                is_limited_time = discount_rows[0][4] if discount_rows[0][4] else 0
                is_marketing = discount_rows[0][5] if discount_rows[0][5] else 0
                
                self.coupon_input.setText(str(int(round(coupon_amount))) if coupon_amount > 0 else "")
                self.new_customer_input.setText(str(int(round(new_customer_discount))) if new_customer_discount > 0 else "")
                self.current_roi_input.setText(str(saved_roi) if saved_roi > 0 else "")
                self.return_rate_input.setText(str(saved_return_rate) if saved_return_rate > 0 else "")
                self.update_max_discount_label()
                
                # 设置限时限量购和营销活动按钮状态
                self.btn_limited_time.setChecked(bool(is_limited_time))
                self.btn_marketing.setChecked(bool(is_marketing))
                self.update_tag_button_styles()
            
            # 1. 清空表格
            self.table.setRowCount(0)
            
            # 2. 清空原始记录集合
            self.original_spec_codes = set()
            
            # 3. 查询数据库（包含is_locked字段）
            rows = self.db.safe_fetchall(
                "SELECT spec_name, spec_code, sale_price, weight_percent, is_locked, spec_image_data FROM product_specs WHERE product_id=?",
                (self.product_id,)
            )
            
            if not rows:
                return

            # 3.1 按券后价排序（便宜的在上面）
            max_discount = 0
            if discount_rows:
                coupon_amount = discount_rows[0][0] if discount_rows[0][0] else 0
                new_customer_amount = discount_rows[0][1] if discount_rows[0][1] else 0
                max_discount = max(coupon_amount, new_customer_amount)
            
            rows_with_final_price = []
            for row_data in rows:
                sale_price = float(row_data[2]) if row_data[2] else 0.0
                final_price = sale_price - max_discount
                rows_with_final_price.append((row_data, final_price))
            
            rows_with_final_price.sort(key=lambda x: x[1])
            rows = [r[0] for r in rows_with_final_price]

            # 3. 检查是否有导入的订单数据
            order_data_res = self.db.safe_fetchall(
                "SELECT SUM(order_count) FROM imported_orders WHERE product_id=?",
                (self.product_code,)
            )
            has_imported_orders = order_data_res and order_data_res[0][0] and order_data_res[0][0] > 0

            # 3.1 如果有导入订单，计算基于订单数量的权重
            spec_orders = {}
            if has_imported_orders:
                imported_data = self.db.safe_fetchall(
                    "SELECT spec_code, order_count FROM imported_orders WHERE product_id=?",
                    (self.product_code,)
                )
                spec_orders = {str(row[0]): row[1] for row in imported_data}
                total_orders = sum(spec_orders.values())
            else:
                total_orders = 0

            # 4. 填充数据
            for row_idx, row_data in enumerate(rows):
                spec_name = str(row_data[0]) if row_data[0] else ""
                spec_code = str(row_data[1]) if row_data[1] else ""
                sale_price = float(row_data[2]) if row_data[2] else 0.0
                weight_percent = float(row_data[3]) if row_data[3] else 0.0
                is_locked = row_data[4] if row_data[4] else 0  # 读取锁定状态
                spec_image_data = row_data[5] if len(row_data) > 5 else None
                
                # 记录原始编码
                if spec_code:
                    self.original_spec_codes.add(spec_code)
                
                # 获取成本价
                cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
                cost_price = float(cost_res[0][0]) if cost_res else 0.0

                # 计算单行毛利（使用券后价）
                margin_pct = 0.0
                final_price = sale_price - max_discount
                if final_price > 0 and cost_price > 0:
                    margin_pct = (final_price - cost_price) / final_price * 100

                # 插入行
                self.table.insertRow(row_idx)
                
                # 第0列：AI优化按钮
                ai_widget = QWidget()
                ai_layout = QHBoxLayout(ai_widget)
                ai_layout.setContentsMargins(2, 0, 2, 0)
                
                ai_btn = QPushButton()
                icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons")
                ai_icon_path = os.path.join(icons_dir, "ai_spec.svg")
                ai_btn.setIcon(QIcon(ai_icon_path))
                ai_btn.setIconSize(QSize(18, 18))
                ai_btn.setFixedSize(28, 24)
                ai_btn.setToolTip("AI优化规格名称")
                ai_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3498db;
                        color: white;
                        border: none;
                        border-radius: 3px;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #2980b9;
                    }
                """)
                ai_btn.clicked.connect(lambda checked, r=row_idx: self.ai_optimize_single_spec(r))
                ai_layout.addWidget(ai_btn)
                ai_layout.addStretch()
                
                self.table.setCellWidget(row_idx, self.COL_AI, ai_widget)
                
                # 规格图列
                self._set_spec_image_cell(row_idx, spec_image_data)

                # 规格名称列
                self._set_spec_name_cells(row_idx, spec_name)
                # 关联编码列
                self.table.setItem(row_idx, self.COL_SPEC_CODE, self._mark_editable_spec_item(QTableWidgetItem(spec_code)))
                
                # 成本列 (不可编辑)
                cost_item = QTableWidgetItem(f"{cost_price:.2f}")
                cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, self.COL_COST, cost_item)
                
                self.table.setItem(row_idx, self.COL_SALE_PRICE, self._mark_editable_spec_item(QTableWidgetItem(f"{sale_price:.2f}")))
                
                # 券后价列 (不可编辑) = 手动售价 - 最大优惠
                coupon_amount = discount_rows[0][0] if discount_rows and discount_rows[0][0] else 0
                new_customer_amount = discount_rows[0][1] if discount_rows and discount_rows[0][1] else 0
                max_discount = max(coupon_amount, new_customer_amount)
                final_price = sale_price - max_discount
                final_price_item = QTableWidgetItem(f"{final_price:.2f}")
                final_price_item.setFlags(final_price_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, self.COL_FINAL_PRICE, final_price_item)

                # 毛利列 (不可编辑)
                margin_item = QTableWidgetItem(f"{margin_pct:.2f}%")
                margin_item.setFlags(margin_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, self.COL_MARGIN_RATE, margin_item)

                # 毛利润列 (不可编辑) = 券后价 - 成本
                gross_profit = final_price - cost_price
                profit_item = QTableWidgetItem(f"{gross_profit:.2f}")
                profit_item.setFlags(profit_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, self.COL_GROSS_PROFIT, profit_item)

                # 权重列 - 根据锁定状态和订单数据显示
                order_count = spec_orders.get(str(spec_code), 0) if has_imported_orders else 0
                refund_count = 0
                if has_imported_orders:
                    refund_res = self.db.safe_fetchall(
                        "SELECT refund_count FROM imported_orders WHERE product_id=? AND spec_code=?",
                        (self.product_code, str(spec_code))
                    )
                    refund_count = refund_res[0][0] if refund_res and refund_res[0][0] else 0
                if has_imported_orders and total_orders > 0:
                    display_weight = (order_count / total_orders) * 100
                else:
                    display_weight = weight_percent
                if has_imported_orders:
                    weight_text = f"{display_weight:.2f}%"
                    weight_item = QTableWidgetItem(weight_text)
                    weight_item.setFlags(weight_item.flags() & ~Qt.ItemIsEditable)
                else:
                    if is_locked == 1:
                        weight_text = f"🔒 {display_weight:.2f}%"
                    else:
                        weight_text = f"{display_weight:.2f}%"
                    weight_item = QTableWidgetItem(weight_text)
                weight_item.setData(Qt.UserRole, display_weight)
                if weight_item.flags() & Qt.ItemIsEditable:
                    self._mark_editable_spec_item(weight_item)
                if order_count > 0:
                    weight_item.setToolTip(f"订单数: {order_count}单")
                elif has_imported_orders:
                    weight_item.setToolTip("该规格无订单")
                self.table.setItem(row_idx, self.COL_WEIGHT, weight_item)
                
                # 第 9 列添加权重对比
                weight_compare_widget = QWidget()
                weight_compare_layout = QHBoxLayout(weight_compare_widget)
                weight_compare_layout.setContentsMargins(0, 0, 0, 0)
                weight_compare_layout.setAlignment(Qt.AlignCenter)
                weight_compare_label = QLabel("-")
                weight_compare_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
                weight_compare_layout.addWidget(weight_compare_label)
                self._set_unselectable_cell_widget(row_idx, self.COL_WEIGHT_COMPARE, weight_compare_widget)

                # 第 10 列添加单量
                order_count_item = self._make_unselectable_item(f"{order_count}单")
                order_count_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, self.COL_ORDER_COUNT, order_count_item)

                # 第 11 列添加单量对比
                order_compare_widget = QWidget()
                order_compare_layout = QHBoxLayout(order_compare_widget)
                order_compare_layout.setContentsMargins(0, 0, 0, 0)
                order_compare_layout.setAlignment(Qt.AlignCenter)
                order_compare_label = QLabel("-")
                order_compare_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
                order_compare_layout.addWidget(order_compare_label)
                self._set_unselectable_cell_widget(row_idx, self.COL_ORDER_COMPARE, order_compare_widget)

                # 第 12 列添加退款订单
                refund_orders_item = self._make_unselectable_item(f"{refund_count}单" if refund_count > 0 else "无")
                refund_orders_item.setTextAlignment(Qt.AlignCenter)
                if refund_count > 0:
                    refund_orders_item.setForeground(QColor("#e74c3c"))
                else:
                    refund_orders_item.setForeground(QColor("#95a5a6"))
                self.table.setItem(row_idx, self.COL_REFUND_ORDERS, refund_orders_item)

                # 第 13 列添加退款占比
                if order_count > 0 and refund_count > 0:
                    refund_ratio = refund_count / order_count * 100
                    refund_ratio_item = self._make_unselectable_item(f"{refund_ratio:.2f}%")
                    refund_ratio_item.setForeground(QColor("#e74c3c"))
                else:
                    refund_ratio_item = self._make_unselectable_item("无")
                    refund_ratio_item.setForeground(QColor("#95a5a6"))
                refund_ratio_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, self.COL_REFUND_RATIO, refund_ratio_item)

                # 🔑【关键修复】强制更新表格
                self.table.update()
            
            # 5. 加载完成后，计算一次综合毛利
            self.calculate_total_margin()
            self.update_remaining_weight_label()
            self.update_total_orders_label()
            self.update_compare_columns()
            self._refresh_spec_filter_options()
            self._apply_spec_filters()
            self._schedule_spec_table_column_resize()

            # 🔑【关键修复】恢复之前选中的行
            if self._saved_current_row > 0 and self._saved_current_row < self.table.rowCount():
                # 选中该行
                self.table.selectRow(self._saved_current_row)
                # 滚动到该行（居中显示）
                QTimer.singleShot(50, lambda: self.table.scrollToItem(
                    self.table.item(self._saved_current_row, 0),
                    QAbstractItemView.PositionAtCenter
                ))
            
        except Exception as e:
            import traceback
            print(f"加载规格失败：{traceback.format_exc()}")
            QMessageBox.warning(self, "错误", f"加载数据失败：{e}")

    def _show_spec_row_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        menu = QMenu(self)
        delete_action = QAction("删除规格", self)
        delete_action.triggered.connect(lambda: self.delete_spec_row(row))
        menu.addAction(delete_action)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def delete_spec_row(self, row):
        """
        【中文功能说明】
        删除指定行的规格。
        逻辑：右键菜单 -> 移除行 -> 自动重算剩余权重 (归一化到 100%) -> 更新界面
        """
        if row < 0 or row >= self.table.rowCount():
            return

        # 1. 获取该行信息
        code_item = self.table.item(row, self.COL_SPEC_CODE)
        spec_name = self._compose_spec_name(row) or "未知"

        # 2. 移除行
        self.table.removeRow(row)

        # 3. 自动重算权重 (归一化)
        self.normalize_weights_after_delete()

        self._schedule_spec_table_column_resize()
        self._show_copy_bubble(f"已删除规格：{spec_name}", fade_in_ms=80, hold_ms=360, fade_out_ms=60)

    def normalize_weights_after_delete(self):
        """
        【辅助方法】删除后专用：将剩余权重简单归一化到 100%
        逻辑：计算当前总权重 -> 每个权重 = (原权重/总权重)*100
        """
        row_count = self.table.rowCount()
        if row_count == 0:
            self.calculate_total_margin()
            return

        if self.is_balancing:
            return
        self.is_balancing = True

        try:
            # 1. 收集当前权重
            total_weight = 0.0
            weights = []
            for r in range(row_count):
                w_item = self.table.item(r, self.COL_WEIGHT)
                if w_item:
                    w_text = w_item.text().replace("🔒", "").strip()
                    try:
                        w = float(w_text)
                    except ValueError:
                        w = 0.0
                else:
                    w = 0.0
                weights.append(w)
                total_weight += w
            
            if total_weight == 0:
                # 如果总重为 0，平均分配
                avg_w = 100.0 / row_count
                weights = [avg_w] * row_count
                total_weight = 100.0

            # 2. 更新权重列
            for r in range(row_count):
                if total_weight > 0:
                    new_w = (weights[r] / total_weight) * 100.0
                else:
                    new_w = 0.0
                
                w_item = self.table.item(r, self.COL_WEIGHT)
                if w_item:
                    # 保留锁图标逻辑
                    old_text = w_item.text()
                    has_lock = "🔒" in old_text
                    new_text = f"🔒 {new_w:.2f}" if has_lock else f"{new_w:.2f}"
                    w_item.setText(new_text)
                
                # 重算单行毛利
                self.calculate_row_margin(r)
            
            # 3. 更新综合毛利
            self.calculate_total_margin()
            
        finally:
            self.is_balancing = False

    def normalize_weights_and_recalc(self):
        """
        【中文功能说明】
        权重归一化与毛利重算。
        逻辑：遍历所有行 -> 计算总权重 -> 按比例放大每个权重至总和100% -> 重算每行毛利 -> 更新综合毛利。
        """
        row_count = self.table.rowCount()
        if row_count == 0:
            self.calculate_total_margin()
            return

        # 防止递归锁
        if self.is_balancing:
            return
        self.is_balancing = True

        try:
            # 1. 收集当前权重
            total_weight = 0.0
            weights = []
            for r in range(row_count):
                w_item = self.table.item(r, self.COL_WEIGHT)
                w_text = w_item.text().replace("🔒", "").strip() if w_item else "0"
                try:
                    w = float(w_text)
                except ValueError:
                    w = 0.0
                weights.append(w)
                total_weight += w
            
            if total_weight == 0:
                # 如果总权重为0，平均分配
                avg_w = 100.0 / row_count if row_count > 0 else 0
                weights = [avg_w] * row_count
                total_weight = 100.0

            # 2. 更新权重列 (归一化)
            for r in range(row_count):
                if total_weight > 0:
                    new_w = (weights[r] / total_weight) * 100.0
                else:
                    new_w = 0.0
                
                w_item = self.table.item(r, self.COL_WEIGHT)
                if w_item:
                    # 保留锁图标逻辑 (如果原来有锁，加上锁)
                    old_text = w_item.text()
                    has_lock = "🔒" in old_text
                    new_text = f"🔒 {new_w:.2f}" if has_lock else f"{new_w:.2f}"
                    w_item.setText(new_text)
                
                # 3. 重算单行毛利
                self.recalc_single_row_margin(r)
            
            # 4. 更新综合毛利
            self.calculate_total_margin()
            
        finally:
            self.is_balancing = False

    def recalc_single_row_margin(self, row):
        """重新计算某一行的毛利率和毛利润。"""
        self.calculate_row_margin(row)

    def calculate_roi_metrics(self):
        """计算投产比相关指标：毛保本投产、净保本投产、最佳投产"""
        margin_rate = self.get_current_margin_rate()
        return_rate = self.get_return_rate()
        
        if margin_rate <= 0:
            self.lbl_gross_break_even.setText("0.00")
            self.lbl_net_break_even.setText("0.00")
            self.lbl_best_roi.setText("0.00")
            self.lbl_net_profit_rate.setText("请设置毛利")
            self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #e74c3c; background-color: #fdeaea; padding: 5px 10px; border-radius: 3px;")
            self.lbl_roi_multiple.setText("--")
            self.lbl_scale_roi.setText("--")
            self.lbl_promotion_ratio.setText("--")
            self._refresh_auto_roi_bid_field()
            return
        
        # 毛保本投产 = 1 / 毛利率
        gross_break_even = 1 / margin_rate if margin_rate > 0 else 0
        
        # 净保本投产 = 1 / [毛利率 × (1 - 退货率) - 技术服务费率]
        net_margin_formula = margin_rate * (1 - return_rate / 100) - 0.0006
        net_break_even = 1 / net_margin_formula if net_margin_formula > 0 else 0
        
        # 最佳投产 = 净保本投产 × 1.4
        best_roi = net_break_even * 1.4 if net_break_even > 0 else 0
        
        self.lbl_gross_break_even.setText(f"{gross_break_even:.2f}")
        self.lbl_net_break_even.setText(f"{net_break_even:.2f}")
        self.lbl_best_roi.setText(f"{best_roi:.2f}")
        
        self.on_current_roi_changed()
    
    def get_return_rate(self):
        """获取退货率（小数形式）"""
        try:
            return_rate_text = self.return_rate_input.text().strip()
            if not return_rate_text:
                return 0.0
            return_rate = float(return_rate_text)
            if return_rate < 0:
                return 0.0
            if return_rate > 100:
                return 100.0
            return return_rate
        except ValueError:
            return 0.0

    def get_current_margin_rate(self):
        """获取当前综合毛利率（小数形式）"""
        margin_text = self.lbl_total_margin.text()
        try:
            margin_rate = float(margin_text.replace("%", "").replace("当前综合毛利率：", "").strip())
            return margin_rate / 100
        except ValueError:
            return 0.0

    def on_current_roi_changed(self):
        """当前投产输入变化时，计算净利率和投产倍数"""
        if not self._roi_bid_syncing and getattr(self, "roi_input_mode", "roi") == "roi":
            if self.current_roi_input.hasFocus():
                self._mark_roi_bid_manual_source("roi")
            self._sync_bid_from_roi()
        self._update_roi_derived_metrics()

    def on_transaction_bid_changed(self):
        """成交出价输入变化时，反算当前投产。"""
        if not self._roi_bid_syncing and getattr(self, "roi_input_mode", "roi") == "bid":
            if self.transaction_bid_input.hasFocus():
                self._mark_roi_bid_manual_source("transaction_bid")
            self._sync_roi_from_bid()
        self._update_roi_derived_metrics()
    
    def on_return_rate_changed(self):
        """退货率输入变化时，重新计算所有指标"""
        if hasattr(self, 'lbl_gross_break_even'):
            self.calculate_roi_metrics()

    def add_row(self):
        """添加新行"""
        idx = self.table.rowCount()
        self.table.insertRow(idx)
        
        # 第0列：AI优化按钮
        ai_widget = QWidget()
        ai_layout = QHBoxLayout(ai_widget)
        ai_layout.setContentsMargins(2, 0, 2, 0)
        
        ai_btn = QPushButton()
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons")
        ai_icon_path = os.path.join(icons_dir, "ai_spec.svg")
        ai_btn.setIcon(QIcon(ai_icon_path))
        ai_btn.setIconSize(QSize(18, 18))
        ai_btn.setFixedSize(28, 24)
        ai_btn.setToolTip("AI优化规格名称")
        ai_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        ai_btn.clicked.connect(lambda: self.ai_optimize_single_spec(idx))
        ai_layout.addWidget(ai_btn)
        ai_layout.addStretch()
        
        self.table.setCellWidget(idx, self.COL_AI, ai_widget)
        
        # 规格图列
        self._set_spec_image_cell(idx)

        # 规格名称列
        self._set_spec_name_cells(idx, f"新规格{idx+1}")
        # 关联编码列
        self.table.setItem(idx, self.COL_SPEC_CODE, self._mark_editable_spec_item(QTableWidgetItem("")))
        
        # 第3列：自动成本（不可编辑）
        cost_item = QTableWidgetItem("")
        cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(idx, self.COL_COST, cost_item)
        
        # 第4列：手动售价
        self.table.setItem(idx, self.COL_SALE_PRICE, self._mark_editable_spec_item(QTableWidgetItem("")))
        
        # 第5列：券后价（不可编辑）
        final_price_item = QTableWidgetItem("0.00")
        final_price_item.setFlags(final_price_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(idx, self.COL_FINAL_PRICE, final_price_item)
        
        # 第6列：毛利率（不可编辑）
        margin_item = QTableWidgetItem("0.00%")
        margin_item.setFlags(margin_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(idx, self.COL_MARGIN_RATE, margin_item)

        # 第7列：毛利润（不可编辑）
        profit_item = QTableWidgetItem("0.00")
        profit_item.setFlags(profit_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(idx, self.COL_GROSS_PROFIT, profit_item)
        
        # 第8列：权重
        self.table.setItem(idx, self.COL_WEIGHT, self._mark_editable_spec_item(QTableWidgetItem("0")))

        # 第9列：权重对比
        weight_compare_widget = QWidget()
        weight_compare_layout = QVBoxLayout(weight_compare_widget)
        weight_compare_layout.setContentsMargins(0, 2, 0, 2)
        weight_compare_layout.setAlignment(Qt.AlignCenter)
        weight_compare_value_label = QLabel("-")
        weight_compare_value_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
        weight_compare_sub_label = QLabel("较上周")
        weight_compare_sub_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        weight_compare_layout.addWidget(weight_compare_value_label)
        weight_compare_layout.addWidget(weight_compare_sub_label)
        self._set_unselectable_cell_widget(idx, self.COL_WEIGHT_COMPARE, weight_compare_widget)

        # 第10列：单量
        order_count_item = self._make_unselectable_item("0单")
        order_count_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(idx, self.COL_ORDER_COUNT, order_count_item)

        # 第11列：单量对比
        order_compare_widget = QWidget()
        order_compare_layout = QVBoxLayout(order_compare_widget)
        order_compare_layout.setContentsMargins(0, 2, 0, 2)
        order_compare_layout.setAlignment(Qt.AlignCenter)
        order_compare_value_label = QLabel("-")
        order_compare_value_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
        order_compare_sub_label = QLabel("较上周")
        order_compare_sub_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        order_compare_layout.addWidget(order_compare_value_label)
        order_compare_layout.addWidget(order_compare_sub_label)
        self._set_unselectable_cell_widget(idx, self.COL_ORDER_COMPARE, order_compare_widget)

        # 第12列：退款订单
        refund_orders_item = self._make_unselectable_item("无")
        refund_orders_item.setTextAlignment(Qt.AlignCenter)
        refund_orders_item.setForeground(QColor("#95a5a6"))
        self.table.setItem(idx, self.COL_REFUND_ORDERS, refund_orders_item)

        # 第13列：退款占比
        refund_ratio_item = self._make_unselectable_item("无")
        refund_ratio_item.setTextAlignment(Qt.AlignCenter)
        refund_ratio_item.setForeground(QColor("#95a5a6"))
        self.table.setItem(idx, self.COL_REFUND_RATIO, refund_ratio_item)

        self._refresh_spec_filter_options()
        self._apply_spec_filters()
        self._schedule_spec_table_column_resize()
        self.table.scrollToBottom()

    def on_cell_change(self, row, col):
        """单元格变化处理：包含智能权重平衡（防死循环版）"""
        
        # 🔒【关键】如果正在自动平衡中，直接返回，不要再次触发
        if self.is_balancing:
            return
        
        # 1. 如果是权重列变化，触发智能平衡
        if col == self.COL_WEIGHT:
            item = self.table.item(row, self.COL_WEIGHT)
            if not item:
                return

            try:
                text = item.data(Qt.DisplayRole) or ""
                new_val = float(text.replace("🔒", "").strip())
            except:
                return

            original_val = item.data(Qt.UserRole)
            print(f"[DEBUG on_cell_change] row={row}, new_val={new_val}, original_val={original_val}")
            if original_val is not None and abs(new_val - original_val) < 0.001:
                print(f"[DEBUG] 数值未变化，直接返回")
                return

            print(f"[DEBUG] 调用 auto_balance_weights")
            self.is_balancing = True
            try:
                self.auto_balance_weights(row)
                item.setData(Qt.UserRole, new_val)
            finally:
                self.is_balancing = False

            self.calculate_all_margins()
            self.update_remaining_weight_label()
            
        elif col == self.COL_SPEC_CODE:  # 关联编码变化 -> 查成本
            self.fetch_cost(row)
            self.calculate_row_margin(row)
            self.calculate_total_margin()
            
        elif col == self.COL_SALE_PRICE:  # 手动售价变化 -> 算单行毛利
            self.calculate_row_margin(row)
            self.calculate_total_margin()
            
        else:
            # 其他变化只刷新总毛利
            self.calculate_total_margin()
        
        # 确保毛保本等指标实时更新
        if hasattr(self, 'lbl_gross_break_even'):
            self.calculate_roi_metrics()
        self._schedule_spec_table_column_resize()
    
    def calculate_locked_weight_sum(self):
        """计算所有已锁定规格的权重总和"""
        total_locked = 0.0
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self.COL_WEIGHT)
            if not item:
                continue
            text = item.data(Qt.DisplayRole) or ""
            if text.startswith("🔒"):
                try:
                    val = float(text.replace("🔒", "").strip())
                    total_locked += val
                except:
                    pass
        return total_locked
    
    def get_remaining_weight(self):
        """获取剩余可分配权重"""
        locked_sum = self.calculate_locked_weight_sum()
        return max(0, 100.0 - locked_sum)
    
    def update_remaining_weight_label(self):
        """更新剩余可分配权重标签（已移除显示）"""
        pass

    def calculate_all_margins(self):
        """辅助函数：刷新所有行的单行毛利和总毛利"""
        for r in range(self.table.rowCount()):
            self.calculate_row_margin(r)
        self.calculate_total_margin()

    def auto_balance_weights(self, changed_row):
        """自动平衡权重：将剩余权重均分给其他未锁定的行"""
        print(f"[DEBUG auto_balance_weights] called with changed_row={changed_row}")
        rows = self.table.rowCount()
        if rows <= 1:
            return

        # 1. 获取当前修改行的新权重值
        item_changed = self.table.item(changed_row, self.COL_WEIGHT)
        if not item_changed:
            return

        try:
            text = item_changed.data(Qt.DisplayRole) or ""
            new_val = float(text.replace("🔒", "").strip())
        except:
            return

        # 检查权重是否真的发生了变化（对比 UserRole 中保存的原始值）
        original_val = item_changed.data(Qt.UserRole)
        if original_val is not None and abs(new_val - original_val) < 0.001:
            return
        
        # 2. 计算剩余可用权重
        # 修复：先计算其他所有锁定行的总和，然后计算剩余可用权重
        all_locked_sum = 0.0
        for r in range(rows):
            if r == changed_row:
                continue
            
            item = self.table.item(r, self.COL_WEIGHT)
            if not item:
                continue
            
            t = item.data(Qt.DisplayRole) or ""
            if t.startswith("🔒"):
                try:
                    locked_val = float(t.replace("🔒", "").strip())
                    all_locked_sum += locked_val
                except:
                    pass
        
        # 检查当前行是否锁定，以及总锁定权重是否超过100
        current_text = item_changed.data(Qt.DisplayRole) or ""
        is_current_locked = current_text.startswith("🔒")
        
        remaining_weight = 100.0 - all_locked_sum - new_val
        
        # 如果当前行已锁定且总锁定超过100，给出警告并修正
        if is_current_locked and (all_locked_sum + new_val) > 100.0:
            max_allowed = max(0, 100.0 - all_locked_sum)
            item_changed.setData(Qt.DisplayRole, f"🔒 {max_allowed:.2f}")
            QMessageBox.warning(self, "权重超限", f"锁定权重总和不能超过100%！\n已自动调整为：{max_allowed:.2f}%")
            remaining_weight = max_allowed  # 更新剩余权重
        
        # 3. 统计其他未锁定的行数
        other_unlocked_rows = []
        for r in range(rows):
            if r == changed_row:
                continue # 跳过自己
            
            item = self.table.item(r, self.COL_WEIGHT)
            if not item:
                continue
            
            t = item.data(Qt.DisplayRole) or ""
            # 如果该行被锁定，则不参与自动分配
            if t.startswith("🔒"):
                # 如果其他行被锁定，它的权重也要从剩余里扣除吗？
                # 策略 A：锁定行权重固定，剩余权重只分给未锁定行。（推荐）
                # 策略 B：锁定行也占用总额，导致总和可能不等于100。（不推荐）
                # 我们采用策略 A：锁定行视为“固定支出”，剩下的钱大家分。
                
                # 所以，我们需要先从 remaining_weight 里减去锁定行的权重
                pass
            else:
                other_unlocked_rows.append(r)
        
        # 4. 执行分配
        if len(other_unlocked_rows) > 0:
            # 防止除零或负数
            if remaining_weight < 0:
                # 如果剩余权重是负的（比如你设了90，但其他锁定行占了20），提示一下或者强制设为0
                # 这里我们温柔一点，直接设为0，让用户自己调整
                avg = 0.0
            else:
                avg = remaining_weight / len(other_unlocked_rows)
            
            # 更新其他行
            for r in other_unlocked_rows:
                item = self.table.item(r, self.COL_WEIGHT)
                if item:
                    # 保持原来的锁定状态（虽然这里肯定是未锁定的）
                    item.setData(Qt.DisplayRole, f"{avg:.2f}")
        else:
            # 如果其他行全被锁定了，那就没办法分了，保持现状
            pass

    def fetch_cost(self, row):
        """根据关联编码获取成本"""
        code_item = self.table.item(row, self.COL_SPEC_CODE)
        code = code_item.text().strip() if code_item else ""
        if not code:
            item_cost = self.table.item(row, self.COL_COST)
            if item_cost: item_cost.setText("")
            self.calculate_row_margin(row)
            self.calculate_total_margin()
            return
        
        res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (code,))
        if res:
            cost = res[0][0]
            item_cost = self.table.item(row, self.COL_COST)
            if item_cost: item_cost.setText(f"{cost:.2f}")
            self.calculate_row_margin(row)
            self.calculate_total_margin()
        else:
            item_cost = self.table.item(row, self.COL_COST)
            if item_cost: item_cost.setText("")
            item_margin = self.table.item(row, self.COL_MARGIN_RATE)
            if item_margin: item_margin.setText("未找到成本")
            item_profit = self.table.item(row, self.COL_GROSS_PROFIT)
            if item_profit: item_profit.setText("0.00")
            self.calculate_total_margin()

    def calculate_row_margin(self, row):
        """计算单行毛利"""
        item_cost = self.table.item(row, self.COL_COST)
        item_price = self.table.item(row, self.COL_SALE_PRICE)
        item_final_price = self.table.item(row, self.COL_FINAL_PRICE)
        item_margin = self.table.item(row, self.COL_MARGIN_RATE)
        item_profit = self.table.item(row, self.COL_GROSS_PROFIT)
        
        if not item_cost or not item_price or not item_margin:
            return

        cost_text = item_cost.text()
        price_text = item_price.text()
        
        if "未找到" in cost_text:
            return

        try:
            if not cost_text or not price_text:
                if item_final_price:
                    item_final_price.setText("0.00")
                item_margin.setText("0.00%")
                if item_profit:
                    item_profit.setText("0.00")
                return
            
            cost = float(cost_text)
            price = float(price_text)
            
            # 获取最大优惠金额
            coupon = float(self.coupon_input.text()) if self.coupon_input.text() else 0
            new_customer = float(self.new_customer_input.text()) if self.new_customer_input.text() else 0
            max_discount = max(coupon, new_customer)
            
            # 应用最大优惠后计算券后价
            final_price = price - max_discount
            if item_final_price:
                item_final_price.setText(f"{final_price:.2f}")

            gross_profit = final_price - cost
            if item_profit:
                item_profit.setText(f"{gross_profit:.2f}")
            
            # 计算毛利
            if final_price > 0 and cost > 0:
                margin = ((final_price - cost) / final_price) * 100
                item_margin.setText(f"{margin:.2f}%")
            elif final_price <= 0:
                item_margin.setText("价格过低")
            else:
                item_margin.setText("0.00%")
        except:
            if item_final_price:
                item_final_price.setText("错误")
            if item_profit:
                item_profit.setText("错误")
            item_margin.setText("错误")

    def calculate_all(self):
        """重算所有行"""
        for r in range(self.table.rowCount()):
            self.calculate_row_margin(r)
        self.calculate_total_margin()

    def calculate_total_margin(self):
        """计算综合毛利率（使用表格显示的权重）"""
        total_weighted_margin = 0.0
        total_weight = 0.0

        coupon = float(self.coupon_input.text()) if self.coupon_input.text() else 0
        new_customer = float(self.new_customer_input.text()) if self.new_customer_input.text() else 0
        max_discount = max(coupon, new_customer)

        for r in range(self.table.rowCount()):
            price_item = self.table.item(r, self.COL_SALE_PRICE)
            code_item = self.table.item(r, self.COL_SPEC_CODE)
            margin_item = self.table.item(r, self.COL_MARGIN_RATE)
            weight_item = self.table.item(r, self.COL_WEIGHT)

            if not all([price_item, code_item, margin_item, weight_item]):
                continue

            try:
                price = float(price_item.text())
                code = code_item.text()

                margin_text = margin_item.text().replace("%", "").replace("％", "").strip()
                margin_val = float(margin_text) if margin_text else 0.0

                weight_text = weight_item.text().replace("🔒", "").replace("%", "").replace("％", "").strip()
                weight_val = float(weight_text) if weight_text else 0.0

                if price <= 0 or weight_val <= 0:
                    continue

                cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (code,))
                cost = float(cost_res[0][0]) if cost_res else 0.0

                final_price = price - max_discount

                if final_price > 0 and cost > 0:
                    margin = (final_price - cost) / final_price
                    total_weighted_margin += margin * weight_val
                    total_weight += weight_val
            except Exception:
                continue

        if total_weight > 0:
            final_margin = (total_weighted_margin / total_weight) * 100
            self.lbl_total_margin.setText(f"当前综合毛利率：{final_margin:.2f}%")
        else:
            self.lbl_total_margin.setText("当前综合毛利率：0.00%")

    def open_profit_calculator(self):
        """打开利润计算器对话框"""
        margin_text = self.lbl_total_margin.text()
        try:
            margin_rate = float(margin_text.replace("%", "").replace("当前综合毛利率：", "").strip())
        except ValueError:
            margin_rate = 0.0
        
        avg_price = self.calculate_weighted_avg_price()
        
        dialog = ProfitCalculatorDialog(margin_rate, avg_price, self.product_id, self.product_name, "product", self, self.db)
        dialog.show()
    
    def ai_optimize_single_spec(self, row):
        """AI优化单个规格名称"""
        item = self.table.item(row, self.COL_SPEC_NAME)
        if not item or not item.text().strip():
            QMessageBox.warning(self, "⚠️ 提示", "该规格没有名称！")
            return
        
        original_name = self._compose_spec_name(row)
        
        api_key = self.db.get_setting("ai_api_key", "")
        if not api_key:
            QMessageBox.warning(self, "⚠️ 提示", "请先在API配置中设置API Key！")
            return

        self._show_strategy_config_dialog(original_name, row)

    def _show_strategy_config_dialog(self, original_name, row):
        """显示规格优化策略标尺配置窗口。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🤖 规格优化策略")
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)

        title = QLabel("请选择本次规格优化的策略方向")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50; padding: 8px;")
        layout.addWidget(title)

        spec_label = QLabel(f"当前规格：{original_name}")
        spec_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 0 8px 8px 8px;")
        spec_label.setWordWrap(True)
        layout.addWidget(spec_label)

        conversion_slider, conversion_spin, conversion_desc = self._create_axis_control(
            layout,
            "转化方向",
            "明显劝退",
            "中性",
            "强购买引导",
            self._describe_conversion_level
        )
        price_slider, price_spin, price_desc = self._create_axis_control(
            layout,
            "价格人群",
            "低价人群",
            "中性",
            "高价人群",
            self._describe_price_audience_level
        )

        hint_card = QWidget()
        hint_card.setStyleSheet("""
            QWidget {
                background-color: #fffdf7;
                border: 1px solid #f1c40f;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        hint_layout = QVBoxLayout(hint_card)
        hint_layout.setContentsMargins(10, 8, 10, 8)
        hint_label = QLabel("本次补充提示（可选）")
        hint_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50;")
        hint_layout.addWidget(hint_label)
        hint_input = QLineEdit()
        hint_input.setPlaceholderText("例如：这是铁棍山药，主打粉糯口感和日常滋补")
        hint_input.setMaxLength(160)
        hint_input.setStyleSheet("padding: 7px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;")
        hint_layout.addWidget(hint_input)
        hint_desc = QLabel("仅本次调用使用，不保存到数据库。")
        hint_desc.setStyleSheet("font-size: 10px; color: #6c757d;")
        hint_layout.addWidget(hint_desc)
        layout.addWidget(hint_card)

        def open_preview():
            dialog.accept()
            self._show_optimization_preview_dialog(
                original_name,
                conversion_level=conversion_spin.value(),
                price_audience_level=price_spin.value(),
                custom_hint=hint_input.text().strip(),
                row=row
            )

        btn_layout = QHBoxLayout()

        btn_common_rules = QPushButton("📋 通用规则设置")
        btn_common_rules.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 8px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        btn_common_rules.clicked.connect(lambda: self._show_common_rules_dialog(dialog))
        btn_layout.addWidget(btn_common_rules)

        btn_layout.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_cancel)

        btn_preview = QPushButton("进入预览")
        btn_preview.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 9px 22px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        btn_preview.clicked.connect(open_preview)
        btn_layout.addWidget(btn_preview)

        layout.addLayout(btn_layout)

        dialog.exec_()

    def _create_axis_control(self, parent_layout, title, left_text, center_text, right_text, describe_func):
        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50;")
        header.addWidget(title_label)
        header.addStretch()
        desc_label = QLabel(describe_func(0))
        desc_label.setStyleSheet("font-size: 12px; color: #3498db; font-weight: bold;")
        header.addWidget(desc_label)
        layout.addLayout(header)

        axis_layout = QHBoxLayout()
        left_label = QLabel(left_text)
        left_label.setStyleSheet("font-size: 11px; color: #e74c3c;")
        axis_layout.addWidget(left_label)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(-10, 10)
        slider.setValue(0)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(1)
        axis_layout.addWidget(slider, 1)

        spin = QSpinBox()
        spin.setRange(-10, 10)
        spin.setValue(0)
        spin.setFixedWidth(70)
        axis_layout.addWidget(spin)

        right_label = QLabel(right_text)
        right_label.setStyleSheet("font-size: 11px; color: #27ae60;")
        axis_layout.addWidget(right_label)
        layout.addLayout(axis_layout)

        center_label = QLabel(f"-10 {left_text}    0 {center_text}    +10 {right_text}")
        center_label.setAlignment(Qt.AlignCenter)
        center_label.setStyleSheet("font-size: 10px; color: #6c757d;")
        layout.addWidget(center_label)

        def sync_from_slider(value):
            spin.blockSignals(True)
            spin.setPrefix("+" if value > 0 else "")
            spin.setValue(value)
            spin.blockSignals(False)
            desc_label.setText(describe_func(value))

        def sync_from_spin(value):
            spin.setPrefix("+" if value > 0 else "")
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
            desc_label.setText(describe_func(value))

        slider.valueChanged.connect(sync_from_slider)
        spin.valueChanged.connect(sync_from_spin)
        parent_layout.addWidget(card)
        return slider, spin, desc_label

    def _show_optimization_preview_dialog(self, original_name, conversion_level=0, price_audience_level=0, custom_hint="", parent_dialog=None, row=None):
        """显示优化预览窗口：展示条件、选择的提示词、生成预览"""
        dialog = QDialog(parent_dialog or self)
        dialog.setWindowTitle("🤖 规格优化预览")
        dialog.resize(800, 650)
        main_layout = QVBoxLayout(dialog)

        header = QLabel("🤖 规格优化预览")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        main_layout.addWidget(header)

        mode_color = "#27ae60" if conversion_level >= 0 else "#e74c3c"
        mode_icon = self._describe_conversion_level(conversion_level)
        price_icon = self._describe_price_audience_level(price_audience_level)
        mode_label = QLabel(f"当前策略：转化方向 {conversion_level:+d}（{mode_icon}）｜价格人群 {price_audience_level:+d}（{price_icon}）")
        mode_label.setStyleSheet(f"font-size: 13px; color: {mode_color}; font-weight: bold; padding: 5px;")
        main_layout.addWidget(mode_label)

        separator_top = QFrame()
        separator_top.setFrameShape(QFrame.HLine)
        separator_top.setStyleSheet("color: #dee2e6;")
        main_layout.addWidget(separator_top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(12)

        spec_info = self._get_spec_info_by_name(original_name)
        margin_rate = spec_info.get("margin_rate", 0)
        sale_price = spec_info.get("sale_price", "0")
        cost_price = spec_info.get("cost_price", "0")
        margin_value = spec_info.get("margin_value", "0")

        condition_card = QWidget()
        condition_card.setStyleSheet(f"""
            QWidget {{
                background-color: #f8f9fa;
                border-left: 4px solid #3498db;
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        cond_layout = QVBoxLayout(condition_card)
        cond_layout.setContentsMargins(10, 6, 10, 6)
        cond_layout.setSpacing(6)

        cond_title = QLabel("📊 当前规格条件")
        cond_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50;")
        cond_layout.addWidget(cond_title)

        row1 = QWidget()
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(20, 2, 20, 2)
        row1_layout.setSpacing(15)

        for label_text, value_text in [("规格名称", original_name), ("售价", sale_price), ("成本", cost_price)]:
            label = QLabel(f"{label_text}：")
            label.setStyleSheet("font-size: 11px; color: #6c757d; font-weight: bold; min-width: 60px;")
            row1_layout.addWidget(label)
            value = QLabel(value_text)
            value.setStyleSheet("font-size: 11px; color: #2c3e50;")
            row1_layout.addWidget(value)

        row1_layout.addStretch()
        cond_layout.addWidget(row1)

        row2 = QWidget()
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(20, 2, 20, 2)
        row2_layout.setSpacing(15)

        for label_text, value_text in [("毛利", margin_value), ("毛利率", f"{margin_rate:.2f}%")]:
            label = QLabel(f"{label_text}：")
            label.setStyleSheet("font-size: 11px; color: #6c757d; font-weight: bold; min-width: 60px;")
            row2_layout.addWidget(label)
            value = QLabel(value_text)
            value.setStyleSheet("font-size: 11px; color: #2c3e50;")
            row2_layout.addWidget(value)

        row2_layout.addStretch()
        cond_layout.addWidget(row2)

        scroll_layout.addWidget(condition_card)

        price_relation = self._get_price_relation_info(row, original_name)
        relation_color = "#27ae60" if price_relation.get("is_lowest") else "#e67e22"
        relation_label = QLabel(f"💰 价格相对位置：{price_relation.get('summary', '暂无价格数据')}")
        relation_label.setStyleSheet(f"font-size: 12px; color: {relation_color}; font-weight: bold; padding: 8px; background-color: #f8f9fa; border-radius: 4px;")
        scroll_layout.addWidget(relation_label)

        product_memo = self._get_product_memo()
        product_memo_label = QLabel(f"🎯 主界面图片备注：{product_memo if product_memo else '未填写主界面图片备注'}")
        product_memo_label.setWordWrap(True)
        product_memo_label.setStyleSheet("font-size: 12px; color: #155724; font-weight: bold; padding: 8px; background-color: #f3fbf5; border-radius: 4px;")
        scroll_layout.addWidget(product_memo_label)

        hint_text = custom_hint.strip() if custom_hint else ""
        hint_label = QLabel(f"📝 本次补充提示：{hint_text if hint_text else '未填写本次补充提示'}")
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("font-size: 12px; color: #8a6d3b; font-weight: bold; padding: 8px; background-color: #fffdf7; border-radius: 4px;")
        scroll_layout.addWidget(hint_label)

        tags_card = QWidget()
        tags_layout = QVBoxLayout(tags_card)
        tags_layout.setContentsMargins(10, 8, 10, 8)
        tags_layout.setSpacing(8)

        tags_title = QLabel("🏷️ 当前调用的提示词")
        tags_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50;")
        tags_layout.addWidget(tags_title)

        tags_flow = QWidget()
        tags_flow_layout = QHBoxLayout(tags_flow)
        tags_flow_layout.setContentsMargins(5, 0, 5, 0)
        tags_flow_layout.setSpacing(6)

        tag_configs = []

        product_memo = self._get_product_memo()
        store_memo = self._get_store_memo()

        forbidden = self.db.get_setting("ai_spec_forbidden_words", "")
        if forbidden:
            tag_configs.append(("🚫 违禁词", "#e74c3c"))

        product_info = self.db.get_setting("ai_product_info_prompt", "")
        if product_info:
            tag_configs.append(("🛒 产品信息", "#3498db"))

        product_attr = self.db.get_setting("ai_spec_attr_prompt", "")
        if product_attr:
            tag_configs.append(("📦 商品属性", "#9b59b6"))

        if product_memo:
            tag_configs.append(("🎯 主界面图片备注", "#1e8449"))

        if self.db.get_setting("ai_spec_base_prompt", ""):
            tag_configs.append(("🧩 基础生成规则", "#16a085"))
        if self.db.get_setting("ai_spec_conversion_axis_prompt", ""):
            tag_configs.append((f"🎯 转化方向：{conversion_level:+d} {mode_icon}", mode_color))
        if self.db.get_setting("ai_spec_price_audience_prompt", ""):
            tag_configs.append((f"👥 价格人群：{price_audience_level:+d} {price_icon}", "#2980b9"))
        if self.db.get_setting("ai_spec_price_relation_prompt", ""):
            tag_configs.append(("💰 价格相对位置", relation_color))
        if hint_text:
            tag_configs.append(("📝 本次补充提示", "#f39c12"))

        if store_memo:
            tag_configs.append(("📋 店铺大纲", "#6c757d"))

        for tag_text, color in tag_configs:
            tag = QLabel(tag_text)
            tag.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    color: white;
                    padding: 6px 12px;
                    border-radius: 12px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
            tags_flow_layout.addWidget(tag)

        tags_flow_layout.addStretch()
        tags_layout.addWidget(tags_flow)

        btn_view_prompts = QPushButton("📋 查看提示词详情")
        btn_view_prompts.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 8px 15px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        btn_view_prompts.clicked.connect(lambda: self._show_prompt_detail_dialog(
            dialog, conversion_level, price_audience_level, price_relation, original_name, row, custom_hint
        ))
        tags_layout.addWidget(btn_view_prompts)

        scroll_layout.addWidget(tags_card)

        full_prompt = self._build_full_prompt_text_optimized(original_name, conversion_level, price_audience_level, row, custom_hint)
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            token_count = len(enc.encode(full_prompt))
            token_hint = f"📊 预计Token数量：约 {token_count} tokens"
        except ImportError:
            estimated_tokens = len(full_prompt) // 4
            token_hint = f"📊 预计Token数量：约 {estimated_tokens} tokens（粗略估算）"

        token_card = QWidget()
        token_card.setStyleSheet("""
            QWidget {
                background-color: #f3e5f5;
                border: 1px solid #ce93d8;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        token_layout = QVBoxLayout(token_card)
        token_layout.setContentsMargins(10, 6, 10, 6)
        token_label = QLabel(token_hint)
        token_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #9b59b6;")
        token_layout.addWidget(token_label)
        saved_label = QLabel("💡 标尺策略：转化方向 + 价格人群 + 价格相对位置动态拼装")
        saved_label.setStyleSheet("font-size: 11px; color: #27ae60;")
        token_layout.addWidget(saved_label)
        scroll_layout.addWidget(token_card)

        preview_card = self._create_card("📤 预期生成的规格名称", [
            ("数量", "10个不同风格的规格名称"),
            ("格式", "保留原规格核心词，约30字左右"),
            ("风格", "不同命名风格，不重复原规格名称"),
        ], "#f39c12")
        scroll_layout.addWidget(preview_card)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        separator_bottom = QFrame()
        separator_bottom.setFrameShape(QFrame.HLine)
        separator_bottom.setStyleSheet("color: #dee2e6;")
        main_layout.addWidget(separator_bottom)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 12px 25px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        btn_cancel.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        btn_generate = QPushButton("🚀 生成规格名称")
        btn_generate.setStyleSheet(f"""
            QPushButton {{
                background-color: {mode_color};
                color: white;
                padding: 12px 30px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {mode_color.replace('27ae60', '219a52').replace('e74c3c', 'c0392b')};
            }}
        """)
        btn_generate.clicked.connect(lambda: self._start_optimize_from_preview(
            original_name, conversion_level, price_audience_level, custom_hint, dialog, row
        ))
        btn_layout.addWidget(btn_generate)

        main_layout.addLayout(btn_layout)

        dialog.exec_()

    def _start_optimize_from_preview(self, original_name, conversion_level=0, price_audience_level=0, custom_hint="", parent_dialog=None, row=None):
        """从预览窗口确认并开始优化"""
        if parent_dialog:
            parent_dialog.accept()
        if row is None:
            row = self.table.currentRow()
        if row >= 0:
            self._do_ai_optimize(row, original_name, conversion_level, price_audience_level, custom_hint)

    def _create_card(self, title, items, color):
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: #f8f9fa;
                border-left: 4px solid {color};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)
        for key, value in items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(20, 2, 10, 2)
            key_label = QLabel(key + "：")
            key_label.setStyleSheet("font-size: 11px; color: #6c757d; font-weight: bold; min-width: 80px;")
            row_layout.addWidget(key_label)
            value_label = QLabel(value)
            value_label.setStyleSheet("font-size: 11px; color: #2c3e50;")
            value_label.setWordWrap(True)
            row_layout.addWidget(value_label)
            row_layout.addStretch()
            layout.addWidget(row)
        return card

    def _get_spec_info_by_name(self, spec_name):
        specs = self._get_specs_with_margin_details()
        for spec in specs:
            if spec.get("spec_name", "") == spec_name:
                return spec
        return {"spec_name": spec_name, "sale_price": "0", "cost_price": "0",
                "margin_value": "0", "margin_rate": 0}

    def _get_specs_with_margin_details(self):
        try:
            rows = []
            if hasattr(self, "table"):
                for r in range(self.table.rowCount()):
                    code_item = self.table.item(r, self.COL_SPEC_CODE)
                    price_item = self.table.item(r, self.COL_SALE_PRICE)
                    spec_name = self._compose_spec_name(r)
                    if not spec_name:
                        continue
                    price_val = None
                    if price_item:
                        try:
                            price_text = price_item.text().strip().replace("¥", "").replace(",", "")
                            price_val = float(price_text) if price_text else None
                        except (ValueError, TypeError):
                            price_val = None
                    rows.append((spec_name, code_item.text().strip() if code_item else "", price_val))
            if not rows:
                rows = self.db.safe_fetchall(
                    "SELECT spec_name, spec_code, sale_price FROM product_specs WHERE product_id=?",
                    (self.product_id,)
                )
        except Exception:
            return []

        if not rows:
            return []

        store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.product_id,))
        store_id = store_rows[0][0] if store_rows and store_rows[0] else None

        results = []
        for row in rows:
            spec_name, spec_code, sale_price = row
            cost_price = 0.0
            if spec_code:
                cost_res = self.db.safe_fetchall(
                    "SELECT cost_price FROM cost_library WHERE spec_code=?",
                    (spec_code,)
                )
                if cost_res and cost_res[0][0]:
                    cost_price = float(cost_res[0][0])

            try:
                sale_price_float = float(sale_price) if sale_price else 0
                cost_price_float = float(cost_price)
                if sale_price_float > 0 and cost_price_float > 0:
                    margin_value = sale_price_float - cost_price_float
                    margin_rate = margin_value / sale_price_float
                else:
                    margin_value = 0
                    margin_rate = 0
            except (ValueError, TypeError, ZeroDivisionError):
                margin_value = 0
                margin_rate = 0

            results.append({
                "spec_name": spec_name,
                "sale_price": f"{sale_price_float:.2f}" if sale_price_float > 0 else "--",
                "cost_price": f"{cost_price:.2f}" if cost_price > 0 else "--",
                "margin_value": f"{margin_value:.2f}" if margin_value != 0 else "--",
                "margin_rate": margin_rate,
            })

        return results

    def _describe_conversion_level(self, level):
        level = int(level)
        if level >= 9:
            return "超强购买引导"
        if level >= 6:
            return "强购买引导"
        if level >= 3:
            return "轻度转化引导"
        if level > 0:
            return "微弱转化引导"
        if level == 0:
            return "中性表达"
        if level <= -9:
            return "明显劝退"
        if level <= -6:
            return "强弱化购买意愿"
        if level <= -3:
            return "轻度弱化购买意愿"
        return "微弱弱化购买意愿"

    def _describe_price_audience_level(self, level):
        level = int(level)
        if level >= 9:
            return "高价精品人群"
        if level >= 6:
            return "高价品质人群"
        if level >= 3:
            return "偏品质人群"
        if level > 0:
            return "轻度品质倾向"
        if level == 0:
            return "中性人群"
        if level <= -9:
            return "极度低价敏感"
        if level <= -6:
            return "低价敏感"
        if level <= -3:
            return "偏性价比人群"
        return "轻度优惠倾向"

    def _get_table_specs_for_ai(self):
        """从当前表格读取规格信息，包含尚未保存的价格。"""
        specs = []
        for r in range(self.table.rowCount()):
            price_item = self.table.item(r, self.COL_SALE_PRICE)
            code_item = self.table.item(r, self.COL_SPEC_CODE)
            spec_name = self._compose_spec_name(r)
            if not spec_name:
                continue
            price = None
            if price_item:
                try:
                    price_text = price_item.text().strip().replace("¥", "").replace(",", "")
                    price = float(price_text) if price_text else None
                except (ValueError, TypeError):
                    price = None
            specs.append({
                "row": r,
                "name": spec_name,
                "code": code_item.text().strip() if code_item else "",
                "price": price,
            })
        return specs

    def _get_price_relation_info(self, row=None, original_name=""):
        specs = self._get_table_specs_for_ai()
        priced = [s for s in specs if s.get("price") is not None]
        current = None
        if row is not None:
            for spec in specs:
                if spec["row"] == row:
                    current = spec
                    break
        if current is None and original_name:
            for spec in specs:
                if spec["name"] == original_name:
                    current = spec
                    break
        if current is None:
            current = {"name": original_name, "price": None, "row": row}

        current_price = current.get("price")
        if current_price is None or not priced:
            return {
                "current_price": current_price,
                "min_price": None,
                "max_price": None,
                "is_lowest": False,
                "is_highest": False,
                "summary": "当前规格价格缺失，禁止使用最便宜、最低价等绝对价格词",
                "specs": specs,
            }

        prices = [s["price"] for s in priced]
        min_price = min(prices)
        max_price = max(prices)
        lower_count = len([p for p in prices if p < current_price])
        higher_count = len([p for p in prices if p > current_price])
        is_lowest = abs(current_price - min_price) < 0.0001
        is_highest = abs(current_price - max_price) < 0.0001

        if is_lowest and is_highest:
            summary = f"当前规格 ¥{current_price:.2f}，所有有价规格价格一致"
        elif is_lowest:
            summary = f"当前规格 ¥{current_price:.2f}，为当前最低价"
        elif is_highest:
            summary = f"当前规格 ¥{current_price:.2f}，为当前最高价，高于最低价 ¥{min_price:.2f}"
        else:
            summary = f"当前规格 ¥{current_price:.2f}，高于最低价 ¥{min_price:.2f}，低于最高价 ¥{max_price:.2f}"

        return {
            "current_price": current_price,
            "min_price": min_price,
            "max_price": max_price,
            "lower_count": lower_count,
            "higher_count": higher_count,
            "is_lowest": is_lowest,
            "is_highest": is_highest,
            "summary": summary,
            "specs": specs,
        }

    def _get_default_spec_base_prompt(self):
        return """【基础生成规则】
你是电商SKU规格命名专家，也是一名懂消费者心理的运营策划。请围绕当前规格生成10个不同风格的新规格名称。

【内部发散步骤】（只在心里完成，不要输出分析过程）
1. 先识别产品主体词：从商品标题、产品信息、主界面图片备注、本次补充提示、原规格中提取最短但清楚的商品主体名。
2. 每条SKU正文都必须包含产品主体词或更明确的同义主体，不能优化后只剩精品装、家庭装、尝鲜款、礼盒装这类空泛规格。
3. 再识别购买人群和购买痛点：优先结合主界面图片备注判断该链接主要针对的人群，再思考谁会买、为什么买、担心什么、在什么场景用、和其他规格怎么比较。
4. 针对不同品类提取可感知价值：食品看口感、营养成分、烹饪/食用场景；日用品看材质、耐用、收纳、家庭场景；服饰看面料、版型、季节、人群；工具看效率、适配、耐用和使用场景。
5. 10个结果必须覆盖不同角度，例如品质型、场景型、人群型、规格对比型、礼赠型、安心型、复购型、尝鲜型、家庭囤货型、专业推荐型。
6. 禁止10条只是替换少量形容词，禁止全部堆叠甄选、精品、高品质这类同质词。

【目标人群备注】
主界面图片备注：{product_memo}
这条备注代表当前商品链接长期想打的目标人群，是命名的重要方向。
如果本次补充提示和主界面图片备注同时存在，本次补充提示用于临时细化，主界面图片备注用于判断长期目标人群和核心消费场景。
正向转化时围绕该目标人群的痛点、期待和购买理由发散；负向转化时让该目标人群之外的用户感觉当前规格不适合自己。

【合规边界】
可以基于已给出的商品信息发散表达，但不能编造具体产地、认证、检测、治疗功效、药效、销量数据、获奖背书。
食品类可以表达营养、口感、日常滋补、早餐/煲汤/家庭餐等场景，但不能写治疗、降血糖、治病、药用承诺。

必须保留原规格的核心信息，如数量、重量、尺码、颜色、款式、组合关系。
不要直接复制原规格名称，要在原规格基础上做清晰、可读、有运营目的的改写。
不要输出独立风格标签，不要把风格写成单独前缀；风格差异必须融入SKU正文，例如通过卖点、人群、场景、规格对比、语气结构体现。
SKU名称尽量接近35字，最多不超过40字。
强制禁止使用中文逗号、英文逗号、顿号、句号、分号、冒号、感叹号、问号、斜杠、反斜杠、下划线、星号、项目符号。
允许使用的符号只有：- + 丨 () [] 【】
可以少量使用允许符号让10条在结构上有差异，但不要为了符号牺牲可读性。
禁止出现"原规格"、"新规格"、"优化后"等解释性前缀。
直接输出10个新规格名，一行一个，不要解释。"""

    def _get_default_conversion_axis_prompt(self):
        return """【转化方向标尺规则】
当前转化方向数值：{conversion_level}，说明：{conversion_desc}。
正向转化：先识别购买人群，再围绕人群痛点写购买理由，例如省心、适合家庭、适合送礼、适合囤货、适合尝鲜、适合高频使用。
数值越接近+10，越要让顾客觉得这个规格就是最适合自己的选择，但不要只写热销、推荐、放心，要写具体场景和具体价值。
数值在+1到+5时，只做轻度购买引导，不要过度促销。
数值为0时，保持客观中性，只优化清晰度、主体识别和规格差异。
负向转化：目标不是说产品差，而是让非目标用户主动放弃当前规格，倾向选择其他规格。
负向转化必须按强度分层：
-1到-4：轻度筛选，表达更适合特定需求，避免人人适合。
-5到-7：明显劝退，必须让非目标用户感觉不太适合自己，可写需求不匹配、轻用无需、先看其他规格。
-8到-10：强劝退，必须出现筛选门槛词，例如慎选、先别选、轻需求无需、普通家用看基础款、仅适合高频、仅适合送礼、仅适合囤货、仅适合重度需求。
数值越接近-10，越不能写成促进购买文案，禁止出现放心选、值得入、强推、闭眼入、必选、人人适合、品质必选等强转化表达。
高价人群负向时尤其要强调只适合高频使用、重度需求、送礼、囤货、大规格、高标准用户；普通用户会觉得用不上、没必要、需求不匹配。
低价人群负向时强调预算不匹配、轻用无需选、先看基础规格、入门不建议。
负向表达必须合规：不能编造质量问题、瑕疵、假货、风险、差评，只能用规格小/大、预算不匹配、使用频率不匹配、场景不匹配、建议对比其他规格等表达。"""

    def _get_default_price_audience_prompt(self):
        return """【价格人群标尺规则】
当前价格人群数值：{price_audience_level}，说明：{price_audience_desc}。
数值越接近+10，越面向高价品质人群：不要只写甄选、精品、高品质，要说明顾客能感知到的价值依据，如口感/营养/材质/工艺/耐用/省心/礼赠/家庭场景/长期使用价值。
高价人群不强调便宜、优惠、低价、划算，重点表达值不值、好不好、适不适合、是否省心。
当转化方向为负数且价格人群偏高时，劝退方式要变成“高门槛筛选”：强调该规格更适合高标准用户、重度使用者、礼赠场景、大规格需求、明确品质追求者，让普通用户觉得没必要选它。
高价人群劝退不要说贵、不划算、质量差，而要用“更适合懂品质/送礼/长期囤用/高频使用/对口感材质有要求的人”来抬高选择门槛。
高价人群负向必须是筛选式劝退，不要写成高端推荐，不要夸到所有人都想买。
高价人群负向禁止写成“值得买、放心选、推荐入手、品质必选、人人适合、闭眼入、强推、放心囤”等促进转化表达。
如果转化方向接近-10且价格人群偏高，SKU中应体现门槛或限制，例如“高频才合适”“送礼再选”“大规格慎选”“轻需求先别选”“普通家用看基础款”。
数值越接近-10，越面向低价敏感人群：可以使用实惠、优惠、性价比、入门、尝鲜、囤货、家庭装等表达，但必须受价格相对位置限制。
当转化方向为负数且价格人群偏低时，可以强调预算不匹配、入门不建议、日常轻用无需选择、可先看更基础规格，但不能误导当前规格是最低价。
数值为0时，不明显偏向高价或低价，只保证规格名称清楚、真实、易比较。
无论数值如何，都不能和当前规格的真实价格相对位置冲突。"""

    def _get_default_price_relation_prompt(self):
        return """【价格相对位置规则】
{price_relation_summary}
所有规格当前表格价格：
{spec_price_layout}
如果当前规格不是当前最低价，禁止使用：最便宜、最低价、全网低价、超低价、底价、白菜价、亏本价。
如果当前规格是最高价，应优先解释价值、品质、容量、组合、适用人群，不要伪装成低价款。
如果当前规格是最低价，可以使用入门、实惠、低门槛、尝鲜等词，但仍不能夸大为全网最低。
生成时必须参考所有规格价格，保证命名不会误导顾客。"""

    def _format_spec_price_layout(self, specs):
        if not specs:
            return "暂无规格价格数据"
        lines = []
        for i, spec in enumerate(specs, 1):
            price = spec.get("price")
            price_text = f"¥{price:.2f}" if price is not None else "价格缺失"
            lines.append(f"{i}. {spec.get('name', '')} - {price_text}")
        return "\n".join(lines)

    def _format_template(self, template, **kwargs):
        try:
            return template.format(**kwargs)
        except Exception as e:
            print(f"格式化AI提示词失败: {e}")
            return template

    def _build_strategy_prompt_parts(self, original_name, conversion_level=0, price_audience_level=0, row=None, custom_hint=""):
        conversion_desc = self._describe_conversion_level(conversion_level)
        price_audience_desc = self._describe_price_audience_level(price_audience_level)
        price_relation = self._get_price_relation_info(row, original_name)
        spec_price_layout = self._format_spec_price_layout(price_relation.get("specs", []))
        product_memo = self._get_product_memo()

        base_template = self.db.get_setting("ai_spec_base_prompt", "") or self._get_default_spec_base_prompt()
        conversion_template = self.db.get_setting("ai_spec_conversion_axis_prompt", "") or self._get_default_conversion_axis_prompt()
        price_audience_template = self.db.get_setting("ai_spec_price_audience_prompt", "") or self._get_default_price_audience_prompt()
        price_relation_template = self.db.get_setting("ai_spec_price_relation_prompt", "") or self._get_default_price_relation_prompt()

        values = {
            "conversion_level": f"{conversion_level:+d}",
            "conversion_desc": conversion_desc,
            "price_audience_level": f"{price_audience_level:+d}",
            "price_audience_desc": price_audience_desc,
            "price_relation_summary": price_relation.get("summary", ""),
            "spec_price_layout": spec_price_layout,
            "product_name": self.product_name,
            "current_spec_name": original_name,
            "custom_hint": custom_hint.strip() if custom_hint else "未填写本次补充提示",
            "product_memo": product_memo if product_memo else "未填写主界面图片备注",
        }

        return {
            "base": self._format_template(base_template, **values),
            "conversion": self._format_template(conversion_template, **values),
            "price_audience": self._format_template(price_audience_template, **values),
            "price_relation": self._format_template(price_relation_template, **values),
            "price_relation_info": price_relation,
            "product_memo": product_memo,
        }

    def _get_product_memo(self):
        try:
            rows = self.db.safe_fetchall("SELECT product_memo FROM products WHERE id=?", (self.product_id,))
            return rows[0][0].strip() if rows and rows[0][0] else ""
        except Exception as e:
            print(f"获取主界面图片备注失败: {e}")
        return ""

    def _get_store_memo(self):
        try:
            store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.product_id,))
            if store_rows and store_rows[0]:
                store_id = store_rows[0][0]
                memo_rows = self.db.safe_fetchall("SELECT memo FROM stores WHERE id=?", (store_id,))
                return memo_rows[0][0] if memo_rows and memo_rows[0][0] else ""
        except Exception as e:
            print(f"获取店铺备注失败: {e}")
        return ""

    def _build_full_prompt_text_optimized(self, original_name, conversion_level=0, price_audience_level=0, row=None, custom_hint=""):
        """构建优化后的完整API提示词文本（仅使用一个毛利策略）"""
        parts = self._build_strategy_prompt_parts(original_name, conversion_level, price_audience_level, row, custom_hint)
        lines = []
        lines.append("=" * 60)
        lines.append("【API调用完整提示词预览】")
        lines.append("=" * 60)
        lines.append("")

        lines.append("【1. 违禁词过滤规则】")
        forbidden_words = self.db.get_setting("ai_spec_forbidden_words", "")
        if forbidden_words:
            forbidden_list = [w.strip() for w in forbidden_words.split(",") if w.strip()]
            lines.append(f"禁止出现：{', '.join(forbidden_list)}")
        else:
            lines.append("（未设置违禁词）")
        lines.append("")

        lines.append("【2. 商品属性提示词】")
        lines.append("-" * 40)
        product_attr = self.db.get_setting("ai_product_info_prompt", "") or "（未设置）"
        lines.append(product_attr)
        lines.append("")

        lines.append("【3. 当前链接信息】")
        lines.append("-" * 40)
        lines.append(f"商品标题：{self.product_name}")
        lines.append("")

        lines.append("【4. 主界面图片备注 / 链接目标人群提示】")
        lines.append("-" * 40)
        product_memo = parts.get("product_memo", "") or self._get_product_memo()
        lines.append(product_memo if product_memo else "未填写主界面图片备注")
        lines.append("")

        lines.append("【5. 本次补充提示】")
        lines.append("-" * 40)
        lines.append(custom_hint.strip() if custom_hint else "未填写本次补充提示")
        lines.append("")

        lines.append("【6. 所有规格信息】")
        lines.append("-" * 40)
        specs_layout = self._get_specs_with_margin()
        lines.append(specs_layout)
        lines.append("")

        lines.append("【7. 当前优化规格】")
        lines.append("-" * 40)
        lines.append(f"正在优化：{original_name}")
        lines.append("")

        lines.append("【8. 基础生成规则】")
        lines.append("-" * 40)
        lines.append(parts["base"].strip())
        lines.append("")

        lines.append(f"【9. 转化方向标尺：{conversion_level:+d} {self._describe_conversion_level(conversion_level)}】")
        lines.append("-" * 40)
        lines.append(parts["conversion"].strip())
        lines.append("")

        lines.append(f"【10. 价格人群标尺：{price_audience_level:+d} {self._describe_price_audience_level(price_audience_level)}】")
        lines.append("-" * 40)
        lines.append(parts["price_audience"].strip())
        lines.append("")

        lines.append("【11. 价格相对位置规则】")
        lines.append("-" * 40)
        lines.append(parts["price_relation"].strip())
        lines.append("")

        lines.append("【12. 店铺运营大纲】")
        lines.append("-" * 40)
        store_memo = self._get_store_memo()
        if store_memo:
            lines.append(store_memo)
        else:
            lines.append("（未设置店铺运营大纲）")

        lines.append("")
        lines.append("=" * 60)
        lines.append("【User Prompt（用户输入）】")
        lines.append("=" * 60)
        lines.append(f"商品标题：{self.product_name}")
        lines.append("")
        lines.append(f"原规格名称：{original_name}")

        return "\n".join(lines)

    def _do_ai_optimize(self, row, original_name, conversion_level=0, price_audience_level=0, custom_hint=""):
        """执行AI优化"""
        api_key = self.db.get_setting("ai_api_key", "")
        if not api_key:
            QMessageBox.warning(self, "⚠️ 提示", "请先在API配置中设置API Key！")
            return

        product_memo = self._get_product_memo()
        store_memo = self._get_store_memo()

        forbidden_words = self.db.get_setting("ai_spec_forbidden_words", "")
        forbidden_rule = ""
        if forbidden_words:
            forbidden_list = [w.strip() for w in forbidden_words.split(",") if w.strip()]
            if forbidden_list:
                forbidden_rule = f"""【违禁词过滤规则 - 最高优先级，必须严格遵守】
禁止在生成的任何规格名称中出现以下词汇：{', '.join(forbidden_list)}
如果生成的内容包含违禁词，必须替换为合规表达。
绝对不能在规格名称中出现"·"符号。

"""

        product_attr_prompt = self._build_product_attr_prompt(original_name)
        strategy_parts = self._build_strategy_prompt_parts(original_name, conversion_level, price_audience_level, row, custom_hint)

        product_memo_prompt = ""
        if product_memo:
            product_memo_prompt = f"""【主界面图片备注 - 链接目标人群提示 - 高优先级】
{product_memo}
这条备注代表当前商品链接主要针对的人群。生成SKU时必须优先围绕这类人群的痛点、使用场景、购买顾虑和筛选门槛来写。
正向转化时增强该人群的购买理由；负向转化时让该人群之外的用户感觉当前规格不适合自己。

"""

        custom_hint_prompt = ""
        if custom_hint and custom_hint.strip():
            custom_hint_prompt = f"""【本次补充提示 - 高优先级】
{custom_hint.strip()}
请把这条补充提示作为本次命名的重要上下文，但仍要遵守价格相对位置、违禁词和合规边界。

"""

        priority_prompt = ""
        if store_memo:
            priority_prompt = f"""【店铺运营指导大纲 - 最高优先级】
{store_memo}

"""

        prompt_text = (
            forbidden_rule
            + product_memo_prompt
            + product_attr_prompt
            + custom_hint_prompt
            + priority_prompt
            + strategy_parts["base"] + "\n\n"
            + strategy_parts["conversion"] + "\n\n"
            + strategy_parts["price_audience"] + "\n\n"
            + strategy_parts["price_relation"] + "\n\n"
        )

        user_prompt = f"商品标题：{self.product_name}\n\n原规格名称：{original_name}"
        
        progress = QProgressDialog("正在调用AI优化...", "取消", 0, 0, self)
        progress.setWindowTitle("🤖 AI处理中")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        
        try:
            api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
            model = self.db.get_setting("ai_model", "deepseek-v4-flash")
            
            headers = {
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": model,
                "messages": [
                    {"role": "system", "content": prompt_text},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 4096,
                "temperature": 0.9
            }
            
            response = None
            for attempt in range(3):
                response = requests.post(api_url, headers=headers, json=data, timeout=60)
                if response.status_code not in (500, 503):
                    break
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
            
            progress.close()
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result["choices"][0]["message"]["content"].strip()
                
                self.show_ai_result_dialog(row, original_name, ai_response, conversion_level, price_audience_level, custom_hint)
            else:
                error_detail = response.text.strip()[:500] if response is not None else ""
                if response.status_code == 503:
                    message = "API调用失败：503\nDeepSeek服务器当前过载，请稍后重试。"
                else:
                    message = f"API调用失败：{response.status_code}"
                if error_detail:
                    message += f"\n\n返回内容：{error_detail}"
                QMessageBox.warning(self, "❌ 错误", message)
                
        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "❌ 错误", f"发生错误：{str(e)}")
    
    def show_ai_result_dialog(self, row, original_name, optimized_name, conversion_level=0, price_audience_level=0, custom_hint=""):
        """显示AI优化结果对话框（10条选项供选择）"""
        options = self._parse_ai_options(optimized_name)
        options = self._filter_forbidden_words(options)

        if not options:
            QMessageBox.warning(self, "⚠️ 提示", f"AI生成的所有规格名称都包含违禁词，请重新生成或调整违禁词设置！")
            return

        self._current_row = row
        self._current_original_name = original_name
        self._current_conversion_level = conversion_level
        self._current_price_audience_level = price_audience_level
        self._current_custom_hint = custom_hint

        dialog = QDialog(self)
        dialog.setWindowTitle("🤖 AI优化结果（选择1个）")
        dialog.setMinimumWidth(800)
        dialog.setMinimumHeight(600)
        layout = QVBoxLayout(dialog)

        mode_text = f"转化 {conversion_level:+d}（{self._describe_conversion_level(conversion_level)}）｜价格人群 {price_audience_level:+d}（{self._describe_price_audience_level(price_audience_level)}）"
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"当前策略：{mode_text}"))
        header_layout.addWidget(QLabel(f"原规格名称：{original_name}"))
        if custom_hint and custom_hint.strip():
            hint_result_label = QLabel(f"本次补充：{custom_hint.strip()}")
            hint_result_label.setWordWrap(True)
            header_layout.addWidget(hint_result_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        layout.addWidget(QLabel("请选择优化后的规格名称（已清理禁用符号，选择后会写入规格并复制到剪贴板）："))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(450)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)

        import re

        for i, option in enumerate(options):
            spec_name = self._sanitize_ai_spec_name(option)

            container = QWidget()
            container.setStyleSheet("""
                QWidget {
                    background-color: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 5px;
                    padding: 8px;
                }
            """)
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(10, 8, 10, 8)

            number_label = QLabel(f"{i+1}.")
            number_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50; min-width: 30px;")
            container_layout.addWidget(number_label)

            spec_label = QLabel(spec_name)
            spec_label.setWordWrap(True)
            spec_label.setStyleSheet("""
                QLabel {
                    padding: 5px 10px;
                    font-size: 12px;
                    color: #2c3e50;
                }
            """)
            container_layout.addWidget(spec_label)
            container_layout.setStretch(1, 1)

            container_layout.addSpacing(10)

            btn_select = QPushButton("✅ 选择")
            btn_select.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    font-weight: bold;
                    padding: 8px 15px;
                    border-radius: 3px;
                    min-width: 70px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)

            def select_option(opt_text, r=row):
                final_name = self._sanitize_ai_spec_name(opt_text)
                if self.two_level_specs:
                    self._set_spec_name_cells(r, final_name)
                else:
                    self.table.item(r, self.COL_SPEC_NAME).setText(final_name)
                self._refresh_spec_filter_options()
                self._apply_spec_filters()

                clipboard = QApplication.clipboard()
                clipboard.setText(final_name)

                QMessageBox.information(dialog, "✅ 成功", f"已选择并复制：{final_name}")
                dialog.accept()

            btn_select.clicked.connect(lambda checked, opt=option: select_option(opt))
            container_layout.addWidget(btn_select)

            scroll_layout.addWidget(container)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        btn_layout = QHBoxLayout()
        
        btn_refresh = QPushButton("🔄 重新生成")
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        
        def refresh_result():
            conversion_level = getattr(self, '_current_conversion_level', 0)
            price_audience_level = getattr(self, '_current_price_audience_level', 0)
            custom_hint = getattr(self, '_current_custom_hint', "")
            self._do_ai_optimize(self._current_row, self._current_original_name, conversion_level, price_audience_level, custom_hint)
            dialog.accept()
        
        btn_refresh.clicked.connect(refresh_result)
        
        btn_close = QPushButton("❌ 关闭")
        btn_close.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_refresh)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def _strip_display_label(self, text):
        """去掉AI结果开头的展示标签，保留真正写入规格的SKU正文。"""
        if not text:
            return ""
        cleaned = re.sub(r'^【[^】]{1,12}】\s*', '', str(text).strip())
        cleaned = re.sub(r'^\[[^\]]{1,12}\]\s*', '', cleaned)
        return cleaned.strip()

    def _sanitize_ai_spec_name(self, text):
        """清理AI候选规格名中的禁用符号，保留允许的SKU符号。"""
        if not text:
            return ""
        cleaned = str(text).strip()
        cleaned = re.sub(r'^(优化后[：:]\s*)', '', cleaned)
        cleaned = re.sub(r'^(规格名称[：:]\s*)', '', cleaned)
        cleaned = re.sub(r'^(新规格[：:]\s*)', '', cleaned)
        forbidden_chars = "，,、。；;：:！!？?／/\\_＿*＊•·“”\"'‘’《》<>"
        trans = str.maketrans({ch: " " for ch in forbidden_chars})
        cleaned = cleaned.translate(trans)
        cleaned = re.sub(r'\s+', '', cleaned)
        return cleaned.strip()

    def _parse_ai_options(self, text):
        """解析AI返回的多条规格选项"""
        if not text:
            print("AI返回内容为空")
            return []

        import re

        print(f"=== AI原始返回内容 ===")
        print(text[:500])
        print("=" * 50)

        text = text.strip()
        lines = text.split('\n')
        options = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            line = re.sub(r'^\d+[.、、\.]\s*', '', line)
            line = re.sub(r'^(优化后[：:]\s*)', '', line)
            line = re.sub(r'^(规格名称[：:]\s*)', '', line)
            line = re.sub(r'^(新规格[：:]\s*)', '', line)
            line = re.sub(r'^(新规格\d+[.、\.]\s*)', '', line)
            line = re.sub(r'^[-*]\s*', '', line)
            line = self._sanitize_ai_spec_name(line)

            if line and len(line) >= 2:
                options.append(line)
            elif line:
                print(f"跳过过短的行: {line}")

        if not options and text:
            print("解析失败，返回原始文本")
            options = [text.strip()]

        unique_options = []
        for opt in options:
            if opt not in unique_options:
                unique_options.append(opt)

        print(f"解析结果: {len(unique_options)} 个选项")
        return unique_options

    def _filter_forbidden_words(self, options):
        """过滤包含违禁词的选项"""
        forbidden_words = self.db.get_setting("ai_spec_forbidden_words", "")
        if not forbidden_words:
            return options
        
        forbidden_list = [w.strip().lower() for w in forbidden_words.split(",") if w.strip()]
        if not forbidden_list:
            return options
        
        filtered = []
        for option in options:
            option_lower = option.lower()
            has_forbidden = False
            for word in forbidden_list:
                if word in option_lower:
                    has_forbidden = True
                    break
            if not has_forbidden:
                filtered.append(option)
        
        return filtered
    
    def _build_product_info_prompt(self, original_name):
        """构建产品信息提示词（用户上传的产品属性）"""
        product_attr = self.db.get_setting("ai_product_info_prompt", "") or ""
        if product_attr:
            return product_attr + "\n\n"
        return ""

    def _build_product_attr_prompt(self, original_name):
        """构建商品属性提示词（包含规格布局等信息）"""
        attr_template = self.db.get_setting("ai_spec_attr_prompt", "")
        if not attr_template:
            attr_template = """【商品属性信息】
{product_attr}

【当前链接标题】
{product_name}

【所有规格信息】（每个规格的名称、毛利率、价格）
{specs_layout}

【当前正在优化的规格】
{current_spec_name}

请结合以上商品属性和规格信息，生成最适合该规格的优化名称。"""

        try:
            product_attr = self.db.get_setting("ai_product_info_prompt", "") or ""
            specs_layout = self._get_specs_with_margin()

            attr_prompt = attr_template.format(
                product_attr=product_attr,
                product_name=self.product_name,
                specs_layout=specs_layout,
                current_spec_name=original_name
            )
        except Exception as e:
            print(f"构建商品属性提示词失败: {e}")
            attr_prompt = f"【当前链接标题】\n{self.product_name}\n\n【当前正在优化的规格】\n{original_name}"

        return attr_prompt + "\n\n"

    def _get_specs_with_margin(self):
        """获取所有规格的布局信息（名称、毛利率、价格）"""
        rows = []
        if hasattr(self, "table"):
            for r in range(self.table.rowCount()):
                code_item = self.table.item(r, self.COL_SPEC_CODE)
                price_item = self.table.item(r, self.COL_SALE_PRICE)
                spec_name = self._compose_spec_name(r)
                if not spec_name:
                    continue
                price_val = None
                if price_item:
                    try:
                        price_text = price_item.text().strip().replace("¥", "").replace(",", "")
                        price_val = float(price_text) if price_text else None
                    except (ValueError, TypeError):
                        price_val = None
                rows.append((spec_name, code_item.text().strip() if code_item else "", price_val))
        if not rows:
            rows = self.db.safe_fetchall(
                "SELECT spec_name, spec_code, sale_price FROM product_specs WHERE product_id=?",
                (self.product_id,)
            )
        if not rows:
            return "暂无规格数据"

        layout_lines = []
        for i, (spec_name, spec_code, sale_price) in enumerate(rows, 1):
            sale_price_str = f"{sale_price:.2f}" if sale_price else "--"

            cost_price = 0.0
            if spec_code:
                cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
                if cost_res and cost_res[0][0]:
                    cost_price = float(cost_res[0][0])

            if sale_price and cost_price > 0:
                margin_rate = ((sale_price - cost_price) / sale_price * 100) if sale_price > 0 else 0
                margin_str = f"{margin_rate:.2f}%"
            else:
                margin_str = "--"
            layout_lines.append(f"规格{i}: {spec_name} - 毛利率:{margin_str} - 价格:{sale_price_str}元")

        return "\n".join(layout_lines)

    def _get_specs_layout(self):
        """获取所有规格的布局信息"""
        rows = self.db.safe_fetchall(
            "SELECT spec_name, spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
            (self.product_id,)
        )
        if not rows:
            return "暂无规格数据"

        layout_lines = []
        for i, (spec_name, spec_code, sale_price, weight) in enumerate(rows, 1):
            sale_price_str = f"{sale_price:.2f}" if sale_price else "--"
            weight_str = f"{weight:.2f}%" if weight else "0%"
            layout_lines.append(f"{i}. {spec_name} - 价格:{sale_price_str}元 - 权重:{weight_str}")

        return "\n".join(layout_lines)

    def _get_total_orders(self):
        """获取总订单数"""
        res = self.db.safe_fetchall(
            "SELECT SUM(order_count) FROM imported_orders WHERE product_id=?",
            (self.product_code,)
        )
        return res[0][0] if res and res[0][0] else 0

    def _get_current_roi(self):
        """获取当前投产比"""
        res = self.db.safe_fetchall(
            "SELECT current_roi FROM products WHERE id=?",
            (self.product_id,)
        )
        return res[0][0] if res and res[0][0] else None

    def _get_gross_break_even(self):
        """获取毛保本投产"""
        res = self.db.safe_fetchall(
            "SELECT gross_break_even_roi FROM products WHERE id=?",
            (self.product_id,)
        )
        return res[0][0] if res and res[0][0] else None

    def _get_net_break_even(self):
        """获取净保本投产"""
        res = self.db.safe_fetchall(
            "SELECT net_break_even_roi FROM products WHERE id=?",
            (self.product_id,)
        )
        return res[0][0] if res and res[0][0] else None

    def _show_prompt_detail_dialog(self, parent_dialog, conversion_level=0, price_audience_level=0, price_relation=None, original_name="", row=None, custom_hint=""):
        dialog = QDialog(parent_dialog)
        dialog.setWindowTitle("📋 当前调用的提示词详情")
        dialog.resize(700, 600)
        layout = QVBoxLayout(dialog)

        header = QLabel("📋 当前调用的提示词详情")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(10)

        parts = self._build_strategy_prompt_parts(original_name, conversion_level, price_audience_level, row, custom_hint)
        if price_relation is None:
            price_relation = parts.get("price_relation_info", {})

        prompt_items = [
            ("🚫 违禁词过滤", "ai_spec_forbidden_words", False),
            ("🛒 产品信息", "ai_product_info_prompt", False),
            ("📦 商品属性提示词", "ai_spec_attr_prompt", False),
            ("🎯 主界面图片备注 / 链接目标人群提示", parts.get("product_memo", "") or "未填写主界面图片备注", True),
            ("📝 本次补充提示", custom_hint.strip() if custom_hint else "未填写本次补充提示", True),
            ("🧩 基础生成规则", parts["base"], True),
            (f"🎯 转化方向：{conversion_level:+d} {self._describe_conversion_level(conversion_level)}", parts["conversion"], True),
            (f"👥 价格人群：{price_audience_level:+d} {self._describe_price_audience_level(price_audience_level)}", parts["price_audience"], True),
            (f"💰 价格相对位置：{price_relation.get('summary', '')}", parts["price_relation"], True),
        ]

        store_memo = self._get_store_memo()

        if store_memo:
            prompt_items.append(("📋 店铺运营大纲", store_memo, True))

        for title, content_or_key, is_content in prompt_items:
            card = QWidget()
            card.setStyleSheet("""
                QWidget {
                    background-color: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 5px;
                    padding: 8px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 6, 10, 6)

            title_label = QLabel(title)
            title_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50;")
            card_layout.addWidget(title_label)

            if is_content and not isinstance(content_or_key, str) == False:
                content_text = content_or_key if is_content else self.db.get_setting(content_or_key, "")
            else:
                content_text = content_or_key if is_content else self.db.get_setting(content_or_key, "")

            if not content_text:
                content_text = "（未设置）"

            content_display = QTextEdit()
            content_display.setPlainText(content_text)
            content_display.setReadOnly(True)
            content_display.setMaximumHeight(150)
            content_display.setStyleSheet("""
                QTextEdit {
                    background-color: white;
                    border: 1px solid #dee2e6;
                    border-radius: 3px;
                    padding: 8px;
                    font-size: 11px;
                    font-family: Consolas, monospace;
                    color: #495057;
                }
            """)
            card_layout.addWidget(content_display)
            content_layout.addWidget(card)

        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        dialog.exec_()
    
    def _get_default_common_prompt(self):
        return """【通用规则 - 拼多多平台】
1. 禁止出现"运费险"关键词，统一替换为"退货包运费"
2. 所有商品默认包邮，禁止使用"限时包邮"等营销词汇。如果标题有"顺丰"可以加"顺丰包邮"作为卖点。
3. 如果规格名称已经有明确的重量单位，不要再用"加量"一类词，但"量大实惠"可以用。"""
    
    def _get_jd_common_prompt(self):
        return """【通用规则 - 京东平台】
1. 可以使用"京东配送"、"京东自营"等京东特色词汇
2. 强调正品保证,物流快速等服务优势
3. 可以使用"包邮"营销词汇"""
    
    def _get_taobao_common_prompt(self):
        return """【通用规则 - 淘宝平台】
1. 可以使用"包邮"、"特价"等营销词汇
2. 强调性价比和促销力度
3. 可以使用表情符号增加吸引力"""
    
    def _get_douyin_common_prompt(self):
        return """【通用规则 - 抖音平台】
1. 强调直播间专属优惠
2. 可以使用"限时秒杀"、"爆款推荐"等短视频风格词汇
3. 制造紧迫感和抢购氛围"""
    
    def _get_common_prompt(self):
        saved = self.db.get_setting("ai_common_prompt", "")
        if saved:
            return saved
        return self._get_default_common_prompt()
    
    def _show_common_rules_dialog(self, parent=None):
        """显示当前调用的提示词概览"""
        dialog = QDialog(parent or self)
        dialog.setWindowTitle("📋 当前调用的提示词")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        layout = QVBoxLayout(dialog)

        header = QLabel("📋 AI规格优化 - 当前调用的提示词")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 以下是AI优化规格名称时调用的所有提示词。点击对应按钮可跳转到编辑页面。")
        info.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        prompt_list_widget = QWidget()
        prompt_list_layout = QVBoxLayout(prompt_list_widget)
        prompt_list_layout.setSpacing(8)
        prompt_list_layout.setContentsMargins(0, 5, 0, 5)

        prompt_items = [
            ("🛒 产品信息（用户上传）", "ai_product_info_prompt", "产品提示词配置 → 产品信息标签页"),
            ("📦 商品属性提示词", "ai_spec_attr_prompt", "规格优化提示词配置 → 商品属性标签页"),
            ("🧩 基础生成规则", "ai_spec_base_prompt", "规格优化提示词配置 → 基础生成规则标签页"),
            ("🎯 转化标尺规则", "ai_spec_conversion_axis_prompt", "规格优化提示词配置 → 转化标尺规则标签页"),
            ("🚫 违禁词过滤", "ai_spec_forbidden_words", "规格优化提示词配置 → 违禁词设置按钮"),
            ("👥 价格人群规则", "ai_spec_price_audience_prompt", "产品提示词配置 → 价格人群规则标签页"),
            ("💰 价格相对位置规则", "ai_spec_price_relation_prompt", "产品提示词配置 → 价格相对位置规则标签页"),
        ]

        for title, setting_key, location in prompt_items:
            item_widget = QWidget()
            item_widget.setStyleSheet("""
                QWidget {
                    background-color: #f8f9fa;
                    border-radius: 5px;
                    border: 1px solid #dee2e6;
                    padding: 8px;
                }
            """)
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(10, 5, 10, 5)

            info_layout = QVBoxLayout()
            title_label = QLabel(title)
            title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #2c3e50;")
            info_layout.addWidget(title_label)

            location_label = QLabel(f"【位置】{location}")
            location_label.setStyleSheet("font-size: 11px; color: #6c757d;")
            info_layout.addWidget(location_label)

            current_value = self.db.get_setting(setting_key, "")
            if current_value:
                value_label = QLabel(f"当前内容：{current_value[:40]}{'...' if len(current_value) > 40 else ''}")
                value_label.setStyleSheet("font-size: 10px; color: #95a5a6;")
                value_label.setWordWrap(True)
                info_layout.addWidget(value_label)

            info_layout.addStretch()
            item_layout.addLayout(info_layout)

            btn_edit = QPushButton("编辑")
            btn_edit.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    padding: 5px 15px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            btn_edit.clicked.connect(lambda checked, key=setting_key: self._open_prompt_editor(key))
            item_layout.addWidget(btn_edit)

            prompt_list_layout.addWidget(item_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(prompt_list_widget)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        dialog.exec_()

    def _open_prompt_editor(self, setting_key):
        if setting_key in ("ai_spec_attr_prompt", "ai_spec_base_prompt", "ai_spec_conversion_axis_prompt"):
            dialog = SpecPromptEditorDialog(self.db, self)
            dialog.exec_()
        elif setting_key == "ai_spec_forbidden_words":
            dialog = SpecPromptEditorDialog(self.db, self)
            dialog.exec_()
        else:
            dialog = ProductPromptEditorDialog(self.db, self)
            dialog.exec_()

    def _save_col_width_to_db(self):
        """延迟保存列宽到数据库"""
        if hasattr(self, '_pending_col_resize'):
            logicalIndex, newSize = self._pending_col_resize
            self.db.set_setting(f"spec_table_col_{logicalIndex}_width", str(newSize))

    def _on_spec_table_col_resized(self, logicalIndex, oldSize, newSize):
        """列宽改变时保存到数据库（带防抖）"""
        self._pending_col_resize = (logicalIndex, newSize)
        self._col_resize_timer.stop()
        self._col_resize_timer.start(300)
    
    def _extract_spec_name(self, text):
        """从AI输出中提取纯规格名称，去除注释和非法字符"""
        if not text:
            return text
        
        lines = text.strip().split('\n')
        first_line = lines[0].strip()
        
        # 去除常见的前缀标记
        import re
        cleaned = re.sub(r'^(优化后[：:]\s*)', '', first_line)
        cleaned = re.sub(r'^(规格名称[：:]\s*)', '', cleaned)
        cleaned = re.sub(r'^(建议[：:]\s*)', '', cleaned)
        
        # 去除·符号
        cleaned = cleaned.replace('·', '')
        
        # 如果第一行很短（小于50字符），可能就是纯名称
        if len(cleaned) <= 50:
            return cleaned
        
        # 否则尝试找到第一行作为名称
        for line in lines:
            line = line.strip()
            if line and not line.startswith('注') and not line.startswith('备注') and not line.startswith('说明'):
                # 去除前缀
                line = re.sub(r'^(优化后[：:]\s*)', '', line)
                line = re.sub(r'^(规格名称[：:]\s*)', '', line)
                line = re.sub(r'^(建议[：:]\s*)', '', line)
                # 去除·符号
                line = line.replace('·', '')
                if line:
                    return line
        
        # 最后再去除一次·符号
        cleaned = cleaned.replace('·', '')
        return cleaned

    def _get_last_snapshot(self):
        """获取上一期导入的历史快照数据 - 直接取排序后的下一条记录"""
        try:
            store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.product_id,))
            if not store_rows or not store_rows[0][0]:
                return None
            store_id = store_rows[0][0]

            # 获取当前商品导入的订单日期范围
            current_data = self.db.safe_fetchall("""
                SELECT order_date FROM imported_orders WHERE product_id=?
            """, (self.product_code,))

            current_end_date = None
            current_start_date = None
            if current_data:
                for (order_date,) in current_data:
                    if order_date and '~' in order_date:
                        parts = order_date.split('~')
                        if len(parts) == 2:
                            current_start_date = parts[0].strip()
                            current_end_date = parts[1].strip()
                            break

            # 获取所有历史记录（已按订单结束日期降序排序）
            all_history = self.db.safe_fetchall("""
                SELECT id, snapshot_data
                FROM import_history
                WHERE store_id=? AND snapshot_data IS NOT NULL AND snapshot_data != ''
                ORDER BY import_time DESC
            """, (store_id,))

            # 从快照中解析订单结束日期
            def get_end_date_from_snapshot(snapshot_data):
                try:
                    snapshot = json.loads(snapshot_data)
                    orders = snapshot.get("orders", {})
                    all_dates = []
                    for key, data in orders.items():
                        if isinstance(data, dict) and "dates" in data:
                            for date_val in data.get("dates", []):
                                if date_val and '/' in date_val:
                                    try:
                                        if '~' in date_val:
                                            for p in date_val.split('~'):
                                                if '/' in p:
                                                    m, d = p.split('/')
                                                    all_dates.append((int(m), int(d)))
                                        else:
                                            m, d = date_val.split('/')
                                            all_dates.append((int(m), int(d)))
                                    except:
                                        pass
                    if all_dates:
                        all_dates.sort()
                        return all_dates[-1]  # 返回结束日期
                except:
                    pass
                return None

            # 遍历历史记录，找到当前数据对应的下一条
            for i, (hist_id, snapshot_data) in enumerate(all_history):
                prev_end_date = get_end_date_from_snapshot(snapshot_data)

                # 如果当前有数据，找结束日期小于当前结束日期的第一条
                if current_end_date and prev_end_date:
                    # 比较日期 - 需要处理月份可能不同的情况
                    try:
                        curr_parts = current_end_date.split('/')
                        curr_m, curr_d = int(curr_parts[0]), int(curr_parts[1])
                        prev_m, prev_d = int(prev_end_date[0]), int(prev_end_date[1])

                        # 如果月份不同，用月份比较；如果月份相同，用日期比较
                        if prev_m < curr_m or (prev_m == curr_m and prev_d < curr_d):
                            return json.loads(snapshot_data)
                    except:
                        pass

            # 如果没找到，返回None
            return None
        except Exception as e:
            return None

    def _update_spec_compare_labels(self, row, current_count, last_count, current_total, current_weight, last_weight):
        """更新指定行的对比列标签"""
        weight_compare_widget = self.table.cellWidget(row, self.COL_WEIGHT_COMPARE)
        order_compare_widget = self.table.cellWidget(row, self.COL_ORDER_COMPARE)

        if not weight_compare_widget or not order_compare_widget:
            return

        weight_compare_label = weight_compare_widget.layout().itemAt(0).widget()
        order_compare_label = order_compare_widget.layout().itemAt(0).widget()

        if last_count is None:
            weight_compare_label.setText("无")
            weight_compare_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
            order_compare_label.setText("无")
            order_compare_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
            return

        if last_weight is None:
            last_weight = 0

        weight_change = current_weight - last_weight
        order_change = current_count - last_count

        if abs(weight_change) < 0.001:
            weight_compare_label.setText("⚪ 0.00%")
            weight_compare_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        elif weight_change > 0:
            weight_compare_label.setText(f"🟢 ↑{weight_change:.2f}%")
            weight_compare_label.setStyleSheet("color: #27ae60; font-size: 12px; font-weight: bold;")
        else:
            weight_compare_label.setText(f"🔴 ↓{abs(weight_change):.2f}%")
            weight_compare_label.setStyleSheet("color: #c0392b; font-size: 12px; font-weight: bold;")

        if order_change > 0:
            order_compare_label.setText(f"🟢 ↑{order_change}")
            order_compare_label.setStyleSheet("color: #27ae60; font-size: 12px; font-weight: bold;")
        elif order_change < 0:
            order_compare_label.setText(f"🔴 ↓{abs(order_change)}")
            order_compare_label.setStyleSheet("color: #c0392b; font-size: 12px; font-weight: bold;")
        else:
            order_compare_label.setText("⚪ 0")
            order_compare_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")

    def _get_last_snapshot_values(self):
        """获取上一次快照中当前商品的所有规格订单数"""
        snapshot = self._get_last_snapshot()
        if not snapshot:
            return {}
        result = {}
        orders_data = snapshot.get("orders", {})
        for key, data in orders_data.items():
            parts = key.split("_")
            if len(parts) >= 2:
                user_product_id = parts[0]
                spec_code_part = "_".join(parts[1:])
                if user_product_id == self.product_code:
                    result[spec_code_part] = data.get("count", 0)
        return result

    def refresh_weight_display(self):
        """刷新权重显示（应用历史后调用）"""
        imported_data = self.db.safe_fetchall(
            "SELECT spec_code, order_count FROM imported_orders WHERE product_id=?",
            (self.product_code,)
        )
        
        if not imported_data:
            for row in range(self.table.rowCount()):
                weight_item = self.table.item(row, self.COL_WEIGHT)
                if weight_item:
                    weight_item.setText("0.00%")
                    weight_item.setData(Qt.UserRole, 0)
                order_item = self.table.item(row, self.COL_ORDER_COUNT)
                if order_item:
                    order_item.setText("0单")
            self.update_total_orders_label()
            self.update_compare_columns()
            return
        
        spec_order_counts = {str(row[0]): row[1] for row in imported_data}
        total_orders = sum(spec_order_counts.values())

        for row in range(self.table.rowCount()):
            spec_code_item = self.table.item(row, self.COL_SPEC_CODE)
            if not spec_code_item:
                continue
            spec_code = str(spec_code_item.text()).strip()
            
            if spec_code in spec_order_counts:
                count = spec_order_counts[spec_code]
                weight = (count / total_orders) * 100 if total_orders > 0 else 0
                weight_text = f"{weight:.2f}%"
                weight_item = QTableWidgetItem(weight_text)
                weight_item.setFlags(weight_item.flags() & ~Qt.ItemIsEditable)
                weight_item.setData(Qt.UserRole, weight)
                weight_item.setToolTip(f"订单数: {count}单")
                self.table.setItem(row, self.COL_WEIGHT, weight_item)
                order_item = self._make_unselectable_item(f"{count}单")
                order_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, self.COL_ORDER_COUNT, order_item)
            else:
                weight_text = "0.00%"
                weight_item = QTableWidgetItem(weight_text)
                weight_item.setFlags(weight_item.flags() & ~Qt.ItemIsEditable)
                weight_item.setData(Qt.UserRole, 0.0)
                self.table.setItem(row, self.COL_WEIGHT, weight_item)
                order_item = self._make_unselectable_item("0单")
                order_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, self.COL_ORDER_COUNT, order_item)
        
        self.update_total_orders_label()
        self.update_compare_columns()

    def update_total_orders_label(self):
        """更新总订单标签"""
        imported_data = self.db.safe_fetchall(
            "SELECT SUM(order_count) FROM imported_orders WHERE product_id=?",
            (self.product_code,)
        )
        total = imported_data[0][0] if imported_data and imported_data[0][0] else 0
        self.lbl_total_orders.setText(f"总订单: {total}")
        spec_sales = self.db.safe_fetchall(
            "SELECT ps.sale_price, io.order_count FROM product_specs ps "
            "LEFT JOIN imported_orders io ON io.product_id = ? AND io.spec_code = ps.spec_code "
            "WHERE ps.product_id = ?",
            (self.product_code, self.product_id)
        )
        total_amount = 0.0
        total_orders = 0
        for sale_price, order_count in spec_sales:
            if sale_price and order_count:
                total_amount += sale_price * order_count
                total_orders += order_count
        if total_orders > 0:
            avg_price = total_amount / total_orders
            self.lbl_sales_info.setText(f"销售额: ¥{total_amount:.2f} | 客单价: ¥{avg_price:.2f}")
        else:
            self.lbl_sales_info.setText("销售额: - | 客单价: -")
        self.update_order_date_range_label()

    def update_order_date_range_label(self):
        """更新订单时间范围和导入时间标签"""
        if not hasattr(self, 'lbl_order_date_range'):
            return

        all_dates = self.db.safe_fetchall("""
            SELECT order_date FROM imported_orders WHERE product_id=? AND order_date IS NOT NULL
        """, (self.product_code,))

        order_range_str = "无日期"
        if all_dates:
            parsed_dates = []
            for (date_val,) in all_dates:
                if date_val:
                    try:
                        if '~' in date_val:
                            parts = date_val.split('~')
                            for p in parts:
                                if '/' in p:
                                    m, d = p.split('/')
                                    parsed_dates.append((int(m), int(d)))
                        elif '/' in date_val:
                            m, d = date_val.split('/')
                            parsed_dates.append((int(m), int(d)))
                    except:
                        pass

            if parsed_dates:
                parsed_dates.sort()
                min_date = parsed_dates[0]
                max_date = parsed_dates[-1]
                if min_date != max_date:
                    order_range_str = f"{min_date[0]}/{min_date[1]}-{max_date[0]}/{max_date[1]}"
                else:
                    order_range_str = f"{min_date[0]}/{min_date[1]}"

        latest_import = self.db.safe_fetchall("""
            SELECT import_time FROM imported_orders WHERE product_id=? ORDER BY import_time DESC LIMIT 1
        """, (self.product_code,))

        import_date_str = "未知"
        if latest_import and latest_import[0][0]:
            import_time = latest_import[0][0]
            import_date_str = import_time.split()[0] if ' ' in import_time else import_time
            try:
                if '-' in import_date_str:
                    parts = import_date_str.split('-')
                    if len(parts) >= 2:
                        month = int(parts[1])
                        day = int(parts[2])
                        import_date_str = f"{month}月{day}号"
            except:
                pass

        self.lbl_order_date_range.setText(f"订单: {order_range_str} | 导入: {import_date_str}")

    def update_compare_columns(self):
        """更新所有规格的对比列数据"""
        imported_data = self.db.safe_fetchall(
            "SELECT spec_code, order_count FROM imported_orders WHERE product_id=?",
            (self.product_code,)
        )

        last_snapshot = self._get_last_snapshot()
        last_spec_counts = {}
        last_spec_weights = {}
        last_total_orders = 0
        if last_snapshot:
            last_orders_data = last_snapshot.get("orders", {})
            for key, data in last_orders_data.items():
                parts = key.split("_")
                if len(parts) >= 2:
                    prod_id_part = parts[0]
                    spec_code_part = "_".join(parts[1:])
                    if prod_id_part == self.product_code:
                        last_spec_counts[spec_code_part] = data.get("count", 0)
                        last_total_orders += data.get("count", 0)
        
        last_snapshot_weights = last_snapshot.get("weights", {}) if last_snapshot else {}

        current_spec_counts = {str(row[0]): row[1] for row in imported_data} if imported_data else {}
        current_total = sum(current_spec_counts.values())

        for row in range(self.table.rowCount()):
            spec_code_item = self.table.item(row, self.COL_SPEC_CODE)
            if not spec_code_item:
                continue
            spec_code = str(spec_code_item.text()).strip()
            current_count = current_spec_counts.get(spec_code, 0)
            last_count = last_spec_counts.get(spec_code, None)
            
            weight_item = self.table.item(row, self.COL_WEIGHT)
            current_weight = weight_item.data(Qt.UserRole) if weight_item else 0
            
            last_spec_weight = 0
            if last_count is not None and last_total_orders > 0:
                last_spec_weight = (last_count / last_total_orders) * 100
            elif last_count is None:
                last_spec_weight = None

            self._update_spec_compare_labels(row, current_count, last_count, current_total, current_weight, last_spec_weight)

    def _editable_input_style(self):
        return "padding: 5px; border: 1px solid #3498db; border-radius: 3px; background-color: #ffffff; color: #2c3e50;"

    def _auto_input_style(self):
        return "padding: 5px; border: 1px solid #d0d5da; border-radius: 3px; background-color: #eeeeee; color: #666;"

    def _mark_roi_bid_manual_source(self, source):
        if source in ("roi", "transaction_bid"):
            self._roi_bid_manual_source = source

    def _set_roi_bid_input_mode(self, mode, user_action=False):
        if mode not in ("roi", "bid"):
            return
        old_mode = getattr(self, "roi_input_mode", "roi")
        if user_action:
            self._mark_roi_bid_manual_source("roi" if mode == "roi" else "transaction_bid")
            if old_mode != mode:
                self._roi_bid_mode_switches.append((old_mode, mode))
        self.roi_input_mode = mode
        self._apply_roi_bid_input_mode()
        if mode == "roi":
            self._sync_bid_from_roi()
        else:
            self._sync_roi_from_bid()

    def _apply_roi_bid_input_mode(self):
        if not hasattr(self, "current_roi_input") or not hasattr(self, "transaction_bid_input"):
            return
        roi_manual = self.roi_input_mode == "roi"
        self.current_roi_input.setReadOnly(not roi_manual)
        self.transaction_bid_input.setReadOnly(roi_manual)
        self.current_roi_input.setStyleSheet(self._editable_input_style() if roi_manual else self._auto_input_style())
        self.transaction_bid_input.setStyleSheet(self._auto_input_style() if roi_manual else self._editable_input_style())
        self.current_roi_input.setToolTip("双击切换为手动输入当前投产")
        self.transaction_bid_input.setToolTip("双击切换为手动输入成交出价")

    def _get_avg_price_for_bid(self):
        try:
            return float(self.calculate_weighted_avg_price())
        except Exception:
            return 0.0

    def _get_return_factor_for_bid(self):
        return_rate = self.get_return_rate()
        return max(0.0, 1 - return_rate / 100)

    def _calc_bid_from_roi(self, roi):
        avg_price = self._get_avg_price_for_bid()
        return_factor = self._get_return_factor_for_bid()
        if avg_price <= 0 or roi <= 0 or return_factor <= 0:
            return None
        return avg_price / (roi * return_factor)

    def _calc_roi_from_bid(self, bid):
        avg_price = self._get_avg_price_for_bid()
        return_factor = self._get_return_factor_for_bid()
        if avg_price <= 0 or bid <= 0 or return_factor <= 0:
            return None
        return avg_price / (bid * return_factor)

    def _sync_bid_from_roi(self):
        if not hasattr(self, "transaction_bid_input"):
            return
        try:
            roi_text = self.current_roi_input.text().strip()
            roi = float(roi_text) if roi_text else 0.0
        except ValueError:
            roi = 0.0
        bid = self._calc_bid_from_roi(roi)
        self._roi_bid_syncing = True
        try:
            self.transaction_bid_input.setText(f"{bid:.2f}" if bid is not None else "")
        finally:
            self._roi_bid_syncing = False

    def _sync_roi_from_bid(self):
        if not hasattr(self, "current_roi_input"):
            return
        try:
            bid_text = self.transaction_bid_input.text().strip()
            bid = float(bid_text) if bid_text else 0.0
        except ValueError:
            bid = 0.0
        roi = self._calc_roi_from_bid(bid)
        self._roi_bid_syncing = True
        try:
            self.current_roi_input.setText(f"{roi:.2f}" if roi is not None else "")
        finally:
            self._roi_bid_syncing = False

    def _refresh_auto_roi_bid_field(self):
        if not hasattr(self, "transaction_bid_input"):
            return
        if self.roi_input_mode == "roi":
            self._sync_bid_from_roi()
        else:
            self._sync_roi_from_bid()

    def _update_roi_derived_metrics(self):
        try:
            current_roi_text = self.current_roi_input.text().strip()
            if not current_roi_text:
                self.lbl_net_profit_rate.setText("0.00%")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #999; background-color: #f0f0f0; padding: 5px 10px; border-radius: 3px;")
                self.lbl_roi_multiple.setText("--")
                self.lbl_scale_roi.setText("--")
                self.lbl_promotion_ratio.setText("--")
                return

            current_roi = float(current_roi_text)

            if current_roi <= 0:
                self.lbl_net_profit_rate.setText("0.00%")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #999; background-color: #f0f0f0; padding: 5px 10px; border-radius: 3px;")
                self.lbl_roi_multiple.setText("--")
                self.lbl_scale_roi.setText("--")
                self.lbl_promotion_ratio.setText("--")
                return

            margin_rate = self.get_current_margin_rate()
            if margin_rate <= 0:
                self.lbl_net_profit_rate.setText("请设置毛利")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #e74c3c; background-color: #fdeaea; padding: 5px 10px; border-radius: 3px;")
                self.lbl_roi_multiple.setText("--")
                self.lbl_scale_roi.setText("--")
                self.lbl_promotion_ratio.setText("--")
                return

            return_rate = self.get_return_rate()

            net_margin_formula = margin_rate * (1 - return_rate / 100) - 0.0006
            net_break_even = 1 / net_margin_formula if net_margin_formula > 0 else 0

            net_profit_rate = margin_rate * (1 - return_rate / 100) - 0.006 - (1 / current_roi)
            net_profit_rate = net_profit_rate * 100

            if net_profit_rate > 0:
                self.lbl_net_profit_rate.setText(f"{net_profit_rate:.2f}%")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #27ae60; background-color: #e8f8f5; padding: 5px 10px; border-radius: 3px;")
            elif net_profit_rate == 0:
                self.lbl_net_profit_rate.setText(f"{net_profit_rate:.2f}%")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #e67e22; background-color: #fef5e7; padding: 5px 10px; border-radius: 3px;")
            else:
                self.lbl_net_profit_rate.setText(f"{net_profit_rate:.2f}%")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #e74c3c; background-color: #fdeaea; padding: 5px 10px; border-radius: 3px;")

            if net_break_even > 0:
                roi_multiple = current_roi / net_break_even
                self.lbl_roi_multiple.setText(f"{roi_multiple:.2f}倍")
                self.lbl_scale_roi.setText(f"{net_break_even * 0.8:.2f}")
            else:
                self.lbl_roi_multiple.setText("--")
                self.lbl_scale_roi.setText("--")

            promotion_ratio = (1 / current_roi) * 100
            self.lbl_promotion_ratio.setText(f"{promotion_ratio:.2f}%")

        except ValueError:
            self.lbl_net_profit_rate.setText("0.00%")
            self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #999; background-color: #f0f0f0; padding: 5px 10px; border-radius: 3px;")
            self.lbl_roi_multiple.setText("--")
            self.lbl_scale_roi.setText("--")
            self.lbl_promotion_ratio.setText("--")

    def calculate_weighted_avg_price(self):
        """根据权重计算加权平均客单价"""
        total_weight = 0.0
        weighted_price = 0.0
        
        for r in range(self.table.rowCount()):
            price_item = self.table.item(r, self.COL_SALE_PRICE)
            weight_item = self.table.item(r, self.COL_WEIGHT)
            
            if not price_item or not weight_item:
                continue
            
            try:
                price = float(price_item.text()) if price_item.text() else 0
                weight_text = weight_item.data(Qt.DisplayRole) or ""
                clean_weight_text = weight_text.replace("🔒", "").strip()
                import re
                match = re.match(r'^([\d.]+)', clean_weight_text)
                if match:
                    clean_weight_text = match.group(1)
                else:
                    clean_weight_text = "0"
                weight = float(clean_weight_text) if clean_weight_text else 0
                
                if price > 0 and weight > 0:
                    weighted_price += price * weight
                    total_weight += weight
            except ValueError:
                continue
        
        if total_weight > 0:
            return weighted_price / total_weight
        return 0.0

    def on_discount_changed(self):
        """优惠券或新客立减金额变化时更新显示"""
        self.update_max_discount_label()
        self.recalculate_all_margins()
        # 确保毛保本等指标实时更新
        if hasattr(self, 'lbl_gross_break_even'):
            self.calculate_roi_metrics()

    def recalculate_all_margins(self):
        """重新计算所有行的毛利和综合毛利"""
        for r in range(self.table.rowCount()):
            self.calculate_row_margin(r)
        self.calculate_total_margin()

    def update_max_discount_label(self):
        """更新最大优惠金额显示"""
        try:
            coupon = float(self.coupon_input.text()) if self.coupon_input.text() else 0
            new_customer = float(self.new_customer_input.text()) if self.new_customer_input.text() else 0
            max_discount = max(coupon, new_customer)
            self.max_discount_label.setText(f"最大优惠: ¥{max_discount:.2f}")
        except ValueError:
            self.max_discount_label.setText("最大优惠: ¥0.00")
    
    def update_tag_button_styles(self):
        """更新限时限量购和营销活动按钮的样式"""
        if self.btn_limited_time.isChecked():
            self.btn_limited_time.setStyleSheet("""
                QPushButton {
                    border: 2px solid #e74c3c;
                    background-color: rgba(231, 76, 60, 0.1);
                    border-radius: 4px;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(231, 76, 60, 0.2);
                }
            """)
        else:
            self.btn_limited_time.setStyleSheet("""
                QPushButton {
                    border: none;
                    background-color: transparent;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(0,0,0,0.1);
                    border-radius: 4px;
                }
            """)
        
        if self.btn_marketing.isChecked():
            self.btn_marketing.setStyleSheet("""
                QPushButton {
                    border: 2px solid #9b59b6;
                    background-color: rgba(155, 89, 182, 0.1);
                    border-radius: 4px;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(155, 89, 182, 0.2);
                }
            """)
        else:
            self.btn_marketing.setStyleSheet("""
                QPushButton {
                    border: none;
                    background-color: transparent;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(0,0,0,0.1);
                    border-radius: 4px;
                }
            """)

    def average_weights(self):
        """一键均分权重（防闪退版）"""
        rows = self.table.rowCount()
        if rows == 0:
            return
        
        locked_weight_sum = 0.0
        unlocked_rows = []
        
        # 权重列
        for r in range(rows):
            item = self.table.item(r, self.COL_WEIGHT)
            if not item:
                continue
            
            text = item.data(Qt.DisplayRole) or ""
            is_locked = text.startswith("🔒")
            
            # 安全提取数字
            clean_text = text.replace("🔒", "").strip()
            try:
                val = float(clean_text)
            except ValueError:
                val = 0.0
            
            if is_locked:
                locked_weight_sum += val
            else:
                unlocked_rows.append(r)
        
        remaining = 100.0 - locked_weight_sum
        if remaining < -0.01:
            QMessageBox.warning(self, "警告", "锁定权重总和超过 100%！")
            return
        
        if len(unlocked_rows) > 0:
            avg = remaining / len(unlocked_rows)
            for r in unlocked_rows:
                item = self.table.item(r, self.COL_WEIGHT)
                if item:
                    # 保持锁定状态不变，只改数字
                    old_text = item.data(Qt.DisplayRole) or ""
                    was_locked = old_text.startswith("🔒")
                    new_val_str = f"🔒 {avg:.2f}" if was_locked else f"{avg:.2f}"
                    item.setData(Qt.DisplayRole, new_val_str)
            
            # 重新计算所有行的毛利（因为权重变了，毛利也会变）
            self.calculate_all_margins()
        else:
            if abs(locked_weight_sum - 100.0) > 0.01:
                QMessageBox.information(self, "提示", f"所有行已锁定，总权重：{locked_weight_sum:.2f}%")

    def _format_log_number(self, value, suffix=""):
        try:
            num = float(value)
            text = f"{num:.2f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            text = str(value)
        return f"{text}{suffix}"

    def _build_metric_change(self, metric, old, new, text, change_type, time_str):
        return {
            "time": time_str,
            "metric": metric,
            "old": old,
            "new": new,
            "text": text,
            "type": change_type,
        }

    def _calculate_weighted_margin_from_specs(self, specs, discount_amount):
        total_weighted_margin = 0.0
        total_weight = 0.0
        for spec in specs:
            try:
                spec_code = spec.get("spec_code", "")
                sale_price = float(spec.get("sale_price") or 0)
                weight = float(spec.get("weight_percent") or 0)
                if sale_price <= 0 or weight <= 0:
                    continue

                cost_rows = self.db.safe_fetchall(
                    "SELECT cost_price FROM cost_library WHERE spec_code=?",
                    (spec_code,)
                )
                cost = float(cost_rows[0][0]) if cost_rows and cost_rows[0][0] else 0.0
                final_price = sale_price - discount_amount
                if final_price <= 0 or cost <= 0:
                    continue

                margin = (final_price - cost) / final_price
                total_weighted_margin += margin * weight
                total_weight += weight
            except Exception:
                continue
        return (total_weighted_margin / total_weight * 100) if total_weight > 0 else 0.0

    def _calculate_weighted_avg_price_from_specs(self, specs):
        total_weight = 0.0
        weighted_price = 0.0
        for spec in specs:
            try:
                sale_price = float(spec.get("sale_price") or 0)
                weight = float(spec.get("weight_percent") or 0)
                if sale_price > 0 and weight > 0:
                    weighted_price += sale_price * weight
                    total_weight += weight
            except Exception:
                continue
        return weighted_price / total_weight if total_weight > 0 else 0.0

    def _calc_bid_for_record(self, avg_price, roi, return_rate):
        try:
            roi = float(roi or 0)
            avg_price = float(avg_price or 0)
            return_factor = max(0.0, 1 - float(return_rate or 0) / 100)
            if avg_price <= 0 or roi <= 0 or return_factor <= 0:
                return 0.0
            return avg_price / (roi * return_factor)
        except Exception:
            return 0.0

    def save_data(self):
        """
        【中文功能说明】
        保存规格数据到数据库，并智能检测：
        1. 价格变化 -> 记录调价日志。
        2. 规格删除 -> 记录删除日志。
        3. 自动计算新的综合毛利并写入日志。
        4. 只有点击“保存”才生效，点击“取消”不记录任何日志。
        """
        # 🔑【关键修复】保存当前选中的行
        current_row = self.table.currentRow()
        if current_row >= 0:
            self._saved_current_row = current_row
        try:
            # 1. 获取旧数据（用于对比价格和检测删除）
            old_rows = self.db.safe_fetchall(
                "SELECT spec_name, spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?", 
                (self.product_id,)
            )
            old_price_map = {r[1]: float(r[2] or 0) for r in old_rows} # {编码: 旧价格}
            old_name_map = {r[1]: r[0] for r in old_rows}  # {编码: 旧名称}
            old_codes_set = set(old_price_map.keys())       # 旧编码集合
            old_specs_for_margin = [
                {
                    "spec_name": r[0],
                    "spec_code": r[1],
                    "sale_price": r[2],
                    "weight_percent": r[3],
                }
                for r in old_rows
            ]

            old_discount_rows = self.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate FROM products WHERE id=?",
                (self.product_id,)
            )
            old_coupon = old_discount_rows[0][0] if old_discount_rows and old_discount_rows[0][0] else 0
            old_new_customer = old_discount_rows[0][1] if old_discount_rows and old_discount_rows[0][1] else 0
            old_roi = old_discount_rows[0][2] if old_discount_rows and old_discount_rows[0][2] else 0
            old_return_rate = old_discount_rows[0][3] if old_discount_rows and old_discount_rows[0][3] else 0
            old_discount_amount = max(old_coupon, old_new_customer)
            old_margin_pct = self._calculate_weighted_margin_from_specs(old_specs_for_margin, old_discount_amount)
            old_avg_price = self._calculate_weighted_avg_price_from_specs(old_specs_for_margin)
            old_transaction_bid = self._calc_bid_for_record(old_avg_price, old_roi, old_return_rate)
            roi_bid_manual_source = getattr(self, "_roi_bid_manual_source", None)
            roi_bid_mode_switches = list(getattr(self, "_roi_bid_mode_switches", []))
            
            # 准备新数据
            new_specs = []
            price_changes = []      # 存储调价记录 [(名称, 编码, 旧价, 新价)]
            current_codes_set = set() # 存储当前表格中存在的编码
            
            # 2. 遍历当前表格收集新数据
            row_count = self.table.rowCount()
            
            for r in range(row_count):
                item_code = self.table.item(r, self.COL_SPEC_CODE)
                item_price = self.table.item(r, self.COL_SALE_PRICE)
                item_weight = self.table.item(r, self.COL_WEIGHT)  # 权重列（可能带锁图标）
                spec_image_data = self._get_spec_image_data(r)
                
                if not item_code:
                    continue

                spec_name = self._compose_spec_name(r)
                # 规格名称最多40字符
                if len(spec_name) > 40 and not self.two_level_specs:
                    spec_name = spec_name[:40]
                    item_name = self.table.item(r, self.COL_SPEC_NAME)
                    if item_name:
                        item_name.setText(spec_name)
                spec_code = item_code.text().strip()
                
                # 记录当前存在的编码
                if spec_code:
                    current_codes_set.add(spec_code)
                
                # 获取价格
                price_text = item_price.text().strip() if item_price else ""
                new_price = float(price_text) if price_text else 0.0
                
                # 【关键】获取权重，正确处理带锁图标的文本
                weight_text = item_weight.text().strip() if item_weight else ""
                # 判断是否锁定（检查是否有锁图标）
                is_locked = 1 if "🔒" in weight_text else 0
                # 去掉锁图标和空格，只保留数字部分
                clean_weight = weight_text.replace("🔒", "").strip().replace("%", "")
                try:
                    weight_percent = float(clean_weight) if clean_weight else 0.0
                except ValueError:
                    weight_percent = 0.0
                    is_locked = 0  # 如果转换失败，视为未锁定
                
                if not spec_name:
                    continue
                
                # 【关键】保存时带上锁定状态
                new_specs.append((self.product_id, spec_name, spec_code, new_price, weight_percent, is_locked, spec_image_data))
                
                # 检测价格变化
                if spec_code in old_price_map:
                    old_price = old_price_map[spec_code]
                    if abs(new_price - old_price) > 0.001:
                        price_changes.append((spec_name or old_name_map.get(spec_code, spec_code), spec_code, old_price, new_price))
                elif new_price > 0:
                    # 新加的规格
                    price_changes.append((spec_name or spec_code, spec_code, 0.0, new_price))

            # 3. 检测删除操作
            deleted_codes = old_codes_set - current_codes_set
            deleted_logs = []
            for code in deleted_codes:
                name = old_name_map.get(code, "未知规格")
                deleted_logs.append(f"删除规格 [{name}]")

            # 4. 执行数据库事务 (先删后插)
            # 先保存优惠券和新客立减金额
            # 记录是否有投产/优惠券变化
            param_changed = False
            param_change_details = []
            metric_change_specs = []
            coupon_amount = old_coupon
            new_customer_discount = old_new_customer
            current_roi = old_roi
            return_rate = old_return_rate
            is_limited_time = 0
            is_marketing = 0
            old_limited_time = 0
            old_marketing = 0
            
            try:
                coupon_amount = float(self.coupon_input.text()) if self.coupon_input.text() else 0
                new_customer_discount = float(self.new_customer_input.text()) if self.new_customer_input.text() else 0
                current_roi = float(self.current_roi_input.text()) if self.current_roi_input.text() else 0
                return_rate = float(self.return_rate_input.text()) if self.return_rate_input.text() else 0
                
                # 检查优惠券变化
                if coupon_amount != old_coupon:
                    param_changed = True
                    if old_coupon == 0 or old_coupon is None:
                        param_change_details.append(f"设置了{coupon_amount}元优惠券")
                    elif coupon_amount == 0:
                        param_change_details.append("取消了优惠券")
                    else:
                        param_change_details.append(f"优惠券: {old_coupon}→{coupon_amount}")
                
                # 检查新客立减变化
                if new_customer_discount != old_new_customer:
                    param_changed = True
                    if old_new_customer == 0 or old_new_customer is None:
                        param_change_details.append(f"设置了新客立减{new_customer_discount}元")
                    elif new_customer_discount == 0:
                        param_change_details.append("取消了新客立减")
                    else:
                        param_change_details.append(f"新客立减: {old_new_customer}→{new_customer_discount}")
                
                # 检查投产/成交出价模式变化。成交出价模式会反算投产并保存，但日志只记录本次人工来源。
                if current_roi != old_roi and roi_bid_manual_source in ("roi", "transaction_bid"):
                    param_changed = True
                    if roi_bid_manual_source == "roi":
                        param_change_details.append(f"投产: {old_roi}→{current_roi}")
                    else:
                        param_change_details.append("成交出价调整")

                if roi_bid_mode_switches:
                    param_changed = True
                    for old_mode, new_mode in roi_bid_mode_switches:
                        old_text = "投产比" if old_mode == "roi" else "成交出价"
                        new_text = "投产比" if new_mode == "roi" else "成交出价"
                        param_change_details.append(f"{old_text}转换{new_text}")
                
                # 检查退货率变化
                if return_rate != old_return_rate:
                    param_changed = True
                    param_change_details.append(f"退货率: {old_return_rate}→{return_rate}%")
                
                is_limited_time = 1 if self.btn_limited_time.isChecked() else 0
                is_marketing = 1 if self.btn_marketing.isChecked() else 0
                
                old_tag_values = self.db.safe_fetchall(
                    "SELECT is_limited_time, is_marketing FROM products WHERE id=?",
                    (self.product_id,)
                )
                old_limited_time = old_tag_values[0][0] if old_tag_values and old_tag_values[0][0] else 0
                old_marketing = old_tag_values[0][1] if old_tag_values and old_tag_values[0][1] else 0
                
                tag_changes = []
                if is_limited_time != old_limited_time:
                    param_changed = True
                    if is_limited_time == 1:
                        tag_changes.append("报名了限时限量购")
                    else:
                        tag_changes.append("取消了限时限量购")
                if is_marketing != old_marketing:
                    param_changed = True
                    if is_marketing == 1:
                        tag_changes.append("报名了营销活动")
                    else:
                        tag_changes.append("取消了营销活动")
                
                if tag_changes:
                    param_change_details.extend(tag_changes)
                
                margin_rate = self.get_current_margin_rate()
                return_rate_val = self.get_return_rate()
                net_margin_formula = margin_rate * (1 - return_rate_val / 100) - 0.0006
                net_break_even_roi = 1 / net_margin_formula if net_margin_formula > 0 else 0
                
                self.db.safe_execute(
                    "UPDATE products SET coupon_amount=?, new_customer_discount=?, current_roi=?, return_rate=?, is_limited_time=?, is_marketing=?, net_break_even_roi=? WHERE id=?",
                    (coupon_amount, new_customer_discount, current_roi, return_rate, is_limited_time, is_marketing, net_break_even_roi, self.product_id)
                )
            except ValueError:
                pass
            
            self.db.safe_execute("DELETE FROM product_specs WHERE product_id=?", (self.product_id,))
            
            if new_specs:
                placeholders = ','.join(['(?, ?, ?, ?, ?, ?, ?)'] * len(new_specs))
                flat_data = [item for spec in new_specs for item in spec]
                self.db.safe_execute(
                    f"INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent, is_locked, spec_image_data) VALUES {placeholders}",
                    flat_data
                )
            self.db.update_product_category_label(self.product_id)
            
            # 5. 生成并写入日志 (如果有变化或删除)
            if price_changes or deleted_logs or param_changed:
                discount_amount = max(coupon_amount, new_customer_discount)

                # 重新计算保存后的综合毛利（基于优惠后的最终价格）
                rows = self.db.safe_fetchall(
                    "SELECT spec_name, spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?", 
                    (self.product_id,)
                )
                new_specs_for_margin = [
                    {"spec_name": r[0], "spec_code": r[1], "sale_price": r[2], "weight_percent": r[3]}
                    for r in rows
                ]
                current_margin_pct = self._calculate_weighted_margin_from_specs(new_specs_for_margin, discount_amount)
                current_avg_price = self._calculate_weighted_avg_price_from_specs(new_specs_for_margin)
                current_transaction_bid = self._calc_bid_for_record(current_avg_price, current_roi, return_rate)
                
                # 获取当前日期
                now = datetime.now()
                year, month, day = now.year, now.month, now.day
                
                # 读取今天已有的记录，获取历史综合毛利值
                existing_res = self.db.safe_fetchall(
                    "SELECT records_json FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                    (self.product_id, year, month, day)
                )
                
                existing_logs = []
                if existing_res:
                    try:
                        existing_logs = json.loads(existing_res[0][0])
                    except:
                        existing_logs = []
                
                # 判断综合毛利是否发生实质性变化（阈值0.1%）
                MARGIN_CHANGE_THRESHOLD = 0.1
                margin_changed = abs(current_margin_pct - old_margin_pct) >= MARGIN_CHANGE_THRESHOLD
                
                # 构建日志文本
                time_str = now.strftime("%H:%M")
                metric_changes = []
                log_parts = []

                if price_changes:
                    for spec_name, code, old, new in price_changes:
                        old_text = self._format_log_number(old, "元")
                        new_text = self._format_log_number(new, "元")
                        if old <= 0:
                            change_text = f"{spec_name}设置售价到{new_text}"
                            change_type = "price_set"
                        elif new > old:
                            change_text = f"{spec_name}从{old_text}涨价到{new_text}"
                            change_type = "price_increase"
                        else:
                            change_text = f"{spec_name}从{old_text}降价到{new_text}"
                            change_type = "price_decrease"
                        log_parts.append(change_text)
                        metric_changes.append(self._build_metric_change(
                            "规格售价", old_text, new_text, change_text, change_type, time_str
                        ))

                if deleted_logs:
                    log_parts.extend(deleted_logs)
                    for deleted_text in deleted_logs:
                        metric_changes.append(self._build_metric_change(
                            "规格删除", "", "", deleted_text, "spec_deleted", time_str
                        ))

                if coupon_amount != old_coupon:
                    old_text = self._format_log_number(old_coupon, "元")
                    new_text = self._format_log_number(coupon_amount, "元")
                    if coupon_amount > 0 and old_coupon <= 0:
                        change_text = f"优惠券设置为{new_text}"
                    elif coupon_amount <= 0:
                        change_text = f"优惠券从{old_text}取消"
                    else:
                        change_text = f"优惠券从{old_text}调整到{new_text}"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("优惠券", old_text, new_text, change_text, "coupon", time_str))

                if new_customer_discount != old_new_customer:
                    old_text = self._format_log_number(old_new_customer, "元")
                    new_text = self._format_log_number(new_customer_discount, "元")
                    if new_customer_discount > 0 and old_new_customer <= 0:
                        change_text = f"新客立减设置为{new_text}"
                    elif new_customer_discount <= 0:
                        change_text = f"新客立减从{old_text}取消"
                    else:
                        change_text = f"新客立减从{old_text}调整到{new_text}"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("新客立减", old_text, new_text, change_text, "new_customer_discount", time_str))

                for old_mode, new_mode in roi_bid_mode_switches:
                    old_text = "投产比模式" if old_mode == "roi" else "成交出价模式"
                    new_text = "投产比模式" if new_mode == "roi" else "成交出价模式"
                    change_text = f"从{old_text}转换到{new_text}"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("投产/出价模式", old_text, new_text, change_text, "roi_bid_mode", time_str))

                if current_roi != old_roi and roi_bid_manual_source == "roi":
                    old_text = self._format_log_number(old_roi)
                    new_text = self._format_log_number(current_roi)
                    direction = "提高" if current_roi > old_roi else "降低"
                    change_text = f"投产从{old_text}{direction}到{new_text}"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("投产", old_text, new_text, change_text, "roi", time_str))

                if abs(current_transaction_bid - old_transaction_bid) >= 0.01 and roi_bid_manual_source == "transaction_bid":
                    old_text = f"¥{self._format_log_number(old_transaction_bid)}"
                    new_text = f"¥{self._format_log_number(current_transaction_bid)}"
                    change_text = f"成交出价从{old_text}调整到{new_text}"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("成交出价", old_text, new_text, change_text, "transaction_bid", time_str))

                if return_rate != old_return_rate:
                    old_text = self._format_log_number(old_return_rate, "%")
                    new_text = self._format_log_number(return_rate, "%")
                    direction = "提高" if return_rate > old_return_rate else "降低"
                    change_text = f"退货率从{old_text}{direction}到{new_text}"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("退货率", old_text, new_text, change_text, "return_rate", time_str))

                if is_limited_time != old_limited_time:
                    old_text = "已报名" if old_limited_time else "未报名"
                    new_text = "已报名" if is_limited_time else "未报名"
                    change_text = "报名了限时限量购" if is_limited_time else "取消了限时限量购"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("限时限量购", old_text, new_text, change_text, "limited_time", time_str))

                if is_marketing != old_marketing:
                    old_text = "已报名" if old_marketing else "未报名"
                    new_text = "已报名" if is_marketing else "未报名"
                    change_text = "报名了营销活动" if is_marketing else "取消了营销活动"
                    log_parts.append(change_text)
                    metric_changes.append(self._build_metric_change("营销活动", old_text, new_text, change_text, "marketing", time_str))

                if margin_changed:
                    old_text = self._format_log_number(old_margin_pct, "%")
                    new_text = self._format_log_number(current_margin_pct, "%")
                    change_text = f"综合毛利从{old_text}变为{new_text}"
                    metric_changes.append(self._build_metric_change("综合毛利", old_text, new_text, change_text, "gross_margin", time_str))
                
                has_price_increase = any(old > 0 and new > old for _, _, old, new in price_changes)
                log_text = "；".join(log_parts)
                if has_price_increase:
                    log_text = f"{log_text}，新综合毛利 {current_margin_pct:.1f}%"
                
                # 追加新日志
                existing_logs.append({"time": time_str, "text": log_text, "changes": metric_changes})
                
                # 写回数据库
                self.db.safe_execute(
                    "INSERT OR REPLACE INTO records (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
                    (self.product_id, year, month, day, json.dumps(existing_logs, ensure_ascii=False))
                )
                
                # 提示用户
                msg = "规格已保存。\n"
                if price_changes: msg += f"✅ 记录 {len(price_changes)} 条调价日志。\n"
                if deleted_logs: msg += f"🗑️ 记录 {len(deleted_logs)} 条删除日志。"
                if param_changed: msg += f"📊 记录参数调整。"
                self.main_app.show_toast(msg)
                
                # 刷新主界面
                self.main_app.load_data_safe()
                self.refresh_metric_change_panel()
            
            # 6. 成功保存，关闭窗口
            self.accept()

        except Exception as e:
            import traceback
            print("❌ 保存失败详细信息:")
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"保存失败：{e}")

    def edit_product_code(self):
        """编辑商品ID（用户自定义ID）"""
        text, ok = QInputDialog.getText(
            self, 
            "修改商品ID", 
            "请输入新的商品ID:",
            text=self.product_code
        )
        if ok and text.strip():
            new_code = text.strip()
            try:
                # 更新name字段（商品ID）
                self.db.safe_execute(
                    "UPDATE products SET name=? WHERE id=?", 
                    (new_code, self.product_id)
                )
                self.product_code = new_code
                self.lbl_code.setText(f"商品ID: <b>{new_code}</b>")  # 去掉颜色样式
                
                # 更新主界面
                self.main_app.load_data_safe()
                
                self.main_app.show_toast(f"✅ 商品ID已更新为: {new_code}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"更新失败: {e}")

    def edit_product_name(self):
        """编辑商品标题"""
        text, ok = QInputDialog.getText(
            self, 
            "修改商品标题", 
            "请输入新的商品标题:",
            text=self.product_name
        )
        if ok and text.strip():
            new_title = text.strip()
            try:
                # 检查products表是否有title字段
                cursor = self.db.cursor
                cursor.execute("PRAGMA table_info(products)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'title' in columns:
                    # ✅ 正确：更新title字段（商品标题）
                    self.db.safe_execute(
                        "UPDATE products SET title=? WHERE id=?", 
                        (new_title, self.product_id)
                    )
                    self.product_name = new_title
                    self.lbl_name.setText(f"商品标题: <b>{new_title}</b>")
                    self.setWindowTitle(f"📦 规格与毛利管理 - {new_title}")
                    
                    # 更新主界面的商品标题显示
                    self.main_app.load_data_safe()
                    
                    self.main_app.show_toast(f"✅ 商品标题已更新为: {new_title}")
                else:
                    QMessageBox.warning(self, "提示", "数据库表结构不支持修改商品标题，请联系管理员")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"更新失败: {e}")
    
    def increase_roi_5_percent(self):
        """涨5%投产按钮点击事件"""
        try:
            self._set_roi_bid_input_mode("roi", user_action=True)
            current_text = self.current_roi_input.text().strip()
            if not current_text:
                # 如果没有输入，默认从1开始
                new_roi = 1.0
            else:
                current_roi = float(current_text)
                # 计算涨5%后的值，使用更精确的舍入
                new_roi = round(current_roi * 1.05, 2)
            
            # 更新输入框
            self.current_roi_input.setText(f"{new_roi:.2f}")
            # 触发计算
            self.on_current_roi_changed()
            
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的投产数值")

    def decrease_roi_5_percent(self):
        """降5%投产按钮点击事件"""
        try:
            self._set_roi_bid_input_mode("roi", user_action=True)
            current_text = self.current_roi_input.text().strip()
            if not current_text:
                new_roi = 1.0
            else:
                current_roi = float(current_text)
                new_roi = max(0.01, round(current_roi * 0.95, 2))

            self.current_roi_input.setText(f"{new_roi:.2f}")
            self.on_current_roi_changed()

        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的投产数值")

    def increase_bid_5_percent(self):
        """涨5%成交出价按钮点击事件"""
        try:
            self._set_roi_bid_input_mode("bid", user_action=True)
            current_text = self.transaction_bid_input.text().strip()
            if not current_text:
                new_bid = 1.0
            else:
                current_bid = float(current_text)
                new_bid = round(current_bid * 1.05, 2)
            self.transaction_bid_input.setText(f"{new_bid:.2f}")
            self.on_transaction_bid_changed()
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的成交出价")

    def decrease_bid_5_percent(self):
        """降5%成交出价按钮点击事件"""
        try:
            self._set_roi_bid_input_mode("bid", user_action=True)
            current_text = self.transaction_bid_input.text().strip()
            if not current_text:
                new_bid = 1.0
            else:
                current_bid = float(current_text)
                new_bid = max(0.01, round(current_bid * 0.95, 2))
            self.transaction_bid_input.setText(f"{new_bid:.2f}")
            self.on_transaction_bid_changed()
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的成交出价")

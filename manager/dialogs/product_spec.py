# -*- coding: utf-8 -*-
"""商品规格管理与毛利计算器对话框"""
import os
import re
import json
import requests
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QWidget, QLineEdit, QSpinBox,
    QComboBox, QFrame, QGridLayout, QAbstractItemView, QFileDialog,
    QProgressDialog, QApplication, QInputDialog, QTextEdit, QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QSize
from PyQt5.QtGui import QColor, QPixmap, QIcon

try:
    from ..delegates import SpecNameDelegate, CenterAlignDelegate, WeightDelegate
except ImportError:
    from delegates import SpecNameDelegate, CenterAlignDelegate, WeightDelegate

try:
    from .profit import ProfitCalculatorDialog
except ImportError:
    from profit import ProfitCalculatorDialog

try:
    from .api_config import SpecPromptEditorDialog, ProductPromptEditorDialog
except ImportError:
    from api_config import SpecPromptEditorDialog, ProductPromptEditorDialog

class ProductSpecDialog(QDialog):
    """商品规格管理与毛利计算器"""
    def __init__(self, db_manager, product_id, product_code, product_name, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.product_id = product_id
        self.product_code = product_code
        self.product_name = product_name
        self.main_app = parent
        self.setWindowTitle(f"📦 规格与毛利管理 - {product_name}")
        self.setWindowFlags(Qt.Window)
        self.resize(1380, 900)
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
        

    def delayed_refresh(self):
        """延迟刷新表格"""
        try:
            self.table.resizeRowsToContents()
            self.table.viewport().update()
            if hasattr(self, 'lbl_gross_break_even'):
                self.calculate_roi_metrics()
        except:
            pass

    def init_ui(self):
        layout = QVBoxLayout(self)

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
        self.lbl_code.setToolTip("双击修改商品ID")
        
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
        
        roi_grid.addWidget(QLabel("当前投产 (ROI):"), 0, 0)
        
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

        roi_grid.addWidget(QLabel("最佳投产:"), 1, 0)
        self.lbl_best_roi = QLabel("0.00")
        self.lbl_best_roi.setStyleSheet("font-weight: bold; color: #27ae60; background-color: #e8f8f5; padding: 5px 10px; border-radius: 3px;")
        self.lbl_best_roi.setAlignment(Qt.AlignCenter)
        roi_grid.addWidget(self.lbl_best_roi, 1, 1)

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

        roi_layout.addLayout(roi_grid)
        
        roi_widget.setStyleSheet("background-color: #f8f9fa; border-radius: 5px; border: 1px solid #dee2e6;")
        layout.addWidget(roi_widget)

        # 规格表格区

        # 2. 规格表格
        self.table = QTableWidget()
        self.table.setColumnCount(14)
        self.table.setHorizontalHeaderLabels([
            "", "规格名称", "关联编码", "自动成本", "手动售价", "券后价", "单规格毛利", "权重%", "权重对比\n(较上周)", "单量", "单量对比\n(较上周)", "退款订单", "退款占比\n(单规格)", "操作"
        ])
        
        # 设置列宽策略 - AI列和规格名称列固定宽度，其他列自适应拉伸
        header = self.table.horizontalHeader()

        # AI按钮列(索引0)固定宽度
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50)

        # 规格名称列(索引1)固定宽度（增加40像素）
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 180)

        # 其他列自适应拉伸
        for i in range(2, 14):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

        self.table.setAlternatingRowColors(False)

        # 设置表格字体和样式
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
            }
            QTableWidget::item {
                text-align: center;
                font-weight: normal;
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
                font-weight: bold;
            }
        """)
        
        # 设置默认行高，确保输入框显示完整
        self.table.verticalHeader().setDefaultSectionSize(35)  # 设置合适的行高
        
        # 启用自动行高调整
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        # 设置数值列居中显示（关联编码、自动成本、手动售价、券后价、单规格毛利、权重%）
        self.center_delegate = CenterAlignDelegate(self)
        for col in [2, 3, 4, 5, 6, 7]:
            self.table.setItemDelegateForColumn(col, self.center_delegate)
        
        layout.addWidget(self.table)
        
        # 设置代理
        # 规格名称列（最多40字符）
        self.spec_name_delegate = SpecNameDelegate(self)
        self.table.setItemDelegateForColumn(1, self.spec_name_delegate)
        
        # 权重列
        self.weight_delegate = WeightDelegate(self)
        self.table.setItemDelegateForColumn(7, self.weight_delegate)

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

    def eventFilter(self, obj, event):
        """事件过滤器：处理标签双击事件"""
        if event.type() == QEvent.MouseButtonDblClick:
            if obj == self.lbl_code:
                self.edit_product_code()
                return True
            elif obj == self.lbl_name:
                self.edit_product_name()
                return True
        return super().eventFilter(obj, event)

    def load_specs(self):
        """从数据库加载规格数据到表格，并初始化删除功能"""
        try:
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
                
                self.coupon_input.setText(str(coupon_amount) if coupon_amount > 0 else "")
                self.new_customer_input.setText(str(new_customer_discount) if new_customer_discount > 0 else "")
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
                "SELECT spec_name, spec_code, sale_price, weight_percent, is_locked FROM product_specs WHERE product_id=?",
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
                
                # 记录原始编码
                if spec_code:
                    self.original_spec_codes.add(spec_code)
                
                # 获取成本价
                cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
                cost_price = float(cost_res[0][0]) if cost_res else 0.0
                
                # 计算单行毛利
                margin_pct = 0.0
                if sale_price > 0:
                    margin_pct = (sale_price - cost_price) / sale_price * 100
                
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
                
                self.table.setCellWidget(row_idx, 0, ai_widget)
                
                # 第1列：规格名称（最多40字符）
                spec_item = QTableWidgetItem(spec_name)
                spec_item.setToolTip("规格名称（最多40字符）")
                self.table.setItem(row_idx, 1, spec_item)
                # 第2列：关联编码
                self.table.setItem(row_idx, 2, QTableWidgetItem(spec_code))
                
                # 成本列 (不可编辑)
                cost_item = QTableWidgetItem(f"{cost_price:.2f}")
                cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 3, cost_item)
                
                self.table.setItem(row_idx, 4, QTableWidgetItem(f"{sale_price:.2f}"))
                
                # 券后价列 (不可编辑) = 手动售价 - 最大优惠
                coupon_amount = discount_rows[0][0] if discount_rows and discount_rows[0][0] else 0
                new_customer_amount = discount_rows[0][1] if discount_rows and discount_rows[0][1] else 0
                max_discount = max(coupon_amount, new_customer_amount)
                final_price = sale_price - max_discount
                final_price_item = QTableWidgetItem(f"{final_price:.2f}")
                final_price_item.setFlags(final_price_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 5, final_price_item)

                # 毛利列 (不可编辑)
                margin_item = QTableWidgetItem(f"{margin_pct:.2f}%")
                margin_item.setFlags(margin_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 6, margin_item)

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
                if is_locked == 1:
                    weight_text = f"🔒 {display_weight:.2f}%"
                else:
                    weight_text = f"{display_weight:.2f}%"
                weight_item = QTableWidgetItem(weight_text)
                weight_item.setData(Qt.UserRole, display_weight)
                if order_count > 0:
                    weight_item.setToolTip(f"订单数: {order_count}单")
                elif has_imported_orders:
                    weight_item.setToolTip("该规格无订单")
                self.table.setItem(row_idx, 7, weight_item)
                
                # 第 8 列添加权重对比
                weight_compare_widget = QWidget()
                weight_compare_layout = QHBoxLayout(weight_compare_widget)
                weight_compare_layout.setContentsMargins(0, 0, 0, 0)
                weight_compare_layout.setAlignment(Qt.AlignCenter)
                weight_compare_label = QLabel("-")
                weight_compare_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
                weight_compare_layout.addWidget(weight_compare_label)
                self.table.setCellWidget(row_idx, 8, weight_compare_widget)

                # 第 9 列添加单量
                order_count_item = QTableWidgetItem(f"{order_count}单")
                order_count_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, 9, order_count_item)

                # 第 10 列添加单量对比
                order_compare_widget = QWidget()
                order_compare_layout = QHBoxLayout(order_compare_widget)
                order_compare_layout.setContentsMargins(0, 0, 0, 0)
                order_compare_layout.setAlignment(Qt.AlignCenter)
                order_compare_label = QLabel("-")
                order_compare_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
                order_compare_layout.addWidget(order_compare_label)
                self.table.setCellWidget(row_idx, 10, order_compare_widget)

                # 第 11 列添加退款订单
                refund_orders_item = QTableWidgetItem(f"{refund_count}单" if refund_count > 0 else "无")
                refund_orders_item.setTextAlignment(Qt.AlignCenter)
                refund_orders_item.setFlags(refund_orders_item.flags() & ~Qt.ItemIsEditable)
                if refund_count > 0:
                    refund_orders_item.setForeground(QColor("#e74c3c"))
                else:
                    refund_orders_item.setForeground(QColor("#95a5a6"))
                self.table.setItem(row_idx, 11, refund_orders_item)

                # 第 12 列添加退款占比
                if order_count > 0 and refund_count > 0:
                    refund_ratio = refund_count / order_count * 100
                    refund_ratio_item = QTableWidgetItem(f"{refund_ratio:.2f}%")
                    refund_ratio_item.setForeground(QColor("#e74c3c"))
                else:
                    refund_ratio_item = QTableWidgetItem("无")
                    refund_ratio_item.setForeground(QColor("#95a5a6"))
                refund_ratio_item.setTextAlignment(Qt.AlignCenter)
                refund_ratio_item.setFlags(refund_ratio_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_idx, 12, refund_ratio_item)

                # 第 13 列添加删除按钮
                btn_delete = QPushButton("🗑️")
                btn_delete.setToolTip("删除此规格")
                btn_delete.setStyleSheet("""
                    QPushButton {
                        background-color: #ff4d4f; color: white; border-radius: 4px; font-weight: bold; font-size: 12px;
                    }
                    QPushButton:hover { background-color: #ff7875; }
                    QPushButton:pressed { background-color: #d9363e; }
                """)
                btn_delete.clicked.connect(lambda checked, r=row_idx: self.delete_spec_row(r))
                self.table.setCellWidget(row_idx, 13, btn_delete)
                
                # 🔑【关键修复】强制更新表格
                self.table.update()
            
            # 5. 加载完成后，计算一次综合毛利
            self.calculate_total_margin()
            self.update_remaining_weight_label()
            self.update_total_orders_label()
            self.update_compare_columns()

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

    def delete_spec_row(self, row):
        """
        【中文功能说明】
        删除指定行的规格。
        逻辑：确认 -> 移除行 -> 自动重算剩余权重 (归一化到 100%) -> 更新界面
        """
        # 1. 获取该行信息
        name_item = self.table.item(row, 0)
        code_item = self.table.item(row, 1)
        spec_name = name_item.text() if name_item else "未知"
        spec_code = code_item.text() if code_item else "未知"
        
        # 2. 二次确认
        reply = QMessageBox.question(
            self, '确认删除', 
            f'确定要删除规格 "{spec_name}" ({spec_code}) 吗？\n\n删除后，剩余规格的权重将自动按比例重新分配为 100%。',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 3. 移除行
            self.table.removeRow(row)
            
            # 4. 自动重算权重 (归一化)
            # 这里直接调用一个简单的归一化逻辑，或者复用 average_weights 的逻辑
            self.normalize_weights_after_delete()
            
            QMessageBox.information(self, "提示", f"已移除 {spec_name}。\n请点击“保存”按钮使更改生效。")

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
                w_item = self.table.item(r, 7) # 权重列是第 8 列 (索引 7)
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
                
                w_item = self.table.item(r, 7)
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
                w_item = self.table.item(r, 7) # 权重列 (第8列)
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
                
                w_item = self.table.item(r, 7)
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
        """重新计算某一行的毛利率并更新到第5列"""
        price_item = self.table.item(row, 3) # 售价
        code_item = self.table.item(row, 1)  # 编码
        margin_item = self.table.item(row, 5) # 毛利列
        
        if not price_item or not code_item or not margin_item:
            return
        
        try:
            price = float(price_item.text())
            code = code_item.text()
            
            # 查成本
            cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (code,))
            cost = float(cost_res[0][0]) if cost_res else 0.0
            
            if price > 0:
                margin = (price - cost) / price * 100
                margin_item.setText(f"{margin:.2f}%")
        except:
            pass

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
        try:
            current_roi_text = self.current_roi_input.text().strip()
            if not current_roi_text:
                self.lbl_net_profit_rate.setText("0.00%")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #999; background-color: #f0f0f0; padding: 5px 10px; border-radius: 3px;")
                self.lbl_roi_multiple.setText("--")
                return
            
            current_roi = float(current_roi_text)
            
            if current_roi <= 0:
                self.lbl_net_profit_rate.setText("0.00%")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #999; background-color: #f0f0f0; padding: 5px 10px; border-radius: 3px;")
                self.lbl_roi_multiple.setText("--")
                return
            
            margin_rate = self.get_current_margin_rate()
            if margin_rate <= 0:
                self.lbl_net_profit_rate.setText("请设置毛利")
                self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #e74c3c; background-color: #fdeaea; padding: 5px 10px; border-radius: 3px;")
                self.lbl_roi_multiple.setText("--")
                return
            
            return_rate = self.get_return_rate()
            
            # 计算净保本投产
            net_margin_formula = margin_rate * (1 - return_rate / 100) - 0.0006
            net_break_even = 1 / net_margin_formula if net_margin_formula > 0 else 0
            
            # 净利率 = 毛利率×(1-退货率)-0.006-(1÷投产比)
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
            
            # 计算并显示投产倍数
            if net_break_even > 0:
                roi_multiple = current_roi / net_break_even
                self.lbl_roi_multiple.setText(f"{roi_multiple:.2f}倍")
            else:
                self.lbl_roi_multiple.setText("--")
            
            # 计算放量投产（净保本投产的0.8倍）
            if net_break_even > 0:
                scale_roi = net_break_even * 0.8
                self.lbl_scale_roi.setText(f"{scale_roi:.2f}")
            else:
                self.lbl_scale_roi.setText("--")
            
            # 计算推广占比（1/当前投产）
            if current_roi > 0:
                promotion_ratio = (1 / current_roi) * 100
                self.lbl_promotion_ratio.setText(f"{promotion_ratio:.2f}%")
            else:
                self.lbl_promotion_ratio.setText("--")
                
        except ValueError:
            self.lbl_net_profit_rate.setText("0.00%")
            self.lbl_net_profit_rate.setStyleSheet("font-weight: bold; color: #999; background-color: #f0f0f0; padding: 5px 10px; border-radius: 3px;")
            self.lbl_roi_multiple.setText("--")
            self.lbl_scale_roi.setText("--")
            self.lbl_promotion_ratio.setText("--")
    
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
        
        self.table.setCellWidget(idx, 0, ai_widget)
        
        # 第1列：规格名称（最多40字符）
        spec_item = QTableWidgetItem(f"新规格{idx+1}")
        spec_item.setToolTip("规格名称（最多40字符）")
        self.table.setItem(idx, 1, spec_item)
        # 第2列：关联编码
        self.table.setItem(idx, 2, QTableWidgetItem(""))
        
        # 第3列：自动成本（不可编辑）
        cost_item = QTableWidgetItem("")
        cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(idx, 3, cost_item)
        
        # 第4列：手动售价
        self.table.setItem(idx, 4, QTableWidgetItem(""))
        
        # 第5列：券后价（不可编辑）
        final_price_item = QTableWidgetItem("0.00")
        final_price_item.setFlags(final_price_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(idx, 5, final_price_item)
        
        # 第6列：单规格毛利（不可编辑）
        margin_item = QTableWidgetItem("0.00%")
        margin_item.setFlags(margin_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(idx, 6, margin_item)
        
        # 第7列：权重
        self.table.setItem(idx, 7, QTableWidgetItem("0"))

        # 第8列：权重对比
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
        self.table.setCellWidget(idx, 8, weight_compare_widget)

        # 第9列：单量
        order_count_item = QTableWidgetItem("0单")
        order_count_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(idx, 9, order_count_item)

        # 第10列：单量对比
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
        self.table.setCellWidget(idx, 10, order_compare_widget)

        # 第11列：退款订单
        refund_orders_item = QTableWidgetItem("无")
        refund_orders_item.setTextAlignment(Qt.AlignCenter)
        refund_orders_item.setFlags(refund_orders_item.flags() & ~Qt.ItemIsEditable)
        refund_orders_item.setForeground(QColor("#95a5a6"))
        self.table.setItem(idx, 11, refund_orders_item)

        # 第12列：退款占比
        refund_ratio_item = QTableWidgetItem("无")
        refund_ratio_item.setTextAlignment(Qt.AlignCenter)
        refund_ratio_item.setFlags(refund_ratio_item.flags() & ~Qt.ItemIsEditable)
        refund_ratio_item.setForeground(QColor("#95a5a6"))
        self.table.setItem(idx, 12, refund_ratio_item)

        # 第13列：删除按钮
        btn_delete = QPushButton("🗑️")
        btn_delete.setToolTip("删除此规格")
        btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #ff4d4f; color: white; border-radius: 4px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #ff7875; }
            QPushButton:pressed { background-color: #d9363e; }
        """)
        btn_delete.clicked.connect(lambda checked, r=idx: self.delete_spec_row(r))
        self.table.setCellWidget(idx, 13, btn_delete)

        self.table.scrollToBottom()

    def on_cell_change(self, row, col):
        """单元格变化处理：包含智能权重平衡（防死循环版）"""
        
        # 🔒【关键】如果正在自动平衡中，直接返回，不要再次触发
        if self.is_balancing:
            return
        
        # 1. 如果是权重列变化，触发智能平衡
        if col == 7:
            item = self.table.item(row, 7)
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
            
        elif col == 2:  # 关联编码变化 -> 查成本
            self.fetch_cost(row)
            self.calculate_row_margin(row)
            self.calculate_total_margin()
            
        elif col == 4:  # 手动售价变化 -> 算单行毛利
            self.calculate_row_margin(row)
            self.calculate_total_margin()
            
        else:
            # 其他变化只刷新总毛利
            self.calculate_total_margin()
        
        # 确保毛保本等指标实时更新
        if hasattr(self, 'lbl_gross_break_even'):
            self.calculate_roi_metrics()
    
    def calculate_locked_weight_sum(self):
        """计算所有已锁定规格的权重总和"""
        total_locked = 0.0
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 7)
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
        item_changed = self.table.item(changed_row, 7)
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
            
            item = self.table.item(r, 7)
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
            
            item = self.table.item(r, 7)
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
                item = self.table.item(r, 7)
                if item:
                    # 保持原来的锁定状态（虽然这里肯定是未锁定的）
                    item.setData(Qt.DisplayRole, f"{avg:.2f}")
        else:
            # 如果其他行全被锁定了，那就没办法分了，保持现状
            pass

    def fetch_cost(self, row):
        """根据关联编码获取成本"""
        code_item = self.table.item(row, 2)
        code = code_item.text().strip() if code_item else ""
        if not code:
            item_cost = self.table.item(row, 3)
            if item_cost: item_cost.setText("")
            self.calculate_row_margin(row)
            self.calculate_total_margin()
            return
        
        res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (code,))
        if res:
            cost = res[0][0]
            item_cost = self.table.item(row, 3)
            if item_cost: item_cost.setText(f"{cost:.2f}")
            self.calculate_row_margin(row)
            self.calculate_total_margin()
        else:
            item_cost = self.table.item(row, 3)
            if item_cost: item_cost.setText("")
            item_margin = self.table.item(row, 6)
            if item_margin: item_margin.setText("未找到成本")
            self.calculate_total_margin()

    def calculate_row_margin(self, row):
        """计算单行毛利"""
        item_cost = self.table.item(row, 3)
        item_price = self.table.item(row, 4)
        item_final_price = self.table.item(row, 5)
        item_margin = self.table.item(row, 6)
        
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
            price_item = self.table.item(r, 4)
            code_item = self.table.item(r, 2)
            margin_item = self.table.item(r, 6)
            weight_item = self.table.item(r, 7)

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
        item = self.table.item(row, 1)
        if not item or not item.text().strip():
            QMessageBox.warning(self, "⚠️ 提示", "该规格没有名称！")
            return
        
        original_name = item.text().strip()
        
        api_key = self.db.get_setting("ai_api_key", "")
        if not api_key:
            QMessageBox.warning(self, "⚠️ 提示", "请先在API配置中设置API Key！")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("🤖 选择优化类型")
        dialog.setMinimumWidth(300)
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("请选择规格名称优化类型："))
        
        btn_high = QPushButton("🎯 高转化（提升购买意愿）")
        btn_high.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)

        btn_high_preview = QPushButton("👁️ 预览")
        btn_high_preview.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 5px 10px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        btn_high_preview.clicked.connect(lambda: self._show_optimization_preview_dialog(original_name, "high", dialog))

        btn_low = QPushButton("⚠️ 低转化（降低购买意愿）")
        btn_low.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)

        btn_low_preview = QPushButton("👁️ 预览")
        btn_low_preview.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 5px 10px;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        btn_low_preview.clicked.connect(lambda: self._show_optimization_preview_dialog(original_name, "low", dialog))

        def start_optimize(prompt_type, row):
            dialog.close()
            self._show_optimization_preview_dialog(original_name, prompt_type, row=row)

        btn_high.clicked.connect(lambda: start_optimize("high", row))
        btn_low.clicked.connect(lambda: start_optimize("low", row))

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

        high_layout = QHBoxLayout()
        high_layout.addWidget(btn_high)
        high_layout.addWidget(btn_high_preview)
        layout.addLayout(high_layout)

        low_layout = QHBoxLayout()
        low_layout.addWidget(btn_low)
        low_layout.addWidget(btn_low_preview)
        layout.addLayout(low_layout)

        layout.addWidget(btn_common_rules)

        dialog.exec_()

    def _show_optimization_preview_dialog(self, original_name, prompt_type, parent_dialog=None, row=None):
        """显示优化预览窗口：展示条件、选择的提示词、生成预览"""
        dialog = QDialog(parent_dialog or self)
        dialog.setWindowTitle("🤖 规格优化预览")
        dialog.resize(800, 650)
        main_layout = QVBoxLayout(dialog)

        header = QLabel("🤖 规格优化预览")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        main_layout.addWidget(header)

        mode_color = "#27ae60" if prompt_type == "high" else "#e74c3c"
        mode_icon = "🎯 高转化" if prompt_type == "high" else "⚠️ 低转化"
        mode_label = QLabel(f"当前模式：{mode_icon}")
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

        if margin_rate >= 25:
            margin_level = "高毛利(≥25%)"
            margin_color = "#27ae60"
        else:
            margin_level = "低毛利(<25%)"
            margin_color = "#e74c3c"

        margin_level_label = QLabel(f"📈 当前毛利等级：{margin_level}")
        margin_level_label.setStyleSheet(f"font-size: 12px; color: {margin_color}; font-weight: bold; padding: 8px; background-color: #f8f9fa; border-radius: 4px;")
        scroll_layout.addWidget(margin_level_label)

        if prompt_type == "high" and margin_rate >= 25:
            strategy_name = "高转化+高毛利"
            strategy_key = "ai_high_high_margin_prompt"
        elif prompt_type == "high" and margin_rate < 25:
            strategy_name = "高转化+低毛利"
            strategy_key = "ai_high_low_margin_prompt"
        elif prompt_type == "low" and margin_rate >= 25:
            strategy_name = "低转化+高毛利"
            strategy_key = "ai_low_high_margin_prompt"
        else:
            strategy_name = "低转化+低毛利"
            strategy_key = "ai_low_low_margin_prompt"

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

        store_memo = ""
        try:
            store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.product_id,))
            if store_rows and store_rows[0]:
                store_id = store_rows[0][0]
                memo_rows = self.db.safe_fetchall("SELECT memo FROM stores WHERE id=?", (store_id,))
                store_memo = memo_rows[0][0] if memo_rows and memo_rows[0][0] else ""
        except Exception:
            pass

        forbidden = self.db.get_setting("ai_spec_forbidden_words", "")
        if forbidden:
            tag_configs.append(("🚫 违禁词", "#e74c3c"))

        product_info = self.db.get_setting("ai_product_info_prompt", "")
        if product_info:
            tag_configs.append(("🛒 产品信息", "#3498db"))

        product_attr = self.db.get_setting("ai_spec_attr_prompt", "")
        if product_attr:
            tag_configs.append(("📦 商品属性", "#9b59b6"))

        spec_prompt = self.db.get_setting("ai_spec_high_prompt" if prompt_type == "high" else "ai_spec_low_prompt", "")
        if spec_prompt:
            tag_configs.append((mode_icon, mode_color))

        strategy_prompt = self.db.get_setting(strategy_key, "")
        if strategy_prompt:
            tag_configs.append(("💰 " + strategy_name, margin_color))

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
        btn_view_prompts.clicked.connect(lambda: self._show_prompt_detail_dialog(dialog, prompt_type, strategy_name, margin_rate))
        tags_layout.addWidget(btn_view_prompts)

        scroll_layout.addWidget(tags_card)

        full_prompt = self._build_full_prompt_text_optimized(original_name, prompt_type)
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
        saved_label = QLabel("💡 已优化：仅调用1个毛利策略，节省Tokens")
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
        btn_generate.clicked.connect(lambda: self._start_optimize_from_preview(original_name, prompt_type, dialog, row))
        btn_layout.addWidget(btn_generate)

        main_layout.addLayout(btn_layout)

        dialog.exec_()

    def _start_optimize_from_preview(self, original_name, prompt_type, parent_dialog=None, row=None):
        """从预览窗口确认并开始优化"""
        if parent_dialog:
            parent_dialog.accept()
        if row is None:
            row = self.table.currentRow()
        if row >= 0:
            self._do_ai_optimize(row, original_name, prompt_type)

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

    def _build_full_prompt_text_optimized(self, original_name, prompt_type):
        """构建优化后的完整API提示词文本（仅使用一个毛利策略）"""
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

        lines.append("【4. 所有规格信息】")
        lines.append("-" * 40)
        specs_layout = self._get_specs_with_margin()
        lines.append(specs_layout)
        lines.append("")

        lines.append("【5. 当前优化规格】")
        lines.append("-" * 40)
        lines.append(f"正在优化：{original_name}")
        lines.append("")

        margin_rate = self.get_current_margin_rate() * 100
        if prompt_type == "high" and margin_rate >= 25:
            setting_key = "ai_high_high_margin_prompt"
            strategy_name = "高转化+高毛利(≥25%)"
        elif prompt_type == "high" and margin_rate < 25:
            setting_key = "ai_high_low_margin_prompt"
            strategy_name = "高转化+低毛利(<25%)"
        elif prompt_type == "low" and margin_rate >= 25:
            setting_key = "ai_low_high_margin_prompt"
            strategy_name = "低转化+高毛利(≥25%)"
        else:
            setting_key = "ai_low_low_margin_prompt"
            strategy_name = "低转化+低毛利(<25%)"

        margin_strategy = self.db.get_setting(setting_key, "")

        lines.append(f"【6. 毛利策略：{strategy_name}】")
        lines.append("-" * 40)
        lines.append(margin_strategy.strip())
        lines.append("")

        lines.append("【7. 店铺运营大纲】")
        lines.append("-" * 40)
        store_memo = ""
        try:
            store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.product_id,))
            if store_rows and store_rows[0]:
                store_id = store_rows[0][0]
                memo_rows = self.db.safe_fetchall("SELECT memo FROM stores WHERE id=?", (store_id,))
                store_memo = memo_rows[0][0] if memo_rows and memo_rows[0][0] else ""
        except Exception:
            pass
        if store_memo:
            lines.append(store_memo)
        else:
            lines.append("（未设置店铺运营大纲）")
        lines.append("")

        if prompt_type == "high":
            lines.append("【8. 高转化规格优化提示词】")
            lines.append("-" * 40)
            spec_prompt = self.db.get_setting("ai_spec_high_prompt", "")
            if spec_prompt:
                lines.append(spec_prompt)
            else:
                lines.append("（使用默认高转化提示词）")
        else:
            lines.append("【8. 低转化规格优化提示词】")
            lines.append("-" * 40)
            spec_prompt = self.db.get_setting("ai_spec_low_prompt", "")
            if spec_prompt:
                lines.append(spec_prompt)
            else:
                lines.append("（使用默认低转化提示词）")

        lines.append("")
        lines.append("=" * 60)
        lines.append("【User Prompt（用户输入）】")
        lines.append("=" * 60)
        lines.append(f"商品标题：{self.product_name}")
        lines.append("")
        lines.append(f"原规格名称：{original_name}")

        return "\n".join(lines)

    def _do_ai_optimize(self, row, original_name, prompt_type):
        """执行AI优化"""
        api_key = self.db.get_setting("ai_api_key", "")
        if not api_key:
            QMessageBox.warning(self, "⚠️ 提示", "请先在API配置中设置API Key！")
            return

        store_memo = ""
        try:
            store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.product_id,))
            if store_rows and store_rows[0]:
                store_id = store_rows[0][0]
                memo_rows = self.db.safe_fetchall("SELECT memo FROM stores WHERE id=?", (store_id,))
                store_memo = memo_rows[0][0] if memo_rows and memo_rows[0][0] else ""
        except Exception as e:
            print(f"获取店铺备注失败: {e}")

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
        product_info = self._build_product_info_prompt(original_name)

        priority_prompt = ""
        if store_memo:
            priority_prompt = f"""【店铺运营指导大纲 - 最高优先级】
{store_memo}

"""

        margin_rate = self.get_current_margin_rate() * 100
        if prompt_type == "high" and margin_rate >= 25:
            setting_key = "ai_high_high_margin_prompt"
            strategy_name = "高转化+高毛利(≥25%)"
        elif prompt_type == "high" and margin_rate < 25:
            setting_key = "ai_high_low_margin_prompt"
            strategy_name = "高转化+低毛利(<25%)"
        elif prompt_type == "low" and margin_rate >= 25:
            setting_key = "ai_low_high_margin_prompt"
            strategy_name = "低转化+高毛利(≥25%)"
        else:
            setting_key = "ai_low_low_margin_prompt"
            strategy_name = "低转化+低毛利(<25%)"

        margin_strategy = self.db.get_setting(setting_key, "")

        output_format = """【输出格式要求】
必须生成10个不同的规格名称。
每个规格名称必须有明显差异（使用不同的风格、卖点、词汇组合）。
每个规格名称必须包含风格标记，格式为：【风格名】，例如：【热销爆款】、【限时优惠】、【性价比之王】、【品质保障】、【新品首发】等。
每个规格名称的总字数（包括风格标记）必须达到40个字符左右。
保留原规格的核心词（如数量、尺码、款式等），并在基础上扩展描述。
直接输出10个新规格名，一行一个，不要解释。

"""

        if prompt_type == "high":
            spec_prompt = self.db.get_setting("ai_spec_high_prompt", "")
            prompt_text = forbidden_rule + product_attr_prompt + margin_strategy + priority_prompt + output_format + spec_prompt
        else:
            spec_prompt = self.db.get_setting("ai_spec_low_prompt", "")
            prompt_text = forbidden_rule + product_attr_prompt + margin_strategy + priority_prompt + output_format + spec_prompt

        user_prompt = f"商品标题：{self.product_name}\n\n原规格名称：{original_name}"
        
        progress = QProgressDialog("正在调用AI优化...", "取消", 0, 0, self)
        progress.setWindowTitle("🤖 AI处理中")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        
        try:
            api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/v1/chat/completions")
            model = self.db.get_setting("ai_model", "deepseek-chat")
            
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
            
            response = requests.post(api_url, headers=headers, json=data, timeout=60)
            
            progress.close()
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result["choices"][0]["message"]["content"].strip()
                
                self.show_ai_result_dialog(row, original_name, ai_response, prompt_type)
            else:
                QMessageBox.warning(self, "❌ 错误", f"API调用失败：{response.status_code}")
                
        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "❌ 错误", f"发生错误：{str(e)}")
    
    def show_ai_result_dialog(self, row, original_name, optimized_name, prompt_type="high"):
        """显示AI优化结果对话框（10条选项供选择）"""
        options = self._parse_ai_options(optimized_name)
        options = self._filter_forbidden_words(options)

        if not options:
            QMessageBox.warning(self, "⚠️ 提示", f"AI生成的所有规格名称都包含违禁词，请重新生成或调整违禁词设置！")
            return

        self._current_row = row
        self._current_original_name = original_name
        self._current_prompt_type = prompt_type

        dialog = QDialog(self)
        dialog.setWindowTitle("🤖 AI优化结果（选择1个）")
        dialog.setMinimumWidth(800)
        dialog.setMinimumHeight(600)
        layout = QVBoxLayout(dialog)

        mode_text = "🎯 高转化" if prompt_type == "high" else "⚠️ 低转化"
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"当前模式：{mode_text}"))
        header_layout.addWidget(QLabel(f"原规格名称：{original_name}"))
        header_layout.addStretch()
        layout.addLayout(header_layout)

        layout.addWidget(QLabel("请选择优化后的规格名称（风格标记仅供观看，选择时不会复制到规格）："))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(450)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)

        style_names = [
            "热销爆款", "限时优惠", "赠品福利", "性价比之王", "品质保障",
            "新品首发", "实用推荐", "环保健康", "明星同款", "回头客",
            "容量太小", "性价比低", "限时缺货", "质量问题", "适用范围窄",
            "赠品少", "寿命短", "回头率低", "替代品", "谨慎购买"
        ]

        import re

        for i, option in enumerate(options):
            style_text = ""
            style_match = re.search(r'【([^】]+)】', option)
            if style_match:
                style_text = style_match.group(1)

            spec_name = re.sub(r'^【[^】]+】\s*', '', option)

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

            style_label = QLabel(style_text if style_text else "未知")
            if style_text:
                style_label.setStyleSheet("""
                    QLabel {
                        background-color: #9b59b6;
                        color: white;
                        padding: 5px 10px;
                        border-radius: 12px;
                        font-size: 11px;
                        font-weight: bold;
                    }
                """)
            else:
                style_label.setStyleSheet("""
                    QLabel {
                        background-color: #95a5a6;
                        color: white;
                        padding: 5px 10px;
                        border-radius: 12px;
                        font-size: 11px;
                    }
                """)
            style_label.setMinimumWidth(100)
            style_label.setAlignment(Qt.AlignCenter)
            container_layout.addWidget(style_label)

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
            container_layout.setStretch(2, 1)

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
                final_name = opt_text
                self.table.item(r, 1).setText(final_name)

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
            prompt_type = getattr(self, '_current_prompt_type', 'high')
            self._do_ai_optimize(self._current_row, self._current_original_name, prompt_type)
            dialog.accept()
        
        btn_refresh.clicked.connect(refresh_result)
        
        btn_close = QPushButton("❌ 关闭")
        btn_close.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_refresh)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
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
            line = line.replace('·', '').replace('•', '')

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

    def _get_margin_strategy_prompt(self, prompt_type):
        """根据高/低转化类型和毛利率获取策略提示词"""
        margin_rate = self.get_current_margin_rate() * 100

        if prompt_type == "high":
            if margin_rate >= 25:
                prompt = self.db.get_setting("ai_high_high_margin_prompt", "")
                if not prompt:
                    prompt = """【毛利策略：高转化 + 高毛利(≥25%)

当前产品毛利率较高，选择高转化模式。

【核心策略】
1. 以产品质量、功能、耐用性为卖点
2. 强调品质上乘、经久耐用
3. 突出产品的核心功能和独特卖点
4. 暗示使用寿命长、性价比高（单位使用成本低）
5. 适合追求品质的顾客群体

请结合产品本身的特点和功能，生成能体现产品价值的规格名称。"""
            else:
                prompt = self.db.get_setting("ai_high_low_margin_prompt", "")
                if not prompt:
                    prompt = """【毛利策略：高转化 + 低毛利(<25%)

当前产品毛利率较低，选择高转化模式。

【核心策略】
1. 以低价优势、实惠、性价比为卖点
2. 强调价格优惠、促销力度大
3. 制造紧迫感，促进快速下单
4. 暗示赠品多、套餐划算
5. 适合价格敏感的顾客群体

请结合产品的价格优势，生成能促进快速下单的规格名称。"""
        else:
            if margin_rate >= 25:
                prompt = self.db.get_setting("ai_low_high_margin_prompt", "")
                if not prompt:
                    prompt = """【毛利策略：低转化 + 高毛利(≥25%)

当前产品毛利率较高，选择低转化模式。
目标：让顾客觉得这个产品不适合自己，主动选择其他规格。

【核心策略】
1. 强调价格偏高、不实惠
2. 暗示性价比低、不值得
3. 突出产品可能存在的缺点或局限
4. 让顾客觉得"买这个不划算"

请生成让顾客觉得"不适合我"的规格名称。"""
            else:
                prompt = self.db.get_setting("ai_low_low_margin_prompt", "")
                if not prompt:
                    prompt = """【毛利策略：低转化 + 低毛利(<25%)

当前产品毛利率较低，选择低转化模式。
目标：让顾客觉得这个产品不适合自己，主动选择其他规格。

【核心策略】
1. 强调价格看似便宜但实际不优惠
2. 暗示"便宜没好货"
3. 突出产品可能偷工减料或质量一般
4. 让顾客觉得"买这个不明智"

请生成让顾客觉得"不适合我"的规格名称。"""

        return prompt + "\n\n"
    
    def _show_prompt_detail_dialog(self, parent_dialog, prompt_type, strategy_name, margin_rate):
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

        prompt_items = [
            ("🚫 违禁词过滤", "ai_spec_forbidden_words", True),
            ("🛒 产品信息", "ai_product_info_prompt", False),
            ("📦 商品属性提示词", "ai_spec_attr_prompt", False),
            ("🎯 高转化提示词" if prompt_type == "high" else "⚠️ 低转化提示词",
             "ai_spec_high_prompt" if prompt_type == "high" else "ai_spec_low_prompt", False),
            ("💰 毛利策略: " + strategy_name,
             "ai_high_high_margin_prompt" if prompt_type == "high" and margin_rate >= 25 else
             "ai_high_low_margin_prompt" if prompt_type == "high" and margin_rate < 25 else
             "ai_low_high_margin_prompt" if prompt_type == "low" and margin_rate >= 25 else
             "ai_low_low_margin_prompt", False),
        ]

        store_memo = ""
        try:
            store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.product_id,))
            if store_rows and store_rows[0]:
                store_id = store_rows[0][0]
                memo_rows = self.db.safe_fetchall("SELECT memo FROM stores WHERE id=?", (store_id,))
                store_memo = memo_rows[0][0] if memo_rows and memo_rows[0][0] else ""
        except Exception:
            pass

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
            ("🎯 高转化提示词", "ai_spec_high_prompt", "规格优化提示词配置 → 高转化标签页"),
            ("⚠️ 低转化提示词", "ai_spec_low_prompt", "规格优化提示词配置 → 低转化标签页"),
            ("🚫 违禁词过滤", "ai_spec_forbidden_words", "规格优化提示词配置 → 违禁词设置按钮"),
            ("💰 高转化+高毛利策略", "ai_high_high_margin_prompt", "产品提示词配置 → 高转化+高毛利标签页"),
            ("💰 高转化+低毛利策略", "ai_high_low_margin_prompt", "产品提示词配置 → 高转化+低毛利标签页"),
            ("💰 低转化+高毛利策略", "ai_low_high_margin_prompt", "产品提示词配置 → 低转化+高毛利标签页"),
            ("💰 低转化+低毛利策略", "ai_low_low_margin_prompt", "产品提示词配置 → 低转化+低毛利标签页"),
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
        if setting_key == "ai_spec_attr_prompt":
            dialog = SpecPromptEditorDialog(self.db, self)
            dialog.exec_()
        elif setting_key == "ai_spec_high_prompt":
            dialog = SpecPromptEditorDialog(self.db, self)
            dialog.exec_()
        elif setting_key == "ai_spec_low_prompt":
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
                            return json.loads(snapshot_data).get("orders", {})
                    except:
                        pass

            # 如果没找到，返回None
            return None
        except Exception as e:
            return None

    def _update_spec_compare_labels(self, row, current_count, last_count, current_total):
        """更新指定行的对比列标签"""
        weight_compare_widget = self.table.cellWidget(row, 8)
        order_compare_widget = self.table.cellWidget(row, 10)

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

        current_weight = (current_count / current_total * 100) if current_total > 0 else 0
        last_total = sum(self._get_last_snapshot_values().values()) if self._get_last_snapshot_values() else 0
        last_weight = (last_count / last_total * 100) if last_total > 0 else 0

        weight_change = current_weight - last_weight
        order_change = current_count - last_count

        if weight_change > 0:
            weight_compare_label.setText(f"🟢 ↑{weight_change:.2f}%")
            weight_compare_label.setStyleSheet("color: #27ae60; font-size: 12px; font-weight: bold;")
        elif weight_change < 0:
            weight_compare_label.setText(f"🔴 ↓{abs(weight_change):.2f}%")
            weight_compare_label.setStyleSheet("color: #c0392b; font-size: 12px; font-weight: bold;")
        else:
            weight_compare_label.setText("⚪ 0.00%")
            weight_compare_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")

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
        for key, data in snapshot.items():
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
                weight_item = self.table.item(row, 7)
                if weight_item:
                    weight_item.setText("0.00%")
                    weight_item.setData(Qt.UserRole, 0)
                order_item = self.table.item(row, 9)
                if order_item:
                    order_item.setText("0单")
            self.update_total_orders_label()
            self.update_compare_columns()
            return
        
        spec_order_counts = {str(row[0]): row[1] for row in imported_data}
        total_orders = sum(spec_order_counts.values())
        
        for row in range(self.table.rowCount()):
            spec_code_item = self.table.item(row, 2)
            if not spec_code_item:
                continue
            spec_code = str(spec_code_item.text()).strip()
            is_locked_item = self.table.item(row, 7)
            is_locked = is_locked_item and "🔒" in is_locked_item.text() if is_locked_item else False
            
            if spec_code in spec_order_counts:
                count = spec_order_counts[spec_code]
                weight = (count / total_orders) * 100 if total_orders > 0 else 0
                weight_text = f"🔒 {weight:.2f}%" if is_locked else f"{weight:.2f}%"
                weight_item = QTableWidgetItem(weight_text)
                weight_item.setData(Qt.UserRole, weight)
                weight_item.setToolTip(f"订单数: {count}单")
                self.table.setItem(row, 7, weight_item)
                order_item = QTableWidgetItem(f"{count}单")
                order_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 9, order_item)
            else:
                weight_text = f"🔒 0.00%" if is_locked else "0.00%"
                weight_item = QTableWidgetItem(weight_text)
                weight_item.setData(Qt.UserRole, 0.0)
                self.table.setItem(row, 7, weight_item)
                order_item = QTableWidgetItem("0单")
                order_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 9, order_item)
        
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
        if last_snapshot:
            for key, data in last_snapshot.items():
                parts = key.split("_")
                if len(parts) >= 2:
                    prod_id_part = parts[0]
                    spec_code_part = "_".join(parts[1:])
                    if prod_id_part == self.product_code:
                        last_spec_counts[spec_code_part] = data.get("count", 0)

        current_spec_counts = {str(row[0]): row[1] for row in imported_data} if imported_data else {}
        current_total = sum(current_spec_counts.values())

        if not last_snapshot or not last_spec_counts:
            for row in range(self.table.rowCount()):
                weight_compare_widget = self.table.cellWidget(row, 8)
                order_compare_widget = self.table.cellWidget(row, 10)
                if weight_compare_widget:
                    label = weight_compare_widget.layout().itemAt(0).widget()
                    label.setText("无")
                    label.setStyleSheet("color: #95a5a6; font-size: 12px;")
                if order_compare_widget:
                    label = order_compare_widget.layout().itemAt(0).widget()
                    label.setText("无")
                    label.setStyleSheet("color: #95a5a6; font-size: 12px;")
            return

        for row in range(self.table.rowCount()):
            spec_code_item = self.table.item(row, 2)
            if not spec_code_item:
                continue
            spec_code = str(spec_code_item.text()).strip()
            current_count = current_spec_counts.get(spec_code, 0)
            last_count = last_spec_counts.get(spec_code, None)

            self._update_spec_compare_labels(row, current_count, last_count, current_total)

    def calculate_weighted_avg_price(self):
        """根据权重计算加权平均客单价"""
        total_weight = 0.0
        weighted_price = 0.0
        
        for r in range(self.table.rowCount()):
            price_item = self.table.item(r, 4)
            weight_item = self.table.item(r, 7)
            
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
        
        # 列索引7是权重列
        for r in range(rows):
            item = self.table.item(r, 7)
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
                item = self.table.item(r, 7)
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
                "SELECT spec_name, spec_code, sale_price FROM product_specs WHERE product_id=?", 
                (self.product_id,)
            )
            old_price_map = {r[1]: r[2] for r in old_rows} # {编码: 旧价格}
            old_name_map = {r[1]: r[0] for r in old_rows}  # {编码: 旧名称}
            old_codes_set = set(old_price_map.keys())       # 旧编码集合
            
            # 准备新数据
            new_specs = []
            price_changes = []      # 存储调价记录 [(编码, 旧价, 新价)]
            current_codes_set = set() # 存储当前表格中存在的编码
            
            # 2. 遍历当前表格收集新数据
            row_count = self.table.rowCount()
            
            for r in range(row_count):
                item_name = self.table.item(r, 1)
                item_code = self.table.item(r, 2)
                item_price = self.table.item(r, 4)
                item_weight = self.table.item(r, 7)  # 权重列（可能带锁图标）
                
                if not item_name or not item_code:
                    continue

                spec_name = item_name.text().strip()
                # 规格名称最多40字符
                if len(spec_name) > 40:
                    spec_name = spec_name[:40]
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
                new_specs.append((self.product_id, spec_name, spec_code, new_price, weight_percent, is_locked))
                
                # 检测价格变化
                if spec_code in old_price_map:
                    old_price = old_price_map[spec_code]
                    if abs(new_price - old_price) > 0.001:
                        price_changes.append((spec_code, old_price, new_price))
                elif new_price > 0:
                    # 新加的规格
                    price_changes.append((spec_code, 0.0, new_price))

            # 3. 检测删除操作
            deleted_codes = old_codes_set - current_codes_set
            deleted_logs = []
            for code in deleted_codes:
                name = old_name_map.get(code, "未知规格")
                deleted_logs.append(f"删除规格 [{name}]")

            # 4. 执行数据库事务 (先删后插)
            # 先保存优惠券和新客立减金额
            # 获取旧值用于判断是否变化
            old_discount_rows = self.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate FROM products WHERE id=?",
                (self.product_id,)
            )
            old_coupon = old_discount_rows[0][0] if old_discount_rows and old_discount_rows[0][0] else 0
            old_new_customer = old_discount_rows[0][1] if old_discount_rows and old_discount_rows[0][1] else 0
            old_roi = old_discount_rows[0][2] if old_discount_rows and old_discount_rows[0][2] else 0
            old_return_rate = old_discount_rows[0][3] if old_discount_rows and old_discount_rows[0][3] else 0
            
            # 记录是否有投产/优惠券变化
            param_changed = False
            param_change_details = []
            
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
                
                # 检查投产变化
                if current_roi != old_roi:
                    param_changed = True
                    param_change_details.append(f"投产: {old_roi}→{current_roi}")
                
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
                placeholders = ','.join(['(?, ?, ?, ?, ?, ?)'] * len(new_specs))
                flat_data = [item for spec in new_specs for item in spec]
                self.db.safe_execute(
                    f"INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent, is_locked) VALUES {placeholders}",
                    flat_data
                )
            
            # 5. 生成并写入日志 (如果有变化或删除)
            if price_changes or deleted_logs or param_changed:
                # 读取优惠券和新客立减金额
                discount_rows = self.db.safe_fetchall(
                    "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
                    (self.product_id,)
                )
                coupon_amount = discount_rows[0][0] if discount_rows and discount_rows[0][0] else 0
                new_customer_discount = discount_rows[0][1] if discount_rows and discount_rows[0][1] else 0
                total_discount = coupon_amount + new_customer_discount

                # 重新计算保存后的综合毛利（基于优惠后的最终价格）
                rows = self.db.safe_fetchall(
                    "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?", 
                    (self.product_id,)
                )
                total_weighted_margin = 0.0
                total_weight = 0.0
                
                for r in rows:
                    sc, sp, w = r[0], r[1], r[2]
                    if sp is None or w is None: continue
                    
                    cr = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (sc,))
                    c = cr[0][0] if cr else 0.0
                    
                    final_price = sp - total_discount
                    if final_price > 0:
                        m = (final_price - c) / final_price
                        total_weighted_margin += m * w
                        total_weight += w
                
                current_margin_pct = (total_weighted_margin / total_weight * 100) if total_weight > 0 else 0.0
                
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
                
                # 从历史日志中提取最近一次记录的综合毛利值
                last_recorded_margin = None
                if existing_logs:
                    for log_entry in reversed(existing_logs):
                        log_text = log_entry.get("text", "")
                        margin_match = re.search(r'综合毛利[为为]?\s*([\d.]+)%', log_text)
                        if margin_match:
                            last_recorded_margin = float(margin_match.group(1))
                            break
                
                # 判断综合毛利是否发生实质性变化（阈值0.1%）
                MARGIN_CHANGE_THRESHOLD = 0.1
                margin_changed = False
                if last_recorded_margin is None:
                    margin_changed = True
                else:
                    margin_changed = abs(current_margin_pct - last_recorded_margin) >= MARGIN_CHANGE_THRESHOLD
                
                # 构建日志文本
                time_str = now.strftime("%H:%M")
                
                log_parts = []
                if price_changes:
                    change_details = "; ".join([f"{code}: {old:.2f}→{new:.2f}" for code, old, new in price_changes])
                    log_parts.append(f"调整售价 [{change_details}]")
                if deleted_logs:
                    log_parts.extend(deleted_logs)
                if param_changed:
                    log_parts.append(f"[{'; '.join(param_change_details)}]")
                
                # 仅当综合毛利发生实质性变化时添加毛利后缀
                if margin_changed:
                    log_text = f"自动记录：{'; '.join(log_parts)}，新综合毛利为 {current_margin_pct:.1f}%"
                else:
                    log_text = f"自动记录：{'; '.join(log_parts)}"
                
                # 追加新日志
                existing_logs.append({"time": time_str, "text": log_text})
                
                # 写回数据库
                self.db.safe_execute(
                    "INSERT OR REPLACE INTO records (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
                    (self.product_id, year, month, day, json.dumps(existing_logs))
                )
                
                # 提示用户
                msg = "规格已保存。\n"
                if price_changes: msg += f"✅ 记录 {len(price_changes)} 条调价日志。\n"
                if deleted_logs: msg += f"🗑️ 记录 {len(deleted_logs)} 条删除日志。"
                if param_changed: msg += f"📊 记录参数调整。"
                self.main_app.show_toast(msg)
                
                # 刷新主界面
                self.main_app.load_data_safe()
            
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

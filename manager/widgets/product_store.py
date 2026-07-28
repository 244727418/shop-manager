# -*- coding: utf-8 -*-
"""
商品与店铺相关 UI 组件：ProductWidget、StoreWidget、RecordRow、InPlaceEditor
"""
import os
import json
import re
import html
import math
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QApplication, QScrollArea, QTextEdit,
    QTimeEdit, QDialog, QSizePolicy, QCheckBox, QDateEdit, QLayout,
    QMenu, QAction, QInputDialog, QLineEdit
)
from PyQt5.QtCore import (
    Qt, QEvent, QTime, QSize, QDate, QBuffer, QByteArray, QIODevice, QTimer, QPoint,
)
from PyQt5.QtGui import QImageReader, QPixmap, QIcon, QImage, QColor, qGray
try:
    from PyQt5 import sip
except ImportError:
    import sip
try:
    from manager.crash_report import append_event, append_exception
except ImportError:
    from crash_report import append_event, append_exception


def _icons_dir():
    """icons 在 shop_manager/icons，本模块在 shop_manager/widgets/"""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")


def _net_margin_background_color(net_margin_pct):
    if net_margin_pct is None:
        return QColor.fromHslF(0.0, 0.0, 0.82)
    margin = float(net_margin_pct)
    strength = 1.0 - math.exp(-abs(margin) / 15.0)
    target_hue = 0.0 if margin < 0 else 120.0
    target_saturation = 0.55 + 0.43 * strength
    target_lightness = 0.82 - 0.64 * strength
    if -2.0 <= margin <= 1.0:
        return QColor.fromHslF((55.0 + margin * 3.0) / 360.0, 0.78, 0.72)
    if margin < -2.0:
        ratio = min(1.0, (-margin - 2.0) / 4.0)
        start_hue = 49.0
    else:
        ratio = min(1.0, (margin - 1.0) / 4.0)
        start_hue = 58.0
    return QColor.fromHslF(
        (start_hue + (target_hue - start_hue) * ratio) / 360.0,
        0.78 + (target_saturation - 0.78) * ratio,
        0.72 + (target_lightness - 0.72) * ratio,
    )


def _bubble_metric_foreground(net_margin_pct, background):
    return "#fffdf5" if net_margin_pct is not None and qGray(background.rgb()) < 90 else "#171b18"


def _bubble_metric_typography(real_mode, visible_count):
    if real_mode and visible_count <= 2:
        return 16, 22
    if real_mode and visible_count <= 4:
        return 14, 18
    if real_mode and visible_count <= 7:
        return 12, 15
    return (11, 12) if real_mode else (13, 15)


def _expected_profit_for_100(is_natural_flow, margin_rate, return_rate, roi=0):
    net_ratio = float(margin_rate or 0) * max(0.0, 1 - float(return_rate or 0) / 100) - 0.006
    if is_natural_flow:
        return 100 * net_ratio
    return 100 * float(roi or 0) * net_ratio - 100 if float(roi or 0) > 0 else None


_PIXMAP_CACHE = {}


class _MetricState:
    __slots__ = ("_text", "_tooltip", "_visible")

    def __init__(self, text=""):
        self._text = text
        self._tooltip = ""
        self._visible = True

    def text(self):
        return self._text

    def setText(self, text):
        self._text = str(text)

    def toolTip(self):
        return self._tooltip

    def setToolTip(self, text):
        self._tooltip = str(text)

    def setVisible(self, visible):
        self._visible = bool(visible)

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False

    def isHidden(self):
        return not self._visible

    def _ignore(self, *_args, **_kwargs):
        pass

    setFixedHeight = setMaximumHeight = setMinimumHeight = _ignore
    setStyleSheet = setTextFormat = setWordWrap = _ignore


def _cached_pixmap(key, factory):
    pixmap = _PIXMAP_CACHE.get(key)
    if pixmap is not None:
        return pixmap
    pixmap = factory()
    if len(_PIXMAP_CACHE) > 512:
        _PIXMAP_CACHE.clear()
    _PIXMAP_CACHE[key] = pixmap
    return pixmap


def _enlarge_context_menu(menu):
    menu.setStyleSheet("""
        QMenu {
            font-size: 14px;
            padding: 6px;
        }
        QMenu::item {
            padding: 8px 28px 8px 16px;
            min-width: 150px;
        }
    """)


class ProductWidget(QWidget):
    """左侧冻结列中的商品展示控件"""
    BUBBLE_WIDTH = 340
    BUBBLE_HEIGHT = 104

    def __init__(self, prod_id, prod_code, prod_title, image_data, main_app, display_mode="table"):
        super().__init__()
        self.prod_id = prod_id
        self.prod_code = prod_code
        self.prod_title = prod_title
        self.main_app = main_app
        self.db = main_app.db
        self.display_mode = display_mode
        self._bubble_background = "#545e47"
        self._bubble_foreground = "#171b18"
        self._bubble_highlight_color = "#00e5ff"
        self._bubble_highlight_foreground = "#111111"
        self.setObjectName("ProductWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._search_highlight_active = False
        self._suppress_next_code_click = False
        self._code_click_timer = QTimer(self)
        self._code_click_timer.setSingleShot(True)
        self._code_click_timer.timeout.connect(self.copy_product_id)

        main_layout = QVBoxLayout(self) if display_mode == "bubble" else QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) if display_mode == "bubble" else main_layout.setContentsMargins(4, 1, 4, 1)
        main_layout.setSpacing(4 if display_mode == "bubble" else 6)

        image_size = 104 if display_mode == "bubble" else 72
        img_container = QWidget()
        img_container.setFixedSize(image_size, image_size)
        img_container.installEventFilter(self)
        img_layout = QVBoxLayout(img_container)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(2)

        self.img_label = QLabel()
        self.img_label.setFixedSize(image_size, image_size)
        self.img_label.setStyleSheet("border: none; padding: 1px; margin: 0px;")
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMouseTracking(True)
        self.img_label.setFocusPolicy(Qt.StrongFocus)
        self.img_label.setToolTip("Ctrl+V 粘贴换图，双击查看大图")
        self.img_label.installEventFilter(self)
        self.set_image_from_data(image_data)

        self.category_label = QLabel()
        self.category_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.category_label.setWordWrap(True)
        self.category_label.setMinimumHeight(18)
        self.category_label.setMaximumHeight(48)
        self.category_label.setFixedWidth(200)
        self.category_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.category_label.installEventFilter(self)
        self.update_product_category_display()

        img_layout.addWidget(self.img_label)

        content_layout = None
        if display_mode != "bubble":
            content_layout = QHBoxLayout()
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(8)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        top_layout = None
        if display_mode != "bubble":
            top_layout = QHBoxLayout()
            top_layout.setSpacing(4)

        self.code_label = QLabel(str(prod_code))
        self.code_label.setStyleSheet("font-weight: bold; color: #4a90e2; font-size: 11px;")
        self.code_label.setCursor(Qt.PointingHandCursor)
        self.code_label.installEventFilter(self)
        self.code_label.setToolTip("单击复制 ID，双击复制同款")
        self.code_label.setMinimumWidth(100)
        self.code_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.real_date_label = QLabel("")
        self.real_date_label.setStyleSheet("font-weight: bold; color: #8e44ad; font-size: 11px;")
        self.real_date_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.real_date_label.hide()

        tag_layout = QHBoxLayout()
        tag_layout.setSpacing(2)

        self.coupon_badge = QLabel()
        self.coupon_badge.setFixedSize(16, 16)
        self.coupon_badge.hide()
        self.coupon_amount_label = QLabel()
        self.coupon_amount_label.setStyleSheet("color: #555; background: transparent; font-size: 10px; font-weight: bold;")
        self.coupon_amount_label.setMaximumWidth(34)
        self.coupon_amount_label.hide()

        self.new_customer_badge = QLabel()
        self.new_customer_badge.setFixedSize(16, 16)
        self.new_customer_badge.hide()
        self.new_customer_amount_label = QLabel()
        self.new_customer_amount_label.setStyleSheet("color: #555; background: transparent; font-size: 10px; font-weight: bold;")
        self.new_customer_amount_label.setMaximumWidth(34)
        self.new_customer_amount_label.hide()

        self.limited_time_badge = QLabel()
        self.limited_time_badge.setFixedSize(16, 16)
        self.limited_time_badge.hide()

        self.marketing_badge = QLabel()
        self.marketing_badge.setFixedSize(16, 16)
        self.marketing_badge.installEventFilter(self)
        self.marketing_badge.hide()
        for badge in (self.coupon_badge, self.new_customer_badge, self.limited_time_badge, self.marketing_badge):
            badge.setStyleSheet("background: transparent; border: none; padding: 0px;")

        self.natural_flow_badge = QLabel("无推广")
        self.natural_flow_badge.setStyleSheet("color: white; background-color: #16a085; border-radius: 3px; padding: 1px 4px; font-size: 10px; font-weight: bold;")
        self.natural_flow_badge.hide()

        self.sitewide_badge = QLabel("全站")
        self.sitewide_badge.setStyleSheet("color: white; background-color: #8e44ad; border-radius: 3px; padding: 1px 4px; font-size: 10px; font-weight: bold;")
        self.sitewide_badge.hide()

        self.reminder_badge = QLabel("任务")
        self.reminder_badge.setFixedSize(26, 26)
        self.reminder_badge.setAlignment(Qt.AlignCenter)
        self.reminder_badge.setStyleSheet(
            "color:#111; background:#fde047; border:1px solid #111; "
            "border-radius:13px; font-size:10px; font-weight:bold;"
        )
        self.reminder_badge.setToolTip("该链接有待完成任务，悬停查看内容和时间")
        self.reminder_badge.installEventFilter(self)
        self.reminder_badge.hide()

        self.garbage_badge = QLabel()
        self.garbage_badge.setFixedSize(26, 26)
        self.garbage_badge.setStyleSheet("background:transparent; border:none;")
        self.garbage_badge.setToolTip("该链接最近一次推广数据有数据但无净成交")
        self.garbage_badge_circle = QLabel("垃圾", self.garbage_badge)
        self.garbage_badge_circle.setFixedSize(22, 22)
        self.garbage_badge_circle.move(2, 4)
        self.garbage_badge_circle.setAlignment(Qt.AlignCenter)
        self.garbage_badge_circle.setStyleSheet(
            "color:white; background:#dc2626; border:1px solid #111; border-radius:11px; "
            "font-size:9px; font-weight:bold;"
        )
        self.garbage_streak_badge = QLabel(self.garbage_badge)
        self.garbage_streak_badge.setFixedSize(15, 15)
        self.garbage_streak_badge.move(5, 0)
        self.garbage_streak_badge.setAlignment(Qt.AlignCenter)
        self.garbage_streak_badge.setStyleSheet(
            "color:white; background:black; border:none; border-radius:7px; "
            "font-size:9px; font-weight:bold; padding:0px;"
        )
        self.garbage_streak_badge.raise_()
        self.garbage_streak_badge.hide()
        self.garbage_badge.hide()

        self.waste_badge = QLabel("废物")
        self.waste_badge.setFixedSize(26, 26)
        self.waste_badge.setAlignment(Qt.AlignCenter)
        self.waste_badge.setStyleSheet("color:white; background:#7c2d12; border:1px solid #111; border-radius:13px; font-size:10px; font-weight:bold;")
        self.waste_badge.setToolTip("最近导入的一周订单表无订单；创建未满 7 天的链接不标记")
        self.waste_badge.hide()

        tag_layout.addWidget(self.coupon_badge)
        tag_layout.addWidget(self.coupon_amount_label)
        tag_layout.addWidget(self.new_customer_badge)
        tag_layout.addWidget(self.new_customer_amount_label)
        tag_layout.addWidget(self.limited_time_badge)
        tag_layout.addWidget(self.marketing_badge)
        tag_layout.addWidget(self.natural_flow_badge)
        tag_layout.addWidget(self.sitewide_badge)
        tag_layout.addWidget(self.reminder_badge)
        tag_layout.addWidget(self.garbage_badge)
        tag_layout.addWidget(self.waste_badge)
        tag_layout.addStretch()

        if display_mode != "bubble":
            top_layout.addWidget(self.code_label)
            top_layout.addWidget(self.real_date_label)
            top_layout.addLayout(tag_layout, 1)

        if display_mode == "bubble":
            self.code_label.setFixedWidth(92)
            self.code_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.code_label.setStyleSheet(
                "font-weight: bold; color: #171b18; background: transparent; border: none; font-size: 11px;"
            )
            self.real_date_label.setStyleSheet(
                "font-weight: bold; color: #171b18; background: transparent; border: none; font-size: 11px;"
            )
        else:
            self.title_label = QLabel(prod_title)
            self.title_label.setWordWrap(True)
            self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.title_label.setStyleSheet(
                "font-size: 11px; color: #333;"
            )
            self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.title_label.setMinimumHeight(30)
            self.title_label.setMaximumHeight(34)
            self.title_label.setToolTip(prod_title)
            self.title_label.installEventFilter(self)

        self.original_name = prod_code
        self.original_title = prod_title

        if display_mode != "bubble":
            self.memo_label = QLabel()
            self.memo_label.setWordWrap(False)
            self.memo_label.setMaximumHeight(18)
            self.memo_label.setCursor(Qt.PointingHandCursor)
            self.memo_label.installEventFilter(self)
            self.memo_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            self.update_product_memo_display()

        if display_mode == "bubble":
            self.margin_label = _MetricState("毛利率: -")
            self.link_order_label = _MetricState("单量:0单")
            self.net_profit_label = _MetricState("净利率: -")
            self.roi_label = _MetricState()
        else:
            margin_row1_layout = QHBoxLayout()
            margin_row1_layout.setSpacing(6)
            margin_row1_layout.setContentsMargins(0, 0, 0, 0)

            self.margin_label = QLabel("毛利率: -")
            self.margin_label.setStyleSheet("color: #d9534f; font-weight: bold; font-size: 12px;")
            self.margin_label.setTextFormat(Qt.RichText)
            self.margin_label.setWordWrap(True)
            self.margin_label.installEventFilter(self)

            self.link_order_label = QLabel("单量:0单")
            self.link_order_label.setStyleSheet("color: #8b4513; font-size: 12px; font-weight: bold;")
            self.link_order_label.installEventFilter(self)

            margin_row1_layout.addWidget(self.margin_label)
            margin_row1_layout.addWidget(self.link_order_label)
            margin_row1_layout.addStretch()

            self.net_profit_label = QLabel("净利率: -")
            self.net_profit_label.setStyleSheet("color: #28a745; font-weight: bold; font-size: 13px;")
            self.net_profit_label.setTextFormat(Qt.RichText)
            self.net_profit_label.setWordWrap(True)
            self.net_profit_label.installEventFilter(self)

            self.roi_label = QLabel("")
            self.roi_label.setStyleSheet("color: blue; font-size: 13px;")
            self.roi_label.setTextFormat(Qt.RichText)
            self.roi_label.setWordWrap(True)
            self.roi_label.installEventFilter(self)

            margin_layout = QVBoxLayout()
            margin_layout.setSpacing(0)
            margin_layout.setContentsMargins(0, 0, 0, 0)
            margin_layout.addLayout(margin_row1_layout)
            margin_layout.addWidget(self.net_profit_label)
            margin_layout.addWidget(self.roi_label)
            margin_layout.addStretch()

            self.metrics_panel = QWidget()
            self.metrics_panel.setObjectName("ProductMetricsPanel")
            self.metrics_panel.setMinimumWidth(250)
            self.metrics_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.metrics_panel.setLayout(margin_layout)

        if display_mode == "bubble":
            self.bubble_chips_widget = QWidget()
            self.bubble_chips_widget.setAttribute(Qt.WA_StyledBackground, True)
            self.bubble_chips_widget.setStyleSheet("background: transparent; border: none;")
            chips_layout = QGridLayout(self.bubble_chips_widget)
            chips_layout.setContentsMargins(0, 0, 0, 0)
            chips_layout.setHorizontalSpacing(2)
            chips_layout.setVerticalSpacing(1)
            self.bubble_chip_labels = {}
            for key, row, column, column_span in (
                ("promotion", 0, 0, 2), ("status", 0, 2, 1),
                ("order", 1, 0, 1), ("multiple", 1, 1, 2),
            ):
                chip = QLabel()
                chip.setAlignment(Qt.AlignCenter)
                chip.setFixedHeight(18)
                chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                chip.installEventFilter(self)
                chips_layout.addWidget(chip, row, column, 1, column_span)
                self.bubble_chip_labels[key] = chip
            chips_layout.setColumnStretch(0, 1)
            chips_layout.setColumnStretch(1, 1)
            self.bubble_chips_widget.setFixedHeight(37)
            self.bubble_chips_widget.hide()
            self.bubble_metrics_widget = QWidget()
            self.bubble_metrics_widget.setAttribute(Qt.WA_StyledBackground, True)
            self.bubble_metrics_widget.setStyleSheet("background: transparent; border: none;")
            self.bubble_metrics_layout = QGridLayout(self.bubble_metrics_widget)
            self.bubble_metrics_layout.setContentsMargins(0, 0, 0, 0)
            self.bubble_metrics_layout.setHorizontalSpacing(1)
            self.bubble_metrics_layout.setVerticalSpacing(1)
            self.bubble_metrics_layout.setAlignment(Qt.AlignTop)
            self.bubble_metric_chips = []
            self.bubble_metrics_label = QLabel()
            self.bubble_metrics_label.setTextFormat(Qt.RichText)
            self.bubble_metrics_label.hide()

        if display_mode == "bubble":
            info_layout.setAlignment(Qt.AlignTop)
            info_layout.setSpacing(0)
            title_layout = QHBoxLayout()
            title_layout.setContentsMargins(0, 0, 0, 0)
            title_layout.setSpacing(3)
            header_left = QWidget()
            header_left.setFixedHeight(24)
            header_left.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            header_left.setAttribute(Qt.WA_StyledBackground, True)
            header_left.setStyleSheet("background: transparent; border: none;")
            header_left_layout = QHBoxLayout(header_left)
            header_left_layout.setContentsMargins(0, 0, 0, 0)
            header_left_layout.setSpacing(2)
            header_left_layout.addWidget(self.code_label)
            header_left_layout.addWidget(self.real_date_label)
            header_left_layout.addLayout(tag_layout, 1)
            title_layout.addWidget(header_left, 1)
            title_layout.addWidget(self.category_label, 0, Qt.AlignRight | Qt.AlignVCenter)
            info_layout.addLayout(title_layout)
            info_layout.addWidget(self.bubble_chips_widget)
            info_layout.addWidget(self.bubble_metrics_widget)
            body_layout = QHBoxLayout()
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(4)
            body_layout.addWidget(img_container, 0, Qt.AlignCenter)
            body_layout.addLayout(info_layout, 1)
            main_layout.addLayout(body_layout)
            self.setFixedWidth(self.BUBBLE_WIDTH)
            self.setFixedHeight(self.BUBBLE_HEIGHT)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
            self._update_bubble_width()
            self._apply_product_style()
        else:
            info_layout.addLayout(top_layout)
            info_layout.addWidget(self.title_label)
            info_layout.addWidget(self.category_label)
            info_layout.addWidget(self.memo_label)
            info_layout.addStretch()
            content_layout.addLayout(info_layout, 1)
            content_layout.addWidget(self.metrics_panel, 2)
            main_layout.addWidget(img_container)
            main_layout.addLayout(content_layout, 1)

        self.violation_overlay = QWidget(self)
        self.violation_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.violation_overlay.setGeometry(self.rect())
        self.violation_overlay.setStyleSheet("background-color: rgba(255, 0, 0, 128);")
        violation_layout = QVBoxLayout(self.violation_overlay)
        violation_layout.setContentsMargins(0, 0, 0, 0)
        violation_label = QLabel("违规")
        violation_label.setFixedSize(76, 76)
        violation_label.setAlignment(Qt.AlignCenter)
        violation_label.setStyleSheet(
            "background:#e53935; color:#111; border:3px solid #8b0000; "
            "border-radius:38px; font-size:24px; font-weight:bold;"
        )
        violation_layout.addWidget(violation_label, 0, Qt.AlignCenter)
        self.violation_overlay.hide()

        self.update_margin_display(fresh=False)
        self.update_promo_badges()
        self.update_task_badge()

    def set_search_highlight(self, active):
        self._search_highlight_active = bool(active)
        if self.display_mode == "bubble":
            foreground = self._bubble_highlight_foreground if active else self._bubble_foreground
            self._apply_bubble_text_color(foreground)
            self._sync_bubble_metrics()
        self._apply_product_style()

    def _apply_product_style(self):
        if self._search_highlight_active:
            self.setStyleSheet(
                f"#ProductWidget {{ background-color: {self._bubble_highlight_color}; "
                f"border: 3px solid {self._bubble_highlight_foreground}; border-radius: 8px; }}"
            )
        elif self.display_mode == "bubble":
            self.setStyleSheet(
                f"#ProductWidget {{ background-color: {self._bubble_background}; "
                "border: none; border-radius: 8px; }"
            )
        else:
            self.setStyleSheet("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "violation_overlay"):
            self.violation_overlay.setGeometry(self.rect())
            if self.violation_overlay.isVisible():
                self.violation_overlay.raise_()

    def refresh_violation_state(self, fresh=False):
        card_data = {} if fresh else self.main_app.get_product_card_data(self.prod_id)
        if "is_violation" in card_data:
            self.is_violation = bool(card_data["is_violation"])
        else:
            rows = self.db.safe_fetchall(
                "SELECT COALESCE(is_violation, 0) FROM products WHERE id=?", (self.prod_id,)
            )
            self.is_violation = bool(rows and rows[0][0])
        if hasattr(self, "violation_overlay"):
            self.violation_overlay.setVisible(self.display_mode == "bubble" and self.is_violation)
            if self.violation_overlay.isVisible():
                self.violation_overlay.raise_()

    def set_violation_state(self, enabled):
        store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.prod_id,))
        store_id = store_rows[0][0] if store_rows else None
        with self.db.conn:
            self.db.conn.execute(
                "UPDATE products SET is_violation=? WHERE id=?", (1 if enabled else 0, self.prod_id)
            )
            if enabled:
                self.db.conn.execute(
                    """DELETE FROM daily_tasks WHERE product_id=? AND is_completed=0
                       AND (task_content LIKE '【垃圾链接】%' OR task_content LIKE '【废物链接】%')""",
                    (self.prod_id,),
                )
        card_cache = getattr(self.main_app, "_product_card_data_cache", None)
        if isinstance(card_cache, dict) and self.prod_id in card_cache:
            card_cache[self.prod_id]["is_violation"] = 1 if enabled else 0
        task_states = getattr(self.main_app, "_product_task_states", None)
        if isinstance(task_states, dict):
            task_states.pop(self.prod_id, None)
        self.refresh_violation_state()
        if hasattr(self.main_app, "refresh_store_cards"):
            self.main_app.refresh_store_cards(store_id)
        dialog = getattr(self.main_app, "store_margin_dialogs", {}).get(store_id)
        if dialog is not None and hasattr(dialog, "load_products"):
            dialog.load_products()
        if hasattr(self.main_app, "update_daily_task_button_badge"):
            self.main_app.update_daily_task_button_badge()
        if hasattr(self.main_app, "show_toast"):
            self.main_app.show_toast("已标记违规" if enabled else "已解除违规")

    def _update_bubble_width(self):
        if self.display_mode != "bubble":
            return
        self.setFixedWidth(self.BUBBLE_WIDTH)

    def _update_bubble_net_margin_color(self, net_margin_pct):
        if self.display_mode != "bubble":
            return
        color = _net_margin_background_color(net_margin_pct)
        self._bubble_background = color.name()
        self._bubble_foreground = _bubble_metric_foreground(net_margin_pct, color)
        highlight = QColor.fromHslF((color.hslHueF() + 0.5) % 1.0, 1.0, 0.62)
        self._bubble_highlight_color = highlight.name()
        self._bubble_highlight_foreground = "#171b18"
        foreground = self._bubble_highlight_foreground if self._search_highlight_active else self._bubble_foreground
        self._apply_bubble_text_color(foreground)
        self._apply_product_style()

    def _apply_bubble_text_color(self, foreground):
        self.code_label.setStyleSheet(
            f"font-weight: bold; color: {foreground}; background: transparent; font-size: 11px;"
        )
        self.real_date_label.setStyleSheet(
            f"font-weight: bold; color: {foreground}; background: transparent; font-size: 11px;"
        )
        self.category_label.setStyleSheet(
            f"color: {foreground}; background: transparent; border: none; "
            f"padding: 0px 3px 0px 6px; font-size: {getattr(self, '_category_font_size', 12)}px; "
            "font-weight: bold;"
        )
        for amount_label in (self.coupon_amount_label, self.new_customer_amount_label):
            amount_label.setStyleSheet(
                f"color: {foreground}; background: transparent; "
                "font-size: 10px; font-weight: bold; padding: 0px;"
            )

    def update_task_badge(self):
        try:
            states = getattr(getattr(self, "main_app", None), "_product_task_states", None)
            state = states.get(self.prod_id) if isinstance(states, dict) else None
            if state is None:
                rows = self.db.safe_fetchall(
                    """SELECT task_content FROM daily_tasks
                       WHERE product_id=? AND is_completed=0""",
                    (self.prod_id,),
                )
                task_contents = [str(row[0] or "") for row in rows]
                reminder_rows = self.db.safe_fetchall(
                    "SELECT 1 FROM task_reminders WHERE product_id=? AND is_reminded=0 LIMIT 1",
                    (self.prod_id,),
                )
                state = (
                    any(text.startswith("【垃圾链接】") for text in task_contents),
                    any(text.startswith("【废物链接】") for text in task_contents),
                    bool(reminder_rows) or any(
                        not text.startswith(("【垃圾链接】", "【废物链接】")) for text in task_contents
                    ),
                    next((text for text in task_contents if text.startswith("【垃圾链接】")), ""),
                )
                if isinstance(states, dict):
                    states[self.prod_id] = state
            garbage, waste, reminder = state[:3]
            match = re.search(r"连续(\d+)次", state[3] if len(state) > 3 else "")
            streak = int(match.group(1)) if match else 1
            visible = self.display_mode == "bubble"
            self.reminder_badge.setVisible(visible and reminder)
            self.garbage_badge.setVisible(visible and garbage)
            if hasattr(self, "garbage_streak_badge"):
                self.garbage_streak_badge.setText(str(streak))
                self.garbage_streak_badge.setVisible(visible and garbage and streak >= 2)
                self.garbage_streak_badge.raise_()
            self.waste_badge.setVisible(visible and waste)
        except Exception as e:
            print(f"更新链接任务标签失败: {e}")

    def update_garbage_badge(self):
        self.update_task_badge()

    def recommended_row_height(self, base_height=140):
        if (
            hasattr(self.main_app, "is_real_promotion_data_mode")
            and self.main_app.is_real_promotion_data_mode()
        ):
            return max(base_height, 140)
        extra_lines = getattr(self, "_memo_extra_lines", 0)
        if extra_lines <= 0:
            return base_height
        return base_height + min(32, extra_lines * 12)

    def update_product_category_display(self):
        try:
            card_data = self.main_app.get_product_card_data(self.prod_id)
            category = card_data.get("product_category_label") or ""
            link_type = card_data.get("link_type") or ""
        except Exception as e:
            print(f"读取链接类型信息失败: {e}")
            category = ""
            link_type = ""

        category = str(category or "").strip()
        link_type = str(link_type or "").strip()
        category_text = category if category else "无"
        link_type_text = link_type if link_type else "无"
        if self.display_mode == "bubble":
            self.category_label.setWordWrap(False)
            self.category_label.setFixedHeight(18)
            self.category_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        else:
            self.category_label.setText(f"商品类型：{category_text}\n链接类型：{link_type_text}")
        tooltip_parts = [
            f"商品类型：{category or '无'}",
            f"链接类型：{link_type or '无'}",
            "双击打开原有编辑入口",
        ]
        self.category_label.setToolTip("\n".join(tooltip_parts))
        if category or link_type:
            self.category_label.setStyleSheet(
                "color: #245269; background-color: #e8f4fb; border: 1px solid #b8dff2; "
                "border-radius: 4px; padding: 1px 4px; font-size: 12px; font-weight: bold;"
            )
        else:
            self.category_label.setStyleSheet(
                "color: #777; background-color: #f5f5f5; border: 1px dashed #d0d0d0; "
                "border-radius: 4px; padding: 1px 4px; font-size: 12px;"
            )
        if self.display_mode == "bubble":
            max_label_width = 132
            for font_size in range(12, 7, -1):
                self.category_label.setStyleSheet(
                    "color: #fffdf5; background: transparent; border: none; "
                    f"padding: 0px 3px 0px 6px; font-size: {font_size}px; font-weight: bold;"
                )
                self.category_label.ensurePolished()
                metrics = self.category_label.fontMetrics()
                natural_width = metrics.horizontalAdvance(link_type_text) + 12
                if natural_width <= max_label_width or font_size == 8:
                    break
            self._category_font_size = font_size
            label_width = min(max_label_width, max(22, natural_width))
            self.category_label.setText(link_type_text)
            self.category_label.setFixedWidth(label_width)
        if self.display_mode == "bubble" and hasattr(self, "memo_label"):
            self._update_bubble_width()

    def update_product_memo_display(self):
        if not hasattr(self, "memo_label"):
            return
        try:
            memo = self.main_app.get_product_card_data(self.prod_id).get("product_memo") or ""
        except Exception as e:
            print(f"读取链接备注失败: {e}")
            memo = ""

        if memo:
            raw_memo = str(memo)
            compact = " ".join(raw_memo.split())
            explicit_lines = len([line for line in raw_memo.splitlines() if line.strip()])
            estimated_lines = max(explicit_lines, (len(compact) + 55) // 56)
            self._memo_extra_lines = max(0, estimated_lines - 2)
            if self._memo_extra_lines:
                self.memo_label.setMinimumHeight(18)
                self.memo_label.setMaximumHeight(18)
                self._memo_display_lines = 1
                limit = 58
            else:
                self.memo_label.setMinimumHeight(18)
                self.memo_label.setMaximumHeight(18)
                self._memo_display_lines = 1
                limit = 58
            display_text = compact[:limit] + "..." if len(compact) > limit else compact
            self.memo_label.setText(f"📝 {display_text}")
            self.memo_label.setToolTip(str(memo))
            self.memo_label.setStyleSheet(
                "color: #7f4f24; background-color: #fff6df; border: 1px solid #f1d29b; "
                "border-radius: 3px; padding: 1px 3px; font-size: 11px;"
            )
        else:
            self._memo_extra_lines = 0
            self._memo_display_lines = 1
            self.memo_label.setMinimumHeight(18)
            self.memo_label.setMaximumHeight(18)
            self.memo_label.setText("📝 点击添加备注")
            self.memo_label.setToolTip("双击添加链接备注")
            self.memo_label.setStyleSheet(
                "color: #999; background-color: #f7f7f7; border: 1px dashed #d0d0d0; "
                "border-radius: 3px; padding: 1px 3px; font-size: 11px; font-style: italic;"
            )
        if self.display_mode == "bubble":
            self._update_bubble_width()

    def edit_product_memo(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("链接备注")
        dialog.resize(500, 320)
        layout = QVBoxLayout(dialog)

        hint = QLabel("备注会长期保留，并在详细导出中显示。")
        hint.setStyleSheet("color: #666; font-size: 12px; padding: 4px;")
        layout.addWidget(hint)

        rows = self.db.safe_fetchall("SELECT product_memo FROM products WHERE id=?", (self.prod_id,))
        current_memo = rows[0][0] if rows and rows[0][0] else ""
        text_edit = QTextEdit()
        text_edit.setPlainText(current_memo)
        text_edit.setPlaceholderText("输入链接备注...")
        text_edit.setMaximumHeight(190)
        layout.addWidget(text_edit)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("QPushButton { background-color: #27ae60; color: white; padding: 8px 20px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #219a52; }")
        btn_cancel = QPushButton("取消")
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        def save_memo():
            memo = text_edit.toPlainText().strip()
            self.db.safe_execute("UPDATE products SET product_memo=? WHERE id=?", (memo, self.prod_id))
            self.update_product_memo_display()
            if hasattr(self.main_app, "update_product_row_height"):
                self.main_app.update_product_row_height(self.prod_id)
            self.main_app.show_toast("链接备注已更新")
            dialog.accept()

        btn_save.clicked.connect(save_memo)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec_()

    def update_promo_badges(self):
        try:
            card_data = self.main_app.get_product_card_data(self.prod_id)
            if not card_data:
                self.coupon_badge.hide()
                self.coupon_amount_label.hide()
                self.new_customer_badge.hide()
                self.new_customer_amount_label.hide()
                self.limited_time_badge.hide()
                self.marketing_badge.hide()
                self.natural_flow_badge.hide()
                self.sitewide_badge.hide()
                return
            coupon = card_data.get("coupon_amount") or 0
            new_customer = card_data.get("new_customer_discount") or 0
            is_limited_time = card_data.get("is_limited_time") or 0
            is_marketing = card_data.get("is_marketing") or 0
            marketing_activity = str(card_data.get("marketing_activity") or "").strip()
            is_natural_flow = card_data.get("is_natural_flow") or 0
            is_sitewide_managed = card_data.get("is_sitewide_managed") or 0
            icons_dir = _icons_dir()
            coupon_icon_path = os.path.join(icons_dir, "coupon.svg")
            new_customer_icon_path = os.path.join(icons_dir, "new_customer.svg")
            limited_time_icon_path = os.path.join(icons_dir, "limited-time.svg")
            marketing_icon_path = os.path.join(icons_dir, "marketing.svg")
            promo_icon_size = 17
            if coupon and coupon > 0:
                pixmap = _cached_pixmap(("icon", coupon_icon_path, promo_icon_size), lambda: QPixmap(coupon_icon_path).scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if not pixmap.isNull():
                    self.coupon_badge.setPixmap(pixmap)
                else:
                    self.coupon_badge.setText("券")
                self.coupon_badge.show()
                self.coupon_amount_label.setText(f"减{float(coupon):g}")
                self.coupon_amount_label.show()
            else:
                self.coupon_badge.hide()
                self.coupon_amount_label.hide()
            if new_customer and new_customer > 0:
                pixmap = _cached_pixmap(("icon", new_customer_icon_path, promo_icon_size), lambda: QPixmap(new_customer_icon_path).scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if not pixmap.isNull():
                    self.new_customer_badge.setPixmap(pixmap)
                else:
                    self.new_customer_badge.setText("新")
                self.new_customer_badge.show()
                self.new_customer_amount_label.setText(f"减{float(new_customer):g}")
                self.new_customer_amount_label.show()
            else:
                self.new_customer_badge.hide()
                self.new_customer_amount_label.hide()
            if is_limited_time:
                pixmap = _cached_pixmap(("icon", limited_time_icon_path, promo_icon_size), lambda: QPixmap(limited_time_icon_path).scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if not pixmap.isNull():
                    self.limited_time_badge.setPixmap(pixmap)
                else:
                    self.limited_time_badge.setText("⏰")
                self.limited_time_badge.show()
            else:
                self.limited_time_badge.hide()
            if is_marketing:
                pixmap = _cached_pixmap(("icon", marketing_icon_path, promo_icon_size), lambda: QPixmap(marketing_icon_path).scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if not pixmap.isNull():
                    self.marketing_badge.setPixmap(pixmap)
                else:
                    self.marketing_badge.setText("📢")
                self.marketing_badge.setToolTip(marketing_activity or "营销活动")
                self.marketing_badge.show()
            else:
                self.marketing_badge.hide()
            self.natural_flow_badge.hide()
            self.sitewide_badge.setVisible(
                self.display_mode != "bubble"
                and bool(is_sitewide_managed)
                and not bool(is_natural_flow)
            )
        except Exception as e:
            print(f"更新促销图标失败：{e}")

    def update_margin_display(self, fresh=True):
        self._update_margin_display(fresh=fresh)
        self._sync_bubble_metrics()
        self.refresh_violation_state()

    def _set_bubble_chip(self, key, text, background, border, tooltip=""):
        chip = getattr(self, "bubble_chip_labels", {}).get(key)
        if chip is None:
            return
        chip.setText(text)
        chip.setToolTip(tooltip or text)
        chip.setStyleSheet(
            f"color:#111; background:{background}; border:1px solid {border}; "
            "border-radius:6px; padding:1px; font-weight:bold;"
        )
        chip.setVisible(bool(text))

    def _sync_bubble_metrics(self):
        if self.display_mode != "bubble":
            return
        real_mode = (
            hasattr(self.main_app, "is_real_promotion_data_mode")
            and self.main_app.is_real_promotion_data_mode()
        )
        hidden_metrics = (
            self.main_app.get_real_promotion_hidden_metrics()
            if real_mode and hasattr(self.main_app, "get_real_promotion_hidden_metrics")
            else set()
        )
        visible_count = getattr(self, "_real_visible_metric_count", 99)
        font_size, line_height = _bubble_metric_typography(real_mode, visible_count)
        self.bubble_metrics_label.setStyleSheet(
            f"font-size: {font_size}px; background: transparent; padding: 0px; margin: 0px;"
        )
        self.bubble_metrics_label.setContentsMargins(0, 0, 0, 0)
        self.bubble_metrics_label.setMargin(0)
        foreground = (
            self._bubble_highlight_foreground
            if self._search_highlight_active
            else self._bubble_foreground
        )
        profit_status = None
        card_data = self.main_app.get_product_card_data(self.prod_id) or {}
        metric_prefixes = (
            "全站投产倍数:", "点击转化率:", "投产倍数:", "出价倍数:", "净投产比:",
            "保本出价:", "曝光占比:", "每笔成交:", "每笔花费:", "净成交:",
            "交易额:", "毛利率:", "净利润:", "净利率:", "客单价:", "点击率:",
            "毛利润:", "花费:", "单量:", "全站:", "投产:", "出价:",
        )
        split_pattern = r"(?<!\S)(?=" + "|".join(re.escape(prefix) for prefix in metric_prefixes) + r")"

        def metric_parts(label):
            nonlocal profit_status
            parts = []
            text = str(label.text() or "").strip()
            if label.isHidden() or not text:
                return parts
            plain_text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)))
            for line in plain_text.splitlines():
                for plain in re.split(split_pattern, line.strip()):
                    plain = plain.strip()
                    if not plain:
                        continue
                    match = re.search(r"\s*(微盈利|一般亏|微亏|巨亏|盈利|保本|亏损)$", plain)
                    if label is self.net_profit_label and match:
                        profit_status = match.group(1)
                        plain = plain[:match.start()].rstrip()
                    if plain:
                        parts.append(plain)
            return parts

        def metric_tooltip(plain):
            name = plain.split(":", 1)[0]
            descriptions = {
                "单量": "单量：当前月份导入订单中识别到的该链接订单数。",
                "净成交": "净成交：推广数据中扣除退款等影响后的成交单量。",
                "毛利率": "毛利率：商品毛利润占成交金额的比例。",
                "毛利润": "毛利润：成交金额扣除商品成本和优惠后的利润。",
                "净利润": "净利润：扣除商品成本、优惠、退货、技术服务费及推广费用后的利润。",
                "净利率": "净利率：净利润占成交金额的比例。",
                "客单价": "客单价：该链接平均每单的成交金额。",
                "花费": "花费：当前推广数据产生的推广费用。",
                "交易额": "交易额：当前推广数据产生的成交金额。",
                "净投产比": "净投产比：净成交金额除以推广花费。",
                "投产": "投产：每花费 1 元推广费预计带来的成交金额。",
                "全站": "全站投产：全站推广每花费 1 元预计带来的成交金额。",
                "投产倍数": "投产倍数：当前投产除以保本投产；大于 1 通常表示高于保本线。",
                "全站投产倍数": "全站投产倍数：当前全站投产除以保本投产。",
                "出价": "出价：当前设置的每笔成交推广出价。",
                "保本出价": "保本出价：预计单笔利润刚好为 0 时可承受的最高成交出价。",
                "出价倍数": "出价倍数：当前成交出价除以保本出价；大于 1 通常表示高于保本线。",
                "曝光占比": "曝光占比：推广曝光量占商品总曝光量的比例。",
                "每笔成交": "每笔成交：平均每笔净成交对应的成交金额。",
                "每笔花费": "每笔花费：平均获得一笔净成交所消耗的推广费用。",
                "点击率": "点击率：点击量占曝光量的比例。",
                "点击转化率": "点击转化率：净成交单量占点击量的比例。",
            }
            if name == "预计盈亏":
                if card_data.get("is_natural_flow"):
                    return "预计盈亏：按自然成交额 100 元估算，不计算推广花费。"
                return "预计盈亏：按推广花费 100 元估算，结合当前投产或成交出价计算。"
            if name == "净利润" and card_data.get("is_natural_flow"):
                return "净利润：自然成交金额扣除商品成本、优惠、退货和技术服务费后的利润，不计算推广花费。"
            return descriptions.get(name, plain)

        def render(plain):
            nonbreaking = "\u2060".join(plain.replace(" ", "\u00a0"))
            return f'<span style="color:{foreground};font-weight:bold;">{html.escape(nonbreaking)}</span>'

        margin_parts = metric_parts(self.margin_label)
        order_parts = metric_parts(self.link_order_label)
        net_parts = metric_parts(self.net_profit_label)
        roi_parts = metric_parts(self.roi_label)
        order_source = next((part for part in order_parts if part.startswith("单量:")), "")
        if real_mode:
            order_source = next((part for part in net_parts if part.startswith("净成交:")), order_source)
        order_text = order_source.replace("净成交:", "净成交").replace("单量:", "单量").rstrip("单")

        if real_mode:
            promotion_source = next((part for part in net_parts if part.startswith("净投产比:")), "")
            promotion_text = f"真实推广·{promotion_source.replace(':', '', 1)}" if promotion_source else "真实推广"
            promotion_colors = ("#a5f3fc", "#0891b2")
        elif card_data.get("is_natural_flow"):
            promotion_text = "无推广·自然流量"
            promotion_colors = ("#86efac", "#16a34a")
        elif card_data.get("is_sitewide_managed"):
            promotion_source = next((part for part in roi_parts if part.startswith("全站:")), "全站:未设置")
            promotion_text = f"推广中·全站托管·投产{promotion_source.split(':', 1)[1]}"
            promotion_colors = ("#c4b5fd", "#7c3aed")
        elif (card_data.get("roi_input_mode") or "roi") == "bid":
            promotion_source = next((part for part in roi_parts if part.startswith("出价:")), "出价:未设置")
            promotion_text = f"推广中·成交出价{promotion_source.replace('出价:', '')}"
            promotion_colors = ("#fdba74", "#ea580c")
        else:
            promotion_source = next((part for part in roi_parts if part.startswith("投产:")), "投产:未设置")
            promotion_text = f"推广中·稳定成本·{promotion_source.replace(':', '', 1)}"
            promotion_colors = ("#93c5fd", "#2563eb")

        multiple_source = next(
            (part for part in roi_parts if part.startswith(("全站投产倍数:", "投产倍数:", "出价倍数:"))),
            "",
        )
        multiple_text = (
            multiple_source.replace("全站投产倍数:", "倍数")
            .replace("投产倍数:", "倍数")
            .replace("出价倍数:", "出价倍数")
        )
        status_colors = {
            "盈利": ("#86efac", "#16a34a"), "微盈利": ("#bbf7d0", "#22c55e"),
            "保本": ("#fde68a", "#d97706"), "微亏": ("#fed7aa", "#ea580c"),
            "一般亏": ("#fecaca", "#dc2626"), "巨亏": ("#fca5a5", "#991b1b"),
            "亏损": ("#fecaca", "#dc2626"),
        }
        if real_mode:
            promotion_tooltip = "推广状态：当前展示该链接已导入的真实推广数据。"
        elif card_data.get("is_natural_flow"):
            promotion_tooltip = "推广状态：该链接当前未开启推广，按自然流量计算盈亏。"
        elif card_data.get("is_sitewide_managed"):
            promotion_tooltip = "推广状态：该链接当前使用全站托管推广。"
        elif (card_data.get("roi_input_mode") or "roi") == "bid":
            promotion_tooltip = "推广状态：该链接当前按成交出价进行推广。"
        else:
            promotion_tooltip = "推广状态：该链接当前使用稳定成本推广。"
        self._set_bubble_chip("order", order_text, "#fde68a", "#d97706", metric_tooltip(order_source or "单量:"))
        self._set_bubble_chip("promotion", promotion_text, *promotion_colors, promotion_tooltip)
        self._set_bubble_chip("multiple", multiple_text, "#bfdbfe", "#2563eb", metric_tooltip(multiple_source))
        self._set_bubble_chip(
            "status", profit_status or "", *status_colors.get(profit_status, ("#e5e7eb", "#6b7280")),
            f"盈亏状态：根据当前净利率判断为{profit_status}。" if profit_status else "",
        )
        self.bubble_chips_widget.setVisible(any(chip.text() for chip in self.bubble_chip_labels.values()))

        moved_prefixes = (
            "单量:", "净成交:", "净投产比:", "全站:", "投产:", "全站投产倍数:",
            "投产倍数:", "出价:", "保本出价:", "出价倍数:", "无推广",
        )
        net_parts = [part for part in net_parts if not part.startswith(moved_prefixes)]
        roi_parts = [part for part in roi_parts if not part.startswith(moved_prefixes)]
        summary_parts = margin_parts + net_parts
        avg_price = getattr(self, "_bubble_avg_price", 0) or 0
        if (
            avg_price > 0
            and "avg_price" not in hidden_metrics
            and not any(part.startswith("客单价:") for part in summary_parts)
        ):
            summary_parts.append(f"客单价:¥{avg_price:.2f}")
        remaining_parts = summary_parts + roi_parts
        expected_profit = getattr(self, "_bubble_expected_profit", None)
        if expected_profit is not None and not real_mode:
            remaining_parts.append(f"预计盈亏:¥{expected_profit:.2f}")
        rows = [remaining_parts[index:index + 2] for index in range(0, len(remaining_parts), 2)]
        rows = [row for row in rows if row]

        while len(self.bubble_metric_chips) < len(remaining_parts):
            chip = QLabel(self.bubble_metrics_widget)
            chip.setAlignment(Qt.AlignCenter)
            chip.setFixedHeight(18)
            chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            chip.installEventFilter(self)
            self.bubble_metric_chips.append(chip)

        loss_statuses = {"微亏", "一般亏", "巨亏", "亏损"}
        for index, plain in enumerate(remaining_parts):
            chip = self.bubble_metric_chips[index]
            if plain.startswith(("毛利率:", "毛利润:")):
                background, border = "#fecaca", "#ef4444"
            elif plain.startswith(("净利率:", "净利润:", "预计盈亏:")):
                if profit_status in loss_statuses or re.search(r":-|\(.*-", plain):
                    background, border = "#fecaca", "#dc2626"
                elif profit_status == "保本":
                    background, border = "#fde68a", "#d97706"
                else:
                    background, border = "#bbf7d0", "#16a34a"
            elif plain.startswith(("客单价:", "交易额:", "每笔成交:")):
                background, border = "#bfdbfe", "#2563eb"
            elif plain.startswith(("花费:", "每笔花费:")):
                background, border = "#fed7aa", "#ea580c"
            elif plain.startswith("曝光占比:"):
                background, border = "#ddd6fe", "#7c3aed"
            elif plain.startswith(("点击率:", "点击转化率:")):
                background, border = "#a5f3fc", "#0891b2"
            else:
                background, border = "#e5e7eb", "#6b7280"
            row, column = divmod(index, 2)
            column_span = 2 if index == len(remaining_parts) - 1 and column == 0 else 1
            self.bubble_metrics_layout.addWidget(chip, row, column, 1, column_span)
            chip.setText(plain)
            chip.setToolTip(metric_tooltip(plain))
            chip.setStyleSheet(
                f"color:#111; background:{background}; border:1px solid {border}; "
                "border-radius:6px; padding:1px; font-weight:bold;"
            )
            chip.show()
        for chip in self.bubble_metric_chips[len(remaining_parts):]:
            chip.hide()
        self.bubble_metrics_widget.setVisible(bool(remaining_parts))

        html_rows = []
        for row in rows:
            cells = []
            for plain in row:
                span = 2 if len(row) == 1 else 1
                cells.append(
                    f'<td colspan="{span}" align="center" style="background-color:transparent; border:1px solid {foreground}; '
                    f'border-radius:4px; padding:1px; margin:0px; line-height:{line_height}px; white-space:nowrap;">'
                    f'{render(plain)}</td>'
                )
            html_rows.append(f'<tr>{"".join(cells)}</tr>')
        self.bubble_metrics_label.setText(
            '<table width="100%" cellspacing="1" cellpadding="0" style="margin:0px; background-color:transparent;">'
            + "".join(html_rows) + "</table>"
        )
        self.bubble_metrics_label.setToolTip("")
        self.bubble_metrics_label.hide()

    def _update_margin_display(self, fresh=True):
        self._bubble_avg_price = 0
        self._bubble_expected_profit = None
        self._update_bubble_net_margin_color(None)
        try:
            real_promotion_mode = (
                hasattr(self.main_app, "is_real_promotion_data_mode")
                and self.main_app.is_real_promotion_data_mode()
            )
            if hasattr(self, "title_label"):
                self.title_label.setVisible(self.display_mode != "bubble" and not real_promotion_mode)
            if hasattr(self, "memo_label"):
                self.memo_label.setVisible(self.display_mode != "bubble" and not real_promotion_mode)
            if hasattr(self, "real_date_label"):
                self.real_date_label.hide()
            if hasattr(self, "link_order_label"):
                self.link_order_label.setVisible(not real_promotion_mode)
            if not real_promotion_mode:
                self.margin_label.setWordWrap(True)
                self.margin_label.setMinimumHeight(0)
                self.margin_label.setMaximumHeight(16777215)
                self.margin_label.setStyleSheet("color: #d9534f; font-weight: bold; font-size: 12px;")

            margin_metrics = self.main_app.get_product_gross_margin_metrics(self.prod_id, fresh=fresh)
            if not margin_metrics.get("spec_count"):
                self.margin_label.setText("毛利率: -")
                self.net_profit_label.setText("净利率: -")
                self.margin_label.hide()
                self.net_profit_label.hide()
                self.roi_label.setText("")
                self.link_order_label.setText("单量:0单")
                if hasattr(self.main_app, "update_product_row_height"):
                    self.main_app.update_product_row_height(self.prod_id)
                return
            card_data = self.main_app.get_product_card_data(self.prod_id)
            coupon = card_data.get("coupon_amount") or 0
            new_customer = card_data.get("new_customer_discount") or 0
            max_discount = max(coupon, new_customer)
            current_roi = card_data.get("current_roi") or 0
            return_rate = card_data.get("return_rate") or 0
            net_break_even_roi = card_data.get("net_break_even_roi") or 0
            is_natural_flow = card_data.get("is_natural_flow") or 0
            is_sitewide_managed = card_data.get("is_sitewide_managed") or 0
            sitewide_roi = card_data.get("sitewide_roi") or 0
            store_id = card_data.get("store_id")
            roi_input_mode = card_data.get("roi_input_mode") or "roi"
            transaction_bid = card_data.get("transaction_bid") or 0
            final_margin_pct = margin_metrics.get("gross_margin_pct")
            if final_margin_pct is not None:
                avg_price = margin_metrics.get("avg_final_price") or 0
                self._bubble_avg_price = float(avg_price)
                avg_gross_profit = margin_metrics.get("avg_gross_profit") or 0
                self.margin_label.setText(f"毛利率:{final_margin_pct:.2f}%")
                weight_source = "导入订单规格单量" if margin_metrics.get("weight_source") == "orders" else "保存规格权重"
                order_info = ""
                if margin_metrics.get("weight_source") == "orders":
                    order_info = f"\n识别单量: {int(margin_metrics.get('recognized_order_count') or 0)} 单"
                self.margin_label.setToolTip(
                    "综合毛利口径：券后价=(售价-最大优惠)，按规格窗口同口径加权\n"
                    f"有效规格: {int(margin_metrics.get('valid_spec_count') or 0)} 个\n"
                    f"权重来源: {weight_source}{order_info}\n"
                    f"权重合计: {float(margin_metrics.get('total_weight') or 0):.2f}%\n"
                    f"最大优惠: ¥{float(margin_metrics.get('discount_amount') or 0):.2f}"
                )
                self.margin_label.show()
                final_net_margin_pct = -100
                margin_rate_decimal = final_margin_pct / 100
                net_margin_formula = margin_rate_decimal * (1 - return_rate / 100) - 0.006
                net_break_even_roi = 1 / net_margin_formula if net_margin_formula > 0 else 0
                effective_roi = sitewide_roi if is_sitewide_managed and not is_natural_flow else current_roi
                expected_roi = effective_roi
                if roi_input_mode == "bid" and not is_natural_flow and avg_price > 0:
                    bid = float(transaction_bid or 0)
                    if bid <= 0 and effective_roi > 0:
                        bid = avg_price / effective_roi
                    expected_roi = avg_price / bid if bid > 0 else 0
                self._bubble_expected_profit = _expected_profit_for_100(
                    is_natural_flow, margin_rate_decimal, return_rate, expected_roi
                )
                if (
                    real_promotion_mode
                ):
                    self._apply_real_promotion_display(store_id, margin_rate_decimal, net_break_even_roi)
                    if hasattr(self.main_app, "update_product_row_height"):
                        self.main_app.update_product_row_height(self.prod_id)
                    return
                if roi_input_mode == "bid" and not is_natural_flow and not is_sitewide_managed:
                    self._apply_bid_mode_display(
                        avg_price,
                        avg_gross_profit,
                        margin_rate_decimal,
                        current_roi,
                        transaction_bid,
                        return_rate,
                        net_break_even_roi,
                    )
                    if hasattr(self.main_app, "update_product_row_height"):
                        self.main_app.update_product_row_height(self.prod_id)
                    return
                if is_natural_flow:
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006) * 100
                elif effective_roi > 0 and return_rate >= 0:
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006 - (1 / effective_roi)) * 100
                self._update_bubble_net_margin_color(final_net_margin_pct)
                net_profit_text = self._get_net_profit_status(final_net_margin_pct)
                self.net_profit_label.setText(f"净利率: {final_net_margin_pct:.2f}% {net_profit_text}")
                if is_natural_flow:
                    roi_multiple_text = '<span style="color: #16a085; font-weight: bold;">无推广</span>'
                elif effective_roi > 0 and net_break_even_roi > 0:
                    roi_multiple = effective_roi / net_break_even_roi
                    label = "全站" if is_sitewide_managed else "投产"
                    multiple_label = "全站投产倍数" if is_sitewide_managed else "投产倍数"
                    roi_multiple_text = f'<span style="color: #666666; font-weight: bold;">{label}:</span><span style="color: #e74c3c; font-weight: bold;">{effective_roi:.2f}</span><br><span style="color: #666666; font-weight: bold;">{multiple_label}:</span><span style="color: #3498db; font-weight: bold;">{roi_multiple:.2f}倍</span>'
                elif effective_roi > 0:
                    label = "全站" if is_sitewide_managed else "投产"
                    multiple_label = "全站投产倍数" if is_sitewide_managed else "投产倍数"
                    roi_multiple_text = f'<span style="color: #666666; font-weight: bold;">{label}:</span><span style="color: #e74c3c; font-weight: bold;">{effective_roi:.2f}</span><br><span style="color: #666666; font-weight: bold;">{multiple_label}:</span><span style="color: #e74c3c; font-weight: bold;">无法保本</span>'
                else:
                    roi_multiple_text = ""
                self.roi_label.setText(roi_multiple_text)
                if final_net_margin_pct > 5:
                    self.net_profit_label.setStyleSheet("color: #006400; font-weight: bold; font-size: 13px;")
                elif final_net_margin_pct > 1:
                    self.net_profit_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 13px;")
                elif final_net_margin_pct >= -2:
                    self.net_profit_label.setStyleSheet("color: #daa520; font-weight: bold; font-size: 13px;")
                elif final_net_margin_pct >= -5:
                    self.net_profit_label.setStyleSheet("color: #ff8c00; font-weight: bold; font-size: 13px;")
                elif final_net_margin_pct >= -8:
                    self.net_profit_label.setStyleSheet("color: #dc143c; font-weight: bold; font-size: 13px;")
                else:
                    self.net_profit_label.setStyleSheet("color: #8b0000; font-weight: bold; font-size: 13px;")
                self.net_profit_label.show()
            else:
                self.margin_label.setText("毛利率: -")
                self.margin_label.show()
                self.net_profit_label.setText("净利率: -")
                self.net_profit_label.show()
                self.roi_label.setText("")
            self.update_link_order_count()
            if hasattr(self.main_app, "update_product_row_height"):
                self.main_app.update_product_row_height(self.prod_id)
        except Exception as e:
            print(f"更新毛利显示失败：{e}")
            if hasattr(self, "title_label"):
                self.title_label.setVisible(self.display_mode != "bubble")
            if hasattr(self, "memo_label"):
                self.memo_label.setVisible(self.display_mode != "bubble")
            if hasattr(self, "real_date_label"):
                self.real_date_label.hide()
            self.margin_label.setText("毛利率: 错误")
            self.margin_label.show()
            self.net_profit_label.setText("净利率: 错误")
            self.net_profit_label.show()
            self.roi_label.setText("")
            self.link_order_label.setText("单量:0单")
            if hasattr(self.main_app, "update_product_row_height"):
                self.main_app.update_product_row_height(self.prod_id)

    def _get_current_display_order_count(self):
        try:
            store_id = self.main_app.get_product_card_data(self.prod_id).get("store_id")
            year = int(getattr(self.main_app, "year", 0) or 0)
            month = int(getattr(self.main_app, "month", 0) or 0)
            if store_id and year > 0 and month > 0:
                prefix = f"{year:04d}-{month:02d}"
                rows = self.main_app.db.safe_fetchall(
                    "SELECT order_count FROM imported_orders WHERE store_id=? AND product_id=? AND order_date LIKE ?",
                    (store_id, self.prod_code, f"{prefix}%")
                )
                if rows:
                    return sum(float(row[0] or 0) for row in rows)
            if store_id:
                rows = self.main_app.db.safe_fetchall(
                    "SELECT order_count FROM imported_orders WHERE store_id=? AND product_id=?",
                    (store_id, self.prod_code)
                )
            else:
                rows = self.main_app.db.safe_fetchall(
                    "SELECT order_count FROM imported_orders WHERE product_id=?",
                    (self.prod_code,)
                )
            return sum(float(row[0] or 0) for row in rows) if rows else 0.0
        except Exception as e:
            print(f"读取链接单量失败: {e}")
            return 0.0

    def _apply_bid_mode_display(self, avg_price, avg_gross_profit, margin_rate_decimal, current_roi, transaction_bid, return_rate, net_break_even_roi):
        order_count = self._get_current_display_order_count()
        gross_profit_total = avg_gross_profit * order_count
        estimated_trade_amount = avg_price * order_count
        self.margin_label.setText(f"毛利润: ¥{gross_profit_total:.2f}<br>客单价: ¥{avg_price:.2f}")
        self.margin_label.setToolTip(
            "成交出价模式毛利润口径：当前月份链接单量 × 单笔加权毛利润\n"
            f"当前月份链接单量: {order_count:.0f}单\n"
            f"估算交易额: ¥{estimated_trade_amount:.2f}\n"
            f"客单价: ¥{avg_price:.2f}\n"
            f"单笔毛利润: ¥{avg_gross_profit:.2f}\n"
            f"总毛利润: ¥{gross_profit_total:.2f}"
        )
        self.margin_label.show()

        return_factor = max(0.0, 1 - float(return_rate or 0) / 100)
        bid = float(transaction_bid or 0)
        if bid <= 0 and avg_price > 0 and current_roi and current_roi > 0:
            bid = avg_price / current_roi
        if avg_price > 0 and bid > 0 and return_factor > 0:
            avg_net_profit = avg_gross_profit * return_factor - (avg_price * 0.006) - bid
            net_profit_total = avg_net_profit * order_count
            net_margin_pct = (avg_net_profit / avg_price) * 100
            self._update_bubble_net_margin_color(net_margin_pct)
            ad_cost_total = bid * order_count
            status = self._get_net_profit_status(net_margin_pct)
            self.net_profit_label.setText(f"净利润: ¥{net_profit_total:.2f}<br>净利率: {net_margin_pct:.2f}% {status}")
            self.net_profit_label.setToolTip(
                "成交出价模式净利润口径：当前月份链接单量 × 单笔净利润\n"
                "单笔净利润 = 单笔毛利润 × (1-退货率) - 技术服务费 - 成交出价\n"
                f"当前月份链接单量: {order_count:.0f}单\n"
                f"估算交易额: ¥{estimated_trade_amount:.2f}\n"
                f"估算推广花费: ¥{ad_cost_total:.2f}\n"
                f"成交出价: ¥{bid:.2f}/单\n"
                f"单笔净利润: ¥{avg_net_profit:.2f}\n"
                f"净利润: ¥{net_profit_total:.2f}\n"
                f"净利率: {net_margin_pct:.2f}%\n"
                f"状态: {status}"
            )

            if net_profit_total > 0:
                self.net_profit_label.setStyleSheet("color: #006400; font-weight: bold; font-size: 13px;")
            elif abs(net_profit_total) < 0.000001:
                self.net_profit_label.setStyleSheet("color: #daa520; font-weight: bold; font-size: 13px;")
            else:
                self.net_profit_label.setStyleSheet("color: #dc143c; font-weight: bold; font-size: 13px;")
            self.net_profit_label.show()

            break_even_bid = avg_gross_profit * return_factor - (avg_price * 0.006)
            if break_even_bid > 0 and bid > 0:
                bid_multiple = bid / break_even_bid
                multiple_text = f"{bid_multiple:.2f}倍"
                multiple_color = "#dc143c" if bid_multiple > 1 else "#006400" if bid_multiple < 1 else "#daa520"
            else:
                break_even_bid = 0.0
                multiple_text = "--"
                multiple_color = "#3498db"
            self.roi_label.setText(
                f'<span style="color: #666666; font-weight: bold;">出价:</span>'
                f'<span style="color: #e74c3c; font-weight: bold;">¥{bid:.2f}</span><br>'
                f'<span style="color: #666666; font-weight: bold;">保本出价:</span>'
                f'<span style="color: #16a085; font-weight: bold;">¥{break_even_bid:.2f}</span><br>'
                f'<span style="color: #666666; font-weight: bold;">出价倍数:</span>'
                f'<span style="color: {multiple_color}; font-weight: bold;">{multiple_text}</span>'
            )
            self.roi_label.setToolTip(
                "出价倍数 = 当前成交出价 ÷ 保本出价\n"
                "成交出价模式和投产相反：出价倍数大于 1 表示当前出价高于保本线，通常偏亏；小于 1 表示低于保本线。\n"
                f"保本出价 = 单笔毛利润 × (1-退货率) - 技术服务费 = ¥{break_even_bid:.2f}\n"
                f"当前成交出价: ¥{bid:.2f}\n"
                f"出价倍数: {multiple_text}"
            )
        else:
            self._update_bubble_net_margin_color(None)
            self.net_profit_label.setText("净利润: --<br>净利率: --")
            self.net_profit_label.setStyleSheet("color: #999; font-weight: bold; font-size: 13px;")
            self.net_profit_label.show()
            self.roi_label.setText(
                '<span style="color: #666666; font-weight: bold;">出价:</span>'
                '<span style="color: #e74c3c; font-weight: bold;">--</span><br>'
                '<span style="color: #666666; font-weight: bold;">保本出价:</span>'
                '<span style="color: #16a085; font-weight: bold;">--</span><br>'
                '<span style="color: #666666; font-weight: bold;">出价倍数:</span>'
                '<span style="color: #3498db; font-weight: bold;">--</span>'
            )
            self.roi_label.setToolTip("出价倍数 = 当前成交出价 ÷ 保本出价")
        self.link_order_label.setText(f"单量:{order_count:.0f}单")
        self.update_link_order_count()

    def update_link_order_count(self):
        try:
            if (
                hasattr(self.main_app, "is_real_promotion_data_mode")
                and self.main_app.is_real_promotion_data_mode()
                and hasattr(self.main_app, "get_latest_promotion_data")
            ):
                self.link_order_label.hide()
                return

            store_id = self.main_app.get_product_card_data(self.prod_id).get("store_id")
            total = self.main_app._get_product_order_count(self.prod_code, store_id)
            self.link_order_label.setText(f"单量:{int(float(total or 0))}单")
        except Exception as e:
            print(f"更新链接单量失败: {e}")
            self.link_order_label.setText("单量:0单")

    def _get_net_profit_status(self, net_margin_pct):
        if net_margin_pct > 5:
            return "盈利"
        elif net_margin_pct > 1:
            return "微盈利"
        elif net_margin_pct >= -2:
            return "保本"
        elif net_margin_pct >= -5:
            return "微亏"
        elif net_margin_pct >= -8:
            return "一般亏"
        else:
            return "巨亏"

    def _apply_real_promotion_display(self, store_id, margin_rate_decimal, net_break_even_roi):
        hidden_metrics = (
            self.main_app.get_real_promotion_hidden_metrics()
            if hasattr(self.main_app, "get_real_promotion_hidden_metrics")
            else set()
        )
        display_metric_keys = {
            "avg_price", "gross_margin_rate", "cost", "transaction_amount", "net_orders",
            "net_roi", "net_profit", "net_margin_rate", "profit_status", "roi_multiple",
            "promotion_share", "amount_per_order", "cost_per_order", "ctr", "conversion_rate",
        }
        self._real_visible_metric_count = len(display_metric_keys - hidden_metrics)
        metric_separator = "<br>" if self._real_visible_metric_count <= 4 else " "
        data = None
        if hasattr(self.main_app, "get_latest_promotion_data"):
            data = self.main_app.get_latest_promotion_data(store_id, self.prod_code)
        if not data:
            self._update_bubble_net_margin_color(None)
            if hasattr(self, "real_date_label"):
                self.real_date_label.hide()
            self.margin_label.setWordWrap(False)
            self.margin_label.setFixedHeight(16)
            self.margin_label.setStyleSheet("color: #d9534f; font-weight: bold; font-size: 12px;")
            self.margin_label.setText("真实推广: 无数据")
            self.margin_label.show()
            self.net_profit_label.setText("净利润: 无真实推广数据")
            self.net_profit_label.setStyleSheet("color: #999; font-weight: bold; font-size: 13px;")
            self.net_profit_label.show()
            self.roi_label.setText("")
            self.link_order_label.hide()
            return True

        cost = float(data.get("cost") or 0)
        transaction_amount = float(data.get("transaction_amount") or 0)
        net_amount = float(data.get("net_transaction_amount") or 0)
        net_roi = float(data.get("net_roi") or 0)
        net_orders = float(data.get("net_orders") or 0)
        promotion_share = float(data.get("promotion_impression_share") or 0)
        cost_per_net_order = float(data.get("cost_per_net_order") or 0)
        ctr = float(data.get("ctr") or 0)
        click_conversion_rate = float(data.get("click_conversion_rate") or 0)
        amount_per_net_order = net_amount / net_orders if net_orders > 0 else 0
        if cost_per_net_order <= 0 and net_orders > 0:
            cost_per_net_order = cost / net_orders
        snapshot_net_profit = data.get("net_profit")
        snapshot_net_margin = data.get("net_margin_rate")
        if snapshot_net_profit is not None and snapshot_net_margin is not None:
            net_profit = float(snapshot_net_profit)
            net_margin_pct = float(snapshot_net_margin)
            net_margin_text = f"{net_margin_pct:.2f}%"
            status = self._get_net_profit_status(net_margin_pct)
        elif net_amount > 0:
            tech_fee = net_amount * 0.006
            net_profit = net_amount * margin_rate_decimal - cost - tech_fee
            net_margin_pct = net_profit / net_amount * 100
            net_margin_text = f"{net_margin_pct:.2f}%"
            status = self._get_net_profit_status(net_margin_pct)
        else:
            net_profit = -cost
            net_margin_pct = None
            net_margin_text = "无成交"
            status = "亏损" if net_profit < 0 else "保本"
        self._update_bubble_net_margin_color(net_margin_pct)
        roi_multiple = net_roi / net_break_even_roi if net_break_even_roi and net_break_even_roi > 0 else None
        if hasattr(self, "real_date_label"):
            self.real_date_label.hide()

        def metric(key, label, value, color="#333"):
            if key in hidden_metrics:
                return ""
            return (
                '<span style="white-space: nowrap;">'
                f'<span style="color:#666;font-weight:bold;">{label}</span>'
                f'<span style="color:{color};font-weight:bold;">{value}</span>'
                '</span>'
            )

        def money(value):
            return f"¥{float(value or 0):.2f}"

        if hasattr(self, "metrics_panel"):
            self.metrics_panel.setMaximumWidth(16777215)
            self.metrics_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.margin_label.setWordWrap(False)
        self.margin_label.setMinimumHeight(16)
        self.margin_label.setMaximumHeight(16777215)
        self.net_profit_label.setMaximumHeight(16777215)
        self.roi_label.setMaximumHeight(16777215)
        self.margin_label.setStyleSheet("color: #d9534f; font-weight: bold; font-size: 12px;")
        gross_margin_text = f"{margin_rate_decimal * 100:.2f}%"
        self.margin_label.setText(
            f'{metric("gross_margin_rate", "毛利率:", gross_margin_text, "#d9534f")}<br>'
            f'{metric("cost", "花费:", money(cost), "#e67e22")}<br>'
            f'{metric("transaction_amount", "交易额:", money(transaction_amount), "#2c7be5")}'
        )
        self.margin_label.setVisible(bool(self.margin_label.text().strip()))
        if net_profit > 0:
            self.net_profit_label.setStyleSheet("color: #006400; font-weight: bold; font-size: 13px;")
        elif abs(net_profit) < 0.000001:
            self.net_profit_label.setStyleSheet("color: #daa520; font-weight: bold; font-size: 13px;")
        else:
            self.net_profit_label.setStyleSheet("color: #dc143c; font-weight: bold; font-size: 13px;")
        self.net_profit_label.setText(
            f'{metric("net_orders", "净成交:", f"{net_orders:.0f}单", "#8b4513")}{metric_separator}'
            f'{metric("net_roi", "净投产比:", f"{net_roi:.2f}", "#e74c3c")}<br>'
            f'{metric("net_profit", "净利润:", f"¥{net_profit:.2f}", "#dc143c" if net_profit < 0 else "#006400")}{metric_separator}'
            f'{metric("net_margin_rate", "净利率:", net_margin_text, "#dc143c" if net_profit < 0 else "#006400")}{metric_separator}'
            f'{metric("profit_status", "", status, "#dc143c" if net_profit < 0 else "#006400")}'
        )
        self.net_profit_label.setToolTip(
            f"净成交: {net_orders:.0f}单\n净投产比: {net_roi:.2f}\n"
            f"净利润: ¥{net_profit:.2f}\n净利率: {net_margin_text}\n状态: {status}"
        )
        self.net_profit_label.setVisible(bool(re.sub(r"<[^>]+>", "", self.net_profit_label.text()).strip()))
        multiple_text = f"{roi_multiple:.2f}倍" if roi_multiple is not None else "--"
        self.roi_label.setText(
            f'{metric("roi_multiple", "投产倍数:", multiple_text, "#3498db")}{metric_separator}'
            f'{metric("promotion_share", "曝光占比:", f"{promotion_share * 100:.2f}%", "#8e44ad")}<br>'
            f'{metric("amount_per_order", "每笔成交:", f"¥{amount_per_net_order:.2f}", "#2c7be5")}{metric_separator}'
            f'{metric("cost_per_order", "每笔花费:", f"¥{cost_per_net_order:.2f}", "#e67e22")}<br>'
            f'{metric("ctr", "点击率:", f"{ctr * 100:.2f}%", "#16a085")}{metric_separator}'
            f'{metric("conversion_rate", "点击转化率:", f"{click_conversion_rate * 100:.2f}%", "#16a085")}'
        )
        self.roi_label.setToolTip(
            f"投产倍数: {multiple_text}\n曝光占比: {promotion_share * 100:.2f}%\n"
            f"每笔成交金额: ¥{amount_per_net_order:.2f}\n每笔花费: ¥{cost_per_net_order:.2f}\n"
            f"点击率: {ctr * 100:.2f}%\n点击转化率: {click_conversion_rate * 100:.2f}%"
        )
        self.link_order_label.hide()
        return True

    def eventFilter(self, obj, event):
        if sip.isdeleted(self) or sip.isdeleted(obj):
            return False
        if getattr(self, "_disposing", False):
            return False
        tooltip_targets = tuple(
            widget for widget in (
                getattr(self, "code_label", None),
                getattr(self, "category_label", None),
                getattr(self, "bubble_metrics_label", None),
                getattr(self, "img_label", None),
                getattr(self, "reminder_badge", None),
                getattr(self, "marketing_badge", None),
            ) if widget is not None
        ) + tuple(getattr(self, "bubble_metric_chips", ())) + tuple(
            getattr(self, "bubble_chip_labels", {}).values()
        )
        if obj in tooltip_targets:
            if event.type() == QEvent.ToolTip:
                text = obj.toolTip()
                if obj == getattr(self, "reminder_badge", None):
                    loader = getattr(self.main_app, "get_product_pending_task_lines", None)
                    lines = loader(self.prod_id) if callable(loader) else []
                    text = "\n\n".join(lines) if lines else "当前没有待完成任务"
                self._show_bubble_tooltip(text, event.globalPos())
                return True
            if event.type() == QEvent.Leave:
                self._hide_bubble_tooltip()
        if hasattr(self, "category_label") and obj == self.category_label:
            if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self.show_category_link_editor_menu(event.globalPos())
                return True
        if hasattr(self, "img_label") and obj == self.img_label and event.type() == QEvent.ContextMenu:
            self.show_product_image_history_dialog()
            return True
        if event.type() == QEvent.ContextMenu:
            self.show_product_context_menu(event.globalPos())
            return True
        if hasattr(self, "code_label") and obj == self.code_label:
            if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self._suppress_next_code_click = True
                self._code_click_timer.stop()
                self.copy_same_product()
                return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                if self._suppress_next_code_click:
                    self._suppress_next_code_click = False
                    return True
                self._code_click_timer.start(QApplication.doubleClickInterval())
                return True
        if hasattr(self, "memo_label") and obj == self.memo_label and event.type() == QEvent.MouseButtonDblClick:
            self.edit_product_memo()
            return True
        if hasattr(self, "img_label") and obj == self.img_label:
            if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self.show_product_image_viewer()
                return True
            if event.type() == QEvent.Enter:
                self.img_label.setFocus(Qt.MouseFocusReason)
                return False
            if event.type() == QEvent.Leave:
                self.img_label.clearFocus()
                return False
            if event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
                    self._paste_image_from_clipboard()
                    return True
        return False

    def _show_bubble_tooltip(self, text, global_pos):
        text = str(text or "").strip()
        if not text:
            return
        popup = getattr(self, "_bubble_tooltip", None)
        if popup is None:
            popup = QLabel(self, Qt.ToolTip)
            popup.setWordWrap(True)
            popup.setMaximumWidth(420)
            popup.setStyleSheet(
                "background: #ffffff; color: #111111; border: 1px solid #b8b8b8; "
                "padding: 4px 6px; font-size: 12px;"
            )
            self._bubble_tooltip = popup
        popup.hide()
        popup.setText(text)
        popup.ensurePolished()
        popup.adjustSize()
        position = global_pos + QPoint(12, 16)
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            position.setX(max(available.left(), min(position.x(), available.right() - popup.width() + 1)))
            position.setY(max(available.top(), min(position.y(), available.bottom() - popup.height() + 1)))
        popup.move(position)
        popup.show()

    def _hide_bubble_tooltip(self):
        popup = getattr(self, "_bubble_tooltip", None)
        if popup is not None:
            popup.hide()

    def show_category_link_editor_menu(self, global_pos):
        menu = QMenu(self)
        action_category = QAction("编辑商品类型（成本库）", self)
        action_link_type = QAction("编辑链接类型（商品类型）", self)
        menu.addAction(action_category)
        menu.addAction(action_link_type)
        selected = menu.exec_(global_pos)
        if selected == action_category:
            self.open_cost_library_editor_section("category")
        elif selected == action_link_type:
            self.open_cost_library_editor_section("link_type")

    def open_cost_library_editor_section(self, section):
        if not hasattr(self.main_app, "show_cost_library"):
            return
        self.main_app.show_cost_library()
        dialog = getattr(self.main_app, "cost_library_dialog", None)
        if dialog is None:
            return
        if section == "category" and hasattr(dialog, "show_category_manage"):
            target_category = self._current_product_category_label()
            QTimer.singleShot(0, lambda: dialog.show_category_manage(target_category))
        elif section == "link_type" and hasattr(dialog, "show_link_combinations"):
            QTimer.singleShot(0, lambda: dialog.show_link_combinations(self.prod_code))

    def _current_product_category_label(self):
        try:
            rows = self.db.safe_fetchall(
                "SELECT COALESCE(product_category_label, '') FROM products WHERE id=?",
                (self.prod_id,),
            )
            return str(rows[0][0] or "").strip() if rows else ""
        except Exception:
            return ""

    def contextMenuEvent(self, event):
        self.show_product_context_menu(event.globalPos())
        event.accept()

    def show_product_context_menu(self, global_pos):
        self.refresh_violation_state(fresh=True)
        menu = QMenu(self)
        _enlarge_context_menu(menu)
        if self.is_violation:
            release_action = menu.addAction("解除违规")
            if menu.exec_(global_pos) == release_action:
                self.set_violation_state(False)
            return
        material_action = QAction("打开链接素材库", self)
        product_material_action = QAction("打开产品素材库", self)
        record_action = QAction("操作记录", self)
        quick_profit_action = QAction("快速计算利润", self)
        pdd_code_fetch_action = QAction("抓取添加编码", self)
        pdd_price_fetch_action = QAction("抓取价格管理", self)
        promotion_action = QAction("查看推广数据", self)
        delete_action = QAction("删除链接", self)
        menu.addAction(promotion_action)
        menu.addAction(record_action)
        menu.addAction(material_action)
        menu.addAction(product_material_action)
        menu.addAction(quick_profit_action)
        menu.addAction(pdd_code_fetch_action)
        menu.addAction(pdd_price_fetch_action)
        violation_action = menu.addAction("标记违规")
        menu.addAction(delete_action)
        selected = menu.exec_(global_pos)
        if selected == promotion_action:
            self.open_promotion_history()
        elif selected == record_action:
            if hasattr(self.main_app, "open_product_record_window"):
                self.main_app.open_product_record_window(self.prod_id)
        elif selected == material_action:
            if hasattr(self.main_app, "open_link_material_library"):
                self.main_app.open_link_material_library(self.prod_id)
        elif selected == product_material_action:
            if hasattr(self.main_app, "open_product_material_library_for_link"):
                self.main_app.open_product_material_library_for_link(self.prod_id)
        elif selected == quick_profit_action:
            self.open_quick_profit_calculator()
        elif selected in (pdd_code_fetch_action, pdd_price_fetch_action):
            store_id = getattr(self.main_app, "product_store_map", {}).get(self.prod_id)
            if not store_id and hasattr(self.main_app, "get_product_card_data"):
                store_id = self.main_app.get_product_card_data(self.prod_id).get("store_id")
            method_name = (
                "open_pdd_code_fetch_for_store"
                if selected == pdd_code_fetch_action
                else "open_pdd_price_fetch_for_store"
            )
            if hasattr(self.main_app, method_name):
                if selected == pdd_code_fetch_action:
                    getattr(self.main_app, method_name)(store_id, self.prod_code)
                else:
                    getattr(self.main_app, method_name)(store_id)
        elif selected == violation_action:
            self.set_violation_state(True)
        elif selected == delete_action:
            self.delete_product()

    def open_quick_profit_calculator(self):
        metrics = self.main_app.get_product_gross_margin_metrics(self.prod_id, fresh=True)
        margin_rate = metrics.get("gross_margin_pct")
        avg_price = metrics.get("avg_final_price")
        if margin_rate is None or not avg_price:
            QMessageBox.warning(self, "无法计算", "当前链接缺少有效的规格价格、成本或权重。")
            return
        rows = self.db.safe_fetchall(
            "SELECT COALESCE(return_rate, 0) FROM products WHERE id=?", (self.prod_id,)
        )
        return_rate = float(rows[0][0] or 0) if rows else 0.0
        self.main_app.open_profit_calculator_dialog(
            float(margin_rate), float(avg_price), self.prod_id, self.prod_title,
            "product", self, self.db, return_rate=return_rate, quick_mode=True,
        )

    def open_promotion_history(self):
        try:
            store_rows = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.prod_id,))
            store_id = store_rows[0][0] if store_rows else None
            store_name = ""
            if store_id:
                name_rows = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
                store_name = name_rows[0][0] if name_rows and name_rows[0][0] else ""
            try:
                from manager.dialogs.promotion_data import ProductPromotionHistoryDialog
            except ImportError:
                from dialogs.promotion_data import ProductPromotionHistoryDialog
            dialog = ProductPromotionHistoryDialog(store_id, store_name, self.prod_code, self.prod_title, self.db, self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"打开推广数据失败: {e}")

    def show_product_image_viewer(self):
        try:
            rows = self.db.safe_fetchall("SELECT image_data FROM products WHERE id=?", (self.prod_id,))
            image_data = rows[0][0] if rows and rows[0][0] else None
            if not image_data:
                self.main_app.show_toast("当前链接没有主图")
                return
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            if pixmap.isNull():
                self.main_app.show_toast("主图读取失败")
                return
            try:
                from manager.dialogs.product_spec import SpecImageViewerDialog
            except ImportError:
                from dialogs.product_spec import SpecImageViewerDialog
            dialog = SpecImageViewerDialog(pixmap, self)
            dialog.setWindowTitle("链接主图查看")
            dialog.exec_()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"查看主图失败: {e}")

    def show_product_image_history_dialog(self):
        self._ensure_main_image_history_record_links()
        dialog = QDialog(self)
        dialog.setWindowTitle("主图历史")
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)

        title = QLabel("右键主图历史：可查看大图或删除历史图片")
        title.setStyleSheet("font-weight: bold; color: #2c3e50; padding: 4px;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        def load_items():
            while grid.count():
                item = grid.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            rows = self.db.safe_fetchall(
                "SELECT id, image_data, changed_at, source FROM product_image_history WHERE product_id=? ORDER BY changed_at DESC, id DESC",
                (self.prod_id,)
            )
            if not rows:
                empty = QLabel("暂无历史图片")
                empty.setAlignment(Qt.AlignCenter)
                empty.setStyleSheet("color: #999; font-size: 14px; padding: 30px;")
                grid.addWidget(empty, 0, 0)
                return

            for idx, (history_id, image_data, changed_at, source) in enumerate(rows):
                card = QWidget()
                card.setFixedSize(154, 226)
                card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(6, 6, 6, 6)
                card_layout.setSpacing(5)
                card.setStyleSheet("QWidget { border: 1px solid #ddd; border-radius: 4px; background: #fafafa; }")

                preview = QLabel()
                preview.setFixedSize(130, 130)
                preview.setAlignment(Qt.AlignCenter)
                preview.setStyleSheet("border: 1px solid #ccc; background: white;")
                pixmap = QPixmap()
                pixmap.loadFromData(bytes(image_data))
                if pixmap.isNull():
                    preview.setText("图片读取失败")
                else:
                    preview.setPixmap(pixmap.scaled(126, 126, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                card_layout.addWidget(preview)

                date_edit = QDateEdit()
                date_edit.setDisplayFormat("yyyy-MM-dd")
                date_edit.setCalendarPopup(True)
                date_edit.setFixedHeight(22)
                date_edit.setStyleSheet("border: 1px solid #ddd; color: #555; font-size: 11px;")

                time_edit = QTimeEdit()
                time_edit.setDisplayFormat("HH:mm")
                time_edit.setFixedHeight(22)
                parsed_dt = self._parse_history_datetime(changed_at)
                if parsed_dt:
                    date_edit.setDate(QDate(parsed_dt.year, parsed_dt.month, parsed_dt.day))
                    time_edit.setTime(QTime(parsed_dt.hour, parsed_dt.minute))
                else:
                    date_edit.setDate(QDate.currentDate())
                time_edit.setStyleSheet("border: 1px solid #ddd; color: #555; font-size: 11px;")
                date_edit.setToolTip(str(changed_at))
                time_edit.setToolTip(str(changed_at))
                card_layout.addWidget(date_edit)
                card_layout.addWidget(time_edit)

                btn_row = QHBoxLayout()
                btn_view = QPushButton("查看")
                btn_delete = QPushButton("删除")
                btn_view.setFixedHeight(28)
                btn_delete.setFixedHeight(28)
                btn_view.setStyleSheet("padding: 4px 8px;")
                btn_delete.setStyleSheet("padding: 4px 8px; color: #c0392b;")
                btn_row.addWidget(btn_view)
                btn_row.addWidget(btn_delete)
                card_layout.addLayout(btn_row)

                btn_view.clicked.connect(lambda checked=False, data=bytes(image_data): self._show_history_image_viewer(data))
                btn_delete.clicked.connect(lambda checked=False, hid=history_id: delete_history_image(hid))
                date_edit.editingFinished.connect(
                    lambda hid=history_id, old_changed_at=str(changed_at), date_editor=date_edit, time_editor=time_edit: update_history_time(hid, old_changed_at, date_editor, time_editor)
                )
                time_edit.editingFinished.connect(
                    lambda hid=history_id, old_changed_at=str(changed_at), date_editor=date_edit, time_editor=time_edit: update_history_time(hid, old_changed_at, date_editor, time_editor)
                )

                grid.addWidget(card, idx // 4, idx % 4)

        def update_history_time(history_id, old_changed_at, date_editor, time_editor):
            new_date = date_editor.date()
            new_time = time_editor.time()
            new_dt = datetime(
                new_date.year(), new_date.month(), new_date.day(),
                new_time.hour(), new_time.minute(), 0
            )
            new_changed_at = new_dt.strftime("%Y-%m-%d %H:%M:%S")
            if new_changed_at == old_changed_at:
                return
            self.db.safe_execute(
                "UPDATE product_image_history SET changed_at=? WHERE id=? AND product_id=?",
                (new_changed_at, history_id, self.prod_id)
            )
            self._sync_main_image_operation_record_time(history_id, new_changed_at)
            load_items()
            self.main_app.show_toast("历史图片时间已同步")

        def delete_history_image(history_id):
            reply = QMessageBox.question(dialog, "确认删除", "确定删除这张历史图片吗？")
            if reply != QMessageBox.Yes:
                return
            self.db.safe_execute("DELETE FROM product_image_history WHERE id=?", (history_id,))
            self._remove_main_image_operation_record(history_id)
            load_items()
            self.main_app.show_toast("历史图片已删除")

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        load_items()
        dialog.exec_()

    def _parse_history_datetime(self, changed_at):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(str(changed_at), fmt)
            except Exception:
                pass
        return None

    def _show_history_image_viewer(self, image_data):
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if pixmap.isNull():
            self.main_app.show_toast("历史图片读取失败")
            return
        try:
            from manager.dialogs.product_spec import SpecImageViewerDialog
        except ImportError:
            from dialogs.product_spec import SpecImageViewerDialog
        viewer = SpecImageViewerDialog(pixmap, self)
        viewer.setWindowTitle("历史主图查看")
        viewer.exec_()

    def _paste_image_from_clipboard(self):
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        pixmap = self._pixmap_from_clipboard_mime(clipboard, mime_data)
        if pixmap.isNull():
            self.main_app.show_toast("剪贴板中没有可用图片")
            return

        try:
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            if not buffer.open(QIODevice.WriteOnly):
                self.main_app.show_toast("剪贴板图片保存失败")
                return
            if not pixmap.save(buffer, "PNG"):
                buffer.close()
                self.main_app.show_toast("剪贴板图片保存失败")
                return
            buffer.close()
            image_data = bytes(byte_array)
            if not image_data:
                self.main_app.show_toast("剪贴板图片保存失败")
                return
            self._save_product_main_image(image_data, "paste")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"粘贴图片失败: {e}")

    def _pixmap_from_clipboard_mime(self, clipboard, mime_data):
        if not mime_data:
            return QPixmap()
        if mime_data.hasImage():
            image = clipboard.image()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                if not pixmap.isNull():
                    return pixmap
        for path in self._image_paths_from_clipboard_mime(mime_data):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                return pixmap
        return QPixmap()

    def _image_paths_from_clipboard_mime(self, mime_data):
        paths = []
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
        if mime_data.hasText():
            for line in str(mime_data.text() or "").splitlines():
                value = line.strip().strip('"')
                if value.startswith("file:///"):
                    value = value.replace("file:///", "", 1)
                paths.append(value)
        result = []
        supported = {bytes(fmt).decode("ascii", "ignore").lower() for fmt in QImageReader.supportedImageFormats()}
        for path in paths:
            path = os.path.abspath(path)
            ext = os.path.splitext(path)[1].lstrip(".").lower()
            if path and os.path.isfile(path) and ext in supported and path not in result:
                result.append(path)
        return result

    def _save_product_main_image(self, image_data, source):
        changed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.main_app.db.safe_execute(
            "UPDATE products SET image_data=? WHERE id=?",
            (image_data, self.prod_id)
        )
        self.main_app.db.safe_execute(
            "INSERT INTO product_image_history (product_id, image_data, changed_at, source) VALUES (?, ?, ?, ?)",
            (self.prod_id, image_data, changed_at, source)
        )
        history_id = self.main_app.db.cursor.lastrowid
        self._append_main_image_change_record(changed_at, history_id)
        if hasattr(self.main_app, "autosave_current_archive"):
            ok, result = self.main_app.autosave_current_archive()
            if not ok:
                print(f"product image archive autosave failed: {result}")
        self.set_image_from_data(image_data)
        self.main_app.show_toast("✅ 主轮播图已更新并记录")

    def _append_main_image_change_record(self, changed_at, history_id):
        change_dt = datetime.strptime(changed_at, "%Y-%m-%d %H:%M:%S")
        year, month, day = change_dt.year, change_dt.month, change_dt.day
        time_str = change_dt.strftime("%H:%M")
        text = "更换了主轮播图"
        change = {
            "time": time_str,
            "metric": "主轮播图",
            "old": "原图",
            "new": "新图",
            "text": text,
            "type": "main_carousel_image",
            "history_id": history_id,
        }
        rows = self.main_app.db.safe_fetchall(
            "SELECT records_json FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
            (self.prod_id, year, month, day)
        )
        try:
            records = json.loads(rows[0][0]) if rows and rows[0][0] else []
        except Exception:
            records = []
        records.append({"time": time_str, "text": text, "history_id": history_id, "changes": [change]})
        self.main_app.db.safe_execute(
            "INSERT OR REPLACE INTO records (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
            (self.prod_id, year, month, day, json.dumps(records, ensure_ascii=False))
        )
        if getattr(self.main_app, "year", None) == year and getattr(self.main_app, "month", None) == month:
            for row, row_prod_id in getattr(self.main_app, "row_data_map", {}).items():
                if row_prod_id == self.prod_id:
                    self.main_app.render_records_for_product(row, self.prod_id, self.main_app.table.columnCount() - 1)
                    break

    def _record_main_image_history_id(self, record):
        if not isinstance(record, dict):
            return None
        history_id = record.get("history_id")
        if history_id:
            return history_id
        for change in record.get("changes", []) or []:
            if isinstance(change, dict) and change.get("type") == "main_carousel_image" and change.get("history_id"):
                return change.get("history_id")
        return None

    def _is_main_image_record(self, record):
        if not isinstance(record, dict):
            return False
        if self._record_main_image_history_id(record):
            return True
        for change in record.get("changes", []) or []:
            if isinstance(change, dict) and change.get("type") == "main_carousel_image":
                return True
        return False

    def _assign_history_id_to_record(self, record, history_id):
        record["history_id"] = history_id
        for change in record.get("changes", []) or []:
            if isinstance(change, dict) and change.get("type") == "main_carousel_image":
                change["history_id"] = history_id

    def _main_image_record_payload(self, changed_at, history_id):
        dt = self._parse_history_datetime(changed_at) or datetime.now()
        time_str = dt.strftime("%H:%M")
        text = "更换了主轮播图"
        change = {
            "time": time_str,
            "metric": "主轮播图",
            "old": "原图",
            "new": "新图",
            "text": text,
            "type": "main_carousel_image",
            "history_id": history_id,
        }
        return {"time": time_str, "text": text, "history_id": history_id, "changes": [change]}

    def _ensure_main_image_history_record_links(self):
        histories = self.main_app.db.safe_fetchall(
            "SELECT id, changed_at FROM product_image_history WHERE product_id=? ORDER BY changed_at ASC, id ASC",
            (self.prod_id,)
        )
        if not histories:
            return

        history_by_id = {history_id: changed_at for history_id, changed_at in histories}
        history_match = {}
        for history_id, changed_at in histories:
            dt = self._parse_history_datetime(changed_at)
            if dt:
                history_match.setdefault((dt.year, dt.month, dt.day, dt.strftime("%H:%M")), []).append(history_id)

        rows = self.main_app.db.safe_fetchall(
            "SELECT year, month, day, records_json FROM records WHERE product_id=?",
            (self.prod_id,)
        )
        used_ids = set()
        changed_days = {}
        for year, month, day, records_json in rows:
            try:
                records = json.loads(records_json) if records_json else []
            except Exception:
                records = []
            new_records = []
            changed = False
            for record in records:
                if not self._is_main_image_record(record):
                    new_records.append(record)
                    continue
                history_id = self._record_main_image_history_id(record)
                if history_id in history_by_id:
                    used_ids.add(history_id)
                    self._assign_history_id_to_record(record, history_id)
                    new_records.append(record)
                    continue
                key = (year, month, day, record.get("time", ""))
                candidates = [hid for hid in history_match.get(key, []) if hid not in used_ids]
                if candidates:
                    history_id = candidates[0]
                    used_ids.add(history_id)
                    self._assign_history_id_to_record(record, history_id)
                    new_records.append(record)
                    changed = True
                else:
                    changed = True
            if changed:
                changed_days[(year, month, day)] = new_records

        for history_id, changed_at in histories:
            if history_id in used_ids:
                continue
            dt = self._parse_history_datetime(changed_at)
            if not dt:
                continue
            key = (dt.year, dt.month, dt.day)
            if key not in changed_days:
                existing_rows = self.main_app.db.safe_fetchall(
                    "SELECT records_json FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                    (self.prod_id, dt.year, dt.month, dt.day)
                )
                try:
                    changed_days[key] = json.loads(existing_rows[0][0]) if existing_rows and existing_rows[0][0] else []
                except Exception:
                    changed_days[key] = []
            changed_days[key].append(self._main_image_record_payload(changed_at, history_id))

        for (year, month, day), records in changed_days.items():
            self._write_records_for_day(year, month, day, records)

    def _write_records_for_day(self, year, month, day, records):
        records = self._sort_records_by_time(records)
        if records:
            self.main_app.db.safe_execute(
                "INSERT OR REPLACE INTO records (product_id, year, month, day, records_json) VALUES (?, ?, ?, ?, ?)",
                (self.prod_id, year, month, day, json.dumps(records, ensure_ascii=False))
            )
        else:
            self.main_app.db.safe_execute(
                "DELETE FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                (self.prod_id, year, month, day)
            )
        if getattr(self.main_app, "year", None) == year and getattr(self.main_app, "month", None) == month:
            for row, row_prod_id in getattr(self.main_app, "row_data_map", {}).items():
                if row_prod_id == self.prod_id:
                    self.main_app.render_records_for_product(row, self.prod_id, self.main_app.table.columnCount() - 1)
                    break

    def _sort_records_by_time(self, records):
        def key(record):
            text = str(record.get("time", "") if isinstance(record, dict) else "")
            try:
                hour, minute = text.split(":", 1)
                return (int(hour), int(minute))
            except Exception:
                return (99, 99)
        return sorted(records or [], key=key)

    def _remove_main_image_operation_record(self, history_id):
        rows = self.main_app.db.safe_fetchall(
            "SELECT year, month, day, records_json FROM records WHERE product_id=?",
            (self.prod_id,)
        )
        for year, month, day, records_json in rows:
            try:
                records = json.loads(records_json) if records_json else []
            except Exception:
                records = []
            new_records = [record for record in records if self._record_main_image_history_id(record) != history_id]
            if len(new_records) != len(records):
                self._write_records_for_day(year, month, day, new_records)

    def _sync_main_image_operation_record_time(self, history_id, changed_at):
        dt = self._parse_history_datetime(changed_at)
        if not dt:
            return
        new_time = dt.strftime("%H:%M")
        target_key = (dt.year, dt.month, dt.day)
        rows = self.main_app.db.safe_fetchall(
            "SELECT year, month, day, records_json FROM records WHERE product_id=?",
            (self.prod_id,)
        )
        moved_records = []
        changed_days = {}
        for year, month, day, records_json in rows:
            try:
                records = json.loads(records_json) if records_json else []
            except Exception:
                records = []
            kept_records = []
            for record in records:
                if self._record_main_image_history_id(record) == history_id:
                    record["time"] = new_time
                    record["history_id"] = history_id
                    for change in record.get("changes", []) or []:
                        if isinstance(change, dict) and change.get("type") == "main_carousel_image":
                            change["time"] = new_time
                            change["history_id"] = history_id
                    moved_records.append(record)
                else:
                    kept_records.append(record)
            if len(kept_records) != len(records):
                changed_days[(year, month, day)] = kept_records

        if not moved_records:
            moved_records.append(self._main_image_record_payload(changed_at, history_id))

        if target_key not in changed_days:
            existing_rows = self.main_app.db.safe_fetchall(
                "SELECT records_json FROM records WHERE product_id=? AND year=? AND month=? AND day=?",
                (self.prod_id, dt.year, dt.month, dt.day)
            )
            try:
                changed_days[target_key] = json.loads(existing_rows[0][0]) if existing_rows and existing_rows[0][0] else []
            except Exception:
                changed_days[target_key] = []
        changed_days[target_key].extend(moved_records)

        for (year, month, day), records in changed_days.items():
            self._write_records_for_day(year, month, day, records)

    def update_roi_display(self, margin_rate=None):
        self.update_margin_display()
        return

    def set_image(self, path):
        if path and path != 'None':
            try:
                original_pixmap = QPixmap(path)
                if not original_pixmap.isNull():
                    container_size = 60
                    if original_pixmap.width() > container_size or original_pixmap.height() > container_size:
                        pixmap = original_pixmap.scaled(container_size, container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    else:
                        pixmap = original_pixmap
                    self.img_label.setPixmap(pixmap)
                    self.img_label.setAlignment(Qt.AlignCenter)
                else:
                    self.img_label.setText("图片\n加载失败")
                    self.img_label.setAlignment(Qt.AlignCenter)
            except Exception:
                self.img_label.setText("图片\n加载失败")
                self.img_label.setAlignment(Qt.AlignCenter)
        else:
            self.img_label.setText("无图片")
            self.img_label.setAlignment(Qt.AlignCenter)

    def change_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择商品主图", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            try:
                with open(path, 'rb') as f:
                    image_data = f.read()
                self._save_product_main_image(image_data, "file")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"更新图片失败: {e}")

    def set_image_from_data(self, image_data):
        if image_data:
            try:
                container_size = max(1, self.img_label.width() - 2)
                image_bytes = bytes(image_data)
                key = ("product_image", self.prod_id, len(image_bytes), image_bytes[:32], image_bytes[-32:], container_size)

                def make_pixmap():
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_bytes)
                    if pixmap.isNull():
                        return pixmap
                    pixmap = pixmap.scaled(
                        container_size, container_size,
                        Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                    )
                    x = max(0, (pixmap.width() - container_size) // 2)
                    y = max(0, (pixmap.height() - container_size) // 2)
                    return pixmap.copy(x, y, container_size, container_size)

                pixmap = _cached_pixmap(key, make_pixmap)
                if not pixmap.isNull():
                    self.img_label.setPixmap(pixmap)
                    self.img_label.setAlignment(Qt.AlignCenter)
                else:
                    self.img_label.setText("图片\n加载失败")
                    self.img_label.setAlignment(Qt.AlignCenter)
            except Exception:
                self.img_label.setText("图片\n加载失败")
                self.img_label.setAlignment(Qt.AlignCenter)
        else:
            self.img_label.setText("无图片")
            self.img_label.setAlignment(Qt.AlignCenter)

    def mouseDoubleClickEvent(self, event):
        if (
            self.display_mode == "bubble"
            and event.button() == Qt.LeftButton
            and hasattr(self.main_app, "open_product_spec_dialog")
        ):
            self.main_app.open_product_spec_dialog(
                self.db, self.prod_id, self.prod_code, self.prod_title, self.main_app
            )
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def delete_product(self):
        append_event(f"ui:delete_product:confirm product_id={self.prod_id}")
        reply = QMessageBox.question(self, "确认", "确定删除该商品及其所有记录吗？")
        if reply == QMessageBox.Yes:
            try:
                append_event(f"ui:delete_product:start product_id={self.prod_id}")
                rows = self.main_app.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.prod_id,))
                store_id = rows[0][0] if rows else None
                self.main_app.db.delete_product_cascade(self.prod_id)
                if hasattr(self.main_app, "update_daily_task_button_badge"):
                    self.main_app.update_daily_task_button_badge()
                if hasattr(self.main_app, "refresh_after_product_deleted"):
                    self.main_app.refresh_after_product_deleted(self.prod_id, store_id)
                else:
                    self.main_app.load_data_safe()
                append_event(f"ui:delete_product:done product_id={self.prod_id}")
            except Exception as e:
                append_exception("ui:delete_product:failed", error=e)
                QMessageBox.warning(self, "错误", f"删除商品失败: {e}")

    def _on_code_click(self, event):
        self.copy_product_id()

    def copy_same_product(self):
        append_event(f"ui:copy_same_product:start product_id={self.prod_id}")
        store_id = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.prod_id,))
        if store_id and store_id[0]:
            self.main_app.add_product(store_id[0][0], copy_from_id=self.prod_id)

    def copy_product_id(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.original_name)
        self.main_app.show_toast(f"✅ 已复制商品ID: {self.original_name}")


class StoreWidget(QWidget):
    """店铺展示控件。"""
    BUBBLE_HEIGHT = 38

    def __init__(self, store_id, store_name, main_app, display_mode="table"):
        super().__init__()
        self.setObjectName("StoreWidget")
        self.display_mode = display_mode
        self.store_id = store_id
        self.store_name = store_name
        self.main_app = main_app
        self.db = main_app.db
        self._store_summary_cache = None
        self._store_foreground = "#fffdf5"
        if display_mode == "bubble":
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setFixedHeight(self.BUBBLE_HEIGHT)
            self.setStyleSheet(
                "#StoreWidget { background-color: #245c3d; border: none; border-radius: 8px; }"
            )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3) if display_mode == "bubble" else layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(12 if display_mode == "bubble" else 5)

        label_widget = QWidget()
        label_layout = QVBoxLayout(label_widget)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(2)

        top_row_widget = QWidget()
        top_row_layout = QHBoxLayout(top_row_widget)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(5)

        self.sync_flag_label = QLabel("")
        self.sync_flag_label.setStyleSheet("background-color: #d4edda; color: #155724; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: bold;")
        self.sync_flag_label.setAlignment(Qt.AlignCenter)
        self.sync_flag_label.hide()

        self.label = QLabel(f" {store_name}")
        self.label.setStyleSheet("background-color: #cfe4c8; color: #20372a; font-weight: bold; padding: 1px 6px; border-radius: 5px;")
        self.label.setWordWrap(False)
        self.label.setCursor(Qt.PointingHandCursor)
        self.label.installEventFilter(self)
        self.label.setToolTip("双击修改店铺名称")

        if display_mode != "bubble":
            top_row_layout.addWidget(self.sync_flag_label)
            top_row_layout.addWidget(self.label)
            top_row_layout.addStretch()

        memo_rows = self.db.safe_fetchall("SELECT memo FROM stores WHERE id=?", (store_id,))
        store_memo = memo_rows[0][0] if memo_rows and memo_rows[0][0] else ""
        if store_memo:
            display_text = store_memo[:30] + "..." if len(store_memo) > 30 else store_memo
            self.memo_label = QLabel(f"📝 {display_text}")
            self.memo_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px 5px;")
            self.memo_label.setWordWrap(True)
            self.memo_label.setCursor(Qt.PointingHandCursor)
            self.memo_label.installEventFilter(self)
        else:
            self.memo_label = QLabel("📝 点击添加备注")
            self.memo_label.setStyleSheet("color: #999; font-size: 11px; padding: 2px 5px; font-style: italic;")
            self.memo_label.setCursor(Qt.PointingHandCursor)
            self.memo_label.installEventFilter(self)

        margin = self.calculate_store_margin()
        if margin is not None:
            self.margin_label = QLabel(f"   综合毛利: {margin:.2f}%")
            self.margin_label.setStyleSheet("background-color: #fdeaa8; padding: 3px 8px; font-size: 12px; color: #e74c3c; font-weight: bold;")
        else:
            self.margin_label = QLabel("   综合毛利: --")
            self.margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")

        display_net_margin = None
        if self._is_real_promotion_mode():
            real_metrics = self.calculate_store_real_promotion_metrics()
            if real_metrics:
                net_profit = real_metrics["net_profit"]
                net_margin = real_metrics["net_margin_pct"]
                display_net_margin = net_margin
                record_date = real_metrics.get("record_date") or ""
                net_orders = float(real_metrics.get("net_orders") or 0)
                profit_color = "#006400" if net_profit > 0 else ("#daa520" if abs(net_profit) < 0.000001 else "#dc143c")
                self.net_margin_label = QLabel(f"{record_date} 推广盈亏: ¥{net_profit:.2f} 净利:{net_margin:.2f}%")
                self.net_margin_label.setStyleSheet(f"background-color: #e8f4f8; padding: 3px 8px; font-size: 12px; color: {profit_color}; font-weight: bold;")
                avg_price = real_metrics.get("avg_price")
                if avg_price is not None:
                    self.avg_price_label = QLabel(f"净成交: {net_orders:.0f}单 真实客单: ¥{avg_price:.2f}")
                    self.avg_price_label.setStyleSheet("background-color: #e8f8f5; padding: 3px 8px; font-size: 12px; color: #27ae60; font-weight: bold;")
                else:
                    self.avg_price_label = QLabel(f"净成交: {net_orders:.0f}单 真实客单: --")
                    self.avg_price_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
            else:
                self.net_margin_label = QLabel("推广盈亏: --")
                self.net_margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
                self.avg_price_label = QLabel("真实客单: --")
                self.avg_price_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
        else:
            net_margin = self.calculate_store_net_margin()
            display_net_margin = net_margin
            if net_margin is not None:
                net_margin_color = self._get_net_margin_color(net_margin)
                self.net_margin_label = QLabel(f"净利率: {net_margin:.2f}%")
                self.net_margin_label.setStyleSheet(f"background-color: #e8f4f8; padding: 3px 8px; font-size: 12px; color: {net_margin_color}; font-weight: bold;")
            else:
                self.net_margin_label = QLabel("净利率: --")
                self.net_margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")

            avg_price = self.calculate_store_avg_price()
            if avg_price is not None:
                self.avg_price_label = QLabel(f"客单价: ¥{avg_price:.2f}")
                self.avg_price_label.setStyleSheet("background-color: #e8f8f5; padding: 3px 8px; font-size: 12px; color: #27ae60; font-weight: bold;")
            else:
                self.avg_price_label = QLabel("客单价: --")
                self.avg_price_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")

        self.task_ratio_widget = QWidget(self)
        task_ratio_layout = QHBoxLayout(self.task_ratio_widget)
        task_ratio_layout.setContentsMargins(0, 0, 0, 0)
        task_ratio_layout.setSpacing(4)
        self.garbage_ratio_badge = QLabel("垃圾")
        self.garbage_ratio_badge.setFixedSize(26, 26)
        self.garbage_ratio_badge.setAlignment(Qt.AlignCenter)
        self.garbage_ratio_badge.setStyleSheet(
            "color:white; background:#dc2626; border:1px solid #111; "
            "border-radius:13px; font-size:10px; font-weight:bold;"
        )
        self.garbage_ratio_badge.setToolTip("垃圾链接占比")
        self.garbage_ratio_label = QLabel()
        self.waste_ratio_badge = QLabel("废物")
        self.waste_ratio_badge.setFixedSize(26, 26)
        self.waste_ratio_badge.setAlignment(Qt.AlignCenter)
        self.waste_ratio_badge.setStyleSheet(
            "color:white; background:#7c2d12; border:1px solid #111; "
            "border-radius:13px; font-size:10px; font-weight:bold;"
        )
        self.waste_ratio_badge.setToolTip("废物链接占比")
        self.waste_ratio_label = QLabel()
        task_ratio_layout.addWidget(self.garbage_ratio_badge)
        task_ratio_layout.addWidget(self.garbage_ratio_label)
        task_ratio_layout.addSpacing(4)
        task_ratio_layout.addWidget(self.waste_ratio_badge)
        task_ratio_layout.addWidget(self.waste_ratio_label)
        self.task_ratio_widget.hide()

        if display_mode == "bubble":
            background = _net_margin_background_color(display_net_margin)
            self._store_foreground = "#171b18" if qGray(background.rgb()) >= 145 else "#fffdf5"
            self.setStyleSheet(
                f"#StoreWidget {{ background-color: {background.name()}; border: none; border-radius: 8px; }}"
            )
            self._apply_bubble_store_label_styles()
            layout.addWidget(self.sync_flag_label)
            layout.addWidget(self.label)
            layout.addWidget(self.memo_label, 1)
            layout.addWidget(self.margin_label)
            layout.addWidget(self.net_margin_label)
            layout.addWidget(self.avg_price_label)
            layout.addWidget(self.task_ratio_widget)
        else:
            label_layout.addWidget(top_row_widget)
            label_layout.addWidget(self.memo_label)
            label_layout.addWidget(self.margin_label)
            label_layout.addWidget(self.net_margin_label)
            label_layout.addWidget(self.avg_price_label)
            label_layout.addWidget(self.task_ratio_widget)
            layout.addWidget(label_widget)

        self._refresh_garbage_ratio_label()
        if display_mode == "bubble":
            self._apply_bubble_store_label_styles()

    def _apply_bubble_store_label_styles(self):
        if self.display_mode != "bubble":
            return
        for label in (
            self.sync_flag_label,
            self.label,
            self.memo_label,
            self.margin_label,
            self.net_margin_label,
            self.avg_price_label,
            self.garbage_ratio_label,
            self.waste_ratio_label,
        ):
            foreground = "#111111" if label in (self.garbage_ratio_label, self.waste_ratio_label) else self._store_foreground
            label.setStyleSheet(
                f"background: transparent; color: {foreground}; border: none; "
                "padding: 0px 4px; font-size: 14px; font-weight: bold;"
            )
            label.setWordWrap(False)
        self.label.setStyleSheet(
            f"background: transparent; color: {self._store_foreground}; border: none; "
            "padding: 0px 4px; font-size: 15px; font-weight: bold;"
        )
        self.memo_label.setMaximumWidth(320)

    def refresh_bubble_metrics(self):
        if self.display_mode != "bubble":
            return
        display_net_margin = None
        if self._is_real_promotion_mode():
            metrics = self.calculate_store_real_promotion_metrics()
            if metrics:
                display_net_margin = metrics["net_margin_pct"]
                avg_price = metrics.get("avg_price")
                self.net_margin_label.setText(
                    f'{metrics.get("record_date") or ""} 推广盈亏: ¥{metrics["net_profit"]:.2f} '
                    f'净利:{display_net_margin:.2f}%'
                )
                self.avg_price_label.setText(
                    f'净成交: {float(metrics.get("net_orders") or 0):.0f}单 '
                    f'真实客单: {f"¥{avg_price:.2f}" if avg_price is not None else "--"}'
                )
            else:
                self.net_margin_label.setText("推广盈亏: --")
                self.avg_price_label.setText("真实客单: --")
        else:
            self._store_summary_cache = None
            display_net_margin = self.calculate_store_net_margin()
            avg_price = self.calculate_store_avg_price()
            self.net_margin_label.setText(
                f"净利率: {display_net_margin:.2f}%" if display_net_margin is not None else "净利率: --"
            )
            self.avg_price_label.setText(
                f"客单价: ¥{avg_price:.2f}" if avg_price is not None else "客单价: --"
            )
        background = _net_margin_background_color(display_net_margin)
        self._store_foreground = "#171b18" if qGray(background.rgb()) >= 145 else "#fffdf5"
        self.setStyleSheet(
            f"#StoreWidget {{ background-color: {background.name()}; border: none; border-radius: 8px; }}"
        )
        self._refresh_garbage_ratio_label()
        self._apply_bubble_store_label_styles()

    def contextMenuEvent(self, event):
        self.show_store_context_menu(event.globalPos())
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_store_margin_dialog()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def show_store_context_menu(self, global_pos):
        menu = QMenu(self)
        _enlarge_context_menu(menu)
        add_action = menu.addAction("添加链接")
        pdd_code_fetch_action = menu.addAction("抓取添加编码")
        pdd_price_fetch_action = menu.addAction("抓取价格管理")
        pdd_promotion_fetch_action = menu.addAction("抓取推广状态")
        promotion_data_action = menu.addAction("推广数据分析")
        record_action = menu.addAction("店铺操作记录")
        delete_action = menu.addAction("删除店铺")
        selected = menu.exec_(global_pos)
        if selected == add_action:
            self.add_product()
        elif selected == pdd_code_fetch_action and hasattr(self.main_app, "open_pdd_code_fetch_for_store"):
            self.main_app.open_pdd_code_fetch_for_store(self.store_id)
        elif selected == pdd_price_fetch_action and hasattr(self.main_app, "open_pdd_price_fetch_for_store"):
            self.main_app.open_pdd_price_fetch_for_store(self.store_id)
        elif selected == pdd_promotion_fetch_action and hasattr(self.main_app, "open_pdd_promotion_status_fetch_for_store"):
            self.main_app.open_pdd_promotion_status_fetch_for_store(self.store_id)
        elif selected == promotion_data_action and hasattr(self.main_app, "open_promotion_data_for_store"):
            self.main_app.open_promotion_data_for_store(self.store_id)
        elif selected == record_action:
            if hasattr(self.main_app, "open_store_record_window"):
                self.main_app.open_store_record_window(self.store_id)
        elif selected == delete_action:
            self.delete_store()

    def calculate_store_margin(self):
        return self._calculate_store_summary()["margin"]

    def _refresh_garbage_ratio_label(self):
        total_rows = self.db.safe_fetchall(
            """SELECT COUNT(*) FROM products WHERE store_id=?
               AND COALESCE(is_archived, 0)=0""",
            (self.store_id,),
        )
        task_rows = self.db.safe_fetchall(
            """SELECT
                   COUNT(DISTINCT CASE WHEN dt.task_content LIKE '【垃圾链接】%' THEN dt.product_id END),
                   COUNT(DISTINCT CASE WHEN dt.task_content LIKE '【废物链接】%' THEN dt.product_id END)
               FROM daily_tasks dt
               JOIN products p ON p.id=dt.product_id
               WHERE dt.store_id=? AND dt.is_completed=0
                 AND COALESCE(p.is_archived, 0)=0 AND COALESCE(p.is_violation, 0)=0""",
            (self.store_id,),
        )
        total = int(total_rows[0][0] or 0) if total_rows else 0
        garbage = int(task_rows[0][0] or 0) if task_rows else 0
        waste = int(task_rows[0][1] or 0) if task_rows else 0
        if not garbage and not waste:
            self.task_ratio_widget.hide()
            return
        self.garbage_ratio_label.setText(
            f"{garbage}/{total}（{garbage / total * 100:.1f}%）" if total else "0/0"
        )
        self.waste_ratio_label.setText(
            f"{waste}/{total}（{waste / total * 100:.1f}%）" if total else "0/0"
        )
        self.garbage_ratio_badge.setVisible(bool(garbage))
        self.garbage_ratio_label.setVisible(bool(garbage))
        self.waste_ratio_badge.setVisible(bool(waste))
        self.waste_ratio_label.setVisible(bool(waste))
        if self.display_mode != "bubble":
            self.garbage_ratio_label.setStyleSheet("background:#fff1f2; color:#111; padding:3px 8px; font-size:12px; font-weight:bold;")
            self.waste_ratio_label.setStyleSheet("background:#fff7ed; color:#111; padding:3px 8px; font-size:12px; font-weight:bold;")
        self.task_ratio_widget.show()

    def _calculate_store_summary(self):
        if self._store_summary_cache is not None:
            return self._store_summary_cache
        summary = {"margin": None, "net_margin": None, "avg_price": None}
        try:
            products = self.db.safe_fetchall(
                """SELECT id, store_weight, current_roi, return_rate, is_natural_flow,
                          is_sitewide_managed, COALESCE(roi_input_mode, 'roi'),
                          COALESCE(transaction_bid, 0)
                   FROM products WHERE store_id=? AND COALESCE(is_archived, 0)=0
                     AND COALESCE(is_violation, 0)=0""",
                (self.store_id,),
            )
            store_rows = self.db.safe_fetchall("SELECT sitewide_roi FROM stores WHERE id=?", (self.store_id,))
            sitewide_roi = float(store_rows[0][0] or 0) if store_rows else 0.0
            total_weight = total_margin = total_net_margin = total_price = 0.0
            net_weight = 0.0
            for prod_id, weight, roi, return_rate, natural, sitewide, input_mode, bid in products:
                weight = float(weight or 0)
                if weight <= 0:
                    continue
                metrics = self.main_app.get_product_gross_margin_metrics(prod_id)
                margin = metrics.get("gross_margin_pct")
                avg_price = float(metrics.get("avg_final_price") or 0)
                if margin is None:
                    continue
                margin = float(margin)
                total_margin += margin * weight
                total_price += avg_price * weight
                total_weight += weight
                effective_roi = sitewide_roi if sitewide and not natural else float(roi or 0)
                if input_mode == "bid" and not sitewide and not natural and float(bid or 0) > 0 and avg_price > 0:
                    effective_roi = avg_price / float(bid)
                margin_decimal = margin / 100
                if natural:
                    net_margin = (margin_decimal * (1 - float(return_rate or 0) / 100) - 0.006) * 100
                elif effective_roi > 0:
                    net_margin = (margin_decimal * (1 - float(return_rate or 0) / 100) - 0.006 - 1 / effective_roi) * 100
                else:
                    continue
                total_net_margin += net_margin * weight
                net_weight += weight
            if total_weight > 0:
                summary["margin"] = total_margin / total_weight
                summary["avg_price"] = total_price / total_weight
            if net_weight > 0:
                summary["net_margin"] = total_net_margin / net_weight
        except Exception as e:
            print(f"计算店铺汇总失败: {e}")
        self._store_summary_cache = summary
        return summary

    def _is_real_promotion_mode(self):
        return (
            hasattr(self.main_app, "is_real_promotion_data_mode")
            and self.main_app.is_real_promotion_data_mode()
            and hasattr(self.main_app, "get_latest_promotion_data")
        )

    def _calculate_product_margin_decimal(self, prod_id, product_code=None, order_date=None):
        specs = self.db.safe_fetchall(
            """SELECT spec_code, sale_price, weight_percent FROM product_specs
               WHERE product_id=? AND COALESCE(is_temporarily_off_shelf, 0)=0""",
            (prod_id,)
        )
        if not specs:
            return None
        product_rows = self.db.safe_fetchall(
            "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
            (prod_id,)
        )
        coupon = (product_rows[0][0] or 0) if product_rows else 0
        new_customer = (product_rows[0][1] or 0) if product_rows else 0
        max_discount = max(coupon, new_customer)

        def fetch_order_weights(target_date):
            if not product_code or not target_date:
                return {}
            rows = self.db.safe_fetchall(
                """
                SELECT spec_code, COALESCE(SUM(order_count), 0)
                FROM imported_orders
                WHERE store_id=? AND product_id=? AND order_date=?
                GROUP BY spec_code
                """,
                (self.store_id, product_code, target_date),
            )
            return {
                spec_code: float(order_count or 0)
                for spec_code, order_count in rows
                if float(order_count or 0) > 0
            }

        order_weights = fetch_order_weights(order_date)

        margin_by_spec = {}
        manual_weights = {}
        for spec_code, sale_price, weight in specs:
            if sale_price is None or sale_price <= 0:
                continue
            cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
            cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
            final_price = sale_price - max_discount
            if final_price > 0 and cost > 0:
                margin_by_spec[spec_code] = (final_price - cost) / final_price
                if weight and weight > 0:
                    manual_weights[spec_code] = float(weight)

        def weighted_margin(weights):
            total_weight = 0.0
            total_margin = 0.0
            for spec_code, weight in weights.items():
                margin = margin_by_spec.get(spec_code)
                if margin is None or weight <= 0:
                    continue
                total_margin += margin * weight
                total_weight += weight
            if total_weight <= 0:
                return None
            return total_margin / total_weight

        return (
            weighted_margin(order_weights)
            or weighted_margin(manual_weights)
            or (sum(margin_by_spec.values()) / len(margin_by_spec) if margin_by_spec else None)
        )

    def calculate_store_real_promotion_metrics(self):
        try:
            products = self.db.safe_fetchall(
                """SELECT id, name, is_natural_flow FROM products WHERE store_id=?
                   AND COALESCE(is_archived, 0)=0 AND COALESCE(is_violation, 0)=0""",
                (self.store_id,)
            )
            if not products:
                return None
            total_net_amount = 0.0
            total_cost = 0.0
            total_net_orders = 0.0
            total_net_profit = 0.0
            matched_count = 0
            product_data = []
            latest_store_date = ""
            for prod_id, product_code, is_natural_flow in products:
                data = self.main_app.get_latest_promotion_data(self.store_id, product_code)
                record_date = str(data.get("record_date") or "") if data else ""
                if not record_date:
                    continue
                latest_store_date = max(latest_store_date, record_date)
                product_data.append((prod_id, product_code, data, record_date))

            if not latest_store_date:
                return None

            for prod_id, product_code, data, record_date in product_data:
                if record_date != latest_store_date:
                    continue
                margin_decimal = self._calculate_product_margin_decimal(prod_id, product_code, record_date)
                if margin_decimal is None:
                    margin_decimal = 0.0
                net_amount = float(data.get("net_transaction_amount") or 0)
                cost = float(data.get("cost") or 0)
                net_orders = float(data.get("net_orders") or 0)
                if data.get("net_profit") is not None:
                    net_profit = float(data.get("net_profit"))
                else:
                    tech_fee = net_amount * 0.006
                    net_profit = net_amount * margin_decimal - cost - tech_fee
                total_net_amount += net_amount
                total_cost += cost
                total_net_orders += net_orders
                total_net_profit += net_profit
                matched_count += 1
            if matched_count <= 0:
                return None
            if total_net_amount > 0:
                net_margin_pct = total_net_profit / total_net_amount * 100
            else:
                net_margin_pct = -100.0 if total_cost > 0 else 0.0
            avg_price = total_net_amount / total_net_orders if total_net_orders > 0 else None
            return {
                "net_profit": total_net_profit,
                "net_margin_pct": net_margin_pct,
                "avg_price": avg_price,
                "net_orders": total_net_orders,
                "net_amount": total_net_amount,
                "cost": total_cost,
                "record_date": latest_store_date,
            }
        except Exception as e:
            print(f"计算店铺真实推广指标失败: {e}")
            return None

    def calculate_store_net_margin(self):
        return self._calculate_store_summary()["net_margin"]

    def calculate_store_avg_price(self):
        return self._calculate_store_summary()["avg_price"]

    def _get_net_margin_color(self, net_margin_pct):
        if net_margin_pct > 5:
            return "#006400"
        elif net_margin_pct > 1:
            return "#27ae60"
        elif net_margin_pct >= -2:
            return "#daa520"
        elif net_margin_pct >= -5:
            return "#ff8c00"
        elif net_margin_pct >= -8:
            return "#dc143c"
        else:
            return "#8b0000"

    def delete_store(self):
        if hasattr(self.main_app, "delete_store_by_id"):
            self.main_app.delete_store_by_id(self.store_id, self.store_name)

    def add_product(self):
        self.main_app.add_product(self.store_id)

    def eventFilter(self, obj, event):
        if sip.isdeleted(self) or sip.isdeleted(obj):
            return False
        if getattr(self, "_disposing", False):
            return False
        if obj == self.label:
            if event.type() == QEvent.ContextMenu:
                self.show_store_context_menu(event.globalPos())
                return True
            if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self.rename_store()
                return True
        elif hasattr(self, 'memo_label') and obj == self.memo_label and event.type() == QEvent.MouseButtonDblClick:
            self.edit_store_memo()
            return True
        return False

    def rename_store(self):
        rows = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (self.store_id,))
        current_name = rows[0][0] if rows and rows[0][0] else str(self.store_name).strip()
        new_name, ok = QInputDialog.getText(
            self,
            "修改店铺名称",
            "店铺名称：",
            QLineEdit.Normal,
            current_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "提示", "店铺名称不能为空")
            return
        if new_name == current_name:
            return
        duplicate = self.db.safe_fetchall(
            "SELECT id FROM stores WHERE name=? AND id<>? LIMIT 1",
            (new_name, self.store_id),
        )
        if duplicate:
            QMessageBox.warning(self, "提示", "已存在同名店铺，请换一个名称")
            return
        try:
            self.db.safe_execute("UPDATE stores SET name=? WHERE id=?", (new_name, self.store_id))
            self.store_name = new_name
            self.label.setText(f" {new_name}")
            if hasattr(self.main_app, "refresh_after_store_renamed"):
                self.main_app.refresh_after_store_renamed(self.store_id, new_name)
            self.main_app.show_toast(f"✅ 店铺名称已修改为：{new_name}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"修改店铺名称失败: {e}")

    def edit_store_memo(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("💡 店铺备注/运营指导大纲")
        dialog.resize(500, 350)
        layout = QVBoxLayout(dialog)
        hint = QLabel("💡 此内容将作为店铺运营指导大纲，自动应用到所有AI功能调用中（包括利润分析建议、AI优化规格等）")
        hint.setStyleSheet("color: #666; font-size: 12px; padding: 5px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        current_memo = ""
        memo_rows = self.db.safe_fetchall("SELECT memo FROM stores WHERE id=?", (self.store_id,))
        if memo_rows and memo_rows[0][0]:
            current_memo = memo_rows[0][0]
        text_edit = QTextEdit()
        text_edit.setPlainText(current_memo)
        text_edit.setPlaceholderText("输入店铺运营指导大纲...")
        text_edit.setMaximumHeight(200)
        layout.addWidget(text_edit)
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 保存")
        btn_save.setStyleSheet("QPushButton { background-color: #27ae60; color: white; padding: 8px 20px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #219a52; }")
        btn_cancel = QPushButton("取消")
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        def save_memo():
            store_memo = text_edit.toPlainText().strip()
            self.db.safe_execute("UPDATE stores SET memo=? WHERE id=?", (store_memo, self.store_id))
            if store_memo:
                display_text = store_memo[:30] + "..." if len(store_memo) > 30 else store_memo
                self.memo_label.setText(f"📝 {display_text}")
                self.memo_label.setStyleSheet("color: #e74c3c; font-size: 11px; padding: 2px 5px; font-weight: bold;")
            else:
                self.memo_label.setText("📝 点击添加备注")
                self.memo_label.setStyleSheet("color: #999; font-size: 11px; padding: 2px 5px; font-style: italic;")
            self._apply_bubble_store_label_styles()
            self.main_app.show_toast("✅ 店铺备注已更新")
            dialog.accept()

        btn_save.clicked.connect(save_memo)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec_()

    def open_store_margin_dialog(self):
        """通过 main_app 打开店铺毛利对话框，避免 widgets 依赖主模块的 Dialog"""
        self.main_app.open_store_margin_dialog(self.store_id, self.store_name)

    def refresh_margin_display(self):
        self._store_summary_cache = None
        margin = self.calculate_store_margin()
        if margin is not None:
            self.margin_label.setText(f"   综合毛利: {margin:.2f}%")
            self.margin_label.setStyleSheet("background-color: #fdeaa8; padding: 3px 8px; font-size: 12px; color: #e74c3c; font-weight: bold;")
        else:
            self.margin_label.setText("   综合毛利: --")
            self.margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
        self._refresh_garbage_ratio_label()
        self._apply_bubble_store_label_styles()
        self.margin_label.show()

    def refresh_sync_flag(self):
        """刷新权重已同步标签显示"""
        imported_data = self.db.safe_fetchall(
            "SELECT COUNT(*) FROM imported_orders WHERE store_id=?",
            (self.store_id,)
        )
        has_imported = imported_data and imported_data[0][0] > 0 if imported_data else False
        synced_data = self.db.safe_fetchall(
            "SELECT weight_synced FROM stores WHERE id=?",
            (self.store_id,)
        )
        is_synced = synced_data and synced_data[0][0] == 1 if synced_data else False
        if has_imported and is_synced:
            self.sync_flag_label.setText("✅权重已同步")
            self.sync_flag_label.show()
        else:
            self.sync_flag_label.setText("")
            self.sync_flag_label.hide()


class RecordRow(QWidget):
    """单条操作记录的输入行"""
    def __init__(self, time_str="", text="", with_task_buttons=False, parent_dialog=None):
        super().__init__()
        self.parent_dialog = parent_dialog
        self.with_task_buttons = with_task_buttons

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        row1 = QWidget()
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(2, 1, 2, 1)
        row1_layout.setSpacing(3)

        time_label = QLabel("🕐")
        time_label.setFixedWidth(20)
        row1_layout.addWidget(time_label)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFixedWidth(55)
        if time_str:
            try:
                self.time_edit.setTime(QTime.fromString(time_str, "HH:mm"))
            except Exception:
                self.time_edit.setTime(QTime.currentTime())
        else:
            self.time_edit.setTime(QTime.currentTime())
        row1_layout.addWidget(self.time_edit)

        text_label = QLabel("📝")
        text_label.setFixedWidth(20)
        row1_layout.addWidget(text_label)

        self.text_edit = QTextEdit(text)
        self.text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text_edit.setMinimumHeight(30)
        self.text_edit.setMaximumHeight(60)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        row1_layout.addWidget(self.text_edit, 1)

        self.btn_del = QPushButton("🗑")
        self.btn_del.setFixedSize(22, 22)
        self.btn_del.setStyleSheet("padding: 0px; border: none; background: transparent;")
        self.btn_del.clicked.connect(self.on_delete_clicked)
        row1_layout.addWidget(self.btn_del)

        main_layout.addWidget(row1)

        if with_task_buttons:
            row2 = QWidget()
            row2_layout = QHBoxLayout(row2)
            row2_layout.setContentsMargins(2, 1, 2, 1)
            row2_layout.setSpacing(8)

            self.chk_task = QCheckBox("☑️ 任务")
            self.chk_task.setFixedWidth(70)
            row2_layout.addWidget(self.chk_task)

            self.chk_reminder = QCheckBox("🔔 提醒")
            self.chk_reminder.setFixedWidth(70)
            self.chk_reminder.stateChanged.connect(self.on_reminder_toggled)
            row2_layout.addWidget(self.chk_reminder)

            date_label = QLabel("📅")
            date_label.setFixedWidth(20)
            row2_layout.addWidget(date_label)

            tomorrow = QDate.currentDate().addDays(1)
            self.reminder_date = QDateEdit()
            self.reminder_date.setCalendarPopup(True)
            self.reminder_date.setDate(tomorrow)
            self.reminder_date.setDisplayFormat("yyyy-MM-dd")
            self.reminder_date.setFixedWidth(105)
            self.reminder_date.setVisible(False)
            row2_layout.addWidget(self.reminder_date)

            time_label2 = QLabel("⏰")
            time_label2.setFixedWidth(20)
            row2_layout.addWidget(time_label2)

            self.reminder_time = QTimeEdit()
            self.reminder_time.setDisplayFormat("HH:mm")
            self.reminder_time.setFixedWidth(55)
            self.reminder_time.setTime(QTime.currentTime())
            self.reminder_time.setVisible(False)
            row2_layout.addWidget(self.reminder_time)

            row2_layout.addStretch()

            main_layout.addWidget(row2)

    def on_reminder_toggled(self, state):
        if hasattr(self, 'reminder_date'):
            self.reminder_date.setVisible(state == Qt.Checked)
        if hasattr(self, 'reminder_time'):
            self.reminder_time.setVisible(state == Qt.Checked)

    def on_delete_clicked(self):
        self.deleteLater()

    def get_data(self):
        data = {"time": self.time_edit.time().toString("HH:mm"), "text": self.text_edit.toPlainText().strip()}
        if self.with_task_buttons:
            data["add_task"] = self.chk_task.isChecked()
            data["add_reminder"] = self.chk_reminder.isChecked()
            if data["add_reminder"]:
                data["reminder_datetime"] = f"{self.reminder_date.date().toString('yyyy-MM-dd')} {self.reminder_time.time().toString('HH:mm')}"
        return data


class InPlaceEditor(QWidget):
    """原地编辑器"""
    def __init__(self, records, save_callback, cancel_callback):
        super().__init__()
        self.save_callback = save_callback
        self.cancel_callback = cancel_callback
        self.rows = []
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.scroll_widget)
        for rec in records:
            self.add_row(rec.get("time", ""), rec.get("text", ""))
        if not records:
            self.add_row()
        bottom_layout = QHBoxLayout()
        btn_add = QPushButton("+ 加一行")
        btn_add.clicked.connect(lambda: self.add_row())
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.cancel_callback)
        bottom_layout.addWidget(btn_add)
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_save)
        bottom_layout.addWidget(btn_cancel)
        main_layout.addWidget(self.scroll)
        main_layout.addLayout(bottom_layout)
        self.setStyleSheet("background-color: #f9f9f9; border: 1px solid #4a90e2;")

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
        try:
            self.save_callback(data)
            self.hide()
        except Exception as e:
            print(f"保存回调出错：{e}")

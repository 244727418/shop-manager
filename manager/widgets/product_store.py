# -*- coding: utf-8 -*-
"""
商品与店铺相关 UI 组件：ProductWidget、StoreWidget、RecordRow、InPlaceEditor
"""
import os
import json
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QApplication, QScrollArea, QTextEdit,
    QTimeEdit, QDialog, QSizePolicy, QCheckBox, QDateEdit, QLayout,
    QMenu, QAction
)
from PyQt5.QtCore import Qt, QEvent, QTime, QSize, QDate, QBuffer, QByteArray, QIODevice, QTimer
from PyQt5.QtGui import QPixmap, QIcon


def _icons_dir():
    """icons 在 shop_manager/icons，本模块在 shop_manager/widgets/"""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")


class ProductWidget(QWidget):
    """左侧冻结列中的商品展示控件"""
    def __init__(self, prod_id, prod_code, prod_title, image_data, main_app):
        super().__init__()
        self.prod_id = prod_id
        self.prod_code = prod_code
        self.prod_title = prod_title
        self.main_app = main_app
        self.db = main_app.db
        self.setObjectName("ProductWidget")
        self._search_highlight_active = False
        self._suppress_next_code_click = False
        self._code_click_timer = QTimer(self)
        self._code_click_timer.setSingleShot(True)
        self._code_click_timer.timeout.connect(self.copy_product_id)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 2, 5, 2)
        main_layout.setSpacing(6)

        img_container = QWidget()
        img_container.setFixedWidth(77)
        img_container.installEventFilter(self)
        img_layout = QVBoxLayout(img_container)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(2)

        self.img_label = QLabel()
        self.img_label.setFixedSize(72, 72)
        self.img_label.setStyleSheet("border: 1px solid #ddd; border-radius: 4px; padding: 0px;")
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMouseTracking(True)
        self.img_label.setFocusPolicy(Qt.StrongFocus)
        self.img_label.setToolTip("Ctrl+V 粘贴换图，双击查看大图")
        self.img_label.installEventFilter(self)
        self.set_image_from_data(image_data)

        self.category_label = QLabel()
        self.category_label.setAlignment(Qt.AlignCenter)
        self.category_label.setWordWrap(True)
        self.category_label.setMinimumHeight(16)
        self.category_label.setMaximumHeight(16777215)
        self.category_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.category_label.installEventFilter(self)
        self.update_product_category_display()

        img_layout.addWidget(self.img_label)
        img_layout.addWidget(self.category_label)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(4)

        self.code_label = QLabel(f"🆔 {prod_code}")
        self.code_label.setStyleSheet("font-weight: bold; color: #4a90e2; font-size: 11px;")
        self.code_label.setCursor(Qt.PointingHandCursor)
        self.code_label.installEventFilter(self)
        self.code_label.setToolTip("单击复制 ID，双击复制同款")

        tag_layout = QHBoxLayout()
        tag_layout.setSpacing(2)

        self.coupon_badge = QLabel()
        self.coupon_badge.setFixedSize(16, 16)
        self.coupon_badge.hide()

        self.new_customer_badge = QLabel()
        self.new_customer_badge.setFixedSize(16, 16)
        self.new_customer_badge.hide()

        self.limited_time_badge = QLabel()
        self.limited_time_badge.setFixedSize(16, 16)
        self.limited_time_badge.hide()

        self.marketing_badge = QLabel()
        self.marketing_badge.setFixedSize(16, 16)
        self.marketing_badge.hide()

        self.natural_flow_badge = QLabel("无推广")
        self.natural_flow_badge.setStyleSheet("color: white; background-color: #16a085; border-radius: 3px; padding: 1px 4px; font-size: 10px; font-weight: bold;")
        self.natural_flow_badge.hide()

        self.sitewide_badge = QLabel("全站")
        self.sitewide_badge.setStyleSheet("color: white; background-color: #8e44ad; border-radius: 3px; padding: 1px 4px; font-size: 10px; font-weight: bold;")
        self.sitewide_badge.hide()

        self.task_badge = QLabel("任务")
        self.task_badge.setStyleSheet("color: white; background-color: #e74c3c; border-radius: 3px; padding: 1px 4px; font-size: 10px; font-weight: bold;")
        self.task_badge.setToolTip("该链接有未完成任务或未提醒的提醒")
        self.task_badge.hide()

        tag_layout.addWidget(self.coupon_badge)
        tag_layout.addWidget(self.new_customer_badge)
        tag_layout.addWidget(self.limited_time_badge)
        tag_layout.addWidget(self.marketing_badge)
        tag_layout.addWidget(self.natural_flow_badge)
        tag_layout.addWidget(self.sitewide_badge)
        tag_layout.addWidget(self.task_badge)
        tag_layout.addStretch()

        top_layout.addWidget(self.code_label)
        top_layout.addLayout(tag_layout)

        self.title_label = QLabel(prod_title)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setStyleSheet("font-size: 11px; color: #333;")
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.title_label.setMaximumHeight(32)
        self.title_label.installEventFilter(self)

        self.original_name = prod_code
        self.original_title = prod_title

        self.memo_label = QLabel()
        self.memo_label.setWordWrap(True)
        self.memo_label.setMaximumHeight(30)
        self.memo_label.setCursor(Qt.PointingHandCursor)
        self.memo_label.installEventFilter(self)
        self.memo_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.update_product_memo_display()

        margin_row1_layout = QHBoxLayout()
        margin_row1_layout.setSpacing(10)
        margin_row1_layout.setContentsMargins(0, 0, 0, 0)

        self.margin_label = QLabel("毛利: -")
        self.margin_label.setStyleSheet("color: #d9534f; font-weight: bold; font-size: 12px;")
        self.margin_label.installEventFilter(self)

        self.link_order_label = QLabel("单量：0单")
        self.link_order_label.setStyleSheet("color: #8b4513; font-size: 12px; font-weight: bold;")
        self.link_order_label.installEventFilter(self)

        margin_row1_layout.addWidget(self.margin_label)
        margin_row1_layout.addWidget(self.link_order_label)
        margin_row1_layout.addStretch()

        self.margin_left_layout = QVBoxLayout()
        self.margin_left_layout.setSpacing(1)
        self.margin_left_layout.setContentsMargins(0, 0, 0, 0)

        self.net_profit_label = QLabel("净利: -")
        self.net_profit_label.setStyleSheet("color: #28a745; font-weight: bold; font-size: 13px;")
        self.net_profit_label.installEventFilter(self)

        self.roi_label = QLabel("")
        self.roi_label.setStyleSheet("font-family: Microsoft YaHei; color: blue; font-size: 13px;")
        self.roi_label.setTextFormat(Qt.RichText)
        self.roi_label.installEventFilter(self)

        self.margin_left_layout.addWidget(self.net_profit_label)
        self.margin_left_layout.addWidget(self.roi_label)

        margin_layout = QVBoxLayout()
        margin_layout.setSpacing(1)
        margin_layout.setContentsMargins(0, 0, 0, 0)
        margin_layout.addLayout(margin_row1_layout)
        margin_layout.addLayout(self.margin_left_layout)

        info_layout.addLayout(top_layout)
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.memo_label)
        info_layout.addLayout(margin_layout)

        main_layout.addWidget(img_container)
        main_layout.addLayout(info_layout)

        self.update_margin_display()
        self.update_promo_badges()
        self.update_task_badge()
        self.update_link_order_count()

    def set_search_highlight(self, active):
        self._search_highlight_active = bool(active)
        if self._search_highlight_active:
            self.setStyleSheet(
                "#ProductWidget { background-color: #fff8d8; "
                "border: 2px solid #f1c40f; border-radius: 4px; }"
            )
        else:
            self.setStyleSheet("")

    def update_task_badge(self):
        try:
            task_rows = self.db.safe_fetchall(
                "SELECT COUNT(*) FROM daily_tasks WHERE product_id=? AND is_completed=0",
                (self.prod_id,)
            )
            reminder_rows = self.db.safe_fetchall(
                "SELECT COUNT(*) FROM task_reminders WHERE product_id=? AND is_reminded=0",
                (self.prod_id,)
            )
            task_count = int(task_rows[0][0] or 0) if task_rows else 0
            reminder_count = int(reminder_rows[0][0] or 0) if reminder_rows else 0
            total = task_count + reminder_count
            if total > 0:
                self.task_badge.setVisible(True)
                self.task_badge.setToolTip(f"未完成任务 {task_count} 个，未提醒提醒 {reminder_count} 个")
            else:
                self.task_badge.hide()
        except Exception as e:
            print(f"更新任务标签失败: {e}")

    def recommended_row_height(self, base_height=140):
        extra_lines = getattr(self, "_memo_extra_lines", 0)
        if extra_lines <= 0:
            return base_height
        return base_height + min(36, extra_lines * 12)

    def update_product_category_display(self):
        try:
            rows = self.db.safe_fetchall("SELECT product_category_label FROM products WHERE id=?", (self.prod_id,))
            category = rows[0][0] if rows and rows[0][0] else ""
        except Exception as e:
            print(f"读取链接商品类型失败: {e}")
            category = ""

        if category:
            text = str(category).strip()
            display_text = text[:16] + "..." if len(text) > 16 else text
            self.category_label.setText(display_text)
            self.category_label.setToolTip(f"商品类型：{text}")
            self.category_label.setStyleSheet(
                "color: #245269; background-color: #e8f4fb; border: 1px solid #b8dff2; "
                "border-radius: 4px; padding: 0px; font-size: 12px; font-weight: bold;"
            )
            self.category_label.adjustSize()
        else:
            self.category_label.setText("未识别")
            self.category_label.setToolTip("成本库未识别到商品类型")
            self.category_label.setStyleSheet(
                "color: #777; background-color: #f5f5f5; border: 1px dashed #d0d0d0; "
                "border-radius: 4px; padding: 0px; font-size: 12px;"
            )
            self.category_label.adjustSize()

    def update_product_memo_display(self):
        try:
            rows = self.db.safe_fetchall("SELECT product_memo FROM products WHERE id=?", (self.prod_id,))
            memo = rows[0][0] if rows and rows[0][0] else ""
        except Exception as e:
            print(f"读取链接备注失败: {e}")
            memo = ""

        if memo:
            raw_memo = str(memo)
            compact = " ".join(raw_memo.split())
            explicit_lines = len([line for line in raw_memo.splitlines() if line.strip()])
            estimated_lines = max(explicit_lines, (len(compact) + 27) // 28)
            self._memo_extra_lines = max(0, estimated_lines - 2)
            if self._memo_extra_lines:
                self.memo_label.setMinimumHeight(42)
                self.memo_label.setMaximumHeight(46)
                self._memo_display_lines = 3
                limit = 96
            else:
                self.memo_label.setMinimumHeight(24)
                self.memo_label.setMaximumHeight(30)
                self._memo_display_lines = 2
                limit = 64
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
            self.memo_label.setMaximumHeight(30)
            self.memo_label.setText("📝 点击添加备注")
            self.memo_label.setToolTip("双击添加链接备注")
            self.memo_label.setStyleSheet(
                "color: #999; background-color: #f7f7f7; border: 1px dashed #d0d0d0; "
                "border-radius: 3px; padding: 1px 3px; font-size: 11px; font-style: italic;"
            )

    def edit_product_memo(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("链接备注")
        dialog.resize(500, 320)
        layout = QVBoxLayout(dialog)

        hint = QLabel("备注只显示在主界面当前链接卡片中。")
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
            discount_rows = self.main_app.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, is_limited_time, is_marketing, is_natural_flow, is_sitewide_managed FROM products WHERE id=?",
                (self.prod_id,)
            )
            if not discount_rows:
                self.coupon_badge.hide()
                self.new_customer_badge.hide()
                self.limited_time_badge.hide()
                self.marketing_badge.hide()
                self.natural_flow_badge.hide()
                self.sitewide_badge.hide()
                return
            coupon = discount_rows[0][0] if discount_rows[0][0] else 0
            new_customer = discount_rows[0][1] if discount_rows[0][1] else 0
            is_limited_time = discount_rows[0][2] if discount_rows[0][2] else 0
            is_marketing = discount_rows[0][3] if discount_rows[0][3] else 0
            is_natural_flow = discount_rows[0][4] if discount_rows[0][4] else 0
            is_sitewide_managed = discount_rows[0][5] if discount_rows[0][5] else 0
            icons_dir = _icons_dir()
            coupon_icon_path = os.path.join(icons_dir, "coupon.svg")
            new_customer_icon_path = os.path.join(icons_dir, "new_customer.svg")
            limited_time_icon_path = os.path.join(icons_dir, "limited-time.svg")
            marketing_icon_path = os.path.join(icons_dir, "marketing.svg")
            promo_icon_size = 17
            if coupon and coupon > 0:
                pixmap = QPixmap(coupon_icon_path)
                if not pixmap.isNull():
                    self.coupon_badge.setPixmap(pixmap.scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.coupon_badge.setText(f"¥{int(coupon)}")
                self.coupon_badge.show()
            else:
                self.coupon_badge.hide()
            if new_customer and new_customer > 0:
                pixmap = QPixmap(new_customer_icon_path)
                if not pixmap.isNull():
                    self.new_customer_badge.setPixmap(pixmap.scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.new_customer_badge.setText(f"¥{int(new_customer)}")
                self.new_customer_badge.show()
            else:
                self.new_customer_badge.hide()
            if is_limited_time:
                pixmap = QPixmap(limited_time_icon_path)
                if not pixmap.isNull():
                    self.limited_time_badge.setPixmap(pixmap.scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.limited_time_badge.setText("⏰")
                self.limited_time_badge.show()
            else:
                self.limited_time_badge.hide()
            if is_marketing:
                pixmap = QPixmap(marketing_icon_path)
                if not pixmap.isNull():
                    self.marketing_badge.setPixmap(pixmap.scaled(promo_icon_size, promo_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.marketing_badge.setText("📢")
                self.marketing_badge.show()
            else:
                self.marketing_badge.hide()
            self.natural_flow_badge.setVisible(bool(is_natural_flow))
            self.sitewide_badge.setVisible(bool(is_sitewide_managed) and not bool(is_natural_flow))
        except Exception as e:
            print(f"更新促销图标失败：{e}")

    def update_margin_display(self):
        try:
            rows = self.main_app.db.safe_fetchall(
                "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                (self.prod_id,)
            )
            if not rows:
                self.margin_label.setText("毛利: -")
                self.net_profit_label.setText("净利: -")
                self.margin_label.hide()
                self.net_profit_label.hide()
                self.roi_label.setText("")
                self.link_order_label.setText("单量：0单")
                if hasattr(self.main_app, "update_product_row_height"):
                    self.main_app.update_product_row_height(self.prod_id)
                return
            product_rows = self.main_app.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate, net_break_even_roi, is_natural_flow, is_sitewide_managed, store_id FROM products WHERE id=?",
                (self.prod_id,)
            )
            max_discount = 0
            current_roi = 0
            return_rate = 0
            net_break_even_roi = 0
            is_natural_flow = 0
            is_sitewide_managed = 0
            sitewide_roi = 0
            store_id = None
            if product_rows:
                coupon = product_rows[0][0] if product_rows[0][0] else 0
                new_customer = product_rows[0][1] if product_rows[0][1] else 0
                max_discount = max(coupon, new_customer)
                current_roi = product_rows[0][2] if product_rows[0][2] else 0
                return_rate = product_rows[0][3] if product_rows[0][3] else 0
                net_break_even_roi = product_rows[0][4] if product_rows[0][4] else 0
                is_natural_flow = product_rows[0][5] if product_rows[0][5] else 0
                is_sitewide_managed = product_rows[0][6] if product_rows[0][6] else 0
                store_id = product_rows[0][7] if product_rows[0][7] else None
                if store_id:
                    store_rows = self.main_app.db.safe_fetchall("SELECT sitewide_roi FROM stores WHERE id=?", (store_id,))
                    sitewide_roi = store_rows[0][0] if store_rows and store_rows[0][0] else 0
            total_weighted_margin = 0.0
            total_weight = 0.0
            for r in rows:
                spec_code, sale_price, weight = r[0], r[1], r[2]
                if sale_price is None or weight is None:
                    continue
                cost_res = self.main_app.db.safe_fetchall(
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
                discount_info = f"(减{max_discount:.0f})" if max_discount > 0 else ""
                self.margin_label.setText(f"毛利:{final_margin_pct:.1f}%{discount_info}")
                self.margin_label.show()
                final_net_margin_pct = -100
                margin_rate_decimal = final_margin_pct / 100
                effective_roi = sitewide_roi if is_sitewide_managed and not is_natural_flow else current_roi
                if (
                    hasattr(self.main_app, "is_real_promotion_data_mode")
                    and self.main_app.is_real_promotion_data_mode()
                    and not is_natural_flow
                ):
                    self._apply_real_promotion_display(store_id, margin_rate_decimal, net_break_even_roi)
                    if hasattr(self.main_app, "update_product_row_height"):
                        self.main_app.update_product_row_height(self.prod_id)
                    return
                if is_natural_flow:
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006) * 100
                elif effective_roi > 0 and return_rate >= 0:
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006 - (1 / effective_roi)) * 100
                net_profit_text = self._get_net_profit_status(final_net_margin_pct)
                self.net_profit_label.setText(f"净利:{final_net_margin_pct:.1f}% {net_profit_text}")
                if is_natural_flow:
                    roi_multiple_text = '<span style="color: #16a085; font-weight: bold;">无推广</span>'
                elif effective_roi > 0 and net_break_even_roi > 0:
                    roi_multiple = effective_roi / net_break_even_roi
                    label = "全站投产" if is_sitewide_managed else "投产"
                    roi_multiple_text = f'<span style="color: #666666; font-weight: bold;">{label}:</span><span style="color: #e74c3c; font-weight: bold;">{effective_roi:.2f}</span> <span style="color: #666666; font-weight: bold;">投产倍数:</span><span style="color: #3498db; font-weight: bold;">{roi_multiple:.2f}倍</span>'
                elif effective_roi > 0:
                    label = "全站投产" if is_sitewide_managed else "投产"
                    roi_multiple_text = f'<span style="color: #666666; font-weight: bold;">{label}:</span><span style="color: #e74c3c; font-weight: bold;">{effective_roi:.2f}</span> <span style="color: #666666; font-weight: bold;">投产倍数:</span><span style="color: #3498db; font-weight: bold;">--</span>'
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
                self.margin_label.setText("毛利: -")
                self.margin_label.show()
                self.net_profit_label.setText("净利: -")
                self.net_profit_label.show()
                self.roi_label.setText("")
            self.update_link_order_count()
            if hasattr(self.main_app, "update_product_row_height"):
                self.main_app.update_product_row_height(self.prod_id)
        except Exception as e:
            print(f"更新毛利显示失败：{e}")
            self.margin_label.setText("毛利: 错误")
            self.margin_label.show()
            self.net_profit_label.setText("净利: 错误")
            self.net_profit_label.show()
            self.roi_label.setText("")
            self.link_order_label.setText("单量：0单")
            if hasattr(self.main_app, "update_product_row_height"):
                self.main_app.update_product_row_height(self.prod_id)

    def update_link_order_count(self):
        try:
            if (
                hasattr(self.main_app, "is_real_promotion_data_mode")
                and self.main_app.is_real_promotion_data_mode()
                and hasattr(self.main_app, "get_latest_promotion_data")
            ):
                product_rows = self.main_app.db.safe_fetchall(
                    "SELECT store_id, is_natural_flow FROM products WHERE id=?",
                    (self.prod_id,)
                )
                store_id = product_rows[0][0] if product_rows else None
                is_natural_flow = product_rows[0][1] if product_rows else 0
                if store_id and not is_natural_flow:
                    data = self.main_app.get_latest_promotion_data(store_id, self.prod_code)
                    net_orders = float(data.get("net_orders") or 0) if data else 0
                    self.link_order_label.setText(f"净成交：{net_orders:.0f}单")
                    return

            spec_counts = self.main_app.db.safe_fetchall(
                "SELECT spec_code, order_count, refund_count FROM imported_orders WHERE product_id=?",
                (self.prod_code,)
            )
            total = sum(sc[1] for sc in spec_counts) if spec_counts else 0
            self.link_order_label.setText(f"单量：{total}单")
        except Exception as e:
            print(f"更新链接单量失败: {e}")
            self.link_order_label.setText("单量：0单")

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
        data = None
        if hasattr(self.main_app, "get_latest_promotion_data"):
            data = self.main_app.get_latest_promotion_data(store_id, self.prod_code)
        if not data:
            self.margin_label.setText("真实推广: 无数据")
            self.margin_label.show()
            self.net_profit_label.setText("净利: 无真实推广数据")
            self.net_profit_label.setStyleSheet("color: #999; font-weight: bold; font-size: 13px;")
            self.net_profit_label.show()
            self.roi_label.setText("")
            self.link_order_label.setText("净成交：0单")
            return True

        cost = float(data.get("cost") or 0)
        transaction_amount = float(data.get("transaction_amount") or 0)
        net_amount = float(data.get("net_transaction_amount") or 0)
        net_roi = float(data.get("net_roi") or 0)
        net_orders = float(data.get("net_orders") or 0)
        promotion_share = float(data.get("promotion_impression_share") or 0)
        tech_fee = net_amount * 0.006
        if net_amount > 0:
            net_profit = net_amount * margin_rate_decimal - cost - tech_fee
            net_margin_pct = net_profit / net_amount * 100
            net_margin_text = f"{net_margin_pct:.1f}%"
            status = self._get_net_profit_status(net_margin_pct)
        else:
            net_profit = -cost
            net_margin_text = "无成交"
            status = "亏损" if net_profit < 0 else "保本"
        roi_multiple = net_roi / net_break_even_roi if net_break_even_roi and net_break_even_roi > 0 else None
        date_text = str(data.get("record_date") or "")[-5:]
        self.margin_label.setText(f"真实:{date_text} 交易¥{transaction_amount:.0f} 花费¥{cost:.0f}")
        self.margin_label.show()
        self.net_profit_label.setText(f"净利润:¥{net_profit:.2f} 净利:{net_margin_text} {status}")
        if net_profit > 0:
            self.net_profit_label.setStyleSheet("color: #006400; font-weight: bold; font-size: 13px;")
        elif abs(net_profit) < 0.000001:
            self.net_profit_label.setStyleSheet("color: #daa520; font-weight: bold; font-size: 13px;")
        else:
            self.net_profit_label.setStyleSheet("color: #dc143c; font-weight: bold; font-size: 13px;")
        self.net_profit_label.show()
        multiple_text = f"{roi_multiple:.2f}倍" if roi_multiple is not None else "--"
        self.roi_label.setText(
            f'<span style="color:#666;font-weight:bold;">净投产:</span><span style="color:#e74c3c;font-weight:bold;">{net_roi:.2f}</span> '
            f'<span style="color:#666;font-weight:bold;">倍数:</span><span style="color:#3498db;font-weight:bold;">{multiple_text}</span> '
            f'<span style="color:#666;font-weight:bold;">曝占:</span><span style="color:#8e44ad;font-weight:bold;">{promotion_share * 100:.1f}%</span>'
        )
        self.link_order_label.setText(f"净成交：{net_orders:.0f}单")
        return True

    def eventFilter(self, obj, event):
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
            if event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
                    self._paste_image_from_clipboard()
                    return True
        return super().eventFilter(obj, event)

    def contextMenuEvent(self, event):
        self.show_product_context_menu(event.globalPos())
        event.accept()

    def show_product_context_menu(self, global_pos):
        menu = QMenu(self)
        promotion_action = QAction("查看推广数据", self)
        delete_action = QAction("删除链接", self)
        menu.addAction(promotion_action)
        menu.addAction(delete_action)
        selected = menu.exec_(global_pos)
        if selected == promotion_action:
            self.open_promotion_history()
        elif selected == delete_action:
            self.delete_product()

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
        if not mime_data or not mime_data.hasImage():
            self.main_app.show_toast("剪贴板中没有图片")
            return

        image = clipboard.image()
        if image.isNull():
            self.main_app.show_toast("剪贴板图片读取失败")
            return

        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self.main_app.show_toast("剪贴板图片读取失败")
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
        try:
            rows = self.main_app.db.safe_fetchall(
                "SELECT current_roi, return_rate FROM products WHERE id=?",
                (self.prod_id,)
            )
            if not rows:
                self.roi_label.setText("")
                return
            current_roi = rows[0][0] if rows[0][0] else 0
            return_rate = rows[0][1] if rows[0][1] else 0
            if current_roi <= 0:
                self.roi_label.setText("")
                return
            if margin_rate is None:
                margin_text = self.margin_label.text()
                try:
                    margin_rate = float(margin_text.replace("净利:", "").replace("毛利:", "").replace("%", "").strip().split()[0]) / 100
                except Exception:
                    margin_rate = 0
            if margin_rate <= 0:
                self.roi_label.setText("")
                return
            net_margin_formula = margin_rate * (1 - return_rate / 100) - 0.0006
            if net_margin_formula <= 0:
                self.roi_label.setText("(亏损)")
                self.roi_label.setStyleSheet("color: #e74c3c; font-size: 11px; font-weight: bold;")
            else:
                net_break_even = 1 / net_margin_formula
                best_roi = net_break_even * 1.4
                if current_roi >= best_roi:
                    self.roi_label.setText("✓达标")
                    self.roi_label.setStyleSheet("color: #27ae60; font-size: 11px; font-weight: bold;")
                elif current_roi >= net_break_even:
                    self.roi_label.setText("✓")
                    self.roi_label.setStyleSheet("color: #6c757d; font-size: 11px;")
                else:
                    self.roi_label.setText("未达")
                    self.roi_label.setStyleSheet("color: #e67e22; font-size: 11px;")
        except Exception as e:
            print(f"更新投产显示失败：{e}")
            self.roi_label.setText("")

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
                pixmap = QPixmap()
                pixmap.loadFromData(image_data)
                if not pixmap.isNull():
                    container_size = 72
                    if pixmap.width() > container_size or pixmap.height() > container_size:
                        pixmap = pixmap.scaled(container_size, container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

    def delete_product(self):
        reply = QMessageBox.question(self, "确认", "确定删除该商品及其所有记录吗？")
        if reply == QMessageBox.Yes:
            try:
                product_rows = self.main_app.db.safe_fetchall(
                    "SELECT store_id, name, title FROM products WHERE id=?",
                    (self.prod_id,)
                )
                store_id = product_rows[0][0] if product_rows else None
                product_id = product_rows[0][1] if product_rows else self.prod_code
                product_title = product_rows[0][2] if product_rows else self.prod_title
                self.main_app.db.safe_execute("DELETE FROM product_specs WHERE product_id=?", (self.prod_id,))
                self.main_app.db.safe_execute("DELETE FROM records WHERE product_id=?", (self.prod_id,))
                self.main_app.db.safe_execute("DELETE FROM product_image_history WHERE product_id=?", (self.prod_id,))
                self.main_app.db.safe_execute("DELETE FROM products WHERE id=?", (self.prod_id,))
                if store_id and hasattr(self.main_app, "record_store_link_change"):
                    self.main_app.record_store_link_change(store_id, "delete", product_id, product_title)
                self.main_app.load_data_safe()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除商品失败: {e}")

    def _on_code_click(self, event):
        self.copy_product_id()

    def copy_same_product(self):
        store_id = self.db.safe_fetchall("SELECT store_id FROM products WHERE id=?", (self.prod_id,))
        if store_id and store_id[0]:
            self.main_app.add_product(store_id[0][0], copy_from_id=self.prod_id)

    def copy_product_id(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.original_name)
        self.main_app.show_toast(f"✅ 已复制商品ID: {self.original_name}")


class StoreWidget(QWidget):
    """店铺展示控件，包含删除按钮和添加商品按钮"""
    def __init__(self, store_id, store_name, main_app):
        super().__init__()
        self.store_id = store_id
        self.store_name = store_name
        self.main_app = main_app
        self.db = main_app.db

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

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
        self.label.setStyleSheet("background-color: #87CEEB; font-weight: bold; padding: 1px; border-radius: 5px;")
        self.label.setWordWrap(False)
        self.label.setCursor(Qt.PointingHandCursor)
        self.label.setToolTip("左键双击查看店铺毛利 | 右键双击编辑店铺备注")
        self.label.installEventFilter(self)

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
            self.margin_label = QLabel(f"   综合毛利: {margin:.1f}%")
            self.margin_label.setStyleSheet("background-color: #fdeaa8; padding: 3px 8px; font-size: 12px; color: #e74c3c; font-weight: bold;")
        else:
            self.margin_label = QLabel("   综合毛利: --")
            self.margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")

        if self._is_real_promotion_mode():
            real_metrics = self.calculate_store_real_promotion_metrics()
            if real_metrics:
                net_profit = real_metrics["net_profit"]
                net_margin = real_metrics["net_margin_pct"]
                profit_color = "#006400" if net_profit > 0 else ("#daa520" if abs(net_profit) < 0.000001 else "#dc143c")
                self.net_margin_label = QLabel(f"推广盈亏: ¥{net_profit:.0f} 净利:{net_margin:.1f}%")
                self.net_margin_label.setStyleSheet(f"background-color: #e8f4f8; padding: 3px 8px; font-size: 12px; color: {profit_color}; font-weight: bold;")
                avg_price = real_metrics.get("avg_price")
                if avg_price is not None:
                    self.avg_price_label = QLabel(f"真实客单: ¥{avg_price:.1f}")
                    self.avg_price_label.setStyleSheet("background-color: #e8f8f5; padding: 3px 8px; font-size: 12px; color: #27ae60; font-weight: bold;")
                else:
                    self.avg_price_label = QLabel("真实客单: --")
                    self.avg_price_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
            else:
                self.net_margin_label = QLabel("推广盈亏: --")
                self.net_margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
                self.avg_price_label = QLabel("真实客单: --")
                self.avg_price_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
        else:
            net_margin = self.calculate_store_net_margin()
            if net_margin is not None:
                net_margin_color = self._get_net_margin_color(net_margin)
                self.net_margin_label = QLabel(f"净利率: {net_margin:.1f}%")
                self.net_margin_label.setStyleSheet(f"background-color: #e8f4f8; padding: 3px 8px; font-size: 12px; color: {net_margin_color}; font-weight: bold;")
            else:
                self.net_margin_label = QLabel("净利率: --")
                self.net_margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")

            avg_price = self.calculate_store_avg_price()
            if avg_price is not None:
                self.avg_price_label = QLabel(f"客单价: ¥{avg_price:.1f}")
                self.avg_price_label.setStyleSheet("background-color: #e8f8f5; padding: 3px 8px; font-size: 12px; color: #27ae60; font-weight: bold;")
            else:
                self.avg_price_label = QLabel("客单价: --")
                self.avg_price_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")

        label_layout.addWidget(top_row_widget)
        label_layout.addWidget(self.memo_label)
        label_layout.addWidget(self.margin_label)
        label_layout.addWidget(self.net_margin_label)
        label_layout.addWidget(self.avg_price_label)

        btn_widget = QWidget()
        btn_layout = QVBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(3)
        icons_dir = _icons_dir()
        self.delete_btn = QPushButton()
        self.delete_btn.setIcon(QIcon(os.path.join(icons_dir, "delete_store.svg")))
        self.delete_btn.setIconSize(QSize(20, 20))
        self.delete_btn.setToolTip("删除店铺")
        self.delete_btn.setFixedSize(28, 22)
        self.delete_btn.setStyleSheet("QPushButton { background-color: #dc3545; border-radius: 3px; } QPushButton:hover { background-color: #c82333; }")
        self.delete_btn.clicked.connect(self.delete_store)
        self.add_product_btn = QPushButton()
        self.add_product_btn.setIcon(QIcon(os.path.join(icons_dir, "add_link.svg")))
        self.add_product_btn.setIconSize(QSize(20, 20))
        self.add_product_btn.setToolTip("添加商品")
        self.add_product_btn.setFixedSize(28, 22)
        self.add_product_btn.setStyleSheet("QPushButton { background-color: #28a745; border-radius: 3px; } QPushButton:hover { background-color: #218838; }")
        self.add_product_btn.clicked.connect(self.add_product)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.add_product_btn)
        layout.addWidget(label_widget)
        layout.addWidget(btn_widget)

    def calculate_store_margin(self):
        try:
            products = self.db.safe_fetchall("SELECT id, store_weight FROM products WHERE store_id=?", (self.store_id,))
            if not products:
                return None
            total_weight = 0
            total_weighted_margin = 0
            for prod_id, store_weight in products:
                if not store_weight or store_weight <= 0:
                    continue
                specs = self.db.safe_fetchall(
                    "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                    (prod_id,)
                )
                if not specs:
                    continue
                coupon_res = self.db.safe_fetchall(
                    "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
                    (prod_id,)
                )
                coupon = (coupon_res[0][0] or 0) if coupon_res else 0
                new_customer = (coupon_res[0][1] or 0) if coupon_res else 0
                max_discount = max(coupon, new_customer)
                total_spec_weight = 0
                total_weighted_margin_prod = 0
                for spec_code, sale_price, weight in specs:
                    if not sale_price or sale_price <= 0:
                        continue
                    weight = weight or 0
                    cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
                    cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
                    final_price = sale_price - max_discount
                    if final_price > 0 and cost > 0:
                        margin = (final_price - cost) / final_price
                        total_weighted_margin_prod += margin * weight
                        total_spec_weight += weight
                if total_spec_weight > 0:
                    spec_margin = total_weighted_margin_prod / total_spec_weight
                    total_weighted_margin += spec_margin * store_weight
                    total_weight += store_weight
            if total_weight > 0:
                return (total_weighted_margin / total_weight) * 100
            return None
        except Exception as e:
            print(f"计算店铺毛利失败: {e}")
            return None

    def _is_real_promotion_mode(self):
        return (
            hasattr(self.main_app, "is_real_promotion_data_mode")
            and self.main_app.is_real_promotion_data_mode()
            and hasattr(self.main_app, "get_latest_promotion_data")
        )

    def _calculate_product_margin_decimal(self, prod_id):
        specs = self.db.safe_fetchall(
            "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
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
        total_spec_weight = 0
        total_weighted_margin = 0
        for spec_code, sale_price, weight in specs:
            if sale_price is None or weight is None or sale_price <= 0:
                continue
            cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
            cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
            final_price = sale_price - max_discount
            if final_price > 0 and cost > 0:
                total_weighted_margin += ((final_price - cost) / final_price) * weight
                total_spec_weight += weight
        if total_spec_weight <= 0:
            return None
        return total_weighted_margin / total_spec_weight

    def calculate_store_real_promotion_metrics(self):
        try:
            products = self.db.safe_fetchall(
                "SELECT id, name, is_natural_flow FROM products WHERE store_id=?",
                (self.store_id,)
            )
            if not products:
                return None
            total_net_amount = 0.0
            total_cost = 0.0
            total_net_orders = 0.0
            total_net_profit = 0.0
            matched_count = 0
            for prod_id, product_code, is_natural_flow in products:
                if is_natural_flow:
                    continue
                margin_decimal = self._calculate_product_margin_decimal(prod_id)
                if margin_decimal is None:
                    continue
                data = self.main_app.get_latest_promotion_data(self.store_id, product_code)
                if not data:
                    continue
                net_amount = float(data.get("net_transaction_amount") or 0)
                cost = float(data.get("cost") or 0)
                net_orders = float(data.get("net_orders") or 0)
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
            }
        except Exception as e:
            print(f"计算店铺真实推广指标失败: {e}")
            return None

    def calculate_store_net_margin(self):
        try:
            products = self.db.safe_fetchall("SELECT id, store_weight FROM products WHERE store_id=?", (self.store_id,))
            if not products:
                return None
            total_weight = 0
            total_weighted_net_margin = 0
            for prod_id, store_weight in products:
                if not store_weight or store_weight <= 0:
                    continue
                specs = self.db.safe_fetchall(
                    "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                    (prod_id,)
                )
                if not specs:
                    continue
                product_rows = self.db.safe_fetchall(
                    "SELECT coupon_amount, new_customer_discount, current_roi, return_rate FROM products WHERE id=?",
                    (prod_id,)
                )
                coupon = (product_rows[0][0] or 0) if product_rows else 0
                new_customer = (product_rows[0][1] or 0) if product_rows else 0
                max_discount = max(coupon, new_customer)
                current_roi = (product_rows[0][2] or 0) if product_rows else 0
                return_rate = (product_rows[0][3] or 0) if product_rows else 0
                total_spec_weight = 0
                total_weighted_margin_prod = 0
                for spec_code, sale_price, weight in specs:
                    if not sale_price or sale_price <= 0:
                        continue
                    weight = weight or 0
                    cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
                    cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
                    final_price = sale_price - max_discount
                    if final_price > 0 and cost > 0:
                        margin = (final_price - cost) / final_price
                        total_weighted_margin_prod += margin * weight
                        total_spec_weight += weight
                if total_spec_weight > 0:
                    spec_margin = total_weighted_margin_prod / total_spec_weight
                    final_net_margin_pct = -100
                    if current_roi > 0 and return_rate >= 0:
                        margin_rate_decimal = spec_margin
                        final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006 - (1 / current_roi)) * 100
                    total_weighted_net_margin += final_net_margin_pct * store_weight
                    total_weight += store_weight
            if total_weight > 0:
                return total_weighted_net_margin / total_weight
            return None
        except Exception as e:
            print(f"计算店铺净利率失败: {e}")
            return None

    def calculate_store_avg_price(self):
        try:
            products = self.db.safe_fetchall("SELECT id, store_weight FROM products WHERE store_id=?", (self.store_id,))
            if not products:
                return None
            total_weight = 0
            total_weighted_price = 0
            for prod_id, store_weight in products:
                if not store_weight or store_weight <= 0:
                    continue
                specs = self.db.safe_fetchall(
                    "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                    (prod_id,)
                )
                if not specs:
                    continue
                product_rows = self.db.safe_fetchall(
                    "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
                    (prod_id,)
                )
                coupon = (product_rows[0][0] or 0) if product_rows else 0
                new_customer = (product_rows[0][1] or 0) if product_rows else 0
                max_discount = max(coupon, new_customer)
                total_spec_weight = 0
                total_weighted_price_prod = 0
                for spec_code, sale_price, weight in specs:
                    if sale_price is None or weight is None or sale_price <= 0:
                        continue
                    weight = weight or 0
                    final_price = sale_price - max_discount
                    if final_price > 0:
                        total_weighted_price_prod += final_price * weight
                        total_spec_weight += weight
                if total_spec_weight > 0:
                    spec_avg_price = total_weighted_price_prod / total_spec_weight
                    total_weighted_price += spec_avg_price * store_weight
                    total_weight += store_weight
            if total_weight > 0:
                return total_weighted_price / total_weight
            return None
        except Exception as e:
            print(f"计算店铺客单价失败: {e}")
            return None

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
        reply = QMessageBox.question(self, "确认", f"确定删除店铺 '{self.store_name}' 及其所有商品和记录吗？\n此操作不可恢复！")
        if reply == QMessageBox.Yes:
            try:
                products = self.main_app.db.safe_fetchall("SELECT id FROM products WHERE store_id=?", (self.store_id,))
                for product in products:
                    prod_id = product[0]
                    self.main_app.db.safe_execute("DELETE FROM product_specs WHERE product_id=?", (prod_id,))
                    self.main_app.db.safe_execute("DELETE FROM records WHERE product_id=?", (prod_id,))
                self.main_app.db.safe_execute("DELETE FROM products WHERE store_id=?", (self.store_id,))
                self.main_app.db.safe_execute("DELETE FROM stores WHERE id=?", (self.store_id,))
                self.main_app.load_data_safe()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除店铺失败: {e}")

    def add_product(self):
        self.main_app.add_product(self.store_id)

    def eventFilter(self, obj, event):
        if obj == self.label and event.type() == QEvent.MouseButtonDblClick:
            self.open_store_margin_dialog()
            return True
        elif hasattr(self, 'memo_label') and obj == self.memo_label and event.type() == QEvent.MouseButtonDblClick:
            self.edit_store_memo()
            return True
        return super().eventFilter(obj, event)

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
            self.main_app.show_toast("✅ 店铺备注已更新")
            dialog.accept()

        btn_save.clicked.connect(save_memo)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec_()

    def open_store_margin_dialog(self):
        """通过 main_app 打开店铺毛利对话框，避免 widgets 依赖主模块的 Dialog"""
        self.main_app.open_store_margin_dialog(self.store_id, self.store_name)

    def refresh_margin_display(self):
        margin = self.calculate_store_margin()
        if margin is not None:
            self.margin_label.setText(f"   综合毛利: {margin:.1f}%")
            self.margin_label.setStyleSheet("background-color: #fdeaa8; padding: 3px 8px; font-size: 12px; color: #e74c3c; font-weight: bold;")
        else:
            self.margin_label.setText("   综合毛利: --")
            self.margin_label.setStyleSheet("background-color: #f5f5f5; padding: 3px 8px; font-size: 12px; color: #999;")
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

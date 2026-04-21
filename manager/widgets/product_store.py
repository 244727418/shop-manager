# -*- coding: utf-8 -*-
"""
商品与店铺相关 UI 组件：ProductWidget、StoreWidget、RecordRow、InPlaceEditor
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QApplication, QScrollArea, QTextEdit,
    QTimeEdit, QDialog, QSizePolicy, QCheckBox, QDateEdit, QLayout
)
from PyQt5.QtCore import Qt, QEvent, QTime, QSize, QDate
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

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 2, 5, 2)
        main_layout.setSpacing(6)

        img_container = QWidget()
        img_container.setFixedWidth(77)
        img_layout = QVBoxLayout(img_container)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(2)

        self.img_label = QLabel()
        self.img_label.setFixedSize(72, 72)
        self.img_label.setStyleSheet("border: 1px solid #ddd; border-radius: 4px; padding: 0px;")
        self.img_label.setAlignment(Qt.AlignCenter)
        self.set_image_from_data(image_data)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(2)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        btn_img = QPushButton("🔄")
        btn_img.setFixedSize(22, 22)
        btn_img.setToolTip("换图")
        btn_img.setStyleSheet("QPushButton { font-size: 15px; padding: 0px; background-color: #6c757d; color: white; border-radius: 2px; } QPushButton:hover { background-color: #5a6268; }")
        btn_img.clicked.connect(self.change_image)

        btn_copy = QPushButton("📋")
        btn_copy.setFixedSize(22, 22)
        btn_copy.setToolTip("复制ID")
        btn_copy.setStyleSheet("QPushButton { font-size: 15px; padding: 0px; background-color: #17a2b8; color: white; border-radius: 2px; } QPushButton:hover { background-color: #138496; }")
        btn_copy.clicked.connect(self.copy_product_id)

        btn_del = QPushButton("🗑️")
        btn_del.setFixedSize(22, 22)
        btn_del.setToolTip("删除")
        btn_del.setStyleSheet("QPushButton { font-size: 15px; padding: 0px; background-color: #dc3545; color: white; border-radius: 2px; } QPushButton:hover { background-color: #c82333; }")
        btn_del.clicked.connect(self.delete_product)

        btn_layout.addWidget(btn_img)
        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_del)

        img_layout.addWidget(self.img_label)
        img_layout.addLayout(btn_layout)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(4)

        self.code_label = QLabel(f"🆔 {prod_code}")
        self.code_label.setStyleSheet("font-weight: bold; color: #4a90e2; font-size: 11px;")
        self.code_label.setCursor(Qt.PointingHandCursor)
        self.code_label.mousePressEvent = self._on_code_click
        self.code_label.setToolTip("双击修改ID")

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

        tag_layout.addWidget(self.coupon_badge)
        tag_layout.addWidget(self.new_customer_badge)
        tag_layout.addWidget(self.limited_time_badge)
        tag_layout.addWidget(self.marketing_badge)
        tag_layout.addStretch()

        top_layout.addWidget(self.code_label)
        top_layout.addLayout(tag_layout)

        self.title_label = QLabel(prod_title)
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setStyleSheet("font-size: 11px; color: #333;")
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.title_label.setMaximumHeight(32)

        self.original_name = prod_code
        self.original_title = prod_title

        margin_row1_layout = QHBoxLayout()
        margin_row1_layout.setSpacing(10)
        margin_row1_layout.setContentsMargins(0, 0, 0, 0)

        self.margin_label = QLabel("毛利: -")
        self.margin_label.setStyleSheet("color: #d9534f; font-weight: bold; font-size: 12px;")

        self.link_order_label = QLabel("单量：0单")
        self.link_order_label.setStyleSheet("color: #8b4513; font-size: 12px; font-weight: bold;")

        margin_row1_layout.addWidget(self.margin_label)
        margin_row1_layout.addWidget(self.link_order_label)
        margin_row1_layout.addStretch()

        self.margin_left_layout = QVBoxLayout()
        self.margin_left_layout.setSpacing(1)
        self.margin_left_layout.setContentsMargins(0, 0, 0, 0)

        self.net_profit_label = QLabel("净利: -")
        self.net_profit_label.setStyleSheet("color: #28a745; font-weight: bold; font-size: 13px;")

        self.roi_label = QLabel("")
        self.roi_label.setStyleSheet("font-family: Microsoft YaHei; color: blue; font-size: 13px;")
        self.roi_label.setTextFormat(Qt.RichText)

        self.margin_left_layout.addWidget(self.net_profit_label)
        self.margin_left_layout.addWidget(self.roi_label)

        margin_layout = QVBoxLayout()
        margin_layout.setSpacing(1)
        margin_layout.setContentsMargins(0, 0, 0, 0)
        margin_layout.addLayout(margin_row1_layout)
        margin_layout.addLayout(self.margin_left_layout)

        info_layout.addLayout(top_layout)
        info_layout.addWidget(self.title_label)
        info_layout.addLayout(margin_layout)

        main_layout.addWidget(img_container)
        main_layout.addLayout(info_layout)

        self.update_margin_display()
        self.update_promo_badges()
        self.update_link_order_count()

    def update_promo_badges(self):
        try:
            discount_rows = self.main_app.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, is_limited_time, is_marketing FROM products WHERE id=?",
                (self.prod_id,)
            )
            if not discount_rows:
                self.coupon_badge.hide()
                self.new_customer_badge.hide()
                self.limited_time_badge.hide()
                self.marketing_badge.hide()
                return
            coupon = discount_rows[0][0] if discount_rows[0][0] else 0
            new_customer = discount_rows[0][1] if discount_rows[0][1] else 0
            is_limited_time = discount_rows[0][2] if discount_rows[0][2] else 0
            is_marketing = discount_rows[0][3] if discount_rows[0][3] else 0
            icons_dir = _icons_dir()
            coupon_icon_path = os.path.join(icons_dir, "coupon.svg")
            new_customer_icon_path = os.path.join(icons_dir, "new_customer.svg")
            limited_time_icon_path = os.path.join(icons_dir, "limited-time.svg")
            marketing_icon_path = os.path.join(icons_dir, "marketing.svg")
            if coupon and coupon > 0:
                pixmap = QPixmap(coupon_icon_path)
                if not pixmap.isNull():
                    self.coupon_badge.setPixmap(pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.coupon_badge.setText(f"¥{int(coupon)}")
                self.coupon_badge.show()
            else:
                self.coupon_badge.hide()
            if new_customer and new_customer > 0:
                pixmap = QPixmap(new_customer_icon_path)
                if not pixmap.isNull():
                    self.new_customer_badge.setPixmap(pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.new_customer_badge.setText(f"¥{int(new_customer)}")
                self.new_customer_badge.show()
            else:
                self.new_customer_badge.hide()
            if is_limited_time:
                pixmap = QPixmap(limited_time_icon_path)
                if not pixmap.isNull():
                    self.limited_time_badge.setPixmap(pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.limited_time_badge.setText("⏰")
                self.limited_time_badge.show()
            else:
                self.limited_time_badge.hide()
            if is_marketing:
                pixmap = QPixmap(marketing_icon_path)
                if not pixmap.isNull():
                    self.marketing_badge.setPixmap(pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.marketing_badge.setText("📢")
                self.marketing_badge.show()
            else:
                self.marketing_badge.hide()
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
                self.link_order_label.setText("单量：0单")
                return
            product_rows = self.main_app.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount, current_roi, return_rate, net_break_even_roi FROM products WHERE id=?",
                (self.prod_id,)
            )
            max_discount = 0
            current_roi = 0
            return_rate = 0
            net_break_even_roi = 0
            if product_rows:
                coupon = product_rows[0][0] if product_rows[0][0] else 0
                new_customer = product_rows[0][1] if product_rows[0][1] else 0
                max_discount = max(coupon, new_customer)
                current_roi = product_rows[0][2] if product_rows[0][2] else 0
                return_rate = product_rows[0][3] if product_rows[0][3] else 0
                net_break_even_roi = product_rows[0][4] if product_rows[0][4] else 0
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
                if current_roi > 0 and return_rate >= 0:
                    margin_rate_decimal = final_margin_pct / 100
                    final_net_margin_pct = (margin_rate_decimal * (1 - return_rate / 100) - 0.006 - (1 / current_roi)) * 100
                net_profit_text = self._get_net_profit_status(final_net_margin_pct)
                self.net_profit_label.setText(f"净利:{final_net_margin_pct:.1f}% {net_profit_text}")
                roi_multiple_text = ""
                if current_roi > 0 and net_break_even_roi > 0:
                    roi_multiple = current_roi / net_break_even_roi
                    roi_multiple_text = f'<span style="color: #666666; font-weight: bold;">投产:</span><span style="color: #e74c3c; font-weight: bold;">{current_roi:.2f}</span> <span style="color: #666666; font-weight: bold;">投产倍数:</span><span style="color: #3498db; font-weight: bold;">{roi_multiple:.2f}倍</span>'
                elif current_roi > 0:
                    roi_multiple_text = f'<span style="color: #666666; font-weight: bold;">投产:</span><span style="color: #e74c3c; font-weight: bold;">{current_roi:.2f}</span> <span style="color: #666666; font-weight: bold;">投产倍数:</span><span style="color: #3498db; font-weight: bold;">--</span>'
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
        except Exception as e:
            print(f"更新毛利显示失败：{e}")
            self.margin_label.setText("毛利: 错误")
            self.margin_label.show()
            self.net_profit_label.setText("净利: 错误")
            self.net_profit_label.show()
            self.roi_label.setText("")
            self.link_order_label.setText("单量：0单")

    def update_link_order_count(self):
        try:
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

    def update_roi_display(self, margin_rate=None):
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
                self.main_app.db.safe_execute(
                    "UPDATE products SET image_data=? WHERE id=?",
                    (image_data, self.prod_id)
                )
                self.set_image_from_data(image_data)
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
                self.main_app.db.safe_execute("DELETE FROM product_specs WHERE product_id=?", (self.prod_id,))
                self.main_app.db.safe_execute("DELETE FROM records WHERE product_id=?", (self.prod_id,))
                self.main_app.db.safe_execute("DELETE FROM products WHERE id=?", (self.prod_id,))
                self.main_app.load_data_safe()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除商品失败: {e}")

    def _on_code_click(self, event):
        self.copy_product_id()
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
        self.label.setWordWrap(True)
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

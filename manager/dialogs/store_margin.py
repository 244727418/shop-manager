# -*- coding: utf-8 -*-
"""店铺毛利管理对话框"""
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QWidget, QLineEdit, QPushButton, QMessageBox, QMenu, QAction,
    QAbstractItemView, QFileDialog, QComboBox, QDialog
)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QColor, QPixmap, QDoubleValidator

try:
    from openpyxl import load_workbook
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


class StoreMarginDialog(QDialog):
    """店铺毛利综合管理对话框"""
    def __init__(self, store_id, store_name, main_app, parent=None, save_callback=None):
        super().__init__(parent)
        self.store_id = store_id
        self.store_name = store_name
        self.main_app = main_app
        self.db = main_app.db
        self.product_weights = {}
        self.is_balancing = False
        self.save_callback = save_callback

        self.setWindowTitle(f"🏪 店铺毛利管理 - {store_name}")
        self.resize(1200, 800)
        self.init_ui()
        self.load_products()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonDblClick:
            if isinstance(obj, QLineEdit):
                row = obj.property("row")
                prod_id = obj.property("prod_id")
                if row is not None and prod_id is not None:
                    return super().eventFilter(obj, event)
            elif isinstance(obj, QLabel):
                row = obj.property("row")
                prod_id = obj.property("prod_id")
                if row is not None and prod_id is not None:
                    self.toggle_lock(row, prod_id)
                    return True
        return super().eventFilter(obj, event)

    def on_weight_changed(self, prod_id, text):
        if prod_id not in self.product_weights:
            return
        sender = self.sender()
        try:
            new_weight = float(text) if text else 0
        except ValueError:
            new_weight = 0
        if new_weight < 0:
            new_weight = 0
            if sender:
                sender.setText("0")
        total_locked = sum(
            data.get("weight", 0) for pid, data in self.product_weights.items()
            if pid != prod_id and data.get("locked", 0)
        )
        max_allowed = 100 - total_locked
        if new_weight > max_allowed:
            new_weight = max_allowed
            if sender:
                sender.blockSignals(True)
                weight_str = str(int(new_weight)) if new_weight == int(new_weight) else f"{new_weight:.1f}"
                sender.setText(weight_str)
                sender.blockSignals(False)
        if new_weight < 0:
            new_weight = 0
            if sender:
                sender.blockSignals(True)
                sender.setText("0")
                sender.blockSignals(False)
        if new_weight > 100:
            new_weight = 100
            if sender:
                sender.blockSignals(True)
                sender.setText("100")
                sender.blockSignals(False)
        self.product_weights[prod_id]["weight"] = new_weight

    def on_weight_editing_finished(self, prod_id):
        if prod_id not in self.product_weights:
            return
        new_weight = self.product_weights[prod_id].get("weight", 0)
        self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (new_weight, prod_id))
        self.rebalance_unlocked_weights(prod_id)
        self.calculate_total_margin()
        self.update_weight_inputs()

    def rebalance_unlocked_weights(self, changed_prod_id):
        total_locked = sum(
            data.get("weight", 0) for data in self.product_weights.values() if data.get("locked", 0)
        )
        changed_weight = self.product_weights[changed_prod_id]["weight"]
        remaining = max(0, 100 - total_locked - changed_weight)
        unlocked_prods = [
            pid for pid, data in self.product_weights.items()
            if pid != changed_prod_id and not data.get("locked", 0)
        ]
        if not unlocked_prods:
            return
        avg_weight = remaining / len(unlocked_prods)
        for pid in unlocked_prods:
            self.product_weights[pid]["weight"] = avg_weight
            self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (avg_weight, pid))

    def update_weight_inputs(self):
        for row in range(self.table.rowCount()):
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            if not prod_id or prod_id not in self.product_weights:
                continue
            cell_widget = self.table.cellWidget(row, 6)
            if not cell_widget:
                continue
            weight_input = cell_widget.findChild(QLineEdit)
            if weight_input:
                weight = self.product_weights[prod_id]["weight"]
                weight_str = str(int(weight)) if weight == int(weight) else f"{weight:.1f}"
                weight_input.blockSignals(True)
                weight_input.setText(weight_str)
                weight_input.blockSignals(False)

    def save_weights(self):
        old_margin = self.calculate_total_margin()
        saved_count = 0
        for row in range(self.table.rowCount()):
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            if not prod_id or prod_id not in self.product_weights:
                continue
            weight = self.product_weights[prod_id]["weight"]
            is_locked = self.product_weights[prod_id]["locked"]
            self.db.safe_execute(
                "UPDATE products SET store_weight=?, store_weight_locked=? WHERE id=?",
                (weight, is_locked, prod_id),
            )
            saved_count += 1
        new_margin = self.calculate_total_margin()
        if old_margin is not None and new_margin is not None and abs(old_margin - new_margin) > 0.01:
            self.save_margin_log(old_margin, new_margin)
        self.main_app.show_toast(f"✅ 已保存 {saved_count} 项权重数据")
        self.main_app.refresh_store_weight_sync_flag(self.store_id)
        if self.save_callback:
            self.save_callback(self.store_id, new_margin)
        self.close()

    def save_margin_log(self, old_margin, new_margin):
        try:
            time_str = datetime.now().strftime("%H:%M")
            change = new_margin - old_margin
            change_str = f"+{change:.1f}%" if change > 0 else f"{change:.1f}%"
            log_text = f"【权重保存】综合毛利: {old_margin:.1f}% → {new_margin:.1f}% ({change_str})"
            year = datetime.now().year
            month = datetime.now().month
            day = datetime.now().day
            records = self.db.get_store_record(self.store_id, year, month, day)
            records.append({"time": time_str, "text": log_text})
            self.db.save_store_record(self.store_id, year, month, day, records)
        except Exception as e:
            print(f"保存毛利日志失败: {e}")

    def _calc_total_margin_from_db(self):
        """计算当前综合毛利（从数据库权重）"""
        try:
            products = self.db.safe_fetchall(
                "SELECT id, store_weight FROM products WHERE store_id=?", (self.store_id,)
            )
            if not products:
                return None
            total_weight = 0
            total_weighted_margin = 0
            for prod_id, store_weight in products:
                if not store_weight or store_weight <= 0:
                    continue
                specs = self.db.safe_fetchall(
                    "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                    (prod_id,),
                )
                if not specs:
                    continue
                coupon_res = self.db.safe_fetchall(
                    "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?", (prod_id,)
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
                    cost_res = self.db.safe_fetchall(
                        "SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,)
                    )
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
            return (total_weighted_margin / total_weight) * 100 if total_weight > 0 else None
        except Exception as e:
            print(f"计算综合毛利失败: {e}")
            return None

    def init_ui(self):
        layout = QVBoxLayout(self)
        self._debug_smd_label = QLabel("【板块:店铺毛利对话框\n文件:store_margin.py】毛利明细表格/权重设置/操作按钮")
        self._debug_smd_label.setStyleSheet("background-color: #87CEEB; color: #000; font-weight: bold; padding: 1px;")
        self._debug_smd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._debug_smd_label)
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 15, 10, 15)
        self.lbl_title = QLabel(f"📊 {self.store_name} - 毛利明细")
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        self.lbl_total_margin = QLabel("综合毛利: 0.00%")
        self.lbl_total_margin.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #e74c3c; background-color: #fdeaa8; padding: 10px 20px; border-radius: 8px;"
        )
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_total_margin)
        self.lbl_total_orders = QLabel("总订单: 0")
        self.lbl_total_orders.setStyleSheet("font-size: 14px; color: #666; padding: 5px 10px;")
        header_layout.addWidget(self.lbl_total_orders)
        self.lbl_total_amount = QLabel("总销售额: ¥0.00")
        self.lbl_total_amount.setStyleSheet("font-size: 14px; color: #27ae60; padding: 5px 10px; font-weight: bold;")
        header_layout.addWidget(self.lbl_total_amount)
        layout.addWidget(header_widget)
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(["图片", "商品ID", "商品标题", "综合成本", "客单价", "毛利", "权重(%)", "单量", "销售额", "操作"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellChanged.connect(self.on_cell_changed)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        for i, w in enumerate([70, 120, 150, 80, 80, 80, 120, 60, 80, 80]):
            self.table.setColumnWidth(i, w)
        layout.addWidget(self.table)
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        self.btn_auto_balance = QPushButton("⚖️ 自动均分权重")
        self.btn_auto_balance.clicked.connect(self.auto_balance_weights)
        self.btn_profit_calc = QPushButton("🧮 计算利润")
        self.btn_profit_calc.setStyleSheet(
            "QPushButton { background-color: #9b59b6; color: white; font-weight: bold; padding: 5px 15px; border-radius: 3px; }"
            " QPushButton:hover { background-color: #8e44ad; }"
        )
        self.btn_profit_calc.clicked.connect(self.open_profit_calculator)
        self.btn_import_orders = QPushButton("📥 导入订单")
        self.btn_import_orders.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 5px 15px; border-radius: 3px; }"
            " QPushButton:hover { background-color: #219a52; }"
        )
        self.btn_import_orders.clicked.connect(self.import_orders)
        self.btn_sync_weight = QPushButton("🔄 同步订单权重")
        self.btn_sync_weight.setStyleSheet(
            "QPushButton { background-color: #e67e22; color: white; font-weight: bold; padding: 5px 15px; border-radius: 3px; }"
            " QPushButton:hover { background-color: #d35400; }"
        )
        self.btn_sync_weight.clicked.connect(self.sync_order_weight)
        self.btn_save = QPushButton("💾 保存")
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #007bff; color: white; font-weight: bold; padding: 5px 15px; border-radius: 3px; }"
            " QPushButton:hover { background-color: #0056b3; }"
        )
        self.btn_save.clicked.connect(self.save_weights)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_auto_balance)
        btn_layout.addWidget(self.btn_profit_calc)
        btn_layout.addWidget(self.btn_import_orders)
        btn_layout.addWidget(self.btn_sync_weight)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_close)
        layout.addWidget(btn_widget)

    def load_products(self):
        self.table.cellChanged.disconnect()
        products = self.db.safe_fetchall(
            "SELECT id, name, title, image_path, store_weight, store_weight_locked FROM products WHERE store_id=? ORDER BY sort_order",
            (self.store_id,),
        )
        self.product_weights = {prod[0]: {"weight": prod[4] or 0, "locked": 0} for prod in products}
        self.table.setRowCount(len(products))
        for row, prod in enumerate(products):
            prod_id, prod_code, prod_title, image_path, store_weight, store_locked = prod
            if prod_id in self.product_weights:
                self.product_weights[prod_id]["locked"] = store_locked or 0
            img_widget = QWidget()
            img_layout = QVBoxLayout(img_widget)
            img_layout.setContentsMargins(5, 5, 5, 5)
            img_label = QLabel()
            img_label.setFixedSize(60, 60)
            img_label.setScaledContents(False)
            img_label.setAlignment(Qt.AlignCenter)
            if image_path and os.path.exists(image_path):
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    img_label.setPixmap(pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    img_label.setText("❌")
                    img_label.setStyleSheet("background-color: #f5f5f5; color: #999; border: 1px solid #ddd;")
            else:
                img_label.setText("📷")
                img_label.setStyleSheet("background-color: #f5f5f5; color: #999; border: 1px solid #ddd;")
            img_layout.addWidget(img_label)
            self.table.setCellWidget(row, 0, img_widget)
            self.table.setRowHeight(row, 70)
            item_id = QTableWidgetItem(str(prod_code))
            item_id.setFlags(item_id.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, item_id)
            item_title = QTableWidgetItem(prod_title or "")
            item_title.setFlags(item_title.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, item_title)
            cost, price, margin = self.get_product_margin(prod_id)
            self.table.setItem(row, 3, QTableWidgetItem(f"{cost:.2f}" if cost else "0.00"))
            item_price = QTableWidgetItem(f"{price:.2f}" if price else "0.00")
            item_price.setFlags(item_price.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, item_price)
            margin_text = f"{margin:.2f}%" if margin else "0.00%"
            item_margin = QTableWidgetItem(margin_text)
            item_margin.setFlags(item_margin.flags() & ~Qt.ItemIsEditable)
            if margin and margin < 10:
                item_margin.setBackground(QColor("#ffcccc"))
            elif margin and margin > 30:
                item_margin.setBackground(QColor("#ccffcc"))
            self.table.setItem(row, 5, item_margin)
            weight = store_weight or 0
            is_locked = store_locked or 0
            weight_widget = QWidget()
            weight_layout = QHBoxLayout(weight_widget)
            weight_layout.setContentsMargins(2, 2, 2, 2)
            weight_layout.setSpacing(5)
            left_widget = QWidget()
            left_layout = QVBoxLayout(left_widget)
            left_layout.setContentsMargins(0, 0, 0, 0)
            weight_str = str(int(weight)) if weight == int(weight) else f"{weight:.1f}"
            weight_input = QLineEdit(weight_str)
            weight_input.setAlignment(Qt.AlignCenter)
            weight_input.setFixedHeight(25)
            weight_input.setValidator(QDoubleValidator(0, 100, 1, weight_input))
            weight_input.setStyleSheet(
                "QLineEdit { background-color: #e8f5e9; border: 1px solid #4caf50; border-radius: 3px; padding: 2px; font-weight: bold; color: #2e7d32; }"
            )
            weight_input.installEventFilter(self)
            weight_input.setProperty("row", row)
            weight_input.setProperty("prod_id", prod_id)
            weight_input.textChanged.connect(lambda text, pid=prod_id: self.on_weight_changed(pid, text))
            weight_input.editingFinished.connect(lambda pid=prod_id: self.on_weight_editing_finished(pid))
            left_layout.addWidget(weight_input)
            right_widget = QWidget()
            right_layout = QVBoxLayout(right_widget)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setAlignment(Qt.AlignCenter)
            lock_label = QLabel("🔒" if is_locked else "")
            lock_label.setAlignment(Qt.AlignCenter)
            lock_label.setFixedSize(25, 25)
            lock_label.setStyleSheet(
                "QLabel { background-color: #ffe0b2; border: 1px solid #ff9800; border-radius: 3px; font-size: 14px; }"
                if is_locked
                else "QLabel { background-color: #f5f5f5; border: 1px dashed #ccc; border-radius: 3px; font-size: 14px; }"
            )
            lock_label.installEventFilter(self)
            lock_label.setProperty("row", row)
            lock_label.setProperty("prod_id", prod_id)
            right_layout.addWidget(lock_label)
            weight_layout.addWidget(left_widget, 3)
            weight_layout.addWidget(right_widget, 1)
            self.table.setCellWidget(row, 6, weight_widget)
            order_label_widget = QWidget()
            order_label_layout = QHBoxLayout(order_label_widget)
            order_label_layout.setContentsMargins(0, 0, 0, 0)
            order_label = QLabel("")
            order_label.setAlignment(Qt.AlignCenter)
            order_label.setStyleSheet("color: #888; font-size: 10px;")
            order_label_layout.addWidget(order_label)
            self.table.setCellWidget(row, 7, order_label_widget)
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_edit = QPushButton("📦")
            btn_edit.setFixedSize(40, 25)
            btn_edit.clicked.connect(lambda checked, pid=prod_id, pc=prod_code, pt=prod_title: self.open_spec_dialog(pid, pc, pt))
            btn_layout.addWidget(btn_edit)
            self.table.setCellWidget(row, 9, btn_widget)
            self.table.setItem(row, 8, QTableWidgetItem("-"))
            self.table.item(row, 1).setData(Qt.UserRole, prod_id)
            order_label.setProperty("prod_id", prod_id)
            self._update_order_label_for_row(row, weight_input, order_label, prod_id)
        self.table.cellChanged.connect(self.on_cell_changed)
        self.calculate_total_margin()
        self.update_total_orders_label()
        self.update_product_avg_price()

    def update_product_avg_price(self):
        """更新所有商品的客单价和销售额列"""
        for row in range(self.table.rowCount()):
            prod_id_item = self.table.item(row, 1)
            if not prod_id_item:
                continue
            prod_id = prod_id_item.data(Qt.UserRole)
            if not prod_id:
                continue
            spec_sales = self.db.safe_fetchall(
                "SELECT ps.sale_price, io.order_count FROM product_specs ps "
                "LEFT JOIN imported_orders io ON io.product_id = ps.product_id AND io.spec_code = ps.spec_code "
                "WHERE ps.product_id = ?",
                (prod_id,)
            )
            total_amount = 0.0
            total_orders = 0
            for sale_price, order_count in spec_sales:
                if sale_price and order_count:
                    total_amount += sale_price * order_count
                    total_orders += order_count
            if total_orders > 0:
                avg_price = total_amount / total_orders
                self.table.item(row, 4).setText(f"¥{avg_price:.2f}")
                self.table.item(row, 8).setText(f"¥{total_amount:.2f}")
            else:
                self.table.item(row, 4).setText("-")
                self.table.item(row, 8).setText("-")

    def _update_order_label_for_row(self, row, weight_input, order_label, prod_id):
        """更新单量显示标签"""
        spec_counts = self.db.safe_fetchall(
            "SELECT spec_code, order_count FROM imported_orders WHERE product_id=?",
            (prod_id,)
        )
        total_prod_orders = sum(sc[1] for sc in spec_counts) if spec_counts else 0
        if total_prod_orders > 0:
            order_label.setText(f"{total_prod_orders}单")
            weight_input.setToolTip(f"订单数: {total_prod_orders}单")
        else:
            order_label.setText("0单")
            weight_input.setToolTip("")

    def get_product_margin(self, product_id):
        specs = self.db.safe_fetchall(
            "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?", (product_id,)
        )
        if not specs:
            return 0, 0, 0
        prod_res = self.db.safe_fetchall(
            "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?", (product_id,)
        )
        coupon = (prod_res[0][0] or 0) if prod_res else 0
        new_customer = (prod_res[0][1] or 0) if prod_res else 0
        max_discount = max(coupon, new_customer)
        total_weighted_margin = total_weight = total_cost = total_price = 0
        for spec_code, sale_price, weight in specs:
            if not sale_price or sale_price <= 0:
                continue
            weight = weight or 0
            cost_res = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code=?", (spec_code,))
            cost = cost_res[0][0] if cost_res and cost_res[0][0] else 0
            final_price = sale_price - max_discount
            if final_price > 0 and cost > 0:
                margin = (final_price - cost) / final_price
                total_weighted_margin += margin * weight
                total_weight += weight
            total_cost += cost * weight
            total_price += sale_price * weight
        if total_weight > 0:
            return (
                total_cost / total_weight,
                total_price / total_weight,
                (total_weighted_margin / total_weight) * 100,
            )
        return 0, 0, 0

    def calculate_total_margin(self):
        total_weight = 0
        total_weighted_margin = 0
        for row in range(self.table.rowCount()):
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            cell_widget = self.table.cellWidget(row, 6)
            if not cell_widget:
                continue
            weight_input = cell_widget.findChild(QLineEdit)
            margin_item = self.table.item(row, 5)
            if not weight_input or not margin_item:
                continue
            try:
                weight = float(weight_input.text()) if weight_input.text() else 0
                margin = float(margin_item.text().replace("%", ""))
            except ValueError:
                continue
            total_weight += weight
            total_weighted_margin += margin * weight
        total_margin = (total_weighted_margin / total_weight) if total_weight > 0 else 0
        self.lbl_total_margin.setText(f"综合毛利: {total_margin:.2f}%")
        if total_margin < 10:
            self.lbl_total_margin.setStyleSheet(
                "font-size: 20px; font-weight: bold; color: #c0392b; background-color: #fdeaa8; padding: 10px 20px; border-radius: 8px;"
            )
        elif total_margin > 30:
            self.lbl_total_margin.setStyleSheet(
                "font-size: 20px; font-weight: bold; color: #27ae60; background-color: #d5f5e3; padding: 10px 20px; border-radius: 8px;"
            )
        else:
            self.lbl_total_margin.setStyleSheet(
                "font-size: 20px; font-weight: bold; color: #e74c3c; background-color: #fdeaa8; padding: 10px 20px; border-radius: 8px;"
            )

    def open_profit_calculator(self):
        margin_text = self.lbl_total_margin.text()
        try:
            margin_rate = float(margin_text.replace("%", "").replace("综合毛利:", "").strip())
        except ValueError:
            margin_rate = 0.0
        avg_price = self.calculate_weighted_avg_price()
        self.main_app.open_profit_calculator_dialog(
            margin_rate, avg_price, self.store_id, self.store_name, "store", self, self.db
        )

    def calculate_weighted_avg_price(self):
        total_weight = 0.0
        weighted_price = 0.0
        for row in range(self.table.rowCount()):
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            cell_widget = self.table.cellWidget(row, 6)
            if not cell_widget:
                continue
            weight_input = cell_widget.findChild(QLineEdit)
            price_item = self.table.item(row, 4)
            if not weight_input or not price_item:
                continue
            try:
                weight = float(weight_input.text()) if weight_input.text() else 0
                price = float(price_item.text()) if price_item.text() else 0
                if price > 0 and weight > 0:
                    weighted_price += price * weight
                    total_weight += weight
            except ValueError:
                continue
        return weighted_price / total_weight if total_weight > 0 else 0.0

    def on_cell_changed(self, row, col):
        pass

    def toggle_lock(self, row, prod_id):
        current = self.product_weights.get(prod_id, {})
        is_locked = current.get("locked", 0)
        new_locked = 1 if not is_locked else 0
        self.db.safe_execute("UPDATE products SET store_weight_locked=? WHERE id=?", (new_locked, prod_id))
        if new_locked == 1:
            total_locked = sum(
                data.get("weight", 0) for pid, data in self.product_weights.items()
                if pid != prod_id and data.get("locked", 0)
            )
            remaining = 100 - total_locked
            if current.get("weight", 0) > remaining:
                self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (remaining, prod_id))
        self.load_products()

    def auto_balance_weights(self):
        unlocked_rows = []
        for row in range(self.table.rowCount()):
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            if prod_id and not self.product_weights.get(prod_id, {}).get("locked", 0):
                unlocked_rows.append(prod_id)
        if not unlocked_rows:
            return
        total_locked = sum(
            data.get("weight", 0) for data in self.product_weights.values() if data.get("locked", 0)
        )
        remaining = 100 - total_locked
        avg_weight = (remaining / len(unlocked_rows)) if remaining > 0 else 0
        for prod_id in unlocked_rows:
            self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (avg_weight, prod_id))
        self.load_products()

    def on_cell_double_clicked(self, row, col):
        if col == 6:
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            if prod_id:
                is_locked = self.product_weights.get(prod_id, {}).get("locked", 0)
                if is_locked:
                    self.toggle_lock(row, prod_id)
                    QMessageBox.information(self, "已解锁", "权重已解锁，可以编辑！")
                else:
                    self.is_editing = True
                    self.table.editItem(self.table.item(row, 6))

    def show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row, col = item.row(), item.column()
        prod_id = self.table.item(row, 1).data(Qt.UserRole)
        menu = QMenu(self)
        action_edit = QAction("📦 编辑规格", self)
        action_edit.triggered.connect(lambda: self.open_spec_dialog_by_id(prod_id))
        menu.addAction(action_edit)
        if col == 6 and prod_id:
            is_locked = self.product_weights.get(prod_id, {}).get("locked", 0)
            if is_locked:
                action_unlock = QAction("🔓 解锁权重", self)
                action_unlock.triggered.connect(lambda: self.toggle_lock(row, prod_id))
                menu.addAction(action_unlock)
            else:
                action_lock = QAction("🔒 锁定权重", self)
                action_lock.triggered.connect(lambda: self.toggle_lock(row, prod_id))
                menu.addAction(action_lock)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def open_spec_dialog_by_id(self, product_id):
        prod = self.db.safe_fetchall("SELECT name, title FROM products WHERE id=?", (product_id,))
        if prod:
            self.open_spec_dialog(product_id, prod[0][0], prod[0][1])

    def open_spec_dialog(self, product_id, product_code, product_title):
        """通过 main_app 打开规格对话框，避免 dialogs 依赖主模块中的 ProductSpecDialog"""
        self.main_app.open_product_spec_dialog(self.db, product_id, product_code, product_title, self)

    def import_orders(self):
        """导入订单功能"""
        if not OPENPYXL_AVAILABLE:
            QMessageBox.warning(self, "缺少依赖", "请先安装 openpyxl 库：\npip install openpyxl")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择订单Excel文件", "", "Excel文件 (*.xlsx *.xls)")
        if not file_path:
            return
        try:
            wb = load_workbook(file_path, data_only=True)
            sheet = wb.active
            headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
            if not headers or all(h == "" for h in headers):
                QMessageBox.warning(self, "错误", "Excel文件没有找到有效的表头行")
                return
            col_mapping = self._auto_detect_columns(headers)
            if not all(col_mapping.values()):
                col_mapping = self._show_column_mapping_dialog(headers, col_mapping)
                if not col_mapping:
                    return
            product_id_col = col_mapping["product_id"]
            spec_code_col = col_mapping["spec_code"]
            quantity_col = col_mapping["quantity"]
            products_in_store = self.db.safe_fetchall(
                "SELECT id, name FROM products WHERE store_id=? ORDER BY sort_order", (self.store_id,)
            )
            if not products_in_store:
                QMessageBox.information(self, "提示", "当前店铺没有任何商品，请先添加商品")
                return
            product_code_to_id = {str(p[1]): p[0] for p in products_in_store}
            product_codes_in_store = set(str(p[1]) for p in products_in_store)
            all_store_specs = {}
            for prod_id, prod_code in products_in_store:
                specs = self.db.safe_fetchall(
                    "SELECT spec_code FROM product_specs WHERE product_id=?", (prod_id,)
                )
                all_store_specs[prod_id] = set(str(s[0]) for s in specs if s[0])
            order_data = {}
            excel_product_codes_found = set()
            total_row_count = 0
            for row in sheet.iter_rows(min_row=2, values_only=True):
                total_row_count += 1
                if total_row_count > 10000:
                    break
                try:
                    product_id_value = str(row[product_id_col]).strip() if product_id_col < len(row) else ""
                    spec_code_value = str(row[spec_code_col]).strip() if spec_code_col < len(row) else ""
                    quantity_value = row[quantity_col] if quantity_col < len(row) else None
                except:
                    continue
                if not product_id_value or product_id_value == "None":
                    continue
                if product_id_value not in product_codes_in_store:
                    continue
                excel_product_codes_found.add(product_id_value)
                prod_id = product_code_to_id.get(product_id_value)
                if prod_id is None:
                    continue
                quantity = 1
                if quantity_value is not None:
                    try:
                        quantity = max(1, int(quantity_value))
                    except (ValueError, TypeError):
                        quantity = 1
                spec_codes = all_store_specs.get(prod_id, set())
                spec_code_str = str(spec_code_value).strip() if spec_code_value else ""
                if spec_code_str and spec_code_str != "None" and spec_code_str in spec_codes:
                    key = (prod_id, spec_code_str)
                    if key not in order_data:
                        order_data[key] = 0
                    order_data[key] += quantity
            missing_product_codes = product_codes_in_store - excel_product_codes_found
            if missing_product_codes:
                msg = f"以下商品ID在表格中没有订单记录：\n{', '.join(missing_product_codes)}\n\n是否继续同步（未匹配的商品链接权重将设为0）？"
                reply = QMessageBox.question(self, "部分商品无订单", msg, QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    return
            import_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.safe_execute("DELETE FROM imported_orders WHERE store_id=?", (self.store_id,))
            print(f"[DEBUG] 准备插入订单数据: {order_data}")
            for (prod_id, spec_code), count in order_data.items():
                print(f"[DEBUG] 插入: store_id={self.store_id}, prod_id={prod_id}, spec_code={spec_code}, count={count}")
                self.db.safe_execute(
                    "INSERT INTO imported_orders (store_id, product_id, spec_code, order_count, import_time) VALUES (?, ?, ?, ?, ?)",
                    (self.store_id, prod_id, spec_code, count, import_time)
                )
            self.main_app.show_toast(f"✅ 已导入 {len(order_data)} 条订单数据")
            self.sync_order_weight()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入订单失败：\n{str(e)}")

    def _auto_detect_columns(self, headers):
        """自动检测列映射"""
        mapping = {"product_id": None, "spec_code": None, "quantity": None}
        product_id_keywords = ["商品id", "商品ID", "id", "产品id", "产品ID", "product_id"]
        spec_code_keywords = ["规格编码", "规格code", "spec_code", "规格code", "sku", "SKU"]
        quantity_keywords = ["数量", "订单数量", "quantity", "count", "num", "销售数量"]
        for idx, header in enumerate(headers):
            header_lower = header.lower().strip()
            if mapping["product_id"] is None:
                for kw in product_id_keywords:
                    if kw in header_lower:
                        mapping["product_id"] = idx
                        break
            if mapping["spec_code"] is None:
                for kw in spec_code_keywords:
                    if kw in header_lower:
                        mapping["spec_code"] = idx
                        break
            if mapping["quantity"] is None:
                for kw in quantity_keywords:
                    if kw in header_lower:
                        mapping["quantity"] = idx
                        break
        return mapping

    def _show_column_mapping_dialog(self, headers, auto_mapping):
        """显示列映射对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("📋 列映射选择")
        dialog.resize(500, 300)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("请为每个字段选择对应的Excel列："))
        combo_product_id = QComboBox()
        combo_product_id.addItems(["-- 不选择 --"] + headers)
        if auto_mapping["product_id"] is not None:
            combo_product_id.setCurrentIndex(auto_mapping["product_id"] + 1)
        layout.addWidget(QLabel("商品ID列："))
        layout.addWidget(combo_product_id)
        combo_spec_code = QComboBox()
        combo_spec_code.addItems(["-- 不选择 --"] + headers)
        if auto_mapping["spec_code"] is not None:
            combo_spec_code.setCurrentIndex(auto_mapping["spec_code"] + 1)
        layout.addWidget(QLabel("规格编码列："))
        layout.addWidget(combo_spec_code)
        combo_quantity = QComboBox()
        combo_quantity.addItems(["-- 不选择（默认为1） --"] + headers)
        if auto_mapping["quantity"] is not None:
            combo_quantity.setCurrentIndex(auto_mapping["quantity"] + 1)
        layout.addWidget(QLabel("数量列："))
        layout.addWidget(combo_quantity)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确认")
        btn_ok.setStyleSheet("QPushButton { background-color: #27ae60; color: white; padding: 8px 20px; border-radius: 4px; }")
        btn_cancel = QPushButton("取消")
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        result = {"product_id": None, "spec_code": None, "quantity": None}
        def on_ok():
            result["product_id"] = combo_product_id.currentIndex() - 1 if combo_product_id.currentIndex() > 0 else None
            result["spec_code"] = combo_spec_code.currentIndex() - 1 if combo_spec_code.currentIndex() > 0 else None
            result["quantity"] = combo_quantity.currentIndex() - 1 if combo_quantity.currentIndex() > 0 else None
            dialog.accept()
        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dialog.reject)
        if dialog.exec_() == QDialog.Accepted:
            return result
        return None

    def sync_order_weight(self):
        """同步订单权重"""
        print(f"[DEBUG store_margin] sync_order_weight called for store_id={self.store_id}")
        imported_data = self.db.safe_fetchall(
            "SELECT product_id, spec_code, order_count FROM imported_orders WHERE store_id=?",
            (self.store_id,)
        )
        print(f"[DEBUG store_margin] imported_data: {imported_data}")
        if not imported_data:
            self.main_app.show_toast("⚠️ 没有找到已导入的订单数据")
            return
        prod_order_totals = {}
        spec_order_counts = {}
        for product_id, spec_code, order_count in imported_data:
            spec_code_str = str(spec_code).strip()
            if product_id not in prod_order_totals:
                prod_order_totals[product_id] = 0
            prod_order_totals[product_id] += order_count
            key = (product_id, spec_code_str)
            if key not in spec_order_counts:
                spec_order_counts[key] = 0
            spec_order_counts[key] += order_count
        products_in_store = self.db.safe_fetchall(
            "SELECT id FROM products WHERE store_id=?", (self.store_id,)
        )
        store_total_orders = sum(prod_order_totals.get(p[0], 0) for p in products_in_store)
        print(f"[DEBUG] 店铺总订单: {store_total_orders}")
        print(f"[DEBUG] 每个商品订单: {prod_order_totals}")
        print(f"[DEBUG] 每个规格订单: {spec_order_counts}")
        for prod_id in prod_order_totals:
            total = prod_order_totals[prod_id]
            weight = (total / store_total_orders * 100) if store_total_orders > 0 else 0
            print(f"[DEBUG] 商品 {prod_id}: 订单{total}, 权重{weight:.2f}%")
            self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (weight, prod_id))
            if prod_id in self.product_weights:
                self.product_weights[prod_id]["weight"] = weight
        for prod_id, prod_data in self.product_weights.items():
            specs = self.db.safe_fetchall(
                "SELECT spec_code FROM product_specs WHERE product_id=?", (prod_id,)
            )
            for (spec_code,) in specs:
                if (prod_id, spec_code) not in spec_order_counts:
                    self.db.safe_execute(
                        "UPDATE product_specs SET weight_percent=0 WHERE product_id=? AND spec_code=?",
                        (prod_id, spec_code)
                    )
        for (product_id, spec_code), count in spec_order_counts.items():
            prod_total = prod_order_totals.get(product_id, 0)
            weight = (count / prod_total * 100) if prod_total > 0 else 0
            print(f"[DEBUG] 规格 {product_id}/{spec_code}: 订单{count}, 权重{weight:.2f}%")
            self.db.safe_execute(
                "UPDATE product_specs SET weight_percent=? WHERE product_id=? AND spec_code=?",
                (weight, product_id, str(spec_code))
            )
        for row in range(self.table.rowCount()):
            prod_id_item = self.table.item(row, 1)
            if not prod_id_item:
                continue
            prod_id = prod_id_item.data(Qt.UserRole)
            if not prod_id or prod_id not in prod_order_totals:
                continue
            total = prod_order_totals[prod_id]
            weight = (total / store_total_orders * 100) if store_total_orders > 0 else 0
            cell_widget = self.table.cellWidget(row, 6)
            if cell_widget:
                weight_input = cell_widget.findChild(QLineEdit)
                if weight_input:
                    weight_input.blockSignals(True)
                    weight_input.setText(f"{weight:.2f}%")
                    weight_input.blockSignals(False)
            spec_counts = self.db.safe_fetchall(
                "SELECT spec_code, order_count FROM imported_orders WHERE product_id=?",
                (prod_id,)
            )
            total_prod_orders = sum(sc[1] for sc in spec_counts) if spec_counts else 0
            order_label_widget = self.table.cellWidget(row, 7)
            if order_label_widget:
                order_label = order_label_widget.findChild(QLabel)
                if order_label:
                    order_label.setText(f"{total_prod_orders}单")
            if weight_input and total_prod_orders > 0:
                weight_input.setToolTip(f"订单数: {total_prod_orders}单")
        self.update_total_orders_label()
        self.update_product_avg_price()
        self.main_app.show_toast("✅ 订单权重已同步")
        self.main_app.refresh_store_weight_sync_flag(self.store_id)

    def update_total_orders_label(self):
        """更新总订单和综合客单价标签"""
        imported_data = self.db.safe_fetchall(
            "SELECT SUM(order_count) FROM imported_orders WHERE store_id=?",
            (self.store_id,)
        )
        total = imported_data[0][0] if imported_data and imported_data[0][0] else 0
        total_amount = 0.0
        for row in range(self.table.rowCount()):
            prod_id_item = self.table.item(row, 1)
            if not prod_id_item:
                continue
            prod_id = prod_id_item.data(Qt.UserRole)
            if not prod_id:
                continue
            spec_sales = self.db.safe_fetchall(
                "SELECT ps.sale_price, io.order_count FROM product_specs ps "
                "LEFT JOIN imported_orders io ON io.product_id = ps.product_id AND io.spec_code = ps.spec_code "
                "WHERE ps.product_id = ?",
                (prod_id,)
            )
            for sale_price, order_count in spec_sales:
                if sale_price and order_count:
                    total_amount += sale_price * order_count
        if total > 0:
            avg_price = total_amount / total
            self.lbl_total_orders.setText(f"总订单: {total} | 综合客单价: ¥{avg_price:.2f}")
        else:
            self.lbl_total_orders.setText(f"总订单: 0")
        self.lbl_total_amount.setText(f"总销售额: ¥{total_amount:.2f}")

    def update_weight_display_with_orders(self):
        """更新权重列显示单量"""
        for row in range(self.table.rowCount()):
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            if not prod_id:
                continue
            spec_counts = self.db.safe_fetchall(
                "SELECT spec_code, order_count FROM imported_orders WHERE product_id=?",
                (prod_id,)
            )
            total_prod_orders = sum(sc[1] for sc in spec_counts) if spec_counts else 0
            cell_widget = self.table.cellWidget(row, 6)
            if not cell_widget:
                continue
            weight_input = cell_widget.findChild(QLineEdit)
            if weight_input:
                current_weight = weight_input.text()
                if total_prod_orders > 0:
                    weight_input.setToolTip(f"订单数: {total_prod_orders}")


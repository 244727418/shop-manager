# -*- coding: utf-8 -*-
"""店铺毛利管理对话框"""
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QWidget, QLineEdit, QPushButton, QMessageBox, QMenu, QAction,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QColor, QPixmap, QDoubleValidator


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
        layout.addWidget(header_widget)
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["图片", "商品ID", "商品标题", "综合成本", "售价", "毛利", "权重(%)", "操作"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellChanged.connect(self.on_cell_changed)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        for i, w in enumerate([70, 80, 150, 80, 80, 80, 120]):
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
            self.table.setItem(row, 4, QTableWidgetItem(f"{price:.2f}" if price else "0.00"))
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
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_edit = QPushButton("📦")
            btn_edit.setFixedSize(40, 25)
            btn_edit.clicked.connect(lambda checked, pid=prod_id, pc=prod_code, pt=prod_title: self.open_spec_dialog(pid, pc, pt))
            btn_layout.addWidget(btn_edit)
            self.table.setCellWidget(row, 7, btn_widget)
            self.table.item(row, 1).setData(Qt.UserRole, prod_id)
        self.table.cellChanged.connect(self.on_cell_changed)
        self.calculate_total_margin()

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

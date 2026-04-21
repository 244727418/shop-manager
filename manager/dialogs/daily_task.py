# -*- coding: utf-8 -*-
"""每日任务对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QTextEdit, QPushButton,
    QWidget, QScrollArea, QFrame, QCheckBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QDateTime
from PyQt5.QtGui import QFont


class DailyTaskDialog(QDialog):
    """每日任务对话框 - 大盘分析和亏损链接优化"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.main_app = parent
        self.setWindowTitle("📋 每日任务 - 大盘分析")
        self.setWindowFlags(Qt.Window)
        self.resize(1000, 700)
        self.init_ui()
        self.start_reminder_check()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self._debug_dtd_label = QLabel("【板块:任务对话框\n文件:daily_task.py】大盘分析/亏损链接优化/任务列表/代办提醒")
        self._debug_dtd_label.setStyleSheet("background-color: #FFB6C1; color: #000; font-weight: bold; padding: 1px; font-size: 11px;")
        self._debug_dtd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._debug_dtd_label)

        header = QLabel("📊 每日任务大盘")
        header.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px; color: #2c3e50;")
        layout.addWidget(header)

        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)

        self.main_task_list = QListWidget()
        self.main_task_list.addItem("🔴 亏损链接优化 - 检查所有亏损商品")
        self.main_task_list.currentRowChanged.connect(self.on_task_selected)
        tab_layout.addWidget(QLabel("📋 任务列表:"))
        tab_layout.addWidget(self.main_task_list)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("选择任务查看详情...")
        tab_layout.addWidget(QLabel("📝 任务详情:"))
        tab_layout.addWidget(self.detail_text)

        layout.addWidget(tab_widget)

        self.reminder_label = QLabel("🔔 待办提醒")
        self.reminder_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px; color: #e74c3c;")
        layout.addWidget(self.reminder_label)

        self.reminder_list = QListWidget()
        self.reminder_list.itemClicked.connect(self.on_reminder_item_clicked)
        layout.addWidget(self.reminder_list)

        self.load_tasks()
        self.load_reminders()

        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self.on_refresh)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_refresh)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def start_reminder_check(self):
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(30000)

    def check_reminders(self):
        try:
            now = QDateTime.currentDateTime()
            current_time_str = now.toString("yyyy-MM-dd HH:mm:ss")

            reminders = self.db.safe_fetchall(
                """SELECT id, store_id, product_id, task_content, remind_time
                   FROM task_reminders WHERE is_reminded = 0 ORDER BY remind_time"""
            )

            for rem_id, store_id, product_id, task_content, remind_time in reminders:
                if str(remind_time) <= current_time_str:
                    self.show_reminder_popup(rem_id, store_id, product_id, task_content, remind_time)
                    self.db.safe_execute(
                        "UPDATE task_reminders SET is_reminded = 1 WHERE id = ?",
                        (rem_id,)
                    )
        except Exception as e:
            print(f"检查提醒失败: {e}")

    def show_reminder_popup(self, rem_id, store_id, product_id, task_content, remind_time):
        store_name = ""
        try:
            store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
            if store_res and store_res[0][0]:
                store_name = store_res[0][0]
        except:
            pass

        product_code = str(product_id)
        product_title = ""
        try:
            prod_res = self.db.safe_fetchall("SELECT name, title FROM products WHERE id=?", (product_id,))
            if prod_res and prod_res[0][0]:
                product_code = prod_res[0][0]
                product_title = prod_res[0][1] if prod_res[0][1] else ""
        except:
            pass

        msg = QMessageBox(self)
        msg.setWindowTitle(f"🔔 提醒 - {store_name}")
        msg.setText(f"""<b>⏰ 时间: {remind_time}</b><br><br>
<b>🏪 店铺:</b> {store_name}<br><br>
<b>📦 链接ID:</b> {product_code} <button id="copy_btn">复制</button><br><br>
<b>📝 任务内容:</b><br>{task_content}""")
        msg.setTextFormat(Qt.RichText)
        msg.setIcon(QMessageBox.Information)

        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(product_code)

        msg.exec_()

    def load_reminders(self):
        self.reminder_list.clear()
        try:
            reminders = self.db.safe_fetchall(
                """SELECT id, store_id, product_id, task_content, remind_time, is_reminded
                   FROM task_reminders ORDER BY remind_time DESC LIMIT 50"""
            )

            for rem_id, store_id, product_id, task_content, remind_time, is_reminded in reminders:
                store_name = ""
                try:
                    store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
                    if store_res and store_res[0][0]:
                        store_name = store_res[0][0]
                except:
                    pass

                product_code = str(product_id)
                try:
                    prod_res = self.db.safe_fetchall("SELECT name FROM products WHERE id=?", (product_id,))
                    if prod_res and prod_res[0][0]:
                        product_code = prod_res[0][0]
                except:
                    pass

                status_icon = "✅" if is_reminded else "🔔"
                item_text = f"{status_icon} [{store_name}] {product_code} - {remind_time}"
                self.reminder_list.addItem(item_text)

        except Exception as e:
            print(f"加载提醒失败: {e}")

    def on_reminder_item_clicked(self, item):
        pass

    def on_refresh(self):
        self.load_tasks()
        self.load_reminders()
        self.show_toast("已刷新")

    def show_toast(self, message):
        if self.main_app and hasattr(self.main_app, 'show_toast'):
            self.main_app.show_toast(message)

    def load_tasks(self):
        self.main_task_list.clear()

        self.main_task_list.addItem("🔴 亏损链接优化 - 检查所有亏损商品")

        total_products = self.db.safe_fetchall("SELECT COUNT(*) FROM products")
        total = total_products[0][0] if total_products and total_products[0][0] else 0

        self.task_data = {
            0: {"title": "亏损链接优化", "total": total}
        }

        daily_tasks = self.db.safe_fetchall(
            """SELECT id, store_id, product_id, task_content, is_completed, created_time
               FROM daily_tasks WHERE is_completed = 0 ORDER BY created_time DESC LIMIT 20"""
        )

        for task_id, store_id, product_id, task_content, is_completed, created_time in daily_tasks:
            store_name = ""
            try:
                store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
                if store_res and store_res[0][0]:
                    store_name = store_res[0][0]
            except:
                pass

            product_code = str(product_id)
            try:
                prod_res = self.db.safe_fetchall("SELECT name FROM products WHERE id=?", (product_id,))
                if prod_res and prod_res[0][0]:
                    product_code = prod_res[0][0]
            except:
                pass

            status_icon = "✅" if is_completed else "📋"
            item_text = f"{status_icon} [{store_name}] {product_code}: {task_content[:30]}..."
            self.main_task_list.addItem(item_text)

    def on_task_selected(self, index):
        if index < 0:
            return

        if index == 0:
            self.analyze_loss_links()
        elif index >= 1:
            self.show_daily_task_detail(index)

    def show_daily_task_detail(self, index):
        self.detail_text.clear()
        daily_tasks = self.db.safe_fetchall(
            """SELECT id, store_id, product_id, task_content, is_completed, created_time
               FROM daily_tasks WHERE is_completed = 0 ORDER BY created_time DESC LIMIT 20"""
        )

        if index - 1 < len(daily_tasks):
            task_id, store_id, product_id, task_content, is_completed, created_time = daily_tasks[index - 1]

            store_name = ""
            try:
                store_res = self.db.safe_fetchall("SELECT name FROM stores WHERE id=?", (store_id,))
                if store_res and store_res[0][0]:
                    store_name = store_res[0][0]
            except:
                pass

            product_code = str(product_id)
            product_title = ""
            try:
                prod_res = self.db.safe_fetchall("SELECT name, title FROM products WHERE id=?", (product_id,))
                if prod_res and prod_res[0][0]:
                    product_code = prod_res[0][0]
                    product_title = prod_res[0][1] if prod_res[0][1] else ""
            except:
                pass

            self.detail_text.append("=" * 70)
            self.detail_text.append(f"📋 每日任务详情")
            self.detail_text.append("=" * 70)
            self.detail_text.append(f"🏪 店铺: {store_name}")
            self.detail_text.append(f"📦 链接ID: {product_code}")
            if product_title:
                self.detail_text.append(f"📝 标题: {product_title}")
            self.detail_text.append(f"📅 创建时间: {created_time}")
            self.detail_text.append(f"📝 任务内容:\n{task_content}")

            btn_complete = QPushButton("标记完成")
            btn_complete.clicked.connect(lambda: self.complete_task(task_id))
            self.detail_text.append("")
            self.detail_text.append("")

    def complete_task(self, task_id):
        try:
            self.db.safe_execute("UPDATE daily_tasks SET is_completed = 1 WHERE id = ?", (task_id,))
            self.load_tasks()
            self.show_toast("✅ 任务已标记完成")
        except Exception as e:
            print(f"完成任务失败: {e}")

    def analyze_loss_links(self):
        self.detail_text.clear()
        self.detail_text.append("=" * 70)
        self.detail_text.append("🔴 亏损链接分析报告")
        self.detail_text.append("=" * 70)

        products = self.db.safe_fetchall("""
            SELECT p.id, p.name, s.name as store_name, p.current_roi, p.return_rate,
                   (SELECT COUNT(*) FROM product_specs WHERE product_id = p.id) as spec_count
            FROM products p
            LEFT JOIN stores s ON p.store_id = s.id
            ORDER BY s.name, p.name
        """)

        if not products:
            self.detail_text.append("暂无链接数据，请先添加链接！")
            return

        loss_count = 0
        break_even_count = 0
        profit_count = 0
        no_roi_count = 0

        current_store = ""

        for p in products:
            p_id, name, store_name, current_roi, return_rate, spec_count = p

            if store_name != current_store:
                current_store = store_name
                self.detail_text.append("")
                self.detail_text.append(f"🏪 店铺: {store_name}")
                self.detail_text.append("-" * 50)

            if not current_roi or current_roi == 0:
                no_roi_count += 1
                self.detail_text.append(f"⚪ {name}: 未填写投产 (规格数:{spec_count})")
                continue

            rows = self.db.safe_fetchall(
                "SELECT spec_code, sale_price, weight_percent FROM product_specs WHERE product_id=?",
                (p_id,)
            )

            if not rows:
                self.detail_text.append(f"⚪ {name}: 无规格数据")
                continue

            product_rows = self.db.safe_fetchall(
                "SELECT coupon_amount, new_customer_discount FROM products WHERE id=?",
                (p_id,)
            )
            max_discount = 0
            if product_rows:
                coupon = product_rows[0][0] if product_rows[0][0] else 0
                new_customer = product_rows[0][1] if product_rows[0][1] else 0
                max_discount = max(coupon, new_customer)

            total_weighted_margin = 0.0
            total_weight = 0.0

            for r in rows:
                spec_code, sale_price, weight = r
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
                margin_rate = (total_weighted_margin / total_weight)
            else:
                margin_rate = 0

            if return_rate is None:
                return_rate = 0

            if current_roi > 0 and margin_rate > 0:
                net_profit_rate = (margin_rate * (1 - return_rate / 100) - 0.006 - (1 / current_roi)) * 100
            else:
                net_profit_rate = -100

            if net_profit_rate < -2:
                loss_count += 1
                self.detail_text.append(f"❌ {name}: 净利{net_profit_rate:.1f}% 投产{current_roi:.1f} (亏损)")
            elif net_profit_rate < 1:
                break_even_count += 1
                self.detail_text.append(f"🟡 {name}: 净利{net_profit_rate:.1f}% 投产{current_roi:.1f} (保本)")
            else:
                profit_count += 1
                self.detail_text.append(f"✅ {name}: 净利{net_profit_rate:.1f}% 投产{current_roi:.1f} (盈利)")

        self.detail_text.append("")
        self.detail_text.append("=" * 70)
        self.detail_text.append(f"📊 统计结果:")
        self.detail_text.append(f"  - 亏损链接: {loss_count} 个 (净利率 < -2%)")
        self.detail_text.append(f"  - 保本链接: {break_even_count} 个 (-2% <= 净利率 < 1%)")
        self.detail_text.append(f"  - 盈利链接: {profit_count} 个 (净利率 >= 1%)")
        self.detail_text.append(f"  - 未填写投产: {no_roi_count} 个")
        self.detail_text.append(f"  - 总链接数: {loss_count + break_even_count + profit_count + no_roi_count} 个")

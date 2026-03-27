# -*- coding: utf-8 -*-
"""每日任务对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QTextEdit, QPushButton
)
from PyQt5.QtCore import Qt


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

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        
        self._debug_dtd_label = QLabel("【板块:任务对话框\n文件:daily_task.py】大盘分析/亏损链接优化/任务列表")
        self._debug_dtd_label.setStyleSheet("background-color: #FFB6C1; color: #000; font-weight: bold; padding: 1px; font-size: 13px;")
        self._debug_dtd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._debug_dtd_label)
        
        header = QLabel("📊 每日任务大盘")
        header.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px; color: #2c3e50;")
        layout.addWidget(header)

        self.task_list_widget = QListWidget()
        layout.addWidget(self.task_list_widget)

        self.load_tasks()

        detail_layout = QHBoxLayout()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("选择任务查看详情...")
        detail_layout.addWidget(self.detail_text)

        self.task_list_widget.currentRowChanged.connect(self.on_task_selected)

        layout.addLayout(detail_layout)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def load_tasks(self):
        self.task_list_widget.clear()

        self.task_list_widget.addItem("🔴 亏损链接优化 - 检查所有亏损商品")

        total_products = self.db.safe_fetchall("SELECT COUNT(*) FROM products")
        total = total_products[0][0] if total_products and total_products[0][0] else 0

        self.task_data = {
            0: {"title": "亏损链接优化", "total": total}
        }

    def on_task_selected(self, index):
        if index < 0:
            return

        if index == 0:
            self.analyze_loss_links()

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

            if net_profit_rate < -5:
                loss_count += 1
                self.detail_text.append(f"❌ {name}: 净利{net_profit_rate:.1f}% 投产{current_roi:.1f} (亏损)")
            elif net_profit_rate <= 5:
                break_even_count += 1
                self.detail_text.append(f"🟡 {name}: 净利{net_profit_rate:.1f}% 投产{current_roi:.1f} (保本)")
            else:
                profit_count += 1

        self.detail_text.append("")
        self.detail_text.append("=" * 70)
        self.detail_text.append(f"📊 统计结果:")
        self.detail_text.append(f"  - 亏损链接: {loss_count} 个 (净利率 < -5%)")
        self.detail_text.append(f"  - 保本链接: {break_even_count} 个 (-5% <= 净利率 <= 5%)")
        self.detail_text.append(f"  - 盈利链接: {profit_count} 个 (净利率 > 5%)")
        self.detail_text.append(f"  - 未填写投产: {no_roi_count} 个")
        self.detail_text.append(f"  - 总链接数: {loss_count + break_even_count + profit_count + no_roi_count} 个")

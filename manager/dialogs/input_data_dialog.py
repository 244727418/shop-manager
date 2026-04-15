# -*- coding: utf-8 -*-
"""录入数据对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton
)
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtCore import Qt


class InputDataDialog(QDialog):
    """手动录入数据对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📝 录入数据")
        self.resize(400, 450)
        self.calculated_values = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        debug_label = QLabel("🔧 调试: input_data_dialog.py")
        debug_label.setStyleSheet("font-size: 10px; color: #999; background-color: #f0f0f0; padding: 2px 8px; border-bottom: 1px solid #ddd;")
        debug_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        debug_label.setCursor(Qt.IBeamCursor)
        layout.addWidget(debug_label)

        title = QLabel("📝 请填写以下数据（手动输入项）")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.input_fields = {}
        input_fields_config = [
            ("实发订单", "实际发货的订单数量"),
            ("实发金额", "实际发货的总金额（元）"),
            ("毛利润", "毛利金额（元）"),
            ("退款金额", "退款的总金额（元）"),
            ("退款订单", "退款的订单数量"),
            ("推广费", "推广费用（元）"),
            ("扣款", "扣款金额（元）"),
            ("其他服务", "其他服务费用（元）"),
            ("其他", "其他费用（可以为负值）"),
        ]

        for field_name, tooltip in input_fields_config:
            le = QLineEdit()
            le.setPlaceholderText(f"请输入{field_name}")
            le.setToolTip(tooltip)
            le.setStyleSheet("padding: 6px; border: 1px solid #ccc; border-radius: 3px; font-size: 13px;")
            if field_name in ["实发金额", "毛利润", "退款金额", "推广费", "扣款", "其他服务", "其他"]:
                le.setValidator(QDoubleValidator())
            elif field_name in ["实发订单", "退款订单"]:
                le.setValidator(QIntValidator(0, 99999999))
            self.input_fields[field_name] = le
            label = QLabel(f"{field_name}:")
            label.setStyleSheet("color: #555; font-weight: bold;")
            form_layout.addRow(label, le)

        layout.addLayout(form_layout)

        calc_btn = QPushButton("🧮 计算并预览")
        calc_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        calc_btn.clicked.connect(self.calculate)
        layout.addWidget(calc_btn)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet("""
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            font-size: 12px;
        """)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        btn_layout = QVBoxLayout()
        btn_confirm = QPushButton("✅ 确认保存")
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #219a52; }
        """)
        btn_confirm.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_confirm)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def calculate(self):
        try:
            actual_orders = int(self.input_fields["实发订单"].text() or 0)
            actual_amount = float(self.input_fields["实发金额"].text() or 0)
            gross_profit = float(self.input_fields["毛利润"].text() or 0)
            refund_amount = float(self.input_fields["退款金额"].text() or 0)
            refund_orders = int(self.input_fields["退款订单"].text() or 0)
            promotion_fee = float(self.input_fields["推广费"].text() or 0)
            deduction = float(self.input_fields["扣款"].text() or 0)
            other_service = float(self.input_fields["其他服务"].text() or 0)
            other = float(self.input_fields["其他"].text() or 0)

            if actual_orders == 0 or actual_amount == 0:
                self.preview_label.setText("⚠️ 实发订单和实发金额不能为0")
                return

            gross_margin_rate = (gross_profit / actual_amount * 100) if actual_amount > 0 else 0
            refund_rate_by_amount = (refund_amount / actual_amount * 100) if actual_amount > 0 else 0
            refund_rate_by_orders = (refund_orders / actual_orders * 100) if actual_orders > 0 else 0
            unit_price = actual_amount / actual_orders
            promotion_ratio = (promotion_fee / actual_amount * 100) if actual_amount > 0 else 0
            tech_fee = actual_amount * 0.006
            net_profit = gross_profit - refund_amount - promotion_fee - deduction - other_service + other - tech_fee
            net_margin_rate = (net_profit / actual_amount * 100) if actual_amount > 0 else 0
            profit_per_order = net_profit / actual_orders if actual_orders > 0 else 0

            self.calculated_values = {
                "gross_margin_rate": gross_margin_rate,
                "refund_rate_by_amount": refund_rate_by_amount,
                "refund_rate_by_orders": refund_rate_by_orders,
                "unit_price": unit_price,
                "promotion_ratio": promotion_ratio,
                "tech_fee": tech_fee,
                "net_profit": net_profit,
                "net_margin_rate": net_margin_rate,
                "profit_per_order": profit_per_order,
            }

            preview_text = f"""
<b>自动计算结果预览：</b><br>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━<br>
📊 毛利率: <span style="color:#27ae60">{gross_margin_rate:.2f}%</span><br>
📉 金额退款率: <span style="color:#e74c3c">{refund_rate_by_amount:.2f}%</span><br>
📉 订单退款率: <span style="color:#e74c3c">{refund_rate_by_orders:.2f}%</span><br>
💰 件单价: <span style="color:#3498db">¥{unit_price:.2f}</span><br>
📢 推广占比: <span style="color:#9b59b6">{promotion_ratio:.2f}%</span><br>
🔧 技术服务费: <span style="color:#f39c12">¥{tech_fee:.2f}</span><br>
💵 净利润: <span style="color:#27ae60;font-weight:bold">¥{net_profit:.2f}</span><br>
📈 净利率: <span style="color:#27ae60">{net_margin_rate:.2f}%</span><br>
📊 单笔利润: <span style="color:#3498db">¥{profit_per_order:.2f}</span>
            """
            self.preview_label.setText(preview_text)

        except ValueError:
            self.preview_label.setText("⚠️ 请检查输入数值是否正确")

    def get_data(self):
        return {
            "actual_orders": int(self.input_fields["实发订单"].text() or 0),
            "actual_amount": float(self.input_fields["实发金额"].text() or 0),
            "gross_profit": float(self.input_fields["毛利润"].text() or 0),
            "refund_amount": float(self.input_fields["退款金额"].text() or 0),
            "refund_orders": int(self.input_fields["退款订单"].text() or 0),
            "promotion_fee": float(self.input_fields["推广费"].text() or 0),
            "deduction": float(self.input_fields["扣款"].text() or 0),
            "other_service": float(self.input_fields["其他服务"].text() or 0),
            "other": float(self.input_fields["其他"].text() or 0),
            **self.calculated_values
        }

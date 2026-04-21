# -*- coding: utf-8 -*-
"""店铺毛利管理对话框"""
import os
import json
from datetime import datetime
from PyQt5.QtWidgets import QHeaderView, QAbstractItemView
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTableWidget, QTableWidgetItem,
    QWidget, QLineEdit, QPushButton, QMessageBox, QMenu, QAction,
    QAbstractItemView, QFileDialog, QComboBox, QScrollArea, QHeaderView,
    QApplication
)
from PyQt5.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve, QRect, QTimer, pyqtSignal, QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import QColor, QPixmap, QDoubleValidator, QFont
from PyQt5.QtWidgets import QApplication, QGraphicsOpacityEffect
from PyQt5.QtGui import QClipboard

try:
    from openpyxl import load_workbook
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


class ScalableTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale_factor = 1.0

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.scale_factor = min(2.0, self.scale_factor + 0.1)
            else:
                self.scale_factor = max(0.5, self.scale_factor - 0.1)
            self.apply_scale()
            event.accept()
            return
        super().wheelEvent(event)

    def apply_scale(self):
        base_row_height = 60
        base_header_height = 50

        row_height = int(base_row_height * self.scale_factor)
        header_height = int(base_header_height * self.scale_factor)

        for row in range(self.rowCount()):
            if row == 0 or row % 2 != 0:
                self.setRowHeight(row, row_height)
            else:
                self.setRowHeight(row, int(row_height * 0.4))

        header = self.horizontalHeader()
        header.setFixedHeight(header_height)

        font_size = int(16 * self.scale_factor)
        header_font = QFont()
        header_font.setPointSize(max(10, int(16 * self.scale_factor)))
        header.setFont(header_font)

        table_font = QFont()
        table_font.setPointSize(font_size)
        self.setFont(table_font)

        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    font = item.font()
                    font.setPointSize(font_size)
                    item.setFont(font)


class ImageCell(QWidget):
    cell_hovered = pyqtSignal(int)
    image_view_requested = pyqtSignal(int)
    paste_requested = pyqtSignal(int)
    clear_requested = pyqtSignal(int)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.image_label = None
        self.clear_btn = None
        self.current_pixmap = None
        self.setStyleSheet("border: 2px dashed #cccccc; background-color: #f5f5f5; border-radius: 4px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        self.placeholder = QLabel("Ctrl+V\n粘贴图片")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color: #999999; font-size: 12px;")
        layout.addWidget(self.placeholder)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def enterEvent(self, event):
        self.cell_hovered.emit(self.index)
        self.setFocus()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.clearFocus()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_V:
            self.paste_requested.emit(self.index)
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.current_pixmap:
            self.image_view_requested.emit(self.index)
        super().mouseDoubleClickEvent(event)

    def set_image(self, pixmap):
        self.current_pixmap = pixmap
        self.placeholder.setVisible(False)

        for child in self.children():
            if isinstance(child, QWidget) and child != self.placeholder:
                child.deleteLater()

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setAlignment(Qt.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.image_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.image_label)

        self.clear_btn = QPushButton("×")
        self.clear_btn.setFixedSize(24, 24)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(231, 76, 60, 200);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(192, 57, 43, 255);
            }
        """)
        self.clear_btn.clicked.connect(lambda: self.clear_requested.emit(self.index))
        container_layout.addWidget(self.clear_btn)

        layout = self.layout()
        layout.addWidget(container)

    def clear_image(self):
        for child in self.children():
            if isinstance(child, QWidget) and child != self.placeholder:
                child.deleteLater()
        self.image_label = None
        self.clear_btn = None
        self.current_pixmap = None
        self.placeholder.setVisible(True)

    def has_image(self):
        return self.current_pixmap is not None


class LargeMarginDataDialog(QDialog):
    """放大版毛利数据表格窗口"""
    FORMULAS = {
        "日期": None,
        "实发订单": None,
        "实发金额": None,
        "毛利润": None,
        "毛利率": "毛利润 / 实发金额 × 100%",
        "退款金额": None,
        "金额退款率": "退款金额 / 实发金额 × 100%",
        "退款订单": None,
        "订单退款率": "退款订单 / 实发订单 × 100%",
        "件单价": "实发金额 / 实发订单",
        "推广费": None,
        "推广占比": "推广费 / 实发金额 × 100%",
        "技术服务费": "实发金额 × 0.6%",
        "扣款": None,
        "其他服务": None,
        "其他": None,
        "净利润": "毛利润 - 退款金额 - 推广费 - 扣款 - 其他服务 + 其他 - 技术服务费",
        "净利率": "净利润 / 实发金额 × 100%",
        "单笔利润": "净利润 / 实发订单",
        "日盈亏": "净利润 / 天数",
    }

    def load_all_data(self):
        """从数据库加载所有历史数据"""
        try:
            records = self.db.safe_fetchall("""
                SELECT start_date, end_date, actual_orders, actual_amount, gross_profit,
                       refund_amount, refund_orders, promotion_fee, deduction, other_service, other,
                       gross_margin_rate, refund_rate_by_amount, refund_rate_by_orders,
                       unit_price, promotion_ratio, tech_fee,
                       net_profit, net_margin_rate, profit_per_order
                FROM manual_margin_data WHERE store_id=? ORDER BY start_date ASC, end_date ASC
            """, (self.store_id,))
            return records
        except Exception as e:
            print(f"加载历史数据失败: {e}")
            return []

    def _add_week_comparison_row(self, row, current, previous, GREEN, RED, GRAY):
        """添加较上周对比数据行"""
        current_net_profit = current[17] if current[17] else 0
        previous_net_profit = previous[17] if previous[17] else 0
        current_net_margin = current[18] if current[18] else 0
        previous_net_margin = previous[18] if previous[18] else 0

        current_daily = 0
        if current[0] and current[1]:
            try:
                from datetime import datetime
                start_dt = datetime.strptime(current[0], "%Y-%m-%d")
                end_dt = datetime.strptime(current[1], "%Y-%m-%d")
                days = max(1, (end_dt - start_dt).days + 1)
                current_daily = current_net_profit / days if days > 0 else 0
            except:
                pass

        previous_daily = 0
        if previous[0] and previous[1]:
            try:
                from datetime import datetime
                start_dt = datetime.strptime(previous[0], "%Y-%m-%d")
                end_dt = datetime.strptime(previous[1], "%Y-%m-%d")
                days = max(1, (end_dt - start_dt).days + 1)
                previous_daily = previous_net_profit / days if days > 0 else 0
            except:
                pass

        for col in range(20):
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)

            if col == 0:
                item.setText("较上周")
                item.setBackground(QColor("#e8e8e8"))
            elif col == 1:
                if previous[2] and previous[2] != 0:
                    change = ((current[2] or 0) - (previous[2] or 0)) / abs(previous[2]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 2:
                if (previous[3] or 0) != 0:
                    change = ((current[3] or 0) - (previous[3] or 0)) / abs(previous[3]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 3:
                if (previous[4] or 0) != 0:
                    change = ((current[4] or 0) - (previous[4] or 0)) / abs(previous[4]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 4:
                change = (current[11] or 0) - (previous[11] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
            elif col == 5:
                if (previous[5] or 0) != 0:
                    change = ((current[5] or 0) - (previous[5] or 0)) / abs(previous[5]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 6:
                change = (current[12] or 0) - (previous[12] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
            elif col == 7:
                if previous[6] and previous[6] != 0:
                    change = ((current[6] or 0) - (previous[6] or 0)) / abs(previous[6]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 8:
                change = (current[13] or 0) - (previous[13] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
            elif col == 9:
                if (previous[14] or 0) != 0:
                    change = ((current[14] or 0) - (previous[14] or 0)) / abs(previous[14]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 10:
                if (previous[7] or 0) != 0:
                    change = ((current[7] or 0) - (previous[7] or 0)) / abs(previous[7]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 11:
                change = (current[15] or 0) - (previous[15] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
            elif col == 12:
                if (previous[16] or 0) != 0:
                    change = ((current[16] or 0) - (previous[16] or 0)) / abs(previous[16]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 13:
                if (previous[8] or 0) != 0:
                    change = ((current[8] or 0) - (previous[8] or 0)) / abs(previous[8]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 14:
                if (previous[9] or 0) != 0:
                    change = ((current[9] or 0) - (previous[9] or 0)) / abs(previous[9]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 15:
                if (previous[10] or 0) != 0:
                    change = ((current[10] or 0) - (previous[10] or 0)) / abs(previous[10]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 16:
                if previous_net_profit != 0:
                    change = (current_net_profit - previous_net_profit) / abs(previous_net_profit) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 17:
                change = current_net_margin - previous_net_margin
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
            elif col == 18:
                if (previous[19] or 0) != 0:
                    change = ((current[19] or 0) - (previous[19] or 0)) / abs(previous[19]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 19:
                if previous_daily != 0:
                    change = (current_daily - previous_daily) / abs(previous_daily) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)

            item.setFont(QFont("", -1, QFont.Bold))
            self.table.setItem(row, col, item)
        self.table.setRowHeight(row, 22)

    def __init__(self, store_name, store_id, db, parent=None):
        super().__init__(parent)
        self.store_id = store_id
        self.db = db
        self.parent_dialog = parent
        self.setWindowTitle(f"📊 {store_name} - 毛利数据明细（放大版）")
        self.setStyleSheet("background-color: #f5f5f5;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        header_label = QLabel("📈 毛利数据明细 - 放大查看模式（点击右上角关闭按钮退出）")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; padding: 10px;")
        main_layout.addWidget(header_label)

        self.table = ScalableTableWidget()
        self.table.setColumnCount(21)
        self.table.setHorizontalHeaderLabels([
            "日期", "实发订单", "实发金额", "毛利润", "毛利率", "退款金额", "金额退款率",
            "退款订单", "订单退款率", "件单价", "推广费", "推广占比",
            "技术服务费", "扣款", "其他服务", "其他", "净利润",
            "净利率", "单笔利润", "日盈亏", "操作"
        ])

        records = self.load_all_data()
        total_rows = 2 * len(records) - 1
        self.table.setRowCount(total_rows)

        GREEN = QColor("#27ae60")
        RED = QColor("#e74c3c")
        GRAY = QColor("#999999")

        current_table_row = 0
        for i, record in enumerate(records):
            table_row = current_table_row
            start_date = record[0] if record[0] else ""
            end_date = record[1] if record[1] else ""
            start_display = start_date[5:10] if start_date and len(start_date) >= 10 else start_date
            end_display = end_date[5:10] if end_date and len(end_date) >= 10 else end_date
            date_str = f"{start_display}\n{end_display}"

            days = 1
            if start_date and end_date:
                try:
                    from datetime import datetime
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    days = max(1, (end_dt - start_dt).days + 1)
                except:
                    pass

            net_profit = record[17] if record[17] else 0
            daily_profit = net_profit / days if days > 0 else 0

            values = [
                date_str,
                str(int(record[2])) if record[2] else "0",
                f"¥{record[3]:.2f}" if record[3] else "¥0.00",
                f"¥{record[4]:.2f}" if record[4] else "¥0.00",
                f"{record[11]:.2f}%" if record[11] else "0.00%",
                f"¥{record[5]:.2f}" if record[5] else "¥0.00",
                f"{record[12]:.2f}%" if record[12] else "0.00%",
                str(int(record[6])) if record[6] else "0",
                f"{record[13]:.2f}%" if record[13] else "0.00%",
                f"¥{record[14]:.2f}" if record[14] else "¥0.00",
                f"¥{record[7]:.2f}" if record[7] else "¥0.00",
                f"{record[15]:.2f}%" if record[15] else "0.00%",
                f"¥{record[16]:.2f}" if record[16] else "¥0.00",
                f"¥{record[8]:.2f}" if record[8] else "¥0.00",
                f"¥{record[9]:.2f}" if record[9] else "¥0.00",
                f"¥{record[10]:.2f}" if record[10] else "¥0.00",
                f"¥{record[17]:.2f}" if record[17] else "¥0.00",
                f"{record[18]:.2f}%" if record[18] else "0.00%",
                f"¥{record[19]:.2f}" if record[19] else "¥0.00",
                f"¥{daily_profit:.2f}",
            ]

            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if j == 0:
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                if j == 0:
                    pass
                elif j in [1, 2, 3, 5, 7, 10, 13, 14, 15]:
                    item.setBackground(QColor("#c8e6c9"))
                    item.setForeground(QColor("#1b5e20"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    item.setBackground(QColor("#bbdefb"))
                    item.setForeground(QColor("#0d47a1"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(table_row, j, item)

            delete_btn = QPushButton("🗑️")
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            delete_btn.clicked.connect(lambda checked, r=table_row, idx=i: self.delete_data_row_with_comparison(r, idx))
            self.table.setCellWidget(table_row, 20, delete_btn)
            self.table.setRowHeight(table_row, 60)

            if i > 0:
                self._add_week_comparison_row(table_row + 1, record, records[i - 1], GREEN, RED, GRAY)
                current_table_row += 2
            else:
                current_table_row += 1

        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setGridStyle(Qt.SolidLine)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        table_font = QFont()
        table_font.setPointSize(16)
        self.table.setFont(table_font)

        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #cccccc;
                font-size: 16px;
                border: 2px solid #cccccc;
                border-radius: 6px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 1px;
                text-align: center;
                border: 1px solid #cccccc;
                font-size: 16px;
            }
            QTableWidget::item:selected {
                background-color: #e6f3ff;
                color: black;
                outline: none;
            }
            QHeaderView {
                border: none;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                padding: 1px;
                margin: 0px;
                border: none;
                border-left: 1px solid #cccccc;
                border-bottom: 1px solid #cccccc;
                border-right: 1px solid #cccccc;
                font-size: 16px;
                font-weight: bold;
                min-height: 50px;
            }
        """)

        self.header = self.table.horizontalHeader()
        self.header.setSectionResizeMode(QHeaderView.Interactive)
        self.header.setMinimumSectionSize(80)
        self.header.setStretchLastSection(True)
        self.header.setMouseTracking(True)
        self.header.viewport().setMouseTracking(True)
        self.header.viewport().installEventFilter(self)

        main_layout.addWidget(self.table)

        # 底部按钮行
        bottom_btn_widget = QWidget()
        bottom_btn_layout = QHBoxLayout(bottom_btn_widget)
        bottom_btn_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_calculate_total = QPushButton("🧮 计算总和")
        self.btn_calculate_total.setFixedHeight(45)
        self.btn_calculate_total.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.btn_calculate_total.clicked.connect(self.calculate_total)
        bottom_btn_layout.addWidget(self.btn_calculate_total)
        
        bottom_btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(45)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        close_btn.clicked.connect(self.accept)
        bottom_btn_layout.addWidget(close_btn)
        
        main_layout.addWidget(bottom_btn_widget)

        self.image_area = QWidget()
        self.image_area.setMaximumHeight(0)
        self.image_area.setVisible(False)
        image_layout = QHBoxLayout(self.image_area)
        image_layout.setContentsMargins(0, 5, 0, 0)

        self.image_grid = QGridLayout()
        self.image_grid.setSpacing(5)
        image_layout.addLayout(self.image_grid)

        self.temp_images = []
        self.image_count = 6

        for i in range(self.image_count):
            cell = ImageCell(i)
            cell.setFixedSize(150, 150)
            cell.cell_hovered.connect(self.on_cell_hovered)
            cell.paste_requested.connect(self.on_paste_requested)
            cell.image_view_requested.connect(self.show_image_viewer)
            cell.clear_requested.connect(self.clear_temp_image)
            cell.setAcceptDrops(True)
            self.image_grid.addWidget(cell, 0, i)
            self.temp_images.append(cell)

        self.btn_toggle_image_area = QPushButton("📷")
        self.btn_toggle_image_area.setFixedHeight(35)
        self.btn_toggle_image_area.setFixedWidth(45)
        self.btn_toggle_image_area.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        self.btn_toggle_image_area.clicked.connect(self.toggle_image_area)

        main_layout.addWidget(self.btn_toggle_image_area)
        main_layout.addWidget(self.image_area)

        self.temp_image_index = -1
        self.installEventFilter(self)

        self.records = records

        for col in range(self.table.columnCount()):
            self.header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        QApplication.processEvents()
        total_width = self.table.horizontalHeader().length() + self.table.verticalHeader().width() + 50
        screen = QApplication.desktop().screenGeometry()
        window_width = min(max(total_width, 1200), screen.width() - 100)
        data_rows = (self.table.rowCount() + 1) // 2
        comparison_rows = self.table.rowCount() - data_rows
        window_height = min(max(200 + data_rows * 60 + comparison_rows * 12, 600), screen.height() - 100)
        self.resize(window_width, window_height)

    def toggle_image_area(self):
        if self.image_area.isVisible():
            self.image_area.setVisible(False)
            self.image_area.setMaximumHeight(0)
        else:
            self.image_area.setVisible(True)
            self.image_area.setMaximumHeight(220)

    def on_cell_hovered(self, index):
        self.temp_image_index = index

    def on_paste_requested(self, index):
        clipboard = QApplication.clipboard()
        mimeData = clipboard.mimeData()
        if mimeData.hasImage():
            pixmap = QPixmap.fromImage(clipboard.image())
            self.temp_images[index].set_image(pixmap)
            self.save_temp_image(index, pixmap)

    def save_temp_image(self, index, pixmap):
        try:
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.WriteOnly)
            pixmap.save(buffer, "PNG")
            image_data = bytes(byte_array)
            self.db.safe_execute(
                """INSERT OR REPLACE INTO store_temp_images (store_id, slot_index, image_data, created_time)
                VALUES (?, ?, ?, ?)""",
                (self.store_id, index, image_data, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        except Exception as e:
            print(f"保存临时图片失败: {e}")

    def load_temp_images(self):
        try:
            print(f"[DEBUG] load_temp_images called, store_id={self.store_id}, image_count={self.image_count}")
            rows = self.db.safe_fetchall(
                "SELECT slot_index, image_data FROM store_temp_images WHERE store_id=? ORDER BY slot_index",
                (self.store_id,)
            )
            print(f"[DEBUG] Found {len(rows)} images in DB")
            for slot_index, image_data in rows:
                print(f"[DEBUG] Loading image to slot {slot_index}")
                if slot_index < self.image_count:
                    byte_array = QByteArray(image_data)
                    pixmap = QPixmap()
                    pixmap.loadFromData(byte_array, "PNG")
                    self.temp_images[slot_index].set_image(pixmap)
        except Exception as e:
            print(f"加载临时图片失败: {e}")

    def clear_temp_image(self, index):
        self.temp_images[index].clear_image()
        try:
            self.db.safe_execute(
                "DELETE FROM store_temp_images WHERE store_id=? AND slot_index=?",
                (self.store_id, index)
            )
        except Exception as e:
            print(f"删除临时图片失败: {e}")

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def show_image_viewer(self, index):
        cell = self.temp_images[index]
        if not cell or not cell.has_image():
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"图片 {index + 1}")
        dialog.resize(900, 700)
        dialog.setStyleSheet("background-color: #1a1a1a;")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(5, 5, 5, 5)

        self.viewer_index = index
        self.viewer_cells = [c for c in self.temp_images if c.has_image()]

        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setScaledContents(False)
        label.mouseDoubleClickEvent = lambda e: dialog.close()

        pixmap = self.viewer_cells[self.viewer_index].current_pixmap
        scaled = pixmap.scaled(880, 660, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)
        layout.addWidget(label)

        nav_layout = QHBoxLayout()
        btn_prev = QPushButton("◀ 上一张")
        btn_prev.setStyleSheet("background-color: #444; color: white; padding: 8px 20px; border-radius: 4px;")
        btn_prev.clicked.connect(lambda: self.navigate_image(-1, label))
        btn_next = QPushButton("下一张 ▶")
        btn_next.setStyleSheet("background-color: #444; color: white; padding: 8px 20px; border-radius: 4px;")
        btn_next.clicked.connect(lambda: self.navigate_image(1, label))
        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("background-color: #e74c3c; color: white; padding: 8px 20px; border-radius: 4px;")
        btn_close.clicked.connect(dialog.close)

        nav_layout.addWidget(btn_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(QLabel(f"{self.viewer_index + 1} / {len(self.viewer_cells)}"))
        nav_layout.addStretch()
        nav_layout.addWidget(btn_next)
        layout.addLayout(nav_layout)

        dialog.exec_()

    def navigate_image(self, direction, label_widget):
        if not self.viewer_cells:
            return
        self.viewer_index = (self.viewer_index + direction) % len(self.viewer_cells)
        pixmap = self.viewer_cells[self.viewer_index].current_pixmap
        scaled = pixmap.scaled(880, 660, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label_widget.setPixmap(scaled)
        dialog = label_widget.parentWidget()
        nav_layout = dialog.layout().itemAt(1).layout()
        page_label = nav_layout.itemAt(2).widget()
        if page_label:
            page_label.setText(f"{self.viewer_index + 1} / {len(self.viewer_cells)}")

    def showEvent(self, event):
        super().showEvent(event)
        self.reload_data()
        self.load_temp_images()

    def reload_data(self):
        records = self.load_all_data()
        self.table.setRowCount(0)
        self.table.clearContents()

        if not records:
            self.records = []
            return

        total_rows = 2 * len(records) - 1
        self.table.setRowCount(total_rows)

        GREEN = QColor("#27ae60")
        RED = QColor("#e74c3c")
        GRAY = QColor("#999999")

        current_table_row = 0
        for i, record in enumerate(records):
            table_row = current_table_row
            start_date = record[0] if record[0] else ""
            end_date = record[1] if record[1] else ""
            start_display = start_date[5:10] if start_date and len(start_date) >= 10 else start_date
            end_display = end_date[5:10] if end_date and len(end_date) >= 10 else end_date
            date_str = f"{start_display}\n{end_display}"

            days = 1
            if start_date and end_date:
                try:
                    from datetime import datetime
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    days = max(1, (end_dt - start_dt).days + 1)
                except:
                    pass

            net_profit = record[17] if record[17] else 0
            daily_profit = net_profit / days if days > 0 else 0

            values = [
                date_str,
                str(int(record[2])) if record[2] else "0",
                f"¥{record[3]:.2f}" if record[3] else "¥0.00",
                f"¥{record[4]:.2f}" if record[4] else "¥0.00",
                f"{record[11]:.2f}%" if record[11] else "0.00%",
                f"¥{record[5]:.2f}" if record[5] else "¥0.00",
                f"{record[12]:.2f}%" if record[12] else "0.00%",
                str(int(record[6])) if record[6] else "0",
                f"{record[13]:.2f}%" if record[13] else "0.00%",
                f"¥{record[14]:.2f}" if record[14] else "¥0.00",
                f"¥{record[7]:.2f}" if record[7] else "¥0.00",
                f"{record[15]:.2f}%" if record[15] else "0.00%",
                f"¥{record[16]:.2f}" if record[16] else "¥0.00",
                f"¥{record[8]:.2f}" if record[8] else "¥0.00",
                f"¥{record[9]:.2f}" if record[9] else "¥0.00",
                f"¥{record[10]:.2f}" if record[10] else "¥0.00",
                f"¥{record[17]:.2f}" if record[17] else "¥0.00",
                f"{record[18]:.2f}%" if record[18] else "0.00%",
                f"¥{record[19]:.2f}" if record[19] else "¥0.00",
                f"¥{daily_profit:.2f}",
            ]

            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if j == 0:
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                if j == 0:
                    pass
                elif j in [1, 2, 3, 5, 7, 10, 13, 14, 15]:
                    item.setBackground(QColor("#c8e6c9"))
                    item.setForeground(QColor("#1b5e20"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    item.setBackground(QColor("#bbdefb"))
                    item.setForeground(QColor("#0d47a1"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(table_row, j, item)

            delete_btn = QPushButton("🗑️")
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            delete_btn.clicked.connect(lambda checked, r=table_row, idx=i: self.delete_data_row_with_comparison(r, idx))
            self.table.setCellWidget(table_row, 20, delete_btn)
            self.table.setRowHeight(table_row, 60)

            if i > 0:
                self._add_week_comparison_row(table_row + 1, record, records[i - 1], GREEN, RED, GRAY)
                current_table_row += 2
            else:
                current_table_row += 1

        self.records = records

    def show_context_menu(self, pos):
        menu = QMenu()
        hint_action = QAction("ℹ️ 对比行不可操作", self.table)
        hint_action.setEnabled(False)
        menu.addAction(hint_action)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def delete_data_row_with_comparison(self, row, record_index):
        date_item = self.table.item(row, 0)
        date_text = date_item.text().split('\n')[0] if date_item else ""

        reply = QMessageBox.question(self, "确认删除", f"确定要删除 {date_text} 这行数据及其对比行吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        if record_index < len(self.records):
            record = self.records[record_index]
            self.db.safe_execute("""
                DELETE FROM manual_margin_data WHERE store_id=? AND start_date=? AND end_date=?
            """, (self.store_id, record[0], record[1]))

        if self.parent_dialog and hasattr(self.parent_dialog, 'update_current_history_label'):
            self.parent_dialog.update_current_history_label()
        if self.parent_dialog and hasattr(self.parent_dialog, 'refresh_manual_data_display'):
            self.parent_dialog.refresh_manual_data_display()

        self.reload_data()
        QApplication.processEvents()

        self.show_toast("✅ 已删除")

    def show_toast(self, message):
        """显示气泡提示（淡入淡出0.5秒）"""
        if not hasattr(self, 'toast_label'):
            self.toast_label = QLabel(self)
            self.toast_label.setStyleSheet("""
                background-color: rgba(0, 0, 0, 180);
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px;
            """)
            self.toast_label.setAttribute(Qt.WA_TranslucentBackground)
            self.toast_label.setWindowFlags(Qt.FramelessWindowHint)
            self.toast_opacity = QGraphicsOpacityEffect()
            self.toast_label.setGraphicsEffect(self.toast_opacity)
            self.toast_opacity.setOpacity(0)

        self.toast_label.setText(message)
        self.toast_label.adjustSize()
        parent_pos = self.mapToGlobal(self.rect().bottomLeft())
        x = parent_pos.x() + (self.width() - self.toast_label.width()) // 2
        y = parent_pos.y() - self.toast_label.height() - 10
        self.toast_label.move(x, y)
        self.toast_label.show()
        self.toast_label.repaint()

        self.toast_opacity.setOpacity(1)
        QApplication.processEvents()

        QTimer.singleShot(500, self.fade_out_toast)

    def fade_out_toast(self):
        if hasattr(self, 'toast_opacity'):
            self.toast_opacity.setOpacity(0)
            QTimer.singleShot(500, self.toast_label.hide if hasattr(self, 'toast_label') else lambda: None)

    def calculate_total(self):
        """计算选中行或所有行的总和并弹出窗口显示"""
        records = self.load_all_data()
        if not records:
            QMessageBox.information(self, "提示", "无数据可计算")
            return

        def is_data_row(row):
            return row == 0 or row % 2 == 1

        selected_rows = self.table.selectionModel().selectedRows()

        if selected_rows:
            rows_to_calculate = [row.row() for row in selected_rows if is_data_row(row.row())]
        else:
            rows_to_calculate = [row for row in range(self.table.rowCount()) if is_data_row(row)]

        if not rows_to_calculate:
            QMessageBox.information(self, "提示", "没有可计算的数据行")
            return

        # 初始化总和
        total_orders = 0  # 实发订单
        total_amount = 0  # 实发金额
        total_gross_profit = 0  # 毛利润
        total_refund_amount = 0  # 退款金额
        total_refund_orders = 0  # 退款订单
        total_promotion_fee = 0  # 推广费
        total_deduction = 0  # 扣款
        total_other_service = 0  # 其他服务
        total_other = 0  # 其他
        total_days = 0  # 总天数

        for row in rows_to_calculate:
            if row >= self.table.rowCount():
                continue
            
            # 获取日期单元格并计算天数
            date_item = self.table.item(row, 0)
            if date_item:
                date_text = date_item.text()
                if '\n' in date_text:
                    parts = date_text.split('\n')
                    if len(parts) >= 2:
                        start_date_str = parts[0].strip()
                        end_date_str = parts[1].strip()
                        try:
                            from datetime import datetime
                            # 假设年份为当前年份
                            current_year = datetime.now().year
                            start_dt = datetime.strptime(f"{current_year}-{start_date_str}", "%Y-%m-%d")
                            end_dt = datetime.strptime(f"{current_year}-{end_date_str}", "%Y-%m-%d")
                            days = max(1, (end_dt - start_dt).days + 1)
                            total_days += days
                        except:
                            total_days += 1
                    else:
                        total_days += 1
                else:
                    total_days += 1
            else:
                total_days += 1
            
            # 获取单元格数据
            orders_item = self.table.item(row, 1)
            amount_item = self.table.item(row, 2)
            gross_profit_item = self.table.item(row, 3)
            refund_amount_item = self.table.item(row, 5)
            refund_orders_item = self.table.item(row, 7)
            promotion_fee_item = self.table.item(row, 10)
            deduction_item = self.table.item(row, 13)
            other_service_item = self.table.item(row, 14)
            other_item = self.table.item(row, 15)

            # 累加
            if orders_item:
                try:
                    total_orders += int(orders_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if amount_item:
                try:
                    total_amount += float(amount_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if gross_profit_item:
                try:
                    total_gross_profit += float(gross_profit_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if refund_amount_item:
                try:
                    total_refund_amount += float(refund_amount_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if refund_orders_item:
                try:
                    total_refund_orders += int(refund_orders_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if promotion_fee_item:
                try:
                    total_promotion_fee += float(promotion_fee_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if deduction_item:
                try:
                    total_deduction += float(deduction_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if other_service_item:
                try:
                    total_other_service += float(other_service_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass
            if other_item:
                try:
                    total_other += float(other_item.text().replace('¥', '').replace(',', ''))
                except:
                    pass

        # 计算派生值
        tech_fee = total_amount * 0.006  # 技术服务费
        net_profit = total_gross_profit - total_refund_amount - total_promotion_fee - total_deduction - total_other_service + total_other - tech_fee
        
        # 计算百分比
        gross_margin_rate = (total_gross_profit / total_amount * 100) if total_amount > 0 else 0
        refund_rate_by_amount = (total_refund_amount / total_amount * 100) if total_amount > 0 else 0
        refund_rate_by_orders = (total_refund_orders / total_orders * 100) if total_orders > 0 else 0
        unit_price = (total_amount / total_orders) if total_orders > 0 else 0
        promotion_ratio = (total_promotion_fee / total_amount * 100) if total_amount > 0 else 0
        net_margin_rate = (net_profit / total_amount * 100) if total_amount > 0 else 0
        profit_per_order = (net_profit / total_orders) if total_orders > 0 else 0
        daily_profit = (net_profit / total_days) if total_days > 0 else 0

        # 弹出总和窗口
        total_dialog = QDialog(self)
        total_dialog.setWindowTitle("📊 数据总和")
        total_dialog.setStyleSheet("background-color: #f5f5f5;")
        total_layout = QVBoxLayout(total_dialog)
        total_layout.setContentsMargins(10, 10, 10, 10)
        
        title_label = QLabel(f"📈 数据总和（共{len(rows_to_calculate)}行，总计{total_days}天）")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; padding: 10px;")
        total_layout.addWidget(title_label)
        
        # 创建表格显示总和
        total_table = QTableWidget()
        total_table.setColumnCount(20)
        total_table.setHorizontalHeaderLabels([
            "日期", "实发订单", "实发金额", "毛利润", "毛利率", "退款金额", "金额退款率",
            "退款订单", "订单退款率", "件单价", "推广费", "推广占比",
            "技术服务费", "扣款", "其他服务", "其他", "净利润",
            "净利率", "单笔利润", "日盈亏"
        ])
        
        total_table.setRowCount(1)
        
        # 填充数据
        values = [
            f"总计\n({len(rows_to_calculate)}行\n{total_days}天)",
            str(int(total_orders)),
            f"¥{total_amount:.2f}",
            f"¥{total_gross_profit:.2f}",
            f"{gross_margin_rate:.2f}%",
            f"¥{total_refund_amount:.2f}",
            f"{refund_rate_by_amount:.2f}%",
            str(int(total_refund_orders)),
            f"{refund_rate_by_orders:.2f}%",
            f"¥{unit_price:.2f}",
            f"¥{total_promotion_fee:.2f}",
            f"{promotion_ratio:.2f}%",
            f"¥{tech_fee:.2f}",
            f"¥{total_deduction:.2f}",
            f"¥{total_other_service:.2f}",
            f"¥{total_other:.2f}",
            f"¥{net_profit:.2f}",
            f"{net_margin_rate:.2f}%",
            f"¥{profit_per_order:.2f}",
            f"¥{daily_profit:.2f}"
        ]
        
        for j, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if j == 0:
                item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                item.setBackground(QColor("#e8e8e8"))
            elif j in [1, 2, 3, 5, 7, 10, 13, 14, 15]:
                item.setBackground(QColor("#c8e6c9"))
                item.setForeground(QColor("#1b5e20"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                item.setBackground(QColor("#bbdefb"))
                item.setForeground(QColor("#0d47a1"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            total_table.setItem(0, j, item)
        
        total_table.setRowHeight(0, 60)
        total_table.verticalHeader().setVisible(False)
        total_table.setShowGrid(True)
        total_table.setGridStyle(Qt.SolidLine)
        total_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        table_font = QFont()
        table_font.setPointSize(16)
        total_table.setFont(table_font)
        
        total_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #cccccc;
                font-size: 16px;
                border: 2px solid #cccccc;
                border-radius: 6px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 1px;
                text-align: center;
                border: 1px solid #cccccc;
                font-size: 16px;
            }
            QTableWidget::item:selected {
                background-color: #0078d7;
                color: white;
            }
            QHeaderView {
                border: none;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                padding: 1px;
                margin: 0px;
                border: none;
                border-left: 1px solid #cccccc;
                border-bottom: 1px solid #cccccc;
                border-right: 1px solid #cccccc;
                font-size: 16px;
                font-weight: bold;
                min-height: 50px;
            }
        """)
        
        header = total_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setMinimumSectionSize(80)
        header.setStretchLastSection(True)
        
        total_layout.addWidget(total_table)
        
        # 调整列宽以适应内容
        for col in range(total_table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        total_table.horizontalHeader().setStretchLastSection(True)
        QApplication.processEvents()
        
        # 设置窗口大小
        total_width = header.length() + total_table.verticalHeader().width() + 50
        screen = QApplication.desktop().screenGeometry()
        window_width = min(max(total_width, 1200), screen.width() - 100)
        window_height = min(300, screen.height() - 100)
        total_dialog.resize(window_width, window_height)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(45)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        close_btn.clicked.connect(total_dialog.accept)
        total_layout.addWidget(close_btn)
        
        total_dialog.exec_()

    def eventFilter(self, obj, event):
        if obj == self.header.viewport() and event.type() == QEvent.MouseMove:
            col = self.header.logicalIndexAt(event.pos())
            if 0 <= col < len(self.FORMULAS):
                col_names = list(self.FORMULAS.keys())
                formula = self.FORMULAS[col_names[col]]
                if formula:
                    self.header.setToolTip(formula)
                else:
                    self.header.setToolTip("")
            return super().eventFilter(obj, event)
        return super().eventFilter(obj, event)


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
        self.is_reading_mode = False
        self.large_dialog = None

        self.setWindowTitle(f"🏪 店铺毛利管理 - {store_name}")
        self.resize(1700, 800)

        self.toast_label = QLabel(self)
        self.toast_label.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.toast_label.setAttribute(Qt.WA_TranslucentBackground)
        self.toast_label.setStyleSheet("""
            background-color: rgba(128, 128, 128, 0.5);
            color: black;
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 14px;
        """)
        self.toast_label.setAlignment(Qt.AlignCenter)
        self.toast_label.hide()
        self.toast_label.setGraphicsEffect(QGraphicsOpacityEffect(opacity=0.5))
        self.toast_opacity_effect = QGraphicsOpacityEffect(opacity=0.5)
        self.toast_label.setGraphicsEffect(self.toast_opacity_effect)

        self.toast_fade_out_animation = QPropertyAnimation(self.toast_opacity_effect, b"opacity")
        self.toast_fade_out_animation.setDuration(500)
        self.toast_fade_out_animation.setStartValue(0.5)
        self.toast_fade_out_animation.setEndValue(0.0)
        self.toast_fade_out_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.toast_fade_out_animation.finished.connect(self.toast_label.hide)

        self.init_ui()
        self.load_products()
        self.refresh_manual_data_display()

    def toggle_reading_mode(self):
        """切换阅览模式 - 弹出放大版数据表格窗口"""
        self.is_reading_mode = not self.is_reading_mode
        if self.is_reading_mode:
            self.btn_reading_mode.setText("📖 退出阅览")
            self.btn_reading_mode.setStyleSheet("font-size: 11px; padding: 3px 5px; background-color: #e74c3c; color: white; border-radius: 3px;")
            self.show_toast("已打开放大版数据窗口")
            if self.large_dialog is None:
                self.large_dialog = LargeMarginDataDialog(self.store_name, self.store_id, self.db, self)
                self.large_dialog.setAttribute(Qt.WA_QuitOnClose, False)
                self.large_dialog.show()
            else:
                self.large_dialog.reload_data()
                self.large_dialog.show()
                self.large_dialog.activateWindow()
            self.is_reading_mode = False
            self.btn_reading_mode.setText("🔍 阅览模式")
            self.btn_reading_mode.setStyleSheet("font-size: 11px; padding: 3px 5px; background-color: #3498db; color: white; border-radius: 3px;")
        else:
            if self.large_dialog and self.large_dialog.isVisible():
                self.large_dialog.close()
            self.btn_reading_mode.setText("🔍 阅览模式")
            self.btn_reading_mode.setStyleSheet("font-size: 11px; padding: 3px 5px; background-color: #3498db; color: white; border-radius: 3px;")
            self.show_toast("已退出阅览模式")
            self.is_reading_mode = False

    def show_toast(self, message):
        """显示气泡提示（淡入淡出0.5秒，不透明度50%）"""
        self.toast_fade_out_animation.stop()
        self.toast_opacity_effect.setOpacity(0.5)
        self.toast_label.setText(message)
        self.toast_label.adjustSize()
        parent_pos = self.mapToGlobal(self.rect().bottomLeft())
        x = parent_pos.x() + (self.width() - self.toast_label.width()) // 2
        y = parent_pos.y() - 80
        self.toast_label.move(x, y)
        self.toast_label.show()
        QTimer.singleShot(500, self.fade_out_toast)

    def fade_out_toast(self):
        """淡出气泡提示"""
        self.toast_fade_out_animation.start()

    def get_sys_id_by_user_id(self, user_id):
        """根据用户ID获取系统ID"""
        for sys_id, uid in self.sys_id_to_user_id.items():
            if uid == user_id:
                return sys_id
        return None

    def get_main_spec(self, prod_id):
        """获取商品的主卖规格"""
        spec_counts = self.db.safe_fetchall(
            "SELECT spec_code, order_count FROM imported_orders WHERE product_id=?",
            (prod_id,)
        )
        if not spec_counts:
            return None, 0
        total_orders = sum(sc[1] for sc in spec_counts if sc[1])
        if total_orders == 0:
            return None, 0
        max_spec = max(spec_counts, key=lambda x: x[1] if x[1] else 0)
        return max_spec[0] if max_spec[0] else None, max_spec[1] if max_spec[1] else 0

    def get_user_id_by_sys_id(self, sys_id):
        """根据系统ID获取用户ID"""
        return self.sys_id_to_user_id.get(sys_id)

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

    def on_weight_changed(self, user_id, text):
        if user_id not in self.product_weights:
            return
        sender = self.sender()
        try:
            new_weight = float(text) if text else 0
        except ValueError:
            new_weight = 0
        new_weight = max(0, min(100, new_weight))
        total_locked = sum(
            data.get("weight", 0) for uid, data in self.product_weights.items()
            if uid != user_id and data.get("locked", 0)
        )
        max_allowed = 100 - total_locked
        if new_weight > max_allowed:
            new_weight = max_allowed
        self.product_weights[user_id]["weight"] = new_weight
        self.db.safe_execute("UPDATE stores SET weight_synced=0 WHERE id=?", (self.store_id,))
        self.main_app.refresh_store_weight_sync_flag(self.store_id)
        self.rebalance_unlocked_weights(user_id)
        self.update_weight_inputs()
        self.calculate_total_margin()

    def on_weight_editing_finished(self, user_id):
        if user_id not in self.product_weights:
            return
        sys_id = self.get_sys_id_by_user_id(user_id)
        if not sys_id:
            return
        new_weight = self.product_weights[user_id].get("weight", 0)
        self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (new_weight, sys_id))
        self.update_weight_inputs()

    def rebalance_unlocked_weights(self, changed_user_id):
        total_locked = sum(
            data.get("weight", 0) for data in self.product_weights.values() if data.get("locked", 0)
        )
        changed_weight = self.product_weights[changed_user_id]["weight"]
        remaining = max(0, 100 - total_locked - changed_weight)
        unlocked_prods = [
            uid for uid, data in self.product_weights.items()
            if uid != changed_user_id and not data.get("locked", 0)
        ]
        if not unlocked_prods:
            return
        avg_weight = remaining / len(unlocked_prods)
        for uid in unlocked_prods:
            self.product_weights[uid]["weight"] = avg_weight
            sys_id = self.get_sys_id_by_user_id(uid)
            if sys_id:
                self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (avg_weight, sys_id))

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
            sys_id = self.get_sys_id_by_user_id(prod_id)
            if not sys_id:
                continue
            weight = self.product_weights[prod_id]["weight"]
            is_locked = self.product_weights[prod_id]["locked"]
            self.db.safe_execute(
                "UPDATE products SET store_weight=?, store_weight_locked=? WHERE id=?",
                (weight, is_locked, sys_id),
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

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 调试标签
        debug_widget = QWidget()
        debug_layout = QHBoxLayout(debug_widget)
        debug_layout.setContentsMargins(5, 2, 5, 2)
        debug_label = QLabel(f"[DEBUG] 文件: dialogs/store_margin.py")
        debug_label.setStyleSheet("background-color: #ffeb3b; color: #000; font-size: 11px; padding: 2px 8px;")
        debug_label.setCursor(Qt.PointingHandCursor)
        debug_label.setToolTip("点击复制文件路径")
        debug_layout.addWidget(debug_label)
        debug_layout.addStretch()
        layout.addWidget(debug_widget)

        def copy_path():
            clipboard = QApplication.clipboard()
            clipboard.setText("e:/zhuomian/shop/manager/dialogs/store_margin.py")
        debug_label.mousePressEvent = lambda e: copy_path()

        # ====== 板块1: 过往数据分析板块 ======
        historical_widget = QWidget()
        historical_widget.setStyleSheet("border: 1px solid #dee2e6; border-radius: 8px;")
        historical_layout = QVBoxLayout(historical_widget)
        historical_layout.setContentsMargins(0, 0, 0, 0)

        # 板块标题栏（放在日期选择行上方）- 包含多个功能标签
        section_title_bar = QWidget()
        section_title_bar.setStyleSheet("padding: 5px 10px; border-radius: 4px;")
        section_title_layout = QHBoxLayout(section_title_bar)
        section_title_layout.setContentsMargins(5, 5, 5, 5)

        section_label_1 = QLabel("📈 过往数据分析")
        section_label_1.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; padding: 5px 10px; border-radius: 4px;")
        section_title_layout.addWidget(section_label_1)

        section_label_2 = QLabel("📅 数据周期选择")
        section_label_2.setStyleSheet("font-size: 12px; color: #666; padding: 5px 10px;")
        section_title_layout.addWidget(section_label_2)

        section_label_3 = QLabel("📝 手动录入数据")
        section_label_3.setStyleSheet("font-size: 12px; color: #666; padding: 5px 10px;")
        section_title_layout.addWidget(section_label_3)

        section_label_4 = QLabel("📊 周环比对比")
        section_label_4.setStyleSheet("font-size: 12px; color: #666; padding: 5px 10px;")
        section_title_layout.addWidget(section_label_4)

        section_title_layout.addStretch()
        historical_layout.addWidget(section_title_bar)

        # 日期选择行
        date_row = QWidget()
        date_layout = QHBoxLayout(date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)

        date_label = QLabel("数据周期:")
        date_label.setStyleSheet("font-size: 12px; color: #666; padding: 0 5px;")

        # 使用日期选择器
        from PyQt5.QtWidgets import QDateEdit
        from PyQt5.QtCore import QDate

        self.date_start_input = QDateEdit()
        self.date_start_input.setCalendarPopup(True)
        self.date_start_input.setDate(QDate.currentDate().addDays(-7))  # 默认一周前
        self.date_start_input.setDisplayFormat("yyyy-MM-dd")
        self.date_start_input.setFixedWidth(100)
        self.date_start_input.setStyleSheet("font-size: 11px; padding: 2px;")

        self.date_separator = QLabel("~")
        self.date_separator.setStyleSheet("font-size: 12px; color: #666; padding: 0 5px;")

        self.date_end_input = QDateEdit()
        self.date_end_input.setCalendarPopup(True)
        self.date_end_input.setDate(QDate.currentDate())  # 默认今天
        self.date_end_input.setDisplayFormat("yyyy-MM-dd")
        self.date_end_input.setFixedWidth(100)
        self.date_end_input.setStyleSheet("font-size: 11px; padding: 2px;")

        # 快捷按钮
        self.btn_last_week = QPushButton("📅 近七天")
        self.btn_last_week.setFixedWidth(80)
        self.btn_last_week.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton:pressed {
                background-color: #6c7a7d;
            }
        """)
        self.btn_last_week.clicked.connect(self.set_last_week)

        self.btn_input_data = QPushButton("📝 录入数据")
        self.btn_input_data.setFixedWidth(90)
        self.btn_input_data.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.btn_input_data.clicked.connect(self.open_input_data_dialog)

        self.btn_import_data = QPushButton("📂 导入数据")
        self.btn_import_data.setFixedWidth(90)
        self.btn_import_data.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:pressed {
                background-color: #7d3c98;
            }
        """)
        self.btn_import_data.clicked.connect(self.import_data)

        self.btn_reading_mode = QPushButton("🔍 阅览模式")
        self.btn_reading_mode.setFixedWidth(90)
        self.btn_reading_mode.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2471a3;
            }
        """)
        self.btn_reading_mode.clicked.connect(self.toggle_reading_mode)

        self.lbl_current_history = QLabel("📍 当前: 暂无数据")
        self.lbl_current_history.setStyleSheet("""
            QLabel {
                color: #3498db;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
                background-color: #e8f4fc;
                border-radius: 4px;
            }
        """)

        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_start_input)
        date_layout.addWidget(self.date_separator)
        date_layout.addWidget(self.date_end_input)
        date_layout.addWidget(self.btn_last_week)
        date_layout.addWidget(self.btn_input_data)
        date_layout.addWidget(self.btn_import_data)
        date_layout.addWidget(self.btn_reading_mode)
        date_layout.addWidget(self.lbl_current_history)
        date_layout.addStretch()

        historical_layout.addWidget(date_row)

        # 子板块C: 手动录入数据表格
        self.margin_data_table = QTableWidget()
        self.margin_data_table.setColumnCount(20)  # 日期 + 19个指标
        # 设置表头
        self.margin_data_table.setHorizontalHeaderLabels([
            "日期", "实发订单", "实发金额", "毛利润", "毛利率", "退款金额", "金额退款率",
            "退款订单", "订单退款率", "件单价", "推广费", "推广占比",
            "技术服务费", "扣款", "其他服务", "其他", "净利润",
            "净利率", "单笔利润", "日盈亏"
        ])
        self.margin_data_table.verticalHeader().setVisible(False)
        self.margin_data_table.setShowGrid(True)
        self.margin_data_table.setGridStyle(Qt.SolidLine)
        self.margin_data_table.setAlternatingRowColors(False)
        # Excel风格标准表格
        self.margin_data_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #cccccc;
                font-size: 14px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                margin: 0px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 0px;
                text-align: center;
                border: 1px solid #cccccc;
                font-size: 14px;
            }
            QTableWidget::item:selected {
                background-color: #e6f3ff;
                color: black;
                outline: none;
            }
            QHeaderView {
                border: none;
                margin: 0px;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                padding: 0px;
                margin: 0px;
                border: none;
                border-left: 1px solid #cccccc;
                border-bottom: 1px solid #cccccc;
                border-right: 1px solid #cccccc;
                font-size: 14px;
                font-weight: bold;
                min-height: 45px;
            }
            QHeaderView::section:first {
                border-left: 1px solid #cccccc;
                border-top-left-radius: 4px;
            }
            QHeaderView::section:last {
                border-right: 1px solid #cccccc;
                border-top-right-radius: 4px;
            }
        """)
        # 设置表格字体大小
        from PyQt5.QtGui import QFont
        table_font = QFont()
        table_font.setPointSize(14)
        self.margin_data_table.setFont(table_font)

        header = self.margin_data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(50)
        self.margin_data_table._initial_width = None
        self.margin_data_table.setMinimumHeight(60)
        self.margin_data_table.setMaximumHeight(100)
        self.margin_data_table.verticalHeader().setVisible(False)
        self.margin_data_table.setShowGrid(True)
        self.margin_data_table.setGridStyle(Qt.SolidLine)
        
        historical_layout.addWidget(self.margin_data_table)

        # 周环比对比表格
        self.week_table = QTableWidget()
        self.week_table.setColumnCount(20)
        self.week_table.setRowCount(1)
        self.week_table.verticalHeader().setVisible(False)
        self.week_table.horizontalHeader().setVisible(False)
        self.week_table.setShowGrid(True)
        self.week_table.setGridStyle(Qt.SolidLine)
        self.week_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #cccccc;
                font-size: 14px;
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 0px;
                text-align: center;
                border: 1px solid #cccccc;
                font-size: 14px;
            }
            QHeaderView::section {
                background-color: #d0d0d0;
                padding: 0px;
                border: 1px solid #cccccc;
                font-size: 14px;
                font-weight: bold;
                min-height: 30px;
            }
        """)
        week_header = self.week_table.horizontalHeader()
        week_header.setSectionResizeMode(QHeaderView.Stretch)
        self.week_table.setMaximumHeight(40)
        
        historical_layout.addWidget(self.week_table)

        # 板块标题：商品规格毛利权重
        section_title_2 = QLabel("📦 订单规格毛利权重")
        section_title_2.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; padding: 5px 10px; border-radius: 4px;")
        historical_layout.addWidget(section_title_2)

        # 毛利明细表格
        self.table = QTableWidget()
        self.table.setColumnCount(15)
        self.table.setHorizontalHeaderLabels(["图片", "商品 ID", "商品标题", "综合成本", "客单价", "毛利", "权重 (%)", "权重对比\n(较上周)", "单量", "单量对比\n(较上周)", "销售额", "主卖规格", "退款率", "退款占比\n最多规格", "操作"])
        self.table.setAlternatingRowColors(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellChanged.connect(self.on_cell_changed)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        
        # 设置列宽自适应填充
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(50)
        # 商品标题列固定200像素
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 200)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #cccccc;
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 0px;
                text-align: center;
                border: 1px solid #cccccc;
                background-color: white;
            }
            QTableWidget::item:selected {
                background-color: #e6f3ff;
                color: black;
                outline: none;
            }
            QTableWidget::item:hover {
                background-color: #d4edda;
            }
            QHeaderView {
                border: none;
                background-color: white;
            }
            QHeaderView::section {
                background-color: white;
                padding: 0px;
                margin: 0px;
                border: 1px solid #cccccc;
                font-weight: bold;
                min-height: 35px;
                text-align: center;
            }
        """)
        historical_layout.addWidget(self.table)
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        self.btn_auto_balance = QPushButton("⚖️ 自动均分权重")
        self.btn_auto_balance.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #2c3e50;
            }
            QPushButton:pressed {
                background-color: #1a252f;
            }
        """)
        self.btn_auto_balance.clicked.connect(self.auto_balance_weights)
        self.btn_profit_calc = QPushButton("🧮 计算利润")
        self.btn_profit_calc.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:pressed {
                background-color: #7d3c98;
            }
        """)
        self.btn_profit_calc.clicked.connect(self.open_profit_calculator)
        self.btn_import_orders = QPushButton("📥 导入订单")
        self.btn_import_orders.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:pressed {
                background-color: #1e8449;
            }
        """)
        self.btn_import_orders.clicked.connect(self.import_orders)
        
        # 历史记录按钮
        self.btn_history = QPushButton("📜 全部记录")
        self.btn_history.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #7d3c98;
            }
            QPushButton:pressed {
                background-color: #6c3483;
            }
        """)
        self.btn_history.clicked.connect(self.show_import_history)

        self.lbl_total_margin = QLabel("综合毛利: 0.00%")
        self.lbl_total_margin.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #e74c3c; background-color: #fdeaa8; padding: 6px 12px; border-radius: 6px;"
        )

        self.lbl_total_orders = QLabel("总单量: 0")
        self.lbl_total_orders.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #3498db; background-color: #e8f4fc; padding: 6px 12px; border-radius: 6px;"
        )

        self.lbl_order_range = QLabel("当前订单时间范围: --")
        self.lbl_order_range.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #8e44ad; background-color: #f5eef8; padding: 6px 12px; border-radius: 6px;"
        )

        self.btn_save = QPushButton("💾 保存")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
        """)
        self.btn_save.clicked.connect(self.save_weights)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_auto_balance)
        btn_layout.addWidget(self.btn_profit_calc)
        btn_layout.addWidget(self.btn_import_orders)
        btn_layout.addWidget(self.btn_history)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(self.lbl_total_margin)
        btn_layout.addWidget(self.lbl_total_orders)
        btn_layout.addWidget(self.lbl_order_range)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_close)
        historical_layout.addWidget(btn_widget)

        layout.addWidget(historical_widget)

    def resizeEvent(self, event):
        """窗口大小改变时同步两表列宽"""
        super().resizeEvent(event)
        self.sync_table_widths()

    def load_products(self):
        self.table.cellChanged.disconnect()
        products = self.db.safe_fetchall(
            "SELECT id, name, title, image_data, store_weight, store_weight_locked FROM products WHERE store_id=? ORDER BY sort_order",
            (self.store_id,),
        )
        self.sys_id_to_user_id = {}
        self.product_weights = {}
        self.refund_widgets = {}
        for prod in products:
            sys_id, prod_id, prod_title, image_data, store_weight, store_locked = prod
            self.sys_id_to_user_id[sys_id] = prod_id
            self.product_weights[prod_id] = {"sys_id": sys_id, "weight": store_weight or 0, "locked": 0}
        self.table.setRowCount(len(products))
        for row, prod in enumerate(products):
            sys_id, prod_id, prod_title, image_data, store_weight, store_locked = prod
            if prod_id in self.product_weights:
                self.product_weights[prod_id]["locked"] = store_locked or 0
            img_widget = QWidget()
            img_layout = QVBoxLayout(img_widget)
            img_layout.setContentsMargins(5, 5, 5, 5)
            img_label = QLabel()
            img_label.setFixedSize(60, 60)
            img_label.setScaledContents(False)
            img_label.setAlignment(Qt.AlignCenter)
            if image_data:
                pixmap = QPixmap()
                pixmap.loadFromData(image_data)
                if not pixmap.isNull():
                    img_label.setPixmap(pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    img_label.setText("❌")
                    img_label.setStyleSheet("color: #999; border: 1px solid #ddd;")
            else:
                img_label.setText("📷")
                img_label.setStyleSheet("color: #999; border: 1px solid #ddd;")
            img_layout.addWidget(img_label)
            self.table.setCellWidget(row, 0, img_widget)
            self.table.setRowHeight(row, 70)
            item_id = QTableWidgetItem(str(prod_id))
            item_id.setFlags(item_id.flags() & ~Qt.ItemIsEditable)
            item_id.setFont(QFont("Microsoft YaHei", 9))
            self.table.setItem(row, 1, item_id)
            item_title = QTableWidgetItem(prod_title or "")
            item_title.setFlags(item_title.flags() & ~Qt.ItemIsEditable)
            item_title.setFont(QFont("Microsoft YaHei", 9))
            self.table.setItem(row, 2, item_title)
            cost, price, margin = self.get_product_margin(sys_id)
            cost_item = QTableWidgetItem(f"¥{cost:.2f}" if cost else "¥0.00")
            cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
            cost_item.setTextAlignment(Qt.AlignCenter)
            cost_item.setFont(QFont("Microsoft YaHei", 19))
            self.table.setItem(row, 3, cost_item)
            item_price = QTableWidgetItem(f"¥{price:.2f}" if price else "¥0.00")
            item_price.setFlags(item_price.flags() & ~Qt.ItemIsEditable)
            item_price.setTextAlignment(Qt.AlignCenter)
            item_price.setFont(QFont("Microsoft YaHei", 19))
            self.table.setItem(row, 4, item_price)
            margin_text = f"{margin:.2f}%" if margin else "0.00%"
            item_margin = QTableWidgetItem(margin_text)
            item_margin.setFlags(item_margin.flags() & ~Qt.ItemIsEditable)
            item_margin.setTextAlignment(Qt.AlignCenter)
            item_margin.setFont(QFont("Microsoft YaHei", 19))
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
                "QLineEdit { background-color: white; border: 1px solid #4caf50; border-radius: 3px; padding: 2px; font-weight: bold; color: #2e7d32; }"
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
                "QLabel { background-color: white; border: 1px solid #ff9800; border-radius: 3px; font-size: 19px; }"
                if is_locked
                else "QLabel { background-color: white; border: 1px dashed #ccc; border-radius: 3px; font-size: 19px; }"
            )
            lock_label.installEventFilter(self)
            lock_label.setProperty("row", row)
            lock_label.setProperty("prod_id", prod_id)
            right_layout.addWidget(lock_label)
            weight_layout.addWidget(left_widget, 3)
            weight_layout.addWidget(right_widget, 1)
            self.table.setCellWidget(row, 6, weight_widget)
            
            # 新增：权重对比列（第 8 列）
            weight_compare_widget = QWidget()
            weight_compare_layout = QHBoxLayout(weight_compare_widget)
            weight_compare_layout.setContentsMargins(0, 0, 0, 0)
            weight_compare_label = QLabel("-")
            weight_compare_label.setAlignment(Qt.AlignCenter)
            weight_compare_label.setStyleSheet("color: black; font-size: 19px;")
            weight_compare_layout.addWidget(weight_compare_label)
            self.table.setCellWidget(row, 7, weight_compare_widget)
            
            order_label_widget = QWidget()
            order_label_layout = QHBoxLayout(order_label_widget)
            order_label_layout.setContentsMargins(0, 0, 0, 0)
            order_label = QLabel("")
            order_label.setAlignment(Qt.AlignCenter)
            order_label.setStyleSheet("color: black; font-size: 19px;")
            order_label_layout.addWidget(order_label)
            self.table.setCellWidget(row, 8, order_label_widget)
            
            # 新增：单量对比列（第 10 列）
            order_compare_widget = QWidget()
            order_compare_layout = QHBoxLayout(order_compare_widget)
            order_compare_layout.setContentsMargins(0, 0, 0, 0)
            order_compare_label = QLabel("-")
            order_compare_label.setAlignment(Qt.AlignCenter)
            order_compare_label.setStyleSheet("color: black; font-size: 19px;")
            order_compare_layout.addWidget(order_compare_label)
            self.table.setCellWidget(row, 9, order_compare_widget)
            
            main_spec_widget = QWidget()
            main_spec_layout = QHBoxLayout(main_spec_widget)
            main_spec_layout.setContentsMargins(0, 0, 0, 0)
            main_spec_label = QLabel("-")
            main_spec_label.setAlignment(Qt.AlignCenter)
            main_spec_label.setStyleSheet("color: black; font-size: 19px;")
            main_spec_layout.addWidget(main_spec_label)
            self.table.setCellWidget(row, 11, main_spec_widget)
            if prod_id in self.product_weights:
                self.product_weights[prod_id]["main_spec"] = main_spec_label
                main_spec_code, spec_orders = self.get_main_spec(prod_id)
                if spec_orders > 0 and main_spec_code:
                    main_spec_label.setText(str(main_spec_code))
                elif spec_orders == 0:
                    main_spec_label.setText("无")
            refund_orders_label = QLabel("无")
            refund_orders_label.setAlignment(Qt.AlignCenter)
            refund_orders_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            self.table.setCellWidget(row, 12, refund_orders_label)
            self.refund_widgets[row] = {'orders': refund_orders_label}
            refund_ratio_label = QLabel("无")
            refund_ratio_label.setAlignment(Qt.AlignCenter)
            refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            self.table.setCellWidget(row, 13, refund_ratio_label)
            self.refund_widgets[row]['ratio'] = refund_ratio_label
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(5, 2, 5, 2)
            btn_edit = QPushButton("查看商品")
            btn_edit.setFixedSize(60, 25)
            btn_edit.setStyleSheet("QPushButton { padding: 1px; }")
            btn_edit.clicked.connect(lambda checked, sid=sys_id, pid=prod_id, pt=prod_title: self.open_spec_dialog(sid, pid, pt))
            btn_layout.addWidget(btn_edit)
            self.table.setCellWidget(row, 14, btn_widget)
            self.table.setItem(row, 10, QTableWidgetItem("-"))
            self.table.item(row, 10).setFont(QFont("Microsoft YaHei", 14))
            self.table.item(row, 10).setTextAlignment(Qt.AlignCenter)
            self.table.item(row, 1).setData(Qt.UserRole, prod_id)
            order_label.setProperty("prod_id", prod_id)
            self._update_order_label_for_row(row, weight_input, order_label, prod_id)
        self.table.cellChanged.connect(self.on_cell_changed)
        self.calculate_total_margin()
        self.update_current_history_label()
        self.update_orders_display()
        self.update_compare_columns()
        self.update_product_avg_price()

    def update_product_avg_price(self):
        """更新所有商品的客单价和销售额列"""
        for row in range(self.table.rowCount()):
            prod_id_item = self.table.item(row, 1)
            if not prod_id_item:
                continue
            user_product_id = prod_id_item.data(Qt.UserRole)
            if not user_product_id:
                continue
            sys_id = self.get_sys_id_by_user_id(user_product_id)
            if not sys_id:
                self.table.item(row, 4).setText("-")
                self.table.item(row, 10).setText("-")
                continue
            spec_sales = self.db.safe_fetchall(
                "SELECT ps.sale_price, io.order_count FROM product_specs ps "
                "LEFT JOIN imported_orders io ON io.product_id = ? AND io.spec_code = ps.spec_code "
                "WHERE ps.product_id = ?",
                (user_product_id, sys_id)
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
                self.table.item(row, 10).setText(f"¥{total_amount:.2f}")
            else:
                self.table.item(row, 4).setText("-")
                self.table.item(row, 10).setText("-")

    def refresh_manual_data_display(self):
        """刷新手动录入数据展示（只显示最近一次数据）"""
        try:
            records = self.load_manual_data()
            
            # 只取最后一条记录（最近一次）
            if not records:
                self.margin_data_table.setRowCount(0)
                return
                
            record = records[-1]  # 取最后一条

            self.margin_data_table.setRowCount(1)
            
            # 显示日期范围：开始日期 和 结束日期 分两行显示
            start_date = record[0] if record[0] else ""
            end_date = record[1] if record[1] else ""
            start_display = start_date[5:10] if start_date and len(start_date) >= 10 else start_date
            end_display = end_date[5:10] if end_date and len(end_date) >= 10 else end_date
            date_str = f"{start_display}\n{end_display}"

            # 计算天数
            days = 1
            if start_date and end_date:
                try:
                    from datetime import datetime
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                    days = max(1, (end_dt - start_dt).days + 1)
                except:
                    pass
            
            # 计算日盈亏
            net_profit = record[17] if record[17] else 0
            daily_profit = net_profit / days if days > 0 else 0
            
            values = [
                date_str,  # 0: 日期
                str(int(record[2])),  # 1: 实发订单
                f"¥{record[3]:.2f}",  # 2: 实发金额
                f"¥{record[4]:.2f}",  # 3: 毛利润
                f"{record[11]:.2f}%",  # 4: 毛利率
                f"¥{record[5]:.2f}",  # 5: 退款金额
                f"{record[12]:.2f}%",  # 6: 金额退款率
                str(int(record[6])),  # 7: 退款订单
                f"{record[13]:.2f}%",  # 8: 订单退款率
                f"¥{record[14]:.2f}",  # 9: 件单价
                f"¥{record[7]:.2f}",  # 10: 推广费
                f"{record[15]:.2f}%",  # 11: 推广占比
                f"¥{record[16]:.2f}",  # 12: 技术服务费
                f"¥{record[8]:.2f}",  # 13: 扣款
                f"¥{record[9]:.2f}",  # 14: 其他服务
                f"¥{record[10]:.2f}",  # 15: 其他
                f"¥{record[17]:.2f}",  # 16: 净利润
                f"{record[18]:.2f}%",  # 17: 净利率
                f"¥{record[19]:.2f}",  # 18: 单笔利润
                f"¥{daily_profit:.2f}",  # 19: 日盈亏
            ]

            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                if j == 0:
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)

                if j == 0:
                    pass
                elif j in [1, 2, 3, 5, 7, 10, 13, 14, 15]:
                    item.setBackground(QColor("#c8e6c9"))
                    item.setForeground(QColor("#1b5e20"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    item.setBackground(QColor("#bbdefb"))
                    item.setForeground(QColor("#0d47a1"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                self.margin_data_table.setItem(0, j, item)

            self.margin_data_table.setRowHeight(0, 60)

            # 计算周环比变化
            self.calculate_week_comparison(records)
            
            # 同步两表列宽
            self.sync_table_widths()

        except Exception as e:
            print(f"刷新手动数据展示失败: {e}")
            import traceback
            traceback.print_exc()

    def sync_table_widths(self):
        """同步两个表格的列宽，确保完全对齐"""
        try:
            for col in range(20):
                width = self.margin_data_table.columnWidth(col)
                self.week_table.setColumnWidth(col, width)
        except Exception as e:
            print(f"同步列宽失败: {e}")

    def calculate_week_comparison(self, records):
        """计算并显示周环比变化"""
        if len(records) < 2:
            for col in range(20):
                item = QTableWidgetItem("暂无上周数据")
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setBackground(QColor("#f5f5f5"))
                self.week_table.setItem(0, col, item)
            return

        current = records[-1]
        previous = records[-2]

        current_net_profit = current[17] if current[17] else 0
        previous_net_profit = previous[17] if previous[17] else 0
        current_net_margin = current[18] if current[18] else 0
        previous_net_margin = previous[18] if previous[18] else 0

        current_daily = 0
        if current[0] and current[1]:
            try:
                from datetime import datetime
                start_dt = datetime.strptime(current[0], "%Y-%m-%d")
                end_dt = datetime.strptime(current[1], "%Y-%m-%d")
                days = max(1, (end_dt - start_dt).days + 1)
                current_daily = current_net_profit / days if days > 0 else 0
            except:
                pass

        previous_daily = 0
        if previous[0] and previous[1]:
            try:
                from datetime import datetime
                start_dt = datetime.strptime(previous[0], "%Y-%m-%d")
                end_dt = datetime.strptime(previous[1], "%Y-%m-%d")
                days = max(1, (end_dt - start_dt).days + 1)
                previous_daily = previous_net_profit / days if days > 0 else 0
            except:
                pass

        GREEN = QColor("#27ae60")
        RED = QColor("#e74c3c")
        GRAY = QColor("#999999")

        for col in range(20):
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)

            if col == 0:
                item.setText("较上周")
                item.setBackground(QColor("#e8e8e8"))
            elif col == 1:
                if previous[2] and previous[2] != 0:
                    change = ((current[2] or 0) - (previous[2] or 0)) / abs(previous[2]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 2:
                if (previous[3] or 0) != 0:
                    change = ((current[3] or 0) - (previous[3] or 0)) / abs(previous[3]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 3:
                if (previous[4] or 0) != 0:
                    change = ((current[4] or 0) - (previous[4] or 0)) / abs(previous[4]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 4:
                change = (current[11] or 0) - (previous[11] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
            elif col == 5:
                if (previous[5] or 0) != 0:
                    change = ((current[5] or 0) - (previous[5] or 0)) / abs(previous[5]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 6:
                change = (current[12] or 0) - (previous[12] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
            elif col == 7:
                if previous[6] and previous[6] != 0:
                    change = ((current[6] or 0) - (previous[6] or 0)) / abs(previous[6]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 8:
                change = (current[13] or 0) - (previous[13] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
            elif col == 9:
                if (previous[14] or 0) != 0:
                    change = ((current[14] or 0) - (previous[14] or 0)) / abs(previous[14]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 10:
                if (previous[7] or 0) != 0:
                    change = ((current[7] or 0) - (previous[7] or 0)) / abs(previous[7]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 11:
                change = (current[15] or 0) - (previous[15] or 0)
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
            elif col == 12:
                if (previous[16] or 0) != 0:
                    change = ((current[16] or 0) - (previous[16] or 0)) / abs(previous[16]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 13:
                if (previous[8] or 0) != 0:
                    change = ((current[8] or 0) - (previous[8] or 0)) / abs(previous[8]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 14:
                if (previous[9] or 0) != 0:
                    change = ((current[9] or 0) - (previous[9] or 0)) / abs(previous[9]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(RED if change > 0 else GREEN if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 15:
                if (previous[10] or 0) != 0:
                    change = ((current[10] or 0) - (previous[10] or 0)) / abs(previous[10]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 16:
                if previous_net_profit != 0:
                    change = (current_net_profit - previous_net_profit) / abs(previous_net_profit) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 17:
                change = current_net_margin - previous_net_margin
                icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                item.setText(f"{icon} {abs(change):.1f}%")
                item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
            elif col == 18:
                if (previous[19] or 0) != 0:
                    change = ((current[19] or 0) - (previous[19] or 0)) / abs(previous[19]) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)
            elif col == 19:
                if previous_daily != 0:
                    change = (current_daily - previous_daily) / abs(previous_daily) * 100
                    icon = "↑" if change > 0 else "↓" if change < 0 else "→"
                    item.setText(f"{icon} {abs(change):.1f}%")
                    item.setForeground(GREEN if change > 0 else RED if change < 0 else GRAY)
                else:
                    item.setText("→ 0.0%")
                    item.setForeground(GRAY)

            self.week_table.setItem(0, col, item)

    def load_manual_data(self):
        """从数据库加载手动录入数据"""
        try:
            records = self.db.safe_fetchall("""
                SELECT start_date, end_date, actual_orders, actual_amount, gross_profit,
                       refund_amount, refund_orders, promotion_fee, deduction, other_service, other,
                       gross_margin_rate, refund_rate_by_amount, refund_rate_by_orders,
                       unit_price, promotion_ratio, tech_fee, net_profit, net_margin_rate, profit_per_order
                FROM manual_margin_data WHERE store_id=? ORDER BY start_date ASC, end_date ASC
            """, (self.store_id,))
            return records
        except Exception as e:
            print(f"加载手动数据失败: {e}")
            return []

    def delete_manual_data(self, start_date):
        """删除手动录入数据"""
        reply = QMessageBox.question(self, "确认删除", "确定删除这条数据吗？")
        if reply == QMessageBox.Yes:
            try:
                self.db.safe_execute(
                    "DELETE FROM manual_margin_data WHERE store_id=? AND start_date=?",
                    (self.store_id, start_date)
                )
                # 先清空表格，等待UI更新后再刷新数据
                self.margin_data_table.setRowCount(0)
                QApplication.processEvents()
                self.refresh_manual_data_display()
                self.update_current_history_label()
                self.show_toast("✅ 已删除数据")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {e}")

    def open_input_data_dialog(self):
        """打开录入数据对话框"""
        from .input_data_dialog import InputDataDialog
        dialog = InputDataDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            # 添加日期信息
            start_date = self.date_start_input.date().toString("yyyy-MM-dd")
            end_date = self.date_end_input.date().toString("yyyy-MM-dd")
            data["start_date"] = start_date
            data["end_date"] = end_date
            self.save_manual_data(data)
            self.refresh_manual_data_display()
            self.update_current_history_label()

    def import_data(self):
        """导入Excel/CSV数据"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择导入文件", "",
            "Excel文件 (*.xlsx *.xls);;CSV文件 (*.csv);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            import os
            ext = os.path.splitext(file_path)[1].lower()

            if ext in ['.xlsx', '.xls']:
                import openpyxl
                from datetime import datetime as dt
                wb = openpyxl.load_workbook(file_path)
                ws = wb.active
                rows = []
                for row in ws.iter_rows(values_only=True):
                    row_data = []
                    for cell in row:
                        if isinstance(cell, (dt,)) and cell is not None:
                            row_data.append(cell.strftime("%Y-%m-%d"))
                        else:
                            row_data.append(cell)
                    rows.append(row_data)
            else:
                import csv
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

            if len(rows) < 2:
                QMessageBox.warning(self, "错误", "文件数据少于2行，无法导入")
                return

            header = [str(h).strip() if h else "" for h in rows[0]]

            # 自动识别列
            col_map = {}
            for i, h in enumerate(header):
                h_str = str(h).strip()
                h_lower = h_str.lower()
                if "日期" in h_str or "date" in h_lower:
                    col_map["start_date"] = i
                elif "实发订单" in h_str:
                    col_map["actual_orders"] = i
                elif "实发金额" in h_str:
                    col_map["actual_amount"] = i
                elif "毛利润" in h_str and "净" not in h_str:
                    col_map["gross_profit"] = i
                elif "退款金额" in h_str:
                    col_map["refund_amount"] = i
                elif "退款订单" in h_str:
                    col_map["refund_orders"] = i
                elif "推广费" in h_str:
                    col_map["promotion_fee"] = i
                elif "扣款" in h_str:
                    col_map["deduction"] = i
                elif "其他服务" in h_str:
                    col_map["other_service"] = i
                elif h_str.strip() == "其他" or (h_str.strip().startswith("其他") and "服务" not in h_str):
                    col_map["other"] = i

            # 总是弹出列映射对话框，自动识别到的帮用户选上
            dialog = QDialog(self)
            dialog.setWindowTitle("选择列映射")
            dialog.resize(500, 400)
            layout = QVBoxLayout(dialog)

            recognized_count = len(col_map)
            layout.addWidget(QLabel(f"已自动识别 {recognized_count} 个字段，其他字段请手动选择："))

            fields = [
                ("start_date", "日期（必填）"),
                ("actual_orders", "实发订单"),
                ("actual_amount", "实发金额"),
                ("gross_profit", "毛利润"),
                ("refund_amount", "退款金额"),
                ("refund_orders", "退款订单"),
                ("promotion_fee", "推广费"),
                ("deduction", "扣款"),
                ("other_service", "其他服务"),
                ("other", "其他"),
            ]

            combos = {}
            for field_key, field_name in fields:
                row_layout = QHBoxLayout()
                row_layout.addWidget(QLabel(field_name))
                combo = QComboBox()
                combo.addItem("（不导入）", -1)
                for idx, h in enumerate(header):
                    combo.addItem(f"{idx}: {h}", idx)
                # 自动设置已识别的列
                if field_key in col_map:
                    combo.setCurrentIndex(col_map[field_key] + 1)  # +1 因为第一个是"（不导入）"
                row_layout.addWidget(combo)
                layout.addLayout(row_layout)
                combos[field_key] = combo

            btn_layout = QHBoxLayout()
            ok_btn = QPushButton("确定")
            cancel_btn = QPushButton("取消")
            btn_layout.addWidget(ok_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)

            def on_ok():
                new_col_map = {}
                for field_key, combo in combos.items():
                    idx = combo.currentData()
                    if idx != -1:
                        new_col_map[field_key] = idx
                dialog.col_map = new_col_map
                dialog.accept()

            ok_btn.clicked.connect(on_ok)
            cancel_btn.clicked.connect(dialog.reject)

            if dialog.exec_() != QDialog.Accepted:
                return

            col_map = dialog.col_map

            if "start_date" not in col_map:
                QMessageBox.warning(self, "错误", "请至少选择日期列")
                return

            imported_count = 0
            overwritten_count = 0
            for row_idx in range(1, len(rows)):
                row = rows[row_idx]
                if not row or all(str(cell).strip() == "" for cell in row):
                    continue

                # 解析日期
                date_str = str(row[col_map["start_date"]]).strip()
                try:
                    from datetime import datetime
                    import re
                    start_date = None
                    end_date = None

                    dash_match = re.match(r'(\d{1,2})\.(\d{1,2})-(\d{1,2})\.(\d{1,2})', date_str)
                    if dash_match:
                        current_year = datetime.now().year
                        start_date = datetime(current_year, int(dash_match.group(1)), int(dash_match.group(2)))
                        end_date = datetime(current_year, int(dash_match.group(3)), int(dash_match.group(4)))
                    else:
                        date_str_clean = date_str.replace("/", "-").replace("~", "-")
                        parts = date_str_clean.split("-")
                        if len(parts) == 3:
                            if len(parts[0]) == 4:
                                start_date = end_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                            else:
                                current_year = datetime.now().year
                                start_date = end_date = datetime(current_year, int(parts[0]), int(parts[1]))
                        elif len(parts) == 2:
                            current_year = datetime.now().year
                            start_date = end_date = datetime(current_year, int(parts[0]), int(parts[1]))
                        elif len(parts) == 1 and parts[0]:
                            if "." in parts[0]:
                                sub_parts = parts[0].split(".")
                            elif "/" in parts[0]:
                                sub_parts = parts[0].split("/")
                            else:
                                sub_parts = None
                            if sub_parts and len(sub_parts) == 2:
                                current_year = datetime.now().year
                                start_date = end_date = datetime(current_year, int(sub_parts[0]), int(sub_parts[1]))

                    if start_date is None:
                        continue
                    start_date_str = start_date.strftime("%Y-%m-%d")
                    end_date_str = end_date.strftime("%Y-%m-%d")
                except:
                    continue

                # 解析数值
                def get_float(val, default=0.0):
                    try:
                        s = str(val).replace("¥", "").replace(",", "").replace("%", "").strip()
                        return float(s) if s else default
                    except:
                        return default

                def get_int(val, default=0):
                    try:
                        s = str(val).replace(",", "").strip()
                        return int(float(s)) if s else default
                    except:
                        return default

                data = {
                    "start_date": start_date_str,
                    "end_date": end_date_str,
                    "actual_orders": get_int(row[col_map.get("actual_orders", -1)]),
                    "actual_amount": get_float(row[col_map.get("actual_amount", -1)]),
                    "gross_profit": get_float(row[col_map.get("gross_profit", -1)]),
                    "refund_amount": get_float(row[col_map.get("refund_amount", -1)]),
                    "refund_orders": get_int(row[col_map.get("refund_orders", -1)]),
                    "promotion_fee": get_float(row[col_map.get("promotion_fee", -1)]),
                    "deduction": get_float(row[col_map.get("deduction", -1)]),
                    "other_service": get_float(row[col_map.get("other_service", -1)]),
                    "other": get_float(row[col_map.get("other", -1)]),
                }

                # 计算自动指标
                if data["actual_amount"] > 0:
                    data["gross_margin_rate"] = (data["gross_profit"] / data["actual_amount"]) * 100
                    data["refund_rate_by_amount"] = (data["refund_amount"] / data["actual_amount"]) * 100
                    data["promotion_ratio"] = (data["promotion_fee"] / data["actual_amount"]) * 100
                    data["unit_price"] = data["actual_amount"] / data["actual_orders"] if data["actual_orders"] > 0 else 0
                else:
                    data["gross_margin_rate"] = 0
                    data["refund_rate_by_amount"] = 0
                    data["promotion_ratio"] = 0
                    data["unit_price"] = 0

                if data["actual_orders"] > 0:
                    data["refund_rate_by_orders"] = (data["refund_orders"] / data["actual_orders"]) * 100
                else:
                    data["refund_rate_by_orders"] = 0

                data["tech_fee"] = data["actual_amount"] * 0.006

                data["net_profit"] = (
                    data["gross_profit"]
                    - data["refund_amount"]
                    - data["promotion_fee"]
                    - data["deduction"]
                    - data["other_service"]
                    + data["other"]
                    - data["tech_fee"]
                )

                if data["actual_amount"] > 0:
                    data["net_margin_rate"] = (data["net_profit"] / data["actual_amount"]) * 100
                else:
                    data["net_margin_rate"] = 0

                if data["actual_orders"] > 0:
                    data["profit_per_order"] = data["net_profit"] / data["actual_orders"]
                else:
                    data["profit_per_order"] = 0

                result = self.save_manual_data(data)
                if result == "new":
                    imported_count += 1
                elif result == "overwrite":
                    imported_count += 1
                    overwritten_count += 1

            self.refresh_manual_data_display()
            self.update_current_history_label()
            if overwritten_count > 0:
                self.show_toast(f"✅ 导入成功：新增 {imported_count - overwritten_count} 条，覆盖 {overwritten_count} 条")
            else:
                self.show_toast(f"✅ 已导入 {imported_count} 条数据")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"导入失败: {e}")

    def save_manual_data(self, data):
        """保存手动录入数据"""
        try:
            from datetime import datetime
            start_date = data.get("start_date", "")
            end_date = data.get("end_date", "")

            # 检查是否有相同日期的记录
            existing = self.db.safe_fetchall("""
                SELECT actual_orders, actual_amount, gross_profit, refund_amount,
                       refund_orders, promotion_fee, deduction, other_service, other
                FROM manual_margin_data
                WHERE store_id=? AND start_date=? AND end_date=?
            """, (self.store_id, start_date, end_date))

            if existing:
                old_record = existing[0]
                new_values = (
                    data.get("actual_orders", 0),
                    data.get("actual_amount", 0),
                    data.get("gross_profit", 0),
                    data.get("refund_amount", 0),
                    data.get("refund_orders", 0),
                    data.get("promotion_fee", 0),
                    data.get("deduction", 0),
                    data.get("other_service", 0),
                    data.get("other", 0),
                )
                if old_record == new_values:
                    return False  # 数据相同，跳过

                reply = QMessageBox.question(
                    self, "确认覆盖",
                    f"该日期范围 ({start_date} ~ {end_date}) 已存在数据，是否覆盖？"
                )
                if reply != QMessageBox.Yes:
                    return False
                is_overwrite = True
            else:
                is_overwrite = False

            created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 使用REPLACE自动覆盖已存在的记录
            self.db.safe_execute("""
                INSERT OR REPLACE INTO manual_margin_data (
                    store_id, start_date, end_date,
                    actual_orders, actual_amount, gross_profit,
                    refund_amount, refund_orders, promotion_fee,
                    deduction, other_service, other,
                    gross_margin_rate, refund_rate_by_amount, refund_rate_by_orders,
                    unit_price, promotion_ratio, tech_fee,
                    net_profit, net_margin_rate, profit_per_order,
                    created_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.store_id,
                data.get("start_date", ""),
                data.get("end_date", ""),
                data.get("actual_orders", 0),
                data.get("actual_amount", 0),
                data.get("gross_profit", 0),
                data.get("refund_amount", 0),
                data.get("refund_orders", 0),
                data.get("promotion_fee", 0),
                data.get("deduction", 0),
                data.get("other_service", 0),
                data.get("other", 0),
                data.get("gross_margin_rate", 0),
                data.get("refund_rate_by_amount", 0),
                data.get("refund_rate_by_orders", 0),
                data.get("unit_price", 0),
                data.get("promotion_ratio", 0),
                data.get("tech_fee", 0),
                data.get("net_profit", 0),
                data.get("net_margin_rate", 0),
                data.get("profit_per_order", 0),
                created_time
            ))
            return "overwrite" if is_overwrite else "new"
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存失败: {e}")
            return False

    def save_historical_data(self):
        """保存当前导入订单数据到历史记录"""
        try:
            start_date = self.date_start_input.date().toString("yyyy-MM-dd")
            end_date = self.date_end_input.date().toString("yyyy-MM-dd")
            
            if start_date > end_date:
                QMessageBox.warning(self, "提示", "开始日期不能晚于结束日期")
                return
            
            # 计算天数差
            from datetime import datetime
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days_diff = (end_dt - start_dt).days + 1
            
            if days_diff <= 0:
                QMessageBox.warning(self, "提示", "日期范围无效")
                return
            
            # 获取店铺的所有导入订单数据
            orders = self.db.safe_fetchall(
                "SELECT actual_amount, order_count FROM imported_orders WHERE store_id=?",
                (self.store_id,)
            )
            
            if not orders:
                QMessageBox.information(self, "提示", "当前没有导入的订单数据")
                return
            
            # 计算总数据
            total_amount = 0.0
            total_orders = 0
            
            for actual_amount, order_count in orders:
                if actual_amount:
                    total_amount += actual_amount
                if order_count:
                    total_orders += order_count
            
            # 计算客单价和日均数据
            avg_price = total_amount / total_orders if total_orders > 0 else 0
            daily_amount = total_amount / days_diff
            daily_orders = total_orders / days_diff
            
            # 保存到数据库
            created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self.db.safe_execute(
                "INSERT OR REPLACE INTO historical_data (store_id, start_date, end_date, total_amount, total_orders, avg_price, daily_amount, daily_orders, created_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.store_id, start_date, end_date, total_amount, total_orders, avg_price, daily_amount, daily_orders, created_time)
            )
            
            # 更新显示
            self.lbl_daily_amount.setText(f"日销售金额: ¥{daily_amount:.2f}")
            self.lbl_daily_orders.setText(f"日单量: {daily_orders:.1f}单")
            
            # 显示保存成功信息
            self.show_toast(f"✅ 已保存 {start_date} ~ {end_date} 的数据")
            
        except Exception as e:
            print(f"保存历史数据失败: {e}")
            QMessageBox.warning(self, "错误", f"保存历史数据失败: {e}")

    def view_historical_data(self):
        """查看历史数据"""
        try:
            # 创建历史数据查看对话框
            dialog = QDialog(self)
            dialog.setWindowTitle(f"📊 {self.store_name} - 历史数据")
            dialog.resize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            # 标题
            title_label = QLabel("📈 历史数据分析记录")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
            layout.addWidget(title_label)
            
            # 获取历史数据
            historical_data = self.db.safe_fetchall(
                "SELECT id, start_date, end_date, total_amount, total_orders, avg_price, daily_amount, daily_orders, created_time FROM historical_data WHERE store_id=? ORDER BY start_date DESC, end_date DESC",
                (self.store_id,)
            )
            
            if not historical_data:
                no_data_label = QLabel("暂无历史数据记录")
                no_data_label.setStyleSheet("font-size: 14px; color: #999; text-align: center; padding: 20px;")
                layout.addWidget(no_data_label)
            else:
                # 创建滚动区域
                scroll_area = QScrollArea()
                scroll_widget = QWidget()
                scroll_layout = QVBoxLayout(scroll_widget)
                scroll_layout.setSpacing(5)
                
                for data in historical_data:
                    data_id, start_date, end_date, total_amount, total_orders, avg_price, daily_amount, daily_orders, created_time = data
                    
                    # 创建数据卡片
                    card_widget = QWidget()
                    card_widget.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 8px;")
                    card_layout = QVBoxLayout(card_widget)
                    card_layout.setContentsMargins(8, 8, 8, 8)
                    
                    # 日期行
                    date_row = QWidget()
                    date_layout = QHBoxLayout(date_row)
                    date_layout.setContentsMargins(0, 0, 0, 0)
                    
                    date_label = QLabel(f"📅 {start_date} ~ {end_date}")
                    date_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #2c3e50;")
                    
                    delete_btn = QPushButton("🗑️")
                    delete_btn.setFixedSize(20, 20)
                    delete_btn.setStyleSheet("font-size: 10px; padding: 0px; background-color: #dc3545; color: white; border-radius: 2px;")
                    delete_btn.clicked.connect(lambda checked, d_id=data_id: self.delete_historical_data(d_id, dialog))
                    
                    date_layout.addWidget(date_label)
                    date_layout.addStretch()
                    date_layout.addWidget(delete_btn)
                    
                    # 数据行
                    data_row = QWidget()
                    data_layout = QHBoxLayout(data_row)
                    data_layout.setContentsMargins(0, 5, 0, 0)
                    
                    amount_label = QLabel(f"总额: ¥{total_amount:.2f}")
                    amount_label.setStyleSheet("font-size: 11px; color: #e74c3c;")
                    
                    orders_label = QLabel(f"订单: {total_orders}单")
                    orders_label.setStyleSheet("font-size: 11px; color: #3498db;")
                    
                    avg_label = QLabel(f"客单价: ¥{avg_price:.2f}")
                    avg_label.setStyleSheet("font-size: 11px; color: #27ae60;")
                    
                    daily_amount_label = QLabel(f"日销: ¥{daily_amount:.2f}")
                    daily_amount_label.setStyleSheet("font-size: 11px; color: #9b59b6;")
                    
                    daily_orders_label = QLabel(f"日单: {daily_orders:.1f}")
                    daily_orders_label.setStyleSheet("font-size: 11px; color: #f39c12;")
                    
                    data_layout.addWidget(amount_label)
                    data_layout.addWidget(orders_label)
                    data_layout.addWidget(avg_label)
                    data_layout.addWidget(daily_amount_label)
                    data_layout.addWidget(daily_orders_label)
                    
                    card_layout.addWidget(date_row)
                    card_layout.addWidget(data_row)
                    
                    scroll_layout.addWidget(card_widget)
                
                scroll_layout.addStretch()
                scroll_area.setWidget(scroll_widget)
                scroll_area.setWidgetResizable(True)
                layout.addWidget(scroll_area)
            
            # 关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            
            dialog.exec_()
            
        except Exception as e:
            print(f"查看历史数据失败: {e}")
            QMessageBox.warning(self, "错误", f"查看历史数据失败: {e}")

    def set_last_week(self):
        """设置近七天的日期范围（昨天到过去七天）"""
        from PyQt5.QtCore import QDate
        
        # 结束日期设置为昨天
        yesterday = QDate.currentDate().addDays(-1)
        # 开始日期设置为七天前
        seven_days_ago = yesterday.addDays(-6)
        
        self.date_start_input.setDate(seven_days_ago)
        self.date_end_input.setDate(yesterday)
        
        self.show_toast(f"已设置日期范围: {seven_days_ago.toString('yyyy-MM-dd')} ~ {yesterday.toString('yyyy-MM-dd')}")

    def delete_historical_data(self, data_id, parent_dialog):
        """删除历史数据"""
        reply = QMessageBox.question(self, "确认删除", "确定删除这条历史数据记录吗？")
        if reply == QMessageBox.Yes:
            try:
                self.db.safe_execute("DELETE FROM historical_data WHERE id=?", (data_id,))
                # 刷新对话框
                parent_dialog.accept()
                self.view_historical_data()
                self.show_toast("✅ 已删除历史数据")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {e}")

    def _update_order_label_for_row(self, row, weight_input, order_label, prod_id):
        """更新单量显示标签"""
        spec_counts = self.db.safe_fetchall(
            "SELECT spec_code, order_count, refund_count FROM imported_orders WHERE product_id=?",
            (prod_id,)
        )
        total_prod_orders = sum(sc[1] for sc in spec_counts) if spec_counts else 0
        if total_prod_orders > 0:
            order_label.setText(f"{total_prod_orders}单")
            weight_input.setToolTip(f"订单数: {total_prod_orders}单")
        else:
            order_label.setText("0单")
            weight_input.setToolTip("")
        refund_orders_label = self.table.cellWidget(row, 12)
        refund_ratio_label = self.table.cellWidget(row, 13)
        if spec_counts:
            total_orders = sum(sc[1] or 0 for sc in spec_counts)
            total_refund = sum(sc[2] or 0 for sc in spec_counts)
            if total_orders > 0 and total_refund > 0:
                refund_rate = total_refund / total_orders * 100
                if refund_orders_label and hasattr(refund_orders_label, 'setText'):
                    refund_orders_label.setText(f"{refund_rate:.2f}%")
                    refund_orders_label.setStyleSheet("color: #e74c3c; font-size: 19px; font-weight: bold;")
                max_refund_spec = None
                max_refund_rate = -1
                for spec_code, oc, rc in spec_counts:
                    oc = oc or 0
                    rc = rc or 0
                    if oc > 0 and rc > 0:
                        sr = rc / oc
                        if sr > max_refund_rate:
                            max_refund_rate = sr
                            max_refund_spec = spec_code
                if refund_ratio_label and hasattr(refund_ratio_label, 'setText'):
                    if max_refund_spec:
                        refund_ratio_label.setText(str(max_refund_spec))
                        refund_ratio_label.setStyleSheet("color: #e74c3c; font-size: 19px; font-weight: bold;")
                    else:
                        refund_ratio_label.setText("无")
                        refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            elif total_orders > 0 and total_refund == 0:
                if refund_orders_label and hasattr(refund_orders_label, 'setText'):
                    refund_orders_label.setText("0.00%")
                    refund_orders_label.setStyleSheet("color: #27ae60; font-size: 19px;")
                if refund_ratio_label and hasattr(refund_ratio_label, 'setText'):
                    refund_ratio_label.setText("无")
                    refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            else:
                if refund_orders_label and hasattr(refund_orders_label, 'setText'):
                    refund_orders_label.setText("无")
                    refund_orders_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
                if refund_ratio_label and hasattr(refund_ratio_label, 'setText'):
                    refund_ratio_label.setText("无")
                    refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
        else:
            if refund_orders_label and hasattr(refund_orders_label, 'setText'):
                refund_orders_label.setText("无")
                refund_orders_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            if refund_ratio_label and hasattr(refund_ratio_label, 'setText'):
                refund_ratio_label.setText("无")
                refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")

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
            user_id = self.get_user_id_by_sys_id(product_id)
            order_res = self.db.safe_fetchall(
                "SELECT order_count FROM imported_orders WHERE product_id=? AND spec_code=?",
                (user_id, spec_code)
            )
            order_count = order_res[0][0] if order_res and order_res[0][0] else 0
            weight = order_count if order_count > 0 else (weight or 0)
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
        if total_weight > 100:
            self.lbl_total_margin.setToolTip(f"⚠️ 权重总和超过100% ({total_weight:.1f}%)，可能导致毛利计算不准")
        else:
            self.lbl_total_margin.setToolTip("")
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

    def toggle_lock(self, row, user_id):
        sys_id = self.get_sys_id_by_user_id(user_id)
        if not sys_id:
            return
        current = self.product_weights.get(user_id, {})
        is_locked = current.get("locked", 0)
        new_locked = 1 if not is_locked else 0
        self.db.safe_execute("UPDATE products SET store_weight_locked=? WHERE id=?", (new_locked, sys_id))
        if new_locked == 1:
            total_locked = sum(
                data.get("weight", 0) for uid, data in self.product_weights.items()
                if uid != user_id and data.get("locked", 0)
            )
            remaining = 100 - total_locked
            if current.get("weight", 0) > remaining:
                self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (remaining, sys_id))
        self.load_products()

    def calculate_weights_from_orders(self):
        order_data = self.db.safe_fetchall("""
            SELECT product_id, SUM(order_count) as total_orders
            FROM imported_orders WHERE store_id=? GROUP BY product_id
        """, (self.store_id,))
        if not order_data:
            return
        total_store_orders = sum(row[1] for row in order_data if row[1])
        if total_store_orders <= 0:
            return
        product_orders = {row[0]: row[1] for row in order_data}
        total_locked = sum(
            data.get("weight", 0) for data in self.product_weights.values() if data.get("locked", 0)
        )
        unlocked_orders = 0
        for prod_id, orders in product_orders.items():
            if not self.product_weights.get(prod_id, {}).get("locked", 0):
                unlocked_orders += orders
        if unlocked_orders <= 0:
            return
        for prod_id, orders in product_orders.items():
            if self.product_weights.get(prod_id, {}).get("locked", 0):
                continue
            weight = (orders / unlocked_orders) * (100 - total_locked)
            sys_id = self.get_sys_id_by_user_id(prod_id)
            if sys_id:
                self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (weight, sys_id))

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
        for user_id in unlocked_rows:
            sys_id = self.get_sys_id_by_user_id(user_id)
            if sys_id:
                self.db.safe_execute("UPDATE products SET store_weight=? WHERE id=?", (avg_weight, sys_id))
        self.load_products()

    def on_cell_double_clicked(self, row, col):
        if col == 1:
            prod_id = self.table.item(row, 1).data(Qt.UserRole)
            if prod_id:
                clipboard = QApplication.clipboard()
                clipboard.setText(str(prod_id))
                self.show_toast(f"✅ 商品ID {prod_id} 已复制到剪贴板")
                return
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

    def show_margin_data_context_menu(self, pos):
        """显示财务数据表格的右键菜单"""
        item = self.margin_data_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        
        # 获取该行的日期数据
        date_item = self.margin_data_table.item(row, 0)
        if not date_item:
            return
            
        date_text = date_item.text()
        # 日期格式可能是 "04-01\n04-07" 或 "04-01~04-07"
        if "\n" in date_text:
            parts = date_text.split("\n")
        elif "~" in date_text:
            parts = date_text.split("~")
        else:
            return

        if len(parts) >= 2 and parts[0].strip():
            start_date_short = parts[0].strip()
            current_year = datetime.now().year
            start_date_full = f"{current_year}-{start_date_short}"
        else:
            QMessageBox.warning(self, "错误", "该数据的开始日期为空，无法删除")
            return
            
        menu = QMenu(self)
        action_delete = QAction("🗑️ 删除此行数据", self)
        action_delete.triggered.connect(lambda: self.delete_manual_data(start_date_full))
        menu.addAction(action_delete)
        
        menu.exec_(self.margin_data_table.viewport().mapToGlobal(pos))

    def show_week_comparison(self):
        """显示周环比对比结果"""
        current_index = self.combo_current.currentIndex()
        previous_index = self.combo_previous.currentIndex()
        
        if current_index < 0 or previous_index < 0:
            self.comparison_result.setText("请选择当前周和对比周")
            return
            
        current_data = self.combo_current.itemData(current_index)
        previous_data = self.combo_previous.itemData(previous_index)
        
        if not current_data or not previous_data:
            self.comparison_result.setText("数据加载失败，请重试")
            return
            
        # 解析数据
        current_values = current_data
        previous_values = previous_data
        
        # 计算关键指标变化
        result_text = "📈 周环比对比结果:\n\n"
        
        # 实发订单变化
        current_orders = current_values[2]  # actual_orders
        previous_orders = previous_values[2]
        order_change = current_orders - previous_orders
        order_change_pct = (order_change / previous_orders * 100) if previous_orders > 0 else 0
        order_icon = "📈" if order_change > 0 else "📉" if order_change < 0 else "➡️"
        result_text += f"{order_icon} 实发订单: {current_orders}单 (上周: {previous_orders}单) "
        if order_change != 0:
            result_text += f"变化: {order_change:+d}单 ({order_change_pct:+.1f}%)\n"
        else:
            result_text += "持平\n"
        
        # 实发金额变化
        current_amount = current_values[3]  # actual_amount
        previous_amount = previous_values[3]
        amount_change = current_amount - previous_amount
        amount_change_pct = (amount_change / previous_amount * 100) if previous_amount > 0 else 0
        amount_icon = "📈" if amount_change > 0 else "📉" if amount_change < 0 else "➡️"
        result_text += f"{amount_icon} 实发金额: ¥{current_amount:.2f} (上周: ¥{previous_amount:.2f}) "
        if amount_change != 0:
            result_text += f"变化: ¥{amount_change:+.2f} ({amount_change_pct:+.1f}%)\n"
        else:
            result_text += "持平\n"
        
        # 净利润变化
        current_profit = current_values[17]  # net_profit
        previous_profit = previous_values[17]
        profit_change = current_profit - previous_profit
        profit_change_pct = (profit_change / previous_profit * 100) if previous_profit > 0 else 0
        profit_icon = "📈" if profit_change > 0 else "📉" if profit_change < 0 else "➡️"
        result_text += f"{profit_icon} 净利润: ¥{current_profit:.2f} (上周: ¥{previous_profit:.2f}) "
        if profit_change != 0:
            result_text += f"变化: ¥{profit_change:+.2f} ({profit_change_pct:+.1f}%)\n"
        else:
            result_text += "持平\n"
        
        # 净利率变化
        current_margin = current_values[18]  # net_margin_rate
        previous_margin = previous_values[18]
        margin_change = current_margin - previous_margin
        margin_icon = "📈" if margin_change > 0 else "📉" if margin_change < 0 else "➡️"
        result_text += f"{margin_icon} 净利率: {current_margin:.2f}% (上周: {previous_margin:.2f}%) "
        if margin_change != 0:
            result_text += f"变化: {margin_change:+.2f}%\n"
        else:
            result_text += "持平\n"
        
        # 单笔利润变化
        current_ppo = current_values[19]  # profit_per_order
        previous_ppo = previous_values[19]
        ppo_change = current_ppo - previous_ppo
        ppo_change_pct = (ppo_change / previous_ppo * 100) if previous_ppo > 0 else 0
        ppo_icon = "📈" if ppo_change > 0 else "📉" if ppo_change < 0 else "➡️"
        result_text += f"{ppo_icon} 单笔利润: ¥{current_ppo:.2f} (上周: ¥{previous_ppo:.2f}) "
        if ppo_change != 0:
            result_text += f"变化: ¥{ppo_change:+.2f} ({ppo_change_pct:+.1f}%)\n"
        else:
            result_text += "持平\n"
        
        self.comparison_result.setText(result_text)

    def open_spec_dialog_by_id(self, user_product_id):
        prod = self.db.safe_fetchall(
            "SELECT id, title FROM products WHERE name=? AND store_id=?",
            (user_product_id, self.store_id)
        )
        if prod:
            sys_id, prod_title = prod[0]
            self.open_spec_dialog(sys_id, user_product_id, prod_title)

    def open_spec_dialog(self, sys_id, prod_id, prod_title):
        """通过 main_app 打开规格对话框，避免 dialogs 依赖主模块中的 ProductSpecDialog"""
        self.main_app.open_product_spec_dialog(self.db, sys_id, prod_id, prod_title, self)

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
            
            # 直接弹出手动选择界面让用户确认
            col_mapping = self._show_column_mapping_dialog(headers, col_mapping)
            if col_mapping is None:
                return
            
            product_id_col = col_mapping["product_id"]
            spec_code_col = col_mapping["spec_code"]
            quantity_col = col_mapping["quantity"]
            date_col = col_mapping.get("order_date")
            status_col = col_mapping.get("order_status")
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
            matched_count = 0
            for row in sheet.iter_rows(min_row=2, values_only=True):
                total_row_count += 1
                if total_row_count > 10000:
                    break
                try:
                    product_id_value = str(row[product_id_col]).strip() if product_id_col < len(row) else ""
                    spec_code_value = str(row[spec_code_col]).strip() if spec_code_col < len(row) else ""
                    quantity_value = row[quantity_col] if quantity_col < len(row) and quantity_col is not None else None
                    date_value = None
                    if date_col is not None and date_col < len(row):
                        date_value = row[date_col]
                    status_value = None
                    if status_col is not None and status_col < len(row):
                        status_value = str(row[status_col]).strip() if row[status_col] else ""
                except:
                    continue
                if not product_id_value or product_id_value == "None":
                    continue
                if product_id_value not in product_codes_in_store:
                    continue
                excel_product_codes_found.add(product_id_value)
                prod_db_id = product_code_to_id.get(product_id_value)
                if prod_db_id is None:
                    continue
                quantity = 1
                if quantity_value is not None:
                    try:
                        quantity = max(1, int(quantity_value))
                    except (ValueError, TypeError):
                        quantity = 1
                order_date_str = None
                if date_value is not None:
                    if isinstance(date_value, datetime):
                        order_date_str = date_value.strftime("%m/%d")
                    else:
                        date_str = str(date_value).strip()
                        if ' ' in date_str:
                            date_str = date_str.split()[0]
                        import re
                        match = re.search(r'(\d{1,2})[/-](\d{1,2})', date_str)
                        if match:
                            month, day = match.groups()
                            order_date_str = f"{int(month)}/{int(day)}"
                        else:
                            order_date_str = date_str[:5]
                spec_codes = all_store_specs.get(prod_db_id, set())
                spec_code_str = str(spec_code_value).strip() if spec_code_value else ""
                if spec_code_str and spec_code_str != "None" and spec_code_str in spec_codes:
                    if status_col is not None and status_value:
                        is_valid_order = ("已发货" in status_value) or ("已收货" in status_value)
                        if not is_valid_order:
                            continue
                    matched_count += 1
                    key = (product_id_value, spec_code_str)
                    if key not in order_data:
                        order_data[key] = {"count": 0, "refund_count": 0, "dates": []}
                    order_data[key]["count"] += quantity
                    if order_date_str:
                        order_data[key]["dates"].append(order_date_str)
                    if status_value:
                        is_refund = "退款成功" in status_value
                        if is_refund:
                            order_data[key]["refund_count"] += quantity
            
            missing_product_codes = product_codes_in_store - excel_product_codes_found
            if missing_product_codes:
                msg = f"以下商品ID在表格中没有订单记录：\n{', '.join(missing_product_codes)}\n\n是否继续同步（未匹配的商品链接权重将设为0）？"
                reply = QMessageBox.question(self, "部分商品无订单", msg, QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    return
            import_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 保存历史快照
            total_products = len(set(prod_id for prod_id, spec_code in order_data.keys()))
            total_specs = len(order_data)
            total_orders = sum(data["count"] for data in order_data.values())
            total_amount = 0  # 不再导入实收金额
            
            # 保存快照数据到 import_history 表
            snapshot_data = json.dumps({
                "orders": {f"{prod_id}_{spec_code}": data for (prod_id, spec_code), data in order_data.items()}
            })
            
            self.db.safe_execute("""
                INSERT INTO import_history (store_id, import_time, file_name, total_products, total_specs, total_orders, total_amount, snapshot_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (self.store_id, import_time, os.path.basename(file_path), total_products, total_specs, total_orders, total_amount, snapshot_data))
            
            self.db.safe_execute("DELETE FROM imported_orders WHERE store_id=?", (self.store_id,))
            for (product_id_val, spec_code), data in order_data.items():
                earliest_date = min(data["dates"]) if data["dates"] else None
                latest_date = max(data["dates"]) if data["dates"] else None
                date_range = f"{earliest_date}~{latest_date}" if earliest_date and latest_date else None
                self.db.safe_execute(
                    "INSERT INTO imported_orders (store_id, product_id, spec_code, order_count, import_time, order_date, actual_amount, refund_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (self.store_id, product_id_val, spec_code, data["count"], import_time, date_range, 0, data.get("refund_count", 0))
                )
            self.load_products()
            self.calculate_weights_from_orders()
            self.update_compare_columns()
            self.update_orders_display()
            self.update_product_avg_price()
            self.calculate_total_margin()
            self.update_weight_inputs()
            self.update_total_orders_label()
            self.update_order_range_label()
            self.main_app.show_toast(f"✅ 已导入 {len(order_data)} 条订单数据")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入订单失败：\n{str(e)}")

    def _auto_detect_columns(self, headers):
        """自动检测列映射"""
        mapping = {"product_id": None, "spec_code": None, "quantity": None, "order_date": None, "order_status": None}
        product_id_keywords = ["商品id", "商品ID", "id", "产品id", "产品ID", "product_id"]
        spec_code_keywords = ["规格编码", "规格code", "spec_code", "规格code", "sku", "SKU"]
        quantity_keywords = ["数量", "订单数量", "quantity", "count", "num", "销售数量"]
        order_date_keywords = ["日期", "date", "时间", "time", "订单日期", "下单日期", "成交时间"]
        order_status_keywords = ["订单状态", "状态", "order_status", "order state"]
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
            if mapping["order_date"] is None:
                for kw in order_date_keywords:
                    if kw in header_lower:
                        mapping["order_date"] = idx
                        break
            if mapping["order_status"] is None:
                for kw in order_status_keywords:
                    if kw in header:
                        mapping["order_status"] = idx
                        break
        return mapping

    def _show_column_mapping_dialog(self, headers, auto_mapping):
        """显示列映射对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("📋 列映射选择")
        dialog.resize(500, 400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("请为每个字段选择对应的Excel列："))
        layout.addSpacing(10)
        
        combo_product_id = QComboBox()
        combo_product_id.addItems(["-- 不选择 --"] + headers)
        if auto_mapping.get("product_id") is not None:
            combo_product_id.setCurrentIndex(auto_mapping["product_id"] + 1)
        layout.addWidget(QLabel("商品ID列 *："))
        layout.addWidget(combo_product_id)
        
        combo_spec_code = QComboBox()
        combo_spec_code.addItems(["-- 不选择 --"] + headers)
        if auto_mapping.get("spec_code") is not None:
            combo_spec_code.setCurrentIndex(auto_mapping["spec_code"] + 1)
        layout.addWidget(QLabel("规格编码列 *："))
        layout.addWidget(combo_spec_code)
        
        combo_quantity = QComboBox()
        combo_quantity.addItems(["-- 不选择（默认为1） --"] + headers)
        if auto_mapping.get("quantity") is not None:
            combo_quantity.setCurrentIndex(auto_mapping["quantity"] + 1)
        layout.addWidget(QLabel("数量列："))
        layout.addWidget(combo_quantity)
        
        combo_order_date = QComboBox()
        combo_order_date.addItems(["-- 不选择 --"] + headers)
        if auto_mapping.get("order_date") is not None:
            combo_order_date.setCurrentIndex(auto_mapping["order_date"] + 1)
        layout.addWidget(QLabel("订单日期列："))
        layout.addWidget(combo_order_date)
        
        combo_order_status = QComboBox()
        combo_order_status.addItems(["-- 不选择 --"] + headers)
        if auto_mapping.get("order_status") is not None:
            combo_order_status.setCurrentIndex(auto_mapping["order_status"] + 1)
        layout.addWidget(QLabel("订单状态列（用于识别退款）："))
        layout.addWidget(combo_order_status)
        
        layout.addSpacing(20)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确认")
        btn_ok.setStyleSheet("QPushButton { background-color: #27ae60; color: white; padding: 8px 20px; border-radius: 4px; }")
        btn_cancel = QPushButton("取消")
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        result = {"product_id": None, "spec_code": None, "quantity": None, "order_date": None, "order_status": None}
        
        def on_ok():
            result["product_id"] = combo_product_id.currentIndex() - 1 if combo_product_id.currentIndex() > 0 else None
            result["spec_code"] = combo_spec_code.currentIndex() - 1 if combo_spec_code.currentIndex() > 0 else None
            result["quantity"] = combo_quantity.currentIndex() - 1 if combo_quantity.currentIndex() > 0 else None
            result["order_date"] = combo_order_date.currentIndex() - 1 if combo_order_date.currentIndex() > 0 else None
            result["order_status"] = combo_order_status.currentIndex() - 1 if combo_order_status.currentIndex() > 0 else None
            dialog.accept()
        
        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dialog.reject)
        
        if dialog.exec_() == QDialog.Accepted:
            return result
        return None
    
    def update_orders_display(self):
        """更新单量列显示"""
        # 获取当前导入的数据
        current_data = self.db.safe_fetchall("""
            SELECT product_id, spec_code, order_count, refund_count
            FROM imported_orders
            WHERE store_id=?
        """, (self.store_id,))

        # 计算每个商品的总订单数和退款数（直接用 product_id 即商品ID字符串）
        prod_order_totals = {}
        prod_refund_data = {}
        total_refund_sum = 0
        for prod_id, spec_code, order_count, refund_count in current_data:
            if prod_id not in prod_order_totals:
                prod_order_totals[prod_id] = 0
                prod_refund_data[prod_id] = []
            prod_order_totals[prod_id] += order_count or 0
            prod_refund_data[prod_id].append((spec_code, order_count or 0, refund_count or 0))
            total_refund_sum += refund_count or 0

        # 遍历表格行
        for row in range(self.table.rowCount()):
            prod_id_item = self.table.item(row, 1)
            if not prod_id_item:
                continue
            user_product_id = prod_id_item.data(Qt.UserRole)
            if not user_product_id:
                continue

            order_label_widget = self.table.cellWidget(row, 8)
            if order_label_widget and user_product_id:
                order_label = order_label_widget.layout().itemAt(0).widget()
                if order_label:
                    if user_product_id in prod_order_totals:
                        order_label.setText(f"{prod_order_totals[user_product_id]}单")
                        order_label.setStyleSheet("color: black; font-size: 19px;")
                    else:
                        order_label.setText("0单")
                        order_label.setStyleSheet("color: #95a5a6; font-size: 19px;")

            refund_orders_label = self.refund_widgets.get(row, {}).get('orders')
            refund_ratio_label = self.refund_widgets.get(row, {}).get('ratio')
            if user_product_id and user_product_id in prod_refund_data:
                spec_data = prod_refund_data[user_product_id]
                total_orders = sum(d[1] for d in spec_data)
                total_refund = sum(d[2] for d in spec_data)
                if total_orders > 0 and total_refund > 0:
                    refund_rate = total_refund / total_orders * 100
                    if refund_orders_label:
                        refund_orders_label.setText(f"{refund_rate:.2f}%")
                        refund_orders_label.setStyleSheet("color: #e74c3c; font-size: 19px; font-weight: bold;")
                    max_refund_spec = None
                    max_refund_rate_val = -1
                    for spec_code, oc, rc in spec_data:
                        if oc > 0 and rc > 0:
                            sr = rc / oc
                            if sr > max_refund_rate_val:
                                max_refund_rate_val = sr
                                max_refund_spec = spec_code
                    if refund_ratio_label:
                        if max_refund_spec:
                            refund_ratio_label.setText(str(max_refund_spec))
                            refund_ratio_label.setStyleSheet("color: #e74c3c; font-size: 19px; font-weight: bold;")
                        else:
                            refund_ratio_label.setText("无")
                            refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
                else:
                    if refund_orders_label:
                        refund_orders_label.setText("无")
                        refund_orders_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
                    if refund_ratio_label:
                        refund_ratio_label.setText("无")
                        refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            else:
                if refund_orders_label:
                    refund_orders_label.setText("无")
                    refund_orders_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
                if refund_ratio_label:
                    refund_ratio_label.setText("无")
                    refund_ratio_label.setStyleSheet("color: #95a5a6; font-size: 19px;")

        self.update_total_orders_label()
        self.update_order_range_label()

        # 强制刷新表格显示
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer
        QApplication.processEvents()
    
    def update_current_history_label(self):
        """更新当前使用数据标签"""
        if not hasattr(self, 'lbl_current_history'):
            return

        latest_record = self.db.safe_fetchall("""
            SELECT start_date, end_date, actual_orders, actual_amount, gross_profit,
                   refund_amount, refund_orders, promotion_fee, deduction, other_service, other,
                   gross_margin_rate, refund_rate_by_amount, refund_rate_by_orders,
                   unit_price, promotion_ratio, tech_fee,
                   net_profit, net_margin_rate, profit_per_order
            FROM manual_margin_data WHERE store_id=? ORDER BY start_date DESC, end_date DESC LIMIT 1
        """, (self.store_id,))

        if latest_record:
            record = latest_record[0]
            start_date = record[0] if record[0] else ""
            end_date = record[1] if record[1] else ""

            if start_date and len(start_date) >= 10:
                start_display = start_date[5:10]
            else:
                start_display = start_date

            if end_date and len(end_date) >= 10:
                end_display = end_date[5:10]
            else:
                end_display = end_date

            if start_display == end_display:
                date_str = start_display
            else:
                date_str = f"{start_display}~{end_display}"

            net_profit = record[17] if record[17] else 0
            net_margin = record[18] if record[18] else 0

            self.lbl_current_history.setText(
                f"📍 最新: {date_str} | 净利润: ¥{net_profit:.2f} ({net_margin:.2f}%)"
            )
            self.lbl_current_history.setStyleSheet("""
                QLabel {
                    color: #27ae60;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 6px 12px;
                    background-color: #e8f8f0;
                    border-radius: 4px;
                }
            """)
        else:
            self.lbl_current_history.setText("📍 当前: 暂无数据")
            self.lbl_current_history.setStyleSheet("""
                QLabel {
                    color: #7f8c8d;
                    font-size: 12px;
                    padding: 6px 12px;
                    background-color: #f5f5f5;
                    border-radius: 4px;
                }
            """)
    
    def update_total_orders_label(self):
        """更新总单量标签"""
        total_data = self.db.safe_fetchall("""
            SELECT SUM(order_count) FROM imported_orders WHERE store_id=?
        """, (self.store_id,))
        total = total_data[0][0] if total_data and total_data[0][0] else 0
        self.lbl_total_orders.setText(f"总单量: {total}")

    def update_order_range_label(self):
        """更新当前订单时间范围标签"""
        date_data = self.db.safe_fetchall("""
            SELECT order_date FROM imported_orders WHERE store_id=? AND order_date IS NOT NULL
        """, (self.store_id,))
        if not date_data:
            self.lbl_order_range.setText("当前订单时间范围: --")
            return
        all_dates = []
        for (date_range,) in date_data:
            if date_range and '~' in date_range:
                parts = date_range.split('~')
                all_dates.extend(parts)
            elif date_range:
                all_dates.append(date_range)
        if not all_dates:
            self.lbl_order_range.setText("当前订单时间范围: --")
            return
        try:
            parsed_dates = []
            for d in all_dates:
                if '/' in d:
                    m, day = d.split('/')
                    parsed_dates.append((int(m), int(day)))
            if parsed_dates:
                parsed_dates.sort()
                min_d = parsed_dates[0]
                max_d = parsed_dates[-1]
                if min_d != max_d:
                    range_str = f"{min_d[0]}/{min_d[1]}-{max_d[0]}/{max_d[1]}"
                else:
                    range_str = f"{min_d[0]}/{min_d[1]}"
                self.lbl_order_range.setText(f"当前订单时间范围: {range_str}")
            else:
                self.lbl_order_range.setText("当前订单时间范围: --")
        except:
            self.lbl_order_range.setText("当前订单时间范围: --")

    def update_compare_columns(self):
        """更新对比列数据 - 按订单时间范围与上一期对比"""
        # 获取当前导入的数据
        current_data = self.db.safe_fetchall("""
            SELECT product_id, spec_code, order_count, order_date
            FROM imported_orders
            WHERE store_id=?
        """, (self.store_id,))
        
        # 如果没有任何数据，显示 "-"
        if not current_data:
            for row in range(self.table.rowCount()):
                weight_compare_widget = self.table.cellWidget(row, 7)
                if weight_compare_widget:
                    weight_label = weight_compare_widget.layout().itemAt(0).widget()
                    weight_label.setText("-")
                    weight_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
                    
                order_compare_widget = self.table.cellWidget(row, 9)
                if order_compare_widget:
                    order_label = order_compare_widget.layout().itemAt(0).widget()
                    order_label.setText("-")
                    order_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            return
        
        # 获取当前订单的日期范围（用于找上一期）
        current_date_range = None
        for _, _, _, order_date in current_data:
            if order_date and '~' in order_date:
                current_date_range = order_date
                break
        
        # 解析当前日期范围获取结束日期
        current_end_date = None
        if current_date_range:
            try:
                parts = current_date_range.split('~')
                if len(parts) == 2:
                    current_end_date = parts[1].strip()
            except:
                pass
        
        # 找上一期历史记录（按订单日期范围排序，找小于当前结束日期的最接近的那一期）
        last_history_data = None
        if current_end_date:
            # 获取所有历史记录
            all_history = self.db.safe_fetchall("""
                SELECT id, snapshot_data
                FROM import_history
                WHERE store_id=? AND snapshot_data IS NOT NULL AND snapshot_data != ''
                ORDER BY import_time DESC
            """, (self.store_id,))

            for hist_id, snapshot_data in all_history:
                try:
                    snapshot = json.loads(snapshot_data)
                    # 从订单数据中解析日期范围
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
                        prev_end_date = f"{all_dates[-1][0]}/{all_dates[-1][1]}"
                        # 找小于当前结束日期的最接近的那一期
                        curr_parts = current_end_date.split('/')
                        curr_m, curr_d = int(curr_parts[0]), int(curr_parts[1])
                        prev_m, prev_d = int(all_dates[-1][0]), int(all_dates[-1][1])
                        if prev_m < curr_m or (prev_m == curr_m and prev_d < curr_d):
                            last_history_data = (snapshot_data, snapshot)
                            break
                except:
                    pass

        # 如果没找到按日期的对比，取最新的历史记录
        if not last_history_data:
            last_history = self.db.safe_fetchall("""
                SELECT snapshot_data
                FROM import_history
                WHERE store_id=? AND snapshot_data IS NOT NULL AND snapshot_data != ''
                ORDER BY import_time DESC
                LIMIT 1
            """, (self.store_id,))
            if last_history and last_history[0][0]:
                try:
                    last_history_data = (last_history[0][0], None)
                except:
                    pass
        
        # 如果还是没有可对比的历史，显示 "无"
        if not last_history_data:
            for row in range(self.table.rowCount()):
                weight_compare_widget = self.table.cellWidget(row, 7)
                if weight_compare_widget:
                    weight_label = weight_compare_widget.layout().itemAt(0).widget()
                    weight_label.setText("无")
                    weight_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
                    
                order_compare_widget = self.table.cellWidget(row, 9)
                if order_compare_widget:
                    order_label = order_compare_widget.layout().itemAt(0).widget()
                    order_label.setText("无")
                    order_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            return
        
        # 解析上一期的快照数据
        try:
            last_snapshot = json.loads(last_history_data[0])
            last_orders = last_snapshot.get("orders", {})
        except:
            for row in range(self.table.rowCount()):
                weight_compare_widget = self.table.cellWidget(row, 7)
                if weight_compare_widget:
                    weight_label = weight_compare_widget.layout().itemAt(0).widget()
                    weight_label.setText("无")
                    weight_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
                    
                order_compare_widget = self.table.cellWidget(row, 9)
                if order_compare_widget:
                    order_label = order_compare_widget.layout().itemAt(0).widget()
                    order_label.setText("无")
                    order_label.setStyleSheet("color: #95a5a6; font-size: 19px;")
            return
        
        # 计算每个商品的总订单数
        product_current = {}
        for prod_id, spec_code, order_count, _ in current_data:
            if prod_id not in product_current:
                product_current[prod_id] = {"orders": 0, "specs": {}}
            product_current[prod_id]["orders"] += order_count
            product_current[prod_id]["specs"][spec_code] = order_count

        # 解析上一期快照数据的 key（使用商品ID字符串）
        product_last = {}
        for key, data in last_orders.items():
            parts = key.split("_", 1)
            if len(parts) >= 2:
                user_product_id = parts[0]
                spec_code = parts[1]
                if user_product_id not in product_last:
                    product_last[user_product_id] = {"orders": 0, "specs": {}}
                product_last[user_product_id]["orders"] += data["count"]
                product_last[user_product_id]["specs"][spec_code] = data["count"]

        # 更新表格中的对比列
        for row in range(self.table.rowCount()):
            prod_id_item = self.table.item(row, 1)
            if not prod_id_item:
                continue
            user_product_id = prod_id_item.data(Qt.UserRole)
            if not user_product_id:
                continue

            # 权重对比（百分比，2位小数）
            weight_compare_widget = self.table.cellWidget(row, 7)
            if not weight_compare_widget:
                continue
            weight_label = weight_compare_widget.layout().itemAt(0).widget()
            if user_product_id and user_product_id in product_current and user_product_id in product_last:
                current_total_orders = product_current[user_product_id]["orders"]
                last_total_orders = product_last[user_product_id]["orders"]

                order_change = current_total_orders - last_total_orders
                if last_total_orders > 0:
                    order_change_percent = (order_change / last_total_orders * 100)
                else:
                    order_change_percent = 0

                if order_change_percent > 0:
                    weight_label.setText(f"🟢 ↑{order_change_percent:.2f}%")
                    weight_label.setStyleSheet("color: #27ae60; font-size: 19px; font-weight: bold;")
                elif order_change_percent < 0:
                    weight_label.setText(f"🔴 ↓{abs(order_change_percent):.2f}%")
                    weight_label.setStyleSheet("color: #c0392b; font-size: 19px; font-weight: bold;")
                else:
                    weight_label.setText("⚪ 0.00%")
                    weight_label.setStyleSheet("color: #7f8c8d; font-size: 19px;")
            else:
                # 商品不在对比数据中，显示 "无"
                weight_label.setText("无")
                weight_label.setStyleSheet("color: #95a5a6; font-size: 19px;")

            # 单量对比
            order_compare_widget = self.table.cellWidget(row, 9)
            if not order_compare_widget:
                continue
            order_label = order_compare_widget.layout().itemAt(0).widget()
            if user_product_id and user_product_id in product_current and user_product_id in product_last:
                current_orders = product_current[user_product_id]["orders"]
                last_orders_count = product_last[user_product_id]["orders"]
                order_change = current_orders - last_orders_count

                if order_change > 0:
                    order_label.setText(f"🟢 ↑{order_change}")
                    order_label.setStyleSheet("color: #27ae60; font-size: 19px; font-weight: bold;")
                elif order_change < 0:
                    order_label.setText(f"🔴 ↓{abs(order_change)}")
                    order_label.setStyleSheet("color: #c0392b; font-size: 19px; font-weight: bold;")
                else:
                    order_label.setText("⚪ 0")
                    order_label.setStyleSheet("color: #7f8c8d; font-size: 19px;")
            else:
                # 商品不在对比数据中，显示 "无"
                order_label.setText("无")
                order_label.setStyleSheet("color: #95a5a6; font-size: 19px;")

    def show_import_history(self):
        """显示导入历史记录对话框"""
        dialog = ImportHistoryDialog(self.store_id, self.store_name, self.db, self)
        dialog.exec_()
        self.update_total_orders_label()
        self.update_order_range_label()


# ==================== 导入历史记录对话框类 ====================

class ImportHistoryDialog(QDialog):
    """导入历史记录对话框"""
    def __init__(self, store_id, store_name, db, parent=None):
        super().__init__(parent)
        self.store_id = store_id
        self.store_name = store_name
        self.db = db
        self.parent_window = parent
        self.setWindowTitle(f"📜 {store_name} - 全部记录")
        self.resize(900, 600)
        self.setStyleSheet("background-color: #f5f5f5;")
        self.init_ui()
        self.load_history()
        self.check_old_data()
    
    def check_old_data(self):
        """检查是否有旧数据（imported_orders有数据但历史快照无效）"""
        # 检查 imported_orders 是否有数据
        current_orders = self.db.safe_fetchall(
            "SELECT product_id, spec_code, order_count, import_time FROM imported_orders WHERE store_id=?", (self.store_id,)
        )
        has_current_orders = current_orders and len(current_orders) > 0

        # 检查历史记录是否有有效快照（不仅要存在，还要 snapshot_data 不为空且能解析）
        history_records = self.db.safe_fetchall(
            "SELECT snapshot_data FROM import_history WHERE store_id=? ORDER BY import_time DESC LIMIT 1",
            (self.store_id,)
        )
        has_valid_history = False
        if history_records and history_records[0][0]:
            try:
                snapshot = json.loads(history_records[0][0])
                if snapshot and "orders" in snapshot:
                    has_valid_history = True
            except:
                has_valid_history = False

        # 如果有当前订单但没有有效历史，自动为旧数据创建快照
        if has_current_orders and not has_valid_history:
            # 根据旧数据创建快照
            from datetime import datetime
            orders_data = {}
            total_products = set()
            total_specs = 0
            total_orders = 0
            
            for prod_id, spec_code, order_count, import_time in current_orders:
                key = f"{prod_id}_{spec_code}"
                orders_data[key] = {"count": order_count, "dates": []}
                total_products.add(prod_id)
                total_specs += 1
                total_orders += order_count
            
            # 创建历史快照
            snapshot_data = json.dumps({"orders": orders_data})
            self.db.safe_execute("""
                INSERT INTO import_history (store_id, import_time, file_name, total_products, total_specs, total_orders, total_amount, snapshot_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (self.store_id, import_time if import_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "旧数据导入", len(total_products), total_specs, total_orders, 0, snapshot_data))
            
            if self.parent_window:
                self.parent_window.main_app.show_toast("✅ 已为旧数据创建历史快照")
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 标题
        title_label = QLabel(f"📊 {self.store_name} - 订单全部记录")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(title_label)
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "导入时间", "文件名", "订单时间范围", "商品数", "总单量", "操作"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        
        self.btn_close = QPushButton("关闭")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        self.btn_close.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
    
    def load_history(self):
        """加载历史记录 - 按订单日期范围排序（最新日期排最上面）"""
        # 调试：检查 snapshot_data 格式
        self.db._check_and_migrate_snapshot_data()

        records = self.db.safe_fetchall("""
            SELECT id, import_time, file_name, total_products, total_specs, total_orders, total_amount, snapshot_data
            FROM import_history
            WHERE store_id=?
        """, (self.store_id,))

        # 计算每个记录的订单日期范围，并按结束日期降序排序
        def get_order_end_date(record):
            _, _, _, _, _, _, _, snapshot_data = record
            if snapshot_data:
                try:
                    snapshot = json.loads(snapshot_data)
                    if snapshot and "orders" in snapshot:
                        all_dates = []
                        for key, data in snapshot["orders"].items():
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
            return (0, 0)  # 默认最小的日期

        # 按订单结束日期降序排序
        records.sort(key=get_order_end_date, reverse=True)

        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            hist_id, import_time, file_name, total_products, total_specs, total_orders, total_amount, snapshot_data = record

            # 导入时间
            time_item = QTableWidgetItem(import_time)
            time_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, time_item)

            # 文件名
            file_item = QTableWidgetItem(file_name if file_name else "未知")
            file_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 1, file_item)

            # 订单时间范围（从snapshot_data中提取所有日期计算范围）
            order_range_str = "无日期"
            if snapshot_data:
                try:
                    snapshot = json.loads(snapshot_data)
                    if snapshot and "orders" in snapshot:
                        all_dates = []
                        for key, data in snapshot["orders"].items():
                            if isinstance(data, dict) and "dates" in data:
                                for date_val in data.get("dates", []):
                                    if date_val and '/' in date_val:
                                        try:
                                            m, d = date_val.split('/')
                                            all_dates.append((int(m), int(d)))
                                        except:
                                            pass
                        if all_dates:
                            all_dates.sort()
                            min_date = all_dates[0]
                            max_date = all_dates[-1]
                            if min_date != max_date:
                                order_range_str = f"{min_date[0]}/{min_date[1]}-{max_date[0]}/{max_date[1]}"
                            else:
                                order_range_str = f"{min_date[0]}/{min_date[1]}"
                except:
                    order_range_str = "解析失败"

            range_item = QTableWidgetItem(order_range_str)
            range_item.setFlags(Qt.ItemIsEnabled)
            range_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, range_item)

            # 商品数
            prod_item = QTableWidgetItem(str(total_products))
            prod_item.setFlags(Qt.ItemIsEnabled)
            prod_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, prod_item)

            # 总单量
            orders_item = QTableWidgetItem(str(total_orders))
            orders_item.setFlags(Qt.ItemIsEnabled)
            orders_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, orders_item)

            # 操作按钮（应用和删除）
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(1, 1, 1, 1)
            btn_layout.setAlignment(Qt.AlignCenter)
            btn_layout.setSpacing(1)
            
            btn_apply = QPushButton("应用")
            btn_apply.setFixedSize(45, 28)
            btn_apply.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 1px 2px;
                }
                QPushButton:hover {
                    background-color: #229954;
                }
            """)
            btn_apply.clicked.connect(lambda checked, hid=hist_id: self.apply_history(hid))
            btn_layout.addWidget(btn_apply)
            
            btn_delete = QPushButton("删除")
            btn_delete.setFixedSize(45, 28)
            btn_delete.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    font-size: 11px;
                    padding: 1px 2px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            btn_delete.clicked.connect(lambda checked, hid=hist_id: self.delete_single_history(hid))
            btn_layout.addWidget(btn_delete)
            
            self.table.setCellWidget(row, 5, btn_widget)
    
    def delete_single_history(self, history_id):
        """删除单条历史记录"""
        # 检查是否删除的是最新的历史记录，如果是则同时清空 imported_orders
        latest_history = self.db.safe_fetchall("""
            SELECT id FROM import_history WHERE store_id=? ORDER BY import_time DESC LIMIT 1
        """, (self.store_id,))
        
        is_latest = latest_history and latest_history[0][0] == history_id
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认删除")
        msg_box.setText("确定要删除这条导入记录吗？")
        msg_box.setIcon(QMessageBox.Warning)
        
        yes_btn = msg_box.addButton("确定", QMessageBox.YesRole)
        no_btn = msg_box.addButton("取消", QMessageBox.NoRole)
        
        yes_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        no_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        
        msg_box.setDefaultButton(no_btn)
        msg_box.exec_()
        
        if msg_box.clickedButton() == yes_btn:
            self.db.safe_execute("DELETE FROM import_history WHERE id=?", (history_id,))
            
            # 检查是否还有历史记录
            remaining_history = self.db.safe_fetchall("""
                SELECT COUNT(*) FROM import_history WHERE store_id=?
            """, (self.store_id,))
            
            # 如果删除的是最新记录或者没有任何历史记录了，清空 imported_orders
            if is_latest or (remaining_history and remaining_history[0][0] == 0):
                self.db.safe_execute("DELETE FROM imported_orders WHERE store_id=?", (self.store_id,))

            self.load_history()

            self.parent_window.update_total_orders_label()
            self.parent_window.update_order_range_label()
            self.parent_window.main_app.show_toast("✅ 已删除")
    
    def delete_selected(self):
        """删除选中的历史记录"""
        selected_rows = []
        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                selected_rows.append(row)
        
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的记录")
            return
        
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_rows)} 条记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for row in reversed(selected_rows):
                hist_id = self.table.item(row, 0).data(Qt.UserRole)
                self.db.safe_execute("DELETE FROM import_history WHERE id=?", (hist_id,))
            self.load_history()
    
    def apply_history(self, history_id):
        """应用历史记录的订单数据"""
        # 获取历史记录
        history_records = self.db.safe_fetchall(
            "SELECT snapshot_data FROM import_history WHERE id=?",
            (history_id,)
        )

        if not history_records or not history_records[0][0]:
            return

        try:
            snapshot = json.loads(history_records[0][0])
            orders_data = snapshot.get("orders", {})
        except:
            return

        # 清空当前的 imported_orders
        self.db.safe_execute("DELETE FROM imported_orders WHERE store_id=?", (self.store_id,))

        # 恢复历史订单数据
        for key, data in orders_data.items():
            parts = key.split("_", 1)
            if len(parts) >= 2:
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
                """, (self.store_id, user_product_id, spec_code, order_count,
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S"), date_range, 0, refund_count))

        # 关闭对话框
        self.accept()

        # 刷新界面显示
        if self.parent_window:
            self.parent_window.load_products()
            self.parent_window.calculate_weights_from_orders()
            self.parent_window.update_compare_columns()
            self.parent_window.update_product_avg_price()
            self.parent_window.calculate_total_margin()
            self.parent_window.update_total_orders_label()
            self.parent_window.update_order_range_label()
            self.parent_window.main_app.show_toast("✅ 已应用")

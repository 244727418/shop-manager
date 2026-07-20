# -*- coding: utf-8 -*-
"""推广日报数据分析窗口。"""
import json
import os
import re
import time
from datetime import datetime, timedelta

from PyQt5.QtCore import QDate, QPropertyAnimation, QRect, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDateEdit, QDialog, QFileDialog,
    QCheckBox, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressDialog, QPushButton, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

try:
    from manager.file_dialog_memory import remembered_open_file
except ImportError:
    from file_dialog_memory import remembered_open_file

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None

try:
    from ..window_icons import apply_window_icon
except ImportError:
    from window_icons import apply_window_icon


PROMOTION_COLUMNS = [
    ("product_id", "商品ID"),
    ("product_title", "商品标题"),
    ("bid_method", "出价方式"),
    ("cost", "成交花费(元)"),
    ("transaction_amount", "交易额(元)"),
    ("roi", "实际投产比"),
    ("net_transaction_amount", "净交易额(元)"),
    ("net_roi", "净实际投产比"),
    ("net_orders", "净成交笔数"),
    ("net_profit", "净利润"),
    ("net_margin_rate", "净利率"),
    ("cost_per_net_order", "每笔净成交花费(元)"),
    ("cpc", "单次点击成本(CPC)"),
    ("impressions", "曝光量"),
    ("clicks", "点击量"),
    ("promotion_impressions", "推广曝光量"),
    ("promotion_impression_share", "推广曝光占比"),
    ("ctr", "点击率"),
    ("click_conversion_rate", "点击转化率"),
]
PROMOTION_LABELS = dict(PROMOTION_COLUMNS)
HIDDEN_PROMOTION_COLUMNS = {"bid_method", "product_title", "transaction_amount", "roi"}
DISPLAY_PROMOTION_COLUMNS = [(key, label) for key, label in PROMOTION_COLUMNS if key not in HIDDEN_PROMOTION_COLUMNS]
DEFAULT_PROMOTION_COLUMN_ORDER = [key for key, _label in DISPLAY_PROMOTION_COLUMNS]
HISTORY_PROMOTION_COLUMNS = []
for _key, _label in DISPLAY_PROMOTION_COLUMNS:
    HISTORY_PROMOTION_COLUMNS.append((_key, _label))
    if _key == "cost_per_net_order":
        HISTORY_PROMOTION_COLUMNS.append(("net_amount_per_order", "每笔净成交金额"))
PROMOTION_COLUMN_WIDTHS = {
    "product_id": 100,
    "product_title": 100,
    "bid_method": 76,
    "cost": 92,
    "transaction_amount": 92,
    "roi": 78,
    "net_transaction_amount": 98,
    "net_roi": 88,
    "net_orders": 78,
    "net_profit": 86,
    "net_margin_rate": 78,
    "cost_per_net_order": 112,
    "net_amount_per_order": 112,
    "cpc": 96,
    "impressions": 78,
    "clicks": 70,
    "promotion_impressions": 90,
    "promotion_impression_share": 96,
    "ctr": 72,
    "click_conversion_rate": 88,
}
PROMOTION_COLUMN_LIMITS = {
    "product_id": (38, 96),
    "product_title": (50, 120),
    "bid_method": (34, 70),
    "cost": (46, 92),
    "transaction_amount": (46, 92),
    "roi": (34, 66),
    "net_transaction_amount": (48, 96),
    "net_roi": (34, 72),
    "net_orders": (34, 70),
    "net_profit": (42, 88),
    "net_margin_rate": (38, 78),
    "cost_per_net_order": (48, 98),
    "net_amount_per_order": (48, 98),
    "cpc": (46, 86),
    "impressions": (38, 78),
    "clicks": (34, 70),
    "promotion_impressions": (40, 82),
    "promotion_impression_share": (42, 86),
    "ctr": (34, 70),
    "click_conversion_rate": (42, 82),
}

DIRECT_COLUMNS = [
    key for key, _label in PROMOTION_COLUMNS
    if key not in ("bid_method", "cpc", "promotion_impression_share", "net_profit", "net_margin_rate")
]
NUMERIC_COLUMNS = [key for key, _label in PROMOTION_COLUMNS if key not in ("product_id", "product_title", "bid_method")]
HISTORY_NUMERIC_COLUMNS = set(NUMERIC_COLUMNS) | {"net_amount_per_order"}
CORE_COMPARE_COLUMNS = [
    key for key, _label in PROMOTION_COLUMNS
    if key not in ("product_id", "product_title", "bid_method")
]
CORE_COMPARE_COLUMNS.append("net_amount_per_order")
LOWER_IS_BETTER = {"cost", "cost_per_net_order", "cpc"}
COMPARE_BASE_ROLE = Qt.UserRole + 41
COMPARE_TEXT_ROLE = Qt.UserRole + 42
COMPARE_COLOR_ROLE = Qt.UserRole + 43


def _weekday_text(qdate):
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][qdate.dayOfWeek() - 1]


def _promotion_quick_range(today, mode, latest_date=None):
    if mode == "recent_7":
        end = today.addDays(-1)
        return end.addDays(-6), end
    monday = today.addDays(1 - today.dayOfWeek())
    if mode == "last_week":
        return monday.addDays(-7), monday.addDays(-1)
    if mode == "this_week":
        end = latest_date if latest_date and latest_date.isValid() else today
        return monday, end
    raise ValueError(f"未知快捷日期范围：{mode}")


def _normalize_header(text):
    return re.sub(r"[\s（）()_\-]+", "", str(text or "").strip().lower())


def _parse_number(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            if pd is not None and pd.isna(value):
                return 0.0
        except Exception:
            pass
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "--", "-"):
        return 0.0
    is_percent = "%" in text
    for token in ("￥", "¥", "元", ",", " "):
        text = text.replace(token, "")
    text = text.replace("%", "")
    try:
        number = float(text)
    except Exception:
        return 0.0
    if is_percent:
        return number / 100 if number > 1 else number
    return number


def _fmt_number(value, digits=2):
    try:
        value = float(value or 0)
    except Exception:
        value = 0.0
    if abs(value - int(value)) < 0.000001:
        return str(int(value))
    return f"{value:.{digits}f}"


def _fmt_money(value):
    return f"¥{float(value or 0):.2f}"


def _fmt_ratio(value):
    return f"{float(value or 0) * 100:.2f}%"


def _apply_plain_table_focus_style(table):
    table.setFocusPolicy(Qt.NoFocus)
    table.setStyleSheet("""
        QTableWidget {
            outline: 0;
            padding: 0px;
            selection-background-color: #dbeafe;
            selection-color: #111827;
        }
        QTableWidget::item {
            border: none;
            outline: none;
            padding: 0px;
        }
        QTableWidget::item:focus {
            border: none;
            outline: none;
            padding: 0px;
        }
        QTableWidget::item:selected {
            border: none;
            outline: none;
            padding: 0px;
            background-color: #dbeafe;
            color: #111827;
        }
        QHeaderView::section {
            padding: 0px;
            margin: 0px;
        }
    """)


def _font_text_width(font, text):
    metrics = QFontMetrics(font)
    if hasattr(metrics, "horizontalAdvance"):
        return metrics.horizontalAdvance(text)
    return metrics.width(text)


def _wrap_text_to_width(text, font, width):
    width = max(8, int(width) - 2)
    lines = []
    metrics = QFontMetrics(font)
    for raw_line in str(text or "").splitlines() or [""]:
        current = ""
        for char in raw_line:
            candidate = current + char
            if current and _font_text_width(font, candidate) > width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return "\n".join(lines)


def _wrap_table_headers(table, labels):
    header_font = table.horizontalHeader().font()
    max_lines = 1
    for col, label in enumerate(labels):
        item = table.horizontalHeaderItem(col)
        if not item:
            continue
        wrapped = _wrap_text_to_width(label, header_font, table.columnWidth(col))
        item.setText(wrapped)
        max_lines = max(max_lines, len(wrapped.splitlines()) or 1)
    header_height = min(76, max(30, QFontMetrics(header_font).height() * max_lines + 4))
    table.horizontalHeader().setFixedHeight(header_height)


def _resize_table_columns_by_values(
    table,
    column_keys=None,
    fixed_widths=None,
    default_min=34,
    default_max=110,
    fill_viewport=False,
):
    fixed_widths = fixed_widths or {}
    column_keys = column_keys or []
    widths = []
    flexible_cols = []
    for col in range(table.columnCount()):
        if col in fixed_widths:
            widths.append(int(fixed_widths[col]))
            continue
        key = column_keys[col] if col < len(column_keys) else None
        min_width, max_width = PROMOTION_COLUMN_LIMITS.get(key, (default_min, default_max))
        width = min_width
        for row in range(table.rowCount()):
            item = table.item(row, col)
            if not item:
                continue
            font = item.font() if item.font() else table.font()
            text_width = max((_font_text_width(font, line) for line in item.text().splitlines()), default=0)
            width = max(width, text_width + 2)
        widths.append(min(max(width, min_width), max_width))
        flexible_cols.append(col)

    if fill_viewport and flexible_cols:
        viewport_width = max(0, table.viewport().width() - 2)
        total_width = sum(widths)
        if viewport_width > total_width:
            extra = viewport_width - total_width
            weight_total = sum(max(widths[col], 1) for col in flexible_cols)
            used = 0
            for index, col in enumerate(flexible_cols):
                if index == len(flexible_cols) - 1:
                    addition = extra - used
                else:
                    addition = int(extra * max(widths[col], 1) / weight_total)
                    used += addition
                widths[col] += addition

    for col, width in enumerate(widths):
        table.setColumnWidth(col, width)


class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, text="", sort_value=None, pinned=False):
        super().__init__(str(text))
        self.sort_value = sort_value
        self.pinned = pinned
        self.pin_as_less = True

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            if self.pinned != other.pinned:
                return self.pinned if self.pin_as_less else not self.pinned
            left = self.sort_value
            right = other.sort_value
            if left is not None and right is not None:
                try:
                    return float(left) < float(right)
                except (TypeError, ValueError):
                    return str(left) < str(right)
        return super().__lt__(other)


class PromotionCompareDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        base_text = index.data(COMPARE_BASE_ROLE)
        compare_text = index.data(COMPARE_TEXT_ROLE)
        compare_color = index.data(COMPARE_COLOR_ROLE)
        if not compare_text:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, opt, painter, opt.widget)

        painter.save()
        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget).adjusted(2, 1, -2, -1)
        metrics = QFontMetrics(opt.font)
        line_height = metrics.height()
        total_height = line_height * 2 + 2
        top = rect.y() + max(0, (rect.height() - total_height) // 2)
        base_rect = QRect(rect.x(), top, rect.width(), line_height)
        compare_rect = QRect(rect.x(), top + line_height + 2, rect.width(), line_height)

        if opt.state & QStyle.State_Selected:
            painter.setPen(opt.palette.highlightedText().color())
        else:
            painter.setPen(opt.palette.text().color())
        painter.drawText(base_rect, Qt.AlignCenter, str(base_text or index.data(Qt.DisplayRole) or ""))

        font = QFont(opt.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(compare_color or "#6b7280"))
        painter.drawText(compare_rect, Qt.AlignCenter, str(compare_text))
        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        if index.data(COMPARE_TEXT_ROLE):
            hint.setHeight(max(hint.height(), 44))
        return hint


class PromotionColumnMappingDialog(QDialog):
    def __init__(self, headers, auto_mapping, parent=None):
        super().__init__(parent)
        apply_window_icon(self, "promotion")
        self.setWindowTitle("推广数据列映射")
        self.resize(520, 560)
        self._combos = {}

        layout = QVBoxLayout(self)
        tip = QLabel("请确认导入表列映射。商品ID必选，其余未选择的指标按 0 处理。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #666;")
        layout.addWidget(tip)

        for key in DIRECT_COLUMNS:
            label_text = dict(PROMOTION_COLUMNS)[key]
            row = QHBoxLayout()
            field_label = QLabel(label_text)
            row.addWidget(field_label)
            combo = QComboBox()
            combo.addItem("不导入", None)
            for idx, header in enumerate(headers):
                combo.addItem(str(header), idx)
            if auto_mapping.get(key) is not None:
                combo.setCurrentIndex(auto_mapping[key] + 1)
            row.addWidget(combo)
            layout.addLayout(row)
            self._combos[key] = combo
            if key == "cost":
                self._cost_label = field_label

        self._default_cost_index = self._combos["cost"].currentIndex()
        normalized_headers = [_normalize_header(header) for header in headers]
        self._marketing_cost_column = next(
            (idx for idx, header in enumerate(normalized_headers) if "成交营销花费" in header),
            None,
        )
        self.chk_use_marketing_cost = QCheckBox("成交花费映射为【成交营销花费】")
        self.chk_use_marketing_cost.setEnabled(self._marketing_cost_column is not None)
        if self._marketing_cost_column is None:
            self.chk_use_marketing_cost.setToolTip("导入表中未识别到【成交营销花费】列")
        layout.addWidget(self.chk_use_marketing_cost)

        row = QHBoxLayout()
        row.addWidget(QLabel("结算券花费(元)"))
        combo = QComboBox()
        combo.addItem("不导入", None)
        for idx, header in enumerate(headers):
            combo.addItem(str(header), idx)
        if auto_mapping.get("settlement_coupon_cost") is not None:
            combo.setCurrentIndex(auto_mapping["settlement_coupon_cost"] + 1)
        row.addWidget(combo)
        layout.addLayout(row)
        self._combos["settlement_coupon_cost"] = combo

        self.chk_deduct_settlement_coupon = QCheckBox("净交易额减去结算券花费")
        layout.addWidget(self.chk_deduct_settlement_coupon)
        def sync_coupon_option():
            enabled = combo.currentData() is not None and not self.chk_use_marketing_cost.isChecked()
            self.chk_deduct_settlement_coupon.setEnabled(enabled)
            if not enabled:
                self.chk_deduct_settlement_coupon.setChecked(False)

        def sync_marketing_cost(checked):
            self._cost_label.setText("成交营销花费(元)" if checked else PROMOTION_LABELS["cost"])
            target = self._marketing_cost_column + 1 if checked else self._default_cost_index
            self._combos["cost"].setCurrentIndex(target)
            self.chk_deduct_settlement_coupon.setChecked(False)
            self.chk_use_marketing_cost.setEnabled(
                self._marketing_cost_column is not None
                and not self.chk_deduct_settlement_coupon.isChecked()
            )
            sync_coupon_option()

        def sync_marketing_option(checked):
            self.chk_use_marketing_cost.setEnabled(
                self._marketing_cost_column is not None and not checked
            )

        combo.currentIndexChanged.connect(sync_coupon_option)
        self.chk_use_marketing_cost.toggled.connect(sync_marketing_cost)
        self.chk_deduct_settlement_coupon.toggled.connect(sync_marketing_option)
        sync_coupon_option()

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def mapping(self):
        return {key: combo.currentData() for key, combo in self._combos.items()}

    def deduct_settlement_coupon(self):
        return self.chk_deduct_settlement_coupon.isChecked()


class PromotionColumnOrderDialog(QDialog):
    def __init__(self, current_order, parent=None):
        super().__init__(parent)
        apply_window_icon(self, "promotion")
        self.setWindowTitle("推广数据列设置")
        self.resize(420, 560)
        layout = QVBoxLayout(self)

        tip = QLabel("图片列固定在最左，操作列固定在最右。这里只调整中间数据列顺序。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #666;")
        layout.addWidget(tip)

        self.list_widget = QListWidget()
        for key in current_order:
            item = QListWidgetItem(PROMOTION_LABELS.get(key, key))
            item.setData(Qt.UserRole, key)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        move_row = QHBoxLayout()
        btn_up = QPushButton("上移")
        btn_down = QPushButton("下移")
        btn_default = QPushButton("恢复默认")
        btn_up.clicked.connect(lambda: self._move_selected(-1))
        btn_down.clicked.connect(lambda: self._move_selected(1))
        btn_default.clicked.connect(self._restore_default)
        move_row.addWidget(btn_up)
        move_row.addWidget(btn_down)
        move_row.addWidget(btn_default)
        layout.addLayout(move_row)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_save.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _move_selected(self, step):
        row = self.list_widget.currentRow()
        target = row + step
        if row < 0 or target < 0 or target >= self.list_widget.count():
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(target, item)
        self.list_widget.setCurrentRow(target)

    def _restore_default(self):
        self.list_widget.clear()
        for key in DEFAULT_PROMOTION_COLUMN_ORDER:
            item = QListWidgetItem(PROMOTION_LABELS.get(key, key))
            item.setData(Qt.UserRole, key)
            self.list_widget.addItem(item)

    def column_order(self):
        order = []
        for row in range(self.list_widget.count()):
            key = self.list_widget.item(row).data(Qt.UserRole)
            if key in PROMOTION_LABELS:
                order.append(key)
        return order


class PromotionDataDialog(QDialog):
    def __init__(self, store_id, store_name, db, main_app=None, parent=None):
        super().__init__(parent)
        apply_window_icon(self, "promotion")
        self.store_id = store_id
        self.store_name = store_name
        self.db = db
        self.main_app = main_app
        self.column_order = self._load_column_order()
        self.copy_bubble = None
        self._copy_bubble_anims = []
        self._applying_column_widths = False
        self.setWindowTitle(f"推广数据分析 - {store_name}")
        self.resize(1280, 720)
        self._build_ui()
        self.load_current_date()

    def _load_column_order(self):
        raw = self.db.get_setting("promotion_data_column_order", "")
        try:
            order = json.loads(raw) if raw else []
        except Exception:
            order = []
        valid = [key for key in order if key in DEFAULT_PROMOTION_COLUMN_ORDER]
        for index, key in enumerate(DEFAULT_PROMOTION_COLUMN_ORDER):
            if key in valid:
                continue
            insert_at = len(valid)
            for previous_key in reversed(DEFAULT_PROMOTION_COLUMN_ORDER[:index]):
                if previous_key in valid:
                    insert_at = valid.index(previous_key) + 1
                    break
            valid.insert(insert_at, key)
        return valid

    def _save_column_order(self, order):
        self.db.set_setting("promotion_data_column_order", json.dumps(order, ensure_ascii=False))
        self.column_order = order

    def _load_column_widths(self):
        raw = self.db.get_setting("promotion_data_column_widths", "")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {}
        result = {}
        for key, width in data.items():
            if key in PROMOTION_LABELS:
                try:
                    result[key] = max(30, min(500, int(width)))
                except Exception:
                    pass
        return result

    def _save_column_width(self, key, width):
        if key not in PROMOTION_LABELS:
            return
        widths = self._load_column_widths()
        widths[key] = max(30, min(500, int(width)))
        self.db.set_setting("promotion_data_column_widths", json.dumps(widths, ensure_ascii=False))

    def _apply_main_table_columns(self):
        headers = self._main_table_headers()
        self._applying_column_widths = True
        try:
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setColumnWidth(0, 78)
            for index, key in enumerate(self.column_order, start=1):
                self.table.setColumnWidth(index, PROMOTION_COLUMN_WIDTHS.get(key, 88))
            self.table.setColumnWidth(len(headers) - 1, 92)
        finally:
            self._applying_column_widths = False

    def _main_table_headers(self):
        return ["图片"] + [self._header_label(key) for key in self.column_order] + ["操作"]

    def _resize_main_table_columns(self):
        last_col = len(self.column_order) + 1
        column_keys = [None] + self.column_order + [None]
        fixed_widths = {0: 80, last_col: 60}
        saved_widths = self._load_column_widths()
        for index, key in enumerate(self.column_order, start=1):
            if key == "product_title":
                fixed_widths[index] = saved_widths.get(key, PROMOTION_COLUMN_WIDTHS.get(key, 100))
            elif key in saved_widths:
                fixed_widths[index] = saved_widths[key]
        self._applying_column_widths = True
        try:
            _resize_table_columns_by_values(
                self.table,
                column_keys=column_keys,
                fixed_widths=fixed_widths,
                default_min=34,
                default_max=104,
                fill_viewport=True,
            )
            _wrap_table_headers(self.table, self._main_table_headers())
        finally:
            self._applying_column_widths = False

    def _header_label(self, key):
        label = PROMOTION_LABELS.get(key, key)
        breaks = {
            "cost_per_net_order": "每笔净成交\n花费(元)",
            "cpc": "单次点击\n成本(CPC)",
            "promotion_impressions": "推广\n曝光量",
            "promotion_impression_share": "推广曝光\n占比",
            "click_conversion_rate": "点击\n转化率",
            "net_transaction_amount": "净交易额\n(元)",
            "transaction_amount": "交易额\n(元)",
            "net_roi": "净实际\n投产比",
            "net_profit": "净利润",
            "net_margin_rate": "净利率",
        }
        return breaks.get(key, label)

    def open_column_order_dialog(self):
        dialog = PromotionColumnOrderDialog(self.column_order, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        order = dialog.column_order()
        self._save_column_order(order)
        self.load_current_date()

    def _key_for_column(self, column):
        if 1 <= column <= len(self.column_order):
            return self.column_order[column - 1]
        return None

    def _column_for_key(self, key):
        if key in self.column_order:
            return self.column_order.index(key) + 1
        return -1

    def _on_main_header_clicked(self, logical_index):
        key = self._key_for_column(logical_index)
        if not key:
            return
        old_key = self.db.get_setting("promotion_data_sort_key", "")
        old_order = self.db.get_setting("promotion_data_sort_order", "desc")
        if old_key == key:
            order = "asc" if old_order == "desc" else "desc"
        else:
            order = "desc"
        self.db.set_setting("promotion_data_sort_key", key)
        self.db.set_setting("promotion_data_sort_order", order)
        self._apply_saved_main_sort()

    def _on_main_section_resized(self, logical_index, _old_size, new_size):
        if self._applying_column_widths:
            return
        key = self._key_for_column(logical_index)
        if not key:
            return
        self._save_column_width(key, new_size)
        QTimer.singleShot(0, self._resize_main_table_columns)

    def _apply_saved_main_sort(self):
        key = self.db.get_setting("promotion_data_sort_key", "")
        column = self._column_for_key(key)
        if column < 0:
            self.table.horizontalHeader().setSortIndicatorShown(False)
            return
        order_text = self.db.get_setting("promotion_data_sort_order", "desc")
        order = Qt.AscendingOrder if order_text == "asc" else Qt.DescendingOrder
        for row in range(self.table.rowCount()):
            for col in range(1, len(self.column_order) + 1):
                item = self.table.item(row, col)
                if isinstance(item, NumericTableWidgetItem):
                    item.pin_as_less = order == Qt.AscendingOrder
        self.table.sortItems(column, order)
        self.table.horizontalHeader().setSortIndicator(column, order)
        self.table.horizontalHeader().setSortIndicatorShown(True)

    def _on_main_cell_clicked(self, row, column):
        if self._key_for_column(column) != "product_id":
            return
        item = self.table.item(row, column)
        product_id = item.text().strip() if item else ""
        if not product_id:
            return
        QApplication.clipboard().setText(product_id)
        self._show_copy_bubble()

    def _show_copy_bubble(self):
        if self.copy_bubble is None:
            self.copy_bubble = QLabel("已复制商品ID", self)
            self.copy_bubble.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.copy_bubble.setAlignment(Qt.AlignCenter)
            self.copy_bubble.setStyleSheet("""
                QLabel {
                    background: rgba(17, 24, 39, 210);
                    color: white;
                    border-radius: 12px;
                    padding: 7px 14px;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
            effect = QGraphicsOpacityEffect(self.copy_bubble)
            self.copy_bubble.setGraphicsEffect(effect)
        self.copy_bubble.adjustSize()
        table_top = self.table.mapTo(self, self.table.rect().topLeft()).y() if hasattr(self, "table") else 80
        x = max(10, (self.width() - self.copy_bubble.width()) // 2)
        y = max(10, table_top + 12)
        self.copy_bubble.move(x, y)
        self.copy_bubble.show()
        self.copy_bubble.raise_()
        effect = self.copy_bubble.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(self.copy_bubble)
            self.copy_bubble.setGraphicsEffect(effect)
        fade_in = QPropertyAnimation(effect, b"opacity", self)
        fade_in.setDuration(100)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_out = QPropertyAnimation(effect, b"opacity", self)
        fade_out.setDuration(300)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.finished.connect(self.copy_bubble.hide)
        fade_in.finished.connect(lambda: QTimer.singleShot(100, fade_out.start))
        self._copy_bubble_anims = [fade_in, fade_out]
        fade_in.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("导入日期："))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate().addDays(-1))
        self.date_edit.dateChanged.connect(lambda _date: self._select_single_date())
        top.addWidget(self.date_edit)
        self.date_label = QLabel("")
        self.date_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        top.addWidget(self.date_label)

        btn_prev = QPushButton("前一天")
        btn_next = QPushButton("后一天")
        self.btn_import = QPushButton("导入数据")
        self.btn_history = QPushButton("查看全部数据")
        self.btn_columns = QPushButton("列设置")
        btn_prev.clicked.connect(lambda: self._shift_date(-1))
        btn_next.clicked.connect(lambda: self._shift_date(1))
        self.btn_import.clicked.connect(self.import_promotion_data)
        self.btn_history.clicked.connect(self.open_import_history_dialog)
        self.btn_columns.clicked.connect(self.open_column_order_dialog)
        top.addWidget(btn_prev)
        top.addWidget(btn_next)
        top.addWidget(self.btn_import)
        top.addWidget(self.btn_history)
        top.addWidget(self.btn_columns)
        top.addStretch()
        layout.addLayout(top)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("统计范围："))
        self.range_start_edit = QDateEdit()
        self.range_end_edit = QDateEdit()
        for editor in (self.range_start_edit, self.range_end_edit):
            editor.setDisplayFormat("yyyy-MM-dd")
            editor.setCalendarPopup(True)
            editor.setDate(self.date_edit.date())
        range_row.addWidget(self.range_start_edit)
        range_row.addWidget(QLabel("至"))
        range_row.addWidget(self.range_end_edit)
        btn_query = QPushButton("查询")
        btn_recent_7 = QPushButton("近7天")
        btn_last_week = QPushButton("上周")
        btn_this_week = QPushButton("本周")
        btn_query.clicked.connect(self._apply_selected_range)
        btn_recent_7.clicked.connect(lambda: self._set_quick_range("recent_7"))
        btn_last_week.clicked.connect(lambda: self._set_quick_range("last_week"))
        btn_this_week.clicked.connect(lambda: self._set_quick_range("this_week"))
        range_row.addWidget(btn_query)
        range_row.addWidget(btn_recent_7)
        range_row.addWidget(btn_last_week)
        range_row.addWidget(btn_this_week)
        range_row.addStretch()
        layout.addLayout(range_row)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSortingEnabled(False)
        _apply_plain_table_focus_style(self.table)
        table_font = QFont("Microsoft YaHei", 12)
        self.table.setFont(table_font)
        header_font = QFont("Microsoft YaHei", 10)
        header_font.setBold(True)
        self.table.horizontalHeader().setFont(header_font)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.horizontalHeader().setFixedHeight(48)
        self.table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                padding: 0px;
                margin: 0px;
                border: 1px solid #d0d5da;
                background-color: #f3f6f8;
            }
        """)
        self._apply_main_table_columns()
        self.table.horizontalHeader().sectionClicked.connect(self._on_main_header_clicked)
        self.table.horizontalHeader().sectionResized.connect(self._on_main_section_resized)
        self.table.cellClicked.connect(self._on_main_cell_clicked)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        bottom.addWidget(self.status_label)
        bottom.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)
        self._refresh_date_label()

    def open_import_history_dialog(self):
        dialog = PromotionImportHistoryDialog(self.store_id, self.store_name, self.db, self.main_app, self)
        dialog.exec_()
        self.load_current_date()

    def _refresh_date_label(self):
        qdate = self.date_edit.date()
        self.date_label.setText(_weekday_text(qdate))

    def _select_single_date(self):
        self._refresh_date_label()
        if not hasattr(self, "range_start_edit"):
            return
        self.range_start_edit.setDate(self.date_edit.date())
        self.range_end_edit.setDate(self.date_edit.date())
        self.load_current_date()

    def _selected_range(self):
        return self.range_start_edit.date(), self.range_end_edit.date()

    def _apply_selected_range(self):
        start, end = self._selected_range()
        if start > end:
            QMessageBox.warning(self, "日期范围错误", "开始日期不能晚于结束日期。")
            return
        self.load_current_date()

    def _set_quick_range(self, mode):
        today = QDate.currentDate()
        latest = None
        if mode == "this_week":
            monday = today.addDays(1 - today.dayOfWeek())
            rows = self.db.safe_fetchall(
                "SELECT MAX(record_date) FROM promotion_daily_data WHERE store_id=? AND record_date BETWEEN ? AND ?",
                (self.store_id, monday.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")),
            )
            if rows and rows[0][0]:
                latest = QDate.fromString(str(rows[0][0]), "yyyy-MM-dd")
        start, end = _promotion_quick_range(today, mode, latest)
        self.range_start_edit.setDate(start)
        self.range_end_edit.setDate(end)
        self.load_current_date()

    def _shift_date(self, days):
        self.date_edit.setDate(self.date_edit.date().addDays(days))

    def _record_date(self):
        return self.date_edit.date().toString("yyyy-MM-dd")

    def _store_products(self):
        rows = self.db.safe_fetchall("SELECT id, name, title, COALESCE(is_natural_flow, 0) FROM products WHERE store_id=?", (self.store_id,))
        return {
            str(name or "").strip(): {"sys_id": sys_id, "title": title or "", "is_natural_flow": bool(is_natural_flow)}
            for sys_id, name, title, is_natural_flow in rows
        }

    def _calculate_promotion_profit_snapshot(self, product_sys_id, net_amount, cost):
        return self.db.calculate_promotion_profit_snapshot(product_sys_id, net_amount, cost)

    def _auto_detect_columns(self, headers):
        patterns = {
            "product_id": ["商品id", "商品id链接id", "链接id", "productid", "goodsid", "商品编号"],
            "product_title": ["商品标题", "商品名称", "商品名", "标题", "名称"],
            "cost": ["推广成交花费", "成交花费元", "成交花费", "花费", "消耗"],
            "transaction_amount": ["交易额元", "交易额", "成交金额"],
            "roi": ["实际投产比", "投产比", "roi"],
            "net_transaction_amount": ["净交易额元", "净交易额"],
            "net_roi": ["净实际投产比", "净投产比", "净roi"],
            "net_orders": ["净成交笔数", "净成交订单", "净成交"],
            "cost_per_net_order": ["每笔净成交花费元", "每笔净成交花费", "每单花费"],
            "impressions": ["曝光量", "总曝光"],
            "clicks": ["点击量", "点击数"],
            "promotion_impressions": ["推广曝光量", "推广曝光"],
            "ctr": ["点击率"],
            "click_conversion_rate": ["点击转化率", "转化率"],
            "settlement_coupon_cost": ["结算券花费元", "结算券花费", "结算券消耗"],
        }
        normalized = [_normalize_header(h) for h in headers]
        exact_headers = {
            "net_transaction_amount": "净交易额元",
            "settlement_coupon_cost": "结算券花费元",
        }
        mapping = {}
        for key, keys in patterns.items():
            mapping[key] = None
            if key in exact_headers:
                mapping[key] = next((idx for idx, header in enumerate(normalized) if header == exact_headers[key]), None)
                continue
            if key == "cost":
                for idx, header in enumerate(normalized):
                    if "推广成交花费" in header and "结算券" not in header:
                        mapping[key] = idx
                        break
                if mapping[key] is not None:
                    continue
            for idx, header in enumerate(normalized):
                raw_header = str(headers[idx])
                if key in ("transaction_amount", "roi") and "净" in raw_header:
                    continue
                if key == "cost" and ("每笔" in raw_header or "净" in raw_header or "结算券" in raw_header):
                    continue
                if any(pattern in header for pattern in keys):
                    if key == "impressions" and "推广" in raw_header:
                        continue
                    mapping[key] = idx
                    break
        return mapping

    def _read_file(self, file_path):
        if pd is None:
            raise RuntimeError("未检测到 pandas 库，无法导入 Excel/CSV。")
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            try:
                return pd.read_csv(file_path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                return pd.read_csv(file_path, encoding="gbk")
        if ext == ".xlsx":
            return pd.read_excel(file_path, engine="openpyxl")
        if ext == ".xls":
            try:
                import xlrd  # noqa: F401
            except ImportError as exc:
                raise RuntimeError("读取 .xls 老格式文件需要安装 xlrd，请先安装依赖后重试。") from exc
            try:
                return pd.read_excel(file_path, engine="xlrd")
            except ImportError as exc:
                raise RuntimeError("读取 .xls 老格式文件需要安装 xlrd，请先安装依赖后重试。") from exc
        return pd.read_excel(file_path)

    def import_promotion_data(self):
        file_path, _ = remembered_open_file(
            self, self.db, "选择推广数据文件", "Excel/CSV文件 (*.xlsx *.xls *.csv)"
        )
        if not file_path:
            return
        try:
            df = self._read_file(file_path)
            headers = list(df.columns)
            dialog = PromotionColumnMappingDialog(headers, self._auto_detect_columns(headers), self)
            if dialog.exec_() != QDialog.Accepted:
                return
            mapping = dialog.mapping()
            deduct_settlement_coupon = dialog.deduct_settlement_coupon()
            if mapping.get("product_id") is None:
                QMessageBox.warning(self, "缺少列映射", "必须选择商品ID列。")
                return
            record_date = self._record_date()
            exists = self.db.safe_fetchall(
                "SELECT COUNT(*) FROM promotion_daily_data WHERE store_id=? AND record_date=?",
                (self.store_id, record_date)
            )
            if exists and int(exists[0][0] or 0) > 0:
                reply = QMessageBox.question(
                    self, "覆盖确认",
                    f"{record_date} 已导入过推广数据。\n本次导入会整体覆盖该日期数据，是否继续？"
                )
                if reply != QMessageBox.Yes:
                    return

            product_map = self._store_products()
            rows_to_insert = []
            skipped = 0
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for _idx, row in df.iterrows():
                product_id = str(row.iloc[mapping["product_id"]] if mapping.get("product_id") is not None else "").strip()
                if not product_id or product_id not in product_map:
                    skipped += 1
                    continue
                item = {
                    "store_id": self.store_id,
                    "record_date": record_date,
                    "product_id": product_id,
                    "product_title": (
                        str(row.iloc[mapping["product_title"]]).strip()
                        if mapping.get("product_title") is not None
                        else product_map.get(product_id, {}).get("title", "")
                    ),
                    "bid_method": "",
                    "imported_at": now,
                }
                for key in NUMERIC_COLUMNS:
                    if key in ("cpc", "promotion_impression_share"):
                        continue
                    col = mapping.get(key)
                    item[key] = _parse_number(row.iloc[col]) if col is not None else 0.0
                if deduct_settlement_coupon and mapping.get("settlement_coupon_cost") is not None:
                    source_net_amount = item.get("net_transaction_amount", 0.0)
                    settlement_coupon_cost = _parse_number(row.iloc[mapping["settlement_coupon_cost"]])
                    item["net_transaction_amount"] = source_net_amount - settlement_coupon_cost
                    item["net_roi"] = item["net_transaction_amount"] / item.get("cost", 0.0) if item.get("cost", 0.0) else 0.0
                clicks = item.get("clicks", 0.0)
                cost = item.get("cost", 0.0)
                impressions = item.get("impressions", 0.0)
                promo_impressions = item.get("promotion_impressions", 0.0)
                item["cpc"] = cost / clicks if clicks else 0.0
                item["promotion_impression_share"] = promo_impressions / impressions if impressions else 0.0
                product_sys_id = product_map.get(product_id, {}).get("sys_id")
                net_profit, net_margin_rate = self._calculate_promotion_profit_snapshot(
                    product_sys_id,
                    item.get("net_transaction_amount", 0),
                    item.get("cost", 0),
                )
                item["net_profit"] = net_profit
                item["net_margin_rate"] = net_margin_rate
                rows_to_insert.append(item)

            with self.db.conn:
                self.db.conn.execute(
                    "DELETE FROM promotion_daily_data WHERE store_id=? AND record_date=?",
                    (self.store_id, record_date)
                )
                self.db.conn.executemany("""
                    INSERT OR REPLACE INTO promotion_daily_data
                    (store_id, record_date, product_id, product_title, bid_method, cost, transaction_amount, roi,
                     net_transaction_amount, net_roi, net_orders, net_profit, net_margin_rate, cost_per_net_order, cpc, impressions,
                     clicks, promotion_impressions, promotion_impression_share, ctr, click_conversion_rate, imported_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [(
                    item["store_id"], item["record_date"], item["product_id"], item.get("product_title", ""), item["bid_method"],
                    item.get("cost", 0), item.get("transaction_amount", 0), item.get("roi", 0),
                    item.get("net_transaction_amount", 0), item.get("net_roi", 0), item.get("net_orders", 0),
                    item.get("net_profit"), item.get("net_margin_rate"),
                    item.get("cost_per_net_order", 0), item.get("cpc", 0), item.get("impressions", 0),
                    item.get("clicks", 0), item.get("promotion_impressions", 0),
                    item.get("promotion_impression_share", 0), item.get("ctr", 0),
                    item.get("click_conversion_rate", 0), item["imported_at"],
                ) for item in rows_to_insert])
            recovered_waste_ids = sorted({
                product_map[str(item.get("product_id") or "")]["sys_id"]
                for item in rows_to_insert
                if float(item.get("net_orders") or 0) > 0
                and str(item.get("product_id") or "") in product_map
            })
            if recovered_waste_ids:
                placeholders = ",".join("?" for _ in recovered_waste_ids)
                self.db.safe_execute(
                    f"""UPDATE daily_tasks SET is_completed=1
                        WHERE store_id=? AND is_completed=0
                          AND task_content LIKE '【废物链接】%'
                          AND product_id IN ({placeholders})""",
                    (self.store_id, *recovered_waste_ids),
                )
            garbage_count = self.db.reconcile_garbage_link_tasks(self.store_id, now)
            if self.main_app and hasattr(self.main_app, "autosave_current_archive"):
                saved, error = self.main_app.autosave_current_archive()
                if not saved:
                    raise RuntimeError(f"推广数据已写入当前数据库，但自动保存本地存档失败：{error}")
            self.load_current_date()
            if self.main_app and hasattr(self.main_app, "force_refresh_frozen_table"):
                self.main_app.force_refresh_frozen_table(self.store_id)
            if self.main_app and hasattr(self.main_app, "update_daily_task_button_badge"):
                self.main_app.update_daily_task_button_badge()
            QMessageBox.information(self, "导入完成", f"已导入 {len(rows_to_insert)} 条。\n跳过非当前店铺链接 {skipped} 条。")
            if garbage_count and self.main_app and hasattr(self.main_app, "show_toast"):
                self.main_app.show_toast(f"已标记 {garbage_count} 个垃圾链接")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _fetch_current_rows(self):
        start, end = self._selected_range()
        return self.db.safe_fetchall("""
            WITH totals AS (
                SELECT product_id, MAX(product_title) AS product_title, MAX(bid_method) AS bid_method,
                       SUM(cost) AS cost, SUM(transaction_amount) AS transaction_amount,
                       SUM(net_transaction_amount) AS net_transaction_amount, SUM(net_orders) AS net_orders,
                       SUM(impressions) AS impressions, SUM(clicks) AS clicks,
                       SUM(promotion_impressions) AS promotion_impressions,
                       SUM(net_profit) AS net_profit, COUNT(net_profit) AS profit_count, COUNT(*) AS row_count
                FROM promotion_daily_data
                WHERE store_id=? AND record_date BETWEEN ? AND ?
                  AND EXISTS (
                      SELECT 1 FROM products active_product
                      WHERE active_product.store_id=promotion_daily_data.store_id
                        AND active_product.name=promotion_daily_data.product_id
                        AND COALESCE(active_product.is_archived, 0)=0
                        AND COALESCE(active_product.is_violation, 0)=0
                  )
                GROUP BY product_id
            )
            SELECT totals.product_id, COALESCE(NULLIF(totals.product_title, ''), p.title), p.image_data,
                   totals.bid_method, totals.cost, totals.transaction_amount,
                   CASE WHEN totals.cost<>0 THEN totals.transaction_amount/totals.cost ELSE 0 END,
                   totals.net_transaction_amount,
                   CASE WHEN totals.cost<>0 THEN totals.net_transaction_amount/totals.cost ELSE 0 END,
                   totals.net_orders,
                   CASE WHEN totals.net_orders<>0 THEN totals.cost/totals.net_orders ELSE 0 END,
                   CASE WHEN totals.clicks<>0 THEN totals.cost/totals.clicks ELSE 0 END,
                   totals.impressions, totals.clicks, totals.promotion_impressions,
                   CASE WHEN totals.impressions<>0 THEN totals.promotion_impressions/totals.impressions ELSE 0 END,
                   CASE WHEN totals.impressions<>0 THEN totals.clicks/totals.impressions ELSE 0 END,
                   CASE WHEN totals.clicks<>0 THEN totals.net_orders/totals.clicks ELSE 0 END,
                   CASE WHEN totals.profit_count=totals.row_count THEN totals.net_profit END,
                   CASE WHEN totals.profit_count=totals.row_count AND totals.net_transaction_amount<>0
                        THEN totals.net_profit/totals.net_transaction_amount*100 END
            FROM totals
            LEFT JOIN products p ON p.store_id=? AND p.name=totals.product_id
              AND COALESCE(p.is_archived, 0)=0 AND COALESCE(p.is_violation, 0)=0
            ORDER BY p.sort_order, totals.product_id
        """, (
            self.store_id,
            start.toString("yyyy-MM-dd"),
            end.toString("yyyy-MM-dd"),
            self.store_id,
        ))

    def _row_to_data(self, row):
        return {
            "product_id": row[0],
            "product_title": row[1] or "",
            "image_data": row[2],
            "bid_method": row[3],
            "cost": row[4],
            "transaction_amount": row[5],
            "roi": row[6],
            "net_transaction_amount": row[7],
            "net_roi": row[8],
            "net_orders": row[9],
            "cost_per_net_order": row[10],
            "cpc": row[11],
            "impressions": row[12],
            "clicks": row[13],
            "promotion_impressions": row[14],
            "promotion_impression_share": row[15],
            "ctr": row[16],
            "click_conversion_rate": row[17],
            "net_profit": row[18],
            "net_margin_rate": row[19],
            "_is_summary": False,
        }

    def _summary_row_data(self, rows):
        if not rows:
            return None

        def total(key):
            return sum(float(row.get(key) or 0) for row in rows)

        cost = total("cost")
        transaction_amount = total("transaction_amount")
        net_amount = total("net_transaction_amount")
        net_orders = total("net_orders")
        impressions = total("impressions")
        clicks = total("clicks")
        promotion_impressions = total("promotion_impressions")
        net_profit_values = [row.get("net_profit") for row in rows]
        net_profit = sum(float(value or 0) for value in net_profit_values) if all(value is not None for value in net_profit_values) else None
        return {
            "product_id": "全部总和",
            "product_title": f"共 {len(rows)} 条链接",
            "image_data": None,
            "bid_method": "汇总",
            "cost": cost,
            "transaction_amount": transaction_amount,
            "roi": transaction_amount / cost if cost else 0.0,
            "net_transaction_amount": net_amount,
            "net_roi": net_amount / cost if cost else 0.0,
            "net_orders": net_orders,
            "cost_per_net_order": cost / net_orders if net_orders else 0.0,
            "cpc": cost / clicks if clicks else 0.0,
            "impressions": impressions,
            "clicks": clicks,
            "promotion_impressions": promotion_impressions,
            "promotion_impression_share": promotion_impressions / impressions if impressions else 0.0,
            "ctr": clicks / impressions if impressions else 0.0,
            "click_conversion_rate": net_orders / clicks if clicks else 0.0,
            "net_profit": net_profit,
            "net_margin_rate": (net_profit / net_amount * 100) if net_profit is not None and net_amount else None,
            "_is_summary": True,
        }

    def _set_image_cell(self, row_idx, image_data):
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(78, 78)
        label.setStyleSheet("background: #fafafa; border: none;")
        if image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(bytes(image_data))
            if not pixmap.isNull():
                scaled = pixmap.scaled(78, 78, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x = max(0, (scaled.width() - 78) // 2)
                y = max(0, (scaled.height() - 78) // 2)
                label.setPixmap(scaled.copy(x, y, 78, 78))
            else:
                label.setText("图片失败")
        else:
            label.setText("无图")
        layout.addWidget(label)
        self.table.setCellWidget(row_idx, 0, cell)

    def _clear_main_table_body(self):
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, col)
                if widget is not None:
                    self.table.removeCellWidget(row, col)
                    widget.deleteLater()
        for widget in self.table.viewport().findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            widget.setParent(None)
            widget.deleteLater()
        self.table.clearContents()
        self.table.setRowCount(0)

    def load_current_date(self):
        if not hasattr(self, "table"):
            return
        start, end = self._selected_range()
        if start > end:
            return
        self.table.setSortingEnabled(False)
        self._clear_main_table_body()
        self._apply_main_table_columns()
        db_rows = self._fetch_current_rows()
        data_rows = [self._row_to_data(row) for row in db_rows]
        summary = self._summary_row_data(data_rows)
        display_rows = ([summary] if summary else []) + data_rows
        self.table.setRowCount(len(display_rows))
        for row_idx, data in enumerate(display_rows):
            title = data.get("product_title") or ""
            is_summary = bool(data.get("_is_summary"))
            self._set_image_cell(row_idx, data.get("image_data"))
            for col_idx, key in enumerate(self.column_order):
                value = data.get(key, "")
                if key in ("net_profit", "net_margin_rate") and value is None:
                    text = "--"
                elif key in ("cost", "transaction_amount", "net_transaction_amount", "cost_per_net_order", "cpc", "net_profit"):
                    text = _fmt_money(value)
                elif key == "net_margin_rate":
                    text = f"{float(value or 0):.2f}%"
                elif key in ("promotion_impression_share", "ctr", "click_conversion_rate"):
                    text = _fmt_ratio(value)
                elif key in ("roi", "net_roi"):
                    text = f"{float(value or 0):.2f}"
                elif key in ("impressions", "clicks", "promotion_impressions", "net_orders"):
                    text = _fmt_number(value, 0)
                else:
                    text = str(value or "")
                sort_value = value if value is not None and (key in NUMERIC_COLUMNS or key in ("cpc", "promotion_impression_share")) else None
                item = NumericTableWidgetItem(text, sort_value, is_summary)
                item.setTextAlignment(Qt.AlignCenter)
                if is_summary:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QColor("#eef6ea"))
                if key in ("net_profit", "net_margin_rate") and value is not None:
                    item.setForeground(QColor("#1b8f3a" if float(value or 0) >= 0 else "#c0392b"))
                if key == "product_id" and not is_summary:
                    font = item.font()
                    font.setPointSize(max(8, font.pointSize() - 10))
                    item.setFont(font)
                if key == "product_id" and title:
                    item.setToolTip(title)
                if key == "product_title" and not is_summary:
                    font = item.font()
                    font.setPointSize(max(8, font.pointSize() - 20))
                    item.setFont(font)
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if key == "product_title" and is_summary:
                    item.setTextAlignment(Qt.AlignCenter)
                if key == "bid_method" and not is_summary:
                    font = item.font()
                    font.setPointSize(max(8, font.pointSize() - 30))
                    item.setFont(font)
                self.table.setItem(row_idx, col_idx + 1, item)
            if is_summary:
                summary_item = QTableWidgetItem("汇总")
                summary_item.setTextAlignment(Qt.AlignCenter)
                summary_item.setBackground(QColor("#eef6ea"))
                self.table.setItem(row_idx, len(self.column_order) + 1, summary_item)
            else:
                btn = QPushButton("单链接\n历史")
                btn.setStyleSheet("QPushButton { font-size: 11px; padding: 2px; }")
                btn.clicked.connect(lambda _=False, pid=data.get("product_id"), title=title: self.open_product_history(pid, title))
                self.table.setCellWidget(row_idx, len(self.column_order) + 1, btn)
            self.table.setRowHeight(row_idx, 78)
        counts = self.db.safe_fetchall(
            "SELECT COUNT(DISTINCT record_date), COUNT(*) FROM promotion_daily_data "
            "WHERE store_id=? AND record_date BETWEEN ? AND ?",
            (self.store_id, start.toString("yyyy-MM-dd"), end.toString("yyyy-MM-dd")),
        )
        day_count, record_count = counts[0] if counts else (0, 0)
        range_text = start.toString("yyyy-MM-dd") if start == end else f"{start.toString('yyyy-MM-dd')} 至 {end.toString('yyyy-MM-dd')}"
        self.status_label.setText(
            f"{range_text}｜{day_count or 0} 天｜{len(db_rows)} 个链接｜{record_count or 0} 条数据"
        )
        self._resize_main_table_columns()
        QTimer.singleShot(0, self._resize_main_table_columns)
        self._apply_saved_main_sort()

    def open_product_history(self, product_id, product_title=""):
        dialog = ProductPromotionHistoryDialog(self.store_id, self.store_name, product_id, product_title, self.db, self)
        dialog.exec_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "table"):
            QTimer.singleShot(0, self._resize_main_table_columns)


class PromotionImportHistoryDialog(QDialog):
    def __init__(self, store_id, store_name, db, main_app=None, parent=None):
        super().__init__(parent)
        apply_window_icon(self, "promotion")
        self.store_id = store_id
        self.store_name = store_name
        self.db = db
        self.main_app = main_app
        self.setWindowTitle(f"推广导入历史 - {store_name}")
        self.resize(980, 560)
        self._build_ui()
        self.load_rows()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tip = QLabel("按导入日期汇总展示。删除会整体删除该日期下当前店铺的全部推广数据。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #666;")
        layout.addWidget(tip)

        self.table = QTableWidget()
        self._headers = [
            "导入日期", "周几", "链接数", "成交花费", "净交易额", "净成交笔数", "净利润", "净利率", "导入时间", "操作"
        ]
        self.table.setColumnCount(len(self._headers))
        self.table.setHorizontalHeaderLabels(self._headers)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        _apply_plain_table_focus_style(self.table)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _query_summary(self):
        return self.db.safe_fetchall("""
            SELECT record_date, COUNT(*) AS product_count,
                   COALESCE(SUM(cost), 0), COALESCE(SUM(net_transaction_amount), 0), COALESCE(SUM(net_orders), 0),
                   SUM(net_profit), COUNT(net_profit), MAX(imported_at)
            FROM promotion_daily_data
            WHERE store_id=? AND EXISTS (
                SELECT 1 FROM products p
                WHERE p.store_id=promotion_daily_data.store_id
                  AND p.name=promotion_daily_data.product_id
                  AND COALESCE(p.is_archived, 0)=0 AND COALESCE(p.is_violation, 0)=0
            )
            GROUP BY record_date
            ORDER BY record_date DESC
        """, (self.store_id,))

    def load_rows(self):
        self.table.setSortingEnabled(False)
        rows = self._query_summary()
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            record_date, product_count, cost, net_amount, net_orders, net_profit, profit_count, imported_at = row
            complete_profit = int(profit_count or 0) == int(product_count or 0)
            net_margin_rate = (float(net_profit or 0) / float(net_amount or 0) * 100) if complete_profit and net_amount else None
            weekday = ""
            try:
                dt = datetime.strptime(str(record_date), "%Y-%m-%d")
                weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
            except Exception:
                pass
            values = [
                record_date,
                weekday,
                str(int(product_count or 0)),
                _fmt_money(cost),
                _fmt_money(net_amount),
                _fmt_number(net_orders, 0),
                "--" if not complete_profit else _fmt_money(net_profit),
                "--" if net_margin_rate is None else f"{net_margin_rate:.2f}%",
                imported_at or "",
            ]
            sort_values = [
                record_date, None, product_count or 0, cost or 0, net_amount or 0, net_orders or 0,
                None if not complete_profit else net_profit or 0,
                net_margin_rate,
                imported_at or "",
            ]
            for col, value in enumerate(values):
                item = NumericTableWidgetItem(str(value), sort_values[col])
                item.setTextAlignment(Qt.AlignCenter)
                if col in (6, 7) and complete_profit:
                    compare_value = net_profit if col == 6 else net_margin_rate
                    if compare_value is not None:
                        item.setForeground(QColor("#1b8f3a" if float(compare_value or 0) >= 0 else "#c0392b"))
                self.table.setItem(row_idx, col, item)
            btn_delete = QPushButton("删除")
            btn_delete.setStyleSheet("QPushButton { color: #c0392b; font-weight: bold; }")
            btn_delete.clicked.connect(lambda _=False, date=record_date: self.delete_date(date))
            self.table.setCellWidget(row_idx, len(self._headers) - 1, btn_delete)
            self.table.setRowHeight(row_idx, 42)
        _resize_table_columns_by_values(
            self.table,
            fixed_widths={len(self._headers) - 1: 48},
            default_min=34,
            default_max=120,
            fill_viewport=True,
        )
        _wrap_table_headers(self.table, self._headers)
        QTimer.singleShot(0, self._resize_columns)
        self.table.setSortingEnabled(True)

    def _resize_columns(self):
        if not hasattr(self, "table"):
            return
        _resize_table_columns_by_values(
            self.table,
            fixed_widths={len(self._headers) - 1: 48},
            default_min=34,
            default_max=120,
            fill_viewport=True,
        )
        _wrap_table_headers(self.table, self._headers)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_columns)

    def delete_date(self, record_date):
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除 {record_date} 的全部推广数据吗？\n此操作会删除当前店铺该日期所有链接的数据。"
        )
        if reply != QMessageBox.Yes:
            return
        self.db.safe_execute(
            "DELETE FROM promotion_daily_data WHERE store_id=? AND record_date=?",
            (self.store_id, record_date)
        )
        self.load_rows()
        parent = self.parent()
        if parent and hasattr(parent, "load_current_date"):
            parent.load_current_date()
        if self.main_app and hasattr(self.main_app, "force_refresh_frozen_table"):
            self.main_app.force_refresh_frozen_table(self.store_id)


class ProductPromotionHistoryDialog(QDialog):
    def __init__(self, store_id, store_name, product_id, product_title, db, parent=None):
        super().__init__(parent)
        apply_window_icon(self, "promotion")
        self.store_id = store_id
        self.store_name = store_name
        self.product_id = str(product_id)
        self.product_title = product_title or ""
        self.db = db
        self._ui_ready = False
        self.setWindowTitle(f"推广历史 - {self.product_id}")
        self.resize(1280, 720)
        self._all_rows = []
        self._build_ui()
        self._ui_ready = True
        self.load_rows()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel(f"{self.store_name} / {self.product_id} {self.product_title}")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        top = QHBoxLayout()
        self.filter_enabled = QPushButton("日期筛选")
        self.filter_enabled.setCheckable(True)
        self.filter_enabled.clicked.connect(lambda _checked=False: self.load_rows())
        self.start_date = QDateEdit()
        self.end_date = QDateEdit()
        for edit in (self.start_date, self.end_date):
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setCalendarPopup(True)
        yesterday = QDate.currentDate().addDays(-1)
        self.start_date.setDate(yesterday.addDays(-6))
        self.end_date.setDate(yesterday)
        top.addWidget(self.filter_enabled)
        top.addWidget(QLabel("开始"))
        top.addWidget(self.start_date)
        top.addWidget(QLabel("结束"))
        top.addWidget(self.end_date)
        for text, days in (("近30天", 30), ("近7天", 7), ("近3天", 3), ("昨日", 1)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, d=days: self._set_quick_range(d))
            top.addWidget(btn)
        btn_ai = QPushButton("AI生成总结")
        btn_ai.clicked.connect(self.generate_ai_summary)
        top.addWidget(btn_ai)
        top.addStretch()
        layout.addLayout(top)

        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(78)
        self.summary_text.setStyleSheet("""
            QPlainTextEdit {
                background: #f8fafc;
                border: 1px solid #d7dee8;
                border-radius: 4px;
                padding: 6px;
                color: #1f2937;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.summary_text)

        self.table = QTableWidget()
        history_labels = [label for key, label in HISTORY_PROMOTION_COLUMNS if key not in ("product_id", "product_title")]
        self._db_header_keys = ["record_date"] + [key for key, _label in PROMOTION_COLUMNS if key not in ("product_id", "product_title")]
        self._header_keys = ["record_date"] + [key for key, _label in HISTORY_PROMOTION_COLUMNS if key not in ("product_id", "product_title")]
        self._header_labels = ["日期"] + history_labels
        self.table.setColumnCount(len(history_labels) + 1)
        self.table.setHorizontalHeaderLabels(self._header_labels)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setCornerButtonEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setWordWrap(True)
        self.table.setItemDelegate(PromotionCompareDelegate(self.table))
        _apply_plain_table_focus_style(self.table)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        self.start_date.dateChanged.connect(lambda _date: self.load_rows())
        self.end_date.dateChanged.connect(lambda _date: self.load_rows())

        bottom = QHBoxLayout()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom.addStretch()
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def _set_quick_range(self, days):
        yesterday = QDate.currentDate().addDays(-1)
        self.filter_enabled.setChecked(True)
        self.start_date.setDate(yesterday.addDays(-(days - 1)))
        self.end_date.setDate(yesterday)
        self.load_rows()

    def _query_rows(self):
        params = [self.store_id, self.product_id]
        sql = """
            SELECT record_date, bid_method, cost, transaction_amount, roi, net_transaction_amount,
                   net_roi, net_orders, net_profit, net_margin_rate, cost_per_net_order, cpc, impressions, clicks,
                   promotion_impressions, promotion_impression_share, ctr, click_conversion_rate
            FROM promotion_daily_data
            WHERE store_id=? AND product_id=?
        """
        if self.filter_enabled.isChecked():
            sql += " AND record_date>=? AND record_date<=?"
            params.extend([self.start_date.date().toString("yyyy-MM-dd"), self.end_date.date().toString("yyyy-MM-dd")])
        sql += " ORDER BY record_date ASC"
        return self.db.safe_fetchall(sql, tuple(params))

    def _compare_text(self, key, current, previous):
        if previous is None:
            return ""
        if key in ("net_profit", "net_margin_rate") and current is None:
            return ""
        try:
            current = float(current or 0)
            previous = float(previous or 0)
        except Exception:
            return ""
        diff = current - previous
        if abs(diff) < 0.000001:
            return "→ 0"
        icon = "↑" if diff > 0 else "↓"
        if previous:
            text = f"{icon} {abs(diff / abs(previous) * 100):.1f}%"
        else:
            text = f"{icon} {_fmt_number(abs(diff))}"
        return text

    def _format_history_cell(self, key, value, previous):
        base, compare = self._format_history_cell_parts(key, value, previous)
        return f"{base}\n{compare}" if compare else base

    def _format_history_cell_parts(self, key, value, previous):
        if key in ("net_profit", "net_margin_rate") and value is None:
            base = "--"
        elif key in ("cost", "transaction_amount", "net_transaction_amount", "cost_per_net_order", "net_amount_per_order", "cpc", "net_profit"):
            base = _fmt_money(value)
        elif key == "net_margin_rate":
            base = f"{float(value or 0):.2f}%"
        elif key in ("promotion_impression_share", "ctr", "click_conversion_rate"):
            base = _fmt_ratio(value)
        elif key in ("roi", "net_roi"):
            base = f"{float(value or 0):.2f}"
        elif key in ("impressions", "clicks", "promotion_impressions", "net_orders"):
            base = _fmt_number(value, 0)
        else:
            base = str(value or "")
        compare = self._compare_text(key, value, previous) if key in CORE_COMPARE_COLUMNS else ""
        return base, compare

    def _compare_color(self, key, current, previous):
        if key not in CORE_COMPARE_COLUMNS or previous is None:
            return None
        if key in ("net_profit", "net_margin_rate") and current is None:
            return None
        try:
            current = float(current or 0)
            previous = float(previous or 0)
        except Exception:
            return None
        diff = current - previous
        if abs(diff) < 0.000001:
            return "#6b7280"
        improved = diff > 0
        if key in LOWER_IS_BETTER:
            improved = not improved
        return "#1b8f3a" if improved else "#c0392b"

    def _update_summary_text(self, row_maps):
        if not hasattr(self, "summary_text"):
            return
        if not row_maps:
            self.summary_text.setPlainText("当前筛选范围没有推广数据。")
            return
        cost = sum(float(row.get("cost") or 0) for row in row_maps)
        amount = sum(float(row.get("transaction_amount") or 0) for row in row_maps)
        net_amount = sum(float(row.get("net_transaction_amount") or 0) for row in row_maps)
        net_orders = sum(float(row.get("net_orders") or 0) for row in row_maps)
        profit_values = [float(row.get("net_profit") or 0) for row in row_maps if row.get("net_profit") is not None]
        net_profit = sum(profit_values) if len(profit_values) == len(row_maps) else None
        net_margin_rate = (net_profit / net_amount * 100) if net_profit is not None and net_amount else None
        impressions = sum(float(row.get("impressions") or 0) for row in row_maps)
        clicks = sum(float(row.get("clicks") or 0) for row in row_maps)
        promo_impressions = sum(float(row.get("promotion_impressions") or 0) for row in row_maps)
        roi = amount / cost if cost else 0
        net_roi = net_amount / cost if cost else 0
        cost_per_net_order = cost / net_orders if net_orders else 0
        net_amount_per_order = net_amount / net_orders if net_orders else 0
        cpc = cost / clicks if clicks else 0
        promo_share = promo_impressions / impressions if impressions else 0
        ctr = clicks / impressions if impressions else 0
        click_conversion = net_orders / clicks if clicks else 0
        dates = [str(row.get("record_date") or "") for row in row_maps if row.get("record_date")]
        date_text = f"{min(dates)} ~ {max(dates)}" if dates else "当前筛选"
        parts = [
            f"当前筛选汇总：{date_text}，共 {len(row_maps)} 天",
            f"成交花费 {_fmt_money(cost)}",
            f"交易额 {_fmt_money(amount)}",
            f"实际投产比 {roi:.2f}",
            f"净交易额 {_fmt_money(net_amount)}",
            f"净实际投产比 {net_roi:.2f}",
            f"净成交笔数 {_fmt_number(net_orders, 0)}",
            f"净利润 {('--' if net_profit is None else _fmt_money(net_profit))}",
            f"净利率 {('--' if net_margin_rate is None else f'{net_margin_rate:.2f}%')}",
            f"每笔净成交花费 {_fmt_money(cost_per_net_order)}",
            f"每笔净成交金额 {_fmt_money(net_amount_per_order)}",
            f"曝光量 {_fmt_number(impressions, 0)}",
            f"点击量 {_fmt_number(clicks, 0)}",
            f"CPC {_fmt_money(cpc)}",
            f"推广曝光量 {_fmt_number(promo_impressions, 0)}",
            f"推广曝光占比 {_fmt_ratio(promo_share)}",
            f"点击率 {_fmt_ratio(ctr)}",
            f"点击转化率 {_fmt_ratio(click_conversion)}",
        ]
        self.summary_text.setPlainText("；".join(parts))

    def load_rows(self):
        if not getattr(self, "_ui_ready", False) or not hasattr(self, "table"):
            return
        self.table.setSortingEnabled(False)
        rows = self._query_rows()
        self._all_rows = rows
        self.table.setRowCount(len(rows))
        previous_by_key = {}
        summary_rows = []
        for row_idx, row in enumerate(rows):
            row_map = dict(zip(self._db_header_keys, row))
            net_orders = float(row_map.get("net_orders") or 0)
            net_amount = float(row_map.get("net_transaction_amount") or 0)
            row_map["net_amount_per_order"] = net_amount / net_orders if net_orders else 0.0
            summary_rows.append(dict(row_map))
            for col_idx, key in enumerate(self._header_keys):
                text = row_map.get(key, "")
                base_text = None
                compare_text = ""
                compare_color = None
                if key != "record_date":
                    base_text, compare_text = self._format_history_cell_parts(key, text, previous_by_key.get(key))
                    text = f"{base_text}\n{compare_text}" if compare_text else base_text
                    compare_color = self._compare_color(key, row_map.get(key), previous_by_key.get(key))
                sort_value = row_map.get(key) if key != "record_date" else row_map.get(key)
                if key in ("net_profit", "net_margin_rate") and row_map.get(key) is None:
                    sort_value = None
                item = NumericTableWidgetItem(str(text), sort_value if key == "record_date" or key in HISTORY_NUMERIC_COLUMNS or key in ("cpc", "promotion_impression_share") else None)
                item.setTextAlignment(Qt.AlignCenter)
                if key in ("net_profit", "net_margin_rate") and row_map.get(key) is not None:
                    item.setForeground(QColor("#1b8f3a" if float(row_map.get(key) or 0) >= 0 else "#c0392b"))
                if compare_text:
                    item.setData(COMPARE_BASE_ROLE, base_text)
                    item.setData(COMPARE_TEXT_ROLE, compare_text)
                    item.setData(COMPARE_COLOR_ROLE, compare_color or "#6b7280")
                self.table.setItem(row_idx, col_idx, item)
            for key in self._header_keys:
                if key != "record_date":
                    previous_by_key[key] = row_map.get(key)
            self.table.setRowHeight(row_idx, 52)
        self._update_summary_text(summary_rows)
        _resize_table_columns_by_values(
            self.table,
            column_keys=self._header_keys,
            default_min=34,
            default_max=110,
            fill_viewport=True,
        )
        _wrap_table_headers(self.table, self._header_labels)
        QTimer.singleShot(0, self._resize_columns)
        self.table.setSortingEnabled(True)

    def _resize_columns(self):
        if not hasattr(self, "table"):
            return
        _resize_table_columns_by_values(
            self.table,
            column_keys=self._header_keys,
            default_min=34,
            default_max=110,
            fill_viewport=True,
        )
        _wrap_table_headers(self.table, self._header_labels)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_columns)

    def _ai_context_rows(self):
        headers = ["日期"] + [label for key, label in HISTORY_PROMOTION_COLUMNS if key not in ("product_id", "product_title")]
        result = []
        for row in range(self.table.rowCount()):
            item = {}
            for col in range(self.table.columnCount()):
                header = headers[col] if col < len(headers) else str(col)
                cell = self.table.item(row, col)
                item[header] = cell.text() if cell else ""
            result.append(item)
        return result

    def generate_ai_summary(self):
        api_key = self.db.get_setting("ai_api_key", "")
        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        if not api_key:
            QMessageBox.warning(self, "提示", "请先在 AI API 配置中填写 API Key。")
            return
        rows = self._ai_context_rows()
        if not rows:
            QMessageBox.information(self, "提示", "当前筛选范围没有推广数据。")
            return
        prompt = {
            "任务": "生成单链接推广数据文字总结",
            "要求": [
                "只基于提供的数据总结，不编造未提供信息。",
                "不要 Markdown、不要表格、不要代码块。",
                "用自然段和简单序号说明趋势、异常、花费效率、转化变化和下步动作。",
            ],
            "店铺": self.store_name,
            "商品ID": self.product_id,
            "商品标题": self.product_title,
            "筛选数据": rows,
        }
        progress = QProgressDialog("正在调用 AI 生成总结...", "取消", 0, 0, self)
        progress.setWindowTitle("AI处理中")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()
        try:
            import requests
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是电商推广数据分析助手，输出简洁、直接、可转发的中文文字总结。"},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, indent=2)},
                ],
                "temperature": 0.35,
                "max_tokens": 2048,
            }
            response = requests.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
            progress.close()
            if response.status_code != 200:
                QMessageBox.warning(self, "AI调用失败", f"状态码：{response.status_code}\n{response.text[:500]}")
                return
            content = response.json()["choices"][0]["message"]["content"].strip()
            self._show_ai_result(content)
        except Exception as e:
            progress.close()
            QMessageBox.warning(self, "AI调用失败", str(e))

    def _show_ai_result(self, content):
        dialog = QDialog(self)
        dialog.setWindowTitle("AI推广总结")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setPlainText(content)
        text.setReadOnly(True)
        layout.addWidget(text)
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("复制")
        btn_close = QPushButton("关闭")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(text.toPlainText()))
        btn_close.clicked.connect(dialog.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
        dialog.exec_()

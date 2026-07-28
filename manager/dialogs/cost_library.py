# -*- coding: utf-8 -*-
"""成本库管理对话框"""
import csv
import hashlib
import io
import json
import os
import re
import time
from datetime import datetime, timedelta

from PyQt5.QtCore import QByteArray, QBuffer, QEvent, QEasingCurve, QIODevice, QItemSelectionModel, QPoint, QSize, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QBrush, QColor, QCursor, QFontMetrics, QIcon, QKeySequence, QPainter, QPen, QPixmap, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QProgressDialog,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStyledItemDelegate,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

try:
    from PyQt5 import sip
except ImportError:
    import sip

try:
    from ..window_icons import apply_window_icon
except ImportError:
    from window_icons import apply_window_icon

try:
    from ..pinyin_search import any_terms_match, match_score, split_search_terms, text_matches
except ImportError:
    from pinyin_search import any_terms_match, match_score, split_search_terms, text_matches


class SelectAllLineEditDelegate(QStyledItemDelegate):
    """Line edit delegate that selects all text whenever editing starts."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        self.active_editor = editor
        editor.setAlignment(Qt.AlignCenter)
        QTimer.singleShot(0, editor.selectAll)
        return editor

    def setEditorData(self, editor, index):
        editor.setText(str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or ""))
        QTimer.singleShot(0, editor.selectAll)


class MultiLineTextEditDelegate(QStyledItemDelegate):
    """Use wrapped text editing for table cells that may display wrapped text."""

    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        self.active_editor = editor
        editor.setAcceptRichText(False)
        editor.setLineWrapMode(QTextEdit.WidgetWidth)
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        editor.setPlainText(str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or ""))
        QTimer.singleShot(0, editor.selectAll)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText().strip(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def eventFilter(self, editor, event):
        if isinstance(editor, QTextEdit):
            if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ControlModifier:
                    self.commitData.emit(editor)
                    self.closeEditor.emit(editor)
                    return True
        return super().eventFilter(editor, event)


class SpecNameBadgeDelegate(MultiLineTextEditDelegate):
    """Draw a small single/combined badge in the bottom-right of spec names."""

    COMBO_STATE_ROLE = Qt.UserRole + 101

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        text = str(index.data(Qt.DisplayRole) or "")
        combo_state = index.data(self.COMBO_STATE_ROLE)
        is_combo = bool(combo_state) if combo_state is not None else bool(re.search(r"\+|＋|﹢", text))
        label = "组合" if is_combo else "单品"
        bg_color = QColor("#fff2cc" if is_combo else "#eaf8ee")
        border_color = QColor("#d6a400" if is_combo else "#5aa469")
        text_color = QColor("#7a4f00" if is_combo else "#1f6f3d")

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = option.font
        font.setPointSize(max(7, font.pointSize() - 2))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        badge_width = metrics.horizontalAdvance(label) + 8
        badge_height = 14
        x = option.rect.right() - badge_width - 3
        y = option.rect.bottom() - badge_height - 3
        badge_rect = option.rect.__class__(x, y, badge_width, badge_height)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(badge_rect, 5, 5)
        painter.setPen(text_color)
        painter.drawText(badge_rect, Qt.AlignCenter, label)
        painter.restore()


class FixedHeightWrapDelegate(QStyledItemDelegate):
    """Allow wrapped painting while keeping the column from changing row height."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(32)
        return size


def _extract_ai_json_or_text(raw_text):
    text = str(raw_text or "").strip()
    text = re.sub(r"^```(?:json|text)?\s*|\s*```$", "", text, flags=re.I).strip()
    if not text:
        return {}, ""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidate = text[start:end + 1]
        for fixed in (candidate, candidate.replace("'", '"')):
            try:
                data = json.loads(fixed)
                if isinstance(data, dict):
                    return data, text
            except Exception:
                pass
    return {}, text


def _clean_ai_short_value(raw_text, field_name, existing_options=None, max_chars=18):
    existing_options = [str(item or "").strip() for item in (existing_options or []) if str(item or "").strip()]
    data, text = _extract_ai_json_or_text(raw_text)
    value = str(data.get(field_name) or data.get("name") or data.get("link_type") or "").strip()

    if not value and existing_options:
        for option in existing_options:
            if option and option in text:
                return option

    if not value:
        patterns = [
            rf'"?{re.escape(field_name)}"?\s*[:：]\s*["“]?([^"”\n,，}}]+)',
            r"(?:组合名称|链接组合名称|名称)\s*[:：]\s*([^。\n，,]+)",
            r"(?:链接类型|类型)\s*[:：]\s*([^。\n，,]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                value = match.group(1).strip()
                break

    if not value:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        short_lines = [
            line.strip("-* 0123456789.、：:")
            for line in lines
            if not line.startswith(("我们", "根据", "以下", "说明", "分析", "推荐", "因为"))
        ]
        value = (short_lines[-1] if short_lines else (lines[-1] if lines else text)).strip()

    value = re.sub(r"^(?:最终)?(?:组合名称|链接组合名称|链接类型|类型|名称)\s*[:：]\s*", "", value).strip()
    value = re.split(r"[。；;\n\r]", value)[0].strip()
    value = value.strip("\"'“”‘’` ，,。")
    if existing_options:
        for option in existing_options:
            if option == value or (option and option in value):
                return option
    return value[:max_chars].strip()


class CostHistoryDialog(QDialog):
    """独立的成本库操作日志窗口。"""

    COL_IMAGE = 0
    COL_DATE = 1
    COL_NAME = 2
    COL_CODE = 3
    COL_OPERATION = 4
    COL_OLD = 5
    COL_NEW = 6
    COL_SOURCE = 7
    ROW_SIZE = 76
    OPERATIONS = (
        ("product_cost", "产品成本"),
        ("code", "规格编码"),
        ("name", "名称"),
        ("attribute", "产品属性"),
        ("image", "图片"),
        ("category", "商品类型"),
        ("quantity", "数量"),
        ("weight", "重量"),
    )

    def __init__(self, db_manager, cost_library=None, main_window=None):
        super().__init__(None)
        apply_window_icon(self, "cost")
        self.db = db_manager
        self.cost_library = cost_library
        self.main_window = main_window
        self._filter_ready = False
        self._history_signature = None
        self.setWindowTitle("历史操作")
        self.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
        )
        self.resize(1360, 760)
        self.init_ui()
        self.load_data()
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(700)
        self.poll_timer.timeout.connect(self._poll_changes)
        self.poll_timer.start()
        QTimer.singleShot(0, self._center_on_screen)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("搜索商品名称/规格编码:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品名称或规格编码...")
        self.search_input.textChanged.connect(self.load_data)
        filter_layout.addWidget(self.search_input, 1)

        filter_layout.addWidget(QLabel("时间:"))
        self.time_filter = QComboBox()
        self.time_filter.addItem("今天", "today")
        self.time_filter.addItem("近三天（不含今天）", "last3")
        self.time_filter.addItem("近七天（不含今天）", "last7")
        self.time_filter.addItem("全部时间", "all")
        saved_time = self.db.get_setting("cost_history_time_filter", "today")
        saved_index = self.time_filter.findData(saved_time)
        self.time_filter.setCurrentIndex(max(saved_index, 0))
        self.time_filter.currentIndexChanged.connect(self._time_filter_changed)
        filter_layout.addWidget(self.time_filter)

        self.operation_button = QPushButton()
        self.operation_menu = QMenu(self)
        self.operation_list = QListWidget()
        self.operation_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.operation_list.setMinimumWidth(180)
        self.operation_list.setMaximumHeight(250)
        for key, label in self.OPERATIONS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.operation_list.addItem(item)
        operation_filter_widget = QWidget()
        operation_filter_layout = QVBoxLayout(operation_filter_widget)
        operation_filter_layout.setContentsMargins(6, 6, 6, 6)
        operation_filter_layout.setSpacing(4)
        operation_actions = QHBoxLayout()
        self.operation_select_all_button = QPushButton("全选")
        self.operation_invert_button = QPushButton("反选")
        self.operation_select_all_button.clicked.connect(self._select_all_operations)
        self.operation_invert_button.clicked.connect(self._invert_operations)
        operation_actions.addWidget(self.operation_select_all_button)
        operation_actions.addWidget(self.operation_invert_button)
        operation_filter_layout.addLayout(operation_actions)
        operation_filter_layout.addWidget(self.operation_list)
        action = QWidgetAction(self.operation_menu)
        action.setDefaultWidget(operation_filter_widget)
        self.operation_menu.addAction(action)
        self.operation_button.clicked.connect(self._show_operation_menu)
        self.operation_list.itemSelectionChanged.connect(self._operation_filter_changed)
        filter_layout.addWidget(self.operation_button)

        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.load_data)
        filter_layout.addWidget(btn_refresh)
        layout.addLayout(filter_layout)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([
            "图片", "日期", "商品名称", "规格编码", "操作", "修改前", "修改后", "来源"
        ])
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.setIconSize(QSize(68, 68))
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setWordWrap(True)
        self.table_view.setTextElideMode(Qt.ElideNone)
        self.table_view.clicked.connect(self.copy_spec_code)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table_view.setColumnWidth(self.COL_IMAGE, self.ROW_SIZE)
        self.table_view.setColumnWidth(self.COL_DATE, 105)
        self.table_view.setColumnWidth(self.COL_NAME, 300)
        self.table_view.setColumnWidth(self.COL_CODE, 175)
        self.table_view.setColumnWidth(self.COL_OPERATION, 100)
        self.table_view.setColumnWidth(self.COL_OLD, 250)
        self.table_view.setColumnWidth(self.COL_NEW, 250)
        self.table_view.setColumnWidth(self.COL_SOURCE, 80)
        vertical = self.table_view.verticalHeader()
        vertical.setSectionResizeMode(QHeaderView.Fixed)
        vertical.setDefaultSectionSize(self.ROW_SIZE)
        vertical.setMinimumSectionSize(self.ROW_SIZE)
        layout.addWidget(self.table_view, 1)

        btn_layout = QHBoxLayout()
        self.lbl_count = QLabel("共 0 条操作")
        btn_delete = QPushButton("删除选中")
        btn_delete.clicked.connect(self.delete_selected)
        btn_clear = QPushButton("清空历史操作")
        btn_clear.setStyleSheet("color: #b42318;")
        btn_clear.clicked.connect(self.clear_all)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_clear)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        self._restore_operation_filter()
        self._filter_ready = True

    def _center_on_screen(self):
        screen = QApplication.desktop().availableGeometry(self.cost_library or self)
        self.move(screen.center() - self.rect().center())

    def _restore_operation_filter(self):
        raw = self.db.get_setting("cost_history_operation_filters", "")
        try:
            selected = set(json.loads(raw)) if raw else {key for key, _label in self.OPERATIONS}
        except (TypeError, ValueError, json.JSONDecodeError):
            selected = {key for key, _label in self.OPERATIONS}
        if "price" in selected:
            selected.discard("price")
            selected.add("product_cost")
        if selected == {key for key, _label in self.OPERATIONS if key != "code"}:
            selected.add("code")
        self.operation_list.blockSignals(True)
        for row in range(self.operation_list.count()):
            item = self.operation_list.item(row)
            item.setSelected(item.data(Qt.UserRole) in selected)
        self.operation_list.blockSignals(False)
        self._update_operation_button()

    def _selected_operations(self):
        return [str(item.data(Qt.UserRole)) for item in self.operation_list.selectedItems()]

    def _update_operation_button(self):
        selected = self.operation_list.selectedItems()
        if len(selected) == self.operation_list.count():
            text = "操作筛选：全部"
        elif not selected:
            text = "操作筛选：未选择"
        elif len(selected) <= 2:
            text = "操作筛选：" + "、".join(item.text() for item in selected)
        else:
            text = f"操作筛选：已选 {len(selected)} 项"
        self.operation_button.setText(text)

    def _show_operation_menu(self):
        self.operation_menu.popup(self.operation_button.mapToGlobal(QPoint(0, self.operation_button.height())))

    def _select_all_operations(self):
        self.operation_list.blockSignals(True)
        for row in range(self.operation_list.count()):
            self.operation_list.item(row).setSelected(True)
        self.operation_list.blockSignals(False)
        self._operation_filter_changed()

    def _invert_operations(self):
        self.operation_list.blockSignals(True)
        for row in range(self.operation_list.count()):
            item = self.operation_list.item(row)
            item.setSelected(not item.isSelected())
        self.operation_list.blockSignals(False)
        self._operation_filter_changed()

    def _operation_filter_changed(self):
        self._update_operation_button()
        if not self._filter_ready:
            return
        self.db.set_setting(
            "cost_history_operation_filters",
            json.dumps(self._selected_operations(), ensure_ascii=False),
        )
        self.load_data()

    def _time_filter_changed(self):
        if not self._filter_ready:
            return
        self.db.set_setting("cost_history_time_filter", self.time_filter.currentData() or "today")
        self.load_data()

    def _time_bounds(self):
        mode = self.time_filter.currentData() or "today"
        if mode == "all":
            return None
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days = {"today": 0, "last3": 3, "last7": 7}.get(mode, 0)
        start = today if mode == "today" else today - timedelta(days=days)
        end = today + timedelta(days=1) if mode == "today" else today
        return int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    @staticmethod
    def _format_history_date(value):
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").strftime("%m月%d日\n%H:%M")
        except ValueError:
            return text

    @staticmethod
    def _format_number(value):
        if value in (None, ""):
            return ""
        try:
            return f"{float(value):.4f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(value)

    def _operation_display(self, operation_type, old_value, new_value):
        if operation_type == "product_cost":
            try:
                old_number = float(old_value)
                new_number = float(new_value)
                label = (
                    "产品成本上涨" if new_number > old_number
                    else "产品成本下降" if new_number < old_number
                    else "调整产品成本"
                )
            except (TypeError, ValueError):
                label = "调整产品成本"
            return label, self._format_number(old_value), self._format_number(new_value)
        labels = {
            "code": "修改编码",
            "name": "修改名称",
            "attribute": "修改属性",
            "image": "更换图片",
            "category": "修改类型",
            "quantity": "修改数量",
            "weight": "修改重量",
        }
        return labels.get(operation_type, operation_type or "操作"), str(old_value or ""), str(new_value or "")

    def _query_rows(self):
        where = []
        params = []
        bounds = self._time_bounds()
        if bounds:
            where.append("COALESCE(h.event_time_ms, 0)>=? AND COALESCE(h.event_time_ms, 0)<?")
            params.extend(bounds)
        operations = self._selected_operations()
        if not operations:
            return []
        placeholders = ",".join("?" for _ in operations)
        where.append(f"COALESCE(h.operation_type, 'price') IN ({placeholders})")
        params.extend(operations)
        where.append(
            "(COALESCE(h.operation_type, 'price')<>'product_cost' "
            "OR COALESCE(cl.product_attribute_is_combo, 0)=0)"
        )
        query = f"""SELECT h.event_id, h.import_time,
                            COALESCE(NULLIF(h.spec_name, ''), cl.spec_name, '') AS spec_name,
                            h.spec_code, COALESCE(h.operation_type, 'price'),
                            COALESCE(h.old_value, CAST(h.old_cost_price AS TEXT), ''),
                            COALESCE(h.new_value, CAST(h.new_cost_price AS TEXT), ''),
                            h.source
                     FROM cost_history h
                     LEFT JOIN cost_library cl ON cl.spec_code=h.spec_code
                     WHERE {' AND '.join(where)}
                     ORDER BY COALESCE(h.event_time_ms, 0) DESC, h.id DESC"""
        return self.db.safe_fetchall(query, tuple(params))

    def _load_thumbnail_icons(self, spec_codes):
        icons = {}
        codes = list(dict.fromkeys(str(code or "") for code in spec_codes if str(code or "")))
        for start in range(0, len(codes), 800):
            batch = codes[start:start + 800]
            placeholders = ",".join("?" for _ in batch)
            for spec_code, image_data in self.db.safe_fetchall(
                f"""SELECT spec_code, thumbnail_data FROM cost_library
                    WHERE spec_code IN ({placeholders})
                      AND LENGTH(COALESCE(thumbnail_data, X''))>0""",
                tuple(batch),
            ):
                pixmap = QPixmap()
                if pixmap.loadFromData(bytes(image_data or b"")):
                    icons[str(spec_code)] = QIcon(
                        pixmap.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
        return icons

    def load_data(self):
        if not hasattr(self, "model") or not self._filter_ready:
            return
        keyword = self.search_input.text().strip()
        terms = split_search_terms(keyword)
        rows = [
            row for row in self._query_rows()
            if not terms or any_terms_match(terms, row[2], row[3])
        ]
        icons = self._load_thumbnail_icons(row[3] for row in rows)
        self.model.setRowCount(len(rows))
        for row, (event_id, import_time, spec_name, spec_code, operation_type, old_value, new_value, source) in enumerate(rows):
            operation, old_display, new_display = self._operation_display(operation_type, old_value, new_value)
            image_item = QStandardItem()
            icon = icons.get(str(spec_code or ""))
            if icon is not None:
                image_item.setIcon(icon)
            image_item.setData(str(event_id or ""), Qt.UserRole)
            self.model.setItem(row, self.COL_IMAGE, image_item)
            values = (
                self._format_history_date(import_time), str(spec_name or ""), str(spec_code or ""),
                operation, old_display, new_display,
                {
                    "manual": "手动", "import": "导入", "lan": "局域网",
                    "combo": "组合计算", "undo": "撤销", "redo": "恢复",
                }.get(source, str(source or "")),
            )
            for offset, value in enumerate(values, start=1):
                item = QStandardItem(value)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                item.setSizeHint(QSize(-1, self.ROW_SIZE))
                self.model.setItem(row, offset, item)
            self.table_view.setRowHeight(row, self.ROW_SIZE)
        self.lbl_count.setText(f"共 {self.model.rowCount()} 条操作")
        self._resize_columns_to_contents()
        self._history_signature = self._read_signature()

    def _resize_columns_to_contents(self):
        self.table_view.resizeColumnsToContents()
        limits = {
            self.COL_IMAGE: (self.ROW_SIZE, self.ROW_SIZE),
            self.COL_DATE: (90, 120),
            self.COL_NAME: (180, 360),
            self.COL_CODE: (120, 220),
            self.COL_OPERATION: (90, 140),
            self.COL_OLD: (120, 320),
            self.COL_NEW: (120, 320),
            self.COL_SOURCE: (70, 100),
        }
        for column, (minimum, maximum) in limits.items():
            width = self.table_view.columnWidth(column)
            self.table_view.setColumnWidth(column, max(minimum, min(width, maximum)))

    def _read_signature(self):
        rows = self.db.safe_fetchall(
            "SELECT COUNT(*), COALESCE(MAX(event_time_ms), 0) FROM cost_history"
        )
        clear_at = self.db.get_setting("cost_history_clear_at", "0")
        return (rows[0][0], rows[0][1], str(clear_at)) if rows else (0, 0, str(clear_at))

    def _poll_changes(self):
        signature = self._read_signature()
        if signature != self._history_signature:
            self.load_data()

    def copy_spec_code(self, index):
        if not index.isValid() or index.column() != self.COL_CODE:
            return
        spec_code = self.model.item(index.row(), self.COL_CODE).text().strip()
        if spec_code:
            QApplication.clipboard().setText(spec_code)
            self._show_hint("已复制")

    def _show_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        quick_search = menu.addAction("在成本库快速搜索")
        if menu.exec_(self.table_view.viewport().mapToGlobal(pos)) == quick_search:
            self._quick_search(index.row())

    def _quick_search(self, row):
        spec_code = self.model.item(row, self.COL_CODE).text().strip()
        current = self.db.safe_fetchall(
            """SELECT COALESCE(spec_name, ''), COALESCE(product_attribute_is_combo, 0)
               FROM cost_library WHERE spec_code=?""",
            (spec_code,),
        )
        if not current or int(current[0][1] or 0):
            QMessageBox.information(self, "提示", "快速搜索只用于当前成本库里的单品规格。")
            return
        exact_name = str(current[0][0] or "").strip()
        if not exact_name:
            return
        library = self.cost_library
        if library is None or sip.isdeleted(library):
            if self.main_window and hasattr(self.main_window, "show_cost_library"):
                self.main_window.show_cost_library()
                library = getattr(self.main_window, "cost_library_dialog", None)
        if library is None or sip.isdeleted(library):
            return
        if library.isMinimized():
            library.showNormal()
        else:
            library.show()
        library.raise_()
        library.activateWindow()
        library.search_input.setText(exact_name)
        library.search_input.setFocus(Qt.ShortcutFocusReason)
        library.search_input.selectAll()

    def _show_hint(self, text):
        if self.main_window and hasattr(self.main_window, "show_toast"):
            self.main_window.show_toast(text, 1000)
        else:
            QToolTip.showText(QCursor.pos(), text, self, self.rect(), 1000)

    def delete_selected(self):
        rows = sorted({index.row() for index in self.table_view.selectionModel().selectedRows()})
        if not rows:
            QMessageBox.warning(self, "提示", "请先选中要删除的操作记录。")
            return
        if QMessageBox.question(
            self, "确认删除", f"确定删除选中的 {len(rows)} 条操作记录吗？\n当前成本库不会被修改。",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        event_ids = [self.model.item(row, self.COL_IMAGE).data(Qt.UserRole) for row in rows]
        count = self.db.delete_cost_history_events(event_ids)
        self.load_data()
        self._show_hint(f"已删除 {count} 条操作记录")

    def clear_all(self):
        if QMessageBox.question(
            self, "清空历史操作", "确定清空全部历史操作吗？\n不会修改当前成本库，此操作会同步到局域网组织。",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        count = self.db.clear_cost_history()
        self.load_data()
        self._show_hint(f"已清空 {count} 条操作记录")


class AIPickDialog(QDialog):
    """AI选品对话框。"""

    def __init__(self, db_manager, main_window=None, parent=None):
        super().__init__(parent)
        apply_window_icon(self, "cost")
        self.db = db_manager
        self.main_window = main_window
        self.cost_rows = []
        self.result_rows = []
        self.setWindowTitle("AI选品")
        self.resize(980, 760)
        self.init_ui()
        self.load_cost_rows()
        self.load_stores()

    def init_ui(self):
        layout = QVBoxLayout(self)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("关键词:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入商品名称关键词，筛选目标产品...")
        self.keyword_input.textChanged.connect(self.search_targets)
        self.keyword_input.returnPressed.connect(self.search_targets)
        btn_search = QPushButton("搜索")
        btn_search.clicked.connect(self.search_targets)
        btn_ai = QPushButton("AI选品")
        btn_ai.setStyleSheet("background-color: #6f42c1; color: white; font-weight: bold;")
        btn_ai.clicked.connect(self.run_ai_pick)
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(btn_search)
        search_layout.addWidget(btn_ai)
        layout.addLayout(search_layout)

        layout.addWidget(QLabel("目标产品（勾选后作为搭配参考）:"))
        self.target_model = QStandardItemModel()
        self.target_model.setHorizontalHeaderLabels(["选择", "商品名称", "数量"])
        self.target_table = QTableView()
        self.target_table.setModel(self.target_model)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.target_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.target_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.target_table.setColumnWidth(0, 54)
        self.target_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.target_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.target_table, 2)

        layout.addWidget(QLabel("AI推荐搭配商品（可取消勾选）:"))
        self.result_model = QStandardItemModel()
        self.result_model.setHorizontalHeaderLabels(["选择", "商品名称", "数量", "推荐理由"])
        self.result_table = QTableView()
        self.result_table.setModel(self.result_model)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.result_table.setColumnWidth(0, 54)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.result_table, 3)

        create_layout = QHBoxLayout()
        self.chk_create_link = QCheckBox("新建链接")
        self.chk_create_link.setChecked(True)
        create_layout.addWidget(self.chk_create_link)
        create_layout.addWidget(QLabel("店铺:"))
        self.store_combo = QComboBox()
        self.store_combo.setMinimumWidth(180)
        create_layout.addWidget(self.store_combo)
        create_layout.addWidget(QLabel("标题:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("AI选品-关键词")
        create_layout.addWidget(self.title_input)
        layout.addLayout(create_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_create = QPushButton("创建链接")
        btn_create.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_create.clicked.connect(self.create_link)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def load_cost_rows(self):
        rows = self.db.safe_fetchall(
            """SELECT spec_name, spec_code, quantity
               FROM cost_library
               WHERE COALESCE(spec_name, '') <> ''
               ORDER BY CASE WHEN sort_order IS NULL THEN 1 ELSE 0 END, sort_order, spec_code"""
        )
        self.cost_rows = [
            {
                "row_index": idx + 1,
                "name": str(name or ""),
                "spec_code": str(code or ""),
                "quantity": self._format_quantity(quantity),
            }
            for idx, (name, code, quantity) in enumerate(rows)
        ]

    def load_stores(self):
        self.store_combo.clear()
        stores = self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order, id")
        for store_id, store_name in stores:
            self.store_combo.addItem(str(store_name or f"店铺{store_id}"), store_id)

        default_store_id = self._default_store_id()
        if default_store_id is not None:
            index = self.store_combo.findData(default_store_id)
            if index >= 0:
                self.store_combo.setCurrentIndex(index)

    def _default_store_id(self):
        if not self.main_window:
            return None
        try:
            selected_rows = self.main_window.table.selectionModel().selectedRows()
            if selected_rows:
                row = selected_rows[0].row()
                prod_id = self.main_window.row_data_map.get(row)
                if prod_id:
                    return self.main_window.product_store_map.get(prod_id)
                return self.main_window.row_store_map.get(row)
        except Exception:
            pass
        try:
            stores = self.db.safe_fetchall("SELECT id FROM stores ORDER BY sort_order, id LIMIT 1")
            return stores[0][0] if stores else None
        except Exception:
            return None

    def search_targets(self):
        keyword = self.keyword_input.text().strip().lower()
        self.target_model.setRowCount(0)
        if not keyword:
            return

        matches = self._filter_cost_rows_by_name(keyword)

        for row_data in matches:
            row = self.target_model.rowCount()
            self.target_model.insertRow(row)
            check_item = QStandardItem("")
            check_item.setCheckable(True)
            check_item.setCheckState(Qt.Unchecked)
            check_item.setEditable(False)
            check_item.setData(row_data["row_index"], Qt.UserRole)
            self.target_model.setItem(row, 0, check_item)
            self._set_readonly_item(self.target_model, row, 1, row_data["name"])
            self._set_readonly_item(self.target_model, row, 2, row_data["quantity"])
        if not self.title_input.text().strip():
            self.title_input.setText(f"AI选品-{self.keyword_input.text().strip()}")

    def _format_quantity(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return ""
        numeric_text = text.replace(",", "")
        try:
            number = float(numeric_text)
        except ValueError:
            return text
        if number.is_integer():
            return str(int(number))
        return str(int(round(number)))

    def _split_search_terms(self, search_text):
        return split_search_terms(search_text)

    def _filter_cost_rows_by_name(self, search_text):
        search_text = search_text.strip().lower()
        terms = self._split_search_terms(search_text)
        if not terms:
            return []

        matched = []
        for row in self.cost_rows:
            full_hit, hit_count = match_score(search_text, terms, row["name"])
            if hit_count <= 0:
                continue
            matched.append((full_hit, hit_count, row["row_index"], row))
        matched.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [item[3] for item in matched]

    def _set_readonly_item(self, model, row, col, text):
        item = QStandardItem(str(text or ""))
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        model.setItem(row, col, item)

    def selected_targets(self):
        targets = []
        for row in range(self.target_model.rowCount()):
            check_item = self.target_model.item(row, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                row_index = check_item.data(Qt.UserRole)
                name_item = self.target_model.item(row, 1)
                if row_index:
                    targets.append({"row_index": int(row_index), "name": name_item.text() if name_item else ""})
        return targets

    def _extract_json_text(self, text):
        text = str(text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            return text[start:end + 1]
        return text

    def _parse_ai_pick_result(self, text):
        json_text = self._extract_json_text(text)
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            normalized = json_text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
            normalized = re.sub(r"row[\s_\-]*index\*?", "row_index", normalized, flags=re.I)
            normalized = re.sub(r"'([^']*)'", r'"\1"', normalized)
            normalized = re.sub(r"(?<=[\[,])\s*\(", "{", normalized)
            normalized = re.sub(r"\)\s*(?=[,\]])", "}", normalized)
            try:
                data = json.loads(normalized)
            except json.JSONDecodeError:
                data = []
                for part in re.findall(r"\{[^{}]*\}", normalized):
                    row_match = re.search(r'"?row_index"?\s*[:：]\s*"?(\d+)"?', part, flags=re.I)
                    reason_match = re.search(r'"?(?:reason|理由)"?\s*[:：]\s*["\']?([^,"\'}\]\)]+)', part, flags=re.I)
                    relevance_match = re.search(r'"?(?:relevance|score|相关度)"?\s*[:：]\s*"?(\d+(?:\.\d+)?)"?', part, flags=re.I)
                    if row_match:
                        data.append({
                            "row_index": int(row_match.group(1)),
                            "reason": reason_match.group(1).strip() if reason_match else "",
                            "relevance": float(relevance_match.group(1)) if relevance_match else None,
                        })

        if isinstance(data, dict):
            data = data.get("items") or data.get("results") or [data]

        result = []
        for order, item in enumerate(data if isinstance(data, list) else []):
            if not isinstance(item, dict):
                continue
            row_index = item.get("row_index", item.get("index", item.get("序号")))
            reason = str(item.get("reason") or item.get("理由") or item.get("match_reason") or "").strip()
            relevance = item.get("relevance", item.get("score", item.get("相关度")))
            try:
                relevance = float(relevance)
            except (TypeError, ValueError):
                relevance = None
            try:
                result.append((int(row_index), reason[:80], relevance, order))
            except (TypeError, ValueError):
                continue
        return result

    def _build_ai_pick_prompt(self, targets):
        items = [{"row_index": row["row_index"], "name": row["name"]} for row in self.cost_rows]
        return (
            "你是电商搭配选品助手。只根据商品名称判断哪些商品适合与目标商品一起搭配销售。"
            "请结合完整候选商品名称列表识别同类、同款、同场景商品，再推荐最相关的搭配商品。"
            "不要推荐目标商品本身。最多返回 10 个推荐商品名称组。"
            "只返回标准 JSON 数组，字段为 row_index、reason、relevance。"
            "relevance 是 0 到 100 的相关度分数，越相关分数越高。"
            "示例：[{\"row_index\":2,\"reason\":\"同场景搭配\",\"relevance\":92}]。\n"
            f"目标商品名称：{json.dumps([t['name'] for t in targets], ensure_ascii=False)}\n"
            f"候选商品名称列表：{json.dumps(items, ensure_ascii=False)}"
        )

    def _product_name_key(self, name):
        return str(name or "").strip().lower()

    def _base_product_key(self, name):
        text = str(name or "").strip().lower()
        if not text:
            return ""
        normalized = re.sub(r"[（(【\[].*?[）)】\]]", "", text)
        normalized = re.sub(r"\d+(?:\.\d+)?\s*(?:本|个|件|装|套|包|组|盒|箱|支|份|册)", "", normalized)
        normalized = re.sub(r"(?:本|个|件|装|套|包|组|盒|箱|支|份|册)\s*\d+(?:\.\d+)?", "", normalized)
        normalized = re.sub(r"\d+(?:\.\d+)?", "", normalized)
        normalized = re.sub(r"(?:本|个|件|装|套|包|组|盒|箱|支|份|册)", "", normalized)
        normalized = re.sub(r"[\\/\-_\s,，.。:：;；+＋|、]+", "", normalized)
        normalized = normalized.strip()
        if len(normalized) < 2:
            return self._product_name_key(name)
        return normalized

    def _build_name_groups(self):
        groups = {}
        for row in self.cost_rows:
            key = self._product_name_key(row["name"])
            if not key:
                continue
            groups.setdefault(key, []).append(row)
        return groups

    def _build_base_name_groups(self):
        groups = {}
        for row in self.cost_rows:
            key = self._base_product_key(row["name"])
            if not key:
                continue
            groups.setdefault(key, []).append(row)
        return groups

    def _append_product_group(self, result_rows, seen_codes, groups, name_key, reason):
        for row_data in groups.get(name_key, []):
            spec_code = row_data["spec_code"]
            if spec_code in seen_codes:
                continue
            seen_codes.add(spec_code)
            result_rows.append({**row_data, "reason": reason})

    def _append_base_product_group(self, result_rows, seen_codes, base_groups, base_key, selected_codes=None):
        selected_codes = selected_codes or set()
        for row_data in base_groups.get(base_key, []):
            spec_code = row_data["spec_code"]
            if spec_code in seen_codes:
                continue
            seen_codes.add(spec_code)
            reason = "目标产品" if spec_code in selected_codes else "同款规格"
            result_rows.append({**row_data, "reason": reason})

    def run_ai_pick(self):
        api_key = self.db.get_setting("ai_api_key", "")
        if not api_key:
            QMessageBox.warning(self, "提示", "请先在 AI API 配置中填写 API Key。")
            return
        targets = self.selected_targets()
        if not targets:
            QMessageBox.warning(self, "提示", "请先勾选目标产品。")
            return
        if not self.cost_rows:
            QMessageBox.warning(self, "提示", "成本库没有可选商品。")
            return

        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "只输出严格 JSON 数组，不要解释，不要 markdown。"},
                {"role": "user", "content": self._build_ai_pick_prompt(targets)},
            ],
            "temperature": 0.35,
            "max_tokens": 4096,
        }

        progress = QProgressDialog("正在调用 AI 选品...", "取消", 0, 2, self)
        progress.setWindowTitle("AI选品")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            import requests

            response = None
            for attempt in range(3):
                if progress.wasCanceled():
                    return
                response = requests.post(api_url, headers=headers, json=data, timeout=90)
                if response.status_code not in (500, 503):
                    break
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
            if response is None:
                raise RuntimeError("AI 请求没有返回结果")
            if response.status_code != 200:
                raise RuntimeError(f"AI 请求失败：HTTP {response.status_code}\n{response.text[:300]}")

            progress.setLabelText("正在解析 AI 推荐结果...")
            progress.setValue(1)
            QApplication.processEvents()
            response_data = response.json()
            content = response_data["choices"][0]["message"].get("content", "")
            if not str(content or "").strip():
                raise RuntimeError(f"AI 返回内容为空。\nAPI URL：{api_url}\n模型：{model}\n返回内容：{str(response_data)[:500]}")
            picks = self._parse_ai_pick_result(content)
            if not picks:
                raise RuntimeError(f"AI 没有返回可识别的推荐结果。\n返回内容：{str(content)[:500]}")
        except Exception as e:
            QMessageBox.critical(self, "AI选品失败", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()

        row_map = {row["row_index"]: row for row in self.cost_rows}
        base_groups = self._build_base_name_groups()
        self.result_rows = []
        seen_codes = set()
        target_base_keys = []
        selected_target_codes = set()
        for target in targets:
            row_data = row_map.get(target["row_index"])
            if not row_data:
                continue
            selected_target_codes.add(row_data["spec_code"])
            base_key = self._base_product_key(row_data["name"])
            if base_key not in target_base_keys:
                target_base_keys.append(base_key)
        for base_key in target_base_keys:
            self._append_base_product_group(
                self.result_rows,
                seen_codes,
                base_groups,
                base_key,
                selected_target_codes,
            )

        recommended_groups = {}
        for row_index, reason, relevance, order in picks:
            row_data = row_map.get(row_index)
            if not row_data:
                continue
            base_key = self._base_product_key(row_data["name"])
            if not base_key or base_key in target_base_keys:
                continue
            current = recommended_groups.get(base_key)
            candidate = {
                "base_key": base_key,
                "reason": reason,
                "relevance": relevance,
                "order": order,
            }
            if current is None:
                recommended_groups[base_key] = candidate
                continue
            current_score = current["relevance"] if current["relevance"] is not None else -current["order"]
            candidate_score = relevance if relevance is not None else -order
            if candidate_score > current_score or (candidate_score == current_score and order < current["order"]):
                recommended_groups[base_key] = candidate

        sorted_groups = sorted(
            recommended_groups.values(),
            key=lambda item: (-(item["relevance"] if item["relevance"] is not None else -item["order"]), item["order"]),
        )
        for group in sorted_groups[:10]:
            self._append_product_group(self.result_rows, seen_codes, base_groups, group["base_key"], group["reason"])
        self.load_results()

    def load_results(self):
        self.result_model.setRowCount(0)
        for row_data in self.result_rows:
            row = self.result_model.rowCount()
            self.result_model.insertRow(row)
            check_item = QStandardItem("")
            check_item.setCheckable(True)
            check_item.setCheckState(Qt.Unchecked)
            check_item.setEditable(False)
            check_item.setData(row_data["row_index"], Qt.UserRole)
            self.result_model.setItem(row, 0, check_item)
            self._set_readonly_item(self.result_model, row, 1, row_data["name"])
            self._set_readonly_item(self.result_model, row, 2, row_data["quantity"])
            self._set_readonly_item(self.result_model, row, 3, row_data.get("reason", ""))
        if not self.result_rows:
            QMessageBox.information(self, "提示", "AI 没有推荐可用搭配商品。")

    def selected_results(self):
        selected = []
        row_map = {row["row_index"]: row for row in self.result_rows}
        for row in range(self.result_model.rowCount()):
            check_item = self.result_model.item(row, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                row_data = row_map.get(check_item.data(Qt.UserRole))
                if row_data:
                    selected.append(row_data)
        return selected

    def _unique_product_id(self):
        base = datetime.now().strftime("AI_PICK_%Y%m%d_%H%M%S")
        product_id = base
        suffix = 1
        while self.db.safe_fetchall("SELECT id FROM products WHERE name=?", (product_id,)):
            suffix += 1
            product_id = f"{base}_{suffix}"
        return product_id

    def create_link(self):
        if not self.chk_create_link.isChecked():
            QMessageBox.information(self, "提示", "未勾选新建链接，当前只展示 AI 推荐结果。")
            return
        store_id = self.store_combo.currentData()
        if store_id is None:
            QMessageBox.warning(self, "提示", "请先创建店铺。")
            return
        specs = self.selected_results()
        if not specs:
            QMessageBox.warning(self, "提示", "请先勾选要写入链接的推荐商品。")
            return

        product_id = self._unique_product_id()
        title = self.title_input.text().strip() or f"AI选品-{self.keyword_input.text().strip() or product_id}"
        try:
            self.db.conn.execute("BEGIN TRANSACTION")
            max_order_rows = self.db.cursor.execute("SELECT MAX(sort_order) FROM products WHERE store_id=?", (store_id,)).fetchall()
            max_order = max_order_rows[0][0] if max_order_rows and max_order_rows[0][0] is not None else 0
            self.db.cursor.execute(
                """INSERT INTO products
                   (store_id, name, title, coupon_amount, new_customer_discount, image_path, sort_order, is_natural_flow)
                   VALUES (?, ?, ?, 0, 0, NULL, ?, 1)""",
                (store_id, product_id, title, max_order + 1),
            )
            product_db_id = self.db.cursor.execute("SELECT last_insert_rowid()").fetchone()[0]
            for spec in specs:
                self.db.cursor.execute(
                    """INSERT INTO product_specs
                       (product_id, spec_name, spec_code, sale_price, weight_percent, is_locked)
                       VALUES (?, ?, ?, 0, 0, 0)""",
                    (product_db_id, spec["name"], spec["spec_code"]),
                )
            self.db.conn.commit()
            self.db.update_all_product_category_labels()
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "创建失败", f"创建 AI 选品链接失败：{e}")
            return

        if self.main_window and hasattr(self.main_window, "record_product_operation"):
            self.main_window.record_product_operation(
                product_db_id,
                f"新建链接：商品ID {product_id}，标题：{title}",
                metric="新建链接",
                old="",
                new=product_id,
                change_type="product_created",
            )
        if self.main_window and hasattr(self.main_window, "refresh_after_product_added"):
            self.main_window.refresh_after_product_added(product_db_id, store_id)
        QMessageBox.information(self, "成功", f"已创建空白链接：{product_id}\n已写入 {len(specs)} 条规格。")


class CostCategoryManageDialog(QDialog):
    """维护商品类型颜色、规格排序和当前类型统计。"""

    QUANTITY_UNITS = "本|个|件|装|套|包|组|盒|箱|支|份|册"

    class CategoryPickerDialog(QDialog):
        def __init__(self, categories, parent=None):
            super().__init__(parent)
            self.categories = categories
            self.selected_category = ""
            self.setWindowTitle("移动规格到其他分类")
            self.resize(520, 420)
            layout = QVBoxLayout(self)
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("搜索全部商品类型...")
            self.search_input.textChanged.connect(self.refresh)
            layout.addWidget(self.search_input)
            self.model = QStandardItemModel()
            self.model.setHorizontalHeaderLabels(["商品类型"])
            self.table = QTableView()
            self.table.setModel(self.model)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.doubleClicked.connect(self.accept)
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            layout.addWidget(self.table)
            buttons = QHBoxLayout()
            buttons.addStretch()
            ok_btn = QPushButton("确认")
            ok_btn.clicked.connect(self.accept)
            cancel_btn = QPushButton("取消")
            cancel_btn.clicked.connect(self.reject)
            buttons.addWidget(ok_btn)
            buttons.addWidget(cancel_btn)
            layout.addLayout(buttons)
            self.refresh()

        def refresh(self):
            self.model.setRowCount(0)
            terms = split_search_terms(self.search_input.text())
            for category in self.categories:
                if terms and not any_terms_match(terms, category):
                    continue
                row = self.model.rowCount()
                self.model.insertRow(row)
                item = QStandardItem(category)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                self.model.setItem(row, 0, item)
            if self.model.rowCount():
                self.table.selectRow(0)

        def accept(self):
            index = self.table.currentIndex()
            if index.isValid():
                item = self.model.item(index.row(), 0)
                self.selected_category = item.text().strip() if item else ""
            super().accept()

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.current_category = ""
        self._category_rows = []
        self._loading_spec_order = False
        self._order_save_timer = QTimer(self)
        self._order_save_timer.setSingleShot(True)
        self._order_save_timer.timeout.connect(self._save_current_spec_order)
        self.setWindowTitle("商品类型管理")
        self.resize(1080, 680)
        self.init_ui()
        self.load_categories()

    def _spec_codes_for_categories(self, labels):
        labels = [str(label or "").strip() for label in labels if str(label or "").strip()]
        if not labels:
            return []
        placeholders = ",".join("?" for _ in labels)
        return [
            str(row[0]) for row in self.db.safe_fetchall(
                f"SELECT spec_code FROM cost_library WHERE category_label IN ({placeholders})",
                tuple(labels),
            )
        ]

    def _notify_parent_specs_changed(self, spec_codes, reorder=False, refresh_products=False):
        codes = list(dict.fromkeys(str(code) for code in (spec_codes or []) if code))
        if not codes:
            return
        parent = self.parent()
        if parent and hasattr(parent, "_refresh_cost_rows"):
            parent._refresh_cost_rows(codes)
        if reorder and parent and hasattr(parent, "_reorder_visible_cost_rows"):
            parent._reorder_visible_cost_rows()
        if refresh_products and parent and hasattr(parent, "_refresh_main_products_for_specs"):
            parent._refresh_main_products_for_specs(codes)

    def init_ui(self):
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.addWidget(QLabel("商品类型（双击颜色格可修改颜色）"))
        self.category_search = QLineEdit()
        self.category_search.setPlaceholderText("搜索商品类型...")
        self.category_search.textChanged.connect(self.apply_category_filter)
        left.addWidget(self.category_search)
        self.category_model = QStandardItemModel()
        self.category_model.setHorizontalHeaderLabels(["商品类型", "颜色", "规格数", "链接数"])
        self.category_table = QTableView()
        self.category_table.setModel(self.category_model)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.category_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.category_table.clicked.connect(self.on_category_clicked)
        self.category_table.doubleClicked.connect(self.on_category_double_clicked)
        self.category_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.category_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.category_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.category_table.setColumnWidth(1, 58)
        left.addWidget(self.category_table)

        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.addWidget(QLabel("当前类型规格（拖拽左侧行号后自动保存）"))
        self.spec_search = QLineEdit()
        self.spec_search.setPlaceholderText("搜索商品名称或规格编码...")
        self.spec_search.textChanged.connect(lambda: self.load_specs_for_category(self.current_category))
        right.addWidget(self.spec_search)
        self.spec_model = QStandardItemModel()
        self.spec_model.setHorizontalHeaderLabels(["商品名称", "规格编码", "当前已上架规格数量"])
        self.spec_table = QTableView()
        self.spec_table.setModel(self.spec_model)
        self.spec_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.spec_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.spec_table.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.spec_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.spec_table.verticalHeader().setSectionsMovable(True)
        self.spec_table.verticalHeader().setDragEnabled(True)
        self.spec_table.verticalHeader().setDefaultSectionSize(32)
        self.spec_table.verticalHeader().sectionMoved.connect(self._schedule_order_save)
        self.spec_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.spec_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.spec_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        right.addWidget(self.spec_table)
        btn_auto_sort = QPushButton("AI自动排序当前类型")
        btn_auto_sort.clicked.connect(self.auto_sort_current_specs)
        btn_move_category = QPushButton("移动规格到其他分类")
        btn_move_category.clicked.connect(self.move_selected_specs_to_category)
        right.addWidget(btn_auto_sort)
        right.addWidget(btn_move_category)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([380, 700])
        layout.addWidget(splitter)

        btn_layout = QHBoxLayout()
        btn_add = QPushButton("新建商品类型")
        btn_add.clicked.connect(self.add_category)
        btn_rename = QPushButton("重命名商品类型")
        btn_rename.clicked.connect(self.rename_current_category)
        btn_delete = QPushButton("删除选中类型")
        btn_delete.clicked.connect(self.delete_selected_categories)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.load_categories)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_rename)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_refresh)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _make_item(self, text, editable=False, color=""):
        item = QStandardItem(str(text or ""))
        item.setEditable(editable)
        item.setTextAlignment(Qt.AlignCenter)
        if self._is_valid_hex_color(color):
            item.setBackground(QBrush(QColor(color)))
        return item

    def _make_color_item(self, color):
        item = QStandardItem("")
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        color = str(color or "").strip().upper()
        item.setData(color, Qt.UserRole)
        if self._is_valid_hex_color(color):
            item.setBackground(QBrush(QColor(color)))
        return item

    def _is_valid_hex_color(self, color):
        return isinstance(color, str) and bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", color.strip()))

    def load_categories(self):
        if hasattr(self.db, "sync_cost_categories"):
            self.db.sync_cost_categories()
        self._category_rows = self.db.get_cost_categories_with_counts() if hasattr(self.db, "get_cost_categories_with_counts") else []
        self.apply_category_filter()

    def apply_category_filter(self):
        current = self.current_category
        self.category_model.setRowCount(0)
        keyword = self.category_search.text().strip().lower() if hasattr(self, "category_search") else ""
        rows = []
        for label, color, spec_count, link_count in self._category_rows:
            if keyword and not text_matches(keyword, label):
                continue
            rows.append((label, color, spec_count, link_count))
        select_row = 0
        for label, color, spec_count, link_count in rows:
            row = self.category_model.rowCount()
            if label == current:
                select_row = row
            self.category_model.insertRow(row)
            self.category_model.setItem(row, 0, self._make_item(label, color=color))
            self.category_model.setItem(row, 1, self._make_color_item(color))
            self.category_model.setItem(row, 2, self._make_item(spec_count))
            self.category_model.setItem(row, 3, self._make_item(link_count))
        if self.category_model.rowCount() > 0:
            select_row = min(select_row, self.category_model.rowCount() - 1)
            self.category_table.selectRow(select_row)
            self.load_specs_for_category(self.category_model.item(select_row, 0).text())
        else:
            self.current_category = ""
            self.spec_model.setRowCount(0)

    def focus_category(self, category_label):
        label = str(category_label or "").strip()
        if not label:
            return
        self.current_category = label
        self.category_search.setText(label)
        self.apply_category_filter()
        for row in range(self.category_model.rowCount()):
            item = self.category_model.item(row, 0)
            if item and item.text().strip() == label:
                index = self.category_model.index(row, 0)
                self.category_table.selectRow(row)
                self.category_table.scrollTo(index, QAbstractItemView.PositionAtCenter)
                self.load_specs_for_category(label)
                self.category_table.setFocus(Qt.OtherFocusReason)
                return

    def on_category_clicked(self, index):
        if index.isValid():
            item = self.category_model.item(index.row(), 0)
            self.load_specs_for_category(item.text() if item else "")

    def on_category_double_clicked(self, index):
        if not index.isValid():
            return
        if index.column() == 0:
            self.rename_category_at_row(index.row())
        elif index.column() == 1:
            self.choose_category_color(index.row())

    def add_category(self):
        label, ok = QInputDialog.getText(self, "新建商品类型", "请输入商品类型名称:")
        label = label.strip() if ok else ""
        if not ok or not label:
            return
        try:
            if not hasattr(self.db, "ensure_cost_category"):
                raise RuntimeError("当前数据库管理器不支持新建商品类型。")
            self.db.ensure_cost_category(label)
            self.db.set_setting("cost_sync_local_dirty", "1")
            self.current_category = label
            self.category_search.clear()
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "新建失败", f"新建商品类型失败：{e}")
            return
        self.load_categories()

    def rename_current_category(self):
        index = self.category_table.currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "提示", "请先选择要重命名的商品类型。")
            return
        self.rename_category_at_row(index.row())

    def rename_category_at_row(self, row):
        item = self.category_model.item(row, 0)
        old_label = item.text().strip() if item else ""
        if not old_label:
            return
        new_label, ok = QInputDialog.getText(self, "重命名商品类型", "请输入新的商品类型名称:", text=old_label)
        new_label = new_label.strip() if ok else ""
        if not ok or not new_label or new_label == old_label:
            return
        affected_codes = self._spec_codes_for_categories([old_label])
        try:
            if hasattr(self.db, "rename_cost_category"):
                self.db.rename_cost_category(old_label, new_label)
                self.db.set_setting("cost_sync_local_dirty", "1")
            else:
                raise RuntimeError("当前数据库管理器不支持商品类型重命名。")
            self.current_category = new_label
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "重命名失败", f"商品类型重命名失败：{e}")
            return
        self._notify_parent_specs_changed(affected_codes, reorder=True, refresh_products=True)
        self.load_categories()

    def delete_selected_categories(self):
        rows = sorted({index.row() for index in self.category_table.selectedIndexes()})
        labels = []
        for row in rows:
            item = self.category_model.item(row, 0)
            label = item.text().strip() if item else ""
            if label:
                labels.append(label)
        if not labels:
            QMessageBox.warning(self, "提示", "请先选择要删除的商品类型。")
            return
        preview = "\n".join(f"- {label}" for label in labels[:12])
        if len(labels) > 12:
            preview += f"\n... 等 {len(labels)} 个"
        reply = QMessageBox.question(
            self,
            "确认删除商品类型",
            "确定删除选中的商品类型吗？\n\n"
            f"{preview}\n\n"
            "这些类型下的成本库规格不会删除，但商品类型会被清空。",
        )
        if reply != QMessageBox.Yes:
            return
        affected_codes = self._spec_codes_for_categories(labels)
        try:
            if not hasattr(self.db, "delete_cost_categories"):
                raise RuntimeError("当前数据库管理器不支持商品类型删除。")
            self.db.delete_cost_categories(labels)
            self.db.set_setting("cost_sync_local_dirty", "1")
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", f"商品类型删除失败：{e}")
            return
        self._notify_parent_specs_changed(affected_codes, reorder=True, refresh_products=True)
        self.current_category = ""
        self.load_categories()

    def load_specs_for_category(self, label):
        self._loading_spec_order = True
        self.current_category = str(label or "")
        self.spec_model.setRowCount(0)
        rows = self.db.safe_fetchall(
            """SELECT cost_library.spec_name, cost_library.spec_code,
                      COALESCE(listed_specs.listed_count, 0) AS listed_count,
                      cost_library.manual_sort_order, cost_library.sort_order
               FROM cost_library
               LEFT JOIN (
                   SELECT spec_code, COUNT(*) AS listed_count
                   FROM product_specs
                   WHERE COALESCE(spec_code, '') <> ''
                   GROUP BY spec_code
               ) listed_specs ON listed_specs.spec_code = cost_library.spec_code
               WHERE COALESCE(cost_library.category_label, '') = ?
               ORDER BY CASE WHEN manual_sort_order IS NULL THEN 1 ELSE 0 END,
                        manual_sort_order, sort_order, cost_library.spec_code""",
            (self.current_category,),
        )
        rows = self._sort_specs(rows)
        keyword = self.spec_search.text().strip().lower() if hasattr(self, "spec_search") else ""
        if keyword:
            terms = split_search_terms(keyword)
            rows = [
                row for row in rows
                if any_terms_match(terms, row[0], row[1])
            ]
        for spec_name, spec_code, listed_count, _manual, _sort_order in rows:
            self._append_spec_row(spec_name, spec_code, listed_count)
        self._reset_visual_order()
        self.spec_table.resizeRowsToContents()
        self._loading_spec_order = False

    def _append_spec_row(self, spec_name, spec_code, listed_count):
        row = self.spec_model.rowCount()
        self.spec_model.insertRow(row)
        self.spec_model.setItem(row, 0, self._make_item(spec_name))
        self.spec_model.setItem(row, 1, self._make_item(spec_code))
        self.spec_model.setItem(row, 2, self._make_item(int(listed_count or 0)))

    def _reset_visual_order(self):
        header = self.spec_table.verticalHeader()
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            if logical != visual:
                header.moveSection(visual, logical)

    def _schedule_order_save(self, *_args):
        if not self._loading_spec_order:
            self._order_save_timer.start(350)

    def _save_current_spec_order(self):
        ordered_codes = []
        for row in self._visual_ordered_model_rows():
            item = self.spec_model.item(row, 1)
            code = item.text().strip() if item else ""
            if code:
                ordered_codes.append(code)
        if not ordered_codes:
            return
        try:
            self.db.update_cost_manual_sort_orders(ordered_codes)
            self.db.set_setting("cost_sync_local_dirty", "1")
            self._notify_parent_specs_changed(ordered_codes, reorder=True)
            parent = self.parent()
            if parent and hasattr(parent, "_show_copy_hint"):
                parent._show_copy_hint("规格顺序已自动保存", 1000)
        except Exception as exc:
            QMessageBox.critical(self, "排序保存失败", str(exc))

    def _current_spec_rows(self):
        rows = []
        for row in range(self.spec_model.rowCount()):
            rows.append({
                "name": self.spec_model.item(row, 0).text().strip(),
                "spec_code": self.spec_model.item(row, 1).text().strip(),
                "listed_count": self.spec_model.item(row, 2).text().strip(),
            })
        return rows

    def _visual_ordered_model_rows(self):
        header = self.spec_table.verticalHeader()
        ordered = []
        for visual in range(self.spec_model.rowCount()):
            logical = header.logicalIndex(visual)
            if 0 <= logical < self.spec_model.rowCount():
                ordered.append(logical)
        return ordered

    def _set_spec_rows(self, rows):
        self.spec_model.setRowCount(0)
        for row_data in rows:
            self._append_spec_row(row_data["name"], row_data["spec_code"], row_data["listed_count"])
        self._reset_visual_order()
        self.spec_table.resizeRowsToContents()

    def _selected_spec_codes(self):
        rows = sorted({index.row() for index in self.spec_table.selectedIndexes()})
        codes = []
        for row in rows:
            item = self.spec_model.item(row, 1)
            spec_code = item.text().strip() if item else ""
            if spec_code and spec_code not in codes:
                codes.append(spec_code)
        return codes

    def move_selected_specs_to_category(self):
        spec_codes = self._selected_spec_codes()
        if not spec_codes:
            QMessageBox.warning(self, "提示", "请先选中要移动分类的规格。")
            return
        categories = [
            str(row[0] or "").strip()
            for row in self._category_rows
            if str(row[0] or "").strip() and str(row[0] or "").strip() != self.current_category
        ]
        if not categories:
            QMessageBox.warning(self, "提示", "没有可移动到的其他商品类型。")
            return
        dialog = self.CategoryPickerDialog(categories, self)
        dialog.setWindowTitle(f"移动 {len(spec_codes)} 个规格到其他分类")
        if dialog.exec_() != QDialog.Accepted or not dialog.selected_category:
            return
        target = dialog.selected_category
        try:
            for spec_code in spec_codes:
                if hasattr(self.db, "update_cost_spec_category"):
                    self.db.update_cost_spec_category(spec_code, target)
            self.db.set_setting("cost_sync_local_dirty", "1")
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "移动失败", f"移动规格分类失败：{e}")
            return
        self._notify_parent_specs_changed(spec_codes, reorder=True, refresh_products=True)
        QMessageBox.information(self, "成功", f"已移动 {len(spec_codes)} 个规格到“{target}”。")
        self.load_categories()

    def _base_product_key(self, name):
        text = str(name or "").strip().lower()
        if not text:
            return ""
        normalized = re.sub(r"[（(【\[].*?[）)】\]]", "", text)
        normalized = re.sub(rf"\d+(?:\.\d+)?\s*(?:{self.QUANTITY_UNITS})", "", normalized)
        normalized = re.sub(rf"(?:{self.QUANTITY_UNITS})\s*\d+(?:\.\d+)?", "", normalized)
        normalized = re.sub(r"\d+(?:\.\d+)?", "", normalized)
        normalized = re.sub(rf"(?:{self.QUANTITY_UNITS})", "", normalized)
        normalized = re.sub(r"[\\/\-_\s,，.。:：;；+＋|、]+", "", normalized)
        return normalized if len(normalized) >= 2 else text

    def _quantity_rank(self, spec_name):
        match = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{self.QUANTITY_UNITS})", str(spec_name or ""))
        if match:
            return float(match.group(1))
        return 10**9

    def _sort_specs(self, rows):
        if any(row[3] is not None for row in rows):
            return rows
        return sorted(rows, key=lambda row: (self._base_product_key(row[0]), self._quantity_rank(row[0]), str(row[1] or "")))

    def _fallback_sort_rows(self, rows):
        return sorted(rows, key=lambda row: (self._base_product_key(row["name"]), self._quantity_rank(row["name"]), row["name"], row["spec_code"]))

    def auto_sort_current_specs(self):
        rows = self._current_spec_rows()
        if not rows:
            QMessageBox.information(self, "提示", "当前商品类型下没有可排序的规格。")
            return
        try:
            sorted_rows = self._ai_sort_rows(rows)
            self._set_spec_rows(sorted_rows)
            self._save_current_spec_order()
            QMessageBox.information(self, "成功", "AI排序完成并已自动保存。")
        except Exception as e:
            self._set_spec_rows(self._fallback_sort_rows(rows))
            self._save_current_spec_order()
            QMessageBox.warning(self, "AI排序已使用本地兜底", f"{e}\n\n已按本地规则排序并自动保存。")

    def _build_ai_sort_prompt(self, rows):
        candidates = [{"row_index": idx, "name": row["name"]} for idx, row in enumerate(rows, start=1)]
        return (
            "给下面商品排序。要求：同款产品放一起；同款内按商品名称里的本数、张数、套装、套餐等规格从少到多。"
            "无法判断的保持原顺序。"
            "输出排序后的 row_index 即可，可以用逗号分隔，也可以用JSON数组；不要输出商品名。\n"
            f"商品列表：{json.dumps(candidates, ensure_ascii=False)}"
        )

    def _ai_sort_rows(self, rows):
        api_key = self.db.get_setting("ai_api_key", "") if hasattr(self.db, "get_setting") else ""
        if not api_key:
            raise RuntimeError("未配置 API Key。")
        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你只需要输出排序后的 row_index 顺序。"},
                {"role": "user", "content": self._build_ai_sort_prompt(rows)},
            ],
            "temperature": 0,
            "max_tokens": max(2048, min(12000, len(rows) * 16)),
        }

        progress = QProgressDialog("正在调用 AI 自动排序...", "取消", 0, 2, self)
        progress.setWindowTitle("AI自动排序")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            import requests

            response = requests.post(api_url, headers=headers, json=payload, timeout=90)
            if progress.wasCanceled():
                raise RuntimeError("已取消 AI 排序。")
            if response.status_code != 200:
                raise RuntimeError(f"AI 请求失败：HTTP {response.status_code}\n{response.text[:300]}")
            progress.setLabelText("正在解析 AI 排序结果...")
            progress.setValue(1)
            QApplication.processEvents()
            response_data = response.json()
            message = response_data["choices"][0].get("message", {})
            content = message.get("content", "") or message.get("reasoning_content", "")
            if not str(content or "").strip():
                raise RuntimeError(f"AI 返回内容为空。\nAPI URL：{api_url}\n模型：{model}\n返回内容：{str(response_data)[:500]}")
            order = self._parse_ai_sort_result(content)
            if not order:
                raise RuntimeError(f"AI 没有返回可识别的排序结果。\n返回内容：{str(content)[:500]}")
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()

        row_map = {idx: row for idx, row in enumerate(rows, start=1)}
        sorted_rows = []
        seen = set()
        for row_index in order:
            if row_index in row_map and row_index not in seen:
                sorted_rows.append(row_map[row_index])
                seen.add(row_index)
        for idx, row in row_map.items():
            if idx not in seen:
                sorted_rows.append(row)
        return sorted_rows

    def _parse_ai_sort_result(self, text):
        json_text = self._extract_json_text(text)
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            try:
                fixed = json_text.replace("'", '"').replace("(", "{").replace(")", "}")
                data = json.loads(fixed)
            except json.JSONDecodeError:
                data = None
        order = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, int):
                    order.append(item)
                elif isinstance(item, dict):
                    value = item.get("row_index") or item.get("rowIndex") or item.get("index")
                    try:
                        order.append(int(value))
                    except (TypeError, ValueError):
                        continue
        if order:
            return order

        text = str(text or "")
        for pattern in (
            r"row[_\s-]*index[\"'\s:=：]+(\d+)",
            r"rowIndex[\"'\s:=：]+(\d+)",
            r"\bindex[\"'\s:=：]+(\d+)",
        ):
            values = [int(value) for value in re.findall(pattern, text, flags=re.I)]
            if values:
                return values

        index_list = re.search(r"(?:\d+\s*[,，、\s]+){1,}\d+", text)
        if index_list:
            return [int(value) for value in re.findall(r"\d+", index_list.group(0))]

        # 最后兜底：只在文本看起来像纯索引列表时提取数字，避免把“3本/50张”等商品数量误当成行号。
        compact = re.sub(r"[\s,，、;；|\[\]{}()（）\"'`]+", "", text)
        if re.fullmatch(r"\d+", compact or ""):
            return [int(value) for value in re.findall(r"\d+", text)]
        return order

    def _extract_json_text(self, text):
        text = str(text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
        return text

    def choose_category_color(self, row):
        color_item = self.category_model.item(row, 1)
        if not color_item:
            return
        initial_text = color_item.data(Qt.UserRole) or "#FFFFFF"
        color = QColorDialog.getColor(QColor(initial_text or "#FFFFFF"), self, "选择商品类型颜色")
        if not color.isValid():
            return
        color_text = color.name().upper()
        if color_text == str(initial_text or "").strip().upper():
            return
        for col in (0, 1):
            item = self.category_model.item(row, col)
            item.setBackground(QBrush(QColor(color_text)))
        color_item.setData(color_text, Qt.UserRole)
        try:
            label_item = self.category_model.item(row, 0)
            label = label_item.text().strip() if label_item else ""
            if label:
                affected_codes = self._spec_codes_for_categories([label])
                self.db.update_cost_category_color(label, color_text)
                self.db.set_setting("cost_sync_local_dirty", "1")
                self._notify_parent_specs_changed(affected_codes)
                parent = self.parent()
                if parent and hasattr(parent, "_show_copy_hint"):
                    parent._show_copy_hint("商品类型颜色已自动保存", 1000)
        except Exception as exc:
            QMessageBox.critical(self, "颜色保存失败", str(exc))

class CostItemCreateDialog(QDialog):
    """手动新增成本库商品规格。"""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.selected_single_spec = None
        self.cost_mode = self.db.get_cost_library_mode() if hasattr(self.db, "get_cost_library_mode") else "total"
        self.setWindowTitle("新增商品")
        self.resize(720, 620 if self.cost_mode == "detail" else 540)
        self.init_ui()
        self.load_categories()

    def init_ui(self):
        layout = QVBoxLayout(self)

        quick_label = QLabel("快速识别：一次粘贴表头行和对应的数据行，点击识别后自动填入下方字段。")
        quick_label.setWordWrap(True)
        quick_label.setStyleSheet("color: #666;")
        layout.addWidget(quick_label)
        self.quick_header_input = QTextEdit()
        self.quick_header_input.setAcceptRichText(False)
        self.quick_header_input.setPlaceholderText("一次粘贴表头 + 数据行，例如：\n商品类型\t商品名称\t商品编码\t...\n语文字词默写纸\t错字默写本...\t2606110004\t...")
        self.quick_header_input.setFixedHeight(132)
        layout.addWidget(self.quick_header_input)
        self.quick_value_input = QTextEdit()
        self.quick_value_input.setAcceptRichText(False)
        self.quick_value_input.setVisible(False)
        quick_btn_layout = QHBoxLayout()
        quick_btn_layout.addStretch()
        btn_quick_parse = QPushButton("识别并填入")
        btn_quick_parse.clicked.connect(self.quick_fill_from_paste)
        quick_btn_layout.addWidget(btn_quick_parse)
        layout.addLayout(quick_btn_layout)

        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("商品类型:"))
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.setInsertPolicy(QComboBox.NoInsert)
        self.category_combo.lineEdit().setPlaceholderText("输入商品类型关键字搜索...")
        category_layout.addWidget(self.category_combo)
        layout.addLayout(category_layout)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("商品名称:"))
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(self._update_selected_single_values)
        name_layout.addWidget(self.name_input, 1)
        btn_select_single = QPushButton("选择单品商品")
        btn_select_single.clicked.connect(self.select_single_product)
        name_layout.addWidget(btn_select_single)
        layout.addLayout(name_layout)

        code_layout = QHBoxLayout()
        code_layout.addWidget(QLabel("规格编码:"))
        self.code_input = QLineEdit()
        code_layout.addWidget(self.code_input)
        layout.addLayout(code_layout)

        attribute_layout = QHBoxLayout()
        attribute_layout.addWidget(QLabel("产品属性:"))
        self.attribute_input = QTextEdit()
        self.attribute_input.setAcceptRichText(False)
        self.attribute_input.setPlaceholderText("可为空；快速识别会合并尺寸、张数（含封面）、印刷工艺")
        self.attribute_input.setFixedHeight(72)
        attribute_layout.addWidget(self.attribute_input)
        layout.addLayout(attribute_layout)

        cost_layout = QHBoxLayout()
        cost_layout.addWidget(QLabel("产品成本:" if self.cost_mode == "detail" else "成本价:"))
        self.cost_input = QLineEdit()
        cost_layout.addWidget(self.cost_input)
        layout.addLayout(cost_layout)

        self.weight_input = QLineEdit()
        if self.cost_mode == "detail":
            weight_layout = QHBoxLayout()
            weight_layout.addWidget(QLabel("重量（kg）:"))
            weight_layout.addWidget(self.weight_input)
            layout.addLayout(weight_layout)
            misc_fee = self.db.get_cost_misc_fee() if hasattr(self.db, "get_cost_misc_fee") else 0
            note = QLabel(f"详细成本模式：产品成本或重量留空时不计算总成本；杂费 {misc_fee:.2f}，快递费按模板计算")
            note.setStyleSheet("color: #666; padding: 4px;")
            note.setWordWrap(True)
            layout.addWidget(note)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.create_item)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _parse_pasted_row(self, text):
        text = str(text or "").strip("\ufeff\r\n ")
        if not text:
            return []
        try:
            rows = [
                [str(cell or "").strip() for cell in row]
                for row in csv.reader(io.StringIO(text), delimiter="\t")
                if any(str(cell or "").strip() for cell in row)
            ]
        except Exception:
            rows = []
        if rows:
            if len(rows) == 1:
                return rows[0]
            first = rows[0]
            for extra in rows[1:]:
                if len(extra) == 1 and first:
                    first[-1] = (first[-1] + "\n" + extra[0]).strip()
            return first
        return [part.strip() for part in text.split("\t")]

    def _parse_pasted_table(self, text):
        text = str(text or "").strip("\ufeff\r\n ")
        if not text:
            return []
        try:
            return [
                [str(cell or "").strip() for cell in row]
                for row in csv.reader(io.StringIO(text), delimiter="\t")
                if any(str(cell or "").strip() for cell in row)
            ]
        except Exception:
            return []

    def _extract_quick_headers_values_by_lines(self, text):
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\ufeff\n ")
        lines = [line for line in text.split("\n") if line.strip()]
        if len(lines) < 2 or "\t" not in lines[0]:
            return [], []
        headers = [cell.strip().strip('"') for cell in lines[0].split("\t")]
        value_lines = lines[1:]
        values = [cell.strip().strip('"') for cell in value_lines[0].split("\t")]
        for line in value_lines[1:]:
            parts = [cell.strip().strip('"') for cell in line.split("\t")]
            if not parts:
                continue
            if len(values) >= len(headers):
                values[-1] = (values[-1] + "\n" + "\t".join(parts)).strip()
                continue
            missing = len(headers) - len(values)
            if len(parts) <= missing:
                if len(parts) == 1 and missing > 1 and values:
                    values[-1] = (values[-1] + "\n" + parts[0]).strip()
                else:
                    values.extend(parts)
            else:
                continuation_count = len(parts) - missing
                continuation = "\n".join(parts[:continuation_count]).strip()
                if continuation and values:
                    values[-1] = (values[-1] + "\n" + continuation).strip()
                values.extend(parts[continuation_count:])
        if len(values) > len(headers):
            fixed = values[: len(headers)]
            fixed[-1] = "\n".join([fixed[-1]] + values[len(headers):]).strip()
            values = fixed
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        return headers, values

    def _extract_quick_headers_values(self):
        combined_text = self.quick_header_input.toPlainText()
        headers, values = self._extract_quick_headers_values_by_lines(combined_text)
        if headers and values:
            return headers, values
        rows = self._parse_pasted_table(combined_text)
        if len(rows) >= 2:
            headers = rows[0]
            values = list(rows[1])
            for extra in rows[2:]:
                if not extra:
                    continue
                if len(values) < len(headers):
                    missing = len(headers) - len(values)
                    if len(extra) == 1 and values:
                        values[-1] = (str(values[-1] or "") + "\n" + str(extra[0] or "")).strip()
                    elif len(extra) > missing and values:
                        continuation_count = len(extra) - missing
                        continuation = "\n".join(str(cell or "") for cell in extra[:continuation_count]).strip()
                        if continuation:
                            values[-1] = (str(values[-1] or "") + "\n" + continuation).strip()
                        values.extend(extra[continuation_count:])
                    else:
                        values.extend(extra)
                elif values:
                    values[-1] = (str(values[-1] or "") + "\n" + "\t".join(str(cell or "") for cell in extra)).strip()
            if len(values) > len(headers):
                fixed = values[: len(headers)]
                fixed[-1] = "\n".join([fixed[-1]] + values[len(headers):]).strip()
                values = fixed
            return headers, values
        value_text = self.quick_value_input.toPlainText() if hasattr(self, "quick_value_input") else ""
        headers = self._parse_pasted_row(combined_text)
        values = self._parse_pasted_row(value_text)
        return headers, values

    def _normalize_header(self, value):
        return re.sub(r"[\s_（）()【】\[\]：:]+", "", str(value or "").strip().lower())

    def _find_column(self, headers, keyword_groups):
        normalized = [self._normalize_header(header) for header in headers]
        for keywords in keyword_groups:
            normalized_keywords = [self._normalize_header(keyword) for keyword in keywords]
            for idx, header in enumerate(normalized):
                if header in normalized_keywords:
                    return idx
            for idx, header in enumerate(normalized):
                if any(keyword and keyword in header for keyword in normalized_keywords):
                    return idx
        return None

    def _value_at(self, values, index):
        if index is None or index < 0 or index >= len(values):
            return ""
        value = str(values[index] or "").strip()
        return "" if value.lower() == "nan" else value

    def _clean_money_text(self, value):
        value = str(value or "").replace("￥", "").replace("¥", "").replace("$", "").replace(",", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        return match.group(0) if match else value

    def _clean_weight_text(self, value):
        match = re.search(r"\d+(?:\.\d+)?", str(value or "").replace(",", ""))
        return match.group(0) if match else str(value or "").strip()

    def _build_attribute_from_columns(self, headers, values):
        parts = []
        columns = [
            ("尺寸", [["尺寸", "规格尺寸", "size"]], "mm"),
            ("张数（含封面）", [["张数（含封面）", "张数含封面"], ["张数", "页数", "pages"]], "张"),
            ("印刷工艺", [["印刷工艺", "印刷", "工艺", "print"]], ""),
        ]
        for default_label, keywords, suffix in columns:
            index = self._find_column(headers, keywords)
            value = self._value_at(values, index)
            if not value:
                continue
            if suffix and suffix not in value:
                value = f"{value}{suffix}"
            label = str(headers[index]).strip() if index is not None and index < len(headers) and str(headers[index]).strip() else default_label
            parts.append(f"{label}：{value}")
        return "\n".join(parts)

    def quick_fill_from_paste(self):
        headers, values = self._extract_quick_headers_values()
        if not headers or not values:
            QMessageBox.warning(self, "识别失败", "请一次粘贴表头行和对应的数据行。")
            return
        if len(headers) < 2 or len(values) < 2:
            QMessageBox.warning(
                self,
                "识别失败",
                "没有识别到表格列。请从表格里直接复制整行表头和数据行，或先粘贴到记事本确认列之间是制表符分隔。",
            )
            return
        if len(values) < len(headers):
            values = values + [""] * (len(headers) - len(values))

        mappings = {
            "category": self._find_column(headers, [["商品类型"], ["产品类型", "类型", "分类", "类别", "品类", "类目", "category", "type"]]),
            "name": self._find_column(headers, [["商品名称", "商品名"], ["产品名称", "产品名", "品名", "标题", "name", "title", "名称"]]),
            "code": self._find_column(headers, [["规格编码", "商品编码"], ["规格代码", "编码", "sku", "spec_code", "code"]]),
            "weight": self._find_column(headers, [["重量"], ["单重", "单个重量", "净重", "weight"]]),
        }
        if self.cost_mode == "detail":
            mappings["cost"] = self._find_column(headers, [["产品成本"], ["单品成本", "单个成本", "产品单价", "进价", "成本"]])
        else:
            mappings["cost"] = self._find_column(headers, [["总成本"], ["成本价", "成本", "价格", "price", "cost", "单价", "进价", "money"]])

        category = self._value_at(values, mappings["category"])
        if category:
            self.category_combo.setEditText(category)
        name = self._value_at(values, mappings["name"])
        if name:
            self.name_input.setText(name)
        code = self._value_at(values, mappings["code"])
        if code:
            self.code_input.setText(code)
        cost = self._value_at(values, mappings["cost"])
        if cost:
            self.cost_input.setText(self._clean_money_text(cost))
        if self.cost_mode == "detail":
            weight = self._value_at(values, mappings["weight"])
            if weight:
                self.weight_input.setText(self._clean_weight_text(weight))
        attribute = self._build_attribute_from_columns(headers, values)
        if attribute:
            self.attribute_input.setPlainText(attribute)
        preview_lines = [
            "已按表头自动填入可识别字段：",
            f"商品类型：{category or '-'}",
            f"商品名称：{name or '-'}",
            f"规格编码：{code or '-'}",
            f"成本：{self._clean_money_text(cost) if cost else '-'}",
        ]
        if self.cost_mode == "detail":
            preview_lines.append(f"重量：{self.weight_input.text().strip() or '-'}")
        preview_lines.append("产品属性：")
        preview_lines.append(attribute or "-")
        QMessageBox.information(self, "识别完成", "\n".join(preview_lines))

    def load_categories(self):
        if hasattr(self.db, "sync_cost_categories"):
            self.db.sync_cost_categories()
        rows = self.db.safe_fetchall(
            """SELECT label
               FROM cost_categories
               WHERE COALESCE(label, '') <> ''
               ORDER BY sort_order, label"""
        )
        self.category_combo.clear()
        self.category_labels = []
        for (label,) in rows:
            text = str(label)
            self.category_labels.append(text)
            self.category_combo.addItem(text, text)
        completer = QCompleter(self.category_labels, self.category_combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.category_combo.setCompleter(completer)

    def select_single_product(self):
        rows = self.db.safe_fetchall(
            """SELECT COALESCE(category_label, ''), COALESCE(spec_name, ''), spec_code,
                      product_cost, unit_weight, COALESCE(product_attribute, '')
               FROM cost_library
               WHERE COALESCE(spec_code, '')<>''
                 AND COALESCE(product_attribute_is_combo, 0)=0
               ORDER BY CASE WHEN sort_order IS NULL THEN 1 ELSE 0 END, sort_order, spec_code"""
        )
        specs = [
            {
                "category": str(category or ""), "name": str(name or ""), "code": str(code),
                "product_cost": product_cost, "unit_weight": unit_weight,
                "attribute": str(attribute or ""),
            }
            for category, name, code, product_cost, unit_weight, attribute in rows
        ]
        if not specs:
            QMessageBox.information(self, "提示", "成本库里还没有可选择的单品商品。")
            return

        picker = QDialog(self)
        picker.setWindowTitle("选择单品商品")
        picker.resize(620, 120)
        picker_layout = QVBoxLayout(picker)
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        displays = []
        for spec in specs:
            display = f"{spec['name']}｜{spec['category'] or '未分类'}｜{spec['code']}"
            displays.append(display)
            combo.addItem(display, spec)
        combo.setCurrentIndex(-1)
        combo.lineEdit().setPlaceholderText("输入商品名称、类型或规格编码搜索...")
        completer = QCompleter(displays, combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        combo.setCompleter(completer)
        picker_layout.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(picker.accept)
        buttons.rejected.connect(picker.reject)
        picker_layout.addWidget(buttons)
        if picker.exec_() != QDialog.Accepted:
            return
        index = combo.findText(combo.currentText(), Qt.MatchExactly)
        spec = combo.itemData(index) if index >= 0 else None
        if not isinstance(spec, dict):
            QMessageBox.information(self, "提示", "请从搜索结果中选择一个单品商品。")
            return
        self.selected_single_spec = dict(spec)
        self.name_input.setText(spec["name"])
        if not self.attribute_input.toPlainText().strip() and spec["attribute"]:
            self.attribute_input.setPlainText(spec["attribute"])
        self._update_selected_single_values()

    def _selected_single_multiplier(self):
        if not self.selected_single_spec:
            return 0
        name = self.name_input.text().strip()
        if not name.startswith(self.selected_single_spec["name"]):
            return 0
        return self.db.cost_combo_multiplier(name) if hasattr(self.db, "cost_combo_multiplier") else 1

    def _update_selected_single_values(self):
        if self.cost_mode != "detail":
            return
        multiplier = self._selected_single_multiplier()
        if multiplier <= 0:
            return
        product_cost = self.selected_single_spec.get("product_cost")
        unit_weight = self.selected_single_spec.get("unit_weight")
        self.cost_input.setText(
            "" if product_cost is None else f"{float(product_cost) * multiplier:.4f}".rstrip("0").rstrip(".")
        )
        self.weight_input.setText(
            "" if unit_weight is None else f"{float(unit_weight) * multiplier:.4f}".rstrip("0").rstrip(".")
        )

    def _parse_cost(self):
        text = self.cost_input.text().replace("¥", "").replace("$", "").replace(",", "").strip()
        if not text:
            if self.cost_mode == "detail":
                return None
            raise ValueError("成本价不能为空")
        value = float(text)
        if value < 0:
            raise ValueError("产品成本不能小于 0" if self.cost_mode == "detail" else "成本价不能小于 0")
        return value

    def _parse_unit_weight(self):
        text = self.weight_input.text().replace(",", "").strip()
        if not text:
            return None
        match = re.search(r"\d+(?:\.\d+)?", text)
        if not match:
            raise ValueError("重量必须是数字")
        value = float(match.group(0))
        if value <= 0:
            raise ValueError("重量必须大于 0")
        return value

    def create_item(self):
        category_label = str(self.category_combo.currentText() or "").strip()
        spec_name = self.name_input.text().strip()
        spec_code = self.code_input.text().strip()
        quantity = ""
        product_attribute = self.attribute_input.toPlainText().strip()
        if not category_label:
            QMessageBox.warning(self, "提示", "商品类型不能为空。")
            return
        if not spec_name:
            QMessageBox.warning(self, "提示", "商品名称不能为空。")
            return
        if not spec_code:
            QMessageBox.warning(self, "提示", "规格编码不能为空。")
            return
        if self.db.safe_fetchall("SELECT 1 FROM cost_library WHERE spec_code=?", (spec_code,)):
            QMessageBox.warning(self, "提示", f"规格编码已存在：{spec_code}")
            return
        try:
            input_cost = self._parse_cost()
            product_cost = None
            unit_weight = None
            shipping_fee = None
            misc_fee = None
            cost_calc_mode = "total"
            if self.cost_mode == "detail":
                product_cost = input_cost
                unit_weight = self._parse_unit_weight()
                if product_cost is not None and unit_weight is not None:
                    cost_price, shipping_fee, misc_fee, _total_weight = self.db.calculate_detailed_cost(
                        product_cost, 1, unit_weight
                    )
                else:
                    cost_price = None
                cost_calc_mode = "detail"
            else:
                cost_price = input_cost
        except ValueError as e:
            QMessageBox.warning(self, "成本格式错误", str(e))
            return

        category_color = self.db.ensure_cost_category(category_label) if hasattr(self.db, "ensure_cost_category") else ""
        max_rows = self.db.safe_fetchall("SELECT MAX(sort_order) FROM cost_library")
        next_order = (max_rows[0][0] if max_rows and max_rows[0][0] is not None else 0) + 1
        multiplier = self._selected_single_multiplier()
        is_combo = int(bool(self.selected_single_spec and multiplier > 1))
        combo_json = (
            json.dumps([{
                "spec_code": self.selected_single_spec["code"], "quantity": multiplier,
            }], ensure_ascii=False)
            if is_combo else ""
        )
        try:
            self.db.safe_execute(
                """INSERT INTO cost_library
                   (spec_code, spec_name, quantity, category_label, category_color, cost_price, sort_order,
                    manual_sort_order, product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
                    product_attribute, product_attribute_combo_disabled, product_attribute_is_combo,
                    combo_components_json, combo_reviewed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                (
                    spec_code, spec_name, quantity, category_label, category_color, cost_price, next_order,
                    product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode, product_attribute,
                    is_combo, combo_json, is_combo,
                ),
            )
            if hasattr(self.db, "normalize_cost_category_colors"):
                self.db.normalize_cost_category_colors()
            self.db.set_setting("cost_sync_local_dirty", "1")
            QMessageBox.information(self, "成功", "商品已新增。")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "新增失败", f"新增商品失败：{e}")


class CostLinkCreateDialog(QDialog):
    """从成本库选中规格创建空白链接。"""

    def __init__(self, db_manager, specs, main_window=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.specs = specs
        self.main_window = main_window
        self.setWindowTitle("创建链接")
        self.resize(680, 420)
        self.init_ui()
        self.load_stores()

    def init_ui(self):
        layout = QVBoxLayout(self)
        store_layout = QHBoxLayout()
        store_layout.addWidget(QLabel("店铺:"))
        self.store_combo = QComboBox()
        store_layout.addWidget(self.store_combo)
        layout.addLayout(store_layout)
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("标题:"))
        self.title_input = QLineEdit(datetime.now().strftime("成本库链接-%Y%m%d_%H%M%S"))
        title_layout.addWidget(self.title_input)
        layout.addLayout(title_layout)

        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("商品类型:"))
        self.category_value_label = QLabel(self._inferred_category_label())
        self.category_value_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        category_layout.addWidget(self.category_value_label, 1)
        layout.addLayout(category_layout)

        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("链接类型:"))
        self.link_type_input = QLineEdit()
        self.link_type_input.setPlaceholderText("必填，例如：学生练习套装")
        type_layout.addWidget(self.link_type_input)
        btn_ai_type = QPushButton("AI生成链接类型")
        btn_ai_type.clicked.connect(self.generate_link_type)
        type_layout.addWidget(btn_ai_type)
        layout.addLayout(type_layout)

        preview_names = "、".join([str(spec.get("spec_name") or "") for spec in self.specs[:8] if spec.get("spec_name")])
        if len(self.specs) > 8:
            preview_names += "..."
        preview_label = QLabel(f"将写入 {len(self.specs)} 条规格，售价默认 0，权重默认 0。\n{preview_names}")
        preview_label.setWordWrap(True)
        preview_label.setMaximumWidth(620)
        preview_label.setStyleSheet("color: #555; padding: 4px;")
        layout.addWidget(preview_label)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_create = QPushButton("创建")
        btn_create.clicked.connect(self.create_link)
        btn_close = QPushButton("取消")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def load_stores(self):
        for store_id, store_name in self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order, id"):
            self.store_combo.addItem(str(store_name or f"店铺{store_id}"), store_id)

    def _inferred_category_label(self):
        counts = {}
        for index, spec in enumerate(self.specs):
            label = str(spec.get("category_label") or "").strip()
            if not label:
                continue
            info = counts.setdefault(label, {"count": 0, "first": index})
            info["count"] += 1
        if not counts:
            return "未分类商品类型"
        return min(counts, key=lambda label: (-counts[label]["count"], counts[label]["first"], label))

    def _ai_context(self):
        lines = []
        for index, spec in enumerate(self.specs, start=1):
            lines.append(
                f"{index}. 商品名称:{str(spec.get('spec_name') or '').strip()}; "
                f"规格编码:{str(spec.get('spec_code') or '').strip()}; "
                f"商品类型:{str(spec.get('category_label') or '').strip()}"
            )
        return "\n".join(lines)

    def _existing_link_types(self):
        rows = self.db.safe_fetchall(
            "SELECT DISTINCT link_type FROM products WHERE COALESCE(link_type, '') <> '' ORDER BY link_type"
        )
        return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]

    def _call_ai_text(self):
        api_key = self.db.get_setting("ai_api_key", "") if hasattr(self.db, "get_setting") else ""
        if not api_key:
            raise RuntimeError("未配置 API Key，请先到 API 配置里填写。")
        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        existing_types = self._existing_link_types()
        field_name = "link_type"
        max_chars = 40
        task = (
            "为这次选中的商品选择链接类型。先从现有链接类型中选择最符合的一个；"
            "只有现有链接类型都不符合时，才生成一个新的短链接类型。"
            "必须只返回 JSON，例如 {\"link_type\":\"儿童启蒙资料\"}。"
        )
        reference = "现有链接类型:\n" + ("\n".join(f"- {item}" for item in existing_types) or "无")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是电商链接分类助手。只输出一个 JSON 对象，不要解释，不要代码块，不要推理过程。"},
                {"role": "user", "content": f"{task}\n\n{reference}\n\n本次商品:\n{self._ai_context()}"},
            ],
            "temperature": 0.3,
            "max_tokens": 300,
        }
        import requests
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(f"AI请求失败：HTTP {response.status_code}\n{response.text[:300]}")
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        content = str(message.get("content") or "").strip()
        if not content:
            raise RuntimeError(f"AI返回内容为空。API URL: {api_url}\n模型:{model}\n返回内容:{str(data)[:500]}")
        value = _clean_ai_short_value(content, field_name, existing_types, max_chars)
        if not value:
            raise RuntimeError(f"AI返回内容无法识别。返回内容:{content[:300]}")
        return value

    def generate_link_type(self):
        try:
            self.link_type_input.setText(self._call_ai_text())
        except Exception as e:
            QMessageBox.warning(self, "AI生成失败", str(e))

    def _unique_product_id(self):
        base = datetime.now().strftime("COST_LINK_%Y%m%d_%H%M%S")
        product_id = base
        suffix = 1
        while self.db.safe_fetchall("SELECT id FROM products WHERE name=?", (product_id,)):
            suffix += 1
            product_id = f"{base}_{suffix}"
        return product_id

    def create_link(self):
        store_id = self.store_combo.currentData()
        if store_id is None:
            QMessageBox.warning(self, "提示", "请先创建店铺。")
            return
        product_id = self._unique_product_id()
        title = self.title_input.text().strip() or product_id
        link_type = self.link_type_input.text().strip()
        if not link_type:
            QMessageBox.warning(self, "提示", "请填写链接类型。")
            return
        try:
            self.db.conn.execute("BEGIN TRANSACTION")
            max_rows = self.db.cursor.execute("SELECT MAX(sort_order) FROM products WHERE store_id=?", (store_id,)).fetchall()
            max_order = max_rows[0][0] if max_rows and max_rows[0][0] is not None else 0
            self.db.cursor.execute(
                """INSERT INTO products
                   (store_id, name, title, coupon_amount, new_customer_discount, image_path, sort_order,
                    product_category_label, link_type, is_natural_flow)
                   VALUES (?, ?, ?, 0, 0, NULL, ?, ?, ?, 1)""",
                (store_id, product_id, title, max_order + 1, self._inferred_category_label(), link_type),
            )
            product_db_id = self.db.cursor.execute("SELECT last_insert_rowid()").fetchone()[0]
            for spec in self.specs:
                self.db.cursor.execute(
                    """INSERT INTO product_specs
                       (product_id, spec_name, spec_code, sale_price, weight_percent, is_locked)
                       VALUES (?, ?, ?, 0, 0, 0)""",
                    (product_db_id, spec["spec_name"], spec["spec_code"]),
                )
            self.db.conn.commit()
            if hasattr(self.db, "update_product_category_label"):
                self.db.update_product_category_label(product_db_id)
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "创建失败", f"创建链接失败：{e}")
            return
        if self.main_window and hasattr(self.main_window, "record_product_operation"):
            self.main_window.record_product_operation(
                product_db_id,
                f"新建链接：商品ID {product_id}，标题：{title}",
                metric="新建链接",
                old="",
                new=product_id,
                change_type="product_created",
            )
        if self.main_window and hasattr(self.main_window, "refresh_after_product_added"):
            self.main_window.refresh_after_product_added(product_db_id, store_id)
        QMessageBox.information(self, "成功", f"已创建空白链接：{product_id}\n已写入 {len(self.specs)} 条规格。")
        self.accept()


class LinkAddToCombinationDialog(QDialog):
    """选择现有链接加入当前链接组合。"""

    def __init__(self, db_manager, combo_id, store_id=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.combo_id = combo_id
        self.store_id = store_id
        self.setWindowTitle("添加链接到组合")
        self.resize(860, 620)
        self.init_ui()
        self.load_links()

    def init_ui(self):
        layout = QVBoxLayout(self)
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索链接ID/标题:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入链接ID或标题关键字，空格分隔...")
        self.search_input.textChanged.connect(self.load_links)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["图片", "链接ID", "标题", "当前组合"])
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setIconSize(QSize(58, 58))
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 72)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确认添加")
        btn_ok.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _make_item(self, text, user_data=None):
        item = QStandardItem(str(text or ""))
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        if user_data is not None:
            item.setData(user_data, Qt.UserRole)
        return item

    def _make_image_item(self, image_data, user_data=None):
        item = QStandardItem("")
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        if user_data is not None:
            item.setData(user_data, Qt.UserRole)
        if image_data:
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(image_data)):
                item.setData(pixmap.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation), Qt.DecorationRole)
            else:
                item.setText("无图")
        else:
            item.setText("无图")
        return item

    def load_links(self):
        self.model.setRowCount(0)
        params = []
        where = []
        if self.store_id is not None:
            where.append("p.store_id = ?")
            params.append(self.store_id)
        keyword = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        sql = """SELECT p.id, p.name, COALESCE(p.title, ''), p.image_data, COALESCE(lc.name, '')
                 FROM products p
                 LEFT JOIN link_combinations lc ON lc.id = p.link_combo_id"""
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(p.sort_order, 0), p.id"
        rows = self.db.safe_fetchall(sql, tuple(params))
        terms = split_search_terms(keyword)
        for product_id, product_code, title, image_data, combo_name in rows:
            if terms and not any_terms_match(terms, product_code, title):
                continue
            row = self.model.rowCount()
            self.model.insertRow(row)
            self.model.setItem(row, 0, self._make_image_item(image_data, product_id))
            self.model.setItem(row, 1, self._make_item(product_code, product_id))
            self.model.setItem(row, 2, self._make_item(title))
            self.model.setItem(row, 3, self._make_item(combo_name or "未分组"))
        self.table.resizeRowsToContents()

    def selected_product_ids(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        ids = []
        for row in rows:
            item = self.model.item(row, 1)
            product_id = item.data(Qt.UserRole) if item else None
            if product_id and product_id not in ids:
                ids.append(product_id)
        return ids


class LinkClassifyResultDialog(QDialog):
    """展示 AI 链接归类结果。"""

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = rows or []
        self.setWindowTitle("AI归类结果")
        self.resize(760, 520)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel(f"已归类 {len(self.rows)} 条链接")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["图片", "链接ID", "链接组合", "链接类型"])
        table = QTableView()
        table.setModel(self.model)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setWordWrap(True)
        table.setTextElideMode(Qt.ElideNone)
        table.setIconSize(QSize(58, 58))
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.setColumnWidth(0, 72)
        layout.addWidget(table)

        for image_data, code, combo_name, link_type in self.rows:
            row = self.model.rowCount()
            self.model.insertRow(row)
            self.model.setItem(row, 0, self._make_image_item(image_data))
            self.model.setItem(row, 1, self._make_item(code))
            self.model.setItem(row, 2, self._make_item(combo_name or "-"))
            self.model.setItem(row, 3, self._make_item(link_type or "-"))

        btns = QHBoxLayout()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _make_item(self, text):
        item = QStandardItem(str(text or ""))
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _make_image_item(self, image_data):
        item = QStandardItem("")
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        if image_data:
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(image_data)):
                item.setData(pixmap.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation), Qt.DecorationRole)
            else:
                item.setText("无图")
        else:
            item.setText("无图")
        return item


class LinkUnclassifiedClassifyDialog(QDialog):
    """查看当前店铺未加入链接组合的链接，并触发 AI 归类。"""

    def __init__(self, owner, store_id=None, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.db = owner.db
        self.store_id = store_id
        self.products = []
        self.setWindowTitle("未分类链接AI归类")
        self.resize(940, 680)
        self.init_ui()
        self.load_links()

    def init_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("当前筛选店铺下缺少链接组合或链接类型的链接")
        layout.addWidget(title)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索链接ID/标题:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入链接ID或标题关键字，空格分隔...")
        self.search_input.textChanged.connect(self.load_links)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["图片", "链接ID", "标题", "店铺", "规格数"])
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setIconSize(QSize(58, 58))
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 72)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.lbl_count = QLabel("共 0 条未完整归类链接")
        btn_classify = QPushButton("AI归类未分类链接")
        btn_classify.setStyleSheet("background-color: #17a2b8; color: white; font-weight: bold;")
        btn_classify.clicked.connect(self.classify_links)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_classify)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _make_item(self, text, user_data=None):
        item = QStandardItem(str(text or ""))
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        if user_data is not None:
            item.setData(user_data, Qt.UserRole)
        return item

    def load_links(self):
        self.model.setRowCount(0)
        self.products = self.owner.product_context_rows(only_unclassified=True, store_id=self.store_id)
        terms = split_search_terms(self.search_input.text())
        visible = []
        for product in self.products:
            if terms and not any_terms_match(terms, product.get("code"), product.get("title")):
                continue
            visible.append(product)
        for product in visible:
            row = self.model.rowCount()
            self.model.insertRow(row)
            self.model.setItem(row, 0, self.owner._make_product_image_item(product.get("image_data"), product.get("product_id")))
            self.model.setItem(row, 1, self._make_item(product.get("code"), product.get("product_id")))
            self.model.setItem(row, 2, self._make_item(product.get("title")))
            self.model.setItem(row, 3, self._make_item(product.get("store_name")))
            self.model.setItem(row, 4, self._make_item(len(product.get("specs") or [])))
        self.table.resizeRowsToContents()
        self.lbl_count.setText(f"共 {len(visible)} 条未完整归类链接")

    def visible_products(self):
        visible_ids = []
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 1)
            product_id = item.data(Qt.UserRole) if item else None
            if product_id:
                visible_ids.append(product_id)
        product_map = {product.get("product_id"): product for product in self.products}
        return [product_map[product_id] for product_id in visible_ids if product_id in product_map]

    def classify_links(self):
        products = self.visible_products()
        if not products:
            QMessageBox.information(self, "提示", "当前没有可归类的未完整归类链接。")
            return
        updated = self.owner.classify_products_with_ai(products, self)
        if updated:
            self.load_links()


class LinkCombinationDialog(QDialog):
    """按成本库商品类型查看和维护链接类型。"""
    NO_LINK_TYPE_COMBO_ID = "__no_link_type__"
    NO_LINK_TYPE_COMBO_NAME = "未分类链接类型"

    class ComboPickerDialog(QDialog):
        def __init__(self, options, parent=None):
            super().__init__(parent)
            self.options = options
            self.selected_combo_id = None
            self.setWindowTitle("移动到其他组合")
            self.resize(560, 420)
            layout = QVBoxLayout(self)
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("搜索组合名称...")
            self.search_input.textChanged.connect(self.refresh)
            layout.addWidget(self.search_input)
            self.model = QStandardItemModel()
            self.model.setHorizontalHeaderLabels(["组合名称"])
            self.table = QTableView()
            self.table.setModel(self.model)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.doubleClicked.connect(self.accept)
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            layout.addWidget(self.table)
            buttons = QHBoxLayout()
            buttons.addStretch()
            ok_btn = QPushButton("确认")
            ok_btn.clicked.connect(self.accept)
            cancel_btn = QPushButton("取消")
            cancel_btn.clicked.connect(self.reject)
            buttons.addWidget(ok_btn)
            buttons.addWidget(cancel_btn)
            layout.addLayout(buttons)
            self.refresh()

        def refresh(self):
            self.model.setRowCount(0)
            terms = split_search_terms(self.search_input.text())
            for name, combo_id in self.options:
                if terms and not any_terms_match(terms, name):
                    continue
                row = self.model.rowCount()
                self.model.insertRow(row)
                item = QStandardItem(str(name or ""))
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                item.setData(combo_id, Qt.UserRole)
                self.model.setItem(row, 0, item)
            if self.model.rowCount():
                self.table.selectRow(0)

        def accept(self):
            index = self.table.currentIndex()
            if index.isValid():
                item = self.model.item(index.row(), 0)
                self.selected_combo_id = item.data(Qt.UserRole) if item else None
            super().accept()

    def __init__(self, db_manager, main_window=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.main_window = main_window
        self.current_combo_id = None
        self._pending_focus_product_code = ""
        self._loading_links = False
        self.setWindowTitle("链接商品类型")
        self.resize(1050, 620)
        self.init_ui()
        self.load_combos()

    def init_ui(self):
        layout = QVBoxLayout(self)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选店铺:"))
        self.store_filter_combo = QComboBox()
        self.store_filter_combo.addItem("全部店铺", None)
        for store_id, store_name in self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order, id"):
            self.store_filter_combo.addItem(str(store_name or f"店铺{store_id}"), store_id)
        self.store_filter_combo.currentIndexChanged.connect(self.on_store_filter_changed)
        filter_layout.addWidget(self.store_filter_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.addWidget(QLabel("商品类型"))
        combo_search_layout = QHBoxLayout()
        combo_search_layout.addWidget(QLabel("搜索:"))
        self.combo_search_input = QLineEdit()
        self.combo_search_input.setPlaceholderText("输入商品ID、标题、链接类型或商品类型")
        self.combo_search_input.textChanged.connect(self.load_combos)
        combo_search_layout.addWidget(self.combo_search_input)
        left.addLayout(combo_search_layout)
        self.combo_model = QStandardItemModel()
        self.combo_model.setHorizontalHeaderLabels(["商品类型", "链接数"])
        self.combo_table = QTableView()
        self.combo_table.setModel(self.combo_model)
        self.combo_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.combo_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.combo_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.combo_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.combo_table.clicked.connect(self.on_combo_clicked)
        self.combo_table.customContextMenuRequested.connect(self.show_combo_context_menu)
        self.combo_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.combo_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        left.addWidget(self.combo_table)
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.addWidget(QLabel("商品类型内链接"))
        link_search_layout = QHBoxLayout()
        link_search_layout.addWidget(QLabel("搜索:"))
        self.link_search_input = QLineEdit()
        self.link_search_input.setPlaceholderText("输入商品ID/标题/链接类型；无链接类型可输入“无链接类型”")
        self.link_search_input.textChanged.connect(lambda: self.load_links(self.current_combo_id))
        link_search_layout.addWidget(self.link_search_input)
        right.addLayout(link_search_layout)
        self.link_model = QStandardItemModel()
        self.link_model.setHorizontalHeaderLabels(["图片", "链接ID", "标题", "链接类型", "店铺", "规格数"])
        self.link_model.itemChanged.connect(self.on_link_item_changed)
        self.link_table = QTableView()
        self.link_table.setModel(self.link_model)
        self.link_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.link_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.link_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.link_table.setWordWrap(True)
        self.link_table.setTextElideMode(Qt.ElideNone)
        self.link_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.link_table.verticalHeader().setDefaultSectionSize(72)
        self.link_table.setIconSize(QSize(58, 58))
        self.link_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.link_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.link_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.link_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.link_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.link_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.link_table.setColumnWidth(0, 72)
        right.addWidget(self.link_table)
        right_btns = QHBoxLayout()
        btn_ai_type = QPushButton("AI生成链接类型")
        btn_ai_type.clicked.connect(self.ai_set_selected_link_type)
        right_btns.addWidget(btn_ai_type)
        right_btns.addStretch()
        right.addLayout(right_btns)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([320, 730])
        layout.addWidget(splitter)

        bottom = QHBoxLayout()
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.load_combos)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom.addStretch()
        bottom.addWidget(btn_refresh)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def _make_item(self, text, editable=False, user_data=None):
        item = QStandardItem(str(text or ""))
        item.setEditable(editable)
        item.setTextAlignment(Qt.AlignCenter)
        if user_data is not None:
            item.setData(user_data, Qt.UserRole)
        return item

    def _make_product_image_item(self, image_data, user_data=None):
        item = QStandardItem("")
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        if user_data is not None:
            item.setData(user_data, Qt.UserRole)
        if image_data:
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(image_data)):
                item.setData(pixmap.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation), Qt.DecorationRole)
            else:
                item.setText("无图")
        else:
            item.setText("无图")
        return item

    def current_store_filter_id(self):
        return self.store_filter_combo.currentData() if hasattr(self, "store_filter_combo") else None

    def _is_no_link_type_combo(self, combo_id=None):
        return (self.current_combo_id if combo_id is None else combo_id) == self.NO_LINK_TYPE_COMBO_ID

    def _no_link_type_link_count(self, store_id=None, search_text=""):
        where = ["COALESCE(p.is_archived, 0) = 0", "COALESCE(p.link_type, '') = ''"]
        params = []
        if store_id is not None:
            where.append("p.store_id = ?")
            params.append(store_id)
        for term in split_search_terms(search_text):
            term = str(term or "").lower()
            if term in ("无链接类型", "没有链接类型", "空链接类型", "未设置链接类型"):
                continue
            where.append(
                "(LOWER(COALESCE(p.name, '')) LIKE ? "
                "OR LOWER(COALESCE(p.title, '')) LIKE ? "
                "OR LOWER(?) LIKE ?)"
            )
            params.extend([f"%{term}%", f"%{term}%", self.NO_LINK_TYPE_COMBO_NAME, f"%{term}%"])
        rows = self.db.safe_fetchall(
            f"SELECT COUNT(*) FROM products p WHERE {' AND '.join(where)}",
            tuple(params),
        )
        return int(rows[0][0] or 0) if rows else 0

    def on_store_filter_changed(self):
        self.load_combos()

    def load_combos(self):
        previous = self.current_combo_id
        self.combo_model.setRowCount(0)
        store_id = self.current_store_filter_id()
        if hasattr(self.db, "update_all_product_category_labels"):
            self.db.update_all_product_category_labels(store_id)
        where = ["COALESCE(p.is_archived, 0)=0"]
        params = []
        if store_id is not None:
            where.append("p.store_id=?")
            params.append(store_id)
        for term in split_search_terms(self.combo_search_input.text() if hasattr(self, "combo_search_input") else ""):
            where.append(
                "(LOWER(COALESCE(p.name, '')) LIKE ? OR LOWER(COALESCE(p.title, '')) LIKE ? "
                "OR LOWER(COALESCE(p.link_type, '')) LIKE ? OR LOWER(COALESCE(p.product_category_label, '')) LIKE ?)"
            )
            params.extend([f"%{str(term).lower()}%"] * 4)
        rows = self.db.safe_fetchall(
            f"""SELECT COALESCE(p.product_category_label, ''), COALESCE(cc.color, '#DDEBF7'),
                       COALESCE(cc.sort_order, 0), COUNT(p.id)
                FROM products p
                LEFT JOIN cost_categories cc ON cc.label=p.product_category_label
                WHERE {' AND '.join(where)}
                GROUP BY p.product_category_label, cc.color, cc.sort_order
                ORDER BY COALESCE(cc.sort_order, 0), p.product_category_label""",
            tuple(params),
        )
        select_row = 0
        for category_label, color, _sort_order, link_count in rows:
            category_key = str(category_label or "")
            name = category_key or "未分类商品类型"
            row = self.combo_model.rowCount()
            if category_key == previous:
                select_row = row
            self.combo_model.insertRow(row)
            category_item = self._make_item(name, user_data=category_key)
            category_item.setBackground(QColor(str(color or "#DDEBF7")))
            self.combo_model.setItem(row, 0, category_item)
            self.combo_model.setItem(row, 1, self._make_item(int(link_count or 0)))
        if self.combo_model.rowCount():
            select_row = min(select_row, self.combo_model.rowCount() - 1)
            self.combo_table.selectRow(select_row)
            self.current_combo_id = self.combo_model.item(select_row, 0).data(Qt.UserRole)
            self.load_links(self.current_combo_id)
        else:
            self.current_combo_id = None
            self.link_model.setRowCount(0)

    def on_combo_clicked(self, index):
        if not index.isValid():
            return
        item = self.combo_model.item(index.row(), 0)
        self.current_combo_id = item.data(Qt.UserRole) if item else None
        self.load_links(self.current_combo_id)

    def show_combo_context_menu(self, pos):
        return

    def load_links(self, combo_id):
        self._loading_links = True
        self.link_model.setRowCount(0)
        if combo_id is None:
            self._loading_links = False
            return
        store_id = self.current_store_filter_id()
        store_clause = " AND p.store_id = ?" if store_id is not None else ""
        params = [combo_id]
        if store_id is not None:
            params.append(store_id)
        terms = split_search_terms(self.link_search_input.text() if hasattr(self, "link_search_input") else "")
        search_clause = ""
        for term in terms:
            term = str(term).lower()
            if term in ("无链接类型", "没有链接类型", "空链接类型", "未设置链接类型"):
                search_clause += " AND COALESCE(p.link_type, '') = ''"
            else:
                search_clause += (
                    " AND (LOWER(COALESCE(p.name, '')) LIKE ? "
                    "OR LOWER(COALESCE(p.title, '')) LIKE ? "
                    "OR LOWER(COALESCE(p.link_type, '')) LIKE ?)"
                )
                params.extend([f"%{term}%"] * 3)
        rows = self.db.safe_fetchall(
            f"""SELECT p.id, p.name, COALESCE(p.title, ''), COALESCE(p.link_type, ''),
                      p.image_data,
                      COALESCE(s.name, ''), COUNT(ps.id) AS spec_count
               FROM products p
                LEFT JOIN stores s ON s.id = p.store_id
                LEFT JOIN product_specs ps ON ps.product_id = p.id
                WHERE COALESCE(p.product_category_label, '') = ?
                AND COALESCE(p.is_archived, 0) = 0
                {store_clause}
                {search_clause}
                GROUP BY p.id, p.name, p.title, p.link_type, p.image_data, s.name, p.sort_order
                ORDER BY COALESCE(p.sort_order, 0), p.id""",
            tuple(params),
        )
        for product_db_id, product_code, title, link_type, image_data, store_name, spec_count in rows:
            row = self.link_model.rowCount()
            self.link_model.insertRow(row)
            self.link_model.setItem(row, 0, self._make_product_image_item(image_data, user_data=product_db_id))
            self.link_model.setItem(row, 1, self._make_item(product_code, user_data=product_db_id))
            self.link_model.setItem(row, 2, self._make_item(title))
            self.link_model.setItem(row, 3, self._make_item(link_type, editable=True))
            self.link_model.setItem(row, 4, self._make_item(store_name))
            self.link_model.setItem(row, 5, self._make_item(int(spec_count or 0)))
        self.link_table.resizeRowsToContents()
        self._select_pending_product_code()
        self._loading_links = False

    def on_link_item_changed(self, item):
        if self._loading_links or not item or item.column() != 3:
            return
        id_item = self.link_model.item(item.row(), 1)
        product_id = id_item.data(Qt.UserRole) if id_item else None
        if not product_id:
            return
        try:
            self.db.update_product_link_type(product_id, item.text().strip())
            if self.main_window and hasattr(self.main_window, "refresh_external_products"):
                self.main_window.refresh_external_products([product_id])
            QToolTip.showText(QCursor.pos(), "已自动保存")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def focus_product(self, product_code):
        code = str(product_code or "").strip()
        if not code:
            return
        self._pending_focus_product_code = code
        self.combo_search_input.setText(code)
        self.load_combos()
        if self.current_combo_id is not None:
            self.link_search_input.setText(code)
            self.load_links(self.current_combo_id)
        self._select_pending_product_code()

    def _select_pending_product_code(self):
        code = str(getattr(self, "_pending_focus_product_code", "") or "").strip()
        if not code:
            return False
        for row in range(self.link_model.rowCount()):
            item = self.link_model.item(row, 1)
            if item and item.text().strip() == code:
                index = self.link_model.index(row, 1)
                self.link_table.selectRow(row)
                self.link_table.scrollTo(index, QAbstractItemView.PositionAtCenter)
                self.link_table.setFocus(Qt.OtherFocusReason)
                return True
        return False

    def add_combo(self):
        name, ok = QInputDialog.getText(self, "新增链接组合", "请输入链接组合名称:")
        if not ok or not name.strip():
            return
        try:
            self.db.ensure_link_combination(name.strip())
            self.load_combos()
        except Exception as e:
            QMessageBox.warning(self, "新增失败", str(e))

    def _current_combo_name(self):
        row = self.combo_table.currentIndex().row()
        item = self.combo_model.item(row, 0) if row >= 0 else None
        return item.text().strip() if item else ""

    def _selected_combo_rows(self):
        return sorted({index.row() for index in self.combo_table.selectedIndexes()})

    def _selected_combo_ids_and_names(self):
        combos = []
        for row in self._selected_combo_rows():
            item = self.combo_model.item(row, 0)
            if not item:
                continue
            combo_id = item.data(Qt.UserRole)
            name = item.text().strip()
            if combo_id is not None and all(existing_id != combo_id for existing_id, _name in combos):
                combos.append((combo_id, name))
        return combos

    def delete_selected_combos(self):
        combos = self._selected_combo_ids_and_names()
        if not combos and self.current_combo_id is not None:
            combos = [(self.current_combo_id, self._current_combo_name())]
        combos = [(combo_id, name) for combo_id, name in combos if not self._is_no_link_type_combo(combo_id)]
        if not combos:
            QMessageBox.warning(self, "提示", "未分类链接类型是临时分组，不能删除。")
            return
        names = [name or str(combo_id) for combo_id, name in combos]
        reply = QMessageBox.question(
            self,
            "确认删除链接组合",
            "确定要删除选中的 {} 个链接组合吗？\n\n{}\n\n组合内链接不会被删除，只会解除链接组合归属。".format(
                len(combos),
                "\n".join(f"- {name}" for name in names[:12]) + ("\n..." if len(names) > 12 else ""),
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if hasattr(self.db, "delete_link_combinations"):
                self.db.delete_link_combinations([combo_id for combo_id, _name in combos])
            else:
                raise RuntimeError("当前数据库管理器不支持删除链接组合。")
        except Exception as e:
            QMessageBox.critical(self, "删除失败", f"删除链接组合失败：{e}")
            return
        self.current_combo_id = None
        self.load_combos()

    def rename_combo(self):
        if self.current_combo_id is None:
            QMessageBox.warning(self, "提示", "请先选择链接组合。")
            return
        if self._is_no_link_type_combo():
            QMessageBox.warning(self, "提示", "未分类链接类型是临时分组，不能重命名。")
            return
        name, ok = QInputDialog.getText(self, "重命名链接组合", "请输入新的链接组合名称:", text=self._current_combo_name())
        if not ok or not name.strip():
            return
        if hasattr(self.db, "rename_link_combination") and self.db.rename_link_combination(self.current_combo_id, name.strip()):
            self.load_combos()
        else:
            QMessageBox.warning(self, "重命名失败", "链接组合名称可能已存在。")

    def _selected_product_ids(self):
        rows = sorted({index.row() for index in self.link_table.selectedIndexes()})
        ids = []
        for row in rows:
            item = self.link_model.item(row, 1)
            product_id = item.data(Qt.UserRole) if item else None
            if product_id and product_id not in ids:
                ids.append(product_id)
        return ids

    def move_selected_links(self):
        product_ids = self._selected_product_ids()
        if not product_ids:
            QMessageBox.warning(self, "提示", "请先选择要移动的链接。")
            return
        rows = self.db.get_link_combinations_with_counts() if hasattr(self.db, "get_link_combinations_with_counts") else []
        options = [(name, combo_id) for combo_id, name, _sort_order, _count in rows if combo_id != self.current_combo_id]
        if not options:
            QMessageBox.warning(self, "提示", "没有其他链接组合可移动。")
            return
        dialog = self.ComboPickerDialog(options, self)
        if dialog.exec_() != QDialog.Accepted or dialog.selected_combo_id is None:
            return
        for product_id in product_ids:
            if hasattr(self.db, "update_product_link_combo"):
                self.db.update_product_link_combo(product_id, dialog.selected_combo_id)
        self.load_combos()

    def add_links_to_current_combo(self):
        if self.current_combo_id is None:
            QMessageBox.warning(self, "提示", "请先选择一个链接组合。")
            return
        if self._is_no_link_type_combo():
            QMessageBox.warning(self, "提示", "未分类链接类型是临时分组，不能添加链接。请移动到真实组合或先填写链接类型。")
            return
        dialog = LinkAddToCombinationDialog(self.db, self.current_combo_id, self.current_store_filter_id(), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        product_ids = dialog.selected_product_ids()
        if not product_ids:
            QMessageBox.warning(self, "提示", "请先选择要添加的链接。")
            return
        try:
            for product_id in product_ids:
                if hasattr(self.db, "update_product_link_combo"):
                    self.db.update_product_link_combo(product_id, self.current_combo_id)
        except Exception as e:
            QMessageBox.critical(self, "添加失败", f"添加链接失败：{e}")
            return
        self.load_combos()

    def show_unclassified_classify_dialog(self):
        dialog = LinkUnclassifiedClassifyDialog(self, self.current_store_filter_id(), self)
        dialog.exec_()
        self.load_combos()

    def product_context_rows(self, only_unclassified=False, store_id=None):
        params = []
        where = ["COALESCE(p.is_archived, 0) = 0"]
        if store_id is not None:
            where.append("p.store_id=?")
            params.append(store_id)
        if only_unclassified:
            where.append("(p.link_combo_id IS NULL OR COALESCE(p.link_type, '') = '')")
        sql = """SELECT p.id, p.name, COALESCE(p.title, ''), COALESCE(p.link_type, ''),
                        COALESCE(lc.name, ''), COALESCE(s.name, ''), p.image_data,
                        COALESCE(ps.spec_name, ''), COALESCE(ps.spec_code, ''), COALESCE(cl.category_label, '')
                 FROM products p
                 LEFT JOIN stores s ON s.id = p.store_id
                 LEFT JOIN link_combinations lc ON lc.id = p.link_combo_id
                 LEFT JOIN product_specs ps ON ps.product_id = p.id
                 LEFT JOIN cost_library cl ON cl.spec_code = ps.spec_code"""
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(p.sort_order, 0), p.id, ps.id"
        rows = self.db.safe_fetchall(sql, tuple(params))
        products = {}
        order = []
        for product_id, code, title, link_type, combo_name, store_name, image_data, spec_name, spec_code, category in rows:
            if product_id not in products:
                products[product_id] = {
                    "product_id": product_id,
                    "code": str(code or ""),
                    "title": str(title or ""),
                    "link_type": str(link_type or ""),
                    "combo_name": str(combo_name or ""),
                    "store_name": str(store_name or ""),
                    "image_data": image_data,
                    "specs": [],
                }
                order.append(product_id)
            if spec_name or spec_code or category:
                products[product_id]["specs"].append({
                    "name": str(spec_name or ""),
                    "code": str(spec_code or ""),
                    "category": str(category or ""),
                })
        return [products[product_id] for product_id in order]

    def classify_products_with_ai(self, products, message_parent=None):
        if not products:
            QMessageBox.information(self, "提示", "当前筛选范围内没有链接。")
            return 0
        message_parent = message_parent or self
        try:
            results = self._call_ai_classify_links(products)
            if not results:
                raise RuntimeError("AI没有返回可识别的归类结果。")
            product_map = {idx: item for idx, item in enumerate(products, start=1)}
            updated = 0
            updated_ids = []
            updated_details = []
            for result in results:
                try:
                    row_index = int(result.get("row_index") or result.get("rowIndex") or result.get("index") or 0)
                except (TypeError, ValueError):
                    row_index = 0
                product = product_map.get(row_index)
                if not product:
                    continue
                combo_name = str(result.get("combo_name") or result.get("combo") or result.get("name") or "").strip()
                link_type = str(result.get("link_type") or result.get("type") or "").strip()
                if not combo_name:
                    continue
                combo_id = self.db.ensure_link_combination(combo_name) if hasattr(self.db, "ensure_link_combination") else None
                self.db.cursor.execute(
                    "UPDATE products SET link_combo_id=?, link_type=? WHERE id=?",
                    (combo_id, link_type or product.get("link_type", ""), product["product_id"]),
                )
                updated += 1
                updated_ids.append(product["product_id"])
                final_type = link_type or product.get("link_type", "")
                updated_details.append((product.get("image_data"), product.get("code", ""), combo_name, final_type))
            self.db.conn.commit()
        except Exception as e:
            try:
                self.db.conn.rollback()
            except Exception:
                pass
            QMessageBox.warning(message_parent, "AI归类失败", str(e))
            return 0
        if updated_details:
            dialog = LinkClassifyResultDialog(updated_details, message_parent)
            dialog.exec_()
        else:
            QMessageBox.information(message_parent, "成功", "AI返回了结果，但没有匹配到可更新的链接。")
        if updated_ids and self.main_window and hasattr(self.main_window, "refresh_external_products"):
            self.main_window.refresh_external_products(updated_ids)
        self.load_combos()
        return updated

    def _call_ai_classify_links(self, products):
        api_key = self.db.get_setting("ai_api_key", "") if hasattr(self.db, "get_setting") else ""
        if not api_key:
            raise RuntimeError("未配置 API Key，请先到 API 配置里填写。")
        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        existing_types = self._existing_link_types()
        existing_combos = self._existing_combo_names()
        candidates = []
        for idx, product in enumerate(products, start=1):
            candidates.append({
                "row_index": idx,
                "link_id": product["code"],
                "title": product["title"],
                "current_link_type": product["link_type"],
                "current_combo_name": product["combo_name"],
                "specs": [
                    {"name": spec["name"], "category": spec["category"]}
                    for spec in product.get("specs", [])
                ],
            })
        prompt = (
            "请根据链接标题和规格产品，把每个链接归类到链接组合名称和链接类型。"
            "同一用途/人群/场景/成套搭配的链接归到同一个组合名称。"
            "链接类型优先从现有链接类型中选择，确实不合适再生成新的短类型。"
            "组合名称可以复用已有组合名称，也可以生成新的组合名称。"
            "必须返回标准JSON数组，每个对象只包含 row_index、combo_name、link_type。"
            "不要解释，不要代码块。\n\n"
            f"现有链接类型：{json.dumps(existing_types, ensure_ascii=False)}\n"
            f"已有链接组合名称：{json.dumps(existing_combos, ensure_ascii=False)}\n"
            f"链接列表：{json.dumps(candidates, ensure_ascii=False)}"
        )
        progress = QProgressDialog("正在调用 AI 归类链接...", "取消", 0, 2, self)
        progress.setWindowTitle("AI归类")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            import requests
            response = requests.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是电商链接归类助手。只输出标准JSON数组，不要解释。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": max(2048, min(16000, len(products) * 80)),
                },
                timeout=120,
            )
            if progress.wasCanceled():
                raise RuntimeError("已取消 AI 归类。")
            if response.status_code != 200:
                raise RuntimeError(f"AI请求失败：HTTP {response.status_code}\n{response.text[:500]}")
            progress.setLabelText("正在解析 AI 归类结果...")
            progress.setValue(1)
            QApplication.processEvents()
            data = response.json()
            message = data.get("choices", [{}])[0].get("message", {})
            content = str(message.get("content") or message.get("reasoning_content") or "").strip()
            if not content:
                raise RuntimeError(f"AI返回内容为空。API URL:{api_url}\n模型:{model}\n返回内容:{str(data)[:500]}")
            return self._parse_ai_classify_result(content)
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()

    def _parse_ai_classify_result(self, text):
        text = str(text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
        start = text.find("[")
        end = text.rfind("]")
        json_text = text[start:end + 1] if start != -1 and end > start else text
        for candidate in (json_text, json_text.replace("'", '"')):
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    data = data.get("items") or data.get("results") or data.get("data") or []
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
            except json.JSONDecodeError:
                continue
        results = []
        pattern = re.compile(
            r"row[_\s-]*index[\"'\s:=：]+(\d+).*?(?:combo[_\s-]*name|组合名称|name)[\"'\s:=：]+([^,，\n;；}]+).*?(?:link[_\s-]*type|链接类型|type)[\"'\s:=：]+([^,，\n;；}]+)",
            flags=re.I | re.S,
        )
        for row_index, combo_name, link_type in pattern.findall(text):
            results.append({
                "row_index": int(row_index),
                "combo_name": str(combo_name).strip().strip("\"'“”"),
                "link_type": str(link_type).strip().strip("\"'“”"),
            })
        return results

    def _spec_context_for_products(self, product_ids):
        if not product_ids:
            return ""
        placeholders = ",".join(["?"] * len(product_ids))
        rows = self.db.safe_fetchall(
            f"""SELECT p.name, COALESCE(p.title, ''), ps.spec_name, COALESCE(ps.spec_code, ''), COALESCE(cl.category_label, '')
                FROM products p
                LEFT JOIN product_specs ps ON ps.product_id = p.id
                LEFT JOIN cost_library cl ON cl.spec_code = ps.spec_code
                WHERE p.id IN ({placeholders})
                ORDER BY p.id, ps.id""",
            tuple(product_ids),
        )
        return "\n".join(
            f"链接ID:{pid}; 标题:{title}; 商品:{spec_name}; 规格编码:{spec_code}; 商品类型:{category}"
            for pid, title, spec_name, spec_code, category in rows
        )

    def _existing_link_types(self):
        rows = self.db.safe_fetchall(
            "SELECT DISTINCT link_type FROM products WHERE COALESCE(link_type, '') <> '' ORDER BY link_type"
        )
        return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]

    def _call_ai_text(self, prompt, context):
        api_key = self.db.get_setting("ai_api_key", "") if hasattr(self.db, "get_setting") else ""
        if not api_key:
            raise RuntimeError("未配置 API Key，请先到 API 配置里填写。")
        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        existing_types = self._existing_link_types()
        reference = "现有链接类型:\n" + ("\n".join(f"- {item}" for item in existing_types) or "无")
        format_rule = (
            "先从现有链接类型中选择最符合的一个；没有符合的再生成新的。"
            "必须只返回 JSON 对象，字段名为 link_type，不要解释，不要代码块。"
        )
        import requests
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是电商链接分类助手。只输出一个 JSON 对象，不要解释，不要代码块，不要推理过程。"},
                    {"role": "user", "content": f"{format_rule}\n\n原任务:{prompt}\n\n{reference}\n\n商品信息:\n{context}"},
                ],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(f"AI请求失败：HTTP {response.status_code}\n{response.text[:300]}")
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        content = str(message.get("content") or "").strip()
        if not content:
            raise RuntimeError(f"AI返回内容为空。API URL: {api_url}\n模型:{model}\n返回内容:{str(data)[:500]}")
        value = _clean_ai_short_value(content, "link_type", existing_types, 40)
        if not value:
            raise RuntimeError(f"AI返回内容无法识别。返回内容:{content[:300]}")
        return value

    def ai_set_selected_link_type(self):
        product_ids = self._selected_product_ids()
        if not product_ids:
            QMessageBox.warning(self, "提示", "请先选择一条链接。")
            return
        try:
            link_type = self._call_ai_text("根据这些规格生成这条链接自己的链接类型。只输出一个短类型名，12个中文以内。", self._spec_context_for_products(product_ids))
            selected_rows = sorted({index.row() for index in self.link_table.selectedIndexes()})
            for row in selected_rows:
                item = self.link_model.item(row, 3)
                if item:
                    item.setText(link_type)
        except Exception as e:
            QMessageBox.warning(self, "AI生成失败", str(e))


class ShippingRuleDialog(QDialog):
    """设置成本库详细成本模式的快递费规则。"""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self._loading = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(lambda: self.save_rules(auto_save=True))
        self.setWindowTitle("快递费设置")
        self.resize(720, 460)
        self.init_ui()
        self.load_rules()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("重量单位：kg。按区间匹配，超过规则使用续重公式。"))
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["起始重量kg", "结束重量kg", "费用"])
        self.model.itemChanged.connect(self._schedule_save)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        range_btns = QHBoxLayout()
        btn_add = QPushButton("添加区间")
        btn_add.clicked.connect(self.add_range)
        btn_delete = QPushButton("删除区间")
        btn_delete.clicked.connect(self.delete_selected_range)
        range_btns.addWidget(btn_add)
        range_btns.addWidget(btn_delete)
        range_btns.addStretch()
        layout.addLayout(range_btns)

        over_layout = QHBoxLayout()
        self.over_threshold = QLineEdit()
        self.over_base_fee = QLineEdit()
        self.over_deduct_weight = QLineEdit()
        self.over_step_weight = QLineEdit()
        self.over_step_fee = QLineEdit()
        for label, widget in [
            ("超过kg", self.over_threshold),
            ("基础费", self.over_base_fee),
            ("扣减kg", self.over_deduct_weight),
            ("续重单位kg", self.over_step_weight),
            ("每续重费用", self.over_step_fee),
        ]:
            over_layout.addWidget(QLabel(label))
            widget.setFixedWidth(72)
            widget.editingFinished.connect(self._schedule_save)
            over_layout.addWidget(widget)
        layout.addLayout(over_layout)

        btn_layout = QHBoxLayout()
        btn_default = QPushButton("恢复默认")
        btn_default.clicked.connect(self.load_default_rules)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_default)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _make_item(self, value):
        item = QStandardItem("" if value is None else str(value))
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def load_default_rules(self):
        rules = getattr(self.db, "DEFAULT_COST_SHIPPING_RULES", None) or {
            "ranges": [
                {"min": 0, "max": 0.5, "fee": 1.7},
                {"min": 0.5, "max": 1, "fee": 1.9},
                {"min": 1, "max": 2, "fee": 2.9},
                {"min": 2, "max": 3, "fee": 3.2},
            ],
            "over": {"threshold": 3, "base_fee": 2.5, "deduct_weight": 1, "step_weight": 1, "step_fee": 1},
        }
        self._apply_rules(rules)
        self._schedule_save()

    def load_rules(self):
        self._apply_rules(self.db.get_cost_shipping_rules() if hasattr(self.db, "get_cost_shipping_rules") else {})

    def _apply_rules(self, rules):
        self._loading = True
        self.model.setRowCount(0)
        for rule in rules.get("ranges", []):
            self.add_range(rule.get("min", ""), rule.get("max", ""), rule.get("fee", ""))
        over = rules.get("over", {})
        self.over_threshold.setText(str(over.get("threshold", 3)))
        self.over_base_fee.setText(str(over.get("base_fee", 2.5)))
        self.over_deduct_weight.setText(str(over.get("deduct_weight", 1)))
        self.over_step_weight.setText(str(over.get("step_weight", 1)))
        self.over_step_fee.setText(str(over.get("step_fee", 1)))
        self._loading = False

    def add_range(self, min_weight="", max_weight="", fee=""):
        row = self.model.rowCount()
        self.model.insertRow(row)
        self.model.setItem(row, 0, self._make_item(min_weight))
        self.model.setItem(row, 1, self._make_item(max_weight))
        self.model.setItem(row, 2, self._make_item(fee))
        if not self._loading:
            self._schedule_save()

    def delete_selected_range(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.model.removeRow(row)
        self._schedule_save()

    def _schedule_save(self, *_args):
        if not self._loading:
            self._save_timer.start(350)

    def _parse_non_negative(self, text, field):
        try:
            value = float(str(text).strip())
        except ValueError:
            raise ValueError(f"{field} 必须是数字")
        if value < 0:
            raise ValueError(f"{field} 不能小于 0")
        return value

    def save_rules(self, auto_save=False):
        try:
            ranges = []
            for row in range(self.model.rowCount()):
                min_value = self._parse_non_negative(self.model.item(row, 0).text(), "起始重量")
                max_value = self._parse_non_negative(self.model.item(row, 1).text(), "结束重量")
                fee = self._parse_non_negative(self.model.item(row, 2).text(), "费用")
                if max_value <= min_value:
                    raise ValueError(f"第 {row + 1} 行结束重量必须大于起始重量")
                ranges.append({"min": min_value, "max": max_value, "fee": fee})
            if not ranges:
                raise ValueError("至少需要一条重量区间")
            over = {
                "threshold": self._parse_non_negative(self.over_threshold.text(), "超过重量"),
                "base_fee": self._parse_non_negative(self.over_base_fee.text(), "基础费"),
                "deduct_weight": self._parse_non_negative(self.over_deduct_weight.text(), "扣减重量"),
                "step_weight": self._parse_non_negative(self.over_step_weight.text(), "续重单位"),
                "step_fee": self._parse_non_negative(self.over_step_fee.text(), "每续重费用"),
            }
            if over["step_weight"] <= 0:
                raise ValueError("续重单位必须大于 0")
        except ValueError as e:
            if not auto_save:
                QMessageBox.warning(self, "格式错误", str(e))
            return

        if hasattr(self.db, "set_cost_shipping_rules"):
            self.db.set_cost_shipping_rules({"ranges": ranges, "over": over})
        parent = self.parent()
        if parent and hasattr(parent, "_refresh_detail_costs_after_settings"):
            parent._refresh_detail_costs_after_settings(show_message=False)
        QToolTip.showText(QCursor.pos(), "快递费规则已自动保存")


class MiscFeeDialog(QDialog):
    """设置成本库详细成本模式的全局杂费。"""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("杂费设置")
        self.resize(360, 130)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("每个规格固定杂费:"))
        self.input_fee = QLineEdit(f"{self.db.get_cost_misc_fee():.2f}" if hasattr(self.db, "get_cost_misc_fee") else "0")
        self.input_fee.editingFinished.connect(lambda: self.save_fee(auto_save=True))
        row.addWidget(self.input_fee)
        layout.addLayout(row)
        btns = QHBoxLayout()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btns.addStretch()
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def save_fee(self, auto_save=False):
        try:
            value = float(self.input_fee.text().strip() or 0)
            if value < 0:
                raise ValueError
        except ValueError:
            if not auto_save:
                QMessageBox.warning(self, "格式错误", "杂费必须是大于等于 0 的数字。")
            return
        if hasattr(self.db, "set_cost_misc_fee"):
            self.db.set_cost_misc_fee(value)
        parent = self.parent()
        if parent and hasattr(parent, "_refresh_detail_costs_after_settings"):
            parent._refresh_detail_costs_after_settings(show_message=False)
        QToolTip.showText(QCursor.pos(), "杂费已自动保存")


class CostPriceTestDialog(QDialog):
    """临时测试详细成本规格的多件折扣毛利。"""

    CAND_COL_NAME = 0
    CAND_COL_CODE = 1
    CAND_COL_QUANTITY = 2
    CAND_COL_COST = 3

    PICK_COL_NAME = 0
    PICK_COL_CODE = 1
    PICK_COL_QUANTITY = 2
    PICK_COL_PRODUCT_COST = 3
    PICK_COL_WEIGHT = 4
    PICK_COL_SHIPPING = 5
    PICK_COL_BASE_TOTAL = 6
    PICK_COL_SINGLE_PRICE = 7

    TEST_COL_NAME = 0
    TEST_COL_WEIGHT = 1
    TEST_COL_SHIPPING = 2
    TEST_COL_BUY_COUNT = 3
    TEST_COL_TOTAL_COST = 4
    TEST_COL_SINGLE_PRICE = 5
    TEST_COL_DISCOUNT = 6
    TEST_COL_DISCOUNT_UNIT_PRICE = 7
    TEST_COL_RECEIPT = 8
    TEST_COL_PROFIT = 9
    TEST_COL_MARGIN = 10

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self._recalculating = False
        self.setWindowTitle("测价")
        self.resize(1280, 720)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        tip = QLabel("仅测试详细成本模式规格。购买件数、多件折扣、单件售价为临时输入，不保存到数据库。")
        tip.setStyleSheet("color: #666;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        candidate_area = QHBoxLayout()
        search_panel = QWidget()
        search_panel_layout = QVBoxLayout(search_panel)
        search_panel_layout.setContentsMargins(0, 0, 0, 0)
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索规格编码/商品名称:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入规格编码或商品名称关键字，空格分隔...")
        self.search_input.textChanged.connect(self.load_candidates)
        btn_add = QPushButton("加入测价候选区")
        btn_add.clicked.connect(self.add_selected_candidates)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_add)
        search_panel_layout.addLayout(search_layout)

        pick_panel = QWidget()
        pick_panel_layout = QVBoxLayout(pick_panel)
        pick_panel_layout.setContentsMargins(0, 0, 0, 0)
        option_layout = QHBoxLayout()
        option_layout.addWidget(QLabel("统一多件折扣:"))
        self.default_discount_input = QLineEdit("8")
        self.default_discount_input.setPlaceholderText("8 / 8折 / 0.8 / 80%")
        self.default_discount_input.setFixedWidth(140)
        option_layout.addWidget(self.default_discount_input)
        btn_generate = QPushButton("快速生成1-10件毛利率")
        btn_generate.clicked.connect(self.generate_selected_quantity_rows)
        option_layout.addWidget(btn_generate)
        btn_custom = QPushButton("新增自定义测价行")
        btn_custom.clicked.connect(self.generate_custom_rows)
        option_layout.addWidget(btn_custom)
        btn_remove_pick = QPushButton("移除候选规格")
        btn_remove_pick.clicked.connect(self.delete_selected_pick_rows)
        option_layout.addWidget(btn_remove_pick)
        option_layout.addStretch()
        pick_panel_layout.addLayout(option_layout)

        self.candidate_model = QStandardItemModel()
        self.candidate_model.setHorizontalHeaderLabels(["商品名称", "规格编码", "数量", "总成本"])
        self.candidate_table = QTableView()
        self.candidate_table.setModel(self.candidate_model)
        self.candidate_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.candidate_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.candidate_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.candidate_table.doubleClicked.connect(lambda _index: self.add_selected_candidates())
        self.candidate_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.candidate_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.candidate_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.candidate_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.candidate_table.setMinimumHeight(130)
        search_panel_layout.addWidget(QLabel("搜索候选区"))
        search_panel_layout.addWidget(self.candidate_table)

        self.pick_model = QStandardItemModel()
        self.pick_model.setHorizontalHeaderLabels([
            "商品名称", "规格编码", "数量", "产品成本", "单个重量kg", "快递费", "总成本", "单件售价",
        ])
        self.pick_table = QTableView()
        self.pick_table.setModel(self.pick_model)
        self.pick_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pick_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.pick_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.pick_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, self.PICK_COL_SINGLE_PRICE + 1):
            self.pick_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.pick_table.setMinimumHeight(120)
        pick_panel_layout.addWidget(QLabel("测价候选区（双击左侧规格加入；这里为每个规格单独填写单件售价）"))
        pick_panel_layout.addWidget(self.pick_table)
        candidate_area.addWidget(search_panel, 1)
        candidate_area.addWidget(pick_panel, 1)
        layout.addLayout(candidate_area)

        self.test_model = QStandardItemModel()
        self.test_model.setHorizontalHeaderLabels([
            "商品名称", "重量kg", "快递费", "购买件数", "总成本", "单件售价", "多件折扣",
            "折后单件价格", "实收总价（可填写）", "利润", "毛利率",
        ])
        self.test_model.itemChanged.connect(self.on_test_item_changed)
        self.test_table = QTableView()
        self.test_table.setModel(self.test_model)
        self.test_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.test_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.test_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.test_table.setWordWrap(True)
        self.test_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, self.TEST_COL_MARGIN + 1):
            self.test_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(self.test_table, 1)

        btn_layout = QHBoxLayout()
        self.count_label = QLabel("候选 0 条，测价 0 行")
        btn_duplicate = QPushButton("复制选中测价行")
        btn_duplicate.clicked.connect(self.duplicate_selected_test_rows)
        btn_delete = QPushButton("删除选中测价行")
        btn_delete.clicked.connect(self.delete_selected_test_rows)
        btn_clear_result = QPushButton("清空结果")
        btn_clear_result.clicked.connect(self.clear_test_rows)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.count_label)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_duplicate)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_clear_result)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        self.load_candidates()

    def _make_item(self, text, editable=False, user_data=None):
        item = QStandardItem(str(text if text is not None else ""))
        item.setEditable(editable)
        item.setTextAlignment(Qt.AlignCenter)
        if user_data is not None:
            item.setData(user_data, Qt.UserRole)
        return item

    def _price_test_column_color(self, col):
        if col == self.TEST_COL_NAME:
            return "#F5F5F5"
        if col in (self.TEST_COL_WEIGHT, self.TEST_COL_SHIPPING, self.TEST_COL_TOTAL_COST):
            return "#FFF2CC"
        if col in (self.TEST_COL_BUY_COUNT, self.TEST_COL_SINGLE_PRICE, self.TEST_COL_DISCOUNT):
            return "#DDEBF7"
        if col in (self.TEST_COL_DISCOUNT_UNIT_PRICE, self.TEST_COL_RECEIPT):
            return "#E2F0D9"
        if col == self.TEST_COL_PROFIT:
            return "#FCE4D6"
        if col == self.TEST_COL_MARGIN:
            return "#E4DFEC"
        return ""

    def _apply_price_test_item_style(self, item, col):
        color = self._price_test_column_color(col)
        if color:
            item.setBackground(QBrush(QColor(color)))
        if col in (self.TEST_COL_PROFIT, self.TEST_COL_MARGIN):
            font = item.font()
            font.setBold(True)
            item.setFont(font)

    def _parse_number(self, value, default=0.0):
        if hasattr(self.db, "parse_cost_number"):
            parsed = self.db.parse_cost_number(value, None)
            if parsed is not None:
                return float(parsed)
        match = re.search(r"-?\d+(?:\.\d+)?", str(value or "").replace(",", ""))
        return float(match.group(0)) if match else float(default)

    def _quantity_factor(self, quantity):
        if hasattr(self.db, "parse_cost_quantity_factor"):
            value = self.db.parse_cost_quantity_factor(quantity)
            return value if value and value > 0 else 1.0
        value = self._parse_number(quantity, 1.0)
        return value if value > 0 else 1.0

    def _discount_rate(self, value):
        text = str(value or "").strip().replace("%", "")
        if not text:
            return 1.0
        number = self._parse_number(text, 1.0)
        if number <= 0:
            return 1.0
        if number <= 1:
            return number
        if number <= 10:
            return number / 10.0
        return number / 100.0

    def load_candidates(self):
        self.candidate_model.setRowCount(0)
        terms = split_search_terms(self.search_input.text())
        where = ["COALESCE(cost_calc_mode, 'total') = 'detail'", "product_cost IS NOT NULL", "unit_weight IS NOT NULL"]
        rows = self.db.safe_fetchall(
            f"""SELECT spec_name, spec_code, COALESCE(quantity, ''), product_cost, unit_weight,
                       COALESCE(shipping_fee, 0), COALESCE(misc_fee, 0), COALESCE(cost_price, 0)
                FROM cost_library
                WHERE {' AND '.join(where)}
                ORDER BY CASE WHEN sort_order IS NULL THEN 1 ELSE 0 END, sort_order, spec_code
                LIMIT 1000""",
        )
        filtered_rows = []
        for spec_name, spec_code, quantity, product_cost, unit_weight, shipping_fee, misc_fee, cost_price in rows:
            search_text = self.search_input.text().strip()
            if terms:
                full_hit, hit_count = match_score(search_text, terms, spec_name, spec_code, quantity)
                if hit_count <= 0 and not full_hit:
                    continue
            else:
                full_hit, hit_count = 0, 0
            filtered_rows.append((full_hit, hit_count, spec_name, spec_code, quantity, product_cost, unit_weight, shipping_fee, misc_fee, cost_price))
        filtered_rows.sort(key=lambda item: (-item[0], -item[1], str(item[2] or ""), str(item[3] or "")))
        for _full_hit, _hit_count, spec_name, spec_code, quantity, product_cost, unit_weight, shipping_fee, misc_fee, cost_price in filtered_rows[:200]:
            spec = {
                "name": str(spec_name or ""),
                "code": str(spec_code or ""),
                "quantity": str(quantity or ""),
                "product_cost": float(product_cost or 0),
                "unit_weight": float(unit_weight or 0),
                "shipping_fee": float(shipping_fee or 0),
                "misc_fee": float(misc_fee or 0),
                "cost_price": float(cost_price or 0),
            }
            row = self.candidate_model.rowCount()
            self.candidate_model.insertRow(row)
            self.candidate_model.setItem(row, self.CAND_COL_NAME, self._make_item(spec["name"], user_data=spec))
            self.candidate_model.setItem(row, self.CAND_COL_CODE, self._make_item(spec["code"]))
            self.candidate_model.setItem(row, self.CAND_COL_QUANTITY, self._make_item(spec["quantity"]))
            self.candidate_model.setItem(row, self.CAND_COL_COST, self._make_item(f"{spec['cost_price']:.2f}"))
        self.update_count_label()

    def selected_candidate_specs(self):
        specs = []
        rows = sorted({index.row() for index in self.candidate_table.selectedIndexes()})
        for row in rows:
            item = self.candidate_model.item(row, self.CAND_COL_NAME)
            spec = item.data(Qt.UserRole) if item else None
            if spec:
                specs.append(spec)
        return specs

    def add_selected_candidates(self):
        specs = self.selected_candidate_specs()
        if not specs and self.candidate_model.rowCount() == 1:
            item = self.candidate_model.item(0, self.CAND_COL_NAME)
            spec = item.data(Qt.UserRole) if item else None
            specs = [spec] if spec else []
        if not specs:
            QMessageBox.information(self, "提示", "请先选择要测价的规格。")
            return
        for spec in specs:
            self.add_pick_row(spec)
        self.update_count_label()

    def add_pick_row(self, spec):
        for row in range(self.pick_model.rowCount()):
            item = self.pick_model.item(row, self.PICK_COL_CODE)
            if item and item.text().strip() == str(spec.get("code") or "").strip():
                self.pick_table.selectRow(row)
                return
        row = self.pick_model.rowCount()
        self.pick_model.insertRow(row)
        values = [
            spec["name"], spec["code"], spec["quantity"], f"{spec['product_cost']:.2f}",
            f"{spec['unit_weight']:.4f}".rstrip("0").rstrip("."), f"{spec['shipping_fee']:.2f}",
            f"{spec['cost_price']:.2f}", "",
        ]
        for col, value in enumerate(values):
            item = self._make_item(value, editable=(col == self.PICK_COL_SINGLE_PRICE), user_data=spec if col == self.PICK_COL_NAME else None)
            self.pick_model.setItem(row, col, item)

    def selected_pick_specs(self):
        rows = sorted({index.row() for index in self.pick_table.selectedIndexes()})
        if not rows:
            rows = list(range(self.pick_model.rowCount()))
        result = []
        for row in rows:
            item = self.pick_model.item(row, self.PICK_COL_NAME)
            spec = item.data(Qt.UserRole) if item else None
            if not spec:
                continue
            price_item = self.pick_model.item(row, self.PICK_COL_SINGLE_PRICE)
            single_price = price_item.text().strip() if price_item else ""
            result.append((spec, single_price, row))
        return result

    def add_test_row(self, spec, buy_count="2", single_price="", discount="8"):
        row = self.test_model.rowCount()
        self._recalculating = True
        try:
            self.test_model.insertRow(row)
            values = [
                spec["name"], "", "", buy_count, "", single_price, discount, "", "", "", "",
            ]
            editable_cols = {
                self.TEST_COL_BUY_COUNT, self.TEST_COL_SINGLE_PRICE,
                self.TEST_COL_DISCOUNT, self.TEST_COL_RECEIPT,
            }
            for col, value in enumerate(values):
                item = self._make_item(value, editable=(col in editable_cols), user_data=spec if col == self.TEST_COL_NAME else None)
                self._apply_price_test_item_style(item, col)
                self.test_model.setItem(row, col, item)
        finally:
            self._recalculating = False
        self.recalculate_row(row)

    def on_test_item_changed(self, item):
        if self._recalculating or item.column() not in (
            self.TEST_COL_BUY_COUNT, self.TEST_COL_SINGLE_PRICE,
            self.TEST_COL_DISCOUNT, self.TEST_COL_RECEIPT,
        ):
            return
        if item.column() == self.TEST_COL_RECEIPT:
            item.setData(bool(item.text().strip()), Qt.UserRole + 1)
        self.recalculate_row(item.row())

    def recalculate_row(self, row):
        if row < 0:
            return
        self._recalculating = True
        try:
            spec_item = self.test_model.item(row, self.TEST_COL_NAME)
            spec = spec_item.data(Qt.UserRole) if spec_item else {}
            quantity = str((spec or {}).get("quantity") or "")
            product_cost = float((spec or {}).get("product_cost") or 0)
            unit_weight = float((spec or {}).get("unit_weight") or 0)
            misc_fee = float((spec or {}).get("misc_fee") or 0)
            buy_count = max(1, int(round(self._parse_number(self.test_model.item(row, self.TEST_COL_BUY_COUNT).text(), 1))))
            single_price = self._parse_number(self.test_model.item(row, self.TEST_COL_SINGLE_PRICE).text(), 0)
            discount_rate = self._discount_rate(self.test_model.item(row, self.TEST_COL_DISCOUNT).text()) if buy_count > 1 else 1.0
            quantity_factor = self._quantity_factor(quantity)
            total_weight = unit_weight * quantity_factor * buy_count
            if hasattr(self.db, "calculate_cost_shipping_fee"):
                shipping_fee = self.db.calculate_cost_shipping_fee(total_weight)
            else:
                shipping_fee = float((spec or {}).get("shipping_fee") or 0)
            product_total = product_cost * quantity_factor * buy_count
            total_cost = product_total + shipping_fee + misc_fee
            receipt_item = self.test_model.item(row, self.TEST_COL_RECEIPT)
            manual_receipt = bool(receipt_item.data(Qt.UserRole + 1)) if receipt_item else False
            receipt = (
                max(0.0, self._parse_number(receipt_item.text(), 0))
                if manual_receipt
                else single_price * buy_count * discount_rate
            )
            discount_unit_price = receipt / buy_count if buy_count > 0 else 0.0
            profit = receipt - total_cost
            margin = (profit / receipt * 100) if receipt > 0 else 0.0
            updates = {
                self.TEST_COL_WEIGHT: f"{total_weight:.4f}".rstrip("0").rstrip("."),
                self.TEST_COL_SHIPPING: f"{shipping_fee:.2f}",
                self.TEST_COL_BUY_COUNT: str(buy_count),
                self.TEST_COL_TOTAL_COST: f"{total_cost:.2f}",
                self.TEST_COL_DISCOUNT_UNIT_PRICE: f"{discount_unit_price:.2f}",
                self.TEST_COL_RECEIPT: f"{receipt:.2f}",
                self.TEST_COL_PROFIT: f"{profit:.2f}",
                self.TEST_COL_MARGIN: f"{margin:.2f}%",
            }
            for col, value in updates.items():
                item = self.test_model.item(row, col)
                if item:
                    item.setText(value)
        finally:
            self._recalculating = False

    def duplicate_selected_test_rows(self):
        rows = sorted({index.row() for index in self.test_table.selectedIndexes()})
        for row in rows:
            item = self.test_model.item(row, self.TEST_COL_NAME)
            spec = item.data(Qt.UserRole) if item else None
            if not spec:
                continue
            new_row = self.test_model.rowCount()
            self.add_test_row(
                spec,
                self.test_model.item(row, self.TEST_COL_BUY_COUNT).text(),
                self.test_model.item(row, self.TEST_COL_SINGLE_PRICE).text(),
                self.test_model.item(row, self.TEST_COL_DISCOUNT).text(),
            )
            source_receipt = self.test_model.item(row, self.TEST_COL_RECEIPT)
            if source_receipt and source_receipt.data(Qt.UserRole + 1):
                target_receipt = self.test_model.item(new_row, self.TEST_COL_RECEIPT)
                target_receipt.setData(True, Qt.UserRole + 1)
                target_receipt.setText(source_receipt.text())
        self.update_count_label()

    def generate_custom_rows(self):
        picks = self.selected_pick_specs()
        if not picks:
            QMessageBox.information(self, "提示", "请先把规格加入测价候选区。")
            return
        for spec, single_price, _row in picks:
            self.add_test_row(spec, buy_count="1", single_price=single_price, discount="")
        self.update_count_label()

    def generate_selected_quantity_rows(self):
        picks = self.selected_pick_specs()
        if not picks:
            QMessageBox.information(self, "提示", "请先双击上方规格加入测价候选区。")
            return
        discount = self.default_discount_input.text().strip() or "8"
        for spec, single_price, row in picks:
            if not single_price:
                QMessageBox.warning(self, "提示", f"请先填写测价候选区第 {row + 1} 行的单件售价。")
                return
            for count in range(1, 11):
                self.add_test_row(spec, buy_count=str(count), single_price=single_price, discount=discount)
        self.update_count_label()

    def delete_selected_pick_rows(self):
        rows = sorted({index.row() for index in self.pick_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.pick_model.removeRow(row)
        self.update_count_label()

    def delete_selected_test_rows(self):
        rows = sorted({index.row() for index in self.test_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.test_model.removeRow(row)
        self.update_count_label()

    def clear_test_rows(self):
        self.test_model.setRowCount(0)
        self.update_count_label()

    def update_count_label(self):
        if hasattr(self, "count_label"):
            pick_count = self.pick_model.rowCount() if hasattr(self, "pick_model") else 0
            self.count_label.setText(f"搜索候选 {self.candidate_model.rowCount()} 条，测价候选 {pick_count} 条，测价 {self.test_model.rowCount()} 行")


class UnlistedCostSpecsDialog(QDialog):
    """独立的未上架规格操作窗口，支持筛选、搜索、上架车和创建链接。"""

    COL_IMAGE = 0
    COL_CATEGORY = 1
    COL_NAME = 2
    ROW_ROLE = Qt.UserRole + 320

    def __init__(self, db_manager, main_window=None, default_store_id=None, parent=None):
        super().__init__(None)
        self.db = db_manager
        self.main_window = main_window
        self.default_store_id = default_store_id
        self.all_rows = []
        self.cart = {}
        self.setWindowTitle("未上架规格")
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.resize(980, 720)
        apply_window_icon(self)
        self.init_ui()
        self.load_stores()
        self.refresh_rows()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选店铺:"))
        self.store_combo = QComboBox()
        self.store_combo.currentIndexChanged.connect(self.refresh_rows)
        filter_layout.addWidget(self.store_combo, 0)
        filter_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品类型/规格名称/规格编码关键字，空格分隔...")
        self.search_input.textChanged.connect(self.populate_table)
        filter_layout.addWidget(self.search_input, 1)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh_rows)
        filter_layout.addWidget(btn_refresh)
        layout.addLayout(filter_layout)

        self.table_view = QTableView()
        self.model = QStandardItemModel(0, 3, self)
        self.model.setHorizontalHeaderLabels(["图片", "商品类型", "规格名称"])
        self.table_view.setModel(self.model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setWordWrap(True)
        self.table_view.verticalHeader().setDefaultSectionSize(64)
        self.table_view.horizontalHeader().setSectionResizeMode(self.COL_IMAGE, QHeaderView.Fixed)
        self.table_view.setColumnWidth(self.COL_IMAGE, 72)
        self.table_view.horizontalHeader().setSectionResizeMode(self.COL_CATEGORY, QHeaderView.ResizeToContents)
        self.table_view.horizontalHeader().setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        self.table_view.clicked.connect(self.on_table_clicked)
        self.copy_shortcut = QShortcut(QKeySequence.Copy, self.table_view)
        self.copy_shortcut.activated.connect(self.copy_selected)
        layout.addWidget(self.table_view, 1)

        cart_frame = QWidget()
        cart_frame.setObjectName("unlistedCartFrame")
        cart_frame.setStyleSheet(
            "QWidget#unlistedCartFrame { background: #fafafa; border: 1px solid #dcdcdc; border-radius: 8px; }"
        )
        cart_outer = QVBoxLayout(cart_frame)
        cart_outer.setContentsMargins(10, 8, 10, 8)
        cart_outer.setSpacing(6)
        cart_header = QHBoxLayout()
        self.cart_title_label = QLabel("上架车（0）")
        self.cart_title_label.setStyleSheet("font-weight: bold;")
        cart_header.addWidget(self.cart_title_label)
        cart_header.addStretch()
        self.btn_clear_cart = QPushButton("清空上架车")
        self.btn_clear_cart.clicked.connect(self.clear_cart)
        cart_header.addWidget(self.btn_clear_cart)
        cart_outer.addLayout(cart_header)

        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setFixedHeight(118)
        self.cart_scroll.setFrameShape(QScrollArea.NoFrame)
        self.cart_widget = QWidget()
        self.cart_chip_layout = QHBoxLayout(self.cart_widget)
        self.cart_chip_layout.setContentsMargins(2, 2, 2, 2)
        self.cart_chip_layout.setSpacing(6)
        self.cart_scroll.setWidget(self.cart_widget)
        cart_outer.addWidget(self.cart_scroll)
        layout.addWidget(cart_frame, 0)

        hint = QLabel("Ctrl+单击表格行加入/移出上架车；上架车不受搜索影响。Ctrl+C 可复制当前选中行。")
        hint.setStyleSheet("color: #777;")
        layout.addWidget(hint)

        btn_layout = QHBoxLayout()
        self.lbl_count = QLabel("0 条")
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addStretch()
        btn_copy_selected = QPushButton("复制选中")
        btn_copy_selected.clicked.connect(self.copy_selected)
        btn_copy_cart = QPushButton("复制上架车")
        btn_copy_cart.clicked.connect(self.copy_cart)
        btn_create = QPushButton("创建链接")
        btn_create.clicked.connect(self.create_link)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_copy_selected)
        btn_layout.addWidget(btn_copy_cart)
        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        self.refresh_cart_view()

    def load_stores(self):
        self.store_combo.blockSignals(True)
        self.store_combo.clear()
        self.store_combo.addItem("全部店铺", None)
        default_index = 0
        for store_id, store_name in self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order, id"):
            self.store_combo.addItem(str(store_name or f"店铺{store_id}"), store_id)
            if self.default_store_id is not None and int(store_id) == int(self.default_store_id):
                default_index = self.store_combo.count() - 1
        self.store_combo.setCurrentIndex(default_index)
        self.store_combo.blockSignals(False)

    def refresh_rows(self):
        store_id = self.store_combo.currentData() if hasattr(self, "store_combo") else None
        rows = self.fetch_unlisted_rows(store_id)
        self.all_rows = [self._row_dict(row) for row in rows]
        self.populate_table()

    def fetch_unlisted_rows(self, store_id=None):
        listed_sql = """
            SELECT product_specs.spec_code, COUNT(*) AS listed_count
            FROM product_specs
            JOIN products ON products.id = product_specs.product_id
            WHERE COALESCE(product_specs.spec_code, '') <> ''
              AND COALESCE(products.is_archived, 0) = 0
        """
        params = []
        if store_id is not None:
            listed_sql += " AND products.store_id = ?"
            params.append(store_id)
        listed_sql += " GROUP BY product_specs.spec_code"
        sql = f"""
            SELECT cost_library.category_label,
                   cost_library.spec_name,
                   cost_library.spec_code,
                   cost_library.thumbnail_data,
                   COALESCE(cost_categories.color, cost_library.category_color, cost_library.source_bg_color, '') AS row_color,
                   cost_library.sort_order
            FROM cost_library
            LEFT JOIN cost_categories ON cost_categories.label = cost_library.category_label
            LEFT JOIN ({listed_sql}) listed_specs ON listed_specs.spec_code = cost_library.spec_code
            WHERE COALESCE(cost_library.spec_code, '') <> ''
              AND COALESCE(listed_specs.listed_count, 0) = 0
            ORDER BY CASE WHEN COALESCE(cost_library.category_label, '') = '' THEN 1 ELSE 0 END,
                     cost_library.category_label,
                     CASE WHEN cost_library.sort_order IS NULL THEN 1 ELSE 0 END,
                     cost_library.sort_order,
                     cost_library.spec_code
        """
        return self.db.safe_fetchall(sql, tuple(params))

    def _row_dict(self, row):
        category, name, code, thumbnail_data, color, sort_order = row
        return {
            "category_label": str(category or "").strip(),
            "spec_name": str(name or "").strip(),
            "spec_code": str(code or "").strip(),
            "thumbnail_data": bytes(thumbnail_data or b""),
            "color": str(color or "").strip(),
            "sort_order": sort_order if sort_order is not None else 999999999,
        }

    def filtered_rows(self):
        query = self.search_input.text().strip()
        terms = split_search_terms(query)
        if not terms:
            return list(self.all_rows)
        scored = []
        for row in self.all_rows:
            full_hit, hit_count = match_score(
                query,
                terms,
                row.get("category_label", ""),
                row.get("spec_name", ""),
                row.get("spec_code", ""),
            )
            if hit_count > 0:
                scored.append((full_hit, hit_count, row.get("sort_order", 999999999), row.get("spec_code", ""), row))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
        return [item[4] for item in scored]

    def populate_table(self):
        rows = self.filtered_rows()
        self.model.setRowCount(0)
        for row_data in rows:
            category = row_data.get("category_label") or "未分类"
            items = [QStandardItem(), QStandardItem(category), QStandardItem(row_data.get("spec_name", ""))]
            thumbnail_data = row_data.get("thumbnail_data") or b""
            pixmap = QPixmap()
            if thumbnail_data and pixmap.loadFromData(thumbnail_data):
                items[self.COL_IMAGE].setData(
                    pixmap.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation),
                    Qt.DecorationRole,
                )
            for item in items:
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                item.setData(row_data, self.ROW_ROLE)
                item.setToolTip(
                    f"商品类型：{category}\n规格名称：{row_data.get('spec_name') or '-'}\n"
                    f"规格编码：{row_data.get('spec_code') or '-'}"
                )
                color = row_data.get("color")
                if color:
                    item.setBackground(QBrush(QColor(color)))
            self.model.appendRow(items)
        self.lbl_count.setText(f"{len(rows)} 条 / 共 {len(self.all_rows)} 条")
        self.table_view.resizeRowsToContents()

    def on_table_clicked(self, index):
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.toggle_cart_row(index.row())

    def _row_data_from_model(self, row):
        item = self.model.item(row, self.COL_NAME)
        return item.data(self.ROW_ROLE) if item else None

    def toggle_cart_row(self, row):
        row_data = self._row_data_from_model(row)
        if not row_data:
            return
        spec_code = row_data.get("spec_code")
        if not spec_code:
            return
        if spec_code in self.cart:
            self.cart.pop(spec_code, None)
            self.show_hint("已移出上架车")
        else:
            self.cart[spec_code] = dict(row_data)
            self.show_hint("已加入上架车")
        self.refresh_cart_view()

    def remove_cart_item(self, spec_code):
        self.cart.pop(spec_code, None)
        self.refresh_cart_view()

    def clear_cart(self):
        if not self.cart:
            return
        self.cart.clear()
        self.refresh_cart_view()
        self.show_hint("已清空上架车")

    def refresh_cart_view(self):
        while self.cart_chip_layout.count():
            item = self.cart_chip_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.cart_title_label.setText(f"上架车（{len(self.cart)}）")
        self.btn_clear_cart.setEnabled(bool(self.cart))
        if not self.cart:
            placeholder = QLabel("Ctrl+单击未上架规格加入上架车")
            placeholder.setStyleSheet("color: #888; padding: 8px;")
            self.cart_chip_layout.addWidget(placeholder)
            self.cart_chip_layout.addStretch()
            return
        for spec_code, spec in self.cart.items():
            category = spec.get("category_label") or "未分类"
            spec_name = spec.get("spec_name") or spec_code
            chip = QWidget()
            chip.setObjectName("unlistedCartChip")
            chip.setFixedSize(198, 48)
            chip.setToolTip(f"商品类型：{category}\n规格名称：{spec_name}\n规格编码：{spec_code}")
            chip.setStyleSheet(
                "QWidget#unlistedCartChip { background-color: #ffffff; border: 1px solid #cfd8dc; border-radius: 10px; }"
                "QWidget#unlistedCartChip:hover { background-color: #ffffff; color: #000000; border: 1px solid #9e9e9e; }"
                "QWidget#unlistedCartChip:hover QLabel { color: #000000; }"
            )
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 4, 4, 4)
            chip_layout.setSpacing(4)
            text_layout = QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(1)
            category_label = QLabel(category)
            category_label.setStyleSheet("color: #8a5a00; font-size: 11px; font-weight: bold; border: none; background: transparent;")
            name_label = QLabel(spec_name)
            name_label.setStyleSheet("color: #245269; font-size: 12px; font-weight: bold; border: none; background: transparent;")
            category_label.setToolTip(category)
            name_label.setToolTip(spec_name)
            text_layout.addWidget(category_label)
            text_layout.addWidget(name_label)
            remove_btn = QPushButton("×")
            remove_btn.setFixedSize(20, 20)
            remove_btn.setStyleSheet(
                "QPushButton { border: none; background-color: #eeeeee; color: #333; border-radius: 10px; font-weight: bold; }"
                "QPushButton:hover { background-color: #d6d6d6; }"
            )
            remove_btn.clicked.connect(lambda _checked=False, code=spec_code: self.remove_cart_item(code))
            chip_layout.addLayout(text_layout, 1)
            chip_layout.addWidget(remove_btn)
            self.cart_chip_layout.addWidget(chip)
        self.cart_chip_layout.addStretch()

    def selected_specs(self):
        rows = sorted({index.row() for index in self.table_view.selectedIndexes()})
        specs = []
        seen = set()
        for row in rows:
            row_data = self._row_data_from_model(row)
            if not row_data:
                continue
            spec_code = row_data.get("spec_code")
            if not spec_code or spec_code in seen:
                continue
            seen.add(spec_code)
            specs.append(dict(row_data))
        return specs

    def create_specs_payload(self):
        source = list(self.cart.values()) if self.cart else self.selected_specs()
        return [
            {
                "spec_name": spec.get("spec_name", ""),
                "spec_code": spec.get("spec_code", ""),
                "category_label": spec.get("category_label", ""),
            }
            for spec in source
            if spec.get("spec_code")
        ]

    def create_link(self):
        specs = self.create_specs_payload()
        if not specs:
            QMessageBox.warning(self, "提示", "请先选择或加入上架车规格。")
            return
        dialog = CostLinkCreateDialog(self.db, specs, self.main_window, self)
        store_id = self.store_combo.currentData()
        if store_id is not None:
            index = dialog.store_combo.findData(store_id)
            if index >= 0:
                dialog.store_combo.setCurrentIndex(index)
        if dialog.exec_() == QDialog.Accepted:
            self.cart.clear()
            self.refresh_cart_view()
            self.refresh_rows()

    def _format_specs_for_copy(self, specs):
        if not specs:
            return ""
        lines = ["商品类型\t规格名称"]
        for spec in specs:
            lines.append(
                f"{spec.get('category_label') or '未分类'}\t{spec.get('spec_name') or ''}"
            )
        return "\n".join(lines)

    def copy_selected(self):
        current = self.table_view.currentIndex()
        if current.isValid() and current.column() == self.COL_IMAGE:
            row_data = self._row_data_from_model(current.row()) or {}
            pixmap = QPixmap()
            if pixmap.loadFromData(row_data.get("thumbnail_data") or b""):
                QApplication.clipboard().setPixmap(pixmap)
                self.show_hint("图片已复制")
            else:
                self.show_hint("该规格没有图片")
            return
        text = self._format_specs_for_copy(self.selected_specs())
        if not text:
            QMessageBox.information(self, "提示", "请先选择要复制的规格。")
            return
        QApplication.clipboard().setText(text)
        self.show_hint("已复制")

    def copy_cart(self):
        text = self._format_specs_for_copy(list(self.cart.values()))
        if not text:
            QMessageBox.information(self, "提示", "上架车为空。")
            return
        QApplication.clipboard().setText(text)
        self.show_hint("已复制")

    def show_hint(self, text):
        QToolTip.showText(QCursor.pos(), text, self, self.rect(), 1200)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self.copy_selected()
            return
        super().keyPressEvent(event)


class ProductAttributeDialog(QDialog):
    """Edit a cost-library product attribute, optionally composing it from other specs."""

    def __init__(
        self,
        db_manager,
        current_value="",
        current_spec_code="",
        current_spec_name="",
        auto_detect_disabled=False,
        force_combo=False,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.current_spec_code = str(current_spec_code or "").strip()
        self.current_spec_name = str(current_spec_name or "").strip()
        self.auto_detect_disabled = bool(auto_detect_disabled)
        self.initial_combo_state = bool(force_combo)
        self._auto_detected_combo = False
        self._selection_changed = False
        self._source_has_combo_mark = False
        self._initial_rows_sized = False
        self.all_specs = []
        self.selected_specs = {}
        self.setWindowTitle("产品属性编辑")
        self.resize(1120, 680)
        self.init_ui()
        self.load_specs()
        current_text = str(current_value or "").strip()
        self.attribute_edit.setPlainText(current_text)
        name_has_combo_mark = len(self._split_combo_parts(self.current_spec_name)) >= 2
        attribute_has_combo_mark = len(self._split_combo_parts(current_text)) >= 2
        self._source_has_combo_mark = name_has_combo_mark
        saved_items = self.db.get_cost_combo_items(
            self.current_spec_code, suggest=self.initial_combo_state
        ) if hasattr(self.db, "get_cost_combo_items") else []
        single_codes = {spec["code"] for spec in self.all_specs}
        saved_items = [item for item in saved_items if item.get("code") in single_codes]
        if self.initial_combo_state and saved_items:
            self.selected_specs = {item["code"]: dict(item) for item in saved_items}
            self.combo_check.setChecked(True)
            self.refresh_selected_table()
        elif self.initial_combo_state:
            if attribute_has_combo_mark:
                self.auto_detect_combo(current_text)
            elif name_has_combo_mark:
                self.auto_detect_combo(self.current_spec_name)
            else:
                self.combo_check.setChecked(True)
                self.refresh_selected_table()
        elif not self.auto_detect_disabled and name_has_combo_mark:
            self.auto_detect_combo(self.current_spec_name)
        self.on_combo_toggled(self.combo_check.isChecked())
        self._update_attribute_preview()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.current_product_label = QLabel(f"当前编辑商品：{self.current_spec_name or '-'}")
        self.current_product_label.setWordWrap(True)
        self.current_product_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.current_product_label.setStyleSheet(
            "background:#f6f8fa;border:1px solid #d8dee4;border-radius:4px;padding:5px;color:#24292f;"
        )
        layout.addWidget(self.current_product_label)
        self.attribute_label = QLabel("产品属性:")
        layout.addWidget(self.attribute_label)
        self.attribute_edit = QTextEdit()
        self.attribute_edit.setPlaceholderText("输入产品属性，例如：17cm、A款17cm、A17cm+B20cm")
        self.attribute_edit.setFixedHeight(84)
        self.attribute_edit.textChanged.connect(self._update_attribute_preview)
        layout.addWidget(self.attribute_edit)

        combo_bar = QHBoxLayout()
        self.combo_check = QCheckBox("组合产品")
        self.combo_check.toggled.connect(self.on_combo_toggled)
        combo_bar.addWidget(self.combo_check)
        combo_bar.addStretch()
        layout.addLayout(combo_bar)

        self.combo_widget = QWidget()
        combo_layout = QVBoxLayout(self.combo_widget)
        combo_layout.setContentsMargins(0, 0, 0, 0)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索单品规格:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品名称/规格编码/产品属性关键字，空格分隔...")
        self.search_input.textChanged.connect(self.refresh_spec_table)
        search_layout.addWidget(self.search_input)
        combo_layout.addLayout(search_layout)

        self.spec_model = QStandardItemModel()
        self.spec_model.setHorizontalHeaderLabels(["商品类型", "商品名称", "规格编码", "数量", "产品属性"])
        self.spec_table = QTableView()
        self.spec_table.setModel(self.spec_model)
        self.spec_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.spec_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.spec_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.spec_table.setWordWrap(True)
        self.spec_table.setTextElideMode(Qt.ElideNone)
        self.spec_table.setStyleSheet("QTableView::item { padding: 1px; }")
        self.spec_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.spec_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.spec_table.setColumnWidth(0, 120)
        self.spec_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.spec_table.setColumnWidth(1, 300)
        self.spec_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.spec_table.setColumnWidth(2, 150)
        self.spec_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.spec_table.setColumnWidth(3, 70)
        self.spec_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.spec_table.clicked.connect(self.on_spec_clicked)
        combo_layout.addWidget(self.spec_table, 1)

        selected_title = QHBoxLayout()
        selected_title.addWidget(QLabel("已选组合单品:"))
        selected_title.addStretch()
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self.clear_combo_items)
        selected_title.addWidget(btn_clear)
        combo_layout.addLayout(selected_title)

        self.selected_scroll = QScrollArea()
        self.selected_scroll.setWidgetResizable(True)
        self.selected_scroll.setFixedHeight(86)
        self.selected_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.selected_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.selected_content = QWidget()
        self.selected_chip_layout = QHBoxLayout(self.selected_content)
        self.selected_chip_layout.setContentsMargins(6, 4, 6, 4)
        self.selected_chip_layout.setSpacing(6)
        self.selected_scroll.setWidget(self.selected_content)
        combo_layout.addWidget(self.selected_scroll)
        layout.addWidget(self.combo_widget, 1)

        layout.addWidget(QLabel("当前属性信息:"))
        self.attribute_preview = QTextEdit()
        self.attribute_preview.setReadOnly(True)
        self.attribute_preview.setAcceptRichText(False)
        self.attribute_preview.setPlaceholderText("暂无产品属性")
        self.attribute_preview.setFixedHeight(104)
        self.attribute_preview.setStyleSheet(
            "QTextEdit{background:#f7f9fc;border:1px solid #d8dee4;border-radius:4px;padding:5px;}"
        )
        layout.addWidget(self.attribute_preview)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self.save_and_accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def on_combo_toggled(self, checked):
        self.attribute_label.setVisible(not checked)
        self.attribute_edit.setVisible(not checked)
        self.combo_widget.setVisible(bool(checked))
        self.resize(max(self.width(), 1120), 680 if checked else 390)
        self._update_attribute_preview()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_rows_sized:
            QTimer.singleShot(0, self._resize_spec_rows_after_show)

    def _resize_spec_rows_after_show(self):
        if not hasattr(self, "spec_table"):
            return
        self.spec_table.resizeRowsToContents()
        self._initial_rows_sized = True

    def _update_attribute_preview(self):
        if not hasattr(self, "attribute_preview"):
            return
        text = self.generated_attribute() if self.combo_check.isChecked() else self.attribute_edit.toPlainText().strip()
        if self.attribute_preview.toPlainText() != text:
            self.attribute_preview.setPlainText(text)

    def load_specs(self):
        rows = self.db.safe_fetchall(
            """SELECT COALESCE(category_label, ''), COALESCE(spec_name, ''), spec_code,
                      COALESCE(quantity, ''), COALESCE(product_attribute, ''),
                      COALESCE(product_attribute_combo_disabled, 0), COALESCE(product_attribute_is_combo, 0)
               FROM cost_library
               WHERE COALESCE(spec_code, '') <> ''
               ORDER BY CASE WHEN sort_order IS NULL THEN 1 ELSE 0 END, sort_order, spec_code"""
        )
        self.all_specs = [
            {
                "category": str(category or ""),
                "name": str(name or ""),
                "code": str(code or ""),
                "quantity": str(quantity or ""),
                "attribute": str(attribute or ""),
            }
            for category, name, code, quantity, attribute, combo_disabled, attr_is_combo in rows
            if str(code or "").strip()
            and str(code or "").strip() != self.current_spec_code
            and (
                int(combo_disabled or 0)
                or (
                    not int(attr_is_combo or 0)
                    and not self.db.is_cost_combo_name(name)
                )
            )
        ]
        self.refresh_spec_table()

    def auto_detect_combo(self, text):
        text = str(text or "").strip()
        parts = self._split_combo_parts(text)
        if len(parts) < 2:
            return
        selected = {}
        for part in parts:
            match = self._match_combo_part(part)
            if not match:
                continue
            selected[match["code"]] = {**match, "combo_quantity": 1}
        self.selected_specs = selected
        self._auto_detected_combo = True
        self.refresh_selected_table()
        self.combo_check.setChecked(True)
        if selected:
            self.attribute_edit.setPlainText(self.generated_attribute())

    def _split_combo_parts(self, text):
        return [item.strip() for item in re.split(r"\+|＋|﹢", str(text or "")) if item.strip()]

    def _match_combo_part(self, part):
        part_norm = self._normalize_combo_text(part)
        best = None
        best_score = -1
        for spec in self.all_specs:
            candidates = [
                f"{spec['name']}{spec['attribute']}",
                str(spec["name"] or ""),
                str(spec["attribute"] or ""),
            ]
            for candidate in candidates:
                candidate_norm = self._normalize_combo_text(candidate)
                if not candidate_norm:
                    continue
                if candidate_norm == part_norm:
                    return spec
                if candidate_norm in part_norm or part_norm in candidate_norm:
                    score = min(len(candidate_norm), len(part_norm))
                    if score > best_score:
                        best = spec
                        best_score = score
        return best if best_score >= 2 else None

    def _normalize_combo_text(self, value):
        return re.sub(r"[\s,，。;；:：|｜/\\_\-（）()【】\\[\\]{}]+", "", str(value or "").strip().lower())

    def refresh_spec_table(self):
        self.spec_model.setRowCount(0)
        text = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        terms = split_search_terms(text)
        rows = []
        for spec in self.all_specs:
            values = (spec["category"], spec["name"], spec["code"], spec["quantity"], spec["attribute"])
            if terms and not any_terms_match(terms, *values):
                continue
            full_hit, hit_count = match_score(text, terms, *values)
            rows.append((full_hit, hit_count, spec))
        rows.sort(key=lambda item: (-item[0], -item[1], item[2]["name"], item[2]["code"]))
        for _full_hit, _hit_count, spec in rows:
            row = self.spec_model.rowCount()
            self.spec_model.insertRow(row)
            horizontal_attribute = " / ".join(
                line.strip() for line in str(spec["attribute"] or "").splitlines() if line.strip()
            )
            for col, value in enumerate((
                spec["category"], spec["name"], spec["code"], spec["quantity"], horizontal_attribute,
            )):
                item = QStandardItem(value)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 0:
                    item.setData(spec, Qt.UserRole)
                self.spec_model.setItem(row, col, item)
        self.spec_table.resizeRowsToContents()

    def on_spec_clicked(self, index):
        if not index.isValid() or not (QApplication.keyboardModifiers() & Qt.ControlModifier):
            return
        item = self.spec_model.item(index.row(), 0)
        spec = item.data(Qt.UserRole) if item else None
        if not spec:
            return
        code = spec["code"]
        if code in self.selected_specs:
            self.selected_specs.pop(code, None)
        else:
            selected = dict(spec)
            if not self.selected_specs and not re.search(r"\+|＋|﹢", self.current_spec_name):
                multiplier = self.db.cost_combo_multiplier(self.current_spec_name) if hasattr(self.db, "cost_combo_multiplier") else 1
                selected["combo_quantity"] = multiplier
            self.selected_specs[code] = selected
        self._selection_changed = True
        self.refresh_selected_table()
        self.attribute_edit.setPlainText(self.generated_attribute())

    def refresh_selected_table(self):
        if not hasattr(self, "selected_chip_layout"):
            return
        while self.selected_chip_layout.count():
            item = self.selected_chip_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self.selected_specs:
            placeholder = QLabel("Ctrl+单击上方规格加入组合")
            placeholder.setStyleSheet("color: #888; padding: 6px;")
            self.selected_chip_layout.addWidget(placeholder)
            self.selected_chip_layout.addStretch()
            return
        for spec in self.selected_specs.values():
            code = spec["code"]
            name = str(spec.get("name") or code)
            attribute = str(spec.get("attribute") or "").strip()
            quantity = float(spec.get("combo_quantity") or 1)
            qty_text = f" ×{int(quantity) if quantity.is_integer() else quantity:g}"
            full_text = f"{name}{attribute}{qty_text}" if attribute else f"{name}{qty_text}"
            chip = QWidget()
            chip.setObjectName("attributeComboChip")
            chip.setToolTip(f"完整规格：{full_text}\n商品名称：{name}\n规格编码：{code}\n产品属性：{attribute or '-'}")
            chip.setStyleSheet(
                "QWidget#attributeComboChip { background-color: #eef7ff; border: 1px solid #9ec5fe; border-radius: 10px; }"
            )
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 4, 4, 4)
            name_label = QLabel(name)
            name_label.setToolTip(chip.toolTip())
            name_label.setStyleSheet("border: none; background: transparent; color: #1f4e79; font-weight: bold;")
            multiplier_label = QLabel("×")
            multiplier_label.setStyleSheet("border:none;background:transparent;color:#1f4e79;font-weight:bold;")
            quantity_input = QSpinBox()
            quantity_input.setRange(1, 999)
            quantity_input.setValue(max(1, int(round(quantity))))
            quantity_input.setFixedWidth(58)
            quantity_input.setToolTip("设置该单品在组合中的数量")
            quantity_input.valueChanged.connect(
                lambda value, spec_code=code: self.set_combo_quantity(spec_code, value)
            )
            text_width = QFontMetrics(name_label.font()).horizontalAdvance(name)
            chip.setFixedSize(max(220, text_width + 126), 38)
            remove_btn = QPushButton("×")
            remove_btn.setFixedSize(20, 20)
            remove_btn.setStyleSheet(
                "QPushButton { border: none; background-color: #cfe2ff; color: #1f4e79; border-radius: 10px; font-weight: bold; }"
                "QPushButton:hover { background-color: #9ec5fe; }"
            )
            remove_btn.clicked.connect(lambda _checked=False, spec_code=code: self.remove_combo_item(spec_code))
            chip_layout.addWidget(name_label, 1)
            chip_layout.addWidget(multiplier_label)
            chip_layout.addWidget(quantity_input)
            chip_layout.addWidget(remove_btn)
            self.selected_chip_layout.addWidget(chip)
        self.selected_chip_layout.addStretch()

    def set_combo_quantity(self, code, quantity):
        spec = self.selected_specs.get(code)
        if not spec:
            return
        spec["combo_quantity"] = int(quantity)
        self._selection_changed = True
        self.attribute_edit.setPlainText(self.generated_attribute())

    def remove_selected_combo_item(self):
        return

    def remove_combo_item(self, code):
        if code:
            self.selected_specs.pop(code, None)
            self._selection_changed = True
            self.refresh_selected_table()
            self.attribute_edit.setPlainText(self.generated_attribute())

    def clear_combo_items(self):
        self.selected_specs.clear()
        self._selection_changed = True
        self.refresh_selected_table()
        self.attribute_edit.clear()

    def generated_attribute(self):
        lines = []
        seen = set()
        for spec in self.selected_specs.values():
            attribute = str(spec.get("attribute") or "").strip()
            for line in re.split(r"\r?\n|\s+/\s+", attribute):
                line = line.strip()
                key = re.sub(r"\s+", "", line).replace("：", ":").casefold()
                if line and key not in seen:
                    seen.add(key)
                    lines.append(line)
        return "\n".join(lines)

    def attribute_text(self):
        if self.combo_check.isChecked():
            return self.generated_attribute()
        return self.attribute_edit.toPlainText().strip()

    def auto_detect_disable_value(self):
        if self.combo_check.isChecked():
            return 0
        if self.initial_combo_state or self._source_has_combo_mark or self.auto_detect_disabled:
            return 1
        return 0

    def is_combo_product(self):
        return 1 if self.combo_check.isChecked() else 0

    def component_items(self):
        return [
            {"spec_code": spec["code"], "quantity": spec.get("combo_quantity") or 1}
            for spec in self.selected_specs.values()
        ]

    def save_and_accept(self):
        if self.combo_check.isChecked() and not self.selected_specs:
            QMessageBox.warning(self, "提示", "组合产品至少需要选择一个包含单品")
            return
        self.accept()


class CostComboReviewDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self._row_animations = []
        self._removing_codes = set()
        self.setWindowTitle("组合产品待处理")
        self.resize(1380, 780)
        layout = QVBoxLayout(self)
        tip_row = QHBoxLayout()
        tip = QLabel("组合关系已由系统设置并联动成本、重量。点击对钩只标记为已人工检查，不会重新计算或修改包含单品。")
        tip.setStyleSheet("color:#555;padding:4px;")
        tip_row.addWidget(tip)
        tip_row.addStretch()
        self.bulk_confirm_button = QPushButton("✓ 批量检查")
        self.bulk_confirm_button.setToolTip("将当前选中的组合产品批量标记为已人工检查")
        self.bulk_confirm_button.clicked.connect(self.confirm_selected)
        tip_row.addWidget(self.bulk_confirm_button)
        layout.addLayout(tip_row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["商品类型", "商品名称", "包含单品", "已检查"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(3, 64)
        self.table.doubleClicked.connect(self._edit_from_index)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_edit = QPushButton("编辑选中")
        btn_edit.clicked.connect(self.edit_current)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        buttons.addWidget(btn_edit)
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)
        self.refresh()
        self.review_sync_timer = QTimer(self)
        self.review_sync_timer.setInterval(700)
        self.review_sync_timer.timeout.connect(self._sync_reviewed_rows)
        self.review_sync_timer.start()

    @staticmethod
    def _attribute_for_items(items):
        if len(items) == 1 and float(items[0].get("combo_quantity") or 1) > 1:
            return str(items[0].get("attribute") or "").strip()
        return "+".join(
            f"{item.get('name') or ''}{item.get('attribute') or ''}" for item in items
        )

    def _pending_rows(self, spec_codes=None):
        params = tuple(dict.fromkeys(str(code) for code in (spec_codes or []) if code))
        code_filter = ""
        if params:
            code_filter = f" AND spec_code IN ({','.join('?' for _ in params)})"
        return self.db.safe_fetchall(
            f"""SELECT spec_code, COALESCE(category_label, ''), COALESCE(spec_name, ''),
                       COALESCE(product_attribute, ''), COALESCE(product_attribute_combo_disabled, 0)
                FROM cost_library
                WHERE COALESCE(product_attribute_is_combo, 0)=1
                  AND COALESCE(combo_reviewed, 0)=0{code_filter}
                ORDER BY sort_order, spec_code""",
            params,
        )

    def _set_component_cell(self, row, items):
        chip_host = QWidget()
        chip_host.setAttribute(Qt.WA_TransparentForMouseEvents)
        chip_layout = QVBoxLayout(chip_host)
        chip_layout.setContentsMargins(4, 3, 4, 3)
        chip_layout.setSpacing(5)
        row_height = 10
        if not items:
            chip = QLabel("未识别到单品，双击编辑")
            chip.setWordWrap(True)
            chip.setStyleSheet("color:#b42318;background:#fff1f0;border:1px solid #ffa39e;border-radius:9px;padding:4px 8px;")
            chip_layout.addWidget(chip)
            row_height += 40
        for index, item in enumerate(items):
            qty = float(item.get("combo_quantity") or 1)
            qty_text = f" *{int(qty) if qty.is_integer() else qty:g}" if qty > 1 else ""
            chip_text = f"{item.get('name') or item.get('code')}{qty_text}"
            chip = QLabel(chip_text)
            chip.setWordWrap(True)
            chip.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text_width = QFontMetrics(chip.font()).horizontalAdvance(chip_text)
            bubble_width = min(max(text_width + 32, 240), 900)
            text_height = QFontMetrics(chip.font()).boundingRect(
                0, 0, bubble_width - 24, 10000, Qt.TextWordWrap, chip_text
            ).height()
            chip.setMinimumWidth(bubble_width)
            chip.setMinimumHeight(max(34, text_height + 16))
            chip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
            colors = ("#e6f4ff", "#f6ffed", "#fff7e6", "#f9f0ff")
            chip.setStyleSheet(
                f"background:{colors[index % len(colors)]};border:1px solid #91caff;"
                "border-radius:10px;padding:4px 9px;color:#1f2937;"
            )
            chip.setToolTip(f"{item.get('name') or ''}\n规格编码：{item.get('code') or ''}\n数量：{qty_text.strip('* ') or '1'}")
            chip_layout.addWidget(chip)
            row_height += chip.minimumHeight() + 5
        self.table.setCellWidget(row, 2, chip_host)
        self.table.setRowHeight(row, max(52, row_height))

    def _append_row(self, data):
        code, category, name, attribute, disabled = data
        items = self.db.get_cost_combo_items(code, suggest=False)
        row = self.table.rowCount()
        self.table.insertRow(row)
        record = {
            "code": str(code), "name": str(name), "category": str(category),
            "attribute": str(attribute), "disabled": int(disabled or 0), "items": items,
        }
        category_item = QTableWidgetItem(str(category))
        category_item.setData(Qt.UserRole, record)
        category_item.setTextAlignment(Qt.AlignCenter)
        name_item = QTableWidgetItem(str(name))
        name_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, category_item)
        self.table.setItem(row, 1, name_item)
        self._set_component_cell(row, items)
        confirm_button = QPushButton("✓")
        confirm_button.setFocusPolicy(Qt.NoFocus)
        confirm_button.setToolTip("标记为已人工检查，仅移除这条待处理提示")
        confirm_button.setCursor(Qt.PointingHandCursor)
        confirm_button.setStyleSheet(
            "QPushButton{background:#e8f5e9;color:#16803c;border:1px solid #81c784;"
            "border-radius:14px;font-size:17px;font-weight:bold;padding:3px;}"
            "QPushButton:hover{background:#c8e6c9;}QPushButton:pressed{background:#a5d6a7;}"
        )
        confirm_button.clicked.connect(lambda _checked=False, record=record: self.confirm_record(record))
        confirm_button.setFixedSize(32, 32)
        confirm_host = QWidget()
        confirm_layout = QHBoxLayout(confirm_host)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        confirm_layout.setAlignment(Qt.AlignCenter)
        confirm_layout.addWidget(confirm_button)
        self.table.setCellWidget(row, 3, confirm_host)

    def refresh(self):
        self.table.setRowCount(0)
        for row in self._pending_rows():
            self._append_row(row)

    def _record(self, row=None):
        row = self.table.currentRow() if row is None else row
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _edit_from_index(self, index):
        if index.isValid() and index.column() in (1, 2):
            self.table.setCurrentCell(index.row(), index.column())
            self.edit_current()

    def edit_current(self):
        record = self._record()
        if not record:
            QMessageBox.information(self, "提示", "请先选择一个组合产品")
            return
        dialog = ProductAttributeDialog(
            self.db, record["attribute"], record["code"], record["name"],
            record["disabled"], True, self,
        )
        if dialog.exec_() == QDialog.Accepted:
            changed = self.db.save_cost_combo_definition(
                record["code"], dialog.is_combo_product(), dialog.component_items(),
                dialog.attribute_text(), dialog.auto_detect_disable_value(), mark_reviewed=False,
            )
            self.db.set_setting("cost_sync_local_dirty", "1")
            changed_codes = list(dict.fromkeys([record["code"]] + list(changed or [])))
            parent = self.parent()
            if parent and hasattr(parent, "_refresh_cost_rows"):
                parent._refresh_cost_rows(changed_codes)
            if parent and hasattr(parent, "_refresh_main_products_for_specs"):
                parent._refresh_main_products_for_specs(changed_codes)
            record["attribute"] = dialog.attribute_text()
            record["disabled"] = dialog.auto_detect_disable_value()
            record["items"] = self.db.get_cost_combo_items(record["code"], suggest=False)
            row = self._row_for_code(record["code"])
            if row >= 0:
                self._set_component_cell(row, record["items"])
                self.table.setCurrentCell(row, 2)

    def confirm_record(self, record):
        code = str(record.get("code") or "").strip()
        if not code:
            return
        self._mark_reviewed([code], self.sender())

    def confirm_selected(self):
        records = [self._record(index.row()) for index in self.table.selectionModel().selectedRows(0)]
        codes = [record.get("code") for record in records if record]
        if not codes:
            QMessageBox.information(self, "提示", "请先选择一个或多个组合产品")
            return
        self._mark_reviewed(codes, self.bulk_confirm_button)

    def _mark_reviewed(self, codes, button=None):
        codes = list(dict.fromkeys(str(code or "").strip() for code in codes if str(code or "").strip()))
        if not codes:
            return
        if isinstance(button, QPushButton):
            button.setEnabled(False)
        try:
            self.db.safe_execute(
                f"UPDATE cost_library SET combo_reviewed=1 WHERE spec_code IN ({','.join('?' for _ in codes)})",
                tuple(codes),
            )
            self.db.set_setting("cost_sync_local_dirty", "1")
        except Exception as exc:
            if isinstance(button, QPushButton):
                button.setEnabled(True)
            QMessageBox.warning(self, "标记失败", str(exc))
            return
        if isinstance(button, QPushButton):
            button.setEnabled(True)
        for code in codes:
            self._remove_row_animated(code)

    def _row_for_code(self, code):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            record = item.data(Qt.UserRole) if item else None
            if record and str(record.get("code") or "") == code:
                return row
        return -1

    def _remove_row_animated(self, code):
        if code in self._removing_codes:
            return
        row = self._row_for_code(code)
        if row < 0:
            return
        self._removing_codes.add(code)
        animation = QVariantAnimation(self)
        animation.setDuration(140)
        animation.setStartValue(self.table.rowHeight(row))
        animation.setEndValue(0)
        animation.setEasingCurve(QEasingCurve.InOutCubic)

        def update_height(value):
            current_row = self._row_for_code(code)
            if current_row >= 0:
                self.table.setRowHeight(current_row, max(1, int(value)))

        def finish():
            current_row = self._row_for_code(code)
            if current_row >= 0:
                self.table.removeRow(current_row)
            self._removing_codes.discard(code)
            if animation in self._row_animations:
                self._row_animations.remove(animation)

        animation.valueChanged.connect(update_height)
        animation.finished.connect(finish)
        self._row_animations.append(animation)
        animation.start()

    def _sync_reviewed_rows(self, changed_codes=None):
        pending_rows = self._pending_rows(changed_codes)
        pending_codes = {str(row[0]) for row in pending_rows}
        visible_codes = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            record = item.data(Qt.UserRole) if item else None
            if record:
                visible_codes.append(str(record.get("code") or ""))
        for code in visible_codes:
            if code and (changed_codes is None or code in changed_codes) and code not in pending_codes:
                self._remove_row_animated(code)
        visible_set = set(visible_codes)
        for pending_row in pending_rows:
            if str(pending_row[0]) not in visible_set:
                self._append_row(pending_row)


class CostLibraryDialog(QDialog):
    """查看、编辑和管理成本库对话框。"""

    COL_CATEGORY = 0
    COL_IMAGE = 1
    COL_NAME = 2
    COL_CODE = 3
    COL_ATTRIBUTE = 4
    COL_QUANTITY = 5
    COL_PRODUCT_COST = 6
    COL_UNIT_WEIGHT = 7
    COL_SHIPPING_FEE = 8
    COL_MISC_FEE = 9
    COL_COST = 10
    COL_LISTED_COUNT = 11
    LOAD_VISIBLE_BATCH_SIZE = 8
    LOAD_VISIBLE_ROW_COUNT = 48
    LOAD_BACKGROUND_BATCH_SIZE = 128
    UNDO_LIMIT = 10
    UNDO_COST_COLUMNS = (
        "spec_code", "spec_name", "cost_price", "quantity", "sort_order",
        "source_bg_color", "category_label", "category_color", "manual_sort_order",
        "product_cost", "unit_weight", "shipping_fee", "misc_fee", "cost_calc_mode",
        "product_attribute", "product_attribute_combo_disabled",
        "product_attribute_is_combo", "combo_components_json", "combo_reviewed",
        "thumbnail_data", "thumbnail_manual",
    )

    CATEGORY_COLORS = [
        "#FFF2CC", "#DDEBF7", "#E2F0D9", "#FCE4D6", "#E4DFEC",
        "#D9EAD3", "#F4CCCC", "#D0E0E3", "#FCE5CD", "#D9D2E9",
        "#CFE2F3", "#EADCF8", "#D5E8D4", "#FFE599", "#D9EAF7",
    ]

    def __init__(self, db_manager, main_window=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.main_window = main_window or parent
        self._original_rows = {}
        self._row_by_spec_code = {}
        self._dirty_spec_codes = set()
        self._component_cost_values = {}
        self._combo_definitions = {}
        self._component_to_combos = {}
        self._loading = False
        self._populating_model = False
        self._recalculating = False
        self._save_pending = False
        self._combos_initialized = False
        self._load_generation = 0
        self._initial_load_pending = True
        self._cost_rows_cache = None
        self._thumbnail_icon_cache = {}
        self._thumbnail_scan_scheduled = False
        self._thumbnail_scan_running = False
        self._thumbnail_rescan_pending = False
        self._last_thumbnail_scan = 0.0
        self.combo_review_dialog = None
        self.history_dialog = None
        self._undo_stack = []
        self._redo_stack = []
        self._restoring_undo = False
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._run_auto_save)
        self.cost_mode = self._get_cost_mode()
        self.listing_cart = {}
        self.link_combination_dialog = None
        self.setWindowTitle("成本库管理")
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.resize(1480, 720)
        try:
            self.init_ui()
            self._setup_undo_shortcuts()
            self.lbl_count.setText("正在加载...")
            self.load_progress.setRange(0, 0)
            self.load_progress.setFormat("正在准备数据...")
            self.load_progress.show()
            QTimer.singleShot(0, self._run_initial_load)
        except Exception as e:
            import traceback

            print(traceback.format_exc())
            QMessageBox.critical(self, "严重错误", f"打开成本库窗口失败:\n{str(e)}\n\n请检查控制台详情。")
            self.reject()

    def _setup_button(self, button, tooltip="", danger=False):
        button.setToolTip(tooltip or button.text())
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(30)
        button.setStyleSheet(f"""
            QPushButton {{
                background: {'#fff5f5' if danger else '#f7f9fc'};
                color: {'#b42318' if danger else '#243447'};
                border: 1px solid {'#f3b8b8' if danger else '#cfd8e3'};
                border-radius: 6px;
                padding: 5px 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {'#ffe4e4' if danger else '#eaf2ff'};
                border-color: {'#e46b6b' if danger else '#7da7d9'};
            }}
            QPushButton:pressed {{
                background: {'#ffd1d1' if danger else '#d7e7fb'};
                padding-top: 6px;
                padding-bottom: 4px;
            }}
            QPushButton:disabled {{
                background: #eeeeee;
                color: #999999;
                border-color: #dddddd;
            }}
        """)
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "table_view") and self.model.rowCount() >= 0:
            if not hasattr(self, "_column_resize_timer"):
                self._column_resize_timer = QTimer(self)
                self._column_resize_timer.setSingleShot(True)
                self._column_resize_timer.timeout.connect(self._resize_columns_when_idle)
            self._column_resize_timer.start(120)

    def _resize_columns_when_idle(self):
        if self._loading:
            self._column_resize_timer.start(120)
            return
        self._resize_columns_for_content()

    def _focus_search(self):
        self.search_input.setFocus(Qt.ShortcutFocusReason)
        self.search_input.selectAll()

    def _get_cost_mode(self):
        if hasattr(self.db, "get_cost_library_mode"):
            return self.db.get_cost_library_mode()
        return "total"

    def on_cost_mode_changed(self):
        self.cost_mode = self.mode_combo.currentData() or "total"
        if hasattr(self.db, "set_cost_library_mode"):
            self.db.set_cost_library_mode(self.cost_mode)
        self._apply_cost_mode_visibility()
        self._reload_cached_data()

    def on_sort_mode_changed(self):
        if hasattr(self.db, "set_setting"):
            self.db.set_setting("cost_library_sort_mode", self.sort_combo.currentData() or "type")
        self._reload_cached_data()

    def _is_combo_spec(self, spec_name, product_attribute, combo_disabled, explicit_combo=0):
        if int(combo_disabled or 0):
            return False
        if int(explicit_combo or 0):
            return True
        return bool(re.search(r"\+|＋|﹢", str(spec_name or "")))

    def _set_name_combo_state(self, row, is_combo):
        item = self.model.item(row, self.COL_NAME)
        if item:
            item.setData(bool(is_combo), SpecNameBadgeDelegate.COMBO_STATE_ROLE)

    def _apply_cost_mode_visibility(self):
        if not hasattr(self, "table_view"):
            return
        detail = self.cost_mode == "detail"
        self.table_view.setColumnHidden(self.COL_QUANTITY, True)
        for col in (self.COL_PRODUCT_COST, self.COL_UNIT_WEIGHT, self.COL_SHIPPING_FEE, self.COL_MISC_FEE):
            self.table_view.setColumnHidden(col, not detail)
        if hasattr(self, "btn_shipping_rules"):
            self.btn_shipping_rules.setEnabled(detail)
            self.btn_misc_fee.setEnabled(detail)

    def init_ui(self):
        self.model = QStandardItemModel()
        layout = QVBoxLayout(self)

        self.cost_mode_controls = QWidget()
        mode_layout = QHBoxLayout(self.cost_mode_controls)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(QLabel("成本模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("总成本模式", "total")
        self.mode_combo.addItem("详细成本模式", "detail")
        self.mode_combo.setCurrentIndex(1 if self.cost_mode == "detail" else 0)
        self.mode_combo.currentIndexChanged.connect(self.on_cost_mode_changed)
        self.btn_shipping_rules = QPushButton("快递费设置")
        self._setup_button(self.btn_shipping_rules, "设置详细成本模式的快递费规则")
        self.btn_shipping_rules.clicked.connect(self.show_shipping_settings)
        self.btn_misc_fee = QPushButton("杂费设置")
        self._setup_button(self.btn_misc_fee, "设置详细成本模式的每规格固定杂费")
        self.btn_misc_fee.clicked.connect(self.show_misc_fee_settings)
        self.btn_lan_sync = QPushButton("局域网同步")
        self._setup_button(self.btn_lan_sync, "创建或加入组织，软件内成本变化会自动实时同步")
        self.btn_lan_sync.clicked.connect(self.show_lan_sync)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(self.btn_shipping_rules)
        mode_layout.addWidget(self.btn_misc_fee)
        mode_layout.addWidget(self.btn_lan_sync)
        mode_layout.addStretch()
        layout.addWidget(self.cost_mode_controls)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索商品类型/商品名称/规格编码:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品类型、商品名称或规格编码关键字，空格分隔...")
        self.search_shortcut = QShortcut(QKeySequence.Find, self)
        self.search_shortcut.activated.connect(self._focus_search)
        self._search_reload_timer = QTimer(self)
        self._search_reload_timer.setSingleShot(True)
        self._search_reload_timer.setInterval(120)
        self._search_reload_timer.timeout.connect(self._reload_cached_data)
        self.search_input.textChanged.connect(lambda _text: self._search_reload_timer.start())
        search_layout.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("按商品类型", "type")
        self.sort_combo.addItem("按导入顺序", "import")
        saved_sort = self.db.get_setting("cost_library_sort_mode", "type") if hasattr(self.db, "get_setting") else "type"
        sort_index = self.sort_combo.findData(saved_sort)
        if sort_index >= 0:
            self.sort_combo.setCurrentIndex(sort_index)
        self.sort_combo.currentIndexChanged.connect(self.on_sort_mode_changed)
        btn_refresh = QPushButton("刷新")
        self._setup_button(btn_refresh, "重新加载成本库数据")
        btn_refresh.clicked.connect(self._load_data_progressive)
        btn_import = QPushButton("导入成本表")
        self._setup_button(btn_import, "从成本表导入或更新成本库")
        btn_import.clicked.connect(self.import_cost_data)
        self.btn_price_test = QPushButton("测价")
        self._setup_button(self.btn_price_test, "打开测价窗口，测试多件价格和毛利")
        self.btn_price_test.clicked.connect(self.show_price_test)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.sort_combo)
        search_layout.addWidget(btn_import)
        search_layout.addWidget(self.btn_price_test)
        search_layout.addWidget(btn_refresh)
        self.btn_history = QPushButton("历史操作")
        self._setup_button(self.btn_history, "查看成本库的价格、名称、属性、图片和类型等操作记录")
        self.btn_history.clicked.connect(self.show_history)
        search_layout.addWidget(self.btn_history)
        layout.addLayout(search_layout)

        self.model.setHorizontalHeaderLabels([
            "商品类型", "图片", "商品名称", "规格编码", "产品属性", "数量", "产品成本", "重量（kg）",
            "快递费", "杂费", "总成本", "已上架规格数"
        ])
        self.model.itemChanged.connect(self.on_item_changed)

        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.setIconSize(QSize(58, 58))
        self._configure_column_widths()
        self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setWordWrap(True)
        self.table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table_view.setStyleSheet(
            "QTableView::item:hover { background-color: #ffffff; color: #000000; }"
        )
        self.table_view.installEventFilter(self)
        self.table_view.viewport().installEventFilter(self)
        self.table_view.clicked.connect(self.handle_cost_table_click)
        self.table_view.doubleClicked.connect(self.show_thumbnail_preview)
        self.table_view.doubleClicked.connect(self.open_product_attribute_editor)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_cost_table_context_menu)
        select_all_delegate = SelectAllLineEditDelegate(self.table_view)
        multiline_delegate = MultiLineTextEditDelegate(self.table_view)
        self.table_view.setItemDelegateForColumn(self.COL_CATEGORY, select_all_delegate)
        self.table_view.setItemDelegateForColumn(self.COL_NAME, SpecNameBadgeDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(self.COL_CODE, select_all_delegate)
        self.table_view.setItemDelegateForColumn(self.COL_QUANTITY, multiline_delegate)
        self.table_view.setItemDelegateForColumn(self.COL_ATTRIBUTE, FixedHeightWrapDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(self.COL_COST, select_all_delegate)
        self.table_view.setItemDelegateForColumn(self.COL_PRODUCT_COST, select_all_delegate)
        self.table_view.setItemDelegateForColumn(self.COL_UNIT_WEIGHT, select_all_delegate)
        self.table_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.table_view, 1)
        self._apply_cost_mode_visibility()

        self.listing_cart_widget = QWidget()
        self.listing_cart_widget.setFixedHeight(38)
        self.listing_cart_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cart_layout = QHBoxLayout(self.listing_cart_widget)
        cart_layout.setContentsMargins(0, 2, 0, 2)
        cart_layout.setSpacing(6)
        self.cart_title_label = QLabel("上架车（0）")
        self.cart_title_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.cart_title_label.setFixedWidth(78)
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setFixedHeight(34)
        self.cart_scroll.setFrameShape(QScrollArea.NoFrame)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.cart_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cart_content = QWidget()
        self.cart_chip_layout = QHBoxLayout(self.cart_content)
        self.cart_chip_layout.setContentsMargins(4, 2, 4, 2)
        self.cart_chip_layout.setSpacing(4)
        self.cart_scroll.setWidget(self.cart_content)
        self.btn_clear_cart = QPushButton("清空上架车")
        self.btn_clear_cart.setFixedHeight(28)
        self._setup_button(self.btn_clear_cart, "清空当前临时选择的上架规格")
        self.btn_clear_cart.clicked.connect(self.clear_listing_cart)
        cart_layout.addWidget(self.cart_title_label)
        cart_layout.addWidget(self.cart_scroll, 1)
        cart_layout.addWidget(self.btn_clear_cart)
        layout.addWidget(self.listing_cart_widget, 0)
        self.refresh_listing_cart_view()

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)
        self.lbl_count = QLabel("共 0 条数据")
        self.load_progress = QProgressBar()
        self.load_progress.setFixedSize(190, 18)
        self.load_progress.setTextVisible(True)
        self.load_progress.hide()
        btn_category_manage = QPushButton("商品类型管理")
        self._setup_button(btn_category_manage, "管理商品类型、颜色和类型内规格排序")
        btn_category_manage.clicked.connect(self.show_category_manage)
        self.btn_link_combos = QPushButton("商品类型链接")
        self._setup_button(self.btn_link_combos, "按商品类型查看和维护链接类型")
        self.btn_link_combos.clicked.connect(self.show_link_combinations)
        btn_unlisted = QPushButton("未上架规格")
        self._setup_button(btn_unlisted, "列出当前还没有上架的规格")
        btn_unlisted.clicked.connect(self.show_unlisted_specs)
        self.btn_combo_review = QPushButton("组合待处理")
        self._setup_button(self.btn_combo_review, "检查系统识别出的组合产品及其包含单品")
        self.btn_combo_review.clicked.connect(self.show_combo_review)
        btn_add_item = QPushButton("新增商品")
        self._setup_button(btn_add_item, "手动新增一条成本库规格")
        btn_add_item.clicked.connect(self.show_create_item)
        btn_create_link = QPushButton("创建链接")
        self._setup_button(btn_create_link, "用上架车或当前选中规格创建空白链接")
        btn_create_link.clicked.connect(self.create_selected_link)
        btn_del = QPushButton("删除选中项")
        self._setup_button(btn_del, "删除当前选中的成本库规格", danger=True)
        btn_del.clicked.connect(self.delete_selected)
        btn_clear = QPushButton("清空成本库")
        self._setup_button(btn_clear, "清空当前成本库数据", danger=True)
        btn_clear.clicked.connect(self.clear_all)
        btn_close = QPushButton("关闭")
        self._setup_button(btn_close, "关闭成本库窗口")
        btn_close.clicked.connect(self.reject)
        for button in (
            btn_category_manage, self.btn_link_combos, btn_unlisted, self.btn_combo_review, btn_add_item,
            btn_create_link, btn_clear, btn_del, btn_close,
        ):
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addWidget(self.load_progress)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_category_manage)
        btn_layout.addWidget(self.btn_link_combos)
        btn_layout.addWidget(btn_unlisted)
        btn_layout.addWidget(self.btn_combo_review)
        btn_layout.addWidget(btn_add_item)
        btn_layout.addWidget(btn_create_link)
        btn_layout.addWidget(btn_clear)
        btn_layout.addWidget(btn_del)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _run_initial_load(self):
        if self._initial_load_pending:
            self._load_data_progressive()

    def load_data(self):
        """Reload immediately for callers that need the complete model before returning."""
        self._initial_load_pending = False
        self._start_load(force_query=True, progressive=False)

    def _load_data_progressive(self, *_args):
        self._initial_load_pending = False
        self._start_load(force_query=True, progressive=True)

    def _reload_cached_data(self):
        self._initial_load_pending = False
        self._start_load(force_query=False, progressive=True)

    def _fetch_cost_rows(self):
        query = """SELECT cost_library.category_label, cost_library.spec_name, cost_library.spec_code,
                          COALESCE(cost_library.product_attribute, '') AS product_attribute,
                          COALESCE(cost_library.product_attribute_combo_disabled, 0) AS product_attribute_combo_disabled,
                          COALESCE(cost_library.product_attribute_is_combo, 0) AS product_attribute_is_combo,
                          cost_library.quantity, cost_library.cost_price,
                          cost_library.sort_order, cost_library.source_bg_color,
                          COALESCE(cost_categories.color, cost_library.category_color, '') AS category_color,
                          COALESCE(listed_specs.listed_count, 0) AS listed_count,
                          cost_library.manual_sort_order,
                          cost_categories.sort_order AS category_sort_order,
                          cost_library.product_cost, cost_library.unit_weight,
                          cost_library.shipping_fee, cost_library.misc_fee,
                          COALESCE(cost_library.cost_calc_mode, 'total') AS cost_calc_mode,
                          COALESCE(cost_library.combo_components_json, '') AS combo_components_json,
                          cost_library.thumbnail_data,
                          COALESCE(cost_library.thumbnail_manual, 0) AS thumbnail_manual
                   FROM cost_library
                   LEFT JOIN cost_categories ON cost_categories.label = cost_library.category_label
                   LEFT JOIN (
                       SELECT spec_code, COUNT(*) AS listed_count
                       FROM product_specs
                       WHERE COALESCE(spec_code, '') <> ''
                       GROUP BY spec_code
                   ) listed_specs ON listed_specs.spec_code = cost_library.spec_code
                   ORDER BY CASE WHEN COALESCE(cost_library.category_label, '') = '' THEN 1 ELSE 0 END,
                            cost_categories.sort_order,
                            cost_library.category_label,
                            CASE WHEN cost_library.manual_sort_order IS NULL THEN 1 ELSE 0 END,
                            cost_library.manual_sort_order,
                            cost_library.sort_order,
                            cost_library.spec_code"""
        return self.db.safe_fetchall(query)

    def _start_load(self, force_query, progressive):
        if self.model.signalsBlocked():
            self.model.blockSignals(False)
        self.table_view.setUpdatesEnabled(True)
        vertical_scroll = (
            self.table_view.verticalScrollBar().value()
            if hasattr(self, "table_view") and self.model.rowCount() else None
        )
        horizontal_scroll = (
            self.table_view.horizontalScrollBar().value()
            if hasattr(self, "table_view") and self.model.rowCount() else None
        )
        self._loading = True
        self._load_generation += 1
        load_generation = self._load_generation
        updates_disabled = False
        try:
            self.lbl_count.setText("正在准备数据...")
            self.load_progress.setRange(0, 0)
            self.load_progress.setFormat("正在准备数据...")
            self.load_progress.show()
            combo_changes = []
            if force_query and not self._combos_initialized:
                if hasattr(self.db, "detect_cost_combo_candidates"):
                    self.db.detect_cost_combo_candidates()
                if hasattr(self.db, "recalculate_cost_combinations_for_components"):
                    combo_changes = self.db.recalculate_cost_combinations_for_components(
                        record_history=True, source="combo"
                    )
                self._combos_initialized = True

            if force_query or self._cost_rows_cache is None:
                self._cost_rows_cache = self._fetch_cost_rows()
            source_rows = self._cost_rows_cache
            self._build_combo_preview_maps(source_rows)
            self._category_import_order = self._build_category_import_order(source_rows)
            all_sorted_rows = self._filter_and_sort_rows(source_rows, "")
            rows = self._filter_and_sort_rows(source_rows, self.search_input.text().strip())
            category_hues = self._category_hues_for_rows(all_sorted_rows)

            self.model.setRowCount(0)
            self._original_rows = {}
            self._row_by_spec_code = {}
            self._dirty_spec_codes.clear()
            total_rows = len(rows)
            self.model.setRowCount(total_rows)
            self.load_progress.setRange(0, max(total_rows, 1))
            self.load_progress.setValue(0)
            self.load_progress.setFormat("已加载 %v/%m")
            state = {
                "generation": load_generation,
                "rows": rows,
                "index": 0,
                "category_hues": category_hues,
                "gradient_total": max(total_rows - 1, 1),
                "vertical_scroll": vertical_scroll,
                "horizontal_scroll": horizontal_scroll,
                "combo_changes": combo_changes,
                "progressive": progressive,
                "updates_disabled": not progressive,
                "signals_blocked": not progressive,
                "brushes": {},
            }
            if not progressive:
                self.table_view.setUpdatesEnabled(False)
                self.model.blockSignals(True)
                updates_disabled = True
            self._append_load_batch(state)
        except Exception:
            self._fail_load(load_generation, updates_disabled)

    def _append_load_batch(self, state):
        generation = state["generation"]
        if generation != self._load_generation:
            return
        try:
            rows = state["rows"]
            start = state["index"]
            if not state["progressive"]:
                batch_size = max(len(rows), 1)
            elif start < self.LOAD_VISIBLE_ROW_COUNT:
                batch_size = self.LOAD_VISIBLE_BATCH_SIZE
            else:
                if not state["updates_disabled"]:
                    self.table_view.setUpdatesEnabled(False)
                    self.model.blockSignals(True)
                    state["updates_disabled"] = True
                    state["signals_blocked"] = True
                batch_size = self.LOAD_BACKGROUND_BATCH_SIZE
            end = min(start + batch_size, len(rows))
            self._populating_model = True
            try:
                for visible_index in range(start, end):
                    self._populate_cost_row(visible_index, rows[visible_index], state)
            finally:
                self._populating_model = False
            state["index"] = end
            if rows:
                self.load_progress.setValue(end)
                self.lbl_count.setText(f"正在加载 {end}/{len(rows)} 条...")
            if end < len(rows):
                QTimer.singleShot(0, lambda current=state: self._append_load_batch(current))
            else:
                self._finish_load(state)
        except Exception:
            self._fail_load(
                generation, state["updates_disabled"], state["signals_blocked"]
            )

    def _populate_cost_row(self, row_index, row_data, state):
        (
            category_label, spec_name, spec_code, product_attribute, combo_disabled,
            attr_is_combo, quantity, cost_price, _sort_order, _source_bg_color,
            _category_color, listed_count, _manual_sort_order, _category_sort_order,
            product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
            _combo_components_json, thumbnail_data, _thumbnail_manual,
        ) = row_data
        category_value = str(category_label or "")
        name_value = str(spec_name or "")
        code_value = str(spec_code or "")
        attribute_value = str(product_attribute or "")
        combo_disabled_value = int(combo_disabled or 0)
        attr_is_combo_value = int(attr_is_combo or 0)
        quantity_value = self._format_quantity(quantity)
        cost_value = float(cost_price) if cost_price is not None else None
        product_cost_value = float(product_cost) if product_cost is not None else None
        unit_weight_value = float(unit_weight) if unit_weight is not None else None
        shipping_value = float(shipping_fee) if shipping_fee is not None else None
        misc_value = float(misc_fee) if misc_fee is not None else None
        row_color = self._gradient_row_color(
            category_value, row_index, state["gradient_total"], state["category_hues"]
        )
        brush = state["brushes"].get(row_color)
        if brush is None and self._is_valid_hex_color(row_color):
            brush = QBrush(QColor(row_color))
            state["brushes"][row_color] = brush
        is_combo = self._is_combo_spec(
            name_value, attribute_value, combo_disabled_value, attr_is_combo_value
        )
        self._original_rows[code_value] = (
            category_value, name_value, attribute_value, combo_disabled_value,
            attr_is_combo_value, quantity_value, cost_value, product_cost_value,
            unit_weight_value, shipping_value, misc_value, str(cost_calc_mode or "total"),
        )
        self._row_by_spec_code[code_value] = row_index

        self._set_item(row_index, self.COL_CATEGORY, category_value, editable=True, bg_color=brush)
        self._set_thumbnail_item(row_index, thumbnail_data, brush)
        self._set_item(row_index, self.COL_NAME, name_value, editable=True, bg_color=brush)
        self._set_name_combo_state(row_index, is_combo)
        self._set_item(row_index, self.COL_CODE, code_value, editable=True, bg_color=brush)
        self.model.item(row_index, self.COL_CODE).setData(code_value, Qt.UserRole)
        self._set_item(row_index, self.COL_ATTRIBUTE, attribute_value, editable=False, bg_color=brush)
        attr_item = self.model.item(row_index, self.COL_ATTRIBUTE)
        if attr_item:
            attr_item.setData(combo_disabled_value, Qt.UserRole)
            attr_item.setData(attr_is_combo_value, Qt.UserRole + 1)
        self._set_item(
            row_index, self.COL_QUANTITY, quantity_value,
            editable=(self.cost_mode == "detail"), bg_color=brush,
        )
        self._set_item(
            row_index, self.COL_PRODUCT_COST,
            "" if product_cost_value is None else f"{product_cost_value:.2f}",
            editable=(self.cost_mode == "detail" and not is_combo), bg_color=brush,
        )
        self._set_item(
            row_index, self.COL_UNIT_WEIGHT,
            "" if unit_weight_value is None else f"{unit_weight_value:.4f}".rstrip("0").rstrip("."),
            editable=(self.cost_mode == "detail" and not is_combo), bg_color=brush,
        )
        self._set_item(
            row_index, self.COL_SHIPPING_FEE,
            "" if shipping_value is None else f"{shipping_value:.2f}",
            editable=False, bg_color=brush,
        )
        self._set_item(
            row_index, self.COL_MISC_FEE,
            "" if misc_value is None else f"{misc_value:.2f}",
            editable=False, bg_color=brush,
        )
        self._set_item(
            row_index, self.COL_COST, "" if cost_value is None else f"{cost_value:.2f}",
            editable=(self.cost_mode != "detail" and not is_combo), bg_color=brush,
        )
        self._set_item(
            row_index, self.COL_LISTED_COUNT, str(int(listed_count or 0)),
            editable=False, bg_color=brush,
        )
        if is_combo:
            for column in (self.COL_PRODUCT_COST, self.COL_UNIT_WEIGHT, self.COL_COST):
                item = self.model.item(row_index, column)
                if item:
                    item.setToolTip("组合产品由包含单品的成本和重量自动计算，不可手动修改")
        if code_value in self.listing_cart:
            self.listing_cart[code_value].update({
                "spec_name": name_value,
                "spec_code": code_value,
                "category_label": category_value,
                "quantity": quantity_value,
            })

    def _finish_load(self, state):
        generation = state["generation"]
        if generation != self._load_generation:
            return
        if state["signals_blocked"]:
            self.model.blockSignals(False)
        if state["updates_disabled"]:
            self.table_view.setUpdatesEnabled(True)
        if not state["rows"]:
            self.load_progress.setValue(1)
        self.load_progress.setFormat("正在整理显示...")
        if hasattr(self, "_column_resize_timer"):
            self._column_resize_timer.stop()
        self._resize_columns_for_content()
        self.refresh_listing_cart_view()
        if state["vertical_scroll"] is not None:
            self.table_view.verticalScrollBar().setValue(state["vertical_scroll"])
        if state["horizontal_scroll"] is not None:
            self.table_view.horizontalScrollBar().setValue(state["horizontal_scroll"])
        self.lbl_count.setText(f"共 {self.model.rowCount()} 条数据")
        self.load_progress.setFormat("加载完成 %v/%m")
        self.table_view.viewport().update()
        self._loading = False
        QTimer.singleShot(350, lambda current=generation: self._hide_finished_load_progress(current))
        self._schedule_missing_thumbnail_scan()
        if state["combo_changes"]:
            QTimer.singleShot(
                0,
                lambda codes=tuple(state["combo_changes"]): self._refresh_main_products_for_specs(codes),
            )

    def _fail_load(self, generation, updates_disabled=False, signals_blocked=False):
        import traceback

        print(traceback.format_exc())
        if generation != self._load_generation:
            return
        if signals_blocked:
            self.model.blockSignals(False)
        if updates_disabled:
            self.table_view.setUpdatesEnabled(True)
        self._loading = False
        self.lbl_count.setText("加载失败")
        self.load_progress.hide()

    def _hide_finished_load_progress(self, generation):
        if generation == self._load_generation and self.load_progress.value() >= self.load_progress.maximum():
            self.load_progress.hide()

    def _build_combo_preview_maps(self, rows):
        self._component_cost_values = {
            str(row[2] or ""): (row[14], row[15]) for row in rows if str(row[2] or "")
        }
        self._combo_definitions = {}
        self._component_to_combos = {}
        for row in rows:
            combo_code = str(row[2] or "")
            if not combo_code or not int(row[5] or 0):
                continue
            try:
                raw_items = json.loads(row[19] or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            items = []
            for raw_item in raw_items if isinstance(raw_items, list) else []:
                component_code = str(raw_item.get("spec_code") or raw_item.get("code") or "").strip()
                if not component_code:
                    continue
                try:
                    quantity = max(float(raw_item.get("quantity") or 1), 1)
                except (TypeError, ValueError):
                    quantity = 1
                items.append((component_code, quantity))
                self._component_to_combos.setdefault(component_code, set()).add(combo_code)
            if items:
                self._combo_definitions[combo_code] = items

    def _preview_combo_dependents(self, component_code):
        row = self._row_by_spec_code.get(component_code)
        if row is not None:
            product_item = self.model.item(row, self.COL_PRODUCT_COST)
            weight_item = self.model.item(row, self.COL_UNIT_WEIGHT)
            try:
                self._component_cost_values[component_code] = (
                    float(product_item.text()), float(weight_item.text())
                )
            except (AttributeError, TypeError, ValueError):
                return
        pending = list(self._component_to_combos.get(component_code, ()))
        visited = set()
        previous_recalculating = self._recalculating
        self._recalculating = True
        try:
            while pending:
                combo_code = pending.pop(0)
                if combo_code in visited:
                    continue
                visited.add(combo_code)
                product_cost = 0.0
                unit_weight = 0.0
                valid = True
                for item_code, quantity in self._combo_definitions.get(combo_code, ()):
                    values = self._component_cost_values.get(item_code)
                    if not values or values[0] is None or values[1] is None:
                        valid = False
                        break
                    product_cost += float(values[0]) * quantity
                    unit_weight += float(values[1]) * quantity
                if valid:
                    product_cost = round(product_cost, 4)
                    unit_weight = round(unit_weight, 4)
                    total, shipping, misc, _ = self.db.calculate_detailed_cost(product_cost, 1, unit_weight)
                    self._component_cost_values[combo_code] = (product_cost, unit_weight)
                    display_values = {
                        self.COL_PRODUCT_COST: f"{product_cost:.2f}",
                        self.COL_UNIT_WEIGHT: f"{unit_weight:.4f}".rstrip("0").rstrip("."),
                        self.COL_SHIPPING_FEE: f"{shipping:.2f}",
                        self.COL_MISC_FEE: f"{misc:.2f}",
                        self.COL_COST: f"{total:.2f}",
                    }
                else:
                    self._component_cost_values[combo_code] = (None, None)
                    display_values = {
                        self.COL_PRODUCT_COST: "", self.COL_UNIT_WEIGHT: "",
                        self.COL_SHIPPING_FEE: "", self.COL_MISC_FEE: "", self.COL_COST: "",
                    }
                combo_row = self._row_by_spec_code.get(combo_code)
                if combo_row is not None:
                    for column, text in display_values.items():
                        item = self.model.item(combo_row, column)
                        if item and item.text() != text:
                            item.setText(text)
                pending.extend(self._component_to_combos.get(combo_code, ()))
        finally:
            self._recalculating = previous_recalculating

    def _configure_column_widths(self):
        header = self.table_view.horizontalHeader()
        header.setStretchLastSection(False)
        for col in range(self.model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_view.verticalHeader().setDefaultSectionSize(44)
        self.table_view.verticalHeader().setMinimumSectionSize(36)
        self.table_view.verticalHeader().setMaximumSectionSize(120)

    def _resize_columns_for_content(self):
        widths = {
            self.COL_CATEGORY: 110,
            self.COL_IMAGE: 70,
            self.COL_NAME: 300,
            self.COL_CODE: 190,
            self.COL_ATTRIBUTE: 150,
            self.COL_QUANTITY: 76,
            self.COL_PRODUCT_COST: 92,
            self.COL_UNIT_WEIGHT: 96,
            self.COL_SHIPPING_FEE: 82,
            self.COL_MISC_FEE: 76,
            self.COL_COST: 86,
            self.COL_LISTED_COUNT: 110,
        }
        for col, width in widths.items():
            self.table_view.setColumnWidth(col, width)

        self.table_view.resizeRowsToContents()
        self._cap_row_heights()

    def _cap_row_heights(self):
        if not hasattr(self, "table_view"):
            return
        max_height = 76
        for row in range(self.model.rowCount()):
            if self.table_view.rowHeight(row) > max_height:
                self.table_view.setRowHeight(row, max_height)

    def _format_quantity(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return ""
        numeric_text = text.replace(",", "")
        try:
            number = float(numeric_text)
        except ValueError:
            return text
        if number.is_integer():
            return str(int(number))
        return str(int(round(number)))

    def handle_cost_table_click(self, index):
        if index.isValid() and QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.toggle_listing_cart_row(index.row())

    def eventFilter(self, watched, event):
        if (
            watched in (self.table_view, self.table_view.viewport())
            and event.type() == QEvent.KeyPress
            and event.matches(QKeySequence.Copy)
        ):
            index = self.table_view.currentIndex()
            if index.isValid():
                QApplication.clipboard().setText(str(index.data(Qt.DisplayRole) or ""))
            return True
        if (
            watched in (self.table_view, self.table_view.viewport())
            and event.type() == QEvent.KeyPress
            and bool(event.text())
            and event.text() in "0123456789."
            and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)
        ):
            index = self.table_view.currentIndex()
            if (
                index.isValid()
                and index.column() == self.COL_PRODUCT_COST
                and index.flags() & Qt.ItemIsEditable
            ):
                self.table_view.edit(index)
                QTimer.singleShot(0, lambda text=event.text(): self._seed_product_cost_editor(text))
                return True
        return super().eventFilter(watched, event)

    def _seed_product_cost_editor(self, text):
        editor = QApplication.focusWidget()
        if isinstance(editor, QLineEdit) and self.table_view.isAncestorOf(editor):
            editor.setText(text)
            editor.setCursorPosition(len(text))

    def open_product_attribute_editor(self, index):
        if not index.isValid() or index.column() != self.COL_ATTRIBUTE:
            return
        attribute_item = self.model.item(index.row(), self.COL_ATTRIBUTE)
        code_item = self.model.item(index.row(), self.COL_CODE)
        name_item = self.model.item(index.row(), self.COL_NAME)
        current_value = attribute_item.text().strip() if attribute_item else ""
        spec_code = code_item.text().strip() if code_item else ""
        spec_name = name_item.text().strip() if name_item else ""
        affected_before = {spec_code}
        affected_before.update(self._component_to_combos.get(spec_code, ()))
        before_rows = self._capture_cost_rows(affected_before)
        auto_disabled = bool(attribute_item.data(Qt.UserRole)) if attribute_item else False
        is_combo = bool(name_item.data(SpecNameBadgeDelegate.COMBO_STATE_ROLE)) if name_item else False
        dialog = ProductAttributeDialog(self.db, current_value, spec_code, spec_name, auto_disabled, is_combo, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        new_value = dialog.attribute_text()
        combo_disabled = dialog.auto_detect_disable_value()
        attr_is_combo = dialog.is_combo_product()
        if hasattr(self.db, "save_cost_combo_definition"):
            changed = self.db.save_cost_combo_definition(
                spec_code, bool(attr_is_combo), dialog.component_items(), new_value, combo_disabled
            )
            changed_codes = list(dict.fromkeys([spec_code] + list(changed or [])))
            after_rows = self._capture_cost_rows(set(changed_codes) | affected_before)
            self._push_cost_undo("修改产品属性", before_rows, after_rows)
            self.db.set_setting("cost_sync_local_dirty", "1")
            self._show_copy_hint("组合信息已保存" if attr_is_combo else "产品属性已保存", 1000)
            self._refresh_cost_rows(changed_codes)
            self._refresh_main_products_for_specs(changed_codes)
            return
        if attribute_item:
            attribute_item.setText(new_value)
            attribute_item.setData(combo_disabled, Qt.UserRole)
            attribute_item.setData(attr_is_combo, Qt.UserRole + 1)
        else:
            self._set_item(index.row(), self.COL_ATTRIBUTE, new_value, editable=False)
            new_item = self.model.item(index.row(), self.COL_ATTRIBUTE)
            if new_item:
                new_item.setData(combo_disabled, Qt.UserRole)
                new_item.setData(attr_is_combo, Qt.UserRole + 1)
        self._set_name_combo_state(index.row(), self._is_combo_spec(spec_name, new_value, combo_disabled, attr_is_combo))
        name_item = self.model.item(index.row(), self.COL_NAME)
        if name_item:
            name_item.emitDataChanged()
        QTimer.singleShot(0, self._resize_columns_for_content)

    def _show_copy_hint(self, text, duration=1000):
        main_window = self.main_window
        if main_window and hasattr(main_window, "show_toast"):
            main_window.show_toast(text, duration)
        else:
            QToolTip.showText(QCursor.pos(), text, self, self.rect(), duration)

    def _setup_undo_shortcuts(self):
        self.undo_shortcut = QShortcut(QKeySequence.Undo, self)
        self.undo_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.undo_shortcut.activated.connect(self.undo_last_cost_change)
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.redo_shortcut.activated.connect(self.redo_last_cost_change)

    def _commit_active_cost_editor(self):
        focus_widget = QApplication.focusWidget()
        if focus_widget and (
            focus_widget is self.table_view or self.table_view.isAncestorOf(focus_widget)
        ):
            self.table_view.setFocus(Qt.OtherFocusReason)
            QApplication.processEvents()
        if self._dirty_spec_codes:
            self._auto_save_timer.stop()
            self.save_changes(auto_save=True)

    def _capture_cost_rows(self, spec_codes):
        codes = list(dict.fromkeys(
            str(code or "").strip() for code in (spec_codes or []) if str(code or "").strip()
        ))
        if not codes:
            return {}
        columns = ", ".join(self.UNDO_COST_COLUMNS)
        result = {}
        for start in range(0, len(codes), 800):
            batch = codes[start:start + 800]
            placeholders = ",".join("?" for _ in batch)
            for row in self.db.safe_fetchall(
                f"SELECT {columns} FROM cost_library WHERE spec_code IN ({placeholders})",
                tuple(batch),
            ):
                result[str(row[0])] = tuple(row)
        return result

    def _push_cost_undo(self, label, before, after, renames=()):
        if self._restoring_undo or before == after:
            return
        self._undo_stack.append({
            "label": str(label or "修改"),
            "before": dict(before),
            "after": dict(after),
            "renames": tuple(renames or ()),
        })
        del self._undo_stack[:-self.UNDO_LIMIT]
        self._redo_stack.clear()

    def _replace_loaded_spec_code(self, old_code, new_code):
        old_code = str(old_code or "").strip()
        new_code = str(new_code or "").strip()
        if not old_code or not new_code or old_code == new_code:
            return
        row = self._row_by_spec_code.pop(old_code, None)
        if row is None:
            for candidate in range(self.model.rowCount()):
                item = self.model.item(candidate, self.COL_CODE)
                if item and str(item.data(Qt.UserRole) or item.text()).strip() == old_code:
                    row = candidate
                    break
        previous_populating = self._populating_model
        self._populating_model = True
        try:
            if row is not None:
                item = self.model.item(row, self.COL_CODE)
                if item:
                    item.setText(new_code)
                    item.setData(new_code, Qt.UserRole)
                self._row_by_spec_code[new_code] = row
        finally:
            self._populating_model = previous_populating
        original = self._original_rows.pop(old_code, None)
        if original is not None:
            self._original_rows[new_code] = original
        component_value = self._component_cost_values.pop(old_code, None)
        if component_value is not None:
            self._component_cost_values[new_code] = component_value
        combo = self._combo_definitions.pop(old_code, None)
        if combo is not None:
            self._combo_definitions[new_code] = combo
        dependents = self._component_to_combos.pop(old_code, None)
        if dependents is not None:
            self._component_to_combos[new_code] = dependents
        for combo_codes in self._component_to_combos.values():
            if old_code in combo_codes:
                combo_codes.discard(old_code)
                combo_codes.add(new_code)
        cart_item = self.listing_cart.pop(old_code, None)
        if cart_item is not None:
            cart_item["spec_code"] = new_code
            self.listing_cart[new_code] = cart_item
            self.refresh_listing_cart_view()
        self._dirty_spec_codes.discard(old_code)
        self._dirty_spec_codes.discard(new_code)

    def _restore_cost_action(self, command, undo):
        target = command["before"] if undo else command["after"]
        source = command["after"] if undo else command["before"]
        renames = [
            (new_code, old_code) if undo else (old_code, new_code)
            for old_code, new_code in command.get("renames", ())
        ]
        candidate_codes = set(target) | set(source)
        for old_code, new_code in renames:
            candidate_codes.update((old_code, new_code))
        columns = self.UNDO_COST_COLUMNS
        update_columns = columns[1:]
        placeholders = ",".join("?" for _ in columns)
        assignments = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
        try:
            self._restoring_undo = True
            self.db.conn.execute("BEGIN TRANSACTION")
            self.db.cursor.execute(
                "UPDATE cost_history_control SET enabled=1, source=? WHERE id=1",
                ("undo" if undo else "redo",),
            )
            for old_code, new_code in renames:
                old_exists = self.db.cursor.execute(
                    "SELECT 1 FROM cost_library WHERE spec_code=?", (old_code,)
                ).fetchone()
                new_exists = self.db.cursor.execute(
                    "SELECT 1 FROM cost_library WHERE spec_code=?", (new_code,)
                ).fetchone()
                if old_exists and not new_exists:
                    self.db.rename_cost_spec_code(
                        old_code, new_code, manage_transaction=False, mark_dirty=False
                    )
                elif not new_exists:
                    raise ValueError(f"无法恢复规格编码：{old_code}")
            current = self._capture_cost_rows(candidate_codes)
            for code in set(current) - set(target):
                self.db.cursor.execute("DELETE FROM cost_library WHERE spec_code=?", (code,))
            for row in target.values():
                self.db.cursor.execute(
                    f"""INSERT INTO cost_library ({", ".join(columns)})
                        VALUES ({placeholders})
                        ON CONFLICT(spec_code) DO UPDATE SET {assignments}""",
                    row,
                )
            self.db.cursor.execute(
                "UPDATE cost_history_control SET enabled=1, source='manual' WHERE id=1"
            )
            self.db.conn.commit()
        except Exception as exc:
            self.db.conn.rollback()
            try:
                self.db.cursor.execute(
                    "UPDATE cost_history_control SET enabled=1, source='manual' WHERE id=1"
                )
                self.db.conn.commit()
            except Exception:
                pass
            QMessageBox.critical(self, "撤销失败", str(exc))
            return False
        finally:
            self._restoring_undo = False

        for old_code, new_code in renames:
            self._replace_loaded_spec_code(old_code, new_code)
        mapped_source = {
            dict(renames).get(code, code)
            for code in source
        }
        if mapped_source != set(target):
            self.load_data()
        else:
            self._refresh_cost_rows(target)
            self._reorder_visible_cost_rows()
        self.db.set_setting("cost_sync_local_dirty", "1")
        self._refresh_main_products_for_specs(candidate_codes)
        self._show_copy_hint("已撤销" if undo else "已恢复", 1000)
        return True

    def undo_last_cost_change(self):
        self._commit_active_cost_editor()
        if not self._undo_stack:
            self._show_copy_hint("没有可撤销的操作", 1000)
            return
        command = self._undo_stack.pop()
        if self._restore_cost_action(command, True):
            self._redo_stack.append(command)
            del self._redo_stack[:-self.UNDO_LIMIT]
        else:
            self._undo_stack.append(command)

    def redo_last_cost_change(self):
        self._commit_active_cost_editor()
        if not self._redo_stack:
            self._show_copy_hint("没有可恢复的操作", 1000)
            return
        command = self._redo_stack.pop()
        if self._restore_cost_action(command, False):
            self._undo_stack.append(command)
            del self._undo_stack[:-self.UNDO_LIMIT]
        else:
            self._redo_stack.append(command)

    def _row_to_cart_spec(self, row):
        name_item = self.model.item(row, self.COL_NAME)
        code_item = self.model.item(row, self.COL_CODE)
        category_item = self.model.item(row, self.COL_CATEGORY)
        quantity_item = self.model.item(row, self.COL_QUANTITY)
        spec_code = code_item.text().strip() if code_item else ""
        if not spec_code:
            return None
        return {
            "spec_name": name_item.text().strip() if name_item else "",
            "spec_code": spec_code,
            "category_label": category_item.text().strip() if category_item else "",
            "quantity": quantity_item.text().strip() if quantity_item else "",
        }

    def toggle_listing_cart_row(self, row):
        spec = self._row_to_cart_spec(row)
        if not spec:
            return
        spec_code = spec["spec_code"]
        if spec_code in self.listing_cart:
            self.listing_cart.pop(spec_code, None)
            self._show_copy_hint("已移出上架车")
        else:
            self.listing_cart[spec_code] = spec
            self._show_copy_hint("已加入上架车")
        self.refresh_listing_cart_view()

    def remove_listing_cart_item(self, spec_code):
        self.listing_cart.pop(spec_code, None)
        self.refresh_listing_cart_view()

    def clear_listing_cart(self):
        if not self.listing_cart:
            return
        self.listing_cart.clear()
        self.refresh_listing_cart_view()
        self._show_copy_hint("已清空上架车")

    def refresh_listing_cart_view(self):
        if not hasattr(self, "cart_chip_layout"):
            return
        while self.cart_chip_layout.count():
            item = self.cart_chip_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.cart_title_label.setText(f"上架车（{len(self.listing_cart)}）")
        self.btn_clear_cart.setEnabled(bool(self.listing_cart))
        if not self.listing_cart:
            placeholder = QLabel("Ctrl+单击规格加入上架车")
            placeholder.setStyleSheet("color: #888; padding-left: 6px;")
            self.cart_chip_layout.addWidget(placeholder)
            self.cart_chip_layout.addStretch()
            return
        for spec_code, spec in self.listing_cart.items():
            category = spec.get("category_label") or "未分类"
            spec_name = spec.get("spec_name") or spec_code
            chip = QWidget()
            chip.setObjectName("listingCartChip")
            chip.setFixedSize(220, 28)
            chip.setToolTip(f"规格编码：{spec_code}\n数量：{spec.get('quantity') or '-'}\n点击移出上架车")
            chip.setStyleSheet(
                "QWidget#listingCartChip { background-color: #fffdf2; border: 1px solid #f1d98b; border-radius: 8px; }"
                "QWidget#listingCartChip:hover { background-color: #ffffff; color: #000000; border: 1px solid #d0d0d0; }"
                "QWidget#listingCartChip:hover QLabel { color: #000000; }"
            )
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 2, 3, 2)
            chip_layout.setSpacing(4)
            category_label = QLabel(category)
            category_label.setFixedWidth(62)
            category_label.setStyleSheet("color: #8a5a00; font-size: 11px; font-weight: bold; border: none; background: transparent;")
            category_label.setToolTip(category)
            name_label = QLabel(spec_name)
            name_label.setFixedWidth(118)
            name_label.setStyleSheet("color: #245269; font-size: 12px; font-weight: bold; border: none; background: transparent;")
            name_label.setToolTip(spec_name)
            remove_btn = QPushButton("×")
            remove_btn.setFixedSize(18, 18)
            remove_btn.setStyleSheet(
                "QPushButton { border: none; background-color: #f3d47a; color: #704600; border-radius: 10px; font-weight: bold; }"
                "QPushButton:hover { background-color: #e8b94f; }"
            )
            remove_btn.clicked.connect(lambda _checked=False, code=spec_code: self.remove_listing_cart_item(code))
            chip_layout.addWidget(category_label)
            chip_layout.addWidget(name_label, 1)
            chip_layout.addWidget(remove_btn)
            self.cart_chip_layout.addWidget(chip)
        self.cart_chip_layout.addStretch()

    def show_cost_table_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        action_open_material = menu.addAction("打开该规格素材库")
        action_replace_image = None
        if index.column() == self.COL_IMAGE:
            action_replace_image = menu.addAction("从素材库选择/替换缩略图")
        action_move = None
        if index.column() == self.COL_CATEGORY:
            action_move = menu.addAction("移动到其他商品类型")
        selected = menu.exec_(self.table_view.viewport().mapToGlobal(pos))
        if selected == action_open_material:
            self.open_row_material_library(index.row())
        elif action_replace_image is not None and selected == action_replace_image:
            self.replace_row_thumbnail_from_material(index.row())
        elif action_move is not None and selected == action_move:
            self.move_row_category(index.row())

    @staticmethod
    def _thumbnail_bytes_from_path(path):
        source = QPixmap(str(path or ""))
        if source.isNull():
            return b""
        result = b""
        for max_size, quality in ((720, 78), (600, 70), (480, 62), (360, 55)):
            scaled = source.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            canvas = QPixmap(scaled.size())
            canvas.fill(Qt.white)
            painter = QPainter(canvas)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            raw = QByteArray()
            buffer = QBuffer(raw)
            buffer.open(QIODevice.WriteOnly)
            canvas.save(buffer, "JPG", quality)
            buffer.close()
            result = bytes(raw)
            if len(result) <= 96 * 1024:
                return result
        return result if len(result) <= 96 * 1024 else b""

    def replace_row_thumbnail_from_material(self, row):
        code_item = self.model.item(row, self.COL_CODE)
        spec_code = code_item.text().strip() if code_item else ""
        if not spec_code or not self.main_window or not hasattr(self.main_window, "material_images_for_cost_specs"):
            QMessageBox.information(self, "提示", "当前无法读取该规格的素材库。")
            return
        paths = self.main_window.material_images_for_cost_specs([spec_code]).get(spec_code, [])
        if not paths:
            QMessageBox.information(self, "提示", "该规格的素材库里还没有可用图片。")
            return
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "从素材库选择缩略图",
            paths[0],
            "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.gif)",
        )
        if not selected_path:
            return
        image_data = self._thumbnail_bytes_from_path(selected_path)
        if not image_data:
            QMessageBox.warning(self, "替换失败", "无法读取或压缩所选图片。")
            return
        before_rows = self._capture_cost_rows([spec_code])
        if self.db.set_cost_thumbnail(spec_code, image_data, manual=True):
            self._push_cost_undo(
                "替换商品图片",
                before_rows,
                self._capture_cost_rows([spec_code]),
            )
            self._update_thumbnail_cell(spec_code, image_data)
            self._show_copy_hint("缩略图已替换并等待局域网同步", 1000)

    def show_thumbnail_preview(self, index):
        if not index.isValid() or index.column() != self.COL_IMAGE:
            return
        item = self.model.item(index.row(), self.COL_IMAGE)
        image_data = bytes(item.data(Qt.UserRole) or b"") if item else b""
        pixmap = QPixmap()
        if not image_data or not pixmap.loadFromData(image_data):
            return
        try:
            from .material_library import MaterialImageViewerDialog
        except ImportError:
            from material_library import MaterialImageViewerDialog
        code_item = self.model.item(index.row(), self.COL_CODE)
        name_item = self.model.item(index.row(), self.COL_NAME)
        spec_code = code_item.text().strip() if code_item else ""
        spec_name = name_item.text().strip() if name_item else ""
        dialog = MaterialImageViewerDialog(
            parent=self,
            image_data=image_data,
            window_title=spec_name or "商品图片",
        )
        dialog.scroll_area.setToolTip("按住 Ctrl 滚动鼠标滚轮可放大或缩小")
        save_button = dialog.button_box.addButton("保存图片", QDialogButtonBox.ActionRole)
        save_button.setToolTip("将当前白底图另存到电脑")
        save_button.clicked.connect(
            lambda: self.save_thumbnail_as_file(image_data, spec_name)
        )
        material_button = dialog.button_box.addButton(
            "同步到本机素材库", QDialogButtonBox.ActionRole
        )
        material_button.setToolTip("保存为该规格在本机素材库中的白底图")
        material_button.clicked.connect(
            lambda: self.sync_thumbnail_to_local_material(spec_code, image_data)
        )
        dialog.exec_()

    @staticmethod
    def _write_thumbnail_file(image_data, path):
        pixmap = QPixmap()
        if not path or not pixmap.loadFromData(bytes(image_data or b"")):
            return ""
        root, extension = os.path.splitext(path)
        if not extension:
            path = root + ".jpg"
            extension = ".jpg"
        image_format = {
            ".png": "PNG",
            ".bmp": "BMP",
            ".webp": "WEBP",
        }.get(extension.lower(), "JPG")
        return path if pixmap.save(path, image_format, 95) else ""

    def save_thumbnail_as_file(self, image_data, spec_name=""):
        safe_name = re.sub(r'[<>:"/\\|?*]', "", str(spec_name or "")).strip() or "商品"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存白底图",
            f"{safe_name[:60]}-白底图.jpg",
            "JPEG 图片 (*.jpg *.jpeg);;PNG 图片 (*.png);;WebP 图片 (*.webp);;BMP 图片 (*.bmp)",
        )
        if not path:
            return
        saved_path = self._write_thumbnail_file(image_data, path)
        if not saved_path:
            QMessageBox.warning(self, "保存失败", "无法保存该图片。")
            return
        self._show_copy_hint("图片已保存", 1000)

    def sync_thumbnail_to_local_material(self, spec_code, image_data):
        if not spec_code:
            QMessageBox.warning(self, "同步失败", "当前规格没有规格编码。")
            return
        if not self.main_window or not hasattr(self.main_window, "save_cost_thumbnail_to_material"):
            QMessageBox.warning(self, "同步失败", "当前无法访问本机素材库。")
            return
        try:
            path = self.main_window.save_cost_thumbnail_to_material(spec_code, image_data)
        except Exception as exc:
            QMessageBox.warning(self, "同步失败", str(exc))
            return
        if path:
            self._show_copy_hint("已同步到本机素材库", 1000)

    def open_row_material_library(self, row):
        code_item = self.model.item(row, self.COL_CODE)
        spec_code = code_item.text().strip() if code_item else ""
        if not spec_code:
            QMessageBox.warning(self, "提示", "当前行没有规格编码，无法打开素材库。")
            return
        if self.main_window and hasattr(self.main_window, "open_product_material_library"):
            self.main_window.open_product_material_library(spec_code)
        else:
            QMessageBox.warning(self, "提示", "主窗口没有可用的素材库入口。")

    def move_row_category(self, row):
        code_item = self.model.item(row, self.COL_CODE)
        category_item = self.model.item(row, self.COL_CATEGORY)
        spec_code = code_item.text().strip() if code_item else ""
        current_category = category_item.text().strip() if category_item else ""
        if not spec_code:
            QMessageBox.warning(self, "提示", "当前行没有规格编码，无法移动商品类型。")
            return

        rows = self.db.safe_fetchall(
            """SELECT label FROM cost_categories
               WHERE COALESCE(label, '') <> ''
               ORDER BY sort_order, label"""
        )
        categories = [str(row_data[0]).strip() for row_data in rows if str(row_data[0] or "").strip()]
        categories = [label for label in categories if label != current_category]
        if not categories:
            QMessageBox.warning(self, "提示", "没有可移动到的其他商品类型，请先在商品类型管理中创建或导入商品类型。")
            return

        target, ok = QInputDialog.getItem(
            self,
            "移动到其他商品类型",
            f"将规格 [{spec_code}] 移动到：",
            categories,
            0,
            False,
        )
        if not ok or not target:
            return

        before_rows = self._capture_cost_rows([spec_code])
        try:
            if hasattr(self.db, "update_cost_spec_category"):
                self.db.update_cost_spec_category(spec_code, target)
            else:
                category_color = self._category_color(target)
                self.db.safe_execute(
                    "UPDATE cost_library SET category_label=?, category_color=? WHERE spec_code=?",
                    (target, category_color, spec_code),
                )
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
            self.db.set_setting("cost_sync_local_dirty", "1")
        except Exception as e:
            QMessageBox.critical(self, "移动失败", f"移动商品类型失败：{e}")
            return

        self._push_cost_undo(
            "移动商品类型",
            before_rows,
            self._capture_cost_rows([spec_code]),
        )
        self._refresh_cost_rows([spec_code])
        self._refresh_main_products_for_specs([spec_code])
        self._show_copy_hint("已移动")

    def _split_search_terms(self, search_text):
        return split_search_terms(search_text)

    def _base_product_key(self, name):
        text = str(name or "").strip().lower()
        if not text:
            return ""
        normalized = re.sub(r"[（(【\[].*?[）)】\]]", "", text)
        normalized = re.sub(rf"\d+(?:\.\d+)?\s*(?:{CostCategoryManageDialog.QUANTITY_UNITS})", "", normalized)
        normalized = re.sub(rf"(?:{CostCategoryManageDialog.QUANTITY_UNITS})\s*\d+(?:\.\d+)?", "", normalized)
        normalized = re.sub(r"\d+(?:\.\d+)?", "", normalized)
        normalized = re.sub(rf"(?:{CostCategoryManageDialog.QUANTITY_UNITS})", "", normalized)
        normalized = re.sub(r"[\\/\-_\s,，。；;：:、]+", "", normalized)
        return normalized if len(normalized) >= 2 else text

    def _quantity_rank(self, spec_name, quantity):
        text = str(quantity or "").strip()
        if text:
            try:
                return float(re.sub(r"[^\d.]", "", text) or "0")
            except ValueError:
                pass
        match = re.search(rf"(\d+(?:\.\d+)?)\s*(?:{CostCategoryManageDialog.QUANTITY_UNITS})", str(spec_name or ""))
        if match:
            return float(match.group(1))
        return 10**9

    def _sort_mode(self):
        return self.sort_combo.currentData() if hasattr(self, "sort_combo") else "type"

    def _category_family_key(self, label):
        text = str(label or "").strip().lower()
        text = re.sub(r"(套装|组合|套餐|礼盒|系列|单本|多本|单品|多件|装)$", "", text)
        text = re.sub(r"\d+(?:\.\d+)?\s*(?:本|个|件|套|包|盒|张|册|份)", "", text)
        text = re.sub(r"[\\/\-_\s,，。；;：:、（）()【】\[\]]+", "", text)
        return text or str(label or "").strip().lower()

    def _category_hues_for_rows(self, rows):
        categories = []
        for row in rows:
            category = str(row[0] or "").strip() or "未分类"
            if category not in categories:
                categories.append(category)
        colors = {}
        total_categories = max(len(categories), 1)
        for index, category in enumerate(categories):
            hue = int(index * 359 / total_categories)
            colors[category] = QColor.fromHsl(hue, 128, 204).name().upper()
        return colors

    def _gradient_row_color(self, category, row_index, row_total, category_hues):
        category = str(category or "").strip() or "未分类"
        return category_hues.get(category, "#FFFFFF")

    def _build_category_import_order(self, rows):
        order = {}
        for row in sorted(rows, key=lambda item: (item[8] if item[8] is not None else 10**9, str(item[2] or ""))):
            category = str(row[0] or "").strip()
            if category and category not in order:
                order[category] = len(order)
        return order

    def _row_sort_key(self, row):
        category_label, spec_name, spec_code, _product_attribute, _combo_disabled, _attr_is_combo, quantity, _cost_price, sort_order, _source_bg_color, _category_color, _listed_count, manual_sort_order, category_sort_order = row[:14]
        if self._sort_mode() == "import":
            return (
                1 if not str(category_label or "").strip() else 0,
                getattr(self, "_category_import_order", {}).get(str(category_label or "").strip(), 10**9),
                str(category_label or ""),
                sort_order if sort_order is not None else 10**9,
                str(spec_code or ""),
            )
        return (
            1 if not str(category_label or "").strip() else 0,
            self._category_family_key(category_label),
            category_sort_order if category_sort_order is not None else 10**9,
            str(category_label or ""),
            0 if manual_sort_order is not None else 1,
            manual_sort_order if manual_sort_order is not None else 10**9,
            self._base_product_key(spec_name),
            self._quantity_rank(spec_name, quantity),
            sort_order if sort_order is not None else 10**9,
            str(spec_code or ""),
        )

    def _sort_cost_rows(self, rows):
        return sorted(rows, key=self._row_sort_key)

    def _filter_and_sort_rows(self, rows, search_text):
        search_text = search_text.strip().lower()
        terms = self._split_search_terms(search_text)
        if not terms:
            return self._sort_cost_rows(rows)

        exact_single_codes = {
            str(row[2] or "")
            for row in rows
            if not int(row[5] or 0)
            and str(row[1] or "").strip().casefold() == search_text.casefold()
        }
        related_combo_codes = set()
        if exact_single_codes:
            for row in rows:
                if not int(row[5] or 0):
                    continue
                try:
                    components = json.loads(row[19] or "[]")
                except (TypeError, ValueError, json.JSONDecodeError):
                    components = []
                if any(
                    str(component.get("spec_code") or component.get("code") or "") in exact_single_codes
                    for component in components if isinstance(component, dict)
                ):
                    related_combo_codes.add(str(row[2] or ""))

        matched = []
        for row in rows:
            category_label, spec_name, spec_code, product_attribute, _combo_disabled, _attr_is_combo, quantity, cost_price, sort_order, source_bg_color, category_color = row[:11]
            full_hit, hit_count = match_score(search_text, terms, category_label, spec_name, spec_code, product_attribute, quantity)
            related_combo = str(spec_code or "") in related_combo_codes
            exact_name = str(spec_name or "").strip().casefold() == search_text.casefold()
            if hit_count <= 0 and not related_combo:
                continue
            matched.append((exact_name, related_combo, full_hit, hit_count, self._row_sort_key(row), row))

        matched.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], item[4]))
        return [item[5] for item in matched]

    def _set_item(self, row, col, text, editable, bg_color=""):
        item = QStandardItem(str(text))
        item.setEditable(editable)
        item.setTextAlignment(Qt.AlignCenter)
        if isinstance(bg_color, QBrush):
            item.setBackground(bg_color)
        elif self._is_valid_hex_color(bg_color):
            item.setBackground(QBrush(QColor(bg_color)))
        self.model.setItem(row, col, item)

    def _set_thumbnail_item(self, row, image_data, bg_color=""):
        item = QStandardItem()
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignCenter)
        raw = bytes(image_data or b"")
        item.setData(raw, Qt.UserRole)
        if raw:
            cache_key = hashlib.sha1(raw).digest()
            icon = self._thumbnail_icon_cache.get(cache_key)
            if icon is None:
                pixmap = QPixmap()
                if pixmap.loadFromData(raw):
                    icon = QIcon(pixmap.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    self._thumbnail_icon_cache[cache_key] = icon
            if icon is not None:
                item.setIcon(icon)
                item.setToolTip("双击放大；右键可从素材库替换")
        if isinstance(bg_color, QBrush):
            item.setBackground(bg_color)
        elif self._is_valid_hex_color(bg_color):
            item.setBackground(QBrush(QColor(bg_color)))
        self.model.setItem(row, self.COL_IMAGE, item)

    def _update_thumbnail_cell(self, spec_code, image_data):
        self._cost_rows_cache = None
        row = self._row_by_spec_code.get(str(spec_code or ""))
        if row is None:
            return
        category_item = self.model.item(row, self.COL_CATEGORY)
        color = category_item.background().color().name() if category_item else ""
        previous_loading = self._loading
        previous_populating = self._populating_model
        self._loading = True
        self._populating_model = True
        try:
            self._set_thumbnail_item(row, image_data, color)
            self.table_view.setRowHeight(row, max(self.table_view.rowHeight(row), 64))
        finally:
            self._populating_model = previous_populating
            self._loading = previous_loading

    def _schedule_missing_thumbnail_scan(self, delay=250):
        if (
            self._thumbnail_scan_scheduled
            or self._thumbnail_scan_running
            or time.monotonic() - self._last_thumbnail_scan < 2
            or not self.main_window
            or not hasattr(self.main_window, "material_images_for_cost_specs")
        ):
            return
        self._thumbnail_scan_scheduled = True
        QTimer.singleShot(max(0, int(delay)), self._seed_missing_thumbnails_from_material)

    def refresh_missing_thumbnails(self):
        self._last_thumbnail_scan = 0.0
        if self._thumbnail_scan_running:
            self._thumbnail_rescan_pending = True
            return
        self._schedule_missing_thumbnail_scan(delay=0)

    def _seed_missing_thumbnails_from_material(self):
        self._thumbnail_scan_scheduled = False
        if self._thumbnail_scan_running:
            return
        self._thumbnail_scan_running = True
        try:
            added = 0
            inherited_codes = self.db.inherit_single_multiplier_combo_thumbnails()
            if inherited_codes:
                self._refresh_cost_rows(inherited_codes)
                added += len(inherited_codes)
            missing_codes = [
                str(row[0]) for row in self.db.safe_fetchall(
                    """SELECT spec_code FROM cost_library
                       WHERE COALESCE(spec_code, '')<>''
                         AND COALESCE(product_attribute_is_combo, 0)=0
                         AND LENGTH(COALESCE(thumbnail_data, X''))=0"""
                )
            ]
            if missing_codes:
                paths = self.main_window.material_images_for_cost_specs(missing_codes, white_only=True)
                for spec_code, path in paths.items():
                    image_data = self._thumbnail_bytes_from_path(path)
                    if image_data and self.db.set_cost_thumbnail(
                        spec_code, image_data, manual=False, only_if_empty=True
                    ):
                        self._update_thumbnail_cell(spec_code, image_data)
                        added += 1
                inherited_codes = self.db.inherit_single_multiplier_combo_thumbnails()
                if inherited_codes:
                    self._refresh_cost_rows(inherited_codes)
                    added += len(inherited_codes)
            if added:
                self._show_copy_hint(f"已从素材库补充 {added} 张白底图", 1000)
        except Exception as exc:
            print(f"成本库识别白底图失败: {exc}")
        finally:
            self._last_thumbnail_scan = time.monotonic()
            self._thumbnail_scan_running = False
            if self._thumbnail_rescan_pending:
                self._thumbnail_rescan_pending = False
                QTimer.singleShot(0, self.refresh_missing_thumbnails)

    def _is_valid_hex_color(self, color):
        return isinstance(color, str) and bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", color.strip()))

    def _parse_required_price(self, text):
        value = str(text).replace("¥", "").replace("$", "").replace(",", "").strip()
        if value == "":
            raise ValueError("成本价不能为空")
        price = float(value)
        if price < 0:
            raise ValueError("成本价不能小于 0")
        return price

    def _parse_optional_price(self, text):
        value = str(text).replace("¥", "").replace("$", "").replace(",", "").strip()
        if value == "":
            return None
        price = float(value)
        if price < 0:
            raise ValueError("测价不能小于 0")
        return price

    def _parse_optional_non_negative(self, text, field):
        value = str(text).replace("¥", "").replace("$", "").replace(",", "").strip()
        if value == "":
            return None
        parsed = float(value)
        if parsed < 0:
            raise ValueError(f"{field}不能小于 0")
        return parsed

    def _parse_required_non_negative(self, text, field):
        parsed = self._parse_optional_non_negative(text, field)
        if parsed is None:
            raise ValueError(f"{field}不能为空")
        return parsed

    def on_item_changed(self, item):
        if self._populating_model or self._recalculating:
            return
        code_item = self.model.item(item.row(), self.COL_CODE)
        spec_code = code_item.text().strip() if code_item else ""
        original_code = str(code_item.data(Qt.UserRole) or spec_code).strip() if code_item else ""
        if original_code:
            self._dirty_spec_codes.add(original_code)
        if item.column() in (self.COL_QUANTITY, self.COL_PRODUCT_COST, self.COL_UNIT_WEIGHT, self.COL_COST):
            self.recalculate_row(item.row())
            if item.column() in (self.COL_PRODUCT_COST, self.COL_UNIT_WEIGHT) and spec_code:
                self._preview_combo_dependents(spec_code)
        elif item.column() in (self.COL_CATEGORY, self.COL_NAME):
            QTimer.singleShot(0, lambda row=item.row(): self.table_view.resizeRowToContents(row))
        self._auto_save_timer.start(120)

    def _run_auto_save(self):
        if self._loading or self._recalculating or self._save_pending:
            self._auto_save_timer.start(200)
            return
        self._save_pending = True
        try:
            self.save_changes(auto_save=True)
        finally:
            self._save_pending = False

    def recalculate_row(self, row):
        cost_item = self.model.item(row, self.COL_COST)
        if not cost_item:
            return

        self._recalculating = True
        try:
            if self.cost_mode == "detail":
                product_item = self.model.item(row, self.COL_PRODUCT_COST)
                weight_item = self.model.item(row, self.COL_UNIT_WEIGHT)
                quantity_item = self.model.item(row, self.COL_QUANTITY)
                shipping_item = self.model.item(row, self.COL_SHIPPING_FEE)
                misc_item = self.model.item(row, self.COL_MISC_FEE)
                product_text = product_item.text().strip() if product_item else ""
                weight_text = weight_item.text().strip() if weight_item else ""
                code_item = self.model.item(row, self.COL_CODE)
                old_code = str(code_item.data(Qt.UserRole) or code_item.text()).strip() if code_item else ""
                old_mode = self._original_rows.get(
                    old_code, ("", "", "", 0, 0, "", None, None, None, None, None, "total")
                )[11]
                if old_mode == "detail" or product_text or weight_text:
                    product_cost = self._parse_optional_non_negative(product_text, "产品成本")
                    unit_weight = self._parse_optional_non_negative(weight_text, "重量")
                    if product_cost is not None and unit_weight is not None:
                        quantity = quantity_item.text().strip() if quantity_item else ""
                        name_item = self.model.item(row, self.COL_NAME)
                        is_combo = bool(name_item.data(SpecNameBadgeDelegate.COMBO_STATE_ROLE)) if name_item else False
                        total_cost, shipping_fee, misc_fee, _total_weight = self.db.calculate_detailed_cost(
                            product_cost, 1 if is_combo else quantity, unit_weight
                        )
                        cost_item.setText(f"{total_cost:.2f}")
                    else:
                        cost_item.setText("")
                        shipping_fee = misc_fee = None
                    if shipping_item:
                        shipping_item.setText("" if shipping_fee is None else f"{shipping_fee:.2f}")
                    if misc_item:
                        misc_item.setText("" if misc_fee is None else f"{misc_fee:.2f}")
            elif cost_item.text().strip():
                self._parse_required_price(cost_item.text())
        except ValueError:
            return
        finally:
            self._recalculating = False

    def save_changes(self, auto_save=False):
        updates = []
        category_changed_codes = []
        dirty_codes = set(self._dirty_spec_codes) if auto_save else None
        if auto_save and not dirty_codes:
            return

        for row in range(self.model.rowCount()):
            code_item = self.model.item(row, self.COL_CODE)
            new_code = code_item.text().strip() if code_item else ""
            old_code = str(code_item.data(Qt.UserRole) or new_code).strip() if code_item else ""
            if not old_code or (dirty_codes is not None and old_code not in dirty_codes):
                continue
            if not new_code:
                QMessageBox.warning(self, "规格编码错误", f"第 {row + 1} 行：规格编码不能为空")
                return
            if new_code != old_code and self.db.safe_fetchall(
                "SELECT 1 FROM cost_library WHERE spec_code=?", (new_code,)
            ):
                QMessageBox.warning(self, "规格编码错误", f"规格编码已存在：{new_code}")
                return
            category_item = self.model.item(row, self.COL_CATEGORY)
            name_item = self.model.item(row, self.COL_NAME)
            attribute_item = self.model.item(row, self.COL_ATTRIBUTE)
            quantity_item = self.model.item(row, self.COL_QUANTITY)
            product_item = self.model.item(row, self.COL_PRODUCT_COST)
            weight_item = self.model.item(row, self.COL_UNIT_WEIGHT)
            shipping_item = self.model.item(row, self.COL_SHIPPING_FEE)
            misc_item = self.model.item(row, self.COL_MISC_FEE)
            cost_item = self.model.item(row, self.COL_COST)
            if not cost_item:
                continue

            category_label = category_item.text().strip() if category_item else ""
            spec_name = name_item.text().strip() if name_item else ""
            product_attribute = attribute_item.text().strip() if attribute_item else ""
            combo_disabled = int(attribute_item.data(Qt.UserRole) or 0) if attribute_item else 0
            attr_is_combo = int(attribute_item.data(Qt.UserRole + 1) or 0) if attribute_item else 0
            quantity = quantity_item.text().strip() if quantity_item else ""
            old_category, old_name, old_attribute, old_combo_disabled, old_attr_is_combo, old_quantity, old_cost, old_product_cost, old_unit_weight, old_shipping_fee, old_misc_fee, old_mode = self._original_rows.get(
                old_code, ("", "", "", 0, 0, "", None, None, None, None, None, "total")
            )
            try:
                product_text = product_item.text().strip() if product_item else ""
                weight_text = weight_item.text().strip() if weight_item else ""
                use_detail = self.cost_mode == "detail" and (
                    old_mode == "detail" or product_text or weight_text
                )
                product_cost = None
                unit_weight = None
                shipping_fee = None
                misc_fee = None
                cost_calc_mode = "total"
                if use_detail:
                    product_cost = self._parse_optional_non_negative(product_text, "产品成本")
                    unit_weight = self._parse_optional_non_negative(weight_text, "重量")
                    if product_cost is not None and unit_weight is not None:
                        new_cost, shipping_fee, misc_fee, _total_weight = self.db.calculate_detailed_cost(
                            product_cost, 1 if attr_is_combo else quantity, unit_weight
                        )
                    else:
                        new_cost = None
                    cost_item.setText("" if new_cost is None else f"{new_cost:.2f}")
                    if shipping_item:
                        shipping_item.setText("" if shipping_fee is None else f"{shipping_fee:.2f}")
                    if misc_item:
                        misc_item.setText("" if misc_fee is None else f"{misc_fee:.2f}")
                    cost_calc_mode = "detail"
                else:
                    new_cost = self._parse_required_price(cost_item.text())
            except ValueError as e:
                QMessageBox.warning(self, "成本格式错误", f"第 {row + 1} 行 [{new_code}]：{e}")
                return

            code_changed = new_code != old_code
            category_changed = category_label != old_category
            name_changed = spec_name != old_name
            attribute_changed = product_attribute != old_attribute
            combo_disabled_changed = combo_disabled != int(old_combo_disabled or 0)
            attr_is_combo_changed = attr_is_combo != int(old_attr_is_combo or 0)
            quantity_changed = quantity != old_quantity
            cost_changed = (
                (old_cost is None) != (new_cost is None)
                or (
                    old_cost is not None and new_cost is not None
                    and abs(new_cost - old_cost) > 0.001
                )
            )
            detail_changed = (
                quantity_changed
                or old_mode != cost_calc_mode
                or ((old_product_cost is None) != (product_cost is None))
                or (old_product_cost is not None and product_cost is not None and abs(product_cost - old_product_cost) > 0.001)
                or ((old_unit_weight is None) != (unit_weight is None))
                or (old_unit_weight is not None and unit_weight is not None and abs(unit_weight - old_unit_weight) > 0.0001)
                or ((old_shipping_fee is None) != (shipping_fee is None))
                or (old_shipping_fee is not None and shipping_fee is not None and abs(shipping_fee - old_shipping_fee) > 0.001)
                or ((old_misc_fee is None) != (misc_fee is None))
                or (old_misc_fee is not None and misc_fee is not None and abs(misc_fee - old_misc_fee) > 0.001)
            )
            if code_changed or category_changed or name_changed or attribute_changed or combo_disabled_changed or attr_is_combo_changed or cost_changed or detail_changed:
                category_color = self._category_color(category_label) if category_label else ""
                updates.append((
                    old_code, new_code, category_label, category_color, spec_name, quantity,
                    product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
                    new_cost, product_attribute, combo_disabled, attr_is_combo,
                ))
            if category_changed:
                category_changed_codes.append(new_code)
        if not updates:
            if dirty_codes is not None:
                self._dirty_spec_codes.difference_update(dirty_codes)
            if not auto_save:
                self._show_copy_hint("没有需要保存的修改", 1000)
            return

        before_codes = set()
        for update in updates:
            old_code = update[0]
            before_codes.add(old_code)
            before_codes.update(self._component_to_combos.get(old_code, ()))
        before_rows = self._capture_cost_rows(before_codes)
        renames = [(update[0], update[1]) for update in updates if update[0] != update[1]]
        changed_codes = list(dict.fromkeys(update[1] for update in updates))
        try:
            self.db.conn.execute("BEGIN TRANSACTION")
            for old_code, new_code, category_label, category_color, spec_name, quantity, product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode, new_cost, product_attribute, combo_disabled, attr_is_combo in updates:
                if old_code != new_code:
                    self.db.rename_cost_spec_code(
                        old_code, new_code, manage_transaction=False, mark_dirty=False
                    )
                self.db.cursor.execute(
                    """UPDATE cost_library
                       SET category_label=?, category_color=?, spec_name=?, quantity=?,
                           product_cost=?, unit_weight=?, shipping_fee=?, misc_fee=?, cost_calc_mode=?,
                           cost_price=?, product_attribute=?, product_attribute_combo_disabled=?, product_attribute_is_combo=?
                       WHERE spec_code=?""",
                    (
                        category_label, category_color, spec_name, quantity,
                        product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
                        new_cost, product_attribute, combo_disabled, attr_is_combo, new_code,
                    ),
                )

            if category_changed_codes:
                placeholders = ",".join("?" for _ in category_changed_codes)
                product_ids = self.db.safe_fetchall(
                    f"SELECT DISTINCT product_id FROM product_specs WHERE spec_code IN ({placeholders})",
                    tuple(category_changed_codes),
                )
                for (product_id,) in product_ids:
                    label = self.db.calculate_product_category_label(product_id)
                    self.db.cursor.execute(
                        "UPDATE products SET product_category_label=? WHERE id=?",
                        (label, product_id),
                    )
            self.db.conn.commit()
        except Exception as e:
            self.db.conn.rollback()
            QMessageBox.critical(self, "保存失败", f"保存成本库修改失败：{e}")
            return

        if hasattr(self.db, "recalculate_cost_combinations_for_components"):
            changed_codes.extend(
                self.db.recalculate_cost_combinations_for_components(
                    changed_codes, record_history=True, source="manual"
                )
            )
            changed_codes = list(dict.fromkeys(changed_codes))

        rename_map = dict(renames)
        after_codes = set(changed_codes)
        after_codes.update(rename_map.get(code, code) for code in before_codes)
        after_rows = self._capture_cost_rows(after_codes)
        self._push_cost_undo("修改成本库", before_rows, after_rows, renames)
        for old_code, new_code in renames:
            self._replace_loaded_spec_code(old_code, new_code)
        self._show_copy_hint(
            f"已自动保存 {len(updates)} 条修改", 1000
        )
        if hasattr(self.db, "set_setting"):
            self.db.set_setting("cost_sync_local_dirty", "1")
        self._dirty_spec_codes.difference_update(update[0] for update in updates)
        self._refresh_cost_rows(changed_codes)
        if renames:
            self._reorder_visible_cost_rows()
        QTimer.singleShot(
            0, lambda codes=tuple(changed_codes): self._refresh_main_products_for_specs(codes)
        )

    def _refresh_cost_rows(self, spec_codes):
        self._cost_rows_cache = None
        codes = list(dict.fromkeys(str(code) for code in (spec_codes or []) if code))
        if not codes:
            return
        rows = []
        for start in range(0, len(codes), 800):
            batch = codes[start:start + 800]
            placeholders = ",".join("?" for _ in batch)
            rows.extend(self.db.safe_fetchall(
                f"""SELECT cost_library.spec_code, COALESCE(cost_library.category_label, ''),
                           COALESCE(cost_library.spec_name, ''), COALESCE(cost_library.product_attribute, ''),
                           COALESCE(cost_library.product_attribute_combo_disabled, 0),
                           COALESCE(cost_library.product_attribute_is_combo, 0),
                           COALESCE(cost_library.quantity, ''), cost_library.cost_price,
                           cost_library.product_cost, cost_library.unit_weight,
                           cost_library.shipping_fee, cost_library.misc_fee,
                           COALESCE(cost_library.cost_calc_mode, 'total'),
                           COALESCE(cost_library.combo_components_json, ''), cost_library.thumbnail_data,
                           (SELECT COUNT(*) FROM product_specs
                            WHERE product_specs.spec_code=cost_library.spec_code) AS listed_count
                    FROM cost_library
                    WHERE cost_library.spec_code IN ({placeholders})""",
                tuple(batch),
            ))
        previous_loading = self._loading
        previous_populating = self._populating_model
        self._loading = True
        self._populating_model = True
        try:
            cart_changed = False
            visible_category_colors = {}
            refreshed_codes = set(codes)
            for visible_row in range(self.model.rowCount()):
                code_item = self.model.item(visible_row, self.COL_CODE)
                if code_item and code_item.text().strip() in refreshed_codes:
                    continue
                category_item = self.model.item(visible_row, self.COL_CATEGORY)
                if not category_item:
                    continue
                brush = category_item.background()
                if brush.style() != Qt.NoBrush:
                    visible_category_colors.setdefault(
                        category_item.text().strip(), brush.color().name()
                    )
            fallback_category_colors = {}
            for code, category, name, attribute, combo_disabled, is_combo, quantity, cost, product_cost, weight, shipping, misc, mode, combo_json, thumbnail_data, listed_count in rows:
                code = str(code)
                row = self._row_by_spec_code.get(code)
                if row is not None:
                    code_item = self.model.item(row, self.COL_CODE)
                    if code_item:
                        code_item.setData(code, Qt.UserRole)
                    values = {
                        self.COL_CATEGORY: str(category or ""),
                        self.COL_NAME: str(name or ""),
                        self.COL_ATTRIBUTE: str(attribute or ""),
                        self.COL_QUANTITY: self._format_quantity(quantity),
                        self.COL_PRODUCT_COST: "" if product_cost is None else f"{float(product_cost):.2f}",
                        self.COL_UNIT_WEIGHT: "" if weight is None else f"{float(weight):.4f}".rstrip("0").rstrip("."),
                        self.COL_SHIPPING_FEE: "" if shipping is None else f"{float(shipping):.2f}",
                        self.COL_MISC_FEE: "" if misc is None else f"{float(misc):.2f}",
                        self.COL_COST: "" if cost is None else f"{float(cost):.2f}",
                        self.COL_LISTED_COUNT: str(int(listed_count or 0)),
                    }
                    for column, text in values.items():
                        item = self.model.item(row, column)
                        if item and item.text() != text:
                            item.setText(text)
                    attribute_item = self.model.item(row, self.COL_ATTRIBUTE)
                    if attribute_item:
                        attribute_item.setData(int(combo_disabled or 0), Qt.UserRole)
                        attribute_item.setData(int(is_combo or 0), Qt.UserRole + 1)
                    combo_state = self._is_combo_spec(name, attribute, combo_disabled, is_combo)
                    self._set_name_combo_state(row, combo_state)
                    for column in (self.COL_PRODUCT_COST, self.COL_UNIT_WEIGHT, self.COL_COST):
                        item = self.model.item(row, column)
                        if item:
                            item.setEditable(
                                (column != self.COL_COST and self.cost_mode == "detail" and not combo_state)
                                or (column == self.COL_COST and self.cost_mode != "detail" and not combo_state)
                            )
                            item.setToolTip(
                                "组合产品由包含单品的成本和重量自动计算，不可手动修改"
                                if combo_state else ""
                            )
                    raw = bytes(thumbnail_data or b"")
                    image_item = self.model.item(row, self.COL_IMAGE)
                    if image_item is not None and bytes(image_item.data(Qt.UserRole) or b"") != raw:
                        color_item = self.model.item(row, self.COL_CATEGORY)
                        color = color_item.background().color().name() if color_item else ""
                        self._set_thumbnail_item(row, raw, color)
                    category_key = str(category or "").strip()
                    target_color = visible_category_colors.get(category_key, "")
                    if not self._is_valid_hex_color(target_color):
                        if category_key not in fallback_category_colors:
                            fallback_category_colors[category_key] = (
                                self._category_color(category_key) if category_key else ""
                            )
                        target_color = fallback_category_colors[category_key]
                    if self._is_valid_hex_color(target_color):
                        brush = QBrush(QColor(target_color))
                        for column in range(self.model.columnCount()):
                            item = self.model.item(row, column)
                            if item:
                                item.setBackground(brush)
                    self.table_view.resizeRowToContents(row)
                    if self.table_view.rowHeight(row) > 76:
                        self.table_view.setRowHeight(row, 76)
                    if code in self.listing_cart:
                        self.listing_cart[code].update({
                            "spec_name": str(name or ""),
                            "category_label": str(category or ""),
                            "quantity": self._format_quantity(quantity),
                        })
                        cart_changed = True
                self._original_rows[code] = (
                    str(category or ""), str(name or ""), str(attribute or ""),
                    int(combo_disabled or 0), int(is_combo or 0), self._format_quantity(quantity),
                    None if cost is None else float(cost), None if product_cost is None else float(product_cost),
                    None if weight is None else float(weight),
                    None if shipping is None else float(shipping),
                    None if misc is None else float(misc), str(mode or "total"),
                )
                self._component_cost_values[code] = (product_cost, weight)
                self._combo_definitions.pop(code, None)
                for combo_codes in self._component_to_combos.values():
                    combo_codes.discard(code)
                if int(is_combo or 0):
                    try:
                        raw_items = json.loads(combo_json or "[]")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        raw_items = []
                    items = []
                    for raw_item in raw_items if isinstance(raw_items, list) else []:
                        component_code = str(raw_item.get("spec_code") or raw_item.get("code") or "").strip()
                        if not component_code:
                            continue
                        try:
                            component_quantity = max(float(raw_item.get("quantity") or 1), 1)
                        except (TypeError, ValueError):
                            component_quantity = 1
                        items.append((component_code, component_quantity))
                        self._component_to_combos.setdefault(component_code, set()).add(code)
                    if items:
                        self._combo_definitions[code] = items
            if cart_changed:
                self.refresh_listing_cart_view()
        finally:
            self._populating_model = previous_populating
            self._loading = previous_loading

    def _reorder_visible_cost_rows(self):
        self._cost_rows_cache = None
        current_codes = [
            self.model.item(row, self.COL_CODE).text().strip()
            for row in range(self.model.rowCount())
            if self.model.item(row, self.COL_CODE)
        ]
        if not current_codes:
            return
        rows = self.db.safe_fetchall(
            """SELECT cost_library.category_label, cost_library.spec_name, cost_library.spec_code,
                      COALESCE(cost_library.product_attribute, ''),
                      COALESCE(cost_library.product_attribute_combo_disabled, 0),
                      COALESCE(cost_library.product_attribute_is_combo, 0),
                      cost_library.quantity, cost_library.cost_price, cost_library.sort_order,
                      cost_library.source_bg_color,
                      COALESCE(cost_categories.color, cost_library.category_color, ''),
                      0, cost_library.manual_sort_order, cost_categories.sort_order
               FROM cost_library
               LEFT JOIN cost_categories ON cost_categories.label=cost_library.category_label"""
        )
        current_set = set(current_codes)
        self._category_import_order = self._build_category_import_order(rows)
        desired_rows = self._filter_and_sort_rows(
            [row for row in rows if str(row[2] or "") in current_set],
            self.search_input.text().strip(),
        )
        desired_codes = [str(row[2] or "") for row in desired_rows]
        if desired_codes == current_codes:
            return

        selected_codes = {
            self.model.item(index.row(), self.COL_CODE).text().strip()
            for index in self.table_view.selectionModel().selectedRows()
            if self.model.item(index.row(), self.COL_CODE)
        }
        current_code = ""
        current_index = self.table_view.currentIndex()
        if current_index.isValid():
            code_item = self.model.item(current_index.row(), self.COL_CODE)
            current_code = code_item.text().strip() if code_item else ""
        heights = {
            code: self.table_view.rowHeight(row)
            for row, code in enumerate(current_codes)
        }
        vertical_scroll = self.table_view.verticalScrollBar().value()
        horizontal_scroll = self.table_view.horizontalScrollBar().value()
        previous_loading = self._loading
        previous_populating = self._populating_model
        self._loading = True
        self._populating_model = True
        self.table_view.setUpdatesEnabled(False)
        try:
            desired_set = set(desired_codes)
            for row in range(len(current_codes) - 1, -1, -1):
                if current_codes[row] not in desired_set:
                    self.model.removeRow(row)
                    current_codes.pop(row)
            for target_row, code in enumerate(desired_codes):
                if target_row < len(current_codes) and current_codes[target_row] == code:
                    continue
                try:
                    source_row = current_codes.index(code, target_row)
                except ValueError:
                    continue
                items = self.model.takeRow(source_row)
                self.model.insertRow(target_row, items)
                current_codes.insert(target_row, current_codes.pop(source_row))
            self._row_by_spec_code = {code: row for row, code in enumerate(current_codes)}
            category_hues = self._category_hues_for_rows(self._sort_cost_rows(rows))
            for row, code in enumerate(current_codes):
                self.table_view.setRowHeight(row, heights.get(code, self.table_view.rowHeight(row)))
                category_item = self.model.item(row, self.COL_CATEGORY)
                category = category_item.text().strip() if category_item else ""
                color = self._gradient_row_color(category, row, len(current_codes), category_hues)
                if self._is_valid_hex_color(color):
                    brush = QBrush(QColor(color))
                    for column in range(self.model.columnCount()):
                        item = self.model.item(row, column)
                        if item and item.background().color() != brush.color():
                            item.setBackground(brush)
            selection_model = self.table_view.selectionModel()
            selection_model.clearSelection()
            for code in selected_codes:
                row = self._row_by_spec_code.get(code)
                if row is not None:
                    selection_model.select(
                        self.model.index(row, 0),
                        QItemSelectionModel.Select | QItemSelectionModel.Rows,
                    )
            if current_code in self._row_by_spec_code:
                self.table_view.setCurrentIndex(
                    self.model.index(self._row_by_spec_code[current_code], current_index.column())
                )
            self.lbl_count.setText(f"共 {self.model.rowCount()} 条数据")
        finally:
            self.table_view.setUpdatesEnabled(True)
            self._populating_model = previous_populating
            self._loading = previous_loading
            self.table_view.verticalScrollBar().setValue(vertical_scroll)
            self.table_view.horizontalScrollBar().setValue(horizontal_scroll)

    def refresh_external_changes(self, spec_codes=(), image_codes=(), categories_changed=False):
        changed_codes = list(dict.fromkeys(str(code) for code in (spec_codes or []) if code))
        image_codes = list(dict.fromkeys(str(code) for code in (image_codes or []) if code))
        review_dialog = getattr(self, "combo_review_dialog", None)
        if review_dialog is not None and not sip.isdeleted(review_dialog) and changed_codes:
            review_dialog._sync_reviewed_rows(changed_codes)
        if self._loading:
            self._cost_rows_cache = None
            QTimer.singleShot(0, self._load_data_progressive)
            return
        if changed_codes:
            placeholders = ",".join("?" for _ in changed_codes)
            existing = {
                str(row[0]) for row in self.db.safe_fetchall(
                    f"SELECT spec_code FROM cost_library WHERE spec_code IN ({placeholders})",
                    tuple(changed_codes),
                )
            }
            visible = set(self._row_by_spec_code)
            if any((code in existing) != (code in visible) for code in changed_codes):
                self.load_data()
                return
        refresh_codes = changed_codes + [code for code in image_codes if code in self._row_by_spec_code]
        if categories_changed:
            refresh_codes.extend(self._row_by_spec_code)
        self._refresh_cost_rows(refresh_codes)

    def _refresh_main_products_for_specs(self, spec_codes=None):
        if not self.main_window or not hasattr(self.main_window, "refresh_external_products"):
            return
        params = tuple(dict.fromkeys(str(code) for code in (spec_codes or []) if code))
        where = ""
        if params:
            where = f"WHERE spec_code IN ({','.join('?' for _ in params)})"
        product_ids = [
            row[0] for row in self.db.safe_fetchall(
                f"SELECT DISTINCT product_id FROM product_specs {where}",
                params,
            )
        ]
        self.main_window.refresh_external_products(product_ids)

    def _category_color(self, label):
        if hasattr(self.db, "ensure_cost_category"):
            return self.db.ensure_cost_category(label)
        if hasattr(self.db, "category_color_for_label"):
            return self.db.category_color_for_label(label)
        label = str(label or "").strip()
        if not label:
            return ""
        digest = hashlib.md5(label.encode("utf-8")).hexdigest()
        return self.CATEGORY_COLORS[int(digest[:8], 16) % len(self.CATEGORY_COLORS)]

    def _normalize_category_colors(self):
        if hasattr(self.db, "normalize_cost_category_colors"):
            self.db.normalize_cost_category_colors()

    def show_price_test(self):
        existing = getattr(self, "price_test_dialog", None)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        dialog = CostPriceTestDialog(self.db, self)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _=None: setattr(self, "price_test_dialog", None))
        self.price_test_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def import_cost_data(self):
        parent = self.main_window
        if not parent or not hasattr(parent, "import_cost_data"):
            QMessageBox.warning(self, "提示", "当前窗口无法调用导入成本表功能。")
            return
        parent.import_cost_data()
        self._normalize_category_colors()
        self.load_data()

    def _refresh_detail_costs_after_settings(self, show_message=True):
        try:
            changed = self.db.recalculate_detailed_cost_library(record_history=True, source="manual") if hasattr(self.db, "recalculate_detailed_cost_library") else 0
            if show_message:
                QMessageBox.information(self, "成功", f"设置已保存，已刷新 {changed} 条详细成本数据。")
            QTimer.singleShot(0, self._refresh_after_detail_cost_change)
        except Exception as e:
            QMessageBox.critical(self, "刷新失败", f"重新计算详细成本失败：{e}")

    def _refresh_after_detail_cost_change(self):
        self._refresh_cost_rows(self._row_by_spec_code)
        self._refresh_main_products_for_specs()

    def show_shipping_settings(self):
        dialog = ShippingRuleDialog(self.db, self)
        dialog.exec_()

    def show_misc_fee_settings(self):
        dialog = MiscFeeDialog(self.db, self)
        dialog.exec_()

    def show_history(self):
        dialog = self.history_dialog
        if dialog is not None and not sip.isdeleted(dialog):
            if dialog.isMinimized():
                dialog.showNormal()
            else:
                dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        dialog = CostHistoryDialog(self.db, cost_library=self, main_window=self.main_window)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _=None: setattr(self, "history_dialog", None))
        self.history_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def show_combo_review(self):
        dialog = CostComboReviewDialog(self.db, self)
        self.combo_review_dialog = dialog
        try:
            dialog.exec_()
        finally:
            self.combo_review_dialog = None

    def _center_child_dialog(self, dialog):
        parent_window = self.window()
        center = parent_window.frameGeometry().center() if parent_window else QApplication.desktop().screenGeometry().center()
        geometry = dialog.frameGeometry()
        geometry.moveCenter(center)
        dialog.move(geometry.topLeft())

    def show_category_manage(self, target_category=""):
        dialog = CostCategoryManageDialog(self.db, self)
        if target_category:
            QTimer.singleShot(0, lambda: dialog.focus_category(target_category))
        self._center_child_dialog(dialog)
        dialog.exec_()

    def show_create_item(self):
        dialog = CostItemCreateDialog(self.db, self)
        if dialog.exec_() == QDialog.Accepted:
            spec_code = dialog.code_input.text().strip()
            self._push_cost_undo(
                "新增商品",
                {},
                self._capture_cost_rows([spec_code]),
            )
            self._normalize_category_colors()
            self.load_data()

    def show_link_combinations(self, target_product_code=""):
        existing = getattr(self, "link_combination_dialog", None)
        if existing is not None:
            if existing.isMinimized():
                existing.showNormal()
            else:
                existing.show()
            existing.raise_()
            existing.activateWindow()
            if target_product_code and hasattr(existing, "focus_product"):
                QTimer.singleShot(0, lambda: existing.focus_product(target_product_code))
            return
        dialog = LinkCombinationDialog(self.db, self.main_window, None)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        dialog.destroyed.connect(lambda _=None: setattr(self, "link_combination_dialog", None))
        self.link_combination_dialog = dialog
        self._center_child_dialog(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def show_lan_sync(self):
        try:
            from .cost_sync import CostSyncDialog
        except ImportError:
            from cost_sync import CostSyncDialog
        dialog = CostSyncDialog(self.db, self.main_window, self)
        self._center_child_dialog(dialog)
        dialog.exec_()

    def show_sync_hint(self, text):
        self._show_copy_hint(str(text or "同步完成"), 1000)

    def _build_unlisted_specs_text(self, rows):
        grouped = {}
        for category_label, spec_name, spec_code, quantity in rows:
            category = str(category_label or "").strip() or "未分类"
            grouped.setdefault(category, []).append((
                str(spec_name or "").strip(),
                str(spec_code or "").strip(),
                self._format_quantity(quantity),
            ))

        lines = []
        for category in sorted(grouped.keys()):
            items = grouped[category]
            lines.append(f"【{category}】未上架规格（{len(items)}个）")
            for index, (spec_name, spec_code, quantity) in enumerate(items, start=1):
                parts = [f"{index}. 商品名称：{spec_name or '-'}", f"规格编码：{spec_code or '-'}"]
                if quantity:
                    parts.append(f"数量：{quantity}")
                lines.append("；".join(parts))
            lines.append("")
        return "\n".join(lines).strip()

    def get_unlisted_specs_rows(self, store_id=None):
        if store_id is None:
            return self.db.safe_fetchall(
                """SELECT cost_library.category_label, cost_library.spec_name,
                          cost_library.spec_code, cost_library.quantity
                   FROM cost_library
                   LEFT JOIN (
                       SELECT spec_code, COUNT(*) AS listed_count
                       FROM product_specs
                       WHERE COALESCE(spec_code, '') <> ''
                       GROUP BY spec_code
                   ) listed_specs ON listed_specs.spec_code = cost_library.spec_code
                   WHERE COALESCE(listed_specs.listed_count, 0) = 0
                   ORDER BY CASE WHEN COALESCE(cost_library.category_label, '') = '' THEN 1 ELSE 0 END,
                            cost_library.category_label,
                            cost_library.sort_order,
                            cost_library.spec_code"""
            )
        return self.db.safe_fetchall(
            """SELECT cost_library.category_label, cost_library.spec_name,
                      cost_library.spec_code, cost_library.quantity
               FROM cost_library
               LEFT JOIN (
                   SELECT product_specs.spec_code, COUNT(*) AS listed_count
                   FROM product_specs
                   JOIN products ON products.id = product_specs.product_id
                   WHERE COALESCE(product_specs.spec_code, '') <> ''
                     AND products.store_id = ?
                   GROUP BY product_specs.spec_code
               ) listed_specs ON listed_specs.spec_code = cost_library.spec_code
               WHERE COALESCE(listed_specs.listed_count, 0) = 0
               ORDER BY CASE WHEN COALESCE(cost_library.category_label, '') = '' THEN 1 ELSE 0 END,
                        cost_library.category_label,
                        cost_library.sort_order,
                        cost_library.spec_code""",
            (store_id,),
        )

    def show_unlisted_specs(self):
        existing = getattr(self, "unlisted_specs_dialog", None)
        if existing is not None and not sip.isdeleted(existing):
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        default_store_id = None
        selected_stores = getattr(self.main_window, "current_store_filter", None) if self.main_window else None
        if selected_stores and len(selected_stores) == 1:
            try:
                default_store_id = next(iter(selected_stores))
            except Exception:
                default_store_id = None
        dialog = UnlistedCostSpecsDialog(self.db, self.main_window, default_store_id=default_store_id)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _obj=None: setattr(self, "unlisted_specs_dialog", None))
        self.unlisted_specs_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _selected_cost_specs(self):
        rows = sorted({index.row() for index in self.table_view.selectedIndexes()})
        specs = []
        seen = set()
        for row in rows:
            name_item = self.model.item(row, self.COL_NAME)
            code_item = self.model.item(row, self.COL_CODE)
            category_item = self.model.item(row, self.COL_CATEGORY)
            spec_code = code_item.text().strip() if code_item else ""
            if not spec_code or spec_code in seen:
                continue
            seen.add(spec_code)
            specs.append({
                "spec_name": name_item.text().strip() if name_item else "",
                "spec_code": spec_code,
                "category_label": category_item.text().strip() if category_item else "",
            })
        return specs

    def _cart_cost_specs(self):
        return [
            {
                "spec_name": spec.get("spec_name", ""),
                "spec_code": spec.get("spec_code", ""),
                "category_label": spec.get("category_label", ""),
            }
            for spec in self.listing_cart.values()
            if spec.get("spec_code")
        ]

    def create_selected_link(self):
        use_cart = bool(self.listing_cart)
        specs = self._cart_cost_specs() if use_cart else self._selected_cost_specs()
        if not specs:
            QMessageBox.warning(self, "提示", "请先选中要创建链接的规格。")
            return
        dialog = CostLinkCreateDialog(self.db, specs, self.main_window, self)
        if dialog.exec_() == QDialog.Accepted:
            if use_cart:
                self.listing_cart.clear()
                self.refresh_listing_cart_view()
            self.load_data()

    def delete_selected(self):
        try:
            indexes = self.table_view.selectedIndexes()
            if not indexes:
                QMessageBox.warning(self, "提示", "请先选中要删除的行！")
                return
            rows = sorted({index.row() for index in indexes}, reverse=True)
            reply = QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除选中的 {len(rows)} 条数据吗？\n此操作不可恢复！",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            spec_codes = [
                self.model.item(row, self.COL_CODE).text().strip()
                for row in rows
                if self.model.item(row, self.COL_CODE)
            ]
            before_rows = self._capture_cost_rows(spec_codes)
            count = 0
            for row in rows:
                item = self.model.item(row, self.COL_CODE)
                if item:
                    self.db.safe_execute("DELETE FROM cost_library WHERE spec_code=?", (item.text(),))
                    count += 1
            self._push_cost_undo("删除商品", before_rows, {})
            QMessageBox.information(self, "成功", f"已删除 {count} 条数据。")
            self.db.set_setting("cost_sync_local_dirty", "1")
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", f"删除过程中出错：{str(e)}")

    def clear_all(self):
        try:
            reply = QMessageBox.question(
                self,
                "确认清空",
                "确定要清空整个成本库吗？\n此操作不可恢复！\n历史操作记录会保留。",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.db.safe_execute("DELETE FROM cost_library")
                self.db.set_setting("cost_sync_local_dirty", "1")
                QMessageBox.information(self, "成功", "成本库已清空，历史操作记录已保留。")
                self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "清空失败", f"清空过程中出错：{str(e)}")

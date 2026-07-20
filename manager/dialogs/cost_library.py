# -*- coding: utf-8 -*-
"""成本库管理对话框"""
import csv
import hashlib
import io
import json
import re
import time
from datetime import datetime

from PyQt5.QtCore import QEvent, QSize, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QCursor, QFontMetrics, QPainter, QPen, QPixmap, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyledItemDelegate,
    QTableView,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
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
    """查看和删除成本历史记录。"""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("历史成本")
        self.resize(1020, 520)
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索规格编码:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入规格编码关键字...")
        self.search_input.textChanged.connect(self.load_data)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.load_data)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(btn_refresh)
        layout.addLayout(search_layout)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([
            "时间", "商品名称", "规格编码", "原成本", "新成本", "变化金额", "变化百分比", "来源"
        ])
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.clicked.connect(self.copy_spec_code)
        layout.addWidget(self.table_view, 1)

        btn_layout = QHBoxLayout()
        self.lbl_count = QLabel("共 0 条历史")
        btn_delete = QPushButton("删除选中历史")
        btn_delete.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
        btn_delete.clicked.connect(self.delete_selected)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _format_price(self, value):
        return "" if value is None else f"{float(value):.2f}"

    def _format_percent(self, value):
        return "" if value is None else f"{float(value):.2f}%"

    def _format_history_date(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19], fmt).strftime("%m月%d日")
            except ValueError:
                continue
        return text[5:10].replace("-", "月") + "日" if len(text) >= 10 and text[4:5] == "-" else text

    def load_data(self):
        self.model.setRowCount(0)
        keyword = self.search_input.text().strip()
        terms = split_search_terms(keyword)
        rows = self.db.safe_fetchall(
            """SELECT cost_history.id, cost_history.import_time,
                      COALESCE(cost_library.spec_name, '') AS spec_name,
                      cost_history.spec_code, cost_history.old_cost_price,
                      cost_history.new_cost_price, cost_history.change_amount,
                      cost_history.change_percent, cost_history.source
               FROM cost_history
               LEFT JOIN cost_library ON cost_library.spec_code = cost_history.spec_code
               ORDER BY cost_history.import_time DESC, cost_history.id DESC"""
        )

        for history_id, import_time, spec_name, spec_code, old_cost, new_cost, amount, percent, source in rows:
            if terms and not any_terms_match(terms, spec_name, spec_code, source):
                continue
            row = self.model.rowCount()
            self.model.insertRow(row)
            values = [
                self._format_history_date(import_time),
                str(spec_name or ""),
                str(spec_code or ""),
                self._format_price(old_cost),
                self._format_price(new_cost),
                self._format_price(amount),
                self._format_percent(percent),
                "手动" if source == "manual" else "导入",
            ]
            for col, value in enumerate(values):
                item = QStandardItem(value)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 0:
                    item.setData(history_id, Qt.UserRole)
                self.model.setItem(row, col, item)
        self.lbl_count.setText(f"共 {self.model.rowCount()} 条历史")

    def copy_spec_code(self, index):
        if not index.isValid() or index.column() != 2:
            return
        item = self.model.item(index.row(), 2)
        spec_code = item.text().strip() if item else ""
        if not spec_code:
            return
        QApplication.clipboard().setText(spec_code)
        self._show_copy_hint("已复制")

    def _show_copy_hint(self, text):
        parent = self.parent()
        main_window = parent.parent() if parent and parent.parent() else parent
        if main_window and hasattr(main_window, "show_toast"):
            main_window.show_toast(text, 1200)
        else:
            QToolTip.showText(QCursor.pos(), text, self, self.rect(), 1200)

    def delete_selected(self):
        indexes = self.table_view.selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "提示", "请先选中要删除的历史记录！")
            return

        rows = sorted({index.row() for index in indexes}, reverse=True)
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(rows)} 条历史记录吗？\n当前成本库不会被修改。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        count = 0
        for row in rows:
            item = self.model.item(row, 0)
            history_id = item.data(Qt.UserRole) if item else None
            if history_id is None:
                continue
            self.db.safe_execute("DELETE FROM cost_history WHERE id=?", (history_id,))
            count += 1

        QMessageBox.information(self, "成功", f"已删除 {count} 条历史记录。")
        self.load_data()


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
                   (store_id, name, title, coupon_amount, new_customer_discount, image_path, sort_order)
                   VALUES (?, ?, ?, 0, 0, NULL, ?)""",
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
        self.setWindowTitle("商品类型管理")
        self.resize(1080, 680)
        self.init_ui()
        self.load_categories()

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
        right.addWidget(QLabel("当前类型规格（拖拽左侧行号调整顺序，保存后生效）"))
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
        btn_save = QPushButton("保存修改")
        btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.queue_save_changes)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.load_categories)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_rename)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_save)
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
            self.current_category = label
            self.category_search.clear()
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "新建失败", f"新建商品类型失败：{e}")
            return
        parent = self.parent()
        if parent and hasattr(parent, "load_data"):
            parent.load_data()
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
        try:
            if hasattr(self.db, "rename_cost_category"):
                self.db.rename_cost_category(old_label, new_label)
            else:
                raise RuntimeError("当前数据库管理器不支持商品类型重命名。")
            self.current_category = new_label
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "重命名失败", f"商品类型重命名失败：{e}")
            return
        parent = self.parent()
        if parent and hasattr(parent, "load_data"):
            parent.load_data()
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
        try:
            if not hasattr(self.db, "delete_cost_categories"):
                raise RuntimeError("当前数据库管理器不支持商品类型删除。")
            self.db.delete_cost_categories(labels)
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", f"商品类型删除失败：{e}")
            return
        parent = self.parent()
        if parent and hasattr(parent, "load_data"):
            parent.load_data()
        self.current_category = ""
        self.load_categories()

    def load_specs_for_category(self, label):
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
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "移动失败", f"移动规格分类失败：{e}")
            return
        parent = self.parent()
        if parent and hasattr(parent, "load_data"):
            parent.load_data()
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
            QMessageBox.information(self, "成功", "AI排序完成，请点击“保存修改”后生效。")
        except Exception as e:
            self._set_spec_rows(self._fallback_sort_rows(rows))
            QMessageBox.warning(self, "AI排序已使用本地兜底", f"{e}\n\n已按本地规则排序，请点击“保存修改”后生效。")

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
        for col in (0, 1):
            item = self.category_model.item(row, col)
            item.setBackground(QBrush(QColor(color_text)))
        color_item.setData(color_text, Qt.UserRole)

    def save_changes(self):
        try:
            for row in range(self.category_model.rowCount()):
                label = self.category_model.item(row, 0).text().strip()
                color_item = self.category_model.item(row, 1)
                color = str(color_item.data(Qt.UserRole) or "").strip()
                if label and color and hasattr(self.db, "update_cost_category_color"):
                    self.db.update_cost_category_color(label, color)
            ordered_codes = []
            for row in self._visual_ordered_model_rows():
                spec_code = self.spec_model.item(row, 1).text().strip()
                if spec_code:
                    ordered_codes.append(spec_code)
            if ordered_codes and hasattr(self.db, "update_cost_manual_sort_orders"):
                self.db.update_cost_manual_sort_orders(ordered_codes)
            if hasattr(self.db, "update_all_product_category_labels"):
                self.db.update_all_product_category_labels()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存商品类型失败：{e}")
            return
        parent = self.parent()
        if parent and hasattr(parent, "load_data"):
            parent.load_data()
        QMessageBox.information(self, "成功", "商品类型修改已保存。")
        self.load_categories()


class CostItemCreateDialog(QDialog):
    """手动新增成本库商品规格。"""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
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
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        code_layout = QHBoxLayout()
        code_layout.addWidget(QLabel("规格编码:"))
        self.code_input = QLineEdit()
        code_layout.addWidget(self.code_input)
        layout.addLayout(code_layout)

        quantity_layout = QHBoxLayout()
        quantity_layout.addWidget(QLabel("数量:"))
        self.quantity_input = QLineEdit()
        quantity_layout.addWidget(self.quantity_input)
        layout.addLayout(quantity_layout)

        attribute_layout = QHBoxLayout()
        attribute_layout.addWidget(QLabel("产品属性:"))
        self.attribute_input = QTextEdit()
        self.attribute_input.setAcceptRichText(False)
        self.attribute_input.setPlaceholderText("可为空；快速识别会合并尺寸、张数（含封面）、印刷工艺")
        self.attribute_input.setFixedHeight(72)
        attribute_layout.addWidget(self.attribute_input)
        layout.addLayout(attribute_layout)

        cost_layout = QHBoxLayout()
        cost_layout.addWidget(QLabel("产品单成本:" if self.cost_mode == "detail" else "成本价:"))
        self.cost_input = QLineEdit()
        cost_layout.addWidget(self.cost_input)
        layout.addLayout(cost_layout)

        self.weight_input = QLineEdit()
        if self.cost_mode == "detail":
            weight_layout = QHBoxLayout()
            weight_layout.addWidget(QLabel("单个重量kg:"))
            weight_layout.addWidget(self.weight_input)
            layout.addLayout(weight_layout)
            misc_fee = self.db.get_cost_misc_fee() if hasattr(self.db, "get_cost_misc_fee") else 0
            note = QLabel(f"详细成本模式：总成本 = 产品单成本 × 数量 + 杂费 {misc_fee:.2f} + 快递费（按模板自动计算）")
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
            "quantity": self._find_column(headers, [["数量"], ["件数", "个数", "库存数量", "qty", "quantity", "count", "num"]]),
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
        quantity = self._value_at(values, mappings["quantity"])
        if quantity:
            self.quantity_input.setText(quantity)
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
            f"数量：{quantity or '-'}",
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

    def _parse_cost(self):
        text = self.cost_input.text().replace("¥", "").replace("$", "").replace(",", "").strip()
        if not text:
            raise ValueError("产品单成本不能为空" if self.cost_mode == "detail" else "成本价不能为空")
        value = float(text)
        if value < 0:
            raise ValueError("产品单成本不能小于 0" if self.cost_mode == "detail" else "成本价不能小于 0")
        return value

    def _parse_unit_weight(self):
        text = self.weight_input.text().replace(",", "").strip()
        if not text:
            raise ValueError("单个重量不能为空")
        match = re.search(r"\d+(?:\.\d+)?", text)
        if not match:
            raise ValueError("单个重量必须是数字")
        value = float(match.group(0))
        if value <= 0:
            raise ValueError("单个重量必须大于 0")
        return value

    def create_item(self):
        category_label = str(self.category_combo.currentText() or "").strip()
        spec_name = self.name_input.text().strip()
        spec_code = self.code_input.text().strip()
        quantity = self.quantity_input.text().strip()
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
                cost_price, shipping_fee, misc_fee, _total_weight = self.db.calculate_detailed_cost(product_cost, quantity, unit_weight)
                cost_calc_mode = "detail"
            else:
                cost_price = input_cost
        except ValueError as e:
            QMessageBox.warning(self, "成本格式错误", str(e))
            return

        category_color = self.db.ensure_cost_category(category_label) if hasattr(self.db, "ensure_cost_category") else ""
        max_rows = self.db.safe_fetchall("SELECT MAX(sort_order) FROM cost_library")
        next_order = (max_rows[0][0] if max_rows and max_rows[0][0] is not None else 0) + 1
        try:
            self.db.safe_execute(
                """INSERT INTO cost_library
                   (spec_code, spec_name, quantity, category_label, category_color, cost_price, sort_order,
                    manual_sort_order, product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
                    product_attribute, product_attribute_combo_disabled, product_attribute_is_combo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 0, 0)""",
                (
                    spec_code, spec_name, quantity, category_label, category_color, cost_price, next_order,
                    product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode, product_attribute,
                ),
            )
            if hasattr(self.db, "normalize_cost_category_colors"):
                self.db.normalize_cost_category_colors()
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
        self.load_link_combos()

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

        self.chk_new_combo = QCheckBox("新建链接组合")
        self.chk_new_combo.toggled.connect(self._on_combo_mode_changed)
        layout.addWidget(self.chk_new_combo)

        existing_combo_layout = QHBoxLayout()
        existing_combo_layout.addWidget(QLabel("选择组合:"))
        self.combo_select = QComboBox()
        existing_combo_layout.addWidget(self.combo_select)
        layout.addLayout(existing_combo_layout)

        new_combo_layout = QHBoxLayout()
        new_combo_layout.addWidget(QLabel("组合名称:"))
        self.combo_name_input = QLineEdit()
        self.combo_name_input.setPlaceholderText("链接组合名称，不是链接标题")
        new_combo_layout.addWidget(self.combo_name_input)
        btn_ai_combo = QPushButton("AI生成组合名称")
        btn_ai_combo.clicked.connect(self.generate_combo_name)
        new_combo_layout.addWidget(btn_ai_combo)
        layout.addLayout(new_combo_layout)

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

    def load_link_combos(self):
        self.combo_select.clear()
        rows = self.db.get_link_combinations_with_counts() if hasattr(self.db, "get_link_combinations_with_counts") else []
        for combo_id, name, _sort_order, link_count in rows:
            self.combo_select.addItem(f"{name}（{int(link_count or 0)}条链接）", combo_id)
        self.chk_new_combo.setChecked(self.combo_select.count() == 0)
        self._on_combo_mode_changed(self.chk_new_combo.isChecked())

    def _on_combo_mode_changed(self, checked):
        self.combo_select.setEnabled(not checked)
        self.combo_name_input.setEnabled(checked)

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

    def _existing_combo_names(self):
        rows = self.db.safe_fetchall("SELECT name FROM link_combinations ORDER BY sort_order, name")
        return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]

    def _call_ai_text(self, purpose):
        api_key = self.db.get_setting("ai_api_key", "") if hasattr(self.db, "get_setting") else ""
        if not api_key:
            raise RuntimeError("未配置 API Key，请先到 API 配置里填写。")
        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        existing_types = self._existing_link_types()
        existing_combos = self._existing_combo_names()
        if purpose == "combo":
            field_name = "name"
            max_chars = 40
            task = (
                "为这次选中的商品生成一个链接组合名称。组合名称不是商品标题，应该体现人群、用途或组合场景。"
                "优先参考现有链接类型和已有组合名称的风格，但不要直接输出解释。"
                "必须只返回 JSON，例如 {\"name\":\"儿童启蒙资料组合\"}。"
            )
        else:
            field_name = "link_type"
            max_chars = 40
            task = (
                "为这次选中的商品选择链接类型。先从现有链接类型中选择最符合的一个；"
                "只有现有链接类型都不符合时，才生成一个新的短链接类型。"
                "必须只返回 JSON，例如 {\"link_type\":\"儿童启蒙资料\"}。"
            )
        reference = (
            "现有链接类型:\n" + ("\n".join(f"- {item}" for item in existing_types) or "无") +
            "\n\n已有链接组合名称:\n" + ("\n".join(f"- {item}" for item in existing_combos) or "无")
        )
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
        options = existing_types if purpose == "type" else existing_combos + existing_types
        value = _clean_ai_short_value(content, field_name, options, max_chars)
        if not value:
            raise RuntimeError(f"AI返回内容无法识别。返回内容:{content[:300]}")
        return value

    def generate_combo_name(self):
        try:
            self.combo_name_input.setText(self._call_ai_text("combo"))
            self.chk_new_combo.setChecked(True)
        except Exception as e:
            QMessageBox.warning(self, "AI生成失败", str(e))

    def generate_link_type(self):
        try:
            self.link_type_input.setText(self._call_ai_text("type"))
        except Exception as e:
            QMessageBox.warning(self, "AI生成失败", str(e))

    def _resolve_combo_id(self):
        if self.chk_new_combo.isChecked():
            combo_name = self.combo_name_input.text().strip()
            if not combo_name:
                raise ValueError("请填写链接组合名称。")
            combo_id = self.db.ensure_link_combination(combo_name) if hasattr(self.db, "ensure_link_combination") else None
            if not combo_id:
                raise ValueError("链接组合创建失败。")
            return combo_id
        combo_id = self.combo_select.currentData()
        if combo_id is None:
            raise ValueError("请选择一个已有链接组合，或勾选新建链接组合。")
        return combo_id

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
        try:
            combo_id = self._resolve_combo_id()
        except ValueError as e:
            QMessageBox.warning(self, "提示", str(e))
            return
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
                   (store_id, name, title, coupon_amount, new_customer_discount, image_path, sort_order, link_combo_id, link_type)
                   VALUES (?, ?, ?, 0, 0, NULL, ?, ?, ?)""",
                (store_id, product_id, title, max_order + 1, combo_id, link_type),
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
    """查看和维护链接组合及链接类型。"""
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
        self.setWindowTitle("链接组合")
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
        btn_ai_classify = QPushButton("未分类链接AI归类")
        btn_ai_classify.clicked.connect(self.show_unclassified_classify_dialog)
        filter_layout.addWidget(self.store_filter_combo)
        filter_layout.addStretch()
        filter_layout.addWidget(btn_ai_classify)
        layout.addLayout(filter_layout)

        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.addWidget(QLabel("链接组合"))
        combo_search_layout = QHBoxLayout()
        combo_search_layout.addWidget(QLabel("搜索:"))
        self.combo_search_input = QLineEdit()
        self.combo_search_input.setPlaceholderText("输入商品ID/标题/链接类型/组合名；无链接类型可输入“无链接类型”")
        self.combo_search_input.textChanged.connect(self.load_combos)
        combo_search_layout.addWidget(self.combo_search_input)
        left.addLayout(combo_search_layout)
        self.combo_model = QStandardItemModel()
        self.combo_model.setHorizontalHeaderLabels(["组合名称", "链接数"])
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
        left_btns = QHBoxLayout()
        btn_add_combo = QPushButton("新增组合")
        btn_add_combo.clicked.connect(self.add_combo)
        btn_rename_combo = QPushButton("重命名")
        btn_rename_combo.clicked.connect(self.rename_combo)
        btn_delete_combo = QPushButton("删除组合")
        btn_delete_combo.clicked.connect(self.delete_selected_combos)
        btn_ai_combo = QPushButton("AI生成组合名称")
        btn_ai_combo.clicked.connect(self.ai_rename_current_combo)
        left_btns.addWidget(btn_add_combo)
        left_btns.addWidget(btn_rename_combo)
        left_btns.addWidget(btn_delete_combo)
        left_btns.addWidget(btn_ai_combo)
        left.addLayout(left_btns)

        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.addWidget(QLabel("组合内链接"))
        link_search_layout = QHBoxLayout()
        link_search_layout.addWidget(QLabel("搜索:"))
        self.link_search_input = QLineEdit()
        self.link_search_input.setPlaceholderText("输入商品ID/标题/链接类型；无链接类型可输入“无链接类型”")
        self.link_search_input.textChanged.connect(lambda: self.load_links(self.current_combo_id))
        link_search_layout.addWidget(self.link_search_input)
        right.addLayout(link_search_layout)
        self.link_model = QStandardItemModel()
        self.link_model.setHorizontalHeaderLabels(["图片", "链接ID", "标题", "链接类型", "店铺", "规格数"])
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
        btn_move = QPushButton("移动到其他组合")
        btn_move.clicked.connect(self.move_selected_links)
        btn_add_link = QPushButton("添加链接")
        btn_add_link.clicked.connect(self.add_links_to_current_combo)
        btn_save = QPushButton("保存修改")
        btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.save_link_types)
        right_btns.addWidget(btn_ai_type)
        right_btns.addWidget(btn_move)
        right_btns.addWidget(btn_add_link)
        right_btns.addStretch()
        right_btns.addWidget(btn_save)
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
        if hasattr(self.db, "update_all_product_category_labels"):
            self.db.update_all_product_category_labels(self.current_store_filter_id())
        self.load_combos()

    def load_combos(self):
        previous = self.current_combo_id
        self.combo_model.setRowCount(0)
        store_id = self.current_store_filter_id()
        combo_search = self.combo_search_input.text().strip() if hasattr(self, "combo_search_input") else ""
        rows = self.db.get_link_combinations_with_counts(store_id, combo_search) if hasattr(self.db, "get_link_combinations_with_counts") else []
        select_row = 0
        for combo_id, name, _sort_order, link_count in rows:
            row = self.combo_model.rowCount()
            if combo_id == previous:
                select_row = row
            self.combo_model.insertRow(row)
            self.combo_model.setItem(row, 0, self._make_item(name, user_data=combo_id))
            self.combo_model.setItem(row, 1, self._make_item(int(link_count or 0)))
        no_type_count = self._no_link_type_link_count(store_id, combo_search)
        if no_type_count:
            row = self.combo_model.rowCount()
            if previous == self.NO_LINK_TYPE_COMBO_ID:
                select_row = row
            self.combo_model.insertRow(row)
            self.combo_model.setItem(row, 0, self._make_item(self.NO_LINK_TYPE_COMBO_NAME, user_data=self.NO_LINK_TYPE_COMBO_ID))
            self.combo_model.setItem(row, 1, self._make_item(no_type_count))
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
        index = self.combo_table.indexAt(pos)
        if not index.isValid() or index.column() != 0:
            return
        if index.row() not in self._selected_combo_rows():
            self.combo_table.selectRow(index.row())
        item = self.combo_model.item(index.row(), 0)
        self.current_combo_id = item.data(Qt.UserRole) if item else None
        if self._is_no_link_type_combo():
            return
        menu = QMenu(self)
        delete_action = menu.addAction("删除选中组合")
        action = menu.exec_(self.combo_table.viewport().mapToGlobal(pos))
        if action == delete_action:
            self.delete_selected_combos()

    def load_links(self, combo_id):
        self.link_model.setRowCount(0)
        if combo_id is None:
            return
        store_id = self.current_store_filter_id()
        store_clause = " AND p.store_id = ?" if store_id is not None else ""
        params = [] if self._is_no_link_type_combo(combo_id) else [combo_id]
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
                WHERE {"COALESCE(p.link_type, '') = ''" if self._is_no_link_type_combo(combo_id) else "p.link_combo_id = ?"}
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

    def save_link_types(self):
        try:
            for row in range(self.link_model.rowCount()):
                id_item = self.link_model.item(row, 1)
                type_item = self.link_model.item(row, 3)
                product_id = id_item.data(Qt.UserRole) if id_item else None
                if product_id and hasattr(self.db, "update_product_link_type"):
                    self.db.update_product_link_type(product_id, type_item.text().strip() if type_item else "")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        QMessageBox.information(self, "成功", "链接类型已保存。")
        self.load_links(self.current_combo_id)

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

    def _existing_combo_names(self):
        rows = self.db.safe_fetchall("SELECT name FROM link_combinations ORDER BY sort_order, name")
        return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]

    def _call_ai_text(self, prompt, context):
        api_key = self.db.get_setting("ai_api_key", "") if hasattr(self.db, "get_setting") else ""
        if not api_key:
            raise RuntimeError("未配置 API Key，请先到 API 配置里填写。")
        api_url = self.db.get_setting("ai_api_url", "https://api.deepseek.com/chat/completions")
        model = self.db.get_setting("ai_model", "deepseek-v4-flash")
        is_type = "链接类型" in prompt
        field_name = "link_type" if is_type else "name"
        existing_types = self._existing_link_types()
        existing_combos = self._existing_combo_names()
        reference = (
            "现有链接类型:\n" + ("\n".join(f"- {item}" for item in existing_types) or "无") +
            "\n\n已有链接组合名称:\n" + ("\n".join(f"- {item}" for item in existing_combos) or "无")
        )
        format_rule = (
            "如果生成链接类型，先从现有链接类型中选择最符合的一个；没有符合的再生成新的。"
            "如果生成组合名称，参考现有链接类型和已有组合名称的风格。"
            f"必须只返回 JSON 对象，字段名为 {field_name}，不要解释，不要代码块。"
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
        options = existing_types if is_type else existing_combos + existing_types
        value = _clean_ai_short_value(content, field_name, options, 40)
        if not value:
            raise RuntimeError(f"AI返回内容无法识别。返回内容:{content[:300]}")
        return value

    def ai_rename_current_combo(self):
        if self.current_combo_id is None:
            QMessageBox.warning(self, "提示", "请先选择链接组合。")
            return
        if self._is_no_link_type_combo():
            QMessageBox.warning(self, "提示", "未分类链接类型是临时分组，不能重命名。")
            return
        product_ids = []
        for row in range(self.link_model.rowCount()):
            item = self.link_model.item(row, 1)
            if item and item.data(Qt.UserRole):
                product_ids.append(item.data(Qt.UserRole))
        try:
            name = self._call_ai_text("根据这些链接和规格生成一个链接组合名称，体现人群、用途或组合场景。只输出名称，15个中文以内。", self._spec_context_for_products(product_ids))
            if hasattr(self.db, "rename_link_combination") and self.db.rename_link_combination(self.current_combo_id, name):
                self.load_combos()
        except Exception as e:
            QMessageBox.warning(self, "AI生成失败", str(e))

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
        self.setWindowTitle("快递费设置")
        self.resize(720, 460)
        self.init_ui()
        self.load_rules()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("重量单位：kg。按区间匹配，超过规则使用续重公式。"))
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["起始重量kg", "结束重量kg", "费用"])
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
            over_layout.addWidget(widget)
        layout.addLayout(over_layout)

        btn_layout = QHBoxLayout()
        btn_default = QPushButton("恢复默认")
        btn_default.clicked.connect(self.load_default_rules)
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.save_rules)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_default)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
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

    def load_rules(self):
        self._apply_rules(self.db.get_cost_shipping_rules() if hasattr(self.db, "get_cost_shipping_rules") else {})

    def _apply_rules(self, rules):
        self.model.setRowCount(0)
        for rule in rules.get("ranges", []):
            self.add_range(rule.get("min", ""), rule.get("max", ""), rule.get("fee", ""))
        over = rules.get("over", {})
        self.over_threshold.setText(str(over.get("threshold", 3)))
        self.over_base_fee.setText(str(over.get("base_fee", 2.5)))
        self.over_deduct_weight.setText(str(over.get("deduct_weight", 1)))
        self.over_step_weight.setText(str(over.get("step_weight", 1)))
        self.over_step_fee.setText(str(over.get("step_fee", 1)))

    def add_range(self, min_weight="", max_weight="", fee=""):
        row = self.model.rowCount()
        self.model.insertRow(row)
        self.model.setItem(row, 0, self._make_item(min_weight))
        self.model.setItem(row, 1, self._make_item(max_weight))
        self.model.setItem(row, 2, self._make_item(fee))

    def delete_selected_range(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.model.removeRow(row)

    def _parse_non_negative(self, text, field):
        try:
            value = float(str(text).strip())
        except ValueError:
            raise ValueError(f"{field} 必须是数字")
        if value < 0:
            raise ValueError(f"{field} 不能小于 0")
        return value

    def save_rules(self):
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
            QMessageBox.warning(self, "格式错误", str(e))
            return

        if hasattr(self.db, "set_cost_shipping_rules"):
            self.db.set_cost_shipping_rules({"ranges": ranges, "over": over})
        self.accept()


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
        row.addWidget(self.input_fee)
        layout.addLayout(row)
        btns = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.save_fee)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def save_fee(self):
        try:
            value = float(self.input_fee.text().strip() or 0)
            if value < 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "格式错误", "杂费必须是大于等于 0 的数字。")
            return
        if hasattr(self.db, "set_cost_misc_fee"):
            self.db.set_cost_misc_fee(value)
        self.accept()


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

    COL_CATEGORY = 0
    COL_NAME = 1
    COL_QUANTITY = 2
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
        self.search_input.setPlaceholderText("输入商品类型/规格名称/规格编码/数量关键字，空格分隔...")
        self.search_input.textChanged.connect(self.populate_table)
        filter_layout.addWidget(self.search_input, 1)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh_rows)
        filter_layout.addWidget(btn_refresh)
        layout.addLayout(filter_layout)

        self.table_view = QTableView()
        self.model = QStandardItemModel(0, 3, self)
        self.model.setHorizontalHeaderLabels(["商品类型", "规格名称", "数量"])
        self.table_view.setModel(self.model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setWordWrap(True)
        self.table_view.verticalHeader().setDefaultSectionSize(42)
        self.table_view.horizontalHeader().setSectionResizeMode(self.COL_CATEGORY, QHeaderView.ResizeToContents)
        self.table_view.horizontalHeader().setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        self.table_view.horizontalHeader().setSectionResizeMode(self.COL_QUANTITY, QHeaderView.ResizeToContents)
        self.table_view.clicked.connect(self.on_table_clicked)
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
                   cost_library.quantity,
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
        category, name, code, quantity, color, sort_order = row
        return {
            "category_label": str(category or "").strip(),
            "spec_name": str(name or "").strip(),
            "spec_code": str(code or "").strip(),
            "quantity": self._format_quantity(quantity),
            "color": str(color or "").strip(),
            "sort_order": sort_order if sort_order is not None else 999999999,
        }

    def _format_quantity(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            number = float(text)
            if number.is_integer():
                return str(int(number))
        except Exception:
            pass
        return text

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
                row.get("quantity", ""),
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
            values = [category, row_data.get("spec_name", ""), row_data.get("quantity", "")]
            items = []
            for value in values:
                item = QStandardItem(str(value or ""))
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                item.setData(row_data, self.ROW_ROLE)
                item.setToolTip(
                    f"商品类型：{category}\n规格名称：{row_data.get('spec_name') or '-'}\n"
                    f"规格编码：{row_data.get('spec_code') or '-'}\n数量：{row_data.get('quantity') or '-'}"
                )
                color = row_data.get("color")
                if color:
                    item.setBackground(QBrush(QColor(color)))
                items.append(item)
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
            chip.setToolTip(f"商品类型：{category}\n规格名称：{spec_name}\n规格编码：{spec_code}\n数量：{spec.get('quantity') or '-'}")
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
        lines = ["商品类型\t规格名称\t数量"]
        for spec in specs:
            lines.append(
                f"{spec.get('category_label') or '未分类'}\t{spec.get('spec_name') or ''}\t{spec.get('quantity') or ''}"
            )
        return "\n".join(lines)

    def copy_selected(self):
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
        self.all_specs = []
        self.selected_specs = {}
        self.setWindowTitle("产品属性编辑")
        self.resize(760, 560)
        self.init_ui()
        self.load_specs()
        current_text = str(current_value or "").strip()
        self.attribute_edit.setPlainText(current_text)
        name_has_combo_mark = len(self._split_combo_parts(self.current_spec_name)) >= 2
        attribute_has_combo_mark = len(self._split_combo_parts(current_text)) >= 2
        self._source_has_combo_mark = name_has_combo_mark
        if self.initial_combo_state:
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

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.attribute_label = QLabel("产品属性:")
        layout.addWidget(self.attribute_label)
        self.attribute_edit = QTextEdit()
        self.attribute_edit.setPlaceholderText("输入产品属性，例如：17cm、A款17cm、A17cm+B20cm")
        self.attribute_edit.setFixedHeight(110)
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
        self.spec_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.spec_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.spec_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.spec_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
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

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def on_combo_toggled(self, checked):
        self.attribute_label.setVisible(not checked)
        self.attribute_edit.setVisible(not checked)
        self.combo_widget.setVisible(bool(checked))
        self.resize(760, 560 if checked else 320)

    def load_specs(self):
        rows = self.db.safe_fetchall(
            """SELECT COALESCE(category_label, ''), COALESCE(spec_name, ''), spec_code,
                      COALESCE(quantity, ''), COALESCE(product_attribute, ''),
                      COALESCE(product_attribute_combo_disabled, 0), COALESCE(product_attribute_is_combo, 0)
               FROM cost_library
               WHERE COALESCE(spec_code, '') <> ''
                 AND COALESCE(product_attribute, '') <> ''
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
            and not bool(re.search(r"\+|＋|﹢", str(name or "")))
            and not (not int(combo_disabled or 0) and int(attr_is_combo or 0))
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
            selected[match["code"]] = match
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
            for col, value in enumerate((spec["category"], spec["name"], spec["code"], spec["quantity"], spec["attribute"])):
                item = QStandardItem(value)
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 0:
                    item.setData(spec, Qt.UserRole)
                self.spec_model.setItem(row, col, item)

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
            self.selected_specs[code] = spec
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
            full_text = f"{name}{attribute}" if attribute else name
            chip = QWidget()
            chip.setObjectName("attributeComboChip")
            chip.setFixedSize(168, 38)
            chip.setToolTip(f"完整规格：{full_text}\n商品名称：{name}\n规格编码：{code}\n产品属性：{attribute or '-'}")
            chip.setStyleSheet(
                "QWidget#attributeComboChip { background-color: #eef7ff; border: 1px solid #9ec5fe; border-radius: 10px; }"
            )
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 4, 4, 4)
            name_label = QLabel(name)
            name_label.setToolTip(chip.toolTip())
            name_label.setStyleSheet("border: none; background: transparent; color: #1f4e79; font-weight: bold;")
            remove_btn = QPushButton("×")
            remove_btn.setFixedSize(20, 20)
            remove_btn.setStyleSheet(
                "QPushButton { border: none; background-color: #cfe2ff; color: #1f4e79; border-radius: 10px; font-weight: bold; }"
                "QPushButton:hover { background-color: #9ec5fe; }"
            )
            remove_btn.clicked.connect(lambda _checked=False, spec_code=code: self.remove_combo_item(spec_code))
            chip_layout.addWidget(name_label, 1)
            chip_layout.addWidget(remove_btn)
            self.selected_chip_layout.addWidget(chip)
        self.selected_chip_layout.addStretch()

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
        parts = []
        for spec in self.selected_specs.values():
            name = str(spec.get("name") or "").strip()
            attribute = str(spec.get("attribute") or "").strip()
            parts.append(f"{name}{attribute}" if attribute else name)
        return "+".join(part for part in parts if part)

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


class CostLibraryDialog(QDialog):
    """查看、编辑和管理成本库对话框。"""

    COL_CATEGORY = 0
    COL_NAME = 1
    COL_CODE = 2
    COL_ATTRIBUTE = 3
    COL_QUANTITY = 4
    COL_PRODUCT_COST = 5
    COL_UNIT_WEIGHT = 6
    COL_SHIPPING_FEE = 7
    COL_MISC_FEE = 8
    COL_COST = 9
    COL_LISTED_COUNT = 10

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
        self._loading = False
        self._recalculating = False
        self._save_pending = False
        self.cost_mode = self._get_cost_mode()
        self.listing_cart = {}
        self.link_combination_dialog = None
        self.setWindowTitle("成本库管理")
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.resize(1480, 720)
        try:
            self.init_ui()
            self.lbl_count.setText("正在加载...")
            QTimer.singleShot(0, self.load_data)
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
            QTimer.singleShot(0, self._resize_columns_for_content)

    def _get_cost_mode(self):
        if hasattr(self.db, "get_cost_library_mode"):
            return self.db.get_cost_library_mode()
        return "total"

    def on_cost_mode_changed(self):
        self.cost_mode = self.mode_combo.currentData() or "total"
        if hasattr(self.db, "set_cost_library_mode"):
            self.db.set_cost_library_mode(self.cost_mode)
        self._apply_cost_mode_visibility()
        self.load_data()

    def on_sort_mode_changed(self):
        if hasattr(self.db, "set_setting"):
            self.db.set_setting("cost_library_sort_mode", self.sort_combo.currentData() or "type")
        self.load_data()

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
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(self.btn_shipping_rules)
        mode_layout.addWidget(self.btn_misc_fee)
        mode_layout.addStretch()
        layout.addWidget(self.cost_mode_controls)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索商品类型/商品名称/规格编码:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品类型、商品名称或规格编码关键字，空格分隔...")
        self.search_input.textChanged.connect(self.load_data)
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
        btn_refresh.clicked.connect(self.load_data)
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
        btn_history = QPushButton("历史成本")
        self._setup_button(btn_history, "查看成本变化历史")
        btn_history.clicked.connect(self.show_history)
        search_layout.addWidget(btn_history)
        layout.addLayout(search_layout)

        self.model.setHorizontalHeaderLabels([
            "商品类型", "商品名称", "规格编码", "产品属性", "数量", "产品成本", "单个重量kg",
            "快递费", "杂费", "总成本", "已上架规格数"
        ])
        self.model.itemChanged.connect(self.on_item_changed)

        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self._configure_column_widths()
        self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setWordWrap(True)
        self.table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table_view.setStyleSheet(
            "QTableView::item:hover { background-color: #ffffff; color: #000000; }"
        )
        self.table_view.clicked.connect(self.copy_name_or_code)
        self.table_view.doubleClicked.connect(self.open_product_attribute_editor)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_cost_table_context_menu)
        select_all_delegate = SelectAllLineEditDelegate(self.table_view)
        multiline_delegate = MultiLineTextEditDelegate(self.table_view)
        self.table_view.setItemDelegateForColumn(self.COL_CATEGORY, select_all_delegate)
        self.table_view.setItemDelegateForColumn(self.COL_NAME, SpecNameBadgeDelegate(self.table_view))
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
        btn_category_manage = QPushButton("商品类型管理")
        self._setup_button(btn_category_manage, "管理商品类型、颜色和类型内规格排序")
        btn_category_manage.clicked.connect(self.show_category_manage)
        self.btn_link_combos = QPushButton("链接组合")
        self._setup_button(self.btn_link_combos, "查看和维护链接组合")
        self.btn_link_combos.clicked.connect(self.show_link_combinations)
        btn_unlisted = QPushButton("未上架规格")
        self._setup_button(btn_unlisted, "列出当前还没有上架的规格")
        btn_unlisted.clicked.connect(self.show_unlisted_specs)
        btn_add_item = QPushButton("新增商品")
        self._setup_button(btn_add_item, "手动新增一条成本库规格")
        btn_add_item.clicked.connect(self.show_create_item)
        btn_create_link = QPushButton("创建链接")
        self._setup_button(btn_create_link, "用上架车或当前选中规格创建空白链接")
        btn_create_link.clicked.connect(self.create_selected_link)
        self.btn_save = QPushButton("保存修改")
        self._setup_button(self.btn_save, "保存当前表格里已修改的内容")
        self.btn_save.clicked.connect(self.queue_save_changes)
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
            btn_category_manage, self.btn_link_combos, btn_unlisted, btn_add_item,
            btn_create_link, self.btn_save, btn_clear, btn_del, btn_close,
        ):
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_layout.addWidget(self.lbl_count)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_category_manage)
        btn_layout.addWidget(self.btn_link_combos)
        btn_layout.addWidget(btn_unlisted)
        btn_layout.addWidget(btn_add_item)
        btn_layout.addWidget(btn_create_link)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(btn_clear)
        btn_layout.addWidget(btn_del)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def load_data(self):
        try:
            self._loading = True
            self.model.setRowCount(0)
            self._original_rows = {}
            search_text = self.search_input.text().strip()
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
                              COALESCE(cost_library.cost_calc_mode, 'total') AS cost_calc_mode
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
            rows = self.db.safe_fetchall(query)
            self._category_import_order = self._build_category_import_order(rows)
            all_sorted_rows = self._filter_and_sort_rows(rows, "")
            rows = self._filter_and_sort_rows(rows, search_text)
            category_hues = self._category_hues_for_rows(all_sorted_rows)
            gradient_total = max(len(rows) - 1, 1)
            for visible_index, (category_label, spec_name, spec_code, product_attribute, combo_disabled, attr_is_combo, quantity, cost_price, sort_order, source_bg_color, category_color, listed_count, manual_sort_order, category_sort_order, product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode) in enumerate(rows):
                category_value = str(category_label or "")
                name_value = str(spec_name or "")
                code_value = str(spec_code or "")
                attribute_value = str(product_attribute or "")
                combo_disabled_value = int(combo_disabled or 0)
                attr_is_combo_value = int(attr_is_combo or 0)
                quantity_value = self._format_quantity(quantity)
                listed_count_value = str(int(listed_count or 0))
                cost_value = float(cost_price) if cost_price is not None else 0.0
                product_cost_value = float(product_cost) if product_cost is not None else None
                unit_weight_value = float(unit_weight) if unit_weight is not None else None
                shipping_value = float(shipping_fee) if shipping_fee is not None else None
                misc_value = float(misc_fee) if misc_fee is not None else None
                row_color = self._gradient_row_color(category_value, visible_index, gradient_total, category_hues)
                is_combo = self._is_combo_spec(name_value, attribute_value, combo_disabled_value, attr_is_combo_value)
                self._original_rows[code_value] = (
                    category_value, name_value, attribute_value, combo_disabled_value, attr_is_combo_value, quantity_value, cost_value,
                    product_cost_value, unit_weight_value, shipping_value, misc_value, str(cost_calc_mode or "total")
                )

                row_index = self.model.rowCount()
                self.model.insertRow(row_index)

                self._set_item(row_index, self.COL_CATEGORY, category_value, editable=True, bg_color=row_color)
                self._set_item(row_index, self.COL_NAME, name_value, editable=True, bg_color=row_color)
                self._set_name_combo_state(row_index, is_combo)
                self._set_item(row_index, self.COL_CODE, code_value, editable=False, bg_color=row_color)
                self._set_item(row_index, self.COL_ATTRIBUTE, attribute_value, editable=False, bg_color=row_color)
                attr_item = self.model.item(row_index, self.COL_ATTRIBUTE)
                if attr_item:
                    attr_item.setData(combo_disabled_value, Qt.UserRole)
                    attr_item.setData(attr_is_combo_value, Qt.UserRole + 1)
                self._set_item(row_index, self.COL_QUANTITY, quantity_value, editable=(self.cost_mode == "detail"), bg_color=row_color)
                self._set_item(row_index, self.COL_PRODUCT_COST, "" if product_cost_value is None else f"{product_cost_value:.2f}", editable=(self.cost_mode == "detail"), bg_color=row_color)
                self._set_item(row_index, self.COL_UNIT_WEIGHT, "" if unit_weight_value is None else f"{unit_weight_value:.4f}".rstrip("0").rstrip("."), editable=(self.cost_mode == "detail"), bg_color=row_color)
                self._set_item(row_index, self.COL_SHIPPING_FEE, "" if shipping_value is None else f"{shipping_value:.2f}", editable=False, bg_color=row_color)
                self._set_item(row_index, self.COL_MISC_FEE, "" if misc_value is None else f"{misc_value:.2f}", editable=False, bg_color=row_color)
                self._set_item(row_index, self.COL_COST, f"{cost_value:.2f}", editable=(self.cost_mode != "detail"), bg_color=row_color)
                self._set_item(row_index, self.COL_LISTED_COUNT, listed_count_value, editable=False, bg_color=row_color)
                if code_value in self.listing_cart:
                    self.listing_cart[code_value].update({
                        "spec_name": name_value,
                        "spec_code": code_value,
                        "category_label": category_value,
                        "quantity": quantity_value,
                    })
            self._resize_columns_for_content()
            self.refresh_listing_cart_view()
            self.lbl_count.setText(f"共 {self.model.rowCount()} 条数据")
        except Exception:
            import traceback

            print(traceback.format_exc())
            self.lbl_count.setText("加载失败")
        finally:
            self._loading = False

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

    def copy_name_or_code(self, index):
        if index.isValid() and QApplication.keyboardModifiers() & Qt.ControlModifier:
            self.toggle_listing_cart_row(index.row())
            return
        if not index.isValid() or index.column() != self.COL_CODE:
            return
        item = self.model.item(index.row(), index.column())
        text = item.text().strip() if item else ""
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._show_copy_hint("已复制")

    def open_product_attribute_editor(self, index):
        if not index.isValid() or index.column() != self.COL_ATTRIBUTE:
            return
        attribute_item = self.model.item(index.row(), self.COL_ATTRIBUTE)
        code_item = self.model.item(index.row(), self.COL_CODE)
        name_item = self.model.item(index.row(), self.COL_NAME)
        current_value = attribute_item.text().strip() if attribute_item else ""
        spec_code = code_item.text().strip() if code_item else ""
        spec_name = name_item.text().strip() if name_item else ""
        auto_disabled = bool(attribute_item.data(Qt.UserRole)) if attribute_item else False
        is_combo = bool(name_item.data(SpecNameBadgeDelegate.COMBO_STATE_ROLE)) if name_item else False
        dialog = ProductAttributeDialog(self.db, current_value, spec_code, spec_name, auto_disabled, is_combo, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        new_value = dialog.attribute_text()
        combo_disabled = dialog.auto_detect_disable_value()
        attr_is_combo = dialog.is_combo_product()
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
        action_move = None
        if index.column() == self.COL_CATEGORY:
            action_move = menu.addAction("移动到其他商品类型")
        selected = menu.exec_(self.table_view.viewport().mapToGlobal(pos))
        if selected == action_open_material:
            self.open_row_material_library(index.row())
        elif action_move is not None and selected == action_move:
            self.move_row_category(index.row())

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
        except Exception as e:
            QMessageBox.critical(self, "移动失败", f"移动商品类型失败：{e}")
            return

        self._normalize_category_colors()
        self.load_data()
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

        matched = []
        for row in rows:
            category_label, spec_name, spec_code, product_attribute, _combo_disabled, _attr_is_combo, quantity, cost_price, sort_order, source_bg_color, category_color = row[:11]
            full_hit, hit_count = match_score(search_text, terms, category_label, spec_name, spec_code, product_attribute, quantity)
            if hit_count <= 0:
                continue
            matched.append((full_hit, hit_count, self._row_sort_key(row), row))

        matched.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [item[3] for item in matched]

    def _set_item(self, row, col, text, editable, bg_color=""):
        item = QStandardItem(str(text))
        item.setEditable(editable)
        item.setTextAlignment(Qt.AlignCenter)
        if self._is_valid_hex_color(bg_color):
            item.setBackground(QBrush(QColor(bg_color)))
        self.model.setItem(row, col, item)

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
        if self._loading or self._recalculating:
            return
        if item.column() in (self.COL_QUANTITY, self.COL_PRODUCT_COST, self.COL_UNIT_WEIGHT, self.COL_COST):
            self.recalculate_row(item.row())
            QTimer.singleShot(0, self._resize_columns_for_content)

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
                if product_text and weight_text and hasattr(self.db, "calculate_detailed_cost"):
                    product_cost = self._parse_required_non_negative(product_text, "产品成本")
                    unit_weight = self._parse_required_non_negative(weight_text, "单个重量")
                    quantity = quantity_item.text().strip() if quantity_item else ""
                    total_cost, shipping_fee, misc_fee, _total_weight = self.db.calculate_detailed_cost(product_cost, quantity, unit_weight)
                    cost_item.setText(f"{total_cost:.2f}")
                    if shipping_item:
                        shipping_item.setText(f"{shipping_fee:.2f}")
                    if misc_item:
                        misc_item.setText(f"{misc_fee:.2f}")
            self._parse_required_price(cost_item.text())
        except ValueError:
            return
        finally:
            self._recalculating = False

    def queue_save_changes(self):
        if self._save_pending:
            return
        self._save_pending = True
        self._show_copy_hint("正在保存...", 1000)
        self.btn_save.setEnabled(False)
        self.btn_save.setText("保存中...")
        delegates = {
            self.table_view.itemDelegateForColumn(col)
            for col in range(self.model.columnCount())
        }
        for delegate in delegates:
            editor = getattr(delegate, "active_editor", None)
            if editor is not None and not sip.isdeleted(editor):
                delegate.commitData.emit(editor)
                delegate.closeEditor.emit(editor)
        self.table_view.clearFocus()
        QTimer.singleShot(80, self._run_save_changes)

    def _run_save_changes(self):
        try:
            self.save_changes()
        finally:
            self._save_pending = False
            if not sip.isdeleted(self.btn_save):
                self.btn_save.setText("保存修改")
                self.btn_save.setEnabled(True)

    def save_changes(self):
        updates = []
        cost_history_changes = []
        category_changed_codes = []

        for row in range(self.model.rowCount()):
            category_item = self.model.item(row, self.COL_CATEGORY)
            name_item = self.model.item(row, self.COL_NAME)
            code_item = self.model.item(row, self.COL_CODE)
            attribute_item = self.model.item(row, self.COL_ATTRIBUTE)
            quantity_item = self.model.item(row, self.COL_QUANTITY)
            product_item = self.model.item(row, self.COL_PRODUCT_COST)
            weight_item = self.model.item(row, self.COL_UNIT_WEIGHT)
            shipping_item = self.model.item(row, self.COL_SHIPPING_FEE)
            misc_item = self.model.item(row, self.COL_MISC_FEE)
            cost_item = self.model.item(row, self.COL_COST)
            spec_code = code_item.text().strip() if code_item else ""
            if not spec_code or not cost_item:
                continue

            category_label = category_item.text().strip() if category_item else ""
            spec_name = name_item.text().strip() if name_item else ""
            product_attribute = attribute_item.text().strip() if attribute_item else ""
            combo_disabled = int(attribute_item.data(Qt.UserRole) or 0) if attribute_item else 0
            attr_is_combo = int(attribute_item.data(Qt.UserRole + 1) or 0) if attribute_item else 0
            quantity = quantity_item.text().strip() if quantity_item else ""
            try:
                product_text = product_item.text().strip() if product_item else ""
                weight_text = weight_item.text().strip() if weight_item else ""
                use_detail = self.cost_mode == "detail" and (product_text or weight_text)
                product_cost = None
                unit_weight = None
                shipping_fee = None
                misc_fee = None
                cost_calc_mode = "total"
                if use_detail:
                    product_cost = self._parse_required_non_negative(product_text, "产品成本")
                    unit_weight = self._parse_required_non_negative(weight_text, "单个重量")
                    new_cost, shipping_fee, misc_fee, _total_weight = self.db.calculate_detailed_cost(product_cost, quantity, unit_weight)
                    if cost_item:
                        cost_item.setText(f"{new_cost:.2f}")
                    if shipping_item:
                        shipping_item.setText(f"{shipping_fee:.2f}")
                    if misc_item:
                        misc_item.setText(f"{misc_fee:.2f}")
                    cost_calc_mode = "detail"
                else:
                    new_cost = self._parse_required_price(cost_item.text())
            except ValueError as e:
                QMessageBox.warning(self, "成本格式错误", f"第 {row + 1} 行 [{spec_code}]：{e}")
                return

            old_category, old_name, old_attribute, old_combo_disabled, old_attr_is_combo, old_quantity, old_cost, old_product_cost, old_unit_weight, old_shipping_fee, old_misc_fee, old_mode = self._original_rows.get(
                spec_code, ("", "", "", 0, 0, "", None, None, None, None, None, "total")
            )
            category_changed = category_label != old_category
            name_changed = spec_name != old_name
            attribute_changed = product_attribute != old_attribute
            combo_disabled_changed = combo_disabled != int(old_combo_disabled or 0)
            attr_is_combo_changed = attr_is_combo != int(old_attr_is_combo or 0)
            quantity_changed = quantity != old_quantity
            cost_changed = old_cost is None or abs(new_cost - old_cost) > 0.001
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
            if category_changed or name_changed or attribute_changed or combo_disabled_changed or attr_is_combo_changed or cost_changed or detail_changed:
                category_color = self._category_color(category_label) if category_label else ""
                updates.append((
                    spec_code, category_label, category_color, spec_name, quantity,
                    product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
                    new_cost, product_attribute, combo_disabled, attr_is_combo,
                ))
            if category_changed:
                category_changed_codes.append(spec_code)
            if cost_changed:
                cost_history_changes.append((spec_code, old_cost, new_cost))

        if not updates:
            self._show_copy_hint("没有需要保存的修改")
            return

        changed_codes = list(dict.fromkeys(update[0] for update in updates))
        import_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.db.conn.execute("BEGIN TRANSACTION")
            for spec_code, category_label, category_color, spec_name, quantity, product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode, new_cost, product_attribute, combo_disabled, attr_is_combo in updates:
                self.db.cursor.execute(
                    """UPDATE cost_library
                       SET category_label=?, category_color=?, spec_name=?, quantity=?,
                           product_cost=?, unit_weight=?, shipping_fee=?, misc_fee=?, cost_calc_mode=?,
                           cost_price=?, product_attribute=?, product_attribute_combo_disabled=?, product_attribute_is_combo=?
                       WHERE spec_code=?""",
                    (
                        category_label, category_color, spec_name, quantity,
                        product_cost, unit_weight, shipping_fee, misc_fee, cost_calc_mode,
                        new_cost, product_attribute, combo_disabled, attr_is_combo, spec_code,
                    ),
                )

            for spec_code, old_cost, new_cost in cost_history_changes:
                change_amount = None if old_cost is None else new_cost - old_cost
                change_percent = None
                if old_cost not in (None, 0):
                    change_percent = (new_cost - old_cost) / old_cost * 100
                self.db.cursor.execute(
                    """INSERT INTO cost_history
                       (spec_code, old_cost_price, new_cost_price, change_amount, change_percent, source, import_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (spec_code, old_cost, new_cost, change_amount, change_percent, "manual", import_time),
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

        self._show_copy_hint(
            f"已保存 {len(updates)} 条修改，其中 {len(cost_history_changes)} 条成本变化已写入历史记录"
        )
        self.load_data()
        self._refresh_main_products_for_specs(changed_codes)

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

    def _refresh_detail_costs_after_settings(self):
        try:
            changed = self.db.recalculate_detailed_cost_library(record_history=True, source="manual") if hasattr(self.db, "recalculate_detailed_cost_library") else 0
            QMessageBox.information(self, "成功", f"设置已保存，已刷新 {changed} 条详细成本数据。")
            QTimer.singleShot(0, self._refresh_after_detail_cost_change)
        except Exception as e:
            QMessageBox.critical(self, "刷新失败", f"重新计算详细成本失败：{e}")

    def _refresh_after_detail_cost_change(self):
        self.load_data()
        self._refresh_main_products_for_specs()

    def show_shipping_settings(self):
        dialog = ShippingRuleDialog(self.db, self)
        if dialog.exec_() == QDialog.Accepted:
            self._refresh_detail_costs_after_settings()

    def show_misc_fee_settings(self):
        dialog = MiscFeeDialog(self.db, self)
        if dialog.exec_() == QDialog.Accepted:
            self._refresh_detail_costs_after_settings()

    def show_history(self):
        dialog = CostHistoryDialog(self.db, self)
        dialog.exec_()

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
        self._normalize_category_colors()
        self.load_data()
        self._refresh_main_products_for_specs()

    def show_create_item(self):
        dialog = CostItemCreateDialog(self.db, self)
        if dialog.exec_() == QDialog.Accepted:
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
        dialog.destroyed.connect(lambda _=None: QTimer.singleShot(0, self._reload_after_link_combination_closed))
        self.link_combination_dialog = dialog
        self._center_child_dialog(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        if target_product_code and hasattr(dialog, "focus_product"):
            QTimer.singleShot(0, lambda: dialog.focus_product(target_product_code))

    def _reload_after_link_combination_closed(self):
        try:
            if sip.isdeleted(self):
                return
            if hasattr(self, "search_input") and sip.isdeleted(self.search_input):
                return
            if hasattr(self, "lbl_count") and sip.isdeleted(self.lbl_count):
                return
            self.load_data()
        except RuntimeError:
            return

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

            count = 0
            for row in rows:
                item = self.model.item(row, self.COL_CODE)
                if item:
                    self.db.safe_execute("DELETE FROM cost_library WHERE spec_code=?", (item.text(),))
                    count += 1
            QMessageBox.information(self, "成功", f"已删除 {count} 条数据。")
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", f"删除过程中出错：{str(e)}")

    def clear_all(self):
        try:
            reply = QMessageBox.question(
                self,
                "确认清空",
                "确定要清空整个成本库吗？\n此操作不可恢复！\n历史成本记录会保留。",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.db.safe_execute("DELETE FROM cost_library")
                QMessageBox.information(self, "成功", "成本库已清空，历史成本记录已保留。")
                self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "清空失败", f"清空过程中出错：{str(e)}")

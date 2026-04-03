# -*- coding: utf-8 -*-
"""表格列代理：规格名、居中、权重（含锁定图标）"""
from PyQt5.QtWidgets import QStyledItemDelegate, QLineEdit
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QDoubleValidator


class SpecNameDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_length = 40

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setMaxLength(self.max_length)
        # 设置输入框高度与行高匹配
        editor.setFixedHeight(option.rect.height() - 4)  # 减去边距
        return editor


class CenterAlignDelegate(QStyledItemDelegate):
    """数值列居中对齐代理"""
    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignCenter)
        # 设置输入框高度与行高匹配
        editor.setFixedHeight(option.rect.height() - 4)  # 减去边距
        return editor

    def paint(self, painter, option, index):
        painter.save()
        painter.fillRect(option.rect, option.backgroundBrush)
        text = index.data(Qt.DisplayRole)
        if text:
            painter.drawText(option.rect, Qt.AlignCenter, str(text))
        painter.restore()


class WeightDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lock_icon = "🔒"
        self.icon_width = 25

    def paint(self, painter, option, index):
        text = index.data(Qt.DisplayRole) or ""
        is_locked = text.startswith(self.lock_icon)
        num_text = text.replace(self.lock_icon, "").strip()
        rect = option.rect
        w = rect.width() - self.icon_width
        h = rect.height()
        text_rect = QRect(rect.left(), rect.top(), w, h)
        icon_rect = QRect(rect.right() - self.icon_width, rect.top(), self.icon_width, h)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, num_text)
        if is_locked:
            painter.drawText(icon_rect, Qt.AlignCenter, self.lock_icon)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # 设置输入框高度与行高匹配
        editor.setFixedHeight(option.rect.height() - 4)  # 减去边距
        text = index.data(Qt.DisplayRole) or ""
        num_text = text.replace("🔒", "").strip()
        import re
        match = re.match(r'^([\d.]+)', num_text)
        if match:
            num_text = match.group(1)
        else:
            num_text = ""
        try:
            current_val = float(num_text)
        except ValueError:
            current_val = 0.0
        editor.setText(num_text)

        def get_max_allowed():
            model = index.model()
            row_count = model.rowCount()
            current_row = index.row()
            locked_sum = 0.0
            for r in range(row_count):
                if r == current_row:
                    continue
                idx = model.index(r, 7)
                cell_text = model.data(idx, Qt.DisplayRole) or ""
                if cell_text.startswith("🔒"):
                    try:
                        clean_text = cell_text.replace("🔒", "").strip()
                        import re
                        match = re.match(r'^([\d.]+)', clean_text)
                        if match:
                            val = float(match.group(1))
                        else:
                            val = 0.0
                        locked_sum += val
                    except ValueError:
                        pass
            max_val = 100.0 - locked_sum
            return max_val if max_val > 0 else 0.0

        def on_text_changed(new_text):
            if not new_text:
                return
            try:
                val = float(new_text)
            except ValueError:
                return
            max_allowed = get_max_allowed()
            if val > max_allowed:
                editor.blockSignals(True)
                corrected = f"{max_allowed:.2f}"
                editor.setText(corrected)
                editor.setCursorPosition(len(corrected))
                editor.blockSignals(False)

        editor.textChanged.connect(on_text_changed)
        validator = QDoubleValidator(0.0, 9999.0, 2, editor)
        editor.setValidator(validator)
        return editor

    def setModelData(self, editor, model, index):
        raw_text = editor.text().strip()
        if not raw_text:
            raw_text = "0.00"
        try:
            clean_text = raw_text.replace("🔒", "").replace(" ", "")
            val = round(float(clean_text), 2)
        except ValueError:
            return
        old_text = model.data(index, Qt.DisplayRole) or ""
        is_locked = old_text.startswith("🔒")
        final_text = f"🔒 {val:.2f}" if is_locked else f"{val:.2f}"
        model.setData(index, final_text, Qt.DisplayRole)

    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect
        rect.setRight(rect.right() - self.icon_width)
        editor.setGeometry(rect)

    def editorEvent(self, event, model, option, index):
        if event.type() == event.MouseButtonDblClick and event.button() == Qt.LeftButton:
            rect = option.rect
            icon_rect = QRect(rect.right() - self.icon_width, rect.top(), self.icon_width, rect.height())
            pos = event.pos()
            if icon_rect.contains(pos):
                current_text = index.data(Qt.DisplayRole) or ""
                is_locked = current_text.startswith(self.lock_icon)
                num_text = current_text.replace(self.lock_icon, "").strip()
                new_text = f"🔒 {num_text}" if not is_locked else f"{num_text}"
                model.setData(index, new_text, Qt.DisplayRole)
                return True
        return super().editorEvent(event, model, option, index)

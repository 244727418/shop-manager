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
        editor.setFixedHeight(option.rect.height() - 4)
        return editor


class CenterAlignDelegate(QStyledItemDelegate):
    """数值列居中对齐代理"""
    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignCenter)
        editor.setFixedHeight(option.rect.height() - 4)
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
        self.icon_width = 20

    def paint(self, painter, option, index):
        text = index.data(Qt.DisplayRole) or ""
        is_locked = text.startswith(self.lock_icon)
        num_text = text.replace(self.lock_icon, "").strip()
        rect = option.rect
        w = rect.width() - self.icon_width
        h = rect.height()
        text_rect = QRect(rect.left(), rect.top(), w, h)
        icon_rect = QRect(rect.right() - self.icon_width, rect.top(), self.icon_width, h)
        painter.drawText(text_rect, Qt.AlignCenter, num_text)
        if is_locked:
            painter.drawText(icon_rect, Qt.AlignCenter, self.lock_icon)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignCenter)
        editor.setFixedHeight(option.rect.height() - 4)
        text = index.data(Qt.DisplayRole) or ""
        num_text = text.replace("🔒", "").strip()
        import re
        match = re.match(r'^([\d.]+)', num_text)
        if match:
            num_text = match.group(1)
        editor.setText(num_text)
        validator = QDoubleValidator(editor)
        editor.setValidator(validator)
        return editor

    def setEditorData(self, editor, index):
        text = index.data(Qt.DisplayRole) or ""
        num_text = text.replace("🔒", "").strip()
        import re
        match = re.match(r'^([\d.]+)', num_text)
        if match:
            editor.setText(match.group(1))

    def setModelData(self, editor, model, index):
        text = editor.text()
        is_locked = index.data(Qt.DisplayRole) and index.data(Qt.DisplayRole).startswith(self.lock_icon)
        if is_locked:
            text = f"{self.lock_icon} {text}"
        model.setData(index, text, Qt.EditRole)

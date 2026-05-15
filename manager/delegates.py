# -*- coding: utf-8 -*-
"""表格列代理：规格名、居中、权重（含锁定图标）"""
from PyQt5.QtWidgets import QStyledItemDelegate, QPlainTextEdit, QLineEdit
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QDoubleValidator, QFont


class SpecNameDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_length = 40
        self._editing_index = None

    def paint(self, painter, option, index):
        painter.save()
        if index != self._editing_index:
            super().paint(painter, option, index)
        else:
            painter.fillRect(option.rect, option.backgroundBrush)
        painter.restore()

    def createEditor(self, parent, option, index):
        self._editing_index = index
        editor = QPlainTextEdit(parent)
        editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setFrameStyle(0)
        editor.setStyleSheet(
            "QPlainTextEdit { "
            "border: none; "
            "margin: 0px; "
            "padding: 0px; "
            "background-color: white; "
            "font-size: 13px; "
            "font-weight: normal; "
            "text-align: center; "
            "}"
        )
        editor.document().setDocumentMargin(0)
        return editor

    def setEditorData(self, editor, index):
        text = index.data(Qt.DisplayRole) or ""
        editor.setPlainText(text)

    def setModelData(self, editor, model, index):
        text = editor.toPlainText()
        if len(text) > self.max_length:
            text = text[:self.max_length]
        model.setData(index, text, Qt.EditRole)

    def destroyEditor(self, editor, index):
        self._editing_index = None
        super().destroyEditor(editor, index)


class CenterAlignDelegate(QStyledItemDelegate):
    """数值列居中对齐代理"""
    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignCenter)
        editor.setFont(option.font)
        editor.setFrame(False)
        editor.setTextMargins(1, 0, 1, 0)
        editor.setStyleSheet(
            "QLineEdit { "
            "padding: 1px; "
            "margin: 0px; "
            "border: none; "
            "background-color: #eaf8ee; "
            "font-family: YouYuan, 'Microsoft YaHei UI', sans-serif; "
            "font-weight: bold; "
            "}"
        )
        editor.setFixedHeight(option.rect.height())
        return editor

    def paint(self, painter, option, index):
        painter.save()
        font = QFont(option.font)
        font.setFamily("YouYuan")
        font.setBold(True)
        painter.setFont(font)
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
        h = rect.height()
        if is_locked:
            text_rect = QRect(rect.left(), rect.top(), max(1, rect.width() - self.icon_width), h)
            icon_rect = QRect(rect.right() - self.icon_width, rect.top(), self.icon_width, h)
        else:
            text_rect = rect
            icon_rect = QRect()
        painter.save()
        font = QFont(option.font)
        font.setFamily("YouYuan")
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignCenter, num_text)
        if is_locked:
            painter.drawText(icon_rect, Qt.AlignCenter, self.lock_icon)
        painter.restore()

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignCenter)
        editor.setFont(option.font)
        editor.setFrame(False)
        editor.setTextMargins(1, 0, 1, 0)
        editor.setStyleSheet(
            "QLineEdit { "
            "padding: 1px; "
            "margin: 0px; "
            "border: none; "
            "background-color: #eaf8ee; "
            "font-family: YouYuan, 'Microsoft YaHei UI', sans-serif; "
            "font-weight: bold; "
            "}"
        )
        editor.setFixedHeight(option.rect.height())
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

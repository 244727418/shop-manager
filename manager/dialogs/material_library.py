# -*- coding: utf-8 -*-
"""Local material library dialog."""
import hashlib
import gc
import filecmp
import html
import io
import json
import os
import re
import shutil
import struct
import time
from urllib.parse import urlparse

import requests
from PyQt5.QtCore import QEvent, QMimeData, QPoint, QPropertyAnimation, QRect, QSize, Qt, QSettings, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QDesktopServices, QDrag, QFont, QIcon, QImage, QImageReader, QKeySequence, QPainter, QPixmap, QTextDocument
try:
    from PyQt5 import sip
except ImportError:
    import sip

try:
    from ..window_icons import apply_window_icon
except ImportError:
    from window_icons import apply_window_icon

try:
    from ..pinyin_search import all_terms_match, split_search_terms
except ImportError:
    from pinyin_search import all_terms_match, split_search_terms
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QLayout,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QDialogButtonBox,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=8):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        item = self._items.pop(index) if 0 <= index < len(self._items) else None
        self.invalidate()
        return item

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            space_x = self.spacing()
            space_y = self.spacing()
            hint = item.sizeHint()
            next_x = x + hint.width() + space_x
            if next_x - space_x > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
            if widget:
                widget.setVisible(True)
        return y + line_height - rect.y() + margins.bottom()


class DeletedLinkToolButton(QToolButton):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 115))
        pen = painter.pen()
        pen.setColor(QColor("#d9534f"))
        pen.setWidth(3)
        painter.setPen(pen)
        y = self.rect().center().y()
        painter.drawLine(8, y, self.width() - 8, y)
        painter.end()


class MaterialImageItemDelegate(QStyledItemDelegate):
    @staticmethod
    def item_regions(option):
        widget = getattr(option, "widget", None)
        compact = getattr(widget, "compact_material_view", False)
        rect = option.rect.adjusted(1, 1, -1, -1)
        text_height = 52 if compact else 62
        gap = 2
        text_rect = QRect(rect.left() + 1, rect.bottom() - text_height + 1, rect.width() - 2, text_height)
        available_height = max(1, rect.height() - text_height - gap - 2)
        square_size = max(1, min(rect.width() - 2, available_height))
        icon_rect = QRect(
            rect.left() + (rect.width() - square_size) // 2,
            rect.top() + 1,
            square_size,
            square_size,
        )
        return rect, icon_rect, text_rect

    def paint(self, painter, option, index):
        option.state &= ~QStyle.State_HasFocus
        if index.data(MaterialImageList.EMPTY_ROLE):
            painter.save()
            rect = option.rect.adjusted(2, 2, -2, -2)
            painter.fillRect(rect, QColor("#ffffff"))
            painter.setPen(QColor("#8a8f98"))
            painter.drawText(
                rect.adjusted(6, 4, -6, -4),
                Qt.AlignCenter | Qt.TextWordWrap,
                str(index.data(Qt.DisplayRole) or ""),
            )
            painter.restore()
            return
        rect, icon_rect, text_rect = self.item_regions(option)
        selected = bool(option.state & QStyle.State_Selected)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(rect, QColor("#e8f4ff") if selected else QColor("#ffffff"))
        painter.setPen(QColor("#3498db") if selected else QColor("#111111"))
        painter.drawRect(rect)
        painter.setPen(QColor("#c7ccd4"))
        painter.drawRect(icon_rect.adjusted(0, 0, -1, -1))

        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            target = icon_rect
            source_size = QSize(max(target.width(), target.height()) * 2, max(target.width(), target.height()) * 2)
            pixmap = icon.pixmap(source_size)
            if not pixmap.isNull():
                pixmap = pixmap.scaledToWidth(target.width(), Qt.SmoothTransformation)
                x = target.left() + (target.width() - pixmap.width()) // 2
                y = target.top() + (target.height() - pixmap.height()) // 2
                painter.setClipRect(target)
                painter.drawPixmap(x, y, pixmap)
                painter.setClipping(False)

        painter.setPen(QColor("#3498db") if selected else QColor("#8a8f98"))
        painter.drawRect(text_rect.adjusted(0, 0, -1, -1))
        painter.setPen(QColor("#1f2d3d"))
        font = painter.font()
        current_size = font.pointSizeF()
        font.setPointSizeF(max(6.0, current_size if current_size > 0 else 9.0))
        font.setLetterSpacing(QFont.PercentageSpacing, 92)
        painter.setFont(font)
        label_rect = text_rect.adjusted(1, 1, -1, -1)
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setDocumentMargin(0)
        doc.setTextWidth(label_rect.width())
        text = html.escape(str(index.data(Qt.DisplayRole) or "")).replace("\n", "<br>")
        doc.setHtml(f'<div style="line-height:0.5px;">{text}</div>')
        painter.setClipRect(label_rect)
        painter.translate(label_rect.topLeft())
        doc.drawContents(painter)
        painter.restore()

    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setLineWrapMode(QTextEdit.WidgetWidth)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setStyleSheet(
            'QTextEdit { border: 1px solid #3498db; border-radius: 4px; padding: 1px; '
            'background: #ffffff; color: #1f2d3d; font: 9pt "Microsoft YaHei"; }'
        )
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        text = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
        prefix = str(index.data(Qt.UserRole + 4) or "")
        if prefix:
            window = self.parent().window() if self.parent() else None
            if window and hasattr(window, "editable_product_material_name"):
                text = window.editable_product_material_name(text, prefix)
        link_prefix = str(index.data(Qt.UserRole + 5) or "")
        if link_prefix:
            window = self.parent().window() if self.parent() else None
            if window and hasattr(window, "editable_link_material_name"):
                text = window.editable_link_material_name(text, link_prefix)
        editor.setPlainText(text)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText().strip(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        _rect, _icon_rect, text_rect = self.item_regions(option)
        editor.setGeometry(text_rect.adjusted(1, 1, -1, -1))

    def eventFilter(self, editor, event):
        if isinstance(editor, QTextEdit):
            if event.type() == QEvent.FocusOut:
                self.commitData.emit(editor)
                self.closeEditor.emit(editor)
                return False
            if event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    self.commitData.emit(editor)
                    self.closeEditor.emit(editor)
                    return True
                if event.key() == Qt.Key_Escape:
                    self.closeEditor.emit(editor)
                    return True
        return super().eventFilter(editor, event)


class MaterialImageList(QListWidget):
    PATH_ROLE = Qt.UserRole + 1
    ORIGINAL_TEXT_ROLE = Qt.UserRole + 2
    PREFIX_ROLE = Qt.UserRole + 3
    PRODUCT_NAME_PREFIX_ROLE = Qt.UserRole + 4
    LINK_NAME_PREFIX_ROLE = Qt.UserRole + 5
    EMPTY_ROLE = Qt.UserRole + 6
    INTERNAL_MOVE_MIME = "application/x-shop-material-image-paths"
    INTERNAL_SOURCE_COLUMN_MIME = "application/x-shop-material-source-column"
    WINDOWS_FILE_DROP_MIME = "application/x-qt-windows-mime;value=\"FileNameW\""
    WINDOWS_DROPFILES_MIME = "application/x-qt-windows-mime;value=\"FileDrop\""

    def __init__(self, parent=None, column_key=None, compact=False):
        super().__init__(parent)
        self.material_column_key = column_key
        self.compact_material_view = compact
        self._reorder_target_row = -1
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(84, 84) if compact else QSize(134, 134))
        self.setGridSize(QSize(86, 140) if compact else QSize(136, 202))
        self._preferred_grid_width = self.gridSize().width()
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setWrapping(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(12)
        self.verticalScrollBar().setPageStep(96)
        self.horizontalScrollBar().setSingleStep(12)
        self.setSpacing(0 if compact else 1)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.ElideNone)
        self.setUniformItemSizes(False)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.viewport().installEventFilter(self)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setDropIndicatorShown(True)
        self.setItemDelegate(MaterialImageItemDelegate(self))
        if compact:
            self.setStyleSheet(
                """
                QListWidget {
                    border: 1px solid #111111;
                    border-radius: 0px;
                    background: #ffffff;
                    padding: 1px;
                }
                QListWidget::item {
                    border: none;
                    padding: 0px;
                    margin: 0px;
                }
                QListWidget::item:selected {
                    background: #e8f4ff;
                    color: #1f2d3d;
                    outline: none;
                }
                QListWidget::item:focus {
                    outline: none;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                QListWidget {
                    border: 1px solid #111111;
                    border-radius: 6px;
                    background: #ffffff;
                    padding: 1px;
                }
                QListWidget::item {
                    border: 1px solid #111111;
                    border-radius: 3px;
                    padding: 1px;
                }
                QListWidget::item:selected {
                    background: #e8f4ff;
                    border-color: #3498db;
                    color: #1f2d3d;
                    outline: none;
                }
                QListWidget::item:focus {
                    outline: none;
                }
                """
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_grid_to_viewport()

    def fit_grid_to_viewport(self):
        viewport_width = self.viewport().width()
        if viewport_width <= 0:
            return
        grid = self.gridSize()
        spacing = max(0, self.spacing())
        preferred_width = max(1, getattr(self, "_preferred_grid_width", grid.width()))
        columns = getattr(self, "_fixed_columns", 0) or max(1, round(viewport_width / max(1, preferred_width + spacing)))
        edge_reserve = columns if self.compact_material_view else 1
        fitted_width = max(1, (viewport_width - spacing * max(0, columns - 1) - edge_reserve) // columns)
        if abs(fitted_width - grid.width()) <= 1:
            return
        text_height = 52 if self.compact_material_view else 62
        image_width = max(1, fitted_width - 2)
        self.setIconSize(QSize(image_width, image_width))
        self.setGridSize(QSize(fitted_width, fitted_width + text_height + 4))
        for index in range(self.count()):
            self.item(index).setSizeHint(self.gridSize())

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_thumbnails(1 if delta > 0 else -1)
                event.accept()
                return
        super().wheelEvent(event)

    def zoom_thumbnails(self, direction):
        step = 10
        min_size, max_size = (54, 150) if self.compact_material_view else (88, 240)
        current_width = getattr(self, "_preferred_grid_width", self.gridSize().width())
        new_width = max(min_size, min(max_size, current_width + direction * step))
        if new_width == current_width:
            return
        self._preferred_grid_width = new_width
        self.fit_grid_to_viewport()
        self.viewport().update()

    def restore_selection_by_paths(self, paths):
        wanted = set(paths or [])
        if not wanted:
            return
        first = None
        for index in range(self.count()):
            item = self.item(index)
            path = self.item_path(item)
            selected = bool(path and os.path.abspath(path) in wanted)
            item.setSelected(selected)
            if selected and first is None:
                first = item
        if first:
            self.setCurrentItem(first)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            parent = self.window()
            if hasattr(parent, "copy_selected_images"):
                parent.copy_selected_images(self)
                return
        if event.matches(QKeySequence.Cut):
            parent = self.window()
            if hasattr(parent, "copy_selected_images"):
                parent.copy_selected_images(self, cut=True)
                return
        if event.matches(QKeySequence.Paste):
            parent = self.window()
            if hasattr(parent, "paste_images_from_clipboard"):
                parent.paste_images_from_clipboard(self)
                return
        if event.key() == Qt.Key_Delete:
            parent = self.window()
            if hasattr(parent, "delete_images"):
                parent.delete_images(self)
                return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        if not item:
            super().mouseDoubleClickEvent(event)
            return
        rect = self.visualItemRect(item)
        text_height = 38 if self.compact_material_view else 46
        name_rect = QRect(rect.left() + 1, rect.bottom() - text_height + 2, rect.width() - 2, text_height - 1)
        parent = self.window()
        if not name_rect.contains(event.pos()):
            if hasattr(parent, "open_image_viewer"):
                parent.open_image_viewer(item)
                return
        self.editItem(item)

    def eventFilter(self, watched, event):
        if watched is self.viewport() and event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            parent = self.window()
            if hasattr(parent, "set_active_link_image_column"):
                parent.set_active_link_image_column(self.material_column_key)
            mime_data = event.mimeData()
            if self.is_internal_reorder_drop(mime_data):
                if event.type() == QEvent.DragMove:
                    self.update_reorder_target(event.pos())
                elif event.type() == QEvent.Drop:
                    self.reorder_paths_to_pos(self.paths_from_internal_mime(mime_data), event.pos())
                    self._reorder_target_row = -1
                event.setDropAction(Qt.MoveAction)
                event.accept()
                return True
            if not hasattr(parent, "can_import_mime_data") or not parent.can_import_mime_data(mime_data):
                return super().eventFilter(watched, event)
            event.setDropAction(Qt.MoveAction if mime_data.hasFormat(self.INTERNAL_MOVE_MIME) else Qt.CopyAction)
            if event.type() == QEvent.Drop:
                if hasattr(parent, "import_from_mime_data") and parent.import_from_mime_data(mime_data):
                    event.accept()
                    return True
                return super().eventFilter(watched, event)
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def is_internal_reorder_drop(self, mime_data):
        parent = self.window()
        if not mime_data.hasFormat(self.INTERNAL_MOVE_MIME):
            return False
        return getattr(parent, "library_mode", None) == getattr(parent, "PRODUCT_MODE", None) and not self.material_column_key

    def update_reorder_target(self, pos):
        item = self.itemAt(pos)
        row = self.row(item) if item else self.count() - 1
        if row == self._reorder_target_row:
            return
        self._reorder_target_row = row
        if item and self.item_path(item):
            self.flash_reordered_items([item])

    def item_path(self, item):
        if not item:
            return ""
        path = item.data(self.PATH_ROLE)
        return path if path and os.path.exists(path) else ""

    def reorder_selected_items_to_pos(self, pos):
        return self.reorder_paths_to_pos(self.selected_image_paths(), pos)

    def reorder_paths_to_pos(self, paths, pos):
        normalized_paths = [os.path.abspath(path) for path in paths or [] if path]
        target_item = self.itemAt(pos)
        target_row = self.row(target_item) if target_item else self.count()
        selected_rows = []
        for index in range(self.count()):
            item = self.item(index)
            path = self.item_path(item)
            if path and os.path.abspath(path) in normalized_paths:
                selected_rows.append(index)
        if not selected_rows:
            return False
        if target_row in selected_rows and len(selected_rows) == 1:
            return True
        moving = []
        for row in reversed(selected_rows):
            moving.insert(0, self.takeItem(row))
            if row < target_row:
                target_row -= 1
        target_row = max(0, min(target_row, self.count()))
        for offset, item in enumerate(moving):
            self.insertItem(target_row + offset, item)
            item.setSelected(True)
        self.setCurrentItem(moving[0])
        self.flash_reordered_items(moving)
        parent = self.window()
        if hasattr(parent, "remember_product_image_order"):
            parent.remember_product_image_order(self)
        return True

    def flash_reordered_items(self, items):
        original = []
        for item in items:
            original.append((item, item.background()))
            item.setBackground(QColor("#fff3cd"))
        QTimer.singleShot(220, lambda: [item.setBackground(brush) for item, brush in original])

    def dragEnterEvent(self, event):
        parent = self.window()
        if hasattr(parent, "set_active_link_image_column"):
            parent.set_active_link_image_column(self.material_column_key)
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.setDropAction(Qt.MoveAction if event.mimeData().hasFormat(self.INTERNAL_MOVE_MIME) else Qt.CopyAction)
            event.accept()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        parent = self.window()
        if hasattr(parent, "set_active_link_image_column"):
            parent.set_active_link_image_column(self.material_column_key)
        if self.is_internal_reorder_drop(event.mimeData()):
            self.update_reorder_target(event.pos())
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.setDropAction(Qt.MoveAction if event.mimeData().hasFormat(self.INTERNAL_MOVE_MIME) else Qt.CopyAction)
            event.accept()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        parent = self.window()
        if hasattr(parent, "set_active_link_image_column"):
            parent.set_active_link_image_column(self.material_column_key)
        if self.is_internal_reorder_drop(event.mimeData()):
            self.reorder_paths_to_pos(self.paths_from_internal_mime(event.mimeData()), event.pos())
            self._reorder_target_row = -1
            event.setDropAction(Qt.MoveAction)
            event.accept()
            return
        if hasattr(parent, "import_from_mime_data") and parent.import_from_mime_data(event.mimeData()):
            event.setDropAction(Qt.MoveAction if event.mimeData().hasFormat(self.INTERNAL_MOVE_MIME) else Qt.CopyAction)
            event.accept()
            return
        super().dropEvent(event)

    def selected_image_paths(self):
        paths = []
        for item in self.selectedItems():
            path = item.data(self.PATH_ROLE)
            if path and os.path.exists(path) and path not in paths:
                paths.append(path)
        return paths

    def paths_from_internal_mime(self, mime_data):
        if not mime_data.hasFormat(self.INTERNAL_MOVE_MIME):
            return []
        try:
            text = bytes(mime_data.data(self.INTERNAL_MOVE_MIME)).decode("utf-8")
        except Exception:
            return []
        paths = []
        for line in text.splitlines():
            path = line.strip()
            if path and os.path.exists(path) and path not in paths:
                paths.append(path)
        return paths

    def windows_file_drop_data(self, paths):
        return ("\0".join(paths) + "\0\0").encode("utf-16le")

    def windows_dropfiles_data(self, paths):
        files = self.windows_file_drop_data(paths)
        return struct.pack("<IiiII", 20, 0, 0, 0, 1) + files

    def set_file_drag_mime(self, mime, paths):
        mime.setData(self.WINDOWS_DROPFILES_MIME, self.windows_dropfiles_data(paths))
        mime.setData(self.WINDOWS_FILE_DROP_MIME, self.windows_file_drop_data(paths))

    def mimeData(self, items):
        paths = []
        for item in items:
            path = item.data(self.PATH_ROLE)
            if path and os.path.exists(path) and path not in paths:
                paths.append(path)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        self.set_file_drag_mime(mime, paths)
        mime.setData(self.INTERNAL_MOVE_MIME, "\n".join(paths).encode("utf-8"))
        if self.material_column_key:
            mime.setData(self.INTERNAL_SOURCE_COLUMN_MIME, str(self.material_column_key).encode("utf-8"))
        return mime

    def startDrag(self, supported_actions):
        paths = self.selected_image_paths()
        if not paths:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        self.set_file_drag_mime(mime, paths)
        mime.setData(self.INTERNAL_MOVE_MIME, "\n".join(paths).encode("utf-8"))
        if self.material_column_key:
            mime.setData(self.INTERNAL_SOURCE_COLUMN_MIME, str(self.material_column_key).encode("utf-8"))
        drag.setMimeData(mime)
        current = self.currentItem()
        if current and current.icon():
            pixmap = current.icon().pixmap(self.iconSize())
            if not pixmap.isNull():
                drag.setPixmap(pixmap)
        drag.exec_(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)

    def enterEvent(self, event):
        parent = self.window()
        if hasattr(parent, "set_active_link_image_column"):
            parent.set_active_link_image_column(self.material_column_key)
        super().enterEvent(event)


class MaterialImageViewerDialog(QDialog):
    def __init__(self, image_path, parent=None, image_paths=None):
        super().__init__(parent)
        paths = [path for path in (image_paths or []) if path and os.path.exists(path)]
        if image_path and os.path.exists(image_path) and image_path not in paths:
            paths.insert(0, image_path)
        self.image_paths = paths or [image_path]
        self.current_index = max(0, self.image_paths.index(image_path)) if image_path in self.image_paths else 0
        self.pixmap = QPixmap()
        self.scale_factor = 1.0
        self.current_display_scale = 1.0
        self.fit_to_window = True
        self._dragging_image = False
        self._drag_start_pos = QPoint()
        self._drag_start_h = 0
        self._drag_start_v = 0
        self.resize(900, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        self.btn_prev = QPushButton("上一张")
        self.btn_prev.clicked.connect(self.show_previous_image)
        self.btn_next = QPushButton("下一张")
        self.btn_next.clicked.connect(self.show_next_image)
        self.btn_zoom_out = QPushButton("缩小")
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_by(0.8))
        self.btn_zoom_in = QPushButton("放大")
        self.btn_zoom_in.clicked.connect(lambda: self.zoom_by(1.25))
        self.btn_actual = QPushButton("原始尺寸")
        self.btn_actual.clicked.connect(self.show_actual_size)
        self.btn_fit = QPushButton("适应窗口")
        self.btn_fit.clicked.connect(self.show_fit_to_window)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #555;")
        toolbar.addWidget(self.btn_prev)
        toolbar.addWidget(self.btn_next)
        toolbar.addSpacing(10)
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_actual)
        toolbar.addWidget(self.btn_fit)
        toolbar.addWidget(self.info_label, 1)
        self.btn_prev.setVisible(False)
        self.btn_next.setVisible(False)
        self.btn_zoom_out.setVisible(False)
        self.btn_zoom_in.setVisible(False)
        layout.addLayout(toolbar)
        viewer_layout = QHBoxLayout()
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(4)
        self.side_prev_button = QPushButton("<")
        self.side_prev_button.setFixedWidth(38)
        self.side_prev_button.setToolTip("上一张")
        self.side_prev_button.clicked.connect(self.show_previous_image)
        self.side_next_button = QPushButton(">")
        self.side_next_button.setFixedWidth(38)
        self.side_next_button.setToolTip("下一张")
        self.side_next_button.clicked.connect(self.show_next_image)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { background: #111; border: 1px solid #222; }")
        self.scroll_area.viewport().installEventFilter(self)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #111; color: white;")
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.installEventFilter(self)
        self.image_label.setCursor(Qt.OpenHandCursor)
        self.scroll_area.setWidget(self.image_label)
        viewer_layout.addWidget(self.side_prev_button)
        viewer_layout.addWidget(self.scroll_area, 1)
        viewer_layout.addWidget(self.side_next_button)
        layout.addLayout(viewer_layout, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.load_current_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_to_window:
            self.update_pixmap()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.show_previous_image()
            return
        if event.key() == Qt.Key_Right:
            self.show_next_image()
            return
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_by(1.25)
            return
        if event.key() == Qt.Key_Minus:
            self.zoom_by(0.8)
            return
        if event.key() == Qt.Key_0:
            self.show_fit_to_window()
            return
        if event.key() == Qt.Key_1:
            self.show_actual_size()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        self.zoom_at(
            1.15 if event.angleDelta().y() > 0 else 1 / 1.15,
            self.scroll_area.viewport().mapFromGlobal(event.globalPos()),
        )
        event.accept()

    def eventFilter(self, watched, event):
        if watched in (self.scroll_area.viewport(), self.image_label):
            if event.type() == QEvent.Wheel:
                viewport_pos = event.pos()
                if watched is self.image_label:
                    viewport_pos = self.image_label.mapTo(self.scroll_area.viewport(), event.pos())
                self.zoom_at(1.15 if event.angleDelta().y() > 0 else 1 / 1.15, viewport_pos)
                event.accept()
                return True
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._dragging_image = True
                self._drag_start_pos = event.globalPos()
                self._drag_start_h = self.scroll_area.horizontalScrollBar().value()
                self._drag_start_v = self.scroll_area.verticalScrollBar().value()
                self.image_label.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return True
            if event.type() == QEvent.MouseMove and self._dragging_image:
                delta = event.globalPos() - self._drag_start_pos
                self.scroll_area.horizontalScrollBar().setValue(self._drag_start_h - delta.x())
                self.scroll_area.verticalScrollBar().setValue(self._drag_start_v - delta.y())
                event.accept()
                return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self._dragging_image = False
                self.image_label.setCursor(Qt.OpenHandCursor)
                event.accept()
                return True
            if event.type() == QEvent.Leave and self._dragging_image:
                self._dragging_image = False
                self.image_label.setCursor(Qt.OpenHandCursor)
        return super().eventFilter(watched, event)

    def current_path(self):
        if 0 <= self.current_index < len(self.image_paths):
            return self.image_paths[self.current_index]
        return ""

    def load_current_image(self):
        path = self.current_path()
        self.pixmap = QPixmap(path)
        self.scale_factor = 1.0
        self.fit_to_window = True
        self.setWindowTitle(os.path.basename(path) if path else "图片查看")
        self.update_pixmap()

    def show_previous_image(self):
        if len(self.image_paths) <= 1:
            return
        self.current_index = (self.current_index - 1) % len(self.image_paths)
        self.load_current_image()

    def show_next_image(self):
        if len(self.image_paths) <= 1:
            return
        self.current_index = (self.current_index + 1) % len(self.image_paths)
        self.load_current_image()

    def zoom_by(self, factor):
        center = self.scroll_area.viewport().rect().center()
        self.zoom_at(factor, center)

    def zoom_at(self, factor, viewport_pos):
        if self.pixmap.isNull():
            return
        old_size = self.image_label.size()
        if old_size.width() <= 0 or old_size.height() <= 0:
            return
        if viewport_pos is None:
            viewport_pos = self.scroll_area.viewport().rect().center()
        label_pos = self.image_label.mapFrom(self.scroll_area.viewport(), viewport_pos)
        rel_x = max(0.0, min(1.0, label_pos.x() / max(1, old_size.width())))
        rel_y = max(0.0, min(1.0, label_pos.y() / max(1, old_size.height())))
        if self.fit_to_window:
            self.scale_factor = self.current_display_scale
        self.fit_to_window = False
        self.scale_factor = max(0.05, min(8.0, self.scale_factor * factor))
        self.update_pixmap()
        new_size = self.image_label.size()
        target_x = int(rel_x * new_size.width() - viewport_pos.x())
        target_y = int(rel_y * new_size.height() - viewport_pos.y())
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        hbar.setValue(max(hbar.minimum(), min(hbar.maximum(), target_x)))
        vbar.setValue(max(vbar.minimum(), min(vbar.maximum(), target_y)))

    def show_actual_size(self):
        if self.pixmap.isNull():
            return
        self.fit_to_window = False
        self.scale_factor = 1.0
        self.update_pixmap()

    def show_fit_to_window(self):
        self.fit_to_window = True
        self.update_pixmap()

    def update_pixmap(self):
        if self.pixmap.isNull():
            self.image_label.setText("图片无法打开")
            return
        target = self.scroll_area.viewport().size()
        if target.width() <= 2 or target.height() <= 2:
            return
        if self.fit_to_window:
            scaled = self.pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            shown_scale = scaled.width() / max(1, self.pixmap.width())
        else:
            scaled_size = QSize(
                max(1, int(self.pixmap.width() * self.scale_factor)),
                max(1, int(self.pixmap.height() * self.scale_factor)),
            )
            scaled = self.pixmap.scaled(scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            shown_scale = self.scale_factor
        self.current_display_scale = shown_scale
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.btn_prev.setEnabled(len(self.image_paths) > 1)
        self.btn_next.setEnabled(len(self.image_paths) > 1)
        self.side_prev_button.setEnabled(len(self.image_paths) > 1)
        self.side_next_button.setEnabled(len(self.image_paths) > 1)
        self.info_label.setText(
            f"{self.current_index + 1}/{len(self.image_paths)}  "
            f"{self.pixmap.width()}x{self.pixmap.height()}  "
            f"{int(shown_scale * 100)}%"
        )


class PdfExtractWorker(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, pdf_path, output_folder, page_limit, base_name, dpi=300, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.output_folder = output_folder
        self.page_limit = page_limit
        self.base_name = base_name
        self.dpi = max(72, int(dpi or 300))
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        doc = None
        try:
            try:
                import fitz
            except Exception:
                self.failed.emit("缺少 PyMuPDF 依赖，请先安装 requirements.txt 里的 PyMuPDF。")
                return
            doc = fitz.open(self.pdf_path)
            total_pages = len(doc)
            if total_pages <= 0:
                self.failed.emit("PDF 没有可提取的页面。")
                return
            count = total_pages if self.page_limit is None else min(int(self.page_limit), total_pages)
            os.makedirs(self.output_folder, exist_ok=True)
            saved = []
            for page_index in range(count):
                if self._cancel_requested:
                    self.failed.emit("PDF 提取已取消。")
                    return
                page = doc.load_page(page_index)
                zoom = self.dpi / 72.0
                matrix = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                filename = f"{self.base_name}_第{page_index + 1:02d}页.png"
                dest = self.unique_destination_path(self.output_folder, filename)
                pix.save(dest)
                saved.append(dest)
                self.progress.emit(page_index + 1, count)
                del pix
                del page
                if page_index % 5 == 4:
                    gc.collect()
            doc.close()
            doc = None
            self.finished_ok.emit(saved)
        except MemoryError:
            self.failed.emit("PDF 页面过大，内存不足，提取失败。")
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass
            gc.collect()

    @staticmethod
    def unique_destination_path(folder, filename):
        name, ext = os.path.splitext(filename)
        candidate = os.path.join(folder, filename)
        index = 1
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{name}_{index:02d}{ext}")
            index += 1
        return candidate


class PsdThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, str, float, int, int, bytes)
    finished_batch = pyqtSignal(int)

    def __init__(self, paths, target_size, generation, parent=None):
        super().__init__(parent)
        self.paths = list(paths or [])
        self.target_size = QSize(target_size)
        self.generation = generation
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            from psd_tools import PSDImage
            from PIL import Image
        except Exception:
            self.finished_batch.emit(self.generation)
            return
        max_size = (
            max(32, int(self.target_size.width() or 96)),
            max(32, int(self.target_size.height() or 96)),
        )
        for path in self.paths:
            if self._cancel_requested:
                break
            try:
                abs_path = os.path.abspath(path)
                mtime = os.path.getmtime(abs_path)
                psd = PSDImage.open(abs_path)
                image = psd.composite()
                if image is None:
                    continue
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                if image.mode == "RGBA":
                    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
                    background.alpha_composite(image)
                    image = background.convert("RGB")
                image.thumbnail(max_size, Image.LANCZOS)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=False)
                self.thumbnail_ready.emit(
                    self.generation,
                    abs_path,
                    float(mtime),
                    max_size[0],
                    max_size[1],
                    buffer.getvalue(),
                )
            except Exception:
                continue
            finally:
                gc.collect()
        self.finished_batch.emit(self.generation)


class PdfDropPanel(QWidget):
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if self.dialog.pdf_paths_from_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if self.dialog.pdf_paths_from_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def dropEvent(self, event):
        paths = self.dialog.pdf_paths_from_mime_data(event.mimeData())
        if paths:
            self.dialog.set_pending_pdf(paths[0])
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()


class MaterialPromptLibraryDialog(QDialog):
    def __init__(self, material_dialog, parent=None):
        super().__init__(None)
        self.material_dialog = material_dialog
        self.data = {"categories": []}
        self.current_category_index = -1
        self.current_prompt_index = -1
        self.reference_delete_undo = []
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setWindowTitle("\u901a\u7528\u53c2\u8003")
        self.resize(980, 600)
        self.setAcceptDrops(True)
        self.init_ui()
        self.load_prompts()
        self.refresh_categories()
        self.refresh_reference_images()

    def prompt_store_path(self):
        folder = self.material_dialog.shared_reference_folder()
        if not folder:
            return ""
        return os.path.join(folder, ".shop_material_prompts.json")

    def reference_folder(self):
        return self.material_dialog.shared_reference_folder()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: #6c757d;")
        self.pin_checkbox = QCheckBox("\u7f6e\u9876")
        self.pin_checkbox.toggled.connect(self.toggle_pin)
        top.addWidget(self.path_label, 1)
        top.addWidget(self.pin_checkbox)
        layout.addLayout(top)
        body = QHBoxLayout()
        prompt_panel = QVBoxLayout()
        prompt_panel.addWidget(QLabel("\u63d0\u793a\u8bcd"))
        prompt_body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("\u5206\u7c7b"))
        self.category_list = QListWidget()
        self.category_list.setFixedWidth(90)
        self.category_list.currentRowChanged.connect(self.on_category_changed)
        left.addWidget(self.category_list, 1)
        cat_buttons = QHBoxLayout()
        btn_add_category = QPushButton("\u65b0\u5efa")
        btn_add_category.setFixedWidth(42)
        btn_add_category.setStyleSheet("padding: 0;")
        btn_add_category.clicked.connect(self.add_category)
        btn_delete_category = QPushButton("\u5220\u9664")
        btn_delete_category.setFixedWidth(42)
        btn_delete_category.setStyleSheet("padding: 0;")
        btn_delete_category.clicked.connect(self.delete_category)
        cat_buttons.addWidget(btn_add_category)
        cat_buttons.addWidget(btn_delete_category)
        left.addLayout(cat_buttons)
        prompt_body.addLayout(left)
        middle = QVBoxLayout()
        middle.addWidget(QLabel("\u63d0\u793a\u8bcd"))
        self.prompt_list = QListWidget()
        self.prompt_list.setWordWrap(True)
        self.prompt_list.setTextElideMode(Qt.ElideNone)
        self.prompt_list.currentRowChanged.connect(self.on_prompt_changed)
        middle.addWidget(self.prompt_list, 1)
        prompt_buttons = QHBoxLayout()
        btn_add_prompt = QPushButton("\u65b0\u5efa")
        btn_add_prompt.clicked.connect(self.add_prompt)
        btn_delete_prompt = QPushButton("\u5220\u9664")
        btn_delete_prompt.clicked.connect(self.delete_prompt)
        prompt_buttons.addWidget(btn_add_prompt)
        prompt_buttons.addWidget(btn_delete_prompt)
        middle.addLayout(prompt_buttons)
        prompt_body.addLayout(middle, 3)
        right = QVBoxLayout()
        right.addWidget(QLabel("\u6807\u9898"))
        self.title_input = QLineEdit()
        right.addWidget(self.title_input)
        right.addWidget(QLabel("\u63d0\u793a\u8bcd\u5185\u5bb9"))
        self.content_edit = QTextEdit()
        self.content_edit.setAcceptRichText(False)
        right.addWidget(self.content_edit, 1)
        editor_buttons = QHBoxLayout()
        btn_copy = QPushButton("\u590d\u5236\u63d0\u793a\u8bcd")
        btn_copy.clicked.connect(self.copy_prompt)
        btn_save = QPushButton("\u4fdd\u5b58")
        btn_save.clicked.connect(self.save_prompt)
        editor_buttons.addWidget(btn_copy)
        editor_buttons.addStretch()
        editor_buttons.addWidget(btn_save)
        right.addLayout(editor_buttons)
        prompt_body.addLayout(right, 3)
        prompt_panel.addLayout(prompt_body, 1)
        body.addLayout(prompt_panel, 3)
        ref_panel = QVBoxLayout()
        ref_panel.setContentsMargins(1, 1, 1, 1)
        ref_panel.setSpacing(1)
        ref_panel.addWidget(QLabel("\u901a\u7528\u53c2\u8003\u56fe"))
        self.reference_list = MaterialImageList(self, compact=True)
        self.reference_list._fixed_columns = 4
        self.reference_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.reference_list.itemDoubleClicked.connect(self.open_reference_image)
        self.reference_list.itemChanged.connect(self.handle_reference_item_changed)
        undo_shortcut = QShortcut(QKeySequence.Undo, self.reference_list)
        undo_shortcut.activated.connect(self.undo_delete_reference_images)
        ref_panel.addWidget(self.reference_list, 1)
        ref_buttons = QHBoxLayout()
        btn_ref_import = QPushButton("\u5bfc\u5165\u56fe\u7247")
        btn_ref_import.clicked.connect(self.import_reference_images)
        btn_ref_copy = QPushButton("\u590d\u5236")
        btn_ref_copy.clicked.connect(self.copy_reference_images)
        self.reference_psd_checkbox = QCheckBox("\u663e\u793a PSD")
        self.reference_psd_checkbox.setChecked(self.material_dialog.settings.value("show_reference_psd", False, type=bool))
        self.reference_psd_checkbox.toggled.connect(self.set_reference_psd_visible)
        btn_ref_open = QPushButton("\u6253\u5f00\u6587\u4ef6\u5939")
        btn_ref_open.clicked.connect(self.open_reference_folder)
        ref_buttons.addWidget(btn_ref_import)
        ref_buttons.addWidget(btn_ref_copy)
        ref_buttons.addWidget(self.reference_psd_checkbox)
        ref_buttons.addStretch()
        ref_buttons.addWidget(btn_ref_open)
        ref_panel.addLayout(ref_buttons)
        hint = QLabel("\u53ef\u62d6\u62fd/\u7c98\u8d34\u56fe\u7247\u5230\u8fd9\u91cc\uff0c\u9002\u5408\u4fdd\u5b58\u901a\u7528\u59ff\u52bf\u53c2\u8003\u3001\u516c\u5171 Logo \u7b49\u3002")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6c757d;")
        ref_panel.addWidget(hint)
        body.addLayout(ref_panel, 2)
        layout.addLayout(body, 1)

    def set_reference_psd_visible(self, checked):
        self.material_dialog.settings.setValue("show_reference_psd", checked)
        self.material_dialog.settings.sync()
        self.refresh_reference_images()

    def toggle_pin(self, checked):
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.raise_()

    def load_prompts(self):
        path = self.prompt_store_path()
        self.path_label.setText(path or "请先设置素材库母文件夹")
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and isinstance(data.get("categories"), list):
                    self.data = data
            except Exception:
                self.data = {"categories": []}
        if not self.data.get("categories"):
            self.data["categories"] = [{"name": "参考", "prompts": []}]

    def save_data(self):
        path = self.prompt_store_path()
        if not path:
            QMessageBox.information(self, "提示", "请先设置素材库母文件夹。")
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temp_path = path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
            self.path_label.setText(path)
            return True
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存提示词失败：\n{e}")
            return False

    def refresh_categories(self):
        current = max(0, self.current_category_index)
        self.category_list.blockSignals(True)
        self.category_list.clear()
        for category in self.data.get("categories", []):
            self.category_list.addItem(str(category.get("name", "") or "未分类"))
        self.category_list.blockSignals(False)
        if self.category_list.count():
            self.category_list.setCurrentRow(min(current, self.category_list.count() - 1))

    def refresh_prompts(self):
        category = self.current_category()
        prompts = category.get("prompts", []) if category else []
        current = max(0, self.current_prompt_index)
        self.prompt_list.blockSignals(True)
        self.prompt_list.clear()
        for prompt in prompts:
            self.prompt_list.addItem(str(prompt.get("title", "") or "未命名提示词"))
        self.prompt_list.blockSignals(False)
        if self.prompt_list.count():
            self.prompt_list.setCurrentRow(min(current, self.prompt_list.count() - 1))
        else:
            self.current_prompt_index = -1
            self.title_input.clear()
            self.content_edit.clear()

    def current_category(self):
        categories = self.data.get("categories", [])
        if 0 <= self.current_category_index < len(categories):
            return categories[self.current_category_index]
        return None

    def current_prompt(self):
        category = self.current_category()
        prompts = category.get("prompts", []) if category else []
        if 0 <= self.current_prompt_index < len(prompts):
            return prompts[self.current_prompt_index]
        return None

    def on_category_changed(self, row):
        self.current_category_index = row
        self.current_prompt_index = -1
        self.refresh_prompts()

    def on_prompt_changed(self, row):
        self.current_prompt_index = row
        prompt = self.current_prompt()
        if not prompt:
            self.title_input.clear()
            self.content_edit.clear()
            return
        self.title_input.setText(str(prompt.get("title", "")))
        self.content_edit.setPlainText(str(prompt.get("content", "")))

    def add_category(self):
        name, ok = QInputDialog.getText(self, "新建分类", "分类名称：")
        name = name.strip() if ok else ""
        if not name:
            return
        self.data.setdefault("categories", []).append({"name": name, "prompts": []})
        self.current_category_index = len(self.data["categories"]) - 1
        self.save_data()
        self.refresh_categories()

    def delete_category(self):
        categories = self.data.get("categories", [])
        if not (0 <= self.current_category_index < len(categories)):
            return
        if QMessageBox.question(self, "确认", "确定删除这个分类吗？") != QMessageBox.Yes:
            return
        categories.pop(self.current_category_index)
        if not categories:
            categories.append({"name": "参考", "prompts": []})
        self.current_category_index = max(0, min(self.current_category_index, len(categories) - 1))
        self.save_data()
        self.refresh_categories()

    def add_prompt(self):
        category = self.current_category()
        if not category:
            self.data.setdefault("categories", []).append({"name": "参考", "prompts": []})
            self.current_category_index = 0
            category = self.current_category()
        category.setdefault("prompts", []).append({"title": "未命名提示词", "content": ""})
        self.current_prompt_index = len(category["prompts"]) - 1
        self.save_data()
        self.refresh_prompts()

    def save_prompt(self):
        category = self.current_category()
        if not category:
            return
        prompts = category.setdefault("prompts", [])
        if not (0 <= self.current_prompt_index < len(prompts)):
            prompts.append({"title": "", "content": ""})
            self.current_prompt_index = len(prompts) - 1
        title = self.title_input.text().strip() or "未命名提示词"
        content = self.content_edit.toPlainText().strip()
        prompts[self.current_prompt_index] = {"title": title, "content": content}
        if self.save_data():
            self.refresh_prompts()

    def delete_prompt(self):
        category = self.current_category()
        prompts = category.get("prompts", []) if category else []
        if not (0 <= self.current_prompt_index < len(prompts)):
            return
        prompts.pop(self.current_prompt_index)
        self.current_prompt_index = max(-1, min(self.current_prompt_index, len(prompts) - 1))
        self.save_data()
        self.refresh_prompts()

    def copy_prompt(self):
        content = self.content_edit.toPlainText().strip()
        if not content:
            return
        QApplication.clipboard().setText(content)

    def reference_image_paths(self):
        folder = self.reference_folder()
        if not folder or not os.path.isdir(folder):
            return []
        return self.material_dialog.sorted_image_files(folder, show_psd=self.reference_psd_checkbox.isChecked())

    def refresh_reference_images(self):
        self.reference_list.clear()
        images = [(path, os.path.basename(path)) for path in self.reference_image_paths()]
        self.material_dialog.add_image_items(images, image_list=self.reference_list, empty_text="暂无通用参考图")

    def reference_selected_paths(self):
        paths = []
        for item in self.reference_list.selectedItems():
            path = self.material_dialog.image_path_from_item(item)
            if path and path not in paths:
                paths.append(path)
        if not paths:
            current = self.reference_list.currentItem()
            path = self.material_dialog.image_path_from_item(current)
            if path:
                paths.append(path)
        return paths

    def import_reference_images(self):
        folder = self.reference_folder()
        if not folder:
            QMessageBox.information(self, "提示", "请先设置素材库母文件夹。")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择通用参考图",
            os.path.expanduser("~"),
            "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.psd)",
        )
        if paths:
            self.import_reference_paths(paths)

    def import_reference_paths(self, paths):
        folder = self.reference_folder()
        if not folder:
            return False
        os.makedirs(folder, exist_ok=True)
        copied = 0
        import_time = time.time()
        for path in paths or []:
            path = os.path.abspath(path)
            for image_path in self.material_dialog.iter_image_paths(path, show_psd=self.reference_psd_checkbox.isChecked()):
                dest = self.material_dialog.unique_destination_path(folder, os.path.basename(image_path))
                if os.path.abspath(image_path) == os.path.abspath(dest):
                    continue
                try:
                    shutil.copy2(image_path, dest)
                    os.utime(dest, (import_time - copied * 0.001, import_time - copied * 0.001))
                    copied += 1
                except Exception as e:
                    QMessageBox.warning(self, "导入失败", f"导入参考图失败：\n{e}")
                    break
        if copied:
            self.refresh_reference_images()
        return copied > 0

    def import_reference_image_data(self, image_data):
        folder = self.reference_folder()
        if not folder:
            return False
        if image_data is None or not hasattr(image_data, "save") or image_data.isNull():
            return False
        os.makedirs(folder, exist_ok=True)
        filename = f"粘贴图片_{time.strftime('%Y%m%d_%H%M%S')}.png"
        dest = self.material_dialog.unique_destination_path(folder, filename)
        if not image_data.save(dest, "PNG"):
            QMessageBox.warning(self, "导入失败", "剪贴板图片保存失败。")
            return False
        self.refresh_reference_images()
        return True

    def reference_paths_from_mime_data(self, mime_data):
        paths = []
        if mime_data.hasUrls():
            paths.extend(url.toLocalFile() for url in mime_data.urls() if url.isLocalFile())
        if mime_data.hasText():
            paths.extend(self.material_dialog.paths_from_text(mime_data.text()))
        result = []
        for path in paths:
            path = os.path.abspath(path)
            if path and os.path.exists(path) and path not in result:
                result.append(path)
        return result

    def can_import_mime_data(self, mime_data):
        if mime_data.hasImage():
            return True
        return bool(self.reference_paths_from_mime_data(mime_data))

    def import_from_mime_data(self, mime_data):
        paths = self.reference_paths_from_mime_data(mime_data)
        if paths:
            return self.import_reference_paths(paths)
        if mime_data.hasImage():
            image = mime_data.imageData()
            if isinstance(image, QPixmap):
                image = image.toImage()
            return self.import_reference_image_data(image)
        return False

    def paste_images_from_clipboard(self, source_list=None):
        if not self.import_from_mime_data(QApplication.clipboard().mimeData()):
            QMessageBox.information(self, "提示", "剪贴板里没有可导入的图片或本地图片文件。")

    def copy_reference_images(self, cut=False):
        paths = self.reference_selected_paths()
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        mime.setText("\n".join(paths))
        mime.setData("Preferred DropEffect", (2 if cut else 5).to_bytes(4, "little"))
        QApplication.clipboard().setMimeData(mime)

    def delete_reference_images(self):
        paths = self.reference_selected_paths()
        if not paths:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除选中的 {len(paths)} 张通用参考图吗？\n此操作可按 Ctrl+Z 撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        undo_folder = os.path.join(self.reference_folder(), ".shop_material_undo")
        os.makedirs(undo_folder, exist_ok=True)
        failed = []
        moved = []
        for path in paths:
            try:
                backup = self.material_dialog.unique_destination_path(undo_folder, os.path.basename(path))
                shutil.move(path, backup)
                moved.append((backup, path))
            except Exception as e:
                failed.append(f"{path}\n{e}")
        if moved:
            self.reference_delete_undo.append(moved)
        self.refresh_reference_images()
        if failed:
            QMessageBox.warning(self, "部分删除失败", "\n\n".join(failed[:5]))

    def delete_images(self, source_list=None):
        self.delete_reference_images()

    def undo_delete_reference_images(self):
        if not self.reference_delete_undo:
            return
        failed = []
        for backup, original in self.reference_delete_undo.pop():
            try:
                destination = original
                if os.path.exists(destination):
                    destination = self.material_dialog.unique_destination_path(
                        os.path.dirname(original), os.path.basename(original)
                    )
                shutil.move(backup, destination)
            except Exception as e:
                failed.append(f"{original}\n{e}")
        self.refresh_reference_images()
        if failed:
            QMessageBox.warning(self, "部分撤销失败", "\n\n".join(failed[:5]))

    def open_reference_folder(self):
        folder = self.reference_folder()
        if not folder:
            QMessageBox.information(self, "提示", "请先设置素材库母文件夹。")
            return
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
    def open_reference_image(self, item):
        path = self.material_dialog.image_path_from_item(item)
        if not path:
            return
        if self.material_dialog.is_psd_file(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        dialog = MaterialImageViewerDialog(path, self, self.reference_image_paths())
        dialog.exec_()

    def open_image_viewer(self, item):
        self.open_reference_image(item)

    def handle_reference_item_changed(self, item):
        path = self.material_dialog.image_path_from_item(item)
        if not path:
            return
        original_text = item.data(MaterialImageList.ORIGINAL_TEXT_ROLE) or ""
        new_text = str(item.text() or "").strip()
        if not new_text or new_text == original_text:
            return
        folder = os.path.dirname(path)
        old_ext = os.path.splitext(path)[1] or ".png"
        stem, typed_ext = os.path.splitext(new_text)
        if typed_ext.lower() in self.material_dialog.IMAGE_EXTENSIONS:
            new_filename = self.material_dialog.safe_folder_name(stem, "素材") + typed_ext
        else:
            new_filename = self.material_dialog.safe_folder_name(new_text, "素材") + old_ext
        new_path = os.path.join(folder, new_filename)
        if os.path.abspath(new_path) == os.path.abspath(path):
            return
        if os.path.exists(new_path):
            new_path = self.material_dialog.unique_destination_path(folder, new_filename)
        try:
            os.rename(path, new_path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"导入参考图失败：\n{e}")
            self.reference_list.blockSignals(True)
            item.setText(original_text)
            self.reference_list.blockSignals(False)
            return
        self.refresh_reference_images()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            if self.import_from_mime_data(QApplication.clipboard().mimeData()):
                return
        if event.matches(QKeySequence.Copy):
            if self.reference_list.hasFocus():
                self.copy_reference_images()
                return
        if event.matches(QKeySequence.Cut):
            if self.reference_list.hasFocus():
                self.copy_reference_images(cut=True)
                return
        if event.key() == Qt.Key_Delete and self.reference_list.hasFocus():
            self.delete_reference_images()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if self.can_import_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.can_import_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self.import_from_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        super().dropEvent(event)


class MaterialLibraryDialog(QDialog):
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".psd"}
    PSD_EXTENSION = ".psd"
    PRODUCT_MODE = "product"
    LINK_MODE = "link"
    LINK_UNGROUPED = "未分组"
    LINK_NO_TYPE = "无链接类型"
    LINK_DELETED_SUFFIX = "（已删除）"
    BULK_IMPORT_CONFIRM_THRESHOLD = 30
    BULK_MOVE_CONFIRM_THRESHOLD = 30
    IMPORT_SCAN_LIMIT = 5000
    LARGE_IMAGE_DISPLAY_THRESHOLD = 300

    def __init__(self, db_manager, parent=None):
        super().__init__(None)
        self.main_app = parent
        self.db = db_manager
        self.settings = QSettings("ShopManager", "MaterialLibrary")
        self.categories = []
        self.specs = []
        self.library_mode = self.PRODUCT_MODE
        self.product_state = {}
        self.link_state = {}
        self.local_root_folders = {}
        self.local_spec_folder_mappings = {}
        self.local_link_folder_paths = {}
        self.local_category_folder_paths = {}
        self.product_image_order_overrides = {}
        self.current_category = None
        self.current_spec = None
        self.selected_category_labels = set()
        self.selected_spec_names = set()
        self.category_buttons = {}
        self.spec_buttons = {}
        self.link_items = []
        self.link_combos = []
        self.link_types = []
        self.link_products = []
        self.selected_link_combo = ""
        self.selected_link_type = ""
        self.selected_link_product_ids = set()
        self.link_product_buttons = {}
        self.link_store_filter_id = None
        self.active_link_image_column = "main"
        self.link_image_lists = {}
        self.link_image_column_overrides = {}
        self.image_thumbnail_cache = {}
        self.psd_thumbnail_cache = {}
        self.psd_thumbnail_worker = None
        self.psd_thumbnail_generation = 0
        self.thumbnail_load_generation = 0
        self.pending_thumbnail_items = []
        self.thumbnail_load_timer = QTimer(self)
        self.thumbnail_load_timer.setInterval(1)
        self.thumbnail_load_timer.timeout.connect(self.process_pending_thumbnail_items)
        self.large_image_display_confirmed = set()
        self.link_image_load_generation = 0
        self.mode_image_load_generation = 0
        self._chip_animations = {}
        self._chip_press_button = None
        self._chip_press_pos = QPoint()
        self._chip_press_time = 0
        self._chip_dragging_order = False
        self._active_drop_hover_chip = None
        self._active_order_hover_chip = None
        self._category_sync_queue = []
        self._category_sync_running = False
        self._spec_sync_queue = []
        self._spec_sync_running = False
        self._settings_keys_cache = None
        self._tab_mode_switching = False
        self._last_tab_switch_time = 0
        self.pending_pdf_path = ""
        self.pdf_worker = None
        self.prompt_library_dialog = None
        self.mode_toast = None
        self.mode_toast_generation = 0
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        QApplication.instance().installEventFilter(self)
        apply_window_icon(self, "material")
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setWindowTitle("\u7d20\u6750\u5e93")
        self.resize(1180, 760)
        self.init_ui()
        self.install_tab_shortcuts()
        self.load_categories()
        self.refresh_root_label()
        self.activate_keyboard_shortcuts()

    def activate_keyboard_shortcuts(self):
        self.setFocus(Qt.ActiveWindowFocusReason)
        QTimer.singleShot(0, lambda: self.setFocus(Qt.ActiveWindowFocusReason))

    def install_tab_shortcuts(self):
        self.tab_shortcut = QShortcut(QKeySequence(Qt.Key_Tab), self)
        self.tab_shortcut.setContext(Qt.WindowShortcut)
        self.tab_shortcut.activated.connect(self.handle_tab_mode_switch)
        self.backtab_shortcut = QShortcut(QKeySequence(Qt.Key_Backtab), self)
        self.backtab_shortcut.setContext(Qt.WindowShortcut)
        self.backtab_shortcut.activated.connect(self.handle_tab_mode_switch)
        self.search_shortcut = QShortcut(QKeySequence.Find, self)
        self.search_shortcut.setContext(Qt.WindowShortcut)
        self.search_shortcut.activated.connect(self.focus_search_input)

    def focus_search_input(self):
        if hasattr(self, "search_input"):
            self.search_input.setFocus(Qt.ShortcutFocusReason)
            self.search_input.selectAll()

    def remove_tab_focus(self, widget):
        widget.setFocusPolicy(Qt.NoFocus)
        return widget

    def showEvent(self, event):
        super().showEvent(event)
        self.activate_keyboard_shortcuts()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("\u7d20\u6750\u5e93")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: #6c757d;")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_copy_link_folder_path = QPushButton("\u590d\u5236\u6587\u4ef6\u5939\u8def\u5f84")
        self.remove_tab_focus(self.btn_copy_link_folder_path)
        self.btn_copy_link_folder_path.clicked.connect(self.copy_current_folder_path)
        self.mode_button = QPushButton("\u4ea7\u54c1\u7d20\u6750\u5e93")
        self.remove_tab_focus(self.mode_button)
        self.mode_button.setCheckable(True)
        self.mode_button.clicked.connect(self.toggle_library_mode)
        self.btn_fetch_link_material = QPushButton("抓取素材")
        self.remove_tab_focus(self.btn_fetch_link_material)
        self.btn_fetch_link_material.clicked.connect(self.open_selected_link_for_material_fetch)
        self.btn_fetch_link_material.setVisible(False)
        self.btn_prompts = QPushButton("\u901a\u7528\u53c2\u8003")
        self.remove_tab_focus(self.btn_prompts)
        self.btn_prompts.clicked.connect(self.show_prompt_library)
        btn_open = QPushButton("\u6253\u5f00\u6587\u4ef6\u5939")
        self.remove_tab_focus(btn_open)
        btn_open.clicked.connect(self.open_current_folder)
        btn_refresh = QPushButton("\u5237\u65b0")
        self.remove_tab_focus(btn_refresh)
        btn_refresh.clicked.connect(self.refresh_current_view)
        self.btn_settings = QToolButton()
        self.remove_tab_focus(self.btn_settings)
        self.btn_settings.setText("\u8bbe\u7f6e")
        self.btn_settings.setPopupMode(QToolButton.InstantPopup)
        settings_menu = QMenu(self.btn_settings)
        settings_menu.addAction("\u8bbe\u7f6e\u4ea7\u54c1\u7d20\u6750\u5e93\u6587\u4ef6\u5939", lambda: self.choose_root_folder(self.PRODUCT_MODE))
        settings_menu.addAction("\u8bbe\u7f6e\u94fe\u63a5\u7d20\u6750\u5e93\u6587\u4ef6\u5939", lambda: self.choose_root_folder(self.LINK_MODE))
        self.btn_settings.setMenu(settings_menu)
        top.addWidget(title)
        top.addWidget(self.path_label, 1)
        top.addWidget(self.btn_copy_link_folder_path)
        top.addWidget(self.mode_button)
        top.addWidget(self.btn_fetch_link_material)
        top.addWidget(self.btn_prompts)
        top.addWidget(btn_open)
        top.addWidget(btn_refresh)
        top.addWidget(self.btn_settings)
        layout.addLayout(top)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("\u641c\u7d22:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索类型、规格、编码或链接；支持拼音/首字母，空格分隔多个关键词")
        self.search_input.textChanged.connect(self.on_search_changed)
        search_row.addWidget(self.search_input, 1)
        self.store_filter_combo = QComboBox()
        self.remove_tab_focus(self.store_filter_combo)
        self.store_filter_combo.setMinimumWidth(160)
        self.store_filter_combo.currentIndexChanged.connect(self.on_store_filter_changed)
        self.show_inactive_links_checkbox = QCheckBox("\u663e\u793a\u5df2\u4e0b\u67b6\u548c\u5220\u9664")
        self.remove_tab_focus(self.show_inactive_links_checkbox)
        self.show_inactive_links_checkbox.stateChanged.connect(self.on_link_visibility_changed)
        self.link_sort_button = QPushButton()
        self.remove_tab_focus(self.link_sort_button)
        self.link_sort_button.setCheckable(True)
        self.link_sort_button.setChecked(self.settings.value("link_image_sort_descending", False, type=bool))
        self.link_sort_button.toggled.connect(self.on_link_sort_changed)
        self.update_link_sort_button_text()
        self.show_psd_files_checkbox = QCheckBox("\u663e\u793a PSD")
        self.remove_tab_focus(self.show_psd_files_checkbox)
        self.show_psd_files_checkbox.setChecked(self.settings.value("show_psd_files", False, type=bool))
        self.show_psd_files_checkbox.stateChanged.connect(self.on_psd_visibility_changed)
        self.store_filter_combo.setVisible(False)
        self.show_inactive_links_checkbox.setVisible(False)
        self.link_sort_button.setVisible(False)
        search_row.addWidget(self.store_filter_combo)
        search_row.addWidget(self.show_inactive_links_checkbox)
        search_row.addWidget(self.link_sort_button)
        search_row.addWidget(self.show_psd_files_checkbox)
        layout.addLayout(search_row)
        nav_row = QHBoxLayout()
        self.back_button = QPushButton("\u8fd4\u56de\u7c7b\u578b")
        self.remove_tab_focus(self.back_button)
        self.back_button.clicked.connect(self.back_to_categories)
        self.back_button.setEnabled(False)
        self.current_label = QLabel("\u5546\u54c1\u7c7b\u578b")
        self.current_label.setStyleSheet("font-weight: bold; color: #34495e;")
        nav_row.addWidget(self.back_button)
        nav_row.addWidget(self.current_label)
        nav_row.addStretch()
        layout.addLayout(nav_row)
        bubble_row = QHBoxLayout()
        bubble_left = QWidget()
        bubble_left_layout = QVBoxLayout(bubble_left)
        bubble_left_layout.setContentsMargins(0, 0, 0, 0)
        bubble_left_layout.setSpacing(0)
        self.category_scroll, self.category_content, self.category_layout = self._make_chip_scroll()
        self.spec_scroll, self.spec_content, self.spec_layout = self._make_chip_scroll()
        self.link_product_scroll, self.link_product_content, self.link_product_layout = self._make_chip_scroll()
        self.spec_scroll.setVisible(False)
        self.link_product_scroll.setVisible(False)
        bubble_left_layout.addWidget(self.category_scroll)
        bubble_left_layout.addWidget(self.spec_scroll)
        bubble_left_layout.addWidget(self.link_product_scroll)
        bubble_row.addWidget(bubble_left, 1)
        self.pdf_import_panel = self.create_pdf_import_panel()
        bubble_row.addWidget(self.pdf_import_panel)
        layout.addLayout(bubble_row)
        self.image_count_label = QLabel("\u8bf7\u9009\u62e9\u5546\u54c1\u7c7b\u578b")
        self.image_count_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addWidget(self.image_count_label)
        self.image_list = MaterialImageList(self)
        self.image_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.image_list.customContextMenuRequested.connect(self.show_image_context_menu)
        self.image_list.itemChanged.connect(self.handle_image_item_changed)
        content_row = QHBoxLayout()
        self.image_area = QWidget()
        image_area_layout = QVBoxLayout(self.image_area)
        image_area_layout.setContentsMargins(0, 0, 0, 0)
        image_area_layout.setSpacing(4)
        image_area_layout.addWidget(self.image_list, 1)
        self.link_image_panel = self.create_link_image_panel()
        self.link_image_panel.setVisible(False)
        image_area_layout.addWidget(self.link_image_panel, 1)
        content_row.addWidget(self.image_area, 1)
        attr_panel = QWidget()
        attr_panel.setFixedWidth(280)
        attr_layout = QVBoxLayout(attr_panel)
        attr_layout.setContentsMargins(8, 0, 0, 0)
        attr_title = QLabel("\u5f53\u524d\u89c4\u683c\u4ea7\u54c1\u5c5e\u6027")
        attr_title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.attribute_text = QTextEdit()
        self.attribute_text.setReadOnly(True)
        self.attribute_text.setAcceptRichText(False)
        self.attribute_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.attribute_text.setStyleSheet("QTextEdit { border: 1px solid #d9dee5; border-radius: 6px; padding: 8px; background: #fbfcfd; color: #2c3e50; }")
        attr_layout.addWidget(attr_title)
        attr_layout.addWidget(self.attribute_text, 1)
        content_row.addWidget(attr_panel)
        layout.addLayout(content_row, 1)

    def _make_chip_scroll(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(218)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        chip_layout = FlowLayout(content, margin=2, spacing=8)
        scroll.setWidget(content)
        return scroll, content, chip_layout

    def create_pdf_import_panel(self):
        panel = PdfDropPanel(self)
        panel.setFixedWidth(260)
        panel.setStyleSheet("QWidget { background: #fbfcfd; border: 1px dashed #9fb3c8; border-radius: 6px; } QLabel, QComboBox, QPushButton, QProgressBar { border: none; background: transparent; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        title = QLabel("PDF \u63d0\u53d6")
        title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.pdf_hint_label = QLabel("\u62d6\u62fd/\u7c98\u8d34 PDF \u5230\u8fd9\u91cc")
        self.pdf_hint_label.setWordWrap(True)
        self.pdf_hint_label.setStyleSheet("color: #6c757d;")
        self.pdf_file_label = QLabel("\u672a\u9009\u62e9 PDF")
        self.pdf_file_label.setWordWrap(True)
        self.pdf_file_label.setStyleSheet("color: #34495e;")
        self.pdf_page_combo = QComboBox()
        self.remove_tab_focus(self.pdf_page_combo)
        for label, value in (("1\u5f20", 1), ("3\u5f20", 3), ("5\u5f20", 5), ("10\u5f20", 10), ("\u5168\u90e8", None)):
            self.pdf_page_combo.addItem(label, value)
        self.pdf_dpi_combo = QComboBox()
        self.remove_tab_focus(self.pdf_dpi_combo)
        self.pdf_dpi_combo.addItem("300 DPI\uff08\u9ed8\u8ba4\uff09", 300)
        self.pdf_dpi_combo.addItem("600 DPI\uff08\u9ad8\u6e05\uff09", 600)
        self.pdf_extract_button = QPushButton("\u63d0\u53d6")
        self.remove_tab_focus(self.pdf_extract_button)
        self.pdf_extract_button.clicked.connect(self.extract_pending_pdf)
        self.pdf_progress = QProgressBar()
        self.pdf_progress.setRange(0, 100)
        self.pdf_progress.setValue(0)
        self.pdf_progress.setTextVisible(True)
        self.pdf_status_label = QLabel("\u7b49\u5f85 PDF")
        self.pdf_status_label.setWordWrap(True)
        self.pdf_status_label.setStyleSheet("color: #6c757d;")
        layout.addWidget(title)
        layout.addWidget(self.pdf_hint_label)
        layout.addWidget(self.pdf_file_label)
        layout.addWidget(self.pdf_page_combo)
        layout.addWidget(self.pdf_dpi_combo)
        layout.addWidget(self.pdf_extract_button)
        layout.addWidget(self.pdf_progress)
        layout.addWidget(self.pdf_status_label)
        layout.addStretch()
        return panel

    def create_link_image_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)
        self.link_image_lists = {}
        for key, title in (("main", "主图"), ("detail", "详情页"), ("sku", "SKU")):
            top_row.addWidget(self.create_link_image_column(key, title), 1)
        layout.addLayout(top_row, 1)
        return panel

    def create_link_image_column(self, key, title):
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            "QLabel { font-weight: bold; color: #2c3e50; background: #f3f6f9; border: 1px solid #111111; padding: 3px; }"
        )
        image_list = MaterialImageList(self, column_key=key, compact=True)
        image_list.setContextMenuPolicy(Qt.CustomContextMenu)
        image_list.customContextMenuRequested.connect(self.show_image_context_menu)
        image_list.itemChanged.connect(self.handle_image_item_changed)
        self.link_image_lists[key] = image_list
        layout.addWidget(label)
        layout.addWidget(image_list, 1)
        return column

    def settings_key(self, mode=None):
        mode = mode or self.library_mode
        parent = getattr(self, "main_app", None)
        account_id = ""
        try:
            if parent and getattr(parent, "archive_manager", None):
                active = parent.archive_manager.get_active_data_account()
                if active:
                    account_id = str(active.get("id") or "")
        except Exception:
            account_id = ""
        if account_id:
            return f"{mode}_root_folder/account/{account_id}"
        db_path = getattr(self.db, "db_path", "") or ""
        digest = hashlib.md5(os.path.abspath(db_path).encode("utf-8")).hexdigest()
        return f"{mode}_root_folder/db/{digest}"

    def root_folder(self):
        return self.root_folder_for_mode(self.library_mode)

    def root_folder_for_mode(self, mode):
        key = self.settings_key(mode)
        value = str(self.settings.value(key, "") or "").strip()
        if not value:
            value = str(self.local_root_folders.get(key, "") or "").strip()
        if not value and mode == self.PRODUCT_MODE:
            legacy_key = self.settings_key(mode).replace(f"{self.PRODUCT_MODE}_root_folder", "root_folder")
            value = str(self.settings.value(legacy_key, "") or "").strip()
        return value

    def set_root_folder(self, folder, mode=None):
        key = self.settings_key(mode or self.library_mode)
        value = os.path.abspath(folder)
        self.local_root_folders[key] = value
        self.settings.setValue(key, value)
        self.settings.sync()

    def shared_reference_base_folder(self):
        product_root = self.root_folder_for_mode(self.PRODUCT_MODE)
        link_root = self.root_folder_for_mode(self.LINK_MODE)
        return product_root or link_root or self.root_folder()

    def shared_reference_folder(self):
        base = self.shared_reference_base_folder()
        if not base:
            return ""
        folder = os.path.join(base, "\u901a\u7528\u53c2\u8003\u7d20\u6750")
        if not getattr(self, "_shared_reference_migrated", False):
            self.migrate_shared_reference_storage(folder)
            self._shared_reference_migrated = True
        return folder

    def legacy_reference_roots(self):
        roots = []
        for mode in (self.PRODUCT_MODE, self.LINK_MODE):
            root = self.root_folder_for_mode(mode)
            if root and root not in roots:
                roots.append(root)
        current = self.root_folder()
        if current and current not in roots:
            roots.append(current)
        return roots

    def merge_prompt_data(self, base_data, incoming_data):
        if not isinstance(base_data, dict):
            base_data = {"categories": []}
        if not isinstance(incoming_data, dict):
            return base_data
        categories = base_data.setdefault("categories", [])
        by_name = {str(cat.get("name", "") or "\u53c2\u8003"): cat for cat in categories if isinstance(cat, dict)}
        seen = set()
        for cat in categories:
            for prompt in cat.get("prompts", []) or []:
                if isinstance(prompt, dict):
                    seen.add((str(prompt.get("title", "")), str(prompt.get("content", ""))))
        for incoming_cat in incoming_data.get("categories", []) or []:
            if not isinstance(incoming_cat, dict):
                continue
            name = str(incoming_cat.get("name", "") or "\u53c2\u8003")
            target_cat = by_name.get(name)
            if target_cat is None:
                target_cat = {"name": name, "prompts": []}
                categories.append(target_cat)
                by_name[name] = target_cat
            prompts = target_cat.setdefault("prompts", [])
            for prompt in incoming_cat.get("prompts", []) or []:
                if not isinstance(prompt, dict):
                    continue
                key = (str(prompt.get("title", "")), str(prompt.get("content", "")))
                if key in seen:
                    continue
                prompts.append(prompt)
                seen.add(key)
        return base_data

    def migrate_shared_reference_storage(self, target_folder):
        if not target_folder:
            return
        if getattr(self, "_shared_reference_migrating", False):
            return
        self._shared_reference_migrating = True
        try:
            os.makedirs(target_folder, exist_ok=True)
            target_prompt = os.path.join(target_folder, ".shop_material_prompts.json")
            prompt_data = {"categories": []}
            if os.path.isfile(target_prompt):
                try:
                    with open(target_prompt, "r", encoding="utf-8") as fh:
                        prompt_data = json.load(fh)
                except Exception:
                    prompt_data = {"categories": []}
            for root in self.legacy_reference_roots():
                legacy_folders = [
                    os.path.join(root, ".shop_material_references"),
                    os.path.join(root, "\u901a\u7528\u53c2\u8003\u7d20\u6750"),
                ]
                for legacy_folder in legacy_folders:
                    if not os.path.isdir(legacy_folder) or os.path.abspath(legacy_folder) == os.path.abspath(target_folder):
                        continue
                    legacy_prompt = os.path.join(legacy_folder, ".shop_material_prompts.json")
                    if os.path.isfile(legacy_prompt) and os.path.abspath(legacy_prompt) != os.path.abspath(target_prompt):
                        try:
                            with open(legacy_prompt, "r", encoding="utf-8") as fh:
                                prompt_data = self.merge_prompt_data(prompt_data, json.load(fh))
                        except Exception:
                            pass
                    for image_path in self.iter_image_paths(legacy_folder):
                        if os.path.exists(os.path.join(target_folder, os.path.basename(image_path))):
                            continue
                        dest = self.unique_destination_path(target_folder, os.path.basename(image_path))
                        if os.path.abspath(image_path) == os.path.abspath(dest):
                            continue
                        try:
                            shutil.copy2(image_path, dest)
                        except Exception:
                            pass
            if prompt_data.get("categories"):
                with open(target_prompt, "w", encoding="utf-8") as fh:
                    json.dump(prompt_data, fh, ensure_ascii=False, indent=2)
        finally:
            self._shared_reference_migrating = False

    def normalized_abs_path(self, path):
        try:
            return os.path.normcase(os.path.abspath(path))
        except Exception:
            return ""

    def path_is_same_or_child(self, child, parent):
        child_abs = self.normalized_abs_path(child)
        parent_abs = self.normalized_abs_path(parent)
        if not child_abs or not parent_abs:
            return False
        try:
            common = os.path.commonpath([child_abs, parent_abs])
        except ValueError:
            return False
        return common == parent_abs

    def root_relative_parts(self, path):
        root = self.root_folder()
        if not root:
            return []
        try:
            rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
        except ValueError:
            return []
        if rel in ("", ".") or rel.startswith(".."):
            return []
        return [part for part in rel.split(os.sep) if part]

    def is_link_product_level_folder(self, folder, expected_code=""):
        parts = self.root_relative_parts(folder)
        if len(parts) != 4:
            return False
        if expected_code:
            code, _suffix = self.strip_link_status_suffix(parts[-1])
            return code == str(expected_code or "").strip()
        return True

    def is_dangerous_material_folder_source(self, source, target_folder=""):
        if not source or not os.path.isdir(source):
            return False
        root = self.root_folder()
        if root and self.normalized_abs_path(source) == self.normalized_abs_path(root):
            return True
        source_parts = self.root_relative_parts(source)
        if source_parts and len(source_parts) < 4:
            return True
        if target_folder and self.path_is_same_or_child(target_folder, source):
            return True
        return False

    def refresh_root_label(self):
        folder = self.root_folder()
        self.path_label.setText(folder if folder else "\u672a\u8bbe\u7f6e\u7d20\u6750\u5e93\u6bcd\u6587\u4ef6\u5939")

    def folder_dialog_start_dir(self, folder):
        folder = str(folder or "").strip()
        while folder and not os.path.isdir(folder):
            parent = os.path.dirname(os.path.abspath(folder))
            if parent == folder:
                folder = ""
                break
            folder = parent
        if folder and os.path.isdir(folder):
            return folder
        fallback = self.shared_reference_base_folder()
        if fallback and os.path.isdir(fallback):
            return fallback
        return os.path.expanduser("~")

    def choose_root_folder(self, mode=None):
        mode = mode or self.library_mode
        current = self.root_folder_for_mode(mode)
        title = "\u9009\u62e9\u94fe\u63a5\u7d20\u6750\u5e93\u6bcd\u6587\u4ef6\u5939" if mode == self.LINK_MODE else "\u9009\u62e9\u4ea7\u54c1\u7d20\u6750\u5e93\u6bcd\u6587\u4ef6\u5939"
        dialog = QFileDialog(self, title, self.folder_dialog_start_dir(current))
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        if dialog.exec_() != QFileDialog.Accepted:
            return
        selected = dialog.selectedFiles()
        folder = selected[0] if selected else ""
        if not folder:
            return
        self.set_root_folder(folder, mode)
        self.refresh_root_label()
        if mode == self.library_mode:
            self.refresh_current_view()

    def show_prompt_library(self):
        if not self.root_folder():
            QMessageBox.information(self, "提示", "请先设置素材库母文件夹，再使用通用参考。")
            return
        existing = getattr(self, "prompt_library_dialog", None)
        if existing is not None:
            if existing.isMinimized():
                existing.showNormal()
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        dialog = MaterialPromptLibraryDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _=None: setattr(self, "prompt_library_dialog", None))
        self.prompt_library_dialog = dialog
        dialog.show()

    def ensure_root_folder(self):
        folder = self.root_folder()
        if not folder:
            QMessageBox.information(self, "提示", "请先点击右上角“设置”，选择素材库母文件夹。")
            return ""
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建素材库母文件夹失败：\n{e}")
            return ""
        return folder

    def toggle_library_mode(self):
        target = self.LINK_MODE if self.library_mode == self.PRODUCT_MODE else self.PRODUCT_MODE
        self.set_library_mode(target)

    def handle_tab_mode_switch(self):
        now = time.time()
        if self._tab_mode_switching or now - self._last_tab_switch_time < 0.15:
            return True
        self._tab_mode_switching = True
        self._last_tab_switch_time = now
        self.toggle_library_mode()
        QTimer.singleShot(0, lambda: setattr(self, "_tab_mode_switching", False))
        return True

    def event_belongs_to_material_window(self, watched):
        return bool(hasattr(watched, "window") and watched.window() is self)

    def save_mode_state(self):
        if self.library_mode == self.PRODUCT_MODE:
            self.product_state = {
                "current_category": self.current_category.get("label", "") if self.current_category else "",
                "selected_categories": set(self.selected_category_labels),
                "selected_specs": set(self.selected_spec_names),
            }
        else:
            self.link_state = {
                "store_id": self.link_store_filter_id,
                "combo": self.selected_link_combo,
                "type": self.selected_link_type,
                "ids": set(self.selected_link_product_ids),
                "show_inactive": self.show_inactive_links_checkbox.isChecked(),
            }

    def set_library_mode(self, mode):
        if mode not in (self.PRODUCT_MODE, self.LINK_MODE):
            return
        if mode == self.library_mode:
            self.refresh_current_view()
            return
        self.save_mode_state()
        self.library_mode = mode
        is_link = self.apply_mode_visibility()
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.refresh_root_label()
        if is_link:
            self.restore_link_state()
        else:
            self.restore_product_state()
        self.schedule_refresh_images_for_current_mode()
        self.show_mode_toast("\u5207\u6362\u5230\u94fe\u63a5\u7d20\u6750\u5e93" if is_link else "\u5207\u6362\u5230\u4ea7\u54c1\u7d20\u6750\u5e93")

    def apply_mode_visibility(self):
        is_link = self.library_mode == self.LINK_MODE
        if hasattr(self, "mode_button"):
            self.mode_button.blockSignals(True)
            self.mode_button.setChecked(is_link)
            self.mode_button.setText("\u94fe\u63a5\u7d20\u6750\u5e93" if is_link else "\u4ea7\u54c1\u7d20\u6750\u5e93")
            self.mode_button.blockSignals(False)
        if hasattr(self, "store_filter_combo"):
            self.store_filter_combo.setVisible(is_link)
        if hasattr(self, "show_inactive_links_checkbox"):
            self.show_inactive_links_checkbox.setVisible(is_link)
        if hasattr(self, "link_sort_button"):
            self.link_sort_button.setVisible(is_link)
        if hasattr(self, "btn_fetch_link_material"):
            self.btn_fetch_link_material.setVisible(is_link)
        if hasattr(self, "image_list"):
            self.image_list.setVisible(not is_link)
        if hasattr(self, "link_image_panel"):
            self.link_image_panel.setVisible(is_link)
        if hasattr(self, "btn_copy_link_folder_path"):
            self.btn_copy_link_folder_path.setVisible(True)
        if hasattr(self, "pdf_import_panel"):
            self.pdf_import_panel.setVisible(not is_link)
        if not is_link and hasattr(self, "link_product_scroll"):
            self.link_product_scroll.setVisible(False)
        return is_link

    def show_mode_toast(self, text):
        if self.mode_toast is None:
            label = QLabel(self)
            label.setAlignment(Qt.AlignCenter)
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            label.setAttribute(Qt.WA_ShowWithoutActivating, True)
            label.setFocusPolicy(Qt.NoFocus)
            label.setStyleSheet(
                """
                QLabel {
                    background: rgba(30, 39, 46, 220);
                    color: white;
                    border-radius: 18px;
                    padding: 12px 28px;
                    font-size: 24px;
                    font-weight: bold;
                }
                """
            )
            self.mode_toast = label
        self.mode_toast.setText(text)
        self.mode_toast.adjustSize()
        x = (self.width() - self.mode_toast.width()) // 2
        y = int(self.height() * 0.68)
        self.mode_toast.move(max(0, x), max(0, y))
        self.mode_toast.raise_()
        self.mode_toast.show()
        self.mode_toast_generation += 1
        generation = self.mode_toast_generation
        QTimer.singleShot(300, lambda: self.mode_toast.hide() if generation == self.mode_toast_generation else None)

    def schedule_refresh_images_for_current_mode(self):
        self.mode_image_load_generation += 1
        generation = self.mode_image_load_generation
        if self.library_mode == self.LINK_MODE:
            self.clear_link_image_lists()
        elif hasattr(self, "image_list"):
            self.clear_product_image_list()
        self.image_count_label.setText("\u6b63\u5728\u5237\u65b0\u7d20\u6750\u5e93...")
        QTimer.singleShot(20, lambda: self.refresh_images_for_current_mode_if_current(generation, self.library_mode))

    def refresh_images_for_current_mode_if_current(self, generation, mode):
        if generation != self.mode_image_load_generation or mode != self.library_mode:
            return
        self.refresh_images_for_current_mode()

    def refresh_images_for_current_mode(self):
        if self.library_mode == self.LINK_MODE:
            self.load_images_for_link_selection()
            return
        if self.current_category and self.selected_spec_names:
            self.load_images_for_selected_specs()
        elif self.current_category:
            self.load_images_for_category()
        elif self.selected_category_labels:
            self.load_images_for_selected_categories()
        else:
            self.clear_product_image_list()
            self.image_count_label.setText("请选择商品类型")
            self.update_attribute_sidebar()

    def restore_product_state(self):
        self.link_product_scroll.setVisible(False)
        state = self.product_state or {}
        self.selected_category_labels = set(state.get("selected_categories") or [])
        self.selected_spec_names = set(state.get("selected_specs") or [])
        label = state.get("current_category") or (next(iter(self.selected_category_labels), "") if self.selected_category_labels else "")
        self.current_category = next((item for item in self.categories if item.get("label") == label), None)
        self.current_spec = None
        if self.current_category:
            self.load_specs(self.current_category.get("label", ""))
            if len(self.selected_spec_names) == 1:
                spec_name = next(iter(self.selected_spec_names))
                self.current_spec = next((item for item in self.specs if item.get("name") == spec_name), None)
            self.refresh_spec_bubbles()
        else:
            self.refresh_category_bubbles()

    def restore_link_state(self):
        state = self.link_state or {}
        self.load_store_filter(state.get("store_id"))
        self.show_inactive_links_checkbox.blockSignals(True)
        self.show_inactive_links_checkbox.setChecked(bool(state.get("show_inactive", False)))
        self.show_inactive_links_checkbox.blockSignals(False)
        self.selected_link_combo = state.get("combo") or ""
        self.selected_link_type = state.get("type") or ""
        self.selected_link_product_ids = set(state.get("ids") or [])
        self.load_link_data()
        self.normalize_selected_link_product_keys()
        self.refresh_link_bubbles()

    def open_link_material_for_product(self, product_db_id):
        try:
            rows = self.db.safe_fetchall(
                """SELECT p.id, COALESCE(p.name, ''), COALESCE(p.link_type, ''),
                          p.store_id, COALESCE(s.name, ''), COALESCE(lc.name, '')
                   FROM products p
                   LEFT JOIN stores s ON s.id = p.store_id
                   LEFT JOIN link_combinations lc ON lc.id = p.link_combo_id
                   WHERE p.id=?""",
                (product_db_id,),
            )
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取链接信息失败：\n{e}")
            return
        if not rows:
            QMessageBox.information(self, "提示", "这个链接已经不存在。")
            return
        _db_id, code, link_type, store_id, _store_name, combo = rows[0]
        if self.library_mode != self.LINK_MODE:
            self.set_library_mode(self.LINK_MODE)
        self.load_store_filter(store_id)
        self.selected_link_combo = str(combo or "").strip() or self.LINK_UNGROUPED
        self.selected_link_type = str(link_type or "").strip() or self.LINK_NO_TYPE
        self.load_link_data()
        item = next((item for item in self.link_items if item.get("db_id") == _db_id), None)
        self.selected_link_product_ids = {self.link_item_key(item)} if item else set()
        item = self.selected_single_link_item()
        if item:
            self.ensure_link_product_folder(item)
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

    def open_product_material_for_spec_code(self, spec_code):
        spec_code = str(spec_code or "").strip()
        if not spec_code:
            QMessageBox.information(self, "提示", "当前规格没有规格编码。")
            return
        rows = self.db.safe_fetchall(
            """SELECT COALESCE(category_label, ''), COALESCE(spec_name, '')
               FROM cost_library
               WHERE spec_code=?""",
            (spec_code,),
        )
        if not rows:
            QMessageBox.information(self, "提示", "成本库里没有找到这个规格。")
            return
        category_label, _spec_name = rows[0]
        category_label = str(category_label or "").strip()
        if not category_label:
            QMessageBox.information(self, "提示", "这个规格没有商品类型，无法定位素材库文件夹。")
            return
        if self.library_mode != self.PRODUCT_MODE:
            self.set_library_mode(self.PRODUCT_MODE)
        if not self.ensure_root_folder():
            return
        self.load_categories()
        category = next((item for item in self.categories if item.get("label") == category_label), None)
        if not category:
            QMessageBox.information(self, "提示", "成本库没有这个商品类型：" + str(category_label))
            return
        self.current_category = category
        self.selected_category_labels = {category_label}
        self.load_specs(category_label)
        spec = next(
            (
                item for item in self.specs
                if spec_code in (item.get("codes") or [])
                or spec_code == item.get("code")
                or spec_code == item.get("primary_code")
            ),
            None,
        )
        if not spec:
            QMessageBox.information(self, "提示", "没有找到对应的素材库规格。")
            return
        self.current_spec = spec
        self.selected_spec_names = {spec.get("name", "")}
        self.sync_spec_folder(category, spec)
        self.refresh_spec_bubbles()
        self.load_images_for_spec()

    def open_product_material_for_link(self, product_db_id):
        rows = self.db.safe_fetchall(
            """SELECT ps.spec_code, COALESCE(ps.spec_name, ''), COALESCE(ps.sale_price, 0),
                      COALESCE(cl.category_label, ''), COALESCE(cl.spec_name, '')
               FROM product_specs ps
               LEFT JOIN cost_library cl ON cl.spec_code = ps.spec_code
               WHERE ps.product_id=? AND COALESCE(ps.spec_code, '') <> ''
            """,
            (product_db_id,),
        )
        categories = {}
        for spec_code, product_spec_name, sale_price, category_label, cost_spec_name in rows:
            category_label = str(category_label or "").strip()
            spec_code = str(spec_code or "").strip()
            if not category_label or not spec_code:
                continue
            spec_name = str(cost_spec_name or product_spec_name or spec_code).strip()
            product_name = self.normalize_material_spec_name(spec_name) or spec_name
            category = categories.setdefault(category_label, {"count": 0, "max_price": 0.0, "groups": {}})
            try:
                price = float(sale_price or 0)
            except Exception:
                price = 0.0
            category["count"] += 1
            category["max_price"] = max(category["max_price"], price)
            group = category["groups"].setdefault(
                product_name.lower(),
                {"name": product_name, "count": 0, "max_price": 0.0, "spec_code": spec_code},
            )
            group["count"] += 1
            if price >= group["max_price"]:
                group["max_price"] = price
                group["spec_code"] = spec_code

        if not categories:
            QMessageBox.information(self, "提示", "这个链接的规格没有匹配到成本库商品类型，无法打开产品素材库。")
            return

        category_label, category_info = sorted(
            categories.items(),
            key=lambda item: (-item[1]["count"], -item[1]["max_price"], item[0]),
        )[0]
        groups = list(category_info["groups"].values())
        if len(groups) == 1:
            self.open_product_material_for_spec_code(groups[0]["spec_code"])
            return

        if self.library_mode != self.PRODUCT_MODE:
            self.set_library_mode(self.PRODUCT_MODE)
        if not self.ensure_root_folder():
            return
        self.load_categories()
        category = next((item for item in self.categories if item.get("label") == category_label), None)
        if not category:
            QMessageBox.information(self, "提示", "成本库没有这个商品类型：" + str(category_label))
            return
        self.select_category(category)

    def safe_folder_name(self, text, fallback):
        value = re.sub(r'[<>:"/\\\\|?*]', "", str(text or "")).strip().strip(".")
        return value or fallback
    def normalize_material_spec_name(self, spec_name):
        text = str(spec_name or "").strip()
        if not text:
            return ""
        text = text.translate(str.maketrans({"\uff08": "(", "\uff09": ")", "\u3010": "[", "\u3011": "]", "\uff3b": "[", "\uff3d": "]"}))
        text = re.sub(r"\s+([\(\[]) ", r"\1", text)
        text = re.sub(r"\s+([\(\[])", r"\1", text)
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fffA-Za-z0-9])", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        units = r"\u5f20|\u672c|\u9875|\u5957|\u4efd|\u4e2a|\u518c|\u7ec4"
        changed = True
        while changed:
            before = text
            text = re.sub(rf"\s*\u5171\s*\d+\s*(?:{units})(?:\s*[\[(]\s*\d+\s*(?:{units})\s*[\])])?\s*$", "", text)
            text = re.sub(rf"\s*[\[(]\s*(?:\u5171\s*)?\d+\s*(?:{units})(?:\s*[\[(]\s*\d+\s*(?:{units})\s*[\])])?(?:\s*\u88c5)?\s*[\])]\s*$", "", text)
            text = re.sub(rf"\s*(?<![-\u2013\u2014\d])\d+\s*(?:{units})(?:\s*[\[(]\s*\d+\s*(?:{units})\s*[\])])?(?:\s*\u88c5)?\s*$", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            changed = text != before
        return text or str(spec_name or "").strip()

    def normalize_attribute_key(self, text):
        value = str(text or "").strip().lower()
        value = value.translate(str.maketrans({"\uff1a": ":", "\uff0c": ",", "\uff1b": ";", "\u3001": ","}))
        value = re.sub(r"\s+", "", value)
        return value

    def category_folder(self, category):
        root = self.root_folder()
        return os.path.join(root, self.safe_folder_name(category.get("label"), "未命名类型"))

    def category_identity_key(self, specs):
        codes = sorted({
            str(code or "").strip()
            for spec in specs or []
            for code in (spec.get("codes", []) or [spec.get("primary_code", ""), spec.get("code", "")])
            if str(code or "").strip()
        })
        if not codes:
            return ""
        digest = hashlib.md5("|".join(codes).encode("utf-8")).hexdigest()
        return f"category_folder_path/{self.settings_key(self.PRODUCT_MODE)}/{digest}"

    def sync_category_folder(self, category, specs=None):
        if not self.root_folder():
            return ""
        specs = specs if specs is not None else self.get_specs_for_category(category.get("label", ""))
        target = self.category_folder(category)
        key = self.category_identity_key(specs)
        if key:
            old_path = str(self.settings.value(key, "") or "").strip()
            if not old_path:
                old_path = str(self.local_category_folder_paths.get(key, "") or "").strip()
            if old_path and os.path.isdir(old_path) and os.path.abspath(old_path) != os.path.abspath(target):
                try:
                    self.merge_or_move_material_folder(old_path, target)
                except Exception:
                    pass
        os.makedirs(target, exist_ok=True)
        if key:
            if os.path.abspath(str(self.local_category_folder_paths.get(key, "") or "")) != os.path.abspath(target):
                self.local_category_folder_paths[key] = target
                self.settings.setValue(key, target)
                self._settings_keys_cache = None
                self.settings.sync()
        return target

    def spec_folder(self, category, spec):
        return os.path.join(
            self.category_folder(category),
            self.safe_folder_name(spec.get("name"), "未命名规格"),
        )

    def spec_alias_folder_names(self, spec):
        names = []
        for name in [spec.get("name", ""), spec.get("primary_original_name", "")] + list(spec.get("aliases", [])):
            safe_name = self.safe_folder_name(name, "未命名规格")
            if safe_name and safe_name not in names:
                names.append(safe_name)
            normalized = self.safe_folder_name(self.normalize_material_spec_name(name), "未命名规格")
            if normalized and normalized not in names:
                names.append(normalized)
        return names

    def spec_folder_mapping_key(self, category, code):
        category_name = self.safe_folder_name(category.get("label"), "未命名类型")
        code_value = self.safe_folder_name(code, "未命名编码")
        return f"spec_folder_name/{self.settings_key(self.PRODUCT_MODE)}/{category_name}/{code_value}"

    def spec_folder_path_mapping_key(self, code):
        code_value = self.safe_folder_name(code, "未命名编码")
        return f"spec_folder_path/{self.settings_key(self.PRODUCT_MODE)}/{code_value}"

    def mapped_spec_folder_paths(self, category, spec):
        paths = []
        root = self.root_folder()
        for code in spec.get("codes", []) or [spec.get("primary_code", "")]:
            if not code:
                continue
            path_key = self.spec_folder_path_mapping_key(code)
            value = str(self.settings.value(path_key, "") or "").strip()
            if value and value not in paths:
                paths.append(value)
            code_value = self.safe_folder_name(code, "未命名编码")
            prefix = f"spec_folder_name/{self.settings_key(self.PRODUCT_MODE)}/"
            suffix = f"/{code_value}"
            for key in self.settings_all_keys():
                if not key.startswith(prefix) or not key.endswith(suffix):
                    continue
                category_name = key[len(prefix):-len(suffix)]
                folder_name = str(self.settings.value(key, "") or "").strip()
                if root and category_name and folder_name:
                    legacy_path = os.path.join(root, category_name, folder_name)
                    if legacy_path not in paths:
                        paths.append(legacy_path)
        return paths

    def settings_all_keys(self):
        if self._settings_keys_cache is None:
            try:
                self._settings_keys_cache = self.settings.allKeys()
            except Exception:
                self._settings_keys_cache = []
        return self._settings_keys_cache

    def discover_spec_folder_paths_across_categories(self, category, spec):
        root = self.root_folder()
        if not root or not os.path.isdir(root):
            return []
        current_category_folder = os.path.abspath(self.category_folder(category))
        folder_names = set(self.spec_alias_folder_names(spec))
        paths = []
        try:
            category_names = os.listdir(root)
        except Exception:
            return []
        for category_name in category_names:
            category_path = os.path.join(root, category_name)
            if not os.path.isdir(category_path):
                continue
            for folder_name in folder_names:
                source = os.path.join(category_path, folder_name)
                if not os.path.isdir(source):
                    continue
                if os.path.abspath(source) == os.path.abspath(os.path.join(current_category_folder, folder_name)):
                    continue
                if source not in paths:
                    paths.append(source)
        return paths

    def mapped_spec_folder_names(self, category, spec):
        names = []
        for code in spec.get("codes", []) or [spec.get("primary_code", "")]:
            if not code:
                continue
            key = self.spec_folder_mapping_key(category, code)
            value = str(self.settings.value(key, "") or "").strip()
            if not value:
                value = str(self.local_spec_folder_mappings.get(key, "") or "").strip()
            if value and value not in names:
                names.append(value)
        return names

    def save_spec_folder_mapping(self, category, spec, folder_name):
        target = self.spec_folder(category, spec)
        changed = False
        for code in spec.get("codes", []) or [spec.get("primary_code", "")]:
            if code:
                key = self.spec_folder_mapping_key(category, code)
                path_key = self.spec_folder_path_mapping_key(code)
                if str(self.local_spec_folder_mappings.get(key, "") or "") != folder_name:
                    self.local_spec_folder_mappings[key] = folder_name
                    self.settings.setValue(key, folder_name)
                    changed = True
                if str(self.settings.value(path_key, "") or "") != target:
                    self.settings.setValue(path_key, target)
                    changed = True
        if changed:
            self._settings_keys_cache = None
            self.settings.sync()

    def merge_or_move_material_folder(self, source, target):
        if not source or not os.path.isdir(source):
            return
        if os.path.abspath(source) == os.path.abspath(target):
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.exists(target):
            try:
                os.rename(source, target)
                return
            except OSError:
                os.makedirs(target, exist_ok=True)
        for name in os.listdir(source):
            src_path = os.path.join(source, name)
            dst_path = os.path.join(target, name)
            if os.path.isdir(src_path):
                self.merge_or_move_material_folder(src_path, dst_path)
            else:
                if os.path.exists(dst_path) and filecmp.cmp(src_path, dst_path, shallow=False):
                    try:
                        os.remove(src_path)
                    except OSError:
                        pass
                    continue
                dst_path = self.unique_destination_path(target, name) if os.path.exists(dst_path) else dst_path
                shutil.move(src_path, dst_path)
        try:
            os.rmdir(source)
        except OSError:
            pass

    def copy_material_folder(self, source, target):
        if not source or not os.path.isdir(source) or os.path.abspath(source) == os.path.abspath(target):
            return
        os.makedirs(target, exist_ok=True)
        for name in os.listdir(source):
            src_path = os.path.join(source, name)
            dst_path = os.path.join(target, name)
            if os.path.isdir(src_path):
                self.copy_material_folder(src_path, dst_path)
            else:
                if os.path.exists(dst_path):
                    if filecmp.cmp(src_path, dst_path, shallow=False):
                        continue
                    dst_path = self.unique_destination_path(target, name)
                shutil.copy2(src_path, dst_path)

    def spec_folder_path_shared_by_other_codes(self, source, spec):
        source = os.path.normcase(os.path.abspath(source or ""))
        current_codes = {
            self.safe_folder_name(code, "code")
            for code in (spec.get("codes", []) or [spec.get("primary_code", ""), spec.get("code", "")])
            if str(code or "").strip()
        }
        prefix = f"spec_folder_path/{self.settings_key(self.PRODUCT_MODE)}/"
        for key in self.settings_all_keys():
            if not key.startswith(prefix):
                continue
            value = str(self.settings.value(key, "") or "").strip()
            if value and os.path.normcase(os.path.abspath(value)) == source and key[len(prefix):] not in current_codes:
                return True
        return False

    def remove_empty_category_parent(self, path):
        root = os.path.abspath(self.root_folder() or "")
        parent = os.path.abspath(os.path.dirname(path or ""))
        if not root or os.path.normcase(os.path.dirname(parent)) != os.path.normcase(root):
            return
        try:
            os.rmdir(parent)
        except OSError:
            pass

    def sync_spec_folder(self, category, spec, discover_across_categories=True):
        if not self.root_folder():
            return ""
        target = self.spec_folder(category, spec)
        category_folder = self.category_folder(category)
        alias_names = self.spec_alias_folder_names(spec)
        folder_names = alias_names + [
            name for name in self.mapped_spec_folder_names(category, spec)
            if name not in alias_names
        ]
        sources = self.mapped_spec_folder_paths(category, spec)
        if discover_across_categories:
            sources += self.discover_spec_folder_paths_across_categories(category, spec)
        for source in sources:
            if os.path.isdir(source) and os.path.abspath(source) != os.path.abspath(target):
                try:
                    if self.spec_folder_path_shared_by_other_codes(source, spec):
                        self.copy_material_folder(source, target)
                    else:
                        self.merge_or_move_material_folder(source, target)
                        self.remove_empty_category_parent(source)
                except Exception:
                    pass
        for folder_name in folder_names:
            source = os.path.join(category_folder, folder_name)
            if os.path.isdir(source) and os.path.abspath(source) != os.path.abspath(target):
                try:
                    self.merge_or_move_material_folder(source, target)
                except Exception:
                    pass
        self.save_spec_folder_mapping(category, spec, self.safe_folder_name(spec.get("name"), "未命名规格"))
        return target

    def sync_spec_folders(self, category, specs=None):
        if not self.root_folder():
            return
        self.sync_category_folder(category, specs if specs is not None else self.specs)
        for spec in specs if specs is not None else self.specs:
            self.sync_spec_folder(category, spec)

    def spec_image_folders(self, category, spec):
        category_folder = self.category_folder(category)
        folders = []
        seen = set()
        for folder_name in self.spec_alias_folder_names(spec) + self.mapped_spec_folder_names(category, spec):
            folder = os.path.join(category_folder, folder_name)
            key = os.path.abspath(folder)
            if key not in seen:
                seen.add(key)
                folders.append(folder)
        for folder in self.mapped_spec_folder_paths(category, spec):
            key = os.path.abspath(folder)
            if key not in seen:
                seen.add(key)
                folders.append(folder)
        return folders

    def schedule_deferred_spec_sync(self, category, specs=None):
        if not self.root_folder() or not category:
            return
        self._spec_sync_queue = [(category, spec) for spec in (specs if specs is not None else self.specs)]
        if self._spec_sync_running:
            return
        self._spec_sync_running = bool(self._spec_sync_queue)
        if self._spec_sync_running:
            QTimer.singleShot(50, self.process_deferred_spec_sync)

    def process_deferred_spec_sync(self):
        if not self._spec_sync_queue:
            self._spec_sync_running = False
            return
        category, spec = self._spec_sync_queue.pop(0)
        try:
            self.sync_spec_folder(category, spec, discover_across_categories=False)
        except Exception:
            pass
        QTimer.singleShot(15, self.process_deferred_spec_sync)

    def load_categories(self, refresh=True):
        try:
            if hasattr(self.db, "sync_cost_categories"):
                self.db.sync_cost_categories()
            rows = self.db.safe_fetchall(
                """SELECT cc.label, cc.color, COALESCE(cc.sort_order, 0), COUNT(cl.spec_code) AS spec_count
                   FROM cost_categories cc
                   JOIN cost_library cl ON cl.category_label = cc.label
                   WHERE COALESCE(cc.label, '') <> ''
                   GROUP BY cc.label, cc.color, cc.sort_order
                   HAVING COUNT(cl.spec_code) > 0
                   ORDER BY cc.sort_order, cc.label"""
            )
            rows = sorted(rows, key=lambda row: (self.cost_category_family_key(row[0]), row[2] or 0, str(row[0] or "")))
            colors = self.cost_category_display_colors([row[0] for row in rows])
            self.categories = [
                {
                    "label": str(label or ""),
                    "color": colors.get(str(label or "").strip(), "#DDEBF7"),
                    "sort": sort_order or 0,
                    "count": count or 0,
                }
                for label, _color, sort_order, count in rows
                if str(label or "").strip()
            ]
        except Exception as e:
            QMessageBox.warning(self, "\u8b66\u544a", f"\u8bfb\u53d6\u6210\u672c\u5e93\u5546\u54c1\u7c7b\u578b\u5931\u8d25\uff1a\\n{e}")
            self.categories = []
        if refresh:
            self.refresh_bubbles()

    def cost_category_family_key(self, label):
        text = str(label or "").strip().lower()
        if not text:
            return ""
        text = re.sub(
            r"(\u5957\u88c5|\u7ec4\u5408|\u5957\u9910|\u793c\u76d2|\u7cfb\u5217|\u5355\u672c|\u591a\u672c|\u5355\u54c1|\u591a\u4ef6|\u88c5)$",
            "",
            text,
        )
        text = re.sub(r"\d+(?:\.\d+)?\s*(?:\u672c|\u4e2a|\u4ef6|\u5957|\u5305|\u76d2|\u5f20|\u518c|\u4efd)?", "", text)
        text = re.sub(r"[\\/\-_\s,\uff0c\u3002\uff1b;\uff1f\u3001\uff08\uff09()\u3010\u3011\[\]]+", "", text)
        return text or str(label or "").strip().lower()

    def cost_category_display_colors(self, labels):
        groups = {}
        for label in labels:
            label = str(label or "").strip()
            if label:
                groups.setdefault(self.cost_category_family_key(label), []).append(label)
        colors = {}
        total_categories = max(sum(len(v) for v in groups.values()), 1)
        color_index = 0
        for family_index, family in enumerate(sorted(groups)):
            members = sorted(dict.fromkeys(groups[family]))
            for member_index, label in enumerate(members):
                hue = int(color_index * 359 / total_categories)
                colors[label] = QColor.fromHsl(hue, 128, 204).name().upper()
                color_index += 1
        return colors

    def sync_all_category_folders(self):
        if not self.root_folder():
            return
        for category in self.categories:
            try:
                specs = self.get_specs_for_category(category.get("label", ""))
                self.sync_category_folder(category, specs)
            except Exception:
                pass

    def schedule_deferred_category_sync(self):
        if not self.root_folder():
            return
        self._category_sync_queue = list(self.categories)
        if self._category_sync_running:
            return
        self._category_sync_running = bool(self._category_sync_queue)
        if self._category_sync_running:
            QTimer.singleShot(0, self.process_deferred_category_sync)

    def process_deferred_category_sync(self):
        if not self._category_sync_queue:
            self._category_sync_running = False
            return
        category = self._category_sync_queue.pop(0)
        try:
            specs = self.get_specs_for_category(category.get("label", ""))
            self.sync_category_folder(category, specs)
        except Exception:
            pass
        QTimer.singleShot(20, self.process_deferred_category_sync)

    def load_specs(self, category_label):
        self.specs = self.get_specs_for_category(category_label)

    def search_text_matches(self, keyword, *values):
        return all_terms_match(split_search_terms(keyword), *values)

    def on_search_changed(self, text):
        keyword = str(text or "").strip()
        if self.library_mode == self.LINK_MODE and keyword:
            matches = [item for item in self.link_items if str(item.get("code", "")).strip().casefold() == keyword.casefold()]
            if len(matches) == 1:
                item = matches[0]
                self.selected_link_combo = item["combo"]
                self.selected_link_type = item["link_type"]
                self.selected_link_product_ids = {self.link_item_key(item)}
                self.search_input.blockSignals(True)
                self.search_input.clear()
                self.search_input.blockSignals(False)
                self.ensure_link_product_folder(item)
                self.refresh_link_bubbles()
                self.schedule_load_images_for_link_selection()
                return
        self.refresh_bubbles()

    def spec_matches_keyword(self, spec, keyword, *extra_values):
        if not keyword:
            return True
        values = [
            spec.get("name", ""),
            spec.get("code", ""),
            spec.get("primary_code", ""),
            spec.get("primary_original_name", ""),
        ]
        values.extend(spec.get("aliases", []) or [])
        values.extend(spec.get("codes", []) or [])
        values.extend(extra_values)
        return self.search_text_matches(keyword, *values)

    def category_matches_keyword(self, category, keyword):
        if not keyword:
            return True
        label = str(category.get("label", "") or "")
        if self.search_text_matches(keyword, label):
            return True
        try:
            specs = self.get_specs_for_category(label)
        except Exception:
            return False
        return any(self.spec_matches_keyword(spec, keyword, label) for spec in specs)

    def get_specs_for_category(self, category_label):
        rows = self.db.safe_fetchall(
            """SELECT COALESCE(spec_name, ''), spec_code, COALESCE(product_attribute, ''),
                      manual_sort_order, sort_order
               FROM cost_library
               WHERE COALESCE(category_label, '') = ?
               ORDER BY CASE WHEN manual_sort_order IS NULL THEN 1 ELSE 0 END,
                        manual_sort_order, sort_order, spec_code""",
            (category_label,),
        )
        normalized_name_counts = {}
        for spec_name, spec_code, _product_attribute, _manual_sort_order, _sort_order in rows:
            original_name = str(spec_name or "").strip() or str(spec_code or "").strip() or "未命名规格"
            normalized_name = self.normalize_material_spec_name(original_name) or original_name
            normalized_name_counts.setdefault(normalized_name.lower(), set()).add(original_name)
        grouped = {}
        for spec_name, spec_code, product_attribute, manual_sort_order, sort_order in rows:
            original_name = str(spec_name or "").strip() or str(spec_code or "").strip() or "未命名规格"
            normalized_name = self.normalize_material_spec_name(original_name) or original_name
            normalized_key = normalized_name.lower()
            should_merge_name = len(normalized_name_counts.get(normalized_key, set())) > 1
            display_name = normalized_name if should_merge_name else original_name
            key = normalized_key if should_merge_name else f"{original_name.lower()}::{str(spec_code or '').strip()}"
            code = str(spec_code or "").strip()
            item = grouped.get(key)
            if not item:
                item = {
                    "name": display_name,
                    "code": code,
                    "primary_code": code,
                    "primary_original_name": original_name,
                    "merged_by_quantity": should_merge_name,
                    "manual_sort": manual_sort_order,
                    "sort": sort_order,
                    "codes": [],
                    "aliases": [],
                    "attributes": [],
                    "attribute_keys": set(),
                }
                grouped[key] = item
            if code and code not in item["codes"]:
                item["codes"].append(code)
            if original_name not in item["aliases"]:
                item["aliases"].append(original_name)
            if item.get("merged_by_quantity"):
                target_name = self.normalize_material_spec_name(item.get("primary_original_name", "")) or item["name"]
            else:
                target_name = item.get("primary_original_name", "") or item["name"]
            if item["name"] != target_name:
                item["name"] = target_name
            attr_text = str(product_attribute or "").strip()
            attr_key = self.normalize_attribute_key(attr_text)
            if attr_text and attr_key and attr_key not in item["attribute_keys"]:
                item["attributes"].append(attr_text)
                item["attribute_keys"].add(attr_key)
        specs = list(grouped.values())
        for item in specs:
            item.pop("attribute_keys", None)
            item.pop("merged_by_quantity", None)
        return specs

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        layout.invalidate()

    def refresh_chip_layout_geometry(self, scroll, content, layout):
        if not scroll.isVisible():
            return
        layout.invalidate()
        layout.activate()
        content.updateGeometry()
        content.adjustSize()
        scroll.viewport().update()
        scroll.updateGeometry()

    def schedule_chip_layout_refresh(self):
        targets = (
            (self.category_scroll, self.category_content, self.category_layout),
            (self.spec_scroll, self.spec_content, self.spec_layout),
            (self.link_product_scroll, self.link_product_content, self.link_product_layout),
        )
        for scroll, content, layout in targets:
            self.refresh_chip_layout_geometry(scroll, content, layout)
        QTimer.singleShot(
            0,
            lambda: [
                self.refresh_chip_layout_geometry(scroll, content, layout)
                for scroll, content, layout in targets
            ],
        )

    def refresh_bubbles(self):
        self.apply_mode_visibility()
        if self.library_mode == self.LINK_MODE:
            self.refresh_link_bubbles()
            return
        if self.current_category:
            self.refresh_spec_bubbles()
        else:
            self.refresh_category_bubbles()

    def clear_search_input(self):
        if not hasattr(self, "search_input") or not self.search_input.text():
            return False
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        return True

    def refresh_category_bubbles(self):
        if self.library_mode != self.PRODUCT_MODE:
            return
        self.apply_mode_visibility()
        self.category_scroll.setVisible(True)
        self.spec_scroll.setVisible(False)
        self.link_product_scroll.setVisible(False)
        self.back_button.setEnabled(False)
        self.current_label.setText("\u5546\u54c1\u7c7b\u578b")
        self.clear_layout(self.category_layout)
        self.clear_layout(self.link_product_layout)
        self.category_buttons = {}
        self.link_product_buttons = {}
        self.link_products = []
        keyword = self.search_input.text().strip().lower()
        for category in self.categories:
            label = category["label"]
            if not self.category_matches_keyword(category, keyword):
                continue
            button = self.create_chip(label, category.get("color") or "#DDEBF7")
            button.setChecked(label in self.selected_category_labels)
            self.configure_order_chip(button, "category", label)
            button.clicked.connect(lambda _checked=False, c=category: self.toggle_category(c))
            self.category_layout.addWidget(button)
            self.category_buttons[label] = button
        if not self.categories:
            self.image_count_label.setText("\u6210\u672c\u5e93\u91cc\u8fd8\u6ca1\u6709\u5546\u54c1\u7c7b\u578b")
        self.schedule_chip_layout_refresh()

    def refresh_spec_bubbles(self):
        if self.library_mode != self.PRODUCT_MODE:
            return
        self.apply_mode_visibility()
        self.category_scroll.setVisible(False)
        self.spec_scroll.setVisible(True)
        self.link_product_scroll.setVisible(False)
        self.back_button.setEnabled(True)
        category_label = self.current_category.get("label", "")
        self.current_label.setText("\u5546\u54c1\u7c7b\u578b\uff1a" + str(category_label))
        self.clear_layout(self.spec_layout)
        self.clear_layout(self.link_product_layout)
        self.spec_buttons = {}
        self.link_product_buttons = {}
        self.link_products = []
        keyword = self.search_input.text().strip().lower()
        for spec in self.specs:
            name = spec["name"]
            if not self.spec_matches_keyword(spec, keyword, category_label):
                continue
            button = self.create_chip(name, self.current_category.get("color") or "#DDEBF7")
            button.setChecked(name in self.selected_spec_names)
            self.configure_spec_drop_target(button, spec)
            self.configure_order_chip(button, "spec", name)
            button.clicked.connect(lambda _checked=False, s=spec: self.toggle_spec(s))
            self.spec_layout.addWidget(button)
            self.spec_buttons[name] = button
        self.schedule_chip_layout_refresh()

    def create_chip(self, text, color):
        bg = QColor(color if color else "#DDEBF7")
        fg = QColor("#1f2d3d")
        button = QPushButton(text)
        self.remove_tab_focus(button)
        button.setCheckable(True)
        button.setMinimumHeight(34)
        button.setProperty("baseMinimumHeight", 34)
        button.setAcceptDrops(True)
        button.installEventFilter(self)
        button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg.name()};
                color: {fg.name()};
                border: 1px solid #b8c2cc;
                border-radius: 16px;
                padding: 5px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: #3498db;
            }}
            QPushButton:checked {{
                border: 2px solid #2f80ed;
                padding: 4px 13px;
            }}
            QPushButton[dropHover="true"] {{
                background-color: #eafff2;
                border: 2px solid #27ae60;
                padding: 4px 13px;
            }}
            QPushButton[orderHover="true"] {{
                background-color: #fff7d6;
                border: 2px solid #f39c12;
                padding: 4px 13px;
            }}
            """
        )
        return button

    def configure_order_chip(self, button, order_type, order_id):
        button.setProperty("materialOrderType", order_type)
        button.setProperty("materialOrderId", str(order_id or ""))
        button.setAcceptDrops(True)
        button.installEventFilter(self)

    def configure_spec_drop_target(self, button, spec):
        button.setProperty("materialDropTarget", "product_spec")
        button.material_spec = spec

    def configure_link_product_drop_target(self, button, item):
        button.setProperty("materialDropTarget", "link_product")
        button.material_link_item = item
        button.setAcceptDrops(True)
        button.installEventFilter(self)

    def set_chip_drop_hover(self, button, active):
        if button is None or sip.isdeleted(button):
            if self._active_drop_hover_chip is button:
                self._active_drop_hover_chip = None
            return
        if active:
            if (
                self._active_drop_hover_chip is not None
                and self._active_drop_hover_chip is not button
                and not sip.isdeleted(self._active_drop_hover_chip)
            ):
                self.set_chip_drop_hover(self._active_drop_hover_chip, False)
            self._active_drop_hover_chip = button
        elif self._active_drop_hover_chip is button:
            self._active_drop_hover_chip = None
        button.setProperty("dropHover", bool(active))
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()
        base_height = int(button.property("baseMinimumHeight") or 34)
        target_height = base_height + 6 if active else base_height
        animation = QPropertyAnimation(button, b"minimumHeight", self)
        animation.setDuration(120)
        animation.setStartValue(button.minimumHeight())
        animation.setEndValue(target_height)
        animation.valueChanged.connect(lambda _value: self.schedule_chip_layout_refresh())
        animation.finished.connect(self.schedule_chip_layout_refresh)
        animation.start()
        self._chip_animations[id(button)] = animation

    def clear_active_drop_hover(self):
        button = self._active_drop_hover_chip
        self._active_drop_hover_chip = None
        if button is not None:
            self.set_chip_drop_hover(button, False)

    def set_chip_order_hover(self, button, active):
        if button is None or sip.isdeleted(button):
            if self._active_order_hover_chip is button:
                self._active_order_hover_chip = None
            return
        if active:
            if (
                self._active_order_hover_chip is not None
                and self._active_order_hover_chip is not button
                and not sip.isdeleted(self._active_order_hover_chip)
            ):
                self.set_chip_order_hover(self._active_order_hover_chip, False)
            self._active_order_hover_chip = button
            self.clear_active_drop_hover()
        elif self._active_order_hover_chip is button:
            self._active_order_hover_chip = None
        button.setProperty("orderHover", bool(active))
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()
        base_height = int(button.property("baseMinimumHeight") or 34)
        target_height = base_height + 8 if active else base_height
        height_anim = QPropertyAnimation(button, b"minimumHeight", self)
        height_anim.setDuration(120)
        height_anim.setStartValue(button.minimumHeight())
        height_anim.setEndValue(target_height)
        height_anim.valueChanged.connect(lambda _value: self.schedule_chip_layout_refresh())
        height_anim.finished.connect(self.schedule_chip_layout_refresh)
        height_anim.start()
        self._chip_animations[(id(button), "order_height")] = height_anim
        if active:
            start_pos = button.pos()
            shake = QPropertyAnimation(button, b"pos", self)
            shake.setDuration(180)
            shake.setKeyValueAt(0.0, start_pos)
            shake.setKeyValueAt(0.25, start_pos + QPoint(-2, 0))
            shake.setKeyValueAt(0.5, start_pos + QPoint(2, 0))
            shake.setKeyValueAt(0.75, start_pos + QPoint(-1, 0))
            shake.setKeyValueAt(1.0, start_pos)
            shake.start()
            self._chip_animations[(id(button), "order_shake")] = shake

    def clear_active_order_hover(self):
        button = self._active_order_hover_chip
        self._active_order_hover_chip = None
        if button is not None:
            self.set_chip_order_hover(button, False)

    def chip_order_mime_text(self, order_type, order_id):
        return f"{order_type}\n{order_id}"

    def parse_chip_order_mime(self, mime_data):
        if not mime_data.hasFormat("application/x-shop-material-chip-order"):
            return "", ""
        try:
            text = bytes(mime_data.data("application/x-shop-material-chip-order")).decode("utf-8")
        except Exception:
            return "", ""
        parts = text.splitlines()
        return (parts[0].strip(), parts[1].strip()) if len(parts) >= 2 else ("", "")

    def start_chip_order_drag(self, button):
        order_type = str(button.property("materialOrderType") or "")
        order_id = str(button.property("materialOrderId") or "")
        if order_type not in ("category", "spec") or not order_id:
            return
        self._chip_dragging_order = True
        drag = QDrag(button)
        mime = QMimeData()
        mime.setData("application/x-shop-material-chip-order", self.chip_order_mime_text(order_type, order_id).encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = button.grab()
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
        drag.exec_(Qt.MoveAction)
        self._chip_dragging_order = False
        self.clear_active_order_hover()
        self.clear_active_drop_hover()

    def move_item_before(self, items, source_value, target_value, value_getter):
        source_index = next((index for index, item in enumerate(items) if value_getter(item) == source_value), -1)
        target_index = next((index for index, item in enumerate(items) if value_getter(item) == target_value), -1)
        if source_index < 0 or target_index < 0 or source_index == target_index:
            return False
        item = items.pop(source_index)
        if source_index < target_index:
            target_index -= 1
        items.insert(target_index, item)
        return True

    def save_category_chip_order(self):
        try:
            for index, category in enumerate(self.categories, start=1):
                label = category.get("label", "")
                category["sort"] = index
                if hasattr(self.db, "cursor"):
                    self.db.cursor.execute("UPDATE cost_categories SET sort_order=? WHERE label=?", (index, label))
                elif hasattr(self.db, "safe_execute"):
                    self.db.safe_execute("UPDATE cost_categories SET sort_order=? WHERE label=?", (index, label))
            if hasattr(self.db, "conn"):
                self.db.conn.commit()
            return True
        except Exception as e:
            try:
                if hasattr(self.db, "conn"):
                    self.db.conn.rollback()
            except Exception:
                pass
            QMessageBox.warning(self, "保存排序失败", f"保存商品类型顺序失败：\n{e}")
            return False

    def save_spec_chip_order(self):
        ordered_codes = []
        for spec in self.specs:
            for code in spec.get("codes", []) or [spec.get("primary_code", ""), spec.get("code", "")]:
                code = str(code or "").strip()
                if code and code not in ordered_codes:
                    ordered_codes.append(code)
        if not ordered_codes:
            return False
        if hasattr(self.db, "update_cost_manual_sort_orders"):
            ok = self.db.update_cost_manual_sort_orders(ordered_codes)
        else:
            ok = False
            try:
                for index, code in enumerate(ordered_codes, start=1):
                    if hasattr(self.db, "cursor"):
                        self.db.cursor.execute("UPDATE cost_library SET manual_sort_order=? WHERE spec_code=?", (index, code))
                if hasattr(self.db, "conn"):
                    self.db.conn.commit()
                ok = True
            except Exception:
                ok = False
        if not ok:
            QMessageBox.warning(self, "保存排序失败", "保存规格顺序失败。")
        return bool(ok)

    def reorder_chip(self, order_type, source_id, target_id):
        if order_type == "category":
            changed = self.move_item_before(self.categories, source_id, target_id, lambda item: item.get("label", ""))
            if changed and self.save_category_chip_order():
                self.refresh_category_bubbles()
            return changed
        if order_type == "spec":
            changed = self.move_item_before(self.specs, source_id, target_id, lambda item: item.get("name", ""))
            if changed and self.save_spec_chip_order():
                self.refresh_spec_bubbles()
            return changed
        return False

    def eventFilter(self, watched, event):
        if (
            event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress)
            and event.key() in (Qt.Key_Tab, Qt.Key_Backtab)
            and self.event_belongs_to_material_window(watched)
        ):
            event.accept()
            return self.handle_tab_mode_switch()
        if getattr(watched, "property", None) and watched.property("materialOrderType") in ("category", "spec"):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._chip_press_button = watched
                self._chip_press_pos = event.pos()
                self._chip_press_time = time.time()
            elif event.type() == QEvent.MouseMove and self._chip_press_button is watched:
                distance = (event.pos() - self._chip_press_pos).manhattanLength()
                if distance >= QApplication.startDragDistance() and time.time() - self._chip_press_time >= 0.3:
                    self.start_chip_order_drag(watched)
                    return True
            elif event.type() == QEvent.MouseButtonRelease and self._chip_press_button is watched:
                self._chip_press_button = None
                self._chip_press_time = 0
            if event.type() in (QEvent.DragEnter, QEvent.DragMove):
                source_type, source_id = self.parse_chip_order_mime(event.mimeData())
                target_type = str(watched.property("materialOrderType") or "")
                target_id = str(watched.property("materialOrderId") or "")
                if source_type == target_type and source_id and target_id and source_id != target_id:
                    self.clear_active_drop_hover()
                    self.set_chip_order_hover(watched, True)
                    event.setDropAction(Qt.MoveAction)
                    event.accept()
                    return True
                self.clear_active_order_hover()
            if event.type() == QEvent.DragLeave:
                self.clear_active_order_hover()
                return False
            if event.type() == QEvent.Drop:
                self.clear_active_order_hover()
                source_type, source_id = self.parse_chip_order_mime(event.mimeData())
                target_type = str(watched.property("materialOrderType") or "")
                target_id = str(watched.property("materialOrderId") or "")
                if source_type == target_type and source_id and target_id and source_id != target_id:
                    if self.reorder_chip(source_type, source_id, target_id):
                        event.setDropAction(Qt.MoveAction)
                        event.accept()
                        return True
        if getattr(watched, "property", None) and watched.property("materialDropTarget") in ("product_spec", "link_product"):
            if event.type() in (QEvent.DragEnter, QEvent.DragMove):
                if self.image_paths_from_mime_data(event.mimeData()):
                    self.set_chip_drop_hover(watched, True)
                    event.setDropAction(Qt.MoveAction if event.mimeData().hasFormat(MaterialImageList.INTERNAL_MOVE_MIME) else Qt.CopyAction)
                    event.accept()
                    return True
                self.clear_active_drop_hover()
            if event.type() == QEvent.DragLeave:
                self.clear_active_drop_hover()
                return False
            if event.type() == QEvent.Drop:
                self.clear_active_drop_hover()
                paths = self.image_paths_from_mime_data(event.mimeData())
                target_type = watched.property("materialDropTarget")
                if target_type == "product_spec":
                    spec = getattr(watched, "material_spec", None)
                    moved = bool(paths and spec and self.move_images_to_spec(paths, spec))
                else:
                    item = getattr(watched, "material_link_item", None)
                    source_column = self.internal_drag_source_column_from_mime(event.mimeData())
                    moved = bool(paths and item and self.move_images_to_link_product(paths, item, source_column))
                if moved:
                    event.setDropAction(Qt.MoveAction if event.mimeData().hasFormat(MaterialImageList.INTERNAL_MOVE_MIME) else Qt.CopyAction)
                    event.accept()
                    return True
        return super().eventFilter(watched, event)

    def image_paths_from_mime_data(self, mime_data):
        paths = []
        if mime_data.hasUrls():
            paths.extend(url.toLocalFile() for url in mime_data.urls() if url.isLocalFile())
        if mime_data.hasText():
            paths.extend(self.paths_from_text(mime_data.text()))
        result = []
        for path in paths:
            path = os.path.abspath(path)
            if self.is_image_file(path) and path not in result:
                result.append(path)
        return result

    def move_images_to_spec(self, paths, spec):
        if not self.current_category or not self.ensure_root_folder():
            return False
        target_folder = self.sync_spec_folder(self.current_category, spec) or self.spec_folder(self.current_category, spec)
        os.makedirs(target_folder, exist_ok=True)
        moved = 0
        for path in paths:
            if not self.is_image_file(path):
                continue
            if os.path.abspath(os.path.dirname(path)) == os.path.abspath(target_folder):
                continue
            filename = self.product_material_filename(target_folder, os.path.basename(path))
            dest = self.unique_destination_path(target_folder, filename)
            try:
                os.replace(path, dest)
                moved += 1
            except Exception:
                try:
                    shutil.move(path, dest)
                    moved += 1
                except Exception as e:
                    QMessageBox.warning(self, "移动失败", f"移动图片失败：\n{path}\n\n{e}")
                    break
        if moved:
            self.refresh_current_view()
        return moved > 0

    def load_store_filter(self, preferred_store_id=None):
        self.store_filter_combo.blockSignals(True)
        self.store_filter_combo.clear()
        self.store_filter_combo.addItem("\u5168\u90e8\u5e97\u94fa", None)
        try:
            rows = self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order, id")
        except Exception:
            rows = []
        selected_index = 0
        for store_id, store_name in rows:
            index = self.store_filter_combo.count()
            self.store_filter_combo.addItem(str(store_name or f"\u5e97\u94fa{store_id}"), store_id)
            if preferred_store_id is not None and int(store_id) == int(preferred_store_id):
                selected_index = index
        self.store_filter_combo.setCurrentIndex(selected_index)
        self.link_store_filter_id = self.store_filter_combo.currentData()
        self.store_filter_combo.blockSignals(False)

    def on_store_filter_changed(self):
        if self.library_mode != self.LINK_MODE:
            return
        self.link_store_filter_id = self.store_filter_combo.currentData()
        self.selected_link_combo = ""
        self.selected_link_type = ""
        self.selected_link_product_ids = set()
        self.load_link_data()
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

    def on_link_visibility_changed(self):
        if self.library_mode != self.LINK_MODE:
            return
        self.load_link_data()
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

    def update_link_sort_button_text(self):
        descending = self.link_sort_button.isChecked()
        self.link_sort_button.setText("排序：降序" if descending else "排序：升序")

    def on_link_sort_changed(self, descending):
        self.settings.setValue("link_image_sort_descending", bool(descending))
        self.settings.sync()
        self.update_link_sort_button_text()
        if self.library_mode == self.LINK_MODE:
            self.load_images_for_link_selection()

    def on_psd_visibility_changed(self):
        self.settings.setValue("show_psd_files", self.show_psd_files_checkbox.isChecked())
        self.settings.sync()
        self.flash_psd_toggle_button()
        self.refresh_current_view()

    def flash_psd_toggle_button(self):
        original = self.show_psd_files_checkbox.styleSheet()
        checked_color = "#dff6e8" if self.show_psd_files_checkbox.isChecked() else "#fff3cd"
        self.show_psd_files_checkbox.setStyleSheet(
            original
            + f"""
            QCheckBox {{
                background: {checked_color};
                border-color: #2ecc71;
            }}
            """
        )
        QTimer.singleShot(140, lambda: self.show_psd_files_checkbox.setStyleSheet(original))

    def link_status_suffix(self, item):
        if item.get("deleted"):
            return self.LINK_DELETED_SUFFIX
        return ""

    def strip_link_status_suffix(self, name):
        text = str(name or "")
        for suffix in (self.LINK_DELETED_SUFFIX,):
            if text.endswith(suffix):
                return text[:-len(suffix)], suffix
        return text, ""

    def link_base_parts(self, item):
        store = item.get("store_name") or "未命名店铺"
        combo = item.get("combo") or self.LINK_UNGROUPED
        link_type = item.get("link_type") or self.LINK_NO_TYPE
        code = item.get("code") or "未命名ID"
        return store, combo, link_type, code

    def link_product_folder(self, item, use_status=True):
        root = self.root_folder()
        store, combo, link_type, code = self.link_base_parts(item)
        folder_name = self.safe_folder_name(code + (self.link_status_suffix(item) if use_status else ""), "未命名ID")
        return os.path.join(
            root,
            self.safe_folder_name(store, "未命名店铺"),
            self.safe_folder_name(combo, self.LINK_UNGROUPED),
            self.safe_folder_name(link_type, self.LINK_NO_TYPE),
            folder_name,
        )

    def find_existing_link_folder(self, code):
        root = self.root_folder()
        if not root or not os.path.isdir(root):
            return ""
        target_code = str(code or "")
        for current_root, dirs, _files in os.walk(root):
            for dirname in dirs:
                folder_code, _suffix = self.strip_link_status_suffix(dirname)
                if folder_code == target_code:
                    return os.path.join(current_root, dirname)
        return ""

    def link_folder_mapping_key(self, item):
        db_id = item.get("db_id")
        if db_id is None:
            return ""
        return f"link_folder_path/{self.settings_key(self.LINK_MODE)}/{db_id}"

    def mapped_link_folder_path(self, item):
        key = self.link_folder_mapping_key(item)
        if not key:
            return ""
        value = str(self.settings.value(key, "") or "").strip()
        if not value:
            value = str(self.local_link_folder_paths.get(key, "") or "").strip()
        return value

    def save_link_folder_mapping(self, item, folder):
        key = self.link_folder_mapping_key(item)
        if not key or not folder:
            return
        value = os.path.abspath(folder)
        if os.path.abspath(str(self.local_link_folder_paths.get(key, "") or "")) == value:
            return
        self.local_link_folder_paths[key] = value
        self.settings.setValue(key, value)
        self.settings.sync()

    def merge_or_move_folder(self, source, target):
        if not source or not os.path.isdir(source):
            return
        if os.path.abspath(source) == os.path.abspath(target):
            return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.exists(target):
            try:
                os.rename(source, target)
                return
            except OSError:
                os.makedirs(target, exist_ok=True)
        for name in os.listdir(source):
            src_path = os.path.join(source, name)
            dst_path = os.path.join(target, name)
            if os.path.isdir(src_path):
                self.merge_or_move_folder(src_path, dst_path)
            else:
                dst_path = self.unique_destination_path(target, name) if os.path.exists(dst_path) else dst_path
                try:
                    os.replace(src_path, dst_path)
                except OSError:
                    shutil.copy2(src_path, dst_path)
                    try:
                        os.remove(src_path)
                    except OSError:
                        pass
        try:
            os.rmdir(source)
        except OSError:
            pass

    def ensure_link_product_folder(self, item):
        if not self.ensure_root_folder():
            return ""
        target = self.link_product_folder(item, use_status=True)
        normal = self.link_product_folder(item, use_status=False)
        code = str(item.get("code", "") or "").strip()
        try:
            if not item.get("deleted"):
                old_folder = target if os.path.isdir(target) else ""
                old_folder_from_mapping = bool(old_folder)
                if not old_folder and os.path.isdir(normal):
                    old_folder = normal
                    old_folder_from_mapping = True
                if not old_folder:
                    old_folder = self.mapped_link_folder_path(item)
                    old_folder_from_mapping = bool(old_folder)
                if old_folder and not self.is_link_product_level_folder(old_folder):
                    old_folder = ""
                if not old_folder or not os.path.isdir(old_folder):
                    old_folder = self.find_existing_link_folder(item.get("code", ""))
                    old_folder_from_mapping = False
                if old_folder and not self.is_link_product_level_folder(old_folder, "" if old_folder_from_mapping else code):
                    old_folder = ""
                if old_folder and os.path.abspath(old_folder) != os.path.abspath(target):
                    self.merge_or_move_folder(old_folder, target)
            if (
                os.path.exists(normal)
                and self.is_link_product_level_folder(normal, code)
                and os.path.abspath(normal) != os.path.abspath(target)
                and not os.path.exists(target)
            ):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.rename(normal, target)
            os.makedirs(target, exist_ok=True)
            self.save_link_folder_mapping(item, target)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建链接素材文件夹失败：\n{e}")
            return ""
        return target

    def load_link_data(self):
        if self.store_filter_combo.count() == 0:
            self.load_store_filter(self.link_store_filter_id)
        where = []
        params = []
        if self.link_store_filter_id is not None:
            where.append("p.store_id=?")
            params.append(self.link_store_filter_id)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        try:
            rows = self.db.safe_fetchall(
                f"""SELECT p.id, COALESCE(p.name, ''), COALESCE(p.title, ''),
                          COALESCE(p.link_type, ''), p.image_data, COALESCE(p.image_path, ''),
                          p.store_id, COALESCE(s.name, ''),
                          COALESCE(lc.name, '')
                   FROM products p
                   LEFT JOIN stores s ON s.id = p.store_id
                   LEFT JOIN link_combinations lc ON lc.id = p.link_combo_id
                   {where_sql}
                   ORDER BY COALESCE(s.sort_order, 0), s.id, COALESCE(lc.sort_order, 0),
                            lc.name, COALESCE(p.link_type, ''), COALESCE(p.sort_order, 0), p.id""",
                tuple(params),
            )
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取链接素材数据失败：\n{e}")
            rows = []
        show_inactive = self.show_inactive_links_checkbox.isChecked()
        items = []
        current_codes = set()
        for db_id, code, title, link_type, image_data, image_path, store_id, store_name, combo in rows:
            code = str(code or db_id or "").strip()
            if not code:
                continue
            current_codes.add(code)
            item = {
                "db_id": db_id,
                "code": code,
                "title": str(title or ""),
                "link_type": str(link_type or "").strip() or self.LINK_NO_TYPE,
                "combo": str(combo or "").strip() or self.LINK_UNGROUPED,
                "store_id": store_id,
                "store_name": str(store_name or "").strip() or "未命名店铺",
                "image_data": image_data,
                "image_path": str(image_path or "").strip(),
                "deleted": False,
            }
            items.append(item)
        if show_inactive and self.root_folder():
            items.extend(self.scan_deleted_link_folders(current_codes))
        self.link_items = items
        self.link_combos = sorted({item["combo"] for item in items}, key=lambda value: value.lower())

    def rename_link_folder_to_status(self, item):
        target = self.link_product_folder(item, use_status=True)
        normal = self.link_product_folder(item, use_status=False)
        try:
            if os.path.isdir(normal) and os.path.abspath(normal) != os.path.abspath(target) and not os.path.exists(target):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.rename(normal, target)
        except Exception:
            pass

    def scan_deleted_link_folders(self, current_codes):
        root = self.root_folder()
        if not root or not os.path.isdir(root):
            return []
        items = []
        for store_name in sorted(os.listdir(root), key=lambda value: value.lower()):
            store_path = os.path.join(root, store_name)
            if not os.path.isdir(store_path):
                continue
            for combo in sorted(os.listdir(store_path), key=lambda value: value.lower()):
                combo_path = os.path.join(store_path, combo)
                if not os.path.isdir(combo_path):
                    continue
                for link_type in sorted(os.listdir(combo_path), key=lambda value: value.lower()):
                    type_path = os.path.join(combo_path, link_type)
                    if not os.path.isdir(type_path):
                        continue
                    for folder_name in sorted(os.listdir(type_path), key=lambda value: value.lower()):
                        folder_path = os.path.join(type_path, folder_name)
                        if not os.path.isdir(folder_path):
                            continue
                        code, suffix = self.strip_link_status_suffix(folder_name)
                        if code in current_codes:
                            continue
                        target_name = code + self.LINK_DELETED_SUFFIX
                        target_path = os.path.join(type_path, self.safe_folder_name(target_name, "未命名ID"))
                        if suffix != self.LINK_DELETED_SUFFIX and not os.path.exists(target_path):
                            try:
                                os.rename(folder_path, target_path)
                                folder_path = target_path
                            except Exception:
                                pass
                        if self.link_store_filter_id is not None:
                            matched = False
                            for idx in range(self.store_filter_combo.count()):
                                if self.store_filter_combo.itemData(idx) == self.link_store_filter_id:
                                    matched = self.safe_folder_name(self.store_filter_combo.itemText(idx), "未命名店铺") == store_name
                                    break
                            if not matched:
                                continue
                        items.append({
                            "db_id": None,
                            "code": code,
                            "title": "",
                            "link_type": link_type or self.LINK_NO_TYPE,
                            "combo": combo or self.LINK_UNGROUPED,
                            "store_id": None,
                            "store_name": store_name or "未命名店铺",
                            "image_data": None,
                            "deleted": True,
                            "folder_path": folder_path,
                        })
        return items

    def filtered_link_items(self, keyword):
        if not keyword:
            return list(self.link_items)
        result = []
        for item in self.link_items:
            values = [
                item.get("combo", ""),
                item.get("link_type", ""),
                item.get("code", ""),
                item.get("title", ""),
                item.get("store_name", ""),
            ]
            if self.search_text_matches(keyword, *values):
                result.append(item)
        return result

    def create_link_id_chip(self, item):
        text = item.get("code", "")
        if item.get("deleted"):
            text += self.LINK_DELETED_SUFFIX
        store_name = str(item.get("store_name") or "").strip()
        if store_name:
            text = f"{store_name}\n{text}"
        button = DeletedLinkToolButton() if item.get("deleted") else QToolButton()
        self.remove_tab_focus(button)
        button.setCheckable(True)
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(64, 64))
        button.setMinimumSize(QSize(106, 96))
        button.setMaximumWidth(152)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.setStyleSheet(
            """
            QToolButton {
                background-color: #F7E8D5;
                color: #1f2d3d;
                border: 1px solid #b8c2cc;
                border-radius: 8px;
                padding: 5px 6px;
                font-weight: bold;
            }
            QToolButton:hover {
                border-color: #3498db;
            }
            QToolButton:checked {
                border: 2px solid #2f80ed;
                padding: 4px 5px;
            }
            """
        )
        pixmap = QPixmap()
        image_data = item.get("image_data")
        if image_data:
            pixmap.loadFromData(bytes(image_data))
        if pixmap.isNull():
            image_path = item.get("image_path", "")
            if image_path and os.path.exists(image_path):
                pixmap = QPixmap(image_path)
        if pixmap.isNull() and item.get("deleted"):
            image_path = self.deleted_link_preview_image_path(item)
            if image_path:
                pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            button.setIcon(QIcon(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        button.setToolTip(item.get("title") or item.get("code", ""))
        self.configure_link_product_drop_target(button, item)
        return button

    def deleted_link_preview_image_path(self, item):
        folder = item.get("folder_path") or ""
        images = self.sorted_image_files(folder, show_psd=False)
        if not images:
            return ""
        main_image = next((path for path in images if self.link_image_column_for_path(path) == "main"), "")
        return main_image or images[0]

    def select_link_combo(self, combo):
        if self.library_mode != self.LINK_MODE:
            return
        if not self.ensure_root_folder():
            return
        self.clear_search_input()
        if self.selected_link_combo == combo:
            self.selected_link_combo = ""
            self.selected_link_type = ""
            self.selected_link_product_ids = set()
        else:
            self.selected_link_combo = combo
            self.selected_link_type = ""
            self.selected_link_product_ids = set()
        self.refresh_link_bubbles()
        self.schedule_load_images_for_link_selection()

    def select_link_type(self, link_type):
        if self.library_mode != self.LINK_MODE:
            return
        if not self.ensure_root_folder():
            return
        self.clear_search_input()
        if self.selected_link_type == link_type:
            self.selected_link_type = ""
            self.selected_link_product_ids = set()
        else:
            self.selected_link_type = link_type
            self.selected_link_product_ids = set()
        self.refresh_link_bubbles()
        self.schedule_load_images_for_link_selection()

    def toggle_link_product(self, item):
        if self.library_mode != self.LINK_MODE:
            return
        key = self.link_item_key(item)
        if not key:
            return
        search_cleared = self.clear_search_input()
        old_selection = set(self.selected_link_product_ids)
        ctrl_pressed = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if ctrl_pressed:
            if key in self.selected_link_product_ids:
                self.selected_link_product_ids.remove(key)
            else:
                self.selected_link_product_ids.add(key)
        elif self.selected_link_product_ids == {key}:
            self.selected_link_product_ids = set()
        else:
            self.selected_link_product_ids = {key}
        self.update_link_product_button_checks()
        if not self.ensure_link_product_folder(item):
            self.selected_link_product_ids = old_selection
            self.update_link_product_button_checks()
            return
        if search_cleared:
            self.refresh_link_bubbles()
        else:
            self.update_link_product_button_checks()
        self.schedule_load_images_for_link_selection()

    def update_link_product_button_checks(self):
        for key, button in getattr(self, "link_product_buttons", {}).items():
            button.blockSignals(True)
            button.setChecked(key in self.selected_link_product_ids)
            button.blockSignals(False)

    def schedule_load_images_for_link_selection(self):
        self.link_image_load_generation += 1
        generation = self.link_image_load_generation
        self.clear_link_image_lists()
        self.image_count_label.setText("正在切换链接素材...")
        QTimer.singleShot(0, lambda: self.load_images_for_link_selection_if_current(generation))

    def load_images_for_link_selection_if_current(self, generation):
        if generation != self.link_image_load_generation:
            return
        self.load_images_for_link_selection()

    def refresh_link_bubbles(self):
        if self.library_mode != self.LINK_MODE:
            return
        self.apply_mode_visibility()
        showing_combo = not self.selected_link_combo
        showing_type = bool(self.selected_link_combo) and not self.selected_link_type
        showing_product = bool(self.selected_link_combo and self.selected_link_type)
        self.category_scroll.setVisible(showing_combo)
        self.spec_scroll.setVisible(showing_type)
        self.link_product_scroll.setVisible(showing_product)
        self.back_button.setEnabled(bool(self.selected_link_combo))
        if showing_product:
            self.current_label.setText("\u94fe\u63a5\u7c7b\u578b\uff1a" + str(self.selected_link_type))
        elif showing_type:
            self.current_label.setText("\u94fe\u63a5\u7ec4\u5408\uff1a" + str(self.selected_link_combo))
        else:
            self.current_label.setText("\u94fe\u63a5\u7ec4\u5408")

        self.clear_layout(self.category_layout)
        self.clear_layout(self.spec_layout)
        self.clear_layout(self.link_product_layout)
        self.category_buttons = {}
        self.spec_buttons = {}
        self.link_product_buttons = {}
        self.link_products = []

        keyword = self.search_input.text().strip().lower()
        visible_items = self.filtered_link_items(keyword)
        if showing_combo:
            combos = sorted({item["combo"] for item in visible_items}, key=lambda value: value.lower())
            for combo in combos:
                button = self.create_chip(combo, "#DDEBF7")
                button.setChecked(False)
                button.clicked.connect(lambda _checked=False, value=combo: self.select_link_combo(value))
                self.category_layout.addWidget(button)
                self.category_buttons[combo] = button
        elif showing_type:
            type_items = [
                item for item in visible_items
                if item["combo"] == self.selected_link_combo
            ]
            types = sorted({item["link_type"] for item in type_items}, key=lambda value: value.lower())
            for link_type in types:
                button = self.create_chip(link_type, "#E8F4EA")
                button.setChecked(False)
                button.clicked.connect(lambda _checked=False, value=link_type: self.select_link_type(value))
                self.spec_layout.addWidget(button)
                self.spec_buttons[link_type] = button
        elif showing_product:
            self.link_products = [
                item for item in visible_items
                if item["combo"] == self.selected_link_combo and item["link_type"] == self.selected_link_type
            ]
            for item in self.link_products:
                button = self.create_link_id_chip(item)
                key = self.link_item_key(item)
                button.setChecked(key in self.selected_link_product_ids)
                button.clicked.connect(lambda _checked=False, value=item: self.toggle_link_product(value))
                self.link_product_layout.addWidget(button)
                self.link_product_buttons[key] = button

        if not self.link_items:
            self.image_count_label.setText("当前没有可显示的链接素材")
        self.schedule_chip_layout_refresh()

    def select_category(self, category):
        if self.library_mode != self.PRODUCT_MODE:
            return
        root = self.ensure_root_folder()
        if not root:
            return
        self.clear_search_input()
        self.current_category = category
        self.current_spec = None
        self.selected_category_labels = {category.get("label", "")}
        self.selected_spec_names = set()
        try:
            self.load_specs(category.get("label", ""))
            self.sync_category_folder(category, self.specs)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建商品类型文件夹失败：\n{e}")
            return
        self.refresh_spec_bubbles()
        self.load_images_for_category()
        self.schedule_deferred_spec_sync(category, self.specs)

    def toggle_category(self, category):
        if self.library_mode != self.PRODUCT_MODE:
            return
        if not self.ensure_root_folder():
            return
        self.clear_search_input()
        label = category.get("label", "")
        ctrl_pressed = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if ctrl_pressed:
            if label in self.selected_category_labels:
                self.selected_category_labels.remove(label)
            else:
                self.selected_category_labels.add(label)
        else:
            self.selected_category_labels = {label}
        self.selected_spec_names = set()
        if len(self.selected_category_labels) == 1:
            selected_label = next(iter(self.selected_category_labels))
            selected_category = next((item for item in self.categories if item.get("label") == selected_label), category)
            self.current_category = selected_category
            self.current_spec = None
            try:
                self.load_specs(selected_label)
                self.sync_category_folder(selected_category, self.specs)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"创建商品类型文件夹失败：\n{e}")
                return
            self.refresh_spec_bubbles()
            self.load_images_for_category()
            self.schedule_deferred_spec_sync(selected_category, self.specs)
        else:
            self.current_category = None
            self.current_spec = None
            self.refresh_category_bubbles()
            self.load_images_for_selected_categories()

    def select_spec(self, spec):
        if self.library_mode != self.PRODUCT_MODE:
            return
        if not self.current_category:
            return
        if not self.ensure_root_folder():
            return
        self.clear_search_input()
        self.current_spec = spec
        self.selected_spec_names = {spec.get("name", "")}
        try:
            os.makedirs(self.spec_folder(self.current_category, spec), exist_ok=True)
            self.sync_spec_folder(self.current_category, spec)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建规格文件夹失败：\n{e}")
            return
        self.refresh_spec_bubbles()
        self.load_images_for_spec()

    def toggle_spec(self, spec):
        if self.library_mode != self.PRODUCT_MODE:
            return
        if not self.current_category:
            return
        if not self.ensure_root_folder():
            return
        self.clear_search_input()
        name = spec.get("name", "")
        ctrl_pressed = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if ctrl_pressed:
            if name in self.selected_spec_names:
                self.selected_spec_names.remove(name)
            else:
                self.selected_spec_names.add(name)
                try:
                    os.makedirs(self.spec_folder(self.current_category, spec), exist_ok=True)
                    self.sync_spec_folder(self.current_category, spec)
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"创建规格文件夹失败：\n{e}")
                    return
        elif self.selected_spec_names == {name}:
            self.selected_spec_names.remove(name)
        else:
            self.selected_spec_names = {name}
            try:
                os.makedirs(self.spec_folder(self.current_category, spec), exist_ok=True)
                self.sync_spec_folder(self.current_category, spec)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"创建规格文件夹失败：\n{e}")
                return
        self.current_spec = spec if self.selected_spec_names else None
        self.refresh_spec_bubbles()
        if self.selected_spec_names:
            self.load_images_for_selected_specs()
        else:
            self.load_images_for_category()

    def back_to_categories(self):
        if self.library_mode == self.LINK_MODE and not self.current_category:
            if self.selected_link_product_ids:
                self.selected_link_product_ids = set()
            elif self.selected_link_type:
                self.selected_link_type = ""
            elif self.selected_link_combo:
                self.selected_link_combo = ""
            self.refresh_link_bubbles()
            self.load_images_for_link_selection()
            return
        self.current_category = None
        self.current_spec = None
        self.selected_spec_names = set()
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.clear_product_image_list()
        if self.selected_category_labels:
            self.load_images_for_selected_categories()
        else:
            self.image_count_label.setText("请选择商品类型")
            self.update_attribute_sidebar()
        self.refresh_category_bubbles()

    def refresh_current_view(self):
        self.refresh_root_label()
        if self.library_mode == self.LINK_MODE:
            self.load_link_data()
            self.refresh_link_bubbles()
            self.load_images_for_link_selection()
            return
        self.load_categories(refresh=False)
        if self.current_category:
            category_label = self.current_category.get("label", "")
            refreshed_category = next(
                (category for category in self.categories if category.get("label") == category_label),
                None,
            )
            self.current_category = refreshed_category
            if self.current_category:
                self.load_specs(category_label)
            if self.current_spec:
                current_name = self.current_spec.get("name", "")
                self.current_spec = next(
                    (spec for spec in self.specs if spec.get("name") == current_name),
                    None,
                )
            if self.current_category:
                self.refresh_spec_bubbles()
        if self.current_category and self.selected_spec_names:
            self.load_images_for_selected_specs()
        elif self.current_category:
            self.load_images_for_category()
        elif self.selected_category_labels:
            self.load_images_for_selected_categories()
        else:
            self.refresh_category_bubbles()

    def is_image_file(self, path, show_psd=None):
        if not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        if ext == self.PSD_EXTENSION:
            return self.show_psd_files() if show_psd is None else bool(show_psd)
        return ext in self.IMAGE_EXTENSIONS

    def is_psd_file(self, path):
        return os.path.isfile(path) and os.path.splitext(path)[1].lower() == self.PSD_EXTENSION

    def show_psd_files(self):
        return bool(getattr(self, "show_psd_files_checkbox", None) and self.show_psd_files_checkbox.isChecked())

    def image_natural_sort_key(self, path, white_first=False, mtime=None):
        name = os.path.basename(path)
        stem, _ext = os.path.splitext(name)
        normalized_stem = stem.strip().lower()
        white_rank = 0 if white_first and normalized_stem == "白底图" else 1
        parts = re.split(r"(\d+)", normalized_stem)
        natural_parts = [int(part) if part.isdigit() else part for part in parts]
        if mtime is None:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0
        has_number = any(part.isdigit() for part in parts)
        return (white_rank, -mtime, 0 if has_number else 1, natural_parts, name.lower())

    def sorted_image_files(self, folder, white_first=False, show_psd=None):
        if not folder or not os.path.isdir(folder):
            return []
        try:
            entries = []
            for entry in os.scandir(folder):
                try:
                    if not entry.is_file():
                        continue
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext == self.PSD_EXTENSION and not (self.show_psd_files() if show_psd is None else show_psd):
                        continue
                    if ext not in self.IMAGE_EXTENSIONS:
                        continue
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue
                entries.append((entry.path, mtime))
            entries.sort(key=lambda item: self.image_natural_sort_key(item[0], white_first=white_first, mtime=item[1]))
            return [path for path, _mtime in entries]
        except Exception:
            return []

    def current_product_image_order_key(self):
        if self.library_mode != self.PRODUCT_MODE:
            return ""
        if self.current_category and self.selected_spec_names:
            specs = "|".join(sorted(self.selected_spec_names))
            return f"category:{self.current_category.get('label', '')}|specs:{specs}"
        if self.current_category:
            return f"category:{self.current_category.get('label', '')}"
        if self.selected_category_labels:
            return "categories:" + "|".join(sorted(self.selected_category_labels))
        return "root"

    def product_image_order_settings_key(self, order_key):
        digest = hashlib.md5(str(order_key or "").encode("utf-8")).hexdigest()
        return f"product_image_order/{self.settings_key(self.PRODUCT_MODE)}/{digest}"

    def product_image_order_store_path(self):
        root = self.root_folder()
        if not root:
            return ""
        return os.path.join(root, ".shop_material_order.json")

    def read_product_image_order_store(self):
        path = self.product_image_order_store_path()
        if not path or not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def write_product_image_order_store(self, data):
        path = self.product_image_order_store_path()
        if not path:
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temp_path = path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
            return True
        except Exception:
            return False

    def load_product_image_order(self, order_key):
        if not order_key:
            return []
        if order_key in self.product_image_order_overrides:
            return self.product_image_order_overrides.get(order_key) or []
        store_data = self.read_product_image_order_store()
        stored_value = store_data.get(order_key)
        raw = ""
        if isinstance(stored_value, list):
            paths = stored_value
        else:
            raw = str(self.settings.value(self.product_image_order_settings_key(order_key), "") or "").strip()
            try:
                paths = json.loads(raw) if raw else []
            except Exception:
                paths = []
        if not raw:
            paths = paths if isinstance(stored_value, list) else paths
        normalized = []
        path_values = paths if isinstance(paths, list) else []
        for path in path_values:
            path = str(path or "").strip()
            if path and path not in normalized:
                normalized.append(path)
        self.product_image_order_overrides[order_key] = normalized
        return normalized

    def save_product_image_order(self, order_key, paths):
        if not order_key:
            return
        clean_paths = []
        for path in paths or []:
            path = str(path or "").strip()
            if path and path not in clean_paths:
                clean_paths.append(path)
        self.product_image_order_overrides[order_key] = clean_paths
        store_data = self.read_product_image_order_store()
        if clean_paths:
            store_data[order_key] = clean_paths
        else:
            store_data.pop(order_key, None)
        self.write_product_image_order_store(store_data)
        key = self.product_image_order_settings_key(order_key)
        if clean_paths:
            self.settings.setValue(key, json.dumps(clean_paths, ensure_ascii=False))
        else:
            self.settings.remove(key)
        self.settings.sync()

    def remember_product_image_order(self, image_list=None):
        if self.library_mode != self.PRODUCT_MODE:
            return
        image_list = image_list or self.image_list
        key = self.current_product_image_order_key()
        if not key:
            return
        paths = []
        for index in range(image_list.count()):
            item = image_list.item(index)
            path = self.image_path_from_item(item)
            if path and path not in paths:
                paths.append(path)
        if paths:
            self.save_product_image_order(key, paths)

    def apply_product_image_order(self, images):
        if self.library_mode != self.PRODUCT_MODE:
            return images
        key = self.current_product_image_order_key()
        order = self.load_product_image_order(key)
        if not order:
            return images
        rank = {os.path.abspath(path): index for index, path in enumerate(order)}
        return sorted(
            images,
            key=lambda item: (
                1 if os.path.abspath(item[0]) in rank else 0,
                rank.get(os.path.abspath(item[0]), len(rank)),
            ),
        )

    def update_product_image_order_path(self, old_path, new_path):
        old_abs = os.path.abspath(old_path)
        new_abs = os.path.abspath(new_path)
        for key, paths in list(self.product_image_order_overrides.items()):
            changed = False
            updated = []
            for path in paths:
                if os.path.abspath(path) == old_abs:
                    updated.append(new_abs)
                    changed = True
                else:
                    updated.append(path)
            if changed:
                self.save_product_image_order(key, updated)

    def load_images_for_category(self):
        self.clear_product_image_list()
        if not self.current_category:
            return
        images = self.images_for_category(self.current_category)
        images = self.apply_product_image_order(images)
        self.add_image_items(images)
        self.image_count_label.setText(f"\u5f53\u524d\u7c7b\u578b\u56fe\u7247\uff1a{len(images)} \u5f20")
        self.update_attribute_sidebar()

    def load_images_for_selected_categories(self):
        self.clear_product_image_list()
        images = []
        for category in self.categories:
            if category.get("label") not in self.selected_category_labels:
                continue
            self.load_specs(category.get("label", ""))
            category_images = self.images_for_category(category)
            for path, name in category_images:
                images.append((path, os.path.basename(path)))
        images = self.apply_product_image_order(images)
        self.add_image_items(images)
        self.image_count_label.setText(f"\u5f53\u524d\u7c7b\u578b\u56fe\u7247\uff1a{len(images)} \u5f20")
        self.update_attribute_sidebar()

    def images_for_category(self, category, specs=None):
        source_specs = specs if specs is not None else self.specs
        self.sync_category_folder(category, source_specs)
        folder = self.category_folder(category)
        images = [(path, os.path.basename(path)) for path in self.sorted_image_files(folder, white_first=True)]
        for spec in source_specs:
            self.sync_spec_folder(category, spec)
            for spec_folder in self.spec_image_folders(category, spec):
                for path in self.sorted_image_files(spec_folder, white_first=True):
                    images.append((path, os.path.basename(path)))
        return images

    def load_images_for_selected_specs(self):
        self.clear_product_image_list()
        if not self.current_category:
            return
        selected_specs = [spec for spec in self.specs if spec.get("name") in self.selected_spec_names]
        self.sync_category_folder(self.current_category, self.specs)
        images = []
        for spec in selected_specs:
            self.sync_spec_folder(self.current_category, spec)
            for folder in self.spec_image_folders(self.current_category, spec):
                for path in self.sorted_image_files(folder, white_first=True):
                    images.append((path, os.path.basename(path)))
        images = self.apply_product_image_order(images)
        self.add_image_items(images)
        self.image_count_label.setText(f"\u5f53\u524d\u7c7b\u578b\u56fe\u7247\uff1a{len(images)} \u5f20")
        self.update_attribute_sidebar()

    def load_images_for_spec(self):
        self.clear_product_image_list()
        if not self.current_category or not self.current_spec:
            return
        self.sync_category_folder(self.current_category, self.specs)
        self.sync_spec_folder(self.current_category, self.current_spec)
        images = []
        for folder in self.spec_image_folders(self.current_category, self.current_spec):
            images.extend((path, os.path.basename(path)) for path in self.sorted_image_files(folder, white_first=True))
        images = self.apply_product_image_order(images)
        self.add_image_items(images)
        self.image_count_label.setText(f"\u5f53\u524d\u7c7b\u578b\u56fe\u7247\uff1a{len(images)} \u5f20")
        self.update_attribute_sidebar()

    def link_item_key(self, item):
        if not item:
            return ""
        db_id = item.get("db_id")
        if db_id is not None:
            return f"db:{db_id}"
        return "folder:" + "|".join(
            str(item.get(key, "") or "")
            for key in ("store_name", "combo", "link_type", "code")
        )

    def normalize_selected_link_product_keys(self):
        if not self.selected_link_product_ids:
            return
        valid_keys = {self.link_item_key(item) for item in self.link_items}
        normalized = set()
        for value in set(self.selected_link_product_ids):
            if value in valid_keys:
                normalized.add(value)
                continue
            match = next((
                item for item in self.link_items
                if item.get("code") == value
                and (not self.selected_link_combo or item.get("combo") == self.selected_link_combo)
                and (not self.selected_link_type or item.get("link_type") == self.selected_link_type)
                and (self.link_store_filter_id is None or item.get("store_id") == self.link_store_filter_id)
            ), None)
            if match:
                normalized.add(self.link_item_key(match))
        self.selected_link_product_ids = normalized

    def selected_link_items(self):
        if not self.selected_link_product_ids:
            return []
        selected = []
        for item in self.link_items:
            if self.link_item_key(item) in self.selected_link_product_ids:
                selected.append(item)
        return selected

    def link_image_column_prefix(self, column_key):
        return {"main": "主图", "detail": "详情页", "sku": "SKU"}.get(column_key, "")

    def editable_link_material_name(self, text, link_prefix):
        text = str(text or "").strip()
        link_prefix = str(link_prefix or "").strip()
        if " / " in text:
            text = text.rsplit(" / ", 1)[-1].strip()
        stem, ext = os.path.splitext(text)
        if ext.lower() in self.IMAGE_EXTENSIONS:
            text = stem
        prefixes = [prefix for prefix in (link_prefix, "主图", "详情页", "SKU", "??", "???") if prefix]
        for prefix in prefixes:
            if text.startswith(prefix + "【") and text.endswith("】"):
                inner = text[len(prefix) + 1:-1].strip()
                return inner or text
            if text.startswith(prefix + "?") and text.endswith("?"):
                inner = text[len(prefix) + 1:-1].strip()
                return inner or text
        return text

    def link_material_stem_from_edit(self, edited_text, link_prefix):
        link_prefix = str(link_prefix or "").strip()
        raw_text = self.editable_link_material_name(edited_text, link_prefix)
        safe_inner = self.safe_folder_name(raw_text, "未命名")
        return f"{link_prefix}【{safe_inner}】" if link_prefix else safe_inner

    def link_material_filename(self, original_filename, column_key):
        prefix = self.link_image_column_prefix(column_key)
        if not prefix:
            return original_filename
        stem, ext = os.path.splitext(os.path.basename(original_filename))
        ext = ext or ".png"
        inner = self.editable_link_material_name(stem, prefix)
        return f"{prefix}【{self.safe_folder_name(inner, '未命名')}】{ext}"

    def link_material_filename_from_edit(self, edited_text, old_path, link_prefix):
        old_ext = os.path.splitext(old_path)[1] or ".png"
        stem, typed_ext = os.path.splitext(str(edited_text or "").strip())
        if typed_ext.lower() in self.IMAGE_EXTENSIONS:
            return self.link_material_stem_from_edit(stem, link_prefix) + typed_ext
        return self.link_material_stem_from_edit(edited_text, link_prefix) + old_ext

    def link_image_column_setting_key(self, path):
        normalized_path = os.path.normcase(os.path.abspath(path))
        digest = hashlib.md5(normalized_path.encode("utf-8")).hexdigest()
        return f"link_image_column/{self.settings_key(self.LINK_MODE)}/{digest}"

    def saved_link_image_column(self, path):
        key = self.link_image_column_setting_key(path)
        value = str(self.settings.value(key, "") or "").strip()
        return value if value in ("main", "detail", "sku") else ""

    def save_link_image_column(self, path, column_key):
        if column_key not in ("main", "detail", "sku"):
            return
        normalized_path = os.path.abspath(path)
        self.link_image_column_overrides[normalized_path] = column_key
        self.settings.setValue(self.link_image_column_setting_key(normalized_path), column_key)
        self.settings.sync()

    def remove_saved_link_image_column(self, path):
        normalized_path = os.path.abspath(path)
        self.link_image_column_overrides.pop(normalized_path, None)
        self.settings.remove(self.link_image_column_setting_key(normalized_path))
        self.settings.sync()

    def classify_link_image_name(self, filename):
        stem, _ext = os.path.splitext(os.path.basename(filename))
        normalized = stem.strip()
        for column_key, prefix in (("main", "主图"), ("detail", "详情页"), ("sku", "SKU"), ("main", "??"), ("detail", "???")):
            if normalized.startswith(prefix + "【") and normalized.endswith("】"):
                return column_key, 0
            if normalized.startswith(prefix + "?") and normalized.endswith("?"):
                return column_key, 0
            match = re.match(rf"^{re.escape(prefix)}\s*(?:[（(\[_-]?\s*(\d+)\s*[）)\]]?)?$", normalized, re.IGNORECASE)
            if match:
                return column_key, int(match.group(1) or 0)
        return "main", 0

    def is_link_auto_named_file(self, filename):
        stem, _ext = os.path.splitext(os.path.basename(filename))
        prefixes = ("主图", "详情页", "SKU", "??", "???")
        return any(
            (stem.strip().startswith(prefix + "【") and stem.strip().endswith("】"))
            or (stem.strip().startswith(prefix + "?") and stem.strip().endswith("?"))
            for prefix in prefixes
        )

    def link_column_sort_key(self, path):
        name = os.path.basename(path).lower()
        _column, number = self.classify_link_image_name(name)
        natural = tuple((0, int(part)) if part.isdigit() else (1, part) for part in re.split(r"(\d+)", name))
        if number > 0:
            return (0, -number if self.link_sort_button.isChecked() else number, natural)
        return (1, 0, natural)

    def link_image_column_for_path(self, path):
        normalized_path = os.path.abspath(path)
        override = self.link_image_column_overrides.get(normalized_path)
        if override in ("main", "detail", "sku") and os.path.exists(normalized_path):
            return override
        saved = self.saved_link_image_column(normalized_path)
        if saved:
            self.link_image_column_overrides[normalized_path] = saved
            return saved
        column_key, _number = self.classify_link_image_name(os.path.basename(path))
        return column_key if column_key in ("main", "detail", "sku") else "main"

    def next_link_column_index(self, folder, column_key):
        if column_key not in ("main", "detail", "sku") or not os.path.isdir(folder):
            return 1
        used = set()
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not self.is_image_file(path):
                continue
            detected_column, number = self.classify_link_image_name(name)
            if detected_column == column_key and number > 0:
                used.add(number)
        index = 1
        while index in used:
            index += 1
        return index

    def allocate_link_column_index(self, folder, column_key, allocation_state):
        key = (os.path.abspath(folder), column_key)
        if key not in allocation_state:
            used = set()
            if os.path.isdir(folder):
                for name in os.listdir(folder):
                    path = os.path.join(folder, name)
                    if not self.is_image_file(path):
                        continue
                    detected_column, number = self.classify_link_image_name(name)
                    if detected_column == column_key and number > 0:
                        used.add(number)
            allocation_state[key] = used
        used = allocation_state[key]
        index = 1
        while index in used:
            index += 1
        used.add(index)
        return index

    def load_images_for_link_selection(self):
        self.clear_link_image_lists()
        if not self.selected_link_product_ids:
            self.image_count_label.setText("请选择一个或多个商品ID查看链接素材")
            self.update_attribute_sidebar()
            return
        grouped = {"main": [], "detail": [], "sku": []}
        truncated_total = 0
        seen_paths = set()
        for item in self.selected_link_items():
            if not item.get("deleted"):
                self.ensure_link_product_folder(item)
            folder = item.get("folder_path") or self.link_product_folder(item, use_status=True)
            image_files = self.sorted_image_files(folder)
            if len(image_files) > self.LARGE_IMAGE_DISPLAY_THRESHOLD:
                confirm_key = os.path.abspath(folder)
                if confirm_key not in self.large_image_display_confirmed:
                    reply = QMessageBox.question(
                        self,
                        "图片数量过多",
                        f"链接 ID {item.get('code', '')} 的素材文件夹里有 {len(image_files)} 张图片。\n"
                        f"一次加载太多图片可能会卡顿。\n选择“否”将只显示前 {self.LARGE_IMAGE_DISPLAY_THRESHOLD} 张。",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if reply == QMessageBox.Yes:
                        self.large_image_display_confirmed.add(confirm_key)
                    else:
                        truncated_total += len(image_files) - self.LARGE_IMAGE_DISPLAY_THRESHOLD
                        image_files = image_files[:self.LARGE_IMAGE_DISPLAY_THRESHOLD]
                else:
                    pass
            for path in image_files:
                path_key = os.path.normcase(os.path.abspath(path))
                if path_key in seen_paths:
                    continue
                seen_paths.add(path_key)
                name = os.path.splitext(os.path.basename(path))[0]
                if len(self.selected_link_product_ids) != 1:
                    name = f"{item.get('code', '')} / {name}"
                column_key = self.link_image_column_for_path(path)
                grouped[column_key].append((path, name))
        total = 0
        empty_texts = {
            "main": "\u6682\u65e0\u4e3b\u56fe",
            "detail": "\u6682\u65e0\u8be6\u60c5\u9875",
            "sku": "\u6682\u65e0 SKU",
        }
        for column_key, image_list in self.link_image_lists.items():
            images = sorted(grouped.get(column_key, []), key=lambda item: self.link_column_sort_key(item[0]))
            total += len(images)
            self.add_image_items(images, image_list=image_list, empty_text=empty_texts.get(column_key, "\u6682\u65e0\u56fe\u7247"))
        suffix = f"\uff0c\u5df2\u9690\u85cf {truncated_total} \u5f20\u5927\u56fe" if truncated_total else ""
        self.image_count_label.setText(f"\u5f53\u524d\u94fe\u63a5\u7d20\u6750\u56fe\u7247\uff1a{total} \u5f20{suffix}")
        self.update_attribute_sidebar()

    def update_attribute_sidebar(self):
        if not hasattr(self, "attribute_text"):
            return
        if self.library_mode == self.LINK_MODE:
            lines = []
            for item in self.selected_link_items():
                lines.append(f"{item.get('store_name', '')} / {item.get('combo', '')} / {item.get('link_type', '')}")
                lines.append(f"{item.get('code', '')}")
                if item.get("title"):
                    lines.append(f"  {item.get('title')}")
                if item.get("deleted"):
                    lines.append("  宸插垹闄?")
                lines.append("")
            self.attribute_text.setPlainText("\n".join(lines).strip() if lines else "当前没有选中的链接。")
            return
        lines = []
        if self.current_category:
            category_label = self.current_category.get("label", "")
            specs = self.specs
            if self.selected_spec_names:
                specs = [spec for spec in specs if spec.get("name") in self.selected_spec_names]
            lines.extend(self.attribute_lines_for_specs(category_label, specs))
        elif self.selected_category_labels:
            for category in self.categories:
                category_label = category.get("label", "")
                if category_label not in self.selected_category_labels:
                    continue
                specs = self.get_specs_for_category(category_label)
                category_lines = self.attribute_lines_for_specs(category_label, specs)
                if category_lines:
                    if lines:
                        lines.append("")
                    lines.extend(category_lines)
        self.attribute_text.setPlainText("\n".join(lines) if lines else "\u5f53\u524d\u6ca1\u6709\u4ea7\u54c1\u5c5e\u6027")

    def attribute_lines_for_specs(self, category_label, specs):
        lines = []
        for spec in specs:
            attrs = [str(attr or "").strip() for attr in spec.get("attributes", []) if str(attr or "").strip()]
            codes = []
            for code in (spec.get("codes", []) or [spec.get("primary_code", ""), spec.get("code", "")]):
                code = str(code or "").strip()
                if code and code not in codes:
                    codes.append(code)
            spec_name = str(spec.get("name", "") or "").strip()
            if not attrs and not codes and not spec_name:
                continue
            if not lines:
                if codes:
                    lines.append("\u89c4\u683c\u7f16\u7801\uff1a" + "\u3001".join(codes))
                lines.append("\u3010" + str(category_label) + "\u3011")
            elif codes:
                lines.append("\u89c4\u683c\u7f16\u7801\uff1a" + "\u3001".join(codes))
            lines.append(spec_name)
            if attrs:
                lines.append(f"  {attrs[0]}")
        return lines

    def add_image_items(self, images, image_list=None, empty_text="\u5f53\u524d\u6587\u4ef6\u5939\u6ca1\u6709\u53ef\u663e\u793a\u7684\u56fe\u7247"):
        if image_list is None:
            image_list = self.image_list
        image_list.blockSignals(True)
        pending_psd_paths = []
        for path, display_name in images:
            pixmap = self.cached_thumbnail_pixmap(path, image_list.iconSize())
            if pixmap.isNull():
                pixmap = self.load_psd_thumbnail_pixmap(path, image_list.iconSize()) if self.is_psd_file(path) else self.image_placeholder_pixmap(image_list.iconSize())
            item = QListWidgetItem(QIcon(pixmap), display_name)
            item.setSizeHint(image_list.gridSize())
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setData(MaterialImageList.PATH_ROLE, path)
            item.setData(MaterialImageList.ORIGINAL_TEXT_ROLE, display_name)
            prefix = ""
            if " / " in display_name:
                prefix = display_name.rsplit(" / ", 1)[0]
            item.setData(MaterialImageList.PREFIX_ROLE, prefix)
            product_prefix = ""
            if self.library_mode == self.PRODUCT_MODE:
                product_prefix = self.product_material_prefix_for_folder(os.path.dirname(path))
            item.setData(MaterialImageList.PRODUCT_NAME_PREFIX_ROLE, product_prefix)
            link_prefix = ""
            if self.library_mode == self.LINK_MODE:
                link_prefix = self.link_image_column_prefix(self.link_image_column_for_path(path))
            item.setData(MaterialImageList.LINK_NAME_PREFIX_ROLE, link_prefix)
            item.setToolTip(os.path.basename(path))
            image_list.addItem(item)
            if self.is_psd_file(path):
                pending_psd_paths.append(path)
            elif not self.cached_thumbnail_pixmap(path, image_list.iconSize()).isNull():
                pass
            else:
                size = image_list.iconSize()
                self.pending_thumbnail_items.append((self.thumbnail_load_generation, image_list, item, path, size.width(), size.height()))
        if image_list.count() == 0:
            item = QListWidgetItem("当前文件夹没有可显示的图片")
            item.setFlags(Qt.NoItemFlags)
            item.setText(empty_text)
            item.setData(MaterialImageList.EMPTY_ROLE, True)
            item.setSizeHint(QSize(image_list.gridSize().width(), 56))
            image_list.addItem(item)
        image_list.blockSignals(False)
        if self.pending_thumbnail_items and not self.thumbnail_load_timer.isActive():
            self.thumbnail_load_timer.start()
        self.queue_psd_thumbnails(pending_psd_paths, image_list.iconSize())

    def cached_thumbnail_pixmap(self, path, target_size):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return QPixmap()
        cache = self.psd_thumbnail_cache if self.is_psd_file(path) else self.image_thumbnail_cache
        pixmap = cache.get((os.path.abspath(path), mtime, target_size.width(), target_size.height()))
        return pixmap if pixmap and not pixmap.isNull() else QPixmap()

    def image_placeholder_pixmap(self, target_size):
        width = max(48, target_size.width())
        height = max(48, target_size.height())
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#f4f6f8"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#ccd3dc"))
        painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))
        painter.end()
        return pixmap

    def process_pending_thumbnail_items(self):
        if not self.pending_thumbnail_items:
            self.thumbnail_load_timer.stop()
            return
        batch = self.pending_thumbnail_items[:8]
        self.pending_thumbnail_items = self.pending_thumbnail_items[8:]
        for generation, image_list, item, path, width, height in batch:
            if generation != self.thumbnail_load_generation:
                continue
            try:
                if image_list.row(item) < 0 or self.image_path_from_item(item) != path:
                    continue
                pixmap = self.load_thumbnail_pixmap(path, QSize(width, height))
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap))
            except RuntimeError:
                continue
        if not self.pending_thumbnail_items:
            self.thumbnail_load_timer.stop()

    def cancel_pending_thumbnail_loads(self):
        self.thumbnail_load_generation += 1
        self.pending_thumbnail_items = []
        if self.thumbnail_load_timer.isActive():
            self.thumbnail_load_timer.stop()

    def load_thumbnail_pixmap(self, path, target_size):
        if self.is_psd_file(path):
            return self.load_psd_thumbnail_pixmap(path, target_size)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return QPixmap()
        cache_key = (os.path.abspath(path), mtime, target_size.width(), target_size.height())
        cached = self.image_thumbnail_cache.get(cache_key)
        if cached and not cached.isNull():
            return cached
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        original_size = reader.size()
        if original_size.isValid() and target_size.width() > 0 and target_size.height() > 0:
            scaled_size = original_size
            scaled_size.scale(target_size, Qt.KeepAspectRatio)
            reader.setScaledSize(scaled_size)
        image = reader.read()
        if image.isNull():
            return QPixmap()
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return QPixmap()
        if pixmap.width() > target_size.width() or pixmap.height() > target_size.height():
            pixmap = pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_thumbnail_cache[cache_key] = pixmap
        if len(self.image_thumbnail_cache) > 1000:
            self.image_thumbnail_cache.pop(next(iter(self.image_thumbnail_cache)))
        return pixmap

    def load_psd_thumbnail_pixmap(self, path, target_size):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return self.psd_placeholder_pixmap(target_size)
        cache_key = (os.path.abspath(path), mtime, target_size.width(), target_size.height())
        cached = self.psd_thumbnail_cache.get(cache_key)
        if cached and not cached.isNull():
            return cached
        return self.psd_placeholder_pixmap(target_size)

    def queue_psd_thumbnails(self, paths, target_size):
        paths = [os.path.abspath(path) for path in paths or [] if self.is_psd_file(path)]
        if not paths:
            return
        pending = []
        seen = set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            cache_key = (path, mtime, target_size.width(), target_size.height())
            if cache_key not in self.psd_thumbnail_cache:
                pending.append(path)
        if not pending:
            return
        self.psd_thumbnail_generation += 1
        if self.psd_thumbnail_worker and self.psd_thumbnail_worker.isRunning():
            self.psd_thumbnail_worker.request_cancel()
        worker = PsdThumbnailWorker(pending, target_size, self.psd_thumbnail_generation, self)
        self.psd_thumbnail_worker = worker
        worker.thumbnail_ready.connect(self.on_psd_thumbnail_ready)
        worker.finished_batch.connect(self.on_psd_thumbnail_finished)
        worker.start()

    def on_psd_thumbnail_ready(self, generation, path, mtime, width, height, data):
        if generation != self.psd_thumbnail_generation:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data, "PNG") or pixmap.isNull():
            return
        cache_key = (os.path.abspath(path), float(mtime), int(width), int(height))
        self.psd_thumbnail_cache[cache_key] = pixmap
        if len(self.psd_thumbnail_cache) > 200:
            self.psd_thumbnail_cache.pop(next(iter(self.psd_thumbnail_cache)))
        self.update_psd_thumbnail_items(path, pixmap)

    def on_psd_thumbnail_finished(self, generation):
        if generation == self.psd_thumbnail_generation:
            self.psd_thumbnail_worker = None

    def clear_product_image_list(self):
        self.cancel_pending_thumbnail_loads()
        if hasattr(self, "image_list"):
            self.image_list.clear()

    def update_psd_thumbnail_items(self, path, pixmap):
        abs_path = os.path.abspath(path)
        lists = []
        if hasattr(self, "image_list"):
            lists.append(self.image_list)
        lists.extend(list(getattr(self, "link_image_lists", {}).values()))
        prompt_dialog = getattr(self, "prompt_library_dialog", None)
        if prompt_dialog is not None and hasattr(prompt_dialog, "reference_list"):
            lists.append(prompt_dialog.reference_list)
        for image_list in lists:
            for index in range(image_list.count()):
                item = image_list.item(index)
                item_path = self.image_path_from_item(item)
                if item_path and os.path.abspath(item_path) == abs_path:
                    item.setIcon(QIcon(pixmap))

    def psd_placeholder_pixmap(self, target_size):
        width = max(64, target_size.width())
        height = max(64, target_size.height())
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#2b3340"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#8bd3ff"))
        font = QFont("Arial", max(14, min(width, height) // 4))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "PSD")
        painter.end()
        return pixmap

    def clear_link_image_lists(self):
        self.cancel_pending_thumbnail_loads()
        for image_list in getattr(self, "link_image_lists", {}).values():
            image_list.clear()

    def set_active_link_image_column(self, column_key):
        if self.library_mode == self.LINK_MODE and column_key in ("main", "detail", "sku", "uncategorized"):
            self.active_link_image_column = column_key

    def update_active_link_image_column_from_cursor(self):
        if self.library_mode != self.LINK_MODE:
            return
        global_pos = QCursor.pos()
        for column_key, image_list in getattr(self, "link_image_lists", {}).items():
            local_pos = image_list.viewport().mapFromGlobal(global_pos)
            if image_list.viewport().rect().contains(local_pos):
                self.set_active_link_image_column(column_key)
                return

    def image_lists_for_selection(self, source_list=None):
        if source_list is not None:
            return [source_list]
        if self.library_mode == self.LINK_MODE and hasattr(self, "link_image_lists"):
            focused = QApplication.focusWidget()
            for image_list in self.link_image_lists.values():
                if focused is image_list or focused is image_list.viewport():
                    return [image_list]
            return list(self.link_image_lists.values())
        return [self.image_list]

    def copy_selected_images(self, source_list=None, cut=False):
        paths = []
        for image_list in self.image_lists_for_selection(source_list):
            for item in image_list.selectedItems():
                path = item.data(MaterialImageList.PATH_ROLE)
                if path and os.path.exists(path) and path not in paths:
                    paths.append(path)
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        mime.setText("\n".join(paths))
        mime.setData("Preferred DropEffect", (2 if cut else 5).to_bytes(4, "little"))
        QApplication.clipboard().setMimeData(mime)

    def image_path_from_item(self, item):
        if not item:
            return ""
        path = item.data(MaterialImageList.PATH_ROLE)
        return path if path and os.path.exists(path) else ""

    def show_image_context_menu(self, pos):
        image_list = self.sender() if isinstance(self.sender(), MaterialImageList) else self.image_list
        item = image_list.itemAt(pos)
        path = self.image_path_from_item(item)
        if not path:
            return
        menu = QMenu(self)
        open_action = QAction("打开查看", self)
        rename_action = QAction("重命名", self)
        delete_action = QAction("删除", self)
        menu.addAction(open_action)
        menu.addAction(rename_action)
        menu.addSeparator()
        menu.addAction(delete_action)
        open_action.triggered.connect(lambda: self.open_image_viewer(item))
        rename_action.triggered.connect(lambda: self.rename_image_smart(item))
        delete_action.triggered.connect(lambda: self.delete_images(image_list))
        menu.exec_(image_list.viewport().mapToGlobal(pos))

    def open_image_viewer(self, item):
        path = self.image_path_from_item(item)
        if not path:
            return
        if self.is_psd_file(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        dialog = MaterialImageViewerDialog(path, self, self.image_paths_for_viewer(item))
        dialog.exec_()

    def image_paths_for_viewer(self, current_item):
        lists = []
        if hasattr(self, "image_list"):
            lists.append(self.image_list)
        lists.extend(list(getattr(self, "link_image_lists", {}).values()))
        for image_list in lists:
            found = False
            paths = []
            for index in range(image_list.count()):
                item = image_list.item(index)
                path = self.image_path_from_item(item)
                if path and not self.is_psd_file(path):
                    paths.append(path)
                if item is current_item:
                    found = True
            if found and paths:
                return paths
        return [self.image_path_from_item(current_item)]

    def rename_image(self, item):
        path = self.image_path_from_item(item)
        if not path:
            return
        folder = os.path.dirname(path)
        old_name = os.path.basename(path)
        stem, ext = os.path.splitext(old_name)
        product_prefix = ""
        if self.library_mode == self.PRODUCT_MODE:
            product_prefix = self.product_material_prefix_for_folder(folder)
        link_prefix = ""
        if self.library_mode == self.LINK_MODE:
            link_prefix = self.link_image_column_prefix(self.link_image_column_for_path(path))
        if product_prefix:
            input_stem = self.editable_product_material_name(stem, product_prefix)
        elif link_prefix:
            input_stem = self.editable_link_material_name(stem, link_prefix)
        else:
            input_stem = stem
        new_stem, ok = QInputDialog.getText(self, "重命名", "名称", text=input_stem)
        if not ok:
            return
        if product_prefix:
            new_stem = self.product_material_stem_from_edit(folder, new_stem, path)
        elif link_prefix:
            new_stem = self.link_material_stem_from_edit(new_stem, link_prefix)
        else:
            new_stem = self.safe_folder_name(new_stem, stem)
        if not new_stem:
            return
        new_path = os.path.join(folder, new_stem + ext)
        if os.path.abspath(new_path) == os.path.abspath(path):
            return
        if os.path.exists(new_path):
            new_path = self.unique_destination_path(folder, new_stem + ext)
        try:
            os.rename(path, new_path)
        except Exception as e:
            QMessageBox.warning(self, "重命名失败", f"重命名图片失败：\n{e}")
            return
        self.update_product_image_order_path(path, new_path)
        self.remember_link_image_column_after_rename(path, new_path, item)
        self.refresh_after_image_file_change()

    def rename_image_smart(self, item):
        image_list = item.listWidget() if item else self.image_list
        selected_count = len([selected for selected in image_list.selectedItems() if self.image_path_from_item(selected)])
        if selected_count > 1:
            self.batch_rename_images(item)
            return
        self.rename_image(item)

    def handle_image_item_changed(self, item):
        path = self.image_path_from_item(item)
        if not path:
            return
        original_text = item.data(MaterialImageList.ORIGINAL_TEXT_ROLE) or ""
        new_text = str(item.text() or "").strip()
        if not new_text or new_text == original_text:
            return
        prefix = item.data(MaterialImageList.PREFIX_ROLE) or ""
        raw_name = new_text
        if prefix and new_text.startswith(prefix + " / "):
            raw_name = new_text[len(prefix) + 3:]
        elif " / " in new_text:
            raw_name = new_text.rsplit(" / ", 1)[-1]
        folder = os.path.dirname(path)
        old_ext = os.path.splitext(path)[1]
        product_prefix = item.data(MaterialImageList.PRODUCT_NAME_PREFIX_ROLE) or ""
        if self.library_mode == self.PRODUCT_MODE and product_prefix:
            new_filename = self.product_material_filename_from_edit(folder, raw_name, path)
        elif self.library_mode == self.LINK_MODE and item.data(MaterialImageList.LINK_NAME_PREFIX_ROLE):
            new_filename = self.link_material_filename_from_edit(
                raw_name,
                path,
                item.data(MaterialImageList.LINK_NAME_PREFIX_ROLE),
            )
        else:
            stem, typed_ext = os.path.splitext(raw_name)
            if typed_ext.lower() in self.IMAGE_EXTENSIONS:
                new_filename = self.safe_folder_name(stem, "素材") + typed_ext
            else:
                new_filename = self.safe_folder_name(raw_name, "素材") + old_ext
        new_path = os.path.join(folder, new_filename)
        if os.path.abspath(new_path) == os.path.abspath(path):
            self.reset_image_item_text(item, original_text)
            return
        if os.path.exists(new_path):
            new_path = self.unique_destination_path(folder, new_filename)
        try:
            os.rename(path, new_path)
        except Exception as e:
            QMessageBox.warning(self, "重命名失败", f"重命名图片失败：\n{e}")
            self.reset_image_item_text(item, original_text)
            return
        self.update_product_image_order_path(path, new_path)
        self.remember_link_image_column_after_rename(path, new_path, item)
        self.refresh_after_image_file_change()

    def remember_link_image_column_after_rename(self, old_path, new_path, item):
        if self.library_mode != self.LINK_MODE:
            return
        source_list = item.listWidget() if item else None
        column_key = getattr(source_list, "material_column_key", "")
        if column_key not in ("main", "detail", "sku"):
            return
        self.remove_saved_link_image_column(old_path)
        self.save_link_image_column(new_path, column_key)

    def refresh_after_image_file_change(self):
        if self.library_mode == self.LINK_MODE:
            self.load_images_for_link_selection()
            return
        self.refresh_current_view()

    def reset_image_item_text(self, item, text):
        image_list = item.listWidget() if item else self.image_list
        image_list.blockSignals(True)
        item.setText(text)
        image_list.blockSignals(False)

    def selected_image_items_ordered_from(self, start_item):
        image_list = start_item.listWidget() if start_item else self.image_list
        selected = [item for item in image_list.selectedItems() if self.image_path_from_item(item)]
        if start_item not in selected:
            selected.insert(0, start_item)
        ordered = []
        for index in range(image_list.count()):
            item = image_list.item(index)
            if item in selected:
                ordered.append(item)
        if start_item in ordered:
            start_index = ordered.index(start_item)
            ordered = ordered[start_index:] + ordered[:start_index]
        return ordered

    def batch_rename_images(self, start_item):
        start_path = self.image_path_from_item(start_item)
        if not start_path:
            return
        items = self.selected_image_items_ordered_from(start_item)
        if len(items) <= 1:
            self.rename_image(start_item)
            return
        base_name, ok = QInputDialog.getText(self, "批量重命名", "基础名称", text=os.path.splitext(os.path.basename(start_path))[0])
        if not ok:
            return
        base_name = self.safe_folder_name(base_name, "未命名")
        if not base_name:
            return
        plan = []
        used_targets = set()
        for index, item in enumerate(items, start=1):
            path = self.image_path_from_item(item)
            if not path:
                continue
            folder = os.path.dirname(path)
            _stem, ext = os.path.splitext(os.path.basename(path))
            target = os.path.join(folder, f"{base_name}（{index}）" + ext)
            normalized_target = os.path.abspath(target)
            if normalized_target in used_targets:
                QMessageBox.warning(self, "批量重命名失败", "目标文件名重复。")
                return
            if os.path.exists(target) and os.path.abspath(target) != os.path.abspath(path):
                target = self.unique_destination_path(folder, os.path.basename(target))
                normalized_target = os.path.abspath(target)
                if normalized_target in used_targets:
                    QMessageBox.warning(self, "批量重命名失败", "目标文件名重复。")
                    return
            used_targets.add(normalized_target)
            plan.append((path, target))
        temp_plan = []
        try:
            for old_path, _target in plan:
                temp_path = old_path + f".renaming_{time.time_ns()}"
                os.rename(old_path, temp_path)
                temp_plan.append((temp_path, old_path))
            for (temp_path, _old_path), (_source_path, target_path) in zip(temp_plan, plan):
                os.rename(temp_path, target_path)
            for source_path, target_path in plan:
                self.update_product_image_order_path(source_path, target_path)
        except Exception as e:
            for temp_path, old_path in reversed(temp_plan):
                if os.path.exists(temp_path) and not os.path.exists(old_path):
                    try:
                        os.rename(temp_path, old_path)
                    except Exception:
                        pass
            QMessageBox.warning(self, "批量重命名失败", f"批量重命名图片失败：\n{e}")
            return
        self.refresh_current_view()

    def delete_images(self, source_list=None):
        paths = []
        for image_list in self.image_lists_for_selection(source_list):
            for item in image_list.selectedItems():
                path = self.image_path_from_item(item)
                if path and path not in paths:
                    paths.append(path)
        if not paths:
            for image_list in self.image_lists_for_selection(source_list):
                current = image_list.currentItem()
                path = self.image_path_from_item(current)
                if path:
                    paths.append(path)
                    break
        if not paths:
            return
        reply = QMessageBox.question(
            self,
            "\u786e\u8ba4\u5220\u9664",
            f"\u786e\u5b9a\u5220\u9664\u9009\u4e2d\u7684 {len(paths)} \u5f20\u56fe\u7247\u5417\uff1f\\n\u6b64\u64cd\u4f5c\u4f1a\u5220\u9664\u6587\u4ef6\u672c\u8eab\u3002",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        failed = []
        for path in paths:
            try:
                os.remove(path)
            except Exception as e:
                failed.append(f"{path}\n{e}")
        self.refresh_current_view()
        if failed:
            QMessageBox.warning(self, "\u5220\u9664\u5931\u8d25", "\\n\\n".join(failed[:5]))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            self.paste_images_from_clipboard()
            return
        if event.key() == Qt.Key_Backspace and not self.is_text_editing_focus():
            if self.can_go_back_material_level():
                self.back_to_categories()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.pdf_worker and self.pdf_worker.isRunning():
            QMessageBox.information(self, "提示", "PDF 正在提取，请等待完成后再关闭。")
            event.ignore()
            return
        if self.psd_thumbnail_worker and self.psd_thumbnail_worker.isRunning():
            self.psd_thumbnail_worker.request_cancel()
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

    def is_text_editing_focus(self):
        widget = QApplication.focusWidget()
        return isinstance(widget, (QLineEdit, QTextEdit))

    def can_go_back_material_level(self):
        if self.library_mode == self.LINK_MODE:
            return bool(self.selected_link_combo or self.selected_link_type or self.selected_link_product_ids)
        return bool(self.current_category)

    def pdf_panel_drag_enter(self, event):
        if self.pdf_paths_from_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def pdf_panel_drag_move(self, event):
        if self.pdf_paths_from_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def pdf_panel_drop(self, event):
        paths = self.pdf_paths_from_mime_data(event.mimeData())
        if paths:
            self.set_pending_pdf(paths[0])
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        event.ignore()

    def dragEnterEvent(self, event):
        if self.can_import_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.can_import_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self.import_from_mime_data(event.mimeData()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            return
        super().dropEvent(event)

    def can_import_mime_data(self, mime_data):
        if mime_data.hasFormat(MaterialImageList.INTERNAL_MOVE_MIME):
            return True
        if self.library_mode != self.LINK_MODE and self.pdf_paths_from_mime_data(mime_data):
            return True
        if mime_data.hasImage():
            return True
        if mime_data.hasUrls():
            return any(url.isLocalFile() for url in mime_data.urls())
        if mime_data.hasText():
            return any(os.path.exists(path) for path in self.paths_from_text(mime_data.text()))
        return False

    def target_import_folder(self):
        if not self.ensure_root_folder():
            return ""
        if self.library_mode == self.LINK_MODE:
            item = self.selected_single_link_item()
            if not item:
                QMessageBox.information(self, "提示", "请先选择一个商品ID。")
                return ""
            return self.ensure_link_product_folder(item)
        if not self.current_category:
            QMessageBox.information(self, "提示", "请先选择一个规格。")
            return ""
        folder = self.current_folder()
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建文件夹失败：\n{e}")
            return ""
        return folder

    def selected_single_link_item(self):
        if self.library_mode != self.LINK_MODE or len(self.selected_link_product_ids) != 1:
            return None
        key = next(iter(self.selected_link_product_ids))
        return next((item for item in self.link_items if self.link_item_key(item) == key), None)

    def selected_single_spec(self):
        if not self.current_category or len(self.selected_spec_names) != 1:
            return None
        spec_name = next(iter(self.selected_spec_names))
        for spec in self.specs:
            if spec.get("name") == spec_name:
                return spec
        return None

    def selected_single_spec_folder(self):
        if self.library_mode == self.LINK_MODE:
            item = self.selected_single_link_item()
            return self.ensure_link_product_folder(item) if item else ""
        spec = self.selected_single_spec()
        if not spec:
            return ""
        if not self.ensure_root_folder():
            return ""
        self.sync_spec_folder(self.current_category, spec)
        folder = self.spec_folder(self.current_category, spec)
        os.makedirs(folder, exist_ok=True)
        return folder

    def extract_pending_pdf(self):
        if self.library_mode == self.LINK_MODE:
            QMessageBox.information(self, "提示", "链接素材库模式不支持 PDF 导入。")
            return
        if self.pdf_worker and self.pdf_worker.isRunning():
            QMessageBox.information(self, "提示", "PDF 正在提取中。")
            return
        if not self.pending_pdf_path or not os.path.exists(self.pending_pdf_path):
            QMessageBox.information(self, "提示", "请先选择 PDF 文件。")
            return
        target_folder = self.selected_single_spec_folder()
        if not target_folder:
            QMessageBox.information(self, "提示", "请先选择一个规格后再提取 PDF。")
            return
        page_limit = self.pdf_page_combo.currentData()
        dpi = int(self.pdf_dpi_combo.currentData() or 300)
        base_name = self.safe_folder_name(os.path.splitext(os.path.basename(self.pending_pdf_path))[0], "PDF文件")
        self.pdf_extract_button.setEnabled(False)
        self.pdf_progress.setValue(0)
        self.pdf_status_label.setText(f"正在提取 PDF... {dpi} DPI")
        self.pdf_worker = PdfExtractWorker(self.pending_pdf_path, target_folder, page_limit, base_name, dpi, self)
        self.pdf_worker.progress.connect(self.on_pdf_extract_progress)
        self.pdf_worker.finished_ok.connect(self.on_pdf_extract_finished)
        self.pdf_worker.failed.connect(self.on_pdf_extract_failed)
        self.pdf_worker.finished.connect(lambda: self.pdf_extract_button.setEnabled(True))
        self.pdf_worker.start()

    def on_pdf_extract_progress(self, current, total):
        percent = int(current * 100 / total) if total else 0
        self.pdf_progress.setValue(percent)
        self.pdf_status_label.setText(f"正在提取 {current}/{total} 页")

    def on_pdf_extract_finished(self, saved_paths):
        import_time = time.time()
        for index, path in enumerate(saved_paths):
            try:
                os.utime(path, (import_time - index * 0.001, import_time - index * 0.001))
            except OSError:
                pass
        self.pdf_progress.setValue(100)
        self.pdf_status_label.setText(f"已提取 {len(saved_paths)} 张")
        self.refresh_current_view()

    def on_pdf_extract_failed(self, message):
        self.pdf_status_label.setText("提取失败")
        QMessageBox.warning(self, "PDF 提取失败", message)

    def unique_destination_path(self, folder, filename):
        name, ext = os.path.splitext(filename)
        safe_name = self.safe_folder_name(name, "素材")
        ext = ext or ".png"
        max_stem_length = max(1, 240 - len(os.path.abspath(folder)) - len(os.sep) - len(ext))
        safe_name = safe_name[:max_stem_length].rstrip(" .") or "素材"
        candidate = os.path.join(folder, safe_name + ext)
        index = 2
        while os.path.exists(candidate):
            suffix = f"（{index}）"
            stem = safe_name[:max(1, max_stem_length - len(suffix))].rstrip(" .") or "素材"
            candidate = os.path.join(folder, stem + suffix + ext)
            index += 1
        return candidate

    def product_material_prefix_for_folder(self, folder):
        if self.library_mode != self.PRODUCT_MODE or not folder:
            return ""
        return self.safe_folder_name(os.path.basename(os.path.abspath(folder)), "未命名")

    def editable_product_material_name(self, text, product_prefix):
        text = str(text or "").strip()
        product_prefix = str(product_prefix or "").strip()
        if " / " in text:
            text = text.rsplit(" / ", 1)[-1].strip()
        stem, ext = os.path.splitext(text)
        if ext.lower() in self.IMAGE_EXTENSIONS:
            text = stem
        if product_prefix and text.startswith(product_prefix + "【") and text.endswith("】"):
            inner = text[len(product_prefix) + 1:-1].strip()
            return inner or text
        if product_prefix and text.startswith(product_prefix + "?") and text.endswith("?"):
            inner = text[len(product_prefix) + 1:-1].strip()
            return inner or text
        return text

    def product_material_stem_from_edit(self, folder, edited_text, old_path=None):
        product_prefix = self.product_material_prefix_for_folder(folder)
        raw_text = str(edited_text or "").strip()
        if not product_prefix:
            return self.safe_folder_name(raw_text, "未命名")
        raw_text = self.editable_product_material_name(raw_text, product_prefix)
        safe_inner = self.safe_folder_name(raw_text, "未命名")
        return f"{product_prefix}【{safe_inner}】"

    def product_material_filename(self, folder, original_filename):
        if self.library_mode != self.PRODUCT_MODE:
            return original_filename
        stem, ext = os.path.splitext(os.path.basename(original_filename))
        ext = ext or ".png"
        product_prefix = self.product_material_prefix_for_folder(folder)
        if not product_prefix:
            return self.safe_folder_name(stem, "未命名") + ext
        if stem.startswith(product_prefix + "【") and stem.endswith("】"):
            safe_stem = self.safe_folder_name(stem, "未命名")
        elif stem.startswith(product_prefix + "?") and stem.endswith("?"):
            safe_stem = self.safe_folder_name(stem, "未命名")
        else:
            safe_stem = f"{product_prefix}【{self.safe_folder_name(stem, '未命名')}】"
        return safe_stem + ext

    def product_material_filename_from_edit(self, folder, edited_text, old_path):
        old_ext = os.path.splitext(old_path)[1] or ".png"
        stem, typed_ext = os.path.splitext(str(edited_text or "").strip())
        if typed_ext.lower() in self.IMAGE_EXTENSIONS:
            return self.product_material_stem_from_edit(folder, stem, old_path) + typed_ext
        return self.product_material_stem_from_edit(folder, edited_text, old_path) + old_ext

    def active_link_import_column(self):
        if self.library_mode != self.LINK_MODE:
            return ""
        if self.active_link_image_column in ("main", "detail", "sku"):
            return self.active_link_image_column
        return "main"

    def link_import_filename(self, folder, original_filename, column_key, next_indices):
        if self.library_mode != self.LINK_MODE or column_key not in ("main", "detail", "sku"):
            return original_filename
        if self.is_link_auto_named_file(original_filename):
            return original_filename
        return self.link_material_filename(original_filename, column_key)

    def link_move_filename(self, folder, original_filename, column_key, next_indices):
        if self.library_mode != self.LINK_MODE or column_key not in ("main", "detail", "sku"):
            return original_filename
        current_column, _number = self.classify_link_image_name(original_filename)
        if current_column == column_key:
            return original_filename
        return self.link_material_filename(original_filename, column_key)

    def link_transfer_filename(self, folder, original_filename, column_key, allocation_state):
        if column_key not in ("main", "detail", "sku"):
            return original_filename
        return self.link_material_filename(original_filename, column_key)

    def internal_drag_paths_from_mime(self, mime_data):
        if not mime_data.hasFormat(MaterialImageList.INTERNAL_MOVE_MIME):
            return []
        try:
            text = bytes(mime_data.data(MaterialImageList.INTERNAL_MOVE_MIME)).decode("utf-8")
        except Exception:
            return []
        paths = []
        for line in text.splitlines():
            path = os.path.abspath(line.strip())
            if path and self.is_image_file(path) and path not in paths:
                paths.append(path)
        return paths

    def internal_drag_source_column_from_mime(self, mime_data):
        if not mime_data.hasFormat(MaterialImageList.INTERNAL_SOURCE_COLUMN_MIME):
            return ""
        try:
            column_key = bytes(mime_data.data(MaterialImageList.INTERNAL_SOURCE_COLUMN_MIME)).decode("utf-8").strip()
        except Exception:
            return ""
        return column_key if column_key in ("main", "detail", "sku") else ""

    def move_internal_images_to_link_column(self, paths, source_column=""):
        if self.library_mode != self.LINK_MODE:
            return False
        column_key = self.active_link_image_column
        if column_key not in ("main", "detail", "sku"):
            return bool(paths)
        if source_column == column_key:
            return bool(paths)
        clean_paths = [path for path in (paths or []) if self.is_image_file(path)]
        if len(clean_paths) >= self.BULK_MOVE_CONFIRM_THRESHOLD:
            if not self.confirm_bulk_material_operation(
                "确认移动",
                len(clean_paths),
                "移动到" + self.link_image_column_prefix(column_key),
            ):
                return False
        moved = 0
        next_indices = {}
        for path in clean_paths:
            if not self.is_image_file(path):
                continue
            folder = os.path.dirname(path)
            filename = self.link_move_filename(folder, os.path.basename(path), column_key, next_indices)
            dest = self.unique_destination_path(folder, filename)
            if os.path.abspath(path) == os.path.abspath(dest):
                continue
            try:
                os.rename(path, dest)
                self.remove_saved_link_image_column(path)
                self.save_link_image_column(dest, column_key)
                moved += 1
            except Exception as e:
                QMessageBox.warning(self, "移动失败", f"移动图片失败：\n{path}\n\n{e}")
                return moved > 0
        if moved:
            self.load_images_for_link_selection()
        return bool(paths)

    def move_images_to_link_product(self, paths, item, source_column=""):
        if self.library_mode != self.LINK_MODE or not item:
            return False
        target_folder = item.get("folder_path") or self.ensure_link_product_folder(item)
        if not target_folder:
            return False
        os.makedirs(target_folder, exist_ok=True)
        clean_paths = [path for path in (paths or []) if self.is_image_file(path)]
        if len(clean_paths) >= self.BULK_MOVE_CONFIRM_THRESHOLD:
            source_column_text = self.link_image_column_prefix(source_column) if source_column in ("main", "detail", "sku") else "未分类"
            if not self.confirm_bulk_material_operation(
                "确认移动链接素材",
                len(clean_paths),
                f"\u76ee\u6807 ID\uff1a{item.get('code', '')}\\n\u7d20\u6750\u5206\u7c7b\uff1a{source_column_text}\\n\u76ee\u6807\u6587\u4ef6\u5939\uff1a{target_folder}",
            ):
                return False
        moved = 0
        allocation_state = {}
        for path in clean_paths:
            if not self.is_image_file(path):
                continue
            source_folder = os.path.abspath(os.path.dirname(path))
            if source_folder == os.path.abspath(target_folder):
                continue
            column_key = source_column if source_column in ("main", "detail", "sku") else self.link_image_column_for_path(path)
            filename = self.link_transfer_filename(target_folder, os.path.basename(path), column_key, allocation_state)
            dest = self.unique_destination_path(target_folder, filename)
            try:
                os.replace(path, dest)
                self.remove_saved_link_image_column(path)
                self.save_link_image_column(dest, column_key)
                moved += 1
            except Exception:
                try:
                    shutil.move(path, dest)
                    self.remove_saved_link_image_column(path)
                    self.save_link_image_column(dest, column_key)
                    moved += 1
                except Exception as e:
                    QMessageBox.warning(self, "移动失败", f"移动图片失败：\n{path}\n\n{e}")
                    break
        if moved:
            self.load_images_for_link_selection()
        return moved > 0

    def iter_image_paths(self, path, show_psd=None):
        if self.is_image_file(path, show_psd=show_psd):
            yield path
            return
        if not os.path.isdir(path):
            return
        for root, _dirs, files in os.walk(path):
            for name in sorted(files, key=lambda item: item.lower()):
                candidate = os.path.join(root, name)
                if self.is_image_file(candidate, show_psd=show_psd):
                    yield candidate

    def material_import_target_description(self, folder):
        if self.library_mode == self.LINK_MODE:
            item = self.selected_single_link_item()
            column = self.link_image_column_prefix(self.active_link_import_column()) or "未分类"
            if item:
                return f"\u76ee\u6807 ID\uff1a{item.get('code', '')}\\n\u7d20\u6750\u5206\u7c7b\uff1a{column}\\n\u76ee\u6807\u6587\u4ef6\u5939\uff1a{folder}"
        if self.library_mode == self.PRODUCT_MODE:
            return f"目标文件夹：{folder}"
        return str(folder or "")

    def confirm_bulk_material_operation(self, title, count, target_description):
        reply = QMessageBox.question(
            self,
            title,
            f"\u5373\u5c06\u5904\u7406 {count} \u5f20\u56fe\u7247\u3002\\n\\n{target_description}\\n\\n\u662f\u5426\u7ee7\u7eed\uff1f",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def collect_import_image_paths(self, paths, target_folder):
        collected = []
        seen = set()
        for raw_path in paths or []:
            path = os.path.abspath(raw_path)
            if os.path.isdir(path):
                if self.library_mode == self.LINK_MODE and self.is_dangerous_material_folder_source(path, target_folder):
                    QMessageBox.warning(
                        self,
                        "\u963b\u6b62\u5371\u9669\u5bfc\u5165",
                        f"\u4e0d\u80fd\u628a\u6574\u4e2a\u94fe\u63a5\u7d20\u6750\u5e93\u6216\u4e0a\u5c42\u6587\u4ef6\u5939\u5bfc\u5165\u5230\u5355\u4e2aID\u3002\\n\\n\u6765\u6e90\u6587\u4ef6\u5939\uff1a\\n{path}",
                    )
                    return None
                for image_path in self.iter_image_paths(path):
                    abs_image = os.path.abspath(image_path)
                    if abs_image in seen:
                        continue
                    seen.add(abs_image)
                    collected.append(abs_image)
                    if len(collected) > self.IMPORT_SCAN_LIMIT:
                        QMessageBox.warning(
                            self,
                            "\u56fe\u7247\u67e5\u770b",
                            f"\u672c\u6b21\u5bfc\u5165\u8d85\u8fc7 {self.IMPORT_SCAN_LIMIT} \u5f20\u56fe\u7247\uff0c\u5df2\u505c\u6b62\u3002\\n\u8bf7\u5206\u6279\u5bfc\u5165\u3002",
                        )
                        return None
            elif self.is_image_file(path):
                if path not in seen:
                    seen.add(path)
                    collected.append(path)
        if len(collected) >= self.BULK_IMPORT_CONFIRM_THRESHOLD:
            if not self.confirm_bulk_material_operation(
                "确认批量导入",
                len(collected),
                self.material_import_target_description(target_folder),
            ):
                return None
        return collected

    def mime_prefers_move(self, mime_data):
        if not mime_data or not mime_data.hasFormat("Preferred DropEffect"):
            return False
        try:
            return int.from_bytes(bytes(mime_data.data("Preferred DropEffect"))[:4], "little") == 2
        except Exception:
            return False

    def import_paths(self, paths, move=False):
        folder = self.target_import_folder()
        if not folder:
            return False
        self.update_active_link_image_column_from_cursor()
        image_paths = self.collect_import_image_paths(paths, folder)
        if image_paths is None:
            return False
        if not image_paths:
            return False
        changed = 0
        import_time = time.time()
        column_key = self.active_link_import_column()
        next_indices = {}
        for image_path in image_paths:
            original_name = os.path.basename(image_path)
            if self.library_mode == self.LINK_MODE:
                filename = self.link_import_filename(folder, original_name, column_key, next_indices)
            else:
                filename = self.product_material_filename(folder, original_name)
            if len(os.path.join(os.path.abspath(folder), filename)) > 240:
                filename = original_name
            dest = self.unique_destination_path(folder, filename)
            if os.path.abspath(image_path) == os.path.abspath(dest):
                continue
            try:
                if move:
                    shutil.move(image_path, dest)
                else:
                    shutil.copy2(image_path, dest)
                os.utime(dest, (import_time - changed * 0.001, import_time - changed * 0.001))
                if self.library_mode == self.LINK_MODE and column_key in ("main", "detail", "sku"):
                    if move:
                        self.remove_saved_link_image_column(image_path)
                    self.save_link_image_column(dest, column_key)
                changed += 1
            except Exception as e:
                action = "移动" if move else "导入"
                QMessageBox.warning(self, f"{action}失败", f"{action}图片失败：\n{image_path}\n\n{e}")
                return changed > 0
        if changed:
            self.refresh_current_view()
        return changed > 0

    def import_image_data(self, image_data):
        folder = self.target_import_folder()
        if not folder:
            return False
        self.update_active_link_image_column_from_cursor()
        if image_data is None or not hasattr(image_data, "save") or image_data.isNull():
            return False
        if isinstance(image_data, QPixmap):
            image_data = image_data.toImage()
        if isinstance(image_data, QImage):
            image_data = image_data.convertToFormat(QImage.Format_ARGB32)
        if self.library_mode == self.LINK_MODE:
            column_key = self.active_link_import_column()
            filename = self.link_import_filename(folder, "粘贴图片.png", column_key, {})
        else:
            filename = self.product_material_filename(folder, f"粘贴图片_{time.strftime('%Y%m%d_%H%M%S')}.png")
        dest = self.unique_destination_path(folder, filename)
        if not image_data.save(dest, "PNG"):
            QMessageBox.warning(self, "导入失败", "剪贴板图片保存失败。")
            return False
        if self.library_mode == self.LINK_MODE:
            column_key = self.active_link_import_column()
            if column_key in ("main", "detail", "sku"):
                self.save_link_image_column(dest, column_key)
        self.refresh_current_view()
        return True

    def import_clipboard_image(self):
        return self.import_image_data(QApplication.clipboard().image())

    def import_from_mime_data(self, mime_data):
        internal_paths = self.internal_drag_paths_from_mime(mime_data)
        if internal_paths:
            source_column = self.internal_drag_source_column_from_mime(mime_data)
            return self.move_internal_images_to_link_column(internal_paths, source_column)
        pdf_paths = self.pdf_paths_from_mime_data(mime_data)
        if pdf_paths:
            if self.library_mode == self.LINK_MODE:
                QMessageBox.information(self, "提示", "链接素材库模式不支持 PDF 导入。")
                return False
            self.set_pending_pdf(pdf_paths[0])
            return True
        if mime_data.hasUrls():
            paths = [url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()]
            if paths:
                return self.import_paths(paths, move=self.mime_prefers_move(mime_data))
        if mime_data.hasText():
            paths = self.paths_from_text(mime_data.text())
            if paths:
                return self.import_paths(paths, move=self.mime_prefers_move(mime_data))
        if mime_data.hasImage():
            image = mime_data.imageData()
            if isinstance(image, QPixmap):
                image = image.toImage()
            return self.import_image_data(image)
        return False

    def paste_images_from_clipboard(self, source_list=None):
        if isinstance(source_list, MaterialImageList):
            self.set_active_link_image_column(source_list.material_column_key)
        self.update_active_link_image_column_from_cursor()
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        pdf_paths = self.pdf_paths_from_mime_data(mime_data)
        if pdf_paths:
            self.import_from_mime_data(mime_data)
            return
        paths = []
        if mime_data.hasUrls():
            paths.extend(url.toLocalFile() for url in mime_data.urls() if url.isLocalFile())
        if mime_data.hasText():
            paths.extend(self.paths_from_text(mime_data.text()))
        paths = list(dict.fromkeys(path for path in paths if path))
        if paths:
            self.import_paths(paths, move=self.mime_prefers_move(mime_data))
            return
        image = clipboard.image()
        if not image.isNull() and self.import_image_data(image):
            return
        QMessageBox.information(self, "提示", "剪贴板里没有可导入的图片或本地图片文件。")

    def pdf_paths_from_mime_data(self, mime_data):
        paths = []
        if mime_data.hasUrls():
            paths.extend(url.toLocalFile() for url in mime_data.urls() if url.isLocalFile())
        if mime_data.hasText():
            paths.extend(self.paths_from_text(mime_data.text()))
        return [
            os.path.abspath(path)
            for path in paths
            if path and os.path.isfile(path) and os.path.splitext(path)[1].lower() == ".pdf"
        ]

    def set_pending_pdf(self, pdf_path):
        self.pending_pdf_path = os.path.abspath(pdf_path)
        self.pdf_file_label.setText(os.path.basename(self.pending_pdf_path))
        self.pdf_file_label.setToolTip(self.pending_pdf_path)
        self.pdf_status_label.setText("已选择 PDF，请选择页数后点击提取。")
        self.pdf_progress.setValue(0)

    def paths_from_text(self, text):
        paths = []
        for line in str(text or "").splitlines():
            value = line.strip().strip('"')
            if value.startswith("file:///"):
                value = QUrl(value).toLocalFile()
            if value and os.path.exists(value):
                paths.append(value)
        return paths

    def current_folder(self):
        if self.library_mode == self.LINK_MODE:
            item = self.selected_single_link_item()
            if item:
                return item.get("folder_path") or self.link_product_folder(item, use_status=True)
            root = self.root_folder()
            if self.selected_link_combo and self.selected_link_type:
                base_items = [item for item in self.link_items if item.get("combo") == self.selected_link_combo and item.get("link_type") == self.selected_link_type]
                if base_items:
                    store, combo, link_type, _code = self.link_base_parts(base_items[0])
                    return os.path.join(root, self.safe_folder_name(store, "未命名店铺"), self.safe_folder_name(combo, self.LINK_UNGROUPED), self.safe_folder_name(link_type, self.LINK_NO_TYPE))
            if self.selected_link_combo:
                base_items = [item for item in self.link_items if item.get("combo") == self.selected_link_combo]
                if base_items:
                    store, combo, _link_type, _code = self.link_base_parts(base_items[0])
                    return os.path.join(root, self.safe_folder_name(store, "未命名店铺"), self.safe_folder_name(combo, self.LINK_UNGROUPED))
            return root
        if self.current_category and self.current_spec:
            target = self.spec_folder(self.current_category, self.current_spec)
            for folder in self.spec_image_folders(self.current_category, self.current_spec):
                if self.sorted_image_files(folder):
                    return folder
            return target
        if self.current_category:
            return self.category_folder(self.current_category)
        return self.root_folder()

    def copy_current_folder_path(self):
        if not self.ensure_root_folder():
            return
        folder = self.current_folder()
        if self.library_mode == self.LINK_MODE:
            item = self.selected_single_link_item()
            if item and not item.get("deleted"):
                folder = self.ensure_link_product_folder(item) or folder
        folder = os.path.abspath(folder)
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建文件夹失败：\n{e}")
            return
        QApplication.clipboard().setText(folder)
        if hasattr(self, "image_count_label"):
            self.image_count_label.setText("\u5df2\u590d\u5236\u6587\u4ef6\u5939\u8def\u5f84\uff1a" + str(folder))

    def open_selected_link_for_material_fetch(self):
        if self.library_mode != self.LINK_MODE:
            return
        item = self.selected_single_link_item()
        if not item:
            QMessageBox.information(self, "抓取素材", "请先选择一个商品ID。")
            return
        store_id = item.get("store_id")
        product_id = item.get("code")
        main_app = getattr(self, "main_app", None)
        if not store_id or not main_app or not hasattr(main_app, "_get_pdd_browser_monitor"):
            QMessageBox.information(self, "抓取素材", "没有找到当前链接对应的店铺浏览器。")
            return
        try:
            monitor = main_app._get_pdd_browser_monitor()
            self.show_link_material_fetch_dialog(monitor, item)
        except Exception as e:
            QMessageBox.warning(self, "抓取素材", f"打开店铺浏览器失败：{e}")

    def show_link_material_fetch_dialog(self, monitor, item, status_text=""):
        product_id = item.get("code", "")
        dialog = QDialog(None)
        dialog.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        dialog.setWindowTitle("抓取链接素材")
        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"商品ID：{product_id}\n"
            "先等待自动打开编辑页。页面加载完成后，点击“开始抓取”。"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        status = QLabel(status_text or "准备打开编辑页...")
        status.setWordWrap(True)
        status.setStyleSheet("color: #6c757d;")
        layout.addWidget(status)
        buttons = QDialogButtonBox()
        start_button = buttons.addButton("开始抓取", QDialogButtonBox.AcceptRole)
        open_button = buttons.addButton("重新打开编辑页", QDialogButtonBox.ActionRole)
        cancel_button = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        layout.addWidget(buttons)
        cancel_button.clicked.connect(dialog.reject)

        def open_edit_page():
            open_button.setEnabled(False)
            status.setText("正在打开商品列表、搜索ID并点击编辑...")
            self.image_count_label.setText(f"正在打开编辑页：{product_id}")
            QApplication.processEvents()
            result = monitor.open_product_edit_page(
                product_id,
                expected_store_name=item.get("store_name", ""),
                store_id=item.get("store_id"),
            )
            message = result.get("status", "") if isinstance(result, dict) else ""
            status.setText(message or "打开编辑页完成。")
            open_button.setEnabled(True)
            if not (isinstance(result, dict) and result.get("ok")):
                status.setText((message or "打开编辑页失败。") + "\n你也可以手动进入编辑页后点击“开始抓取”。")

        def start_fetch():
            start_button.setEnabled(False)
            status.setText("正在抓取并下载图片...")
            self.image_count_label.setText(f"正在抓取链接素材：{product_id}")
            QApplication.processEvents()
            result = monitor.fetch_product_material_images(
                product_id,
                expected_store_name=item.get("store_name", ""),
                store_id=item.get("store_id"),
                open_edit=False,
            )
            message = result.get("status", "") if isinstance(result, dict) else ""
            if isinstance(result, dict) and result.get("ok"):
                saved = self.save_fetched_link_material_images(result.get("images", {}), item)
                self.refresh_current_view()
                self.image_count_label.setText(f"抓取完成：已保存 {saved} 张。{message}")
                status.setText(f"抓取完成：已保存 {saved} 张。")
                dialog.accept()
                return
            start_button.setEnabled(True)
            status.setText(message or "抓取失败。")
            QMessageBox.warning(dialog, "抓取素材", message or "抓取失败。")

        open_button.clicked.connect(open_edit_page)
        start_button.clicked.connect(start_fetch)
        dialog.resize(380, 180)
        QTimer.singleShot(0, open_edit_page)
        self.link_material_fetch_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def fetched_material_extension(self, url, content_type=""):
        ext = os.path.splitext(urlparse(str(url or "")).path)[1].lower()
        if ext in self.IMAGE_EXTENSIONS and ext != self.PSD_EXTENSION:
            return ext
        content_type = str(content_type or "").lower()
        if "jpeg" in content_type or "jpg" in content_type:
            return ".jpg"
        if "webp" in content_type:
            return ".webp"
        if "gif" in content_type:
            return ".gif"
        return ".png"

    def download_fetched_material_image(self, row):
        urls = []
        for key in ("url", "fallback_url"):
            url = str((row or {}).get(key) or "").strip()
            if url and url not in urls:
                urls.append(url)
        headers = {"User-Agent": "Mozilla/5.0"}
        last_error = None
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                return url, response.content, response.headers.get("Content-Type", "")
            except Exception as e:
                last_error = e
        raise last_error or RuntimeError("图片下载失败")

    def save_fetched_link_material_images(self, images, item):
        folder = self.ensure_link_product_folder(item)
        if not folder:
            return 0
        os.makedirs(folder, exist_ok=True)
        saved = 0
        import_time = time.time()
        for column_key in ("main", "detail", "sku"):
            prefix = self.link_image_column_prefix(column_key)
            rows = list((images or {}).get(column_key) or [])
            for index, row in enumerate(rows, start=1):
                try:
                    url, content, content_type = self.download_fetched_material_image(row)
                    ext = self.fetched_material_extension(url, content_type)
                    dest = self.unique_destination_path(folder, f"{prefix}【{index:02d}】{ext}")
                    with open(dest, "wb") as file:
                        file.write(content)
                    os.utime(dest, (import_time - saved * 0.001, import_time - saved * 0.001))
                    self.save_link_image_column(dest, column_key)
                    saved += 1
                except Exception as e:
                    QMessageBox.warning(self, "抓取素材", f"下载{prefix}失败：\n{(row or {}).get('url', '')}\n\n{e}")
                    return saved
        return saved

    def open_current_folder(self):
        if not self.ensure_root_folder():
            return
        folder = self.current_folder()
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建文件夹失败：\n{e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

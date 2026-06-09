# -*- coding: utf-8 -*-
"""本地素材库窗口。"""
import hashlib
import gc
import os
import re
import shutil
import time

from PyQt5.QtCore import QEvent, QMimeData, QPoint, QPropertyAnimation, QRect, QSize, Qt, QSettings, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QDrag, QIcon, QImageReader, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
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


class MaterialImageItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.state &= ~QStyle.State_HasFocus
        super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setLineWrapMode(QTextEdit.WidgetWidth)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setStyleSheet(
            """
            QTextEdit {
                border: 1px solid #3498db;
                border-radius: 4px;
                padding: 4px;
                background: #ffffff;
                color: #1f2d3d;
                font: 9pt "Microsoft YaHei";
            }
            """
        )
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        editor.setPlainText(str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or ""))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText().strip(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        widget = getattr(option, "widget", None)
        if getattr(widget, "compact_material_view", False):
            editor.setGeometry(option.rect.adjusted(1, 78, -1, -1))
            return
        editor.setGeometry(option.rect.adjusted(1, 114, -1, -1))

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
    INTERNAL_MOVE_MIME = "application/x-shop-material-image-paths"
    INTERNAL_SOURCE_COLUMN_MIME = "application/x-shop-material-source-column"

    def __init__(self, parent=None, column_key=None, compact=False):
        super().__init__(parent)
        self.material_column_key = column_key
        self.compact_material_view = compact
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(76, 76) if compact else QSize(110, 110))
        self.setGridSize(QSize(86, 124) if compact else QSize(136, 154))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setWrapping(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
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
                    padding: 0px;
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

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            parent = self.window()
            if hasattr(parent, "copy_selected_images"):
                parent.copy_selected_images(self)
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
        icon_height = self.iconSize().height()
        icon_top = rect.top() + (0 if self.compact_material_view else 8)
        icon_bottom = icon_top + icon_height + (4 if self.compact_material_view else 12)
        parent = self.window()
        if event.pos().y() <= icon_bottom:
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
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.setDropAction(Qt.MoveAction if event.mimeData().hasFormat(self.INTERNAL_MOVE_MIME) else Qt.CopyAction)
            event.accept()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        parent = self.window()
        if hasattr(parent, "set_active_link_image_column"):
            parent.set_active_link_image_column(self.material_column_key)
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

    def mimeData(self, items):
        paths = []
        for item in items:
            path = item.data(self.PATH_ROLE)
            if path and os.path.exists(path) and path not in paths:
                paths.append(path)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        mime.setText("\n".join(paths))
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
        mime.setText("\n".join(paths))
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
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.pixmap = QPixmap(image_path)
        self.setWindowTitle(os.path.basename(image_path))
        self.resize(900, 700)
        layout = QVBoxLayout(self)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #111; color: white;")
        layout.addWidget(self.image_label, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.update_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_pixmap()

    def update_pixmap(self):
        if self.pixmap.isNull():
            self.image_label.setText("图片无法打开")
            return
        target = self.image_label.size()
        if target.width() <= 2 or target.height() <= 2:
            return
        self.image_label.setPixmap(self.pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class PdfExtractWorker(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, pdf_path, output_folder, page_limit, base_name, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.output_folder = output_folder
        self.page_limit = page_limit
        self.base_name = base_name
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
                pix = page.get_pixmap(alpha=False)
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


class MaterialLibraryDialog(QDialog):
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
    PRODUCT_MODE = "product"
    LINK_MODE = "link"
    LINK_UNGROUPED = "未分组"
    LINK_NO_TYPE = "无链接类型"
    LINK_ARCHIVED_SUFFIX = "（已下架）"
    LINK_DELETED_SUFFIX = "（已删除）"

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
        self._chip_animations = {}
        self._category_sync_queue = []
        self._category_sync_running = False
        self.pending_pdf_path = ""
        self.pdf_worker = None
        self.setAcceptDrops(True)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setWindowTitle("素材库")
        self.resize(1180, 760)
        self.init_ui()
        self.load_categories()
        self.refresh_root_label()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("素材库")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: #6c757d;")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_open = QPushButton("打开文件夹")
        btn_open.clicked.connect(self.open_current_folder)
        self.btn_copy_link_folder_path = QPushButton("复制文件夹路径")
        self.btn_copy_link_folder_path.clicked.connect(self.copy_current_folder_path)
        self.btn_copy_link_folder_path.setVisible(False)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh_current_view)
        self.mode_button = QPushButton("产品素材库")
        self.mode_button.setCheckable(True)
        self.mode_button.clicked.connect(self.toggle_library_mode)
        btn_settings = QToolButton()
        btn_settings.setText("设置")
        btn_settings.clicked.connect(self.choose_root_folder)
        top.addWidget(title)
        top.addWidget(self.path_label, 1)
        top.addWidget(self.btn_copy_link_folder_path)
        top.addWidget(self.mode_button)
        top.addWidget(btn_open)
        top.addWidget(btn_refresh)
        top.addWidget(btn_settings)
        layout.addLayout(top)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索商品类型、规格名称、规格编码")
        self.search_input.textChanged.connect(self.refresh_bubbles)
        search_row.addWidget(self.search_input, 1)
        self.store_filter_combo = QComboBox()
        self.store_filter_combo.setMinimumWidth(160)
        self.store_filter_combo.currentIndexChanged.connect(self.on_store_filter_changed)
        self.show_inactive_links_checkbox = QCheckBox("显示已下架和删除")
        self.show_inactive_links_checkbox.stateChanged.connect(self.on_link_visibility_changed)
        self.store_filter_combo.setVisible(False)
        self.show_inactive_links_checkbox.setVisible(False)
        search_row.addWidget(self.store_filter_combo)
        search_row.addWidget(self.show_inactive_links_checkbox)
        layout.addLayout(search_row)

        nav_row = QHBoxLayout()
        self.back_button = QPushButton("返回类型")
        self.back_button.clicked.connect(self.back_to_categories)
        self.back_button.setEnabled(False)
        self.current_label = QLabel("商品类型")
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

        self.image_count_label = QLabel("请选择商品类型")
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
        attr_title = QLabel("当前规格产品属性")
        attr_title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.attribute_text = QTextEdit()
        self.attribute_text.setReadOnly(True)
        self.attribute_text.setAcceptRichText(False)
        self.attribute_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.attribute_text.setStyleSheet(
            "QTextEdit { border: 1px solid #d9dee5; border-radius: 6px; padding: 8px; background: #fbfcfd; color: #2c3e50; }"
        )
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
        panel.setStyleSheet(
            """
            QWidget {
                background: #fbfcfd;
                border: 1px dashed #9fb3c8;
                border-radius: 6px;
            }
            QLabel, QComboBox, QPushButton, QProgressBar {
                border: none;
                background: transparent;
            }
            """
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        title = QLabel("PDF 提取")
        title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.pdf_hint_label = QLabel("拖拽/粘贴 PDF 到这里")
        self.pdf_hint_label.setWordWrap(True)
        self.pdf_hint_label.setStyleSheet("color: #6c757d;")
        self.pdf_file_label = QLabel("未选择 PDF")
        self.pdf_file_label.setWordWrap(True)
        self.pdf_file_label.setStyleSheet("color: #34495e;")
        self.pdf_page_combo = QComboBox()
        for label, value in (("1张", 1), ("3张", 3), ("5张", 5), ("10张", 10), ("全部", None)):
            self.pdf_page_combo.addItem(label, value)
        self.pdf_extract_button = QPushButton("提取")
        self.pdf_extract_button.clicked.connect(self.extract_pending_pdf)
        self.pdf_progress = QProgressBar()
        self.pdf_progress.setRange(0, 100)
        self.pdf_progress.setValue(0)
        self.pdf_progress.setTextVisible(True)
        self.pdf_status_label = QLabel("等待 PDF")
        self.pdf_status_label.setWordWrap(True)
        self.pdf_status_label.setStyleSheet("color: #6c757d;")
        layout.addWidget(title)
        layout.addWidget(self.pdf_hint_label)
        layout.addWidget(self.pdf_file_label)
        layout.addWidget(self.pdf_page_combo)
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
            if parent and getattr(parent, "cloud_manager", None):
                active = parent.cloud_manager.get_active_data_account()
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
        key = self.settings_key()
        value = str(self.settings.value(key, "") or "").strip()
        if not value:
            value = str(self.local_root_folders.get(key, "") or "").strip()
        if not value and self.library_mode == self.PRODUCT_MODE:
            legacy_key = self.settings_key().replace(f"{self.PRODUCT_MODE}_root_folder", "root_folder")
            value = str(self.settings.value(legacy_key, "") or "").strip()
        return value

    def set_root_folder(self, folder):
        key = self.settings_key()
        value = os.path.abspath(folder)
        self.local_root_folders[key] = value
        self.settings.setValue(key, value)
        self.settings.sync()

    def refresh_root_label(self):
        folder = self.root_folder()
        self.path_label.setText(folder if folder else "未设置素材库母文件夹")

    def choose_root_folder(self):
        current = self.root_folder()
        folder = QFileDialog.getExistingDirectory(self, "选择素材库母文件夹", current or os.path.expanduser("~"))
        if not folder:
            return
        self.set_root_folder(folder)
        self.refresh_root_label()
        self.refresh_current_view()

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
        is_link = mode == self.LINK_MODE
        self.mode_button.blockSignals(True)
        self.mode_button.setChecked(is_link)
        self.mode_button.setText("链接素材库" if is_link else "产品素材库")
        self.mode_button.blockSignals(False)
        self.store_filter_combo.setVisible(is_link)
        self.show_inactive_links_checkbox.setVisible(is_link)
        if hasattr(self, "image_list"):
            self.image_list.setVisible(not is_link)
        if hasattr(self, "link_image_panel"):
            self.link_image_panel.setVisible(is_link)
        if hasattr(self, "btn_copy_link_folder_path"):
            self.btn_copy_link_folder_path.setVisible(is_link)
        if hasattr(self, "pdf_import_panel"):
            self.pdf_import_panel.setVisible(not is_link)
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.refresh_root_label()
        if is_link:
            self.restore_link_state()
        else:
            self.restore_product_state()
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
            self.image_list.clear()
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
        self.refresh_current_view()

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
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

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
        self.selected_link_product_ids = {str(code or "").strip()}
        self.load_link_data()
        item = self.selected_single_link_item()
        if item:
            self.ensure_link_product_folder(item)
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

    def safe_folder_name(self, text, fallback):
        value = re.sub(r'[<>:"/\\\\|?*]', "", str(text or "")).strip().strip(".")
        return value or fallback

    def normalize_material_spec_name(self, spec_name):
        text = str(spec_name or "").strip()
        if not text:
            return ""
        text = re.sub(r"\s*[【\[\(（]\s*\d+\s*(?:张|页|本|套|份|个|册)\s*[】\]\)）]\s*$", "", text)
        text = re.sub(r"\s*\d+\s*(?:张|页|本|套|份|个|册)\s*$", "", text)
        text = re.sub(r"\s*\d+\s*本\s*[（(]\s*\d+\s*张\s*[）)]\s*$", "", text)
        text = re.sub(r"\s*[（(]\s*\d+\s*张\s*[）)]\s*$", "", text)
        text = re.sub(r"\s*[【\[\(（]\s*\d+\s*本\s*装?\s*[】\]\)）]\s*$", "", text)
        text = re.sub(r"\s*\d+\s*本\s*装\s*$", "", text)
        text = re.sub(r"[【\[\(（]\s*(?:共\s*)?\d+\s*本\s*[】\]\)）]", "", text)
        text = re.sub(r"(?:^|[\s,，;；、-])(?:共\s*)?\d+\s*本(?=$|[\s,，;；、-])", " ", text)
        text = re.sub(r"(?<=[）\]\】)])\s+(?=[\u4e00-\u9fffA-Za-z0-9])", "", text)
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
        text = text.replace("(", "（").replace(")", "）")
        text = re.sub(r"\s+", " ", text).strip()
        return text or str(spec_name or "").strip()

    def normalize_attribute_key(self, text):
        value = str(text or "").strip().lower()
        value = value.replace("：", ":").replace("，", ",").replace("；", ";").replace("、", ",")
        value = re.sub(r"\s+", "", value)
        return value

    def normalize_material_spec_name(self, spec_name):
        text = str(spec_name or "").strip()
        if not text:
            return ""
        text = text.replace("（", "(").replace("）", ")").replace("【", "[").replace("】", "]")
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fffA-Za-z0-9])", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        units = "张|页|本|套|份|个|册"
        changed = True
        while changed:
            before = text
            text = re.sub(rf"\s*[\[(]\s*(?:共\s*)?\d+\s*(?:{units})(?:\s*装)?\s*[\])]$", "", text)
            text = re.sub(rf"\s*\d+\s*(?:{units})\s*[\[(]\s*\d+\s*(?:张|页)\s*[\])]$", "", text)
            text = re.sub(rf"\s*\d+\s*(?:{units})(?:\s*装)?$", "", text)
            changed = text != before
        return text.strip() or str(spec_name or "").strip()

    def normalize_material_spec_name(self, spec_name):
        text = str(spec_name or "").strip()
        if not text:
            return ""
        text = (
            text.replace("（", "(")
            .replace("）", ")")
            .replace("【", "[")
            .replace("】", "]")
            .replace("｛", "[")
            .replace("｝", "]")
        )
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fffA-Za-z0-9])", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        units = r"张|页|本|套|份|个|册"
        count_units = r"本|套|份|个|册"
        page_units = r"张|页"
        changed = True
        while changed:
            before = text
            text = re.sub(
                rf"\s*共\s*\d+\s*(?:{count_units})(?:\s*[\[(]\s*\d+\s*(?:{page_units})\s*[\])])?\s*$",
                "",
                text,
            )
            text = re.sub(
                rf"\s*[\[(]\s*(?:共\s*)?\d+\s*(?:{units})(?:\s*[\[(]\s*\d+\s*(?:{units})\s*[\])])?(?:\s*装)?\s*[\])]\s*$",
                "",
                text,
            )
            text = re.sub(rf"\s*\d+\s*(?:{units})(?:\s*装)?\s*$", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            changed = text != before
        return text or str(spec_name or "").strip()

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
            self.local_category_folder_paths[key] = target
            self.settings.setValue(key, target)
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
            try:
                keys = self.settings.allKeys()
            except Exception:
                keys = []
            for key in keys:
                if not key.startswith(prefix) or not key.endswith(suffix):
                    continue
                category_name = key[len(prefix):-len(suffix)]
                folder_name = str(self.settings.value(key, "") or "").strip()
                if root and category_name and folder_name:
                    legacy_path = os.path.join(root, category_name, folder_name)
                    if legacy_path not in paths:
                        paths.append(legacy_path)
        return paths

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
        for code in spec.get("codes", []) or [spec.get("primary_code", "")]:
            if code:
                key = self.spec_folder_mapping_key(category, code)
                self.local_spec_folder_mappings[key] = folder_name
                self.settings.setValue(key, folder_name)
                self.settings.setValue(self.spec_folder_path_mapping_key(code), target)
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
                dst_path = self.unique_destination_path(target, name) if os.path.exists(dst_path) else dst_path
                shutil.move(src_path, dst_path)
        try:
            os.rmdir(source)
        except OSError:
            pass

    def sync_spec_folder(self, category, spec):
        if not self.root_folder():
            return ""
        target = self.spec_folder(category, spec)
        category_folder = self.category_folder(category)
        folder_names = self.spec_alias_folder_names(spec) + [
            name for name in self.mapped_spec_folder_names(category, spec)
            if name not in self.spec_alias_folder_names(spec)
        ]
        for source in self.mapped_spec_folder_paths(category, spec) + self.discover_spec_folder_paths_across_categories(category, spec):
            if os.path.isdir(source) and os.path.abspath(source) != os.path.abspath(target):
                try:
                    self.merge_or_move_material_folder(source, target)
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

    def load_categories(self):
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
            self.categories = [
                {"label": str(label or ""), "color": color or "#DDEBF7", "sort": sort_order or 0, "count": count or 0}
                for label, color, sort_order, count in rows
                if str(label or "").strip()
            ]
            self.schedule_deferred_category_sync()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取成本库商品类型失败：\n{e}")
            self.categories = []
        self.refresh_bubbles()

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

    def spec_matches_keyword(self, spec, keyword):
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
        return any(keyword in str(value or "").lower() for value in values)

    def category_matches_keyword(self, category, keyword):
        if not keyword:
            return True
        label = str(category.get("label", "") or "")
        if keyword in label.lower():
            return True
        try:
            specs = self.get_specs_for_category(label)
        except Exception:
            return False
        return any(self.spec_matches_keyword(spec, keyword) for spec in specs)

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
        grouped = {}
        for spec_name, spec_code, product_attribute, manual_sort_order, sort_order in rows:
            original_name = str(spec_name or "").strip() or str(spec_code or "").strip() or "未命名规格"
            name = self.normalize_material_spec_name(original_name) or original_name
            key = name.lower()
            item = grouped.get(key)
            if not item:
                item = {
                    "name": name,
                    "code": str(spec_code or ""),
                    "manual_sort": manual_sort_order,
                    "sort": sort_order,
                    "aliases": [],
                    "attributes": [],
                    "attribute_keys": set(),
                }
                grouped[key] = item
            if original_name not in item["aliases"]:
                item["aliases"].append(original_name)
            attr_text = str(product_attribute or "").strip()
            attr_key = self.normalize_attribute_key(attr_text)
            if attr_text and attr_key and attr_key not in item["attribute_keys"]:
                item["attributes"].append(attr_text)
                item["attribute_keys"].add(attr_key)
            if not item.get("code") and spec_code:
                item["code"] = str(spec_code or "")
        specs = list(grouped.values())
        for item in specs:
            item.pop("attribute_keys", None)
        return specs

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
        grouped = {}
        for spec_name, spec_code, product_attribute, manual_sort_order, sort_order in rows:
            original_name = str(spec_name or "").strip() or str(spec_code or "").strip() or "未命名规格"
            normalized_name = self.normalize_material_spec_name(original_name) or original_name
            key = normalized_name.lower()
            code = str(spec_code or "").strip()
            item = grouped.get(key)
            if not item:
                item = {
                    "name": normalized_name,
                    "code": code,
                    "primary_code": code,
                    "primary_original_name": original_name,
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
            target_name = self.normalize_material_spec_name(item.get("primary_original_name", "")) or item["name"]
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
        return specs

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
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
        if self.library_mode == self.LINK_MODE:
            self.refresh_link_bubbles()
            return
        if self.current_category:
            self.refresh_spec_bubbles()
        else:
            self.refresh_category_bubbles()

    def refresh_category_bubbles(self):
        self.category_scroll.setVisible(True)
        self.spec_scroll.setVisible(False)
        self.back_button.setEnabled(False)
        self.current_label.setText("商品类型")
        self.clear_layout(self.category_layout)
        self.category_buttons = {}
        keyword = self.search_input.text().strip().lower()
        for category in self.categories:
            label = category["label"]
            if not self.category_matches_keyword(category, keyword):
                continue
            button = self.create_chip(label, category.get("color") or "#DDEBF7")
            button.setChecked(label in self.selected_category_labels)
            button.clicked.connect(lambda _checked=False, c=category: self.toggle_category(c))
            self.category_layout.addWidget(button)
            self.category_buttons[label] = button
        if not self.categories:
            self.image_count_label.setText("成本库里还没有商品类型")
        self.schedule_chip_layout_refresh()

    def refresh_spec_bubbles(self):
        self.category_scroll.setVisible(False)
        self.spec_scroll.setVisible(True)
        self.back_button.setEnabled(True)
        category_label = self.current_category.get("label", "")
        self.current_label.setText(f"商品类型：{category_label}")
        self.clear_layout(self.spec_layout)
        self.spec_buttons = {}
        keyword = self.search_input.text().strip().lower()
        for spec in self.specs:
            name = spec["name"]
            if not self.spec_matches_keyword(spec, keyword):
                continue
            button = self.create_chip(name, self.current_category.get("color") or "#DDEBF7")
            button.setChecked(name in self.selected_spec_names)
            self.configure_spec_drop_target(button, spec)
            button.clicked.connect(lambda _checked=False, s=spec: self.toggle_spec(s))
            self.spec_layout.addWidget(button)
            self.spec_buttons[name] = button
        self.schedule_chip_layout_refresh()

    def create_chip(self, text, color):
        bg = QColor(color if color else "#DDEBF7")
        fg = QColor("#1f2d3d")
        button = QPushButton(text)
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
            """
        )
        return button

    def configure_spec_drop_target(self, button, spec):
        button.setProperty("materialDropTarget", "product_spec")
        button.material_spec = spec

    def configure_link_product_drop_target(self, button, item):
        button.setProperty("materialDropTarget", "link_product")
        button.material_link_item = item
        button.setAcceptDrops(True)
        button.installEventFilter(self)

    def set_chip_drop_hover(self, button, active):
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

    def eventFilter(self, watched, event):
        if getattr(watched, "property", None) and watched.property("materialDropTarget") in ("product_spec", "link_product"):
            if event.type() in (QEvent.DragEnter, QEvent.DragMove):
                if self.image_paths_from_mime_data(event.mimeData()):
                    self.set_chip_drop_hover(watched, True)
                    event.setDropAction(Qt.MoveAction if event.mimeData().hasFormat(MaterialImageList.INTERNAL_MOVE_MIME) else Qt.CopyAction)
                    event.accept()
                    return True
            if event.type() == QEvent.DragLeave:
                self.set_chip_drop_hover(watched, False)
                return False
            if event.type() == QEvent.Drop:
                self.set_chip_drop_hover(watched, False)
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
            dest = self.unique_destination_path(target_folder, os.path.basename(path))
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
            self.image_count_label.setText(f"已移动 {moved} 张图片到 {spec.get('name', '')}")
        return moved > 0

    def load_store_filter(self, preferred_store_id=None):
        self.store_filter_combo.blockSignals(True)
        self.store_filter_combo.clear()
        self.store_filter_combo.addItem("全部店铺", None)
        try:
            rows = self.db.safe_fetchall("SELECT id, name FROM stores ORDER BY sort_order, id")
        except Exception:
            rows = []
        selected_index = 0
        for store_id, store_name in rows:
            index = self.store_filter_combo.count()
            self.store_filter_combo.addItem(str(store_name or f"店铺{store_id}"), store_id)
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

    def link_status_suffix(self, item):
        if item.get("deleted"):
            return self.LINK_DELETED_SUFFIX
        if item.get("archived"):
            return self.LINK_ARCHIVED_SUFFIX
        return ""

    def strip_link_status_suffix(self, name):
        text = str(name or "")
        for suffix in (self.LINK_ARCHIVED_SUFFIX, self.LINK_DELETED_SUFFIX):
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
        try:
            if not item.get("deleted"):
                old_folder = self.mapped_link_folder_path(item)
                if not old_folder or not os.path.isdir(old_folder):
                    old_folder = self.find_existing_link_folder(item.get("code", ""))
                if old_folder and os.path.abspath(old_folder) != os.path.abspath(target):
                    self.merge_or_move_folder(old_folder, target)
            if os.path.exists(normal) and os.path.abspath(normal) != os.path.abspath(target) and not os.path.exists(target):
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
                          COALESCE(p.is_archived, 0), p.store_id, COALESCE(s.name, ''),
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
        for db_id, code, title, link_type, image_data, image_path, archived, store_id, store_name, combo in rows:
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
                "archived": bool(archived),
                "deleted": False,
            }
            if not item["archived"] or show_inactive:
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
                            "archived": False,
                            "deleted": True,
                            "folder_path": folder_path,
                        })
        return items

    def refresh_link_bubbles(self):
        self.category_scroll.setVisible(True)
        self.spec_scroll.setVisible(bool(self.selected_link_combo))
        self.link_product_scroll.setVisible(bool(self.selected_link_type))
        self.back_button.setEnabled(bool(self.selected_link_combo))
        self.current_label.setText("链接素材库")
        self.clear_layout(self.category_layout)
        self.clear_layout(self.spec_layout)
        self.clear_layout(self.link_product_layout)
        self.category_buttons = {}
        self.spec_buttons = {}
        self.link_product_buttons = {}
        keyword = self.search_input.text().strip().lower()

        visible_items = self.filtered_link_items(keyword)
        combos = sorted({item["combo"] for item in visible_items}, key=lambda value: value.lower())
        for combo in combos:
            button = self.create_chip(combo, "#DDEBF7")
            button.setChecked(combo == self.selected_link_combo)
            button.clicked.connect(lambda _checked=False, value=combo: self.select_link_combo(value))
            self.category_layout.addWidget(button)
            self.category_buttons[combo] = button

        if self.selected_link_combo:
            type_items = [item for item in visible_items if item["combo"] == self.selected_link_combo]
            types = sorted({item["link_type"] for item in type_items}, key=lambda value: value.lower())
            for link_type in types:
                button = self.create_chip(link_type, "#E8F4EA")
                button.setChecked(link_type == self.selected_link_type)
                button.clicked.connect(lambda _checked=False, value=link_type: self.select_link_type(value))
                self.spec_layout.addWidget(button)
                self.spec_buttons[link_type] = button

        if self.selected_link_combo and self.selected_link_type:
            self.link_products = [
                item for item in visible_items
                if item["combo"] == self.selected_link_combo and item["link_type"] == self.selected_link_type
            ]
            for item in self.link_products:
                button = self.create_link_id_chip(item)
                button.setChecked(item["code"] in self.selected_link_product_ids)
                button.clicked.connect(lambda _checked=False, value=item: self.toggle_link_product(value))
                self.link_product_layout.addWidget(button)
                self.link_product_buttons[item["code"]] = button
        if not self.link_items:
            self.image_count_label.setText("当前没有可显示的链接素材")
        self.schedule_chip_layout_refresh()

    def filtered_link_items(self, keyword):
        if not keyword:
            return list(self.link_items)
        result = []
        for item in self.link_items:
            haystack = " ".join([
                item.get("combo", ""),
                item.get("link_type", ""),
                item.get("code", ""),
                item.get("title", ""),
                item.get("store_name", ""),
            ]).lower()
            if keyword in haystack:
                result.append(item)
        return result

    def create_link_id_chip(self, item):
        text = item.get("code", "")
        if item.get("archived"):
            text += self.LINK_ARCHIVED_SUFFIX
        if item.get("deleted"):
            text += self.LINK_DELETED_SUFFIX
        button = QToolButton()
        button.setCheckable(True)
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(64, 64))
        button.setMinimumSize(QSize(106, 96))
        button.setMaximumWidth(128)
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
        if not pixmap.isNull():
            button.setIcon(QIcon(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        button.setToolTip(item.get("title") or item.get("code", ""))
        self.configure_link_product_drop_target(button, item)
        return button

    def select_link_combo(self, combo):
        if not self.ensure_root_folder():
            return
        if self.selected_link_combo == combo:
            self.selected_link_combo = ""
            self.selected_link_type = ""
            self.selected_link_product_ids = set()
        else:
            self.selected_link_combo = combo
            self.selected_link_type = ""
            self.selected_link_product_ids = set()
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

    def select_link_type(self, link_type):
        if not self.ensure_root_folder():
            return
        if self.selected_link_type == link_type:
            self.selected_link_type = ""
            self.selected_link_product_ids = set()
        else:
            self.selected_link_type = link_type
            self.selected_link_product_ids = set()
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

    def toggle_link_product(self, item):
        if not self.ensure_link_product_folder(item):
            return
        code = item.get("code", "")
        ctrl_pressed = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if ctrl_pressed:
            if code in self.selected_link_product_ids:
                self.selected_link_product_ids.remove(code)
            else:
                self.selected_link_product_ids.add(code)
        elif self.selected_link_product_ids == {code}:
            self.selected_link_product_ids = set()
        else:
            self.selected_link_product_ids = {code}
        self.refresh_link_bubbles()
        self.load_images_for_link_selection()

    def refresh_link_bubbles(self):
        showing_combo = not self.selected_link_combo
        showing_type = bool(self.selected_link_combo) and not self.selected_link_type
        showing_product = bool(self.selected_link_combo and self.selected_link_type)
        self.category_scroll.setVisible(showing_combo)
        self.spec_scroll.setVisible(showing_type)
        self.link_product_scroll.setVisible(showing_product)
        self.back_button.setEnabled(bool(self.selected_link_combo))
        if showing_product:
            self.current_label.setText(f"链接类型：{self.selected_link_type}")
        elif showing_type:
            self.current_label.setText(f"链接组合：{self.selected_link_combo}")
        else:
            self.current_label.setText("链接组合")

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
                button.setChecked(item["code"] in self.selected_link_product_ids)
                button.clicked.connect(lambda _checked=False, value=item: self.toggle_link_product(value))
                self.link_product_layout.addWidget(button)
                self.link_product_buttons[item["code"]] = button

        if not self.link_items:
            self.image_count_label.setText("当前没有可显示的链接素材")
        self.schedule_chip_layout_refresh()

    def select_category(self, category):
        root = self.ensure_root_folder()
        if not root:
            return
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
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.refresh_spec_bubbles()
        self.load_images_for_category()

    def toggle_category(self, category):
        if not self.ensure_root_folder():
            return
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
            self.sync_spec_folders(selected_category)
            self.refresh_spec_bubbles()
            self.load_images_for_category()
        else:
            self.current_category = None
            self.current_spec = None
            self.refresh_category_bubbles()
            self.load_images_for_selected_categories()

    def select_spec(self, spec):
        if not self.current_category:
            return
        if not self.ensure_root_folder():
            return
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
        if not self.current_category:
            return
        if not self.ensure_root_folder():
            return
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
        if self.library_mode == self.LINK_MODE:
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
        self.image_list.clear()
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
        if self.current_category and self.selected_spec_names:
            self.load_images_for_selected_specs()
        elif self.current_category:
            self.load_images_for_category()
        elif self.selected_category_labels:
            self.load_images_for_selected_categories()
        else:
            self.load_categories()

    def is_image_file(self, path):
        return os.path.isfile(path) and os.path.splitext(path)[1].lower() in self.IMAGE_EXTENSIONS

    def image_natural_sort_key(self, path, white_first=False):
        name = os.path.basename(path)
        stem, _ext = os.path.splitext(name)
        normalized_stem = stem.strip().lower()
        white_rank = 0 if white_first and normalized_stem == "白底图" else 1
        parts = re.split(r"(\d+)", normalized_stem)
        natural_parts = [int(part) if part.isdigit() else part for part in parts]
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0
        has_number = any(part.isdigit() for part in parts)
        return (white_rank, 0 if has_number else 1, natural_parts, mtime, name.lower())

    def sorted_image_files(self, folder, white_first=False):
        if not folder or not os.path.isdir(folder):
            return []
        try:
            paths = [
                os.path.join(folder, name)
                for name in os.listdir(folder)
                if self.is_image_file(os.path.join(folder, name))
            ]
            return sorted(paths, key=lambda path: self.image_natural_sort_key(path, white_first=white_first))
        except Exception:
            return []

    def images_for_category(self, category, specs=None):
        folder = self.category_folder(category)
        images = [(path, os.path.basename(path)) for path in self.sorted_image_files(folder)]
        source_specs = specs if specs is not None else self.specs
        for spec in source_specs:
            spec_name = spec.get("name", "")
            folder_names = [spec_name] + [
                alias for alias in spec.get("aliases", [])
                if alias and alias != spec_name
            ]
            seen_folders = set()
            for folder_name in folder_names:
                spec_folder = os.path.join(folder, self.safe_folder_name(folder_name, "未命名规格"))
                normalized_folder = os.path.abspath(spec_folder)
                if normalized_folder in seen_folders:
                    continue
                seen_folders.add(normalized_folder)
                for path in self.sorted_image_files(spec_folder):
                    images.append((path, f"{spec_name} / {os.path.basename(path)}"))
        return images

    def load_images_for_category(self):
        self.image_list.clear()
        if not self.current_category:
            return
        images = self.images_for_category(self.current_category)
        self.add_image_items(images)
        self.image_count_label.setText(f"当前类型图片：{len(images)} 张")
        self.update_attribute_sidebar()

    def load_images_for_selected_categories(self):
        self.image_list.clear()
        images = []
        for category in self.categories:
            if category.get("label") not in self.selected_category_labels:
                continue
            self.load_specs(category.get("label", ""))
            category_images = self.images_for_category(category)
            for path, name in category_images:
                images.append((path, f"{category.get('label', '')} / {name}"))
        self.add_image_items(images)
        self.image_count_label.setText(f"当前选择图片：{len(images)} 张")
        self.update_attribute_sidebar()

    def load_images_for_selected_specs(self):
        self.image_list.clear()
        if not self.current_category:
            return
        selected_specs = [spec for spec in self.specs if spec.get("name") in self.selected_spec_names]
        images = []
        for spec in selected_specs:
            spec_name = spec.get("name", "")
            folder_names = [spec_name] + [
                alias for alias in spec.get("aliases", [])
                if alias and alias != spec_name
            ]
            seen_folders = set()
            for folder_name in folder_names:
                folder = os.path.join(self.category_folder(self.current_category), self.safe_folder_name(folder_name, "未命名规格"))
                normalized_folder = os.path.abspath(folder)
                if normalized_folder in seen_folders:
                    continue
                seen_folders.add(normalized_folder)
                for path in self.sorted_image_files(folder):
                    images.append((path, f"{spec_name} / {os.path.basename(path)}"))
        self.add_image_items(images)
        self.image_count_label.setText(f"当前规格图片：{len(images)} 张")
        self.update_attribute_sidebar()

    def load_images_for_spec(self):
        self.image_list.clear()
        if not self.current_category or not self.current_spec:
            return
        images = []
        folder_names = [self.current_spec.get("name", "")] + [
            alias for alias in self.current_spec.get("aliases", [])
            if alias and alias != self.current_spec.get("name", "")
        ]
        seen_folders = set()
        for folder_name in folder_names:
            folder = os.path.join(self.category_folder(self.current_category), self.safe_folder_name(folder_name, "未命名规格"))
            normalized_folder = os.path.abspath(folder)
            if normalized_folder in seen_folders:
                continue
            seen_folders.add(normalized_folder)
            images.extend((path, os.path.basename(path)) for path in self.sorted_image_files(folder))
        self.add_image_items(images)
        self.image_count_label.setText(f"当前规格图片：{len(images)} 张")
        self.update_attribute_sidebar()

    def images_for_category(self, category, specs=None):
        source_specs = specs if specs is not None else self.specs
        self.sync_category_folder(category, source_specs)
        self.sync_spec_folders(category, source_specs)
        folder = self.category_folder(category)
        images = [(path, os.path.basename(path)) for path in self.sorted_image_files(folder, white_first=True)]
        for spec in source_specs:
            spec_name = spec.get("name", "")
            seen_folders = set()
            for folder_name in self.spec_alias_folder_names(spec):
                spec_folder = os.path.join(folder, folder_name)
                normalized_folder = os.path.abspath(spec_folder)
                if normalized_folder in seen_folders:
                    continue
                seen_folders.add(normalized_folder)
                for path in self.sorted_image_files(spec_folder, white_first=True):
                    images.append((path, f"{spec_name} / {os.path.basename(path)}"))
        return images

    def load_images_for_selected_specs(self):
        self.image_list.clear()
        if not self.current_category:
            return
        selected_specs = [spec for spec in self.specs if spec.get("name") in self.selected_spec_names]
        self.sync_category_folder(self.current_category, self.specs)
        images = []
        for spec in selected_specs:
            self.sync_spec_folder(self.current_category, spec)
            spec_name = spec.get("name", "")
            seen_folders = set()
            for folder_name in self.spec_alias_folder_names(spec):
                folder = os.path.join(self.category_folder(self.current_category), folder_name)
                normalized_folder = os.path.abspath(folder)
                if normalized_folder in seen_folders:
                    continue
                seen_folders.add(normalized_folder)
                for path in self.sorted_image_files(folder, white_first=True):
                    images.append((path, f"{spec_name} / {os.path.basename(path)}"))
        self.add_image_items(images)
        self.image_count_label.setText(f"当前规格图片：{len(images)} 张")
        self.update_attribute_sidebar()

    def load_images_for_spec(self):
        self.image_list.clear()
        if not self.current_category or not self.current_spec:
            return
        self.sync_category_folder(self.current_category, self.specs)
        self.sync_spec_folder(self.current_category, self.current_spec)
        images = []
        seen_folders = set()
        for folder_name in self.spec_alias_folder_names(self.current_spec):
            folder = os.path.join(self.category_folder(self.current_category), folder_name)
            normalized_folder = os.path.abspath(folder)
            if normalized_folder in seen_folders:
                continue
            seen_folders.add(normalized_folder)
            images.extend((path, os.path.basename(path)) for path in self.sorted_image_files(folder, white_first=True))
        self.add_image_items(images)
        self.image_count_label.setText(f"当前规格图片：{len(images)} 张")
        self.update_attribute_sidebar()

    def selected_link_items(self):
        if not self.selected_link_product_ids:
            return []
        selected = []
        for item in self.link_items:
            if item.get("code") in self.selected_link_product_ids:
                selected.append(item)
        return selected

    def link_image_column_prefix(self, column_key):
        return {
            "main": "主图",
            "detail": "详情页",
            "sku": "SKU",
        }.get(column_key, "")

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
        patterns = (
            ("main", "主图"),
            ("detail", "详情页"),
            ("sku", "sku"),
        )
        for column_key, prefix in patterns:
            pattern = rf"^{re.escape(prefix)}\s*(?:[（(【\[_，,\-]?\s*(\d+)\s*[）)】\]]?)?(?:[_\-]\d+)?$"
            match = re.match(pattern, normalized, re.IGNORECASE)
            if match:
                number = int(match.group(1)) if match.group(1) else 0
                return column_key, number
        return "main", 0

    def is_link_auto_named_file(self, filename):
        column_key, number = self.classify_link_image_name(filename)
        return column_key in ("main", "detail", "sku") and number > 0

    def link_column_sort_key(self, path):
        column_key, number = self.classify_link_image_name(os.path.basename(path))
        if column_key != "main" or number:
            return (0, number if number else 999999, self.image_natural_sort_key(path))
        return self.image_natural_sort_key(path)

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
        for item in self.selected_link_items():
            if not item.get("deleted"):
                self.ensure_link_product_folder(item)
            folder = item.get("folder_path") or self.link_product_folder(item, use_status=True)
            for path in self.sorted_image_files(folder):
                name = os.path.splitext(os.path.basename(path))[0]
                if len(self.selected_link_product_ids) != 1:
                    name = f"{item.get('code', '')} / {name}"
                column_key = self.link_image_column_for_path(path)
                grouped[column_key].append((path, name))
        total = 0
        empty_texts = {
            "main": "没有主图",
            "detail": "没有详情页",
            "sku": "没有 SKU 图",
        }
        for column_key, image_list in self.link_image_lists.items():
            images = sorted(grouped.get(column_key, []), key=lambda item: self.link_column_sort_key(item[0]))
            total += len(images)
            self.add_image_items(images, image_list=image_list, empty_text=empty_texts.get(column_key, "没有图片"))
        self.image_count_label.setText(f"当前链接素材图片：{total} 张")
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
                if item.get("archived"):
                    lines.append("  已下架")
                if item.get("deleted"):
                    lines.append("  已删除")
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
        self.attribute_text.setPlainText("\n".join(lines) if lines else "当前没有可显示的产品属性。")

    def attribute_lines_for_specs(self, category_label, specs):
        lines = []
        for spec in specs:
            attrs = [str(attr or "").strip() for attr in spec.get("attributes", []) if str(attr or "").strip()]
            if not attrs:
                continue
            if not lines:
                lines.append(f"【{category_label}】")
            lines.append(f"{spec.get('name', '')}")
            lines.append(f"  {attrs[0]}")
        return lines

    def add_image_items(self, images, image_list=None, empty_text="当前文件夹没有可显示的图片"):
        if image_list is None:
            image_list = self.image_list
        image_list.blockSignals(True)
        for path, display_name in images:
            pixmap = self.load_thumbnail_pixmap(path, image_list.iconSize())
            if pixmap.isNull():
                continue
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
            item.setToolTip(path)
            image_list.addItem(item)
        if image_list.count() == 0:
            item = QListWidgetItem("当前文件夹没有可显示的图片")
            item.setFlags(Qt.NoItemFlags)
            item.setText(empty_text)
            image_list.addItem(item)
        image_list.blockSignals(False)

    def load_thumbnail_pixmap(self, path, target_size):
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
        return pixmap

    def clear_link_image_lists(self):
        for image_list in getattr(self, "link_image_lists", {}).values():
            image_list.clear()

    def set_active_link_image_column(self, column_key):
        if self.library_mode == self.LINK_MODE and column_key in ("main", "detail", "sku", "uncategorized"):
            self.active_link_image_column = column_key

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

    def copy_selected_images(self, source_list=None):
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
        dialog = MaterialImageViewerDialog(path, self)
        dialog.exec_()

    def rename_image(self, item):
        path = self.image_path_from_item(item)
        if not path:
            return
        folder = os.path.dirname(path)
        old_name = os.path.basename(path)
        stem, ext = os.path.splitext(old_name)
        new_stem, ok = QInputDialog.getText(self, "重命名图片", "文件名：", text=stem)
        if not ok:
            return
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
        base_name, ok = QInputDialog.getText(self, "批量重命名", "基础名称：", text=os.path.splitext(os.path.basename(start_path))[0])
        if not ok:
            return
        base_name = self.safe_folder_name(base_name, "素材")
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
            target = os.path.join(folder, f"{base_name}（{index}）{ext}")
            normalized_target = os.path.abspath(target)
            if normalized_target in used_targets:
                QMessageBox.warning(self, "批量重命名失败", "生成的新文件名存在重复。")
                return
            if os.path.exists(target) and os.path.abspath(target) != os.path.abspath(path):
                target = self.unique_destination_path(folder, os.path.basename(target))
                normalized_target = os.path.abspath(target)
                if normalized_target in used_targets:
                    QMessageBox.warning(self, "批量重命名失败", "生成的新文件名存在重复。")
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
            "确认删除",
            f"确定要删除选中的 {len(paths)} 张本地图片吗？\n此操作会删除文件本身。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
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
            QMessageBox.warning(self, "部分删除失败", "\n\n".join(failed[:5]))

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
            QMessageBox.information(self, "提示", "PDF 正在提取中，请等待完成后再关闭素材库窗口。")
            event.ignore()
            return
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
                QMessageBox.information(self, "提示", "请先只选择一个商品ID，再导入素材。")
                return ""
            return self.ensure_link_product_folder(item)
        if not self.current_category:
            QMessageBox.information(self, "提示", "请先选择一个商品类型，再导入素材。")
            return ""
        folder = self.current_folder()
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建导入文件夹失败：\n{e}")
            return ""
        return folder

    def selected_single_link_item(self):
        if self.library_mode != self.LINK_MODE or len(self.selected_link_product_ids) != 1:
            return None
        code = next(iter(self.selected_link_product_ids))
        return next((item for item in self.link_items if item.get("code") == code), None)

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
            QMessageBox.information(self, "提示", "链接素材库模式不支持 PDF 提取。")
            return
        if self.pdf_worker and self.pdf_worker.isRunning():
            QMessageBox.information(self, "提示", "PDF 正在提取中，请稍候。")
            return
        if not self.pending_pdf_path or not os.path.exists(self.pending_pdf_path):
            QMessageBox.information(self, "提示", "请先拖拽或粘贴一个 PDF 文件。")
            return
        target_folder = self.selected_single_spec_folder()
        if not target_folder:
            QMessageBox.information(self, "提示", "请先只选择一个商品规格，再提取 PDF。")
            return
        page_limit = self.pdf_page_combo.currentData()
        base_name = self.safe_folder_name(os.path.splitext(os.path.basename(self.pending_pdf_path))[0], "PDF素材")
        self.pdf_extract_button.setEnabled(False)
        self.pdf_progress.setValue(0)
        self.pdf_status_label.setText("正在提取 PDF...")
        self.pdf_worker = PdfExtractWorker(self.pending_pdf_path, target_folder, page_limit, base_name, self)
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
        self.pdf_progress.setValue(100)
        self.pdf_status_label.setText(f"提取完成：{len(saved_paths)} 张")
        self.refresh_current_view()

    def on_pdf_extract_failed(self, message):
        self.pdf_status_label.setText("提取失败")
        QMessageBox.warning(self, "PDF 提取失败", message)

    def unique_destination_path(self, folder, filename):
        name, ext = os.path.splitext(filename)
        safe_name = self.safe_folder_name(name, "素材")
        ext = ext or ".png"
        candidate = os.path.join(folder, safe_name + ext)
        index = 2
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{safe_name}（{index}）{ext}")
            index += 1
        return candidate

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
        prefix = self.link_image_column_prefix(column_key)
        if not prefix:
            return original_filename
        _stem, ext = os.path.splitext(original_filename)
        ext = ext or ".png"
        index = self.allocate_link_column_index(folder, column_key, next_indices)
        return f"{prefix}（{index}）{ext}"

    def link_move_filename(self, folder, original_filename, column_key, next_indices):
        if self.library_mode != self.LINK_MODE or column_key not in ("main", "detail", "sku"):
            return original_filename
        current_column, _number = self.classify_link_image_name(original_filename)
        if current_column == column_key:
            return original_filename
        prefix = self.link_image_column_prefix(column_key)
        _stem, ext = os.path.splitext(original_filename)
        ext = ext or ".png"
        index = self.allocate_link_column_index(folder, column_key, next_indices)
        return f"{prefix}（{index}）{ext}"

    def link_transfer_filename(self, folder, original_filename, column_key, allocation_state):
        if column_key not in ("main", "detail", "sku"):
            return original_filename
        prefix = self.link_image_column_prefix(column_key)
        _stem, ext = os.path.splitext(original_filename)
        ext = ext or ".png"
        index = self.allocate_link_column_index(folder, column_key, allocation_state)
        return f"{prefix}（{index}）{ext}"

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
        moved = 0
        next_indices = {}
        for path in paths or []:
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
            self.image_count_label.setText(f"已移动 {moved} 张图片")
        return bool(paths)

    def move_images_to_link_product(self, paths, item, source_column=""):
        if self.library_mode != self.LINK_MODE or not item:
            return False
        target_folder = item.get("folder_path") or self.ensure_link_product_folder(item)
        if not target_folder:
            return False
        os.makedirs(target_folder, exist_ok=True)
        moved = 0
        allocation_state = {}
        for path in paths or []:
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
            self.image_count_label.setText(f"已移动 {moved} 张图片到 {item.get('code', '')}")
        return moved > 0

    def iter_image_paths(self, path):
        if self.is_image_file(path):
            yield path
            return
        if not os.path.isdir(path):
            return
        for root, _dirs, files in os.walk(path):
            for name in sorted(files, key=lambda item: item.lower()):
                candidate = os.path.join(root, name)
                if self.is_image_file(candidate):
                    yield candidate

    def import_paths(self, paths):
        folder = self.target_import_folder()
        if not folder:
            return False
        copied = 0
        import_time = time.time()
        column_key = self.active_link_import_column()
        next_indices = {}
        for raw_path in paths or []:
            path = os.path.abspath(raw_path)
            for image_path in self.iter_image_paths(path):
                filename = self.link_import_filename(folder, os.path.basename(image_path), column_key, next_indices)
                dest = self.unique_destination_path(folder, filename)
                if os.path.abspath(image_path) == os.path.abspath(dest):
                    continue
                try:
                    shutil.copy2(image_path, dest)
                    os.utime(dest, (import_time + copied * 0.001, import_time + copied * 0.001))
                    if self.library_mode == self.LINK_MODE and column_key in ("main", "detail", "sku"):
                        self.save_link_image_column(dest, column_key)
                    copied += 1
                except Exception as e:
                    QMessageBox.warning(self, "导入失败", f"导入图片失败：\n{image_path}\n\n{e}")
                    return copied > 0
        if copied:
            self.refresh_current_view()
            self.image_count_label.setText(f"已导入 {copied} 张图片")
        return copied > 0

    def import_image_data(self, image_data):
        folder = self.target_import_folder()
        if not folder:
            return False
        if image_data is None or not hasattr(image_data, "save") or image_data.isNull():
            return False
        if self.library_mode == self.LINK_MODE:
            column_key = self.active_link_import_column()
            filename = self.link_import_filename(folder, "粘贴图片.png", column_key, {})
        else:
            filename = f"粘贴图片_{time.strftime('%Y%m%d_%H%M%S')}.png"
        dest = self.unique_destination_path(folder, filename)
        if not image_data.save(dest, "PNG"):
            QMessageBox.warning(self, "导入失败", "剪贴板图片保存失败。")
            return False
        if self.library_mode == self.LINK_MODE:
            column_key = self.active_link_import_column()
            if column_key in ("main", "detail", "sku"):
                self.save_link_image_column(dest, column_key)
        self.refresh_current_view()
        self.image_count_label.setText("已导入 1 张图片")
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
                return self.import_paths(paths)
        if mime_data.hasText():
            paths = self.paths_from_text(mime_data.text())
            if paths:
                return self.import_paths(paths)
        if mime_data.hasImage():
            return self.import_image_data(mime_data.imageData())
        return False

    def paste_images_from_clipboard(self, source_list=None):
        if isinstance(source_list, MaterialImageList):
            self.set_active_link_image_column(source_list.material_column_key)
        mime_data = QApplication.clipboard().mimeData()
        if not self.import_from_mime_data(mime_data):
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
        self.pdf_status_label.setText("已选择 PDF，选择页数后点击提取。")
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
            return self.spec_folder(self.current_category, self.current_spec)
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
            self.image_count_label.setText(f"已复制文件夹路径：{folder}")

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

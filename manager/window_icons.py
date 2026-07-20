"""Window icon helpers for the desktop app."""

import os
import sys

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFontDialog,
    QMessageBox,
    QProgressDialog,
)


ICON_FILES = {
    "main": "window_main.svg",
    "cost": "window_cost.svg",
    "material": "window_material.svg",
    "spec": "window_spec.svg",
    "record": "window_record.svg",
    "daily": "window_daily.svg",
    "promotion": "window_promotion.svg",
    "store": "window_store.svg",
    "settings": "window_settings.svg",
    "archive": "window_archive.svg",
    "api": "window_api.svg",
}

ICON_TEXTS = {
    "main": "主", "cost": "成", "material": "素", "spec": "规",
    "record": "操", "daily": "每", "promotion": "推", "store": "店",
    "settings": "设", "archive": "存", "api": "A",
}

ICON_COLORS = {
    "main": "#2f5d47", "cost": "#687886", "material": "#4f9b86",
    "spec": "#536b7c", "record": "#4f86a8", "daily": "#bd666a",
    "promotion": "#9a6a5f", "store": "#5f8a62", "settings": "#6f7d88",
    "archive": "#7b6860", "api": "#b88445",
}

_ICON_CACHE = {}


def icons_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "manager", "icons")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def icon_path(name="main"):
    filename = ICON_FILES.get(name, ICON_FILES["main"])
    return os.path.join(icons_dir(), filename)


def _title_initial(title, fallback="主"):
    return next((char.upper() for char in str(title or "") if char.isalnum()), fallback)


def _text_icon(text, name="main"):
    key = (str(text or "主")[:1], name)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(ICON_COLORS.get(name, ICON_COLORS["main"])))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    font = QFont("Microsoft YaHei", 39)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, key[0])
    painter.end()
    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def get_window_icon(name="main"):
    try:
        if QApplication.instance() is not None:
            return _text_icon(ICON_TEXTS.get(name, ICON_TEXTS["main"]), name)
        path = icon_path(name)
        if os.path.exists(path):
            return QIcon(path)
    except Exception as e:
        print(f"加载窗口图标失败 {name}: {e}")
    return QIcon()


class _WindowTitleIconFilter(QObject):
    def eventFilter(self, widget, event):
        if event.type() in (QEvent.Show, QEvent.WindowTitleChange):
            try:
                if isinstance(widget, QDialog) and is_standard_window_candidate(widget):
                    name = widget.property("windowIconKey") or "main"
                    fallback = ICON_TEXTS.get(name, ICON_TEXTS["main"])
                    widget.setWindowIcon(_text_icon(_title_initial(widget.windowTitle(), fallback), name))
            except Exception:
                pass
        return False


_WINDOW_TITLE_ICON_FILTER = None


def install_window_icon_filter(app):
    global _WINDOW_TITLE_ICON_FILTER
    try:
        current_app = _WINDOW_TITLE_ICON_FILTER.parent() if _WINDOW_TITLE_ICON_FILTER is not None else None
    except RuntimeError:
        current_app = None
    if current_app is not app:
        _WINDOW_TITLE_ICON_FILTER = _WindowTitleIconFilter(app)
    app.installEventFilter(_WINDOW_TITLE_ICON_FILTER)


def is_standard_window_candidate(widget):
    try:
        if not isinstance(widget, QDialog):
            return False
        flags = widget.windowFlags()
        window_type = flags & Qt.WindowType_Mask
        if window_type in (Qt.Popup, Qt.Tool, Qt.SplashScreen):
            return False
        skip_hints = Qt.FramelessWindowHint | Qt.BypassWindowManagerHint
        if flags & skip_hints:
            return False
        # Qt common dialogs manage their own native flags. Changing them while
        # they are opening can make static file-dialog calls return immediately.
        if isinstance(widget, (QFileDialog, QColorDialog, QFontDialog, QMessageBox, QProgressDialog)):
            return False
        if flags & Qt.WindowStaysOnTopHint and widget.isModal():
            return False
        return True
    except Exception:
        return False


def apply_standard_window_flags(widget):
    """Give normal dialogs native minimize/maximize/close buttons and remove the help button."""
    if not is_standard_window_candidate(widget):
        return False
    try:
        flags = widget.windowFlags()
        new_flags = (
            (flags | Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
            & ~Qt.WindowContextHelpButtonHint
        )
        if new_flags != flags and not widget.isVisible():
            widget.setWindowFlags(new_flags)
        return True
    except Exception as e:
        print(f"应用标准窗口按钮失败: {e}")
        return False


def apply_window_icon(widget, name="main"):
    try:
        apply_standard_window_flags(widget)
        widget.setProperty("windowIconKey", name)
        app = QApplication.instance()
        if app is not None:
            install_window_icon_filter(app)
        fallback = ICON_TEXTS.get(name, ICON_TEXTS["main"])
        icon = _text_icon(_title_initial(widget.windowTitle(), fallback), name)
        if not icon.isNull():
            widget.setWindowIcon(icon)
        return icon
    except Exception as e:
        print(f"应用窗口图标失败 {name}: {e}")
        return QIcon()

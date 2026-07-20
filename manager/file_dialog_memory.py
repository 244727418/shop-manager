# -*- coding: utf-8 -*-
"""Helpers for QFileDialog calls that remember the last used folder."""
import os

from PyQt5.QtWidgets import QFileDialog


LAST_DIR_SETTING_KEY = "file_dialog_last_dir"


def _last_dir(db):
    try:
        path = db.get_setting(LAST_DIR_SETTING_KEY, "") if db else ""
    except Exception:
        path = ""
    if path and os.path.isdir(path):
        return path
    return ""


def _remember_path(db, file_path):
    if not db or not file_path:
        return
    folder = os.path.dirname(os.path.abspath(file_path))
    if not folder or not os.path.isdir(folder):
        return
    try:
        db.set_setting(LAST_DIR_SETTING_KEY, folder)
    except Exception:
        pass


def remembered_open_file(parent, db, caption, file_filter, selected_filter=""):
    file_path, used_filter = QFileDialog.getOpenFileName(
        parent, caption, _last_dir(db), file_filter, selected_filter
    )
    _remember_path(db, file_path)
    return file_path, used_filter


def remembered_save_file(parent, db, caption, default_name, file_filter, selected_filter=""):
    initial_dir = _last_dir(db)
    initial_path = os.path.join(initial_dir, default_name) if initial_dir else default_name
    file_path, used_filter = QFileDialog.getSaveFileName(
        parent, caption, initial_path, file_filter, selected_filter
    )
    _remember_path(db, file_path)
    return file_path, used_filter


def remembered_existing_directory(parent, db, caption):
    folder = QFileDialog.getExistingDirectory(
        parent, caption, _last_dir(db), QFileDialog.ShowDirsOnly
    )
    if folder and os.path.isdir(folder):
        try:
            db.set_setting(LAST_DIR_SETTING_KEY, folder)
        except Exception:
            pass
    return folder

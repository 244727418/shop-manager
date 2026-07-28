import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from manager import shop_manager
from manager.shop_manager import (
    BUNDLED_APP_FONT_FILES,
    CURRENT_RELEASE_NOTES,
    DEFAULT_GLOBAL_HOTKEYS,
    SettingsDialog,
    auto_start_command,
    startup_release_notes,
)
from manager.db import SafeDatabaseManager


def test_current_hotkeys_are_the_defaults():
    assert DEFAULT_GLOBAL_HOTKEYS == {
        "quick_hotkey_main": "Ctrl+Shift+Z",
        "quick_hotkey_cost_library": "Ctrl+Shift+C",
        "quick_hotkey_material_library": "Ctrl+Shift+S",
    }


def test_app_font_presets_stay_small_and_cover_requested_styles():
    assert list(SettingsDialog.FONT_PRESETS) == [
        "默认（微软雅黑）", "黄油体", "卡通体", "书法体", "宋体", "黑体", "圆体",
    ]
    assert all(SettingsDialog.FONT_PRESETS.values())
    assert all((Path(__file__).parent / "fonts" / name).is_file() for name in BUNDLED_APP_FONT_FILES.values())
    assert "app_font" in SafeDatabaseManager.COMMON_SETTING_KEYS


def test_release_notes_only_show_once_for_the_installed_update():
    version = shop_manager.VERSION
    settings = {
        "last_update_manifest": {"version": version, "notes": CURRENT_RELEASE_NOTES},
    }
    assert startup_release_notes(settings, version) == CURRENT_RELEASE_NOTES
    settings["release_notes_seen_version"] = version
    assert startup_release_notes(settings, version) == ""
    assert startup_release_notes(settings, "99.0") == ""


def test_release_notes_are_recorded_before_the_popup():
    original_load = shop_manager.load_global_update_settings
    original_save = shop_manager.save_global_update_setting
    version = shop_manager.VERSION
    settings = {
        "last_update_manifest": {"version": version, "notes": "本次更新"},
    }
    events = []

    class FakeWindow:
        current_version = version

        def show_current_release_notes(self, notes=None):
            events.append(("show", notes))

    try:
        shop_manager.load_global_update_settings = lambda: dict(settings)

        def save_setting(key, value):
            events.append(("save", value))
            settings[key] = value

        shop_manager.save_global_update_setting = save_setting
        window = FakeWindow()
        assert shop_manager.ShopManagerApp.show_release_notes_once(window)
        assert events == [("save", version), ("show", "本次更新")]
        assert not shop_manager.ShopManagerApp.show_release_notes_once(window)
    finally:
        shop_manager.load_global_update_settings = original_load
        shop_manager.save_global_update_setting = original_save


def test_frozen_auto_start_command_quotes_executable(monkeypatch):
    executable = r"C:\Program Files\Shop Manager\shop_manager.exe"
    monkeypatch.setattr(sys, "executable", executable)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert auto_start_command() == subprocess.list2cmdline([executable, "--autostart"])


def test_source_auto_start_command_includes_script(monkeypatch):
    executable = r"C:\Python\pythonw.exe"
    script = r"E:\Shop Manager\manager\shop_manager.py"
    monkeypatch.setattr(sys, "executable", executable)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [script])

    assert auto_start_command() == subprocess.list2cmdline([executable, script, "--autostart"])

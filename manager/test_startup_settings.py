import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from manager.shop_manager import DEFAULT_GLOBAL_HOTKEYS, auto_start_command


def test_current_hotkeys_are_the_defaults():
    assert DEFAULT_GLOBAL_HOTKEYS == {
        "quick_hotkey_main": "Ctrl+Shift+Z",
        "quick_hotkey_cost_library": "Ctrl+Shift+C",
        "quick_hotkey_material_library": "Ctrl+Shift+S",
    }


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

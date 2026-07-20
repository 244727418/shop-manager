# -*- coding: utf-8 -*-
"""调试版和打包版共用的崩溃报告。"""
import faulthandler
import atexit
import os
import platform
import shutil
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime

try:
    from manager.data_root import DataRootManager
except ImportError:
    from data_root import DataRootManager


REPORT_NAME = "崩溃报告.log"
PREVIOUS_REPORT_NAME = REPORT_NAME.replace(".log", "_上次.log")
_report_file = None
_recent_events = deque(maxlen=80)
_event_lock = threading.RLock()
_start_monotonic = time.monotonic()


def crash_report_path():
    manager = DataRootManager()
    directory = manager.get_data_root() or os.path.join(manager.app_dir(), "logs")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, REPORT_NAME)


def _previous_report_path(path):
    return os.path.join(os.path.dirname(path), PREVIOUS_REPORT_NAME)


def _reset_current_report(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        previous = _previous_report_path(path)
        try:
            if os.path.exists(previous):
                os.remove(previous)
            os.replace(path, previous)
        except Exception:
            pass


def append_exception(context, error=None, exc_info=None):
    try:
        with open(crash_report_path(), "a", encoding="utf-8") as report:
            report.write("\n" + "=" * 80 + "\n")
            report.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{context}]\n")
            if exc_info:
                traceback.print_exception(*exc_info, file=report)
            elif error is not None:
                traceback.print_exception(type(error), error, error.__traceback__, file=report)
            _write_likely_cause(report, error=error, exc_info=exc_info)
            _write_system_snapshot(report)
            _write_recent_events(report)
            _write_thread_stacks(report)
    except Exception:
        pass


def append_event(context):
    try:
        text = f"{datetime.now():%Y-%m-%d %H:%M:%S} [event] {context} | {_resource_summary()}"
        with _event_lock:
            _recent_events.append(text)
        with open(crash_report_path(), "a", encoding="utf-8") as report:
            report.write(text + "\n")
    except Exception:
        pass


def dump_crash_context(context="snapshot"):
    try:
        with open(crash_report_path(), "a", encoding="utf-8") as report:
            report.write("\n" + "-" * 80 + "\n")
            report.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{context}]\n")
            _write_system_snapshot(report)
            _write_recent_events(report)
            _write_thread_stacks(report)
    except Exception:
        pass


def _resource_summary():
    parts = [f"uptime={time.monotonic() - _start_monotonic:.1f}s"]
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        vm = psutil.virtual_memory()
        parts.append(f"rss={mem.rss / 1024 / 1024:.1f}MB")
        parts.append(f"vms={mem.vms / 1024 / 1024:.1f}MB")
        parts.append(f"ram_free={vm.available / 1024 / 1024:.0f}MB")
        parts.append(f"ram_used={vm.percent:.0f}%")
        parts.append(f"threads={proc.num_threads()}")
    except Exception:
        pass
    try:
        usage = shutil.disk_usage(os.path.dirname(crash_report_path()))
        parts.append(f"disk_free={usage.free / 1024 / 1024 / 1024:.1f}GB")
    except Exception:
        pass
    return " ".join(parts)


def _write_system_snapshot(report):
    report.write("\nsystem snapshot:\n")
    report.write(f"  {_resource_summary()}\n")
    try:
        report.write(f"  argv={sys.argv}\n")
        report.write(f"  cwd={os.getcwd()}\n")
        report.write(f"  executable={sys.executable}\n")
    except Exception:
        pass


def _write_likely_cause(report, error=None, exc_info=None):
    exc_type = exc_info[0] if exc_info else (type(error) if error is not None else None)
    exc_value = exc_info[1] if exc_info else error
    if exc_type is None:
        return
    report.write("\nlikely cause hint:\n")
    if issubclass(exc_type, MemoryError):
        report.write("  Python MemoryError: likely memory pressure or oversized data processing.\n")
    elif issubclass(exc_type, PermissionError):
        report.write("  PermissionError: likely file/process permission or locked file.\n")
    elif "sqlite3" in sys.modules and issubclass(exc_type, sys.modules["sqlite3"].Error):
        report.write("  sqlite database error: likely data/DB lock/schema issue.\n")
    else:
        report.write(f"  Python exception: {exc_type.__name__}: {exc_value}\n")


def _write_recent_events(report):
    with _event_lock:
        events = list(_recent_events)
    if not events:
        return
    report.write("\nrecent events:\n")
    for event in events:
        report.write(f"  {event}\n")


def _write_thread_stacks(report):
    try:
        frames = sys._current_frames()
        report.write("\nthread stacks:\n")
        for thread in threading.enumerate():
            report.write(f"\n--- thread name={thread.name} ident={thread.ident} daemon={thread.daemon} ---\n")
            frame = frames.get(thread.ident)
            if frame is not None:
                traceback.print_stack(frame, file=report)
    except Exception:
        pass


def _handle_uncaught(exc_type, exc_value, exc_traceback):
    append_exception("uncaught", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _handle_thread_exception(args):
    append_exception(
        f"thread:{getattr(args.thread, 'name', 'unknown')}",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _handle_unraisable(args):
    append_exception(
        f"unraisable:{getattr(args.object, '__class__', type(args.object)).__name__}",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _mark_clean_exit():
    try:
        append_event("process:normal_exit")
        if _report_file is not None:
            _report_file.flush()
    except Exception:
        pass


def install_crash_reporting(version=""):
    global _report_file
    if _report_file is not None:
        return crash_report_path()
    try:
        path = crash_report_path()
        _reset_current_report(path)
        _report_file = open(path, "a", encoding="utf-8", buffering=1)
        _report_file.write("=" * 80 + "\n")
        _report_file.write(
            f"{datetime.now():%Y-%m-%d %H:%M:%S} process start | "
            f"version={version or '-'} | pid={os.getpid()} | frozen={bool(getattr(sys, 'frozen', False))} | "
            f"debugger={'debugpy' in sys.modules} | exe={sys.executable}\n"
        )
        _report_file.write(
            f"python={sys.version.split()[0]} | platform={platform.platform()} | cwd={os.getcwd()}\n"
        )
        _write_system_snapshot(_report_file)
        _report_file.flush()
        faulthandler.enable(file=_report_file, all_threads=True)
        sys.excepthook = _handle_uncaught
        if hasattr(threading, "excepthook"):
            threading.excepthook = _handle_thread_exception
        if hasattr(sys, "unraisablehook"):
            sys.unraisablehook = _handle_unraisable
        atexit.register(_mark_clean_exit)
        return path
    except Exception:
        _report_file = None
        return None

import json
import os


def test_crash_report_uses_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    root = str(tmp_path / "存档")
    os.makedirs(root)
    config_dir = tmp_path / "店铺管理软件"
    config_dir.mkdir()
    with open(config_dir / "data_root.json", "w", encoding="utf-8") as config:
        json.dump({"data_root": root}, config, ensure_ascii=False)

    try:
        raise RuntimeError("crash report check")
    except RuntimeError as error:
        try:
            from manager.crash_report import append_exception, crash_report_path
        except ImportError:
            from crash_report import append_exception, crash_report_path
        append_exception("test", error=error)

    path = crash_report_path()
    assert path == os.path.join(root, "崩溃报告.log")
    with open(path, encoding="utf-8") as report:
        assert "RuntimeError: crash report check" in report.read()


def test_crash_report_includes_recent_events(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    root = str(tmp_path / "存档")
    os.makedirs(root)
    config_dir = tmp_path / "店铺管理软件"
    config_dir.mkdir()
    with open(config_dir / "data_root.json", "w", encoding="utf-8") as config:
        json.dump({"data_root": root}, config, ensure_ascii=False)

    try:
        from manager.crash_report import append_event, append_exception, crash_report_path
    except ImportError:
        from crash_report import append_event, append_exception, crash_report_path

    append_event("ui:test_action:start")
    try:
        raise ValueError("recent event check")
    except ValueError as error:
        append_exception("test_recent", error=error)

    with open(crash_report_path(), encoding="utf-8") as report:
        text = report.read()
    assert "ui:test_action:start" in text
    assert "recent events:" in text
    assert "thread stacks:" in text
if __name__ == "__main__":
    test_crash_report_uses_data_root()
    print("crash report OK")

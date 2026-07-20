import os
import sys
from glob import glob
from pathlib import Path

import pytest


def test_conda_runtime_dlls_exist():
    conda_bin = os.path.join(sys.prefix, "Library", "bin")
    required = ("libssl*.dll", "libcrypto*.dll", "libexpat*.dll")
    missing = [pattern for pattern in required if not glob(os.path.join(conda_bin, pattern))]
    if missing:
        pytest.skip(f"当前环境不是打包环境，缺少：{', '.join(missing)}")


def test_current_spec_is_workspace_relative():
    spec = Path(__file__).resolve().parents[1] / "shop_manager_v5.2.spec"
    content = spec.read_text(encoding="utf-8")
    assert "C:\\Users\\" not in content
    assert "D:\\" not in content
    assert "SPECPATH" in content


if __name__ == "__main__":
    test_conda_runtime_dlls_exist()
    print("OK")

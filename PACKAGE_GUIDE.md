# 店铺管理系统 PyInstaller 打包提示词

## 项目信息

**项目路径：** `E:\zhuomian\shop`
**主入口文件：** `manager\shop_manager.py`
**项目结构：**
```
shop/
└── manager/
    ├── __init__.py
    ├── shop_manager.py      # 主入口（直接运行这个会报错，需要打包）
    ├── db.py                # 数据库模块
    ├── delegates.py         # 表格代理
    ├── prompts.py          # 提示词管理
    ├── ui_utils.py          # UI工具
    ├── dialogs/             # 对话框模块
    │   ├── __init__.py
    │   ├── api_config.py
    │   ├── cost_import.py
    │   ├── cost_library.py
    │   ├── daily_task.py
    │   ├── make_product_spec.py
    │   ├── product_spec.py
    │   ├── profit.py
    │   ├── records.py
    │   └── store_margin.py
    ├── widgets/            # UI组件模块
    │   ├── __init__.py
    │   └── product_store.py
    ├── icons/              # 图标文件夹
    └── config.json         # 配置文件
```

---

## 打包原因

`shop_manager.py` 中使用了 `from manager.xxx` 形式的**绝对导入**：
```python
from manager.db import SafeDatabaseManager
from manager.widgets import ProductWidget, StoreWidget, RecordRow, InPlaceEditor
from manager.dialogs import (...)
```

这种导入方式**不能直接双击运行**（会报 `ModuleNotFoundError`），但**可以打包成exe后正常运行**。

---

## 打包命令

```powershell
cd E:\zhuomian\shop
pyinstaller --onefile --windowed --add-data "manager/icons;manager/icons" manager/shop_manager.py --clean --noconfirm
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `--onefile` | 打包成单个exe文件 |
| `--windowed` | 不显示命令行窗口（GUI程序） |
| `--add-data "manager/icons;manager/icons"` | 包含图标文件夹（分号Windows路径分隔符） |
| `--clean` | 清理之前的build文件 |
| `--noconfirm` | 不询问确认 |

**输出位置：** `dist\shop_manager.exe`

---

## 【重要】添加新模块时的注意事项

### 1. 添加新Python模块

如果在 `manager/dialogs/` 或 `manager/widgets/` 下添加了新文件，**不需要修改任何代码**，因为它们的 `__init__.py` 已经使用了相对导入，打包时会自动包含。

### 2. 添加新的顶级模块（如 manager/xxx.py）

如果添加了新的顶级模块（如 `manager/new_module.py`），需要：

**方法A：在 shop_manager.py 中添加导入语句**
```python
from manager.new_module import SomeClass
```

**方法B：在 spec 文件中添加 hiddenimports**
```python
hiddenimports=['manager.new_module', ...]
```

### 3. 添加新的资源文件

如果添加了新的资源文件（如 `manager/new_folder/something.png`），需要在打包命令中添加：

```powershell
--add-data "manager/new_folder;manager/new_folder"
```

### 4. 添加新的第三方库依赖

如果代码中 import 了新的第三方库（如 `import new_library`），PyInstaller 通常能自动检测到。但如果打包后运行报错，需要在 spec 文件中添加：

```python
hiddenimports=['new_library', ...]
```

---

## spec 配置文件

如果需要更精细的控制，可以创建 `shop_manager.spec` 文件：

```python
# shop_manager.spec
a = Analysis(
    ['manager\\shop_manager.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('manager\\icons', 'manager\\icons'),
        ('manager\\config.json', 'manager'),
    ],
    hiddenimports=[
        'manager.db', 'manager.delegates', 'manager.prompts', 'manager.ui_utils',
        'manager.widgets', 'manager.widgets.product_store',
        'manager.dialogs', 'manager.dialogs.records', 'manager.dialogs.store_margin',
        'manager.dialogs.cost_import', 'manager.dialogs.cost_library',
        'manager.dialogs.api_config', 'manager.dialogs.profit',
        'manager.dialogs.daily_task', 'manager.dialogs.product_spec',
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'sqlite3', 'requests', 'psutil', 'pandas', 'openpyxl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='shop_manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

**使用 spec 文件打包：**
```powershell
pyinstaller shop_manager.spec --clean --noconfirm
```

---

## 快速检查清单

打包前确认以下内容：

- [ ] `manager/__init__.py` 存在
- [ ] `manager/dialogs/__init__.py` 存在
- [ ] `manager/widgets/__init__.py` 存在
- [ ] `manager/icons/` 目录存在
- [ ] `manager/config.json` 存在
- [ ] `manager/shop_manager.py` 中所有导入语句都使用 `from manager.xxx` 格式

---

## 常见错误排查

### 错误1：ModuleNotFoundError: No module named 'xxx'
**原因：** 缺少 hiddenimports
**解决：** 在 spec 文件的 hiddenimports 中添加缺失的模块

### 错误2：FileNotFoundError: xxx
**原因：** 资源文件未包含
**解决：** 在 `--add-data` 或 spec 的 datas 中添加

### 错误3：ImportError: attempted relative import with no known parent package
**原因：** 在打包后的exe中使用了相对导入
**解决：** 使用 `from manager.xxx` 而不是 `from .xxx`

---

## 联系方式

如有疑问，请联系开发者。
```
# -*- mode: python ; coding: utf-8 -*-
# 店铺毛利管理系统 v2.5 打包配置
# PyInstaller --noconfirm --onefile --windowed --icon=manager/icons/app.ico --name=shop_manager_v2.5 --additional-hooks-dir=. shop_manager.spec

import sys
import os

block_cipher = None

# 收集所有必要的模块
hiddenimports = [
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PyQt5.sip',
    'openpyxl',
    'openpyxl.cell',
    'openpyxl.workbook',
    'pandas',
    'numpy',
    'jinja2',
    '低温烹饪',
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    'dateutil',
    'pytz',
]

a = Analysis(
    ['manager\\shop_manager.py'],
    pathex=[
        os.path.abspath('.'),
        os.path.abspath('manager'),
    ],
    binaries=[],
    datas=[
        ('manager/icons', 'manager/icons'),
        ('manager/config.json', 'manager/config.json'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='shop_manager_v2.5',
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

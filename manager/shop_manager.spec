# -*- mode: python ; coding: utf-8 -*-


block_cipher = None

a = Analysis(
    ['shop_manager.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('dialogs', 'dialogs'),
        ('widgets', 'widgets'),
    ],
    hiddenimports=[
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.sip',
        'db',
        'prompts',
        'ui_utils',
        'delegates',
        'dialogs',
        'dialogs.store_margin',
        'dialogs.input_data_dialog',
        'dialogs.profit',
        'dialogs.records',
        'dialogs.cost_library',
        'dialogs.cost_import',
        'dialogs.api_config',
        'dialogs.product_spec',
        'dialogs.make_product_spec',
        'dialogs.daily_task',
        'widgets.product_store',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ShopManager_v2.6',
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
    icon=None,
    version='version_info.txt',
)
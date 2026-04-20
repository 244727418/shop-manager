# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['e:\\zhuomian\\shop\\manager\\shop_manager.py'],
    pathex=[],
    binaries=[],
    datas=[('manager\\icons', 'manager\\icons')],
    hiddenimports=['manager', 'manager.db', 'manager.delegates', 'manager.prompts', 'manager.ui_utils', 'manager.widgets', 'manager.widgets.product_store', 'manager.dialogs', 'manager.dialogs.records', 'manager.dialogs.store_margin', 'manager.dialogs.cost_import', 'manager.dialogs.cost_library', 'manager.dialogs.api_config', 'manager.dialogs.profit', 'manager.dialogs.daily_task', 'manager.dialogs.product_spec', 'manager.dialogs.make_product_spec', 'manager.dialogs.input_data_dialog', 'manager.cloud_sync', 'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtSvg', 'pandas', 'openpyxl', 'requests', 'psutil', 'sqlite3', 'cos_python_sdk_v5', 'cos', 'crcmod', 'pycryptodome', 'xmltodict'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'sklearn', 'skimage', 'tensorflow', 'torch', 'dask', 'distributed', 'panel', 'bokeh', 'plotly', 'pyqtgraph', 'vtk', 'mayavi', 'PyOpenGL', 'holoviews', 'hvplot', 'xarray', 'intake', 'fsspec', 'tensorboard', 'cloudpickle'],
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
    name='shop_manager_v3.2',
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

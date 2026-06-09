# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


xlrd_hiddenimports = collect_submodules('xlrd')
fitz_hiddenimports = ['fitz', 'fitz.table', 'fitz.utils', 'pymupdf']

a = Analysis(
    ['e:\\zhuomian\\shop\\manager\\shop_manager.py'],
    pathex=[],
    binaries=[],
    datas=[('manager\\icons', 'manager\\icons')],
    hiddenimports=['manager', 'manager.db', 'manager.delegates', 'manager.prompts', 'manager.ui_utils', 'manager.update_manager', 'manager.widgets', 'manager.widgets.product_store', 'manager.dialogs', 'manager.dialogs.records', 'manager.dialogs.store_margin', 'manager.dialogs.cost_import', 'manager.dialogs.cost_library', 'manager.dialogs.material_library', 'manager.dialogs.api_config', 'manager.dialogs.profit', 'manager.dialogs.daily_task', 'manager.dialogs.product_spec', 'manager.dialogs.make_product_spec', 'manager.dialogs.input_data_dialog', 'manager.dialogs.promotion_data', 'manager.pdd_browser_monitor', 'manager.cloud_sync', 'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtSvg', 'PyQt5.QtNetwork', 'pandas', 'openpyxl', 'xlrd', 'requests', 'psutil', 'sqlite3', 'cos_python_sdk_v5', 'cos', 'crcmod', 'pycryptodome', 'xmltodict'] + xlrd_hiddenimports + fitz_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'sklearn', 'skimage', 'tensorflow', 'torch', 'dask', 'distributed', 'panel', 'bokeh', 'plotly', 'pyqtgraph', 'vtk', 'mayavi', 'PyOpenGL', 'holoviews', 'hvplot', 'xarray', 'intake', 'fsspec', 'tensorboard', 'cloudpickle', 'IPython', 'nbformat', 'jsonschema', 'sphinx', 'docutils', 'jinja2', 'black', 'pygments', 'sqlalchemy', 'tables', 'lxml', 'zmq', 'numba', 'llvmlite'],
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
    name='shop_manager_v3.17.2',
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

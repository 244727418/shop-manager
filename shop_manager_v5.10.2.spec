# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules
import os
import sys
from glob import glob


xlrd_hiddenimports = collect_submodules('xlrd')
openpyxl_datas, openpyxl_binaries, openpyxl_hiddenimports = collect_all('openpyxl')
et_xmlfile_hiddenimports = collect_submodules('et_xmlfile')
fitz_hiddenimports = ['fitz', 'fitz.table', 'fitz.utils', 'pymupdf']
pypinyin_hiddenimports = collect_submodules('pypinyin')
conda_bin = os.path.join(sys.prefix, 'Library', 'bin')
runtime_binaries = [
    (path, '.')
    for pattern in ('libssl*.dll', 'libcrypto*.dll', 'libexpat*.dll')
    for path in glob(os.path.join(conda_bin, pattern))
]

a = Analysis(
    [os.path.join(SPECPATH, 'manager', 'shop_manager.py')],
    pathex=[SPECPATH],
    binaries=openpyxl_binaries + runtime_binaries,
    datas=[('manager\\icons', 'manager\\icons')] + openpyxl_datas,
    hiddenimports=['manager', 'manager.db', 'manager.delegates', 'manager.prompts', 'manager.ui_utils', 'manager.update_manager', 'manager.widgets', 'manager.widgets.product_store', 'manager.dialogs', 'manager.dialogs.records', 'manager.dialogs.store_margin', 'manager.dialogs.cost_import', 'manager.dialogs.cost_library', 'manager.dialogs.material_library', 'manager.material_mobile_service', 'manager.dialogs.api_config', 'manager.dialogs.profit', 'manager.dialogs.daily_task', 'manager.dialogs.product_spec', 'manager.dialogs.make_product_spec', 'manager.dialogs.input_data_dialog', 'manager.dialogs.promotion_data', 'manager.pdd_browser_monitor', 'manager.archive_manager', 'qrcode', 'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtSvg', 'PyQt5.QtNetwork', 'pandas', 'openpyxl', 'et_xmlfile', 'xlrd', 'requests', 'psutil', 'sqlite3'] + xlrd_hiddenimports + openpyxl_hiddenimports + et_xmlfile_hiddenimports + fitz_hiddenimports + pypinyin_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'skimage', 'tensorflow', 'torch', 'torchvision', 'torchaudio', 'dask', 'distributed', 'panel', 'bokeh', 'plotly', 'pyqtgraph', 'vtk', 'mayavi', 'PyOpenGL', 'holoviews', 'hvplot', 'xarray', 'intake', 'fsspec', 'tensorboard', 'cloudpickle', 'IPython', 'nbformat', 'jsonschema', 'sphinx', 'docutils', 'jinja2', 'black', 'pygments', 'sqlalchemy', 'tables', 'lxml', 'zmq', 'numba', 'llvmlite'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='shop_manager_v5.10.2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

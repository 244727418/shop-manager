# -*- coding: utf-8 -*-
"""One-off script to generate product_spec.py from shop_manager.py"""
import os
import re

this_dir = os.path.dirname(os.path.abspath(__file__))
parent = os.path.dirname(this_dir)
main_path = os.path.join(parent, 'shop_manager.py')

with open(main_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

body = ''.join(lines[3650:6031])
body = body.replace(
    'os.path.join(os.path.dirname(__file__), "icons"',
    'os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons"'
)

header = '''# -*- coding: utf-8 -*-
"""商品规格管理与毛利计算器对话框"""
import os
import re
import json
import requests
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QWidget, QLineEdit, QSpinBox,
    QComboBox, QFrame, QGridLayout, QAbstractItemView, QFileDialog,
    QProgressDialog, QApplication, QInputDialog, QTextEdit, QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QSize
from PyQt5.QtGui import QColor, QPixmap, QIcon

try:
    from ..delegates import SpecNameDelegate, CenterAlignDelegate, WeightDelegate
except ImportError:
    from delegates import SpecNameDelegate, CenterAlignDelegate, WeightDelegate

try:
    from .profit import ProfitCalculatorDialog
except ImportError:
    from profit import ProfitCalculatorDialog

'''

out_path = os.path.join(this_dir, 'product_spec.py')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(header)
    f.write(body)
print('Written', out_path)

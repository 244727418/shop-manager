# -*- coding: utf-8 -*-
"""成本表导入配置对话框"""
import os
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import pandas as pd  # type: ignore

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt


class CostImportDialog(QDialog):
    """成本表导入配置对话框 - 极简版 (无预览，只选列)"""
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.column_names = []

        self.setWindowTitle("📥 导入成本表 - 选择列")
        self.resize(500, 320)
        self.init_ui()
        self.load_columns()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self._debug_cid_label = QLabel("【板块:成本导入对话框\n文件:cost_import.py】文件路径/列选择/规格编码/成本价/导入执行")
        self._debug_cid_label.setStyleSheet("background-color: #DDA0DD; color: #000; font-weight: bold; padding: 1px;")
        self._debug_cid_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._debug_cid_label)
        lbl_info = QLabel(f"文件已加载：{self.file_path.split('/')[-1]}\n请选择对应的列：")
        lbl_info.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(lbl_info)
        layout_spec = QHBoxLayout()
        layout_spec.addWidget(QLabel("【规格编码/SKU】"))
        self.combo_spec = QComboBox()
        self.combo_spec.setMinimumWidth(300)
        layout_spec.addWidget(self.combo_spec)
        layout.addLayout(layout_spec)
        layout_price = QHBoxLayout()
        layout_price.addWidget(QLabel("【成本价】"))
        self.combo_price = QComboBox()
        self.combo_price.setMinimumWidth(300)
        layout_price.addWidget(self.combo_price)
        layout.addLayout(layout_price)
        layout.addStretch()
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_confirm = QPushButton("✅ 确认导入")
        self.btn_confirm.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 10px 30px;")
        self.btn_confirm.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("❌ 取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_confirm)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def load_columns(self):
        try:
            import pandas as pd  # type: ignore
            if not os.path.exists(self.file_path):
                raise Exception("文件路径不存在")
            df_test = pd.read_excel(self.file_path, nrows=1, header=0, engine='openpyxl')
            df = pd.read_excel(self.file_path, nrows=0, header=0, engine='openpyxl')
            raw_columns = df.columns.tolist()
            valid_columns = [str(c).strip() for c in raw_columns if str(c).strip() != "" and str(c).lower() != "nan"]
            if len(valid_columns) == 0:
                df_backup = pd.read_excel(self.file_path, nrows=1, header=None, engine='openpyxl')
                backup_row = df_backup.iloc[0].tolist()
                raise Exception(f"读取到的第一行为空或无效。实际读取内容：{backup_row}")
            self.column_names = raw_columns
            self.combo_spec.clear()
            self.combo_price.clear()
            for idx, name in enumerate(self.column_names):
                name_str = str(name).strip()
                if not name_str or name_str.lower() == "nan":
                    continue
                col_letter = ""
                num = idx + 1
                while num > 0:
                    num, rem = divmod(num - 1, 26)
                    col_letter = chr(65 + rem) + col_letter
                display_text = f"{name_str} ({col_letter}列)"
                self.combo_spec.addItem(display_text, idx)
                self.combo_price.addItem(display_text, idx)
            if self.combo_spec.count() == 0:
                raise Exception("所有列名均为空")
            self.auto_match_columns()
        except PermissionError:
            QMessageBox.critical(
                self, "文件被占用",
                "❌ 无法读取文件！\n\n**文件可能正在被 Excel 或 WPS 打开！**\n\n请务必先**关闭**该 Excel 文件，然后再点击导入。"
            )
            self.reject()
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            QMessageBox.critical(
                self, "读取失败",
                f"❌ 无法读取列名！\n\n错误信息：{str(e)}\n\n"
                f"排查建议：\n1. 请确保 Excel 文件已**关闭**。\n"
                f"2. 检查第一行是否真的有文字。\n3. 尝试将文件另存为新的 .xlsx 再导入。"
            )
            self.reject()

    def auto_match_columns(self):
        spec_keywords = ['规格', '编码', 'SKU', 'Code', 'ID', '型号', '商品编号', 'SPU', 'No']
        price_keywords = ['成本', '价格', 'Price', 'Cost', '单价', '进价', 'Money']
        spec_found = price_found = False
        for idx, name in enumerate(self.column_names):
            name_str = str(name).strip()
            if not name_str or name_str.lower() == "nan":
                continue
            name_lower = name_str.lower()
            if not spec_found and any(k.lower() in name_lower for k in spec_keywords):
                i = self.combo_spec.findData(idx)
                if i >= 0:
                    self.combo_spec.setCurrentIndex(i)
                spec_found = True
            if not price_found and any(k.lower() in name_lower for k in price_keywords):
                i = self.combo_price.findData(idx)
                if i >= 0:
                    self.combo_price.setCurrentIndex(i)
                price_found = True
            if spec_found and price_found:
                break

    def get_mapping(self):
        spec_idx = self.combo_spec.currentData()
        price_idx = self.combo_price.currentData()
        if spec_idx is None or price_idx is None:
            return None, None
        return int(spec_idx), int(price_idx)

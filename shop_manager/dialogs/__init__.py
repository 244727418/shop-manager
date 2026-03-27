# -*- coding: utf-8 -*-
"""对话框：操作记录、每日记录、店铺毛利、成本导入、API配置、成本库、利润、每日任务、规格等"""
from .records import OperationRecordDialog, DailyRecordDialog
from .store_margin import StoreMarginDialog
from .cost_import import CostImportDialog
from .cost_library import CostLibraryDialog
from .api_config import ApiConfigDialog
from .profit import ProfitAnalysisDialog, ProfitCalculatorDialog, ProfitHistoryDialog
from .daily_task import DailyTaskDialog
from .product_spec import ProductSpecDialog

__all__ = [
    "OperationRecordDialog",
    "DailyRecordDialog",
    "StoreMarginDialog",
    "CostImportDialog",
    "CostLibraryDialog",
    "ApiConfigDialog",
    "ProfitAnalysisDialog",
    "ProfitCalculatorDialog",
    "ProfitHistoryDialog",
    "DailyTaskDialog",
    "ProductSpecDialog",
]

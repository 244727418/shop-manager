# -*- coding: utf-8 -*-
"""对话框：操作记录、每日记录、店铺毛利、成本导入、API配置、成本库、利润、每日任务、规格等"""
_EXPORTS = {
    "OperationRecordDialog": ".records",
    "DailyRecordDialog": ".records",
    "StoreMarginDialog": ".store_margin",
    "CostImportDialog": ".cost_import",
    "CostLibraryDialog": ".cost_library",
    "MaterialLibraryDialog": ".material_library",
    "ApiConfigDialog": ".api_config",
    "ProfitAnalysisDialog": ".profit",
    "ProfitCalculatorDialog": ".profit",
    "ProfitHistoryDialog": ".profit",
    "DailyTaskDialog": ".daily_task",
    "TaskReminderPopupDialog": ".daily_task",
    "ProductSpecDialog": ".product_spec",
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "OperationRecordDialog",
    "DailyRecordDialog",
    "StoreMarginDialog",
    "CostImportDialog",
    "CostLibraryDialog",
    "MaterialLibraryDialog",
    "ApiConfigDialog",
    "ProfitAnalysisDialog",
    "ProfitCalculatorDialog",
    "ProfitHistoryDialog",
    "DailyTaskDialog",
    "TaskReminderPopupDialog",
    "ProductSpecDialog",
]

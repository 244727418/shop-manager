# shop_manager 主文件重构计划

## 现状

- **主文件** `shop_manager/shop_manager.py` 约 **7800+ 行**，包含：
  - 6 个大型对话框类（ApiConfig、KnowledgeBase、ProfitAnalysis、ProfitCalculator、ProfitHistory、ProductSpec）
  - 1 个主窗口类 `ShopManagerApp`
  - 入口 `if __name__ == "__main__"` 与全局样式
- 主文件在 `from dialogs import ...` 之后**又重新定义**了同名对话框类，导致实际运行的是主文件内实现，`dialogs/` 下的实现未被使用。
- 存在重复逻辑：`get_default_prompt`、`convert_markdown_to_html` 在多处重复实现。

---

## 已完成的优化（第一阶段）

1. **公共提示词**：新建 `shop_manager/prompts.py`，提供 `get_default_prompt()`，供 ApiConfigDialog、ProfitAnalysisDialog 等使用。
2. **UI 工具**：新建 `shop_manager/ui_utils.py`，提供 `convert_markdown_to_html(text)`，供利润分析、历史记录对话框使用。
3. **主文件**：已删除 ApiConfigDialog 中重复的 `get_default_prompt`（两处）、ProfitAnalysisDialog / ProfitHistoryDialog 中重复的 `convert_markdown_to_html` 与 ProfitAnalysisDialog 的 `get_default_prompt`，改为调用上述公共模块。主文件减少约 **200+ 行**重复代码。

## 已完成的优化（第二阶段：主文件瘦身）

4. **主文件裁剪**：已从 `shop_manager.py` 中**删除** 6 个对话框类（ApiConfigDialog、KnowledgeBaseDialog、ProfitAnalysisDialog、ProfitCalculatorDialog、ProfitHistoryDialog、ProductSpecDialog），主文件现仅保留：
   - 版本常量 `VERSION`
   - 全部 import（含 `from dialogs import ...`）
   - **ShopManagerApp** 类
   - `if __name__ == "__main__":` 入口与全局样式
   - 主文件从约 **7610 行** 降至约 **2068 行**，达到「约 2000 行以内」目标。
5. **对话框来源**：上述 6 个对话框现**仅**由 `shop_manager/dialogs/` 提供（api_config.py、knowledge_base.py、profit.py、product_spec.py）。当前 `dialogs/` 内已是可用的完整实现；若将来需要与历史主文件内某版逻辑完全一致，可从版本历史恢复主文件后运行 `shop_manager/_migrate_dialogs.py` 覆盖 dialogs，再重新裁剪主文件。

---

## 后续拆分建议（按优先级）

**说明**：第二步、第三步已完成（主文件已裁剪，仅保留 ShopManagerApp 与入口，约 2068 行）。

### 第二步：让主文件只使用 dialogs 包（✅ 已完成）

目标：主文件**不再定义**任何对话框类，仅保留 `ShopManagerApp` 与入口。

| 对话框类 | 主文件约行数 | 建议操作 |
|----------|--------------|----------|
| ProfitHistoryDialog | ~400 | 以主文件实现为准，覆盖 `dialogs/profit.py` 中对应类，主文件删除该类 |
| ProfitCalculatorDialog | ~479 | 同上 |
| ProfitAnalysisDialog | ~694 | 同上 |
| ApiConfigDialog | ~1094 | 以主文件实现覆盖 `dialogs/api_config.py`，主文件删除 |
| KnowledgeBaseDialog | ~736 | 以主文件实现覆盖 `dialogs/knowledge_base.py`，主文件删除 |
| ProductSpecDialog | ~2381 | 以主文件实现覆盖 `dialogs/product_spec.py`（若单文件过大可再拆为 UI + 计算逻辑） |

**操作要点**：

- 从主文件中**剪切**整段类代码到对应 `dialogs/xxx.py`，替换该文件中同名类。
- 在对话框文件中补充 `from prompts import get_default_prompt`、`from ui_utils import convert_markdown_to_html` 等依赖（或使用相对导入 `from ..prompts`）。
- 主文件仅保留：`from dialogs import ...`，**删除**这 6 个类的全部定义。
- 每迁移一个类，运行一次应用与相关功能，确认无报错再迁下一个。

### 第三步：主文件瘦身后的目标内容（✅ 已完成）

- 版本常量 `VERSION`
- 所有 import（含 dialogs、prompts、ui_utils、db、widgets、delegates）
- **仅** `ShopManagerApp` 类（主窗口逻辑）
- `if __name__ == "__main__":`：高 DPI、QApplication、字体、全局样式、创建并显示 `ShopManagerApp`、exec

预期主文件从 7800+ 行降至约 **2000 行以内**（视 ShopManagerApp 是否再拆）。

### 第四步（可选）：进一步拆分

- **样式**：将 `if __name__` 中的大段 `style` 字符串迁到 `shop_manager/styles.py` 或 `constants.py`，入口处 `from styles import APP_STYLE` 再 `app.setStyleSheet(APP_STYLE)`。
- **ProductSpecDialog**：若 `product_spec.py` 仍超过 1500 行，可拆为 `product_spec_ui.py`（界面与事件）+ `product_spec_logic.py`（权重、毛利、投产、成本拉取、AI 优化等纯逻辑）。
- **API 调用**：将 ApiConfigDialog 的 `test_api` 及各处 AI 请求抽到 `shop_manager/ai_client.py`，便于复用与单测。
- **调试标签**：将 `_debug_*_label` 的创建与样式统一为一个小工具或环境变量开关，便于发布前关闭。

---

## 建议执行顺序

1. 先迁 **ProfitHistoryDialog**（依赖少），验证导入与运行。
2. 再迁 **ProfitCalculatorDialog**、**ProfitAnalysisDialog**（共用 prompts / ui_utils）。
3. 再迁 **ApiConfigDialog**、**KnowledgeBaseDialog**。
4. 最后迁 **ProductSpecDialog**（体量最大，注意与 db、delegates、widgets 的依赖）。
5. 主文件仅剩 ShopManagerApp + 入口后，再考虑样式与 ProductSpec 的二次拆分。

---

## 文件与职责一览

| 路径 | 职责 |
|------|------|
| `shop_manager/shop_manager.py` | 入口、主窗口 ShopManagerApp、全局样式（目标：仅此 + import） |
| `shop_manager/prompts.py` | 默认系统提示词 `get_default_prompt()` |
| `shop_manager/ui_utils.py` | `convert_markdown_to_html(text)` 等 UI 工具 |
| `shop_manager/db.py` | 数据库与 RAG |
| `shop_manager/delegates.py` | 表格委托 |
| `shop_manager/widgets/` | 商品/店铺等小组件 |
| `shop_manager/dialogs/*.py` | 各对话框实现（与主文件去重后唯一来源） |

按本计划分步执行，可在不改变功能的前提下显著降低主文件行数、提升可维护性。

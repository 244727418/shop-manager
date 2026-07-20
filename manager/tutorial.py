# -*- coding: utf-8 -*-
"""只读功能目录与分步新手教程。"""
import math

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)


SCREEN_ANCHORS = {
    "main": {
        "tutorial": "btn_tutorial",
        "month_prev": "tutorial_prev_month",
        "month_next": "tutorial_next_month",
        "search": "search_input",
        "tag_filter": "btn_tag_filter",
        "store_filter": "btn_store_filter",
        "sort": "product_sort_combo",
        "main_area": "data_mode_scroll",
        "store_bubble": "@first_store_bubble",
        "product_bubble": "@first_product_bubble",
        "add_store": "tutorial_add_store",
        "daily_task": "btn_daily_task",
        "batch_export": "tutorial_batch_export",
        "cost": "btn_view_cost",
        "material": "btn_material_library",
        "promotion_mode": "btn_real_promotion_mode",
        "api": "btn_api_config",
        "account": "btn_switch_local_account",
        "archive": "btn_archive",
        "pdd": "btn_pinduoduo",
        "update": "btn_check_update",
    },
    "daily": {
        "overview": "result_table",
        "garbage": "btn_known_garbage",
        "reminders": "reminder_list",
    },
    "records": {"entry": "new_text_edit"},
    "store_margin": {
        "settings": "settings_widget",
        "date": "date_start_input",
        "manual": "btn_input_data",
        "images": "btn_weekly_images",
        "import": "btn_import_data",
        "table": "margin_data_table",
        "profit": "btn_profit_calc",
        "orders": "btn_import_orders",
        "history": "btn_history",
        "ai": "btn_ai_report",
        "promotion": "btn_promotion_data",
        "pdd": "btn_pdd_merchant_test",
        "export": "btn_export_excel",
        "save": "btn_save",
    },
    "margin_input": {
        "form": "input_form_widget",
        "preview": "btn_calculate",
        "save": "btn_confirm",
    },
    "product_spec": {
        "discount": "promo_widget",
        "roi": "roi_widget",
        "bid": "transaction_bid_input",
        "batch": "batch_price_controls",
        "profit": "btn_profit_calc",
        "summary": "btn_basic_info_summary",
        "promotion": "btn_promotion_history",
        "pdd_code": "btn_pdd_code_fetch",
        "pdd_price": "btn_pdd_price_fetch",
    },
    "cost": {
        "mode": "cost_mode_controls",
        "shipping": "btn_shipping_rules",
        "misc": "btn_misc_fee",
        "search": "search_input",
        "table": "table_view",
        "combos": "btn_link_combos",
        "cart": "listing_cart_widget",
        "price_test": "btn_price_test",
        "save": "btn_save",
    },
    "material": {
        "mode": "mode_button",
        "settings": "btn_settings",
        "search": "search_input",
        "back": "back_button",
        "pdf": "pdf_extract_button",
        "reference": "btn_prompts",
    },
    "promotion": {
        "date": "date_edit",
        "import": "btn_import",
        "history": "btn_history",
        "columns": "btn_columns",
        "table": "table",
    },
    "api": {
        "key": "api_key_input",
        "test": "btn_test_api",
        "profit_prompt": "btn_profit_prompt",
        "common_prompt": "btn_common_prompt",
        "spec_prompt": "btn_spec_prompt",
        "product_prompt": "btn_product_prompt",
    },
    "archive": {
        "accounts": "account_list",
        "add": "btn_add_account",
        "new": "btn_create_new_data",
        "save": "btn_save_archive",
        "read": "btn_read_archive",
        "path": "btn_set_local_path",
    },
    "settings": {
        "auto_start": "auto_start_checkbox",
        "hotkeys": "hotkey_panel",
        "window": None,
    },
}


def _step(anchor, title, text, example, screen=None):
    data = {"anchor": anchor, "title": title, "text": text, "example": example}
    if screen:
        data["screen"] = screen
    return data


def _topic(topic_id, category, title, summary, screen, *steps):
    return {
        "id": topic_id,
        "category": category,
        "title": title,
        "summary": summary,
        "screen": screen,
        "steps": list(steps),
    }


TUTORIAL_TOPICS = [
    _topic(
        "overview", "快速上手", "软件功能总览",
        "认识教程入口、主工作区和推荐使用顺序。", "main",
        _step("tutorial", "教程随时可重看", "右上角入口始终保留，不记录完成状态；默认 Ctrl+Shift+Z 可快速呼出主界面。", "示例：想复习成本库时，再次点击“功能教程”即可。"),
        _step("main_area", "主工作区", "主界面按店铺分组展示链接气泡，可直接查看店铺汇总和链接关键数据。", "示例：先建店铺和链接，再补成本、规格、推广和每日记录。"),
        _step("cost", "推荐第一步：成本库", "先维护规格编码、成本、重量和运费，后续毛利计算会自动引用。", "示例：规格 A 成本 12.50 元、重量 0.35kg。"),
        _step("archive", "最后记得存档", "账号与存档用于隔离和备份不同店铺数据。", "示例：工作完成后保存到“主店铺-2026”存档。"),
    ),
    _topic(
        "calendar_navigation", "主界面", "月份与数据卡片",
        "查看不同月份，并认识当前主界面的店铺行和链接气泡行。", "main",
        _step("month_prev", "切换月份", "使用上个月、下个月浏览对应月份的数据。", "示例：从 7 月切换到 6 月核对历史数据。"),
        _step("store_bubble", "店铺行", "这里显示当前首个可见店铺的汇总卡片；没有店铺时会高亮主工作区并说明前置条件。", "示例：旗舰店行显示链接数量、销售和利润概览。"),
        _step("product_bubble", "链接气泡行", "这里显示当前首个可见链接气泡，支持查看图片、备注、规格毛利和常用右键操作。", "示例：右键商品 123456 查看素材、利润或推广历史。"),
    ),
    _topic(
        "search_filters", "主界面", "搜索、排序与筛选",
        "快速定位商品，并按店铺、标签、利润和推广状态整理视图。", "main",
        _step("search", "实时搜索", "输入商品 ID、标题或备注，结果会自动高亮和筛选；Ctrl+F 可直接聚焦搜索框。", "示例：输入“夏季水杯”或商品 ID 123456。"),
        _step("tag_filter", "标签筛选", "可按商品类型、优惠、活动、推广方式和盈亏状态组合筛选。", "示例：只看“营销活动 + 亏钱”的链接。"),
        _step("store_filter", "店铺筛选", "只显示指定店铺，适合多店铺账号。", "示例：仅查看“旗舰店”和“测试店”。"),
        _step("sort", "链接排序", "支持按单量、净利润、净利率、毛利率、投产等指标排序。", "示例：按净利润排序，优先处理亏损链接。"),
    ),
    _topic(
        "stores_links", "店铺与链接", "店铺和链接管理",
        "创建店铺与链接，维护名称、备注、图片、类型和常用右键操作。", "main",
        _step("add_store", "添加店铺", "创建店铺后，可在店铺右键菜单添加链接、查看推广和操作记录。", "示例：店铺名称“拼多多旗舰店”。"),
        _step("store_bubble", "店铺卡操作", "双击店铺名可改名；右键可添加链接、抓取数据、查看推广或删除。", "示例：右键店铺 → 添加链接 → 输入商品 ID。"),
        _step("product_bubble", "链接卡操作", "链接支持图片、备注、复制 ID、规格毛利、素材、推广历史和快速利润。", "示例：右键商品 123456 → 快速计算利润。"),
    ),
    _topic(
        "records_tasks", "记录与任务", "操作记录与每日任务",
        "记录每天做过的事情，并集中处理提醒、待办和异常链接。", "records",
        _step("entry", "操作记录", "从店铺或链接气泡的右键菜单进入，可按日期添加时间与操作内容；教程不会点击保存。", "示例：10:30 调整主图；14:00 优化投产至 3.2。"),
        _step("overview", "每日任务大盘", "集中查看店铺任务、链接任务、废物链接和垃圾链接。", "示例：今日待办：检查近两条推广数据均为 0 的链接。", screen="daily"),
        _step("reminders", "定时提醒", "任务可以设置提醒时间，到时弹出提示并可标记完成。", "示例：今天 16:00 提醒复查价格。", screen="daily"),
    ),
    _topic(
        "store_margin", "毛利与利润", "店铺毛利管理",
        "录入或导入经营数据，查看毛利、订单、历史、AI 报告和推广分析。", "store_margin",
        _step("settings", "店铺计算参数", "维护全站投产与店铺满减规则，作为利润计算基础。", "示例：满 50 减 5，全站投产目标 3.0。"),
        _step("table", "毛利数据表", "按日期查看真实客单、推广消耗、利润和净利率。", "示例：净利润 128 元，净利率 12.8%。"),
        _step("orders", "导入订单", "导入订单后可按实际单量生成规格权重；教程不会打开文件选择器。", "示例：规格红色占订单 60%，蓝色占 40%。"),
        _step("history", "订单导入历史", "“全部记录”只查看导入订单产生的规格毛利、单量和售卖权重历史。", "示例：核对红色规格 60%、蓝色规格 40% 的权重来源。"),
        _step("ai", "AI 报告", "根据当前店铺毛利数据生成经营分析；教程不会调用 API。", "示例：报告建议降低亏损链接出价 5%。"),
    ),
    _topic(
        "product_spec", "毛利与利润", "规格与链接毛利",
        "维护优惠、活动、投产、出价、退货率、规格价格和权重。", "product_spec",
        _step("discount", "优惠与活动", "整块促销区域包含优惠券、新客立减、店铺满减、限时活动和营销活动，都会影响成交价或活动标记。", "示例：售价 29.9 元，优惠券减 3 元，并开启限时活动。"),
        _step("roi", "投产与出价", "可使用投产模式或出价模式，系统结合毛利和退货率计算结果。", "示例：当前投产 3.2，退货率 8%。"),
        _step("batch", "规格筛选与批量改价", "先通过规格表头筛选可见规格，再按固定售价、折扣、增减金额或目标毛利率批量修改价格。", "示例：把筛选出的红色规格售价统一设置为 29.9 元。"),
        _step("profit", "利润计算", "打开利润计算器，并自动带入当前综合毛利、客单价和退款率。", "示例：预计每单利润 4.62 元，保本投产 2.7。"),
    ),
    _topic(
        "cost_library", "资料库", "成本库完整工作流",
        "管理商品类型、规格成本、运费杂费、链接组合、上架车与测价。", "cost",
        _step("mode", "成本模式与费用规则", "总成本模式直接维护成本；明细模式拆分货品、运费和杂费。默认 Ctrl+Shift+C 可快速呼出成本库。", "示例：货品 10 元 + 运费 1.7 元 + 杂费 0.45 元。"),
        _step("search", "搜索规格", "按商品类型、商品名称或规格编码搜索，支持用空格分隔多个关键词。", "示例：搜索“水杯 RED”同时限定商品和规格。"),
        _step("table", "成本表", "维护规格的商品类型、名称、编码、成本、重量和库存属性。", "示例：规格 SKU-RED-M 总成本 12.15 元。"),
        _step("combos", "链接组合", "打开链接组合窗口，把多个成本规格整理为销售链接组合。", "示例：红色 M + 蓝色 M 组成“夏季组合链接”。"),
        _step("cart", "上架车", "Ctrl+单击规格可加入或移出上架车，再用所选规格创建链接。", "示例：把红色 M、蓝色 M 加入上架车后创建组合链接。"),
        _step("price_test", "测价", "打开测价窗口，组合规格数量和售价，预览成本与毛利结果。", "示例：目标毛利率 35%，比较 24.9 元和 29.9 元售价。"),
    ),
    _topic(
        "material_library", "资料库", "素材库完整工作流",
        "按产品、商品类型或链接整理图片、PSD、PDF 和参考提示词。", "material",
        _step("settings", "设置素材母文件夹", "分别设置产品素材库和链接素材库位置。", "示例：D:\\店铺素材\\产品素材库。"),
        _step("mode", "产品与链接模式", "产品模式按分类和规格管理，链接模式按店铺链接管理。默认 Ctrl+Shift+S 呼出素材库；窗口内按 Tab 或 Shift+Tab 可切换两种素材库。", "示例：Ctrl+Shift+S 呼出素材库，再按 Tab 从产品素材库切换到链接素材库。"),
        _step("search", "多关键词搜索", "可搜索商品类型、规格名称、规格编码或链接；支持拼音、首字母，并用空格分隔多个关键词。", "示例：输入“水杯 RED”同时匹配水杯分类和红色规格。"),
        _step("pdf", "PDF 图片提取", "从供应商 PDF 中提取图片并放入当前素材目录。", "示例：从供应商 PDF 提取 6 张产品图。"),
        _step("reference", "通用参考", "管理通用参考图和常用提示词，供不同商品素材制作时复用。", "示例：保存一组白底主图参考和常用修图提示词。"),
    ),
    _topic(
        "promotion_orders", "推广与报表", "推广数据与订单分析",
        "按日期导入推广数据，对比链接表现并查看历史趋势。", "promotion",
        _step("date", "选择导入日期", "选择要查看或导入的单日推广数据日期。", "示例：选择 7 月 7 日查看当天表现。"),
        _step("import", "导入推广数据", "选择平台推广表并匹配字段；教程只高亮入口，不打开文件。", "示例：导入 7 月 7 日推广数据表。"),
        _step("table", "推广指标表", "查看曝光、点击、花费、成交、投产、净利润和净利率。", "示例：花费 300 元，成交 1200 元，投产 4.0。"),
        _step("history", "历史与 AI 总结", "查看全部导入记录、商品趋势，并可在历史窗口生成 AI 总结。", "示例：近七天点击率下降，建议先优化主图。"),
        _step("columns", "列设置", "调整推广指标列的显示顺序，图片列和操作列保持固定。", "示例：把净利润和净利率移动到投产后面。"),
        _step("promotion_mode", "主界面真实推广模式", "打开后，各店铺卡片显示最近导入的真实推广指标。", "示例：直接在主界面比较各店铺最近净利润。", screen="main"),
    ),
    _topic(
        "reports_exports", "推广与报表", "每周算账录入与导出",
        "重点讲解每周常用的手工录入、附带图片和导出；历史批量导入仅用于一次性补齐漏录数据。", "store_margin",
        _step("manual", "每周录入数据（常用）", "先选择本周数据周期，再点击“录入数据”。这是以后每周更新店铺算账数据的常用入口。", "示例：选择本周一至周日，录入本周经营数据。"),
        _step("form", "填写本周经营数据", "依次填写实发订单、实发金额、毛利润、退款、推广费、扣款和其他费用；空项按 0 处理。", "示例：实发 100 单、金额 3000 元、毛利润 900 元、推广费 300 元。", screen="margin_input"),
        _step("preview", "计算并预览", "计算毛利率、退款率、件单价、推广占比、净利润和净利率，确认数值合理后再保存。", "示例：预览净利润 520 元、净利率 17.33%。", screen="margin_input"),
        _step("save", "确认保存", "正式使用时确认预览无误再保存到所选周期；教程只高亮按钮，不会保存示例。", "示例：确认周期和结果后保存本周数据。", screen="margin_input"),
        _step("images", "上传本周图片素材", "返回店铺毛利窗口打开“本周附带图片”，在图片格悬停后按 Ctrl+V 粘贴后台截图；导出时会附带原图。", "示例：粘贴本周经营概览、退款分析和推广消耗截图。"),
        _step("table", "核对本周结果", "保存后在顶部毛利数据表核对客单、推广消耗、利润和净利率。", "示例：核对本周净利润 520 元、净利率 17.33%。"),
        _step("export", "导出本周算账数据", "导出包含本周算账数据和附带图片的 Excel；完整报表还会附带商品权重与规格售卖页面。", "示例：导出“旗舰店-本周毛利.xlsx”。"),
        _step("import", "补录历史算账数据（低频）", "仅在以前某周漏录、需要一次性批量补齐过往所有计算数据时使用；完成首次补录后，日常每周更新不再需要这个入口。", "示例：首次使用时一次性导入过去 12 周算账表，之后改用“录入数据”。"),
        _step("batch_export", "批量导出店铺", "主界面可一次选择多个店铺，导出详细版或多 Sheet 简化版。", "示例：一次导出旗舰店、专营店本月毛利。", screen="main"),
    ),
    _topic(
        "pdd_tools", "拼多多工具", "拼多多抓取与同步",
        "从店铺或链接进入商家端抓取编码、价格和推广状态。", "main",
        _step("pdd", "打开商家后台", "按当前店铺打开拼多多商家后台；教程不会启动浏览器。", "示例：选择旗舰店后打开对应登录环境。"),
        _step("store_bubble", "店铺抓取入口", "店铺右键可抓取添加编码、价格管理和推广状态。", "示例：抓取价格后先核对匹配状态，再决定是否同步。"),
        _step("product_bubble", "链接级同步", "规格毛利窗口可针对当前链接抓取编码或价格。", "示例：商品 123456 匹配到 3 个在线规格。"),
    ),
    _topic(
        "api_ai", "系统与账号", "API 与 AI 功能",
        "配置 AI 服务，并维护利润分析、通用、规格和产品提示词。", "api",
        _step("key", "API Key", "填写并保存 AI 服务密钥；输入内容默认隐藏，教程不会保存。", "示例：粘贴 API Key 后保持隐藏显示。"),
        _step("test", "连接测试", "保存配置后可测试连通性；教程不会发送网络请求。", "示例：测试成功后再使用 AI 报告。"),
        _step("profit_prompt", "利润分析提示词", "利润分析模板决定报告结构和输出要求。", "示例：要求输出结论、风险和三条建议。"),
        _step("common_prompt", "通用提示词", "维护会自动附加到多个 AI 功能的运营常识。", "示例：所有报告都优先检查退款率和净利率。"),
        _step("spec_prompt", "规格优化提示词", "维护规格转化、属性和违禁词规则。", "示例：规格名保留容量，删除重复营销词。"),
        _step("product_prompt", "产品提示词", "维护产品层面的 AI 生成规则，并可恢复系统默认。", "示例：输出目标人群、卖点和标题建议。"),
    ),
    _topic(
        "accounts_archives", "系统与账号", "账号切换与本地存档",
        "隔离不同账号的数据，并保存、读取和管理本地存档。", "archive",
        _step("accounts", "账号列表", "每个账号对应独立数据，可创建空白数据或切换已有账号。", "示例：旗舰店、专营店分别使用独立数据库。"),
        _step("add", "添加存档账号", "创建新的本地存档账号；教程不会执行。", "示例：添加“测试店”账号。"),
        _step("new", "新建空白数据", "为选定账号创建一份不含店铺和链接的空白数据。", "示例：给“测试店”创建空白数据库。"),
        _step("save", "保存到存档", "保存当前账号数据作为备份；主界面也可按 Ctrl+S 快速保存。", "示例：保存到“旗舰店-20260714”存档。"),
        _step("read", "读取存档", "读取会恢复存档内容，正式操作前应确认当前账号。", "示例：恢复“旗舰店-20260714”存档。"),
        _step("path", "存档母文件夹", "统一设置本机存档目录，并可快速打开文件夹。", "示例：D:\\店铺管理工具存档。"),
        _step("account", "主界面快速切换账号", "状态栏可以直接切换当前本地账号数据。", "示例：从旗舰店切换到专营店，界面重新加载对应数据。", screen="main"),
    ),
    _topic(
        "settings_shortcuts", "系统与账号", "托盘、快捷键与开机自启",
        "设置后台快速呼出、开机启动和系统托盘使用方式。", "settings",
        _step("auto_start", "开机自启", "默认开启；取消勾选并保存后不会随 Windows 启动。教程不会修改。", "示例：开机后静默进入托盘，不弹出主窗口。"),
        _step("hotkeys", "全局快捷键", "主界面、成本库和素材库都有可修改的快速呼出快捷键。", "示例：Ctrl+Shift+Z 呼出主界面。"),
        _step("window", "系统托盘", "关闭主窗口会进入托盘；双击托盘显示，右键可设置或退出。", "示例：右键托盘 → 设置 → 修改快捷键。"),
    ),
    _topic(
        "software_update", "系统与账号", "检查软件更新",
        "普通用户可以检查并安装收到的新版本。", "main",
        _step("update", "检查更新", "检查已收到或服务器上的新版；教程不会联网或下载。", "示例：发现 v5.8 后查看版本说明，再确认安装。"),
        _step("tutorial", "教程随功能同步", "功能目录和教程步骤来自同一份注册表，新增功能时必须补齐对应步骤。", "示例：新增报表入口时，同时注册“报表”教程锚点和示例。"),
    ),
]


def validate_tutorial_catalog(topics=None):
    topics = topics or TUTORIAL_TOPICS
    seen = set()
    for topic in topics:
        topic_id = str(topic.get("id") or "").strip()
        if not topic_id or topic_id in seen:
            raise ValueError(f"教程功能 ID 无效或重复: {topic_id}")
        seen.add(topic_id)
        screen = topic.get("screen")
        if screen not in SCREEN_ANCHORS:
            raise ValueError(f"未知教程界面: {screen}")
        if not all(str(topic.get(key) or "").strip() for key in ("category", "title", "summary")):
            raise ValueError(f"教程功能信息不完整: {topic_id}")
        steps = topic.get("steps") or []
        if not steps:
            raise ValueError(f"教程没有步骤: {topic_id}")
        for step in steps:
            step_screen = step.get("screen", screen)
            if step_screen not in SCREEN_ANCHORS:
                raise ValueError(f"未知步骤界面: {topic_id}/{step_screen}")
            if step.get("anchor") not in SCREEN_ANCHORS[step_screen]:
                raise ValueError(f"未知教程锚点: {topic_id}/{step_screen}/{step.get('anchor')}")
            if not all(str(step.get(key) or "").strip() for key in ("title", "text", "example")):
                raise ValueError(f"教程步骤信息不完整: {topic_id}/{step.get('title')}")
    return True


validate_tutorial_catalog()


class TutorialCatalogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_topic_id = ""
        self.setWindowTitle("📖 功能教程")
        self.resize(860, 580)
        self.setMinimumSize(760, 500)

        root = QVBoxLayout(self)
        title = QLabel("功能教程")
        title.setStyleSheet("font-size:22px; font-weight:700; color:#243447;")
        root.addWidget(title)
        note = QLabel("选择功能即可进入只读分步教程。教程不会保存示例，也不会触发导入、同步或网络操作。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#587087; padding-bottom:8px;")
        root.addWidget(note)

        body = QHBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(300)
        self.tree.setStyleSheet("QTreeWidget{border:1px solid #d9e2e8;border-radius:8px;padding:6px;} QTreeWidget::item{height:30px;} QTreeWidget::item:selected{background:#dcefe6;color:#234f3d;}")
        categories = {}
        category_counts = {}
        for topic in TUTORIAL_TOPICS:
            parent_item = categories.get(topic["category"])
            if parent_item is None:
                parent_item = QTreeWidgetItem([topic["category"]])
                parent_item.setFlags(parent_item.flags() & ~Qt.ItemIsSelectable)
                categories[topic["category"]] = parent_item
                self.tree.addTopLevelItem(parent_item)
            category_counts[topic["category"]] = category_counts.get(topic["category"], 0) + 1
            item = QTreeWidgetItem([f"{category_counts[topic['category']]}. {topic['title']}"])
            item.setData(0, Qt.UserRole, topic["id"])
            parent_item.addChild(item)
        self.tree.expandAll()
        body.addWidget(self.tree, 2)

        detail = QFrame()
        detail.setStyleSheet("QFrame{background:#f7faf8;border:1px solid #d9e7df;border-radius:10px;}")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(24, 24, 24, 24)
        self.detail_title = QLabel("选择一个功能")
        self.detail_title.setStyleSheet("font-size:20px;font-weight:700;color:#244a3a;border:none;")
        self.detail_summary = QLabel("左侧列出了软件当前面向普通用户的主要功能区。")
        self.detail_summary.setWordWrap(True)
        self.detail_summary.setStyleSheet("font-size:14px;color:#455d52;line-height:1.5;border:none;")
        self.detail_steps = QLabel("")
        self.detail_steps.setWordWrap(True)
        self.detail_steps.setStyleSheet("color:#6b7e74;border:none;")
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_summary)
        detail_layout.addWidget(self.detail_steps)
        detail_layout.addStretch()
        self.start_button = QPushButton("开始教程")
        self.start_button.setEnabled(False)
        self.start_button.setFixedHeight(38)
        self.start_button.setStyleSheet("QPushButton{background:#3f8b68;color:white;border:none;border-radius:7px;font-weight:700;} QPushButton:hover{background:#34775a;} QPushButton:disabled{background:#b8c4be;}")
        detail_layout.addWidget(self.start_button)
        body.addWidget(detail, 3)
        root.addLayout(body, 1)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(close_button)
        root.addLayout(footer)

        self.tree.currentItemChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(lambda *_args: self._start_selected())
        self.start_button.clicked.connect(self._start_selected)

    def _selection_changed(self, item, _previous):
        topic_id = str(item.data(0, Qt.UserRole) or "") if item else ""
        topic = next((row for row in TUTORIAL_TOPICS if row["id"] == topic_id), None)
        self.selected_topic_id = topic_id if topic else ""
        self.start_button.setEnabled(bool(topic))
        if not topic:
            return
        self.detail_title.setText(item.text(0))
        self.detail_summary.setText(topic["summary"])
        self.detail_steps.setText(f"共 {len(topic['steps'])} 步 · 可随时按 Esc 退出 · 示例仅供观看")

    def _start_selected(self):
        if self.selected_topic_id:
            self.accept()


class TutorialOverlay(QWidget):
    previousRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    exitRequested = pyqtSignal()

    def __init__(self, host, target=None):
        super().__init__(host)
        self.host = host
        self.target = target
        self.phase = 0.0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setGeometry(host.rect())
        host.installEventFilter(self)

        self.card = QFrame(self)
        self.card.setMinimumWidth(420)
        self.card.setMaximumWidth(420)
        self.card.setStyleSheet("QFrame{background:white;border:1px solid #d5ded9;border-radius:12px;} QLabel{border:none;background:transparent;}")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 18, 20, 16)
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("color:#718078;font-size:12px;")
        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color:#244a3a;font-size:18px;font-weight:700;")
        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("color:#344a40;font-size:14px;")
        example_title = QLabel("示例（仅展示，不保存）")
        example_title.setStyleSheet("color:#8a6630;font-size:12px;font-weight:700;margin-top:6px;")
        self.example_label = QLabel()
        self.example_label.setWordWrap(True)
        self.example_label.setStyleSheet("background:#fff8e8;color:#6f552d;border:1px solid #f0dfb8;border-radius:7px;padding:9px;")
        card_layout.addWidget(self.progress_label)
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.text_label)
        card_layout.addWidget(example_title)
        card_layout.addWidget(self.example_label)

        buttons = QHBoxLayout()
        self.exit_button = QPushButton("退出")
        self.previous_button = QPushButton("上一步")
        self.next_button = QPushButton("下一步")
        self.next_button.setStyleSheet("QPushButton{background:#3f8b68;color:white;border:none;border-radius:6px;padding:7px 16px;font-weight:700;} QPushButton:hover{background:#34775a;}")
        buttons.addWidget(self.exit_button)
        buttons.addStretch()
        buttons.addWidget(self.previous_button)
        buttons.addWidget(self.next_button)
        card_layout.addLayout(buttons)

        self.exit_button.clicked.connect(self.exitRequested)
        self.previous_button.clicked.connect(self.previousRequested)
        self.next_button.clicked.connect(self.nextRequested)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate)
        self.animation_timer.start(40)

    def set_step(self, step, index, total, target=None, notice=""):
        self.target = target
        self.progress_label.setText(f"{index + 1} / {total}")
        self.title_label.setText(step["title"])
        text = step["text"]
        if notice:
            text = f"{notice}\n\n{text}"
        self.text_label.setText(text)
        self.example_label.setText(step["example"])
        self.previous_button.setEnabled(index > 0)
        self.next_button.setText("完成" if index + 1 == total else "下一步")
        self.card.adjustSize()
        self.setGeometry(self.host.rect())
        self._position_card()
        self.show()
        self.raise_()
        self.card.raise_()
        self.setFocus(Qt.OtherFocusReason)
        self.update()

    def _target_rect(self):
        target = self.target
        if target is None:
            return QRect()
        try:
            if not target.isVisible():
                return QRect()
            top_left = self.mapFromGlobal(target.mapToGlobal(QPoint(0, 0)))
            return QRect(top_left, target.size()).adjusted(-9, -9, 9, 9).intersected(self.rect())
        except RuntimeError:
            return QRect()

    def _position_card(self):
        self.card.adjustSize()
        width, height = self.card.width(), self.card.height()
        hole = self._target_rect()
        margin = 16
        if hole.isValid() and not hole.isEmpty():
            candidates = [
                QPoint(hole.left(), hole.bottom() + 18),
                QPoint(hole.right() - width, hole.bottom() + 18),
                QPoint(hole.left(), hole.top() - height - 18),
                QPoint(hole.right() - width, hole.top() - height - 18),
                QPoint(hole.right() + 18, hole.top()),
                QPoint(hole.right() + 18, hole.bottom() - height),
                QPoint(hole.left() - width - 18, hole.top()),
                QPoint(hole.left() - width - 18, hole.bottom() - height),
                QPoint(margin, margin),
                QPoint(self.width() - width - margin, margin),
                QPoint(margin, self.height() - height - margin),
                QPoint(self.width() - width - margin, self.height() - height - margin),
            ]
            best = None
            for point in candidates:
                point = QPoint(
                    max(margin, min(point.x(), self.width() - width - margin)),
                    max(margin, min(point.y(), self.height() - height - margin)),
                )
                card_rect = QRect(point.x(), point.y(), width, height)
                overlap = card_rect.intersected(hole.adjusted(-8, -8, 8, 8))
                overlap_area = max(0, overlap.width()) * max(0, overlap.height())
                if overlap_area == 0:
                    self.card.move(point)
                    return
                if best is None or overlap_area < best[0]:
                    best = (overlap_area, point)
            if best is not None:
                self.card.move(best[1])
                return
        self.card.move(
            max(margin, self.width() - width - margin),
            max(margin, self.height() - height - margin),
        )

    def _animate(self):
        self.phase = (self.phase + 0.04) % 1.0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        hole = self._target_rect()
        if hole.isValid() and not hole.isEmpty():
            path = QPainterPath()
            path.setFillRule(Qt.OddEvenFill)
            path.addRect(QRectF(self.rect()))
            path.addRoundedRect(QRectF(hole), 10, 10)
            painter.fillPath(path, QColor(8, 16, 22, 166))
            pulse = (math.sin(self.phase * math.pi * 2) + 1) / 2
            glow = hole.adjusted(-int(3 + pulse * 4), -int(3 + pulse * 4), int(3 + pulse * 4), int(3 + pulse * 4))
            painter.setPen(QPen(QColor(255, 196, 72, int(155 + pulse * 100)), 3 + pulse * 2))
            painter.drawRoundedRect(QRectF(glow), 13, 13)
        else:
            painter.fillRect(self.rect(), QColor(8, 16, 22, 166))

    def eventFilter(self, watched, event):
        if watched is self.host and event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
            self.setGeometry(self.host.rect())
            self._position_card()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.exitRequested.emit()
        elif event.key() in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.nextRequested.emit()
        elif event.key() == Qt.Key_Left:
            self.previousRequested.emit()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def closeEvent(self, event):
        self.animation_timer.stop()
        try:
            self.host.removeEventFilter(self)
        except RuntimeError:
            pass
        super().closeEvent(event)


class TutorialController(QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.topic = None
        self.step_index = 0
        self.overlay = None
        self.current_screen = ""
        self.current_window = None
        self.owned_windows = []

    def show_catalog(self):
        self._cleanup()
        dialog = TutorialCatalogDialog(self.main_window)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_topic_id:
            QTimer.singleShot(0, lambda topic_id=dialog.selected_topic_id: self.start_topic(topic_id))

    def start_topic(self, topic_id):
        self._cleanup()
        self.topic = next((row for row in TUTORIAL_TOPICS if row["id"] == topic_id), None)
        if not self.topic:
            return
        self.step_index = 0
        self._show_current_step()

    def _show_current_step(self):
        if not self.topic:
            return
        step = self.topic["steps"][self.step_index]
        screen = step.get("screen", self.topic["screen"])
        if screen == self.current_screen and self.current_window is not None:
            self._attach_overlay(self.current_window, screen, step, "")
            return

        self._close_overlay()
        previous_window = self.current_window
        if previous_window in self.owned_windows:
            self.owned_windows.remove(previous_window)
            try:
                previous_window.close()
            except RuntimeError:
                pass
        self.current_window = None
        self.current_screen = ""
        try:
            window, created, notice = self.main_window.open_tutorial_screen(screen)
        except Exception as error:
            window, created, notice = self.main_window, False, f"对应界面暂时无法打开：{error}"
        if window is None:
            window, created = self.main_window, False
            notice = notice or "当前账号还没有该功能所需的数据，先查看示例和入口说明。"
        if created and window not in self.owned_windows:
            self.owned_windows.append(window)
        self.current_screen = screen
        self.current_window = window
        QTimer.singleShot(80, lambda w=window, s=screen, row=step, n=notice: self._attach_overlay(w, s, row, n))

    def _resolve_target(self, window, screen, anchor):
        target_name = SCREEN_ANCHORS[screen].get(anchor)
        if not target_name:
            return None
        if target_name.startswith("@"):
            resolver = getattr(self.main_window, "resolve_tutorial_target", None)
            return resolver(target_name[1:]) if callable(resolver) else None
        target = getattr(window, target_name, None)
        if isinstance(target, QWidget):
            return target
        try:
            return window.findChild(QWidget, target_name)
        except RuntimeError:
            return None

    def _attach_overlay(self, window, screen, step, notice):
        try:
            if window is None or not window.isVisible():
                window = self.main_window
            window.raise_()
            window.activateWindow()
            target = self._resolve_target(window, screen, step["anchor"])
            if self.overlay is None or self.overlay.parent() is not window:
                self._close_overlay()
                self.overlay = TutorialOverlay(window, target)
                self.overlay.previousRequested.connect(self.previous_step)
                self.overlay.nextRequested.connect(self.next_step)
                self.overlay.exitRequested.connect(self.exit_tutorial)
            self.overlay.set_step(step, self.step_index, len(self.topic["steps"]), target, notice)
        except RuntimeError:
            self.current_screen = ""
            self.current_window = None
            QTimer.singleShot(0, self._show_current_step)

    def previous_step(self):
        if self.topic and self.step_index > 0:
            self.step_index -= 1
            self._show_current_step()

    def next_step(self):
        if not self.topic:
            return
        if self.step_index + 1 < len(self.topic["steps"]):
            self.step_index += 1
            self._show_current_step()
            return
        self._cleanup()
        QTimer.singleShot(0, self.show_catalog)

    def exit_tutorial(self):
        self._cleanup()

    def _close_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.close()
                self.overlay.deleteLater()
            except RuntimeError:
                pass
        self.overlay = None

    def _cleanup(self):
        self._close_overlay()
        for window in reversed(self.owned_windows):
            try:
                window.close()
            except RuntimeError:
                pass
        self.owned_windows.clear()
        self.topic = None
        self.step_index = 0
        self.current_screen = ""
        self.current_window = None

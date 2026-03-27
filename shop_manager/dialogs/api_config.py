# -*- coding: utf-8 -*-
"""API配置对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QComboBox, QTextEdit, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView,
)
from PyQt5.QtCore import Qt


class ApiConfigDialog(QDialog):
    """API配置对话框"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("🔑 API配置")
        self.resize(650, 600)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ===== 临时调试标签 =====
        self._debug_api_label = QLabel("【板块:API配置对话框\n文件:api_config.py】API Key/系统提示词/模板选择")
        self._debug_api_label.setStyleSheet("background-color: #DDA0DD; color: #000; font-weight: bold; padding: 1px;")
        self._debug_api_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._debug_api_label)

        header = QLabel("🤖 AI API 配置")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info_label = QLabel("💡 支持DeepSeek、OpenAI等兼容API（国内推荐DeepSeek）")
        info_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        layout.addWidget(info_label)

        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("请输入API Key...")
        self.api_key_input.setMinimumWidth(300)
        api_key_layout.addWidget(self.api_key_input)

        self.btn_show_key = QPushButton("👁")
        self.btn_show_key.setFixedWidth(30)
        self.btn_show_key.clicked.connect(self.toggle_key_visibility)
        api_key_layout.addWidget(self.btn_show_key)
        layout.addLayout(api_key_layout)

        self.btn_save_api = QPushButton("💾 保存API Key")
        self.btn_save_api.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 20px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.btn_save_api.clicked.connect(self.save_api_key)
        layout.addWidget(self.btn_save_api)

        self.btn_load_system_prompt = QPushButton("📥 加载系统提示词")
        self.btn_load_system_prompt.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 20px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        self.btn_load_system_prompt.clicked.connect(self.load_system_prompts)
        layout.addWidget(self.btn_load_system_prompt)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #dee2e6;")
        layout.addWidget(separator)

        template_title = QLabel("📝 提示词模板管理")
        template_title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px 0 5px 0;")
        layout.addWidget(template_title)

        template_select_layout = QHBoxLayout()
        template_select_layout.addWidget(QLabel("选择模板:"))

        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(200)
        self.template_combo.currentIndexChanged.connect(self.on_template_selected)
        template_select_layout.addWidget(self.template_combo)

        self.btn_apply_template = QPushButton("✅ 应用")
        self.btn_apply_template.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.btn_apply_template.clicked.connect(self.apply_template)
        template_select_layout.addWidget(self.btn_apply_template)

        self.btn_new_template = QPushButton("➕ 新建模板")
        self.btn_new_template.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.btn_new_template.clicked.connect(self.new_template)
        template_select_layout.addWidget(self.btn_new_template)

        template_select_layout.addStretch()
        layout.addLayout(template_select_layout)

        self.active_label = QLabel("当前生效: ")
        self.active_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 5px 0;")
        layout.addWidget(self.active_label)

        self.prompt_text = QTextEdit()
        self.prompt_text.setPlaceholderText("请输入提示词模板...\n使用 {推广费}, {投产比}, {退货率} 等占位符")
        self.prompt_text.setMinimumHeight(180)
        self.prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.prompt_text)

        prompt_btn_layout = QHBoxLayout()

        self.btn_save_prompt = QPushButton("💾 保存当前模板")
        self.btn_save_prompt.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 20px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.btn_save_prompt.clicked.connect(self.save_current_template)
        prompt_btn_layout.addWidget(self.btn_save_prompt)

        self.btn_delete_template = QPushButton("🗑️ 删除模板")
        self.btn_delete_template.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 20px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.btn_delete_template.clicked.connect(self.delete_template)
        prompt_btn_layout.addWidget(self.btn_delete_template)

        prompt_btn_layout.addStretch()
        layout.addLayout(prompt_btn_layout)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("color: #dee2e6; margin-top: 10px;")
        layout.addWidget(separator2)

        common_prompt_title = QLabel("📌 通用提示词（运营常识）")
        common_prompt_title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px 0 5px 0;")
        layout.addWidget(common_prompt_title)

        common_info = QLabel("💡 这些提示词会在AI分析时自动附加，提供拼多多运营常识和时效性技巧")
        common_info.setStyleSheet("color: #6c757d; font-size: 11px; padding: 2px 0;")
        layout.addWidget(common_info)

        self.common_prompt_list = QListWidget()
        self.common_prompt_list.setMinimumHeight(100)
        self.common_prompt_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.common_prompt_list)

        common_btn_layout = QHBoxLayout()

        self.btn_add_common = QPushButton("➕ 添加")
        self.btn_add_common.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 5px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.btn_add_common.clicked.connect(self.add_common_prompt)
        common_btn_layout.addWidget(self.btn_add_common)

        self.btn_edit_common = QPushButton("✏️ 编辑")
        self.btn_edit_common.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                padding: 5px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.btn_edit_common.clicked.connect(self.edit_common_prompt)
        common_btn_layout.addWidget(self.btn_edit_common)

        self.btn_delete_common = QPushButton("🗑️ 删除")
        self.btn_delete_common.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 5px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.btn_delete_common.clicked.connect(self.delete_common_prompt)
        common_btn_layout.addWidget(self.btn_delete_common)

        common_btn_layout.addStretch()
        layout.addLayout(common_btn_layout)

        test_layout = QHBoxLayout()

        self.btn_test_api = QPushButton("🔧 测试API连接")
        self.btn_test_api.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                padding: 8px 20px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """)
        self.btn_test_api.clicked.connect(self.test_api)
        test_layout.addWidget(self.btn_test_api)

        self.test_result_label = QLabel("")
        self.test_result_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        test_layout.addWidget(self.test_result_label)
        test_layout.addStretch()
        layout.addLayout(test_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def toggle_key_visibility(self):
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.btn_show_key.setText("🔒")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.btn_show_key.setText("👁")

    def load_settings(self):
        if self.db:
            self.api_key = self.db.get_setting("ai_api_key", "") or ""
            self.api_key_input.setText(self.api_key)

            self.load_templates()
            self.load_common_prompts()

    def load_templates(self):
        current_prompt_id = None
        if self.template_combo.currentIndex() >= 0:
            current_prompt_id = self.template_combo.itemData(self.template_combo.currentIndex())

        self.template_combo.blockSignals(True)
        self.template_combo.clear()

        prompts = self.db.get_all_prompts()
        self.prompt_data = {}

        for p in prompts:
            prompt_id, name, content, is_active, is_system = p
            self.prompt_data[prompt_id] = {"name": name, "content": content, "is_active": is_active, "is_system": is_system}

            display_name = name
            if is_active:
                display_name = f"✓ {name}"
            if is_system:
                display_name = f"[系统] {name}"

            self.template_combo.addItem(display_name, prompt_id)

            if is_active:
                self.prompt_text.setPlainText(content)
                self.active_prompt_id = prompt_id

        if not prompts:
            default_prompt = self.get_default_prompt()
            self.prompt_text.setPlainText(default_prompt)

        if current_prompt_id and current_prompt_id in self.prompt_data:
            for i in range(self.template_combo.count()):
                if self.template_combo.itemData(i) == current_prompt_id:
                    self.template_combo.setCurrentIndex(i)
                    self.prompt_text.setPlainText(self.prompt_data[current_prompt_id]["content"])
                    break

        self.template_combo.blockSignals(False)
        self.update_active_label()

    def update_active_label(self):
        active_name = "无"
        for pid, data in self.prompt_data.items():
            if data.get("is_active"):
                active_name = data.get("name", "未知")
                break
        self.active_label.setText(f"当前生效: {active_name}")

    def load_common_prompts(self):
        self.common_prompt_list.clear()

        prompts = self.db.get_all_common_prompts()
        self.common_prompt_data = {}

        for p in prompts:
            prompt_id, content, is_active, sort_order = p
            self.common_prompt_data[prompt_id] = {"content": content, "is_active": is_active}

            display = content
            if len(display) > 60:
                display = display[:60] + "..."
            if not is_active:
                display = f"[禁用] {display}"

            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, prompt_id)
            self.common_prompt_list.addItem(item)

    def add_common_prompt(self):
        text, ok = QInputDialog.getText(self, "添加通用提示词", "请输入运营常识或技巧:")
        if not ok or not text.strip():
            return

        self.db.add_common_prompt(text.strip())
        self.load_common_prompts()
        QMessageBox.information(self, "✅ 成功", "通用提示词已添加！")

    def edit_common_prompt(self):
        current_row = self.common_prompt_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要编辑的提示词！")
            return

        item = self.common_prompt_list.item(current_row)
        prompt_id = item.data(Qt.UserRole)

        if prompt_id in self.common_prompt_data:
            old_content = self.common_prompt_data[prompt_id]["content"]
            text, ok = QInputDialog.getText(self, "编辑通用提示词", "请输入运营常识或技巧:", text=old_content)
            if not ok or not text.strip():
                return

            self.db.update_common_prompt(prompt_id, text.strip())
            self.load_common_prompts()
            QMessageBox.information(self, "✅ 成功", "通用提示词已更新！")

    def delete_common_prompt(self):
        current_row = self.common_prompt_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的提示词！")
            return

        item = self.common_prompt_list.item(current_row)
        prompt_id = item.data(Qt.UserRole)

        reply = QMessageBox.question(self, "确认删除", "确定要删除这条通用提示词吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_common_prompt(prompt_id)
            self.load_common_prompts()
            QMessageBox.information(self, "✅ 成功", "通用提示词已删除！")

    def on_template_selected(self, index):
        if index < 0:
            return
        prompt_id = self.template_combo.itemData(index)
        if prompt_id and prompt_id in self.prompt_data:
            self.prompt_text.setPlainText(self.prompt_data[prompt_id]["content"])

    def apply_template(self):
        index = self.template_combo.currentIndex()
        if index < 0:
            QMessageBox.warning(self, "提示", "请先选择一个模板！")
            return

        prompt_id = self.template_combo.itemData(index)

        self.db.set_active_prompt(prompt_id)

        self.load_templates()

        QMessageBox.information(self, "✅ 成功", "模板已应用！\n\nAI分析将使用新模板。")

    def new_template(self):
        name, ok = QInputDialog.getText(self, "新建模板", "请输入模板名称:")
        if not ok or not name.strip():
            return

        content = self.prompt_text.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "提示", "请先填写模板内容！")
            return

        self.db.save_prompt(name.strip(), content, False)
        self.load_templates()

        QMessageBox.information(self, "✅ 成功", f"模板「{name}」已创建！")

    def save_current_template(self):
        index = self.template_combo.currentIndex()

        if index >= 0:
            prompt_id = self.template_combo.itemData(index)
            content = self.prompt_text.toPlainText().strip()

            if prompt_id in self.prompt_data:
                old_name = self.prompt_data[prompt_id]["name"]
                self.db.update_prompt(prompt_id, old_name, content)
                QMessageBox.information(self, "✅ 成功", "模板已更新！")
                self.load_templates()
                return

        name, ok = QInputDialog.getText(self, "保存模板", "请输入模板名称:")
        if not ok or not name.strip():
            return

        content = self.prompt_text.toPlainText().strip()
        self.db.save_prompt(name.strip(), content, False)
        self.load_templates()
        QMessageBox.information(self, "✅ 成功", f"模板「{name}」已保存！")

    def delete_template(self):
        index = self.template_combo.currentIndex()
        if index < 0:
            QMessageBox.warning(self, "提示", "请先选择一个模板！")
            return

        prompt_id = self.template_combo.itemData(index)

        if prompt_id in self.prompt_data:
            if self.prompt_data[prompt_id].get("is_system"):
                QMessageBox.warning(self, "提示", "系统模板无法删除！")
                return

            reply = QMessageBox.question(self, "确认删除",
                f"确定要删除模板「{self.prompt_data[prompt_id]['name']}」吗？",
                QMessageBox.Yes | QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.db.delete_prompt(prompt_id)
                self.load_templates()
                QMessageBox.information(self, "✅ 成功", "模板已删除！")

    def save_api_key(self):
        if self.db:
            self.api_key = self.api_key_input.text().strip()
            self.db.set_setting("ai_api_key", self.api_key)
        QMessageBox.information(self, "✅ 成功", "API Key 已保存！")

    def load_system_prompts(self):
        if not self.db:
            QMessageBox.warning(self, "提示", "数据库未连接！")
            return

        reply = QMessageBox.question(
            self, "确认",
            "确定要加载系统提示词吗？\n这将删除所有现有提示词并恢复为系统默认的三个模板。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            default_prompts = [
                ("专业深度分析", """你是一位资深拼多多电商运营专家，拥有多年类目运营经验。请根据以下完整的推广数据，给出专业、深入、可操作的分析建议。

【分析对象】
{分析对象信息}

【今日战绩】
推广费：{推广费}元
投产比：{投产比}
退货率：{退货率}%
毛利率：{毛利率}%
客单价：{客单价}元

【自动计算出的数据】
成交金额：{成交金额}元
退款金额：{退款金额}元
实际成交：{实际成交}元
产品成本：{产品成本}元
毛利润：{毛利润}元
技术服务费：{技术服务费}元
净利润：{净利润}元
净利率：{净利率}%
推广占比：{推广占比}%
成交单量：{成交单量}单
每笔成交花费：{每笔成交花费}元/单
单笔利润：{单笔利润}元/单

【保本情况】
毛保本投产：{毛保本投产}
净保本投产：{净保本投产}
净保本1.25倍：{净保本1.25倍}
最佳投产：{最佳投产}
当前投产倍数：{当前投产倍数}

请按以下格式输出，要求内容详实、数据支撑、实用可执行：

📊 【盈利状况诊断】
（分析当前是否盈利，亏损原因，盈利/亏损幅度，与行业平均对比）

⚠️ 【问题点深度剖析】
（列出2-4个核心问题，每个问题要说明原因、影响程度、改进优先级）

🎯 【实战优化方案】
（列出3-5条具体可执行的优化建议，每条要包含：具体动作+预期效果+操作难度）

📈 【市场趋势与竞争分析】
（分析该类目当前市场趋势、竞争格局、消费者偏好变化、季节性因素等，提供前瞻性建议）

💎 【核心干货总结】
（用最精炼的语言总结2-3个最关键的决策点）

要求：
1. 数据必须完全准确，每项数据都要在分析中体现
2. 建议要具体可执行，避免空洞废话
3. 分析要深入本质，给出真正的干货
4. 适当引用行业经验和数据支撑
5. 总字数不少于500字，内容要充实详细""", True),

                ("贴吧老哥风格", """你是一位贴吧老哥风格的拼多多推广数据分析师，说话要接地气、带点调侃，用词犀利但不失专业。根据以下完整数据，给出一针见血的分析建议：

【分析对象】
{分析对象信息}

【今日战绩】
推广费：{推广费}元
投产比：{投产比}
退货率：{退货率}%
毛利率：{毛利率}%
客单价：{客单价}元

【自动计算出的数据】
成交金额：{成交金额}元
退款金额：{退款金额}元
实际成交：{实际成交}元
产品成本：{产品成本}元
毛利润：{毛利润}元
技术服务费：{技术服务费}元
净利润：{净利润}元
净利率：{净利率}%
推广占比：{推广占比}%
成交单量：{成交单量}单
每笔成交花费：{每笔成交花费}元/单
单笔利润：{单笔利润}元/单

【参考线】（这些是理论值，不是实际开的投产，别搞混了）
毛保本投产：{毛保本投产}（未扣服务费的保本线，特殊时期如起量阶段可参考）
净保本投产：{净保本投产}（扣了千6服务费后的保本线，常规开车参考此线）
净保本1.25倍：{净保本1.25倍}（安全线）
最佳投产：{最佳投产}（理想目标）
当前投产倍数：{当前投产倍数}（实际投产÷净保本，大于1就赚）

（列出3-5条条精简建议，每条尽量在60字，用数字序号，语气要像贴吧老哥指点江山）

要求：整体风格要像贴吧老哥，但数据要对得上，别瞎jb扯。""", True),

                ("简洁快速版", """你是拼多多数据分析助手。请根据以下数据给出简短分析建议：

【分析对象】
{分析对象信息}

【核心数据】
推广费：{推广费}元 | 投产比：{投产比} | 退货率：{退货率}%
毛利率：{毛利率}% | 客单价：{客单价}元
净利润：{净利润}元 | 净利率：{净利率}%
成交单量：{成交单量}单 | 单笔利润：{单笔利润}元/单

请简洁输出：
1. 盈利/亏损情况
2. 存在的主要问题（最多2个）
3. 优化建议（最多2条，每条15字内）""", True),

                ("锐评版（毒舌）", """你是一个说话一针见血、不惯着毛病的拼多多运营老炮。别整那些虚头巴脑的，直接上干货。根据下面这组数据，给我往死里锐评：

【数据在这】
推广费：{推广费}元（一天烧这么多）
投产比：{投产比}（1换{投产比}）
退货率：{退货率}%
毛利率：{毛利率}%
客单价：{客单价}元
净利润：{净利润}元
净利率：{净利率}%
推广占比：{推广占比}%
单笔利润：{单笔利润}元/单
成交单量：{成交单量}单

【参考线】
保本投产：{毛保本投产}
净保本：{净保本投产}
最佳投产：{最佳投产}
当前倍数：{当前投产倍数}

---

给我按这个格式输出，少废话：

一、是死是活？
一句话说清楚现在赚还是亏？赚多少？亏多少？别绕弯子。

二、哪最烂？
挑2-3个最垃圾的数据直接开骂，说明白烂在哪、为啥烂，再不救会怎样。

三、怎么救？
给3条骚操作，每条必须：干啥+咋干+能多赚多少。别整"优化用户体验"这种屁话，要说"把图换了、把价降了、把人洗了"这种人话。

四、有的救吗？
一句话总结：这链接是能爆还是该砍？

要求：毒舌可以，但数据要对得上。说人话，别装逼。""", True),

                ("暴躁版", """你是一个脾气暴躁但懂行的拼多多运营，最烦那些废话连篇的分析。现在让你分析下面这组数据，用最暴躁的语气输出，但内容要专业：

【数据】
推广费：{推广费}元
投产比：{投产比}
退货率：{退货率}%
毛利率：{毛利率}%
客单价：{客单价}元
净利润：{净利润}元
净利率：{净利率}%
推广占比：{推广占比}%
单笔利润：{单笔利润}元/单
保本投产：{毛保本投产}
当前倍数：{当前投产倍数}

---

给我按这个格式输出，语气要像老子在骂人，但每条都要说到点子上：

一、赚了还是亏了？（20字以内）
（比如：赚个屁！/还行，有口饭吃/亏出屎了）

二、哪儿最欠骂？（每条25字以内）
1. （最烂的数据+为啥烂）
2. （第二烂的数据+为啥烂）
3. （第三烂的数据+为啥烂）

三、怎么整？（每条30字以内）
1. （干啥+咋干）
2. （干啥+咋干）
3. （干啥+咋干）

四、这链接还能要吗？（15字以内）
（比如：赶紧砍了/加预算干/再观察两天）

要求：语气暴躁但不是瞎骂，每句话都要有数据支撑。说人话，别整废话。""", True),

                ("阴阳怪气版（笑里藏刀）", """你是一个阴阳怪气、说话带刺但句句在理的拼多多运营。下面这组数据，用最阴阳怪气的语气给我分析，明褒暗贬，笑里藏刀：

【数据】
推广费：{推广费}元
投产比：{投产比}
退货率：{退货率}%
毛利率：{毛利率}%
客单价：{客单价}元
净利润：{净利润}元
净利率：{净利率}%
推广占比：{推广占比}%
单笔利润：{单笔利润}元/单
保本投产：{毛保本投产}
当前倍数：{当前投产倍数}

---

给我按这个格式输出，语气要阴阳怪气，明夸暗损：

一、哎哟不错哦？（20字以内）
（比如：这数据可太棒了，棒得我想哭/牛逼坏了，亏得真均匀）

二、值得表扬的地方（每条25字以内）
1. （表面夸实际损，比如：投产比真高啊，高到连货本都快盖不住了）
2. （表面夸实际损，比如：退货率控制得真好，再高一点就可以关门了）
3. （表面夸实际损，比如：客单价稳如老狗，稳得利润都没了）

三、要不咱试试这样？（每条30字以内）
1. （阴阳怪气地提建议，比如：要不再多烧点？亏得不够彻底我不甘心）
2. （阴阳怪气地提建议，比如：毛利这么感人，要不直接做慈善得了）
3. （阴阳怪气地提建议，比如：这单笔利润，建议改行卖惨）

四、真心话（20字以内）
最后说句人话，但前面铺垫要够阴阳。

要求：每句话都要有数据支撑，损人要损到点子上，别纯阴阳没内容。""", True),
            ]

            self.db.safe_execute("DELETE FROM ai_prompts")

            for name, content, is_system in default_prompts:
                self.db.save_prompt(name, content, is_system)

            self.db.set_active_prompt(1)

            self.load_templates()

            QMessageBox.information(self, "✅ 成功", "系统提示词已加载！\n\n已恢复为以下六个系统模板：\n1. 专业深度分析\n2. 贴吧老哥风格\n3. 简洁快速版\n4. 锐评版（毒舌）\n5. 暴躁版（老子急）\n6. 阴阳怪气版（笑里藏刀）")

    def get_default_prompt(self):
        return """你是一位资深拼多多电商运营专家，拥有多年类目运营经验。请根据以下完整的推广数据，给出专业、深入、可操作的分析建议。

【分析对象】
{分析对象信息}

【今日战绩】
推广费：{推广费}元
投产比：{投产比}
退货率：{退货率}%
毛利率：{毛利率}%
客单价：{客单价}元

【自动计算出的数据】
成交金额：{成交金额}元
退款金额：{退款金额}元
实际成交：{实际成交}元
产品成本：{产品成本}元
毛利润：{毛利润}元
技术服务费：{技术服务费}元
净利润：{净利润}元
净利率：{净利率}%
推广占比：{推广占比}%
成交单量：{成交单量}单
每笔成交花费：{每笔成交花费}元/单
单笔利润：{单笔利润}元/单

【保本情况】
毛保本投产：{毛保本投产}
净保本投产：{净保本投产}
净保本1.25倍：{净保本1.25倍}
最佳投产：{最佳投产}
当前投产倍数：{当前投产倍数}

请按以下格式输出，要求内容详实、数据支撑、实用可执行：

📊 【盈利状况诊断】
（分析当前是否盈利，亏损原因，盈利/亏损幅度，与行业平均对比）

⚠️ 【问题点深度剖析】
（列出2-4个核心问题，每个问题要说明原因、影响程度、改进优先级）

🎯 【实战优化方案】
（列出3-5条具体可执行的优化建议，每条要包含：具体动作+预期效果+操作难度）

📈 【市场趋势与竞争分析】
（分析该类目当前市场趋势、竞争格局、消费者偏好变化、季节性因素等，提供前瞻性建议）

💎 【核心干货总结】
（用最精炼的语言总结2-3个最关键的决策点）

要求：
1. 数据必须完全准确，每项数据都要在分析中体现
2. 建议要具体可执行，避免空洞废话
3. 分析要深入本质，给出真正的干货
4. 适当引用行业经验和数据支撑
5. 总字数不少于500字，内容要充实详细"""

    def test_api(self):
        api_key = self.api_key_input.text().strip()

        if not api_key:
            self.test_result_label.setText("❌ 请先输入API Key")
            self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            return

        self.test_result_label.setText("🔄 测试中(DeepSeek)...")
        self.test_result_label.setStyleSheet("color: #6c757d; font-size: 12px;")
        self.btn_test_api.setEnabled(False)

        try:
            import requests

            api_key_clean = api_key.strip()

            is_deepseek = (
                "sk-" in api_key_clean and len(api_key_clean) > 40
            ) or (
                api_key_clean.startswith("deepseek-")
            )

            if is_deepseek or "sk-" in api_key_clean:
                headers = {
                    "Authorization": f"Bearer {api_key_clean}",
                    "Content-Type": "application/json"
                }

                deepseek_urls = [
                    "https://api.deepseek.com/v1/chat/completions",
                    "https://api.deepseek.com/v1/chat/completions",
                ]

                model = "deepseek-chat"
                test_url = deepseek_urls[0]
            else:
                headers = {
                    "Authorization": f"Bearer {api_key_clean}",
                    "Content-Type": "application/json"
                }
                test_url = "https://api.openai.com/v1/chat/completions"
                model = "gpt-3.5-turbo"

            data = {
                "model": model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 20,
                "temperature": 0.7
            }

            response = requests.post(
                test_url,
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result["choices"][0]["message"]["content"]
                self.test_result_label.setText(f"✅ 成功！回复：{ai_response[:50]}")
                self.test_result_label.setStyleSheet("color: #27ae60; font-size: 12px; font-weight: bold;")
            elif response.status_code == 401:
                self.test_result_label.setText("❌ API Key无效，请检查是否正确")
                self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            elif response.status_code == 403:
                self.test_result_label.setText("❌ 访问被拒绝，请检查API Key权限")
                self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            else:
                self.test_result_label.setText(f"❌ 失败：{response.status_code}")
                self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")

        except requests.exceptions.Timeout:
            self.test_result_label.setText("❌ 超时：国内访问DeepSeek可能需要代理")
            self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        except requests.exceptions.ConnectionError as ce:
            self.test_result_label.setText(f"❌ 连接失败: {str(ce)[:50]}")
            self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            print(f"API测试连接失败: {ce}")
        except Exception as e:
            error_msg = str(e)
            if "sk-" in api_key:
                self.test_result_label.setText(f"❌ 请检查API Key是否为DeepSeek格式")
            else:
                self.test_result_label.setText(f"❌ 错误：{error_msg[:50]}")
            self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            print(f"API测试异常: {error_msg}")

        finally:
            self.btn_test_api.setEnabled(True)

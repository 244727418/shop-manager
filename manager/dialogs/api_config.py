# -*- coding: utf-8 -*-
"""API配置对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QComboBox, QTextEdit, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView, QTabWidget, QWidget,
)
from PyQt5.QtCore import Qt


class ApiConfigDialog(QDialog):
    """API配置对话框"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("🔑 API配置")
        self.resize(550, 450)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

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

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #dee2e6; margin: 15px 0;")
        layout.addWidget(separator)

        config_title = QLabel("⚙️ AI功能配置")
        config_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50; padding: 5px 0;")
        layout.addWidget(config_title)

        config_btn_layout = QVBoxLayout()

        self.btn_profit_prompt = QPushButton("📝 计算利润AI提示词配置")
        self.btn_profit_prompt.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                padding: 12px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
        """)
        self.btn_profit_prompt.clicked.connect(self.open_profit_prompt_editor)
        config_btn_layout.addWidget(self.btn_profit_prompt)

        profit_info = QLabel("💡 管理计算利润分析的AI提示词模板")
        profit_info.setStyleSheet("color: #6c757d; font-size: 11px; padding: 2px 5px; margin-bottom: 10px;")
        config_btn_layout.addWidget(profit_info)

        self.btn_common_prompt = QPushButton("📌 通用提示词管理")
        self.btn_common_prompt.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                padding: 12px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """)
        self.btn_common_prompt.clicked.connect(self.open_common_prompt_editor)
        config_btn_layout.addWidget(self.btn_common_prompt)

        common_info = QLabel("💡 管理运营常识提示词，AI分析时会自动附加")
        common_info.setStyleSheet("color: #6c757d; font-size: 11px; padding: 2px 5px; margin-bottom: 10px;")
        config_btn_layout.addWidget(common_info)

        self.btn_spec_prompt = QPushButton("📋 规格优化提示词配置")
        self.btn_spec_prompt.setStyleSheet("""
            QPushButton {
                background-color: #16a085;
                color: white;
                padding: 12px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1abc9c;
            }
        """)
        self.btn_spec_prompt.clicked.connect(self.open_spec_prompt_editor)
        config_btn_layout.addWidget(self.btn_spec_prompt)

        spec_info = QLabel("💡 配置AI优化商品规格名称的提示词（含违禁词过滤）")
        spec_info.setStyleSheet("color: #6c757d; font-size: 11px; padding: 2px 5px; margin-bottom: 10px;")
        config_btn_layout.addWidget(spec_info)

        self.btn_product_prompt = QPushButton("🛒 产品提示词配置")
        self.btn_product_prompt.setStyleSheet("""
            QPushButton {
                background-color: #2980b9;
                color: white;
                padding: 12px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3498db;
            }
        """)
        self.btn_product_prompt.clicked.connect(self.open_product_prompt_editor)
        config_btn_layout.addWidget(self.btn_product_prompt)

        product_info = QLabel("💡 配置AI生成规格时使用的产品信息提示词（毛利率策略）")
        product_info.setStyleSheet("color: #6c757d; font-size: 11px; padding: 2px 5px; margin-bottom: 10px;")
        config_btn_layout.addWidget(product_info)

        layout.addLayout(config_btn_layout)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("color: #dee2e6; margin: 15px 0;")
        layout.addWidget(separator2)

        test_layout = QHBoxLayout()

        self.btn_test_api = QPushButton("🔧 测试API连接")
        self.btn_test_api.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 10px 20px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        self.btn_test_api.clicked.connect(self.test_api)
        test_layout.addWidget(self.btn_test_api)

        self.test_result_label = QLabel("")
        self.test_result_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        test_layout.addWidget(self.test_result_label)
        test_layout.addStretch()
        layout.addLayout(test_layout)

        layout.addStretch()

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

    def save_api_key(self):
        if self.db:
            self.api_key = self.api_key_input.text().strip()
            self.db.set_setting("ai_api_key", self.api_key)
        QMessageBox.information(self, "✅ 成功", "API Key 已保存！")

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

                test_url = "https://api.deepseek.com/v1/chat/completions"
                model = "deepseek-chat"
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

    def open_profit_prompt_editor(self):
        dialog = ProfitPromptEditorDialog(self.db, self)
        dialog.exec_()

    def open_common_prompt_editor(self):
        dialog = CommonPromptEditorDialog(self.db, self)
        dialog.exec_()

    def open_spec_prompt_editor(self):
        dialog = SpecPromptEditorDialog(self.db, self)
        dialog.exec_()

    def open_product_prompt_editor(self):
        dialog = ProductPromptEditorDialog(self.db, self)
        dialog.exec_()


class ProfitPromptEditorDialog(QDialog):
    """计算利润AI提示词编辑器"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("📝 计算利润AI提示词配置")
        self.resize(700, 550)
        self.init_ui()
        self.load_templates()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("📝 AI计算利润提示词模板管理")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 这些提示词模板用于AI分析计算利润时使用。您可以新建、编辑、删除模板，并设置默认模板。")
        info.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        template_select_layout = QHBoxLayout()
        template_select_layout.addWidget(QLabel("选择模板:"))

        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(200)
        self.template_combo.currentIndexChanged.connect(self.on_template_selected)
        template_select_layout.addWidget(self.template_combo)

        self.btn_apply_template = QPushButton("✅ 设为默认")
        self.btn_apply_template.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 5px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.btn_apply_template.clicked.connect(self.apply_template)
        template_select_layout.addWidget(self.btn_apply_template)

        self.btn_new_template = QPushButton("➕ 新建")
        self.btn_new_template.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                padding: 5px 12px;
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
        self.prompt_text.setMinimumHeight(250)
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
                background-color: #3498db;
                color: white;
                padding: 8px 15px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.btn_save_prompt.clicked.connect(self.save_current_template)
        prompt_btn_layout.addWidget(self.btn_save_prompt)

        self.btn_delete_template = QPushButton("🗑️ 删除模板")
        self.btn_delete_template.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.btn_delete_template.clicked.connect(self.delete_template)
        prompt_btn_layout.addWidget(self.btn_delete_template)

        self.btn_load_system = QPushButton("📥 加载系统模板")
        self.btn_load_system.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                padding: 8px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.btn_load_system.clicked.connect(self.load_system_prompts)
        prompt_btn_layout.addWidget(self.btn_load_system)

        prompt_btn_layout.addStretch()
        layout.addLayout(prompt_btn_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

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
        self.active_label.setText(f"当前生效模板: {active_name}")

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
        QMessageBox.information(self, "✅ 成功", "模板已设为默认！\n\nAI分析将使用新模板。")

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
                self.load_templates()
                QMessageBox.information(self, "✅ 成功", "模板已更新！")
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

    def load_system_prompts(self):
        if not self.db:
            QMessageBox.warning(self, "提示", "数据库未连接！")
            return

        reply = QMessageBox.question(
            self, "确认",
            "确定要加载系统提示词吗？\n这将删除所有现有提示词并恢复为系统默认模板。",
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

            QMessageBox.information(self, "✅ 成功", "系统提示词已加载！\n\n已恢复为以下六个系统模板：\n1. 专业深度分析\n2. 贴吧老哥风格\n3. 简洁快速版\n4. 锐评版（毒舌）\n5. 暴躁版\n6. 阴阳怪气版")


class CommonPromptEditorDialog(QDialog):
    """通用提示词编辑器"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("📌 通用提示词管理")
        self.resize(600, 500)
        self.init_ui()
        self.load_prompts()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("📌 通用提示词（运营常识）")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 这些提示词会在AI分析时自动附加，提供拼多多运营常识和时效性技巧。")
        info.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.common_prompt_list = QListWidget()
        self.common_prompt_list.setMinimumHeight(200)
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
                background-color: #27ae60;
                color: white;
                padding: 8px 15px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.btn_add_common.clicked.connect(self.add_common_prompt)
        common_btn_layout.addWidget(self.btn_add_common)

        self.btn_edit_common = QPushButton("✏️ 编辑")
        self.btn_edit_common.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.btn_edit_common.clicked.connect(self.edit_common_prompt)
        common_btn_layout.addWidget(self.btn_edit_common)

        self.btn_delete_common = QPushButton("🗑️ 删除")
        self.btn_delete_common.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 15px;
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

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def load_prompts(self):
        self.common_prompt_list.clear()
        prompts = self.db.get_all_common_prompts()
        self.common_prompt_data = {}
        for p in prompts:
            prompt_id, content, is_active, sort_order = p
            self.common_prompt_data[prompt_id] = {"content": content, "is_active": is_active}
            display = content
            if len(display) > 70:
                display = display[:70] + "..."
            if not is_active:
                display = f"[禁用] {display}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, prompt_id)
            self.common_prompt_list.addItem(item)

    def add_common_prompt(self):
        text, ok = QInputDialog.getMultiLineText(self, "添加通用提示词", "请输入运营常识或技巧:")
        if not ok or not text.strip():
            return
        self.db.add_common_prompt(text.strip())
        self.load_prompts()
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
            text, ok = QInputDialog.getMultiLineText(self, "编辑通用提示词", "请输入运营常识或技巧:", old_content)
            if not ok or not text.strip():
                return
            self.db.update_common_prompt(prompt_id, text.strip())
            self.load_prompts()
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
            self.load_prompts()
            QMessageBox.information(self, "✅ 成功", "通用提示词已删除！")


class SpecPromptEditorDialog(QDialog):
    """规格优化提示词编辑器"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("📋 规格优化提示词配置")
        self.resize(800, 600)
        self.init_ui()
        self.load_prompts()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("🤖 AI规格优化提示词配置")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 配置AI优化商品规格名称的提示词。用户可选择「高转化」或「低转化」模式。")
        info.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        layout.addWidget(info)

        tab_widget = QTabWidget()
        self.high_tab = QWidget()
        self.low_tab = QWidget()
        self.attr_tab = QWidget()
        tab_widget.addTab(self.high_tab, "🎯 高转化提示词")
        tab_widget.addTab(self.low_tab, "⚠️ 低转化提示词")
        tab_widget.addTab(self.attr_tab, "📦 商品属性提示词")
        layout.addWidget(tab_widget)

        self.high_layout = QVBoxLayout(self.high_tab)
        high_label = QLabel("【SKU规格名称生成提示词模板 - 高转化优化版】")
        high_label.setStyleSheet("font-weight: bold; color: #27ae60;")
        self.high_layout.addWidget(high_label)

        self.high_prompt_text = QTextEdit()
        self.high_prompt_text.setPlaceholderText("请输入高转化提示词...")
        self.high_prompt_text.setMinimumHeight(250)
        self.high_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        self.high_layout.addWidget(self.high_prompt_text)

        self.low_layout = QVBoxLayout(self.low_tab)
        low_label = QLabel("【SKU规格名称生成提示词模板 - 低转化优化版】")
        low_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        self.low_layout.addWidget(low_label)

        self.low_prompt_text = QTextEdit()
        self.low_prompt_text.setPlaceholderText("请输入低转化提示词...")
        self.low_prompt_text.setMinimumHeight(250)
        self.low_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        self.low_layout.addWidget(self.low_prompt_text)

        self.attr_layout = QVBoxLayout(self.attr_tab)
        attr_label = QLabel("【商品属性提示词 - 附加信息】")
        attr_label.setStyleSheet("font-weight: bold; color: #2980b9;")
        self.attr_layout.addWidget(attr_label)

        attr_desc = QLabel("💡 输入商品属性信息，如：垆土铁棍山药、密度高、偶尔有锈斑等。系统会自动填充标题、所有规格名称、价格、毛利率，并标注当前优化的是哪个规格。")
        attr_desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        attr_desc.setWordWrap(True)
        self.attr_layout.addWidget(attr_desc)

        self.attr_prompt_text = QTextEdit()
        self.attr_prompt_text.setPlaceholderText("例如：这是垆土铁棍山药，密度高，偶尔有锈斑偶尔没有，口感粉糯...")
        self.attr_prompt_text.setMinimumHeight(250)
        self.attr_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        self.attr_layout.addWidget(self.attr_prompt_text)

        forbidden_layout = QHBoxLayout()

        forbidden_label = QLabel("🚫 违禁词设置：")
        forbidden_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        forbidden_layout.addWidget(forbidden_label)

        self.btn_set_forbidden = QPushButton("⚠️ 设置违禁词")
        self.btn_set_forbidden.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 15px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.btn_set_forbidden.clicked.connect(self.open_forbidden_words_editor)
        forbidden_layout.addWidget(self.btn_set_forbidden)

        self.forbidden_count_label = QLabel("")
        self.forbidden_count_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        forbidden_layout.addWidget(self.forbidden_count_label)

        forbidden_layout.addStretch()
        layout.addLayout(forbidden_layout)

        btn_layout = QHBoxLayout()

        self.btn_reset_high = QPushButton("🔄 恢复高转化默认")
        self.btn_reset_high.clicked.connect(lambda: self.reset_prompt("high"))
        btn_layout.addWidget(self.btn_reset_high)

        self.btn_reset_low = QPushButton("🔄 恢复低转化默认")
        self.btn_reset_low.clicked.connect(lambda: self.reset_prompt("low"))
        btn_layout.addWidget(self.btn_reset_low)

        self.btn_reset_attr = QPushButton("🔄 恢复属性默认")
        self.btn_reset_attr.clicked.connect(lambda: self.reset_prompt("attr"))
        btn_layout.addWidget(self.btn_reset_attr)

        btn_layout.addStretch()

        self.btn_save = QPushButton("💾 保存")
        self.btn_save.setStyleSheet("""
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
        self.btn_save.clicked.connect(self.save_prompts)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("关闭")
        self.btn_cancel.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def get_default_high_prompt(self):
        return """你是一个电商SKU命名专家，擅长通过规格名称提升顾客购买意愿。请根据用户输入的原规格名称，生成10个不同风格的新规格名称。

【核心逻辑】
不是让顾客"快买"，而是让顾客觉得"这个选项最划算最适合我"：
强调性价比高、量大实惠
突出热销、多人选择
暗示赠品多、套餐划算
制造紧迫感（限时、限量）
让顾客主动认为"买这个最聪明"

【重要 - 避免重复原规格】
不要直接把原规格名称复制出来！
要在原规格基础上进行创意改编，让每个规格名称都新颖独特
禁止出现"原规格：xxx"、"原规格名称"、"新规格1："等前缀
每个规格必须是完整的、独立的名称
不要出现"原规格"三个字

【风格要求 - 10个规格必须包含以下风格】
1. 热销爆款风格（强调多人购买、销量）
2. 限时优惠风格（强调特价、限时）
3. 赠品福利风格（强调送赠品、送礼品）
4. 性价比之王风格（强调便宜、划算）
5. 品质保障风格（强调质量、正品）
6. 新品首发风格（强调新品、首发）
7. 实用推荐风格（强调实用、推荐）
8. 环保健康风格（强调安全、环保）
9. 明星同款风格（强调潮流、时尚）
10. 回头客风格（强调回购、老客）

【要求】
只能用括号：（）、【】、-、丨
每个规格字数控制在25-35字之间
10个规格的风格必须各不相同，不能雷同
保留原规格的核心词（如数量、尺码、款式等）
从消费者视角出发，让他们自己觉得"这个值"
禁止使用"·"符号
直接输出10个新规格名，一行一个，不要解释"""

    def get_default_low_prompt(self):
        return """你是一个电商SKU命名专家，擅长通过规格名称降低顾客购买意愿。请根据用户输入的原规格名称，生成10个不同风格的新规格名称，让顾客觉得"这个不适合我"。

【核心逻辑】
不是让顾客"别买"，而是让顾客觉得"这个选项不适合我"：
强调数量少、规格小、性价比低
暗示产品有瑕疵或风险
突出使用周期短、不够用
让顾客主动选择其他更划算的规格

【重要 - 避免重复原规格】
不要直接把原规格名称复制出来！
要在原规格基础上进行创意改编，让每个规格名称都新颖独特
禁止出现"原规格：xxx"、"原规格名称"、"新规格1："等前缀
每个规格必须是完整的、独立的名称
不要出现"原规格"三个字

【风格要求 - 10个规格必须包含以下风格】
1. 容量太小风格（强调量少、不够用）
2. 性价比低风格（强调贵、不划算）
3. 限时缺货风格（暗示可能缺货、要等）
4. 质量问题风格（暗示可能有瑕疵）
5. 适用范围窄风格（强调只适合特定人群）
6. 赠品少风格（强调没有赠品、不值得）
7. 寿命短风格（强调用不久、不耐用）
8. 回头率低风格（暗示买过的人不再买）
9. 替代品风格（暗示有更好的选择）
10. 谨慎购买风格（暗示要仔细考虑）

【要求】
只能用括号：（）、【】、-、丨
每个规格字数控制在25-35字之间
10个规格的风格必须各不相同，不能雷同
保留原规格的核心词（如数量、尺码、款式等）
从消费者视角出发，让他们自己觉得"这个不合适"
禁止使用"·"符号
直接输出10个新规格名，一行一个，不要解释"""

    def get_default_attr_prompt(self):
        return """【商品属性信息】
{product_attr}

【当前链接标题】
{product_name}

【所有规格信息】（每个规格的名称、毛利率、价格）
{specs_layout}

【当前正在优化的规格】
{current_spec_name}

请结合以上商品属性和规格信息，生成最适合该规格的优化名称。"""

    def load_prompts(self):
        high_prompt = self.db.get_setting("ai_spec_high_prompt", "")
        low_prompt = self.db.get_setting("ai_spec_low_prompt", "")
        attr_prompt = self.db.get_setting("ai_spec_attr_prompt", "")

        if high_prompt:
            self.high_prompt_text.setPlainText(high_prompt)
        else:
            self.high_prompt_text.setPlainText(self.get_default_high_prompt())

        if low_prompt:
            self.low_prompt_text.setPlainText(low_prompt)
        else:
            self.low_prompt_text.setPlainText(self.get_default_low_prompt())

        if attr_prompt:
            self.attr_prompt_text.setPlainText(attr_prompt)
        else:
            self.attr_prompt_text.setPlainText(self.get_default_attr_prompt())

        self.update_forbidden_count()

    def update_forbidden_count(self):
        forbidden_words = self.db.get_setting("ai_spec_forbidden_words", "")
        if forbidden_words:
            word_list = [w.strip() for w in forbidden_words.split(",") if w.strip()]
            self.forbidden_count_label.setText(f"（已设置 {len(word_list)} 个违禁词）")
        else:
            self.forbidden_count_label.setText("（未设置违禁词）")

    def reset_prompt(self, prompt_type):
        if prompt_type == "high":
            reply = QMessageBox.question(self, "确认", "确定要恢复高转化提示词为默认吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.high_prompt_text.setPlainText(self.get_default_high_prompt())
        elif prompt_type == "low":
            reply = QMessageBox.question(self, "确认", "确定要恢复低转化提示词为默认吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.low_prompt_text.setPlainText(self.get_default_low_prompt())
        elif prompt_type == "attr":
            reply = QMessageBox.question(self, "确认", "确定要恢复商品属性提示词为默认吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.attr_prompt_text.setPlainText(self.get_default_attr_prompt())

    def save_prompts(self):
        high_prompt = self.high_prompt_text.toPlainText().strip()
        low_prompt = self.low_prompt_text.toPlainText().strip()
        attr_prompt = self.attr_prompt_text.toPlainText().strip()

        if not high_prompt:
            QMessageBox.warning(self, "⚠️ 警告", "高转化提示词不能为空！")
            return
        if not low_prompt:
            QMessageBox.warning(self, "⚠️ 警告", "低转化提示词不能为空！")
            return

        self.db.set_setting("ai_spec_high_prompt", high_prompt)
        self.db.set_setting("ai_spec_low_prompt", low_prompt)
        self.db.set_setting("ai_spec_attr_prompt", attr_prompt)

        QMessageBox.information(self, "✅ 成功", "规格优化提示词已保存！\n\n下次AI优化规格名称时将使用新的提示词。")
        self.accept()

    def open_forbidden_words_editor(self):
        dialog = ForbiddenWordsEditorDialog(self.db, self)
        if dialog.exec_():
            self.update_forbidden_count()


class ForbiddenWordsEditorDialog(QDialog):
    """违禁词编辑器"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("🚫 违禁词设置")
        self.resize(500, 400)
        self.init_ui()
        self.load_forbidden_words()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("⚠️ AI规格优化违禁词设置")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #e74c3c; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 设置后，AI生成的规格名称中如果包含违禁词，将被自动过滤。多个违禁词用英文逗号分隔。")
        info.setStyleSheet("color: #6c757d; font-size: 11px; padding: 5px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.forbidden_text = QTextEdit()
        self.forbidden_text.setPlaceholderText("例如：最好,第一,顶级,极品,全网最低价,绝对,极致\n\n（多个违禁词用英文逗号分隔）")
        self.forbidden_text.setMinimumHeight(150)
        self.forbidden_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.forbidden_text)

        default_label = QLabel("💡 默认违禁词列表（可一键恢复）：")
        default_label.setStyleSheet("color: #6c757d; font-size: 11px; padding: 5px;")
        layout.addWidget(default_label)

        default_layout = QHBoxLayout()

        btn_pinduoduo = QPushButton("拼多多违禁词")
        btn_pinduoduo.clicked.connect(lambda: self.set_default_forbidden(self.get_pinduoduo_forbidden()))
        default_layout.addWidget(btn_pinduoduo)

        btn_taobao = QPushButton("淘宝违禁词")
        btn_taobao.clicked.connect(lambda: self.set_default_forbidden(self.get_taobao_forbidden()))
        default_layout.addWidget(btn_taobao)

        btn_jd = QPushButton("京东违禁词")
        btn_jd.clicked.connect(lambda: self.set_default_forbidden(self.get_jd_forbidden()))
        default_layout.addWidget(btn_jd)

        default_layout.addStretch()
        layout.addLayout(default_layout)

        btn_layout = QHBoxLayout()

        btn_clear = QPushButton("清空违禁词")
        btn_clear.clicked.connect(self.clear_forbidden)
        btn_layout.addWidget(btn_clear)

        btn_layout.addStretch()

        btn_save = QPushButton("💾 保存")
        btn_save.setStyleSheet("""
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
        btn_save.clicked.connect(self.save_forbidden)
        btn_layout.addWidget(btn_save)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def get_pinduoduo_forbidden(self):
        return "最好,第一,顶级,极品,全网最低价,绝对,极致,国家级,世界级,最高级,最佳,最优,最大,最小,首选,独家,唯一,正品,正牌,假一赔十,假一赔百,全网第一,销量第一,排名第一,全网销量冠军,全网销量第一,天猫,京东,淘宝,拼多多旗舰店"

    def get_taobao_forbidden(self):
        return "最好,第一,顶级,极品,全网最低价,绝对,极致,国家级,世界级,最高级,最佳,最优,最大,最小,首选,独家,唯一,正品,正牌,假一赔十,全网第一,销量第一,排名第一,全网销量冠军,全网销量第一"

    def get_jd_forbidden(self):
        return "最好,第一,顶级,极品,全网最低价,绝对,极致,国家级,世界级,最高级,最佳,最优,最大,最小,首选,独家,唯一,正品,正牌,假一赔十,全网第一,销量第一,排名第一,全网销量冠军,全网销量第一,天猫,淘宝"

    def load_forbidden_words(self):
        forbidden_words = self.db.get_setting("ai_spec_forbidden_words", "")
        if forbidden_words:
            self.forbidden_text.setPlainText(forbidden_words)
        else:
            self.forbidden_text.setPlainText("")

    def set_default_forbidden(self, words):
        self.forbidden_text.setPlainText(words)

    def clear_forbidden(self):
        reply = QMessageBox.question(self, "确认", "确定要清空所有违禁词吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.forbidden_text.setPlainText("")

    def save_forbidden(self):
        forbidden_words = self.forbidden_text.toPlainText().strip()
        self.db.set_setting("ai_spec_forbidden_words", forbidden_words)
        QMessageBox.information(self, "✅ 成功", "违禁词设置已保存！")
        self.accept()


class ProductPromptEditorDialog(QDialog):
    """产品提示词编辑器"""
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("🛒 产品提示词配置")
        self.resize(850, 700)
        self.init_ui()
        self.load_prompts()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("🛒 AI产品规格优化 - 产品提示词配置")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 配置AI生成规格名称时使用的产品提示词。产品信息由用户手动上传，毛利策略根据转化类型和毛利率自动选择。")
        info.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        tab_widget = QTabWidget()

        self.product_info_tab = QWidget()
        self.high_high_margin_tab = QWidget()
        self.high_low_margin_tab = QWidget()
        self.low_high_margin_tab = QWidget()
        self.low_low_margin_tab = QWidget()

        tab_widget.addTab(self.product_info_tab, "📦 产品信息（用户上传）")
        tab_widget.addTab(self.high_high_margin_tab, "🎯高转化+💰高毛利")
        tab_widget.addTab(self.high_low_margin_tab, "🎯高转化+💰低毛利")
        tab_widget.addTab(self.low_high_margin_tab, "⚠️低转化+💰高毛利")
        tab_widget.addTab(self.low_low_margin_tab, "⚠️低转化+💰低毛利")

        layout.addWidget(tab_widget)

        self.init_product_info_tab()
        self.init_high_high_margin_tab()
        self.init_high_low_margin_tab()
        self.init_low_high_margin_tab()
        self.init_low_low_margin_tab()

        btn_layout = QHBoxLayout()

        self.btn_reset = QPushButton("🔄 恢复默认")
        self.btn_reset.clicked.connect(self.reset_all_prompts)
        btn_layout.addWidget(self.btn_reset)

        btn_layout.addStretch()

        self.btn_save = QPushButton("💾 保存")
        self.btn_save.setStyleSheet("""
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
        self.btn_save.clicked.connect(self.save_prompts)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("关闭")
        self.btn_cancel.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def init_product_info_tab(self):
        layout = QVBoxLayout(self.product_info_tab)

        label = QLabel("【产品信息 - 用户上传】")
        label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addWidget(label)

        desc = QLabel("💡 请手动输入产品信息。系统会自动标注当前正在优化的规格。\n【提示】只包含：标题、所有规格名称+毛利率+价格，一字不差地传给AI。")
        desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.product_info_text = QTextEdit()
        self.product_info_text.setMinimumHeight(350)
        self.product_info_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.product_info_text)

    def init_high_high_margin_tab(self):
        layout = QVBoxLayout(self.high_high_margin_tab)

        label = QLabel("【高转化 + 高毛利(≥25%)】")
        label.setStyleSheet("font-weight: bold; color: #27ae60;")
        layout.addWidget(label)

        desc = QLabel("💡 高转化 + 高毛利时，以产品质量、功能、耐用性为卖点。让顾客觉得买这个最值。")
        desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.high_high_prompt_text = QTextEdit()
        self.high_high_prompt_text.setMinimumHeight(350)
        self.high_high_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.high_high_prompt_text)

    def init_high_low_margin_tab(self):
        layout = QVBoxLayout(self.high_low_margin_tab)

        label = QLabel("【高转化 + 低毛利(<25%)】")
        label.setStyleSheet("font-weight: bold; color: #e67e22;")
        layout.addWidget(label)

        desc = QLabel("💡 高转化 + 低毛利时，以低价优势、实惠、性价比为卖点。让顾客觉得买这个最划算。")
        desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.high_low_prompt_text = QTextEdit()
        self.high_low_prompt_text.setMinimumHeight(350)
        self.high_low_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.high_low_prompt_text)

    def init_low_high_margin_tab(self):
        layout = QVBoxLayout(self.low_high_margin_tab)

        label = QLabel("【低转化 + 高毛利(≥25%)】")
        label.setStyleSheet("font-weight: bold; color: #9b59b6;")
        layout.addWidget(label)

        desc = QLabel("💡 低转化 + 高毛利时，以不实惠、单价贵等方向优化。让顾客觉得不适合自己。")
        desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.low_high_prompt_text = QTextEdit()
        self.low_high_prompt_text.setMinimumHeight(350)
        self.low_high_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.low_high_prompt_text)

    def init_low_low_margin_tab(self):
        layout = QVBoxLayout(self.low_low_margin_tab)

        label = QLabel("【低转化 + 低毛利(<25%)】")
        label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        layout.addWidget(label)

        desc = QLabel("💡 低转化 + 低毛利时，以不实惠、单价贵等方向优化。让顾客觉得不适合自己。")
        desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.low_low_prompt_text = QTextEdit()
        self.low_low_prompt_text.setMinimumHeight(350)
        self.low_low_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.low_low_prompt_text)

    def get_default_product_info_prompt(self):
        return """（请在此处输入产品相关信息，如：垆土铁棍山药、密度高、偶尔有锈斑等）"""

    def get_default_high_high_margin_prompt(self):
        return """【毛利策略：高转化 + 高毛利(≥25%)】

当前产品毛利率较高，选择高转化模式。

【核心策略】
1. 以产品质量、功能、耐用性为卖点
2. 强调品质上乘、经久耐用
3. 突出产品的核心功能和独特卖点
4. 暗示使用寿命长、性价比高（单位使用成本低）
5. 适合追求品质的顾客群体

请结合产品本身的特点和功能，生成能体现产品价值的规格名称。"""

    def get_default_high_low_margin_prompt(self):
        return """【毛利策略：高转化 + 低毛利(<25%)】

当前产品毛利率较低，选择高转化模式。

【核心策略】
1. 以低价优势、实惠、性价比为卖点
2. 强调价格优惠、促销力度大
3. 制造紧迫感，促进快速下单
4. 暗示赠品多、套餐划算
5. 适合价格敏感的顾客群体

请结合产品的价格优势，生成能促进快速下单的规格名称。"""

    def get_default_low_high_margin_prompt(self):
        return """【毛利策略：低转化 + 高毛利(≥25%)】

当前产品毛利率较高，选择低转化模式。
目标：让顾客觉得这个产品不适合自己，主动选择其他规格。

【核心策略】
1. 强调价格偏高、不实惠
2. 暗示性价比低、不值得
3. 突出产品可能存在的缺点或局限
4. 让顾客觉得"买这个不划算"

请生成让顾客觉得"不适合我"的规格名称。"""

    def get_default_low_low_margin_prompt(self):
        return """【毛利策略：低转化 + 低毛利(<25%)】

当前产品毛利率较低，选择低转化模式。
目标：让顾客觉得这个产品不适合自己，主动选择其他规格。

【核心策略】
1. 强调价格看似便宜但实际不优惠
2. 暗示"便宜没好货"
3. 突出产品可能偷工减料或质量一般
4. 让顾客觉得"买这个不明智"

请生成让顾客觉得"不适合我"的规格名称。"""

    def load_prompts(self):
        product_info = self.db.get_setting("ai_product_info_prompt", "")
        high_high = self.db.get_setting("ai_high_high_margin_prompt", "")
        high_low = self.db.get_setting("ai_high_low_margin_prompt", "")
        low_high = self.db.get_setting("ai_low_high_margin_prompt", "")
        low_low = self.db.get_setting("ai_low_low_margin_prompt", "")

        self.product_info_text.setPlainText(product_info if product_info else self.get_default_product_info_prompt())
        self.high_high_prompt_text.setPlainText(high_high if high_high else self.get_default_high_high_margin_prompt())
        self.high_low_prompt_text.setPlainText(high_low if high_low else self.get_default_high_low_margin_prompt())
        self.low_high_prompt_text.setPlainText(low_high if low_high else self.get_default_low_high_margin_prompt())
        self.low_low_prompt_text.setPlainText(low_low if low_low else self.get_default_low_low_margin_prompt())

    def reset_all_prompts(self):
        reply = QMessageBox.question(self, "确认", "确定要恢复所有提示词为默认吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.product_info_text.setPlainText(self.get_default_product_info_prompt())
            self.high_high_prompt_text.setPlainText(self.get_default_high_high_margin_prompt())
            self.high_low_prompt_text.setPlainText(self.get_default_high_low_margin_prompt())
            self.low_high_prompt_text.setPlainText(self.get_default_low_high_margin_prompt())
            self.low_low_prompt_text.setPlainText(self.get_default_low_low_margin_prompt())

    def save_prompts(self):
        product_info = self.product_info_text.toPlainText().strip()
        high_high = self.high_high_prompt_text.toPlainText().strip()
        high_low = self.high_low_prompt_text.toPlainText().strip()
        low_high = self.low_high_prompt_text.toPlainText().strip()
        low_low = self.low_low_prompt_text.toPlainText().strip()

        if not product_info:
            QMessageBox.warning(self, "⚠️ 警告", "产品信息不能为空！")
            return

        self.db.set_setting("ai_product_info_prompt", product_info)
        self.db.set_setting("ai_high_high_margin_prompt", high_high)
        self.db.set_setting("ai_high_low_margin_prompt", high_low)
        self.db.set_setting("ai_low_high_margin_prompt", low_high)
        self.db.set_setting("ai_low_low_margin_prompt", low_low)

        QMessageBox.information(self, "✅ 成功", "产品提示词配置已保存！")
        self.accept()

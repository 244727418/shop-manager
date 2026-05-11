# -*- coding: utf-8 -*-
"""API配置对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
    QComboBox, QTextEdit, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QAbstractItemView, QTabWidget, QWidget,
)
from PyQt5.QtCore import Qt
import time

SPEC_PROMPT_VERSION = "sku_axis_no_style_label_v3"


def get_default_spec_base_prompt_v2():
    return """【基础生成规则】
你是电商SKU规格命名专家，也是一名懂消费者心理的运营策划。请围绕当前规格生成10个不同风格的新规格名称。

【内部发散步骤】（只在心里完成，不要输出分析过程）
1. 先识别产品主体词：从商品标题、产品信息、本次补充提示、原规格中提取最短但清楚的商品主体名。
2. 每条SKU正文都必须包含产品主体词或更明确的同义主体，不能优化后只剩精品装、家庭装、尝鲜款、礼盒装这类空泛规格。
3. 再识别购买人群和购买痛点：谁会买、为什么买、担心什么、在什么场景用、和其他规格怎么比较。
4. 针对不同品类提取可感知价值：食品看口感、营养成分、烹饪/食用场景；日用品看材质、耐用、收纳、家庭场景；服饰看面料、版型、季节、人群；工具看效率、适配、耐用和使用场景。
5. 10个结果必须覆盖不同角度，例如品质型、场景型、人群型、规格对比型、礼赠型、安心型、复购型、尝鲜型、家庭囤货型、专业推荐型。
6. 禁止10条只是替换少量形容词，禁止全部堆叠甄选、精品、高品质这类同质词。

【合规边界】
可以基于已给出的商品信息发散表达，但不能编造具体产地、认证、检测、治疗功效、药效、销量数据、获奖背书。
食品类可以表达营养、口感、日常滋补、早餐/煲汤/家庭餐等场景，但不能写治疗、降血糖、治病、药用承诺。

必须保留原规格的核心信息，如数量、重量、尺码、颜色、款式、组合关系。
不要直接复制原规格名称，要在原规格基础上做清晰、可读、有运营目的的改写。
不要输出独立风格标签，不要把风格写成单独前缀；风格差异必须融入SKU正文，例如通过卖点、人群、场景、规格对比、语气结构体现。
SKU名称尽量接近35字，最多不超过40字。
强制禁止使用中文逗号、英文逗号、顿号、句号、分号、冒号、感叹号、问号、斜杠、反斜杠、下划线、星号、项目符号。
允许使用的符号只有：- + 丨 () [] 【】
可以少量使用允许符号让10条在结构上有差异，但不要为了符号牺牲可读性。
禁止出现"原规格"、"新规格"、"优化后"等解释性前缀。
直接输出10个新规格名，一行一个，不要解释。"""


def get_default_conversion_axis_prompt_v2():
    return """【转化方向标尺规则】
当前转化方向数值：{conversion_level}，说明：{conversion_desc}。
正向转化：先识别购买人群，再围绕人群痛点写购买理由，例如省心、适合家庭、适合送礼、适合囤货、适合尝鲜、适合高频使用。
数值越接近+10，越要让顾客觉得这个规格就是最适合自己的选择，但不要只写热销、推荐、放心，要写具体场景和具体价值。
数值在+1到+5时，只做轻度购买引导，不要过度促销。
数值为0时，保持客观中性，只优化清晰度、主体识别和规格差异。
负向转化：目标不是说产品差，而是让非目标用户主动放弃当前规格，倾向选择其他规格。
数值越接近-10，劝退越明显：必须写出选择门槛、适用限制或需求不匹配，不能写成人人都想买的强转化文案。
高价人群负向时尤其要强调只适合高频使用、重度需求、送礼、囤货、大规格、高标准用户；普通用户会觉得用不上、没必要、需求不匹配。
低价人群负向时强调预算不匹配、轻用无需选、先看基础规格、入门不建议。
负向表达必须合规：不能编造质量问题、瑕疵、假货、风险、差评，只能用规格小/大、预算不匹配、使用频率不匹配、场景不匹配、建议对比其他规格等表达。"""


def get_default_price_audience_prompt_v2():
    return """【价格人群标尺规则】
当前价格人群数值：{price_audience_level}，说明：{price_audience_desc}。
数值越接近+10，越面向高价品质人群：不要只写甄选、精品、高品质，要说明顾客能感知到的价值依据，如口感/营养/材质/工艺/耐用/省心/礼赠/家庭场景/长期使用价值。
高价人群不强调便宜、优惠、低价、划算，重点表达值不值、好不好、适不适合、是否省心。
当转化方向为负数且价格人群偏高时，劝退方式要变成“高门槛筛选”：强调该规格更适合高标准用户、重度使用者、礼赠场景、大规格需求、明确品质追求者，让普通用户觉得没必要选它。
高价人群劝退不要说贵、不划算、质量差，而要用“更适合懂品质/送礼/长期囤用/高频使用/对口感材质有要求的人”来抬高选择门槛。
高价人群负向禁止写成“值得买、放心选、推荐入手、品质必选、人人适合”等促进转化表达。
数值越接近-10，越面向低价敏感人群：可以使用实惠、优惠、性价比、入门、尝鲜、囤货、家庭装等表达，但必须受价格相对位置限制。
当转化方向为负数且价格人群偏低时，可以强调预算不匹配、入门不建议、日常轻用无需选择、可先看更基础规格，但不能误导当前规格是最低价。
数值为0时，不明显偏向高价或低价，只保证规格名称清楚、真实、易比较。
无论数值如何，都不能和当前规格的真实价格相对位置冲突。"""


def ensure_spec_prompt_defaults_v2(db):
    if not db:
        return
    try:
        if db.get_setting("ai_spec_prompt_version", "") == SPEC_PROMPT_VERSION:
            return
        db.set_setting("ai_spec_base_prompt", get_default_spec_base_prompt_v2())
        db.set_setting("ai_spec_conversion_axis_prompt", get_default_conversion_axis_prompt_v2())
        db.set_setting("ai_spec_price_audience_prompt", get_default_price_audience_prompt_v2())
        db.set_setting("ai_spec_prompt_version", SPEC_PROMPT_VERSION)
    except Exception as e:
        print(f"升级规格优化提示词失败: {e}")


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

                test_url = "https://api.deepseek.com/chat/completions"
                model = "deepseek-v4-flash"
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

            response = None
            for attempt in range(3):
                response = requests.post(
                    test_url,
                    headers=headers,
                    json=data,
                    timeout=30
                )
                if response.status_code not in (500, 503):
                    break
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))

            if response.status_code == 503:
                error_detail = response.text.strip()[:120]
                self.test_result_label.setText(f"API测试失败：503，DeepSeek服务器当前过载，请稍后重试 {error_detail}")
                self.test_result_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
                return

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
        ensure_spec_prompt_defaults_v2(self.db)
        self.setWindowTitle("📋 规格优化提示词配置")
        self.resize(800, 600)
        self.init_ui()
        self.load_prompts()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("🤖 AI规格优化提示词配置")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 配置AI优化商品规格名称的提示词。运行时会根据「转化方向」和「价格人群」标尺动态拼装。")
        info.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        layout.addWidget(info)

        tab_widget = QTabWidget()
        self.base_tab = QWidget()
        self.conversion_tab = QWidget()
        self.attr_tab = QWidget()
        tab_widget.addTab(self.base_tab, "🧩 基础生成规则")
        tab_widget.addTab(self.conversion_tab, "🎯 转化标尺规则")
        tab_widget.addTab(self.attr_tab, "📦 商品属性提示词")
        layout.addWidget(tab_widget)

        self.base_layout = QVBoxLayout(self.base_tab)
        base_label = QLabel("【SKU规格名称生成提示词模板 - 基础生成规则】")
        base_label.setStyleSheet("font-weight: bold; color: #16a085;")
        self.base_layout.addWidget(base_label)

        base_desc = QLabel("💡 可使用变量：{product_name}、{current_spec_name}、{custom_hint}")
        base_desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        base_desc.setWordWrap(True)
        self.base_layout.addWidget(base_desc)

        self.base_prompt_text = QTextEdit()
        self.base_prompt_text.setPlaceholderText("请输入基础生成规则...")
        self.base_prompt_text.setMinimumHeight(250)
        self.base_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        self.base_layout.addWidget(self.base_prompt_text)

        self.conversion_layout = QVBoxLayout(self.conversion_tab)
        conversion_label = QLabel("【SKU规格名称生成提示词模板 - 转化标尺规则】")
        conversion_label.setStyleSheet("font-weight: bold; color: #27ae60;")
        self.conversion_layout.addWidget(conversion_label)

        conversion_desc = QLabel("💡 可使用变量：{conversion_level}、{conversion_desc}、{product_name}、{current_spec_name}、{custom_hint}")
        conversion_desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        conversion_desc.setWordWrap(True)
        self.conversion_layout.addWidget(conversion_desc)

        self.conversion_prompt_text = QTextEdit()
        self.conversion_prompt_text.setPlaceholderText("请输入转化标尺规则...")
        self.conversion_prompt_text.setMinimumHeight(250)
        self.conversion_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        self.conversion_layout.addWidget(self.conversion_prompt_text)

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

        self.btn_reset_base = QPushButton("🔄 恢复基础默认")
        self.btn_reset_base.clicked.connect(lambda: self.reset_prompt("base"))
        btn_layout.addWidget(self.btn_reset_base)

        self.btn_reset_conversion = QPushButton("🔄 恢复转化默认")
        self.btn_reset_conversion.clicked.connect(lambda: self.reset_prompt("conversion"))
        btn_layout.addWidget(self.btn_reset_conversion)

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

    def get_default_base_prompt(self):
        return get_default_spec_base_prompt_v2()

    def get_default_conversion_prompt(self):
        return get_default_conversion_axis_prompt_v2()

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
        base_prompt = self.db.get_setting("ai_spec_base_prompt", "")
        conversion_prompt = self.db.get_setting("ai_spec_conversion_axis_prompt", "")
        attr_prompt = self.db.get_setting("ai_spec_attr_prompt", "")

        if base_prompt:
            self.base_prompt_text.setPlainText(base_prompt)
        else:
            self.base_prompt_text.setPlainText(self.get_default_base_prompt())

        if conversion_prompt:
            self.conversion_prompt_text.setPlainText(conversion_prompt)
        else:
            self.conversion_prompt_text.setPlainText(self.get_default_conversion_prompt())

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
        if prompt_type == "base":
            reply = QMessageBox.question(self, "确认", "确定要恢复基础生成规则为默认吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.base_prompt_text.setPlainText(self.get_default_base_prompt())
        elif prompt_type == "conversion":
            reply = QMessageBox.question(self, "确认", "确定要恢复转化标尺规则为默认吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.conversion_prompt_text.setPlainText(self.get_default_conversion_prompt())
        elif prompt_type == "attr":
            reply = QMessageBox.question(self, "确认", "确定要恢复商品属性提示词为默认吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.attr_prompt_text.setPlainText(self.get_default_attr_prompt())

    def save_prompts(self):
        base_prompt = self.base_prompt_text.toPlainText().strip()
        conversion_prompt = self.conversion_prompt_text.toPlainText().strip()
        attr_prompt = self.attr_prompt_text.toPlainText().strip()

        if not base_prompt:
            QMessageBox.warning(self, "⚠️ 警告", "基础生成规则不能为空！")
            return
        if not conversion_prompt:
            QMessageBox.warning(self, "⚠️ 警告", "转化标尺规则不能为空！")
            return

        self.db.set_setting("ai_spec_base_prompt", base_prompt)
        self.db.set_setting("ai_spec_conversion_axis_prompt", conversion_prompt)
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
        ensure_spec_prompt_defaults_v2(self.db)
        self.setWindowTitle("🛒 产品提示词配置")
        self.resize(850, 700)
        self.init_ui()
        self.load_prompts()

    def init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel("🛒 AI产品规格优化 - 产品提示词配置")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 10px;")
        layout.addWidget(header)

        info = QLabel("💡 配置AI生成规格名称时使用的产品提示词。价格人群和价格相对位置会根据标尺与当前表格价格动态生成。")
        info.setStyleSheet("color: #6c757d; font-size: 12px; padding: 5px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        tab_widget = QTabWidget()

        self.product_info_tab = QWidget()
        self.price_audience_tab = QWidget()
        self.price_relation_tab = QWidget()

        tab_widget.addTab(self.product_info_tab, "📦 产品信息（用户上传）")
        tab_widget.addTab(self.price_audience_tab, "👥 价格人群规则")
        tab_widget.addTab(self.price_relation_tab, "💰 价格相对位置规则")

        layout.addWidget(tab_widget)

        self.init_product_info_tab()
        self.init_price_audience_tab()
        self.init_price_relation_tab()

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

    def init_price_audience_tab(self):
        layout = QVBoxLayout(self.price_audience_tab)

        label = QLabel("【价格人群标尺规则】")
        label.setStyleSheet("font-weight: bold; color: #2980b9;")
        layout.addWidget(label)

        desc = QLabel("💡 可使用变量：{price_audience_level}、{price_audience_desc}、{product_name}、{current_spec_name}、{custom_hint}")
        desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.price_audience_prompt_text = QTextEdit()
        self.price_audience_prompt_text.setMinimumHeight(350)
        self.price_audience_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.price_audience_prompt_text)

    def init_price_relation_tab(self):
        layout = QVBoxLayout(self.price_relation_tab)

        label = QLabel("【价格相对位置规则】")
        label.setStyleSheet("font-weight: bold; color: #e67e22;")
        layout.addWidget(label)

        desc = QLabel("💡 可使用变量：{price_relation_summary}、{spec_price_layout}、{product_name}、{current_spec_name}")
        desc.setStyleSheet("color: #6c757d; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.price_relation_prompt_text = QTextEdit()
        self.price_relation_prompt_text.setMinimumHeight(350)
        self.price_relation_prompt_text.setStyleSheet("""
            QTextEdit {
                background-color: #fff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.price_relation_prompt_text)

    def get_default_product_info_prompt(self):
        return """（请在此处输入产品相关信息，如：垆土铁棍山药、密度高、偶尔有锈斑等）"""

    def get_default_price_audience_prompt(self):
        return get_default_price_audience_prompt_v2()

    def get_default_price_relation_prompt(self):
        return """【价格相对位置规则】
{price_relation_summary}
所有规格当前表格价格：
{spec_price_layout}
如果当前规格不是当前最低价，禁止使用：最便宜、最低价、全网低价、超低价、底价、白菜价、亏本价。
如果当前规格是最高价，应优先解释价值、品质、容量、组合、适用人群，不要伪装成低价款。
如果当前规格是最低价，可以使用入门、实惠、低门槛、尝鲜等词，但仍不能夸大为全网最低。
生成时必须参考所有规格价格，保证命名不会误导顾客。"""

    def load_prompts(self):
        product_info = self.db.get_setting("ai_product_info_prompt", "")
        price_audience = self.db.get_setting("ai_spec_price_audience_prompt", "")
        price_relation = self.db.get_setting("ai_spec_price_relation_prompt", "")

        self.product_info_text.setPlainText(product_info if product_info else self.get_default_product_info_prompt())
        self.price_audience_prompt_text.setPlainText(price_audience if price_audience else self.get_default_price_audience_prompt())
        self.price_relation_prompt_text.setPlainText(price_relation if price_relation else self.get_default_price_relation_prompt())

    def reset_all_prompts(self):
        reply = QMessageBox.question(self, "确认", "确定要恢复所有提示词为默认吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.product_info_text.setPlainText(self.get_default_product_info_prompt())
            self.price_audience_prompt_text.setPlainText(self.get_default_price_audience_prompt())
            self.price_relation_prompt_text.setPlainText(self.get_default_price_relation_prompt())

    def save_prompts(self):
        product_info = self.product_info_text.toPlainText().strip()
        price_audience = self.price_audience_prompt_text.toPlainText().strip()
        price_relation = self.price_relation_prompt_text.toPlainText().strip()

        if not product_info:
            QMessageBox.warning(self, "⚠️ 警告", "产品信息不能为空！")
            return

        self.db.set_setting("ai_product_info_prompt", product_info)
        self.db.set_setting("ai_spec_price_audience_prompt", price_audience)
        self.db.set_setting("ai_spec_price_relation_prompt", price_relation)

        QMessageBox.information(self, "✅ 成功", "产品提示词配置已保存！")
        self.accept()

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEventLoop, QTimer, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from manager.tutorial import (
    SCREEN_ANCHORS,
    TUTORIAL_TOPICS,
    TutorialCatalogDialog,
    TutorialController,
    TutorialOverlay,
    validate_tutorial_catalog,
)
from manager.dialogs.material_library import MaterialLibraryDialog
from manager.dialogs.input_data_dialog import InputDataDialog

_APP = None


def _app():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _wait(milliseconds=100):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec_()


def test_catalog_is_complete_and_uses_registered_anchors():
    assert validate_tutorial_catalog()
    assert len({topic["id"] for topic in TUTORIAL_TOPICS}) == len(TUTORIAL_TOPICS)
    assert {"快速上手", "主界面", "店铺与链接", "记录与任务", "毛利与利润", "资料库", "推广与报表", "拼多多工具", "系统与账号"} <= {
        topic["category"] for topic in TUTORIAL_TOPICS
    }
    for topic in TUTORIAL_TOPICS:
        for step in topic["steps"]:
            screen = step.get("screen", topic["screen"])
            assert step["anchor"] in SCREEN_ANCHORS[screen]
            assert step["example"].strip()


def test_catalog_selection_enables_replay():
    _app()
    dialog = TutorialCatalogDialog()
    first_topic = dialog.tree.topLevelItem(0).child(0)
    dialog.tree.setCurrentItem(first_topic)

    assert dialog.start_button.isEnabled()
    assert dialog.selected_topic_id == TUTORIAL_TOPICS[0]["id"]
    dialog.close()


def test_catalog_keeps_current_release_notes_available():
    _app()
    dialog = TutorialCatalogDialog(release_version="5.17.1", release_notes="修复更新流程")
    assert dialog.release_notes_button.text() == "本次版本更新内容"
    assert dialog.release_notes_button.isEnabled()
    assert dialog.release_notes == "修复更新流程"
    dialog.close()


def test_catalog_numbers_topics_inside_each_category():
    _app()
    dialog = TutorialCatalogDialog()
    for category_index in range(dialog.tree.topLevelItemCount()):
        category = dialog.tree.topLevelItem(category_index)
        for topic_index in range(category.childCount()):
            assert category.child(topic_index).text(0).startswith(f"{topic_index + 1}. ")
    dialog.close()


def test_main_calendar_tutorial_uses_current_data_cards():
    topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "calendar_navigation")
    anchors = [step["anchor"] for step in topic["steps"]]
    assert "today" not in SCREEN_ANCHORS["main"]
    assert anchors == ["month_prev", "store_bubble", "product_bubble"]


def test_updated_tutorials_match_current_controls():
    spec_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "product_spec")
    cost_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "cost_library")
    material_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "material_library")
    search_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "search_filters")

    assert SCREEN_ANCHORS["product_spec"]["discount"] == "promo_widget"
    assert SCREEN_ANCHORS["product_spec"]["batch"] == "batch_price_controls"
    assert "批量改价" in spec_topic["steps"][2]["title"]
    assert "权重" not in spec_topic["steps"][2]["example"]
    assert "AI选品" not in str(cost_topic)
    assert "Ctrl+Shift+S" in material_topic["steps"][1]["text"]
    assert "空格" in material_topic["steps"][2]["text"]
    assert search_topic["steps"][-1]["anchor"] == "sort_direction"
    assert [step["anchor"] for step in cost_topic["steps"][-3:]] == ["combo_review", "history", "lan_sync"]
    assert "save" not in SCREEN_ANCHORS["cost"]
    assert material_topic["steps"][-1]["anchor"] == "mobile"

    store_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "store_margin")
    assert "order_table" in [step["anchor"] for step in store_topic["steps"]]

    pdd_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "pdd_tools")
    assert [step["anchor"] for step in pdd_topic["steps"][-2:]] == ["pdd_code", "pdd_price"]
    assert "跳转下一个未匹配" in pdd_topic["steps"][-1]["text"]

    settings_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "settings_shortcuts")
    assert settings_topic["steps"][-1]["anchor"] == "font"

    reports_topic = next(row for row in TUTORIAL_TOPICS if row["id"] == "reports_exports")
    report_anchors = [step["anchor"] for step in reports_topic["steps"]]
    assert report_anchors[:7] == ["manual", "form", "preview", "save", "images", "table", "export"]
    assert "history" not in report_anchors
    assert "低频" in reports_topic["steps"][7]["title"]
    assert "每周更新不再需要" in reports_topic["steps"][7]["text"]


def test_margin_input_tutorial_targets_the_real_form():
    _app()
    dialog = InputDataDialog()
    assert dialog.width() == 250
    assert dialog.minimumWidth() == dialog.maximumWidth() == 250
    assert all("调试" not in label.text() for label in dialog.findChildren(QLabel))
    assert SCREEN_ANCHORS["margin_input"] == {
        "form": "input_form_widget",
        "preview": "btn_calculate",
        "save": "btn_confirm",
    }
    tutorial_dialog = InputDataDialog(tutorial_mode=True)
    assert tutorial_dialog.width() == 900
    assert dialog.input_form_widget is not None
    assert dialog.btn_calculate.text() == "🧮 计算并预览"
    assert dialog.btn_confirm.text() == "✅ 确认保存"
    dialog.close()
    tutorial_dialog.close()


def test_tutorial_card_does_not_cover_a_highlight_when_space_exists():
    app = _app()
    host = QWidget()
    host.resize(900, 680)
    target = QWidget(host)
    target.setGeometry(20, 80, 420, 340)
    host.show()
    app.processEvents()

    overlay = TutorialOverlay(host, target)
    overlay.set_step(
        {"title": "填写本周经营数据", "text": "讲解文字不能挡住表单。", "example": "示例数据。"},
        1,
        4,
        target,
    )
    app.processEvents()
    assert not overlay.card.geometry().intersects(overlay._target_rect())
    overlay.close()
    host.close()


def test_material_search_supports_space_separated_terms():
    assert MaterialLibraryDialog.search_text_matches(None, "水杯 red", "夏季水杯", "RED-M")
    assert not MaterialLibraryDialog.search_text_matches(None, "水杯 blue", "夏季水杯", "RED-M")


def test_controller_resolves_dynamic_main_targets():
    _app()

    class FakeMain(QWidget):
        def __init__(self):
            super().__init__()
            self.target = QPushButton(self)
            self.requested = []

        def resolve_tutorial_target(self, name):
            self.requested.append(name)
            return self.target

    main = FakeMain()
    controller = TutorialController(main)
    assert controller._resolve_target(main, "main", "store_bubble") is main.target
    assert main.requested == ["first_store_bubble"]
    main.close()


def test_overlay_tracks_target_and_blocks_underlying_clicks():
    app = _app()
    host = QWidget()
    host.resize(900, 600)
    target = QPushButton("危险操作", host)
    target.setGeometry(80, 70, 120, 36)
    clicked = []
    target.clicked.connect(lambda: clicked.append(True))
    host.show()
    app.processEvents()

    overlay = TutorialOverlay(host, target)
    overlay.set_step(
        {"title": "只读步骤", "text": "底层按钮不能点击。", "example": "示例不保存。"},
        0,
        1,
        target,
    )
    app.processEvents()
    hole = overlay._target_rect()
    assert hole.contains(overlay.mapFromGlobal(target.mapToGlobal(target.rect().center())))

    QTest.mouseClick(overlay, Qt.LeftButton, pos=hole.center())
    assert clicked == []

    host.resize(1000, 700)
    app.processEvents()
    assert overlay.geometry() == host.rect()
    overlay.close()
    host.close()


def test_controller_can_exit_and_start_again_without_writes():
    app = _app()

    class FakeMain(QWidget):
        def __init__(self):
            super().__init__()
            self.resize(900, 600)
            self.btn_tutorial = QPushButton("教程", self)
            self.btn_tutorial.setGeometry(760, 20, 100, 32)
            self.opened = []

        def open_tutorial_screen(self, screen):
            self.opened.append(screen)
            self.show()
            return self, False, ""

    main = FakeMain()
    main.show()
    app.processEvents()
    controller = TutorialController(main)
    controller.start_topic("overview")
    _wait()

    assert controller.overlay is not None
    assert main.opened == ["main"]
    controller.exit_tutorial()
    assert controller.overlay is None

    controller.start_topic("overview")
    _wait()
    assert controller.overlay is not None
    controller.exit_tutorial()
    main.close()


def test_controller_closes_its_previous_window_when_switching_screens():
    app = _app()

    class FakeMain(QWidget):
        def __init__(self):
            super().__init__()
            self.resize(900, 600)
            self.opened = []

        def open_tutorial_screen(self, screen):
            window = QWidget()
            window.resize(700, 500)
            window.show()
            self.opened.append(window)
            return window, True, ""

    main = FakeMain()
    main.show()
    app.processEvents()
    controller = TutorialController(main)
    controller.start_topic("records_tasks")
    _wait()
    controller.next_step()
    _wait()

    opened = list(main.opened)
    assert len(opened) == 2
    assert not opened[0].isVisible()
    assert opened[1].isVisible()
    controller.exit_tutorial()
    app.processEvents()
    assert not any(window.isVisible() for window in opened)
    main.close()

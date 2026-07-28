import os
import json
import tempfile
import unittest

from manager.dialogs.material_library import MaterialLibraryDialog


class FakeEditor:
    def __init__(self):
        self.text = ""

    def toPlainText(self):
        return self.text

    def setPlainText(self, text):
        self.text = text

    def blockSignals(self, _blocked):
        pass

    def setEnabled(self, _enabled):
        pass


class FakeList:
    def __init__(self):
        self.items = []
        self.current_row = -1

    def blockSignals(self, _blocked):
        pass

    def clear(self):
        self.items = []

    def addItem(self, item):
        self.items.append(item)

    def setCurrentRow(self, row):
        self.current_row = row

    def item(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def row(self, item):
        return self.items.index(item)

    def setEnabled(self, _enabled):
        pass


class FakeLabel:
    def setText(self, _text):
        pass


class FakeTimer:
    def stop(self):
        pass


class FakeWidget:
    def __init__(self, parent=None):
        self.parent = parent

    def parentWidget(self):
        return self.parent


class LinkReferenceSubject:
    LINK_MODE = "link"
    library_mode = LINK_MODE
    link_type_reference_store_path = MaterialLibraryDialog.link_type_reference_store_path
    load_link_type_reference = MaterialLibraryDialog.load_link_type_reference
    save_link_type_reference = MaterialLibraryDialog.save_link_type_reference
    link_type_reference_entries = MaterialLibraryDialog.link_type_reference_entries
    refresh_link_type_reference_list = MaterialLibraryDialog.refresh_link_type_reference_list
    show_current_link_type_reference = MaterialLibraryDialog.show_current_link_type_reference
    on_link_type_reference_renamed = MaterialLibraryDialog.on_link_type_reference_renamed

    def __init__(self, root):
        self.root = root
        self.selected_link_type = "主图链接"
        self._link_reference_loaded_type = ""
        self._link_reference_loaded_path = ""
        self._link_reference_data = {}
        self._link_reference_current_index = -1
        self._link_reference_loading = False
        self.link_reference_list = FakeList()
        self.link_reference_editor = FakeEditor()
        self.link_reference_type_label = FakeLabel()
        self.link_reference_save_timer = FakeTimer()

    def root_folder_for_mode(self, _mode):
        return self.root


class MaterialLinkReferenceTest(unittest.TestCase):
    def test_hovered_image_list_is_found_through_its_viewport(self):
        product_list = FakeWidget()
        main_list = FakeWidget()
        main_viewport = FakeWidget(main_list)
        subject = type(
            "PasteRoutingSubject",
            (),
            {"image_list": product_list, "link_image_lists": {"main": main_list}},
        )()

        resolved = MaterialLibraryDialog.material_image_list_for_widget(subject, main_viewport)

        self.assertIs(resolved, main_list)

    def test_multiple_named_notes_and_legacy_note_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as root:
            path = os.path.join(root, ".shop_link_type_references.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"旧链接": "旧版单条内容"}, fh, ensure_ascii=False)
            subject = LinkReferenceSubject(root)
            subject.load_link_type_reference(force=True)
            subject._link_reference_data["主图链接"] = [
                {"title": "产品分析", "content": "分析内容"},
                {"title": "通用提示词", "content": "提示词内容"},
            ]
            subject.refresh_link_type_reference_list(1)
            subject.link_reference_list.item(1).setText("新版提示词")
            subject.on_link_type_reference_renamed(subject.link_reference_list.item(1))
            subject.save_link_type_reference(silent=True)

            reloaded = LinkReferenceSubject(root)
            reloaded.load_link_type_reference(force=True)
            self.assertEqual([entry["title"] for entry in reloaded.link_type_reference_entries()], ["产品分析", "新版提示词"])
            reloaded.selected_link_type = "旧链接"
            reloaded.load_link_type_reference(force=True)
            self.assertEqual(reloaded.link_type_reference_entries(), [{"title": "未命名文案", "content": "旧版单条内容"}])


if __name__ == "__main__":
    unittest.main()

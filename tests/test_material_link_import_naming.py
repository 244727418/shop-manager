import os
import tempfile
import unittest

from manager.dialogs.material_library import MaterialLibraryDialog


class LinkImportNamingSubject:
    LINK_MODE = "link"
    library_mode = LINK_MODE
    IMAGE_EXTENSIONS = MaterialLibraryDialog.IMAGE_EXTENSIONS
    link_import_filename = MaterialLibraryDialog.link_import_filename
    allocate_link_column_index = MaterialLibraryDialog.allocate_link_column_index
    classify_link_image_name = MaterialLibraryDialog.classify_link_image_name
    link_image_column_prefix = MaterialLibraryDialog.link_image_column_prefix

    def is_image_file(self, path):
        return os.path.isfile(path) and os.path.splitext(path)[1].lower() in self.IMAGE_EXTENSIONS


class MaterialLinkImportNamingTest(unittest.TestCase):
    def test_main_and_detail_are_numbered_but_sku_keeps_original_name(self):
        subject = LinkImportNamingSubject()
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as folder:
            open(os.path.join(folder, "主图（1）.png"), "wb").close()
            open(os.path.join(folder, "主图（3）.jpg"), "wb").close()
            allocations = {}

            self.assertEqual(subject.link_import_filename(folder, "原图.jpg", "main", allocations), "主图（2）.jpg")
            self.assertEqual(subject.link_import_filename(folder, "另一张.png", "main", allocations), "主图（4）.png")
            self.assertEqual(subject.link_import_filename(folder, "详情.webp", "detail", allocations), "详情页（1）.webp")
            self.assertEqual(subject.link_import_filename(folder, "规格原图.png", "sku", allocations), "规格原图.png")


if __name__ == "__main__":
    unittest.main()

import base64
import hashlib
import json
import os
import tempfile
import time
import unittest

from PyQt5.QtCore import QByteArray, QBuffer, QEvent, QIODevice, Qt
from PyQt5.QtGui import QImage, QKeyEvent
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton

from manager.cost_sync_service import CostSyncService
from manager.db import SafeDatabaseManager
from manager.dialogs.cost_library import CostHistoryDialog, CostLibraryDialog, UnlistedCostSpecsDialog
from manager.dialogs.cost_sync import CostSyncDialog
from manager.dialogs.material_library import MaterialImageViewerDialog, MaterialLibraryDialog


class CostSyncDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = SafeDatabaseManager(os.path.join(self.temp.name, "host.db"))
        self.db.configure_cost_sync("group-a", "文创", "host", "s" * 32)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    @staticmethod
    def detail_snapshot(product_cost=2.0, stamp=0, device=""):
        metadata = {"_modified_at": stamp, "_modified_by": device} if stamp else {}
        return {
            "schema": 1,
            "categories": [{"label": "本册", "color": "#DDEEFF", "sort_order": 1, **metadata}],
            "rows": [{
                "spec_code": "SKU-1",
                "spec_name": "错题本3本",
                "category_label": "本册",
                "category_color": "#DDEEFF",
                "quantity": "3",
                "product_attribute": "尺寸：A5",
                "combo_disabled": 0,
                "is_combo": 0,
                "product_cost": product_cost,
                "unit_weight": 0.2,
                "cost_calc_mode": "detail",
                "cost_price": None,
                "sort_order": 1,
                "manual_sort_order": None,
                **metadata,
            }],
            "images": [],
        }

    def test_invite_and_hmac_are_stable(self):
        payload, token = CostSyncService.create_invite("文创", "192.168.1.23:48781")
        invite = CostSyncService.parse_invite(token)
        self.assertEqual(invite["group_id"], payload["group_id"])
        self.assertEqual(invite["host"], "192.168.1.23:48781")
        signature = CostSyncService.make_signature("secret", "POST", "/path", "1", "n", b"{}")
        self.assertEqual(signature, CostSyncService.make_signature("secret", "POST", "/path", "1", "n", b"{}"))
        self.assertNotEqual(signature, CostSyncService.make_signature("wrong", "POST", "/path", "1", "n", b"{}"))

    def test_rejoining_same_group_preserves_sync_checkpoint(self):
        self.db.publish_cost_sync_snapshot(self.detail_snapshot(stamp=100, device="pc-a"), "pc-a")
        previous = self.db.get_cost_sync_state()
        self.db.configure_cost_sync("group-a", "文创", "client", "s" * 32, "192.168.1.23:48781")
        state = self.db.get_cost_sync_state()
        self.assertEqual(state["revision"], previous["revision"])
        self.assertEqual(state["snapshot_hash"], previous["snapshot_hash"])
        self.db.configure_cost_sync("group-b", "文创新组织", "client", "t" * 32, "192.168.1.24:48781")
        state = self.db.get_cost_sync_state()
        self.assertEqual(state["revision"], 0)
        self.assertFalse(state.get("snapshot_hash"))
        self.assertEqual(self.db.safe_fetchall("SELECT spec_code FROM cost_library"), [("SKU-1",)])

    def test_sync_dialog_shows_local_ip_without_internal_counters(self):
        app = QApplication.instance() or QApplication([])
        dialog = CostSyncDialog(self.db)
        texts = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertTrue(dialog.local_ip_label.text())
        self.assertNotIn("这台电脑的数据编号:", texts)
        self.assertNotIn("等待发送的修改:", texts)
        dialog.close()
        app.processEvents()

    def test_publish_is_idempotent_and_propagates_newer_deletion(self):
        first = self.db.publish_cost_sync_snapshot(self.detail_snapshot(stamp=100, device="pc-a"), "pc-a")
        self.assertEqual(first["revision"], 1)
        self.assertEqual(self.db.safe_fetchall("SELECT COUNT(*) FROM cost_library")[0][0], 1)

        same = self.db.publish_cost_sync_snapshot(self.detail_snapshot(stamp=100, device="pc-a"), "pc-a")
        self.assertEqual(same["revision"], 1)
        self.assertEqual(same["changed_codes"], [])

        deleted = {
            "schema": 1,
            "rows": [{"spec_code": "SKU-1", "_deleted": True, "_modified_at": 110, "_modified_by": "pc-b"}],
            "categories": [],
        }
        result = self.db.publish_cost_sync_snapshot(deleted, "pc-b")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(self.db.safe_fetchall("SELECT spec_code FROM cost_library"), [])

    def test_newest_record_timestamp_wins(self):
        self.db.publish_cost_sync_snapshot(self.detail_snapshot(2.0, 200, "pc-a"), "pc-a")
        older = self.db.publish_cost_sync_snapshot(self.detail_snapshot(9.0, 190, "pc-b"), "pc-b")
        self.assertEqual(older["revision"], 1)
        self.assertAlmostEqual(self.db.safe_fetchall("SELECT product_cost FROM cost_library")[0][0], 2.0)
        newer = self.db.publish_cost_sync_snapshot(self.detail_snapshot(3.0, 210, "pc-b"), "pc-b")
        self.assertEqual(newer["revision"], 2)
        self.assertAlmostEqual(self.db.safe_fetchall("SELECT product_cost FROM cost_library")[0][0], 3.0)

    def test_detail_cost_uses_receiving_computer_settings(self):
        self.db.set_cost_misc_fee(0.45)
        published = self.db.publish_cost_sync_snapshot(self.detail_snapshot(stamp=100, device="pc-a"), "pc-a")
        client = SafeDatabaseManager(os.path.join(self.temp.name, "client.db"))
        try:
            client.configure_cost_sync("group-a", "文创", "client", "s" * 32, "127.0.0.1")
            client.set_cost_misc_fee(1.25)
            self.assertEqual(self.db.get_cost_misc_fee(), 0.45)
            self.assertEqual(client.get_cost_misc_fee(), 1.25)
            snapshot_json = client._cost_sync_snapshot_json(published["snapshot"])
            digest = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
            result = client.apply_remote_cost_sync_snapshot(published["snapshot"], 1, digest, "pc-a", "now")
            self.assertEqual(result["changed_codes"], ["SKU-1"])
            host_cost = self.db.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code='SKU-1'")[0][0]
            client_cost = client.safe_fetchall("SELECT cost_price FROM cost_library WHERE spec_code='SKU-1'")[0][0]
            self.assertNotEqual(host_cost, client_cost)
            self.assertAlmostEqual(client_cost - host_cost, 0.8, places=6)
        finally:
            client.close()

    def test_incomplete_detail_cost_stays_uncomputed_after_sync(self):
        client = SafeDatabaseManager(os.path.join(self.temp.name, "blank-detail-client.db"))
        try:
            client.apply_cost_sync_snapshot(
                self.detail_snapshot(product_cost=None), replace_local=True
            )
            self.assertEqual(
                client.safe_fetchall(
                    """SELECT product_cost, unit_weight, shipping_fee, misc_fee, cost_price
                       FROM cost_library WHERE spec_code='SKU-1'"""
                )[0],
                (None, 0.2, None, None, None),
            )
        finally:
            client.close()

    def test_shipping_rules_and_misc_fee_are_account_local_and_not_in_snapshot(self):
        client = SafeDatabaseManager(os.path.join(self.temp.name, "fee-client.db"))
        try:
            host_rules = json.loads(json.dumps(self.db.DEFAULT_COST_SHIPPING_RULES))
            client_rules = json.loads(json.dumps(self.db.DEFAULT_COST_SHIPPING_RULES))
            host_rules["ranges"][0]["fee"] = 1.11
            client_rules["ranges"][0]["fee"] = 2.22
            self.db.set_cost_misc_fee(0.3)
            client.set_cost_misc_fee(0.9)
            self.db.set_cost_shipping_rules(host_rules)
            client.set_cost_shipping_rules(client_rules)

            self.assertEqual(self.db.get_cost_misc_fee(), 0.3)
            self.assertEqual(client.get_cost_misc_fee(), 0.9)
            self.assertEqual(self.db.get_cost_shipping_rules()["ranges"][0]["fee"], 1.11)
            self.assertEqual(client.get_cost_shipping_rules()["ranges"][0]["fee"], 2.22)
            snapshot = self.db.build_cost_sync_snapshot()
            self.assertNotIn("cost_misc_fee", snapshot)
            self.assertNotIn("cost_shipping_rules_json", snapshot)
        finally:
            client.close()

    def test_cost_library_mode_is_account_local(self):
        client = SafeDatabaseManager(os.path.join(self.temp.name, "mode-client.db"))
        try:
            self.db.set_cost_library_mode("detail")
            client.set_cost_library_mode("total")
            self.assertEqual(self.db.get_cost_library_mode(), "detail")
            self.assertEqual(client.get_cost_library_mode(), "total")
        finally:
            client.close()

    def test_unlisted_specs_shows_and_copies_image_without_quantity_column(self):
        app = QApplication.instance() or QApplication([])
        image = QImage(4, 4, QImage.Format_RGB32)
        image.fill(Qt.red)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        self.db.safe_execute(
            """INSERT INTO cost_library
               (spec_code, spec_name, category_label, quantity, thumbnail_data)
               VALUES ('UNLISTED-1', '未上架商品', '练习本', '3', ?)""",
            (bytes(data),),
        )

        dialog = UnlistedCostSpecsDialog(self.db)
        try:
            self.assertEqual(
                [dialog.model.headerData(i, Qt.Horizontal) for i in range(dialog.model.columnCount())],
                ["图片", "商品类型", "规格名称"],
            )
            image_index = dialog.model.index(0, dialog.COL_IMAGE)
            dialog.table_view.setCurrentIndex(image_index)
            dialog.copy_selected()
            self.assertFalse(QApplication.clipboard().pixmap().isNull())
        finally:
            dialog.close()
            app.processEvents()

    def test_single_unit_cost_history_syncs_without_remote_duplicates(self):
        self.db.publish_cost_sync_snapshot(self.detail_snapshot(2.0, 100, "pc-a"), "pc-a")
        self.assertEqual(self.db.safe_fetchall("SELECT COUNT(*) FROM cost_history")[0][0], 0)
        self.db.safe_execute("UPDATE cost_library SET product_cost=2.5 WHERE spec_code='SKU-1'")
        history = self.db.safe_fetchall(
            "SELECT event_id, spec_code, operation_type, old_value, new_value, source FROM cost_history"
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0][1:], ("SKU-1", "product_cost", "2.0", "2.5", "manual"))

        client = SafeDatabaseManager(os.path.join(self.temp.name, "history-client.db"))
        try:
            result = client.apply_cost_sync_snapshot(self.db.build_cost_sync_snapshot(), replace_local=True)
            self.assertEqual(result["history_changed_count"], 1)
            self.assertEqual(client.safe_fetchall("SELECT event_id FROM cost_history"), [(history[0][0],)])
            client.apply_cost_sync_snapshot(self.db.build_cost_sync_snapshot(), replace_local=False)
            self.assertEqual(client.safe_fetchall("SELECT COUNT(*) FROM cost_history")[0][0], 1)

            self.assertEqual(self.db.clear_cost_history(), 1)
            client.apply_cost_sync_snapshot(self.db.build_cost_sync_snapshot(), replace_local=False)
            self.assertEqual(client.safe_fetchall("SELECT COUNT(*) FROM cost_history")[0][0], 0)
        finally:
            client.close()

    def test_total_cost_changes_do_not_create_product_cost_history(self):
        self.db.cursor.execute(
            """INSERT INTO cost_library
               (spec_code, spec_name, cost_price, cost_calc_mode)
               VALUES ('TOTAL-ONLY', '总成本商品', 3, 'total')"""
        )
        self.db.conn.commit()
        self.db.safe_execute(
            "UPDATE cost_library SET cost_price=4 WHERE spec_code='TOTAL-ONLY'"
        )
        self.assertEqual(
            self.db.safe_fetchall(
                "SELECT operation_type FROM cost_history WHERE spec_code='TOTAL-ONLY'"
            ),
            [],
        )

    def test_legacy_total_cost_history_is_not_synced(self):
        self.db.cursor.execute(
            """INSERT INTO cost_history
               (event_id, spec_code, operation_type, old_value, new_value,
                old_cost_price, new_cost_price, source, import_time, event_time_ms)
               VALUES ('legacy-total', 'SKU-OLD', 'price', '3', '4', 3, 4,
                       'manual', '2026-01-01 10:00:00', 1)"""
        )
        self.db.cursor.execute(
            """INSERT INTO cost_history
               (event_id, spec_code, operation_type, old_value, new_value,
                old_cost_price, new_cost_price, source, import_time, event_time_ms)
               VALUES ('product-cost', 'SKU-NEW', 'product_cost', '2', '2.5', 2, 2.5,
                       'manual', '2026-01-01 10:00:01', 2)"""
        )
        self.db.conn.commit()

        snapshot = self.db.build_cost_sync_snapshot()
        self.assertEqual(
            [event["event_id"] for event in snapshot["history"]],
            ["product-cost"],
        )

        merged = self.db.merge_cost_sync_snapshots(
            {"schema": 1, "history": [dict(
                event_id="legacy-total",
                operation_type="price",
                event_time_ms=1,
            )]},
            snapshot,
        )
        self.assertEqual(
            [event["event_id"] for event in merged["history"]],
            ["product-cost"],
        )

        client = SafeDatabaseManager(os.path.join(self.temp.name, "legacy-history-client.db"))
        try:
            snapshot["history"].append({
                "event_id": "remote-legacy-total",
                "spec_code": "SKU-OLD",
                "operation_type": "price",
                "old_value": "4",
                "new_value": "5",
                "source": "lan",
                "import_time": "2026-01-01 10:00:02",
                "event_time_ms": 3,
            })
            client.apply_cost_sync_snapshot(snapshot, replace_local=True)
            self.assertEqual(
                client.safe_fetchall(
                    "SELECT event_id FROM cost_history ORDER BY event_time_ms"
                ),
                [("product-cost",)],
            )
        finally:
            client.close()

    def test_legacy_total_cost_history_is_removed_on_startup(self):
        path = os.path.join(self.temp.name, "legacy-history.db")
        legacy = SafeDatabaseManager(path)
        legacy.cursor.execute(
            """INSERT INTO cost_history
               (event_id, spec_code, operation_type, old_value, new_value,
                old_cost_price, new_cost_price, source, import_time, event_time_ms)
               VALUES ('legacy-total', 'SKU-OLD', 'price', '3', '4', 3, 4,
                       'manual', '2026-01-01 10:00:00', 1)"""
        )
        legacy.cursor.execute(
            """INSERT INTO cost_history
               (event_id, spec_code, operation_type, old_value, new_value,
                old_cost_price, new_cost_price, source, import_time, event_time_ms)
               VALUES ('product-cost', 'SKU-NEW', 'product_cost', '2', '2.5', 2, 2.5,
                       'manual', '2026-01-01 10:00:01', 2)"""
        )
        legacy.conn.commit()
        legacy.close()

        reopened = SafeDatabaseManager(path)
        try:
            self.assertEqual(
                reopened.safe_fetchall(
                    "SELECT event_id, operation_type FROM cost_history ORDER BY event_time_ms"
                ),
                [("product-cost", "product_cost")],
            )
        finally:
            reopened.close()

    def test_spec_code_rename_migrates_references_and_syncs_to_peers(self):
        self.db.publish_cost_sync_snapshot(self.detail_snapshot(2.0, 100, "pc-a"), "pc-a")
        self.db.cursor.execute(
            "INSERT INTO products (id, store_id, name, title) VALUES (1, 1, 'LINK-1', '测试链接')"
        )
        self.db.cursor.execute(
            """INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent)
               VALUES (1, '错题本3本', 'SKU-1', 0, 0)"""
        )
        self.db.cursor.execute(
            """INSERT INTO imported_orders
               (store_id, product_id, spec_code, order_count, import_time, actual_amount, refund_count)
               VALUES (1, 'LINK-1', 'SKU-1', 2, '2026-01-01', 10, 0)"""
        )
        self.db.cursor.execute(
            """INSERT INTO cost_library
               (spec_code, spec_name, cost_price, combo_components_json, product_attribute_is_combo)
               VALUES ('COMBO-1', '组合商品', 3, '[{"spec_code":"SKU-1","quantity":2}]', 1)"""
        )
        self.db.conn.commit()

        baseline = self.db.build_cost_sync_snapshot()
        client = SafeDatabaseManager(os.path.join(self.temp.name, "rename-client.db"))
        try:
            client.apply_cost_sync_snapshot(baseline, replace_local=True)
            client.cursor.execute(
                "INSERT INTO products (id, store_id, name, title) VALUES (1, 1, 'LINK-1', '测试链接')"
            )
            client.cursor.execute(
                """INSERT INTO product_specs (product_id, spec_name, spec_code, sale_price, weight_percent)
                   VALUES (1, '错题本3本', 'SKU-1', 0, 0)"""
            )
            client.conn.commit()

            self.assertTrue(self.db.rename_cost_spec_code("SKU-1", "SKU-NEW"))
            self.assertEqual(
                self.db.safe_fetchall("SELECT spec_code FROM product_specs"), [("SKU-NEW",)]
            )
            self.assertEqual(
                self.db.safe_fetchall("SELECT spec_code FROM imported_orders"), [("SKU-NEW",)]
            )
            combo_items = json.loads(self.db.safe_fetchall(
                "SELECT combo_components_json FROM cost_library WHERE spec_code='COMBO-1'"
            )[0][0])
            self.assertEqual(combo_items[0]["spec_code"], "SKU-NEW")
            self.assertEqual(
                self.db.safe_fetchall(
                    "SELECT operation_type, old_value, new_value FROM cost_history "
                    "WHERE operation_type='code' ORDER BY id DESC LIMIT 1"
                )[0],
                ("code", "SKU-1", "SKU-NEW"),
            )

            changes = CostSyncService(lambda *_args: {})._snapshot_diff(
                baseline, self.db.build_cost_sync_snapshot()
            )
            client.apply_cost_sync_snapshot(changes, replace_local=False)
            self.assertEqual(
                client.safe_fetchall("SELECT spec_code FROM product_specs"), [("SKU-NEW",)]
            )
        finally:
            client.close()

    def test_operation_history_records_metadata_and_dialog_filters(self):
        app = QApplication.instance() or QApplication([])
        self.db.publish_cost_sync_snapshot(self.detail_snapshot(2.0, 100, "pc-a"), "pc-a")
        self.db.safe_execute(
            """UPDATE cost_library
               SET spec_name='新名称', category_label='新类型', product_attribute='尺寸：A4',
                   quantity='5', unit_weight=0.3, thumbnail_data=X'01'
               WHERE spec_code='SKU-1'"""
        )
        operations = {
            row[0] for row in self.db.safe_fetchall("SELECT operation_type FROM cost_history")
        }
        self.assertEqual(operations, {"name", "category", "attribute", "quantity", "weight", "image"})

        dialog = CostHistoryDialog(self.db)
        self.assertEqual(dialog.windowTitle(), "历史操作")
        self.assertIsNone(dialog.parent())
        self.assertEqual(dialog.table_view.textElideMode(), 3)
        self.assertEqual(dialog.model.rowCount(), 6)
        self.assertEqual(dialog.table_view.columnWidth(dialog.COL_IMAGE), dialog.ROW_SIZE)
        self.assertLessEqual(dialog.table_view.columnWidth(dialog.COL_NAME), 360)
        dialog._select_all_operations()
        self.assertEqual(len(dialog.operation_list.selectedItems()), dialog.operation_list.count())
        dialog._invert_operations()
        self.assertEqual(len(dialog.operation_list.selectedItems()), 0)
        for row in range(dialog.operation_list.count()):
            item = dialog.operation_list.item(row)
            item.setSelected(item.data(256) == "name")
        app.processEvents()
        self.assertEqual(dialog.model.rowCount(), 1)
        self.assertEqual(dialog.model.item(0, dialog.COL_OPERATION).text(), "修改名称")
        dialog.close()
        app.processEvents()

    def test_detail_snapshot_omits_local_derived_total(self):
        self.db.publish_cost_sync_snapshot(self.detail_snapshot(stamp=100, device="pc-a"), "pc-a")
        snapshot = self.db.build_cost_sync_snapshot()
        self.assertIsNone(snapshot["rows"][0]["cost_price"])

    def test_category_only_change_is_reported_and_updates_row_color_cache(self):
        self.db.publish_cost_sync_snapshot(self.detail_snapshot(stamp=100, device="pc-a"), "pc-a")
        snapshot = self.detail_snapshot(stamp=110, device="pc-b")
        snapshot["categories"][0]["color"] = "#123456"
        snapshot["categories"][0]["sort_order"] = 9
        result = self.db.publish_cost_sync_snapshot(snapshot, "pc-b")
        self.assertTrue(result["categories_changed"])
        self.assertEqual(result["changed_codes"], [])
        self.assertEqual(
            self.db.safe_fetchall("SELECT category_color FROM cost_library WHERE spec_code='SKU-1'")[0][0],
            "#123456",
        )

    def test_thumbnail_auto_fill_never_overwrites_but_manual_replacement_does(self):
        first_image = base64.b64encode(b"first-white-image").decode("ascii")
        other_image = base64.b64encode(b"other-white-image").decode("ascii")
        manual_image = base64.b64encode(b"manual-image").decode("ascii")
        first = self.detail_snapshot(stamp=100, device="pc-a")
        first["images"] = [{
            "spec_code": "SKU-1", "data": first_image, "manual": 0,
            "_modified_at": 100, "_modified_by": "pc-a",
        }]
        self.db.publish_cost_sync_snapshot(first, "pc-a")

        automatic_conflict = {
            "schema": 1, "rows": [], "categories": [],
            "images": [{
                "spec_code": "SKU-1", "data": other_image, "manual": 0,
                "_modified_at": 110, "_modified_by": "pc-b",
            }],
        }
        unchanged = self.db.publish_cost_sync_snapshot(automatic_conflict, "pc-b")
        self.assertEqual(unchanged["revision"], 1)
        self.assertEqual(
            bytes(self.db.safe_fetchall(
                "SELECT thumbnail_data FROM cost_library WHERE spec_code='SKU-1'"
            )[0][0]),
            b"first-white-image",
        )

        manual_replacement = {
            "schema": 1, "rows": [], "categories": [],
            "images": [{
                "spec_code": "SKU-1", "data": manual_image, "manual": 1,
                "_modified_at": 120, "_modified_by": "pc-b",
            }],
        }
        replaced = self.db.publish_cost_sync_snapshot(manual_replacement, "pc-b")
        self.assertEqual(replaced["image_changed_codes"], ["SKU-1"])
        stored = self.db.safe_fetchall(
            "SELECT thumbnail_data, thumbnail_manual FROM cost_library WHERE spec_code='SKU-1'"
        )[0]
        self.assertEqual((bytes(stored[0]), stored[1]), (b"manual-image", 1))
        self.assertEqual(self.db.build_cost_sync_snapshot()["images"][0]["data"], manual_image)

        service = CostSyncService(lambda *_args: {})
        diff = service._snapshot_diff(
            {"schema": 1, "rows": [], "categories": [], "images": manual_replacement["images"]},
            {"schema": 1, "rows": [], "categories": [], "images": []},
        )
        self.assertEqual(diff["images"], [])

    def test_snapshot_diff_ignores_received_metadata_and_tracks_real_changes(self):
        service = CostSyncService(lambda *_args: {})
        old = self.detail_snapshot(2.0, 100, "pc-a")
        unchanged = self.detail_snapshot(2.0)
        self.assertFalse(service._has_changes(service._snapshot_diff(old, unchanged)))
        changed = self.detail_snapshot(2.5)
        diff = service._snapshot_diff(old, changed)
        self.assertEqual([row["spec_code"] for row in diff["rows"]], ["SKU-1"])
        self.assertGreater(diff["rows"][0]["_modified_at"], 0)

    def test_initial_sync_flag_is_only_cleared_after_contacting_a_peer(self):
        skip = {"value": True}

        def provider(action, _payload):
            if action == "skip_initial_diff":
                return {"skip": skip["value"]}
            if action == "clear_skip_initial_diff":
                skip["value"] = False
                return {"ok": True}
            raise ValueError(action)

        service = CostSyncService(provider)
        self.assertTrue(service._should_skip_initial_diff({"revision": 3, "snapshot_hash": "known"}))
        self.assertTrue(skip["value"])

    def test_cost_table_edit_auto_saves_without_batch_save_button(self):
        app = QApplication.instance() or QApplication([])
        self.db.cursor.execute(
            "INSERT INTO cost_library (spec_code, spec_name, cost_price, cost_calc_mode) VALUES ('AUTO-1', '旧名称', 1, 'total')"
        )
        self.db.cursor.executemany(
            "INSERT INTO cost_library (spec_code, spec_name, cost_price, cost_calc_mode) VALUES (?, ?, 1, 'total')",
            [(f"AUTO-{index:02d}", f"滚动测试商品{index:02d}") for index in range(2, 42)],
        )
        self.db.conn.commit()
        dialog = CostLibraryDialog(self.db)
        dialog.resize(760, 320)
        dialog.show()
        deadline = time.time() + 1.5
        while dialog.model.rowCount() == 0 and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        self.assertFalse(any(button.text() == "保存修改" for button in dialog.findChildren(QPushButton)))
        reloads = []
        dialog.load_data = lambda: reloads.append(True)
        scroll_bar = dialog.table_view.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum() // 2)
        scroll_before = scroll_bar.value()
        row = dialog._row_by_spec_code["AUTO-1"]
        dialog.model.item(row, dialog.COL_NAME).setText("新名称")
        deadline = time.time() + 1.2
        while time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        self.assertEqual(
            self.db.safe_fetchall("SELECT spec_name FROM cost_library WHERE spec_code='AUTO-1'")[0][0],
            "新名称",
        )
        self.assertEqual(reloads, [])
        self.assertEqual(scroll_bar.value(), scroll_before)
        dialog.close()
        app.processEvents()

    def test_cost_code_click_only_selects_and_ctrl_c_copies(self):
        app = QApplication.instance() or QApplication([])
        self.db.cursor.execute(
            "INSERT INTO cost_library (spec_code, spec_name, cost_price) VALUES ('COPY-1', '复制测试', 1)"
        )
        self.db.conn.commit()
        dialog = CostLibraryDialog(self.db)
        deadline = time.time() + 1.5
        while dialog.model.rowCount() == 0 and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)

        row = dialog._row_by_spec_code["COPY-1"]
        index = dialog.model.index(row, dialog.COL_CODE)
        dialog.table_view.setCurrentIndex(index)
        QApplication.clipboard().setText("未复制")
        dialog.handle_cost_table_click(index)
        self.assertEqual(QApplication.clipboard().text(), "未复制")

        copy_event = QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.ControlModifier)
        self.assertTrue(dialog.eventFilter(dialog.table_view, copy_event))
        self.assertEqual(QApplication.clipboard().text(), "COPY-1")
        dialog.close()
        app.processEvents()

    def test_cost_table_thumbnail_precedes_product_name(self):
        app = QApplication.instance() or QApplication([])
        self.db.cursor.execute(
            "INSERT INTO cost_library (spec_code, spec_name, cost_price) VALUES ('IMG-1', '图片商品', 1)"
        )
        self.db.conn.commit()
        image = QImage(12, 12, QImage.Format_RGB32)
        image.fill(0xFFFFFFFF)
        raw = QByteArray()
        buffer = QBuffer(raw)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        image_data = bytes(raw)
        self.assertTrue(self.db.set_cost_thumbnail("IMG-1", image_data))

        dialog = CostLibraryDialog(self.db)
        deadline = time.time() + 1.5
        while dialog.model.rowCount() == 0 and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        self.assertLess(dialog.COL_IMAGE, dialog.COL_NAME)
        self.assertEqual(dialog.model.headerData(dialog.COL_IMAGE, 1), "图片")
        item = dialog.model.item(0, dialog.COL_IMAGE)
        self.assertEqual(bytes(item.data(256)), image_data)
        self.assertFalse(item.icon().isNull())
        dialog.close()
        app.processEvents()

    def test_cost_thumbnail_viewer_loads_database_image_and_saves(self):
        app = QApplication.instance() or QApplication([])
        image = QImage(18, 12, QImage.Format_RGB32)
        image.fill(0xFF336699)
        raw = QByteArray()
        buffer = QBuffer(raw)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        image_data = bytes(raw)

        viewer = MaterialImageViewerDialog(
            image_data=image_data, window_title="成本库白底图"
        )
        app.processEvents()
        self.assertFalse(viewer.pixmap.isNull())
        self.assertEqual(viewer.windowTitle(), "成本库白底图")
        output = os.path.join(self.temp.name, "saved-thumbnail.png")
        self.assertEqual(
            CostLibraryDialog._write_thumbnail_file(image_data, output), output
        )
        self.assertFalse(QImage(output).isNull())
        viewer.close()
        viewer.deleteLater()
        app.processEvents()

    def test_cost_thumbnail_can_sync_to_local_material_folder(self):
        app = QApplication.instance() or QApplication([])
        self.db.ensure_cost_category("练习本")
        self.db.cursor.execute(
            """INSERT INTO cost_library
               (spec_code, spec_name, category_label, cost_price)
               VALUES ('LOCAL-IMG', '本地图片商品', '练习本', 1)"""
        )
        self.db.conn.commit()
        image = QImage(18, 12, QImage.Format_RGB32)
        image.fill(0xFF336699)
        raw = QByteArray()
        buffer = QBuffer(raw)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()

        dialog = MaterialLibraryDialog(self.db)
        material_root = os.path.join(self.temp.name, "materials")
        dialog.set_root_folder(material_root)
        saved_path = dialog.save_cost_thumbnail_to_product_material(
            "LOCAL-IMG", bytes(raw)
        )
        self.assertTrue(os.path.isfile(saved_path))
        self.assertTrue(dialog.is_white_background_image(saved_path))
        dialog.close()
        dialog.deleteLater()
        app.processEvents()

    def test_prefixed_product_white_background_image_is_detected(self):
        self.assertTrue(MaterialLibraryDialog.is_white_background_image("错题本/错题本【白底图】.png"))
        self.assertTrue(MaterialLibraryDialog.is_white_background_image("错题本/白底图.png"))
        self.assertFalse(MaterialLibraryDialog.is_white_background_image("错题本/错题本【详情图】.png"))

    def test_cost_table_seeds_an_empty_thumbnail_from_material_library(self):
        app = QApplication.instance() or QApplication([])
        self.db.cursor.execute(
            "INSERT INTO cost_library (spec_code, spec_name, cost_price) VALUES ('AUTO-IMG', '自动图片商品', 1)"
        )
        self.db.conn.commit()
        image_path = os.path.join(self.temp.name, "白底图.png")
        image = QImage(24, 24, QImage.Format_RGB32)
        image.fill(0xFF336699)
        self.assertTrue(image.save(image_path, "PNG"))

        class MaterialSource:
            def material_images_for_cost_specs(self, codes, white_only=False):
                return {"AUTO-IMG": image_path} if white_only and "AUTO-IMG" in codes else {}

        dialog = CostLibraryDialog(self.db, main_window=MaterialSource())
        deadline = time.time() + 2
        stored = None
        while time.time() < deadline:
            app.processEvents()
            rows = self.db.safe_fetchall(
                "SELECT thumbnail_data, thumbnail_manual FROM cost_library WHERE spec_code='AUTO-IMG'"
            )
            stored = rows[0] if rows else None
            if stored and stored[0]:
                break
            time.sleep(0.01)
        self.assertTrue(stored and stored[0])
        self.assertEqual(stored[1], 0)
        row = dialog._row_by_spec_code["AUTO-IMG"]
        self.assertFalse(dialog.model.item(row, dialog.COL_IMAGE).icon().isNull())
        dialog.close()
        app.processEvents()

    def test_late_member_syncs_first_and_any_member_can_relay_latest_data(self):
        app = QApplication.instance() or QApplication([])
        peers = []

        def make_peer(name, role, host="", stale=False):
            db = SafeDatabaseManager(os.path.join(self.temp.name, f"{name}.db"))
            if stale:
                db.cursor.execute(
                    "INSERT INTO cost_library (spec_code, spec_name, cost_price, cost_calc_mode) VALUES (?, ?, ?, ?)",
                    ("STALE-1", "加入前旧数据", 99.0, "total"),
                )
                db.conn.commit()
            db.configure_cost_sync("live-group", "文创", role, "k" * 32, host)
            db.set_setting("cost_sync_skip_initial_diff", "1" if role == "client" else "0")
            if stale:
                db.set_setting("cost_sync_pending_json", json.dumps({
                    "schema": 1,
                    "rows": [{"spec_code": "STALE-1", "_modified_at": 9999999999999}],
                    "categories": [],
                    "images": [],
                }))

            def provider(action, payload):
                if action == "state":
                    return db.get_cost_sync_state()
                if action == "local_snapshot":
                    return {"snapshot": db.build_cost_sync_snapshot()}
                if action == "merge_snapshots":
                    return {"snapshot": db.merge_cost_sync_snapshots(payload["current"], payload["incoming"])}
                if action == "load_pending":
                    try:
                        pending = json.loads(db.get_setting("cost_sync_pending_json", "") or "{}")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pending = {}
                    return {"snapshot": pending}
                if action == "save_pending":
                    db.set_setting("cost_sync_pending_json", json.dumps(payload.get("snapshot") or {}))
                    return {"ok": True}
                if action == "skip_initial_diff":
                    return {"skip": db.get_setting("cost_sync_skip_initial_diff", "0") == "1"}
                if action == "clear_skip_initial_diff":
                    db.set_setting("cost_sync_skip_initial_diff", "0")
                    return {"ok": True}
                if action == "clear_local_dirty":
                    db.set_setting("cost_sync_local_dirty", "0")
                    return {"ok": True}
                if action == "remember_host":
                    db.update_cost_sync_state(coordinator_host=payload.get("coordinator_host") or "")
                    return {"ok": True}
                if action == "snapshot":
                    state = db.get_cost_sync_state()
                    try:
                        snapshot = json.loads(state.get("snapshot_json") or "{}")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        snapshot = {}
                    return {
                        "revision": int(state.get("revision") or 0),
                        "snapshot": snapshot,
                        "snapshot_hash": state.get("snapshot_hash") or "",
                        "publisher_id": state.get("publisher_id") or "",
                        "published_at": state.get("published_at") or "",
                    }
                if action == "publish":
                    return db.publish_cost_sync_snapshot(payload.get("snapshot"), payload.get("publisher_id") or "")
                if action == "apply_remote":
                    return db.apply_remote_cost_sync_snapshot(
                        payload.get("snapshot"), payload.get("revision"), payload.get("snapshot_hash") or "",
                        payload.get("publisher_id") or "", payload.get("published_at") or "",
                        bool(payload.get("replace_local")),
                    )
                raise ValueError(action)

            service = CostSyncService(provider)
            service.POLL_SECONDS = 0.15
            service.start()
            peer = {"db": db, "service": service}
            peers.append(peer)
            return peer

        def wait_for(condition, timeout=8):
            deadline = time.time() + timeout
            while time.time() < deadline:
                app.processEvents()
                if condition():
                    return True
                time.sleep(0.02)
            return False

        try:
            a = make_peer("peer-a", "host")
            a["db"].cursor.execute(
                "INSERT INTO cost_library (spec_code, spec_name, cost_price, cost_calc_mode) VALUES (?, ?, ?, ?)",
                ("LIVE-1", "A电脑原始数据", 3.0, "total"),
            )
            a["db"].conn.commit()
            self.assertTrue(wait_for(lambda: bool(a["db"].get_cost_sync_state().get("snapshot_hash"))))

            a_host = f"127.0.0.1:{a['service'].httpd.server_port}"
            b = make_peer("peer-b", "client", a_host, stale=True)
            self.assertTrue(wait_for(lambda: b["db"].safe_fetchall(
                "SELECT spec_name FROM cost_library WHERE spec_code='LIVE-1'"
            ) == [("A电脑原始数据",)]))
            self.assertEqual(b["db"].safe_fetchall(
                "SELECT COUNT(*) FROM cost_library WHERE spec_code='STALE-1'"
            )[0][0], 0)
            self.assertEqual(a["db"].safe_fetchall("SELECT COUNT(*) FROM cost_library")[0][0], 1)
            self.assertTrue(wait_for(lambda: not json.loads(
                b["db"].get_setting("cost_sync_pending_json", "") or "{}"
            ).get("rows")))
            self.assertTrue(wait_for(lambda:
                a["db"].get_cost_sync_state().get("snapshot_hash")
                == b["db"].get_cost_sync_state().get("snapshot_hash")
            ))
            stable_revisions = (
                a["db"].get_cost_sync_state()["revision"],
                b["db"].get_cost_sync_state()["revision"],
            )
            settled_until = time.time() + 0.5
            while time.time() < settled_until:
                app.processEvents()
                time.sleep(0.02)
            self.assertEqual(stable_revisions, (
                a["db"].get_cost_sync_state()["revision"],
                b["db"].get_cost_sync_state()["revision"],
            ))

            b_host = f"127.0.0.1:{b['service'].httpd.server_port}"
            self.assertTrue(wait_for(lambda: b_host in a["service"]._cached_peer_hosts()))
            discoveries = []
            original_discover = a["service"].discover_all
            a["service"].discover_all = lambda *_args, **_kwargs: discoveries.append(True) or []
            self.assertIn(b_host, a["service"]._peer_hosts())
            self.assertEqual(discoveries, [])
            a["service"].discover_all = original_discover
            a["db"].cursor.execute("UPDATE cost_library SET spec_name='A直接推送' WHERE spec_code='LIVE-1'")
            a["db"].conn.commit()
            a["service"].notify_local_change()
            self.assertTrue(wait_for(lambda: b["db"].safe_fetchall(
                "SELECT spec_name FROM cost_library WHERE spec_code='LIVE-1'"
            ) == [("A直接推送",)]))
            self.assertTrue(wait_for(lambda: b["db"].safe_fetchall(
                """SELECT operation_type, new_value FROM cost_history
                   WHERE spec_code='LIVE-1' ORDER BY id DESC LIMIT 1"""
            ) == [("name", "A直接推送")]))

            b["db"].cursor.execute("UPDATE cost_library SET spec_name='B电脑最新修改' WHERE spec_code='LIVE-1'")
            b["db"].conn.commit()
            self.assertTrue(wait_for(lambda: a["db"].safe_fetchall(
                "SELECT spec_name FROM cost_library WHERE spec_code='LIVE-1'"
            ) == [("B电脑最新修改",)]))

            b["db"].set_cost_thumbnail("LIVE-1", b"live-thumbnail")
            b["db"].safe_execute(
                """UPDATE cost_library
                   SET product_attribute_is_combo=1, combo_reviewed=1
                   WHERE spec_code='LIVE-1'"""
            )
            b["db"].set_setting("cost_sync_local_dirty", "1")
            self.assertTrue(wait_for(lambda: a["db"].safe_fetchall(
                "SELECT thumbnail_data, combo_reviewed FROM cost_library WHERE spec_code='LIVE-1'"
            ) == [(b"live-thumbnail", 1)]))

            a["service"].stop()
            c = make_peer("peer-c", "client", b_host)
            self.assertTrue(wait_for(lambda: c["db"].safe_fetchall(
                "SELECT spec_name FROM cost_library WHERE spec_code='LIVE-1'"
            ) == [("B电脑最新修改",)]))
            self.assertEqual(c["db"].safe_fetchall(
                "SELECT thumbnail_data, combo_reviewed FROM cost_library WHERE spec_code='LIVE-1'"
            ), [(b"live-thumbnail", 1)])

            c["db"].cursor.execute("UPDATE cost_library SET spec_name='C电脑最新修改' WHERE spec_code='LIVE-1'")
            c["db"].conn.commit()
            self.assertTrue(wait_for(lambda: b["db"].safe_fetchall(
                "SELECT spec_name FROM cost_library WHERE spec_code='LIVE-1'"
            ) == [("C电脑最新修改",)]))

            a["db"].update_cost_sync_state(coordinator_host=b_host)
            a["service"].start()
            self.assertTrue(wait_for(lambda: a["db"].safe_fetchall(
                "SELECT spec_name FROM cost_library WHERE spec_code='LIVE-1'"
            ) == [("C电脑最新修改",)]))
        finally:
            for peer in reversed(peers):
                peer["service"].stop()
                peer["db"].close()


if __name__ == "__main__":
    unittest.main()

import base64
import os
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from PyQt5.QtWidgets import QApplication

from manager.dialogs.material_library import MaterialLibraryDialog
from manager.material_mobile_service import MaterialMobileService


class MaterialMobileServiceTest(unittest.TestCase):
    def test_identical_spec_names_with_different_codes_merge_once(self):
        QApplication.instance() or QApplication([])

        class FakeDb:
            @staticmethod
            def safe_fetchall(*_args):
                return [
                    ("A5直背本（空白款）", "A1", "属性一", None, 1),
                    ("A5直背本（空白款）", "A2", "属性一", None, 2),
                    ("A5直背本（空白款）", "A3", "属性二", None, 3),
                    ("A5直背本（空白款）", "A4", "属性二", None, 4),
                ]

        dialog = MaterialLibraryDialog.__new__(MaterialLibraryDialog)
        dialog.db = FakeDb()
        specs = dialog.get_specs_for_category("直背本")
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["name"], "A5直背本（空白款）")
        self.assertEqual(specs[0]["codes"], ["A1", "A2", "A3", "A4"])

    def test_lan_ip_ignores_meta_proxy_adapter(self):
        self.assertEqual(
            MaterialMobileService.select_lan_ip(["198.18.0.1", "192.168.1.118"]),
            "192.168.1.118",
        )
        self.assertEqual(
            MaterialMobileService.select_lan_ip([
                ("172.20.128.1", "vEthernet (WSL)"),
                ("192.168.31.100", "WLAN"),
            ]),
            "192.168.31.100",
        )

    def test_pair_catalog_upload_and_revoke(self):
        app = QApplication.instance() or QApplication([])
        external_folder = os.environ.get("SHOP_TEST_TMP", "")
        folder_context = nullcontext(external_folder) if external_folder else tempfile.TemporaryDirectory()
        with folder_context as folder:
            state = {"account_id": "account-a", "uploaded": []}

            def provider(action, payload):
                if action == "session":
                    return {"account_id": state["account_id"], "account_name": "测试账号"}
                if action == "catalog":
                    return {
                        "catalog": {"categories": [{"id": "cat", "label": "类型", "color": "#ffffff", "specs": [{"id": "spec", "name": "规格", "codes": ["1"]}]}]},
                        "targets": {"cat/spec": {"category_label": "类型", "spec_name": "规格", "codes": ["1"]}},
                    }
                if action == "target":
                    return {"folder": folder, "prefix": "测试规格"}
                if action == "uploaded":
                    state["uploaded"].append(payload["path"])
                    return {"ok": True}
                raise AssertionError(action)

            service = MaterialMobileService(provider, os.path.join(folder, "bindings.json"))
            service.set_active_account({"id": "account-a", "name": "测试账号"})
            pairing = service.create_pairing({"id": "account-a", "name": "测试账号"})
            query = parse_qs(urlparse(pairing["uri"]).query)
            result = {}

            def client():
                base = f"http://127.0.0.1:{service.httpd.server_port}"
                paired = requests.post(
                    base + "/api/v1/pair",
                    json={"pair_code": query["pair_code"][0], "device_id": "phone-1", "device_name": "测试手机"},
                    timeout=5,
                ).json()
                if "access_token" not in paired:
                    raise AssertionError(f"pair failed: {paired}")
                token = paired["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                result["catalog"] = requests.get(base + "/api/v1/catalog", headers=headers, timeout=5).json()
                original = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
                result["upload"] = requests.post(
                    base + "/api/v1/materials/cat/spec",
                    headers={**headers, "Content-Type": "image/png", "X-File-Extension": ".png"},
                    data=original,
                    timeout=5,
                ).json()
                result["original"] = original
                result["token"] = token
                result["images"] = requests.get(
                    base + "/api/v1/materials/cat/spec", headers=headers, timeout=5
                ).json()
                image_id = result["images"]["images"][0]["id"]
                result["thumbnail"] = requests.get(
                    base + f"/api/v1/materials/cat/spec/{image_id}?variant=thumbnail",
                    headers=headers,
                    timeout=5,
                )
                result["download"] = requests.get(
                    base + f"/api/v1/materials/cat/spec/{image_id}?variant=original",
                    headers=headers,
                    timeout=5,
                )
                state["account_id"] = "account-b"
                result["inactive"] = requests.get(base + "/api/v1/session", headers=headers, timeout=5).json()
                state["account_id"] = "account-a"
                result["restored"] = requests.get(base + "/api/v1/session", headers=headers, timeout=5).json()
                result["invalid"] = requests.post(
                    base + "/api/v1/materials/cat/spec",
                    headers={**headers, "Content-Type": "image/png", "X-File-Extension": ".png"},
                    data=b"not-an-image",
                    timeout=5,
                ).json()

            worker = threading.Thread(target=client)
            worker.start()
            deadline = time.time() + 10
            while worker.is_alive() and time.time() < deadline:
                app.processEvents()
                time.sleep(0.01)
            worker.join(1)
            try:
                self.assertFalse(worker.is_alive())
                self.assertTrue(result["catalog"]["ok"])
                self.assertTrue(result["upload"]["ok"])
                self.assertEqual(Path(state["uploaded"][0]).read_bytes(), result["original"])
                self.assertEqual(len(result["images"]["images"]), 1)
                self.assertEqual(result["thumbnail"].headers["Content-Type"], "image/jpeg")
                self.assertGreater(len(result["thumbnail"].content), 0)
                self.assertEqual(result["download"].content, result["original"])
                self.assertEqual(result["inactive"]["code"], "account_inactive")
                self.assertTrue(result["restored"]["ok"])
                self.assertFalse(result["invalid"]["ok"])
                self.assertEqual(len(state["uploaded"]), 1)
                self.assertTrue(service.revoke_device("account-a", "phone-1"))
                self.assertIsNone(service.authenticate(result["token"], "account-a"))
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()

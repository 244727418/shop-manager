import hashlib
import json
import os
import socket
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin

import requests
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


HTTP_PORT = 8765
UDP_PORT = 8766
DISCOVERY_MAGIC = "shop_manager_update_v1"
GLOBAL_UPDATE_SETTINGS_FILE = "update_settings.json"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def current_exe_path():
    return sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])


def global_update_settings_path():
    return os.path.join(app_dir(), GLOBAL_UPDATE_SETTINGS_FILE)


def load_global_update_settings():
    path = global_update_settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_global_update_setting(key, value):
    data = load_global_update_settings()
    data[key] = value
    with open(global_update_settings_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        sock.close()


def get_subnet_broadcast(ip):
    parts = str(ip or "").split(".")
    if len(parts) != 4:
        return ""
    try:
        nums = [int(part) for part in parts]
    except ValueError:
        return ""
    if any(num < 0 or num > 255 for num in nums):
        return ""
    return f"{nums[0]}.{nums[1]}.{nums[2]}.255"


def normalize_server_url(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    return value.rstrip("/")


def parse_version(value):
    parts = []
    for item in str(value or "").replace("_", ".").replace("-", ".").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return parts or [0]


def is_newer_version(remote, current):
    left = parse_version(remote)
    right = parse_version(current)
    size = max(len(left), len(right))
    left += [0] * (size - len(left))
    right += [0] * (size - len(right))
    return left > right


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(version, package_path, notes, host_ip=None, port=HTTP_PORT):
    filename = os.path.basename(package_path)
    base_url = f"http://{host_ip or get_lan_ip()}:{port}/"
    return {
        "type": DISCOVERY_MAGIC,
        "version": str(version).strip(),
        "filename": filename,
        "url": urljoin(base_url, filename),
        "sha256": file_sha256(package_path),
        "size": os.path.getsize(package_path),
        "notes": notes or "",
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_manifest(server_url, timeout=3):
    server_url = normalize_server_url(server_url)
    if not server_url:
        return None
    response = requests.get(urljoin(server_url + "/", "latest.json"), timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not data.get("version") or not data.get("url"):
        raise ValueError("更新信息格式不正确")
    return data


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


class UpdatePublishService:
    def __init__(self):
        self.httpd = None
        self.thread = None
        self.directory = None
        self.manifest = None
        self.broadcast_host = ""

    def start(self, directory, manifest, port=HTTP_PORT):
        self.stop()
        self.directory = directory
        self.manifest = manifest
        manifest_path = os.path.join(directory, "latest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        handler = partial(_QuietHandler, directory=directory)
        self.httpd = ThreadingHTTPServer(("", port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
        self.httpd = None
        self.thread = None

    def push(self):
        if not self.manifest:
            raise RuntimeError("请先开启更新服务")
        payload = json.dumps(self.manifest, ensure_ascii=False).encode("utf-8")
        self._broadcast(payload)

    def push_test_message(self):
        payload = {
            "type": DISCOVERY_MAGIC,
            "message_kind": "test",
            "message": "滴滴滴",
            "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._broadcast(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        return payload

    def _broadcast(self, payload):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            targets = {"255.255.255.255"}
            if self.broadcast_host:
                subnet_broadcast = get_subnet_broadcast(self.broadcast_host)
                if subnet_broadcast:
                    targets.add(subnet_broadcast)
            if self.manifest and self.manifest.get("url"):
                host = self.manifest["url"].split("/")[2].split(":")[0]
                subnet_broadcast = get_subnet_broadcast(host)
                if subnet_broadcast:
                    targets.add(subnet_broadcast)
            for target in targets:
                try:
                    sock.sendto(payload, (target, UDP_PORT))
                except Exception as e:
                    print(f"发送更新广播失败 {target}: {e}")
        finally:
            sock.close()


class UpdateBroadcastListener(QObject):
    updateReceived = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", UDP_PORT))
            while self._running:
                data, addr = sock.recvfrom(65535)
                try:
                    payload = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                if isinstance(payload, dict) and payload.get("type") == DISCOVERY_MAGIC:
                    payload["_sender_ip"] = addr[0] if addr else ""
                    self.updateReceived.emit(payload)
        except Exception as e:
            print(f"更新广播监听失败: {e}")
        finally:
            sock.close()


class UpdateDownloadWorker(QThread):
    progressChanged = pyqtSignal(int)
    finishedOk = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, manifest, target_dir, parent=None):
        super().__init__(parent)
        self.manifest = manifest
        self.target_dir = target_dir

    def run(self):
        try:
            url = self.manifest["url"]
            filename = self.manifest.get("filename") or os.path.basename(url.split("?")[0])
            target_path = os.path.join(self.target_dir, filename)
            temp_path = target_path + ".download"
            response = requests.get(url, stream=True, timeout=10)
            response.raise_for_status()
            total = int(response.headers.get("content-length") or self.manifest.get("size") or 0)
            done = 0
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        self.progressChanged.emit(min(99, int(done * 100 / total)))
            expected_hash = self.manifest.get("sha256")
            if expected_hash and file_sha256(temp_path).lower() != expected_hash.lower():
                os.remove(temp_path)
                raise ValueError("文件校验失败，请重新推送更新")
            if os.path.exists(target_path):
                os.remove(target_path)
            os.replace(temp_path, target_path)
            self.progressChanged.emit(100)
            self.finishedOk.emit(target_path)
        except Exception as e:
            self.failed.emit(str(e))


class UpdateAdminDialog(QDialog):
    def __init__(self, main_app, publish_service, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.db = main_app.db
        self.publish_service = publish_service
        self.package_path = ""
        self.setWindowTitle("管理员更新中心")
        self.resize(560, 360)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        settings = load_global_update_settings()

        self.version_input = QLineEdit(self.main_app.current_version)
        form.addRow("新版本号", self.version_input)

        self.host_ip_input = QLineEdit(settings.get("update_host_ip", "") or get_lan_ip())
        self.host_ip_input.setPlaceholderText("例如 192.168.1.118")
        form.addRow("主电脑IP", self.host_ip_input)

        package_row = QHBoxLayout()
        self.package_input = QLineEdit()
        self.package_input.setReadOnly(True)
        btn_choose = QPushButton("选择安装包")
        btn_choose.clicked.connect(self.choose_package)
        btn_current = QPushButton("使用当前程序")
        btn_current.clicked.connect(self.use_current_package)
        package_row.addWidget(self.package_input)
        package_row.addWidget(btn_choose)
        package_row.addWidget(btn_current)
        form.addRow("更新文件", package_row)

        self.url_label = QLabel(f"http://{self.host_ip_input.text().strip() or get_lan_ip()}:{HTTP_PORT}")
        form.addRow("本机更新地址", self.url_label)

        layout.addLayout(form)

        self.status_label = QLabel("先选择最新打包好的 exe，再开启服务。")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_start = QPushButton("开启主电脑服务")
        btn_start.clicked.connect(self.start_service)
        btn_push = QPushButton("推送更新")
        btn_push.clicked.connect(self.push_update)
        btn_test = QPushButton("测试广播")
        btn_test.clicked.connect(self.push_test_message)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_start)
        btn_row.addWidget(btn_push)
        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def choose_package(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择最新版本安装包", app_dir(), "程序文件 (*.exe);;所有文件 (*.*)")
        if path:
            self.package_path = path
            self.package_input.setText(path)

    def use_current_package(self):
        if not getattr(sys, "frozen", False):
            QMessageBox.warning(self, "当前不是打包程序", "源码运行时不能使用当前程序推送更新。请先打包成 exe，再打开 exe 后使用当前程序。")
            return
        path = current_exe_path()
        if not os.path.exists(path) or not path.lower().endswith(".exe"):
            QMessageBox.warning(self, "文件不存在", "没有找到当前 exe 程序文件。")
            return
        self.package_path = path
        self.package_input.setText(path)

    def start_service(self):
        if not self.package_path or not os.path.exists(self.package_path):
            QMessageBox.warning(self, "缺少文件", "请先选择最新打包好的安装包。")
            return
        version = self.version_input.text().strip()
        if not version:
            QMessageBox.warning(self, "缺少版本号", "请填写新版本号。")
            return
        try:
            host_ip = self.host_ip_input.text().strip() or get_lan_ip()
            self.publish_service.broadcast_host = host_ip
            manifest = build_manifest(version, self.package_path, "", host_ip=host_ip)
            self.publish_service.start(os.path.dirname(self.package_path), manifest)
            server_url = f"http://{host_ip}:{HTTP_PORT}"
            save_global_update_setting("update_host_ip", host_ip)
            save_global_update_setting("update_server_url", server_url)
            self.status_label.setText(f"更新服务已开启：{server_url}")
            self.url_label.setText(server_url)
            QMessageBox.information(self, "已开启", "主电脑更新服务已开启。其他电脑启动时可检查更新。")
        except OSError as e:
            QMessageBox.warning(self, "开启失败", f"端口 {HTTP_PORT} 被占用或被防火墙拦截：{e}")
        except Exception as e:
            QMessageBox.warning(self, "开启失败", str(e))

    def push_update(self):
        try:
            self.publish_service.push()
            self.status_label.setText("已向局域网推送更新通知。")
            QMessageBox.information(self, "已推送", "已广播更新通知。已打开软件的客户端会立即提示。")
        except Exception as e:
            QMessageBox.warning(self, "推送失败", str(e))

    def push_test_message(self):
        try:
            self.publish_service.broadcast_host = self.host_ip_input.text().strip() or get_lan_ip()
            save_global_update_setting("update_host_ip", self.publish_service.broadcast_host)
            payload = self.publish_service.push_test_message()
            self.status_label.setText(f"已发送测试广播：{payload['message']}")
            QMessageBox.information(self, "已发送", f"已发送测试广播：\n{payload['message']}")
        except Exception as e:
            QMessageBox.warning(self, "发送失败", str(e))


class UpdateSettingsDialog(QDialog):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.db = main_app.db
        self.setWindowTitle("更新设置")
        self.resize(480, 180)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        settings = load_global_update_settings()
        self.server_input = QLineEdit(settings.get("update_server_url", "") or "")
        self.admin_checkbox = QCheckBox("启用管理员更新模式")
        self.admin_checkbox.setChecked(str(settings.get("update_admin_mode", "0")) == "1")
        form.addRow("更新地址", self.server_input)
        form.addRow("", self.admin_checkbox)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_check = QPushButton("立即检查")
        btn_check.clicked.connect(self.check_now)
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_check)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def save(self):
        save_global_update_setting("update_server_url", normalize_server_url(self.server_input.text()))
        save_global_update_setting("update_admin_mode", "1" if self.admin_checkbox.isChecked() else "0")
        QMessageBox.information(self, "已保存", "更新设置已保存。")
        self.accept()

    def check_now(self):
        self.save()
        self.main_app.check_update_on_startup(show_no_update=True)

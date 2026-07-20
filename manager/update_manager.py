import ctypes
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
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
UPDATE_AGENT_UDP_PORT = 8767
DISCOVERY_MAGIC = "shop_manager_update_v1"
GLOBAL_UPDATE_SETTINGS_FILE = "update_settings.json"
UPDATE_CACHE_DIR_NAME = "更新助手"
UPDATE_PUBLISH_DIR_NAME = "更新发布"
PENDING_UPDATE_FILE = "pending_update.json"
UPDATE_AGENT_TASK_NAME = "ShopManagerUpdateAgent"
UPDATE_AGENT_INTERVAL_HOURS = 4
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

try:
    from manager.data_root import DataRootManager
except ImportError:
    try:
        from data_root import DataRootManager
    except ImportError:
        DataRootManager = None


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def current_exe_path():
    return sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])


def global_update_settings_path():
    if DataRootManager is not None:
        try:
            manager = DataRootManager()
            root = manager.get_data_root()
            if root:
                manager.ensure_structure(root)
                return manager.update_settings_path(root)
        except Exception:
            pass
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


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def save_global_update_settings(data):
    _write_json(global_update_settings_path(), data or {})


def save_global_update_setting(key, value):
    data = load_global_update_settings()
    data[key] = value
    save_global_update_settings(data)


def update_storage_dir(name):
    path = os.path.join(os.path.dirname(global_update_settings_path()), name)
    os.makedirs(path, exist_ok=True)
    return path


def update_cache_dir():
    path = os.path.join(app_dir(), UPDATE_CACHE_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def update_publish_dir():
    return update_storage_dir(UPDATE_PUBLISH_DIR_NAME)


def pending_update_path(cache_dir=None):
    return os.path.join(cache_dir or update_cache_dir(), PENDING_UPDATE_FILE)


def ensure_update_server_id():
    settings = load_global_update_settings()
    server_id = str(settings.get("update_server_id") or "").strip()
    if server_id:
        return server_id
    server_id = uuid.uuid4().hex
    settings["update_server_id"] = server_id
    save_global_update_settings(settings)
    return server_id


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
        "server_id": ensure_update_server_id(),
        "server_host": socket.gethostname(),
        "server_port": int(port),
        "version": str(version).strip(),
        "filename": filename,
        "url": urljoin(base_url, filename),
        "sha256": file_sha256(package_path),
        "size": os.path.getsize(package_path),
        "notes": notes or "",
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def manifest_server_url(manifest):
    update_url = str((manifest or {}).get("url") or "").strip()
    if "://" not in update_url:
        return ""
    return normalize_server_url("/".join(update_url.split("/")[:3]))


def bind_trusted_update_source(manifest):
    server_id = str((manifest or {}).get("server_id") or "").strip()
    server_url = manifest_server_url(manifest)
    if not server_id or not server_url:
        raise ValueError("更新来源缺少可信主机标识或下载地址")
    settings = load_global_update_settings()
    settings.update({
        "trusted_update_server_id": server_id,
        "trusted_update_server_url": server_url,
        "trusted_update_server_host": str(manifest.get("server_host") or "").strip(),
        "trusted_update_server_port": int(manifest.get("server_port") or HTTP_PORT),
        "auto_update_enabled": "0",
    })
    save_global_update_settings(settings)
    return settings


def is_trusted_update_manifest(manifest, settings=None):
    trusted_id = str((settings or load_global_update_settings()).get("trusted_update_server_id") or "").strip()
    server_id = str((manifest or {}).get("server_id") or "").strip()
    return bool(trusted_id and server_id and trusted_id == server_id)


def trusted_server_urls(settings=None):
    settings = settings or load_global_update_settings()
    urls = []
    host = str(settings.get("trusted_update_server_host") or "").strip()
    port = int(settings.get("trusted_update_server_port") or HTTP_PORT)
    if host:
        urls.append(normalize_server_url(f"http://{host}:{port}"))
    saved_url = normalize_server_url(settings.get("trusted_update_server_url") or "")
    if saved_url and saved_url not in urls:
        urls.append(saved_url)
    return urls


def fetch_trusted_manifest(settings=None, timeout=4):
    settings = settings or load_global_update_settings()
    errors = []
    for server_url in trusted_server_urls(settings):
        try:
            manifest = fetch_manifest(server_url, timeout=timeout)
            if not is_trusted_update_manifest(manifest, settings):
                raise ValueError("更新主机身份与首次绑定记录不一致")
            filename = os.path.basename(str(manifest.get("filename") or ""))
            if filename:
                manifest = dict(manifest)
                manifest["url"] = urljoin(server_url + "/", filename)
            return manifest
        except Exception as e:
            errors.append(str(e))
    if errors:
        raise RuntimeError("；".join(errors))
    return None


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


def _safe_update_filename(manifest):
    filename = os.path.basename(str((manifest or {}).get("filename") or ""))
    if not filename:
        filename = os.path.basename(str((manifest or {}).get("url") or "").split("?")[0])
    if not filename or filename in (".", "..") or not filename.lower().endswith(".exe"):
        raise ValueError("更新文件名无效，只允许 EXE 安装包")
    return filename


def download_update_file(manifest, target_dir, progress_callback=None, require_hash=False):
    url = str((manifest or {}).get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("更新下载地址无效")
    expected_hash = str(manifest.get("sha256") or "").strip().lower()
    if require_hash and not expected_hash:
        raise ValueError("自动更新必须包含 SHA256 校验值")

    os.makedirs(target_dir, exist_ok=True)
    filename = _safe_update_filename(manifest)
    target_path = os.path.join(target_dir, filename)
    temp_path = f"{target_path}.{os.getpid()}.download"
    response = None
    try:
        response = requests.get(url, stream=True, timeout=(5, 60))
        response.raise_for_status()
        total = int(response.headers.get("content-length") or manifest.get("size") or 0)
        done = 0
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total and progress_callback:
                    progress_callback(min(99, int(done * 100 / total)))
        if total and done != total:
            raise ValueError(f"更新文件大小不一致：应为 {total}，实际 {done}")
        if expected_hash and file_sha256(temp_path).lower() != expected_hash:
            raise ValueError("文件校验失败，请重新推送更新")
        os.replace(temp_path, target_path)
        if progress_callback:
            progress_callback(100)
        return target_path
    finally:
        try:
            response.close()
        except Exception:
            pass
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def save_pending_update(manifest, cached_path, cache_dir=None):
    data = {key: value for key, value in (manifest or {}).items() if not str(key).startswith("_")}
    data["cached_path"] = os.path.abspath(cached_path)
    data["cached_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_json(pending_update_path(cache_dir), data)
    return data


def load_pending_update(current_version, cache_dir=None, verify_hash=True):
    cache_dir = os.path.abspath(cache_dir or update_cache_dir())
    path = pending_update_path(cache_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if not isinstance(manifest, dict):
            return None
        if not is_newer_version(manifest.get("version"), current_version):
            return None
        cached_path = os.path.abspath(str(manifest.get("cached_path") or ""))
        if os.path.commonpath([cache_dir, cached_path]) != cache_dir or not os.path.isfile(cached_path):
            return None
        expected_hash = str(manifest.get("sha256") or "").strip().lower()
        if not expected_hash or (verify_hash and file_sha256(cached_path).lower() != expected_hash):
            return None
        manifest["_cached_path"] = cached_path
        return manifest
    except Exception:
        return None


def cache_update_package(manifest, cache_dir=None, progress_callback=None):
    cache_dir = cache_dir or update_cache_dir()
    cached_path = download_update_file(
        manifest,
        cache_dir,
        progress_callback=progress_callback,
        require_hash=True,
    )
    save_pending_update(manifest, cached_path, cache_dir)
    return cached_path


def stage_publish_package(package_path):
    if not os.path.isfile(package_path):
        raise FileNotFoundError(package_path)
    filename = os.path.basename(package_path)
    if not filename.lower().endswith(".exe"):
        raise ValueError("只能发布 EXE 安装包")
    directory = update_publish_dir()
    target_path = os.path.join(directory, filename)
    temp_path = target_path + ".staging"
    shutil.copy2(package_path, temp_path)
    os.replace(temp_path, target_path)
    return target_path


def save_published_update(manifest):
    directory = update_publish_dir()
    _write_json(os.path.join(directory, "latest.json"), manifest)
    settings = load_global_update_settings()
    settings["update_publish_enabled"] = "1"
    settings["published_update_manifest"] = manifest
    save_global_update_settings(settings)


def find_newer_local_package(current_version, directory=None):
    directory = directory or app_dir()
    candidates = []
    try:
        names = os.listdir(directory)
    except OSError:
        return None
    for name in names:
        if not name.lower().endswith(".exe"):
            continue
        match = re.search(r"(?i)(?:shop[_ -]?manager|店铺管理).*?v(\d+(?:\.\d+)*)", name)
        if not match or not is_newer_version(match.group(1), current_version):
            continue
        candidates.append((parse_version(match.group(1)), match.group(1), os.path.join(directory, name)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    version, version_text, path = candidates[0]
    return {"version": version_text, "filename": os.path.basename(path), "_local_path": path}


def update_agent_command():
    executable = sys.executable
    args = []
    if getattr(sys, "frozen", False):
        args.append(executable)
    else:
        if sys.platform == "win32":
            pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
            if os.path.isfile(pythonw):
                executable = pythonw
        args.extend([executable, os.path.join(app_dir(), "manager", "shop_manager.py")])
    args.append("--update-agent")
    return subprocess.list2cmdline(args)


def install_update_agent_task(run_now=True):
    if sys.platform != "win32":
        return False, "仅 Windows 支持后台更新计划任务"
    schtasks = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "schtasks.exe")
    command = update_agent_command()
    result = subprocess.run(
        [
            schtasks, "/Create", "/F",
            "/SC", "HOURLY", "/MO", str(UPDATE_AGENT_INTERVAL_HOURS),
            "/TN", UPDATE_AGENT_TASK_NAME,
            "/TR", command,
            "/RL", "LIMITED",
        ],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "创建计划任务失败").strip()
    if run_now:
        start_update_agent_task()
    return True, ""


def start_update_agent_task():
    if sys.platform != "win32":
        return False
    schtasks = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "schtasks.exe")
    result = subprocess.run(
        [schtasks, "/Run", "/TN", UPDATE_AGENT_TASK_NAME],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def uninstall_update_agent_task():
    if sys.platform != "win32":
        return True
    schtasks = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "schtasks.exe")
    subprocess.run(
        [schtasks, "/End", "/TN", UPDATE_AGENT_TASK_NAME],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    result = subprocess.run(
        [schtasks, "/Delete", "/F", "/TN", UPDATE_AGENT_TASK_NAME],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return result.returncode == 0 or b"cannot find" in result.stderr.lower()


def notify_update_agent(manifest):
    if not isinstance(manifest, dict):
        return False
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        payload = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        sock.sendto(payload, ("127.0.0.1", UPDATE_AGENT_UDP_PORT))
        return True
    except OSError:
        return False
    finally:
        sock.close()


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
        _write_json(manifest_path, manifest)
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

    def _broadcast(self, payload, ports=(UDP_PORT,)):
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
                for port in ports:
                    try:
                        sock.sendto(payload, (target, port))
                    except Exception as e:
                        print(f"发送更新广播失败 {target}:{port}: {e}")
        finally:
            sock.close()


def run_update_agent(current_version, stop_event=None):
    settings = load_global_update_settings()
    if str(settings.get("update_publish_enabled", "0")) == "1":
        manifest = settings.get("published_update_manifest")
        directory = update_publish_dir()
        package = os.path.join(directory, _safe_update_filename(manifest or {})) if manifest else ""
        if isinstance(manifest, dict) and os.path.isfile(package):
            service = UpdatePublishService()
            try:
                service.start(directory, manifest)
            except OSError:
                return 0
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                pass
            finally:
                service.stop()
            return 0

    if str(settings.get("auto_update_enabled", "0")) != "1":
        return 0
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(),
                0x40,
            )
        except Exception:
            pass
    def check_and_cache(manifest=None):
        error = ""
        try:
            current_settings = load_global_update_settings()
            pushed = manifest is not None
            manifest = manifest or fetch_trusted_manifest(current_settings)
            if manifest and not is_trusted_update_manifest(manifest, current_settings):
                raise ValueError("更新来源与首次绑定的主电脑不一致")
            if manifest and is_newer_version(manifest.get("version"), current_version):
                pending = load_pending_update(current_version, verify_hash=not pushed)
                pending_version = str((pending or {}).get("version") or "")
                if not pending or is_newer_version(manifest.get("version"), pending_version):
                    cache_update_package(manifest)
        except Exception as e:
            error = str(e)
        latest = load_global_update_settings()
        latest["auto_update_last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
        latest["auto_update_last_error"] = error
        save_global_update_settings(latest)
        return not error

    check_and_cache()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", UPDATE_AGENT_UDP_PORT))
        sock.settimeout(1)
    except OSError:
        sock.close()
        return 0
    next_check = time.monotonic() + UPDATE_AGENT_INTERVAL_HOURS * 3600
    try:
        while stop_event is None or not stop_event.is_set():
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                if time.monotonic() >= next_check:
                    check_and_cache()
                    next_check = time.monotonic() + UPDATE_AGENT_INTERVAL_HOURS * 3600
                continue
            try:
                manifest = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(manifest, dict) or manifest.get("type") != DISCOVERY_MAGIC:
                continue
            if manifest.get("message_kind") == "test":
                continue
            filename = os.path.basename(str(manifest.get("filename") or ""))
            if addr and filename:
                port = int(manifest.get("server_port") or HTTP_PORT)
                manifest["url"] = urljoin(f"http://{addr[0]}:{port}/", filename)
            check_and_cache(manifest)
    finally:
        sock.close()
    return 0


class UpdateBroadcastListener(QObject):
    updateReceived = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread = None
        self._sock = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock = sock
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
            self._sock = None
            sock.close()

    def stop(self):
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        self._thread = None


class UpdateDownloadWorker(QThread):
    progressChanged = pyqtSignal(int)
    finishedOk = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, manifest, target_dir, parent=None, record_pending=False):
        super().__init__(parent)
        self.manifest = manifest
        self.target_dir = target_dir
        self.record_pending = bool(record_pending)

    def run(self):
        try:
            if self.record_pending:
                target_path = cache_update_package(
                    self.manifest,
                    self.target_dir,
                    progress_callback=self.progressChanged.emit,
                )
            else:
                target_path = download_update_file(
                    self.manifest,
                    self.target_dir,
                    progress_callback=self.progressChanged.emit,
                )
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
            published_package = stage_publish_package(self.package_path)
            self.publish_service.broadcast_host = host_ip
            manifest = build_manifest(version, published_package, "", host_ip=host_ip)
            save_published_update(manifest)
            background_serving = False
            try:
                self.publish_service.start(update_publish_dir(), manifest)
            except OSError as e:
                if getattr(e, "winerror", None) != 10048 and getattr(e, "errno", None) != 98:
                    raise
                self.publish_service.directory = update_publish_dir()
                self.publish_service.manifest = manifest
                background_serving = True
            server_url = f"http://{host_ip}:{HTTP_PORT}"
            save_global_update_setting("update_host_ip", host_ip)
            save_global_update_setting("update_server_url", server_url)
            task_ok, task_error = install_update_agent_task(run_now=not background_serving)
            if not task_ok:
                raise RuntimeError(f"后台更新助手安装失败：{task_error}")
            state = "后台服务已更新" if background_serving else "更新服务已开启"
            self.status_label.setText(f"{state}：{server_url}")
            self.url_label.setText(server_url)
            self.main_app.show_toast(f"{state}，关闭主程序后仍可下载", 1600)
        except OSError as e:
            QMessageBox.warning(self, "开启失败", f"端口 {HTTP_PORT} 被占用或被防火墙拦截：{e}")
        except Exception as e:
            QMessageBox.warning(self, "开启失败", str(e))

    def push_update(self):
        try:
            self.publish_service.push()
            self.status_label.setText("已向局域网推送更新通知。")
            self.main_app.show_toast("已发送更新推送", 1000)
        except Exception as e:
            QMessageBox.warning(self, "推送失败", str(e))

    def push_test_message(self):
        try:
            self.publish_service.broadcast_host = self.host_ip_input.text().strip() or get_lan_ip()
            save_global_update_setting("update_host_ip", self.publish_service.broadcast_host)
            payload = self.publish_service.push_test_message()
            self.status_label.setText(f"已发送测试广播：{payload['message']}")
            self.main_app.show_toast(f"已发送测试广播：{payload['message']}", 1000)
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

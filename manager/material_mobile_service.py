# -*- coding: utf-8 -*-
"""LAN service and pairing UI for the Android material uploader."""
import hashlib
import hmac
import ipaddress
import io
import json
import os
import re
import secrets
import socket
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import qrcode
import psutil
from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class MaterialMobileService(QObject):
    context_requested = pyqtSignal(object)
    DISCOVERY_PORT = 48761
    HTTP_PORTS = range(48762, 48773)
    MAX_IMAGE_BYTES = 300 * 1024 * 1024
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
    MIME_EXTENSIONS = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/gif": ".gif",
    }

    def __init__(self, context_provider, config_path=None, parent=None):
        super().__init__(parent)
        self.context_provider = context_provider
        self.config_path = config_path or self.default_config_path()
        self.lock = threading.RLock()
        self.upload_lock = threading.Lock()
        self.config = self.load_config()
        self.desktop_id = self.config.setdefault("desktop_id", str(uuid.uuid4()))
        self.config.setdefault("enabled", False)
        self.config.setdefault("devices", [])
        self.active_account = {}
        self.pair_codes = {}
        self.catalog_targets = {}
        self.image_targets = {}
        self.thumbnail_cache = OrderedDict()
        self.thumbnail_lock = threading.Lock()
        self.httpd = None
        self.http_thread = None
        self.discovery_socket = None
        self.discovery_thread = None
        self.running = False
        self.context_requested.connect(self._resolve_context_request, Qt.QueuedConnection)
        self.save_config()

    @staticmethod
    def default_config_path():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ShopManager", "material_mobile_bindings.json")

    @classmethod
    def is_enabled(cls, config_path=None):
        path = config_path or cls.default_config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return bool(json.load(fh).get("enabled"))
        except Exception:
            return False

    def load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        temp_path = self.config_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as fh:
            json.dump(self.config, fh, ensure_ascii=False, indent=2)
        os.replace(temp_path, self.config_path)

    def _resolve_context_request(self, request):
        try:
            request["result"] = self.context_provider(request["action"], request.get("payload") or {})
        except Exception as exc:
            request["error"] = str(exc)
        finally:
            request["event"].set()

    def request_context(self, action, **payload):
        if QThread.currentThread() == self.thread():
            return self.context_provider(action, payload)
        request = {"action": action, "payload": payload, "event": threading.Event()}
        self.context_requested.emit(request)
        if not request["event"].wait(15):
            raise RuntimeError("电脑端响应超时")
        if request.get("error"):
            raise RuntimeError(request["error"])
        return request.get("result") or {}

    def set_active_account(self, account):
        account = account or {}
        current_id = str(account.get("id") or "")
        with self.lock:
            if current_id != str(self.active_account.get("id") or ""):
                self.catalog_targets.clear()
                self.image_targets.clear()
            self.active_account = {
                "id": current_id,
                "name": str(account.get("name") or "未绑定账号"),
            }

    def start(self):
        if self.running:
            return self.httpd.server_port
        service = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def send_json(self, status, payload):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def read_json(self, limit=16384):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > limit:
                    raise ValueError("请求内容无效")
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def bearer_token(self):
                value = self.headers.get("Authorization", "")
                return value[7:].strip() if value.startswith("Bearer ") else ""

            def authenticated(self):
                session = service.request_context("session")
                service.set_active_account({"id": session.get("account_id"), "name": session.get("account_name")})
                device = service.authenticate(self.bearer_token())
                if not device:
                    self.send_json(401, {"ok": False, "code": "unauthorized", "message": "绑定已失效，请重新扫码"})
                    return None, None
                if str(device.get("account_id") or "") != str(session.get("account_id") or ""):
                    self.send_json(409, {"ok": False, "code": "account_inactive", "message": "电脑当前打开的是另一个账号"})
                    return None, None
                return session, device

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                try:
                    if path == "/api/v1/session":
                        session, device = self.authenticated()
                        if not device:
                            return
                        self.send_json(200, {
                            "ok": True,
                            "desktop_id": service.desktop_id,
                            "desktop_name": socket.gethostname(),
                            "account_id": session.get("account_id"),
                            "account_name": session.get("account_name"),
                            "device_id": device.get("device_id"),
                        })
                        return
                    if path == "/api/v1/catalog":
                        session, device = self.authenticated()
                        if not device:
                            return
                        result = service.request_context("catalog")
                        with service.lock:
                            service.catalog_targets[str(session.get("account_id") or "")] = result.get("targets") or {}
                        service.touch_device(device)
                        self.send_json(200, {"ok": True, **(result.get("catalog") or {})})
                        return
                    image_match = re.fullmatch(r"/api/v1/materials/([^/]+)/([^/]+)/([a-f0-9]{24})", path)
                    list_match = re.fullmatch(r"/api/v1/materials/([^/]+)/([^/]+)", path)
                    if image_match or list_match:
                        session, device = self.authenticated()
                        if not device:
                            return
                        match = image_match or list_match
                        target_key = f"{unquote(match.group(1))}/{unquote(match.group(2))}"
                        target_meta = service.catalog_target(session.get("account_id"), target_key)
                        if not target_meta:
                            self.send_json(409, {"ok": False, "code": "refresh_catalog", "message": "分类已更新，请返回后重新选择规格"})
                            return
                        target = service.request_context("target", target=target_meta)
                        if list_match:
                            images = service.list_material_images(session.get("account_id"), target_key, target)
                            service.touch_device(device)
                            self.send_json(200, {"ok": True, "images": images})
                            return
                        image = service.image_target(
                            session.get("account_id"), target_key, image_match.group(3), target
                        )
                        if not image:
                            self.send_json(404, {"ok": False, "code": "image_missing", "message": "图片不存在或已更新"})
                            return
                        variant = (parse_qs(parsed.query).get("variant") or ["thumbnail"])[0]
                        service.send_material_image(self, image, original=variant == "original")
                        service.touch_device(device)
                        return
                    self.send_json(404, {"ok": False, "message": "接口不存在"})
                except Exception as exc:
                    self.send_json(500, {"ok": False, "message": str(exc)})

            def do_POST(self):
                path = urlparse(self.path).path
                try:
                    if path == "/api/v1/pair":
                        data = self.read_json()
                        session = service.request_context("session")
                        result = service.complete_pairing(data, session)
                        self.send_json(200, {"ok": True, **result})
                        return
                    match = re.fullmatch(r"/api/v1/materials/([^/]+)/([^/]+)", path)
                    if match:
                        session, device = self.authenticated()
                        if not device:
                            return
                        account_id = str(session.get("account_id") or "")
                        key = f"{unquote(match.group(1))}/{unquote(match.group(2))}"
                        with service.lock:
                            target_meta = (service.catalog_targets.get(account_id) or {}).get(key)
                        if not target_meta:
                            self.send_json(409, {"ok": False, "code": "refresh_catalog", "message": "分类已更新，请返回后重新选择规格"})
                            return
                        target = service.request_context("target", target=target_meta)
                        saved_path = service.receive_image(self, target)
                        service.touch_device(device)
                        service.request_context("uploaded", path=saved_path)
                        self.send_json(200, {"ok": True, "filename": os.path.basename(saved_path)})
                        return
                    self.send_json(404, {"ok": False, "message": "接口不存在"})
                except PermissionError as exc:
                    self.send_json(409, {"ok": False, "code": "account_inactive", "message": str(exc)})
                except ValueError as exc:
                    self.send_json(400, {"ok": False, "message": str(exc)})
                except Exception as exc:
                    self.send_json(500, {"ok": False, "message": str(exc)})

            def log_message(self, _format, *_args):
                pass

        for port in self.HTTP_PORTS:
            try:
                self.httpd = ExclusiveThreadingHTTPServer(("0.0.0.0", port), Handler)
                break
            except OSError:
                continue
        if self.httpd is None:
            self.httpd = ExclusiveThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.httpd.daemon_threads = True
        self.running = True
        self.http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.http_thread.start()
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()
        return self.httpd.server_port

    def stop(self):
        self.running = False
        if self.discovery_socket:
            try:
                self.discovery_socket.close()
            except OSError:
                pass
            self.discovery_socket = None
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    @classmethod
    def local_ips(cls):
        candidates = []
        try:
            stats = psutil.net_if_stats()
            for interface, addresses in psutil.net_if_addrs().items():
                if interface in stats and not stats[interface].isup:
                    continue
                for address in addresses:
                    if address.family == socket.AF_INET:
                        candidates.append((address.address, interface))
        except Exception:
            pass
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                candidates.append((sock.getsockname()[0], ""))
        except OSError:
            pass
        try:
            candidates.extend(
                (info[4][0], "") for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            )
        except OSError:
            pass
        return cls.rank_lan_ips(candidates)

    @classmethod
    def local_ip(cls):
        return next(iter(cls.local_ips()), "")

    @staticmethod
    def rank_lan_ips(candidates):
        virtual_names = (
            "vpn", "tun", "tap", "meta", "clash", "warp", "wsl", "vethernet",
            "hyper-v", "vmware", "virtualbox", "vbox", "docker", "tailscale",
            "zerotier", "loopback", "蓝牙",
        )
        physical_names = ("ethernet", "wi-fi", "wifi", "wlan", "以太网", "无线")
        proxy_network = ipaddress.ip_network("198.18.0.0/15")
        ranked = {}
        for candidate in candidates:
            if isinstance(candidate, (tuple, list)):
                value = candidate[0] if candidate else ""
                interface = str(candidate[1] if len(candidate) > 1 else "").casefold()
            else:
                value, interface = candidate, ""
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                continue
            if (
                address.version != 4 or address.is_loopback or address.is_link_local or
                address in proxy_network or any(token in interface for token in virtual_names)
            ):
                continue
            score = 10 if interface else 0
            if address in ipaddress.ip_network("192.168.0.0/16"):
                score += 140
            elif address in ipaddress.ip_network("10.0.0.0/8"):
                score += 120
            elif address in ipaddress.ip_network("172.16.0.0/12"):
                score += 100
            if any(token in interface for token in physical_names):
                score += 200
            ranked[str(address)] = max(score, ranked.get(str(address), -1))
        return [address for address, _score in sorted(ranked.items(), key=lambda item: -item[1])]

    @staticmethod
    def select_lan_ip(candidates):
        return next(iter(MaterialMobileService.rank_lan_ips(candidates)), "")

    def create_pairing(self, account):
        account_id = str((account or {}).get("id") or "")
        if not account_id:
            raise RuntimeError("当前数据还没有绑定软件账号")
        self.set_active_account(account)
        port = self.start()
        hosts = self.local_ips()
        if not hosts:
            raise RuntimeError("没有检测到局域网地址")
        host = hosts[0]
        pair_code = secrets.token_urlsafe(24)
        with self.lock:
            self.pair_codes[pair_code] = {"account_id": account_id, "expires": time.time() + 300}
            self.config["enabled"] = True
            self.save_config()
        uri = (
            "shopmaterial://pair?v=1"
            f"&host={host}&port={port}&desktop_id={self.desktop_id}"
            f"&account_id={account_id}&pair_code={pair_code}&hosts={','.join(hosts)}"
        )
        return {"uri": uri, "expires": time.time() + 300, "host": host, "hosts": hosts, "port": port}

    def complete_pairing(self, data, session):
        pair_code = str(data.get("pair_code") or "")
        device_id = str(data.get("device_id") or "").strip()[:128]
        device_name = str(data.get("device_name") or "Android 手机").strip()[:80]
        account_id = str(session.get("account_id") or "")
        with self.lock:
            pending = self.pair_codes.get(pair_code)
            if not pending or pending["expires"] < time.time():
                self.pair_codes.pop(pair_code, None)
                raise ValueError("配对二维码已过期，请在电脑上刷新")
            if pending["account_id"] != account_id:
                raise PermissionError("电脑当前账号已切换，请重新扫码")
            if not device_id:
                raise ValueError("手机设备标识无效")
            self.pair_codes.pop(pair_code, None)
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            devices = self.config.setdefault("devices", [])
            devices[:] = [
                item for item in devices
                if not (item.get("account_id") == account_id and item.get("device_id") == device_id)
            ]
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            devices.append({
                "account_id": account_id,
                "account_name": str(session.get("account_name") or ""),
                "device_id": device_id,
                "device_name": device_name,
                "token_hash": token_hash,
                "created_at": now,
                "last_seen": now,
            })
            self.save_config()
        return {
            "access_token": token,
            "desktop_id": self.desktop_id,
            "desktop_name": socket.gethostname(),
            "account_id": account_id,
            "account_name": str(session.get("account_name") or ""),
            "discovery_port": self.DISCOVERY_PORT,
            "http_port": self.httpd.server_port,
        }

    def authenticate(self, token, account_id=None):
        if not token:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self.lock:
            return next(
                (
                    item for item in self.config.get("devices", [])
                    if (account_id is None or item.get("account_id") == account_id)
                    and hmac.compare_digest(str(item.get("token_hash") or ""), digest)
                ),
                None,
            )

    def touch_device(self, device):
        with self.lock:
            device["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.save_config()

    def devices_for_account(self, account_id):
        with self.lock:
            return [
                dict(item) for item in self.config.get("devices", [])
                if item.get("account_id") == str(account_id or "")
            ]

    def revoke_device(self, account_id, device_id):
        with self.lock:
            devices = self.config.get("devices", [])
            before = len(devices)
            devices[:] = [
                item for item in devices
                if not (item.get("account_id") == account_id and item.get("device_id") == device_id)
            ]
            if len(devices) != before:
                self.save_config()
                return True
        return False

    def catalog_target(self, account_id, target_key):
        with self.lock:
            return (self.catalog_targets.get(str(account_id or "")) or {}).get(target_key)

    def list_material_images(self, account_id, target_key, target):
        folder = os.path.abspath(str((target or {}).get("folder") or ""))
        if not folder or not os.path.isdir(folder):
            return []
        rows = []
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return []
        for entry in entries:
            if not entry.is_file() or os.path.splitext(entry.name)[1].lower() not in self.IMAGE_EXTENSIONS:
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            image_id = hashlib.sha256(
                f"{self.desktop_id}\0{account_id}\0{target_key}\0{entry.name}\0{stat.st_mtime_ns}\0{stat.st_size}".encode("utf-8")
            ).hexdigest()[:24]
            rows.append({
                "id": image_id,
                "name": entry.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime_ns,
                "path": entry.path,
                "folder": folder,
            })
        rows.sort(key=lambda item: (-item["mtime"], item["name"].casefold()))
        with self.lock:
            account_images = self.image_targets.setdefault(str(account_id or ""), {})
            for row in rows:
                account_images[(target_key, row["id"])] = row
        return [{"id": row["id"], "name": row["name"], "size": row["size"]} for row in rows]

    def image_target(self, account_id, target_key, image_id, target):
        folder = os.path.abspath(str((target or {}).get("folder") or ""))
        with self.lock:
            image = (self.image_targets.get(str(account_id or "")) or {}).get((target_key, image_id))
        if not image or image.get("folder") != folder:
            return None
        path = os.path.abspath(str(image.get("path") or ""))
        try:
            if os.path.commonpath([folder, path]) != folder or not os.path.isfile(path):
                return None
        except ValueError:
            return None
        return image

    def send_material_image(self, handler, image, original=False):
        path = image["path"]
        ext = os.path.splitext(path)[1].lower()
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
        }.get(ext, "application/octet-stream")
        if original:
            size = os.path.getsize(path)
            handler.send_response(200)
            handler.send_header("Content-Type", mime)
            handler.send_header("Content-Length", str(size))
            handler.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(os.path.basename(path))}")
            handler.send_header("Cache-Control", "private, max-age=86400")
            handler.end_headers()
            with open(path, "rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
            return
        data = self.thumbnail_bytes(path)
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "private, max-age=86400")
        handler.end_headers()
        handler.wfile.write(data)

    def thumbnail_bytes(self, path):
        stat = os.stat(path)
        key = (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)
        with self.thumbnail_lock:
            cached = self.thumbnail_cache.get(key)
            if cached is not None:
                self.thumbnail_cache.move_to_end(key)
                return cached
            from PIL import Image, ImageOps
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((420, 420), Image.Resampling.LANCZOS)
                if image.mode in {"RGBA", "LA"}:
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=82, optimize=True)
                data = output.getvalue()
            self.thumbnail_cache[key] = data
            self.thumbnail_cache.move_to_end(key)
            while len(self.thumbnail_cache) > 256:
                self.thumbnail_cache.popitem(last=False)
            return data

    def _discovery_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.DISCOVERY_PORT))
            sock.settimeout(1)
            self.discovery_socket = sock
        except OSError:
            return
        while self.running:
            try:
                payload, address = sock.recvfrom(4096)
                request = json.loads(payload.decode("utf-8"))
                if request.get("protocol") != "shop-material-v1":
                    continue
                if request.get("desktop_id") != self.desktop_id:
                    continue
                account_id = str(request.get("account_id") or "")
                device_id = str(request.get("device_id") or "")
                if not any(
                    item.get("account_id") == account_id and item.get("device_id") == device_id
                    for item in self.config.get("devices", [])
                ):
                    continue
                active = dict(self.active_account)
                response = {
                    "protocol": "shop-material-v1",
                    "desktop_id": self.desktop_id,
                    "desktop_name": socket.gethostname(),
                    "account_id": account_id,
                    "account_name": active.get("name", ""),
                    "status": "active" if active.get("id") == account_id else "account_inactive",
                    "port": self.httpd.server_port if self.httpd else 0,
                }
                sock.sendto(json.dumps(response, ensure_ascii=False).encode("utf-8"), address)
            except socket.timeout:
                continue
            except (OSError, ValueError, json.JSONDecodeError):
                continue

    def receive_image(self, handler, target):
        try:
            length = int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > self.MAX_IMAGE_BYTES:
            raise ValueError("图片为空或超过 300 MB")
        content_type = str(handler.headers.get("Content-Type", "")).split(";", 1)[0].lower()
        ext = str(handler.headers.get("X-File-Extension", "")).lower().strip()
        if ext and not ext.startswith("."):
            ext = "." + ext
        if ext not in self.IMAGE_EXTENSIONS:
            ext = self.MIME_EXTENSIONS.get(content_type, "")
        if ext not in self.IMAGE_EXTENSIONS:
            raise ValueError("仅支持 JPG、PNG、WEBP、BMP、GIF 图片")
        folder = os.path.abspath(str(target.get("folder") or ""))
        prefix = str(target.get("prefix") or "").strip()
        if not folder:
            raise ValueError("目标规格文件夹无效")
        os.makedirs(folder, exist_ok=True)
        with self.upload_lock:
            index = 1
            while True:
                suffix = f"【扫码上传{index}】" if prefix else f"扫码上传{index}"
                max_stem = max(1, 240 - len(folder) - len(os.sep) - len(ext))
                safe_prefix = prefix[:max(0, max_stem - len(suffix))].rstrip(" .")
                path = os.path.join(folder, safe_prefix + suffix + ext)
                if not os.path.exists(path):
                    break
                index += 1
            temp_path = path + ".uploading"
            remaining = length
            try:
                with open(temp_path, "wb") as output:
                    while remaining:
                        chunk = handler.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("图片传输中断")
                        output.write(chunk)
                        remaining -= len(chunk)
                if not self.is_image_file(temp_path, ext):
                    raise ValueError("文件内容不是有效图片")
                os.replace(temp_path, path)
            except Exception:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                raise
        return path

    @staticmethod
    def is_image_file(path, ext):
        with open(path, "rb") as image_file:
            header = image_file.read(16)
        if ext in {".jpg", ".jpeg"}:
            return header.startswith(b"\xff\xd8\xff")
        if ext == ".png":
            return header.startswith(b"\x89PNG\r\n\x1a\n")
        if ext == ".webp":
            return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
        if ext == ".bmp":
            return header.startswith(b"BM")
        if ext == ".gif":
            return header.startswith((b"GIF87a", b"GIF89a"))
        return False


class MobileBindingDialog(QDialog):
    def __init__(self, service, account, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowCloseButtonHint)
        self.service = service
        self.account = account
        self.pairing = {}
        self.setWindowTitle("手机绑定")
        self.setMinimumSize(520, 650)
        layout = QVBoxLayout(self)
        title = QLabel("素材库助手")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        refresh_button = QPushButton("刷新绑定二维码")
        refresh_button.clicked.connect(self.refresh_pairing)
        device_title = QLabel("已绑定手机")
        device_title.setStyleSheet("font-weight: bold;")
        self.device_list = QListWidget()
        revoke_button = QPushButton("解除选中手机绑定")
        revoke_button.clicked.connect(self.revoke_selected)
        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.close)
        layout.addWidget(title)
        layout.addWidget(self.qr_label)
        layout.addWidget(self.status_label)
        layout.addWidget(refresh_button)
        layout.addWidget(device_title)
        layout.addWidget(self.device_list, 1)
        layout.addWidget(revoke_button)
        layout.addWidget(close_buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_expiry_text)
        self.timer.start(1000)
        self.refresh_tick = 0
        self.refresh_pairing()

    @staticmethod
    def qr_pixmap(text):
        qr = qrcode.QRCode(version=None, box_size=1, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        scale = max(1, 300 // len(matrix))
        size = len(matrix) * scale
        image = QImage(size, size, QImage.Format_RGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.black)
        for row, values in enumerate(matrix):
            for column, enabled in enumerate(values):
                if enabled:
                    painter.drawRect(column * scale, row * scale, scale, scale)
        painter.end()
        return QPixmap.fromImage(image)

    def refresh_pairing(self):
        try:
            self.pairing = self.service.create_pairing(self.account)
            self.qr_label.setPixmap(self.qr_pixmap(self.pairing["uri"]))
            self.refresh_devices()
            self.update_expiry_text()
        except Exception as exc:
            QMessageBox.warning(self, "手机绑定启动失败", str(exc))

    def update_expiry_text(self):
        self.refresh_tick += 1
        if self.refresh_tick % 3 == 0:
            self.refresh_devices()
        seconds = max(0, int(self.pairing.get("expires", 0) - time.time()))
        self.status_label.setText(
            f"电脑：{socket.gethostname()}  |  账号：{self.account.get('name', '')}\n"
            f"局域网地址：{', '.join(self.pairing.get('hosts') or [])}:{self.pairing.get('port', '')}\n"
            f"请用“素材库助手”扫码，二维码剩余 {seconds} 秒"
        )

    def refresh_devices(self):
        self.device_list.clear()
        for device in self.service.devices_for_account(self.account.get("id")):
            item = QListWidgetItem(
                f"{device.get('device_name', 'Android 手机')}  |  "
                f"最近连接：{device.get('last_seen') or '从未'}"
            )
            item.setData(Qt.UserRole, device.get("device_id"))
            self.device_list.addItem(item)
        if not self.device_list.count():
            self.device_list.addItem("暂无已绑定手机")

    def revoke_selected(self):
        item = self.device_list.currentItem()
        device_id = item.data(Qt.UserRole) if item else ""
        if not device_id:
            return
        if QMessageBox.question(
            self,
            "解除绑定",
            "解除后该手机必须重新扫码才能访问此账号，是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.service.revoke_device(str(self.account.get("id") or ""), str(device_id))
        self.refresh_devices()

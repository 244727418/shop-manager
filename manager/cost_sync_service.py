# -*- coding: utf-8 -*-
"""Authenticated peer-to-peer LAN transport for real-time cost sync."""

import base64
import hashlib
import hmac
import json
import secrets
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal


class _ExclusiveHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CostSyncService(QObject):
    """Hosts or consumes one account's cost-library synchronization organization."""

    context_requested = pyqtSignal(object)
    status_changed = pyqtSignal(str)
    snapshot_applied = pyqtSignal(object)

    PROTOCOL = "shop-cost-sync-v1"
    DISCOVERY_PORT = 48780
    HTTP_PORTS = range(48781, 48791)
    MAX_BODY_BYTES = 96 * 1024 * 1024
    CLOCK_SKEW_SECONDS = 90
    POLL_SECONDS = 1.0
    PEER_CACHE_SECONDS = 300
    QUICK_DISCOVERY_SECONDS = 0.18

    def __init__(self, context_provider, parent=None):
        super().__init__(parent)
        self.context_provider = context_provider
        self.device_id = str(uuid.uuid4())
        self.httpd = None
        self.http_thread = None
        self.discovery_socket = None
        self.discovery_thread = None
        self.poll_thread = None
        self.running = False
        self.stopping = False
        self.publish_lock = threading.Lock()
        self.nonce_lock = threading.Lock()
        self.peer_lock = threading.Lock()
        self.seen_nonces = {}
        self.known_hosts = {}
        self.discovered_host = ""
        self.active_group_id = ""
        self.clock_offset_ms = 0
        self.last_stamp = 0
        self.last_contact_at = 0
        self.baseline_snapshot = None
        self.pending_snapshot = {"schema": 1, "rows": [], "categories": [], "images": [], "history": [], "history_clear_at": 0}
        self.wake_event = threading.Event()
        self.context_requested.connect(self._resolve_context_request, Qt.QueuedConnection)

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
        deadline = time.time() + 20
        while not request["event"].wait(0.1):
            if self.stopping:
                raise RuntimeError("成本同步服务已停止")
            if time.time() >= deadline:
                raise RuntimeError("成本同步等待本机数据超时")
        if request.get("error"):
            raise RuntimeError(request["error"])
        return request.get("result") or {}

    @staticmethod
    def create_invite(group_name, host=""):
        payload = {
            "v": 1,
            "group_id": uuid.uuid4().hex,
            "group_name": str(group_name or "成本库同步组织").strip() or "成本库同步组织",
            "secret": secrets.token_urlsafe(32),
        }
        host = CostSyncService._normalise_host(host)
        if host:
            payload["host"] = host
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return payload, token

    @staticmethod
    def parse_invite(token):
        try:
            token = str(token or "").strip()
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            payload = json.loads(raw.decode("utf-8"))
            if int(payload.get("v") or 0) != 1:
                raise ValueError
            group_id = str(payload.get("group_id") or "").strip()
            secret = str(payload.get("secret") or "").strip()
            if not group_id or len(secret) < 24:
                raise ValueError
            return {
                "group_id": group_id,
                "group_name": str(payload.get("group_name") or "成本库同步组织").strip(),
                "secret": secret,
                "host": CostSyncService._normalise_host(payload.get("host")),
            }
        except Exception as exc:
            raise ValueError("邀请密钥无效或不完整") from exc

    @staticmethod
    def _canonical_json(payload):
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def make_signature(cls, secret, method, path, timestamp, nonce, body=b""):
        body_hash = hashlib.sha256(body or b"").hexdigest()
        message = "\n".join((method.upper(), path, str(timestamp), str(nonce), body_hash)).encode("utf-8")
        return hmac.new(str(secret).encode("utf-8"), message, hashlib.sha256).hexdigest()

    def start(self):
        if self.running:
            self.reconfigure()
            self.notify_local_change()
            return
        self.stopping = False
        self.running = True
        self.wake_event.clear()
        self.reconfigure()
        self.poll_thread = threading.Thread(target=self._poll_loop, name="cost-sync-poll", daemon=True)
        self.poll_thread.start()

    def notify_local_change(self):
        """Wake the poller immediately; the snapshot diff remains the source of truth."""
        self.wake_event.set()

    def reconfigure(self):
        state = self.request_context("state") if self.running else {}
        group_id = str(state.get("group_id") or "")
        if group_id != self.active_group_id:
            self.clear_peer_cache()
            self.active_group_id = group_id
        should_host = bool(state.get("group_id"))
        if should_host and not self.httpd:
            self._start_host()
        elif not should_host and self.httpd:
            self._stop_host()
        self.discovered_host = ""

    def clear_peer_cache(self):
        with self.peer_lock:
            self.known_hosts.clear()
        self.discovered_host = ""

    def stop(self):
        self.stopping = True
        self.running = False
        self.wake_event.set()
        self._stop_host()
        current = threading.current_thread()
        if self.poll_thread and self.poll_thread is not current:
            self.poll_thread.join(timeout=2)
        self.poll_thread = None

    def _start_host(self):
        service = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format, *_args):
                return

            def send_json(self, status, payload):
                body = service._canonical_json(payload)
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def read_body(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length < 0 or length > service.MAX_BODY_BYTES:
                    raise ValueError("同步数据过大")
                return self.rfile.read(length) if length else b""

            def authenticate(self, body):
                state = service.request_context("state")
                group_id = self.headers.get("X-Cost-Group", "")
                timestamp = self.headers.get("X-Cost-Timestamp", "")
                nonce = self.headers.get("X-Cost-Nonce", "")
                signature = self.headers.get("X-Cost-Signature", "")
                if not state.get("group_id") or group_id != state.get("group_id"):
                    return False
                try:
                    if abs(time.time() - int(timestamp)) > service.CLOCK_SKEW_SECONDS:
                        return False
                except (TypeError, ValueError):
                    return False
                if not nonce or not service._accept_nonce(nonce):
                    return False
                expected = service.make_signature(
                    state.get("secret"), self.command, self.path.split("?", 1)[0], timestamp, nonce, body
                )
                return hmac.compare_digest(signature, expected)

            def dispatch(self):
                path = self.path.split("?", 1)[0]
                body = self.read_body()
                if not self.authenticate(body):
                    self.send_json(401, {"ok": False, "message": "同步密钥错误或请求已失效"})
                    return
                sender_host = service._remember_request_peer(
                    self.client_address[0], self.headers.get("X-Cost-Listen-Port")
                )
                if self.command == "GET" and path == "/api/v1/cost-sync/status":
                    state = service.request_context("state")
                    self.send_json(200, {
                        "ok": True,
                        "server_time_ms": int(time.time() * 1000),
                        "revision": int(state.get("revision") or 0),
                        "snapshot_hash": state.get("snapshot_hash") or "",
                        "publisher_id": state.get("publisher_id") or "",
                        "published_at": state.get("published_at") or "",
                    })
                    return
                if self.command == "GET" and path == "/api/v1/cost-sync/snapshot":
                    result = service.request_context("snapshot")
                    self.send_json(200, {"ok": True, **result})
                    return
                if self.command == "POST" and path == "/api/v1/cost-sync/publish":
                    payload = json.loads(body.decode("utf-8")) if body else {}
                    before = service.request_context("state")
                    with service.publish_lock:
                        result = service.request_context(
                            "publish",
                            snapshot=payload.get("snapshot"),
                            publisher_id=str(payload.get("publisher_id") or ""),
                        )
                    self.send_json(200, {"ok": True, **result})
                    if int(result.get("revision") or 0) > int(before.get("revision") or 0):
                        threading.Thread(
                            target=service._send_snapshot_to_peers,
                            args=(payload.get("snapshot") or {}, sender_host),
                            name="cost-sync-relay",
                            daemon=True,
                        ).start()
                    return
                self.send_json(404, {"ok": False, "message": "接口不存在"})

            def do_GET(self):
                try:
                    self.dispatch()
                except Exception as exc:
                    self.send_json(500, {"ok": False, "message": str(exc)})

            def do_POST(self):
                self.do_GET()

        for port in self.HTTP_PORTS:
            try:
                self.httpd = _ExclusiveHTTPServer(("0.0.0.0", port), Handler)
                break
            except OSError:
                continue
        if not self.httpd:
            raise RuntimeError("无法启动成本同步节点，局域网端口均被占用")
        self.http_thread = threading.Thread(target=self.httpd.serve_forever, name="cost-sync-http", daemon=True)
        self.http_thread.start()
        self.discovery_thread = threading.Thread(target=self._discovery_loop, name="cost-sync-discovery", daemon=True)
        self.discovery_thread.start()
        self.status_changed.emit(f"同步节点已启动：{self.local_ip()}:{self.httpd.server_port}")

    def _stop_host(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
        if self.discovery_socket:
            try:
                self.discovery_socket.close()
            except Exception:
                pass
        self.httpd = None
        self.discovery_socket = None
        current = threading.current_thread()
        for thread in (self.http_thread, self.discovery_thread):
            if thread and thread is not current:
                thread.join(timeout=1)
        self.http_thread = None
        self.discovery_thread = None

    def _accept_nonce(self, nonce):
        now = time.time()
        with self.nonce_lock:
            self.seen_nonces = {key: value for key, value in self.seen_nonces.items() if now - value < 120}
            if nonce in self.seen_nonces:
                return False
            self.seen_nonces[nonce] = now
            return True

    def _discovery_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.DISCOVERY_PORT))
        sock.settimeout(1)
        self.discovery_socket = sock
        while self.running and self.httpd:
            try:
                raw, address = sock.recvfrom(4096)
                request = json.loads(raw.decode("utf-8"))
                state = self.request_context("state")
                if request.get("protocol") != self.PROTOCOL or request.get("group_id") != state.get("group_id"):
                    continue
                response = self._canonical_json({
                    "protocol": self.PROTOCOL,
                    "group_id": state.get("group_id"),
                    "device_id": self.device_id,
                    "port": self.httpd.server_port,
                    "revision": int(state.get("revision") or 0),
                    "latest_stamp": self._snapshot_latest_stamp(
                        json.loads(state.get("snapshot_json") or "{}")
                    ),
                })
                sock.sendto(response, address)
            except socket.timeout:
                continue
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
                if self.running:
                    time.sleep(0.2)

    @staticmethod
    def _snapshot_latest_stamp(snapshot):
        return max(
            [int((snapshot or {}).get("history_clear_at") or 0)]
            + [
                int(item.get("_modified_at") or 0)
                for key in ("rows", "categories", "images", "history")
                for item in (snapshot or {}).get(key, [])
            ]
        )

    def discover_all(self, group_id, timeout=1.2):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peers = {}
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.15)
            request = self._canonical_json({
                "protocol": self.PROTOCOL, "group_id": group_id, "device_id": self.device_id
            })
            sock.bind(("", 0))
            sock.sendto(request, ("255.255.255.255", self.DISCOVERY_PORT))
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw, address = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                response = json.loads(raw.decode("utf-8"))
                if (
                    response.get("protocol") == self.PROTOCOL
                    and response.get("group_id") == group_id
                    and response.get("device_id") != self.device_id
                ):
                    host = f"{address[0]}:{int(response.get('port') or min(self.HTTP_PORTS))}"
                    peers[host] = max(
                        int(response.get("latest_stamp") or 0),
                        int(peers.get(host) or 0),
                    )
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        finally:
            sock.close()
        return [host for host, _stamp in sorted(peers.items(), key=lambda item: (-item[1], item[0]))]

    def discover(self, group_id, timeout=1.2):
        peers = self.discover_all(group_id, timeout)
        return peers[0] if peers else ""

    @staticmethod
    def local_ip():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            sock.close()

    def _host_from_state(self, state, discover=True):
        host = str(state.get("coordinator_host") or "").strip()
        if host.startswith("http://"):
            host = host[7:]
        if host and ":" not in host:
            host = f"{host}:{min(self.HTTP_PORTS)}"
        if not host and self.discovered_host:
            host = self.discovered_host
        if not host:
            cached = self._cached_peer_hosts()
            host = cached[0] if cached else ""
        if not host and discover:
            peers = self._discover_peer_hosts(state.get("group_id"))
            host = peers[0] if peers else ""
            if host:
                try:
                    self.request_context("remember_host", coordinator_host=host)
                except Exception:
                    pass
        return host

    def _request(self, method, path, payload=None, timeout=2, host_override=""):
        state = self.request_context("state")
        if not state.get("group_id"):
            raise RuntimeError("当前账号尚未加入成本同步组织")
        host = str(host_override or "").strip() or self._host_from_state(state)
        if not host:
            raise RuntimeError("未发现在线的成本同步成员")
        body = self._canonical_json(payload) if payload is not None else b""
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Cost-Group": state.get("group_id"),
            "X-Cost-Timestamp": timestamp,
            "X-Cost-Nonce": nonce,
            "X-Cost-Signature": self.make_signature(state.get("secret"), method, path, timestamp, nonce, body),
        }
        if self.httpd:
            headers["X-Cost-Listen-Port"] = str(self.httpd.server_port)
        request = Request(f"http://{host}{path}", data=body if method == "POST" else None, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                message = json.loads(exc.read().decode("utf-8")).get("message")
            except Exception:
                message = str(exc)
            raise RuntimeError(message or f"同步成员返回错误 {exc.code}") from exc
        except (URLError, OSError) as exc:
            if host_override:
                raise RuntimeError("该成本同步成员当前不可用") from exc
            self.discovered_host = ""
            fallback = self.discover(state.get("group_id"))
            if not fallback or fallback == host:
                raise RuntimeError("未发现在线的成本同步成员") from exc
            self.discovered_host = fallback
            host = fallback
            fallback_request = Request(
                f"http://{fallback}{path}", data=body if method == "POST" else None,
                headers=headers, method=method,
            )
            try:
                with urlopen(fallback_request, timeout=timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, OSError) as retry_exc:
                raise RuntimeError("未发现可用的成本同步成员") from retry_exc
        if not result.get("ok"):
            raise RuntimeError(result.get("message") or "成本同步失败")
        self._remember_peer(host)
        self.last_contact_at = time.time()
        return result

    def publish_snapshot(self, snapshot):
        with self.publish_lock:
            local_result = self.request_context("publish", snapshot=snapshot, publisher_id=self.device_id)
        self._send_snapshot_to_peers(snapshot)
        return local_result

    def _next_stamp(self):
        value = int(time.time() * 1000) + int(self.clock_offset_ms)
        self.last_stamp = max(value, self.last_stamp + 1)
        return self.last_stamp

    def _observe_snapshot(self, snapshot):
        self.last_stamp = max(self.last_stamp, self._snapshot_latest_stamp(snapshot))

    @staticmethod
    def _normalise_host(host):
        host = str(host or "").strip()
        if host.startswith("http://"):
            host = host[7:]
        if host and ":" not in host:
            host = f"{host}:{min(CostSyncService.HTTP_PORTS)}"
        return host.rstrip("/")

    def _own_hosts(self):
        if not self.httpd:
            return set()
        port = self.httpd.server_port
        return {f"127.0.0.1:{port}", f"{self.local_ip()}:{port}"}

    def _remember_peer(self, host):
        host = self._normalise_host(host)
        if not host or host in self._own_hosts():
            return ""
        with self.peer_lock:
            self.known_hosts[host] = time.time()
        self.discovered_host = host
        return host

    def _remember_request_peer(self, address, port):
        try:
            port = int(port)
        except (TypeError, ValueError):
            return ""
        if port not in self.HTTP_PORTS:
            return ""
        return self._remember_peer(f"{address}:{port}")

    def _cached_peer_hosts(self):
        cutoff = time.time() - self.PEER_CACHE_SECONDS
        with self.peer_lock:
            self.known_hosts = {
                host: seen_at for host, seen_at in self.known_hosts.items() if seen_at >= cutoff
            }
            return list(self.known_hosts)

    def _discover_peer_hosts(self, group_id, timeout=None):
        peers = self.discover_all(
            group_id, timeout=self.QUICK_DISCOVERY_SECONDS if timeout is None else timeout
        )
        for host in peers:
            self._remember_peer(host)
        return peers

    def _peer_hosts(self, discover_if_empty=True):
        state = self.request_context("state")
        hosts = []
        preferred = self._normalise_host(state.get("coordinator_host"))
        if preferred:
            hosts.append(preferred)
        hosts.extend(self._cached_peer_hosts())
        if discover_if_empty and not hosts:
            hosts.extend(self._discover_peer_hosts(state.get("group_id")))
        own_hosts = self._own_hosts()
        return [host for host in dict.fromkeys(hosts) if host not in own_hosts]

    def _send_snapshot_to_peers(self, snapshot, exclude_host=""):
        if not self.running:
            return 0
        exclude_host = self._normalise_host(exclude_host)
        attempted = set()
        sent = 0

        def send(host):
            nonlocal sent
            if not host or host == exclude_host or host in attempted:
                return
            attempted.add(host)
            try:
                self._request(
                    "POST", "/api/v1/cost-sync/publish",
                    {"snapshot": snapshot, "publisher_id": self.device_id},
                    timeout=30, host_override=host,
                )
                sent += 1
            except Exception:
                pass

        try:
            hosts = self._peer_hosts()
        except RuntimeError:
            return 0
        for host in hosts:
            send(host)
        if not sent and not exclude_host and self.running:
            try:
                state = self.request_context("state")
            except RuntimeError:
                return sent
            for host in self._discover_peer_hosts(state.get("group_id"), timeout=0.35):
                send(host)
        return sent

    @staticmethod
    def _snapshot_items(snapshot, key, identity):
        return {
            str(item.get(identity) or "").strip(): dict(item)
            for item in (snapshot or {}).get(key, [])
            if str(item.get(identity) or "").strip()
        }

    @staticmethod
    def _shared_value(item):
        derived = {"cost_calc_mode", "cost_price"} if int((item or {}).get("is_combo") or 0) else set()
        return {
            key: value for key, value in (item or {}).items()
            if not key.startswith("_") and key not in derived
        }

    def _snapshot_diff(self, old, new):
        stamp = self._next_stamp()
        old_clear_at = int((old or {}).get("history_clear_at") or 0)
        new_clear_at = int((new or {}).get("history_clear_at") or 0)
        result = {
            "schema": 1, "rows": [], "categories": [], "images": [], "history": [],
            "history_clear_at": new_clear_at if new_clear_at != old_clear_at else 0,
        }
        for key, identity in (
            ("rows", "spec_code"), ("categories", "label"),
            ("images", "spec_code"), ("history", "event_id"),
        ):
            old_items = self._snapshot_items(old, key, identity)
            new_items = self._snapshot_items(new, key, identity)
            for item_id, item in new_items.items():
                if self._shared_value(old_items.get(item_id)) == self._shared_value(item):
                    continue
                changed = dict(item)
                changed["_modified_at"] = stamp
                changed["_modified_by"] = self.device_id
                result[key].append(changed)
            removed_ids = (
                old_items.keys() - new_items.keys()
                if key != "images" and not (key == "history" and new_clear_at > old_clear_at)
                else ()
            )
            for item_id in removed_ids:
                if old_items[item_id].get("_deleted"):
                    continue
                deleted = {
                    identity: item_id,
                    "_deleted": True,
                    "_modified_at": stamp,
                    "_modified_by": self.device_id,
                }
                if key == "history":
                    deleted["event_time_ms"] = int(old_items[item_id].get("event_time_ms") or 0)
                result[key].append(deleted)
        return result

    @staticmethod
    def _has_changes(snapshot):
        return bool(
            (snapshot or {}).get("rows")
            or (snapshot or {}).get("categories")
            or (snapshot or {}).get("images")
            or (snapshot or {}).get("history")
            or int((snapshot or {}).get("history_clear_at") or 0)
        )

    def _merge_pending(self, changes, preserve_existing=False):
        if not self._has_changes(changes):
            return
        if preserve_existing:
            existing_rows = self._snapshot_items(self.pending_snapshot, "rows", "spec_code")
            existing_categories = self._snapshot_items(self.pending_snapshot, "categories", "label")
            existing_images = self._snapshot_items(self.pending_snapshot, "images", "spec_code")
            existing_history = self._snapshot_items(self.pending_snapshot, "history", "event_id")
            changes = {
                "schema": 1,
                "rows": [row for row in changes.get("rows", []) if row.get("spec_code") not in existing_rows],
                "categories": [row for row in changes.get("categories", []) if row.get("label") not in existing_categories],
                "images": [image for image in changes.get("images", []) if image.get("spec_code") not in existing_images],
                "history": [item for item in changes.get("history", []) if item.get("event_id") not in existing_history],
                "history_clear_at": int(changes.get("history_clear_at") or 0),
            }
        self.pending_snapshot = self.request_context(
            "merge_snapshots", current=self.pending_snapshot, incoming=changes
        ).get("snapshot") or self.pending_snapshot
        self.request_context("save_pending", snapshot=self.pending_snapshot)

    def _clear_pending(self):
        self.pending_snapshot = {"schema": 1, "rows": [], "categories": [], "images": [], "history": [], "history_clear_at": 0}
        self.request_context("save_pending", snapshot=self.pending_snapshot)
        self.request_context("clear_local_dirty")

    def _should_skip_initial_diff(self, state):
        return bool(self.request_context("skip_initial_diff").get("skip"))

    def pull_latest(self, host="", replace_local=False):
        status = self._request("GET", "/api/v1/cost-sync/status", host_override=host)
        if status.get("server_time_ms"):
            self.clock_offset_ms = int(status["server_time_ms"]) - int(time.time() * 1000)
        state = self.request_context("state")
        if str(status.get("snapshot_hash") or "") == str(state.get("snapshot_hash") or ""):
            return {"changed": False, **status}
        remote = self._request("GET", "/api/v1/cost-sync/snapshot", timeout=30, host_override=host)
        self._observe_snapshot(remote.get("snapshot"))
        result = self.request_context(
            "apply_remote",
            snapshot=remote.get("snapshot"),
            revision=int(remote.get("revision") or 0),
            snapshot_hash=remote.get("snapshot_hash") or "",
            publisher_id=remote.get("publisher_id") or "",
            published_at=remote.get("published_at") or "",
            replace_local=replace_local,
        )
        self.snapshot_applied.emit(result)
        return {"changed": True, **result}

    def pull_all_latest(self, replace_local=False):
        contacted = 0
        changed = False
        attempted = set()

        def pull(host):
            nonlocal contacted, changed
            if not host or host in attempted:
                return
            attempted.add(host)
            try:
                result = self.pull_latest(host, replace_local=replace_local)
                contacted += 1
                changed = changed or bool(result.get("changed"))
            except Exception:
                pass

        for host in self._peer_hosts():
            pull(host)
        if not contacted:
            state = self.request_context("state")
            for host in self._discover_peer_hosts(state.get("group_id"), timeout=0.35):
                pull(host)
        if not contacted:
            raise RuntimeError("未发现在线的成本同步成员")
        return {"changed": changed, "contacted": contacted}

    def _poll_loop(self):
        while self.running:
            self.wake_event.clear()
            try:
                state = self.request_context("state")
                if state.get("group_id"):
                    if self.baseline_snapshot is None:
                        skip_initial = self._should_skip_initial_diff(state)
                        if skip_initial:
                            # A joining computer must pull first; its pre-existing library is not a local edit.
                            self._clear_pending()
                        else:
                            loaded = self.request_context("load_pending")
                            self.pending_snapshot = loaded.get("snapshot") or self.pending_snapshot
                            self._observe_snapshot(self.pending_snapshot)
                        try:
                            previous = json.loads(state.get("snapshot_json") or "{}")
                        except (TypeError, ValueError, json.JSONDecodeError):
                            previous = {}
                        self._observe_snapshot(previous)
                        local = self.request_context("local_snapshot").get("snapshot") or {
                            "schema": 1, "rows": [], "categories": [], "images": [], "history": [], "history_clear_at": 0
                        }
                        if not skip_initial:
                            self._merge_pending(self._snapshot_diff(previous, local), preserve_existing=True)
                        self.baseline_snapshot = local

                    latest_state = self.request_context("state")
                    skip_initial = self._should_skip_initial_diff(latest_state)
                    current = self.request_context("local_snapshot").get("snapshot") or self.baseline_snapshot
                    if not skip_initial:
                        try:
                            comparison = json.loads(latest_state.get("snapshot_json") or "{}")
                        except (TypeError, ValueError, json.JSONDecodeError):
                            comparison = {}
                        self._observe_snapshot(comparison)
                        self._merge_pending(self._snapshot_diff(comparison, current))
                        if self._has_changes(self.pending_snapshot):
                            self.publish_snapshot(self.pending_snapshot)
                            self._clear_pending()
                    try:
                        self.pull_all_latest(replace_local=bool(skip_initial))
                        if skip_initial:
                            self.request_context("clear_skip_initial_diff")
                    except Exception:
                        pass
                    self.baseline_snapshot = self.request_context("local_snapshot").get("snapshot") or current
            except Exception as exc:
                self.status_changed.emit(str(exc))
            if self.running:
                self.wake_event.wait(self.POLL_SECONDS)


__all__ = ["CostSyncService"]

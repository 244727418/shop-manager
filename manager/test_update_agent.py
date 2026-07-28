import socket
import tempfile
import threading
import time
from pathlib import Path

try:
    from manager import update_manager
except ModuleNotFoundError:
    import update_manager


class _DownloadResponse:
    def __init__(self, content):
        self.content = content
        self.headers = {"content-length": str(len(content))}

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        midpoint = max(1, len(self.content) // 2)
        yield self.content[:midpoint]
        yield self.content[midpoint:]

    def close(self):
        return None


def test_background_update_flow():
    original_settings_path = update_manager.global_update_settings_path
    original_get = update_manager.requests.get
    original_cache_dir = update_manager.update_cache_dir
    original_fetch_trusted = update_manager.fetch_trusted_manifest
    original_agent_port = update_manager.UPDATE_AGENT_UDP_PORT
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        settings_path = root / "update_settings.json"
        update_manager.global_update_settings_path = lambda: str(settings_path)
        try:
            package = root / "shop_manager_v6.0.exe"
            package.write_bytes(b"verified-background-update")
            manifest = update_manager.build_manifest(
                "6.0",
                str(package),
                "后台更新说明",
                host_ip="127.0.0.1",
            )

            settings = update_manager.bind_trusted_update_source(manifest)
            assert settings["auto_update_enabled"] == "1"
            assert update_manager.is_trusted_update_manifest(manifest, settings)

            service = update_manager.UpdatePublishService()
            service.manifest = manifest
            broadcast_ports = []
            service._broadcast = lambda _payload, ports=(update_manager.UDP_PORT,): broadcast_ports.extend(ports)
            service.push()
            assert broadcast_ports == [update_manager.UDP_PORT, update_manager.UPDATE_AGENT_UDP_PORT]

            update_manager.requests.get = lambda *args, **kwargs: _DownloadResponse(package.read_bytes())
            download_dir = root / "received"
            downloaded = Path(
                update_manager.download_update_file(
                    manifest,
                    str(download_dir),
                    require_hash=True,
                )
            )
            assert downloaded.name == "shop_manager_v6.0.exe"
            assert downloaded.read_bytes() == package.read_bytes()
            assert not list(download_dir.rglob("*.download"))
            assert not (download_dir / ".update_tmp").exists()

            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.bind(("127.0.0.1", 0))
            update_manager.UPDATE_AGENT_UDP_PORT = probe.getsockname()[1]
            probe.close()
            cache_dir = root / "cache"
            update_manager.update_cache_dir = lambda: str(cache_dir)
            update_manager.fetch_trusted_manifest = lambda settings=None, timeout=4: None
            stop_event = threading.Event()
            agent = threading.Thread(
                target=update_manager.run_update_agent,
                args=("5.0", stop_event),
                daemon=True,
            )
            agent.start()
            time.sleep(0.2)
            assert update_manager.notify_update_agent(manifest)
            deadline = time.time() + 3
            pending = None
            while time.time() < deadline and pending is None:
                pending = update_manager.load_pending_update("5.0", str(cache_dir))
                time.sleep(0.05)
            stop_event.set()
            agent.join(2)
            assert pending and Path(pending["_cached_path"]).suffix.lower() == ".exe"
            assert update_manager.load_pending_update("6.0", str(cache_dir)) is None
            assert update_manager.load_pending_update(
                "6.0", str(cache_dir), allow_current=True
            )["notes"] == "后台更新说明"
            assert not list(cache_dir.rglob("*.download"))
            saved_settings = update_manager.load_global_update_settings()
            assert saved_settings["last_update_manifest"]["notes"] == "后台更新说明"

            app_source = Path(__file__).with_name("shop_manager.py").read_text(encoding="utf-8-sig")
            assert "notify_update_agent(payload)" in app_source
            assert 'dialog.addButton("立即重启"' in app_source
            assert 'dialog.addButton("稍后自行重启"' in app_source
        finally:
            update_manager.requests.get = original_get
            update_manager.update_cache_dir = original_cache_dir
            update_manager.fetch_trusted_manifest = original_fetch_trusted
            update_manager.UPDATE_AGENT_UDP_PORT = original_agent_port
            update_manager.global_update_settings_path = original_settings_path


if __name__ == "__main__":
    test_background_update_flow()
    print("background update flow OK")

import tempfile
from pathlib import Path

try:
    from manager import update_manager
except ModuleNotFoundError:
    import update_manager


def test_foreground_only_update_flow():
    original_settings_path = update_manager.global_update_settings_path
    with tempfile.TemporaryDirectory() as temp_dir:
        settings_path = Path(temp_dir) / "update_settings.json"
        update_manager.global_update_settings_path = lambda: str(settings_path)
        try:
            package = Path(temp_dir) / "shop_manager_v6.0.exe"
            package.write_bytes(b"foreground-only-update")
            manifest = update_manager.build_manifest("6.0", str(package), "", host_ip="127.0.0.1")

            settings = update_manager.bind_trusted_update_source(manifest)
            assert settings["auto_update_enabled"] == "0"
            assert update_manager.is_trusted_update_manifest(manifest, settings)

            service = update_manager.UpdatePublishService()
            service.manifest = manifest
            broadcast_ports = []
            service._broadcast = lambda _payload, ports=(update_manager.UDP_PORT,): broadcast_ports.extend(ports)
            service.push()
            assert broadcast_ports == [update_manager.UDP_PORT]
            assert update_manager.UPDATE_AGENT_UDP_PORT not in broadcast_ports
        finally:
            update_manager.global_update_settings_path = original_settings_path


if __name__ == "__main__":
    test_foreground_only_update_flow()
    print("foreground-only update flow OK")

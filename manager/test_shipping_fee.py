from manager.data_root import DataRootManager
from manager.db import SafeDatabaseManager


def test_shipping_fee_uses_next_weight_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    DataRootManager().set_data_root(str(tmp_path / "data"))
    db = SafeDatabaseManager(str(tmp_path / "shipping.db"))
    db.set_cost_shipping_rules({
        "ranges": [
            {"min": 0, "max": 1, "fee": 2.5},
            {"min": 1, "max": 2, "fee": 3.5},
            {"min": 3, "max": 4, "fee": 4.5},
        ],
        "over": {"threshold": 3, "base_fee": 4.5, "deduct_weight": 1, "step_weight": 1, "step_fee": 1},
    })
    assert db.calculate_cost_shipping_fee(2.5) == 4.5
    db.conn.close()

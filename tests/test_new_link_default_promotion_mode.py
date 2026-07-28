import re
from pathlib import Path


def test_all_new_link_inserts_default_to_no_promotion():
    root = Path(__file__).parents[1] / "manager"
    sources = {
        "shop_manager.py": 1,
        "dialogs/cost_library.py": 2,
        "dialogs/store_margin.py": 1,
    }
    for relative_path, expected_count in sources.items():
        text = (root / relative_path).read_text(encoding="utf-8")
        inserts = re.findall(r"INSERT INTO products\s*\([^)]*is_natural_flow\)", text, re.DOTALL)
        assert len(inserts) >= expected_count

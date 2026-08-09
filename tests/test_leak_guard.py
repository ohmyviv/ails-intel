from pathlib import Path
from ails_intel.leak_guard import scan


def test_clean_tree_passes(tmp_path: Path):
    (tmp_path / "a.md").write_text("public text 0123456789abcdef0123456789abcdef01234567")
    assert scan(tmp_path) == []


def test_google_sheet_url_detected(tmp_path: Path):
    bad = "https://" + "docs.google.com" + "/spreadsheets/" + "d/" + "placeholder"
    (tmp_path / "a.md").write_text(bad)
    assert scan(tmp_path)

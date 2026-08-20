from pathlib import Path


def test_ticket_5_documentation_acceptance():
    root = Path(__file__).parents[1]
    readme = (root / "README.md").read_text()
    assert "TableStory" in readme
    assert "?mode=tv" in readme
    assert "pytest" in readme and "node --test" in readme
    assert not (root / "catalog.json").exists()
    terminology_test = root / "tests/test_terminology.py"
    assert terminology_test.is_file()
    source = terminology_test.read_text().lower()
    assert all(marker in source for marker in ("forbidden", "violations", '"watch" + "list"'))

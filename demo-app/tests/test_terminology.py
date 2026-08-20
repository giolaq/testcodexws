from pathlib import Path


def test_supported_product_files_use_recipe_language():
    root = Path(__file__).parents[1]
    forbidden = ["pocket " + "cin" + "ema", "mo" + "vie", "fi" + "lm", "watch" + "list", "post" + "er"]
    files = [root / "app.py", root / "recipe_api.py", *root.glob("templates/*"), *root.glob("static/*.js"), *root.glob("static/*.css")]
    violations = {
        str(path.relative_to(root)): word
        for path in files for word in forbidden
        if word in path.read_text().lower()
    }
    assert violations == {}

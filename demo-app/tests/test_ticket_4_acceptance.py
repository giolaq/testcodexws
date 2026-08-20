from pathlib import Path


def test_ticket_4_tv_recipe_acceptance(client):
    home = client.get("/?mode=tv")
    assert home.status_code == 200
    assert b'class="tv"' in home.data
    rails = client.get("/api/rails").get_json()
    assert [rail["title"] for rail in rails] == [
        "Popular this week", "Ready in 30 minutes", "Vegetarian favourites", "My Cookbook",
    ]
    assert all(len(rail["recipe_ids"]) >= 2 for rail in rails[:3])
    assert b"recipe-rails.js" in home.data and b"recipe-tv-nav.js" in home.data

    root = Path(__file__).parents[1] / "static"
    browse = (root / "recipe-tv-nav.js").read_text()
    detail = (root / "recipe-tv-detail.js").read_text()
    rails_source = (root / "recipe-rails.js").read_text()
    assert all(key in browse for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"))
    assert "scrollIntoView" in browse
    assert "Escape" in detail and "Backspace" in detail
    assert "/api/rails" in rails_source and "recipe_ids" in rails_source
    assert b"/?mode=tv" in client.get("/recipe/tomato-pasta?mode=tv").data

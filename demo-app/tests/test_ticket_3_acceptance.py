from pathlib import Path


def test_ticket_3_mobile_recipe_acceptance(client):
    home = client.get("/")
    assert home.status_code == 200
    assert b"TableStory" in home.data
    assert b"Good food, clearly told." in home.data
    assert b'Search dishes or ingredients' in home.data
    assert b'data-search=' in home.data

    detail = client.get("/recipe/tomato-pasta")
    assert detail.status_code == 200
    assert all(text in detail.data for text in (b"Prep 10 min", b"Cook 20 min", b"Ingredients", b"Method"))
    assert b'aria-pressed="false"' in detail.data

    source = (Path(__file__).parents[1] / "static/app.js").read_text()
    assert "addEventListener('input'" in source and "card.hidden" in source
    assert "No recipes found" in home.data.decode()
    assert "aria-pressed" in source and "/api/cookbook" in source

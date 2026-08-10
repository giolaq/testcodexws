def test_home_and_recipe_detail_render(client):
    home = client.get("/")
    assert home.status_code == 200
    assert b"TableStory" in home.data
    assert home.data.count(b'class="recipe-card"') == 12
    assert client.get("/recipe/tomato-pasta").status_code == 200
    assert client.get("/recipe/missing").status_code == 404


def test_recipe_search_and_detail_api(client):
    recipes = client.get("/api/recipes?q=miso").get_json()
    assert [recipe["id"] for recipe in recipes] == ["miso-noodles"]
    assert client.get("/api/recipes/tomato-pasta").get_json()["title"] == "Silky Tomato Pasta"
    assert client.get("/api/recipes/missing").status_code == 404


def test_cookbook_round_trip(client):
    assert client.get("/api/cookbook").get_json() == []
    assert client.post("/api/cookbook", json={"id": "tomato-pasta"}).status_code == 201
    assert [recipe["id"] for recipe in client.get("/api/cookbook").get_json()] == ["tomato-pasta"]
    assert client.delete("/api/cookbook/tomato-pasta").get_json() == {"ids": []}
    assert client.post("/api/cookbook", json={"id": "missing"}).status_code == 400

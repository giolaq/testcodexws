def test_ticket_1_recipe_api_acceptance(client):
    response = client.get("/api/recipes")
    assert response.status_code == 200
    recipes = response.get_json()
    assert len(recipes) >= 12
    required = {
        "id", "title", "description", "category", "dietary_tags",
        "ingredients", "steps", "prep_minutes", "cook_minutes",
    }
    assert all(required <= set(recipe) for recipe in recipes)

    assert {recipe["id"] for recipe in client.get("/api/recipes?q=weeknight").get_json()} == {"tomato-pasta"}
    assert "tomato-pasta" in {recipe["id"] for recipe in client.get("/api/recipes?q=dinner").get_json()}
    assert "miso-noodles" in {recipe["id"] for recipe in client.get("/api/recipes?q=vegan").get_json()}
    assert {recipe["id"] for recipe in client.get("/api/recipes?q=tomatoes").get_json()} == {"tomato-pasta"}

    known_ids = {recipe["id"] for recipe in recipes}
    rails = client.get("/api/rails").get_json()
    assert rails and all(set(rail["recipe_ids"]) <= known_ids for rail in rails)
    assert client.get("/api/recipes/not-a-recipe").status_code == 404


def test_ticket_1_cookbook_acceptance(client):
    assert client.get("/api/cookbook").get_json() == []
    added = client.post("/api/cookbook", json={"id": "tomato-pasta"})
    assert added.status_code == 201
    assert added.get_json()["ids"] == ["tomato-pasta"]
    assert [recipe["id"] for recipe in client.get("/api/cookbook").get_json()] == ["tomato-pasta"]
    assert client.delete("/api/cookbook/tomato-pasta").get_json()["ids"] == []

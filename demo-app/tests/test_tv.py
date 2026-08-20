def test_tv_mode_and_recipe_detail(client):
    assert b'class="tv"' in client.get("/?mode=tv").data
    assert b'class="mobile"' in client.get("/").data
    detail = client.get("/recipe/tomato-pasta?mode=tv")
    assert detail.status_code == 200
    assert b'class="tv detail-page"' in detail.data


def test_recipe_rails_are_stable(client):
    rails = client.get("/api/rails").get_json()
    assert [rail["title"] for rail in rails] == [
        "Popular this week", "Ready in 30 minutes", "Vegetarian favourites", "My Cookbook",
    ]
    assert all("recipe_ids" in rail for rail in rails)

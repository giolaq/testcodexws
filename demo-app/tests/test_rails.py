from app import load_catalog


def test_rails_are_curated_and_stable(client):
    rails = client.get("/api/rails").get_json()

    assert [rail["title"] for rail in rails] == [
        "Trending now",
        "My watchlist",
        "Science fiction",
        "Mysteries",
    ]
    assert len(rails[0]["movie_ids"]) == 8
    assert len(rails[2]["movie_ids"]) >= 3

    catalog_ids = {movie["id"] for movie in load_catalog()}
    assert all(movie_id in catalog_ids for rail in rails for movie_id in rail["movie_ids"])
    assert client.get("/api/rails").get_json() == rails


def test_watchlist_rail_reflects_current_state(client):
    assert client.get("/api/rails").get_json()[1]["movie_ids"] == []

    client.post("/api/watchlist", json={"id": "static-sea"})
    client.post("/api/watchlist", json={"id": "afterlight"})
    assert client.get("/api/rails").get_json()[1]["movie_ids"] == ["afterlight", "static-sea"]

    client.delete("/api/watchlist/afterlight")
    assert client.get("/api/rails").get_json()[1]["movie_ids"] == ["static-sea"]

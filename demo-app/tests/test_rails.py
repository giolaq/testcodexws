def test_rails_are_curated_and_stable(client):
    rails = client.get("/api/rails").get_json()
    assert [rail["title"] for rail in rails] == ["Trending now", "My watchlist", "Science fiction", "Mysteries"]
    assert len(rails[0]["movie_ids"]) == 8
    assert len(rails[2]["movie_ids"]) >= 3


def test_watchlist_rail_reflects_session_state(client):
    client.post("/api/watchlist", json={"id": "afterlight"})
    assert client.get("/api/rails").get_json()[1]["movie_ids"] == ["afterlight"]

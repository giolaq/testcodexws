SMOKE_PATH = "/api/factory-smoke-f137258d0e"
READY_PAYLOAD = {"status": "ready"}


def test_factory_smoke_returns_exact_ready_json(client):
    response = client.get(SMOKE_PATH)

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == READY_PAYLOAD


def test_factory_smoke_is_repeatable_stateless_and_get_only(client):
    responses = [client.get(SMOKE_PATH) for _ in range(3)]

    assert all(response.status_code == 200 for response in responses)
    assert all(response.is_json for response in responses)
    assert [response.get_json() for response in responses] == [READY_PAYLOAD] * 3
    assert client.post(SMOKE_PATH).status_code == 405
    assert client.get(SMOKE_PATH).get_json() == READY_PAYLOAD


def test_existing_home_contract_remains_unchanged(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Pocket Cinema" in response.data
    assert response.data.count(b'class="movie-card"') == 24

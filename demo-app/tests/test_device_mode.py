def test_query_parameter_enables_tv_mode(client):
    assert b'class="tv"' in client.get("/?mode=tv").data
    assert b'class="mobile"' in client.get("/").data


def test_tv_user_agent_enables_tv_mode(client):
    response = client.get("/", headers={"User-Agent": "Example Smart-TV"})
    assert b'class="tv"' in response.data

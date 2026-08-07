def test_tv_detail_renders_full_screen_assets_and_actions(client):
    response = client.get("/movie/afterlight?mode=tv")

    assert response.status_code == 200
    assert b'<body class="detail-page tv"' in response.data
    assert b'tv-detail.css' in response.data
    assert b'tv-detail.js' in response.data
    assert response.data.count(b'data-tv-action') == 2
    assert b'data-browse-url="/?mode=tv"' in response.data


def test_mobile_detail_stays_mobile(client):
    response = client.get("/movie/afterlight")

    assert b'<body class="detail-page mobile"' in response.data
    assert b'data-browse-url="/"' in response.data


def test_tv_browse_links_keep_tv_mode_for_detail(client):
    response = client.get("/?mode=tv")

    assert b'href="/movie/afterlight?mode=tv"' in response.data

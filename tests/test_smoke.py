def test_index_ok(client):
    response = client.get('/')
    assert response.status_code == 200


def test_stats_ok(client):
    response = client.get('/stats')
    assert response.status_code == 200

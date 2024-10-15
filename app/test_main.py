from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_list_files():
    response = client.get("/files")
    assert response.status_code == 200
    assert response.json() == []

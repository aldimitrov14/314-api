from fastapi.testclient import TestClient

from app.main import app


def test_missing_api_key_is_rejected() -> None:
    client = TestClient(app)
    response = client.post("/v1/estimates/stl")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"

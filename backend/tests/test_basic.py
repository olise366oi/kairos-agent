import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from home import home_server
    return TestClient(home_server.app)


TOKEN = "test-token-for-pytest"


def test_import_ok():
    from home import home_server
    assert home_server.app is not None


def test_auth_required(client):
    resp = client.get("/api/home/state")
    assert resp.status_code == 401


def test_auth_wrong_token(client):
    resp = client.get("/api/home/state?t=wrong-token")
    assert resp.status_code == 401


def test_auth_correct_token(client):
    resp = client.get(f"/api/home/state?t={TOKEN}")
    assert resp.status_code == 200


def test_setup_status_initial(client):
    resp = client.get(f"/api/setup/status?t={TOKEN}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert "default_persona" in data
    assert data["default_persona"] != ""


def test_setup_save_and_status(client):
    payload = {
        "name": "测试用户",
        "api_key": "sk-test-key",
        "persona": "你是一个测试助手。",
    }
    resp = client.post(f"/api/setup/save?t={TOKEN}", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp2 = client.get(f"/api/setup/status?t={TOKEN}")
    data = resp2.json()
    assert data["configured"] is True
    assert data["name"] == "测试用户"
    assert data["persona"] == "你是一个测试助手。"

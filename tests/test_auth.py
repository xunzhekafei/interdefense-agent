"""账号密码登录：无账号文件时行为不变，有账号文件时保护全部 API。"""
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import AuthStore, add_user


class DummyAgent:
    def configured(self):
        return True

    def reply(self, *args, **kwargs):
        return "好的"

    def report(self, *args, **kwargs):
        return {}


def client_for(tmp_path):
    return TestClient(create_app(tmp_path, DummyAgent(), recognizer=None))


def test_auth_disabled_without_users_file(tmp_path):
    with client_for(tmp_path) as client:
        assert client.get("/api/me").json() == {"user": None, "enabled": False}
        assert client.get("/api/sessions").status_code == 200


def test_auth_protects_api_and_allows_login(tmp_path):
    add_user(tmp_path, "reviewer", "secret123")
    with client_for(tmp_path) as client:
        assert client.get("/api/me").status_code == 401
        assert client.get("/api/sessions").status_code == 401
        # 健康检查始终公开
        assert client.get("/api/health").status_code == 200

        assert client.post("/api/login", json={"username": "reviewer",
                                              "password": "wrong"}).status_code == 401
        response = client.post("/api/login", json={"username": "reviewer",
                                                   "password": "secret123"})
        assert response.status_code == 200
        assert response.json()["user"] == "reviewer"
        assert client.get("/api/me").json()["user"] == "reviewer"
        assert client.get("/api/sessions").status_code == 200

        assert client.post("/api/logout").status_code == 200
        assert client.get("/api/sessions").status_code == 401


def test_auth_store_token_roundtrip_and_tampering(tmp_path):
    store = AuthStore(tmp_path)
    token = store.issue("alice")
    assert store.check(token) == "alice"
    assert store.check("garbage") is None
    assert store.check(token + "x") is None
    assert store.check(None) is None


def test_auth_store_rejects_wrong_password(tmp_path):
    add_user(tmp_path, "alice", "secret123")
    store = AuthStore(tmp_path)
    assert store.verify("alice", "secret123") is True
    assert store.verify("alice", "wrong") is False
    assert store.verify("bob", "secret123") is False


def test_auth_store_rejects_expired_token(tmp_path, monkeypatch):
    import backend.auth as auth
    store = AuthStore(tmp_path)
    token = store.issue("alice")
    monkeypatch.setattr(auth.time, "time", lambda: 10**12)
    assert store.check(token) is None

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


def test_bearer_token_works_without_cookie(tmp_path):
    """原生 App 用 Authorization: Bearer；登录响应里要带 token。"""
    add_user(tmp_path, "reviewer", "secret123")
    with client_for(tmp_path) as client:
        login = client.post("/api/login", json={"username": "reviewer",
                                                "password": "secret123"}).json()
        token = login["token"]
        # 换一个不带 cookie 的客户端，模拟手机 App
        with client_for(tmp_path) as mobile:
            assert mobile.get("/api/sessions").status_code == 401
            headers = {"Authorization": f"Bearer {token}"}
            assert mobile.get("/api/me", headers=headers).json()["user"] == "reviewer"
            assert mobile.get("/api/sessions", headers=headers).status_code == 200
            assert mobile.get("/api/me", headers={"Authorization": "Bearer bad.token"}
                              ).status_code == 401


def test_bearer_token_is_revoked_by_logout(tmp_path):
    add_user(tmp_path, "reviewer", "secret123")
    with client_for(tmp_path) as client:
        token = client.post("/api/login", json={"username": "reviewer",
                                                "password": "secret123"}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/me", headers=headers).status_code == 200
        # 登出时带上 Bearer，token 必须和服务端版本号一起作废
        assert client.post("/api/logout", headers=headers).status_code == 200
        assert client.get("/api/me", headers=headers).status_code == 401


def test_websocket_accepts_bearer_token(tmp_path):
    """手机端的 WebSocket 也要能只靠 token 连上，不依赖 cookie。"""
    add_user(tmp_path, "reviewer", "secret123")
    with client_for(tmp_path) as client:
        token = client.post("/api/login", json={"username": "reviewer",
                                                "password": "secret123"}).json()["token"]
        session = client.post("/api/sessions", json={"candidate": "甲", "role": "答辩"},
                              headers={"Authorization": f"Bearer {token}"}).json()
        with client.websocket_connect(
                f"/api/sessions/{session['id']}/ws",
                headers={"Authorization": f"Bearer {token}"}) as ws:
            assert ws.receive_json()["type"] == "session.snapshot"

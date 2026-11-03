# -*- coding: utf-8 -*-
"""账号密码登录：只为「把作品部署出去给评审用」这一件事服务。

不追求完整的用户系统：

- 账号存 `<data_dir>/auth.json`，密码用 PBKDF2-HMAC-SHA256 加盐哈希
- 登录后发一个 HMAC 签名的会话 cookie（HttpOnly、SameSite=Lax、7 天）
- **没有 auth.json 时默认关闭鉴权**，本地开发和测试行为完全不变
- 用 `python -m backend.auth add <用户名>` 添加账号（交互式输入密码）

数据目录默认 `.web-data/`，已被 gitignore；`auth.json` 和 `auth_secret`
也在那里，不会进仓库。
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

COOKIE = "interview_session"
TTL_SECONDS = int(os.environ.get("AUTH_TTL_DAYS", "7")) * 86400
PBKDF2_ROUNDS = 200_000


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, salt: bytes | None = None) -> dict:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return {"salt": _b64(salt), "hash": _b64(digest)}


class AuthStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "auth.json"
        self.secret_path = self.data_dir / "auth_secret"
        self._secret_cache: bytes | None = None

    # ---- 账号 ----

    def enabled(self) -> bool:
        """有账号文件才启用鉴权；没有就保持本地无登录模式。"""
        return self.path.is_file()

    def users(self) -> dict:
        if not self.enabled():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        users = data.get("users")
        return users if isinstance(users, dict) else {}

    def verify(self, username: str, password: str) -> bool:
        user = self.users().get(username)
        if not isinstance(user, dict):
            return False
        try:
            salt = _unb64(user["salt"])
            expected = _unb64(user["hash"])
        except (KeyError, ValueError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
        return hmac.compare_digest(actual, expected)

    # ---- 会话 ----

    def _secret(self) -> bytes:
        if self._secret_cache is not None:
            return self._secret_cache
        env = os.environ.get("AUTH_SECRET")
        if env:
            self._secret_cache = env.encode()
        elif self.secret_path.is_file():
            self._secret_cache = self.secret_path.read_bytes()
        else:
            secret = secrets.token_bytes(32)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.secret_path.write_bytes(secret)
            self._secret_cache = secret
        return self._secret_cache

    def issue(self, username: str) -> str:
        payload = _b64(json.dumps(
            {"u": username, "exp": int(time.time()) + TTL_SECONDS},
            ensure_ascii=False).encode())
        signature = _b64(hmac.new(self._secret(), payload.encode(), hashlib.sha256).digest())
        return f"{payload}.{signature}"

    def check(self, token: str | None) -> str | None:
        if not token or "." not in token:
            return None
        payload, signature = token.rsplit(".", 1)
        expected = _b64(hmac.new(self._secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            data = json.loads(_unb64(payload))
        except (ValueError, json.JSONDecodeError):
            return None
        if int(data.get("exp", 0)) < time.time():
            return None
        return str(data.get("u") or "") or None


def add_user(data_dir: Path, username: str, password: str) -> None:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "auth.json"
    data = {"users": {}}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"users": {}}
    users = data.setdefault("users", {})
    users[username] = hash_password(password)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="管理评审账号")
    parser.add_argument("command", choices=["add", "list"])
    parser.add_argument("username", nargs="?")
    parser.add_argument("--data-dir", default=".web-data")
    args = parser.parse_args()

    store = AuthStore(Path(args.data_dir))
    if args.command == "add":
        if not args.username:
            parser.error("add 需要用户名")
        password = getpass.getpass("密码：")
        if len(password) < 6:
            parser.error("密码至少 6 位")
        add_user(Path(args.data_dir), args.username, password)
        print(f"已添加账号：{args.username}")
    else:
        for name in store.users():
            print(name)


if __name__ == "__main__":
    main()

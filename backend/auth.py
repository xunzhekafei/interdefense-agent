# -*- coding: utf-8 -*-
"""账号密码登录：只为「把作品部署出去给评审用」这一件事服务。

不追求完整的用户系统：

- 账号存 `<data_dir>/auth.json`，密码用 PBKDF2-HMAC-SHA256 加盐哈希
- 登录后发一个 HMAC 签名的会话 cookie（HttpOnly、SameSite=Lax、7 天）
- **没有 auth.json 时默认关闭鉴权**，本地开发和测试行为完全不变
- 用 `python -m backend.auth add <用户名>` 添加账号（交互式输入密码）

登出必须让已发出的 cookie 失效：每个账号在 auth.json 里带一个 token 版本号，
登出时把版本加一；旧 cookie 的版本对不上，随即作废（同账号其他设备也会下线）。

连续登录失败按「客户端 IP」与「IP + 用户名」各计一次，5 次后锁 60 秒，
之后逐次翻倍，上限 15 分钟。纯内存计数，重启服务清零——评审场景够用，也不会写爆磁盘。

数据目录默认 `.web-data/`，已被 gitignore；`auth.json` 和 `auth_secret`
也在那里，不会进仓库。
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path

from settings import env_int

logger = logging.getLogger(__name__)

COOKIE = "interview_session"
TTL_SECONDS = env_int("AUTH_TTL_DAYS", 7) * 86400
PBKDF2_ROUNDS = 200_000

# 登录限流：第 5 次失败开始锁 60 秒，再失败逐次翻倍，最多 15 分钟
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 60
LOGIN_MAX_LOCK_SECONDS = 900


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _chmod_private(path: Path) -> None:
    """POSIX 上把含密码哈希/签名密钥的文件收紧到仅所有者可读写。"""
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        logger.warning("无法设置 %s 的权限，请手动 chmod 600", path)


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
        # HTTP 线程池会并发读；写 auth.json（加账号/登出）必须串行。
        self._lock = threading.RLock()
        self._users_cache: dict | None = None
        self._users_mtime: int | None = None
        # key = "客户端 IP:用户名"，value = {"count": int, "locked_until": float}
        self._failures: dict[str, dict] = {}
        # 升级前创建的 auth.json / auth_secret 可能是 644，启动时顺手收紧。
        for path in (self.path, self.secret_path):
            if path.is_file():
                _chmod_private(path)

    # ---- 账号 ----

    def enabled(self) -> bool:
        """有账号文件才启用鉴权；没有就保持本地无登录模式。"""
        return self.path.is_file()

    def _read_users(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            stat = self.path.stat()
            if (self._users_cache is not None
                    and self._users_mtime == stat.st_mtime_ns):
                return self._users_cache
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        users = data.get("users") if isinstance(data, dict) else None
        users = users if isinstance(users, dict) else {}
        self._users_cache = users
        self._users_mtime = stat.st_mtime_ns
        return users

    def _write_users(self, users: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"users": users}, ensure_ascii=False, indent=2)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        _chmod_private(temporary)
        os.replace(temporary, self.path)
        _chmod_private(self.path)
        self._users_cache = users
        self._users_mtime = self.path.stat().st_mtime_ns

    def users(self) -> dict:
        if not self.enabled():
            return {}
        with self._lock:
            return dict(self._read_users())

    def set_user(self, username: str, password: str) -> None:
        """新增或重置账号；重置密码同时让该账号已签发的 cookie 失效。"""
        with self._lock:
            users = dict(self._read_users())
            user = users.get(username)
            version = int(user.get("version") or 0) if isinstance(user, dict) else 0
            users[username] = {**hash_password(password), "version": version + 1}
            self._write_users(users)

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

    def _version(self, username: str) -> int:
        with self._lock:
            user = self._read_users().get(username)
            if not isinstance(user, dict):
                return 0
            try:
                return int(user.get("version") or 0)
            except (TypeError, ValueError):
                return 0

    # ---- 登录限流 ----

    def blocked(self, key: str, now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        with self._lock:
            record = self._failures.get(key)
            return bool(record and moment < record.get("locked_until", 0))

    def record_failure(self, key: str, now: float | None = None) -> int:
        moment = time.time() if now is None else now
        with self._lock:
            record = self._failures.setdefault(key, {"count": 0, "locked_until": 0.0})
            record["count"] += 1
            if record["count"] >= LOGIN_MAX_FAILURES:
                penalty = min(LOGIN_MAX_LOCK_SECONDS,
                              LOGIN_LOCK_SECONDS * 2 ** (record["count"] - LOGIN_MAX_FAILURES))
                record["locked_until"] = moment + penalty
            return record["count"]

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

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
            _chmod_private(self.secret_path)
            self._secret_cache = secret
        return self._secret_cache

    def _parse(self, token: str | None, check_exp: bool = True) -> dict | None:
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
        if not isinstance(data, dict):
            return None
        if check_exp and int(data.get("exp", 0)) < time.time():
            return None
        return data

    def issue(self, username: str) -> str:
        payload = _b64(json.dumps(
            {"u": username, "exp": int(time.time()) + TTL_SECONDS,
             "v": self._version(username)},
            ensure_ascii=False).encode())
        signature = _b64(hmac.new(self._secret(), payload.encode(), hashlib.sha256).digest())
        return f"{payload}.{signature}"

    def check(self, token: str | None) -> str | None:
        data = self._parse(token)
        if data is None:
            return None
        username = str(data.get("u") or "")
        if not username:
            return None
        try:
            version = int(data.get("v") or 0)
        except (TypeError, ValueError):
            version = 0
        if version != self._version(username):
            return None
        return username

    def revoke(self, token: str | None) -> bool:
        """登出：让这个 token（以及同账号其它 cookie）立即失效。"""
        data = self._parse(token, check_exp=False)
        if data is None:
            return False
        username = str(data.get("u") or "")
        if not username:
            return False
        with self._lock:
            users = dict(self._read_users())
            user = users.get(username)
            if not isinstance(user, dict):
                return False
            user["version"] = self._version(username) + 1
            self._write_users(users)
            return True


def add_user(data_dir: Path, username: str, password: str) -> None:
    AuthStore(Path(data_dir)).set_user(username, password)


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
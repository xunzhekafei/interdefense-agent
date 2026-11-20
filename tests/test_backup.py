"""备份/恢复回归：一致快照、账号文件、保留策略、恢复回退。"""
import os

import pytest

from backend.auth import AuthStore, add_user
from backend.sessions import SessionStore
from tools.backup import backup, restore


def _session(session_id, created="2026-01-01"):
    return {"id": session_id, "candidate": "甲", "role": "AI",
            "created_at": created, "status": "ready",
            "messages": [], "report": None, "seq": 0}


def test_backup_and_restore_roundtrip(tmp_path):
    data = tmp_path / ".web-data"
    store = SessionStore(data / "interviews.sqlite3")
    store.save(_session("s1"))
    store.close()
    add_user(data, "alice", "secret123")
    AuthStore(data).issue("alice")

    folder = backup(data, keep=2)
    assert (folder / "interviews.sqlite3").is_file()
    assert (folder / "auth.json").is_file()
    assert (folder / "auth_secret").is_file()

    # 备份之后新增一场；恢复后应该回到备份时点。
    store = SessionStore(data / "interviews.sqlite3")
    store.save(_session("s2"))
    store.close()

    restore(folder, data)
    store = SessionStore(data / "interviews.sqlite3")
    try:
        assert {item["id"] for item in store.summaries()} == {"s1"}
    finally:
        store.close()
    # 恢复前的库被另存，误恢复可回退。
    assert list(data.glob("interviews.sqlite3.pre-restore-*"))


def test_backup_keeps_only_requested_count(tmp_path):
    data = tmp_path / ".web-data"
    store = SessionStore(data / "interviews.sqlite3")
    store.save(_session("s1"))
    store.close()

    for _ in range(3):
        backup(data, keep=2)

    folders = [path for path in (data / "backups").iterdir() if path.is_dir()]
    assert len(folders) == 2


@pytest.mark.skipif(os.name != "posix", reason="Windows 没有 POSIX 权限位")
def test_backup_and_auth_files_are_private(tmp_path):
    data = tmp_path / ".web-data"
    store = SessionStore(data / "interviews.sqlite3")
    store.save(_session("s1"))
    store.close()
    add_user(data, "alice", "secret123")
    AuthStore(data).issue("alice")

    folder = backup(data, keep=2)
    assert (folder / "interviews.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (folder / "auth.json").stat().st_mode & 0o777 == 0o600
    assert (folder / "auth_secret").stat().st_mode & 0o777 == 0o600
    assert folder.stat().st_mode & 0o777 == 0o700


def test_restore_rejects_broken_backup(tmp_path):
    data = tmp_path / ".web-data"
    store = SessionStore(data / "interviews.sqlite3")
    store.save(_session("s1"))
    store.close()

    broken = tmp_path / "broken.sqlite3"
    broken.write_bytes(b"not a database")
    with pytest.raises(ValueError):
        restore(broken, data)
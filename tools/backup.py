# -*- coding: utf-8 -*-
"""备份 / 恢复 Web 版数据。

    python tools/backup.py                          # 备份到 .web-data/backups/<时间戳>/
    python tools/backup.py --keep 14                # 保留最近 14 份
    python tools/backup.py --restore .web-data/backups/20261110-120000

备份包含 SQLite 的一致快照（用 backup API，不是直接 cp）、`auth.json` 与
`auth_secret`（存在时）。备份目录在 POSIX 上设为 0700，文件 0600；
整个 `.web-data` 已被 gitignore，不要上传备份。

恢复前必须先停服务；脚本会校验备份完整性，并把当前库另存为
`interviews.sqlite3.pre-restore-<时间戳>`，恢复错了还能回退。
"""
import argparse
import logging
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_NAME = "interviews.sqlite3"
AUTH_FILES = ("auth.json", "auth_secret")


def _private(path: Path, mode: int) -> None:
    """POSIX 上收紧权限；Windows 没有对应权限位，跳过。"""
    if os.name != "posix":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        logger.warning("无法设置 %s 的权限，请手动 chmod %o", path, mode)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup(data_dir: Path, keep: int = 7) -> Path:
    """生成一份一致快照，返回备份目录。"""
    data_dir = Path(data_dir)
    source_db = data_dir / DB_NAME
    if not source_db.is_file():
        raise FileNotFoundError(f"找不到数据库：{source_db}")

    backup_root = data_dir / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    _private(backup_root, 0o700)

    stamp = _stamp()
    folder = backup_root / stamp
    suffix = 1
    while folder.exists():                 # 同一秒内多次备份
        folder = backup_root / f"{stamp}-{suffix}"
        suffix += 1
    folder.mkdir(parents=True)
    _private(folder, 0o700)

    target_db = folder / DB_NAME
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(target_db)
        try:
            source.backup(target)          # 包含 WAL 中已提交的数据
        finally:
            target.close()
    finally:
        source.close()
    _private(target_db, 0o600)

    for name in AUTH_FILES:
        candidate = data_dir / name
        if candidate.is_file():
            copied = folder / name
            shutil.copy2(candidate, copied)
            _private(copied, 0o600)

    _prune(backup_root, keep)
    return folder


def _prune(backup_root: Path, keep: int) -> None:
    if keep <= 0:
        return
    folders = sorted((path for path in backup_root.iterdir() if path.is_dir()),
                     key=lambda path: path.name)
    for old in folders[:-keep]:
        shutil.rmtree(old, ignore_errors=False)


def restore(backup_dir: Path, data_dir: Path) -> Path:
    """用备份覆盖当前库；调用前请确保服务已停止。返回恢复后的数据库路径。"""
    backup_dir = Path(backup_dir)
    data_dir = Path(data_dir)
    source_db = backup_dir / DB_NAME if backup_dir.is_dir() else backup_dir
    if not source_db.is_file():
        raise FileNotFoundError(f"找不到备份数据库：{source_db}")

    check = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as error:
        raise ValueError(f"备份不是有效的 SQLite 文件：{error}") from error
    finally:
        check.close()
    if result != "ok":
        raise ValueError(f"备份损坏，拒绝恢复：{result}")

    data_dir.mkdir(parents=True, exist_ok=True)
    target_db = data_dir / DB_NAME
    if target_db.exists():
        kept = data_dir / f"{DB_NAME}.pre-restore-{_stamp()}"
        shutil.copy2(target_db, kept)
        _private(kept, 0o600)

    # 旧的 WAL/SHM 属于恢复前的库，必须移除，否则会被旧日志覆盖。
    for suffix in ("-wal", "-shm"):
        stale = data_dir / f"{DB_NAME}{suffix}"
        if stale.exists():
            stale.unlink()

    shutil.copy2(source_db, target_db)
    _private(target_db, 0o600)

    if backup_dir.is_dir():
        for name in AUTH_FILES:
            candidate = backup_dir / name
            if candidate.is_file():
                shutil.copy2(candidate, data_dir / name)
                _private(data_dir / name, 0o600)
    return target_db


def main():
    parser = argparse.ArgumentParser(description="备份 / 恢复 Web 版数据")
    parser.add_argument("--data-dir", default=".web-data", help="数据目录（默认 .web-data）")
    parser.add_argument("--keep", type=int, default=7, help="保留最近几份备份（默认 7）")
    parser.add_argument("--restore", metavar="DIR", help="从指定备份目录恢复（先停服务）")
    args = parser.parse_args()

    if args.restore:
        target = restore(Path(args.restore), Path(args.data_dir))
        print(f"已恢复：{target}")
    else:
        folder = backup(Path(args.data_dir), args.keep)
        print(f"已备份到：{folder}")


if __name__ == "__main__":
    main()
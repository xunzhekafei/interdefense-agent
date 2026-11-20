"""Durable session snapshots and an ordered event log, independent of CLI state."""
import json
import sqlite3
import threading
from pathlib import Path

# 库结构版本：新增列/表时递增；旧库在打开时自动补齐。
SCHEMA_VERSION = 1

# 列表页只需要这些字段；完整问答和报告留在 payload 里，按需读取。
SUMMARY_FIELDS = ("id", "candidate", "role", "created_at", "status",
                  "mode", "rounds", "pressure")


def _summary(session):
    summary = {key: session.get(key) for key in SUMMARY_FIELDS}
    summary["mode"] = session.get("mode") or "text"
    summary["rounds"] = session.get("rounds") or 15
    return summary


class SessionStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                summary TEXT, report TEXT);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_session ON events(session_id, seq);
        """)
        # 旧库没有 summary / report 列：就地补齐，旧行读取时回退解析 payload。
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(sessions)")}
        for name in ("summary", "report"):
            if name not in columns:
                self.db.execute(f"ALTER TABLE sessions ADD COLUMN {name} TEXT")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"数据库版本 {version} 高于当前代码支持的 {SCHEMA_VERSION}")
        if version < SCHEMA_VERSION:
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.db.commit()

    def schema_version(self) -> int:
        with self.lock:
            return int(self.db.execute("PRAGMA user_version").fetchone()[0])

    def save(self, session, event_type=None, data=None, turn_id=None):
        with self.lock, self.db:
            event = None
            if event_type:
                event = dict(type=event_type, session_id=session["id"], turn_id=turn_id, data=data or {})
                cursor = self.db.execute("INSERT INTO events(session_id,payload) VALUES (?,?)",
                                         (session["id"], json.dumps(event, ensure_ascii=False)))
                session["seq"] = cursor.lastrowid
                event["seq"] = cursor.lastrowid
            report = session.get("report")
            self.db.execute(
                "INSERT OR REPLACE INTO sessions(id,payload,summary,report) VALUES (?,?,?,?)",
                (session["id"], json.dumps(session, ensure_ascii=False),
                 json.dumps(_summary(session), ensure_ascii=False),
                 json.dumps(report, ensure_ascii=False) if report is not None else None))
            return event

    def get(self, session_id):
        with self.lock:
            row = self.db.execute("SELECT payload FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise KeyError(session_id)
            return json.loads(row[0])

    def exists(self, session_id):
        with self.lock:
            return self.db.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone() is not None

    def list(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM sessions ORDER BY rowid DESC")]

    def summaries(self):
        """列表页/删除校验用的轻量视图：不解析完整问答和报告。"""
        with self.lock:
            rows = self.db.execute(
                "SELECT summary, payload FROM sessions ORDER BY rowid DESC").fetchall()
        return [json.loads(summary) if summary else _summary(json.loads(payload))
                for summary, payload in rows]

    def list_reports(self):
        """成长画像只关心报告本身；返回摘要 + report，仍不解析 messages。"""
        with self.lock:
            rows = self.db.execute(
                "SELECT summary, report, payload FROM sessions ORDER BY rowid DESC").fetchall()
        result = []
        for summary, report, payload in rows:
            if summary:
                item = json.loads(summary)
                item["report"] = json.loads(report) if report is not None else None
            else:
                session = json.loads(payload)
                item = _summary(session)
                item["report"] = session.get("report")
            result.append(item)
        return result

    def delete(self, session_id):
        """删除场次快照和它的全部事件。返回是否真的删掉了。"""
        with self.lock, self.db:
            cursor = self.db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            self.db.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            return cursor.rowcount > 0

    def events(self, session_id, after):
        with self.lock:
            rows = self.db.execute("SELECT seq,payload FROM events WHERE session_id=? AND seq>? ORDER BY seq LIMIT 200",
                                   (session_id, after)).fetchall()
            return [{**json.loads(payload), "seq": seq} for seq, payload in rows]

    def prune_events(self, session_id, keep=200):
        """只保留每场最近 keep 条事件。

        新版每个回合只写几条聚合事件；旧版每个 token 一行，长面试能把 events 表撑到
        几万行。重连靠快照恢复，不依赖历史增量，因此清理是安全的。
        """
        with self.lock, self.db:
            cursor = self.db.execute(
                "DELETE FROM events WHERE session_id=? AND seq NOT IN "
                "(SELECT seq FROM events WHERE session_id=? ORDER BY seq DESC LIMIT ?)",
                (session_id, session_id, keep))
            return cursor.rowcount

    def prune_all_events(self, keep=200):
        """启动时收敛历史膨胀：每场只保留最近 keep 条事件。

        所有场次共用一个事务，避免启动时每场单独提交一次。
        """
        with self.lock, self.db:
            session_ids = [row[0] for row in self.db.execute("SELECT id FROM sessions")]
            removed = 0
            for session_id in session_ids:
                cursor = self.db.execute(
                    "DELETE FROM events WHERE session_id=? AND seq NOT IN "
                    "(SELECT seq FROM events WHERE session_id=? ORDER BY seq DESC LIMIT ?)",
                    (session_id, session_id, keep))
                removed += cursor.rowcount
            return removed

    def close(self):
        self.db.close()
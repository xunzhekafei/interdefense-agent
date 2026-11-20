"""流式链路回归：增量不逐条落库，但推送、快照和最终状态必须一致。"""
import asyncio
import json
import socket
import threading
import time

import pytest

from backend.app import create_app
from backend.service import InterviewService


def _event_loop_supported():
    """受限沙箱会拦截 socketpair，事件循环起不来；此时跳过端到端 WS 用例。"""
    try:
        left, right = socket.socketpair()
    except OSError:
        return False
    left.close()
    right.close()
    return True


class ShortAgent:
    def configured(self):
        return True

    def reply(self, session, emit, cancel, directory=None):
        text = f"{session['candidate']}，请介绍你的项目。"
        for char in text:
            emit("reply.delta", {"text": char})
        return text


class StreamAgent:
    def configured(self):
        return True

    def reply(self, session, emit, cancel, directory=None):
        for _ in range(2000):
            emit("reply.delta", {"text": "字"})
        return "字" * 2000


class BlockingAgent:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def configured(self):
        return True

    def reply(self, session, emit, cancel, directory=None):
        emit("reply.delta", {"text": "半句"})
        self.started.set()
        assert self.release.wait(5)
        return "半句完成"


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.incoming = asyncio.Queue()
        self.headers = {}
        self.cookies = {}
        self.closed_code = None

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_text(self):
        return await self.incoming.get()

    async def close(self, code=1000, reason=None):
        self.closed_code = code


async def wait_until(predicate, timeout=5):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return False


@pytest.mark.skipif(not _event_loop_supported(), reason="沙箱禁止事件循环自管道")
def test_websocket_pushes_delta_then_authoritative_snapshot(tmp_path):
    """WS 事件驱动：连上先拿快照，之后按增量推送，终态再发权威快照。"""

    async def scenario():
        app = create_app(tmp_path, ShortAgent(), recognizer=None)
        async with app.router.lifespan_context(app):
            sid = app.state.service.create("甲", "AI", "")["id"]
            route = next(route for route in app.router.routes
                         if getattr(route, "path", "") == "/api/sessions/{session_id}/ws")
            ws = FakeSocket()
            task = asyncio.create_task(route.endpoint(ws, sid))
            try:
                assert await wait_until(lambda: bool(ws.sent))
                assert ws.sent[0]["type"] == "session.snapshot"
                ws.incoming.put_nowait(json.dumps({
                    "action": "start", "text": "", "request_id": "r" * 8,
                    "input_mode": "text"}))
                stopped = lambda: any(  # noqa: E731
                    event["type"] == "session.snapshot"
                    and event["data"]["active_turn"] is None
                    and event["data"]["messages"] for event in ws.sent)
                assert await wait_until(stopped)
                deltas = [event for event in ws.sent if event["type"] == "reply.delta"]
                assert deltas
                assert "".join(event["data"]["text"] for event in deltas) == "甲，请介绍你的项目。"
                # 快照只在连接、提交确认和终态出现，不再每个增量重发全量。
                assert len([e for e in ws.sent if e["type"] == "session.snapshot"]) < 10
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def wait_done(service, session_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = service.store.get(session_id)
        if not session["active_turn"]:
            return session
        time.sleep(0.005)
    raise AssertionError("turn did not finish")


def test_stream_deltas_are_batched_not_persisted_one_by_one(tmp_path):
    service = InterviewService(tmp_path, StreamAgent())
    try:
        sid = service.create("甲", "AI", "")["id"]
        saves = []
        original = service.store.save
        service.store.save = lambda *args, **kwargs: (saves.append(args), original(*args, **kwargs))[1]
        events = []
        stop = service.listen(sid, events.append)
        try:
            service.submit(sid, action="start", request_id="r" * 8)
            session = wait_done(service, sid)
        finally:
            stop()

        assert len(session["messages"][-1]["text"]) == 2000
        # 2000 个增量只落库个位数次；之前是每个增量一次整场写入。
        assert len(saves) <= 10
        deltas = [event for event in events if event["type"] == "reply.delta"]
        assert 1 <= len(deltas) <= 40
        assert "".join(event["data"]["text"] for event in deltas) == "字" * 2000
        snapshots = [event for event in events if event["type"] == "session.snapshot"]
        assert snapshots and snapshots[-1]["data"]["active_turn"] is None
        rows = service.store.db.execute(
            "SELECT count(*) FROM events WHERE session_id=?", (sid,)).fetchone()[0]
        assert rows <= 10
    finally:
        service.close()


def test_snapshot_exposes_in_flight_text_before_persist(tmp_path):
    agent = BlockingAgent()
    service = InterviewService(tmp_path, agent)
    try:
        sid = service.create("甲", "AI", "")["id"]
        service.submit(sid, action="start", request_id="r" * 8)
        assert agent.started.wait(5)
        # 几十毫秒内的增量还没落库，刷新页面仍应看到它。
        assert service.snapshot(sid)["messages"][-1]["text"] == "半句"
        agent.release.set()
        wait_done(service, sid)
    finally:
        agent.release.set()
        service.close()


def test_summaries_and_reports_skip_message_payload(tmp_path):
    service = InterviewService(tmp_path, StreamAgent())
    try:
        sid = service.create("甲", "AI", "")["id"]
        session = service.store.get(sid)
        session["messages"] = [{
            "id": "m", "turn_id": "t", "role": "user", "text": "x" * 1000,
            "status": "completed", "input_mode": "text"}]
        session["report"] = {"overall": 8, "dimension_scores": {}}
        service.store.save(session)

        summary = service.store.summaries()[0]
        assert summary["id"] == sid and "messages" not in summary
        assert summary["candidate"] == "甲"

        full = service.store.list_reports()[0]
        assert full["report"]["overall"] == 8 and "messages" not in full
    finally:
        service.close()

def test_store_migrates_old_schema(tmp_path):
    """旧库只有 id/payload：新增列要就地补上，旧行读取时回退解析。"""
    import json
    import sqlite3

    from backend.sessions import SessionStore

    path = tmp_path / "interviews.sqlite3"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                             session_id TEXT NOT NULL, payload TEXT NOT NULL);
    """)
    session = {"id": "s1", "candidate": "甲", "role": "AI", "created_at": "2026-01-01",
               "status": "ready", "messages": [], "report": None, "seq": 0}
    db.execute("INSERT INTO sessions VALUES (?,?)", ("s1", json.dumps(session)))
    db.commit()
    db.close()

    store = SessionStore(path)
    try:
        assert store.summaries()[0]["candidate"] == "甲"
        assert store.get("s1")["id"] == "s1"
        store.save(dict(session, status="completed", report={"overall": 8}))
        assert store.list_reports()[0]["report"]["overall"] == 8
    finally:
        store.close()

def test_store_schema_version_and_event_pruning(tmp_path):
    from backend.sessions import SCHEMA_VERSION, SessionStore

    store = SessionStore(tmp_path / "interviews.sqlite3")
    try:
        assert store.schema_version() == SCHEMA_VERSION
        session = {"id": "s1", "candidate": "甲", "role": "AI",
                   "created_at": "2026-01-01", "status": "ready",
                   "messages": [], "report": None, "seq": 0}
        store.save(session)
        for _ in range(300):
            store.save(session, "reply.delta", {"text": "x"})

        assert store.prune_events("s1", keep=50) == 250
        rows = store.events("s1", 0)
        assert len(rows) == 50
        assert rows[-1]["seq"] == session["seq"]   # 保留的是最新事件
    finally:
        store.close()

def test_store_prunes_all_sessions(tmp_path):
    """启动时统一收敛旧库：每场只保留最近 keep 条事件。"""
    from backend.sessions import SessionStore

    store = SessionStore(tmp_path / "interviews.sqlite3")
    try:
        for session_id in ("a", "b"):
            session = {"id": session_id, "candidate": "甲", "role": "AI",
                       "created_at": "2026-01-01", "status": "completed",
                       "messages": [], "report": None, "seq": 0}
            store.save(session)
            for _ in range(300):
                store.save(session, "reply.delta", {"text": "x"})

        assert store.prune_all_events(keep=50) == 500
        assert len(store.events("a", 0)) == 50
        assert len(store.events("b", 0)) == 50
    finally:
        store.close()
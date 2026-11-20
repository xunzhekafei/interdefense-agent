"""One local execution queue; session data and cancellation stay independent."""
import copy
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from interview_spec import DEFAULT_ROUNDS, classify_answer

from .agent_adapter import InterviewAgent
from .sessions import SessionStore

# 流式增量不再逐条落库：攒到时间窗口或字符阈值再写。
# 推送和落库拆成两条线——推送保持流畅，落库只为崩溃后可恢复。
PUSH_INTERVAL = 0.05
PUSH_CHARS = 120
SAVE_INTERVAL = 1.0
SAVE_CHARS = 4000


def now():
    return datetime.now(timezone.utc).isoformat()


def public_error(error):
    """Do not forward SDK response bodies (which may contain credentials) to browsers."""
    name = type(error).__name__
    if name == "AuthenticationError":
        return "模型服务鉴权失败（401）。请检查后端 ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN 是否为当前提供商的密钥，然后重启服务。"
    if name == "RateLimitError":
        return "模型服务请求过于频繁，请稍后重试。已保留问答记录。"
    if name in ("APIConnectionError", "APITimeoutError"):
        return "暂时无法连接模型服务或请求超时，请检查网络后重试。已保留问答记录。"
    return "本轮处理失败，请检查后端日志后重试。已保留问答记录。"


class TurnState:
    """One in-flight turn. The session lives in memory for the whole turn.

    以前每个增量都要从 SQLite 读整场、改一个字符、再整场写回并提交；会话越大越慢。
    现在文本只改内存、按窗口推送，落库降到每秒一次，重连快照仍然是最新内容。
    """

    def __init__(self, session, turn_id, cancel):
        self.session = session
        self.turn_id = turn_id
        self.cancel = cancel
        self.pending_push = ""
        self.pending_save = ""
        self.last_push = time.monotonic()
        self.last_save = time.monotonic()
        self.deleted = False


class InterviewService:
    def __init__(self, directory: Path, adapter=None):
        self.directory = directory
        self.store = SessionStore(directory / "interviews.sqlite3")
        self.adapter = adapter or InterviewAgent()
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="interview")
        # 笔记更新单独一个线程：不能挡住下一轮，也不该让用户等它跑完
        self.memory_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory")
        self.cancels = {}
        self.runs = {}
        self.listeners = {}
        # No process-local job survives a restart; retain partial output for review.
        for session in self.store.list():
            if session["active_turn"]:
                self._interrupt(session, "服务已重启，本轮未完成。可重试。")
        # 旧版本每个 token 一行事件；启动时一次性收敛，避免库无限增长。
        self.store.prune_all_events(200)

    # ---- 实时订阅 ----

    def listen(self, session_id, callback):
        """注册一个事件回调（在回合线程里调用）。返回取消订阅的函数。"""
        with self.lock:
            self.listeners.setdefault(session_id, set()).add(callback)

        def stop():
            with self.lock:
                callbacks = self.listeners.get(session_id)
                if callbacks is not None:
                    callbacks.discard(callback)
                    if not callbacks:
                        self.listeners.pop(session_id, None)

        return stop

    def _publish(self, session_id, event):
        with self.lock:
            callbacks = list(self.listeners.get(session_id, ()))
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                logging.getLogger(__name__).debug("实时事件推送失败", exc_info=True)

    def _publish_snapshot(self, session):
        self._publish(session["id"], {
            "type": "session.snapshot", "seq": session.get("seq", 0),
            "data": copy.deepcopy(session)})

    def snapshot(self, session_id):
        """连接/刷新时取最新状态；回合进行中优先返回内存态（可能比库里新几十毫秒）。"""
        with self.lock:
            session = self.store.get(session_id)
            turn_id = session.get("active_turn")
            run = self.runs.get(turn_id) if turn_id else None
            if run is not None and not run.deleted and run.session["id"] == session_id:
                return copy.deepcopy(run.session)
            return session

    # ---- 回合内增量 ----

    def _push_delta(self, run):
        """把攒下的增量合并成一条事件推给前端。"""
        if not run.pending_push:
            return
        text = run.pending_push
        run.pending_push = ""
        run.last_push = time.monotonic()
        self._publish(run.session["id"], {
            "type": "reply.delta", "session_id": run.session["id"],
            "turn_id": run.turn_id, "seq": run.session.get("seq", 0),
            "data": {"text": text}})

    def _save_delta(self, run):
        """只把新增文本作为一条聚合事件落库，供崩溃恢复与审计。"""
        if not run.pending_save:
            return
        text = run.pending_save
        run.pending_save = ""
        run.last_save = time.monotonic()
        self.store.save(run.session, "reply.delta", {"text": text})

    # ---- 场次操作 ----

    def create(self, candidate, role, background, pressure="标准", mode="text",
               rounds=DEFAULT_ROUNDS):
        session = dict(id=uuid.uuid4().hex, candidate=candidate, role=role, background=background,
                       pressure=pressure, mode=mode, rounds=rounds, created_at=now(),
                       status="ready", active_turn=None, messages=[], report=None, seq=0,
                       error=None, last_action=None, requests=[])
        self.store.save(session)
        return session

    def _interrupt(self, session, reason, event_type="turn.cancelled", turn_id=None):
        turn_id = turn_id or session["active_turn"]
        for message in session["messages"]:
            if message["turn_id"] == turn_id and message["status"] == "streaming":
                message["status"] = "interrupted"
        session.update(status="ready", active_turn=None, error=reason)
        self.store.save(session, event_type, {"message": reason}, turn_id)
        self._publish_snapshot(session)

    def delete(self, session_id):
        """删掉一场面试。

        正在跑的回合先取消——worker 收尾时会发现场次已经不在，安全退出，
        不会把已删除的场次又写回去。内存态也要一起移除，否则收尾会把旧数据写回来。
        """
        with self.lock:
            session = self.store.get(session_id)      # 不存在时抛 KeyError
            turn_id = session.get("active_turn")
            if turn_id:
                cancel = self.cancels.get(turn_id)
                if cancel is not None:
                    cancel.set()
                run = self.runs.pop(turn_id, None)
                if run is not None:
                    run.deleted = True
                self.cancels.pop(turn_id, None)
            self.store.delete(session_id)
            self.listeners.pop(session_id, None)

    def submit(self, session_id, action, text="", request_id="", input_mode="text"):
        with self.lock:
            session = self.store.get(session_id)
            if request_id in session["requests"]:
                return session  # At-most-once submission on client reconnect.
            if action == "cancel":
                session["requests"].append(request_id)
                turn_id = session.get("active_turn")
                if turn_id:
                    cancel = self.cancels.get(turn_id)
                    if cancel is not None:
                        cancel.set()
                    run = self.runs.get(turn_id)
                    if run is not None and not run.deleted:
                        run.session["requests"] = session["requests"]
                        session = run.session
                    self._interrupt(session, "本轮已取消，可重试。")
                else:
                    self.store.save(session)
                    self._publish_snapshot(session)
                return self.store.get(session_id)
            if session["active_turn"]:
                raise ValueError("当前场次仍在处理，请等待或取消本轮")
            if session["status"] == "completed":
                raise ValueError("这场面试已完成，请新建面试")
            if not self.adapter.configured():
                raise ValueError("未配置模型密钥，请设置 ANTHROPIC_API_KEY 后重启后端")
            retry = action == "retry"
            if retry:
                if not session["error"] or not session["last_action"]:
                    raise ValueError("没有可重试的轮次")
                action = session["last_action"]
            elif action == "start":
                if session["messages"]:
                    raise ValueError("面试已经开始，请继续回答")
            elif action == "answer":
                if not any(m["role"] == "assistant" and m["status"] == "completed" for m in session["messages"]):
                    raise ValueError("请先开始面试")
                if not text.strip() or len(text) > 12000:
                    raise ValueError("回答需为 1–12000 个字符")
                # Finishing is a host action, not a model-selected file workflow.
                if text.strip() in ("结束面试", "不面了"):
                    action = "finish"
                # 误触/复制题目/只发问候：挡在提交前，别让它变成一轮 0 分。
                # 反问环节不挡——候选人反问什么都可以，报告里会跳过。
                if action == "answer" and not retry:
                    question = next((m["text"] for m in reversed(session["messages"])
                                     if m["role"] == "assistant"
                                     and m["status"] == "completed"), "")
                    kind = classify_answer(question, text)
                    if kind in ("copy", "empty", "greeting"):
                        raise ValueError({
                            "copy": "这段回答和面试官的问题几乎一样，可能是误触。请直接回答上面的问题。",
                            "empty": "回答不能为空。",
                            "greeting": "这只是问候，请直接回答上面的问题。",
                        }[kind])
            elif action != "finish":
                raise ValueError("不支持的操作")
            if action == "finish" and not any(m["role"] == "user" for m in session["messages"]):
                raise ValueError("至少回答一次后才能生成报告")
            turn_id = uuid.uuid4().hex
            cancel = threading.Event()
            self.cancels[turn_id] = cancel
            # Retry retains the original user answer; never inserts it a second time.
            if action == "answer" and not retry:
                self._add_message(session, turn_id, "user", text.strip(), "completed", input_mode)
            if action != "finish":
                self._add_message(session, turn_id, "assistant", "", "streaming")
            session.update(active_turn=turn_id, status="scoring" if action == "finish" else "running",
                           error=None, last_action=action)
            session["requests"].append(request_id)
            self.store.save(session, "turn.started", {"action": action}, turn_id)
            # 只传场次 id：worker 自己读一次最新快照，避免每次提交复制整场问答。
            self.executor.submit(self._run, session["id"], action, turn_id, cancel)
            return session

    @staticmethod
    def _add_message(session, turn_id, role, text, status, input_mode="text"):
        # input_mode 只在候选人消息上有意义：面试官的话永远是文字。
        # 它由客户端声明、服务端无法核实——但作为「这条是语音转写的，术语拼写别太当真」
        # 的提示足够用了。见 agent.VOICE_MARK。
        session["messages"].append(dict(id=uuid.uuid4().hex, turn_id=turn_id, role=role, text=text,
                                        status=status, input_mode=input_mode, created_at=now()))

    def _run(self, session_id, action, turn_id, cancel):
        with self.lock:
            try:
                session = self.store.get(session_id)
            except KeyError:
                return
            if session.get("active_turn") != turn_id or cancel.is_set():
                return
            run = TurnState(session, turn_id, cancel)
            self.runs[turn_id] = run

        def emit(event_type, data):
            with self.lock:
                current = self.runs.get(turn_id)
                if (current is None or current.deleted or cancel.is_set()
                        or current.session.get("active_turn") != turn_id):
                    raise InterruptedError("轮次已取消")
                if event_type == "reply.delta":
                    text = data.get("text", "")
                    current.session["messages"][-1]["text"] += text
                    current.pending_push += text
                    current.pending_save += text
                    stamp = time.monotonic()
                    if (len(current.pending_push) >= PUSH_CHARS
                            or stamp - current.last_push >= PUSH_INTERVAL):
                        self._push_delta(current)
                    if (len(current.pending_save) >= SAVE_CHARS
                            or stamp - current.last_save >= SAVE_INTERVAL):
                        self._save_delta(current)
                else:
                    # 展示类事件（工具进度、报告进度）直接推送，不占用落库。
                    self._publish(current.session["id"], {
                        "type": event_type, "session_id": current.session["id"],
                        "turn_id": turn_id, "seq": current.session.get("seq", 0),
                        "data": data or {}})

        try:
            if cancel.is_set():
                return
            if action == "finish":
                result = self.adapter.report(run.session, emit, cancel, self.directory / session_id)
            else:
                result = self.adapter.reply(run.session, emit, cancel, self.directory / session_id)
            with self.lock:
                current = self.runs.get(turn_id)
                if current is None or current.deleted:
                    return                    # 场次已被删除，别再写回去
                if cancel.is_set() or current.session.get("active_turn") != turn_id:
                    return
                self._push_delta(current)
                session = current.session
                if action == "finish":
                    session["report"] = result
                    session["status"] = "completed"
                    self.store.save(session, "report.completed", {"report": result}, turn_id)
                else:
                    message = session["messages"][-1]
                    message["text"] = message["text"] or result
                    if not message["text"].strip():
                        raise ValueError("模型没有返回文字，请重试")
                    message["status"] = "completed"
                    session["status"] = "ready"
                    self.store.save(session, "reply.completed", {"text": message["text"]}, turn_id)
                session["active_turn"] = None
                self.store.save(session, "turn.completed", {}, turn_id)
                self.store.prune_events(session_id)
                self._publish_snapshot(session)
                # 本轮已经对用户结束了。笔记在后台更新，下一轮开始前基本能赶上；
                # 赶不上就晚一轮，不影响面试本身。
                if action != "finish":
                    self.memory_executor.submit(self._refresh_memory, session_id)
        except InterruptedError:
            with self.lock:
                current = self.runs.get(turn_id)
                if current is None or current.deleted:
                    return
                if current.session.get("active_turn") == turn_id:
                    self._push_delta(current)
                    self._interrupt(current.session, "本轮已取消，可重试。")
        except Exception as error:
            logging.getLogger(__name__).exception("Interview turn failed: %s", turn_id)
            with self.lock:
                current = self.runs.get(turn_id)
                if current is None or current.deleted:
                    return
                if current.session.get("active_turn") == turn_id:
                    self._push_delta(current)
                    self._interrupt(current.session, public_error(error), "turn.failed")
        finally:
            with self.lock:
                self.runs.pop(turn_id, None)
                self.cancels.pop(turn_id, None)

    def _refresh_memory(self, session_id):
        """后台更新结构化笔记；失败或场次已删就静默跳过。"""
        updater = getattr(self.adapter, "update_memory", None)
        if updater is None:
            return
        try:
            snapshot = self.store.get(session_id)
        except KeyError:
            return
        except Exception:
            # 服务正在关闭、数据库已关：后台任务是尽力而为，不往外抛
            logging.getLogger(__name__).debug("笔记任务读库失败", exc_info=True)
            return
        version = len(snapshot.get("messages") or [])
        try:
            memory = updater(snapshot)
        except Exception:
            logging.getLogger(__name__).exception("面试笔记更新失败：%s", session_id)
            return
        if not memory:
            return
        with self.lock:
            try:
                session = self.store.get(session_id)
            except KeyError:
                return
            except Exception:
                logging.getLogger(__name__).debug("笔记任务回写失败", exc_info=True)
                return
            # 后来的回合已经写过更新的笔记，这次就作废
            if version < int(session.get("memory_version") or 0):
                return
            session["memory"] = memory
            session["memory_version"] = version
            self.store.save(session)

    def close(self):
        with self.lock:
            for cancel in self.cancels.values():
                cancel.set()
            self.listeners.clear()
        self.memory_executor.shutdown(wait=False, cancel_futures=True)
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.store.close()
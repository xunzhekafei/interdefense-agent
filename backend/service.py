"""One local execution queue; session data and cancellation stay independent."""
import copy
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from interview_spec import DEFAULT_ROUNDS, classify_answer

from .agent_adapter import InterviewAgent
from .sessions import SessionStore


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
        # No process-local job survives a restart; retain partial output for review.
        for session in self.store.list():
            if session["active_turn"]:
                self._interrupt(session, "服务已重启，本轮未完成。可重试。")

    def create(self, candidate, role, background, pressure="标准", mode="text",
               rounds=DEFAULT_ROUNDS):
        session = dict(id=uuid.uuid4().hex, candidate=candidate, role=role, background=background,
                       pressure=pressure, mode=mode, rounds=rounds, created_at=now(),
                       status="ready", active_turn=None, messages=[], report=None, seq=0,
                       error=None, last_action=None, requests=[])
        self.store.save(session)
        return session

    def _interrupt(self, session, reason, event_type="turn.cancelled"):
        turn_id = session["active_turn"]
        for message in session["messages"]:
            if message["turn_id"] == turn_id and message["status"] == "streaming":
                message["status"] = "interrupted"
        session.update(status="ready", active_turn=None, error=reason)
        self.store.save(session, event_type, {"message": reason}, turn_id)

    def delete(self, session_id):
        """删掉一场面试。

        正在跑的回合先取消——worker 收尾时会发现场次已经不在，安全退出，
        不会把已删除的场次又写回去。
        """
        with self.lock:
            session = self.store.get(session_id)      # 不存在时抛 KeyError
            turn_id = session.get("active_turn")
            if turn_id:
                cancel = self.cancels.get(turn_id)
                if cancel is not None:
                    cancel.set()
                self.cancels.pop(turn_id, None)
            self.store.delete(session_id)

    def submit(self, session_id, action, text="", request_id="", input_mode="text"):
        with self.lock:
            session = self.store.get(session_id)
            if request_id in session["requests"]:
                return session  # At-most-once submission on client reconnect.
            if action == "cancel":
                session["requests"].append(request_id)
                if session["active_turn"]:
                    self.cancels[session["active_turn"]].set()
                    self._interrupt(session, "本轮已取消，可重试。")
                else:
                    self.store.save(session)
                return session
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
            self.executor.submit(self._run, copy.deepcopy(session), action, turn_id, cancel)
            return session

    @staticmethod
    def _add_message(session, turn_id, role, text, status, input_mode="text"):
        # input_mode 只在候选人消息上有意义：面试官的话永远是文字。
        # 它由客户端声明、服务端无法核实——但作为「这条是语音转写的，术语拼写别太当真」
        # 的提示足够用了。见 agent.VOICE_MARK。
        session["messages"].append(dict(id=uuid.uuid4().hex, turn_id=turn_id, role=role, text=text,
                                        status=status, input_mode=input_mode, created_at=now()))

    def _run(self, snapshot, action, turn_id, cancel):
        session_id = snapshot["id"]

        def emit(event_type, data):
            with self.lock:
                session = self.store.get(session_id)
                if cancel.is_set() or session["active_turn"] != turn_id:
                    raise InterruptedError("轮次已取消")
                if event_type == "reply.delta":
                    session["messages"][-1]["text"] += data["text"]
                self.store.save(session, event_type, data, turn_id)

        try:
            if cancel.is_set():
                return
            if action == "finish":
                result = self.adapter.report(snapshot, emit, cancel, self.directory / session_id)
            else:
                result = self.adapter.reply(snapshot, emit, cancel, self.directory / session_id)
            with self.lock:
                try:
                    session = self.store.get(session_id)
                except KeyError:
                    return                    # 场次已被删除，别再写回去
                if cancel.is_set() or session["active_turn"] != turn_id:
                    return
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
                # 本轮已经对用户结束了。笔记在后台更新，下一轮开始前基本能赶上；
                # 赶不上就晚一轮，不影响面试本身。
                if action != "finish":
                    self.memory_executor.submit(self._refresh_memory, session_id)
        except InterruptedError:
            with self.lock:
                try:
                    session = self.store.get(session_id)
                except KeyError:
                    return
                if session["active_turn"] == turn_id:
                    self._interrupt(session, "本轮已取消，可重试。")
        except Exception as error:
            logging.getLogger(__name__).exception("Interview turn failed: %s", turn_id)
            with self.lock:
                try:
                    session = self.store.get(session_id)
                except KeyError:
                    return
                if session["active_turn"] == turn_id:
                    self._interrupt(session, public_error(error), "turn.failed")
        finally:
            with self.lock:
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
        self.memory_executor.shutdown(wait=False, cancel_futures=True)
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.store.close()

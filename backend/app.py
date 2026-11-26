"""Run locally: python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000."""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import (FastAPI, File, HTTPException, Request, Response, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from interview_spec import DEFAULT_ROUNDS
from settings import env_flag

from .auth import COOKIE, TTL_SECONDS, AuthStore
from .profile import build_profile
from .report_export import to_markdown, to_pdf
from .script_import import MAX_UPLOAD_BYTES as SCRIPT_MAX_BYTES
from .script_import import ScriptImportError, extract as extract_script
from .service import InterviewService
from .speech import CAPABILITIES

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)

# create_app 没显式传 recognizer 时用这个哨兵，表示「按环境试着构建一个」。
# 显式传 None 则表示「不要语音」，两者含义不同：测试靠它拿到确定行为。
_AUTO = object()

# 音频大小上限（约 20 分钟的 opus）。真正的防线在前端时长上限，这里只是兜底。
MAX_AUDIO_BYTES = 5 * 1024 * 1024

# 浏览器 MediaRecorder 可能产出的容器。PyAV 三种都能解，这里只做早期拦截给出清晰报错。
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/aac", "audio/wav", "audio/x-wav")

# 公网部署的基础防护。CSP 只放行同源脚本/样式与 WebSocket，
# 避免 XSS 直接读走登录 cookie 或会话内容。
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
}
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; media-src 'self' blob:; connect-src 'self' ws: wss:; "
    "font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
# /docs 的 Swagger UI 从 CDN 加载脚本，套 CSP 会白屏；文档页不套 CSP。
CSP_EXEMPT_PATHS = ("/docs", "/redoc", "/openapi.json")


def apply_security_headers(response, secure=False, csp=True):
    """给响应补安全头；已有同名头不覆盖，便于反向代理自行调整。"""
    for name, value in SECURITY_HEADERS.items():
        if name not in response.headers:
            response.headers[name] = value
    if csp and "Content-Security-Policy" not in response.headers:
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    if secure and "Strict-Transport-Security" not in response.headers:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def _build_recognizer():
    """按环境尝试构建本地语音识别器；依赖没装就返回 None，不抛异常。

    WEB_SPEECH=off 可以显式关掉语音——装了依赖但暂时不想用时，不必去卸载。
    必须在函数内部 import：CI 只装 requirements-web.txt + requirements-dev.txt，
    模块级 import 会把 faster-whisper 变成硬依赖，也会让每次 import backend.app 都变慢。
    """
    if not env_flag("WEB_SPEECH", True):
        print("[语音] 已由 WEB_SPEECH 关闭（麦克风按钮不会出现）", flush=True)
        return None
    try:
        from .whisper_asr import build_recognizer
    except Exception:      # 依赖缺失、CUDA DLL 加载失败，都算「这台机器没有语音能力」
        return None
    return build_recognizer()


class SessionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    candidate: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=120)
    background: str = Field(default="", max_length=8000)
    # 场景：求职面试 / 毕业答辩 / 课程汇报。后两者会用讲稿切出陈述单元，
    # 追问锚定到单元而不是泛泛提问。
    scene: Literal["interview", "defense", "presentation"] = "interview"
    script: str = Field(default="", max_length=20000)
    # 从上一场继承检验点：服务端读上一场已确认的摘要卡，不接收客户端伪造的内容
    focus_from: str | None = Field(default=None, max_length=64)
    # 面试压力档位，各档规则见 skills/mock-interviewer/SKILL.md
    pressure: Literal["温和", "标准", "压力"] = "标准"
    # 交互方式：文字 / 纯语音。纯语音会话不显示文字输入框，回答自动转写提交。
    mode: Literal["text", "voice"] = "text"
    # 目标总题数（含开场和反问），只允许几个固定档位
    rounds: Literal[10, 15, 20, 30, 50] = DEFAULT_ROUNDS


class SummaryEdit(BaseModel):
    id: str = Field(min_length=1, max_length=16)
    status: Literal["pending", "confirmed", "rejected", "resolved", "dismissed"] = "pending"
    edited_text: str | None = Field(default=None, max_length=200)


class SummaryPatch(BaseModel):
    claims: list[SummaryEdit] = Field(default_factory=list)
    open_questions: list[SummaryEdit] = Field(default_factory=list)


class SummaryRefresh(BaseModel):
    refresh: bool = False


class Command(BaseModel):
    action: Literal["start", "answer", "finish", "cancel", "retry"]
    text: str = Field(default="", max_length=12000)
    request_id: str = Field(min_length=8, max_length=80)
    # 只用来告诉评分「这条是语音转写的」——服务端在提交时只拿到一个字符串，
    # 无法核实它到底是不是语音输入。作为宽容术语拼写的提示足够，别当事实用。
    # 注意这个模型没设 model_config，pydantic 默认 extra="ignore"：
    # 客户端多传字段不会报错，只会被静默丢掉。加字段必须同时改这里。
    input_mode: Literal["text", "voice"] = "text"


class LoginInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


def create_app(directory=None, adapter=None, recognizer=_AUTO):
    data_dir = Path(directory) if directory else ROOT / ".web-data"

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = InterviewService(data_dir, adapter)
        # 语音能力在启动时解析一次：_AUTO → 按环境试建；显式 None → 关闭语音。
        # 这里只构建识别器对象，**不加载模型**（首次转写或预热接口才加载）。
        app.state.recognizer = _build_recognizer() if recognizer is _AUTO else recognizer
        try:
            yield
        finally:
            await asyncio.to_thread(app.state.service.close)

    app = FastAPI(title="InterDefense Studio", lifespan=lifespan)
    # 部署到公网时用 WEB_ALLOWED_HOSTS 放行域名/隧道地址；默认只允许本机。
    allowed_hosts = [h.strip() for h in os.environ.get(
        "WEB_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    origins = {o.strip() for o in os.environ.get(
        "WEB_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,"
        "http://127.0.0.1:5173,http://localhost:5173").split(",") if o.strip()}

    # 登录状态：没有 auth.json 时 enabled=False，行为与之前完全一致。
    app.state.auth = AuthStore(data_dir)

    def _allowed_origins(request) -> set:
        """同源请求永远放行；WEB_ALLOWED_ORIGINS 只用于额外的跨源来源。"""
        allowed = set(origins)
        host = request.headers.get("host")
        if host:
            allowed.update({f"http://{host}", f"https://{host}"})
        return allowed

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        # Same-origin app / Vite proxy. Reject browser writes from unrelated sites.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin not in _allowed_origins(request):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "不允许的来源"}, status_code=403)
        return await call_next(request)

    def request_token(request):
        """Cookie 优先，其次 Authorization: Bearer —— 原生 App 用后者。

        浏览器里没有 Bearer 头，行为不变；Android 客户端不必自己管理 cookie
        存储，登录后把 token 放进 HTTP 头即可。
        """
        header = request.headers.get("authorization") or ""
        if header[:7].lower() == "bearer ":
            return header[7:].strip()
        return request.cookies.get(COOKIE)

    def websocket_token(websocket):
        header = websocket.headers.get("authorization") or ""
        if header[:7].lower() == "bearer ":
            return header[7:].strip()
        return websocket.cookies.get(COOKIE)

    @app.middleware("http")
    async def check_auth(request: Request, call_next):
        auth = app.state.auth
        if not auth.enabled():
            return await call_next(request)
        path = request.url.path
        # 登录本身和健康检查必须公开；静态页面也要能加载出登录页。
        if not path.startswith("/api/") or path in ("/api/health", "/api/login", "/api/logout"):
            return await call_next(request)
        user = auth.check(request_token(request))
        if user is None:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "请先登录"}, status_code=401)
        request.state.user = user
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # 最后注册 = 最外层：401/403 等早退响应也会带上这些头。
        response = await call_next(request)
        secure = (request.url.scheme == "https"
                  or request.headers.get("x-forwarded-proto") == "https")
        apply_security_headers(response, secure,
                               csp=request.url.path not in CSP_EXEMPT_PATHS)
        return response

    def get_session(session_id):
        try:
            return app.state.service.store.get(session_id)
        except KeyError:
            raise HTTPException(404, "找不到面试场次")

    def speech_capabilities():
        """对外提供的能力由注入的 recognizer 决定，不是「faster_whisper 能不能 import」。

        否则会出现这样的坑：本机装上语音依赖后 asr 变 True，而断言 asr is False 的测试就挂——
        故障只在功能开始可用之后、且只在本机出现，CI 反而照样绿。
        """
        recognizer = app.state.recognizer
        capabilities = dict(CAPABILITIES)          # 复制一份，不 mutate 模块级共享的那份
        capabilities["asr"] = recognizer is not None
        capabilities["ready"] = bool(recognizer is not None and recognizer.ready())
        # 有识别能力就同时支持文字和纯语音会话
        capabilities["input_modes"] = ["text", "voice"] if recognizer is not None else ["text"]
        return capabilities

    @app.get("/api/health")
    def health():
        return {"configured": app.state.service.adapter.configured(), "speech": speech_capabilities()}

    @app.post("/api/login")
    def login(body: LoginInput, request: Request, response: Response):
        auth = app.state.auth
        if not auth.enabled():
            return {"user": None, "enabled": False}
        # nginx / Tunnel 反代时 client.host 通常是 127.0.0.1，限流会退化为全局计数；
        # 单用户评审场景可接受，也避免因伪造 X-Forwarded-For 绕过限制。
        client = request.client.host if request.client else "unknown"
        attempt_key = f"{client}:{body.username.strip().lower()}"
        # 同时按 IP 和 IP+用户名计数：换用户名试密码也会被 IP 维度拦住。
        attempt_keys = (f"ip:{client}", attempt_key)
        if any(auth.blocked(key) for key in attempt_keys):
            raise HTTPException(429, "登录尝试过于频繁，请稍后再试")
        if not auth.verify(body.username, body.password):
            for key in attempt_keys:
                auth.record_failure(key)
            raise HTTPException(401, "用户名或密码错误")
        for key in attempt_keys:
            auth.record_success(key)
        token = auth.issue(body.username)
        # 走 HTTPS（或 Cloudflare Tunnel 转发）时加 Secure；本机 http 不加，否则 cookie 存不住。
        secure = (request.url.scheme == "https"
                  or request.headers.get("x-forwarded-proto") == "https")
        response.set_cookie(COOKIE, token, max_age=TTL_SECONDS, httponly=True,
                            samesite="lax", secure=secure, path="/")
        # token 同时返回给原生客户端：它不用管 cookie，放进 Authorization 头即可。
        return {"user": body.username, "enabled": True, "token": token}

    @app.get("/api/me")
    def me(request: Request):
        auth = app.state.auth
        if not auth.enabled():
            return {"user": None, "enabled": False}
        user = auth.check(request_token(request))
        if user is None:
            raise HTTPException(401, "请先登录")
        return {"user": user, "enabled": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        auth = app.state.auth
        if auth.enabled():
            # 只删 cookie 只让浏览器不再发送；服务端版本号 +1 才能让旧 token 真正作废。
            auth.revoke(request_token(request))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/sessions")
    def sessions():
        # 只读摘要列：列表页不需要完整问答和报告，避免每次刷新反序列化整库。
        return app.state.service.store.summaries()

    @app.get("/api/profile")
    def profile():
        """跨场次能力画像：只聚合已生成报告的场次，不调用模型。"""
        return build_profile(app.state.service.store.list_reports())

    @app.post("/api/sessions", status_code=201)
    def create_session(body: SessionInput):
        try:
            return app.state.service.create(**body.model_dump())
        except ValueError as error:
            raise HTTPException(400, str(error))

    @app.get("/api/sessions/{session_id}")
    def session(session_id: str):
        # 回合进行中优先返回内存态：刷新页面时不会比流式输出慢一拍。
        try:
            return app.state.service.snapshot(session_id)
        except KeyError:
            raise HTTPException(404, "找不到面试场次")

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str):
        """删除一场面试及其全部事件。正在跑的回合会先被取消。"""
        try:
            app.state.service.delete(session_id)
        except KeyError:
            raise HTTPException(404, "场次不存在")
        return {"deleted": True}

    @app.post("/api/import-script")
    async def import_script(file: UploadFile = File(...)):
        """上传讲稿（.docx / .pptx / .txt / .md），返回提取出的纯文本。

        刻意不直接建场次：文本先回到输入框让学生确认和修改，
        「AI 读错了我的讲稿」要在开始追问之前就发现。
        """
        data = await file.read(SCRIPT_MAX_BYTES + 1)
        # 上传失败时最难判断的是「请求到底有没有到后端」。这条日志让终端能直接回答：
        # 没有这一行 → 浏览器/宿主的问题；有这一行但报错 → 解析的问题。
        logger.info("讲稿导入：%s（%d 字节）", (file.filename or "")[-60:], len(data))
        if len(data) > SCRIPT_MAX_BYTES:
            raise HTTPException(
                413, f"文件超过 {SCRIPT_MAX_BYTES // (1024 * 1024)} MB，请只上传讲稿正文")
        try:
            result = extract_script(file.filename or "", data)
        except ScriptImportError as error:
            logger.warning("讲稿导入失败：%s", error)
            raise HTTPException(400, str(error)) from error
        logger.info("讲稿导入成功：%s，%d 字%s", result["filename"], result["chars"],
                    "（已截断）" if result["truncated"] else "")
        return result

    @app.post("/api/sessions/{session_id}/summary-card")
    def summary_card(session_id: str, body: SummaryRefresh | None = None):
        """生成摘要卡：AI 对讲稿的理解清单 + 缺少证据的地方。"""
        try:
            card = app.state.service.summary_card(
                session_id, refresh=bool(body and body.refresh))
        except KeyError:
            raise HTTPException(404, "找不到面试场次")
        except ValueError as error:
            raise HTTPException(409, str(error))
        return {"summary_card": card}

    @app.patch("/api/sessions/{session_id}/summary-card")
    def edit_summary_card(session_id: str, body: SummaryPatch):
        """学生逐条确认 / 驳回 / 改写摘要卡的理解。"""
        try:
            card = app.state.service.patch_summary_card(
                session_id,
                claims=[item.model_dump() for item in body.claims],
                open_questions=[item.model_dump() for item in body.open_questions])
        except KeyError:
            raise HTTPException(404, "找不到面试场次")
        except ValueError as error:
            raise HTTPException(409, str(error))
        return {"summary_card": card}

    @app.post("/api/sessions/{session_id}/summary-card/confirm")
    def confirm_summary_card(session_id: str):
        """确认摘要卡，并把确认结果转成下一场的定向检验点。"""
        try:
            return app.state.service.confirm_summary_card(session_id)
        except KeyError:
            raise HTTPException(404, "找不到面试场次")
        except ValueError as error:
            raise HTTPException(409, str(error))

    @app.get("/api/sessions/{session_id}/report")
    def report(session_id: str):
        result = get_session(session_id)["report"]
        if result is None:
            raise HTTPException(404, "报告尚未生成")
        return result

    @app.get("/api/sessions/{session_id}/report.md")
    def report_markdown(session_id: str):
        session = get_session(session_id)
        result = session["report"]
        if result is None:
            raise HTTPException(404, "报告尚未生成")
        return Response(
            content=to_markdown(result, session.get("scene") or ""),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="interview-report-{session_id[:8]}.md"'
            },
        )

    @app.get("/api/sessions/{session_id}/report.pdf")
    def report_pdf(session_id: str):
        session = get_session(session_id)
        result = session["report"]
        if result is None:
            raise HTTPException(404, "报告尚未生成")
        return Response(
            content=to_pdf(result, session.get("scene") or ""),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="interview-report-{session_id[:8]}.pdf"'
            },
        )

    @app.post("/api/sessions/{session_id}/transcribe")
    async def transcribe(session_id: str, request: Request):
        """把一段录音转成文字。**不写入会话**——文字回给前端填进输入框，由用户确认后再走 answer 提交。

        因此这里不碰 service.lock、也不走 service.executor（那是轮次专用的单线程队列）：
        推理要跑十几秒，占住它们会把事件循环和正在流式的轮次一起冻住。
        """
        recognizer = app.state.recognizer
        if recognizer is None:
            raise HTTPException(503, "本机未启用语音识别（需安装 requirements-speech.txt）")
        state = get_session(session_id)
        if state["status"] == "completed":
            raise HTTPException(409, "这场面试已完成，不能再录入回答")

        mime_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if mime_type and not any(mime_type.startswith(t) for t in AUDIO_TYPES):
            raise HTTPException(415, f"不支持的音频类型：{mime_type}")
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "录音太长了，请分段提交")
        audio = await request.body()
        if not audio:
            raise HTTPException(400, "没有收到音频数据")
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "录音太长了，请分段提交")

        async def chunks():
            yield audio

        text, utterance_id = "", ""
        try:
            async for transcript in recognizer.transcribe(
                    chunks(), mime_type=mime_type or "application/octet-stream"):
                text, utterance_id = transcript.text, transcript.utterance_id
                if transcript.final:
                    break
        except Exception:
            # 不把底层异常细节回给浏览器（和 service.public_error 同样的考虑）
            logging.getLogger(__name__).exception("Transcribe failed for session %s", session_id)
            raise HTTPException(500, "语音识别失败，请检查后端日志")
        return {"text": text, "utterance_id": utterance_id}

    @app.post("/api/speech/warmup")
    async def warmup():
        """显式加载语音模型。首次可能要下载几百 MB，所以不在服务启动时做，由用户触发。"""
        recognizer = app.state.recognizer
        if recognizer is None:
            raise HTTPException(503, "本机未启用语音识别（需安装 requirements-speech.txt）")
        try:
            await asyncio.to_thread(recognizer.warmup)
        except Exception:
            logging.getLogger(__name__).exception("Speech warmup failed")
            raise HTTPException(500, "语音模型加载失败，请检查后端日志")
        return speech_capabilities()

    @app.websocket("/api/sessions/{session_id}/ws")
    async def socket(websocket: WebSocket, session_id: str):
        auth = app.state.auth
        if auth.enabled() and auth.check(websocket_token(websocket)) is None:
            # reason 让前端能区分「没登录」和「场次不存在」
            await websocket.close(code=1008, reason="unauthorized")
            return
        origin = websocket.headers.get("origin")
        if origin and origin not in _allowed_origins(websocket):
            await websocket.close(code=1008)
            return
        service = app.state.service
        try:
            state = service.snapshot(session_id)
        except KeyError:
            await websocket.close(code=1008)
            return
        await websocket.accept()

        # 回合线程只往这个队列投事件；发送统一由一个 task 串行做，
        # 避免「接收命令的 task」和「推送事件的 task」同时写 socket。
        outgoing: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_event(event):
            if loop.is_closed():
                return
            try:
                loop.call_soon_threadsafe(outgoing.put_nowait, event)
            except RuntimeError:
                logging.getLogger(__name__).debug("WebSocket 已关闭，丢弃事件")

        unsubscribe = service.listen(session_id, on_event)
        await websocket.send_json({"type": "session.snapshot", "seq": state.get("seq", 0),
                                   "data": state})
        last_snapshot = (state.get("seq", 0), state.get("active_turn"),
                         len(state.get("messages") or []),
                         ((state.get("messages") or [{}])[-1].get("text", "")))

        async def push():
            nonlocal last_snapshot
            while True:
                event = await outgoing.get()
                if event.get("type") == "session.snapshot":
                    data = event.get("data") or {}
                    messages = data.get("messages") or []
                    key = (event.get("seq", 0), data.get("active_turn"), len(messages),
                           messages[-1].get("text", "") if messages else "")
                    if key == last_snapshot:
                        continue
                    last_snapshot = key
                await websocket.send_json(event)

        async def receive():
            nonlocal last_snapshot
            while True:
                # 事件驱动：不再每 100ms 轮询数据库，也不再重复发全量快照。
                raw = await websocket.receive_text()
                if len(raw) > 64000:
                    await websocket.close(code=1009)
                    return
                try:
                    command = Command.model_validate_json(raw)
                    # 重连后可能用同一 request_id 重发命令；submit 返回原状态时，
                    # 客户端仍需要一份快照作为确认，不能按「内容相同」跳过。
                    last_snapshot = None
                    # submit 会加锁、读写 SQLite；放到线程里，别卡事件循环。
                    await asyncio.to_thread(
                        service.submit, session_id, **command.model_dump())
                    await outgoing.put({"type": "command.accepted",
                                        "request_id": command.request_id})
                    # 用内存态而不是 submit 的返回值：worker 可能已经推了增量，
                    # 晚到的旧快照会把前端刚追加的文字覆盖掉。
                    state = service.snapshot(session_id)
                    await outgoing.put({"type": "session.snapshot",
                                        "seq": state.get("seq", 0), "data": state})
                except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                    await outgoing.put({"type": "command.error", "data": {"message": str(exc)}})

        tasks = [asyncio.create_task(push()), asyncio.create_task(receive())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.cancelled():
                    continue
                error = task.exception()
                if error is not None and not isinstance(error, WebSocketDisconnect):
                    logging.getLogger(__name__).warning(
                        "WebSocket 会话异常：%s：%r", session_id, error)
        finally:
            unsubscribe()
            for task in tasks:
                task.cancel()
            try:
                # The worker persists its result even if the browser closes.
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                logging.getLogger(__name__).debug("WebSocket 父任务已取消，跳过清理等待")

    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    # PWA 资源：manifest、Service Worker、图标。它们必须在站点根路径下，
    # 否则浏览器不认（scope 也会不对）。
    if (dist / "icons").is_dir():
        app.mount("/icons", StaticFiles(directory=dist / "icons"), name="icons")

    @app.get("/manifest.webmanifest")
    def manifest():
        path = dist / "manifest.webmanifest"
        if not path.is_file():
            raise HTTPException(404, "前端尚未构建")
        return FileResponse(path, media_type="application/manifest+json")

    @app.get("/sw.js")
    def service_worker():
        path = dist / "sw.js"
        if not path.is_file():
            raise HTTPException(404, "前端尚未构建")
        # 不能缓存：浏览器一天只检查一次更新，缓存住会让修复迟迟到不了用户
        return FileResponse(path, media_type="text/javascript",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/")
    def index():
        if not (dist / "index.html").is_file():
            raise HTTPException(503, "请先在 frontend 执行 npm install 和 npm run build")
        return FileResponse(dist / "index.html")

    return app


app = create_app()

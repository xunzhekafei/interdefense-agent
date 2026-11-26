package com.interdefense.app

import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.interdefense.app.data.Api
import com.interdefense.app.data.ApiException
import com.interdefense.app.data.ChatMessage
import com.interdefense.app.data.DimensionRow
import com.interdefense.app.data.Prefs
import com.interdefense.app.data.SessionSocket
import com.interdefense.app.data.SummaryRow
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

enum class Screen { Login, Home, Summary, Chat, Report }

/**
 * 整个练习流程的状态机：登录 → 首页 → 摘要卡 → 对话 → 报告。
 *
 * 没有引入 ViewModel / DI：三个屏幕共享同一份状态，一个持有 Compose
 * mutableStateOf 的类足够了。网络调用全部在 IO 线程，结果回到主线程再写状态。
 */
class AppController(context: Context) {

    private val prefs = Prefs(context.applicationContext)
    private val main = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var socket: SessionSocket? = null

    var screen by mutableStateOf(Screen.Home)
        private set
    var baseUrl by mutableStateOf(prefs.baseUrl)
    var username by mutableStateOf("")
    var password by mutableStateOf("")
    var authEnabled by mutableStateOf(false)
    var loggedIn by mutableStateOf(false)
    var checking by mutableStateOf(true)
    var busy by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)

    // 首页输入
    var scene by mutableStateOf("defense")
    var script by mutableStateOf("")
    var rounds by mutableStateOf(15)

    // 当前场次
    var sessionId by mutableStateOf<String?>(null)
        private set
    var messages by mutableStateOf<List<ChatMessage>>(emptyList())
    var connected by mutableStateOf(false)
    var streaming by mutableStateOf(false)
    var summaryRows by mutableStateOf<List<SummaryRow>>(emptyList())

    // 报告
    var overall by mutableStateOf<Double?>(null)
    var dimensions by mutableStateOf<List<DimensionRow>>(emptyList())
    var reportSummary by mutableStateOf("")

    init {
        bootstrap()
    }

    private fun bootstrap() {
        checking = true
        scope.launch {
            try {
                val me = withContext(Dispatchers.IO) { Api.me(prefs.baseUrl, prefs.token) }
                authEnabled = me.optBoolean("enabled", false)
                loggedIn = !authEnabled || me.optString("user").isNotBlank()
                screen = if (loggedIn) Screen.Home else Screen.Login
            } catch (reason: Exception) {
                // 连不上后端：停在登录页，地址可以改，方便局域网第一次配置
                authEnabled = true
                screen = Screen.Login
                // 401 只表示 token 过期，不用吓用户；网络错误才把原因显示出来
                error = if (reason is ApiException && reason.code == 401) null else reason.message
            } finally {
                checking = false
            }
        }
    }

    fun retryConnection() {
        error = null
        prefs.baseUrl = baseUrl
        bootstrap()
    }

    fun login() {
        if (busy) return
        busy = true
        error = null
        scope.launch {
            try {
                prefs.baseUrl = baseUrl
                val result = withContext(Dispatchers.IO) {
                    Api.login(prefs.baseUrl, username.trim(), password)
                }
                prefs.token = result.optString("token").takeIf { it.isNotBlank() }
                loggedIn = true
                password = ""
                screen = Screen.Home
            } catch (reason: Exception) {
                error = reason.message
            } finally {
                busy = false
            }
        }
    }

    fun logout() {
        socket?.close()
        socket = null
        prefs.token = null
        loggedIn = false
        screen = Screen.Login
    }

    // ---- 首页 → 摘要卡 ----

    fun startSession() {
        if (busy) return
        if (script.trim().length < 50) {
            error = "讲稿太短了：至少粘贴一段正文（50 字以上）"
            return
        }
        busy = true
        error = null
        scope.launch {
            try {
                prefs.baseUrl = baseUrl
                val created = withContext(Dispatchers.IO) {
                    Api.createSession(prefs.baseUrl, prefs.token, scene, script.trim(), rounds)
                }
                val id = created.optString("id")
                sessionId = id
                val card = withContext(Dispatchers.IO) {
                    Api.summaryCard(prefs.baseUrl, prefs.token, id)
                }.optJSONObject("summary_card")
                summaryRows = parseSummary(card)
                screen = Screen.Summary
            } catch (reason: Exception) {
                error = reason.message
            } finally {
                busy = false
            }
        }
    }

    private fun parseSummary(card: JSONObject?): List<SummaryRow> {
        val claims = card?.optJSONArray("claims") ?: JSONArray()
        val rows = ArrayList<SummaryRow>(claims.length())
        for (index in 0 until claims.length()) {
            val item = claims.optJSONObject(index) ?: continue
            rows.add(SummaryRow(item.optString("unit_ref"), item.optString("text")))
        }
        return rows
    }

    fun confirmSummary() {
        val id = sessionId ?: return
        if (busy) return
        busy = true
        error = null
        scope.launch {
            try {
                withContext(Dispatchers.IO) { Api.confirmSummary(prefs.baseUrl, prefs.token, id) }
                openChat(id)
            } catch (reason: Exception) {
                error = reason.message
            } finally {
                busy = false
            }
        }
    }

    fun abandonSession() {
        socket?.close()
        socket = null
        sessionId = null
        summaryRows = emptyList()
        script = ""
        screen = Screen.Home
    }

    // ---- 对话 ----

    private fun openChat(id: String) {
        messages = emptyList()
        connected = false
        streaming = false
        error = null
        socket = SessionSocket(
            baseUrl = prefs.baseUrl,
            token = prefs.token,
            sessionId = id,
            onSnapshot = { data -> main.post { applySnapshot(data) } },
            onDelta = { text -> main.post { appendDelta(text) } },
            onClosed = { reason ->
                main.post {
                    connected = false
                    if (screen == Screen.Chat && reason.isNotBlank()) error = reason
                }
            },
        ).also { it.connect() }
        screen = Screen.Chat
        // 讲稿已经提交，不需要自我介绍，直接进入追问
        socket?.send("start")
    }

    private fun applySnapshot(data: JSONObject) {
        connected = true
        val array = data.optJSONArray("messages") ?: JSONArray()
        val list = ArrayList<ChatMessage>(array.length())
        for (index in 0 until array.length()) {
            val item = array.optJSONObject(index) ?: continue
            list.add(
                ChatMessage(
                    id = item.optString("id"),
                    role = item.optString("role"),
                    text = item.optString("text"),
                    status = item.optString("status"),
                ),
            )
        }
        messages = list
        streaming = !data.isNull("active_turn") && data.optString("active_turn").isNotBlank()
        val report = data.optJSONObject("report")
        if (report != null && data.optString("status") == "completed") {
            applyReport(report)
            screen = Screen.Report
        }
    }

    private fun appendDelta(text: String) {
        if (text.isEmpty()) return
        val list = messages.toMutableList()
        val last = list.lastOrNull()
        if (last != null && last.role == "assistant" && last.status == "streaming") {
            list[list.lastIndex] = last.copy(text = last.text + text)
        } else {
            list.add(ChatMessage("local-${System.nanoTime()}", "assistant", text, "streaming"))
        }
        messages = list
        streaming = true
    }

    fun sendAnswer(text: String) {
        val body = text.trim()
        if (body.isEmpty() || streaming) return
        val sent = socket?.send("answer", body) ?: false
        if (!sent) {
            error = "连接还没就绪，请稍后重试"
            return
        }
        error = null
        messages = messages + ChatMessage("local-${System.nanoTime()}", "user", body, "streaming")
        streaming = true
    }

    fun finishSession() {
        val id = sessionId ?: return
        if (busy) return
        socket?.send("finish")
        busy = true
        error = null
        scope.launch {
            repeat(150) {                     // 最多等 5 分钟：长报告要逐题评分
                delay(2000)
                val data = runCatching {
                    withContext(Dispatchers.IO) { Api.session(prefs.baseUrl, prefs.token, id) }
                }.getOrNull()
                val report = data?.optJSONObject("report")
                if (report != null) {
                    applyReport(report)
                    screen = Screen.Report
                    busy = false
                    return@launch
                }
            }
            busy = false
            error = "报告生成超时，可以稍后在电脑端打开这一场查看"
        }
    }

    private fun applyReport(report: JSONObject) {
        overall = if (report.isNull("overall")) null else report.optDouble("overall").takeIf { !it.isNaN() }
        reportSummary = report.optString("summary")
        val scores = report.optJSONObject("dimension_scores") ?: JSONObject()
        dimensions = scores.keys().asSequence()
            .map { DimensionRow(it, scores.optDouble(it, 0.0)) }
            .toList()
    }

    fun backHome() {
        socket?.close()
        socket = null
        sessionId = null
        messages = emptyList()
        dimensions = emptyList()
        overall = null
        reportSummary = ""
        summaryRows = emptyList()
        screen = Screen.Home
    }

    fun clearError() {
        error = null
    }

    /** 界面销毁（旋转、退出）时释放连接，避免后台继续收 WebSocket。 */
    fun dispose() {
        socket?.close()
        socket = null
        scope.cancel()
    }
}

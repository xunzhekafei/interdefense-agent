package com.interdefense.app.data

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

class ApiException(message: String, val code: Int = 0) : Exception(message)

/**
 * 后端 HTTP / WebSocket 客户端。
 *
 * 直接用 OkHttp + org.json，不引 Retrofit / Moshi：接口只有七八个，
 * 手写解析比多两套注解和代码生成更好排查。所有函数都是阻塞的，
 * 调用方负责放到 Dispatchers.IO。
 */
object Api {

    private val JSON = "application/json; charset=utf-8".toMediaType()

    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        // 报告生成是分钟级的：实测 4 题约 40 秒，长讲稿会更久
        .readTimeout(300, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private fun call(
        base: String,
        path: String,
        token: String?,
        method: String,
        body: JSONObject? = null,
    ): JSONObject {
        val request = Request.Builder()
            .url(base.trimEnd('/') + path)
            .apply { if (token != null) header("Authorization", "Bearer $token") }
            .apply {
                val payload = (body ?: JSONObject()).toString().toRequestBody(JSON)
                when (method) {
                    "GET" -> get()
                    "POST" -> post(payload)
                    "PATCH" -> patch(payload)
                    else -> error("不支持的方法：$method")
                }
            }
            .build()

        client.newCall(request).execute().use { response: Response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val detail = runCatching { JSONObject(text).optString("detail") }.getOrNull()
                throw ApiException(
                    detail?.takeIf { it.isNotBlank() } ?: "请求失败（HTTP ${response.code}）",
                    response.code,
                )
            }
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        }
    }

    fun health(base: String): JSONObject = call(base, "/api/health", null, "GET")

    fun me(base: String, token: String?): JSONObject = call(base, "/api/me", token, "GET")

    fun login(base: String, username: String, password: String): JSONObject =
        call(base, "/api/login", null, "POST",
            JSONObject().put("username", username).put("password", password))

    fun createSession(
        base: String,
        token: String?,
        scene: String,
        script: String,
        rounds: Int,
    ): JSONObject = call(base, "/api/sessions", token, "POST", JSONObject()
        .put("candidate", "本机练习")
        .put("role", if (scene == "defense") "毕业设计答辩" else "课程汇报")
        .put("scene", scene)
        .put("script", script)
        .put("rounds", rounds)
        .put("pressure", "标准")
        .put("mode", "text"))

    fun session(base: String, token: String?, id: String): JSONObject =
        call(base, "/api/sessions/$id", token, "GET")

    /** 生成摘要卡是 POST（GET 会 405）——网页端踩过一次，这里写清楚。 */
    fun summaryCard(base: String, token: String?, id: String): JSONObject =
        call(base, "/api/sessions/$id/summary-card", token, "POST", JSONObject())

    fun confirmSummary(base: String, token: String?, id: String): JSONObject =
        call(base, "/api/sessions/$id/summary-card/confirm", token, "POST", JSONObject())
}

/**
 * 回合 WebSocket。
 *
 * 服务端会推 `session.snapshot`（全量状态）和 `reply.delta`（增量文字）。
 * 快照是唯一真相：断线重连后只要重新连上，消息列表就能恢复。
 */
class SessionSocket(
    base: String,
    private val token: String?,
    private val sessionId: String,
    private val onSnapshot: (JSONObject) -> Unit,
    private val onDelta: (String) -> Unit,
    private val onClosed: (String) -> Unit,
) {

    private val url: String = base.trimEnd('/')
        .replaceFirst("https://", "wss://")
        .replaceFirst("http://", "ws://") + "/api/sessions/$sessionId/ws"

    private var socket: WebSocket? = null

    fun connect() {
        val request = Request.Builder()
            .url(url)
            .apply { if (token != null) header("Authorization", "Bearer $token") }
            .build()
        socket = Api.client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val event = runCatching { JSONObject(text) }.getOrNull() ?: return
                val data = event.optJSONObject("data") ?: JSONObject()
                when (event.optString("type")) {
                    "session.snapshot" -> onSnapshot(data)
                    "reply.delta" -> onDelta(data.optString("text"))
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                onClosed(t.message ?: "连接断开")
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                onClosed(reason.ifBlank { "连接已断开" })
            }
        })
    }

    fun send(action: String, text: String = ""): Boolean {
        val payload = JSONObject()
            .put("action", action)
            .put("text", text)
            .put("request_id", UUID.randomUUID().toString())
            .toString()
        return socket?.send(payload) ?: false
    }

    fun close() {
        socket?.close(1000, null)
        socket = null
    }
}

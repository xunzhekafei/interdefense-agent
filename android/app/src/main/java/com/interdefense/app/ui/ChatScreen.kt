package com.interdefense.app.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.interdefense.app.AppController
import com.interdefense.app.data.ChatMessage
import com.interdefense.app.speech.VoiceInput

@Composable
fun ChatScreen(controller: AppController) {
    val context = LocalContext.current
    var draft by remember { mutableStateOf("") }
    var listening by remember { mutableStateOf(false) }
    val voiceAvailable = remember { VoiceInput.isAvailable(context) }
    val voice = remember {
        VoiceInput(
            context = context,
            onPartial = { draft = it },
            onFinal = { text ->
                if (text.isNotBlank()) draft = text
                listening = false
            },
            onError = { message ->
                listening = false
                controller.error = message
            },
        )
    }
    DisposableEffect(Unit) {
        onDispose { voice.destroy() }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            listening = true
            voice.start()
        } else {
            controller.error = "需要录音权限才能用语音作答，也可以直接打字"
        }
    }

    fun startVoice() {
        val allowed = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        if (allowed) {
            listening = true
            voice.start()
        } else {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    val listState = rememberLazyListState()
    val lastText = controller.messages.lastOrNull()?.text
    LaunchedEffect(controller.messages.size, lastText) {
        if (controller.messages.isNotEmpty()) {
            listState.animateScrollToItem(controller.messages.lastIndex)
        }
    }

    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Column(Modifier.fillMaxSize().statusBarsPadding()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        if (controller.connected) "答辩追问" else "正在连接…",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "一次一题 · 答完再继续",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                TextButton(
                    onClick = { controller.finishSession() },
                    enabled = !controller.busy,
                ) { Text("结束并出报告") }
            }

            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(controller.messages) { message -> MessageBubble(message) }
            }

            controller.error?.let { message ->
                Text(
                    message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }

            Column(Modifier.fillMaxWidth().imePadding().padding(16.dp)) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text(if (listening) "正在听…说完点「停止」" else "输入你的回答") },
                    minLines = 2,
                    maxLines = 5,
                )
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (voiceAvailable) {
                        OutlinedButton(
                            onClick = {
                                if (listening) {
                                    voice.stop()
                                    listening = false
                                } else {
                                    startVoice()
                                }
                            },
                        ) { Text(if (listening) "停止" else "语音") }
                    }
                    Spacer(Modifier.weight(1f))
                    Button(
                        onClick = {
                            controller.sendAnswer(draft)
                            draft = ""
                        },
                        enabled = draft.isNotBlank() && !controller.streaming,
                    ) { Text(if (controller.streaming) "等待回复…" else "发送") }
                }
            }
        }

        if (controller.busy) {
            Box(
                Modifier.fillMaxSize().background(Color(0x66000000)),
                contentAlignment = Alignment.Center,
            ) {
                Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.surface) {
                    Row(
                        Modifier.padding(horizontal = 22.dp, vertical = 18.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(12.dp))
                        Text("正在生成报告…")
                    }
                }
            }
        }
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    val isUser = message.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            color = if (isUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface,
            contentColor = if (isUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.widthIn(max = 320.dp),
        ) {
            Text(
                message.text.ifBlank { "…" },
                modifier = Modifier.padding(12.dp),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

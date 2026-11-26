package com.interdefense.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.interdefense.app.AppController

@Composable
fun HomeScreen(controller: AppController) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 20.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text("新的练习", style = MaterialTheme.typography.headlineSmall)
                Text(
                    "上传/粘贴讲稿，按段落被追问",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (controller.authEnabled) {
                TextButton(onClick = { controller.logout() }) { Text("退出") }
            }
        }

        Spacer(Modifier.height(20.dp))
        Text("场景", style = MaterialTheme.typography.labelLarge)
        Spacer(Modifier.height(6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = controller.scene == "defense",
                onClick = { controller.scene = "defense" },
                label = { Text("毕业答辩") },
            )
            FilterChip(
                selected = controller.scene == "presentation",
                onClick = { controller.scene = "presentation" },
                label = { Text("课程汇报") },
            )
        }

        Spacer(Modifier.height(18.dp))
        Text("陈述讲稿", style = MaterialTheme.typography.labelLarge)
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(
            value = controller.script,
            onValueChange = { if (it.length <= 20000) controller.script = it },
            modifier = Modifier.fillMaxWidth().height(260.dp),
            placeholder = { Text("粘贴讲稿正文。可以带「研究背景 / 研究方法 / 结果 / 创新 / 局限」小标题，切分会更准。") },
            supportingText = { Text("${controller.script.length} / 20000 字") },
        )

        Spacer(Modifier.height(16.dp))
        Text("练习轮数", style = MaterialTheme.typography.labelLarge)
        Spacer(Modifier.height(6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(10, 15, 20).forEach { value ->
                FilterChip(
                    selected = controller.rounds == value,
                    onClick = { controller.rounds = value },
                    label = { Text("$value 轮") },
                )
            }
        }

        controller.error?.let { message ->
            Spacer(Modifier.height(12.dp))
            Text(message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = { controller.startSession() },
            enabled = !controller.busy,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (controller.busy) "正在读你的讲稿…" else "开始练习")
        }
        Spacer(Modifier.height(10.dp))
        Text(
            "结束后在手机上查看总分和维度分；逐题复盘、单元覆盖等完整报告在电脑端打开同一场即可。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

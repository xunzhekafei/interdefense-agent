package com.interdefense.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.interdefense.app.AppController
import com.interdefense.app.data.SummaryRow

/**
 * 摘要卡：先让学生确认「AI 有没有读懂讲稿」，再开始追问。
 *
 * 手机端只做「确认 / 放弃」。逐条改写留到网页端——小屏幕上改长句子的体验
 * 明显不如电脑，硬做反而降低完成率。
 */
@Composable
fun SummaryScreen(controller: AppController) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
            Text("先确认理解，再开始追问", style = MaterialTheme.typography.headlineSmall)
            Text(
                "下面是 AI 从讲稿里读到的核心主张。哪条不对，回电脑端改写后再练。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                start = 20.dp, end = 20.dp, bottom = 16.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(controller.summaryRows) { row ->
                ClaimCard(row)
            }
        }

        controller.error?.let { message ->
            Text(
                message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(horizontal = 20.dp),
            )
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = { controller.abandonSession() }) { Text("放弃") }
            Spacer(Modifier.weight(1f))
            Button(onClick = { controller.confirmSummary() }, enabled = !controller.busy) {
                Text(if (controller.busy) "准备中…" else "确认，开始练习")
            }
        }
    }
}

@Composable
private fun ClaimCard(row: SummaryRow) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            if (row.unitRef.isNotBlank()) {
                Text(
                    row.unitRef,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
                Spacer(Modifier.height(4.dp))
            }
            Text(row.text, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

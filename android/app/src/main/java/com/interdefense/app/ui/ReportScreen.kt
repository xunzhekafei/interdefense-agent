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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.interdefense.app.AppController

/**
 * 手机端报告只给「结论层」：总分、四维、一段总结。
 *
 * 逐题复盘、单元覆盖、上一场检验点这些在网页端看——手机上读长报告体验差，
 * 也没法对照讲稿原文。这就是「手机练、电脑复盘」的分工。
 */
@Composable
fun ReportScreen(controller: AppController) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
    ) {
        Text("本次练习结束", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary)
        Spacer(Modifier.height(8.dp))

        val overall = controller.overall
        if (overall != null) {
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    String.format("%.1f", overall),
                    style = MaterialTheme.typography.displayMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text("/ 10", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        } else {
            Text("本次有效回答不足，未给出维度评分", style = MaterialTheme.typography.titleMedium)
        }

        Spacer(Modifier.height(20.dp))
        controller.dimensions.forEach { dimension ->
            Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(dimension.name, style = MaterialTheme.typography.bodyMedium)
                    Text(
                        String.format("%.1f", dimension.score),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Spacer(Modifier.height(4.dp))
                LinearProgressIndicator(
                    progress = { (dimension.score / 10.0).toFloat().coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }

        if (controller.reportSummary.isNotBlank()) {
            Spacer(Modifier.height(20.dp))
            Text("整体评价", style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(6.dp))
            Text(controller.reportSummary, style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.height(20.dp))
        Text(
            "逐题复盘、陈述单元覆盖、下一场检验点：在电脑端打开同一场查看。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(Modifier.height(24.dp))
        Button(onClick = { controller.backHome() }, modifier = Modifier.fillMaxWidth()) {
            Text("再练一次")
        }
    }
}

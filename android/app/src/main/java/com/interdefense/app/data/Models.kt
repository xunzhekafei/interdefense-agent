package com.interdefense.app.data

/** 一条对话消息；字段与后端 `session.messages` 对齐。 */
data class ChatMessage(
    val id: String,
    val role: String,        // "assistant" | "user"
    val text: String,
    val status: String,      // "streaming" | "completed" | "interrupted"
)

/** 摘要卡里的一行：单元编号 + 一句话主张。 */
data class SummaryRow(val unitRef: String, val text: String)

/** 报告里的一个维度。 */
data class DimensionRow(val name: String, val score: Double)

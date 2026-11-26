package com.interdefense.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// 与网页端同一套色：深墨绿 + 米白纸面 + 浅绿点缀
private val Ink = Color(0xFF172C2C)
private val Deep = Color(0xFF2F4A3D)
private val Leaf = Color(0xFF6F8F6F)
private val Paper = Color(0xFFF7F8F5)
private val Card = Color(0xFFFBFCF9)

private val scheme = lightColorScheme(
    primary = Deep,
    onPrimary = Color(0xFFEAF1EC),
    secondary = Leaf,
    onSecondary = Color.White,
    background = Paper,
    onBackground = Ink,
    surface = Card,
    onSurface = Ink,
    surfaceVariant = Color(0xFFEDF1E8),
    onSurfaceVariant = Color(0xFF50635B),
    outline = Color(0xFFDCE3D6),
    error = Color(0xFFB23B2E),
)

@Composable
fun InterDefenseTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, typography = Typography(), content = content)
}

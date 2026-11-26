package com.interdefense.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import com.interdefense.app.ui.ChatScreen
import com.interdefense.app.ui.HomeScreen
import com.interdefense.app.ui.InterDefenseTheme
import com.interdefense.app.ui.LoginScreen
import com.interdefense.app.ui.ReportScreen
import com.interdefense.app.ui.SummaryScreen

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            InterDefenseTheme {
                // 旋转屏幕会重建 Activity，这里不保留状态：重新进入首页即可，
                // 未完成的场次在服务端，可以从网页端接着看。
                val controller = remember { AppController(applicationContext) }
                DisposableEffect(controller) {
                    onDispose { controller.dispose() }
                }
                when (controller.screen) {
                    Screen.Login -> LoginScreen(controller)
                    Screen.Home -> HomeScreen(controller)
                    Screen.Summary -> SummaryScreen(controller)
                    Screen.Chat -> ChatScreen(controller)
                    Screen.Report -> ReportScreen(controller)
                }
            }
        }
    }
}

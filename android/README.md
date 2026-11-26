# 手机练习端（Android 原生）

答辩复盘的原生客户端。范围是**练习端三屏**：

1. 登录（服务端没开账号时自动跳过）
2. 首页：选场景 → 粘贴讲稿 → 选轮数
3. 摘要卡确认 → 对话（文字 / 系统语音识别）→ 报告（结论层）

逐题复盘、单元覆盖、成长画像留在网页端：**手机练、电脑复盘**。这样手机端能做得小、
做得稳，跨设备接续也有得讲。

## 当前状态

**未编译验证。** 写这份代码的机器上没有 Android SDK，无法执行 Gradle 构建。
第一次在 Android Studio 里同步时，可能会遇到少量 API 版本差异（版本号集中在两个
`build.gradle.kts` 里，改起来很快）。这一点已记在开发台账 §14。

已实现：

- 与网页端同一个后端（REST + WebSocket），登录用 `Authorization: Bearer`，不依赖 cookie
- 讲稿 → 陈述单元 → 摘要卡确认 → 逐轮追问 → 结束后轮询报告
- 系统语音识别（`SpeechRecognizer`）填进输入框，可修改后再发送；设备不支持时自动隐藏麦克风
- 断线重连：WebSocket 重连后以服务端快照恢复消息

未实现（后续）：

- 讲稿文件上传（.docx/.pptx）——需要 `/api/import-script` 的 multipart 客户端
- 摘要卡逐条改写、场次历史、成长画像
- 后台录音、离线草稿
- OPPO 互联开放能力（手机 ↔ 电脑接续）、OPPO 软件商店上架材料

## 环境

- Android Studio（Ladybug 或更新）+ JDK 17
- 手机：Android 8.0（API 26）及以上

## 打开与构建

```bash
# 1. Android Studio → Open → 选择本目录（android/）
# 2. 如果提示缺少 Gradle wrapper：
#    在 android/ 下执行一次  gradle wrapper --gradle-version 8.9
#    （需要本机有 Gradle；或用 Android Studio 提示的「使用默认 Gradle」）
# 3. 同步完成后：
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## 连接后端

| 运行环境 | 服务地址 |
| --- | --- |
| 模拟器 | `http://10.0.2.2:8000`（默认值） |
| 真机（同一 WiFi） | `http://<电脑局域网 IP>:8000`，在登录页填写 |

后端要放行手机访问的 Host：

```powershell
$env:WEB_ALLOWED_HOSTS = "localhost,127.0.0.1,192.168.1.50"   # 换成你的 IP
.\start.ps1
```

演示期用明文 HTTP（`usesCleartextTraffic=true`）。**上架前必须换成 HTTPS 并删掉这个开关。**

## 目录

```
app/src/main/java/com/interdefense/app/
  MainActivity.kt        入口 + 屏幕路由
  AppController.kt       状态机（登录/首页/摘要卡/对话/报告）与轮询
  data/Api.kt            OkHttp REST + WebSocket
  data/Prefs.kt          服务地址与 token 存储
  data/Models.kt         消息、摘要行、维度行
  speech/VoiceInput.kt   系统语音识别封装
  ui/LoginScreen.kt
  ui/HomeScreen.kt
  ui/SummaryScreen.kt
  ui/ChatScreen.kt
  ui/ReportScreen.kt
  ui/Theme.kt
```

## 为什么用系统语音识别

后端用 faster-whisper 做转写，但 2C2G 的云服务器跑不动模型。手机端改用系统自带的
识别服务：不占服务器、不产生按量费用，识别结果先落在输入框里由学生确认——和网页端
「先确认再提交」是同一条原则。代价是识别质量取决于手机厂商的语音服务。

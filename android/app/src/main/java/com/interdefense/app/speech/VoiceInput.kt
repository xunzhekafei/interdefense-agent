package com.interdefense.app.speech

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/**
 * 用系统自带的语音识别，不上传音频到我们的服务器。
 *
 * 这样移动端不依赖 faster-whisper（2C2G 云服务器跑不动），也不产生按量计费；
 * 代价是识别质量由手机厂商的语音服务决定，转写结果会先填进输入框，
 * 用户能改——和网页端「先确认再提交」是同一条原则。
 *
 * 必须主线程创建和调用。
 */
class VoiceInput(
    context: Context,
    private val onPartial: (String) -> Unit,
    private val onFinal: (String) -> Unit,
    private val onError: (String) -> Unit,
) {

    private val appContext = context.applicationContext
    private var recognizer: SpeechRecognizer? = null

    companion object {
        /** 有些设备/模拟器没有系统识别服务，这时界面不显示麦克风。 */
        fun isAvailable(context: Context): Boolean =
            SpeechRecognizer.isRecognitionAvailable(context)
    }

    private fun ensureRecognizer(): SpeechRecognizer {
        recognizer?.let { return it }
        val created = SpeechRecognizer.createSpeechRecognizer(appContext)
        created.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit

            override fun onError(error: Int) {
                onError(message(error))
            }

            override fun onResults(results: Bundle?) {
                onFinal(firstResult(results))
            }

            override fun onPartialResults(partialResults: Bundle?) {
                val text = firstResult(partialResults)
                if (text.isNotEmpty()) onPartial(text)
            }
        })
        recognizer = created
        return created
    }

    fun start() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        ensureRecognizer().startListening(intent)
    }

    fun stop() {
        recognizer?.stopListening()
    }

    fun destroy() {
        recognizer?.destroy()
        recognizer = null
    }

    private fun firstResult(bundle: Bundle?): String =
        bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull().orEmpty()

    private fun message(code: Int): String = when (code) {
        SpeechRecognizer.ERROR_AUDIO -> "录音出错，再试一次"
        SpeechRecognizer.ERROR_CLIENT -> "识别被中断"
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "没有录音权限"
        SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "语音服务网络不可用"
        SpeechRecognizer.ERROR_NO_MATCH -> "没听清，再说一次？"
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "识别器忙，稍后再试"
        SpeechRecognizer.ERROR_SERVER -> "语音服务出错"
        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "没有听到声音"
        else -> "识别失败（$code）"
    }
}

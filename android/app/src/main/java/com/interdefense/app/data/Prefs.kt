package com.interdefense.app.data

import android.content.Context
import com.interdefense.app.BuildConfig

/**
 * 本地只存两样东西：服务地址和登录 token。
 *
 * token 用 SharedPreferences 而不是 EncryptedSharedPreferences：本项目没有
 * 引入 security-crypto（多一个依赖、多一个上架检查项），token 是 7 天有效期、
 * 只能访问本应用自己的接口，风险可控。真要上架再换成 Keystore 加密。
 */
class Prefs(context: Context) {

    private val sp = context.getSharedPreferences("interdefense", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = sp.getString("base_url", null)?.takeIf { it.isNotBlank() } ?: BuildConfig.API_BASE
        set(value) = sp.edit().putString("base_url", value.trim().trimEnd('/')).apply()

    var token: String?
        get() = sp.getString("token", null)
        set(value) = sp.edit().putString("token", value).apply()
}

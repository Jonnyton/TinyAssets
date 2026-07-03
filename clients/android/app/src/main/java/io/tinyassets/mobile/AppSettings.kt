package io.tinyassets.mobile

import android.content.Context

/**
 * Runtime-overridable settings, persisted in SharedPreferences. Lets a build be
 * pointed at a local branch server (e.g. the emulator's `http://10.0.2.2:8003/mcp`
 * host loopback) and carry a founder bearer token for testing while the on-device
 * WorkOS token-exchange slice is not yet wired.
 */
class AppSettings(context: Context) {
    private val prefs = context.getSharedPreferences("tinyassets", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_URL, TinyAssetsConfig.defaultMcpUrl)
            ?: TinyAssetsConfig.defaultMcpUrl
        set(value) {
            prefs.edit().putString(KEY_URL, value.trim()).apply()
        }

    var bearerToken: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) {
            prefs.edit().putString(KEY_TOKEN, value.trim()).apply()
        }

    private companion object {
        const val KEY_URL = "mcp_url"
        const val KEY_TOKEN = "bearer_token"
    }
}

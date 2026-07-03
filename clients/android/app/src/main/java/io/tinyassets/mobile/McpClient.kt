package io.tinyassets.mobile

import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

data class EndpointCheck(
    val url: String,
    val statusCode: Int,
    val bodyPreview: String,
)

object TinyAssetsConfig {
    // Registered via WorkOS AuthKit Dynamic Client Registration (this AuthKit AS
    // uses DCR — /oauth2/authorize rejects the dashboard "Applications" client
    // ids with application_not_found; a DCR-registered public client is what the
    // hosted sign-in flow accepts). Public client (PKCE, no secret).
    const val workOsClientId = "client_01KWN1CTMEGTD92CNFXRPEAG47"

    /** Default production MCP endpoint. Overridable at runtime via [AppSettings]
     *  so a build can be pointed at a local branch server for testing. */
    const val defaultMcpUrl = "https://tinyassets.io/mcp"
    const val mcpUrl = defaultMcpUrl
    const val protectedResourceMetadataUrl =
        "https://tinyassets.io/.well-known/oauth-protected-resource"
    const val workOsAuthKitDomain = "inventive-van-62-staging.authkit.app"
    const val mobileRedirectUri = "tinyassets://auth/callback"
}

/** Result of a `converse` relay turn to the universe intelligence. */
sealed interface ConverseResult {
    data class Reply(val text: String, val universeId: String) : ConverseResult
    data class Error(val message: String, val authRequired: Boolean) : ConverseResult
}

/**
 * Minimal MCP Streamable-HTTP client. Speaks just enough JSON-RPC to relay a
 * founder turn to the universe's `converse` handle and render its first-person
 * reply. Uses only `HttpURLConnection` + `org.json` (both in the Android SDK) so
 * no new dependency is added.
 */
class McpClient {
    private var requestId = 0

    suspend fun checkProtectedResourceMetadata(
        url: String = TinyAssetsConfig.protectedResourceMetadataUrl,
    ): Result<EndpointCheck> = withContext(Dispatchers.IO) {
        runCatching {
            val connection = URL(url).openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 8_000
            connection.readTimeout = 8_000
            val status = connection.responseCode
            val stream =
                if (status in 200..399) connection.inputStream else connection.errorStream
            val preview = stream?.bufferedReader()?.use { it.readText().take(400) }.orEmpty()
            EndpointCheck(url = url, statusCode = status, bodyPreview = preview)
        }
    }

    /**
     * Relay [message] to the universe at [baseUrl]'s `converse` handle and return
     * its own first-person reply. [token] is the founder's bearer token (from
     * WorkOS sign-in); when null the server rejects with an auth-required error,
     * which is surfaced honestly rather than faked.
     */
    suspend fun converse(
        baseUrl: String,
        token: String?,
        message: String,
    ): ConverseResult = withContext(Dispatchers.IO) {
        try {
            // 1. initialize — capture the session id the server assigns.
            val (initResp, sessionId) = rpc(
                baseUrl, token, sessionId = null,
                body = jsonRpc(
                    nextId(), "initialize",
                    JSONObject()
                        .put("protocolVersion", "2025-06-18")
                        .put("capabilities", JSONObject())
                        .put(
                            "clientInfo",
                            JSONObject()
                                .put("name", "tinyassets-android")
                                .put("version", "0.1.0"),
                        ),
                ),
            )
            initResp.optJSONObject("error")?.let {
                return@withContext ConverseResult.Error(
                    it.optString("message", "MCP initialize failed"), false,
                )
            }

            // 2. notifications/initialized (fire-and-forget).
            rpc(baseUrl, token, sessionId, jsonRpc(null, "notifications/initialized", null))

            // 3. tools/call converse.
            val (callResp, _) = rpc(
                baseUrl, token, sessionId,
                body = jsonRpc(
                    nextId(), "tools/call",
                    JSONObject()
                        .put("name", "converse")
                        .put(
                            "arguments",
                            JSONObject().put("message", message).put("graph_id", ""),
                        ),
                ),
            )
            callResp.optJSONObject("error")?.let {
                return@withContext ConverseResult.Error(
                    it.optString("message", "converse call failed"), false,
                )
            }
            val result = callResp.optJSONObject("result")
                ?: return@withContext ConverseResult.Error("Empty response from server.", false)

            val payload = toolPayload(result)
            when {
                payload.has("reply") -> ConverseResult.Reply(
                    payload.getString("reply"),
                    payload.optString("universe_id", ""),
                )
                payload.has("error") -> ConverseResult.Error(
                    payload.getString("error"),
                    payload.optBoolean("auth_required", false) ||
                        payload.optBoolean("auth_scope_required", false),
                )
                else -> ConverseResult.Error("Unexpected reply shape from your universe.", false)
            }
        } catch (e: Exception) {
            ConverseResult.Error("Couldn't reach your universe: ${e.message}", false)
        }
    }

    private fun nextId(): Int = ++requestId

    private fun jsonRpc(id: Int?, method: String, params: JSONObject?): JSONObject {
        val body = JSONObject().put("jsonrpc", "2.0").put("method", method)
        if (id != null) body.put("id", id)
        if (params != null) body.put("params", params)
        return body
    }

    /** POST one JSON-RPC message; return (parsed-response, session-id header). */
    private fun rpc(
        baseUrl: String,
        token: String?,
        sessionId: String?,
        body: JSONObject,
    ): Pair<JSONObject, String?> {
        val conn = URL(baseUrl).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.connectTimeout = 10_000
        conn.readTimeout = 120_000
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.setRequestProperty("Accept", "application/json, text/event-stream")
        if (!token.isNullOrBlank()) conn.setRequestProperty("Authorization", "Bearer $token")
        if (!sessionId.isNullOrBlank()) conn.setRequestProperty("Mcp-Session-Id", sessionId)

        conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }

        val status = conn.responseCode
        val returnedSession = conn.getHeaderField("Mcp-Session-Id") ?: sessionId
        val stream = if (status in 200..299) conn.inputStream else conn.errorStream
        val raw = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        val contentType = conn.contentType ?: ""
        val json = parseBody(raw, contentType)
        return json to returnedSession
    }

    /** Parse a JSON body OR a text/event-stream (SSE) body's last data: frame. */
    private fun parseBody(raw: String, contentType: String): JSONObject {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return JSONObject()
        if (contentType.contains("text/event-stream") || trimmed.startsWith("event:")) {
            var last: String? = null
            for (line in trimmed.lineSequence()) {
                if (line.startsWith("data:")) last = line.substring(5).trim()
            }
            return if (last.isNullOrBlank()) JSONObject() else JSONObject(last)
        }
        return if (trimmed.startsWith("{")) JSONObject(trimmed) else JSONObject()
    }

    /** A structured tool result: prefer structuredContent, else parse content[0].text. */
    private fun toolPayload(result: JSONObject): JSONObject {
        result.optJSONObject("structuredContent")?.let { return it }
        val content = result.optJSONArray("content")
        if (content != null) {
            for (i in 0 until content.length()) {
                val item = content.optJSONObject(i) ?: continue
                if (item.optString("type") == "text") {
                    val text = item.optString("text").trim()
                    if (text.startsWith("{")) return JSONObject(text)
                }
            }
        }
        return JSONObject()
    }
}

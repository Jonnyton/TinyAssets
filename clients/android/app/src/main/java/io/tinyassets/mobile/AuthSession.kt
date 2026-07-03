package io.tinyassets.mobile

import android.net.Uri
import android.util.Base64
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

sealed interface MobileAuthState {
    data object SignedOut : MobileAuthState
    data object AwaitingCallback : MobileAuthState
    data class CallbackReceived(
        val authorizationCode: String,
        val codeVerifier: String,
        val state: String,
    ) : MobileAuthState {
        val codePreview: String = "${authorizationCode.take(8)}..."
    }
    data object ExchangingToken : MobileAuthState
    data class SignedIn(val accessToken: String) : MobileAuthState
    data class Failed(val message: String) : MobileAuthState
}

data class AuthorizationRequest(
    val authorizationUrl: String,
    val state: String,
    val codeVerifier: String,
)

class MobileAuthController {
    private var pendingRequest: PendingAuthRequest? = null

    fun beginSignIn(): AuthorizationRequest {
        val state = randomUrlSafeString(byteCount = 24)
        val codeVerifier = randomUrlSafeString(byteCount = 64)
        val codeChallenge = codeVerifier.codeChallenge()
        val authorizationUrl = Uri.Builder()
            .scheme("https")
            .authority(TinyAssetsConfig.workOsAuthKitDomain)
            .path("/oauth2/authorize")
            .appendQueryParameter("client_id", TinyAssetsConfig.workOsClientId)
            .appendQueryParameter("redirect_uri", TinyAssetsConfig.mobileRedirectUri)
            .appendQueryParameter("response_type", "code")
            .appendQueryParameter("scope", "openid profile email offline_access")
            .appendQueryParameter("resource", TinyAssetsConfig.mcpUrl)
            .appendQueryParameter("state", state)
            .appendQueryParameter("code_challenge", codeChallenge)
            .appendQueryParameter("code_challenge_method", "S256")
            .build()
            .toString()

        pendingRequest = PendingAuthRequest(state = state, codeVerifier = codeVerifier)
        return AuthorizationRequest(
            authorizationUrl = authorizationUrl,
            state = state,
            codeVerifier = codeVerifier,
        )
    }

    fun receiveRedirect(uri: Uri?): MobileAuthState? {
        if (uri?.scheme != "tinyassets" || uri.host != "auth" || uri.path != "/callback") {
            return null
        }

        val code = uri.getQueryParameter("code")
        val returnedState = uri.getQueryParameter("state")
        if (code.isNullOrBlank() || returnedState.isNullOrBlank()) {
            return MobileAuthState.Failed("Auth callback was missing code or state.")
        }

        val pending = pendingRequest
        if (pending == null || pending.state != returnedState) {
            return MobileAuthState.Failed("Auth callback state did not match the pending request.")
        }

        pendingRequest = null
        return MobileAuthState.CallbackReceived(
            authorizationCode = code,
            codeVerifier = pending.codeVerifier,
            state = returnedState,
        )
    }

    /**
     * Exchange the authorization code + PKCE verifier for a WorkOS access token
     * at the AuthKit token endpoint. Mobile is a PUBLIC OAuth client, so there is
     * no client secret — PKCE is the proof. Returns the access token on success.
     */
    suspend fun exchangeCode(code: String, codeVerifier: String): Result<String> =
        withContext(Dispatchers.IO) {
            runCatching {
                val form = listOf(
                    "grant_type" to "authorization_code",
                    "code" to code,
                    "client_id" to TinyAssetsConfig.workOsClientId,
                    "redirect_uri" to TinyAssetsConfig.mobileRedirectUri,
                    "code_verifier" to codeVerifier,
                ).joinToString("&") { (key, value) ->
                    "$key=" + URLEncoder.encode(value, "UTF-8")
                }
                val conn = URL("https://${TinyAssetsConfig.workOsAuthKitDomain}/oauth2/token")
                    .openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.connectTimeout = 10_000
                conn.readTimeout = 20_000
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
                conn.setRequestProperty("Accept", "application/json")
                conn.outputStream.use { it.write(form.toByteArray(Charsets.UTF_8)) }

                val status = conn.responseCode
                val stream = if (status in 200..299) conn.inputStream else conn.errorStream
                val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                val json = if (body.trim().startsWith("{")) JSONObject(body) else JSONObject()
                if (status !in 200..299) {
                    throw IllegalStateException(
                        json.optString(
                            "error_description",
                            json.optString("error", "token exchange failed (HTTP $status)"),
                        ),
                    )
                }
                json.optString("access_token").ifBlank {
                    throw IllegalStateException("token response contained no access_token")
                }
            }
        }

    fun reset() {
        pendingRequest = null
    }
}

private data class PendingAuthRequest(
    val state: String,
    val codeVerifier: String,
)

private fun randomUrlSafeString(byteCount: Int): String {
    val bytes = ByteArray(byteCount)
    SecureRandom().nextBytes(bytes)
    return Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
}

private fun String.codeChallenge(): String {
    val digest = MessageDigest.getInstance("SHA-256").digest(toByteArray(Charsets.US_ASCII))
    return Base64.encodeToString(digest, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
}

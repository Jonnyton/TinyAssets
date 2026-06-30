package io.tinyassets.mobile

import android.net.Uri
import android.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom

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

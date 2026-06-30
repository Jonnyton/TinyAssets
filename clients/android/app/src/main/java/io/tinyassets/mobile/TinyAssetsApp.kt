package io.tinyassets.mobile

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

@Composable
fun TinyAssetsApp(inboundIntent: Intent? = null) {
    val authController = remember { MobileAuthController() }
    var authState by remember { mutableStateOf<MobileAuthState>(MobileAuthState.SignedOut) }

    LaunchedEffect(inboundIntent?.dataString) {
        val redirectState = authController.receiveRedirect(inboundIntent?.data)
        if (redirectState != null) {
            authState = redirectState
        }
    }

    TinyAssetsTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            UniverseChatScreen(
                authState = authState,
                authController = authController,
                onAuthStateChange = { authState = it },
            )
        }
    }
}

@Composable
private fun UniverseChatScreen(
    authState: MobileAuthState,
    authController: MobileAuthController,
    onAuthStateChange: (MobileAuthState) -> Unit,
) {
    val uriHandler = LocalUriHandler.current
    val messages = conversationMessages(authState)

    Column(modifier = Modifier.fillMaxSize()) {
        AuthPanel(
            authState = authState,
            onBeginSignIn = {
                val request = authController.beginSignIn()
                onAuthStateChange(MobileAuthState.AwaitingCallback)
                uriHandler.openUri(request.authorizationUrl)
            },
            onReset = {
                authController.reset()
                onAuthStateChange(MobileAuthState.SignedOut)
            },
        )

        if (messages.isEmpty()) {
            Spacer(modifier = Modifier.weight(1f))
        } else {
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(messages, key = { it.id }) { message ->
                    ChatBubble(message = message)
                }
            }
        }
    }
}

@Composable
private fun AuthPanel(
    authState: MobileAuthState,
    onBeginSignIn: () -> Unit,
    onReset: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        when (authState) {
            MobileAuthState.SignedOut -> {
                Text("Your universe", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.SemiBold)
                Button(onClick = onBeginSignIn) {
                    Text("Sign in")
                }
            }
            MobileAuthState.AwaitingCallback -> {
                Text("Waiting for WorkOS", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium)
                Text(TinyAssetsConfig.mobileRedirectUri, style = MaterialTheme.typography.bodySmall)
            }
            is MobileAuthState.CallbackReceived -> {
                Text("WorkOS sign-in received", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium)
                Text(
                    "Authorization code ${authState.codePreview} and its PKCE verifier are in memory only.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Button(onClick = onReset) {
                    Text("Reset sign-in")
                }
            }
            is MobileAuthState.Failed -> {
                Text("Sign-in failed", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Medium)
                Text(authState.message, style = MaterialTheme.typography.bodySmall)
                Button(onClick = onReset) {
                    Text("Try again")
                }
            }
        }
    }
}

private fun conversationMessages(authState: MobileAuthState): List<ChatMessage> = when (authState) {
    MobileAuthState.SignedOut -> emptyList()
    MobileAuthState.AwaitingCallback -> listOf(
        ChatMessage("WorkOS is handling sign-in. The app will return here through the registered callback."),
    )
    is MobileAuthState.CallbackReceived -> listOf(
        ChatMessage("The native shell stops at callback receipt for now. Token exchange, secure token storage, founder universe resolution, and authorization-before-voice routing must land before this screen can render your universe's first-person reply."),
        ChatMessage("No persona, soul, identity, or conversation history is cached locally."),
    )
    is MobileAuthState.Failed -> listOf(
        ChatMessage("The app is in an honest degraded state. It will not replay or invent a universe voice without a valid server-routed session."),
    )
}

@Composable
private fun ChatBubble(message: ChatMessage) {
    Row(modifier = Modifier.fillMaxWidth()) {
        Card(modifier = Modifier.weight(1f, fill = false)) {
            Text(
                text = message.text,
                modifier = Modifier.padding(12.dp),
            )
        }
        Spacer(modifier = Modifier.width(44.dp))
    }
}

private data class ChatMessage(
    val text: String,
) {
    val id: String = text
}

@Composable
private fun TinyAssetsTheme(content: @Composable () -> Unit) {
    MaterialTheme(content = content)
}

@Preview
@Composable
private fun TinyAssetsPreview() {
    TinyAssetsApp()
}

package io.tinyassets.mobile

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

private enum class Speaker { FOUNDER, UNIVERSE, SYSTEM }

private data class ChatMessage(
    val speaker: Speaker,
    val text: String,
    val id: Long,
)

@Composable
fun TinyAssetsApp(inboundIntent: Intent? = null) {
    val context = LocalContext.current
    val authController = remember { MobileAuthController() }
    val settings = remember { AppSettings(context) }
    val mcpClient = remember { McpClient() }
    var authState by remember {
        mutableStateOf<MobileAuthState>(
            TokenStore.accessToken(context)?.let { MobileAuthState.SignedIn(it) }
                ?: MobileAuthState.SignedOut,
        )
    }

    LaunchedEffect(inboundIntent?.dataString) {
        val received = authController.receiveRedirect(inboundIntent?.data)
            ?: return@LaunchedEffect
        if (received is MobileAuthState.CallbackReceived) {
            // Exchange the code+PKCE verifier for a real access token, store it
            // in the Keystore, and carry it as the founder bearer for converse.
            authState = MobileAuthState.ExchangingToken
            authState = authController.exchangeCode(
                received.authorizationCode, received.codeVerifier,
            ).fold(
                onSuccess = {
                    TokenStore.saveAccessToken(context, it)
                    MobileAuthState.SignedIn(it)
                },
                onFailure = { MobileAuthState.Failed("Sign-in failed: ${it.message}") },
            )
        } else {
            authState = received
        }
    }

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            UniverseChatScreen(
                settings = settings,
                mcpClient = mcpClient,
                authState = authState,
                onBeginSignIn = {
                    val request = authController.beginSignIn()
                    authState = MobileAuthState.AwaitingCallback
                    request
                },
            )
        }
    }
}

@Composable
private fun UniverseChatScreen(
    settings: AppSettings,
    mcpClient: McpClient,
    authState: MobileAuthState,
    onBeginSignIn: () -> AuthorizationRequest,
) {
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()

    val messages = remember { mutableStateListOf<ChatMessage>() }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var showSettings by remember { mutableStateOf(false) }
    var serverUrl by remember { mutableStateOf(settings.serverUrl) }
    var token by remember { mutableStateOf(settings.bearerToken) }
    var nextId by remember { mutableStateOf(0L) }
    val listState = rememberLazyListState()

    fun add(speaker: Speaker, text: String) {
        messages.add(ChatMessage(speaker, text, nextId++))
    }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // Header + controls
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "Your universe",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            when (authState) {
                MobileAuthState.SignedOut -> TextButton(onClick = {
                    val req = onBeginSignIn()
                    uriHandler.openUri(req.authorizationUrl)
                }) { Text("Sign in") }
                MobileAuthState.AwaitingCallback,
                is MobileAuthState.CallbackReceived,
                MobileAuthState.ExchangingToken ->
                    Text("Signing in…", style = MaterialTheme.typography.bodySmall)
                is MobileAuthState.SignedIn ->
                    Text("Signed in", style = MaterialTheme.typography.bodySmall)
                is MobileAuthState.Failed ->
                    Text("Sign-in failed", style = MaterialTheme.typography.bodySmall)
            }
            TextButton(onClick = { showSettings = !showSettings }) { Text("Server") }
        }

        if (showSettings) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = serverUrl,
                    onValueChange = { serverUrl = it; settings.serverUrl = it },
                    label = { Text("MCP server URL") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = token,
                    onValueChange = { token = it; settings.bearerToken = it },
                    label = { Text("Founder bearer token (optional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "Emulator → host loopback is 10.0.2.2. Point at a local branch " +
                        "server, e.g. http://10.0.2.2:8003/mcp.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        // Conversation
        Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
            if (messages.isEmpty()) {
                Text(
                    "Say hello to your universe below.",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.align(Alignment.Center).padding(24.dp),
                )
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(messages, key = { it.id }) { ChatBubble(it) }
                }
            }
        }

        // Input row
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                placeholder = { Text("Message your universe") },
                modifier = Modifier.weight(1f),
                enabled = !sending,
            )
            Button(
                enabled = !sending && input.isNotBlank(),
                onClick = {
                    val text = input.trim()
                    input = ""
                    add(Speaker.FOUNDER, text)
                    sending = true
                    scope.launch {
                        // The manual token field wins (dev override); otherwise use
                        // the founder token from WorkOS sign-in.
                        val bearer = token.trim().ifBlank {
                            (authState as? MobileAuthState.SignedIn)?.accessToken.orEmpty()
                        }
                        val result = mcpClient.converse(
                            baseUrl = serverUrl.trim(),
                            token = bearer.ifBlank { null },
                            message = text,
                        )
                        when (result) {
                            is ConverseResult.Reply -> add(Speaker.UNIVERSE, result.text)
                            is ConverseResult.Error -> add(Speaker.SYSTEM, result.message)
                        }
                        sending = false
                    }
                },
            ) { Text(if (sending) "…" else "Send") }
        }
    }
}

@Composable
private fun ChatBubble(message: ChatMessage) {
    val isFounder = message.speaker == Speaker.FOUNDER
    val container = when (message.speaker) {
        Speaker.FOUNDER -> MaterialTheme.colorScheme.primaryContainer
        Speaker.UNIVERSE -> MaterialTheme.colorScheme.secondaryContainer
        Speaker.SYSTEM -> MaterialTheme.colorScheme.surfaceVariant
    }
    Row(modifier = Modifier.fillMaxWidth()) {
        if (isFounder) Spacer(modifier = Modifier.width(44.dp))
        Card(
            modifier = Modifier.weight(1f, fill = false),
            colors = CardDefaults.cardColors(containerColor = container),
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = when (message.speaker) {
                        Speaker.FOUNDER -> "You"
                        Speaker.UNIVERSE -> "Your universe"
                        Speaker.SYSTEM -> "TinyAssets"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(text = message.text, style = MaterialTheme.typography.bodyMedium)
            }
        }
        if (!isFounder) Spacer(modifier = Modifier.width(44.dp))
    }
}

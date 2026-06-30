package io.tinyassets.mobile

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

@Composable
fun TinyAssetsApp(
    initialDestination: AppDestination = AppDestination.Chat,
    inboundIntent: Intent? = null,
) {
    var selectedDestination by rememberSaveable { mutableStateOf(initialDestination) }
    val authController = remember { MobileAuthController() }
    var authState by remember { mutableStateOf<MobileAuthState>(MobileAuthState.SignedOut) }

    LaunchedEffect(inboundIntent?.dataString) {
        val redirectState = authController.receiveRedirect(inboundIntent?.data)
        if (redirectState != null) {
            authState = redirectState
            selectedDestination = AppDestination.Chat
        }
    }

    TinyAssetsTheme {
        Scaffold(
            bottomBar = {
                NavigationBar {
                    AppDestination.entries.forEach { destination ->
                        NavigationBarItem(
                            selected = selectedDestination == destination,
                            onClick = { selectedDestination = destination },
                            label = { Text(destination.label) },
                            icon = {},
                        )
                    }
                }
            },
        ) { contentPadding ->
            Surface(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(contentPadding),
            ) {
                when (selectedDestination) {
                    AppDestination.Chat -> UniverseChatScreen(
                        authState = authState,
                        authController = authController,
                        onAuthStateChange = { authState = it },
                    )
                    AppDestination.Mcp -> McpScreen()
                    AppDestination.Settings -> SettingsScreen(
                        onSignOut = {
                            authController.reset()
                            authState = MobileAuthState.SignedOut
                            selectedDestination = AppDestination.Chat
                        },
                    )
                }
            }
        }
    }
}

private val AppDestination.label: String
    get() = when (this) {
        AppDestination.Chat -> "Chat"
        AppDestination.Mcp -> "MCP"
        AppDestination.Settings -> "Settings"
    }

@Composable
private fun UniverseChatScreen(
    authState: MobileAuthState,
    authController: MobileAuthController,
    onAuthStateChange: (MobileAuthState) -> Unit,
) {
    val uriHandler = LocalUriHandler.current
    var draft by rememberSaveable { mutableStateOf("") }
    var nextMessageId by rememberSaveable { mutableIntStateOf(2) }
    val messages = remember {
        mutableStateListOf(
            ChatMessage(
                id = 1,
                role = ChatRole.Agent,
                text = "Sign in with WorkOS and I will route you to your universe.",
            ),
        )
    }

    Column(modifier = Modifier.fillMaxSize()) {
        AuthPanel(
            authState = authState,
            onBeginSignIn = {
                val request = authController.beginSignIn()
                onAuthStateChange(MobileAuthState.AwaitingCallback)
                uriHandler.openUri(request.authorizationUrl)
            },
            onRetry = {
                authController.reset()
                onAuthStateChange(MobileAuthState.SignedOut)
            },
        )

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

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 56.dp, max = 132.dp),
                label = { Text("Message your universe agent") },
                maxLines = 4,
            )
            Button(
                enabled = draft.isNotBlank() && authState is MobileAuthState.CallbackReceived,
                onClick = {
                    val text = draft.trim()
                    if (text.isEmpty()) {
                        return@Button
                    }
                    messages.add(ChatMessage(id = nextMessageId++, role = ChatRole.User, text = text))
                    messages.add(
                        ChatMessage(
                            id = nextMessageId++,
                            role = ChatRole.Agent,
                            text = "I have the shape of that request. Once token exchange and MCP chat routing land, this goes to your universe agent instead of staying local.",
                        ),
                    )
                    draft = ""
                },
            ) {
                Text("Send")
            }
        }
    }
}

@Composable
private fun AuthPanel(
    authState: MobileAuthState,
    onBeginSignIn: () -> Unit,
    onRetry: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("Your universe", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        when (authState) {
            MobileAuthState.SignedOut -> {
                Text("Log in with WorkOS to talk to the agent for your universe.")
                Button(onClick = onBeginSignIn) {
                    Text("Continue with WorkOS")
                }
            }
            MobileAuthState.AwaitingCallback -> {
                Text("Waiting for WorkOS callback...")
                Text(TinyAssetsConfig.mobileRedirectUri, style = MaterialTheme.typography.bodySmall)
            }
            is MobileAuthState.CallbackReceived -> {
                Text("WorkOS callback received", fontWeight = FontWeight.Medium)
                Text(
                    "Authorization code ${authState.codePreview} and its PKCE verifier are in memory only. Token exchange and secure storage are the next slice.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            is MobileAuthState.Failed -> {
                Text("Sign-in failed", fontWeight = FontWeight.Medium)
                Text(authState.message, style = MaterialTheme.typography.bodySmall)
                Button(onClick = onRetry) {
                    Text("Try again")
                }
            }
        }
    }
}

@Composable
private fun McpScreen(client: McpClient = remember { McpClient() }) {
    var endpointState by remember { mutableStateOf<EndpointState>(EndpointState.Loading) }
    var refreshKey by remember { mutableIntStateOf(0) }

    LaunchedEffect(refreshKey) {
        endpointState = client.checkProtectedResourceMetadata().fold(
            onSuccess = { EndpointState.Ready(it) },
            onFailure = { EndpointState.Failed(it.message ?: "Endpoint check failed") },
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("MCP Resource", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        Text(TinyAssetsConfig.mcpUrl, style = MaterialTheme.typography.bodyMedium)

        when (val state = endpointState) {
            EndpointState.Loading -> Text("Checking protected resource metadata...")
            is EndpointState.Ready -> {
                Text("Metadata HTTP ${state.check.statusCode}", fontWeight = FontWeight.Medium)
                Text(state.check.url)
                Text(state.check.bodyPreview.ifBlank { "No response body." })
            }
            is EndpointState.Failed -> Text("Check failed: ${state.message}")
        }

        Button(
            onClick = {
                endpointState = EndpointState.Loading
                refreshKey += 1
            },
        ) {
            Text("Refresh")
        }
    }
}

@Composable
private fun SettingsScreen(onSignOut: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Connection", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        SettingRow(label = "MCP", value = TinyAssetsConfig.mcpUrl)
        SettingRow(label = "AuthKit", value = TinyAssetsConfig.workOsAuthKitDomain)
        SettingRow(label = "Redirect", value = TinyAssetsConfig.mobileRedirectUri)
        Text("Tokens belong in Android Keystore-backed storage after WorkOS OIDC is wired.")
        Button(onClick = onSignOut) {
            Text("Reset session")
        }
    }
}

@Composable
private fun SettingRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top,
    ) {
        Text(label, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(88.dp))
        Text(value, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun ChatBubble(message: ChatMessage) {
    Row(modifier = Modifier.fillMaxWidth()) {
        if (message.role == ChatRole.User) {
            Spacer(modifier = Modifier.width(44.dp))
        }
        Card(modifier = Modifier.weight(1f, fill = false)) {
            Text(
                text = message.text,
                modifier = Modifier.padding(12.dp),
            )
        }
        if (message.role == ChatRole.Agent) {
            Spacer(modifier = Modifier.width(44.dp))
        }
    }
}

private data class ChatMessage(
    val id: Int,
    val role: ChatRole,
    val text: String,
)

private enum class ChatRole {
    User,
    Agent,
}

private sealed interface EndpointState {
    data object Loading : EndpointState
    data class Ready(val check: EndpointCheck) : EndpointState
    data class Failed(val message: String) : EndpointState
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

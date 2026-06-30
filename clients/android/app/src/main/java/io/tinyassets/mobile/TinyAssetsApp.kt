package io.tinyassets.mobile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

@Composable
fun TinyAssetsApp(initialDestination: AppDestination = AppDestination.Home) {
    var selectedDestination by rememberSaveable { mutableStateOf(initialDestination) }

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
                    AppDestination.Home -> HomeScreen(onOpenMcp = { selectedDestination = AppDestination.Mcp })
                    AppDestination.Mcp -> McpScreen()
                    AppDestination.Settings -> SettingsScreen()
                }
            }
        }
    }
}

private val AppDestination.label: String
    get() = when (this) {
        AppDestination.Home -> "Home"
        AppDestination.Mcp -> "MCP"
        AppDestination.Settings -> "Settings"
    }

@Composable
private fun HomeScreen(onOpenMcp: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text("TinyAssets", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
        Text(
            "Native mobile control surface for the same MCP resource server used by chatbot clients.",
            style = MaterialTheme.typography.bodyLarge,
        )
        Button(onClick = onOpenMcp) {
            Text("Check MCP endpoint")
        }
    }
}

@Composable
private fun McpScreen(client: McpClient = remember { McpClient() }) {
    var endpointState by remember { mutableStateOf<EndpointState>(EndpointState.Loading) }
    var refreshKey by remember { mutableStateOf(0) }

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
private fun SettingsScreen() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Connection", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        SettingRow(label = "MCP", value = TinyAssetsConfig.mcpUrl)
        SettingRow(label = "AuthKit", value = TinyAssetsConfig.workOsAuthKitDomain)
        Text("Tokens belong in Android Keystore-backed storage after WorkOS OIDC is wired.")
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

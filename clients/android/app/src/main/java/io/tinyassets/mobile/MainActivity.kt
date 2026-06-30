package io.tinyassets.mobile

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.mutableStateOf

class MainActivity : ComponentActivity() {
    private val inboundIntent = mutableStateOf<Intent?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        inboundIntent.value = intent
        enableEdgeToEdge()
        setContent {
            TinyAssetsApp(
                initialDestination = destinationFromIntent(intent),
                inboundIntent = inboundIntent.value,
            )
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        inboundIntent.value = intent
    }
}

enum class AppDestination {
    Chat,
    Mcp,
    Settings,
}

fun destinationFromIntent(intent: Intent?): AppDestination {
    val uri = intent?.data ?: return AppDestination.Chat
    return when {
        uri.scheme == "tinyassets" && uri.host == "auth" -> AppDestination.Chat
        uri.scheme == "tinyassets" && uri.host == "mcp" -> AppDestination.Mcp
        uri.path?.contains("mcp", ignoreCase = true) == true -> AppDestination.Mcp
        uri.path?.contains("settings", ignoreCase = true) == true -> AppDestination.Settings
        else -> AppDestination.Chat
    }
}

package io.tinyassets.mobile

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TinyAssetsApp(initialDestination = destinationFromIntent(intent))
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
    }
}

enum class AppDestination {
    Home,
    Mcp,
    Settings,
}

fun destinationFromIntent(intent: Intent?): AppDestination {
    val uri = intent?.data ?: return AppDestination.Home
    return when {
        uri.scheme == "tinyassets" && uri.host == "mcp" -> AppDestination.Mcp
        uri.path?.contains("mcp", ignoreCase = true) == true -> AppDestination.Mcp
        uri.path?.contains("settings", ignoreCase = true) == true -> AppDestination.Settings
        else -> AppDestination.Home
    }
}

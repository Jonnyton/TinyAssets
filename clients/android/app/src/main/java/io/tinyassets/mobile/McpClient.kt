package io.tinyassets.mobile

import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class EndpointCheck(
    val url: String,
    val statusCode: Int,
    val bodyPreview: String,
)

object TinyAssetsConfig {
    const val mcpUrl = "https://tinyassets.io/mcp"
    const val protectedResourceMetadataUrl = "https://tinyassets.io/.well-known/oauth-protected-resource"
    const val workOsAuthKitDomain = "inventive-van-62-staging.authkit.app"
}

class McpClient {
    suspend fun checkProtectedResourceMetadata(): Result<EndpointCheck> = withContext(Dispatchers.IO) {
        runCatching {
            val connection = URL(TinyAssetsConfig.protectedResourceMetadataUrl).openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 8_000
            connection.readTimeout = 8_000

            val status = connection.responseCode
            val stream = if (status in 200..399) {
                connection.inputStream
            } else {
                connection.errorStream
            }
            val preview = stream?.bufferedReader()?.use { reader ->
                reader.readText().take(400)
            }.orEmpty()
            EndpointCheck(
                url = TinyAssetsConfig.protectedResourceMetadataUrl,
                statusCode = status,
                bodyPreview = preview,
            )
        }
    }
}

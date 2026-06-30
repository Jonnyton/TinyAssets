import Foundation

enum TinyAssetsConfiguration {
    static let mcpURL = URL(string: "https://tinyassets.io/mcp")!
    static let protectedResourceMetadataURL = URL(string: "https://tinyassets.io/.well-known/oauth-protected-resource")!
    static let workOSAuthKitDomain = "inventive-van-62-staging.authkit.app"
}

struct ProtectedResourceMetadata: Decodable {
    let resource: String?
    let authorizationServers: [String]?

    enum CodingKeys: String, CodingKey {
        case resource
        case authorizationServers = "authorization_servers"
    }
}

struct EndpointCheck {
    let url: URL
    let statusCode: Int
    let metadata: ProtectedResourceMetadata?
    let bodyPreview: String
}

struct MCPClient {
    func checkProtectedResourceMetadata() async throws -> EndpointCheck {
        let request = URLRequest(url: TinyAssetsConfiguration.protectedResourceMetadataURL)
        let (data, response) = try await URLSession.shared.data(for: request)
        let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
        let metadata = try? JSONDecoder().decode(ProtectedResourceMetadata.self, from: data)
        let preview = String(data: data.prefix(400), encoding: .utf8) ?? ""

        return EndpointCheck(
            url: TinyAssetsConfiguration.protectedResourceMetadataURL,
            statusCode: statusCode,
            metadata: metadata,
            bodyPreview: preview
        )
    }
}

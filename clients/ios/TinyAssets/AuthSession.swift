import CryptoKit
import Foundation
import Security

enum MobileAuthState: Equatable {
    case signedOut
    case awaitingCallback
    case callbackReceived(AuthCallback)
    case failed(String)
}

struct AuthCallback: Equatable {
    let authorizationCode: String
    let codeVerifier: String
    let state: String

    var codePreview: String {
        "\(authorizationCode.prefix(8))..."
    }
}

struct MobileAuthFlow {
    private(set) var state: MobileAuthState = .signedOut
    private var pendingRequest: PendingAuthRequest?

    mutating func beginSignIn() throws -> URL {
        let request = try AuthURLFactory.makeAuthorizationRequest()
        pendingRequest = PendingAuthRequest(
            state: request.state,
            codeVerifier: request.codeVerifier
        )
        state = .awaitingCallback
        return request.url
    }

    mutating func receiveRedirect(_ url: URL) {
        guard url.scheme == "tinyassets", url.host == "auth", url.path == "/callback" else {
            return
        }

        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let code = components.queryItems?.first(where: { $0.name == "code" })?.value,
              let returnedState = components.queryItems?.first(where: { $0.name == "state" })?.value else {
            state = .failed("Auth callback was missing code or state.")
            return
        }

        guard let pendingRequest, pendingRequest.state == returnedState else {
            state = .failed("Auth callback state did not match the pending request.")
            return
        }

        self.pendingRequest = nil
        state = .callbackReceived(AuthCallback(
            authorizationCode: code,
            codeVerifier: pendingRequest.codeVerifier,
            state: returnedState
        ))
    }

    mutating func signOut() {
        pendingRequest = nil
        state = .signedOut
    }

    mutating func fail(_ message: String) {
        pendingRequest = nil
        state = .failed(message)
    }
}

struct AuthorizationRequest {
    let url: URL
    let state: String
    let codeVerifier: String
}

private struct PendingAuthRequest {
    let state: String
    let codeVerifier: String
}

enum AuthURLFactory {
    static func makeAuthorizationRequest() throws -> AuthorizationRequest {
        let state = try randomURLSafeString(byteCount: 24)
        let codeVerifier = try randomURLSafeString(byteCount: 64)
        let codeChallenge = codeChallenge(for: codeVerifier)

        var components = URLComponents()
        components.scheme = "https"
        components.host = TinyAssetsConfiguration.workOSAuthKitDomain
        components.path = "/oauth2/authorize"
        components.queryItems = [
            URLQueryItem(name: "client_id", value: TinyAssetsConfiguration.workOSClientID),
            URLQueryItem(name: "redirect_uri", value: TinyAssetsConfiguration.mobileRedirectURI),
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "scope", value: "openid profile email offline_access"),
            URLQueryItem(name: "resource", value: TinyAssetsConfiguration.mcpURL.absoluteString),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]

        guard let url = components.url else {
            throw AuthError.invalidAuthorizationURL
        }

        return AuthorizationRequest(url: url, state: state, codeVerifier: codeVerifier)
    }

    private static func codeChallenge(for verifier: String) -> String {
        let digest = SHA256.hash(data: Data(verifier.utf8))
        return Data(digest).base64URLEncodedString()
    }

    private static func randomURLSafeString(byteCount: Int) throws -> String {
        var bytes = [UInt8](repeating: 0, count: byteCount)
        let status = SecRandomCopyBytes(kSecRandomDefault, byteCount, &bytes)
        guard status == errSecSuccess else {
            throw AuthError.randomGenerationFailed
        }
        return Data(bytes).base64URLEncodedString()
    }
}

enum AuthError: Error {
    case invalidAuthorizationURL
    case randomGenerationFailed
}

extension AuthError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .invalidAuthorizationURL:
            return "Could not build the WorkOS authorization URL."
        case .randomGenerationFailed:
            return "Could not create a secure PKCE challenge."
        }
    }
}

private extension Data {
    func base64URLEncodedString() -> String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

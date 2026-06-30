import SwiftUI

struct AppShell: View {
    @State private var authFlow = MobileAuthFlow()

    var body: some View {
        UniverseChatView(authFlow: $authFlow)
            .onOpenURL { url in
                authFlow.receiveRedirect(url)
            }
    }
}

private struct UniverseChatView: View {
    @Binding var authFlow: MobileAuthFlow
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                header
                if !messages.isEmpty {
                    Divider()
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(messages) { message in
                                ChatBubble(message: message)
                            }
                        }
                        .padding(16)
                    }
                } else {
                    Spacer()
                }
            }
            .navigationTitle("TinyAssets")
        }
    }

    @ViewBuilder
    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            switch authFlow.state {
            case .signedOut:
                Text("Your universe")
                    .font(.largeTitle)
                    .fontWeight(.semibold)
                Button("Sign in") {
                    do {
                        let url = try authFlow.beginSignIn()
                        openURL(url)
                    } catch {
                        authFlow.fail(error.localizedDescription)
                    }
                }
                .buttonStyle(.borderedProminent)
            case .awaitingCallback:
                Text("Waiting for WorkOS")
                    .font(.headline)
                Text(TinyAssetsConfiguration.mobileRedirectURI)
                    .font(.caption)
                    .textSelection(.enabled)
            case .callbackReceived(let callback):
                Text("WorkOS sign-in received")
                    .font(.headline)
                Text("Authorization code \(callback.codePreview) and its PKCE verifier are in memory only.")
                    .font(.caption)
                Button("Reset sign-in") {
                    authFlow.signOut()
                }
                .buttonStyle(.bordered)
            case .failed(let message):
                Text("Sign-in failed")
                    .font(.headline)
                Text(message)
                    .font(.caption)
                Button("Try again") {
                    authFlow.signOut()
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
    }

    private var messages: [ChatMessage] {
        switch authFlow.state {
        case .signedOut:
            return []
        case .awaitingCallback:
            return [
                ChatMessage(text: "WorkOS is handling sign-in. The app will return here through the registered callback.")
            ]
        case .callbackReceived:
            return [
                ChatMessage(text: "The native shell stops at callback receipt for now. Token exchange, secure token storage, founder universe resolution, and authorization-before-voice routing must land before this screen can render your universe's first-person reply."),
                ChatMessage(text: "No persona, soul, identity, or conversation history is cached locally.")
            ]
        case .failed:
            return [
                ChatMessage(text: "The app is in an honest degraded state. It will not replay or invent a universe voice without a valid server-routed session.")
            ]
        }
    }
}

private struct ChatMessage: Identifiable {
    let id = UUID()
    let text: String
}

private struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            Text(message.text)
                .padding(12)
                .background(Color.secondary.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            Spacer(minLength: 36)
        }
    }
}

#Preview {
    AppShell()
}

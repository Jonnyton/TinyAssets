import SwiftUI

enum AppTab: Hashable, CaseIterable, Identifiable {
    case chat
    case mcp
    case settings

    var id: Self { self }

    var title: String {
        switch self {
        case .chat:
            return "Chat"
        case .mcp:
            return "MCP"
        case .settings:
            return "Settings"
        }
    }

    var symbolName: String {
        switch self {
        case .chat:
            return "message"
        case .mcp:
            return "point.3.connected.trianglepath.dotted"
        case .settings:
            return "gearshape"
        }
    }
}

struct AppShell: View {
    @State private var selectedTab: AppTab = .chat
    @State private var authFlow = MobileAuthFlow()

    var body: some View {
        TabView(selection: $selectedTab) {
            UniverseChatView(authFlow: $authFlow)
                .tabItem { Label(AppTab.chat.title, systemImage: AppTab.chat.symbolName) }
                .tag(AppTab.chat)

            MCPStatusView()
                .tabItem { Label(AppTab.mcp.title, systemImage: AppTab.mcp.symbolName) }
                .tag(AppTab.mcp)

            SettingsView()
                .tabItem { Label(AppTab.settings.title, systemImage: AppTab.settings.symbolName) }
                .tag(AppTab.settings)
        }
        .onOpenURL { url in
            authFlow.receiveRedirect(url)
            selectedTab = .chat
        }
    }
}

private struct UniverseChatView: View {
    @Binding var authFlow: MobileAuthFlow
    @Environment(\.openURL) private var openURL
    @State private var draft = ""
    @State private var messages: [ChatMessage] = [
        ChatMessage(role: .agent, text: "Sign in with WorkOS and I will route you to your universe.")
    ]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                authHeader
                Divider()
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(messages) { message in
                            ChatBubble(message: message)
                        }
                    }
                    .padding(16)
                }
                Divider()
                composer
            }
            .navigationTitle("Your universe")
        }
    }

    @ViewBuilder
    private var authHeader: some View {
        VStack(alignment: .leading, spacing: 10) {
            switch authFlow.state {
            case .signedOut:
                Text("Log in with WorkOS to talk to the agent for your universe.")
                    .font(.body)
                Button("Continue with WorkOS") {
                    do {
                        let url = try authFlow.beginSignIn()
                        openURL(url)
                    } catch {
                        authFlow.fail(error.localizedDescription)
                    }
                }
                .buttonStyle(.borderedProminent)
            case .awaitingCallback:
                Text("Waiting for WorkOS callback...")
                    .font(.body)
                Text("Redirect URI: \(TinyAssetsConfiguration.mobileRedirectURI)")
                    .font(.caption)
            case .callbackReceived(let callback):
                Text("WorkOS callback received")
                    .font(.headline)
                Text("Authorization code \(callback.codePreview) and its PKCE verifier are in memory only. Token exchange and secure Keychain storage are the next slice.")
                    .font(.caption)
            case .failed(let message):
                Text("Sign-in failed")
                    .font(.headline)
                Text(message)
                    .font(.caption)
                Button("Try again") {
                    authFlow.signOut()
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
    }

    private var composer: some View {
        HStack(spacing: 10) {
            TextField("Message your universe agent", text: $draft, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...4)
            Button("Send") {
                sendLocalMessage()
            }
            .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !canUseChatShell)
        }
        .padding(12)
    }

    private var canUseChatShell: Bool {
        if case .callbackReceived = authFlow.state {
            return true
        }
        return false
    }

    private func sendLocalMessage() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        messages.append(ChatMessage(role: .user, text: text))
        messages.append(ChatMessage(role: .agent, text: "I have the shape of that request. Once token exchange and MCP chat routing land, this goes to your universe agent instead of staying local."))
        draft = ""
    }
}

private struct MCPStatusView: View {
    @State private var state: EndpointState = .loading
    private let client = MCPClient()

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text("MCP Resource")
                    .font(.title2)
                    .fontWeight(.semibold)
                Text(TinyAssetsConfiguration.mcpURL.absoluteString)
                    .font(.callout)

                switch state {
                case .loading:
                    ProgressView("Checking protected resource metadata...")
                case .ready(let check):
                    Text("Metadata HTTP \(check.statusCode)")
                        .fontWeight(.medium)
                    Text(check.url.absoluteString)
                        .font(.caption)
                    if let resource = check.metadata?.resource {
                        LabeledContent("Resource", value: resource)
                    }
                    if let servers = check.metadata?.authorizationServers, !servers.isEmpty {
                        LabeledContent("Auth server", value: servers.joined(separator: ", "))
                    }
                    Text(check.bodyPreview.isEmpty ? "No response body." : check.bodyPreview)
                        .font(.caption)
                        .textSelection(.enabled)
                case .failed(let message):
                    Text("Check failed: \(message)")
                        .foregroundStyle(.red)
                }

                Button("Refresh") {
                    Task { await refresh() }
                }
                .buttonStyle(.bordered)

                Spacer()
            }
            .padding(24)
            .navigationTitle("MCP")
            .task { await refresh() }
        }
    }

    private func refresh() async {
        state = .loading
        do {
            state = .ready(try await client.checkProtectedResourceMetadata())
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

private struct SettingsView: View {
    var body: some View {
        NavigationStack {
            List {
                Section("Connection") {
                    LabeledContent("MCP", value: TinyAssetsConfiguration.mcpURL.absoluteString)
                    LabeledContent("AuthKit", value: TinyAssetsConfiguration.workOSAuthKitDomain)
                }
                Section("Credential boundary") {
                    Text("Tokens belong in Keychain after WorkOS OIDC is wired. The app should not store provider API keys.")
                }
            }
            .navigationTitle("Settings")
        }
    }
}

private enum EndpointState {
    case loading
    case ready(EndpointCheck)
    case failed(String)
}

private struct ChatMessage: Identifiable {
    let id = UUID()
    let role: ChatRole
    let text: String
}

private enum ChatRole: Equatable {
    case user
    case agent
}

private struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user {
                Spacer(minLength: 36)
            }
            Text(message.text)
                .padding(12)
                .background(message.role == .user ? Color.accentColor.opacity(0.16) : Color.secondary.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            if message.role == .agent {
                Spacer(minLength: 36)
            }
        }
    }
}

#Preview {
    AppShell()
}

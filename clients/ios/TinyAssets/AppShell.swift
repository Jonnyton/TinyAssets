import SwiftUI

enum AppTab: Hashable, CaseIterable, Identifiable {
    case home
    case mcp
    case settings

    var id: Self { self }

    var title: String {
        switch self {
        case .home:
            return "Home"
        case .mcp:
            return "MCP"
        case .settings:
            return "Settings"
        }
    }

    var symbolName: String {
        switch self {
        case .home:
            return "house"
        case .mcp:
            return "point.3.connected.trianglepath.dotted"
        case .settings:
            return "gearshape"
        }
    }
}

struct AppShell: View {
    @State private var selectedTab: AppTab = .home

    var body: some View {
        TabView(selection: $selectedTab) {
            HomeView(onOpenMCP: { selectedTab = .mcp })
                .tabItem { Label(AppTab.home.title, systemImage: AppTab.home.symbolName) }
                .tag(AppTab.home)

            MCPStatusView()
                .tabItem { Label(AppTab.mcp.title, systemImage: AppTab.mcp.symbolName) }
                .tag(AppTab.mcp)

            SettingsView()
                .tabItem { Label(AppTab.settings.title, systemImage: AppTab.settings.symbolName) }
                .tag(AppTab.settings)
        }
    }
}

private struct HomeView: View {
    let onOpenMCP: () -> Void

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 18) {
                Text("TinyAssets")
                    .font(.largeTitle)
                    .fontWeight(.semibold)
                Text("Native mobile control surface for the same MCP resource server used by chatbot clients.")
                    .font(.body)
                Button("Check MCP endpoint", action: onOpenMCP)
                    .buttonStyle(.borderedProminent)
                Spacer()
            }
            .padding(24)
            .navigationTitle("Home")
        }
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

#Preview {
    AppShell()
}

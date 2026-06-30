import AppIntents

struct OpenTinyAssetsIntent: AppIntent {
    static var title: LocalizedStringResource = "Open TinyAssets"
    static var description = IntentDescription("Open the TinyAssets mobile control surface.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        .result()
    }
}

struct CheckTinyAssetsMCPIntent: AppIntent {
    static var title: LocalizedStringResource = "Check TinyAssets MCP"
    static var description = IntentDescription("Open TinyAssets to the MCP status surface.")
    static var openAppWhenRun = true

    func perform() async throws -> some IntentResult {
        .result()
    }
}

struct TinyAssetsShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: OpenTinyAssetsIntent(),
            phrases: [
                "Open \(.applicationName)",
                "Show \(.applicationName)"
            ],
            shortTitle: "Open",
            systemImageName: "sparkles"
        )

        AppShortcut(
            intent: CheckTinyAssetsMCPIntent(),
            phrases: [
                "Check \(.applicationName)",
                "Check TinyAssets MCP"
            ],
            shortTitle: "Check MCP",
            systemImageName: "point.3.connected.trianglepath.dotted"
        )
    }
}

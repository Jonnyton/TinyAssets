# TinyAssets iOS

Native SwiftUI starter for TinyAssets.

## Build

Prerequisites:

- macOS with Xcode 16 or newer
- An available iOS 17+ Simulator

From this directory:

```bash
open TinyAssets.xcodeproj
./scripts/build-simulator.sh
```

The app currently opens WorkOS AuthKit with PKCE, handles
`tinyassets://auth/callback`, and shows a one-screen universe conversation
surface. It does not send local messages or simulate a persona reply. Token
exchange, Keychain storage, founder-universe resolution, and MCP chat routing
remain the next slice.

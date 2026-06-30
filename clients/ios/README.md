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
`tinyassets://auth/callback`, and shows the universe-agent chat shell. Token
exchange and Keychain storage remain the next slice.

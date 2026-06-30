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

The app currently checks `https://tinyassets.io/.well-known/oauth-protected-resource`
and keeps WorkOS token storage as an explicit next slice.

# CricketClubApp iOS

This directory is the iOS app surface for CricketClubApp.

Current implementation:
- A SwiftUI native shell that loads the same live CricketClubApp web experience in a `WKWebView`
- An Xcode project scaffold at `ios/CricketClubApp.xcodeproj`
- A small health/status badge that reflects the live web app state
- A starter app icon asset catalog at `ios/Assets.xcassets`

Parity rule:
- Any feature added to the website must also be reflected here.
- The iOS app should preserve the same club-scoped workflows, scorekeeping, archives, assistant chat, and player coordination by loading the shared web runtime.
- Keep the iOS shell aligned with the web app source of truth in `README.md` and `MOBILE_PARITY.md`.

Implemented files:
- `ios/Sources/CricketClubAppApp.swift`
- `ios/Sources/RootView.swift`
- `ios/Sources/WebShellView.swift`
- `ios/Sources/AppState.swift`
- `ios/Sources/AppConfig.swift`
- `ios/CricketClubApp.xcodeproj/project.pbxproj`
- `ios/Info.plist`
- `ios/Assets.xcassets/AppIcon.appiconset`

Release notes:
- `ios/TESTFLIGHT.md`
- `ios/INSTALL_ON_PHONE.md` (TestFlight-only)

# CricketClubApp Android

This directory is the Android app surface for CricketClubApp.

Current implementation:
- A Jetpack Compose native shell that loads the same live CricketClubApp web experience in an Android `WebView`
- A Gradle project scaffold under `android/`
- A small health/status badge that reflects the live web app state

Parity rule:
- Any feature added to the website must also be reflected here.
- The Android app should preserve the same club-scoped workflows, scorekeeping, archives, assistant chat, and player coordination by loading the shared web runtime.
- Keep the Android shell aligned with the web app source of truth in `README.md` and `MOBILE_PARITY.md`.

Implemented files:
- `android/app/src/main/java/com/cricketclubapp/MainActivity.kt`
- `android/app/src/main/java/com/cricketclubapp/WebShell.kt`
- `android/app/src/main/java/com/cricketclubapp/HealthViewModel.kt`
- `android/app/src/main/java/com/cricketclubapp/AppConfig.kt`
- `android/settings.gradle.kts`
- `android/build.gradle.kts`
- `android/app/build.gradle.kts`
- `android/app/src/main/AndroidManifest.xml`
- `android/app/src/main/res/values/themes.xml`
- `android/app/src/main/res/values/strings.xml`

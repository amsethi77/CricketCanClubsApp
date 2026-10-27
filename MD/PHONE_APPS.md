# Phone apps (Android + iPhone) - build and publish for the Diwali launch

Plan (Oct 26 2026): the website, the iPhone app and the Android app launch together on Sun 8 Nov 2026.
The apps show the CricketCanClubs website inside a native app, so web, iPhone and Android always have the same
features. Native extras: bottom tabs (Home, Live, Score, Scorecards, Upload), camera for scorecard photos,
pull down to refresh, the phone's back button / swipe goes back a page, a "No internet" screen with Try again,
WhatsApp / phone / email links open their own apps, app icon and splash screen.
Fully native screens (Swift / Kotlin) come after launch, one at a time (live scoring first).

The website address is in one place in each app:
- Android: `android/app/build.gradle.kts` -> `BASE_URL`
- iPhone: `ios/Sources/AppConfig.swift` -> `defaultBaseURL`

Both point to `https://cricketcanclubs-web.azurewebsites.net`. Change both if the Azure address is different.
The website must be live there before the apps can be tested or submitted.

## Dates
| When | What | Who |
|---|---|---|
| Oct 27-29 | Website live on Azure | Amit |
| Oct 28 | Android: upload to Play Console closed testing, add 12+ testers | Amit |
| Oct 28-31 | Test both apps on real phones | Dhruvika + Amit |
| By Nov 1 | iPhone: submit for App Store review | Amit (needs the Mac) |
| Nov 8 | Launch | all |

Google Play: a personal developer account created after Nov 13 2023 must run a closed test with at least 12
testers for 14 days before the app can be public. If that applies, on Nov 8 Android users join through the
closed-test link; the store listing goes public when the 14 days are done. Business (organisation) accounts
don't have this rule.

## Still needed on the website before submitting (Claude)
- A privacy policy page (e.g. /privacy) - both stores require the link.
- "Delete my account" for members in their profile - Apple requires it for apps where people can sign up.
- A demo member account for Apple's reviewers.

## Android (Windows, Android Studio)
1. Install Android Studio (latest). Open the `android` folder (File > Open). Let it sync; if it asks to use the
   Gradle wrapper (8.13) or to install Android SDK 36, say yes.
2. Test: plug in an Android phone with USB debugging on (or start an emulator) and press Run (green triangle).
   Check: tabs, sign in, Upload > take a photo, pull down to refresh, back button, airplane mode shows "No internet".
3. Release file: Build > Generate Signed App Bundle / APK > Android App Bundle > create a new key store.
   **Keep the key store file and passwords safe and backed up (not in git)** - every later update needs it.
   The file is `android/app/release/app-release.aab`.
4. Play Console (play.google.com/console): Create app "CricketCanClubs" > Testing > Closed testing > create a track,
   upload the .aab, add testers' Gmail addresses, share the opt-in link with them.
5. Store listing: icon `store_assets/play_icon_512.png`, feature graphic `store_assets/play_feature_1024x500.png`,
   2+ phone screenshots, short and full description, privacy policy link, Data safety form
   (collects: name, email, phone for accounts; photos the user uploads).
6. Each update: raise `versionCode` (1, 2, 3...) in `android/app/build.gradle.kts`.

## iPhone (Mac, Xcode)
1. Open `ios/CricketClubApp.xcodeproj` in Xcode (latest). Team is set to AT2629ZM2V; bundle id `com.cricketclubapp`.
2. Test: pick an iPhone (plugged in) or a simulator, press Run. Same checks as Android.
3. App Store Connect (appstoreconnect.apple.com): My Apps > + > New App, name "CricketCanClubs",
   bundle id `com.cricketclubapp`.
4. In Xcode: Product > Archive > Distribute App > App Store Connect > Upload.
5. In App Store Connect: screenshots (6.9" iPhone), description, keywords, support URL, privacy policy URL,
   App Privacy answers, age rating. Add a **demo account** (email + password of a test member) under
   App Review Information - Apple signs in to check the app. Submit for review.
6. Review notes to paste: "CricketCanClubs is the app for our cricket clubs: live scores, scoring matches,
   scorecards and rankings. Members photograph paper scorecards with the camera (Upload tab) and the app reads them.
   Demo account below."
7. Each update: raise Build (CURRENT_PROJECT_VERSION) in Xcode.

## Icon
`store_assets/` and the apps use a placeholder icon (white stumps and a red ball on green). Replace it with the club
logo when Amit has one: iPhone `ios/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png` (1024x1024, no
transparency); Android `android/app/src/main/res/mipmap-*` (Android Studio: right-click res > New > Image Asset).

## After launch
- Push notifications (live score updates, scorecard published): needs a Firebase project (Android) and an Apple
  push key (iPhone), plus sending from the website.
- Native screens, starting with live scoring (works offline at the ground).

# Phone apps (Android + iPhone) - build and publish for the Diwali launch

Plan: the website, the iPhone app and the Android app launch together on Sun 8 Nov 2026.
**Oct 28 2026: the apps are one Expo / React Native project in `mobile/`** (one codebase for both; the iPhone app
is built in Expo's cloud, so no Mac is needed). It replaces the separate Swift (`ios/`) and Kotlin (`android/`)
apps, which are kept only for reference and can be deleted.
The app shows the CricketCanClubs website inside a native app, so web, iPhone and Android always have the same
features. Native extras: bottom tabs (Home, Live, Score, Scorecards, Upload), camera for scorecard photos,
pull down to refresh (iPhone), back button, a "No internet" screen with Try again, WhatsApp / phone / email links
open their own apps, app icon and splash screen. Fully native screens come after launch, in the same Expo project.

Website address: `mobile/src/config.ts` -> `BASE_URL` = `https://cricketcanclubs-web.azurewebsites.net`.
The website must be live there before the apps can be tested or submitted.

## Dates
| When | What | Who |
|---|---|---|
| Oct 27-29 | Website live on Azure | Amit |
| Oct 28 | Android: upload to Play Console closed testing, add 12+ testers | Amit |
| Oct 28-31 | Test both apps on real phones | Dhruvika + Amit |
| By Nov 1 | iPhone: build in Expo cloud and submit for App Store review | Amit's Apple login + Dhruvika |
| Nov 8 | Launch | all |

Google Play: a personal developer account created after Nov 13 2023 must run a closed test with at least 12
testers for 14 days before the app can be public. If that applies, on Nov 8 Android users join through the
closed-test link; the store listing goes public when the 14 days are done. Business (organisation) accounts
don't have this rule.

## Website pages the stores ask for
- Privacy policy (done Oct 27): `https://cricketcanclubs-web.azurewebsites.net/privacy` - paste this link in both
  stores. Set `SUPPORT_EMAIL` in Azure's Environment variables so the page shows a contact email.
- Delete my account (done Oct 27): Profile page -> "Delete my account" (type DELETE). Apple asks where it is:
  "Sign in > Profile > Delete my account".
- Still to do: a demo member account for Apple's reviewers (a normal player account in a test club, not an admin).

## Build and publish (Windows is enough)
Try it, cloud builds and store submission: see `mobile/README.md`. In short:
1. Test on a phone: `cd mobile`, `npm install`, `npx expo start`, scan the QR code with Expo Go.
2. Free account at expo.dev, then in `mobile`: `npx eas-cli@latest login` and `npx eas-cli@latest init`.
3. Android: `npm run build:android-test` (.apk to share with testers) and `npm run build:android` (.aab for Play).
   Play Console (play.google.com/console): Create app "CricketCanClubs" > Testing > Closed testing > upload the .aab,
   add testers' Gmail addresses, share the opt-in link. Store listing: icon `store_assets/play_icon_512.png`,
   feature graphic `store_assets/play_feature_1024x500.png`, 2+ phone screenshots, descriptions, privacy policy link,
   Data safety form (collects name, email, phone for accounts; photos the user uploads).
4. iPhone: `npm run build:ios` (sign in with the Apple Developer account; Expo makes the certificates), then
   `npm run submit:ios`. In App Store Connect: screenshots (6.9" iPhone), description, keywords, support URL,
   privacy policy URL, App Privacy answers, age rating, **demo account** under App Review Information.
   Review notes: "CricketCanClubs is the app for our cricket clubs: live scores, scoring matches, scorecards and
   rankings. Members photograph paper scorecards with the camera (Upload tab) and the app reads them. Demo account below."
5. Each update: raise `version`, `ios.buildNumber` and `android.versionCode` in `mobile/app.json`.

## Icon
`store_assets/` and the app use a placeholder icon (white stumps and a red ball on green). Replace it with the club
logo when Amit has one: `mobile/assets/icon.png` (1024x1024, no transparency) and the `android-icon-*.png` files.

## After launch
- Push notifications (live score updates, scorecard published): `expo-notifications` + Expo's push service, plus
  sending from the website.
- Native screens, starting with live scoring (works offline at the ground).

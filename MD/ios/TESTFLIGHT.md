# CricketClubApp iOS TestFlight Checklist

This project has a real Xcode app target and can be archived for TestFlight.

## What to prepare before upload

- An Apple Developer Program account
- App Store Connect access
- A unique bundle identifier, if you want to move away from the starter `com.cricketclubapp`
- A production signing team in Xcode
- A checked-in starter app icon asset catalog lives at `ios/Assets.xcassets`
- A release version and build number

## Xcode steps

1. Open `ios/CricketClubApp.xcodeproj` in Xcode.
2. Select the `CricketClubApp` scheme.
3. Pick `Any iOS Device (arm64)` or a connected iPhone.
4. In Signing & Capabilities, choose your Apple team.
5. Update the version/build number before each upload.
6. Set `CRICKETCLUBAPP_BASE_URL` if you want a non-default web target.
7. Use Product > Archive.
8. Open the Organizer and upload to App Store Connect.

If your local Xcode runtime has simulator/asset-catalog issues, keep the starter icon catalog in the repo and wire it only after you have a matching runtime or an Apple-signing machine ready for release builds.

## TestFlight validation

- Install the build from TestFlight on your iPhone.
- Confirm the shell loads the CricketClubApp website.
- Verify the Assistant status chip refreshes from `/api/health`.
- Check sign-in, clubs, dashboard, scoring, and assistant chat.

## Notes

- The current iOS surface is a native shell over the live website, so every web feature is available inside TestFlight automatically.
- Keep the website as the source of truth for new product behavior, then mirror the release notes here when you ship a new build.

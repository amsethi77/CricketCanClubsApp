# Install CricketClubApp On Your iPhone via TestFlight

This iOS target is a native shell over the live CricketClubApp web app, and the intended phone install path is TestFlight.

## What you need

- A Mac with Xcode
- An Apple ID signed into Xcode
- An Apple Developer Program membership
- App Store Connect access

## What the app will do

- Open the live CricketClubApp web experience inside a native iPhone shell.
- Show the assistant status chip in the top-right.
- Use the same club, scoring, chat, and archive flows as the website.

## Local web override

If you want the iPhone shell to load your local dev server instead of Azure, set:

```bash
CRICKETCLUBAPP_BASE_URL=http://127.0.0.1:8090
```

before launching from Xcode while you are archiving or testing.

## TestFlight path

1. Archive the app from Xcode.
2. Upload the archive to App Store Connect.
3. Enable TestFlight in App Store Connect.
4. Install the build from the TestFlight app on your iPhone.

See `ios/TESTFLIGHT.md` for the archive checklist.

## Notes

- The repository includes a starter app icon catalog under `ios/Assets.xcassets`.
- The Xcode shell is already build-verified on this Mac.
- For App Store review, you still need Apple signing, bundle-id setup, and final store metadata in App Store Connect.
- If you only want to test on your phone, TestFlight is the path to use from this repo.

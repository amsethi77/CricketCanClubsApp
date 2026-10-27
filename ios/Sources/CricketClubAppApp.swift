import SwiftUI

/// CricketCanClubs for iPhone. README "Phone apps (Android + iPhone)".
@main
struct CricketClubAppApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
                .onOpenURL { url in appState.handleIncoming(url) }
        }
    }
}

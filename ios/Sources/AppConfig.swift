import Foundation

/// Where the app finds the CricketCanClubs website, and the bottom tabs.
/// The iPhone app shows the same site as the web and Android (they stay in lockstep), with native tabs, camera upload,
/// pull to refresh and an offline screen around it. README "Phone apps (Android + iPhone)".
enum AppConfig {
    /// Change this one line when the Azure address changes (or set CCBaseURL in Info.plist for testing).
    static let defaultBaseURL = "https://cricketcanclubs-web.azurewebsites.net"

    static var baseURL: URL {
        if let raw = Bundle.main.object(forInfoDictionaryKey: "CCBaseURL") as? String,
           let url = URL(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)), !raw.isEmpty {
            return url
        }
        return URL(string: defaultBaseURL)!
    }

    /// Added to the browser's user agent so the website can tell it runs inside the app.
    static let userAgentSuffix = "CricketCanClubsApp/1.0 (iOS)"

    struct Tab: Identifiable, Equatable {
        let label: String
        let path: String
        let symbol: String
        var id: String { path }
        var url: URL { URL(string: AppConfig.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path)! }
    }

    static let tabs: [Tab] = [
        Tab(label: "Home", path: "/", symbol: "house.fill"),
        Tab(label: "Live", path: "/live", symbol: "dot.radiowaves.left.and.right"),
        Tab(label: "Score", path: "/score", symbol: "square.and.pencil"),
        Tab(label: "Scorecards", path: "/scorecards", symbol: "list.bullet.rectangle"),
        Tab(label: "Upload", path: "/scorecards/upload", symbol: "camera.fill"),
    ]

    /// True for pages of our own website (they open inside the app); everything else opens outside.
    static func isOwnPage(_ url: URL?) -> Bool {
        guard let url, let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http" else { return false }
        return url.host?.lowercased() == baseURL.host?.lowercased()
    }

    /// Which tab a page belongs to (longest matching path wins; the dashboard counts as Home).
    static func tab(for url: URL?) -> Tab? {
        let path = (url?.path).flatMap { $0.isEmpty ? "/" : $0 } ?? "/"
        return tabs
            .filter { $0.path == "/" ? (path == "/" || path == "/dashboard") : path.hasPrefix($0.path) }
            .max { $0.path.count < $1.path.count }
    }
}

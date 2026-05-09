import Foundation

enum AppConfig {
    static var baseURL: URL {
        if let raw = ProcessInfo.processInfo.environment["CRICKETCLUBAPP_BASE_URL"],
           let url = URL(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
           !raw.isEmpty {
            return url
        }
        return URL(string: "https://cricketcanclubs-web.azurewebsites.net")!
    }

    static var healthURL: URL {
        baseURL.appendingPathComponent("api/health")
    }
}

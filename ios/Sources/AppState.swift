import Foundation
import SwiftUI

@MainActor
final class AppState: ObservableObject {
    enum HealthState: String {
        case connecting = "Connecting"
        case online = "Online"
        case thinking = "Thinking"
        case offline = "Offline"
    }

    @Published var healthState: HealthState = .connecting
    @Published var healthDetail: String = "Checking the CricketClubApp site..."
    @Published var baseURL: URL = AppConfig.baseURL
    @Published var lastCheckedAt: Date?

    func refreshHealth() async {
        healthState = .connecting
        healthDetail = "Checking the CricketClubApp site..."
        do {
            let (data, response) = try await URLSession.shared.data(from: AppConfig.healthURL)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                healthState = .offline
                healthDetail = "The web app health endpoint did not return success."
                lastCheckedAt = Date()
                return
            }
            let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let llm = payload?["llm"] as? [String: Any]
            let available = llm?["available"] as? Bool ?? false
            let provider = llm?["provider"] as? String ?? ""
            let model = llm?["model"] as? String ?? ""
            if available {
                healthState = .online
                healthDetail = model.isEmpty ? "Online" : "Online · \(model)"
            } else if provider == "ollama" {
                healthState = .thinking
                healthDetail = "Thinking"
            } else {
                healthState = .offline
                healthDetail = "Offline"
            }
            lastCheckedAt = Date()
        } catch {
            healthState = .offline
            healthDetail = error.localizedDescription
            lastCheckedAt = Date()
        }
    }
}

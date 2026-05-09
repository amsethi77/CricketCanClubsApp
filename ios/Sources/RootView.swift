import SwiftUI

struct RootView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ZStack(alignment: .topTrailing) {
            WebShellView(url: appState.baseURL)
                .ignoresSafeArea()

            VStack(alignment: .trailing, spacing: 10) {
                VStack(alignment: .trailing, spacing: 6) {
                    statusPill
                    Text(appState.healthDetail)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8)
                }
                refreshButton
            }
            .padding()
        }
    }

    private var statusPill: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(statusColor)
                .frame(width: 12, height: 12)
                .scaleEffect(appState.healthState == .thinking || appState.healthState == .connecting ? 1.1 : 1.0)
                .opacity(appState.healthState == .thinking || appState.healthState == .connecting ? 0.75 : 1.0)
            Text(appState.healthState.rawValue)
                .font(.system(size: 14, weight: .semibold))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.thinMaterial)
        .clipShape(Capsule())
        .overlay(Capsule().strokeBorder(Color.white.opacity(0.15), lineWidth: 1))
        .shadow(color: .black.opacity(0.12), radius: 10, x: 0, y: 4)
    }

    private var refreshButton: some View {
        Button {
            Task { await appState.refreshHealth() }
        } label: {
            Text("Refresh status")
                .font(.system(size: 13, weight: .medium))
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.white.opacity(0.86))
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private var statusColor: Color {
        switch appState.healthState {
        case .online: return .green
        case .thinking: return .green
        case .connecting: return .red
        case .offline: return .red
        }
    }
}

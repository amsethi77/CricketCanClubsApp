import SwiftUI

private let brandGreen = Color(red: 10 / 255, green: 110 / 255, blue: 70 / 255)

/// The app screen: the website, a thin loading bar, the "no internet" screen and native tabs at the bottom.
struct RootView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .top) {
                WebShellView(webView: appState.webView)
                if appState.progress > 0 && appState.progress < 1 {
                    ProgressView(value: appState.progress)
                        .progressViewStyle(.linear)
                        .tint(brandGreen)
                        .frame(height: 2)
                }
                if appState.isOffline {
                    OfflineView { appState.retry() }
                }
            }
            TabBar()
        }
        .background(Color(.systemBackground))
    }
}

/// Native bottom tabs: each opens that page of the website.
private struct TabBar: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        let selected = AppConfig.tab(for: appState.currentURL)
        VStack(spacing: 0) {
            Divider()
            HStack(spacing: 0) {
                ForEach(AppConfig.tabs) { tab in
                    Button {
                        appState.open(tab)
                    } label: {
                        VStack(spacing: 3) {
                            Image(systemName: tab.symbol)
                                .font(.system(size: 19, weight: .semibold))
                            Text(tab.label)
                                .font(.system(size: 10, weight: .medium))
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 7)
                        .padding(.bottom, 4)
                        .foregroundStyle(selected == tab ? brandGreen : Color(.secondaryLabel))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(tab.label)
                    .accessibilityAddTraits(selected == tab ? .isSelected : [])
                }
            }
        }
        .background(.bar)
    }
}

private struct OfflineView: View {
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
            Text("No internet connection")
                .font(.title3.bold())
            Text("Check your Wi-Fi or mobile data, then try again.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Try again", action: retry)
                .buttonStyle(.borderedProminent)
                .tint(brandGreen)
                .padding(.top, 6)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemGroupedBackground))
    }
}

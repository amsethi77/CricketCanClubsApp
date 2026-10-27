import Foundation
import SwiftUI
import UIKit
import WebKit

/// Owns the one web view the app uses and what the screen shows around it: which tab is active,
/// the loading bar and the "no internet" screen.
@MainActor
final class AppState: NSObject, ObservableObject {
    @Published var currentURL: URL?
    @Published var progress: Double = 0
    @Published var isOffline = false

    let webView: WKWebView
    private var observations: [NSKeyValueObservation] = []
    private let refreshControl = UIRefreshControl()

    override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default() // keeps the sign-in between launches
        config.allowsInlineMediaPlayback = true
        config.applicationNameForUserAgent = AppConfig.userAgentSuffix
        webView = WKWebView(frame: .zero, configuration: config)
        super.init()

        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .automatic
        webView.navigationDelegate = self
        webView.uiDelegate = self

        refreshControl.addTarget(self, action: #selector(pullToRefresh), for: .valueChanged)
        webView.scrollView.refreshControl = refreshControl

        observations = [
            webView.observe(\.estimatedProgress, options: [.new]) { [weak self] view, _ in
                Task { @MainActor in self?.progress = view.estimatedProgress }
            },
            webView.observe(\.url, options: [.new]) { [weak self] view, _ in
                Task { @MainActor in self?.currentURL = view.url }
            },
        ]
        load(AppConfig.tabs[0].url)
    }

    func load(_ url: URL) {
        isOffline = false
        webView.load(URLRequest(url: url))
    }

    func open(_ tab: AppConfig.Tab) {
        load(tab.url)
    }

    func retry() {
        isOffline = false
        if let url = webView.url ?? currentURL {
            webView.load(URLRequest(url: url))
        } else {
            load(AppConfig.tabs[0].url)
        }
    }

    /// A link to one of our pages (e.g. tapped in WhatsApp) opens that page in the app.
    func handleIncoming(_ url: URL) {
        if AppConfig.isOwnPage(url) { load(url) }
    }

    @objc private func pullToRefresh() {
        if webView.url == nil { retry() } else { webView.reload() }
    }

    fileprivate func finishedLoading() {
        refreshControl.endRefreshing()
    }

    fileprivate func failed(_ error: Error) {
        refreshControl.endRefreshing()
        let nsError = error as NSError
        if nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled { return }
        isOffline = true
    }
}

extension AppState: WKNavigationDelegate {
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction) async -> WKNavigationActionPolicy {
        guard let url = navigationAction.request.url else { return .cancel }
        if url.scheme == "about" || url.scheme == "blob" || url.scheme == "data" || AppConfig.isOwnPage(url) {
            return .allow
        }
        // WhatsApp, phone, email, maps and other websites open in their own apps.
        _ = await UIApplication.shared.open(url)
        return .cancel
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isOffline = false
        finishedLoading()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        failed(error)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        failed(error)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }
}

extension AppState: WKUIDelegate {
    /// Links that open a new window (target="_blank"): our pages open here, others outside.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if AppConfig.isOwnPage(url) { webView.load(URLRequest(url: url)) } else { UIApplication.shared.open(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo) async {
        _ = await ask(message, buttons: [("OK", true)])
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo) async -> Bool {
        await ask(message, buttons: [("Cancel", false), ("OK", true)])
    }

    /// The website's alert() / confirm() as a native pop-up (e.g. "Delete this scorecard?").
    private func ask(_ message: String, buttons: [(String, Bool)]) async -> Bool {
        let scene = UIApplication.shared.connectedScenes.first { $0.activationState == .foregroundActive } as? UIWindowScene
        guard var top = scene?.windows.first(where: { $0.isKeyWindow })?.rootViewController else { return false }
        while let next = top.presentedViewController { top = next }
        let presenter = top
        return await withCheckedContinuation { continuation in
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            for (title, answer) in buttons {
                alert.addAction(UIAlertAction(title: title, style: answer ? .default : .cancel) { _ in
                    continuation.resume(returning: answer)
                })
            }
            presenter.present(alert, animated: true)
        }
    }
}

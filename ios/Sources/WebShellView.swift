import SwiftUI
import WebKit

/// Shows AppState's web view. The web view itself lives in AppState, so switching tabs or screens never reloads it.
/// Photo uploads (<input type="file">) open the iPhone's own "Take Photo / Photo Library" menu.
struct WebShellView: UIViewRepresentable {
    let webView: WKWebView

    func makeUIView(context: Context) -> WKWebView {
        webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

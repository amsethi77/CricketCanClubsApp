package com.cricketclubapp

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * The website inside the app: one WebView kept for the life of the screen, wrapped in pull-to-refresh.
 * Our own pages open inside; WhatsApp, phone, email and other websites open in their own apps.
 */
class WebShell(
    context: Context,
    private val listener: Listener,
) {
    interface Listener {
        fun onPageChanged(url: String)
        fun onProgress(percent: Int)
        fun onOffline(offline: Boolean)
        /** The page asked for a file (scorecard photo): show the camera / gallery chooser. */
        fun onPickFile(callback: ValueCallback<Array<Uri>>, params: WebChromeClient.FileChooserParams): Boolean
    }

    val webView: WebView = WebView(context)
    val refreshLayout: SwipeRefreshLayout = SwipeRefreshLayout(context)
    private var mainFrameFailed = false

    init {
        configure()
        refreshLayout.layoutParams = android.view.ViewGroup.LayoutParams(MATCH_PARENT, MATCH_PARENT)
        refreshLayout.addView(webView, android.view.ViewGroup.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        refreshLayout.setColorSchemeColors(0xFF0A6E46.toInt())
        refreshLayout.setOnRefreshListener { reload() }
        // Only pull to refresh when the page is scrolled to the top.
        refreshLayout.setOnChildScrollUpCallback { _, _ -> webView.canScrollVertically(-1) }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configure() {
        webView.layoutParams = android.view.ViewGroup.LayoutParams(MATCH_PARENT, MATCH_PARENT)
        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true // sign-in is kept in localStorage
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            loadWithOverviewMode = true
            useWideViewPort = true
            mediaPlaybackRequiresUserGesture = false
            setSupportMultipleWindows(false)
            userAgentString = userAgentString + AppConfig.USER_AGENT_SUFFIX
        }
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (AppConfig.isOwnPage(uri)) return false
                openOutside(view.context, uri)
                return true
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                mainFrameFailed = false
                listener.onPageChanged(url)
            }

            override fun onPageFinished(view: WebView, url: String) {
                refreshLayout.isRefreshing = false
                if (!mainFrameFailed) listener.onOffline(false)
                listener.onPageChanged(url)
                CookieManager.getInstance().flush()
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) {
                    mainFrameFailed = true
                    refreshLayout.isRefreshing = false
                    listener.onOffline(true)
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                listener.onProgress(newProgress)
            }

            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams,
            ): Boolean = listener.onPickFile(filePathCallback, fileChooserParams)
        }
    }

    fun load(url: String) {
        webView.loadUrl(url)
    }

    fun reload() {
        if (webView.url.isNullOrEmpty()) load(AppConfig.tabs.first().url) else webView.reload()
    }

    fun goBack(): Boolean {
        if (webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return false
    }

    private fun openOutside(context: Context, uri: Uri) {
        try {
            val intent = if (uri.scheme == "intent") {
                // Only as a normal link: a web page must not be able to start hidden parts of other apps.
                Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME).apply {
                    addCategory(Intent.CATEGORY_BROWSABLE)
                    component = null
                    selector = null
                }
            } else {
                Intent(Intent.ACTION_VIEW, uri)
            }
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
        } catch (error: ActivityNotFoundException) {
            Toast.makeText(context, "No app on this phone can open that link.", Toast.LENGTH_SHORT).show()
        } catch (error: Exception) {
            Toast.makeText(context, "Couldn't open that link.", Toast.LENGTH_SHORT).show()
        }
    }
}

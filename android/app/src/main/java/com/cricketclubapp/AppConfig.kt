package com.cricketclubapp

import android.net.Uri

/**
 * Where the app finds the CricketCanClubs website. The phone app shows the same site as the web (web, iPhone and
 * Android stay in lockstep), with native tabs, camera upload, pull to refresh and an offline screen around it.
 * README "Phone apps (Android + iPhone)".
 */
object AppConfig {
    /** Change this one line when the Azure address changes (or set BASE_URL in app/build.gradle.kts). */
    val baseUrl: String = BuildConfig.BASE_URL.trimEnd('/')

    val host: String = Uri.parse(baseUrl).host.orEmpty()

    /** Added to the browser's user agent so the website can tell it runs inside the app. */
    const val USER_AGENT_SUFFIX = " CricketCanClubsApp/1.0 (Android)"

    /** Bottom tabs: label to page on the website (the website hides its own bottom bar inside the app). */
    val tabs = listOf(
        Tab("Home", "/"),
        Tab("Live", "/live"),
        Tab("Score", "/score"),
        Tab("Scorecards", "/scorecards"),
        Tab("Upload", "/scorecards/upload"),
    )

    data class Tab(val label: String, val path: String) {
        val url: String get() = baseUrl + path
    }

    /** True for pages of our own website (they open inside the app); everything else opens outside. */
    fun isOwnPage(uri: Uri?): Boolean {
        if (uri == null) return false
        val scheme = uri.scheme?.lowercase()
        return (scheme == "https" || scheme == "http") && uri.host.equals(host, ignoreCase = true)
    }
}

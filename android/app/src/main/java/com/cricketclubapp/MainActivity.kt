package com.cricketclubapp

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.FileProvider
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import java.io.File

private val Green = Color(0xFF0A6E46)
private val GreenDark = Color(0xFF064A2F)

/**
 * CricketCanClubs for Android: the website with native bottom tabs, camera upload for scorecard photos,
 * pull to refresh, back button through the pages and a "no internet" screen. README "Phone apps (Android + iPhone)".
 */
class MainActivity : ComponentActivity(), WebShell.Listener {
    private lateinit var shell: WebShell

    private var currentUrl by mutableStateOf("")
    private var progress by mutableIntStateOf(0)
    private var offline by mutableStateOf(false)

    // File chooser (scorecard photo): the page waits for exactly one answer.
    private var pendingFiles: ValueCallback<Array<Uri>>? = null
    private var cameraPhoto: Uri? = null
    private var cameraFile: File? = null

    private val pickFile = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val callback = pendingFiles ?: return@registerForActivityResult
        pendingFiles = null
        var uris: Array<Uri>? = null
        if (result.resultCode == Activity.RESULT_OK) {
            uris = WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data)
            if (uris.isNullOrEmpty()) {
                val photo = cameraPhoto
                if (photo != null && (cameraFile?.length() ?: 0L) > 0L) uris = arrayOf(photo)
            }
        }
        callback.onReceiveValue(uris)
        cameraPhoto = null
        cameraFile = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)

        shell = WebShell(this, this)
        if (savedInstanceState == null || shell.webView.restoreState(savedInstanceState) == null) {
            shell.load(startUrl(intent))
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (!shell.goBack()) {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                    isEnabled = true
                }
            }
        })

        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Green, secondary = GreenDark)) {
                Scaffold(
                    bottomBar = {
                        NavigationBar(containerColor = Color.White) {
                            AppConfig.tabs.forEach { tab ->
                                NavigationBarItem(
                                    selected = isSelected(tab),
                                    onClick = { offline = false; shell.load(tab.url) },
                                    icon = { Icon(iconFor(tab), contentDescription = tab.label) },
                                    label = { Text(tab.label, fontSize = 11.sp, maxLines = 1) },
                                    colors = NavigationBarItemDefaults.colors(
                                        selectedIconColor = Green,
                                        selectedTextColor = Green,
                                        indicatorColor = Color(0xFFDDF1E6),
                                    ),
                                )
                            }
                        }
                    },
                ) { padding ->
                    Box(modifier = Modifier.fillMaxSize().padding(padding)) {
                        AndroidView(factory = { shell.refreshLayout }, modifier = Modifier.fillMaxSize())
                        if (progress in 1..99) {
                            LinearProgressIndicator(
                                progress = { progress / 100f },
                                modifier = Modifier.fillMaxWidth().height(3.dp),
                                color = Green,
                            )
                        }
                        if (offline) OfflineScreen(onRetry = { offline = false; shell.reload() })
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // A link to one of our pages (e.g. from WhatsApp) opens that page in the app.
        intent.data?.let { if (AppConfig.isOwnPage(it)) shell.load(it.toString()) }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        shell.webView.saveState(outState)
    }

    override fun onDestroy() {
        pendingFiles?.onReceiveValue(null)
        pendingFiles = null
        super.onDestroy()
    }

    private fun startUrl(intent: Intent?): String {
        val link = intent?.data
        return if (AppConfig.isOwnPage(link)) link.toString() else AppConfig.tabs.first().url
    }

    private fun isSelected(tab: AppConfig.Tab): Boolean {
        val path = Uri.parse(currentUrl).path.orEmpty().ifEmpty { "/" }
        val best = AppConfig.tabs
            .filter { candidate -> if (candidate.path == "/") path == "/" || path == "/dashboard" else path.startsWith(candidate.path) }
            .maxByOrNull { it.path.length }
        return best == tab
    }

    private fun iconFor(tab: AppConfig.Tab): ImageVector = when (tab.path) {
        "/live" -> Icons.Filled.PlayArrow
        "/score" -> Icons.Filled.Edit
        "/scorecards" -> Icons.Filled.List
        "/scorecards/upload" -> Icons.Filled.Add
        else -> Icons.Filled.Home
    }

    // --- WebShell.Listener ---

    override fun onPageChanged(url: String) {
        currentUrl = url
    }

    override fun onProgress(percent: Int) {
        progress = percent
    }

    override fun onOffline(offline: Boolean) {
        this.offline = offline
    }

    override fun onPickFile(callback: ValueCallback<Array<Uri>>, params: WebChromeClient.FileChooserParams): Boolean {
        pendingFiles?.onReceiveValue(null)
        pendingFiles = callback

        val wantsImages = params.acceptTypes.none { it.isNotBlank() } || params.acceptTypes.any { it.startsWith("image") || it == "*/*" }
        val camera = if (wantsImages) cameraIntent() else null
        val intent = if (params.isCaptureEnabled && camera != null) {
            camera
        } else {
            val pick = try { params.createIntent() } catch (error: Exception) {
                Intent(Intent.ACTION_GET_CONTENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE)
            }
            Intent.createChooser(pick, "Scorecard photo").apply {
                if (camera != null) putExtra(Intent.EXTRA_INITIAL_INTENTS, arrayOf(camera))
            }
        }
        return try {
            pickFile.launch(intent)
            true
        } catch (error: Exception) {
            pendingFiles = null
            callback.onReceiveValue(null)
            false
        }
    }

    /** "Take photo" for the scorecard: the camera app saves into our private folder, shared through FileProvider. */
    private fun cameraIntent(): Intent? {
        val capture = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        if (capture.resolveActivity(packageManager) == null) return null
        return try {
            val folder = File(cacheDir, "scorecard_photos").apply { mkdirs() }
            folder.listFiles()?.filter { System.currentTimeMillis() - it.lastModified() > 86_400_000 }?.forEach { it.delete() }
            val file = File(folder, "scorecard_${System.currentTimeMillis()}.jpg")
            val uri = FileProvider.getUriForFile(this, "$packageName.files", file)
            cameraFile = file
            cameraPhoto = uri
            capture.putExtra(MediaStore.EXTRA_OUTPUT, uri)
            capture.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION)
            capture
        } catch (error: Exception) {
            null
        }
    }
}

@androidx.compose.runtime.Composable
private fun OfflineScreen(onRetry: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().background(Color(0xFFF3F7FB)).padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("No internet connection", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color(0xFF102A43))
        Spacer(Modifier.height(10.dp))
        Text(
            "Check your Wi-Fi or mobile data, then try again.",
            textAlign = TextAlign.Center,
            color = Color(0xFF4B647D),
        )
        Spacer(Modifier.height(20.dp))
        Button(onClick = onRetry, colors = ButtonDefaults.buttonColors(containerColor = Green)) {
            Text("Try again")
        }
    }
}

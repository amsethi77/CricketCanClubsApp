package com.cricketclubapp

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class HealthViewModel(application: Application) : AndroidViewModel(application) {
    var statusText by mutableStateOf("Connecting")
        private set

    var detailText by mutableStateOf("Checking the CricketClubApp site...")
        private set

    var isOnline by mutableStateOf(false)
        private set

    fun refresh() {
        statusText = "Connecting"
        detailText = "Checking the CricketClubApp site..."
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val connection = URL(AppConfig.healthUrl).openConnection() as HttpURLConnection
                connection.requestMethod = "GET"
                connection.connectTimeout = 10_000
                connection.readTimeout = 10_000
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                val payload = if (body.isNotEmpty()) JSONObject(body) else JSONObject()
                val llm = payload.optJSONObject("llm")
                val available = llm?.optBoolean("available", false) ?: false
                val model = llm?.optString("model", "") ?: ""
                withContext(Dispatchers.Main) {
                    if (code in 200..299 && available) {
                        isOnline = true
                        statusText = "Online"
                        detailText = if (model.isNotEmpty()) "Online · $model" else "Online"
                    } else if (llm?.optString("provider", "") == "ollama") {
                        isOnline = false
                        statusText = "Thinking"
                        detailText = "Thinking"
                    } else {
                        isOnline = false
                        statusText = "Offline"
                        detailText = "Offline"
                    }
                }
            } catch (error: Exception) {
                withContext(Dispatchers.Main) {
                    isOnline = false
                    statusText = "Offline"
                    detailText = error.localizedMessage ?: "Offline"
                }
            }
        }
    }
}

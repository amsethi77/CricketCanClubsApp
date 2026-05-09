package com.cricketclubapp

import android.os.Build

object AppConfig {
    val baseUrl: String
        get() {
            val env = System.getenv("CRICKETCLUBAPP_BASE_URL")?.trim().orEmpty()
            if (env.isNotEmpty()) return env.trimEnd('/')
            return "https://cricketcanclubs-web.azurewebsites.net"
        }

    val healthUrl: String
        get() = "$baseUrl/api/health"
}

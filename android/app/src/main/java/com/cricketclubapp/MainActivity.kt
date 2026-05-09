package com.cricketclubapp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    private val healthViewModel: HealthViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    Box(modifier = Modifier.fillMaxSize()) {
                        WebShell(modifier = Modifier.fillMaxSize())
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            horizontalAlignment = Alignment.End,
                            verticalArrangement = Arrangement.Top,
                        ) {
                            StatusChip(
                                text = healthViewModel.statusText,
                                detail = healthViewModel.detailText,
                                online = healthViewModel.isOnline,
                            )
                            Button(
                                onClick = { healthViewModel.refresh() },
                                colors = ButtonDefaults.buttonColors(containerColor = Color.White),
                                modifier = Modifier.padding(top = 8.dp)
                            ) {
                                Text("Refresh status", color = Color(0xFF102A43), fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                }
            }
        }
        healthViewModel.refresh()
    }
}

@Composable
private fun StatusChip(text: String, detail: String, online: Boolean) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.92f)),
        shape = RoundedCornerShape(999.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
        modifier = Modifier.padding(4.dp)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(RoundedCornerShape(999.dp))
                    .background(if (online) Color(0xFF1DB954) else Color(0xFFD62839))
            )
            Column(modifier = Modifier.padding(start = 8.dp)) {
                Text(
                    text = text,
                    color = Color(0xFF102A43),
                    fontWeight = FontWeight.SemiBold
                )
                Text(
                    text = detail,
                    color = Color(0xFF4B647D),
                    fontWeight = FontWeight.Normal
                )
            }
        }
    }
}

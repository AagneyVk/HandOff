package dev.handoff.client

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); setContent { HandOffApp() } }
}
private data class AppWindow(val id: String, val title: String, val app: String)

@Composable
private fun HandOffApp() {
    var address by rememberSaveable { mutableStateOf("") }
    var status by remember { mutableStateOf("Connect to your computer") }
    var connected by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var windows by remember { mutableStateOf(emptyList<AppWindow>()) }
    val client = remember {
        ProtocolClient(onState = { value ->
            status = value
            busy = value == "Connecting"
            if (value.startsWith("Disconnected")) { connected = false; windows = emptyList() }
        }, onMessage = { message ->
            val payload = message.getJSONObject("payload")
            when (message.getString("type")) {
                "capabilities" -> { connected = true; busy = false; status = payload.optString("host_name", "Computer") }
                "windows.snapshot" -> {
                    val array = payload.getJSONArray("windows")
                    windows = (0 until array.length()).map { array.getJSONObject(it).let { w -> AppWindow(w.getString("id"), w.getString("title"), w.optString("app")) } }
                }
                "error" -> { busy = false; status = payload.optString("message", "Request failed") }
            }
        })
    }
    DisposableEffect(client) { onDispose { client.dispose() } }
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    MaterialTheme(colorScheme = if (dark) darkColorScheme() else lightColorScheme()) {
        Scaffold { padding ->
            LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                item { Spacer(Modifier.height(24.dp)); Text("HandOff", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.SemiBold); Text("Your apps. Across devices.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
                item {
                    ElevatedCard(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(status, style = MaterialTheme.typography.titleMedium)
                            if (!connected) {
                                Text("Start the Windows host, then enter its address. Both devices must be on the same trusted network.")
                                OutlinedTextField(value = address, onValueChange = { address = it }, label = { Text("Computer IP address") }, placeholder = { Text("192.168.1.10") }, singleLine = true, enabled = !busy, modifier = Modifier.fillMaxWidth())
                                Button(onClick = { busy = true; client.connect(address) }, enabled = address.isNotBlank() && !busy) { Text(if (busy) "Connecting…" else "Connect") }
                                if (busy) TextButton(onClick = { client.close(); busy = false; status = "Connection cancelled" }) { Text("Cancel") }
                            } else {
                                Row {
                                    TextButton(onClick = { client.send("windows.list", JSONObject()) }) { Text("Refresh apps") }
                                    TextButton(onClick = { client.close(); connected = false; windows = emptyList(); status = "Disconnected" }) { Text("Disconnect") }
                                }
                            }
                        }
                    }
                }
                item {
                    Text("Preview build", style = MaterialTheme.typography.labelLarge)
                    Text("This build can connect and list Windows apps. Live video, audio and secure pairing are not implemented yet; continuing an app is unavailable.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (connected) {
                    item { Text("Open apps", style = MaterialTheme.typography.titleLarge) }
                    if (windows.isEmpty()) item { Text("No available windows. Open an app on your computer and refresh.") }
                    items(windows, key = { it.id }) { window ->
                        OutlinedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(window.title, fontWeight = FontWeight.Medium)
                                Text(window.app, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                item { Spacer(Modifier.height(24.dp)) }
            }
        }
    }
}

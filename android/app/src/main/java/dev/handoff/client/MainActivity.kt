package dev.handoff.client

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import kotlin.math.abs

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { HandOffHarness() }
    }
}

@Composable
private fun HandOffHarness() {
    var host by remember { mutableStateOf("192.168.1.2") }
    var state by remember { mutableStateOf("Not connected") }
    var lastEvent by remember { mutableStateOf("—") }
    var running by remember { mutableStateOf(false) }
    val client = remember {
        ProtocolClient(
            onMessage = { msg ->
                val type = msg.optString("type")
                lastEvent = type
                if (type == "session.started") running = true
            },
            onState = { state = it },
        )
    }
    DisposableEffect(Unit) { onDispose { client.close() } }

    MaterialTheme {
        Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("HandOff V0", style = MaterialTheme.typography.headlineMedium)
            Text("$state · last: $lastEvent", style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(
                value = host,
                onValueChange = { host = it },
                label = { Text("Host LAN IP") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { client.connect(host.trim()) }) { Text("Connect") }
                Button(onClick = { client.startFakeSession() }) { Text("Start test") }
            }

            Text(if (running) "Synthetic interaction surface" else "Start the test session to enable input")
            MotionSurface(enabled = running, client = client)
            Text("Tap sends normalized pointer input. Drag vertically sends scroll. The moving grid is intentionally rendered locally in V0; real encoded frames replace it next.")
        }
    }
}

@Composable
private fun MotionSurface(enabled: Boolean, client: ProtocolClient) {
    var phase by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(enabled) {
        while (enabled) {
            withFrameNanos { phase = ((it / 1_000_000L) % 4000L) / 4000f }
        }
    }
    Canvas(
        Modifier
            .fillMaxWidth()
            .aspectRatio(16f / 9f)
            .background(Color(0xFF111318))
            .pointerInput(enabled) {
                if (enabled) detectTapGestures { p ->
                    client.pointer(p.x / size.width, p.y / size.height, "tap")
                }
            }
            .pointerInput(enabled) {
                if (enabled) detectDragGestures(
                    onDragEnd = { },
                    onDrag = { change, drag ->
                        change.consume()
                        if (abs(drag.y) > abs(drag.x)) client.scroll(0f, -drag.y / size.height)
                    }
                )
            }
    ) {
        val cols = 8
        val rows = 5
        for (x in 1 until cols) drawLine(Color.DarkGray, Offset(size.width * x / cols, 0f), Offset(size.width * x / cols, size.height))
        for (y in 1 until rows) drawLine(Color.DarkGray, Offset(0f, size.height * y / rows), Offset(size.width, size.height * y / rows))
        val cx = size.width * (0.1f + 0.8f * phase)
        drawCircle(Color.White, radius = 18.dp.toPx(), center = Offset(cx, size.height / 2f))
    }
}

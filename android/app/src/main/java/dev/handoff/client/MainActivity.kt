package dev.handoff.client

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlin.math.abs

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { HandOffApp() }
    }
}

private enum class ConnectionState { Looking, Ready, Connecting, Live, Unavailable }

@Composable
private fun HandOffApp() {
    var connection by remember { mutableStateOf(ConnectionState.Looking) }
    var detail by remember { mutableStateOf("Looking for your computer…") }
    var lastEvent by remember { mutableStateOf("—") }
    val client = remember {
        ProtocolClient(
            onMessage = { msg ->
                lastEvent = msg.optString("type")
                when (msg.optString("type")) {
                    "capabilities" -> { connection = ConnectionState.Ready; detail = "Nearby · Ready" }
                    "session.started" -> { connection = ConnectionState.Live; detail = "Live" }
                    "error" -> { connection = ConnectionState.Unavailable; detail = "Couldn't continue. Tap to try again." }
                }
            },
            onState = { raw ->
                if (raw.contains("connected", ignoreCase = true)) {
                    connection = ConnectionState.Connecting
                    detail = "Preparing…"
                }
            },
        )
    }
    DisposableEffect(Unit) { onDispose { client.close() } }

    HandOffTheme {
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            AnimatedContent(targetState = connection == ConnectionState.Live, label = "handoff") { live ->
                if (live) LiveSurface(client) { client.close(); connection = ConnectionState.Looking; detail = "Looking for your computer…" }
                else Home(connection, detail, lastEvent,
                    onContinue = { connection = ConnectionState.Connecting; detail = "Preparing…"; client.startFakeSession() },
                    onRetry = { connection = ConnectionState.Looking; detail = "Looking for your computer…" })
            }
        }
    }
}

@Composable
private fun Home(state: ConnectionState, detail: String, lastEvent: String, onContinue: () -> Unit, onRetry: () -> Unit) {
    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = 22.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        Spacer(Modifier.height(12.dp))
        Text("HandOff", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.SemiBold)
        Text("Pick up exactly where you left off.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(8.dp))

        ElevatedCard(
            Modifier.fillMaxWidth().clickable(enabled = state == ConnectionState.Unavailable, onClick = onRetry),
            shape = RoundedCornerShape(28.dp),
            colors = CardDefaults.elevatedCardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)
        ) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(shape = RoundedCornerShape(14.dp), color = MaterialTheme.colorScheme.surfaceContainerHighest) {
                        Text("▰", Modifier.padding(horizontal = 15.dp, vertical = 12.dp), style = MaterialTheme.typography.titleLarge)
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Your computer", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text(detail, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    AnimatedVisibility(state == ConnectionState.Looking || state == ConnectionState.Connecting) {
                        CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                    }
                }

                if (state == ConnectionState.Ready || state == ConnectionState.Connecting) {
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Continue current activity", fontWeight = FontWeight.Medium)
                            Text("The running window stays exactly where it is.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Button(onClick = onContinue, enabled = state == ConnectionState.Ready, shape = RoundedCornerShape(50)) {
                            Text(if (state == ConnectionState.Connecting) "Preparing" else "Continue")
                        }
                    }
                }
            }
        }

        Spacer(Modifier.weight(1f))
        Text(
            "Paired devices reconnect automatically. Advanced network and stream details stay out of the way unless you need them.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        if (lastEvent != "—") Text("Diagnostics · $lastEvent", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.outline)
    }
}

@Composable
private fun LiveSurface(client: ProtocolClient, onReturn: () -> Unit) {
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        MotionSurface(true, client)
        Surface(
            modifier = Modifier.align(Alignment.TopCenter).statusBarsPadding().padding(top = 10.dp),
            shape = RoundedCornerShape(50),
            color = MaterialTheme.colorScheme.surface.copy(alpha = .92f),
            tonalElevation = 6.dp
        ) {
            Row(Modifier.padding(start = 16.dp, end = 8.dp, top = 7.dp, bottom = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Live", fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.width(12.dp))
                TextButton(onClick = onReturn) { Text("Return") }
            }
        }
    }
}

@Composable
private fun MotionSurface(enabled: Boolean, client: ProtocolClient) {
    var phase by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(enabled) { while (enabled) withFrameNanos { phase = ((it / 1_000_000L) % 4000L) / 4000f } }
    Canvas(
        Modifier.fillMaxSize().clip(RoundedCornerShape(0.dp)).background(Color(0xFF090A0C))
            .pointerInput(enabled) { if (enabled) detectTapGestures { p -> client.pointer(p.x / size.width, p.y / size.height, "tap") } }
            .pointerInput(enabled) { if (enabled) detectDragGestures { change, drag -> change.consume(); if (abs(drag.y) > abs(drag.x)) client.scroll(0f, -drag.y / size.height) } }
    ) {
        for (x in 1 until 8) drawLine(Color(0xFF24262A), Offset(size.width * x / 8, 0f), Offset(size.width * x / 8, size.height))
        for (y in 1 until 12) drawLine(Color(0xFF24262A), Offset(0f, size.height * y / 12), Offset(size.width, size.height * y / 12))
        drawCircle(Color.White, radius = 18.dp.toPx(), center = Offset(size.width * (.1f + .8f * phase), size.height / 2f))
    }
}

@Composable
private fun HandOffTheme(content: @Composable () -> Unit) {
    val scheme = if (androidx.compose.foundation.isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()
    MaterialTheme(colorScheme = scheme, typography = Typography(), content = content)
}

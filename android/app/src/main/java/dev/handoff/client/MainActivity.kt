package dev.handoff.client

import android.graphics.Bitmap
import android.os.Bundle
import android.view.WindowManager
import android.view.SurfaceView
import android.view.SurfaceHolder
import androidx.compose.ui.viewinterop.AndroidView
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

class MainActivity : ComponentActivity() {
    private var background: (() -> Unit)? = null
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { HandOffApp(this) { background = it } }
    }
    override fun onStop() { background?.invoke(); super.onStop() }
}
private data class AppWindow(val id: String, val title: String, val app: String)

@Composable
private fun HandOffApp(activity: MainActivity, bindBackground: ((() -> Unit)?) -> Unit) {
    val context = LocalContext.current
    val store = remember { CredentialStore(context) }
    var paired by remember { mutableStateOf(store.load()) }
    var status by remember { mutableStateOf("Ready when you are") }
    var connected by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var live by remember { mutableStateOf(false) }
    var pairingText by remember { mutableStateOf("") }
    var showManual by remember { mutableStateOf(false) }
    var windows by remember { mutableStateOf(emptyList<AppWindow>()) }
    var bitmap by remember { mutableStateOf<Bitmap?>(null) }
    var sequence by remember { mutableIntStateOf(0) }
    var compatibility by remember { mutableStateOf(false) }
    var audioChoice by remember { mutableStateOf(false) }
    var videoCodec by remember { mutableStateOf("jpeg") }
    var videoSize by remember { mutableStateOf(640 to 480) }
    var title by remember { mutableStateOf("Your app") }
    val client = remember {
        ProtocolClient(store, onState = { value ->
            status = value
            busy = value == "Connecting securely…"
            connected = value == "Connected"
            if (!connected) { live = false; bitmap = null; windows = emptyList() }
            paired = store.load()
        }, onFrame = { frame, seq -> bitmap = frame; sequence = seq },
        onVideoFrame = { width, height, seq -> videoSize = width to height; sequence = seq },
        onAudio = { status = "Computer audio · All apps" }, onMessage = { msg ->
            when (msg.getString("type")) {
                "windows" -> {
                    val array = msg.getJSONArray("windows")
                    windows = (0 until array.length()).map { array.getJSONObject(it).let { w -> AppWindow(w.getString("id"), w.getString("title"), w.optString("app")) } }
                }
                "started" -> {
                    videoCodec = msg.optString("codec", "jpeg")
                    videoSize = msg.optInt("width", 640) to msg.optInt("height", 480)
                    live = true; busy = false
                    status = if (videoCodec == "h264") "H.264 · ${msg.optString("encoder")}" else "Compatibility video · JPEG"
                }
                "audio.stopped" -> { status = msg.optString("message", "Audio stopped") }
                "stopped" -> { live = false; busy = false; bitmap = null; status = msg.optString("message", "Returned to computer") }
                "error" -> { busy = false; status = msg.optString("message", "Try again") }
            }
        })
    }
    DisposableEffect(client) {
        bindBackground { client.close(); connected = false; live = false; busy = false; bitmap = null; windows = emptyList(); status = "Paused · Reconnect to continue" }
        onDispose { bindBackground(null); client.dispose() }
    }
    DisposableEffect(live) {
        if (live) activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }
    fun pair(raw: String) {
        try { val link = Pairing.parse(raw); pairingText = ""; client.pair(link) }
        catch (e: Exception) { status = e.message ?: "That pairing link is invalid" }
    }
    val export = rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) {
            try {
                context.contentResolver.openOutputStream(uri)?.use { it.write(client.report().toString(2).toByteArray()) }
                status = "Session report saved"
            } catch (_: Exception) { status = "Could not save the report" }
        }
    }
    val scanner = rememberLauncherForActivityResult(ScanContract()) { result -> result.contents?.let { pair(it) } }
    BackHandler(live) { client.stop() }
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    val scheme = if (dark) darkColorScheme(primary = Color(0xFF77D8C4), background = Color(0xFF111918), surface = Color(0xFF182321))
                 else lightColorScheme(primary = Color(0xFF006B58), background = Color(0xFFF6F9F7), surface = Color.White)
    MaterialTheme(colorScheme = scheme) {
        Scaffold { padding ->
            if (live) {
                Column(Modifier.fillMaxSize().padding(padding).background(Color.Black)) {
                    Surface {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(title, Modifier.weight(1f), maxLines = 1, fontWeight = FontWeight.SemiBold)
                                TextButton(onClick = { client.stop() }) { Text("Return") }
                            }
                            Text(status, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                        if (videoCodec == "h264") LiveVideo(videoSize, sequence, client)
                        else bitmap?.let { frame -> LiveImage(frame, sequence, client) } ?: CircularProgressIndicator()
                    }
                    Text("Tap to click · Swipe to scroll", color = Color.White, modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.labelMedium)
                }
            } else {
                LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal = 24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    item {
                        Spacer(Modifier.height(24.dp))
                        Text("HANDOFF", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.height(10.dp))
                        Text("Pick up where\nyou left off.", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(8.dp))
                        Text("Keep your app running on your computer. Bring its window to your phone.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    item {
                        ElevatedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text(if (connected) "Your computer is connected" else "Your computer", style = MaterialTheme.typography.titleLarge)
                                Text(status, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                                if (connected) {
                                    Row {
                                        TextButton(onClick = { client.send("windows") }) { Text("Refresh apps") }
                                        TextButton(onClick = { client.close(); connected = false; busy = false; windows = emptyList(); status = "Disconnected" }) { Text("Disconnect") }
                                    }
                                } else if (busy) {
                                    TextButton(onClick = { client.close(); busy = false; status = "Connection cancelled" }) { Text("Cancel") }
                                } else {
                                    paired?.let { c ->
                                        Button(onClick = { client.reconnect(c) }, modifier = Modifier.fillMaxWidth()) { Text("Connect to ${c.host}") }
                                    }
                                    OutlinedButton(onClick = { scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setPrompt("Scan the QR code in HandOff on your computer").setBeepEnabled(false)) }, modifier = Modifier.fillMaxWidth()) { Text("Pair with QR code") }
                                    TextButton(onClick = { showManual = !showManual }) { Text("Use a pairing link") }
                                    if (showManual) {
                                        OutlinedTextField(pairingText, { pairingText = it }, label = { Text("Paste pairing link") }, modifier = Modifier.fillMaxWidth(), maxLines = 3)
                                        Button(onClick = { pair(pairingText) }, enabled = pairingText.isNotBlank()) { Text("Pair computer") }
                                    }
                                    if (paired != null) TextButton(onClick = { store.clear(); paired = null; status = "Computer forgotten" }) { Text("Forget computer") }
                                }
                            }
                        }
                    }
                    if (connected) {
                        item {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = compatibility, onCheckedChange = { compatibility = it }, enabled = !busy)
                                Text("Compatibility video (JPEG)")
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = audioChoice, onCheckedChange = { audioChoice = it }, enabled = !busy)
                                Text("Play computer audio (all apps)")
                            }
                            Text("Audio also needs approval on your computer.", style = MaterialTheme.typography.bodySmall)
                            Spacer(Modifier.height(16.dp))
                            Text("Shared with you", style = MaterialTheme.typography.titleLarge)
                        }
                        if (windows.isEmpty()) item { Text("Select an app in HandOff on your computer, click Share selected app, then refresh here.") }
                        items(windows, key = { it.id }) { window ->
                            OutlinedCard(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(window.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                    Text(window.app, style = MaterialTheme.typography.bodySmall)
                                    Button(onClick = { title = window.title; busy = true; status = "Opening your app…"; client.start(window.id, compatibility, audioChoice) }, enabled = !busy) { Text("Continue here") }
                                }
                            }
                        }
                    }
                    item {
                        TextButton(onClick = { export.launch("handoff-session.json") }, enabled = client.report().optInt("decoded_frames") > 0) { Text("Export session report") }
                        Text("Private by design", style = MaterialTheme.typography.titleMedium)
                        Text("Pair directly with your computer. Only the app you choose is shared over your local network. Stop sharing on either device at any time.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(24.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun LiveImage(frame: Bitmap, sequence: Int, client: ProtocolClient) {
    Image(frame.asImageBitmap(), contentDescription = "Shared application", contentScale = ContentScale.Fit,
        modifier = Modifier.fillMaxSize().remoteInput(frame.width, frame.height, sequence, client))
}

@Composable
private fun LiveVideo(dimensions: Pair<Int, Int>, sequence: Int, client: ProtocolClient) {
    BoxWithConstraints(Modifier.fillMaxSize().remoteInput(dimensions.first, dimensions.second, sequence, client), contentAlignment = Alignment.Center) {
        val ratio = dimensions.first.toFloat() / dimensions.second
        val width = minOf(maxWidth, maxHeight * ratio)
        AndroidView(modifier = Modifier.size(width, width / ratio), factory = { context ->
            SurfaceView(context).also { view ->
                view.holder.addCallback(object : SurfaceHolder.Callback {
                    override fun surfaceCreated(holder: SurfaceHolder) { client.setSurface(holder.surface) }
                    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) { client.setSurface(holder.surface) }
                    override fun surfaceDestroyed(holder: SurfaceHolder) { client.setSurface(null) }
                })
            }
        })
    }
}

@Composable
private fun Modifier.remoteInput(width: Int, height: Int, sequence: Int, client: ProtocolClient): Modifier {
    val currentSequence by rememberUpdatedState(sequence)
    val dimensions by rememberUpdatedState(width to height)
    return this
        .pointerInput(Unit) {
            detectTapGestures { point ->
                contentPoint(point.x, point.y, size.width.toFloat(), size.height.toFloat(), dimensions.first, dimensions.second)
                    ?.let { client.tap(it.first, it.second, currentSequence) }
            }
        }
        .pointerInput(Unit) {
            var accumulated = 0f
            detectDragGestures(onDragStart = { accumulated = 0f }, onDrag = { change, drag ->
                change.consume(); accumulated += drag.y
                if (kotlin.math.abs(accumulated) >= 24f) {
                    contentPoint(change.position.x, change.position.y, size.width.toFloat(), size.height.toFloat(), dimensions.first, dimensions.second)
                        ?.let { client.scroll(it.first, it.second, (-accumulated / 60f).coerceIn(-5f, 5f), currentSequence) }
                    accumulated = 0f
                }
            })
        }
}

package dev.handoff.client

import android.graphics.Bitmap
import android.graphics.Point
import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.hardware.display.DisplayManager
import android.os.Bundle
import android.provider.Settings
import android.view.WindowManager
import android.view.Display
import android.view.SurfaceView
import android.view.SurfaceHolder
import androidx.compose.ui.viewinterop.AndroidView
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

class MainActivity : ComponentActivity() {
    private var background: (() -> Unit)? = null
    private var projectionFlow = false
    private var settingsFlow = false
    fun keepSettingsConnection() { settingsFlow = true }
    override fun onResume() { super.onResume(); settingsFlow = false }
    fun keepProjectionConnection(value: Boolean) { projectionFlow = value }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { HandOffApp(this) { background = it } }
    }
    override fun onStop() { if (!projectionFlow && !settingsFlow) background?.invoke(); super.onStop() }
}
private data class AppWindow(val id: String, val title: String, val app: String, val kind: String)

private fun controlSettingsHint(): String = when (android.os.Build.MANUFACTURER.lowercase()) {
    "samsung" -> "Galaxy path: Settings → Accessibility → Installed apps → HandOff phone control."
    "xiaomi", "redmi", "poco" -> "Xiaomi/POCO path: Settings → Additional settings → Accessibility → Downloaded apps. Then set HandOff Battery saver to No restrictions and allow Auto-start if offered."
    "oneplus", "oppo", "realme" -> "OnePlus/OPPO/Realme path: Settings → Additional settings → Accessibility → Downloaded apps. Also allow background activity for HandOff."
    "vivo", "iqoo" -> "Vivo/iQOO path: Settings → Shortcuts & accessibility → Accessibility → Downloaded apps. Also allow background power use for HandOff."
    "huawei", "honor" -> "Huawei/Honor path: Settings → Accessibility features → Accessibility → Installed services. In App launch, manage HandOff manually and allow background running."
    else -> "Android path: Settings → Accessibility → Downloaded apps / Installed apps → HandOff phone control."
}

@OptIn(ExperimentalMaterial3Api::class)
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
    var dragMode by remember { mutableStateOf(false) }
    var keyboardSupported by remember { mutableStateOf(false) }
    var textEntry by remember { mutableStateOf("") }
    var profile by remember { mutableStateOf("balanced") }
    var phoneSharing by remember { mutableStateOf(false) }
    var phoneAudio by remember { mutableStateOf(false) }
    var projectionPending by remember { mutableStateOf(false) }
    var controlEnabled by remember { mutableStateOf(RemoteControlService.enabled()) }
    var controlInstalled by remember { mutableStateOf(RemoteControlService.installed(context)) }
    var controlEnabledInSettings by remember { mutableStateOf(RemoteControlService.enabledInSettings(context)) }
    var showControlHelp by remember { mutableStateOf(false) }
    var shareAfterControl by remember { mutableStateOf(false) }
    var controlsExpanded by remember { mutableStateOf(true) }
    var showKeyboardControls by remember { mutableStateOf(false) }
    val client = remember {
        ProtocolClient(store, onState = { value ->
            status = value
            busy = value == "Connecting securely…"
            connected = value == "Connected"
            if (!connected) { live = false; showKeyboardControls = false; bitmap = null; windows = emptyList() }
            paired = store.load()
        }, onFrame = { frame, seq -> bitmap = frame; sequence = seq },
        onVideoFrame = { width, height, seq -> videoSize = width to height; sequence = seq },
        onAudio = { status = "Computer audio · All apps" }, onMessage = { msg ->
            when (msg.getString("type")) {
                "windows" -> {
                    val array = msg.getJSONArray("windows")
                    windows = (0 until array.length()).map { array.getJSONObject(it).let { w -> AppWindow(w.getString("id"), w.getString("title"), w.optString("app"), w.optString("kind", "window")) } }
                }
                "started" -> {
                    videoCodec = msg.optString("codec", "jpeg")
                    videoSize = msg.optInt("width", 640) to msg.optInt("height", 480)
                    val controls = msg.optJSONArray("controls")
                    keyboardSupported = controls != null && (0 until controls.length()).any { controls.optString(it) == "text" }
                    live = true; busy = false
                    status = if (videoCodec == "h264") "H.264 · ${msg.optString("encoder")}" else "Compatibility video · JPEG"
                }
                "video.fallback" -> { status = msg.optString("message"); compatibility = true }
                "audio.stopped" -> { status = msg.optString("message", "Audio stopped") }
                "source.ready" -> { phoneSharing = true; projectionPending = false; status = "Phone is live on your computer" }
                "source.stopped", "source.localStopped" -> {
                    phoneSharing = false; projectionPending = false; activity.keepProjectionConnection(false)
                    status = msg.optString("message", "Phone sharing stopped")
                }
                "stopped" -> { live = false; showKeyboardControls = false; busy = false; bitmap = null; status = msg.optString("message", "Returned to computer") }
                "error" -> {
                    busy = false
                    if (projectionPending) { projectionPending = false; activity.keepProjectionConnection(false) }
                    status = msg.optString("message", "Try again")
                }
            }
        })
    }
    LaunchedEffect(client) {
        while (true) {
            controlEnabled = RemoteControlService.enabled()
            controlInstalled = RemoteControlService.installed(context)
            controlEnabledInSettings = RemoteControlService.enabledInSettings(context)
            client.refreshPhoneControls()
            kotlinx.coroutines.delay(500)
        }
    }
    DisposableEffect(client) {
        bindBackground { client.close(); connected = false; live = false; busy = false; bitmap = null; windows = emptyList(); status = "Paused · Reconnect to continue" }
        onDispose { bindBackground(null); client.dispose() }
    }
    DisposableEffect(live, videoSize) {
        val insets = WindowCompat.getInsetsController(activity.window, activity.window.decorView)
        if (live) {
            activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            activity.requestedOrientation = if (videoSize.first >= videoSize.second)
                ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE else ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
            insets.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            insets.hide(WindowInsetsCompat.Type.systemBars())
        }
        onDispose {
            activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            insets.show(WindowInsetsCompat.Type.systemBars())
        }
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
    val projectionLauncher = rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            val size = Point()
            @Suppress("DEPRECATION")
            context.getSystemService(DisplayManager::class.java).getDisplay(Display.DEFAULT_DISPLAY)?.getRealSize(size)
            val rawWidth = if (size.x > 0) size.x else context.resources.displayMetrics.widthPixels
            val rawHeight = if (size.y > 0) size.y else context.resources.displayMetrics.heightPixels
            val scale = minOf(1f, 1280f / maxOf(rawWidth, rawHeight), 720f / minOf(rawWidth, rawHeight))
            val width = maxOf(2, (rawWidth * scale).toInt() / 2 * 2)
            val height = maxOf(2, (rawHeight * scale).toInt() / 2 * 2)
            client.beginPhoneShare(context, result.resultCode, result.data!!, width, height, phoneAudio)
            status = "Starting secure phone stream…"
        } else {
            projectionPending = false; activity.keepProjectionConnection(false); status = "Phone sharing cancelled"
        }
    }
    fun requestProjection() {
        projectionPending = true; activity.keepProjectionConnection(true)
        val manager = context.getSystemService(MediaProjectionManager::class.java)
        val intent = if (android.os.Build.VERSION.SDK_INT >= 34)
            manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
        else manager.createScreenCaptureIntent()
        projectionLauncher.launch(intent)
    }
    fun openControlSettings() {
        try {
            activity.keepSettingsConnection()
            context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        } catch (_: Exception) { status = "This device could not open Accessibility settings" }
    }
    fun openAppInfo() {
        try {
            activity.keepSettingsConnection()
            context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                android.net.Uri.parse("package:${context.packageName}")))
        } catch (_: Exception) { status = "This device could not open HandOff app info" }
    }
    fun openBatterySettings() {
        try {
            activity.keepSettingsConnection()
            context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        } catch (_: Exception) { openAppInfo() }
    }
    val audioPermission = rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) requestProjection()
        else { projectionPending = false; activity.keepProjectionConnection(false); status = "Audio permission denied; turn phone audio off to share video only" }
    }
    LaunchedEffect(controlEnabled, shareAfterControl) {
        if (shareAfterControl && controlEnabled) {
            shareAfterControl = false
            if (phoneAudio && androidx.core.content.ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                activity.keepProjectionConnection(true)
                audioPermission.launch(Manifest.permission.RECORD_AUDIO)
            } else requestProjection()
        }
    }
    BackHandler(live) { if (showKeyboardControls) showKeyboardControls = false else client.stop() }
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    val scheme = if (dark) darkColorScheme(primary = Color(0xFF77D8C4), background = Color(0xFF111918), surface = Color(0xFF182321))
                 else lightColorScheme(primary = Color(0xFF006B58), background = Color(0xFFF6F9F7), surface = Color.White)
    MaterialTheme(colorScheme = scheme) {
        if (showControlHelp) AlertDialog(
            onDismissRequest = { showControlHelp = false },
            title = { Text("Allow laptop control") },
            text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("This setting is not listed under Permissions. Android puts remote touch under Accessibility special access.", fontWeight = FontWeight.SemiBold)
                Text("1. Open App info. On Android 13 or newer, tap ⋮ and Allow restricted settings. Samsung/Pixel may not show this step.")
                Text("2. Open Accessibility → Installed apps / Downloaded apps → HandOff phone control → Use service.")
                Text(controlSettingsHint())
                Text(if (controlInstalled) "HandOff phone control is installed ✓" else "Android has not discovered the HandOff control service. Reinstall the newest signed APK and restart the phone.")
                Text(if (controlEnabledInSettings) "Accessibility switch is on ✓" else "Accessibility switch is still off")
                Text("Xiaomi/POCO/Redmi, OnePlus/OPPO/Realme and Vivo/iQOO may also require HandOff to be allowed in Battery or Auto-start settings so their system does not stop the service.")
                Text("HandOff now requests the entire default display on Android 14+ so remote coordinates match the real screen.")
            } },
            confirmButton = { TextButton(onClick = {
                showControlHelp = false
                openControlSettings()
            }) { Text("Open Accessibility") } },
            dismissButton = { TextButton(onClick = { openAppInfo() }) { Text("App info first") } }
        )
        if (showKeyboardControls && live) ModalBottomSheet(onDismissRequest = { showKeyboardControls = false }) {
            Column(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 20.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Computer keyboard", style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(textEntry, { textEntry = it.take(256) }, modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Type on computer") }, singleLine = true,
                    trailingIcon = { TextButton(onClick = {
                        if (textEntry.isNotEmpty()) { client.text(textEntry, sequence); textEntry = ""; showKeyboardControls = false }
                    }) { Text("Send") } })
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                    TextButton(onClick = { client.key("backspace", sequence) }) { Text("⌫") }
                    TextButton(onClick = { client.key("enter", sequence) }) { Text("Enter") }
                    TextButton(onClick = { client.key("escape", sequence) }) { Text("Esc") }
                    TextButton(onClick = { client.key("left", sequence) }) { Text("←") }
                    TextButton(onClick = { client.key("right", sequence) }) { Text("→") }
                }
                Text("Close this panel to return to direct touch control.", style = MaterialTheme.typography.bodySmall)
            }
        }
        Scaffold { padding ->
            if (live) {
                Row(Modifier.fillMaxSize().padding(padding).background(Color.Black)) {
                    Box(Modifier.weight(1f).fillMaxHeight(), contentAlignment = Alignment.Center) {
                        if (videoCodec == "h264") LiveVideo(videoSize, sequence, client, dragMode)
                        else bitmap?.let { frame -> LiveImage(frame, sequence, client, dragMode) } ?: CircularProgressIndicator()
                    }
                    Surface(Modifier.width(if (controlsExpanded) 108.dp else 40.dp).fillMaxHeight(),
                        color = MaterialTheme.colorScheme.surface) {
                        Column(Modifier.fillMaxSize().padding(horizontal = 4.dp, vertical = 6.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterVertically)) {
                            TextButton(onClick = { controlsExpanded = !controlsExpanded }) {
                                Text(if (controlsExpanded) "Hide ›" else "‹")
                            }
                            if (controlsExpanded) {
                                Text(title, maxLines = 2, style = MaterialTheme.typography.labelSmall,
                                    fontWeight = FontWeight.SemiBold)
                                FilledTonalButton(onClick = { dragMode = false }, enabled = dragMode,
                                    contentPadding = PaddingValues(horizontal = 8.dp)) { Text("Scroll") }
                                FilledTonalButton(onClick = { dragMode = true }, enabled = !dragMode,
                                    contentPadding = PaddingValues(horizontal = 8.dp)) { Text("Drag") }
                                if (keyboardSupported) OutlinedButton(onClick = { showKeyboardControls = true },
                                    contentPadding = PaddingValues(horizontal = 8.dp)) { Text("Keys") }
                                Spacer(Modifier.weight(1f))
                                TextButton(onClick = { client.stop() }) { Text("Return") }
                            }
                        }
                    }
                }
            } else {
                LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal = 24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    item {
                        Spacer(Modifier.height(24.dp))
                        Text("HANDOFF", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.height(10.dp))
                        Text("Pick up where\nyou left off.", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.SemiBold)
                        Spacer(Modifier.height(8.dp))
                        Text("Bring a running computer app—or an entire display you explicitly approve—to your phone.", color = MaterialTheme.colorScheme.onSurfaceVariant)
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
                            ElevatedCard(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Text("Use phone on computer", style = MaterialTheme.typography.titleLarge)
                                    Text("Android will ask whether to share one app or the whole phone. Nothing starts without that system confirmation.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Checkbox(phoneAudio, { phoneAudio = it }, enabled = !phoneSharing && !projectionPending)
                                        Text("Share phone media audio")
                                    }
                                    if (phoneAudio) Text("Android calls this permission ‘Record audio’. HandOff captures allowed app playback, not the microphone.", style = MaterialTheme.typography.bodySmall)
                                    Text(when {
                                        controlEnabled -> "Laptop control is ready ✓"
                                        controlEnabledInSettings -> "Accessibility is on, but the phone stopped its service"
                                        else -> "View only · remote touch is not enabled"
                                    }, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
                                    if (!controlEnabled) {
                                        Text("Remote touch is Accessibility special access—not an item under App permissions.",
                                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                            OutlinedButton(onClick = { openAppInfo() }) { Text("1 App info") }
                                            Button(onClick = { openControlSettings() }) { Text("2 Accessibility") }
                                        }
                                        if (controlEnabledInSettings) OutlinedButton(onClick = { openBatterySettings() }) {
                                            Text("Battery / background settings")
                                        }
                                    }
                                    TextButton(onClick = { showControlHelp = true }) { Text("Show exact control setup") }
                                    if (phoneSharing) Button(onClick = { PhoneProjectionService.stop(context) }, modifier = Modifier.fillMaxWidth()) { Text("Return to phone") }
                                    else {
                                        Button(onClick = {
                                            if (!controlEnabled) {
                                                shareAfterControl = true
                                                status = "Enable HandOff phone control; sharing will continue when you return"
                                                openControlSettings()
                                            } else if (phoneAudio && androidx.core.content.ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
                                                { activity.keepProjectionConnection(true); audioPermission.launch(Manifest.permission.RECORD_AUDIO) }
                                            else requestProjection()
                                        }, enabled = !projectionPending && !live, modifier = Modifier.fillMaxWidth()) {
                                            Text(if (projectionPending) "Waiting for Android…" else if (controlEnabled) "Share and control phone" else "Enable control & share phone")
                                        }
                                        if (!controlEnabled) TextButton(onClick = { requestProjection() }, modifier = Modifier.fillMaxWidth()) {
                                            Text("Share view only")
                                        }
                                    }
                                }
                            }
                        }
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
                            Text("Streaming", style = MaterialTheme.typography.titleSmall)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                listOf("smooth" to "Smooth", "balanced" to "Balanced", "sharp" to "Sharp").forEach { choice ->
                                    FilterChip(selected = profile == choice.first, onClick = { profile = choice.first }, label = { Text(choice.second) })
                                }
                            }
                            Spacer(Modifier.height(16.dp))
                            Text("Shared with you", style = MaterialTheme.typography.titleLarge)
                        }
                        if (windows.isEmpty()) item { Text("Select an app or display in HandOff on your computer, click Share selected, then refresh here.") }
                        items(windows, key = { it.id }) { window ->
                            OutlinedCard(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(window.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                    Text(if (window.kind == "display") "Everything visible on this display" else window.app, style = MaterialTheme.typography.bodySmall)
                                    Button(onClick = { title = window.title; busy = true; status = "Opening your app…"; client.start(window.id, compatibility, audioChoice, profile) }, enabled = !busy && !phoneSharing && !projectionPending) { Text("Continue here") }
                                }
                            }
                        }
                    }
                    item { UpdateCard(activity) }
                    item {
                        TextButton(onClick = { export.launch("handoff-session.json") }, enabled = client.report().let {
                            it.optInt("decoded_frames") + it.optInt("phone_controls_delivered") + it.optInt("phone_controls_failed") > 0
                        }) { Text("Export session report") }
                        Text("Private by design", style = MaterialTheme.typography.titleMedium)
                        Text("Pair directly with your computer. Only the app or display you explicitly choose is shared over your local network. Stop sharing on either device at any time.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.height(24.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun LiveImage(frame: Bitmap, sequence: Int, client: ProtocolClient, dragMode: Boolean) {
    Image(frame.asImageBitmap(), contentDescription = "Shared application", contentScale = ContentScale.Fit,
        modifier = Modifier.fillMaxSize().remoteInput(frame.width, frame.height, sequence, client, dragMode))
}

@Composable
private fun LiveVideo(dimensions: Pair<Int, Int>, sequence: Int, client: ProtocolClient, dragMode: Boolean) {
    BoxWithConstraints(Modifier.fillMaxSize().remoteInput(dimensions.first, dimensions.second, sequence, client, dragMode), contentAlignment = Alignment.Center) {
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
private fun Modifier.remoteInput(width: Int, height: Int, sequence: Int, client: ProtocolClient, dragMode: Boolean): Modifier {
    val currentSequence by rememberUpdatedState(sequence)
    val dimensions by rememberUpdatedState(width to height)
    return this
        .pointerInput(Unit) {
            detectTapGestures { point ->
                contentPoint(point.x, point.y, size.width.toFloat(), size.height.toFloat(), dimensions.first, dimensions.second)
                    ?.let { client.tap(it.first, it.second, currentSequence) }
            }
        }
        .pointerInput(dragMode) {
            var accumulated = 0f
            var start: Pair<Float, Float>? = null
            var end: Pair<Float, Float>? = null
            detectDragGestures(onDragStart = { point ->
                accumulated = 0f
                start = contentPoint(point.x, point.y, size.width.toFloat(), size.height.toFloat(), dimensions.first, dimensions.second)
                end = start
            }, onDragEnd = {
                if (dragMode) start?.let { from -> end?.let { to -> client.drag(from.first, from.second, to.first, to.second, currentSequence) } }
            }, onDrag = { change, drag ->
                change.consume()
                end = contentPoint(change.position.x, change.position.y, size.width.toFloat(), size.height.toFloat(), dimensions.first, dimensions.second)
                accumulated += drag.y
                if (!dragMode && kotlin.math.abs(accumulated) >= 24f) {
                    contentPoint(change.position.x, change.position.y, size.width.toFloat(), size.height.toFloat(), dimensions.first, dimensions.second)
                        ?.let { client.scroll(it.first, it.second, (-accumulated / 60f).coerceIn(-5f, 5f), currentSequence) }
                    accumulated = 0f
                }
            })
        }
}

package dev.handoff.client

import android.graphics.Bitmap
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.view.Choreographer
import android.view.Surface
import android.os.SystemClock
import org.json.JSONObject
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.io.IOException
import java.net.Socket
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import kotlin.concurrent.thread

class ProtocolClient(
    private val store: CredentialStore,
    private val onMessage: (JSONObject) -> Unit,
    private val onState: (String) -> Unit,
    private val onFrame: (Bitmap, Int) -> Unit,
    private val onVideoFrame: (Int, Int, Int) -> Unit = { _, _, _ -> },
    private val onAudio: () -> Unit = {},
) {
    private val report = SessionReport()
    fun report(): JSONObject = report.json()
    private val main = Handler(Looper.getMainLooper())
    private val generation = AtomicLong()
    private val output = ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS, ArrayBlockingQueue(64))
    private val heartbeat = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var socket: Socket? = null
    @Volatile private var writer: DataOutputStream? = null
    @Volatile private var session: String? = null
    @Volatile private var disposed = false
    @Volatile private var surface: Surface? = null
    @Volatile private var audioAllowed = false
    @Volatile private var activeAudio: AudioPlayer? = null
    @Volatile private var sourceSession: String? = null
    @Volatile private var sourceContext: Context? = null
    private val sourceSequence = AtomicLong()
    private val sourceAudioPending = AtomicBoolean()
    @Volatile private var lastSourceControls: Boolean? = null
    private var lastSourceAck = 0L
    @Volatile private var fallbackPending = false
    private data class DesktopRequest(val window: String, val audio: Boolean, val profile: String)
    @Volatile private var desktopRequest: DesktopRequest? = null
    fun refreshPhoneControls() {
        val active = sourceSession ?: return
        val enabled = RemoteControlService.enabled()
        if (lastSourceControls == enabled) return
        lastSourceControls = enabled
        send("source.controls", JSONObject().put("session", active).put("controls", enabled))
    }
    private data class ProjectionRequest(val context: Context, val resultCode: Int, val data: Intent,
        val width: Int, val height: Int, val audio: Boolean)
    @Volatile private var projectionRequest: ProjectionRequest? = null
    fun setSurface(value: Surface?) { surface = value }

    init { heartbeat.scheduleAtFixedRate({ if (writer != null) send("ping") }, 8, 8, TimeUnit.SECONDS) }
    private fun state(epoch: Long, value: String) { main.post { if (generation.get() == epoch && !disposed) onState(value) } }

    private data class Endpoint(val host: String, val port: Int)
    fun pair(pairing: Pairing) = connect(pairing.host, pairing.port, pairing.wanHost, pairing.wanPort, pairing.pin,
        JSONObject().put("type", "pair").put("code", pairing.code).put("name", android.os.Build.MODEL))
    fun reconnect(c: Credentials) = connect(c.host, c.port, c.wanHost, c.wanPort, c.pin,
        JSONObject().put("type", "auth").put("device", c.device).put("token", c.token))

    private fun connect(host: String, port: Int, wanHost: String?, wanPort: Int?, pin: String, auth: JSONObject) {
        close()
        if (disposed) return
        val epoch = generation.get()
        val endpoints = buildList {
            add(Endpoint(host, port))
            if (wanHost != null && wanPort != null) add(Endpoint(wanHost, wanPort))
        }.distinct()
        state(epoch, "Connecting securely…")
        thread(name = "handoff-reader", isDaemon = true) {
            var decoder: VideoDecoder? = null
            var player: AudioPlayer? = null
            var decoderSize: Pair<Int, Int>? = null
            var raw: Socket? = null
            try {
                var connected: Endpoint? = null
                var lastFailure: Exception? = null
                for (endpoint in endpoints) {
                    if (generation.get() != epoch) return@thread
                    val trial = Socket()
                    socket = trial
                    try {
                        val timeout = if (endpoints.size > 1 && endpoint == endpoints.first()) 900 else 3500
                        trial.connect(InetSocketAddress(endpoint.host, endpoint.port), timeout)
                        raw = trial
                        connected = endpoint
                        break
                    } catch (exc: Exception) {
                        lastFailure = exc
                        try { trial.close() } catch (_: Exception) { }
                    }
                }
                val route = connected ?: throw IOException(
                    if (endpoints.size > 1) "Could not reach this computer on LAN or direct Internet. ${lastFailure?.message ?: ""}".trim()
                    else "Could not reach this computer. ${lastFailure?.message ?: ""}".trim())
                val activeSocket = raw ?: error("Connection socket unavailable")
                activeSocket.tcpNoDelay = true
                activeSocket.soTimeout = 10000
                val context = SSLContext.getInstance("TLS").apply { init(null, arrayOf(PinnedTrust(pin)), null) }
                val tls = context.socketFactory.createSocket(activeSocket, route.host, route.port, true) as SSLSocket
                tls.enabledProtocols = tls.supportedProtocols.filter { it == "TLSv1.2" || it == "TLSv1.3" }.toTypedArray()
                tls.soTimeout = 10000
                tls.tcpNoDelay = true
                tls.startHandshake()
                val out = DataOutputStream(java.io.BufferedOutputStream(tls.outputStream, 65536))
                val input = DataInputStream(tls.inputStream)
                Wire.write(out, auth.put("v", 1).toString().toByteArray(Charsets.UTF_8))
                val first = readJson(input)
                synchronized(this) {
                    if (generation.get() != epoch) return@thread
                val advertisedHost = first.optString("wan").takeIf { it.matches(Regex("[A-Za-z0-9.:_-]{1,253}")) }
                val advertisedPort = first.optInt("wan_port").takeIf { it in 1..65535 }
                val savedWanHost = if (advertisedHost != null && advertisedPort != null) advertisedHost else wanHost
                val savedWanPort = if (advertisedHost != null && advertisedPort != null) advertisedPort else wanPort
                when (first.getString("type")) {
                    "paired" -> store.save(Credentials(host, port, pin, first.getString("device"), first.getString("token"), savedWanHost, savedWanPort))
                    "ready" -> store.save(Credentials(host, port, pin, auth.getString("device"), auth.getString("token"), savedWanHost, savedWanPort))
                    "revoked" -> { store.clear(); error(first.optString("message", "Pair again on your computer")) }
                    else -> error(first.optString("message", "Pairing failed"))
                }
                    socket = tls; writer = out
                }
                tls.soTimeout = 25000
                state(epoch, "Connected")
                send("windows")
                while (generation.get() == epoch) {
                    val msg = readJson(input)
                    when (msg.getString("type")) {
                        "started" -> { session = msg.getString("session"); report.start(msg.optString("codec"),
                            msg.optString("encoder"), msg.optString("profile", "balanced"), msg.optString("target", "window")) }
                        "stopped" -> {
                            report.stop(); session = null; decoder?.close(); decoder = null; decoderSize = null; player?.close(); player = null
                            if (fallbackPending) {
                                fallbackPending = false
                                desktopRequest?.let { start(it.window, true, it.audio, it.profile) }
                                continue
                            }
                        }
                        "audio.stopped" -> { player?.close(); player = null }
                        "source.ready" -> {
                            val request = projectionRequest ?: error("Phone projection request expired")
                            sourceSession = msg.getString("session"); sourceSequence.set(0); lastSourceAck = 0; lastSourceControls = null
                            refreshPhoneControls()
                            PhoneProjectionService.start(request.context, request.resultCode, request.data,
                                request.width, request.height, request.audio)
                        }
                        "source.ack" -> {
                            require(msg.getString("session") == sourceSession) { "Stale phone frame acknowledgement" }
                            val ack = msg.getLong("sequence")
                            require(ack == lastSourceAck + 1 && ack <= sourceSequence.get()) { "Invalid phone frame acknowledgement" }
                            lastSourceAck = ack
                            PhoneSourceBus.requestFrame(); continue
                        }
                        "source.stopped" -> {
                            sourceSession = null; projectionRequest = null
                        }
                        "phone.stop" -> { requirePhoneSession(msg); sourceContext?.let { PhoneProjectionService.stop(it) }; continue }
                        "phone.tap" -> {
                            requirePhoneSession(msg)
                            RemoteControlService.tap(msg.getDouble("x").toFloat(), msg.getDouble("y").toFloat()) { success, message ->
                                phoneControlResult("tap", success, message)
                            }
                            continue
                        }
                        "phone.drag" -> {
                            requirePhoneSession(msg)
                            RemoteControlService.drag(msg.getDouble("x0").toFloat(), msg.getDouble("y0").toFloat(),
                                msg.getDouble("x1").toFloat(), msg.getDouble("y1").toFloat()) { success, message ->
                                phoneControlResult("drag", success, message)
                            }
                            continue
                        }
                        "phone.scroll" -> {
                            requirePhoneSession(msg)
                            RemoteControlService.scroll(msg.getDouble("x").toFloat(), msg.getDouble("y").toFloat(), msg.getDouble("dy").toFloat()) { success, message ->
                                phoneControlResult("scroll", success, message)
                            }
                            continue
                        }
                        "phone.text" -> {
                            requirePhoneSession(msg); msg.getString("text").takeIf { it.length <= 256 }?.let { RemoteControlService.text(it) }; continue
                        }
                        "phone.key" -> {
                            requirePhoneSession(msg); RemoteControlService.key(msg.getString("key")); continue
                        }
                        "audio" -> {
                            require(msg.getString("session") == session && audioAllowed) { "Unexpected audio session" }
                            require(msg.getInt("rate") == 48000 && msg.getInt("channels") == 2 && msg.getString("format") == "s16le") { "Unsupported audio format" }
                            val (kind, bytes) = Wire.read(input)
                            require(kind == 4 && bytes.size == 3840) { "Invalid audio packet" }
                            if (player == null) {
                                synchronized(this) {
                                    require(generation.get() == epoch) { "Session closed" }
                                    player = AudioPlayer()
                                    activeAudio = player
                                }
                            }
                            player?.offer(bytes)
                            report.audio()
                            main.post { if (generation.get() == epoch && !disposed) onAudio() }
                            continue
                        }
                        "revoked" -> { store.clear(); error(msg.getString("message")) }
                        "frame" -> {
                            require(msg.getString("session") == session) { "Stale video session" }
                            val sequence = msg.getInt("sequence")
                            val (kind, bytes) = Wire.read(input)
                            if (kind == 3) {
                                val width = msg.getInt("width"); val height = msg.getInt("height")
                                require(width in 2..1920 && height in 2..1080 && msg.getString("codec") == "h264") { "Invalid H.264 format" }
                                try {
                                if (decoder == null || decoderSize != (width to height) || decoder?.isSurface(surface) != true) {
                                    decoder?.close(); decoder = null
                                    val deadline = SystemClock.elapsedRealtime() + 3000
                                    while ((surface == null || surface?.isValid != true) && generation.get() == epoch && SystemClock.elapsedRealtime() < deadline) Thread.sleep(10)
                                    require(generation.get() == epoch) { "Session closed" }
                                    decoder = VideoDecoder(surface ?: error("Video surface unavailable"), width, height)
                                    decoderSize = width to height
                                }
                                decoder.render(bytes, sequence)
                                } catch (e: Exception) {
                                    if (generation.get() != epoch) throw e
                                    report.error()
                                    fallbackPending = true
                                    send("stop", includeSession = true)
                                    main.post { if (generation.get() == epoch && !disposed)
                                        onMessage(JSONObject().put("type", "video.fallback").put("message", "Switching to compatibility video…")) }
                                    continue
                                }
                                report.video(bytes.size)
                                main.post { if (generation.get() == epoch && !disposed) onVideoFrame(width, height, sequence) }
                                send("ack", JSONObject().put("sequence", sequence), true)
                                continue
                            }
                            require(kind == 2) { "Missing video frame" }
                            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
                            require(options.outWidth in 1..1920 && options.outHeight in 1..1080 && options.outMimeType == "image/jpeg") { "Unsupported video dimensions" }
                            require(options.outWidth == msg.getInt("width") && options.outHeight == msg.getInt("height")) { "Video dimensions changed unexpectedly" }
                            val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: error("Could not decode video")
                            report.video(bytes.size)
                            val frameSession = session
                            main.post {
                                if (generation.get() == epoch && session == frameSession && !disposed) {
                                    onFrame(bitmap, sequence)
                                    Choreographer.getInstance().postFrameCallback {
                                        if (generation.get() == epoch && session == frameSession && !disposed)
                                            send("ack", JSONObject().put("sequence", sequence), true)
                                    }
                                } else bitmap.recycle()
                            }
                            continue
                        }
                    }
                    main.post { if (generation.get() == epoch && !disposed) onMessage(msg) }
                }
            } catch (e: Exception) {
                if (generation.get() == epoch) { report.error(); report.stop() }
                state(epoch, e.message ?: "Connection lost. Reconnect to continue.")
            } finally {
                try { decoder?.close() } catch (_: Exception) {}
                try { player?.close() } catch (_: Exception) {}
                try { raw?.close() } catch (_: Exception) { }
                synchronized(this) {
                    if (generation.get() == epoch) {
                        sourceContext?.let { if (sourceSession != null) PhoneProjectionService.stop(it) }
                        PhoneSourceBus.sink = null; sourceSession = null; projectionRequest = null
                        writer = null; socket = null; session = null
                    }
                }
            }
        }
    }

    private fun readJson(input: DataInputStream): JSONObject {
        val (kind, data) = Wire.read(input)
        require(kind == 1) { "Expected control message" }
        return JSONObject(String(data, Charsets.UTF_8)).also { require(it.getInt("v") == 1) { "Unsupported host version" } }
    }

    private fun requirePhoneSession(msg: JSONObject) {
        require(sourceSession != null && msg.getString("session") == sourceSession) { "Stale phone control session" }
    }

    private fun phoneControlResult(action: String, success: Boolean, message: String) {
        val active = sourceSession ?: return
        send("source.controlResult", JSONObject().put("session", active).put("action", action)
            .put("success", success).put("message", message.take(160)))
    }

    fun beginPhoneShare(context: Context, resultCode: Int, data: Intent, width: Int, height: Int, audio: Boolean) {
        require(width in 2..1920 && height in 2..1920 && width * height <= 1920 * 1080)
        sourceContext = context.applicationContext
        projectionRequest = ProjectionRequest(context.applicationContext, resultCode, data, width, height, audio)
        PhoneSourceBus.sink = object : PhoneSourceBus.Sink {
            override fun video(bytes: ByteArray) = sendSourceMedia("source.frame", 3, bytes,
                JSONObject().put("sequence", sourceSequence.incrementAndGet()))
            override fun audio(bytes: ByteArray) {
                if (sourceAudioPending.compareAndSet(false, true)) sendSourceMedia("source.audio", 4, bytes,
                    JSONObject().put("rate", 48000).put("channels", 2).put("format", "s16le")) { sourceAudioPending.set(false) }
            }
            override fun stopped(message: String) {
                val active = sourceSession
                if (active != null) send("source.stop", JSONObject().put("session", active))
                main.post { if (!disposed) onMessage(JSONObject().put("type", "source.localStopped").put("message", message)) }
            }
        }
        send("source.start", JSONObject().put("width", width).put("height", height).put("codec", "h264")
            .put("audio", audio).put("controls", RemoteControlService.enabled()))
    }

    private fun sendSourceMedia(type: String, kind: Int, bytes: ByteArray, payload: JSONObject, done: () -> Unit = {}) {
        val epoch = generation.get(); val active = sourceSession ?: return done()
        try {
            output.execute {
                try {
                    if (generation.get() != epoch || sourceSession != active) return@execute
                    val out = writer ?: return@execute
                    payload.put("v", 1).put("type", type).put("session", active)
                    Wire.write(out, payload.toString().toByteArray(Charsets.UTF_8)); Wire.write(out, kind, bytes)
                } catch (_: Exception) { synchronized(this) { try { socket?.close() } catch (_: Exception) {} } }
                finally { done() }
            }
        } catch (_: RejectedExecutionException) { done(); close() }
    }

    fun send(type: String, payload: JSONObject = JSONObject(), includeSession: Boolean = false) {
        if (disposed) return
        val epoch = generation.get()
        val currentSession = session
        if (includeSession && currentSession == null) return
        try {
            output.execute {
                if (generation.get() != epoch) return@execute
                try {
                    payload.put("v", 1).put("type", type)
                    if (includeSession) payload.put("session", currentSession)
                    val out = writer ?: return@execute
                    Wire.write(out, payload.toString().toByteArray(Charsets.UTF_8))
                } catch (_: Exception) {
                    state(epoch, "Connection lost. Reconnect to continue.")
                    synchronized(this) { if (generation.get() == epoch) try { socket?.close() } catch (_: Exception) { } }
                }
            }
        } catch (_: RejectedExecutionException) {
            close()
            state(generation.get(), "Connection is busy. Reconnect to continue.")
        }
    }
    fun start(window: String, compatibility: Boolean = false, audio: Boolean = false, profile: String = "balanced") {
        audioAllowed = audio
        desktopRequest = DesktopRequest(window, audio, profile)
        send("start", JSONObject().put("window", window)
            .put("codecs", org.json.JSONArray(if (compatibility) listOf("jpeg") else listOf("h264", "jpeg")))
            .put("audio", audio).put("profile", profile))
    }
    fun stop() { fallbackPending = false; send("stop", includeSession = true) }
    fun tap(x: Float, y: Float, sequence: Int) = send("tap", JSONObject().put("x", x).put("y", y).put("sequence", sequence), true)
    fun scroll(x: Float, y: Float, dy: Float, sequence: Int) = send("scroll", JSONObject().put("x", x).put("y", y).put("dy", dy).put("sequence", sequence), true)
    fun drag(x0: Float, y0: Float, x1: Float, y1: Float, sequence: Int) = send("drag",
        JSONObject().put("x0", x0).put("y0", y0).put("x1", x1).put("y1", y1).put("sequence", sequence), true)
    fun text(value: String, sequence: Int) = send("text", JSONObject().put("text", value.take(256)).put("sequence", sequence), true)
    fun key(value: String, sequence: Int) = send("key", JSONObject().put("key", value).put("sequence", sequence), true)
    @Synchronized fun close() {
        report.stop()
        sourceContext?.let { if (sourceSession != null) PhoneProjectionService.stop(it) }
        PhoneSourceBus.sink = null; sourceSession = null; projectionRequest = null
        fallbackPending = false; desktopRequest = null; lastSourceControls = null
        generation.incrementAndGet()
        try { socket?.close() } catch (_: Exception) { }
        socket = null; writer = null; session = null
        activeAudio?.close(); activeAudio = null
        output.queue.clear()
    }
    fun dispose() { disposed = true; close(); output.shutdownNow(); heartbeat.shutdownNow() }
}

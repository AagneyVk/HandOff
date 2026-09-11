package dev.handoff.client

import android.graphics.Bitmap
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
import java.net.Socket
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
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
    fun setSurface(value: Surface?) { surface = value }

    init { heartbeat.scheduleAtFixedRate({ if (writer != null) send("ping") }, 8, 8, TimeUnit.SECONDS) }
    private fun state(epoch: Long, value: String) { main.post { if (generation.get() == epoch && !disposed) onState(value) } }

    fun pair(pairing: Pairing) = connect(pairing.host, pairing.port, pairing.pin,
        JSONObject().put("type", "pair").put("code", pairing.code).put("name", android.os.Build.MODEL))
    fun reconnect(c: Credentials) = connect(c.host, c.port, c.pin,
        JSONObject().put("type", "auth").put("device", c.device).put("token", c.token))

    private fun connect(host: String, port: Int, pin: String, auth: JSONObject) {
        close()
        if (disposed) return
        val epoch = generation.get()
        val raw = Socket()
        socket = raw
        state(epoch, "Connecting securely…")
        thread(name = "handoff-reader", isDaemon = true) {
            var decoder: VideoDecoder? = null
            var player: AudioPlayer? = null
            var decoderSize: Pair<Int, Int>? = null
            try {
                raw.connect(InetSocketAddress(host, port), 5000)
                raw.tcpNoDelay = true
                raw.soTimeout = 10000
                val context = SSLContext.getInstance("TLS").apply { init(null, arrayOf(PinnedTrust(pin)), null) }
                val tls = context.socketFactory.createSocket(raw, host, port, true) as SSLSocket
                tls.enabledProtocols = tls.supportedProtocols.filter { it == "TLSv1.2" || it == "TLSv1.3" }.toTypedArray()
                tls.soTimeout = 10000
                tls.startHandshake()
                val out = DataOutputStream(tls.outputStream)
                val input = DataInputStream(tls.inputStream)
                Wire.write(out, auth.put("v", 1).toString().toByteArray(Charsets.UTF_8))
                val first = readJson(input)
                synchronized(this) {
                    if (generation.get() != epoch) return@thread
                when (first.getString("type")) {
                    "paired" -> store.save(Credentials(host, port, pin, first.getString("device"), first.getString("token")))
                    "ready" -> Unit
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
                        "started" -> session = msg.getString("session")
                        "stopped" -> { session = null; decoder?.close(); decoder = null; decoderSize = null; player?.close(); player = null }
                        "audio.stopped" -> { player?.close(); player = null }
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
                                require(width in 2..1600 && height in 2..1000 && msg.getString("codec") == "h264") { "Invalid H.264 format" }
                                if (decoder == null || decoderSize != (width to height)) {
                                    decoder?.close(); decoder = null
                                    val deadline = SystemClock.elapsedRealtime() + 3000
                                    while ((surface == null || surface?.isValid != true) && generation.get() == epoch && SystemClock.elapsedRealtime() < deadline) Thread.sleep(10)
                                    require(generation.get() == epoch) { "Session closed" }
                                    decoder = VideoDecoder(surface ?: error("Video surface unavailable"), width, height)
                                    decoderSize = width to height
                                }
                                decoder.render(bytes, sequence)
                                main.post { if (generation.get() == epoch && !disposed) onVideoFrame(width, height, sequence) }
                                send("ack", JSONObject().put("sequence", sequence), true)
                                continue
                            }
                            require(kind == 2) { "Missing video frame" }
                            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
                            require(options.outWidth in 1..1600 && options.outHeight in 1..1000 && options.outMimeType == "image/jpeg") { "Unsupported video dimensions" }
                            require(options.outWidth == msg.getInt("width") && options.outHeight == msg.getInt("height")) { "Video dimensions changed unexpectedly" }
                            val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: error("Could not decode video")
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
                state(epoch, e.message ?: "Connection lost. Reconnect to continue.")
            } finally {
                try { decoder?.close() } catch (_: Exception) {}
                try { player?.close() } catch (_: Exception) {}
                try { raw.close() } catch (_: Exception) { }
                synchronized(this) {
                    if (generation.get() == epoch) { writer = null; socket = null; session = null }
                }
            }
        }
    }

    private fun readJson(input: DataInputStream): JSONObject {
        val (kind, data) = Wire.read(input)
        require(kind == 1) { "Expected control message" }
        return JSONObject(String(data, Charsets.UTF_8)).also { require(it.getInt("v") == 1) { "Unsupported host version" } }
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
    fun start(window: String, compatibility: Boolean = false, audio: Boolean = false) {
        audioAllowed = audio
        send("start", JSONObject().put("window", window).put("codecs", org.json.JSONArray(if (compatibility) listOf("jpeg") else listOf("h264", "jpeg"))).put("audio", audio))
    }
    fun stop() = send("stop", includeSession = true)
    fun tap(x: Float, y: Float, sequence: Int) = send("tap", JSONObject().put("x", x).put("y", y).put("sequence", sequence), true)
    fun scroll(x: Float, y: Float, dy: Float, sequence: Int) = send("scroll", JSONObject().put("x", x).put("y", y).put("dy", dy).put("sequence", sequence), true)
    @Synchronized fun close() {
        generation.incrementAndGet()
        try { socket?.close() } catch (_: Exception) { }
        socket = null; writer = null; session = null
        activeAudio?.close(); activeAudio = null
        output.queue.clear()
    }
    fun dispose() { disposed = true; close(); output.shutdownNow(); heartbeat.shutdownNow() }
}

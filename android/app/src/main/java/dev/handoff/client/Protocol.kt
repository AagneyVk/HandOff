package dev.handoff.client

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.view.Choreographer
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
) {
    private val main = Handler(Looper.getMainLooper())
    private val generation = AtomicLong()
    private val output = ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS, ArrayBlockingQueue(64))
    private val heartbeat = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var socket: Socket? = null
    @Volatile private var writer: DataOutputStream? = null
    @Volatile private var session: String? = null
    @Volatile private var disposed = false

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
                        "stopped" -> session = null
                        "revoked" -> { store.clear(); error(msg.getString("message")) }
                        "frame" -> {
                            require(msg.getString("session") == session) { "Stale video session" }
                            val sequence = msg.getInt("sequence")
                            val (kind, bytes) = Wire.read(input)
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
            state(epoch, "Connection is busy. Reconnect to continue.")
            close()
        }
    }
    fun start(window: String) = send("start", JSONObject().put("window", window))
    fun stop() = send("stop", includeSession = true)
    fun tap(x: Float, y: Float, sequence: Int) = send("tap", JSONObject().put("x", x).put("y", y).put("sequence", sequence), true)
    fun scroll(x: Float, y: Float, dy: Float, sequence: Int) = send("scroll", JSONObject().put("x", x).put("y", y).put("dy", dy).put("sequence", sequence), true)
    @Synchronized fun close() {
        generation.incrementAndGet()
        try { socket?.close() } catch (_: Exception) { }
        socket = null; writer = null; session = null
        output.queue.clear()
    }
    fun dispose() { disposed = true; close(); output.shutdownNow(); heartbeat.shutdownNow() }
}

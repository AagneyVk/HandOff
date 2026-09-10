package dev.handoff.client

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.BufferedWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong
import kotlin.concurrent.thread

class ProtocolClient(private val onMessage: (JSONObject) -> Unit, private val onState: (String) -> Unit) {
    private val main = Handler(Looper.getMainLooper())
    private val generation = AtomicLong()
    private val output = Executors.newSingleThreadExecutor()
    @Volatile private var socket: Socket? = null
    @Volatile private var writer: BufferedWriter? = null
    @Volatile private var sessionId: String? = null

    private fun state(epoch: Long, value: String) { main.post { if (generation.get() == epoch) onState(value) } }

    fun connect(host: String, port: Int = 47820) {
        close()
        val epoch = generation.get()
        val s = Socket()
        socket = s
        state(epoch, "Connecting")
        thread(name = "handoff-reader", isDaemon = true) {
            try {
                s.connect(InetSocketAddress(host.trim(), port), 5000)
                s.tcpNoDelay = true
                s.soTimeout = 15000
                synchronized(this) {
                    if (generation.get() != epoch) return@thread
                    writer = s.getOutputStream().bufferedWriter(Charsets.UTF_8)
                }
                send("hello", JSONObject().put("client", "android"))
                send("windows.list", JSONObject())
                val reader = s.getInputStream().bufferedReader(Charsets.UTF_8)
                while (generation.get() == epoch) {
                    val line = StringBuilder()
                    while (true) {
                        val ch = reader.read()
                        if (ch == -1) throw java.io.EOFException("Computer disconnected")
                        if (ch == 10) break
                        require(line.length < 65536) { "Response too large" }
                        line.append(ch.toChar())
                    }
                    val msg = JSONObject(line.toString())
                    require(msg.getInt("version") == 0) { "Unsupported host version" }
                    msg.getJSONObject("payload")
                    if (msg.getString("type") == "capabilities") s.soTimeout = 0
                    if (msg.getString("type") == "session.started") sessionId = msg.getString("session_id")
                    main.post { if (generation.get() == epoch) onMessage(msg) }
                }
            } catch (e: Exception) {
                state(epoch, "Disconnected: ${e.message ?: "Connection failed"}")
            } finally {
                s.close()
                synchronized(this) {
                    if (generation.get() == epoch) { socket = null; writer = null; sessionId = null }
                }
            }
        }
    }

    fun send(type: String, payload: JSONObject, includeSession: Boolean = false) {
        val epoch = generation.get()
        val session = sessionId
        if (includeSession && session == null) return
        output.execute {
            if (generation.get() != epoch) return@execute
            try {
                val message = JSONObject().put("version", 0)
                    .put("id", UUID.randomUUID().toString()).put("type", type)
                    .put("timestamp_us", System.nanoTime() / 1000).put("payload", payload)
                if (includeSession) message.put("session_id", session)
                val out = writer ?: return@execute
                out.write(message.toString()); out.newLine(); out.flush()
            } catch (e: Exception) {
                state(epoch, "Disconnected: ${e.message ?: "Send failed"}")
                if (generation.get() == epoch) socket?.close()
            }
        }
    }

    fun startSession(windowId: String) = send("session.start", JSONObject().put("window_id", windowId))
    fun stopSession() { send("session.stop", JSONObject(), true); sessionId = null }
    @Synchronized fun close() {
        generation.incrementAndGet()
        try { socket?.close() } catch (_: Exception) { }
        socket = null; writer = null; sessionId = null
    }
    fun dispose() { close(); output.shutdownNow() }
}

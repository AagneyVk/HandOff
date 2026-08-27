package dev.handoff.client

import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.util.UUID
import kotlin.concurrent.thread

class ProtocolClient(
    private val onMessage: (JSONObject) -> Unit,
    private val onState: (String) -> Unit,
) {
    private var socket: Socket? = null
    private var writer: BufferedWriter? = null
    @Volatile private var sessionId: String? = null

    fun connect(host: String, port: Int = 47820) {
        close()
        thread(name = "handoff-control", isDaemon = true) {
            try {
                onState("Connecting…")
                val s = Socket()
                s.connect(InetSocketAddress(host, port), 3000)
                socket = s
                writer = BufferedWriter(OutputStreamWriter(s.getOutputStream()))
                onState("Connected")
                send("hello", JSONObject().put("client", "android-v0"))
                send("windows.list", JSONObject())
                val reader = BufferedReader(InputStreamReader(s.getInputStream()))
                while (true) {
                    val line = reader.readLine() ?: break
                    val message = JSONObject(line)
                    if (message.optString("type") == "session.started") {
                        sessionId = message.optString("session_id").ifBlank { null }
                    }
                    onMessage(message)
                }
            } catch (e: Exception) {
                onState("Disconnected: ${e.message ?: e.javaClass.simpleName}")
            } finally {
                close()
            }
        }
    }

    @Synchronized
    fun send(type: String, payload: JSONObject, includeSession: Boolean = false) {
        val out = writer ?: return
        val message = JSONObject()
            .put("version", 0)
            .put("id", UUID.randomUUID().toString().replace("-", ""))
            .put("type", type)
            .put("timestamp_us", System.nanoTime() / 1_000L)
            .put("payload", payload)
        if (includeSession) sessionId?.let { message.put("session_id", it) }
        out.write(message.toString())
        out.newLine()
        out.flush()
    }

    fun startFakeSession() = send(
        "session.start",
        JSONObject().put("window_id", "fake:motion-grid")
    )

    fun pointer(x: Float, y: Float, action: String) = send(
        "input.pointer",
        JSONObject().put("x", x.coerceIn(0f, 1f)).put("y", y.coerceIn(0f, 1f)).put("action", action),
        includeSession = true,
    )

    fun scroll(dx: Float, dy: Float) = send(
        "input.scroll",
        JSONObject().put("dx", dx).put("dy", dy),
        includeSession = true,
    )

    @Synchronized
    fun close() {
        try { socket?.close() } catch (_: Exception) {}
        socket = null
        writer = null
        sessionId = null
    }
}

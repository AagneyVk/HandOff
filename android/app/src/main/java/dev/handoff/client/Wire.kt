package dev.handoff.client

import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.URI
import java.net.URLDecoder
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.X509TrustManager

object Wire {
    const val MAX_PACKET = 2 * 1024 * 1024
    fun read(input: DataInputStream): Pair<Int, ByteArray> {
        val length = input.readInt()
        require(length in 2..MAX_PACKET) { "Invalid packet size" }
        val kind = input.readUnsignedByte()
        require(kind in 1..4) { "Unsupported packet" }
        require(kind != 1 || length <= 16385) { "Control packet too large" }
        return kind to ByteArray(length - 1).also { input.readFully(it) }
    }
    fun write(output: DataOutputStream, data: ByteArray) {
        require(data.size in 1..16384)
        output.writeInt(data.size + 1); output.writeByte(1); output.write(data); output.flush()
    }
}

data class Pairing(val host: String, val port: Int, val pin: String, val code: String) {
    companion object {
        fun parse(value: String): Pairing {
            require(value.length <= 2048) { "Pairing link is too long" }
            val uri = URI(value.trim())
            require(uri.scheme == "handoff" && uri.host == "pair" && uri.fragment == null && uri.userInfo == null) { "Scan a HandOff QR code" }
            val entries = (uri.rawQuery ?: "").split('&').map {
                val fields = it.split('=', limit = 2)
                require(fields.size == 2) { "Invalid pairing link" }
                fields[0] to URLDecoder.decode(fields[1], "UTF-8")
            }
            require(entries.map { it.first }.toSet().size == entries.size) { "Invalid pairing link" }
            val values = entries.toMap()
            val host = values["host"] ?: error("Missing computer address")
            require(host.matches(Regex("[A-Za-z0-9.:_-]{1,253}"))) { "Invalid computer address" }
            val port = values["port"]?.toIntOrNull() ?: error("Invalid port")
            require(port in 1..65535)
            val pin = values["pin"] ?: ""
            require(pin.matches(Regex("[0-9a-f]{64}"))) { "Invalid computer identity" }
            val code = values["code"] ?: ""
            require(code.matches(Regex("[A-Za-z0-9_-]{43}"))) { "Invalid pairing code" }
            return Pairing(host, port, pin, code)
        }
    }
}

class PinnedTrust(private val pin: String) : X509TrustManager {
    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) { throw CertificateException("Client certificates are unsupported") }
    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        val cert = chain?.firstOrNull() ?: throw CertificateException("Missing computer certificate")
        cert.checkValidity()
        val digest = MessageDigest.getInstance("SHA-256").digest(cert.encoded).joinToString("") { "%02x".format(it.toInt() and 255) }
        if (!MessageDigest.isEqual(digest.toByteArray(Charsets.US_ASCII), pin.toByteArray(Charsets.US_ASCII))) {
            throw CertificateException("Computer identity changed. Pair again on your computer.")
        }
    }
}

/** Map touches into the displayed content, excluding letterbox bars. */
fun contentPoint(x: Float, y: Float, viewWidth: Float, viewHeight: Float, imageWidth: Int, imageHeight: Int): Pair<Float, Float>? {
    if (viewWidth <= 0 || viewHeight <= 0 || imageWidth <= 0 || imageHeight <= 0) return null
    val scale = minOf(viewWidth / imageWidth, viewHeight / imageHeight)
    val width = imageWidth * scale; val height = imageHeight * scale
    val nx = (x - (viewWidth - width) / 2) / width
    val ny = (y - (viewHeight - height) / 2) / height
    return if (nx.isFinite() && ny.isFinite() && nx in 0f..1f && ny in 0f..1f) nx to ny else null
}

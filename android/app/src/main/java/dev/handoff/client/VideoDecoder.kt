package dev.handoff.client

import android.media.MediaCodec
import android.media.MediaFormat
import android.os.Build
import android.os.SystemClock
import android.view.Surface

/** Used only by the connection reader thread. Surface lifecycle is owned by the UI. */
class VideoDecoder(private val surface: Surface, val width: Int, val height: Int) {
    private val codec = MediaCodec.createDecoderByType("video/avc")
    init {
        try {
            val format = MediaFormat.createVideoFormat("video/avc", width, height)
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, Wire.MAX_PACKET)
            if (Build.VERSION.SDK_INT >= 30) format.setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
            codec.configure(format, surface, null, 0)
            codec.start()
        } catch (e: Exception) { codec.release(); throw e }
    }
    fun render(bytes: ByteArray, sequence: Int) {
        require(surface.isValid) { "Video surface was closed" }
        val deadline = SystemClock.elapsedRealtime() + 2000
        var queued = false
        val info = MediaCodec.BufferInfo()
        while (SystemClock.elapsedRealtime() < deadline) {
            if (!queued) {
                val index = codec.dequeueInputBuffer(10000)
                if (index >= 0) {
                    val input = codec.getInputBuffer(index) ?: error("Missing decoder input buffer")
                    require(input.capacity() >= bytes.size) { "Video frame exceeds decoder capacity" }
                    input.clear(); input.put(bytes)
                    codec.queueInputBuffer(index, 0, bytes.size, sequence.toLong() * 33333, 0)
                    queued = true
                }
            }
            val output = codec.dequeueOutputBuffer(info, 10000)
            if (output >= 0) {
                val image = info.size > 0 || (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0
                codec.releaseOutputBuffer(output, image)
                if (image && queued) return
            }
        }
        error("Video decoder timed out. Reconnect with compatibility video enabled.")
    }
    fun close() { try { codec.stop() } finally { codec.release() } }
}

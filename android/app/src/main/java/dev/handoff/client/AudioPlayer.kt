package dev.handoff.client

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import java.util.concurrent.ArrayBlockingQueue
import kotlin.concurrent.thread

/** At most four 20 ms PCM chunks queued; late audio is discarded. */
class AudioPlayer {
    private val queue = ArrayBlockingQueue<ByteArray>(4)
    @Volatile private var closed = false
    private val track = AudioTrack.Builder()
        .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MOVIE).build())
        .setAudioFormat(AudioFormat.Builder().setSampleRate(48000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_STEREO).build())
        .setBufferSizeInBytes(maxOf(7680, AudioTrack.getMinBufferSize(48000, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT)))
        .setTransferMode(AudioTrack.MODE_STREAM).build()
    private val worker: Thread
    init {
        try {
            check(track.state == AudioTrack.STATE_INITIALIZED) { "Audio output unavailable" }
            track.play()
        } catch (e: Exception) { track.release(); throw e }
        worker = thread(name="handoff-audio", isDaemon=true) {
            try {
                while (!closed) {
                    val data = queue.take()
                    if (closed) break
                    check(track.write(data, 0, data.size, AudioTrack.WRITE_BLOCKING) >= 0) { "Audio device disconnected" }
                }
            } catch (_: Exception) { }
            finally { closed = true; track.release() }
        }
    }
    fun offer(bytes: ByteArray) {
        require(bytes.size == 3840) { "Invalid audio packet" }
        if (!closed && !queue.offer(bytes)) { queue.poll(); queue.offer(bytes) }
    }
    @Synchronized fun close() {
        if (closed) return
        closed = true
        try { track.pause(); track.flush() } finally { worker.interrupt() }
    }
}

package dev.handoff.client

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.*
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import androidx.core.content.ContextCompat
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

object PhoneSourceBus {
    interface Sink {
        fun video(bytes: ByteArray)
        fun audio(bytes: ByteArray)
        fun stopped(message: String)
    }
    @Volatile var sink: Sink? = null
    @Volatile var source: PhoneProjectionService? = null
    fun requestFrame() { source?.requestFrame() }
}

class PhoneProjectionService : Service() {
    companion object {
        private const val CHANNEL = "handoff_projection"
        private const val STOP = "dev.handoff.client.STOP_PROJECTION"
        fun start(context: Context, resultCode: Int, data: Intent, width: Int, height: Int, audio: Boolean) {
            val intent = Intent(context, PhoneProjectionService::class.java).putExtra("resultCode", resultCode)
                .putExtra("data", data).putExtra("width", width).putExtra("height", height).putExtra("audio", audio)
            ContextCompat.startForegroundService(context, intent)
        }
        fun stop(context: Context) { context.stopService(Intent(context, PhoneProjectionService::class.java)) }
    }

    private var projection: MediaProjection? = null
    private var display: VirtualDisplay? = null
    private var codec: MediaCodec? = null
    private var surface: android.view.Surface? = null
    private var videoThread: Thread? = null
    private var audioRecord: AudioRecord? = null
    private var audioThread: Thread? = null
    private val running = AtomicBoolean(false)
    private val wanted = AtomicBoolean(true)
    private var csd = ByteArray(0)

    override fun onBind(intent: Intent?) = null

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Phone screen sharing", NotificationManager.IMPORTANCE_LOW))
        val stopIntent = PendingIntent.getService(this, 1, Intent(this, PhoneProjectionService::class.java).setAction(STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.presence_video_online)
            .setContentTitle("Phone is shared with your computer").setContentText("Tap Stop to return it to this phone")
            .setOngoing(true).addAction(Notification.Action.Builder(null, "Stop", stopIntent).build()).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(41, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        else startForeground(41, notification)
    }

    @Suppress("DEPRECATION")
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == STOP) { stopSelf(); return START_NOT_STICKY }
        if (running.get()) return START_NOT_STICKY
        val data = intent?.getParcelableExtra<Intent>("data") ?: run { stopSelf(); return START_NOT_STICKY }
        val width = intent.getIntExtra("width", 720)
        val height = intent.getIntExtra("height", 1280)
        if (width !in 2..1920 || height !in 2..1920 || width * height > 1920 * 1080) { stopSelf(); return START_NOT_STICKY }
        try { begin(intent.getIntExtra("resultCode", Activity.RESULT_CANCELED), data, width, height, intent.getBooleanExtra("audio", false)) }
        catch (e: Exception) { PhoneSourceBus.sink?.stopped(e.message ?: "Phone capture could not start"); stopSelf() }
        return START_NOT_STICKY
    }

    private fun begin(resultCode: Int, data: Intent, width: Int, height: Int, withAudio: Boolean) {
        projection = getSystemService(MediaProjectionManager::class.java).getMediaProjection(resultCode, data)
        projection?.registerCallback(object : MediaProjection.Callback() { override fun onStop() { stopSelf() } }, Handler(Looper.getMainLooper()))
        val format = MediaFormat.createVideoFormat("video/avc", width, height).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, 3_000_000)
            setInteger(MediaFormat.KEY_FRAME_RATE, 20)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
            if (Build.VERSION.SDK_INT >= 29) setInteger(MediaFormat.KEY_PREPEND_HEADER_TO_SYNC_FRAMES, 1)
        }
        codec = MediaCodec.createEncoderByType("video/avc").apply {
            configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            this@PhoneProjectionService.surface = createInputSurface(); start()
        }
        display = projection?.createVirtualDisplay("HandOff phone", width, height, resources.configuration.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, surface, null, null)
            ?: error("Phone projection was denied")
        running.set(true); PhoneSourceBus.source = this
        videoThread = thread(name="handoff-phone-video", isDaemon=true) { videoLoop() }
        if (withAudio && Build.VERSION.SDK_INT >= 29) {
            try { startPlaybackAudio() }
            catch (_: Exception) { /* Video remains available when an app/device blocks playback capture. */ }
        }
    }

    fun requestFrame() {
        wanted.set(true)
        try { codec?.setParameters(Bundle().apply { putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0) }) }
        catch (_: Exception) { }
    }

    private fun videoLoop() {
        val info = MediaCodec.BufferInfo()
        try {
            while (running.get()) {
                val encoder = codec ?: break
                val index = encoder.dequeueOutputBuffer(info, 20_000)
                if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    val format = encoder.outputFormat
                    val pieces = listOf("csd-0", "csd-1").mapNotNull { key -> format.getByteBuffer(key)?.let { buffer ->
                        ByteArray(buffer.remaining()).also { buffer.duplicate().get(it) }
                    } }
                    csd = pieces.fold(ByteArray(0)) { all, item -> all + item }
                } else if (index >= 0) {
                    val buffer = encoder.getOutputBuffer(index)
                    if (buffer != null && info.size > 0 && info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0 && wanted.compareAndSet(true, false)) {
                        buffer.position(info.offset); buffer.limit(info.offset + info.size)
                        val frame = ByteArray(info.size).also { buffer.get(it) }
                        PhoneSourceBus.sink?.video(if (hasParameterSets(frame)) frame else csd + frame)
                    }
                    encoder.releaseOutputBuffer(index, false)
                }
            }
        } catch (e: Exception) { if (running.get()) PhoneSourceBus.sink?.stopped(e.message ?: "Phone video stopped") }
    }

    private fun hasParameterSets(data: ByteArray): Boolean {
        for (i in 0 until maxOf(0, data.size - 5)) {
            if (data[i] == 0.toByte() && data[i + 1] == 0.toByte() &&
                ((data[i + 2] == 1.toByte() && (data[i + 3].toInt() and 0x1f) == 7) ||
                 (data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte() && (data[i + 4].toInt() and 0x1f) == 7))) return true
        }
        return false
    }

    @android.annotation.TargetApi(29)
    private fun startPlaybackAudio() {
        val config = AudioPlaybackCaptureConfiguration.Builder(projection ?: return)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA).addMatchingUsage(AudioAttributes.USAGE_GAME).build()
        val format = AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(48000)
            .setChannelMask(AudioFormat.CHANNEL_IN_STEREO).build()
        audioRecord = AudioRecord.Builder().setAudioFormat(format).setBufferSizeInBytes(7680)
            .setAudioPlaybackCaptureConfig(config).build().also { it.startRecording() }
        audioThread = thread(name="handoff-phone-audio", isDaemon=true) {
            val data = ByteArray(3840)
            while (running.get()) {
                val count = audioRecord?.read(data, 0, data.size, AudioRecord.READ_BLOCKING) ?: break
                if (count == data.size) PhoneSourceBus.sink?.audio(data.copyOf())
            }
        }
    }

    override fun onDestroy() {
        running.set(false); PhoneSourceBus.source = null
        try { audioRecord?.stop() } catch (_: Exception) { }; audioThread?.interrupt(); audioRecord?.release()
        videoThread?.interrupt(); try { codec?.stop() } catch (_: Exception) { }; codec?.release()
        display?.release(); surface?.release(); try { projection?.stop() } catch (_: Exception) { }
        PhoneSourceBus.sink?.stopped("Phone sharing stopped")
        super.onDestroy()
    }
}

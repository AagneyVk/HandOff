package dev.handoff.client

import android.os.Build
import android.os.SystemClock
import org.json.JSONObject

class SessionReport {
    private var started = 0L
    private var ended = 0L
    private var frames = 0
    private var bytes = 0L
    private var audio = 0
    private var errors = 0
    private var codec = ""
    private var encoder = ""
    private var profile = ""
    private var target = ""
    private var controlDelivered = 0
    private var controlFailed = 0
    private var lastControl = ""
    @Synchronized fun start(codec: String, encoder: String, profile: String, target: String) {
        started = SystemClock.elapsedRealtime(); ended = 0; frames = 0; bytes = 0; audio = 0; errors = 0
        this.codec = codec; this.encoder = encoder; this.profile = profile; this.target = target
    }
    @Synchronized fun video(size: Int) { frames++; bytes += size }
    @Synchronized fun audio() { audio++ }
    @Synchronized fun error() { if (started > 0 && ended == 0L) errors++ }
    @Synchronized fun phoneStart() { controlDelivered = 0; controlFailed = 0; lastControl = "" }
    @Synchronized fun control(success: Boolean, message: String) {
        if (success) controlDelivered++ else controlFailed++
        lastControl = message.take(160)
    }
    @Synchronized fun stop() { if (started > 0 && ended == 0L) ended = SystemClock.elapsedRealtime() }
    @Synchronized fun json(): JSONObject {
        val seconds = if (started == 0L) 0.0 else ((if (ended > 0) ended else SystemClock.elapsedRealtime()) - started) / 1000.0
        val emulator = Build.FINGERPRINT.contains("generic") || Build.FINGERPRINT.contains("emulator") || Build.MODEL.contains("sdk", true) || Build.HARDWARE.contains("ranchu") || Build.HARDWARE.contains("goldfish")
        return JSONObject().put("schema", 1).put("source_revision", BuildConfig.SOURCE_REVISION)
            .put("device_kind", if (emulator) "emulator" else "physical")
            .put("android_api", Build.VERSION.SDK_INT).put("codec", codec).put("encoder", encoder)
            .put("profile", profile).put("target", target)
            .put("duration_seconds", seconds).put("decoded_frames", frames).put("video_bytes", bytes)
            .put("average_fps", if (seconds > 0) frames / seconds else 0.0)
            .put("audio_chunks_received", audio).put("errors", errors)
            .put("phone_controls_delivered", controlDelivered).put("phone_controls_failed", controlFailed)
            .put("last_phone_control", lastControl)
    }
}

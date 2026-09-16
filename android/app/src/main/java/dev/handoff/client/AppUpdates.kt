package dev.handoff.client

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import java.io.File
import java.net.URL
import java.security.MessageDigest
import javax.net.ssl.HttpsURLConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray

object AppUpdates {
    data class Release(val tag: String, val url: String, val digest: String, val size: Long)
    private const val PREFIX = "https://github.com/AagneyVk/HandOff/releases/download/"
    private const val LIMIT = 150L * 1024 * 1024
    fun version(value: String): List<Int>? {
        val m = Regex("v?(\\d+)\\.(\\d+)\\.(\\d+)(?:-rc(\\d+))?").matchEntire(value) ?: return null
        return listOf(m.groupValues[1].toInt(), m.groupValues[2].toInt(), m.groupValues[3].toInt(), m.groupValues[4].toIntOrNull() ?: 1000000)
    }
    private fun newer(a: String, b: String): Boolean {
        val av = version(a) ?: return false; val bv = version(b) ?: return false
        for (i in av.indices) if (av[i] != bv[i]) return av[i] > bv[i]
        return false
    }
    private fun connection(url: String): HttpsURLConnection {
        var current = url
        repeat(6) {
            require(current.startsWith("https://")) { "Insecure update redirect" }
            val conn = URL(current).openConnection() as HttpsURLConnection
            conn.connectTimeout = 15000; conn.readTimeout = 30000; conn.instanceFollowRedirects = false
            conn.setRequestProperty("User-Agent", "HandOff-updater")
            if (conn.responseCode in listOf(301, 302, 303, 307, 308)) {
                val location = conn.getHeaderField("Location") ?: error("Missing update redirect")
                current = URL(URL(current), location).toString(); conn.disconnect()
            } else {
                if (conn.responseCode != 200) { conn.disconnect(); error("Update server unavailable; try again later") }
                return conn
            }
        }
        error("Too many update redirects")
    }
    fun check(): Release? {
        val conn = connection("https://api.github.com/repos/AagneyVk/HandOff/releases?per_page=30")
        val json = try { conn.inputStream.use { stream ->
            val data = stream.readBytesBounded(1024 * 1024)
            JSONArray(String(data, Charsets.UTF_8))
        } } finally { conn.disconnect() }
        var best: Release? = null
        for (i in 0 until json.length()) {
            val r = json.getJSONObject(i); val tag = r.optString("tag_name")
            if (r.optBoolean("draft") || !newer(tag, best?.tag ?: BuildConfig.VERSION_NAME)) continue
            val assets = r.optJSONArray("assets") ?: continue
            for (j in 0 until assets.length()) {
                val a = assets.getJSONObject(j)
                val digest = a.optString("digest"); val url = a.optString("browser_download_url"); val size = a.optLong("size")
                if (a.optString("name") == "HandOff.apk" && url.startsWith(PREFIX) &&
                    Regex("sha256:[0-9a-f]{64}").matches(digest) && size in 1..LIMIT)
                    best = Release(tag, url, digest.removePrefix("sha256:"), size)
            }
        }
        return best
    }
    private fun java.io.InputStream.readBytesBounded(limit: Int): ByteArray {
        val result = java.io.ByteArrayOutputStream(); val buffer = ByteArray(8192)
        while (true) { val count = read(buffer); if (count < 0) break
            require(result.size() + count <= limit) { "Update metadata too large" }; result.write(buffer, 0, count) }
        return result.toByteArray()
    }
    fun download(context: Context, release: Release): File {
        val dir = File(context.cacheDir, "updates").apply { mkdirs() }
        val part = File(dir, "HandOff.partial"); val target = File(dir, "HandOff.apk")
        val conn = connection(release.url); val hash = MessageDigest.getInstance("SHA-256")
        try {
            var total = 0L
            conn.inputStream.use { input -> part.outputStream().use { out ->
                val buffer = ByteArray(65536)
                while (true) { val count = input.read(buffer); if (count < 0) break
                    total += count; require(total <= release.size && total <= LIMIT) { "APK size mismatch" }
                    hash.update(buffer, 0, count); out.write(buffer, 0, count)
                }
            } }
            require(total == release.size && hash.digest().joinToString("") { "%02x".format(it) } == release.digest) { "Update verification failed" }
            validateApk(context, part)
            check(part.renameTo(target)) { "Could not save update" }
            return target
        } finally { conn.disconnect(); part.delete() }
    }
    @Suppress("DEPRECATION")
    private fun validateApk(context: Context, file: File) {
        val pm = context.packageManager
        val apk = pm.getPackageArchiveInfo(file.path, android.content.pm.PackageManager.GET_SIGNATURES) ?: error("Invalid APK")
        val installed = pm.getPackageInfo(context.packageName, android.content.pm.PackageManager.GET_SIGNATURES)
        require(apk.packageName == context.packageName && apk.versionCode > installed.versionCode) { "APK is not a newer HandOff version" }
        val expected = installed.signatures?.map { it.toCharsString() }?.toSet()
        require(!expected.isNullOrEmpty() && apk.signatures?.map { it.toCharsString() }?.toSet() == expected) {
            "This APK uses a different signing key. A debug-to-release migration needs a one-time manual install; HandOff will not replace your app or erase pairing."
        }
    }
    fun install(context: Context, file: File): Boolean {
        validateApk(context, file)
        if (!context.packageManager.canRequestPackageInstalls()) {
            context.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}")))
            return false
        }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.updates", file)
        context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
        return true
    }
}

@Composable
fun UpdateCard(activity: MainActivity) {
    var message by remember { mutableStateOf("HandOff ${BuildConfig.VERSION_NAME}") }
    var release by remember { mutableStateOf<AppUpdates.Release?>(null) }
    var file by remember { mutableStateOf<File?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    OutlinedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("App updates", style = MaterialTheme.typography.titleMedium)
            Text(message)
            Button(enabled = !busy, onClick = {
                val ready = file
                if (ready != null) {
                    try {
                        activity.keepSettingsConnection()
                        message = if (AppUpdates.install(activity, ready)) "Confirm the update in Android" else "Allow installs from HandOff, return here, then tap Install update again"
                    } catch (e: Exception) { message = e.message ?: "Could not open installer" }
                } else scope.launch {
                    busy = true
                    try {
                        val chosen = release
                        if (chosen == null) {
                            message = "Checking GitHub Releases…"
                            release = withContext(Dispatchers.IO) { AppUpdates.check() }
                            message = release?.let { "Update available: ${it.tag}" } ?: "No newer signed APK is published"
                        } else {
                            message = "Downloading and verifying…"
                            file = withContext(Dispatchers.IO) { AppUpdates.download(activity.applicationContext, chosen) }
                            message = "Update verified; pairing and settings will be kept"
                        }
                    } catch (e: Exception) { message = e.message ?: "Update failed; try again" }
                    finally { busy = false }
                }
            }) { Text(if (busy) "Please wait…" else if (file != null) "Install update" else if (release != null) "Download update" else "Check for updates") }
        }
    }
}

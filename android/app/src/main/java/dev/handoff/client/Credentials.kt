package dev.handoff.client

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class Credentials(val host: String, val port: Int, val pin: String, val device: String, val token: String)

class CredentialStore(context: Context) {
    private val prefs = context.getSharedPreferences("paired-computer", Context.MODE_PRIVATE)
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("handoff-pairing", null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("handoff-pairing", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun save(c: Credentials) {
        val data = JSONObject().put("host", c.host).put("port", c.port).put("pin", c.pin).put("device", c.device).put("token", c.token).toString().toByteArray()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val ciphertext = cipher.doFinal(data)
        check(prefs.edit().putString("value", Base64.encodeToString(cipher.iv + ciphertext, Base64.NO_WRAP)).commit()) { "Could not save pairing" }
    }
    fun load(): Credentials? = try {
        prefs.getString("value", null)?.let {
            val bytes = Base64.decode(it, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12))) }
            val obj = JSONObject(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
            Credentials(obj.getString("host"), obj.getInt("port"), obj.getString("pin"), obj.getString("device"), obj.getString("token"))
        }
    } catch (_: Exception) { clear(); null }
    fun clear() { prefs.edit().clear().apply() }
}

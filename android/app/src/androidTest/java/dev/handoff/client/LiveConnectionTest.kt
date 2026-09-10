package dev.handoff.client

import android.graphics.Color
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class LiveConnectionTest {
    @Test fun pairDecodeReturnAndReconnectOverPinnedTls() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val raw = instrumentation.uiAutomation.executeShellCommand("cat /data/local/tmp/handoff-pairing.txt").use { descriptor ->
            android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor).bufferedReader().readText()
        }
        val store = CredentialStore(context)
        store.clear()
        val paired = CountDownLatch(1)
        val frames = CountDownLatch(2)
        val returned = CountDownLatch(1)
        val reconnected = CountDownLatch(1)
        val count = AtomicInteger()
        val failure = AtomicReference<String?>()
        lateinit var client: ProtocolClient
        instrumentation.runOnMainSync {
            client = ProtocolClient(store, onState = { state ->
                if (state == "Connected") {
                    if (count.incrementAndGet() == 1) paired.countDown() else reconnected.countDown()
                } else if (state != "Connecting securely…") failure.set(state)
            }, onMessage = { msg ->
                if (msg.getString("type") == "stopped") returned.countDown()
                if (msg.getString("type") == "error") failure.set(msg.optString("message"))
            }, onFrame = { bitmap, _ ->
                if (bitmap.width != 64 || bitmap.height != 48 || Color.green(bitmap.getPixel(20, 20)) < 170)
                    failure.set("Decoded frame does not match the host fixture")
                frames.countDown()
            })
            client.pair(Pairing.parse(raw))
        }
        try {
            assertTrue("Pair timed out: ${failure.get()}", paired.await(15, TimeUnit.SECONDS))
            assertNotNull("Credentials not saved through Android Keystore", store.load())
            client.start("win32:7")
            assertTrue("Video/ack timed out: ${failure.get()}", frames.await(15, TimeUnit.SECONDS))
            client.stop()
            assertTrue("Return timed out: ${failure.get()}", returned.await(10, TimeUnit.SECONDS))
            client.close()
            client.reconnect(store.load()!!)
            assertTrue("Reconnect timed out: ${failure.get()}", reconnected.await(15, TimeUnit.SECONDS))
            assertNull(failure.get())
        } finally { client.dispose(); store.clear() }
    }
}

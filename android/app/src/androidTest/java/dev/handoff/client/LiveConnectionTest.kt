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
    @Test fun phoneControlServiceIsDiscoverableAndProtected() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val component = android.content.ComponentName(context, RemoteControlService::class.java)
        @Suppress("DEPRECATION")
        val service = context.packageManager.getServiceInfo(component, android.content.pm.PackageManager.GET_META_DATA)
        assertTrue(service.exported)
        assertEquals("android.permission.BIND_ACCESSIBILITY_SERVICE", service.permission)
        val manager = context.getSystemService(android.view.accessibility.AccessibilityManager::class.java)
        val discovered = manager.installedAccessibilityServiceList.firstOrNull {
            it.resolveInfo.serviceInfo.name == RemoteControlService::class.java.name
        }
        assertNotNull("HandOff control is missing from Android Accessibility settings", discovered)
        assertTrue(discovered!!.capabilities and android.accessibilityservice.AccessibilityServiceInfo.CAPABILITY_CAN_PERFORM_GESTURES != 0)
    }

    @Test fun phoneControlReportsWhenUserHasNotEnabledTheService() {
        assertFalse("Test device unexpectedly has HandOff control enabled", RemoteControlService.enabled())
        val completed = CountDownLatch(1)
        val message = AtomicReference<String?>()
        assertFalse(RemoteControlService.tap(.5f, .5f) { ok, detail ->
            assertFalse(ok); message.set(detail); completed.countDown()
        })
        assertTrue(completed.await(1, TimeUnit.SECONDS))
        assertTrue(message.get()?.contains("not connected") == true)
    }

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
        val fallbackFrames = CountDownLatch(2)
        val audio = CountDownLatch(2)
        val h264Frames = AtomicInteger()
        // Drain decoded output just as SurfaceView's compositor does in the app.
        // An unconsumed SurfaceTexture fills its buffer queue and can block codec.stop().
        val images = android.media.ImageReader.newInstance(64, 48, android.graphics.ImageFormat.YUV_420_888, 3)
        images.setOnImageAvailableListener({ reader -> reader.acquireLatestImage()?.close() }, android.os.Handler(android.os.Looper.getMainLooper()))
        val surface = images.surface
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
            }, onVideoFrame = { width, height, _ ->
                if (width != 64 || height != 48) failure.set("Unexpected H.264 dimensions")
                h264Frames.incrementAndGet(); frames.countDown()
            }, onAudio = { audio.countDown() }, onFrame = { bitmap, _ ->
                if (bitmap.width != 64 || bitmap.height != 48 || Color.green(bitmap.getPixel(20, 20)) < 170)
                    failure.set("Decoded frame does not match the host fixture")
                frames.countDown()
                fallbackFrames.countDown()
            })
            client.setSurface(surface)
            client.pair(Pairing.parse(raw))
        }
        try {
            assertTrue("Pair timed out: ${failure.get()}", paired.await(15, TimeUnit.SECONDS))
            assertNotNull("Credentials not saved through Android Keystore", store.load())
            client.start("win32:7", audio = true)
            assertTrue("Video/ack timed out: ${failure.get()}", frames.await(15, TimeUnit.SECONDS))
            assertTrue("PCM audio did not arrive", audio.await(10, TimeUnit.SECONDS))
            assertTrue("H.264 was not decoded", h264Frames.get() >= 2)
            client.stop()
            assertTrue("Return timed out: ${failure.get()}", returned.await(10, TimeUnit.SECONDS))
            client.close()
            client.reconnect(store.load()!!)
            assertTrue("Reconnect timed out: ${failure.get()}", reconnected.await(15, TimeUnit.SECONDS))
            client.setSurface(null)
            client.start("win32:7")
            assertTrue("Missing surface did not recover to JPEG: ${failure.get()}", fallbackFrames.await(20, TimeUnit.SECONDS))
            assertNull(failure.get())
        } finally { client.dispose(); store.clear(); images.close() }
    }
}

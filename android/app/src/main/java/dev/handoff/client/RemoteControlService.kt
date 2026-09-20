package dev.handoff.client

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Point
import android.graphics.Path
import android.hardware.display.DisplayManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityManager
import android.view.accessibility.AccessibilityNodeInfo

class RemoteControlService : AccessibilityService() {
    companion object {
        @Volatile private var current: RemoteControlService? = null
        fun enabled(): Boolean = current != null
        fun installed(context: Context): Boolean = services(context, false).any { service ->
            service.resolveInfo.serviceInfo.let { it.packageName == context.packageName && it.name == RemoteControlService::class.java.name }
        }
        fun enabledInSettings(context: Context): Boolean = services(context, true).any { service ->
            service.resolveInfo.serviceInfo.let { it.packageName == context.packageName && it.name == RemoteControlService::class.java.name }
        }
        private fun services(context: Context, enabledOnly: Boolean) =
            context.getSystemService(AccessibilityManager::class.java).let { manager ->
                if (enabledOnly) manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
                else manager.installedAccessibilityServiceList
            }
        fun tap(x: Float, y: Float, result: (Boolean, String) -> Unit = { _, _ -> }) =
            current?.gesture(x, y, x, y, 90L, result) ?: unavailable(result)
        fun drag(x0: Float, y0: Float, x1: Float, y1: Float, result: (Boolean, String) -> Unit = { _, _ -> }) =
            current?.gesture(x0, y0, x1, y1, 360L, result) ?: unavailable(result)
        fun scroll(x: Float, y: Float, dy: Float, result: (Boolean, String) -> Unit = { _, _ -> }): Boolean {
            val distance = .28f * if (dy >= 0) -1 else 1
            return current?.gesture(x, y, x, (y + distance).coerceIn(.08f, .92f), 280L, result) ?: unavailable(result)
        }
        private fun unavailable(result: (Boolean, String) -> Unit): Boolean {
            result(false, "Accessibility service is not connected")
            return false
        }
        fun text(value: String) = current?.editText(value, false)
        fun key(name: String) = current?.key(name)
    }

    private data class PendingGesture(val x0: Float, val y0: Float, val x1: Float, val y1: Float,
        val duration: Long, val result: (Boolean, String) -> Unit)
    private val pending = ArrayDeque<PendingGesture>()
    private var gestureActive = false

    override fun onServiceConnected() { current = this }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() { failPending("Android interrupted phone control") }
    override fun onDestroy() { if (current === this) current = null; failPending("Accessibility service stopped"); super.onDestroy() }
    override fun onUnbind(intent: android.content.Intent?): Boolean { if (current === this) current = null; return false }

    private fun size(): Pair<Float, Float> {
        val point = Point()
        @Suppress("DEPRECATION")
        getSystemService(DisplayManager::class.java).getDisplay(Display.DEFAULT_DISPLAY)?.getRealSize(point)
        if (point.x > 0 && point.y > 0) return point.x.toFloat() to point.y.toFloat()
        return resources.displayMetrics.let { it.widthPixels.toFloat() to it.heightPixels.toFloat() }
    }

    private fun gesture(x0: Float, y0: Float, x1: Float, y1: Float, duration: Long,
        result: (Boolean, String) -> Unit): Boolean {
        if (listOf(x0, y0, x1, y1).any { !it.isFinite() || it !in 0f..1f }) {
            result(false, "Invalid phone coordinates")
            return false
        }
        Handler(Looper.getMainLooper()).post {
            if (pending.size >= 32) result(false, "Phone control queue is full")
            else { pending.addLast(PendingGesture(x0, y0, x1, y1, duration, result)); dispatchNext() }
        }
        return true
    }

    private fun dispatchNext() {
        if (gestureActive) return
        val request = pending.removeFirstOrNull() ?: return
        gestureActive = true
        val (width, height) = size()
        val path = Path().apply {
            moveTo(request.x0 * maxOf(1f, width - 1), request.y0 * maxOf(1f, height - 1))
            lineTo(request.x1 * maxOf(1f, width - 1), request.y1 * maxOf(1f, height - 1))
        }
        val callback = object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) = finish(true, "Delivered to phone")
            override fun onCancelled(gestureDescription: GestureDescription?) = finish(false, "Android cancelled the gesture")
            private fun finish(success: Boolean, message: String) {
                request.result(success, message); gestureActive = false; dispatchNext()
            }
        }
        val accepted = dispatchGesture(GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, request.duration)).build(), callback, null)
        if (!accepted) {
            gestureActive = false
            request.result(false, "Android rejected the gesture; re-enable HandOff phone control")
            dispatchNext()
        }
    }

    private fun failPending(message: String) {
        Handler(Looper.getMainLooper()).post {
            while (pending.isNotEmpty()) pending.removeFirst().result(false, message)
            gestureActive = false
        }
    }

    private fun focused(): AccessibilityNodeInfo? = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)

    private fun editText(value: String, replaceLast: Boolean) {
        if (value.length > 256) return
        Handler(Looper.getMainLooper()).post {
            val node = focused() ?: return@post
            val old = node.text?.toString().orEmpty()
            val updated = if (replaceLast) old.dropLast(1) else old + value
            node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,
                Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, updated) })
        }
    }

    private fun key(name: String) {
        when (name) {
            "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
            "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
            "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
            "backspace" -> editText("", true)
            "enter" -> Handler(Looper.getMainLooper()).post {
                val node = focused() ?: return@post
                if (android.os.Build.VERSION.SDK_INT >= 30) node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)
                else editText("\n", false)
            }
            "left", "right", "up", "down" -> Unit // Reserved; Android exposes no general safe arrow injection API.
        }
    }
}

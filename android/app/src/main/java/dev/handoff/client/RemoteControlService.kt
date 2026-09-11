package dev.handoff.client

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class RemoteControlService : AccessibilityService() {
    companion object {
        @Volatile private var current: RemoteControlService? = null
        fun enabled(): Boolean = current != null
        fun tap(x: Float, y: Float) = current?.gesture(x, y, x, y, 70L)
        fun drag(x0: Float, y0: Float, x1: Float, y1: Float) = current?.gesture(x0, y0, x1, y1, 320L)
        fun scroll(x: Float, y: Float, dy: Float) {
            val distance = .28f * if (dy >= 0) -1 else 1
            current?.gesture(x, y, x, (y + distance).coerceIn(.08f, .92f), 260L)
        }
        fun text(value: String) = current?.editText(value, false)
        fun key(name: String) = current?.key(name)
    }

    override fun onServiceConnected() { current = this }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() = Unit
    override fun onUnbind(intent: android.content.Intent?): Boolean { if (current === this) current = null; return false }

    private fun size(): Pair<Float, Float> {
        val metrics = resources.displayMetrics
        return metrics.widthPixels.toFloat() to metrics.heightPixels.toFloat()
    }

    private fun gesture(x0: Float, y0: Float, x1: Float, y1: Float, duration: Long) {
        if (listOf(x0, y0, x1, y1).any { !it.isFinite() || it !in 0f..1f }) return
        Handler(Looper.getMainLooper()).post {
            val (width, height) = size()
            val path = Path().apply { moveTo(x0 * width, y0 * height); lineTo(x1 * width, y1 * height) }
            dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, duration)).build(), null, null)
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

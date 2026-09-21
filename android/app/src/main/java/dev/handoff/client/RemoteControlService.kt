package dev.handoff.client

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Point
import android.graphics.Path
import android.graphics.Rect
import android.hardware.display.DisplayManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityManager
import android.view.accessibility.AccessibilityNodeInfo

class RemoteControlService : AccessibilityService() {
    companion object {
        private const val TAG = "HandOffControl"
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
            current?.tapAt(x, y, result) ?: unavailable(result)
        fun drag(x0: Float, y0: Float, x1: Float, y1: Float, result: (Boolean, String) -> Unit = { _, _ -> }) =
            current?.gesture(x0, y0, x1, y1, 360L, result) ?: unavailable(result)
        fun scroll(x: Float, y: Float, dy: Float, result: (Boolean, String) -> Unit = { _, _ -> }): Boolean {
            return current?.scrollAt(x, y, dy, result) ?: unavailable(result)
        }
        private fun unavailable(result: (Boolean, String) -> Unit): Boolean {
            result(false, "Accessibility service is not connected")
            return false
        }
        fun text(value: String) = current?.editText(value, false)
        fun key(name: String) = current?.key(name)
    }

    private data class PendingGesture(val x0: Float, val y0: Float, val x1: Float, val y1: Float,
        val duration: Long, val result: (Boolean, String) -> Unit, val token: Long)
    private val pending = ArrayDeque<PendingGesture>()
    private val main = Handler(Looper.getMainLooper())
    private var active: PendingGesture? = null
    private var nextToken = 0L

    override fun onServiceConnected() {
        serviceInfo = serviceInfo.apply {
            flags = flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS or AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
        }
        current = this
        Log.i(TAG, "service_connected manufacturer=${android.os.Build.MANUFACTURER} sdk=${android.os.Build.VERSION.SDK_INT} gestures=${serviceInfo.capabilities and AccessibilityServiceInfo.CAPABILITY_CAN_PERFORM_GESTURES != 0}")
    }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() { failAll("Android interrupted phone control") }
    override fun onDestroy() { if (current === this) current = null; failAll("Accessibility service stopped"); super.onDestroy() }
    override fun onUnbind(intent: android.content.Intent?): Boolean {
        if (current === this) current = null
        failAll("Accessibility service disconnected")
        return false
    }

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
        main.post {
            if (pending.size >= 32) result(false, "Phone control queue is full")
            else { pending.addLast(PendingGesture(x0, y0, x1, y1, duration, result, ++nextToken)); dispatchNext() }
        }
        return true
    }

    private fun tapAt(x: Float, y: Float, result: (Boolean, String) -> Unit): Boolean {
        if (!valid(x, y)) { result(false, "Invalid phone coordinates"); return false }
        main.post {
            val (width, height) = size()
            if (performNodeAction(x * width, y * height, AccessibilityNodeInfo.ACTION_CLICK))
                result(true, "Clicked phone control")
            else gesture(x, y, x, y, 80L, result)
        }
        return true
    }

    private fun scrollAt(x: Float, y: Float, dy: Float, result: (Boolean, String) -> Unit): Boolean {
        if (!valid(x, y) || !dy.isFinite() || dy == 0f) { result(false, "Invalid phone scroll"); return false }
        main.post {
            val (width, height) = size()
            val action = if (dy < 0) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            if (performNodeAction(x * width, y * height, action)) result(true, "Scrolled phone control")
            else gesture(x, y, x, scrollGestureEnd(y, dy), 280L, result)
        }
        return true
    }

    private fun valid(vararg values: Float) = values.all { it.isFinite() && it in 0f..1f }

    private fun performNodeAction(x: Float, y: Float, action: Int): Boolean {
        val roots = windows.sortedByDescending { it.layer }.mapNotNull { it.root }.ifEmpty {
            listOfNotNull(rootInActiveWindow)
        }
        var best: AccessibilityNodeInfo? = null
        var bestArea = Long.MAX_VALUE
        var visited = 0
        fun visit(node: AccessibilityNodeInfo?, depth: Int = 0) {
            if (node == null || depth > 64 || ++visited > 4096 || !node.isVisibleToUser) return
            val bounds = Rect(); node.getBoundsInScreen(bounds)
            if (!bounds.contains(x.toInt(), y.toInt())) return
            val supports = when (action) {
                AccessibilityNodeInfo.ACTION_CLICK -> node.isClickable
                AccessibilityNodeInfo.ACTION_SCROLL_FORWARD, AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD ->
                    node.isScrollable || node.actionList.any { it.id == action }
                else -> node.actionList.any { it.id == action }
            }
            val area = bounds.width().toLong() * bounds.height().toLong()
            if (supports && node.isEnabled && area in 1 until bestArea) { best = node; bestArea = area }
            for (index in node.childCount - 1 downTo 0) visit(node.getChild(index), depth + 1)
        }
        roots.forEach { visit(it) }
        val delivered = best?.performAction(action) == true
        Log.d(TAG, "node_action action=$action x=${x.toInt()} y=${y.toInt()} delivered=$delivered")
        return delivered
    }

    private fun dispatchNext() {
        if (active != null) return
        val request = pending.removeFirstOrNull() ?: return
        active = request
        val (width, height) = size()
        val path = Path().apply {
            moveTo(request.x0 * maxOf(1f, width - 1), request.y0 * maxOf(1f, height - 1))
            if (request.x0 != request.x1 || request.y0 != request.y1)
                lineTo(request.x1 * maxOf(1f, width - 1), request.y1 * maxOf(1f, height - 1))
        }
        val callback = object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) = finish(request, true, "Touch delivered to phone")
            override fun onCancelled(gestureDescription: GestureDescription?) = finish(request, false, "Android cancelled the gesture")
        }
        val accepted = dispatchGesture(GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, request.duration)).build(), callback, null)
        Log.d(TAG, "gesture_dispatch token=${request.token} accepted=$accepted from=${request.x0},${request.y0} to=${request.x1},${request.y1}")
        if (!accepted) {
            finish(request, false, "Android rejected the gesture; re-enable HandOff phone control")
        } else {
            main.postDelayed({
                if (active?.token == request.token)
                    finish(request, false, "Android did not finish the gesture; control recovered")
            }, request.duration + 1800L)
        }
    }

    private fun finish(request: PendingGesture, success: Boolean, message: String) {
        if (active?.token != request.token) return
        Log.i(TAG, "gesture_result token=${request.token} success=$success message=$message")
        active = null
        request.result(success, message)
        dispatchNext()
    }

    private fun failAll(message: String) {
        main.post {
            active?.result?.invoke(false, message)
            active = null
            while (pending.isNotEmpty()) pending.removeFirst().result(false, message)
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

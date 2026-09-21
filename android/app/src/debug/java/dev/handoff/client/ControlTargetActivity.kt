package dev.handoff.client

import android.app.Activity
import android.os.Bundle
import android.view.MotionEvent
import android.view.View
import java.util.concurrent.CountDownLatch

class ControlTargetActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val target = View(this).apply {
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            setBackgroundColor(android.graphics.Color.rgb(20, 100, 180))
            setOnTouchListener { _, event ->
                if (event.actionMasked == MotionEvent.ACTION_UP) touch?.countDown()
                true
            }
        }
        setContentView(target)
    }

    companion object {
        @Volatile var touch: CountDownLatch? = null
    }
}

package dev.handoff.client

import org.junit.Assert.*
import org.junit.Test

class PhoneFrameWindowTest {
    @Test fun continuousFramesDoNotWaitForNewKeyframes() {
        val window = PhoneFrameWindow()
        assertFalse(window.offer(false))
        assertTrue(window.offer(true))
        assertTrue(window.offer(false))
        assertTrue(window.offer(false))
        assertFalse(window.acknowledge())
        assertTrue(window.offer(false))
    }
    @Test fun overloadRequiresFreshReferenceFrameAndBoundsBacklog() {
        val window = PhoneFrameWindow(2)
        assertTrue(window.offer(true))
        assertTrue(window.offer(false))
        assertFalse(window.offer(false))
        assertTrue(window.acknowledge())
        assertFalse(window.offer(false))
        assertTrue(window.offer(true))
        assertFalse(window.acknowledge())
        assertTrue(window.offer(false))
    }
}

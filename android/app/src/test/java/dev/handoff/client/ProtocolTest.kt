package dev.handoff.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtocolTest {
    @Test
    fun helloEncodesProtocolVersionAndType() {
        val message = ControlMessage(type = "hello", payload = mapOf("client" to "android-test"))
        val encoded = message.encode()
        assertTrue(encoded.contains("\"version\":0"))
        assertTrue(encoded.contains("\"type\":\"hello\""))
    }

    @Test
    fun normalizedCoordinatesArePreserved() {
        val message = ControlMessage(
            type = "input.pointer",
            payload = mapOf("x" to 0.25, "y" to 0.75, "action" to "tap")
        )
        val decoded = ControlMessage.decode(message.encode())
        assertEquals(0.25, decoded.payload["x"] as Double, 0.0001)
        assertEquals(0.75, decoded.payload["y"] as Double, 0.0001)
    }
}

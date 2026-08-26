package dev.handoff.client

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtocolTest {
    @Test
    fun jsonPayloadPreservesNormalizedCoordinates() {
        val payload = JSONObject()
            .put("x", 0.25)
            .put("y", 0.75)
            .put("action", "tap")
        assertEquals(0.25, payload.getDouble("x"), 0.0001)
        assertEquals(0.75, payload.getDouble("y"), 0.0001)
        assertEquals("tap", payload.getString("action"))
    }

    @Test
    fun protocolVersionContractIsZero() {
        val message = JSONObject()
            .put("version", 0)
            .put("type", "hello")
            .put("payload", JSONObject())
        assertEquals(0, message.getInt("version"))
        assertTrue(message.has("payload"))
    }
}

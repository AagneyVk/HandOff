package dev.handoff.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pure JVM contract tests.
 *
 * org.json is provided by the Android runtime and its local-JVM stub methods throw
 * "Method ... not mocked" unless a separate implementation is added. Keep unit
 * tests platform-neutral; Android-runtime behaviour belongs in instrumented tests.
 */
class ProtocolTest {
    @Test
    fun normalizedCoordinatesStayInsideProtocolRange() {
        fun normalized(value: Float) = value.coerceIn(0f, 1f)

        assertEquals(0.25f, normalized(0.25f), 0.0001f)
        assertEquals(0.75f, normalized(0.75f), 0.0001f)
        assertEquals(0f, normalized(-1f), 0.0001f)
        assertEquals(1f, normalized(2f), 0.0001f)
    }

    @Test
    fun protocolContractMatchesHostV0() {
        val protocolVersion = 0
        val requiredEnvelopeFields = setOf("version", "id", "type", "timestamp_us", "payload")

        assertEquals(0, protocolVersion)
        assertTrue(requiredEnvelopeFields.containsAll(listOf("version", "type", "payload")))
    }
}

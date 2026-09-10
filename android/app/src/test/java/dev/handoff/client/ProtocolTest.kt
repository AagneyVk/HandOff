package dev.handoff.client

import org.junit.Assert.*
import org.junit.Test
import java.io.*

class ProtocolTest {
    @Test fun packetRoundTripAndTruncation() {
        val buffer = ByteArrayOutputStream()
        Wire.write(DataOutputStream(buffer), "hello".toByteArray())
        val (kind, data) = Wire.read(DataInputStream(ByteArrayInputStream(buffer.toByteArray())))
        assertEquals(1, kind); assertEquals("hello", String(data))
        try {
            Wire.read(DataInputStream(ByteArrayInputStream(buffer.toByteArray().copyOf(6))))
            fail("Truncated packet accepted")
        } catch (_: EOFException) { }
    }
    @Test fun oversizedPacketRejectedBeforeAllocation() {
        val bytes = ByteArrayOutputStream()
        DataOutputStream(bytes).writeInt(Int.MAX_VALUE)
        try { Wire.read(DataInputStream(ByteArrayInputStream(bytes.toByteArray()))); fail("Oversize accepted") }
        catch (_: IllegalArgumentException) { }
    }
    @Test fun pairingRequiresPinAndUniqueFields() {
        val link = "handoff://pair?host=192.168.1.2&port=47821&pin=${"a".repeat(64)}&code=${"b".repeat(43)}"
        assertEquals("192.168.1.2", Pairing.parse(link).host)
        for (bad in listOf(link + "&host=evil", link.replace("handoff:", "http:"), link.replace("a".repeat(64), "abc"))) {
            try { Pairing.parse(bad); fail("Invalid pairing accepted") }
            catch (_: IllegalArgumentException) { }
        }
    }
    @Test fun letterboxingNeverMapsBarsToInput() {
        assertNull(contentPoint(100f, 10f, 200f, 400f, 200, 100))
        assertEquals(.5f, contentPoint(100f, 200f, 200f, 400f, 200, 100)!!.first, .0001f)
        assertEquals(.5f, contentPoint(100f, 200f, 200f, 400f, 200, 100)!!.second, .0001f)
        assertNull(contentPoint(Float.NaN, 0f, 200f, 400f, 200, 100))
        assertNull(contentPoint(0f, 0f, 0f, 400f, 200, 100))
    }
}

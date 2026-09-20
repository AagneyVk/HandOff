package dev.handoff.client

/** Bound network backlog while preserving H.264 reference-frame dependencies. */
class PhoneFrameWindow(private val capacity: Int = 3) {
    private var outstanding = 0
    private var needsSync = true
    @Synchronized fun offer(keyFrame: Boolean): Boolean {
        if (outstanding >= capacity) { needsSync = true; return false }
        if (needsSync && !keyFrame) return false
        if (keyFrame) needsSync = false
        outstanding++
        return true
    }
    @Synchronized fun acknowledge(): Boolean {
        if (outstanding > 0) outstanding--
        return needsSync && outstanding < capacity
    }
    @Synchronized fun needsKeyFrame(): Boolean = needsSync && outstanding < capacity
}

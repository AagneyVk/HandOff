package dev.handoff.client

/** Convert desktop wheel direction into the equivalent physical finger swipe. */
fun scrollGestureEnd(y: Float, dy: Float): Float =
    (y + .28f * if (dy < 0f) -1f else 1f).coerceIn(.08f, .92f)

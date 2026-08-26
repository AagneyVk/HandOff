# HandOff production architecture direction

V1 is a development branch, not a production release. This document records the architecture we will hold production work against.

## Design references

HandOff borrows proven patterns rather than inventing a remote-streaming stack blindly:

- Sunshine/Moonlight: hardware-accelerated capture/encode, low-latency media path, explicit input channel and client decoder.
- scrcpy: minimal buffering, direct hardware codec use, independent control/media concerns, predictable session lifecycle.
- Windows Graphics Capture: native per-window/display capture on Windows, feeding GPU-backed frames rather than screenshot polling.
- Android MediaCodec: decode directly to a Surface with hardware codecs when available.
- WebRTC: useful reference for encrypted real-time media, congestion control, NAT traversal and packet-loss behavior; V1 LAN transport remains replaceable behind an interface.

## Production boundaries

The architecture is split into five explicit layers:

1. **Platform capture** — Windows Graphics Capture on Windows; PipeWire/portal or compositor-specific backend on Wayland Linux later.
2. **Media pipeline** — GPU surface -> hardware H.264 baseline/AVC first; HEVC/AV1 only after capability negotiation.
3. **Transport** — low-latency media channel separate from reliable authenticated control. No raw unauthenticated LAN control in a release build.
4. **Client presentation** — Android MediaCodec -> Surface, bounded jitter queue, frame dropping rather than latency accumulation.
5. **Control** — normalized coordinates plus source frame/window geometry; session-scoped, authenticated, rate-limited input messages.

## Required properties before a production claim

### Security
- Explicit first-device pairing and persistent device identity.
- Authenticated encrypted control and media traffic.
- No listener exposed beyond the selected network interfaces without authentication.
- Session tokens are random, short-lived and bound to the paired peer.
- Replay protection / monotonically increasing control sequence numbers.
- Remote input disabled until a user-approved session is active.

### Reliability
- Protocol version/capability negotiation.
- Bounded message sizes and decoder limits.
- Timeouts for connect, handshake, media startup and idle sessions.
- Heartbeat/liveness and deterministic teardown.
- Reconnect/resume behavior that never leaves input control active after media loss.
- Backpressure: stale video frames are dropped, never queued without bound.
- Orientation/window-size changes renegotiate geometry atomically.

### Media
- Hardware encode preferred; software fallback is explicit and measurable.
- Hardware decode to Android Surface preferred.
- Keyframe request/recovery path.
- Audio and video clocks have timestamps and drift handling.
- Adaptive bitrate/resolution based on measured network/decode health.
- Protected/DRM content may be black or unavailable and must fail safely.

### Input
- Letterbox/crop transforms are accounted for before mapping coordinates.
- DPI scaling and multi-monitor coordinates are tested on Windows.
- Touch down/move/up are represented separately; scroll is not substituted for all gestures.
- Keyboard/IME and modifier keys have explicit protocol messages.
- Focus is acquired deliberately; input is never sent to an unintended window silently.

### Observability
Per session measure capture, encode, network, decode, presentation and input-to-photon latency, plus dropped frames, bitrate, reconnects and codec/backend selected. Logs must not contain captured media or sensitive typed content.

## Quality gates

A release cannot be called production-ready until all are green:

- Windows compile/unit/integration tests.
- Android compile/unit/lint/instrumented tests.
- Physical Windows + Android end-to-end test.
- 30-minute soak test with repeated orientation/window changes.
- Network impairment tests: loss, jitter, disconnect/reconnect.
- Windows DPI 100/125/150%, multiple resolutions, and multi-monitor mapping.
- Android API 26 minimum plus representative modern API levels and at least two physical vendors when available.
- Codec fallback tests and clean error UX when no supported hardware codec exists.
- Pairing/authentication negative tests.
- No unbounded queues/threads and clean shutdown under repeated sessions.

## V1 next implementation order

1. Make CI green and keep it mandatory.
2. Replace development TCP semantics with a session state machine and bounded/authenticated framing.
3. Native Windows window enumeration and Windows Graphics Capture backend.
4. H.264 hardware encoder abstraction and timestamped media packets.
5. Android MediaCodec Surface decoder with frame dropping and lifecycle-safe teardown.
6. Coordinate transform + Windows input backend.
7. Audio capture/playback.
8. Pairing/encryption, discovery, adaptive quality, reconnect and soak tests.

This keeps HandOff's differentiator: a handed-off *window/activity surface*, not a generic whole-desktop remote-control product.

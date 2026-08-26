# HandOff UX and lifecycle contract

HandOff is a continuity product, not a remote-desktop configuration utility. The normal path must hide transport, addressing, codec and diagnostics details.

## Golden path

After one-time pairing:

1. Open HandOff.
2. Trusted nearby devices are discovered and authenticated automatically.
3. If one trusted computer is available, surface its current activity first.
4. Tap **Continue**.
5. Transition directly to the live interaction surface.
6. Tap **Return** to end the remote surface; source state is already current because the application never migrated.

No IP address, port, codec, bitrate or resolution selection is allowed in the primary flow.

## First-run and permissions

- Ask only for capabilities that are required at the moment they become useful.
- Android PC-to-phone receiving requires network access but must not request unrelated camera, contacts, location or storage permissions.
- Discovery implementations that require additional Android runtime permissions must explain the feature before invoking the system permission dialog and remain usable when denied.
- Windows host runs per-user by default. Ordinary capture, discovery and input must not require administrator elevation.
- Firewall setup must be narrowly scoped to HandOff. Failure must be detected and explained without exposing raw socket errors in the primary UI.
- Pairing is explicit once. Trusted devices then authenticate automatically using persisted device credentials.
- Revoked trust immediately terminates active control authorization.

## Lifecycle requirements

The product must be tested across:

- fresh install / first launch
- permission granted, denied, denied permanently, later granted and later revoked
- foreground/background/foreground
- Android activity recreation and orientation change
- process death and cold restart
- Windows login, logout, sleep, wake and host restart
- Wi-Fi loss and recovery
- network change while idle and while live
- laptop unavailable / becomes available
- remote process crash
- source window closes during a session
- decoder/encoder failure
- repeated start/stop sessions without leaked sockets, tasks, surfaces or codecs

## UX states

Primary UI states are deliberately finite:

- Looking: show useful shell immediately; discovery runs behind it.
- Ready: device and likely current activity are actionable.
- Preparing: one calm progress state; no technical jargon.
- Live: content dominates; chrome is minimal and dismissible.
- Unavailable: short human explanation and one recovery action.

Diagnostics may expose RTT, loss, bitrate, FPS, codec, queues and protocol events, but never as required normal-operation controls.

## Interaction principles

- 48dp minimum Android touch targets.
- Edge-to-edge with system insets respected.
- System light/dark appearance by default.
- Motion communicates continuity rather than decoration.
- Touch maps to content coordinates after aspect-fit/crop transforms, never raw display coordinates.
- Swipe feels like content scrolling, not remote mouse dragging.
- Keyboard appears when text input is requested by the remote interaction model.
- Weak networks trigger automatic quality adaptation before user intervention.
- Reconnect is automatic for an authenticated recent session when safe.

## Production acceptance

A feature is not considered ready because it compiles. Release gates include Android unit/lint/instrumented checks, Windows tests, physical Windows↔Android runs, lifecycle matrix, 30-minute soak, repeated reconnect, packet loss/jitter, DPI/multi-monitor, orientation/resize, permission-negative paths, and authentication-negative paths.

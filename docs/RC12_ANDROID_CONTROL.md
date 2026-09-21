# RC12 Android control reliability

RC12 replaces the single opaque gesture path with a layered control engine:

1. Taps first target the smallest enabled clickable Accessibility node under the remote pointer.
2. Wheel input first targets the smallest scrollable node and uses forward/backward Accessibility actions.
3. Custom views, canvases, games and surfaces fall back to a physical `dispatchGesture` touch or swipe.
4. Tap gestures use a stationary path instead of a zero-length line segment.
5. Desktop wheel direction is converted to the matching physical finger direction.
6. Every queued gesture has a completion deadline. An OEM that drops the callback no longer blocks every later gesture.
7. Service interruption/unbinding fails the active command as well as queued commands.
8. Android logcat and the exported session report record delivery/failure evidence.

CI now enables the real HandOff Accessibility service in an Android emulator, opens a non-accessible custom View, injects a tap through the production service, and requires the View to receive `ACTION_UP`. The earlier test only checked that Android listed the service and advertised gesture capability.

Android still requires the user to enable an Accessibility service once. A normal third-party application cannot grant itself this special access; attempting to bypass that boundary would be insecure and rejected by Android. After it is enabled, control execution and recovery are handled by HandOff itself.

## P2PShare transport finding

P2PShare v2 performs real UDP hole punching: both apps retain one UDP socket, discover its public mapping with STUN, and exchange HMAC-authenticated HELLO probes on that mapping. HandOff RC11 instead added automatic UPnP TCP mapping. These are different mechanisms.

The P2PShare v2 reliability layer is specialized for file offers, chunks, repair ranges and completion hashes. HandOff needs a long-lived ordered interactive stream carrying control, audio and bounded video frames. Reusing only the punch while continuing with TCP/TLS would not work because a UDP NAT mapping cannot receive TCP. The correct follow-up is to place HandOff framing over a UDP-native reliable transport (QUIC) and let the authenticated punch feed that transport; this remains a transport migration, not a one-file copy.

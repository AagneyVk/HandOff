# Android client

Android is the first HandOff receiver/controller.

V0 responsibilities:

- discover/connect to a desktop host on the same LAN
- show host capabilities and capturable windows
- start/stop one handoff session
- decode/render the incoming video stream
- preserve the source aspect ratio and expose the exact content rectangle
- convert touch coordinates to normalized `0..1` source coordinates
- map tap, drag/swipe and scroll gestures to protocol input messages
- collect latency/drop telemetry

The client must not assume the source is Windows or Linux; behavior is driven by host capability negotiation.

# V0 implementation plan

## Definition of done

V0 is complete when a real desktop window can be selected on both supported desktop hosts and viewed/controlled from Android over a LAN with recorded latency metrics.

Do not add accounts, cloud relays, AI, clipboard sync, file transfer, remote filesystem access, or general remote-desktop features before this works.

## Phase 0 — protocol harness

- Define versioned control messages.
- Implement host capability advertisement.
- Implement fake window source and deterministic test frames.
- Implement normalized pointer/scroll events.
- Add timestamp echo/latency probe.
- Add protocol tests that do not require a GUI.

Exit: Android can discover/connect to a development host, receive a generated moving test frame, and send touch coordinates back correctly.

## Phase 1 — Windows real window

- Enumerate capturable top-level windows.
- Capture a selected window using Windows Graphics Capture.
- Encode frames with a low-latency configuration.
- Decode/render on Android.
- Map tap and vertical swipe/scroll back to the selected window.

Exit: browser video can be watched on Android and a swipe changes the actual browser state.

## Phase 2 — Linux/Arch real window

- Detect Wayland vs X11.
- Wayland: negotiate window capture through portal/PipeWire where available.
- X11: compatibility capture backend.
- Implement capability-aware input backend; never pretend unsupported Wayland injection works.
- Reuse the same protocol and Android client.

Exit: the same Android build can hand off a browser window from Windows or Arch.

## Phase 3 — audio

- Capture application/system audio using the best available OS-specific path.
- Synchronize audio/video.
- Avoid source/receiver double playback where feasible.

## Phase 4 — continuity UX

Only after the transport is solid:

- device discovery without IP entry
- persistent trusted pairing
- one-action `HandOff` command
- `Return` action
- portrait/landscape adaptation
- reconnect after brief network interruption
- adaptive bitrate/frame rate
- optional background-window behavior

## Benchmarks

Record at minimum:

- source resolution / receiver resolution
- FPS
- bitrate
- capture time
- encode time
- network transit estimate
- decode/render time
- input-to-visible-response latency
- CPU utilization
- GPU utilization where available
- dropped frames

Initial product target: interactions should feel immediate on a healthy LAN. We will set hard latency targets after measuring the first real pipeline rather than inventing numbers before hardware tests.

## Non-goals for V0

- internet/WAN relay
- iOS
- DRM bypass
- hidden capture
- unattended remote control
- process migration
- URL/session reconstruction
- multiple simultaneous handed-off windows

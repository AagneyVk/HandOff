# Architecture

## Core idea

HandOff separates **execution** from the **interaction surface**. A handed-off application continues running on its source machine. The receiver gets a low-latency representation of that application's window and sends normalized input events back.

This avoids trying to migrate process memory, browser sessions, application state, cookies, or URLs.

## V0 data plane

```text
Desktop application window
        |
        v
OS capture backend
        |
        v
video encoder
        |
        +-----------------------> Android decoder -> Surface
        ^                                      |
        |                                      v
OS input backend <--- normalized input <--- touch mapper
```

## Control plane

The control plane is separate from media. It handles device discovery, pairing, window enumeration, session start/stop, stream metadata, orientation, capability negotiation, telemetry and input events.

Initial transport choices are intentionally replaceable. The protocol must not assume a particular media transport.

## Shared protocol

All coordinates sent by clients are normalized to the handed-off content rectangle (`0.0..1.0`). The host converts them to source-window coordinates. This prevents Android resolution/orientation from leaking into platform input backends.

Initial message families:

- `hello` / `capabilities`
- `windows.list` / `windows.snapshot`
- `session.start` / `session.started` / `session.stop`
- `stream.config`
- `input.pointer`
- `input.scroll`
- `input.key`
- `telemetry.latency`
- `error`

Every message carries a protocol version, message ID, session ID where applicable, and monotonic timestamp where timing matters.

## Host backend boundary

A desktop backend implements four conceptual interfaces:

```text
WindowProvider
  list_windows()
  resolve_window(id)

CaptureProvider
  start(window, frame_sink)
  stop()

InputProvider
  pointer(window, normalized_x, normalized_y, action)
  scroll(window, dx, dy)
  key(window, key, action)

AudioProvider
  start(target, audio_sink)
  stop()
```

### Windows

Target implementation: Windows Graphics Capture for window capture, with native Windows input/window APIs behind the input adapter. Hardware video encoding should be preferred when available.

### Linux / Arch

Linux must support modern Wayland rather than assuming X11. The intended modern capture path is PipeWire with the desktop portal where required by the compositor. X11-specific capture/input may exist as a compatibility backend, not as the architecture.

Wayland intentionally restricts arbitrary global capture/input, so capability detection is mandatory and input support may vary by compositor/portal. We must report that honestly rather than silently falling back to unsafe assumptions.

## Android

Android is initially a receiver/controller. It owns:

- LAN discovery and pairing UI
- session selection
- hardware-backed video decode where available
- aspect-ratio aware rendering
- touch -> normalized input mapping
- latency telemetry

Android -> desktop capture is a later milestone and should live behind the same conceptual capture/session interfaces.

## Security model

V0 is LAN-only but must not equate LAN with trust. Before broader use we require explicit pairing and authenticated sessions. Input is accepted only for the currently authorized handoff session. A session must never silently expand from one selected window to unrestricted desktop control.

## Performance principle

Measure each stage rather than optimizing blindly:

```text
capture -> encode -> network -> decode -> display
input -> network -> inject -> app render -> capture -> display
```

The second metric is the important product metric: **input-to-visible-response latency**.

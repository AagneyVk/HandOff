# Implemented V1 runtime

## RC4 Android → desktop

After the phone has authenticated to the pinned desktop host, it may request `source.start {width,height,codec:"h264",audio,controls}`. The desktop returns a random reverse `session` and opens a dedicated viewer. Android then invokes the OS MediaProjection consent screen; Android 14+ can let the user select one app or the full display. Capture runs in a visible `mediaProjection` foreground service and ends when the system chip, notification action, phone UI, desktop viewer, connection or device lock stops it.

Each `source.frame {session,sequence}` is followed atomically by one Annex-B H.264 keyframe. The desktop decodes it with PyAV and returns `source.ack`; Android requests a new synchronization frame only after that acknowledgement, preventing a hidden queue and avoiding broken prediction chains when intermediate encoder output is discarded. Optional `source.audio` packets carry the same bounded PCM format as desktop audio. Android playback capture is limited to Android 10+ media/game usages and applications that permit capture.

Desktop input is returned as `phone.tap`, `phone.drag`, `phone.scroll`, `phone.text`, `phone.key` under the reverse session. Android accepts it only while that session exists. Gesture/text execution additionally requires the user-enabled, non-exported HandOff Accessibility service. Pairing or projection permission does not enable Accessibility. General key injection is intentionally not attempted: Back/Home/Recents, Enter, Backspace and text-field editing use documented accessibility actions; unsupported arrow behavior is ignored.

## RC3 continuity extensions

RC3 makes an explicitly selected monitor a first-class source alongside an app window on Windows and X11. App-only sharing never falls back to a display. `windows` entries include `kind: "window"|"display"`; `started` reports `target`, `profile`, `fps`, and supported `controls`. Display-wide input is permitted only after the desktop owner selects and approves that display.

The Android client offers `smooth` (1280×720, 30 fps, 3 Mbps H.264), `balanced` (1600×1000, 30 fps, 4 Mbps), and `sharp` (1920×1080, 24 fps, 6 Mbps) upper bounds. Source aspect ratio is retained and these are caps, not guaranteed rates. `drag` carries bounded normalized start/end coordinates. Windows additionally advertises `text` (1–256 Unicode characters) and a small allowlist of `key` values. All controls require the current session and latest acknowledged frame; display geometry or app identity changes invalidate them.

## RC2 media extensions

The JPEG base protocol below remains compatible. RC2 adds `codecs: ["h264", "jpeg"]` and optional `audio: true` to `start`. H.264 uses packet kind **3** (Annex B access unit); PCM audio uses kind **4** (48 kHz stereo signed 16-bit little endian, 960 samples/channel). `frame` includes `codec`; `started` includes `codec`, `encoder`, `width` and `height`. Hardware negotiation fails back to JPEG before the first frame. Each `audio` metadata packet (`session`, `rate`, `channels`, `format: "s16le"`) immediately precedes its PCM packet. `audio.stopped` closes playback independently of video. Both desktop and Android must opt in to all-computer output audio.

H.264 acknowledgements follow MediaCodec output submission to its Surface; JPEG acknowledgements follow UI display scheduling. Neither is an optical end-to-end latency measurement. See [RC2 media and release details](RELEASE.md) for buffering, hardware validation and signing requirements.

## Base protocol and trust model

The desktop owner explicitly selects a window. Only that window is listed to authenticated clients, and one phone owns the live session at a time. Stopping sharing invalidates the selection immediately, blocks subsequent input and tears down streaming through a 200 ms authorization monitor. A packet already on the network cannot be recalled.

## Pairing and identity

The host creates an ECDSA P-256 TLS identity in the per-user HandOff directory. Its SHA-256 certificate fingerprint is supplied out of band in the desktop pairing QR code. Android's trust manager checks the exact fingerprint and certificate validity before sending any credentials. It does not use a trust-all manager or accept an unverified certificate on first contact.

An invitation contains the computer address, port, fingerprint and 256-bit random code. It expires after five minutes and is single-use. A successful pair returns a random device ID and 256-bit token over TLS. The host persists only its SHA-256 token digest; Android encrypts the saved credentials with an AES-GCM key in Android Keystore. Host persistence uses atomic replacement and POSIX owner-only file modes; on Windows it lives under the current user's LOCALAPPDATA and inherits its ACL. Local administrators remain trusted. Backups of the Android app are disabled.

QR codes and copied links are credentials: only scan/copy from your own host. No unattended LAN discovery is treated as proof of identity. Forgetting a computer on Android clears local storage; revoking on desktop invalidates credentials at the host. All-device revocation also cancels pending invitations.

## Transport

TLS 1.2 or newer, TCP 47821. Each packet is a four-byte unsigned big-endian length (including kind), a one-byte kind, then payload. Kind 1 is UTF-8 JSON; kind 2 is JPEG. Control payloads are at most 16 KiB and all packets at most 2 MiB. All JSON messages include integer `v: 1` and `type`.

First message: `pair {code,name}` → `paired {device,token}`, or `auth {device,token}` → `ready`.

Authenticated messages:

| Request | Response/behavior |
| --- | --- |
| `windows` | `windows {windows:[...]}` includes only the locally approved app or display |
| `start {window}` | `started {session,codec:"jpeg",audio:false}`, then frames |
| `ack {session,sequence}` | Grants the next frame after Android decoding/display scheduling |
| `tap {session,sequence,x,y}` | Normalized coordinates in the captured client area |
| `scroll {session,sequence,x,y,dy}` | Bounded scroll amount |
| `drag {session,sequence,x0,y0,x1,y1}` | Bounded direct mouse drag |
| `text {session,sequence,text}` | Windows-only Unicode entry, maximum 256 characters |
| `key {session,sequence,key}` | Windows-only allowlisted navigation/editing key |
| `stop {session}` | Releases capture and returns `stopped` |
| `ping` | `pong` |

Each `frame {session,sequence,width,height}` packet is immediately followed by a JPEG packet under one output lock. One image is in flight. The host waits for its acknowledgement before capturing the next image, preventing an unbounded queue when the network or phone is slow. Capture occurs in a separate killable process with a four-second deadline. Client input is accepted only for the acknowledged current frame, active session and unchanged window identity. Resize mismatches reject input until a matching frame arrives.

Android disconnects on backgrounding, including rotation through activity recreation. It retains the paired credentials but requires reconnect/continue again. Heartbeats run every eight seconds; socket/capture deadlines end stale sessions. No automatic reopening of an app occurs after a disconnect.

## Capture and input boundaries

Windows: PrintWindow client-area capture or explicit per-monitor BitBlt capture, bounded GDI allocations and explicit handle signatures. Some GPU/DRM app surfaces return black content. Input for app targets requires foreground, matching dimensions and WindowFromPoint/GetAncestor validation. Display targets deliberately cover everything visible on that monitor and therefore allow desktop-wide input. OS-global SendInput has an unavoidable focus race; this is not an OS-enforced per-window input sandbox. UIPI restrictions apply.

X11: XComposite offscreen capture of a selected client or explicit root-display capture; only supported 24/32-bit TrueColor formats are decoded. Native Wayland is rejected. App input is checked against foreground/geometry/point ancestry under a brief server grab. Display sharing permits display-wide XTest input. The desktop/session's X server remains trusted.

## Primary implementation references

- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- https://github.com/python-xlib/python-xlib/blob/master/Xlib/ext/composite.py
- https://developer.android.com/reference/javax/net/ssl/SSLSocket
- https://developer.android.com/topic/performance/graphics/load-bitmap
- https://github.com/journeyapps/zxing-android-embedded

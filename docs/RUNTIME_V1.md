# Implemented V1 runtime

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
| `windows` | `windows {windows:[...]}` includes only the locally approved app |
| `start {window}` | `started {session,codec:"jpeg",audio:false}`, then frames |
| `ack {session,sequence}` | Grants the next frame after Android decoding/display scheduling |
| `tap {session,sequence,x,y}` | Normalized coordinates in the captured client area |
| `scroll {session,sequence,x,y,dy}` | Bounded scroll amount |
| `stop {session}` | Releases capture and returns `stopped` |
| `ping` | `pong` |

Each `frame {session,sequence,width,height}` packet is immediately followed by a JPEG packet under one output lock. One image is in flight. The host waits for its acknowledgement before capturing the next image, preventing an unbounded queue when the network or phone is slow. Capture occurs in a separate killable process with a four-second deadline. Client input is accepted only for the acknowledged current frame, active session and unchanged window identity. Resize mismatches reject input until a matching frame arrives.

Android disconnects on backgrounding, including rotation through activity recreation. It retains the paired credentials but requires reconnect/continue again. Heartbeats run every eight seconds; socket/capture deadlines end stale sessions. No automatic reopening of an app occurs after a disconnect.

## Capture and input boundaries

Windows: PrintWindow client-area capture, bounded GDI allocations and explicit handle signatures. Some apps return black content. There is no whole-screen fallback. Input requires the target to be foreground, dimensions to match and WindowFromPoint/GetAncestor to resolve to the selected window. OS-global SendInput has an unavoidable focus race; this is not an OS-enforced per-window input sandbox. UIPI restrictions apply.

X11: XComposite offscreen pixmap capture of the selected client; only supported 24/32-bit TrueColor formats are decoded. Native Wayland is rejected. XTest input is checked against foreground/geometry/point ancestry under a brief server grab. The desktop/session's X server remains trusted.

## Primary implementation references

- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- https://github.com/python-xlib/python-xlib/blob/master/Xlib/ext/composite.py
- https://developer.android.com/reference/javax/net/ssl/SSLSocket
- https://developer.android.com/topic/performance/graphics/load-bitmap
- https://github.com/journeyapps/zxing-android-embedded

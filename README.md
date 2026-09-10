# HandOff

Continue a running desktop app on Android over your local network. The app keeps running on the computer; HandOff sends its selected window to your phone and maps touch back to it.

## Get started

1. Open **Actions → Framework tests** and choose a successful run on `v1`.
2. Download **HandOff-Windows**, extract it fully, and launch `HandOff.exe`. Keep the `_internal` folder beside it.
3. Download **handoff-v1-debug-apk**, extract it, and install the APK on Android 8 or newer.
4. Put both devices on the same private network. Allow HandOff on **private networks** if Windows Firewall asks.
5. In desktop HandOff, select an app and click **Share selected app**.
6. Choose the computer's LAN address and click **New pairing code**. In Android HandOff, tap **Pair with QR code** and scan it.
7. Tap **Continue here**. Tap the video to click; swipe vertically to scroll. Keep the shared app foreground on the computer to allow input.
8. Tap **Return** on Android or **Stop sharing** on the computer to end the session.

The code expires after five minutes and works once. Afterwards, the phone can reconnect using its saved pairing. **Remove all paired phones** revokes access. Camera permission is used only by the QR scanner; **Use a pairing link** is also available.

## Implemented

- Desktop sharing UI and Android connection/live/return UI.
- TLS 1.2+ with explicit SHA-256 certificate pinning from the locally displayed QR code.
- Single-use 256-bit pairing invitations, per-device credentials, revocation, hashed host-side tokens and Android Keystore-encrypted credential storage.
- Windows client-area capture and Linux X11 XComposite window capture. Neither falls back to capturing the whole desktop.
- Bounded JPEG framing, decoder dimension checks, one frame in flight, capture-process deadlines and network timeouts.
- Foreground and occlusion checks before pointer input; letterbox-aware Android coordinates, session/sequence validation and input rate limits.
- Return, disconnect, closed-window/capture error handling, and automatic disconnect when Android goes into the background.
- Windows executable and Android debug APK build artifacts.

## Current release scope

This is an **RC implementation**, not a claim of completed production certification. Video is JPEG at a maximum of 12 frames per second, up to 1600 × 1000; actual throughput depends on the app and network. Audio, keyboard entry, drag-and-drop, Android-as-source, native Wayland, hardware video codecs, signed distribution and seamless background reconnection are not implemented. Protected or GPU-rendered windows may return blank frames through PrintWindow. Elevated Windows apps cannot necessarily accept input from a normal host process.

The Android artifact is debug-signed, and the Windows executable is unsigned. Do not call build success a real-device latency or compatibility measurement. Physical Android ↔ Windows/Arch acceptance testing remains required before promoting a stable release.

## Run from source

Windows: install Python 3.12+, then double-click `start-windows.bat`, or:

```sh
python -m pip install -r host/requirements.txt
python -m host.app
```

Arch Linux: use an X11 session; install `python`, `tk`, `libxcomposite` and a working X server. Then:

```sh
bash start-linux.sh
```

Other Linux distributions also need Python venv/Tk support. Native Wayland is rejected explicitly. The host uses TCP **47821**; no router port-forwarding is needed. If an address changes, generate a fresh pairing code. There is no cloud relay or paid API.

Android development: open `android` in Android Studio with JDK 17 and Android SDK 35, or run installed Gradle 8.10.2:

```sh
cd android
gradle :app:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

## Verification

```sh
python -m pip install -r host/requirements.txt
python -m unittest discover -s tests -v
```

CI runs encrypted socket integration tests, Windows native pixel capture, Linux XComposite pixel capture under Xvfb, Android JVM tests/build/lint and Windows packaging. Test fixtures for transport use generated images; separate native tests exercise real window APIs.

See [runtime protocol](docs/RUNTIME_V1.md) and [acceptance checklist](docs/ACCEPTANCE.md). Older architecture documents describe the vision; the implemented runtime is `host/runtime` and the Android V1 framed-TLS client. The old newline-delimited V0 harness is for development only and is incompatible with the new Android client.

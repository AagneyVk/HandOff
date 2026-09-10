# HandOff

Local-first application continuity for Android and desktop. **Development preview, not a production release.**

## Current implementation

The Android client connects to a manually entered Windows host address and lists real open windows. It provides refresh, cancellation, disconnect, and connection failure states. Network writes run off the UI thread; connection callbacks are delivered on the UI thread, and stale connections cannot close a newer connection.

Live window capture, media transport, Android video decoding, audio, authenticated pairing, automatic discovery, and Linux capture are not implemented. The earlier animated “Live” screen was a local demonstration, not received video. Session start now reports this limitation, and remote input is disabled until authenticated live sessions exist.

## Run the Windows preview

Install Python 3.12 or newer, open a terminal at the repository root, and run:

```sh
python -m host.windows.v1_host
```

Connect Android to the same trusted LAN and enter the computer's IPv4 address in HandOff. The preview listens on TCP port 47820. Allow Python on private networks in Windows Firewall if prompted. The window catalog contains application titles and is not encrypted or authenticated: do not expose this preview port to the internet or an untrusted network.

## Build Android

Open `android` in Android Studio with JDK 17 and Android SDK 35, or use installed Gradle 8.10.2:

```sh
cd android
gradle :app:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

The GitHub Actions Android job publishes the debug APK as an artifact. No Gradle wrapper is currently committed.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests include actual TCP exchanges for hello, window listing, malformed message recovery, and rejection of unavailable sessions and remote input. Native window enumeration tests require Windows. Android compilation and lint run in CI; a passing build does not establish real-device streaming support.

## Production completion gates

- Authenticated, encrypted pairing with local consent and revocation.
- Windows and Linux native window capture, bounded media queues, codec negotiation and Android decoding.
- Input routed only to the visible authorized application, matching the video content rectangle.
- Lifecycle handling, reconnection, discovery, packaging and signed releases.
- Measured Android/Windows/Linux device tests for video, audio, input, rotation, network loss and repeated handoff.

Architecture proposals in `docs` describe the intended product, not implemented capabilities.

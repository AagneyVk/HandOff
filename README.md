# HandOff

Continue a running app or display in either direction between Android and your computer. The source device keeps running it; HandOff carries live pixels, permitted playback audio and scoped control through one pinned-TLS connection. It prefers the local network and can connect directly over the Internet when the computer's router supports automatic port mapping.

## Get started

1. Open **Actions → Framework tests** and choose a successful run on `v1`.
2. Download **HandOff-Windows**, extract it fully, and launch `HandOff.exe`. Keep the `_internal` folder beside it.
3. Download **handoff-v1-debug-apk**, extract it, and install the APK on Android 8 or newer.
4. For first pairing, put both devices on the same private network. Allow HandOff on **private networks** if Windows Firewall asks. The desktop will show whether zero-cost direct Internet access is available through your router.
5. In desktop HandOff, select an app or **Entire display** and click **Share selected**.
6. Choose the computer's LAN address and click **New pairing code**. In Android HandOff, tap **Pair with QR code** and scan it.
7. Pick Smooth, Balanced or Sharp and tap **Continue here**. Tap to click, use Scroll mode for reels/documents, or Drag mode for sliders and direct manipulation. Windows also supports sending text and Enter from the phone. Keep an app-only target foreground to allow input.
8. Tap **Return** on Android or **Stop sharing** on the computer to end the session.

For Android → computer, connect the paired devices and choose **Share phone to computer**. Android's system dialog lets you approve one app or the whole display each time. The computer opens a dedicated phone window. To control it with mouse, wheel and keyboard, tap **Enable phone control** first and explicitly enable the HandOff Accessibility service. Phone media audio is optional and requires Android's audio-record permission because that is the permission Android uses for playback capture; HandOff configures playback capture, not microphone input.

The code expires after five minutes and works once. Afterwards, the phone can reconnect using its saved pairing. **Remove all paired phones** revokes access. Camera permission is used only by the QR scanner; **Use a pairing link** is also available.

## Implemented

- Desktop sharing UI and Android connection/live/return UI.
- TLS 1.2+ with explicit SHA-256 certificate pinning from the locally displayed QR code.
- Single-use 256-bit pairing invitations, per-device credentials, revocation, hashed host-side tokens and Android Keystore-encrypted credential storage.
- Explicit Windows monitor capture, Windows client-area capture, Linux X11 display capture and XComposite app-window capture. Display sharing is a separate visible choice; app sharing never silently expands to the desktop.
- Hardware H.264 probing (NVENC/QSV/AMF), Android MediaCodec surface rendering and JPEG compatibility fallback.
- Explicit opt-in computer-output audio, bounded PCM queues and Android playback; no microphone fallback.
- Bounded media framing, decoder dimension checks, one video frame in flight, capture-process deadlines and network timeouts.
- Tap, wheel-style scrolling and true drag gestures; Windows Unicode text/navigation keys. App targets retain foreground/occlusion checks, while display targets are explicitly authorized for desktop-wide control.
- Smooth (1280×720/30), Balanced (1600×1000/30) and Sharp (1920×1080/24) bounded stream profiles. One-frame backpressure prevents lag accumulation.
- Android app/full-display capture through MediaProjection, hardware H.264 encoding, one-frame keyframe backpressure and an aspect-correct desktop phone viewer.
- Explicit Android Accessibility control for desktop tap, drag, wheel scrolling, text, Back, Home, Enter and editing actions. It is never enabled or invoked merely by pairing.
- Optional Android 10+ media/game playback capture to the computer. Apps can opt out and protected/DRM content can remain silent or black.
- Return, disconnect, closed-window/capture error handling, and automatic disconnect when Android goes into the background.
- LAN-first reconnect with a second, automatically mapped direct-Internet candidate. The mapping exists only while HandOff runs and carries the same pinned-TLS protocol; no screen, audio or input is sent through a cloud relay.
- Windows executable and Android debug APK build artifacts.

## Current release scope

This is **RC11**. Both directions are implemented, but physical GPU/audio/device and router compatibility must still be measured on your own hardware. CI validates the encrypted media protocols, H.264 encode/decode plumbing, native desktop capture/input, Android build/lint and lifecycle behavior that can run without bypassing Android's mandatory projection/accessibility consent. Direct Internet mode works only where the computer's router provides UPnP and a genuine public IPv4 address. CGNAT, symmetric NAT, disabled UPnP and restrictive firewalls require a relay or VPN, which this zero-cost direct-only mode deliberately does not hide. Per-app desktop audio isolation, tightly synchronized A/V, file drag-and-drop and native Wayland remain outside this build. Linux remote text entry is not advertised because portable Unicode injection is not reliable across X11 keyboard maps.

See [media, physical validation and signing](docs/RELEASE.md). The signed-release workflow is ready but requires your publisher credentials and physical session evidence. Ordinary CI artifacts are still debug-signed Android and unsigned Windows.

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

Other Linux distributions also need Python venv/Tk support. Native Wayland is rejected explicitly. The host uses TCP **47821** internally. It requests a temporary UPnP mapping automatically and removes it at shutdown; no manual router setup is needed on compatible networks. If the desktop's public address changes, generate and scan a fresh pairing code. There is no cloud relay, account or paid API.

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

CI runs encrypted socket integration tests, Windows native pixel capture, Linux XComposite pixel capture under Xvfb, Android JVM tests/build/lint, an Android H.264/audio emulator exchange and Windows packaging/launch checks. Test fixtures for transport use generated images; separate native tests exercise real window APIs.

See [runtime protocol](docs/RUNTIME_V1.md) and [acceptance checklist](docs/ACCEPTANCE.md). Older architecture documents describe the vision; the implemented runtime is `host/runtime` and the Android V1 framed-TLS client. The old newline-delimited V0 harness is for development only and is incompatible with the new Android client.

## Installing and updating

Use the [GitHub Releases](https://github.com/AagneyVk/HandOff/releases) Windows installer, then Check for updates inside HandOff. Android signed updates require one-time signing setup. See [update setup and migration](docs/UPDATES.md).

# Phase 0 development harness

This harness proves the HandOff control loop before native capture/encoding is introduced.

## Host

Requires Python 3.11+ and no third-party packages.

From the repository root:

```bash
python -m unittest discover -s tests -v
python -m host.shared.dev_host
```

The host listens on TCP `47820` on all interfaces. Allow that port through the local firewall only on the trusted LAN used for development.

Find the host's LAN address and enter it in the Android development client.

## Android

Open the `android/` directory in Android Studio and run the `app` module on a physical Android device connected to the same LAN.

1. Enter the desktop LAN IP.
2. Tap **Connect**.
3. Tap **Start test**.
4. Tap the synthetic surface. The host should log normalized pointer coordinates.
5. Drag vertically. The host should log normalized scroll deltas.
6. Observe `telemetry.latency` as the last received message after input.

## What the moving grid means

The moving grid/circle is rendered locally by Android in Phase 0. It deliberately does **not** pretend that media streaming already exists. The control protocol, session lifecycle, coordinate mapping and latency acknowledgement are being validated independently first.

The next media milestone replaces this synthetic mode with an encoded desktop frame source while keeping the same control/session protocol.

## Security note

This development host has no pairing/authentication yet. It is for a trusted development LAN only. Do not expose TCP 47820 to the internet or an untrusted network.

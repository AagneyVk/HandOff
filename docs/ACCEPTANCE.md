# Stable-release acceptance

Automated build results are recorded in GitHub Actions. These physical-device checks are release gates, not claims that they were executed in the build container.

- Pair Windows and an Android phone via QR; reject a QR whose certificate pin was altered.
- Connect again after restarting both apps; remove paired phones on desktop and confirm the old phone loses access.
- Share a browser and a native editor; confirm visible content is their running state, with no reload or URL recreation.
- Share each monitor explicitly; confirm only the chosen monitor appears, coordinates map correctly, and app-only approval never expands to a display.
- Tap the center and all four edges in portrait and landscape; black letterbox bars must never click.
- Scroll a document; cover the shared app and verify input is rejected rather than clicking the covering app.
- Test Scroll and Drag modes. On Windows, send ASCII, non-ASCII and emoji text plus Enter; verify typing is rejected when an app-only target loses foreground.
- Exercise Smooth, Balanced and Sharp on portrait/landscape phones and confirm the stream remains bounded after resize.
- From Android, approve one-app projection and whole-display projection separately. Confirm the desktop viewer preserves aspect ratio and closes from the phone, notification/system projection chip, desktop window, screen lock and network loss.
- With Accessibility disabled, confirm phone sharing is view-only. Enable it explicitly and test desktop tap, drag, wheel, text, Back/Home/Enter/Backspace. Disable it during a session and confirm control stops.
- Request Android playback audio with an allowed media app, an opted-out app and protected content. No path may substitute microphone capture.
- Resize, minimize and close the app during streaming. Verify a useful error/return state and no stuck capture process.
- Stop on desktop while the phone is live and while the connection stalls. No new input may be accepted.
- Disable Wi-Fi, reconnect, and repeat start/return 20 times; check host child processes and phone memory.
- Repeat capture/input on Arch X11 with a compositor. Wayland should produce an explicit unsupported-session message.
- Measure frame rate, p50/p95 input response and bandwidth on actual LAN hardware; no performance figures are inferred from unit tests.
- Verify packaged Windows executable on a clean non-development machine and APK installation on supported Android versions.
- Before a stable public release: signing, upgrade strategy, compatibility matrix and security review; implement/test missing audio if audio is part of the advertised product.

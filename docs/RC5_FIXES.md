# RC5 physical-test fixes

Addresses reported phone-control setup failure, sluggish phone motion, and absent desktop video on Android.

- Accessibility service is exported for system discovery and remains protected by Android's signature-level BIND_ACCESSIBILITY_SERVICE permission.
- Setup explains screen capture vs Accessibility vs optional playback audio. Includes Android's user-operated restricted-settings path for trusted sideloaded APKs. Availability refreshes while running and is sent to the laptop without restarting the session.
- Settings navigation preserves the connection. Controls use full display metrics. Choose Entire screen for matching capture/input coordinates; single-app capture offsets are not supported.
- Phone H.264 sends normal reference frames at a configured 30 fps, up to three frames in flight. Congestion discards dependent frames until a new keyframe, preventing a growing backlog. Buffered TLS packet writes and coalesced desktop redraws remove redundant work. Actual latency and achieved fps require hardware measurement.
- Desktop approval changes are announced to the phone automatically. If Android cannot initialize/render H.264, the session stops and retries JPEG over the existing authenticated connection. Decoder surface changes trigger recreation.
- Both directions cannot run simultaneously in one connection, avoiding a recursive screen-within-screen session.

Verification includes JVM frame-window dependency tests, TLS control-capability changes and approval announcements, actual desktop H.264 interframe decode, Android system discovery of the Accessibility service, and emulator missing-surface recovery to JPEG.

Physical acceptance: install both RC5 builds; enable HandOff phone control through the setup dialog; check laptop label changes live; share Entire screen; click/swipe/type; disable Accessibility and verify input stops. Return phone sharing; share a desktop target and verify it appears automatically; start viewing on the phone. Compare motion lag with RC4 on the same network. Test rotation and protected apps separately; CI cannot certify device-specific rendering or latency.

Sources: https://developer.android.com/guide/topics/ui/accessibility/service and https://support.google.com/android/answer/12623953

# Media and signed release procedure

## Video

Android requests H.264 by default. The capture worker tests NVIDIA NVENC, Intel Quick Sync, then AMD AMF through PyAV. A codec is advertised only after it produces an immediate Annex B access unit. No hardware encoder means JPEG fallback. Select **Compatibility video (JPEG)** on Android if a device decoder is incompatible. Smooth/Balanced run up to 30 fps and Sharp up to 24 fps; JPEG remains capped at 12 fps. These are bounds, not measured performance. Capture uses PrintWindow/BitBlt on Windows and XComposite/root capture on X11 with CPU pixel readback; it is not a zero-copy GPU pipeline. Resize recreates the encoder and decoder.

CI uses libx264 only for its controlled H.264 fixture. Passing that test validates protocol/decode plumbing, not a physical NVENC/QSV/AMF device. The shipped selector never reports libx264 as hardware acceleration.

## Audio

Enable **Share computer audio (all apps, never microphone)** on desktop and **Play computer audio (all apps)** on Android before Continue. This is explicitly output-device loopback, not per-application audio isolation. It may include notifications and sound from other apps. Both switches default off. A missing output/loopback device is an error; microphone capture is never a fallback.

PCM is 48 kHz, stereo, signed 16-bit little endian in 20 ms chunks. Capture and playback queues are bounded. Old capture chunks are discarded instead of accumulating delay. Return/disconnect ends capture and playback. Audio and video currently use the same encrypted TCP connection; severe network congestion can interrupt sound, and there is no shared media-clock A/V synchronization yet. For Linux, a PulseAudio-compatible server (including PipeWire's compatibility service) is required.

## Physical validation

1. Install an APK from a successful **Framework tests** run and its matching desktop source/executable.
2. Share an app, request normal video and audio, and use it for at least 60 seconds. Confirm the displayed encoder is hardware H.264.
3. Check audible sound, visible content, taps/scroll, resize and repeated Return/reconnect. Verify stopping desktop sharing prevents subsequent input. Turn audio off and confirm sound stops.
4. Return, then tap **Export session report** on Android. This report contains counts and the exact source revision, not pairing credentials or window titles.
5. Run `python tools/validate_session.py handoff-session.json --revision <tested SHA>`.

The checker requires a reported physical Android device, a hardware encoder, at least 60 seconds/600 decoded frames, average decoding rate ≥10 fps, audio packets and no recorded connection errors. These are minimum evidence gates, not quality certification. Device classification is a heuristic and the JSON is not cryptographically attested. Packet reception alone does not prove audible playback, image quality or low input latency; manual checks are required.

## Signing credentials

Provide these repository Actions secrets using GitHub settings; never commit or paste private keys into source:

- `ANDROID_KEYSTORE_B64`: base64 of the existing release JKS/PKCS12 file.
- `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
- `ANDROID_SIGNING_SHA256`: expected publisher certificate SHA-256 fingerprint.
- `WINDOWS_CERT_PFX_B64`, `WINDOWS_CERT_PASSWORD`: trusted code-signing certificate and key. A hardware-bound/cloud signing certificate needs a provider-specific signing adapter instead of a PFX export.

The **Signed release candidate** manual workflow requires the exact tested SHA, the exported report encoded as base64, and confirmation of manual quality checks. It builds signed APK/Windows artifacts, checks the Android signer fingerprint and Windows trust chain, and smoke-tests the signed executable. It fails when credentials/evidence are missing; it never substitutes debug/self-signed publisher keys. It does not automatically publish a public GitHub release.

The ordinary CI artifacts remain debug-signed Android / unsigned Windows. Installing a release-signed APK over the debug APK requires removing the debug app first because their signing identities differ. Keep and back up the actual release key to preserve future upgrade compatibility.

## References

- https://developer.android.com/reference/android/media/MediaCodec
- https://developer.android.com/tools/apksigner
- https://developer.android.com/studio/publish/app-signing
- https://pyav.org/docs/stable/api/codec.html
- https://soundcard.readthedocs.io/en/latest/

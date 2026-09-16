# Install once, update from HandOff

Windows: download `HandOff-Setup.exe` from GitHub Releases, run it, and use the Start menu shortcut. No ZIP extraction or Python installation is required. The per-user installer does not require administrator access. It keeps pairing data in `%LOCALAPPDATA%/HandOff`, separately from program files. Existing portable users can close their old copy and run Setup; pairing stays in the same location.

Inside HandOff, choose Check for updates → Download update → Install update. The download is size-bounded and checked against the GitHub release asset SHA-256 digest. Installation closes HandOff after confirmation; finish Setup with Open HandOff selected. A failed download can be retried and never launches an installer. Windows publisher signing is not yet configured for this installer; it is not advertised as signed.

Android: App updates → Check for updates → Download update → Install update. Android may require Allow from this source for HandOff; return and tap Install update again. Android always presents the install confirmation. The app checks the download digest, package name, version code and exact signing identity before offering installation. Only the private updates cache directory is shared with the system installer.

## One-time Android signing setup

On your own computer, install Java (keytool) and GitHub CLI, sign in using `gh auth login`, then run from the repository:

```
python tools/setup_android_signing.py
```

This generates a permanent private key only if none exists, keeps it under your home directory `.handoff-signing`, and uploads five signing secrets to this repository through GitHub CLI. Back up that directory securely. Never commit it, paste its contents into chat, or replace the signing key for routine updates. If you already configured an external release key, keep using that key and do not generate a replacement.

Rerun the Framework tests workflow on main after configuring signing, or push the next version. CI runs release tests/lint, verifies the signing fingerprint, and publishes `HandOff.apk`. If that exact revision's release already exists without an APK, rerunning adds the signed APK without replacing existing assets. Other changes require a version bump.

The old CI debug APK used a different signing key. It cannot be updated in place using the permanent release key. Moving from that debug build requires one manual uninstall/install and pairing again. Once on the signed channel, subsequent updates retain settings and pairing. HandOff does not silently uninstall or delete user data.

## Publishing

`Framework tests` builds and exercises the Windows installer on every tested branch. Only main pushes with all platform gates green publish GitHub prereleases. Android release signing is optional until its permanent identity is configured; without it, only the Windows installer is published and CI explains the missing setup. Debug APKs remain testing artifacts, never update assets.

Bump `host/version.py`, Android `versionName`, and Android `versionCode` for each update. Tags use `v1.0.0-rcN` or `v1.0.0`; the updater orders these numerically. Released assets are never overwritten. Both apps must be updated when wire protocol capabilities change. No background installation occurs.

Verification: CI tests installer first-install/reinstall/launch/uninstall; release ordering, malformed metadata, corrupted download rejection and version consistency; Android compilation, lint and existing emulator connection tests. Real Android installer confirmation and debug-to-release migration still need device testing.

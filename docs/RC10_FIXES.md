# RC10 updater reliability

RC10 removes GitHub REST API rate limits from the normal update path.

- Windows and Android read a tiny, CDN-cached `update-channel/update.json` file first.
- The Releases API remains a compatibility fallback only.
- The publishing workflow generates the channel from the exact tested installer and signed APK.
- Both clients still require an HTTPS GitHub release URL, bounded file size, and matching SHA-256 digest.
- Android additionally verifies the APK package, higher version code, and installed signing identity before installation.

RC9 and older builds still use the rate-limited API, so a user whose shared network quota is already exhausted may need to install RC10 directly once. Every later release can be discovered through the update channel.

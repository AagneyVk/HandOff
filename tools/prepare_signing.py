"""Decode provided signing material privately; never generate a replacement identity."""
import base64
import os
from pathlib import Path
import sys

mode = sys.argv[1]
if mode == 'android':
    required = ['ANDROID_KEYSTORE_B64', 'ANDROID_KEYSTORE_PASSWORD', 'ANDROID_KEY_ALIAS', 'ANDROID_KEY_PASSWORD', 'ANDROID_SIGNING_SHA256']
    path = Path(os.environ['RUNNER_TEMP']) / 'handoff-release.jks'
else:
    required = ['WINDOWS_CERT_PFX_B64', 'WINDOWS_CERT_PASSWORD']
    path = Path(os.environ['RUNNER_TEMP']) / 'handoff-release.pfx'
missing = [name for name in required if not os.environ.get(name)]
if missing: raise SystemExit('Signing is not configured: ' + ', '.join(missing))
data = base64.b64decode(os.environ[required[0]], validate=True)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'wb') as file: file.write(data)
if mode == 'android':
    with open(os.environ['GITHUB_ENV'], 'a') as file: file.write(f'ANDROID_KEYSTORE_PATH={path}\n')

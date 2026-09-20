import os
from pathlib import Path
import re
import subprocess

sdk = Path(os.environ['ANDROID_HOME'])
exe = sdk / 'build-tools' / '35.0.0' / ('apksigner.bat' if os.name == 'nt' else 'apksigner')
result = subprocess.run([str(exe), 'verify', '--verbose', '--print-certs', 'android/app/build/outputs/apk/release/app-release.apk'], check=True, capture_output=True, text=True)
match = re.search(r'Signer #1 certificate SHA-256 digest: ([0-9a-fA-F]+)', result.stdout)
expected = os.environ['ANDROID_SIGNING_SHA256'].replace(':', '').lower()
if not match or match.group(1).lower() != expected: raise SystemExit('Unexpected Android signing certificate')
print('APK signature and configured publisher fingerprint verified')

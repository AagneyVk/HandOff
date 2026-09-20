"""Run once on your own computer with Java keytool and authenticated GitHub CLI.
The private key stays in ~/.handoff-signing and GitHub Actions secrets, never Git.
Existing key material is reused; this command never rotates it.
"""
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

repo = 'AagneyVk/HandOff'
subprocess.run(['gh', 'auth', 'status'], check=True)
folder = Path.home() / '.handoff-signing'
folder.mkdir(mode=0o700, exist_ok=True)
key = folder / 'release.jks'
settings = folder / 'credentials.json'
if key.exists() != settings.exists(): raise SystemExit('Incomplete signing backup; recover it before proceeding.')
if not key.exists():
    configured = subprocess.run(['gh', 'secret', 'list', '--repo', repo, '--json', 'name'], check=True, capture_output=True, text=True)
    if any(item['name'] == 'ANDROID_KEYSTORE_B64' for item in json.loads(configured.stdout)):
        raise SystemExit('A release key is already configured in GitHub. Restore your original local key backup; do not replace it.')
    credentials = {'password': secrets.token_urlsafe(32), 'alias': 'handoff'}
    fd = os.open(settings, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file: json.dump(credentials, file)
    env = dict(os.environ, HANDOFF_SIGNING_PASSWORD=credentials['password'])
    subprocess.run(['keytool', '-genkeypair', '-keystore', str(key), '-storetype', 'JKS',
        '-alias', credentials['alias'], '-keyalg', 'RSA', '-keysize', '3072', '-validity', '10000',
        '-dname', 'CN=HandOff', '-storepass:env', 'HANDOFF_SIGNING_PASSWORD',
        '-keypass:env', 'HANDOFF_SIGNING_PASSWORD'], env=env, check=True)
credentials = json.loads(settings.read_text())
env = dict(os.environ, HANDOFF_SIGNING_PASSWORD=credentials['password'])
result = subprocess.run(['keytool', '-exportcert', '-keystore', str(key), '-alias', credentials['alias'],
    '-storepass:env', 'HANDOFF_SIGNING_PASSWORD'], env=env, check=True, capture_output=True)
import hashlib
values = {'ANDROID_KEYSTORE_B64': base64.b64encode(key.read_bytes()).decode(),
    'ANDROID_KEYSTORE_PASSWORD': credentials['password'], 'ANDROID_KEY_ALIAS': credentials['alias'],
    'ANDROID_KEY_PASSWORD': credentials['password'], 'ANDROID_SIGNING_SHA256': hashlib.sha256(result.stdout).hexdigest()}
for name, value in values.items():
    subprocess.run(['gh', 'secret', 'set', name, '--repo', repo], input=value, text=True, check=True)
print('Signing configured. Back up the private .handoff-signing folder securely. Do not commit or share it.')

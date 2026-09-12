"""Pinned TLS identity and revocable bearer credentials; no secrets in logs."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import ssl
import threading
import time
from urllib.parse import urlencode

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def atomic_private(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Identity:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.pem = self.directory / 'identity.pem'
        if not self.pem.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            now = datetime.now(timezone.utc)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'HandOff local host')])
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
                    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                    .sign(key, hashes.SHA256()))
            atomic_private(self.pem, (key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()) + cert.public_bytes(serialization.Encoding.PEM)).decode())
        cert = x509.load_pem_x509_certificate(self.pem.read_bytes())
        self.fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(self.pem)


class TrustStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'devices.json'
        self.lock = threading.RLock()
        self.devices = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.invite = None
        self.expires = 0

    def invitation(self, host, port, fingerprint):
        with self.lock:
            self.invite = secrets.token_urlsafe(32)
            self.expires = time.monotonic() + 300
            return 'handoff://pair?' + urlencode(dict(host=host, port=port, pin=fingerprint, code=self.invite))

    def pair(self, code, name):
        with self.lock:
            if not isinstance(code, str) or not self.invite or time.monotonic() > self.expires or not hmac.compare_digest(code, self.invite):
                raise ValueError('Pairing link expired or already used. Generate a new link on your computer.')
            if len(self.devices) >= 16:
                raise ValueError('Remove a paired device before pairing another.')
            device, token = secrets.token_hex(16), secrets.token_urlsafe(32)
            self.devices[device] = dict(name=str(name)[:80], digest=hashlib.sha256(token.encode()).hexdigest())
            self._save()
            self.invite = None
            return device, token

    def authenticate(self, device, token):
        with self.lock:
            record = self.devices.get(device) if isinstance(device, str) else None
            return bool(record and isinstance(token, str) and hmac.compare_digest(record['digest'], hashlib.sha256(token.encode()).hexdigest()))

    def trusted(self, device):
        with self.lock:
            return device in self.devices

    def revoke_all(self):
        with self.lock:
            self.devices.clear()
            self.invite = None
            self._save()

    def _save(self):
        atomic_private(self.path, json.dumps(self.devices))

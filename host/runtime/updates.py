"""Explicit release updates. HTTPS and GitHub's asset digest protect the download."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

from host.version import VERSION
API = 'https://api.github.com/repos/AagneyVk/HandOff/releases?per_page=30'
CHANNEL = 'https://raw.githubusercontent.com/AagneyVk/HandOff/update-channel/update.json'
PREFIX = 'https://github.com/AagneyVk/HandOff/releases/download/'
MAX_SIZE = 400 * 1024 * 1024
METADATA_LIMIT = 1024 * 1024


def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?', value)
    if not match: raise ValueError('Unsupported release version')
    major, minor, patch, rc = match.groups()
    return int(major), int(minor), int(patch), int(rc) if rc else 1000000


class HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'): raise ValueError('Insecure download redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'HandOff-updater', 'Accept': 'application/vnd.github+json'})
    return urllib.request.build_opener(HttpsRedirect()).open(req, timeout=30)


def select_release(releases, current=VERSION):
    candidates = []
    for release in releases:
        if release.get('draft'): continue
        try: newer = version(release['tag_name']) > version(current)
        except (ValueError, KeyError, TypeError): continue
        if not newer: continue
        for asset in release.get('assets', []):
            if asset.get('name') != 'HandOff-Setup.exe': continue
            digest = asset.get('digest', '')
            url = asset.get('browser_download_url', '')
            size = asset.get('size', 0)
            if (not re.fullmatch(r'sha256:[0-9a-f]{64}', digest or '') or not url.startswith(PREFIX)
                    or type(size) is not int or not 0 < size <= MAX_SIZE): continue
            candidates.append(dict(tag=release['tag_name'], url=url, digest=digest[7:], size=size))
    return max(candidates, key=lambda r: version(r['tag'])) if candidates else None


def select_channel(manifest, current=VERSION):
    if not isinstance(manifest, dict) or manifest.get('schema') != 1:
        raise ValueError('Unsupported update channel metadata')
    tag = manifest.get('tag')
    try: newer = version(tag) > version(current)
    except (ValueError, TypeError): raise ValueError('Invalid update channel version') from None
    asset = manifest.get('assets', {}).get('windows')
    if not isinstance(asset, dict):
        raise ValueError('Windows update is missing from the update channel')
    digest = asset.get('sha256', '')
    url = asset.get('url', '')
    size = asset.get('size', 0)
    if (asset.get('name') != 'HandOff-Setup.exe'
            or not re.fullmatch(r'[0-9a-f]{64}', digest or '')
            or not isinstance(url, str) or not url.startswith(PREFIX)
            or type(size) is not int or not 0 < size <= MAX_SIZE):
        raise ValueError('Invalid Windows update channel metadata')
    return dict(tag=tag, url=url, digest=digest, size=size) if newer else None


def read_json(url):
    with open_url(url) as response:
        data = response.read(METADATA_LIMIT + 1)
    if len(data) > METADATA_LIMIT: raise ValueError('Release metadata too large')
    return json.loads(data)


def check():
    """Use the CDN-backed channel first; REST API is only a compatibility fallback."""
    try:
        return select_channel(read_json(CHANNEL))
    except Exception as channel_error:
        try:
            return select_release(read_json(API))
        except Exception as api_error:
            raise RuntimeError(
                'Update services are temporarily unavailable. '
                f'Channel: {channel_error}; fallback: {api_error}'
            ) from api_error


def download(release, directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'HandOff-Setup.exe'
    partial = target.with_suffix('.partial')
    digest = hashlib.sha256(); total = 0
    try:
        with open_url(release['url']) as response, partial.open('wb') as output:
            while chunk := response.read(65536):
                total += len(chunk)
                if total > release['size'] or total > MAX_SIZE: raise ValueError('Installer size mismatch')
                digest.update(chunk); output.write(chunk)
        if total != release['size'] or digest.hexdigest() != release['digest']:
            raise ValueError('Installer verification failed; nothing was installed')
        os.replace(partial, target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def install(path):
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        raise ValueError('Install updates from the installed Windows app. Source checkouts use git pull.')
    subprocess.Popen([str(path), '/SP-', '/CLOSEAPPLICATIONS'], close_fds=True)

import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from host.runtime import updates


class UpdateTests(unittest.TestCase):
    def asset(self, data=b'installer'):
        return dict(name='HandOff-Setup.exe', size=len(data), digest='sha256:' + hashlib.sha256(data).hexdigest(),
                    browser_download_url=updates.PREFIX+'v1.0.0/HandOff-Setup.exe')

    def test_release_order_and_missing_or_untrusted_assets(self):
        releases = [dict(tag_name='v1.0.0-rc8', assets=[self.asset()]), dict(tag_name='v1.0.0', assets=[self.asset()])]
        self.assertEqual(updates.select_release(releases, '1.0.0-rc6')['tag'], 'v1.0.0')
        self.assertIsNone(updates.select_release(releases, '1.0.0'))
        self.assertIsNone(updates.select_release([dict(tag_name='v9.0.0', assets=[dict(self.asset(), digest=None)])]))
        self.assertIsNone(updates.select_release([dict(tag_name='v9.0.0', assets=[dict(self.asset(), browser_download_url='https://example.com/evil.exe')])]))
        self.assertIsNone(updates.select_release([dict(tag_name='v9.0.0', draft=True, assets=[self.asset()])]))

    def test_rate_limit_resistant_update_channel(self):
        asset = self.asset()
        manifest = dict(schema=1, tag='v1.0.0-rc10', assets=dict(windows=dict(
            name=asset['name'], size=asset['size'], sha256=asset['digest'][7:], url=asset['browser_download_url']
        )))
        self.assertEqual(updates.select_channel(manifest, '1.0.0-rc9')['tag'], 'v1.0.0-rc10')
        self.assertIsNone(updates.select_channel(manifest, '1.0.0-rc10'))
        with self.assertRaises(ValueError):
            updates.select_channel(dict(manifest, schema=2), '1.0.0-rc9')
        manifest['assets']['windows']['url'] = 'https://example.com/HandOff-Setup.exe'
        with self.assertRaises(ValueError):
            updates.select_channel(manifest, '1.0.0-rc9')

    def test_check_falls_back_to_api_when_channel_is_unavailable(self):
        releases = [dict(tag_name='v9.0.0', assets=[self.asset()])]
        with patch.object(updates, 'read_json', side_effect=[OSError('CDN unavailable'), releases]) as read:
            self.assertEqual(updates.check()['tag'], 'v9.0.0')
        self.assertEqual([call.args[0] for call in read.call_args_list], [updates.CHANNEL, updates.API])

    def test_download_checks_hash_and_cleans_partial(self):
        data = b'installer'
        release = updates.select_release([dict(tag_name='v9.0.0', assets=[self.asset(data)])])
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(updates, 'open_url', return_value=io.BytesIO(b'corrupted')):
                with self.assertRaises(ValueError): updates.download(release, folder)
            self.assertEqual(list(Path(folder).iterdir()), [])
            with patch.object(updates, 'open_url', return_value=io.BytesIO(data)):
                self.assertEqual(updates.download(release, folder).read_bytes(), data)

    def test_version_files_agree(self):
        from host.version import VERSION
        self.assertIn('versionName = "' + VERSION + '"', Path('android/app/build.gradle.kts').read_text())

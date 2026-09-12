import unittest
from tools.validate_session import validate

class EvidenceTests(unittest.TestCase):
    def report(self):
        return dict(schema=1, source_revision='a' * 40, device_kind='physical', codec='h264', encoder='h264_nvenc', duration_seconds=65,
                    decoded_frames=1200, average_fps=18, audio_chunks_received=1500, errors=0)
    def test_accepts_report_for_exact_revision(self):
        self.assertEqual(validate(self.report(), 'a' * 40), [])
    def test_rejects_emulator_software_wrong_revision_and_missing_evidence(self):
        for field, value in [('device_kind', 'emulator'), ('encoder', 'libx264'), ('source_revision', 'b' * 40),
                             ('audio_chunks_received', 0), ('errors', 1), ('duration_seconds', float('nan')), ('average_fps', True)]:
            with self.subTest(field=field):
                report = self.report(); report[field] = value
                self.assertTrue(validate(report, 'a' * 40))

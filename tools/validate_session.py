"""Check exported session evidence. This does not certify visual/audio quality."""
import argparse
import json
import math
from pathlib import Path


def validate(report, revision):
    failures = []
    def check(ok, message):
        if not ok: failures.append(message)
    def number(key):
        value = report.get(key)
        return value if type(value) in (int, float) and math.isfinite(value) else -1
    check(report.get('schema') == 1, 'Unsupported report schema')
    check(report.get('source_revision') == revision, 'Report is for a different source revision')
    check(report.get('device_kind') == 'physical', 'Physical Android run required')
    check(report.get('codec') == 'h264', 'H.264 run required')
    check(report.get('encoder') in ('h264_nvenc', 'h264_qsv', 'h264_amf'), 'Hardware encoder run required')
    check(number('duration_seconds') >= 60, 'Run must last at least 60 seconds')
    check(number('decoded_frames') >= 600, 'At least 600 decoded frames required')
    check(number('average_fps') >= 10, 'Average decode rate must be at least 10 fps')
    check(number('audio_chunks_received') >= 100, 'Audio reception evidence required')
    check(number('errors') == 0, 'Session contains errors')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('report'); parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text())
    failures = validate(report, args.revision)
    if failures: raise SystemExit('\n'.join(failures))
    print('Session evidence passes automated checks. Confirm visual quality, audible sound and input manually.')

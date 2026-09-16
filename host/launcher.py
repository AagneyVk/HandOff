import multiprocessing
import os
import sys
import traceback
from pathlib import Path


def _crash_log_path():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'HandOff'
    base.mkdir(parents=True, exist_ok=True)
    return base / 'startup-error.log'


if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        from host.app import main
        main()
    except Exception:
        try:
            path = _crash_log_path()
            path.write_text(traceback.format_exc(), encoding='utf-8')
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"HandOff could not start.\n\nDiagnostic details were saved to:\n{path}",
                    "HandOff startup error",
                    0x10,
                )
        finally:
            raise

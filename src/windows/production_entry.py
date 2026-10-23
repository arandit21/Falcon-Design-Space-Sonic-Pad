"""Windowless production entry point for the verified native transport."""
import os
import pathlib
import runpy
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ['PYTHONUTF8'] = '1'
os.environ['QML_DISABLE_DISK_CACHE'] = '1'
original_popen = subprocess.Popen


class HiddenProcess(original_popen):
    def __init__(self, *args, **kwargs):
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        super().__init__(*args, **kwargs)


subprocess.Popen = HiddenProcess
import sys
sys.path.insert(0, str(ROOT))
from connection_settings import state_dir
if not (state_dir(ROOT) / '.ssh' / 'falcon_sonic_rsa').is_file():
    raise RuntimeError('Не найден ключ подключения Sonic Pad. Повтори установку патча.')

# Existing authentication is noninteractive in the permanent launcher.
# USB, camera and serial code is shared with the verified installation.
os.environ['FALCON_PERMANENT_LAUNCH'] = '1'
runpy.run_path(str(ROOT / 'run_native.py'), run_name='__main__')

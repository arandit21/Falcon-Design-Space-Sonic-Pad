"""SSH photo delivery to the existing FDS Qt camera adapter."""
import base64
import hashlib
import json
import subprocess
import threading

CAMERA_QT_HASHES = {
    'Qt5Gui.dll': '5e7d2d41b8b92a880e83b8cc0ca173f5da61218604186196787ee1600956be1e',
    'Qt5Multimedia.dll': '1a59ae2a9ff768ad6bfb888fe3dd2544e238f0b28da83cf375ebd803ce713dc4',
}


def verify_camera_runtime(folder):
    for name, expected in CAMERA_QT_HASHES.items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Unsupported camera Qt DLL: ' + name)


class CameraBridge:
    def __init__(self, options, host, script):
        self.options = list(options)
        self.host = host
        self.script = script
        self.lock = threading.Lock()

    def request(self, operation):
        result = subprocess.run(
            ['ssh'] + self.options + ['-oBatchMode=yes', '-oConnectTimeout=5', self.host,
             'python3 /mnt/UDISK/falcon_native_usb/sonic_camera_photo.py ' + operation],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35)
        if result.returncode:
            raise RuntimeError('Camera SSH failed: ' + result.stderr.decode(errors='replace')[-500:])
        data = json.loads(result.stdout.decode('utf8'))
        if not data.get('ok'):
            raise RuntimeError(data.get('error', 'Camera request failed'))
        return data

    def capture(self, capture_id):
        if not self.lock.acquire(blocking=False):
            self.script.exports_sync.camera_frame(capture_id, '', 'Предыдущий снимок ещё обрабатывается')
            return
        try:
            data = self.request('photo')
            jpeg = base64.b64decode(data['jpeg'], validate=True)
            if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9') or len(jpeg) > 12000000:
                raise RuntimeError('Invalid photo from Sonic Pad')
            self.script.exports_sync.camera_frame(capture_id, jpeg.hex(), None)
        except Exception as error:
            print('Camera photo failed: ' + str(error), flush=True)
            try:
                self.script.exports_sync.camera_frame(capture_id, '', str(error))
            except Exception:
                pass  # FDS may have been closed while a photo was being captured.
        finally:
            self.lock.release()

    def on_message(self, message, data):
        print(json.dumps(message, ensure_ascii=False), flush=True)
        event = message.get('payload', {})
        if event.get('event') == 'remote_camera_photo_requested':
            threading.Thread(target=self.capture, args=(event['id'],), daemon=True).start()

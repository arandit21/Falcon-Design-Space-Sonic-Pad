#!/usr/bin/env python3
"""One real USB camera photo; no serial or machine-control operations."""
import base64
import fcntl
import glob
import json
import os
import pathlib
import subprocess
import sys


def camera_device():
    found = []
    for name in glob.glob('/sys/class/video4linux/video*'):
        item = pathlib.Path(name)
        if (item / 'name').read_text().strip() != 'Creality Falcon Camera':
            continue
        device = item.resolve()
        usb = next((p for p in [device] + list(device.parents) if (p / 'idVendor').exists()), None)
        if usb and (usb / 'idVendor').read_text().strip() == '1bcf' and (usb / 'idProduct').read_text().strip() == '0b19':
            found.append('/dev/' + item.name)
    if len(found) != 1:
        raise RuntimeError('Expected one physical Creality Falcon Camera, found {}'.format(len(found)))
    return found[0]


def photo():
    device = camera_device()
    # Keep existing Sonic Pad services and their startup configuration intact.
    with open('/tmp/falcon_native_camera_photo.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        service = '/etc/init.d/rtsp_server'
        # Restore only a service that was running before this photo.
        running = False
        for comm in glob.glob('/proc/[0-9]*/comm'):
            try:
                if pathlib.Path(comm).read_text().strip() == 'rtsp_demo':
                    running = True
            except OSError:
                pass
        try:
            if running:
                subprocess.run([service, 'stop'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=True)
            result = subprocess.run([
                'ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'v4l2',
                '-input_format', 'mjpeg', '-video_size', '2592x1944', '-i', device,
                '-ss', '0.5', '-frames:v', '1', '-c:v', 'copy', '-f', 'image2pipe', 'pipe:1'
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            image = result.stdout
            if result.returncode or not image.startswith(b'\xff\xd8') or not image.endswith(b'\xff\xd9'):
                raise RuntimeError('USB camera photo failed: ' + result.stderr.decode(errors='replace')[-600:])
            if len(image) > 12000000:
                raise RuntimeError('USB camera photo exceeds the size limit')
            return {'ok': True, 'device': device, 'width': 2592, 'height': 1944, 'jpeg': base64.b64encode(image).decode('ascii')}
        finally:
            if running:
                subprocess.run([service, 'start'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=True)


if __name__ == '__main__':
    try:
        operation = sys.argv[1] if len(sys.argv) > 1 else 'metadata'
        if operation == 'metadata':
            result = {'ok': True, 'device': camera_device(), 'width': 2592, 'height': 1944}
        elif operation == 'photo':
            result = photo()
        else:
            raise RuntimeError('Unsupported camera operation')
    except Exception as error:
        result = {'ok': False, 'error': str(error)}
    print(json.dumps(result))

#!/usr/bin/env python3
# Falcon A1 / Sonic Pad R3 -- information-only diagnostic relay.
# No laser motion, power, settings changes or job commands. No autostart.
import argparse
import errno
import fcntl
import json
import re
import os
import select
import termios
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

EXPECTED_FW = b'[software versions: CV40-MASTER-Release '


def verify_usb_identity(device):
    """Refuse to query a ttyACM node unless its USB parent matches Falcon A1.

    This safeguards Klipper printers attached to the same Sonic Pad. For a
    pseudoterminal used by the offline test harness, no hardware check applies.
    """
    base = os.path.basename(device)
    if not (device.startswith('/dev/ttyACM') and base.startswith('ttyACM')):
        return
    node = os.path.realpath('/sys/class/tty/{}/device'.format(base))
    # cdc_acm interface is `1-X.Y:1.0`, vendor/product live in USB parent.
    usb_parent = os.path.dirname(node)
    with open(os.path.join(usb_parent, 'idVendor')) as f:
        vendor = f.read().strip().lower()
    with open(os.path.join(usb_parent, 'idProduct')) as f:
        product = f.read().strip().lower()
    if (vendor, product) != ('303a', '4001'):
        raise RuntimeError('Refusing serial access: {} is USB {}:{}'.format(device, vendor, product))


def query_identity(device, timeout=4.0):
    """Reproduce the successfully tested original Stage 1 opening sequence.

    Returns raw bytes, retaining all CR/LF, plus timing; never alters GRBL settings.
    A single caller must own this fd during each query.
    """
    verify_usb_identity(device)
    fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = None
    try:
        old = termios.tcgetattr(fd)
        cfg = termios.tcgetattr(fd)
        cfg[0] = 0
        cfg[1] = 0
        cfg[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        cfg[3] = 0
        cfg[4] = termios.B115200
        cfg[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, cfg)
        time.sleep(0.3)
        termios.tcflush(fd, termios.TCIFLUSH)
        sent = os.write(fd, b'$I\n')
        if sent != 3:
            raise OSError('USB short write: {} of 3 bytes'.format(sent))

        data = bytearray()
        begun = time.monotonic()
        while time.monotonic() - begun < timeout and len(data) < 4096:
            left = timeout - (time.monotonic() - begun)
            if left <= 0:
                break
            ready, _, _ = select.select([fd], [], [], min(0.1, left))
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except (BlockingIOError, InterruptedError):
                continue
            if not chunk:
                continue
            data.extend(chunk)
            # Normalize only for end-of-reply recognition, not the raw output.
            lines = bytes(data).replace(b'\r', b'').split(b'\n')
            # Trailing newline is optional; ignore the empty element it adds.
            nonempty = [line.strip() for line in lines if line.strip()]
            if nonempty and (nonempty[-1] == b'ok' or nonempty[-1].startswith(b'error:')):
                break
        return bytes(data), round((time.monotonic() - begun) * 1000)
    finally:
        if old is not None:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, old)
            except OSError:
                pass
        os.close(fd)


def validate_identity(raw):
    if not raw:
        return 'no data from USB serial'
    flat = raw.replace(b'\r', b'')
    lines = [s.strip() for s in flat.split(b'\n') if s.strip()]
    if any(x.startswith(b'error:') for x in lines):
        return 'GRBL responded with error instead of identity: ' + repr(raw[:200])
    if not lines or lines[-1] != b'ok':
        return 'incomplete serial response: no final ok'
    missing = []
    for marker in (b'[VER:', b'[OPT:', EXPECTED_FW, b'ID:'):
        if marker not in raw:
            missing.append(marker.decode('ascii', 'replace'))
    if missing:
        return 'identity missing markers: {}'.format(','.join(missing))
    return None


# GRBL realtime status '?' is a read-only single-byte request. It does not
# change motion, laser power or controller settings.
ALLOWED_STATES = frozenset(('Idle', 'Run', 'Hold', 'Jog', 'Alarm', 'Door', 'Check', 'Home', 'Sleep'))

def query_state(device, timeout=1.5):
    verify_usb_identity(device)
    fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = None
    try:
        old = termios.tcgetattr(fd)
        cfg = termios.tcgetattr(fd)
        cfg[0] = cfg[1] = cfg[3] = 0
        cfg[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        cfg[4] = cfg[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, cfg)
        time.sleep(0.1)
        termios.tcflush(fd, termios.TCIFLUSH)
        if os.write(fd, b'?') != 1:
            raise OSError('short realtime status write')
        data = bytearray()
        started = time.monotonic()
        while time.monotonic() - started < timeout and len(data) < 2048:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    data.extend(os.read(fd, 2048))
                except (BlockingIOError, InterruptedError):
                    continue
                m = re.search(rb'<([A-Za-z]+)(?:[|:>])', bytes(data))
                if m and b'>' in bytes(data)[m.start():]:
                    state = m.group(1).decode('ascii')
                    if state in ALLOWED_STATES:
                        return state, bytes(data)[m.start():bytes(data).find(b'>', m.start())+1]
                    return 'Unknown', bytes(data)[:240]
        return 'Unknown', bytes(data)[:240]
    finally:
        if old is not None:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, old)
            except OSError:
                pass
        os.close(fd)

def identity_fields(raw):
    content = raw.replace(b'\r', b'').decode('ascii', 'replace')
    def find(pattern):
        m = re.search(pattern, content)
        return m.group(1).strip() if m else ''
    return {
        'model': 'Creality Falcon A1',
        'id': find(r'(?m)^ID:([^\n]+)'),
        'firmware': find(r'(?m)^\[software versions: ([^\]]+)\]'),
        'grbl_version': find(r'(?m)^\[VER:([^\]]+)\]'),
        'grbl_options': find(r'(?m)^\[OPT:([^\]]+)\]')
    }


class BridgeHTTP(HTTPServer):
    allow_reuse_address = True
    def __init__(self, addr, handler, device, interval):
        super().__init__(addr, handler)
        self.device = device
        self.interval = interval
        self.last_started = -1e9
        self.count = 0
        self.success = 0
        self.last_error = 'none'
        self.cached_identity = None
        self.cached_when = 0.0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default request lines, but log important events below.
        return

    def reply(self, status, content, content_type='text/plain; charset=utf-8', extra_headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(content)
        except (OSError, BrokenPipeError):
            pass

    def device_readonly(self):
        # Single-thread HTTPServer ensures no overlap between /id and /device.
        # Never claim online from a cached identity alone.
        try:
            verify_usb_identity(self.server.device)
            if not os.path.exists(self.server.device):
                raise OSError('USB serial device not present')
            now = time.monotonic()
            cache = self.server.cached_identity
            if cache is None or now - self.server.cached_when > 1800:
                self.server.last_started = now
                raw, _ = query_identity(self.server.device)
                error = validate_identity(raw)
                if error:
                    raise RuntimeError('identity: ' + error)
                cache = identity_fields(raw)
                self.server.cached_identity = cache
                self.server.cached_when = time.monotonic()
                self.server.success += 1
            state, line = query_state(self.server.device)
            # A controller that doesn't answer '?' is not confirmed online.
            online = state != 'Unknown'
            answer = dict(cache)
            answer.update({
                'schema': 1,
                'bridge': 'Falcon A1 Bridge R4 (read-only)',
                'identified': True,
                'online': online,
                'state': state,
                'identity_age_seconds': round(time.monotonic() - self.server.cached_when, 1),
                'status_response': line.decode('ascii','replace')[:240],
                'read_only': True,
            })
            if online:
                self.server.last_error = 'none'
            else:
                self.server.last_error = 'No validated GRBL status response'
            return self.reply(200, json.dumps(answer, ensure_ascii=True).encode('utf-8'),
                              'application/json; charset=utf-8')
        except Exception as exc:
            self.server.cached_identity = None
            self.server.last_error = '{}: {}'.format(type(exc).__name__, exc)
            answer = {'schema':1, 'identified': False, 'online': False, 'read_only': True,
                      'state':'Unknown', 'error': self.server.last_error}
            return self.reply(503, json.dumps(answer).encode('ascii'),
                              'application/json; charset=utf-8')

    def do_GET(self):
        if self.path == '/device':
            return self.device_readonly()
        if self.path == '/health':
            msg = 'Falcon A1 Bridge R4\nmode=READ_ONLY\nrequests={}\nsuccess={}\nlast_error={}\n'.format(
                self.server.count, self.server.success, self.server.last_error)
            return self.reply(200, msg.encode('utf-8'))
        if self.path != '/id':
            return self.reply(404, b'not found\n')
        now = time.monotonic()
        if now - self.server.last_started < self.server.interval:
            return self.reply(429, b'Too soon: wait before the next identity request\n', extra_headers={'Retry-After': '2'})
        self.server.last_started = now
        self.server.count += 1
        try:
            raw, ms = query_identity(self.server.device)
            error = validate_identity(raw)
            if error:
                self.server.last_error = error
                print('BAD identity {} bytes / {} ms: {} | RAW={!r}'.format(len(raw), ms, error, raw[:180]), flush=True)
                return self.reply(502, ('USB identity error: {}\n'.format(error)).encode('utf-8'))
            self.server.success += 1
            self.server.cached_identity = identity_fields(raw)
            self.server.cached_when = time.monotonic()
            self.server.last_error = 'none'
            print('GOOD identity {} bytes / {} ms'.format(len(raw), ms), flush=True)
            return self.reply(200, raw, 'application/octet-stream')
        except Exception as exc:
            self.server.last_error = '{}: {}'.format(type(exc).__name__, exc)
            print('USB exception: {}'.format(self.server.last_error), flush=True)
            return self.reply(503, ('USB exception: {}\n'.format(self.server.last_error)).encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description='Falcon A1 R4 read-only auto-discovery')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=18765)
    parser.add_argument('--device', default='/dev/ttyACM0')
    parser.add_argument('--interval', type=float, default=2.0)
    args = parser.parse_args()
    if args.interval < 1.0:
        parser.error('--interval must be at least 1.0 second')
    with open('/tmp/falcon_a1_bridge_r3.lock', 'w') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EACCES):
                raise SystemExit('ERROR: Another R3 bridge instance is running')
            raise
        server = BridgeHTTP((args.host, args.port), Handler, args.device, args.interval)
        print('Falcon A1 Bridge R4: http://{}:{}/device'.format(args.host, args.port), flush=True)
        print('READ-ONLY; GET /device, /id and /health only. Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            print('Bridge stopped.', flush=True)
        finally:
            server.server_close()


if __name__ == '__main__':
    main()

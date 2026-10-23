#!/usr/bin/env python3
"""Native serial transport, SSH-forwarded loopback endpoints only.

No G-code generation, translation, synthetic status, or command retries.
The Windows application remains responsible for the device protocol.
"""
import argparse
import array
import fcntl
import glob
import hashlib
import json
import os
import select
import signal
import socket
import socketserver
import termios
import threading
import time


def acquire_bridge_lock(lock):
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    except BlockingIOError:
        pass
    identity = os.fstat(lock.fileno())
    owner = None
    with open('/proc/locks') as stream:
        for line in stream:
            fields = line.split()
            if len(fields) < 6 or fields[1] != 'FLOCK':
                continue
            device = fields[5].split(':')
            if len(device) != 3:
                continue
            if (int(device[0], 16), int(device[1], 16), int(device[2])) == (os.major(identity.st_dev), os.minor(identity.st_dev), identity.st_ino):
                owner = int(fields[4])
                break
    if not owner or owner <= 1:
        raise RuntimeError('USB lock is held; its owner could not be verified')
    with open('/proc/{}/cmdline'.format(owner), 'rb') as stream:
        args = [part.decode('utf8', 'replace') for part in stream.read().split(b'\0') if part]
    scripts = [arg for arg in args[1:] if os.path.basename(arg) in ('bridge_r3.py', 'falcon_a1_bridge_r3.py', 'falcon_a1_bridge_r4.py', 'command_bridge.py')]
    allowed = {'68bebb4f7526237f28cfc568da7a7f79879ba1f75a2ca16ac2635c30d29a9e5b',
               'bedd02fe96aaa438ec15926f9876fe33b777049087768c1907fe8e75686a146f',
               'c62e167d0db0358dfe20ddeed540414588f9ccddb1afdf3b9932126daa2827e8'}
    if len(scripts) != 1:
        raise RuntimeError('USB lock belongs to unrecognized process PID {}; close its old test window first'.format(owner))
    script = scripts[0]
    if not os.path.isabs(script):
        script = os.path.join(os.readlink('/proc/{}/cwd'.format(owner)), script)
    with open(script, 'rb') as stream:
        digest = hashlib.sha256(stream.read()).hexdigest()
    executable = os.path.basename(os.readlink('/proc/{}/exe'.format(owner)))
    if digest not in allowed or not executable.startswith('python'):
        raise RuntimeError('USB lock owner PID {} is not a verified diagnostic Falcon bridge; left untouched'.format(owner))
    if os.path.basename(script) == 'command_bridge.py':
        if digest != 'c62e167d0db0358dfe20ddeed540414588f9ccddb1afdf3b9932126daa2827e8':
            raise RuntimeError('Unknown command bridge; left untouched')
        targets = []
        for fd_path in glob.glob('/proc/{}/fd/*'.format(owner)):
            try: targets.append(os.readlink(fd_path))
            except OSError: pass
        usb = [target for target in targets if target.startswith('/dev/ttyACM')]
        if not usb or not all(target.endswith(' (deleted)') for target in usb):
            raise RuntimeError('Verified old command bridge still has a live USB port; close its old test window first')
    print('Stopping verified old Falcon bridge PID {} ({})'.format(owner, os.path.basename(script)), flush=True)
    os.kill(owner, signal.SIGTERM)
    for attempt in range(50):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            time.sleep(0.1)
    raise RuntimeError('Verified old bridge did not release the USB lock; no force kill performed')


def discover():
    found = []
    for device in sorted(glob.glob('/dev/ttyACM*')):
        parent = os.path.realpath('/sys/class/tty/' + os.path.basename(device) + '/device')
        while parent != '/':
            try:
                with open(parent + '/idVendor') as stream:
                    vendor = int(stream.read().strip(), 16)
                with open(parent + '/idProduct') as stream:
                    product = int(stream.read().strip(), 16)
                if (vendor, product) == (0x303a, 0x4001):
                    metadata = {'device': device, 'vendor': vendor, 'product': product}
                    for key in ('manufacturer', 'product', 'serial'):
                        try:
                            with open(parent + '/' + key) as stream:
                                metadata[key + '_text'] = stream.read().strip()
                        except OSError:
                            metadata[key + '_text'] = ''
                    found.append(metadata)
                break
            except FileNotFoundError:
                parent = os.path.dirname(parent)
    if len(found) != 1:
        raise RuntimeError('Expected exactly one USB 303a:4001; found ' + str(len(found)))
    return found[0]


class Relay:
    def __init__(self, instance=''):
        self.lock = threading.RLock()
        self.fd = None
        self.instance = instance
        self.last_lease = time.monotonic()
        self.stopping = threading.Event()
        self.shutdown_server = None

    def transfer(self, connection):
        metadata = discover()
        with self.lock:
            if self.fd is not None:
                raise RuntimeError('Serial device is already open')
            fd = os.open(metadata['device'], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                saved = termios.tcgetattr(fd)
                cfg = termios.tcgetattr(fd)
                cfg[0] = cfg[1] = cfg[3] = 0
                cfg[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
                cfg[4] = cfg[5] = termios.B115200
                cfg[6][termios.VMIN] = 0
                cfg[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, cfg)
            except BaseException:
                os.close(fd)
                raise
            self.fd = fd
        # A transport acknowledgement, consumed by the hook before QIODevice
        # opens. It never reaches the application's native device protocol.
        toward_usb = bytearray()
        toward_pc = bytearray()
        try:
            connection.sendall(b'{"ok":true}\n')
            connection.setblocking(False)
            while not self.stopping.is_set():
                readers = []
                writers = []
                if len(toward_usb) < 1048576:
                    readers.append(connection)
                if len(toward_pc) < 1048576:
                    readers.append(fd)
                if toward_usb:
                    writers.append(fd)
                if toward_pc:
                    writers.append(connection)
                readable, writable, _ = select.select(readers, writers, [], 1)
                if connection in readable:
                    data = connection.recv(65536)
                    if not data:
                        break
                    toward_usb.extend(data)
                if fd in readable:
                    data = os.read(fd, 65536)
                    if not data:
                        break
                    toward_pc.extend(data)
                if fd in writable:
                    with self.lock:
                        count = os.write(fd, toward_usb)
                    del toward_usb[:count]
                if connection in writable:
                    count = connection.send(toward_pc)
                    del toward_pc[:count]
        finally:
            with self.lock:
                self.fd = None
                try:
                    termios.tcsetattr(fd, termios.TCSANOW, saved)
                except OSError:
                    pass
                os.close(fd)

    def control(self, request):
        op = request['op']
        if op == 'metadata':
            return {'ok': True, 'metadata': discover(), 'instance': self.instance}
        if op in ('lease', 'shutdown'):
            if request.get('instance') != self.instance:
                raise RuntimeError('Relay instance mismatch')
            self.last_lease = time.monotonic()
            if op == 'shutdown':
                self.stopping.set()
                self.shutdown_server()
            return {'ok': True}
        with self.lock:
            if self.fd is None:
                raise RuntimeError('Serial port is not open')
            if op == 'dtr':
                mask = array.array('i', [termios.TIOCM_DTR])
                fcntl.ioctl(self.fd, termios.TIOCMBIS if request['value'] else termios.TIOCMBIC, mask)
            elif op == 'rts':
                mask = array.array('i', [termios.TIOCM_RTS])
                fcntl.ioctl(self.fd, termios.TIOCMBIS if request['value'] else termios.TIOCMBIC, mask)
            elif op == 'clear':
                direction = int(request['direction'])
                termios.tcflush(self.fd, {1: termios.TCIFLUSH, 2: termios.TCOFLUSH, 3: termios.TCIOFLUSH}[direction])
            else:
                raise RuntimeError('Unsupported serial operation')
        return {'ok': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-port', type=int, default=18921)
    parser.add_argument('--control-port', type=int, default=18922)
    parser.add_argument('--instance', default='')
    args = parser.parse_args()
    # The same exclusive lock used by the existing read-only bridge.
    lock = open('/tmp/falcon_a1_bridge_r3.lock', 'a')
    acquire_bridge_lock(lock)
    relay = Relay(args.instance)

    class DataHandler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                relay.transfer(self.request)
            except Exception as error:
                print('Serial session ended: ' + str(error), flush=True)

    class ControlHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(3)
            try:
                line = self.rfile.readline(4097)
                if len(line) > 4096:
                    raise ValueError('Request too large')
                result = relay.control(json.loads(line.decode('utf8')))
            except Exception as error:
                result = {'ok': False, 'error': str(error)}
            self.wfile.write((json.dumps(result) + '\n').encode('utf8'))

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(('127.0.0.1', args.data_port), DataHandler) as data:
        with Server(('127.0.0.1', args.control_port), ControlHandler) as control:
            relay.shutdown_server = lambda: threading.Thread(target=data.shutdown, daemon=True).start()
            def watch_lease():
                while not relay.stopping.wait(1):
                    if relay.instance and time.monotonic() - relay.last_lease > 20:
                        relay.stopping.set()
                        relay.shutdown_server()
            threading.Thread(target=watch_lease, daemon=True).start()
            thread = threading.Thread(target=control.serve_forever, daemon=True)
            thread.start()
            print('Native serial relay ready; SSH forwarding required', flush=True)
            data.serve_forever()
            relay.stopping.set()
            control.shutdown()


if __name__ == '__main__':
    main()

"""Candidate native USB transport. Original EXE and QML are unchanged.

Camera photos use a separate adapter; the serial transport is unchanged.
"""
import hashlib
import datetime
import json
import os
import pathlib
import shlex
import socket
import subprocess
import sys
import time
import threading
import traceback
import uuid
import shutil
from camera_bridge import CameraBridge, verify_camera_runtime

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'dependencies'))
import frida

EXE = pathlib.Path(r'C:\Program Files\Falcon Design Space\FalconDesignSpace.exe')
EXPECTED = '9ec27ec0c06814ba261706552df0a473b8dbb239bbdde2e37b8f6ab303b53f99'
SSH_OPTIONS = ['-oHostKeyAlgorithms=+ssh-rsa', '-oPubkeyAcceptedAlgorithms=ssh-rsa', '-oMACs=+hmac-sha1']
PAD = 'root@192.168.1.36'


def request(port, operation):
    with socket.create_connection(('127.0.0.1', port), timeout=2) as connection:
        connection.sendall((json.dumps(operation) + '\n').encode('utf8'))
        with connection.makefile('rb') as stream:
            result = json.loads(stream.readline(8192).decode('utf8'))
    if not result.get('ok'):
        raise RuntimeError(result.get('error', 'Remote operation failed'))
    return result


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def main():
    if hashlib.sha256(EXE.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError('Unsupported Falcon Design Space EXE; original installation was not changed')
    # Never attach to or replace a process the user already started.
    if any(p.name.lower() == 'falcondesignspace.exe' for p in frida.get_local_device().enumerate_processes()):
        raise RuntimeError('Close Falcon Design Space before starting this candidate')
    build = json.loads((ROOT / 'build.json').read_text(encoding='utf8'))
    for name, expected in build['qt_dll_sha256'].items():
        if hashlib.sha256((EXE.parent / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Unsupported Qt DLL: ' + name)
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    copied = subprocess.run(['robocopy.exe', str(EXE.parent), str(runtime), '/E', '/R:0', '/W:0', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/XD', 'log', 'repository', '/XF', 'FalconDesignSpace.exe', '*.bak', 'maintenancetool*', 'vc_redist*', 'installer*'], stdout=subprocess.DEVNULL)
    if copied.returncode > 7:
        raise RuntimeError('Could not prepare the local application runtime')
    local_exe = runtime / 'FalconDesignSpace.exe'
    shutil.copy2(EXE, local_exe)
    if hashlib.sha256(local_exe.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError('Local EXE does not match the unchanged original')
    print('NATIVE USB: original application protocol; Sonic Pad camera photos supported.', flush=True)
    print('Preparing Sonic Pad; enter its password when SSH asks.', flush=True)
    key_dir = ROOT / '.ssh'
    key_dir.mkdir(exist_ok=True)
    key = key_dir / 'falcon_sonic_rsa'
    if not key.exists():
        subprocess.run(['ssh-keygen', '-t', 'rsa', '-b', '3072', '-m', 'PEM', '-N', '', '-C', 'falcon-native-usb', '-f', str(key)], check=True)
    account = os.environ.get('USERDOMAIN', '') + '\\' + os.environ['USERNAME']
    subprocess.run(['icacls', str(key), '/inheritance:r', '/grant:r', account + ':(R)'], check=True, stdout=subprocess.DEVNULL)
    options = SSH_OPTIONS + ['-i', str(key), '-oIdentitiesOnly=yes']
    public = (key_dir / 'falcon_sonic_rsa.pub').read_text(encoding='ascii').strip()
    quoted = shlex.quote(public)
    setup = 'set -e; umask 077; TASK_KEY_DIR="$(cd ~ && pwd)/.ssh"; mkdir -p "$TASK_KEY_DIR" /mnt/UDISK/falcon_native_usb; touch "$TASK_KEY_DIR/authorized_keys"; grep -qxF ' + quoted + ' "$TASK_KEY_DIR/authorized_keys" || printf \'\\n%s\\n\' ' + quoted + ' >> "$TASK_KEY_DIR/authorized_keys"; chmod 700 "$TASK_KEY_DIR"; chmod 600 "$TASK_KEY_DIR/authorized_keys"; if [ -d /etc/dropbear ]; then touch /etc/dropbear/authorized_keys; grep -qxF ' + quoted + " /etc/dropbear/authorized_keys || printf '\\n%s\\n' " + quoted + ' >> /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys; fi'
    subprocess.run(['ssh'] + options + [PAD, setup], check=True)
    auth = subprocess.run(['ssh'] + options + ['-oBatchMode=yes', '-oConnectTimeout=5', PAD, 'true'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if auth.returncode:
        raise RuntimeError('Sonic Pad still rejected the installed SSH key: ' + auth.stderr.strip())
    print('SSH key login verified; further password prompts are not required.', flush=True)
    subprocess.run(['scp', '-O'] + options + [str(ROOT / 'sonic_serial_relay.py'), str(ROOT / 'sonic_native.sh'), PAD + ':/mnt/UDISK/falcon_native_usb/'], check=True)
    subprocess.run(['scp', '-O'] + options + [str(ROOT / 'sonic_camera_photo.py'), PAD + ':/mnt/UDISK/falcon_native_usb/'], check=True)
    data_port, control_port = free_port(), free_port()
    while data_port == control_port:
        control_port = free_port()
    instance = uuid.uuid4().hex
    ssh = subprocess.Popen(['ssh'] + options + ['-oExitOnForwardFailure=yes', '-oServerAliveInterval=5', '-oServerAliveCountMax=3', '-L', '127.0.0.1:{}:127.0.0.1:18921'.format(data_port), '-L', '127.0.0.1:{}:127.0.0.1:18922'.format(control_port), PAD, 'sh /mnt/UDISK/falcon_native_usb/sonic_native.sh ' + instance], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf8', errors='replace', bufsize=1)
    def show_ssh_output():
        for chunk in iter(lambda: ssh.stdout.read(1), ''):
            print(chunk, end='', flush=True)
    ssh_reader = threading.Thread(target=show_ssh_output, daemon=True)
    ssh_reader.start()
    pid = None
    session = None
    try:
        print('Waiting for the real USB identity. If SSH asks for a password, enter it in this window.', flush=True)
        deadline = time.monotonic() + 180
        last_error = ''
        while time.monotonic() < deadline:
            if ssh.poll() is not None:
                ssh_reader.join(timeout=2)
                raise RuntimeError('SSH/relay ended with code ' + str(ssh.returncode) + '; see the preceding SSH output')
            try:
                result = request(control_port, {'op': 'metadata'})
                if result.get('instance') != instance:
                    raise RuntimeError('A relay from another run is still active')
                metadata = result['metadata']
                break
            except (OSError, ValueError, RuntimeError) as error:
                last_error = str(error)
                time.sleep(1)
        else:
            raise RuntimeError('USB/SSH startup timed out: ' + last_error)
        if (metadata['vendor'], metadata['product']) != (0x303a, 0x4001):
            raise RuntimeError('Unexpected USB identity')
        print('Physical USB: ' + json.dumps(metadata, ensure_ascii=False), flush=True)
        device = frida.get_local_device()
        pid = device.spawn([str(local_exe)], cwd=str(runtime))
        print('Spawned original FDS PID ' + str(pid), flush=True)
        session = device.attach(pid)
        def detached(reason, crash):
            print('FDS detached: ' + str(reason), flush=True)
            if crash:
                print('FDS crash: ' + str(crash.report), flush=True)
        session.on('detached', detached)
        script = session.create_script((ROOT / 'serial_tcp_agent.js').read_text(encoding='utf8'))
        script.on('message', lambda message, data: print(json.dumps(message, ensure_ascii=False), flush=True))
        script.load()
        script.exports_sync.configure({'host': '127.0.0.1', 'port': data_port, 'controlPort': control_port, 'metadata': metadata})
        camera_script = None
        try:
            verify_camera_runtime(runtime)
            camera_script = session.create_script((ROOT / 'camera_agent.js').read_text(encoding='utf8'))
            camera_bridge = CameraBridge(options, PAD, camera_script)
            camera_script.on('message', camera_bridge.on_message)
            camera_script.load()
            camera_metadata = camera_bridge.request('metadata')
            camera_script.exports_sync.camera_configure(True)
            print('Physical camera: ' + json.dumps(camera_metadata, ensure_ascii=False), flush=True)
            print('Camera: select Creality Falcon Camera (Sonic Pad), then use Photo.', flush=True)
        except Exception as error:
            print('Camera unavailable: ' + str(error), flush=True)
        request(control_port, {'op': 'lease', 'instance': instance})
        device.resume(pid)
        print('Original Falcon Design Space started. Select the USB device normally.', flush=True)
        last_lease = 0
        while not session.is_detached:
            if ssh.poll() is not None:
                raise RuntimeError('SSH tunnel disconnected. Close the application; no command is retried.')
            if time.monotonic() - last_lease > 3:
                request(control_port, {'op': 'lease', 'instance': instance})
                last_lease = time.monotonic()
            time.sleep(0.25)
    finally:
        if session and not session.is_detached:
            # The native process must not outlive removal of its transport hooks.
            if pid is not None:
                try:
                    frida.get_local_device().kill(pid)
                except frida.ProcessNotFoundError:
                    pass
            session.detach()
        if ssh.poll() is None:
            try:
                request(control_port, {'op': 'shutdown', 'instance': instance})
                ssh.wait(timeout=10)
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
                ssh.terminate()
                ssh.wait(timeout=10)


if __name__ == '__main__':
    log_dir = ROOT / 'results' / datetime.datetime.now().strftime('run_%Y%m%d_%H%M%S_%f')
    log_dir.mkdir(parents=True)
    log = (log_dir / 'console.log').open('w', encoding='utf8', buffering=1)

    class Tee:
        def __init__(self, stream):
            self.stream = stream

        def write(self, text):
            self.stream.write(text)
            log.write(text)

        def flush(self):
            self.stream.flush()
            log.flush()

    sys.stdout = Tee(sys.stdout)
    sys.stderr = Tee(sys.stderr)
    print('Run log: ' + str(log_dir / 'console.log'), flush=True)
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print('Native candidate stopped: ' + str(error), file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

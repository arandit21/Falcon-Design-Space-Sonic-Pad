#!/usr/bin/env python3
"""Manage only the package-owned read-only R4 process; no machine commands."""
import glob,hashlib,os,pathlib,signal,subprocess,sys,time
BRIDGE=pathlib.Path('/etc/falcon_a1/bridge_r3.py')
PIDFILE=pathlib.Path('/tmp/falcon_sonic_pad_r4.pid')
DIGEST='bedd02fe96aaa438ec15926f9876fe33b777049087768c1907fe8e75686a146f'
def owned(pid):
    try:
        command=pathlib.Path('/proc/{}/cmdline'.format(pid)).read_bytes().split(b'\0')
        return str(BRIDGE).encode() in command and pathlib.Path('/proc/{}/stat'.format(pid)).read_text().split()[2]!='Z'
    except (OSError,IndexError):return False
def current():
    try:
        pid=int(PIDFILE.read_text());return pid if pid>1 and owned(pid) else None
    except (OSError,ValueError):return None
def device():
    found=[]
    for item in sorted(glob.glob('/sys/class/tty/ttyACM*')):
        node=(pathlib.Path(item)/'device').resolve()
        for parent in [node]+list(node.parents):
            try:
                if (parent/'idVendor').read_text().strip()=='303a' and (parent/'idProduct').read_text().strip()=='4001':
                    found.append('/dev/'+pathlib.Path(item).name);break
            except OSError:pass
    if len(found)>1:raise RuntimeError('More than one Falcon A1 attached; connect a single machine.')
    return found[0] if found else '/dev/ttyACM0'
def stop():
    pid=current()
    if not pid:
        print('Managed R4 is not running; other processes left untouched.');return
    if hashlib.sha256(BRIDGE.read_bytes()).hexdigest()!=DIGEST:raise RuntimeError('Bridge file changed; process left untouched.')
    os.kill(pid,signal.SIGTERM)
    for _ in range(50):
        if not owned(pid):
            PIDFILE.unlink();print('Managed R4 stopped.');return
        time.sleep(.1)
    raise RuntimeError('Managed R4 did not stop; no force kill performed.')
def start():
    if current():print('Managed R4 already running.');return
    if hashlib.sha256(BRIDGE.read_bytes()).hexdigest()!=DIGEST:raise RuntimeError('Unexpected R4 file.')
    with open('/tmp/falcon_sonic_pad_r4.log','ab') as log:
        child=subprocess.Popen([sys.executable,'-u',str(BRIDGE),'--host','127.0.0.1','--device',device()],stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,start_new_session=True)
    PIDFILE.write_text(str(child.pid));time.sleep(.5)
    if child.poll() is not None:
        PIDFILE.unlink();raise RuntimeError('R4 failed; see /tmp/falcon_sonic_pad_r4.log (port/USB lock may be occupied).')
    print('Read-only R4 running on 127.0.0.1:18765.')
def main():
    if os.geteuid()!=0:raise RuntimeError('Run as root on Sonic Pad.')
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='start':start()
    elif action=='stop':stop()
    elif action=='restart':stop();start()
    elif action=='status':print('running' if current() else 'stopped')
    else:raise ValueError('Expected start|stop|restart|status')
if __name__=='__main__':
    try:main()
    except Exception as error:print('ERROR: '+str(error),file=sys.stderr);sys.exit(1)

#!/usr/bin/env python3
"""Install the exact R4 dependency required by the verified native launcher."""
import ast,hashlib,os,shutil,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=Path('/etc/falcon_a1')
SERVICE=Path('/etc/init.d/falcon_a1_bridge')
BOOT=Path('/etc/rc.d/S99falcon_a1_bridge')
EXPECTED='bedd02fe96aaa438ec15926f9876fe33b777049087768c1907fe8e75686a146f'
RC_COMMON=Path('/etc/rc.common')
MARKER='FALCON_SONIC_PAD_MANAGED_R4=1'
def check():
    if os.geteuid()!=0 or sys.version_info<(3,7):raise RuntimeError('Requires root and Python 3.7+ on Sonic Pad.')
    if not RC_COMMON.exists():raise RuntimeError('Expected Sonic Pad/OpenWrt init system not found.')
    for name in ['python3','sha256sum','ffmpeg']:
        if not shutil.which(name):raise RuntimeError('Missing dependency: '+name)
    if hashlib.sha256((HERE/'falcon_a1_bridge_r4.py').read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('R4 source checksum mismatch.')
    for name in ['falcon_a1_bridge_r4.py','service_control.py','sonic_serial_relay.py','sonic_camera_photo.py']:
        ast.parse((HERE/name).read_text(encoding='utf8'),filename=name)
    live=ROOT/'bridge_r3.py'
    if live.exists() and hashlib.sha256(live.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('Unknown/older bridge exists; migrate it separately. No files changed.')
    if SERVICE.exists() and (not live.exists() or 'BRIDGE=/etc/falcon_a1/bridge_r3.py' not in SERVICE.read_text()):raise RuntimeError('Unknown existing service; left untouched.')
    if BOOT.is_symlink() and os.readlink(str(BOOT))!='../init.d/falcon_a1_bridge':raise RuntimeError('Unexpected autostart link; left untouched.')
    if BOOT.exists() and not BOOT.is_symlink():raise RuntimeError('Unexpected autostart file; left untouched.')
    print('CHECK PASSED: prerequisites and exact R4 verified; no machine commands sent.')
def install():
    check()
    if SERVICE.exists():print('Compatible R4 service already installed; registration and processes preserved.');return
    ROOT.mkdir(parents=True,exist_ok=True)
    for source,target in [('falcon_a1_bridge_r4.py','bridge_r3.py'),('service_control.py','service_control.py')]:
        shutil.copyfile(str(HERE/source),str(ROOT/target));os.chmod(str(ROOT/target),0o600)
    shutil.copyfile(str(HERE/'falcon_a1_bridge.init'),str(SERVICE));os.chmod(str(SERVICE),0o755)
    BOOT.parent.mkdir(parents=True,exist_ok=True)
    if not BOOT.is_symlink():BOOT.symlink_to('../init.d/falcon_a1_bridge')
    try:subprocess.run([str(SERVICE),'start'],check=True)
    except Exception:
        if BOOT.is_symlink():BOOT.unlink()
        SERVICE.unlink();raise
    print('INSTALLED: read-only R4 autostart; native relay starts with FDS over SSH.')
def uninstall():
    if os.geteuid()!=0:raise RuntimeError('Requires root.')
    if not SERVICE.exists() or MARKER not in SERVICE.read_text():raise RuntimeError('Only this package managed service can be removed. Legacy services preserved.')
    subprocess.run([str(SERVICE),'stop'],check=True)
    if BOOT.is_symlink() and os.readlink(str(BOOT))=='../init.d/falcon_a1_bridge':BOOT.unlink()
    SERVICE.unlink();print('Service/autostart removed; scripts retained in /etc/falcon_a1.')
def main():
    action=sys.argv[1] if len(sys.argv)>1 else 'check'
    if action=='check':check()
    elif action=='install':install()
    elif action=='uninstall':uninstall()
    else:raise ValueError('Expected check|install|uninstall')
if __name__=='__main__':
    try:main()
    except Exception as error:print('ERROR: '+str(error),file=sys.stderr);sys.exit(1)

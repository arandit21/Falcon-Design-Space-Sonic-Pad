"""Interactive initial SSH pairing; no motion or laser commands."""
from pathlib import Path
import subprocess
import shlex
import sys
from connection_settings import state_dir, read_host

ROOT=Path(__file__).resolve().parent

def main():
    state=state_dir(ROOT);key=state/'.ssh'/'falcon_sonic_rsa';known=key.parent/'known_hosts'
    current=read_host(ROOT)
    print('Первоначальная настройка Sonic Pad. Движение и лазер не включаются.',flush=True)
    entered=input('IP Sonic Pad ['+current+']: ').strip()
    if entered:
        import ipaddress
        ipaddress.IPv4Address(entered)
        (state/'connection.ini').write_text('[Connection]\nhost='+entered+'\n',encoding='utf8')
    host=read_host(ROOT)
    options=['-oHostKeyAlgorithms=+ssh-rsa','-oPubkeyAcceptedAlgorithms=ssh-rsa','-oMACs=+hmac-sha1','-oConnectTimeout=10','-oHostKeyAlias=falcon-sonic-pad','-oUserKnownHostsFile="'+known.as_posix()+'"','-i',str(key),'-oIdentitiesOnly=yes']
    probe=subprocess.run(['ssh']+options+['-oBatchMode=yes','-oStrictHostKeyChecking=yes','root@'+host,'true'],capture_output=True)
    if probe.returncode:
        print('Подтверди отпечаток SSH только своего Sonic Pad и введи его root-пароль. Пароль не сохраняется.',flush=True)
        public=key.with_suffix('.pub').read_text(encoding='ascii').strip();quoted=shlex.quote(public)
        command='set -e; umask 077; mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; grep -qxF '+quoted+' /root/.ssh/authorized_keys || printf "\\n%s\\n" '+quoted+' >> /root/.ssh/authorized_keys; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys; if [ -d /etc/dropbear ]; then touch /etc/dropbear/authorized_keys; grep -qxF '+quoted+' /etc/dropbear/authorized_keys || printf "\\n%s\\n" '+quoted+' >> /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys; fi'
        subprocess.run(['ssh']+options+['-oStrictHostKeyChecking=ask','root@'+host,command],check=True)
    subprocess.run(['ssh']+options+['-oBatchMode=yes','-oStrictHostKeyChecking=yes','root@'+host,'true'],check=True)
    print('Устанавливаем совместимую службу Sonic Pad. Движение и лазер не включаются.',flush=True)
    package=ROOT/'sonic-pad'
    files=[package/name for name in ['falcon_a1_bridge_r4.py','service_control.py','falcon_a1_bridge.init','install_service.py','sonic_serial_relay.py','sonic_camera_photo.py','sonic_native.sh']]
    if not all(path.is_file() for path in files):raise RuntimeError('В установке отсутствует пакет службы Sonic Pad.')
    remote='/mnt/UDISK/falcon_sonicpad_service'
    subprocess.run(['ssh']+options+['-oBatchMode=yes','-oStrictHostKeyChecking=yes','root@'+host,'mkdir -p '+remote],check=True)
    subprocess.run(['scp','-O']+options+['-oBatchMode=yes','-oStrictHostKeyChecking=yes']+[str(path) for path in files]+['root@'+host+':'+remote+'/'],check=True)
    subprocess.run(['ssh']+options+['-oBatchMode=yes','-oStrictHostKeyChecking=yes','root@'+host,'python3 '+remote+'/install_service.py check && python3 '+remote+'/install_service.py install'],check=True)
    print('Готово. Дальше запускай ярлык Falcon — Sonic Pad.',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Настройка не завершена: '+str(error),flush=True)
        input('Нажми Enter, чтобы закрыть окно. Настройку можно повторить ярлыком в меню Пуск.')
        sys.exit(1)

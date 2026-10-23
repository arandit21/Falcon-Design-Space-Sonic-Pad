from pathlib import Path
import importlib.util,json,shutil,subprocess,sys,tempfile
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src/windows'))
import install,base_install,first_setup

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
service=load('service_install',REPO/'sonic-pad/install_service.py')
class Boot:
 def __init__(self,path):self.parent=path.parent;self.target=None
 def exists(self):return self.target is not None
 def is_symlink(self):return self.target is not None
 def symlink_to(self,target):self.target=target
 def unlink(self):self.target=None
 def __fspath__(self):return str(self.parent/'S99falcon_a1_bridge')
base=REPO/'tests/test_runs';base.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=base,prefix='public_') as folder:
 t=Path(folder);app=t/'Sonic Pad';app.mkdir();state=t/'User Data';conf=t/'Fresh Config';fds=t/'FDS';fds.mkdir()
 shutil.copy2(REPO/'dist/payload/calibration.json',app/'calibration.json')
 install.install(app,conf,t/'missing-key',make_shortcuts=False,data_root=state)
 assert json.loads((app/'calibration.json').read_text())['CameraConfig']==[]
 key=state/'.ssh/falcon_sonic_rsa'
 assert subprocess.run(['ssh-keygen','-y','-f',str(key)],capture_output=True).returncode==0
 shutil.copytree(REPO/'dist/payload/base_patch',app/'base_patch')
 (fds/'FalconDesignSpace.exe').write_bytes(b'clean FDS fixture')
 base_install.apply(app,fds);base_install.apply(app,fds);base_install.restore(app)
 assert (fds/'FalconDesignSpace.exe').read_bytes()==b'clean FDS fixture'
 shutil.copytree(REPO/'sonic-pad',app/'sonic-pad')
 calls=[]
 def fake_ssh(args,**kw):calls.append(args);return subprocess.CompletedProcess(args,1 if len(calls)==1 else 0)
 with patch.object(first_setup,'ROOT',app),patch('builtins.input',return_value='192.168.1.37'),patch.object(first_setup.subprocess,'run',side_effect=fake_ssh):first_setup.main()
 assert len(calls)==6 and calls[-2][0]=='scp' and 'install_service.py check' in calls[-1][-1]
 assert '-oStrictHostKeyChecking=ask' in calls[1]
 assert '192.168.1.37' in (state/'connection.ini').read_text()
 rc=t/'rc.common';rc.touch();root=t/'etc/falcon_a1';init=t/'etc/init.d/falcon_a1_bridge';init.parent.mkdir(parents=True);boot=Boot(t/'etc/rc.d/S99falcon_a1_bridge')
 with patch.object(service,'ROOT',root),patch.object(service,'SERVICE',init),patch.object(service,'BOOT',boot),patch.object(service,'RC_COMMON',rc),patch.object(service.os,'geteuid',return_value=0,create=True),patch.object(service.os,'readlink',return_value='../init.d/falcon_a1_bridge'),patch.object(service.shutil,'which',return_value='/usr/bin/fixture'),patch.object(service.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
  service.install();assert boot.target=='../init.d/falcon_a1_bridge' and init.exists()
  original=init.read_bytes();service.install();assert init.read_bytes()==original
  init.write_text('unknown service')
  try:service.install();raise AssertionError('Unknown service was accepted')
  except RuntimeError:pass
  assert init.read_text()=='unknown service'
  init.write_bytes(original);service.uninstall();assert not init.exists() and boot.target is None
  # A failed fresh service start must not remain registered at boot.
  run.side_effect=subprocess.CalledProcessError(1,['fixture'])
  try:service.install();raise AssertionError('Failed startup accepted')
  except subprocess.CalledProcessError:pass
  assert not init.exists() and boot.target is None
 print('PASS: clean key generation; empty public calibration; base patch restore; SSH bootstrap and service upload; new/existing/unknown service; boot registration and failed-start cleanup (network/processes mocked)')

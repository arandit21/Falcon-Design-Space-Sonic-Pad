"""Offline tests of the unified installer. No SSH, services, motion or device writes."""
from pathlib import Path
import importlib.util,json,os,shutil,tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sonic_ru_installer',ROOT/'sonic-pad-russian/install.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
INPUTS=Path(os.environ.get('SONIC_RU_BUILD_INPUTS',str(ROOT/'inputs')))
PACKAGE=ROOT/'dist/sonic_pad_russian/Sonic_Pad_Russian_54.20_1.0.0'
manifest=json.loads((PACKAGE/'manifest.json').read_text(encoding='utf8'))
testroot=ROOT/'tests/test_runs';testroot.mkdir(exist_ok=True)
def fixture(base):
 target=base/'device';target.mkdir()
 for item in manifest['files']:
  path=item['path'];src=INPUTS/('ui' if 'fluidd-pad/' in path else 'web/stock')/path;dst=target/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
  if '/css/' in path:dst.write_bytes(b'original custom css fixture\n')
 for item in manifest['guards']:
  path=item['path'];src=INPUTS/('web/stock' if '/fluidd/' in path else 'ui')/path;dst=target/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 for path in ['usr/share/fluidd-pad/config.json','usr/share/fluidd-pad/customUi/init.json','usr/share/web/pad/config.json','printer_data/config/printer.cfg']:
  p=target/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('KEEP USER CONFIG')
 return target
with tempfile.TemporaryDirectory(dir=testroot,prefix='sonic_suite_') as folder:
 base=Path(folder);target=fixture(base);state=base/'backup';original={item['path']:(target/item['path']).read_bytes() for item in manifest['files']}
 module.check(PACKAGE,target);assert not state.exists()
 module.install(PACKAGE,target,state);module.verify(PACKAGE,target)
 backup=(state/'original/snapshot.json').read_bytes();count=len(list(state.iterdir()))
 module.install(PACKAGE,target,state);assert backup==(state/'original/snapshot.json').read_bytes() and len(list(state.iterdir()))==count
 for path in ['usr/share/fluidd-pad/config.json','usr/share/fluidd-pad/customUi/init.json','usr/share/web/pad/config.json','printer_data/config/printer.cfg']:assert (target/path).read_text()=='KEEP USER CONFIG'
 module.restore(PACKAGE,target,state)
 assert all((target/path).read_bytes()==data for path,data in original.items())
 # Fault after partial installation must restore the state from this attempt.
 real_copy=module.atomic_copy;calls=[0]
 def fail_once(*args):
  calls[0]+=1
  if calls[0]==4:raise OSError('fixture failure')
  return real_copy(*args)
 with patch.object(module,'atomic_copy',side_effect=fail_once):
  try:module.install(PACKAGE,target,state);raise AssertionError('Failure not propagated')
  except OSError:pass
 assert all((target/path).read_bytes()==data for path,data in original.items())
 # Unknown application/firmware must be rejected before any write.
 item=next(x for x in manifest['files'] if x['path'].endswith('app.45351586.js'));(target/item['path']).write_bytes(b'unknown firmware')
 before={x['path']:(target/x['path']).read_bytes() for x in manifest['files']}
 try:module.install(PACKAGE,target,state);raise AssertionError('Unknown firmware accepted')
 except RuntimeError:pass
 assert all((target/path).read_bytes()==data for path,data in before.items())
 (target/item['path']).write_bytes(original[item['path']])
 # A corrupt package is refused; no target bytes are changed.
 bad=base/'bad-package';shutil.copytree(PACKAGE,bad);(bad/'payload'/manifest['files'][0]['path']).write_bytes(b'corrupt')
 try:module.install(bad,target,state);raise AssertionError('Corrupt package accepted')
 except RuntimeError:pass
 assert all((target/path).read_bytes()==data for path,data in original.items())
print('PASS: complete install/verify/restore, repeat-install preservation, partial failure rollback, unknown build rejection, corrupt payload rejection, user configurations untouched')

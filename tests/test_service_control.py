from pathlib import Path
import importlib.util,tempfile,subprocess
from unittest.mock import patch
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('manager',repo/'sonic-pad/service_control.py');manager=importlib.util.module_from_spec(spec);spec.loader.exec_module(manager)
with tempfile.TemporaryDirectory(dir=repo/'tests/test_runs') as folder:
 root=Path(folder);pidfile=root/'pid';pidfile.write_text('1')
 with patch.object(manager,'PIDFILE',pidfile):assert manager.current() is None
 pidfile.write_text('123456')
 with patch.object(manager,'PIDFILE',pidfile),patch.object(manager,'owned',return_value=False),patch.object(manager.os,'kill') as kill:
  assert manager.current() is None;manager.stop();kill.assert_not_called()
 bridge=root/'bridge';bridge.write_text('unknown program')
 with patch.object(manager,'BRIDGE',bridge),patch.object(manager,'current',return_value=123456),patch.object(manager.os,'kill') as kill:
  try:manager.stop();raise AssertionError('Changed script accepted')
  except RuntimeError:pass
  kill.assert_not_called()
print('PASS: service manager ignores PID 1, stale/unrecognized PID and changed bridge; no signals sent')

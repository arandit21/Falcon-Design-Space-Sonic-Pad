from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src/windows"))
from startup_support import refresh_lease

calls=[]
def intermittent(port,op):
    calls.append((port,op))
    if len(calls)<3:raise TimeoutError('fixture transient timeout')
    return {'ok':True}
assert refresh_lease(intermittent,12345,'owned-instance',pause=lambda _:None)=={'ok':True}
assert calls==[(12345,{'op':'lease','instance':'owned-instance'})]*3
calls.clear()
def unavailable(port,op):
    calls.append(op)
    raise TimeoutError('fixture unavailable')
try:refresh_lease(unavailable,12345,'owned-instance',pause=lambda _:None);raise AssertionError('Missing failure')
except TimeoutError:pass
assert len(calls)==3
print('PASS: transient heartbeat recovered; persistent failure bounded; only lease requests retried')
